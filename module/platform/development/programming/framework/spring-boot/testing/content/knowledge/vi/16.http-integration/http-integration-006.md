# Kiểm thử HTTP tích hợp: Upload, download và phản hồi có kích thước lớn trong Spring Boot

## 1. Vấn đề cần giải quyết

Một API có thể trả đúng JSON cho yêu cầu thông thường nhưng vẫn lỗi khi khách hàng **tải tệp lên**, **tải tệp xuống** hoặc nhận **response lớn**. Các lỗi thường không nằm trong phép tính nghiệp vụ đơn giản mà nằm ở ranh giới HTTP: cách encode `multipart/form-data`, tên part, kích thước tối đa, parser của servlet container, byte bị sửa khi qua codec, `Content-Disposition`, `Content-Length`, xử lý `Range` hoặc stream bị ngắt.

Bài này tập trung vào việc **gửi HTTP request thực tế và khẳng định cả response** trong Spring Boot; không dừng ở việc mock một service rồi assert giá trị Java.

Ba tình huống chính:

1. **Upload:** client gửi file nhị phân bằng multipart; server đọc đúng part, tên file, số byte và trả response/Location phù hợp.
2. **Download:** server trả về **đúng từng byte**, status, media type và headers; tải tệp không phải chỉ là xem DTO chứa ID.
3. **Large response:** server viết nhiều khối dữ liệu; client test **tiêu thụ theo luồng** mà không gom toàn bộ vào một `byte[]` lớn và kiểm tổng số byte, tính toàn vẹn, trạng thái hoàn tất.

Ta sẽ so sánh `MockMvc` với **HTTP thực qua `@SpringBootTest(webEnvironment = RANDOM_PORT)`**, rồi thực hành một ứng dụng Java 17+/Spring Boot 3.5.x có tệp nhỏ lưu trong RAM để minh họa và endpoint phát phản hồi lớn bằng `StreamingResponseBody`.

### Kết quả cần đạt

- Hiểu `multipart/form-data`, `MultipartFile`, `MockMultipartFile` và cách kiểm upload bằng HTTP thực.
- Phân biệt giới hạn của `MockMvc`: nó tạo multipart request giả, **không thực thi parser multipart thực của servlet container**.
- Test HTTP 201, 200, 206, 400, 404, 413 và 415 theo hợp đồng cụ thể.
- Kiểm `Location`, `Content-Type`, `Content-Disposition`, `Content-Length` và khi cần `Content-Range`.
- Kiểm download **byte-for-byte** bằng `assertArrayEquals`, không chuyển dữ liệu nhị phân thành `String`.
- Dùng `StreamingResponseBody` + `HttpClient.BodyHandlers.ofInputStream()` cho response lớn.
- Hiểu bộ nhớ, timeout, async dispatch, Range, security, validation filename, cleanup và giới hạn chứng minh của mỗi kiểu test.

## 2. Chọn mức kiểm thử: MockMvc hay HTTP thật?

| Mức kiểm thử | Cách chạy | Kiểm tốt điều gì? | Chưa đủ để chứng minh |
| --- | --- | --- | --- |
| Unit test service | Khởi tạo service thật với fake/mock storage | Quy tắc đặt tên, kiểm size, tính checksum, trạng thái lưu | Multipart parser, MVC binding, HTTP headers |
| `@WebMvcTest` + `MockMvc` | Web MVC slice, mock request/response | Mapping, part name, validation, status, JSON/headers/bytes ở controller | Container multipart limits, real TCP, client encoding |
| `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` | Context Boot rộng hơn, mock servlet request | Controller + các beans thực có trong context, không mở cổng | Parser container thật, network, proxy, streaming qua socket |
| `@SpringBootTest(RANDOM_PORT)` + HTTP client | Embedded HTTP server và client giao tiếp loopback | Multipart wire format, HTTP headers/status, body và stream qua TCP | Reverse proxy/CDN production, lưu trữ cloud, TLS edge nếu chưa cấu hình |
| Integration với storage/antivirus thật | HTTP server + test DB/object storage/scan service | Các hợp đồng persistence, streaming, retry, cleanup thực tế | Chưa chắc bằng production load và topology |

**Quan trọng:** `MockMvcRequestBuilders.multipart(...)` thiết lập một `MockMultipartHttpServletRequest` với các part đã được chuẩn bị. Nó **không parse chuỗi multipart thực** như Tomcat khi nhận request qua TCP. Vì vậy, một bài test MockMvc upload PASS không chứng minh boundary, parser và `spring.servlet.multipart.max-file-size` trên server thật đều đúng.

Trong bài thực hành, test MockMvc kiểm nhanh các nhánh MVC; test `RANDOM_PORT` kiểm end-to-end từ **JDK HttpClient → TCP → embedded server → controller**. Hai lớp test là bổ sung, không thay thế nhau.

## 3. HTTP multipart: hiểu request trước khi test

`multipart/form-data` chia request body thành nhiều *part*, phân cách bởi một `boundary`. Mỗi part có headers riêng; tên part quan trọng vì controller thường dùng `@RequestParam("file")` hoặc `@RequestPart("file")`.

Ví dụ cấu trúc một request có file:

~~~http
POST /api/files HTTP/1.1
Content-Type: multipart/form-data; boundary=BoundaryTest202

--BoundaryTest202
Content-Disposition: form-data; name="file"; filename="tiny.bin"
Content-Type: application/octet-stream

<bytes của tiny.bin>
--BoundaryTest202--
~~~

Đoạn trên là **minh họa cấu trúc**, không phải raw request hoàn chỉnh có CRLF và `Content-Length` chính xác. Trong request thật, các dòng protocol phải phân tách bằng `\r\n`; bytes có thể chứa `0x00`, `0x0A`, `0xFF` và không được đổi sang text. Client tạo body/boundary hoặc bạn phải tạo chúng khớp nhau một cách tuyệt đối.

### 3.1 Ba loại Content-Type thường bị nhầm

- **Request tổng:** `multipart/form-data; boundary=...`.
- **Part file:** ví dụ `application/octet-stream` hoặc `image/png`, do client cung cấp và có thể không đáng tin.
- **Response sau upload:** thường là `application/json` với ID/metadata; download có thể trả `application/octet-stream`.

Không dùng `application/json` làm request Content-Type khi đang gửi file theo `MultipartFile`; không dựa vào MIME client khai báo để kết luận nội dung tệp an toàn.

### 3.2 MultipartFile, RequestParam và RequestPart

Spring MVC hỗ trợ:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
ResponseEntity<?> upload(@RequestParam("file") MultipartFile file) {
    // ...
}
~~~

Đây là **khung controller minh họa**, cần annotations/imports và method body hợp lệ để thành file thực. Với file part thông thường, `@RequestParam("file")` là đủ. `@RequestPart` hữu ích khi cần bind một part JSON thành DTO qua converter, đặc biệt request gồm **metadata JSON + file**.

Trong Spring Boot servlet stack, multipart configuration thường do Boot thiết lập dựa trên `jakarta.servlet.http.Part`/container; không nhầm với WebFlux `FilePart`, `PartEvent` hoặc `Flux<DataBuffer>`.

### 3.3 Những trường hợp phải test

| Input | Điều cần kiểm |
| --- | --- |
| Part `file` hợp lệ, có bytes nhị phân | 201/200 theo contract, ID, vị trí download, bytes nguyên vẹn |
| File trống | 400 hoặc status được thiết kế rõ |
| Thiếu part `file` | 400 (thường do required argument thiếu), không lưu dữ liệu |
| Sai Content-Type request | 415 nếu endpoint chỉ consumes multipart |
| Size vượt application limit | 413 trong contract ví dụ |
| Size vượt servlet container limit | Status/exception handling **qua server thật**, có thể phụ thuộc container |
| Filename có `../` hoặc backslash | Tên an toàn không chứa path và không ghi file ra ngoài thư mục |
| Multipart không đóng boundary/headers sai | Có lỗi client rõ ràng, không tạo bản ghi sai |
| Hai part trùng name hoặc upload nhiều file | Hợp đồng phải định nghĩa rõ: một file, list file hay từ chối |

Giới hạn mặc định Spring Boot 3.5 cho servlet multipart là **1MB mỗi file**, **10MB mỗi request**, ngưỡng chuyển nội dung vào disk khi đạt threshold mặc định **0B**. Chúng là cấu hình khởi tạo multipart của server, không là ràng buộc mà `MockMultipartFile` tự thực thi.

## 4. Download đúng nghĩa phải bảo vệ bytes và headers

Một download không chỉ là `ResponseEntity.ok(file)` theo nghĩa JSON. Với nội dung nhị phân, thường dùng một `Resource` cùng response headers:

~~~java
Resource body = new ByteArrayResource(data);
return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .contentLength(data.length)
        .header(HttpHeaders.CONTENT_DISPOSITION,
                ContentDisposition.attachment()
                        .filename("tiny.bin")
                        .build()
                        .toString())
        .body(body);
~~~

Đoạn này là **minh họa bên trong controller** có `data`, `Resource`, `ByteArrayResource` và các imports. Trong ví dụ hoàn chỉnh ở mục 9, controller trả `ResponseEntity<Resource>`.

Các assertion quan trọng:

- **Status:** `200 OK` cho tải đủ tài nguyên, `404` nếu ID không tồn tại, `206 Partial Content` cho range hợp lệ được hỗ trợ.
- **Content-Type:** `application/octet-stream` hoặc media type đã được xác định an toàn.
- **Content-Disposition:** `attachment; filename="tiny.bin"` hướng browser download; xử lý Unicode filename cần tuân thủ encoding và escape.
- **Content-Length:** số **byte thực** của body khi biết trước. Không dùng `String.length()` để tính số byte file.
- **Nội dung:** so sánh `byte[]` gốc với bytes tải xuống bằng `assertArrayEquals` hoặc checksum kết hợp số byte khi file quá lớn.

Nếu response là PNG/PDF/ZIP, **không dùng `getContentAsString()` hoặc `new String(bytes)` rồi so sánh**, vì encoding có thể thay bytes hoặc làm mất dữ liệu. File chứa `0x00` không phải chuỗi kết thúc như C.

### Range và download tiếp tục

HTTP `Range: bytes=2-4` yêu cầu một đoạn tài nguyên. Khi hỗ trợ, response thường là:

~~~http
HTTP/1.1 206 Partial Content
Content-Range: bytes 2-4/6
Content-Length: 3
~~~

Ba byte response tương ứng các vị trí index 2,3,4 trong tệp dài 6 byte. Spring MVC có cơ chế xử lý HTTP Range cho `Resource` hoặc `ResponseEntity<Resource>` **với điều kiện** response status 200 và Resource hỗ trợ truy cập lặp lại; **`InputStreamResource` không phù hợp** với cơ chế Range tự động này.

Tránh khẳng định rằng mọi `StreamingResponseBody` tự hiểu `Range`. Nếu API video/media có resume, hãy test 206, `Content-Range`, byte boundaries và 416 cho range không hợp lệ theo contract; dùng Resource phù hợp hoặc logic range riêng.

## 5. Phản hồi lớn: “không OOM” là một hợp đồng riêng

Ví dụ endpoint trả 5MB JSON hoặc 100MB tệp: nếu controller tính `byte[] output = new byte[100_000_000]` rồi mới gửi, đó **không phải streaming ở tầng application** dù socket sau đó truyền theo từng packet.

Ngược lại, `StreamingResponseBody` cho phép controller viết dần từng khối vào `OutputStream`:

~~~java
StreamingResponseBody body = output -> {
    byte[] buffer = new byte[8192];
    for (int chunk = 0; chunk < 100; chunk++) {
        output.write(buffer);
    }
    output.flush();
};
~~~

Đoạn trên là **mẫu minh họa**, viết 100 khối toàn zero với tổng `819_200` byte. Trong bài thực hành, ta viết pattern xác định `byte[index] = index mod 256` để có thể xác minh **toàn bộ nội dung** mà không giữ body lớn trong RAM.

**StreamingResponseBody** trong Spring MVC dùng xử lý request bất đồng bộ và tác vụ viết trên executor; đó không tự đồng nghĩa non-blocking I/O của WebFlux. Trong production nên cấu hình `AsyncTaskExecutor` thích hợp, timeout, thread pool và giới hạn đồng thời; một streaming writer chậm có thể giữ tài nguyên lâu.

### 5.1 Chọn HTTP client handler phù hợp

| Client / API | Hành vi tiêu thụ | Với file lớn |
| --- | --- | --- |
| JDK `BodyHandlers.ofByteArray()` | Tập hợp toàn bộ response thành `byte[]` | Chỉ dùng khi file có giới hạn nhỏ rõ ràng |
| JDK `BodyHandlers.ofString()` | Decode bytes thành text | Không dùng cho tải nhị phân |
| JDK `BodyHandlers.ofInputStream()` | Đọc dần qua `InputStream`; phải đóng stream | Phù hợp để kiểm large download theo chunks |
| JDK `BodyHandlers.ofFile(path)` | Ghi response xuống file | Phù hợp khi muốn kiểm file thật và dung lượng disk |
| MockMvc `content().bytes(...)` | Dùng mock response buffer trong JVM | Hợp cho body nhỏ; không chứng minh streaming TCP |
| WebClient `bodyToMono(byte[].class)` | Gom toàn body trong client reactive | Không phù hợp cho response cực lớn, có thể chạm codec buffer limit |

Kiểm phản hồi lớn bằng **số byte tổng + đối chiếu từng block hoặc digest**, không dùng một assertion chỉ kiểm `200`; response có thể bị truncate hoặc sai byte giữa stream vẫn trả status ban đầu 200.

### 5.2 Content-Length và Transfer-Encoding

- Nếu server biết trước kích thước và không nén/chuyển dạng, có thể đặt `Content-Length` đúng tổng bytes.
- Nếu độ dài chưa biết, server có thể dùng **chunked transfer coding** trong HTTP/1.1, hoặc cách framing khác với HTTP/2. Đừng giả định luôn có `Content-Length`.
- Compression (`gzip`) có thể khiến số byte **truyền qua dây** khác số byte **sau giải nén**. Test phải xác định đang kiểm representation nào.
- Không assert `Transfer-Encoding: chunked` chỉ vì controller dùng `StreamingResponseBody`; framing phụ thuộc HTTP version, container, proxy và compression.
- Sau khi headers đã gửi, lỗi giữa stream có thể khiến client gặp truncation/IOException mà server không đổi status từ 200 thành 500 được. Vì vậy phải **đọc đến EOF** và xác minh đủ bytes.

## 6. Dữ liệu kiểm thử phải phát hiện được lỗi mã hóa

Đừng chỉ upload chuỗi `"hello"` và nghĩ rằng file nhị phân an toàn. Tạo data có cả bytes khó:

~~~java
byte[] payload = {
        0, 10, 13, 65, 127, (byte) 0x80, (byte) 0xFF
};
~~~

Đoạn này là **fixture Java trong test**. Nó có zero byte, line feed, carriage return và bytes ngoài ASCII; các lỗi do chuyển bytes qua String/UTF-8 có thể lộ ra.

Đối với phản hồi lớn, chọn pattern có thể kiểm độc lập:

~~~text
index:  0   1   2   ...  254 255 256 257
byte:   00  01  02  ...  FE  FF  00  01
~~~

Với stream dài 2MiB + 37 bytes, test có thể kiểm tại index `i` rằng `(actualByte & 0xFF) == (i & 0xFF)`. Không cần giữ 2MiB expected array; chỉ cần buffer 8KiB và bộ đếm. Nếu có dữ liệu production không có pattern xác định, dùng **checksum SHA-256 đã biết trước hoặc tính độc lập từ fixture nguồn**, so sánh thêm size và khi cần metadata.

**Checksum giống nhau không thay thế mọi assertion**: vẫn cần kiểm HTTP status, Content-Type, disposition, quyền truy cập và đúng file được chọn.

## 7. Thiết kế API mẫu: một phần lưu tệp nhỏ, một phần stream lớn

Ta sẽ xây một mini Spring Boot 3.5.x MVC application:

~~~text
POST /api/files          multipart form-data; part "file"
  -> validate empty, size, filename
  -> lưu bytes nhỏ trong in-memory store (demo)
  -> 201 Created + Location + JSON receipt

GET /api/files/{id}
  -> 200 + octet-stream + Content-Disposition
  -> body là Resource để test bytes/Range
  -> 404 nếu không có ID

GET /api/files/large?size=N
  -> 200 + Content-Length=N, streaming pattern 0..255 lặp lại
  -> 400 nếu N ngoài 1..16MiB
~~~

**Giới hạn minh họa cố ý:**

- Upload API chỉ nhận tối đa **512KiB** theo application rule; ngay cả khi container cho phép tới 1MB, application vẫn trả 413 nếu quá 512KiB. Dùng `MultipartFile.getBytes()` chỉ vì giới hạn nhỏ này.
- In-memory storage và bộ đếm ID là fixture đơn giản, **không phải thiết kế production**: không survive restart, không scale ngang, không có quota/TTL/ACL.
- Generated large response lên tới **16MiB** không phải file lưu trong store; nó là stream tổng hợp để minh họa kiểm bytes/EOF.
- Không có Spring Security trong ví dụ; ứng dụng production phải có authorization theo file owner/tenant.
- Tất cả test chạy local, không kết nối cloud, DB hay network ngoài loopback.

### Lựa chọn status/headers

| Endpoint | Thành công | Từ chối |
| --- | --- | --- |
| `POST /api/files` | 201, `Location: /api/files/F-n`, JSON `id,filename,size` | 400 file rỗng/thiếu; 413 vượt 512KiB; 415 sai media type |
| `GET /api/files/F-n` | 200, octet-stream, attachment filename, Content-Length | 404 ID không tồn tại |
| `GET /api/files/F-n` với Range | 206, `Content-Range` và đúng đoạn bytes (Resource hỗ trợ) | 416 nếu range không thể đáp ứng theo API |
| `GET /api/files/large?size=N` | 200, stream N bytes, Content-Length | 400 nếu N không hợp lệ |

### Cây thư mục

~~~text
src/
  main/
    java/example/filehttp/
      FileHttpApplication.java
      StoredFile.java
      UploadReceipt.java
      InMemoryFileStore.java
      FileController.java
  test/
    java/example/filehttp/
      FileMockMvcTest.java
      FileLiveHttpTest.java
    resources/
      application.properties
~~~

Ví dụ này dùng **Java 17+**, Spring Boot **3.5.x**, JUnit Jupiter, `spring-boot-starter-web` và `spring-boot-starter-test`. Không thêm WebFlux starter: đây là ví dụ Servlet MVC/StreamingResponseBody; nếu ứng dụng thực dùng WebFlux, xem phần so sánh ở mục 13.

## 8. Production code hoàn chỉnh cho mini application

### 8.1 FileHttpApplication.java

~~~java
package example.filehttp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FileHttpApplication {
    public static void main(String[] args) {
        SpringApplication.run(FileHttpApplication.class, args);
    }
}
~~~

Boot tìm controller và store ở cùng package thông qua component scan. Test sử dụng root application này, không cần thêm `@SpringBootApplication` trong test.

### 8.2 StoredFile.java

~~~java
package example.filehttp;

public record StoredFile(
        String id,
        String filename,
        byte[] content) {
}
~~~

Record giữ bytes trong demo. Với tệp production lớn, hãy lưu metadata và storage key riêng, stream từ file/object storage; không đặt toàn bộ file trong một record/bean lâu sống.

### 8.3 UploadReceipt.java

~~~java
package example.filehttp;

public record UploadReceipt(
        String id,
        String filename,
        long size) {
}
~~~

DTO response được Jackson serialize thành JSON; không trả đường dẫn file nội bộ/OS filesystem cho người gọi.

### 8.4 InMemoryFileStore.java

~~~java
package example.filehttp;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class InMemoryFileStore {
    private final AtomicLong ids = new AtomicLong();
    private final ConcurrentMap<String, StoredFile> data =
            new ConcurrentHashMap<>();

    public StoredFile save(String filename, byte[] content) {
        String id = "F-" + ids.incrementAndGet();
        StoredFile saved = new StoredFile(
                id, filename, content.clone());
        data.put(id, saved);
        return saved;
    }

    public Optional<StoredFile> find(String id) {
        StoredFile found = data.get(id);
        if (found == null) {
            return Optional.empty();
        }
        return Optional.of(new StoredFile(
                found.id(), found.filename(),
                found.content().clone()));
    }
}
~~~

Việc clone giúp test không vô tình mutate array đã lưu qua cùng tham chiếu. `ConcurrentHashMap` và `AtomicLong` hỗ trợ các thao tác trong **một JVM**, **không** chứng minh uniqueness xuyên nhiều server instance hoặc tính bền vững storage. Khi làm thực, dùng DB/object store có ID và quyền truy cập riêng.

### 8.5 FileController.java

~~~java
package example.filehttp;

import java.io.IOException;
import java.net.URI;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
@RequestMapping("/api/files")
public class FileController {
    private static final long MAX_UPLOAD = 512L * 1024;
    private static final int MAX_STREAM = 16 * 1024 * 1024;
    private final InMemoryFileStore store;

    public FileController(InMemoryFileStore store) {
        this.store = store;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<UploadReceipt> upload(
            @RequestParam("file") MultipartFile file) throws IOException {
        if (file.isEmpty()) {
            return ResponseEntity.badRequest().build();
        }
        if (file.getSize() > MAX_UPLOAD) {
            return ResponseEntity.status(
                    HttpStatus.PAYLOAD_TOO_LARGE).build();
        }

        String filename = safeFilename(file.getOriginalFilename());
        StoredFile saved = store.save(filename, file.getBytes());

        return ResponseEntity
                .created(URI.create("/api/files/" + saved.id()))
                .body(new UploadReceipt(
                        saved.id(), filename, saved.content().length));
    }

    @GetMapping("/{id}")
    public ResponseEntity<Resource> download(
            @PathVariable("id") String id) {

        return store.find(id)
                .map(file -> {
                    Resource resource =
                            new ByteArrayResource(file.content());

                    return ResponseEntity.ok()
                            .contentType(
                                    MediaType.APPLICATION_OCTET_STREAM)
                            .contentLength(file.content().length)
                            .header(HttpHeaders.CONTENT_DISPOSITION,
                                    ContentDisposition.attachment()
                                            .filename(file.filename())
                                            .build()
                                            .toString())
                            .body(resource);
                })
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping(
            path = "/large",
            produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<StreamingResponseBody> large(
            @RequestParam("size") int size) {

        if (size < 1 || size > MAX_STREAM) {
            return ResponseEntity.badRequest().build();
        }

        StreamingResponseBody body = output -> {
            byte[] block = new byte[8192];
            int offset = 0;

            while (offset < size) {
                int count = Math.min(block.length, size - offset);
                for (int i = 0; i < count; i++) {
                    block[i] = (byte) ((offset + i) & 0xFF);
                }
                output.write(block, 0, count);
                offset += count;
            }
            output.flush();
        };

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .contentLength(size)
                .body(body);
    }

    private static String safeFilename(String untrusted) {
        String raw = untrusted == null ? "" :
                untrusted.replace('\\', '/');
        String base = raw.substring(raw.lastIndexOf('/') + 1);
        String safe = base.replaceAll("[^A-Za-z0-9._-]", "_");

        if (safe.isBlank() || safe.equals(".")
                || safe.equals("..")) {
            return "upload.bin";
        }
        return safe.length() <= 80
                ? safe : safe.substring(safe.length() - 80);
    }
}
~~~

**Đọc đúng các chi tiết:**

- `upload` từ chối file rỗng và file >512KiB trước khi gọi `getBytes()`. Việc container từ chối file >1MB xảy ra **ở tầng sớm hơn**, có thể không đi tới controller.
- `safeFilename` đổi dấu `\` sang `/`, chỉ giữ basename và ký tự thuộc allowlist; không dùng nguyên `getOriginalFilename()` để tạo filesystem path. Đây chỉ là kiểm soát filename cơ bản, không thay antivirus/authorization.
- `download` trả `ResponseEntity<Resource>` và `ByteArrayResource`; body binary không qua Jackson. Content-Disposition dùng builder để quote/escape filename.
- `large` không cấp phát `byte[size]`; nó tạo một buffer 8KiB và ghi dần. `Content-Length` đúng vì size biết trước; với stream không biết độ dài, không tự đặt một độ dài giả.
- `StreamingResponseBody` sử dụng async Servlet processing; phải có async support, executor phù hợp ở production. Khi client hủy giữa chừng, write có thể ném `IOException`; không tự giả định toàn bộ file đã được gửi.

**Bảo vệ tài nguyên:** `MAX_STREAM` giúp request không thể yêu cầu stream vô hạn; ở hệ thống thật cần thêm quota, rate limits, authentication, backpressure/connection limits và timeouts.

## 9. Cấu hình test cho multipart và ứng dụng

File `src/test/resources/application.properties`:

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=1MB
spring.servlet.multipart.max-request-size=2MB
spring.servlet.multipart.file-size-threshold=0B
~~~

Vì application giới hạn 512KiB, một request multipart chứa 512KiB+1 (nhưng dưới 1MB) sẽ tới controller và nhận **413 do application rule**, thay vì phụ thuộc vào exception từ container. Đây là cách viết test 413 ổn định và độc lập với container.

Để kiểm **max-file-size = 1MB thật của servlet parser**, phải có test HTTP thật với payload lớn hơn 1MB và error mapping được thiết kế phù hợp; MockMvc mock multipart không chứng minh giới hạn parser. Có thể cần cấu hình `MaxUploadSizeExceededException` handling và hành vi container khi request vượt limit.

Không đặt tệp test vào đường dẫn production, không tự tạo container storage từ environment production khi chạy CI. Trong ví dụ, không có đường dẫn disk dùng để lưu file upload lâu dài.

## 10. MockMvc: kiểm upload, download và stream nhỏ nhanh

File `src/test/java/example/filehttp/FileMockMvcTest.java`:

~~~java
package example.filehttp;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@DisplayName("MockMvc kiểm controller multipart và download")
class FileMockMvcTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    @DisplayName("Upload 201 rồi download có đúng từng byte")
    void uploadsAndDownloadsBinary() throws Exception {
        byte[] original = {0, 10, 13, 65, 127, (byte) 0xFF};
        MockMultipartFile part = new MockMultipartFile(
                "file", "tiny.bin",
                MediaType.APPLICATION_OCTET_STREAM_VALUE,
                original);

        MvcResult uploaded = mvc.perform(
                        multipart("/api/files").file(part))
                .andExpect(status().isCreated())
                .andExpect(header().exists(HttpHeaders.LOCATION))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.filename").value("tiny.bin"))
                .andExpect(jsonPath("$.size").value(original.length))
                .andReturn();

        JsonNode receipt = mapper.readTree(
                uploaded.getResponse().getContentAsByteArray());
        String id = receipt.path("id").asText();

        assertFalse(id.isBlank());
        assertEquals("/api/files/" + id,
                uploaded.getResponse().getHeader(HttpHeaders.LOCATION));

        mvc.perform(get("/api/files/{id}", id))
                .andExpect(status().isOk())
                .andExpect(content().contentType(
                        MediaType.APPLICATION_OCTET_STREAM))
                .andExpect(header().string(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"tiny.bin\""))
                .andExpect(header().longValue(
                        HttpHeaders.CONTENT_LENGTH, original.length))
                .andExpect(content().bytes(original));
    }

    @Test
    @DisplayName("File rỗng bị từ chối bằng 400")
    void rejectsEmptyUpload() throws Exception {
        MockMultipartFile empty = new MockMultipartFile(
                "file", "empty.bin",
                MediaType.APPLICATION_OCTET_STREAM_VALUE,
                new byte[0]);

        mvc.perform(multipart("/api/files").file(empty))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("Vượt app limit 512KiB thì trả 413")
    void rejectsOversizedUpload() throws Exception {
        byte[] tooLarge = new byte[512 * 1024 + 1];
        MockMultipartFile part = new MockMultipartFile(
                "file", "oversized.bin",
                MediaType.APPLICATION_OCTET_STREAM_VALUE,
                tooLarge);

        mvc.perform(multipart("/api/files").file(part))
                .andExpect(status().is(413));
    }

    @Test
    @DisplayName("Tên tệp có path bị rút về basename an toàn")
    void sanitizesUntrustedFilename() throws Exception {
        MockMultipartFile part = new MockMultipartFile(
                "file", "../../unsafe.bin",
                MediaType.APPLICATION_OCTET_STREAM_VALUE,
                new byte[]{1});

        mvc.perform(multipart("/api/files").file(part))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.filename").value("unsafe.bin"));
    }

    @Test
    @DisplayName("Download ID không tồn tại trả 404")
    void returns404ForMissingFile() throws Exception {
        mvc.perform(get("/api/files/F-not-present"))
                .andExpect(status().isNotFound());
    }

    @Test
    @DisplayName("Request không phải multipart bị từ chối 415")
    void rejectsWrongUploadMediaType() throws Exception {
        mvc.perform(post("/api/files")
                        .contentType(MediaType.APPLICATION_OCTET_STREAM)
                        .content(new byte[]{1, 2, 3}))
                .andExpect(status().is(415));
    }

    @Test
    @DisplayName("StreamingResponseBody dùng async dispatch trong MockMvc")
    void smallGeneratedStreamUsesAsyncDispatch() throws Exception {
        int size = 257;

        MvcResult async = mvc.perform(get("/api/files/large")
                        .param("size", Integer.toString(size)))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(async))
                .andExpect(status().isOk())
                .andExpect(header().longValue(
                        HttpHeaders.CONTENT_LENGTH, size))
                .andExpect(content().bytes(pattern(size)));
    }

    private static byte[] pattern(int size) {
        byte[] bytes = new byte[size];
        for (int i = 0; i < size; i++) {
            bytes[i] = (byte) (i & 0xFF);
        }
        return bytes;
    }
}
~~~

**Có 7 phương thức `@Test`.** Từ test đầu, phần bytes chứa `0x00` và `0xFF` giúp phát hiện lỗi chuyển thành text. Test download kiểm cả status, Content-Type, Content-Disposition, Content-Length và **toàn bộ byte array**.

### Tại sao asyncDispatch cần thiết?

`StreamingResponseBody` được Spring MVC xử lý bất đồng bộ. Trong MockMvc, request đầu có thể trả về trạng thái `asyncStarted()`; sau khi async result sẵn sàng, test gọi `asyncDispatch(result)` để hoàn tất xử lý response như một dispatch khác. Với HTTP client thật, caller chỉ đọc body đến EOF, không tự gọi dispatch.

**Giới hạn lớn:** MockMvc ghi body vào mock response buffer, nên việc test `smallGeneratedStreamUsesAsyncDispatch` PASS **không chứng minh server truyền 16MiB qua TCP với memory ổn định**. Bằng chứng đó cần test live ở mục 11.

### Tại sao có thể kiểm 413 trong MockMvc ở đây?

Vì `FileController` tự có rule `file.getSize() > 512KiB`, không phải vì MockMvc đã mô phỏng Tomcat multipart size limit. Một test chỉ dựa vào `spring.servlet.multipart.max-file-size` mà không có controller rule **không nên mong** MockMultipartFile tự bị container từ chối.

## 11. HTTP thật: upload bằng multipart wire format và download stream lớn

File `src/test/java/example/filehttp/FileLiveHttpTest.java`:

~~~java
package example.filehttp;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@DisplayName("HTTP thật: multipart, bytes, Range, response lớn")
class FileLiveHttpTest {

    @LocalServerPort
    int port;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    @DisplayName("Multipart thật upload/download và kiểm Range 206")
    void realMultipartRoundTripAndRange() throws Exception {
        byte[] source = {
                0, 10, 13, 65, 127, (byte) 0xFF
        };
        String boundary = "BoundaryTest202";
        byte[] body = multipartBody(
                boundary, "file", "real.bin", source);

        HttpRequest upload = HttpRequest.newBuilder(url("/api/files"))
                .header("Content-Type",
                        "multipart/form-data; boundary=" + boundary)
                .timeout(Duration.ofSeconds(20))
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();

        HttpResponse<String> uploaded = http.send(
                upload,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertEquals(201, uploaded.statusCode());
        assertTrue(uploaded.headers()
                .firstValue("Content-Type").orElse("")
                .startsWith("application/json"));

        JsonNode receipt = mapper.readTree(uploaded.body());
        String id = receipt.path("id").asText();
        assertFalse(id.isBlank());
        assertEquals("real.bin",
                receipt.path("filename").asText());
        assertEquals(source.length,
                receipt.path("size").asInt());

        String location = uploaded.headers()
                .firstValue("Location").orElseThrow();
        assertEquals("/api/files/" + id,
                URI.create(location).getPath());

        // URI.resolve chấp nhận Location tương đối hoặc tuyệt đối.
        URI downloadUri = url("/").resolve(location);

        HttpResponse<byte[]> downloaded = http.send(
                HttpRequest.newBuilder(downloadUri)
                        .timeout(Duration.ofSeconds(20))
                        .GET().build(),
                HttpResponse.BodyHandlers.ofByteArray());

        assertEquals(200, downloaded.statusCode());
        assertEquals("application/octet-stream",
                downloaded.headers()
                        .firstValue("Content-Type").orElse(""));
        assertEquals("attachment; filename=\"real.bin\"",
                downloaded.headers()
                        .firstValue("Content-Disposition").orElse(""));
        assertEquals(source.length,
                downloaded.headers()
                        .firstValueAsLong("Content-Length").orElse(-1));
        assertArrayEquals(source, downloaded.body());

        HttpResponse<byte[]> ranged = http.send(
                HttpRequest.newBuilder(downloadUri)
                        .header("Range", "bytes=2-4")
                        .timeout(Duration.ofSeconds(20))
                        .GET().build(),
                HttpResponse.BodyHandlers.ofByteArray());

        assertEquals(206, ranged.statusCode());
        assertEquals("bytes 2-4/" + source.length,
                ranged.headers()
                        .firstValue("Content-Range").orElse(""));
        assertArrayEquals(Arrays.copyOfRange(source, 2, 5),
                ranged.body());
    }

    @Test
    @DisplayName("Stream lớn kiểm từng byte theo block, không gom body")
    void consumesLargeResponseWithoutMaterializingWholeBody()
            throws Exception {
        int size = 2 * 1024 * 1024 + 37;

        HttpRequest request = HttpRequest.newBuilder(
                        url("/api/files/large?size=" + size))
                .header("Accept", "application/octet-stream")
                .timeout(Duration.ofSeconds(30))
                .GET()
                .build();

        HttpResponse<InputStream> response = http.send(
                request,
                HttpResponse.BodyHandlers.ofInputStream());

        assertEquals(200, response.statusCode());
        assertEquals("application/octet-stream",
                response.headers()
                        .firstValue("Content-Type").orElse(""));
        assertEquals(size,
                response.headers()
                        .firstValueAsLong("Content-Length").orElse(-1));

        long count = 0;
        byte[] chunk = new byte[8192];

        try (InputStream stream = response.body()) {
            int n;
            while ((n = stream.read(chunk)) != -1) {
                for (int i = 0; i < n; i++) {
                    int actual = chunk[i] & 0xFF;
                    int expected = (int) ((count + i) & 0xFF);
                    if (actual != expected) {
                        fail("Byte mismatch at index " + (count + i));
                    }
                }
                count += n;
            }
        }

        assertEquals(size, count);
    }

    @Test
    @DisplayName("Ứng dụng từ chối upload >512KiB qua HTTP thật")
    void realServerRejectsApplicationSizeLimit() throws Exception {
        byte[] tooLarge = new byte[512 * 1024 + 1];
        String boundary = "BoundaryTooLarge202";
        byte[] body = multipartBody(
                boundary, "file", "big.bin", tooLarge);

        HttpRequest request = HttpRequest.newBuilder(url("/api/files"))
                .header("Content-Type",
                        "multipart/form-data; boundary=" + boundary)
                .timeout(Duration.ofSeconds(20))
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();

        HttpResponse<Void> response = http.send(
                request, HttpResponse.BodyHandlers.discarding());

        assertEquals(413, response.statusCode());
    }

    @Test
    @DisplayName("Size stream ngoài phạm vi nhận 400")
    void rejectsInvalidLargeResponseSize() throws Exception {
        HttpResponse<Void> response = http.send(
                HttpRequest.newBuilder(
                                url("/api/files/large?size=16777217"))
                        .timeout(Duration.ofSeconds(20))
                        .GET().build(),
                HttpResponse.BodyHandlers.discarding());

        assertEquals(400, response.statusCode());
    }

    @Test
    @DisplayName("Tải ID không tồn tại qua TCP trả 404")
    void returns404ForMissingDownload() throws Exception {
        HttpResponse<Void> response = http.send(
                HttpRequest.newBuilder(
                                url("/api/files/F-never-created"))
                        .timeout(Duration.ofSeconds(20))
                        .GET().build(),
                HttpResponse.BodyHandlers.discarding());

        assertEquals(404, response.statusCode());
    }

    private URI url(String relativePath) {
        return URI.create(
                "http://127.0.0.1:" + port + relativePath);
    }

    private static byte[] multipartBody(
            String boundary,
            String field,
            String filename,
            byte[] payload) throws Exception {

        ByteArrayOutputStream out = new ByteArrayOutputStream();

        String preamble = "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"" + field
                + "\"; filename=\"" + filename + "\"\r\n"
                + "Content-Type: application/octet-stream\r\n\r\n";
        String epilogue = "\r\n--" + boundary + "--\r\n";

        out.write(preamble.getBytes(StandardCharsets.US_ASCII));
        out.write(payload);
        out.write(epilogue.getBytes(StandardCharsets.US_ASCII));

        return out.toByteArray();
    }
}
~~~

**Có 5 phương thức `@Test`.** Khi chạy chúng, Spring Boot khởi động embedded server trên cổng ngẫu nhiên (inject bằng `@LocalServerPort`), rồi JDK `HttpClient` thực hiện HTTP request thông qua loopback.

### Đọc đúng bằng chứng của từng test

1. **`realMultipartRoundTripAndRange`:** tự tạo multipart boundary/header/body chuẩn, POST qua TCP, assert 201 và JSON, sau đó GET từ `Location` và kiểm toàn bộ bytes, Content-Disposition, Content-Length. Tiếp theo gửi `Range` và kiểm 206 + 3 byte.
2. **`consumesLargeResponseWithoutMaterializingWholeBody`:** dùng `BodyHandlers.ofInputStream()`, một buffer 8KiB và bộ đếm. Nó kiểm **từng byte** của response dài 2MiB + 37; không giữ cả body trong một `byte[]`. Đọc tới EOF giúp phát hiện stream thiếu bytes.
3. **`realServerRejectsApplicationSizeLimit`:** payload hơn 512KiB nhưng dưới giới hạn parser 1MB; kiểm HTTP 413 từ controller rule qua server thật.
4. **`rejectsInvalidLargeResponseSize`:** request >16MiB giới hạn stream, kiểm 400 mà không làm server phát một body khổng lồ.
5. **`returns404ForMissingDownload`:** ID không tồn tại không phát binary body thành công.

**Lưu ý về tài nguyên client:** với `BodyHandlers.ofInputStream()`, phải đọc/đóng `InputStream`. Nếu không đóng, connection có thể không được giải phóng như mong muốn, gây cạn connection pool trong suite lớn. Nếu test cố ý hủy giữa chừng, đóng stream rồi kiểm behavior phù hợp; không coi cancellation là rollback file upload.

**Phân biệt memory:** hàm `multipartBody(...)` trong live test **có tạo `byte[]` của request**, nhưng file test này bị giới hạn 512KiB nên phù hợp. Với **upload nhiều GB**, dùng streaming request body publisher/file-based client thay vì tự dựng nguyên multipart body trong RAM.

## 12. Chạy Gradle và kết quả dự kiến

Trong một dự án Spring Boot 3.5.x đã có plugin/versions được quản lý, bổ sung vào `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là **đoạn cấu hình**, không phải file `build.gradle` đầy đủ. Với Java toolchain 17+, có đủ `spring-webmvc`, embedded servlet container, `spring-test`, Jackson và JUnit Jupiter qua các starters.

Chạy cả hai lớp test:

~~~bash
./gradlew test --tests example.filehttp.FileMockMvcTest --tests example.filehttp.FileLiveHttpTest
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.filehttp.FileMockMvcTest --tests example.filehttp.FileLiveHttpTest
~~~

**Kết quả kỳ vọng:** tổng cộng **12 phương thức JUnit Jupiter PASS** (7 MockMvc + 5 HTTP live) trong dự án có đúng package và dependencies, không có Spring Security hoặc các custom configs làm đổi hợp đồng. Test **không in stdout của riêng ứng dụng**; log Spring Boot và báo cáo Gradle có thể thay đổi theo version, máy chạy và random port. `BUILD SUCCESSFUL` là kết quả build kỳ vọng, không phải log đã được ghi nhận.

Nếu dùng một project đã có Spring Security, HTTP endpoints có thể bị chặn bởi auth/CSRF. Hãy bổ sung chính sách security và test credentials/`spring-security-test` phù hợp, không tắt filters toàn cục chỉ để nhận 200.

### Kết quả khác nhau giữa MockMvc và server thật là tín hiệu quan trọng

- MockMvc upload PASS, live upload FAIL → kiểm boundary/CRLF, multipart resolver và container limits.
- MockMvc download bytes đúng, live download bị cắt → kiểm server/network/timeout/framing/stream writer.
- Live response status 200 nhưng body thiếu bytes → kiểm client **đã đọc hết stream** và so với Content-Length.
- Header Content-Disposition đúng nhưng browser không download → kiểm encoding filename, CORS, cross-origin download policy, MIME, CSP và hành vi của client/browser.
- Download 206 sai Content-Range → kiểm Resource type, status 200 gốc, range parser, conditional headers và proxy.

## 13. Khi phản hồi thực sự rất lớn: thiết kế kiểm thử an toàn

### 13.1 Tránh dùng byte[] ở cả hai phía

Ví dụ dùng `ByteArrayResource` là phù hợp **cho uploaded files nhỏ**. Với file 5GB, production nên dùng:

- `FileSystemResource` hoặc một Resource đọc file từ disk một cách lazy, khi file đã được phép truy cập.
- `StreamingResponseBody` để ghi từng chunk từ InputStream/object storage.
- `ResourceRegion`/`ResponseEntity<Resource>` đúng điều kiện khi hỗ trợ range.
- Object storage presigned URL cho tải xuống trực tiếp nếu kiến trúc cho phép, với TTL và ACL phù hợp.

Không dùng `file.getBytes()`, `Files.readAllBytes(...)` hoặc `bodyToMono(byte[].class)` cho các file khổng lồ. Chúng có thể tạo bản sao dữ liệu và làm tăng heap. `Content-Length` không nói gì về memory của quá trình tạo body.

### 13.2 Kiểm bằng checksum, không sao chép file vào test heap

Khi không có quy luật byte đơn giản, kiểm hash:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
long total = 0L;

try (InputStream in = response.body()) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = in.read(buffer)) != -1) {
        digest.update(buffer, 0, n);
        total += n;
    }
}

byte[] sha256 = digest.digest();
assertEquals(expectedSize, total);
assertArrayEquals(expectedSha256, sha256);
~~~

Đây là **đoạn minh họa** bên trong test có `HttpResponse<InputStream> response`, `expectedSize` và `expectedSha256` đã biết, cần import `MessageDigest` và assertions. Hash phải được xây dựng **độc lập** từ fixture nguồn hoặc giá trị tin cậy; nếu test tính expected hash bằng cách gọi lại chính hàm server đang bị kiểm, cả hai có thể cùng sai.

Bài test này chỉ giữ buffer 8KiB và digest state, thay vì đọc một file 5GB vào RAM. Cần đồng thời xác minh Content-Type, owner authorization, disposition và status.

### 13.3 Không kiểm “không tăng heap” chỉ bằng 1 request

Đọc stream theo khối chứng minh **client test không chủ động gom toàn body**, nhưng không tự chứng minh heap của server luôn ổn định. Muốn đánh giá bộ nhớ production:

- Thử file đủ lớn và nhiều kết nối đồng thời trong môi trường kiểm soát.
- Theo dõi heap/RSS/GC và native/direct buffers, không chỉ `Runtime.freeMemory()` trong một lần đo.
- Kiểm thread pool/executor queue khi client chậm hoặc bỏ cuộc.
- Giới hạn tài nguyên (upload size, active streams, disk quota, timeouts) và test hành vi khi bị từ chối.
- Kiểm object storage API/client có thực sự stream hay tự buffer.
- Nếu cần throughput/latency, tách performance/load test khỏi suite unit/CI cơ bản.

Không dùng `Thread.sleep(...)` để giả lập client chậm một cách vô hạn. Với test tốc độ/chậm, dùng client/server có điều kiện kiểm soát, deadline rõ và metric quan sát được.

### 13.4 EOF, timeout, cancel và HTTP failure

Khi download lớn, test cần đọc cho đến khi `InputStream.read(...) == -1`; nếu `Content-Length` là 2MiB mà chỉ nhận 1MiB, **đó là lỗi**, kể cả status ban đầu là 200.

Trên đường truyền thực:

- `HttpRequest.timeout(Duration)` giới hạn một khía cạnh thời gian của request; behavior timeout/đọc stream có thể phụ thuộc BodyHandler và version JDK. Với stream dài, cần quản lý deadline quan sát toàn operation theo thiết kế test.
- Lỗi sau khi headers đã gửi có thể biểu hiện là IOException/truncation; không thể yêu cầu server đổi status thành 500 sau khi response đã commit.
- Nếu client cancel/đóng stream, server có thể gặp broken pipe hoặc connection reset. Không để test suite coi log đó là business exception bất ngờ nếu tình huống đã được mô phỏng có chủ đích.
- Với upload thất bại giữa chừng, cần xử lý file temp/partial objects, transaction/cleanup và không ghi nhận metadata “hoàn tất” khi chưa nhận đủ bytes.

## 14. HTTP Range, ETag và caching

Các tệp lớn/video thường cần hỗ trợ **resume download** bằng Range:

~~~http
GET /api/files/F-1
Range: bytes=1000-1999
~~~

Trong trường hợp thành công, server trả 206 với đoạn 1.000 bytes; `Content-Range` mô tả offset và tổng kích thước. Bài live test ở mục 11 dùng file nhỏ và `bytes=2-4` để chứng minh protocol cụ thể.

Ngoài Range, production có thể có:

- **ETag:** định danh version nội dung, hữu ích cho `If-None-Match` và `If-Range`.
- **Last-Modified:** caching/revalidation, cần đồng hồ và metadata nhất quán.
- **Accept-Ranges: bytes:** chỉ quảng bá khi server thực sự đáp ứng range.
- **416 Range Not Satisfiable:** range vượt giới hạn file, có thể kèm `Content-Range: bytes */size`.
- **206 multipart/byteranges:** khi request nhiều khoảng byte, Content-Type có thể là multipart/byteranges và boundary riêng, **khác multipart/form-data của upload**.
- **HEAD:** một số client dùng để lấy metadata mà không tải body; test headers, body trống và Content-Length theo contract.

Đừng khẳng định `StreamingResponseBody` tự thực hiện Range; endpoint `large` trong ví dụ sinh stream tuần tự và **không được thiết kế để xử lý Range**. Nếu cần resume, dùng storage có random access hoặc tính toán đoạn stream cụ thể, và test các trường hợp bình thường/không hợp lệ.

## 15. Spring WebFlux: cùng mục tiêu, API khác

Nếu ứng dụng dùng Spring WebFlux, upload thường sử dụng `FilePart` hoặc `PartEvent`, còn large response có thể trả `Flux<DataBuffer>`. Không copy nguyên controller `MultipartFile`/`StreamingResponseBody` từ MVC sang WebFlux mà không chỉnh kiến trúc.

Một mẫu WebFlux upload (chỉ minh họa, cần định nghĩa đích và quản lý cleanup):

~~~java
@PostMapping(
        path = "/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<ResponseEntity<Void>> upload(
        @RequestPart("file") FilePart file) {
    Path target = Path.of("/controlled-test-storage", "safe.bin");
    return file.transferTo(target)
            .thenReturn(ResponseEntity.accepted().build());
}
~~~

Đoạn trên **không phải file độc lập**: phải có import `Mono`, `FilePart`, `Path`, `ResponseEntity`, mapping/controller và một thư mục tồn tại; tên target là minh họa, không được dùng đường dẫn production. Trong thực tế phải kiểm permission, filename validation, temp file, size limits và xử lý lỗi I/O.

Khi làm việc với `Flux<DataBuffer>` hoặc `PartEvent`, buffer phải được tiêu thụ/chuyển tiếp/**release** đúng hợp đồng để tránh memory leaks. Reactive non-blocking không miễn trách nhiệm quản lý buffer.

### WebTestClient cho response lớn

`WebTestClient` có DSL `expectStatus`/`expectHeader`/`expectBody` thuận tiện, nhưng `expectBody(byte[].class)` hoặc `bodyToMono(byte[].class)` có thể gom cả body và chạm `maxInMemorySize`. Với streaming response, có thể dùng `returnResult(...)` và xử lý `Flux<DataBuffer>` theo cách bảo đảm giải phóng buffers, hoặc dùng HTTP client streaming thích hợp.

**Không sửa lỗi `DataBufferLimitException` bằng cách vô hạn tăng `maxInMemorySize` trên mọi test.** Trước hết xem API có nên stream hay không, client có đang aggregate không, và mức giới hạn hợp lý cho contract.

## 16. Bảo mật upload/download và những test bắt buộc khi đưa lên production

Đây là phạm vi rủi ro cao vì server nhận dữ liệu không đáng tin và trả nội dung có thể khiến browser xử lý đặc biệt.

### 16.1 Upload

- **Filename traversal:** client có thể gửi `../../etc/passwd` hoặc `C:\temp\evil.exe`. Không ghép filename gốc vào filesystem path. Chuẩn hóa basename, allowlist và lưu bằng storage key riêng.
- **Media type giả:** client tự khai báo `image/png` cho file thực chất là executable. Dùng file signature/sniffing và policy phù hợp, không tin `MultipartFile.getContentType()` như bằng chứng an toàn.
- **Size limit:** kiểm cả per-file, per-request, số part, ngưỡng disk và quota tổng; container limits và app rule là hai tầng khác nhau.
- **Zip bombs, decompression, parser bugs:** nếu server giải nén hoặc xử lý ảnh/PDF, đặt giới hạn kích thước sau giải nén, số entry, độ sâu và timeout.
- **Virus scanning và quarantine:** nhận upload không đồng nghĩa “sẵn sàng download công khai”; trạng thái scan phải tách biệt khi chính sách yêu cầu.
- **Authorization/tenant:** file phải gắn owner và kiểm quyền trước khi lưu/đọc; đoán được ID không cấp quyền.
- **Temp file cleanup:** upload lỗi/timeout cần xóa tệp tạm hoặc object dang dở; tránh lấp đầy disk.
- **Metadata/XSS:** response filename/Content-Disposition phải escape; nếu hiển thị tên tệp trong HTML, encode theo context.

### 16.2 Download

- Kiểm **401/403** khi chưa xác thực/không có quyền; `404` trong trường hợp cần che sự tồn tại của đối tượng phải tuân thủ policy.
- Kiểm Content-Disposition `attachment` cho nội dung không tin cậy; nếu cố ý inline, cần CSP, MIME chính xác và `X-Content-Type-Options: nosniff` theo policy.
- Không trả local filesystem paths, temporary credentials hoặc signed URL lâu sống trong response/log.
- Không dùng byte array/stream khác owner để đáp ứng ID, đặc biệt khi cache key không bao gồm tenant.
- Với Range và caching, kiểm quyền **trước** khi trả bất kỳ partial bytes; `Range` không phải cách vượt ACL.

### 16.3 Ví dụ các test nên bổ sung khi production có auth

| Case | Kỳ vọng |
| --- | --- |
| User A tải file của user B | 403 hoặc 404 theo security contract, không trả bytes |
| Anonymous upload nếu cần auth | 401/403, không ghi storage |
| CSRF với form upload | Token đúng mới cho request nếu policy yêu cầu |
| Filename chứa slash, backslash, quote, CRLF, Unicode | Không traversal hoặc header injection |
| Upload vượt quota tổng dù từng file nhỏ | Status lỗi có ngữ nghĩa; không để state nửa vời |
| MIME khai báo sai thực tế | Từ chối hoặc quarantine theo policy |
| Tải file có ETag cũ/Range sai | 200/206/304/416 đúng hợp đồng |
| Client mất kết nối giữa download | Resource/stream được đóng và metrics phản ánh lỗi |

Ví dụ mini không cấu hình Security; không lấy đó làm mặc định cho ứng dụng thật.

## 17. Lỗi thường gặp khi kiểm upload/download/large response

**1. Dùng MockMvc rồi tuyên bố multipart parser đã được kiểm.**  
MockMvc tạo `MockMultipartHttpServletRequest`, không parse raw multipart qua embedded container. Cần thêm ít nhất một test `RANDOM_PORT`.

**2. Dùng `content().string(...)` hoặc `BodyHandlers.ofString()` cho file binary.**  
Text decoding có thể đổi bytes. Dùng byte array cho file nhỏ, InputStream/checksum cho file lớn.

**3. Chỉ kiểm status 200 mà không kiểm Content-Disposition hoặc bytes.**  
Controller có thể trả HTML/JSON lỗi với status sai thiết kế, hoặc đúng headers nhưng body bị hỏng. Assert tất cả thuộc hợp đồng.

**4. So sánh ID mới bằng literal cố định.**  
IDs có thể được sinh mỗi lần. Parse ID/Location từ response upload rồi dùng chính nó để download; không dựa vào thứ tự test hay ID bắt đầu bằng F-1.

**5. Upload quá lớn trong MockMvc rồi mong `spring.servlet.multipart.max-file-size` tự từ chối.**  
MockMultipartFile không qua parser container. Chỉ test app limit ở MockMvc; test parser limit qua HTTP thật.

**6. Đo kích thước file bằng số ký tự.**  
`String.length()` đo UTF-16 code units, không bằng số byte UTF-8 hay số byte binary. Dùng `MultipartFile.getSize()`, `byte[].length` hoặc số byte đọc từ stream.

**7. Trust filename từ client.**  
Có nguy cơ path traversal/header injection. Normalize, allowlist, dùng storage-generated keys và kiểm lại đường dẫn sau resolve theo chính sách.

**8. Trả Content-Length sai cho streaming.**  
Client có thể chờ thêm hoặc coi response bị truncate. Chỉ đặt khi biết chắc số bytes được viết, còn không để container xử lý framing.

**9. Kiểm “streaming” bằng cách đọc toàn bộ response vào byte[].**  
Test đó vẫn có thể kiểm đúng bytes nếu nhỏ, nhưng không chứng minh client không bị OOM. Dùng `ofInputStream()`/`ofFile()` và đọc đến EOF.

**10. Khẳng định truyền chunked vì dùng StreamingResponseBody.**  
HTTP/1.1/2, Content-Length và compression có thể dẫn đến framing khác nhau. Test contract dữ liệu, đừng pin header tầng transport nếu không yêu cầu.

**11. Quên asyncDispatch với MockMvc streaming.**  
Response chưa hoàn tất khi async bắt đầu. Gọi `request().asyncStarted()`, `asyncDispatch(...)` và kiểm response cuối.

**12. Không đóng HTTP InputStream.**  
Dễ rò connection/không trả kết nối về pool. Dùng try-with-resources và đọc đến EOF.

**13. Tưởng status 200 bảo đảm toàn body đã nhận.**  
Lỗi giữa luồng sau commit có thể chỉ hiện như EOF sớm/IOException. So size và checksum/bytes khi stream kết thúc.

**14. Test 413 với payload lớn hơn cả container max rồi mong controller handler luôn chạy.**  
Container có thể từ chối trước controller, response/connection behavior tùy cấu hình. Nếu muốn kiểm business limit, chọn size dưới container max; parser limit cần test riêng.

**15. Test HTTP thật nhưng vẫn muốn test @Transactional rollback toàn bộ server.**  
Client và server xử lý trên thread/transaction khác; rollback test thread không tự rollback dữ liệu đã commit trong HTTP handler. Dùng storage test cô lập và cleanup rõ.

**16. Đặt timeout quá nhỏ hoặc dùng `Thread.sleep` để chờ stream.**  
Dễ flaky trên CI. Dùng deadline hợp lý, completion/EOF rõ, xác minh async executor và không block tùy tiện.

**17. Dùng chung in-memory store có mutable state giữa tests mà không nghĩ tới cache.**  
`@SpringBootTest` context có thể được tái sử dụng. Test nên lấy ID từ response, không hardcode ID hoặc dựa vào số bản ghi chung; với stateful business phải cleanup.

**18. Nghĩ multipart/form-data của upload giống multipart/byteranges.**  
Chúng là hai định dạng/case khác nhau; multipart/byteranges là response cho nhiều byte ranges, không phải upload form fields.

## 18. Quy trình QA một endpoint file trong Spring Boot

1. **Định nghĩa contract:** method/URI, part names, status codes, size limits, headers, response schema/bytes.
2. **Chọn hai lớp test:** MockMvc cho nhánh nhanh, RANDOM_PORT cho raw multipart/container/stream.
3. **Dùng fixture binary:** có 0x00, CR/LF, non-ASCII byte; không chỉ ASCII text.
4. **Upload request thực:** boundary/CRLF đúng, content type multipart, part `file`, filename và bytes.
5. **Assert upload response:** 201, JSON metadata, Location; chỉ dựa vào ID thực từ response.
6. **Download bằng ID vừa tạo:** kiểm 200, Content-Type, Content-Disposition, Content-Length và bytes toàn vẹn.
7. **Kiểm negative cases:** empty/missing part, wrong media type, quá app limit, parser limit, not found, unauthorized.
8. **Kiểm range nếu hỗ trợ:** 206, Content-Range, đoạn byte chính xác, invalid range.
9. **Kiểm large response:** yêu cầu size giới hạn hợp lệ; đọc theo buffer cố định, kiểm từng block/hash, EOF và tổng bytes.
10. **Kiểm async/timeout:** MockMvc streaming cần asyncDispatch; live client phải có deadline/đóng InputStream.
11. **Kiểm resource usage riêng:** heap, disk temp, executor, load, slow clients, cancellation nếu API có rủi ro tải cao.
12. **Kiểm storage/security thật:** quotas, permission, virus scanning, object store, path traversal/ACL.
13. **Tách evidence:** MockMvc không chứng minh TCP; live HTTP với in-memory store không chứng minh cloud storage, antivirus hay CDN.
14. **Chạy CI ổn định:** random port, fixture và cleanup độc lập, không cần production credentials.

### Checklist cuối

- [ ] Client thực sự gửi `multipart/form-data` với boundary và part name đúng.
- [ ] Có ít nhất một test upload qua server thật, không chỉ MockMultipartFile.
- [ ] Empty, missing, wrong media type, oversize được kiểm theo status contract.
- [ ] Tên tệp input không dùng trực tiếp làm filesystem path hoặc response header không escape.
- [ ] Response upload 201/Location/JSON metadata đúng và không lộ storage path.
- [ ] Download kiểm **bytes** chứ không chuyển binary sang String.
- [ ] Content-Type, Content-Disposition, Content-Length được kiểm khi thuộc hợp đồng.
- [ ] Range/206/Content-Range được kiểm nếu endpoint hỗ trợ resume.
- [ ] Test response lớn đọc stream theo khối hoặc ghi file, không materialize toàn body trong test heap.
- [ ] Tổng bytes/EOF/checksum được kiểm; status ban đầu 200 không được xem là đủ.
- [ ] MockMvc async dùng `asyncDispatch` khi cần.
- [ ] Giới hạn server multipart và application rule được kiểm **riêng**.
- [ ] Có test authorization/tenant, storage quota và cleanup tại đúng tầng trong production.
- [ ] Không hardcode random port hay thứ tự ID/fixture giữa các test methods.
- [ ] Có chiến lược timeout, cancellation, task executor và resource monitoring.
- [ ] Dự án test dùng đúng Java/Spring Boot version của API/imports; không dùng MVC `MultipartFile` như WebFlux `FilePart`.

**Kết luận:** kiểm thử upload/download có giá trị khi đi hết một vòng **multipart request → xử lý server → status/Location → download → đúng từng byte**. Với body lớn, cần kiểm HTTP thực qua một client **tiêu thụ theo luồng**, không chỉ kiểm status hoặc dùng mock response buffer. Kết hợp MockMvc và RANDOM_PORT để phát hiện lỗi ở cả logic MVC lẫn protocol/container, đồng thời kiểm bảo mật và tài nguyên ở những tầng tương ứng.

### Tài liệu tham khảo chính thức

- [Spring Framework — Multipart MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): `MultipartFile`, `@RequestParam`, `@RequestPart` và cách bind multipart.
- [Spring Boot 3.5 — Servlet Multipart Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.servlet.multipart.max-file-size`, `max-request-size`, threshold.
- [Spring Boot — Handling Multipart Uploads](https://docs.spring.io/spring-boot/how-to/spring-mvc.html): xử lý upload và các giới hạn container.
- [Spring Framework — MockMvc Performing Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/requests.html): `multipart(...)` dùng mock servlet request, không parse raw multipart.
- [Spring Framework — Testing Async MVC Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): `request().asyncStarted()`, `asyncDispatch(...)`.
- [Spring Framework — MVC Async and Streaming](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): `StreamingResponseBody`, async executor, timeouts.
- [Spring Framework — HTTP Range Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-range.html): `Resource`/`ResponseEntity<Resource>`, `206`, giới hạn `InputStreamResource`.
- [Spring Framework — Response Body with Resource](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html): response Resource và các lưu ý stream.
- [Java 17 HttpClient API](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP request/response, BodyPublishers/BodyHandlers.
- [Spring Framework — WebFlux Multipart](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html): `FilePart` và `PartEvent`, giải phóng `DataBuffer`.
