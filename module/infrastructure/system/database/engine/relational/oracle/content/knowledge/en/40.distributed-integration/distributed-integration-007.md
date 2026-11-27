# UTL_FILE, DIRECTORY, and Filesystem Access Limitations

In data integration flows, Oracle sometimes needs to exchange files with external systems: reading CSVs delivered by applications, writing processing outcomes to files, or creating intermediate files for another process to forward. PL/SQL provides the `UTL_FILE` package for reading and writing files on the database server side. Access permissions are routed through `DIRECTORY` objects, combining Oracle database privileges and operating system permissions.

The key point to remember is that `UTL_FILE` operates on the filesystem visible to the Oracle Database server processes. It does not open folders on the computer of someone running SQL Developer, a web application, or a client connecting to the database. Therefore, when designing distributed integrations, clearly determine which database server holds the files, who creates them, who reads them, and how database nodes share visibility into that storage area.

## 1. Roles of UTL_FILE and DIRECTORY

`UTL_FILE` is a PL/SQL package used to open, read, write, append, close, rename, copy, or delete files inside a directory permitted by the database. The package provides file-level operations; it is not a general filesystem administration API and does not replace a file-transfer service such as SFTP or integration middleware.

A `DIRECTORY` object is a logical name stored in the Oracle Data Dictionary, mapped to a physical path on the database server. Example:

| Component | Example | Meaning |
|---|---|---|
| DIRECTORY object | `INBOUND_DIR` | Logical name passed by PL/SQL to `UTL_FILE` |
| Physical path | `/u01/app/oracle/inbound` | Actual folder on the database server |
| File name | `orders_20261114.csv` | File inside the mapped folder |
| Application schema | `INTEGRATION_APP` | Account granted read or write privileges on the directory |

When calling `UTL_FILE.FOPEN('INBOUND_DIR', 'orders.csv', 'r')`, Oracle looks up the `INBOUND_DIR` object, retrieves the declared physical path, and instructs the database process to open the file in that path. Applications do not pass an arbitrary filesystem path on each call.

A `DIRECTORY` object does not automatically create the folder on the operating system. The physical folder must be created beforehand, exist on the database server, and have appropriate filesystem permissions. One `DIRECTORY` object can be granted to multiple schemas, so you do not need a separate object per schema if schemas genuinely share the same storage area.

## 2. Creating a DIRECTORY and Granting Privileges

An administrator or account with an appropriate system privilege, typically `CREATE ANY DIRECTORY`, creates the mapping object:

```sql
CREATE OR REPLACE DIRECTORY inbound_dir
  AS '/u01/app/oracle/inbound';

CREATE OR REPLACE DIRECTORY outbound_dir
  AS '/u01/app/oracle/outbound';
```

Paths in the example are paths on the host running Oracle Database, not on a user's workstation. On Windows, paths follow Windows server rules, such as `D:\oracle\exchange\inbound`.

After creating the objects, grant only the required privileges to the schema running the program:

```sql
GRANT READ ON DIRECTORY inbound_dir TO integration_app;
GRANT WRITE ON DIRECTORY outbound_dir TO integration_app;
```

`READ` permits reading files in the directory; `WRITE` permits supported file-write operations. Grant both privileges only if a single process needs to read and write in the same directory:

```sql
GRANT READ, WRITE ON DIRECTORY exchange_dir TO integration_app;
```

Privileges can be revoked when no longer needed:

```sql
REVOKE WRITE ON DIRECTORY outbound_dir FROM integration_app;
```

Unquoted `DIRECTORY` object names are normalized to uppercase by Oracle. You can inspect mappings visible to the current account:

```sql
SELECT directory_name, directory_path
FROM all_directories
WHERE directory_name IN ('INBOUND_DIR', 'OUTBOUND_DIR');
```

Accounts with appropriate data dictionary privileges can query `DBA_DIRECTORIES` to view all `DIRECTORY` objects in the database.

Two permission layers must both allow the operation:

1. **Oracle Database:** the schema must hold `READ` or `WRITE` privilege on the exact `DIRECTORY` object.
2. **Operating system:** the service account or OS account running the Oracle Database processes must have corresponding OS permissions to read, write, create, or delete files at the physical path.

Granting Oracle privileges alone cannot bypass OS filesystem permissions. Conversely, granting read/write permissions to the OS account does not automatically grant access to a database schema.

If the operation is invoked from a stored procedure running with definer's rights, grant the `DIRECTORY` privilege directly to the schema owning the program. Do not rely on privileges received via roles when those privileges must be checked during compilation or execution of stored PL/SQL programs.

## 3. Writing Files with UTL_FILE

The following example creates a CSV file in `OUTBOUND_DIR`:

```sql
DECLARE
  l_file UTL_FILE.FILE_TYPE;
BEGIN
  l_file := UTL_FILE.FOPEN(
    location     => 'OUTBOUND_DIR',
    filename     => 'orders_20261114.csv',
    open_mode    => 'w',
    max_linesize => 32767
  );

  UTL_FILE.PUT_LINE(l_file, 'order_id,amount');
  UTL_FILE.PUT_LINE(l_file, '1001,250.00');
  UTL_FILE.PUT_LINE(l_file, '1002,175.50');

  UTL_FILE.FCLOSE(l_file);
EXCEPTION
  WHEN OTHERS THEN
    IF UTL_FILE.IS_OPEN(l_file) THEN
      BEGIN
        UTL_FILE.FCLOSE(l_file);
      EXCEPTION
        WHEN OTHERS THEN
          NULL; -- Preserve original exception; app should log file close errors if needed.
      END;
    END IF;
    RAISE;
END;
/
```

`FOPEN` takes the `DIRECTORY` object name in `location`, the file name in `filename`, and the open mode in `open_mode`. In this example, mode `w` creates a new file or overwrites an existing file of the same name. Therefore, avoid fixed filenames if multiple runs must preserve previous outputs.

Common text modes:

| Mode | Meaning |
|---|---|
| `r` | Open file for reading; file must exist and be readable |
| `w` | Open for writing; creates file or overwrites existing file |
| `a` | Open for appending data to the end of the file |

The corresponding binary modes are `rb`, `wb`, and `ab`. When working in binary mode, use procedures such as `GET_RAW` and `PUT_RAW` instead of line-by-line text processing.

Common text procedures:

- `PUT` writes a string to the file buffer.
- `PUT_LINE` writes a string and terminates the line.
- `NEW_LINE` writes a line terminator.
- `FFLUSH` flushes buffered data to the file.
- `FCLOSE` closes the file and finishes writing.
- `IS_OPEN` checks whether a file handle is still open.

Always close handles after completion. Include a cleanup branch on exceptions to avoid leaving handles open in the session. Do not keep many files open concurrently unless necessary.

## 4. Reading Files with UTL_FILE

The following example reads an input file line by line. Upon reaching end-of-file, `GET_LINE` raises `NO_DATA_FOUND`; the loop catches this exception to exit:

```sql
DECLARE
  l_file UTL_FILE.FILE_TYPE;
  l_line VARCHAR2(32767);
BEGIN
  l_file := UTL_FILE.FOPEN(
    location     => 'INBOUND_DIR',
    filename     => 'orders.csv',
    open_mode    => 'r',
    max_linesize => 32767
  );

  LOOP
    BEGIN
      UTL_FILE.GET_LINE(l_file, l_line);
    EXCEPTION
      WHEN NO_DATA_FOUND THEN
        EXIT;
    END;

    -- Replace with parsing and loading logic suited to the CSV format.
    DBMS_OUTPUT.PUT_LINE(l_line);
  END LOOP;

  UTL_FILE.FCLOSE(l_file);
EXCEPTION
  WHEN OTHERS THEN
    IF UTL_FILE.IS_OPEN(l_file) THEN
      UTL_FILE.FCLOSE(l_file);
    END IF;
    RAISE;
END;
/
```

This example only illustrates reading line by line. In production code, parse CSVs properly: commas may appear inside quoted fields, fields may span newlines, and data may follow specific escaping rules. Avoid naive comma-splitting if the input format allows complex CSV fields.

Beyond reading and writing, the package provides `FGETATTR` for file attributes, `FCOPY` for copying, `FRENAME` for renaming, and `FREMOVE` for deleting files. These operations remain subject to the same `DIRECTORY` privileges and OS filesystem permissions.

## 5. Filesystem Access Limitations

### 5.1. Accessing Only Mapped Paths

PL/SQL applications use `DIRECTORY` names created and granted by administrators. This design controls which filesystem areas a schema is permitted to access. When calling `FOPEN`, pass a filename within that directory; never accept an arbitrary absolute path from a user and pass it directly into the call.

For example, if an application receives a filename from an integration message, validate the filename against an allowlist or defined naming rule. Strip path components, disallowed subdirectory names, and values that could alter file location. Never use external input to decide the `DIRECTORY` path or access storage broader than business permissions allow.

### 5.2. Oracle Privileges and OS Permissions Are Two Independent Conditions

A call can fail even when the `DIRECTORY` object exists:

- The schema lacks `READ` or `WRITE` privilege on the object.
- The stored procedure runs under a different schema than the one granted privilege.
- The physical path does not exist on the database server.
- The Oracle service account lacks OS permissions to read, write, or create files in that folder.
- The file already exists, but its permissions or attributes disallow the requested operation.
- The filesystem is out of space or has hit OS resource limits.

Thus, when investigating failures, verify the `DIRECTORY` name, Oracle object privileges, the real path on the right server, and permissions of the OS account running the database.

### 5.3. Execution Location Constraints

`UTL_FILE` runs on the database server side. If a user connects from a personal machine with `C:\data`, that path means nothing automatically to a database running on Linux or another server. Files must be moved to storage accessible by the database server.

A `DIRECTORY` object is also not a network connection or file-transfer protocol. It maps to a path visible to the database server, such as local storage or a mounted filesystem. To transfer files to a remote host, use a file-transfer mechanism or appropriate middleware; `UTL_FILE` cannot act as an SFTP command.

In Oracle RAC, instances can run across multiple nodes. If nodes need to read the same set of files, the mapped path must exist with consistent permissions across every involved node. Typically, shared storage or a well-operated file-distribution mechanism is required. If each node has only local storage, a file created on one node may not exist when a subsequent session runs on another node.

In a multitenant environment, create and verify `DIRECTORY` objects inside the exact container/PDB used by the application, and verify the path on the actual database server. A `DIRECTORY` object existing in a PDB does not guarantee the physical path exists or has permissions on every host.

### 5.4. Line Size and Open Handle Limits

The `max_linesize` parameter of `FOPEN` accepts values from 1 to 32767; the default is 1024. This is the line-size limit handled by `UTL_FILE` text operations. When processing long lines, specify an appropriate size and respect the 32767-byte cap. With multibyte character sets, the actual character count can be smaller than the byte limit.

Simultaneously open files are also bounded by Oracle configuration—including `UTL_FILE_MAX_OPEN_FILES`—as well as process and OS resource limits. Close handles immediately when done, avoid opening a handle per record, and never hold files open across long business processing.

If data has lines exceeding the limit, large record structures, or binary processing requirements, design an appropriate format and loading mechanism instead of trying to push `max_linesize` past the package limit.

### 5.5. Character Sets and Binary Data

`FOPEN` processes text files in the package's standard character mode. For Unicode data requiring NCHAR handling, use `FOPEN_NCHAR` along with NCHAR procedures such as `GET_LINE_NCHAR` and `PUT_LINE_NCHAR`. Never mix a handle opened in NCHAR mode with incompatible procedures; Oracle may raise `CHARSETMISMATCH`.

For binary content, use binary open modes and `RAW` procedures. Never process binary files as text, as character conversion or newline translation can alter raw bytes.

### 5.6. Files Are Outside Database Transactions

Writing files with `UTL_FILE` does not participate in Oracle transaction rollback. If a program writes part of a file, encounters an error, and rolls back database changes, the already-written file content is not automatically undone. Similarly, committing a transaction does not guarantee an external system received or processed the file.

For critical integration flows, manage import/export states using a control table in the database. You can write to a temporary filename, flush and close the file, and then rename it to the published filename so downstream processes only read completed files. This reduces the risk of a consumer reading a partially written file, though filesystem actions still require monitoring and error handling. Add transaction IDs, unique filenames, duplicate checks, and safe rerun mechanics to prevent loading or sending data twice.

### 5.7. Concurrent Writes and Overwriting

`UTL_FILE` provides no business-level locking when multiple processes write to the same file. Two sessions opening the same filename for write or append concurrently can produce interleaved output or overwrite each other's results. Use unique filenames by batch, transaction ID, or timestamp; if a shared file is required, coordinate write access with locking or queuing at the application layer.

Pay special attention to `w` mode: opening an existing file in this mode overwrites its contents. Before using a fixed filename, establish clear retention, replacement, archiving, and recovery policies.

## 6. UTL_FILE in Distributed Integration Architectures

A file-exchange pattern typically has three parts:

1. **Inbound area:** external systems deliver files to a folder accessible by the database server. The application schema only holds `READ` privilege if it only ingests data.
2. **In-database processing:** PL/SQL reads the file, validates structure and data, writes rows to staging tables, and promotes valid data to business tables. Record filename, batch ID, receipt time, row count, and processing status.
3. **Outbound area:** the program writes output files to a separate folder. An external file-transfer process picks up completed files and sends them to the target system. The schema holds only `WRITE` privilege if it does not need to re-read or delete files.

Separate inbound and outbound directories to scope privileges by data flow direction. Use a dedicated integration schema, grant access only on required `DIRECTORY` objects, and restrict OS permissions strictly to those folders. Never grant `DIRECTORY` privileges to `PUBLIC` without an explicit requirement.

If the database spans multiple nodes, choose one approach: shared storage, routing jobs to the node owning the files, or having the file-transfer service deliver files to the right node. When integrating with a remote database over a database link, remember that a database link enables remote SQL queries; it does not turn a local `DIRECTORY` into a filesystem path on the remote host.

For networked file transfers, retries, encryption, partner authentication, throttling, or delivery tracking, delegate transport to middleware or a managed file transfer service. The database can produce and consume files in a staging area while the integration layer handles network transport and status feedback.

## 7. Common Errors and Isolation

| Oracle Error | Common Cause | Investigation Direction |
|---|---|---|
| `ORA-29280: invalid directory path` | `DIRECTORY` name does not exist or mapped path is invalid | Check `ALL_DIRECTORIES`/`DBA_DIRECTORIES`, target PDB, and server path |
| `ORA-29289: directory access denied` | Schema lacks privileges on `DIRECTORY` | Check and grant required `READ` or `WRITE` privilege |
| `ORA-29283: invalid file operation` | File missing, invalid filename, or OS rejected operation | Check filename, physical folder, OS permissions, and filesystem state |
| `ORA-29284: file read error` | Error while reading file | Check file, read permissions, format, and filesystem state |
| `ORA-29285: file write error` | Error while writing file | Check write permissions, disk space, quotas, and filesystem limits |
| `CHARSETMISMATCH` | Using NCHAR handle with non-NCHAR procedures or vice versa | Consistently use `FOPEN` or `FOPEN_NCHAR` with matching procedures |

An effective isolation checklist:

1. Confirm which schema and which PDB/service the program is running under.
2. Check the `DIRECTORY` name and mapped path in the Data Dictionary.
3. Confirm the schema holds the required object privilege; for definer's rights stored procedures, confirm direct grants to the owner.
4. Log onto or ask an administrator to check the exact database host/node to verify the folder exists and the Oracle OS service account has appropriate permissions.
5. Check filename, open mode, line size, encoding, disk space, and open handle count.
6. Log batch IDs and filenames so reruns or manual handling will not create duplicate data.

## 8. Legacy Configuration Notes and Safe Practices

`UTL_FILE_DIR` is a legacy initialization parameter that once configured directories accessible to `UTL_FILE`. This parameter was deprecated and desupported as of Oracle Database 18c. For new designs, use `DIRECTORY` objects and explicit privileges rather than relying on `UTL_FILE_DIR`.

Recommended practices:

- Create separate `DIRECTORY` objects for each flow or data zone with distinct security boundaries.
- Grant only `READ` or `WRITE` as needed; avoid granting both unnecessarily.
- Never grant `DIRECTORY` privileges to `PUBLIC` and never use accounts with overly broad filesystem rights.
- Keep physical paths administrator-configured; never take arbitrary paths from input data.
- Validate and sanitize filenames arriving from external systems; reject unapproved path components.
- Enforce limits on file size, row count, processing duration, and staging storage at the integration layer.
- Use unique filenames, persist processing state, and design safe rerun mechanics.
- Close files in both success and error paths; log enough details for traceability.
- Clean up old files according to retention policies agreed with operations.
- Protect sensitive data on the filesystem with proper access controls, encryption, and retention rules.

`UTL_FILE` fits when the database needs to read or write files in a governed, controlled filesystem area. `DIRECTORY` objects define which area a schema may request access to; OS permissions decide whether Oracle processes can execute the operation. In distributed systems, complement this with designs for multi-node file placement, file transport, delivery state, reruns, and consistency, since filesystem operations are outside database transactions.
