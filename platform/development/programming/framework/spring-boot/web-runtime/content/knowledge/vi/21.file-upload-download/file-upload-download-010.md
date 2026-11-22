# Range request, tải tiếp và giới hạn hỗ trợ theo cách trả tài nguyên trong Spring Boot

**Ngữ cảnh:** Spring Boot → web-runtime → Tải và nhận tệp. Bài này trình bày HTTP byte-range request, cơ chế **tải tiếp (resume)**, status `200/206/416`, các header `Range`, `Content-Range`, `Accept-Ranges`, `If-Range`, sự khác biệt giữa các kiểu response của Spring MVC và Spring WebFlux, cách thử bằng `curl`, xử lý an toàn và giới hạn hiệu năng. Ví dụ chính là **Java 17, Spring Boot 3.5.16, Spring Framework 6.2.x, Maven, Servlet/Spring MVC**. Code WebFlux được đánh dấu minh họa riêng.

## 1. Bài toán: vì sao tải file lớn phải hỗ trợ từng phần?

Nếu server luôn gửi toàn bộ file từ byte đầu tiên, một client đã nhận 900 MB của file 1 GB rồi bị rớt mạng có thể phải tải lại 1 GB. **HTTP Range request** cho phép client yêu cầu **một hoặc nhiều đoạn byte của một representation**. Nhờ đó trình duyệt, trình quản lý download và một số media player có thể:

- tiếp tục tải từ offset đã nhận, nếu bản file trên server không thay đổi;
- chỉ tải khúc cần phát của video/audio khi tua đến vị trí khác;
- chia việc tải thành nhiều đoạn có kiểm soát;
- giảm dữ liệu truyền lại sau khi mất kết nối.

**Không phải cứ có HTTP streaming là tự resume được.** Việc server truyền dần từng chunk để tiết kiệm bộ nhớ khác với **random access** theo byte offset. Cách tạo HTTP response quyết định Spring có thể xử lý `Range` tự động hay không.

~~~text
Client đã có 0..499 (500 byte)
          │
          └── GET /files/report.bin
              Range: bytes=500-
                        │
                        ▼
                 Server có hỗ trợ Range?
                    │               │
                    ▼               ▼
               206 Partial       200 OK (gửi nguyên file)
               Content           Client không được append bừa
                    │
                    ▼
               Content-Range: bytes 500-999/1000
               Body gồm 500 byte cuối
                    │
                    ▼
          Client xác minh version, offset,
          độ dài rồi ghép thành 1.000 byte
~~~

Range dùng để **đọc một phần response**. Nó không phải kỹ thuật resumable **upload**: upload theo chunk có offset, session/token và phương thức riêng (ví dụ protocol tus, multipart object storage). Đừng nhầm request `Range` với upload `Content-Range` trên PUT nếu chưa có hợp đồng API cụ thể.

## 2. HTTP byte ranges theo RFC 9110

### 2.1. Các header quan trọng

| Header | Chiều | Vai trò | Ví dụ |
| --- | --- | --- | --- |
| **`Range`** | Request | Client xin một hoặc nhiều đoạn của representation | `Range: bytes=0-1023` |
| **`Accept-Ranges`** | Response | Server quảng bá loại range hỗ trợ | `Accept-Ranges: bytes` |
| **`Content-Range`** | Response `206`/`416` | Phần được trả và độ dài representation đầy đủ | `Content-Range: bytes 0-1023/10000` |
| **`If-Range`** | Request kèm `Range` | Chỉ lấy đoạn nếu representation chưa đổi; ngược lại mong đợi body đầy đủ | `If-Range: "file-v5"` |
| `ETag` | Response | Validator cho representation, nên ưu tiên **strong ETag** khi nối byte an toàn | `ETag: "file-v5"` |
| `Last-Modified` | Response | Thời điểm thay đổi, có thể dùng conditional request | `Last-Modified: Wed, 21 Oct 2015 07:28:00 GMT` |
| `Content-Length` | Response | Số byte của **body response hiện tại**, thường nhỏ hơn file gốc khi `206` | `Content-Length: 1024` |
| `Content-Disposition` | Response | Gợi ý browser hiển thị hay tải file và tên file | `attachment; filename="report.pdf"` |

**`bytes` đếm byte (octet), không đếm ký tự, dòng hay code point.** Vị trí bắt đầu là **0**; vị trí cuối **bao gồm** trong khoảng. Ví dụ file có độ dài chính xác 26 byte chứa chuỗi ASCII `ABCDEFGHIJKLMNOPQRSTUVWXYZ` thì:

| Request header | Byte positions | Body mong đợi |
| --- | --- | --- |
| `Range: bytes=0-4` | 0 đến 4 | `ABCDE` (5 byte) |
| `Range: bytes=10-14` | 10 đến 14 | `KLMNO` (5 byte) |
| `Range: bytes=20-` | 20 đến cuối | `UVWXYZ` (6 byte) |
| `Range: bytes=-4` | 4 byte cuối | `WXYZ` |
| `Range: bytes=0-2,23-25` | 2 đoạn rời nhau | `ABC` và `XYZ`, thường body multipart |
| `Range: bytes=100-` | Bắt đầu sau cuối file 26 byte | Không thỏa mãn, thường `416` |

Nếu client gửi `Range: bytes=20-50` mà file chỉ dài 26 byte, phạm vi hợp lệ có thể được thu hẹp thành **20–25**, với `Content-Range: bytes 20-25/26`. Không lấy byte 50 ngoài file.

### 2.2. Ba status chính

**`200 OK`**: server trả representation đầy đủ. Có thể do client không gửi `Range`, server không hỗ trợ, server chủ động bỏ qua `Range`, hoặc `If-Range` không thỏa điều kiện trên implementation tuân chuẩn. Khi nhận 200, client resume **không được append** body vào file đã tải dở; phải thay bằng bản hoàn chỉnh sau khi kiểm tra.

**`206 Partial Content`**: server thỏa mãn `Range`. Với **một** đoạn, response có `Content-Range` mô tả đoạn byte và tổng độ dài. Ví dụ giả định (các header như Date được rút gọn):

~~~http
GET /files/alphabet HTTP/1.1
Host: localhost:8080
Range: bytes=10-14

HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Type: text/plain
Content-Range: bytes 10-14/26
Content-Length: 5

KLMNO
~~~

`Content-Length: 5` nói về **body của phản hồi 206**; file gốc vẫn có 26 byte theo `Content-Range`. Không hiểu nhầm 5 là tổng độ dài file.

**`416 Range Not Satisfiable`**: không có đoạn yêu cầu nào thỏa mãn, hoặc server từ chối một bộ range quá nhiều/không hợp lý. Khi biết độ dài gốc là 26 byte, thông tin hữu ích là:

~~~http
HTTP/1.1 416 Range Not Satisfiable
Content-Range: bytes */26
~~~

Theo RFC 9110, một server **có thể bỏ qua `Range`** và trả 200 trong một số tình huống; vì vậy client phải đọc status và headers thực tế thay vì cứng nhắc cho rằng request sai luôn nhận 416.

### 2.3. Một request chứa nhiều range

Ví dụ:

~~~http
Range: bytes=0-2,23-25
~~~

Server có thể trả `206` với `Content-Type: multipart/byteranges; boundary=...`. Mỗi part chứa `Content-Range` và phần byte tương ứng. Đây là **multipart response cho nhiều đoạn tải xuống**, khác `multipart/form-data` vốn thường dùng **upload form/file**.

~~~http
HTTP/1.1 206 Partial Content
Content-Type: multipart/byteranges; boundary=demo

--demo
Content-Type: text/plain
Content-Range: bytes 0-2/26

ABC
--demo
Content-Type: text/plain
Content-Range: bytes 23-25/26

XYZ
--demo--
~~~

Đoạn trên chỉ là **sơ đồ biểu diễn dễ đọc**; boundary, CRLF và các header phát sinh sẽ khác trong response thật. Không tự ghép chuỗi body multipart rồi ghi nối trực tiếp vào tệp. Client phải parse từng part và ghi đúng offset. Server cũng có quyền từ chối bộ range có quá nhiều đoạn nhỏ, chồng lấn hoặc gây tải bất hợp lý.

### 2.4. `Accept-Ranges` chỉ là tín hiệu

`Accept-Ranges: bytes` báo rằng server dự kiến hỗ trợ byte-range; `Accept-Ranges: none` báo không hỗ trợ. **Thiếu `Accept-Ranges` không tự động chứng minh server không hỗ trợ**, và có header này cũng không bảo đảm mọi request tương lai trả 206. CDN, reverse proxy, content encoding hay phiên bản tài nguyên có thể làm hành vi khác.

Cách kiểm tra đáng tin là **gửi một request `Range` thực sự**, rồi so status `206` và `Content-Range`, độ dài/body.

## 3. Tải tiếp cần kiểm tra tính toàn vẹn của representation

Giả sử client đã nhận 500 byte của version A. Trong lúc kết nối mất, server phát hành version B với nội dung khác nhưng URL giữ nguyên. Nếu client đơn giản xin `Range: bytes=500-` rồi append vào 500 byte cũ, file kết quả có thể là **nửa A + nửa B**, bị hỏng mà vẫn có đúng kích thước.

### 3.1. Cơ chế `If-Range` theo HTTP

**Nếu client giữ strong ETag** của bản đã tải, nó có thể yêu cầu:

~~~http
GET /files/report HTTP/1.1
Range: bytes=500-
If-Range: "sha256-or-version-of-A"
~~~

Với server tuân thủ `If-Range`:
- Validator vẫn khớp: trả **206** cho đoạn cần tải.
- Validator không còn khớp: bỏ Range và trả **200** kèm representation mới hoàn chỉnh. Client **thay** file tạm, không append.
- Không có validator đáng tin: client nên sử dụng URL có version bất biến, kiểm tra metadata/checksum trước khi resume hoặc tải lại file.

**`If-Range` không giống `If-None-Match`.** `If-None-Match` là điều kiện cache/GET có thể cho `304 Not Modified`, trong khi `If-Range` được thiết kế để chọn giữa **partial 206** và **full 200**. Theo RFC, không gửi `If-Range` đơn lẻ khi không có `Range`. **Không dùng weak ETag** (ví dụ `W/"abc"`) trong `If-Range`; HTTP date chỉ dùng khi đủ điều kiện là strong validator.

### 3.2. Giới hạn thực tế của phiên bản framework

Spring Framework hỗ trợ **Range tự động** cho nhiều response dạng `Resource`, nhưng điều đó **không đồng nghĩa mọi phiên bản đều hỗ trợ đầy đủ từng nhánh của `If-Range`**. Đặc biệt ở **Spring Framework 6.2.x** (được dùng cùng Spring Boot 3.5.x), phải **test trực tiếp kịch bản validator đổi giữa lúc tải**; không dựa vào việc Range 206 cơ bản chạy tốt để kết luận `If-Range` được bảo đảm. Dự án Spring Framework có thay đổi **“Honor If-Range for resource range requests” (#37218)** trong nhánh 7.1; hành vi này không nên mặc định áp cho 6.2.

Nếu download đòi hỏi tính nhất quán chặt trên Boot 3.5, các chiến lược thực tế:
1. **URL/version hoặc object key bất biến:** mỗi phiên bản file có ID/version riêng, không thay bytes dưới cùng ID trong lúc tải.
2. **Kiểm tra metadata ở ứng dụng** trước khi trả range: version/ETag client giữ phải tương ứng với object thực sự được serve; mismatch trả full 200 hoặc yêu cầu restart theo hợp đồng API.
3. **Checksum** và so sánh tổng byte sau khi download xong; nếu không khớp thì loại file bị ghép sai.
4. **Integration test cho `Range` + `If-Range` cùng proxy/CDN** trên đúng Spring Framework/Boot đang chạy; không chỉ unit test parser.

Không dùng `Content-Length` như validator: hai phiên bản file có thể **cùng kích thước nhưng nội dung khác nhau**.

### 3.3. Resume algorithm phía client

Một client download đơn giản nên:
1. Lấy URL, version/strong ETag và kích thước của file. Lưu metadata bên cạnh file tạm.
2. Nếu chưa có dữ liệu, GET bình thường hoặc xin range đầu; giữ bytes vào file tạm.
3. Sau đứt mạng, lấy offset thực `N` từ độ dài file tạm, gửi `Range: bytes=N-` và `If-Range`/version khi đủ điều kiện.
4. Nhận `206`: xác thực `Content-Range` bắt đầu **đúng N**, tổng length/validator hợp lý; mới append bytes.
5. Nhận `200`: bỏ file tạm cũ và ghi **toàn bộ** body mới từ byte 0.
6. Nhận `416`: kiểm tra tổng length từ `Content-Range: bytes */L`; nếu `N=L` có thể file đã đủ, **nhưng vẫn cần checksum/version**; nếu `N>L` hoặc validator khác, restart.
7. Nhận lỗi mạng/`5xx`/`429`: retry có giới hạn, exponential backoff và timeout; không ghép nội dung chưa xác minh.
8. Kiểm tra tổng size và checksum trước khi đổi tên file tạm thành artifact chính thức.

Đối với một URL dữ liệu động sinh lại theo thời gian, random access chỉ có ý nghĩa khi server giữ được **một snapshot ổn định** xuyên suốt các request.

## 4. Spring MVC hỗ trợ Range tự động khi nào?

Spring MVC có cơ chế parse `Range` qua `HttpRange` rồi tạo `ResourceRegion`, được ghi bởi `ResourceRegionHttpMessageConverter`. Các endpoint trả đúng kiểu **`Resource`** thường được framework xử lý Range mà không cần tự đọc offset hay tự đặt status 206.

Điều kiện thực tế trong Spring Framework:
- Controller `@ResponseBody`/`@RestController` trả **`Resource`** hoặc **`ResponseEntity<Resource>`**.
- Với `ResponseEntity<Resource>`, status khởi đầu phải là **`200 OK`** để Spring có thể chuyển thành 206 khi Range hợp lệ.
- Resource **không** là `InputStreamResource` (bao gồm trường hợp stream chỉ đọc một lượt).
- Static resource handler của MVC cũng hỗ trợ Range cho tài nguyên thích hợp.
- Các message converters/handler cấu hình mặc định hoặc tương thích phải còn hoạt động; custom response writing có thể đi lối khác.

### 4.1. So sánh kiểu trả nội dung và khả năng auto-range

| Cách trả file | Tính chất | `Range` tự động? | Nên dùng khi |
| --- | --- | --- | --- |
| **`ResponseEntity<Resource>` + `FileSystemResource`** | File có độ dài, đọc lặp lại/seek được | **Có**, khi status gốc 200 | File lưu trên disk, cần partial download |
| **`ResponseEntity<Resource>` + `ByteArrayResource`** | Bytes sẵn trong RAM, stream lặp lại được | **Có**, khi status gốc 200 | File nhỏ, dữ liệu có sẵn trong bộ nhớ |
| **`ClassPathResource`** qua controller/resource handler | File/resource trong classpath/JAR, có thể reopen | **Thường có**, nếu converter nhận kiểu Resource thích hợp | Asset đóng gói hoặc file nhỏ/vừa |
| Static resource ở `src/main/resources/static/` | Boot resource handler có sẵn | **Có** với static resource phù hợp | CSS/JS/ảnh/file public |
| **`InputStreamResource`** | Stream chỉ mở/đọc một lần, không hỗ trợ random access chung | **Không** theo cơ chế auto-range nói trên | Proxy/stream một chiều, file từ nguồn chỉ hỗ trợ stream |
| **`ResponseEntity<byte[]>`** | Byte array được message converter ghi trực tiếp | **Không**, không phải Resource | Payload nhỏ, không yêu cầu Range |
| **`StreamingResponseBody`** (MVC) | Ghi trực tiếp vào output stream bất đồng bộ | **Không** chỉ nhờ dùng kiểu này | Stream lớn/được tạo dần; tự xử lý Range nếu cần |
| `HttpServletResponse.getOutputStream()` | Tự điều khiển toàn bộ body/status | **Không**, developer chịu trách nhiệm | Logic truyền đặc thù |
| `ResponseEntity<Flux<DataBuffer>>` (WebFlux) | Reactive stream của các buffer | **Không** nhờ kiểu Flux | Stream reactive hoặc proxy dữ liệu |
| `ResponseEntity<Resource>` (WebFlux) | Reactive HTTP writer có Resource | **Có**, điều kiện như Resource phù hợp | File/download endpoint reactive |

**Chú ý:** `FileSystemResource` có thể stream file mà không cần load toàn bộ vào RAM. `ByteArrayResource` có thể hỗ trợ Range nhưng **toàn bộ file đã nằm trong bộ nhớ**; đừng xây `ByteArrayResource(Files.readAllBytes(veryLargeFile))` cho file multi-GB. Với `InputStreamResource`, ngay cả khi bạn biết file length và tự set `Content-Length`, điều đó cũng **không biến stream một lượt thành seekable/repeatable**.

Với static asset đóng gói JAR, resource có thể cần tìm và mở lại stream, nên hiệu suất truy cập byte ngẫu nhiên có thể khác file trên filesystem/CDN. **Hỗ trợ giao thức không đồng nghĩa hiệu suất range tối ưu trên mọi storage**.

### 4.2. Những header không tự bật tính năng

`Content-Disposition: attachment` quyết định gợi ý **download** thay vì hiển thị inline. Nó **không** kích hoạt Range. `Content-Type` cho MIME cũng không kích hoạt Range. `Accept-Ranges: bytes` do bạn tự gắn trên một response `byte[]` cũng **không** tạo ra body đúng theo Range. Cần đường xử lý thật sự parse Range và truyền đúng từng đoạn.

Nếu controller trả `ResponseEntity.status(HttpStatus.CREATED).body(resource)` hoặc status lỗi, đừng kỳ vọng Spring tự chuyển thành 206 cho request Range: cơ chế Resource auto-range áp dụng khi response ban đầu ở **200**.

## 5. Ví dụ Java 17 chạy được: ba endpoint trả cùng một chuỗi 26 byte

Ví dụ này dùng **Spring Boot 3.5.16**, một bản đã được phát hành trên Maven Central, với Java 17+ và Maven 3.6.3+. Không cần DB hay upload. Nó cố ý có **3 cách trả cùng một content** để quan sát trực tiếp giới hạn Range.

### 5.1. Cấu trúc project

~~~text
range-demo/
├─ pom.xml
└─ src/main/
   ├─ java/com/example/rangedemo/
   │  ├─ RangeDemoApplication.java
   │  └─ FileDownloadController.java
   └─ resources/static/
      └─ alphabet.txt  (tùy chọn, tạo đúng 26 byte như bước 5.5)
~~~

### 5.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>range-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 5.3. `src/main/java/com/example/rangedemo/RangeDemoApplication.java`

~~~java
package com.example.rangedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RangeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RangeDemoApplication.class, args);
    }
}
~~~

### 5.4. `src/main/java/com/example/rangedemo/FileDownloadController.java`

~~~java
package com.example.rangedemo;

import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
@RequestMapping("/files")
public class FileDownloadController {
    private static final byte[] ALPHABET =
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ".getBytes(StandardCharsets.US_ASCII);

    // Path 1: Resource - Spring MVC tự chuyển 200 -> 206 khi Range hợp lệ.
    @GetMapping("/resource")
    public ResponseEntity<Resource> asResource() {
        Resource resource = new ByteArrayResource(ALPHABET);
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"alphabet.txt\"")
                .body(resource);
    }

    // Path 2: byte[] - body được trả đầy đủ dù client gửi Range.
    @GetMapping("/bytes")
    public ResponseEntity<byte[]> asBytes() {
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body(ALPHABET);
    }

    // Path 3: StreamingResponseBody - một chiều, không auto-range.
    @GetMapping("/stream")
    public ResponseEntity<StreamingResponseBody> asStream() {
        StreamingResponseBody stream = out -> out.write(ALPHABET);
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body(stream);
    }
}
~~~

**Vì sao ví dụ dùng `ByteArrayResource` dù file lớn nên dùng FileSystemResource?** Đây là **fixture nhỏ 26 byte** để kiểm thử byte-range chính xác. Với file thật, dùng storage có seek/range và `FileSystemResource` hoặc Resource tương đương; đừng giữ file nhiều GB trong `byte[]`.

Spring MVC xử lý `ResponseEntity<Resource>` theo handler/message converter đặc biệt; `ResponseEntity<byte[]>` đi qua converter của byte array; `StreamingResponseBody` đi qua cơ chế async streaming riêng. Cùng dữ liệu nhưng cách trả khác dẫn đến hành vi Range khác.

### 5.5. Tùy chọn: file tĩnh cho static resource handler

Nếu muốn kiểm tra Range trên file tĩnh của Spring Boot, tạo file **không có newline cuối** đúng 26 byte tại `src/main/resources/static/alphabet.txt`.

Trong bash:

~~~bash
mkdir -p src/main/resources/static
printf %s ABCDEFGHIJKLMNOPQRSTUVWXYZ > src/main/resources/static/alphabet.txt
~~~

Trong Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path src/main/resources/static
[System.IO.File]::WriteAllBytes(
  "src/main/resources/static/alphabet.txt",
  [System.Text.Encoding]::ASCII.GetBytes("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
)
~~~

Khi chạy app, gọi `GET /alphabet.txt` sẽ đi qua **static resource handler**, không phải `FileDownloadController`. Nếu bạn tạo file từ editor và nó tự thêm xuống dòng, file sẽ dài **27 byte**; khi đó kết quả Content-Range tổng chiều dài thay đổi. File tạo theo lệnh trên mới có đúng 26 byte.

### 5.6. Chạy ứng dụng

Từ thư mục `range-demo`:

~~~bash
java -version
mvn spring-boot:run
~~~

Sau khi app mở cổng 8080 mặc định, mở terminal khác (ví dụ bash hoặc dùng `curl.exe` trong PowerShell) và thử:

~~~bash
curl -i http://localhost:8080/files/resource
curl -i -H "Range: bytes=0-4" http://localhost:8080/files/resource
curl -i -H "Range: bytes=10-14" http://localhost:8080/files/resource
curl -i -H "Range: bytes=20-" http://localhost:8080/files/resource
curl -i -H "Range: bytes=-4" http://localhost:8080/files/resource
curl -i -H "Range: bytes=100-" http://localhost:8080/files/resource
~~~

Các kết quả cần quan sát trong dự án **cấu hình mặc định**:

| Request | Status mong đợi | Body/headers trọng tâm |
| --- | --- | --- |
| Không có `Range` | **200** | Body `ABCDEFGHIJKLMNOPQRSTUVWXYZ`, tổng 26 byte |
| `bytes=0-4` | **206** | `ABCDE`, `Content-Range: bytes 0-4/26` |
| `bytes=10-14` | **206** | `KLMNO`, `Content-Range: bytes 10-14/26` |
| `bytes=20-` | **206** | `UVWXYZ`, `Content-Range: bytes 20-25/26` |
| `bytes=-4` | **206** | `WXYZ`, `Content-Range: bytes 22-25/26` |
| `bytes=100-` | **416** (thường theo framework phù hợp) | `Content-Range: bytes */26` nếu được cung cấp |

Body ví dụ **không bao gồm newline**; `curl -i` có thể hiện prompt terminal ngay sau `Z`. Header khác như Date/Connection/Transfer-Encoding có thể khác theo HTTP server và môi trường.

So sánh hai cách không tự hỗ trợ Range:

~~~bash
curl -i -H "Range: bytes=0-4" http://localhost:8080/files/bytes
curl -i -H "Range: bytes=0-4" http://localhost:8080/files/stream
~~~

Trong ví dụ, hai endpoint này trả **200 OK** với **toàn bộ 26 byte** vì không có logic tự parse Range. `StreamingResponseBody` có thể được viết qua executor async; việc có hoặc không có `Content-Length` phụ thuộc cách servlet response được gửi. Không suy ra 206 từ việc thấy response được gửi theo nhiều network chunks.

Với file `alphabet.txt` tùy chọn:

~~~bash
curl -i -H "Range: bytes=0-4" http://localhost:8080/alphabet.txt
~~~

Với file static đúng 26 byte, mong đợi **206** và `ABCDE` nếu static resource mapping còn bật và không bị security/proxy thay đổi. Không nhầm URL `/alphabet.txt` với `/static/alphabet.txt`.

**Thử multi-range:**

~~~bash
curl -i -H "Range: bytes=0-2,23-25" http://localhost:8080/files/resource
~~~

Response có thể là `206 multipart/byteranges`, mỗi part được gắn `Content-Range`. Giá trị boundary do framework sinh, không dự đoán byte-for-byte.

### 5.7. Thử resume bằng curl với nội dung bất biến

Dùng bash, tại thư mục tạm phù hợp:

~~~bash
# Bước 1: cố ý chỉ nhận mười byte đầu
curl -fsS -H "Range: bytes=0-9" \
  http://localhost:8080/files/resource -o alphabet.txt

# Bước 2: curl tiếp tục từ offset của file đang có
curl -fS -C - \
  http://localhost:8080/files/resource -o alphabet.txt

# Bước 3: so độ dài và nội dung
wc -c alphabet.txt
cat alphabet.txt
~~~

Stdout của `wc -c` chứa tên file và là **26 byte** sau khi nối thành công (không khẳng định spacing chính xác của lệnh). `cat` hiển thị `ABCDEFGHIJKLMNOPQRSTUVWXYZ` không có newline cuối. `-C -` khiến curl tự xác định offset dựa trên file output hiện tại và yêu cầu resume; nếu server không thỏa, curl có thể báo lỗi thay vì ghép sai. **Trong sản phẩm thật**, client cần thêm bước kiểm tra ETag/version/checksum và xử lý status để tránh trộn hai bản file.

Để thử đa client, network cancellation, proxy và 416, nên có automated integration tests chứ không chỉ tin một lệnh curl thành công.

## 6. Trả file trên filesystem: `FileSystemResource`

Một endpoint phục vụ tệp đã lưu ở disk có thể trả `ResponseEntity<Resource>` với `FileSystemResource`, thay cho `ByteArrayResource`, để tránh đọc toàn bộ tệp vào heap. Ví dụ **mảnh minh họa**, giả định tầng service đã tra cứu ID, kiểm tra quyền và trả **một `Path` hợp lệ được server kiểm soát**:

~~~java
// Mảnh tích hợp, cần imports/authorization service phù hợp trong project thật.
@GetMapping("/downloads/{id}")
public ResponseEntity<Resource> download(@PathVariable String id) {
    Path approvedPath = downloadService.resolveAuthorizedPath(id);
    Resource resource = new FileSystemResource(approvedPath);

    if (!resource.exists() || !resource.isReadable()) {
        throw new ResponseStatusException(HttpStatus.NOT_FOUND);
    }

    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .header(HttpHeaders.CONTENT_DISPOSITION,
                    "attachment; filename=\"download.bin\"")
            .body(resource);
}
~~~

Chọn đường dẫn **từ metadata/storage của server** sau khi authorization, thay vì lấy chuỗi người dùng nhập rồi gọi `Path.of(userInput)` để mở file tùy ý. Kiểm tra canonical path và symlink/traversal khi hệ thống cho phép nhiều đường dẫn, không lộ tuyệt đối path server cho client. Có thể áp dụng thêm rate limit, timeouts và audit.

**Lưu ý race/version:** FileSystemResource có thể mở file trong khi nó bị ghi lại trên disk. Nếu nội dung hoặc độ dài thay đổi giữa các request Range (hoặc ngay trong khi stream), cơ chế resume có thể ghép bytes không nhất quán. Với download quan trọng, lưu file dưới **object key/version bất biến**, hoặc tạo snapshot trước khi phục vụ, dùng strong ETag/checksum tương ứng.

Với file rất lớn, `FileSystemResource` phù hợp khi file thực sự nằm trên filesystem. Nếu file nằm ở S3/GCS/remote object storage, tốt hơn là **presigned download URL** hoặc stream có forward Range đúng protocol; không tải toàn bộ object về RAM rồi bọc vào `ByteArrayResource`.

## 7. WebFlux: điều kiện tương tự nhưng writer khác MVC

Spring **WebFlux** cũng xử lý Range tự động khi annotated controller trả `Resource` hoặc `ResponseEntity<Resource>` (status ban đầu 200, không phải `InputStreamResource`) và với static resources phù hợp. Cơ chế ở WebFlux dùng `HttpRange`, `ResourceRegionEncoder` và `ResourceHttpMessageWriter`, khác converter của Servlet MVC.

Ví dụ **mảnh mã WebFlux** (không thuộc project MVC ở mục 5; dùng project có `spring-boot-starter-webflux`):

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class ReactiveDownloadController {

    @GetMapping("/reactive/file")
    Mono<ResponseEntity<Resource>> file() {
        Resource body = new ByteArrayResource(
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ".getBytes(StandardCharsets.US_ASCII));
        return Mono.just(ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body(body));
    }
}
~~~

`Mono<ResponseEntity<Resource>>` cho phép Spring biết body là `Resource`; WebFlux writer có thể xử lý Range tương ứng. Nếu thay body thành `Flux<DataBuffer>`, pipeline chỉ là **dòng buffer tuần tự**; không mặc nhiên chuyển client `Range` thành 206. Muốn proxy/object streaming kèm resume phải tự xử lý offset, tổng size, headers và các điều kiện hợp lệ hoặc dùng một API của storage có hỗ trợ HTTP Range.

**WebFlux non-blocking không đồng nghĩa mọi storage tự seek được.** Dùng blocking disk read/JDBC trên event loop có thể gây nghẽn; nếu triển khai manual stream, dùng API reactive hoặc scheduling phù hợp và xử lý release `DataBuffer` theo hợp đồng của Spring. Với nội dung file tĩnh/thông thường, ưu tiên built-in Resource writer thay vì tự viết buffer pipeline.

Nếu thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường chọn **MVC/Servlet application type**, vì vậy cần xác minh stack thực chạy trước khi đối chiếu kết quả.

## 8. `ResourceRegion` và tự xử lý Range khi cần

### 8.1. Vì sao có `ResourceRegion`?

`ResourceRegion` biểu diễn một vùng của Spring `Resource` với **vị trí bắt đầu** và **số byte**. `HttpRange` là tiện ích parse request Range và tạo các vùng:

~~~java
// Mảnh khái niệm, không phải một handler hoàn chỉnh.
List<HttpRange> ranges = HttpRange.parseRanges("bytes=0-4,10-14");
List<ResourceRegion> regions = HttpRange.toResourceRegions(ranges, resource);
~~~

Trong Spring MVC, `ResourceRegionHttpMessageConverter` có thể viết các vùng ra response; trong WebFlux, `ResourceRegionEncoder` và `ResourceHttpMessageWriter` tham gia. **Không** dùng đoạn trên như một endpoint hoàn chỉnh: bạn còn phải lựa chọn 200/206/416, quản lý media type, multipart boundary, Content-Range, Content-Length, HEAD, security, conditional validators và input abuse.

Tự viết parser/formatter thủ công có nhiều góc cạnh: `bytes=-N`, `bytes=N-`, multiple ranges, start>end, integer overflow, out-of-bounds, file size 0, If-Range, duplicate/overlap, media type, compression. Hãy dùng built-in Resource handling trước; chỉ tự điều khiển khi storage/case nghiệp vụ yêu cầu.

### 8.2. Trả file từ object storage hoặc upstream HTTP

Nếu backend proxy một object store hỗ trợ `Range`:
1. Client gửi Range và optional If-Range/version.
2. Backend xác thực quyền truy cập, tra cứu object/version đã gắn với người dùng.
3. Gửi Range phù hợp tới upstream (hoặc dùng SDK byte-range), giới hạn số range/offset theo chính sách.
4. Đọc status/headers của upstream; **không** tự đặt `206` chỉ vì đã gửi Range.
5. Chuyển tiếp hoặc tái tạo chính xác `Content-Range`, `Content-Type`, `Content-Length`, validators và body; với multipart phải bảo toàn boundary và từng part.
6. Nếu upstream trả **200 full**, client-facing backend không được giả làm 206 của một đoạn nhỏ trừ khi đã tự cắt bytes và tính toán headers thật chính xác.
7. Xử lý cancellation/backpressure, tránh giữ connection/stream sau khi client ngắt kết nối.

Với nhiều tệp rất lớn, presigned URL trực tiếp đến object storage/CDN phù hợp hơn việc bắt mọi byte đi qua JVM application. Nếu backend cần kiểm tra quyền, tạo URL ngắn hạn sau khi authorized; các URL này vẫn phải có TTL/phạm vi phù hợp.

## 9. Giới hạn theo phương thức, cache và content encoding

### 9.1. Range thông thường cho GET, HEAD chỉ kiểm tra metadata

Theo HTTP, `Range` được định nghĩa để tác động lên **GET**. Server phải bỏ qua `Range` ở các phương thức mà semantics không hỗ trợ, như POST. `HEAD` được dùng để lấy headers của representation mà không gửi body; nó hữu ích để kiểm tra kích thước/ETag nhưng **không tải byte range**.

Không nhầm `HEAD + Range` với cách tải tiếp một đoạn file. Để resume hãy dùng **GET** thật.

### 9.2. Preconditions có thứ tự

Các điều kiện request như `If-None-Match`/`If-Modified-Since` được đánh giá trước Range. Nếu GET có thể trả `304 Not Modified`, server không cần xử lý Range thành 206 ở request đó. `If-Range` là điều kiện riêng cho tải một phần; nó kiểm tra representation chưa thay đổi và (nếu không) cho phép gửi nguyên representation.

Không tự trộn `If-Range`, `If-Match` và `If-None-Match` mà không hiểu kết quả có thể là **200, 206, 304, 412 hoặc 416** tùy header và tình trạng tài nguyên.

### 9.3. `Content-Encoding: gzip` làm byte offset phức tạp hơn

Range `bytes=...` áp dụng lên **selected representation data**, bao gồm content coding nếu representation được truyền với `Content-Encoding`. Ví dụ server có thể gửi bản gzip; offset trong bản gzip **không bằng** offset của bytes file gốc sau giải nén. Vì thế:
- client resume nên yêu cầu **cùng representation variant** (content encoding, ETag, URL/version);
- khi thử nghiệm nên gửi `Accept-Encoding: identity` nếu muốn đối chiếu trực tiếp byte offset của file chưa nén;
- proxy/CDN nén hoặc biến đổi nội dung có thể đổi validator và kích thước;
- `Vary: Accept-Encoding` và ETag từng variant phải nhất quán để tránh ghép nhầm;
- truyền file nén như `.zip` không có nghĩa response dùng `Content-Encoding: gzip` — đó là hai tầng khái niệm khác nhau.

### 9.4. HTTP chunked transfer không phải range

`Transfer-Encoding: chunked` (HTTP/1.1) là **cách đóng khung response trên đường truyền**, không phải cơ chế client yêu cầu byte 500 đến cuối. Một response 200 chunked có thể dài và streaming rất tốt nhưng vẫn **không có random access**. HTTP/2 và HTTP/3 có framing riêng; vẫn dùng semantics `Range`/`206` ở cấp HTTP.

### 9.5. CDN và reverse proxy

Range có thể được xử lý ở ứng dụng, reverse proxy hoặc CDN. Khi đi qua Nginx/Envoy/load balancer, kiểm tra:
- header `Range`/`If-Range` có được forward;
- proxy có strip/đổi `Content-Encoding`, `ETag`, `Content-Length`;
- redirect có làm client mất header authorization hoặc chuyển URL version;
- có `206`, `416` và multipart đúng khi file được cache;
- chính sách cache và authorization có làm lộ file riêng;
- timeout và limit từng proxy có ngắt tải dài.

Nếu tải trực tiếp từ app được 206 nhưng qua CDN chỉ 200, trước tiên so sánh response headers và caching/proxy transformation; không vội sửa controller.

## 10. Hiệu năng và an toàn khi cho phép tải từng đoạn

**Không phải càng nhiều Range càng tốt.** Một request có hàng ngàn range nhỏ hoặc overlap có thể buộc server tìm/đọc file nhiều lần và tạo body multipart lớn. Hạn chế số lượng ranges/độ lớn tổng request theo nguy cơ thực tế, dùng built-in parser, rate limiting và request limits ở ingress.

**Chi phí bộ nhớ:** tránh `Files.readAllBytes` cho file lớn, nhất là khi nhiều user download đồng thời. Một app phục vụ 100 user, mỗi user dùng `ByteArrayResource` chứa 200 MB file riêng có thể tạo áp lực heap rất lớn. Dùng file-based Resource, zero-copy khi container hỗ trợ, object storage hoặc CDN; đo hiệu năng thực tế.

**Chi phí lưu trữ:** random reads trên HDD, object store, remote filesystem và JAR có chi phí khác nhau. Support 206 không bảo đảm seek nhanh hoặc cloud GET rẻ. Với nhiều request segment, nên thiết kế chunk size đủ lớn, hạn chế parallel fan-out và kiểm soát chi phí/băng thông.

**Đường dẫn và quyền:** không chấp nhận người dùng truyền trực tiếp `/etc/passwd` hoặc `../secrets` làm file path. Dùng opaque file ID và service authorization, chuẩn hóa đường dẫn, chống symlink/traversal, chỉ phục vụ directory đã duyệt. Không public file upload chỉ bằng cách đặt vào `src/main/resources/static` hay một static mapped directory.

**Download headers:** `Content-Disposition: attachment` phù hợp khi muốn trình duyệt lưu file; kiểm soát tên file an toàn, ký tự Unicode và header injection. `Content-Type` phải chính xác hoặc chọn `application/octet-stream` nếu file là binary chung; cân nhắc `X-Content-Type-Options: nosniff`, CSP và chính sách truy cập cho nội dung user-uploaded.

**File ổn định:** dùng ID/version, immutable snapshot, ETag/hash và cuối cùng checksum. Nếu file bị thay trong lúc tải, không có thuật toán append nào tự khắc phục được tính nhất quán.

**Tài nguyên hệ thống:** áp timeout cho network/storage, giới hạn kết nối đồng thời, đo throughput, p95 download time, memory/GC, HTTP 206/416 ratio, cancellation và upstream error. Một app có thể gửi từng phần hiệu quả nhưng vẫn bị nghẽn bandwidth hoặc file descriptor.

## 11. Bảng quyết định: chọn cách trả tài nguyên nào?

| Yêu cầu | Hướng chọn | Vì sao |
| --- | --- | --- |
| CSS/JS/ảnh/file public từ JAR | Static resource handler hoặc CDN | Spring Boot cấu hình sẵn Range cho resource phù hợp |
| File lưu trên ổ đĩa, cần resume | `ResponseEntity<Resource>` + `FileSystemResource` | Có length/repeatable access, auto-range khi status 200 |
| File nhỏ, đã có byte[] | `ByteArrayResource` | Dễ test, Spring xử lý Range; không dùng cho file rất lớn |
| Dữ liệu xuất ra từng dòng mà chưa biết length (CSV stream, báo cáo live) | `StreamingResponseBody` (MVC) hoặc `Flux<DataBuffer>` (WebFlux) | Stream tuần tự; **không tự hỗ trợ resume**, nên có thể cần tạo snapshot trước |
| File từ DB lưu dạng BLOB stream một lần | Stream một chiều, hoặc xuất thành file/object trước | Không đảm bảo seek/length/reopen; nếu cần resume, tạo stable resource |
| File lớn trong S3/GCS | Presigned URL hoặc proxy Range có kiểm soát | Offload byte transfer, sử dụng khả năng Range của storage |
| Media player cần seek | File/representation ổn định, Range hoạt động và media format phù hợp | Player có thể yêu cầu những byte khác nhau theo thời gian |
| Có nhiều file version trên cùng URL | Versioned URL, ETag/If-Range đúng và integration test | Tránh ghép bytes của các phiên bản khác |

Cần phân biệt **file được generate động** với **file đã được generate rồi cố định**. Một báo cáo CSV tính từ DB mỗi lần GET có thể thay đổi thứ tự/size giữa các request, khiến Range không còn nghĩa an toàn. Nếu người dùng cần resume, tạo và lưu snapshot có ID, size, hash, TTL; sau đó phục vụ snapshot như file/resource.

## 12. Lỗi thường gặp và cách điều tra

| Hiện tượng | Nguyên nhân hay gặp | Việc cần làm |
| --- | --- | --- |
| Gửi `Range` nhưng luôn nhận **200** | Trả `byte[]`, `StreamingResponseBody`, `InputStreamResource`, status không phải 200 trước xử lý, hoặc proxy bỏ Range | Kiểm tra loại trả thực tế, endpoint và đường qua proxy |
| `206` nhưng body sai đoạn | Tự tính offset sai (end inclusive) hoặc upstream trả nội dung khác | Kiểm tra `Content-Range`, 0-based offsets và checksum |
| Resume tạo file hỏng dù đủ size | Ghép bytes từ hai versions hoặc gzip/identity khác nhau | Strong validator, immutable URL, checksum |
| `416` khi tải tiếp | Offset local lớn hơn file hiện tại; file bị thay; client gửi range vượt length | Đọc `Content-Range: bytes */L`, xác minh local size/version |
| Multi-range response không ghép được | Body là `multipart/byteranges`, không phải raw bytes đơn | Parse từng part cùng `Content-Range` |
| `Content-Length` chỉ là 1024, file gốc 100 MB | Đang xem partial response `206` | Xem tổng length ở `Content-Range` |
| Không có `Content-Length` | Stream dài/unknown size, transfer framing động | Không kết luận “không có stream”; muốn resume cần metadata khác |
| `Accept-Ranges: bytes` nhưng gửi Range không được 206 | Header quảng bá không bảo đảm mọi tình huống | Test GET Range thật, điều kiện cache và proxy |
| Trả `ResponseEntity<Resource>` nhưng không có 206 | Body thực là `InputStreamResource` hoặc custom converter/response wrapper | Dùng Resource repeatable, status 200, kiểm tra stack |
| Browser tải lại toàn bộ sau ngắt mạng | URL/file đổi, server không hỗ trợ Range hoặc client không resume | Kiểm tra network trace, `Range`, `If-Range` và URL version |
| `206` qua app, `200` qua CDN | Proxy cache/normalization/compression can thiệp | So headers, request direct vs CDN, query cache |
| Media player không tua video được | Range không hoạt động, MIME sai, file container metadata không phù hợp | Kiểm tra Range + Content-Type + media metadata |
| Download dùng `byte[]` gây OutOfMemoryError | Full file và nhiều request cùng giữ bytes trên heap | Chuyển FileSystemResource/object storage/stream |
| `If-Range` sai version nhưng vẫn nhận `206` trên app cũ | Implementation chưa xử lý đầy đủ validator | Tạo immutable snapshot/version hoặc xử lý điều kiện, test đúng version |
| `HEAD` không giống GET | Custom handler/response không nhất quán metadata | So headers cho GET và HEAD, tránh tự tạo Content-Length sai |
| `Range` chứa hàng ngàn phần làm server chậm | Resource abuse/DoS bằng many small ranges | Hạn chế ranges, rate limit và đo I/O |

### Quy trình kiểm tra tối thiểu

1. Gọi GET không Range: ghi status, `Content-Length`, `ETag`/`Last-Modified`, `Content-Encoding`, hash file nhận được.
2. Gọi `Range: bytes=0-4`: kiểm tra **206**, `Content-Range` và đúng 5 byte.
3. Gọi `Range: bytes=-4`: kiểm tra suffix range.
4. Gọi `Range: bytes=100000000-` với fixture nhỏ: quan sát **416**/`Content-Range` và application error handler.
5. Thử `Range: bytes=0-2,23-25`: kiểm tra multipart nếu được trả.
6. So `/files/resource` với `/files/bytes`, `/files/stream` để thấy khác nhau.
7. Nếu muốn resume production, thử đổi version giữa hai GET, gửi `If-Range` và kiểm tra client có **không append** body 200.
8. Thử qua proxy/CDN và khi gửi `Accept-Encoding: identity`, `gzip` (nếu có).
9. Kiểm tra phân quyền cho cùng file, tệp bị xóa lúc tải, client hủy giữa chừng và quá tải concurrency.

## 13. Câu hỏi tự kiểm tra

1. Một file 1.000 byte, client gửi `Range: bytes=500-`. Nếu hỗ trợ, response `Content-Range` và `Content-Length` lý tưởng là gì?
2. Vì sao `Range: bytes=0-4` trả **5 byte**, không phải 4?
3. Với file 26 byte, `Range: bytes=-4` trả nội dung nào?
4. Tại sao `ResponseEntity<byte[]>` có thể trả 200 full dù client gửi `Range`?
5. Vì sao `InputStreamResource` không có cơ chế auto-range giống `FileSystemResource`?
6. Client có 400 byte cũ, server trả 200 body toàn file sau request resume: phải làm gì?
7. `If-Range` và `If-None-Match` có cùng semantics không?
8. Nếu file được nén gzip qua HTTP, offset đang trỏ vào bytes gốc hay selected encoded representation?
9. Vì sao `Content-Disposition: attachment` không có nghĩa server hỗ trợ resume?
10. Một app trả `StreamingResponseBody` để export CSV động. Muốn resume an toàn nên thay đổi kiến trúc ra sao?
11. MVC và WebFlux đều có auto-range cho `Resource`, nhưng framework writer/converter nào khác nhau?
12. Khi `Range` yêu cầu nhiều đoạn, `Content-Type` response có thể là gì?
13. Nếu static handler trả `206` nhưng endpoint controller trả `200`, bạn kiểm tra điều gì đầu tiên?
14. Tại sao chỉ xác thực tổng file size sau khi nối chưa bảo đảm file không bị trộn version?
15. Khi download file 10 GB, tại sao `FileSystemResource` thường thích hợp hơn `ByteArrayResource(Files.readAllBytes(...))`?
16. Nếu dự án dùng Spring Boot 3.5/Framework 6.2, trước khi dựa vào `If-Range` để tải tiếp bạn phải làm gì?

**Đáp án trọng tâm:** (1) `bytes 500-999/1000` và body length 500; (2) end inclusive, bắt đầu 0; (3) `WXYZ`; (4) kiểu byte[] không kích hoạt Resource auto-range; (5) stream một lượt không hỗ trợ seek/reopen chuẩn; (6) thay file tạm bằng full body, không append; (7) không, If-Range quyết định partial/full còn If-None-Match là điều kiện cache; (8) selected representation sau content coding; (9) chỉ gợi ý filename/display; (10) tạo snapshot bất biến rồi serve Resource/object; (11) MVC dùng ResourceRegionHttpMessageConverter, WebFlux dùng ResourceRegionEncoder/ResourceHttpMessageWriter; (12) `multipart/byteranges`; (13) body type, status, converter/route; (14) file khác nội dung có thể cùng size; (15) tránh heap bùng nổ, hỗ trợ đọc lặp; (16) integration test version đổi và dùng immutable object/version hoặc validator handling phù hợp.

## 14. Tài liệu chính thức để đối chiếu

- **RFC 9110 — HTTP Semantics, ``13–15:** https://www.rfc-editor.org/rfc/rfc9110.html — `Range`, `If-Range`, `206`, `416`, `Content-Range`.
- **Spring Framework — Spring MVC Range Requests:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-range.html — điều kiện `Resource` và `ResponseEntity<Resource>`, ngoại lệ `InputStreamResource`.
- **Spring Framework — WebFlux Range Requests:** https://docs.spring.io/spring-framework/reference/web/webflux/range.html — reactive resource writing và `ResourceRegionEncoder`.
- **Spring Framework — MVC static resources:** https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/static-resources.html — cách Spring tìm và phục vụ tài nguyên tĩnh.
- **Spring Framework Javadoc — InputStreamResource:** https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/io/InputStreamResource.html — đặc tính single-use stream.
- **Spring Boot 3.5 System Requirements:** https://docs.spring.io/spring-boot/3.5/system-requirements.html — Java 17+, Framework 6.2.x và Maven phù hợp.
- **Spring Framework issue #34490:** https://github.com/spring-projects/spring-framework/issues/34490 — ví dụ lỗi 416/static-handler được xử lý ở dòng 6.2.9; cần dùng bản patch phù hợp.
- **Spring Framework enhancement #37218 (If-Range):** https://github.com/spring-projects/spring-framework/issues/37218 — lý do cần xác minh tính tương thích của `If-Range` theo phiên bản thay vì suy ra từ `206`.
- **MDN — HTTP range requests:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Range_requests — ví dụ client/server và streaming/resume.
