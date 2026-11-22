# GridFsResource và cung cấp nội dung cho tầng ứng dụng

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_DATA_MONGODB**, chúng ta sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua MongoTemplate hoặc repository; đồng thời học truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu. Riêng chương **GridFS** giải quyết nhu cầu lưu trữ và truy xuất nội dung tệp trong MongoDB.

Hãy hình dung một ứng dụng quản lý hồ sơ: thông tin nghiệp vụ của tài liệu nằm trong collection thông thường, còn nội dung PDF, hình ảnh hoặc tệp đính kèm được lưu bằng GridFS. Khi người dùng bấm **Tải xuống**, ứng dụng phải tìm đúng tệp, kiểm tra quyền truy cập, lấy dữ liệu nhị phân và trả về HTTP response có tên tệp, loại nội dung và kích thước thích hợp.

**GridFsResource** là cầu nối giữa dữ liệu GridFS và khái niệm **Resource** quen thuộc trong Spring Framework. Nhờ đó, tầng web và các dịch vụ xử lý tệp có thể tiêu thụ dữ liệu như một luồng thay vì tự ghép từng chunk thành mảng byte lớn.

Sau bài này, bạn có thể:

1. Phân biệt vai trò của GridFSFile, GridFsOperations, GridFsTemplate và GridFsResource.
2. Tra cứu tệp bằng định danh, lấy GridFsResource và cung cấp nội dung qua Spring MVC.
3. Thiết lập Content-Type, Content-Disposition, Content-Length và xử lý trường hợp tệp không tồn tại.
4. Đọc nội dung bằng InputStream an toàn, tránh tải toàn bộ tệp vào bộ nhớ.
5. Nhận biết khác biệt giữa cách đọc đồng bộ và ReactiveGridFsResource trong WebFlux.
6. Thiết kế kiểm thử, xử lý lỗi và bảo vệ endpoint tải tệp trong hệ thống thực tế.

## 2. GridFsResource nằm ở đâu trong kiến trúc?

GridFS thường lưu metadata tệp trong collection **fs.files** và dữ liệu nhị phân chia nhỏ trong **fs.chunks** (với bucket mặc định là fs). Một bản ghi GridFSFile biểu diễn thông tin về một tệp, chẳng hạn ID, tên tệp, chiều dài, ngày tải lên và metadata. Nó **không phải** toàn bộ nội dung nhị phân.

Các kiểu quan trọng:

| Thành phần | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| GridFSFile | Đối tượng metadata từ MongoDB Java Driver | Có ID, filename, length, uploadDate, metadata; không tự là HTTP response. |
| GridFsOperations | Giao diện thao tác GridFS của Spring Data | Cung cấp findOne, find, getResource, store, delete. |
| GridFsTemplate | Triển khai đồng bộ của GridFsOperations | Có thể được inject thông qua kiểu GridFsOperations. |
| GridFsResource | Resource dựa trên một GridFSFile | Cho phép lấy InputStream, tên, loại nội dung, độ dài và thông tin liên quan. |
| Resource | Trừu tượng tài nguyên của Spring Framework | Được các thành phần HTTP, dịch vụ và framework sử dụng rộng rãi. |
| ReactiveGridFsResource | Đại diện tệp cho luồng reactive | Cung cấp Flux<DataBuffer>; không cùng kiểu với Resource đồng bộ. |

Sơ đồ luồng tải xuống:

~~~mermaid
flowchart LR
    A[Client GET /api/files/id/content] --> B[Controller]
    B --> C[Kiểm tra xác thực và quyền]
    C --> D[Service]
    D --> E[GridFsOperations.findOne]
    E --> F[(fs.files)]
    D --> G[GridFsOperations.getResource]
    G --> H[GridFsResource]
    H --> I[(fs.chunks)]
    H --> J[Spring HTTP Resource converter]
    J --> K[HTTP response body]
~~~

Trong thực tế, driver chỉ đọc chunk dữ liệu khi luồng tải xuống được tiêu thụ. Đối tượng GridFsResource cho phép tầng ứng dụng giữ một tham chiếu tới nội dung; nó không có nghĩa là toàn bộ tệp đã được tải sẵn vào RAM.

### 2.1. Các API cần nắm

~~~java
// API đồng bộ, minh họa các thao tác cốt lõi.
GridFSFile file = gridFsOperations.findOne(query); // Có thể trả về null.
GridFsResource resource = gridFsOperations.getResource(file);

boolean available = resource.exists();
String filename = resource.getFilename();
String contentType = resource.getContentType(); // Có thể null.
long length = resource.contentLength();

// Chỉ mở luồng khi thực sự cần đọc; bên sử dụng phải đóng luồng.
try (InputStream input = resource.getInputStream()) {
    input.transferTo(output);
}
~~~

Lưu ý: đoạn trên giả định **file khác null**, **resource tồn tại**, biến **query** và **output** đã được khai báo. Đây là minh họa API; ví dụ hoàn chỉnh sẽ xuất hiện ở phần tiếp theo.

**GridFsResource kế thừa InputStreamResource**, nên tài nguyên và luồng đọc có đặc tính chỉ tiêu thụ một lần trong mỗi lượt xử lý. Không nên gọi getInputStream để kiểm tra thử rồi dùng chính đối tượng đó lần nữa cho HTTP response. Việc gọi contentLength trên GridFsResource có triển khai riêng phù hợp với kích thước tệp; trong ứng dụng, nếu đã có GridFSFile thì cũng có thể lấy kích thước bằng getLength.

### 2.2. Chọn tệp bằng filename hay ID?

Có hai cách lấy tài nguyên thường gặp:

~~~java
GridFsResource byName = gridFsOperations.getResource("report.pdf");

GridFSFile file = gridFsOperations.findOne(
    Query.query(Criteria.where("_id").is(fileObjectId))
);
GridFsResource byId = gridFsOperations.getResource(file);
~~~

getResource(String) tiện khi tên tệp là duy nhất theo quy ước ứng dụng. Tuy nhiên, GridFS cho phép nhiều tệp trùng filename (ví dụ các lần cập nhật). Với endpoint phục vụ người dùng, **định danh tệp** thường là lựa chọn rõ ràng hơn: tra cứu đúng GridFSFile, kiểm tra metadata và quyền truy cập, rồi lấy resource từ chính đối tượng đó. Nếu hệ thống có version, tenant hoặc trạng thái tài liệu, cần đưa các điều kiện tương ứng vào truy vấn hoặc kiểm tra nghiệp vụ trước khi trả nội dung.

## 3. Ví dụ đầy đủ: trả nội dung GridFS qua Spring MVC

Giả sử một ứng dụng Spring Boot đã cấu hình MongoDB, có Spring Web MVC và Spring Data MongoDB. Tệp được lưu trong bucket GridFS mặc định, với ID là MongoDB ObjectId. Endpoint cần cung cấp:

~~~text
GET /api/files/{id}/content

200 OK:    Nội dung tệp và các HTTP header tương ứng
400:       ID không đúng định dạng ObjectId
404:       Không tìm thấy tệp
500/503:   Sự cố lưu trữ hoặc đọc dữ liệu (xử lý/log ở tầng hạ tầng)
~~~

### 3.1. Tầng service: tìm metadata và lấy GridFsResource

~~~java
package example.files;

import java.util.NoSuchElementException;

import com.mongodb.client.gridfs.model.GridFSFile;
import org.bson.types.ObjectId;
import org.springframework.core.io.Resource;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.gridfs.GridFsOperations;
import org.springframework.data.mongodb.gridfs.GridFsResource;
import org.springframework.stereotype.Service;

@Service
public class GridFsDownloadService {

    private final GridFsOperations gridFs;

    public GridFsDownloadService(GridFsOperations gridFs) {
        this.gridFs = gridFs;
    }

    public DownloadFile load(String hexId) {
        // Ví dụ dùng ObjectId. Nếu hệ thống dùng ID kiểu khác, đổi chiến lược này.
        if (!ObjectId.isValid(hexId)) {
            throw new IllegalArgumentException("Invalid GridFS file id");
        }

        Query query = Query.query(
            Criteria.where("_id").is(new ObjectId(hexId))
        );

        GridFSFile file = gridFs.findOne(query);
        if (file == null) {
            throw new NoSuchElementException("GridFS file not found");
        }

        // Tại đây: đối chiếu quyền truy cập, tenant, trạng thái tài liệu...
        // Không chỉ dựa vào việc người gọi biết ID của tệp.

        GridFsResource resource = gridFs.getResource(file);
        if (!resource.exists()) {
            throw new NoSuchElementException("GridFS resource not found");
        }

        return new DownloadFile(
            resource,
            file.getLength(),
            file.getFilename(),
            resource.getContentType()
        );
    }

    public record DownloadFile(
        Resource resource,
        long length,
        String filename,
        String contentType
    ) {}
}
~~~

**Vì sao service trả một record thay vì byte[]?** Record chỉ mang resource và metadata cần thiết. Khi nhận đối tượng này, controller vẫn chưa phải gom hết nội dung tệp vào bộ nhớ. Việc đọc nội dung sẽ xảy ra ở bước ghi response.

**Vì sao lấy length từ GridFSFile?** Metadata đã được truy vấn, cho phép đặt Content-Length mà không cần mở và đọc InputStream. Khi lưu trữ đang thay đổi hoặc tệp bị xóa giữa các bước, việc stream vẫn có thể thất bại; đó là lỗi cần giám sát và xử lý ở tầng hạ tầng.

### 3.2. Tầng controller: tạo HTTP response

~~~java
package example.files;

import java.nio.charset.StandardCharsets;
import java.util.NoSuchElementException;

import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.InvalidMediaTypeException;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/files")
public class GridFsDownloadController {

    private final GridFsDownloadService service;

    public GridFsDownloadController(GridFsDownloadService service) {
        this.service = service;
    }

    @GetMapping("/{id}/content")
    public ResponseEntity<Resource> download(@PathVariable String id) {
        GridFsDownloadService.DownloadFile file;
        try {
            file = service.load(id);
        } catch (IllegalArgumentException exception) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid file id", exception
            );
        } catch (NoSuchElementException exception) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "File not found", exception
            );
        }

        String safeFilename = sanitizeFilename(file.filename());
        ContentDisposition disposition = ContentDisposition.attachment()
            .filename(safeFilename, StandardCharsets.UTF_8)
            .build();

        return ResponseEntity.ok()
            .contentType(resolveMediaType(file.contentType()))
            .contentLength(file.length())
            .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
            .header("X-Content-Type-Options", "nosniff")
            .cacheControl(CacheControl.noStore())
            .body(file.resource());
    }

    private static MediaType resolveMediaType(String raw) {
        if (raw == null || raw.isBlank()) {
            return MediaType.APPLICATION_OCTET_STREAM;
        }
        try {
            return MediaType.parseMediaType(raw);
        } catch (InvalidMediaTypeException exception) {
            return MediaType.APPLICATION_OCTET_STREAM;
        }
    }

    private static String sanitizeFilename(String filename) {
        if (filename == null || filename.isBlank()) {
            return "download";
        }

        // Chỉ hiển thị tên tệp cuối cùng, loại bỏ CR/LF trong tên từ metadata.
        String normalized = filename.replace('\\', '/');
        String basename = normalized.substring(normalized.lastIndexOf('/') + 1)
            .replace('\r', '_')
            .replace('\n', '_');
        return basename.isBlank() ? "download" : basename;
    }
}
~~~

Đây là ví dụ **đồng bộ với Spring MVC**. Ứng dụng thực tế cần triển khai kiểm tra quyền truy cập tại vị trí đã chú thích trong service, trước khi cho phép mở nội dung. Nếu API phục vụ tệp công khai và có chiến lược cache riêng, hãy điều chỉnh Cache-Control theo yêu cầu; ví dụ sử dụng no-store để tránh lưu tệp riêng tư ngoài ý muốn.

Một vài quyết định trong đoạn controller:

| Chi tiết | Tác dụng | Lưu ý |
| --- | --- | --- |
| ResponseEntity<Resource> | Để Spring ghi nội dung Resource ra response | Tránh tự đọc tất cả byte trong controller. |
| Content-Type | Báo loại nội dung cho client | Fallback về application/octet-stream nếu metadata thiếu hoặc sai. |
| Content-Disposition: attachment | Yêu cầu trình duyệt tải tệp | Có thể dùng inline cho ảnh/PDF được phép xem trực tiếp. |
| filename với UTF-8 | Hỗ trợ tên tệp tiếng Việt | Phải kiểm soát tên tệp đầu vào để tránh chèn header/path. |
| Content-Length | Thông báo số byte dự kiến | Dùng GridFSFile.getLength đã có. |
| X-Content-Type-Options: nosniff | Hạn chế trình duyệt tự suy đoán MIME | Hữu ích khi nội dung do người dùng tải lên. |
| Cache-Control: no-store | Hạn chế cache tệp nhạy cảm | Có thể thay bằng chính sách phù hợp mục đích. |
| 400 và 404 | Tách ID sai định dạng khỏi không tìm thấy | Cân nhắc chính sách che giấu sự tồn tại của tài nguyên khi phân quyền. |

Spring MVC dùng bộ chuyển đổi HTTP phù hợp để lấy luồng từ Resource rồi sao chép ra response. Không gọi getInputStream trước khi trả ResponseEntity vì GridFsResource là tài nguyên dựa trên luồng chỉ nên được tiêu thụ trong một lượt.

### 3.3. Thử tải tệp với curl

~~~bash
# Thay ID bằng ObjectId 24 ký tự hex của tệp đã tồn tại.
curl -i "http://localhost:8080/api/files/507f1f77bcf86cd799439011/content"

# Lưu nội dung xuống đĩa, lấy tên tệp từ Content-Disposition.
curl -L -OJ "http://localhost:8080/api/files/507f1f77bcf86cd799439011/content"
~~~

Ví dụ header nhận được cho một PDF:

~~~http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename*=UTF-8''ho-so.pdf
Content-Length: 145280
X-Content-Type-Options: nosniff
Cache-Control: no-store
~~~

Đây chỉ là **ví dụ minh họa**; tên, mã hóa header và kích thước thực tế phụ thuộc tệp, thư viện HTTP và cấu hình ứng dụng. Để kiểm tra nội dung có nguyên vẹn hay không, so sánh hash SHA-256 của tệp gốc và tệp tải về trong một môi trường kiểm thử được kiểm soát.

## 4. Tạo dữ liệu mẫu để thử đường tải xuống

Nếu cần tự tạo một tệp GridFS, có thể ghi nội dung từ InputStream bằng GridFsOperations.store. Ví dụ service lưu tệp:

~~~java
import java.io.IOException;
import java.io.InputStream;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.gridfs.GridFsOperations;
import org.springframework.web.multipart.MultipartFile;

public class GridFsUploadExample {

    private final GridFsOperations gridFs;

    public GridFsUploadExample(GridFsOperations gridFs) {
        this.gridFs = gridFs;
    }

    public String upload(MultipartFile uploadedFile) throws IOException {
        try (InputStream input = uploadedFile.getInputStream()) {
            ObjectId id = gridFs.store(
                input,
                uploadedFile.getOriginalFilename(),
                uploadedFile.getContentType()
            );
            return id.toHexString();
        }
    }
}
~~~

Đoạn mẫu tập trung vào thao tác API; trước khi dùng trong môi trường thật cần áp giới hạn dung lượng, kiểm tra định dạng/nội dung, chuẩn hóa filename, phân quyền và xử lý lỗi tải lên. Đặc biệt, Content-Type do client gửi lên **không phải bằng chứng** nội dung thực sự thuộc định dạng đó. Khi có yêu cầu chống mã độc, phải quét nội dung theo chính sách hệ thống.

Luồng đọc và ghi cân bằng:

~~~text
Upload: multipart InputStream → gridFs.store(...) → fs.files + fs.chunks → ObjectId
Download: ObjectId → gridFs.findOne(...) → gridFs.getResource(...)
          → Spring Resource HTTP converter → response OutputStream
~~~

## 5. Khi tầng ứng dụng cần tiêu thụ tệp mà không trả HTTP

Tầng ứng dụng có thể cần chuyển PDF sang công cụ trích xuất văn bản, tạo thumbnail hoặc ghi ra một OutputStream do dịch vụ khác cung cấp. Khi ấy, chính dịch vụ tiêu thụ phải quản lý vòng đời InputStream:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

import org.springframework.data.mongodb.gridfs.GridFsResource;

public final class FileStreamCopier {

    private FileStreamCopier() {}

    public static void copy(GridFsResource source, OutputStream target)
            throws IOException {
        if (!source.exists()) {
            throw new java.io.FileNotFoundException(source.getFilename());
        }

        // Đóng nguồn đọc; quyền sở hữu target thuộc về bên gọi.
        try (InputStream input = source.getInputStream()) {
            input.transferTo(target);
        }
    }
}
~~~

Các nguyên tắc quan trọng:

- **Không dùng readAllBytes()** cho tệp lớn: thao tác này có thể gom toàn bộ nội dung vào heap và gây OutOfMemoryError.
- **Đóng luồng** ở nơi trực tiếp đọc dữ liệu; với ví dụ ResponseEntity<Resource>, Spring phụ trách việc sao chép và đóng luồng trong quá trình ghi HTTP.
- **Không tái sử dụng cùng một InputStream** cho nhiều consumer. Nếu cần xử lý lại, thực hiện một lượt truy xuất mới và lấy Resource/stream mới.
- **Không mặc định gọi available() để biết kích thước**: đó không phải tổng dung lượng tệp. Dùng GridFSFile.getLength hoặc GridFsResource.contentLength.
- **Không biến tệp thành String một cách tùy tiện**: dữ liệu có thể là PDF, ảnh hoặc tệp nén; chỉ giải mã thành văn bản khi biết charset và định dạng.
- **Không nuốt lỗi đọc giữa chừng**: nếu kết nối MongoDB đứt hoặc chunk thiếu, phải ghi log và báo lỗi phù hợp; không coi response thiếu byte là thành công.

## 6. Dữ liệu metadata và các điều kiện truy xuất

Đường tải xuống thường bắt đầu bằng một **business document** chứa file ID, ví dụ:

~~~json
{
  "_id": "application-120",
  "ownerId": "user-42",
  "attachmentGridFsId": "507f1f77bcf86cd799439011",
  "status": "APPROVED"
}
~~~

Quy trình đúng thường là: xác định người gọi → tìm business document theo quyền → lấy attachmentGridFsId đã được phép → tra GridFSFile theo ID → lấy resource → trả nội dung. Chỉ truy vấn fs.files theo ID mà không xét owner/tenant dễ tạo lỗi **IDOR** (người dùng truy cập tệp của người khác bằng cách thay ID trên URL).

Ngoài ID, có thể lưu metadata phụ trong GridFS khi tải lên (loại nghiệp vụ, phiên bản, checksum riêng, owner ID...). Dữ liệu metadata giúp lọc và kiểm tra, nhưng không thay thế quy tắc phân quyền ở tầng nghiệp vụ. Nếu dùng filename để tìm nhiều bản:

~~~java
Query query = Query.query(
    Criteria.where("filename").is("statement.pdf")
);

GridFSFile oneFile = gridFsOperations.findOne(query);
~~~

Không nên dựa vào việc findOne sẽ trả đúng phiên bản mới nhất khi có nhiều tệp trùng tên. Hãy lưu ID của bản được chọn trong business document hoặc dùng cơ chế version có quy tắc rõ ràng. Đối với truy vấn nhiều metadata, cân nhắc index phù hợp trong fs.files; đo bằng explain/monitoring theo tải thực tế trước khi tối ưu.

## 7. Đọc reactive với Spring WebFlux

Đối với ứng dụng reactive, sử dụng **ReactiveGridFsOperations** (thường do ReactiveGridFsTemplate triển khai) và **ReactiveGridFsResource**. Khác với GridFsResource đồng bộ, ReactiveGridFsResource cung cấp luồng **Flux<DataBuffer>** qua getDownloadStream; không có kiểu trả về Resource đồng bộ để đưa thẳng vào ResponseEntity<Resource>.

Ví dụ endpoint WebFlux tối giản, vẫn dùng ID kiểu ObjectId:

~~~java
package example.files;

import org.bson.types.ObjectId;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.gridfs.ReactiveGridFsOperations;
import org.springframework.data.mongodb.gridfs.ReactiveGridFsResource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/reactive-files")
public class ReactiveGridFsDownloadController {

    private final ReactiveGridFsOperations gridFs;

    public ReactiveGridFsDownloadController(ReactiveGridFsOperations gridFs) {
        this.gridFs = gridFs;
    }

    @GetMapping("/{id}/content")
    public Mono<ResponseEntity<Flux<DataBuffer>>> download(
            @PathVariable String id) {
        if (!ObjectId.isValid(id)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid file id"
            ));
        }

        Query query = Query.query(
            Criteria.where("_id").is(new ObjectId(id))
        );

        return gridFs.findOne(query)
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "File not found"
            )))
            .flatMap(file -> gridFs.getResource(file)
                .filter(ReactiveGridFsResource::exists)
                .map(resource -> ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_OCTET_STREAM)
                    .contentLength(file.getLength())
                    .body(resource.getDownloadStream())
                )
            )
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "File not found"
            )));
    }
}
~~~

Ví dụ reactive trả MIME mặc định để tập trung vào luồng dữ liệu; khi xây dựng API thực tế phải bổ sung phân quyền, Content-Disposition, MIME được kiểm chứng, chính sách cache và kiểm thử như phiên bản MVC.

**Không dùng block() hoặc lấy Mono<InputStream> để ghép toàn bộ tệp vào RAM** trong luồng xử lý WebFlux. Tài liệu API của ReactiveGridFsResource ghi rõ getInputStream có thể gom dữ liệu trong bộ nhớ; đối với tệp lớn, ưu tiên getDownloadStream. Nội dung reactive thường chỉ được tiêu thụ **một lần**, nên không subscribe thủ công trước rồi chuyển cùng stream cho framework sử dụng.

Khi tự xử lý DataBuffer ngoài cơ chế HTTP do framework quản lý, cần hiểu cách giải phóng buffer (đặc biệt pooled buffer) để tránh rò rỉ bộ nhớ; không tùy tiện cache hoặc giữ tham chiếu lâu dài tới DataBuffer đã được phát ra.

## 8. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Trả 404 mặc dù có tên tệp | Truy vấn sai ID, dùng sai bucket, tệp trùng tên hoặc metadata chưa khớp | Kiểm tra ID/bucket/database và điều kiện tìm kiếm; ưu tiên ID rõ ràng. |
| Trả 400 ngay lập tức | ID không phải ObjectId hex hợp lệ trong ví dụ | Xác định đúng kiểu ID mà ứng dụng đã dùng khi lưu. |
| Tải được nhưng tên tệp/MIME sai | Metadata thiếu, tên không được chuẩn hóa hoặc Content-Disposition sai | Gửi header thích hợp, fallback MIME, vệ sinh filename. |
| Heap tăng mạnh khi nhiều người tải | Dùng byte[], readAllBytes hoặc gom toàn bộ Flux | Trả Resource/Flux và đo lưu lượng, số kết nối, heap. |
| InputStream đã bị tiêu thụ | Mở stream để kiểm tra trước; ghi log nội dung hoặc đọc hai lần | Chỉ mở lúc cần, mỗi lần tiêu thụ dùng lượt truy xuất riêng. |
| Tệp tải về thiếu byte | Mạng bị ngắt, dữ liệu chunk thiếu, client hủy request | Kiểm tra log, chiều dài thực tế, lỗi MongoDB, retry ở tầng thích hợp. |
| Client yêu cầu Range nhưng không nhận 206 | Endpoint chưa triển khai truy xuất từng vùng byte | Thiết kế hỗ trợ Range/ResourceRegion riêng nếu có nhu cầu; không mặc định GridFsResource đáp ứng. |
| Người dùng xem được tệp không thuộc quyền | Chỉ kiểm tra ID mà không kiểm tra business ownership | Phân quyền trước bước lấy nội dung, kiểm thử tình huống khác tenant/owner. |
| Tải chậm dưới tải lớn | Đọc chunk, băng thông, pool kết nối hoặc truy vấn metadata là nút thắt | Theo dõi latency, pool, network, kích thước tệp, chỉ số DB và truy vấn. |

Đối với lỗi đã bắt đầu truyền body, có thể không còn khả năng đổi status HTTP từ 200 thành 500. Vì vậy cần quan sát kết nối bị cắt, số byte thực truyền và lỗi stream tại server hoặc gateway, thay vì chỉ đếm status code cuối cùng.

## 9. Các tình huống kiểm thử nên có

Khi đã có dữ liệu GridFS mẫu và endpoint thực thi, sử dụng kiểm thử tích hợp với MongoDB thật trong môi trường test (chẳng hạn MongoDB chạy qua Testcontainers) để kiểm tra hành vi driver + Spring Data + HTTP:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Tệp tồn tại, nội dung nhỏ | 200; byte tải về bằng byte gốc; filename, Content-Type, Content-Length phù hợp. |
| Tệp lớn hơn một chunk GridFS | 200; không mất/đảo thứ tự chunk; SHA-256 đầu ra khớp dữ liệu gốc. |
| ID sai định dạng | 400, không truy vấn MongoDB với ObjectId không hợp lệ. |
| ID hợp lệ nhưng không tồn tại | 404; không trả nội dung rỗng như thể thành công. |
| Tệp có Content-Type thiếu hoặc không hợp lệ | Header Content-Type fallback về application/octet-stream. |
| Tệp có tên tiếng Việt/ký tự đặc biệt | Tên tải xuống được encode đúng, không chứa CR/LF gây lỗi header. |
| Người gọi không có quyền với business document | 403 hoặc 404 theo chính sách; nội dung không bị phát ra. |
| Đọc bị gián đoạn giữa chừng | Lỗi được ghi nhận, connection bị xử lý đúng; không coi đó là toàn bộ tệp đã truyền xong. |
| Nhiều yêu cầu tải đồng thời | Bộ nhớ không tăng tuyến tính theo tổng kích thước toàn bộ tệp đang tải. |

Có thể thử nhanh bằng lệnh:

~~~bash
# Chỉ xem response headers (tùy server mà HEAD cần được hỗ trợ rõ ràng).
curl -I "http://localhost:8080/api/files/507f1f77bcf86cd799439011/content"

# Lưu tệp trả về, quan sát header và mã trạng thái.
curl -sS -D headers.txt -o downloaded.bin \
  "http://localhost:8080/api/files/507f1f77bcf86cd799439011/content"
~~~

Để chứng minh luồng thực sự tránh giữ toàn bộ tệp, kiểm tra heap/GC và profile khi tải đồng thời những tệp lớn hơn đáng kể so với kích thước heap cho phép. Một bài test chỉ so sánh vài byte của tệp nhỏ sẽ không phát hiện được lỗi dùng readAllBytes.

## 10. Nguyên tắc triển khai trong hệ thống thực tế

1. **Giữ ranh giới rõ ràng:** tầng nghiệp vụ quyết định *ai được tải tệp nào*; GridFsOperations xử lý truy vấn và đọc; controller định nghĩa HTTP contract.
2. **Dùng ID ổn định:** tên tệp chỉ để hiển thị và làm header; nếu có nhiều phiên bản, lưu chính xác ID được tham chiếu từ nghiệp vụ.
3. **Stream dữ liệu:** tránh gom file vào byte[] hoặc String, nhất là khi kích thước chưa biết trước và có nhiều request đồng thời.
4. **Xử lý metadata có chủ đích:** MIME không đáng tin nếu lấy nguyên từ client; tên tệp phải an toàn cho header và đường dẫn.
5. **Quản lý vòng đời stream:** dịch vụ tự đọc thì đóng InputStream; controller trả Resource để Spring quản lý quá trình ghi; reactive dùng Flux<DataBuffer> theo vòng đời subscription.
6. **Có giới hạn và quan sát:** đặt timeout phù hợp, theo dõi lỗi MongoDB/HTTP, lưu lượng, độ trễ và giới hạn người dùng; chọn chiến lược cache dựa trên độ nhạy nội dung.
7. **Chỉ hỗ trợ Range khi đã triển khai:** resume download, seek video hoặc PDF range request là yêu cầu riêng, cần đọc vùng byte và trả header 206/Content-Range chính xác.

GridFsResource hữu ích vì giữ được giao diện Resource thống nhất của Spring, trong khi GridFsOperations phụ trách tìm và mở dữ liệu lưu trữ trong MongoDB. Một endpoint tốt không chỉ tải xuống được tệp mà còn phải chọn đúng tệp, kiểm tra quyền, cung cấp đúng HTTP metadata và truyền nội dung có kiểm soát tài nguyên.

## 11. Tài liệu tham khảo

- [Spring Data MongoDB – GridFS Support](https://docs.spring.io/spring-data/data-mongo/reference/mongodb/template-gridfs.html): cấu hình và thao tác GridFS đồng bộ/reactive.
- [API GridFsOperations](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/gridfs/GridFsOperations.html): findOne, getResource, store và delete.
- [API GridFsResource](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/gridfs/GridFsResource.html): các thuộc tính và cách truy cập InputStream.
- [API ReactiveGridFsOperations](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/gridfs/ReactiveGridFsOperations.html): các thao tác Mono/Flux.
- [API ReactiveGridFsResource](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/gridfs/ReactiveGridFsResource.html): getDownloadStream và lưu ý tiêu thụ dữ liệu.
- [Spring Framework – ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): cách trả nội dung Resource từ controller.
