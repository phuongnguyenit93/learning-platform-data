# Azure Files with SMB and NFS

In the Microsoft Azure ecosystem, not every application stores data as objects in Blob Storage or uses a disk attached exclusively to a virtual machine. Many applications require a **shared folder** that multiple servers or containers can access via familiar file paths. For example, a team of employees needs to open documents through a network drive on Windows; multiple Linux machines need to read a shared resource directory; or an application migrated from an on-premises data center to Azure still relies on a file system interface.

**Azure Files** provides Azure-managed file shares accessed via common file-sharing protocols: **SMB (Server Message Block)** and **NFS (Network File System)**, depending on the supported configuration. You do not have to maintain file servers, operating systems, or storage clusters for these file shares yourself. However, access permissions, networking, performance, backups, and costs still need to be carefully designed.

This lesson belongs to the **File and Disk Storage** chapter of the CLOUD_PROVIDERS_AZURE module, connecting Azure Files with resource groups, Storage Accounts, Microsoft Entra ID, virtual networks, private endpoints, monitoring, and cost control when operating applications on Microsoft Azure.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what Azure Files is and distinguish it from Azure Blob Storage, Managed Disks, and Azure NetApp Files.
2. Choose **SMB** or **NFS 4.1** based on the operating system, authentication model, and application.
3. Design an appropriate Storage Account, file share, private network, DNS, and access permissions.
4. Create and inspect file shares using the Azure CLI; understand the steps to mount shares from Windows and Linux.
5. Distinguish between Azure RBAC permissions, SMB/NTFS file permissions, and NFS UID/GID.
6. Evaluate performance, availability, backup/snapshot, security, monitoring, and cost.
7. Troubleshoot common issues such as inability to connect on port 445/2049, incorrect DNS, insufficient permissions, or performance issues.

The examples use illustrative resource names and are not executed automatically. Certain account, tier, region, and protocol choices depend on availability at deployment time; consult Microsoft documentation for your environment.

## 2. What is Azure Files?

### 2.1. Managed file shares on Azure

Basic model:

~~~text
Azure subscription
└── Resource group: rg-files-demo
    └── Storage Account: <storage-account>
        ├── File share: teamdocs   (SMB)
        └── File share: ...        (protocol and tier as supported)
~~~

A **Storage Account** is an Azure resource containing networking, security, redundancy policies, and supported storage services. A **file share** is the unit of file sharing inside the account; directories and files reside within the share.

Azure Files can be accessed:

- Via **SMB** from SMB-capable clients or services, commonly on Windows and also available on Linux.
- Via **NFS 4.1** in supported scenarios, especially useful for Linux/Unix workloads.
- Via corresponding APIs, SDKs, or management tools to manipulate file shares or data in supported scenarios; do not assume all capabilities are identical between SMB and NFS.

Path examples:

~~~text
SMB UNC:
  \\stfilesdemo001.file.core.windows.net\teamdocs

NFS export:
  stnfsdemo001.file.core.windows.net:/stnfsdemo001/appsdata
~~~

These examples can only be used after the resources, DNS, networking, and access permissions are properly configured. They are not self-managed file server addresses.

### 2.2. Azure Files compared to other services

| Need | Commonly suitable service | Why |
|---|---|---|
| Network drive/shared folder for multiple Windows machines | Azure Files with SMB | Uses the familiar SMB protocol |
| Shared directory for Linux applications supporting NFS | Azure Files with NFS | Supports mounting file shares via NFS 4.1 |
| Storing objects such as images, videos, backups exposed over HTTP/SDK | Azure Blob Storage | Object-style access, not an SMB/NFS file share by default |
| OS disk or data disk for a single Azure VM | Azure Managed Disks | Block storage model attached to a VM |
| NFS/SMB workloads requiring specialized features or performance characteristics | Azure NetApp Files, after evaluation | A separate service from Azure Files with its own design and pricing model |
| On-premises Windows file server needing cloud sync and caching | Azure Files SMB with Azure File Sync when requirements are met | Fits hybrid scenarios using Windows Server as an access point |

Do not treat Azure Files as the sole option for every workload: database systems requiring block storage, transactions, and very low latency may not be suitable for placing data files on a network share. Always rely on application requirements and official vendor support.

## 3. How do SMB and NFS differ?

### 3.1. Protocol comparison table

| Aspect | SMB on Azure Files | NFS on Azure Files |
|---|---|---|
| Typical protocol | SMB 3.x, depending on supported client and configuration | NFS 4.1 |
| Common clients | Windows; Linux/macOS or other environments when SMB is supported | Linux/Unix and appropriate NFS workloads |
| Path format | UNC: \\account.file.core.windows.net\share | Export: account.file.core.windows.net:/account/share |
| Data network port | TCP 445 | TCP 2049 |
| Authentication/access | Account key or identity-based SMB authentication as supported | Primarily relies on network controls and POSIX UID/GID permissions of the supported NFS model |
| File-level permissions | Windows/NTFS ACLs in identity-based SMB scenarios | POSIX owner, group, mode, and supported NFS mechanisms |
| Encryption in transit | SMB 3.x supports encryption when client/configuration aligns | Do not assume NFS 4.1 is encrypted at the transport layer by default; check network protection solutions and current features |
| Application types | Home directories, document shares, applications using UNC | Shared data for Linux apps, working directories, HPC or container workloads where appropriate |
| Feature compatibility | Has identity options and Azure File Sync subject to conditions | Distinct feature set; must verify snapshot/backup/management and tier support before designing |

**A file share does not automatically support both SMB and NFS simultaneously.** The protocol is defined when creating the share according to the product model; do not assume switching protocols is just editing a configuration field. If you need to serve both Windows and Linux, consider SMB for both if the application permits, or design separate shares and data synchronization flows if NFS is required.

### 3.2. Which protocol should you choose?

**Choose SMB when** you need a network drive on Windows, integration with enterprise identities, Windows-style ACLs, or want to use Azure File Sync with a supported Windows Server file server.

**Choose NFS when** the Linux application is designed to mount NFS 4.1, relies on UID/GID/POSIX permissions, and has a reliable private network path to Azure. For workloads heavily dependent on file locking and POSIX semantics, test real-world compatibility.

**Do not choose solely by operating system name.** Linux can mount SMB; containerized applications may still need SMB; and a cross-platform application may mandate whichever protocol the software vendor certifies.

## 4. Component Architecture and Access Flow

### 4.1. A hub-spoke architecture with private networking

~~~mermaid
flowchart LR
    W["Windows VM / SMB client"] --> V["VNet or hybrid network"]
    L["Linux VM / NFS application"] --> V
    O["On-premises"] --> H["VPN / ExpressRoute"]
    H --> V
    V --> P["Private Endpoint for file"]
    P --> A["Azure Storage Account"]
    A --> S["SMB File Share"]
    A --> N["NFS File Share\nwhen account/tier supported"]
    D["Private DNS / DNS forwarder"] -.-> V
~~~

The diagram illustrates both share types as conceptual possibilities in the system. It does not assert that every SKU or Storage Account kind supports both within a single account. When designing, check limits for protocol, account kind, tier, and region.

For a client to use a private endpoint:

1. The client connects to the VNet via the same virtual network, peering, VPN, or an appropriate ExpressRoute circuit.
2. DNS returns the **private** IP address of the endpoint for the name account.file.core.windows.net.
3. NSGs, firewalls, routes, and storage account policies allow the connection.
4. The client opens the appropriate SMB or NFS port and passes the corresponding authentication/authorization checks.

**A Private Endpoint does not automatically grant data read permissions.** It controls the network path to the service; file access permissions are still governed by SMB or NFS mechanisms. Conversely, having share read permissions without a valid network path/DNS will still fail to mount.

### 4.2. Fault domains and availability

Azure Files is a managed service, yet you still need to decide:

- Which region should the Storage Account be placed in, close to which clients and applications?
- Does the data require single-region availability or a cross-region recovery strategy?
- Which redundancy options are supported by the chosen SKU and protocol?
- Can the application handle temporary connection drops, stale handles, or retry errors?
- Are independent backups and periodic restore tests required?

LRS, ZRS, GRS/GZRS, and their variants have different support scopes depending on account type, protocol, tier, and region. Do not assume NFS and SMB share identical redundancy options. Redundancy protection also **does not replace backups** against accidental deletion, ransomware, or operator errors.

## 5. Choosing Storage Account Kind and Performance Tier

### 5.1. Two decision groups: protocol and billing model

First determine the protocol. Then select the appropriate performance tier/model:

- **HDD/standard file shares:** offer capacity, transaction, and/or provisioned options depending on the product model. Suitable when latency and IOPS requirements are not very demanding.
- **SSD/premium file shares:** serve higher IOPS, throughput, and lower latency needs under supported configurations; costs and provisioned capacity must be monitored closely.
- **Provisioned model:** performance/capacity may be tied to provisioned size or capacity parameters. Over-provisioning compared to actual demand leads to waste.
- **Pay-as-you-go model:** costs may include storage capacity, transactions, data transfer, and other items depending on the tier.

Tier/model names and NFS support capabilities can evolve over time. In practice, select the account kind and SKU according to current **Azure Files** documentation rather than applying an SMB HDD CLI example to NFS.

### 5.2. Selection table by workload

| Workload | Characteristics | Starting recommendation |
|---|---|---|
| Office document sharing for Windows users | Small/medium files, requires identity and ACLs | SMB, identity-based authentication, measure actual load |
| Windows application server using a shared folder | Frequent file open/close, locking | SMB, test software behavior and latency |
| Linux application reading shared models/resources | POSIX UID/GID, multiple Linux hosts | NFS 4.1 on a supported tier/account |
| High-I/O data processing | Many small operations or high throughput | Measure IOPS/throughput, consider SSD or another service |
| Archiving infrequently accessed files | Capacity matters more than latency | Evaluate HDD/cost model or Blob depending on access method |
| On-premises file server using SMB | Wants local cache and cloud sync | SMB with Azure File Sync if requirements are met |

Build a proof-of-concept workload before migrating applications with strict file-locking, large capacity, or heavy metadata operation requirements.

## 6. SMB Security and Authentication

### 6.1. Three layers to understand

With SMB, there are typically three distinct layers:

1. **Network:** Can the client reach the account over port 445 and permitted network paths?
2. **Authentication:** The client proves its identity using a method supported by the storage account/share, such as enterprise identity or an account key.
3. **Authorization:** Does the identity have permissions on the share and specific files/directories?

Having TCP port 445 open does not mean files can be read. Conversely, a user assigned a role whose DNS points incorrectly or whose ISP blocks port 445 still cannot use the share.

### 6.2. Identity-based SMB authentication

Azure Files provides identity integration options depending on conditions:

- **Active Directory Domain Services (AD DS):** suitable for organizations with traditional/hybrid Windows domains.
- **Microsoft Entra Domain Services:** uses Azure-managed domain capabilities when the environment meets requirements.
- **Microsoft Entra Kerberos:** supports certain modern/hybrid identity models depending on OS, domain, and deployment conditions.

Merely assigning an Azure RBAC role does not allow any arbitrary Windows client to sign into SMB automatically. Storage identity, Kerberos tickets, join state, DNS, identity synchronization, and client versions must all be properly configured.

In an identity-based SMB design, two permission levels are usually both critical:

| Scope | Mechanism | Meaning |
|---|---|---|
| Share-level | Azure SMB data roles, such as Storage File Data SMB Share Reader/Contributor as needed | Initial permission to access the share |
| Directory/file-level | NTFS ACLs and groups/users | Effective permissions on folders, files, and specific operations |

Granting a broad share-level role does not automatically bypass NTFS ACL restrictions. A user allowed into the share without permissions on a folder will still receive Access denied.

### 6.3. Account keys and why to be cautious

A Storage Account key is a powerful access credential. In certain SMB scenarios, account name/key can be used to mount without domain identity integration. However:

- The key grants broad permissions over related data in the account.
- Losing the key can lead to unintended data access.
- Keys are easily leaked if hardcoded in scripts, command history, logs, YAML, or repositories.
- Rotating keys can disrupt active clients if not properly planned.

Prefer identity-based SMB authentication whenever feasible. If a key must be used for a lab or an application with limited compatibility, store it in an approved secret management system, restrict access, and plan key rotation/revocation. Never put real key values into examples or shared documentation.

### 6.4. Encryption and access control

Azure Storage provides service-side encryption for data at rest. For SMB, use protocol versions and configurations that support encryption in transit in accordance with security requirements. Still prioritize private network connectivity whenever possible.

Settings such as the Storage Account's minimum TLS version apply to TLS-based endpoints and **do not replace SMB session security settings**. Do not treat setting TLS 1.2 on the account as sole proof that all SMB mounts are properly encrypted.

## 7. NFS Security and Access Control

### 7.1. NFS 4.1 and POSIX identity

With NFS shares, Linux applications typically determine permissions via file **UID, GID, owner/group, and mode bits**. For example:

~~~bash
id
ls -ln /mnt/appsdata
stat /mnt/appsdata/example.txt
~~~

If a file belongs to UID 1001 and GID 2001, other machines using NFS must follow consistent identity mapping conventions so permission behavior stays uniform. Two machines sharing the same Linux username but different numeric UIDs can encounter errors or unexpected permissions.

Do not assume an Azure RBAC role assigned to an Entra user automatically controls file read/write operations over an NFS mount. Azure RBAC protects resource management operations, whereas NFS data access must be designed around protocol and network controls.

### 7.2. Networking as an essential protection layer

NFS should never be deployed as an uncontrolled file-sharing service over the Internet. When using Azure Files NFS:

1. Select an account/tier and network access model that supports NFS.
2. Create a private endpoint or product-supported network connection so clients in trusted networks can access it.
3. Configure DNS to resolve account.file.core.windows.net to the appropriate endpoint, especially in hybrid setups.
4. Open TCP 2049 only from required subnets/workloads.
5. Apply network segmentation, NSGs/firewalls, and audit network policy changes.
6. Review POSIX permissions, UID/GID rules, and features like root squash as currently supported if applicable.

**Do not assume NFS 4.1 is encrypted in transit by default.** The NFS protocol differs from SMB regarding transport security. If data requires encryption in transit, evaluate Azure-supported NFS encryption features, network encryption, or appropriate controls per organizational policy; do not rely solely on encryption at rest.

Certain settings related to secure transfer requirements and share types have specific constraints with NFS. Do not toggle security settings based on old examples without checking documentation for the active service version.

### 7.3. UID/GID and write permissions in containerized applications

If an application runs inside a container/Kubernetes, inspect the actual UID/GID used by the process, not just the username in the image. An application running as UID 1000 inside a pod while the NFS directory only permits writes by UID 2000 will fail even though the mount succeeds.

Check `securityContext`, `runAsUser`, `runAsGroup`, and `fsGroup` as supported by the NFS client/CSI driver and environment. Never apply broad `chmod 777` to resolve permission errors in production; fixing ownership/group and provisioning workflows is much safer.

## 8. Network Design: Private Endpoint, DNS, and Ports

### 8.1. Private Endpoint for Azure Files

A Private Endpoint creates a network interface with a private IP address inside a VNet to connect to the corresponding Azure Storage subresource. For Azure Files, the subresource is typically **file**.

Model:

~~~text
Windows/Linux client
    |
    | TCP 445 (SMB) or TCP 2049 (NFS)
    v
Private IP of file private endpoint
    |
    v
<account>.file.core.windows.net (Azure Files)
~~~

The access hostname usually remains account.file.core.windows.net, while private link DNS directs the client to the private IP. This enables tools and applications to use the service-supported hostname and perform proper TLS/SMB identity validation.

### 8.2. DNS must be correct in both Azure and on-premises

In a VNet setup using Private DNS, the relevant zone is typically:

~~~text
privatelink.file.core.windows.net
~~~

You must link the zone to allowed VNets or configure appropriate DNS forwarding if using custom DNS and on-premises networks. From a VM inside the network intended to mount the share, you can verify:

~~~bash
nslookup <ACCOUNT>.file.core.windows.net
~~~

The command should return an IP address matching your private endpoint network design. If the client resolves to a public IP while the storage account only accepts private traffic, mounting may fail even though the resource status is Succeeded.

Do not work around DNS issues by hardcoding a temporary private IP in long-term application configurations. Private endpoints, resources, or DNS records may change; fix the underlying zone/link/forwarding root cause.

### 8.3. Checking network ports

| Client/protocol | Check | Primary port |
|---|---|---|
| Windows SMB | Test-NetConnection -Port 445 | TCP 445 |
| Linux SMB | nc -vz or equivalent tool | TCP 445 |
| Linux NFS | nc -vz or connectivity check from an allowed host | TCP 2049 |

PowerShell example:

~~~powershell
Test-NetConnection -ComputerName "<ACCOUNT>.file.core.windows.net" -Port 445
~~~

Linux example:

~~~bash
nc -vz <ACCOUNT>.file.core.windows.net 2049
~~~

A port reporting open only indicates that TCP traffic can pass; it does not prove authentication succeeds, file permissions are right, or mount protocol options are compatible. For clients outside Azure, an ISP or firewall may block port 445; VPN/ExpressRoute and private DNS generally yield a more consistent access path.

### 8.4. Checking NSGs, firewalls, and bidirectional routing

A client with valid data permissions can still fail due to:

- VNet/subnet lacking a route to the private endpoint.
- Incorrect DNS forwarding or missing VNet link on the Private DNS zone.
- NSG or firewall blocking port 445/2049.
- Storage Account network rules disallowing the actual traffic path.
- VPN/ExpressRoute having an outbound path but missing a return route.
- Intermediate appliances modifying or filtering protocol traffic.

When troubleshooting, test in order: **DNS → TCP → authentication/mount → file operations** to minimize time spent locating the root cause.

## 9. Lab 1: Creating an SMB File Share with Azure CLI

Example of creating SMB resources for a document team in a test environment. The commands are Bash illustrations and **are not executed automatically**; they require appropriate Azure permissions, the right selected subscription, and cost budgeting.

### 9.1. Checking the subscription

~~~bash
az login
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"
~~~

Confirm you are in the correct tenant/subscription before creating any resources. When using CI/CD, prefer managed identity or workload identity federation over hardcoded account passwords.

### 9.2. Creating the resource group and Storage Account

Example using a standard account type for an SMB share:

~~~bash
az group create \
  --name rg-files-lab \
  --location southeastasia

az storage account create \
  --resource-group rg-files-lab \
  --name <UNIQUE_STORAGE_ACCOUNT_NAME> \
  --location southeastasia \
  --kind StorageV2 \
  --sku Standard_LRS
~~~

The Storage Account name must follow naming rules: lowercase letters and digits, unique within the applicable scope. Replace the placeholder with a valid name, such as stfileslababc123 if available.

Choosing Standard_LRS suits a basic SMB learning example, **not a default recommendation for production**. Evaluate redundancy, cost, network access, and the right Azure Files model.

### 9.3. Creating the SMB share

The Azure CLI provides management-plane commands for managing shares:

~~~bash
az storage share-rm create \
  --resource-group rg-files-lab \
  --storage-account <UNIQUE_STORAGE_ACCOUNT_NAME> \
  --name teamdocs \
  --enabled-protocols SMB \
  --quota 100 \
  --output json
~~~

The command above illustrates a 100 GiB quota and SMB protocol. Depending on account type/model, quota options, provisioned capacity, and CLI flags may differ; check command help if your CLI version requires different syntax.

List and inspect the share configuration:

~~~bash
az storage share-rm list \
  --resource-group rg-files-lab \
  --storage-account <UNIQUE_STORAGE_ACCOUNT_NAME> \
  --output table

az storage share-rm show \
  --resource-group rg-files-lab \
  --storage-account <UNIQUE_STORAGE_ACCOUNT_NAME> \
  --name teamdocs \
  --output json
~~~

**Creating the share does not mean it can be mounted immediately.** You still need to configure networking/Private Endpoint per your design and choose an SMB authentication method.

### 9.4. Mounting on Windows with enterprise identity

Assume the administrator has already:

- Configured identity-based SMB authentication for the account.
- Granted appropriate share-level permissions.
- Configured NTFS ACLs or directory permissions accordingly.
- Ensured the client signs in with a compatible identity and obtains Kerberos tickets per the deployment model.
- Set up DNS and network reachability to TCP 445.

On the Windows client machine:

~~~powershell
$account = "<UNIQUE_STORAGE_ACCOUNT_NAME>"
$server = "$account.file.core.windows.net"
Test-NetConnection -ComputerName $server -Port 445

$unc = "\\$server\teamdocs"
net use Z: $unc /persistent:yes
~~~

After mounting, the user can access `Z:\` as a network drive and try creating a file in a folder where they have write access. The `net use` command does not configure identity itself: without domain/Entra Kerberos and proper permissions, authentication will fail.

To remove the mapping created for the lab:

~~~powershell
net use Z: /delete
~~~

This action only removes the client drive mapping; it does not delete the Azure file share.

### 9.5. Mounting SMB on Linux when needed

Linux can mount Azure Files SMB using the CIFS client when the kernel, `cifs-utils`, DNS, and authentication method align. In a Kerberos-configured environment, an illustrative command pattern is:

~~~bash
sudo mkdir -p /mnt/teamdocs

sudo mount -t cifs \
  //<ACCOUNT>.file.core.windows.net/teamdocs \
  /mnt/teamdocs \
  -o vers=3.1.1,sec=krb5
~~~

This command requires a valid Kerberos ticket and proper client setup; it will not always work out of the box on a non-domain-joined Linux VM. If using an account key, store it in a strictly protected credentials file with a rotation process; never place keys on the command line or in shell history.

## 10. Lab 2: Creating and Mounting an NFS 4.1 Share

### 10.1. Choosing an account type that supports NFS

A common example for NFS uses a Storage Account intended for SSD/premium Azure Files. Before creation, verify that the account type, tier, region, and current network/NFS requirements support your exact scenario.

~~~bash
az storage account create \
  --resource-group rg-files-lab \
  --name <UNIQUE_NFS_ACCOUNT_NAME> \
  --location southeastasia \
  --kind FileStorage \
  --sku Premium_LRS
~~~

This is an illustrative configuration and does not guarantee every new account/tier requires or only accepts this same SKU choice. Newer provisioned models may accept different parameters depending on Azure CLI version. Verify support conditions before proceeding.

### 10.2. Creating the NFS share

~~~bash
az storage share-rm create \
  --resource-group rg-files-lab \
  --storage-account <UNIQUE_NFS_ACCOUNT_NAME> \
  --name appsdata \
  --enabled-protocols NFS \
  --quota 100 \
  --output json
~~~

If the command is rejected, distinguish between:

- Account kind/tier does not support NFS.
- Region or quota is invalid.
- Secure transfer/network access settings are incompatible with the chosen protocol.
- CLI/API version or command parameters do not match the current product.
- Principal lacks management-plane permission to create file shares.

Do not disable security controls or expose the account to the Internet just to bypass an NFS creation error. Check product requirements and establish private access properly.

### 10.3. Configuring private networking and the Linux host

Before mounting:

1. Create or verify a Private Endpoint for the account's `file` subresource.
2. Configure Private DNS, VNet links, or appropriate DNS forwarding.
3. Ensure the Linux client reaches the private IP via VNet/VPN/ExpressRoute.
4. Allow TCP 2049 with minimal scope.
5. Install the appropriate NFS client package for your distro; use NFS 4.1.
6. Align application UID/GID and permissions on the target directory.

Example on Linux:

~~~bash
sudo mkdir -p /mnt/appsdata

sudo mount -t nfs \
  -o vers=4,minorversion=1,sec=sys \
  <UNIQUE_NFS_ACCOUNT_NAME>.file.core.windows.net:/<UNIQUE_NFS_ACCOUNT_NAME>/appsdata \
  /mnt/appsdata

findmnt /mnt/appsdata
df -h /mnt/appsdata
~~~

Depending on the distro and NFS client capabilities, mount syntax may need adjustment. The mount point directory must exist, the export path must be accurate, and the share must support NFS 4.1. Notably, `sec=sys` indicates user identification via UID/GID; it is **not proof that traffic is encrypted in transit**.

To verify operations inside a permitted directory:

~~~bash
id
ls -lan /mnt/appsdata
touch /mnt/appsdata/connectivity-check.txt
ls -lan /mnt/appsdata/connectivity-check.txt
~~~

If `touch` returns Permission denied, inspect UID/GID, owner, and mode before altering network rules or widening permissions. Only delete test files when you are sure it is the file you created.

Unmount the share from the Linux machine when no longer in use:

~~~bash
sudo umount /mnt/appsdata
~~~

Do not arbitrarily run mount/unmount in production while applications hold open files; stop workloads or use an appropriate maintenance window.

### 10.4. Persisting mounts across reboots

If using system configuration such as `/etc/fstab`, consider:

- Network and DNS readiness dependencies during boot.
- Appropriate systemd automount or `nofail` options for your distro.
- SMB or NFS timeout/retry behaviors.
- Never storing keys/plaintext credentials in configuration files readable by unauthorized users.
- Ensuring workloads remain safe when the share is temporarily unavailable.

For containers/AKS, evaluate the Azure Files CSI driver and appropriate StorageClass/PersistentVolume rather than manually mounting inside individual containers. Depending on the protocol, CSI driver configuration and features may differ; do not copy an SMB StorageClass and merely replace a string with NFS without checking official guidance.

## 11. Azure Files in Kubernetes and Applications

### 11.1. When using the Azure Files CSI driver

The Azure Files CSI driver allows Kubernetes to use PersistentVolume/PersistentVolumeClaim for supported SMB or NFS scenarios. This is convenient when multiple pods need access to shared files, but keep in mind:

- The StorageClass determines the driver, SKU, and protocol.
- The CSI driver may require prior network or private endpoint configuration so nodes can mount shares.
- Application permissions still rely on the corresponding SMB or NFS mechanisms and do not automatically align with Kubernetes RBAC.
- Kubernetes access modes do not replace OS-level file locking/UID/GID semantics.
- Costs and data belong to Azure Storage and are not automatically deleted when a pod is removed under all reclaim policies.

Logical flow example:

~~~text
Application Pod
    ↓
PVC → PV → Azure Files CSI Driver
    ↓
Azure Files Share
    ↓
Storage Account (network, tier, redundancy)
~~~

When multiple replicas write to the same path, the application must handle concurrent writes. A file share may permit multiple client mounts, but that **does not guarantee the application automatically resolves write contention, file locks, or transactions**.

### 11.2. Document processing application example

A service receiving documents may write uploaded files to a share and record metadata in a database. Key considerations:

1. Use safe filenames to prevent path traversal, filename collisions, and unintended overwrites.
2. Restrict directory permissions by role or workload.
3. Implement concurrency controls and atomic operations compatible with protocol semantics.
4. Scan content for potential threats per organizational security requirements.
5. Store business metadata in the database; do not rely solely on file paths to represent transaction state.
6. Design retries/idempotency in case the network or share is temporarily unreachable.

If the application primarily handles objects over HTTP, Blob Storage and an event/queue pattern may be simpler than a network file share. Do not introduce Azure Files into an architecture if the application does not truly need file system semantics.

## 12. Performance: Latency, IOPS, Throughput, and Metadata Operations

### 12.1. Controlling factors

File share performance depends on:

- Account type/tier (HDD or SSD) and provisioning model.
- Capacity and IOPS/throughput limits per share/account.
- Block/file size and read-write ratio.
- Proportion of small files and create/open/list/stat/close operations.
- Number of concurrent clients and contention within the same directory.
- Network latency between client and storage region.
- Caching mode, mount options, encryption, and client capabilities.
- Whether the workload performs heavy file locking or sequential metadata operations.

**Client-measured latency** can differ from service-side metrics. For example, network RTT from an on-premises data center to Azure plus client processing, DNS, retries, and serialization. To evaluate accurately, measure from actual clients.

### 12.2. Distinguishing IOPS and throughput

- **IOPS:** number of I/O operations per second, critical for workloads with many small files or small blocks.
- **Throughput:** volume of data transferred per second, critical for reading/writing large files.
- **Latency:** time required for an operation to complete, directly impacting application responsiveness.
- **Concurrency:** number of threads/clients issuing requests simultaneously; increasing concurrency does not necessarily improve speed if tier or network limits are reached.

For example: a batch job reading 100,000 files of a few KB each may require heavy metadata operations; a pipeline reading 20 files of several GB each is constrained by throughput. Both workloads have the same total size but very different performance requirements.

### 12.3. Benchmarking process

1. Define realistic load profiles: file sizes, counts, read/write ratio, and concurrency.
2. Test on VMs/nodes matching production specs along the real network path.
3. Measure p50/p95 latency, IOPS, throughput, error rates, and throttling status.
4. Change one variable at a time: tier, share size/provisioned performance, worker count, region, or protocol.
5. Track costs during the same test runs.
6. Document baseline results and alert thresholds before cutover.

Do not rely solely on copying a single large file to conclude NFS or SMB is "faster." Results can be skewed by OS caching and specific workload characteristics.

## 13. Backup, Snapshots, and Recovery

### 13.1. Why isn't redundancy a backup?

Redundancy protects against certain infrastructure failures according to the service model, but it does not prevent valid delete commands, ransomware encryption, or application overwrite bugs. Therefore:

- Define RPO (acceptable data loss) and RTO (recovery time).
- Select snapshot/backup mechanisms supported for your share type, protocol, and tier.
- Configure retention, restrict backup deletion permissions, and separate administrative duties where possible.
- Test restoring both an individual file and an entire directory/share as needed.
- Record restoration test results, rather than only checking whether backup jobs succeeded.

### 13.2. Snapshots, soft delete, and Azure Backup

Azure Files provides features for share snapshots, soft delete, backup, and data protection depending on supported configurations/scenarios. **Availability can differ between SMB/NFS and across tiers/account models**; check the current feature matrix before writing runbooks.

Guidance table:

| Mechanism | Role | Questions to verify |
|---|---|---|
| Share snapshot | Captures point-in-time share state as supported | Do the share/protocol/tier support it? Who creates/deletes? How to restore? |
| Soft delete | Assists recovery in certain share-deletion scenarios | Does it apply to this share? How long is the retention period? |
| Azure Backup | Manages backup schedules and lifecycle for supported workloads | Is it currently supported for this SMB/NFS/tier/region? |
| Replication/DR | Reduces unavailability risk during infrastructure outages | Is redundancy compatible with protocol/tier? What failover steps are needed? |
| Policy-isolated independent copy | Recovers from logical corruption or widespread data loss | Is it protected against deletion by the same credentials? |

Do not assume that switching protocols automatically inherits all backup features previously implemented for SMB shares in your current model.

### 13.3. Azure File Sync in hybrid setups

**Azure File Sync** synchronizes supported SMB file shares between Azure Files and Windows Server, serving scenarios that cache frequently accessed files on-premises.

Do not treat Azure File Sync as a default synchronization solution for NFS shares. If data must be shared between Linux applications and Windows file servers, design an appropriate sync workflow or application layer and test consistency.

## 14. Monitoring and Cost Governance

### 14.1. Metrics to monitor

| Category | Signal or metric | Purpose |
|---|---|---|
| Capacity | Used capacity, quota, or provisioned capacity | Detect abnormal growth |
| Performance | Transactions, latency, ingress/egress, throttling if supported | Identify bottlenecks and workloads hitting limits |
| Availability | Availability, request errors, timeouts | Detect access outages |
| Network | Private endpoint, DNS resolution, TCP 445/2049, VPN/ExpressRoute | Separate network faults from data issues |
| Security | Access/network configuration changes, role assignments, key operations | Investigate unauthorized access or misconfigurations |
| Backup | Jobs, snapshots, retention, and restore tests | Verify recoverability |
| Cost | Capacity/provisioned tier, transactions, egress, and backup | Evaluate cost efficiency |

Azure Monitor provides metrics and diagnostic log categories per resource/service; detailed availability depends on configuration. When creating alerts, verify available metric namespaces and aggregations, and do not assume every SMB/NFS file access event is captured completely in a single log.

### 14.2. Estimating total cost

When comparing SMB and NFS, review:

- Stored data volume and provisioned capacity (if using a provisioned model).
- SSD/HDD tier, provisioned IOPS/throughput, and required limits.
- Number of transactions and metadata operations under the applicable pricing model.
- Data egress charges out of the region/Storage or across network links per current pricing.
- Private Endpoint, VPN Gateway/ExpressRoute, and Azure Monitor/Log Analytics.
- Backups, snapshots, retention, and independent data copies.
- Migration, operational, identity governance, and troubleshooting costs.

Illustrative decision example: a workload holding 2 TiB of rarely read data may not need high-performance SSD. Conversely, a workload storing only tens of GiB while accessing thousands of small files per second can be dominated by IOPS/metadata latency rather than capacity. Do not use capacity as the sole criterion.

Azure Cost Management helps analyze expenses by resource group or tag. Apply tags such as Application, Environment, Owner, and CostCenter per organizational standards; note that tags do not automatically reduce charges or lock a share when budgets are exceeded.

## 15. Real-World Scenario: Upgrading an Enterprise File Server

An enterprise operates two types of workloads:

- **Group A:** Windows employees using shared folders for reports and templates, requiring enterprise identity and department-level permissions.
- **Group B:** an image processing application running on Linux/AKS, needing an NFS filesystem so multiple workers can read shared data.

### 15.1. Design for Group A: SMB

1. Create a Storage Account and SMB share in a governed subscription/resource group.
2. Select a region close to where applications/employees connect to reduce RTT.
3. Create a private endpoint and configure DNS for VNet/hybrid connectivity as required.
4. Integrate AD DS or a supported identity-based SMB option.
5. Assign share-level permissions by group, then configure NTFS ACLs.
6. If the on-premises Windows file server must still serve employees, evaluate Azure File Sync and cloud tiering as supported.
7. Test file open/edit/delete, locking, concurrency, and restore.
8. Monitor capacity, access errors, and costs.

**Mistake to avoid:** distributing the Storage Account key broadly to everyone just to skip identity setup, as this hinders per-user auditing and increases data exposure risk.

### 15.2. Design for Group B: NFS

1. Choose an account/tier supporting Azure Files NFS 4.1 and required performance capabilities.
2. Create the NFS share and private endpoint/network rules.
3. Configure DNS for Linux/AKS nodes.
4. Confirm process UID/GID, directory ownership, and access permissions.
5. Use an NFS mount or the Azure Files CSI driver per supported patterns.
6. Run benchmarks with worker counts and file patterns resembling production.
7. Establish data policies, backup/restore, and monitoring.
8. Test recovery when a node loses connectivity or a pod is rescheduled to another node.

**Mistake to avoid:** running all containers as root and setting `chmod 777` as a "quick fix" for permission errors. This weakens access control and complicates auditing.

### 15.3. Migration and cutover plan

When migrating data from a legacy file server to Azure Files:

1. Inventory total file count, sizes, path characters, permissions, file locks, and daily churn rate.
2. Choose migration tools compatible with SMB/NFS that preserve required metadata.
3. Perform an initial copy while the workload is active if supported by the tool/process.
4. Sync incremental changes and measure cloud access performance.
5. Pilot with a small group of users/workers; verify applications and ACLs/UIDs/GIDs.
6. Schedule a write freeze or cutover window to avoid split-brain writes in two locations.
7. Update UNC paths/mount targets, applications, DNS, or CSI configurations.
8. Monitor errors, maintain a rollback plan, and reconcile data and permissions.
9. Decommission the legacy file server only after confirming complete data retention and backups per policy.

Never run mirror commands with destination-deletion behavior without checking their impact; a misconfigured sync script can propagate accidental deletions to the cloud share.

## 16. Common Issues and Troubleshooting

| Symptom | Possible cause | What to check |
|---|---|---|
| Windows cannot access UNC | TCP 445 blocked, wrong DNS, firewall, or route | Test-NetConnection, DNS, Private Endpoint, network rules |
| SMB mount returns Access denied | Missing share-level role, ACL denies access, or wrong auth | Check identity, Kerberos ticket, role, and NTFS ACL |
| SMB works only with account key | Incomplete identity integration | Check AD DS/Entra Kerberos, domain join, permissions, and account config |
| On-premises client cannot mount | DNS forwarder does not resolve private endpoint or VPN/ER lacks route | Check private DNS, TCP 445/2049, bidirectional routing |
| NFS mount: Permission denied | Mismatched UID/GID/mode or disallowed export/network rules | Check `id`, `ls -ln`, DNS, NFS endpoint, client config |
| NFS mount hangs or times out | TCP 2049 unreachable, wrong DNS/route, or gateway issue | Check connectivity from client host and network status |
| Share creation fails with Unsupported protocol | Unsupported account kind, tier, SKU, or region | Check Azure Files feature matrix and CLI version |
| Files missing after mount | Wrong share/path, mount point shadowed by another mount, or incomplete sync | `findmnt`, UNC/export path, directory listing, sync status |
| Application writes slowly | High RTT, IOPS/throughput cap, excessive metadata ops | Benchmark from client, Azure Monitor, and performance tier/model |
| Linux NFS permissions differ across nodes | Inconsistent UID/GID or pod `securityContext` | Check numeric IDs and directory permissions, not just usernames |
| Snapshots exist but restore fails | Unverified restore procedure, expired/incompatible snapshot | Check feature support, permissions, retention, and test recovery |
| Higher cost than expected | Over-provisioned capacity/IOPS, high transactions, network/backup fees | Review Cost Management and workload metrics |

**Investigation principle:** never conclude "Azure Files is down" from a single mount failure message. Isolate step by step: account/share existence → DNS → network/port → protocol → authentication → file permissions → application semantics.

## 17. Pre-Production Checklist

### Design

- [ ] Clearly define SMB vs. NFS share and which clients/applications must access it.
- [ ] Verify supported account kind, tier, region, limits, and billing model.
- [ ] Define data classification, RPO/RTO, retention, and recovery requirements.
- [ ] Plan CIDR, Private Endpoint, DNS, and hybrid connectivity if needed.
- [ ] Choose identity-based SMB or a consistent NFS access pattern.
- [ ] Avoid placing account keys in code, CI logs, or public config files.

### Functional Testing

- [ ] DNS resolves to the expected endpoint per design.
- [ ] Clients can reach TCP 445 (SMB) or 2049 (NFS).
- [ ] Mount succeeds with expected identity/permissions.
- [ ] Unauthorized users are properly denied.
- [ ] Test create/read/write/rename/delete operations matching the use case.
- [ ] Test multiple concurrent clients, file locking, and reconnection.
- [ ] Measure latency, IOPS/throughput, and load resilience.
- [ ] Test small-scale backup/restore and verify data integrity.

### Operations

- [ ] Assign owner, tags, dashboards, alerts, and troubleshooting runbooks.
- [ ] Restrict administrative privileges and govern network access changes.
- [ ] Establish key rotation policy if shared-key auth is used.
- [ ] Budget for share, backup, network, and monitoring costs.
- [ ] Prepare a cleanup plan for lab resources and preserve necessary data.

## 18. Self-Check Questions

1. **How does Azure Files differ from Managed Disks?** Azure Files provides network file shares for multiple clients over supported protocols; Managed Disks provides block storage for VMs using disk attachment.
2. **Which port does SMB typically use?** TCP 445.
3. **Which protocol version does Azure Files NFS use in common scenarios?** NFS 4.1.
4. **Does a single Azure Files share automatically serve both SMB and NFS simultaneously?** Do not assume so; protocol is a share creation property and support varies.
5. **Does a Private Endpoint automatically grant clients permission to read files?** No. It handles the network path, not data authentication and authorization.
6. **With identity-based SMB, is assigning an Azure RBAC share-level role sufficient for all file operations?** No. NTFS ACLs and supported identity sign-in conditions also apply.
7. **An NFS mount succeeds, yet writes are denied—what should you check?** UID/GID, owner/mode, and corresponding permissions.
8. **Why should Storage Account keys not be placed in production command lines?** Keys grant broad permissions and risk exposure via shell history, logs, or scripts.
9. **Should NFS be exposed over the uncontrolled Internet?** No. Use trusted networks, policies, and protect data in transit as required.
10. **Does redundancy replace backups?** No. It does not fully protect against accidental deletion or ransomware.
11. **Can Linux mount SMB?** Yes, in environments supporting CIFS/SMB and an appropriate authentication method.
12. **When unable to mount from on-premises, in what order should you troubleshoot?** DNS, network/port, protocol, authentication, file permissions, and application.
13. **Why does small total file size not always mean low cost or low performance demand?** Workloads with many small operations can be dominated by transactions, IOPS, and tier/provisioned performance.
14. **Does Azure File Sync automatically sync NFS shares?** No. Check supportability; the typical scenario is Azure Files SMB with Windows Server.
15. **After migration, what should be verified before retiring the legacy file server?** Content, metadata/permissions, applications, latest updates, backups, rollback readiness, and owner sign-off.

## 19. References

- [Azure Files documentation](https://learn.microsoft.com/azure/storage/files/) — overview, features, and management of Azure Files.
- [Planning for an Azure Files deployment](https://learn.microsoft.com/azure/storage/files/storage-files-planning) — choosing accounts, protocols, networking, and performance.
- [Azure Files SMB authentication](https://learn.microsoft.com/azure/storage/files/storage-files-active-directory-overview) — identity-based SMB authentication options.
- [Azure Files networking](https://learn.microsoft.com/azure/storage/files/storage-files-networking-overview) — Private Endpoint, firewall, and hybrid connectivity.
- [Mount an SMB Azure file share on Windows](https://learn.microsoft.com/azure/storage/files/storage-how-to-use-files-windows) — Windows client configuration and connection.
- [Mount an Azure Files NFS share](https://learn.microsoft.com/azure/storage/files/storage-files-how-to-mount-nfs-shares) — prerequisites and NFS mount commands.
- [Azure File Sync overview](https://learn.microsoft.com/azure/storage/file-sync/file-sync-introduction) — synchronizing file servers and cloud in supported scenarios.
- [Azure Files scalability and performance targets](https://learn.microsoft.com/azure/storage/files/storage-files-scale-targets) — resource limits and performance capabilities.
- [Azure Storage monitoring](https://learn.microsoft.com/azure/storage/common/monitor-storage) — metrics, diagnostics, and operational analytics.
- [Azure Storage pricing](https://azure.microsoft.com/pricing/details/storage/files/) — check current pricing models.

Support for NFS, tiers, provisioning models, encryption in transit, identity-based SMB, redundancy, snapshots, and backups may vary by time, region, and SKU. **Operational principle:** select the protocol based on application requirements, restrict networks and permissions per the authentication model, benchmark performance from real clients, and test recovery before placing critical data into production.
