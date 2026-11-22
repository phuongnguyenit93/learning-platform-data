# Không tin cậy tên tệp, header hoặc thuộc tính do máy khách cung cấp

> **Chủ đề:** Dữ liệu yêu cầu trong Spring Boot **3.5.x**, Java **17+**, tập trung Spring MVC trên Servlet stack và các khác biệt quan trọng của WebFlux. Đây là tài liệu học cách **không trao quyền cho dữ liệu do client khai**, đặc biệt tên file multipart, HTTP headers và request attributes. Project Maven minh họa phía dưới có thể chạy, nhưng cố tình chưa triển khai authentication, authorization, malware scanning, quota và vận hành production.

## 1. Trust boundary: client được gửi dữ liệu, không được quyết định quyền

HTTP client có thể chọn phần lớn dữ liệu request: URL, query, form, JSON body, multipart headers, filename, cookie, HTTP headers và bytes của file upload. Frontend validation không bảo vệ server trước curl/Postman hoặc client tự viết.

~~~http
POST /api/files HTTP/1.1
Host: arbitrary.example
X-User-Role: admin
X-Tenant-Id: victim
X-Request-Id: fake-audit-id
Content-Type: multipart/form-data; boundary=example
~~~

Multipart metadata có thể khai:

~~~http
Content-Disposition: form-data; name="file"; filename="../../config/application.yml"
Content-Type: image/png
~~~

Không có gì ở đây chứng minh người gửi là admin, có quyền với tenant, file là PNG thật hoặc tên được phép ghi lên filesystem.

| Giá trị | Nguồn điển hình | Quy tắc |
|---|---|---|
| `MultipartFile.getOriginalFilename()` | Filename do client khai trong multipart | Không dùng thẳng làm path |
| `MultipartFile.getContentType()` | MIME do client khai | Không dùng làm bằng chứng nội dung |
| `X-User-Role`, `X-Tenant-Id` | Client/proxy | Không phải quyền/danh tính |
| `Host`, `X-Forwarded-Host` | Client/proxy chain | Chỉ tin trong trust boundary rõ ràng |
| `Origin`, `Referer` | Browser hoặc client tùy ý | Không dùng authentication |
| `@RequestAttribute("tenant")` | Server/filter/framework đặt vào request | Kiểm tra nguồn gốc của giá trị |
| UUID được server tạo | Ứng dụng | Tin nguồn/cú pháp, vẫn cần kiểm tra quyền tài nguyên |
| Principal Spring Security đã xác minh | Authenticated session/token | Dùng làm cơ sở authorization đúng scope |

Có sáu việc khác nhau: **provenance** (giá trị từ đâu), **syntax validation**, **content/business validation**, **authentication**, **authorization** và **output encoding**. Một tên tệp đúng regex không chứng minh user được tải lên; một UUID hợp lệ không chứng minh được quyền tải xuống.

## 2. Multipart filename là dữ liệu, không phải storage path

Trong Spring MVC:

~~~java
@PostMapping("/upload")
public void upload(@RequestParam("file") MultipartFile file) {
    String originalName = file.getOriginalFilename();
}
~~~

Đây chỉ là fragment để giải thích `MultipartFile`, không phải code lưu file an toàn. `getOriginalFilename()` có thể `null`, rỗng, chứa đường dẫn hoặc ký tự bất thường. Những chuỗi sau đều không được coi là tên file tin cậy:

~~~text
../../application.yml
..\..\secret.txt
/var/app/config.yml
C:\Windows\System32\drivers\etc\hosts
invoice.pdf.exe
CON
NUL.txt
evil%00.png
name<script>.txt
~~~

**Cách nguy hiểm:**

~~~java
// KHÔNG LÀM:
Path destination = Path.of("/app/uploads")
        .resolve(file.getOriginalFilename());

file.transferTo(destination);
~~~

Nếu path được ghép từ input, attacker có thể thử traversal, ghi đè file, dùng absolute path hoặc lợi dụng symlink. Loại bỏ literal `../` bằng `replace` không xử lý hết backslash, encoding, symlink, tên reserved, Unicode normalization và TOCTOU.

**Thiết kế khuyến nghị:**

1. Sinh file ID tại **server**, ví dụ UUID, rồi xây storage key từ ID và extension do server quyết định.
2. Đặt storage root cố định bằng cấu hình deployer, bên ngoài thư mục public/static/executable.
3. Giới hạn size, số file, quota và request body ở proxy, servlet multipart và application logic.
4. Kiểm tra **bytes/nội dung thực** bằng parser phù hợp. Extension và Content-Type do client khai chỉ là metadata.
5. Tạo mới bằng `CREATE_NEW`; không tùy tiện overwrite.
6. Bảo vệ directory permissions; kiểm tra symlink/race nếu attacker hoặc nhiều process có thể can thiệp directory.
7. Nếu cần hiển thị tên gốc, lưu như metadata đã giới hạn, và **escape khi render HTML/ghi log/header**.
8. File upload dùng cho người khác cần malware scan/quarantine/content disarm tùy rủi ro, phân quyền truy cập và chính sách retention.

### Vì sao normalize vẫn chưa đủ?

~~~java
// Fragment chỉ minh họa MỘT lớp kiểm tra:
Path root = Path.of("/srv/uploads").toAbsolutePath().normalize();
Path candidate = root.resolve(untrustedName).normalize();

if (!candidate.startsWith(root)) {
    throw new IllegalArgumentException("Traversal");
}
~~~

`startsWith(Path)` so theo path segments tốt hơn so tiền tố chuỗi, nhưng `normalize()` chỉ loại `.` và `..` trên cú pháp. Nó không ngăn symlink/race. Với upload mới, đừng cho filename client đi vào path ngay từ đầu.

### Filename, MIME và bytes khác nhau

| Thành phần | Ví dụ | Bản chất |
|---|---|---|
| Original filename | `image.png` | Client có thể tự đặt |
| Multipart Content-Type | `image/png` | Client có thể tự khai |
| File content | PNG signature, ảnh decode được, UTF-8 text | Phải kiểm tra đúng format |

`Files.probeContentType` hay extension check có thể hỗ trợ phân loại nhưng không đủ chứng minh file an toàn. Với ảnh, giới hạn pixels và decode/re-encode; với ZIP, chống Zip Slip/zip bomb; với PDF/Office, parser cập nhật và kiểm tra embedded content.

## 3. Header không phải nguồn xác thực

### 3.1. Role và tenant tự khai

~~~java
// Fragment không an toàn:
@GetMapping("/admin")
public String admin(@RequestHeader("X-User-Role") String role) {
    return "admin".equals(role) ? "secret" : "denied";
}
~~~

Ai cũng có thể gửi `X-User-Role: admin`. `X-User-Id`, `X-Tenant-Id`, `X-Is-Admin` cũng vậy. Hãy dùng Spring Security hoặc cơ chế authentication thực sự: xác minh signature/issuer/audience/expiration của token hoặc session phía server, sau đó kiểm tra quyền trên resource.

Nếu trusted API gateway chèn `X-Authenticated-User`, backend chỉ được tin khi đã bảo đảm: gateway **xóa header giả do client gửi**, xác thực trước khi ghi header mới, backend không có đường truy cập trực tiếp không tin cậy và kết nối/giao thức nội bộ được bảo vệ. Không thể chỉ thấy header có mặt rồi coi là authenticated identity.

### 3.2. Host và forwarded headers

~~~text
Host: example.com
Forwarded: for=203.0.113.10;proto=https;host=example.com
X-Forwarded-For: 203.0.113.10
X-Forwarded-Host: example.com
X-Forwarded-Proto: https
X-Forwarded-Prefix: /public
~~~

Các header này có thể bị spoof nếu edge proxy không strip hoặc overwrite input từ client, hoặc backend có direct network exposure. Không dùng trực tiếp để sinh password-reset link, OAuth redirect, IP-based ACL, billing identity hay security audit.

`server.forward-headers-strategy` trong Spring Boot giúp xử lý proxy URL metadata trong cấu hình phù hợp, **không tự xác thực forwarded headers**. Public base URL cho callback/email nhạy cảm nên lấy từ deployment config đáng tin, không ráp từ `request.getHeader("Host")` một cách tùy tiện.

### 3.3. Request ID, log và các header khác

`X-Request-Id` là metadata hỗ trợ trace, nhưng attacker cũng có thể tạo ID trùng, cực dài hoặc chứa ký tự không mong muốn. Giới hạn length/charset và structured-log; audit chống giả mạo cần **server-owned ID riêng**.

- `Origin` dành cho CORS; non-browser client có thể gửi giá trị giả. CORS không thay authentication.
- `Referer` có thể thiếu hoặc bị sửa; không dùng xác minh danh tính.
- `Cookie` chỉ đáng tin sau khi server xác minh session/token.
- `User-Agent` và `Accept-Language` có thể tùy ý.
- `Content-Type` là mô tả cách diễn giải body, không chứng nhận bytes.
- `Content-Length`/`Transfer-Encoding` phải do HTTP server/proxy xử lý chính xác; app vẫn cần request-size limits.
- Không log nguyên `Authorization`, `Cookie` hoặc tất cả headers.
- Tránh phản chiếu header tùy ý vào `Location`, `Set-Cookie` hoặc content-disposition dưới dạng chuỗi tự ghép.

## 4. Request attributes không giống request headers

Trong Spring MVC có ba cách lấy dữ liệu:

~~~java
// Fragment trong một controller method:
@RequestHeader("X-Tenant-Id") String tenantFromHeader
@RequestParam("tenant") String tenantFromQuery
@RequestAttribute("tenantContext") TenantContext context
~~~

`TenantContext` là một kiểu domain ví dụ, đoạn trên không phải Java method độc lập.

- `@RequestHeader` đọc header do HTTP client/proxy gửi.
- `@RequestParam` đọc query/form parameters do client kiểm soát.
- `@RequestAttribute` đọc một attribute đã được **server-side code** đặt trên `HttpServletRequest` trước đó.

**Nuance quan trọng:** client không thể gửi một raw HTTP header để trực tiếp gọi `HttpServletRequest#setAttribute()` trên server. Request attribute thường đến từ filter, interceptor, forward, servlet container hoặc Spring framework. Nhưng **nó vẫn có thể untrusted nếu writer đã copy dữ liệu từ client**.

Ví dụ sai:

~~~java
// Fragment trong filter - KHÔNG an toàn:
String claimed = request.getHeader("X-Tenant-Id");
request.setAttribute("verifiedTenant", claimed);

// Một controller đọc attribute:
String tenant = (String) request.getAttribute("verifiedTenant");
~~~

Tên `verifiedTenant` không làm input tự trở thành đã xác thực. Thiết kế đúng: xác minh principal; xác định tenant user được chọn; kiểm tra tenant membership/resource ownership bằng dữ liệu tin cậy; sau đó đặt typed tenant context do server quản lý. Authentication và authorization vẫn cần ở điểm thao tác tài nguyên.

Pseudocode có chủ ý (không độc lập biên dịch):

~~~java
VerifiedTenantContext context =
    membershipService.authorize(
        authenticatedPrincipal, requestedTenantId);

request.setAttribute("trusted.tenantContext", context);
~~~

`requestedTenantId` có thể do client yêu cầu nhưng **chỉ được sử dụng sau bước authorize**. Request attributes mà framework tạo (ví dụ về forward/path/error) cũng không tự trở thành cơ sở phân quyền.

## 5. Project Spring Boot 3.5: upload UTF-8 với storage key do server tạo

Dự án Maven minh họa chỉ chấp nhận text UTF-8 **tối đa 64 KiB**. Nhờ giới hạn nhỏ, có thể đọc bytes vào RAM để học cơ chế validation. Không áp dụng cách này cho upload lớn hoặc file phức tạp.

~~~text
safe-request-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/saferequest/
    SafeRequestApplication.java
    UploadStore.java
    UploadController.java
  src/test/java/com/example/saferequest/
    UploadSecurityIntegrationTest.java
~~~

### 5.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>safe-request-demo</artifactId>
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
~~~

### 5.2. application.properties

~~~properties
server.port=8080

# Limit tại multipart resolver:
spring.servlet.multipart.max-file-size=64KB
spring.servlet.multipart.max-request-size=128KB

# Root do deployer quyết định, không đến từ client:
app.storage.root=./target/demo-uploads
~~~

`./target/demo-uploads` chỉ dùng cho lab; `mvn clean` có thể xóa nội dung. Production đặt file trong một vùng dữ liệu riêng với quyền process tối thiểu, ngoài public/static/executable root.

### 5.3. Main class

`src/main/java/com/example/saferequest/SafeRequestApplication.java`:

~~~java
package com.example.saferequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeRequestApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeRequestApplication.class, args);
    }
}
~~~

### 5.4. UploadStore.java

`src/main/java/com/example/saferequest/UploadStore.java`:

~~~java
package com.example.saferequest;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.UUID;

import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@Service
public class UploadStore {

    private static final int MAX_BYTES = 64 * 1024;
    private final Path root;

    public UploadStore(Environment environment) {
        String configured = environment.getRequiredProperty(
                "app.storage.root");
        this.root = Path.of(configured).toAbsolutePath().normalize();
    }

    public UUID saveText(MultipartFile file) throws IOException {
        if (file.isEmpty() || file.getSize() > MAX_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid upload size");
        }

        // Chỉ đọc toàn file vì demo đã giới hạn 64 KiB.
        byte[] bytes = file.getBytes();

        if (bytes.length == 0 || bytes.length > MAX_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid upload size");
        }

        validateUtf8(bytes);
        Files.createDirectories(root);

        // Không dùng getOriginalFilename() hoặc getContentType()
        // để dựng storage path.
        UUID id = UUID.randomUUID();
        Path target = root.resolve(id.toString() + ".txt");

        Files.write(target, bytes,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE);
        return id;
    }

    private static void validateUtf8(byte[] bytes) {
        try {
            String text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes)).toString();

            if (text.indexOf('\0') >= 0) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "NUL is not allowed");
            }
        } catch (CharacterCodingException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Expected valid UTF-8 text", ex);
        }
    }
}
~~~

Các điểm an toàn được áp dụng:

1. `getOriginalFilename()` và `getContentType()` không có vai trò tạo storage key hoặc xác minh text.
2. `root` chỉ đến từ deployment config, `target` gồm server UUID và extension cố định.
3. `getSize()` và `bytes.length` đều được giới hạn; multipart limit áp dụng thêm ở framework/server.
4. UTF-8 decoder dùng `CodingErrorAction.REPORT`, loại bytes sai encoding; đây không phải malware scan.
5. `CREATE_NEW` không ghi đè tên đã tồn tại. Directory vẫn cần filesystem permissions, chống symlink/race nếu có untrusted local writers.
6. ID ngẫu nhiên không cho quyền đọc hoặc ghi. Khi có download cần kiểm tra principal/resource ownership.

### 5.5. UploadController.java

`src/main/java/com/example/saferequest/UploadController.java`:

~~~java
package com.example.saferequest;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/files")
public class UploadController {

    private static final Pattern SAFE_REQUEST_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private final UploadStore store;

    public UploadController(UploadStore store) {
        this.store = store;
    }

    @PostMapping(
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<UploadReceipt> upload(
            @RequestPart("file") MultipartFile file,
            @RequestHeader(
                name = "X-Request-Id", required = false
            ) String claimedRequestId) throws IOException {

        UUID fileId = store.saveText(file);
        String requestId = safeRequestId(claimedRequestId);

        return ResponseEntity.status(HttpStatus.CREATED)
                .header("X-Request-Id", requestId)
                .body(new UploadReceipt(
                        fileId.toString(), "stored"));
    }

    private static String safeRequestId(String value) {
        if (value != null &&
                SAFE_REQUEST_ID.matcher(value).matches()) {
            return value;
        }
        return UUID.randomUUID().toString();
    }

    public record UploadReceipt(String id, String status) {
    }
}
~~~

Header `X-Request-Id` chỉ được sử dụng làm **correlation metadata đã lọc format**, không cấp role, tenant hoặc authentication. Client vẫn có thể tạo một request ID đúng regex; audit trail đáng tin phải sinh một server-owned ID riêng. Controller không dựa vào client headers để tạo path hoặc ID file.

**Quan trọng:** Demo cố tình chưa cấu hình Spring Security, nên upload endpoint không bị chặn theo người dùng. Không triển khai public production nếu chưa bổ sung authentication/authorization, quota, rate limiting, policy theo tenant và scan nội dung phù hợp.

## 6. Chạy và kiểm tra bằng curl

Ở thư mục có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Tạo file text trong Bash:

~~~bash
printf 'hello\n' > note.txt
~~~

Upload bình thường:

~~~bash
curl -i "http://localhost:8080/api/files" \
  -H "X-Request-Id: trace_42" \
  -F "file=@note.txt;type=text/plain"
~~~

Kỳ vọng HTTP `201 Created`, header `X-Request-Id: trace_42`, body dạng:

~~~json
{"id":"550e8400-e29b-41d4-a716-446655440000","status":"stored"}
~~~

UUID trên **chỉ minh họa cấu trúc**, mỗi request thực sẽ nhận ID khác. File được lưu dưới `target/demo-uploads/<id-thuc>.txt`, không dùng original filename.

Giả mạo filename/MIME:

~~~bash
curl -i "http://localhost:8080/api/files" \
  -F 'file=@note.txt;filename=../../outside.png;type=image/png'
~~~

Nội dung bytes vẫn là text UTF-8 nên được chấp nhận, nhưng server lưu dưới tên UUID + `.txt`. Filename `../../outside.png` không được sử dụng làm đường dẫn; MIME khai từ client không phải bằng chứng định dạng.

Giả mạo role:

~~~bash
curl -i "http://localhost:8080/api/files" \
  -H "X-User-Role: admin" \
  -H "X-Tenant-Id: victim" \
  -F "file=@note.txt"
~~~

Có thể vẫn trả 201 vì **demo không có authentication**; điều này không có nghĩa client có quyền admin. Các header trên không hề tham gia quyết định lưu file. Production phải áp dụng authentication/authorization thực tế.

File rỗng:

~~~bash
: > empty.txt
curl -i "http://localhost:8080/api/files" \
  -F "file=@empty.txt"
~~~

Service trả 400. Multipart vượt limit có thể bị từ chối trước controller; status/body lỗi chi tiết phụ thuộc exception handler/server, cần kiểm thử trên hạ tầng thật.

## 7. Test tự động với MockMvc

Tạo `src/test/java/com/example/saferequest/UploadSecurityIntegrationTest.java`:

~~~java
package com.example.saferequest;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(
    properties = "app.storage.root=./target/demo-uploads-test"
)
class UploadSecurityIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper mapper;

    @Test
    void ignoresUntrustedFilenameAndMime() throws Exception {
        byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);
        MockMultipartFile file = new MockMultipartFile(
                "file", "../../outside.png", "image/png", bytes);

        MvcResult result = mockMvc.perform(
                multipart("/api/files").file(file)
                    .header("X-User-Role", "admin")
                    .header("X-Request-Id", "bad request id"))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(header().exists("X-Request-Id"))
            .andReturn();

        JsonNode json = mapper.readTree(
                result.getResponse().getContentAsString());
        String id = json.path("id").asText();

        assertDoesNotThrow(() -> UUID.fromString(id));
        assertEquals("stored", json.path("status").asText());

        String returnedRequestId =
                result.getResponse().getHeader("X-Request-Id");
        assertNotEquals("bad request id", returnedRequestId);
        assertDoesNotThrow(
                () -> UUID.fromString(returnedRequestId));

        Path saved = Path.of("target/demo-uploads-test")
                .resolve(id + ".txt");

        assertTrue(Files.isRegularFile(saved));
        assertArrayEquals(bytes, Files.readAllBytes(saved));
    }

    @Test
    void rejectsEmptyFile() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "empty.txt", "text/plain", new byte[0]);

        mockMvc.perform(multipart("/api/files").file(file))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidUtf8() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "fake.png", "text/plain",
                new byte[]{(byte) 0xC3, (byte) 0x28});

        mockMvc.perform(multipart("/api/files").file(file))
                .andExpect(status().isBadRequest());
    }

    @Test
    void preservesOnlySafeCorrelationHeader() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "x.txt", "text/plain",
                "ok".getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/api/files").file(file)
                    .header("X-Request-Id", "trace_42"))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                    "X-Request-Id", "trace_42"));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Test xác nhận filename traversal không tạo storage path, MIME tự khai không được coi là định dạng, role header tự khai không được dùng cấp quyền, request ID sai regex bị thay, file rỗng/UTF-8 sai bị từ chối. `MockMvc` mô phỏng tầng Spring MVC trong Spring context, **không kiểm tra socket HTTP thật, proxy/WAF, Servlet multipart parser thực và HTTP framing**. Cần bổ sung integration test qua web server/ingress khi triển khai production.

## 8. Upload loại file phức tạp cần thêm các lớp kiểm tra

**Ảnh:** chỉ chấp nhận những định dạng cần dùng, kiểm tra signature và decode thật bằng library cập nhật, giới hạn chiều rộng/chiều cao/pixels và cân nhắc re-encode để loại metadata nguy hiểm.

**PDF/Office:** cập nhật parser, xem xét macro/scripts/embedded links, scan virus hoặc content disarm nếu có dữ liệu không tin cậy được chia sẻ, giới hạn CPU/memory/time.

**ZIP/TAR:** file có thể chứa entries như `../../config.yml` dù tên archive ngoài đã đổi thành UUID. Kiểm tra từng entry path chống Zip Slip, symlink, số lượng entries, tổng uncompressed bytes và depth chống zip bomb.

**Object storage:** sinh object key phía server theo namespace tenant đã xác thực và ID mới, dùng bucket policy/presigned URL có scope + expiry, kiểm tra resource ownership trước khi read/download.

**Download:** UUID hợp lệ không phải authorization. Trước khi trả file, kiểm tra principal/tenant/resource. Dùng Content-Type do server xác định, Content-Disposition phù hợp, `X-Content-Type-Options: nosniff` và cache policy nếu cần. Không tự ghép original filename vào response headers.

Ví dụ fragment tạo Content-Disposition với tên do server kiểm soát:

~~~java
String value = org.springframework.http.ContentDisposition.attachment()
        .filename("download.txt", StandardCharsets.UTF_8)
        .build().toString();

responseHeaders.set(
        org.springframework.http.HttpHeaders.CONTENT_DISPOSITION,
        value);
~~~

`responseHeaders` ở đây giả định là `HttpHeaders` được tạo trong scope phù hợp; fragment không phải file Java độc lập.

## 9. WebFlux cũng cần phân tích provenance

Trong WebFlux, các khái niệm tương đương:

| Servlet MVC | Reactive WebFlux |
|---|---|
| `MultipartFile.getOriginalFilename()` | `FilePart.filename()` |
| `HttpServletRequest.getHeader()` | `ServerWebExchange.getRequest().getHeaders()` |
| `HttpServletRequest.getAttribute()` | `ServerWebExchange.getAttributes()` |
| Servlet `Filter` | Reactive `WebFilter` |
| Spring Security `SecurityFilterChain` | `SecurityWebFilterChain` |

`FilePart.filename()` vẫn là dữ liệu do client khai. `ServerWebExchange.getAttributes()` thường do framework/filter ghi nhưng **có thể chứa giá trị lấy từ header**; một `WebFilter` không được gắn `X-Tenant-Id` thành verified context khi chưa xác thực.

Fragment WebFlux (không phải class độc lập):

~~~java
@Override
public Mono<Void> filter(
        ServerWebExchange exchange, WebFilterChain chain) {

    String clientTenant = exchange.getRequest()
            .getHeaders()
            .getFirst("X-Tenant-Id");

    // clientTenant chưa xác thực => không dùng cấp quyền.
    return chain.filter(exchange);
}
~~~

WebFlux non-blocking I/O **không tự ngăn** path traversal, MIME spoofing hoặc auth bypass. Với file lớn, phải dùng streaming/bounded processing, tránh `block()` hoặc filesystem blocking calls trên event loop.

## 10. Những lối tắt bảo mật sai

| Lối tắt | Vì sao sai | Thay bằng |
|---|---|---|
| `filename.replace("../", "")` | Bỏ sót path representations/symlinks | UUID server + root tin cậy |
| `originalName.endsWith(".png")` | Tên file không chứng minh bytes | Format allowlist + parser |
| `getContentType()=="image/png"` | MIME do client khai | Kiểm tra nội dung thực |
| `X-User-Role=="admin"` | Không có xác thực | Spring Security principal |
| `X-Tenant-Id` đúng regex | Không chứng minh membership | Tenant/resource authorization |
| `request.setAttribute("trusted", header)` | Chỉ đổi chỗ lưu, không đổi trust | Verify provenance trước |
| Dùng `Origin` làm identity | CORS khác authentication | Token/session validation |
| Tin mọi `X-Forwarded-For` | Client có thể spoof | Trusted proxy chain |
| Ráp reset link từ `Host` | Host header poisoning | Configured public base URL |
| Tin UUID file là secret | ID đoán/biết được vẫn cần auth | Resource-level permission checks |
| Đọc mọi upload vào byte[] | DoS memory với file lớn | Multipart limits + streaming |
| Lưu file vào static root | Có thể lộ hoặc xử lý nguy hiểm | Private upload storage |

## 11. Checklist trước production

- [ ] Server không dùng original filename làm path, extension lưu do server quyết định.
- [ ] Dung lượng, số lượng và loại file được giới hạn ở proxy/server/application.
- [ ] Nội dung được decoder/parser kiểm tra; file phức tạp có scanning/quarantine khi cần.
- [ ] Storage có quyền tối thiểu, không public ngoài chủ đích, không thể sửa file cấu hình/certificate.
- [ ] Không có path traversal, ZIP Slip, symlink/race hoặc overwrite trái phép.
- [ ] Upload/download đều xác thực và phân quyền theo tenant/resource ownership.
- [ ] `X-User-Role`, `X-User-Id`, `X-Tenant-Id` từ client không trở thành quyền.
- [ ] Trusted proxy strip/overwrite forwarded/identity headers và backend không lộ direct route.
- [ ] Host header không điều khiển reset/redirect link; callback URL có allowlist.
- [ ] Request ID bị giới hạn format/size và audit có server-owned ID riêng.
- [ ] Không log secrets hoặc original filename không kiểm soát; HTML/header output được encode đúng.
- [ ] Request attributes mang ý nghĩa identity có writer và data-flow đã được audit.
- [ ] Có test giả mạo header, tenant, filename, MIME, file size, encoding, malformed multipart.
- [ ] Có integration tests trên HTTP server/gateway thật, không chỉ MockMvc.
- [ ] Có quota, rate limiting, cleanup và monitoring cho upload abuse.

## Tài liệu tham khảo

- [Spring Framework — Multipart Forms](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html) — `MultipartFile` và multipart binding.
- [Spring Framework — Request Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestheader.html) — `@RequestHeader`.
- [Spring Framework — Request Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestattribute.html) — `@RequestAttribute`.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html) — Servlet stack, multipart.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/) — multipart limits và proxy-related config.
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) — defense in depth.
- [OWASP — Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal) — traversal.
- [PortSwigger Web Security Academy — HTTP Host Header Attacks](https://portswigger.net/web-security/host-header) — Host header poisoning.

**Kết luận:** Client cung cấp filename và headers dưới dạng lời khai, **không được dùng chúng làm storage path, role hoặc tenant đã xác thực**. Request attribute thường do server tạo nhưng giá trị chỉ đáng tin khi nguồn và bước xác minh thực sự đáng tin. Sinh ID ở server, kiểm tra nội dung + quota, thiết lập trust boundary proxy và áp dụng authentication/authorization độc lập là nền tảng bảo vệ Spring Boot web applications.
