# Configuring GridFsTemplate and GridFsOperations

## 1. Why does a Spring Data MongoDB application need GridFS configuration?

Suppose a case-processing system needs to store contract PDFs, document scans, and exported reports. Business data such as case ID, processing status, and reviewer can be stored in ordinary MongoDB documents. However, files may exceed the size limit of a single BSON document (typically **16 MiB**) or need to be read and written as streams. MongoDB provides **GridFS** to split files into multiple chunks and store associated metadata.

Within the scope of **SPRING_DATA_MONGODB**, we need to connect to MongoDB, map metadata, perform operations with templates or repositories, and control queries, reactive access, testing, and performance. For GridFS files, the key Spring Data MongoDB components are:

- `GridFsOperations`: an **interface** representing the contract for storing, searching, retrieving `Resource` objects, and deleting files.
- `GridFsTemplate`: the **synchronous (imperative) implementation** of `GridFsOperations`, using the MongoDB Java Driver to work with GridFS.
- `ReactiveGridFsOperations` and `ReactiveGridFsTemplate`: the corresponding interface/implementation pair for reactive streams.

A basic configuration needs to know the **database**, **bucket**, and **MongoConverter**:

~~~text
Spring service
    |
    +---- GridFsOperations (interface)
                |
                v
          GridFsTemplate
                |-- MongoDatabaseFactory --> MongoDB database
                |-- MongoConverter -------> maps metadata Java <-> BSON
                +-- bucket "fs" (default)
                        |-- fs.files  : name, length, uploadDate, metadata...
                        +-- fs.chunks : binary data parts
~~~

For example, with bucket `attachments`, the two collections used are `attachments.files` and `attachments.chunks`. GridFS collections are not like a `@Document` entity that maps to a single collection.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish `GridFsOperations` from `GridFsTemplate` and know when to use the reactive counterpart.
2. Configure GridFS in Spring Boot or declare explicit beans with `MongoDatabaseFactory` and `MongoConverter`.
3. Specify buckets and databases, and select beans with `@Qualifier` when multiple buckets exist.
4. Perform `store`, `findOne`, `getResource`, `getResources`, and `delete` with proper resource handling.
5. Verify data in `<bucket>.files` and `<bucket>.chunks`, write a small integration test, and troubleshoot configuration errors.
6. Understand limitations around metadata, duplicate filenames, queries, failed uploads, and memory performance.

## 2. Foundations: database, bucket, files, and chunks

### 2.1. How does GridFS split a file?

A file stored in a GridFS **bucket** has two logical parts:

| Collection | Main data | Role |
| --- | --- | --- |
| `<bucket>.files` | `_id`, `filename`, `length`, `chunkSize`, `uploadDate`, `metadata` | One document describing each file |
| `<bucket>.chunks` | `files_id`, `n`, `data` | Chunks containing the actual bytes |

The `files_id` field of chunks points to the file's `_id`. `n` specifies the chunk order within the file. The driver is responsible for splitting data during upload and reassembling it during download; normally the application does not need to interact with `*.chunks` directly.

~~~mermaid
flowchart LR
    A["2 MiB PDF"] --> B["GridFsTemplate.store(InputStream, ...)"]
    B --> C["GridFSBucket"]
    C --> D["attachments.files: fileId, name, length, metadata"]
    C --> E["attachments.chunks: chunk 0, 1, 2, ..."]
    D --> F["findOne / getResource"]
    E --> F
    F --> G["InputStream returns bytes to caller"]
~~~

The default bucket is named `fs`, so its collections are `fs.files` and `fs.chunks`. When choosing the `attachments` bucket, the corresponding pair of names is `attachments.files` and `attachments.chunks`. A bucket is a **storage namespace**, not a new database.

### 2.2. Required Spring components

| Component | Responsibility | Notes |
| --- | --- | --- |
| `MongoClient` | Opens connections to MongoDB via driver | Can be managed by Spring Boot |
| `MongoDatabaseFactory` | Provides MongoDB database for synchronous operations | Depends on connection configuration |
| `MongoConverter` | Maps Java/BSON metadata | Usually `MappingMongoConverter` |
| `GridFsTemplate` | Executes synchronous GridFS commands | Implements `GridFsOperations` |
| `GridFsOperations` | API for services, convenient for DI and mocking | Prefer injecting by interface |
| `ReactiveMongoDatabaseFactory` | Provides database in the reactive stack | Used with the reactive driver |
| `ReactiveGridFsTemplate` | Executes reactive GridFS operations | Implements `ReactiveGridFsOperations` |

**You do not need to create a MongoDB repository for each GridFS file** to use these APIs. Repositories remain useful for managing separate business documents (for example, `attachments` holding `caseId`, `fileId`, and access permissions), while bytes are stored by GridFS through the bucket.

## 3. Preparing dependencies and connection

Examples use Spring Boot with MongoDB and modern Java. With **Maven**, the main dependency for synchronous operations is:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Or with **Gradle**:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
~~~

Configure the MongoDB connection in `application.properties` according to your Spring Boot configuration:

~~~properties
spring.data.mongodb.uri=mongodb://localhost:27017/document_store
~~~

The example above follows Spring Boot 3.x configuration conventions. For other Spring Boot generations, check the property namespace of the exact version before copying.

The URI only configures the database the application accesses; **it does not automatically decide which bucket is chosen when creating `GridFsTemplate`**, unless specific GridFS properties or beans do so.

The application must have appropriate permissions to operate on the bucket collections. A read-only user cannot upload or delete files. When testing, prefer using a dedicated database like `document_store` and an account following the principle of least privilege.

### 3.1. Configuration choices

There are two common paths:

1. **Spring Boot auto-configuration**: when conditions match and there is no application-defined `GridFsOperations` bean, Boot can provide a default `GridFsTemplate`.
2. **Explicit bean**: declare `GridFsTemplate` yourself when an explicit bucket, multiple buckets, multiple databases, or wiring control is needed.

Avoid mixing both approaches haphazardly: an application-defined bean can cause auto-configuration to **back off**. Therefore, if you declare beans explicitly, define clearly which `GridFsOperations` beans services actually use.

## 4. Option A: using GridFsOperations configured by Spring Boot

In an appropriately configured Spring Boot application, a service simply injects the interface:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.data.mongodb.gridfs.GridFsOperations;

@Service
public class DocumentStorageService {

    private final GridFsOperations gridFs;

    public DocumentStorageService(GridFsOperations gridFs) {
        this.gridFs = gridFs;
    }

    // store/find/getResource/delete operations are added in section 7.
}
~~~

If using the default bucket, its name is `fs`. With Spring Boot 3.x lines supporting GridFS properties, you can configure it explicitly:

~~~properties
spring.data.mongodb.uri=mongodb://localhost:27017/document_store
spring.data.mongodb.gridfs.bucket=attachments
~~~

Some Spring Boot versions also support a property to choose a **dedicated GridFS database** such as `spring.data.mongodb.gridfs.database`. Check the configuration documentation for your exact version, as namespaces and auto-configuration conditions may vary.

**Bean verification at startup**: if Spring reports no `GridFsOperations` bean, check dependencies, auto-configuration, and custom configuration. If multiple beans exist without `@Primary` or `@Qualifier`, Spring may throw `NoUniqueBeanDefinitionException`.

The advantage of this approach is that the service depends on the `GridFsOperations` contract, making it easy to swap implementations or substitute a mock in unit tests. However, when precise control over multiple buckets is required, explicit declarations are clearer.

## 5. Option B: creating an explicit GridFsTemplate bean

The most common constructor:

~~~java
new GridFsTemplate(mongoDatabaseFactory, mongoConverter)
~~~

and the variant selecting a specific bucket:

~~~java
new GridFsTemplate(mongoDatabaseFactory, mongoConverter, "attachments")
~~~

Example `@Configuration` using **a single bean** to manage the `attachments` bucket:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.convert.MongoConverter;
import org.springframework.data.mongodb.gridfs.GridFsOperations;
import org.springframework.data.mongodb.gridfs.GridFsTemplate;

@Configuration
public class GridFsConfig {

    @Bean
    public GridFsOperations gridFsOperations(
            MongoDatabaseFactory databaseFactory,
            MongoConverter converter) {

        return new GridFsTemplate(
            databaseFactory,
            converter,
            "attachments"
        );
    }
}
~~~

Key points to understand:

- `MongoDatabaseFactory` selects the database from the application's MongoDB configuration.
- `MongoConverter` is managed by the framework and can integrate custom converters for metadata types.
- `"attachments"` is the bucket name. With this configuration, the driver operates on `attachments.files` and `attachments.chunks`.
- Returning `GridFsOperations` lets services inject by interface; the actual object is still `GridFsTemplate`.
- A `GridFsTemplate` **does not need to be recreated per upload**. Configuring it as a singleton bean reuses connections and management handled by Spring and the driver.

Do not instantiate a new `MongoClient` and `MongoConverter` inside each request. That can create redundant connection pools and cause inconsistent metadata mapping.

### 5.1. Role of MongoConverter for metadata

`GridFsTemplate.store(...)` accepts metadata as `Object` or `Document`. When passing a Java object, the template uses `MongoConverter` to convert it to BSON. For example:

~~~java
public record AttachmentMetadata(
    String caseId,
    String uploader,
    String category
) {}
~~~

When uploading:

~~~java
AttachmentMetadata metadata = new AttachmentMetadata(
    "CASE-2026-001",
    "user-123",
    "contract"
);
~~~

Note that this is **illustrative information**. `MongoConverter` does not replace authentication and business authorization. Metadata may need schema validation, type checks, tenant checks, and user permission checks before being written to GridFS. If exact control over BSON is desired, you can pass `org.bson.Document`:

~~~java
Document metadata = new Document("caseId", "CASE-2026-001")
    .append("category", "contract")
    .append("version", 1);
~~~

Avoid relying on Java class names as a long-term data API contract. When metadata structure evolves, explicitly define versions, migrations, and reading logic.

## 6. Configuring multiple buckets in the same database

An organization may want to store contract files and profile images in separate buckets for independent management, such as `contracts` and `avatars`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.convert.MongoConverter;
import org.springframework.data.mongodb.gridfs.GridFsOperations;
import org.springframework.data.mongodb.gridfs.GridFsTemplate;

@Configuration
public class MultiBucketGridFsConfig {

    @Bean("contractsGridFs")
    public GridFsOperations contractsGridFs(
            MongoDatabaseFactory factory,
            MongoConverter converter) {
        return new GridFsTemplate(factory, converter, "contracts");
    }

    @Bean("avatarsGridFs")
    public GridFsOperations avatarsGridFs(
            MongoDatabaseFactory factory,
            MongoConverter converter) {
        return new GridFsTemplate(factory, converter, "avatars");
    }
}
~~~

Inject the right bean using `@Qualifier`:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.data.mongodb.gridfs.GridFsOperations;

@Service
public class ContractFileService {

    private final GridFsOperations contracts;

    public ContractFileService(
            @Qualifier("contractsGridFs") GridFsOperations contracts) {
        this.contracts = contracts;
    }
}
~~~

Corresponding collection pairs:

~~~text
document_store
├── contracts.files
├── contracts.chunks
├── avatars.files
└── avatars.chunks
~~~

If you inject solely by `GridFsOperations` when two beans exist and no selection rule is provided, Spring does not know which bean to use. `@Qualifier` is the clearest approach, while `@Primary` is only suitable if there is genuinely one default bucket.

### 6.1. A bucket is not a database

~~~text
MongoDatabaseFactory --> database "document_store"
                               |
                               +-- bucket "contracts"
                               |      +-- contracts.files
                               |      +-- contracts.chunks
                               |
                               +-- bucket "avatars"
                                      +-- avatars.files
                                      +-- avatars.chunks
~~~

If you need to separate **databases** or different MongoDB connections, you must use a corresponding `MongoDatabaseFactory` (or Boot's dedicated GridFS auto-configuration mechanism if supported by your version). Simply passing `bucket = "contracts"` does not move data into a new database.

### 6.2. Why shouldn't you switch buckets by mutating singleton state?

`GridFsTemplate` typically obtains `GridFSBucket` lazily on the first operation and **caches/reuses** that bucket on the instance. Therefore, a design that “mutates a property at runtime so the same singleton switches to another bucket” easily leads to unintended behavior.

When buckets are fixed, use **one template/bean per bucket**. If you genuinely need dynamic per-operation bucket selection, the API provides a constructor accepting `Supplier<GridFSBucket>` (in supported versions), requiring careful design of the supplier, lifecycle, and permission boundaries. Choosing a bucket by tenant must verify the tenant identifier from a trusted source rather than taking an arbitrary bucket name directly from the request.

## 7. Using GridFsOperations: upload, read back, and delete

### 7.1. Uploading with InputStream

Example of a synchronous service that accepts an `InputStream` and returns the `ObjectId` of the new file:

~~~java
import java.io.IOException;
import java.io.InputStream;

import org.bson.Document;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.gridfs.GridFsOperations;
import org.springframework.stereotype.Service;

@Service
public class GridFsFileWriter {

    private final GridFsOperations gridFs;

    public GridFsFileWriter(GridFsOperations gridFs) {
        this.gridFs = gridFs;
    }

    public ObjectId savePdf(
            InputStream content,
            String filename,
            String caseId) throws IOException {

        Document metadata = new Document("caseId", caseId)
            .append("category", "contract")
            .append("schemaVersion", 1);

        // Caller owns the InputStream; must close where opened.
        // This is a blocking operation.
        return gridFs.store(
            content,
            filename,
            "application/pdf",
            metadata
        );
    }
}
~~~

In the snippet above, `GridFsOperations.store(InputStream, filename, contentType, metadata)` performs the upload and returns an `ObjectId`. `store` does not create a local file: it writes chunks to MongoDB. **The input is a stream**, so there is no need to load the entire file into a `byte[]` before uploading.

`savePdf` only demonstrates the API and does not verify that the content is actually a PDF. In a production application, enforce size limits, file type checks, virus/malware scanning per policy, access control, and filename checks. Never blindly trust a client-supplied MIME type.

### 7.2. Example calling upload from a local file

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.bson.types.ObjectId;

Path source = Path.of("sample-contract.pdf");

try (InputStream input = Files.newInputStream(source)) {
    ObjectId fileId = writer.savePdf(
        input,
        "sample-contract.pdf",
        "CASE-2026-001"
    );

    System.out.println("GridFS fileId = " + fileId.toHexString());
}
~~~

This snippet is a **caller** example for `GridFsFileWriter`, not a method placed directly at the top level of a Java class. `try-with-resources` ensures the InputStream is closed after upload. Do not store an `InputStream` inside a Spring singleton.

### 7.3. Finding files with GridFS queries

Suppose you need to look up a file by `fileId` to retrieve the exact version:

~~~java
import com.mongodb.client.gridfs.model.GridFSFile;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

ObjectId id = new ObjectId("690000000000000000000001");

Query query = new Query(Criteria.where("_id").is(id));
GridFSFile file = gridFs.findOne(query);

if (file == null) {
    throw new IllegalArgumentException("File not found: " + id);
}
~~~

`GridFsOperations.findOne(Query)` returns a `GridFSFile` or `null`. A download request should look up the file by the **ID stored in the business record**, after verifying that the user has permission to access that record.

Do not assume filenames are unique: GridFS allows **multiple files with the same filename**. If using `findOne` by filename, the result may not be the version the caller expects.

Spring Data provides helpers specifically for metadata and filenames:

~~~java
import static org.springframework.data.mongodb.gridfs.GridFsCriteria.whereFilename;

Query byName = new Query(whereFilename().is("sample-contract.pdf"));

GridFSFile found = gridFs.findOne(byName);
~~~

To search by metadata, you can use `GridFsCriteria.whereMetaData("caseId")`. Attaching `Sort` to `Query` is not applied by the GridFS template in the same way as regular MongoDB queries; do not build business logic around “latest file” relying solely on `Query.with(Sort...)` on this API. Manage versions/fileIds in a separate entity instead.

### 7.4. Reading bytes via GridFsResource

Once you have a `GridFSFile`:

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.data.mongodb.gridfs.GridFsResource;

GridFsResource resource = gridFs.getResource(file);
Path output = Path.of("downloaded-contract.pdf");

try (InputStream in = resource.getInputStream();
     OutputStream out = Files.newOutputStream(output)) {
    in.transferTo(out);
}
~~~

`getResource(GridFSFile)` returns a `GridFsResource`, giving access to `InputStream`, filename, content length, and some metadata. `InputStream` is a resource that must be closed. The example uses `transferTo` from Java 9+; on older Java versions, copy using a small buffer.

Do not return an `InputStream` from a method that has already closed it. When implementing HTTP downloads, keep the stream open while the response is written, handle client disconnects, and limit concurrent connections.

### 7.5. getResource by filename and getResources by pattern

Spring Data provides:

~~~java
GridFsResource byFilename =
    gridFs.getResource("sample-contract.pdf");

GridFsResource[] textFiles =
    gridFs.getResources("*.txt");
~~~

`GridFsOperations` extends `ResourcePatternResolver`, so files can be selected using name patterns. Even so, name-based `getResource(String)` **does not solve versioning/duplicate filename issues**. Avoid using it as the retrieval path for critical contracts if the application already stores `fileId`.

If a filename is not found, check `resource.exists()` before calling `getInputStream()`. For pattern results, the array may be empty.

### 7.6. Properly scoped file deletion

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public void deleteById(GridFsOperations gridFs, ObjectId id) {
    Query byId = new Query(Criteria.where("_id").is(id));
    gridFs.delete(byId);
}
~~~

`delete(Query)` deletes **all files matching the query** along with their chunks. Passing a broad query or one matching duplicate filenames can accidentally delete multiple files. Ensure authorization, fileId, and business retention checks have passed before invoking delete; never allow `delete(new Query())` directly from a user-facing API.

## 8. Verifying configuration with mongosh

After the first upload, open `mongosh` to verify the bucket and metadata:

~~~javascript
use document_store

show collections

// Example configuration for bucket "attachments":
db.getCollection("attachments.files")
  .find(
    {},
    { filename: 1, length: 1, uploadDate: 1, metadata: 1 }
  )
  .limit(5)

// Pick a file and verify its corresponding chunks exist:
const file = db.getCollection("attachments.files").findOne({});

if (file) {
  printjson(file);

  const chunks = db.getCollection("attachments.chunks")
    .find({ files_id: file._id })
    .sort({ n: 1 })
    .limit(5)
    .toArray();

  printjson(chunks.map(c => ({
    n: c.n,
    bytes: c.data.length()
  })));
}
~~~

If your MongoDB driver/mongosh version represents `Binary` differently, measuring bytes with `c.data.length()` may need adjustment per the corresponding API. The key goal is confirming **`files_id` and `n`** match the uploaded file.

Data must reside in the **database and bucket configured on the bean**. If upload returns an ID but operators do not see `fs.files`, check whether the application is actually using the `attachments` bucket or another database.

### 8.1. Quick runtime checklist

1. MongoDB is reachable using the right URI and credentials.
2. The Spring context has a matching `GridFsOperations` bean, or beans are selected with `@Qualifier`.
3. The bean receives the expected `MongoDatabaseFactory` and `MongoConverter`.
4. The active bucket matches the intended `<bucket>.files` / `<bucket>.chunks`.
5. Uploading a small file returns `fileId`; `findOne` by ID finds the file; `getResource` reads bytes identical to the input.
6. Test deleting the newly created file in a **test database**, verifying both the file and its chunks are gone.

## 9. Configuring ReactiveGridFsTemplate for WebFlux applications

If the project uses reactive MongoDB, use `ReactiveGridFsOperations` instead of the synchronous interface; the implementation is `ReactiveGridFsTemplate`. Never call blocking methods of `GridFsOperations` directly on the Netty event loop.

Reactive dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
~~~

Declaring a custom bucket:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.core.convert.MongoConverter;
import org.springframework.data.mongodb.gridfs.ReactiveGridFsOperations;
import org.springframework.data.mongodb.gridfs.ReactiveGridFsTemplate;

@Configuration
public class ReactiveGridFsConfig {

    @Bean("reactiveAttachmentsGridFs")
    public ReactiveGridFsOperations reactiveAttachmentsGridFs(
            ReactiveMongoDatabaseFactory factory,
            MongoConverter converter) {

        return new ReactiveGridFsTemplate(
            factory,
            converter,
            "attachments"
        );
    }
}
~~~

This is an **alternative configuration option** for reactive applications. You do not need to create both synchronous and reactive beans if only one model is used.

### 9.1. Storing files with Publisher<DataBuffer>

In the reactive stack, content is supplied as a `Publisher<DataBuffer>` and the upload result is a `Mono<ObjectId>`:

~~~java
import org.bson.Document;
import org.bson.types.ObjectId;
import org.reactivestreams.Publisher;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.data.mongodb.gridfs.ReactiveGridFsOperations;
import reactor.core.publisher.Mono;

public final class ReactiveAttachmentWriter {

    private final ReactiveGridFsOperations operations;

    public ReactiveAttachmentWriter(
            ReactiveGridFsOperations operations) {
        this.operations = operations;
    }

    public Mono<ObjectId> upload(
            Publisher<DataBuffer> content,
            String filename,
            String caseId) {

        Document metadata = new Document("caseId", caseId)
            .append("category", "contract");

        return operations.store(
            content,
            filename,
            "application/pdf",
            metadata
        );
    }
}
~~~

Differences from `GridFsOperations.store(InputStream, ...)`:

- **Do not call `block()`** in normal WebFlux request threads.
- `Mono` is cold/lazy by subscription semantics: a method returning `Mono<ObjectId>` has not yet executed the upload unless subscribed.
- DataBuffers/streams have their own lifecycle. When integrating with `FilePart.content()` in WebFlux, ensure the publisher is consumed exactly once and buffers are released according to the API contract.
- Large uploads require request size limits, timeouts, memory bounds, backpressure, and handling client disconnects.

### 9.2. The reactive API does not return synchronous GridFsResource

In the reactive API, `find`, `getResource`, and `getResources` use reactive types such as `Mono` and `Flux` with `ReactiveGridFsResource`. For example:

~~~java
import reactor.core.publisher.Flux;
import org.springframework.data.mongodb.gridfs.ReactiveGridFsOperations;
import org.springframework.data.mongodb.gridfs.ReactiveGridFsResource;

public Flux<ReactiveGridFsResource> findTextFiles(
        ReactiveGridFsOperations operations) {

    return operations.getResources("*.txt");
}
~~~

When building a reactive HTTP download endpoint, stream content from `ReactiveGridFsResource` into the response per your Spring Framework version's API, handling `DataBuffer`, filename/content-type headers, and proper subscription cancellation. Do not force `Flux<DataBuffer>` into a large `byte[]` just to fit a synchronous API.

## 10. Choosing a configuration style based on needs

| Need | Recommendation | Reason |
| --- | --- | --- |
| Single `fs` bucket or globally configured bucket | Boot auto-configuration, inject `GridFsOperations` | Minimal boilerplate |
| Single bucket with a fixed custom name | Declare one `GridFsTemplate` bean explicitly | Explicit bucket naming |
| Multiple file types across separate buckets | Multiple beans + `@Qualifier` | Avoids namespace confusion |
| GridFS database different from business document database | Dedicated factory or matching Boot property | Separates databases and credentials |
| End-to-end WebFlux application | `ReactiveGridFsOperations` | Prevents blocking I/O on the event loop |
| Multi-tenant with per-request bucket switching | Explicit supplier/factory design and delegation | Avoids mutable singletons and data leaks |
| Simpler service unit testing | Inject the `GridFsOperations` interface | Easy to mock and simulate errors |
| Low-level BSON/chunk manipulation | Direct MongoDB GridFS driver in a dedicated layer | Template does not cover every driver option |

Choose **interfaces at service boundaries**. When multiple beans exist, use meaningful bean names and qualifiers such as `contractsGridFs` instead of generic names like `template1`.

## 11. Testing configuration and the upload–download cycle

### 11.1. Unit tests and integration tests verify different things

A service unit test using a mocked `GridFsOperations` can verify that the code calls `store` with the right metadata and reacts to errors. It **does not prove** that the driver created the right bucket or that uploaded bytes can be downloaded back.

Only integration tests against a real MongoDB instance or Testcontainers verify:

- Correct database, bucket, and credentials connection.
- Proper metadata serializer behavior.
- `store` returns an `ObjectId` and `findOne` locates it.
- Downloaded bytes match uploaded bytes.
- `delete` removes both the created file and its associated chunks.

Do not use mocks as proof that GridFS collections exist.

### 11.2. Integration test example for a dedicated bucket

Illustrative example for a Spring Boot application with a `GridFsOperations` bean pointing to a test database/bucket. This test **writes and deletes data**, so never point it at a production database.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import com.mongodb.client.gridfs.model.GridFSFile;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.gridfs.GridFsOperations;
import org.springframework.data.mongodb.gridfs.GridFsResource;

@SpringBootTest
class GridFsRoundTripIT {

    @Autowired
    private GridFsOperations gridFs;

    @Test
    void uploadDownloadAndDelete() throws Exception {
        byte[] original = "hello-gridfs".getBytes(
            StandardCharsets.UTF_8);

        ObjectId id;
        try (InputStream in = new ByteArrayInputStream(original)) {
            id = gridFs.store(
                in,
                "sample.txt",
                "text/plain",
                new Document("testRun", "gridfs-lesson")
            );
        }

        Query byId = new Query(Criteria.where("_id").is(id));

        try {
            GridFSFile file = gridFs.findOne(byId);
            assertNotNull(file);

            GridFsResource resource = gridFs.getResource(file);
            byte[] actual;

            try (InputStream in = resource.getInputStream()) {
                actual = in.readAllBytes();
            }

            assertTrue(Arrays.equals(original, actual));
        } finally {
            gridFs.delete(byId);
        }

        assertNull(gridFs.findOne(byId));
    }
}
~~~

The test uses Java 9+ for `InputStream.readAllBytes()`. If the project defines multiple `GridFsOperations` beans, replace `@Autowired` with `@Autowired @Qualifier("...")` accordingly or configure the test to expose a single bean. Do not use a file's display sequence number in place of `ObjectId`.

Also test negative cases such as invalid metadata, connection failures, nonexistent files, interrupted uploads, and permission checks if those are risks in your system. For tests involving sensitive data, do not log file contents.

## 12. Common configuration errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `NoSuchBeanDefinitionException: GridFsOperations` | Missing starter or auto-config inactive | Check dependencies/bean configuration and Boot conditions |
| `NoUniqueBeanDefinitionException` | Multiple `GridFsOperations` beans of the same type | Specify `@Qualifier` or one `@Primary` bean |
| Upload succeeds but `fs.files` is empty | Using a different bucket or different database | Check actual bucket name and database |
| `findOne` returns `null` | Wrong ID, query, bucket/database, or file already deleted | Verify `fileId` and namespace; do not infer by filename |
| Downloaded file differs from original | Wrong stream sent, closed early, or transformed outside GridFS | Verify byte-for-byte from upload to download |
| `MongoSecurityException` thrown | Credentials/role lack permissions on bucket | Check read/write/delete roles on the target database |
| Java metadata differs from expectations | Converter/custom conversion and serialization | Inspect `MongoConverter`, BSON, and metadata schema |
| WebFlux endpoint stalls | Calling blocking API on the event loop | Use `ReactiveGridFsOperations` or isolate blocking I/O properly |
| Duplicate filenames cause wrong version reads | GridFS does not treat filename as a unique key | Use `fileId` + version in the business document |
| Memory spike on upload/download | Loading full file into RAM or buffering at the HTTP layer | Keep streaming, limit buffers and concurrency |
| File has metadata but misses some chunks | Abnormal operation error, incomplete write, or manual tampering | Use the GridFS driver properly; check consistency and cleanup workflows |

### 12.1. “Uploaded” but business data not yet updated

A workflow has two operations:

~~~text
1. GridFS store(file) -> fileId
2. MongoRepository.save(caseDocument.attach(fileId))
~~~

If step 1 succeeds but step 2 fails, GridFS may retain a file referenced by no business document. If you update the business document first and upload afterward, the document risks pointing to a nonexistent file. Do not treat two independent commands as one atomic transaction simply because both target MongoDB.

Practical handling can include:

1. Upload and obtain `fileId`.
2. Write the `fileId` link into the business document with version/authorization checks.
3. If linking fails, record the temporary/orphan file for deletion via an idempotent workflow.
4. On worker restart, reconcile files lacking valid references.
5. For high consistency requirements, study transaction/driver limits and suitable compensation workflows; never assume “GridFS is always in the same transaction as repositories.”

### 12.2. Security and operations

- **Enforce download authorization at the business layer** based on case/tenant/fileId; knowing an `ObjectId` does not grant download rights.
- **Do not trust client-supplied filenames** to build local file paths. When returning HTTP responses, set safe `Content-Disposition`/content types, prevent header injection, and handle dangerous files per policy.
- **Do not log binary contents or credentials**. Selectively observe size, bucket, latency, success/failure, and trace IDs.
- Monitor concurrent upload counts, connection pools, transfer durations, and chunk creation rates. Ensure backups/restores cover both `<bucket>.files` and `<bucket>.chunks`, not only metadata.
- Confirm deletion, retention, and reconciliation policies between business documents and GridFS before going to production.

## 13. Complete configuration exercise

Suppose an application stores contracts in `document_store`, bucket `contracts`:

1. Configure the MongoDB connection and verify `MongoDatabaseFactory` and `MongoConverter` are available.
2. Declare `@Bean("contractsGridFs")` returning `new GridFsTemplate(factory, converter, "contracts")`.
3. Inject it via `@Qualifier("contractsGridFs")` in `ContractFileService`.
4. Upload a sample PDF using `store(InputStream, "contract.pdf", "application/pdf", metadata)`.
5. Save `fileId` into the business case document. Look up the file by `_id` and read it back via `getResource(GridFSFile)`.
6. In `mongosh`, verify `contracts.files` contains metadata and `contracts.chunks` contains data.
7. Verify downloaded data matches the source file byte-for-byte and test duplicate-filename cases.
8. Delete **only the test fileId**, and observe that both the file and its chunks are cleaned up.
9. Add a bean for the `avatars` bucket and verify uploads across the two services do not cross namespaces.
10. If using WebFlux, rewrite the service with `ReactiveGridFsOperations` and verify there are no blocking operations on the event loop.

Questions for self-assessment:

- How does `GridFsOperations` differ from `GridFsTemplate`? Why inject the interface?
- When passing `MongoDatabaseFactory` and `MongoConverter`, what does each component determine?
- Why is `"contracts"` a bucket rather than a database?
- If two `GridFsOperations` beans exist, how should a service constructor select the right bean?
- Why can calling `findOne` by filename cause an application to download the wrong file?
- When upload succeeds but saving the `fileId` link fails, how should the application resolve orphan files?
- Why does a unit test with mocks not prove the GridFS configuration is actually correct?
- When WebFlux receives large files, why are `Mono<ObjectId>` and `Publisher<DataBuffer>` better than reading an entire `byte[]`?

## 14. Summary

When configuring **GridFS** in Spring Data MongoDB, start with **database factory + converter + bucket**. Use **`GridFsOperations`** as the interaction contract and **`GridFsTemplate`** as the synchronous implementation. Spring Boot can provide a default bean; when multiple buckets or specialized configurations are needed, define beans explicitly and select them with `@Qualifier`.

For reactive applications, use **`ReactiveGridFsOperations` / `ReactiveGridFsTemplate`** to keep upload/download flows asynchronous. Regardless of stack, identify files by **fileId**, manage input/output streams across their proper lifecycle, validate metadata and permissions, run upload–download integration tests, and maintain a cleanup policy for unreferenced files.

### References

- [Spring Data MongoDB — GridFS Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-gridfs.html)
- [GridFsOperations API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/gridfs/GridFsOperations.html)
- [GridFsTemplate API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/gridfs/GridFsTemplate.html)
- [ReactiveGridFsTemplate API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/gridfs/ReactiveGridFsTemplate.html)
- [MongoDB Manual — GridFS](https://www.mongodb.com/docs/manual/core/gridfs/)
