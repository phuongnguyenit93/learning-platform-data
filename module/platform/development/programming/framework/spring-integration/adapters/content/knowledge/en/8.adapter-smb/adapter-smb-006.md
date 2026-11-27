# UNC Paths and Directory Mapping in Spring Integration SMB

## 1. Problem and Objectives

A partner provides a Windows shared directory:

```text
\\fs01.corp.example\exchange\incoming\partner-a\orders-20261123.csv
```

The Spring Boot application needs to fetch this CSV file to the application host for data import; after importing, the application outputs a confirmation file to:

```text
\\fs01.corp.example\exchange\outgoing\partner-a\orders-20261123.ack
```

In code, we must answer concrete questions: which part is the **server**, which part is the **share**, and which part is the **remote directory**? On a Linux container with no `Z:` drive like a Windows employee's workstation, where are files downloaded? If an adapter already points to the `exchange` share, why must `exchange` not be repeated in `remoteDirectory`? How do we map files accurately across `incoming/outgoing/archive` directories without accidentally writing into another partner's data?

This lesson belongs to the **Adapter SMB** chapter of the `SPRING_INTEGRATION_ADAPTERS` module. The module focuses on connecting external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing file, SFTP, HTTP, JMS, AMQP, Kafka, and database flows; and handling message contracts, errors, and connection lifecycles. Here, the focus is on **UNC paths and remote ↔ local path mapping rules** when using Spring Integration SMB.

After this lesson, you will be able to:

- Parse a UNC path `\\server\share\folder\file` into host, share, remote directory, and filename.
- Distinguish UNC paths, `smb://` URIs, local paths on Windows/Linux, and mapped network drives.
- Configure `SmbSessionFactory.setShareAndDir(...)`, `remoteDirectory(...)`, and `localDirectory(...)` accurately.
- Trace the path of `Message<File>` when SMB inbound downloads files locally and when outbound writes to a share.
- Use an outbound gateway for path-based operations such as `ls/get/mv`, including hierarchical directories.
- Design per-partner mapping while preventing name collisions, path traversal, wrong shares, and lost source metadata.
- Troubleshoot path errors, read/write permissions, path separators, and Windows/Linux environment differences.

## 2. Structure of a UNC Path

**UNC (Universal Naming Convention)** is the standard Windows representation for network resources. Common format:

```text
\\server\share\directory\subdirectory\filename.ext
  └──┘  └──┘ └──────────────────┘ └────────┘
   host  share  path inside share   filename
```

With the example:

```text
\\fs01.corp.example\exchange\incoming\partner-a\orders-20261123.csv
```

we break it down into:

| Component | Value | Role |
|---|---|---|
| Server/host | `fs01.corp.example` | SMB server, reachable via DNS or IP |
| Port | `445` (typical) | SMB port over TCP; not normally shown in a UNC path |
| Share | `exchange` | Shared resource name on the server |
| Remote directory | `incoming/partner-a` | Relative subdirectory inside the share |
| Filename | `orders-20261123.csv` | Target file to read |
| Full UNC | `\\fs01.corp.example\exchange\incoming\partner-a\orders-20261123.csv` | How Windows represents the resource location |

The leading `\\` is the UNC prefix; subsequent `\` characters separate components on Windows. When writing a **Java string literal**, `\` must be escaped:

```java
String unc = "\\\\fs01.corp.example\\exchange\\incoming\\partner-a\\orders-20261123.csv";
System.out.println(unc);
// \\fs01.corp.example\exchange\incoming\partner-a\orders-20261123.csv
```

This Java string is just a **representation** of UNC. In Spring Integration SMB, we normally do not pass this entire string into an adapter. We configure host/share on `SmbSessionFactory`, and directories/filenames on the endpoint.

### 2.1. UNC vs. SMB URI

An SMB client can express the same resource in URI form:

```text
UNC:     \\fs01.corp.example\exchange\incoming\partner-a\orders-20261123.csv
SMB URI: smb://fs01.corp.example/exchange/incoming/partner-a/orders-20261123.csv
```

URIs use `/`; special characters must be URI-encoded properly. Spring Integration uses an underlying Java CIFS/SMB library; `SmbConfig` holds host, domain, credentials, and `shareAndDir` to build connection details. **Never build a URI embedding a password for logs or public configs.**

The URI format above is only for visualizing the destination; code uses `SmbSessionFactory` setters. Domain/authentication credentials are **separate** information, not directory or share names:

```text
host     = fs01.corp.example
share    = exchange
domain   = CORP
username = svc_smb_integration
password = <secret from config system>
```

### 2.2. Commonly Confused Paths

| Value | Format | Is It an SMB Adapter `remoteDirectory` Parameter? |
|---|---|---|
| `\\fs01\exchange\incoming` | Windows UNC | **No**. This is the entire host/share/path |
| `smb://fs01/exchange/incoming` | SMB client URI | **No** for the `remoteDirectory` field in the sample config |
| `incoming/partner-a` | Relative path inside the share | **Yes**, when the factory already points to share `exchange` |
| `C:/app/data/smb-inbox` | Local path on Windows | Used for `localDirectory` |
| `/var/lib/app/smb-inbox` | Local path on Linux | Used for `localDirectory` |
| `Z:\incoming` | Mapped network drive in a Windows session | Should not be relied upon in a Spring Integration SMB client |

**Common mistake:** passing `remoteDirectory("\\\\fs01\\exchange\\incoming")` when the factory already sets host/share. The endpoint can then construct a malformed path or look for a nonexistent directory. Remote parameters must be relative to the **root configured on the session**.

## 3. Choosing a Consistent Root

Throughout this lesson's examples, we establish:

```text
Windows File Server: fs01.corp.example
Share:               exchange
Inbound directory:   incoming/partner-a
Outbound directory:  outgoing/partner-a
Archive directory:   archive/partner-a
Local inbound dir:   ./data/smb-inbox/partner-a
Local outbox dir:    ./data/smb-outbox/partner-a
```

And establish the relationship:

```mermaid
flowchart LR
    subgraph SMB["SMB server: \\fs01\exchange"]
      A["incoming/partner-a/*.csv"]
      B["outgoing/partner-a/*.ack"]
      C["archive/partner-a/*.csv"]
    end
    subgraph APP["Spring Boot application host"]
      D["./data/smb-inbox/partner-a/"]
      E["Process / import data"]
      F["./data/smb-outbox/partner-a/"]
    end
    A -->|Inbound: download| D
    D --> E
    E --> F
    F -->|Outbound: upload| B
    A -.->|Gateway mv once processed| C
```

Review the mapping table before writing configuration:

| Action | Remote Windows/SMB Path | Local Path |
|---|---|---|
| Read report | `\\fs01\exchange\incoming\partner-a\orders.csv` | `./data/smb-inbox/partner-a/orders.csv` |
| Generate confirmation | Not on remote yet | `./data/smb-outbox/partner-a/orders.ack` |
| Send confirmation | `\\fs01\exchange\outgoing\partner-a\orders.ack` | Source: `./data/smb-outbox/partner-a/orders.ack` |
| Archive after import | Source: `incoming/partner-a/orders.csv` → target: `archive/partner-a/orders.csv` | No extra local copy required |

Here, `incoming`, `outgoing`, and `archive` are **three different directories inside the same share**; they are not three separate shares. If a partner truly provides three distinct shares, create corresponding factories/connection points rather than changing only `remoteDirectory`.

### 3.1. Role of `setShareAndDir(...)`

The `SmbConfig.setShareAndDir(...)` API accepts share details and can include a base path inside the share depending on client configuration. To keep control clear and avoid duplicated directories, this lesson uses:

```java
factory.setShareAndDir("exchange");
```

Endpoints then specify relative paths like `incoming/partner-a`. If a project chooses `setShareAndDir("exchange/base")` to anchor at a deeper root, every `remoteDirectory` and request path must be re-verified relative to that **new root**. Do not append `base` a second time; verify with `ls` in a lab environment before writing files.

### 3.2. Forward Slashes `/` in Remote Paths

On Windows, users are accustomed to `\`. In Spring Integration SMB Java DSL configuration, official examples use paths like `"smbSource"` or `"smbTarget"`; when nested, prefer `/` consistently to express **remote paths inside the share**:

```text
Valid per lesson convention: incoming/partner-a
Do not mix separators:       incoming\partner-a
Do not put full UNC:         \\fs01\exchange\incoming\partner-a
```

Spring Integration's remote-file components handle separators per protocol/endpoint; when using advanced settings such as `remote-file-separator`, ensure separators stay consistent. Do not assume Windows `\` works everywhere after passing through SpEL, YAML, Java string literals, or the SMB client.

## 4. Java DSL Configuration with Clear Path Mapping

The example below targets compatible Spring Integration 6.x and Spring Boot 3.x. Choose a `spring-integration-smb` version compatible with your project's dependency management.

**Gradle:**

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-smb'
}
```

### 4.1. Environment-Driven Configuration

**`application.yml`:**

```yaml
demo:
  smb:
    host: ${SMB_HOST:fs01.corp.example}
    port: ${SMB_PORT:445}
    domain: ${SMB_DOMAIN:CORP}
    username: ${SMB_USERNAME}
    password: ${SMB_PASSWORD}
    share: ${SMB_SHARE:exchange}
    inbound-dir: ${SMB_INBOUND_DIR:incoming/partner-a}
    outbound-dir: ${SMB_OUTBOUND_DIR:outgoing/partner-a}
    local-inbound-dir: ${SMB_LOCAL_INBOUND_DIR:./data/smb-inbox/partner-a}
```

In production, all hosts/shares/paths should come from trusted configuration; `SMB_USERNAME` and `SMB_PASSWORD` must be supplied from a secret manager or appropriate secret-protection mechanism. Default values here illustrate path structure, not real enterprise configuration.

**Key relationship:**

```text
SmbSessionFactory(host, share = exchange)
    + inbound-dir = incoming/partner-a
    + remote filename = orders-20261123.csv
    = \\fs01.corp.example\exchange\incoming\partner-a\orders-20261123.csv

local-inbound-dir = ./data/smb-inbox/partner-a
    + local filename = orders-20261123.csv
    = ./data/smb-inbox/partner-a/orders-20261123.csv
```

### 4.2. Declaring the Session Factory

**`SmbPathConfig.java`:**

```java
import java.io.File;

import jcifs.DialectVersion;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.remote.FileExistsMode;
import org.springframework.integration.smb.dsl.Smb;
import org.springframework.integration.smb.session.SmbSessionFactory;

@Configuration
@EnableIntegration
public class SmbPathConfig {

    @Bean
    SmbSessionFactory smbSessionFactory(
            @Value("${demo.smb.host}") String host,
            @Value("${demo.smb.port}") int port,
            @Value("${demo.smb.domain}") String domain,
            @Value("${demo.smb.username}") String username,
            @Value("${demo.smb.password}") String password,
            @Value("${demo.smb.share}") String share) {

        SmbSessionFactory factory = new SmbSessionFactory();
        factory.setHost(host);
        factory.setPort(port);
        factory.setDomain(domain);
        factory.setUsername(username);
        factory.setPassword(password);
        factory.setShareAndDir(share);
        factory.setSmbMinVersion(DialectVersion.SMB210);
        factory.setSmbMaxVersion(DialectVersion.SMB311);
        return factory;
    }

    @Bean
    IntegrationFlow smbInboundFlow(
            SmbSessionFactory factory,
            @Value("${demo.smb.inbound-dir}") String remoteDir,
            @Value("${demo.smb.local-inbound-dir}") String localDir) {

        return IntegrationFlow
                .from(Smb.inboundAdapter(factory)
                        .remoteDirectory(remoteDir)
                        .localDirectory(new File(localDir))
                        .autoCreateLocalDirectory(true)
                        .preserveTimestamp(true)
                        .regexFilter("(?i).*\\.csv$"),
                    endpoint -> endpoint
                        .id("smbInboundEndpoint")
                        .poller(Pollers.fixedDelay(10_000)
                            .maxMessagesPerPoll(5)))
                .handle(message -> {
                    File localFile = (File) message.getPayload();
                    System.out.println(
                        "Downloaded file locally: " + localFile.getAbsolutePath());
                })
                .get();
    }

    @Bean
    IntegrationFlow smbOutboundFlow(
            SmbSessionFactory factory,
            @Value("${demo.smb.outbound-dir}") String remoteDir) {

        return IntegrationFlow.from("sendSmbFiles")
                .handle(Smb.outboundAdapter(factory, FileExistsMode.FAIL)
                        .remoteDirectory(remoteDir)
                        .autoCreateDirectory(true)
                        .fileNameExpression("payload.name")
                        .useTemporaryFileName(true))
                .get();
    }
}
```

Both flows use **the same share** and authenticate via the same `SmbSessionFactory`. In production, you can wrap the factory in `CachingSessionFactory` and inject the wrapper into both flows to reuse sessions; whether caching is used or not does not alter path mapping.

### 4.3. Interpreting Each Path in Code

| Setting | Where? | Result |
|---|---|---|
| `factory.setHost("fs01.corp.example")` | Session factory | Connects to the SMB server |
| `factory.setShareAndDir("exchange")` | Session factory | Selects the root share |
| `.remoteDirectory("incoming/partner-a")` | Inbound adapter | Lists/downloads from the remote directory |
| `.localDirectory(new File("./data/smb-inbox/partner-a"))` | Inbound adapter | Stores synced files on the application host |
| `.autoCreateLocalDirectory(true)` | Inbound adapter | Creates the **local** directory when needed |
| `.remoteDirectory("outgoing/partner-a")` | Outbound adapter | Writes files to the target directory **on the share** |
| `.autoCreateDirectory(true)` | Outbound adapter | Creates the **remote** directory if missing and account has permissions |
| `.fileNameExpression("payload.name")` | Outbound adapter | Keeps the filename from the local `File` payload when uploading to the share |

**Do not confuse the two auto-create flags**: `autoCreateLocalDirectory(true)` creates a directory on the application's local disk; outbound's `autoCreateDirectory(true)` creates a directory on the Windows share. If remote writers lack directory-creation permissions, ask administrators to pre-create directories rather than granting broad privileges unconditionally.

### 4.4. Calling Outbound from a Java Service

In an application with `@IntegrationComponentScan`, define:

```java
import java.io.File;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface SmbFileSender {

    @Gateway(requestChannel = "sendSmbFiles")
    void upload(File localFile);
}
```

Enable scanning for this interface, for example by placing `@IntegrationComponentScan` on an appropriate `@Configuration` class. The service creates a complete ACK file before calling:

```java
File ack = new File("./data/smb-outbox/partner-a/orders-20261123.ack");
if (!ack.isFile() || !ack.canRead()) {
    throw new IllegalStateException("Local ACK file is not ready: " + ack);
}
smbFileSender.upload(ack);
```

With the configuration above, the expected remote destination is:

```text
\\fs01.corp.example\exchange\outgoing\partner-a\orders-20261123.ack
```

Calling `upload(...)` does not confirm the partner has processed the ACK. It only triggers **writing the file to the share**; a separate business confirmation flow is needed to know the receiver read it.

## 5. Two Access Models: SMB Client vs. OS-Mounted Share

This is the single most common source of confusion in cross-platform projects.

### 5.1. Spring Integration SMB Is an SMB Client

When using `SmbSessionFactory`, the Java client opens an SMB session over the network. Host, share, and remote paths live inside Spring Integration configuration without requiring the share to be mounted as a `Z:` drive on the application host.

```text
Java process (Linux/Windows)
   -> SmbSessionFactory(host/share/credentials)
      -> SMB server (TCP 445)
         -> incoming/partner-a/orders.csv
```

On Linux, the local directory might be `/var/lib/myapp/smb-inbox`, while the remote directory remains on the Windows File Server. On Windows, the local directory might be `C:/apps/myapp/data/smb-inbox`.

### 5.2. OS Mount Is a Different Approach

Windows can map `\\fs01\exchange` to `Z:`; Linux can mount SMB/CIFS at `/mnt/exchange`. With this approach, the program reads files through the **operating system's filesystem**, such as Java NIO `Files.list(...)` on the mount path.

That is a different deployment model. Mounts must be managed at the host/container level and depend on login context, permissions, and mount persistence. Spring Integration's SMB adapter **does not require a mount** and should never be configured with `remoteDirectory("Z:/incoming")` simply because a developer mapped `Z:` on their workstation.

| Criterion | Spring Integration SMB Client | OS Mount + Java Filesystem |
|---|---|---|
| Server address | Host/share via `SmbSessionFactory` | OS-managed mount point / network drive |
| Credentials | Session/client config | OS/mount credentials and process permissions |
| Application paths | Remote path relative to share; separate local path | Path on the mounted filesystem |
| Running in containers | No Windows drive mapping needed; needs SMB network reachability | Requires mount provisioned to the container/host |
| Message flow | SMB-specific inbound/outbound/gateway | Typically file adapter or Java NIO |
| Lifecycle | App-managed sessions/cache | OS- or platform-managed mount/reconnect |

A `Z:` drive mapped in an employee's interactive desktop session is normally **absent in a Windows Service session** or application container. Do not try to fix errors by copying a drive letter from a developer's machine onto a production server.

## 6. Mapping a Remote Directory to a Local Directory

With a **local-sync** inbound adapter, the result is a file on the application's disk. The emitted message payload is typically `java.io.File`.

```mermaid
sequenceDiagram
    participant S as SMB server
    participant P as Poller
    participant A as Inbound adapter
    participant L as Local disk
    participant H as Business handler
    P->>A: Poll every 10 seconds
    A->>S: List incoming/partner-a/*.csv
    S-->>A: orders-20261123.csv
    A->>S: Read file
    A->>L: Write ./data/smb-inbox/partner-a/orders-20261123.csv
    A-->>H: Message<File> pointing to local file
    H->>L: Read and process CSV
```

Key things to remember:

1. `remoteDirectory` controls **where to read on the share**.
2. `localDirectory` controls **where to store on the application host**.
3. The filename can stay unchanged or be renamed via local filename configuration. If renamed, preserve source metadata for reconciliation.
4. The handler receives a local file; do not mistake `File.getAbsolutePath()` for a UNC path.
5. Finishing the download does not mean business parsing and data commit have finished.

### 6.1. Using a Different Filename Locally

Spring Integration's SMB inbound DSL lets you configure a local filename strategy. Conceptual example:

```java
.localFilename(name -> "partner-a_" + name)
```

For remote `orders-20261123.csv`, the local file becomes `partner-a_orders-20261123.csv`. Check the exact API of your Spring Integration version and local filters: renaming does not automatically create an idempotency key for the file content.

When renaming, avoid using names derived directly from untrusted data containing `/`, `\`, or `..`. Ensure the target name is purely a **filename** and cannot escape the permitted storage area.

### 6.2. Multiple Remote Directories with Identical Filenames

Suppose:

```text
Remote A: incoming/partner-a/report.csv
Remote B: incoming/partner-b/report.csv
```

If both sources sync into the same local directory as `report.csv`, the two files can collide or be treated as identical by the local filter. Three controllable solutions exist:

- Give each partner its own local directory: `./data/smb-inbox/partner-a` and `./data/smb-inbox/partner-b`.
- Prefix local filenames with a normalized partner and/or batch ID.
- If preserving subdirectory trees is required, configure and verify the corresponding recursion/local-mapping mechanism; do not assume a single-directory inbound adapter automatically mirrors the remote tree.

In this lesson, choosing **one directory per partner** aids traceability and prevents filename collisions.

## 7. Paths in the SMB Outbound Gateway

The SMB outbound gateway lets you execute request/reply commands: `ls`, `nlst`, `get`, `mget`, `rm`, `mv`, `put`, and `mput`. The gateway's `expression` normally evaluates to a **remote relative path**, not a full UNC path.

Java DSL example:

```java
@Bean
IntegrationFlow smbListIncomingFlow(SmbSessionFactory factory) {
    return IntegrationFlow.from("listSmbDirectory")
            .handle(Smb.outboundGateway(factory, "ls", "payload")
                    .options("-1"))
            .get();
}
```

Sending a message with payload `"incoming/partner-a"` to `listSmbDirectory` causes the gateway to list:

```text
\\fs01.corp.example\exchange\incoming\partner-a
```

The reply of `ls -1` is a list of filenames `List<String>`. Using default `ls` without `-1`, the payload is a list of `FileInfo`; with `-R`, names in the reply may include relative paths under the selected directory.

| Command | Request Path | Operation Scope |
|---|---|---|
| `ls` | `incoming/partner-a` | Lists a remote directory |
| `get` | `incoming/partner-a/report.csv` | Downloads one remote file to local |
| `mget` | `incoming/partner-a/*` | Fetches multiple files matching pattern |
| `put` | Payload is local `File`; target dir configured separately | Uploads file to remote directory |
| `mv` | Source `incoming/partner-a/report.csv`, target `archive/partner-a/report.csv` | Renames/moves file within permitted scope |
| `rm` | `archive/partner-a/report.csv` | Deletes a specific file |

**For `put/mput`**, `expression` does not determine the remote path the way it does for other commands—it evaluates the payload being sent. Target directory comes from `remoteDirectory`/`remoteDirectoryExpression`, and filename comes from the name generator/expression.

### 7.1. `get` and `mget`: Local Mapping

`get`/`mget` accept `localDirectory`. When downloading multiple files from subdirectories, you can use a **local directory expression** referencing `#remoteDirectory` and a **local filename expression** referencing `#remoteFileName`.

Mapping concept:

```text
remote: incoming/partner-a/2026/11/report.csv
local:  /data/import/partner-a/2026/11/report.csv
```

However, sanitize and constrain the relative portion before building a local path. `#remoteDirectory` should never be concatenated directly onto a base directory if input could contain `..`, absolute paths, or segments outside the partner's scope.

Spring Integration documentation notes that `local-directory-expression` and static `local-directory` are **mutually exclusive**. Pick one way to determine the local directory per gateway. When preserving a directory tree is not required, a static local directory with controlled unique filenames is usually simpler.

### 7.2. `mv`: Source and Target Paths Are Two Separate Values

With `mv`, the request expression supplies the source path; `rename-expression` supplies the target path. Example:

```java
@Bean
IntegrationFlow smbArchiveFlow(SmbSessionFactory factory) {
    return IntegrationFlow.from("archiveSmbFile")
            .handle(Smb.outboundGateway(factory, "mv", "payload")
                    .renameExpression("headers['file_renameTo']"))
            .get();
}
```

Request:

```text
payload:              incoming/partner-a/orders-20261123.csv
file_renameTo header: archive/partner-a/orders-20261123.csv
```

This is a **server-side** operation; it does not move `./data/smb-inbox/...` locally. After moving, the old remote path may no longer exist. If import committed yet `mv` failed, reconcile state before retrying to avoid re-importing the same data.

## 8. Per-Partner Mapping Without Opening Wrong Directories

A multi-partner system may share a root share:

```text
exchange/
  incoming/
    partner-a/
    partner-b/
  outgoing/
    partner-a/
    partner-b/
  archive/
    partner-a/
    partner-b/
```

Do not take an external `partnerId` directly and concatenate it:

```java
// Do not use unvalidated input to select a remote directory.
String unsafe = "outgoing/" + request.getPartnerId();
```

If `partnerId` contains `../` or an unauthorized value, the remote path can point outside the intended business boundary. Instead, map from an **authenticated partner code** to an allowlist of paths:

```java
import java.util.Map;

final class PartnerSmbPaths {

    private static final Map<String, String> OUTBOUND_DIRS = Map.of(
        "PARTNER_A", "outgoing/partner-a",
        "PARTNER_B", "outgoing/partner-b"
    );

    static String outboundDirFor(String authorizedPartnerCode) {
        String dir = OUTBOUND_DIRS.get(authorizedPartnerCode);
        if (dir == null) {
            throw new IllegalArgumentException(
                "Partner is not authorized for an SMB path");
        }
        return dir;
    }
}
```

When multiple target directories are needed, choose one of two designs:

1. **A dedicated outbound flow per partner/target** with static `remoteDirectory(...)`. Well suited when target count is small and clear permissions/handling are desired.
2. **A single flow using a remote directory expression**, where the header holding the path is populated by the application from a server-side allowlist (such as `PartnerSmbPaths`), never raw paths from public requests. Audit the message's journey through handlers/transformers so no other header can overwrite it.

Partners with distinct access boundaries should use separate factories/credentials or isolated shares/ACLs. Syntactically safe path strings never replace server-side permission enforcement.

### 8.1. Preventing Path Traversal and Invalid Filenames

A sound policy:

- Reject absolute paths, UNC paths, or `smb://` URIs from external inputs where only a **relative path** is allowed.
- Reject `..` segments upon normalization and anything escaping the granted prefix.
- Accept only filenames generated from batch IDs or validated metadata; forbid `/` or `\` in filenames.
- Check forbidden Windows characters such as `< > : " / \ | ? *`, server-reserved names, and length/character limits.
- When creating local files, normalize and verify the target path sits **underneath the allowed root directory**.
- For file servers with symbolic links, DFS, or redirection features, verify server/client path-handling policies as well, rather than relying purely on string checks.

Java NIO example validating a **local path** after mapping:

```java
import java.nio.file.Path;

Path localRoot = Path.of("./data/smb-inbox").toAbsolutePath().normalize();
String trustedRelativePath = "partner-a/orders-20261123.csv";
Path target = localRoot.resolve(trustedRelativePath).normalize();

if (!target.startsWith(localRoot)) {
    throw new IllegalArgumentException("Path escapes local root");
}
```

This check only validates path syntax; if you also need symlink protection or protection against concurrent local filesystem mutations, combine it with OS permissions and safe file operations. Do not copy local-path normalization verbatim onto SMB remote paths assuming identical semantics.

## 9. Notes on Filenames, Encoding, Separators, and Compatibility

### 9.1. Name Collisions and Case Sensitivity

Windows File Servers are typically case-insensitive while preserving case. Samba/NAS servers may be configured differently. Never assume `Report.csv` and `report.csv` are always two distinct files or always the same file across every server.

If using regex or patterns:

```java
.regexFilter("(?i).*\\.csv$")
```

then `(?i)` accepts both `CSV` and `csv` during filtering, but **does not alter** the file server's name-matching rules. Agree on a stable naming convention with partners.

### 9.2. Spaces, Vietnamese/Unicode, and Special Characters

Filenames containing spaces or Unicode can be valid, yet URL encoding, CSV exporting, message header handling, database storage, and cross-system transfers must agree on one convention. Test cases like:

```text
incoming/partner-a/Báo cáo tháng 11.csv
incoming/partner-a/report final.csv
```

Never concatenate credentials and paths into `smb://user:password@host/share/...`; `@`, `:`, or international characters can cause encoding bugs while exposing secrets.

### 9.3. Long UNCs and DFS

A UNC path may point to a DFS namespace, such as `\\corp.example\dfs\exchange\incoming`. Do not assume SMB clients, permissions, and failover policies for DFS behave identically to direct file shares; test against your actual SMB library version and infrastructure. When using DNS aliases or multi-node file servers, coordinate with administrators to confirm targets and permissions.

### 9.4. Local Paths Inside Containers

Inside a container:

```text
Application sees:   /app/data/smb-inbox
Container host:     /srv/myapp-data/smb-inbox   (if bind-mounted)
Windows share:      \\fs01.corp.example\exchange\incoming
```

These three paths belong to **three distinct layers**. `localDirectory(new File("/app/data/smb-inbox"))` must exist or be creatable inside the container's filesystem. If data must survive pod/container deletion, mount an appropriate volume/persistent storage; you cannot rely on the SMB session factory to persist local files.

## 10. Troubleshooting Path Mapping Errors

| Symptom | Likely Cause | Diagnostic Step |
|---|---|---|
| Connection timeout even with valid path | DNS, TCP 445, network, SMB dialect | Test from the exact host/container running the app |
| Access denied on `incoming/partner-a` | Share permission or directory ACL | Verify account and compare read/list rights on path |
| Can list share, yet cannot see files | Wrong remote directory or filter | Run `ls -1` on a known path; cross-check UNC path |
| File ends up in `exchange/exchange/incoming` | Share name repeated in remote path | Check `setShareAndDir` and `remoteDirectory` |
| Inbound file downloaded, yet missing on developer's machine | Local directory is inside the container/server | Check actual local path from safe logs and volume mounts |
| Remote directory creation error | `autoCreateDirectory` lacks permissions | Check ACLs; pre-create remote dirs or grant needed rights |
| Local directory creation error | Process lacks write permission or disk full | Check OS permissions, volumes, and disk space |
| Partner A's file overwritten by Partner B | Same filename and shared local directory | Separate local roots or prefix filenames by partner/batch |
| `get` fails when local file already exists | `FileExistsMode.FAIL` | Choose explicit local existence/retry policy |
| `put` succeeds, yet partner does not see file | Sent to wrong `remoteDirectory` or temp file stuck | Check actual share/dir, temporary naming, rename, and permissions |
| `mv` reports file not found | Wrong source path or file already archived | Check both source and target paths before retrying |
| Fails only when running as a Windows Service | Relies on `Z:` mapped in a user session | Use direct SMB client or mount under the service identity |
| Filename characters mangled / cannot open | Encoding/URI/path conversion | Check special characters and client/server configuration |

When investigating, log **sanitized** values: host alias, share, remote relative path, local absolute path (if policy permits), filename, batch ID, and error category. Never log SMB URLs containing passwords or expose sensitive directories to unauthorized users.

### Quick Path-Debugging Checklist

1. Obtain the exact UNC path provided by the administrator (without credentials).
2. Break out host, share, relative directory, and filename on paper or in a config table.
3. Verify `SmbSessionFactory` has the exact host/share; ensure `remoteDirectory` **does not repeat UNC/share**.
4. Test `ls -1` on a test directory to confirm the path, then `get` a small file if permitted.
5. Verify `localDirectory` using the exact absolute path visible inside the running container/VM.
6. For outbound, send a test file, verify its location on the share including temp-file rename, and only then run real data batches.

## 11. Practicing with a Lab Shared Directory

Prepare a Windows File Server or Samba/NAS share named `exchange` with directories:

```text
exchange/
  incoming/
    partner-a/
    partner-b/
  outgoing/
    partner-a/
    partner-b/
  archive/
    partner-a/
```

Grant read permissions on `incoming` and required write/rename permissions on `outgoing` **in the lab only**. Configure host, share, username, and password via environment variables as in Section 4.

### Lab A — From UNC to Adapter Properties

Given the path:

```text
\\fs01.corp.example\exchange\incoming\partner-a\orders-007.csv
```

Task: write down `host`, `shareAndDir`, `remoteDirectory`, filename, and local directory if storing at `/app/data/inbound/partner-a`.

**Reference answer:** host `fs01.corp.example`, share `exchange`, `remoteDirectory = incoming/partner-a`, filename `orders-007.csv`, `localDirectory = /app/data/inbound/partner-a`. Expected local file: `/app/data/inbound/partner-a/orders-007.csv`.

### Lab B — Downloading a File and Inspecting the Payload

1. Place `orders-007.csv` in `incoming/partner-a` with content:

   ```csv
   order_id,amount,currency
   ORD-101,150000,VND
   ORD-102,85000,VND
   ```

2. Run the inbound flow with `SMB_INBOUND_DIR=incoming/partner-a` and `SMB_LOCAL_INBOUND_DIR=./data/smb-inbox/partner-a`.
3. Wait for a poll and observe the `File` path in the sample log.
4. Open the local file and verify exactly two data rows totaling `235000` VND.

**Result to explain:** the `File` payload points to the local copy, not a UNC path or `smb://` URI.

### Lab C — Distinguishing Remote and Local Directories

1. Change `SMB_LOCAL_INBOUND_DIR` to another local directory in the lab and restart the application.
2. Observe the downloaded file's new location **without** changing the source UNC address.
3. Restore it and change `SMB_INBOUND_DIR` from `incoming/partner-a` to `incoming/partner-b`.
4. Explain why changing one value changes **where files are saved**, while changing the other changes **where files are read on the server**.

**Result:** clearly distinguish the responsibilities of `localDirectory` and `remoteDirectory`.

### Lab D — Sending an ACK to the Right Directory

1. Create `./data/smb-outbox/partner-a/orders-007.ack` after processing the sample file.
2. Call `SmbFileSender.upload(...)`; verify the file appears in `outgoing/partner-a`.
3. Inspect the temporary filename if observable during transfer, and read the official filename only after rename finishes.
4. Test misconfiguring `outgoing/partner-b` **in the lab**, spot the mismatch, and fix it before running real data.

**Result:** map a local source file to a remote destination path matching the intended share and directory.

### Lab E — Two Partners Sending the Same Filename

1. Create `incoming/partner-a/report.csv` and `incoming/partner-b/report.csv` with different contents.
2. In the lab, examine a design pointing both into the same local directory and observe collision/filter risks.
3. Reconfigure so each partner has its own local directory.
4. Verify the two files do not overwrite each other and preserve source-identifying metadata.

**Result:** see the value of an explicit mapping table and per-partner/batch identifiers.

### Lab F — Testing Path and Permission Errors

1. Use outbound gateway `ls -1` to list a valid directory.
2. Try a nonexistent directory like `incoming/no-such-partner` and compare against an empty result from a valid directory.
3. On the lab share, temporarily grant read-only access without write access on a folder, try uploading a file, and observe `Access Denied`.
4. Compare the three error categories: **path does not exist**, **permission denied**, and **cannot connect**.
5. Restore permissions, delete lab-created test files, and document the proper configuration rules.

**Result:** use read-only commands to verify paths before running data-mutating operations.

### Self-Check Questions

1. In `\\srv\share\a\b.csv`, is `a` the share or a remote directory?
2. When `setShareAndDir("share")` is already set, should you configure `remoteDirectory("share/a")`? Why or why not?
3. If the application runs on Linux, must you mount `\\srv\share` as a `Z:` drive to use the SMB adapter?
4. What is the difference between `autoCreateLocalDirectory` and `autoCreateDirectory`?
5. Why can `partner-a/report.csv` and `partner-b/report.csv` collide locally?
6. Does `mv` via the outbound gateway move a file on SMB or move the downloaded local `File`?
7. Why doesn't normalizing a path replace allowlists and ACLs?

## 12. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| A full UNC path goes into `remoteDirectory` | The factory configures host/share; endpoints take remote paths relative to that root |
| `setShareAndDir` only takes a subdirectory name | It represents the share and may include a base path; design a consistent root |
| `localDirectory` is on the SMB server | It is the application's local directory when inbound syncs locally |
| The SMB client requires a `Z:` drive | Spring Integration SMB connects directly to the share; no mapped drive is needed |
| A Windows service sees every user's mapped drives | Mapped drives belong to interactive login sessions/contexts |
| `\` always works in every config | UNC uses backslashes, but Java/YAML/remote paths have different escaping rules |
| Inbound adapter preserves the entire remote folder tree automatically | Mapping/recursion must be configured and tested; a single local directory can flatten paths |
| Sending a file to a share means writing to `localDirectory` | Outbound writes to a remote directory; the source `File` is usually local |
| Same filename means same file | Two remote directories/partners can use identical filenames |
| `ls` returning empty proves credentials are bad | The directory may simply be valid and contain no matching files |
| Checking path strings alone is sufficient security | Must combine allowlists/authorization, canonical paths, ACLs, and symlink governance |
| Successful file download means business import succeeded | Download and business data commit are two independent milestones |

## 13. References

- [Spring Integration Reference 6.5 — SMB Support](https://docs.spring.io/spring-integration/reference/6.5/smb.html): factory config, inbound/outbound adapters, gateways, and Java DSL.
- [Spring Integration 6.5 API — SmbConfig](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/smb/session/SmbConfig.html): `setHost`, `setShareAndDir`, SMB URI syntax, and configuration properties.
- [Spring Integration 6.5 API — SmbSessionFactory](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/smb/session/SmbSessionFactory.html): session factory bound to an SMB share.
- [Spring Integration Reference — Remote File Support](https://docs.spring.io/spring-integration/reference/ftp.html): shared concepts for remote files, paths, and filters; verify SMB-specific capabilities.

**Key takeaway:** a UNC path has the structure **host → share → remote directory → filename**. When using Spring Integration SMB, map those parts consistently across `SmbSessionFactory` and endpoints while managing `localDirectory` as the application's own storage area. Path correctness, least-privilege permissions, and metadata preservation form the foundation for safe file handling across inbound/outbound adapters and gateways.
