# Secure coding

**Secure coding** là thực hành viết, xem xét, kiểm thử và duy trì mã nguồn sao cho phần mềm thực thi đúng các mục tiêu bảo mật trong những điều kiện sử dụng bình thường, bất thường và có chủ đích lạm dụng. Một chương trình viết đúng chức năng chưa chắc đã an toàn: API trả dữ liệu đúng cho giáo viên hợp lệ có thể vẫn cho phép một giáo viên khác thay mã lớp để xem thông tin học viên; job xử lý file hợp lệ có thể bị lợi dụng để đọc file ngoài thư mục cho phép; ứng dụng xác thực tốt vẫn có thể ghi token vào log.

Trong chương **Secure development**, secure coding nằm giữa thiết kế kiến trúc, threat modeling, security requirements, code review, testing, release và vận hành. Bài học đặt trong module **SECURITY_SECURITY_ASSURANCE**, với mục tiêu xây dựng cách **đánh giá có bằng chứng** rằng hệ thống đáp ứng các mục tiêu bảo mật, từ phân tích rủi ro, yêu cầu, controls đến kiểm thử, audit, khắc phục phát hiện và assurance liên tục trong phát triển/vận hành. Vì vậy, không chỉ dừng ở “viết code không có lỗi”, bài học hướng dẫn liên kết **rủi ro → yêu cầu bảo mật → coding control → test/evidence → kết luận có phạm vi → remediation/retest**.

Ngữ cảnh xuyên suốt là nền tảng học trực tuyến xây dựng bằng Java/Spring, có người học, giảng viên, nhiều tổ chức/tenant, chức năng nộp bài, xem điểm, gửi thông báo, tạo báo cáo và tích hợp dịch vụ ngoài. Các đoạn code là **ví dụ minh họa**: có thể cần bổ sung class, annotation, framework configuration và error handling để chạy trong một dự án thật. Không được coi việc sao chép một đoạn code đơn lẻ là chứng cứ toàn bộ dịch vụ đã an toàn.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích secure coding, attack surface, trust boundary, input validation, authentication, authorization, output encoding và defense in depth.
2. Phân biệt lỗi chức năng, bug bảo mật, lỗ hổng có thể bị khai thác và security assurance evidence.
3. Nhận diện các lớp rủi ro như injection, broken access control/BOLA, XSS, CSRF, SSRF, path traversal, insecure deserialization, secret exposure và unsafe error handling.
4. Thiết kế các controls phòng ngừa trong Java và service APIs, ưu tiên thư viện/khả năng an toàn của framework thay vì tự viết cơ chế mật mã hoặc authentication.
5. Áp dụng tenant/resource-level authorization, least privilege, data minimization và bảo vệ thông tin nhạy cảm ở mọi tầng.
6. Hiểu các rủi ro khi xử lý file upload, URL ngoài, JSON, logs, exceptions, concurrency và công việc bất đồng bộ.
7. Xây secure coding checklist cho pull request và đường CI/CD thích hợp với rủi ro.
8. Thiết kế positive, negative, integration, property-based và fuzz tests khi cần, bao gồm kiểm tra side effects.
9. Phân biệt vai trò SAST, DAST, SCA, secret scanning, IaC scanning, manual review và penetration testing.
10. Viết security claim có tiêu chí rõ, xác định evidence và giới hạn của kết luận.
11. Quản lý security findings, false positives, exceptions, remediation, retest và regression.
12. Tổ chức continuous secure coding assurance qua các vòng thay đổi code, thư viện, cấu hình và runtime.

## 2. Secure coding giải quyết vấn đề gì?

### 2.1. Chức năng đúng không đồng nghĩa an toàn

Một API cho phép người học xem bài đã nộp:

~~~http
GET /api/v1/submissions/6142
Authorization: Bearer <access-token>
~~~

Đây chỉ là cú pháp minh họa. HTTP 200 khi chủ bài truy cập chứng minh luồng hợp lệ hoạt động, nhưng chưa trả lời các câu hỏi:

- Người học A thay submission ID của người học B thì sao?
- Access token hết hạn, bị sửa chữ ký hoặc cấp cho ứng dụng khác có được chấp nhận không?
- API có trả cả ghi chú nội bộ của giảng viên không?
- Log có ghi Authorization header hoặc nội dung bài làm không?
- Có endpoint batch/export, cache, GraphQL hoặc worker nào bỏ qua kiểm tra quyền không?
- Tài khoản vừa bị thu hồi quyền thì session và cached authorization có thay đổi theo chính sách không?
- Khi database hoặc authorization service lỗi, API có fail-open không?

**Secure coding** đưa các câu hỏi này vào thiết kế và code, còn **security assurance** thu bằng chứng để kiểm chứng chúng.

### 2.2. Ba lớp thường phải đánh giá

| Lớp | Nội dung | Ví dụ evidence |
|---|---|---|
| **Secure design** | Yêu cầu, trust boundaries, security assumptions, threats và controls | Threat model, design review, policy |
| **Secure implementation** | Code/config thực hiện controls và xử lý dữ liệu đúng | Source diff, PR review, build artifact, tests |
| **Secure operation** | Controls tiếp tục hoạt động trong release, môi trường và kỳ đánh giá | Deployment mapping, log/monitoring, runtime tests, incidents |

Một unit test pass ở nhánh phát triển **không tự chứng minh** production đang chạy build có cùng code/config. Một chứng nhận hoặc chính sách nội bộ **không tự chứng minh** authorization đã được thực thi trên mọi endpoint.

### 2.3. Mục tiêu bảo mật và tác động

Secure coding có thể bảo vệ:

- **Confidentiality:** dữ liệu điểm, bài nộp, token, secret và hồ sơ cá nhân không bị tiết lộ ngoài quyền.
- **Integrity:** không thể sửa điểm, bài nộp, vai trò, trạng thái thanh toán hoặc nội dung báo cáo trái quyền.
- **Availability:** một input bất thường không làm ứng dụng cạn CPU, memory, connection hay queue capacity.
- **Authenticity:** danh tính user/service và nguồn request/message không bị giả mạo.
- **Accountability:** hành động quan trọng có thể truy vết với audit events đáng tin, không lộ dữ liệu thừa.
- **Privacy:** dữ liệu được thu, dùng, chia sẻ và giữ theo mục đích/quyền được duyệt, không chỉ được mã hóa.

## 3. Tư duy threat-first, không checklist-first

### 3.1. Từ tài sản đến kịch bản lạm dụng

Ví dụ mục tiêu: **chỉ giảng viên được phân công mới có thể xuất điểm lớp của mình**.

Thay vì chỉ đánh dấu “đã dùng Spring Security”, cần liệt kê:

1. **Asset:** điểm và dữ liệu nhận diện học viên.
2. **Actor:** giáo viên, học viên, quản trị viên, report worker.
3. **Entry points:** API export, UI, queue, scheduled job, signed download URL.
4. **Trust boundaries:** browser → API → queue → worker → database/storage.
5. **Threat:** giáo viên hợp lệ sửa classId; queue job bị giả mạo hoặc replay; worker có quyền quá rộng.
6. **Security requirements:** xác thực người yêu cầu, kiểm tra quyền lớp, giới hạn dữ liệu/tenant, bảo vệ queue, idempotency và quyền tải file.
7. **Controls:** server-side authorization, worker scoping, private object storage, TTL, audit, quotas.
8. **Tests:** user thuộc lớp khác, forged job, stale session, duplicate message, link hết hạn.
9. **Evidence:** test run theo commit/build, effective IAM policy, log, code review và runtime checks.
10. **Residual risk:** đường legacy chưa có test hoặc vendor ngoài phạm vi.

### 3.2. Threat model không thay code review

Threat modeling giúp dự đoán **đường tấn công và điểm cần bảo vệ**. Code review giúp xác định implementation có đúng mục tiêu không. Runtime tests xác minh những giả định không thể suy ra chỉ từ code.

Một threat model không ghi đến SSRF không chứng minh SSRF không tồn tại; một linter không tìm thấy injection cũng không chứng minh mọi câu truy vấn đều dùng parameter binding.

### 3.3. Secure coding theo trust boundaries

~~~mermaid
flowchart LR
    U["Browser / Mobile"] -->|"Untrusted request"| G["Gateway"]
    G -->|"Authenticated context"| A["Java API"]
    A -->|"Authorized SQL"| D[("Learning DB")]
    A -->|"Scoped job"| Q[["Queue"]]
    Q -->|"Validated event"| W["Report Worker"]
    W -->|"Private object"| S[("Object Storage")]
    A -->|"Approved payload"| V["External Vendor"]
~~~

Ở mỗi đường đi, cần phân biệt **source identity**, **input validity**, **permission**, **data sensitivity** và **response behavior**. Không nên coi dữ liệu trở thành đáng tin hoàn toàn chỉ vì đã đi qua gateway hoặc bắt nguồn từ service nội bộ.

## 4. Secure coding principles

### 4.1. Least privilege

Mỗi người dùng, service, database role, job và API credential chỉ có quyền cần để làm nhiệm vụ, trong scope và thời gian phù hợp.

Ví dụ report worker cần quyền đọc dữ liệu được duyệt và ghi object theo tenant; không cần quyền quản trị toàn database hoặc liệt kê toàn bộ bucket.

### 4.2. Complete mediation

Mỗi truy cập đến tài sản quan trọng đều cần authorization theo policy. Không chỉ kiểm tra lúc UI hiện nút “Export” mà bỏ qua API, queue, worker, cache hoặc download URL.

### 4.3. Fail securely

Nếu không thể xác minh quyền cho thao tác nhạy cảm, không tự chuyển thành allow. Với một số chức năng cần degraded mode, phải thiết kế **chức năng nào còn được dùng, giới hạn dữ liệu nào, thời hạn và audit**.

### 4.4. Defense in depth

Kết hợp validation, identity, authorization, parameterized queries, network policy, least privilege, output encoding, logging và alerting. Mỗi lớp hạn chế một số failure modes; không dùng sự tồn tại của lớp này để bỏ lớp khác.

### 4.5. Secure defaults

Mặc định đóng đường không cần thiết, không bật debug/actuator/public bucket, không cho phép unauthenticated admin operations. Tính năng mới nên yêu cầu approval và configuration rõ khi mở rộng quyền.

### 4.6. Minimize attack surface

Giảm endpoint, parser, plugin, shared credential, dependency và quyền không cần thiết. Đường legacy/debug không còn dùng cần được xác minh và loại bỏ an toàn.

### 4.7. Don't roll your own security

Ưu tiên thư viện/framework đã được đánh giá cho password hashing, token validation, encryption, input parsing và TLS. Tự viết thuật toán hoặc bỏ certificate verification để ứng dụng “chạy được” có thể làm hỏng điều kiện bảo mật.

### 4.8. Explicit ownership and evidence

Security control phải có **owner**, yêu cầu cụ thể, test, phương pháp phát hiện drift và trigger đánh giá lại. Một đoạn code đúng nhưng không nằm trong runtime path vẫn không bảo vệ người dùng.

## 5. Phân loại dữ liệu và nguồn không đáng tin

### 5.1. Input không chỉ đến từ browser

Nguồn cần xác minh gồm:

- URL path/query/body, headers, cookies, multipart uploads.
- Webhooks/callbacks từ vendor.
- Queue messages, scheduled jobs, event streams.
- Database records được ghi bởi user hoặc nguồn khác.
- Config, environment variables, file content và secrets.
- Dependency output, LLM/model response hoặc kết quả dịch vụ ngoài.
- Dữ liệu lấy lại từ cache, search index và object storage.
- Thông tin claim/identity do gateway hoặc proxy chuyển tiếp.

Không tự coi dữ liệu “internal” là đáng tin nếu ranh giới nguồn và cơ chế kiểm chứng chưa rõ.

### 5.2. Data classification tác động tới code

| Loại dữ liệu | Ví dụ | Coding controls thường cần |
|---|---|---|
| Public | Mô tả khóa học công khai | Integrity, output encoding, abuse controls |
| Internal | Event kỹ thuật, metadata cấu hình | Authentication, scoped access, safe logging |
| Confidential | Điểm số, thông tin lớp, email | Object/tenant authz, minimization, encryption theo risk |
| Restricted/Secret | Private keys, access tokens, credentials | Secret manager, no logging, tight access/rotation |
| Derived personal data | Nhãn dự đoán, risk score | Purpose/recipient restrictions, privacy review |

Các nhãn chỉ minh họa; classification và nghĩa vụ thực tế do tổ chức xác định. Một dữ liệu có thể nhạy cảm hơn khi **kết hợp với nguồn khác hoặc chuyển mục đích**.

### 5.3. Validate tại boundary, encode khi xuất

**Input validation** kiểm tra xem dữ liệu có thuộc tập giá trị hợp lệ của business contract. **Output encoding** đảm bảo dữ liệu được biểu diễn an toàn trong ngữ cảnh sử dụng (HTML text, HTML attribute, JavaScript, URL, SQL…). Hai khái niệm **không thay thế nhau**.

SQL injection không được giải quyết bằng HTML escaping. XSS không được xử lý bằng SQL parameter binding. Mỗi interpreter/sink cần biện pháp phù hợp.

## 6. Input validation theo allowlist và contract

### 6.1. Validation nhiều tầng

- **Syntax:** loại, encoding, cấu trúc, độ dài, giới hạn kích thước.
- **Semantic:** ngày bắt đầu không sau ngày kết thúc; điểm trong thang đo.
- **Business:** người gửi có quyền yêu cầu thao tác; trạng thái cho phép.
- **Cross-field:** tổ hợp thuộc tính hợp lệ, không mâu thuẫn.
- **Resource limits:** không xử lý danh sách/số lần lặp vô hạn.
- **Canonicalization:** hiểu format và chuẩn hóa khi thích hợp trước khi so sánh.
- **Provenance:** ai gửi, có thể tin phần nào, dữ liệu có dấu hiệu bị thay đổi?

### 6.2. Ví dụ DTO validation trong Java

~~~java
public record CreateCourseRequest(
        @NotBlank
        @Size(min = 3, max = 120)
        String title,

        @NotNull
        @Min(1)
        @Max(10000)
        Integer estimatedMinutes,

        @Size(max = 5000)
        String description
) {}
~~~

Ví dụ dùng Jakarta Bean Validation annotations và cần cấu hình framework thực tế để validation chạy. Chỉ vì DTO có annotation **không chứng minh** mọi route đã kích hoạt validation hoặc business authorization.

### 6.3. Điều validation không được làm

- Không tin classId hoặc tenantId chỉ vì là số dương.
- Không chỉ kiểm tra “chuỗi không chứa dấu nháy” để chặn SQL injection.
- Không định nghĩa regex khổng lồ có nguy cơ ReDoS.
- Không tự cắt chuỗi quá dài rồi mặc định business action an toàn.
- Không dùng client-side validation làm lớp thực thi cuối cùng.
- Không trả toàn bộ field-level internal error cho user khi thông điệp có dữ liệu nhạy cảm.

### 6.4. Kiểm thử validation

| Trường hợp | Kỳ vọng |
|---|---|
| Giá trị hợp lệ ở ranh giới min/max | Được chấp nhận đúng contract |
| Null, chuỗi rỗng, Unicode bất thường | Xử lý có kiểm soát, không exception chưa quản lý |
| Số âm, overflow, NaN/Infinity khi không hợp lệ | Bị từ chối hoặc chuẩn hóa có căn cứ |
| Body cực lớn, deeply nested JSON | Giới hạn trước khi cạn tài nguyên |
| Duplicate JSON keys hoặc kiểu không khớp | Parser/contract xử lý nhất quán theo policy |
| Ký tự điều khiển, CR/LF trong header/log field | Không gây response/log injection |
| Trường không cho phép cập nhật | Không mass assignment hay bypass business policy |

## 7. Injection: tách dữ liệu khỏi lệnh

### 7.1. Cơ chế lỗi

**Injection** xảy ra khi dữ liệu do actor ít tin cậy kiểm soát được diễn giải như cú pháp lệnh/query trong một interpreter: SQL, NoSQL, OS shell, LDAP, template, expression language hoặc một hệ thống truy vấn khác.

Một lỗi thường gặp là ghép input trực tiếp vào query:

~~~java
// Anti-pattern: data bị ghép vào câu SQL.
String sql = "SELECT id, title FROM courses WHERE title = '"
        + request.title() + "'";
Statement stmt = connection.createStatement();
ResultSet rs = stmt.executeQuery(sql);
~~~

Vấn đề không nằm ở việc chỉ có ký tự nháy đơn, mà là **ngữ cảnh câu lệnh và dữ liệu không được phân tách**.

### 7.2. Parameterized queries

~~~java
String sql = """
        SELECT id, title
        FROM courses
        WHERE tenant_id = ? AND title = ?
        """;

try (PreparedStatement stmt = connection.prepareStatement(sql)) {
    stmt.setString(1, authenticatedTenantId);
    stmt.setString(2, request.title());

    try (ResultSet rows = stmt.executeQuery()) {
        while (rows.next()) {
            // Map only approved result fields.
        }
    }
}
~~~

Đây là ví dụ JDBC. Đối với JPA/Hibernate, cũng cần dùng bind parameters/criteria đúng, tránh tạo dynamic query fragment từ user input. Parameter binding **không thay object/tenant authorization**; authenticatedTenantId phải có nguồn đáng tin và quyền tương ứng.

### 7.3. Khi không thể parameterize identifier

Tên column/table, hướng sắp xếp hoặc SQL fragment không luôn có thể bind như value. Thay vì nối raw input, dùng **allowlist mapping**:

~~~java
enum CourseSort {
    TITLE, CREATED_AT
}

String orderBy = switch (sort) {
    case TITLE -> "title";
    case CREATED_AT -> "created_at";
};

String sql = "SELECT id, title FROM courses WHERE tenant_id = ? "
        + "ORDER BY " + orderBy;
~~~

Cần giới hạn sort direction, pagination và max result size theo contract. Không đưa một SQL fragment từ query string vào ORDER BY chỉ vì phía frontend “chỉ có hai lựa chọn”.

### 7.4. Các loại injection khác

| Loại | Nguyên nhân | Cách phòng ngừa |
|---|---|---|
| **SQL injection** | Ghép chuỗi vào SQL | Parameter binding, allowlist identifiers, least-privileged DB role |
| **NoSQL injection** | Truyền JSON/operator trực tiếp từ user | Strict schema, typed builders, operator allowlist |
| **OS command injection** | Dùng shell để chạy chuỗi do user kiểm soát | Tránh shell; argument list, allowlist, sandbox |
| **LDAP injection** | Ghép filter từ raw input | Safe LDAP filter escaping/builder |
| **Template injection** | User content thành template source/expression | Không compile raw user templates, sandbox/allowlist |
| **Expression injection** | Untrusted input đi vào eval/expression parser | Không eval raw expressions; constrained grammar |
| **Header/log injection** | CRLF/control characters điều khiển parser | Structured APIs, canonical validation, safe logging |

### 7.5. Shell command trong Java

Tránh:

~~~java
// Anti-pattern: shell diễn giải raw user input.
new ProcessBuilder("sh", "-c",
        "convert " + uploadedPath + " output.pdf").start();
~~~

Nếu phải gọi external process, ưu tiên không đi qua shell, truyền **argument array** cố định, canonicalize/allowlist các path, timeout và hạn chế quyền/process sandbox. Ví dụ dưới chỉ minh họa cách tránh shell; chưa đủ xử lý path và resource limits:

~~~java
new ProcessBuilder(
        "/usr/bin/convert",
        approvedInputPath.toString(),
        approvedOutputPath.toString()
).start();
~~~

## 8. Authentication: bảo vệ danh tính và phiên

### 8.1. Những gì authentication cần bảo đảm

- Xác minh đúng danh tính user hoặc workload theo chính sách.
- Passwords/credentials không bị lưu và truyền theo cách không an toàn.
- Tài khoản/credential có lifecycle: enrollment, reset, revocation, disable.
- Session/token có issuance, expiry, audience, scope và replay considerations.
- Các hành động nhạy cảm có step-up/MFA khi phù hợp.
- Lỗi xác thực được báo an toàn và có rate limiting/abuse controls.

### 8.2. Password storage

Không lưu password dạng plaintext, không dùng hash nhanh tổng quát kiểu SHA-256 đơn lẻ làm password storage. Ưu tiên **password hashing function chuyên dụng** được hỗ trợ tốt với tham số cấu hình và migration phù hợp, ví dụ Argon2id, scrypt, bcrypt hoặc PBKDF2 tùy yêu cầu và khả năng nền tảng.

Trong Spring, PasswordEncoder/Authentication framework có thể giúp thực hiện điều này. Chọn thuật toán/tham số theo baseline, hạ tầng và lifecycle; tránh tự thiết kế một thuật toán kết hợp hash/salt không được thẩm định.

### 8.3. Token validation

Khi dùng access token, cần xác định:

- Issuer, signature/algorithm/key được phê duyệt.
- Audience tương ứng API đang được gọi.
- Expiry, not-before khi áp dụng và clock skew hợp lý.
- Token type, scopes/permissions và subject binding.
- Key rotation, revocation/session invalidation theo chính sách.
- Chống token confusion giữa ID token và access token.
- Bảo vệ token ở browser/mobile, logs, URLs và storage.

**Decode JWT payload không đồng nghĩa validate chữ ký và claims.** Không dùng dữ liệu từ token chưa xác thực làm nguồn phân quyền.

### 8.4. User identity và service identity là hai miền khác nhau

Một token của report-worker xác thực workload, không tự cho phép đọc mọi tenant. Một user token có quyền xem bài của chính mình không cấp cho worker quyền xem mọi bài. Khi chuyển giao user context qua queue, phải thiết kế **delegation scope và kiểm tra lại authority** rõ.

## 9. Authorization: tránh BOLA/IDOR và vượt tenant

### 9.1. Broken Object Level Authorization

BOLA/IDOR xảy ra khi actor được xác thực nhưng endpoint không xác minh actor có quyền với **đối tượng cụ thể**. Ví dụ user A thay learnerId để đọc dữ liệu user B.

Một anti-pattern:

~~~java
// Anti-pattern: user đã đăng nhập nhưng thiếu object authorization.
@GetMapping("/learners/{id}")
public LearnerEntity getLearner(@PathVariable long id) {
    return learnerRepository.findById(id).orElseThrow();
}
~~~

### 9.2. Kiểm tra quyền từ nguồn server-side

~~~java
@GetMapping("/learners/{id}")
public LearnerView getLearner(
        @PathVariable long id,
        @AuthenticationPrincipal AppPrincipal principal) {

    // Tốt hơn có thể query theo principal/tenant ngay từ repository.
    LearnerEntity learner = learnerRepository.findById(id)
            .orElseThrow(NotFoundException::new);

    if (!learnerPolicy.canRead(principal, learner)) {
        throw new AccessDeniedException("Not allowed");
    }

    return learnerViewMapper.toPublicView(learner);
}
~~~

Đoạn code là phác thảo. Tùy kiến trúc, truy vấn ngay theo **tenant và quyền** có thể giảm nguy cơ data access trước enforcement, nhưng không thay kiểm tra những đường side effects khác.

### 9.3. RBAC, ABAC và ReBAC

| Mô hình | Quyết định dựa trên | Ví dụ |
|---|---|---|
| **RBAC** | Vai trò | TEACHER có thể dùng chức năng chấm điểm |
| **ABAC** | Thuộc tính user/resource/context | Teacher thuộc tenant, trạng thái khóa học, điều kiện thời gian |
| **ReBAC** | Quan hệ giữa chủ thể và tài nguyên | Giáo viên được phân công lớp X |
| **Policy kết hợp** | Role + quan hệ + tenant + trạng thái | Teacher được chấm điểm lớp X khi đang được phân công |

Chỉ có role TEACHER không đủ để biết lớp nào thuộc quyền. Policy nên ràng buộc **principal, tenant, resource, action, purpose và state** khi cần.

### 9.4. Mọi entry point phải có enforcement

- Endpoint GET, POST, PATCH, DELETE.
- Bulk API, export và report.
- Background worker và scheduled job.
- GraphQL resolver hoặc gRPC method.
- Cache, search và object download URL.
- Admin tool, support impersonation và break-glass.
- Webhook hoặc callbacks dùng dữ liệu.

**Kiểm tra 403 trên API** chưa chứng minh không có file/report/job đã tạo trước khi deny. Cần test **side effects**.

### 9.5. Mass assignment và field-level authorization

Không tự binding mọi field từ JSON sang entity ORM rồi save. Ví dụ user cập nhật profile không được phép tự thay adminRole, tenantId hoặc accountStatus.

~~~java
public record UpdateLearnerProfile(
        @Size(max = 100) String displayName,
        @Size(max = 300) String bio
) {}

public void updateProfile(AppPrincipal principal,
                          long learnerId,
                          UpdateLearnerProfile request) {
    LearnerEntity entity = authorizedRepository
            .findEditableByPrincipal(principal, learnerId)
            .orElseThrow(NotFoundException::new);

    entity.setDisplayName(request.displayName());
    entity.setBio(request.bio());
    // Không copy trực tiếp toàn bộ user request vào entity.
}
~~~

Dùng DTO/command objects với **allowlist writable fields**; kiểm tra quyền riêng cho từng thuộc tính nhạy cảm và transition khi cần.

## 10. Cross-Site Scripting (XSS) và output encoding

### 10.1. XSS là lỗi về ngữ cảnh hiển thị

XSS xảy ra khi nội dung không đáng tin được đưa vào HTML, JavaScript hoặc DOM theo cách browser diễn giải như mã chủ động, dẫn tới chạy script hoặc thay hành vi dưới nguồn gốc trang.

Ví dụ hệ thống hiển thị bài nộp hoặc bình luận trong HTML; input học viên có thể chứa markup hoặc payload bất thường. Chỉ “lọc dấu ngoặc” là không đủ.

### 10.2. Controls phù hợp theo sink

- Với template có **auto-escaping** phù hợp, đưa dữ liệu vào HTML text/attribute đúng cách.
- Tránh nối raw user input vào JavaScript string, HTML attribute, CSS hoặc URL mà không dùng encoder phù hợp ngữ cảnh.
- Tránh **innerHTML** khi chỉ cần textContent trong DOM.
- Nếu sản phẩm thật sự cần rich HTML, dùng **HTML sanitizer** uy tín, policy allowlist chặt và test bypass.
- Dùng Content Security Policy (CSP) làm defense in depth, không coi CSP thay output encoding.
- Cookie flags và phân tách quyền giúp hạn chế một số hậu quả, nhưng không loại bỏ XSS.

### 10.3. Text và HTML là hai loại đầu ra khác nhau

Ví dụ trong browser JavaScript:

~~~javascript
// Nếu cần hiển thị text, không đưa input vào HTML interpreter.
titleNode.textContent = untrustedCourseTitle;

// Anti-pattern khi input không được kiểm soát phù hợp:
// titleNode.innerHTML = untrustedCourseTitle;
~~~

Với ứng dụng Java server-rendered, dùng template engine và đúng tính năng escaping; **không đánh dấu chuỗi user là safe HTML** chỉ để giữ markup.

### 10.4. Kiểm thử XSS

Test nên bao phủ:
- HTML text, attributes, URLs, inline JavaScript và CSS contexts được dùng.
- Stored content ở database và nội dung trả từ API.
- Admin dashboard và notification/email templates.
- Rich text sanitizer trước/sau transformations.
- Export PDF/HTML renderers nếu nội dung được diễn giải.
- Unicode/encoding và các biến thể payload đã biết.
- CSP report/violation events và giới hạn của monitoring.

Một scanner không thấy reflected XSS chưa chứng minh stored XSS trong dashboard quản trị cũng không tồn tại.

## 11. CSRF và bảo vệ hành động thay đổi trạng thái

### 11.1. CSRF khác XSS

**Cross-Site Request Forgery (CSRF)** xảy ra khi trình duyệt tự gửi thông tin xác thực gắn với phiên (thường là cookie) tới một site trong một request do trang bên ngoài kích hoạt, khiến ứng dụng thực hiện hành động ngoài ý muốn của người dùng.

Ví dụ người học đang đăng nhập bằng session cookie. Nếu endpoint đổi email chỉ cần cookie và không có CSRF protection, attacker có thể tìm cách khiến trình duyệt gửi request thay đổi email theo những điều kiện nhất định.

### 11.2. Khi nào cần CSRF protection?

Cần đánh giá **cơ chế authentication được tự động gửi** và loại request có side effects:

- Session cookie và những credential browser tự gắn có thể tạo CSRF risk.
- Với API yêu cầu bearer token chỉ được JavaScript tự thêm vào Authorization header và không tự động gửi cross-origin, CSRF threat model có thể khác; vẫn phải xem token storage, CORS, XSS, cookie fallback và các đường hỗn hợp.
- SameSite cookie có thể hỗ trợ giảm một số CSRF paths, nhưng không tự chứng minh toàn bộ các trường hợp đã được bảo vệ.
- API dùng POST chưa chắc đã an toàn nếu không có CSRF/token/origin protections phù hợp.
- GET/HEAD và những phương thức được coi safe **không nên có side effects làm thay đổi nghiệp vụ**.

### 11.3. Controls

- CSRF tokens do framework quản lý và xác minh khi áp dụng.
- Cookies có Secure, HttpOnly, SameSite theo use case; xem compatibility.
- Origin/Referer checks khi phù hợp, không coi một kiểm tra đơn lẻ là giải pháp vạn năng.
- CORS được cấu hình tối thiểu, không coi CORS là cơ chế thay thế authorization hoặc CSRF protection.
- Re-authentication/step-up cho những thay đổi rất nhạy cảm khi cần.
- State-changing endpoints có HTTP semantics đúng và không dùng GET gây mutation.
- Kiểm thử session state thực, same-site/cross-site requests và fail mode.

### 11.4. Test minh họa

| Test | Expected |
|---|---|
| Session cookie hợp lệ nhưng thiếu CSRF token trên endpoint cần bảo vệ | Từ chối |
| Token sai/bị hoán đổi với session khác | Từ chối |
| Request hợp lệ cùng session và token | Chấp nhận theo authorization |
| Người không có quyền nhưng có CSRF token | Vẫn từ chối vì authorization |
| Cross-origin request qua đường API legacy | Không vượt security policy |
| GET dùng để kích hoạt mutation | Không tồn tại hoặc bị hạn chế theo requirement |

**CSRF token không thay object-level authorization.** Người dùng tự gửi request hợp lệ cũng phải được kiểm tra quyền.

## 12. SSRF: server-side requests không được biến thành proxy tùy ý

### 12.1. Cơ chế

**Server-Side Request Forgery (SSRF)** xảy ra khi attacker khiến server gửi request đến địa chỉ hoặc tài nguyên không được phép thông qua một chức năng có thể chọn URL/host. Ví dụ “import bài giảng từ URL” hoặc “preview ảnh theo link”.

Nếu backend nhận URL tự do rồi fetch mà không kiểm soát, nó có thể truy cập:
- Internal admin services hoặc cổng chỉ mở trong VPC.
- Cloud metadata endpoints.
- Loopback, link-local, private IP và IPv6 addresses.
- Internal DNS service names.
- Services có quyền cao hơn browser.
- Địa chỉ qua redirect hoặc DNS rebinding.

### 12.2. Các lớp phòng vệ

1. **Business allowlist:** chức năng có thật cần fetch những domains/services nào?
2. **Typed URL parsing:** từ chối scheme ngoài HTTP/HTTPS nếu use case chỉ hỗ trợ hai scheme đó.
3. **Host validation:** kiểm tra hostname và allowlist trên đúng cấu trúc URL đã parse.
4. **DNS/IP checking:** kiểm tra địa chỉ đã resolve và phân loại; ngăn destination ngoài policy, kể cả IPv4/IPv6, loopback/link-local/private ranges khi không được phép.
5. **Redirect policy:** không theo redirect tùy ý; nếu theo, cần kiểm tra lại từng target.
6. **Network egress controls:** service chỉ kết nối được tới network/destination được phép.
7. **Timeouts/limits:** giới hạn response size, kết nối, redirects và thời gian.
8. **Credential isolation:** HTTP client không tự gửi secret/token/cookie ngoài scope.
9. **Logging:** ghi target đã chuẩn hóa và decision, tránh log credential trong URL.
10. **Tests:** hostname disguised, alternate encodings, IPv6, DNS changes, redirect, large responses.

Không có một regex đơn giản kiểm tra URL nào giải quyết tất cả biến thể SSRF. **DNS lookup ban đầu không bảo đảm kết nối cuối dùng đúng IP** nếu client tự resolve lại; kiểm soát network-level egress hoặc API hỗ trợ pin/validate địa chỉ kết nối là lớp bổ sung quan trọng.

### 12.3. Lựa chọn thiết kế an toàn hơn

Nếu chức năng chỉ import bài học từ ba đối tác, cho user chọn **partner ID** từ danh mục đã duyệt thay vì nhập URL bất kỳ. Backend dùng endpoint config của đối tác, kiểm soát credentials và payload. Cách này giảm đáng kể attack surface.

### 12.4. Assurance

Một unit test “localhost bị chặn” chưa đủ. Test với:
- Private/loopback/link-local và IPv6.
- DNS trả public trước rồi internal sau trong mô hình thử.
- Redirect từ domain được phép sang domain bị cấm.
- URL chứa userinfo, fragment, port bất thường.
- Service/proxy chạy trong network có metadata API.
- Egress policy và monitoring của container/VM thực.

## 13. Path traversal, file access và canonicalization

### 13.1. Nguyên nhân

**Path traversal** xảy ra khi tên đường dẫn do người dùng kiểm soát có thể khiến ứng dụng đọc/ghi file ngoài vùng được cấp quyền. Ví dụ:

~~~java
// Anti-pattern: lấy trực tiếp file path từ request.
Path path = Paths.get("/srv/learning/uploads", request.fileName());
return Files.readAllBytes(path);
~~~

Nếu filename chứa parent traversal, path tuyệt đối hoặc các biểu diễn khác, code có thể truy cập ngoài thư mục dự kiến. Việc chỉ loại chuỗi ".." có thể bị bypass qua encoding, separators, symlinks hoặc platform differences.

### 13.2. Giảm rủi ro từ thiết kế

- Không để người dùng chỉ định filesystem path nếu không cần; dùng **opaque file IDs** và server-side mapping.
- Tạo tên lưu ngẫu nhiên, tách metadata filename do user cung cấp.
- Dùng base directory cố định, kiểm soát permissions.
- Validate loại và metadata file theo mục đích.
- Khi phải kiểm tra path, dùng Path APIs, canonicalization/real-path checks phù hợp và xử lý symlink.
- Cân nhắc **TOCTOU (time-of-check/time-of-use)**: đường dẫn có thể thay giữa lúc kiểm tra và mở; cần file APIs/permission model tránh race.
- Không chạy processing file bằng quyền hệ thống cao.
- Khi trả file download, validate object authorization trước khi đọc.
- Kiểm soát output destination để tránh ghi đè file/secret.

### 13.3. Dùng ID thay filename làm nguồn quyền

~~~java
public DownloadResource download(
        AppPrincipal principal,
        UUID attachmentId) {

    AttachmentMetadata meta = attachmentRepository
            .findById(attachmentId)
            .orElseThrow(NotFoundException::new);

    if (!attachmentPolicy.canDownload(principal, meta)) {
        throw new AccessDeniedException("Not permitted");
    }

    // Storage key được hệ thống tạo và lưu, không lấy từ query.
    return objectStorage.readPrivateObject(meta.storageKey());
}
~~~

Đây là mẫu khái niệm, chưa bao gồm stream limits, content disposition, conditional requests, signed URLs hoặc permission changes. Kiểm tra policy ở đúng resource vẫn bắt buộc.

## 14. File uploads: kiểm tra cả content và lifecycle

### 14.1. Rủi ro

Một người học tải lên bài nộp dạng PDF hoặc hình ảnh. Những vấn đề có thể xảy ra:
- Upload file executable hoặc nội dung chủ động bị công khai với content type sai.
- File giả đuôi .pdf nhưng payload không phải PDF.
- File rất lớn hoặc file nén có tỷ lệ giải nén cực cao gây DoS.
- Parser/converter độc hại hoặc lỗi thư viện xử lý document.
- File trùng tên ghi đè file người khác.
- Malware trong document.
- Path traversal hoặc public storage exposure.
- File upload có PII bị giữ quá hạn hoặc hiển thị sai quyền.
- Metadata như filename/header gây log injection hoặc XSS ở UI.

### 14.2. Pipeline minh họa

~~~mermaid
flowchart LR
    U["User upload"] --> L["Authz + size/type limits"]
    L --> Q["Private quarantine storage"]
    Q --> S["Content inspection / parser sandbox"]
    S --> M{"Policy decision"}
    M -->|"Allowed"| P["Promote to private storage"]
    M -->|"Rejected"| R["Delete/quarantine + audit"]
    P --> D["Authorized download endpoint"]
~~~

Mỗi bước phải tương ứng với **data classification, scale và threat model**. Antivirus không phải biện pháp đủ cho mọi parser exploit; sandbox/patches, least privilege và content rewriting khi thích hợp có thể cần.

### 14.3. Controls nên kết hợp

| Control | Mục tiêu | Giới hạn |
|---|---|---|
| Allowlist loại file | Chỉ xử lý formats được phép | Extension/MIME có thể giả mạo |
| Kiểm tra file signature và parser | Xác định format theo content | File phức tạp có thể polyglot/malformed |
| Giới hạn kích thước và quota | Chống DoS và storage abuse | Cần kiểm soát decompressed size |
| Private quarantine | Không cho dùng ngay trước kiểm tra | Scanner có thể gặp false negatives |
| Random object key | Tránh overwrite và path injection | Không thay authorization |
| Access control trên download | Ngăn file rò cho tenant khác | Cần test URL/signed access |
| Safe content disposition | Giảm active content in browser | Phụ thuộc response headers và renderer |
| Malware scanning/sandbox | Phát hiện một số file độc hại | Không bảo đảm bắt mọi exploit |
| Lifecycle/retention | Giảm dữ liệu tồn đọng | Cần xử lý backup/vendor copies |

### 14.4. Test cần có

- File hợp lệ ở kích thước min/max.
- Extension và MIME không khớp content.
- File chứa metadata lạ hoặc tên có Unicode/control characters.
- Upload nhiều file đồng thời, tên trùng, retry hoặc cancel.
- File nén vượt quota sau giải nén.
- Unauthorized actor upload vào bài của người khác.
- Unauthorized actor tải object ngoài quyền hoặc dùng link hết hạn.
- Parser timeout/crash không làm worker tiếp tục xử lý file khác sai trạng thái.
- Quarantine fail-safe khi scan service không sẵn sàng theo policy.
- Storage permissions và retention evidence.

## 15. Deserialization, parsing và object binding

### 15.1. Dữ liệu serialized không tự đáng tin

Khi một application nhận JSON, XML, protobuf, Java serialized object hoặc YAML từ nguồn ngoài, parser/deserializer có thể tạo:
- Object graph không mong đợi.
- Các trường/quyền mà client không nên cập nhật.
- Tài nguyên tiêu thụ quá mức do deep nesting hay alias expansion.
- Gọi những cơ chế polymorphic typing sai policy.
- XML external entity hoặc resource loading khi parser không cấu hình an toàn.
- Behavior nguy hiểm ở định dạng serialization có khả năng thực thi object lifecycle.

### 15.2. Java native serialization

Không deserialize byte stream từ nguồn không đáng tin bằng ObjectInputStream một cách tùy tiện. Nếu hệ thống legacy bắt buộc cần Java native serialization, phải giới hạn type bằng cơ chế filtering phù hợp, dùng trusted sources, có migration plan và test. Với API mới, thường nên dùng định dạng dữ liệu có schema/DTO rõ và safe parser configuration.

Ví dụ anti-pattern:

~~~java
// Anti-pattern khi bytes do nguồn không đáng tin kiểm soát.
ObjectInputStream input =
        new ObjectInputStream(untrustedRequest.getInputStream());
Object obj = input.readObject();
~~~

Việc Java có compiler và static type **không làm dữ liệu serialized tự an toàn**.

### 15.3. JSON binding và mass assignment

Dùng DTO chỉ có field được phép, tắt/giới hạn polymorphic binding không cần thiết, kiểm soát unknown properties và parse depth/size. Không bind request trực tiếp vào entity chứa tenantId, role, passwordHash, internalFlags hoặc audit metadata.

### 15.4. XML, YAML và file parsers

Nếu thật sự cần XML, cấu hình parser ngăn external resource/entity access không được phép và giới hạn tài nguyên. YAML loader nên tránh dựng tùy ý object types từ untrusted input, giới hạn alias nesting và size. File parsers phải được cập nhật và chạy trong quyền tối thiểu khi risk yêu cầu.

### 15.5. Tests

- Unknown/disallowed properties và polymorphic type hints.
- Malformed deeply nested JSON/XML/YAML.
- Bản ghi với duplicate keys, oversized arrays, invalid UTF-8.
- Serialization type ngoài allowlist.
- External entity/resource reference bị từ chối theo policy.
- Parser error không ghi raw input và không làm application crash lan rộng.
- Retry/poison messages được quarantine có audit.

## 16. Cryptography trong secure coding

### 16.1. Bảo vệ bằng cơ chế được phê duyệt

Đối với encryption, digital signatures, password hashing, token signing, TLS và key derivation, ưu tiên **mature cryptographic libraries, approved algorithms, secure configurations và key management**. Không tự thiết kế thuật toán hoặc dùng “mã hóa” bằng Base64/đảo chuỗi.

### 16.2. Nhầm lẫn thường gặp

| Khái niệm | Dùng để | Không phải |
|---|---|---|
| **Encryption** | Bảo mật nội dung, đôi khi kết hợp integrity/authentication tùy mode | Không tự xác minh user được quyền xem dữ liệu |
| **Hash** | Tạo digest, kiểm tra integrity trong threat model phù hợp | Không tự mã hóa bí mật hoặc là password hashing phù hợp |
| **MAC/HMAC** | Kiểm tra authenticity/integrity với shared secret | Không bảo mật nội dung |
| **Digital signature** | Xác minh chữ ký bằng public key theo trust | Không bảo đảm signer được cấp quyền nghiệp vụ |
| **KDF/password hashing** | Chuyển secret/password theo mục đích riêng | Không thể thay nhau tùy ý |
| **Base64** | Biểu diễn dữ liệu dạng text | Không phải encryption |
| **TLS** | Bảo vệ kênh theo cấu hình và xác thực peer | Không thay authorization, purpose limitation |

### 16.3. Authenticated encryption

Nếu cần mã hóa dữ liệu application-level, chọn cấu hình **authenticated encryption (AEAD)** được hỗ trợ tốt như AES-GCM theo policy. Những điều quan trọng:

- Sinh và bảo vệ key ở nguồn/cơ chế đáng tin.
- **Nonce/IV uniqueness** theo yêu cầu thuật toán/key; không tự tái sử dụng tùy tiện.
- Không hardcode key/nonce trong source.
- Xác minh authentication tag trước khi dùng plaintext.
- Quản lý key version, rotation, backup/recovery và data re-encryption strategy.
- Xác định associated data khi cần ràng buộc metadata.
- Không tự cắt/ghép ciphertext để “sửa một phần” nếu không có protocol được thiết kế.
- Chọn library APIs ngăn misuse khi khả thi.

Không nên chèn một mẫu vài dòng AES-GCM rồi coi đó là cryptographic design hoàn chỉnh; key lifecycle và data format là một phần của security requirement.

### 16.4. Randomness

Tokens, session IDs, nonces và reset links đòi hỏi randomness thích hợp. Trong Java, ưu tiên SecureRandom cho material cần tính không đoán được. Không dùng Math.random, timestamp hoặc UUID được thiết kế không phù hợp ngữ cảnh để tạo secret với yêu cầu entropy cao.

### 16.5. TLS và certificate verification

Không vô hiệu chain/hostname verification để “sửa lỗi gọi API”. Khi certificate lỗi, kiểm tra hostname, SAN, trust chain, issuer, validity, trust store, TLS config và clock. Trust-all behavior là anti-pattern nghiêm trọng trong production.

## 17. Secrets và key management trong code

### 17.1. Những nơi secret có thể rò rỉ

- Source code, test fixtures và commit history.
- CI variables được in bởi job.
- Container images và build layers.
- Process arguments, shell history và env dumps.
- Stack traces và debug logs.
- HTTP URLs, headers, request/response bodies.
- Error tracking, metrics labels hoặc distributed traces.
- Config snapshots, backups và support tickets.

### 17.2. Controls

- Dùng secret manager/KMS/HSM khi phù hợp.
- Tách secrets giữa environments, tenants và workloads.
- IAM least privilege cho service identity dùng secret.
- Không hardcode password/token/API keys.
- Có rotation, expiry và revocation/quy trình thay khi lộ.
- Hạn chế in environment variables và process metadata.
- Mask/redact trong logs/CI output; vẫn kiểm tra chính secret scanner.
- Quản trị quyền đọc secret store và audit.
- Không dùng secret production trong unit tests.
- Có owner, inventory/reference và incident playbook.

### 17.3. Chia sẻ secret qua code review không phải cách kiểm tra

Assessor không nên yêu cầu paste private key, database password hoặc keystore secret vào PR/ticket để chứng minh có secret. Có thể kiểm tra **secret reference, permission, rotation evidence, runtime connectivity với quyền phù hợp và log access** mà không thu bản sao bí mật.

### 17.4. Secret scanning

Secret scanning có thể tìm pattern, entropy hoặc credential formats trong repository/artifacts. Nhưng:
- Một kết quả “0 findings” chưa chứng minh mọi secret không tồn tại.
- Có false positives như test tokens.
- Một secret đã bị commit rồi xóa khỏi HEAD vẫn có thể tồn tại trong history.
- Khi credential thật bị phát hiện, **rotate/revoke**, không chỉ xóa dòng code.
- Scan có thể cần bao phủ CI logs/images/artifacts theo risk, không chỉ source.

## 18. Logging, auditing và error handling

### 18.1. Log cần hữu ích nhưng không tiết lộ

Một security audit event thường cần:
- Who: actor/service identity đã được xác thực hoặc nguồn không xác thực.
- What: action/resource identifier.
- When: timestamp và correlation/request ID.
- Where: service/env/tenant theo policy.
- Outcome: allow/deny/error.
- Why: rule/policy ID hoặc reason code phù hợp.
- Integrity and retention: bảo vệ log, phân quyền và lưu đúng chính sách.

Không mặc định log toàn bộ request/response. Tránh ghi access tokens, passwords, session cookies, private keys, raw bài làm hoặc dữ liệu cá nhân quá mức.

### 18.2. Log injection

Input có newline hoặc control characters có thể làm log bị chia dòng, giả event hoặc làm hỏng parser. Dùng **structured logging**, encode/normalize dữ liệu không đáng tin, đặt field boundaries và giới hạn size. Khi có log forwarding, kiểm tra biến đổi ở downstream.

### 18.3. Error messages

Một lỗi truy vấn database không nên trả raw SQL, connection string, stack trace hoặc internal object IDs cho client. Phản hồi có thể dùng generic error code/trace ID; server logs giữ thông tin chẩn đoán phù hợp nhưng không đưa secret.

Ví dụ cấu trúc response:

~~~json
{
  "error": "REQUEST_NOT_ALLOWED",
  "message": "Không thể thực hiện thao tác này.",
  "requestId": "example-correlation-id"
}
~~~

Không nên cố làm mọi lỗi thành HTTP 200 “success=false”, vì sẽ làm khó client, monitoring và xác định security decisions. Chọn status/error contract nhất quán, không làm rò chi tiết nhạy cảm.

### 18.4. Không để lỗi hỏng log thành fail-open authorization

Nếu audit logging không sẵn sàng, hệ thống cần định nghĩa hành vi dựa trên risk. Với một số hành động đặc biệt nhạy cảm, có thể cần từ chối hoặc queue durable audit event trước khi xử lý; với những hành động khác, có thể tiếp tục trong degraded mode có giới hạn và cảnh báo. **Không tự cho phép truy cập khi PDP hoặc identity verification lỗi**.

### 18.5. Test

- Token/secret được đưa vào input tổng hợp không xuất hiện trong logs/traces.
- CRLF và control characters không tạo event giả.
- Denied authz có actor/resource/action/correlation phù hợp.
- Exception từ DB/vendor không trả stack traces ra client.
- Log collector ngừng hoạt động được phát hiện, không báo 0 violations giả.
- Audit logs có access controls, retention và tamper detection phù hợp.

## 19. Resource exhaustion, concurrency và race conditions

### 19.1. Availability là mục tiêu secure coding

Một request hợp lệ cú pháp vẫn có thể làm cạn CPU, memory, threads, DB connections hoặc storage nếu xử lý không giới hạn. Ví dụ:
- Page size cực lớn hoặc query không có index.
- Một endpoint nén/giải nén file không giới hạn.
- JSON nested sâu hoặc regex gây backtracking lâu.
- Tạo hàng nghìn job export và retry vô hạn.
- Chuyển toàn bộ blob vào memory thay vì streaming.
- Thiếu timeouts khi gọi vendor.
- Tính toán đắt đỏ lặp đi lặp lại trên dữ liệu attacker kiểm soát.

### 19.2. Controls

- Request body, array length, nesting depth và file size limits.
- Rate limits/quotas theo actor, tenant và service.
- Pagination có max page size; query timeouts, DB connection pools.
- Streaming, bounded queues, backpressure.
- External call timeouts, retry budget, circuit breaker khi phù hợp.
- Algorithm complexity review; tránh regex kém an toàn.
- Memory/CPU limits, worker concurrency controls, task cancellation.
- Bulkhead isolation để một tenant không làm cạn tài nguyên của tenant khác.
- Monitoring latency, queue depth, saturation, errors.

### 19.3. Race condition và TOCTOU

Một luồng “check quyền rồi ghi dữ liệu” có thể mất an toàn nếu trạng thái thay đổi giữa check và use. Ví dụ hai request đồng thời dùng cùng voucher, hoặc một actor bị thu hồi quyền trong lúc job export đang chạy.

Cần đánh giá:
- Transaction boundaries và isolation.
- Uniqueness constraints/invariants ở database.
- Optimistic/pessimistic locking khi phù hợp.
- Compare-and-set hoặc idempotency key.
- Authorization tại thời điểm phù hợp; không giữ authorization snapshot vô thời hạn.
- Retry semantics và side effects.
- File path check/use có symlink thay đổi.

### 19.4. Test concurrency

- Hai request cùng cập nhật resource/version.
- Nhiều job với cùng idempotency key.
- Revoke quyền giữa request và worker execution.
- External vendor timeout, response chậm hoặc retry storm.
- High-volume input làm queue đầy mà không mất integrity/tenant isolation.
- Transaction rollback không để lại file/message side effects trái policy.

## 20. Security của asynchronous workflows và APIs phụ trợ

### 20.1. Queue/message không đương nhiên đáng tin

Một worker nhận message có thể gặp:
- Producer giả mạo hoặc credential bị lộ.
- Payload sửa tenantId, actorId, report scope.
- Message duplicate/replay.
- Message quá cũ sau khi quyền actor đã thay đổi.
- Poison message làm worker crash/retry liên tục.
- Dead-letter queue lưu PII quá hạn.

### 20.2. Không truyền raw authority từ browser sang worker

Nếu client yêu cầu export lớp 45, server cần quyết định **actor có quyền lớp 45** và ghi một job record được kiểm soát. Worker không nên tin role=ADMIN hoặc tenantId từ raw message nếu không có nguồn authoritative và ràng buộc job scope.

Có hai mô hình cần cân nhắc theo yêu cầu:
- **Revalidate at execution:** worker kiểm tra quyền actor/resource khi chạy.
- **Scoped delegated authorization:** server cấp quyền cụ thể cho job có TTL, action/resource binding và audit; worker xác minh artifact trước xử lý.

Mỗi mô hình có đánh đổi về consistency và latency. Chính sách phải nêu hành vi khi quyền bị thu hồi, job retry, link download đã phát hành và expiry.

### 20.3. Idempotency và xử lý lỗi

Với thao tác có side effects, idempotency keys và durable job state giúp tránh tạo nhiều báo cáo hoặc thanh toán lặp. Nhưng idempotency key phải ràng buộc **actor, tenant, operation và payload identity** phù hợp; không thể để một actor đoán key của actor khác rồi nhận kết quả của họ.

### 20.4. Webhooks

Khi nhận callback từ vendor:
- Xác minh nguồn/credential/signature theo contract.
- Kiểm tra timestamp/nonce hoặc replay controls khi có.
- Giới hạn body size, schema, event type và tenant mapping.
- Không tin URL callback làm command tùy ý.
- Không cho event “course.completed” tự nâng quyền user.
- Ghi audit, xử lý duplicates và out-of-order events.
- Thử forged signature, wrong tenant, old event, retry và unknown event type.

Một webhook được ký hợp lệ chưa có nghĩa mọi field trong event được phép quyết định business authorization.

## 21. Dependencies, third-party libraries và supply-chain security

### 21.1. Secure coding không chỉ là code tự viết

Ứng dụng Java phụ thuộc framework, logging library, parser, database driver, HTTP client, cryptography provider, build plugins và container base image. Những thành phần này có thể gây rủi ro qua:
- Vulnerability đã biết và chưa được vá.
- Dependency transitive có phiên bản bị ảnh hưởng.
- Artifact package bị thay thế hoặc xuất bản bởi chủ thể không mong muốn.
- Build script/plugin chạy mã ngoài dự kiến trong CI.
- Registry credential hoặc signing key bị lộ.
- Thư viện đã không được duy trì, không có hướng cập nhật.
- Thay đổi default behavior khiến validation, TLS hoặc serialization yếu đi.
- Mâu thuẫn giữa phiên bản được scan và bản thật chạy production.

### 21.2. Các controls ở supply-chain boundary

| Control | Mục tiêu | Bằng chứng |
|---|---|---|
| Approved dependency policy | Tránh tùy tiện đưa thư viện không phù hợp vào hệ thống | Manifest, review record |
| Lockfile/version control | Xây dựng có thể truy vết dependency resolution | Locked versions, build records |
| Software Composition Analysis (SCA) | Phát hiện dependency vulnerabilities/risks | Scan với version, advisory, scope |
| SBOM | Biết thành phần nào nằm trong artifact | SBOM gắn build digest |
| Artifact provenance | Truy vết nguồn, build và artifact | Source commit, builder identity, digest |
| Signing/verification | Kiểm tra artifact theo signer/policy | Signature, verification records |
| Protected build environment | Hạn chế code/secret manipulation | CI permissions, runner isolation, audit |
| Update/patch governance | Xử lý thư viện dễ tổn thương theo risk | Findings, owner, due date, retest |
| Runtime reconciliation | Bảo đảm scan artifact thật được deploy | Deployment digest, image inventory |

**SBOM không tự chứng minh ứng dụng an toàn**, và một dependency scan không tìm thấy CVE không chứng minh không có đường lạm dụng hoặc vulnerability chưa được công bố.

### 21.3. Đánh giá finding dependency

Một cảnh báo SCA cần xét:
- Component/version có thực trong deployed artifact không?
- Chức năng có bị gọi hoặc có đường exposure theo risk không?
- Impact nếu bị khai thác, data/privilege liên quan?
- Fix version và compatibility?
- Có mitigation tạm, scope limitation và monitoring không?
- Ai owner và khi nào retest?
- Có dependency transitive, shaded JAR hoặc runtime plugin bị bỏ sót không?

Không dùng một điểm số severity duy nhất thay risk assessment. Ngược lại, claim “code path không reachable” phải có **cơ sở kỹ thuật và evidence**, không chỉ lời khẳng định.

## 22. Secure configuration, IaC và deployment

### 22.1. Mã nguồn và runtime config cùng quyết định security

Một class Spring Security có cấu hình tốt vẫn có thể bị vô hiệu bởi route exclusions, profile debug, cloud IAM quá rộng hoặc proxy tin header không được bảo vệ.

Những cấu hình quan trọng:
- Authentication/authorization filters và method security.
- CORS, CSRF, security headers, cookie/session config.
- TLS client/server validation, trust store và certificate settings.
- Database credentials, grants và encryption.
- API gateway routes, ingress/egress và network policies.
- Debug logging, stack traces và actuator/admin endpoints.
- Secret references, workload identities và IAM.
- Storage bucket ACL/policy, signed URLs và retention.
- Container non-root permissions và sandbox settings.
- Queue producer/consumer scopes, retries và DLQ access.
- Feature flags có thể bỏ qua một control.

### 22.2. Cấu hình không phải evidence runtime

Một IaC file khai báo private bucket không chứng minh bucket thực tế chưa bị sửa ngoài pipeline. Một Kubernetes NetworkPolicy có thể không áp dụng như kỳ vọng khi CNI/namespace/selector không khớp. Cần:

1. Review cấu hình và policy design.
2. Test/scan IaC khi thích hợp.
3. Xác minh effective state trên môi trường đích.
4. Negative tests với identity không có quyền.
5. Phát hiện drift sau release.
6. Change records, rollback và control owner.

### 22.3. Environment parity và configuration drift

Staging và production có thể khác IdP, trust stores, egress network, data, feature flags, token audience, secrets, JVM version và dependency endpoints. Một test pass ở staging hỗ trợ design/implementation trong staging; production cần verification theo risk.

Không sao chép secrets production về test để “giống production”. Dùng synthetic fixtures và môi trường kiểm soát có configuration đại diện.

## 23. Frontend/mobile secure coding và API contracts

### 23.1. Frontend là một trust boundary

Browser/mobile client có thể bị người dùng sửa, debug, replay hoặc gọi API trực tiếp. Không đặt business authorization cuối cùng tại frontend.

Các vấn đề nên xem:
- DOM XSS và unsafe HTML rendering.
- CSRF trong cookie-based sessions.
- Token storage/handling, refresh/session lifecycle.
- Open redirects và client-side URL handling.
- Các dữ liệu nhạy cảm bị lộ trong source maps, local storage hoặc logs.
- Deep links, intent handlers và untrusted external callbacks trên mobile.
- Certificate/network validation qua SDK.
- Truy cập camera/file/notification theo quyền và mục đích.

### 23.2. UI visibility không phải quyền

Một nút “Chấm điểm” chỉ hiện cho TEACHER không có nghĩa endpoint chấm điểm đã bảo vệ. Actor có thể gọi API trực tiếp. Backend phải xác minh quan hệ actor–class–assignment, trạng thái bài, tenant và quyền trên field.

### 23.3. API response minimization

Không trả entity ORM nguyên vẹn nếu nó chứa passwordHash, internal flags, refresh tokens, ghi chú riêng tư hoặc thuộc tính không phục vụ UI. Dùng response DTO rõ và contract tests.

~~~java
public record LearnerSummaryResponse(
        long id,
        String displayName,
        int completedLessons
) {}
~~~

Một DTO gọn là control về **field exposure**, nhưng vẫn phải kiểm tra **đối tượng nào** được phép nhận response. Không dùng DTO để thay authorization.

### 23.4. Security headers và CORS

CSP, HSTS, X-Content-Type-Options, cookie attributes và các response headers có thể hỗ trợ giảm một số threats tùy ứng dụng. CORS xác định trình duyệt cho phép origin nào đọc responses trong một số mô hình; nó **không bảo vệ API khỏi non-browser clients** và không thay authentication/authorization.

Không đặt Access-Control-Allow-Origin là wildcard cùng các tình huống credentials không phù hợp chỉ để mọi frontend đều gọi được API. Cấu hình phải bám data flows và user session model.

## 24. Code review: xem luồng dữ liệu và quyền, không chỉ style

### 24.1. Review nên bắt đầu từ thay đổi risk

Reviewer cần biết:
- Feature và data flow mới là gì?
- Actor và tenant nào bị ảnh hưởng?
- Entry points, sensitive sinks và trust boundaries?
- Security assumptions trước đây còn đúng?
- Thêm dependency, network access, secret, parser hoặc quyền mới không?
- Có endpoint batch/webhook/queue hoặc background worker liên quan?
- Có thay đổi authentication, authorization, validation, logging và error handling?
- Tác động đến privacy, availability, monitoring và rollback?

### 24.2. Pull request security checklist

- [ ] Input được parse/validate ở server-side boundary.
- [ ] Parameterized queries và typed builders được sử dụng đúng.
- [ ] User/tenant/object/action authorization có enforcement trên mọi entry point.
- [ ] Không mass assign hoặc trả entity với field nhạy cảm.
- [ ] HTML/script/URL outputs có encoding/sanitization đúng ngữ cảnh.
- [ ] CSRF, CORS và session handling phù hợp threat model.
- [ ] SSRF/file/network operations có allowlist, egress và limits.
- [ ] Upload/deserialization có size/type/depth/permission checks.
- [ ] Secrets không nằm trong source, test artifacts hoặc logs.
- [ ] Crypto/TLS dùng APIs được phê duyệt; không trust-all.
- [ ] External calls/DB/queue có timeouts, quotas, retries/idempotency.
- [ ] Audit logging hữu ích, không lộ PII/credentials.
- [ ] Dependency/config/IaC thay đổi đã được xem theo risk.
- [ ] Positive/negative tests bao phủ abuse cases và side effects.
- [ ] Build/release evidence gắn với code đang review.

Checklist là **hỗ trợ review**, không thay hiểu biết về business logic và risk.

### 24.3. Reviewer independence và authorization

Với thay đổi tác động cao như permission logic, private key handling, payment/grade integrity hoặc identity provider, có thể cần reviewer có chuyên môn hoặc mức độc lập phù hợp theo policy. Tổ chức nên định nghĩa approval rules, không coi một dấu “Approved” từ tác giả PR là bằng chứng review độc lập.

### 24.4. Review comment tốt

Comment chưa hữu ích: “Đoạn này có vẻ không an toàn.”

Comment có thể kiểm chứng: “Endpoint GET /submissions/{id} tìm entity theo ID nhưng không kiểm tra relationship với authenticated principal. Đề nghị dùng scoped repository/policy và thêm negative test user A đọc submission user B; xác nhận response và log không lộ dữ liệu.”

Review tốt đưa ra **risk, vị trí/sink, expected behavior, remediation và test**.

## 25. Chiến lược security testing trong development

### 25.1. Các cấp test

| Cấp | Phù hợp cho | Giới hạn |
|---|---|---|
| **Unit test** | Validation, policy, parser, error handling | Có thể mock mất data flow/runtime thật |
| **Integration test** | Controller–service–database, queue, storage policy | Scope của test env chưa chắc production |
| **Contract/API test** | Schema, field limits, auth/HTTP behavior | Không tự bao phủ business workflows |
| **Negative security test** | Sai identity, tenant, permission, input | Cần kiểm tra side effects và data coverage |
| **Property-based test** | Invariants qua nhiều input/edge cases | Generator cần tốt, oracle rõ |
| **Fuzz testing** | Parser/protocol, malformed/unexpected input | Coverage/triage và harness quyết định chất lượng |
| **SAST** | Code patterns và data flow nguy hiểm | False positives, blind spots, business logic khó biết |
| **DAST** | Hành vi ứng dụng chạy, một số vulnerabilities | Auth context, state/data coverage có giới hạn |
| **SCA** | Vulnerability trong dependencies | Không thay review own code hoặc reachability evidence |
| **Secret scanning** | Credential patterns trong code/artifacts | Có thể bỏ sót secrets và có false positives |
| **IaC/config scan** | Policy misconfig trong IaC | Effective runtime state có thể drift |
| **Manual secure review** | Business logic, chained flows, privilege | Chất lượng phụ thuộc reviewer và scope |
| **Penetration test** | Attacker-centric validation cho scope/time | Không đảm bảo mọi route/vulnerability đã được kiểm tra |
| **Runtime monitoring** | Detect attempted abuse/control drift | Không thay prevention và tests |

### 25.2. Security test phải có oracle rõ

Một test “request bị từ chối” cần định nghĩa:
- Identity và permissions thực.
- Resource/tenant/action.
- Environment/build.
- Payload và expected status.
- Expected absence of sensitive fields.
- Database/queue/file/vendor side effects.
- Audit event, correlation ID và monitoring khi cần.
- Thời điểm policy/state được áp dụng.

Một HTTP 403 có thể đi kèm file export đã tạo từ trước do flow xử lý sai thứ tự; test chỉ xem status sẽ bỏ sót failure.

### 25.3. Negative tests phải thực tế

~~~java
@Test
void anotherTenantCannotExportGrades() {
    var teacherA = fixtures.teacherOfTenantA();
    var classB = fixtures.classOfTenantB();

    assertThrows(AccessDeniedException.class,
        () -> exportService.requestExport(teacherA, classB.id()));

    assertFalse(exportJobRepository.existsForClass(classB.id()));
    assertFalse(storageTestProbe.hasNewExportForClass(classB.id()));
}

@Test
void untrustedRoleHeaderDoesNotChangePrincipal() {
    var learner = fixtures.learnerPrincipal();

    assertThrows(AccessDeniedException.class,
        () -> gradeService.changeGrade(
            learner, fixtures.otherLearnerSubmission(), 90));
}
~~~

Tên service/fixture là minh họa. Test thực tế nên kiểm tra qua HTTP/runtime boundary nếu logic có thể bị bỏ qua trong controller filter hoặc serialization.

### 25.4. Test theo rủi ro và coverage

Không bắt mọi PR chạy mọi fuzz/penetration test. Có thể chia:
- PR: unit/integration authz, code scans, dependency/secret checks.
- Release: end-to-end flows, risk-based DAST, IaC/config verification.
- Periodic/event-driven: focused pen tests, fuzzing, resilience drills, vendor review.
- Sau finding: exploit/regression test đúng root cause và những đường tương tự.

Tần suất và độ sâu dựa vào asset criticality, tốc độ thay đổi, threats và nghĩa vụ; không có một tỷ lệ tự động phù hợp mọi service.

## 26. CI/CD quality gates và security assurance

### 26.1. Pipeline không chỉ là nhiều scanner

~~~mermaid
flowchart LR
    A["Threat / security requirement"] --> B["PR and secure code review"]
    B --> C["Build + unit/integration tests"]
    C --> D["SAST / SCA / secrets / config checks"]
    D --> E{"Gate decision"}
    E -->|"Pass / authorized exception"| F["Signed or traceable artifact"]
    E -->|"Fail"| R["Finding + remediation"]
    F --> G["Deploy to controlled environment"]
    G --> H["Runtime validation + monitoring"]
    H --> I["Assurance evidence/report"]
    R --> B
~~~

Một gate cần:
- Định nghĩa **criteria**, severity/risk, exceptions và thẩm quyền.
- Scope các nguồn/paths đang scan.
- Liên kết kết quả với commit/build/dependency manifest.
- Xử lý scanner failure: scanner không chạy **không được tính là 0 finding**.
- Triage false positives và những findings được chấp nhận có thời hạn.
- Cơ chế chặn khi critical failure theo policy, không có bypass không kiểm soát.
- Artifact provenance và deployment mapping.
- Retest sau fix, không chỉ đánh dấu ticket Closed.

### 26.2. Không nhầm pass gate với bảo đảm toàn hệ thống

Gate pass chỉ hỗ trợ kết luận rằng **các kiểm tra đã chạy với công cụ/cấu hình/tập luật và source scope được ghi nhận** không phát hiện failure theo criteria. Nó không chứng minh:
- Runtime đang chạy đúng artifact đó.
- Threat model đã bao phủ mọi abuse case.
- Dependencies không còn lỗ hổng chưa biết.
- Business authorization không có bypass.
- Production secrets/IAM/logging đúng config.
- Vendor processing đáp ứng mọi nghĩa vụ.

### 26.3. Ví dụ policy gate dạng YAML

Đây là cấu hình **minh họa quy tắc nội bộ**, không phải cú pháp sẵn dùng của một CI provider.

~~~yaml
security_gate:
  policy_version: "sec-dev-2026-example"
  protected_branches: ["main", "release/*"]
  required_checks:
    - id: secure-tests
      evidence: ["test-results", "commit-id"]
      failure_behavior: "block"
    - id: secret-scan
      evidence: ["scan-report", "repository-scope"]
      failure_behavior: "block"
    - id: dependency-scan
      evidence: ["scan-report", "resolved-dependencies"]
      failure_behavior: "block-on-policy-threshold"
    - id: static-analysis
      evidence: ["findings", "ruleset-version"]
      failure_behavior: "block-on-policy-threshold"
  exception:
    required_fields:
      - "finding-id"
      - "scope"
      - "impact-and-residual-risk"
      - "approved-compensating-controls"
      - "approver"
      - "expires-at"
      - "retest-plan"
    unauthorized_bypass: "deny"
  release:
    require_artifact_build_mapping: true
    require_runtime_verification_for_critical_controls: true
~~~

Không dùng placeholder để khẳng định hệ thống thật đang có gate này. Để kiểm chứng phải thu **pipeline config, results, exceptions và deployed artifact mapping**.

## 27. Traceability: từ yêu cầu đến code, test và evidence

### 27.1. Security requirement cần có ID và acceptance criteria

Một yêu cầu như “bảo vệ dữ liệu học viên” quá rộng. Chia nhỏ thành claims kiểm chứng được:

| ID | Requirement | Code/control | Expected test |
|---|---|---|---|
| SC-REQ-01 | API chỉ đọc submission đúng người được phép | Scoped query, object policy | Cross-user 403/404 và không rò body |
| SC-REQ-02 | Teacher chỉ đổi grade lớp được phân công | Relation-aware authorization | Wrong-class/tenant denied, no DB change |
| SC-REQ-03 | Course search không dùng SQL concatenation | Parameter binding | Injection payload không thay query semantics |
| SC-REQ-04 | Rich text không chạy script ngoài policy | Output encoding/sanitizer | Stored XSS test |
| SC-REQ-05 | User-supplied URL không gọi internal destinations | URL policy + egress | Redirect/DNS/IP SSRF tests |
| SC-REQ-06 | Upload không đọc/ghi ngoài scope | Opaque IDs, storage policy | Path/content/authorization tests |
| SC-REQ-07 | API/worker không log token | Structured logging, redaction | Synthetic token log/trace scan |
| SC-REQ-08 | Export job không vượt tenant và không replay side effects | Scoped job, idempotency | Forged/duplicate/stale tests |
| SC-REQ-09 | Error handling không để lộ secret/stack trace | Safe response mapping | Exception/failure tests |
| SC-REQ-10 | Release chỉ từ approved build/dependencies | CI gate, provenance/verification | Build-to-deploy mapping |

### 27.2. Assurance traceability

~~~mermaid
flowchart LR
    R["Threat/Risk"] --> Q["Requirement + acceptance criteria"]
    Q --> C["Control + code owner"]
    C --> T["Test + result"]
    T --> E["Evidence + provenance"]
    E --> A["Assessment + limitation"]
    A --> F["Finding / action"]
    F --> C
~~~

Một traceability matrix có giá trị khi nó gắn **phiên bản thực, owner và kết quả**, không chỉ điền một dấu tick trong bảng.

### 27.3. Bằng chứng có thể được tái sử dụng, nhưng phải kiểm tra phạm vi

Một negative test cho role TEACHER ở endpoint GET không mặc nhiên chứng minh endpoint EXPORT, GraphQL resolver hoặc worker có cùng authorization. Có thể tái sử dụng policy design và helper tests, nhưng **mỗi entry point và boundary phải được đánh giá theo đường thực thi**.

## 28. Claim–Argument–Evidence cho secure coding

### 28.1. Claim mẫu có phạm vi

> Trong các API production quản lý bài nộp và điểm số được liệt kê của bản phát hành được kiểm tra, server-side validation, object/tenant authorization, safe query construction và error handling được triển khai; các positive/negative tests đã xác nhận không phát sinh truy cập hoặc side effects ngoài quyền trong những luồng được kiểm thử.

Claim này **không** nói “toàn bộ nền tảng không còn vulnerability”. Nó có đối tượng, control và điều kiện kiểm tra cụ thể.

### 28.2. Argument

1. Threat model và data-flow inventory đã xác định các entry points và tài sản nhạy cảm trong scope.
2. Security requirements có acceptance criteria cho input, authentication, authorization và output.
3. Code review xác minh controls được đặt trên đúng runtime paths.
4. Tests bao phủ cả actor hợp lệ và actor không có quyền, dữ liệu sai, input bất thường, dependency errors.
5. Query/DB access, queue/storage và logs được kiểm tra side effects.
6. Build, config và deployment mapping chứng minh runtime dùng phiên bản đã kiểm thử.
7. Runtime checks và monitoring phát hiện drift hoặc abuse.
8. Findings/gaps được báo với owner, remediation và limitations.

### 28.3. Evidence cần thu

- Threat model, attack scenarios và data classification.
- Security requirements/control mappings.
- Source commit, PR diff, reviewers, approvals.
- Unit/integration/negative tests, tool version, configuration, fixtures.
- SAST/SCA/secret results với scan scope và triage.
- Build artifacts, SBOM, digest, signing/provenance khi áp dụng.
- CI gate decision và exception records.
- Deployment/config/version mapping.
- Runtime API/authorization/telemetry evidence.
- Incident/finding/remediation/retest records.
- Assessor conclusion với scope, period, exclusions, uncertainty.

### 28.4. Ba mức effectiveness

| Lớp | Câu hỏi | Bằng chứng | Không tự suy ra |
|---|---|---|---|
| **Design** | Control có giải quyết đúng threat và yêu cầu không? | Threat model, architecture decision, requirement | Chưa chắc code thực hiện đúng |
| **Implementation** | Code/config thật có control đúng trên entry points? | Review, tests, effective policy | Chưa chắc control hoạt động ổn định cả kỳ |
| **Operating** | Control và process phát hiện/khắc phục có duy trì trong release? | Release evidence, runtime tests, monitoring, findings | Không suy rộng ra hệ thống ngoài scope |

Một linter không thấy issue không đủ để kết luận **implementation effectiveness** của business authorization; cần test và review đúng semantics của hệ thống.

## 29. Evidence quality và test matrix cho secure coding

### 29.1. Tiêu chí chất lượng evidence

| Thuộc tính | Câu hỏi đánh giá | Ví dụ không đạt |
|---|---|---|
| **Relevance** | Artifact chứng minh security claim nào? | TLS scan dùng để chứng minh object authorization |
| **Scope** | Code paths, endpoints, tenants, environments, clients nào được test? | Chỉ test REST, bỏ worker và batch |
| **Completeness** | Có inventoried tất cả entry points và side effects? | Bỏ GraphQL, cache, storage và vendor |
| **Freshness** | Evidence đúng build, dependency, configuration và kỳ? | PR test cũ trước hotfix |
| **Provenance** | Ai/công cụ nào tạo, source commit, ruleset, fixture, time? | Screenshot không có build/test method |
| **Integrity** | Có đối chiếu được artifact và phát hiện thay đổi trái phép? | Scan report chỉnh tay không audit trail |
| **Reliability** | Test oracle, scanner, env và assertions đáng tin? | Scanner thất bại nhưng dashboard báo zero findings |
| **Representativeness** | Test cases/mẫu bao phủ nhóm có risk khác nhau? | Chỉ admin/tenant duy nhất, bỏ role khác |
| **Repeatability** | Reviewer khác có thể lặp cùng phép kiểm tra? | “Đã thử bằng tay” không ghi steps |
| **Independence** | Người đánh giá có mức độc lập phù hợp mục đích audit? | Tác giả tự phê duyệt finding của chính mình khi policy yêu cầu peer review |
| **Confidentiality** | Evidence được xử lý tránh lộ secret/PII? | Copy raw production user records vào ticket mở |

### 29.2. Evidence metadata tối thiểu

Một security test record nên có:
1. **Evidence ID, risk/requirement/control/claim IDs**.
2. **Module/service, route, entry point, data flows** được kiểm tra.
3. **Commit, build digest, dependency manifest, config, environment**.
4. **Principal/role/tenant/resource/action** của test.
5. **Fixture và payload class**, ưu tiên synthetic data.
6. **Expected/actual**, HTTP response, DB/queue/storage side effects.
7. **Tool/harness/version/ruleset** và người chạy.
8. **Run time/assessment period**, timezone khi cần.
9. **Scope exclusions**, assumptions và known limitations.
10. **Review/approval**, finding, remediation, retest, link đến artifact.
11. **Evidence classification/retention** và quyền truy cập.

### 29.3. Ma trận kiểm thử tổng hợp

| Test ID | Security requirement | Test tình huống | Kết quả kỳ vọng |
|---|---|---|---|
| SC-T01 | Input schema hợp lệ | Missing/unknown/oversized fields | Từ chối/giới hạn theo contract |
| SC-T02 | SQL không bị injection | Tên khóa học chứa SQL meta-characters | Query semantics không đổi, không lộ data |
| SC-T03 | Không command injection | Filename chứa shell metacharacters | Không thực thi lệnh ngoài thiết kế |
| SC-T04 | BOLA protection | Học viên A đọc submission của B | Deny, không trả field nhạy cảm |
| SC-T05 | Tenant isolation | Giáo viên tenant A export lớp B | Deny, không tạo file/job |
| SC-T06 | Field-level authorization | User sửa adminRole/tenantId qua JSON | Không đổi privileged fields |
| SC-T07 | Token validation | Token sai issuer/audience/signature | Reject |
| SC-T08 | Password reset | Token hết hạn hoặc bị dùng lại | Không reset trái policy |
| SC-T09 | Stored XSS | Comment chứa markup chủ động | Không chạy script theo security policy |
| SC-T10 | CSRF | Cookie session, thiếu/sai CSRF token | Reject với endpoint thuộc scope |
| SC-T11 | SSRF | URL redirect về private destination | Không kết nối destination bị cấm |
| SC-T12 | Path traversal | Filename chứa parent traversal/symlink case | Không đọc/ghi ngoài storage scope |
| SC-T13 | Upload validation | File giả type, archive bomb, oversized | Quarantine/reject/limit đúng policy |
| SC-T14 | Safe deserialization | Unapproved polymorphic type/deep nesting | Reject/bounded parse, không side effects |
| SC-T15 | TLS validation | Remote certificate sai hostname/issuer | Không trust-all |
| SC-T16 | Secret handling | Synthetic credential trong request/error | Không lộ trong response/log/trace |
| SC-T17 | Safe error handling | DB/vendor exception chứa internal info | Client không nhận stack/secret |
| SC-T18 | Logging integrity | Input có CRLF/control characters | Không tạo log event giả |
| SC-T19 | Resource limits | Large page/request, repeated jobs | Bounded CPU/memory/queue behavior |
| SC-T20 | Idempotency/replay | Duplicate job message | Không tạo tác động ngoài quy tắc |
| SC-T21 | Stale authorization | Revoke quyền trước worker execution | Xử lý theo scope/expiry policy |
| SC-T22 | Queue producer identity | Forged/untrusted producer | Message bị từ chối |
| SC-T23 | Storage authorization | Actor dùng link/file ID ngoài quyền | Deny theo policy |
| SC-T24 | Runtime configuration | Enable debug/trust-all trong test | Gate hoặc runtime checks phát hiện |
| SC-T25 | Supply-chain provenance | Artifact không đúng signer/digest | Deployment reject |
| SC-T26 | Monitoring health | Collector/scanner tắt trong test | Report error/gap, không báo Pass giả |

**Lưu ý:** Kết quả từ một test chỉ chứng minh behavior trong môi trường và phiên bản được kiểm tra. Những phép thử mô phỏng SSRF/file parsing/resource exhaustion phải chạy trong môi trường được phép và có giới hạn, tránh ảnh hưởng production.

### 29.4. Kiểm tra assertions và side effects

Khi test unauthorized export:
- Không chỉ assert status code 403/404.
- Kiểm tra **không có row read ngoài policy**, hoặc không có data leak ra response/cache/log.
- Không tạo queue message, object/file hay vendor request ngoài quyền.
- Nếu transaction rollback, kiểm tra asynchronous job/outbox có còn phát event không.
- Xác minh audit event của denied action phù hợp và không ghi token/PII thừa.

Những side effects có thể xảy ra sau khi request trả response. Với async workflow, test cần **poll/await có bounded timeout** hoặc dùng reliable test hooks thay vì kiểm tra tức thời rồi kết luận không có job.

### 29.5. Confidence, coverage và uncertainty

Một báo cáo assurance nên thể hiện:
- Những entry points/roles/tenants được kiểm tra.
- Những paths chỉ review code, chưa runtime test.
- Negative tests nào chưa bao phủ.
- Tool blind spots/scan failures.
- Mức độc lập của reviewer.
- Điều kiện thay đổi làm evidence mất giá trị.

Không gán nhãn High confidence chỉ vì số lượng test lớn; một nghìn unit tests trên happy path vẫn có thể bỏ sót một đường cross-tenant authorization.

## 30. Evidence catalog YAML minh họa

Đây là **mẫu dữ liệu nội bộ**, không phải kết quả kiểm toán thực tế hay định dạng bắt buộc của một standard.

~~~yaml
evidence_id: EVD-SC-EXPORT-2026-EXAMPLE
claim_id: CLAIM-SC-EXPORT-AUTHZ
requirements:
  - SC-REQ-01
  - SC-REQ-02
  - SC-REQ-08
control_owners:
  application: "Learning Backend"
  queue_and_storage: "Platform"
  assessment: "Security Assurance"
scope:
  system: "Learning Platform"
  environment: "production-equivalent-test"
  routes: ["/api/v1/classes/{id}/export"]
  components: ["java-api", "export-queue", "report-worker"]
  tenants: ["synthetic-tenant-a", "synthetic-tenant-b"]
  exclusions:
    - "Legacy batch export pending separate review"
source:
  commit: "Replace with actual source revision"
  build_digest: "Replace with actual artifact digest"
  dependencies: "Link to resolved manifest or SBOM"
  policy_version: "Replace with current control policy"
tests:
  - id: "SC-T05"
    expected: "Cross-tenant export is denied without side effects"
    actual: "Pending real test"
  - id: "SC-T20"
    expected: "Duplicate request creates no unauthorized duplicate export"
    actual: "Pending real test"
  - id: "SC-T21"
    expected: "Revoked authority follows async job policy"
    actual: "Pending real test"
evidence:
  methods:
    - "Authenticated integration API tests"
    - "Queue/job persistence assertions"
    - "Private storage probe with synthetic data"
    - "Authorization policy review"
  collected_at: "Populate actual timestamp"
  artifacts: []
assessment:
  status: "Insufficient evidence until tests executed"
  reviewer: "Assigned Security Assurance reviewer"
  limitations:
    - "No claim about other export paths"
review_triggers:
  - "Change to authorization, role, tenant or job schema"
  - "New gateway/worker path or storage policy"
  - "Security finding or runtime drift"
~~~

**Không ghi thông tin xác thực thật vào YAML.** Khi triển khai, các giá trị placeholder phải được thay bằng evidence references và expected/actual results có thể kiểm chứng.

## 31. Case study xuyên suốt: bảo vệ luồng xuất bảng điểm

### 31.1. Business context và trust boundary

Nền tảng có:
- Browser học viên/giảng viên.
- API gateway và Java Learning API.
- Cơ sở dữ liệu nhiều tenant.
- Queue nhận yêu cầu tạo báo cáo.
- Report worker.
- Private object storage và signed download URL.
- Dịch vụ thông báo email.

Yêu cầu: giảng viên chỉ xuất điểm của các lớp mình đang được phân công, theo đúng tenant. Học viên không được xuất bảng điểm của lớp khác. Bản báo cáo phải chỉ chứa trường được duyệt và được tải xuống đúng actor/quyền trong kỳ cho phép.

~~~mermaid
flowchart LR
    UI["Teacher browser"] -->|"authenticated export request"| API["Learning API"]
    API -->|"authorized job reference"| Q[["Queue"]]
    Q --> W["Report Worker"]
    W --> DB[("Grades DB")]
    W --> S[("Private report storage")]
    API -->|"authorized download"| S
    API --> N["Email notification"]
~~~

### 31.2. Anti-pattern thiết kế đầu tiên

Giả sử API:
1. Nhận classId và tenantId từ request.
2. Chỉ kiểm tra token có role TEACHER.
3. Đưa nguyên request lên queue.
4. Worker dùng tenantId trong message để query.
5. Worker lưu file với tên dựa trên classId.
6. API gửi signed URL có thời hạn rất dài.

Những sai lệch:
- Role TEACHER không chứng minh được phân công lớp.
- tenantId do client khai không đáng tin.
- Queue message có thể giả/replay/stale.
- Worker có thể có DB permission quá rộng.
- File name/path có nguy cơ collision/enumeration.
- URL không được ràng buộc đủ với actor/resource lifecycle.
- Event/log có thể chứa bảng điểm hoặc token.

### 31.3. Threat analysis

| Threat | Boundary | Harm/impact |
|---|---|---|
| Thay classId | Browser → API | Disclosure điểm lớp khác |
| Giả tenantId | API → DB/worker | Cross-tenant data leak |
| Role-only authorization | API policy | Teacher vượt quyền phân công |
| Forged/replayed job | API/queue → worker | Export trái quyền, duplicate file |
| Job chạy sau revoke | Identity state → worker | Quyền cũ tiếp tục có hiệu lực ngoài ý muốn |
| Storage key đoán được | Worker → storage | Truy cập dữ liệu không được cấp quyền |
| Signed URL quá rộng | API → browser/storage | Link tái sử dụng hoặc chia sẻ sai |
| Vendor notification log lộ | App → email service | PII/file URL bị chia sẻ ngoài mục đích |
| Resource flooding | API → queue | Availability của worker và database suy giảm |

### 31.4. Secure design đề xuất

1. Server xác minh principal và quan hệ actor–tenant–class qua nguồn authoritative.
2. Lệnh export chỉ chứa **job ID và scope được server phê duyệt**, không tin role tự khai từ client.
3. Queue giới hạn producer identity; consumer validate schema, sender và job reference.
4. Worker kiểm tra permission theo policy khi thực thi hoặc xác minh delegated authorization với scope/TTL rõ.
5. Query database dùng tenant/object scoping và parameterized statements; DB role giới hạn.
6. File được lưu tại private storage với server-generated opaque key, không xây path từ filename do client gửi.
7. Download yêu cầu authorization hoặc signed link ràng buộc scope/expiry theo thiết kế.
8. Reports dùng data minimization, không đưa private notes/credentials.
9. Idempotency và retry controls tránh tạo nhiều bản sao/side effects.
10. Audit log actor, class, job, resource, decision, outcome và request correlation, không ghi nội dung điểm/raw token.
11. Có quota, timeout, file size bounds, retention và deletion.
12. Có tests bao phủ cross-tenant, forged/replay/stale jobs, URL reuse, gateway bypass và monitoring health.

### 31.5. Java pseudo-code: tạo job có quyền

~~~java
public UUID requestGradeExport(AppPrincipal actor, long classId) {
    ClassEntity courseClass = classRepository.findById(classId)
            .orElseThrow(NotFoundException::new);

    if (!classPolicy.canExportGrades(actor, courseClass)) {
        throw new AccessDeniedException("Export not permitted");
    }

    // Service tạo job record có tenant/scope lấy từ nguồn đáng tin.
    ExportJob job = exportJobRepository.create(
            actor.subjectId(),
            courseClass.tenantId(),
            courseClass.id(),
            ExportPurpose.TEACHER_GRADE_REPORT
    );

    // Outbox event chỉ chứa opaque job ID, không truyền raw grades.
    exportOutbox.enqueue(new ExportJobRequested(job.id()));
    return job.id();
}
~~~

Với hệ thống thực cần transaction/outbox consistency, retry/idempotency, actor state changes, logging, rate limits và storage permissions. **Không thể bảo đảm atomicity** giữa DB và queue chỉ bằng hai lệnh liên tiếp mà không có thiết kế transaction/outbox thích hợp.

### 31.6. Worker xử lý job

~~~java
public void handle(ExportJobRequested message) {
    ExportJob job = jobRepository.findById(message.jobId())
            .orElseThrow(InvalidJobException::new);

    if (!jobPolicy.canExecute(job)) {
        jobRepository.markRejected(job.id());
        return;
    }

    // Query dựa trên scope trong job record đã được xác minh.
    GradeReport report = gradeRepository
            .loadAuthorizedReport(job.tenantId(), job.classId());

    // Key lưu trữ do server tạo; quyền worker bị giới hạn.
    String objectKey = reportKeyFactory.newKey(job.tenantId());
    privateObjectStorage.put(objectKey, report.bytes());

    jobRepository.markCompleted(job.id(), objectKey);
}
~~~

Đây là mô hình minh họa, chưa xử lý concurrency/atomicity, cleanup khi storage write thành công nhưng DB update thất bại, workflow cancellation hoặc crash recovery. Kiến trúc thật cần state machine và idempotency.

### 31.7. Kế hoạch test/evidence

| Kịch bản | Test | Evidence |
|---|---|---|
| Teacher đúng lớp | Allow export và download | API + job + object outputs |
| Teacher khác lớp | Deny, không queue/file | HTTP, DB/outbox, storage assertions |
| Learner tự gửi role=TEACHER | Deny, bỏ header giả | AuthN/AuthZ test |
| Cross-tenant job message | Worker reject | Queue/worker trace, no side effects |
| Duplicate job | Chỉ có số report theo policy | Idempotency test |
| Revoke trước khi worker chạy | Xử lý theo delegated/recheck policy | Temporal authorization test |
| Storage prefix ngoài tenant | Deny | Effective IAM policy + negative test |
| Signed URL hết hạn/chia sẻ | Hành vi đúng scope/TTL/revocation design | Download tests |
| Report lớn | Bounded processing | Resource/queue metrics |
| Logging | Không có raw grades/tokens | Synthetic data log scan |
| Legacy export | Khảo sát riêng | Inventory/evidence gap record |
| Release mapping | Đúng commit/build/config | CI artifact và deployment digest |

### 31.8. Kết luận có phạm vi

> **Claim:** Trong scope Java API, export queue, report worker và private storage đã được định danh, các đường xuất bảng điểm được kiểm tra có server-side authorization và giới hạn dữ liệu/tenant; negative tests không cho phép export trái quyền hoặc side effects ngoài policy trên build và môi trường được ghi.
>
> **Limitations:** Luồng legacy batch và một vendor callback chưa được kiểm tra; không suy rộng kết luận sang hai đường này.
>
> **Next steps:** Hoàn thiện discovery, test trên production-equivalent configuration, đối chiếu runtime deployment và retest khi quyền/queue policy thay đổi.

Đây là ví dụ cách **trình bày kết luận**, không phải kết quả kiểm tra một hệ thống thật.

## 32. Findings, remediation, retest và residual risk

### 32.1. Phân loại kết quả trung thực

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| **Pass/Supported** | Control được chứng minh đạt tiêu chí trong scope/kỳ | Cross-tenant denial test đúng trên API/worker được kiểm tra |
| **Fail/Unsupported** | Có sai lệch quan sát được | API trả điểm tenant B cho teacher A |
| **Insufficient evidence** | Chưa đủ coverage/nguồn để kết luận | Chưa kiểm tra legacy job worker |
| **Not applicable** | Requirement không áp dụng có căn cứ | Endpoint không có hoạt động upload trong scope |
| **Exception/accepted risk** | Sai lệch nội bộ được quản trị theo thẩm quyền, không biến thành Pass | Legacy endpoint giới hạn có thời hạn và kế hoạch đóng |

Lỗi chưa được tái hiện trong test nhưng chưa có coverage phù hợp **không được tự kết luận không tồn tại**. Cần đánh giá evidence gap và monitoring tùy risk.

### 32.2. Finding ví dụ: BOLA trong API

**Finding ID:** SC-FIND-EXAMPLE-01.

**Observation:** Teacher A gọi API GET /classes/{id}/grades với ID lớp B và nhận dữ liệu B dù không có quan hệ phân công.

**Evidence:** test principal/class mapping, request/response đã dùng synthetic data, relevant code path, query trace, build/deployment identifiers.

**Root cause:** chỉ kiểm tra role TEACHER, thiếu resource relationship/tenant authorization.

**Impact:** truy cập thông tin điểm ngoài quyền, ảnh hưởng confidentiality và privacy; có thể mở rộng qua export/worker nếu dùng cùng policy.

**Containment:** giới hạn endpoint hoặc chặn đường truy cập trái quyền tùy thẩm quyền và mức impact.

**Remediation:** scoped repository/policy check, method-level enforcement khi thích hợp, kiểm tra các sibling endpoints và background jobs.

**Retest:** teacher hợp lệ vẫn xem lớp của mình; teacher khác bị từ chối; không có DB query/response/queue/export side effects trái quyền; runtime build mapping đúng.

**Closure evidence:** source diff, PR approval, test results, deployment and runtime probe, reviewer conclusion và residual risk nếu chưa kiểm tra sibling paths.

### 32.3. False positives và false negatives

Một scanner báo injection trên một query đã bind parameters có thể là false positive. Cần reviewer có năng lực xác minh data flow và lưu rationale. Không đánh dấu false positive chỉ vì “test chưa thấy exploit”.

Ngược lại, scanner trả zero findings có thể do tool không chạy, thiếu path, ruleset yếu hoặc scanner không hiểu business logic. Chương trình phải xem **scan health, coverage và negative/security regression tests**.

### 32.4. Risk acceptance phải có giới hạn

Một quyết định chấp nhận residual risk nên ghi:
- Finding, asset, data, entry points, affected actor.
- Kịch bản lạm dụng và impact/likelihood/uncertainty.
- Control nào đạt, control nào fail, evidence liên quan.
- Compensating controls, giới hạn thời gian và phạm vi.
- Remediation options, cost/feasibility và plan.
- Người có thẩm quyền, nghĩa vụ bắt buộc và lần review tiếp.
- Điều kiện đánh giá lại khi incident hoặc system change.

Acceptance nội bộ không làm lỗ hổng tự biến mất hoặc tự miễn những yêu cầu pháp lý/hợp đồng bắt buộc.

### 32.5. Phân biệt sửa lỗi và khắc phục gốc rễ

Ví dụ sau một BOLA:
- **Fix cục bộ:** thêm check trong một controller.
- **Root-cause remediation:** cập nhật authorization policy pattern, repository scoping, code review checklist, tests các entry points tương tự, queue worker permissions, monitoring và kiến trúc trust boundaries.
- **Assurance:** xác minh bản sửa được deploy và các đường sibling đã được xem, báo scope còn thiếu.

Chỉ đóng ticket khi status chuyển Done chưa phải security assurance.

## 33. Continuous secure coding assurance trong SDLC

### 33.1. Khi nào cần reassess?

- Thêm API, route, GraphQL resolver, gRPC method hoặc admin endpoint.
- Đổi user role, tenant model, permission, workflow hoặc token lifecycle.
- Thêm parser/file type, URL fetch, rendering engine hoặc external command.
- Mở rộng dữ liệu cá nhân, new vendor, new analytics purpose.
- Đổi queue/event schema, worker, retry, storage hoặc signed URL behavior.
- Đổi framework/JDK/dependency/container runtime.
- Thay cryptographic algorithm, TLS trust store, key/certificate/secret lifecycle.
- Cloud IAM/network/DB policy, CORS/CSRF hoặc feature flags thay đổi.
- Có vulnerability advisory, incident, pen test finding hoặc complaint.
- Test/tool bị tắt, scan scope thu hẹp hoặc evidence freshness không còn.

### 33.2. Tích hợp vào vòng đời

| Giai đoạn | Hoạt động secure coding/assurance | Evidence |
|---|---|---|
| **Discovery** | Assets, data, abuse cases, security/privacy objectives | Context and risk records |
| **Architecture** | Trust boundaries, threat model, policy design | DFD, decisions, requirements |
| **Implementation** | Safe APIs, authorization, validation, secrets | Code, review, unit tests |
| **PR** | Risk-aware reviewer, policy/scan gates | Diff, approvals, findings |
| **CI/CD** | SAST/SCA/secrets/config tests, artifacts, provenance | Tool results and build mapping |
| **Release** | Approvals, config, deployment mapping, security regression | Release record, deployment evidence |
| **Operations** | Monitoring, rate limits, runtime checks, issues | Logs, alerts, control health |
| **Incident** | Containment, analysis, remediation and retest | Incident record, evidence |
| **Periodic assurance** | Review coverage, exceptions, gaps and change triggers | Assessment, control status |
| **Decommission** | Revoke credentials, stop endpoints, handle stored data | Cleanup/retirement evidence |

### 33.3. Bảo vệ chính evidence pipeline

- Scanner failure phải báo **tool error hoặc incomplete result**, không biến thành Pass.
- Test reports gắn đúng commit/build và không bị replace bởi job khác.
- Tool và ruleset versions được theo dõi.
- Có synthetic control tests chứng minh scanner/policy gate vẫn phát hiện một lỗi mẫu trong môi trường kiểm soát khi thích hợp.
- Logs/metrics có health checks, timestamp và source coverage.
- Evidence có access/retention phù hợp, không đưa production secrets vào dashboard.
- Khi một test bị skip hoặc quarantine, report phải thể hiện rõ, không đếm như đã pass.
- Khi bypass gate qua emergency change, cần approval, hạn, log và post-release retest.

### 33.4. Human review và automation bổ trợ nhau

SAST/SCA có thể kiểm tra diện rộng nhanh; unit/integration tests chứng minh behavior đã định; pen test khám phá một số đường attacker; manual review hiểu domain logic; runtime monitoring phát hiện drift/abuse. Một chương trình trưởng thành **kết hợp các nguồn**, không chọn một công cụ làm chứng nhận “ứng dụng an toàn”.

## 34. Roles, RACI và trách nhiệm

R = Responsible (thực hiện), A = Accountable (chịu trách nhiệm cuối theo phân quyền), C = Consulted, I = Informed.

| Hoạt động | Product/Data owner | Developer/Tech Lead | AppSec/Assurance | Platform/DevOps | Risk owner |
|---|---|---|---|---|---|
| Xác định abuse cases và impact | A/R | R hỗ trợ | C | C | I |
| Security requirements/acceptance criteria | C | A/R kỹ thuật | R/C | C | I |
| Thiết kế authz/data flow | C | A/R | C | C | I |
| Viết code và unit/integration tests | I | A/R | C | C | I |
| PR secure review | C | A/R, reviewer độc lập theo policy | C/R khi high-risk | C | I |
| SAST/SCA/secrets/config scanning | I | R triage | A về assurance policy | R vận hành gates | I |
| CI/CD và artifact/deployment mapping | I | C | C | A/R | I |
| Security testing/assessment | C | R hỗ trợ | A/R | R hỗ trợ | I |
| Remediation và retest | C | A/R phần code | R kiểm chứng | R phần infra | I |
| Residual risk acceptance | C | C | C | C | A/R |
| Incident triage và emergency controls | C | R kỹ thuật | R/C | R | A hoặc I theo quy trình |
| Continuous monitoring và review | C | R phần code | A/R assurance | R vận hành | I |

Bảng **minh họa**, không thay RACI tổ chức. Cần xác định một owner chịu trách nhiệm rõ cho control và tách vai trò self-attestation khỏi independent review theo yêu cầu kiểm toán.

## 35. Metrics và báo cáo quản trị

| Metric | Mục đích | Sai lầm cần tránh |
|---|---|---|
| % high-risk APIs có object/tenant negative tests | Coverage authz | Test một route không đại diện mọi route |
| % security requirements trace tới code/test/evidence | Traceability | Một dấu tick không chứng minh effective control |
| Số critical/high findings đang mở và quá hạn | Risk debt | Severity không đủ để hiểu impact |
| Median remediation time theo loại lỗ hổng | Năng lực fix | Fix nhanh nhưng không retest vẫn chưa chắc đúng |
| % remediations có runtime retest | Chất lượng closure | Ticket Done không phải evidence |
| % PR high-risk có reviewer đúng policy | Review governance | Reviewer không có context vẫn có thể bỏ lỗi |
| % CI security checks chạy thành công | Tool health | Không chạy scanner khác 0 finding |
| SCA findings theo deployed artifact | Dependency exposure | Manifest scan không đại diện tất cả runtime |
| Số secrets exposure incidents và time-to-revoke | Secret hygiene/response | Không thấy secret không chứng minh không có |
| % endpoints có abuse-case tests | Threat-to-test coverage | Mẫu số thiếu shadow routes |
| Số bypass/direct paths hoặc authz regressions | Trust boundary visibility | Ít finding có thể do discovery yếu |
| % critical control evidence còn hiệu lực theo kỳ | Evidence freshness | Evidence stale không thể báo Pass hiện tại |
| % exceptions quá hạn | Tính kỷ luật risk governance | Exception hết hạn không tự được gia hạn |
| % releases mapping tới scanned/tested artifacts | Build-to-runtime integrity | CI pass không chứng minh deploy đúng artifact |
| Số privacy/security complaints/incident patterns | Phản hồi thực tế | Không có complaint chưa chứng minh không harm |

Báo cáo nên nêu **top risks, controls thực sự đã chứng minh, scope/period, bất định, findings, owners và quyết định cần lãnh đạo hỗ trợ**, không chỉ một “secure coding score” tổng hợp.

## 36. Những sai lầm thường gặp

**“Code compile và unit tests pass nghĩa đã secure.”** Chưa đủ. Unit tests có thể chỉ kiểm tra happy path, không bao phủ BOLA, SSRF, race hoặc runtime drift.

**“Dùng framework bảo mật nghĩa mọi endpoint được bảo vệ.”** Có thể sai do route exclusions, cấu hình, direct paths hoặc thiếu object authorization.

**“Client đã validate nên backend có thể tin input.”** Client có thể bị sửa hoặc API được gọi trực tiếp.

**“Đăng nhập thành công nghĩa có quyền đọc record ID bất kỳ.”** Authentication không thay resource/tenant authorization.

**“Một role TEACHER đủ để sửa điểm mọi lớp.”** Cần relationship, tenant, resource state và action policy.

**“Escape một lần giải quyết mọi injection/XSS.”** Từng interpreter/sink cần cách tách code/data hoặc encoding phù hợp.

**“Dùng PreparedStatement là đủ bảo mật database.”** Còn cần DB grants, tenant scope, data minimization, query/resource limits.

**“CORS bảo vệ API khỏi người ngoài.”** CORS là policy trình duyệt; không thay AuthN/AuthZ và non-browser clients vẫn gọi API.

**“Mọi JWT đều đáng tin sau khi decode.”** Phải validate signature, issuer, audience, expiry/type và quyền.

**“Thêm HttpOnly cookie giải quyết CSRF/XSS.”** Cookie flags hỗ trợ một số threats nhưng không tự giải quyết mọi điều kiện.

**“Chặn localhost là đã chống SSRF.”** Có redirects, DNS rebinding, IPv6, link-local, private networks và egress paths.

**“Filename không có hai dấu chấm là an toàn.”** Path traversal còn có encoding, symlinks và TOCTOU; dùng opaque IDs và permissions.

**“File có đuôi PDF thì an toàn để parse.”** Cần kiểm tra content/limits, parser behavior, isolation và storage access.

**“Base64 là mã hóa.”** Đây là encoding, không bảo vệ confidentiality.

**“SHA-256(password) đủ để lưu mật khẩu.”** Cần password hashing chuyên dụng và tham số phù hợp.

**“Một scanner 0 findings chứng minh không còn vulnerability.”** Scanner có blind spots, có thể không chạy và khó nhận diện business logic flaws.

**“Một SCA report chứng minh dependency đã được vá ở production.”** Phải nối dependency version với deployed artifact, kiểm tra scope và runtime.

**“Không thấy secrets ở HEAD nghĩa chưa từng lộ.”** Commit history, images/artifacts/CI logs có thể còn credential.

**“HTTP 403 chứng minh không có side effect.”** API có thể đã tạo file/queue event trước khi deny.

**“Hệ thống không có exception stacktrace trên UI là không lộ dữ liệu.”** Logs/traces/metrics có thể vẫn chứa raw token và dữ liệu cá nhân.

**“Deploy code fix là finding đóng.”** Cần retest đúng artifact/config, kiểm tra sibling paths và evidence.

**“Risk accepted nghĩa technical failure trở thành Pass.”** Acceptance không đổi sự thật kỹ thuật hoặc nghĩa vụ bắt buộc.

**“Secure coding là trách nhiệm duy nhất của AppSec.”** Product, Developers, Platform, Data, QA, Security và Risk owners đều góp phần.

## 37. Bài tập thực hành

### Bài tập A — BOLA trong API học viên

Một API GET /api/submissions/{id} chỉ kiểm tra bearer token hợp lệ rồi trả submission. Hãy:
1. Chỉ rõ trust boundary, asset, actor và threat.
2. Viết security requirement có acceptance criteria.
3. Đề xuất policy theo principal, tenant, ownership/resource relationship.
4. Thiết kế negative tests cho actor khác user, tenant và role.
5. Xác định side effects và dữ liệu cần kiểm tra.
6. Viết một Claim–Argument–Evidence với scope.

**Gợi ý:** Một token hợp lệ chưa chứng minh quyền trên submission.

### Bài tập B — SQL injection và quyền dữ liệu

Hệ thống tìm khóa học theo keyword, sort field và tenant. Team sửa keyword thành bind parameter nhưng sort field vẫn nối chuỗi từ query string, còn tenantId lấy từ header do browser gửi.

Hãy phân loại lỗ hổng còn lại, thiết kế allowlist sort và tenant authorization, đề xuất DB permission scope và tests. Nêu vì sao parameterized keyword không đủ để bảo vệ mọi trust boundary.

### Bài tập C — Stored XSS trong diễn đàn

Người học gửi nội dung thảo luận có rich text, được hiển thị trong browser và email notification.

Hãy xác định các sinks khác nhau, policy rich HTML cho phép, output encoding/sanitization, CSP defense in depth và negative tests. Nêu giới hạn khi chỉ kiểm tra HTML text context mà không kiểm tra template/URL/attribute contexts.

### Bài tập D — SSRF và import URL

Một backend Java cho giáo viên nhập URL để lấy tài liệu. Đội kỹ thuật chỉ kiểm tra chuỗi bắt đầu bằng https và chặn “localhost”.

Hãy thiết kế allowlist, redirect/DNS/IP validation, egress policy, request limits, credential isolation và test matrix. Nêu các trường hợp IPv6, link-local, DNS rebind và hostname encoding.

### Bài tập E — Upload và file parsing

Nền tảng nhận PDF/ZIP nộp bài, xử lý OCR và lưu object. Một người dùng gửi archive lớn chứa file có tên bất thường.

Hãy thiết kế quarantine, content verification, resource bounds, scanner/worker isolation, random object keys, per-user/tenant authorization, retention và tests. Nêu cách báo error khi scanner unavailable theo policy.

### Bài tập F — Token và CSRF

Ứng dụng dùng session cookie cho web và bearer token trong Authorization header cho mobile. Team muốn tắt CSRF protection toàn hệ thống “vì API đã dùng JWT”.

Hãy phân tích từng authentication mechanism và endpoint, những nơi browser tự gửi credential, SameSite/CORS/CSRF tokens, XSS/token storage và tests. Không đưa ra kết luận chung cho mọi đường khi chưa có data-flow evidence.

### Bài tập G — Queue và stale authorization

Teacher tạo export job khi có quyền lớp A. Sau đó quyền bị thu hồi nhưng worker nhận message trễ. Đồng thời có duplicate message.

Thiết kế rule cho recheck/delegation TTL, queue identity, job status, idempotency, storage keys, URL expiry và audit. Viết test kiểm tra không có unauthorized side effects.

### Bài tập H — Đọc log và secret incident

Một developer vô tình thêm API token vào log trong một release. Secret scanner HEAD không phát hiện nữa sau khi code được sửa.

Hãy đề xuất:
- Điều tra thời kỳ và nơi logs/artifacts đã lưu.
- Rotation/revoke và containment.
- Giới hạn quyền truy cập logs.
- Redaction và regression tests.
- Bằng chứng retest, deployment mapping và incident closure.
- Phân biệt “không còn trong code” với “không còn giá trị sử dụng”.

### Bài tập I — Security gate

CI báo 0 critical findings nhưng SAST job đã bị skip vì timeout. SCA scan chạy trên manifest khác với artifact deploy; reviewer xác nhận bằng biểu tượng Approved.

Hãy đánh giá evidence quality, coverage, scanner health, provenance, build/deploy mapping và policy gate. Viết kết luận nào có thể/không thể đưa ra và remediation cần ưu tiên.

### Bài tập J — Security assurance report

Cho kỳ đánh giá giả định:
- 60 endpoints được inventoried, 8 endpoint legacy chưa có owner.
- 40/60 có negative authz tests đúng scope.
- Một endpoint thực sự để lộ điểm tenant khác khi sửa classId.
- 3 services có lỗi debug logging chứa token ở staging, chưa biết production impact.
- Dependency scanner lỗi ở hai lần chạy gần nhất.
- 100% API production dùng HTTPS.
- Report worker export chưa được kiểm tra stale authorization.

Hãy:
1. Phân biệt control failure, design/ownership gap và evidence gap.
2. Viết claim có scope, period và limitations.
3. Ưu tiên risk theo data/impact thay vì chỉ đếm findings.
4. Đề xuất containment, root-cause remediation, retest và owner.
5. Nêu tại sao HTTPS coverage không chứng minh BOLA đã được giải quyết.
6. Xác định câu hỏi cần điều tra trước khi kết luận production token exposure.
7. Thiết kế dashboard không biến scanner failure thành “zero vulnerabilities”.

### Bài tập K — Code review theo threat

Một PR thêm tính năng “Preview ảnh từ URL” và “Tải kết quả OCR”. PR đã có validation độ dài URL, nhưng service HTTP client cho phép redirect; downloaded file path được lấy từ query parameter; logs ghi full URL.

Hãy đóng vai security reviewer: viết comment cụ thể chỉ ra risk, sink, controls, test và evidence yêu cầu trước merge. Nêu data classification và cách không ghi credentials trong URL/log.

### Bài tập L — Thiết kế secure coding program

Lập kế hoạch 90 ngày cho một nhóm Java nhỏ:
- Thống kê entry points và high-risk workflows.
- Định nghĩa secure coding baseline và training theo threat.
- Thêm PR review checklist, SAST/SCA/secrets gates phù hợp.
- Xây negative integration tests cho tenant/object authorization.
- Giảm privileged dependencies/secrets và review configurations.
- Gắn findings với owner, due date, retest và exceptions.
- Tạo evidence catalog và metrics cho CISO.
- Xác định trigger reassessment sau feature/dependency/runtime changes.

**Tiêu chí bài làm tốt:** có risk prioritization, owner, measurable acceptance criteria, evidence/limitations và cách điều chỉnh khi kiểm thử phát hiện failure.

## 38. Checklist secure coding có bằng chứng

Checklist hỗ trợ review và assurance; **đánh dấu đủ ô không đồng nghĩa mọi vulnerability đã được loại bỏ**.

- [ ] Có asset/data classification, entry point inventory và threat/abuse scenarios.
- [ ] Security requirements có ID, acceptance criteria và owner.
- [ ] Client, vendor, queue, files, database, model outputs và headers được đánh giá theo trust boundary.
- [ ] Input được validate server-side về type, length, range, depth, business rule và resource limits.
- [ ] SQL/NoSQL/LDAP/OS/template sinks sử dụng safe APIs, parameter binding/allowlists phù hợp.
- [ ] Authentication có credential/session/token lifecycle và validation đầy đủ.
- [ ] Authorization kiểm tra principal–tenant–resource–action–state trên mọi entry point.
- [ ] Không mass assignment hoặc trả sensitive fields qua raw entity.
- [ ] XSS controls đúng context; rich HTML được sanitize theo policy khi cần.
- [ ] CSRF/CORS/cookie/security headers được thiết kế theo thực tế browser/session.
- [ ] SSRF có destination policy, redirect/DNS/IP/egress và resource bounds.
- [ ] File upload/download có ownership, content validation, private storage và limits.
- [ ] Deserialization/parser có schema, type restrictions, depth/size và safe configuration.
- [ ] Crypto dùng approved libraries/algorithms, key management và secure randomness.
- [ ] TLS/client validation không bị trust-all hoặc bypass hostname.
- [ ] Secrets không nằm trong code, logs, URLs, artifacts và có rotation/incident response.
- [ ] Error handling không lộ internal details và không fail-open trên action nhạy cảm.
- [ ] Logging structured, có audit cần thiết và bảo vệ dữ liệu nhạy cảm.
- [ ] API/queue/worker có rate limits, timeouts, concurrency/quotas và idempotency khi cần.
- [ ] Queue/webhook xác minh identity, schema, replay và stale-authorization rules.
- [ ] Dependencies, build plugins, images và artifacts được quản trị/scan theo risk.
- [ ] CI/CD gates có tool health, ruleset version, exception approval và build mapping.
- [ ] Secure code reviews chú ý business authorization và data flows, không chỉ style.
- [ ] Positive/negative/integration tests bao phủ input, identity, authz, side effects, bypass.
- [ ] Test kết quả có commit/build/config/env/actor/resource và expected/actual.
- [ ] Scanner false positives được triage bằng evidence, không bỏ qua tùy tiện.
- [ ] Không tính scanner skipped/failed là “0 finding”.
- [ ] Có traceability risk → requirement → control/code → test/evidence → assessment.
- [ ] Phân biệt design, implementation và operating effectiveness.
- [ ] Assurance conclusion nêu scope, period, population, confidence và exclusions.
- [ ] Findings có impact, root cause, owner, remediation, retest và residual risk decision.
- [ ] Risk acceptance không biến Failed control thành Pass hoặc bỏ nghĩa vụ bắt buộc.
- [ ] Có monitoring/review triggers khi code, framework, data, identity, policy hoặc vendor thay đổi.

## 39. Ghi nhớ

- **Secure coding là thực hành xây dựng và duy trì code đáp ứng mục tiêu bảo mật**, không chỉ viết chương trình chạy đúng hoặc đạt điểm scanner.
- **Threats và trust boundaries phải định hướng requirements**: user, service, queue, file, vendor và runtime không có cùng mức tin cậy.
- **Input validation không thay output encoding**, SQL parameter binding không thay authorization, TLS không thay purpose limitation.
- **Authentication không đồng nghĩa authorization**; phải kiểm tra actor có quyền trên đúng object, tenant, action và trạng thái.
- **Server phải bảo vệ dữ liệu và side effects trên mọi entry point**, kể cả worker, cache, export, storage và đường legacy.
- Injection, XSS, CSRF, SSRF, path traversal, deserialization và resource exhaustion cần controls **đúng ngữ cảnh**; không có một regex hoặc scanner thay được toàn bộ.
- Secrets, keys, tokens và logs là một phần quan trọng của secure coding; khi credential lộ cần **revoke/rotate và điều tra**, không chỉ xóa dòng source.
- Safe libraries/frameworks là nền tảng hữu ích, nhưng cấu hình, privileges, data flow và production behavior vẫn cần kiểm chứng.
- **SAST, SCA, DAST, code review, fuzzing, negative tests và runtime monitoring bổ trợ nhau**; một kết quả Pass chỉ đúng trong scope, tool và kỳ được kiểm tra.
- Assurance cần **Claim–Argument–Evidence**, kết nối threat/risk, requirements, code controls, tests, deployed artifact và đánh giá có giới hạn.
- **Control failure khác evidence gap**; cả hai phải được quản lý trung thực bằng remediation, retest, ownership và risk decision.
- Chương trình mature duy trì vòng lặp **threat modeling → secure implementation → security tests → evidence assessment → findings/remediation → continuous monitoring/reassessment** xuyên suốt phát triển và vận hành.




