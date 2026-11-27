# Synchronizing File Servers with Azure File Sync

Many enterprises already operate Windows file servers serving employees over SMB, containing project documents, operational records, images, and department-level shared folders. When expanding to Microsoft Azure, they want to preserve the familiar network drive experience for opening files, reduce disk capacity maintained in offices, synchronize data across branches, and establish centralized cloud storage.

**Azure File Sync** synchronizes **Windows Server** data with **Azure Files**, and can optionally use **cloud tiering** to cache frequently accessed files on the local server while moving less-used file contents to Azure. Users continue accessing the file server over SMB as before; Azure holds the central copy in an Azure file share.

This lesson belongs to the **File and Disk Storage** chapter of the **CLOUD_PROVIDERS_AZURE** module. Building on knowledge of subscriptions, resource groups, identity, networking, compute services, storage, and cost, we design a file server synchronization solution that can be deployed, monitored, protected, and recovered in a controlled manner.

> **Key takeaway:** Azure File Sync provides **bidirectional synchronization with Azure Files plus local caching**—it is not a standalone backup tool, not block-level disk replication, and does not automatically provide real-time file lock synchronization across all servers.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain when to use Azure File Sync instead of accessing Azure Files directly over SMB.
2. Distinguish **Storage Sync Service**, **sync group**, **cloud endpoint**, **server endpoint**, **registered server**, and **Azure File Sync agent**.
3. Design synchronization between one or more Windows file servers and an Azure file share.
4. Understand the sync workflow, cloud change detection, cloud tiering, and how files are recalled when opened.
5. Prepare Windows Server, NTFS volumes, Azure Storage, identity, and appropriate HTTPS connectivity.
6. Configure Azure File Sync via the Azure Portal and verify from Windows Server.
7. Monitor sync health, and troubleshoot non-syncing files, agent errors, disk space shortages, and networking issues.
8. Design data protection, backup, and recovery when a file server or site fails.
9. Evaluate constraints on concurrent synchronization, access permissions, security, and cost.

## 2. The Challenge: Keeping Local File Servers While Moving Data to Azure

Suppose a company has two offices, each using a Windows file server for the **D:\Shares\Projects** folder. Employees access files via SMB paths such as:

~~~text
\\fileserver-hcm\Projects
\\fileserver-hn\Projects
~~~

Common challenges:

- One branch frequently needs to access data from the other branch over a high-latency WAN.
- Current file servers have nearly full disks, yet most older documents are rarely opened.
- When a server fails, data must be recovered and a replacement server provisioned.
- The IT team wants centralized storage in Azure and visibility into synchronization status.

There are three different approaches:

| Option | Where do users connect? | Characteristics |
|---|---|---|
| Traditional file server | SMB share on a single Windows Server | No built-in cloud copy or cross-branch data availability |
| Direct Azure Files | Azure Files SMB/NFS endpoint per service capabilities | No Windows file server cache required, but clients need network path and appropriate authentication |
| **Azure File Sync** | SMB share on local Windows Server; agent syncs with Azure Files | Preserves local access interface, provides a shared cloud endpoint and optional cloud tiering |

Azure File Sync fits when an organization **wants to continue serving SMB shares locally** while using Azure Files to centralize data and synchronize across servers. If no local server is needed, direct access to Azure Files may be simpler.

## 3. Architecture and Components

~~~mermaid
flowchart TB
    U1["Office A employees"] -->|"SMB to local server"| S1["Windows Server A<br/>D:\Shares\Projects<br/>Azure File Sync agent"]
    U2["Office B employees"] -->|"SMB to local server"| S2["Windows Server B<br/>D:\Shares\Projects<br/>Azure File Sync agent"]
    S1 <-->|"Content sync over HTTPS"| F["Azure Files<br/>file share: projects"]
    S2 <-->|"Content sync over HTTPS"| F
    M["Storage Sync Service<br/>Sync group: projects-sync"] -. "Registration, config, monitoring" .-> S1
    M -. "Registration, config, monitoring" .-> S2
    M -. "Cloud endpoint" .-> F
~~~

The diagram illustrates **one sync group** linking **one Azure file share** with **two server endpoint folders**. The servers do not necessarily communicate directly with one another; content synchronization flows through the Azure file share. Storage Sync Service manages sync relationships, while file data is stored in Azure Files.

### 3.1. Terminology table

| Component | Role | Example |
|---|---|---|
| **Storage Account** | Azure resource containing the Azure file share, responsible for networking, security, redundancy, and billing | stfilesordersdemo |
| **Azure file share** | Centralized Azure Files storage location | projects |
| **Storage Sync Service** | Azure resource managing registered servers and sync groups | stsync-projects |
| **Sync group** | Synchronization relationship between one cloud endpoint and associated server endpoints | projects-sync |
| **Cloud endpoint** | Reference to an Azure file share within a sync group | Azure file share projects |
| **Registered server** | Windows Server with the agent installed and registered to a Storage Sync Service | fileserver-hcm |
| **Server endpoint** | Path on a server volume added to a sync group | D:\Shares\Projects |
| **Azure File Sync agent** | Component installed on Windows Server to track changes, sync, and perform cloud tiering | Supported agent version |

A **sync group has one cloud endpoint** and can have multiple server endpoints within supported limits. Each Azure file share should participate as a cloud endpoint strictly per service uniqueness rules; do not assume the same share can be reused across multiple sync groups.

### 3.2. How do cloud endpoints and server endpoints differ?

The **cloud endpoint** represents the Azure file share where data is centrally stored. A **server endpoint** represents the local path managed by the agent where employees can use an SMB share to read and write.

Example:

~~~text
Storage Sync Service: stsync-projects
└── Sync group: projects-sync
    ├── Cloud endpoint: stfilesordersdemo / projects
    ├── Server endpoint: fileserver-hcm / D:\Shares\Projects
    └── Server endpoint: fileserver-hn  / D:\Shares\Projects
~~~

Importantly, **local paths of server endpoints do not have to match**, provided each path complies with service limits. The sync group determines which endpoints share a dataset.

### 3.3. Windows Server file shares remain a separate configuration

A server endpoint does not automatically create a properly named and permissioned SMB share. You still must manage:

- The SMB share name, such as **Projects**.
- Share-level permissions.
- NTFS Access Control Lists (ACLs).
- User/group identities (typically in Active Directory).
- DNS and network connectivity from clients to the server.

Azure File Sync synchronizes supported data and metadata, including NTFS ACLs, but **SMB share configurations on each Windows Server are not automatically recreated with identical share-level settings** when adding a new server.

## 4. How Does the Sync Flow Work?

### 4.1. A file is created on Server A

Suppose an employee saves a file:

~~~text
\\fileserver-hcm\Projects\Design\diagram-v2.pptx
~~~

A typical cycle:

1. Windows Server A receives the write operation via SMB and writes data to the NTFS volume.
2. The Azure File Sync agent detects the change via file system monitoring mechanisms.
3. The agent syncs supported content and metadata to the Azure file share.
4. Windows Server B receives the change through its sync process with the same cloud endpoint.
5. Office B employees see the file in the corresponding folder once synchronization finishes.

**This is not a system-wide synchronous write within a single transaction.** There may be a delay between Server A finishing the write and Server B seeing the new version.

### 4.2. Changes flow in both directions

Azure File Sync can synchronize:

- **Server → Azure file share:** create, modify, rename, and delete within supported scope.
- **Azure file share → server:** changes on the cloud endpoint are detected and pulled down to server endpoints.
- **Server A → cloud → Server B:** sharing data through the common cloud endpoint.

Because deletions and overwrites are also changes, human errors or ransomware **can propagate**. Data protection requires separate backups, snapshots, and permission policies.

### 4.3. Cloud change detection is not necessarily immediate

Changes made directly on Windows Server are typically tracked by the agent faster than changes made **directly on the Azure file share** by external tools or clients.

Azure File Sync uses a periodic **cloud change detection** mechanism to detect direct changes on the cloud endpoint. Therefore, if a file is written directly to Azure Files, do not assume every server endpoint will see it immediately. In operational documentation, the detection interval is often described as around **once every 24 hours**; specific schedules and on-demand detection jobs must be verified against the current service version.

If you need continuous synchronization from a source updating the cloud directly, evaluate how the application performs updates, acceptable data lag, and Azure-supported cloud change detection tools.

### 4.4. Azure File Sync does not synchronize file locks across servers

Two people can open the same file at two offices before one person's update finishes syncing. SMB file locks are managed by the file server each client connects to and **do not automatically become a distributed lock enforced across all server endpoints simultaneously**.

When two copies are edited concurrently, a **sync conflict** can occur or a conflict copy may be generated per service behavior, depending on the scenario. Do not use Azure File Sync as a concurrent-write platform for databases, applications requiring distributed locking, or real-time multi-author file editing without appropriate coordination.

For documents requiring co-authoring, consider collaboration tools that manage versioning and conflicts at the application layer.

## 5. Cloud Tiering: Keeping Hot Data On-Premises

Cloud tiering is a key feature of Azure File Sync. When enabled, the agent can **keep file namespaces and metadata on Windows Server** while moving the contents of infrequently used files to Azure to free local disk space.

### 5.1. What is a tiered file?

Consider a 4 TB folder consisting of:

- 400 GB of documents employees edit frequently.
- 3.6 TB of rarely accessed historical documents.

With appropriate cloud tiering settings, the server can keep local contents for actively used files and leave older files in a **tiered** state. Users still see filenames, folders, and metadata, but when opening a tiered file, the agent must **recall** its contents from Azure.

~~~mermaid
flowchart LR
    U["User opens file"] --> S["File server"]
    S --> D{"Is file content local?"}
    D -->|Yes| L["Read from local disk"]
    D -->|No| C["Recall via Azure File Sync<br/>from Azure Files"]
    C --> L
~~~

**Cloud tiering is not the same as the Blob Archive tier**: it is a local cache management capability of Azure File Sync on a server endpoint, not a requirement to convert an Azure file share into Azure Blob Archive.

### 5.2. Cloud tiering policies

Common policies include:

| Policy | Meaning | Illustrative example |
|---|---|---|
| **Volume free space** | Maintains a target percentage of free space on the volume, tiering eligible files as needed | Target keeping 20% volume free |
| **Date policy** | Allows tiering files not accessed within a configured timeframe | Files not accessed for 60 days |
| **Tiering disabled** | Keeps all synced file contents on the server endpoint normally | Server has sufficient disk and requires offline reads |

These are **configuration examples**, not mandatory defaults. Which files get tiered also depends on agent eligibility conditions and exceptions.

Note: the free space target applies to the **volume hosting the endpoint**, not an independent quota per folder. If other application data resides on the same volume, setting this policy can affect shared capacity.

### 5.3. What happens if the server loses Internet access?

A file whose **full content is in the local cache** can typically still be read within local permissions and state. However, a tiered file whose content **exists only in Azure** cannot be recalled while disconnected from the cloud endpoint.

Therefore:

- Do not enable aggressive tiering at branches with unstable Internet if users need offline reads.
- Applications needing immediate, reliable access to all data may require tiering disabled or an appropriate caching plan.
- Recalling large files can increase file-open latency and WAN load.
- Estimate which files are "hot," actual network throughput, and minimum local disk capacity.

### 5.4. Estimating space savings

Suppose the total dataset is **6 TB**, of which **1.2 TB** is accessed frequently. Do not assume the server needs exactly 1.2 TB. Leave room for the OS, metadata, files being recalled, short-term changes, new data, agent operations, and the target free space percentage.

A reasonable estimation workflow:

1. Measure current disk usage and monthly growth.
2. Observe file access history and the ratio of frequently used data.
3. Set an appropriate volume free space target.
4. Test bandwidth and latency from the server to Azure.
5. Pilot recall behavior with a representative user group.
6. Monitor local usage and tiered data volume after deployment.

Cloud tiering helps manage **local disk capacity**, but does not proportionally reduce the data volume stored in Azure Files.

## 6. Prerequisites and Limits to Know

### 6.1. Windows Server and file system

The Azure File Sync agent installs on **Windows Server** versions, patch levels, and architectures on Azure's current support list. Do not assume older Windows Server releases or Windows client editions are eligible for registration.

The server endpoint path must reside on a file system and volume type supported by Azure File Sync; **NTFS** is the standard foundation. Review path limits, volume constraints, file system features, mount points, and endpoint limits before deployment.

Special data types such as system files, continuously locked application data, reparse points, specially encrypted files, or unsupported file systems must be evaluated separately. Azure File Sync is not a tool to replicate an entire Windows Server, registry, boot volume, or installed applications.

### 6.2. Azure Storage

Requirements include:

- A **Storage Account** with an account kind and performance tier compatible with Azure Files/Azure File Sync.
- An **Azure file share** using a protocol and configuration supported by Azure File Sync.
- Adequate quota and performance for expected capacity, file count, and access rates.
- Appropriate redundancy: LRS, ZRS, GRS, GZRS, or options supported by SKU/region.
- Approved security settings, network access controls, and backup/restore capabilities.

Azure File Sync uses **Azure Files** as its cloud endpoint; **not** a standard Blob container.

### 6.3. Deployment regions

**The Storage Sync Service and the Azure file share used as the cloud endpoint must reside in compatible regions**, typically placed in the same Azure region per service requirements. Windows Servers can reside on-premises or elsewhere and connect to that region over the network.

Do not assume you can place a Sync Service in any arbitrary region and point it to file shares in other regions. Verify regional rules and applicable constraints before deployment.

### 6.4. Networking and DNS

Servers require outbound HTTPS connectivity to Azure File Sync, Storage, and related authentication/management endpoints. Typically **TCP/443** is the baseline requirement for agent sync; the complete endpoint list depends on configuration and current version.

Distinguish clearly:

- **Client → Windows Server via SMB:** typically uses TCP/445 on the LAN or internal network.
- **Azure File Sync agent → Azure via HTTPS:** outbound connections for sync and management.
- **Client → Azure Files directly via SMB:** if the organization uses this model, TCP/445 along with identity/networking prerequisites apply; this does not mean the agent itself requires outbound SMB 445 to Azure.

Verify DNS, proxies/firewalls, TLS, certificates, allowed Azure endpoints, Storage Account network access rules, and Private Endpoints if used.

### 6.5. Identities and permissions

Distinguish:

1. **Azure management permissions:** permission to create Storage Sync Services, sync groups, cloud endpoints, and administer Storage Accounts.
2. **Windows Server registration identity:** appropriate permissions in Azure and on the server.
3. **User data access permissions:** share-level permissions, NTFS ACLs, and supported Active Directory/identity systems.
4. **Agent permissions:** service authentication mechanisms and permissions used to synchronize data.

Do not use a subscription-wide Owner account for every step purely for convenience. Grant least-privilege scopes, log changes, and rotate credentials per policy.

## 7. Planning a Sample Deployment Model

Suppose an enterprise wants to move the Projects folder to Azure and synchronize two offices:

| Component | Illustrative name |
|---|---|
| Subscription | Approved lab subscription |
| Resource group | rg-filesync-lab |
| Azure resource region | southeastasia |
| Storage Account | stfilesyncdemo12345 *(must be globally unique)* |
| Azure file share | projects |
| Storage Sync Service | stsync-projects |
| Sync group | projects-sync |
| Server A | fileserver-hcm |
| Server B | fileserver-hn |
| Server endpoint A | D:\Shares\Projects |
| Server endpoint B | E:\Department\Projects |
| Server A SMB share | \\fileserver-hcm\Projects |
| Server B SMB share | \\fileserver-hn\Projects |

Names and paths are illustrative only. In real operations, verify names, volumes, quotas, ACLs, and data ownership before creating endpoints.

### 7.1. Pre-deployment decisions

- Is the Azure file share a brand-new **empty** data source, or does it already hold files in active use?
- Does one server currently hold the authoritative data version?
- Do both file servers have overlapping namespaces with differing file contents?
- Is cloud tiering needed on both servers or only on a server with a smaller disk?
- Will users keep legacy SMB paths via DNS aliases/DFS Namespaces or migrate to new paths?
- Have recovery, backup, and user permission workflows been tested?
- Are there applications holding continuous file locks, databases inside the folder, or overly aggressive antivirus scanners?

If data already exists in multiple locations, plan **onboarding and conflict handling** carefully. Do not attach multiple server endpoints in bulk and assume differing copies will merge automatically as desired.

## 8. Step-by-Step Deployment via Azure Portal

The sequence below fits a greenfield model and test environment. Menu labels may vary across Azure Portal updates.

### Step 1: Create the Storage Account and Azure file share

1. In the Azure Portal, select **Storage accounts → Create**.
2. Choose the right subscription and **rg-filesync-lab**.
3. Select a region, account kind/performance tier, and redundancy supported by Azure File Sync.
4. Configure network security, TLS, authentication, and data protection options per policy.
5. Complete Storage Account creation.
6. Open the Storage Account, go to **File shares**, and create the Azure file share **projects**.
7. Choose a quota/tier suited to capacity and workload.
8. Verify the file share appears and contains no unintended data before pairing with an existing server folder.

Cost note: choosing Standard vs. Premium file shares, capacity/IOPS levels, and billing models can significantly affect pricing. Never choose a tier by name alone without evaluating workload characteristics.

### Step 2: Create the Storage Sync Service

1. Search for **Storage Sync Services** in the Portal.
2. Select **Create**.
3. Select the appropriate subscription and resource group.
4. Select a region compatible with the Storage Account hosting the Azure file share.
5. Name it **stsync-projects** and create the resource.
6. Open the Storage Sync Service to verify its status.

The Storage Sync Service organizes sync groups, registered servers, and health status. Do not treat this service itself as a disk storing file contents: the cloud endpoint points to the Azure file share holding the actual files.

### Step 3: Create the Sync Group and Cloud Endpoint

1. Inside Storage Sync Service, select **Sync groups → + Sync group**.
2. Name it **projects-sync**.
3. Select the subscription/Storage Account and the **projects** Azure file share as the cloud endpoint.
4. Confirm region and connectivity requirements.
5. Create the sync group.
6. Verify the sync group shows the cloud endpoint pointing to the intended file share, not another share with unrelated data.

A sync group has only **one cloud endpoint**, while server endpoints are added afterward.

### Step 4: Prepare Windows Server

On each file server:

1. Verify the Windows Server version is supported by Azure File Sync and appropriately patched.
2. Check the NTFS volume and source folder to synchronize.
3. Check remaining free space, file locks, duplicate data, special filenames, and NTFS ACLs.
4. Ensure outbound HTTPS to required Azure endpoints, DNS, and TLS work properly.
5. Ensure SMB shares, share permissions, AD groups, and client access remain intact.
6. Prepare a baseline backup and data recovery plan.

Do not turn your initial deployment into a cutover of all production SMB paths at once. Run a pilot on a small dataset first.

### Step 5: Install the Azure File Sync agent and register the server

1. Download the **Azure File Sync agent** for Windows Server from the official Microsoft source specified in current documentation.
2. Choose a current agent build **supported for your Windows Server version**.
3. Install the agent on the server with appropriate privileges; reboot if prompted by the installer.
4. Open **Server Registration** per the agent workflow.
5. Sign in and select the correct Azure tenant/subscription, resource group, and Storage Sync Service.
6. Complete registration, then return to the Portal and verify the server under **Registered servers**.

If registration does not appear, inspect the agent, authentication, permissions, Azure connectivity, and system clock synchronization. Do not repeatedly reinstall or re-register without checking prior state.

### Step 6: Add the Server Endpoint

Inside **projects-sync**:

1. Select **Add server endpoint**.
2. Choose registered server **fileserver-hcm**.
3. Enter path **D:\Shares\Projects**.
4. Decide whether to enable or disable **cloud tiering**.
5. If enabled, configure volume free space and related policies as needed.
6. Create the endpoint, then monitor initial sync progress and health.

Once initial sync is verified, add **fileserver-hn** with its approved endpoint path and verify data on each side. If the cloud file share already contains data or multiple source file servers exist, review onboarding/initial sync and conflict handling procedures before adding endpoints.

### Step 7: End-to-end testing

1. On Server A, create a new test file inside the synced folder.
2. Confirm the file appears in the Azure file share after agent sync.
3. Confirm the file appears in Server B's folder.
4. From SMB client B, read the file contents and verify NTFS permissions.
5. Edit the file in **one location** and verify the update propagates to the remaining endpoints.
6. If cloud tiering is enabled, verify namespaces, free space, and safe recall of a test file.
7. Check logs, health status, and sync error counts.

**Never use critical business files for deletion or overwrite tests.** Use a pilot directory or authorized test files.

## 9. Verifying Azure Resources with CLI

The Azure Portal is convenient for agent and registration steps. Azure CLI can assist with verifying subscriptions, Storage Accounts, and Azure file shares. The examples below use Bash in Azure Cloud Shell.

### 9.1. Inspect the selected Storage Account

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

RG="rg-filesync-lab"
STORAGE_NAME="<storage-account-name>"

az storage account show \
  --resource-group "$RG" \
  --name "$STORAGE_NAME" \
  --query "{name:name,location:location,kind:kind,sku:sku.name,publicNetworkAccess:publicNetworkAccess}" \
  --output json
~~~

Review the output to verify region, kind, SKU, and access policy. This command queries management-plane configuration only; **it does not prove the agent has synced successfully**.

### 9.2. Verify the file share exists

~~~bash
az storage share-rm list \
  --resource-group "$RG" \
  --storage-account "$STORAGE_NAME" \
  --output table

az storage share-rm show \
  --resource-group "$RG" \
  --storage-account "$STORAGE_NAME" \
  --name "projects" \
  --output json
~~~

The **share-rm** commands use the resource management API for Azure file shares. Depending on Azure CLI version and account model, parameters/extensions may vary; consult CLI help in your target environment when running commands.

### 9.3. Avoid using storage account keys routinely

For administration and metadata reads, prefer Azure RBAC and managed identities as needed. Avoid printing account keys or connection strings into pipeline logs, documentation, or command history.

When data-plane operations are needed, use authentication methods appropriate to service capabilities and identity rather than giving storage keys to all operators.

## 10. Verifying Windows Server with PowerShell

On a Windows Server with inspection privileges:

~~~powershell
# Check OS version and server status
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsBuildNumber

# Check volumes and file systems
Get-Volume | Select-Object DriveLetter, FileSystem, Size, SizeRemaining

# Does the planned server endpoint folder exist?
Test-Path -LiteralPath "D:\Shares\Projects"

# List SMB shares published on the server
Get-SmbShare | Select-Object Name, Path, Description
~~~

Inspect local folder and share permissions:

~~~powershell
Get-Acl -LiteralPath "D:\Shares\Projects" | Format-List

Get-SmbShareAccess -Name "Projects" |
  Select-Object Name, AccountName, AccessControlType, AccessRight
~~~

These are **inspection** commands and do not modify ACLs. Never apply **Everyone: Full Control** as a quick workaround when clients get Access Denied. Identify share permissions, NTFS ACLs, and user identities properly.

### 10.1. Check connectivity prerequisites

~~~powershell
# Example check for HTTPS connectivity to Azure Files endpoint
Test-NetConnection -ComputerName "<storage-account-name>.file.core.windows.net" -Port 443

# Check DNS resolution
Resolve-DnsName "<storage-account-name>.file.core.windows.net"
~~~

Testing one hostname/port verifies only part of the network path; the agent also contacts Storage Sync Service and supporting endpoints. If using Private Endpoints, DNS output must match the private IP design. Do not conclude networking is completely healthy from a single successful `Test-NetConnection`.

### 10.2. Safely create test data

Inside a test folder **already within the server endpoint**:

~~~powershell
$testFile = "D:\Shares\Projects\sync-validation.txt"
"Azure File Sync validation - $(Get-Date -Format o)" |
  Set-Content -LiteralPath $testFile -Encoding UTF8

Get-Item -LiteralPath $testFile |
  Select-Object FullName, Length, LastWriteTimeUtc
~~~

Next, check the Portal/Azure file share to confirm the file, wait for sync to the other server, and compare contents. Do not use this test to claim distributed file locking or fixed sync latency guarantees.

## 11. Cloud Tiering in Production Operations

### 11.1. Cache and recall model

When tiering is enabled:

- Actively accessed files tend to stay cached locally depending on cache capacity and policies.
- Infrequently accessed files may keep only metadata/namespaces on the server.
- When a user opens a tiered file, the agent fetches its content from Azure.
- Large files or slow WAN links can cause noticeable wait times on first open.
- After recall, disk usage shifts; tiering policies continue regulating the cache over time.

Cloud tiering should be treated as **an architectural storage-tiering strategy**, not merely a cost-saving toggle. Azure Files storage charges remain, and recalls can generate extra transactions and network traffic.

### 11.2. Avoiding application issues caused by tiering

Not every application works smoothly with placeholder/tiered files. Before enabling tiering on an application data folder:

1. Determine whether the application reads files sequentially or randomly.
2. Measure acceptable latency when opening a cold file.
3. Verify compatibility of antivirus, backup, and indexing tools with tiered files.
4. Test error handling when Azure connectivity drops.
5. Evaluate impact on apps storing huge container files or editing files continuously.
6. Check software behavior regarding file attributes and filesystem operations.

For database workloads needing very low latency I/O or constant random updates, choose an appropriate storage technology instead of placing data files into Azure File Sync by default.

### 11.3. Monitoring the cache

Monitor:

- Volume capacity and free space percentage.
- Tiered file size relative to total dataset size.
- Recall counts and open latency for common files.
- WAN utilization during peak hours.
- Files failing to tier or reporting errors.
- Agent status and cloud tiering policy health.

Measuring only free disk space without measuring user experience can leave a system "saving disk" while severely degrading file access speed.

## 12. Multi-Branch Synchronization and Conflict Management

Two or more Windows Servers can serve as server endpoints in the same sync group within supported limits.

### 12.1. Designing access permissions and namespaces

- Each branch provides a local SMB share for its users.
- Share names can be standardized, or **DFS Namespace** can provide a unified logical path under supported designs.
- NTFS ACLs on data must be evaluated during sync and recovery.
- Share permissions, DNS aliases, and sign-in policies still need per-server configuration.
- Restrict write permissions to appropriate groups to minimize simultaneous edits across sites.

### 12.2. Conflict example

Scenario:

1. Employee A opens **plan.xlsx** in HCM and edits it.
2. Before the update syncs to Hanoi, employee B opens the older copy on Server B and edits it as well.
3. Both updates are written to their local endpoints.
4. The service must handle the conflict during synchronization.

Do not promise that Azure File Sync will "merge" Excel cell-level changes. Conflict resolution depends on operation type, timing, and sync state, and may preserve conflict copies per supported behavior to avoid silent data loss.

Operational recommendations:

- Limit concurrent editing of critical files across multiple endpoints.
- Use appropriate collaboration software for files needing co-authoring.
- Monitor conflict/error metrics and train users to recognize conflict copies.
- Consider designating one primary write site for high-conflict document types.

### 12.3. If a server goes offline for several hours

Local changes can still be written by users to locally cached data on that server, but they will not reach other endpoints until connectivity and synchronization resume. While offline, tiered files cannot be recalled.

When network connectivity returns:

- The agent processes the synchronization backlog.
- Data should be verified, especially if the same files were edited at another location.
- Monitor bandwidth, sync errors, and latency until the backlog clears.
- Do not force deletions or copies to "make sync faster" without understanding the data state.

## 13. Security: Networking, Permissions, and Encryption

### 13.1. Network boundary

Map out three distinct flows clearly:

~~~mermaid
flowchart LR
    User["LAN users"] -->|"Internal SMB"| Server["Windows File Server"]
    Server -->|"Outbound HTTPS"| Cloud["Azure Files / File Sync"]
    Admin["Azure admin"] -->|"Azure control plane"| Mgmt["Storage Sync Service"]
    Mgmt -. "State management" .-> Server
~~~

Each flow has distinct requirements:

- Internal SMB: restrict access sources and segment networks appropriately.
- Agent sync: outbound HTTPS firewall/proxy rules to required endpoints.
- Azure Files: Storage Account network rules, public/private access, private endpoints, DNS, and File Sync compatibility.
- Portal/control plane: Azure RBAC, MFA/Conditional Access, and change control.

If using Private Endpoints for Storage Accounts or Storage Sync Services where supported, configure private DNS, routes, VPN/ExpressRoute, or appropriate network paths. Never enable "Disable public network access" in production before confirming the agent can reach private endpoints.

### 13.2. Content protection

- On Windows Server, manage NTFS ACLs, share-level permissions, and local admin privileges.
- On Azure, configure Azure Files, Storage Accounts, admin roles, and data-plane access.
- Avoid storing storage account keys in scripts or operational docs.
- Use TLS/encryption mechanisms supported by the service.
- Enable logging and auditing per compliance requirements.
- Apply endpoint security and update Windows Server and agents regularly.

**Do not mix up** three distinct concepts: Azure RBAC managing the Storage Account, client SMB authentication, and agent sync mechanics. Granting a principal management-plane access does not grant users rights to read every file.

### 13.3. Ransomware and accidental deletion

Azure File Sync can propagate malicious changes from a file server to the cloud endpoint. If an account with delete permissions is compromised, accidental or malicious deletions can replicate to other servers.

Combine multiple defenses:

1. Back up the Azure file share per retention policies.
2. Use snapshots/file recovery capabilities per supported service and SKU.
3. Enable file share protection mechanisms where appropriate; distinguish file share soft delete from individual file version recovery.
4. Restrict modify/delete rights and separate backup administration duties.
5. Monitor mass deletions, sync errors, and security alerts.
6. Practice restoring clean datasets and reconciling NTFS permissions.

LRS/ZRS/GRS/GZRS redundancy does not replace backups: logical deletions or overwrites replicate to redundant copies.

## 14. Backup and Disaster Recovery

### 14.1. Where should backups run?

Because the cloud endpoint holds the central dataset in an Azure file share, your backup solution should cover the **Azure file share** using appropriate tools and policies, such as Azure Backup for Azure Files within supported scope.

However, a complete DR plan must also protect:

- Windows Server configuration, SMB shares, and share permissions.
- NTFS ACLs, identities, and related Active Directory configuration.
- Storage Sync Service, sync groups, endpoints, and network configuration.
- Source documentation, application access rights, and recovery runbooks.
- Local files or data stored **outside** server endpoints.

Do not assume backing up the Azure file share automatically recreates all server configurations or Windows applications.

### 14.2. A branch server fails

Scenario: **fileserver-hcm** suffers a disk failure. The cloud endpoint still holds previously synced data.

Reference recovery plan:

1. Determine failure scope, gather logs, and check last known sync status.
2. Provision a replacement Windows Server with a supported OS/agent version.
3. Configure volumes, directories, networking, DNS, domain membership, and security.
4. Install the Azure File Sync agent and register the server with the appropriate Storage Sync Service.
5. Add the new server endpoint to the sync group per Azure recovery guidance.
6. Allow namespace/content sync from the cloud endpoint, applying cloud tiering if appropriate.
7. Recreate SMB shares, share-level permissions, and verify NTFS ACLs.
8. Verify documents, user permissions, applications, and performance before switching clients to the new server.

Changes not yet synced from the failed server to the cloud may not exist on the cloud endpoint. Review logs and local backups if business requirements cover that gap.

### 14.3. Losing an entire site or region

Azure file shares can be configured with redundancy and DR capabilities depending on SKU. However, **File Sync does not automatically restore AD, DNS, VPN, file servers, and SMB paths** during a site outage.

If an Azure Storage region suffers a major outage:

- Review geo-redundancy and supported failover mechanisms for the specific account/share.
- Assess replication lag and potential loss of writes not yet replicated to secondary.
- Understand how storage failover affects the cloud endpoint and Azure File Sync configuration.
- Coordinate compute, network, DNS, and server registration recovery per approved runbooks.
- Verify data consistency after recovery.

Never trigger storage account failover as a quick test in production; follow an organization-approved and Azure-supported DR process.

### 14.4. Practicing recovery without damaging live data

In a lab, use dedicated test files:

1. Create a test file on the server and confirm it syncs to the cloud.
2. Create a snapshot/backup per enabled capabilities.
3. Modify or delete the **test** file—never real documents.
4. Restore the file to a test location per service procedures.
5. Inspect contents, ACLs, filename, and path.
6. Record observed RTO and limitations.

An untested backup is merely an expectation, not proof that a DR plan works.

## 15. Monitoring Azure File Sync

### 15.1. Metrics to track

| Metric/status | Purpose |
|---|---|
| Registered server health | Is the agent online and reporting properly? |
| Server endpoint sync health | Are there sync errors, backlogs, or states needing action? |
| Count of files failing to sync | Detect stuck data or metadata items |
| Last sync timestamp | Know whether endpoints update regularly |
| Cloud endpoint health | Is the Azure file share available to endpoints? |
| Local capacity and free space | Evaluate cloud tiering and disk-full risks |
| Recall/cache behavior | Detect file-open latency and WAN consumption |
| Storage capacity/transactions | Track load and Azure Files limits |
| HTTPS connectivity and agent events | Analyze authentication, TLS, proxy, or network issues |
| Azure Files and data costs | Control growth and operating expenses |

The Azure Portal provides status and monitoring blades for Storage Sync Services, sync groups, and server endpoints. You can integrate Azure Monitor or Azure-supported logging/alerting features depending on your environment.

### 15.2. Event logs on Windows

The agent emits Windows logs and events for diagnostics. On an actual server, identify the log channel for your active agent version using Event Viewer or PowerShell:

~~~powershell
Get-WinEvent -ListLog "*FileSync*" -ErrorAction SilentlyContinue |
  Select-Object LogName, RecordCount, IsEnabled
~~~

This command is for **log discovery** and does not assume every version uses the exact same channel name. Once you locate the log, filter by timestamp and error code to correlate with Portal sync health.

Never delete agent logs or directly edit internal agent databases without official instructions.

### 15.3. Designing alerts

Alert when:

- A server endpoint stays offline beyond an acceptable threshold.
- Sync errors fail to drop or backlogs persist.
- Local disk free space falls too low.
- The Azure file share approaches quota or performance limits.
- Unusually large numbers of files are deleted/modified in a short window.
- Recall volume or costs spike unexpectedly.
- Unplanned changes occur to networking, Storage Accounts, permissions, or backup policies.

Do not rely solely on a high-level "Healthy" status to conclude every file in every folder has the latest copy. Inspect detailed error counts and business sync objectives.

## 16. Layered Troubleshooting

| Symptom | Common causes | What to investigate |
|---|---|---|
| Server fails to register | Insufficient permissions, wrong subscription, unsupported agent/OS, network/TLS/proxy | Check agent, RBAC, sign-in, DNS, and HTTPS endpoints |
| Sync group cannot add cloud endpoint | Incompatible Storage Account/file share/region or missing permissions | Check region, account kind, share, and service limits |
| Cannot add server endpoint | Invalid path, unsupported volume/file system, overlapping endpoints, or insufficient permissions | Check registered server, NTFS path, and endpoint limits |
| Server A has file, Server B does not | Sync lag, backlog, agent error, conflict, or networking | Inspect sync health on both endpoints and specific file status |
| File written directly to Azure Files not visible immediately on server | Cloud change detection has not run yet | Check change detection schedule and supported on-demand triggers |
| Filename visible, opening throws error | Content is tiered, Azure unreachable, or recall failed | Check HTTPS connectivity, cloud tiering, and agent event logs |
| Volume runs out of space | Tiering disabled, cache too large, unsuitable policy, or non-tierable files | Check free space, tiering policy, and ineligible files |
| User gets Access Denied | Incorrect NTFS ACLs, share permissions, or domain/identity | Check both share permissions and folder/file ACLs |
| Multiple conflicting file copies | Concurrent edits to the same file on multiple servers before sync | Check conflicts, workflow, and authoritative version |
| Slow sync | WAN bandwidth, high file count, constant churn, service limits, antivirus scanning | Measure WAN, queue/backlog, metadata rate, and resource usage |
| Sync health good, app opens files slowly | Tiered file recall, DNS, SMB client, or under-resourced file server | Check cache hits, recall latency, and application behavior |
| Data deleted across multiple locations | Deletion was synchronized | Stop faulty source, preserve evidence, restore backup/snapshot |
| Azure bill higher than estimated | Capacity, transactions, tiering recall, redundancy, or backup | Cost Management, metrics, and pricing rules |

### 16.1. Step-by-step diagnostic procedure

When a file does not appear on Server B:

1. **Verify scope:** is the file inside Server A's server endpoint path?
2. **Verify source:** is the file completely saved, not continuously locked by an app, and not an unsupported data type?
3. **Verify Server A:** is the agent online, registered to the right Sync Service, and is the endpoint Healthy?
4. **Verify cloud endpoint:** has the file appeared in the Azure file share yet?
5. **Verify Server B:** is the agent online, in the same sync group, checking the right folder, with no errors/conflicts?
6. **Verify permissions:** do NTFS ACLs and share permissions allow the user to view the file?
7. **Verify network:** can Server B reach service endpoints over DNS/TLS/HTTPS?
8. **Verify backlog:** is there a large file queue, tiering/recall activity, or service throttling?
9. **Read detailed logs:** capture error codes, timestamps, and related events.
10. **Fix root cause and re-test:** perform only supported remediation actions, then verify contents and timestamps.

Avoid bulk-renaming or deleting files while trying to fix sync without backups and a clear understanding of how the service processes changes.

### 16.2. When the cloud endpoint does not appear to update

If files are modified directly on the Azure file share and server endpoints do not reflect them immediately:

- Confirm the exact share is the sync group's cloud endpoint.
- Confirm the cloud change is valid and free of permission errors.
- Check when cloud change detection last ran.
- If business needs require faster detection, consult documentation and current PowerShell modules for **Invoke-AzStorageSyncChangeDetection**.
- Do not invoke continuous detection jobs on huge directories without reviewing limits and costs.

Azure File Sync is not designed for zero-latency detection of every cloud-side modification.

## 17. Deployment Architecture: Performance, Limits, and Cost

### 17.1. Dataset size and file count

10 TB composed of a few hundred large files behaves very differently from 10 TB composed of tens of millions of small files. When planning:

- Measure file/folder counts, path depth, and average file size.
- Determine hourly churn rate and metadata operation volume.
- Check limits on endpoints, files, sync groups, and file system types for the current service.
- Estimate realistic initial sync duration and WAN transfer volume.
- Reserve capacity/IOPS for file opens, scans, backups, and cloud tiering.
- Plan for periods of rapid data growth.

Never use total TB capacity as the sole metric to judge sync speed.

### 17.2. Costs

| Component | Potential cost/impact |
|---|---|
| Azure Files | Storage capacity, Standard/Premium model, redundancy, and transactions |
| Azure File Sync | Service billing component per current pricing, including connected server count where applicable |
| Network | Data transfer, egress, VPN/ExpressRoute, proxy, or Private Endpoint per configuration |
| Cloud tiering | Caching and recalls alter Azure Files access patterns; can generate transactions/network traffic |
| Backup/snapshot | Copy storage/retention, restore operations, and storage consumption |
| Windows file server | VM/hardware, licenses, disks, maintenance, and operational resources |
| Logging/monitoring | Ingestion, retention, alerting, and log analytics systems |

Exact costs vary by region, Azure Files billing model, tier, server count, and access frequency. Use the Azure Pricing Calculator and current pricing sheets; do not assume tiering always lowers the total bill.

### 17.3. When should you NOT use Azure File Sync?

Avoid choosing File Sync by default when:

- The system requires strong **distributed file locking** and real-time multi-site writes.
- Data is primarily databases or application files needing random I/O and ultra-low latency.
- Source machines are not a supported Windows Server release.
- Azure connectivity drops frequently yet all files must be available instantaneously while aggressive tiering is enabled.
- Only a direct cloud share is needed and no Windows Server cache is required.
- Data residency mandates a location incompatible with chosen Azure Files regions/replication.

In those cases, evaluate direct Azure Files, Azure NetApp Files, Azure Managed Disks, dedicated collaboration platforms, or other replication/backup solutions tailored to the actual workload.

## 18. Operations, Change Management, and Rollback

### 18.1. Standard change workflow

1. Identify data owners, file servers, Storage Account, and sync group.
2. Document endpoint paths, ACLs, quotas, cloud tiering policies, and health status.
3. Confirm a recent backup/snapshot exists and restore has been tested.
4. Test changes in a lab with non-sensitive data.
5. Roll out server endpoints one at a time; never add every branch simultaneously without measuring initial sync.
6. Trace data from server → cloud → server and inspect specific files.
7. Verify access permissions, latency, and user experience.
8. Record changes, before/after metrics, and recovery plans.

### 18.2. Removing an endpoint is not the same as deleting data

Removing a server endpoint, pausing sync, uninstalling the agent, or deleting a sync group involves specific prerequisites and cleanup procedures, **especially when tiered files exist**.

Before retiring Azure File Sync on a server:

- Identify which files are tiered and still require recall.
- Ensure retained data is hydrated/recalled via supported procedures if the server will continue operating standalone.
- Back up data and SMB/ACL configurations.
- Follow the official Azure File Sync offboarding procedure rather than simply deleting folders.
- Confirm remaining server endpoints still function and the cloud endpoint retains expected data.

Never delete a Storage Account or Azure file share while any sync group or server endpoint still relies on that data.

### 18.3. After completing a lab

Delete only resources **created specifically for the lab** that are unused by other workloads. Verify:

1. Whether any data needs to be kept or exported elsewhere.
2. Whether server endpoints have been offboarded per guidelines.
3. Whether registered servers and sync groups have remaining dependencies.
4. Whether the Azure file share holds any production data.
5. Whether backups/retention continue incurring charges.

Do not issue blanket resource group deletion commands in lesson labs because a resource group may contain resources outside lab scope.

## 19. Production Readiness Checklist for Azure File Sync

- [ ] Clear business objective: local caching, multi-site sync, or migration.
- [ ] Verified supported Windows Server/agent versions and file systems.
- [ ] Inventoried file counts, file types, capacity, ACLs, and apps holding open files.
- [ ] Storage Account/Azure file share configured with suitable region, redundancy, quota, and performance tier.
- [ ] Storage Sync Service and cloud endpoint match in region and target share.
- [ ] Sync group contains a valid cloud endpoint/server endpoint topology.
- [ ] Server registration, Azure permissions, and Windows permissions properly separated.
- [ ] Outbound firewall/DNS/TLS/HTTPS configured; Private Endpoints tested if used.
- [ ] Share-level permissions, NTFS ACLs, identities, and SMB paths tested.
- [ ] Cloud tiering policy fits requirements and recalls have been tested.
- [ ] Contingency plans exist for server offline, failed tiered recalls, and extended sync backlogs.
- [ ] Bidirectional sync and conflict handling tested with test files.
- [ ] No assumptions made about multi-server file lock synchronization.
- [ ] Backups/snapshots enabled and accidental-deletion restores practiced.
- [ ] Runbooks exist for server failure, ransomware, and network/region outages.
- [ ] Alerts configured for offline agents, sync errors, storage quotas, and free space.
- [ ] Costs and data growth estimated.
- [ ] Agent update and endpoint offboarding procedures defined.

## 20. Hands-On Exercises

### Exercise 1: Diagram a single-office model

An enterprise has a Windows file server holding 2 TB of documents, wants to keep a local SMB share, and replicate data to Azure. Draw a diagram including Storage Account, Azure Files, Storage Sync Service, sync group, cloud endpoint, registered server, and server endpoint. Explain why the Storage Sync Service is not a disk storing file contents.

### Exercise 2: Two-branch design

Two file servers in HCM and Hanoi need to share the Projects folder. Complete the following:

1. Choose the sync group structure.
2. Define both server endpoints.
3. Describe how a file travels from HCM to Hanoi.
4. Identify a concurrent edit scenario that causes a conflict.
5. Propose ways to limit concurrent edits on sensitive documents.

### Exercise 3: Choosing cloud tiering policies

A branch has a 2 TB disk and 5 TB of data, most of which is rarely accessed. Users need fast opening for documents from the past 30 days. Propose preliminary volume free space and date policies, explain risks during Internet outages, and describe how to test recall performance.

Do not assume 100% of older data can be tiered strictly by ratio; budget for caching, metadata, growth, and file opens.

### Exercise 4: Diagnosing a missing file

A user saves **report.docx** on Server A. The file does not appear on Server B after some time. Write a diagnostic checklist in order: path, Server A sync health, Azure file share, Server B sync health, conflicts, ACLs, networking, and event logs.

### Exercise 5: Recovering after accidental deletion

A folder containing 200 files is deleted from an SMB share and subsequently synced to Azure. Explain why redundancy does not save the files, which backup/snapshot features must be enabled beforehand, and a safe restoration sequence to a temporary folder.

### Exercise 6: Migration planning

A file server contains 8 TB of data and 4 million small files. Plan the pilot, initial sync measurement, bandwidth throttling, ACL assessment, user training, and cutover milestones to the new system. Explain why TB capacity alone should not be the only factor considered.

### Self-Check Questions

1. How does a cloud endpoint differ from a server endpoint?
2. How many cloud endpoints does one sync group have?
3. Does Azure File Sync automatically create SMB shares and share permissions on a new server?
4. Why does a file created directly in an Azure file share not necessarily appear immediately on Windows Server?
5. How does cloud tiering differ from Azure Blob Archive?
6. If a file is tiered and the server loses connectivity to Azure, what can happen when a user opens the file?
7. Does Azure File Sync synchronize file locks between two server endpoints?
8. Why are backups still needed even when a storage account uses GRS or GZRS?
9. When provisioning a replacement file server, besides data, what configurations must you recreate?
10. How do client SMB networking and Azure File Sync agent HTTPS networking differ?

## 21. References

- [Azure File Sync overview — Microsoft Learn](https://learn.microsoft.com/azure/storage/file-sync/file-sync-introduction)
- [Plan for an Azure File Sync deployment](https://learn.microsoft.com/azure/storage/file-sync/file-sync-planning)
- [Deploy Azure File Sync](https://learn.microsoft.com/azure/storage/file-sync/file-sync-deployment-guide)
- [Cloud tiering overview](https://learn.microsoft.com/azure/storage/file-sync/file-sync-cloud-tiering-overview)
- [Troubleshoot Azure File Sync](https://learn.microsoft.com/azure/storage/file-sync/file-sync-troubleshoot)
- [Azure Files overview](https://learn.microsoft.com/azure/storage/files/storage-files-introduction)
- [Azure Files networking considerations](https://learn.microsoft.com/azure/storage/files/storage-files-networking-overview)
- [Azure Backup for Azure Files overview](https://learn.microsoft.com/azure/backup/azure-file-share-backup-overview)
- [Azure Files pricing](https://azure.microsoft.com/pricing/details/storage/files/)
