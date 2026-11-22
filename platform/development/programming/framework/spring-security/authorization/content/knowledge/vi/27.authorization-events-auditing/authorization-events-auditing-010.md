# Chính sách lưu giữ, truy cập và tính toàn vẹn của bản ghi audit

Một hệ thống Spring Security có thể ghi lại việc người dùng bị từ chối quyền, thay đổi role, truy cập tài nguyên nhạy cảm hoặc sử dụng quyền quản trị. Nhưng **có log** chưa đủ để gọi đó là một hệ thống audit đáng tin. Sau sự cố, tổ chức phải còn tìm được bằng chứng; người không có nhiệm vụ không được đọc hoặc xuất bằng chứng; người có quyền với ứng dụng không được âm thầm sửa/xóa dấu vết. Đồng thời bản ghi chứa thông tin cá nhân không được giữ vô thời hạn.

Bài thuộc nhóm **Sự kiện và audit** của **Spring Security - authorization**, tập trung vào ba trụ cột: **retention (lưu giữ và hủy đúng hạn), access (kiểm soát truy cập), integrity (tính toàn vẹn và khả năng phát hiện sửa đổi)**. Các ví dụ dùng Java 17+, kết nối với cách Spring Security bảo vệ API quản trị audit và với Spring Boot Actuator. Thời hạn minh họa trong bài **không phải quy định pháp luật áp dụng cho mọi hệ thống**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao audit record cần được bảo vệ trong toàn bộ vòng đời: tạo, truyền, lưu, truy vấn, xuất, đóng băng, khôi phục và hủy.
- Thiết kế bảng chính sách cho từng nhóm sự kiện, xác định thời điểm bắt đầu đếm hạn, thời hạn có thể tra cứu nhanh, thời hạn lưu tổng cộng, ngoại lệ legal hold và trách nhiệm phê duyệt.
- Phân tách quyền **ghi audit**, **đọc**, **xuất**, **đặt hold**, **thay đổi retention**, **xóa theo chính sách**, **quản lý khóa** và **kiểm tra tính toàn vẹn**.
- Phân biệt confidentiality, integrity, availability, authenticity và completeness; hiểu giới hạn của checksum, SHA-256, HMAC, chữ ký số, hash chain và immutable/WORM storage.
- Viết và chạy một ví dụ Java 17 tạo chuỗi HMAC có thể phát hiện bản ghi bị sửa, đồng thời nhận ra việc cắt đuôi cần một checkpoint độc lập.
- Áp dụng guard ở Spring Security và tầng lưu trữ, kiểm thử truy cập trái phép, retention expiry, legal hold, lỗi collector và quy trình điều tra.

## 2. Audit record là loại dữ liệu nào?

Audit record là một bằng chứng có cấu trúc ghi nhận **một sự kiện quan trọng đối với trách nhiệm giải trình**. Nó có thể bắt nguồn từ `AuthorizationDeniedEvent`, `AuthenticationFailureEvent`, hoạt động quản trị người dùng, cập nhật policy, truy vấn/export audit hoặc hành động của job hủy dữ liệu.

Một record nên giúp trả lời các câu hỏi *khi nào, ở đâu, ai hoặc hệ thống nào, đã yêu cầu hành động gì, trên tài nguyên nào, kết quả và dấu vết liên hệ là gì*. Tuy nhiên không phải tất cả các trường đều luôn được biết. Ví dụ `AuthorizationDeniedEvent` báo quyết định authorization bị từ chối, nhưng không mặc định chứa HTTP status cuối cùng hoặc toàn bộ lý do nghiệp vụ.

Ví dụ bản ghi đã được **chuẩn hóa và giảm thiểu dữ liệu**:

```json
{
  "schemaVersion": 1,
  "eventId": "e61f8637-b614-4f1d-936c-a37a85267d95",
  "eventType": "AUTHORIZATION_DENIED",
  "occurredAt": "2026-11-05T08:10:11Z",
  "receivedAt": "2026-11-05T08:10:12Z",
  "service": "order-api",
  "environment": "production",
  "actorRef": "actor-17",
  "tenantRef": "tenant-a",
  "requestId": "req-56c",
  "resourceType": "ORDER",
  "action": "READ",
  "decision": "DENY",
  "policyRef": "order.read.v3",
  "classification": "SECURITY_AUDIT"
}
```

Đây là **schema ứng dụng tự thiết kế**, không phải payload mà Spring Security luôn tự sinh. Các trường được đặt theo hợp đồng riêng: `eventId` để chống ghi trùng; `occurredAt` là thời điểm sự kiện được nhận biết; `receivedAt` là thời điểm collector tiếp nhận; `requestId`/trace ID giúp nối log; `actorRef`/`tenantRef` là mã tham chiếu được bảo vệ thay vì raw credential.

Không ghi mặc định mật khẩu, OTP, Bearer token, cookie phiên, full URL có dữ liệu cá nhân, request body, toàn bộ `Authentication` hoặc `Principal`. **Hash một email hoặc số điện thoại không tự động biến nó thành dữ liệu vô danh**: với tập giá trị nhỏ, hash có thể bị dò; mã định danh giả danh thường vẫn phải được bảo vệ như dữ liệu có khả năng liên kết tới cá nhân.

### 2.1. Năm thuộc tính cần phân biệt

| Thuộc tính | Câu hỏi | Biện pháp thường dùng |
| --- | --- | --- |
| **Confidentiality** | Người không có quyền có xem được bản ghi? | RBAC/ABAC, phân quyền tenant, encryption, che trường, kiểm soát export |
| **Integrity** | Record có bị sửa mà không bị phát hiện? | WORM/append-only đúng cấu hình, HMAC/chữ ký, checkpoint độc lập |
| **Authenticity** | Có thể xác minh nguồn sinh ra bằng chứng? | Danh tính workload, mTLS, chữ ký hoặc xác thực nguồn ingest |
| **Completeness** | Có thiếu sự kiện, mất một đoạn, trùng hoặc lệch thứ tự? | Sequence/checkpoint, nguồn đối chiếu, heartbeat, giám sát ingestion |
| **Availability** | Khi điều tra có đọc được và hiểu được bản ghi cũ? | Replication, backup/restore, schema version, lưu tài liệu diễn giải, RTO truy xuất |

Mã hóa ổ đĩa chủ yếu giải quyết confidentiality; **nó không tự chứng minh một record chưa từng bị xóa**. SHA-256 thuần giúp phát hiện khác biệt so với một hash đáng tin, nhưng kẻ có thể sửa cả record lẫn hash có thể tính lại. Ngược lại, WORM giúp chặn sửa/xóa theo cơ chế lưu trữ, nhưng không xác nhận rằng nguồn đã gửi dữ liệu đúng ngay từ đầu.

## 3. Threat model và kiến trúc bảo vệ

Xác định các đối tượng có thể làm sai lệch bằng chứng:

1. **Người dùng cuối** cố gửi dữ liệu độc hại vào field được log (log injection), thăm dò quyền hoặc khiến hệ thống ngừng ghi vì log quá lớn.
2. **Ứng dụng bị xâm nhập** sở hữu credential DB hoặc collector và cố sửa, tẩy xóa dấu vết trong cùng hạ tầng.
3. **Nhân viên có quyền vận hành** có thể đọc dữ liệu riêng tư, xuất hàng loạt, thay thời hạn lưu hoặc tắt logging.
4. **Người quản lý storage/KMS** có thể thay retention, khóa mã hóa hoặc cấu hình phân quyền nếu không có tách nhiệm vụ.
5. **Lỗi vô ý** gồm mất sự kiện khi queue đầy, lệch đồng hồ, nhân bản bản ghi, xóa trước hạn, backup không khôi phục được, format cũ không đọc nổi.

Một kiến trúc tham khảo:

```text
Spring Security / domain policies
      |
      | structured event (ID, UTC, schema, minimal fields)
      v
collector / queue with authentication + TLS
      |
      +--> alert/metrics on missing events, lag, invalid schema
      |
      v
canonicalization + classification + retention policy
      |
      +--> searchable index (HOT; read scope restricted)
      |
      +--> immutable/archive store (WARM/COLD)
      |       + encrypted + retention lock + separate admin
      |       + manifest/cryptographic checkpoint
      |
      +--> audit of access/export/policy/hold/deletion
      |
      v
investigation/authorized export -> evidence package + manifest
      |
      v
policy expiry + no active hold -> verified purge + disposal evidence
```

Không một thành phần nào riêng lẻ tạo ra bảo đảm “không thể sửa”. Cần phối hợp **ít quyền, tách miền quản trị, lưu trữ bất biến theo thời hạn, dấu kiểm mật mã, giám sát ingest và kiểm thử khôi phục**. Bản thân một bản ghi JSON trong bảng SQL bình thường, kể cả bảng chỉ cho phép `INSERT` qua API, vẫn có thể bị sửa nếu cùng credential được cấp quyền `UPDATE/DELETE` hoặc có quyền quản trị DB.

## 4. Chính sách lưu giữ: phân loại trước, đặt thời hạn sau

Thời hạn lưu cần xuất phát từ **mục đích xử lý, khả năng điều tra, rủi ro, yêu cầu hợp đồng/pháp lý, nghĩa vụ bảo vệ dữ liệu và chi phí**. Không có một giá trị “90 ngày” hoặc “1 năm” đúng cho tất cả sự kiện hay mọi quốc gia. NIST SP 800-53 AU-11 để tổ chức xác định thời hạn phù hợp chính sách và nhu cầu điều tra; OWASP khuyến nghị không hủy trước thời hạn yêu cầu và không giữ quá thời hạn cần thiết.

Với mỗi lớp bản ghi, chính sách nên ghi rõ:

- **Class và mục đích**: ví dụ `AUTHENTICATION_FAILURE`, `AUTHORIZATION_DENIED`, `ROLE_CHANGED`, `AUDIT_EXPORTED`, `POLICY_CHANGED`.
- **Data owner và policy owner**: đơn vị chịu trách nhiệm mục đích lưu, người phê duyệt điều chỉnh, DPO/legal/security khi liên quan.
- **Retention clock**: tính từ `occurredAt`, `receivedAt`, thời điểm case đóng, hay thời điểm nghĩa vụ bắt đầu; quy tắc xử lý event đến muộn.
- **Hot/searchable duration** và **total retention**: thời gian truy vấn trực tiếp khác với thời gian lưu tổng cộng.
- **Trạng thái ngoại lệ**: legal hold, điều tra đang mở, tranh chấp, yêu cầu bảo toàn chứng cứ và người được phép gỡ.
- **Nơi lưu và bản sao**: index, object archive, log aggregator, backup, replica, snapshot và bản xuất ngoài hệ thống.
- **Delete/disposal**: xóa bằng cơ chế nào, được ghi nhận ở đâu, làm sao chứng minh không còn bản sao không hợp lệ.
- **Khả năng phục hồi**: thời gian khôi phục từ archive, loại định dạng/schema và khóa cần giữ để đọc lại.
- **Ngày hiệu lực và version**: thay đổi retention policy phải được xét duyệt và audit, không âm thầm áp dụng cho dữ liệu cũ.

### 4.1. Ma trận minh họa, không phải thời hạn bắt buộc

| Lớp sự kiện | Tra cứu nhanh (ví dụ) | Tổng thời gian lưu (ví dụ) | Lý do cần giữ |
| --- | --- | --- | --- |
| Denial/failed login thường xuyên | 30 ngày | 180 ngày | Phát hiện dò quyền và điều tra ngắn hạn |
| Thay đổi role/authority, admin action | 90 ngày | 365 ngày | Truy vết quyền và thay đổi chính sách |
| Export audit, thay đổi retention/hold | 90 ngày | 730 ngày | Trách nhiệm giải trình đối với chính kho audit |
| Debug log không chứa sự kiện audit | 7 ngày | 14 ngày | Hỗ trợ kỹ thuật ngắn hạn; tránh lưu quá mức |

Các số ngày trên **chỉ để luyện thiết kế**. Hệ thống thật phải thay bằng thời hạn được xác nhận cho bối cảnh pháp lý, loại dữ liệu, ngành và mục đích xử lý. Một bản ghi có thể đồng thời thuộc nhiều lớp; quy tắc ưu tiên phải minh bạch và được phê duyệt. Không dùng một file `application.yml` do developer tự sửa làm nguồn quyết định thời hạn lưu có tính pháp lý.

### 4.2. Cách tính thời hạn và dữ liệu đến muộn

Quy ước mẫu:

```text
retentionStart = occurredAt (UTC, nếu tin cậy và được policy định nghĩa)
retentionUntil = retentionStart + totalRetention
eligibleForPurge = now >= retentionUntil
                   AND legalHold = false
                   AND preservationCase = none
                   AND all required approvals/checks passed
```

Dữ liệu đến muộn đặt ra vấn đề: event xảy ra hôm trước nhưng collector nhận hôm nay. Nếu policy đếm từ `occurredAt`, không tự kéo dài thời hạn vì ingest lại; nếu clock nguồn không đáng tin, cần quy tắc fallback và lưu `receivedAt` để điều tra. Dùng thời gian UTC, schema lưu offset/epoch rõ ràng; tránh dùng ngày giờ cục bộ không kèm múi giờ trong dữ liệu chứng cứ.

Phải làm rõ “giữ 180 ngày” nghĩa là 180 ngày lịch hay sáu tháng lịch, có tính từ sự kiện hay kết thúc vụ việc. Một job TTL thông thường có thể xóa **muộn** hơn mốc vì quét bất đồng bộ; không nên quảng cáo là bảo đảm xóa chính xác theo giây. Khi cần điều kiện chặt, thiết kế SLA xóa, kiểm tra độc lập và theo dõi backlog.

### 4.3. Hot, warm/cold, archive và backup

- **Hot**: index có thể truy vấn theo actor/tenant/time/requestId; giới hạn trường, quota, phân quyền truy vấn, hạn chế full-text tìm dữ liệu nhạy cảm.
- **Warm/cold**: lưu ít tốn kém hơn; thời gian truy xuất có thể lâu hơn nhưng phải có quy trình restore và tiêu chí RTO/RPO được thử nghiệm.
- **Archive bất biến**: bản gốc đã chuẩn hóa, manifest, checksum/HMAC hoặc checkpoint, schema version và metadata key ID; giới hạn quyền xóa/thay đổi.
- **Backup/snapshot**: có chính sách retention và legal hold riêng; không thể coi xóa ở index là đã xóa mọi bản sao. Theo dõi vòng đời, khả năng restore và hủy an toàn.

Retention không đồng nghĩa với **searchability**. Khi index hot hết hạn, có thể xóa index nhanh mà bản gốc vẫn còn trong archive cho đến hạn tổng. Ngược lại, bảo quản archive hàng năm mà không còn decoder/schema/khóa thì trên thực tế không còn bằng chứng dùng được.

### 4.4. Legal hold / preservation hold

**Legal hold** hoặc **preservation hold** giữ lại tập record cần thiết cho điều tra/tranh chấp dù thời hạn bình thường đã đến. Luồng kiểm soát:

1. Nhận yêu cầu có căn cứ, xác định case ID, phạm vi record, mục đích và thẩm quyền phê duyệt.
2. Đóng băng việc xóa **trước** lần purge kế tiếp; áp dụng ở cả archive, index và bản sao được quản lý phù hợp.
3. Ghi ai yêu cầu, ai duyệt, lúc nào, tiêu chí chọn record và vị trí lưu; không đưa nội dung nhạy cảm không cần thiết vào log của hold.
4. Hạn chế và định kỳ rà soát phạm vi hold; hết nhu cầu thì có phê duyệt gỡ hold và audit hành động gỡ.
5. Sau khi gỡ, **tính lại điều kiện theo retention policy đang áp dụng** và xóa bản ghi đã hết hạn nếu không còn lý do giữ khác.

Hold không phải lý do để giữ toàn bộ dữ liệu vô thời hạn. Cũng không nên triển khai chỉ bằng cờ `legalHold=true` trong một index có thể bị xóa: phải bảo vệ cơ chế hold và storage thực thi nó.

## 5. Kiểm soát truy cập: ai được làm gì với bằng chứng?

Quyền với audit phải được coi là **quyền nhạy cảm cao**. Một người có quyền đọc toàn bộ audit có thể thấy hoạt động của nhiều người, tenant, địa chỉ mạng hoặc chi tiết điều tra. Một người có quyền xóa hoặc đổi retention có thể xóa dấu vết. Vì vậy cần chia quyền theo **hành động**, **phạm vi dữ liệu** và **mức độ nhạy cảm**, theo mặc định từ chối.

### 5.1. Ma trận quyền tham khảo

| Vai trò/identity | Ghi | Đọc/truy vấn | Export | Đổi policy/hold | Purge | Xác minh integrity |
| --- | --- | --- | --- | --- | --- | --- |
| Service producer | Gửi event mới qua collector | Không | Không | Không | Không | Không |
| Ingest service | Append theo stream được giao | Chỉ metadata cần xử lý | Không | Không | Không | Có thể kiểm tra lúc ingest |
| SOC/incident investigator | Không sửa record | Đúng case/tenant/time | Theo phê duyệt | Đề xuất hold | Không | Có |
| Auditor độc lập | Không | Chỉ phạm vi được ủy quyền, read-only | Có kiểm soát | Không | Không | Có |
| Retention policy administrator | Không | Metadata chính sách | Không mặc định | Đề nghị thay đổi | Không trực tiếp | Có thể xem báo cáo |
| Hold approver | Không | Metadata/case cần thiết | Không mặc định | Duyệt hold/release | Không trực tiếp | Có thể xem báo cáo |
| Purge automation | Không | Metadata tối thiểu | Không | Không | Chỉ record đủ điều kiện | Ghi bằng chứng hủy |
| KMS/storage administrator | Không mặc định | Không đọc business payload | Không | Không | Không mặc định | Hỗ trợ khóa/anchor theo quyền |

Đây là **mẫu thiết kế**, không phải bảng quyền cố định của Spring Security. Trong thực tế, một người có nhiều vai trò có thể phá vỡ tách nhiệm vụ; nên áp dụng chính sách chống xung đột quyền và phê duyệt hai người cho thao tác rủi ro cao.

Các ranh giới cần bảo vệ đồng thời:

- **Application/API**: JWT/session/SSO được xác thực, `SecurityFilterChain` và method authorization; kiểm soát tenant, case và field-level visibility.
- **Database/index**: account chỉ ghi cho collector, account chỉ đọc phù hợp cho query service; không cấp `UPDATE/DELETE` cho ứng dụng chính trên archive.
- **Object storage**: retention lock, chính sách bucket, versioning/immutability nếu dùng; tài khoản app không có quyền sửa retention hoặc xóa bằng chứng.
- **KMS/HSM**: quản trị key, decrypt/sign/verify tách biệt; thay khóa phải có audit và kiểm soát vòng đời.
- **SIEM/dashboard và export**: SSO/MFA, JIT access theo ticket, session ngắn, rate limit, watermark, giám sát truy vấn và export.
- **Các bản sao ngoài hệ thống**: analyst workstation, email attachment, support ticket, object export cũng là dữ liệu audit cần retention/access riêng.

**Đọc audit cũng phải tạo audit.** Nên ghi ai truy vấn/export, mục đích, phạm vi, thời điểm, số bản ghi trả về, công cụ và nơi chuyển tệp; không nhất thiết ghi lại toàn bộ nội dung query nhạy cảm hoặc kết quả. Lưu audit của chính hoạt động audit vào luồng phù hợp, tránh vòng lặp vô hạn khi sink tự đọc log nội bộ.

### 5.2. Ví dụ phân quyền trong Spring Security

Đoạn sau là **cấu hình minh họa tích hợp vào một ứng dụng Servlet có security hiện hữu**, không phải chương trình độc lập. Nó bảo vệ namespace nội bộ; các handler/controller và identity provider do hệ thống cung cấp:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain auditChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/internal/audit/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/internal/audit/**")
                .hasAuthority("AUDIT_READ")
            .requestMatchers(HttpMethod.POST, "/internal/audit/exports")
                .hasAuthority("AUDIT_EXPORT")
            .anyRequest().denyAll())
        .build();
}
```

Lưu ý quan trọng:

- `securityMatcher` chọn chain áp dụng. Một ứng dụng phải còn chain tổng quát để bảo vệ các URL ngoài `/internal/audit/**`. Nếu không có chain nào khớp, request có thể không được Spring Security bảo vệ.
- Đây chỉ là **lớp bảo vệ HTTP ban đầu**. Có `AUDIT_READ` không có nghĩa được xem mọi tenant, mọi actor và mọi case. Service/query layer phải kiểm tra phạm vi được ủy quyền và lọc trường, phân trang, giới hạn khối lượng dữ liệu.
- `AUDIT_EXPORT` là quyền tách riêng khỏi `AUDIT_READ`. Với yêu cầu export nhạy cảm, thường cần approval bổ sung, lý do, expiry, rate limit và giám sát. Đừng biến GET thành endpoint tải dữ liệu hàng loạt để vượt kiểm soát export.
- Authentication entry point, CSRF, session, CORS, TLS và mTLS cần cấu hình theo cơ chế xác thực thật. Chỉ có chain trên **chưa** cung cấp authentication; và một POST dùng cookie/session có thể cần CSRF token.
- Quyền `AUDIT_POLICY_ADMIN`, `AUDIT_HOLD_APPROVE`, `AUDIT_PURGE_EXECUTE` nếu có phải được kiểm tra độc lập và không nên nằm chung chung dưới `AUDIT_READ`. Quyền API không thay thế guard ở storage/KMS.

Ví dụ ràng buộc tại service, cũng là **snippet minh họa**:

```java
@PreAuthorize("hasAuthority('AUDIT_READ')")
public AuditPage query(AuditQuery criteria, Authentication caller) {
    authorizedScope.check(caller, criteria.tenantId(), criteria.caseId());
    queryLimits.check(criteria);
    auditOfAudit.recordSearch(caller, criteria.safeSummary());
    return auditRepository.findRestricted(criteria);
}
```

Các kiểu `AuditPage`, `AuditQuery`, `authorizedScope` và `auditRepository` là **contract ứng dụng phải tự xây dựng**. Để `@PreAuthorize` hoạt động cần bật `@EnableMethodSecurity` và gọi qua bean do Spring quản lý (proxy). Kiểm tra scope phải được áp đặt server-side trước truy vấn; không tin client tự gửi `tenantId` hay filter. Việc lọc dữ liệu/ẩn field phải diễn ra trước khi serialize response.

### 5.3. Nguyên tắc truy cập vận hành

- **Least privilege**: scope theo tenant, case, thời gian, loại sự kiện, môi trường và trường dữ liệu. Mặc định không cấp quyền cross-tenant.
- **Separation of duties**: người đổi retention không tự phê duyệt purge; người giữ key không đồng thời có quyền xóa archive; ứng dụng chính không sở hữu quyền quản trị log store.
- **MFA và JIT**: thao tác nhạy cảm cần xác thực mạnh và quyền có thời hạn/được cấp theo vụ việc.
- **Break-glass**: có lý do, giới hạn thời gian, ghi đầy đủ, cảnh báo theo thời gian gần thực và review sau khi dùng.
- **Export**: tạo file bảo vệ bằng encryption, signed URL giới hạn thời gian, checksum/manifest và kiểm soát nơi nhận; ghi lại số lượng record/byte, người duyệt và thời gian hết hạn.
- **Periodic access review**: đối chiếu danh sách người/nhóm và service account còn nhiệm vụ; thu hồi quyền sau thay đổi vai trò; kiểm tra quyền trên index, archive và backup thực tế.
- **Chống lạm dụng truy vấn**: giới hạn số record, phạm vi thời gian, số lượt export, lọc/định dạng an toàn, truy vấn được giám sát; không trả ra raw payload chứa token trong UI.

## 6. Tính toàn vẹn: “không sửa được” và “sửa sẽ bị phát hiện” khác nhau

Một pipeline audit đáng tin cần ngăn sửa trái phép **và** phát hiện dấu hiệu bị sửa. Các lớp bảo vệ bổ trợ:

| Cơ chế | Giải quyết | Giới hạn |
| --- | --- | --- |
| Quyền append-only / tài khoản chỉ ghi | Giảm khả năng sửa từ ứng dụng | Admin storage hoặc quyền vượt cấp vẫn có thể sửa |
| Object retention lock / WORM | Hạn chế thay đổi/xóa trong thời hạn khóa | Không bảo đảm nguồn gửi sự kiện đúng hoặc không mất trước ingest |
| TLS/mTLS khi truyền | Bảo vệ đường truyền, có thể xác thực sender | Không tự bảo vệ record sau khi đã lưu |
| SHA-256 lưu kèm record | Phát hiện bit flip so với checksum đáng tin | Kẻ sửa record có thể tính lại hash nếu sửa được cả hai |
| HMAC-SHA256 với key được bảo vệ | Phát hiện sửa khi đối thủ không có key | Người nắm key có thể tạo lại tag; cần tách quyền/anchor |
| Chữ ký số + key kiểm soát | Có thể xác minh nguồn ký và tính toàn vẹn | Cần quản lý khóa, rotation, xác thực certificate/trust |
| Hash chain có sequence | Liên kết record với record trước; phát hiện thay đổi/gap trong đoạn đã kiểm | Cắt cả phần đuôi có thể qua mặt nếu không có checkpoint/expected count ngoài hệ thống |
| Checkpoint/anchor được ký và lưu độc lập | Phát hiện thay đổi sau mốc và cắt đuôi | Phụ thuộc nhịp checkpoint, bảo vệ key và nơi lưu |
| Giám sát ingestion, nguồn đối chiếu | Phát hiện mất dữ liệu/stream bất thường | Không chứng minh từng sự kiện đã xảy ra nếu nguồn đã bị thao túng |

**Tamper-evident** nghĩa là một sửa đổi trái phép sẽ để lại bằng chứng nếu cơ chế kiểm tra và niềm tin vào khóa/checkpoint còn nguyên. Tránh tuyên bố “tamper-proof” hoặc “bất khả sửa” tuyệt đối khi phần lớn hệ thống còn có quản trị viên, quyền khẩn cấp, lỗi triển khai và giới hạn về ingestion.

### 6.1. Canonicalization trước khi băm/ký

Một audit record phải được chuyển thành byte theo **quy tắc xác định**: schema version, thứ tự trường, UTF-8, độ dài, format timestamp và định dạng số. Nếu hai tiến trình serialize JSON khác thứ tự key hoặc khác whitespace rồi ký trực tiếp, cùng ý nghĩa nghiệp vụ có thể tạo hash khác nhau.

Các bước khuyến nghị:

1. Kiểm tra schema, giới hạn độ dài, loại bỏ field cấm và chuẩn hóa ID/time.
2. Dùng định dạng byte canonical có version. Với JSON có thể áp dụng một canonical JSON scheme đã xác định; không dùng bất kỳ chuỗi `toString()` nào của object.
3. Ghi sequence và reference tới record trước **theo từng stream/partition được định nghĩa**.
4. Tính hash/HMAC/chữ ký với khóa lưu và cấp quyền ngoài application log.
5. Ghi record + tag + metadata key ID/storage location trong append-only/WORM store.
6. Định kỳ ký một checkpoint gồm stream ID, sequence cuối, head digest, thời điểm và schema version; gửi bản checkpoint sang miền kiểm soát độc lập.
7. Verifier đọc bản gốc, tính lại từ đầu hoặc từ checkpoint đáng tin, kiểm tra sequence/gap, key version, tag, count và anchor.

Với hệ thống nhiều instance, **không giả định có một tổng thứ tự duy nhất**. Có thể chia theo tenant/partition, gắn sequence và checkpoint cho từng stream; ghi rõ quy tắc xử lý concurrent append, retry và duplicate `eventId`.

## 7. Ví dụ Java 17 chạy độc lập: chuỗi HMAC và kiểm tra cắt đuôi

Ví dụ sau minh họa bằng chứng mật mã. Nó dùng `javax.crypto.Mac`, `HmacSHA256`, `HexFormat` và `record` của Java 17, **không cần Spring hoặc thư viện ngoài**. Dữ liệu nhỏ, một stream, một tiến trình và khóa demo hard-coded chỉ để học; hệ thống thật cần key management, storage bất biến, checkpoint ký/lưu ngoài miền quản trị, phân quyền và giám sát.

Tạo tệp **`AuditChainDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class AuditChainDemo {

    // Chỉ để demo. KHÔNG lưu khóa thực trong source hay file log.
    private static final byte[] DEMO_KEY =
            "local-example-key-not-for-production"
                    .getBytes(StandardCharsets.UTF_8);

    record Event(
            String eventId, String occurredAt, String actorRef,
            String resource, String action, String decision) {}

    record Sealed(Event event, String previousTagHex, String tagHex) {}

    public static void main(String[] args) throws Exception {
        List<Sealed> records = new ArrayList<>();
        append(records, new Event(
                "event-1", "2026-11-05T08:00:00Z",
                "actor-17", "ORDER", "READ", "DENY"));
        append(records, new Event(
                "event-2", "2026-11-05T08:00:01Z",
                "actor-18", "AUDIT", "EXPORT", "ALLOW"));

        // Mô phỏng anchor đáng tin được lưu ở nơi độc lập.
        String trustedHead = records.get(records.size() - 1).tagHex();

        System.out.println("original=" + verifyWithAnchor(records, trustedHead));

        List<Sealed> truncated = List.of(records.get(0));
        System.out.println("truncatedLocal=" + verifyChain(truncated));
        System.out.println("truncatedAnchor="
                + verifyWithAnchor(truncated, trustedHead));

        Sealed first = records.get(0);
        Event old = first.event();
        Event tampered = new Event(
                old.eventId(), old.occurredAt(), old.actorRef(),
                old.resource(), "DELETE", old.decision());
        records.set(0, new Sealed(
                tampered, first.previousTagHex(), first.tagHex()));
        System.out.println("tampered=" + verifyWithAnchor(records, trustedHead));
    }

    private static void append(List<Sealed> records, Event event)
            throws Exception {
        byte[] previous = records.isEmpty()
                ? new byte[32]
                : HexFormat.of().parseHex(
                        records.get(records.size() - 1).tagHex());
        byte[] tag = hmac(previous, event);
        records.add(new Sealed(
                event,
                HexFormat.of().formatHex(previous),
                HexFormat.of().formatHex(tag)));
    }

    private static byte[] hmac(byte[] previous, Event event)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(DEMO_KEY, "HmacSHA256"));
        mac.update(previous);
        return mac.doFinal(canonicalBytes(event));
    }

    // Dạng byte canonical tối giản, có version và length prefix.
    private static byte[] canonicalBytes(Event event) throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream output = new DataOutputStream(buffer)) {
            output.writeInt(1); // schema version
            for (String field : List.of(
                    event.eventId(), event.occurredAt(),
                    event.actorRef(), event.resource(),
                    event.action(), event.decision())) {
                byte[] utf8 = field.getBytes(StandardCharsets.UTF_8);
                output.writeInt(utf8.length);
                output.write(utf8);
            }
        }
        return buffer.toByteArray();
    }

    private static boolean verifyChain(List<Sealed> records)
            throws Exception {
        byte[] previous = new byte[32];
        for (Sealed record : records) {
            byte[] declaredPrevious;
            byte[] storedTag;
            try {
                declaredPrevious = HexFormat.of()
                        .parseHex(record.previousTagHex());
                storedTag = HexFormat.of().parseHex(record.tagHex());
            } catch (IllegalArgumentException malformedHex) {
                return false;
            }
            if (!MessageDigest.isEqual(previous, declaredPrevious)) {
                return false;
            }
            if (!MessageDigest.isEqual(
                    hmac(previous, record.event()), storedTag)) {
                return false;
            }
            previous = storedTag;
        }
        return true;
    }

    private static boolean verifyWithAnchor(
            List<Sealed> records, String trustedHead) throws Exception {
        if (records.isEmpty() || !verifyChain(records)) {
            return false;
        }
        byte[] actual = HexFormat.of().parseHex(
                records.get(records.size() - 1).tagHex());
        byte[] expected = HexFormat.of().parseHex(trustedHead);
        return MessageDigest.isEqual(actual, expected);
    }
}
```

Chạy ở thư mục chứa tệp (JDK 17+):

```bash
javac --release 17 AuditChainDemo.java
java AuditChainDemo
```

**Stdout chính xác** của chương trình, không phụ thuộc timestamp bên ngoài:

```text
original=true
truncatedLocal=true
truncatedAnchor=false
tampered=false
```

Giải thích từng kết quả:

- `original=true`: hai record và head hiện tại khớp chuỗi HMAC và anchor.
- `truncatedLocal=true`: chỉ giữ record đầu tiên vẫn tạo thành một **chuỗi nội bộ hợp lệ**. Do đó HMAC/hash chain một mình **không phát hiện cắt đuôi**.
- `truncatedAnchor=false`: head sau khi cắt không còn trùng head đã được lưu độc lập trước đó.
- `tampered=false`: đổi `READ` thành `DELETE` nhưng giữ tag cũ thì HMAC kiểm tra lại thất bại.

Trong demo, `trustedHead` chỉ là biến được giữ trong cùng tiến trình để minh họa. **Đây chưa phải một anchor độc lập**. Khi triển khai thực, checkpoint phải được ký/ghi sang hệ thống khác với quyền tách biệt, lưu timestamp/sequence/key ID và được kiểm chứng; ứng dụng bị xâm nhập không được phép sửa đồng thời record lẫn checkpoint. Ví dụ cũng không giải quyết xóa cả stream trước checkpoint đầu tiên, tạo event giả bởi người có khóa, gap do producer không gửi, hay khôi phục HMAC key đã bị xóa.

### 7.1. Lưu ý khóa, rotation và tính toàn vẹn thật

- Dùng khóa ngẫu nhiên mạnh cấp bởi KMS/HSM/secret manager, không ghi key trong repo/config log hoặc response. Hạn chế quyền sử dụng `MAC/sign` cho process cần thiết; verifier có quyền và đường trust phù hợp.
- Với HMAC chia sẻ cùng khóa, người có key có thể tạo tag khác hợp lệ. Muốn chống chính người vận hành/ứng dụng có quyền ghi, cần tách key và anchor ở miền quản trị độc lập, hoặc dùng chữ ký số mà key ký không cấp cho đối tượng có thể sửa archive.
- Ghi `keyId` và `algorithmVersion` với record/checkpoint. Rotation không được làm mất khả năng xác minh các record cũ trước khi hết retention; khóa cũ phải có vòng đời, quyền giải mã/xác minh và kế hoạch hủy phù hợp.
- Canonicalization phải có giới hạn kích thước, null handling, normalization và schema migration rõ ràng. Tránh lấy `event.toString()` hoặc raw JSON có thứ tự key không xác định làm bằng chứng.
- Nếu dùng nhiều partition, xác minh từng stream và checkpoint; cần thêm biện pháp cho **event completeness** như expected sequence, counter, heartbeat, backlog/ingestion alert.
- HMAC **không thay thế** policy retention, kiểm soát truy cập hay bảo vệ bí mật. HMAC chỉ bảo đảm tính toàn vẹn tương ứng với mô hình tin cậy của khóa.

## 8. Tích hợp với Spring Boot/Spring Security đúng trách nhiệm

**Spring Security** là nguồn các sự kiện như authentication và authorization denial. **Spring Boot Actuator** cung cấp cơ chế `AuditEvent`, `AuditEventRepository` và listener; `InMemoryAuditEventRepository` tiện cho development nhưng không nên coi là archive audit bền vững cho production. Đối với hệ thống thật, chọn nơi lưu/luồng ghi có backup, retention, phân quyền, integrity verification và khả năng khôi phục phù hợp.

Luồng gợi ý:

1. Dùng các sự kiện Security/domain phù hợp để phát hiện hoạt động cần audit; chuẩn hóa theo schema chung, không dump raw object.
2. Ghi `eventId`, `requestId`/trace ID, timestamp UTC, actor/resource/action/decision và phân loại mức nhạy cảm.
3. Đưa bản ghi vào collector được xác thực, có retry/idempotency và cơ chế phát hiện mất event; xác định yêu cầu **best effort** hay **durable audit**.
4. Quyết định retention/access ở policy service hoặc pipeline được kiểm soát; không để producer tự gửi ngày hết hạn tùy ý.
5. Ghi vào index query và archive; tạo tag/checkpoint, theo dõi ingest, gửi cảnh báo nếu không xác minh được.
6. Truy vấn/export qua API có authorization riêng; mọi hoạt động tìm kiếm/export/hold/purge được audit.
7. Khi đến hạn, purge theo policy sau khi kiểm tra hold, bảo toàn manifest/checkpoint cần thiết và đối chiếu bản sao.

Một vấn đề đặc biệt: event ở `@EventListener` thường xảy ra trong đường request; nếu listener gọi mạng hoặc lưu archive đồng bộ và sink bị lỗi, nó có thể tăng độ trễ/ảnh hưởng xử lý request. Dùng hàng đợi có cơ chế điều tiết tải và SLA rõ ràng; **không** âm thầm bỏ sự kiện quan trọng khi queue đầy. Cần quyết định fail-open/fail-closed theo nghiệp vụ và mức độ đảm bảo, đồng thời giám sát lỗi từng chặng.

**Đừng trộn “audit trail” với application debug log**. Logger `INFO` đơn giản có thể bị rotate sau vài ngày, bị tắt bởi config hoặc bị nhân viên vận hành xóa. Nếu audit yêu cầu bằng chứng đáng tin, hãy thiết kế sink, immutability, lifecycle và quyền truy xuất độc lập.

## 9. Hủy dữ liệu đúng hạn và bằng chứng hủy

Một chính sách retention hoàn chỉnh phải có cả **deletion lifecycle**. Chỉ nói “lưu 365 ngày” mà không có job xóa/giám sát dễ dẫn tới giữ vô hạn; ngược lại `DELETE FROM audit_events WHERE created_at < ...` có thể hủy chứng cứ đang được hold.

Luồng purge an toàn ở mức khái niệm:

```text
Locate expired record/partition
  |
  +-- active hold / preservation case? --> KEEP and record hold reason
  |
  +-- unknown policy / missing metadata? --> QUARANTINE for review
  |
  +-- no hold, policy valid --> authorize purge batch
                                  |
                                  +--> archive/index/replica lifecycle
                                  +--> backups/exports per documented schedule
                                  +--> record disposal evidence
                                  +--> verify/alert on incomplete deletion
```

Bằng chứng hủy nên có batch ID, tiêu chí chọn, policy version, khoảng thời gian, số object/record, kết quả, ngoại lệ, approval và kết quả xác minh. Không ghi lại payload đã bị hủy vào chính disposal log.

Nếu WORM object còn trong thời gian khóa, không hứa xóa trước khi lock hết hiệu lực; nếu yêu cầu pháp lý về xóa dữ liệu mâu thuẫn với nghĩa vụ bảo toàn chứng cứ, cần đánh giá theo luật và thiết kế data minimization/retention từ trước. **Cryptographic erasure** (hủy khóa mã hóa dữ liệu) có thể là một biện pháp trong một số kiến trúc, nhưng cần xét key granularity, replica, cache, backup, khả năng phục hồi và nghĩa vụ chứng minh; không tự coi nó là tương đương mọi yêu cầu xóa.

Khi thay retention policy từ 365 xuống 180 ngày, phải đánh giá tác động với dữ liệu đã có và các holds. Một cron nhận file policy mới rồi xóa hàng loạt trong cùng giây là rủi ro lớn; nên có dry-run, số lượng dự kiến, phê duyệt, giới hạn batch, giám sát và khả năng dừng trước commit theo quy trình được kiểm soát.

## 10. Điều tra và chain of custody

**Tình huống:** ngày 5/11, một nhân viên cho rằng quyền truy cập audit đã bị lạm dụng vào tháng trước. Một hệ thống dùng được phải chứng minh bản ghi tồn tại, thời điểm và nguồn, có thể truy xuất, nguyên vẹn và ai đã tiếp cận bằng chứng sau khi sự cố được mở.

Quy trình đề xuất:

1. **Xác định vụ việc:** case ID, khoảng thời gian UTC, actor/tenant/resource và hệ thống liên quan; lấy nguồn dữ liệu ít nhạy cảm nhất đủ điều tra.
2. **Bảo toàn:** yêu cầu và phê duyệt preservation hold khi phù hợp, ghi phạm vi, đặt ở tầng storage trước khi query/export lớn; xác minh hold được thực thi.
3. **Tìm và đối chiếu:** lấy event theo requestId/traceId, eventId, sequence, actorRef, action, policy version; đối chiếu gateway, IAM, application, KMS và object access logs khi cần.
4. **Xác minh nguyên vẹn:** đọc manifest/checkpoint đã được lưu độc lập, xác minh chữ ký/HMAC/hash chain, record count, time window, sequence và tình trạng missing/gap; không chỉ tin checksum nằm cạnh file.
5. **Xuất chứng cứ:** xuất đúng tập dữ liệu đã duyệt, tạo manifest chứa query scope, schema version, số record, hash từng file/whole package, thời điểm, công cụ, người thực hiện và chữ ký/biên nhận nếu quy trình đòi hỏi.
6. **Bàn giao:** ghi ai nhận, khi nào, mục đích và nơi cất bản sao; mã hóa gói, cấp quyền có thời hạn, theo dõi lần mở và tạo bản phân tích trên copy.
7. **Kết luận có giới hạn:** nếu không có event, phải phân biệt “không xảy ra” với “không thu thập/không còn lưu/không tìm được”; nếu checksum hợp lệ, vẫn phải kiểm tra nguồn và completeness.
8. **Đóng vụ việc:** xét gỡ hold bằng phê duyệt, áp lại retention, hủy bản xuất đúng chính sách và lưu hồ sơ chain of custody theo phân loại phù hợp.

Ví dụ manifest minh họa:

```json
{
  "evidencePackageId": "case-2026-17-export-02",
  "caseId": "case-2026-17",
  "createdAt": "2026-11-05T12:00:00Z",
  "rangeStart": "2026-10-01T00:00:00Z",
  "rangeEndExclusive": "2026-11-01T00:00:00Z",
  "recordCount": 184,
  "schemaVersion": 1,
  "files": [
    {
      "name": "audit.ndjson",
      "sha256": "value-calculated-during-export"
    }
  ],
  "checkpointReference": "independently-stored-signed-checkpoint-id"
}
```

Các giá trị `value-calculated-during-export` và checkpoint reference trong JSON là **minh họa schema**, không phải chữ ký/hash thật; không dùng chính ví dụ làm hồ sơ chứng cứ. SHA-256 trên gói giúp kiểm tra gói có đổi sau lúc tạo, còn xác thực nguồn cần chữ ký/biên nhận và quy trình bảo vệ khóa/mốc tin cậy.

## 11. Monitoring, cảnh báo và trách nhiệm vận hành

Thiết lập các tín hiệu đo lường theo chính sách, ví dụ:

| Tín hiệu | Vì sao quan trọng | Phản ứng |
| --- | --- | --- |
| Collector không nhận heartbeat/event kỳ vọng | Có thể mất tín hiệu hoặc bị tắt logging | Cảnh báo, xác minh producer/queue |
| Ingest lag, retry, dead-letter tăng | Có nguy cơ thiếu audit sau sự cố | Điều tra queue và backpressure |
| Sequence gap/duplicate eventId | Thiếu hoặc replay record | Đối chiếu nguồn, quarantine batch |
| Verify HMAC/signature/checkpoint thất bại | Có dấu hiệu tamper, lỗi key/schema hoặc dữ liệu hỏng | Cô lập bản sao, bảo toàn bằng chứng, điều tra |
| Thay retention/hold/key hoặc bucket policy | Có thể làm mất khả năng xác minh hoặc lưu giữ | Yêu cầu change approval, audit và alert |
| Query/export bất thường hoặc cross-tenant | Có nguy cơ lộ dữ liệu audit | Rate limit, điều tra quyền và case |
| Archive restore thất bại | Có log nhưng không dùng được | Khắc phục backup/key/schema, diễn tập restore |
| Purge backlog tăng hoặc xóa trước hạn | Không đáp ứng retention hoặc giữ quá mức | Dừng job lỗi, kiểm tra policy/hold |
| Disk/quota/cost tăng đột ngột | Dễ bị denial of service qua ghi log | Giới hạn input, xử lý scale, báo sự cố |

Những người chịu trách nhiệm phải được chỉ định: owner của event schema, owner retention, security operations, privacy/legal, storage/platform, KMS và incident manager. Thực hiện review định kỳ quyền đọc và các policy version. Audit được dùng làm chứng cứ chỉ hữu ích khi **quy trình theo dõi lỗi của chính audit pipeline** đã được vận hành và kiểm thử.

## 12. Ma trận kiểm thử bắt buộc trước production

| Kiểm thử | Cách kích hoạt | Kết quả cần xác minh |
| --- | --- | --- |
| Không đủ quyền đọc | User không có `AUDIT_READ` gọi query API | Bị từ chối; không rò record hoặc metadata nhạy cảm |
| Chỉ có quyền đọc | User có `AUDIT_READ` thử export | Bị chặn hoặc đi qua approval riêng, không tự tải hàng loạt |
| Sai tenant/case scope | Investigator query tenant khác | Bị chặn ở domain/query layer dù có authority tổng |
| Ingest account thử UPDATE/DELETE | Dùng credential của producer/collector | Storage từ chối sửa/xóa bản gốc |
| Record bị sửa | Sửa nội dung thử nghiệm sau khi niêm phong | Verify HMAC/signature thất bại |
| Cắt đuôi/mất segment | Xóa record cuối hoặc thiếu sequence | Checkpoint/expected count phát hiện |
| Tắt collector / queue đầy | Fault injection ở môi trường test | Alert, retry/DLQ và xử lý có kiểm soát; không âm thầm mất dữ liệu |
| Retention vừa hết | Đưa clock giả lập qua mốc | Purge theo policy, báo số bản ghi và metadata; không xóa sớm |
| Active hold | Hold record đã hết hạn trước job | Record được giữ; có evidence rằng purge đã bỏ qua |
| Gỡ hold | Approve release và chạy lại policy | Chỉ record đủ điều kiện bị xóa, hành động được audit |
| Backup cũ / archive cold | Restore record đã lưu lâu | Đọc được schema và kiểm tra tag/checkpoint |
| Key rotation | Đổi key mới cho record tiếp theo | Record cũ vẫn verify được đến khi hết retention |
| Audit query/export | Một nhân viên được phép truy xuất | Sinh audit-of-audit với actor, scope, time, outcome |
| Export/manifest | Chỉnh file export sau tạo | Checksum/biên nhận kiểm tra thất bại |
| Log injection / oversized input | Gửi newline, ký tự lạ, data lớn | Không phá format, không làm lộ secrets hoặc đầy storage |

Nên có các test cho trường hợp khôi phục sau mất kết nối dài, duplicate do retry, clock skew, policy rollback, service account bị thu hồi, and security event từ filter/controller không được publish vì lỗi cấu hình. Không thể dùng duy nhất bài test “API trả 403” để kết luận audit đã được ghi bền vững hoặc có tính toàn vẹn.

## 13. Lỗi thường gặp và cách khắc phục

1. **Chỉ lưu log trong RAM hoặc console của pod:** khởi động lại là mất; chuyển sang collector và retention-backed store, thử restore trước khi tuyên bố bền vững.
2. **Đặt một TTL chung cho mọi loại audit:** các sự kiện có rủi ro/luật/nhu cầu khác nhau; phân loại và có policy version, owner, hold rõ ràng.
3. **Nhầm thời gian index với tổng retention:** xóa index hot không xóa archive; giữ archive cũng không có nghĩa truy vấn nhanh; công bố rõ hai mốc.
4. **Chỉ có quyền `ROLE_ADMIN` là đọc/xóa toàn bộ audit:** người quản trị ứng dụng có thể tự xóa dấu vết; áp dụng least privilege, tách quyền query/export/purge và tách storage/KMS.
5. **Chỉ băm file bằng SHA-256 rồi lưu hash cùng file:** người có quyền sửa cả hai tính lại hash; dùng anchor được ký/niêm phong độc lập, khóa và quyền phù hợp.
6. **Tin hash chain phát hiện mọi xóa:** xóa phần đuôi vẫn có thể tạo chuỗi hợp lệ; xác minh head checkpoint/record count bên ngoài.
7. **Ghi dữ liệu thô để “phòng khi điều tra”:** tăng rủi ro riêng tư và mất bí mật; chọn trường tối thiểu, route template, pseudonymization và schema allowlist.
8. **Mất khóa cũ ngay sau rotation:** archive không thể verify/decrypt khi được restore; quản trị key version và giữ đúng hạn phục vụ dữ liệu.
9. **Tắt logging vì sink lỗi mà không cảnh báo:** có khoảng trống chứng cứ; có queue/retry/backpressure, alert và quy tắc xử lý lỗi đã phê duyệt.
10. **Xóa khi đến hạn nhưng quên hold, backup và export:** dễ hủy sớm hoặc giữ quá hạn; dùng lifecycle inventory và điều phối deletion/exception xuyên các bản sao.
11. **Tin raw `X-Forwarded-For` hoặc user-supplied actorId:** attacker có thể giả mạo; chỉ dùng context được xác thực và nguồn proxy đáng tin.
12. **Không audit việc đọc audit:** không truy được ai đã khai thác kho log; có audit-of-audit độc lập và cảnh báo xuất bất thường.
13. **Có archive nhưng không còn schema/documentation/decoder:** không thể giải thích chứng cứ cũ; version hóa schema và diễn tập khôi phục.
14. **Chính sách tồn tại trên wiki nhưng job không thực thi:** thiết lập kiểm thử expiry/hold, đo backlog, đối chiếu cấu hình thực tế với chính sách đã duyệt.

## 14. Bài tập thiết kế

Giả sử một hệ thống đặt hàng dùng Spring Security với ba nhóm sự kiện: `AUTHORIZATION_DENIED`, `ADMIN_ROLE_CHANGED` và `AUDIT_EXPORT_CREATED`. Đội vận hành muốn tra cứu nhanh 30 ngày, nhưng đội điều tra có thể cần record cũ hơn; một số vụ việc bị hold; auditor chỉ được xem dữ liệu của những case được giao.

Hãy tự lập:

1. **Retention matrix** cho ba lớp, bao gồm owner, retention start, hot/archive duration, legal hold rule, archive restore target và policy version. Mọi số ngày phải ghi rõ là giả định bài tập.
2. **Access matrix** cho producer, SOC, auditor, retention admin, hold approver, purge automation và KMS admin. Cho biết ai được xem, export, chỉnh policy, hủy và ký checkpoint.
3. **Integrity plan**: chọn canonical format, sequence scope, HMAC hoặc chữ ký, checkpoint độc lập, cách phát hiện missing/truncated stream và xử lý key rotation.
4. **Incident workflow**: người dùng phát hiện bản xuất audit trái phép. Chỉ rõ request/trace ID, audit-of-audit, hold, cách xác minh checksum/chữ ký, chain of custody và gỡ hold.
5. **Validation**: ít nhất một test truy cập sai tenant, một test xóa khi đang hold, một test cắt đuôi và một test archive restore.

Câu hỏi tự kiểm tra: nếu một file NDJSON và checksum SHA-256 của nó nằm cùng một bucket mà cùng tài khoản admin có thể sửa cả hai, bạn đã có integrity đáng tin chưa? **Chưa**: đối thủ có thể sửa file rồi tính lại checksum. Cần giới hạn quyền, storage immutability hoặc dấu kiểm/anchor ở miền tin cậy khác, đồng thời kiểm tra event completeness và quy trình ingest.

## 15. Tài liệu chính thức và hướng dẫn tham khảo

- OWASP, [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — trường dữ liệu nên loại bỏ, giới hạn truy cập, bảo vệ log khi truyền/lưu, kiểm tra tamper, disposal và kiểm thử lỗi logging.
- NIST, [SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final) — tổ chức hạ tầng và quy trình quản trị log xuyên hệ thống.
- NIST SP 800-53 Rev. 5, **AU-9 Protection of Audit Information**, **AU-11 Audit Record Retention**, **AU-12 Audit Record Generation** — các nhóm kiểm soát bảo vệ audit, xác định thời hạn theo tổ chức và khả năng sinh record; đối chiếu bản chuẩn hiện hành khi đánh giá tuân thủ.
- Spring Boot, [Auditing](https://docs.spring.io/spring-boot/3.5/reference/actuator/auditing.html) — `AuditEventRepository`, audit listener và giới hạn kho in-memory.
- Spring Security, [Authorization Events](https://docs.spring.io/spring-security/reference/servlet/authorization/events.html) — nơi nhận sự kiện authorization để đưa vào pipeline audit đã kiểm soát.
- OWASP, [Developer Guide: Logging and Monitoring](https://devguide.owasp.org/en/04-design/02-web-app-checklist/09-logging-monitoring/) — logging security, phân quyền và bảo vệ integrity.

**Ghi nhớ:** Audit đáng tin đòi hỏi **giữ đủ lâu nhưng không quá hạn**, **chỉ đúng người được truy cập đúng phạm vi**, và **có thể chứng minh tính nguyên vẹn cũng như phát hiện thiếu dữ liệu**. Ba yêu cầu này phải được thực thi bởi quyền, lưu trữ, khóa, quy trình phê duyệt và kiểm thử — không chỉ bởi một lời gọi `logger.info(...)`.