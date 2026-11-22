# Owner, UserPrincipal, and AclFileAttributeView in Java NIO.2

## 1. Lesson Objectives

When reading/writing files, besides byte contents and paths, the filesystem also stores **attributes** such as owner and access rules. Java NIO.2 provides APIs to look up users/groups and, on supporting systems, read or update Access Control Lists (**ACLs**).

Three central concepts:

- **Owner**: an identity recorded by the filesystem as the owner of a file/directory. In Java, owner is represented via `UserPrincipal`.
- **`UserPrincipal`**: an interface describing a user identity, with method `getName()`. `GroupPrincipal` extends `UserPrincipal` for group identities; real identities are managed by the filesystem/provider/OS.
- **`AclFileAttributeView`**: an NIO.2 interface used to read/modify ordered ACLs and work with the owner when the filesystem supports the corresponding permission model.

After this lesson, you will know how to:

1. Read the owner with `Files.getOwner(path)`, distinguishing read operations from changing the owner.
2. Look up identities using `UserPrincipalLookupService` and understand why a display name is insufficient to confirm the same account.
3. Check ACL support before calling `getAcl()`/`setAcl()`.
4. Analyze `AclEntry`: principal, entry type, permissions, inheritance flags, ordering.
5. Distinguish ACLs from POSIX permissions (`rwx`), DOS attributes, and effective access permissions of a process.
6. Handle `IOException`, `UnsupportedOperationException`, `SecurityException`, provider differences, symbolic links, and race conditions.
7. Write Java 17+ code that reads metadata safely while avoiding accidental permission changes to real files.

> **Key mindset:** being able to read the owner **does not prove** the current runner can read/write the file; reading an ACL **does not mean** you have fully computed effective permissions; and `setAcl()`/`setOwner()` are risky permission-mutating operations requiring clear policies.

## 2. What Is an Owner?

Owner is typically the identity a filesystem associates with a file object. On Unix/POSIX systems, a file has a user owner and a group owner; on Windows, owner and DACL are concepts within the security descriptor. Java provides a common abstraction, while **administrative rules and effective permissions are decided by the operating system and filesystem**.

Notes:

- Owner is not synonymous with original author or creator forever; ownership can be changed according to system policies.
- Being the owner does not mean automatically having all read/write/delete permissions.
- `UserPrincipal.getName()` is a **provider-specific identity name**, not a global key usable across Windows, Linux, and all account domains.
- ACLs may grant/deny permissions to principals other than the owner; groups and administrative privileges can participate in permission evaluation.
- A file may be a symlink, and the owner attribute of **the link** can differ from the owner of **the target**, depending on support and link-following options.

### 2.1. Key APIs

| Goal | API | Result / Limitation |
| --- | --- | --- |
| Read owner | `Files.getOwner(path)` | `UserPrincipal`; follows symbolic links by default |
| Read link owner (when supported) | `Files.getOwner(path, NOFOLLOW_LINKS)` | Depends on provider/link semantics |
| Set owner | `Files.setOwner(path, principal)` | Modifies metadata; requires appropriate privileges |
| Obtain owner view | `Files.getFileAttributeView(path, FileOwnerAttributeView.class)` | May return `null` if the view is unsupported |
| Obtain ACL view | `Files.getFileAttributeView(path, AclFileAttributeView.class)` | May return `null` |
| Read ACL | `view.getAcl()` | Ordered `List<AclEntry>` |
| Write ACL | `view.setAcl(entries)` | Replaces the ACL list; risk of losing access if done wrong |
| Read owner from ACL view | `view.getOwner()` | `AclFileAttributeView` extends `FileOwnerAttributeView` |
| Look up accounts | `FileSystem.getUserPrincipalLookupService()` | `lookupPrincipalByName` or `lookupPrincipalByGroupName` |
| POSIX owner/group/mode | `PosixFileAttributeView` and `Files.readAttributes(..., PosixFileAttributes.class)` | Only on filesystems supporting POSIX |

`Files.getOwner` and `Files.setOwner` may use the `FileOwnerAttributeView` mechanism per provider. When a feature is unsupported, do not force the provider to synthesize fake info; detect and handle it properly.

## 3. `UserPrincipal` and `GroupPrincipal`

`java.nio.file.attribute.UserPrincipal` is an interface extending `java.security.Principal`. The key method is:

```java
String displayName = principal.getName();
```

Identities may originate from a distinct user/group system: local accounts, domains, a remote filesystem, or a provider-implemented model. **Do not infer** real identity by comparing display name strings with free-form user input.

`GroupPrincipal` is a subtype of `UserPrincipal` used for **groups**. An ACL entry may point to a user principal or a group principal depending on the filesystem.

### 3.1. Looking Up Principals with `UserPrincipalLookupService`

On systems with an appropriate lookup service:

```java
// Illustrative API; account names must come from trusted configuration.
UserPrincipalLookupService lookup =
        path.getFileSystem().getUserPrincipalLookupService();

UserPrincipal user = lookup.lookupPrincipalByName("example-user");
GroupPrincipal group = lookup.lookupPrincipalByGroupName("example-group");
```

**This snippet is not a standalone program**: it requires `import java.nio.file.Path;`, `java.nio.file.attribute.*;`, a valid `path` variable, and accounts that **actually exist in the provider**.

Points to remember:

- `lookupPrincipalByName` and `lookupPrincipalByGroupName` can throw `UserPrincipalNotFoundException` if the identity is not found.
- `IOException` can occur on lookup failures, or `SecurityException` if the environment enforces corresponding security policies.
- Account names are interpreted by the system/provider; `"admin"` or `"Everyone"` do not have universal meaning.
- **Do not pass `() -> "somebody"` as a principal object to `Files.setOwner` on a real filesystem.** Providers may require a principal created/looked up by the provider itself, or disallow assignment.
- `getName()` only provides a name representation; correctness of permission assignment relies on a principal accepted by the provider.

### 3.2. Distinguishing "Knowing a Name", "Knowing an Identity", and "Having Permission"

| Statement | Can Be Concluded from `getName()` Alone? |
| --- | --- |
| Provider returned an identity name | Yes |
| This principal is the same account across two different machines | No |
| Principal definitely has permission to read the file | No |
| ACL rules are enforced on the current filesystem | No |
| The application itself has permission to change owner/ACL | No |
| User and group with similar names are the same principal kind | No |

Avoid storing only a name string for reuse across multiple systems when the program requires identity accuracy.

## 4. Reading Owner with `Files.getOwner`

API example:

```java
Path file = Path.of("data", "report.txt");
UserPrincipal owner = Files.getOwner(file);
System.out.println(owner.getName());
```

This is an **illustrative snippet**, not a standalone program because it lacks imports and the file might not exist yet. The result is a provider-specific principal name, **with no fixed stdout**.

Reading owner can encounter:

1. `NoSuchFileException` if the path does not exist.
2. `AccessDeniedException` or `IOException` when the filesystem disallows reading the attribute.
3. `UnsupportedOperationException` when the provider does not support owner attributes for that call.
4. `SecurityException` if a corresponding security policy applies.
5. Unexpected changes if another process modifies/renames the file between check and read.

### 4.1. Symlinks: Follow Target or Read Link Attribute?

Normally `Files.getOwner(path)` follows symbolic links. If you want to work with the link object itself:

```java
UserPrincipal linkOwner = Files.getOwner(
        path, LinkOption.NOFOLLOW_LINKS);
```

However, **not every provider supports the same semantics** for symlink ownership. The operation may be unsupported; test on the deployment environment. `NOFOLLOW_LINKS` does not lock the symlink to prevent concurrent changes (TOCTOU).

### 4.2. Reading Owner from `FileOwnerAttributeView`

`FileOwnerAttributeView` allows getting/setting owner via an attribute view:

```java
FileOwnerAttributeView view = Files.getFileAttributeView(
        path, FileOwnerAttributeView.class);

if (view == null) {
    throw new UnsupportedOperationException(
            "Owner view unavailable");
}
UserPrincipal owner = view.getOwner();
```

This is an illustrative snippet. The advantage of `view` is interacting with filesystem attributes through a well-defined interface. If `view` is `null`, do not call `getOwner()` on it.

## 5. What Is an ACL? Why Does It Differ from `rwx` Permissions?

An **ACL (Access Control List)** is a list of access rules attached to an object. Each rule typically specifies:

- **Principal**: who is referenced (user or group).
- **Type**: allow, deny, or audit/alarm info per ACL model.
- **Permissions**: actions such as reading data, writing data, reading ACL, changing owner.
- **Flags**: inheritance rules or scope of application.

An **illustrative** example, not claiming to be a real ACL on a specific system:

```text
Entry 1: ALLOW team-editors → READ_DATA, WRITE_DATA
Entry 2: DENY  guest        → WRITE_DATA
Entry 3: ALLOW owner        → READ_DATA, READ_ACL
```

Do not treat an ACL as an unordered set of permissions. **The list is ordered** and entry order can affect how the system evaluates them. Effective permission evaluation also involves group tokens, inheritance, privileges, policies, and the filesystem.

### 5.1. POSIX Mode and ACL View Are Not Identical

On Unix/POSIX, basic permissions are typically expressed via the three `owner/group/others` groups and `rwx` bits. Java provides:

```java
PosixFileAttributes attributes = Files.readAttributes(
        path, PosixFileAttributes.class);
Set<PosixFilePermission> mode = attributes.permissions();
```

This is an illustrative snippet requiring a POSIX-supporting filesystem; it does not run on every Windows filesystem.

`AclFileAttributeView` targets a richer ACL model, typically associated with filesystems having NFSv4/Windows-compatible ACLs. **Do not assume** every POSIX filesystem has `AclFileAttributeView`, nor that POSIX-style ACLs are fully represented by Java's `AclFileAttributeView` by default. A filesystem may provide owner/POSIX views yet **not** provide an ACL view.

### 5.2. Different from DOS Attributes

`DosFileAttributeView` has flags such as read-only, hidden, system, and archive, not a list of user/group ACEs. The read-only flag does not replace ACL or POSIX permission analysis, and `Files.isReadable`/`isWritable` are only point-in-time accessibility checks.

## 6. `AclFileAttributeView`: Support and API

Obtain the view using:

```java
AclFileAttributeView view = Files.getFileAttributeView(
        path, AclFileAttributeView.class);
```

If the provider does not support ACLs for the path, `view` may be **`null`**. This check is necessary before calling `view.getAcl()`. If the view exists yet the operation fails due to permissions or I/O errors, exceptions can still be thrown.

Main components:

| API | Role |
| --- | --- |
| `AclFileAttributeView` | ACL and owner attribute view |
| `AclFileAttributeView.getAcl()` | Reads ordered `List<AclEntry>` |
| `AclFileAttributeView.setAcl(List<AclEntry>)` | Sets **the entire ACL list** as requested |
| `AclFileAttributeView.getOwner()` | Reads owner |
| `AclFileAttributeView.setOwner(UserPrincipal)` | Changes owner per privileges/provider |
| `AclEntry` | One ACL rule, usually having principal, type, permissions, flags |
| `AclEntryType` | `ALLOW`, `DENY`, `AUDIT`, `ALARM` |
| `AclEntryPermission` | Actions such as `READ_DATA`, `WRITE_DATA`, `READ_ACL`, `WRITE_ACL`, `WRITE_OWNER` |
| `AclEntryFlag` | Flags on how ACEs are inherited on directories/children |
| `UserPrincipalLookupService` | Finds identities understood by the provider |

`getAcl()` returns a list representing the ACL, which may be empty on some files/providers. **Do not re-sort by username**; entry order can be significant when evaluating permissions.

### 6.1. Reading the ACL List

Illustrative code snippet:

```java
AclFileAttributeView view =
        Files.getFileAttributeView(path, AclFileAttributeView.class);

if (view != null) {
    List<AclEntry> entries = view.getAcl();
    for (int i = 0; i < entries.size(); i++) {
        AclEntry entry = entries.get(i);
        System.out.println(i + " " + entry.type()
                + " principal=" + entry.principal().getName()
                + " permissions=" + entry.permissions()
                + " flags=" + entry.flags());
    }
}
```

This is **not a standalone runnable class** because imports and `path` are not declared. Output depends on the actual ACL and has no universal stdout.

Do not log sensitive ACL lists to public destinations. In real programs, restrict access to ACL inspection features and handle errors per file.

### 6.2. Checking Support via `FileStore`

`FileStore.supportsFileAttributeView(AclFileAttributeView.class)` signals file store support capability, for example:

```java
boolean storeSaysAcl = Files.getFileStore(path)
        .supportsFileAttributeView(AclFileAttributeView.class);
```

This is an illustrative snippet (requiring imports and `path`). It is not a guarantee that **every path/operation** grants permission to read or edit ACLs; checking the concrete view, invoking the actual operation, and catching exceptions remain mandatory. `getFileStore` itself can also throw `IOException`.

## 7. What Does `AclEntry` Contain?

An entry has immutable properties:

- `entry.principal()` — the affected identity.
- `entry.type()` — type (allow/deny/audit/alarm).
- `entry.permissions()` — set of `AclEntryPermission`.
- `entry.flags()` — set of `AclEntryFlag`.

### 7.1. ACL Entry Types

| `AclEntryType` | General Meaning |
| --- | --- |
| `ALLOW` | Rule granting the specified permissions |
| `DENY` | Rule denying the specified permissions |
| `AUDIT` | Rule related to logging accesses per policy |
| `ALARM` | Rule related to signaling/alerting accesses per policy |

How audit/alarm are enforced and support for each entry type depend on the platform/provider. Do not treat being able to construct an `AclEntry` object in memory as proof the filesystem will accept `setAcl` with that entry.

### 7.2. Common Permissions

| Permission | Target by Context |
| --- | --- |
| `READ_DATA` / `LIST_DIRECTORY` | Read file data or list directory contents |
| `WRITE_DATA` / `ADD_FILE` | Write file data or add a file in a directory |
| `APPEND_DATA` / `ADD_SUBDIRECTORY` | Append file data or add a subdirectory |
| `READ_NAMED_ATTRS` | Read named attributes |
| `WRITE_NAMED_ATTRS` | Write named attributes |
| `EXECUTE` | Execute a file or traverse a directory per filesystem semantics |
| `DELETE` | Delete the object |
| `DELETE_CHILD` | Delete a child entry in a directory |
| `READ_ATTRIBUTES` / `WRITE_ATTRIBUTES` | Read/write basic attributes |
| `READ_ACL` / `WRITE_ACL` | Read/write the ACL list |
| `WRITE_OWNER` | Change owner information |
| `SYNCHRONIZE` | Synchronize access capability per ACL model |

Several permission name pairs are **aliases/object-type-specific usages** in Java; for instance, `READ_DATA` and `LIST_DIRECTORY` describe the same underlying bit with different meanings for files vs. directories. Do not invent a "each name is an independent bit" model when the API declares them equivalent.

### 7.3. Inheritance Flags

| Flag | General Role |
| --- | --- |
| `FILE_INHERIT` | Rule can be inherited by child files |
| `DIRECTORY_INHERIT` | Rule can be inherited by child directories |
| `NO_PROPAGATE_INHERIT` | Restricts propagation depth of inheritance |
| `INHERIT_ONLY` | Entry is for inheritance only, not applied directly to the current object per appropriate semantics |

Do not infer from flag names that every filesystem implements inheritance identically. In particular, **inherited ACLs** from parent directories can introduce new ACEs when files are created, depending on system policies.

## 8. Complete Java 17+: Creating an Illustrative `AclEntry` in Memory

This example **does not modify real ACLs**. It uses a mock `UserPrincipal` solely to study the object model. `AclEntry` itself is built via the builder; it does not open the filesystem.

Save to file **`AclEntryModelDemo.java`**:

```java
import java.nio.file.attribute.AclEntry;
import java.nio.file.attribute.AclEntryPermission;
import java.nio.file.attribute.AclEntryType;
import java.nio.file.attribute.UserPrincipal;

public class AclEntryModelDemo {
    public static void main(String[] args) {
        // Demo principal only; never pass it to Files.setOwner.
        UserPrincipal demo = () -> "demo-user";

        AclEntry entry = AclEntry.newBuilder()
                .setType(AclEntryType.ALLOW)
                .setPrincipal(demo)
                .setPermissions(
                        AclEntryPermission.READ_DATA,
                        AclEntryPermission.READ_ACL)
                .build();

        System.out.println("Type: " + entry.type());
        System.out.println("Principal: "
                + entry.principal().getName());
        System.out.println("Can read data: "
                + entry.permissions().contains(
                        AclEntryPermission.READ_DATA));
        System.out.println("Can write ACL: "
                + entry.permissions().contains(
                        AclEntryPermission.WRITE_ACL));
        System.out.println("Has inheritance flags: "
                + !entry.flags().isEmpty());
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 AclEntryModelDemo.java
java AclEntryModelDemo
```

**Exact stdout:**

```text
Type: ALLOW
Principal: demo-user
Can read data: true
Can write ACL: false
Has inheritance flags: false
```

**Explanation:**

1. `demo` is a custom `UserPrincipal` with a fixed name; it is only for demonstrating the in-RAM data model.
2. The builder assigns type `ALLOW` and permissions `READ_DATA`, `READ_ACL`.
3. `WRITE_ACL` was not added, so checking membership for that permission returns `false`.
4. `setFlags` was not called; the flags set is empty.
5. **No file had permissions granted**. This entry is merely a Java object; applying a real ACL requires a supporting view, a valid principal accepted by the provider, and ACL modification privileges for the caller.

Do not interpret `Can read data: true` as "the current process has permission to read a file": it only states that **the mock entry contains the `READ_DATA` bit**.

## 9. Complete Java 17+: Inspecting Real Owner and ACL in Read-Only Mode

The example below **does not change owner/ACL**. The program only observes a user-specified path. If no path is provided, it prints usage instructions and avoids scanning directories on its own.

Save as **`OwnerAclInspect.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.AclEntry;
import java.nio.file.attribute.AclFileAttributeView;
import java.nio.file.attribute.FileOwnerAttributeView;
import java.nio.file.attribute.UserPrincipal;
import java.util.List;

public class OwnerAclInspect {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.out.println("Usage: java OwnerAclInspect <path>");
            return;
        }

        Path path = Path.of(args[0]);
        try {
            FileOwnerAttributeView ownerView =
                    Files.getFileAttributeView(
                            path, FileOwnerAttributeView.class);

            if (ownerView == null) {
                System.out.println("Owner view: unsupported");
            } else {
                UserPrincipal owner = ownerView.getOwner();
                System.out.println("Owner: " + owner.getName());
            }

            AclFileAttributeView aclView =
                    Files.getFileAttributeView(
                            path, AclFileAttributeView.class);

            if (aclView == null) {
                System.out.println("ACL view: unsupported");
                return;
            }

            List<AclEntry> entries = aclView.getAcl();
            System.out.println("ACL entries: " + entries.size());

            for (int index = 0; index < entries.size(); index++) {
                AclEntry entry = entries.get(index);
                System.out.println(index + ": "
                        + entry.type()
                        + " principal=" + entry.principal().getName()
                        + " permissions=" + entry.permissions()
                        + " flags=" + entry.flags());
            }
        } catch (IOException failure) {
            System.err.println("I/O error: "
                    + failure.getClass().getSimpleName());
        } catch (UnsupportedOperationException failure) {
            System.err.println("Unsupported view operation");
        } catch (SecurityException failure) {
            System.err.println("Security policy denied operation");
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 OwnerAclInspect.java
java OwnerAclInspect
java OwnerAclInspect my-file.txt
```

With **no arguments**, deterministic stdout is:

```text
Usage: java OwnerAclInspect <path>
```

With `java OwnerAclInspect my-file.txt`, **there is no single universal fixed stdout**: the path may not exist, owners differ, the ACL view may be unsupported, entry counts/rules vary, or permission errors may occur. This is expected behavior for filesystem-dependent APIs.

**Learning points:**

- Check `ownerView == null` and `aclView == null` before calling methods.
- Call `getAcl()` only when the ACL view is present.
- Print `entry.type()`, principal, permissions, and flags in the exact order from `List`; the code **does not sort or alter the ACL**.
- Distinguish I/O errors, unsupported views, and security policies.
- Never call `Files.setOwner`, `view.setOwner`, or `view.setAcl`; this is an example usable for studying metadata safely in **read-only** mode.
- For symlink paths, attribute view calls typically follow links by default. If you want to inspect the link itself, consider overloads with `LinkOption.NOFOLLOW_LINKS` and actual support.

## 10. Changing Owner with `Files.setOwner` — When Should You Do It?

API:

```java
Files.setOwner(path, principal);
```

This is an operation that **changes security metadata**, not a "set display name for a file" command. When permitted by the provider, the caller must hold the necessary privileges. The assigned owner should be a `UserPrincipal` appropriate for the path's filesystem/provider.

Controlled workflow:

1. Pick a test file in an area **owned by you**, not system configuration files or critical data.
2. Verify whether the provider/owner view supports it.
3. Look up the target identity via the same filesystem's `UserPrincipalLookupService` (if needed).
4. Validate the target account against organizational policy; do not accept an arbitrary name from a request to grant ownership.
5. Call `Files.setOwner` while handling `IOException`, `UnsupportedOperationException`, and `SecurityException`.
6. Re-read `Files.getOwner` and evaluate by identity/provider, not display name alone.
7. Record an audit log of who requested it, which file, and the permission change result.

**Use the snippet below only as API structure; do not execute on real files without authorization and controlled procedures:**

```java
// Illustrative: path and trustedUserName are provided by the authenticated application.
var lookup = path.getFileSystem().getUserPrincipalLookupService();
var newOwner = lookup.lookupPrincipalByName(trustedUserName);
Files.setOwner(path, newOwner);
```

This is a **non-standalone illustrative snippet**; do not infer usernames to assign from untrusted external data. It does not create new users: principal lookup is lookup, not account provisioning.

### 10.1. Changing Owner Does Not Automatically Grant Read/Write Permission

After changing the owner, existing ACL entries may remain; POSIX modes/groups and system policies also apply. Do not assume `setOwner` replaces `setAcl` or vice versa. If you need "user X has permission Y", construct an explicit permission policy and verify it appropriately for the provider, rather than only changing the owner.

## 11. Changing ACLs with `setAcl`: Risks and Safe Workflow

API:

```java
view.setAcl(entries);
```

This **is not a simple append-one-ACL-line operation**. It asks the provider to apply **a new list of entries** per the view contract. If you build a list with just one ACE and call `setAcl`, you can accidentally wipe out existing permissions or lock yourself out of the resource.

### 11.1. Controlled Workflow (Do Not Run Blindly on Real Files)

1. Verify `AclFileAttributeView` support and that the caller has permission to modify ACLs.
2. Read the **entire** existing list via `getAcl()`; note ordering, principals, flags, and permissions.
3. Determine the exact edits required by business logic; avoid "sorting" the list yourself or dropping unfamiliar ACEs.
4. Look up proper `UserPrincipal` or `GroupPrincipal` instances via the provider; do not pass mock lambda principals from demos.
5. Build the new list with `AclEntry.newBuilder()`, preserving entries that must remain and keeping order consistent with the filesystem model.
6. Test on an isolated test file, checking permissions before/after; prepare a recovery plan in case administrative access is locked out.
7. Call `setAcl` and re-read `getAcl` to verify the result, handle unexpected differences, and save an audit trail.
8. Remember that between reading and writing the ACL, another process can change the ACL: this is **time-of-check-to-time-of-use**. If strict synchronization is needed, use appropriate administrative mechanisms rather than assuming the view has compare-and-swap.
9. Prepare for `setAcl` failure where post-error state must be re-verified; do not promise atomic rollback across all providers.

### 11.2. Why Shouldn't You Convert an ACL to a `Set`?

`AclFileAttributeView.getAcl()` returns **`List<AclEntry>`**, which is ordered. Converting it to a `HashSet` and writing it back loses ordering, which can alter evaluation. Do not arbitrarily "normalize" order by username or enum type unless you truly understand the filesystem's rules.

### 11.3. ACLs Are Not a Substitute for Principle of Least Privilege

Do not grant `WRITE_ACL` or `WRITE_OWNER` when the requirement is merely reading content; those are very powerful administrative rights. Follow **least privilege**, separate data-reading rights from security-editing rights, and inspect whether inherited ACEs are appropriate.

## 12. Computing Effective Permissions: More Factors Than a Single ACE

When `getAcl()` shows an ACE `ALLOW user → READ_DATA`, we **do not yet** know whether the user can read data in every situation:

- Another `DENY` ACE or ACL ordering/inheritance effects may exist.
- The user may belong to multiple groups with differing entries.
- The file may sit under parent directories that disallow traversal.
- The system also applies share permissions, sandboxes, mount flags, locks/policies, and filesystem restrictions.
- The active runner might be a different principal from the displayed principal.
- The ACL could change right after you read it.

`Files.isReadable(path)`/`isWritable(path)` are **point-in-time checks**, not immutable security decisions. When actually opening/reading/writing, you must handle errors from that operation; do not use metadata checks as the sole authorization gate.

### 12.1. Owner, ACL, and POSIX in a Mixed System

For Java applications running on both Linux and Windows:

- Check available views (`basic`, `posix`, `acl`, `owner` depending on provider).
- Do not translate Windows ACLs 1:1 into POSIX `rwx`.
- If you only want the current user to create/read files per application policy, **setting permissions at file creation time** is sometimes better than post-hoc ACL edits.
- For legal/operational permission auditing requirements, use platform-specific administrative APIs/tools; Java views do not expose every security policy layer of the system.

## 13. Symbolic Links, Ownership, and Race Conditions

### 13.1. Reading Link Attributes or Target Attributes?

NIO.2 APIs usually follow symbolic links by default. Overloads taking `LinkOption.NOFOLLOW_LINKS` express intent to operate on the link rather than the target, **when supported by the provider**:

```java
AclFileAttributeView aclView = Files.getFileAttributeView(
        path, AclFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS);
```

This is an illustrative snippet. It does not guarantee every provider supplies symlink ACLs or allows modifying them.

### 13.2. Changes Between Check and Use

Suppose an application:

1. Checks `Files.getOwner(path)`.
2. Reads `view.getAcl()`.
3. Only afterward opens the file with `Files.newOutputStream(path)`.

If the path/symlink is modified by another process between steps, the opened file can differ from the checked file. This is a **TOCTOU** problem. Never treat `getOwner`, `getAcl`, or `Path.normalize()` as resource locks.

When designing high-security operations on untrusted paths, consider handle/directory-stream-based opening models and safer APIs where supported by the provider; always restrict filesystem permissions, isolate process privileges, and manage write permissions on parent directories.

## 14. Practical Error Handling

| Scenario | Possible Behavior / Exception | How to Respond |
| --- | --- | --- |
| File does not exist | `NoSuchFileException` | Check source/path; do not assume metadata exists |
| Lacking permission to read attributes | `AccessDeniedException`, `IOException` | Report permission error; do not "fall back" to granting broad access |
| ACL view unavailable | `null` from `getFileAttributeView` | Report unsupported; do not invoke methods on view |
| View created yet method unsupported | `UnsupportedOperationException` | Distinguish from empty data |
| Principal not found | `UserPrincipalNotFoundException` | Verify account name/domain |
| Principal incompatible with provider | Provider error / exception from set operation | Do not use self-created mock principals for set owner/ACL |
| Owner/ACL change denied | `IOException` or `SecurityException` | Report error; keep audit log, avoid blind retries |
| Symlink/target modified | Metadata no longer matches at time of use | Apply resource/TOCTOU policies |
| `getAcl()` contains unfamiliar principal | Valid entry in provider model that reader doesn't recognize | Preserve as-is; do not delete or reorder arbitrarily |
| ACL write succeeds yet access is still denied | Likely due to other permission layers | Inspect full policy instead of adding `WRITE_ACL` |

Do not swallow all exceptions with `catch (Exception ignored)`. If a feature only reports permissions, clearly show **unsupported view**, **permission denied**, and **file not found** as three distinct states.

## 15. Common Mistakes

1. Confusing **owner** with "account having all permissions".
2. Confusing `UserPrincipal.getName()` with a globally comparable identity.
3. Thinking every filesystem supports `AclFileAttributeView`.
4. Calling `view.getAcl()` directly when `view == null`.
5. Assuming `getAcl()` returns enough info to compute exact effective permissions for any user.
6. Confusing `PosixFilePermissions` (`rwx`) with rich Windows-style ACLs.
7. Failing to distinguish `FileOwnerAttributeView` from `AclFileAttributeView`.
8. Using a mock lambda principal from an example for `Files.setOwner` on a real machine.
9. Calling `setAcl` with a list containing only a single ACE without preserving old ACL entries.
10. Converting `List<AclEntry>` to a `Set`, losing ordering.
11. Granting `WRITE_ACL` or `WRITE_OWNER` when only data read access is wanted.
12. Ignoring inheritance flags and ACL evaluation of parent directories.
13. Assuming `NOFOLLOW_LINKS` has identical semantics across all providers.
14. Reading the ACL and then opening the file, believing the pathname cannot change.
15. Hardcoding usernames like `"Administrator"`/`"root"` and applying them across platforms.
16. Calling `Files.isReadable` and trusting the subsequent read operation will definitely succeed.
17. Failing to handle `IOException` when changing owner/ACL without a permission recovery plan.
18. Logging ACLs/account names to public channels without controlling sensitive data.

## 16. Practice Exercises and Self-Check

1. **Model:** In `AclEntryModelDemo`, add `WRITE_DATA` to the builder and predict how membership check results change.
2. **Observation:** Run `OwnerAclInspect` on a file you own, recording the owner and whether the ACL view is supported. Why can't you predict one universal ACL list for every machine?
3. **Views:** Check how `Files.getFileAttributeView(path, FileOwnerAttributeView.class)` differs from `AclFileAttributeView.class`. On a filesystem supporting only owner, what should the program do?
4. **Lookup:** Write code using `UserPrincipalLookupService` for an account that genuinely exists on the filesystem. Catch `UserPrincipalNotFoundException` specifically.
5. **ACL Ordering:** Why can sorting `getAcl()` by principal name and calling `setAcl()` alter semantics?
6. **Least Privilege:** If the requirement is that a user can only view content and ACL info, why shouldn't you also grant `WRITE_ACL`/`WRITE_OWNER`?
7. **Symlinks:** If `link` points to `target`, compare the meanings of `Files.getOwner(link)` and `Files.getOwner(link, NOFOLLOW_LINKS)` on a supporting system.
8. **POSIX:** Try reading `PosixFileAttributes.permissions()` on a supporting environment and compare with the ACL view. Why can't you claim the two models are equivalent?
9. **Errors:** Design clear outputs for missing file, unsupported ACL view, and denied attribute read permission.
10. **ACL Edit Workflow:** Create a checklist covering backup, preserving old entries, testing on a test file, principal lookup, audit logging, and readback verification before permitting `setAcl`.
11. **Races:** Describe why checking owner/ACL first still does not guarantee the file opened afterward is the same object.
12. **Proper Scope:** Explain why reading an ACL does not by itself prove a process can delete a file: deletion rights may involve parent directory permissions and other policies.

## 17. Summary

- `Files.getOwner()` returns a **`UserPrincipal`** describing the path's owner per provider; `Files.setOwner()` modifies security metadata and requires appropriate privileges.
- `UserPrincipalLookupService` is used to find valid identities; `GroupPrincipal` describes groups. Display names are not universal identifiers across systems.
- `AclFileAttributeView` allows reading an ordered **`List<AclEntry>`** and, when permitted, setting the ACL. The view may be **unsupported**; check for `null` and handle exceptions.
- Each `AclEntry` contains type, principal, permission set, and flags; ACE support/interpretation depends on the provider and OS.
- ACLs, POSIX `rwx`, DOS attributes, and **effective permissions** are related yet non-identical conceptual layers.
- Reading owner/ACL can be helpful for reporting, yet does not guarantee file identity or accessibility at a later moment.
- When changing ACL/owner is needed, use provider-looked-up principals, preserve necessary rules, test on isolated resources, verify after writing, and have a recovery plan.

**Final Principle:** managing owner/ACL is managing **actual access control** of resources. Check support and fully understand the filesystem's permission policies before making changes, rather than inferring permissions from a single username or an isolated ACL entry.
