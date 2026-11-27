# File Share Authentication and Authorization

In the **CLOUD_PROVIDERS_AZURE** module, learners explore Microsoft Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute services, storage, and data, while learning how to deploy, monitor, protect, and control costs for application architectures. In the **File and Disk Storage** chapter, choosing the right **authentication** and **authorization** mechanisms for an **Azure Files file share** determines who can connect to, read, modify, or administer files in the system.

A common scenario: the Finance team needs to edit reports in the `Finance` folder; the Audit team must only have read access; and other teams must not open the documents. Administrators want to use centralized identities instead of sharing a common password. Azure Files offers different options for SMB, NFS, and FileREST, so a single mechanism cannot be mechanically applied to every protocol.

After this lesson, you will be able to:

- Distinguish between sign-in identity, file share-level permissions, directory/file ACLs, and network restrictions.
- Choose Azure Files authentication via **SMB with identity** or **storage account key** based on requirements and risks.
- Understand three key SMB identity sources: **Active Directory Domain Services (AD DS)**, **Microsoft Entra Domain Services**, and **Microsoft Entra Kerberos**.
- Assign Azure RBAC at the share level, configure NTFS permissions, and verify **effective permissions**.
- Explain why **SAS for FileREST does not replace SMB authentication**, and why **NFS** follows a different control model.
- Perform Azure CLI/PowerShell checks and diagnose permission or port 445 connectivity errors.

## 1. Azure Files and File Share Access Paths

**Azure Files** provides Azure-managed file shares, allowing applications or users to access files over supported protocols. A file share resides inside a **storage account**. Access options to distinguish:

| Interface | Use cases | Access mechanisms to consider |
|---|---|---|
| **SMB** | Windows/Linux VMs, enterprise file shares, shared folders | Kerberos-based identity when configured, or storage account key; share-level permissions and NTFS ACLs |
| **NFS 4.1** | Linux workloads and specialized applications | Network constraints, UID/GID, and POSIX permissions; does not directly follow the SMB Kerberos/RBAC workflow |
| **FileREST API** | Applications or automation calling HTTPS APIs against Azure Files | Shared Key, SAS, and authentication methods supported by the API/version; not an SMB session |

Protocol support, authentication mechanisms, and accompanying features also depend on **storage account kind, SKU/tier, region, and deployment time**. Verify those prerequisites before designing. This lesson focuses primarily on **Azure Files over SMB**, where per-user and per-group authorization requirements are most common.

**Do not confuse Azure Files with Azure Managed Disks**: a managed disk is block storage for a VM; file permissions inside the disk are enforced by the OS/file system. Azure Files is a network-protocol file-sharing service featuring both a Storage security layer and a file/directory permission layer.

### 1.1. Three layers of control

```text
User machine / application
        |
        | 1. Network connectivity (DNS, routes, TCP 445, firewall, private endpoint)
        v
Azure Files endpoint
        |
        | 2. Authentication: SMB identity Kerberos or storage account key
        v
File share-level access
        |
        | 3. Share-level authorization (e.g., Azure RBAC)
        v
NTFS permissions on directories and files
        |
        | 4. DACL/ACE, owner, group, effective permissions
        v
Read / write / rename / delete (or denied)
```

This is a conceptual diagram for an identity-based SMB flow. For account key or FileREST access, the permission evaluation model has important differences explained later.

A successful SMB connection at the network layer **does not prove** a user has permission to read a folder. Conversely, a user with both an appropriate share-level role and NTFS ACL still cannot access files if DNS, routing, or port 445 is blocked.

## 2. How Do Authentication and Authorization Differ?

**Authentication** answers the question *"Who is accessing?"*. When using SMB identity-based authentication, the client proves its identity to the configured Kerberos mechanism. When using an account key, the service receives credentials based on the storage key rather than verifying individual user identities in the same manner.

**Authorization** answers the question *"Is that identity allowed to perform this operation?"*. In identity-based SMB, both must be evaluated:

1. **Share-level permissions**: roles/permissions at the file share level enforced by Azure Files.
2. **File/directory permissions**: NTFS-style ACLs (directory/file-level permissions) stored on the share.

For example: an employee may hold the `Storage File Data SMB Share Reader` role at the share level while having NTFS `Modify` on the `Finance` folder. Actual effective access remains limited by the **read-only share-level layer**. If the share level grants Modify while the ACL grants only Read, the user still cannot write. Both layers participate, and effective permissions cannot exceed the stricter layer.

## 3. SMB Authentication Methods in Azure Files

Azure Files supports Kerberos-based identity integrations, subject to feature and SKU limits. Common options include:

| Identity source | Suitable scenario | Preparation requirements |
|---|---|---|
| **On-premises AD DS** | Organizations with traditional AD DS domain controllers and domain-joined users/VMs | Configure storage account integration with AD DS, identity sync when using Entra ID RBAC, Kerberos, DNS, DC connectivity |
| **Microsoft Entra Domain Services** | Want Azure-managed domain services for workloads using Kerberos/LDAP/NTLM per service capabilities | Managed domain, domain join and network/DNS reachability to managed domain, supported accounts/groups |
| **Microsoft Entra Kerberos** | Designing SMB sign-in with Entra Kerberos under supported conditions, typically involving hybrid identities | Eligible devices and users, identity sync/delegation per feature requirements, Entra Kerberos setup, and Kerberos tickets |

**Note:** Not all user types, devices, domain configurations, SKUs, or cross-tenant scenarios are supported equally. For example, using **cloud-only identities** with Entra Kerberos can depend on feature status and deployment prerequisites; verify before committing to a cloud-only user population. Standard Microsoft Entra ID **does not automatically provide an SMB Kerberos session** simply because a user signed into the Azure Portal.

Within a single storage account, do not assume you can simultaneously enable arbitrary multiple **directory service identity sources** for SMB. Choose one identity source per supportability rules and plan a migration path if switching is required.

### 3.1. AD DS: enterprise identities and groups

With **Active Directory Domain Services**, users sign in with domain accounts and clients obtain Kerberos tickets for the SMB service. The storage account is configured to participate in the corresponding authentication model. AD groups enable role-based assignment rather than granting permissions per individual employee.

Examples:

- `CONTOSO\FinanceEditors`: can modify contents in the accounting folder.
- `CONTOSO\FinanceAuditors`: read-only.
- `CONTOSO\IT-FileAdmins`: delegated to administer ACLs per procedure.

To use Azure RBAC at the share level for corresponding identities, ensure accounts and groups are mapped/synchronized to Microsoft Entra ID via a supported method. For certain non-synchronized identities, organizations may need a **default share-level permission** as supported by Azure Files, while understanding the broad impact of a default permission.

### 3.2. Microsoft Entra Domain Services

**Microsoft Entra Domain Services** provides a managed domain offering traditional domain capabilities required by many legacy applications. Eligible VMs and users can access Azure Files over SMB using this domain-based authentication model.

It is **not** another name for Entra ID: Entra Domain Services is a separate domain service requiring proper configuration, networking, DNS, and administration. User accounts may need to satisfy credential synchronization prerequisites before authentication works, depending on domain history and configuration.

### 3.3. Microsoft Entra Kerberos

Entra Kerberos enables certain Windows environments to use Kerberos to access Azure Files with Microsoft Entra ID identities under supported conditions. This is an attractive option when an organization wants to reduce reliance on traditional domain controllers for part of the access flow.

However, do not assume every **Entra joined** computer can automatically mount every share. Factors to check include:

- Whether users belong to identity types supported by the feature.
- Device join state, OS version, and sign-in configuration.
- Kerberos configuration on both the storage account and tenant.
- Domain/realm, SPNs, tickets, and network/DNS conditions.
- Whether share-level permissions and NTFS ACLs are configured for the right principals/groups.

**Common thread across all three identity-based methods:** having a valid identity solves only part of the equation. Share-level permissions and NTFS ACLs still govern file operations.

## 4. Storage Account Key Authentication: Simple but Broad Privilege

Azure Files over SMB can also be mounted with a **storage account key** if the account kind and policy allow it. A legacy configuration example might specify the storage account name as the username and the account key as the password when mounting the share.

An account key is a secret carrying **very broad privileges** over the storage account. When SMB mounts using a key, per-user/per-group controls and NTFS ACLs do not behave like an employee's Kerberos session: key-based access is administrative/superuser in nature and can **bypass standard user NTFS ACL restrictions**.

Therefore:

- Do not distribute account keys to all employees to mount shares themselves.
- Do not place keys in source code, `.ps1` scripts, container images, Git repositories, chat, or support tickets.
- Do not treat an account-key mount as proof that NTFS ACLs are configured properly.
- When legacy workloads require a key, store it in a controlled secret vault; restrict identities allowed to read or regenerate keys.
- Plan to migrate to **identity-based SMB authentication** when usage and environment support it.

**Key rotation:** a storage account typically provides two access keys to support rotation. Regenerating a key invalidates clients currently using that key and any signatures/SAS tokens bound to it. Rotating keys requires a client update plan, monitoring, and rollback; it is not a harmless operation when hundreds of machines are mounting the share.

## 5. Share-Level RBAC: The First Permission Layer

When using **identity-based SMB authentication**, Azure Files evaluates share-level permissions to determine what level of access an identity has to the share. Azure RBAC provides built-in roles specifically for **SMB file shares**:

| Role | Typical purpose | Notes |
|---|---|---|
| `Storage File Data SMB Share Reader` | Read access at the share level | Does not turn denied NTFS ACLs into allowed access |
| `Storage File Data SMB Share Contributor` | Read/write access at the share level | NTFS permissions can still restrict folders/files |
| `Storage File Data SMB Share Elevated Contributor` | Permits supported elevated operations, typically used when administering file permissions | Grant only to authorized admin groups; never grant broadly |

Built-in role names must be used accurately during configuration; do not confuse them with `Storage File Data Contributor`, roles meant exclusively for Blob Storage, or the ARM `Contributor` role.

A role assignment has three main parts:

```text
Principal:  supported Entra ID group / user
Role:       Storage File Data SMB Share Contributor
Scope:      .../fileServices/default/shares/team-docs
```

Azure RBAC can be assigned at the **file share**, storage account, or an appropriate parent scope. To follow least privilege, use the **smallest scope** that meets requirements. Roles at the storage account level can affect multiple shares in the account and therefore require careful evaluation.

### 5.1. Default share-level permissions

In scenarios supported by Azure Files, a **default share-level permission** can be configured for identities authenticated via the configured Kerberos source. This addresses certain cases where RBAC cannot be assigned per principal, such as AD DS identities not synced to Entra ID.

However, a default permission is a **broader** choice than assigning a role to a specific group. If Contributor or Elevated Contributor is set as the default, every authenticated identity in scope receives that share-level permission first, relying solely on ACLs to restrict them. This increases risk if NTFS ACLs are misconfigured.

Prefer assigning roles to supported **functional groups**; use default permissions only with a clear justification and impact assessment. Never treat default permissions as a shortcut to skip ACL management.

### 5.2. Do not confuse the management plane with the SMB data plane

The Azure `Reader` role at the resource group level allows viewing certain management metadata, which does not mean reading files over SMB. `Contributor` on a subscription permits many resource administration actions, yet **does not automatically provide a Kerberos session with NTFS rights to read every file**.

Conversely, permission to read a share over SMB does not grant rights to alter storage account settings, retrieve account keys, or create role assignments. Separate those who **manage Azure resources**, those who **manage identities/permissions**, and those who **consume file contents**.

## 6. NTFS ACLs: The Second Permission Layer

Azure Files SMB supports directory/file permissions using the **Windows-style NTFS ACL** model. An ACL (Access Control List) contains **ACEs** (Access Control Entries) defining which principals or groups are allowed or denied specific operations.

Common permissions:

| NTFS permission | Typical meaning |
|---|---|
| `Read` / `Read & Execute` | View contents, attributes, and execute depending on file type |
| `Write` | Create or write data within the permission scope |
| `Modify` | Read, write, edit, and typically includes delete within the applicable scope |
| `Full Control` | Highest ACL permissions, including managing permissions per supported model |
| `Deny` | Explicitly denies the declared permission for a principal or group |

Permissions are evaluated based on identity and group memberships, allow/deny ACEs, inheritance, owner, and Windows access check rules. `Deny` ACEs can cause unexpected results when a user belongs to multiple groups. Therefore, manage via **least-privilege Allow entries on appropriate groups** and avoid widespread explicit Deny entries whenever possible.

### 6.1. ACL inheritance

A folder can hold ACEs inherited by child files and subfolders. For example:

```text
Share: team-docs
  |
  +-- Finance
  |     +-- Reports
  |           +-- Q4.xlsx
  |
  +-- Engineering
        +-- Designs
```

The Finance team needs `Modify` in `Finance` and zero access to `Engineering`. ACLs can be assigned at each department's root folder, allowing inheritance down to child objects. When configuring ACLs, verify the **exact SID/group** and inheritance rules, and remove overly broad permissions if required by policy.

A member with `Contributor` at the share level but no ACL entry on `Finance\Reports` will still be denied read or write access to those files. Conversely, a group with `Reader` at the share level cannot write even if the ACL on `Finance` grants `Modify`.

### 6.2. Permission matrix example

| Group | Share-level RBAC | `Finance` ACL | `Engineering` ACL | Desired outcome |
|---|---|---|---|---|
| `FinanceEditors` | SMB Share Contributor | Modify | No access | Edit within Finance |
| `FinanceAuditors` | SMB Share Reader | Read | No access | Read-only in Finance |
| `EngineeringEditors` | SMB Share Contributor | No access | Modify | Edit within Engineering |
| `FileShareAclAdmins` | Approved share/ACL admin permissions | Appropriate ACL management rights | Appropriate ACL management rights | Maintain permissions per procedure |

This is a target model, not a built-in Azure Files rule. You must create the groups, assign roles, and configure the actual ACLs. Also check permissions on the **share root folder** and traversal rights to subfolders; if misconfigured, a user with rights on `Finance` may still fail when navigating from the root to that folder.

## 7. Effective Permissions: Both Layers Must Pass

With SMB identity-based access:

```text
Effective permissions = share-level permission limit
                        INTERSECTED WITH file/directory NTFS ACL permissions
```

This is a conceptual expression: the system evaluates granted permissions and allow/deny conditions according to each layer's technical rules, rather than a simple set intersection for every advanced Windows right.

Examples:

| Share-level | NTFS ACL | Read operation | Write operation |
|---|---|---|---|
| Reader | Read | Yes, if other conditions allow | No |
| Contributor | Read | Yes | No |
| Contributor | Modify | Yes | Yes |
| Reader | Modify | Yes | No |
| No matching share-level permission | Full Control | No | No |

For actions like **modifying ACLs, taking ownership, deleting**, or accessing data via another mechanism, evaluate the specific permissions and supported mechanisms. Do not infer that `Full Control` on a folder always suffices to alter Azure RBAC settings.

## 8. Sample Deployment Architecture

Suppose an enterprise has Finance and Engineering teams using SMB from Windows VMs inside a VNet. The share resides in Azure Files, connected through a **private endpoint** per network policy.

```text
Finance / Engineering users
           |
           | Sign in on Windows VMs in a supported identity environment
           v
Windows SMB client (Kerberos ticket)
           |
           | DNS: <account>.file.core.windows.net
           | -> private endpoint IP via configured Private DNS
           | TCP 445 inside private network
           v
Azure Files: storage account stfilesprod001
           |
           +-- Share: team-docs
                 |
                 +-- Finance (Finance group ACLs)
                 +-- Engineering (Engineering group ACLs)
```

At the **network** layer, control VNets, DNS, firewalls, NSGs, private endpoints, and routes. At the **identity** layer, use Kerberos via the selected source. At the **authorization** layer, combine share-level RBAC and NTFS ACLs. At the **data protection** layer, enable backups, snapshots/soft delete, logging, and retention policies as appropriate.

A private endpoint **does not replace** Kerberos or ACLs. It changes the network path to Storage but does not verify whether an employee is allowed to open `Finance\Reports`.

## 9. Procedure for Configuring Identity-Based SMB Access

Integrating Azure Files with an identity source is an infrastructure change that can affect users currently mounting shares. Test in a non-production environment first and prepare a transition plan if the share currently relies on account keys.

### Step 1: Select and prepare the identity source

For each environment, verify:

1. The Azure Files account/SKU and SMB protocol support the selected identity integration.
2. Users, groups, client machines, and join state meet requirements.
3. Domain/tenant, DNS, Kerberos tickets, clock synchronization, and connectivity to identity components.
4. Target user groups are created and synced/mapped via a supported mechanism.
5. Network rules and SMB TCP 445 path are designed.

In the Azure Portal, open the storage account → configure **File shares / Identity-based access** or the corresponding configuration section in the current UI. Configure AD DS, Microsoft Entra Domain Services, or Microsoft Entra Kerberos per the selected feature. If using AD DS, supplying domain details, SID, SPN, and related accounts must follow the Azure Files integration guide for your organization's domain; never guess identity values.

After configuration, confirm identity-based authentication status on the storage account and test authentication with **one properly scoped test account**. Do not rush to grant broad permissions before confirming Kerberos works.

### Step 2: Grant share-level permissions using groups

Create Azure RBAC role assignments for appropriate groups on the exact file share. For instance, assign `Storage File Data SMB Share Contributor` to `FinanceEditors` on share `team-docs`, and assign Reader to `FinanceAuditors`.

This sets permissions across the entire share. Restricting access strictly to `Finance` while denying `Engineering` happens at the NTFS ACL layer in the next step.

### Step 3: Mount the share using identity

On a supported Windows client, a user signed in with the matching identity, holding a Kerberos ticket and network reachability to Azure Files, mounts the share using the standard UNC path:

```text
\\<storage-account>.file.core.windows.net\<share-name>
```

Do not enter an account key as the password if your goal is to test individual employee Kerberos permissions. An existing SMB session to the same server under different credentials can skew test results; inspect credential caches and active sessions.

### Step 4: Assign ACLs on directories and files

An authorized administrator connects with an appropriately privileged identity, creates or selects folders, and sets group-based ACLs. Start on a test folder, verify inheritance, and only then apply to production data.

### Step 5: Test the allow/deny matrix

Sign in **for real** as each test user persona (Editor, Auditor, unauthorized user), perform read/create/edit/delete operations within test scope, and verify the matrix matches. Do not rely solely on seeing a drive letter appear in File Explorer.

### Step 6: Document and operate

Document the identity source configuration, RBAC scopes, AD/Entra groups, critical ACLs, share owners, group membership add/remove workflows, backups, and troubleshooting runbooks. When employees change departments or leave the company, update memberships and verify obsolete permissions are removed.

## 10. Hands-On Verification and RBAC Assignment with Azure CLI

The following examples assume an **Azure Files SMB share already exists**, the storage account and identity system are configured, and the operator has resource read rights plus (for assignment steps) permission to create role assignments. Commands use Azure CLI in Bash/Azure Cloud Shell. You do not need to read account keys to assign share-level RBAC.

Set variables for the **illustrative** environment:

```bash
az account show --output table
az account set --subscription "<subscription-id>"

RG="rg-files-dev"
ACCOUNT="stfilesdev001"
SHARE="team-docs"
```

### 10.1. Inspect the storage account and identity configuration

```bash
az storage account show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name,kind:kind,identityBasedAuth:azureFilesIdentityBasedAuthentication}" \
  --output json
```

The `identityBasedAuth` field shows SMB identity-based authentication settings if returned by the account/API. An empty, missing, or unconfigured value should be verified further in the Portal and against service capabilities; do not assume your organization's Entra ID is automatically enabled for SMB.

### 10.2. View the File Share and retrieve the Azure Resource ID

```bash
az storage share-rm show \
  --resource-group "$RG" \
  --storage-account "$ACCOUNT" \
  --name "$SHARE" \
  --output json

SHARE_RESOURCE_ID=$(az storage share-rm show \
  --resource-group "$RG" \
  --storage-account "$ACCOUNT" \
  --name "$SHARE" \
  --query id --output tsv)
```

`share-rm` is a control-plane command for managing share resources; it differs from reading file contents over SMB or the FileREST data plane. A share resource ID typically looks like:

```text
/subscriptions/<subscription-id>/resourceGroups/<resource-group>
/providers/Microsoft.Storage/storageAccounts/<account>
/fileServices/default/shares/<share>
```

Use the **actual Resource ID** returned by the CLI rather than manually concatenating strings for an existing resource.

### 10.3. Grant a share-level role to an Entra ID group

An RBAC administrator can assign the role as follows:

```bash
FINANCE_GROUP_OBJECT_ID="<entra-group-object-id>"

az role assignment create \
  --assignee-object-id "$FINANCE_GROUP_OBJECT_ID" \
  --assignee-principal-type Group \
  --role "Storage File Data SMB Share Contributor" \
  --scope "$SHARE_RESOURCE_ID"
```

For a read-only group:

```bash
AUDIT_GROUP_OBJECT_ID="<entra-auditors-group-object-id>"

az role assignment create \
  --assignee-object-id "$AUDIT_GROUP_OBJECT_ID" \
  --assignee-principal-type Group \
  --role "Storage File Data SMB Share Reader" \
  --scope "$SHARE_RESOURCE_ID"
```

Use only the **Object ID of the exact Entra ID group** tied to identities supported by your SMB method. When permissions are assigned to groups, verify group/SID mapping and membership in the actual AD/Kerberos environment. Never assign a role to a similarly named group just because it was easy to spot in the Portal.

Review role assignments:

```bash
az role assignment list \
  --scope "$SHARE_RESOURCE_ID" \
  --include-inherited \
  --output table
```

`--include-inherited` shows effective roles inherited from parent scopes; filtering/display options vary by CLI version. Role assignments may take time to propagate. Users may also need to refresh Kerberos tickets or sign out and back in for new group memberships to take effect.

**Safety practice:** In live environments holding sensitive data, do not grant `Storage File Data SMB Share Elevated Contributor` to regular Editors just so they can create/edit files. Strictly separate ACL administrators from content editors.

## 11. Hands-On on Windows: Connecting and Checking NTFS ACLs

The examples below use Windows PowerShell on a VM/device with an appropriate identity and SMB reachability. Replace account, share, and domain group names with real values. **Do not use an account key during user permission verification steps**, as it invalidates Kerberos/ACL testing.

### 11.1. Check DNS and TCP 445

```powershell
$server = "stfilesdev001.file.core.windows.net"
Resolve-DnsName $server
Test-NetConnection -ComputerName $server -Port 445
```

If using a private endpoint, DNS resolution must match your private network path and configured resolver. Components such as Azure Private DNS, routes, NSGs, or corporate firewalls can cause connection failures. Never conclude "missing NTFS permissions" before TCP 445 succeeds.

### 11.2. Check identity and Kerberos

```powershell
whoami
whoami /groups
klist
```

`whoami` and `whoami /groups` show the active user session and groups recognized in the Windows access token. `klist` lists cached Kerberos tickets. Depending on the identity method, you may need to verify tickets/SPNs for the SMB service and refresh the login session after group membership changes.

Do not paste full lists of group SIDs, Kerberos tickets, or sensitive domain metadata into public support tickets. Share only the diagnostic details necessary with appropriate access restrictions.

### 11.3. Mount the file share using the signed-in identity

```powershell
net use Z: \\stfilesdev001.file.core.windows.net\team-docs /persistent:no
Get-SmbConnection
```

This command expects to use the prepared Windows/Kerberos user session. If prompted for credentials or denied access, inspect the identity source, join status, Kerberos tickets, existing SMB sessions to the same server, and network policies. **Do not "fix" it by typing the storage account key**, as that renders user/group permission testing meaningless.

### 11.4. View current ACLs

```powershell
icacls "Z:\"
icacls "Z:\Finance"
```

The output displays existing ACEs and inherited permissions. If the `Finance` directory does not exist yet, create it with an authorized, properly permissioned account per share governance rules; never modify production folders without backing up ACL metadata first.

### 11.5. Assign ACLs to groups in a test environment

Suppose group `CONTOSO\FinanceEditors` needs Modify on `Finance` and its descendants; an ACL administrator can run:

```powershell
# Run only after receiving ACL administration permissions and reviewing group names.
icacls "Z:\Finance" /grant "CONTOSO\FinanceEditors:(OI)(CI)M"

# For the audit group, read-only, also applied to child files/folders.
icacls "Z:\Finance" /grant "CONTOSO\FinanceAuditors:(OI)(CI)RX"

# Re-read ACLs:
icacls "Z:\Finance"
```

In `icacls`, `(OI)` is object inheritance for files, `(CI)` is container inheritance for folders, `M` is Modify, and `RX` is Read & Execute. Design inheritance and existing ACEs carefully; `/grant` does not automatically strip overly broad legacy permissions. If permissions for another group must be removed, review and adjust ACLs safely first.

The account running `icacls` must hold **ACL modification rights on the directory** plus the appropriate share-level permission. If `icacls` reports `Access is denied`, verify both permission layers instead of falling back to an account key or granting Full Control to everyone.

### 11.6. Testing with three accounts

| Test account | Read `Finance\Report.txt` | Create/edit files in `Finance` | Read `Engineering` |
|---|---|---|---|
| Member of `FinanceEditors` | Succeeds | Succeeds | Denied by design |
| Member of `FinanceAuditors` | Succeeds | Denied | Denied |
| User in neither group | Denied | Denied | Depends on separately granted rights, not allowed by default |

Always test using **real authenticated sessions** for each user. If you test all connections with an account key, all three scenarios may behave identically and fail to reflect target authorization.

## 12. SAS and FileREST: Not an SMB Sign-In Mechanism

A **Shared Access Signature (SAS)** provides time-limited delegated authorization for requests to supported Storage APIs. For Azure Files, SAS can be used with **FileREST** according to supported scopes/permissions and account kinds; REST calls signed with Shared Key or Microsoft Entra ID/OAuth methods supported by each API version must be distinguished using corresponding feature documentation.

**A SAS URL does not replace username/password or Kerberos in an SMB mount command.** You cannot mount a share by pasting a SAS query string onto a UNC path:

```text
# Not valid SMB mount syntax:
\\account.file.core.windows.net\team-docs?sv=...&sig=...
```

When an application calls FileREST, permissions on the SAS/REST request follow that API model; do not assume this yields the exact same behavior as share-level SMB RBAC and NTFS ACLs in a Kerberos session. In particular, requests using account keys carry high privileges and must be managed separately.

**User delegation SAS for Azure Blob Storage** is not a token you can automatically use for Azure Files. Do not confuse `Blob SAS` with `File SAS`, and do not use Blob API documentation to infer FileREST authorization capabilities.

### 12.1. Which method should a backend application choose?

| Workload | Approach |
|---|---|
| Windows users needing `Z:\Finance` | SMB + Kerberos + share-level permissions + NTFS ACLs |
| Application calling Storage management APIs | Azure Resource Manager/RBAC management plane as needed |
| Application calling FileREST | Authentication/authorization supported by FileREST API and version; prefer identity when supported |
| Legacy system mounting SMB via account key | Restrict secret/privileges and plan gradual migration to identity |
| Client needing only temporary file downloads | Evaluate API/backend design, token lifetime, and sharing mechanisms supported by FileREST; never hand account keys to clients |

Not every SDK and protocol handles Entra ID the same way. **An Azure VM's managed identity does not automatically turn into a Kerberos ticket for a user mounting SMB.** For identity-based SMB, proper user identities and Kerberos infrastructure are required; for HTTP/REST calls, separate application authentication flows may apply.

## 13. NFS File Shares: A Different Security Model from SMB

For **Azure Files NFS 4.1**, do not apply share-level SMB roles or NTFS ACLs as if it were the same protocol. Controls typically include:

- Private network connectivity, network restrictions, routes, and private endpoints per supported deployment type.
- UID/GID and **POSIX mode bits** on directories/files.
- **Root squash** where supported and appropriately configured, to limit root privileges originating from clients.
- NFS client host administration, user/group mapping, and related network services.

NFS mounts in standard Azure Files patterns do not directly use Kerberos user identity/SMB RBAC to authenticate individual users the way SMB does. Network protection and host security play an especially vital role.

Linux example:

```bash
# Inspect POSIX directory permissions after the NFS share is mounted.
id
ls -ld /mnt/azfiles/team-docs
ls -l /mnt/azfiles/team-docs
```

Running `chmod` or `chown` on an NFS share must align with actual UID/GID and root squash settings. Never try applying SMB `icacls` examples directly onto an NFS mount.

## 14. Layered Troubleshooting Approach

When users report `Access is denied`, `System error 53`, inability to mount a share, or seeing folders without being able to open files, investigate **in order**, avoiding random broad permission grants.

| Symptom | Likely possibilities | What to check |
|---|---|---|
| Cannot resolve Storage hostname | Incorrect DNS, misconfigured private DNS zone/link | `Resolve-DnsName`, endpoint, and resolver |
| TCP 445 fails to connect | Firewall/ISP, NSG, UDR, private endpoint, or network routing | `Test-NetConnection -Port 445`, effective routes |
| SMB repeatedly prompts for credentials | Invalid Kerberos session, wrong domain/tenant, host ineligible | Join status, `klist`, SPN, account source |
| One user can mount while another cannot | Different share-level RBAC/default permission, group membership, or Kerberos ticket | Role assignments, SID/group, sync status |
| Mounts successfully but cannot read `Finance` | NTFS ACL/inheritance or missing traverse rights on parent folder | `icacls` on root, `Finance`, and target file |
| Can read but cannot create or edit files | Reader share-level role, read-only ACL, or missing create/delete rights | Share-level RBAC + NTFS Modify |
| Unauthorized user can still read | Account key session, overly broad group/ACL, or share-level default permission | `Get-SmbConnection`, ACLs, and role/default permission |
| Access remains wrong after group change | Membership/ticket or RBAC not yet refreshed in active session | Sign out/in, refresh tickets per procedure, propagation delay |
| Application loses connection after key rotation | Still using old account key | Inventory legacy clients and secret update workflow |
| FileREST succeeds while SMB denies access | Two distinct authentication/authorization mechanisms | Do not infer SMB permissions from REST calls |

### 14.1. Eight-step investigation workflow

1. **Identify the protocol:** SMB, NFS, or FileREST; never reuse a single set of assumptions.
2. **Verify the target:** subscription, storage account, share, and hostname; avoid mixing dev and prod.
3. **Verify networking:** DNS, ports, firewall/NSG, private endpoint, routing; capture exact error codes.
4. **Determine effective identity:** which Kerberos user/group or account key; verify whether another SMB session holds stale credentials.
5. **Check share-level authorization:** principal/group Azure RBAC, inherited roles, and default share-level permissions if configured.
6. **Check NTFS ACLs:** ACEs on parent/target folders, inheritance, Deny rules, and permissions needed for each operation.
7. **Correlate recent changes:** RBAC permissions, group memberships, Kerberos tickets, key rotation, or identity config updates.
8. **Apply minimal fix and re-test:** test with Editor, Auditor, and unauthorized accounts; record pass/fail results.

For production applications, store logs and request correlations with proper access controls. Azure Monitor, Storage metrics, file service logs, and client/domain controller event logs can aid analysis, though available log types and fields depend on configuration and protocol.

## 15. Common Mistakes

**Assigning only Azure RBAC and ignoring NTFS ACLs.** Share-level Contributor does not allow writing to a folder where the ACL is Read-only or Deny.

**Configuring only NTFS Full Control and ignoring share-level permissions.** Even with Full Control at the file ACL level, an identity-based SMB session still requires the appropriate permission at the share layer.

**Testing permissions with a storage account key.** Results do not validate employee Kerberos access; keys hold broad privileges and can bypass user-level ACLs.

**Confusing Azure RBAC resource management with SMB data access.** `Reader`/`Contributor` at the resource group level is not equivalent to `Storage File Data SMB Share Reader`/`Contributor`.

**Assuming "Entra joined" automatically means SMB mounts succeed.** You must have a supported identity source, user/OS compatibility, Kerberos, RBAC, ACLs, and network path.

**Granting Elevated Contributor to all employees.** ACL administration rights must be separated from ordinary file editing permissions.

**Enabling default share-level Contributor for everyone without auditing ACLs.** Default permissions expand the blast radius if any folder contains overly permissive ACEs.

**Treating SAS or Blob user delegation SAS as an SMB password.** SAS is a token mechanism for supported API requests, not a Kerberos session or SMB password.

**Checking only port 445 and concluding access works.** An open port does not mean Kerberos, RBAC, and ACLs are valid.

**Forgetting inheritance and rights from other groups.** Users can belong to multiple groups; ACEs and share-level roles inherited from other scopes can alter the outcome.

## 16. Operations and Security Checklist

- [ ] Confirmed whether the Azure Files share uses SMB, NFS, or FileREST and verified SKU support conditions.
- [ ] Selected an SMB identity-based authentication source compatible with devices and users.
- [ ] Verified DNS, routes, private endpoints, network restrictions, and TCP 445 (for SMB).
- [ ] Created functional groups, avoiding widespread manual per-user assignments.
- [ ] Assigned `Storage File Data SMB Share Reader/Contributor` roles at an appropriately narrow scope.
- [ ] Reviewed default share-level permissions; avoided overly broad defaults.
- [ ] Configured NTFS ACLs accurately per directory/file and verified inheritance, Deny, and traversal.
- [ ] Granted separate privileges to ACL administrators; Editors/Auditors hold no unnecessary admin rights.
- [ ] Tested with real Kerberos identities rather than only mounting via account keys.
- [ ] Checked user/group mapping, Kerberos tickets, and sync/role assignment propagation delays.
- [ ] Distinguished SMB permissions from FileREST/SAS and NFS models.
- [ ] Protected account keys, established rotation plans, and inventoried legacy clients.
- [ ] Configured backups/snapshots, soft delete where supported, logging, and recovery procedures.
- [ ] Tested allow cases, deny cases, network loss, and group/permission changes.

## 17. Scenario Exercise

A company uses the Azure Files share `company-docs` over SMB with a supported identity source. Folders `Finance` and `Engineering` reside in the same share. Requirements:

1. Accounting can create/edit/delete business files in `Finance`.
2. Audit can only read `Finance`.
3. Engineers can edit in `Engineering` but must not read `Finance`.
4. The ACL administration team is separate, and account keys are not shared with employees.
5. Windows clients connect over a private endpoint using their respective identities.

**Task:** Propose share-level RBAC for each group, ACLs at the root folder and both subfolders, methods to verify Kerberos/DNS/port 445, and a test matrix for at least three users. Explain two cases: an Auditor with NTFS Modify ACL but share-level Reader; an Engineer with share-level Contributor but no `Finance` ACL.

**Reference solution guide:** Groups that modify contents receive share-level Contributor; Audit receives Reader. In NTFS ACLs, FinanceEditors receive Modify on `Finance`, FinanceAuditors receive Read, EngineeringEditors receive Modify on `Engineering`; other groups receive no grants on folders outside their responsibility. On the share root, configure traversal and inheritance carefully so broad access is not inadvertently granted. Verify with real users via `whoami`, `klist`, `net use`, `icacls`, and read/write tests; in both comparison cases, access remains constrained by the stricter layer.

### Self-Check Questions

**1. What are the two primary authorization layers for identity-based SMB in Azure Files?** Share-level permissions and NTFS file/directory ACLs.

**2. Does assigning the `Contributor` role on a resource group automatically allow everyone to read shares over SMB?** No. SMB authentication with an appropriate identity and data permissions is required.

**3. Why should account keys not be given to employees to mount shares?** Account keys carry very broad privileges, do not enforce per-user identity authorization, and invalidate ACL testing.

**4. Is Microsoft Entra Domain Services identical to standard Entra ID user accounts?** No; it is a managed domain providing domain capabilities that require separate configuration.

**5. Can a Blob user delegation SAS be used in an SMB mount path?** No. That is a token mechanism for supported Blob API requests.

**6. For NFS, do you use `icacls` and `Storage File Data SMB Share` roles directly to manage access?** No. NFS uses its own network controls and POSIX permissions model.

**7. If `Test-NetConnection` on port 445 fails, is the next step changing NTFS ACLs?** No. Fix networking/DNS/routing issues first.

## Conclusion

For **Azure Files SMB**, secure design requires accurately defining **who signs in**, **share-level permissions**, and **NTFS ACLs on files/directories**. AD DS, Microsoft Entra Domain Services, and Microsoft Entra Kerberos are identity sources chosen according to supported environments; Azure RBAC and ACLs complement rather than replace one another.

Account keys may be convenient for legacy systems yet carry broad privileges; SAS applies to supported APIs rather than SMB logins; and NFS follows a separate security model. Combine identity, RBAC, ACLs, private networking, logging, backups, and per-group permission testing so Azure application file shares stay both usable and properly protected.
