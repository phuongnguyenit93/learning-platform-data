# Resource Outbound Adapter: Sending Resource Data to Target Systems

## 1. Problem statement: is "Resource outbound adapter" actually a standalone component?

An order-management service has `.properties` rules on the classpath. A Spring Integration flow discovers them as `Resource` objects and needs to **publish** copies to a monitored configuration directory, or write an aggregated report to the filesystem. When designing this, a developer might assume that because Spring Integration has a **Resource inbound channel adapter**, there must be a symmetric component named `ResourceOutboundChannelAdapter`.

**That assumption is incorrect in current Spring Integration.** The **Integration Endpoints** table in the official documentation states:

| Module | Inbound adapter | Outbound adapter | Inbound gateway | Outbound gateway |
| --- | --- | --- | --- | --- |
| **Resource** | **Resource Inbound Channel Adapter** | **N — no dedicated adapter** | N | N |
| File | File inbound adapter | **File outbound channel adapter** | N | File outbound gateway |
| SFTP | SFTP inbound adapter | **SFTP outbound channel adapter** | N | SFTP outbound gateway |

Therefore, **"Resource outbound adapter" in this topic should be understood as an *outbound design pattern* for Spring `Resource` data/resources**, not the name of an existing class, annotation, or XML namespace in the Resource module. This lesson shows the **real**, API-verifiable implementation paths:

1. Convert `Resource` into a valid `byte[]`, `String`, `InputStream`, or `File` and use the **File outbound channel adapter** to write to the filesystem.
2. Write a **generic outbound channel adapter** using a POJO `@ServiceActivator` method that receives data and writes to a `WritableResource` or appropriate I/O API.
3. If the target is SFTP/HTTP/object store, choose the **adapter/gateway for that specific transport** instead of trying to send a raw `Resource` to a nonexistent "Resource outbound adapter."

This lesson belongs to the **Adapter Resource** chapter of the **SPRING_INTEGRATION_ADAPTERS** module: connecting external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`; managing message contracts, errors, and lifecycles. This section focuses on the **outbound direction** and how to choose an endpoint once you have a `Resource` or its content.

### Learning objectives

After this lesson, you will be able to:

1. State the exact scope of **Resource inbound** support and why you should not invent a dedicated outbound API.
2. Distinguish `Resource` for **reading**, `WritableResource` for **writing**, and the **File outbound handler** for writing to the filesystem.
3. Choose an appropriate Spring message contract: `Message<Resource>`, `Message<byte[]>`, `Message<String>`, `Message<File>`, or a DTO.
4. Implement File outbound using `FileWritingMessageHandler` and `FileHeaders.FILENAME`; manage `FileExistsMode`.
5. Create an outbound POJO `@ServiceActivator` writing to `WritableResource`, and explain why this is not atomic by default.
6. Convert a Resource inbound `Resource[]` batch into valid individual payloads before sending outbound.
7. Design error flows, retries, idempotency, path safety, write permissions, testing, and monitoring.

## 2. Inbound and outbound concepts are not symmetric by name

An **Inbound channel adapter** is the entry point bringing data from an external system into a `MessageChannel`. An **Outbound channel adapter** consumes messages from a channel to invoke an external target, without expecting a reply by default.

```mermaid
flowchart LR
    R["Classpath / JAR / filesystem resources"] --> IN["Resource inbound adapter"]
    IN --> B["Message<Resource[]>"]
    B --> S["Splitter"]
    S --> H["Message<Resource>"]
    H --> T["Reader / Transformer"]
    T --> P["Message<byte[]>"]
    P --> OUT["File outbound channel adapter"]
    OUT --> FS["Filesystem output directory"]
```

Observe the path:

- `ResourceRetrievingMessageSource` discovers a set of resources from patterns like `classpath*:rules/*.properties`. **The output payload is `Resource[]`** in a single Spring message.
- When each resource must be processed individually, use a splitter to obtain `Message<Resource>`.
- Writing files is not `ResourceRetrievingMessageSource`'s job. It performs **input reading/discovery**, not target writing.
- `FileWritingMessageHandler` accepts **`File`, `String`, `byte[]`, `InputStream`** payloads; **do not pass raw `Resource` or `Resource[]` assuming the handler knows how to write them**.

### Distinguishing the questions

| Question | Correct component |
| --- | --- |
| "How do I find all `*.properties` across multiple JARs?" | `ResourcePatternResolver` and Resource inbound |
| "How do I write those files to a local directory?" | Read Resource content, then **File outbound** |
| "I want to write to a custom `WritableResource`?" | Generic outbound POJO + custom I/O implementation |
| "I want to push files to an SFTP server?" | **SFTP outbound adapter/gateway** with the right payload |
| "I want to push data to an HTTP API?" | HTTP/WebFlux outbound adapter/gateway, DTO/request body |
| "I need the resulting output file for further steps?" | Consider **File outbound gateway**, not just a one-way adapter |

## 3. A readable Resource is not necessarily writable

Spring Framework defines two distinct abstractions:

```java
org.springframework.core.io.Resource;
org.springframework.core.io.WritableResource;
```

`Resource` provides inspection and reading APIs such as `getInputStream()`. `WritableResource` **extends `Resource`** and adds `getOutputStream()`:

```java
WritableResource target = ...;

if (!target.isWritable()) {
    throw new IllegalStateException("Target is not writable");
}

try (OutputStream output = target.getOutputStream()) {
    output.write(contentBytes);
}
```

`isWritable()` is a capability hint, **not a guarantee that opening the stream next will succeed**. Permissions, paths, quotas, and target state can change between check and action.

### Implementation table

| Resource implementation | Commonly used as read source | Directly writable? | Notes |
| --- | --- | --- | --- |
| `ClassPathResource` | Yes | **Not by default** | Classpath/JAR is a read source; do not treat JAR entries as output files |
| `FileSystemResource` | Yes | Yes, when filesystem/permissions allow | Can write/overwrite physical files |
| `PathResource` | Yes | Yes, when path is writable | Implements `WritableResource` |
| `FileUrlResource` | Yes | When file URL is writable | Does not imply all HTTP URLs are writable |
| `UrlResource` | Yes, depending on URL | Not by default | `getInputStream()` does not imply PUT/POST support |
| `ByteArrayResource` | Yes | Not via `WritableResource` API | Bytes in RAM; to persist, transfer to a target |
| `InputStreamResource` | Yes, usually once | No | Cannot turn a read InputStream into a write OutputStream |

**Rule:** to write, you must have a **writable target** and an appropriate API. `Resource` only describes a source; you cannot call `resource.getOutputStream()` because that method **is not part of the `Resource` interface**.

### The classpath is not an output directory

```text
Classpath resource:
  jar:file:/app/service.jar!/BOOT-INF/classes/rules/discount.properties

Filesystem target:
  file:/var/app/export/discount.properties
```

To publish a file from inside a JAR, **read** the source via `getInputStream()` and then **write** the content to a filesystem target or external API. Do not attempt to modify a `ClassPathResource` inside a running executable JAR.

## 4. Choosing the right outbound payload

Not every outbound handler accepts every Java type. For **`FileWritingMessageHandler`**, the official documentation specifies:

| Payload | Directly supported by FileWritingMessageHandler? | Meaning |
| --- | --- | --- |
| `java.io.File` | **Yes** | Copies the source file to the target directory |
| `String` | **Yes** | Writes text using the configured encoding |
| `byte[]` | **Yes** | Writes bytes directly |
| `InputStream` | **Yes** | Copies bytes from the stream into the target file |
| `Resource` | **Not in the directly supported payload list** | Requires a transformer or custom handler |
| `Resource[]` | **No** | Must be split and transformed first |
| Business DTO | Not by default | Must be serialized per an explicit contract |

### Why is `byte[]` a good choice for this example?

If the resource is small (e.g., configuration files under 64 KiB), `byte[]` is a **byte snapshot**. It no longer depends on whether the file in the classpath/JAR has its stream closed or changes after discovery.

```text
Resource handle
   -> getInputStream()
   -> bounded byte read
   -> Message<byte[]>
   -> File outbound
```

For multi-GB files, `byte[]` is inappropriate. In that case, consider `InputStream` with a lifecycle contract, `File`, streaming/remote adapters, or an object store retrievable by object key/version.

### Why not use `toString()`?

`resource.toString()` and `resource.getDescription()` usually return a **location description**, not the file contents. Converting `Resource` to `String` via `toString()` would cause outbound to write a path string instead of the desired data, potentially even leaking locations or URL tokens.

## 5. Complete Design A: Resource → bytes → File outbound adapter

Let us implement the use case: discover `classpath*:rules/*.properties`, split into individual `Resource` items, perform bounded byte reads, and write files to an output directory. This section uses the **dedicated File outbound** adapter—the most common solution when the real target is a filesystem.

```mermaid
flowchart LR
    SRC["Resource inbound / manual publisher"] --> B["resourceBatches"]
    B --> SPLIT["@Splitter"]
    SPLIT --> ITEMS["resourceItems"]
    ITEMS --> TRANS["@Transformer"]
    TRANS --> BYTES["fileOutboundInput: Message<byte[]>"]
    BYTES --> WRITER["FileWritingMessageHandler"]
    WRITER --> TARGET["/var/app/exports"]
```

### 5.1. Dependencies

Example Maven project using the Spring Boot BOM to manage compatible versions:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-file</artifactId>
    </dependency>
</dependencies>
```

**Version note:** Spring Integration **7.0+** moved the main `FileWritingMessageHandler` to the `org.springframework.integration.file.outbound` package; the older class in `org.springframework.integration.file` is deprecated. If using Spring Integration 6.x, check that version's Javadoc and use the matching import. The Java examples below use the **7.x** package; do not mix packages across versions.

### 5.2. Configuring the output directory

An application-managed output directory, e.g. configured via:

```properties
app.export-dir=/var/app/exports
```

On Windows or when running locally, replace with a valid environment path. In the example below, the directory must **already exist** and the app's service account must have write permission. Do not point it to the application's classpath or JAR.

### 5.3. Java configuration for File outbound

```java
package com.example.resourceexport;

import java.io.File;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.file.outbound.FileWritingMessageHandler;
import org.springframework.integration.file.support.FileExistsMode;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
public class ExportFileConfiguration {

    @Bean
    public MessageChannel fileOutboundInput() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "fileOutboundInput")
    public MessageHandler fileOutboundHandler(
            @Value("${app.export-dir}") String directory) {

        FileWritingMessageHandler handler =
            new FileWritingMessageHandler(new File(directory));

        handler.setExpectReply(false); // One-way outbound adapter.
        handler.setFileExistsMode(FileExistsMode.FAIL);
        handler.setAutoCreateDirectory(false);
        return handler;
    }
}
```

**Explanation:**

1. `fileOutboundInput` is a `DirectChannel` subscribed to by the outbound handler.
2. `@ServiceActivator` binds `MessageHandler` to the channel; no inbound poller is needed for this subscribable channel.
3. `FileWritingMessageHandler` handles writing physical files, not `ResourceRetrievingMessageSource`.
4. `setExpectReply(false)` indicates one-way output rather than request-reply.
5. `FileExistsMode.FAIL` rejects writes if the destination already exists, fitting a demo that detects conflicts.
6. `setAutoCreateDirectory(false)` requires the directory to be provisioned explicitly.

This code only illustrates the endpoint; it does not produce messages on its own. In the next example, a publisher sends `byte[]` along with a validated filename to `fileOutboundInput`.

### 5.4. Publisher sending bytes and filename

```java
package com.example.resourceexport;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.file.FileHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class ExportPublisher {

    private final MessageChannel output;

    public ExportPublisher(
            @Qualifier("fileOutboundInput") MessageChannel output) {
        this.output = output;
    }

    public void publish(
            String trustedFileName,
            byte[] validatedContent) {

        if (trustedFileName == null ||
                !trustedFileName.matches(
                    "[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
                )) {
            throw new IllegalArgumentException(
                "Unsafe output filename"
            );
        }
        if (validatedContent == null || validatedContent.length == 0) {
            throw new IllegalArgumentException("Empty output content");
        }

        boolean accepted = output.send(
            MessageBuilder.withPayload(validatedContent.clone())
                .setHeader(FileHeaders.FILENAME, trustedFileName)
                .build()
        );
        if (!accepted) {
            throw new IllegalStateException(
                "File outbound channel rejected message"
            );
        }
    }
}
```

`FileHeaders.FILENAME` supplies the filename to the File outbound adapter's `DefaultFileNameGenerator`. If the header is missing and the payload is not a `File`, the framework may fall back to a name based on the Spring message ID with a `.msg` suffix. For contract-based publishing, **do not rely on this fallback**.

**Important:** the regex in the demo only permits a **simple basename** and blocks paths containing slashes, but it is not a complete file-path security solution. Production needs a backend-configured directory, OS permissions, symlink checks, and verification that no other component turns headers into arbitrary paths.

### 5.5. Does File outbound convert Resource to bytes automatically?

No. The following is **against the contract**:

```java
// WRONG: FileWritingMessageHandler does not advertise Resource payloads.
// output.send(MessageBuilder.withPayload(resource).build());

// WRONG: Resource inbound emits Resource[]; the writer does not
// automatically write each element as a separate File.
// output.send(MessageBuilder.withPayload(resources).build());
```

Properly **read and convert into `byte[]`/`String`/`InputStream`/`File`** before passing to File outbound. For classpath/JAR sources, generally do not use `resource.getFile()`.

## 6. Converting Resource into Message<byte[]> with @Transformer

In a flow reading from the classpath, you can receive `Resource` from a splitter and convert it to bytes.

### 6.1. Transformer with a 64 KiB limit

```java
package com.example.resourceexport;

import java.io.IOException;
import java.io.InputStream;

import org.springframework.core.io.Resource;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.file.FileHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class ResourceToFilePayload {

    private static final int MAX_BYTES = 64 * 1024;

    @Transformer(
        inputChannel = "resourceItems",
        outputChannel = "fileOutboundInput"
    )
    public Message<byte[]> toBytes(Resource resource)
            throws IOException {

        String name = resource.getFilename();
        if (name == null ||
                !name.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,127}")) {
            throw new IllegalArgumentException(
                "Resource filename is not safe for export"
            );
        }

        byte[] bytes;
        try (InputStream input = resource.getInputStream()) {
            bytes = input.readNBytes(MAX_BYTES + 1);
        }

        if (bytes.length > MAX_BYTES) {
            throw new IOException("Resource exceeds 64 KiB");
        }

        return MessageBuilder.withPayload(bytes)
            .setHeader(FileHeaders.FILENAME, name)
            .build();
    }
}
```

The method returns **`Message<byte[]>`** to carry both bytes and the filename header. `@Transformer` is part of Spring Integration, not an outbound handler; it simply adapts the contract before File outbound writes.

**What the transformer does not automatically do:** validate `.properties` content schema, compute hashes/checksums, enforce duplicate logical ID policies, verify output file permissions, manage DB transactions, or retry after crashes.

### 6.2. Adding a splitter from Resource[] to Resource

Suppose the inbound source has emitted `Message<Resource[]>` to `resourceBatches`:

```java
package com.example.resourceexport;

import org.springframework.core.io.Resource;
import org.springframework.integration.annotation.Splitter;
import org.springframework.stereotype.Component;

@Component
public class ResourceBatchSplitter {

    @Splitter(
        inputChannel = "resourceBatches",
        outputChannel = "resourceItems"
    )
    public Resource[] split(Resource[] payload) {
        return payload;
    }
}
```

If declaring explicit channels:

```java
@Bean
public MessageChannel resourceBatches() {
    return new DirectChannel();
}

@Bean
public MessageChannel resourceItems() {
    return new DirectChannel();
}
```

These two `@Bean` methods belong in a `@Configuration` class, with imports `org.springframework.context.annotation.Bean`, `org.springframework.messaging.MessageChannel`, and `org.springframework.integration.channel.DirectChannel`. This **augments** the previous example; do not define duplicate bean names in the context.

### 6.3. Sourcing from the Resource inbound adapter

Annotation-based source configuration:

```java
@Bean
@InboundChannelAdapter(
    channel = "resourceBatches",
    poller = @Poller(
        fixedDelay = "10000",
        maxMessagesPerPoll = "1"
    )
)
public MessageSource<Resource[]> resourceSource() {
    ResourceRetrievingMessageSource source =
        new ResourceRetrievingMessageSource(
            "classpath*:rules/*.properties"
        );
    source.setFilter(new AcceptOnceCollectionFilter<>());
    return source;
}
```

This addition uses `@Bean`, `@InboundChannelAdapter`, `@Poller`, `MessageSource`, `ResourceRetrievingMessageSource`, `AcceptOnceCollectionFilter`, and `Resource` with their corresponding imports. This is a **composed flow** example; application code must ensure there is only **one** inbound poller for the same source during testing.

### Final flow

```text
classpath*:rules/*.properties
  -> ResourceRetrievingMessageSource
  -> Message<Resource[]>               (resourceBatches)
  -> @Splitter
  -> Message<Resource>                 (resourceItems)
  -> @Transformer, bounded getInputStream()
  -> Message<byte[]>                   (fileOutboundInput)
       header file_name = "discount.properties"
  -> FileWritingMessageHandler
  -> /var/app/exports/discount.properties
```

**Writing only occurs after the Resource is read into a supported payload.** If the filter accepted a resource and the transformer throws an error, `AcceptOnceCollectionFilter` does not automatically roll back or guarantee redelivery.

## 7. Design B: generic outbound channel adapter writing to WritableResource

If the target **does not fit `FileWritingMessageHandler`** or the application needs to use the `WritableResource` abstraction directly, Spring Integration provides a **generic outbound channel adapter**: a channel wired to a `void` POJO method via `@ServiceActivator` or XML `<int:outbound-channel-adapter>`.

This is an **application-owned outbound POJO**, not a built-in implementation named `ResourceOutboundChannelAdapter`.

### 7.1. Contract for the export command

```java
package com.example.resourceexport;

import java.util.Objects;

public record ExportCommand(String filename, byte[] contents) {

    public ExportCommand {
        Objects.requireNonNull(filename, "filename");
        Objects.requireNonNull(contents, "contents");
        contents = contents.clone();
    }

    @Override
    public byte[] contents() {
        return contents.clone();
    }
}
```

The record clones the byte array to prevent unintended mutations by callers; `byte[]` is mutable, so do not treat it as immutable merely because it lives inside a record.

### 7.2. POJO writing via PathResource

```java
package com.example.resourceexport;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.PathResource;
import org.springframework.core.io.WritableResource;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class WritableResourceSink {

    private final Path directory;

    public WritableResourceSink(
            @Value("${app.export-dir}") String directory) {
        this.directory = Path.of(directory).toAbsolutePath().normalize();
    }

    @ServiceActivator(inputChannel = "writableResourceRequests")
    public void write(ExportCommand command) throws IOException {
        String filename = command.filename();
        if (!filename.matches(
                "[A-Za-z0-9][A-Za-z0-9._-]{0,127}")) {
            throw new IllegalArgumentException(
                "Unsafe output filename"
            );
        }

        if (!Files.isDirectory(
                directory, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("Output directory not available");
        }

        Path destination = directory.resolve(filename).normalize();
        if (!directory.equals(destination.getParent())) {
            throw new IllegalArgumentException(
                "Output path escapes configured directory"
            );
        }

        WritableResource target = new PathResource(destination);
        try (OutputStream output = target.getOutputStream()) {
            output.write(command.contents());
        }
    }
}
```

And channel configuration:

```java
@Configuration
@EnableIntegration
public class WritableResourceChannelConfiguration {

    @Bean
    public MessageChannel writableResourceRequests() {
        return new DirectChannel();
    }
}
```

Imports: `org.springframework.context.annotation.Bean`, `Configuration`, `org.springframework.integration.config.EnableIntegration`, `org.springframework.integration.channel.DirectChannel`, and `org.springframework.messaging.MessageChannel`.

**Important limitation of this demo:** `PathResource#getOutputStream()` can **overwrite an existing file directly** and lacks `FileExistsMode.FAIL`, temporary suffix/atomic move, fsync durability, or symlink race protections found in a hardened production output solution. Regex and `normalize()` block basic path traversal, yet are **insufficient** against directories containing attacker-controlled symlinks. Run this example only against a private application-controlled directory; in production, prefer the File outbound adapter with an appropriate file-existence policy or use `Files.newOutputStream`/`CREATE_NEW`/`NOFOLLOW_LINKS` with filesystem-tested atomic publication.

### 7.3. Sending commands to the outbound POJO

```java
MessageChannel channel = ...; // inject writableResourceRequests bean

ExportCommand command = new ExportCommand(
    "rules-export.properties",
    "rule.id=demo\n".getBytes(StandardCharsets.UTF_8)
);

channel.send(MessageBuilder.withPayload(command).build());
```

Thus:

```text
Message<ExportCommand>
  -> DirectChannel
  -> @ServiceActivator WritableResourceSink.write(...)
  -> PathResource.getOutputStream()
  -> filesystem
```

**No special Resource outbound package is required.** Binding an outbound POJO to a channel is a core capability of Spring Integration Core.

## 8. When to use File outbound vs. a WritableResource POJO?

| Criterion | File outbound channel adapter | Generic POJO with WritableResource |
| --- | --- | --- |
| Dedicated endpoint? | **Yes**: `FileWritingMessageHandler` | No, application implements `@ServiceActivator` |
| Target | Filesystem directory | Any target with a real, permitted `WritableResource` |
| Standard input | `File`, `String`, `byte[]`, `InputStream` | Based on POJO/DTO method signature |
| Filename generator | Built-in, including `FileHeaders.FILENAME` | Custom-built |
| Existing-file policy | `FileExistsMode` | Custom-built |
| Temporary suffix during write | Built-in for applicable modes | Custom-built |
| Writing physical files with minimal code | Very well suited | Easy to get atomicity and security wrong |
| Writing non-filesystem APIs | Not its goal | Depends on custom implementation; usually choose transport adapter |
| Reply after writing | Choose File outbound gateway if needed | Return result via gateway/service if designed |

**Recommendation by target nature:** when writing to a filesystem, prefer the framework-provided **File outbound**. Only use a POJO with `WritableResource` when you need a custom I/O abstraction and accept full responsibility for error handling, durability, concurrency, and security.

## 9. XML: generic outbound adapter and file outbound are two different types

### 9.1. Generic POJO outbound

With a `writableResourceSink` bean having `write(ExportCommand)`:

```xml
<int:channel id="writableResourceRequests"/>

<bean id="writableResourceSink"
      class="com.example.resourceexport.WritableResourceSink"/>

<int:outbound-channel-adapter
        channel="writableResourceRequests"
        ref="writableResourceSink"
        method="write"/>
```

This is an **XML alternative** to the `@ServiceActivator` annotation placed on the class; do not enable **both endpoints** on the same channel if you want one write per message. For a POJO instantiated via XML, constructor `@Value` requires appropriate property resolution/injection; you can also declare explicit constructor arguments. Do not copy isolated XML fragments assuming every bean/namespace is already wired.

If the channel is a `QueueChannel`/`PollableChannel`, the outbound consumer needs a **poller**; a subscribable `DirectChannel` does not need a poller. This distinguishes periodically polling inbound resources from dispatching existing messages to an external target.

### 9.2. File outbound namespace

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:int="http://www.springframework.org/schema/integration"
       xmlns:int-file="http://www.springframework.org/schema/integration/file"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd
         http://www.springframework.org/schema/integration
         https://www.springframework.org/schema/integration/spring-integration.xsd
         http://www.springframework.org/schema/integration/file
         https://www.springframework.org/schema/integration/file/spring-integration-file.xsd">

    <int:channel id="fileOutboundInput"/>

    <int-file:outbound-channel-adapter
            id="resourceExportFiles"
            channel="fileOutboundInput"
            directory="${app.export-dir}"
            auto-create-directory="false"
            mode="FAIL"/>
</beans>
```

**This is the File outbound channel adapter**, not `<int-resource:outbound-channel-adapter>`. It accepts valid payloads from a transformer or publisher; the `int-file` namespace belongs to `spring-integration-file`.

### 9.3. Do not invent an XML namespace

```xml
<!-- WRONG: there is no official Resource outbound namespace like this. -->
<!-- <int-resource:outbound-channel-adapter ... /> -->
```

If you need custom resource paths/payloads, leverage the generic outbound POJO and write implementations/tests matching your application's contract.

## 10. FileExistsMode and file-writing semantics

`FileWritingMessageHandler` supports `FileExistsMode` with several policies:

| Mode | Behavior | Risk |
| --- | --- | --- |
| `REPLACE` | Overwrites an existing file; default | Can lose the previous version |
| `FAIL` | Throws an exception if the destination file already exists | Retrying after a successful write whose ACK was lost can hit conflicts |
| `IGNORE` | Skips writing when the destination file exists | Can mask stale/corrupt data if unverified |
| `APPEND` | Appends content and closes the file after each message | Interleaving/duplicate lines on retries or multiple writers |
| `APPEND_NO_FLUSH` | Appends without flushing/closing immediately | Higher risk of data loss on crash; requires flush policy |
| `REPLACE_IF_MODIFIED` | Compares timestamps per contract | Not a content hash; can be wrong if metadata is incomplete |

### Temporary file suffix

In several modes, File outbound writes using a temporary suffix (default `.writing`) and then publishes the final name once writing finishes. This mechanism **reduces the chance of consumers reading half-written files**, but does not create a distributed transaction across file write, DB, and another broker.

**Note:** `APPEND` does not use a temporary suffix this way. If consumers need to know a file is complete, use a contract-based marker file/manifest and treat files as ready only when the marker is valid.

### Why FAIL does not equal exactly-once

Suppose a worker successfully writes `event-501.json` and then crashes before updating the DB outbox. After restart, retrying the file with `FileExistsMode.FAIL` throws an exception because the file already exists. Do not blindly treat that as a brand-new business failure: compare the checksum/event ID, reconcile state, and mark idempotent success when valid.

```text
BEGIN DB -> save export job PENDING -> COMMIT
          |
          v
  File outbound writes event-501.json
          |
       JVM crash
          |
          v
  Retry same export job
          |
          +-- file exists, checksum matches => reconcile success
          +-- file exists, checksum differs => conflict/quarantine
```

## 11. Writing from Resource[]: avoid confusing a batch with multiple files

`ResourceRetrievingMessageSource` normally emits **one Spring Message carrying `Resource[]`**. Do not feed that batch straight into File outbound:

```text
WRONG:
  ResourceRetrievingMessageSource
  -> Message<Resource[]>
  -> FileWritingMessageHandler
```

Correct flow:

```text
CORRECT:
  Message<Resource[]>
  -> Splitter
  -> Message<Resource>
  -> Transformer (bounded getInputStream)
  -> Message<byte[]> + FileHeaders.FILENAME
  -> FileWritingMessageHandler
```

### Is batch atomicity guaranteed?

No. If a batch contains A, B, and C, and files A/B are written while C fails, files A/B are not automatically rolled back. When publishing an entire config set synchronously is required:

1. Resolve and validate the entire batch before writing.
2. Write into a new versioned staging directory with conflict-free naming.
3. Publish a manifest/marker or flip a version pointer only after **all files** are written and verified.
4. If concurrent readers exist, design atomic version switching based on actual filesystem/object store capabilities.

**Do not treat three file writes as a JDBC transaction**, and do not assume `@Transactional` deletes already-exported files on DB rollback.

## 12. Async boundaries: a Resource handle is not a snapshot

`Message<Resource>` may be sent into an `ExecutorChannel` or `QueueChannel`, and the worker opens the stream later. During the wait:

- The source file may be deleted or replaced.
- A remote URL's token/credential may expire.
- A class loader or plugin may be unloaded.
- An `InputStreamResource` may already be read/closed by another subscriber.
- The application may restart, losing in-memory queue messages.

If the source is guaranteed **immutable and versioned**, you can pass a trusted source ID + version/URI. Otherwise, **read and snapshot bytes before the async handoff** for small payloads, or stage into durable storage with version/ETag support.

| Topology | What does `send()` mean? | Is the file finished writing? |
| --- | --- | --- |
| `DirectChannel` → synchronous `FileWritingMessageHandler` | Handler was called and returned without exception | Handler write step finished, though not equivalent to fsync/durable commit |
| `ExecutorChannel` → `FileWritingMessageHandler` | Task was accepted by the executor | **Not necessarily** |
| In-memory `QueueChannel` → outbound poller | Message was enqueued | **Not necessarily** |
| Synchronous generic POJO `@ServiceActivator` | Method was called and returned | Follows the method's contract, not automatically durable |
| SFTP/HTTP outbound | Operation executed per adapter contract | Does not prove the final consumer processed business logic |

**Observe outcomes at the right layer.** Never mark `EXPORTED` in the DB solely because `QueueChannel.send() == true`.

## 13. Transactions, retries, and idempotency

### 13.1. No automatic shared transaction

```text
BEGIN JDBC transaction
  UPDATE orders
  SEND message to File outbound
COMMIT JDBC transaction
```

A JDBC rollback **does not automatically delete or revert written files**. Likewise, an I/O error does not roll back DB commits that already occurred earlier.

### 13.2. Outbox for critical exports

For exports that must not be missed:

1. A DB transaction persists the business update and an `export_job` with `jobId`, `targetName`, `checksum`, `status=PENDING`.
2. A worker reads `PENDING`, builds deterministic content/version, and invokes outbound.
3. After writing, **verify existence/checksum or reconcile** per contract.
4. Mark `COMPLETED` in the DB; if a crash occurs between file write and DB update, retry the same `jobId` and reconcile.
5. For permanent errors (bad path, permissions, invalid payload), move to `FAILED`/quarantine instead of infinite hot retries.

### 13.3. Identifier keys

| Key | Used for | Do not use in place of |
| --- | --- | --- |
| `jobId` / `eventId` | Business deduplication and retries | Spring message UUID |
| `targetName` | Validated destination name | Raw user-provided path |
| `contentChecksum` | Verifying file content after writing | `lastModified` timestamp alone |
| `MessageHeaders.ID` | Tracing inside an integration flow | Durable export job ID |
| `Resource.getFilename()` | Basename hint | Unique key across multiple JARs/modules |

### 13.4. Duplicates from multiple replicas

Two pods might receive the same `Message<Resource>` and try to write the same file. `FileExistsMode.FAIL` exposes the conflict at the destination, but it is not a distributed lock. You need DB claims/locks/outbox leases, object versioning, or a single-writer workflow. If using `APPEND` while two pods write the same file, you risk interleaved or duplicated data.

## 14. Security: both destination paths and Resources can be untrusted

An outbound writer with filesystem write access is a sensitive capability.

### Minimum controls

1. **Server-configured fixed output directory**; never take raw root directories from HTTP headers.
2. Backend-generated or allowlisted filenames containing no `../`, `..\\`, absolute paths, or control characters.
3. Resolve/normalize and verify the target stays under the allowed root; also guard against symlink traversal/TOCTOU using appropriate APIs and filesystem permissions.
4. The application's OS account should have write access only to the exact required directory.
5. Do not allow overwriting/appending sensitive data outside business policy.
6. Bound resource sizes and counts before reading/writing.
7. Never use raw `resource.getDescription()`/URLs as filenames or in public logs.
8. Remote Resources require host/protocol allowlists to prevent SSRF, plus redirect, timeout, and TLS controls.
9. Never accept arbitrary client-constructed `WritableResource` instances if the method runs with elevated backend privileges.
10. For multi-tenant data, verify tenant ownership/permissions before exporting files or sending to remote adapters.

### A simple regex is not enough

`[A-Za-z0-9][A-Za-z0-9._-]{0,127}` blocks slashes and empty basenames in the example. Still, you must check:

- Symlinks/existing files inside the directory.
- Races between validation and opening.
- Filesystem permissions on parent directories.
- Reserved Windows filenames and platform limits.
- Unicode normalization if the application permits multilingual names.

For high-security requirements, use a **backend-generated filename from a UUID/event ID** and store the user's display name **strictly as metadata**, never as a path.

## 15. Output does not have to be a filesystem

`WritableResource` only makes sense if an implementation allows opening an `OutputStream`. An HTTP API, SFTP server, or object store usually has its own protocol API and is not inherently a `WritableResource`.

| Target | Preferred choice | Recommended payload |
| --- | --- | --- |
| Local filesystem | File outbound adapter | `File`, `byte[]`, `String`, `InputStream` |
| SFTP | SFTP outbound adapter/gateway | Per SFTP adapter contract, after transformation |
| HTTP REST endpoint | HTTP/WebFlux outbound adapter/gateway | Serialized JSON DTO/`byte[]`/request body |
| Kafka/JMS/AMQP | Broker outbound adapter | Serialized event/DTO with idempotency |
| Object store S3/Azure/GCS | Specific SDK/adapter | Bytes/stream, object key, checksum/version |
| An application `WritableResource` | Generic outbound POJO | Validated DTO/bytes |

Do not send a raw `ClassPathResource` over a message broker between two JVMs expecting a consumer on another host to open a JAR entry. Send **serialized content** or an independently accessible versioned object key.

### Adapter or gateway?

- **Outbound adapter:** one-way; does not define a reply message.
- **Outbound gateway:** can emit a reply containing the operation result per endpoint contract.
- **POJO service:** can be one-way or request-reply depending on signature/flow.

If you need confirmation of the created physical file to continue a flow, the File outbound **gateway** fits better than a one-way adapter. Even then, a "file written" reply does not prove an external system has read or applied the content.

## 16. Testing with JUnit: payload contracts and write safety

### 16.1. Testing Resource → byte[] with @TempDir

Test without starting a poller, verifying only the transformer:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.core.io.FileSystemResource;
import org.springframework.integration.file.FileHeaders;
import org.springframework.messaging.Message;

class ResourceToFilePayloadTest {

    @TempDir
    Path tempDir;

    @Test
    void transformsReadableResourceIntoBytesAndFileName()
            throws Exception {
        Path source = tempDir.resolve("rule.properties");
        Files.writeString(source, "rule.id=demo\n",
            StandardCharsets.UTF_8);

        ResourceToFilePayload transformer =
            new ResourceToFilePayload();

        Message<byte[]> result =
            transformer.toBytes(new FileSystemResource(source));

        assertEquals("rule.properties",
            result.getHeaders().get(FileHeaders.FILENAME));
        assertArrayEquals(
            "rule.id=demo\n".getBytes(StandardCharsets.UTF_8),
            result.getPayload()
        );
    }
}
```

This test only exercises the **transformer**. It does not initialize `FileWritingMessageHandler`, guarantee writing to disk succeeds, or test sources inside a JAR.

### 16.2. Testing the WritableResourceSink POJO

```java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class WritableResourceSinkTest {

    @TempDir
    Path tempDir;

    @Test
    void writesBytesIntoApprovedDirectory() throws Exception {
        var sink = new WritableResourceSink(tempDir.toString());
        var command = new ExportCommand(
            "report.txt",
            "hello".getBytes(StandardCharsets.UTF_8)
        );

        sink.write(command);

        assertEquals(
            "hello",
            Files.readString(
                tempDir.resolve("report.txt"),
                StandardCharsets.UTF_8
            )
        );
    }

    @Test
    void rejectsTraversalLikeName() {
        var sink = new WritableResourceSink(tempDir.toString());

        assertThrows(IllegalArgumentException.class,
            () -> sink.write(new ExportCommand(
                "../escape.txt", new byte[] { 1 }
            )));
    }
}
```

**Note:** `WritableResourceSink` above uses direct writing and can overwrite files. Unit tests verify basic behavior, **not** atomic writes, symlink-race resistance, or crash durability.

### 16.3. Integration testing with File outbound

Use a dedicated Spring test context with:

- `fileOutboundInput` as a `DirectChannel`.
- `FileWritingMessageHandler` bound via `@ServiceActivator`.
- `app.export-dir` pointing to a prepared `@TempDir`.
- A publisher sending `Message<byte[]>` with `FileHeaders.FILENAME`.

Verify the file is created with matching content. Send the same filename again with `FileExistsMode.FAIL` and assert an exception is thrown. If switched to `ExecutorChannel`, the test must await completion and inspect the error flow—do not check the file immediately after `send()` returns assuming the worker has finished.

### 16.4. Additional test cases to cover

1. Classpath/JAR resources are opened with `getInputStream()`, not `getFile()`.
2. Resource source emits `Resource[]`; splitter emits individual `Resource` messages.
3. Output file has exact UTF-8/bytes and matching checksum.
4. Payloads exceeding 64 KiB are rejected by the transformer before writing.
5. Filenames containing `../`, slashes, backslashes, or control characters are rejected.
6. Nonexistent or unwritable output directory when `autoCreateDirectory=false`.
7. `FAIL` when the file already exists and conflict reconciliation behavior.
8. Power loss/crash after file write before DB update: retry/reconcile by event ID.
9. Two concurrent writers: claim/lock/unique-naming strategy holds.
10. For remote adapters, verify timeout retries do not create duplicate business effects.

## 17. Monitoring and troubleshooting

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Cannot find `ResourceOutboundChannelAdapter` | **No dedicated Resource outbound adapter exists** | Use File outbound, an outbound POJO, or the transport-specific adapter |
| `MessageHandlingException` when sending `Resource` | `FileWritingMessageHandler` does not support raw `Resource` | Transform to `File`/`String`/`byte[]`/`InputStream` |
| `ClassCastException` with `Resource[]` | Skipped the splitter step | Split the batch before invoking the per-resource transformer |
| File written with UUID name and `.msg` extension | Missing `FileHeaders.FILENAME` | Attach a validated filename header |
| `getFile()` fails in executable JAR | Classpath resource has no physical file | Read `getInputStream()` and convert to bytes |
| Target file already exists error | `FileExistsMode.FAIL` | Reconcile/checksum or pick a mode matching the contract |
| File silently overwritten | Default `REPLACE` | Configure `FAIL`/versioned filenames |
| Output written to wrong directory | Uncontrolled header/path | Fix the root, sanitize basenames, check symlinks |
| Partial file read by consumer | No safe publication protocol | Temporary suffix/marker/staging as appropriate |
| Channel send succeeds but no file appears | Async worker has not run or failed | Monitor worker completion/error channels |
| Resource breaks after queue delay | Stale handle, one-shot stream | Snapshot or use versioned storage |
| Restart triggers duplicate export | Non-durable source filter or queue | Outbox/idempotency/ledger |
| `WritableResource.isWritable()==true` yet write fails | Permission/quota/TOCTOU | Catch `IOException`, inspect infrastructure, bound retries |
| Multiple pods write same filename | Lack of coordination | Use unique job IDs, distributed claims, and versioned naming |

### Metrics to collect

Track messages received from channels, Resources read successfully, total bytes transformed, transformer latency, file write successes/failures, `FAIL` conflicts, queue depth, outbox-to-export latency, checksum mismatches, retries/duplicates, and permission/quota errors. Clearly distinguish **message received**, **file written**, **outbox updated**, and **external consumer applied file**.

## 18. Hands-on exercises with answers

**Exercise 1 — API.** Does Spring Integration ship a built-in `ResourceOutboundChannelAdapter`?

**Answer:** No. The Integration Endpoints table lists Resource as having only an inbound adapter; outbound requires the File adapter, a generic POJO, or a target-specific adapter.

**Exercise 2 — Abstraction.** Does `Resource` have a `getOutputStream()` method?

**Answer:** No. `WritableResource` is the interface that adds the write API.

**Exercise 3 — Classpath.** Should you write directly to a `ClassPathResource` inside an executable JAR?

**Answer:** No. Read via stream and write to a valid writable target, typically a separate filesystem directory or external API.

**Exercise 4 — File outbound payloads.** Which four basic payload types does `FileWritingMessageHandler` support?

**Answer:** `File`, `String`, `byte[]`, and `InputStream`.

**Exercise 5 — Resource[] batch.** The Resource inbound source emits a `Resource[]` of 10 elements. Can you send this array straight to File outbound to create 10 files?

**Answer:** No. You must split and transform each element into a payload supported by File outbound.

**Exercise 6 — Filename.** From which standard header does File outbound obtain the filename?

**Answer:** `FileHeaders.FILENAME`, when using the default filename generator.

**Exercise 7 — Missing header.** What filename can a `byte[]` payload without a filename header be written with?

**Answer:** The default filename generator may fall back to the Spring message ID with a `.msg` extension; do not rely on this for business contracts.

**Exercise 8 — Existing file.** Which mode throws an error if the destination file already exists?

**Answer:** `FileExistsMode.FAIL`.

**Exercise 9 — Overwrite.** Is `FileExistsMode.REPLACE` a version control mechanism?

**Answer:** No. It overwrites the target file; for versioning, design versioned filenames or store history.

**Exercise 10 — Append.** Why is `APPEND_NO_FLUSH` riskier than `APPEND` on power loss?

**Answer:** Data may still sit in unflushed/unclosed buffers; a flush strategy and durability evaluation are required.

**Exercise 11 — Generic outbound.** Which annotation invokes a POJO method when a message arrives on a channel?

**Answer:** `@ServiceActivator(inputChannel = "...")` or XML `<int:outbound-channel-adapter>`.

**Exercise 12 — Poller.** Does a `DirectChannel` outbound consumer require its own poller?

**Answer:** No. `DirectChannel` is subscribable; a poller is required for a `PollableChannel` such as `QueueChannel`.

**Exercise 13 — WritableResource.** Does `isWritable()==true` guarantee `getOutputStream()` won't throw `IOException`?

**Answer:** No. Permissions/FS/quotas/targets can change; write errors must still be handled.

**Exercise 14 — Remote targets.** Can you send a raw `Resource` directly into SFTP/HTTP assuming every adapter understands it?

**Answer:** No. You must follow the actual adapter's payload/header contract, usually transforming the content first.

**Exercise 15 — Transactions.** Does a DB rollback automatically delete files written by File outbound?

**Answer:** No. JDBC and the filesystem are separate transaction boundaries.

**Exercise 16 — Duplicates.** After a crash between file write and outbox update, a retry hits `FAIL`. Can you assume the job never wrote the file?

**Answer:** No. Reconcile using checksum/eventId to determine whether the right file already exists or there is a conflict.

**Exercise 17 — Async.** Does `ExecutorChannel.send()` returning `true` prove the file write completed?

**Answer:** No. It may only confirm the task was accepted for async execution.

**Exercise 18 — Security.** Is it safe to let clients send `../secret.txt` as a filename?

**Answer:** No. Enforce basename allowlists, root containment, symlink checks, and filesystem permissions.

**Exercise 19 — Atomic writes.** Does `WritableResource#getOutputStream()` automatically provide atomic publishing and a temporary suffix?

**Answer:** No. It is an API to open an output stream; atomic/temp policies must be designed by the implementation/application.

**Exercise 20 — When a reply is needed.** After writing a file, the flow needs the created `File` to continue. Which endpoint should you consider?

**Answer:** The File outbound **gateway**, rather than a one-way adapter alone.

**Exercise 21 — Choosing an approach.** A system just needs to export small rules from the classpath to a local directory; what is the most sensible design?

**Answer:** Resource inbound → splitter → bounded read to `byte[]` + `FileHeaders.FILENAME` → File outbound handler.

**Exercise 22 — Testing.** Does unit testing `WritableResourceSink` with `@TempDir` prove symlink resistance and crash safety in production?

**Answer:** No. You must test security/concurrency/atomicity on the real filesystem and permissions, plus retry/reconciliation.

## 19. Key takeaways

**There is no dedicated Resource outbound channel adapter in Spring Integration per the official endpoints table.** "Resource outbound adapter" refers to the pattern of sending content from `Resource`/**`Resource[]`** to a target system. When writing to the filesystem, use **`FileWritingMessageHandler`** or `int-file:outbound-channel-adapter`; they support `File`, `String`, `byte[]`, and `InputStream`, **not raw `Resource`**. If the source is `Resource[]`, **split**, perform bounded reads with `getInputStream()`, and transform before sending. When a custom writable target is required, use **`WritableResource`** via a **generic outbound POJO `@ServiceActivator`**, taking responsibility for path validation, overwrites, atomicity, and retries. For SFTP, HTTP, or brokers, pick the real transport adapter. Always separate message delivery, file writes, DB commits, and external consumption; add idempotency/outbox when high reliability is needed.

## References

- [Spring Integration — Integration Endpoints (Resource module row: outbound N)](https://docs.spring.io/spring-integration/reference/endpoint-summary.html)
- [Spring Integration — Resource Support](https://docs.spring.io/spring-integration/reference/resource.html)
- [Spring Integration — Channel Adapter, generic outbound](https://docs.spring.io/spring-integration/reference/channel-adapter.html)
- [Spring Integration — File Support](https://docs.spring.io/spring-integration/reference/file.html)
- [Spring Integration — Writing Files](https://docs.spring.io/spring-integration/reference/file/writing.html)
- [Spring Integration API — FileWritingMessageHandler, 7.x](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/file/outbound/FileWritingMessageHandler.html)
- [Spring Integration API — FileExistsMode](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/file/support/FileExistsMode.html)
- [Spring Framework API — Resource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/Resource.html)
- [Spring Framework API — WritableResource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/WritableResource.html)
