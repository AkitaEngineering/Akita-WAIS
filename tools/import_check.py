import importlib, sys
mods=['akita_wais','akita_wais.cli','akita_wais.config','akita_wais.common','akita_wais.identity','akita_wais.client','akita_wais.server']
for m in mods:
    try:
        importlib.import_module(m)
        print('Imported', m)
    except Exception as e:
        print('ERROR importing', m, e)
        sys.exit(2)
print('All imports OK')
