# Upload, download và trách nhiệm kiểm soát dữ liệu theo từng lớp

## Mục tiêu học tập

Sau bài học trong chương **Tích hợp ứng dụng**, người học có thể:

- Mô tả luồng **upload/download** qua client, reverse proxy, Spring Security, multipart parser, controller, service, scanner, metadata database và storage; xác định trách nhiệm từng lớp.
- Phân biệt **authentication, CSRF, CORS, object-level authorization, content validation, malware scanning, resource quotas** và bảo vệ response cho browser.
- Thiết kế file lifecycle **quarantine → scanning → available/rejected**, tên lưu trữ do server tạo, nội dung kiểm chứng được, metadata theo tenant và cleanup khi thất bại.
- Ngăn các lỗi **path traversal, BOLA/IDOR, ZIP bomb, Zip Slip, MIME spoofing, stored XSS, SSRF trong xử lý file, symlink/TOCTOU** và rò rỉ thông tin qua CDN/cache hoặc presigned URL.
- Triển khai mẫu Spring **Servlet/Spring MVC** và **Reactive/WebFlux** cho multipart và download streaming, xử lý file lớn không giữ toàn bộ payload trong heap hoặc block event loop.
- Dùng đúng **Content-Disposition, Content-Type, X-Content-Type-Options, CSP, HSTS, Content-Length, Range, Cache-Control**, cookie security và TLS theo hợp đồng từng endpoint.
- Kiểm thử bằng **MockMvc**, **WebTestClient**, integration tests và browser E2E: file hợp lệ/không hợp lệ, thiếu CSRF, sai principal/tenant, file chưa scan, response headers, multipart limits và nhiều user.
- Chẩn đoán lỗi `401`, `403`, `404`, `413`, `415`, `422`, `429`, `502` theo tầng HTTP đã gây lỗi.

## 1. Tại sao upload/download là bài toán bảo mật?

Một HTTP POST nhận file không phải chỉ là “gọi `MultipartFile.transferTo`”, và một HTTP GET download không phải chỉ là “đọc đường dẫn file được truyền qua URL”. Dữ liệu upload **do phía không tin cậy kiểm soát**, có thể được lưu bền vững, được ứng dụng đọc/giải nén, và cuối cùng được browser hoặc phần mềm bên ngoài mở.

Ví dụ request upload trong browser đã đăng nhập:

~~~http
POST /api/files HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=opaque-session-id
X-CSRF-TOKEN: token-issued-for-session
Content-Type: multipart/form-data; boundary=----example

------example
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

<bytes-of-file>
------example--
~~~

**Cả ba thứ** `filename="report.pdf"`, `Content-Type: application/pdf` của part và **bytes** đều có thể do attacker tự đặt. Authentication chỉ chứng minh ai gửi request, **không chứng minh** file đúng loại, an toàn khi parser mở, đủ quota hay có quyền liên kết với hồ sơ của user khác.

Ví dụ download:

~~~http
GET /api/files/9f93c766-138b-4440-a344-9f6d94114ca3/download HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=opaque-session-id
~~~

Server phải xác minh **principal có quyền đọc file ID này hay không**, file đã qua xử lý chưa, có được lưu cache không, trình duyệt được phép hiển thị inline hay nên bắt tải về.

### 1.1. Các yêu cầu bảo mật chính

| Thuộc tính | Khi upload | Khi download |
|---|---|---|
| **Xác thực** | Ai đang gửi file? | Ai yêu cầu lấy byte? |
| **Phân quyền** | Có quyền tạo file thuộc resource/tenant này? | Có quyền đọc đúng file và phiên bản? |
| **Tính toàn vẹn** | Nội dung đúng định dạng/kích thước, có digest nếu cần? | Nội dung đúng bản đã phê duyệt? |
| **Cô lập dữ liệu** | Không ghi đè file khác user, không public trước scan | Không BOLA/IDOR hoặc leak qua URL/cache/log |
| **An toàn browser** | Không phục vụ HTML/SVG như script của ứng dụng | Không cho nội dung không tin cậy thực thi cùng origin |
| **Khả dụng** | Chống body lớn, nhiều parts, ZIP bomb, scanner DoS | Giới hạn download song song/Range/băng thông |
| **Vòng đời** | Quarantine, scan, publish, retention, cleanup | ACL, revoke, expiry, HTTP cache và token URL |

### 1.2. Sơ đồ trách nhiệm theo lớp

~~~mermaid
flowchart LR
    C[Browser hoặc M2M client] --> E[HTTPS edge và reverse proxy]
    E --> F[Spring Security filters]
    F --> H[HTTP multipart/controller]
    H --> V[Service: validate, ACL, quota]
    V --> Q[(Private quarantine)]
    Q --> SC[Scanner và processor sandbox]
    SC --> DB[(Metadata DB)]
    SC --> OBJ[(Approved private storage)]
    C -->|GET download| E
    F -->|authorize file ID| V
    V --> DB
    V --> OBJ
~~~

Không phải tất cả sản phẩm đều bắt buộc có AV scanner, CDN hoặc object storage riêng; mô hình này thể hiện cách **tách trách nhiệm**, nhất là khi file từ người ngoài được người khác download.

## 2. Threat model của upload và download

### 2.1. Những đầu vào không đáng tin

Trong upload, các trường sau đều có thể bị thao túng:

- Tên file và các ký tự path `../../secrets.txt`, dấu phân tách Windows/Unix, Unicode confusable, control characters, tên cực dài.
- Phần mở rộng `.pdf`/`.png` và MIME do client khai; không khẳng định nội dung thật.
- Binary payload chứa virus, macro, file đa định dạng, SVG/HTML/script hoặc mã khai thác parser.
- Metadata `folderId`, `ownerId`, `tenantId`, access level, part count và kích thước do client khai.
- Archive có entry path traversal, nested archives, tỷ lệ nén cực lớn, số file/pixel không giới hạn.
- URL “nhập file từ nơi khác” hoặc callback được server fetch: có nguy cơ **SSRF** nếu không kiểm soát địa chỉ và redirect.
- Request body/transfer encoding bất thường làm tăng chi phí parse, RAM, disk hoặc timeout.

Trong download, attacker có thể thay `fileId`, filename, Range headers, signed URL, request Host/origin và các tham số phiên bản. Thêm vào đó, file đã upload **chưa chắc an toàn khi browser render**.

### 2.2. Ma trận nguy cơ và phòng vệ

| Nguy cơ | Kịch bản | Tầng cần xử lý |
|---|---|---|
| CSRF upload | Trang ngoài kích hoạt POST dùng cookie user | Spring Security CSRF trên browser unsafe request |
| BOLA/IDOR | User A download ID của user B | Service kiểm ACL theo file/tenant sau auth |
| Path traversal | `../../...` trong filename/path | Object key do server tạo, không nối path client |
| Stored XSS | File HTML/SVG được phục vụ inline cùng app origin | Origin isolation, Content-Disposition, CSP, nosniff |
| MIME spoofing | Header `image/png` nhưng byte chứa HTML | MIME detection + format parser, fail closed |
| Malware | File độc hại qua upload tới người đọc | Quarantine, scanner/CDR, controlled release |
| ZIP bomb | Archive nhỏ giải nén thành nhiều GB | Quota bytes/entries/depth/time sau giải nén |
| Zip Slip | Archive entry ghi ra ngoài extraction root | Kiểm tra entry path/symlink, sandbox |
| DoS | Nhiều file/parts hoặc request upload chậm | Edge/container/application limits, quota/concurrency |
| TOCTOU | File hoặc symlink đổi sau khi kiểm tra | Immutable object key, atomic publish và safe file handle |
| Data leak qua CDN | Cache response private theo URL chung | No-store/private, signed access và cache key đúng |
| Signed URL leak | Token trong URL được log/chia sẻ còn hiệu lực | TTL ngắn, scope chặt, HTTPS, tránh log |
| SSRF | API tải file từ URL do client gửi | Allowlist egress/scheme/IP, kiểm DNS/redirect, sandbox |
| Parser exploit | Xử lý ảnh/PDF/Office của attacker | Parser cập nhật, resource limits, worker sandbox |

**Không có một hàm check extension hoặc antivirus nào giải quyết toàn bộ.** Cần tập hợp các lớp defense-in-depth theo loại file và mức độ chia sẻ.

## 3. Bản đồ trách nhiệm kiểm soát dữ liệu

| Lớp | Nên bảo vệ gì? | Không được xem là đủ cho |
|---|---|---|
| Browser/client | Hiển thị picker, tiến độ, chủ động gắn CSRF/Bearer hợp lệ | `accept=.pdf` không ngăn client gửi file khác |
| HTTPS edge/proxy | TLS, body size, timeouts, request rate, header trust | Không biết file có thuộc tenant nào |
| Container/multipart parser | Parse có giới hạn, temp storage, cleanup | Không scan malware hay check business ACL |
| Spring Security filters | Authentication, CSRF, CORS, security headers, route policy | Không kiểm byte file hoặc ownership của object cụ thể |
| Controller | Contract HTTP, validation request sơ bộ, status codes | Không nên ghép path client hoặc tự chứa mọi policy |
| Domain/storage service | Object-level ACL, quota, content policy, scan status, retention | Không thay WAF/TLS và cookie CSRF |
| Quarantine storage | Private object key, không có public read, giới hạn dung lượng | Không tự biết file sạch hay không |
| Scanner/processor | Phân tích malware/format, sandbox/CPU budget | Không thay quyền người dùng |
| Approved storage | Immutable version, access policy, encryption/retention | Không tự chứng minh HTTP user được download |
| Download response/CDN | Disposition, Content-Type, nosniff, CSP, cache/Range | Không bù authorization sai ở service |
| Logs/monitoring | Audit theo user/tenant/file ID, không log secrets/PII | Không nên ghi full file, session hoặc presigned URL |

### 3.1. Thứ tự phòng vệ mong muốn

~~~text
TLS + edge limits
  -> HTTP/multipart parse theo ngưỡng
  -> Spring Security: xác thực + CSRF nếu cookie-based
  -> controller + object/tenant authorization
  -> validate extension/content/signature/quota
  -> ghi private quarantine
  -> scan/CDR/sandbox có timeout
  -> ghi metadata approved và publish atomically
  -> download: auth + file ACL/status + safe response headers
~~~

**Không khẳng định parser luôn chạy sau CSRF.** Trong Servlet, multipart body/temp files có thể được xử lý sớm tùy filter/container ordering, vì token có thể nằm trong multipart fields. Do đó còn cần edge limit/temp disk budget và cleanup ngay cả khi request bị `401`/`403`.

### 3.2. Kích thước file không phải thước đo chi phí duy nhất

Một file 10 MiB có thể giải nén thành 10 GiB, một ảnh nhỏ có hàng trăm triệu pixels hoặc một multipart request có rất nhiều parts. 1000 uploads song song còn gây đầy temp disk. Cần giới hạn **body size, file size, part count, uncompressed bytes, image dimensions, CPU/memory/time, số jobs scan và quota per-user/tenant**, không chỉ một `max-file-size`.

## 4. Xác thực và CSRF: browser khác máy–máy

### 4.1. Browser session cookie: vẫn cần CSRF

Trong ứng dụng session-based, browser tự gắn `JSESSIONID`/`SESSION` theo chính sách Cookie. Vì vậy upload `POST /api/files`, delete `DELETE /api/files/{id}` và các unsafe operations phải có **CSRF token** được server đối chiếu.

Form SSR gửi hidden field `_csrf` hoặc SPA gửi `X-CSRF-TOKEN`; cách client lấy token phải khớp `CsrfTokenRepository` và request handler (có thể có deferred/XOR masking trong Servlet).

**CORS và SameSite không thay CSRF**: CORS chủ yếu kiểm soát quyền đọc response trong browser, còn cookie có thể được browser tự gửi trong một số ngữ cảnh cross-origin/same-site.

### 4.2. M2M Bearer-only upload

Một worker có thể gửi:

~~~http
POST /integrations/files HTTP/1.1
Authorization: Bearer ACCESS_TOKEN_VALID
Content-Type: multipart/form-data; boundary=...
~~~

Nếu `/integrations/**` được chứng minh **chỉ nhận Bearer header do client chủ động đặt**, không có cookie/HTTP Basic/gateway session fallback, có thể miễn CSRF kiểu cookie cho chain đó. **Tuy nhiên** JWT/opaque token validation, issuer/audience/expiry, scope `files:write`, tenant ACL, validation và resource limits vẫn bắt buộc.

Nếu API cũng đọc JWT từ cookie, dù stateless, **không còn thuần bearer-only**. Đừng tắt CSRF toàn ứng dụng chỉ vì có client M2M.

### 4.3. Upload cross-origin bằng SPA

Nếu frontend ở `https://spa.example.com` còn API ở `https://api.example.com`:

- Khi dùng session cookie, cần `credentials: "include"` và cookie `SameSite`/`Secure` phù hợp; custom CSRF header tạo preflight.
- Khi dùng Bearer-only, frontend chủ động gắn `Authorization: Bearer ...`; header này thường tạo preflight, không biến API thành cookie-auth.
- Preflight OPTIONS thường không có credential của request thực; **CORS phải được xử lý trước authentication**.
- CORS allowlist chỉ cấp cho origin tin cậy; không trả wildcard `Access-Control-Allow-Origin: *` cùng `Access-Control-Allow-Credentials: true`.
- Actual POST vẫn phải qua authentication, authorization, CSRF nếu cookie và validation file.

### 4.4. Không dùng GET cho thao tác có tác động

**GET download** có thể được browser navigation/prefetch; không triển khai `GET /api/files/delete?id=...`. Xóa/thay ACL là unsafe operation cần POST/DELETE, authentication, CSRF nếu browser cookie và quyền trên file.

## 5. Thiết kế API và vòng đời file

### 5.1. Hợp đồng route

| Route | Method | Tác vụ | Bảo vệ |
|---|---|---|---|
| `/api/files` | POST multipart | Nhận vào quarantine | Cookie session + CSRF + quota/validation |
| `/api/files/{id}` | GET | Trả metadata/scan status | Auth + ACL theo file/tenant |
| `/api/files/{id}/download` | GET | Trả bytes đã phê duyệt | Auth + ACL + safe response |
| `/api/files/{id}` | DELETE | Thu hồi/xóa file | Auth + CSRF + ACL |
| `/integrations/files` | POST | M2M upload | Bearer-only scope/tenant/quota |
| `/integrations/files/{id}` | GET | M2M download | Bearer-only + resource ACL |

Đối với file mới nhận, `POST` có thể trả **`202 Accepted`** và một file ID. Điều đó nghĩa server đã nhận công việc, **chưa chắc file được phép download**.

### 5.2. Metadata file

~~~text
id:              9f93c766-138b-4440-a344-9f6d94114ca3
ownerId:         alice
tenantId:        tenant-a
originalName:    report.pdf                # untrusted display metadata
storageKey:      approved/9f93.../v1       # server-generated
declaredMime:    application/pdf           # from client
detectedMime:    application/pdf           # from controlled validation
sizeBytes:       184320
sha256:          ...
scanStatus:      CLEAN
visibility:      PRIVATE
version:         v1
createdAt:       ...
expiresAt:       ...
~~~

Không biến `originalName` thành path/key. Metadata phải ràng buộc file với **owner/tenant và resource cha**, có thể thêm ACL, retention/legal hold và version. Client **không** được tự khai `ownerId` rồi hệ thống chấp nhận mà không kiểm quyền.

### 5.3. Trạng thái quarantine

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVING
    RECEIVING --> QUARANTINED: accepted bytes
    RECEIVING --> REJECTED: size/quota/type fail
    QUARANTINED --> SCANNING: worker claims
    SCANNING --> AVAILABLE: scan and policy passed
    SCANNING --> REJECTED: malware or invalid format
    SCANNING --> SCAN_FAILED: scanner timeout/error
    SCAN_FAILED --> SCANNING: bounded retry
    AVAILABLE --> REVOKED: owner/admin action
    REJECTED --> DELETED: cleanup
    REVOKED --> DELETED: retention policy
    AVAILABLE --> DELETED: delete request
~~~

Các status là **thiết kế ứng dụng**, không phải Spring Security cung cấp mặc định. File trong trạng thái QUARANTINED/SCANNING/SCAN_FAILED/REJECTED **không được trả bytes công khai**.

### 5.4. Upload response mẫu

~~~http
HTTP/1.1 202 Accepted
Location: /api/files/9f93c766-138b-4440-a344-9f6d94114ca3
Cache-Control: no-store
Content-Type: application/json

{"id":"9f93c766-138b-4440-a344-9f6d94114ca3","status":"QUARANTINED"}
~~~

`GET /api/files/{id}` có thể trả tiến trình/status cho người có quyền. Không expose quarantine object URL cho client trước khi approved.

## 6. Validation: đừng tin extension, tên file hay Content-Type

### 6.1. Không dùng tên do client khai để ghi vào filesystem

**Không nên:**

~~~java
Path destination = uploadRoot.resolve(file.getOriginalFilename());
file.transferTo(destination);
~~~

`getOriginalFilename()` là metadata **không tin cậy**. Nó có thể chứa `../../private.txt`, dấu phân tách path Windows, tên trùng file hệ thống hoặc ký tự điều khiển. Việc gọi `Path.normalize()` để “dọn” path chỉ là một bước kỹ thuật, **không tự chứng minh** đường dẫn an toàn trước symlink/TOCTOU.

**Nên:**

- Sinh UUID/random object key **ở server**; client không được chọn path lưu trữ.
- Sử dụng private directory/object bucket **ngoài static web root**; tài khoản tiến trình chỉ có quyền tối thiểu.
- Tên gốc chỉ dùng như **display metadata**, giới hạn độ dài và bỏ path separators/control characters trước khi xuất vào response.
- Đọc/ghi file theo ID đã được map từ DB và sau **authorization**, không `root.resolve(request.getParameter("path"))`.
- Không cho tên file trùng làm ghi đè object khác, và sử dụng storage version/immutability khi cần.

### 6.2. Extension và MIME chỉ là tín hiệu

Một endpoint chỉ chấp nhận PDF có thể có policy:

~~~text
Allowed extension: .pdf
Max upload bytes: 20 MiB
Declared Content-Type: application/pdf (không tin)
Detected format: PDF theo kiểm tra bytes/parser
Policy: không macro/script/embedded attachment theo yêu cầu
Scan: AV hoặc CDR worker, timeout và resource limits
Download: attachment; private origin/authorization
~~~

`filename.endswith(".pdf")` và multipart `Content-Type: application/pdf` không thể xác minh file thật. Một file đa định dạng/polyglot có thể vượt magic-byte check đơn giản. Thực tế nên kiểm tra nội dung với thư viện định dạng an toàn/được cập nhật, kèm sandbox/limit đối với parser phức tạp.

### 6.3. Phân biệt những rủi ro từ archive và media

**ZIP bomb:** byte nén ít nhưng uncompressed bytes, số entry, độ sâu hoặc CPU quá lớn.

**Zip Slip:** tên entry chứa `../` hoặc symlink khiến extractor ghi ngoài extraction root.

**Ảnh quá lớn:** payload vài MB nhưng pixel count/frames rất lớn khi decode, có thể làm hết memory.

**PDF/Office/SVG:** có thể chứa active content, macro, URLs hoặc khai thác parser/viewer. Không chỉ đổi MIME sang `application/octet-stream` rồi coi mọi file đã an toàn cho người tải.

Nếu sản phẩm hỗ trợ giải nén hoặc chuyển đổi định dạng, chạy processor với **CPU, memory, time, file size, entry count và egress restrictions**; validate paths trước mọi thao tác ghi; không dùng tài khoản có quyền ghi vào application binaries/secrets.

### 6.4. Nếu hỗ trợ upload-by-URL, phải đánh giá SSRF

Một API cho phép user yêu cầu server tải từ `https://some-site/file.pdf` tạo thêm bề mặt **Server-Side Request Forgery**:

- Chặn scheme ngoài HTTPS khi không cần, URL chứa credentials và redirect tới địa chỉ nội bộ.
- Resolve/check DNS/IP với policy private/link-local/metadata endpoints, kiểm tra lại từng redirect; tránh DNS rebinding.
- Dùng egress allowlist/network controls và proxy phù hợp, không tin chỉ regex tên host.
- Giới hạn bytes và thời gian nhận, không cho stream vô hạn.
- Sau khi tải vẫn phải đi qua **quarantine/scan/ACL** như file user upload.
- Không lấy URL bất kỳ rồi trả trực tiếp bằng redirect nếu URL đó lộ credential hoặc dẫn đến nội dung nguy hiểm.

## 7. Giới hạn ở proxy, container, ứng dụng và storage

### 7.1. Nginx có thể từ chối trước khi Spring nhận request

Ví dụ cấu hình **minh họa** ở HTTPS edge:

~~~nginx
server {
    listen 443 ssl;
    server_name app.example.com;

    ssl_certificate     /etc/ssl/example/app.crt;
    ssl_certificate_key /etc/ssl/example/app.key;

    client_max_body_size 24m;
    client_body_timeout 30s;

    location /api/ {
        proxy_pass http://spring-backend:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }
}
~~~

`client_max_body_size` là **limit request body tổng**, không phải định mức giải nén hay quota user. Multipart có overhead nên thường chọn giới hạn request lớn hơn file size cho một-file upload; phải đánh giá nhiều-part request theo hợp đồng.

Nếu edge trả `413 Content Too Large` (còn thường gọi Payload Too Large), request có thể **không bao giờ đến Spring controller**. Đừng sửa Spring Security CSRF khi nguyên nhân là Nginx size limit.

Proxy có thể **buffer multipart body ra disk** trước khi chuyển upstream; phải giới hạn và giám sát disk/timeout ở edge. TLS termination và forwarded headers phải được cấu hình theo trust boundary, không nhận `X-Forwarded-*` giả từ client Internet.

### 7.2. Spring Boot Servlet multipart limits

~~~yaml
# application.yml — ví dụ cho Spring MVC / Servlet
spring:
  servlet:
    multipart:
      max-file-size: 20MB
      max-request-size: 24MB
      file-size-threshold: 0B
      location: /srv/app-private/tmp-upload
~~~

Các thuộc tính này do **Servlet multipart configuration** áp dụng khi tích hợp đúng. Thư mục temp cần tồn tại/được phép ghi, được giám sát dung lượng, cô lập khỏi web root và có cleanup.

**Quan trọng:** `spring.servlet.multipart.*` là cấu hình **Servlet**, không giả định tự áp dụng cho WebFlux. WebFlux có codec/multipart parsing và data-buffer limits riêng.

### 7.3. Quota của domain service và scanner

Ví dụ policy:

| Giới hạn | Ví dụ minh họa | Lớp |
|---|---|---|
| Request body | 24 MiB | Proxy |
| Mỗi file | 20 MiB | Container + service |
| Số file/1 request | 1 | API/controller |
| File mỗi tenant | 10.000 file | DB/domain service |
| Tổng bytes tenant | 5 GiB | Quota service |
| Upload đồng thời/user | 3 | Rate/concurrency controller |
| Kiểm tra loại file | PDF hoặc ảnh đã định nghĩa | Validation service |
| Tổng bytes giải nén | 100 MiB | Processing worker |
| CPU/scan timeout | Theo workload và hạ tầng | Scanner sandbox |
| Quarantine TTL | Theo retry/retention policy | Lifecycle worker |
| Download concurrency | Theo per-principal/bandwidth policy | Edge/service |

Các con số là **ví dụ để minh họa phân lớp**, không phải giới hạn mặc định của Spring Security.

### 7.4. Cần rollback/cleanup theo lỗi

Khi copy upload xong nhưng ghi metadata thất bại, hoặc scanner không chạy:

- Xóa temp/quarantine object nếu không còn tham chiếu hợp lệ.
- Giải phóng quota reservation hoặc ghi trạng thái retry an toàn.
- Có worker garbage collection/reconciliation để dọn orphaned objects.
- Không để status `AVAILABLE` trước khi scanner kết luận đạt policy.
- Dùng atomic state transition/idempotent jobs để một file không đồng thời bị publish và reject khi có worker retry.
- Audit vừa đủ nhưng không ghi raw file, cookie hoặc token vào logs.

## 8. Multipart upload và CSRF: thứ tự middleware đáng kiểm tra

### 8.1. Token trong multipart body có thể cần parse sớm

Với form HTML:

~~~html
<form action="/api/files" method="post"
      enctype="multipart/form-data">
  <input type="file" name="file" accept=".pdf,application/pdf">
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Tải lên</button>
</form>
~~~

`accept` chỉ là gợi ý của file picker, **không là server-side validation**. `_csrf` là submitted token do Spring Security integration cung cấp.

Tùy cấu hình Servlet container/`MultipartFilter`/`DispatcherServlet`, CSRF filter có thể cần multipart body được parse để nhìn thấy form token. **Đặt MultipartFilter trước Security** thuận tiện cho form token nhưng có thể tạo temp files cho unauthenticated requests; **đặt sau Security** giảm parse sớm nhưng có thể không nhìn thấy token field, đặc biệt khi thử dùng token ở query string (rủi ro rò URL/log).

Giải pháp cụ thể phải được kiểm tra **trên đúng Spring Boot/Spring Security/container version đang dùng**. Cần đặt edge limits và temp disk quotas ngay cả với CSRF.

### 8.2. SPA nên gửi CSRF token qua header

Nếu SPA session-cookie đã nhận token từ endpoint `GET /api/csrf` được bảo vệ:

~~~javascript
const data = new FormData();
data.append("file", selectedFile); // Không tự set multipart boundary.

const response = await fetch("/api/files", {
  method: "POST",
  credentials: "same-origin",
  headers: { "X-CSRF-TOKEN": csrfToken },
  body: data
});
~~~

Không tự gán `Content-Type: multipart/form-data` khi dùng `FormData`: browser cần tự tạo `boundary` đúng với body. Với same-origin, custom header không gây CORS preflight như cross-origin; với SPA/API khác origin, phải cấu hình trusted-origin CORS cho `X-CSRF-TOKEN` và credentials/cookie policy.

**Không gửi session ID hoặc CSRF token trên URL query** để tránh lộ qua access logs, history, referrer và analytics.

### 8.3. M2M multipart qua Bearer

Client máy–máy có thể gọi `POST /integrations/files` với Bearer header, không dùng `JSESSIONID`. CSRF chỉ có thể được miễn trên chain đã chứng minh **không nhận ambient credential**. Upload file vẫn phải có size/type/quota/scan/authz như browser route.

## 9. Servlet: tách SecurityFilterChain cho browser và M2M

Ví dụ **minh họa kiến trúc** khi có browser session APIs tại `/api/files/**` và M2M API tại `/integrations/files/**`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class FilesServletSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain integrations(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/integrations/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/integrations/files")
                    .hasAuthority("SCOPE_files:write")
                .requestMatchers(HttpMethod.GET, "/integrations/files/**")
                    .hasAuthority("SCOPE_files:read")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .logout(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .csrf(AbstractHttpConfigurer::disable)
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/login").permitAll()
                .requestMatchers("/api/files", "/api/files/**")
                    .authenticated()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

**Đọc chính xác hợp đồng:**

- M2M `/integrations/**` được chọn bởi **chain matcher** `@Order(1)`, chỉ nhận Bearer JWT; `csrf.disable()` có điều kiện tại đó.
- Browser chain `@Order(2)` giữ CSRF cho unsafe methods. Có thể cần entry point trả `401` thay vì redirect HTML nếu client là SPA.
- `requestMatchers` trong authorization **không thay `securityMatcher`**. Chỉ chain phù hợp đầu tiên được chọn.
- Nếu ứng dụng dùng JWT trong cookie ở một endpoint, **không để endpoint đó trong chain bearer-only**.
- File upload đủ scope không tự đủ quyền gắn file vào tenant; service phải kiểm tra tài nguyên.
- Để browser SPA khác origin gọi `/api/**`, thêm CORS source + `http.cors(...)` cho đúng chain; preflight cần xử lý trước auth. Không bật credentialed CORS rộng cho M2M route.
- Resource Server cần cấu hình `JwtDecoder` với issuer, **audience validator**, expiry/signature, scope và client identity. Ví dụ chain **chưa cung cấp** Authorization Server phát token.

## 10. Servlet controller: nhận file, tạo receipt và trả trạng thái

### 10.1. Hợp đồng controller không tự “publish sạch”

~~~java
import java.net.URI;
import java.security.Principal;
import java.util.UUID;

import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/files")
class ServletFileUploadController {

    private final FileIngestionService ingestion;

    ServletFileUploadController(FileIngestionService ingestion) {
        this.ingestion = ingestion;
    }

    record UploadReceipt(UUID id, String status) {}

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    ResponseEntity<UploadReceipt> upload(
            @RequestPart("file") MultipartFile file,
            Authentication authentication) throws Exception {

        // Service kiểm size/quota, tenant, content, staging, metadata.
        UUID id = ingestion.stageForUser(authentication, file);

        return ResponseEntity.accepted()
            .location(URI.create("/api/files/" + id))
            .cacheControl(CacheControl.noStore())
            .body(new UploadReceipt(id, "QUARANTINED"));
    }
}
~~~

`FileIngestionService` là **service ứng dụng phải tự triển khai**. Controller mẫu không tự chứng minh scanner đã chạy. Nếu service chưa validate/đặt quota, chỉ có controller này là **không đủ an toàn**.

### 10.2. Bounded copy vào file temp có tên do server tạo

Đoạn **minh họa cho service** này dùng streaming thay vì `file.getBytes()`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

class BoundedQuarantineWriter {

    private static final long MAX_BYTES = 20L * 1024 * 1024;
    private final Path quarantineRoot =
        Path.of("/srv/app-private/quarantine");

    Path copyIncoming(InputStream source) throws IOException {
        Files.createDirectories(quarantineRoot);
        Path tmp = Files.createTempFile(
            quarantineRoot, "pending-", ".bin");

        boolean success = false;
        try (InputStream in = source;
             OutputStream out = Files.newOutputStream(tmp)) {
            byte[] buffer = new byte[8192];
            long count = 0;
            int n;

            while ((n = in.read(buffer)) != -1) {
                count += n;
                if (count > MAX_BYTES) {
                    throw new IOException("File vượt giới hạn");
                }
                out.write(buffer, 0, n);
            }

            success = true;
            return tmp;
        } finally {
            if (!success) {
                Files.deleteIfExists(tmp);
            }
        }
    }
}
~~~

Tại nơi gọi, có thể dùng `file.getInputStream()` nhưng phải xử lý đúng ownership/đóng stream; method mẫu tự đóng stream truyền vào. File vừa copy xong **vẫn ở quarantine** và cần được quản lý bằng metadata/TTL; không cho tải xuống ngay. Code này **chưa có** content validation, hash, tenant quota, AV, cleanup orphaned object và transaction/retry logic—phải bổ sung ở domain service.

**Không để upload temp nằm trong thư mục mà web server phục vụ tĩnh.** Đảm bảo filesystem permissions hạn chế; nếu không dùng Linux/Windows paths tương ứng, cấu hình root theo hạ tầng.

### 10.3. Kiểm tra giới hạn cả trước và sau parse

`MultipartFile.getSize()` có thể giúp từ chối nhanh, nhưng file có thể đã được multipart resolver spool ra disk từ trước. Bounded stream copy là tuyến phòng vệ **bổ sung**, không thay edge/container limits. Không xử lý `file.getBytes()` cho file lớn vì nó cần tạo byte array trong heap.

Nếu file rỗng không hợp lệ, từ chối `isEmpty()`; nếu file nhiều part hoặc quá 20 MiB, trả lỗi 400/413 theo hợp đồng và **dọn cleanup**. Đừng kỳ vọng controller được gọi nếu container đã từ chối request trước đó.

## 11. Servlet download: kiểm quyền trước khi đọc storage

### 11.1. Không lấy filesystem path trực tiếp từ query

**Không nên:**

~~~java
@GetMapping("/download")
byte[] download(@RequestParam String path) throws IOException {
    return Files.readAllBytes(Path.of("/srv/data").resolve(path));
}
~~~

Đoạn này có ít nhất bốn vấn đề: path traversal, không kiểm quyền theo file, tải toàn bộ file vào heap và không đặt response headers an toàn.

**Thiết kế đúng:** Client chỉ cung cấp **opaque file ID**. Service tìm metadata đã lưu, xác minh principal/tenant/object ACL, kiểm tra `status=AVAILABLE`, rồi lấy **storage key do server sinh**. Nó có thể trả một `Resource` có streaming semantics hoặc chuyển bytes từ object storage qua adapter an toàn.

### 11.2. Controller dùng Resource và Content-Disposition

~~~java
import java.nio.charset.StandardCharsets;
import java.util.UUID;

import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ServletFileDownloadController {

    private final FileAccessService files;

    ServletFileDownloadController(FileAccessService files) {
        this.files = files;
    }

    @GetMapping("/api/files/{id}/download")
    ResponseEntity<Resource> download(
            @PathVariable UUID id,
            Authentication authentication) {

        // Service: auth, tenant/ACL, status=AVAILABLE, trusted key.
        DownloadDescriptor target =
            files.openAuthorized(authentication, id);

        String disposition = ContentDisposition.attachment()
            .filename(target.safeDownloadName(), StandardCharsets.UTF_8)
            .build()
            .toString();

        return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
            .cacheControl(CacheControl.noStore())
            .body(target.resource());
    }
}
~~~

`FileAccessService` và `DownloadDescriptor` là **thành phần ứng dụng cần triển khai**. Một interface tham chiếu:

~~~java
import org.springframework.core.io.Resource;
import org.springframework.security.core.Authentication;
import java.util.UUID;

record DownloadDescriptor(
    Resource resource,
    String safeDownloadName) {}

interface FileAccessService {
    DownloadDescriptor openAuthorized(
        Authentication authentication, UUID id);
}
~~~

Trong implementation:

1. Query metadata theo file ID, principal và tenant; kiểm tra quyền đọc file/resource cha **trước khi mở bytes**.
2. Chỉ cho file `AVAILABLE`, scan hợp lệ, chưa revoked/deleted và đúng version.
3. Ánh xạ server-generated storage key từ metadata đã tin cậy tới object; không từ client filename/path.
4. Với local disk, chống traversal, symlink và file swap; với object storage, kiểm object version/permissions.
5. Tạo `safeDownloadName()` bằng policy bỏ control chars, path separators, giới hạn length, Unicode confusables khi phù hợp.
6. Dùng Resource streaming, không `Files.readAllBytes()` cho file lớn.
7. Có cleanup/error handling nếu downstream ngắt kết nối khi stream.

### 11.3. Khi nào trả 401, 403, 404 hoặc 409?

- **`401 Unauthorized`:** chưa xác thực (API contract); browser navigation có thể redirect login theo chain.
- **`403 Forbidden`:** đã xác thực nhưng không có quyền đọc.
- **`404 Not Found`:** file không có hoặc cố ý **ẩn sự tồn tại** với người không có quyền theo policy.
- **`409 Conflict`:** sau khi xác minh người có quyền thấy metadata, file đang `SCANNING` hoặc trạng thái chưa cho download; có thể trả status code khác theo API contract.
- **`410 Gone`:** chỉ dùng khi phù hợp để báo file đã xóa và caller được phép biết sự tồn tại trước đó.

Không tiết lộ filename, Content-Length, hash, scan findings hoặc ETag **trước khi** authorize. Các request HEAD/Range/conditional cũng phải tuân theo cùng ranh giới.

### 11.4. Streaming, Resource và Content-Length

`ResponseEntity<Resource>` cho Spring viết body qua resource converter thay vì tạo byte array lớn. Với trusted local path, có thể dùng `FileSystemResource`; với remote object, dùng adapter streaming phù hợp.

**Không đặt Content-Length không chính xác** (nhất là khi compression/conversion thay bytes). Với `InputStreamResource` chỉ đọc một lần, tránh việc một layer cố tính `contentLength()` bằng cách tiêu thụ stream ngoài ý muốn; dùng metadata size từ object bất biến khi đáng tin cậy.

Khi headers đã gửi và stream lỗi giữa chừng, server có thể không đổi response sang JSON 500; cần connection/error metrics và log metadata không nhạy cảm.

## 12. Phục vụ file chưa tin cậy: Content-Type, Disposition và CSP

### 12.1. Vì sao không đưa upload vào static web root?

Nếu user upload `page.html` hoặc `image.svg` rồi server trả nó từ `https://app.example.com/uploads/page.html`, browser có thể xử lý active content với **origin của ứng dụng**. JavaScript độc hại có thể gọi endpoint same-origin, sử dụng cookie mà browser tự gửi và khai thác dữ liệu DOM.

Không public thư mục quarantine/approved objects qua static mapping khi file chưa được authorize theo đối tượng. Với nội dung cần preview, nên dùng **origin riêng không chia sẻ app session cookie**, thậm chí khác registrable domain; áp CSP và format conversion nếu yêu cầu.

### 12.2. Header download mẫu

~~~http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="report.pdf"
X-Content-Type-Options: nosniff
Cache-Control: no-store
~~~

- `Content-Type` nên xuất phát từ policy/detected format, **không** phản chiếu multipart `file.getContentType()` một cách mù quáng.
- `Content-Disposition: attachment` hướng browser tải file thay vì xử lý inline. Header này quan trọng nhưng không bảo đảm mọi viewer/client an toàn.
- `X-Content-Type-Options: nosniff` hạn chế MIME sniffing trong một số ngữ cảnh script/style; nó **không** thay origin isolation hoặc content validation.
- `Cache-Control: no-store` là mặc định bảo thủ cho file riêng tư; nếu cần cache, phải thiết kế quyền và revocation rõ ràng.
- Một PDF/Office/ảnh độc hại vẫn có thể khai thác phần mềm xem file sau khi tải; cần scanner/CDR/sandbox theo nghiệp vụ.

### 12.3. Tên download và header injection

**Không tự nối:**

~~~java
String disposition = "attachment; filename=" + originalFilename;
~~~

Tên client có thể chứa quote, CR/LF, path separators, bidi/control characters, độ dài vô lý. Sanitize tên hiển thị và dùng builder `ContentDisposition.attachment().filename(safeName, UTF_8)` cho encoding chuẩn. Có thể cung cấp fallback ASCII cho user agents đặc thù, nhưng luôn test Unicode thực tế.

### 12.4. Preview active content đòi chính sách riêng

Nếu sản phẩm bắt buộc preview một số định dạng:

- Ưu tiên loại đã được **chuyển đổi** (ví dụ rasterize ảnh bằng worker sandbox), không render HTML/SVG do user gửi cùng app origin.
- Sử dụng origin riêng có cookie isolation và giới hạn quyền; không share cookie auth giữa host app và content host.
- CSP cần xuất hiện trên **response tài liệu thực sự render**, không chỉ JSON metadata; cân nhắc `sandbox` và script restrictions khi phù hợp.
- Hạn chế iframe embedding bằng `frame-ancestors`, tránh lộ thông tin từ document trong browser.
- Không preview file `QUARANTINED`/`SCAN_FAILED`/`REVOKED`.
- “Virus scan CLEAN” không chứng minh an toàn trước mọi XSS/polyglot/parser vulnerability.

## 13. HEAD, Range, cache, ETag và CDN

### 13.1. Range cho file lớn

Client có thể yêu cầu:

~~~http
GET /api/files/9f93c766-138b-4440-a344-9f6d94114ca3/download HTTP/1.1
Range: bytes=0-1048575
Cookie: JSESSIONID=SESSION_ALICE
~~~

Khi server hỗ trợ Range, response có thể là `206 Partial Content`, `Content-Range`/`Content-Length` chính xác, hoặc `416 Range Not Satisfiable`. Hành vi phụ thuộc `ResourceHttpMessageConverter`/`ResourceHttpMessageWriter`, loại Resource và reverse proxy; **kiểm thử trên đúng stack/version**.

**Mọi request Range phải qua authentication, file-level ACL và status=AVAILABLE**, không cho các range tiếp theo bypass vì “range đầu đã được cho phép”. Với mutable object, khóa version/ETag để không trộn bytes của hai phiên bản.

### 13.2. HEAD và conditional GET có thể làm lộ metadata

`HEAD` trả metadata headers dù không gửi bytes; `If-None-Match`/`If-Modified-Since` có thể dẫn đến `304 Not Modified`.

- Không cho HEAD/304 bỏ qua ACL và trạng thái scan.
- Không tiết lộ filename, size, hash/ETag cho user không có quyền.
- Nếu quyền đã bị thu hồi, revalidation phải phản ánh điều đó.
- 304 không chứng minh file còn có thể được đọc nếu authorization thay đổi sau lần download trước.

### 13.3. Cache private và CDN

Với file nhạy cảm, mặc định `Cache-Control: no-store` trên response download. Nếu cần CDN, xác định nó có **đủ khả năng kiểm quyền** hoặc chỉ cache object sau lớp signed URL với TTL thích hợp; phân biệt cache key theo object version/capability.

`Vary: Cookie` hoặc `Vary: Authorization` **không tự đảm bảo** shared cache không trộn dữ liệu giữa user/tenant. Không biến file private thành public object để “tăng tốc” mà bỏ qua quyền.

### 13.4. Signed URL mang đặc tính bearer capability

Một URL download được ký thường cho phép **ai sở hữu URL còn hiệu lực** đọc object tương ứng. Nó có thể rò trong access logs, support ticket, copied link, browser history hoặc analytics.

Nếu chọn presigned URL, giới hạn **method, object key/version, TTL, response headers và phạm vi quyền**, dùng HTTPS, che query string chứa chữ ký khỏi logs và lưu ý thu hồi không nhất thiết tức thì. Nếu yêu cầu revoke ngay, có thể phải proxy bytes qua API có kiểm quyền tại từng request hoặc thiết kế revocation khác.

## 14. Object storage và presigned upload/download

### 14.1. Upload trực tiếp tới storage vẫn cần authorization

Một số ứng dụng không muốn cho bytes đi qua Spring API vì file lớn. Có thể dùng **presigned POST/PUT** vào object storage, nhưng việc cấp quyền vẫn phải qua API:

~~~mermaid
sequenceDiagram
    actor C as Browser
    participant API as Spring API
    participant DB as Metadata/Quota
    participant O as Private quarantine bucket
    participant S as Scanner

    C->>API: POST xin upload slot + CSRF
    API->>API: Kiểm auth, tenant, quota và policy
    API->>DB: Record PENDING + server-generated object key
    API-->>C: Presigned upload capability ngắn hạn
    C->>O: PUT hoặc POST bytes đúng key
    O-->>C: Acknowledge
    C->>API: POST complete + CSRF
    API->>O: HEAD/verify object size, checksum, version
    API->>DB: Mark QUARANTINED
    API->>S: Queue scan
    S->>DB: SCANNING -> AVAILABLE/REJECTED
~~~

**Quy tắc:**

- Bucket/prefix quarantine phải **private** và key phải **do server sinh**, không để client tự chọn `public-read`/object key tùy ý.
- Presigned capability giới hạn method, key, TTL, size, content type/checksum **theo khả năng thật của store**. Presigned PUT và presigned POST policy không có cùng khả năng ràng buộc.
- Đối với direct browser upload tới storage origin khác, cần CORS ở **storage origin** cho trusted frontend; CORS **không thay chữ ký/quota/scan**.
- Callback `complete` chỉ là yêu cầu của client: server phải tự verify object có thật, thuộc upload record, đúng size/digest/version và chưa hết TTL.
- Chỉ publish sau scanner và metadata state transition thành công; các worker retry phải idempotent.
- Cleanup upload slot/quarantine objects bỏ dở, expired hoặc orphaned, giải phóng quota.

### 14.2. Integrity hash không phải malware scan

SHA-256/checksum giúp phát hiện byte sai, truncation hoặc storage corruption, **không chứng minh file không có malware**. Scanner phải xử lý **cùng object version** sẽ được công bố; nếu không có immutable key/version, có nguy cơ TOCTOU giữa scan và publish.

### 14.3. Signed download link có thể bị chuyển tiếp

Sau khi kiểm user/tenant/scan status, Spring có thể phát một **presigned GET** cho đúng object version, TTL ngắn và response attachment policy. URL mang tính chất **bearer capability**: ai có URL hợp lệ thường có thể sử dụng nó tới khi hết hạn, ngay cả khi quyền trong ứng dụng đã thay đổi, trừ khi có revocation strategy thực sự.

Do đó không log full query string của signed URL, tránh chia sẻ qua email/support ticket và giới hạn TTL/method/object. Nếu cần thu hồi **ngay lập tức** trên từng lần download, cân nhắc streaming qua API authorize hoặc edge authorization được thiết kế riêng.

## 15. Reactive/WebFlux: FilePart và streaming download

### 15.1. Reactive khác Servlet ở API, không khác threat model

Spring WebFlux dùng `FilePart`/reactive publishers thay cho `MultipartFile`, `SecurityWebFilterChain`/`ServerHttpSecurity` thay cho Servlet SecurityFilterChain/HttpSecurity, và `WebSession` thay cho `HttpSession`.

| Nhiệm vụ | Servlet/MVC | Reactive/WebFlux |
|---|---|---|
| Multipart | `MultipartFile` | `FilePart` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| CSRF | `CsrfFilter` | `CsrfWebFilter` |
| Repository theo phiên | `HttpSessionCsrfTokenRepository` | `WebSessionServerCsrfTokenRepository` |
| Download | `ResponseEntity<Resource>` | `Mono<ResponseEntity<Resource>>` |
| Test | `MockMvc` | `WebTestClient` |

`spring.servlet.multipart.*` **không tự áp dụng** cho WebFlux. WebFlux có multipart reader/codec/temp storage limits riêng, thường được cấu hình qua `spring.webflux.multipart.*` tùy Boot/Framework version; hãy xác minh property names và giới hạn thật trên version triển khai.

### 15.2. Reactive security chains cho hai loại client

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
class FileWebFluxSecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain machineFiles(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/integrations/**"))
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.POST, "/integrations/files")
                    .hasAuthority("SCOPE_files:write")
                .pathMatchers(HttpMethod.GET, "/integrations/files/**")
                    .hasAuthority("SCOPE_files:read")
                .anyExchange().denyAll()
            )
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .logout(ServerHttpSecurity.LogoutSpec::disable)
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain browserFiles(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/files", "/api/files/**")
                    .authenticated()
                .anyExchange().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

**Giải thích:** M2M Bearer-only chain mới có thể miễn CSRF theo threat model đã chứng minh, browser WebSession chain vẫn bật CSRF. JWT cần decoder có issuer/audience/expiry/scope validation. Với SPA khác origin dùng cookie, browser chain phải thêm Reactive CORS source/`http.cors(...)` phù hợp để preflight được xử lý trước authentication.

### 15.3. Controller nhận FilePart

~~~java
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
class ReactiveUploadController {

    private final ReactiveFileIngestionService ingestion;

    ReactiveUploadController(ReactiveFileIngestionService ingestion) {
        this.ingestion = ingestion;
    }

    @PostMapping(path = "/api/files",
                 consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Mono<ResponseEntity<Map<String, String>>> upload(
            @RequestPart("file") FilePart file,
            ServerWebExchange exchange) {

        return exchange.getPrincipal()
            .flatMap(principal ->
                ingestion.stageForUser(principal, file))
            .map(id -> ResponseEntity.accepted()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                    "id", id.toString(),
                    "status", "QUARANTINED")));
    }
}
~~~

`ReactiveFileIngestionService` là **service giả định** trả `Mono<UUID>`, triển khai quyền tenant, quota, private quarantine, scanning và cleanup. **Không dùng `file.filename()` làm storage path**.

### 15.4. FilePart.transferTo phải được subscribe và có cleanup

Một đoạn cốt lõi bên trong reactive service, nơi `tempPath` được tạo từ private root với server-generated name:

~~~java
Mono<Void> copy = filePart.transferTo(tempPath);

return copy
    .then(validateAndRegisterPending(tempPath, principal))
    .onErrorResume(error ->
        deleteTempFileNonBlocking(tempPath)
            .then(Mono.error(error)));
~~~

`validateAndRegisterPending` và `deleteTempFileNonBlocking` là **các hàm giả định**, không phải Spring API có sẵn. `transferTo` trả publisher, nên phải **return/compose** để framework subscribe.

Tránh `DataBufferUtils.join(filePart.content())` vô giới hạn, `collectList()` mọi data buffers hoặc `Files.readAllBytes` file lớn. Khi tự xử lý `DataBuffer`, phải tôn trọng backpressure/release đúng cách. File I/O blocking, parser/AV blocking nên chạy trên `Schedulers.boundedElastic()` hoặc worker riêng, **không chặn Reactor event loop**.

### 15.5. Reactive download có ACL trước resource

~~~java
import java.nio.charset.StandardCharsets;
import java.util.UUID;

import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
class ReactiveDownloadController {

    private final ReactiveFileAccessService access;

    ReactiveDownloadController(ReactiveFileAccessService access) {
        this.access = access;
    }

    @GetMapping("/api/files/{id}/download")
    Mono<ResponseEntity<Resource>> download(
            @PathVariable UUID id,
            ServerWebExchange exchange) {

        return exchange.getPrincipal()
            .flatMap(principal -> access.openAuthorized(principal, id))
            .map(target -> ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                    ContentDisposition.attachment()
                        .filename(target.safeDownloadName(),
                                  StandardCharsets.UTF_8)
                        .build().toString())
                .cacheControl(CacheControl.noStore())
                .body(target.resource()));
    }
}
~~~

`ReactiveFileAccessService` là service giả định trả `Mono<DownloadDescriptor>` **sau khi** kiểm auth, tenant, ACL, `AVAILABLE` và object version. Với remote storage nên dùng reactive streaming SDK hoặc `Flux<DataBuffer>` được quản lý đúng; không trả `Mono<byte[]>` cho file lớn.

**Range và HEAD vẫn phải authorize**, kiểm thử trên framework/storage/proxy version thật. Nếu reactive service có blocking DB/storage adapter, chuyển sang scheduler phù hợp hoặc thay bằng non-blocking implementation.

## 16. Chính sách HTTP headers theo nguồn phát response

### 16.1. Mỗi response có chủ sở hữu khác nhau

| Response | Bên phát | Cần kiểm soát |
|---|---|---|
| HTML upload form / SPA shell | Spring MVC, proxy hoặc CDN | CSP, HSTS, frame-ancestors, nosniff, cache HTML |
| JSON upload receipt `202` | Spring API | `no-store`, chỉ ID/status được phép đọc |
| File metadata/status | Spring API | Auth, ACL, tenant, no-store nếu private |
| Stream download | Spring API hoặc object store | Attachment, Content-Type, nosniff, private cache, ACL/Range |
| Untrusted content preview | Domain content cách ly | CSP/sandbox, cookie isolation, no app origin privileges |
| Presigned upload object | Object storage | Signed key/method/TTL/size, storage CORS nếu browser |
| M2M upload/download | OAuth2 Resource Server | Bearer validation/scope/tenant, 401/403, no token logs |
| 413 do reverse proxy | Nginx/gateway | Body limits, error status, không che thành 200 |
| 403 do CSRF/security | Spring Security | Không ghi file công khai, không làm side effect |
| 502/504 do gateway | Reverse proxy | Đúng status, không leak upstream topology |

**CSP trên JSON API không tự bảo vệ HTML do CDN phục vụ.** Tương tự, Spring Security headers trên API không tự đi theo object response khi browser tải qua presigned URL trực tiếp từ storage.

### 16.2. CSP, HSTS và nosniff đóng vai trò khác nhau

- **CSP** hạn chế nguồn script/đích kết nối/embedding trên tài liệu browser; phải có trên HTML/preview thực, kết hợp output encoding và DOM XSS defenses.
- **HSTS** yêu cầu browser ưu tiên HTTPS cho host trong thời hạn/phạm vi đã công bố; cần xem kỹ `includeSubDomains`/preload và TLS readiness.
- **`X-Content-Type-Options: nosniff`** hạn chế một số MIME sniffing; không thay malware scan, isolation hay `Content-Disposition`.
- **Cookie `Secure; HttpOnly; SameSite`** giúp bảo vệ phiên browser; token CSRF vẫn cần trên upload/delete dùng cookie.
- **HTTP firewall** và reverse proxy normalize URL, nhưng không thay file-level ACL/path confinement.
- **Content-Disposition** giúp browser xử lý file như attachment; không bảo đảm phần mềm đọc file không có lỗ hổng.
- **Cache-Control** bảo vệ tính riêng tư và revocation; response private không nên được shared CDN lưu nhầm.

## 17. Ma trận kiểm thử: upload, download và ranh giới quyền

| ID | Tình huống | Kỳ vọng |
|---|---|---|
| **FL-01** | Browser POST upload có session và CSRF đúng, PDF hợp lệ | `202` + file ID, trạng thái QUARANTINED |
| **FL-02** | Browser POST có session nhưng thiếu CSRF | `403`, không có metadata/object mới |
| **FL-03** | Browser POST token CSRF sai | `403`, không ghi file |
| **FL-04** | Browser POST chưa login | 401/redirect theo API contract, không tạo file |
| **FL-05** | M2M Bearer token đủ `files:write` | Upload được xử lý theo partner policy |
| **FL-06** | M2M chỉ có cookie browser, không Bearer | Không được xác thực M2M, không tạo file |
| **FL-07** | M2M Bearer sai issuer/audience/expired | `401`, không tạo file |
| **FL-08** | M2M token hợp lệ thiếu scope write | `403`, không tạo file |
| **FL-09** | File name `../../other.txt` | Không được dùng như storage path, không ghi ngoài quarantine |
| **FL-10** | `image/png` trong header nhưng bytes là HTML | Bị reject hoặc xử lý thành định dạng an toàn theo policy |
| **FL-11** | File vượt max size | `413`/error đúng tầng, temp cleanup |
| **FL-12** | Quá nhiều parts/file count | Bị từ chối theo container/service policy |
| **FL-13** | ZIP bomb hoặc archive path traversal | Không giải nén vô hạn/không ghi ngoài root |
| **FL-14** | Scanner timeout | SCAN_FAILED/QUARANTINED, không publish |
| **FL-15** | Scanner trả malware | REJECTED, không download |
| **FL-16** | Scanner CLEAN và metadata publish | Chỉ file version đã scan là AVAILABLE |
| **FL-17** | GET download file AVAILABLE của Alice bởi Alice | 200/206 theo contract, attachment/nosniff |
| **FL-18** | GET file của Alice bởi Bob/tenant khác | `403` hoặc `404`, **không có bytes** |
| **FL-19** | GET file QUARANTINED/SCAN_FAILED | Không trả bytes, status theo contract |
| **FL-20** | GET file đã revoked/deleted | Không trả bytes |
| **FL-21** | HEAD/Range bởi user không quyền | Không lộ size, hash hoặc bytes |
| **FL-22** | Response Content-Disposition với tên có CR/LF/Unicode | Header an toàn, không injection |
| **FL-23** | Stored HTML/SVG file dưới public URL | Không thực thi script cùng origin app |
| **FL-24** | CDN cache file của Alice | Không trả nội dung cho Bob |
| **FL-25** | Presigned URL expired/revoked | Hành vi theo TTL/revocation policy đã kiểm chứng |
| **FL-26** | Direct-to-storage upload bỏ dở | Object/slot được cleanup, quota giải phóng |
| **FL-27** | Download stream bị client abort | Resource/stream đóng, metric và cleanup đúng |
| **FL-28** | Upload song song quá quota | Bị từ chối, không oversubscribe storage |
| **FL-29** | GET download có mã hóa path/encoded slash lạ | HTTP firewall/matcher không cho traversal/bypass |
| **FL-30** | Proxy trả 413 trước Spring | Client nhận lỗi thật, không hiểu nhầm là CSRF/CORS |
| **FL-31** | POST delete file thiếu CSRF | Không xóa, đúng status |
| **FL-32** | Token trong query string/signature xuất hiện logs | Bị che/redacted theo log policy |

**Với tất cả negative cases, phải kiểm tra side effects**: không có file mới ở approved storage, không có DB record AVAILABLE, không có event phát hành/download ngoài ý muốn và quota được hoàn nguyên đúng.

## 18. Servlet MockMvc: kiểm thử upload và CSRF

### 18.1. Browser upload hợp lệ/thiếu token

Giả định có endpoint `POST /api/files` và test fake `FileIngestionService` trả ID cố định, không cần thật sự scan tệp:

~~~java
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletUploadSecurityTests {

    @Autowired MockMvc mvc;

    MockMultipartFile pdf() {
        return new MockMultipartFile(
            "file",
            "report.pdf",
            "application/pdf",
            "%PDF-1.7\nfixture".getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void browserUploadWithCsrfCanBeAccepted() throws Exception {
        mvc.perform(multipart("/api/files")
                .file(pdf())
                .with(user("alice"))
                .with(csrf().asHeader()))
            .andExpect(status().isAccepted());
    }

    @Test
    void browserUploadMissingCsrfIsRejected() throws Exception {
        mvc.perform(multipart("/api/files")
                .file(pdf())
                .with(user("alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void browserUploadInvalidCsrfIsRejected() throws Exception {
        mvc.perform(multipart("/api/files")
                .file(pdf())
                .with(user("alice"))
                .with(csrf().asHeader().useInvalidToken()))
            .andExpect(status().isForbidden());
    }
}
~~~

**Điều kiện:** Đây là **mẫu test security chain**; một fake ingestion service phải xử lý PDF fixture, vì byte string `%PDF-1.7\nfixture` **không phải một tài liệu PDF hoàn chỉnh**. Nếu chạy parser/AV thật, cần tệp fixture hợp lệ ở môi trường test và expected status theo pipeline.

`with(user())` tạo mock authentication, `with(csrf())` mô phỏng token hợp lệ. Chúng không chứng minh login/session cookie thật, multipart parser limits hoặc reverse proxy config. Phải bổ sung **HTTP integration** để thử form/token thật và 413.

### 18.2. M2M upload có scope và không CSRF

Trên chain `/integrations/**`, dùng `jwt()` mock principal:

~~~java
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

@Test
void m2mUploadWithWriteScopeCanPassWithoutCsrf() throws Exception {
    mvc.perform(multipart("/integrations/files")
            .file(pdf())
            .with(jwt()
                .jwt(j -> j
                    .subject("machine-partner")
                    .claim("client_id", "partner-42"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_files:write"))))
        .andExpect(status().isAccepted());
}
~~~

Đặt method trong class test có `mvc` và `pdf()`; endpoint `/integrations/files` phải được application triển khai (controller tương tự browser nhưng dùng M2M identity). `jwt()` **không xác minh chữ ký/issuer/audience thật**; cần integration với signed token/test decoder.

### 18.3. Test cookie-only request không được gọi M2M upload

~~~java
import jakarta.servlet.http.Cookie;

@Test
void cookieWithoutBearerCannotUploadToM2M() throws Exception {
    mvc.perform(multipart("/integrations/files")
            .file(pdf())
            .cookie(new Cookie("JSESSIONID", "dummy-id")))
        .andExpect(status().isUnauthorized());
}
~~~

Cookie giả chỉ là bước đầu. Test mạnh hơn phải tạo **session browser đã đăng nhập thật**, gửi chính cookie ấy đến `/integrations/files` **không Bearer**, rồi xác nhận không tạo file. Nếu được chấp nhận, M2M chain có session/gateway fallback ngoài dự kiến nên không đủ điều kiện miễn CSRF.

## 19. Servlet MockMvc: kiểm thử download theo tài nguyên

### 19.1. Test header download đã được authorize

Giả định có file AVAILABLE `id` thuộc Alice và `FileAccessService` test trả `Resource` chứa bytes, tên đã sanitize:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletFileDownloadTests {

    @Autowired MockMvc mvc;

    private final UUID fileId = UUID.fromString(
        "9f93c766-138b-4440-a344-9f6d94114ca3");

    @Test
    void ownerCanDownloadWithAttachmentHeader() throws Exception {
        mvc.perform(get("/api/files/{id}/download", fileId)
                .with(user("alice")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Content-Disposition", startsWith("attachment;")))
            .andExpect(header().string(
                "Cache-Control", "no-store"));
    }

    @Test
    void otherUserCannotReadFileBytes() throws Exception {
        mvc.perform(get("/api/files/{id}/download", fileId)
                .with(user("bob")))
            .andExpect(status().isNotFound());
    }
}
~~~

Status `404` ở negative case là **policy giả định** nhằm ẩn việc file tồn tại; nếu ứng dụng chọn `403`, đổi assertion theo contract. Quan trọng hơn là kiểm tra **response body không có bytes/file metadata** và không có storage read unauthorized. Không dùng fake service `alwaysAllow()` khi test authorization.

### 19.2. Test trạng thái file và Range/HEAD

Với fixture ở trạng thái QUARANTINED:

~~~text
GET /api/files/{id}/download với user owner
  -> status theo contract (ví dụ 409), không có bytes.

GET /api/files/{id}/download với user ngoài tenant
  -> 404/403, không tiết lộ status/file size.

HEAD /api/files/{id}/download với user ngoài tenant
  -> vẫn bị authorize, không leak Content-Length/ETag.

GET ... Range: bytes=0-99 với user owner
  -> 206 nếu Range được hỗ trợ, bytes đúng version.

GET ... Range: bytes=0-99 với user ngoài tenant
  -> không có bytes, không tiết lộ metadata.
~~~

Cần kiểm tra với **resource type thật và Spring converter/proxy** vì Range behavior phụ thuộc stack, không thể coi mọi `ResponseEntity<Resource>` đều luôn trả 206.

### 19.3. Kiểm thử path traversal và header injection

- Thử tên upload `../../config.yml` và đường dẫn Windows `..\..\other.txt`: storage key vẫn do server tạo, không có file ngoài quarantine.
- Thử tên dài với CR/LF, Unicode bidi, quote và ký tự điều khiển: `Content-Disposition` phải hợp lệ và không thêm header mới.
- Thử URL `/api/files/../...`, encoded traversal, double slashes: không bypass matcher/firewall/storage.
- Thử tệp đúng extension nhưng byte sai/malware test signature trong **môi trường scanner được phép**: reject/quarantine, không public.
- Test race scanner: AVAILABLE chỉ chuyển khi cùng object version đã scan, không thể tải trong khi status SCANNING.

## 20. Reactive WebTestClient: upload có CSRF và download có ACL

### 20.1. Dùng multipart builder và security test

`WebTestClient` với `spring-security-test` giúp kiểm thử WebFilterChain nhưng **không phải browser thật**.

~~~java
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveFileUploadSecurityTests {

    @Autowired ApplicationContext context;

    private WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    private MultipartBodyBuilder parts() {
        byte[] bytes =
            "%PDF-1.7\nfixture".getBytes(StandardCharsets.UTF_8);

        ByteArrayResource resource = new ByteArrayResource(bytes) {
            @Override
            public String getFilename() {
                return "report.pdf";
            }
        };

        MultipartBodyBuilder body = new MultipartBodyBuilder();
        body.part("file", resource)
            .contentType(MediaType.APPLICATION_PDF);
        return body;
    }

    @Test
    void uploadWithCsrfCanBeAccepted() {
        client().mutateWith(mockUser("alice"))
            .mutateWith(csrf())
            .post().uri("/api/files")
            .body(BodyInserters.fromMultipartData(parts().build()))
            .exchange()
            .expectStatus().isAccepted();
    }

    @Test
    void uploadMissingCsrfIsRejected() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/api/files")
            .body(BodyInserters.fromMultipartData(parts().build()))
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Các test trên cần fake `ReactiveFileIngestionService` chấp nhận PDF fixture và trả UUID; payload `%PDF-1.7\nfixture` **không phải PDF hoàn chỉnh**, không dùng làm parser/AV integration fixture. Mục tiêu ở đây là kiểm CSRF filter, không phải kiểm signature/scan.

### 20.2. M2M Bearer đúng scope trên WebFlux

Khi triển khai `POST /integrations/files` cùng staging policy, có thể dùng:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@Test
void m2mBearerCanUploadWithoutCsrf() {
    client().mutateWith(mockJwt()
            .jwt(jwt -> jwt
                .subject("partner-service")
                .claim("client_id", "partner-42"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_files:write")))
        .post().uri("/integrations/files")
        .body(BodyInserters.fromMultipartData(parts().build()))
        .exchange()
        .expectStatus().isAccepted();
}
~~~

Đặt method trong class có `client()`/`parts()`. `mockJwt()` chỉ giúp kiểm web security authorities; nó **không chứng minh JWT decoder xác minh signature/issuer/audience thật**. Cần signed token/test issuer integration riêng.

### 20.3. Reactive download wrong owner và status

~~~text
A. GET /api/files/{id}/download với mockUser("alice"),
   fixture file thuộc Alice và AVAILABLE:
      -> 200, Content-Disposition attachment,
         Cache-Control no-store, bytes đúng phiên bản.

B. GET cùng ID với mockUser("bob") hoặc tenant khác:
      -> 403 hoặc 404, không lộ bytes, size và filename.

C. GET với owner nhưng status SCANNING:
      -> không có bytes, status theo contract.

D. HEAD hoặc Range cùng ID với user không quyền:
      -> vẫn bị authorize; không leak metadata/bytes.

E. GET qua resource streaming bị hủy subscription:
      -> đóng stream, release DataBuffer và dọn tài nguyên.
~~~

Không dùng `mockUser()` để suy luận WebSession cookies/CSRF token thật: test HTTP nhiều request với login/session cookie jar tách biệt là bước khác. Nếu test dùng service mock trả file cho mọi người, nó **không chứng minh object-level authorization**.

### 20.4. Kiểm thử giới hạn thực tế của WebFlux

Unit/WebTestClient test với vài KB bytes không chứng minh:

- multipart reader giới hạn số part/disk usage;
- upload 20 MiB thật dưới concurrent load;
- parser/scanner blocking không chiếm Reactor event loop;
- backpressure khi downstream chậm;
- cleanup khi client abort giữa file;
- `DataBuffer` release đúng trên error/cancel;
- Range/streaming qua object-store SDK.

Cần integration/load tests với embedded server thật, mock scanner có timeout, storage quota nhỏ và các counter/metrics. Chặn request lớn ở edge và reactive decoder không chỉ controller.

## 21. Browser và HTTP integration end-to-end

### 21.1. Luồng browser có session cookie

Trên public HTTPS origin, với tài khoản test/dữ liệu có thể reset:

1. Mở trang upload thật và xác minh file picker/multipart form; quan sát `_csrf` hoặc endpoint cấp token cho SPA.
2. Đăng nhập, xem cookie có `Secure; HttpOnly; SameSite` phù hợp và không bị browser chặn.
3. POST file nhỏ hợp lệ với cùng session cookie và **CSRF token đúng**; kỳ vọng `202` và metadata QUARANTINED.
4. Dùng ID đó hỏi status; file **chưa được download** trong lúc SCANNING.
5. Giả lập scanner trả CLEAN và publish **đúng object version**; owner download được với `Content-Disposition: attachment`, `nosniff` và cache policy.
6. Từ browser context B/user Bob/tenant khác, GET cùng ID; bị từ chối, không có bytes, tên hay hash nhạy cảm.
7. Từ user Alice gửi lại POST **không có CSRF**; bị chặn, DB/quarantine không có record mới.
8. Từ Alice gửi token giả hoặc token của session B; bị chặn, không tạo file.
9. Gửi file sai MIME/extension, SVG/HTML fixture, tên chứa traversal, file quá size; kiểm tra tầng từ chối và cleanup.
10. DELETE file có/không CSRF, sau khi xóa không download được; signed URL (nếu có) phải theo revocation policy đã ghi.
11. Mở nhiều tab, logout ở tab A và upload ở tab B; session/token cũ bị xử lý an toàn.
12. Lặp trên browser được hỗ trợ và với proxy thật, không chỉ gọi localhost Spring.

### 21.2. Browser khác origin: kiểm preflight và cookies

Nếu SPA ở `https://spa.example.com` gọi upload API ở `https://api.example.com`:

~~~http
OPTIONS /api/files HTTP/1.1
Origin: https://spa.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: x-csrf-token
~~~

Preflight OPTIONS **không nên cần session cookie**. Sau khi CORS cho phép, browser gửi POST có cookie theo `credentials: "include"`, SameSite/Secure/Domain/Path và chính sách third-party cookie. Nếu API dùng `CookieCsrfTokenRepository` ở API host khác, JS SPA có thể không đọc cookie host-only; endpoint JSON/token transport cần thiết kế tương ứng.

**Phân biệt:** Preflight fail thường khiến browser **không gửi actual POST**; CSRF fail xảy ra **khi POST thật đã đến Spring**. Không xem mọi lỗi “Failed to fetch” là CSRF.

### 21.3. M2M Bearer integration

1. Dùng **Authorization Server/test issuer** phát access token đúng issuer/audience/scope `files:write`.
2. POST multipart qua `/integrations/files` bằng header Bearer, không cookie; file vào quarantine và scan như browser upload.
3. Thử thiếu token, sai signature, sai `iss`, sai `aud`, hết hạn, thiếu scope; phải bị chặn trước staging.
4. Gửi **cookie browser đã đăng nhập thật** tới M2M endpoint nhưng không Bearer; không được xác thực.
5. Thử token partner A ghi file vào tenant B; service phải từ chối.
6. GET file bằng `files:read`, kiểm ACL và response header/bytes.
7. Cố dùng token trong URL/query thay vì header; nếu thiết kế header-only phải bị từ chối.
8. Kiểm tra không có token/session/URL chữ ký trong logs.

### 21.4. Cặp kiểm thử BOLA cụ thể

~~~text
Alice, tenant-A:
  POST /api/files -> id=F1
  scanner mark F1 AVAILABLE
  GET /api/files/F1/download -> 200

Bob, tenant-B:
  GET /api/files/F1 -> 403/404
  HEAD /api/files/F1/download -> 403/404
  GET /api/files/F1/download (Range: bytes=0-10) -> 403/404
  Không request nào lộ bytes, filename, length, ETag của F1.
~~~

Nếu test chỉ assert file ID là UUID không đoán được, chưa kiểm tra authorization. **Cho Bob biết ID F1** là một cách kiểm BOLA đúng: quyền không được phụ thuộc việc attacker có biết ID hay không.

## 22. Chẩn đoán những lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Upload trả `413` trước controller | Nginx/client_max_body_size hoặc container multipart limit | So response edge/Spring, proxy logs đã che bí mật |
| Upload `403` với session cookie | CSRF thiếu/sai, token trước login, thiếu quyền hoặc policy khác | Xem exception Security, cookie, CSRF header/token handler |
| Upload `401` | Chưa auth hoặc session cookie không được browser gửi | Kiểm tra Cookie/Set-Cookie, Secure/SameSite/Path, chain |
| Upload `415` | Multipart Content-Type/consumes hoặc media policy không hỗ trợ | Kiểm tra boundary, per-part MIME và endpoint contract |
| Upload `400` sau FormData | JS tự set multipart Content-Type không có boundary | Để browser tự tạo Content-Type khi dùng FormData |
| POST tới /integrations trả HTML login | Wrong security chain/form entry point | Kiểm tra order/securityMatcher/proxy rewrite |
| M2M Bearer token đủ scope nhưng `403` | Partner/tenant ACL hoặc authority mapping sai | Kiểm tra client identity, scope và resource binding |
| M2M cookie-only upload thành công | Auth fallback qua session/gateway | Loại fallback hoặc áp CSRF, test cookie-only |
| File tên `../...` ghi ra ngoài thư mục | Dùng originalFilename như path | Dùng server-generated object key, path confinement |
| File HTML đổi tên .png được phát inline | Tin extension/client MIME, thiếu attachment/nosniff | Detect content, quarantine, isolated preview origin |
| Browser tải file nhưng phát script trong app origin | Untrusted content phục vụ cùng app host | Dời sang isolated origin, attachment/CSP/scan |
| Scanner báo CLEAN nhưng byte bị đổi | TOCTOU/object version không cố định | Scan immutable version, publish atomic pointer |
| Upload thành công nhưng không download được | File còn QUARANTINED/SCANNING hoặc ACL chưa cấp | Query metadata state và policy; không bypass scan |
| Download file khác user được | BOLA/IDOR: check auth nhưng không check file ownership | Truy vấn theo ID+tenant/ACL, test Bob biết ID Alice |
| Download `404` ngẫu nhiên giữa nodes | Metadata/object propagation, storage path local-only | Shared storage/version, eventual consistency policy |
| Browser nhận file sai tên/ký tự lỗi | Content-Disposition không encode/escape | Dùng Spring ContentDisposition builder và sanitized filename |
| HEAD trả 200 metadata dù GET bị 403 | Bypass auth ở HEAD/static route | Áp cùng file ACL cho HEAD/Range/GET |
| Range 206 bị sai Content-Length | Converter/object/proxy nén hoặc range math sai | Test byte offsets, Content-Range, immutable version |
| CDN trả file Alice cho Bob | Public/shared cache key không chứa auth scope | No-store/private hoặc signed edge authorization |
| Signed URL bị dùng sau revoke | URL còn TTL, không có revocation | TTL nhỏ hơn, version invalidation hoặc proxy auth |
| Object store CORS error | Direct browser upload sang storage origin chưa allowlist | Xem preflight tại storage, signed policy và Origin |
| Upload lớn làm đầy temp disk | Proxy/container buffer trước auth, thiếu quota/cleanup | Temp dir metrics, max body/parts/time, concurrent caps |
| ZIP vài KB làm cạn RAM | ZIP bomb hoặc decoder dimension limit | Uncompressed quota, pixel count, sandbox/timeout |
| ZIP giải nén ghi file ngoài root | Zip Slip/path symlink | Check entry path và confinement, sandbox |
| Reactive upload làm nghẽn event loop | Blocking parser/file system/storage trong reactive pipeline | Tracing scheduler, chuyển boundedElastic/worker |
| Reactive stream leak memory | DataBuffer release/cancel handling thiếu | Leak detection, cancel/abort tests, backpressure |
| GET download trả JSON/HTML index.html 200 | Proxy SPA fallback chặn đường API | Tách API routes, giữ backend status và Content-Type |
| CORS error chỉ ở response `413`/`403` | Error path ở proxy/filter thiếu CORS headers | So OPTIONS/actual response, không mở wildcard |
| User hết phiên sau upload lâu | Session TTL/cookie changes hoặc app timeout | UX reauth/retry có kiểm soát, tránh duplicate upload |
| Signed upload “complete” nhưng object sai | Client báo thành công, server không HEAD/verify | Verify size/digest/key/version từ storage trước scan |
| File bị orphaned sau scanner timeout | Không có compensating cleanup/retry TTL | Outbox/idempotent worker/reconciliation jobs |
| Token/cookie lộ trong logs | Debug logging multipart/request headers quá rộng | Redact Authorization/Cookie/CSRF/URLs chữ ký |

### 22.1. Phân biệt 401, 403, 413, 415 và 502

- **401:** xác thực thiếu/không hợp lệ; không liên quan tới loại file nếu request chưa qua auth.
- **403:** có thể do CSRF, thiếu quyền endpoint, thiếu quyền theo file hoặc WAF; xem chain và exception.
- **413:** body vượt limit ở edge/container; controller có thể không chạy.
- **415:** media type request không phù hợp endpoint `consumes`, hoặc policy của ứng dụng có thể trả theo contract.
- **422:** một ứng dụng có thể chọn cho file có nội dung hợp lệ về HTTP nhưng không đạt kiểm định nghiệp vụ/format; không phải default chung.
- **429:** rate/quota theo request concurrency, cần retry/backoff policy.
- **502/504:** proxy/upstream hoặc timeout; không phải bằng chứng CSRF.
- **CORS error:** browser có thể không cho JavaScript đọc status/body, kể cả khi server đã trả 403/413.

### 22.2. Thứ tự đọc Network và backend evidence

~~~text
1. Public URL/method/Origin/headers đúng không?
2. CORS preflight có thực hiện và được phép không?
3. Body có tới edge hay bị 413/timeout?
4. Security chain nào được chọn?
5. Browser cookie hoặc M2M Bearer có được chấp nhận không?
6. Với unsafe browser request, CSRF được kiểm tra không?
7. Principal có quyền upload hoặc đọc đúng file/tenant không?
8. Multipart/file validation và quota từ chối gì?
9. File đã vào quarantine/scan/approved state nào?
10. Download response headers/cache/Range đúng chưa?
11. DB/object state có thay đổi khi request thất bại không?
12. Logs có redact token/cookie/signed URL và file payload chưa?
~~~

Đừng sửa lỗi khác tầng bằng cách tắt `csrf`, mở CORS cho mọi origin hoặc làm public storage bucket.

## 23. Checklist kiến trúc và triển khai

| Hạng mục | Điều kiện đạt |
|---|---|
| **Public URL** | Route upload/download và API status rõ, không lẫn SPA fallback |
| **TLS/edge** | HTTPS, certificate hợp lệ, HSTS theo policy, request body/time limits |
| **Multipart** | Giới hạn per file, tổng request, part count, temp disk, concurrency |
| **Authentication** | Browser session hoặc M2M Bearer đúng chain, không có fallback ngoài ý muốn |
| **CSRF** | Browser POST/DELETE có token hợp lệ; M2M chỉ miễn trên bearer-only chain đã test |
| **CORS** | Chỉ origin cần thiết; preflight được xử lý trước auth khi có cross-origin browser |
| **Object-level ACL** | Query ID + principal/tenant/resource rights trước metadata/bytes |
| **File name** | Tên gốc là untrusted metadata; storage key do server tạo |
| **Storage root** | Private, ngoài static web root; path confinement và symlink/TOCTOU policy |
| **File types** | Allowlist theo nghiệp vụ; kiểm bytes/format, không chỉ extension/MIME |
| **Quarantine** | Không public/read khi chưa scan; bucket/temp private |
| **Scanner** | AV/CDR/sandbox có CPU/memory/time limits và retry idempotent |
| **State machine** | RECEIVING/QUARANTINED/SCANNING/AVAILABLE/REJECTED/REVOKED rõ |
| **Atomic publish** | Chỉ đúng object version đã được scan là AVAILABLE |
| **Quota** | Per user/tenant, tổng bytes, số file, requests concurrent, cleanup |
| **Resource streaming** | Không đọc file lớn toàn bộ vào heap; WebFlux không block event loop |
| **Download headers** | Attachment + Content-Type từ policy + nosniff + cache riêng tư |
| **Browser isolation** | Untrusted active content không render cùng app origin tùy tiện |
| **Range/HEAD** | Dùng cùng file-level authorization và object version |
| **Signed URLs** | TTL/method/key/version chặt, logs không lưu chữ ký, revocation được hiểu rõ |
| **CDN/cache** | Không phục vụ file private cho user/tenant khác |
| **Error semantics** | 401/403/404/409/413/415/422/429 có hợp đồng và không lộ thông tin |
| **Reverse proxy** | Không bỏ header/cookie, không rewrite sai URI, không che status |
| **Logging** | Không log file payload, Bearer/session/CSRF/presigned URL nhạy cảm |
| **Regression tests** | Upload token đúng/sai, wrong tenant, scanner reject, Range, headers, cleanup |
| **Operations** | Temp/storage metrics, AV queues, orphan cleanup, incident response |
| **Lifecycle** | Delete/revoke/retention/legal-hold theo chính sách dữ liệu |

## 24. Bài tập thực hành

### Bài 1 — Upload avatar bị bỏ qua kiểm tra định dạng

Một endpoint cho phép đuôi `.png`, giới hạn 5 MiB. Người dùng đổi tên HTML chứa JavaScript thành `avatar.png` và tải lên; ứng dụng trả file đó inline tại `/uploads/avatar.png` cùng origin.

**Yêu cầu:** Chỉ ra ít nhất ba lớp thiếu.

**Gợi ý giải:** Phải kiểm bytes/format ảnh thay vì tin extension/MIME, giữ private quarantine/scan hoặc rasterize qua worker, không serve active content inline cùng app origin; dùng Content-Disposition, nosniff, CSP/isolated content origin và file-level ACL.

### Bài 2 — ID là UUID thì có cần ACL?

Alice có file ID ngẫu nhiên. Bob nhận được ID từ một đường link chia sẻ nhưng không được Alice cấp quyền; `GET /api/files/{id}/download` chỉ kiểm user đã login.

**Gợi ý:** Đây là BOLA/IDOR. ID khó đoán không phải authorization. Query metadata theo ID + owner/tenant/permission, không trả byte, filename, size/ETag khi Bob không có quyền.

### Bài 3 — Upload trả 413 ở Nginx

Browser gửi file 30 MiB; Spring Boot có `spring.servlet.multipart.max-file-size: 50MB` nhưng vẫn nhận 413.

**Gợi ý:** Kiểm tra edge `client_max_body_size`, các giới hạn body ở gateway/container và nơi tạo response. Không tắt CSRF; Spring controller có thể chưa bao giờ được chạy.

### Bài 4 — M2M có Bearer nhưng không cần scan?

Một worker có JWT đúng signature, issuer, audience và `files:write` gửi tệp chứa mã độc thử nghiệm.

**Gợi ý:** Authentication/authorization cho phép **ai upload**, không xác minh **bytes an toàn**. Vẫn phải áp size/type/quota, quarantine, scanner/processor và tenant ACL. CSRF chỉ là một lớp của browser, không liên quan tới malware.

### Bài 5 — File chưa scan có thể download?

Upload trả `202` với ID F1. Endpoint GET download chỉ kiểm user là owner và đọc object ngay, dù state vẫn `SCANNING`.

**Gợi ý:** Phải kiểm state `AVAILABLE`/approved object version trước khi trả bytes; metadata status có thể được owner đọc nhưng không được giải phóng file sớm. Test race giữa scan/publish/download.

### Bài 6 — Direct upload bằng presigned URL

API trả presigned PUT vào bucket public, client được chọn key và ACL. Sau upload, client POST complete khai báo file đã an toàn.

**Gợi ý:** Nguy cơ public exposure, ghi đè object, bypass quota/scan và tin metadata client. Server cấp private quarantine key có scope/TTL, verify object size/hash/version bằng storage API, scan rồi publish atomically, cleanup slots hết hạn.

### Bài 7 — Range bypass quyền

GET toàn file kiểm ACL, nhưng GET Range tại route khác đọc thẳng object bằng file ID, Bob có thể tải nhiều phần rồi ghép file của Alice.

**Gợi ý:** Mọi Range/HEAD/conditional path phải dùng cùng authorization và approved object version trước khi trả bất cứ byte/metadata nào.

### Bài 8 — Zip bomb và Zip Slip

Một ZIP 2 MiB chứa hàng trăm nghìn entry với tên `../../config` và kích thước giải nén nhiều GB.

**Gợi ý:** Giới hạn tổng uncompressed bytes, entry count, nesting, CPU/memory, kiểm confinement sau normalize, kiểm symlink, sandbox worker. Không giải nén file không tin cậy với quyền ghi filesystem chính của ứng dụng.

### Bài 9 — WebFlux upload làm chậm toàn hệ thống

Controller nhận `FilePart` rồi gọi `DataBufferUtils.join` mọi bytes, decode PDF và scan virus trong cùng reactive pipeline trên event loop.

**Gợi ý:** Tránh buffer toàn file, stream/`transferTo` private quarantine có giới hạn, chuyển blocking parser/AV sang boundedElastic/worker, áp backpressure/cancellation cleanup.

### Bài 10 — Sau logout user vẫn dùng signed URL

Alice lấy presigned GET URL có TTL 24 giờ. Sau khi admin thu hồi quyền của Alice, URL vẫn tải được file.

**Gợi ý:** URL đã cấp là bearer capability; logout/revoke trong app không chắc hủy URL. Giảm TTL, dùng object-version invalidation/edge authorization hoặc stream qua API kiểm quyền mỗi request khi cần revocation tức thời. Đừng log/chia sẻ link ký.

## 25. Câu hỏi tự đánh giá

**1.** Spring Security xác thực thành công một POST upload đã đủ bảo đảm file an toàn chưa?

**Đáp án:** Chưa. Authentication chỉ xác định caller; vẫn cần file-level authorization, size/quota, format detection, quarantine, scan/processor và response policy.

**2.** Vì sao `getOriginalFilename()` không nên dùng làm storage path?

**Đáp án:** Tên được client cung cấp có thể chứa traversal, separator, ký tự điều khiển, path tuyệt đối hoặc trùng tên. Server phải tự tạo key/path, còn original name chỉ là metadata hiển thị.

**3.** `Content-Type: image/png` do client gửi có được tin để quyết định serve inline không?

**Đáp án:** Không. MIME do client khai không chứng minh bytes đúng loại. Cần content detection/parser validation và quyết định attachment/preview ở server.

**4.** Một user được phép upload vào tenant A có tự được download mọi file tenant A không?

**Đáp án:** Không tự động. Download cần quyền đọc trên file/resource cụ thể, áp ACL của nghiệp vụ; phân quyền upload không đồng nghĩa được xem mọi object.

**5.** Nếu SPA sử dụng session cookie, upload POST có còn cần CSRF token không?

**Đáp án:** Có. Browser tự gửi cookie phù hợp, còn CORS/SameSite không thay anti-CSRF cho unsafe operations. CSRF token phải được Spring Security kiểm chứng.

**6.** Một API M2M chỉ nhận Bearer header có thể miễn CSRF không?

**Đáp án:** Có thể, **sau khi chứng minh bearer-only** và không có cookie/Basic/gateway fallback; vẫn cần issuer/audience/scope, object ACL, quotas và scanning.

**7.** Lỗi `413` ở reverse proxy có nghĩa Spring Security đã reject CSRF không?

**Đáp án:** Không. Edge có thể chặn body vì vượt max size trước khi request vào Security filters; cần kiểm tra nơi phát status và limits từng tầng.

**8.** ZIP bomb khác Zip Slip thế nào?

**Đáp án:** ZIP bomb gây cạn tài nguyên khi giải nén, còn Zip Slip lợi dụng entry path/links để ghi ngoài extraction root. Cần limits và path confinement/sandbox riêng.

**9.** Vì sao một file scan CLEAN vẫn nên download qua attachment/nosniff hoặc content origin cách ly?

**Đáp án:** AV CLEAN không bảo đảm file không có active content/XSS/polyglot hay lỗ hổng viewer. Response/browser origin là một lớp phòng vệ độc lập.

**10.** `GET /api/files/{id}/download` đã kiểm ACL, vậy HEAD/Range có thể không kiểm để tăng hiệu năng không?

**Đáp án:** Không. HEAD/Range vẫn có thể tiết lộ size, ETag hoặc bytes; phải dùng cùng ACL và approved object version.

**11.** Tại sao UUID file ID không thể thay quyền đọc?

**Đáp án:** ID có thể lộ qua link/log, đoán ngẫu nhiên cũng không phải bằng chứng ủy quyền. Server phải kiểm principal/tenant/file ACL.

**12.** Presigned URL có thể tiếp tục hoạt động sau khi quyền user bị revoke không?

**Đáp án:** Có thể, tới TTL nếu không có revocation mechanism. URL là capability theo possession, cần expiry/scope ngắn hoặc kiểm quyền mỗi lần khi yêu cầu.

**13.** Có thể dùng `Files.readAllBytes` trong download file vài GB không?

**Đáp án:** Không nên, vì phải giữ toàn bộ bytes trong heap. Dùng Resource/streaming thích hợp và xử lý cancellation/connection abort.

**14.** Với WebFlux, vì sao không nên dùng blocking parser hoặc scanner trên event loop?

**Đáp án:** Nó có thể chặn event loop và làm giảm khả năng phục vụ nhiều request. Dùng worker/scheduler phù hợp, giới hạn CPU/memory/time và streaming/backpressure.

**15.** CORS của object storage có thay chữ ký presigned PUT hay quyền user không?

**Đáp án:** Không. CORS kiểm hành vi browser cross-origin; quyền ghi phải được ràng buộc bởi capability/signature, bucket policy và backend authorize phát link.

**16.** Nếu download response trả `Content-Disposition: attachment`, có thể tắt scan và ACL không?

**Đáp án:** Không. Disposition chỉ ảnh hưởng cách client xử lý response, không kiểm malware hay quyền truy cập.

**17.** Khi scanner timeout sau upload, file nên chuyển thành AVAILABLE vì chưa phát hiện malware không?

**Đáp án:** Không. Timeout không phải kết quả CLEAN. Giữ SCAN_FAILED/QUARANTINED và retry có giới hạn/alert, không public.

**18.** CSRF filter luôn chạy trước mọi byte được ghi vào temp multipart file trong Servlet đúng không?

**Đáp án:** Không thể khẳng định; tùy multipart parser, filter ordering và container. Cần kiểm thử kết hợp edge size/part limits, temp quotas và cleanup.

**19.** Một HTTP 403 khi upload luôn nghĩa token CSRF sai không?

**Đáp án:** Không. Nó có thể do CSRF, thiếu quyền route, object ACL, WAF hoặc security policy; kiểm tra chain, exception và trạng thái request ở từng tầng.

**20.** Trách nhiệm cuối cùng về việc Bob đọc file Alice thuộc lớp nào?

**Đáp án:** Ứng dụng/domain service phải thực thi **object-level authorization** trước khi mở/stream dữ liệu; security chain chỉ đảm bảo caller đã được xác thực và có role/scope ở mức route, còn storage/cache phải tôn trọng quyết định đó.

## Kết luận

**Upload và download là luồng xử lý dữ liệu nhiều lớp**, từ client và browser policy, TLS edge/reverse proxy, HTTP multipart parser, Spring Security authentication/CSRF/CORS, domain authorization đến private storage, scanner/processor và response headers. Bỏ qua một ranh giới có thể dẫn đến CSRF, BOLA/IDOR, path traversal, malware phát tán, stored XSS, DoS hoặc data leak qua cache/signed URLs.

Trong **Servlet/Spring MVC**, dùng `HttpSecurity`/`SecurityFilterChain`, `MultipartFile` và `ResponseEntity<Resource>`; trong **Reactive/WebFlux**, dùng `ServerHttpSecurity`/`SecurityWebFilterChain`, `FilePart` và publisher/resource streaming. Browser dùng session cookie cần CSRF token trên POST/DELETE; M2M Bearer-only chỉ có thể miễn CSRF khi không có ambient credential fallback. Cả hai đều phải kiểm quota, nội dung file, trạng thái quarantine/scan và **quyền truy cập từng file/tenant**.

Các header như **Content-Disposition, Content-Type, nosniff, CSP, HSTS và Cache-Control** giúp browser xử lý output an toàn hơn nhưng không thay quyền truy cập hoặc scan. Nếu dùng direct object storage, cần phát presigned capabilities ngắn hạn, verify object version/checksum, giữ quarantine private và hiểu giới hạn thu hồi signed URLs.

Bài học thuộc module **SPRING_SECURITY_HTTP_PROTECTION** và chương **Tích hợp ứng dụng** nhấn mạnh nguyên tắc: **chỉ công bố bytes đã được xác minh và chỉ cho đúng principal được quyền đọc**, trong khi mọi bước đều có giới hạn tài nguyên, test âm/dương và cleanup. STEP 4 là bước soạn tài liệu; các ví dụ cần được điều chỉnh và kiểm thử theo Spring Security/Boot version, hạ tầng và chính sách dữ liệu thực tế.

## Tài liệu tham khảo

- [Spring Security — CSRF Protection (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF token, multipart/form-data, deferred token và SPA.
- [Spring Security — CSRF Protection (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): `CsrfWebFilter` và WebSession.
- [Spring Security — Servlet Request Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request authorization và security matcher.
- [Spring Security — Reactive Request Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): WebFilterChain và authorization.
- [Spring Security — Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): browser preflight và filter ordering.
- [Spring Security — HTTP Security Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): CSP, HSTS và nosniff.
- [Spring Framework — Multipart Requests (MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): `MultipartFile` và multipart controllers.
- [Spring Framework — Multipart Content (WebFlux)](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html): `FilePart` và multipart processing.
- [Spring Framework — HTTP Range Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): `ResponseEntity<Resource>` và ranges theo framework support.
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): file type validation, malware, storage isolation, filenames, limits.
- [OWASP — Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal): đường dẫn do attacker kiểm soát.
- [OWASP — Insecure Direct Object Reference Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): authorization theo từng object.
- [MDN — Content-Disposition](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Disposition): attachment và filename.
- [MDN — X-Content-Type-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Content-Type-Options): `nosniff` và giới hạn MIME sniffing.
- [MDN — HTTP Range requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Range_requests): 206, Content-Range và 416.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): method semantics, header và status codes.
