# SFTP Inbound Adapter with SSH Keys

## 1. Problem Statement and Objectives

Suppose a partner places a file named `orders-2026-11-23.csv` into the `/exchange/orders` directory on an SFTP server. Your Spring Boot application needs to periodically detect new files, download them to a local directory, and pass them to an order-import service. The partner does not provide an account password; the system must **authenticate using an SSH key pair** while verifying the server's identity before transferring data.

That is the problem solved by the **SFTP inbound channel adapter** in Spring Integration: an inbound component that connects to an external system, synchronizes files from SFTP to the local machine, and produces `Message<File>` for downstream processing steps. It combines a `SessionFactory`, file filters, a `poller`, and a `MessageChannel`/handler in an integration flow. Do not confuse inbound adapters (receiving files), outbound adapters (sending files), and outbound gateways (performing operations on demand).

After this lesson, you will be able to:

- Distinguish between the **application's private key**, the **authorized public key on the server**, and the **server's host key**.
- Configure `DefaultSftpSessionFactory` with a private key, passphrase, and `known_hosts`.
- Create a Java DSL flow using an SFTP inbound adapter, a poller, and file filters.
- Explain the file download lifecycle, poll executions, duplicate-processing prevention, and the limits of the retry mechanism.
- Propose safe operational practices for large files, multiple instances, or interrupted connections.

> **Version scope:** Examples use APIs from **Spring Integration 6.x and later** (SFTP client based on Apache MINA SSHD). In Spring Integration 5.x, several SFTP classes/types are based on JSch and differ from these examples. Let the Spring Boot BOM manage library versions compatible with your project.

## 2. Architecture: From SFTP to MessageChannel

```mermaid
flowchart LR
    A["Partner exports file"] --> B["SFTP: /exchange/orders"]
    B --> C["SSH session: private key + known_hosts"]
    C --> D["Remote filter and SFTP synchronizer"]
    D --> E["Local staging: .writing → .csv"]
    E --> F["Local filter and Message<File>"]
    F --> G["Spring Integration handler"]
    G --> H["DB import / idempotency / error handling"]
```

The actual flow runs as follows:

1. **Poller** triggers the adapter periodically, for example every 10 seconds. SFTP inbound does not receive push events from the server; it actively polls the remote directory.
2. **Session factory** opens/retrieves an SFTP session over SSH. The client proves access rights with its private key; the client also verifies the server's host key against `known_hosts`.
3. **Remote filter** decides which files are eligible for download (`.csv` extension, not previously seen, file finished writing, etc.). The synchronizer downloads matching files to the local disk.
4. A file being downloaded usually carries a temporary `.writing` suffix; once downloaded, it is renamed to its real name. **Local filter** prevents temporary files or files that already emitted a message from being picked up again unintentionally.
5. `FileReadingMessageSource` emits a `Message` with **a `java.io.File` payload on the application machine**. The handler reads/validates the content, persists results, and manages business errors.

Key point: **"download completed" is different from "business processing succeeded"**. The adapter does not automatically guarantee an end-to-end transaction from the SFTP server to the database. This dictates how retry and idempotency must be designed.

## 3. SSH Keys: Who Authenticates Whom?

| Component | Location | Purpose |
| --- | --- | --- |
| Client **private key** | Application, secret mount, or secret manager | Proves the identity of the SFTP account; must be kept secret |
| Client **public key** | Account's `authorized_keys` on the SFTP server | Tells the server which keys are allowed to log in |
| Server **host key** | SFTP server | Proves the server being connected to is a trusted machine |
| **`known_hosts`** file | Application side | Stores verified host public keys to detect spoofed servers or changed keys |
| **Passphrase** | Application secret, if the private key is encrypted | Unlocks the private key; not the SFTP login password |

Illustrative key provisioning workflow (Linux/macOS; on Windows you can use OpenSSH):

```bash
# Run in a secure key-management environment; never commit keys to Git.
ssh-keygen -t ed25519 -a 100 -f ~/.ssh/sftp_orders -C "orders-import-client"

# Send only the public key to the SFTP administrator to add to authorized_keys.
cat ~/.ssh/sftp_orders.pub

# Inspect the public key fingerprint for verification during provisioning.
ssh-keygen -lf ~/.ssh/sftp_orders.pub
```

The SFTP administrator installs the **public key** onto the application's account. The application stores the **private key** in a secret volume, such as `/run/secrets/sftp_orders_key`, and grants read permission only to the process that needs it. On Linux, you can restrict file permissions with `chmod 600` on the private key. Never copy the private key into source code, container images, logs, or committed configuration.

For the host key, obtain the `known_hosts` entry from trusted infrastructure; if using `ssh-keyscan`, **you must verify the fingerprint through an independent channel** before trusting the output, because `ssh-keyscan` alone does not authenticate the server:

```bash
# Example of fetching the server's entry; verify the fingerprint with the administrator before using.
ssh-keyscan -p 22 -t ed25519 sftp.partner.example > sftp_known_hosts

# Test logging in with the same key and known_hosts (replace hostname/user for your real environment).
sftp -i ~/.ssh/sftp_orders \
  -o UserKnownHostsFile=./sftp_known_hosts \
  -P 22 orders_app@sftp.partner.example
```

**Do not enable `allowUnknownKeys=true` in production.** This property skips server identity verification and leaves the connection vulnerable to spoofing attacks. When the server rotates its host key, verify and update `known_hosts` through a managed key-rotation procedure.

## 4. Declaring Dependencies and Configuration

If you use Spring Boot with dependency version management, just add the SFTP module. Gradle example:

```groovy
dependencies {
    implementation 'org.springframework.integration:spring-integration-sftp'
}
```

Or Maven (when the Spring Boot BOM is imported):

```xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-sftp</artifactId>
</dependency>
```

Example `application.yml` using **environment placeholders**, without real keys or passphrases:

```yaml
app:
  sftp:
    host: ${SFTP_HOST:sftp.partner.example}
    port: ${SFTP_PORT:22}
    username: ${SFTP_USERNAME:orders_app}
    private-key: file:${SFTP_PRIVATE_KEY_FILE}
    private-key-passphrase: ${SFTP_PRIVATE_KEY_PASSPHRASE:}
    known-hosts: file:${SFTP_KNOWN_HOSTS_FILE}
    remote-directory: ${SFTP_REMOTE_DIRECTORY:/exchange/orders}
    local-directory: ${SFTP_LOCAL_DIRECTORY:./data/sftp-inbox}
```

`SFTP_PRIVATE_KEY_FILE` and `SFTP_KNOWN_HOSTS_FILE` must be paths **mounted at runtime**; both variables must be provided when running the application. If the key has no passphrase, `SFTP_PRIVATE_KEY_PASSPHRASE` can be left empty. The application needs **read** permission on the private key/`known_hosts` and **write** permission on the `local-directory` folder.

## 5. Configuring the SFTP Session with a Private Key

In Spring Integration 6.x+, the remote file type is `org.apache.sshd.sftp.client.SftpClient.DirEntry`. Create a dedicated session factory while setting a limit on the number of cached sessions:

```java
import org.apache.sshd.sftp.client.SftpClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.integration.file.remote.session.CachingSessionFactory;
import org.springframework.integration.file.remote.session.SessionFactory;
import org.springframework.integration.sftp.session.DefaultSftpSessionFactory;

@Configuration
public class SftpSessionConfig {

    @Bean
    public SessionFactory<SftpClient.DirEntry> sftpSessionFactory(
            @Value("${app.sftp.host}") String host,
            @Value("${app.sftp.port}") int port,
            @Value("${app.sftp.username}") String username,
            @Value("${app.sftp.private-key}") Resource privateKey,
            @Value("${app.sftp.private-key-passphrase:}") String passphrase,
            @Value("${app.sftp.known-hosts}") Resource knownHosts) {

        DefaultSftpSessionFactory delegate = new DefaultSftpSessionFactory(false);
        delegate.setHost(host);
        delegate.setPort(port);
        delegate.setUser(username);
        delegate.setPrivateKey(privateKey);
        if (!passphrase.isBlank()) {
            delegate.setPrivateKeyPassphrase(passphrase);
        }
        delegate.setKnownHostsResource(knownHosts);
        delegate.setAllowUnknownKeys(false);
        delegate.setTimeout(30_000);

        // Limit the number of sessions held in the pool; tune according to actual load.
        return new CachingSessionFactory<>(delegate, 4);
    }
}
```

Explanation of the options with direct impact:

| Setting | Meaning |
| --- | --- |
| `setPrivateKey(Resource)` | Loads the private key for SSH authentication instead of configuring an account password |
| `setPrivateKeyPassphrase(...)` | Set only when the private key is encrypted with a passphrase |
| `setKnownHostsResource(...)` and `setAllowUnknownKeys(false)` | Verifies the SFTP server's host key against the trusted list |
| `setTimeout(30_000)` | Sets a reasonable connection/I/O timeout; duration is in milliseconds |
| `DefaultSftpSessionFactory(false)` | By default uses a dedicated SSH connection per session/channel; avoids assuming a shared connection |
| `CachingSessionFactory<>(delegate, 4)` | Reuses sessions within a bounded pool; sessions are not cached automatically when using only the underlying factory |

When you need a mode that shares a single SSH connection across multiple channels (`new DefaultSftpSessionFactory(true)`), you must clearly understand the connection lifecycle and **combine it with a caching session factory**. The `false` configuration above is usually simpler to start with. For long-lived idle connections, consider `CachingSessionFactory#setTestSession(true)` and monitor pool limits.

## 6. Creating an Inbound Integration Flow with Java DSL

Suppose we only accept CSV files. The flow below limits each fetch cycle to at most **5 files**, while emitting at most **5 messages/poll**. The handler prints the filename for demonstration; in a real application, replace it with a service that validates and imports the data.

```java
import java.io.File;

import org.apache.sshd.sftp.client.SftpClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.remote.session.SessionFactory;
import org.springframework.integration.sftp.dsl.Sftp;

@Configuration
public class SftpInboundFlowConfig {

    @Bean
    public IntegrationFlow sftpInboundFlow(
            SessionFactory<SftpClient.DirEntry> sftpSessionFactory,
            @Value("${app.sftp.remote-directory}") String remoteDirectory,
            @Value("${app.sftp.local-directory}") String localDirectory) {

        return IntegrationFlow
                .from(Sftp.inboundAdapter(sftpSessionFactory)
                                .remoteDirectory(remoteDirectory)
                                .regexFilter(".*\\.csv$")
                                .localDirectory(new File(localDirectory))
                                .autoCreateLocalDirectory(true)
                                .preserveTimestamp(true)
                                .deleteRemoteFiles(false)
                                .maxFetchSize(5),
                        endpoint -> endpoint.id("sftpCsvInbound")
                                .poller(Pollers.fixedDelay(10_000)
                                        .maxMessagesPerPoll(5)))
                .handle(message -> {
                    File localFile = (File) message.getPayload();
                    // Demo: replace with a CSV import service with validation and idempotency.
                    System.out.println("Received file: " + localFile.getAbsolutePath());
                })
                .get();
    }
}
```

In the example, `IntegrationFlow.from(...)` creates the inbound endpoint that reads files from SFTP; `.handle(...)` is the terminal consumer. When you need to process through a dedicated `MessageChannel`, you can add `.channel("sftpFilesChannel")` and register a handler receiving from that channel. The `poller` can use fixed delay, fixed rate, or dynamic configuration depending on server speed and consumption needs.

Parameters to understand:

| Option | Effect and Notes |
| --- | --- |
| `remoteDirectory(...)` | Source directory on the server; the account must have list/read permissions |
| `regexFilter(".*\\.csv$")` | Filters remote filenames by regex. For wildcards, you can use `patternFilter("*.csv")` |
| `localDirectory(...)` | Local staging directory; this is where the `File` payload points |
| `autoCreateLocalDirectory(true)` | Creates the local directory when missing, if the process has permission |
| `preserveTimestamp(true)` | Preserves the server's file modification timestamp; helps certain timestamp-based filter policies |
| `deleteRemoteFiles(false)` | Keeps the file on the server after download. If set to `true`, the file can be deleted **after transfer**, before business processing succeeds |
| `maxFetchSize(5)` | Maximum number of files fetched from the server in one fetch pass; `-1` means unlimited |
| `maxMessagesPerPoll(5)` | Maximum number of messages emitted per poll; distinct from the number of downloaded files |
| `temporaryFileSuffix(".writing")` | Defaults to the `.writing` suffix while downloading to avoid emitting incomplete files |

**Distinguish fetch limits from emit limits:** if `maxFetchSize=4` while `maxMessagesPerPoll=2`, the adapter may download four files in one fetch pass, emit two messages in the current poll, and emit the remaining local files in a subsequent poll. Therefore, choose both values based on file size, processing throughput, and disk capacity.

### Two Types of Filters Solve Two Problems

- **Remote filter** operates on files on SFTP, before downloading. It can filter by name, modification time, or already-downloaded metadata.
- **Local filter** operates on files already in `localDirectory`, before emitting a message to the handler. It prevents duplicate emission of local files and ignores `.writing` files.

By default, Spring Integration provides accept-once/persistent style filters, but the default metadata is stored **in memory**. The name "persistent" describes the algorithm that uses `MetadataStore`; durability across restarts depends on **the type of store** configured. In multi-instance deployments, you should use a shared `ConcurrentMetadataStore` (such as `RedisMetadataStore`) along with an appropriate locking/idempotency strategy. When replacing the filter with a custom filter, explicitly combine both the filename condition and the previously-fetched condition to avoid accidentally dropping either one.

Example of combining **remote** conditions when a shared persistent `ConcurrentMetadataStore` is already available:

```java
import org.apache.sshd.sftp.client.SftpClient;
import org.springframework.integration.file.filters.CompositeFileListFilter;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.sftp.filters.SftpPersistentAcceptOnceFileListFilter;
import org.springframework.integration.sftp.filters.SftpRegexPatternFileListFilter;

CompositeFileListFilter<SftpClient.DirEntry> remoteFilter =
        new CompositeFileListFilter<SftpClient.DirEntry>()
                .addFilter(new SftpRegexPatternFileListFilter(".*\\.csv$"))
                .addFilter(new SftpPersistentAcceptOnceFileListFilter(
                        metadataStore, "orders-sftp-"));

// Use .filter(remoteFilter) on Sftp.inboundAdapter(...) instead of .regexFilter(...).
// metadataStore is a configured ConcurrentMetadataStore bean, such as Redis.
```

For production systems, align the local filter policy and business idempotency key as well. File-filtering metadata **does not replace** data-persistence transactions: a file that was emitted but failed in the handler may not be automatically re-emitted, and a successfully processed file may reappear if filter state changes.

## 7. Preventing Reception of Partially Written Files

An SFTP server can make a file visible as soon as the partner begins uploading it. If the adapter downloads too early, the CSV file may be missing rows or a header/trailer. The `.writing` suffix only protects **while your application is downloading to local disk**; it does not prove that **the file on the server has finished uploading**.

Three ways to coordinate with the partner:

1. **Upload to a temporary name then rename on the server**: the partner writes `orders.csv.part` and renames it to `orders.csv` upon completion; the adapter only selects `*.csv`. This is usually the easiest contract to control when the server supports proper atomic rename.
2. **Marker file**: the partner only creates `orders.csv.done` once the data file is complete; use `SftpSystemMarkerFilePresentFileListFilter` or an equivalent rule to accept only files with a marker.
3. **File age**: if you cannot control the sender, consider `SftpLastModifiedFileListFilter` (Spring Integration 6.2+) to only pick up files whose modification time is old enough. Understand that file age is only a heuristic, weaker than a rename/marker protocol.

You should also agree on encoding (UTF-8), CSV format, delimiter, timezone in filenames, checksum if needed, and how a completed batch is signaled. This is the **message contract at the file boundary**, even though the transport mechanism is SFTP.

## 8. Error Handling, Retry, and Data Guarantees

Divide errors into two stages instead of assuming everything is automatically retried by the adapter:

| Stage | Error Examples | Behavior / Handling Guidance |
| --- | --- | --- |
| Connection and authentication | Host unreachable, host key mismatch, wrong private key, out of sessions | The poll will fail; detect via logs/metrics, fix the root cause, and use timeouts and controlled retry/backoff |
| Listing and downloading files | Permission denied, SFTP disconnect mid-download, insufficient local disk space | The synchronizer can roll back remote filter state for failed downloads if the filter supports `ReversibleFileListFilter`; the file can be retried on a later poll |
| Processing after `File` payload | Corrupted CSV, DB error, validation failure | **Does not automatically roll back remote/local filters** just because the handler throws an exception; requires business retry/recovery mechanisms |
| Multiple processes/instances | Two nodes see the same file, restart loses metadata | Use an appropriate shared metadata store, fetch limits, and DB-level idempotency |

Example of a safely replayable import workflow:

1. Record the file using a durable business key, such as `(partner_id, batch_id)` or a checksum agreed upon with the partner. Create a unique constraint in the DB.
2. Validate filename, format, row count, and checksum before performing business updates.
3. Mark the batch **COMPLETED** only in the same transaction that writes the data (or an equivalent durable state design). If already completed, a retry must become a controlled no-op.
4. For transient errors, record a retry state and schedule a job to re-read the local copy or re-download according to your designed mechanism. For data errors, move the file to quarantine and notify the sender.
5. Only after processing and persistence succeed should you consider archiving/deleting the file per your retention agreement. **`deleteRemoteFiles(true)` is not a confirmation that the business transaction committed**.

In high-reliability systems, consider a pipeline of local staging → validation → transactional import → archive or quarantine; attach a correlation ID (filename/batch ID) to logs. If you delete a local file to trigger reprocessing, understand and reset the **local filter** appropriately; if remote metadata still says the file was received, deleting only the local file will likely not re-download it from SFTP.

## 9. Operations and Security

**Resources and throughput.** Estimate local disk usage from maximum file size, number of files per fetch, and how long handlers hold files. For large files, lower `maxFetchSize` (1–5 is a common starting point), monitor disk pressure, and do not poll faster than processing capacity. When multiple nodes read from one source, use a shared metadata store and consider lowering `maxFetchSize` to keep one node from grabbing most of the files.

**Connections.** Bound `CachingSessionFactory`, configure timeouts, and monitor active session counts; avoid unbounded session creation. After rotating a key passphrase, rotating a host key, or prolonged connection failures, verify how to reset/refresh the cache. Never log private keys, passphrases, or full sensitive file contents.

**Monitoring.** Track poll counts, files discovered/downloaded/processed, latency from partner export to import completion, files in staging, disk usage, SSH errors, CSV read errors, backlog, and retry counts. Set alerts if no file arrives past an SLA window when one is expected; you cannot infer that "no files" is always an error outside a delivery schedule.

**Secret management.** A secret manager or controlled volume is much better than keeping private keys in `resources/`. Apply least privilege to the SFTP account: only list/read the required inbox area, avoiding delete permissions unless required. Document procedures for rotating client keys, changing host keys, and verifying fingerprints through an independent channel.

## 10. End-to-End Verification Lab

**Prerequisites:** have a test SFTP server, an account with the public key attached, a verified `known_hosts` file, and an application that can read both secret config files and write to `local-directory`. Set `remote-directory=/exchange/orders` or a path matching your server.

**Scenario:**

1. Use `sftp -i ...` to test logging in and running `ls` on the remote directory. This separates SSH/SFTP issues from Spring Integration issues.
2. Upload `orders-001.csv.part` containing valid data. Run the application and confirm the `.part` file is **not** picked up.
3. Rename the file to `orders-001.csv` on the server. Wait one poll cycle: expect one complete file in local staging and one handler invocation receiving the `File` payload.
4. Leave the name and timestamp unchanged and wait for additional polls: no duplicate messages should be emitted within the same runtime under default filters.
5. Simulate a brief disconnect, break directory read permissions, use a mismatched private key, and change the host key in a test environment: confirm useful error logs appear and the adapter does not silently skip host-key verification.
6. Have the handler throw an exception **after a successful download**: check how the application records the failure and recovers; do not assume the adapter will automatically re-emit the file.
7. Restart the application and, if running multiple instances, test the same file across two nodes to verify **persistent metadata and business idempotency** per your design.

| Symptom | Where to Check First |
| --- | --- |
| `Auth fail` or `Permission denied` on login | Username, public key in `authorized_keys`, private key, passphrase, file permissions |
| `UnknownHostKey` or host key mismatch | `known_hosts` contents, host/port, official fingerprint, key-rotation event |
| Login succeeds but no files appear | `remoteDirectory`, list/read permissions, `*.csv` regex, rename timing, remote/local filter state |
| File transfer stalls or throws I/O error | Timeout, network, session cache, disk space, file still being written on server |
| File is re-processed after restart | In-memory metadata store, changed timestamp/name, non-durable idempotency mechanism |
| File downloaded but not imported | Handler, DB/validation errors, retry queue, local file state, filter not automatically rolled back on processing error |

## 11. Common Pitfalls

- **Setting `allowUnknownKeys(true)` to "fix" connection errors:** disables host verification; fix `known_hosts` after verifying the fingerprint instead.
- **Confusing the login public key with the server's host key:** `authorized_keys` and `known_hosts` sit on opposite sides and solve opposite directions of authentication.
- **Enabling `deleteRemoteFiles(true)` from the start:** files can vanish from the source before the handler finishes importing; deletion decisions must follow your recovery and retention contract.
- **Relying solely on filters for exactly-once delivery:** filter state does not span DB transactions, restarts, and timestamp changes; business logic still needs idempotency.
- **Filtering only for `.csv` and assuming the file is complete:** you need a rename, marker, or file-age agreement to avoid downloading files still being written.
- **Ignoring fetch limits:** a single poll can pull down many large files, filling the staging disk before handlers finish processing.

## 12. Self-Check Questions

1. Why are both `privateKey` **and** `knownHostsResource` needed, even though both belong to SSH?
2. What happens if `maxFetchSize=10` while `maxMessagesPerPoll=2`?
3. Why is `temporaryFileSuffix=.writing` not enough to avoid picking up a file the partner is still uploading?
4. If the DB import handler fails after the adapter has already downloaded the file, which component is responsible for replay? Why can you not rely solely on the remote filter?
5. With two instances running in parallel, which components do you need to reduce duplicate downloads and ensure a batch is never committed twice?

## References

- [Spring Integration – SFTP Session Factory](https://docs.spring.io/spring-integration/reference/sftp/session-factory.html)
- [Spring Integration – SFTP Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/sftp/inbound.html)
- [Spring Integration – SFTP Session Caching](https://docs.spring.io/spring-integration/reference/sftp/session-caching.html)
- [Spring Integration – Remote Persistent File List Filters](https://docs.spring.io/spring-integration/reference/file/remote-persistent-flf.html)
- [Spring Integration – Controlling Remote File Fetching](https://docs.spring.io/spring-integration/reference/sftp/max-fetch.html)
- [Spring Integration – Remote File Information](https://docs.spring.io/spring-integration/reference/sftp/remote-file-info.html)
