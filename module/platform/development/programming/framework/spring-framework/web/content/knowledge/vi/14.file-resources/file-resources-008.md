# Ngăn path traversal và kiểm soát quyền truy cập tệp trong Spring MVC

> **Phạm vi:** Spring Web MVC (Servlet stack), Java 17+ và Spring Boot 3.x/Spring Framework 6.x. Bài học tập trung vào cách API **upload, download, xem, sửa và xóa tệp** tránh truy cập ngoài vùng lưu trữ, không để người dùng đọc file của người khác, và bảo vệ hệ thống trước đường dẫn độc hại, symbolic links, race conditions, file quá lớn hoặc nội dung nguy hiểm. Cơ chế bảo vệ quan trọng nhất là **không cho client quyết định đường dẫn vật lý** và **kiểm tra quyền ở server cho từng thao tác trên từng tài nguyên**.

## 1. Vấn đề: một tên tệp có thể dẫn tới dữ liệu ngoài ý muốn

Giả sử ứng dụng có endpoint:

```http
GET /api/download?name=invoice.pdf
```

Code thiếu an toàn:

```java
// ANTI-PATTERN — không sử dụng trong ứng dụng thật.
@GetMapping("/download")
public byte[] download(@RequestParam String name) throws IOException {
    return Files.readAllBytes(
            Path.of("/srv/app/uploads/" + name));
}
```

Client có thể thay `name` bằng đoạn đường dẫn đi ngược lên thư mục cha. Nếu ứng dụng nối trực tiếp input vào đường dẫn, một file nhạy cảm ngoài thư mục upload có thể bị đọc (nếu process có quyền filesystem), ví dụ:

```text
/srv/app/uploads/../../private/config.yml
```

Đây là **path traversal / directory traversal**, một loại truy cập filesystem trái phép do đường dẫn do client kiểm soát. Các hệ điều hành, web server và URL decoder có thể biểu diễn đường dẫn theo nhiều cách, vì vậy chỉ kiểm tra xem chuỗi có chứa `../` hay không **không đủ**.

Bên cạnh traversal còn có **IDOR/BOLA (Broken Object Level Authorization)**: client chỉ cần thay ID tệp bằng ID hợp lệ của người khác. Đường dẫn vật lý có thể vẫn nằm hoàn toàn trong thư mục cho phép, nhưng truy cập vẫn trái quyền.

**Hai hàng rào độc lập:**

1. **Filesystem isolation:** tệp được mở phải thuộc vùng lưu trữ, với cách xử lý symlink và quyền OS phù hợp.
2. **Object-level authorization:** người dùng hiện tại phải được phép **đọc/tạo/cập nhật/xóa đúng tệp đó**, bất kể họ có đoán được ID hay không.

Không đạt một trong hai thì endpoint vẫn có thể không an toàn.

## 2. Những nguồn input không đáng tin

Đường dẫn có thể được đưa vào ứng dụng từ nhiều vị trí:

- `@PathVariable("filename")` và `@RequestParam("path")`.
- Header `Content-Disposition` của multipart upload, qua `MultipartFile.getOriginalFilename()`.
- JSON `{"path":"..." }` hoặc các form fields có tên file/thư mục.
- Metadata lưu trong database nếu trước đó được ghi từ client mà không kiểm soát.
- URL lấy từ callback, archive entry name khi giải nén ZIP/TAR hoặc URI chỉ tới remote file.

Dữ liệu đã được lưu trong DB **không tự động trở thành tin cậy**. Nếu user từng có thể sửa `storedPath`, việc lấy `storedPath` từ repository và truyền vào `Files.readAllBytes` vẫn có thể gây traversal.

**Đừng nhầm:**
- Client filename (tên hiển thị): giá trị để trình bày, phải hạn chế/escape.
- Server storage key (tên file nội bộ): **do server tạo**, không lấy từ tên client.
- Opaque file ID (ID API): client dùng tham chiếu tài nguyên; server ánh xạ ID sang metadata.
- Owner/tenant/ACL: dữ liệu quyền từ identity và hệ thống quản lý tài nguyên, **không** tin trường `ownerId` do client tự gửi.

## 3. Các biến thể của path traversal

| Biến thể | Rủi ro | Cách suy nghĩ |
| --- | --- | --- |
| `../` trên hệ Unix | Đi lên thư mục cha | Không cho path client đến filesystem trực tiếp |
| `..\\` trên Windows | Dùng ký tự phân tách Windows | Không chỉ tìm dấu `/` |
| `/etc/...` hoặc `C:\\...` | Đường dẫn tuyệt đối / ổ đĩa | Không cho input tự xác định root |
| UNC paths như `\\\\server\\share` | Truy cập mạng qua đường dẫn Windows | Phân biệt root/UNC trên nền tảng |
| `%2e%2e%2f`, `%252e%252e%252f` | URL encoding / nhiều lớp decode | Thống nhất một cơ chế decode, không tự decode lặp |
| `foo/../secret` | `..` ở giữa | Dùng `Path.normalize()` nhưng chưa đủ cho symlink |
| Symlink `uploads/link -> /etc` | Đi ra ngoài dù path dạng text ở trong root | Kiểm tra real path/NOFOLLOW, root private |
| Hard link hoặc bind mount | Dữ liệu filesystem được tham chiếu nhiều cách | Dùng OS isolation, kiểm soát ai có quyền thay nội dung |
| ZIP entry `../../x` | Zip Slip khi giải nén | Kiểm tra mỗi archive entry trước khi tạo file |
| Tên file `..`, dấu phân tách, NUL, tên đặc biệt | Parser/OS/ngữ cảnh hiển thị khác nhau | Sinh storage key độc lập từ server |

Các ví dụ là **dữ liệu kiểm thử/chẩn đoán**, không có nghĩa mọi framework/container sẽ cho chuỗi ấy đến handler. Một số tầng có thể trả 400/404 trước; điều đó **không thay thế** việc endpoint và storage service được thiết kế an toàn.

### 3.1. Vì sao so chuỗi prefix không an toàn?

Ví dụ:

```java
// SAI: so sánh chuỗi text, không hiểu ranh giới path component.
if (target.toString().startsWith("/srv/files")) {
    // Có thể chấp nhận /srv/files-evil/...
}
```

`Path.startsWith(Path)` có ngữ nghĩa theo thành phần đường dẫn, nên tốt hơn `String.startsWith`:

```java
Path root = Path.of("/srv/files").toAbsolutePath().normalize();
Path target = root.resolve(relativeName).normalize();

if (!target.startsWith(root)) {
    throw new SecurityException("Outside storage root");
}
```

Nhưng đoạn trên chỉ kiểm tra **đường dẫn từ góc nhìn lexical**. Nếu `/srv/files/link` là symbolic link tới thư mục ngoài root thì `target.startsWith(root)` vẫn có thể trả true dù file thực tế ở nơi khác. Xem mục 5 về `toRealPath` và TOCTOU.

### 3.2. Không dùng regex cấm vài chuỗi làm bảo vệ chính

```java
// SAI: không phải allowlist/hard isolation.
if (input.contains("../")) {
    throw new IllegalArgumentException("Bad path");
}
```

Trên Windows còn có `..\\`; dữ liệu có thể đã hoặc chưa URL-decode; path có segment đặc biệt; symbolic link không xuất hiện trong input. Ưu tiên **ID -> metadata -> server-generated key**, hơn là cố biến một client path bất kỳ thành “safe filename” bằng cách thay `../` thành chuỗi rỗng.

## 4. Thiết kế đề xuất: dùng ID thay vì tên file vật lý

Thay API:

```http
GET /api/files?path=../../private/secret.txt
```

bằng:

```http
GET /api/files/11111111-1111-4111-8111-111111111111
```

Server có metadata:

```text
fileId                 -> 11111111-1111-4111-8111-111111111111
owner                  -> alice
storageKey             -> 86a6c5d8-...-generated.bin
displayFilename        -> invoice.txt
mediaType              -> text/plain
size                   -> 1234
status                 -> AVAILABLE
tenantId               -> tenant-a
```

Lưu ý:
- `fileId` là **tham chiếu tài nguyên**; người dùng vẫn có thể gửi một fileId khác, nên **bắt buộc authorization**.
- `storageKey` do server tạo với UUID/nguồn ngẫu nhiên đủ mạnh hoặc khóa hệ thống nội bộ, **không** xây từ `getOriginalFilename()`.
- `displayFilename` là metadata để hiển thị; không có quyền quyết định nơi lưu.
- File nằm ngoài `resources/static`, `public` hoặc thư mục servlet webroot; không để Spring tự phục vụ tài nguyên private thông qua static handler.
- Các thao tác upload/download/delete đều phải tra metadata và kiểm tra `user/tenant/action/resource`.

Sơ đồ:

```text
GET /api/files/{opaqueId}
     |
Spring Security xác thực principal
     |
FileService.findById(opaqueId)
     |
Authorization: principal có thể READ file này?
     |
Metadata: server generated storage key
     |
Storage root private + kiểm tra đường dẫn/file type
     |
Open file -> stream qua ResponseEntity<Resource>
```

**Không dùng UUID khó đoán làm bằng chứng quyền.** UUID giảm khả năng đoán hàng loạt nhưng không thay thế authorization. Một link bị lộ, log sai hoặc client tự thay ID vẫn phải bị kiểm tra quyền.

## 5. Kiểm soát Path trong Java NIO

### 5.1. `normalize()` là phép toán lexical

```java
Path root = Path.of("/srv/app/private-files")
        .toAbsolutePath()
        .normalize();

Path p = root.resolve("drafts/../file.txt").normalize();
// p có hình thức /srv/app/private-files/file.txt
```

`Path.normalize()` loại bỏ các segment `.` và `..` có thể rút gọn về mặt cú pháp; nó **không đọc filesystem** và **không biết symlink trỏ tới đâu**. Nó cũng không xác thực quyền truy cập hoặc chứng minh file tồn tại.

### 5.2. `toRealPath()` kiểm tra filesystem thực

```java
Path configuredRoot = Path.of("/srv/app/private-files");
Path rootReal = configuredRoot.toRealPath(); // Root phải tồn tại.
Path realFile = rootReal.resolve(serverGeneratedName).toRealPath();

if (!realFile.startsWith(rootReal)) {
    throw new SecurityException("Outside permitted root");
}
```

Đây là snippet minh họa. `toRealPath()` (không truyền `NOFOLLOW_LINKS`) giải quyết symlinks và yêu cầu file tồn tại. Nếu một symlink trỏ ra ngoài, real path có thể không còn nằm dưới root, nên phép `startsWith` phát hiện được **tại thời điểm kiểm tra**.

Nhưng đoạn này vẫn có nguy cơ **TOCTOU** nếu một tiến trình khác có thể thay symlink hoặc đường dẫn sau lúc kiểm tra, trước lúc file được mở. Do đó không coi `toRealPath() + startsWith() + open()` là cơ chế chống race condition tuyệt đối.

### 5.3. `NOFOLLOW_LINKS` và giới hạn của nó

Khi không muốn mở symlink ở **thành phần cuối cùng**:

```java
try (InputStream input = Files.newInputStream(
        candidate,
        StandardOpenOption.READ,
        LinkOption.NOFOLLOW_LINKS)) {
    // Đọc/stream trong phạm vi chính sách áp dụng.
}
```

`LinkOption.NOFOLLOW_LINKS` yêu cầu Java không follow symbolic link theo thao tác hỗ trợ. Tuy nhiên nếu `candidate` có **thư mục cha** do đối thủ kiểm soát, các thành phần trung gian vẫn cần bảo vệ. Vì vậy nên kết hợp:

1. Root lưu trữ chỉ do service user quản lý; bên không tin cậy không có quyền tạo/chỉnh symlink/hard link trong đó.
2. Server tự sinh **một filename duy nhất**, tránh nested path tùy ý.
3. Không cho client truy cập path trực tiếp.
4. Với môi trường đối kháng mạnh, dùng `SecureDirectoryStream`/open-relative-to-directory-handle khi file system provider hỗ trợ, hoặc dùng object storage API đã có ranh giới quyền phù hợp.
5. Hạn chế quyền OS và container mount của tiến trình ứng dụng.

`NOFOLLOW_LINKS` là một biện pháp chuyên biệt, **không** thay cho kiểm tra ACL/owner hay phân quyền ở ứng dụng.

### 5.4. Tạo tệp không ghi đè file hiện có

Đối với upload, tránh:

```java
// Không nên: client tên file có thể trùng và ghi đè.
Files.copy(upload.getInputStream(), root.resolve(upload.getOriginalFilename()));
```

Nên tạo key server-side và dùng thao tác **atomic create**:

```java
String storageName = UUID.randomUUID() + ".bin";
Path destination = root.resolve(storageName);

try (InputStream in = upload.getInputStream();
     OutputStream out = Files.newOutputStream(
             destination,
             StandardOpenOption.CREATE_NEW,
             StandardOpenOption.WRITE)) {
    in.transferTo(out);
}
```

Đây là **fragment upload**; root phải là directory bảo vệ, file đã được kiểm tra quyền/giới hạn trước đó, và cần lưu metadata vào database cùng chính sách cleanup nếu lỗi. `CREATE_NEW` đảm bảo thao tác tạo mới thất bại nếu đích đã tồn tại (kể cả symbolic link) và kiểm tra tồn tại + tạo mới là atomic với các thao tác filesystem tương ứng. Đừng tự viết `if (!Files.exists(path)) Files.write(...)` rồi tưởng không có race. Với filesystem có ACL cần yêu cầu initial permissions/private create phù hợp.

## 6. Giới hạn tên file client: sử dụng để hiển thị, không làm storage key

`MultipartFile.getOriginalFilename()` là **input do client cung cấp**. Javadoc Spring cảnh báo giá trị này có thể chứa path information, `..` hoặc ký tự nguy hiểm; không được dùng trực tiếp làm đường dẫn lưu.

Sai:

```java
@PostMapping("/upload")
void upload(@RequestParam MultipartFile file) throws IOException {
    file.transferTo(Path.of("/data/files/", file.getOriginalFilename()));
}
```

Đây là **anti-pattern**: lỗi biên dịch/overload tùy cách dùng `Path.of(...)`, nhưng vấn đề chính là tin client filename và nguy cơ traversal/overwrite. **Đừng sử dụng** mẫu trên; file API thực tế nên có `@RequestParam("file")`, giới hạn kích thước và lưu theo tên server sinh.

Quy tắc tốt:
- Đọc original filename chỉ để hiển thị, audit hoặc gắn response `Content-Disposition` sau khi lọc/chuẩn hóa.
- Giới hạn độ dài và ký tự cho phép của tên hiển thị; loại bỏ control characters, dấu phân tách đường dẫn và chuỗi mang ý nghĩa đặc biệt.
- Với file download, dùng `ContentDisposition.attachment().filename(safeName, StandardCharsets.UTF_8)` để tạo header có escaping/encoding phù hợp, rồi test trên client/browsers mục tiêu.
- Dù display name là `../secret.txt` cũng **không bao giờ** được dùng để xây đường dẫn đọc/ghi thực tế.

**Không tự lấy `Paths.get(original).getFileName()` làm bảo đảm tuyệt đối:** trên Linux, dấu `\\` không là path separator như Windows, ký tự đặc biệt vẫn có thể gây header/UX issues; còn attacker vẫn có thể gây collision. Cách đơn giản là lưu display name qua allowlist và cấp storage name hoàn toàn độc lập.

## 7. Authorization: ngăn IDOR/BOLA trên mỗi file

### 7.1. Authentication khác authorization

- **Authentication:** xác nhận identity, ví dụ principal `alice`.
- **Authorization:** xác nhận `alice` được phép **READ/WRITE/DELETE file X** thuộc tenant tương ứng.

Một API đã gắn `.authenticated()` vẫn có thể cho mọi user đọc file của nhau nếu thiếu kiểm tra trên record:

```java
// ANTI-PATTERN: chỉ biết user đã đăng nhập, không kiểm tra owner.
@GetMapping("/api/files/{id}")
public Resource download(@PathVariable String id) {
    FileRecord file = repository.findById(id);
    return new FileSystemResource(storageRoot.resolve(file.storageKey()));
}
```

Code này có thể có path an toàn nhưng vẫn bị IDOR. Đúng hơn:

```java
FileRecord file = repository.findById(id)
        .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND));

authorizationService.requireCanRead(currentUser, file);

Path filePath = storageService.resolveServerKey(file.storageKey());
Resource body = storageService.open(filePath);
```

Đây là snippet nghiệp vụ; trong demo chạy được ở mục 9, chính sách tối thiểu là so `authenticated principal name` với `owner` trong metadata. Production còn có team sharing, tenant scoping, ACL, account suspension, retention và audit.

### 7.2. 403 hay 404?

Với tài nguyên thuộc người khác:
- **403 Forbidden:** người dùng đã xác thực nhưng không được phép; rõ ràng để debug và quản trị.
- **404 Not Found:** API cố tình không tiết lộ tài nguyên có tồn tại, thường được dùng để giảm enumeration.

Hai lựa chọn có thể hợp lý nếu được thiết kế nhất quán. Không trả 200 kèm thông điệp lỗi. Demo ở mục 9 dùng **403** để học cách quan sát authorization; app có yêu cầu bảo mật tồn tại tài nguyên có thể dùng **404** sau khi áp chính sách kiểm tra.

### 7.3. Tránh lấy chủ sở hữu từ request

```json
{
  "fileId": "11111111-1111-4111-8111-111111111111",
  "owner": "alice"
}
```

Client gửi body như trên **không khiến client trở thành alice**. Chủ sở hữu và tenant phải lấy từ identity đã xác thực cùng metadata server, không lấy từ header `X-User` tự đặt hay giá trị `ownerId` trong form.

### 7.4. Spring Security: hai lớp kiểm soát

- **Lớp HTTP:** `SecurityFilterChain` bắt buộc đăng nhập cho `/api/files/**` và áp quy tắc method/path tổng quát.
- **Lớp domain:** service kiểm tra đúng file record (owner, tenant, sharing ACL, action), không dựa duy nhất vào URL pattern.
- **Lớp OS/storage:** quyền file/dir, container isolation và storage credentials giới hạn blast radius nếu ứng dụng bị lỗi.

Khi chạy nhiều instance hoặc object storage, metadata/ACL check và mở object phải nhất quán với permission design; nếu cần revoke ngay, tránh cache quyền quá lâu và tránh phát link public không thể thu hồi.

## 8. Những thao tác file cần kiểm soát riêng

| Thao tác | Rủi ro | Điều phải kiểm tra |
| --- | --- | --- |
| GET/download | Traversal, IDOR, lộ secrets | AuthN/AuthZ, server storage key, canonical containment và loại file |
| POST/upload | Truy cập ngoài root, overwrite, malware, DoS | AuthN/AuthZ, server key, CREATE_NEW, size/type/quota/scanning |
| PUT/replace | Ghi đè sai file/owner, lost update | Quyền WRITE, ID ownership, version/concurrency |
| DELETE | Xóa file của người khác, link tricks | Quyền DELETE, metadata state, safe deletion và audit |
| List/search | Lộ file names/IDs/tài khoản | Tenant/owner scope ngay trong query, pagination |
| Preview/thumbnail | Parser exploit, XXE/image bombs | Sandbox/isolation, format validation, resource limits |
| ZIP/TAR extract | Zip Slip, symlinks trong archive, zip bomb | Per-entry containment, symlink policy, total expanded quota |

**Không lưu upload vào** `src/main/resources/static`, `src/main/webapp` hoặc thư mục được servlet container tự phục vụ nếu file private. Một `@GetMapping` có authorization sẽ vô nghĩa nếu người dùng cũng có thể tải cùng file qua một public static URL.

## 9. Ví dụ hoàn chỉnh chạy được: file download theo ID, kiểm tra quyền

Ví dụ dưới đây dùng **Spring Boot 3.x, Java 17+, Spring Web và Spring Security**. Vì muốn minh họa authorization thực sự, ví dụ cấu hình **hai tài khoản demo** qua HTTP Basic: `alice` và `bob`. Mỗi người chỉ tải được file của mình. Một private temp directory được server tạo khi ứng dụng khởi động, metadata được định nghĩa phía server.

**Giới hạn cố ý:** đây là demo **chỉ GET/download**, không có upload, database, email, external storage hoặc authorization phức tạp. `{noop}` passwords chỉ dành cho local learning, không dùng production. CSRF không bị tắt; vì demo chỉ cung cấp GET, không cần thực hiện state-changing HTTP requests. File demo nhỏ và tên file server kiểm soát hoàn toàn.

### 9.1. Chuẩn bị Maven project

Tạo Spring Boot 3.x Maven project tại [Spring Initializr](https://start.spring.io/), Java 17+, dependencies **Spring Web** và **Spring Security**:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
</dependencies>
```

Đây là **fragment `<dependencies>`** trong POM do Spring Initializr cung cấp, không phải toàn bộ POM. Đặt Java source dưới đây vào duy nhất file `src/main/java/com/example/demo/DemoApplication.java`.

### 9.2. Mã Java đầy đủ

```java
package com.example.demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Map;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.InputStreamResource;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        // CHỈ DEMO: {noop} và mật khẩu tĩnh không dùng production.
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}alice-password")
                        .roles("USER")
                        .build(),
                User.withUsername("bob")
                        .password("{noop}bob-password")
                        .roles("USER")
                        .build());
    }
}

record FileRecord(
        String id,
        String owner,
        String storageKey,
        String displayName,
        long size) {
}

@Service
class PrivateFileStore {

    static final String ALICE_ID =
            "11111111-1111-4111-8111-111111111111";

    static final String BOB_ID =
            "22222222-2222-4222-8222-222222222222";

    private final Path root;
    private final Map<String, FileRecord> records;

    PrivateFileStore() throws IOException {
        // Thư mục do server tạo, không có client path trong tên.
        root = Files.createTempDirectory("private-file-demo-")
                .toRealPath();

        Path aliceFile = root.resolve("alice-note.txt");
        Path bobFile = root.resolve("bob-note.txt");

        Files.writeString(
                aliceFile, "Hello Alice\n",
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE);

        Files.writeString(
                bobFile, "Hello Bob\n",
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE);

        records = Map.of(
                ALICE_ID,
                new FileRecord(
                        ALICE_ID, "alice", "alice-note.txt",
                        "alice.txt", Files.size(aliceFile)),
                BOB_ID,
                new FileRecord(
                        BOB_ID, "bob", "bob-note.txt",
                        "bob.txt", Files.size(bobFile)));
    }

    Optional<FileRecord> find(String id) {
        return Optional.ofNullable(records.get(id));
    }

    InputStream open(FileRecord record) throws IOException {
        // Metadata được tạo nội bộ. Pattern giúp không vô tình
        // dùng đường dẫn có segment/dấu phân tách từ DB sau này.
        if (!record.storageKey().matches("[a-z0-9-]+\\.txt")) {
            throw new IOException("Invalid internal storage key");
        }

        Path path = root.resolve(record.storageKey()).normalize();
        if (!path.startsWith(root)) {
            throw new IOException("Outside storage root");
        }

        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
            throw new NoSuchFileException("Stored file is unavailable");
        }

        // Không follow symlink ở thành phần file cuối.
        // Root do ứng dụng sở hữu: không cho user tạo nested paths.
        return Files.newInputStream(
                path,
                StandardOpenOption.READ,
                LinkOption.NOFOLLOW_LINKS);
    }
}

@RestController
@RequestMapping("/api/files")
class FileController {

    private final PrivateFileStore store;

    FileController(PrivateFileStore store) {
        this.store = store;
    }

    @GetMapping("/{id}")
    ResponseEntity<Resource> download(
            @PathVariable("id") String id,
            Authentication authentication) throws IOException {

        FileRecord record = store.find(id)
                .orElseThrow(() ->
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND, "File not found"));

        // Authorization cấp object: KHÔNG chỉ kiểm tra logged-in.
        if (!record.owner().equals(authentication.getName())) {
            throw new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "Access denied");
        }

        // Luồng được mở chỉ sau khi đã kiểm tra principal + owner.
        InputStream stream = store.open(record);
        Resource body = new InputStreamResource(stream);

        String contentDisposition = ContentDisposition.attachment()
                .filename(record.displayName(), StandardCharsets.UTF_8)
                .build()
                .toString();

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .contentLength(record.size())
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        contentDisposition)
                .header("X-Content-Type-Options", "nosniff")
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(body);
    }
}
```

### 9.3. Giải thích bảo mật của chương trình

- `SecurityFilterChain` bắt buộc authentication; `Authentication#getName()` được Spring Security cung cấp từ identity HTTP Basic, không lấy từ header `X-User` do client tự bịa.
- `PrivateFileStore.find(id)` chỉ trả metadata mà **server tạo**. Controller không dùng `id` làm filesystem path.
- So sánh `record.owner()` với `authentication.getName()` là object authorization tối thiểu. Nếu bob gửi ID hợp lệ của Alice, API trả 403. Ứng dụng thật cần service/ACL kiểm soát quyền động và tenant.
- Root được tạo bằng `Files.createTempDirectory(...)` và thực hiện `toRealPath()` tại startup; file keys là chuỗi cố định nội bộ không chứa thư mục, không có path do client cung cấp. Thư mục lưu production phải đặt ở vị trí riêng có ACL/owner rõ ràng; ví dụ không khẳng định permissions của mọi nền tảng là giống nhau.
- `Files.isRegularFile(...NOFOLLOW_LINKS)` kiểm tra file cuối không phải symlink tại thời điểm kiểm tra; `Files.newInputStream(...NOFOLLOW_LINKS)` cố gắng không follow symlink ở file cuối khi mở. Root/private directory vẫn phải được bảo vệ khỏi tiến trình độc hại có thể đổi cấu trúc giữa hai thao tác.
- `InputStreamResource` giúp response converter truyền nội dung từ stream. Vì stream one-shot, response đặt trước `contentLength(record.size())` từ metadata demo đã có. Khi metadata không còn đáng tin hoặc file có thể đổi size, cần thiết kế cơ chế nhất quán và xử lý error/streaming riêng.
- `ContentDisposition.attachment()` tạo header download thay vì cho user kiểm soát raw header. Tên hiển thị trong metadata cũng nên được kiểm soát khi cho user tải lên.
- `Cache-Control: no-store` và `nosniff` giảm rủi ro caching/content sniffing. Chúng không thay authorization hoặc nội dung scan.
- Ví dụ có root thư mục tạm và metadata in-memory: **restart sẽ tạo lại file mới**; không dùng cách này để lưu file bền vững.

### 9.4. Khởi chạy

Trong thư mục Spring Initializr project:

```bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell hoặc Command Prompt
mvnw.cmd spring-boot:run
```

Spring Boot mặc định dùng `http://localhost:8080` nếu chưa cấu hình port/context path.

### 9.5. Kiểm thử HTTP theo identity

**Alice tải file của Alice:**

```bash
curl -i -u alice:alice-password \
  http://localhost:8080/api/files/11111111-1111-4111-8111-111111111111
```

Phần chính của response:

```http
HTTP/1.1 200
Content-Type: text/plain
Cache-Control: no-store
X-Content-Type-Options: nosniff

Hello Alice
```

Trong response thực, còn có `Content-Disposition: attachment` với filename được encode theo cách của Spring và `Content-Length: 12`. Body là **12 byte**: `Hello` (5) + space (1) + `Alice` (5) + newline (1). Trình duyệt có thể download thay vì render text vì header attachment.

**Bob cố truy cập file Alice:**

```bash
curl -i -u bob:bob-password \
  http://localhost:8080/api/files/11111111-1111-4111-8111-111111111111
```

Dự kiến **403 Forbidden**; file không được mở bởi controller vì kiểm tra owner đã thất bại. Body lỗi cụ thể do Spring Boot/Security error configuration quyết định, nên không ép JSON exact output.

**Alice dùng ID không tồn tại:**

```bash
curl -i -u alice:alice-password \
  http://localhost:8080/api/files/99999999-9999-4999-8999-999999999999
```

Dự kiến **404 Not Found**.

**Không gửi thông tin đăng nhập:**

```bash
curl -i \
  http://localhost:8080/api/files/11111111-1111-4111-8111-111111111111
```

Dự kiến **401 Unauthorized** với challenge `WWW-Authenticate` thích hợp cho HTTP Basic, do Spring Security xử lý trước controller.

**Alice cố đưa traversal string vào URL:**

```bash
curl -i -u alice:alice-password \
  'http://localhost:8080/api/files/..%2F..%2Fprivate%2Fsecret.txt'
```

Request có thể bị servlet container/Spring Security firewall/MVC mapping từ chối trước handler dưới dạng 400/404. Nếu handler nhận được một ID không nằm trong map, nó không tạo filesystem path từ ID, do đó không mở được file ngoài root. **Không cam kết chính xác status cho mọi encoding/môi trường**; chỉ cam kết thiết kế không ánh xạ input đó thành path.

Trong PowerShell, dùng `curl.exe` và viết lệnh một dòng để tránh `curl` alias và ký tự xuống dòng Bash.

## 10. Tải lên an toàn: pipeline khuyến nghị

Demo ở mục 9 chỉ GET. Để thêm `POST multipart` trong ứng dụng thật, không chỉ cần `@RequestParam MultipartFile`; cần một pipeline có giới hạn rõ:

```text
Authenticated user
   |
Authorization: canUploadTo(targetFolder/tenant)?
   |
Multipart size limits + quotas + rate limiting
   |
Validate filename display + allowlisted extension
   |
Validate actual file type/signature + parse/sandbox policy
   |
Server generates opaque storage key
   |
Private root (outside webroot) + CREATE_NEW
   |
Copy as stream; compute hash/scan if needed
   |
Persist metadata: owner/tenant/ACL/size/status
   |
Return 201 Created + opaque file ID
```

### 10.1. Spring Boot multipart limits

Ví dụ trong `application.properties`:

```properties
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
spring.servlet.multipart.file-size-threshold=0B
```

- `max-file-size` giới hạn một file.
- `max-request-size` giới hạn toàn multipart request.
- `file-size-threshold=0B` liên quan ngưỡng lưu phần nội dung multipart ra disk theo cơ chế Servlet/container; **không** thay thế quota đĩa, timeout, số lượng parts và cleanup.
- Những setting này không phải hard cap chung cho mọi JSON/binary request. Cấu hình thêm reverse proxy/container hoặc byte-counting limit tùy đường dữ liệu.

### 10.2. Không dùng `getBytes()` cho upload lớn

```java
// Không nên: tạo cả byte array trong heap.
byte[] full = upload.getBytes();
```

Thay vì vậy, sau khi phân quyền/giới hạn và tạo storage key:

```java
// Fragment minh họa bên trong storage service.
String storageKey = UUID.randomUUID().toString() + ".bin";
Path destination = storageRoot.resolve(storageKey);

try (InputStream input = upload.getInputStream();
     OutputStream output = Files.newOutputStream(
             destination,
             StandardOpenOption.CREATE_NEW,
             StandardOpenOption.WRITE)) {
    input.transferTo(output);
}
```

Đoạn trên cần `java.util.UUID`, `java.io.InputStream`, `java.io.OutputStream`, `java.nio.file.*`; `storageRoot` phải là thư mục private do server kiểm soát và `upload` là multipart object đã kiểm tra. Không dùng originalFilename để tạo destination. Cần rollback/cleanup nếu copy fail, không publish file metadata trước khi upload và scan hoàn tất.

### 10.3. MIME type và extension không đáng tin

`MultipartFile.getContentType()` là thông tin do client gửi. File tên `photo.png` hoặc header `image/png` không có nghĩa bytes thật là PNG. Với yêu cầu nghiệp vụ:
- Chỉ cho phép loại file cần thiết.
- Dựa vào file signatures + thư viện parse đáng tin cậy, không chỉ extension/header.
- Chặn tệp thực thi/script khi không cần thiết.
- Quét malware/CDR nếu môi trường yêu cầu.
- Tránh xử lý ảnh/XML/PDF/ZIP thiếu giới hạn kích thước sau khi giải mã hoặc giải nén.
- Không phục vụ file user upload trên cùng origin có thể thực thi HTML/JavaScript nếu nội dung không tin cậy; cân nhắc domain chuyên cho download và `Content-Disposition: attachment`.

**Zip Slip:** với archive, mỗi entry name là untrusted path. Cần normalize và kiểm tra containment của từng entry, chặn symbolic link, đường dẫn tuyệt đối, tổng kích thước đã giải nén và số entry. Chỉ kiểm tra filename của ZIP upload **không đủ**.

## 11. Tải xuống và Content-Disposition

Với private file đã được phép đọc, một response điển hình:

```java
return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .header(HttpHeaders.CONTENT_DISPOSITION,
                ContentDisposition.attachment()
                        .filename(safeDisplayName, StandardCharsets.UTF_8)
                        .build()
                        .toString())
        .header("X-Content-Type-Options", "nosniff")
        .cacheControl(CacheControl.noStore())
        .body(resource);
```

Đây là snippet riêng, cần `safeDisplayName` đã được kiểm soát và `resource` có thể stream. Không dùng raw string:

```java
// ANTI-PATTERN: tên lấy từ client có thể gây header/display issues.
response.setHeader("Content-Disposition",
        "attachment; filename=" + userSuppliedName);
```

Không cho client gửi content disposition để đổi đường dẫn mở file. Filename trong header chỉ điều khiển **gợi ý tên tải xuống**, không có quyền thay storage key.

Nếu endpoint hỗ trợ HTTP Range/partial content, cache validators, CDN hoặc signed links:
- Chỉ thực hiện sau khi đã kiểm tra ACL.
- Đảm bảo mỗi đoạn byte tải xuống đều thuộc cùng file được phép.
- Với redirect sang object storage, signed URL phải có phạm vi object cụ thể, TTL ngắn và không lộ credentials chung.
- Không lưu private response ở public CDN cache trừ khi đã thiết kế cache key/auth isolation rõ ràng.

## 12. Symlink, TOCTOU và giới hạn của path validation

### 12.1. TOCTOU nghĩa là gì?

**Time of Check to Time of Use**: hệ thống kiểm tra path/file ở thời điểm T1, nhưng mở/tác động file ở T2. Nếu một đối thủ có thể sửa symlink/thư mục giữa hai thời điểm, kiểm tra đúng ở T1 chưa chắc bảo vệ thao tác T2.

```text
T1: Files.isRegularFile("/private/root/a.txt")
        |
Attacker replaces entry a.txt with symlink
        |
T2: Files.newInputStream("/private/root/a.txt")
        |
Unexpected target
```

Nếu attacker có quyền sửa thư mục lưu, chỉ `normalize()` hay `toRealPath()` không giải quyết triệt để. Biện pháp trọng yếu là **OS directory ownership và ACL** sao cho attacker không thể thay đổi cấu trúc root.

### 12.2. Điều gì bảo vệ mạnh hơn?

- Sử dụng **flat private storage root** và storage key không chứa `/`, `\\` hoặc nested segments.
- Không cấp shell/local user không tin cậy quyền write trong root/parent directories.
- Dùng `CREATE_NEW` khi tạo, `NOFOLLOW_LINKS` lúc mở theo hỗ trợ API, và một file root không thể bị thay bởi actor khác.
- Với yêu cầu chống race trong môi trường filesystem shared/adversarial, cân nhắc `SecureDirectoryStream` (relative operations gắn directory handle) nếu provider hỗ trợ, hoặc cơ chế storage API chuyên dụng.
- File permission/ACL nên tối thiểu: user chạy app chỉ đọc/chỉnh những file cần thiết; không chạy process dưới tài khoản root hoặc dùng mount rộng chứa secrets.
- Nếu cách lưu trữ cho phép hardlinks hoặc bind mounts từ actor khác, cần chính sách OS/container mount phù hợp; chỉ kiểm tra symlink là chưa đủ.

**Lưu ý:** `SecureDirectoryStream` không phải lúc nào cũng được hỗ trợ bởi filesystem provider; phải có fallback có đánh giá an toàn, không tự “fallback” sang truy cập path không kiểm soát khi yêu cầu security cao.

### 12.3. Path validation và authorization phải giữ riêng

Ngay cả khi:
```text
Path is inside /srv/app/private-files
```
thì file vẫn có thể thuộc tenant khác. Và ngay cả khi file được gắn `owner=alice` trong database, một `storageKey=../../secret` vẫn có thể dẫn ra ngoài filesystem. Cần **cả hai** lớp kiểm soát.

## 13. Kiểm thử an ninh bằng MockMvc và service tests

Trong dự án Spring Boot demo, có thể thêm `spring-boot-starter-test` và dependency test cho Spring Security:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-test</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-test</artifactId>
  <scope>test</scope>
</dependency>
```

Test HTTP:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FileAccessTest {

    @Autowired
    MockMvc mvc;

    @Test
    void ownerMayRead() throws Exception {
        mvc.perform(get("/api/files/" + PrivateFileStore.ALICE_ID)
                        .with(httpBasic("alice", "alice-password")))
                .andExpect(status().isOk());
    }

    @Test
    void otherUserForbidden() throws Exception {
        mvc.perform(get("/api/files/" + PrivateFileStore.ALICE_ID)
                        .with(httpBasic("bob", "bob-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedMustAuthenticate() throws Exception {
        mvc.perform(get("/api/files/" + PrivateFileStore.ALICE_ID))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownIdIsNotFound() throws Exception {
        mvc.perform(get("/api/files/not-a-file")
                        .with(httpBasic("alice", "alice-password")))
                .andExpect(status().isNotFound());
    }
}
```

Lưu file tại `src/test/java/com/example/demo/FileAccessTest.java`. Đây là test JUnit 5 dùng Spring Boot 3.x và security-test; code giả định chưa thêm Security configuration khác. Lệnh:

```bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
```

Cần thêm các test cho upload/path operations (không có trong demo GET):
- `../`, `..\\`, absolute path, encoded traversal, double-decoding ở tầng phù hợp.
- File ID của tenant khác, share/revoke, deleted/quarantined file.
- Symlink trong storage root (trên filesystem hỗ trợ) và file bị thay giữa check/open.
- Multipart lớn hơn limit, loại file bị cấm, MIME giả, ZIP entry traversal.
- Filename chứa control chars/CRLF/Unicode dài, duplicate storage keys.
- 404/403 consistency, no path leaks trong error body và logs.
- Static URL không bypass controller security.
- Download lớn có streaming/memory profile tốt, không `Files.readAllBytes` toàn file.

### 13.1. Unit test Path startsWith đúng semantics

```java
import java.nio.file.Path;

public class PathBoundaryExample {
    public static void main(String[] args) {
        Path root = Path.of("/srv/files").normalize();
        Path good = root.resolve("a.txt").normalize();
        Path sibling = Path.of("/srv/files-evil/x.txt").normalize();

        System.out.println(good.startsWith(root));
        System.out.println(sibling.startsWith(root));
    }
}
```

Đây là chương trình Java **độc lập** (ví dụ đường dẫn dạng Unix được `Path` hiểu theo hệ điều hành). Trên Linux/macOS với `/` là separator, chạy:

```bash
javac PathBoundaryExample.java
java PathBoundaryExample
```

Stdout:

```text
true
false
```

Không lấy output này làm bằng chứng chống symlink; chương trình chỉ kiểm tra lexical component prefix trên hệ Unix. Trên Windows cần test bằng đường dẫn native tương ứng.

## 14. Những lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `root + userPath` | Traversal/đọc ngoài root | Dùng opaque ID → metadata → storage key server tạo |
| Chỉ kiểm tra `contains("../")` | Bỏ qua Windows, encoding, symlink | Allowlist storage key + Path checks + OS isolation |
| Dùng `String.startsWith(root)` | Chấp nhận sibling directory như `root-evil` | Dùng `Path.startsWith(root)` |
| Tin `normalize()` là real path | Symlink có thể thoát root | Dùng toRealPath/NOFOLLOW và private storage |
| Check rồi mở file trong shared writable dir | TOCTOU symlink swap | Không cho attacker ghi vào dir; dùng handle-relative API nếu cần |
| Lấy `getOriginalFilename()` để lưu | Traversal, overwrite, tên độc hại | UUID/random server key; displayName tách biệt |
| Dùng `Files.write(...)` ghi đè file | Mất dữ liệu/race | `CREATE_NEW` cho upload mới |
| Kiểm tra đã đăng nhập nhưng không kiểm tra owner | IDOR/BOLA | ACL trên từng record và action |
| Tin `ownerId`, `tenantId` do client gửi | Cross-user/cross-tenant access | Derive identity/tenant từ server auth context |
| File private dưới `static/` | Bypass auth controller | Outside webroot; serve qua authorized endpoint |
| Tin `Content-Type`/extension upload | File giả dạng, XSS, parser exploit | Validate bytes/format, allowlist, scan |
| Dùng `MultipartFile.getBytes()` | Nạp file lớn vào heap | Stream sang storage, enforce quotas |
| `readAllBytes()` khi download | OOM/file lớn | `Resource`/stream, giới hạn tải |
| Trả raw file path trong error | Lộ cấu trúc server | Error body chung và log bảo mật |
| Response file cho phép inline HTML không tin cậy | Stored XSS | Attachment, nosniff, isolated download domain |
| Cache private file công khai | Lộ dữ liệu người dùng | `no-store` hoặc cache partition/permission model |
| Dùng UUID thay authorization | Ai có ID đều có thể truy cập | Check principal + record ACL |
| Upload ZIP kiểm tra tên archive nhưng không entry | Zip Slip | Per-entry safe extraction + quotas |

## 15. Checklist triển khai production

1. Tài nguyên được yêu cầu qua **opaque file ID** hay client có thể tự chọn filesystem path?
2. Storage key có được **server sinh** và không chứa segment do client cung cấp?
3. Directory root có nằm **ngoài webroot**, với OS permissions và container mounts tối thiểu?
4. Đã kiểm tra **authentication + authorization trên từng file, action và tenant** chưa?
5. Với symlink, đã kiểm soát root/parent permissions, `NOFOLLOW_LINKS` và TOCTOU chưa?
6. Upload có `max-file-size`, `max-request-size`, quotas, content validation/scanning và cleanup khi lỗi?
7. File upload được tạo bằng thao tác không ghi đè có tính atomic như `CREATE_NEW`?
8. Download có status/header đúng, không lộ storage path, không nạp toàn file vào heap?
9. Content-Disposition filename có được sanitize/encode; có `nosniff` và chính sách cache?
10. File private có thể bị truy cập trực tiếp qua static handler hoặc CDN URL không?
11. Quá trình xóa/đổi quyền có làm invalid signed URLs/cached copies đúng hợp đồng không?
12. Có kiểm thử người dùng A/B, traversal, encoded input, symlink, parser, concurrency, large files và audit logs?

## 16. Tự kiểm tra

**Câu 1.** `Path.resolve(input).normalize().startsWith(root)` đã chặn hoàn toàn traversal chưa?

**Đáp án:** Chưa. Nó phát hiện nhiều lexical escapes nhưng không đảm bảo đường dẫn thực khi có symbolic links và có thể còn TOCTOU. Bảo vệ tốt nhất là không dùng client path, dùng root private và server-generated key.

**Câu 2.** Nếu Alice biết UUID file của Bob nhưng cả hai đều đã đăng nhập, Alice được tải file Bob không?

**Đáp án:** Không. UUID không phải quyền; service phải kiểm tra object-level authorization, owner/tenant/ACL.

**Câu 3.** Có được dùng `MultipartFile.getOriginalFilename()` làm tên file trên server không?

**Đáp án:** Không nên. Đây là dữ liệu client, có thể chứa path/`..`; chỉ dùng làm display metadata đã xử lý, còn storage key do server tạo.

**Câu 4.** Tại sao `CREATE_NEW` tốt hơn “check file chưa tồn tại rồi write”?

**Đáp án:** `CREATE_NEW` dùng thao tác atomic tạo mới, tránh race giữa check và write và không ghi đè file/symlink đã có.

**Câu 5.** Trả 403 hay 404 khi một file thuộc tenant khác?

**Đáp án:** Tùy chính sách tiết lộ sự tồn tại tài nguyên. 403 biểu thị không được phép; 404 có thể giảm enumeration. Cả hai phải không cấp dữ liệu trái quyền.

**Câu 6.** `Content-Disposition: attachment` và `X-Content-Type-Options: nosniff` đã đủ để upload mọi loại file chưa?

**Đáp án:** Không. Cần giới hạn loại/size, quét hoặc xử lý an toàn, storage isolation và authorization; header chỉ giảm một số rủi ro phía client.

**Câu 7.** Vì sao tệp nằm trong thư mục cho phép vẫn có thể bị truy cập trái quyền?

**Đáp án:** Vì path containment khác **quyền trên đối tượng**. Tệp của người khác vẫn có thể cùng root; phải kiểm tra ACL/owner/tenant.

## 17. Tài liệu chính thức

- [Spring Framework 6.2 — MultipartFile Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/web/multipart/MultipartFile.html): `getOriginalFilename()` là giá trị client, không dùng mù quáng để lưu.
- [Spring Framework — Multipart Files](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): cách nhận multipart request trong MVC.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): static resource handlers và web configuration.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): multipart size limits và container settings.
- [Java 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `normalize`, `startsWith`, `toRealPath`.
- [Java 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `CREATE_NEW`, input/output streams, file attributes.
- [Java 17 — LinkOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS`.
- [OWASP Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal): rủi ro/biện pháp giảm thiểu traversal.
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): allowlist, content validation, storage isolation, access controls và file quotas.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, quyền cấp tài nguyên và kiểm tra trên từng request.

**Kết luận:** Spring MVC không tự bảo đảm file an toàn chỉ vì controller nhận `@PathVariable`, `MultipartFile` hoặc trả `Resource`. Thiết kế đúng là **ID tài nguyên → metadata do server quản lý → authentication và object authorization → storage key do server sinh → private root có OS permissions → thao tác file an toàn và streaming**. `normalize()`/`toRealPath()`/`NOFOLLOW_LINKS` là những lớp kỹ thuật bổ sung, không thay cho việc loại bỏ client-controlled path, ngăn TOCTOU và kiểm soát quyền người dùng.
