# 32.10. Backup, retention và bảo vệ dữ liệu authorized client

Một ứng dụng **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client** có thể đã cấu hình HTTPS, PKCE, `state` và kiểm tra chữ ký ID Token chính xác nhưng vẫn gặp sự cố bảo mật nghiêm trọng nếu **access token** hoặc **refresh token** nằm trong database, bản sao lưu, log hoặc vùng lưu trữ thiếu kiểm soát.

Trong Spring Security, một `OAuth2AuthorizedClient` liên kết **client registration**, **principal** và các **OAuth2 tokens** đã được cấp. Nếu ứng dụng giữ những đối tượng này giữa các HTTP requests hoặc qua các lần khởi động, chúng phải được quản lý như **tài sản chứa credential**, không phải một bảng cache thông thường.

Bài học thuộc chương **32. Triển khai và vận hành**, tập trung vào ba năng lực:

1. **Backup và restore:** dữ liệu authorized client có cần sao lưu không, sao lưu cái gì, ở đâu, mã hóa thế nào, khôi phục và kiểm chứng ra sao?
2. **Retention và deletion:** giữ token đến khi nào; xử lý user logout, revoke consent, tenant offboarding, token hết hạn, dữ liệu trong backup và yêu cầu xóa dữ liệu ra sao?
3. **Bảo vệ khi lưu trữ và vận hành:** mã hóa, phân quyền, quản lý khóa, cách ly người dùng/tenant, tránh token leakage, xử lý refresh token rotation và sự cố sau restore.

Ví dụ sử dụng **Spring Boot 3.x, Spring Security 6.x (đối chiếu API 6.5), Java 17+ và PostgreSQL** khi cần giải thích lưu trữ bền vững. Cấu hình và SQL minh họa không phải một hệ thống mã hóa hoặc chính sách lưu giữ hoàn chỉnh có thể dùng nguyên xi trong production.

> **Thông điệp quan trọng:** **Khôi phục thành công một hàng trong database không đồng nghĩa khôi phục thành công phiên OAuth2.** Một refresh token trong backup có thể đã bị thay thế, thu hồi hoặc hết hạn tại Authorization Server. Hệ thống phải **fail closed**, xóa credential không còn hợp lệ và bắt đầu một authorization flow mới khi cần; không được ép Authorization Server chấp nhận token cũ.

---

## 1. Phân biệt Authorized Client với các đối tượng khác

Các khái niệm tên gần giống nhau nhưng có vòng đời và rủi ro khác nhau.

| Thành phần | Chứa gì? | Có chứa credential có thể dùng để gọi API? | Vòng đời điển hình |
| --- | --- | --- | --- |
| `ClientRegistration` | `registrationId`, `clientId`, provider endpoints, scope, grant và có thể `clientSecret` | **Có thể chứa client secret**, nhưng không phải access token của user | Configuration/secrets lifecycle |
| **`OAuth2AuthorizedClient`** | Registration + principal name + access token + optional refresh token | **Có** | Đến khi hết hiệu lực, revoke, xóa hoặc reauthorize |
| `OAuth2AuthorizationRequest` | `state`, redirect URI, PKCE verifier, OIDC nonce context | Chứa dữ liệu nhạy cảm của giao dịch login, không phải authorized-client token cache | Authorization redirect/callback ngắn hạn |
| `SecurityContext` | `Authentication`, principal và authorities | Có thể tham chiếu identity nhưng không mặc nhiên là authorized client token store | HTTP/session lifetime |
| `OAuth2AuthorizedClientService` | API lưu/tải/xóa authorized client ở application level | Quản lý dữ liệu chứa tokens | Theo storage implementation |
| `OAuth2AuthorizedClientRepository` | API lưu/tải/xóa authorized client giữa các web requests | Có thể liên quan session/service persistence | Theo HTTP/session |
| Authorization Server | Token issuance, consent, grant status, revocation | Có | Theo chính sách của AS |

Trong Spring Security, `OAuth2AuthorizedClient` chứa ít nhất:

```text
OAuth2AuthorizedClient
  clientRegistration
    registrationId = company-login
    clientId = portal-client
    provider/issuer = https://id.example.test/...
  principalName = principal-key-123
  accessToken
    tokenValue = <secret>
    tokenType = Bearer
    issuedAt / expiresAt
    scopes = [profile.read]
  refreshToken (optional)
    tokenValue = <high-value-secret>
    issuedAt
```

**Không in đối tượng này bằng `toString()`, không serialise toàn bộ thành JSON response và không lưu tùy tiện vào audit events.** Dữ liệu token trong object là bí mật dù nó mang tên “cache”.

### 1.1. Authorized Client không phải ClientRegistration

Một `ClientRegistration` có thể được tạo lại từ cấu hình và secret manager. `OAuth2AuthorizedClient` chứa token **đã được AS cấp** cho một registration/principal cụ thể.

Nếu chỉ backup bảng authorized clients nhưng mất `ClientRegistration` tương ứng:
- App có thể không nhận diện được registration ID;
- Token endpoint/issuer/client ID có thể đã thay;
- Cache record không còn phù hợp với cấu hình hiện tại.

Ngược lại, backup cấu hình mà bỏ authorized clients có thể khiến user cần login/consent lại, nhưng không nhất thiết gây mất dữ liệu nghiệp vụ. Điều này mở ra lựa chọn **không backup tokens** trong một số kiến trúc.

### 1.2. Authorized Client không phải Authorization Request

`OAuth2AuthorizationRequest` được lưu **trong lúc chờ callback**; nó chứa state/PKCE/nonce context. Mất request này dẫn đến callback correlation failure, không phải hỏng authorized-client storage.

Đừng áp dụng retention nhiều tháng cho `OAuth2AuthorizationRequest`. Giao dịch redirect cần TTL ngắn và one-time consumption.

### 1.3. Một record có thể đại diện user hoặc service account

| Grant | Principal của authorized client | Token được cấp cho ai? |
| --- | --- | --- |
| `authorization_code` | Thường là user principal | Quyền được user/AS ủy quyền cho client |
| `client_credentials` | Nên dùng service principal name ổn định | Quyền của ứng dụng/service identity |
| `refresh_token` | Gắn authorized client đã được cấp | Làm mới token theo grant/policy cũ |

Do đó, chính sách backup/retention phải phân biệt **user-delegated tokens** và **machine-to-machine tokens**. Một token của service có thể xin lại tự động; token của user có thể cần tương tác và consent mới.

---

## 2. Vì sao dữ liệu authorized client đặc biệt nhạy cảm?

### 2.1. Access token là credential có thể dùng ngay

Với Bearer token, bất kỳ ai sở hữu token còn hợp lệ có thể thử dùng tại Resource Server đúng audience/scope. Bảo vệ bởi TLS khi truyền không giúp nếu token đã bị lộ từ database backup.

### 2.2. Refresh token có thể mang rủi ro kéo dài

Refresh token cho phép client xin access token mới, thường có vòng đời dài hơn access token. Tùy AS, refresh token có:
- Expiration tuyệt đối;
- Inactivity timeout;
- Rotation mỗi lần sử dụng;
- Reuse detection;
- Ràng buộc client/thiết bị/cert;
- Revocation bởi user hoặc administrator.

Đặc biệt, **backup chứa refresh token có thể trở thành một bản sao credential có khả năng dùng lại**, ngay cả khi database chính đã được bảo vệ hoặc đã xóa record.

### 2.3. Principal name có thể là dữ liệu cá nhân

`principalName` có thể là:
- OIDC `sub`;
- Username nội bộ;
- Email nếu hệ thống cấu hình như vậy;
- Service account ID.

Email và identifier dùng để liên hệ với user vẫn có thể là dữ liệu cá nhân. Bảng có thể tiết lộ **nhà cung cấp nào được kết nối với người nào** ngay cả khi token value đã mã hóa.

### 2.4. Token có thể tiết lộ thông tin qua nội dung

Một JWT access token thường chứa `iss`, `sub`, `aud`, `scope`, expiry và có thể các claims nghiệp vụ. JWT là **Base64URL-encoded**, không phải mã hóa bảo mật mặc định. Bản backup chứa JWT plaintext cũng có thể tiết lộ claims.

### 2.5. Tài sản nhạy cảm không chỉ nằm trong cột token

Dữ liệu có thể lan tới:
- Database snapshots;
- WAL/binlog và replication;
- Redis persistence files;
- Object storage backups;
- Cloud backup vault;
- Traces/APM/heap dumps;
- Debug HTTP logging;
- Error reports, crash dumps;
- Support tickets;
- Developer database exports;
- CI artifacts;
- Search indexes;
- Local laptop copies.

Chỉ bật mã hóa một bảng không bảo vệ được những bản sao ở các tầng khác.

---

## 3. Threat model: ai có thể tiếp cận những dữ liệu này?

| Tác nhân/tình huống | Mục tiêu | Lớp phòng thủ |
| --- | --- | --- |
| Database read-only account bị lộ | Đọc access/refresh tokens | Least privilege, token field encryption, audit |
| Backup object bị chia sẻ nhầm | Tải snapshot chứa credentials | Isolated backup IAM, SSE, retention, access logs |
| KMS key bị đánh cắp | Giải mã snapshots hoặc ciphertext | Key access boundaries, rotation, per-scope keys |
| Application pod bị chiếm quyền | Đọc tokens đang dùng | Workload identity, containment, minimal egress |
| Dev xuất production DB sang staging | Làm lộ token tại môi trường yếu hơn | Không copy live tokens; sanitization |
| Nhân viên support in record | Dùng debug tool xem raw tokens | RBAC, redaction, break-glass, approvals |
| Backup restore từ ngày trước | Dùng refresh token đã rotate | Freeze/reconcile, invalid_grant handling |
| Tenant A truy vấn token tenant B | Cross-tenant credential access | Strong tenant key + repository authorization |
| Concurrent refresh từ hai replicas | Dùng cùng refresh token/rotation race | Locking/CAS, versioning, idempotent strategy |
| User revoke consent | Client vẫn lưu token cũ | Local deletion + AS revocation when possible |
| Xóa dữ liệu nhưng snapshot vẫn còn | Recovery đưa token đã xóa trở lại | Deletion ledger/tombstone replay, backup expiry |
| Credential rotation | Restore record liên kết client secret cũ | Secret/key version lifecycle |

**Nguyên tắc:** bảo vệ dữ liệu authorized client cần cả **confidentiality**, **integrity**, **availability** và **deletion correctness**. Một cơ chế mã hóa chỉ giải quyết một phần.

---

## 4. Những lựa chọn lưu trữ trong Spring Security

### 4.1. OAuth2AuthorizedClientService

Service-level API:

```java
public interface OAuth2AuthorizedClientService {
    <T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
        String clientRegistrationId, String principalName);

    void saveAuthorizedClient(
        OAuth2AuthorizedClient authorizedClient,
        Authentication principal);

    void removeAuthorizedClient(
        String clientRegistrationId, String principalName);
}
```

Đây là chữ ký **rút gọn để giải thích**, không phải source copy nguyên văn của một phiên bản nhất định. Nó thể hiện đủ ba hành vi: **load, save, remove**.

Các implementations thường gặp:

- **`InMemoryOAuth2AuthorizedClientService`:** lưu trong tiến trình, dễ cho demo/test, mất dữ liệu khi restart.
- **`JdbcOAuth2AuthorizedClientService`:** lưu trong relational database qua JDBC với schema Spring Security.
- **Custom OAuth2AuthorizedClientService:** dùng storage riêng và/hoặc mã hóa cấp ứng dụng; phải bảo toàn contract.

### 4.2. OAuth2AuthorizedClientRepository

`OAuth2AuthorizedClientRepository` xử lý authorized client giữa các **Servlet web requests**. Implementation phổ biến như `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` có thể delegate đến `OAuth2AuthorizedClientService` cho authenticated principal và sử dụng session-level repository cho một số trường hợp anonymous.

**Đừng kết luận “token chỉ sống trong HttpSession” hay “toàn bộ token nằm ở JDBC” mà không xem repository/service wiring của chính ứng dụng.**

### 4.3. DefaultOAuth2AuthorizedClientManager và service manager

| Bối cảnh | Manager phù hợp |
| --- | --- |
| Servlet HTTP request | `DefaultOAuth2AuthorizedClientManager` với `OAuth2AuthorizedClientRepository` |
| Scheduled/background/service-tier code | `AuthorizedClientServiceOAuth2AuthorizedClientManager` với `OAuth2AuthorizedClientService` |
| Reactive WebFlux HTTP | `DefaultReactiveOAuth2AuthorizedClientManager` |
| Reactive background/service tier | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |

Success/failure handlers của manager có thể lưu hoặc xóa authorized clients theo kết quả token issuance/refresh. **Cần hiểu behavior này trước khi thiết kế backup hoặc restore**, vì một `invalid_grant` có thể khiến bản lưu hiện tại bị xóa.

### 4.4. Không mặc định chia sẻ token cache giữa các instances

`InMemoryOAuth2AuthorizedClientService` trong pod A không chia sẻ token với pod B. Nếu muốn authorized clients sống sau restart/failover, phải dùng shared persistence hoặc một chiến lược reauthorization phù hợp.

**Shared database không tự giải quyết concurrent refresh token rotation.** Nó chỉ làm các bản ghi nhìn thấy được; tính atomicity của updates vẫn phải được thiết kế.

---

## 5. Quyết định đầu tiên: có cần backup token values không?

Một lỗi kiến trúc phổ biến là **backup mọi bảng theo thói quen** rồi mới tìm cách bảo vệ tokens. Hãy đặt câu hỏi trước: **Nếu mất toàn bộ authorized-client cache, hệ thống có thể phục hồi bằng reauthorization không?**

### 5.1. Lựa chọn A — Không backup token values

Phù hợp khi:
- `client_credentials` có thể tự xin token mới;
- User có thể login/consent lại với chi phí chấp nhận được;
- Mất cached tokens không làm mất dữ liệu nghiệp vụ không thể tái tạo;
- Mục tiêu giảm lượng credentials trong backups ưu tiên hơn seamless recovery.

```text
Database loss
    -> authorized-client cache trống
    -> machine client xin token mới
    -> browser user đăng nhập/ủy quyền lại khi cần
    -> dữ liệu nghiệp vụ trong storage riêng vẫn được phục hồi
```

Ưu điểm: giảm bề mặt exposure trong snapshots và tránh restore refresh tokens cũ.

Nhược điểm:
- Người dùng có thể cần login/consent lại;
- AS có thể chịu tải tăng sau disaster recovery;
- Các background workflows cần phương án warm-up/retry;
- Tình huống OP/AS không khả dụng trong lúc khôi phục có thể kéo dài downtime.

**Nếu chọn bỏ token khỏi backup**, phải bảo đảm backup/export process thật sự loại chúng và không vô tình chứa tokens ở WAL, replica snapshots hoặc một bảng khác.

### 5.2. Lựa chọn B — Backup encrypted authorized clients

Phù hợp khi:
- Reauthorization của nhiều user gây gián đoạn lớn;
- Có các integration cần giữ refresh tokens trong khoảng thời gian được phép;
- Có cơ chế key management và restore kiểm soát được;
- Đã đánh giá risk của stale/rotated/revoked tokens.

```text
Active DB --encrypted backup--> Isolated backup vault
      |                                 |
      |                                 v
      |                           Controlled restore
      |                                 |
      v                                 v
App keeps using tokens              Reconcile validity
                                    / purge stale entries
                                       |
                                       v
                                 Controlled resume
```

**Lưu ý:** backup thành công không có nghĩa restored token dùng được. Refresh token rotation làm restore từ bản snapshot cũ có thể **nguy hiểm hơn việc để cache trống**.

### 5.3. Lựa chọn C — Hybrid

Ví dụ:
- Không backup machine access tokens;
- Backup encrypted user-delegated refresh tokens nếu cần;
- Backup metadata `registrationId` và pseudonymous principal keys;
- Tách lifecycle/deletion ledger khỏi token table;
- Xóa token cũ tại restore nếu đã revoke/expired.

Một kiến trúc hybrid cần **định nghĩa rõ authoritative data**. Không để restore của bảng token ghi đè “đã thu hồi quyền” trong hệ thống nghiệp vụ.

---

## 6. Lập chính sách backup với RPO và RTO

**RPO (Recovery Point Objective)** là mức mất dữ liệu theo thời gian có thể chấp nhận. **RTO (Recovery Time Objective)** là thời gian cần để khôi phục dịch vụ.

Với authorized-client tokens, RPO không nên sao chép máy móc từ bảng đơn hàng hoặc giao dịch thanh toán.

| Loại dữ liệu | Ví dụ RPO/RTO cần cân nhắc | Lý do |
| --- | --- | --- |
| Đơn hàng/giao dịch nghiệp vụ | RPO rất thấp | Mất dữ liệu không thể tái tạo |
| Machine access-token cache | Có thể chấp nhận cache mất toàn bộ | Token xin lại bằng client_credentials |
| User authorized-client records | Tùy UX, tần suất re-consent và AS | Mất record có thể buộc reauthorize |
| Revocation/deletion ledger | RPO rất thấp hoặc durable event log | Không được “hồi sinh” credential đã xóa |
| Encryption key metadata | Cần nhất quán với backups được giữ | Mất key khiến ciphertext không thể phục hồi |
| Audit sự kiện truy cập token | Theo security/compliance policy | Điều tra sự cố và chứng minh deletion |

**Ví dụ minh họa**, không phải giá trị bắt buộc:
- Application critical data: RPO vài phút;
- Authorized-client cache: RPO nhiều giờ hoặc chủ đích không restore;
- Revocation/delete events: phải được replay tới mọi restore point;
- RTO token service: đủ để retry/reauthorize mà không làm nghẽn AS.

Không đánh giá thành công backup chỉ bằng “job chạy mỗi 24 giờ”. Cần kiểm tra **restore có dùng được, có đúng key version và có không làm sống lại dữ liệu đã xóa**.

### 6.1. Full backup, incremental và PITR

Với database:
- **Full snapshot:** bản chụp định kỳ;
- **Incremental/differential:** thay đổi kể từ mốc thích hợp;
- **WAL/PITR:** log phục hồi theo thời điểm;
- **Replica:** phục vụ availability, **không phải backup độc lập** khi lỗi/xóa dữ liệu bị nhân bản.

Tất cả đều có thể chứa plaintext token nếu tầng storage không được mã hóa hoặc dữ liệu bị export dạng rõ.

### 6.2. Isolation của backup

Backup nên ở security boundary khác:
- Credentials/roles khác primary app;
- Tài khoản ứng dụng không có quyền xóa/đọc tùy ý backup vault;
- Encryption keys và IAM được phân quyền theo nguyên tắc least privilege;
- Object versioning/immutability khi thích hợp;
- Access logging và alert tải bulk;
- Không copy backup production sang laptop cá nhân hoặc staging không được kiểm soát.

### 6.3. Kiểm tra backup integrity

Ngoài encryption, cần cơ chế integrity:
- Checksum/hashes của artifacts;
- Authenticated encryption/signatures cho data layer;
- Immutable manifest của snapshot/LSN/time;
- Controlled restore rehearsal.

**Checksum thuần không xác thực nguồn hoặc ngăn attacker thay dữ liệu rồi tính checksum mới.** Với threat model bị sửa backup, cần authenticated integrity và permissions thích hợp.

---

## 7. Retention: giữ cái gì trong bao lâu?

Không có một con số áp dụng cho mọi dự án hoặc mọi quốc gia. Phải căn cứ:
- AS token lifetime và grant policy;
- User consent/revocation;
- Nhu cầu nghiệp vụ;
- Threat model và sensitivity;
- Bảo mật/ngành nghề;
- Nghĩa vụ pháp lý/quy định áp dụng;
- Backup schedule;
- SLA và chi phí vận hành.

### 7.1. Ma trận retention đề xuất để thảo luận

| Dữ liệu | Khi nào cần giữ? | Sự kiện phải xóa/thu hồi | Ghi chú |
| --- | --- | --- | --- |
| Active access token | Khi authorized client còn được sử dụng | Grant bị revoke, user unlink, cache invalidation | Access token expiresAt không bảo đảm refresh token hết hạn |
| Active refresh token | Khi cần tiếp tục delegated authorization và còn được phép | Logout theo policy, unlink, consent revoke, inactivity, tenant offboard | Giá trị nhạy cảm cao |
| Machine client access token | Khi chưa hết hạn, tiết kiệm token requests | Service decommission, credential revoke, policy change | Thường có thể tái tạo |
| Expired access token **không có refresh token** | Có thể xóa sớm sau khi hết hạn/buffer | TTL cleanup | Kiểm tra usage/race trước khi xóa |
| Authorized client có refresh token | Cho đến khi không còn được phép/không còn cần | Revocation/expiry/inactivity policy | Không dựa chỉ vào access token expiry |
| Pending authorization request | Chờ callback ngắn hạn | Callback complete/timeout/error | Không được retention như authorized-client record |
| Access audit event | Theo security/incident policy | Hết audit retention | Không ghi token values |
| Backup chứa token data | Theo disaster-recovery policy cụ thể | Backup retention expiry, security incident | Có thể cần crypto-erasure |
| Key versions | Trong khi còn ciphertext/backup cần decrypt | Khi không còn dữ liệu hợp lệ phụ thuộc | Không xóa key trước nếu vẫn phải restore |
| Revocation/deletion tombstones | Đủ lâu để áp dụng cho mọi restore point | Sau khi không backup nào có thể hồi sinh dữ liệu | Nên lưu riêng, không chứa raw token |

**Các mốc 7/30/90 ngày trong một chính sách cụ thể chỉ có ý nghĩa khi được phê duyệt**. Đừng coi thời gian trên là default của Spring Security hoặc nghĩa vụ pháp lý đã được xác nhận.

### 7.2. Access token expiresAt không phải retention của record

Một authorized client có thể chứa:

```text
access_token.expires_at = 2026-11-16T10:00Z
refresh_token            = still valid until revoked/inactive timeout
```

Nếu cleanup job xóa row ngay 10:00Z chỉ vì access token expired, ứng dụng mất refresh token hợp lệ, khiến user phải re-consent không cần thiết.

Ngược lại, nếu không có refresh token và access token đã expired, giữ mãi record thường không có lợi ích vận hành.

### 7.3. Refresh token không phải lúc nào có expiresAt

Trong model Spring Security `OAuth2RefreshToken` có `issuedAt` và có thể có thông tin khác tùy implementation/API, nhưng schema JDBC mặc định **không lưu một `refresh_token_expires_at` rõ ràng**.

Đừng tự tính refresh token expiry bằng:
- `access_token_expires_at`;
- `created_at + 30 days` mà không có AS policy;
- JWT `exp` suy diễn nếu refresh token là opaque.

Nên có **lifecycle metadata riêng** nếu ứng dụng phải thi hành inactivity/retention policy chính xác.

### 7.4. Xóa local storage khác với revoke tại AS

`removeAuthorizedClient(...)` chỉ xóa bản ghi **ở phía client**. Nó không tự động:
- Revoke access token đã cấp;
- Revoke refresh token trên AS;
- Xóa SSO session của OP;
- Kết thúc mọi browser sessions;
- Xóa các bản sao trong backup.

Nếu policy yêu cầu thu hồi grant, cần tích hợp AS **token revocation endpoint (RFC 7009)** khi hỗ trợ, xử lý client authentication và kết quả/timeout phù hợp.

---

## 8. Cấu hình JDBC persistence cho OAuth2AuthorizedClientService

Spring Security 6.5 cung cấp `JdbcOAuth2AuthorizedClientService` sử dụng `JdbcOperations`.

### 8.1. Dependencies

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Spring Boot BOM thường quản lý version cho các dependencies. Bài này không chạy build hoặc thay đổi build file dự án.

### 8.2. JDBC schema gốc của Spring Security

Schema tham khảo của Spring Security:

```sql
CREATE TABLE oauth2_authorized_client (
    client_registration_id varchar(100) NOT NULL,
    principal_name varchar(200) NOT NULL,
    access_token_type varchar(100) NOT NULL,
    access_token_value blob NOT NULL,
    access_token_issued_at timestamp NOT NULL,
    access_token_expires_at timestamp NOT NULL,
    access_token_scopes varchar(1000) DEFAULT NULL,
    refresh_token_value blob DEFAULT NULL,
    refresh_token_issued_at timestamp DEFAULT NULL,
    created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (client_registration_id, principal_name)
);
```

Đây là **schema tham khảo dạng chung**; `BLOB` và timestamp types cần điều chỉnh theo database dialect. Với PostgreSQL, binary field thường dùng `BYTEA` và timestamp cần có policy timezone nhất quán.

**Không tự thêm `tenant_id` hoặc thay primary key của bảng mặc định rồi giả định `JdbcOAuth2AuthorizedClientService` tự đọc/ghi các cột mới.** Class này có SQL queries và row/parameter mappers theo schema của nó. Nếu thiết kế schema khác, cần custom persistence/mapper cùng migration rõ.

### 8.3. Tạo bean JDBC service

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
class AuthorizedClientStorageConfiguration {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            JdbcOperations jdbc,
            ClientRegistrationRepository registrations) {

        return new JdbcOAuth2AuthorizedClientService(
            jdbc, registrations);
    }
}
```

Cần:
- Chạy migration tạo bảng theo đúng schema;
- Xác nhận database user của ứng dụng có quyền tối thiểu;
- Xác nhận Spring Boot chọn bean này thay vì in-memory;
- Có TLS/authentication của kết nối DB;
- Thử save/load/remove bằng synthetic tokens trong môi trường test.

### 8.4. Ví dụ application.yml — không chứa secrets thật

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal.example.test:5432/portal
    username: portal_oauth_client
    password: ${DB_PASSWORD}

  security:
    oauth2:
      client:
        registration:
          reports-machine:
            provider: company-as
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: [reports.read]
        provider:
          company-as:
            token-uri: https://auth.example.test/oauth2/token
```

`JdbcOAuth2AuthorizedClientService` không tự sinh schema trong production chỉ vì có bean. Dùng Flyway/Liquibase hoặc migration được quản lý. Không lưu `DB_PASSWORD` và `REPORTS_CLIENT_SECRET` trong git plaintext.

### 8.5. Mặc định JDBC có tự mã hóa token values không?

**Không được mặc định rằng có application-level encryption.** Schema dùng cột binary để lưu token bytes; BLOB/BYTEA không có nghĩa ciphertext. Database storage encryption/TDE và backup encryption là những **lớp khác nhau**.

Nếu threat model yêu cầu người có quyền SELECT table không được thấy token value, bạn cần **mã hóa token ở mức ứng dụng** hoặc một cơ chế tương đương được review.

---

## 9. Mã hóa at rest: bảo vệ ba lớp khác nhau

| Lớp | Bảo vệ trước | Không bảo vệ đủ trước |
| --- | --- | --- |
| Disk/volume encryption | Ổ đĩa snapshot vật lý bị lấy | DBA/SQL role đọc cột plaintext |
| Database TDE/storage encryption | File dữ liệu/physical backups tùy hệ thống | Ứng dụng hoặc tài khoản DB có quyền SELECT |
| Backup object encryption | Backup object bị lấy khi không có key | Tài khoản backup cùng có quyền decrypt |
| **Application-level token encryption** | SQL reader/snapshot không có application key | App pod bị chiếm cả data lẫn key |
| TLS DB/HTTP | Eavesdropping đường truyền | Compromise endpoint hoặc backup |
| IAM/least privilege | Truy cập trái phép theo role | Key/token lộ từ log hoặc app bug |

**Lớp phòng thủ cần chồng lên nhau.** Application-level encryption không thay backup IAM; backup encryption không thay access control trên bảng active.

### 9.1. Envelope encryption là gì?

Thường dùng:
1. Tạo hoặc lấy **Data Encryption Key (DEK)**.
2. Mã hóa token value bằng AEAD như **AES-GCM** (hoặc thuật toán tương đương đã review).
3. Mã hóa/wrap DEK bởi **Key Encryption Key (KEK)** quản lý trong KMS/HSM.
4. Lưu ciphertext, authentication tag, nonce/IV, key version hoặc wrapped DEK.
5. Khi load, app được ủy quyền sử dụng KMS/key policy để giải mã; token plaintext chỉ tồn tại trong vùng nhớ cần thiết.

```text
Token plaintext
       |
       v
AEAD encryption with DEK + unique nonce + AAD
       |
       v
token_ciphertext + nonce + key_version / wrapped_DEK
       |
       v
Database / encrypted backups

Key lifecycle:
  KMS KEK ----wrap/unwrap----> DEK
       |
       +-- policies, audit, rotation, disable/destroy
```

### 9.2. Vì sao cần authenticated encryption?

Mã hóa không chỉ để che token. Nếu attacker sửa ciphertext, hệ thống phải **phát hiện tampering**, thay vì đưa bytes sai/không xác thực vào security-critical flow.

Với AES-GCM:
- Nonce/IV phải unique theo key; không reuse;
- Authentication tag phải được xác minh;
- Dùng CSPRNG;
- Không tự phát minh cryptographic format;
- Không lưu encryption key trong chính bảng có ciphertext;
- Có định dạng versioned để nâng cấp thuật toán/keys.

**Không dùng Base64, hashing hoặc Java serialization làm “mã hóa token”.** Base64 có thể giải mã; hash một chiều không thể phục hồi token để gọi API.

### 9.3. Associated Authenticated Data (AAD)

AAD ràng buộc ciphertext với metadata đáng tin, ví dụ:

```text
AAD = version=1
    | registrationId=company-login
    | principalKey=principal-key-123
    | tokenKind=refresh
    | tenantId=tenant-a
```

Nếu attacker copy ciphertext của Tenant A sang row của Tenant B, decryption phải thất bại do AAD không khớp.

Lưu ý:
- AAD phải được canonicalize nhất quán;
- Không phụ thuộc raw email có thể đổi;
- Tenant/issuer boundary phải có trong security design;
- Nếu principal key đổi khi migration, phải có kế hoạch re-encrypt.

### 9.4. Phân biệt token types trong encryption

Một row có thể chứa access token và refresh token. Không dùng lại cùng **AEAD nonce** cho hai giá trị dưới cùng key; có thể tạo nonce riêng cho từng encryption hoặc encrypt một envelope có cấu trúc rõ ràng.

Một định dạng metadata minh họa:

```json
{
  "format_version": 1,
  "key_version": "oauth-token-key-v4",
  "access_token_ciphertext": "<binary/base64-encoded-ciphertext>",
  "access_token_nonce": "<unique-random-nonce>",
  "refresh_token_ciphertext": "<binary/base64-encoded-ciphertext>",
  "refresh_token_nonce": "<another-unique-random-nonce>"
}
```

Các chuỗi trên là placeholder, không phải giá trị mã hóa thật.

### 9.5. Key separation theo môi trường

- Không dùng cùng DEK/KEK cho production và staging;
- Không phục hồi production token ciphertext vào staging rồi cấp staging KMS key để decrypt;
- Giới hạn KMS decrypt permissions theo workload identity;
- Alert decrypt volume bất thường;
- Khi xử lý incident, có quy trình disable/rotate keys và revoke tokens.

**Mất key có thể làm mất khả năng restore toàn bộ authorized clients.** Đây có thể là lựa chọn chấp nhận được nếu policy cho phép reauthorization, nhưng phải được dự liệu thay vì coi là sự cố bất ngờ.

---

## 10. Thiết kế encryption wrapper đúng ranh giới

Một sai lầm nguy hiểm là “mã hóa” ngay trong `OAuth2AuthorizedClient` rồi trả object chứa ciphertext cho manager:

```java
// SAI Ý TƯỞNG: downstream nhận ciphertext thay token.
OAuth2AccessToken token = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "ENCRYPTED_TOKEN_VALUE",
    issuedAt,
    expiresAt);
```

Nếu `loadAuthorizedClient` trả token value đã mã hóa, `RestClient` có thể gửi:

```http
Authorization: Bearer ENCRYPTED_TOKEN_VALUE
```

đến Resource Server. Token value chỉ được mã hóa **trên đường đi xuống storage**, và phải được giải mã **trước khi tạo `OAuth2AuthorizedClient` được đưa cho Spring Security dùng**.

### 10.1. Kiến trúc adapter được khuyến nghị

```text
Spring Security OAuth2AuthorizedClientManager
                |
                | loadAuthorizedClient(registration, principal)
                v
Custom SecureOAuth2AuthorizedClientService
                |
                | 1. Lookup encrypted persistence record
                | 2. Verify tenant/principal/registration binding
                | 3. Decrypt access/refresh token values
                | 4. Reconstruct OAuth2AuthorizedClient
                v
Manager nhận token plaintext trong process memory
                |
                v
HTTP Authorization: Bearer actual-token

saveAuthorizedClient:
  manager -> service -> encrypt token values -> DB

removeAuthorizedClient:
  manager -> service -> delete record + lifecycle handling
```

### 10.2. Pseudocode interface của persistence

```java
// Pseudocode thiết kế, KHÔNG phải implementation production.
interface EncryptedAuthorizedClientStore {
    EncryptedRecord find(
        String registrationId,
        String principalKey,
        String tenantId);

    void upsertAtomically(
        EncryptedRecord encryptedRecord,
        long expectedVersion);

    void delete(
        String registrationId,
        String principalKey,
        String tenantId);
}

interface TokenProtector {
    EncryptedPayload encrypt(
        String tokenValue,
        TokenContext authenticatedContext);

    String decrypt(
        EncryptedPayload payload,
        TokenContext authenticatedContext);
}
```

Các types `EncryptedRecord`, `EncryptedPayload` và `TokenContext` là **types do ứng dụng định nghĩa**; chúng không phải Spring Security built-in APIs. Sự lựa chọn thuật toán/encoding/key lifecycle cần security review.

### 10.3. Mẫu adapter Java skeleton có ranh giới rõ

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;

final class SecureAuthorizedClientService
        implements OAuth2AuthorizedClientService {

    private final EncryptedAuthorizedClientStore store;
    private final TokenProtector protector;
    private final AuthorizedClientRecordMapper mapper;

    SecureAuthorizedClientService(
            EncryptedAuthorizedClientStore store,
            TokenProtector protector,
            AuthorizedClientRecordMapper mapper) {
        this.store = store;
        this.protector = protector;
        this.mapper = mapper;
    }

    @Override
    @SuppressWarnings("unchecked")
    public <T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
            String registrationId, String principalName) {

        // 1. Resolve trusted tenant/security scope (not raw user input).
        // 2. Find matching encrypted record by trusted composite identity.
        // 3. Verify AAD, key version, record integrity and lifecycle state.
        // 4. Decrypt actual access/refresh tokens in controlled memory.
        // 5. Reconstruct OAuth2AuthorizedClient with plaintext token objects.
        throw new UnsupportedOperationException(
            "Architecture skeleton only");
    }

    @Override
    public void saveAuthorizedClient(
            OAuth2AuthorizedClient authorizedClient,
            Authentication principal) {

        // Encrypt token values, preserve issuedAt/expiresAt/scopes.
        // Bind ciphertext to registration/principal/tenant.
        // Use atomic save/CAS for refresh rotation correctness.
        throw new UnsupportedOperationException(
            "Architecture skeleton only");
    }

    @Override
    public void removeAuthorizedClient(
            String registrationId, String principalName) {

        // Delete local credentials and write deletion/revocation event.
        throw new UnsupportedOperationException(
            "Architecture skeleton only");
    }
}
```

**Đây là skeleton giảng giải, cố ý không chạy được.** Nó không được đưa vào application context nếu chưa triển khai store, mapper, token protector, tenant binding, error handling, concurrency và tests. Đặc biệt, không được dùng placeholder cipher hoặc tự chế AES-GCM từ những đoạn code không security review.

### 10.4. Có thể tận dụng JdbcOAuth2AuthorizedClientService không?

`JdbcOAuth2AuthorizedClientService` có extension points như row mapper và parameter mapper. Tuy nhiên, nếu muốn mã hóa ở cấp cột:
- Phải mã hóa khi save;
- Phải giải mã khi load;
- Giữ tương thích với token types/scopes/timestamps;
- Dùng AAD và metadata keys thích hợp;
- Xử lý migrations;
- Không để row mapper vô tình tạo plaintext logs.

Một custom service/persistence adapter có thể minh bạch hơn khi thêm tenant keys, ciphertext format và CAS. Không thay bean JWT decoder hoặc RestClient interceptor để làm công việc mã hóa storage.

---

## 11. Encryption key lifecycle và backup retention

Backup có ciphertext nhưng không có key phù hợp thì không thể restore token values.

### 11.1. Key version phải đi cùng dữ liệu

Ví dụ:

```text
DB snapshot 2026-11-01
  token encrypted with key-v2

Live DB 2026-11-16
  token encrypted with key-v4

Disaster restore from Nov 01:
  app must still decrypt key-v2 records,
  or deliberately discard/re-authorize them
```

Nếu đã destroy key-v2 nhưng backup vẫn được kỳ vọng phục hồi, RTO có thể không đạt. Nếu policy **cố ý crypto-erase** dữ liệu bằng cách destroy key, phải ghi rõ backup đó không còn được dùng để phục hồi token.

### 11.2. Rotation có hai việc khác nhau

- **Rotate KEK / rewrap DEK:** thay key dùng để bảo vệ DEK; có thể không cần re-encrypt mọi token ciphertext tùy thiết kế.
- **Rotate DEK / re-encrypt token values:** tạo ciphertext mới và quản lý key version cũ trong thời gian migration.

Không coi đổi key alias trong config là đã re-encrypt tất cả records và snapshots.

### 11.3. Key custody

- KMS/HSM với IAM riêng;
- Không lưu master key trong source, database row hoặc backup cùng nơi;
- Workload identity có quyền decrypt tối thiểu;
- Backup operator không nhất thiết được quyền decrypt;
- Có break-glass workflow với multi-person approval khi phù hợp;
- Tất cả decrypt API calls có audit metadata không nhạy cảm;
- Có plan restore khi KMS vùng chính outage.

### 11.4. Crypto-erasure và xóa theo người dùng

Nếu muốn xóa riêng dữ liệu của user A trong **mọi snapshots** bằng cách destroy key, cần key granularity phù hợp, ví dụ **per-user/per-tenant DEK**. Nếu tất cả users dùng chung một DEK, destroy DEK sẽ làm mất dữ liệu của tất cả.

Crypto-erasure cần chứng minh:
- Không còn bản copy DEK plaintext hoặc wrapped-DEK có thể unwrap;
- Không còn bản sao token plaintext ở logs/dumps/exports;
- KMS backup/key escrow không vô tình còn quyền phục hồi;
- Khóa nào phục vụ dữ liệu nào được ghi nhận đúng.

Không tuyên bố “đã xóa khỏi mọi backup” chỉ vì xóa một alias KMS hoặc một row ở primary DB.

---

## 12. Backup một hệ thống có refresh token rotation

Đây là tình huống vận hành quan trọng nhất của bài.

### 12.1. Refresh token rotation thay đổi dữ liệu liên tục

Giả sử:

```text
T1:
  Active DB stores R1
  Backup snapshot stores R1

T2:
  Client uses R1 to refresh
  AS returns access token A2 + refresh token R2
  AS invalidates R1
  Active DB stores R2

T3:
  Disaster -> restore backup from T1
  Restored DB now stores R1
  AS expects current R2, R1 already invalid
```

Nếu instance được phục hồi cố dùng `R1`:
- AS có thể trả `invalid_grant`;
- Nếu AS có reuse detection/token-family policy, sử dụng R1 cũ có thể bị coi là replay và **khiến cả token family đang còn hoạt động bị revoke**;
- Các client instances khác có thể đang dùng R2 và cũng mất phiên;
- User cần bắt đầu authorization flow mới.

Theo OAuth 2.0 Security BCP (RFC 9700), refresh-token rotation/reuse detection là cơ chế chống replay quan trọng, đặc biệt đối với public clients.

### 12.2. Vì sao không tự động refresh hàng loạt ngay sau restore?

Một disaster restore có thể phục hồi hàng nghìn refresh tokens cũ. Nếu app lập tức chạy batch reauthorization:
- Nhiều invalid_grant xảy ra đồng thời;
- AS token endpoint chịu tải lớn;
- Reuse detection có thể revoke nhiều token families;
- Hệ thống phát nhiều lỗi đăng nhập và support alerts;
- Logs có thể chứa dữ liệu nhạy cảm nếu debug quá mức.

**Khuyến nghị:** có cờ **quarantine/reconciliation mode** cho authorized-client records được restore, nhất là user-delegated refresh tokens. Không gửi refresh request hàng loạt cho record cũ cho đến khi được phân loại theo policy.

### 12.3. Các phương án khôi phục an toàn

| Phương án | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| **Bỏ toàn bộ restored refresh tokens** | Reauthorization chấp nhận được | User login/consent lại |
| Đối chiếu token-state/generation từ authoritative metadata | AS/integration có cơ chế hợp lệ | Không đoán từ access token expiry |
| Quarantine theo snapshot timestamp, cấp lại có kiểm soát | Có quy trình recovery rõ | Tránh trigger reuse detection hàng loạt |
| Chủ động revoke theo supported AS API | Sự cố credential compromise | Có thể làm gián đoạn users |
| Cho machine client xin token mới | `client_credentials` | Không cần restore refresh tokens |
| Read-only warm-up trước khi resume | Muốn kiểm tra mappings/key config | Không sử dụng stale token để gọi AS |

**Không có API OAuth2 chuẩn chung cho client để hỏi “refresh token R1 đã bị rotation chưa?” bằng cách không dùng token.** Một số AS có admin/revocation/introspection policy riêng. Nếu không có cách kiểm chứng, lựa chọn an toàn có thể là bỏ restored token và reauthorize.

### 12.4. Default Spring manager có thể xóa record khi invalid_grant

`AuthorizedClientServiceOAuth2AuthorizedClientManager` có failure handling mặc định: khi reauthorization thất bại vì `invalid_grant`, authorized client cũ có thể được xóa khỏi `OAuth2AuthorizedClientService`.

Đây là behavior hữu ích để tránh tái dùng credential không còn hợp lệ, **nhưng không phải giải pháp toàn bộ restore**:
- Có thể đã gây AS reuse detection trước khi xóa;
- Cần chuẩn bị UX user reauthorization;
- Cần tránh request retry vô hạn;
- Không được restore lại cùng stale record vào lần DR tiếp theo.

### 12.5. Concurrent refresh token rotation trong cluster

Ngay cả khi **không restore backup**, hai instances có thể đọc cùng R1 trước khi một instance cập nhật R2.

```text
Node A reads R1
Node B reads R1

A refreshes R1 -> gets R2 -> saves R2
B refreshes R1 -> invalid_grant / reuse event

Potential impact:
  AS revokes token family
  User must reauthorize
```

Một storage dùng chung không mặc nhiên có **per-authorized-client refresh locking/CAS**. Với rotation-enabled AS và multi-instance, cân nhắc:
- Distributed lock có TTL/fencing;
- Optimistic version check;
- Single-flight refresh theo `(registration, principal, tenant)`;
- Retry/re-read logic không reuse stale refresh token;
- Fail closed khi conflict;
- Tests với concurrent refresh.

### 12.6. Không dùng backup để “quay lui token version”

Nếu DB hiện có R2, operator restore một row R1 với ý nghĩ “token trước vẫn dùng được”, điều đó sai với rotation semantics. Backup dùng để phục hồi **dữ liệu còn hợp lệ**, không để phủ nhận trạng thái authorization hiện tại tại AS.

---

## 13. Backup và data deletion không độc lập

Một user có thể:
- Logout;
- Unlink provider;
- Thu hồi consent ở OP;
- Yêu cầu xóa liên kết dữ liệu;
- Bị khóa hoặc mất quyền tenant;
- Bị offboard khỏi tổ chức.

### 13.1. Xóa dữ liệu live trước, rồi xử lý các bản sao

```text
User unlinks Company SSO
      |
      v
1. Verify authenticated user + ownership
2. Mark credential disconnected / revoked in authoritative ledger
3. Stop new token usage
4. Revoke at AS if supported/policy requires
5. Remove authorized client from active store
6. Invalidate in-memory caches/replicas
7. Record deletion event without token value
8. Let backup retention/crypto-erasure policy handle snapshots
```

**Logout của RP không nhất thiết xóa mọi authorized client.** Một ứng dụng có thể muốn giữ token để user không cần consent lại; nhưng một sản phẩm khác yêu cầu xóa ngay khi logout. Phải phân biệt **logout browser session**, **disconnect account**, **revoke grant** và **delete stored credentials** theo hợp đồng nghiệp vụ.

### 13.2. Xóa ở backup có thể chậm hơn xóa live

Nhiều backup systems giữ immutable snapshots trong một khoảng đã định. Không thể xóa đúng một row khỏi mọi immutable snapshots mà không rebuild toàn bộ artifact.

Các cơ chế giảm rủi ro:
- Retention backup ngắn nhất đáp ứng RPO/RTO/compliance;
- Isolated encrypted storage;
- Per-user/tenant crypto-erasure nếu thiết kế hỗ trợ;
- Delete/revoke ledger durable;
- Restore procedure replay tombstones **trước khi mở token usage**.

### 13.3. Không hồi sinh row đã xóa khi restore

```text
Day 1: snapshot contains authorized_client(U1)
Day 5: user U1 unlinks account -> live DB deletes U1
Day 8: disaster -> restore Day 1 snapshot
       |
       v
Without tombstones:
  U1 token record reappears (BAD)

With deletion ledger newer than snapshot:
  Replay unlink event before app resumes
  Remove U1 record
  Do not use its refresh token
```

**Đây là một yêu cầu correctness độc lập với token encryption**. Backup có thể mã hóa rất tốt nhưng vẫn vi phạm kỳ vọng xóa dữ liệu nếu restore làm sống lại bản ghi bị thu hồi.

### 13.4. Thiết kế tombstone ledger

Metadata cần thiết có thể gồm:
- Stable internal principal identifier;
- Registration ID/issuer;
- Tenant identifier;
- Deletion/revocation event version và timestamp;
- Causal request/audit ID;
- Legal/retention policy class.

Không chứa raw access token hoặc refresh token.

Một event giả:

```json
{
  "event_type": "authorized_client_disconnected",
  "tenant_id": "tenant-a",
  "principal_key": "principal-key-123",
  "registration_id": "company-login",
  "event_version": 42,
  "occurred_at": "2026-11-16T09:00:00Z"
}
```

Đây là **application-defined data model**, không phải Spring Security built-in event schema.

### 13.5. Quyền xóa của user khác admin/service

Không expose:

```http
DELETE /api/authorized-clients?principal=someone-else
```

và gọi thẳng `removeAuthorizedClient` theo raw input. Phải xác minh **chủ thể được phép xóa link đó**, tenant boundary, registration ID allowlist và audit, không cho phép người dùng xóa/can thiệp credential của người khác.

---

## 14. Xóa local authorized client qua service

Ví dụ service-level operation:

```java
package example.security;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.stereotype.Service;

@Service
public class AuthorizedClientLifecycleService {

    private final OAuth2AuthorizedClientService clients;

    public AuthorizedClientLifecycleService(
            OAuth2AuthorizedClientService clients) {
        this.clients = clients;
    }

    public void disconnectVerifiedPrincipal(
            String registrationId,
            String trustedPrincipalKey) {

        // Caller phải chứng minh ownership + tenant authorization
        // TRƯỚC khi vào method này.
        clients.removeAuthorizedClient(
            registrationId, trustedPrincipalKey);
    }
}
```

**Đây chỉ là thao tác xóa local cache/store**. Nếu nghiệp vụ cần revoke token tại AS, quy trình phải biết:
- Token nào cần revoke;
- Endpoint/credential AS nào đáng tin;
- Có cần revoke refresh token hoặc access token;
- Nếu AS không reachable, local deletion có thực hiện trước không;
- Có durable retry/outbox không;
- Timeout/error semantics và user-facing state.

### 14.1. Revoke token theo RFC 7009

RFC 7009 định nghĩa token revocation endpoint cho OAuth2. Nhưng:
- Không phải mọi AS expose cùng endpoint/support;
- Confidential client thường cần authentication;
- Request body chứa **token value nhạy cảm**;
- Thành công của local deletion không chứng minh remote revocation;
- Revocation response có thể không tiết lộ token có tồn tại hay không theo chuẩn.

Nếu không thể revoke tại AS, ít nhất phải ngăn client dùng lại token local và ghi incident/follow-up phù hợp với security policy. Không tự gửi token đến revocation URI từ untrusted query.

---

## 15. Tenant, issuer và principal isolation

Default JDBC schema khóa chính:

```text
(client_registration_id, principal_name)
```

Điều này **không có tenant ID độc lập trong primary key**.

Nếu hệ thống multi-tenant, cần xác định chắc:
- Cùng `principal_name` ở Tenant A/B có thể trùng không;
- Cùng `sub` từ hai issuers có thể trùng không;
- Có user identity mapping về một internal principal ID duy nhất không;
- Registration ID có tenant-specific hay shared;
- Ai được quyền `loadAuthorizedClient` theo key đó.

### 15.1. Không dùng email làm global key

```text
issuer Company: sub=42, email=alice@example.test
issuer Partner: sub=42, email=alice@example.test
```

Điều đó không chứng minh hai tài khoản là một. Với OIDC, identity key tối thiểu là **(issuer, subject)**. Nếu dùng internal principal ID, nó phải được tạo bởi account-linking policy rõ và không bị cross-tenant reuse.

### 15.2. Composite identity trong custom store

Một thiết kế minh họa:

```text
tenant_id
issuer_id
client_registration_id
principal_key
token_kind
record_version
```

Dùng những trường này để:
- Query chính xác record;
- Kiểm tra authorization/tenant boundary;
- Gắn AAD khi encrypt;
- Lock/CAS refresh token rotation;
- Xóa theo user/tenant policy.

Không mặc định chỉnh PK của bảng `oauth2_authorized_client` của Spring rồi nghĩ `JdbcOAuth2AuthorizedClientService` sẽ xử lý composite key mới. Cần custom DAO/service hoặc mapping được thiết kế đầy đủ.

### 15.3. Service principal cho client_credentials

Với `client_credentials`, dùng tên ổn định như:

```text
registrationId = reports-machine
principalName  = reports-batch
```

để cache có thể tái sử dụng token. Nhưng nếu cùng app phục vụ tenants với permissions khác nhau, một principal chung có thể dẫn tới **cross-tenant token reuse**. Cần cache key theo tenant/resource và AS-issued audience phù hợp.

---

## 16. Operational retention job: xóa record thế nào cho đúng?

### 16.1. Vì sao không DELETE toàn bộ expired access tokens?

Sai:

```sql
DELETE FROM oauth2_authorized_client
WHERE access_token_expires_at < CURRENT_TIMESTAMP;
```

Nếu row có refresh token hợp lệ, query này xóa cả khả năng renew. Hậu quả có thể là user login lại hàng loạt.

### 16.2. Candidate cleanup hạn chế hơn

Với bảng stock và cơ sở dữ liệu PostgreSQL, minh họa một query **chỉ để xem candidates**:

```sql
SELECT
    client_registration_id,
    principal_name,
    access_token_expires_at,
    created_at
FROM oauth2_authorized_client
WHERE refresh_token_value IS NULL
  AND access_token_expires_at < CURRENT_TIMESTAMP - INTERVAL '7 days';
```

Query này cố ý chỉ **SELECT**. Một retention job production còn phải xác định:
- Record có được dùng bởi job đang chạy không;
- Có requirement giữ metadata hay không;
- Có recent authorization/update race không;
- Có tenant/deletion policy không;
- Có được phép xóa các bản ghi sau thời gian đó không.

**Con số 7 ngày chỉ là ví dụ buffer để học, không phải policy mặc định.**

### 16.3. Nếu muốn xóa, dùng chiến lược atomic và có giới hạn

Ví dụ transaction-level pseudocode:

```text
1. Acquire appropriate lifecycle lock / version predicate
2. Select candidates by approved policy
3. Recheck current record version and grant status
4. Delete by exact trusted key
5. Write non-sensitive deletion event / audit
6. Commit
7. Emit aggregate metric (count), no token values
```

Không chạy bulk delete 10 triệu rows trong một transaction khi có nguy cơ khóa DB. Dùng batching/monitoring, tôn trọng replica lag, PITR và backup load.

### 16.4. Không giữ stale access token vì mục đích “audit”

Nếu cần audit, lưu:
- Registration ID;
- Principal pseudonymous key;
- Issuer category;
- Token issuance/expiry timestamps;
- Scope category;
- Outcome;
- Token fingerprint **không thể dùng lại** nếu thực sự cần và được review.

Không giữ raw token chỉ để trả lời “user đã dùng token nào”. Token values là credentials, không phải log fields.

### 16.5. Retention policy cần được thực thi ở mọi lớp

Một row đã xóa khỏi primary database có thể còn trong:
- Replica lagging;
- WAL/binlog;
- Backup vault;
- Storage snapshots;
- Test exports;
- Application caches;
- Heap dumps;
- Audit logs.

Chính sách phải mô tả expected lag và xóa/crypto-erasure theo từng hệ thống, không chỉ một SQL DELETE.

---

## 17. Backup/restore runbook chuẩn

### 17.1. Trước sự cố: chuẩn bị

1. Xác định authorized-client tokens có được backup hay không.
2. Phân loại registrations: machine vs delegated, AS/protocol properties, refresh rotation.
3. Ghi rõ nguồn truth cho revocation, disconnect và deletion events.
4. Thiết kế database backup, retention, encryption và IAM.
5. Kiểm tra key versions và khả năng unwrap historical ciphertext.
6. Tài liệu hóa backup manifest: timestamp, DB schema version, key versions, checksum.
7. Có test restore ở isolated environment không dùng production tokens để gọi AS.
8. Có switch tạm dừng outbound token refresh hoặc bulk jobs.
9. Có kế hoạch reauthorization/AS rate-limiting.
10. Định nghĩa RPO/RTO và tiêu chí thành công có thể đo.

### 17.2. Trong sự cố: khôi phục có kiểm soát

```text
Incident declared
      |
      v
Freeze token mutation / active refresh where possible
      |
      v
Restore DB snapshot into isolated target
      |
      v
Verify backup integrity + schema + key version
      |
      v
Replay deletion/revocation ledger after snapshot
      |
      v
Quarantine potentially stale rotated refresh tokens
      |
      v
Purge/reconcile tokens by approved policy
      |
      v
Smoke test with synthetic machine client / test AS
      |
      v
Resume low-risk traffic gradually
      |
      v
Monitor invalid_grant, 401, 403, refresh activity
      |
      v
Post-incident audit + update runbook
```

### 17.3. Đừng restore trực tiếp vào môi trường đang chạy

Nếu app đang dùng R2 nhưng restore ghi R1, concurrent refresh có thể kích hoạt reuse detection. Do đó, tốt nhất:
- Cô lập restored database;
- Dừng/đóng băng mutation relevant workloads;
- Reconcile token state và deletion events;
- Mở traffic từng phần;
- Có rollback/forward recovery plan.

### 17.4. Nếu không thể chắc token có còn hợp lệ

**Bỏ local token và reauthorize** thường an toàn hơn thử sử dụng một refresh token cũ hàng loạt. Đặc biệt khi AS có strict token rotation, việc “test thử” token thật có thể làm thay đổi trạng thái token family.

### 17.5. Nếu backup hoặc key có dấu hiệu bị lộ

Đây là **security incident**, không chỉ vấn đề availability:
- Chặn thêm việc truy cập backup;
- Thu thập access logs/forensics theo quy trình;
- Xác định token/registration/tenants bị ảnh hưởng;
- Xem xét revoke tokens và rotate client credentials/keys;
- Giảm quyền của compromised identities;
- Đánh giá phạm vi dữ liệu cá nhân/credentials;
- Thông báo theo policy và nghĩa vụ áp dụng;
- Không phục hồi một snapshot nghi ngờ bị sửa mà chưa kiểm integrity.

---

## 18. Phục hồi mà không khiến người dùng đăng nhập lại vô hạn

Một UX khôi phục hợp lý:

```text
Restored app receives user request
      |
      v
Load authorized client
      |
      +-- record quarantined/revoked?
      |      -> do not use token
      |      -> redirect to safe reauthorization flow
      |
      +-- access token still valid?
      |      -> may continue if trusted and allowed
      |
      +-- refresh token state uncertain?
             -> controlled reauth instead of blindly retrying
```

**Không viết**:

```java
while (true) {
    try {
        refreshTokenAgain();
    } catch (Exception ignored) {
        // Retry forever.
    }
}
```

Vòng lặp vô hạn có thể làm AS rate limit, tăng số `invalid_grant` và che nguyên nhân restore stale tokens.

### 18.1. Sự khác nhau giữa reauthorization và login

- Có thể cần redirect user đến authorization endpoint để xin grant mới.
- OP SSO session có thể còn, nên không cần nhập mật khẩu nhưng vẫn có **authorization transaction mới**.
- `client_credentials` có thể lấy token mới không cần user.
- Không lấy ID Token hoặc refresh token cũ để tạo Authentication mới mà bỏ state/PKCE/nonce/issuer validation.

### 18.2. Browser logout không tự động revoke all tokens

Một user logout khỏi RP session có thể không yêu cầu revoke authorized-client grants. Nếu sản phẩm yêu cầu “Disconnect Google account” thì action này mới cần xóa/revoke token theo policy.

Cần có documentation phân biệt rõ các hành vi, đặc biệt khi người dùng nghĩ “đăng xuất” đồng nghĩa “không còn token nào được lưu”.

---

## 19. Xử lý invalid_grant và failure handler

Một `invalid_grant` tại refresh thường nghĩa token không còn dùng được, nhưng nguyên nhân có thể là:
- Token expired/revoked;
- Refresh token đã rotate;
- Client credentials/registration thay đổi;
- Grant không còn phù hợp;
- AS policy đã đổi.

### 19.1. Service manager

Với scheduled/service-tier:

```java
@Bean
OAuth2AuthorizedClientManager backgroundManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService clients) {

    OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
            .refreshToken()
            .clientCredentials()
            .build();

    AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
        new AuthorizedClientServiceOAuth2AuthorizedClientManager(
            registrations, clients);

    manager.setAuthorizedClientProvider(provider);
    return manager;
}
```

Imports sử dụng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
```

**Cảnh báo:** Provider builder như trên cần phù hợp grant configuration của từng registration. Nó không tự làm authorization-code browser flow hay nonce validation trong scheduled thread.

### 19.2. Default invalid_grant removal

Spring Security manager có default failure handling để loại bỏ stale authorized client khi phù hợp với `invalid_grant`.

Nếu ứng dụng tự thay `setAuthorizationFailureHandler(...)`, cần chắc:
- Không giữ stale token vô hạn;
- Không xóa nhầm token vừa được cập nhật bởi instance khác;
- Có thể audit non-sensitive failure category;
- Có policy reauthorization;
- Không biến lỗi từ một user thành xóa token của user khác.

### 19.3. Downstream 401 khác refresh invalid_grant

Một Resource Server trả 401 `invalid_token` không mặc nhiên đồng nghĩa refresh token invalid; nó có thể do audience/issuer mismatch, expiration hoặc revocation.

Nếu dùng `OAuth2ClientHttpRequestInterceptor`, có thể cấu hình failure handler để xóa authorized client không hợp lệ theo contract. Không retry không giới hạn mọi 401; trước tiên hiểu AS/RS error và token state.

### 19.4. Backup restore không được khôi phục stale token sau khi handler xóa

Nếu login/refresh thất bại do stale R1 và manager đã xóa record, một replication/restore job không được ghi lại R1 từ snapshot cũ. Deletion/version ledger phải có precedence so với backup data cũ.

---

## 20. Backup với các thành phần Reactive

Trong WebFlux, các abstractions tương ứng:

- `ReactiveOAuth2AuthorizedClientService`;
- `ServerOAuth2AuthorizedClientRepository`;
- `InMemoryReactiveOAuth2AuthorizedClientService`;
- `ReactiveOAuth2AuthorizedClientManager`;
- `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.

### 20.1. Reactive service không dùng Servlet service

```text
Servlet:
  OAuth2AuthorizedClientService
  loadAuthorizedClient(...) -> OAuth2AuthorizedClient

Reactive:
  ReactiveOAuth2AuthorizedClientService
  loadAuthorizedClient(...) -> Mono<OAuth2AuthorizedClient>
```

Một `JdbcOAuth2AuthorizedClientService` dùng blocking JDBC không nên được gọi trực tiếp trên Netty event loop trong Reactive request processing.

Nếu cần persistent authorized clients trong WebFlux:
- Chọn reactive persistence/DAO phù hợp hoặc một adapter blocking được offload có kiểm soát;
- Duy trì semantics cache key, encryption, refresh rotation và deletion;
- Compose publisher đúng;
- Không gọi `.block()` trong request handler.

### 20.2. Encryption trong Reactive pipeline

```text
ReactiveOAuth2AuthorizedClientService.load(...)
    -> load encrypted record asynchronously
    -> decrypt under authorized workload key policy
    -> build OAuth2AuthorizedClient
    -> Mono<OAuth2AuthorizedClient>
```

KMS calls có thể là network I/O hoặc blocking SDK. Nếu SDK blocking, cần xử lý scheduler đúng và có timeout/backpressure/circuit-breaker policy; không đặt một thao tác blocking lâu vào Reactor event loop.

### 20.3. Reactive cache và refresh concurrency

Hai subscriptions cùng lúc có thể gọi authorize/refresh. Nếu persistence dùng optimistic locking:
- Query/update theo record version;
- Khi CAS conflict, re-read current token;
- Không reuse refresh token đã rotate;
- Không leak token giữa tenants hoặc publishers;
- Test bằng `StepVerifier` và concurrent subscriptions.

**Reactive không làm bài toán rotation tự biến mất**; nó chỉ thay API/lifecycle execution.

---

## 21. Logging, metrics và audit

### 21.1. Log tối thiểu an toàn

Ví dụ schema sự kiện:

```json
{
  "event": "authorized_client_storage",
  "action": "load",
  "result": "not_found",
  "registration_id": "company-login",
  "principal_category": "end_user",
  "tenant_category": "enterprise",
  "storage_backend": "jdbc",
  "trace_id": "internal-safe-id"
}
```

Event này **không chứa token**, raw principal/email hoặc Authorization header. Đây là schema ứng dụng tự định nghĩa, không phải log mặc định của Spring Security.

### 21.2. Metrics có cardinality hữu hạn

```text
authorized_client_store_operations_total{operation="load",result="success"}
authorized_client_store_operations_total{operation="save",result="failure"}
authorized_client_store_operations_total{operation="delete",reason="disconnect"}
authorized_client_refresh_total{registration="company",result="invalid_grant"}
authorized_client_backup_restore_total{result="success"}
authorized_client_restore_quarantine_total{reason="stale_refresh"}
authorized_client_decrypt_failures_total{key_version="v4"}
```

Không đặt `tokenValue`, email, `sub`, session ID hay raw exception message vào metric labels.

### 21.3. Audit ai đọc credential

Một quyền đọc DB row không nên tự động cho phép xem raw token. Dùng:
- Database audit SQL access;
- KMS decrypt audit;
- Service-level authorization audit;
- Break-glass approval log;
- Alert bulk export;
- Không log value trong audit event.

Đặc biệt, monitoring của `loadAuthorizedClient` có thể có tần suất cao; cần sampling/aggregation hợp lý để không tạo PII-rich log stream.

### 21.4. Không in AuthorizedClient object

Không nên:

```java
log.info("authorizedClient={}", authorizedClient);
log.debug("accessToken={}", client.getAccessToken().getTokenValue());
log.error("refreshToken={}", client.getRefreshToken().getTokenValue());
```

Dù object `toString()` hiện tại có che token, **không dựa vào điều đó làm biện pháp bảo mật**. Giữ quy tắc không truyền credential-bearing objects vào loggers.

---

## 22. Dữ liệu authorized client trong session và cookie

Một ứng dụng có thể dùng `HttpSessionOAuth2AuthorizedClientRepository` hoặc repository dựa trên HttpSession cho một số trường hợp.

Điều này nghĩa token data có thể đi vào:
- Servlet container memory;
- Redis nếu Spring Session lưu HttpSession;
- Session persistence/swap;
- Session backups/Redis snapshots;
- Browser session identifier (không nhất thiết token value).

### 22.1. Browser cookie không nên chứa raw OAuth2AuthorizedClient

Cookie session tiêu chuẩn thường giữ **opaque session ID**, không phải toàn bộ object authorized client. Không tự serialize token values vào cookie không mã hóa/không xác thực.

### 22.2. Redis persistence có thể sao lưu tokens

Nếu Spring Session lưu authorized-client object trong Redis:
- Redis AOF/RDB snapshots có thể chứa token data;
- Redis replica và backups cũng cần encryption/access control;
- Session TTL không tự bảo đảm token bytes biến mất ngay khỏi snapshots/WAL;
- Redis key expiration khác retention của backup artifacts.

### 22.3. Logout và invalidation

Invalidate session có thể xóa token **chỉ nếu token thật sự được lưu trong session đó**. Nếu authenticated principal records được delegate sang `OAuth2AuthorizedClientService` JDBC, logout session không tự xóa mọi authorized clients trong DB.

**Không suy luận xóa session = revoke consent.** Kiểm tra chính xác repository/service wiring.

---

## 23. Principal-scoped backup và dữ liệu cá nhân

Một user có thể kết nối nhiều providers:

```text
user internal-42:
  company-login -> company access/refresh token
  calendar      -> calendar access/refresh token
  reports       -> reports access token
```

Khi user yêu cầu “xóa liên kết Calendar”, không được xóa nhầm Company login hoặc toàn bộ authorized clients của những users khác.

### 23.1. Xác định phạm vi xóa

Có thể cần:
- Chỉ một `registrationId`;
- Một `principalKey`;
- Một tenant/issuer boundary;
- Một specific grant/resource;
- Tất cả tokens của user nếu account deletion.

### 23.2. Audit mà không giữ credential

Ví dụ audit record:

```json
{
  "subject_key": "internal-42",
  "registration_id": "calendar",
  "action": "disconnect",
  "outcome": "local_deleted",
  "revocation_outcome": "remote_pending"
}
```

Không ghi access/refresh token để làm chứng cứ.

### 23.3. Xóa dữ liệu phải xét backups

Nếu backup sẽ hết hạn sau một thời gian chính sách, có thể:
- Xóa active record ngay;
- Chặn restoration bằng tombstones;
- Hạn chế quyền backup;
- Giữ snapshots trong thời gian tối thiểu đã phê duyệt;
- Cân nhắc crypto-erasure khi yêu cầu và kiến trúc cho phép.

Đây là phần cần đánh giá legal/privacy theo khu vực và tổ chức; bài không đặt ra một thời hạn pháp lý chung.

---

## 24. Database permissions và chống exfiltration

### 24.1. Least-privilege DB role

Ứng dụng chỉ cần các quyền phù hợp trên bảng authorized clients, ví dụ:
- `SELECT` để load;
- `INSERT`/`UPDATE` để save;
- `DELETE` để remove;
- Không cần `DROP TABLE` hay `ALTER TABLE` runtime.

Migration tool dùng role có quyền schema riêng, không chung với runtime application.

### 24.2. Backup account tách khỏi app account

Backup job có quyền tạo snapshot theo policy nhưng không nhất thiết có:
- Quyền decrypt KMS application token;
- Quyền thay đổi production token rows;
- Quyền xóa immutable backups;
- Quyền đọc mọi PII dưới dạng plaintext.

### 24.3. Network và transport

- Database endpoint chỉ mở cho workload cần thiết;
- TLS giữa app và DB/Redis;
- TLS tới AS/RS;
- Không đưa DB dump qua email/chat unencrypted;
- Thực thi egress allowlist cho AS token endpoint và downstream API;
- Không cấp quyền debug SELECT toàn bảng cho support role thông thường.

### 24.4. Backups và encryption key không nên chung một quyền duy nhất

Nếu một IAM role có cả quyền tải toàn bộ backup và quyền decrypt mọi token key, compromise một principal đủ làm mất cả confidentiality. Phân tách roles, approval và audit giúp giảm blast radius.

---

## 25. Khả năng phục hồi sau khi thay đổi client secret hoặc issuer

Không chỉ refresh rotation, cấu hình AS cũng có thể đổi:

```text
Snapshot T1:
  registrationId = company-login
  clientId = portal-client-old
  refresh token R1

Live T2:
  clientId = portal-client-new
  issuer metadata / client auth policy updated
```

Sau restore T1:
- `ClientRegistration` hiện tại có thể không khớp token cũ;
- Refresh token R1 có thể bị AS ràng buộc với old client;
- Token endpoint có thể trả `invalid_client` hoặc `invalid_grant`;
- JWKS/issuer/audience policy có thể đã thay;
- User phải reauthorize theo cấu hình mới.

### 25.1. Secret rotation không tự hợp lệ hóa token cũ

Đổi client secret:
- Có thể giữ client ID và grants nếu AS hỗ trợ;
- Có thể đồng thời revoke old tokens tùy policy;
- Không bảo đảm mọi refresh token cũ vẫn dùng được.

### 25.2. Không lưu client secret trùng trong authorized-client table

`ClientRegistration` có thể chứa client secret theo cấu hình, nhưng authorized-client persistence schema chuẩn lưu token metadata và token values, **không cần lưu client secret trong mỗi row**. Tách secret management khỏi token cache để giảm việc backup nhiều bản sao client secret.

### 25.3. Migration giữa issuers

Không copy token từ issuer A sang registration của issuer B chỉ vì hai provider dùng cùng email hoặc `sub`. Token có issuer/audience/client binding; cần migration và reauthorization được thiết kế đúng protocol.

---

## 26. Kiểm thử kỹ thuật cho storage và backup

Một hệ thống cần test nhiều tầng thay vì chỉ thấy “SQL INSERT thành công”.

### 26.1. Unit test storage contract

Test `OAuth2AuthorizedClientService` với synthetic tokens:
- Save rồi load theo đúng registration/principal;
- Không load được bằng principal khác;
- Remove đúng một record;
- Không xóa nhầm registration khác;
- Access/refresh token values, timestamps và scopes round-trip chính xác;
- Không log token values.

### 26.2. Tạo synthetic OAuth2AuthorizedClient

```java
import java.time.Instant;
import java.util.Set;

import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

ClientRegistration registration =
    ClientRegistration.withRegistrationId("reports-machine")
        .clientId("test-client")
        .clientSecret("test-only-secret")
        .authorizationGrantType(
            AuthorizationGrantType.CLIENT_CREDENTIALS)
        .tokenUri("https://auth.example.test/token")
        .scope("reports.read")
        .build();

Instant now = Instant.now();

OAuth2AccessToken token =
    new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "synthetic-access-token",
        now,
        now.plusSeconds(600),
        Set.of("reports.read"));

OAuth2AuthorizedClient client =
    new OAuth2AuthorizedClient(
        registration, "reports-batch", token);

var principal =
    new TestingAuthenticationToken(
        "reports-batch", "not-a-real-password");

service.saveAuthorizedClient(client, principal);

OAuth2AuthorizedClient loaded =
    service.loadAuthorizedClient(
        "reports-machine", "reports-batch");
```

`service` trong đoạn này là `OAuth2AuthorizedClientService` đã được cấu hình ở test context, ví dụ `JdbcOAuth2AuthorizedClientService` hoặc custom encrypted service.

**Không sử dụng token fixture này để gọi API thật.** Nó là giá trị giả để kiểm tra persistence contract.

### 26.3. JDBC integration test

Với database test container đã migration:
- Insert/save synthetic authorized client;
- Đóng application context/test transaction;
- Khởi tạo service khác cùng database;
- Load lại record;
- Xác minh decrypt/deserialize thành công;
- Test cleanup/removal;
- Test lỗi khi registration đã bị xóa khỏi `ClientRegistrationRepository`;
- Test migration schema version.

**Nếu mục tiêu là kiểm tra encryption**, assert raw database token bytes **không chứa** `synthetic-access-token` và ciphertext khác plaintext; đồng thời verify auth tag/AAD tampering bị từ chối. Đừng dump binary ra test logs.

### 26.4. Backup restore rehearsal

Một test drill phải xác minh:
1. Database snapshot artifact tồn tại và có checksum;
2. KMS/key version còn đủ để decrypt;
3. Restore ở isolated namespace/cluster;
4. Application/schema migrations tương thích;
5. Synthetic token records round-trip;
6. Restore không tái kích hoạt deleted principals;
7. Stale refresh tokens bị quarantine/discard theo policy;
8. Logs không chứa token/secret;
9. Backup access bị audit;
10. RPO/RTO đo được.

### 26.5. Tampering tests

- Thay ciphertext byte → decrypt/authentication tag failure;
- Copy ciphertext sang registration khác → AAD mismatch;
- Copy token của Tenant A sang Tenant B → từ chối;
- Dùng key version không còn hợp lệ → có explicit failure/recovery;
- Replay old encrypted record version → storage/version policy chặn nếu thiết kế hỗ trợ.

Không fallback “nếu decrypt lỗi thì coi ciphertext là plaintext”. Đây là credential exposure/logic bypass nguy hiểm.

---

## 27. Kiểm thử refresh token rotation và stale restore

Một test provider giả có state:

```text
AS token-state:
  current_refresh_token = R1
  R1 valid

Client DB:
  R1

Backup:
  R1

First refresh:
  R1 -> access A2 + refresh R2
  AS marks R1 used
  DB saves R2

Restore old backup:
  DB now R1

Attempt refresh R1:
  AS -> invalid_grant
  possible token-family reuse action
```

### 27.1. Những asserts quan trọng

| Scenario | Expected |
| --- | --- |
| Refresh R1 lần đầu | R2 lưu trong storage sau success |
| Refresh R1 lần thứ hai | AS từ chối |
| Restore R1 khi AS đã dùng R2 | Không tự gửi R1 hàng loạt |
| Invalid_grant | Local stale record removed/quarantined, không infinite retry |
| Hai replicas refresh đồng thời | No cross-user/token mix-up; CAS/lock behavior rõ |
| User disconnected trước snapshot restore | Tombstone loại record |
| AS outage khi restore | Không coi outage là consent revoked nếu không có evidence |
| Client_credentials token hết hạn | Xin token mới bằng client credentials |

### 27.2. Dùng mock AS chứ không dùng production token

Không kiểm thử replay bằng refresh token thật của user. Việc thử dùng token đã rotate có thể khiến AS revoke token family đang hoạt động.

### 27.3. Không trộn invalid_grant với HTTP downstream 401

`invalid_grant` thường là lỗi tại **token endpoint**, liên quan grant/code/refresh token. HTTP 401 `invalid_token` thường từ **Resource Server**. Hai lỗi có failure handlers và remediation khác nhau.

---

## 28. Một deletion workflow có thể kiểm thử

Giả sử user chọn **Disconnect Calendar**.

```text
POST /settings/integrations/calendar/disconnect
  |
  v
Authenticated user + tenant policy
  |
  v
Resolve trusted principal key + calendar registration
  |
  v
Mark disconnected in durable ledger
  |
  v
Cancel new API jobs for calendar
  |
  v
Attempt remote token revocation if supported
  |
  v
Delete local authorized-client record
  |
  v
Invalidate caches / replicas
  |
  v
Acknowledge local disconnect state
```

### 28.1. Các test cases

- User A chỉ xóa token của A;
- User A không được xóa token của B;
- Tenant A không thể xóa token của Tenant B;
- Xóa Calendar không xóa Company login;
- AS revocation 503 được ghi durable pending nếu policy cần retry;
- Local token không được dùng sau khi disconnected;
- Backup restore không hồi sinh record đã disconnected;
- Audit events không chứa raw token;
- API idempotent khi user bấm Disconnect hai lần.

### 28.2. Idempotent deletion

`removeAuthorizedClient(registrationId, principalName)` gọi lần hai khi record đã mất nên được xử lý như một thao tác idempotent trong domain layer nếu yêu cầu. Nhưng đừng tự kết luận AS revocation call đã thành công chỉ vì local delete trả về không lỗi.

### 28.3. Token status và privacy status khác nhau

Một token có thể còn hợp lệ tại AS nhưng user đã disconnect ở RP. **Domain disconnected flag phải chặn local use** ngay, không dựa vào việc AS token đã expire hay chưa.

---

## 29. Runbook bảo vệ data exports và môi trường test

### 29.1. Cấm direct production DB clone chứa tokens

Một anti-pattern:

```text
pg_dump production
  -> import into dev database
  -> all refresh tokens copied to low-security environment
```

Thay thế:
- Synthetic token data;
- Script sanitization chạy **trong security boundary production** trước khi export;
- Drop hoặc replace token columns;
- Loại bỏ client secrets và PII không cần thiết;
- Dùng test principals/registrations;
- Xác minh không có WAL/snapshot phụ chứa plaintext credentials trong export package.

### 29.2. Sanitize dữ liệu nhưng giữ schema

Một test dataset có thể cần:
- Số lượng records;
- Scope distribution đã ẩn danh;
- Token issuedAt/expiresAt giả;
- Registration IDs giả;
- Principal keys giả;
- Các trạng thái expired/revoked/corrupt.

Không cần access/refresh token thật để kiểm thử retention hoặc indexing.

### 29.3. Không để test environment gọi AS/RS production

Ngay cả khi token đã sanitize, ClientRegistration có thể còn token URI production. Cần:
- Test registration endpoints allowlisted;
- Network egress restrictions;
- Secret test-only;
- Explicit profiles;
- Tests fail nếu token URI trỏ production host.

---

## 30. Monitoring và cảnh báo vận hành

Các nhóm chỉ số:

| Chỉ số | Ý nghĩa | Phản ứng |
| --- | --- | --- |
| Authorized client load miss rate | Cache không tìm thấy token | Xem expected reauth vs storage outage |
| DB read/write errors | Persistence unavailable | Retry/backoff hạn chế, incident |
| KMS decrypt failures | Key/format/tampering issue | High-severity alert, fail closed |
| Refresh invalid_grant spike | Stale tokens, rotation race, AS policy | Quarantine, điều tra refresh concurrency |
| User reauthorization rate | UX bị tác động sau restore/retention | Capacity/UX review |
| Backup job failures | RPO có nguy cơ bị vượt | Restore readiness alert |
| Backup restore drill failures | RTO không chắc chắn | Không công bố DR-ready khi chưa thành công |
| Backup vault access anomalies | Có thể xảy ra credential exfiltration | Security incident |
| Growth of expired rows | Cleanup/retention job lỗi | Kiểm tra deletion policy và jobs |
| Deletion ledger replay lag | Restore có nguy cơ hồi sinh record | Block resume đến khi catch up |
| Token issuance rate tăng đột biến | Cache miss/cluster refresh race | Manager principal/cache analysis |

### 30.1. Không đưa raw tokens vào metrics

Sai:

```text
authorized_client_cache_entries{token="eyJhbGci..."} 1
```

Đúng:

```text
authorized_client_cache_entries{registration="company",state="active"} 1234
```

Chỉ dùng labels đã allowlist và không chứa PII/secret.

### 30.2. Phân biệt backup success với restore success

```text
backup_created_total{result="success"} 1
restore_drill_total{result="failure_key_unavailable"} 1
```

Một snapshot thành công nhưng không giải mã được thì không đạt mục tiêu DR. Nên có định kỳ **restore rehearsal**, không chỉ giám sát backup job exit code.

---

## 31. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
| --- | --- |
| “Access token đã hết hạn nên backup token luôn vô hại” | Snapshot có thể còn refresh token hoặc dữ liệu định danh |
| “BLOB trong JDBC nghĩa là đã encrypt” | BLOB/BYTEA là kiểu binary storage, không phải encryption |
| “TDE đã bật nên DBA không thể SELECT token” | TDE không ngăn SQL reader có quyền |
| “Backup encrypted là đủ” | Còn key custody, restore integrity, IAM và token rotation |
| “Restore R1 sẽ dùng lại được như ngày backup” | AS có thể đã rotate/revoke R1 |
| “Nếu invalid_grant thì cứ retry” | Có thể kích hoạt reuse detection và tăng outage |
| “ClientCredentials cũng cần backup refresh token” | Grant này thường không cấp refresh token; token xin lại được |
| “Logout luôn xóa OAuth2AuthorizedClient” | Phụ thuộc repository/service và business policy |
| “removeAuthorizedClient tự revoke tại AS” | Nó chỉ xóa local record |
| “Xóa DB row là xóa khỏi mọi backups” | WAL/snapshots/exports còn trong retention window |
| “Mọi user dùng được key principalName giống email” | Cần issuer/tenant/account linking isolation |
| “Một shared database tự ngăn refresh race” | Cần atomicity/locking/CAS nếu AS rotation policy đòi |
| “Có scope đúng là token hợp lệ cho mọi API” | Phải kiểm audience/issuer/signature/expiry nữa |
| “Application encryption thay IAM được” | App compromise có thể lấy token và key, cần defense in depth |
| “Hash token rồi lưu thay token value” | Hash một chiều không thể dùng để gọi API/refresh |
| “Nếu decrypt fail cứ fallback đọc plaintext” | Đây là fail-open và có thể lộ credentials |
| “Chỉ test SQL insert là đã test DR” | Cần restore/key/deletion/rotation drills |
| “Backup giữ càng lâu càng tốt” | Giữ lâu tăng attack surface và nghĩa vụ xử lý dữ liệu |
| “Cloud snapshot không ai đọc được” | Cần hiểu encryption, access grants, copies và audit |
| “Có thể dùng production refresh token để thử restore” | Rủi ro khiến token family bị revoke và lộ dữ liệu thật |

---

## 32. Bài tập tình huống

### Bài 1 — Service chỉ dùng client_credentials

Một worker định kỳ gọi Reports API và có thể xin token mới từ AS.

**Nên backup token cache không?**

> Có thể chọn **không backup access-token cache** nếu chấp nhận reauthorization và AS capacity phù hợp. Backup nghiệp vụ vẫn cần được bảo vệ riêng.

### Bài 2 — User-delegated refresh token

Một web portal cần user giữ kết nối Calendar qua nhiều tuần.

**Bảo vệ gì?**

> Mã hóa refresh token at rest, IAM/backup encryption, retention policy, revocation/unlink workflow, key lifecycle và restore handling cho rotation.

### Bài 3 — Mã hóa database volume đã bật

DBA vẫn có quyền `SELECT refresh_token_value` và thấy token bytes đọc được.

**Đúng hay sai kỳ vọng?**

> Đúng theo threat model của TDE: disk encryption không tự ngăn database reader. Cần least privilege và application-level token encryption nếu yêu cầu bảo vệ trước SQL reader.

### Bài 4 — Restore token R1 đã rotate

AS đã cấp R2; DB được restore từ snapshot R1.

**Có nên thử refresh R1 ngay?**

> Không nên làm hàng loạt. Có thể gây `invalid_grant`/reuse detection. Cần quarantine/reconcile hoặc bỏ token và reauthorize.

### Bài 5 — Access token expired nhưng refresh còn valid

Cleanup SQL xóa mọi row có `access_token_expires_at < now()`.

**Vấn đề?**

> Sẽ xóa cả refresh tokens có thể còn hợp lệ, gây re-login không cần thiết. Retention phải xét vòng đời authorized-client/grant, không chỉ access token.

### Bài 6 — User disconnect nhưng backup cũ còn token

Sau restore, user thấy liên kết đã xóa xuất hiện lại.

**Nguyên nhân?**

> Restore không replay deletion/revocation events. Cần tombstones/ledger và block token use trước khi restore cleanup.

### Bài 7 — KMS key-v2 bị xóa

Backup tháng trước dùng key-v2, ứng dụng hiện chỉ có key-v4.

**Kết quả?**

> Có thể không decrypt được backup cũ. Cần key retention hoặc chủ đích bỏ/re-authorize token; DR plan phải mô tả rõ.

### Bài 8 — Copy token ciphertext sang tenant khác

Một actor sao chép ciphertext của Tenant A vào row Tenant B.

**Điều gì giúp phát hiện?**

> AEAD integrity + AAD ràng buộc tenant/registration/principal. Ngoài ra storage authorization phải ngăn cross-tenant reads/writes.

### Bài 9 — Hai node cùng refresh R1

Node A lưu R2, node B dùng lại R1 rồi bị `invalid_grant`.

**Bài học?**

> Shared DB chưa đủ; cần per-key concurrency control/optimistic locking và retry logic không reuse stale refresh token.

### Bài 10 — Xóa `OAuth2AuthorizedClient` rồi nghĩ đã revoke grant

**Sai ở đâu?**

> `removeAuthorizedClient` xóa local copy; AS có thể vẫn công nhận token. Cần tích hợp revocation endpoint khi policy yêu cầu và được hỗ trợ.

### Bài 11 — Mất backup access token, không mất business records

Ứng dụng chỉ hỗ trợ `client_credentials`.

**Chiến lược khôi phục?**

> Reacquire machine tokens sau khi AS available; không cần phục hồi historical tokens nếu token cache là disposable.

### Bài 12 — Token chứa PII trong JWT payload

Admin nói “JWT đã ký nên nội dung không đọc được”.

**Đánh giá?**

> Sai. Chữ ký bảo vệ integrity, không tự mã hóa claims. JWT có thể được decode nếu không dùng encryption.

### Bài 13 — Token storage encrypt nhưng logs in token value

**Rủi ro?**

> Token vẫn có thể lộ qua APM/log retention. Cần redaction ở mọi tầng.

### Bài 14 — Principal key là email

Một email được dùng bởi account từ hai issuers.

**Rủi ro?**

> Cross-provider identity collision/cross-tenant token access. Cần `(issuer, sub)` hoặc internal principal key được xác minh.

### Bài 15 — Backup được tải xuống laptop để debug

**Đánh giá?**

> Không phù hợp với security policy thông thường cho credential-bearing data. Dùng sanitized synthetic dataset và controlled isolated restore.

### Bài 16 — User logout RP nhưng Calendar vẫn sync

**Có chắc là bug?**

> Không thể kết luận chỉ từ logout. Cần xác định nghiệp vụ muốn disconnect/revoke hay chỉ kết thúc browser session. Nếu chính sách quy định logout phải ngừng sync, phải triển khai explicit lifecycle deletion/revocation.

### Bài 17 — Key và encrypted backup cùng một IAM role

**Rủi ro?**

> Compromise một role có thể đủ để tải và giải mã toàn bộ tokens. Nên tách quyền và audit.

### Bài 18 — Backup job thành công, restore drill không decrypt được

**Hệ thống DR-ready chưa?**

> Chưa. Backup success không chứng minh restoration success. Cần kiểm tra key lifecycle và restoration tests.

### Bài 19 — Retention 30 ngày theo yêu cầu từ product

**Có thể tự áp dụng cho mọi token không?**

> Không. Cần đánh giá loại token, active grants, AS rotation, consent, quyền riêng tư, backups và pháp lý áp dụng. Không dùng một TTL cố định để làm hỏng authorized sessions.

### Bài 20 — Test REST interceptor đã có mã hóa storage chưa?

RestClient gửi đúng Bearer access token; developer cho rằng database đã an toàn.

**Kết luận?**

> Không. Outbound Bearer header test chứng minh token usage, không chứng minh mã hóa JDBC columns, backup encryption hay IAM. Cần storage security integration tests.

---

## 33. Checklist triển khai production

### Phân loại và lưu trữ

1. Đã xác định tất cả nơi lưu `OAuth2AuthorizedClient` chưa?
2. Đã phân biệt service-level storage và HTTP session repository chưa?
3. Có dùng `InMemoryOAuth2AuthorizedClientService` ngoài ý muốn trên nhiều replicas không?
4. Có dùng `JdbcOAuth2AuthorizedClientService` với đúng schema/migration không?
5. Đã phân biệt client registration secrets với authorized-client tokens chưa?
6. Có policy cho user-delegated và machine tokens riêng chưa?
7. Có identity/tenant/issuer key đủ cách ly không?

### Bảo vệ credentials

8. Token value có encryption at rest theo threat model không?
9. Có TLS cho DB/Redis/KMS/AS/RS không?
10. Backup có encryption và IAM độc lập không?
11. Key versions/DEKs/KEKs có lifecycle và audit không?
12. AEAD/AAD có ràng buộc record/tenant/token type không?
13. Không có plaintext fallback khi decryption thất bại?
14. Không ghi token, client secret, session ID vào logs/traces/metrics?
15. Production DB copy đã được sanitization trước khi dùng ở test/dev?

### Backup và restore

16. Đã quyết định có backup token values hay không theo RPO/RTO chưa?
17. Backup có integrity verification và restore rehearsal không?
18. Có diễn tập restore với key version cũ không?
19. Có cơ chế quarantine stale/rotated refresh tokens không?
20. Có hạn chế bulk refresh ngay sau restore không?
21. Có xử lý revoked/deleted users từ ledger sau snapshot không?
22. Có phân biệt backup snapshots và replication không?
23. Có kế hoạch khôi phục khi AS/KMS chưa available không?

### Retention và xóa

24. Retention có tính access vs refresh token lifecycle không?
25. Cleanup có tránh xóa row còn refresh token hợp lệ không?
26. Disconnect/revoke/local delete có semantics rõ chưa?
27. Backup expiry và crypto-erasure policy có được ghi lại không?
28. Có đảm bảo restore không hồi sinh local token đã xóa không?
29. Có test cross-tenant delete/read prevention không?
30. Có document legal/privacy retention obligations phù hợp tổ chức không?

### Concurrency và vận hành

31. Có test simultaneous refresh trên multi-node không?
32. Có CAS/lock/fencing nếu AS rotation đòi hỏi không?
33. Có theo dõi `invalid_grant` spikes và token issuance anomalies không?
34. Có phân biệt downstream 401 với AS refresh failure không?
35. Có quy trình incident response nếu token backup/key bị lộ không?

---

## 34. Sơ đồ quyết định cuối cùng

```text
Bạn đang thiết kế storage cho OAuth2AuthorizedClient?
                    |
                    v
Authorized client là cache có thể tái tạo?
                    |
           +--------+---------+
           |                  |
          YES                NO
           |                  |
           v                  v
Cân nhắc không backup   Cần persistent encrypted store
token values            + backup strategy theo RPO/RTO
           |                  |
           +--------+---------+
                    |
                    v
Data at rest được bảo vệ?
                    |
       +------------+-------------+
       |                          |
      NO                         YES
       |                          |
       v                          v
Implement IAM/TLS/          Backup isolation, KMS,
encryption + redaction      key versions, integrity
                                  |
                                  v
                        Token lifecycle có rotation?
                                  |
                         +--------+--------+
                         |                 |
                        YES               NO
                         |                 |
                         v                 v
                  Quarantine stale     Verify expiry,
                  restored refresh     revocation,
                  tokens               registration
                         |                 |
                         +--------+--------+
                                  |
                                  v
                      Có deleted/revoked grants
                      sau backup timestamp?
                                  |
                         +--------+--------+
                         |                 |
                        YES               NO
                         |                 |
                         v                 v
                   Replay tombstones  Continue controlled
                   /remove rows      recovery
                         |                 |
                         +--------+--------+
                                  |
                                  v
                           Controlled resume
                                  |
                                  v
                       Monitor invalid_grant / 401 /
                       decrypt failures / reauth rate

Nếu không chắc token hợp lệ: không sử dụng mù quáng.
Nếu không chắc record được phép tồn tại: block use trước khi xác minh.
```

### Các nguyên tắc cần nhớ

1. **`OAuth2AuthorizedClient` chứa credentials**, không chỉ là “cache” vô hại.
2. **`OAuth2AuthorizedClientService` và `OAuth2AuthorizedClientRepository` có phạm vi khác nhau**; phải biết dữ liệu thật đang lưu ở đâu.
3. **`JdbcOAuth2AuthorizedClientService` hỗ trợ persistence nhưng không tự đồng nghĩa token được application-encrypted**.
4. **Backup token values là lựa chọn kiến trúc**. Nếu có thể reauthorize, không backup thường giảm attack surface.
5. **Refresh token rotation khiến snapshot cũ có thể chứa token không còn hợp lệ và có rủi ro reuse detection**. Không tự động refresh hàng loạt ngay sau restore.
6. **Access token expiry không quyết định thời hạn tồn tại của refresh token hoặc toàn bộ authorized-client record**.
7. **Local deletion không tự revoke token tại AS, và xóa primary DB không tự xóa immutable backups**.
8. **Revocation/deletion ledger phải được áp dụng khi restore**, nếu không backup có thể hồi sinh các liên kết đã bị xóa.
9. **Application-level AEAD encryption, backup encryption, KMS/IAM và TLS bổ sung cho nhau**, không thay thế lẫn nhau.
10. **Tenant/issuer/principal isolation và concurrency control** phải được thiết kế cho storage/key/cache, không trông chờ default schema giải quyết hết.
11. **Test restore, encryption/key rotation, retention và invalid_grant** mới chứng minh phương án vận hành hiệu quả; backup job success chỉ là điều kiện cần.
12. **Khi thiếu chắc chắn về quyền hoặc hiệu lực của credential, fail closed và yêu cầu reauthorization** thay vì dùng token cũ hoặc nới security.

### Tài liệu tham khảo

- [Spring Security 6.5 — OAuth2 Client Core Interfaces](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/core.html)
- [Spring Security 6.5 — OAuth2 Client Authorized Clients](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/authorized-clients.html)
- [Spring Security 6.5 — Security Database Schema / OAuth2 Client](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html)
- [Spring Security 6.5 — JdbcOAuth2AuthorizedClientService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/JdbcOAuth2AuthorizedClientService.html)
- [Spring Security 6.5 — AuthorizedClientServiceOAuth2AuthorizedClientManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html)
- [Spring Security 6.5 — Reactive OAuth2 Client Core](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 8705 — OAuth2 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth2 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [NIST SP 800-57 Part 1 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)
- [NIST SP 800-53 Rev. 5 — Security and Privacy Controls](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)
