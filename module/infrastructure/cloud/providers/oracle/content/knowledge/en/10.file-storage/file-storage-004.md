# POSIX permissions, root squash, and file access authentication

## Lesson objectives

Successfully mounting an OCI File Storage file system does not mean every process on the client machine can read or write data. Access permissions are determined across multiple layers: the network path, export options, authentication mechanism, UID/GID identity, and permissions on individual files or directories.

This lesson belongs to the **File Storage** chapter of the **CLOUD_PROVIDERS_ORACLE** module. The content connects IAM, VCN, and shared storage with authorization, monitoring, and application operations requirements on OCI.

After this lesson, you will be able to:

- Distinguish File Storage management permissions in OCI from file read/write permissions over NFS.
- Explain UID, GID, and POSIX permission bits on files and directories.
- Design group-shared directories with setgid and appropriate file-creation policies.
- Describe the effect and limitations of root squash and all squash.
- Distinguish the AUTH_SYS mechanism from Kerberos protection levels when supported and configured.
- Diagnose access errors based on the process's actual identity instead of blindly loosening permissions.

The examples use Linux and assumed UIDs/GIDs. When deploying, you must cross-check NFS capabilities, authentication mechanisms, export options, and permission features supported by OCI File Storage and the guest operating system. This lesson focuses on basic POSIX permissions and does not assume every type of ACL is supported by the service.

## 1. Which layers does a file read request pass through?

A conceptual flow:

```text
Client application process
  -> network connection to the mount target
  -> export and corresponding access conditions
  -> authentication mechanism and request identity
  -> identity mapping or squash, if applicable
  -> permissions on parent directories and target file
  -> read, write, or file management operation
```

| Layer | Deciding question | Example |
| --- | --- | --- |
| OCI IAM | Who can manage service resources? | Creating a file system, managing exports, or related settings |
| VCN network | Does the client have a communication path to the service? | Routes, NSGs/security lists, and firewalls |
| Export options | Under what conditions can a source use the export? | IP ranges, read-only/read-write, squash mechanism |
| NFS authentication | Which identity does the service trust and via which mechanism? | AUTH_SYS or supported Kerberos |
| Filesystem permissions | Does the effective identity have permissions for the path and operation? | UID/GID, mode, and directory traversal permissions |
| Application | Is the business user permitted to perform the operation? | Only the record owner may download their documents |

An IAM user permitted to manage a file system does not automatically become the owner of every file inside it. Conversely, a Linux service account with file read access does not necessarily have permission to modify exports via the OCI API.

You must also distinguish an instance's API-calling identity from a process's NFS access identity. Enabling instance principals for an application does not automatically replace UID/GID or file authentication mechanisms.

## 2. UID and GID are the critical identity data

### 2.1. Account names are only how the OS displays them

In the standard UNIX permission model:

- **UID** identifies the user.
- **GID** identifies the group.
- A process has an effective user/group and may belong to supplementary groups.
- Each file has an owner UID, group GID, and permission bits.

Names like `appuser` or `finance` are looked up from the operating system's account database. Two machines can display the same name while assigning different numeric IDs.

| Client | Username | UID | Group name | GID |
| --- | --- | --- | --- | --- |
| A | appuser | 21001 | finance | 3100 |
| B | appuser | 22001 | finance | 3200 |

If data was created by UID 21001, a process with UID 22001 does not become the owner merely because machine B also has the name `appuser`.

The reverse is also worth noting: UID 21001 might carry different names on two machines yet be treated as the same numeric identity in the corresponding access model. Therefore, aligning account names alone is insufficient.

### 2.2. Synchronizing identities across machines

For applications running across multiple instances, manage UIDs/GIDs consistently via images, system configuration, or an appropriate identity service. If using a directory service, confirm the client and the service's identity mechanism are properly configured; simply using an account directory does not automatically wire all authentication layers together.

Check running processes as well. Adding a user to a group does not guarantee that already-running login sessions or services immediately pick up the new supplementary group. You may need to start a new session or restart the specific service according to operational procedures.

Group transmission and lookup mechanisms also have their own limits and conditions. Do not just check groups in configuration files and assume all supplementary groups will definitely appear in NFS requests.

## 3. POSIX permissions on files and directories

### 3.1. Owner, group, and others

An example permission string:

```text
-rw-r-----  owner=appsvc  group=finance  report.csv
```

The three permission sets apply to owner, group, and others in order:

| Bit | Numeric value | For regular files | For directories |
| --- | --- | --- | --- |
| `r` | 4 | Read contents | List entry names |
| `w` | 2 | Modify contents, subject to related conditions | Create/delete/rename entries when appropriate traversal permission exists |
| `x` | 1 | Execute subject to OS conditions | Traverse/search directory to access entries inside |

For example, `640` corresponds to:

```text
Owner: 6 = r + w
Group: 4 = r
Others: 0 = no permission
```

Permissions on directories are not interpreted the same way as permissions on files. A directory with `r` but missing `x` may reveal entry names under certain conditions while preventing access to contents/metadata as the user expects.

### 3.2. Traversal permissions are required along the whole path

To open `/shared/finance/reports/report.csv`, the identity needs appropriate traversal permissions on all parent directories, not just read permission on the final file.

For example, the file has mode `644`, but the `/shared/finance` directory has mode `700` and belongs to another user. A user cannot bypass that directory merely because the final file grants read access to others.

When investigating a permission denied error, inspect the entire path chain. Changing the mode of the final file may not resolve a missing `x` permission on a parent directory.

### 3.3. Do not arbitrarily combine the three permission sets

In basic POSIX mode checks, the system selects the class matching the identity: owner, group, or others. If the user is the owner but the owner class denies the operation, do not assume it falls back to the group class to compensate.

For example, a file with mode `040` should not be assumed readable by the owner simply because they also belong to the group. You must evaluate the exact permission class and any additional permission mechanisms if supported by the environment.

### 3.4. Deletion permissions depend on the containing directory

File write permission and filename deletion permission are two different things. A user with write and traversal permissions on the containing directory can delete or rename an entry under filesystem rules, even if that file does not allow the user to modify its contents.

The sticky bit on a shared directory restricts delete/rename operations to the entry owner, directory owner, and applicable privileged identities. It does not replace read/write permissions, authentication, or data versioning protections.

Therefore, if the requirement is "members can read but cannot delete each other's files", setting files read-only alone may not suffice. You must design directory permissions and how the application manages file lifecycles.

## 4. Designing group-shared directories

### 4.1. Setgid enables group inheritance

Suppose the `finance` directory has:

```text
Owner UID: 23001
Group GID: 3100
Mode: 2770
```

Meaning:

- The owner and group members can read, write, and traverse the directory.
- Others have no permissions under this mode.
- The setgid bit on the directory causes new entries to inherit the directory's group according to supported filesystem behavior.

Setgid does not automatically grant all group permission bits to every newly created file. The application still determines the creation mode and is subject to rules such as umask.

### 4.2. Umask and how applications create files

In the basic case with no interfering inherited ACL mechanism, if a program requests creating a file with mode `666` and the process uses umask `007`, the typical result is `660`. For a directory requesting `777`, the result is `770`.

```text
Regular file: 666 with umask 007 -> 660
Directory:    777 with umask 007 -> 770
```

This works by masking out permission bits, not ordinary decimal subtraction.

If a program explicitly creates a file with `600`, setgid and a more permissive umask will not automatically turn it into `660`. Temporary file libraries, write-then-rename patterns, and Java applications may set specific permissions; always test the actual write path.

Do not grant execute permissions to all data files just so the group can read them. Document files need appropriate `r` or `w`, not `x` like a program.

### 4.3. ACLs require separate support verification

POSIX ACLs, NFS ACLs, and mode bits are not the same mechanism. Do not assume OCI File Storage, the protocol, and the client in use support every ACL command the same way a local filesystem does.

The baseline design in this lesson uses UID/GID, mode, setgid, and umask. If you want to use ACLs or supplementary permission mechanisms, confirm full support before building policies dependent on them. Do not interpret a failing `setfacl` as evidence that data is lost or that broader IAM permissions are needed.

## 5. How does root squash work?

### 5.1. Root on the client is not automatically an administrator of the file system

With NFS access using UNIX identity, requests from root can carry UID 0. If the server trusts that privileged identity without appropriate restrictions, a client administrator could perform broad operations on shared data.

**Root squash** maps the root identity from the client to an unprivileged anonymous identity according to the export configuration. The associated IDs are handled per the service's squash rules.

Conceptual example:

```text
Client process sends request with UID 0
  -> export applies root squash
  -> server evaluates using configured anonymous UID/GID
  -> checks file/directory permissions against the mapped identity
```

The anonymous value must be verified in the actual configuration rather than inferred solely from the display name `nobody`. Clients can display the same ID under different names.

### 5.2. Why does `sudo` still get permission denied?

Suppose the anonymous UID/GID does not have write permission on the finance group's `2770` directory. An application user in finance can write, whereas a command run as root can be squashed to anonymous and fail to write.

This may be the intended behavior of the policy, not a mount error. `sudo` elevates privileges on the client machine but does not automatically bypass the mapping and permissions enforced by the server.

Similarly, `chown` from the client can be rejected because the post-squash identity lacks ownership administration rights. Do not disable root squash across all sources just to let an initialization script keep running.

### 5.3. Comparing squash options

OCI export options offer identity squash choices according to service capabilities, with the following conceptual meanings:

| Option | How identity is handled | Impact to understand |
| --- | --- | --- |
| No squash | Keeps the identity accepted by the authentication mechanism | Requires strong trust in the client and its privileged identities |
| Root squash | Maps root to anonymous | Reduces client root privileges but does not replace user authentication |
| All squash | Maps all users to anonymous | Requests may lose differentiation by original UID/GID |

If all squash maps everyone to a UID with write permission, anyone allowed to access the export can act with that same identity's privileges. This is not a per-user isolation mechanism.

The anonymous UID/GID must be chosen so it does not accidentally collide with an owner or group holding business privileges. Calling an account "anonymous" does not remove permissions already granted to that ID.

### 5.4. Important limitations of root squash

Root squash primarily restricts requests carrying the root identity. In the AUTH_SYS model, which trusts numeric identities supplied by the client, a client administrator or someone compromising the client can spawn processes with non-zero UIDs.

Therefore, root squash does not prove a compromised client cannot impersonate a user with another UID. It is a useful control layer, yet it must be combined with network scoping, client governance, strong authentication where appropriate, and least privilege.

Do not use root squash as a sandbox for mutually untrusted clients that are allowed to submit requests under a client-asserted identity model.

## 6. How do export options and filesystem permissions work together?

### 6.1. Exports do not replace mode bits

An export may allow read/write from an IP range, yet a file can still reject writes due to POSIX permissions. Conversely, a file with writable mode bits does not turn a read-only export into a read/write one.

Write conditions can be expressed conceptually as:

```text
Valid network path
  AND export permits the source and operation
  AND authentication mechanism is accepted
  AND mapped identity has permissions on the path
  -> only then can the operation be accepted
```

This is a model for checking each layer, not a description of the service's mandatory internal execution order.

### 6.2. Designing intentional access sources

An illustrative plan:

| Client group | Controlled source | Export permission | Desired data permission |
| --- | --- | --- | --- |
| Processing application | Managed application host group | Read/write, appropriate squash | Write only to the service's data area |
| Reporting group | Reporting host group | Read-only | Read only authorized data |
| Administrative flow | Restricted administrative source | Sufficient permission for authorized maintenance tasks | Provision ownership/permissions per procedure |

Do not allow overlapping sources with conflicting intents without checking export option selection rules. Also inventory any other exports or access paths leading to the same data: policy on one export path does not prove all other paths are similarly restricted.

If requiring a privileged source port, understand this is a connection condition, not individual authentication. Anyone with client administrative privileges can control source ports; that condition does not replace Kerberos or proper identity policy.

### 6.3. Initialization permissions differ from day-to-day runtime permissions

A new root directory may not yet allow the application service account to create data, while root is squashed. You need an initial provisioning flow with appropriate privileges to set up ownership/groups and required directories.

This administrative flow must be scoped by source and time, have an accountable owner, and revert to operational policy afterward. Do not leave a broad export with root unsquashed as the default state merely to simplify `chown`.

Another approach is pre-designing structure and permissions using an administrative identity suited to the chosen authentication mechanism. Day-to-day application runs do not need permission to alter ownership across the entire file system.

## 7. NFS authentication: AUTH_SYS and Kerberos

### 7.1. AUTH_SYS trusts the identity provided by the client

With AUTH_SYS, requests use attributes such as UID/GID supplied by the client. This is neither a user entering a password for each file read nor IAM signing every filesystem operation.

This model requires strict client governance and consistent UIDs/GIDs, alongside source access controls. A system with tight mode bits that lets untrusted clients declare arbitrary identities still carries risk.

### 7.2. Kerberos protection levels

OCI File Storage supports Kerberos integration subject to supported service conditions. A deployment requires configuring the service side, identity source, Kerberos infrastructure, and compatible clients; merely adding a mount option does not create a complete authentication system.

Security flavors are typically distinguished as follows:

| Flavor | Main purpose | What it does not automatically replace |
| --- | --- | --- |
| `sys` | Access based on UNIX identity provided by the client | Strong per-user authentication via Kerberos |
| `krb5` | Authentication via Kerberos | Confidentiality of transmitted contents via authentication alone |
| `krb5i` | Kerberos with integrity protection | Content encryption as provided by privacy level |
| `krb5p` | Kerberos with privacy/traffic encryption via this mechanism | Filesystem permissions and application controls |

Select only flavors genuinely supported by the export, client, and service configuration. Deployment prerequisites may include DNS, time synchronization, principals, identity mapping, key material, and ticket acquisition/renewal.

Kerberos authenticates identity, yet appropriate read/write permissions are still required. An authenticated principal does not automatically gain access to every directory. Also do not assume root squash or mapping behaves identically across every security flavor; verify how the service applies them in your actual configuration.

### 7.3. Background services need an appropriate credential mechanism

An interactive login user being able to read a file does not prove a background Java service has the required credentials. A service has its own user, environment, session, and lifecycle.

If using Kerberos, design how the service obtains and maintains credentials under a supported model. Monitor for ticket expiration, identity service disconnections, or clock skew. Do not copy an operator's credentials as a long-term mechanism for an application.

### 7.4. Encryption does not equal authorization

Storage encryption at rest and transport protection in transit are layers distinct from POSIX permissions. An encrypted channel can still allow an authenticated identity to read a file whose mode bits permit it; encryption does not automatically fix overly broad permissions.

Conversely, proper mode bits do not prevent traffic inspection if the transport lacks appropriate protection. You must design identity, permissions, and channel protection together according to system requirements.

## 8. Example: shared reports directory for a Java backend

### 8.1. Context and identities

Two OCI instances run the same Java service and share a reports directory. There is a report-generating group and a report-reading group. The following IDs are illustrative only for this lesson:

| Identity | Illustrative UID/GID | Role |
| --- | --- | --- |
| Report generation service | UID 23001, group finance GID 3100 | Create and update contents |
| Finance staff | Individual UIDs, member of group 3100 | Access according to assigned permissions |
| Non-finance user | Individual UIDs, not in group 3100 | No access to internal area |
| Post-squash anonymous | Dedicated UID/GID chosen in configuration | No write permission to finance area |

Both instances must use consistent IDs for the service and group that need sharing. Parent directory permissions must allow the right identities to traverse to the data area.

### 8.2. Illustrative policy

- The internal directory belongs to the service owner and group finance, mode `2770`.
- The service creates files with a policy allowing the required group to access, e.g., `660` where appropriate.
- Reporting clients are read-only via an export configured as read-only.
- Root squash applies to application sources as designed.
- Do not grant permissions to others just to compensate for inconsistent UIDs/GIDs.

If you require different read and write groups at the per-user level on the same access path, a single group with mode `2770` is insufficient to distinguish them. You must adjust the group/directory model, export path, or supported permission mechanism; do not assume the example table solves every authorization model.

### 8.3. File permissions do not replace web user authorization

Every request in the Java backend may perform I/O under the same service UID. File Storage sees the service identity, not which end user is currently logged into the website.

If user A must not read user B's documents, the application must check business authorization before opening the file. Do not rely solely on all files being owned by the service to allow downloads by a client-supplied path.

Similarly, filenames and paths from users must be handled according to the application's access model. POSIX permissions help constrain the process, yet do not replace object-level checks in the application.

### 8.4. Containers and ownership initialization steps

In containers, cross-check the actual process UID/GID with the NFS side. A username inside an image is not enough to prove it has permissions.

An init process running as root to `chown` data may fail due to root squash. Orchestrator group options also do not guarantee every ownership change will be accepted by the server. Prepare permissions via an authorized procedure, then run the service with the minimum required identity.

## 9. Diagnosing access errors layer by layer

### 9.1. Inspection commands on a Linux client

The commands below are for observation in an authorized environment. Some utilities must be pre-installed; replace paths and usernames with actual data.

```bash
# Identity of the current session
id

# Look up the identity of a specific account
id appsvc
getent passwd appsvc
getent group finance

# Verify filesystem and mount options
findmnt -T /mnt/team/finance
nfsstat -m

# View numeric UID/GID and actual mode
stat -c '%n uid=%u gid=%g mode=%a (%A)' /mnt/team/finance

# View permissions for each path component
namei -l /mnt/team/finance/report.csv
```

The `id` output of your current shell does not prove the running service uses the same identity. Check the process's user/group or corresponding service configuration.

Seeing nice usernames in output does not replace comparing numeric UIDs/GIDs. In environments with mapping or other authentication, also verify the identity accepted by the server after those steps.

### 9.2. Investigation sequence

1. Confirm the right mount target, export, and data path; avoid inspecting a local directory because NFS is not mounted.
2. Check the network path and export policy for the exact client source.
3. Identify the security flavor and actual credentials of the process.
4. Determine the effective UID/GID or identity after mapping/squash.
5. Check traversal permissions on all parent directories and operation permissions on the target object.
6. Check client/export read-only settings, ownership, mode, and relevant OS security layers.
7. Check effects of identity caching, supplementary groups, and already-running processes.
8. Retest with the exact application identity in a test environment without defaulting to root as a stand-in.

### 9.3. Symptom table

| Symptom | Direction to check |
| --- | --- |
| Mount fails | Network, export source, protocol/security flavor, and mount conditions |
| Regular user can write, `sudo` cannot | Root squash and anonymous UID/GID |
| Same username works on host A, denied on host B | Numeric UID/GID, supplementary groups, source-based export, and credentials |
| Can read a known filename but cannot list directory | Difference between `r` and `x` permissions on directories |
| File has read permission yet access is denied | Parent directory traversal permissions and evaluated identity |
| Can write file but cannot delete, or vice versa | Containing directory permissions, sticky bit, and file mode |
| `chown` is denied | Effective identity permissions after squash, not an NFS bug by default |
| Client cannot write even though file permits it | Export/client read-only, squash, directory permissions, or another policy |
| Service fails after some time while interactive session works | Expired credentials, stale session/groups, service environment |
| New files are readable only by owner | Mode requested by program, umask, and temporary-file/rename pattern |

## 10. Practice plan and policy verification

Use a dedicated test directory and identities prepared by the administrator. Create/modify/delete operations in this lab must be confined to test data; this section does not require modifying permissions on production user-facing data.

Build a verification matrix:

| Identity/scenario | Test | Expected result under the illustrative policy |
| --- | --- | --- |
| Report generation service | Create then read back a test file | Succeeds in the assigned area |
| Valid group member | Read a file with matching mode/group | Succeeds |
| Non-group user | Traverse the finance directory | Denied when no other permissions apply |
| Read-only client | Create or modify a test file | Denied even if file mode allows writes |
| Squashed root | Create a file in a directory where anonymous lacks permissions | Denied |
| Two application instances | Read a file created by the other instance | Succeeds with consistent IDs and permissions |
| Create file via real app flow | Check owner/group/mode after creation or rename | Matches policy, not only when created via shell |
| Service restart | Access data with fresh identity/credentials | Does not depend on an operator's old login session |

If a result differs from expectations, record the client source, security flavor, effective identity, owner/group/mode, and export option. Do not modify multiple layers simultaneously and then attribute the cause to a single change.

Operationally, monitor permission errors in the application and configuration changes that affect access. Do not assume OCI administrative logs automatically capture every individual user's NFS file opens; design data observability suited to service and application capabilities.

The tested policy needs an owner and a reproducible way to apply it. A permission set fixed manually today without being stored in configuration can drift after replacing instances, images, or service accounts.

## 11. Self-check

1. Does an IAM user who can manage exports automatically have read access to all files over NFS? Why or why not?
2. Two machines both have user `appsvc` but different UIDs—what issue occurs when using numeric identity permissions?
3. Why does reading a file require checking `x` permissions on parent directories too?
4. Under what circumstances can a user delete a file without having permission to modify its contents?
5. What does setgid on a directory solve, and why does it not guarantee new files have group-write?
6. Why might a command run as root be denied while a service account can write?
7. Does root squash completely prevent a client administrator from impersonating a non-zero UID under AUTH_SYS?
8. When does all squash remove the ability to distinguish users via UID/GID permissions?
9. At which protection layer do `krb5`, `krb5i`, and `krb5p` differ? Do they replace mode bits?
10. Why must a Java backend still check end-user authorization even when the NFS directory has proper permissions?

The output of this lab is an access policy with consistent identities, controlled client sources, sufficient file permissions, and test results covering both allowed and denied cases.
