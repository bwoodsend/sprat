complete -c sprat -f

# Top level commands
complete -x -c sprat -n "not __fish_seen_subcommand_from search info sync" -a "search info sync"
complete -c sprat -f -l help -s h -d 'Display help and exit'

# sprat info
# Complete package names if at least one character has already been typed
complete -c sprat -n "__fish_seen_subcommand_from info" -n 'test -n "$(commandline -t)"' -a '(sprat search -q --name "^"(commandline -t))'
# Output format flags, don't suggest if -a/--all or -j/--json are already specified
complete -c sprat -n "__fish_seen_subcommand_from info" -n "not __fish_seen_argument -a --all -j --json" -f -l classifiers -s c -d 'Show classifiers'
complete -c sprat -n "__fish_seen_subcommand_from info" -n "not __fish_seen_argument -a --all -j --json" -f -l versions -s v -d 'Show releases'
complete -c sprat -n "__fish_seen_subcommand_from info" -n "not __fish_seen_argument -a --all -j --json" -f -l urls -s u -d 'Show all URLs'
complete -c sprat -n "__fish_seen_subcommand_from info" -n "not __fish_seen_argument -a --all -j --json" -f -l all -s a -d 'Show everything'
complete -c sprat -n "__fish_seen_subcommand_from info" -n "not __fish_seen_argument -a --all -j --json" -f -l json -s j -d 'JSON output'

# sprat search
complete -c sprat -n "__fish_seen_subcommand_from search" -n "not __fish_seen_argument -q --quiet -j --json" -f -l json -s j -d 'JSON output'
complete -c sprat -n "__fish_seen_subcommand_from search" -n "not __fish_seen_argument -q --quiet -j --json" -f -l quiet -s q -d 'Print names only'
complete -c sprat -n "__fish_seen_subcommand_from search" -f -l name -s n -d 'Search by name'
complete -c sprat -n "__fish_seen_subcommand_from search" -f -l summary -s s -d 'Search summaries'
complete -c sprat -n "__fish_seen_subcommand_from search" -f -l classifiers -s c -d 'Search in classifiers'
complete -c sprat -n "__fish_seen_subcommand_from search" -f -l keywords -s k -d 'Search in keywords'

# sprat update
# Hide --index flag unless user seems to already know it exists
complete -c sprat -n "__fish_seen_subcommand_from sync" -n '__fish_seen_argument --index || commandline -t | string match -rq i' -F -r -l index
