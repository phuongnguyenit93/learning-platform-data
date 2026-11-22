# Kiểm soát chuyển hướng mở, nội dung tải lên và thông tin nhạy cảm trong log (Spring MVC)

## 1. Mục tiêu: ba đầu vào không đáng tin, ba lớp bảo vệ bổ sung

Một ứng dụng Spring MVC thường nhận **URL đích chuyển hướng**, **tệp tải lên** và **nội dung yêu cầu** được ghi vào nhật ký. Cả ba đều có thể chứa dữ liệu do người dùng bên ngoài kiểm soát. Nếu sử dụng thiếu kiểm soát, chúng dẫn đến những vấn đề khác nhau:

- **Open redirect**: endpoint đưa người dùng đến domain do kẻ tấn công chọn, lợi dụng độ tin cậy của domain chính để lừa đảo, chuyển hướng OAuth sai đích hoặc làm lộ thông tin.
- **Unrestricted file upload / unsafe file handling**: tệp không tin cậy được lưu dưới tên hoặc thư mục nguy hiểm, phục vụ như mã thực thi/HTML, gây path traversal, chứa mã độc, tiêu hao CPU/bộ nhớ/ổ đĩa hoặc vượt quyền truy cập.
- **Sensitive-data logging và log injection**: token, session ID, password, thông tin cá nhân, dữ liệu form/multipart lọt vào log; nội dung chứa xuống dòng/format giả làm sai lệch hoặc giả mạo các bản ghi.

Ba vấn đề này có bề mặt tấn công và biện pháp riêng. Không thể sửa cả ba bằng một `@Valid`, một cấu hình CORS hoặc chỉ bật Spring Security. Các nguyên tắc chung:

1. Xác định **ranh giới tin cậy** trước khi dùng input: URL từ query/form, file metadata, request headers và raw body đều không đáng tin chỉ vì controller nhận được chúng.
2. **Allowlist theo nghiệp vụ** thay vì chỉ chặn vài chuỗi nguy hiểm.
3. Chuẩn hóa cách xử lý và hạn chế quyền/tác động: chuyển hướng đến đích được kiểm duyệt; tệp có tên server sinh, định dạng được kiểm tra, lưu ở vị trí riêng; log chỉ các trường cần vận hành.
4. Áp dụng giới hạn **độ lớn/thời gian/số lần**, authentication/authorization, CSRF, HTTP security headers và lớp bảo vệ hạ tầng khi phù hợp.
5. Kiểm thử cả trường hợp hợp lệ và các đầu vào đối kháng, xác nhận hành vi ở **HTTP response**, file system và observability pipeline.

Bài nằm trong module **Spring Framework - web**, chủ đề cha **CORS và an toàn web**. Baseline code mẫu dùng **Java 17+, Spring Boot 3.5.x / Spring Framework 6.2.x, Spring MVC Servlet**. Ví dụ không tự bật Spring Security hoặc cung cấp kho lưu production; phần production chỉ rõ những lớp cần bổ sung.

## 2. Mô hình luồng dữ liệu và điểm quyết định tin cậy

```text
Client / Browser
     |
     +--- query/form "destination" ----> MVC controller
     |                                    |
     |                           ALLOWLIST mã đích
     |                                    |
     |                       Response 303 Location: /portal/...
     |                       không phản chiếu raw URL
     |
     +--- multipart "file" -----------> multipart parser
     |                                    |
     |                        giới hạn bytes, loại/decoder,
     |                        dimensions, normalize ảnh
     |                                    |
     |                          server-generated ID + name
     |                                    |
     |                      private storage ngoài webroot
     |                                    |
     |                         download handler có auth
     |
     +--- request headers/body -------> servlet filters / MVC / app
                                          |
                                chỉ chọn safe event fields
                                          |
                           structured log + newline escaping
                                          |
                            log sink có quyền/retention
```

Những điểm cần phân biệt:

- **Redirect** dùng HTTP status 3xx và header `Location`. Nó **không** chứng minh rằng đích được tin cậy hay người dùng đã xác thực.
- **CORS** kiểm soát JavaScript trong browser được đọc response cross-origin theo chính sách, **không ngăn browser theo HTTP redirect** hoặc ngăn kẻ tấn công đăng URL phishing cho người dùng.
- **Content Security Policy (CSP)**, `X-Content-Type-Options: nosniff`, `Content-Disposition` và cookie flags là lớp bảo vệ hữu ích, **không thay thế** việc kiểm tra file hoặc redirect.
- **MIME Content-Type** do client công bố chỉ là metadata input. Nó có thể sai hoặc cố ý giả mạo.
- **Log framework parameterized logging** giúp định dạng tham số và tránh phép nối chuỗi, **không tự loại bỏ PII, token hoặc ký tự CR/LF**.

## 3. Open redirect là gì? Vì sao nguy hiểm?

Giả sử ứng dụng có endpoint:

```http
GET /login/continue?next=https://outside.example/collect HTTP/1.1
Host: trusted.example
```

Nếu server sao chép nguyên `next` vào `Location`:

```http
HTTP/1.1 302 Found
Location: https://outside.example/collect
```

Người dùng click một liên kết bắt đầu bằng domain đáng tin nhưng sau đó được đưa tới website ngoài. Đây là **unvalidated redirect**. Kẻ tấn công có thể:

- Dùng domain tin cậy như bước trung gian trong chiến dịch phishing.
- Vượt qua bộ lọc URL chỉ kiểm tra **domain của liên kết đầu tiên**.
- Thao túng luồng **login/logout/return URL**.
- Kết hợp sơ hở trong OAuth/OIDC redirect registration, `state` hoặc token/code handling để làm lộ thông tin, tùy mô hình.
- Chuyển người dùng tới site phân phối mã độc hoặc giả danh biểu mẫu.

**Không phải mọi redirect sang domain khác đều là lỗ hổng.** Đôi khi thanh toán, SSO hoặc partner integrations cần external redirect. Lỗ hổng nằm ở việc **dữ liệu không tin cậy được phép quyết định đích mà không có chính sách kiểm soát đủ chặt**.

### 3.1. Anti-pattern trong Spring MVC

```java
// KHÔNG DÙNG: request input quyết định trực tiếp URL đích.
@GetMapping("/go")
String go(@RequestParam String next) {
    return "redirect:" + next;
}
```

`redirect:` trong MVC là **chỉ dẫn tạo redirect view**, không phải validator URL. Spring không thể biết business allowlist domain của bạn.

```java
// Cũng KHÔNG DÙNG: sao chép raw target vào Location.
@GetMapping("/go")
ResponseEntity<Void> go(@RequestParam String next) {
    return ResponseEntity.status(HttpStatus.FOUND)
            .location(URI.create(next))
            .build();
}
```

Các fragment trên cho thấy lỗi bảo mật, không phải API được khuyến nghị. `URI.create` chỉ parse URI theo cú pháp nhất định; nó **không quyết định** domain hay đường dẫn có được phép hay không.

### 3.2. Vì sao chặn mỗi chuỗi "http" không đủ?

Những dạng đích đáng xem xét khi input là URL/path:

| Dạng do client đề xuất | Điểm nguy hiểm |
| --- | --- |
| `https://attacker.example/path` | URL tuyệt đối tới domain ngoài |
| `//attacker.example/path` | Network-path reference: browser dùng scheme hiện tại nhưng host bên ngoài |
| `\\\\attacker.example` hoặc dấu slash/backslash hỗn hợp | Một số tầng client/proxy/parser xử lý dấu phân cách khác nhau |
| `https://trusted.example.attacker.example/` | Host có prefix giống domain tin cậy nhưng thực ra khác |
| `https://trusted.example@attacker.example/` | Phần trước `@` là userinfo; host thực nằm sau `@` |
| `https://TRUSTED.EXAMPLE./` | Domain case/trailing dot; cần chuẩn hóa theo chính sách |
| URL chứa `%2f`, `%5c`, `%252f` | URL encoding và double-decoding gây mơ hồ |
| URL chứa CR/LF hoặc encoded CR/LF | Header/log injection tùy downstream và validation |
| URL có scheme `javascript:` / `data:` | Không phải đích HTTP(S) an toàn để tự chuyển hướng |
| Open-redirect endpoint trên chính domain tin cậy | Có thể thành **redirect chain** đến attacker |

Không dùng kiểm tra `next.startsWith("https://trusted.example")` hoặc `next.contains("trusted.example")`. Chúng có thể nhận nhầm `trusted.example.attacker.example`, userinfo hoặc path chứa chuỗi domain.

## 4. Cách an toàn nhất: không nhận URL mà nhận mã đích

Nếu chức năng chỉ cần chuyển về một vài trang nội bộ, nhận **mã đích được allowlist**, không nhận URL/path:

```text
Client gửi: destination=dashboard
Server map: "dashboard" -> "/portal/dashboard"

Client gửi: destination=help
Server map: "help" -> "/portal/help"

Client gửi: destination=https://outside.example
Server: 400 Bad Request (không Location)
```

Ưu điểm: không có vấn đề URL canonicalization, protocol-relative URL, userinfo, IDN hoặc double encoding cho những đích không được hỗ trợ. Mapping cố định do server sở hữu cũng giúp audit dễ hơn.

Trong code mẫu ở phần 9:

```java
String path = switch (destination) {
    case "dashboard" -> "/portal/dashboard";
    case "help" -> "/portal/help";
    default -> throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "Unsupported destination");
};

return ResponseEntity.status(HttpStatus.SEE_OTHER)
        .location(URI.create(path))
        .build();
```

Đây là **fragment trong handler**. Status `303 See Other` phù hợp một form POST hoàn tất và muốn browser thực hiện GET đích; với navigation GET thuần, redirect 302/303 tùy contract. **Không cần gửi lại raw destination vào HTML/log/error message**.

### 4.1. Khi phải hỗ trợ redirect ngoài domain

Chỉ xét cho flow có business requirement rõ ràng (đối tác thanh toán, SSO). Hướng thiết kế:

1. Ưu tiên **partner ID** → lấy URL từ config tin cậy, thay vì để client đưa URL tuyệt đối.
2. Nếu URL thực sự được client truyền, parse bằng URI parser và yêu cầu scheme `https` (hoặc policy riêng) cùng **host chính xác** sau canonicalization.
3. Dùng **danh sách exact hosts / origins**, không dựa vào substring hay wildcard `*.example.com` quá rộng.
4. Cân nhắc **port, userinfo, path, query, trailing dot, IDN/punycode, fragment, percent encoding và normalize**; từ chối inputs mơ hồ thay vì cố đoán.
5. Nếu cần external consent, cho người dùng thấy destination host rõ ràng; không bao giờ gắn access tokens, session IDs hoặc password vào URL.
6. Với OAuth2/OIDC, **redirect_uri phải khớp quy tắc đăng ký của provider** và `state`/PKCE được kiểm chứng theo flow; việc app có một “allowlist gần đúng” không thay thế bảo vệ giao thức.
7. Kiểm soát redirect chains: URL internal hợp lệ không được biến thành lối vòng để đi tiếp tới attacker.
8. Review sự khác nhau giữa public base URL, reverse proxy, trusted forwarded headers và path prefix khi deploy.

**Điểm dễ nhầm trong Spring:** `RedirectView#setHosts(...)` hoặc `UrlBasedViewResolver#setRedirectHosts(...)` dùng thông tin hosts trong **cơ chế URL encoding/session handling**, **không phải một cơ chế allowlist bảo mật tuyệt đối để cấm open redirect**. Không dùng cấu hình đó làm thay cho validation/route mapping nghiệp vụ.

## 5. Redirect trong Spring MVC: status, URI, scope và data leakage

### 5.1. `redirect:` và `RedirectView`

`@Controller` có thể trả:

```java
@PostMapping("/save")
String save() {
    // Đã lưu nghiệp vụ thành công.
    return "redirect:/portal/dashboard";
}
```

Fragment này dùng **đích cố định từ server**, khác với `"redirect:" + untrustedValue`. Spring tạo redirect view và thông thường sinh status 302 theo mặc định Servlet MVC; có thể cấu hình 303/redirect view status theo version/thiết kế.

Với `ResponseEntity`:

```java
return ResponseEntity.status(HttpStatus.SEE_OTHER)
        .location(URI.create("/portal/dashboard"))
        .build();
```

Mẫu này trả HTTP `303` trực tiếp và tường minh. Đích root-relative `/portal/dashboard` giả định app nằm ở origin root. Nếu ứng dụng triển khai dưới `/shop` hoặc gateway prefix, cần dựng URL có prefix **public** đúng; `RedirectView#setContextRelative(true)` có thể hỗ trợ context-relative view redirects. Tránh lấy host ngẫu nhiên từ client rồi tạo external URL.

### 5.2. Chọn status phù hợp

| Status | Semantics cơ bản | Lưu ý |
| --- | --- | --- |
| `302 Found` | Redirect tạm thời; user agents lịch sử có thể đổi POST thành GET | Dùng nhiều cho web navigation |
| `303 See Other` | Hướng client lấy representation ở URI khác, thông thường qua GET | Phù hợp Post-Redirect-Get |
| `307 Temporary Redirect` | Giữ HTTP method và body qua redirect | Có thể vô tình forward POST body nhạy cảm nếu destination không tin cậy |
| `308 Permanent Redirect` | Redirect vĩnh viễn và giữ method | Không dùng vô tình cho thay đổi tạm hoặc user-controlled target |
| `301 Moved Permanently` | Chuyển thường trực; client/cache có thể lưu mapping | Cẩn thận với link chưa chuẩn và auth/session flows |

Nếu bạn redirect một POST chứa password hoặc payload bí mật bằng `307/308` sang host không tin cậy, client có thể gửi lại method/body tới host đó; đây là lý do nghiêm trọng để không cho client quyết định redirect target. **303 không tự khiến target an toàn**; nó chỉ thay đổi follow-up method semantics.

### 5.3. Không đưa bí mật vào URL, model redirect hay header

Các nơi có thể lộ query parameters: browser history, reverse-proxy access logs, analytics, monitoring, crash reports, referrers hoặc screenshots.

Không redirect kiểu:

```text
Location: https://partner.example/landing?access_token=<secret>
Location: /portal/dashboard?password=<secret>
```

`RedirectAttributes.addAttribute(...)` có thể thêm giá trị vào redirect URL; `addFlashAttribute(...)` lưu giá trị tạm cho request sau (thường dùng session/FlashMap), phù hợp thông báo không nhạy cảm. **Flash attributes vẫn thuộc server state và không phải nơi nên cất token bí mật một cách tùy tiện**.

Với SPA dùng OAuth redirect, theo đúng flow OAuth/OIDC, không tự phát token từ server vào URL chỉ vì dễ làm.

## 6. File upload: các lớp input không đáng tin

Một request file upload thường là `multipart/form-data`, ví dụ:

```http
POST /api/images HTTP/1.1
Content-Type: multipart/form-data; boundary=...

--...
Content-Disposition: form-data; name="file"; filename="avatar.png"
Content-Type: image/png

<binary content>
--...--
```

Cả `filename`, `Content-Type` lẫn bytes bên trong đều do client kiểm soát. Những kiểu tấn công đáng lưu ý:

- **Path traversal:** filename như `../../config.yml` nếu code ghép trực tiếp vào `Path`.
- **Extension confusion:** `photo.png.exe`, tên chấm/ký tự Unicode đặc biệt, case differences, double extension, trailing dots/spaces; phục vụ có thể bị nhầm content type hoặc thực thi.
- **MIME spoofing:** header khai `image/png` nhưng body là HTML/script hoặc định dạng khác.
- **Polyglot files:** một file có thể có signature hợp lệ của một định dạng và nội dung phụ nguy hiểm; magic bytes đơn lẻ không đủ đảm bảo vô hại.
- **Malware và active content:** Office macro, SVG script, HTML, PDF active features, archive executables.
- **Archive extraction attacks:** ZIP slip (`../` trong entry name), zip bomb, symbolic links, nested archives.
- **Image decompression bombs:** file compressed nhỏ nhưng ảnh khi decode có kích thước/pixel cực lớn.
- **Excessive resource usage:** upload lớn, multipart nhiều parts, requests liên tục, storage quota bị đầy.
- **Unauthorized access:** tài liệu riêng được lưu dưới URL dễ đoán hoặc static public folder; không kiểm tra owner khi download.
- **File overwrite/race:** dùng original filename làm target khiến ghi đè file khác.
- **Log leakage:** ghi raw original filename hoặc nội dung file vào logs, trace/APM.

Các biện pháp phải áp dụng **theo loại file, người dùng, mức độ tin cậy và use case**, không bật một kiểm tra chung rồi coi mọi uploads là an toàn.

## 7. Chính sách upload chặt: allowlist + kiểm chứng nội dung + storage isolation

### 7.1. Allowlist loại file

Chọn danh sách **ngắn, cần cho nghiệp vụ**. Ví dụ profile ảnh PNG, không mở `image/*` rồi chấp nhận mọi ảnh/script-bearing SVG. Cần phân biệt:

1. **Extension**: chỉ metadata gợi ý cho UX, không phải bằng chứng.
2. **Declared MIME**: `MultipartFile#getContentType()`, do client tự khai.
3. **Signature/magic**: vài bytes đầu; kiểm tra sơ bộ, vẫn chưa đủ với polyglot/định dạng phức tạp.
4. **Decoder/parser validation**: cấu trúc file được library phù hợp đọc được, có giới hạn resources.
5. **Canonicalization/CDR/transcoding**: xây lại representation đã kiểm tra và loại bớt metadata/phần nguy hiểm nếu định dạng cho phép.
6. **AV/sandbox scanning**: kiểm tra mã độc/đặc tính thực thi theo policy; không thay thế validation và authorization.

**Không** lấy tên gốc `file.getOriginalFilename()` rồi lưu tại `static/uploads/`; đó là mẫu dễ gây traversal, overwrite, public exposure và unsafe type handling.

### 7.2. Giới hạn kích thước ở nhiều tầng

Với Spring Boot 3.5 Servlet multipart:

```properties
# Chỉ ví dụ cho demo chỉ nhận PNG cỡ nhỏ:
spring.servlet.multipart.max-file-size=256KB
spring.servlet.multipart.max-request-size=320KB
```

Đây là **giới hạn do multipart parser/container** áp dụng. Vẫn nên xác minh bytes của file tại application layer và áp quota/rate limit ở gateway/server. Upload có thể bị từ chối **trước khi controller chạy**; các lỗi thường liên quan `MaxUploadSizeExceededException` và HTTP 413 trong error handling được cấu hình.

`max-file-size` khác `max-request-size`: request có thể có nhiều parts/headers overhead, nên giới hạn tổng có thể lớn hơn giới hạn từng file. Không tin `Content-Length` là đo chính xác trong mọi request; dữ liệu chunked/streamed có thể khác. Với stream lớn, ưu tiên streaming và hạn mức đếm bytes để tránh đọc hết vào memory.

### 7.3. Store ngoài webroot, tên do server sinh

Mô hình đáng dùng:

```text
Upload request
  -> xác thực + phân quyền + quota
  -> validate type/size/structure
  -> AV/CDR/normalization nếu cần
  -> quarantine area
  -> random generated storage key, không dùng client filename
  -> private storage / object store
  -> lưu metadata record (owner, size, MIME, hash, status)
  -> download endpoint kiểm tra quyền
  -> Content-Disposition và Content-Type an toàn
```

Trong demo phần 9, lưu **PNG đã decode rồi re-encode** vào thư mục tạm ngẫu nhiên do server tạo, dùng filename hệ thống tạo, không phục vụ trực tiếp qua Boot `static/**`. Đây là **môi trường học tập**, không phải giải pháp lưu file production bền vững; thư mục tạm có thể bị xóa, không phân quyền giữa người dùng và không có virus scanner.

### 7.4. Phòng path traversal và symlink

Anti-pattern:

```java
// NGUY HIỂM: filename do client kiểm soát quyết định path.
Path output = uploadRoot.resolve(file.getOriginalFilename());
file.transferTo(output);
```

Nếu original filename chứa `../` hoặc đường dẫn tuyệt đối, việc resolve/normalize không được kiểm tra đúng có thể thoát khỏi upload root. Ngoài ra có race nếu attacker có quyền thao túng symlink/path trong storage directory.

Ưu tiên:

- Tạo opaque identifier bằng `UUID.randomUUID()` hoặc random storage key đáng tin.
- Tạo file ở private folder do server kiểm soát, ví dụ `Files.createTempFile(root, "img-", ".png")`; không chèn filename client vào path.
- Không cho request cung cấp **arbitrary relative path**.
- Nếu phải dùng path từ client, cần normalize/canonicalize, resolve real path theo policy, chống traversal/symlink và kiểm tra ownership, kể cả race conditions.
- Dùng storage API có key semantics riêng khi chạy trên S3/GCS; đừng nhầm object-store keys với filesystem path security.

**Không lưu upload vào** `src/main/resources/static` / `public` / thư mục executable WAR/JAR rồi tưởng mỗi file có auth. Các locations này thường dùng để public static content.

## 8. Giao tiếp HTTP khi upload/download

Một API upload hợp lệ có thể trả `201 Created` với ID server cấp và `Location` chỉ tới resource mới:

```http
HTTP/1.1 201 Created
Location: /api/images/3a72ad90-f5cb-47ed-b97b-23278331fb9d
Content-Type: application/json

{"id":"3a72ad90-f5cb-47ed-b97b-23278331fb9d",
 "mediaType":"image/png"}
```

ID ở đây là ví dụ format; response thực tế do server cấp ngẫu nhiên. Nếu xử lý upload cần **quét mã độc bất đồng bộ** trước khi coi file sẵn sàng, một thiết kế hợp lý là `202 Accepted` với trạng thái processing/quarantine; **không công khai file trước khi đạt policy**.

Download phải được quyết định ở **server side**:

- Lấy record dựa trên opaque ID, xác minh authenticated user có quyền.
- Không ghép trực tiếp input ID thành đường dẫn tùy ý.
- Chọn `Content-Type` dựa trên **loại đã kiểm chứng**, không lặp raw upload content type.
- Với nội dung có nguy cơ được browser render như HTML/SVG/PDF, cân nhắc `Content-Disposition: attachment` và content scanning/sandbox, CSP hoặc serving từ origin cô lập.
- Đặt `X-Content-Type-Options: nosniff` khi phù hợp.
- Dùng `Cache-Control: private` hoặc `no-store` với tài liệu nhạy cảm; không giả định CDN công khai có thể cache mọi ảnh tải lên.
- Không phản hồi filesystem path, storage key nội bộ hoặc raw exception message.

**Không bao giờ coi UUID là cơ chế phân quyền.** UUID khó đoán giúp giảm dự đoán nhưng GET/download vẫn phải kiểm tra quyền của người dùng đối với resource.

## 9. Ví dụ Spring Boot 3.5 / Java 17 có thể chạy

Demo gồm:

- `POST /navigation/continue?destination=dashboard|help` trả `303 Location` từ **mã allowlist**.
- `GET /portal/dashboard` và `GET /portal/help` để quan sát đích chuyển hướng.
- `POST /api/images` chỉ nhận PNG nhỏ qua multipart; kiểm tra kích thước trước/sau đọc, dùng Java ImageIO xác định định dạng, giới hạn chiều rộng/cao, **re-encode PNG**, lưu dưới tên random ở private temp directory.
- `GET /api/images/{uuid}` trả PNG đã chuẩn hóa dưới dạng **attachment** với `nosniff` và `Cache-Control: no-store`.
- Logging chỉ ghi ID do server cấp, kích thước output; không ghi request body, original filename, cookie/token.
- Test MockMvc cho allowlist, invalid redirect, upload hợp lệ/không hợp lệ và download.

**Giới hạn chủ ý của demo:** không có authentication/authorization, AV scan, user quota, shared persistent storage, key rotation hoặc moderation. **Không triển khai công khai một endpoint lưu/truy xuất upload y hệt demo**; phải bổ sung các lớp này trước production.

### 9.1. Gradle và multipart properties

Trong project Boot 3.5 đã có Boot plugin/repositories/Java toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là fragment `build.gradle`; thêm vào project Boot chuẩn, không coi là toàn bộ file Gradle độc lập. Java `ImageIO` thuộc JDK `java.desktop` module (có ở Java 17 thông thường; với custom jlink image phải giữ module phù hợp).

Tạo `src/main/resources/application.properties`:

```properties
spring.servlet.multipart.max-file-size=256KB
spring.servlet.multipart.max-request-size=320KB

# Không chủ động đưa request params/headers có thể nhạy cảm
# vào Spring MVC debug log:
spring.mvc.log-request-details=false
```

`spring.mvc.log-request-details=false` là mặc định thông dụng của Boot 3.5, nhưng ghi tường minh giúp thấy intent. Setting này **không xóa những log do code, reverse proxy, servlet access log, security filters hoặc APM khác ghi**.

### 9.2. Java application/controller/upload logic

Tạo **`src/main/java/demo/safeweb/SafeWebApplication.java`**:

```java
package demo.safeweb;

import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.ImageInputStream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class SafeWebApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeWebApplication.class, args);
    }
}

@RestController
class NavigationController {
    @PostMapping("/navigation/continue")
    ResponseEntity<Void> continueTo(
            @RequestParam String destination) {

        String path = switch (destination) {
            case "dashboard" -> "/portal/dashboard";
            case "help" -> "/portal/help";
            default -> throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Unsupported destination");
        };

        return ResponseEntity.status(HttpStatus.SEE_OTHER)
                .location(URI.create(path))
                .build();
    }

    @GetMapping("/portal/dashboard")
    String dashboard() {
        return "dashboard";
    }

    @GetMapping("/portal/help")
    String help() {
        return "help";
    }
}

record ImageResponse(String id, String mediaType) {}

@RestController
@RequestMapping("/api/images")
class ImageController {
    private static final Logger log =
            LoggerFactory.getLogger(ImageController.class);

    private static final int MAX_INPUT_BYTES = 256 * 1024;
    private static final int MAX_DIMENSION = 1024;
    private static final int MAX_PIXELS = 1024 * 1024;
    private static final int MAX_OUTPUT_BYTES = 4 * 1024 * 1024;

    private final Path privateRoot;
    private final ConcurrentMap<UUID, Path> saved =
            new ConcurrentHashMap<>();

    // DEMO ONLY: random temporary directory, not public/static.
    // Production: dedicated private storage, access control and lifecycle.
    ImageController() throws IOException {
        privateRoot = Files.createTempDirectory("safe-image-demo-");
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    ResponseEntity<ImageResponse> upload(
            @RequestPart("file") MultipartFile file)
            throws IOException {

        if (file.isEmpty() || file.getSize() > MAX_INPUT_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid image size");
        }

        // Verify actual bytes, not originalFilename or declared MIME.
        byte[] input = file.getBytes();
        if (input.length == 0 || input.length > MAX_INPUT_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid image size");
        }

        BufferedImage decoded = decodePng(input);

        // Re-encode the decoded pixels; do not serve the original bytes.
        ByteArrayOutputStream normalized = new ByteArrayOutputStream();
        if (!ImageIO.write(decoded, "png", normalized)) {
            throw new IOException("PNG encoder is unavailable");
        }
        byte[] canonicalPng = normalized.toByteArray();
        if (canonicalPng.length > MAX_OUTPUT_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Image output too large");
        }

        UUID id = UUID.randomUUID();
        Path generated = Files.createTempFile(
                privateRoot, "image-", ".png");

        try {
            Files.write(generated, canonicalPng);
            saved.put(id, generated);
        } catch (IOException ex) {
            Files.deleteIfExists(generated);
            throw ex;
        }

        // Log server-generated, bounded metadata only.
        log.info("image_upload_saved imageId={} bytes={}",
                id, canonicalPng.length);

        URI location = URI.create("/api/images/" + id);
        return ResponseEntity.created(location)
                .body(new ImageResponse(id.toString(), "image/png"));
    }

    @GetMapping(path = "/{id}",
            produces = MediaType.IMAGE_PNG_VALUE)
    ResponseEntity<byte[]> download(@PathVariable UUID id)
            throws IOException {

        Path stored = saved.get(id);
        if (stored == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Image not found");
        }

        // DEMO ONLY: real application must verify owner/permission first.
        byte[] content = Files.readAllBytes(stored);
        return ResponseEntity.ok()
                .contentType(MediaType.IMAGE_PNG)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"image.png\"")
                .header("X-Content-Type-Options", "nosniff")
                .cacheControl(CacheControl.noStore())
                .body(content);
    }

    private static BufferedImage decodePng(byte[] bytes)
            throws IOException {

        try (ImageInputStream input =
                     ImageIO.createImageInputStream(
                             new ByteArrayInputStream(bytes))) {

            if (input == null) {
                throw invalidImage();
            }

            Iterator<ImageReader> readers =
                    ImageIO.getImageReaders(input);
            if (!readers.hasNext()) {
                throw invalidImage();
            }

            ImageReader reader = readers.next();
            try {
                reader.setInput(input, true, true);
                if (!reader.getFormatName()
                        .equalsIgnoreCase("png")) {
                    throw invalidImage();
                }

                int width = reader.getWidth(0);
                int height = reader.getHeight(0);

                if (width < 1 || height < 1
                        || width > MAX_DIMENSION
                        || height > MAX_DIMENSION
                        || (long) width * height > MAX_PIXELS) {
                    throw invalidImage();
                }

                BufferedImage image = reader.read(0);
                if (image == null) {
                    throw invalidImage();
                }
                return image;
            } catch (IOException ex) {
                throw invalidImage();
            } finally {
                reader.dispose();
            }
        }
    }

    private static ResponseStatusException invalidImage() {
        return new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid PNG image");
    }
}
```

**Một file Java 17 hợp lệ theo class structure:** chỉ `SafeWebApplication` là public; các controller và record còn lại package-private, cùng package `demo.safeweb`. Java 17 cung cấp switch expression, `ImageIO` và `UUID`. Với dependency Boot web và JDK đầy đủ, Spring component scan sẽ phát hiện hai controllers.

**Quan trọng về mức bảo đảm:** ImageIO được giới hạn size/dimensions rồi re-encode, giúp chống nhiều kiểu file giả dạng và loại bớt metadata/raw payload không mong muốn, nhưng vẫn **không phải sandbox hoặc antivirus**. Image decoder có thể có CVE; compressed input nhỏ vẫn có thể gây áp lực decode; với loại file có nguy cơ cao, dùng process isolation, patched codec, sandbox/AV/CDR và resource quotas mạnh hơn. `MAX_INPUT_BYTES` giới hạn file raw; `MAX_DIMENSION` và `MAX_PIXELS` giới hạn pixel count; không thay thế OS-level memory/CPU limits.

**Chi tiết lưu trữ:** `Files.createTempDirectory` sinh thư mục riêng ngoài static resources; `Files.createTempFile` sinh tên server-controlled, không bao giờ dùng `MultipartFile.getOriginalFilename()`. `saved` chỉ là in-memory map — restart sẽ mất mapping, file tạm có thể không được dọn và không có retention management. Khi triển khai thật phải thay bằng metadata DB/storage service và cleanup/quota theo chính sách.

**Chi tiết tải xuống:** response là `attachment` với tên cố định, MIME được chuẩn hóa và `nosniff`. Không cho browser tự quyết định render original HTML/SVG đã upload. Ở production bắt buộc có auth/authorization trên **cả upload lẫn download**, kiểm tra owner/tenant và trạng thái scan.

### 9.3. Chạy thử bằng curl

```bash
./gradlew bootRun
```

Chuyển tới trang được phép (dùng `-i` để xem 303 thay vì tự theo redirect):

```bash
curl -i -X POST \
  'http://localhost:8080/navigation/continue' \
  --data 'destination=dashboard'
```

Kỳ vọng status `303 See Other` và `Location: /portal/dashboard`.

Thử external redirect do client đề nghị:

```bash
curl -i -X POST \
  'http://localhost:8080/navigation/continue' \
  --data-urlencode 'destination=https://outside.example/collect'
```

Kỳ vọng `400 Bad Request`, **không có `Location` do attacker kiểm soát**.

Upload ảnh PNG hợp lệ (file phải thực sự là PNG):

```bash
curl -i -X POST \
  'http://localhost:8080/api/images' \
  -F 'file=@avatar.png;type=image/png'
```

Nếu ảnh dưới 256 KiB, kích thước không vượt 1024×1024 và decoder đọc được, server dự kiến trả `201 Created`, `Location: /api/images/<uuid-thực>` và body JSON chứa ID. Dấu `<uuid-thực>` là placeholder hướng dẫn, không phải ID được dự đoán trước.

Theo URL `Location` nhận được:

```bash
curl -i 'http://localhost:8080/api/images/<uuid-thực>'
```

Kết quả dự kiến: `200 OK`, `Content-Type: image/png`, `Content-Disposition: attachment; filename="image.png"`, `X-Content-Type-Options: nosniff` và PNG đã chuẩn hóa. Với `curl -o downloaded.png`, dùng đúng URL lấy từ 201.

Thử đổi tên một file text thành `avatar.png`: endpoint sẽ từ chối nếu ImageIO không giải mã nó thành PNG hợp lệ. Nếu gửi ảnh quá lớn, lớp multipart có thể chặn từ trước controller; error status/body cụ thể phụ thuộc exception/error handling và container. Dữ liệu demo không được coi là đã trải qua quét mã độc.

## 10. Integration tests với MockMvc

Tạo **`src/test/java/demo/safeweb/SafeWebApplicationTests.java`**:

```java
package demo.safeweb;

import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeWebApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void knownDestinationRedirectsToInternalRoute()
            throws Exception {

        mvc.perform(post("/navigation/continue")
                .param("destination", "dashboard"))
            .andExpect(status().isSeeOther())
            .andExpect(header().string(
                    HttpHeaders.LOCATION, "/portal/dashboard"));
    }

    @Test
    void externalDestinationIsRejectedWithoutLocation()
            throws Exception {

        MvcResult result = mvc.perform(post("/navigation/continue")
                .param("destination",
                        "https://outside.example/collect"))
            .andExpect(status().isBadRequest())
            .andReturn();

        assertNull(result.getResponse()
                .getHeader(HttpHeaders.LOCATION));
    }

    @Test
    void protocolRelativeDestinationIsRejected()
            throws Exception {

        mvc.perform(post("/navigation/continue")
                .param("destination", "//outside.example/path"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void actualPngIsNormalizedAndDownloaded()
            throws Exception {

        BufferedImage small =
                new BufferedImage(2, 2, BufferedImage.TYPE_INT_RGB);

        ByteArrayOutputStream output = new ByteArrayOutputStream();
        assertTrue(ImageIO.write(small, "png", output));

        // Client-controlled filename is deliberately suspicious.
        MockMultipartFile file = new MockMultipartFile(
                "file", "../../private-config.yml",
                "application/octet-stream", output.toByteArray());

        MvcResult uploaded = mvc.perform(
                multipart("/api/images").file(file))
            .andExpect(status().isCreated())
            .andReturn();

        String location = uploaded.getResponse()
                .getHeader(HttpHeaders.LOCATION);

        assertNotNull(location);
        assertTrue(location.matches(
                "/api/images/[0-9a-fA-F-]{36}"));

        mvc.perform(get(location))
            .andExpect(status().isOk())
            .andExpect(content()
                    .contentTypeCompatibleWith(MediaType.IMAGE_PNG))
            .andExpect(header().string(
                    "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                    HttpHeaders.CONTENT_DISPOSITION,
                    "attachment; filename=\"image.png\""));
    }

    @Test
    void fakePngBytesAreRejected() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "image.png", "image/png",
                "not a png".getBytes(java.nio.charset.StandardCharsets.UTF_8));

        mvc.perform(multipart("/api/images").file(file))
            .andExpect(status().isBadRequest());
    }

    @Test
    void oversizedFileIsRejectedAtApplicationLayer()
            throws Exception {

        MockMultipartFile file = new MockMultipartFile(
                "file", "large.png", "image/png",
                new byte[256 * 1024 + 1]);

        mvc.perform(multipart("/api/images").file(file))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unknownImageIdReturns404() throws Exception {
        mvc.perform(get("/api/images/"
                + "00000000-0000-0000-0000-000000000000"))
            .andExpect(status().isNotFound());
    }
}
```

Chạy:

```bash
./gradlew test
```

Với code Boot 3.5/JDK ImageIO như trên, bảy bài test được **thiết kế để pass**. Đây là kết quả kỳ vọng sau rà soát, **chưa phải output của một lần chạy thực tế**. `MockMvc` không kiểm tra permission của OS filesystem, proxy max body size, nhiều nodes, upload quotas, antivirus/CDR hay log pipeline; cần thêm integration/security/penetration tests tương ứng.

Mục đích test:

- Redirect không nhận full URL hoặc `//host`.
- Upload body phải là PNG đọc được, không chỉ tự khai `Content-Type: image/png`.
- Upload dùng filename bất thường vẫn lưu dưới tên generated và không ghi đè file đích do người dùng chỉ định.
- Download trả MIME/cách xử lý attachment đã được server chọn.
- Trường hợp input size vượt giới hạn trong MockMvc bị controller từ chối.
- Không có bằng chứng nào cho phép kết luận demo đã có **user authorization**, malware scanning hay storage hardening production.

## 11. Những yêu cầu chưa thể bỏ qua ở production upload

### 11.1. Authentication, authorization và ownership

- Chỉ người dùng đủ quyền mới upload.
- Mỗi file record cần owner/tenant, trạng thái scan/quarantine, MIME chuẩn hóa, size, storage key, creation time và retention policy.
- Download kiểm tra quyền **mỗi lần**, kể cả khi biết UUID.
- Tránh IDOR/BOLA: client thay `/api/images/{id}` sang ID người khác không được nhận file.
- Với file public, dùng public object storage/CDN có content rules; với file riêng, dùng signed URL ngắn hạn hoặc download proxy đã xác thực.
- Signed URLs có thời hạn và scope cũng là **credentials**; không ghi nguyên chúng vào logs hoặc referrers.

### 11.2. Antivirus/sandbox và content disarm

Một PNG re-encode không đảm bảo decoder không có lỗi bảo mật hoặc image không mang payload nguy hiểm. Với PDF, DOCX, ZIP, SVG hoặc các định dạng hỗ trợ active content, cần xử lý chuyên biệt:

| Loại file | Ví dụ kiểm soát bổ sung |
| --- | --- |
| PNG/JPEG | Safe decoder, giới hạn pixels/dimensions, strip metadata, re-encode, image-library patching |
| SVG | Không coi là ảnh vô hại; script/links có thể tồn tại; cấm hoặc sanitize nghiêm ngặt và serve isolated |
| PDF | Type/content scanner, sandbox/CDR nếu cần, attachment hoặc isolated viewer |
| DOCX/XLSX | CDR/macro policy, AV scan, không preview trực tiếp mà thiếu sandbox |
| ZIP/TAR | Giới hạn file count, nested depth, decompressed size, chống zip-slip/symlink |
| HTML/JS | Không lưu/serve ở cùng authenticated origin nếu không có isolation phù hợp |
| Executable | Mặc định không cho upload hoặc chỉ trong workflow có kiểm soát chuyên biệt |

Không “chỉ kiểm tra magic bytes” rồi mở PDF/Office/ZIP không giới hạn; parser và preview engine cũng là bề mặt tấn công.

### 11.3. Transaction, consistency và cleanup

- Nếu scan async, đừng công khai file khi trạng thái còn `PENDING`; trả job/upload status theo contract.
- Nếu DB record được tạo nhưng object upload thất bại (hoặc ngược lại), cần rollback/compensation/cleanup.
- Cần quotas theo user/tenant, max object count, max daily bytes, lifecycle TTL, retention/deletion compliance.
- Dùng key do server sinh, avoid collisions/overwrites; với object store chọn write semantics và bucket permissions phù hợp.
- Quản lý tmp files do multipart parser và application tạo; không để file tạm tích tụ vô hạn.
- Cấu hình antivirus/decoder timeouts, memory/CPU/file descriptor limits và separate processing workers.
- Re-encoding ảnh có thể thay đổi màu/alpha/metadata; xác nhận output phù hợp hợp đồng sản phẩm.

## 12. Thông tin nhạy cảm trong log: những gì không nên ghi

OWASP Logging Cheat Sheet liệt kê các loại thường không được log trực tiếp hoặc phải mask/sanitize/hide:

| Dữ liệu | Rủi ro khi xuất hiện trong log | Cách xử lý |
| --- | --- | --- |
| `Authorization: Bearer <token>` | Token có thể bị tái sử dụng | Không ghi token; nếu cần, log kết quả auth và event ID |
| `Cookie` / `Set-Cookie` / `JSESSIONID` | Session hijacking | Loại bỏ hoàn toàn session ID khỏi log |
| Password, OTP, reset token, private key | Lộ credentials | Không log và không phản hồi raw |
| OAuth code, signed URL, API key | Chiếm quyền hoặc truy cập file | Redact token và query parameters |
| Raw JSON/form body | Có thể chứa PII/password, dữ liệu tài chính | Tránh log body; log validated metadata theo allowlist |
| Multipart filename, bytes, document text | Có thể chứa PII, newline injection, malware payload | Không log nguyên bản; server-generated ID thay thế |
| Email, số điện thoại, địa chỉ, ID giấy tờ | Privacy/compliance impact | Chỉ log khi thật cần và theo pháp lý/policy, dùng pseudonymization phù hợp |
| Full exception message/stack trace | Có thể chứa SQL, paths, input, secrets | Sanitize, phân loại lỗi; log stack có kiểm soát và retention |
| Full URL/query/referrer | Query có thể mang token/password | Log route template, bỏ hoặc whitelist query keys |
| Raw IP, User-Agent | PII hoặc untrusted data | Tùy threat model, tuân thủ policy và sanitize |

**Không có quy tắc “mọi log đều phải trống”**. Security event logs vẫn hữu ích để phát hiện tấn công, nhưng chỉ nên ghi fields có mục đích, được phân loại theo độ nhạy cảm, có quyền truy cập và thời hạn lưu rõ.

### 12.1. Parameterized logging không phải redaction

Không nên:

```java
// Anti-pattern: log raw password và token.
log.info("Login user={} password={} token={}",
        request.getParameter("user"),
        request.getParameter("password"),
        request.getHeader("Authorization"));
```

Dạng an toàn hơn:

```java
// Fragment: dữ liệu đã được chọn theo chính sách.
log.info("login_attempt result={} authMethod={} requestId={}",
        "rejected", "password", trustedRequestId);
```

Ở đây `trustedRequestId` phải do server tạo hoặc validate nghiêm ngặt từ hạ tầng tin cậy. Không đổi sang `log.info("userInput={}", rawInput)` rồi cho rằng placeholder tự loại bỏ CR/LF; nó **không phải bộ lọc nội dung**.

### 12.2. Log injection / log forging

Một trường request có thể chứa ký tự xuống dòng nhằm tạo bản ghi giả:

```text
Input malicious (mô phỏng):
  queryName = "Alice\r\n2026-01-01 ERROR admin-login-success"

Nếu log nối trực tiếp:
  INFO queryName=Alice
  2026-01-01 ERROR admin-login-success
```

Log reader, SIEM hoặc parser theo dòng có thể hiểu nhầm dòng thứ hai là event độc lập. Các dấu phân cách `,`, `|`, tabs, JSON quotes/control characters cũng gây vấn đề nếu format không encode đúng.

Biện pháp:

- Ưu tiên **structured JSON logging** bằng serializer đúng, không tự nối text thành JSON.
- Nếu bắt buộc log dữ liệu client ở field cho phép, **sanitize CR/LF/control characters, escape theo sink**, giới hạn độ dài và giá trị.
- Đối với User-Agent/referer/filename, cân nhắc log **classification** hoặc hash/tokenization phù hợp thay vì raw text.
- Không tắt log security events cho IP/users “đã tin cậy”; tránh bỏ qua attacker đã đăng nhập.
- Log record có timestamps/IDs từ hệ thống tin cậy, không lấy nguyên timestamp do client đưa.
- Giữ logs trong destination có quyền truy cập hạn chế và cơ chế chống sửa/xóa/tamper; SIEM có retention/alert thích hợp.

Một helper tối thiểu nếu thực sự cần log chuỗi không tin cậy:

```java
static String safeLogField(String value) {
    if (value == null) {
        return "missing";
    }

    StringBuilder out = new StringBuilder();
    int limit = Math.min(value.length(), 120);

    for (int i = 0; i < limit; i++) {
        char c = value.charAt(i);
        if (Character.isISOControl(c)) {
            out.append('_');
        } else {
            out.append(c);
        }
    }
    return out.toString();
}
```

Đây là **method fragment** chỉ minh họa chuẩn hóa control characters và giới hạn ký tự. **Nó không tự phát hiện secrets/PII và không thay thế escaping theo JSON/XML/log sink**. Không dùng helper này để “hợp pháp hóa” việc log password/token — những dữ liệu đó phải **không được ghi**.

## 13. Log theo route template, không lặp lại raw request URL

Ví dụ với endpoint:

```text
POST /api/images?access_token=SECRET
Authorization: Bearer SECRET
Cookie: JSESSIONID=SECRET
```

Không ghi full URI, query string, raw headers. Một bản ghi hữu ích và ít nhạy cảm hơn:

```text
event=image_upload_saved requestId=<server-generated-id>
resourceId=<uuid> result=created outputBytes=1132
```

**Các giá trị ở trên là ví dụ**, không phải log của chương trình đã chạy. Nếu cần phân tích hiệu suất, dùng route template `/api/images`, HTTP status, duration bucket, bytes count; không đưa file bytes hay filename gốc vào tracing spans.

### 13.1. Tạo correlation ID đúng cách

Nếu cần request correlation ID, phương án đơn giản là server tạo UUID khi request vào, đặt trong MDC rồi **dọn `finally`** khi filter kết thúc:

```java
@Component
class RequestIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        String requestId = UUID.randomUUID().toString();
        MDC.put("requestId", requestId);
        try {
            response.setHeader("X-Request-Id", requestId);
            chain.doFilter(request, response);
        } finally {
            MDC.remove("requestId");
        }
    }
}
```

Đây là **class fragment độc lập**, cần imports Jakarta Servlet, `@Component`, `OncePerRequestFilter`, `MDC`, `UUID`. Không tự thêm vào project demo nếu không cần; nếu thêm, cấu hình registration/order sao cho server-generated request ID có mặt ở các nơi mong muốn.

Với async/multi-thread request, MDC **không tự động đi theo thread**. Cần context propagation strategy và cleanup theo từng thread/dispatch khi có nghiệp vụ thực sự cần. Không giữ `HttpServletRequest`/token dưới dạng ThreadLocal toàn thời gian.

Nếu chấp nhận request ID từ proxy, chỉ tin proxy đã cấu hình, giới hạn charset/length và chống CRLF injection. Nếu không chắc nguồn tin cậy, sinh ID mới trong application.

## 14. Log levels, filter, Spring Boot và phạm vi cấu hình

Trong Boot 3.5 có:

```properties
spring.mvc.log-request-details=false
logging.level.org.springframework.web=INFO
```

Điều này giúp hạn chế một số debug/trace request details của MVC, nhưng **không bảo đảm log hoàn toàn không có dữ liệu nhạy cảm**.

Cần kiểm tra thêm:

- Application logger do developer viết (`log.info/debug/error`).
- Spring Security authentication/authorization logs.
- Servlet container access logs; pattern có thể chứa URL/query, cookies hoặc headers.
- API gateway/reverse proxy/WAF request logs.
- Distributed tracing/APM auto instrumentation (span tags/header capture).
- Exception reporting/Sentry/crash dumps.
- CI/build deployment logs có env vars/secrets.
- Message queue/integration adapters có log request/response bodies.
- Central logging platform: who can access it, encryption at rest/in transit, retention, deletion/incident response.

**Không bật `TRACE` của toàn framework trong production** khi không có chính sách masking phù hợp. Với sự cố khẩn cấp cần debug, sử dụng flag/tài khoản có thời hạn, mục tiêu tối thiểu, rồi tắt và xử lý log đã thu theo retention/privacy requirements.

### 14.1. Chỉ log lỗi mà không lộ exception input

Không nên:

```java
// Anti-pattern nếu ex.getMessage() chứa raw request/token/SQL.
log.error("Upload failed, filename={}, cause={}",
        file.getOriginalFilename(), ex.getMessage(), ex);
```

Nên:

```java
log.warn("image_upload_rejected reason={} requestId={}",
        "invalid_format", trustedRequestId);
```

Chỉ log exception stack khi có lý do vận hành và đã đánh giá nó không chứa secrets; nếu cần stack trong sink nội bộ, bảo vệ sink đó kỹ hơn public logs và không đưa thẳng message vào HTTP error body.

## 15. Spring Security và CORS liên quan thế nào?

### 15.1. CORS không chống open redirects hoặc file upload độc hại

CORS là một cơ chế browser để quyết định web page **cross-origin** có được đọc response hay không. Nếu browser được người dùng yêu cầu điều hướng tới `https://outside.example` qua Location, CORS policy trên JSON API không phải “bức tường” ngăn redirect.

Tương tự, một client ngoài browser có thể gọi multipart endpoint nếu mạng và auth cho phép, **dù `Access-Control-Allow-Origin` không cho phép domain nào**. CORS không phải authentication.

### 15.2. CSRF vẫn quan trọng

Nếu upload endpoint và navigation endpoint dùng **cookie session authentication** và làm thay đổi server state, cần CSRF protection tùy kiến trúc. JavaScript/browser từ site khác có thể gửi một số dạng form requests cross-origin dù không đọc được response. Khi có Spring Security, cấu hình `SecurityFilterChain` theo endpoint và thêm CSRF token cho HTML form hoặc giải pháp phù hợp cho SPA.

Không tắt CSRF toàn ứng dụng chỉ để multipart example test pass. Demo không có Spring Security để giữ scope rõ; production cần xác thực, phân quyền, CSRF, rate limit, tenant isolation và content-type policies.

### 15.3. Response security headers

Những headers thường có ích khi phục vụ dữ liệu do người dùng tải lên:

| Header | Mục đích |
| --- | --- |
| `Content-Type` đúng loại đã kiểm chứng | Browser biết media type thật |
| `X-Content-Type-Options: nosniff` | Giảm một số kiểu MIME sniffing |
| `Content-Disposition: attachment` | Giảm khả năng browser render active content inline |
| `Cache-Control: no-store` / private | Giới hạn cache dữ liệu riêng |
| `Content-Security-Policy` | Hạn chế nguồn script/resource ở origin/view liên quan |
| `Referrer-Policy` | Giảm tiết lộ đường dẫn/query tới bên ngoài |
| `Strict-Transport-Security` trên HTTPS | Buộc HTTPS cho domain khi được triển khai đúng |

**Không có header đơn lẻ nào cho phép bỏ content validation.** Ví dụ serve raw SVG/HTML từ origin đang có session cookies có thể mang rủi ro rất khác serve PNG đã chuẩn hóa dưới dạng attachment.

## 16. Nếu cần download filename do người dùng đặt

Tình huống thường gặp: sản phẩm muốn trình duyệt tải file theo tên hiển thị do user chọn. Tránh ghép trực tiếp raw filename vào HTTP header:

```java
// Anti-pattern: CR/LF, quote hoặc ký tự lạ trong name gây rủi ro.
response.setHeader(
        "Content-Disposition",
        "attachment; filename=\"" + originalFilename + "\"");
```

Tốt hơn:

1. Lưu tên hiển thị riêng trong metadata DB, có validation về Unicode, length, control chars và policy.
2. Sinh storage filename độc lập, tuyệt đối không dùng display name làm path.
3. Khi trả header, dùng **Spring `ContentDisposition` builder** có xử lý encoding/quoting phù hợp, không tự nối chuỗi header thô.
4. Với loại nguy hiểm, ép download filename/extension an toàn từ media type đã xác minh, không tin ext gốc.
5. Nếu không cần tên gốc, luôn dùng một tên cố định như demo `image.png`.

Fragment:

```java
ContentDisposition disposition =
        ContentDisposition.attachment()
                .filename(safeDisplayName, StandardCharsets.UTF_8)
                .build();

return ResponseEntity.ok()
        .header(HttpHeaders.CONTENT_DISPOSITION,
                disposition.toString())
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .body(fileBytes);
```

Đây là fragment trong handler, cần import `ContentDisposition`, `StandardCharsets`, `HttpHeaders` và khai báo `safeDisplayName`/`fileBytes`. **Builder không thay thế business allowlist nội dung**; `safeDisplayName` phải được kiểm tra và giới hạn trước đó. `Content-Type: application/octet-stream` không phải lựa chọn tối ưu cho mọi định dạng; tùy trường hợp và mục tiêu download.

## 17. Error handling và không tạo thông tin rò rỉ

Một lỗi invalid upload nên trả error body ngắn, ổn định:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Invalid image",
  "status": 400,
  "detail": "The uploaded file is not an accepted PNG image"
}
```

Đây là **schema minh họa**, không mặc định mọi Boot app tự trả đúng body trên. Với Spring Framework 6+, `ProblemDetail`/`@RestControllerAdvice` có thể thống nhất lỗi; tránh đưa exception message nội bộ như `/tmp/...`, raw filename, parser stack trace vào response.

Nên phân loại:

| Tình huống | Status thường phù hợp |
| --- | --- |
| Redirect token không được hỗ trợ | `400 Bad Request` |
| Uploaded content không phải PNG hợp lệ | `400 Bad Request` hoặc `415 Unsupported Media Type` theo API contract |
| File/request vượt giới hạn | `413 Content Too Large` (tùy version dùng tên `Payload Too Large`) |
| Chưa xác thực upload/download | `401 Unauthorized` |
| Có xác thực nhưng không đủ quyền | `403 Forbidden` |
| File ID không có/không được tiết lộ | `404 Not Found` khi phù hợp |
| Scanner/storage không sẵn sàng | `503 Service Unavailable` hoặc status theo tình huống |
| Upload đã chấp nhận nhưng đang scan async | `202 Accepted` |
| Upload đã xử lý tạo thành công | `201 Created` |

Không hardcode mọi lỗi thành `200 OK` với `{"success":false}`. HTTP status giúp client và monitoring phân biệt lỗi. Không đặt raw user text làm `ProblemDetail.detail` nếu nó có thể lộ token hoặc nội dung nhạy cảm.

## 18. Triển khai sau reverse proxy, gateway, CDN

Một hệ thống thực tế có nhiều nơi diễn giải URL, body và log:

```text
Browser
   |
CDN/WAF
   |
Reverse Proxy/API Gateway
   |
Servlet container (Tomcat...)
   |
Spring Security FilterChain
   |
Spring MVC controller
   |
Private object storage / scanner
   |
Central log/metrics/tracing
```

Các kiểm tra phải nhất quán:

- **Redirect:** Gateway/proxy có thể chuẩn hóa path, scheme, host; đừng tin `Host`/`X-Forwarded-Host` do client tự gửi khi dựng external URL. Chỉ tin proxy headers từ nguồn đáng tin.
- **Upload limits:** Proxy, connector, multipart parser, app validator và object-store limits đều phải có policy nhất quán; request quá lớn có thể bị chặn trước khi vào controller.
- **Storage:** Shared object storage có bucket ACL, encryption, retention, quarantine, signed URL policy; không expose trực tiếp private key.
- **Logs:** Proxy/CDN có thể log full URL/query/cookie trước khi Spring thấy request; phải cấu hình masking ngay tại tầng đó.
- **Cache:** Tránh public CDN caching cho private download. Signed URLs là credentials, cần short TTL và log redaction.
- **Incident response:** Theo dõi số lượng rejected redirects/uploads, scan failures, anomalous rates và log injections, nhưng không lưu raw malicious payload hoặc secrets trong event feed.

### Có nên tự gọi URL mà client đưa để “xác nhận an toàn”?

Không nên. Nếu server tự thực hiện HTTP GET tới `next` để kiểm tra đích, có thể phát sinh **SSRF**: attacker trỏ tới internal addresses, cloud metadata hoặc DNS rebinding targets. Chống open redirect bằng validation/policy trên cấu trúc URL và mapping, **không fetch URL tùy ý**.

## 19. Security testing: thử cả đường hợp lệ và đường bị chặn

### Redirect

- `destination=dashboard` → 303, `Location` đúng local path.
- `destination=help` → 303, local path khác.
- URL tuyệt đối HTTP(S) → 400, không Location external.
- `//outside.example` → 400.
- URL chứa userinfo, backslash, percent-encoded slashes, CRLF → 400.
- Destination thiếu/unknown → 400 theo API contract.
- Nếu có external partner redirect thực, test exact origin/scheme/port/host/path, URL normalize và redirect chain.
- Kiểm tra status 302/303/307/308 theo body/method forwarding semantics.

### Upload

- PNG hợp lệ, kích thước trong giới hạn → 201, ID server sinh, download đúng PNG.
- JPEG/GIF/SVG/HTML/TXT ngụy trang bằng header `image/png` → reject nếu policy PNG-only.
- PNG file với filename `../secrets.txt` → không tạo path do user điều khiển; storage name generated.
- PNG decompression bomb (metadata dimensions lớn) → reject trước full decode khi có thể.
- File rỗng/too large, quá nhiều parts, tên quá dài, multipart boundary malformed → reject/bounded.
- Multipart POST từ user không có quyền → 401/403 khi Security bật.
- Biết UUID của người khác → 403/404 theo disclosure policy.
- Uploaded file chưa scan → không truy cập được bản public.
- Test storage permission, cleanup, quota/rate limit, scanning timeout và concurrent writes.

### Logging

- Đưa CRLF vào User-Agent/filename/query → không tạo log event giả.
- Đưa token/email/password vào body/query → không xuất hiện trong application logs, access logs và APM spans trừ policy được kiểm duyệt.
- Lỗi validation không log rejected sensitive values.
- Error stack trace không xuất hiện trong HTTP response.
- Tracing correlation ID luôn server-generated hoặc validated, không chứa ký tự bất thường.
- Chỉ role vận hành được phép đọc logs, retention và deletion policy được thi hành.

**Không chỉ test rằng API status là 400 hoặc 201**; phải kiểm tra chính các hiệu ứng phụ: header Location, file bytes, file placement và log records.

## 20. Lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Domain đáng tin redirect sang site lạ | Dùng `redirect:` + untrusted URL | Chọn route mã đích allowlist |
| App kiểm tra domain bằng `startsWith` nhưng bị bypass | Userinfo, subdomain suffix, IDN, encoded URL | Exact canonical URI policy hoặc partner ID |
| `setRedirectHosts` đã dùng nhưng vẫn redirect ngoài | Hiểu nhầm API encodeURL thành security validator | Validate business destination trước khi redirect |
| Avatar PNG thực ra là HTML | Tin `getContentType()` hoặc extension | Decoder/format validation, normalized output |
| Upload overwrite file server | Tin original filename/path | Random storage name, private directory |
| Ảnh nhỏ khiến OOM khi decode | Compressed dimensions cực lớn | Pixel limits, size limits, sandbox |
| User đoán UUID và tải tài liệu người khác | Chỉ kiểm tra file ID, không owner | Authorization/tenant checks |
| PDF/SVG tải lên gây script execution | Serve inline từ authenticated origin | Cấm/sanitize/CDR, attachment/isolated origin |
| Disk đầy sau thời gian | Không quota/cleanup/retention | Background lifecycle/metrics, storage policy |
| Log chứa JWT sau bật DEBUG | Raw request/headers logged | Redaction policy mọi tầng, tắt request detail |
| Log xuất hiện dòng ERROR giả | CRLF/log injection | Structured encoding, bounded allowlist fields |
| APM vẫn giữ query token dù app logger sạch | Instrumentation capture URL/query | Sanitize ở tracing/gateway config |
| Redirect sau POST bị mất/forward body | Nhầm 303 với 307/308 | Chọn status theo nghiệp vụ, cấm external target |
| Test MockMvc pass nhưng proxy vẫn nhận payload lớn | Chỉ test MVC layer | HTTP integration từ gateway/container |
| Download có `nosniff` nhưng vẫn lộ PII | Không xác thực hoặc public cache | Auth/authorization + private/no-store |
| Files được scan nhưng vẫn chứa mã độc | Scanner có giới hạn/signature thiếu | Defense in depth, sandbox/CDR, updates |

## 21. Khác biệt phiên bản Spring Boot / Spring Framework

| Nền tảng | Điều cần kiểm tra |
| --- | --- |
| Spring Framework 5.x / Boot 2.x | Servlet API thường `javax.servlet.*`; MultipartFile/RedirectView vẫn tồn tại; error response khác 6.x |
| Spring Framework 6.x / Boot 3.x | Java 17+, `jakarta.servlet.*`, `ProblemDetail`; properties `spring.servlet.multipart.*` và `spring.mvc.log-request-details` như ví dụ |
| Spring Framework 7.x / Boot 4.x | API web/security còn nhưng một số modules/starter/JSON/test packages đổi; kiểm tra migration guide, properties metadata và component registrations |

**Không bê code `javax.servlet.*` từ Boot 2 vào Boot 3/4**. ImageIO là Java SE và hoạt động với JDK17+, nhưng cần đảm bảo thư viện ảnh/JDK modules trong custom runtime. Khi dùng native image, phản xạ/codec/resource support phải được test riêng.

Spring Security 6/7 xử lý authentication, authorization, CSRF, headers và session theo SecurityFilterChain; các endpoint trong demo **không tự có chúng** chỉ vì dependency `spring-boot-starter-web`. Sử dụng Security starter + cấu hình policy riêng nếu muốn chạy production.

## 22. Checklist trước khi đưa ứng dụng web lên production

- [ ] Không có redirect target xây từ raw `next`/`returnUrl`. Internal routes dùng mã allowlist; external partners do config kiểm soát.
- [ ] Destination policy kiểm soát scheme/host/port/path/canonicalization nếu thực sự cần external redirect.
- [ ] OAuth/OIDC callback URI/state/PKCE được validate theo protocol, không nhầm với generic redirect.
- [ ] Upload type allowlist có business owner, giới hạn file/request size và max concurrency.
- [ ] Không tin `originalFilename` và `Content-Type`; xác minh bytes/parser, kiểm soát giải nén và re-encode/CDR khi phù hợp.
- [ ] Có AV/sandbox/quarantine policy cho loại dữ liệu cần thiết; không public trước scan completion.
- [ ] Storage ngoài public webroot, opaque generated key, không traversal/symlink/overwrite.
- [ ] Upload/download đều có authentication/authorization, quota, CSRF nếu cookie sessions.
- [ ] Download headers `Content-Type`/`Content-Disposition`/`nosniff`/cache được chọn bởi server.
- [ ] Không lưu raw password/token/cookie/signed URL/PII hay multipart body vào logs.
- [ ] Log events có allowlisted fields, escaping control chars, size limits, structured format.
- [ ] Gateway/container/HTTP client/APM/SIEM cũng có log redaction và retention policy.
- [ ] HTTP error body không chứa stack trace, filesystem paths, SQL hay secrets.
- [ ] Có tests cho malicious redirect, upload disguise/size/metadata, unauthorized download, log injection.
- [ ] Đã xác định lifecycle/cleanup/retention của uploaded objects và incident-response process.
- [ ] Có quan sát metrics bảo mật theo event count/status mà không thu dữ liệu nhạy cảm.

## 23. Bài tập và câu hỏi tự đánh giá

1. Vì sao `return "redirect:" + next` trong Spring MVC là open redirect nếu `next` đến từ request? `RedirectView#setHosts` có thay thế validator domain hay không?
2. Một URL `https://portal.example.attacker.example` qua được kiểm tra `startsWith("https://portal.example")`. Viết thiết kế lại bằng partner ID hoặc exact URI policy.
3. So sánh 302, 303, 307, 308 khi client gửi POST chứa body nhạy cảm. Khi nào 307/308 nguy hiểm nếu đích do attacker chọn?
4. Nếu file `avatar.png` chứa bytes HTML nhưng header `image/png`, điều gì sẽ xảy ra khi API chỉ kiểm tra extension/MIME? Bổ sung decoder validation.
5. Vì sao `Files.createTempFile(privateRoot,"image-",".png")` an toàn hơn `privateRoot.resolve(file.getOriginalFilename())`? Nó chưa giải quyết các rủi ro gì?
6. Một compressed PNG nhỏ chứa kích thước 80.000×80.000 pixel. Vì sao giới hạn upload 256 KiB chưa đủ? Cần giới hạn trước/bên trong decoder như thế nào?
7. Người dùng không biết UUID của người khác nhưng vẫn có thể đoán/brute force hoặc có link leak. Vì sao download vẫn cần authorization?
8. Ứng dụng cho upload SVG rồi serve inline cùng cookie-authenticated origin. Những rủi ro nào xuất hiện và nên đổi cách serve/allowlist ra sao?
9. Input User-Agent chứa ký tự CR/LF khiến log có dòng WARNING giả. Đề xuất structured logging, escaping, max length và kiểm thử.
10. Nếu có `spring.mvc.log-request-details=false` nhưng proxy ghi full query chứa token, vấn đề còn không? Ai chịu trách nhiệm redaction?
11. Thêm một test mock multipart với original filename `../../passwords.txt` và body PNG hợp lệ. Vì sao test không nên assert file được lưu dưới tên đó?
12. Thiết kế scan bất đồng bộ với `202 Accepted`, trạng thái `PENDING/SAFE/REJECTED` và quyền download; giải thích khi nào file được phép xuất bản.
13. Khi Spring Security dùng cookie authentication, CORS có ngăn cross-origin form POST gây CSRF không? Cần những lớp nào?
14. Nêu lý do không log raw `Exception#getMessage()` cho mọi lỗi parse multipart/body, và cách phân loại lỗi an toàn.
15. Viết checklist kiểm tra uploads và logs trên 3 môi trường: local Boot app, staging sau gateway và production dùng object storage.

## 24. Tài liệu tham khảo chính thức

- [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): allowlist destinations, tránh raw return URL.
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): extension/MIME validation, storage isolation, AV/CDR, permissions và CSRF.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu không nên ghi, log injection, event collection, integrity.
- [OWASP — Cross-Site Request Forgery Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF khi dùng cookie sessions và state-changing requests.
- [Spring Framework 6.2 — RedirectView API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/view/RedirectView.html): redirect URLs, contextRelative và redirect hosts semantics.
- [Spring Framework 6.2 — Multipart Support](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/multipart.html): multipart parsing, MultipartFile và MVC Servlet.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.servlet.multipart.max-file-size`, `max-request-size`, `spring.mvc.log-request-details`.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): request protection, cookie/session flows.
- [Spring Framework 6.2 — ResponseEntity](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/ResponseEntity.html): explicit redirect/create status and headers.
- [Java 17 — ImageIO](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/javax/imageio/ImageIO.html): image format decoder/encoder primitives; security resource limits remain application responsibility.
