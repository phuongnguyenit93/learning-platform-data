# Filesystem Permissions

Spring Batch commonly reads data from files and writes results, error files, or reports to the filesystem. A reader may be configured properly and the path may exist, yet the Job still fails if the process running Spring Batch lacks the required access permissions.

**Filesystem permissions** are the rights granted by the operating system to a user, group, or security principal for files and directories. Spring Batch does not bypass these permissions itself. When a reader opens a file, a writer creates a file, or a Job renames output, the operation executes under the OS identity of the process running the application.

To handle this properly, determine:

- Which user or service account the process runs under.
- Whether the file and all parent directories have appropriate permissions.
- Whether a reader needs read permission or a writer needs create, modify, delete, and rename permissions.
- Whether the file resides on a local disk, network share, container volume, or mounted storage.
- Whether permissions remain valid when the Job restarts or runs on another worker.

Do not fix permission errors by granting broad permissions to the entire filesystem. Grant the exact least privilege needed to the right directories and Batch execution identity.

## 1. What are filesystem permissions?

The operating system controls who is allowed to access a filesystem object and which operations they are allowed to perform.

Common objects:

- Input files that readers need to open.
- Directories containing input files.
- Output directories where writers need to create files.
- Staging or temporary directories.
- Directories storing rejected, archive, and log files.
- Lock or marker files created by the Job during processing.

Permissions may allow reading a file while disallowing traversal of a parent directory. Conversely, a process may be able to list a directory yet be denied reading a specific file's contents.

Therefore, checking permissions on the file alone is not enough. Inspect the entire path from the root directory down to the file and all operations the application will perform.

## 2. Read, write, and execute permissions on POSIX

On Linux and Unix-like systems, traditional permissions are represented by three groups:

- Owner: the user owning the object.
- Group: the group owning the object.
- Others: all remaining users.

Each group can have read, write, and execute permissions.

| Permission | On a File | On a Directory |
|---|---|---|
| r — read | Read file contents | List entry names inside the directory |
| w — write | Modify file contents | Create, delete, or rename entries inside the directory |
| x — execute | Execute file if it is an executable | Traverse/search: pass through the directory and access entries by name |

The most easily misunderstood permission is execute on a directory. To open a file by path, a process generally needs search/execute permission on every parent directory of that file.

Example:

~~~text
/data
  |
  +-- batch
        |
        +-- input
              |
              +-- orders.csv
~~~

To read orders.csv, the Batch user needs:

- Traverse permission on /data, /data/batch, and /data/batch/input.
- Read permission on orders.csv.
- Additional permissions if the application needs to list, inspect, or rename files.

To create a new file in input, the process needs write and execute permissions on the input directory. Having write permission on an existing file is not enough to create another file in the same directory.

## 3. Permissions required for each operation

Different Spring Batch operations have different permission requirements.

| Operation | Typically Required Permissions |
|---|---|
| Open input file for reading | Read on the file, traverse on parent directories |
| List files in a directory | Read and execute on the directory |
| Create a new output file | Write and execute on the parent directory |
| Write to an existing output file | Write on the file and traverse along the path |
| Delete a file | Write and execute on the directory containing the file; sticky bit/ACL policies may apply |
| Rename or move a file | Appropriate permissions on both source and destination directories |
| Create a temporary file | Write and execute on the temporary directory |
| Create a lock file | Write and execute on the directory holding locks |
| Read rejected/archive files | Read on the file and traverse on parent directories |

On POSIX, deleting a file is primarily governed by permissions on the directory containing the entry, not solely the file's write permission. This is why a non-writable file can still be deleted or renamed by a user with permissions on its parent directory.

ACLs, sticky bits, mount options, and security policies can add further conditions. When diagnosing, evaluate effective permissions rather than looking at a single mode bit.

## 4. Identifying which identity the process runs under

Filesystem permissions are checked against the identity of the process performing the operation.

In development environments, the application may run under the logged-in user's account. When deployed, the same application may run under:

- A Linux service account.
- A Windows service account.
- A container UID/GID.
- A Kubernetes service workload with a security context.
- An application server or scheduler user.
- A dedicated batch worker account.

For example, a file is created by the deploy user while the Job runs as batch-runner. If the file only allows the owner deploy to read and the group has no access, the reader will receive AccessDeniedException or IOException.

Do not infer runtime identity from the account running an IDE or terminal. Check the actual user of the service, container, or worker.

## 5. Checking permissions on Linux

Useful commands:

~~~bash
id
whoami
ls -ld /data /data/batch /data/batch/input
ls -l /data/batch/input/orders.csv
namei -l /data/batch/input/orders.csv
~~~

These commands reveal:

- Current user and groups.
- Owner/group and mode of each file or directory.
- Traverse permissions on each path component.
- Which component might be blocking access.

Example:

~~~text
drwxr-x--- batch batch /data/batch
drwxr-x--- batch batch /data/batch/input
-rw-r----- batch batch orders.csv
~~~

If the process runs as user batch and belongs to group batch, this setup permits reading the file and traversing directories. A user outside that group would be denied access.

Output from ls does not always show all effective permissions if POSIX ACLs, SELinux, AppArmor, or mount policies are active. Inspect ACLs and security policies accordingly.

## 6. Granting least privilege on Linux

A common management pattern is creating a dedicated group for batch, setting owner/group on data directories, and granting permissions as needed.

Example:

~~~bash
sudo groupadd batch-data
sudo usermod -aG batch-data batch-runner
sudo chown -R batch-runner:batch-data /data/batch
sudo chmod 750 /data/batch
sudo chmod 750 /data/batch/input
sudo chmod 640 /data/batch/input/orders.csv
~~~

Meaning of the example:

- batch-runner is the owner.
- batch-data is the shared group.
- Owner has appropriate read/write/traverse permissions.
- Group has read and traverse permissions.
- Others have no access.

Adjust commands and mode values per actual policy. Do not run recursive chmod or chown across broad directories without confirming exact scope, as doing so can alter permissions on unrelated files.

Do not use chmod 777 as a default fix. It grants broad permissions to every user and can allow modifying or replacing input/output files.

## 7. How umask affects new file permissions

When a process creates a new file or directory, the requested mode is combined with the process's umask. Consequently, an output file may end up with different permissions than what the application passed.

For example, umask 0027 normally strips group write permission and all permissions for others from the requested mode.

~~~bash
umask
~~~

If a writer creates output files that a downstream group needs to read, verify the service's umask and desired default permissions. You can use setgid on the directory or default ACLs so new files inherit the appropriate group/permissions.

Do not assume new files always belong to a specific user's group or match the input file's mode. Check owner, group, and permissions after creating output.

## 8. ACLs and effective permissions

POSIX mode bits are not the only mechanism. Access Control Lists (ACLs) allow granting finer-grained permissions to specific users or groups.

Example:

~~~bash
getfacl /data/batch/input
setfacl -m u:batch-runner:rx /data/batch/input
setfacl -m u:batch-runner:r-- /data/batch/input/orders.csv
~~~

ACLs are useful when you do not want to change the primary owner/group of a directory yet need to grant access to a service account.

When ACLs exist, permissions shown by ls may include a + sign. Check both the ACL and the mask, since the mask caps the effective permissions of ACL entries.

For shared directories, default ACLs can apply to newly created files or subdirectories. Check both current ACLs and default ACLs if output files are created while the Job runs.

## 9. Filesystem permissions on Windows

Windows uses Access Control Lists (ACLs) and security principals to govern access permissions. A file or directory can have permissions inherited from its parent directory alongside explicit entries.

Common permissions:

- Read: read content or metadata.
- Write: create or modify content.
- Modify: read, write, delete, and modify objects within granted scope.
- Read & execute: read and execute files, traverse directories.
- List folder contents: list directory entries.
- Delete: delete objects or entries per ACL.
- Full control: broader administrative rights, including changing permissions and ownership per policy.

ACLs can be inspected with PowerShell:

~~~powershell
Get-Acl 'D:\batch\input\orders.csv' | Format-List
icacls 'D:\batch\input\orders.csv'
icacls 'D:\batch\input'
whoami
~~~

If the application runs as a Windows Service, check the service's Log On As account. The permissions of the user running PowerShell do not prove the service account has the same permissions.

Windows can also access files over network shares. In that case, effective access depends on both share permissions and NTFS permissions; actual access is typically the intersection of both permission layers.

## 10. File paths and working directory

A relative path is resolved against the process's working directory. The working directory when running from an IDE can differ from running as a service, scheduler task, or container.

Example:

~~~java
Resource resource = new FileSystemResource("input/orders.csv");
~~~

This path does not necessarily point to the project directory. If the service starts with a different working directory, the reader may report file not found or open the wrong file.

For operational files, use absolute paths or configure an explicit root directory:

~~~properties
batch.input.directory=/data/batch/input
batch.output.directory=/data/batch/output
~~~

Then resolve paths from the controlled configuration. Avoid relying on the terminal's current location or the directory containing the JAR.

Distinguish "NoSuchFileException" from "AccessDeniedException". A wrong path, a parent directory lacking traverse permission, and a file lacking read permission are distinct root causes.

## 11. Spring Resource does not bypass OS permissions

Spring Resource is an abstraction for accessing resources, for example:

- FileSystemResource: file on the filesystem.
- ClassPathResource: resource on the classpath.
- UrlResource: resource via URL.
- InputStreamResource: stream provided by the application.

Example:

~~~java
Resource input = new FileSystemResource(inputPath);

try (InputStream stream = input.getInputStream()) {
    // Read content.
}
~~~

The Resource abstraction decouples code from a single resource representation, yet grants no extra OS permissions. If the process is not permitted to read a file, FileSystemResource still cannot open it.

ClassPathResource also has different semantics from operational files. Resources packaged inside a JAR are usually not directly writable files. Never use a classpath resource as an output directory.

When creating outputs, use FileSystemResource or Path/Files APIs pointing to a directory granted write permissions.

## 12. Configuring FlatFileItemReader and read permissions

Example reader reading CSV:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .delimited()
            .names("id", "orderNumber", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

For the reader to open the file, the process needs:

- Traverse permission on all parent directories.
- Read permission on the file.
- Access to the mount or volume containing the file.
- The source file to exist at the time the reader opens the resource.

If the reader must list files before selecting inputs, the containing directory also needs appropriate list/read and traverse permissions.

Do not check permissions only at startup. A file's owner or ACL could change, or the file could be rotated or moved before the Step actually opens the resource.

## 13. Configuring FlatFileItemWriter and write permissions

A writer creating output files needs permissions on the destination directory. Example:

~~~java
@Bean
@StepScope
public FlatFileItemWriter<OrderResult> orderWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<OrderResult>()
            .name("orderWriter")
            .resource(new FileSystemResource(outputFile))
            .delimited()
            .names("id", "orderNumber", "status")
            .shouldDeleteIfExists(true)
            .saveState(true)
            .build();
}
~~~

Before using shouldDeleteIfExists(true), ensure output policy allows deleting the old file. If the process lacks permission to delete the file or modify entries in the containing directory, the writer may fail even if it has write access to the file.

Common requirements:

- Parent directory has write and execute permissions to create files.
- Old files may require delete/replace permissions depending on mode.
- If appending, the existing file requires write permission.
- If writing to a temporary file then renaming, appropriate permissions on both source and target directories are needed.
- Downstream users need read permission on the output after the Job completes.

Output filenames must be controlled. Never take arbitrary paths from input data without validation.

## 14. Creating directories before running a Job

A common error is configuring a writer with an output path whose parent directory does not yet exist.

Directories can be created before launch:

~~~java
Path outputDirectory =
        Paths.get(configuredOutputDirectory);

Files.createDirectories(outputDirectory);

if (!Files.isDirectory(outputDirectory)
        || !Files.isWritable(outputDirectory)) {
    throw new IllegalStateException(
            "Output directory is not writable: " + outputDirectory);
}
~~~

Files.createDirectories creates missing parent directories if the process has appropriate permissions.

Files.isWritable is a preliminary check and does not guarantee subsequent writes will succeed. Permissions may change, quotas may run out, mounts may disconnect, or filesystems may remount read-only after the check.

If real write permissions must be verified, perform a test file creation in a dedicated health-check directory and delete that probe file afterward. Never create probe files in business data directories where a Job could misinterpret them.

## 15. Temporary files, staging, and atomic publish

A safe workflow typically writes output to a temporary or staging file and publishes only when the Job completes.

~~~text
Output directory
      |
      +--> report.csv.tmp
              |
              v
        Writer writes chunks
              |
              v
        Job completes successfully
              |
              v
        Rename to report.csv
              |
              v
        Consumer reads report.csv
~~~

Renaming within the same filesystem can usually be performed atomically per filesystem semantics, if the filesystem supports it and permission conditions are met. Java can request an atomic move:

~~~java
Files.move(
        temporaryFile,
        finalFile,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING);
~~~

ATOMIC_MOVE may not be supported across two filesystems or on some network filesystems. When unsupported, the application must explicitly handle the exception and provide an alternative publish strategy. Do not assume moves across two volumes are atomic.

The process generally needs write permission on the destination directory and permission to remove the entry from the source directory. If the final file already exists, replacing it also depends on permissions and policies on the destination entry.

## 16. Permissions for archive and rejected files

Batch Jobs often move input files to an archive or save error records after processing.

Example directories:

~~~text
/data/batch/
    input/
    processing/
    output/
    archive/
    rejected/
    temp/
~~~

Define permissions by role:

| Directory | Batch Process Permissions |
|---|---|
| input | Traverse and read; may need move permission if taking files out of inbox |
| processing | Read/write if the Job moves files here |
| output | Create/write; may need rename/delete |
| archive | Create or move processed files |
| rejected | Create/write error files or reports |
| temp | Create/read/write/delete temporary files |

If another service needs to read outputs or archives, grant group/ACL read access to that service rather than opening permissions to all users.

A shared group or default ACL can give newly created files appropriate permissions for consumers. Check umask and inheritance so new files do not end up too restrictive or overly permissive.

## 17. Filesystem permissions in containers

In containers, the process UID/GID may differ from the host's UID/GID. A host directory mounted into a container retains ownership and permissions as exposed by the filesystem/volume driver.

For example, a container runs as user 10001 while the host directory belongs to owner 1000 with owner-only write permissions. The writer may receive Permission denied.

Points to check:

- Which UID/GID the container process runs under.
- Whether the volume is mounted read-only or read-write.
- Host directory ownership and mode.
- fsGroup or securityContext if using Kubernetes.
- User namespaces or rootless container mappings.
- Host SELinux labels or policies.
- Whether the storage driver supports chmod/chown.

Kubernetes can use securityContext and fsGroup to grant volume access to the appropriate group. Exact behavior depends on volume type and cluster configuration. Do not assume fsGroup fixes every volume type or ACL.

Do not run containers as root merely to bypass permission errors without clear operational justification. Configure UID/GID and volume permissions properly for the application's service account.

## 18. Network shares and mounted filesystems

Files may reside on NFS, SMB, or remotely mounted storage. In that case, access permissions depend on both the server-side filesystem and client configuration.

Common causes:

- NFS export maps UID/GID differently from the client.
- Root squash prevents root inside a container from having expected privileges.
- SMB share permissions and NTFS ACLs conflict.
- Share access credentials or tickets expire.
- Mount is configured read-only.
- Network filesystem disconnects or yields stale handles.
- Locking and rename semantics differ from local filesystems.

For outputs requiring atomic publishing, verify the remote filesystem supports the required semantics. For reader restarts, ensure files are not replaced or altered while the Job is paused.

Test operations under the exact service identity on the exact mount the Job uses. A command run on a developer laptop or a different mount does not prove runtime permissions are correct.

## 19. File permissions on Job restart

A restart can happen after filesystem permissions have changed.

Example:

1. On the first run, the reader opens the file and commits several chunks.
2. The Job fails.
3. An administrator alters the ACL or the file is moved to archive.
4. The Job restarts using the old checkpoint.
5. The reader cannot open the file or cannot seek to the saved position.

Checkpoints only store read state; they do not store access permissions and do not keep file descriptors alive across process restarts.

For reliable restart:

- Keep the input file immutable and at a stable location.
- Maintain read/traverse permissions for the service identity throughout the window when restarts can occur.
- Do not delete or swap files while the Job remains in a restartable state.
- Maintain write permissions on output/staging directories if the writer must resume.
- Validate resource permissions and fingerprint when the Step reopens.

If an input file was moved to archive after a Job failed, clearly define whether restarts should read from the archive path or restore the file to its original location. Do not let another workflow move files while a Job is running or awaiting restart.

## 20. Do not rely solely on Files.isReadable and isWritable

Java NIO provides:

~~~java
Files.isReadable(path);
Files.isWritable(path);
Files.isExecutable(path);
~~~

These methods are useful for preliminary checks but have limitations:

- They do not prove the subsequent operation will succeed.
- Permissions can change between the check and the actual open/write.
- ACLs, mounts, quotas, or network state can interfere.
- Some filesystems do not expose complete permission metadata.
- isWritable on a file does not prove the parent directory allows creating new files.

This is a time-of-check to time-of-use (TOCTOU) issue: checked state can change before the real operation runs.

Treat the actual open, create, or write operation as the definitive result. Catch and classify IOException, AccessDeniedException, or FileSystemException with the corresponding path and operation.

## 21. Protecting paths against path traversal

If filenames come from JobParameters or external data, never concatenate arbitrary strings directly onto a root directory.

Unsafe input example:

~~~java
Path target = outputRoot.resolve(requestedFileName);
~~~

If requestedFileName contains ../ or an absolute path, target can escape outputRoot.

Normalize and verify:

~~~java
Path root = outputRoot.toAbsolutePath().normalize();
Path target = root.resolve(requestedFileName).normalize();

if (!target.startsWith(root)) {
    throw new IllegalArgumentException(
            "Output path is outside the allowed directory");
}
~~~

This check blocks traversal along normalized paths. If the environment permits untrusted symlinks, also check real paths, permissions on symlinks/targets, and the possibility of symlink swapping between validation and file opening.

Prefer accepting a logical file ID or whitelisted name rather than letting callers pass arbitrary paths. Allow Jobs to write only inside configured directories.

## 22. Symlinks and replaced files

Symlinks can make a path inside an allowed directory point to a file elsewhere. Effective permissions also depend on the target and the directories leading to the target.

In environments processing untrusted files:

- Do not follow symlinks outside scope unless business rules allow it.
- Validate file type and target per policy.
- Restrict permission to create symlinks inside staging directories.
- Use service-owned directories and disallow untrusted users from modifying entries.
- Beware race conditions between path validation and file opening.

Java NIO provides options like LinkOption.NOFOLLOW_LINKS for certain operations. They do not solve every race condition on their own, but can help reject symlinks in appropriate validation steps.

Do not open files based on paths supplied by untrusted users if the process has broader access rights than that user.

## 23. Lock file permissions and running multiple Jobs

Some applications use lock files to prevent two Jobs from processing the same input. When creating or deleting lock files, the process needs appropriate permissions on the directory containing locks.

Example:

~~~text
processing/
    orders.csv
    orders.csv.lock
~~~

If batch-runner has read permission on input yet lacks write permission on the processing directory, the Job can read the file but cannot create the lock.

Also determine which user creates lock files and whether a restarted process can delete them. If leftover lock files remain, a procedure is needed to check owner, age, and Job status before removing them.

Filesystem locks are not always reliable on every network filesystem. If multiple nodes run Jobs, distributed locks or storage-backed atomic file claims may be needed.

## 24. Diagnosing permission errors in Spring Batch

Common exceptions:

- AccessDeniedException: operation denied due to permissions.
- FileSystemException: general filesystem error, potentially with a reason message.
- NoSuchFileException: file or a path component does not exist.
- FileNotFoundException: file not found or cannot be opened; on some platforms the error message may not distinguish the exact cause.
- IOException: general I/O error.

When logging errors, record:

- Job name and JobExecution ID.
- Step name and StepExecution ID.
- Partition name if applicable.
- Operation: open, read, create, write, delete, or move.
- Normalized path, if it contains no sensitive data.
- Process user/UID or service identity.
- Exception class and root cause.

Do not log sensitive file contents or full JobParameters if they contain credentials. Log only what is needed to identify the file and failing operation.

## 25. Verifying permissions from the Batch process itself

A test run under a developer user does not represent service permissions.

Create a health check or startup validation in the application to verify configured directories:

~~~java
public void validateDirectory(Path directory) throws IOException {
    Files.createDirectories(directory);

    if (!Files.isDirectory(directory)) {
        throw new IllegalStateException(
                "Not a directory: " + directory);
    }

    Path probe = Files.createTempFile(
            directory,
            ".batch-permission-check-",
            ".tmp");

    try {
        Files.writeString(
                probe,
                "permission check",
                StandardOpenOption.TRUNCATE_EXISTING);
    } finally {
        Files.deleteIfExists(probe);
    }
}
~~~

This example tests creating, writing, and deleting a temporary file under the current process identity. Run this only in a health-check directory dedicated to the application, not in an input directory where consumers could misinterpret it.

For input files, opening a stream can be tested in a resource-check step. However, avoid opening the same file in a way that interferes with the reader, locks, or read position. Real checks should reside in a preparation step before the Step begins.

## 26. Least privilege and directory separation

An easy-to-operate design separates directories by purpose and grants distinct permissions.

~~~text
/data/customer-batch/
    inbox/       # source delivers input files
    processing/  # files claimed by Job
    output/      # successful results
    rejected/    # error reports or invalid data
    archive/     # processed inputs
    temp/        # temporary and staging files
~~~

Example policy:

| Actor | Inbox | Processing | Output | Archive | Rejected |
|---|---|---|---|---|---|
| File producer | Create/write | Not needed | Not needed | Not needed | Not needed |
| Batch runner | Read/move | Read/write | Create/write | Create/move | Create/write |
| Downstream consumer | Not needed | Not needed | Read | As needed | Read per policy |
| Operator | Read per policy | Inspect | Read | Read | Read |

This separation reduces the chance of a producer overwriting outputs or a consumer deleting in-flight inputs. Actual permissions should be enforced via owner/group/ACL and tested under the exact service identity.

## 27. Common Pitfalls

### File exists yet the reader still cannot open it

The process may lack read permission on the file or execute/traverse permission on a parent directory. Inspect the entire path and runtime user.

### Having read permission on the file yet unable to traverse the directory

On POSIX, missing execute on a parent directory blocks path access. Grant appropriate search/traverse permissions.

### Writer reports permission denied even though the file does not exist yet

Creating a file requires write and execute on the parent directory. Write permission on another file in the directory is not enough.

### Succeeding in IDE yet failing as a Windows/Linux service

The service runs under a different identity. Check Log On As or the actual process UID/GID.

### Container has root yet volume remains unwritable

The volume may be mounted read-only, UID mappings may differ, ACL/SELinux may block access, or the storage driver enforces its own policy.

### Output file has overly broad or overly narrow permissions

Check umask, default ACLs, group inheritance, and required consumer permissions. Never grant 777 to bypass ownership issues.

### File is locked or cannot be renamed

Another process may hold the file open, share mode may disallow delete/rename, or a remote filesystem has different semantics. Identify owner and file lifecycle.

### Job restart cannot reopen input

The file was moved, deleted, replaced, or its ACL changed. Keep sources immutable and permissions intact during the restart window.

### Files.isWritable returns true yet writer still fails

Permissions may have changed, quota exhausted, mount became read-only, or the directory differs from the actual path. Attempt the real operation and log the root cause.

### Using paths from input data without validation

Path traversal or symlinks can cause the Job to read/write outside allowed directories. Normalize, restrict to root, and control symlinks.

## 28. Process for granting and verifying filesystem permissions

Before deploying a Job that reads/writes files, determine:

1. Which user, group, or service account does the process run as?
2. Does the input file exist and remain immutable throughout the restart lifecycle?
3. Do all parent directories have appropriate traverse permissions?
4. Does the reader have read permission on the file?
5. Does the writer have create/write permissions on the output directory?
6. Does the Job need to delete, replace, rename, or move files?
7. What owner, group, mode, and ACL will new files receive?
8. Does the volume have read-only mounts, UID mappings, or network policies?
9. Do temp, rejected, archive, and lock directories have appropriate permissions?
10. Are paths confined to allowed directories and protected against traversal?
11. Does the health check run under the exact process identity?
12. Can a Job restart still access the right file and checkpoint?

Filesystem permissions are part of Job operational configuration. Readers need file read and path traverse permissions; writers need permissions to create or modify entries in target directories; archive, delete, and atomic publish operations require corresponding permissions on the involved directories. By granting least privilege to the right service identity, keeping sources stable across restarts, and testing operations under the real runtime, Spring Batch can read and write resources safely and diagnosably.
