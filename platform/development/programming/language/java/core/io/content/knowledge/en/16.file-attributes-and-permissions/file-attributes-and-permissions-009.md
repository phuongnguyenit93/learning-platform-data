# Setting Attributes When Creating Files in Java NIO.2

## 1. The Problem: Not Just Creating a File, Creating It with the Right Attributes

When an application writes configurations, private keys, reports, temporary files, or user data, the question is not only "was the file created successfully?" but also **does the new file have the necessary access permissions, owner, and attributes?**

Java NIO.2 supports passing **initial file attributes** into several file and directory creation methods. For example, on a filesystem supporting POSIX permissions, you can request creating a file readable and writable only by the **owner**:

~~~java
Set<PosixFilePermission> permissions =
        PosixFilePermissions.fromString("rw-------");

FileAttribute<Set<PosixFilePermission>> attrs =
        PosixFilePermissions.asFileAttribute(permissions);

Files.createFile(path, attrs);
~~~

This is an **illustrative code snippet**: `path` is a non-existent `Path`, and imports from `java.nio.file`, `java.nio.file.attribute`, and `java.util.Set` are required. The call can throw `IOException` or `UnsupportedOperationException` depending on the filesystem. Complete standalone programs and support checks appear in the sections below.

**Core idea:** requesting attributes **right inside the creation operation** usually avoids the "time window where the file exists with default permissions before being edited", provided the provider supports that attribute at creation time. This is especially critical for sensitive data. However, not every provider accepts every attribute, and the operating system/filesystem still enforces its own policies on effective permissions.

This lesson focuses on **setting attributes when creating files** with Java 17's `Files`. You will learn:

1. To distinguish **initial attributes**, **file open options**, and **post-creation attribute updates**.
2. To use `FileAttribute<?>` with `Files.createFile`, `Files.createDirectory`, `Files.createTempFile`, and `Files.newByteChannel`.
3. To build **POSIX** permission requests with `PosixFilePermissions.fromString` and `asFileAttribute`.
4. To understand provider support scope, Windows/POSIX differences, and limitations of calling `chmod` yourself after creation.
5. To verify results, handle errors, and stay safe when creating files without permitting overwrites.
6. To apply Java 17 through compilable, runnable examples with verified outputs.

## 2. File Attributes, Permissions, and Open Options Are Different Concepts

A filesystem can store types of information about an entry such as:

- **Name, type, and size:** regular file, directory, symbolic link; byte count; basic metadata.
- **Timestamps:** creation, modification, access times (capability and precision depend on the provider).
- **POSIX access permissions:** read/write/execute bits for owner, group, and others.
- **Owner/group:** user and group info attached to the entry, if supported by the filesystem.
- **ACLs:** fine-grained access control lists on some filesystems.
- **DOS attributes:** e.g., hidden, read-only, system, archive when supported by the provider.
- **Provider-defined attributes:** not guaranteed to be usable on all systems.

Three parameter groups are very easy to confuse:

| Kind | Example | Question Answered |
| --- | --- | --- |
| Initial `FileAttribute<?>` | `PosixFilePermissions.asFileAttribute(...)` | *Create newly with what attributes?* |
| `OpenOption` | `CREATE_NEW`, `WRITE`, `APPEND` | *Open/create the file with what mode?* |
| Post-creation attribute setter methods | `Files.setPosixFilePermissions`, `Files.setAttribute`, `Files.setOwner` | *How to change attributes of an existing entry?* |

Do not use `StandardOpenOption.CREATE_NEW` to mean "owner read-only". It controls creation/open conditions, **not a permission set**. Likewise, `PosixFilePermissions.asFileAttribute` does not decide whether to overwrite or append.

### 2.1. Initial Attributes Do Not Mean Every Metadata Field Can Be Set

Each `FileAttribute<T>` has an attribute **name** and **value**. Java has multiple `FileAttributeView`s to read/write metadata, yet **there is no guarantee every readable/writable attribute can be passed at creation time**.

For example, a filesystem might allow editing last-access time **after** the file exists, while not supporting setting that time as an initial attribute in `Files.createFile`. For an attribute unsupported at creation, the provider can throw `UnsupportedOperationException`.

Read the creation method's contract and test against a real provider rather than guessing from the existence of an attribute view.

## 3. APIs Accepting FileAttribute<?> at Creation Time

The following methods have a trailing parameter `FileAttribute<?>... attrs`:

| Method | Purpose | Notes on attrs |
| --- | --- | --- |
| `Files.createFile(path, attrs)` | Creates a new file; does not overwrite an existing file | Applies supported attributes right at creation |
| `Files.createDirectory(path, attrs)` | Creates a single new directory; parent must exist | Can request initial directory permissions |
| `Files.createDirectories(path, attrs)` | Creates necessary parent directories | Attributes apply to directories **newly created**; existing directories are not reset |
| `Files.createTempFile(dir, prefix, suffix, attrs)` | Creates a new temporary file in the specified directory | Can request initial attributes |
| `Files.createTempDirectory(dir, prefix, attrs)` | Creates a new temporary directory | Suitable as a private directory for sensitive data |
| `Files.newByteChannel(path, options, attrs)` | Opens a byte channel, optionally creating the file | Initial attributes only apply **when the file is newly created** |
| `Files.createSymbolicLink(link, target, attrs)` | Creates a symbolic link if supported | Many providers do not support initial attrs for symbolic links; do not infer target permissions |

`Files.createFile` and `Files.createDirectory` provide direct APIs for "creating a new entry with attributes". If you need to open and write immediately in one operation, `Files.newByteChannel` is worth considering when supplying `FileAttribute<?>...` alongside `OpenOption`s.

Not every `Files` write method accepts an initial attributes parameter. In particular, `Files.newOutputStream(path, options...)` overloads take **OpenOption**, without a `FileAttribute<?>` varargs. If you need initial attributes applied and only use `newOutputStream`, you cannot pass extra `FileAttribute`s to a non-existent overload.

## 4. What Is FileAttribute<?>?

`java.nio.file.attribute.FileAttribute<T>` is an interface describing one attribute:

~~~java
public interface FileAttribute<T> {
    String name();
    T value();
}
~~~

This is an **illustrative API signature** (no need to redeclare the interface in your application). Names usually take the form `view-name:attribute-name`, such as `"posix:permissions"`. The corresponding attribute value has a Java type defined by that contract.

For POSIX permissions, Java provides a helper to construct `FileAttribute<Set<PosixFilePermission>>`:

~~~java
Set<PosixFilePermission> permissions =
        PosixFilePermissions.fromString("rw-------");
FileAttribute<Set<PosixFilePermission>> initial =
        PosixFilePermissions.asFileAttribute(permissions);
~~~

This is an illustrative snippet, with imports:

~~~java
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;
~~~

Most common tasks do not require writing your own `FileAttribute` implementation; using the official helper is clearer and reduces attribute name/type errors.

### 4.1. What Does the Varargs Parameter Mean?

A signature such as:

~~~java
Files.createFile(Path path, FileAttribute<?>... attrs)
~~~

allows passing **zero**, **one**, or **multiple** initial attributes (when valid and supported by the provider). Syntactically:

~~~java
Files.createFile(path);                 // No explicit attrs requested.
Files.createFile(path, permissionsAttr); // One initial attribute.
~~~

This is an illustrative snippet with `permissionsAttr` and `path` already defined. Attribute names can collide when supplied multiple times; per the `Files` method contracts, if a name appears multiple times, typically only the value of **the last occurrence** is used. However, passing duplicate attributes is a confusing design flaw; it is better to pass a single clearly determined final value.

Do not add arbitrary attributes without checking support: the rest may be completely valid, yet **a single unsupported attribute** causes the file creation call to fail.

## 5. POSIX Permissions: Three Groups and Three Actions

On filesystems supporting POSIX permissions, modes are typically represented as 9 characters:

~~~text
rwxrwxrwx
│││││││││
││││││└┴┴─ Other: read/write/execute
│││└┴┴──── Group: read/write/execute
└┴┴─────── Owner: read/write/execute
~~~

Positions corresponding to permissions:

| Group | Read | Write | Execute |
| --- | --- | --- | --- |
| Owner | `OWNER_READ` | `OWNER_WRITE` | `OWNER_EXECUTE` |
| Group | `GROUP_READ` | `GROUP_WRITE` | `GROUP_EXECUTE` |
| Others | `OTHERS_READ` | `OTHERS_WRITE` | `OTHERS_EXECUTE` |

In Java, each permission is a `PosixFilePermission` enum value. `Set<PosixFilePermission>` stores the selected permission set with no significant order.

Notation examples:

| Mode String | Meaning | Use Case |
| --- | --- | --- |
| `rw-------` | Owner read/write; group and others have no bits | Secret file or private data |
| `r--------` | Owner read-only | A read-only file after creation (consider content-writing needs) |
| `rw-r-----` | Owner read/write, group read | File shared within a controlled group |
| `rw-r--r--` | Owner read/write, group/others read | Public file on appropriate systems |
| `rwx------` | Owner read/write/traverse; other groups have none | Private directory |
| `rwxr-x---` | Owner full permissions; group read/traverse | Group-shared directory |

The `x` permission on a **directory** relates to **traversing** the path; it is not quite the same as executing an executable file. A directory whose owner only has `rw-------` without `x` can prevent the user from accessing entries inside under the POSIX model. Therefore file and directory modes should not be copied identically merely out of a desire for "privacy".

### 5.1. fromString and toString

`PosixFilePermissions.fromString(String)` converts a 9-character POSIX-syntax string into `Set<PosixFilePermission>`. `toString(Set<PosixFilePermission>)` converts back to a mode string, useful for printing/inspecting a permission set.

~~~java
Set<PosixFilePermission> p =
        PosixFilePermissions.fromString("rw-r-----");
System.out.println(PosixFilePermissions.toString(p));
~~~

Output:

~~~text
rw-r-----
~~~

This is an illustrative snippet requiring placement inside a method/class and imports as above. If the mode string has invalid length or characters, the API throws `IllegalArgumentException`.

## 6. Creating a New File with Initial Permissions

### 6.1. Standalone Java 17 Example: Creating a Private File

File **CreatePrivateFileDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class CreatePrivateFileDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("private-file-demo-");
        Path file = dir.resolve("private.txt");

        try {
            Set<PosixFilePermission> mode =
                    PosixFilePermissions.fromString("rw-------");
            FileAttribute<Set<PosixFilePermission>> initial =
                    PosixFilePermissions.asFileAttribute(mode);

            // This example requires a provider supporting POSIX permissions.
            Files.createFile(file, initial);

            Files.writeString(file, "secret", StandardCharsets.UTF_8);

            Set<PosixFilePermission> actual =
                    Files.getPosixFilePermissions(file);
            System.out.println("Readable text: " +
                    Files.readString(file, StandardCharsets.UTF_8));
            System.out.println("Requested mode: " +
                    PosixFilePermissions.toString(mode));
            System.out.println("Actual mode: " +
                    PosixFilePermissions.toString(actual));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Run command:

~~~bash
javac -encoding UTF-8 CreatePrivateFileDemo.java
java CreatePrivateFileDemo
~~~

Example output on a POSIX filesystem accepting the exact permission set without a permission-reducing policy:

~~~text
Readable text: secret
Requested mode: rw-------
Actual mode: rw-------
~~~

**Execution conditions:** This example is **not meant to run verbatim on every Windows/provider setup**; if the provider does not support POSIX attributes, the operation can throw `UnsupportedOperationException`. The `Actual mode` value must be **read back**, not assumed equal to the request across all filesystems. Policies such as umask, inherited permissions/ACLs, and providers can affect effective permissions.

We do not print the temporary path name (chosen randomly by the JVM), making the output predictable under the stated conditions.

### 6.2. Why Creating First and Setting Permissions Later Is Not Entirely Equivalent

The pattern:

~~~java
Files.createFile(path);
Files.setPosixFilePermissions(
        path, PosixFilePermissions.fromString("rw-------"));
~~~

is an illustrative snippet with **two separate filesystem operations**. Between creation and permission editing, the file may exist with the provider's default permissions, causing a **time window** during which the desired policy has not yet been applied. For sensitive data, this can be a security issue.

The preferred pattern on supporting POSIX providers:

~~~java
FileAttribute<Set<PosixFilePermission>> attrs =
        PosixFilePermissions.asFileAttribute(
                PosixFilePermissions.fromString("rw-------"));
Files.createFile(path, attrs);
~~~

helps request attributes **right at creation time**; per the contract of `Files.createFile`, checking non-existence and creating the file are atomic with respect to filesystem operations affecting the directory. Initial attributes are also set atomically at creation if supported by the provider. However, **this is not a multi-step transaction for all subsequent actions**, nor does it guarantee contents are durably flushed to disk.

## 7. Do Not Confuse "Requested Permissions" and "Actual Permissions"

There are at least three concepts:

1. **Requested permissions**: the `Set<PosixFilePermission>` requested by the program.
2. **Observed mode bits**: the permission set returned by `Files.getPosixFilePermissions(file)` after creation.
3. **Effective access**: what the application/user can actually do in practice, which also depends on effective groups, ACLs, OS policies, parent directories, and other factors.

On some POSIX systems, **umask** and OS/filesystem creation policies can make observed permissions **narrower** or different from expectations. Never assert unconditionally that `Files.createFile(..., attrs)` always creates every exact requested bit in every environment. Verify actual permissions if that is a **mandatory postcondition**.

For secret files, if appropriate effective permissions cannot be verified, the application should **refuse to process sensitive content** or choose a platform-appropriate protection mechanism, rather than skipping verification and writing data anyway.

### 7.1. Verifying Permissions After Creation

~~~java
Set<PosixFilePermission> actual =
        Files.getPosixFilePermissions(path);

Set<PosixFilePermission> expected =
        PosixFilePermissions.fromString("rw-------");

if (!actual.equals(expected)) {
    throw new IOException("File permissions do not match policy");
}
~~~

This is an illustrative snippet with `Path path`, required imports, and a POSIX environment. Comparing exact modes is an **example policy**, which may be too strict or insufficient for other applications. If the requirement is merely "none for group/others", verifying that those corresponding bits **are absent** may be more appropriate than strict equality.

Mode bits are not a complete security guarantee. A filesystem with different ACLs or dedicated sandbox mechanisms may require additional checks.

## 8. Creating Directories with Initial Permissions

For directories holding private data, a common requirement is `rwx------`: only the owner can list entries, create/delete (subject to parent permissions), and traverse into the directory.

~~~java
Set<PosixFilePermission> privateDirMode =
        PosixFilePermissions.fromString("rwx------");

FileAttribute<Set<PosixFilePermission>> dirAttrs =
        PosixFilePermissions.asFileAttribute(privateDirMode);

Files.createDirectory(path, dirAttrs);
~~~

This is an illustrative snippet requiring a non-existent `Path path` and a POSIX-supporting provider. `Files.createDirectory` creates **one** directory; it does not automatically create missing parent directories.

For nested directory chains:

~~~java
Files.createDirectories(path, dirAttrs);
~~~

`Files.createDirectories` creates missing directories; initial attributes apply to **directories actually created**. Already existing directories do not have their permissions changed simply for appearing in the path. Moreover, creating multiple directories **is not a single atomic transaction**: if an intermediate step fails, some parent directories may already have been created.

This is a key distinction when configuring security for an entire directory tree. If an ancestor directory is owned by another party or has broad permissions, setting permissions on a child directory does not by itself eliminate all path risks.

### 8.1. Java 17 Example: Creating a Private POSIX Directory with Support Check

Save **CreatePrivateDirectoryDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class CreatePrivateDirectoryDemo {
    public static void main(String[] args) throws IOException {
        Path parent = Files.createTempDirectory("private-dir-parent-");
        Path child = parent.resolve("private");

        try {
            FileStore store = Files.getFileStore(parent);
            if (!store.supportsFileAttributeView("posix")) {
                System.out.println("POSIX unsupported");
                return;
            }

            Set<PosixFilePermission> p =
                    PosixFilePermissions.fromString("rwx------");
            FileAttribute<Set<PosixFilePermission>> attr =
                    PosixFilePermissions.asFileAttribute(p);

            Files.createDirectory(child, attr);

            Set<PosixFilePermission> actual =
                    Files.getPosixFilePermissions(child);
            System.out.println("Created: " + Files.isDirectory(child));
            System.out.println("Owner access: " +
                    (actual.contains(PosixFilePermission.OWNER_READ)
                     && actual.contains(PosixFilePermission.OWNER_WRITE)
                     && actual.contains(PosixFilePermission.OWNER_EXECUTE)));
        } finally {
            Files.deleteIfExists(child);
            Files.deleteIfExists(parent);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CreatePrivateDirectoryDemo.java
java CreatePrivateDirectoryDemo
~~~

There are two intended outcomes:

~~~text
POSIX unsupported
~~~

or, on a POSIX environment allowing directory creation with the requested owner permissions:

~~~text
Created: true
Owner access: true
~~~

The example **does not silently downgrade security**: if the POSIX view is absent, it reports unsupported rather than creating the directory with unknown permissions and pretending it is equivalent. Even when `FileStore.supportsFileAttributeView("posix")` returns true, the creation operation can fail due to permissions, specific configurations, or unsupported initial attributes; the program lets the exception propagate rather than faking success.

## 9. Attributes When Creating Temporary Files

Temporary files do not mean "unimportant files". Random names prevent collisions, yet are **no substitute** for read/write access protection. If a temp file holds access tokens, medical data, unpublished exports, or keys, appropriate security policies must be applied.

NIO provides the overloads:

~~~java
Files.createTempFile(dir, "session-", ".tmp", attrs);
Files.createTempDirectory(dir, "private-", attrs);
~~~

This is an illustrative snippet with existing `Path dir` and `FileAttribute<?> attrs`. The API returns a `Path` to the **actually created** entry. Newly created entries differ from a pre-guessed filename string.

### 9.1. Java 17 Example: Temporary File with POSIX Requirements

Save **PrivateTempFileDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class PrivateTempFileDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("temp-policy-root-");
        Path temp = null;

        try {
            FileStore store = Files.getFileStore(root);
            if (!store.supportsFileAttributeView("posix")) {
                System.out.println("POSIX unsupported");
                return;
            }

            FileAttribute<Set<PosixFilePermission>> attr =
                    PosixFilePermissions.asFileAttribute(
                            PosixFilePermissions.fromString("rw-------"));

            temp = Files.createTempFile(root, "private-", ".txt", attr);
            Files.writeString(temp, "one", StandardCharsets.UTF_8);

            System.out.println("Exists: " + Files.isRegularFile(temp));
            System.out.println("Contents: " +
                    Files.readString(temp, StandardCharsets.UTF_8));
        } finally {
            if (temp != null) {
                Files.deleteIfExists(temp);
            }
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 PrivateTempFileDemo.java
java PrivateTempFileDemo
~~~

Expected outputs depending on provider:

~~~text
POSIX unsupported
~~~

or when the POSIX provider supports creation:

~~~text
Exists: true
Contents: one
~~~

The program does not print the random filename. `Files.createTempFile` assigns a unique name per contract, instead of the application concatenating `System.currentTimeMillis()` and assuming the name is safe. If the file must never leak, verify postconditions before writing sensitive content and ensure reliable cleanup.

### 9.2. Some Default Attributes May Already Differ from Files.createFile

Overloads creating **temporary files** may use different default attributes when `attrs` is omitted, depending on the provider—for instance, tending to be more restrictive on some systems. However, do not build security guarantees on the guess "temp is always private": when specific requirements exist, **pass appropriate attributes and verify** using supporting APIs/platforms.

## 10. Opening and Creating Immediately with Files.newByteChannel

`Files.newByteChannel(Path, Set<? extends OpenOption>, FileAttribute<?>... attrs)` allows declaring open options while also supplying attributes when the file needs to be newly created.

A pattern that creates a new file and strictly never overwrites:

~~~java
Set<OpenOption> options = Set.of(
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);

try (SeekableByteChannel channel =
        Files.newByteChannel(path, options, initialAttr)) {
    // Write bytes through the channel.
}
~~~

This is an illustrative snippet requiring `Path path`, `FileAttribute<?> initialAttr`, and imports `java.nio.channels.SeekableByteChannel`, `java.nio.file.Files`, `java.nio.file.OpenOption`, `java.nio.file.StandardOpenOption`, `java.util.Set`. The `CREATE_NEW` option requires the file **not exist yet**; checking for name collision and creation are bound to the same creation operation per contract. `WRITE` requests write access.

If the file **already exists**, `CREATE_NEW` causes the operation to fail; initial attrs are not used to modify permissions of an existing file. With `CREATE` on an existing file, `attrs` likewise does not automatically update existing permissions.

### 10.1. Java 17 Example: Creating a File and Writing Bytes with Initial Attributes

Save **CreateWithChannelDemo.java**:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.OpenOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class CreateWithChannelDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("channel-create-");
        Path file = dir.resolve("entry.txt");

        try {
            FileStore store = Files.getFileStore(dir);
            if (!store.supportsFileAttributeView("posix")) {
                System.out.println("POSIX unsupported");
                return;
            }

            FileAttribute<Set<PosixFilePermission>> attr =
                    PosixFilePermissions.asFileAttribute(
                            PosixFilePermissions.fromString("rw-------"));

            Set<OpenOption> options =
                    Set.of(StandardOpenOption.CREATE_NEW,
                           StandardOpenOption.WRITE);

            try (SeekableByteChannel channel =
                         Files.newByteChannel(file, options, attr)) {
                ByteBuffer bytes = ByteBuffer.wrap(
                        "hello".getBytes(StandardCharsets.UTF_8));
                while (bytes.hasRemaining()) {
                    channel.write(bytes);
                }
            }

            System.out.println("Text: " +
                    Files.readString(file, StandardCharsets.UTF_8));
            System.out.println("Bytes: " + Files.size(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CreateWithChannelDemo.java
java CreateWithChannelDemo
~~~

Result when the POSIX provider satisfies the request:

~~~text
Text: hello
Bytes: 5
~~~

Or:

~~~text
POSIX unsupported
~~~

**Why the `while (bytes.hasRemaining())` loop?** `SeekableByteChannel.write(ByteBuffer)` should not be assumed to write all remaining bytes in a single call on every implementation. Looping until the buffer is exhausted handles partial writes, though real applications also need to account for zero-progress or non-blocking channels depending on the actual channel type.

**Distinction from `Files.newOutputStream`:** stream overloads accept open options but have no initial attributes parameter. When you need to pass `FileAttribute<?>` together with open mode, `newByteChannel` is the direct NIO choice.

## 11. CREATE, CREATE_NEW, and Overwrite Risks

Two easily confused options:

- **`CREATE`**: if the file is missing, permits creation; if it already exists, may open the existing file according to the remaining options.
- **`CREATE_NEW`**: requires creating a new file; if the file already exists, the operation typically throws `FileAlreadyExistsException`. This requirement is especially useful when overwriting existing data must not be allowed.

Dangerous pattern:

~~~java
if (!Files.exists(path)) {
    Files.createFile(path, attrs);
}
~~~

This snippet has a race condition (*TOCTOU*). Between the check and the creation, another process can create the file. A passing pre-check does not guarantee the subsequent operation will succeed.

Better:

~~~java
try {
    Files.createFile(path, attrs);
} catch (FileAlreadyExistsException e) {
    // Arbitrate name collision: do not overwrite.
}
~~~

This is an illustrative snippet. `Files.createFile` already checks non-existence and creates atomically per contract with respect to directory-affecting filesystem operations.

**Note:** "Creating the file and setting initial attributes atomically" does not mean "writing all content, computing checksum, closing, and renaming" are all part of one transaction. For critical document updates, you must still design a workflow involving writing a temporary file, verifying, and replacing the target appropriately.

## 12. Checking Provider and View Before Using POSIX

Not every environment supports `PosixFilePermission`. For example, many Windows systems normally use ACLs per OS policy; trying to use `PosixFilePermissions` directly may be unsupported.

Two common checks:

~~~java
boolean posixSupported = Files.getFileStore(dir)
        .supportsFileAttributeView("posix");
~~~

or:

~~~java
boolean posixSupported =
        Files.getFileAttributeView(dir,
                PosixFileAttributeView.class) != null;
~~~

Both are illustrative snippets; `dir` is a `Path` of an existing directory. `FileStore.supportsFileAttributeView("posix")` queries the store's capability; `Files.getFileAttributeView` retrieves an available view for the current path and provider.

**Capability checks are not an absolute promise that the upcoming creation operation will always succeed.** Permissions, mount state, provider policies, and filesystem changes can still make the create call fail; always handle exceptions right at the operation.

### 12.1. What Should You Do When POSIX Is Unsupported?

Do not do:

~~~java
try {
    Files.createFile(path, posixAttrs);
} catch (UnsupportedOperationException ignored) {
    Files.createFile(path); // May weaken security requirements.
}
~~~

This is an **anti-pattern** if the goal is "the file must be readable only by the owner". Creating the file with defaults when POSIX policy cannot be applied can give the new file broader permissions than intended.

Better strategies:

1. **Halt and report unsupported** if the system mandates specific POSIX permissions.
2. **Design a dedicated policy for Windows/ACLs** using supporting APIs/providers, and verify effectiveness on the target OS.
3. **Use a pre-provisioned protected directory** per platform policy; do not infer that POSIX directory permissions equal ACLs on every other system.
4. **Choose storage matching sensitivity levels** (e.g., secrets vault, key management service, or policy-enforced environment), instead of trying to emulate `chmod` on every machine.
5. **Document application compatibility explicitly** in deployment docs and test on target filesystems.

If the data is non-sensitive and lacks strict permission requirements, a more portable behavior can be chosen. Yet that is a **business decision**, not a silent fallback after security enforcement fails.

## 13. A FileAttributeView May Exist Yet Not Be Settable at Creation

Example views:

| View | Common API | Purpose |
| --- | --- | --- |
| `BasicFileAttributeView` | `Files.readAttributes`, `Files.getLastModifiedTime` | Size, type, timestamps |
| `PosixFileAttributeView` | `Files.getPosixFilePermissions`, `Files.setPosixFilePermissions` | POSIX owner/group/mode |
| `DosFileAttributeView` | `Files.readAttributes(path, DosFileAttributes.class)`, `Files.setAttribute(path, "dos:hidden", ...)` | DOS read-only/hidden/archive/system |
| `AclFileAttributeView` | `Files.getFileAttributeView(path, AclFileAttributeView.class)` | Access control lists |
| `FileOwnerAttributeView` | `Files.getOwner`, `Files.setOwner` | Owner |

An API reading or updating a view **after creation** does not by itself prove the provider accepts that attribute inside the `FileAttribute<?>...` array passed at creation time.

For instance, `Files.setAttribute(path, "dos:hidden", true)` (if supported by the provider) is **an operation after the entry already exists**, which does not mean a custom-built `FileAttribute<Boolean>` named `"dos:hidden"` is guaranteed to be accepted during `Files.createFile`.

Similarly, requesting owner or ACL changes at creation time requires verifying the provider's contract/capabilities, and you must never assume every application is allowed to set the owner to someone else.

## 14. Practical Scenarios

### 14.1. Configuration File Containing Tokens

Requirement: file readable/writable only by owner on POSIX.

Sensible design:

1. Ensure the parent directory is owned by a trusted entity and does not allow external actors to rename entries.
2. Verify whether POSIX view/initial attributes are supported.
3. Create via `Files.createFile(path, posixAttr)` or `Files.newByteChannel(path, CREATE_NEW+WRITE, attr)`.
4. Re-read permissions and check postconditions before writing sensitive data if required by policy.
5. Manage writers/channels with `try-with-resources`, handling write/close errors.
6. Never overwrite an existing file using a name supplied by untrusted users.

### 14.2. Private Working Directory

Requirement: only the owner can list/traverse the directory.

On POSIX, request `rwx------` when calling `Files.createDirectory` or `Files.createTempDirectory`. Also inspect permissions of **the parent directory**, especially if the path sits in a shared area or comes from external input.

### 14.3. Group Report File

Requirement: owner read/write, group read.

`rw-r-----` is a potentially suitable POSIX mode set. However, the actual group of a file often depends on owner/group policies, directory setgid, and the filesystem; **setting the mode alone does not guarantee the file belongs to the right readable group**. When strict group sharing is required, verify both group ownership and effective permissions.

### 14.4. Read-Only File Immediately Upon Creation

`r--------` indicates owner read-only. However, if immediately after creation the program wants to write content via another stream, some write approaches may be disallowed; and file descriptors opened before permission changes can follow OS-specific rules.

Usually you should:
- Create the file privately for the writing process using suitable permissions (such as `rw-------`).
- Finish writing data and close resources properly.
- If business rules demand the final file be read-only, apply final permissions per explicit policy and accept that this is a separate step needing error management.
- If there is a requirement that "no permission window broader than policy ever exists", design appropriate provisioning/atomic publication.

"Owner read-only" and "program needs to write initial content" are two goals that must be coordinated, not simply solved by forcing the same mode across every phase.

## 15. Changing Attributes After Creation: Differences and Risks

Java can change permissions after creation:

~~~java
Files.setPosixFilePermissions(
        path, PosixFilePermissions.fromString("rw-------"));
~~~

or use a corresponding `FileAttributeView`. This is useful when administering existing files, or when changing permissions **after content writing finishes**.

Yet the two strategies differ:

~~~text
A. Initial attrs:
   Files.createFile(path, attrs)
   └─ Create new + request applying attrs at creation time

B. Post-creation update:
   Files.createFile(path)
   └─ File exists with default initial attributes
       └─ Files.setPosixFilePermissions(path, ...)
           └─ Time window exists between the two operations
~~~

If an application creates a file and then edits permissions, even when the two calls are consecutive on the same thread, another thread/process can observe the file in between. For data needing protection from the moment it appears, prefer initial attributes **when supported by the provider**.

For an existing file, `FileAttribute<?>` is not a tool to "edit mode" via `Files.createFile`: because `createFile` requires non-existence, it will fail on an existing entry. Choose dedicated attribute-setting APIs and evaluate access controls properly.

## 16. Common Errors and Related Exceptions

| Error/Scenario | Exception Type / Consequence | How to Handle |
| --- | --- | --- |
| Creating a file yet path already exists | Typically `FileAlreadyExistsException` | Do not overwrite blindly; resolve conflict |
| Parent directory does not exist | Possibly `NoSuchFileException` | Create parent per policy or report error |
| Lacking permission to create in parent directory | `AccessDeniedException` or other `IOException` | Report error/permissions; do not arbitrarily escalate privileges |
| Initial attribute unsupported | `UnsupportedOperationException` | Halt or take an approved provider-specific strategy |
| Invalid `null` argument | `NullPointerException` | Validate API inputs |
| Malformed POSIX permissions string | `IllegalArgumentException` | Validate exact 9 characters |
| Multiple attrs with the same name | Contract uses the last value | Avoid passing duplicate names |
| Creating multiple directories with `createDirectories` then failing midway | Some parent directories already created | Handle cleanup/rollback per business logic |
| File created with attrs, yet writing content fails | Empty or incomplete file may remain | Clean up/stage/replace in a controlled way |
| Post-creation mode check differs from request | OS/provider policy altered effective permissions | Do not treat the security task as successful |
| Checking `Files.exists` before `createFile` | TOCTOU, name collision still possible | Rely on create operation and catch errors |
| Creating `Path` inside an area with unintended symbolic links | May point to a different location | Control parent directories, ownership, symlinks, and races |

**Do not classify errors by OS message strings** such as `"Permission denied"` because messages depend on OS/provider and can change. Catch appropriate `IOException` subclasses, preserve `cause`, and log operations/paths safely.

### 16.1. When Is It IOException, When Is It UnsupportedOperationException?

`IOException` is a checked exception for I/O errors, such as missing paths or device failures. `UnsupportedOperationException` is an unchecked exception typically indicating the provider does not support the requested option/attribute.

If an application has a mandatory POSIX permission policy, `UnsupportedOperationException` is **a failure to satisfy requirements**, not an excuse to create a broadly accessible file "just to finish".

Also note `SecurityException` in environments with corresponding access control mechanisms; it is not an `IOException`.

## 17. Testing Properly Across Different Filesystems

Not every Windows environment is alike; nor is every directory on a Linux machine on the same filesystem/provider. There may be NTFS, FAT, tmpfs, network mounts, ZIP filesystems, or custom providers.

A testing strategy:

1. Create a test directory inside **the exact filesystem region** the application will use.
2. Check `FileStore`/`FileAttributeView` support when critical.
3. Create new files with `FileAttribute<?>` per policy.
4. Re-read attributes after creation; do not merely check `Files.exists`.
5. Verify files are not overwritten if the path already exists.
6. Test insufficient permissions and other limits using controlled fixtures without altering permissions on real data.
7. Test content-write failures to see whether partial files are left behind.
8. Verify cleanup works on the target filesystem.
9. Do not assume setting a 9-character mode fully describes Windows ACLs.

### 17.1. Checking Attributes by Security Invariants

For a policy "group and others **must have no mode permissions**", you can inspect elements in the set:

~~~java
Set<PosixFilePermission> actual =
        Files.getPosixFilePermissions(path);

boolean restricted =
        !actual.contains(PosixFilePermission.GROUP_READ)
        && !actual.contains(PosixFilePermission.GROUP_WRITE)
        && !actual.contains(PosixFilePermission.GROUP_EXECUTE)
        && !actual.contains(PosixFilePermission.OTHERS_READ)
        && !actual.contains(PosixFilePermission.OTHERS_WRITE)
        && !actual.contains(PosixFilePermission.OTHERS_EXECUTE);
~~~

This is an illustrative snippet, not a standalone program. This **mode-bit invariant** is a concrete check, yet does not by itself prove all effective permissions if ACLs/privileges/other OS rules exist. When security requirements are high, evaluate on the actual filesystem and application permission model.

### 17.2. Avoid Testing with Fixed Names in User Directories

Do not pick a name like `"test.txt"` in the working directory, delete the file if it exists, and run tests: that can delete another user's or application's data. Use `Files.createTempDirectory` to create an isolated test sandbox, perform operations inside, and delete **only the entries created by the test**.

## 18. Choosing the Right Solution for Each Need

| Need | Sensible Choice |
| --- | --- |
| Create new file, no overwrite, with POSIX mode | `Files.createFile(path, PosixFilePermissions.asFileAttribute(...))` |
| Create private directory | `Files.createDirectory(path, attrs)` or `createTempDirectory(..., attrs)` |
| Create multiple missing parent directories | `Files.createDirectories(path, attrs)`; remember whole-tree atomicity is not guaranteed |
| Create and immediately open byte channel to write with attrs | `Files.newByteChannel(path, Set.of(CREATE_NEW, WRITE), attrs)` |
| Create temp file with specific permissions | `Files.createTempFile(dir, prefix, suffix, attrs)` |
| Set permissions of an existing file | `Files.setPosixFilePermissions(path, permissions)` |
| Need ACLs on a non-POSIX filesystem | Explore `AclFileAttributeView`/provider and deployment policies |
| Only need a new file with default permissions, no special policy | `Files.createFile(path)` or appropriate creation overload |
| Need to prevent "already exists" races | `Files.createFile` or `CREATE_NEW`, never `exists` followed by create |
| Need to prevent data loss on write failures | Write temp file / close / verify / replace per policy; initial attrs only address part of the lifecycle |

## 19. Common Misconceptions

**Misconception 1: `FileAttribute<?>` is a way to change permissions after a file is already opened.**

No. It describes **initial attributes** in creation overloads that support them. For existing entries, use the corresponding `set...` APIs if allowed by the system.

**Misconception 2: Simply calling `Files.createFile(path)` followed immediately by `Files.setPosixFilePermissions` is completely atomic.**

No. Two separate calls create an observable time window. If policy mandates the mode immediately upon appearance, use an overload accepting `attrs` on a supporting provider.

**Misconception 3: `CREATE_NEW` itself means private file permissions.**

No. It specifies non-overwriting creation. File permissions are determined by initial attributes and filesystem policies.

**Misconception 4: A 9-character POSIX mode works identically on all Windows, ZIP, and network filesystems.**

No. Supported views depend on the provider. Windows typically relies on ACLs/NTFS; POSIX mode is not a universal permission model across every environment.

**Misconception 5: If the provider does not support `attrs`, simply omit `attrs` and create a default file—it's equally secure.**

Uncertain and potentially dangerous. For sensitive files, refuse or use a security approach verified for that platform.

**Misconception 6: Setting initial attrs successfully means content has been safely written.**

No. File creation, writing data, closing, syncing, and publishing results are distinct concerns. Critical updates must design the entire lifecycle.

**Misconception 7: Having POSIX owner-only permissions guarantees no one else can access the file under any circumstances.**

No. Effective permissions also depend on ACLs, OS privileges, parent directory permissions, and system security models. Only make claims within what you have verified.

## 20. Self-Check Questions

**Question 1.** What is the difference between `Files.createFile(path, attrs)` and `Files.setPosixFilePermissions(path, perms)`?

**Answer:** the first creates a new file and requests attributes right at creation time; the second modifies permissions of an existing entry. Creating first and modifying later can leave a time window with unintended permissions.

**Question 2.** What is `FileAttribute<Set<PosixFilePermission>>` used for?

**Answer:** it is a typed attribute name/value object passed to creation methods having a `FileAttribute<?>...` parameter. `PosixFilePermissions.asFileAttribute(...)` creates an appropriate value for POSIX permissions.

**Question 3.** What is mode `rw-------`?

**Answer:** owner read and write; group/others are granted no bits in the POSIX mode. It does not by itself tell the whole story about ACLs or other privileges.

**Question 4.** For a private directory, is `rw-------` appropriate for a directory needing traversal?

**Answer:** usually no. A directory needs `x` permission for traversal in the POSIX model; `rwx------` is the typical pattern when only the owner needs access.

**Question 5.** Does passing `attrs` to `Files.createDirectories` automatically change permissions of already-existing parent directories?

**Answer:** no. They apply to newly created directories per contract, without updating existing entries. Also, creating multiple levels is not a single transaction.

**Question 6.** If using a filesystem that does not support POSIX, should you catch `UnsupportedOperationException` and create the file without `attrs`?

**Answer:** only when business policy permits and default permissions are understood. If owner-only is a mandatory security standard, do not fall back silently.

**Question 7.** When using `Files.newByteChannel(path, Set.of(CREATE, WRITE), attrs)` on an existing file, does `attrs` automatically change the existing file's mode?

**Answer:** no. Initial attributes are only used when **actually creating anew**. Opening an existing file is not a permission-editing request.

**Question 8.** Why should `CREATE_NEW` be used when overwriting must be prevented?

**Answer:** it requires creation and rejects if already existing per contract, avoiding the `Files.exists` check-then-create pattern that causes TOCTOU.

**Question 9.** For a sensitive file, is checking `Files.exists(file)` after creation enough?

**Answer:** not yet. You must verify permissions, ownership/ACLs per policy, successful write/close, and related safety conditions.

### Practice Exercises

1. Write a program that creates a file via `Files.createFile` with `rw-------`, reads it back using `Files.getPosixFilePermissions`, and prints via `PosixFilePermissions.toString`. If the provider does not support it, report clearly and do not create sensitive data.
2. Create a directory with `rwx------` via `Files.createDirectory`. Try creating a file inside and then delete both at the end of the program.
3. Use `Files.createTempFile` with initial attrs; verify results without relying on the random filename.
4. Use `Files.newByteChannel` with `CREATE_NEW` + `WRITE` + attrs, write 5 UTF-8 bytes, and check the size.
5. Try creating the same path again with `Files.createFile` to observe `FileAlreadyExistsException`; do not delete the original file when testing.
6. Apply a group policy `rw-r-----` and investigate why the file's actual group also needs to be checked.
7. Create a subdirectory using `Files.createDirectories`, compare permissions of the existing directory and the newly created directory; do not assume the old directory's permissions change.
8. Design handling branches for Windows/ACL and POSIX without bypassing security constraints, documenting support capabilities before deployment.

## 21. Conclusion

- **`FileAttribute<?>`** is how initial attributes are expressed when creating entries through supporting `Files` overloads.
- **`Files.createFile(path, attrs)`** and **`Files.createDirectory(path, attrs)`** allow requesting attributes at creation time; `Files.createDirectories` applies attrs to new entries without modifying existing ones.
- **`PosixFilePermissions.fromString`** and **`asFileAttribute`** form a concise toolkit for constructing POSIX permission requests; mode `rw-------` is commonly used for private files, `rwx------` for private directories.
- **Creating with attrs differs from "create then chmod".** When supported by the provider, setting attributes at creation limits default-permission race windows.
- **Providers determine support and effective permissions.** Do not assume every filesystem understands POSIX, ACLs, or metadata identically; check and fail if policy cannot be satisfied.
- **`CREATE_NEW` prevents overwriting**, while `CREATE` does not alter attributes of an existing file.
- **Creating with the right permissions is not sufficient for comprehensive safety.** You still need to manage write streams, closing, partial failures, data syncing, and path validation.

### Java SE 17 References

- [Files.createFile / createDirectory / createDirectories / createTempFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Files.newByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newByteChannel(java.nio.file.Path,java.util.Set,java.nio.file.attribute.FileAttribute...))
- [FileAttribute](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileAttribute.html)
- [PosixFilePermissions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html)
- [PosixFilePermission](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermission.html)
- [FileStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html)
- [StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [PosixFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html)
- [AclFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html)
