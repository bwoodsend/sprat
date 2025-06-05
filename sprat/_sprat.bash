#!/usr/bin/env bash

_sprat_completion() {
    local cur prev words cword
    _init_completion || return

    local commands="search info sync"
    local has_command=0
    local command=""

    # Determine if we have a command already
    for word in "${words[@]:1:cword}"; do
        if [[ " $commands " == *" $word "* ]]; then
            has_command=1
            command=$word
            break
        fi
    done

    # Global options and main commands
    if [[ $prev == "sprat" || $has_command -eq 0 ]]; then
        if [[ $cur == -* ]]; then
            # Handle options for the main command
            COMPREPLY=($(compgen -W "--help -h" -- "$cur"))
        else
            # Suggest main commands
            COMPREPLY=($(compgen -W "$commands" -- "$cur"))
        fi
        return 0
    fi

    # Command-specific options
    case $command in
        info)
            if [[ $cur == -* ]]; then
                COMPREPLY=($(compgen -W "--classifiers -c --versions -v --urls -u --all -a --json -j" -- "$cur"))
            elif [[ -n "$cur" ]]; then
                # Complete package names only when at least one character is provided
                local package_names=$(sprat search -q --name "^$cur")
                COMPREPLY=($(compgen -W "$package_names" -- "$cur"))
            fi
            ;;
        search)
            if [[ $cur == -* ]]; then
                COMPREPLY=($(compgen -W "--json -j --quiet -q --name -n --summary -s --classifiers -c --keywords -k" -- "$cur"))
            fi
            ;;
        sync)
            if [[ $cur == -* ]]; then
                COMPREPLY=($(compgen -W "--index" -- "$cur"))
            fi
            ;;
    esac

    return 0
}

complete -F _sprat_completion sprat