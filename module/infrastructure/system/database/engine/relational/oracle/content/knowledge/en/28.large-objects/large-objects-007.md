# BFILE, DIRECTORY Objects, and Server-Side File Access in Oracle

Oracle Database provides the **BFILE** data type to reference a binary file located outside the database, on a filesystem accessible to the database server. BFILE stores a locator containing a DIRECTORY object and filename; the file content remains on the filesystem rather than being stored in a table segment like a BLOB.

To read a BFILE, a DBA creates a **DIRECTORY object** mapping a database name to a directory path on the server, then grants READ privilege to the schema needing access. The Oracle Database process must also have OS permissions to traverse the directory and read the file. PL/SQL uses DBMS_LOB routines to check, open, read, and close the file.

BFILE fits when an application needs to reference binary files managed outside the database while accessing them via SQL/PLSQL. BFILE is read-only from Oracle's perspective: the database can read content through the locator, but cannot write or modify the file using DBMS_LOB. If the data must be managed within database transactions, backups, and recovery, BLOB is usually a better fit.

This lesson belongs to the **LOBs and Large Data** topic of *Database Engine Relational Oracle*. Its content focuses on:

- What BFILE is and how it differs from BLOB.
- How DIRECTORY objects map server-side filesystem paths.
- Required database privileges and operating system permissions.
- Storing BFILE locators in tables and creating locators with BFILENAME.
- DBMS_LOB APIs for files: FILEEXISTS, FILEOPEN, READ, GETLENGTH, FILECLOSE, and FILEISOPEN.
- Reading files in chunks, exception handling, and managing file handle lifecycles.
- Access privileges, path injection, and directory protection.
- Transactions, backups, RAC, operational limits, and choosing between BFILE and BLOB.
- Error troubleshooting and SQL/PLSQL practice exercises.

## 1. What Is a BFILE?

BFILE is an external LOB type. A BFILE column in a table does not hold the file's bytes; it holds a locator that lets Oracle locate the file via a DIRECTORY object and filename.

~~~text
Database table
  DOCUMENTS
  +------------+--------------------------------+
  | DOC_ID     | FILE_REF                       |
  +------------+--------------------------------+
  | 101        | locator -> MEDIA_DIR/report.pdf |
  +------------+--------------------------------+
                         |
                         v
              DIRECTORY object MEDIA_DIR
                         |
                         v
              Server filesystem path
              /u01/app/data/media/
                         |
                         v
              report.pdf (file bytes)
~~~

Components:

- **BFILE column/locator:** references the file without storing its content in the database.
- **DIRECTORY object:** a logical database name pointing to a filesystem path.
- **File name:** the name of the file inside the mapped directory.
- **Oracle server process:** the process performing the file read operation.
- **OS permissions:** filesystem permissions held by the OS account running Oracle on the path and file.

### BFILE Is Read-Only

Oracle can open a BFILE in read-only mode and retrieve bytes. DBMS_LOB does not provide operations to write BFILE content, append, trim, or erase external files. If content needs to change, an application or OS workflow must update the file using separate tools; the database simply re-reads the locator when needed.

### BFILE Does Not Contain the File Itself

Inserting a BFILE locator into a table does not upload the file from client to server. The file must already exist at the path pointed to by the DIRECTORY object, and the Oracle server must be able to access that file.

### BFILE Is Not a Client Machine Path

The path in a DIRECTORY object is a path seen from the database server (or a filesystem mounted by the server), not a path on the machine running SQL Developer, SQL*Plus, or a client application. For example, `C:\Users\...\report.pdf` on a user's laptop does not automatically become a BFILE readable by the Oracle server.

## 2. Comparing BFILE and BLOB

BLOB is an internal LOB: binary content is stored inside the database. BFILE is an external LOB: the database stores the locator, while the bytes reside on the filesystem.

| Criterion | BFILE | BLOB |
| --- | --- | --- |
| Content location | Filesystem outside the database | Inside the database |
| Data in column | Locator | Binary content or internal locator |
| Write access via DBMS_LOB | Read-only | Read/write |
| Transaction on content | External file does not participate in Oracle transactions | BLOB changes follow transactions |
| Database backup | Does not automatically back up external files | Backed up with the database per backup policy |
| Consistency | File can change outside the database | Content is managed by the database |
| When to use | File is already managed on filesystem and only needs reading via Oracle | File must be stored, updated, and protected by transactions/database |
| Administration | Must synchronize files, paths, and OS permissions | Managed via tablespaces, LOB storage, and database backups |

### When to Choose BFILE?

- Files are already placed on the server-side filesystem by another process.
- The database only needs to read files, not update their content.
- You want to store metadata and locators in tables while managing content outside the database.
- Large files or many external files that you do not want to bring into internal LOB segments.
- Backup, synchronization, and filesystem permission processes are already managed separately.

### When to Choose BLOB?

- Files must be uploaded and saved in the same transaction that creates the record.
- File and metadata must commit or roll back together.
- File content must be backed up and restored together with the database.
- Applications must update, delete, or replace content via SQL/PLSQL.
- You want to reduce reliance on database server filesystem paths and OS permissions.

### BFILE and External Tables Are Not the Same

An external table allows SQL to read row-like data from files according to a declared access driver and structure. BFILE allows PL/SQL to read the bytes of a specific file through a locator. If you need to parse CSV/records using SQL, an external table may fit better; if you need to read binary content such as PDFs, images, or archives, BFILE is another option.

## 3. DIRECTORY Objects

A DIRECTORY object is a schema object in Oracle containing a mapping from a logical name to a directory path on the database server's filesystem. It neither creates the OS directory nor contains files.

Syntax:

~~~sql
CREATE DIRECTORY media_dir AS '/u01/app/data/media';
~~~

After this statement, the name MEDIA_DIR can be used in BFILENAME or other Oracle features requiring a DIRECTORY object. The path is an absolute path on the database host or a filesystem mounted on the host.

### What Privilege Is Required to Create a DIRECTORY?

Creating a DIRECTORY requires the CREATE ANY DIRECTORY system privilege. This privilege is broad because a grantee can create directory objects pointing to paths on the server. Typically a DBA or controlled deployment account creates the object; application schemas receive only the needed READ privilege.

~~~sql
CREATE DIRECTORY media_dir AS '/u01/app/data/media';
GRANT READ ON DIRECTORY media_dir TO app_user;
~~~

If using other Oracle APIs that write files such as UTL_FILE, WRITE privilege on the corresponding DIRECTORY may be needed. BFILE only reads files, so grant only READ when that is the sole requirement.

### A DIRECTORY Object Is Not an OS Permission

GRANT READ ON DIRECTORY grants privileges only at the database layer. It does not grant file-read permissions to the Oracle process at the operating system level. The OS account running Oracle must:

- Have traverse/execute permission on parent directories.
- Have read permission on the target file.
- Be able to access the corresponding filesystem mount or shared storage.
- Not be blocked by ACLs, SELinux, container boundaries, or other OS policies.

Both permission layers must allow access for a BFILE to be read.

### Changing a DIRECTORY Path

You can change the mapping using CREATE OR REPLACE DIRECTORY:

~~~sql
CREATE OR REPLACE DIRECTORY media_dir
AS '/u02/shared/media';
~~~

The DIRECTORY name remains MEDIA_DIR, but the new path is used for subsequent accesses. File locators store the directory alias and filename; they do not freeze a file copy or old path. Changing the mapping can cause existing locators to point to a different location, so manage this change like a configuration change.

### Viewing DIRECTORY Objects

~~~sql
SELECT directory_name,
       directory_path
FROM all_directories
WHERE directory_name = 'MEDIA_DIR';
~~~

ALL_DIRECTORIES displays directory objects visible to the user based on privileges. DBAs can query DBA_DIRECTORIES; directory objects are managed with database-wide privileges.

## 4. Creating Tables with a BFILE Column and Creating Locators

A BFILE column is declared as a column data type in a table:

~~~sql
CREATE TABLE documents (
    document_id NUMBER
        CONSTRAINT pk_documents PRIMARY KEY,
    file_name VARCHAR2(255) NOT NULL,
    file_ref BFILE
);
~~~

A locator can be created using the BFILENAME function:

~~~sql
INSERT INTO documents (
    document_id,
    file_name,
    file_ref
)
VALUES (
    101,
    'report.pdf',
    BFILENAME('MEDIA_DIR', 'report.pdf')
);
~~~

BFILENAME takes a DIRECTORY object name and a filename and returns a BFILE locator. This function constructs a locator; it does not upload the file and does not guarantee that the file exists or that the Oracle OS process can read it. Verify in practice with DBMS_LOB.FILEEXISTS and file-open operations.

### Updating a Locator

~~~sql
UPDATE documents
SET file_ref = BFILENAME('MEDIA_DIR', 'report-v2.pdf'),
    file_name = 'report-v2.pdf'
WHERE document_id = 101;
~~~

UPDATE changes the locator in the row. It does not rename, copy, or delete files on the filesystem. Old files remain managed by processes outside the database.

### Retrieving a Locator from a Table

~~~sql
DECLARE
    l_file BFILE;
BEGIN
    SELECT file_ref
    INTO l_file
    FROM documents
    WHERE document_id = 101;
END;
/
~~~

The variable l_file receives the locator for DBMS_LOB routines to use. A locator is not the file's entire content; to read bytes, open the BFILE and call READ or an appropriate routine.

### BFILENAME Does Not Check File Existence

You can INSERT a locator for a filename that does not yet exist on the filesystem. Errors typically appear only upon check/open/read. Therefore, if an application must ensure a file is already in place, check with BFILE APIs before marking metadata as ready; you must still handle cases where the file is deleted or modified after the check.

## 5. BFILE Access Privileges

Reading a BFILE requires satisfying both database privileges and filesystem permissions.

### Database Privileges

The DBA creates the directory object and grants READ:

~~~sql
CREATE DIRECTORY media_dir AS '/u01/app/data/media';
GRANT READ ON DIRECTORY media_dir TO app_user;
~~~

The APP_USER schema can construct locators using MEDIA_DIR and invoke BFILE read APIs if other required privileges are present.

### Operating System Permissions

The OS account running Oracle Database must be able to read the file. For example, if the directory has database READ privilege but the file is owned by another OS user with no read permission, FILEOPEN/READ will still fail.

On Linux/Unix, traverse permission (typically execute) on each parent directory and read permission on the file are required. On Windows, check the ACLs of the Oracle service account. If the directory resides on NFS/SMB or shared storage, verify mounts, credentials, availability, and storage-side permissions.

### Stored PL/SQL Privileges

When reading a BFILE from a stored procedure/package, consider AUTHID:

- Definer's rights is the default. The program executes with the owner's privileges under definer's rights rules; granting DIRECTORY READ directly to the schema owner is clear and operationally straightforward.
- Invoker's rights uses the invoker's privileges under AUTHID CURRENT_USER rules; the caller must have appropriate privileges at runtime.
- Privileges granted through roles may not apply inside definer's-rights stored PL/SQL the way direct privileges do; grant the object privilege directly to the owner when the program needs directory access.

Example:

~~~sql
GRANT READ ON DIRECTORY media_dir TO app_owner;

CREATE OR REPLACE PROCEDURE read_document (
    p_document_id IN NUMBER
)
AUTHID DEFINER
AS
    -- BFILE read code
BEGIN
    NULL;
END;
/
~~~

This example only illustrates where to place AUTHID; the body should be implemented according to business requirements. Do not grant CREATE ANY DIRECTORY to an application schema merely so it can read files. DBAs manage mappings; applications receive only least-privilege access on approved directories.

### Privileges Do Not Replace Filename Validation

If users can submit arbitrary filenames, never concatenate those strings directly into BFILENAME. Even though a directory object restricts the root path, the application should still use an allowlist of filenames or validated metadata IDs, restrict allowed characters, and reject path separators and path traversal patterns. Never allow callers to choose the directory alias freely.

## 6. DBMS_LOB APIs for BFILE

The DBMS_LOB package provides routines for working with BFILEs:

| Routine | Purpose |
| --- | --- |
| FILEEXISTS | Checks whether the file referenced by the locator exists and can be identified. |
| FILEOPEN | Opens the file for reading. |
| FILEISOPEN | Checks whether the locator is currently open. |
| GETLENGTH | Gets LOB/file length in bytes for BFILE. |
| READ | Reads bytes from an offset into a RAW buffer. |
| FILECLOSE | Closes an open file. |
| FILECLOSEALL | Closes all open BFILEs in the session. |
| FILEGETNAME | Retrieves the directory alias and filename from the locator. |

### FILEEXISTS

~~~sql
DECLARE
    l_file BFILE := BFILENAME('MEDIA_DIR', 'report.pdf');
    l_exists INTEGER;
BEGIN
    l_exists := DBMS_LOB.FILEEXISTS(l_file);

    IF l_exists = 1 THEN
        DBMS_OUTPUT.PUT_LINE('File exists');
    ELSE
        DBMS_OUTPUT.PUT_LINE('File not found');
    END IF;
END;
/
~~~

FILEEXISTS returns 1 if the file exists and 0 if not, per Oracle's check capability. This is only a point-in-time check; the file may be deleted or modified immediately afterward. FILEEXISTS does not replace exception handling during FILEOPEN/READ.

### FILEOPEN and FILECLOSE

~~~sql
DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);
...
DBMS_LOB.FILECLOSE(l_file);
~~~

BFILEs can only be opened in FILE_READONLY mode. After opening, call READ/GETLENGTH as needed and then close. Do not keep file handles open longer than necessary.

### FILEISOPEN

~~~sql
IF DBMS_LOB.FILEISOPEN(l_file) = 1 THEN
    DBMS_LOB.FILECLOSE(l_file);
END IF;
~~~

FILEISOPEN returns 1 if the file is open and 0 if closed. Use it in exception handlers to close only when needed.

### GETLENGTH

~~~sql
DECLARE
    l_file BFILE := BFILENAME('MEDIA_DIR', 'report.pdf');
    l_length INTEGER;
BEGIN
    DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);
    l_length := DBMS_LOB.GETLENGTH(l_file);
    DBMS_OUTPUT.PUT_LINE('Bytes = ' || l_length);
    DBMS_LOB.FILECLOSE(l_file);
END;
/
~~~

BFILE length is measured in bytes. For text files with multibyte encodings, byte count does not equal character count.

### FILEGETNAME

~~~sql
DECLARE
    l_file BFILE := BFILENAME('MEDIA_DIR', 'report.pdf');
    l_dir_alias VARCHAR2(30);
    l_file_name VARCHAR2(255);
BEGIN
    DBMS_LOB.FILEGETNAME(
        l_file,
        l_dir_alias,
        l_file_name
    );

    DBMS_OUTPUT.PUT_LINE(l_dir_alias || '/' || l_file_name);
END;
/
~~~

FILEGETNAME retrieves the DIRECTORY alias and filename from the locator. It does not return file content and does not prove that the file exists.

## 7. Reading BFILEs with DBMS_LOB.READ

BFILE contains bytes, so READ uses a RAW buffer. LOB offsets start at 1. The amount parameter serves both as the requested byte count to read and receives the actual byte count read.

General syntax:

~~~sql
DBMS_LOB.READ(
    lob_loc IN BFILE,
    amount  IN OUT INTEGER,
    offset  IN INTEGER,
    buffer  OUT RAW
);
~~~

Example reading one chunk:

~~~sql
DECLARE
    l_file   BFILE := BFILENAME('MEDIA_DIR', 'report.pdf');
    l_amount INTEGER := 32767;
    l_offset INTEGER := 1;
    l_buffer RAW(32767);
BEGIN
    DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);

    DBMS_LOB.READ(
        l_file,
        l_amount,
        l_offset,
        l_buffer
    );

    DBMS_OUTPUT.PUT_LINE('Bytes read = ' || l_amount);
    DBMS_LOB.FILECLOSE(l_file);
END;
/
~~~

This example reads only the first chunk. A RAW buffer in PL/SQL has a size limit of 32,767 bytes; to read a longer file, loop over multiple chunks and process each buffer before reading the next chunk.

### Reading an Entire File in Chunks

~~~sql
DECLARE
    l_file       BFILE := BFILENAME('MEDIA_DIR', 'report.pdf');
    l_file_length INTEGER;
    l_offset     INTEGER := 1;
    l_amount     INTEGER;
    l_chunk_size CONSTANT PLS_INTEGER := 32767;
    l_buffer     RAW(32767);
    l_total_read INTEGER := 0;
BEGIN
    IF DBMS_LOB.FILEEXISTS(l_file) = 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'BFILE does not exist');
    END IF;

    DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);
    l_file_length := DBMS_LOB.GETLENGTH(l_file);

    WHILE l_offset <= l_file_length LOOP
        l_amount := LEAST(
            l_chunk_size,
            l_file_length - l_offset + 1
        );

        DBMS_LOB.READ(
            l_file,
            l_amount,
            l_offset,
            l_buffer
        );

        -- Process l_buffer here, e.g., write to a BLOB or decode.
        l_total_read := l_total_read + l_amount;
        l_offset := l_offset + l_amount;
    END LOOP;

    DBMS_LOB.FILECLOSE(l_file);
    DBMS_OUTPUT.PUT_LINE('Total bytes read = ' || l_total_read);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.FILEISOPEN(l_file) = 1 THEN
            DBMS_LOB.FILECLOSE(l_file);
        END IF;
        RAISE;
END;
/
~~~

Key points:

- Check and open the file before reading.
- Use 1-based offsets; after each read, add the actual bytes read to the offset.
- Cap each chunk by the RAW buffer size.
- Close the file on both success and exception paths.
- Do not print RAW contents directly as character strings; bytes could be PDF, image, ZIP, or arbitrary binary data.

### Empty Files

If a file has length 0, the WHILE loop does not execute and READ is not called. This is a valid outcome; do not treat empty files as errors unless prohibited by business rules.

### Offset Exceeding Length

Avoid calling READ with an offset greater than the file length. A READ with no data at that offset can raise NO_DATA_FOUND. Use GETLENGTH to bound the loop and handle cases where the file is modified while being read.

### BFILE Is Not Modified by READ

READ only copies bytes into a PL/SQL buffer. It does not alter the file on the filesystem and does not update the locator in the table.

## 8. Closing Files Safely and Handling Exceptions

File handles are session resources. When opening a BFILE manually, always close the file in both normal and exception paths. Otherwise, the session may keep file handles open until closed or session resources are released.

Management pattern:

~~~sql
DECLARE
    l_file BFILE := BFILENAME('MEDIA_DIR', 'report.pdf');
    l_length INTEGER;
BEGIN
    DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);
    l_length := DBMS_LOB.GETLENGTH(l_file);
    DBMS_OUTPUT.PUT_LINE('Length = ' || l_length);
    DBMS_LOB.FILECLOSE(l_file);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.FILEISOPEN(l_file) = 1 THEN
            DBMS_LOB.FILECLOSE(l_file);
        END IF;
        RAISE;
END;
/
~~~

### Do Not Close an Unopened Locator

Calling FILECLOSE on an unopened locator can raise an invalid file operation error. Use FILEISOPEN to check before closing inside a cleanup handler.

### FILECLOSEALL

~~~sql
BEGIN
    DBMS_LOB.FILECLOSEALL;
END;
/
~~~

FILECLOSEALL closes all open BFILEs in the session. It is a broad cleanup mechanism, but it can close files that other code in the same session still needs. Prefer tracking and closing the specific locator your program opened; use FILECLOSEALL only when you control all file handles in the session.

### File Handles and Transactions Have Separate Lifecycles

FILECLOSE does not COMMIT or ROLLBACK. Nor do COMMIT/ROLLBACK substitute for closing files. Manage BFILE resources separately from transactions on metadata tables.

## 9. Reading Text Files and Encoding

BFILE reads bytes. If a file is UTF-8, UTF-16, or another text encoding, you cannot assume each byte corresponds to one character. You must know the file's encoding and convert properly before handling content as VARCHAR2/CLOB.

### Distinguishing Bytes and Characters

- GETLENGTH on a BFILE returns the file's byte count.
- READ offsets are byte positions, 1-based.
- Unicode character count may differ from byte count.
- Arbitrary chunking can split inside a multibyte character's byte sequence.
- Reading text files requires respecting charset boundaries or using an appropriate LOB conversion API.

### Do Not Use UTL_RAW.CAST_TO_VARCHAR2 as a General Decoder

CAST_TO_VARCHAR2 is not a general-purpose charset converter for arbitrary files. It simply reinterprets bytes according to the environment's capabilities and charset, which can produce garbled characters or data loss. For text with a known encoding, use DBMS_LOB.LOADCLOBFROMFILE or UTL_I18N with the appropriate charset ID; for binary content, keep it as RAW/BLOB.

### Loading a BFILE into a CLOB

When reading a text file into an internal CLOB, you can use DBMS_LOB.LOADCLOBFROMFILE with the right charset ID. Create the destination CLOB, open the BFILE, and pass charset ID, lang_context, and warning according to your Oracle version's API signature. Conceptual example:

~~~sql
DECLARE
    l_src BFILE := BFILENAME('TEXT_DIR', 'notes.txt');
    l_dest CLOB;
    l_dest_offset INTEGER := 1;
    l_src_offset INTEGER := 1;
    l_lang_context INTEGER := DBMS_LOB.DEFAULT_LANG_CTX;
    l_warning INTEGER;
BEGIN
    INSERT INTO text_documents(document_id, content)
    VALUES (1, EMPTY_CLOB())
    RETURNING content INTO l_dest;

    DBMS_LOB.FILEOPEN(l_src, DBMS_LOB.FILE_READONLY);

    DBMS_LOB.LOADCLOBFROMFILE(
        dest_lob     => l_dest,
        src_bfile    => l_src,
        amount       => DBMS_LOB.LOBMAXSIZE,
        dest_offset  => l_dest_offset,
        src_offset   => l_src_offset,
        bfile_csid   => NLS_CHARSET_ID('AL32UTF8'),
        lang_context => l_lang_context,
        warning      => l_warning
    );

    DBMS_LOB.FILECLOSE(l_src);
END;
/
~~~

This sample illustrates the case where table TEXT_DOCUMENTS has a CLOB column CONTENT and the file is genuinely UTF-8 encoded. Check warnings, exceptions, and actual charset; do not blindly copy AL32UTF8 for files with other encodings. The destination CLOB is saved within the Oracle transaction, while the source BFILE remains on the filesystem.

## 10. Copying a BFILE into a BLOB

A workflow can ingest an external file via BFILE and copy its content into a BLOB to bring the file under database-managed storage. After copying, the BLOB content participates in database transactions, backups, and recovery.

Example for a file smaller than the API's amount limit:

~~~sql
CREATE TABLE stored_documents (
    document_id NUMBER PRIMARY KEY,
    content BLOB
);

DECLARE
    l_src BFILE := BFILENAME('MEDIA_DIR', 'report.pdf');
    l_dest BLOB;
    l_amount INTEGER;
    l_dest_offset INTEGER := 1;
    l_src_offset INTEGER := 1;
BEGIN
    IF DBMS_LOB.FILEEXISTS(l_src) = 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Source file not found');
    END IF;

    INSERT INTO stored_documents(document_id, content)
    VALUES (101, EMPTY_BLOB());

    SELECT content
    INTO l_dest
    FROM stored_documents
    WHERE document_id = 101
    FOR UPDATE;

    DBMS_LOB.FILEOPEN(l_src, DBMS_LOB.FILE_READONLY);
    l_amount := DBMS_LOB.GETLENGTH(l_src);

    DBMS_LOB.LOADBLOBFROMFILE(
        dest_lob    => l_dest,
        src_bfile   => l_src,
        amount      => l_amount,
        dest_offset => l_dest_offset,
        src_offset  => l_src_offset
    );

    DBMS_LOB.FILECLOSE(l_src);
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.FILEISOPEN(l_src) = 1 THEN
            DBMS_LOB.FILECLOSE(l_src);
        END IF;
        ROLLBACK;
        RAISE;
END;
/
~~~

This example assumes the file is small enough for amount to fit within the routine's type limits and that table creation privileges exist. For large files, read/copy in chunks or use version-appropriate APIs, tracking offsets and memory limits. The destination BLOB row is locked with SELECT FOR UPDATE to update the locator inside the transaction.

### When to Copy BFILE to BLOB?

- You want to capture an immutable snapshot of the file at ingestion time.
- The file must be backed up and restored with the database.
- File content must participate in transactions alongside metadata.
- You want to reduce filesystem dependency after import.

After a successful copy, an external process can archive or delete the source file per policy. Do not delete the source before the transaction holding the BLOB commits and the result is verified.

## 11. Transactions and External File Consistency

A BFILE locator can be stored inside a transaction, but the bytes on the filesystem are not part of an Oracle transaction:

- INSERT/UPDATE of the locator can COMMIT or ROLLBACK.
- Creating, deleting, replacing, or editing files on the OS is not rolled back by Oracle.
- FILEOPEN does not lock the file under Oracle row-locking rules.
- Database read consistency does not snapshot filesystem contents.
- A file can change between FILEEXISTS and FILEOPEN, or while another process updates it.

### Race Between Checking and Opening a File

An execution sequence might do:

1. FILEEXISTS returns 1.
2. Another OS process deletes or renames the file.
3. FILEOPEN raises an error.

Thus, FILEEXISTS is a convenience check, not a guarantee that the file will remain present. Always catch errors on FILEOPEN/READ.

### Safe File Publishing Workflow

For files produced by another system, use immutable versioned or ID-based filenames, write to a temporary name, and publish via an atomic filesystem rename/move once the file is complete. Only then insert the locator into the table. Avoid overwriting the content of a file currently being read by multiple sessions.

If a file must be replaced, consider versioned filenames and updating the locator in the database once the new file is ready. Replacing an OS file and updating database metadata is still not an automatic distributed transaction; design recovery handling for cases where one step succeeds and the other fails.

## 12. Securing DIRECTORY Objects and Filenames

A DIRECTORY object is a filesystem access boundary managed by the database. Granting READ to a user allows that user to ask Oracle to read files in the granted directory, subject to the Oracle process's OS permissions. Therefore, choosing paths and grantees carefully is critical.

### Least-Privilege Principles

- Only DBAs/controlled deployment accounts should create or alter DIRECTORY objects.
- Grant READ only to schemas that need to read files.
- Do not grant WRITE if only BFILE is used.
- Never grant permissions on directories holding sensitive configs, wallets, passwords, or system files.
- Separate directories by application and data type; avoid one overly broad root directory.
- Never grant CREATE ANY DIRECTORY to ordinary application schemas.
- Review and revoke privileges when an application/user no longer needs access.

### GRANT and REVOKE

~~~sql
GRANT READ ON DIRECTORY media_dir TO app_user;

REVOKE READ ON DIRECTORY media_dir FROM app_user;
~~~

DIRECTORY privileges are object privileges. GRANT READ does not create files, alter OS permissions, or allow users to read arbitrary paths on the server.

### Do Not Accept Arbitrary Directory Aliases from Users

Do not let requests pass a DIRECTORY object name and use it directly:

~~~sql
-- Unsafe design if p_directory is arbitrarily supplied by client.
l_file := BFILENAME(p_directory, p_file_name);
~~~

Instead, hardcode the alias in server-side code or map a validated business code to an approved directory. Callers should only select document IDs they are authorized to access.

### Do Not Accept Full File Paths from Clients

BFILENAME takes a directory alias and filename separately. Do not concatenate absolute paths from clients, and reject directory components like `..` or path separators in filenames when business rules only allow a single filename. Use a character allowlist, length limits, and look up filenames from validated metadata.

### Do Not Trust a Filename Simply Because It Is Stored in a Table

Filenames may originate from uploads or external integrations. If an unvalidated filename is stored in a table, an attacker could exploit path traversal, special names, or control characters to request access to unintended files. Validate filenames at ingestion, restrict directories, use generated IDs, and never let untrusted data decide the directory alias.

### Keep OS Permissions Minimal

The Oracle service account should only have read access to required directories. Avoid granting read access across entire home directories, backup directories, wallets, or credential folders. A DIRECTORY object bounds mappings at the database layer, while OS permissions remain the final line of defense for files.

## 13. Operations: Backup, Restore, and File Synchronization

BFILE bytes live outside the database, so RMAN does not back them up like BLOBs. Database backups preserve locators and metadata, not the file contents themselves.

### Backups Must Cover Both Sides

A BFILE backup procedure needs to:

1. Back up metadata tables and the database per RMAN policy.
2. Back up external directories/files using filesystem or storage tools.
3. Document DIRECTORY object-to-path mappings for each environment.
4. Ensure database snapshots and file snapshots align consistently in time.
5. Test restoring the database and files together.

If only the database is restored, locators may point to files that were deleted, replaced, or not yet restored. If files are restored to a newer version while metadata is point-in-time restored to an earlier point, application data may become inconsistent.

### Data Guard and Standby

Data Guard protects database files and metadata via redo transport/apply, but does not automatically replicate BFILE files on external filesystems. The system needs a separate file replication workflow to the standby host, ensuring the DIRECTORY object points to the right path and the Oracle account on the standby has read permissions.

During switchover/failover, files may be missing on the new host if not replicated. Verify BFILE availability as part of DR readiness checks.

### Oracle RAC

In RAC, each instance can run on a different node. If a DIRECTORY points to a local filesystem existing only on node 1, sessions routed to node 2 will fail to read the same file. Use a shared/cluster filesystem or synchronize files and paths in a controlled way across every node that can serve the service.

Verify:

- Does the path mean the same location on all nodes?
- Does the file exist with the same checksum/version on every node?
- Does the Oracle OS account on each node have read permission?
- Are mounts available after reboot/failover?
- Does file deployment complete before the service accepts requests?

Result cache/LOB cache does not substitute for ensuring the file is present on the node.

### Immutable Files and Checksums

For critical files, store metadata such as size, checksum, version, created_at, and publish status alongside the locator. Checksums can be computed at the application layer or ingestion pipeline; BFILE itself does not guarantee files cannot be altered outside the database.

Versioned or UUID-based filenames avoid overwriting content under the same name while sessions are reading. When a new file is ready, update the locator in a transaction and retain older versions per retention policy.

## 14. Limitations and Characteristics to Remember

### BFILE Is Read-Only and External

- Do not use DBMS_LOB.WRITE, APPEND, TRIM, or ERASE with BFILE.
- Do not use the locator to upload content from a client.
- There is no transaction rollback for filesystem changes.
- There is no automatic file backup/recovery from RMAN.
- There are no Oracle row locks protecting file bytes.

### Size Limits

BFILE has size limits depending on the Oracle version; traditional Oracle documentation specifies a maximum around 4 GB for a BFILE. Verify exact limits for your release/platform and numeric types of amount/offset APIs before processing files near the limit. Do not assume every PL/SQL routine receives an entire file's length in a single call; reading in chunks is safer for large files.

### Open File Count

Each open BFILE consumes a file handle resource. Sessions have resource limits and the OS also enforces file descriptor/handle limits. Close files promptly rather than opening thousands of files and closing only at batch end; handle exceptions and monitor limit errors.

### Directory Objects and Files Can Change Independently

A DBA can run CREATE OR REPLACE DIRECTORY to map the same alias to another path. Files can be renamed/deleted/replaced outside the database. A locator does not guarantee immutability of path or content. Configuration management and file versioning processes are needed.

### BFILE Does Not Decode File Formats

BFILE supplies bytes only. Oracle does not automatically parse PDF, JPEG, ZIP, Office documents, or proprietary formats. Applications must use appropriate parsers or move content into internal LOBs/processing services.

## 15. Troubleshooting BFILE Errors

When FILEOPEN or READ fails, check in order:

1. Is the locator NULL?
2. Does the DIRECTORY alias in the locator exist?
3. Does the DIRECTORY object point to the right server path?
4. Does the user/effective PL/SQL principal have READ privilege on the directory?
5. Does the Oracle OS process have permission to traverse directories and read the file?
6. Does the file exist, with the right name, case sensitivity, and on the right node?
7. Was the file locked, replaced, or deleted during access?
8. Has the session exceeded its open file handle limit?

### Common Error Codes

| Error Code | Common Meaning | Where to Check |
| --- | --- | --- |
| ORA-22285 | Directory or file does not exist for file operation | Check DIRECTORY object, path, filename, and file on server. |
| ORA-22288 | File/LOB operation failed | Inspect accompanying OS error, filesystem permissions, mount, and file status. |
| ORA-22290 | Operation exceeds open files/LOBs limit | Close locators properly; check FILEISOPEN and handle counts. |
| ORA-22289 | Invalid locator/file operation in calling context | Check locator, open/close state, and API call order. |
| ORA-01031 | Insufficient privileges | Check READ privilege on DIRECTORY and effective privileges of stored code. |
| ORA-06502 | Numeric/value error | Check RAW buffer, amount, offset, and data conversion. |

Specific messages may include an OS error or additional error codes. Log the DIRECTORY alias, sanitized filename, failed operation, and SQLCODE/SQLERRM; avoid writing entire file contents or sensitive paths to public logs.

### Checking Directory Privileges

~~~sql
SELECT grantee,
       table_name AS directory_name,
       privilege
FROM all_tab_privs
WHERE table_name = 'MEDIA_DIR'
ORDER BY grantee, privilege;
~~~

ALL_TAB_PRIVS displays object grants visible to the user. DBAs can inspect DBA_TAB_PRIVS. If stored code uses definer's rights, verify the owner's direct grants rather than relying only on roles.

### Checking Paths and Object Status

~~~sql
SELECT directory_name, directory_path
FROM all_directories
WHERE directory_name = 'MEDIA_DIR';

SELECT object_name, object_type, status
FROM user_objects
WHERE object_type IN ('TABLE', 'PROCEDURE', 'FUNCTION', 'PACKAGE')
ORDER BY object_type, object_name;
~~~

Directory objects do not appear as ordinary tables/PLSQL objects in USER_OBJECTS. Use ALL_DIRECTORIES/DBA_DIRECTORIES to inspect mappings.

## 16. Comprehensive Practice Lab

Run inside a learning schema with CREATE TABLE privileges. The DBA must prepare the directory and file on the database server beforehand. DDL performs an implicit commit in Oracle; do not run object creation/drop commands in a production business schema.

### DBA and OS Preparation

1. Create a directory on the database server, e.g., `/u01/app/data/media`.
2. Place a test file `sample.bin` inside that directory.
3. Grant OS permissions so the Oracle service account can traverse the directory and read the file.
4. Create the DIRECTORY object and grant READ:

~~~sql
CREATE OR REPLACE DIRECTORY lab_media_dir
AS '/u01/app/data/media';

GRANT READ ON DIRECTORY lab_media_dir TO lab_user;
~~~

The path must exist on the database host. If using Windows or a shared filesystem, substitute a path suitable for the OS/database service account. Learners cannot replace this step with a path on a client machine.

### Step 1: Verify Directory Mapping

~~~sql
SELECT directory_name, directory_path
FROM all_directories
WHERE directory_name = 'LAB_MEDIA_DIR';
~~~

Confirm the path matches the file location visible to the Oracle server.

### Step 2: Create a Table to Store Locators

~~~sql
CREATE TABLE lab_bfile_documents (
    document_id NUMBER PRIMARY KEY,
    file_name VARCHAR2(255) NOT NULL,
    file_ref BFILE
);
~~~

### Step 3: Create and Store a Locator

~~~sql
INSERT INTO lab_bfile_documents (
    document_id,
    file_name,
    file_ref
)
VALUES (
    1,
    'sample.bin',
    BFILENAME('LAB_MEDIA_DIR', 'sample.bin')
);

COMMIT;
~~~

The INSERT statement stores only the locator. It does not copy the bytes of sample.bin into the database.

### Step 4: Check FILEEXISTS

~~~sql
DECLARE
    l_file BFILE;
    l_exists INTEGER;
BEGIN
    SELECT file_ref
    INTO l_file
    FROM lab_bfile_documents
    WHERE document_id = 1;

    l_exists := DBMS_LOB.FILEEXISTS(l_file);

    IF l_exists = 1 THEN
        DBMS_OUTPUT.PUT_LINE('File exists');
    ELSE
        DBMS_OUTPUT.PUT_LINE('File does not exist');
    END IF;
END;
/
~~~

If it returns 0, check filename, path, case sensitivity, and whether the file was placed on the server.

### Step 5: Open the File and Get Its Length

~~~sql
DECLARE
    l_file BFILE;
    l_length INTEGER;
BEGIN
    SELECT file_ref
    INTO l_file
    FROM lab_bfile_documents
    WHERE document_id = 1;

    DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);
    l_length := DBMS_LOB.GETLENGTH(l_file);

    DBMS_OUTPUT.PUT_LINE('File bytes = ' || l_length);
    DBMS_OUTPUT.PUT_LINE(
        'Is open = ' || DBMS_LOB.FILEISOPEN(l_file)
    );

    DBMS_LOB.FILECLOSE(l_file);
END;
/
~~~

Observe that GETLENGTH returns byte count, not character count.

### Step 6: Read the File in Chunks

~~~sql
DECLARE
    l_file BFILE;
    l_length INTEGER;
    l_offset INTEGER := 1;
    l_amount INTEGER;
    l_buffer RAW(32767);
    l_total INTEGER := 0;
BEGIN
    SELECT file_ref
    INTO l_file
    FROM lab_bfile_documents
    WHERE document_id = 1;

    DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);
    l_length := DBMS_LOB.GETLENGTH(l_file);

    WHILE l_offset <= l_length LOOP
        l_amount := LEAST(32767, l_length - l_offset + 1);
        DBMS_LOB.READ(l_file, l_amount, l_offset, l_buffer);

        -- Process l_buffer or forward to a destination LOB here.
        l_total := l_total + l_amount;
        l_offset := l_offset + l_amount;
    END LOOP;

    DBMS_LOB.FILECLOSE(l_file);
    DBMS_OUTPUT.PUT_LINE('Read bytes = ' || l_total);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.FILEISOPEN(l_file) = 1 THEN
            DBMS_LOB.FILECLOSE(l_file);
        END IF;
        RAISE;
END;
/
~~~

Test with a file larger than 32,767 bytes to observe multiple READ calls. Do not print the RAW buffer as text without knowing the encoding.

### Step 7: Inspect Directory and Filename from Locator

~~~sql
DECLARE
    l_file BFILE;
    l_directory VARCHAR2(128);
    l_name VARCHAR2(255);
BEGIN
    SELECT file_ref
    INTO l_file
    FROM lab_bfile_documents
    WHERE document_id = 1;

    DBMS_LOB.FILEGETNAME(
        l_file,
        l_directory,
        l_name
    );

    DBMS_OUTPUT.PUT_LINE(l_directory || '/' || l_name);
END;
/
~~~

### Step 8: Inspect Privileges

~~~sql
SELECT grantee, table_name, privilege
FROM all_tab_privs
WHERE table_name = 'LAB_MEDIA_DIR';
~~~

If the privilege is missing or FILEOPEN is rejected, ask the DBA to check grants and the Oracle process's OS permissions.

### Step 9: Clean Up Data

~~~sql
DROP TABLE lab_bfile_documents PURGE;
~~~

The DBA can revoke privileges and drop the DIRECTORY object once no longer used by applications:

~~~sql
REVOKE READ ON DIRECTORY lab_media_dir FROM lab_user;
DROP DIRECTORY lab_media_dir;
~~~

DROP DIRECTORY only removes the mapping object in Oracle; it does not delete the directory or files on the filesystem. Delete files/directories via a separate OS procedure only after confirming no locators or applications still use them.

## 17. Common Errors and Resolutions

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| BFILENAME creates locator but FILEEXISTS returns 0 | File missing at server path or wrong name | Check directory mapping and file on database host. |
| ORA-22285 when opening | Directory/file does not exist or wrong name | Check ALL_DIRECTORIES, filename, and case sensitivity. |
| ORA-22288 when opening/reading | OS permissions, mount, or file operation failed | Check accompanying OS error and Oracle service account permissions. |
| ORA-01031 | Missing READ privilege or stored code using wrong effective principal | Grant proper privileges to schema/definer or invoker. |
| File exists on laptop but Oracle cannot see it | Path is on client, not server | Move file to a filesystem accessible by the database server. |
| DIRECTORY READ granted but still unreadable | OS process lacks traverse/read permissions | Fix OS ACLs/permissions and mounts. |
| FILECLOSE raises error | Locator not open or already closed | Check FILEISOPEN before cleanup. |
| ORA-22290 | Too many open file handles | Close files after each operation; audit exception paths. |
| Text file has corrupted diacritics | Wrong encoding or chunk split mid-multibyte character | Use LOAD CLOB API with the exact charset ID. |
| BFILE locator exists but file is gone | File deleted/moved outside database | Synchronize metadata and filesystem; check file on open. |
| File unreadable after failover | File not synchronized to new node/standby | Replicate files and paths/permissions on all serving hosts. |
| Database backup restored but file missing | BFILE bytes are not in RMAN backups | Back up/restore filesystem separately and align point-in-time. |

## 18. Self-Check Questions

1. **What does BFILE store in a table?** A locator referencing a DIRECTORY object and filename, not the file's bytes.
2. **Where does a BFILE live?** On a filesystem accessible to the database server.
3. **Can a BFILE be written using DBMS_LOB?** No; BFILE is read-only.
4. **Does a DIRECTORY object create an OS directory?** No; it only maps a logical name to a path.
5. **What privilege is required to create a DIRECTORY?** The CREATE ANY DIRECTORY system privilege.
6. **What DIRECTORY privilege does BFILE require?** READ; WRITE is unnecessary if only reading BFILEs.
7. **Does GRANT READ grant OS permissions?** No; the Oracle service account must still have filesystem permissions.
8. **Does BFILENAME check whether the file exists?** No; it creates a locator.
9. **What does FILEEXISTS return?** 1 if the file exists per the check, 0 if not.
10. **Where does the offset of DBMS_LOB.READ start?** At 1, and measured in bytes for BFILE.
11. **Why read in chunks?** PL/SQL RAW buffers have size limits; chunking handles large files and controls memory.
12. **Why must FILECLOSE be called in an exception handler?** To release the file handle when an operation fails.
13. **Should FILECLOSEALL be used indiscriminately?** No; it closes all open BFILEs in the session.
14. **Does GETLENGTH return characters or bytes?** Bytes for BFILE.
15. **Does BFILE provide transaction semantics for external files?** No; transactions only manage locators/metadata inside the database.
16. **Does RMAN back up BFILE contents?** No; external files need separate backups.
17. **What must RAC environments watch out for?** Paths/files must be available and readable on every node that can receive sessions.
18. **Does Data Guard automatically replicate BFILE files?** No; a separate filesystem synchronization mechanism is required.
19. **When should BFILE be migrated to BLOB?** When file contents must be managed, backed up, and transactionally controlled by the database.
20. **How does BFILE differ from an external table?** BFILE reads bytes through a locator; external tables read file data as SQL rows/columns.

BFILE lets Oracle reference and read binary files located outside the database via a DIRECTORY object. Successful access requires a valid locator, READ privilege in the database, and filesystem permissions for the Oracle server process. Use DBMS_LOB to check, open, read in chunks, and close files; always handle exceptions and never confuse file handles with transactions. Because bytes reside outside the database, manage backups, restores, versioning, RAC/standby availability, and file consistency separately. Choose BFILE when only external file reading is needed; choose BLOB when content must be managed by the database as internal data.
