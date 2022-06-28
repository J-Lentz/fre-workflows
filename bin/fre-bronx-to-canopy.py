#!/home/oar.gfdl.sw/conda/miniconda3/envs/cylc/bin/python
import argparse
import re
import sys
import subprocess
import metomi.rose.config
import metomi.isodatetime.parsers

#
# Usage: fre-bronx-to-canopy -x XML -e EXP -p PLATFORM -t TARGET
#
# Will overwrite 3 files:
# - rose-suite.conf
# - app/remap-pp-components/rose-app.conf
# - app/regrid-xy/rose-app.conf
#

def freq_from_legacy(legacy_freq):
    """Return ISO8601 duration given Bronx-style frequencies

    Arguments:
        legacy_freq (str)
"""
    lookup = {
        'annual': 'P1Y',
        'monthly': 'P1M',
        'seasonal': 'P3M',
        'daily': 'P1D',
        '120hr': 'P120D',
        '12hr': 'PT12H',
        '8hr': 'PT8H',
        '6hr': 'PT6H',
        '4hr': 'PT4H',
        '3hr': 'PT3H',
        '2hr': 'PT2H',
        '1hr': 'PT1H',
        'hourly': 'PT1H',
        '30min': 'PT30M' }
    return lookup[legacy_freq]

def chunk_from_legacy(legacy_chunk):
    """Return ISO8601 duration given Bronx-style chunk

    Arguments:
        legacy_chunk (str)
"""
    regex = re.compile('(\d+)(\w+)')
    match = regex.match(legacy_chunk)
    if not match:
        print("ERROR: Could not convert Bronx chunk to ISO8601 duration:", legacy_chunk)
        raise Exception
    if match.group(2) == "yr":
        return 'P{}Y'.format(match.group(1))
    elif match.group(2) == 'mo':
        return 'P{}M'.format(match.group(1))
    else:
        raise Exception('Unknown time units', match.group(2))

def frelist_xpath(args, xpath):
    cmd = "frelist -x {} -p {} -t {} {} --evaluate '{}'".format(args.xml, args.platform, args.target, args.experiment, xpath)
    print(">>", xpath)
    process = subprocess.run(cmd, shell=True, check=True, capture_output=True, universal_newlines=True)
    result = process.stdout.strip()
    print(result)
    return(result)

def main(args):
    xml = args.xml
    expname = args.experiment
    platform = args.platform
    target = args.target
    debug = args.debug

    rose_remap = metomi.rose.config.ConfigNode()
    rose_remap.set(keys=['command', 'default'], value='remap-pp-components')
    rose_regrid_xy = metomi.rose.config.ConfigNode()
    rose_regrid_xy.set(keys=['command', 'default'], value='regrid-xy')
    rose_suite = metomi.rose.config.ConfigNode()
    rose_suite.set(keys=['template variables', 'PTMP_DIR'], value="'/xtmp/$USER/ptmp'")
    rose_suite.set(keys=['template variables', 'CLEAN_WORK'], value='True')
    rose_suite.set(keys=['template variables', 'DO_MDTF'], value='False')
    
    if args.pp_start is not None:
        rose_suite.set(keys=['template variables', 'PP_START'], value="'" + str(args.pp_start) + "'")
    else:
        rose_suite.set(keys=['template variables', 'PP_START'], value="'YYYY'")

    if args.pp_stop is not None:
        rose_suite.set(keys=['template variables', 'PP_STOP'], value="'" + str(args.pp_stop) + "'")
    else:
        rose_suite.set(keys=['template variables', 'PP_STOP'], value="'YYYY'")

    if args.do_refined:
        rose_suite.set(keys=['template variables', 'DO_REFINEDIAG'], value='True')
        rose_suite.set(keys=['template variables', 'REFINEDIAG_NAME'], value="'atmos'") # Currently arbitrary value and only 1 value by default at this time.
    else:
        rose_suite.set(keys=['template variables', 'DO_REFINEDIAG'], value='False')

    if args.do_preanalysis:
        rose_suite.set(keys=['template variables', 'DO_PREANALYSIS'], value='True')
        rose_suite.set(keys=['template variables', 'PREANALYSIS_NAME'], value="'vitals'")
    else:
        rose_suite.set(keys=['template variables', 'DO_PREANALYSIS'], value='False')

    rose_suite.set(keys=['template variables', 'EXPERIMENT'], value="'{}'".format(expname))
    rose_suite.set(keys=['template variables', 'PLATFORM'], value="'{}'".format(platform))
    rose_suite.set(keys=['template variables', 'TARGET'], value="'{}'".format(target))

    regex_fre_property = re.compile('\$\((\w+)')
    all_components = set()

    print("Running frelist for XML parsing...")
    print("If this fails, try running the 'frelist' call manually. Did you module load FRE?\n")
    cmd = "frelist -x {} -p {} -t {} {} -d archive".format(xml, platform, target, expname)
    print(">>", cmd)
    process = subprocess.run(cmd, shell=True, check=True, capture_output=True, universal_newlines=True)
    historyDir = process.stdout.strip() + '/history'
    historyDirRefined = historyDir + '_refineDiag'
    print(historyDir)
    cmd = "frelist -x {} -p {} -t {} {} -d postProcess".format(xml, platform, target, expname)
    print(">>", cmd)
    process = subprocess.run(cmd, shell=True, check=True, capture_output=True, universal_newlines=True)
    ppDir = process.stdout.strip()
    print(ppDir)
    gridSpec = frelist_xpath(args, 'input/dataFile[@label="gridSpec"]')
    simTime = frelist_xpath(args, 'runtime/production/@simTime')
    rose_suite.set(keys=['template variables', 'HISTORY_DIR'], value="'{}'".format(historyDir))
    rose_suite.set(keys=['template variables', 'HISTORY_DIR_REFINED'], value="'{}'".format(historyDirRefined))
    rose_suite.set(keys=['template variables', 'PP_DIR'], value="'{}'".format(ppDir))

    if rose_suite.get_value(keys=['template variables', 'DO_REFINEDIAG']) == "True":
       refineDiag_cmd = "frelist -x {} -p {} -t {} {} --evaluate postProcess/refineDiag/@script".format(xml, platform, target, expname)
       refineDiag_process = subprocess.run(refineDiag_cmd, shell=True, check=True, capture_output=True, universal_newlines=True)
       str_output = "'" + refineDiag_process.stdout + "'"
       proc_output_list = str_output.replace(",", "','").replace(" ", "','").replace("\n", "").split(",")

       preanalysis = "refineDiag_data_stager_globalAve.csh"
       preanalysis_path = None
       try:
           preanalysis_path = proc_output_list.pop([idx for idx, substr in enumerate(proc_output_list) if preanalysis in substr][0])
       except IndexError:
           pass
           
       refineDiag_scripts = ",".join(proc_output_list)
       rose_suite.set(keys=['template variables', 'REFINEDIAG_SCRIPT'], value=refineDiag_scripts)

    if rose_suite.get_value(keys=['template variables', 'DO_PREANALYSIS']) == "True":
        if preanalysis_path is not None:
            rose_suite.set(keys=['template variables', 'PREANALYSIS_SCRIPT'], value=preanalysis_path)
        else:
            rose_suite.set(keys=['template variables', 'PREANALYSIS_SCRIPT'], value="''")

    comps = frelist_xpath(args, 'postProcess/component/@type').split()
    rose_suite.set(keys=['template variables', 'PP_COMPONENTS'], value="'{}'".format(' '.join(comps)))

    segment_time = frelist_xpath(args, 'runtime/production/segment/@simTime')
    segment_units = frelist_xpath(args, 'runtime/production/segment/@units')
    if segment_units == 'years':
        segment = 'P' + segment_time + 'Y'
    elif segment_units == 'months':
        segment = 'P' + segment_time + 'M'
    else:
        raise Exception("Unknown segment units:", segment_units)
    # P12M is identical to P1Y but the latter looks nicer
    if segment == 'P12M':
        segment = 'P1Y'
    rose_suite.set(keys=['template variables', 'HISTORY_SEGMENT'], value="'{}'".format(segment))

    comp_count = 0
    for comp in comps:
        comp_count += 1
        print("Component loop: {} out of {}".format(comp_count, len(comps)))
        comp_source = frelist_xpath(args, 'postProcess/component[@type="{}"]/@source'.format(comp))
        xyInterp = frelist_xpath(args, 'postProcess/component[@type="{}"]/@xyInterp'.format(comp))
        sourceGrid = frelist_xpath(args, 'postProcess/component[@type="{}"]/@sourceGrid'.format(comp))
        if xyInterp:
            grid = "regrid-xy"
        else:
            grid = "native"
        sources = set()
        timeseries_count = 0

        # get the number of TS nodes
        results = frelist_xpath(args, 'postProcess/component[@type="{}"]/timeSeries/@freq'.format(comp)).split()
        timeseries_count = len(results)

        # loop over the TS nodes
        for i in range(1, timeseries_count + 1):
            label = comp + '.' + str(i)

            source = frelist_xpath(args, 'postProcess/component[@type="{}"]/timeSeries[{}]/@source'.format(comp, i))
            if source:
                sources.add(source)
                rose_remap.set(keys=[label, 'source'], value=source)
            elif comp_source:
                sources.add(comp_source)
                rose_remap.set(keys=[label, 'source'], value=comp_source)
            else:
                print("WARNING: Skipping a timeSeries with no source and no component source for", comp)
                continue

            freq = freq_from_legacy(frelist_xpath(args, 'postProcess/component[@type="{}"]/timeSeries[{}]/@freq'.format(comp, i)))
            chunk = chunk_from_legacy(frelist_xpath(args, 'postProcess/component[@type="{}"]/timeSeries[{}]/@chunkLength'.format(comp, i)))
            rose_remap.set(keys=[label, 'freq'], value=freq)
            rose_remap.set(keys=[label, 'chunk'], value=chunk)
            rose_remap.set(keys=[label, 'grid'], value=grid)

        rose_remap.set(keys=[comp + '.static', 'source'], value=' '.join(sources))
        rose_remap.set(keys=[comp + '.static', 'chunk'], value="P0Y")
        rose_remap.set(keys=[comp + '.static', 'freq'], value="P0Y")
        rose_remap.set(keys=[comp + '.static', 'grid'], value=grid)

        if grid == "native":
            continue
        else:
            rose_regrid_xy.set(keys=[comp, 'sources'], value=' '.join(sources))
            sourcegrid_split = sourceGrid.split('-')
            rose_regrid_xy.set(keys=[comp, 'inputGrid'], value=sourcegrid_split[1])
            rose_regrid_xy.set(keys=[comp, 'inputRealm'], value=sourcegrid_split[0])
            interp_split = xyInterp.split(',')
            rose_regrid_xy.set(keys=[comp, 'outputGridLon'], value=interp_split[1])
            rose_regrid_xy.set(keys=[comp, 'outputGridLat'], value=interp_split[0])
            rose_regrid_xy.set(keys=[comp, 'gridSpec'], value=gridSpec)
            rose_suite.set(keys=['template variables', 'GRID_SPEC'], value="'{}'".format(gridSpec))

    print("\nSetting PP chunks...")
    all_chunks = set()
    def duration_to_seconds(duration):
        dur = metomi.isodatetime.parsers.DurationParser().parse(duration)
        return dur.get_seconds()

    for keys, sub_node in rose_remap.walk():
        if len(keys) != 1:
            continue
        item = keys[0]
        if item == "env" or item == "command":
            continue
        chunk = rose_remap.get_value(keys=[item, 'chunk'])
        if chunk == 'P0Y':
            continue
        all_chunks.add(chunk)

    sorted_chunks = list(all_chunks)
    sorted_chunks.sort(key=duration_to_seconds, reverse=False)

    assert len(all_chunks) >= 1
    print("  Chunks found:", ', '.join(sorted_chunks))
    if len(all_chunks) == 1:
        rose_suite.set(['template variables', 'PP_CHUNK_A'], "'{}'".format(sorted_chunks[0]))
        rose_suite.set(['template variables', 'PP_CHUNK_B'], "'{}'".format(sorted_chunks[0]))
    else:
        rose_suite.set(['template variables', 'PP_CHUNK_A'], "'{}'".format(sorted_chunks[0]))
        rose_suite.set(['template variables', 'PP_CHUNK_B'], "'{}'".format(sorted_chunks[1]))
    print("  Chunks used: ", ', '.join(sorted_chunks[0:2]))
    
    print("\nWriting output files...")
    dumper = metomi.rose.config.ConfigDumper()
    
    outfile = "rose-suite.conf"
    print("  ", outfile)
    dumper(rose_suite, outfile)

    outfile = "app/remap-pp-components/rose-app.conf"
    print("  ", outfile)
    dumper(rose_remap, outfile)

    outfile = "app/regrid-xy/rose-app.conf"
    print("  ", outfile)
    dumper(rose_regrid_xy, outfile)

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="FRE Bronx-to-Canopy converter")
    parser.add_argument('--xml', '-x', required=True, help="Bronx XML")
    parser.add_argument('--platform', '-p', required=True, help="Platform")
    parser.add_argument('--target', '-t', required=True, help="Target")
    parser.add_argument('--experiment', '-e', required=True, help="Experiment")
    parser.add_argument('--do_refined', action='store_true', default=False, help="Process refineDiag scripts")
    parser.add_argument('--do_preanalysis', action='store_true', default=False, help="Process preanalysis scripts")
    parser.add_argument('--pp_start', help="Starting year of postprocessing. If not specified, default value is 'YYYY' and must be changed in rose-suite.conf")
    parser.add_argument('--pp_stop', help="Ending year of postprocessing. If not specified, default value is 'YYYY' and must be changed in rose-suite.conf")
    parser.add_argument('--debug', action='store_true', required=False, help="print additional output")

    args = parser.parse_args()
    main(args)

