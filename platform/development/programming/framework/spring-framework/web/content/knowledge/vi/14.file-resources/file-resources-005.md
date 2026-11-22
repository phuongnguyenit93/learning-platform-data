# Range request, ResourceRegion và phản hồi 206 Partial Content trong Spring MVC

## 1. Vì sao HTTP Range quan trọng?

Khi client tải tệp video, PDF hoặc một tài liệu lớn, nó có thể cần **một đoạn bytes** thay vì tải lại toàn bộ. Video player muốn tua đến vị trí mới, download manager muốn tiếp tục tệp tải dở, PDF viewer có thể cần vùng chứa metadata/trang cần mở.

HTTP hỗ trợ cơ chế **Range Requests**, định nghĩa trong RFC 9110. Client gửi header `Range`, server có thể đáp bằng `206 Partial Content` với đúng vùng bytes. Trong Spring Web MVC, `Resource`, `HttpRange`, `ResourceRegion` và `ResourceRegionHttpMessageConverter` hỗ trợ phần lớn công việc này.

Bài học dành cho **Spring MVC trên Servlet stack** với **Java 17, Spring Boot 3.3.5 và Spring Framework 6.1.x**. Nội dung gồm cú pháp và ngữ nghĩa HTTP Range, Spring auto-range, sử dụng ResourceRegion, 200/206/416, multi-range, ETag/If-Range, ứng dụng Maven chạy được, MockMvc tests và các giới hạn khi triển khai thực tế. WebFlux có reactive writers khác, không áp dụng nguyên mã controller/converter MVC.

## 2. Hiểu byte offsets đúng

Giả sử tệp có đúng 10 bytes ASCII:

```text
Nội dung: A B C D E F G H I J
Vị trí:   0 1 2 3 4 5 6 7 8 9
Độ dài:  10 bytes
```

Client gửi:

```http
GET /api/files/sample HTTP/1.1
Host: localhost:8080
Range: bytes=2-5
```

Một phản hồi hợp lệ khi server chấp nhận Range:

```http
HTTP/1.1 206 Partial Content
Content-Type: text/plain
Accept-Ranges: bytes
Content-Range: bytes 2-5/10
Content-Length: 4

CDEF
```

Giải thích:

- `bytes` là đơn vị range của HTTP.
- Byte **đầu 2, cuối 5 đều bao gồm**: có `5 - 2 + 1 = 4` bytes.
- `/10` trong `Content-Range` là kích thước của **toàn bộ representation**, không phải độ dài đoạn.
- `Content-Length: 4` là độ dài **phần response thực tế**. Với transfer encoding/chunking, header này không nhất thiết luôn có.
- HTTP status thật là `206`, không phải `200` với JSON `{"code":206}`.
- Body chỉ chứa `CDEF`.

**Range dựa trên bytes, không dựa trên ký tự.** Với UTF-8, một ký tự tiếng Việt có thể dài nhiều bytes, nên Range có thể cắt giữa một ký tự; client tải theo phần cần ghép bytes rồi mới giải mã. Với content coding `gzip` hoặc `br`, offsets áp dụng cho **selected representation bytes** (đã content-encoded nếu được gửi ở dạng đó); không tự đồng nhất với offset của file gốc chưa nén.

## 3. Bốn dạng Range phổ biến

```http
Range: bytes=<first>-<last>
Range: bytes=<first>-
Range: bytes=-<suffix-length>
Range: bytes=<first1>-<last1>,<first2>-<last2>
```

Với `ABCDEFGHIJ` dài 10 bytes:

| Header | Cách hiểu | Phần có thể trả |
| --- | --- | --- |
| `bytes=0-3` | Từ byte 0 đến byte 3 | `ABCD` |
| `bytes=2-5` | Từ byte 2 đến byte 5 | `CDEF` |
| `bytes=7-` | Từ byte 7 tới hết | `HIJ` |
| `bytes=-3` | Ba bytes cuối | `HIJ` |
| `bytes=9-99` | Từ 9, end vượt total | `J` (được chặn tại 9) |
| `bytes=0-1,8-9` | Hai vùng không liên tiếp | `AB` và `IJ` |
| `bytes=10-20` | Bắt đầu ở ngoài file | Không thỏa, thường `416` |
| `bytes=5-4` | End trước start | Cú pháp/phạm vi không hợp lệ |

**`bytes=7-` khác `bytes=-7`**: mẫu đầu từ offset 7 tới cuối; mẫu sau lấy 7 bytes cuối. Nếu suffix length lớn hơn file, vùng hợp lệ có thể là toàn bộ representation.

Client có thể gửi header Range nhưng **server được phép bỏ qua** và trả `200 OK` với toàn bộ representation trong các tình huống hợp lệ. Đừng giả định cứ có `Range` là chắc chắn nhận 206. Các phạm vi sai, overflow, hoặc chứa hàng trăm ranges cần được xử lý bằng parser/giới hạn phù hợp, không tự `split("-")` rồi ép `int`.

## 4. 200 OK, 206 Partial Content, 416 Range Not Satisfiable

### 4.1. 200: trả toàn bộ

```http
HTTP/1.1 200 OK
Content-Type: text/plain
Content-Length: 10
Accept-Ranges: bytes

ABCDEFGHIJ
```

Thường là response khi không có `Range`. `Accept-Ranges: bytes` là tín hiệu server hỗ trợ byte ranges; header này **không nhất thiết** có ở mọi server hỗ trợ. Một server không hỗ trợ ranges có thể quảng bá `Accept-Ranges: none`. Vắng header không luôn có nghĩa range không được hỗ trợ.

Không đặt `Content-Range` trên 200 thông thường để mô tả toàn bộ file; RFC dùng Content-Range theo ngữ nghĩa của 206/416.

### 4.2. 206: trả một phần

```http
HTTP/1.1 206 Partial Content
Content-Type: text/plain
Content-Range: bytes 7-9/10
Content-Length: 3

HIJ
```

Một **single-part 206** phải có `Content-Range` mô tả đúng phần bytes được gửi. Với `bytes=7-9` có 3 bytes. Header `Content-Length`, nếu được phát, ghi kích thước response body, không ghi total trong `/10`.

### 4.3. 416: không có vùng byte nào thỏa

```http
HTTP/1.1 416 Range Not Satisfiable
Content-Range: bytes */10
```

`bytes */10` thể hiện toàn bộ representation hiện tại dài 10 bytes. Đây là dạng unsatisfied-range được RFC khuyến nghị cho lỗi phạm vi không thỏa. Không trả `Content-Range: bytes 20-30/10` vì nó không mô tả vùng tồn tại.

Một Range header **cú pháp sai** và một Range header **đúng cú pháp nhưng ngoài độ dài** không nhất thiết có mọi hành vi giống nhau; status/body cụ thể có thể chịu ảnh hưởng parser, reverse proxy và exception handling.

## 5. Nhiều ranges và multipart/byteranges

Với:

```http
Range: bytes=0-1,8-9
```

server có thể phản hồi bằng hai parts:

```http
HTTP/1.1 206 Partial Content
Content-Type: multipart/byteranges; boundary=demo-boundary

--demo-boundary
Content-Type: text/plain
Content-Range: bytes 0-1/10

AB
--demo-boundary
Content-Type: text/plain
Content-Range: bytes 8-9/10

IJ
--demo-boundary--
```

Ví dụ chỉ minh họa cấu trúc; HTTP multipart thực tế dùng CRLF và boundary thực do server tự tạo. Những quy tắc then chốt:

- Với nhiều parts, outer `Content-Type` là `multipart/byteranges`, **không** phải `multipart/form-data` (loại này dùng với upload).
- `Content-Range` phải nằm trong **từng part**, không ở top-level của response multipart.
- `Content-Length` nếu có là kích thước **toàn multipart body** gồm boundaries, part headers và bytes; không chỉ `2+2=4`.
- Server có thể gộp ranges trùng/chồng/lân cận hoặc giới hạn số ranges; client cần parse Content-Range thực tế thay vì giả định đúng cấu trúc yêu cầu.
- `ResourceRegionHttpMessageConverter` của Spring hỗ trợ viết một `ResourceRegion` hoặc collection `ResourceRegion` tương ứng.

## 6. Spring MVC xử lý Range tự động

Với Spring MVC 6.1, một controller có thể trả `Resource` hoặc `ResponseEntity<Resource>`. Framework có thể xử lý Range mà controller **không cần đọc header `Range` hoặc tự cắt bytes**.

```text
GET /files/42
  Range: bytes=2-5
      |
      v
DispatcherServlet -> @GetMapping
      |
      v
Controller trả ResponseEntity<Resource> status 200
      |
      v
Spring đọc Range qua HttpRange
      |
      v
HttpRange -> List<ResourceRegion>
      |
      v
ResourceRegionHttpMessageConverter ghi 206 + 4 bytes
      |
      v
HTTP 206, Content-Range: bytes 2-5/10
```

**Hai điều kiện quan trọng:**

1. Resource không phải `InputStreamResource`.
2. Với `ResponseEntity<Resource>`, **status ban đầu phải là 200 OK**.

Vì vậy, không làm:

```java
// PHẢN VÍ DỤ: tự đặt 206 không khiến MVC auto-range.
return ResponseEntity.status(HttpStatus.PARTIAL_CONTENT)
        .body(resource);
```

Nếu đưa status 206 sẵn nhưng body vẫn là toàn bộ `Resource`, nhánh tự xử lý ranges có thể bị bỏ qua và response sai ngữ nghĩa. Hãy để Spring bắt đầu từ 200 hoặc tự triển khai vùng bytes/headers đúng nếu có use case đặc biệt.

### Resource nào phù hợp?

| Resource | Có phù hợp auto-range? | Lưu ý |
| --- | --- | --- |
| `FileSystemResource` | Có, thường phù hợp | File thực, có length và mở stream lại |
| `PathResource` | Có, thường phù hợp | Cần storage path an toàn và quyền truy cập |
| `ByteArrayResource` | Có, với dữ liệu nhỏ | Đã giữ toàn bộ bytes trong RAM |
| `InputStreamResource` | **Không dùng cho auto-range** | Stream thường đọc một lần, length/repeatability khó đảm bảo |
| Custom `Resource` | Tùy implementation | Cần length chính xác, stream có thể mở/seek phù hợp |

Trong Spring MVC, auto-range được thực hiện ở return-value/converter layer; `HttpRange` và `ResourceRegion` là abstraction cho từng vùng, `ResourceRegionHttpMessageConverter` ghi đúng bytes. Với static assets phục vụ qua Spring resource handler, Spring cũng có hỗ trợ Range; đừng tạo controller không cần thiết cho file static public.

### Nếu status trước Range không phải 200?

Một conditional GET trả `304 Not Modified` không phải `206`. Một response lỗi `404`, `403` hoặc `500` cũng không chuyển thành partial file chỉ vì client gửi Range. Theo RFC, Range được xem xét sau các preconditions, và chỉ khi response không xét Range sẽ là 200. Kiểm tra authorization và điều kiện representation **trước** bước gửi bytes.

## 7. Dự án Maven hoàn chỉnh chạy được

Ta tạo API phục vụ đúng một tệp test có 10 bytes ASCII `ABCDEFGHIJ`. Controller luôn trả `ResponseEntity<Resource>` với status 200 khi thành công; Spring tự chọn 200, 206 hoặc 416 theo Range. Kết quả dễ kiểm chứng vì kích thước và bytes đã cố định.

### 7.1. Cây dự án

```text
mvc-range-demo/
├── pom.xml
└── src/
    ├── main/java/demo/ranges/
    │   ├── RangeApplication.java
    │   └── SampleFileController.java
    └── test/java/demo/ranges/
        └── SampleFileControllerTest.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>mvc-range-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
```

**`src/main/java/demo/ranges/RangeApplication.java`**

```java
package demo.ranges;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RangeApplication {
    public static void main(String[] args) {
        SpringApplication.run(RangeApplication.class, args);
    }
}
```

**`src/main/java/demo/ranges/SampleFileController.java`**

```java
package demo.ranges;

import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/files")
public class SampleFileController {

    private static final byte[] SAMPLE =
            "ABCDEFGHIJ".getBytes(StandardCharsets.US_ASCII);

    @GetMapping(path = "/sample",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<Resource> sample() {
        Resource resource = new ByteArrayResource(SAMPLE) {
            @Override
            public String getFilename() {
                return "sample.txt";
            }
        };

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"sample.txt\"")
                .body(resource);
    }
}
```

**Vì sao ví dụ này hỗ trợ Range?**

- `SAMPLE` dài đúng 10 bytes (ASCII), được `ByteArrayResource` cung cấp để mở stream lại và lấy `contentLength()`.
- `ResponseEntity.ok()` tạo response ban đầu 200; Spring MVC có thể chuyển sang 206/416.
- `produces=text/plain` và `Content-Type: text/plain` phù hợp với bytes tệp.
- `Content-Disposition` sử dụng filename **do server viết cứng** để minh họa download, không dùng tên user gửi.
- Controller không đọc `Range`, không tự chia mảng và không cố định `Content-Length` hoặc `Content-Range`. Điều đó do framework quyết định theo từng request.
- `ByteArrayResource` chỉ thích hợp ví dụ nhỏ: tệp hàng GB nên dùng `FileSystemResource`/storage native range thay vì `Files.readAllBytes()` gây tốn RAM.

### 7.2. Lệnh chạy và kết quả HTTP

Trong thư mục `mvc-range-demo` với JDK 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Chạy hai lệnh theo thứ tự. Ứng dụng mặc định dùng `http://localhost:8080`.

**Toàn bộ tài nguyên:**

```bash
curl -i http://localhost:8080/api/files/sample
```

Các giá trị quan trọng:

```http
HTTP/1.1 200
Content-Type: text/plain
Accept-Ranges: bytes

ABCDEFGHIJ
```

**Bốn bytes đầu:**

```bash
curl -i -H 'Range: bytes=0-3' \
  http://localhost:8080/api/files/sample
```

```http
HTTP/1.1 206
Content-Range: bytes 0-3/10
Content-Type: text/plain

ABCD
```

**Ba bytes cuối:**

```bash
curl -i -H 'Range: bytes=-3' \
  http://localhost:8080/api/files/sample
```

Dự kiến `206` với `Content-Range: bytes 7-9/10`, body `HIJ`.

**Từ byte 7 đến cuối:**

```bash
curl -i -H 'Range: bytes=7-' \
  http://localhost:8080/api/files/sample
```

Dự kiến `206`, `Content-Range: bytes 7-9/10`, body `HIJ`.

**Phạm vi ngoài tài nguyên:**

```bash
curl -i -H 'Range: bytes=20-30' \
  http://localhost:8080/api/files/sample
```

Dự kiến `416` và header `Content-Range: bytes */10` theo nhánh auto-range của Spring MVC 6.1. Body lỗi hoặc các headers khác phụ thuộc framework/config, không phải một JSON contract riêng của demo.

**Hai vùng không liên tiếp:**

```bash
curl -i -H 'Range: bytes=0-1,8-9' \
  http://localhost:8080/api/files/sample
```

Dự kiến `206`, `Content-Type: multipart/byteranges; boundary=...`, từng part chứa `Content-Range`, phần `AB` và `IJ`. Boundary được tạo động, không hardcode trong tests. Với binary lớn, dùng `curl -D headers.txt -o bytes.bin` để không in nội dung file ra terminal.

Trên Windows PowerShell, `curl` có thể được ánh xạ đến công cụ khác tùy môi trường; hãy sử dụng `curl.exe` nếu cần các options curl chính xác.

## 8. Kiểm thử hợp đồng bằng MockMvc

**`src/test/java/demo/ranges/SampleFileControllerTest.java`**

```java
package demo.ranges;

import java.nio.charset.StandardCharsets;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.ResourceRegion;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpRange;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SampleFileControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void noRangeReturnsWholeResource() throws Exception {
        mvc.perform(get("/api/files/sample"))
           .andExpect(status().isOk())
           .andExpect(header().string(
                    HttpHeaders.ACCEPT_RANGES, "bytes"))
           .andExpect(content().bytes(
                    "ABCDEFGHIJ".getBytes(StandardCharsets.US_ASCII)));
    }

    @Test
    void firstFourBytesReturn206() throws Exception {
        mvc.perform(get("/api/files/sample")
                    .header(HttpHeaders.RANGE, "bytes=0-3"))
           .andExpect(status().isPartialContent())
           .andExpect(header().string(
                    HttpHeaders.CONTENT_RANGE, "bytes 0-3/10"))
           .andExpect(content().bytes(
                    "ABCD".getBytes(StandardCharsets.US_ASCII)));
    }

    @Test
    void suffixRangeSelectsLastThreeBytes() throws Exception {
        mvc.perform(get("/api/files/sample")
                    .header(HttpHeaders.RANGE, "bytes=-3"))
           .andExpect(status().isPartialContent())
           .andExpect(header().string(
                    HttpHeaders.CONTENT_RANGE, "bytes 7-9/10"))
           .andExpect(content().bytes(
                    "HIJ".getBytes(StandardCharsets.US_ASCII)));
    }

    @Test
    void openEndedRangeSelectsRest() throws Exception {
        mvc.perform(get("/api/files/sample")
                    .header(HttpHeaders.RANGE, "bytes=7-"))
           .andExpect(status().isPartialContent())
           .andExpect(header().string(
                    HttpHeaders.CONTENT_RANGE, "bytes 7-9/10"))
           .andExpect(content().bytes(
                    "HIJ".getBytes(StandardCharsets.US_ASCII)));
    }

    @Test
    void invalidOffsetReturns416() throws Exception {
        mvc.perform(get("/api/files/sample")
                    .header(HttpHeaders.RANGE, "bytes=20-30"))
           .andExpect(status().isRequestedRangeNotSatisfiable())
           .andExpect(header().string(
                    HttpHeaders.CONTENT_RANGE, "bytes */10"));
    }

    @Test
    void multipleRangesUseMultipartByteranges() throws Exception {
        MvcResult result = mvc.perform(get("/api/files/sample")
                    .header(HttpHeaders.RANGE, "bytes=0-1,8-9"))
           .andExpect(status().isPartialContent())
           .andReturn();

        String contentType = result.getResponse().getContentType();
        assertTrue(contentType != null &&
                contentType.startsWith("multipart/byteranges;"));

        String body = new String(
                result.getResponse().getContentAsByteArray(),
                StandardCharsets.ISO_8859_1);
        assertTrue(body.contains("Content-Range: bytes 0-1/10"));
        assertTrue(body.contains("Content-Range: bytes 8-9/10"));
        assertTrue(body.contains("AB"));
        assertTrue(body.contains("IJ"));
    }

    @Test
    void httpRangeCreatesCorrectResourceRegion() {
        Resource resource = new ByteArrayResource(
                "ABCDEFGHIJ".getBytes(StandardCharsets.US_ASCII));
        List<HttpRange> ranges = HttpRange.parseRanges("bytes=2-5");
        List<ResourceRegion> regions =
                HttpRange.toResourceRegions(ranges, resource);

        assertEquals(1, regions.size());
        assertEquals(2L, regions.get(0).getPosition());
        assertEquals(4L, regions.get(0).getCount());
    }
}
```

Chạy:

```bash
mvn test
```

Có **7 test methods**. Nếu tất cả pass trên project tạo đúng file, Maven kết thúc exit code `0` và tổng kết thường có `Tests run: 7, Failures: 0, Errors: 0, Skipped: 0`. Đây là mã học tập đã được thiết kế theo API của Java 17 và Spring Boot 3.3.5; bài này không tuyên bố đã chạy Maven trên môi trường tạo Sheet.

MockMvc kiểm tra pipeline MVC, nhưng không đại diện đầy đủ cho reverse proxy, cache, HTTP compression, connection failures hoặc streaming file hàng GB. Với binary thật cần kiểm thử end-to-end qua embedded server và CDN/proxy.

## 9. HttpRange và ResourceRegion: API bên dưới

`HttpRange` là abstraction cho các vùng bytes client yêu cầu. Có thể parse header:

```java
List<HttpRange> ranges =
        HttpRange.parseRanges("bytes=2-5");
List<ResourceRegion> regions =
        HttpRange.toResourceRegions(ranges, resource);
```

Đây là snippet cần biến `resource`, imports và context phù hợp; `httpRangeCreatesCorrectResourceRegion` ở phần tests đã cho một ví dụ chạy trọn.

Các factories khác:

```java
HttpRange firstFour = HttpRange.createByteRange(0, 3);
HttpRange fromSeven = HttpRange.createByteRange(7);
HttpRange lastThree = HttpRange.createSuffixRange(3);
```

`ResourceRegion` gồm `Resource` gốc, `position` và `count`:

```java
ResourceRegion region = new ResourceRegion(resource, 2L, 4L);
```

**`count` là số bytes, không phải last byte offset.** Với `bytes=2-5`: position = 2, count = 4. Nếu gán count = 5 thì vùng sẽ lấy thêm byte thứ 6, gây off-by-one.

`HttpRange.parseRanges` có thể ném `IllegalArgumentException` khi input sai hoặc quá nhiều ranges; `toResourceRegions` tính dựa vào length của Resource và có thể từ chối dữ liệu không thỏa. Đừng tự parse bằng regex đơn giản mà không xử lý suffix, overflow, comma-separated ranges và content-length thay đổi.

`ResourceRegionHttpMessageConverter` ghi một hoặc nhiều `ResourceRegion` ra HTTP response. Dùng manual `ResourceRegion` khi cần giới hạn range policy, backing store đặc biệt hoặc custom handling; nếu chỉ tải file thông thường thì `ResponseEntity<Resource>` với 200 đơn giản và ít lỗi hơn.

### Khi tự tạo response 206

Nếu bạn quyết định đọc header Range và trả regions thủ công, phải chịu trách nhiệm:

1. Đọc/validate Range và total size của **đúng selected representation**.
2. Kiểm tra authorization, preconditions và `If-Range` đúng ngữ nghĩa.
3. Nếu không dùng Range: trả 200 + toàn bộ Resource.
4. Nếu một hoặc nhiều range hợp lệ: trả 206 + đúng region(s), content type và Content-Range/multipart.
5. Nếu không thỏa: trả 416 + `Content-Range: bytes */total` khi thích hợp.
6. Không để `Content-Length` của 206 bằng chiều dài toàn bộ file.
7. Giới hạn số ranges, tổng bytes, seek costs, header length và read time.
8. Không chuyển binary response sang JSON envelope qua `ResponseBodyAdvice`.

Nếu không cần các trách nhiệm đặc biệt đó, đừng tự tái triển khai protocol đã được Spring hỗ trợ.

## 10. If-Range, ETag và bản nhất quán của tài nguyên

Client tải một phần file v1, sau đó file trên server thay thành v2. Nếu client yêu cầu phần còn lại và ghép bytes của hai versions, tệp cuối sẽ lỗi. Vì vậy **resume download** an toàn cần xác định toàn bộ các byte thuộc cùng một phiên bản của representation.

HTTP dùng:

- `ETag`: validator của representation.
- `Last-Modified`: metadata về thời gian sửa đổi.
- `If-None-Match` / `If-Modified-Since`: conditional caching, có thể dẫn đến `304 Not Modified`.
- `If-Range`: yêu cầu áp dụng Range **chỉ khi representation vẫn match validator**; nếu không, gửi toàn bộ.

Ví dụ:

```http
GET /api/files/video HTTP/1.1
Range: bytes=1000-
If-Range: "file-version-v7"
```

Nếu `If-Range` match theo **strong validation**, server có thể trả 206. Nếu không match, server phải bỏ qua Range và gửi toàn bộ representation (thường 200). **Weak ETag** có dạng `W/"..."` không thích hợp cho strong comparison trong If-Range.

**Lưu ý Spring MVC 6.1:** Nhánh auto range khi trả `ResponseEntity<Resource>` quan sát `Range` và status 200, nhưng **không nên mặc định** rằng application đã có full `If-Range` handling và snapshot consistency trong mọi đường Servlet/proxy. Khi tệp có thể thay đổi, kiểm thử cụ thể hoặc triển khai precondition/validator logic ở tầng phù hợp; đừng nối file v1 với v2 chỉ vì HTTP trả 206.

Nếu conditional GET trả `304` thì không xử lý Range như một phần của 200. Theo RFC, Range được xét sau các preconditions và chỉ có ý nghĩa khi response không Range sẽ là 200.

### Strong validator theo bytes

Một strong ETag nên gắn chắc với bytes của representation được chọn. Có thể dùng immutable storage version hoặc digest nội dung khi phù hợp; đừng tính SHA-256 của file 8GB từ đầu ở **mọi** Range request nếu backend không có cache metadata. Với file có Content-Encoding khác nhau cần kiểm tra validators theo đúng representation, tránh cùng validator cho hai byte sequences không giống nhau.

## 11. FileSystemResource, PathResource và bảo mật

Demo dùng `ByteArrayResource` vì chỉ có 10 bytes. Với file thật, nên dùng `FileSystemResource` hoặc `PathResource` có kích thước thực và stream đọc lại:

```java
Path file = trustedRoot.resolve(serverOwnedKey).normalize();
if (!file.startsWith(trustedRoot) ||
        !Files.isRegularFile(file) ||
        !Files.isReadable(file)) {
    throw new ResponseStatusException(
            HttpStatus.NOT_FOUND, "File not found");
}
Resource resource = new FileSystemResource(file);
return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .body(resource);
```

Đây là **snippet** chưa có class/imports hoặc định nghĩa `trustedRoot`/`serverOwnedKey`; nó chỉ diễn đạt ý tưởng. Thực tế:

- Kiểm tra quyền truy cập resource **trước** khi trả Resource.
- Không lấy tên tệp raw từ client hay request parameter làm storage path. Dùng storage key server tạo.
- `Path.normalize()` / `startsWith()` chưa đủ để ngăn symlink race hoặc TOCTOU; cần filesystem isolation và security policy.
- Đặt `Content-Disposition` đúng, encode filename an toàn; tránh dùng original filename từ upload làm đường dẫn lưu.
- Với file user-uploaded, cân nhắc `X-Content-Type-Options: nosniff` và loại content được phục vụ để tránh trình duyệt thực thi content nguy hiểm.
- Tài nguyên cần stable contentLength và nội dung ổn định trong lúc gửi. Nếu tệp đổi kích thước giữa lúc tính Range và đọc, `Content-Range` có thể sai.

Đối với object storage/CDN có hỗ trợ byte-range natively, có thể để backend/storage thực hiện Range trực tiếp thay vì download cả object về Java rồi tự skip; điều này quan trọng với file hàng GB.

## 12. Content-Encoding, caching và proxy

Range offsets áp dụng cho **selected representation bytes**. Một file 1000 bytes có thể gzip thành 400 bytes; `Range: bytes=0-99` của representation gzip không thể ghép tùy tiện với đoạn 0–99 của file chưa nén.

Tầng compression/filter/CDN có thể biến đổi response và làm các header sau không còn đúng:

- `Content-Range` và `Content-Length` nếu bytes bị thay.
- `ETag` nếu validator không đại diện cùng byte representation.
- `Vary: Accept-Encoding` và `Cache-Control` khi proxy cache các variants.
- `Content-Type` / `Content-Disposition` / `Accept-Ranges` nếu sản phẩm chuyển từ file download sang view nội bộ.

Nếu cần streaming/resume/video đáng tin, nên tránh biến đổi content coding tự động không kiểm soát trên endpoint range, hoặc bảo đảm mọi offsets, validators và cache keys nhất quán. Test trực tiếp origin và qua proxy/CDN, không chỉ MockMvc local.

## 13. HEAD, media players và download resume

**HEAD** trả metadata tương ứng GET nhưng không gửi response body. Nó hữu ích để client biết kích thước, validator và `Accept-Ranges`. Tuy nhiên việc trả `HEAD` phải thực sự không gửi bytes; framework/controller/proxy cần được kiểm tra riêng.

**Video player** có thể sử dụng Range để seek. Nhưng HTTP 206 không tự làm video seekable: file container/index/codec cũng phải hỗ trợ. Tương tự, PDF viewer chỉ tải từng phần hiệu quả khi cấu trúc PDF cho phép progressive access phù hợp.

**Resume client:** nếu nhận 206 và Content-Range khớp offset/version thì có thể nối bytes. Nếu server trả **200** thì nên coi như một full representation (thay thế file tạm thay vì nối). Nếu trả 416 thì kiểm tra total, validators, bytes đã tải và quyết định hoàn tất hay tải lại; không lặp retry 416 vô hạn.

## 14. Hiệu năng và hạn chế Range abuse

- Client có thể yêu cầu rất nhiều ranges nhỏ, dẫn đến seek/file reads và multipart overhead lớn. Áp giới hạn số ranges, tổng byte count, header size, timeout và rate limiting khi phù hợp.
- Nếu server đọc toàn bộ file vào `byte[]` rồi trả một đoạn, đã mất phần lớn lợi ích range. Với file lớn dùng seekable source hoặc native range I/O.
- `InputStream.skip()` trên một số nguồn có thể cần thực sự tiêu thụ bytes bị bỏ qua; API có `skip` không đồng nghĩa với random access hiệu quả.
- Nếu client gửi ranges trùng/lân cận, server có thể gộp theo RFC để giảm overhead.
- Mỗi request Range vẫn phải qua authorization và policy của tài nguyên như full GET; không tiết lộ dữ liệu chỉ vì gửi một phần.
- File privately owned cần `Cache-Control` phù hợp, tránh cache dùng chung làm lộ dữ liệu giữa users.
- Tránh ghi log body file/range bytes hoặc access tokens để debug.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `Range` nhưng response luôn 200 | Body không phải `Resource` thích hợp, dùng `InputStreamResource`, status ban đầu khác 200, proxy bỏ Range | Kiểm tra Resource class, return type, original HTTP status |
| `206` nhưng gửi cả file | Controller đặt status 206 thủ công mà không cắt body | Để Spring auto-range từ status 200 hoặc tự dùng ResourceRegion đúng |
| Header `Content-Range` thiếu/mâu thuẫn | Tự gắn header sai hoặc converter khác ghi body | Test status, bytes và total length |
| Off-by-one khi lấy đoạn | Nhầm count với last position | `count=last-first+1` |
| `416` khi bắt đầu ở total size | Request có `first >= totalLength` | Kiểm tra `bytes */total` |
| Resume file bị hỏng | Các đoạn thuộc file versions khác | Strong validators và If-Range/versioned object |
| `multipart/byteranges` bị parse sai | Coi nó là multipart/form-data hoặc lấy một top-level Content-Range | Parse boundary/headers từng part |
| Download tốn RAM | `Files.readAllBytes` trên file lớn | FileSystemResource/PathResource/backend native ranged read |
| Browser phát video không seek | Media index, proxy compression hoặc headers sai | Kiểm tra file media, range responses end-to-end |
| `Content-Length` quá lớn trong 206 | Set bằng toàn file thay vì partial body | Để converter tính length đúng |
| Test MockMvc pass, production fail | Proxy/CDN/HTTP coding/streaming khác | End-to-end integration test |
| Tải file sai quyền | Dùng path ID không kiểm tra principal/resource | Authentication, authorization và storage keys |
| Tải file cũ/mới lẫn nhau | File bị sửa trong lúc đọc | Immutable version/snapshot và ETag |
| CPU tăng bởi hàng trăm ranges | Thiếu range count/size policy | Giới hạn parser và hạ tầng |

Chẩn đoán nhanh:

1. Xem status, Range request, `Accept-Ranges`, `Content-Range`, `Content-Length`, `Content-Type`.
2. So total size hiện tại và byte offset tính theo **selected representation**.
3. Kiểm tra Resource có repeatable stream và contentLength chính xác không.
4. Với một range, so `last-first+1` với bytes response.
5. Với nhiều range, kiểm tra từng `Content-Range` part và dynamic boundary.
6. Đối chiếu qua origin và proxy để phân biệt compression/cache.
7. Kiểm tra file version/ETag/If-Range khi resume.
8. Kiểm tra authorization, byte size limits và resource exhaustion.

## 16. Bài tập tự kiểm tra

1. Tài nguyên dài 10 bytes, `bytes=2-5` tạo `ResourceRegion.position`, `count` và body gì?
2. Vì sao `bytes=-3` và `bytes=3-` không tương đương?
3. `Content-Range: bytes 7-9/10` có số bytes bao nhiêu?
4. Nếu trả `ResponseEntity.status(PARTIAL_CONTENT).body(resource)`, Spring có tự cắt Resource không?
5. Vì sao `InputStreamResource` không phù hợp auto-range?
6. 416 có thể dùng `Content-Range` theo dạng nào?
7. Có được đặt một `Content-Range` top-level trong multipart/byteranges nhiều phần không?
8. Tại sao cần `If-Range` và strong ETag với resume trên file mutable?
9. Vì sao MockMvc test không thay thế proxy integration test?
10. Vì sao Content-Encoding ảnh hưởng offsets?
11. Một GET có Range có được bỏ qua quyền truy cập không?
12. Với 416, client có nên tự nối body lỗi vào file tạm không?

**Gợi ý:** (1) Position=2, count=4, CDEF. (2) Suffix lấy 3 byte cuối, open-ended từ offset 3. (3) 3 bytes. (4) Không; auto-range cần response ban đầu 200 và Resource phù hợp. (5) Stream một lần khó biết length và đọc lại. (6) `bytes */total`. (7) Không; mỗi part có Content-Range riêng. (8) Tránh nối dữ liệu khác phiên bản. (9) Compression/cache/container khác MockMvc. (10) Range tính theo encoded representation bytes. (11) Không. (12) Không; phải kiểm tra total và validators.

## 17. Tài liệu tham khảo

- [RFC 9110 — Range Requests, Content-Range, 206 và 416](https://www.rfc-editor.org/rfc/rfc9110.html)
- [Spring Framework — Range Requests (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-range.html)
- [Spring Framework 6.1 — HttpRange Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/HttpRange.html)
- [Spring Framework 6.1 — ResourceRegionHttpMessageConverter](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/converter/ResourceRegionHttpMessageConverter.html)
- [Spring Framework 6.1 — ResourceRegion Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/core/io/support/ResourceRegion.html)
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [Spring MVC 6.1 source — AbstractMessageConverterMethodProcessor](https://github.com/spring-projects/spring-framework/blob/v6.1.14/spring-webmvc/src/main/java/org/springframework/web/servlet/mvc/method/annotation/AbstractMessageConverterMethodProcessor.java)
- [MDN — Range requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Range_requests)

**Tổng kết:** Client dùng `Range` để yêu cầu byte offsets của một representation. Spring MVC có thể trả `206` và `Content-Range` tự động khi controller trả `Resource`/`ResponseEntity<Resource>` status ban đầu 200 (trừ `InputStreamResource`). `HttpRange` biểu diễn range do client yêu cầu, `ResourceRegion` giữ vùng position/count và `ResourceRegionHttpMessageConverter` ghi single/multipart bytes. Production còn phải quan tâm authorization, validator, caching, compression, version consistency và giới hạn requests.
