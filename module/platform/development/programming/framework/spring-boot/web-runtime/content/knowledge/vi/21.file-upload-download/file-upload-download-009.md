# Trả tệp bằng Resource, Content-Disposition và kiểu nội dung phù hợp trong Spring Boot

## 1. Mục tiêu và kết quả cần đạt

Khi người dùng nhấn **Tải báo cáo**, **Xuất CSV**, **Tải tài liệu PDF** hoặc **Xem trước một tệp**, server phải trả về **đúng byte của tệp**, đồng thời mô tả đúng cách trình duyệt/client nên xử lý phản hồi. Với **Spring Boot + Spring MVC**, cách phổ biến và rõ ràng là trả về `ResponseEntity<Resource>`, thiết lập `Content-Type`, `Content-Disposition` và các header liên quan theo một chính sách do server kiểm soát.

Sau bài này, bạn có thể:

1. Chọn `Resource` thích hợp cho classpath, filesystem, byte array và stream; không đọc toàn bộ file lớn vào RAM một cách không cần thiết.
2. Dùng `ResponseEntity<Resource>` để kiểm soát HTTP status, headers và response body.
3. Phân biệt `Content-Type` (định dạng dữ liệu) với `Content-Disposition` (gợi ý hiển thị hay tải xuống); đặt tên tệp UTF-8 an toàn.
4. Dùng `Content-Length` đúng khi biết kích thước mà không làm hỏng stream; hiểu ý nghĩa của cache, MIME sniffing và range requests.
5. Thiết kế API download dựa trên **ID hợp lệ + kiểm tra quyền**, không dùng raw path do client chỉ định; ngăn path traversal, lộ tệp, header injection và trả nhầm MIME.
6. Chạy ứng dụng Spring Boot Java 17+ và kiểm thử các HTTP header, trạng thái và byte của file.

**Nguyên tắc:** một response file đúng không chỉ là body có dữ liệu; nó cần **đúng nội dung, đúng MIME, đúng tên tải xuống, đúng quyền truy cập và đúng cách browser xử lý**.

## 2. Một HTTP response trả tệp có những thành phần nào?

Ví dụ một response tải báo cáo:

```http
HTTP/1.1 200 OK
Content-Type: text/csv; charset=UTF-8
Content-Disposition: attachment; filename="bao-cao.csv"
Content-Length: 24
Cache-Control: no-store
X-Content-Type-Options: nosniff

id,name
1,An
2,Binh
```

**Đây chỉ là sơ đồ minh họa giao thức**, không phải response byte-for-byte từ ví dụ Java: `Content-Length: 24`, dòng dữ liệu, số header, thứ tự header và newline trong response thực tế phải khớp kích thước thật của file và cấu hình server. Không sao chép một `Content-Length` minh họa vào code.

Vai trò của từng phần:

| Thành phần | Vai trò | Lưu ý |
| --- | --- | --- |
| `200 OK` | Request thành công, server trả body | Trường hợp thiếu file thường là 404; thiếu quyền có thể là 403 hoặc 404 theo chính sách |
| `Content-Type` | Mô tả media type của byte trả về, ví dụ `application/pdf` | Không suy MIME hoàn toàn từ tên do user đưa |
| `Content-Disposition` | `attachment` gợi ý tải về; `inline` gợi ý trình duyệt hiển thị nếu hỗ trợ | Không thay thế cơ chế kiểm tra MIME và bảo mật nội dung |
| `filename`/`filename*` | Tên file được gợi ý khi lưu xuống máy client | Không chứa path, ký tự điều khiển hoặc dữ liệu chưa kiểm tra |
| `Content-Length` | Kích thước body tính bằng **byte**, không phải số ký tự | Chỉ đặt khi tính đúng, không tiêu thụ một stream dùng một lần |
| `Cache-Control` | Điều khiển khả năng lưu/cache response | Tài liệu riêng tư nhạy cảm thường dùng `no-store` |
| `X-Content-Type-Options: nosniff` | Yêu cầu browser hạn chế MIME sniffing ở một số tình huống | Không sửa được nội dung độc hại hoặc MIME sai |

Nếu client dùng `curl -i`, phần header và phần body xuất hiện chung trên terminal. Với file nhị phân như PDF, ZIP hay XLSX, đừng in byte thô ra terminal; dùng `curl -o result.pdf ...` để lưu file.

### 2.1. `Content-Type` không phải tên tệp

Một tệp `report.pdf` nên được trả dưới dạng `application/pdf` nếu server đã xác định đó là PDF hợp lệ. `Content-Type: text/html` hoặc `text/plain` cho byte PDF có thể làm browser xử lý sai. Ngược lại, đặt tên một file HTML là `report.pdf` không tự biến nó thành PDF.

Chọn kiểu nội dung dựa trên **metadata đã xác thực do server quản lý**, đồng thời kiểm tra định dạng thật đối với tệp tải lên không đáng tin cậy khi cần. Phần mở rộng chỉ là một tín hiệu; người dùng hoàn toàn có thể đặt tên sai.

### 2.2. `Content-Disposition` không giống `Content-Type`

Hai response cùng chứa byte PDF có thể có mục đích khác:

```http
Content-Type: application/pdf
Content-Disposition: inline; filename="guide.pdf"
```

`inline` cho biết nội dung **có thể** được hiển thị trong browser (nếu browser/plugin và các header khác cho phép). Đối với download:

```http
Content-Type: application/pdf
Content-Disposition: attachment; filename="guide.pdf"
```

`attachment` gợi ý trình duyệt tải về. Đây không phải cam kết client nào cũng mở hộp thoại giống nhau; ứng dụng, browser, download manager và `<a download>` ở trang web có thể có hành vi riêng. Với HTML/SVG hoặc nội dung người dùng không tin cậy, **không bật inline chỉ vì client yêu cầu**: đây có thể là XSS/active-content risk, đặc biệt khi được phục vụ trên cùng origin với ứng dụng chính.

## 3. `Resource` là gì và nên chọn implementation nào?

`org.springframework.core.io.Resource` là abstraction của Spring cho một tài nguyên có thể đọc. Nó cung cấp các khả năng như `exists()`, `isReadable()`, `getInputStream()`, `contentLength()`, `getFilename()`, `getURL()` và một số API về file. Nó **không có nghĩa** mọi resource đều là một `java.io.File` nằm ngoài đĩa.

| Implementation | Phù hợp khi | Cảnh báo |
| --- | --- | --- |
| `ClassPathResource` | File đi kèm ứng dụng, ví dụ `src/main/resources/downloads/guide.txt` | Có thể nằm trong JAR; **không dùng `getFile()` làm giả định chung** |
| `FileSystemResource` / `PathResource` | File nằm trên filesystem do server kiểm soát | Cần policy root, authorization, quyền OS và chống path traversal/symlink |
| `ByteArrayResource` | Nội dung nhỏ được tạo trong RAM, ví dụ vài dòng CSV | Byte array được giữ trong memory; không phù hợp với file rất lớn |
| `InputStreamResource` | Stream một lần, không có dạng resource tốt hơn | Dùng thận trọng; tính `contentLength()` có thể tiêu thụ stream; không mặc định tái đọc được |
| `UrlResource` | Nguồn file/URL cụ thể do server tin cậy | Không nhận tùy ý `https://...` từ user: có rủi ro SSRF, redirect sang mạng nội bộ |

Spring MVC dùng `ResourceHttpMessageConverter` để đưa dữ liệu từ `Resource` tới HTTP response trong trường hợp thích hợp. Lợi ích của `ResponseEntity<Resource>` so với cách `Files.readAllBytes(...)` là không bắt buộc ứng dụng phải tạo một `byte[]` giữ toàn bộ file trong heap trước khi trả (dù đường đi I/O và buffering thực tế còn tùy resource/converter/container).

### 3.1. Không nhầm `ClassPathResource` với đường dẫn filesystem

`src/main/resources/downloads/guide.txt` sau khi build trở thành resource trong classpath (ví dụ dưới `BOOT-INF/classes/downloads/guide.txt` trong executable JAR Spring Boot). Tải bằng:

```java
Resource resource = new ClassPathResource("downloads/guide.txt");
```

Không dựa vào:

```java
// Không bảo đảm chạy khi tài nguyên nằm bên trong executable JAR.
File file = resource.getFile();
```

`ClassPathResource` vẫn có thể cung cấp input stream ngay cả khi không có đường dẫn `File` độc lập. Đó là lý do dùng `Resource` và để Spring sao chép body là lựa chọn phù hợp.

### 3.2. `InputStreamResource`: tránh tính length trên stream dùng một lần

Ví dụ dễ sai:

```java
// Đoạn minh họa lỗi: inputStream có thể chỉ đọc được một lần.
InputStreamResource body = new InputStreamResource(inputStream);
long size = body.contentLength(); // có nguy cơ đọc hết stream!
```

Không nên tự gọi `contentLength()` trên stream dùng một lần để tạo `Content-Length`; thao tác đó có thể tiêu thụ dữ liệu mà response cần gửi. Nếu nguồn file có metadata kích thước đáng tin cậy thì dùng metadata; nếu không biết, có thể **không đặt Content-Length** và để container quyết định HTTP framing. Với file nhỏ trong RAM, `ByteArrayResource` có thể thích hợp hơn. Với dữ liệu tạo theo luồng, `StreamingResponseBody` là lựa chọn khác trong Spring MVC, cần hiểu executor, lifecycle stream và xử lý lỗi sau khi đã commit response.

## 4. `Content-Disposition` và tên file Unicode

Spring cung cấp `org.springframework.http.ContentDisposition` với builder `attachment()` và `inline()`. Ví dụ:

```java
ContentDisposition disposition = ContentDisposition.attachment()
    .filename("Hướng dẫn sử dụng.txt", StandardCharsets.UTF_8)
    .build();
```

Header tạo ra tuân theo cơ chế encoding tương thích với tên UTF-8, gồm tham số `filename*` theo RFC 5987/RFC 6266 ở các phiên bản Spring Framework tương thích. **Không nên tự ghép string header bằng tên file do người dùng đưa**, chẳng hạn:

```java
// ANTI-PATTERN: có thể dẫn tới filename/path hoặc header injection sai.
String header = "attachment; filename=\"" + userFilename + "\"";
```

Đối với tên có dấu hoặc ký tự ngoài ASCII:

- `filename="..."` thường là tên tương thích cho client cũ.
- `filename*=UTF-8''...` biểu thị tên đã percent-encode theo RFC 5987 cho client hiểu chuẩn này.
- Spring `ContentDisposition` xử lý escape/encoding; vẫn phải chọn **tên file hợp lệ, không chứa đường dẫn hoặc ký tự điều khiển** từ phía server.
- Một số download client có cách hỗ trợ `filename*` khác nhau; dùng tên ASCII đơn giản khi thực sự cần tương thích với client cũ, đồng thời kiểm thử browser/curl mục tiêu.

Không coi filename là đường dẫn lưu file ở server hoặc đích cuối cùng trên máy client. Theo HTTP, nó chỉ là **gợi ý tên**. Client cần xử lý ký tự `/`, `\` và các tên đặc biệt an toàn; server cũng phải tránh phát tên có dấu phân tách hay ký tự không hợp lệ.

Trong project mẫu phía dưới, ID URL chỉ chọn một **record metadata có sẵn**; tên tải xuống là giá trị do server cung cấp, không lấy trực tiếp từ request.

## 5. Chọn `Content-Type` đúng theo định dạng

Ví dụ thường gặp:

| Loại file | `Content-Type` phù hợp | Disposition phổ biến |
| --- | --- | --- |
| Văn bản UTF-8 | `text/plain; charset=UTF-8` | `attachment` để tải, `inline` khi chủ đích chỉ xem text |
| CSV UTF-8 | `text/csv; charset=UTF-8` | Thường `attachment` |
| PDF | `application/pdf` | `inline` khi chủ đích xem và nội dung đáng tin; `attachment` để tải |
| PNG | `image/png` | `inline` khi dùng trong giao diện hoặc `attachment` khi tải |
| JPEG | `image/jpeg` | `inline` hoặc `attachment` |
| ZIP | `application/zip` | Thường `attachment` |
| Excel XLSX | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | Thường `attachment` |
| Không có định dạng đã xác định | `application/octet-stream` | Thường `attachment` |

Đây là các ví dụ media type, không phải một hàm phân loại tất cả file. Khi dữ liệu đến từ người dùng, **không tin riêng `MultipartFile.getContentType()`** hay phần mở rộng trong `getOriginalFilename()`. Nếu yêu cầu hệ thống nghiêm ngặt, cần xác thực nội dung thực, giới hạn định dạng và áp dụng virus/malware scanning theo môi trường.

Với nội dung nhạy cảm:

- Dùng `Content-Disposition: attachment` khi không cần preview.
- Xem xét `X-Content-Type-Options: nosniff` và security headers phù hợp.
- Không cho người dùng tùy ý yêu cầu trả một loại MIME khác chỉ bằng tham số query.
- Tệp CSV xuất từ dữ liệu do user nhập có thể gây **CSV/formula injection** khi mở bằng spreadsheet, nếu một ô bắt đầu bằng công thức như `=`, `+`, `-` hoặc `@`. `Content-Type` và `attachment` **không loại bỏ rủi ro này**; cần chính sách xuất CSV an toàn theo consumer cụ thể.
- Không phục vụ HTML/SVG do user upload như nội dung inline trên origin có cookie phiên đăng nhập nếu chưa có biện pháp cô lập/sanitization thích hợp.

## 6. Ví dụ ứng dụng Spring Boot chạy được

Ví dụ dùng **Java 17+**, **Spring Boot 3.x**, **Spring MVC** với `spring-boot-starter-web` và embedded Tomcat mặc định. Chỉ có hai file được phép tải bằng ID `intro` và `table`. File còn lại trong classpath **không tự có download endpoint**.

### 6.1. Cấu trúc tệp

```text
src/
├─ main/
│  ├─ java/com/example/demo/
│  │  ├─ DownloadApplication.java
│  │  └─ DownloadController.java
│  └─ resources/
│     ├─ downloads/
│     │  ├─ intro.txt
│     │  └─ table.csv
│     └─ application.properties
└─ test/
   └─ java/com/example/demo/
      └─ DownloadControllerTest.java
```

Dependency chính là `org.springframework.boot:spring-boot-starter-web`; phần test dùng `spring-boot-starter-test`. Tạo project Spring Initializr, chọn Java 17+ và các dependency tương ứng. File mẫu đặt trong `resources/downloads/` (không thuộc các static document root mặc định như `static/` hoặc `public/`).

### 6.2. Lớp main

**`src/main/java/com/example/demo/DownloadApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DownloadApplication {
    public static void main(String[] args) {
        SpringApplication.run(DownloadApplication.class, args);
    }
}
```

### 6.3. Controller trả Resource + headers

**`src/main/java/com/example/demo/DownloadController.java`**

```java
package com.example.demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class DownloadController {

    // Danh sách file và metadata do server quyết định, không dùng path từ URL.
    private static final Map<String, FileSpec> FILES = Map.of(
        "intro",
        new FileSpec(
            "downloads/intro.txt",
            "Hướng dẫn Spring Boot.txt",
            MediaType.parseMediaType("text/plain;charset=UTF-8")
        ),
        "table",
        new FileSpec(
            "downloads/table.csv",
            "bao-cao.csv",
            MediaType.parseMediaType("text/csv;charset=UTF-8")
        )
    );

    @GetMapping("/downloads/{id}")
    public ResponseEntity<Resource> download(@PathVariable String id)
            throws IOException {
        return respond(id, false);
    }

    // Chỉ cho xem trước file text cố định do server chọn.
    @GetMapping("/previews/intro")
    public ResponseEntity<Resource> previewIntro() throws IOException {
        return respond("intro", true);
    }

    private ResponseEntity<Resource> respond(String id, boolean preview)
            throws IOException {
        FileSpec spec = FILES.get(id);
        if (spec == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Download not found"
            );
        }

        Resource resource = new ClassPathResource(spec.path());
        if (!resource.exists() || !resource.isReadable()) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Resource not available"
            );
        }

        ContentDisposition disposition = preview
            ? ContentDisposition.inline()
                .filename(spec.downloadName(), StandardCharsets.UTF_8)
                .build()
            : ContentDisposition.attachment()
                .filename(spec.downloadName(), StandardCharsets.UTF_8)
                .build();

        return ResponseEntity.ok()
            .contentType(spec.contentType())
            .contentLength(resource.contentLength())
            .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
            .header("X-Content-Type-Options", "nosniff")
            .cacheControl(CacheControl.noStore())
            .body(resource);
    }

    private record FileSpec(
        String path,
        String downloadName,
        MediaType contentType
    ) {}
}
```

**`src/main/resources/downloads/intro.txt`** (lưu dưới UTF-8, cuối tệp có **một ký tự xuống dòng LF**):

```text
Xin chào Spring Boot!
```

**`src/main/resources/downloads/table.csv`** (UTF-8, LF):

```csv
id,ten
1,An
2,Binh
```

**`src/main/resources/application.properties`**

```properties
server.port=8080
```

**Giải thích kỹ từng lựa chọn:**

1. **`Map<String, FileSpec>`** là allowlist. Client cung cấp một ID logic `intro` hoặc `table`, **không cung cấp file path, tên tệp hoặc MIME**.
2. **`ClassPathResource`** đọc resource đóng gói trong ứng dụng cả khi chạy bằng executable JAR. Controller không cần chuyển sang `java.io.File`.
3. **`exists()` / `isReadable()`** kiểm tra resource có thể phục vụ; nếu thiếu, demo trả 404. Trong production, file bắt buộc mà build thiếu có thể cần log/cảnh báo ở tầng nội bộ thay vì chỉ âm thầm báo không tìm thấy.
4. **`ContentDisposition.attachment()`** áp dụng cho download; đường xem trước `/previews/intro` chỉ cho file text đáng tin do server chọn và dùng `inline()`. Không expose một boolean `inline` do client tùy ý quyết định cho mọi file.
5. **`filename(name, UTF_8)`** tạo header cho tên Unicode đúng chuẩn hơn việc nối chuỗi. Metadata tên không đến từ raw HTTP input.
6. **`contentType(spec.contentType())`** gắn MIME đúng cho từng file. Các chuỗi `text/plain;charset=UTF-8` và `text/csv;charset=UTF-8` là media type hợp lệ.
7. **`contentLength(resource.contentLength())`** phù hợp ở đây vì `ClassPathResource` có thể mở lại stream của file nhỏ, cố định. Với nguồn streaming một lần hoặc file lớn/remote, **không làm máy chủ tải toàn bộ file chỉ để tính length**.
8. **`CacheControl.noStore()`** tránh yêu cầu browser/proxy lưu trữ tệp. Đây là ví dụ mặc định thận trọng, thích hợp với tài liệu có thể nhạy cảm; file public có thể cần caching policy khác để tối ưu hiệu năng.
9. **`nosniff`** hạn chế một số cách trình duyệt suy đoán MIME. Nó không biến byte độc hại thành an toàn.
10. **`ResponseEntity<Resource>`** là kết quả được Spring MVC xử lý qua HTTP message converter. Không trả string đường dẫn như body và không tự tạo `InputStreamResource` không cần thiết.

**Chú ý về HEAD và byte-range:** HTTP HEAD và request `Range` có hành vi riêng theo loại resource, converter và container. Với phần mềm dùng để tải tiếp video/file lớn, hãy kiểm thử `206 Partial Content`, `416 Range Not Satisfiable`, `Accept-Ranges` và cách xử lý `If-Range` cụ thể hoặc dùng static resource handler/object storage đã hỗ trợ. Không tự thêm `Accept-Ranges: bytes` nếu implementation chưa chắc chắn phục vụ đúng partial content. Ví dụ demo chủ yếu kiểm tra tải toàn bộ nội dung bằng GET.

## 7. Chạy và kiểm tra HTTP response

Từ thư mục dự án Maven Wrapper:

```bash
java -version
./mvnw spring-boot:run
```

Trong Windows, dùng `mvnw.cmd spring-boot:run`. Mở terminal khác:

```bash
curl -i http://localhost:8080/downloads/intro
curl -i http://localhost:8080/downloads/table
curl -i http://localhost:8080/previews/intro
curl -i http://localhost:8080/downloads/unknown
```

Kỳ vọng:

| URL | Status | MIME | Disposition |
| --- | --- | --- | --- |
| `/downloads/intro` | 200 | `text/plain; charset=UTF-8` | `attachment`; tên gợi ý `Hướng dẫn Spring Boot.txt` |
| `/downloads/table` | 200 | `text/csv; charset=UTF-8` | `attachment`; tên `bao-cao.csv` |
| `/previews/intro` | 200 | `text/plain; charset=UTF-8` | `inline` |
| `/downloads/unknown` | 404 | Body lỗi do Spring tạo; có thể JSON/HTML tùy request và cấu hình | Không có một file download hợp lệ |

Với `/downloads/intro`, byte của body sau header khớp chính xác tệp `intro.txt`:

```text
Xin chào Spring Boot!
```

Nội dung thực có newline LF sau dấu `!`. Header `Content-Disposition` có thể chứa một dạng tương thích `filename=...` và `filename*=UTF-8''...`; **không giả định thứ tự, casing hoặc các byte header khác ngoài contract đang kiểm thử**. Mã hash của file hoặc giá trị `Content-Length` phụ thuộc byte thực tế; chiều dài là **số byte UTF-8**, không phải số Java `String.length()`.

Lưu riêng file bằng curl:

```bash
curl -fL -o downloaded.txt http://localhost:8080/downloads/intro
curl -fL -o report.csv http://localhost:8080/downloads/table
```

`-f` báo lỗi cho nhiều response HTTP 4xx/5xx; `-L` theo redirect. Với URL không tin cậy, cần cẩn trọng chính sách redirect. `-o` chỉ định tên **tại client**, không phụ thuộc header filename. Nếu dùng `curl -OJ` để tự lấy tên gợi ý từ server, cần biết phiên bản curl/client có thể hỗ trợ `filename*` khác nhau; đừng xem hành vi này là bằng chứng server phát sai UTF-8.

Mở `http://localhost:8080/previews/intro` bằng browser để xem sự khác nhau giữa tải (`attachment`) và hiển thị text (`inline`). Khi preview PDF/HTML hay nội dung không tin cậy, cần chính sách bảo mật nghiêm ngặt hơn; không suy từ ví dụ text mà bật inline bừa bãi.

## 8. Kiểm thử tự động bằng Spring Boot + MockMvc

Thêm dependency `spring-boot-starter-test` ở test scope. Tạo:

**`src/test/java/com/example/demo/DownloadControllerTest.java`**

```java
package com.example.demo;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DownloadControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void returnsTextFileWithExpectedBytes() throws Exception {
        byte[] expected = "Xin chào Spring Boot!\n"
            .getBytes(StandardCharsets.UTF_8);

        mvc.perform(get("/downloads/intro"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.TEXT_PLAIN
            ))
            .andExpect(content().bytes(expected))
            .andExpect(header().string(
                HttpHeaders.CONTENT_DISPOSITION,
                startsWith("attachment;")
            ))
            .andExpect(header().string(
                HttpHeaders.CONTENT_DISPOSITION,
                containsString("filename*=")
            ))
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"
            ));
    }

    @Test
    void csvUsesCsvMediaTypeAndAttachment() throws Exception {
        mvc.perform(get("/downloads/table"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.CONTENT_TYPE, startsWith("text/csv")
            ))
            .andExpect(header().string(
                HttpHeaders.CONTENT_DISPOSITION,
                startsWith("attachment;")
            ));
    }

    @Test
    void onlyExplicitPreviewIsInline() throws Exception {
        mvc.perform(get("/previews/intro"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.CONTENT_DISPOSITION,
                startsWith("inline;")
            ));
    }

    @Test
    void unknownFileIdIsNotExposed() throws Exception {
        mvc.perform(get("/downloads/secret"))
            .andExpect(status().isNotFound());
    }

    @Test
    void contentLengthMatchesReturnedUtf8Bytes() throws Exception {
        byte[] expected = "Xin chào Spring Boot!\n"
            .getBytes(StandardCharsets.UTF_8);

        mvc.perform(get("/downloads/intro"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.CONTENT_LENGTH,
                String.valueOf(expected.length)
            ));
    }
}
```

Chạy test:

```bash
./mvnw test
```

Với đúng project, phiên bản Spring Boot 3.x và file UTF-8 **có một LF cuối file** như mô tả, năm test được **kỳ vọng pass**. Đây là kết quả kỳ vọng để người học kiểm tra, **không phải báo cáo đã chạy test ở một repository cụ thể**.

Nếu test byte thất bại trên Windows, kiểm tra editor đã chuyển newline thành **CRLF** (`\r\n`) hay chưa. Điều này có thể làm file khác byte so với literal `"\n"` trong test; đây không nhất thiết là lỗi controller. Test cần làm rõ byte fixture để không phụ thuộc cấu hình editor.

Điều mà test chứng minh: một ID đã đăng ký trả được file với MIME/attachment/nosniff và nội dung đúng, còn ID ngoài allowlist không truy cập được. Trong production phải bổ sung test **authentication/authorization**, versioning và file nằm ngoài thư mục cho phép, content type của PDF/ZIP thực, file lớn, request HEAD/Range, cache headers, header injection và error handling.

## 9. Tệp lớn, streaming và tải tiếp

### 9.1. Tránh `byte[]` khi không cần

Đây là mẫu dễ gây áp lực bộ nhớ khi file lớn:

```java
// Snippet minh họa; path là đường dẫn nội bộ đã được cấp quyền.
byte[] bytes = Files.readAllBytes(path);
return ResponseEntity.ok().body(bytes);
```

Với hàng trăm request đồng thời và file hàng trăm MB, giữ toàn bộ byte arrays trong heap gây tốn RAM và GC. Ưu tiên resource dạng file/path nếu phù hợp và để Spring copy stream ra response.

`ByteArrayResource` vẫn hợp lý khi dữ liệu **nhỏ, được sinh sẵn trong RAM**, ví dụ hóa đơn vài KB:

```java
byte[] data = "id,amount\n1,100\n"
    .getBytes(StandardCharsets.UTF_8);

Resource resource = new ByteArrayResource(data);
return ResponseEntity.ok()
    .contentType(MediaType.parseMediaType("text/csv;charset=UTF-8"))
    .contentLength(data.length)
    .header(HttpHeaders.CONTENT_DISPOSITION,
        ContentDisposition.attachment()
            .filename("hoa-don.csv", StandardCharsets.UTF_8)
            .build().toString())
    .body(resource);
```

Đây là đoạn minh họa bên trong một method Spring MVC thích hợp (cần import Resource, ByteArrayResource, ResponseEntity, ContentDisposition, HttpHeaders, MediaType và StandardCharsets); không phải chương trình Java standalone. Vì `ByteArrayResource` có stream tạo từ byte array, tính length đơn giản và có thể đọc lại.

### 9.2. Dữ liệu đang được tạo theo luồng

Nếu nội dung được xuất dần từ database hoặc hệ thống ngoài, có thể cân nhắc `StreamingResponseBody` trong **Spring MVC**:

```java
// Snippet minh họa trong controller MVC, không phải endpoint hoàn chỉnh.
StreamingResponseBody stream = outputStream -> {
    exportService.writeCsv(outputStream);
};
return ResponseEntity.ok()
    .contentType(MediaType.parseMediaType("text/csv;charset=UTF-8"))
    .header(HttpHeaders.CONTENT_DISPOSITION,
        ContentDisposition.attachment()
            .filename("export.csv", StandardCharsets.UTF_8)
            .build().toString())
    .body(stream);
```

`exportService` do ứng dụng định nghĩa; code này cần `StreamingResponseBody`, cấu hình Spring MVC async executor và cơ chế mở/đóng dữ liệu. Phân biệt:

- **Resource** mô tả một nguồn có thể đọc, thường phù hợp file có sẵn.
- **StreamingResponseBody** chạy callback ghi vào `OutputStream` khi server trả dữ liệu, phù hợp xuất dữ liệu lớn/sinh dần.
- Nếu exception xảy ra **sau khi HTTP response đã commit header/body**, có thể không còn đổi status 200 thành 500 được. Thiết kế log/metrics, kiểm soát lỗi và cleanup đúng.
- Bắt buộc có giới hạn thời gian, số request đồng thời, memory và timeout phù hợp. Client đóng kết nối giữa chừng là tình huống bình thường cần xử lý.

### 9.3. Range requests, conditional GET và bộ nhớ đệm

Đối với video, âm thanh, PDF lớn hoặc download resume, client có thể gửi:

```http
Range: bytes=0-1023
```

Một server hỗ trợ byte-range chính xác có thể trả `206 Partial Content` kèm `Content-Range` phù hợp, hoặc `416` khi range không hợp lệ. **Không tự hứa hỗ trợ range chỉ vì endpoint dùng `Resource`** mà chưa kiểm thử converter, loại resource và container. Spring MVC có cơ chế xử lý các trường hợp range với resource phù hợp; đối với file tĩnh thuần, `ResourceHttpRequestHandler` và static resource infrastructure thường là hướng thuận tiện hơn. CDN/object storage cũng có thể cung cấp tải lớn, nhưng phải kiểm soát URL có chữ ký, quyền truy cập và thời hạn nếu nội dung riêng tư.

Caching:

- `Cache-Control: no-store`: dữ liệu riêng, tài liệu có tính bảo mật cao, không muốn lưu trong browser/proxy.
- `Cache-Control: private`: response chỉ dành cho client cá nhân; **không đồng nghĩa no-store**.
- `Cache-Control: public, max-age=...`: chỉ khi file thật sự công khai và có chính sách cache phù hợp.
- `ETag` / `Last-Modified` với `If-None-Match` / `If-Modified-Since` hỗ trợ trả `304 Not Modified` nếu không thay đổi. ETag phải gắn với phiên bản/byte thật của tài nguyên, không sinh giá trị giả không được duy trì.
- Khi tên file, quyền truy cập hay nội dung thay đổi theo người dùng, tránh cache chung hoặc dùng URL bền vững thiếu phân quyền làm rò rỉ dữ liệu.

## 10. Bảo mật: đường dẫn, quyền, filename và MIME

### 10.1. Tuyệt đối không ghép raw input thành đường dẫn tệp

Anti-pattern:

```java
// VÍ DỤ KHÔNG AN TOÀN, không dùng cho download.
@GetMapping("/download")
public ResponseEntity<Resource> download(@RequestParam String path) {
    Resource r = new FileSystemResource("/srv/private/" + path);
    return ResponseEntity.ok().body(r);
}
```

Đoạn trên chỉ minh họa nguy cơ, không phải chương trình độc lập. Kẻ tấn công có thể đưa ký tự `../`, dạng encoded, absolute path hoặc symlink để cố đọc file ngoài vùng cho phép. **Đổi sang `Resource` không tự bảo vệ khỏi path traversal.** Vẫn cần kiểm soát **resource nào** được tạo.

Phương án an toàn hơn:

1. Client gửi **document ID**, không gửi path bất kỳ.
2. Server xác minh user hiện tại được phép tải document đó.
3. Server tra metadata nội bộ, gồm storage key/path, tên hiển thị, MIME đã xác minh, kích thước và owner/tenant.
4. Root lưu trữ là cấu hình tin cậy; kiểm tra đường dẫn canonical nằm trong root, không cho symlink thoát root hoặc tác nhân không tin cậy ghi nội dung dưới root.
5. Server trả file qua `Resource` với headers xây từ metadata đã được duyệt.
6. File thiếu nên trả 404; file có nhưng không đủ quyền phải tuân thủ chính sách 403/404 của ứng dụng, không tiết lộ tên hoặc đường dẫn nội bộ.
7. Không trả stack trace/absolute path/secret trong thông báo lỗi.

Đối với file hệ thống đã tồn tại, containment check dựa trên `Path`:

```java
// Snippet trong service, sau khi đã kiểm tra quyền bằng document ID.
Path root = Path.of("/srv/app/approved-downloads").toRealPath();
Path file = root.resolve(serverControlledRelativePath).toRealPath();

if (!file.startsWith(root) || !Files.isRegularFile(file)) {
    throw new SecurityException("Outside approved storage");
}
```

`serverControlledRelativePath` phải xuất phát từ metadata phía server; không lấy nguyên chuỗi query từ request. `Path.startsWith(Path)` so sánh theo **thành phần đường dẫn**, khác `String.startsWith` dễ bị nhầm `approved-downloads` với `approved-downloads-backup`. `toRealPath()` xử lý symlink đối với path tồn tại. **Chỉ riêng check này không giải quyết race giữa kiểm tra và mở file (TOCTOU)** nếu người không tin cậy có quyền thay cấu trúc file; cần thiết kế storage/permission/open an toàn phù hợp hệ điều hành và threat model.

### 10.2. Filename response cần giới hạn

`ContentDisposition.attachment().filename(..., UTF_8)` giúp encode header đúng, nhưng không nên lấy tên file thô chứa path, dòng xuống, ký tự điều khiển hoặc chuỗi dành riêng cho thiết bị từ client. Nên:

- Dùng tên hiển thị do server quyết định, **không dùng storage path làm tên tải về**.
- Strip directory components, giới hạn độ dài, bộ ký tự hoặc một tập tên hợp lệ theo nghiệp vụ.
- Cân nhắc tên ASCII fallback nếu client cũ yêu cầu; kiểm tra filename Unicode trên các browser cần hỗ trợ.
- Không để phần mở rộng đánh lừa người nhận: nếu tên kết thúc `.pdf` mà dữ liệu thật là HTML/JS hoặc executable, có thể gây tải xuống/phân tích sai. Kiểm soát cả MIME lẫn download name.
- Cẩn thận *reflected file download (RFD)* khi phản chiếu tham số đầu vào vào nội dung/tên file downloadable.

### 10.3. Không tin `Content-Type` của upload hoặc `Accept` của download

Nếu hệ thống cho người dùng upload PDF rồi download:

- Không chỉ kiểm tra chuỗi `upload.getContentType()` để tin file đúng PDF.
- Không nhận tham số `?type=text/html` rồi dùng nó làm `Content-Type` của response.
- Chọn media type do service lưu và xác minh, hoặc về `application/octet-stream` khi không thể khẳng định loại.
- Với HTML/SVG/script không tin cậy, ưu tiên download và cân nhắc origin cô lập; không bật inline theo ý user.
- Duy trì `nosniff` và các security headers liên quan; không dựa vào header này để thay validation.

### 10.4. Quyền truy cập không nằm trong Content-Disposition

`Content-Disposition: attachment` chỉ điều khiển cách browser nhận file, **không kiểm tra ai có quyền lấy file**. Với tài liệu cá nhân, cần authentication/authorization **trước** khi tạo response và trước khi mở file/stream. Kiểm tra theo owner/tenant trên **mỗi request**; không dựa vào việc ID “khó đoán”.

Với download URL có chữ ký: giới hạn thời hạn, scope đối tượng, phương thức và khả năng replay theo hệ thống; không dùng URL công khai vô hạn cho dữ liệu nhạy cảm. Với nội dung private, tránh cache chung/đường dẫn CDN public nếu chưa có kiểm soát đúng.

## 11. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng sửa |
| --- | --- | --- |
| API trả tên file/path dưới dạng JSON hoặc text thay vì byte file | Controller return `String` hoặc object mô tả, không phải `Resource` body | Trả `ResponseEntity<Resource>` và kiểm thử body |
| Browser hiển thị PDF thay vì tải | `inline` hoặc thiếu `attachment` | Dùng `ContentDisposition.attachment()` khi yêu cầu download |
| Tên Unicode bị lỗi | Ghép `filename=...` thô, client không hỗ trợ encoding | Dùng `filename(name, UTF_8)`; kiểm tra client thực tế |
| Download có phần mở rộng sai, không mở được | MIME/name không khớp byte | Chọn metadata đúng, xác thực loại file |
| File classpath chạy trong IDE nhưng lỗi khi chạy executable JAR | Gọi `resource.getFile()` thay vì stream | Dùng `ClassPathResource` + `ResponseEntity<Resource>` |
| File tải bị trống/cụt | Stream đã bị đọc khi tính length, stream dùng một lần | Không tính `contentLength()` trên `InputStreamResource` dùng một lần |
| RAM tăng vọt khi nhiều người tải file lớn | `Files.readAllBytes`/`ByteArrayResource` cho file lớn | Dùng file-based Resource hoặc streaming |
| Có thể tải file ngoài thư mục cho phép | Dùng path do client đưa thẳng vào `FileSystemResource` | Dùng document ID, root containment và kiểm tra quyền |
| Header `Content-Length` không khớp | Đếm ký tự, không đếm byte; file bị đổi giữa lúc đo và đọc | Tính byte thật, snapshot file hoặc bỏ length khi không chắc |
| Client hỏi Range nhưng server trả toàn file | Endpoint/Resource/converter chưa hỗ trợ partial content | Kiểm thử range; dùng static resource handler/CDN khi phù hợp |
| File bị cache sai người dùng | Cache headers/scope sai | `no-store`/`private` và chính sách authorization/caching |
| Chỉ lỗi khi có file tên dấu tiếng Việt | Client cũ không hiểu `filename*` | Kiểm tra hỗ trợ RFC 5987 và chọn ASCII fallback khi cần |

## 12. Checklist thiết kế API download production

- [ ] Tài liệu được chọn bằng **ID logic**, không bởi filesystem path từ request.
- [ ] Server xác thực user/tenant và phân quyền theo từng document ID trước khi đọc.
- [ ] Root lưu trữ/loại Resource được quản lý bởi server, có bảo vệ chống traversal và symlink.
- [ ] Tên file do server chọn hoặc làm sạch; không chứa đường dẫn, CR/LF, ký tự điều khiển.
- [ ] `Content-Disposition` chọn `attachment`/`inline` theo chính sách, không theo input tự do; tên Unicode encoded đúng.
- [ ] `Content-Type` đúng theo định dạng đã kiểm tra; unknown file → `application/octet-stream`.
- [ ] `Content-Length` chỉ được gửi khi chính xác và không làm tiêu thụ stream dùng một lần.
- [ ] `X-Content-Type-Options: nosniff` và các security headers phù hợp.
- [ ] Cache policy phân biệt file công khai và file nhạy cảm; không leak qua shared cache.
- [ ] File lớn dùng Resource/stream phù hợp; có timeout, chống tải quá mức, theo dõi client disconnect.
- [ ] Có test 200 body bytes, MIME, attachment, UTF-8 filename, 404/403 và đường dẫn không hợp lệ.
- [ ] Range/HEAD/conditional request được kiểm thử nếu sản phẩm cam kết hỗ trợ.
- [ ] Log/audit ID, người truy cập, kích thước, loại file, kết quả và lỗi mà **không ghi bí mật hoặc path nhạy cảm**.
- [ ] Dữ liệu xuất CSV/XLSX có xử lý nguy cơ formula injection nếu chứa giá trị của người dùng.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao nên trả `ResponseEntity<Resource>` thay vì `byte[]` với file lớn?  
**Đáp:** Spring có thể đọc/copy nội dung từ Resource ra response mà không yêu cầu giữ toàn bộ file trong một mảng byte trên heap ứng dụng; hiệu quả thực tế còn tùy resource và HTTP stack.

**Câu 2.** `Content-Type` và `Content-Disposition` khác nhau như thế nào?  
**Đáp:** `Content-Type` diễn tả định dạng byte (PDF, CSV, text); `Content-Disposition` gợi ý trình duyệt hiển thị inline hay tải attachment và tên lưu file.

**Câu 3.** Một file classpath trong JAR có phải luôn gọi được `getFile()` không?  
**Đáp:** Không. Hãy dùng `ClassPathResource` qua stream/Resource converter khi có thể.

**Câu 4.** Vì sao `filename(name, UTF_8)` tốt hơn nối header thủ công?  
**Đáp:** Builder xử lý cú pháp encoding chuẩn cho tên Unicode và escape cần thiết; vẫn phải dùng tên đã được server kiểm soát.

**Câu 5.** Khi client cung cấp `/download?path=../../secret`, chỉ chuyển thành `FileSystemResource` có an toàn không?  
**Đáp:** Không. `Resource` không tự đặt ranh giới filesystem. Phải chọn file bằng ID, kiểm tra quyền và canonical containment/permission.

**Câu 6.** Có nên luôn trả `Content-Length` bằng `resource.contentLength()` không?  
**Đáp:** Không. Với nguồn stream dùng một lần, việc đo length có thể tiêu thụ stream; chỉ đặt length khi biết chính xác.

**Câu 7.** Trả `Content-Disposition: attachment` có đủ bảo vệ tài liệu bí mật không?  
**Đáp:** Không; vẫn phải authentication, authorization và cache policy đúng.

**Câu 8.** Đổi `Content-Type` của file HTML upload thành `application/pdf` có biến nó thành PDF an toàn không?  
**Đáp:** Không. MIME và tên file phải phản ánh loại nội dung đã được kiểm tra, không thay đổi cấu trúc byte thực.

**Câu 9.** Một endpoint download trả status 200 cho mọi `Range` đã hỗ trợ resume chuẩn chưa?  
**Đáp:** Chưa. Resume yêu cầu xử lý `206`/`Content-Range`/`416` và byte ranges chính xác; cần kiểm thử hoặc dùng thành phần đã hỗ trợ.

## 14. Tài liệu tham khảo

- Spring Framework, *ResponseEntity*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html
- Spring Framework, *Resources*: https://docs.spring.io/spring-framework/reference/core/resources.html
- Spring Framework, `ContentDisposition` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ContentDisposition.html
- Spring Framework, *Static Resources*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- Spring Boot, *Servlet Web Applications*: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring, *Uploading Files* (có ví dụ download `Resource`): https://spring.io/guides/gs/uploading-files/
- MDN, *Content-Disposition*: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Disposition
- RFC 6266, *Use of Content-Disposition in HTTP*: https://www.rfc-editor.org/rfc/rfc6266
- OWASP, *Unrestricted File Upload*: https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload

**Kết luận:** Với Spring MVC, `ResponseEntity<Resource>` là lựa chọn dễ bảo trì khi trả file có sẵn. Tạo `Content-Disposition` bằng builder của Spring, chọn `Content-Type` dựa trên metadata tin cậy, chỉ đặt `Content-Length` khi chính xác và bảo vệ download bằng ID + authorization + storage containment. Kiểm thử **cả response headers và byte nội dung**; không chỉ dựa vào việc trình duyệt hiển thị nút “Tải xuống”.