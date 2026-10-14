import os
import shutil
from datetime import datetime


def get_files_info(base_folder, exclude_folders):
    """
    Recursively scan the base folder and return files (with absolute path) and timestamps.

    Parameters:
    - base_folder => The root folder of the area we want to compare.
    - exclude_folders => Folders that we want to exclude from our comparison. They must be defined with relative (to the base folder) path.
    """
    files = {}

    for root, dirs, filenames in os.walk(base_folder):

        for filename in filenames:
            # Skip excluded folders
            if any(f in root for f in exclude_folders):
                continue

            # Set absolute path
            file_path = os.path.join(root, filename)

            # Get file modification time
            modified_time = datetime.fromtimestamp(os.path.getmtime(file_path))

            # Calculate relative path
            relative_path = os.path.relpath(file_path, base_folder)

            # Extract files
            files[relative_path] = {
                'filepath': file_path,
                'modified_time': modified_time
            }

    return files


def get_directories_info(base_folder, exclude_folders):
    """
    Recursively scan the base folder and return all directories.

    Parameters:
    - base_folder => The root folder to scan.
    - exclude_folders => Folders to exclude from the scan (relative paths).
    """
    directories = {}

    for root, dirs, filenames in os.walk(base_folder):
        # Skip excluded folders
        exclude = [os.path.join(base_folder, e) for e in exclude_folders]
        if any(f in root for f in exclude):
            continue

        for dirname in dirs:
            dir_path = os.path.join(root, dirname)
            # Skip if this directory is in the exclude list
            if any(f in dir_path for f in exclude):
                continue

            relative_path = os.path.relpath(dir_path, base_folder)
            directories[relative_path] = dir_path

    return directories


def compare_folders(folder1, folder2, exclude_folders1, exclude_folders2):
    """
    Compare two folders and return files that differ.

    Parameters:
    - folder1: First base folder path
    - folder2: Second base folder path
    - exclude_folders1: List of folders to exclude from folder1 (relative paths)
    - exclude_folders2: List of folders to exclude from folder2 (relative paths)
    """
    # Get file information from both folders
    files1 = get_files_info(folder1, exclude_folders1)
    files2 = get_files_info(folder2, exclude_folders2)

    # Find common and unique files
    common_files = files1.keys() & files2.keys()
    unique_to_folder1 = files1.keys() - files2.keys()
    unique_to_folder2 = files2.keys() - files1.keys()

    # Compare timestamps for common files
    newer_in_folder1 = {}
    newer_in_folder2 = {}

    for file in common_files:
        time1 = files1[file]['modified_time']
        time2 = files2[file]['modified_time']

        if time1 > time2:
            newer_in_folder1[file] = {
                'folder1_path': files1[file]['filepath'],
                'folder1_time': time1,
                'folder2_path': files2[file]['filepath'],
                'folder2_time': time2,
                'time_difference': (time1 - time2).total_seconds()
            }
        elif time2 > time1:
            newer_in_folder2[file] = {
                'folder1_path': files1[file]['filepath'],
                'folder1_time': time1,
                'folder2_path': files2[file]['filepath'],
                'folder2_time': time2,
                'time_difference': (time2 - time1).total_seconds()
            }

    # Prepare results
    results = {
        'only_in_folder1': {file: files1[file] for file in sorted(unique_to_folder1)},
        'only_in_folder2': {file: files2[file] for file in sorted(unique_to_folder2)},
        'newer_in_folder1': dict(sorted(newer_in_folder1.items())),
        'newer_in_folder2': dict(sorted(newer_in_folder2.items())),
        'identical': sorted([file for file in common_files
                           if files1[file]['modified_time'] == files2[file]['modified_time']])
    }

    return results


def report_folder_differences(folder1, folder2, results):
    """
    Compare two folders and print a detailed report of differences to terminal.

    Parameters:
    - folder1: First base folder path
    - folder2: Second base folder path
    - exclude_folders1: List of folders to exclude from folder1 (relative paths)
    - exclude_folders2: List of folders to exclude from folder2 (relative paths)
    """
    print("=" * 80)
    print(f"FOLDER COMPARISON REPORT\n")
    print(f"Folder 1: {folder1}")
    print(f"Folder 2: {folder2}")
    print("=" * 80)

    # Report files only in folder1
    print(f"\n{'FILES ONLY IN FOLDER 1':^80}")
    print("-" * 80)
    if results['only_in_folder1']:
        for file, info in results['only_in_folder1'].items():
            print(f"{file} - Modified: {info['modified_time']}")
        print(f"\n  Total: {len(results['only_in_folder1'])} file(s)")
    else:
        print("  No unique files found.")

    # Report files only in folder2
    print(f"\n{'FILES ONLY IN FOLDER 2':^80}")
    print("-" * 80)
    if results['only_in_folder2']:
        for file, info in results['only_in_folder2'].items():
            print(f"{file} / Modified: {info['modified_time']}")
        print(f"\n  Total: {len(results['only_in_folder2'])} file(s)")
    else:
        print("  No unique files found.")

    # Report files newer in folder1
    print(f"\n{'FILES NEWER IN FOLDER 1':^80}")
    print("-" * 80)
    if results['newer_in_folder1']:
        for file, info in results['newer_in_folder1'].items():
            print(f"{file} / Folder 1: {info['folder1_time']} - Folder 2: {info['folder2_time']}")
        print(f"\n  Total: {len(results['newer_in_folder1'])} file(s)")
    else:
        print("  No files are newer in folder 1.")

    # Report files newer in folder2
    print(f"\n{'FILES NEWER IN FOLDER 2':^80}")
    print("-" * 80)
    if results['newer_in_folder2']:
        for file, info in results['newer_in_folder2'].items():
            print(f"{file} / Folder 2: {info['folder2_time']} - Folder 1: {info['folder1_time']}")
        print(f"\n  Total: {len(results['newer_in_folder2'])} file(s)")
    else:
        print("  No files are newer in folder 2.")

    # Summary
    print(f"\n{'SUMMARY':^80}")
    print("-" * 80)
    print(f"  Only in Folder 1: {len(results['only_in_folder1'])} file(s)")
    print(f"  Only in Folder 2: {len(results['only_in_folder2'])} file(s)")
    print(f"  Newer in Folder 1: {len(results['newer_in_folder1'])} file(s)")
    print(f"  Newer in Folder 2: {len(results['newer_in_folder2'])} file(s)")
    print(f"  Identical files: {len(results['identical'])} file(s)")
    print("=" * 80)

    return results


def sync_folders(source_folder, dest_folder, results, is_source_folder1, delete_files,
                 exclude_source_folders, exclude_dest_folders):
    """
    Sync folders by copying new files from source, copying newer files from source,
    and optionally deleting files only in destination.

    Parameters:
    - source_folder: Source folder path
    - dest_folder: Destination folder path
    - results: Results from compare_folders function
    - is_source_folder1: True if folder1 is source, False if folder2 is source
    - delete_files: If True, delete files that only exist in destination
    - exclude_source_folders: Folders to exclude from source
    - exclude_dest_folders: Folders to exclude from destination
    """
    copied_files = []
    updated_files = []
    deleted_files = []
    deleted_folders = []
    errors = []

    mode = "Syncing" if delete_files else "Merging"
    print(f"\n{mode} from {source_folder} to {dest_folder}...")
    print("-" * 80)

    # Determine which files to copy/delete based on direction
    if is_source_folder1:
        files_only_in_source = results['only_in_folder1']
        files_to_delete = results['only_in_folder2']
        newer_files = results['newer_in_folder1']
    else:
        files_only_in_source = results['only_in_folder2']
        files_to_delete = results['only_in_folder1']
        newer_files = results['newer_in_folder2']

    # Build a unified list of files to copy (new files + newer files)
    files_to_process = []

    # Add files that only exist in source
    for relative_path, file_info in files_only_in_source.items():
        files_to_process.append({
            'relative_path': relative_path,
            'source_path': file_info['filepath'],
            'dest_path': os.path.join(dest_folder, relative_path),
            'is_update': False
        })

    # Add files that are newer in source
    for relative_path, file_info in newer_files.items():
        if is_source_folder1:
            source_path = file_info['folder1_path']
            dest_path = file_info['folder2_path']
        else:
            source_path = file_info['folder2_path']
            dest_path = file_info['folder1_path']

        files_to_process.append({
            'relative_path': relative_path,
            'source_path': source_path,
            'dest_path': dest_path,
            'is_update': True
        })

    # Copy/update files in a single loop
    for file_item in files_to_process:
        relative_path = file_item['relative_path']
        source_path = file_item['source_path']
        dest_path = file_item['dest_path']
        is_update = file_item['is_update']

        try:
            # Create destination directory if it doesn't exist
            dest_dir = os.path.dirname(dest_path)
            if not os.path.exists(dest_dir):
                os.makedirs(dest_dir)

            shutil.copy2(source_path, dest_path)

            if is_update:
                updated_files.append(relative_path)
                print(f"  Updated: {relative_path}")
            else:
                copied_files.append(relative_path)
                print(f"  Copied: {relative_path}")

        except Exception as e:
            errors.append({'file': relative_path, 'error': str(e)})
            action = "updating" if is_update else "copying"
            print(f"  ERROR {action} {relative_path}: {e}")

    # Delete files that only exist in destination (if delete_files is True)
    if delete_files:
        for relative_path, file_info in files_to_delete.items():
            dest_path = file_info['filepath']

            try:
                os.remove(dest_path)
                deleted_files.append(relative_path)
                print(f"  Deleted: {relative_path}")

            except Exception as e:
                errors.append({'file': relative_path, 'error': str(e)})
                print(f"  ERROR deleting {relative_path}: {e}")

        # Delete empty folders that exist in destination but not in source
        source_dirs = get_directories_info(source_folder, exclude_source_folders)
        dest_dirs = get_directories_info(dest_folder, exclude_dest_folders)

        # Find directories that exist in destination but not in source
        dirs_only_in_dest = set(dest_dirs.keys()) - set(source_dirs.keys())

        # Sort by depth (deepest first) to delete children before parents
        dirs_to_delete = sorted(dirs_only_in_dest, key=lambda x: x.count(os.sep), reverse=True)

        for relative_dir in dirs_to_delete:
            dir_path = dest_dirs[relative_dir]

            try:
                # Only delete if directory is empty or becomes empty
                if os.path.exists(dir_path) and not os.listdir(dir_path):
                    os.rmdir(dir_path)
                    deleted_folders.append(relative_dir)
                    print(f"  Deleted folder: {relative_dir}")
            except Exception as e:
                errors.append({'folder': relative_dir, 'error': str(e)})
                print(f"  ERROR deleting folder {relative_dir}: {e}")

    # Print summary
    print("-" * 80)
    completion_msg = "Sync complete!" if delete_files else "Merge complete!"
    print(f"{completion_msg}")
    print(f"  Files copied: {len(copied_files)}")
    print(f"  Files updated: {len(updated_files)}")
    if delete_files:
        print(f"  Files deleted: {len(deleted_files)}")
        print(f"  Folders deleted: {len(deleted_folders)}")
    print(f"  Errors: {len(errors)}")

    return {
        'copied': copied_files,
        'updated': updated_files,
        'deleted': deleted_files,
        'deleted_folders': deleted_folders,
        'errors': errors
    }


def display_menu():
    """Display the sync menu options."""
    print("\n" + "=" * 80)
    print("SYNC OPTIONS MENU")
    print("=" * 80)
    print("SYNC (with deletion):")
    print("1. Sync from Internal to External (copy new/fresh files + delete files only in External)")
    print("2. Sync from External to Internal (copy new/fresh files + delete files only in Internal)")
    print("\nMERGE (no deletion):")
    print("3. Merge from Internal to External (copy new/fresh files only, no deletion)")
    print("4. Merge from External to Internal (copy new/fresh files only, no deletion)")
    print("\nPress ENTER to quit")
    print("-" * 80)


if __name__ == "__main__":
    # List of folders that must be excluded by any sync process. Absolute path required!
    exclude_int_folder = ['.SynologyWorkingDirectory']
    exclude_ext_folder = []

    # Default source and target folder paths.
    default_int_folder = '/home/nikk/Data/PhotoLanding'
    default_ext_folder = '/media/nikk/WDElements/PhotoLanding'

    # Ask user for folder paths. If none is set, we use the default ones.
    print("\n")
    print("=" * 80)
    print("FOLDER COMPARISON TOOL")
    print("=" * 80)
    print("\nPress Enter to use default folders, or type new paths.")

    # Ask for Internal Folder.
    int_folder_input = input(f"\nInternal Folder (default: {default_int_folder}): ").strip()
    int_folder = int_folder_input if int_folder_input else default_int_folder
    if not os.path.exists(int_folder):
        print(f"\nError: Internal folder does not exist: {int_folder}")
        exit(1)

    # Ask for External Folder.
    ext_folder_input = input(f"External Folder (default: {default_ext_folder}): ").strip()
    ext_folder = ext_folder_input if ext_folder_input else default_ext_folder
    if not os.path.exists(ext_folder):
        print(f"\nError: External folder does not exist: {ext_folder}")
        exit(1)

    print(f"\nUsing:")
    print(f"  Internal Folder: {int_folder}")
    print(f"  External Folder: {ext_folder}")
    print()

    # Run the comparison
    results = compare_folders(int_folder, ext_folder, exclude_int_folder, exclude_ext_folder)
    report_folder_differences(int_folder, ext_folder, results)

    # Show menu and handle user choices
    while True:
        display_menu()
        choice = input("Enter your choice: ").strip()

        if choice == "":
            print("\nExiting...")
            break
        elif choice == "1":
            sync_folders(int_folder, ext_folder, results, is_source_folder1=True, delete_files=True,
                         exclude_source_folders=exclude_int_folder, exclude_dest_folders=exclude_ext_folder)
            # Re-run comparison after sync
            results = compare_folders(int_folder, ext_folder, exclude_int_folder, exclude_ext_folder)
            report_folder_differences(int_folder, ext_folder, results)
            print("\nPress ENTER to exit...")
            input()
            break
        elif choice == "2":
            sync_folders(ext_folder, int_folder, results, is_source_folder1=False, delete_files=True,
                         exclude_source_folders=exclude_ext_folder, exclude_dest_folders=exclude_int_folder)
            # Re-run comparison after sync
            results = compare_folders(int_folder, ext_folder, exclude_int_folder, exclude_ext_folder)
            report_folder_differences(int_folder, ext_folder, results)
            print("\nPress ENTER to exit...")
            input()
            break
        elif choice == "3":
            sync_folders(int_folder, ext_folder, results, is_source_folder1=True, delete_files=False,
                         exclude_source_folders=exclude_int_folder, exclude_dest_folders=exclude_ext_folder)
            # Re-run comparison after merge
            results = compare_folders(int_folder, ext_folder, exclude_int_folder, exclude_ext_folder)
            report_folder_differences(int_folder, ext_folder, results)
            print("\nPress ENTER to exit...")
            input()
            break
        elif choice == "4":
            sync_folders(ext_folder, int_folder, results, is_source_folder1=False, delete_files=False,
                         exclude_source_folders=exclude_ext_folder, exclude_dest_folders=exclude_int_folder)
            # Re-run comparison after merge
            results = compare_folders(int_folder, ext_folder, exclude_int_folder, exclude_ext_folder)
            report_folder_differences(int_folder, ext_folder, results)
            print("\nPress ENTER to exit...")
            input()
            break
        else:
            print("\nInvalid choice. Please enter 1, 2, 3, 4, or press ENTER to quit.")

