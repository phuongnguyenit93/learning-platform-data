# Integrating Azure Files File Share in Spring Boot with Spring Cloud Azure

## 1. Objectives and Context

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we practice integrating Spring Boot with managed services from AWS, Azure, and Google Cloud via the respective Spring Cloud libraries; while also learning identity configuration, access permissions, storage, messaging, secret protection, and testing. This lesson belongs to the **Azure Storage** chapter and focuses on **Azure Files (File Share)** and how to use the service from Spring Boot through the capabilities provided by Spring Cloud Azure.

Suppose an accounting records management application stores reports in a shared directory. Multiple servers need to read and write the same directory structure; some legacy modules already use Java NIO, while newer modules want to manipulate files over HTTPS without mounting a drive. Azure Files supports both directions: **SMB/NFS with the OS filesystem API** and the **FileREST API with the Azure Storage File Shares SDK**. Spring Cloud Azure adds the **Spring Resource abstraction** so applications can use Resource, ResourceLoader, and WritableResource.

After this lesson, you will be able to:

- Distinguish Azure Files from Blob Storage and choose the right access method: SMB/NFS mount, Spring Resource abstraction, or FileREST SDK.
- Declare the spring-cloud-azure-starter-storage-file-share dependency and configure account/endpoint settings in Spring Boot.
- Use azure-file:// URIs to read, write, and find files through Spring Resource.
- Know when to use ShareClient, ShareDirectoryClient, and ShareFileClient directly.
- Distinguish FileREST OAuth permissions from share/ACL permissions for SMB mounts and NFS requirements.
- Organize provisioning, streaming, integration testing, error handling, and secure File Share operations.

## 2. What Is Azure Files?

**Azure Files** is a managed file share service within Azure Storage. A file share has a directory and file hierarchy similar to a traditional file server:

~~~text
Storage account: accountingstore
└── File service
    ├── Share: reports
    │   ├── 2026/
    │   │   ├── january.csv
    │   │   └── february.csv
    │   └── templates/
    │       └── summary.xlsx
    └── Share: team-documents
        └── policies/
            └── retention.pdf
~~~

Azure Files supports three primary access methods:

- **SMB (Server Message Block):** mounts a file share as a filesystem path on Windows/Linux (depending on configuration and OS). Applications use java.io and java.nio.file just like normal files.
- **NFS (Network File System):** mounts a share via NFS on supported configurations/share types; typically paired with Linux environments and corresponding network and filesystem permission requirements.
- **FileREST API:** uses HTTPS calls to manipulate shares, directories, and files. The Azure Storage File Shares SDK for Java provides Java clients over FileREST.

Azure Files fits when an application needs **shared directories, filesystem paths, file-server compatibility, or file/directory operations**. If you only need to store objects like images, videos, or PDFs by key to serve over HTTP, evaluate Blob Storage first; Blob and File Share have different access semantics.

## 3. Choosing an Integration Approach in Spring Boot

Spring Cloud Azure provides the spring-cloud-azure-starter-storage-file-share starter. This starter integrates Azure Files with the **Spring Resource abstraction**. Depending on requirements, there are three options:

| Approach | How the App Accesses Data | When to Use | Who Is Responsible |
|---|---|---|---|
| **Spring Resource + File Share starter** | ResourceLoader, azure-file:// URI, Resource/WritableResource | Basic file read/write in a Spring app wanting a unified API | Spring Cloud Azure configures the resolver and Storage connection |
| **Azure Storage File Shares SDK (FileREST)** | ShareClient, ShareDirectoryClient, ShareFileClient | Need explicit directory/file creation, metadata, leases, copy, ranges, advanced operations | Application calls the Azure SDK directly |
| **SMB/NFS Mount** | Path, Files, FileChannel on a mount point | Legacy apps already using filesystem APIs or needing a shared drive | Infrastructure/OS mounts the share; Java operates on the path |

**Key point to get right:** the starter provides a way to use Spring Resource for Blob/File Share. Do not assume every Azure Files client type or administrative operation appears as an injectable Spring bean. When specialized APIs are needed, use the Azure Storage File Shares SDK directly.

~~~mermaid
flowchart TD
    A[Spring Boot application] --> B{Access Method}
    B -->|Resource abstraction| C[File Share starter]
    B -->|Advanced FileREST| D[Azure Storage File Shares SDK]
    B -->|Filesystem API| E[SMB/NFS mount]
    C --> F[(Azure Files)]
    D --> F
    E --> F
~~~

## 4. Declaring the Spring Cloud Azure File Share Starter

### 4.1. Maven Dependencies

Declare a Spring Cloud Azure BOM compatible with your project's Spring Boot version and the File Share starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-file-share</artifactId>
    </dependency>
</dependencies>
~~~

spring-cloud-azure.version is a project-managed property. Pick the BOM from the **Spring Boot ↔ Spring Cloud Azure compatibility matrix**, rather than choosing an arbitrary version. If the app also uses Blob/Queue, add the respective starters or consider the umbrella spring-cloud-azure-starter-storage starter depending on needs.

### 4.2. Configuration in application.yml

~~~yaml
spring:
  cloud:
    azure:
      storage:
        fileshare:
          enabled: true
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}
          endpoint: ${AZURE_STORAGE_FILESHARE_ENDPOINT}

app:
  files:
    share-name: ${AZURE_FILES_SHARE:reports}
~~~

Spring Cloud Azure File Share properties use the spring.cloud.azure.storage.fileshare prefix:

- enabled: enables/disables File Share auto-configuration; usually defaults to true when the starter is present.
- account-name: storage account name.
- endpoint: File Share endpoint, typically https://<account>.file.core.windows.net on Azure public cloud.
- account-key: configurable in some Shared Key scenarios, but **never commit keys into configuration files**.

When using Microsoft Entra ID/managed identity, omit account keys; configure Spring Cloud Azure's shared credentials per environment. With **user-assigned managed identity**, set spring.cloud.azure.credential.client-id to the client ID of the identity attached to the workload. With system-assigned identity, let the SDK/runtime select the resource-bound identity.

Example specifying a user-assigned identity (place in an Azure profile when needed):

~~~yaml
spring:
  cloud:
    azure:
      credential:
        client-id: ${AZURE_CLIENT_ID}
~~~

Do not use AZURE_CLIENT_ID in place of **principal/object ID** when assigning roles. Client ID selects the identity in config; role assignments target the corresponding principal.

### 4.3. Resources Must Be Provisioned Ahead of Time

The starter helps the application connect and work with resources, but adding the dependency does not create the storage account or file share. Provision via **Bicep, Terraform, ARM templates, Azure CLI, or infrastructure pipelines**:

- Storage account and file share.
- Quota/capacity, redundancy, and network settings.
- Workload identity and role assignments.
- Pre-existing directories if write flows depend on an existing folder structure.

Separate provisioning permissions from runtime permissions. An API that only reads/writes files in an existing share does not need permissions to create storage accounts or modify subscription settings.

## 5. Using Spring Resource Abstraction with azure-file://

### 5.1. Injecting a Resource with @Value

Spring Cloud Azure registers the azure-file:// URI resolution mechanism. You can inject a Resource directly:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@Component
public class ReportResource {
    @Value("azure-file://reports/2026/summary.csv")
    private Resource summaryFile;

    public Resource getSummaryFile() {
        return summaryFile;
    }
}
~~~

In the URI:

- reports is the **file share name**.
- 2026/summary.csv is the directory/file path inside the share.
- This URI is handled by Spring Cloud Azure's resolver; it is not a public URL for browsers to download directly.

Never pass user-supplied paths directly into annotations or concatenate strings arbitrarily. For dynamic paths, verify document ID/business authorization and canonicalize the path before invoking the resolver.

### 5.2. Obtaining a Resource with ResourceLoader

When the resource must be determined at runtime, inject ResourceLoader:

~~~java
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class FileShareResourceService {
    private final ResourceLoader resourceLoader;

    public FileShareResourceService(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource getFile(String shareName, String relativePath) {
        String location = "azure-file://" + shareName + "/" + relativePath;
        return resourceLoader.getResource(location);
    }
}
~~~

This example illustrates the resolver mechanism. In a real application, shareName and relativePath must come from authorized data; prevent clients from passing `../` traversal sequences, cross-tenant share names, or paths outside allowed regions.

### 5.3. Reading Files via InputStream

Resource exposes getInputStream() for streaming reads:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;

public String readSmallText(Resource resource) throws IOException {
    try (InputStream input = resource.getInputStream()) {
        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }
}
~~~

Using readAllBytes() is strictly for **small, size-bounded files**. For large files, stream to an output or process in chunks to avoid holding the entire content in the heap:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.core.io.Resource;

public void downloadToLocalFile(Resource resource, Path target)
        throws IOException {
    try (InputStream input = resource.getInputStream();
         OutputStream output = Files.newOutputStream(target)) {
        input.transferTo(output);
    }
}
~~~

This snippet uses Java 9+ and assumes the destination directory exists. When streaming to an HTTP response, verify user permissions first, set appropriate Content-Type/Content-Disposition headers, and handle client disconnects.

### 5.4. Writing Files via WritableResource

To write, cast the resource to WritableResource:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;
import org.springframework.core.io.WritableResource;

public void writeText(Resource resource, String content)
        throws IOException {
    if (!(resource instanceof WritableResource writable)) {
        throw new IllegalArgumentException("Resource does not support writing");
    }

    try (OutputStream output = writable.getOutputStream()) {
        output.write(content.getBytes(StandardCharsets.UTF_8));
    }
}
~~~

getOutputStream() opens a write stream to the file resource. Behavior when the file already exists depends on the resolver implementation and version; never assume it always appends. Clearly define business semantics (**create new, overwrite, or append**), check file/directory existence, and test the behavior against your starter version.

Spring Cloud Azure resource handling documentation notes that **files larger than 4 MiB are uploaded in parallel** during the resolver's multipart upload flow. This is a starter implementation detail, not a guarantee that every app configuration yields identical throughput; measure in practice with your file sizes, concurrency, network, and SDK version.

### 5.5. Finding Resources by Pattern

Spring Cloud Azure includes protocol resolvers for Blob and File Share. For File Share, AzureStorageFileProtocolResolver can locate files matching an azure-file:// pattern:

~~~java
import org.springframework.core.io.Resource;
import com.azure.spring.cloud.core.resource.AzureStorageFileProtocolResolver;

public Resource[] findTextFiles(
        AzureStorageFileProtocolResolver resolver) {
    return resolver.getResources("azure-file://reports/**/*.txt");
}
~~~

Pattern search is handy for batch jobs or reading a small group of files. Do not use it to replace database queries over large stores; consider pagination, result limits, permissions, and listing costs. The import above uses the package from current Spring Cloud Azure releases; verify exact package/class names against your project's BOM during major upgrades.

## 6. When Specialized APIs Are Needed: Azure Storage File Shares SDK

Spring Resource suits basic file operations. When you need explicit directory/file creation, metadata/SMB property management, leases, copying, detailed listing, or range operations, use the **Azure Storage File Shares SDK for Java**.

### 6.1. SDK Dependencies

Add the azure-storage-file-share and Azure Identity artifacts. Manage versions using the Azure SDK BOM or dependency management compatible with your Spring Cloud Azure setup:

~~~xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-storage-file-share</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
</dependency>
~~~

If your Spring Cloud Azure BOM already manages the corresponding Azure SDK versions, do not override them with a mismatched version. When using the SDK standalone, import azure-sdk-bom to keep Azure SDK artifacts aligned.

### 6.2. Creating a ShareClient with Microsoft Entra ID

ShareClient is the entry point for accessing a file share. Use DefaultAzureCredential for local developer identity and workload/managed identity on Azure:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.file.share.ShareClient;
import com.azure.storage.file.share.ShareClientBuilder;

String accountName = System.getenv("AZURE_STORAGE_ACCOUNT_NAME");
String shareName = "reports";
String endpoint = "https://" + accountName + ".file.core.windows.net";

TokenCredential credential =
        new DefaultAzureCredentialBuilder().build();

ShareClient shareClient = new ShareClientBuilder()
        .endpoint(endpoint)
        .shareName(shareName)
        .credential(credential)
        .buildClient();
~~~

This snippet assumes the Azure public cloud endpoint and a pre-created share. For sovereign clouds or custom endpoints, supply the corresponding endpoint. Never hardcode account keys/connection strings in source; if Shared Key is unavoidable in an environment, store the secret in a secret manager and restrict access.

### 6.3. Creating Directories and Files

Core clients:

| Client | Scope | Example Operations |
|---|---|---|
| ShareClient | One file share | Get root directory, get directory client, access snapshots |
| ShareDirectoryClient | One directory | Create/list directory, create file, delete file or empty directory |
| ShareFileClient | One file | Upload/download, properties, metadata, lease, delete |

Example creating a directory and a new file:

~~~java
import com.azure.storage.file.share.ShareDirectoryClient;
import com.azure.storage.file.share.ShareFileClient;

ShareDirectoryClient root = shareClient.getRootDirectoryClient();
ShareDirectoryClient yearDirectory =
        root.createSubdirectoryIfNotExists("2026");

long fileSize = 1024;
ShareFileClient file = yearDirectory.createFile("summary.csv", fileSize);
~~~

createFile(fileName, maxSize) creates a file with the declared maximum/initial size per the API. If the file already exists, creation can return a conflict; use a unique name or a controlled update workflow. Never call getFileClient() and assume the file already exists on Azure.

### 6.4. Uploading from a Local File

~~~java
import com.azure.storage.file.share.ShareFileClient;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public void uploadNewFile(
        ShareDirectoryClient directory,
        Path source,
        String fileName) throws IOException {

    long size = Files.size(source);
    ShareFileClient target = directory.createFile(fileName, size);
    target.uploadFromFile(source.toString());
}
~~~

This code creates a new file and uploads contents from a local file. For large payloads, the SDK provides upload APIs supporting ParallelTransferOptions; tune transfer settings to RAM/bandwidth and FileREST limits. When writing to an existing file, resize/set ranges or use a proper update workflow rather than assuming uploadFromFile safely handles every overwrite case.

### 6.5. Downloading to an OutputStream

~~~java
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public void downloadFile(
        ShareFileClient source,
        Path destination) throws IOException {
    try (OutputStream output = Files.newOutputStream(destination)) {
        source.download(output);
    }
}
~~~

ShareFileClient.download(OutputStream) writes data to a stream. Avoid ByteArrayOutputStream for large files because it retains all data in the heap. If you want the SDK to write to a local file, downloadToFile(path) is available; per SDK documentation, the destination file must not already exist.

### 6.6. Listing and Deleting

~~~java
for (var item : yearDirectory.listFilesAndDirectories()) {
    System.out.println(
            (item.isDirectory() ? "[DIR] " : "[FILE] ") + item.getName());
}

boolean deleted = yearDirectory.deleteFileIfExists("summary.csv");
~~~

Directories can only be deleted when empty; handle contained files and subdirectories per policy beforehand. Never let end users pass arbitrary paths to delete files without verifying ownership, tenant, and business state.

## 7. Mounting SMB/NFS and Using Java NIO

If an application is already built around a filesystem, you can mount the Azure File Share on the server/container and use Java I/O:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

Path mountedShare = Path.of(System.getenv("AZURE_FILES_MOUNT"));
Path report = mountedShare.resolve("2026/summary.csv");

Files.createDirectories(report.getParent());
Files.copy(
        Path.of("local/summary.csv"),
        report,
        StandardCopyOption.REPLACE_EXISTING);
~~~

This code only operates on **an already-mounted path**; Spring Boot does not mount shares itself. Deployment infrastructure must:

- Configure SMB or NFS according to share type and supported OS.
- Set up networking, DNS, firewalls, and appropriate credentials.
- Attach the volume/mount point to the VM or container.
- Grant filesystem/ACL permissions to the Java process.
- Monitor connections, handles, locks, and I/O errors during share/network disruptions.

SMB can use identity-based authentication with share-level permissions and file/directory ACLs. NFS uses its own permission model and network constraints. Never assume FileREST RBAC settings automatically grant SMB/NFS mount access.

## 8. Authentication and Authorization for Azure Files

### 8.1. Distinguishing FileREST from SMB/NFS

| Access Method | Authentication/Authorization | Points to Note |
|---|---|---|
| Spring Resource/FileREST | Microsoft Entra ID/OAuth or SDK/resolver-supported mechanism | Data-plane role must cover FileREST operations |
| Azure Storage File Shares SDK/FileREST | TokenCredential, e.g., DefaultAzureCredential | Some share-level operations do not support OAuth like file/directory operations; verify specific APIs |
| SMB mount | Identity-based authentication or configured SMB auth | Combines share-level permissions and file/directory ACLs |
| NFS mount | POSIX/UID/GID permissions and network rules per share config | Do not treat this as the same OAuth/RBAC model as FileREST |

### 8.2. Roles for FileREST OAuth

For FileREST examples using Microsoft Entra ID, Azure Files documentation instructs assigning the **Storage File Data Privileged Contributor** role to the security principal. This role grants read, write, ACL modification, and delete permissions across shares in scope even when file/directory ACLs are restrictive; it is a **very powerful** role and must be weighed carefully.

Assign this broad role only to workloads that genuinely need privileged permissions. For read-only workloads, check appropriate read-only roles and supported operations; never grant Contributor to every service by default.

For SMB, share-level roles exist such as **Storage File Data SMB Share Reader**, **Storage File Data SMB Share Contributor**, or **Storage File Data SMB Share Elevated Contributor**, paired with ACL/NTFS permissions per identity configuration. SMB roles are not drop-in replacements for FileREST OAuth roles.

### 8.3. Share-Level Limitations

Not all Azure Files operations support Microsoft Entra OAuth equally. Azure Files documentation notes that OAuth tokens are not accepted for certain **file-share-level data-plane** operations, such as snapshot/share-level operations described in the SDK guide; those operations may require Shared Key or appropriate management mechanisms. Therefore:

- Use Entra ID for FileREST file/directory operations supported by the service.
- Provision shares and manage account/share-level resources via IaC or Azure Resource Manager where appropriate.
- Verify authorization requirements per API before designing one identity for all operations.
- Never silently fall back to an account key when OAuth returns 403.

### 8.4. Secret and Network Protection

- Prefer managed identity on Azure; locally use developer identity per organizational policy.
- Never commit account keys/connection strings to Git, and never log tokens or secrets.
- If Shared Key is unavoidable, store it in Azure Key Vault or an equivalent secret manager, restrict read access, and plan rotation.
- Enforce HTTPS/TLS for FileREST; verify storage firewalls, private endpoints, DNS, and network routes.
- For SMB/NFS, verify protocols/ports, mount options, and connectivity from subnets/containers.

## 9. Managing Shares and Resources at the Infrastructure Layer

The File Share starter focuses on **file access via Spring Resource**. When you need to create/delete storage accounts or file shares at the resource level, use Azure Resource Manager/IaC or Azure Storage management libraries. That is the infrastructure management layer, with different permissions and lifecycles from file/directory operations.

| Task | Tool to Consider |
|---|---|
| Create storage account, configure networking | Bicep/Terraform/ARM |
| Create file share, set quota | IaC or Azure Storage management library |
| Read/write files via azure-file:// URI | Spring Cloud Azure File Share starter |
| Create directories/files, list, copy, lease via FileREST | Azure Storage File Shares SDK |
| Use an existing filesystem path | SMB/NFS mount + Java NIO |

Never assign subscription Owner to a runtime workload just so the app can create a file share. If automated share provisioning is needed, use a separate administrative workflow with bounded permissions and auditing.

## 10. Locking, Concurrency, and SMB/FileREST Differences

Azure Files uses distinct access-coordination mechanisms:

- SMB uses filesystem locking/handles managed by the protocol and OS.
- FileREST SDK can use **leases** to govern write/delete access on a file via a lease ID.
- When accessing the same file simultaneously via SMB and FileREST, do not assume every lock type shares identical semantics or interoperates automatically.

For example, a legacy application might use FileChannel.lock() on an SMB mount:

~~~java
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path file = Path.of(
        System.getenv("AZURE_FILES_MOUNT"), "reports/summary.csv");

try (FileChannel channel = FileChannel.open(
        file, StandardOpenOption.WRITE, StandardOpenOption.READ);
     FileLock lock = channel.lock()) {
    // Perform updates while holding the lock.
}
~~~

FileREST leases have dedicated APIs such as ShareLeaseClient. When using leases, manage acquire, renew (if needed), and release across the proper lifecycle; if a process crashes, plan for lease expiration handling. Never use SMB file locks in one module and FileREST leases in another assuming they coordinate seamlessly without testing.

## 11. Integration Testing

### 11.1. Azurite Does Not Replace Azure Files

Azurite is useful for emulating certain Azure Storage APIs such as Blob/Queue/Table, yet **does not provide a full Azure Files share** for testing the starter, FileREST, SMB, or NFS. Therefore:

- Unit tests can mock business interfaces to verify service logic.
- File Share integration tests require a **test Azure Storage account** with a dedicated share.
- SMB/NFS tests must run on an OS/container environment with real mounts and networking.
- Entra ID/RBAC/private endpoint tests require real principals and matching Azure configuration.

Never embed production account keys in tests; use dedicated test identities or secrets and clean up resources safely.

### 11.2. Test Cases to Include

| Test Case | Expected Result |
|---|---|
| ResourceLoader opens azure-file://share/path/file | Reads exact content when share/file exist and identity is authorized |
| WritableResource.getOutputStream() | Writes content per the active resolver/version semantics |
| File larger than 4 MiB | Verifies successful upload, throughput, and actual RAM usage |
| Non-existent path or share | Error is cleanly classified; no unintended resources created |
| Identity lacks FileREST role | Request rejected; app does not fall back to hardcoded keys |
| SMB mount lacks ACL permissions | Java I/O reports appropriate error; role/share permissions/ACLs checked separately |
| File Share network interruption | Bounded timeouts/retries; threads do not hang indefinitely |
| Two processes write the same file | Lock/lease or overwrite rules behave as designed |
| Target file already exists | Overwrite/append behavior is documented and handled properly |
| Large file download | Uses stream/file output without holding entire content in heap |
| Delete non-empty directory | Rejected per service rules or contents cleaned up under control |

### 11.3. Resource Round-Trip Test Example

The test snippet below demonstrates reading/writing via ResourceLoader. In real test suites, use JUnit, unique filenames, and cleanup:

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.core.io.WritableResource;

String location = "azure-file://test-share/integration/hello.txt";
Resource resource = resourceLoader.getResource(location);

if (!(resource instanceof WritableResource writable)) {
    throw new IllegalStateException("Resource does not support writing");
}

try (OutputStream output = writable.getOutputStream()) {
    output.write("hello-file-share".getBytes(StandardCharsets.UTF_8));
}

try (InputStream input = resource.getInputStream()) {
    String actual = new String(input.readAllBytes(), StandardCharsets.UTF_8);
    if (!"hello-file-share".equals(actual)) {
        throw new AssertionError("Read content does not match");
    }
}
~~~

This example assumes the share, directory, and permissions are already provisioned; verify file/parent-directory creation semantics for your resolver version. This test uses a small string; for large files, verify streaming and avoid readAllBytes().

## 12. Common Errors and Troubleshooting

| Symptom | Causes to Check | Remediation |
|---|---|---|
| Cannot resolve azure-file:// | Missing File Share starter, resolver not auto-configured, or malformed URI | Check dependencies, profiles, prefixes, and versions |
| HTTP 403 | Missing FileREST OAuth role, wrong identity, or Shared Key blocked | Identify principal, role, operation, and auth mode |
| SMB Access denied | Insufficient share-level role or ACL/NTFS permissions | Check identity provider, share role, and file/directory ACLs |
| HTTP 404 | Wrong share/path or directory/file not yet created | Verify resource and provisioned paths |
| HTTP 409 | Share/file/directory already exists or concurrent operation conflict | Use unique names or create-if-not-exists per API |
| Timeout on mount | Network, DNS, protocol/port, or firewall | Check routes, private endpoints, and mount options |
| File unexpectedly overwritten | OutputStream/SDK upload using overwrite semantics | Define create/update/append; use unique names or locks/conditions |
| Slow large-file upload | Transfer options, concurrency, network, and service limits | Measure throughput; tune parallel transfers and concurrency limits |
| OAuth rejected on share operation | Share-level operation does not support Entra OAuth in current API | Use management plane or the mechanism required by the operation docs |
| Azurite tests pass but Azure Files fails | Emulator does not emulate File Share | Run integration tests against an Azure test account |

When investigating, log the operation, sanitized share/path, correlation ID, and error code; never log account keys, connection strings, or tokens. Distinguish **authentication**, **authorization**, **network**, and **resource path** failures before altering permissions.

## 13. Security and Production Operations

Principles when moving File Share to production:

1. **Pick the right protocol:** FileREST for cloud-native APIs; SMB/NFS when a filesystem is needed. Avoid mixing both on the same data without understanding locking, caching, and consistency.
2. **Separate runtime and provisioning rights:** file-processing services need no permissions to create storage accounts or alter role assignments.
3. **Use least-privilege identities:** FileREST OAuth roles and SMB share-level roles/ACLs are distinct models; grant permissions only for actual operations.
4. **Manage paths safely:** map business IDs to server-controlled paths; block path traversal and cross-tenant share access.
5. **Bound resources:** limit upload sizes, concurrent tasks, timeouts, thread pools, and temp disk space.
6. **Plan recovery:** configure backups/snapshots as needed, test restores and retention; never treat a mounted share as a backup.
7. **Observe:** monitor latency, bytes transferred, failed requests, network disconnects, file handles/leases, and share capacity/quotas.
8. **Test on version upgrades:** verify URI resolvers, authentication, parallel uploads, and SDK behavior after every BOM upgrade.

## 14. Practice Scenarios and Self-Check Questions

**Scenario A — Legacy application:** A Java app uses Files.copy() and FileChannel.lock() on a shared folder. Choose an SMB mount, list the infrastructure and permission prerequisites to configure, and explain why merely adding the File Share starter does not mount the share.

**Scenario B — File-processing service via REST:** An API needs to read/write files by ID without mounting volumes. Use spring-cloud-azure-starter-storage-file-share, ResourceLoader, and azure-file:// URIs; identify which operations should move to the File Shares SDK.

**Scenario C — File Share OAuth returns 403:** Local developer runs succeed, but managed identity on Azure is denied. Inspect the selected identity, matching File Data role, operation type (file/directory vs. share-level), endpoint, and networking.

**Scenario D — Upload reports conflict:** Two requests simultaneously create summary.csv. Design unique filenames or a controlled update workflow; explain why getFileClient() only returns a reference handle without creating the file.

**Scenario E — Multi-cloud comparison:** Azure Files provides SMB/NFS/FileREST; AWS offers file services like Amazon EFS/FSx with distinct protocols and characteristics; Google Cloud offers Filestore for NFS. Compare across **mount protocols, SDK APIs, identity/permissions, lock semantics, and application compatibility**—never assume one starter or API drops cleanly into every provider.

### Self-Check Questions

1. **What does the Spring Cloud Azure File Share starter provide?** The Spring Resource abstraction and the azure-file:// resolver for reading/writing File Share resources the Spring way.
2. **Does the starter automatically mount SMB/NFS on the app host?** No. Mounting is an OS/infrastructure responsibility; Java NIO simply operates on the mount point.
3. **When do you need the azure-storage-file-share SDK directly?** When you need specialized APIs like ShareClient/DirectoryClient/FileClient, create/list/delete, metadata, leases, copy, or ranges.
4. **What parts make up azure-file://reports/2026/summary.csv?** The reports share and the 2026/summary.csv path inside that share.
5. **Why doesn't the Blob Data Contributor role grant File Share permissions?** Blob and Files are separate data-plane services; roles and authorization models must target File Share.
6. **Why can't FileREST OAuth and SMB ACLs be treated as the same mechanism?** FileREST uses tokens/roles per supported operation; SMB combines share-level permissions and filesystem ACLs.
7. **Is Azurite sufficient for testing Azure Files?** No; you need an Azure Storage test account for File Share and a real mount environment for SMB/NFS.

## 15. Summary

Azure Files provides managed file shares accessible via **SMB, NFS, or FileREST**. In Spring Boot, spring-cloud-azure-starter-storage-file-share integrates File Share with the **Spring Resource abstraction** through azure-file:// URIs, ResourceLoader, Resource, and WritableResource. When granular control over share/directory/file operations is needed, use the azure-storage-file-share SDK; when filesystem compatibility is needed, mount SMB/NFS and use Java NIO.

The key is choosing the right **access and authorization model**: FileREST OAuth, SMB share permissions/ACLs, and NFS POSIX/network rules have distinct requirements. Combine managed identity, least privilege, IaC provisioning, testing against real Azure, and network monitoring for reliable File Share integration in Spring Cloud Azure.

### Official References

- [Microsoft Learn — Spring Cloud Azure resource handling](https://learn.microsoft.com/azure/developer/java/spring-framework/resource-handling)
- [Microsoft Learn — Spring Cloud Azure configuration reference](https://learn.microsoft.com/azure/developer/java/spring-framework/configuration)
- [Microsoft Learn — Develop for Azure Files with Java](https://learn.microsoft.com/azure/storage/files/storage-java-how-to-use-file-storage)
- [Microsoft Learn — Azure Files identity-based authentication for SMB](https://learn.microsoft.com/azure/storage/files/storage-files-identity-auth-smb)
- [Microsoft Learn — Azure Storage File Shares client library for Java](https://learn.microsoft.com/java/api/com.azure.storage.file.share)
- [Microsoft Learn — ShareFileClient Java API](https://learn.microsoft.com/java/api/com.azure.storage.file.share.sharefileclient)
- [Microsoft Learn — ShareDirectoryClient Java API](https://learn.microsoft.com/java/api/com.azure.storage.file.share.sharedirectoryclient)
- [Microsoft Learn — Auto-configure Azure SDK clients with Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/auto-configure-azure-sdk-clients)
