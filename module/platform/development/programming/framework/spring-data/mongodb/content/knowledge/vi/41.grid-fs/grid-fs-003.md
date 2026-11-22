# Cấu hình GridFsTemplate và GridFsOperations

## 1. Vì sao ứng dụng Spring Data MongoDB cần cấu hình GridFS?

Giả sử một hệ thống xử lý hồ sơ cần lưu file PDF hợp đồng, ảnh chụp tài liệu và bản xuất báo cáo. Dữ liệu nghiệp vụ như mã hồ sơ, trạng thái xử lý, người duyệt có thể lưu bằng document MongoDB thông thường. Nhưng file có thể lớn hơn giới hạn kích thước một document BSON (thông thường **16 MiB**) hoặc cần được đọc/ghi dạng luồng. MongoDB cung cấp **GridFS** để chia file thành nhiều chunk và lưu metadata liên quan.

Trong phạm vi **SPRING_DATA_MONGODB**, ta cần kết nối MongoDB, ánh xạ metadata, thao tác bằng template hoặc repository, đồng thời kiểm soát truy vấn, reactive access, kiểm thử và hiệu năng. Đối với file GridFS, hai thành phần quan trọng của Spring Data MongoDB là:

- `GridFsOperations`: **interface** biểu diễn hợp đồng lưu, tìm kiếm, truy xuất `Resource` và xóa file.
- `GridFsTemplate`: **implementation đồng bộ (imperative)** của `GridFsOperations`, sử dụng MongoDB Java Driver để làm việc với GridFS.
- `ReactiveGridFsOperations` và `ReactiveGridFsTemplate`: cặp interface/implementation tương ứng cho luồng reactive.

Một cấu hình cơ bản cần biết **database**, **bucket** và **MongoConverter**:

~~~text
Spring service
    |
    +---- GridFsOperations (interface)
                |
                v
          GridFsTemplate
                |-- MongoDatabaseFactory --> MongoDB database
                |-- MongoConverter -------> chuyển metadata Java <-> BSON
                +-- bucket "fs" (mặc định)
                        |-- fs.files  : tên, độ dài, uploadDate, metadata...
                        +-- fs.chunks : các phần dữ liệu nhị phân
~~~

Ví dụ với bucket `attachments` thì hai collection được dùng là `attachments.files` và `attachments.chunks`. Các collection của GridFS không giống một `@Document` entity chỉ ánh xạ vào một collection.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `GridFsOperations` và `GridFsTemplate`, biết khi nào dùng phiên bản reactive.
2. Cấu hình GridFS trong Spring Boot hoặc khai báo bean tường minh với `MongoDatabaseFactory` và `MongoConverter`.
3. Chỉ định bucket, database và lựa chọn bean với `@Qualifier` khi có nhiều bucket.
4. Thực hiện `store`, `findOne`, `getResource`, `getResources` và `delete` với xử lý tài nguyên đúng.
5. Kiểm chứng dữ liệu trong `<bucket>.files` và `<bucket>.chunks`, viết một integration test nhỏ và xử lý lỗi cấu hình.
6. Hiểu các giới hạn về metadata, duplicate filename, truy vấn, upload thất bại và hiệu năng bộ nhớ.

## 2. Nền tảng: database, bucket, files và chunks

### 2.1. GridFS chia file như thế nào?

Một file được lưu trong một GridFS **bucket** có hai phần logic:

| Collection | Dữ liệu chính | Vai trò |
| --- | --- | --- |
| `<bucket>.files` | `_id`, `filename`, `length`, `chunkSize`, `uploadDate`, `metadata` | Một document mô tả mỗi file |
| `<bucket>.chunks` | `files_id`, `n`, `data` | Các chunk chứa bytes thực tế |

`files_id` của các chunk trỏ tới `_id` của file. `n` xác định thứ tự chunk trong file. Driver chịu trách nhiệm tách dữ liệu khi upload và ráp lại khi download; thông thường ứng dụng không cần tự thao tác với `*.chunks`.

~~~mermaid
flowchart LR
    A["PDF 2 MiB"] --> B["GridFsTemplate.store(InputStream, ...)"]
    B --> C["GridFSBucket"]
    C --> D["attachments.files: fileId, name, length, metadata"]
    C --> E["attachments.chunks: chunk 0, 1, 2, ..."]
    D --> F["findOne / getResource"]
    E --> F
    F --> G["InputStream trả bytes về caller"]
~~~

Bucket mặc định có tên `fs`, nên collection sẽ là `fs.files` và `fs.chunks`. Khi chọn bucket `attachments`, cặp tên tương ứng là `attachments.files` và `attachments.chunks`. Bucket là **namespace lưu trữ**, không phải một database mới.

### 2.2. Các thành phần Spring cần có

| Thành phần | Trách nhiệm | Ghi chú |
| --- | --- | --- |
| `MongoClient` | Mở kết nối đến MongoDB qua driver | Có thể do Spring Boot quản lý |
| `MongoDatabaseFactory` | Cấp MongoDB database cho thao tác đồng bộ | Phụ thuộc cấu hình kết nối |
| `MongoConverter` | Ánh xạ metadata Java/BSON | Thường dùng `MappingMongoConverter` |
| `GridFsTemplate` | Thực hiện các lệnh GridFS đồng bộ | Cài đặt `GridFsOperations` |
| `GridFsOperations` | API cho service, thuận tiện DI và mock | Nên inject theo interface |
| `ReactiveMongoDatabaseFactory` | Cấp database trong reactive stack | Dùng với reactive driver |
| `ReactiveGridFsTemplate` | Thực hiện GridFS reactive | Cài đặt `ReactiveGridFsOperations` |

**Không cần tạo repository MongoDB cho từng file GridFS** để sử dụng các API này. Repository vẫn hữu ích để quản lý document nghiệp vụ riêng (ví dụ `attachments` chứa `caseId`, `fileId`, quyền truy cập), còn bytes được GridFS lưu qua bucket.

## 3. Chuẩn bị dependencies và kết nối

Ví dụ sử dụng Spring Boot với MongoDB và ứng dụng Java hiện đại. Với **Maven**, phụ thuộc chính cho thao tác đồng bộ là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Hoặc dùng **Gradle**:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
~~~

Kết nối MongoDB trong `application.properties` theo cấu hình Spring Boot tương ứng:

~~~properties
spring.data.mongodb.uri=mongodb://localhost:27017/document_store
~~~

Ví dụ trên áp dụng quy ước cấu hình của các dòng Spring Boot 3.x. Với Spring Boot thế hệ khác, đối chiếu namespace property của đúng phiên bản trước khi sao chép.

URI chỉ cấu hình database mà ứng dụng dùng để truy cập; **nó không tự quyết định bucket nào được chọn khi tạo `GridFsTemplate`**, trừ khi các thuộc tính GridFS hoặc bean cụ thể làm điều đó.

Ứng dụng phải có quyền phù hợp để thao tác collection của bucket. Một user chỉ có quyền đọc thì không thể upload hoặc xóa file. Khi chạy thử, ưu tiên dùng database riêng như `document_store` và tài khoản theo nguyên tắc quyền tối thiểu.

### 3.1. Lựa chọn cấu hình

Có hai con đường phổ biến:

1. **Spring Boot auto-configuration**: khi điều kiện phù hợp và không có bean `GridFsOperations` do ứng dụng tự định nghĩa, Boot có thể cung cấp một `GridFsTemplate` mặc định.
2. **Bean tường minh**: tự khai báo `GridFsTemplate` khi cần bucket được chỉ định rõ, nhiều bucket, nhiều database hoặc kiểm soát wiring.

Không nên trộn cả hai cách một cách ngẫu nhiên: một bean do ứng dụng định nghĩa có thể làm auto-configuration **back off**. Vì vậy, nếu đã tự khai báo, hãy xác định rõ những bean `GridFsOperations` mà service thực sự dùng.

## 4. Phương án A: dùng GridFsOperations do Spring Boot cấu hình

Trong ứng dụng Spring Boot phù hợp, service chỉ cần inject interface:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.data.mongodb.gridfs.GridFsOperations;

@Service
public class DocumentStorageService {

    private final GridFsOperations gridFs;

    public DocumentStorageService(GridFsOperations gridFs) {
        this.gridFs = gridFs;
    }

    // Các thao tác store/find/getResource/delete được bổ sung ở phần 7.
}
~~~

Nếu muốn dùng bucket mặc định, tên sẽ là `fs`. Với dòng Spring Boot 3.x có hỗ trợ các thuộc tính GridFS, ta có thể cấu hình riêng:

~~~properties
spring.data.mongodb.uri=mongodb://localhost:27017/document_store
spring.data.mongodb.gridfs.bucket=attachments
~~~

Một số dòng Spring Boot cũng hỗ trợ thuộc tính chọn **database GridFS riêng** như `spring.data.mongodb.gridfs.database`. Cần kiểm tra tài liệu cấu hình của đúng phiên bản, vì namespace và điều kiện tự cấu hình có thể thay đổi.

**Kiểm tra bean ở thời điểm khởi động**: nếu Spring báo không có `GridFsOperations`, hãy kiểm tra dependency, auto-configuration và custom configuration. Nếu có nhiều bean mà không có `@Primary` hoặc `@Qualifier`, Spring có thể báo `NoUniqueBeanDefinitionException`.

Ưu điểm của cách này là service phụ thuộc vào hợp đồng `GridFsOperations`, thuận tiện thay implementation hoặc thay bằng mock trong unit test. Tuy nhiên, nếu cần kiểm soát chính xác nhiều bucket, khai báo riêng sẽ rõ hơn.

## 5. Phương án B: tạo bean GridFsTemplate tường minh

Constructor thường gặp nhất:

~~~java
new GridFsTemplate(mongoDatabaseFactory, mongoConverter)
~~~

và phiên bản chọn bucket cụ thể:

~~~java
new GridFsTemplate(mongoDatabaseFactory, mongoConverter, "attachments")
~~~

Ví dụ `@Configuration` chỉ dùng **một bean** quản lý bucket `attachments`:

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

Điểm cần hiểu:

- `MongoDatabaseFactory` lựa chọn database từ cấu hình MongoDB của ứng dụng.
- `MongoConverter` được framework quản lý và có thể tích hợp custom converters cho kiểu metadata.
- `"attachments"` là tên bucket. Với cấu hình này, driver sẽ thao tác trên `attachments.files` và `attachments.chunks`.
- Trả về `GridFsOperations` để service inject theo interface; object thực tế vẫn là `GridFsTemplate`.
- Một `GridFsTemplate` **không cần tạo mới cho mỗi upload**. Cấu hình bean singleton giúp tái sử dụng kết nối/cơ chế quản lý do Spring và driver đảm nhận.

Không tự tạo `MongoClient` và `MongoConverter` mới bên trong mỗi request. Điều đó có thể tạo pool kết nối dư thừa và làm metadata mapping không nhất quán.

### 5.1. Vai trò của MongoConverter đối với metadata

`GridFsTemplate.store(...)` nhận metadata kiểu `Object` hoặc `Document`. Khi truyền một Java object, template dùng `MongoConverter` để chuyển thành BSON. Ví dụ:

~~~java
public record AttachmentMetadata(
    String caseId,
    String uploader,
    String category
) {}
~~~

Khi upload:

~~~java
AttachmentMetadata metadata = new AttachmentMetadata(
    "CASE-2026-001",
    "user-123",
    "contract"
);
~~~

Lưu ý đây là **thông tin minh họa**. `MongoConverter` không thay xác thực và phân quyền nghiệp vụ. Dữ liệu metadata có thể cần kiểm tra schema, kiểu dữ liệu, tenant và quyền người dùng trước khi đưa vào GridFS. Nếu cần kiểm soát chính xác BSON, có thể truyền `org.bson.Document`:

~~~java
Document metadata = new Document("caseId", "CASE-2026-001")
    .append("category", "contract")
    .append("version", 1);
~~~

Không nên dựa vào Java class name làm API hợp đồng dữ liệu lâu dài. Khi metadata thay đổi cấu trúc, hãy xác định rõ version, migration và logic đọc lại.

## 6. Cấu hình nhiều bucket trong cùng database

Một tổ chức có thể muốn lưu file hợp đồng và ảnh hồ sơ trong các bucket khác nhau để quản lý riêng, ví dụ `contracts` và `avatars`.

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

Inject đúng bean bằng `@Qualifier`:

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

Cặp collection tương ứng:

~~~text
document_store
├── contracts.files
├── contracts.chunks
├── avatars.files
└── avatars.chunks
~~~

Nếu bạn inject chỉ theo `GridFsOperations` khi có hai bean và không có quy tắc chọn, Spring không biết nên dùng bean nào. `@Qualifier` là cách rõ ràng nhất, còn `@Primary` chỉ phù hợp nếu thực sự có một bucket mặc định.

### 6.1. Bucket không đồng nghĩa database

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

Nếu cần phân tách **database** hoặc kết nối MongoDB khác nhau, phải dùng `MongoDatabaseFactory` tương ứng (hoặc cơ chế auto-configuration riêng cho GridFS nếu phiên bản hỗ trợ). Chỉ truyền tham số `bucket = "contracts"` không chuyển dữ liệu qua database mới.

### 6.2. Vì sao không nên đổi bucket bằng cách sửa state của một singleton?

`GridFsTemplate` thường lấy `GridFSBucket` khi cần ở thao tác đầu tiên và **cache/reuse** bucket đó trong instance. Do vậy, thiết kế “đổi một property lúc runtime để cùng singleton tự chuyển sang bucket khác” dễ dẫn tới hành vi không như mong muốn.

Khi bucket cố định, nên có **mỗi bucket một template/bean**. Nếu thực sự cần chọn bucket động trên mỗi thao tác, API có constructor nhận `Supplier<GridFSBucket>` (ở các phiên bản hỗ trợ) và cần thiết kế rõ supplier, vòng đời và giới hạn quyền. Việc chọn bucket theo tenant phải kiểm tra định danh tenant từ nguồn tin cậy, không lấy trực tiếp tên bucket tùy ý từ request.

## 7. Sử dụng GridFsOperations: upload, đọc lại và xóa

### 7.1. Upload bằng InputStream

Ví dụ một service đồng bộ, nhận `InputStream` và trả về `ObjectId` của file mới:

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

        // Caller sở hữu InputStream; phải đóng ở nơi mở stream.
        // Đây là thao tác blocking.
        return gridFs.store(
            content,
            filename,
            "application/pdf",
            metadata
        );
    }
}
~~~

Ở đoạn trên, `GridFsOperations.store(InputStream, filename, contentType, metadata)` thực hiện upload và trả `ObjectId`. `store` không tạo file local: nó ghi các chunk lên MongoDB. **Đầu vào là stream**, không cần nạp toàn bộ file vào `byte[]` trước khi upload.

Hàm `savePdf` chỉ minh họa API, chưa kiểm tra nội dung thực sự là PDF. Trong ứng dụng production, kiểm tra giới hạn kích thước, loại file, virus/malware theo chính sách, quyền truy cập và nội dung filename. Không nên tin tuyệt đối MIME type do client gửi lên.

### 7.2. Ví dụ gọi upload từ một file local

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

Đoạn này là một ví dụ **caller** cho `GridFsFileWriter`, không phải một method đặt trực tiếp ở top-level của Java class. `try-with-resources` giúp đóng InputStream sau upload. Không giữ `InputStream` trong một Spring singleton.

### 7.3. Tìm file bằng GridFS query

Giả sử cần tra file theo `fileId` để lấy đúng phiên bản:

~~~java
import com.mongodb.client.gridfs.model.GridFSFile;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

ObjectId id = new ObjectId("690000000000000000000001");

Query query = new Query(Criteria.where("_id").is(id));
GridFSFile file = gridFs.findOne(query);

if (file == null) {
    throw new IllegalArgumentException("Khong tim thay file: " + id);
}
~~~

`GridFsOperations.findOne(Query)` trả về `GridFSFile` hoặc `null`. Một request download nên tra cứu theo **ID đã lưu trong hồ sơ nghiệp vụ**, sau khi kiểm tra user có quyền truy cập hồ sơ đó.

Không mặc định filename là duy nhất: GridFS cho phép **nhiều file cùng filename**. Nếu `findOne` theo filename, kết quả có thể không phải phiên bản mà caller mong muốn.

Spring Data có helper dành riêng cho metadata và tên file:

~~~java
import static org.springframework.data.mongodb.gridfs.GridFsCriteria.whereFilename;

Query byName = new Query(whereFilename().is("sample-contract.pdf"));

GridFSFile found = gridFs.findOne(byName);
~~~

Để tìm theo metadata, có thể dùng `GridFsCriteria.whereMetaData("caseId")`. Việc thêm `Sort` vào `Query` không được GridFS template áp dụng như truy vấn MongoDB thông thường; không thiết kế nghiệp vụ dựa vào “file mới nhất” chỉ bằng `Query.with(Sort...)` ở API này. Nên quản lý version/fileId trong entity riêng.

### 7.4. Đọc bytes qua GridFsResource

Sau khi có `GridFSFile`:

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

`getResource(GridFSFile)` trả `GridFsResource`, cho phép lấy `InputStream`, filename, content length và một số metadata. `InputStream` là tài nguyên cần đóng. Ví dụ dùng `transferTo` trong Java 9+; với Java cũ có thể copy bằng buffer nhỏ.

Không trả `InputStream` ra khỏi một method đã đóng nó. Nếu triển khai HTTP download, phải giữ stream mở trong suốt quá trình response được ghi, xử lý client disconnect và giới hạn số kết nối đồng thời.

### 7.5. getResource theo filename và getResources theo pattern

Spring Data cung cấp:

~~~java
GridFsResource byFilename =
    gridFs.getResource("sample-contract.pdf");

GridFsResource[] textFiles =
    gridFs.getResources("*.txt");
~~~

`GridFsOperations` mở rộng `ResourcePatternResolver`, vì vậy có thể chọn file qua pattern tên. Dù vậy, `getResource(String)` dựa trên tên **không giải quyết vấn đề version/duplicate filename**. Không nên dùng nó làm đường tải hợp đồng quan trọng nếu ứng dụng đã lưu `fileId`.

Nếu không tìm thấy filename, hãy kiểm tra `resource.exists()` trước khi gọi `getInputStream()`. Với kết quả pattern, mảng có thể rỗng.

### 7.6. Xóa file đúng phạm vi

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public void deleteById(GridFsOperations gridFs, ObjectId id) {
    Query byId = new Query(Criteria.where("_id").is(id));
    gridFs.delete(byId);
}
~~~

`delete(Query)` xóa **tất cả file khớp query** cùng các chunk của chúng. Nếu truyền một query rộng hoặc query chỉ theo filename trùng lặp, có thể xóa nhiều file ngoài ý muốn. Bảo đảm bước kiểm tra authorization, fileId và nghiệp vụ retention đã hoàn tất trước khi gọi xóa; không cho phép gọi `delete(new Query())` trực tiếp từ API người dùng.

## 8. Kiểm chứng cấu hình bằng mongosh

Sau khi upload đầu tiên, mở `mongosh` để xác nhận bucket và metadata:

~~~javascript
use document_store

show collections

// Ví dụ cấu hình bucket "attachments":
db.getCollection("attachments.files")
  .find(
    {},
    { filename: 1, length: 1, uploadDate: 1, metadata: 1 }
  )
  .limit(5)

// Chọn một file và kiểm tra có các chunk tương ứng:
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

Nếu MongoDB driver/mongosh đang dùng cách biểu diễn `Binary` khác, việc đo bytes bằng `c.data.length()` có thể cần điều chỉnh theo API tương ứng. Mục đích quan trọng là kiểm tra **`files_id` và `n`** khớp với file đã upload.

Dữ liệu phải nằm ở **database và bucket mà bean được cấu hình**. Nếu upload trả ID nhưng người vận hành không thấy `fs.files`, hãy kiểm tra có thực ra ứng dụng đang dùng bucket `attachments` hoặc database khác.

### 8.1. Checklist nhanh ở thời điểm chạy

1. MongoDB có thể kết nối bằng đúng URI và credential.
2. Spring context có một bean `GridFsOperations` phù hợp, hoặc các bean được chọn bằng `@Qualifier`.
3. Bean nhận đúng `MongoDatabaseFactory` và `MongoConverter`.
4. Bucket đang dùng khớp với `<bucket>.files` / `<bucket>.chunks` dự định.
5. Upload một file nhỏ trả `fileId`; `findOne` theo ID trả file; `getResource` đọc bytes giống đầu vào.
6. Thử xóa file vừa tạo trong **database test**, kiểm tra file và chunks không còn.

## 9. Cấu hình ReactiveGridFsTemplate khi ứng dụng dùng WebFlux

Nếu dự án sử dụng reactive MongoDB, dùng `ReactiveGridFsOperations` thay cho interface đồng bộ; implementation là `ReactiveGridFsTemplate`. Không gọi các phương thức blocking của `GridFsOperations` trực tiếp trên Netty event-loop.

Phụ thuộc reactive:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
~~~

Khai báo bucket riêng:

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

Đây là một **phương án cấu hình thay thế** cho ứng dụng reactive. Không cần tạo cả bean đồng bộ và reactive nếu chỉ sử dụng một mô hình.

### 9.1. Lưu file bằng Publisher<DataBuffer>

Trong reactive stack, nội dung được cung cấp dưới dạng `Publisher<DataBuffer>` và kết quả upload là `Mono<ObjectId>`:

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

Điểm khác biệt so với `GridFsOperations.store(InputStream, ...)`:

- **Không gọi `block()`** trong luồng xử lý WebFlux thông thường.
- `Mono` là cold/lazy theo cơ chế subscription: phương thức trả `Mono<ObjectId>` chưa tự thực hiện upload nếu không có subscriber.
- DataBuffer/stream có vòng đời riêng. Khi tích hợp với `FilePart.content()` trong WebFlux, cần bảo đảm publisher được tiêu thụ đúng một lần và giải phóng buffer theo hợp đồng API sử dụng.
- Upload lớn cần chính sách giới hạn request size, timeout, memory, backpressure và xử lý khi client hủy kết nối.

### 9.2. API reactive không trả GridFsResource đồng bộ

Ở reactive API, các phương thức `find`, `getResource` và `getResources` sử dụng các kiểu reactive như `Mono` và `Flux` cùng `ReactiveGridFsResource`. Chẳng hạn:

~~~java
import reactor.core.publisher.Flux;
import org.springframework.data.mongodb.gridfs.ReactiveGridFsOperations;
import org.springframework.data.mongodb.gridfs.ReactiveGridFsResource;

public Flux<ReactiveGridFsResource> findTextFiles(
        ReactiveGridFsOperations operations) {

    return operations.getResources("*.txt");
}
~~~

Khi xây HTTP endpoint download reactive, cần chuyển luồng nội dung từ `ReactiveGridFsResource` sang response theo API của phiên bản Spring Framework, xử lý `DataBuffer`, header filename/content type và hủy subscription đúng. Không ép `Flux<DataBuffer>` thành `byte[]` lớn chỉ để tương thích với API đồng bộ.

## 10. Lựa chọn kiểu cấu hình theo nhu cầu

| Nhu cầu | Gợi ý | Lý do |
| --- | --- | --- |
| Một bucket `fs` hoặc bucket cấu hình chung | Boot auto-configuration, inject `GridFsOperations` | Ít boilerplate |
| Một bucket có tên cố định | Tự khai báo một `GridFsTemplate` | Chủ động tên bucket |
| Nhiều loại file ở các bucket khác nhau | Nhiều bean + `@Qualifier` | Không nhầm namespace |
| Cần database GridFS khác database document nghiệp vụ | Factory dành riêng hoặc thuộc tính Boot tương ứng | Tách database, kiểm soát credential |
| Ứng dụng WebFlux end-to-end | `ReactiveGridFsOperations` | Hạn chế blocking I/O trên event-loop |
| Nhiều tenant, bucket đổi theo request | Thiết kế rõ supplier/factory và ủy quyền | Tránh dùng mutable singleton và rò dữ liệu |
| Đơn giản hóa unit test service | Inject interface `GridFsOperations` | Dễ mock, mô phỏng lỗi |
| Cần thao tác BSON/chunks mức thấp | MongoDB GridFS driver trực tiếp ở lớp chuyên dụng | Template không bao quát mọi tùy chọn driver |

Nên chọn **interface ở ranh giới service**. Khi có nhiều bean, dùng tên bean và qualifier có ý nghĩa nghiệp vụ, ví dụ `contractsGridFs`, thay vì tên chung `template1`.

## 11. Kiểm thử cấu hình và vòng upload–download

### 11.1. Unit test và integration test kiểm tra điều khác nhau

Unit test của service dùng mock `GridFsOperations` có thể xác nhận code gọi `store` với metadata đúng và phản ứng với lỗi. Nó **không chứng minh** driver đã tạo đúng bucket hay bytes upload có thể tải lại.

Integration test với MongoDB thật hoặc Testcontainers mới kiểm tra được:

- Nối đúng database, bucket và credential.
- Serializer của metadata hoạt động đúng.
- `store` trả `ObjectId`, `findOne` tìm lại được.
- Bytes tải xuống giống bytes upload.
- `delete` xóa đúng file đã tạo và các chunk liên quan.

Không dùng mock làm bằng chứng các collection GridFS đã tồn tại.

### 11.2. Ví dụ integration test cho một bucket riêng

Ví dụ minh họa cho ứng dụng Spring Boot đã có bean `GridFsOperations` trỏ tới database/bucket thử nghiệm. Test này **ghi và xóa dữ liệu**, nên tuyệt đối không chĩa nó vào database production.

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

Test dùng Java 9+ cho `InputStream.readAllBytes()`. Nếu dự án có nhiều bean `GridFsOperations`, thay `@Autowired` bằng `@Autowired @Qualifier("...")` tương ứng hoặc cấu hình test để chỉ có một bean. Không dùng số thứ tự hiển thị của file thay `ObjectId`.

Cần kiểm tra thêm negative cases như metadata sai, lỗi kết nối, file không tồn tại, upload bị ngắt và kiểm tra quyền, nếu đó là rủi ro của hệ thống. Với test có dữ liệu nhạy cảm, không nên xuất nội dung vào log.

## 12. Lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException: GridFsOperations` | Thiếu starter hoặc auto-config không kích hoạt | Kiểm tra dependencies/bean configuration và điều kiện Boot |
| `NoUniqueBeanDefinitionException` | Nhiều bean `GridFsOperations` cùng kiểu | Chỉ định `@Qualifier` hoặc một bean `@Primary` |
| Upload thành công nhưng không thấy `fs.files` | Đang dùng bucket khác hoặc database khác | Kiểm tra tên bucket và database thực tế |
| `findOne` trả `null` | Sai ID, query, bucket/database hoặc file đã bị xóa | Kiểm tra `fileId` và namespace; không suy theo filename |
| File được tải về nhưng khác bản gốc | Gửi sai stream, bị đóng sớm hoặc áp dụng biến đổi ngoài GridFS | Kiểm chứng byte-for-byte từ upload tới download |
| Nhận `MongoSecurityException` | Credential/role thiếu quyền trên bucket | Kiểm tra quyền đọc/ghi/xóa ở database được dùng |
| Metadata Java không giống kỳ vọng | Converter/custom conversion và cách serialize | Kiểm tra `MongoConverter`, BSON và schema metadata |
| WebFlux endpoint bị nghẽn | Gọi API blocking trên event-loop | Dùng `ReactiveGridFsOperations` hoặc cô lập I/O blocking đúng cách |
| Trùng filename dẫn đến đọc nhầm phiên bản | GridFS không coi filename là khóa duy nhất | Dùng `fileId` + version trong document nghiệp vụ |
| Memory spike khi upload/download | Nạp toàn file vào RAM hoặc buffering ở HTTP layer | Giữ dạng stream, giới hạn buffer và concurrency |
| File còn metadata nhưng thiếu một số chunks | Lỗi thao tác bất thường, viết chưa hoàn tất hoặc dữ liệu bị can thiệp | Dùng driver GridFS đúng cách; kiểm tra consistency và quy trình cleanup |

### 12.1. “Đã upload” nhưng dữ liệu nghiệp vụ chưa cập nhật

Một workflow có hai thao tác:

~~~text
1. GridFS store(file) -> fileId
2. MongoRepository.save(caseDocument.attach(fileId))
~~~

Nếu bước 1 thành công nhưng bước 2 thất bại, GridFS có thể còn file không được document nghiệp vụ nào tham chiếu. Nếu cập nhật nghiệp vụ trước rồi upload sau, lại có nguy cơ document trỏ tới file chưa tồn tại. Không coi hai lệnh độc lập là một tác vụ nguyên tử chỉ vì cùng MongoDB.

Cách xử lý thực tế có thể gồm:

1. Upload và nhận `fileId`.
2. Ghi liên kết `fileId` vào document nghiệp vụ với kiểm tra version/authorization.
3. Nếu bước liên kết lỗi, ghi nhận file tạm/orphan để xóa bằng quy trình idempotent.
4. Khi khởi động lại worker, reconcile những file chưa có liên kết hợp lệ.
5. Với yêu cầu tính nhất quán cao, nghiên cứu giới hạn transaction/driver và quy trình bù trừ phù hợp; không mặc định “GridFS luôn nằm trong một transaction với repository”.

### 12.2. Bảo mật và vận hành

- **Phân quyền tải file tại tầng nghiệp vụ** dựa trên hồ sơ/tenant/fileId; biết `ObjectId` không đồng nghĩa có quyền tải.
- **Không tin filename do client đưa vào** để tạo đường dẫn file local. Khi trả HTTP response, đặt `Content-Disposition`/content type an toàn, tránh header injection và xử lý file nguy hiểm theo chính sách.
- **Không log nội dung nhị phân hoặc credential**. Quan sát size, bucket, latency, success/failure và trace ID có chọn lọc.
- Theo dõi số lượng upload đồng thời, connection pool, thời gian truyền và tốc độ tạo chunks. Xem xét backup/restore cả `<bucket>.files` và `<bucket>.chunks`, không chỉ metadata.
- Xác nhận chính sách xóa, retention và đối soát giữa document nghiệp vụ với GridFS trước khi đưa hệ thống vào production.

## 13. Bài thực hành cấu hình hoàn chỉnh

Giả sử ứng dụng lưu hợp đồng ở `document_store`, bucket `contracts`:

1. Cấu hình kết nối MongoDB và xác minh `MongoDatabaseFactory`, `MongoConverter` có sẵn.
2. Khai báo `@Bean("contractsGridFs")` trả `new GridFsTemplate(factory, converter, "contracts")`.
3. Inject qua `@Qualifier("contractsGridFs")` trong `ContractFileService`.
4. Upload một file PDF mẫu bằng `store(InputStream, "contract.pdf", "application/pdf", metadata)`.
5. Lưu `fileId` vào document hồ sơ nghiệp vụ. Tra cứu file bằng `_id`, đọc lại qua `getResource(GridFSFile)`.
6. Trên `mongosh` kiểm tra `contracts.files` có metadata, `contracts.chunks` có dữ liệu.
7. Xác minh dữ liệu tải về khớp byte-for-byte với file nguồn và thử case tên file trùng nhau.
8. Xóa **đúng fileId thử nghiệm**, quan sát cả file và chunks liên quan đã được dọn.
9. Mở thêm bean bucket `avatars`, kiểm tra upload của hai service không lẫn namespace.
10. Nếu dùng WebFlux, viết lại service bằng `ReactiveGridFsOperations` và xác nhận không có blocking operations trên event-loop.

Câu hỏi để tự đánh giá:

- `GridFsOperations` khác `GridFsTemplate` ở điểm nào? Vì sao nên inject interface?
- Khi truyền `MongoDatabaseFactory` và `MongoConverter`, từng thành phần quyết định điều gì?
- Vì sao `"contracts"` là bucket chứ không phải database?
- Nếu có hai `GridFsOperations` bean thì constructor của service nên chọn bean nào?
- Vì sao dùng `findOne` theo filename có thể khiến ứng dụng tải sai file?
- Khi upload thành công nhưng lưu liên kết `fileId` thất bại, ứng dụng sẽ giải quyết file orphan ra sao?
- Vì sao một unit test với mock chưa chứng minh cấu hình GridFS thực sự đúng?
- Nếu WebFlux nhận file lớn, vì sao `Mono<ObjectId>` và `Publisher<DataBuffer>` hữu ích hơn việc đọc toàn bộ `byte[]`?

## 14. Tổng kết

Khi cấu hình **GridFS** trong Spring Data MongoDB, hãy bắt đầu từ **database factory + converter + bucket**. Dùng **`GridFsOperations`** làm hợp đồng tương tác, và **`GridFsTemplate`** làm implementation đồng bộ. Spring Boot có thể cung cấp bean mặc định; khi cần nhiều bucket hoặc cấu hình chuyên biệt, tự tạo bean và chọn bằng `@Qualifier`.

Đối với ứng dụng reactive, dùng **`ReactiveGridFsOperations` / `ReactiveGridFsTemplate`** để giữ luồng upload/download bất đồng bộ. Dù ở stack nào, hãy định danh file bằng **fileId**, quản lý input/output streams đúng vòng đời, kiểm tra metadata và permissions, thực hiện integration test upload–download và có chính sách dọn file không còn tham chiếu.

### Tài liệu tham khảo

- [Spring Data MongoDB — GridFS Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-gridfs.html)
- [GridFsOperations API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/gridfs/GridFsOperations.html)
- [GridFsTemplate API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/gridfs/GridFsTemplate.html)
- [ReactiveGridFsTemplate API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/gridfs/ReactiveGridFsTemplate.html)
- [MongoDB Manual — GridFS](https://www.mongodb.com/docs/manual/core/gridfs/)

