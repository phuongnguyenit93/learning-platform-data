# Export options and network-based access control

In the **File Storage** chapter of the Oracle Cloud Infrastructure (OCI) module, this lesson addresses a concrete deployment requirement: multiple Linux machines need to share a filesystem, where some machines can write, some are read-only, and some are denied access. At the same time, the root account on a client must not automatically receive full privileges over the shared data.

We use NFS export options together with VCN security rules and UNIX permissions. The hands-on example uses NFSv3 with `AUTH_SYS`, private IPv4 addresses, and a lab filesystem. This configuration is for learning access control; environments requiring strong user authentication or transport encryption with Kerberos/TLS options must be designed accordingly.

After this lesson, learners will be able to:

- Distinguish OCI administrative permissions from NFS connection permissions and file read/write permissions.
- Choose the appropriate Source CIDR, access mode, source port, and identity squash.
- Explain the order in which entries are applied when CIDRs overlap.
- Configure network and export layers separately, then test both allowed and denied access.
- Update policies in a controlled manner without overlooking other exports pointing to the same filesystem.

## 1. From client to data: distinct control layers

A file read request passes through multiple conditions:

```text
Client has a route to the mount target
  -> traffic is permitted by the network layers
  -> client source matches an appropriate export option
  -> authentication method and source port are accepted
  -> mapped UID/GID has permissions on the file/directory
```

| Layer | What does it control? | Example |
|---|---|---|
| OCI IAM | Who can create/modify service resources | Operators allowed to update export options |
| Routing and network security | Which clients can connect to the mount target | Only the application host group can reach NFS/RPC ports |
| Export options | How a source accesses data through an export | Host A is read/write, host B is read-only |
| NFS identity and UNIX permissions | Which user can perform operations on files | UID 2000 can write to a directory owned by the matching UID/GID |

These layers have separate roles. IAM allowing filesystem edits in the Console does not automatically grant permission to read file contents over NFS; likewise, the root account inside a VM does not automatically have permission to edit exports in OCI. [Source: File Storage security layers](https://docs.oracle.com/en-us/iaas/Content/File/Concepts/securitylayers.htm).

For example, a client might mount successfully yet fail to write because the directory does not allow that UID to write. Conversely, mode `0777` on a directory does not help a client bypass a read-only export or a blocked network path.

Each layer must be verified with appropriate evidence. Seeing a successful mount alone does not prove the permission requirements are correct.

## 2. File system, mount target, export, and export path

Objects to identify:

- **File system** holds the directory tree and data.
- **Mount target** is the NFS connection point on the network.
- **Export set** is attached to a mount target and contains the exports.
- **Export** links a filesystem to an export path and client policy.
- **Export options** is the list of entries defining permissions for sources.

A filesystem can be exposed through multiple exports/mount targets. Policies are attached to the specific export being used, so when auditing access, record the filesystem OCID, export OCID, mount target, and mounted path. [Source: OCI exports and export options](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/exportoptions.htm).

Connection example:

```text
10.40.20.10:/shared-lab  ->  /mnt/fss-lab on the client
```

Here `10.40.20.10` is the mount target IP, `/shared-lab` is the export path, and `/mnt/fss-lab` is the local mount point. These three values play different roles; the export path name does not automatically create a directory of the same name inside the filesystem. [Source: paths in file systems](https://docs.oracle.com/en-us/iaas/Content/File/Concepts/filesystempaths.htm).

If an application is mounting a different export of the same filesystem, editing the export an operator is viewing in the Console may not change that application's access path. Therefore, always start from the actual connection on the client and trace back to OCI.

## 3. Reading export option fields

An entry describes policy for a source, not a list of IAM accounts.

| API/JSON field | Meaning | Lab example |
|---|---|---|
| `source` | IP address or CIDR of the NFS client | `10.40.10.11/32` |
| `requirePrivilegedSourcePort` | Whether the client must use source ports 1–1023 | `true` |
| `access` | Access level through the export | `READ_WRITE` or `READ_ONLY` |
| `identitySquash` | UID/GID mapping rule | `ROOT` |
| `anonymousUid` | UID assigned after the corresponding squash operation | `65534` |
| `anonymousGid` | GID assigned after the corresponding squash operation | `65534` |
| `allowedAuth` | Permitted NFS authentication types | `["SYS"]` |
| `isAnonymousAccessAllowed` | Allows fallback to anonymous identity in relevant LDAP lookup scenarios | `false` |

Data types must be exact: booleans are `true`/`false`, UID/GID are numbers, and `allowedAuth` is an array. These fields belong to the `ClientOptions` structure. [Source: OCI ClientOptions](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/filestorage/model/ClientOptions.html).

### Source describes the connecting machine

For IPv4, `/32` selects one address, `/24` selects a network range. The source must correspond to the address the service receives from the actual connection path. If accessing from on-premises or through an intermediate device performing source translation, check the routing and actual source address instead of guessing.

SSHing into a VM via Bastion and then mounting NFS from that VM initiates the NFS connection from the VM; it is not a direct NFS connection from the laptop's public IP. If the VM has multiple VNICs, check which interface and source IP the route to the mount target uses.

A broad `source` like `0.0.0.0/0` does not automatically turn a mount target into a public address. A mount target does not have an Internet-routable IP, yet a broad rule still permits any source that has a network path and passes the other layers. When creating via CLI without specifying client options, some IPv4 defaults are very broad; declare and read back the policy explicitly. [Source: OCI export create and default client options](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/fs/export/create.html).

### Source port is not destination port

`requirePrivilegedSourcePort: true` checks the client's **source port**. It does not change the destination NFS port and does not mean only processes with UID 0 can read files. An OS-managed NFS client can use a privileged source connection to serve requests from ordinary users.

On Linux, the `resvport` mount option satisfies the privileged source port requirement; `nosuid` restricts SUID/SGID effects for programs executed from that mount. The two options address different concerns. [Source: mounting NFS from UNIX-style instances](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/mountingunixstyleos.htm).

A privileged source port is an additional condition, not a cryptographic user identity authentication method. Do not use it as a substitute for secure administration of trusted clients.

## 4. Entry ordering and overlapping CIDRs

OCI applies **the first entry matching the Source IP** in the export options list. It does not automatically pick the most specific CIDR. If no entry matches, the client does not see that export. [Source: order of applying NFS export options](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/exportoptions.htm).

Consider an illustrative configuration different from the lab list later:

| Order | Source | Access |
|---:|---|---|
| 1 | `10.40.10.0/24` | `READ_ONLY` |
| 2 | `10.40.10.11/32` | `READ_WRITE` |

Client `10.40.10.11` matches entry 1 immediately and receives read-only access. Entry 2 is not used to elevate permissions for that match.

If the intent is one read/write host and the rest of the subnet read-only, place the specific exception first:

| Order | Source | Access |
|---:|---|---|
| 1 | `10.40.10.11/32` | `READ_WRITE` |
| 2 | `10.40.10.0/24` | `READ_ONLY` |

This policy grants read access to other machines in the subnet as well. If the requirement is that only two specific machines may access, use two separate `/32` entries and do not add a whole-subnet entry.

There is no "deny at the end to override allow at the top" under the logic above. Before updating, write down the list of test sources and determine the first entry each source will match.

## 5. Root squash and file permissions

`identitySquash` changes the identity used during permission checks:

| Value | Effect |
|---|---|
| `NONE` | Do not squash under this rule |
| `ROOT` | Map root identity UID/GID 0 to the configured anonymous UID/GID |
| `ALL` | Map all users and groups to the configured identity |

For example, root squash with `anonymousUid=65534`, `anonymousGid=65534` does not make the filesystem read-only. The mapped identity can still perform actions permitted by file/directory mode bits. If a directory allows everyone to write, the squashed account can still write. [Source: identity squash in ClientOptions](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/filestorage/model/ClientOptions.html).

With `AUTH_SYS`, UIDs/GIDs must be synchronized and managed across clients. Two identical usernames with different UIDs are not automatically the same file owner; two different usernames with the same UID can be seen as the same identity at that permission check layer.

Root squash also does not fully protect against a client administrator capable of assuming a non-root UID that has permissions. Therefore, choosing trusted sources and controlling client administration are key parts of an `AUTH_SYS` design.

Setting `isAnonymousAccessAllowed=false` does not mean disabling root squash. This field relates to permitting the anonymous identity during LDAP user lookup in corresponding authentication configurations; the squash rule remains a separate field. [Source: Using Kerberos authentication](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/kerberos.htm).

A common test observation is `sudo touch` failing while the application user succeeds in writing. If root is being squashed while the directory belongs to the application user's UID, that outcome can match the design rather than indicating a network error.

## 6. Network configuration for the mount target

### Lab network model

| Component | Illustrative address |
|---|---|
| Client subnet | `10.40.10.0/24` |
| Mount target subnet | `10.40.20.0/24` |
| Mount target | `10.40.20.10` |
| Client A, read/write | `10.40.10.11` |
| Client B, read-only | `10.40.10.12` |
| Client C, denied by export | `10.40.10.13` |

All addresses must be replaced for your actual environment. Using separate subnets for the mount target and clients helps clearly manage resource scope. Routing must allow the two sides to communicate; if peering, DRG, firewall, or ZPR is involved, also verify applicable rules at those layers.

To separate export testing from network testing, the lab allows the entire client subnet to reach the required ports. That way client C has a network path yet must still be denied by the export. Production environments can further restrict the network layer to only permitted clients.

### Ports needed for NFSv3/RPC in the lab

Per OCI guidance, configure stateful ingress to the mount target and egress from the client with the following destination ports:

| Protocol | Destination ports at mount target |
|---|---|
| TCP | `111`, `2048`, `2049`, `2050` |
| UDP | `111`, `2048` |

Mount target ingress uses source `10.40.10.0/24`; client egress uses destination `10.40.20.10/32`. When requiring a reserved source port, set the matching source port range `1–1023` and verify the client uses `resvport`. Return traffic for stateful connections is tracked by the stateful mechanism. [Source: VCN security rules for File Storage](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/securitylistsfilestorage.htm).

Opening only TCP 2049 does not prove the required mount, RPC, and locking flows work. LDAP/Kerberos or encryption setups require additional network connections; the table above is for the NFSv3 `AUTH_SYS` lab.

### NSG and security list

Attach the appropriate NSGs to the mount target and client VNICs as designed. Security lists apply at the subnet level; NSGs apply to the VNICs/resources attached to the group. A new NSG does not automatically protect every resource just because they are in the same subnet.

When using both NSGs and security lists, review all active allow rules. A narrow rule in an NSG does not narrow a broader rule still present in a security list. If the endpoint has a ZPR security attribute, it must also satisfy the corresponding ZPR policy. [Source: OCI security rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

Check guest firewalls and actual routing when timeouts occur. Do not disable network security layers or open all ports instead of identifying which port and direction are missing.

## 7. Explicit export policy for two clients

Lab requirements:

- A `10.40.10.11` can read/write.
- B `10.40.10.12` is read-only.
- C `10.40.10.13` has no entry for this export.
- A and B use privileged source ports, `AUTH_SYS`, and root squash.

JSON list for `--export-options`:

```json
[
  {
    "source": "10.40.10.11/32",
    "requirePrivilegedSourcePort": true,
    "access": "READ_WRITE",
    "identitySquash": "ROOT",
    "anonymousUid": 65534,
    "anonymousGid": 65534,
    "isAnonymousAccessAllowed": false,
    "allowedAuth": ["SYS"]
  },
  {
    "source": "10.40.10.12/32",
    "requirePrivilegedSourcePort": true,
    "access": "READ_ONLY",
    "identitySquash": "ROOT",
    "anonymousUid": 65534,
    "anonymousGid": 65534,
    "isAnonymousAccessAllowed": false,
    "allowedAuth": ["SYS"]
  }
]
```

The two sources do not overlap, making review and verification straightforward. Do not append `0.0.0.0/0` at the end as a "fallback", as that entry would open an access path for other clients.

### Updating via Console

Open **Storage → File Storage → File Systems**, select the right compartment and filesystem, and go to **Exports**. Select the export by mount target and export path; open **NFS client Export options** to edit the list. Verify the order, source, and all fields before updating.

Export paths cannot be edited in place after creation; when a path change is needed, plan a different export and migrate clients. [Source: editing an export](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/edit-export.htm).

### Updating via OCI CLI

In an authenticated OCI CLI environment with the right region/profile selected, read the resource first:

```bash
oci fs export get --export-id '<EXPORT_OCID>'
```

Record the prior configuration and ETag if using concurrency control. Save the prepared JSON list to `export-options.json` in your operations environment, then update:

```bash
oci fs export update \
  --export-id '<EXPORT_OCID>' \
  --export-options file://export-options.json \
  --if-match '<OBSERVED_ETAG>'
```

`--export-options` updates **the entire list**; it does not append a new entry. `--if-match` ensures the request only applies while the ETag still matches. If someone edited it beforehand, re-read and merge according to the goal rather than blindly overwriting that change. [Source: OCI CLI export update](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/fs/export/update.html).

After updating:

```bash
oci fs export get \
  --export-id '<EXPORT_OCID>' \
  --query 'data."export-options"'
```

Compare the returned content and order against the intended policy. An API success message is evidence of a configuration update, not yet evidence that clients have been properly restricted.

## 8. Preparing data permissions for testing

To test the export, UNIX permissions must allow basic operations. The lab uses an application user with **UID 2000, primary GID 2000** on A and B; client C can use the same UID/GID to rule out identity differences when testing mounts.

Before creating the user, check which UID/GID and names are already in use:

```bash
getent passwd 2000
getent group 2000
getent passwd fssapp
getent group fssapp
```

Only on fresh lab machines, when these values are unused and the plan specifies this UID/GID, create them:

```bash
sudo groupadd --gid 2000 fssapp
sudo useradd --uid 2000 --gid 2000 --create-home fssapp
id fssapp
```

If a suitable user already exists on the machine, use that user instead of modifying the UID of an account already running an application. Usernames do not have to match across machines, but the numeric UIDs/GIDs used for permissions must align.

The data administrator prepares a `/lab-data` directory in the lab filesystem owned by `2000:2000`, mode `2770`. Perform this via an administrative path that truly has create/chown privileges, before narrowing down to the two-client policy above. The example below assumes the administrative path has mounted the right filesystem at `/mnt/fss-admin`:

```bash
sudo mkdir -p /mnt/fss-admin/lab-data
sudo chown 2000:2000 /mnt/fss-admin/lab-data
sudo chmod 2770 /mnt/fss-admin/lab-data
ls -ldn /mnt/fss-admin/lab-data
```

This is a data permission provisioning step, not a command to run from a squashed client root expecting `sudo` to bypass it. If a separate bootstrap export/entry is needed for administration, restrict it to the exact administrative source, document its purpose, and revoke it before concluding the lab is complete.

With mode `2770`, owner and group have read/write/traverse permissions; others have no permissions. The setgid bit makes child files/directories inherit the directory's group according to UNIX semantics. In the root squash test, the anonymous UID/GID must not be the owner, a permitted group, or have any other permission path into this directory.

## 9. Testing from allowed and denied clients

### Mounting the right export

On each Linux client, install the NFS client matching the image. For example, Oracle Linux uses `nfs-utils`; Ubuntu/Debian uses `nfs-common`. Create a dedicated mount point and confirm no other mount exists there.

```bash
sudo mkdir -p /mnt/fss-lab
sudo mount -t nfs \
  -o vers=3,proto=tcp,nosuid,resvport,sec=sys \
  10.40.20.10:/shared-lab /mnt/fss-lab

findmnt --mountpoint /mnt/fss-lab -o TARGET,SOURCE,FSTYPE,OPTIONS
```

Replace the IP/path according to the actual export. Use the Console's sample command matching the authentication method if the environment is configured differently. Do not use `soft` with read/write mounts for File Storage. [Source: mount commands and mount options](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/mountingfilesystems.htm).

The lab uses the same mount options so that B's read-only restriction is tested on the server side, rather than setting `ro` on the client side and concluding the export blocked writes.

### Client A: application can write

After confirming `id fssapp` has the right UID/GID:

```bash
sudo -u fssapp sh -c 'printf "writer-check\n" > /mnt/fss-lab/lab-data/writer.txt'
sudo -u fssapp cat /mnt/fss-lab/lab-data/writer.txt
ls -ln /mnt/fss-lab/lab-data/writer.txt
```

Creation and reading are expected to succeed. Effective permission is the result of both the export allowing writes and directory permissions allowing that identity to write.

### Client B: can read, cannot create new files

```bash
sudo -u fssapp cat /mnt/fss-lab/lab-data/writer.txt
sudo -u fssapp touch /mnt/fss-lab/lab-data/reader-must-not-create.txt
```

Reading is expected to succeed and file creation to fail. Record the actual error and exit status. If the file was created, investigate the active export/mount target, actual source, and applied entry; do not treat the test as passing just because client B can read.

Mount flags displayed on the client are not independent proof of server-side permissions. Use the outcome of operations designed around known UNIX permissions.

### Client C: has a network path but is not permitted by export

From client C, use the same IP and export path to attempt mounting onto a dedicated unmounted mount point. The request is expected to be rejected by the export policy.

To attribute the result to export options, there must be evidence that the network path and required services are allowed for the lab. A network timeout only proves the connection did not complete; it does not prove the export excluded source C.

Do not use an old mount session to another filesystem as evidence. Record the source IP, destination mount target, export path, and test timestamp.

### Root squash on A

Under the directory conditions prepared above and with root having no supplementary group with permissions, test:

```bash
sudo touch /mnt/fss-lab/lab-data/root-must-not-create.txt
```

Root is expected to be mapped to the anonymous identity and fail to create the file. Then verify user `fssapp` can still operate normally. If root can still write, inspect mode/ownership, group membership, the applied entry, and other access paths; seeing UID 0 on the client side alone is not enough to conclude the server used UID 0.

Minimum recording table:

| Client/identity | Read sample file | Create file | What is verified |
|---|---|---|---|
| A, UID 2000 | Succeeds | Succeeds | RW with matching UNIX permissions |
| B, UID 2000 | Succeeds | Fails | Server enforces read-only |
| C | No access via export | Not applicable | Source is not granted access by export |
| A, squashed root | Subject to anonymous permissions | Fails in lab directory | Squash rule and directory permissions work together |

## 10. When strong authentication or encryption is required

CIDR and `AUTH_SYS` fit some tightly managed client networks, yet do not automatically provide cryptographic proof of individual users. OCI File Storage provides Kerberos options:

| Value | Main function |
|---|---|
| `KRB5` | Kerberos authentication |
| `KRB5I` | Authentication and integrity protection for data in transit |
| `KRB5P` | Adds confidentiality for data contents in transit |

Using Kerberos requires configuring the mount target, identity mapping, LDAP, and compatible clients; it is not just replacing `["SYS"]` with another string in JSON. [Source: OCI Kerberos authentication](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/kerberos.htm).

If Kerberos is mandatory, check whether `SYS` is still permitted in the same policy or through another export. An open `SYS` path can prevent mandatory Kerberos from being enforced as intended. [Source: security considerations when configuring File Storage with Active Directory](https://docs.oracle.com/en-us/solutions/configure-file-storage-for-active-directory/considerations-security.html).

Encryption at rest and encryption in transit are two distinct properties. Choosing a narrow source, root squash, or `nosuid` mount does not automatically enable TLS. OCI also offers transport encryption mechanisms via corresponding client tools; choose based on requirements and verify the actual configuration. [Source: File Storage security and in-transit encryption](https://docs.oracle.com/en-us/iaas/Content/File/Concepts/securitylayers.htm).

## 11. Updating, revoking, and auditing other access paths

Before changing the source or access level of an active export, identify affected clients and applications. Losing permissions mid-write can cause application I/O errors, so choose an appropriate window and method to stop work.

Recommended operational procedure:

1. Record the current configuration and client access paths.
2. Determine the complete post-change list, including entry order.
3. Update using an appropriate change-control mechanism.
4. Read the policy back from OCI.
5. Test both allowed and denied operations from the right clients/identities.
6. Audit other exports/mount targets of the same filesystem.
7. Revoke the bootstrap path and record handover results.

With the CLI, `--export-options '[]'` makes that export invisible to clients; omitting the `--export-options` parameter during update preserves the existing list. These are two different actions. [Source: OCI export update](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/fs/export/update.html).

Closing one export does not prove access to the entire filesystem has been revoked if another export still permits that source. Similarly, removing an NSG rule is insufficient if a security list still grants a broader network path. Cross-check all access paths that need revocation.

Do not treat policy updates as deleting data that a client has already read or copied beforehand. When needing conclusions about an active session, separately record stopping the application, normal unmounting, establishing a fresh test connection, and the post-change result; do not assume an existing session fully reflects a new mount check.

## 12. Troubleshooting and completion criteria

| Symptom | Layer to inspect first | Specific check |
|---|---|---|
| Mount timeout | Network | Route, destination IP, NSG/security list, RPC/NFS ports, firewall, and ZPR if applicable |
| Mount denied | Export/authentication | Source IP, path, first matching entry, source port, and `sec` |
| Mounted but user cannot write | File permissions or access | `READ_ONLY`, UID/GID, ownership, mode, and squash |
| Root cannot write but app user can | Squash | Cross-check anonymous UID/GID and directory permissions |
| Machine needing RW only gets RO | Entry ordering | Does a broader CIDR above match before the `/32` exception? |
| Unlisted client still has access | Another export or broad rule | Check actual source and all related exports/mount targets |
| Editing one entry breaks another client | Update method | Was the whole list replaced without keeping existing entries? |
| Kerberos client fails while SYS works | Authentication | Check allowed types, Kerberos setup, and fallback paths |
| Write test reports success but data is local | Mount point | Verify `findmnt --mountpoint` before writing |

When reading logs and sharing evidence, retain OCIDs, IPs, paths, numeric identities, and timestamps as required by your team's guidelines; do not include secrets or credentials in verification documents.

The lab is complete when there is evidence for the following requirements:

- The correct filesystem, export, export path, and mount target are identified.
- Network rules are sufficient for required flows and cover only the intended source scope.
- Export options have a complete list, valid data types, and verified ordering.
- A can read/write, B can read but cannot write, and C cannot access via the export.
- Root squash is tested in a directory with known permissions, separate from the application user test.
- No bootstrap path or other export remains that violates the authorization goal.
- An owner is assigned to track the configuration; lab resources are retained or cleaned up according to agreed purpose and cost.

A verifiable File Storage access policy must connect **network source → applied export → effective identity → data operation**. Tracking this full chain helps explain errors and avoids concluding permissions are right from a single successful mount.
