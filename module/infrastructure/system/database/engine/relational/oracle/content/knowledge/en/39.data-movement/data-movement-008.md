# Parallel, Compression, Encryption, and Usage Prerequisites in Oracle Data Pump

Oracle Data Pump Export and Import (expdp/impdp) are commonly used for logical backups, schema transfers, database migrations, or upgrade preparation. For large datasets, three parameter groups directly impact runtime, storage size, and dump file security:

- **PARALLEL:** controls how many workers/processes run concurrently for a Data Pump job.
- **COMPRESSION:** determines whether metadata and/or table data are compressed during export; COMPRESSION_ALGORITHM selects the compression algorithm.
- **ENCRYPTION:** encrypts dump file contents; ENCRYPTION_MODE decides whether to use a password, wallet/keystore, or both.

These parameters are not always usable on every edition or under every license. A configuration that technically executes does not prove the organization is licensed to use that feature. Before scheduling export/import, confirm edition, option licenses, COMPATIBLE, storage capacity, CPU, memory, I/O, wallets, and dump file transfer methods.

This lesson uses Oracle Database 19c as the baseline. It explains parallelism mechanics, compression choices, encryption modes, usage prerequisites, expdp/impdp examples, performance measurement, and a pre-migration checklist.

## 1. Role of Data Pump in Data Movement

### 1.1. Export creates a dump file set

Data Pump Export uses the expdp command to read data and metadata from the database and write them to one or more dump files. A dump file set uses an Oracle-proprietary binary format that can contain:
- Table data.
- Schema/object metadata.
- Control information required for Import.

Dump files are written by the database server to the location declared via a DIRECTORY object. The expdp client does not write dump files locally on the client machine if DIRECTORY points to a different server path.

### 1.2. Import loads dump files or reads directly from a source database

Data Pump Import uses impdp to load a dump file set into the target database. Besides importing from files, NETWORK_LINK can read data directly from a source database over a database link.

Import can filter or transform metadata/data using parameters such as:
- SCHEMAS, TABLES, FULL, TABLESPACES.
- INCLUDE, EXCLUDE, CONTENT, QUERY.
- REMAP_SCHEMA, REMAP_TABLESPACE, REMAP_TABLE, TRANSFORM.
- TABLE_EXISTS_ACTION.

PARALLEL, COMPRESSION, and ENCRYPTION do not replace data-scoping parameters. They control how the job processes data, dump file size, and dump file protection.

### 1.3. Phases to distinguish

~~~text
Source database
     |
     | expdp
     v
Read metadata and table data
     |
     | PARALLEL: distribute work to workers
     | COMPRESSION: compress dump content
     | ENCRYPTION: encrypt dump files
     v
Dump file set + log file
     |
     | securely transfer files to target
     v
Dump file set at target environment
     |
     | impdp
     v
Read/decrypt/decompress, create objects, load data
     |
     v
Target database + validation
~~~

Parallelism, compression, and encryption can all participate in a single export job. They increase or decrease different resource demands, so test them together rather than tuning each parameter in isolation.

## 2. Checking Usage Prerequisites Before Configuration

### 2.1. Identify the edition

Data Pump parallel export/import is an Enterprise Edition feature. In Standard Edition 2, Data Pump PARALLEL is restricted to degree 1; it cannot run multiple concurrent workers.

You can check database details:

~~~sql
SELECT banner
FROM   v$version
ORDER  BY banner;
~~~

Or inspect edition in views appropriate for your environment's administrative privileges. Do not infer edition solely from an Oracle home name or because the parser accepts a parameter.

### 2.2. Check COMPATIBLE

Some compression/encryption options require a minimum COMPATIBLE level. Check:

~~~sql
SHOW PARAMETER compatible;
~~~

In Oracle 19c, COMPRESSION_ALGORITHM and several ENCRYPTION options require COMPATIBLE at levels specified by the 19c documentation, often 11.0.0 or 12.0.0 depending on the parameter. Check the exact parameter rather than applying a single threshold across all options.

### 2.3. Confirm per-feature licensing

Key prerequisites in Oracle Database 19c:

| Feature | Edition/option requirement to verify | Notes |
| --- | --- | --- |
| Data Pump PARALLEL | Enterprise Edition | Standard Edition 2 restricts PARALLEL = 1 |
| COMPRESSION=METADATA_ONLY | Does not require Advanced Compression | This is the Data Pump Export default |
| COMPRESSION=ALL or DATA_ONLY | Enterprise Edition and Oracle Advanced Compression | Compresses table data inside the dump |
| COMPRESSION_ALGORITHM | Oracle Advanced Compression; required COMPATIBLE | Applies to dump compression algorithms |
| Data Pump dump-file encryption | Enterprise Edition and Oracle Advanced Security per 19c licensing/reference | Must verify contractual entitlement |
| AES128/AES192/AES256 | Algorithms; do not grant entitlement to encryption feature | Must pair with appropriate encryption parameters |

Oracle Advanced Compression and Oracle Advanced Security are separately licensed options in many Enterprise Edition deployment models. Certain cloud/engineered offerings may include option entitlements; verify the exact offering and contract for both source and target systems.

Do not use V$OPTION, the fact that a parameter executes successfully, or a past export as proof of licensing. Check the Licensing Information User Manual and your organization's entitlements before enabling features.

### 2.4. Distinguish licensing from technical prerequisites

A feature may be:
- Present in the binaries yet unlicensed for the system.
- Licensed yet missing wallet, directory, or storage configuration.
- Permitted on the source yet the target has a different edition/option.
- Able to create a dump file yet import cannot decrypt it or lacks the corresponding option.

Therefore, preflight checks must verify both entitlements and technical prerequisites on both ends.

## 3. PARALLEL — Controlling Data Pump Workers

### 3.1. What does PARALLEL do?

PARALLEL sets the maximum number of concurrently executing processes for a Data Pump job. Data Pump has a control process coordinating work and workers performing metadata unload/load, table data, indexes, or eligible tasks.

Example:

~~~text
Data Pump control process
       |
       +---- Worker 1
       +---- Worker 2
       +---- Worker 3
       +---- Worker 4
~~~

If the job has sufficient independent tasks, multiple workers can process objects or partitions simultaneously. If work has sequential dependencies or only one object cannot be subdivided suitably, raising PARALLEL may not speed up the job.

### 3.2. Basic syntax

Export:

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_%U.dmp \
  LOGFILE=app_export.log \
  SCHEMAS=APP \
  PARALLEL=4
~~~

Import:

~~~bash
impdp app_user@target_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_%U.dmp \
  LOGFILE=app_import.log \
  SCHEMAS=APP \
  PARALLEL=4
~~~

The examples use backslashes to illustrate Unix shell syntax. On Windows or when using a parameter file, line continuation differs. DIRECTORY is an Oracle DIRECTORY object, not an arbitrary path on the client machine.

### 3.3. Default PARALLEL and edition

Default PARALLEL is 1. Running multiple workers requires the proper edition and licensing. Oracle 19c specifies PARALLEL multi-worker execution applies only to Enterprise Edition; Standard Edition is capped at 1.

Do not set PARALLEL=8 on Standard Edition expecting eight workers. Check edition before estimating migration timelines.

### 3.4. Choosing an initial degree

An empirical starting point may be 2, 4, or 8 workers depending on:
- Actual allocated CPUs/vCPUs.
- CPU headroom reserved for applications.
- Datafile read speed.
- Dump file write speed.
- PGA and total memory capacity.
- Number of independent tables/partitions.
- Ability to spread dump files across storage.

Oracle recommends not setting PARALLEL much higher than roughly twice the CPU count for maximum throughput in Data Pump performance guidelines. This is a tuning heuristic, not an optimal guarantee. In production, a lower degree may be appropriate to protect application workloads.

### 3.5. Increasing PARALLEL does not mean linear speedup

When adding workers:
- CPU usage increases.
- PGA/memory consumption increases.
- Datafile and dumpfile I/O increases.
- Storage queues can grow.
- Multiple workers may contend on the same file or segment.
- Metadata operations with dependencies still run sequentially.

For example, PARALLEL=8 does not guarantee a job finishes eight times faster than PARALLEL=1. If storage is already saturated, adding workers may simply increase latency.

### 3.6. Provide enough dump files for workers

Each worker writes or reads one dump file at a time. To leverage parallelism, supply enough files or use a substitution variable like %U:

~~~bash
DUMPFILE=app_%U.dmp
PARALLEL=4
FILESIZE=20G
~~~

%U allows Data Pump to generate sequentially numbered filenames. FILESIZE caps each dump file's size; when a file fills, Data Pump moves to the next file per file set configuration.

If only a single static filename is specified without an appropriate pattern, workers may be constrained by available files or fail to utilize parallel I/O as expected.

### 3.7. Spreading files across storage

If multiple suitable volumes exist, you can declare multiple DIRECTORY objects or dump files across different locations to distribute I/O. Effectiveness depends on storage architecture:
- Multiple paths on the same logical volume do not necessarily add bandwidth.
- Dump files on the same device as datafiles can cause read/write contention.
- Striped storage may already distribute I/O effectively.
- In RAC, dump file locations must be accessible from nodes running workers.

Measure throughput and latency of each volume before deciding to spread files.

### 3.8. Parallelism limits by task type

Not every part of Data Pump runs in parallel:
- Transportable tablespace exports differ in how data is unloaded.
- Metadata import has dependencies and some objects must be created sequentially.
- Metadata import over NETWORK_LINK has parallelism limitations.
- Transportable tablespace metadata is not imported in parallel per documented restrictions.
- Certain object types such as triggers, views, sequences, constraints, object grants, and referential constraints may not be processed in parallel in some import paths.

Thus, PARALLEL is a job maximum, not a guarantee that every object gets its own worker.

### 3.9. PARALLEL in RAC

In RAC, Data Pump can utilize resources across multiple instances if configuration allows. The default CLUSTER setting may permit workers to run on other nodes. You can restrict a job to the initiating instance using:

~~~bash
CLUSTER=NO
~~~

Or use SERVICE_NAME together with CLUSTER to bind workers to instances hosting the appropriate service.

When using RAC, verify:
- Whether the DIRECTORY path is available on all nodes.
- Whether dump files reside on appropriate shared filesystem/ASM/object storage.
- Which services and instances are permitted to run workers.
- Which node's CPU/storage is carrying load.
- Whether CLUSTER=NO is appropriate for small jobs to avoid distribution overhead.

### 3.10. Changing PARALLEL while a job is running

You can attach to a running job:

~~~bash
expdp app_user@source_db ATTACH=APP_EXPORT_JOB
~~~

In interactive mode:

~~~text
Export> STATUS
Export> PARALLEL=2
Export> STATUS
Export> PARALLEL=6
~~~

Increasing workers helps only if enough files, resources, and parallelizable work remain. When decreasing, workers currently executing a task may finish their current unit of work before going idle.

Do not kill a job merely to change its degree. Use ATTACH/interactive commands and understand the differences among STOP_JOB, KILL_JOB, EXIT_CLIENT, and CONTINUE_CLIENT.

## 4. Monitoring and Measuring Parallel Performance

### 4.1. Displaying progress

You can instruct Data Pump to log timestamps and metrics:

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_%U.dmp \
  LOGFILE=app_export.log \
  SCHEMAS=APP \
  PARALLEL=4 \
  LOGTIME=ALL \
  METRICS=YES \
  STATUS=60
~~~

LOGTIME=ALL adds timestamps to messages; METRICS=YES adds object/elapsed information to the log; STATUS sets the client status display interval.

### 4.2. Monitoring Data Pump jobs

~~~sql
SELECT owner_name,
       job_name,
       operation,
       job_mode,
       state,
       degree,
       attached_sessions,
       datapump_sessions
FROM   dba_datapump_jobs
ORDER  BY owner_name, job_name;
~~~

DBA_DATAPUMP_JOBS shows existing Data Pump jobs and their states. View/column availability can vary by privileges; use DESC if needed.

### 4.3. Viewing sessions attached to a job

~~~sql
SELECT owner_name,
       job_name,
       instance_id,
       session_type,
       saddr
FROM   dba_datapump_sessions
ORDER  BY owner_name, job_name, session_type;
~~~

Combine this information with V$SESSION to identify worker and control sessions. In RAC, pay attention to INST_ID/INSTANCE_ID so sessions across nodes are not confused.

### 4.4. Monitoring long operations

~~~sql
SELECT sid,
       serial#,
       opname,
       target,
       sofar,
       totalwork,
       units,
       elapsed_seconds,
       time_remaining
FROM   v$session_longops
WHERE  totalwork > 0
AND    sofar < totalwork
ORDER  BY elapsed_seconds DESC;
~~~

Not every Data Pump operation appears as a complete longops row. Use logs and job status alongside this view.

### 4.5. Comparing parallel levels

To find the right degree, run tests on representative data:

| Run | PARALLEL | Elapsed | CPU | Read/write throughput | Dump size |
| --- | ---: | --- | --- | --- | --- |
| A | 1 | Measure | Measure | Measure | Measure |
| B | 2 | Measure | Measure | Measure | Measure |
| C | 4 | Measure | Measure | Measure | Measure |
| D | 8 | Measure | Measure | Measure | Measure |

Keep data, mode, dump storage, compression, encryption, and background load constant when comparing. Changing multiple parameters at once makes it hard to isolate what improved or degraded performance.

## 5. COMPRESSION — Compressing Dump Files During Export

### 5.1. How does COMPRESSION differ from table compression?

Data Pump COMPRESSION compresses content written into the dump file set. It aims to reduce file size and potentially reduce bytes transferred over the network.

It does not alter table compression settings inside the target database. Features such as Basic Table Compression, Advanced Row Compression, SecureFiles compression, and RMAN backup compression are separate features with distinct conditions and licensing.

### 5.2. COMPRESSION values

~~~text
COMPRESSION = ALL
COMPRESSION = DATA_ONLY
COMPRESSION = METADATA_ONLY
COMPRESSION = NONE
~~~

| Value | Compressed content | Meaning |
| --- | --- | --- |
| ALL | Metadata and table data | Compresses all export content |
| DATA_ONLY | Table data | Metadata is not compressed by this option |
| METADATA_ONLY | Metadata | Default value |
| NONE | Uncompressed | Dump files do not use Data Pump compression |

Data Pump Export's default is METADATA_ONLY. Metadata compression can be used without the Oracle Advanced Compression option. Compressing table data with ALL or DATA_ONLY requires Enterprise Edition and Oracle Advanced Compression per 19c documentation.

### 5.3. Metadata compression example

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_meta_%U.dmp \
  LOGFILE=app_meta.log \
  SCHEMAS=APP \
  COMPRESSION=METADATA_ONLY
~~~

This is the default if COMPRESSION is omitted. It compresses metadata in the dump file, without applying Data Pump compression to table data.

### 5.4. Data and metadata compression example

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_all_%U.dmp \
  LOGFILE=app_all.log \
  SCHEMAS=APP \
  COMPRESSION=ALL \
  COMPRESSION_ALGORITHM=BASIC
~~~

COMPRESSION=ALL requires the Oracle Advanced Compression option and Enterprise Edition. Confirm licensing before running in licensed environments.

### 5.5. Data-only compression example

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_data_%U.dmp \
  LOGFILE=app_data.log \
  SCHEMAS=APP \
  COMPRESSION=DATA_ONLY \
  COMPRESSION_ALGORITHM=LOW
~~~

Metadata is not compressed with DATA_ONLY. Depending on migration goals, compressing data can reduce transfer volume, but source CPU overhead must be weighed.

### 5.6. COMPRESSION_ALGORITHM

Oracle Data Pump 19c supports:

| Algorithm | Characteristics | When to consider |
| --- | --- | --- |
| BASIC | Balances compression ratio and speed; matches legacy behavior | When a standard default is desired |
| LOW | Minimal impact on export throughput, uses less CPU | When CPU is the constrained resource |
| MEDIUM | Balances ratio and speed; Oracle recommends testing for general workloads | When a balanced trade-off is needed |
| HIGH | Usually achieves higher compression ratio at higher CPU cost | When network is slow or transfer size is constrained |

Actual compression ratios depend on the data. Repetitive text compresses well; already-compressed, encrypted, or binary data may shrink very little.

### 5.7. Algorithm syntax and prerequisites

~~~bash
COMPRESSION=DATA_ONLY
COMPRESSION_ALGORITHM=MEDIUM
~~~

COMPRESSION_ALGORITHM accepts BASIC, LOW, MEDIUM, or HIGH. In Oracle 19c, this algorithm feature requires COMPATIBLE at the documented level and the Oracle Advanced Compression option.

Do not confuse:
- COMPRESSION selects compression scope.
- COMPRESSION_ALGORITHM selects the compression method.
- COMPRESS in table DDL is a different storage attribute.
- RMAN COMPRESS is a different backup feature.

### 5.8. Performance impact

Dump compression can:
- Reduce bytes written to storage.
- Reduce file size and network transfer time.
- Reduce I/O if storage/network is the bottleneck.
- Increase CPU usage to compress during export and decompress during import.
- Increase duration if CPU is already saturated or data is incompressible.

When CPU is the bottleneck, LOW may outperform HIGH. When network is the bottleneck, HIGH can reduce transferred bytes, though CPU must be benchmarked. MEDIUM is a starting point to test, not a universally optimal setting.

### 5.9. Importing compressed dumps

impdp automatically handles dump files compressed by Data Pump. According to Oracle Data Pump Best Practices, importing a compressed dump file does not require an Advanced Compression license solely to decompress the file. Licensing applies to the export operation and the data compression feature used.

### 5.10. Incompressible data

If data is already compressed at the application layer or has high entropy, adding compression can:
- Waste CPU.
- Yield negligible size reduction.
- Slow down the job.
- Produce multiple files with almost unchanged total size.

Measure actual dump sizes before choosing a compression level for large migrations.

## 6. ENCRYPTION — Encrypting Dump Files

### 6.1. Why encrypt dumps?

Dump files can contain all sensitive data from a schema or database. When dumps are written to staging folders, backup staging, or transferred over a network, filesystem permissions alone may not suffice.

Data Pump encryption encrypts the contents of the dump file set so anyone lacking the key/password cannot read the data simply by opening the file.

Dump file encryption differs from:
- TDE encrypting datafiles/tablespaces/columns inside the database.
- TLS/native network encryption protecting data in transit.
- Filesystem/object storage encryption protecting storage media.

A secure migration architecture may require combining multiple layers.

### 6.2. ENCRYPTION levels

~~~text
ENCRYPTION = ALL
ENCRYPTION = DATA_ONLY
ENCRYPTION = METADATA_ONLY
ENCRYPTION = ENCRYPTED_COLUMNS_ONLY
ENCRYPTION = NONE
~~~

| Value | Encrypted portion of the dump |
| --- | --- |
| ALL | All data and metadata |
| DATA_ONLY | Table data |
| METADATA_ONLY | Metadata |
| ENCRYPTED_COLUMNS_ONLY | Data of columns already TDE-encrypted under supported conditions |
| NONE | Unencrypted dump |

If only ENCRYPTION_PASSWORD is supplied without specifying ENCRYPTION, Oracle Data Pump 19c defaults to ENCRYPTION=ALL. To avoid ambiguity, specify the encryption scope explicitly.

### 6.3. SecureFiles and encryption

If an export includes SecureFiles and you must ensure they are encrypted inside the dump, Oracle requires ENCRYPTION=ALL to encrypt the entire dump file set. Do not assume ENCRYPTED_COLUMNS_ONLY protects all LOB/SecureFiles data.

### 6.4. ENCRYPTION_MODE

Oracle Data Pump supports three modes:

| Mode | Mechanism | When to use |
| --- | --- | --- |
| PASSWORD | Operator-supplied password encrypts/decrypts the dump | Moving files to another database/environment |
| TRANSPARENT | Uses Oracle encryption wallet/keystore | Importing within an environment sharing managed keys/wallet |
| DUAL | Allows decryption using either wallet or password | Need local wallet import plus offsite password recovery capability |

Specify the mode explicitly to avoid relying on defaults tied to whether a wallet is open or closed.

### 6.5. PASSWORD mode

Export example:

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_secure_%U.dmp \
  LOGFILE=app_secure.log \
  SCHEMAS=APP \
  ENCRYPTION=ALL \
  ENCRYPTION_MODE=PASSWORD \
  ENCRYPTION_PASSWORD \
  ENCRYPTION_PWD_PROMPT=YES
~~~

How the password is entered depends on the client and syntax; with the command-line client, ENCRYPTION_PWD_PROMPT=YES tells Data Pump to prompt for the password without echoing it to the screen.

When importing, supply the same password:

~~~bash
impdp app_user@target_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_secure_%U.dmp \
  LOGFILE=app_secure_import.log \
  SCHEMAS=APP \
  ENCRYPTION_PWD_PROMPT=YES
~~~

In some versions/syntaxes, ENCRYPTION_PASSWORD can be supplied directly. Never put plaintext passwords into parameter files committed to source control, shared scripts, or shell history.

### 6.6. TRANSPARENT mode

Transparent mode relies on a configured and available Oracle encryption wallet/keystore. Example:

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_transparent_%U.dmp \
  LOGFILE=app_transparent.log \
  SCHEMAS=APP \
  ENCRYPTION=ALL \
  ENCRYPTION_MODE=TRANSPARENT
~~~

Do not use ENCRYPTION_PASSWORD with TRANSPARENT mode; Oracle raises an error if password parameters are provided in this mode.

When importing, the wallet/keystore containing the matching key must be available in the target environment. If the file is moved to another host/database without the corresponding key, import cannot decrypt it.

### 6.7. DUAL mode

DUAL creates a dump that can be decrypted with either the wallet or the declared password:

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_dual_%U.dmp \
  LOGFILE=app_dual.log \
  SCHEMAS=APP \
  ENCRYPTION=ALL \
  ENCRYPTION_MODE=DUAL \
  ENCRYPTION_PASSWORD \
  ENCRYPTION_PWD_PROMPT=YES \
  ENCRYPTION_ALGORITHM=AES256
~~~

This mode is helpful when local imports can use the wallet while offsite imports require password capability. DUAL requires both the key/wallet mechanism and the password per Oracle configuration.

### 6.8. ENCRYPTION_ALGORITHM

Oracle Database 19c supports:
- AES128.
- AES192.
- AES256.

The default is AES128. The Oracle Advanced Security Guide recommends AES256 for Data Pump exports in 19c.

Example:

~~~bash
ENCRYPTION=ALL
ENCRYPTION_MODE=PASSWORD
ENCRYPTION_ALGORITHM=AES256
ENCRYPTION_PASSWORD
ENCRYPTION_PWD_PROMPT=YES
~~~

ENCRYPTION_ALGORITHM must be paired with ENCRYPTION or ENCRYPTION_PASSWORD. Do not use it with ENCRYPTED_COLUMNS_ONLY because those columns already have their own encryption format.

### 6.9. ENCRYPTED_COLUMNS_ONLY

This option is for columns already encrypted with TDE; it does not encrypt the entire dump file. Per Oracle rules:
- TDE is required for the relevant columns.
- ENCRYPTION_PASSWORD is required.
- Do not use ENCRYPTION_MODE.
- Do not use ENCRYPTION_ALGORITHM to apply an extra algorithm layer to already-encrypted columns.

If you need to protect the entire dump contents, use ENCRYPTION=ALL.

### 6.10. Importing encrypted dumps

Import must match the mechanism used during export:
- PASSWORD: supply the exact password used during export.
- TRANSPARENT: the appropriate wallet/keystore must be available.
- DUAL: either the wallet or password can be used depending on how the dump was created.

If the dump contains encrypted columns, column encryption attributes on source and target must be compatible. Import can fail if encrypted column definitions differ.

### 6.11. Protecting passwords and wallets

- Use interactive prompts instead of plaintext command-line passwords whenever possible.
- Never commit passwords to PARFILEs, shell scripts, or source control.
- Transmit passwords via a secure channel separate from dump files.
- Manage wallet/keystore backups, access controls, and rotation.
- Never place dump files and wallet files together in the same broadly accessible directory.
- Never send passwords in the same email/chat containing dump file links.
- Destroy staging copies according to retention and secure deletion procedures.

## 7. Detailed Licensing and Compatibility Requirements

### 7.1. Parallel Data Pump

Oracle Database 19c Licensing Information lists Parallel Data Pump Export/Import as an Enterprise Edition feature. In Standard Edition 2, PARALLEL is limited to 1.

If source and target run different editions, verify both sides. For example, exporting from EE and importing into SE2 may require adjusting jobs/objects; do not leave PARALLEL high expecting SE2 to utilize it.

### 7.2. Data Pump compression

The Oracle Advanced Compression option includes Data Pump Export Data Compression. Per documentation:
- COMPRESSION=METADATA_ONLY does not require Advanced Compression.
- COMPRESSION=ALL or DATA_ONLY requires Advanced Compression and Enterprise Edition.
- COMPRESSION_ALGORITHM requires Advanced Compression and an appropriate COMPATIBLE setting.
- Importing an already-compressed dump file does not require the option solely to decompress the dump.

Advanced Compression is a separate option for many EE deployments, though it may be included in certain cloud/engineered offerings. Check the permitted features table and contract for your exact deployment.

### 7.3. Data Pump encryption

Oracle Database 19c Licensing Information lists Data Pump Export File encryption under Oracle Advanced Security. Encryption parameters in Data Pump documentation also carry edition limits and option usage prerequisites. TDE/Transparent mode further requires a wallet/keystore and keys.

Distinguish:
- Edition prerequisites for Data Pump features.
- Entitlement to use Oracle Advanced Security.
- Technical prerequisites for wallets/TDE.
- Import capability on the target database.

Do not assume PASSWORD mode, TRANSPARENT mode, or DUAL mode is license-exempt simply because they manage keys differently. Check current Licensing Information for your offering.

### 7.4. Cloud services with different entitlements

Some Oracle Cloud Database offerings include options that on-premises customers must purchase separately. The 19c licensing tables have columns for BaseDB, ExaDB, and other offerings. Check the exact service type, BYOL vs. license-included, and running RU.

### 7.5. Pre-run verification matrix

| Question | Verification source |
| --- | --- |
| Is the database EE or SE2? | V$VERSION, contract/edition records |
| Is PARALLEL permitted? | Oracle Licensing Information |
| Is data compression licensed? | Oracle Advanced Compression entitlement |
| Is dump encryption licensed? | Oracle Advanced Security entitlement |
| Is COMPATIBLE high enough? | SHOW PARAMETER compatible |
| Is wallet/keystore ready? | TDE/keystore configuration |
| Can target decrypt the dump? | Verify wallet/password and test import |
| Enough space for dump files? | Filesystem/object storage capacity |
| Enough files for workers? | DUMPFILE pattern and file count |
| Are resources sufficient? | CPU, PGA, I/O, and workload baseline |

## 8. Combining PARALLEL, COMPRESSION, and ENCRYPTION

### 8.1. A balanced configuration

Example exporting a schema with 4 workers, compressing the whole dump with MEDIUM, and encrypting with a password:

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_migration_%U.dmp \
  FILESIZE=20G \
  LOGFILE=app_migration.log \
  SCHEMAS=APP \
  PARALLEL=4 \
  COMPRESSION=ALL \
  COMPRESSION_ALGORITHM=MEDIUM \
  ENCRYPTION=ALL \
  ENCRYPTION_MODE=PASSWORD \
  ENCRYPTION_ALGORITHM=AES256 \
  ENCRYPTION_PWD_PROMPT=YES \
  LOGTIME=ALL \
  METRICS=YES \
  STATUS=60
~~~

This configuration requires:
- Enterprise Edition.
- Oracle Advanced Compression for data compression.
- Oracle Advanced Security for dump encryption per licensing.
- Appropriate COMPATIBLE setting.
- Sufficient DIRECTORY object and dump storage capacity.
- Password entered via prompt and protected separately.

This is an illustrative configuration, not a recommended PARALLEL or compression setting for every database.

### 8.2. Corresponding import

~~~bash
impdp app_user@target_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_migration_%U.dmp \
  LOGFILE=app_import.log \
  SCHEMAS=APP \
  PARALLEL=4 \
  ENCRYPTION_PWD_PROMPT=YES \
  LOGTIME=ALL \
  METRICS=YES \
  STATUS=60
~~~

Import reads, decrypts, and decompresses using metadata inside the dump file. You do not need to re-specify COMPRESSION_ALGORITHM to decompress the dump. The password must match if export used PASSWORD mode.

If TRANSPARENT mode was used, the matching wallet/keystore is required and no password is supplied. If DUAL was used, choose wallet or password per the designed workflow.

### 8.3. When CPU is the constraint

If export drives database CPU high:
- Lower PARALLEL.
- Try COMPRESSION_ALGORITHM=LOW if licensed.
- Assess whether compressing data is necessary or metadata-only suffices.
- Run during off-peak hours.
- Spread I/O if storage allows.

Do not add workers to compensate for CPU-heavy compression; both increase CPU pressure.

### 8.4. When network is the constraint

If dump files must cross a slow network:
- COMPRESSION can reduce bytes to transfer.
- HIGH may improve compression ratio at higher CPU cost.
- AES encryption adds CPU processing cost.
- Choose a suitable file set size for transfers/retries.
- Verify bandwidth, latency, and post-transfer checksums.

Even if the network uses TLS, dump encryption still protects files at rest on intermediate storage. Two layers mitigate two different risks.

### 8.5. When storage is the constraint

If dump write/read storage is the bottleneck:
- Inspect IOPS, throughput, and latency.
- Avoid placing dump files on the same volume carrying heavy datafile load if possible.
- Use moderate PARALLEL.
- Choose an appropriate dump file count and file placement.
- Do not push worker count past storage capacity.

### 8.6. When dump size is the constraint

If file size must be reduced:
- Compare METADATA_ONLY versus ALL/DATA_ONLY.
- Measure compression ratios on a representative data sample.
- Check for pre-compressed or already-encrypted data.
- Account for decompression time on the target.
- Ensure option licensing for data compression.

## 9. Separating Dump Encryption, TDE, and Transit Protection

### 9.1. Dump-file encryption

ENCRYPTION protects the contents of the dump file set. Anyone possessing the file without the corresponding password or wallet/keystore cannot read the data via normal Data Pump tools.

### 9.2. TDE at rest

TDE protects datafiles/tablespaces/columns according to database configuration. It does not automatically mean every exported dump file is encrypted by the same mechanism. Data Pump has dedicated parameters for dump encryption.

### 9.3. Network encryption

TLS or native network encryption protects traffic between client/database or across endpoints per configuration. Dump file encryption protects stored files. When transferring dumps via SFTP/object storage, also use secure transfer channels and access policies.

### 9.4. Dumps, logs, and SQL files

Data Pump ENCRYPTION applies to the dump file set. Log files, SQLFILEs, parfiles, and supporting files are not encrypted automatically in the same manner. Protect them using filesystem permissions, object storage policies, volume encryption, and retention.

## 10. Verifying Export and Import Results

### 10.1. Reading the export log

Check:
- Whether the job completed successfully.
- Exported object and row counts.
- Whether all expected dump files were created.
- Any warnings about encryption or skipped objects.
- Elapsed time and throughput.
- Actual file sizes versus estimates.

Do not just check that the expdp process exited. A job can finish with warnings or skipped objects.

### 10.2. Verifying the dump file set

On server/storage:
- Check every file matching the %U pattern.
- Check file sizes, timestamps, and file count.
- Verify all files transferred completely to target.
- Generate/verify checksums per procedure.
- Confirm target database server read permissions.

Never rename multi-part dump files inconsistently. Data Pump needs all files to read the complete job.

### 10.3. Checking import before execution

You can generate an SQL preview with SQLFILE:

~~~bash
impdp app_user@target_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_migration_%U.dmp \
  SQLFILE=app_preview.sql \
  SCHEMAS=APP
~~~

SQLFILE writes the DDL Import intends to run under the specified parameters without loading data. Protect this file as it can contain sensitive schema names, objects, and DDL. SQLFILE is not a complete preview of all runtime actions or proof that import will certainly succeed.

### 10.4. Post-import checks

- Read the log and confirm job status.
- Compare counts of tables, indexes, constraints, and objects.
- Check invalid objects.
- Check row counts for key tables.
- Check sequences/identities and grants.
- Check triggers, synonyms, database links, and jobs.
- Run business smoke tests.
- Gather statistics per target policy.
- Confirm sensitive data is protected on the target.

### 10.5. Controlled data comparison

COUNT(*) is only a basic check. For critical tables, compare:
- Row counts.
- Min/max keys.
- Totals by partition or group.
- Hashes/checksums over selected columns.
- Constraint violations.
- Representative business samples.

If the source continues accepting writes during export, use FLASHBACK_SCN/FLASHBACK_TIME or an appropriate consistency procedure to establish a data cutoff. Parallel, compression, and encryption do not automatically ensure cross-table consistency if the source workload changes during export.

## 11. Sample Configuration Scenarios

### 11.1. Small schema export, prioritizing simplicity

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_small.dmp \
  LOGFILE=app_small.log \
  SCHEMAS=APP \
  COMPRESSION=METADATA_ONLY
~~~

Suitable when parallelism, table data compression, and dump encryption are unnecessary. Files must still be protected under data policy.

### 11.2. Large export, EE with ACO

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_large_%U.dmp \
  FILESIZE=10G \
  LOGFILE=app_large.log \
  SCHEMAS=APP \
  PARALLEL=6 \
  COMPRESSION=ALL \
  COMPRESSION_ALGORITHM=MEDIUM \
  LOGTIME=ALL \
  METRICS=YES
~~~

Use only with Enterprise Edition and Oracle Advanced Compression. Benchmark PARALLEL=2/4/6/8 in an equivalent environment before picking the production degree.

### 11.3. Export for offsite transfer using password encryption

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_offsite_%U.dmp \
  LOGFILE=app_offsite.log \
  SCHEMAS=APP \
  ENCRYPTION=ALL \
  ENCRYPTION_MODE=PASSWORD \
  ENCRYPTION_ALGORITHM=AES256 \
  ENCRYPTION_PWD_PROMPT=YES
~~~

Exchange the password through an independent channel. The recipient needs the password to import. Never send the password alongside the dump path/files.

### 11.4. Export using a wallet on the same system

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_wallet_%U.dmp \
  LOGFILE=app_wallet.log \
  SCHEMAS=APP \
  ENCRYPTION=ALL \
  ENCRYPTION_MODE=TRANSPARENT \
  ENCRYPTION_ALGORITHM=AES256
~~~

The wallet/keystore must be available and contain the required key. If moving to another host, have a secure key transfer/recovery plan.

### 11.5. Importing from EE to SE2

Some migrations export from Enterprise Edition and import into Standard Edition 2, requiring:
- Setting PARALLEL appropriate for the target (SE2 degree 1).
- Verifying objects/features are edition-compatible.
- Avoiding features unlicensed on the target.
- Checking partitions, option-specific objects, and dependencies.
- Evaluating import encryption per edition/option and licensing rules.
- Testing performance with a single worker.

## 12. Common Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| PARALLEL does not run multiple workers | SE2 or edition/license limit | Confirm edition; SE2 caps degree at 1 |
| Workers do not scale with PARALLEL | Not enough dump files, few independent tasks, or object dependencies | Use %U, add files, inspect job status |
| High PARALLEL yet job is no faster | CPU/I/O/memory saturation | Lower workers, measure storage/CPU, and benchmark |
| Dump file barely shrinks even with compression HIGH | Data already compressed/encrypted or lacks repetitive patterns | Benchmark data, try NONE/LOW/MEDIUM |
| ORA error due to compression option | Missing ACO or insufficient COMPATIBLE | Verify licensing and parameters |
| ENCRYPTION_PASSWORD rejected | Dump uses TRANSPARENT mode or wrong password | Check mode, use wallet or correct password |
| Import cannot decrypt | Missing/closed wallet, wrong password, missing key | Verify keystore/password and export mode |
| Dump file too large | COMPRESSION=METADATA_ONLY or ineffective compression | Consider data compression if licensed for ACO |
| Sharp CPU spike | Parallel + compression + encryption consuming CPU together | Lower PARALLEL, test a lighter compression level |
| Storage queue grows | Too many workers reading/writing concurrently | Lower degree, distribute files sensibly |
| Import missing objects | Filtered/skipped objects or dependency/privilege issues | Read log, check INCLUDE/EXCLUDE and privileges |
| Dump file set missing files | Incomplete file pattern/transfer | Check %U and checksums across the full file set |

### 12.1. ORA-390xx and worker errors

Data Pump can return ORA-390xx wrapper errors around the worker's root error. Read the entire log to find the first ORA error and the object being processed. Do not address only the last error line.

### 12.2. Insufficient disk space

Check:
- Dump directory free space.
- File count and FILESIZE.
- Temporary space/workarea if import builds indexes/sorts.
- Target tablespaces.
- FRA/archivelog if import generates heavy redo.
- Log file and auxiliary storage space if applicable.

### 12.3. Job hangs or workers appear idle

Use STATUS, DBA_DATAPUMP_JOBS, DBA_DATAPUMP_SESSIONS, and V$SESSION_LONGOPS. Determine whether the job is waiting on I/O, locks, workers, metadata dependencies, or resources. Attach to inspect before using STOP_JOB/KILL_JOB.

### 12.4. Encryption/password mismatch

Verify accurately:
- Export ENCRYPTION_MODE.
- Whether a password was used.
- Whether the wallet/keystore is open.
- AES algorithm.
- Whether all dump file parts are present.
- Whether the import account has DIRECTORY access.
- Whether the target database meets licensing/feature prerequisites.

Do not attempt to guess passwords by running repeated imports; use secret management procedures.

## 13. Benchmarking Workflow for Configuration Selection

### 13.1. Prepare a representative workload

Select a schema/table with:
- Near-production size.
- Representative data types: text, numbers, dates, LOBs, encrypted columns.
- Realistic data distribution.
- Similar partition/object counts.
- Storage and network resembling the target environment.

### 13.2. Establish a baseline

Run export with:
- PARALLEL=1.
- COMPRESSION=METADATA_ONLY or NONE per goal.
- No encryption if in a test environment and permitted by policy.

Record:
- Elapsed time.
- CPU time/CPU utilization.
- Read/write throughput.
- Dump size.
- Worker count.
- Warnings/errors.
- Import elapsed time.

### 13.3. Test parallelism independently

Run PARALLEL=2, 4, 8 sequentially while keeping compression/encryption constant. Observe where throughput stops scaling or application workloads suffer.

### 13.4. Test compression independently

Hold PARALLEL fixed and compare:
- METADATA_ONLY.
- ALL BASIC.
- ALL LOW.
- ALL MEDIUM.
- ALL HIGH.

Test only licensed levels. Record dump size, CPU, elapsed time, and import time. Do not pick solely by smallest file size.

### 13.5. Test encryption independently

Hold PARALLEL/compression fixed and measure overhead of:
- PASSWORD.
- TRANSPARENT.
- DUAL if needed by use case.
- AES128/AES256 per security policy.

Evaluate export/import times and key management workflows. Security policy may require AES256 even if AES128 is faster; do not downgrade algorithms solely for speed without approval.

### 13.6. End-to-end evaluation

Total migration time includes:
- Export.
- Transfer.
- Import.
- Index/constraint creation.
- Statistics gathering.
- Validation.
- Cutover.

Compression may slow export yet speed up transfer. Parallelism may shorten export yet slow down import or application workloads. Choose settings based on end-to-end time and system impact.

## 14. Preflight Checklist

### Edition and licensing

- [ ] Confirm Oracle Database edition on source and target.
- [ ] Confirm PARALLEL is permitted; SE2 is capped at degree 1.
- [ ] Confirm Advanced Compression if compressing table data/using algorithms.
- [ ] Confirm Advanced Security for dump encryption.
- [ ] Check cloud/engineered offering entitlements if applicable.
- [ ] Never rely on a parameter running without error as proof of licensing.

### Compatibility and encryption

- [ ] Check COMPATIBLE.
- [ ] Choose appropriate COMPRESSION and COMPRESSION_ALGORITHM.
- [ ] Choose ENCRYPTION scope and mode.
- [ ] Determine whether password or wallet/keystore is used.
- [ ] Confirm target can decrypt.
- [ ] Verify AES algorithm aligns with security policy.
- [ ] Protect passwords, wallets, and supporting files.

### Resources

- [ ] Estimate dump size and free space.
- [ ] Ensure enough dump files for the PARALLEL degree.
- [ ] Check CPU, PGA, I/O, and network.
- [ ] Spread dump files across suitable storage.
- [ ] Review RAC CLUSTER/SERVICE_NAME.
- [ ] Confirm maintenance window and application load.

### Execution and verification

- [ ] Record LOGFILE, LOGTIME, and METRICS.
- [ ] Record JOB_NAME and STATUS interval.
- [ ] Confirm export completes with all files present.
- [ ] Generate checksums and transfer files securely.
- [ ] Review SQLFILE/preview when needed.
- [ ] Import with the correct password/wallet.
- [ ] Read logs and inspect objects/data.
- [ ] Run business validation and record results.

## 15. Practice Labs

Practice in a test database with a dedicated dump directory and non-sensitive data. Test licensed options only if the environment is properly licensed.

### Lab 1 — Sequential export

Export a schema with PARALLEL=1. Record elapsed time, dump size, and log.

### Lab 2 — Comparing PARALLEL

Repeat with degree 2 and 4 on the same data. Compare worker counts, elapsed time, CPU, and I/O.

### Lab 3 — Dump file pattern

Use DUMPFILE=lab_%U.dmp, PARALLEL=4, and an appropriate FILESIZE. Confirm Data Pump creates multiple files.

### Lab 4 — PARALLEL on Standard Edition

If a licensed SE2 environment is available, verify the PARALLEL=1 limit and compare against an EE test. Do not try to force a higher degree.

### Lab 5 — METADATA_ONLY

Export with COMPRESSION=METADATA_ONLY. Record dump size and confirm table data is not Data Pump-compressed.

### Lab 6 — Comparing compression algorithms

In an ACO-licensed environment, test LOW, MEDIUM, HIGH, and BASIC. Compare CPU, elapsed time, ratio, and import time.

### Lab 7 — Uncompressed

Export with COMPRESSION=NONE. Compare size and duration against metadata/data compression.

### Lab 8 — PASSWORD encryption

Export with ENCRYPTION=ALL and PASSWORD mode. Import using a prompted password. Test an incorrect password in the test environment.

### Lab 9 — TRANSPARENT encryption

Configure a test wallet/keystore, run a transparent export, and import with the corresponding wallet. Test importing when the wallet is unavailable to observe error behavior.

### Lab 10 — DUAL mode

Create a DUAL dump. Test importing via wallet and via password following Oracle-supported procedures.

### Lab 11 — AES algorithms

Compare AES128 and AES256 on the same test schema. Measure CPU/elapsed time and verify the algorithm meets security policy.

### Lab 12 — Parallel combined with compression

Fix a licensed compression setting. Test PARALLEL=1/2/4 and identify where throughput begins to saturate.

### Lab 13 — Parallel combined with encryption

Fix the AES algorithm and mode. Measure impact as workers increase; check whether CPU becomes the bottleneck.

### Lab 14 — Migration planning

Write export/import parameter files for a test schema detailing edition, licensing, COMPATIBLE, worker count, dump file count, compression, encryption, key handoff, storage, and validation plan.

## 16. Oracle References

- [Oracle Database 19c Utilities — Oracle Data Pump Overview](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-overview.html): Data Pump architecture, workers, and job coordination.
- [Oracle Database 19c Utilities — Oracle Data Pump Performance](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-performance-tips.html): PARALLEL, resource consumption, compression/encryption overhead, and tuning.
- [Oracle Database 19c Utilities — Data Pump Export](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-export-utility.html): PARALLEL, COMPRESSION, COMPRESSION_ALGORITHM, and ENCRYPTION parameters.
- [Oracle Database 19c Utilities — Data Pump Import](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/datapump-import-utility.html): importing dump files, PARALLEL, and ENCRYPTION_PASSWORD.
- [Oracle Database 19c Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/Licensing-Information.html): edition, Oracle Advanced Compression, Oracle Advanced Security, and Parallel Data Pump licensing.
- [Oracle Database 19c Advanced Security Guide — Using TDE with Other Oracle Features](https://docs.oracle.com/en/database/oracle/oracle-database/19/asoag/using-transparent-data-encryption-with-other-oracle-features.html): Data Pump encryption modes and AES algorithms.
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_DATAPUMP](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_DATAPUMP.html): Data Pump API and job parameters.

PARALLEL determines worker concurrency and can only be exploited when edition, file counts, object types, and resources permit. COMPRESSION reduces dump size at potential CPU cost; METADATA_ONLY does not require Advanced Compression, whereas compressing table data requires the corresponding option. ENCRYPTION protects dump files using passwords, wallets, or both, requiring key management and verification of Oracle Advanced Security entitlement. **Before running a migration, verify edition/licensing/COMPATIBLE, benchmark on representative data, secure dumps and keys, and thoroughly validate import results.**
