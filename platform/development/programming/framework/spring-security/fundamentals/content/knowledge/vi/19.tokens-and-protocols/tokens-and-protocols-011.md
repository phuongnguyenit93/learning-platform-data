# API key và giới hạn khi dùng một khóa để đại diện cho ứng dụng hoặc người dùng

> **Module:** Spring Security – fundamentals  
> **Nhóm kiến thức:** Token và giao thức  
> **Trọng tâm:** API key là credential nhận diện một client, integration hoặc workload ở mức nào; vì sao nó thường **không đủ để đại diện cho người dùng cuối**; và cách thiết kế authentication, authorization, phạm vi quyền, quản lý khóa và kiểm thử khi tích hợp Spring Security.

## 1. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Giải thích API key là gì, khác session cookie, HTTP Basic password, OAuth2 access token và JWT ra sao.
2. Phân biệt **credential**, **client identity**, **user identity**, **tenant**, **scope/authority** và **quyền trên từng tài nguyên**.
3. Chỉ ra điều mà một API key hợp lệ **chứng minh được** và điều nó **không chứng minh được**.
4. Nhận diện rủi ro khi một khóa dùng chung giữa nhiều ứng dụng, nhân viên, thiết bị hoặc khách hàng: mất truy vết, quyền quá rộng và khó thu hồi.
5. Thiết kế key có entropy cao, tách secret khỏi key ID, lưu hash, đặt hạn sử dụng, phân quyền tối thiểu, rate limit, audit và rotation.
6. Hiểu cách tích hợp API key vào Spring Security bằng một **custom authentication filter**, tạo `Authentication` có principal và authorities rõ ràng, rồi kiểm tra authorization ở HTTP và domain layer.
7. Chạy ví dụ Java 17+ và kiểm thử key hợp lệ, không hợp lệ, thiếu quyền, tenant khác và request không có key.

## 2. API key là gì?

**API key** là một chuỗi bí mật hoặc một credential do dịch vụ cấp cho bên gọi API. Bên gọi trình key trong mỗi request theo giao thức đã thỏa thuận, thường qua HTTP header. Dịch vụ đối chiếu key với bản ghi cấu hình hoặc kho khóa để xác định **client nào đang gọi**, plan/quota nào áp dụng và những thao tác được cho phép.

Ví dụ:

~~~http
GET /api/records/101 HTTP/1.1
Host: api.example.test
X-API-Key: <secret-api-key>
~~~

`<secret-api-key>` chỉ là ký hiệu minh họa, không phải khóa thực. **Không đưa key vào URL query string** vì URL dễ bị ghi lại trong proxy logs, browser history, analytics, referer hoặc hệ thống theo dõi. Ưu tiên header hoặc cơ chế credential chuẩn mà nhà cung cấp API chỉ định.

API key có thể được dùng cho:

- Xác định một service-to-service integration, ví dụ dịch vụ báo cáo gọi API nội bộ.
- Gắn khách hàng/đối tác với mức quota hoặc gói thương mại.
- Tách quyền theo workload, project, environment hoặc tenant.
- Giám sát lượng truy cập theo client và chủ động thu hồi khi bị lộ.
- Xác thực máy–máy đơn giản khi rủi ro/phạm vi phù hợp.

**API key không tự thân là hệ thống đăng nhập người dùng**. Một backend nhận key có thể nhận ra “request được gửi với credential cấp cho integration A”; nó **không mặc nhiên biết** “người dùng cuối tên Alice đã bấm nút này” hoặc “Alice đồng ý cho integration A hành động thay mình”.

### Cách suy luận chính xác

~~~text
Request gửi key K
    |
    v
Server xác minh K hợp lệ, chưa hết hạn/chưa bị thu hồi
    |
    v
Server tra metadata:
  clientId    = reporting-job
  tenantId    = north
  authorities = [RECORD_READ]
    |
    v
Authentication: principal = client:reporting-job
    |
    v
Authorization: client có RECORD_READ?
               bản ghi có thuộc tenant north?
    |
    v
ALLOW hoặc DENY
~~~

Trong ví dụ này, principal là **service account/client identity**, không phải con người. Dù API key do một nhân viên tạo, sử dụng key đó không chứng minh nhân viên ấy chính là người phát lệnh hiện tại.

## 3. API key chứng minh được gì, không chứng minh được gì?

### Có thể chứng minh (nếu được thiết kế đúng)

Một request sở hữu một key hợp lệ cho thấy phía gửi **đang có khả năng sử dụng credential** đã phát cho client hoặc workload xác định. Sau khi đối chiếu server-side, backend có thể biết:

- `clientId` hoặc `serviceAccountId` gắn với key;
- tenant/project/environment được cấp;
- trạng thái key: active, disabled, revoked, expired;
- phạm vi quyền cấp cho credential;
- quota, rate limit và chính sách vận hành liên quan.

Những điều này phụ thuộc **server có lưu metadata và kiểm tra thật sự**. Một chuỗi ngẫu nhiên không có associated policy không tự mang đầy đủ những khả năng trên.

### Không chứng minh được chỉ từ key

1. **Ai là người trực tiếp thao tác?** Nhiều nhân viên có thể cùng biết một key.
2. **Ứng dụng nào đang thực thi?** Một key bị sao chép có thể được dùng bởi chương trình khác hoặc kẻ tấn công.
3. **Người dùng cuối đã xác thực chưa?** Key cấp cho backend không chứa quá trình người dùng login.
4. **Người dùng có đồng ý ủy quyền không?** Sở hữu key không chứng minh có user consent.
5. **Được truy cập mọi bản ghi trong cùng tổ chức không?** Client có `RECORD_READ` vẫn có thể bị giới hạn tenant, owner, classification hoặc mục đích xử lý.
6. **Request có toàn vẹn hoặc chống replay không?** API key gửi nguyên giá trị là bearer secret; kẻ có được key có thể thử dùng lại.
7. **Người gửi có quyền hành động nhân danh user trong thời điểm này không?** Account bị khóa, user bị thu hồi quyền hoặc giao dịch cần MFA vẫn là những điều kiện độc lập.

**Câu hỏi cần đặt khi review hệ thống:** “API key này đại diện cho **ứng dụng**, **một service account** hay **một user**? Nguồn đáng tin của khẳng định đó là gì?” Không trả lời rõ thì authorization rất dễ sai.

## 4. Một khóa dùng chung làm mất ranh giới danh tính

Giả sử ứng dụng “Sales Dashboard” có một key chung, được lưu trong code của 30 nhân viên:

~~~text
Employee Alice --+
Employee Bob -----+--> X-API-Key: SALES_TEAM_KEY --> Data API
Employee Carol ---+
~~~

Backend chỉ nhận được cùng credential. Nếu key không kèm cơ chế xác thực user độc lập, API có thể biết key thuộc team Sales nhưng **không biết Alice, Bob hay Carol đang gửi request**.

Hệ quả:

- **Không thể truy vết hành động ở mức người dùng.** Audit log ghi `key_id=sales-team-key` chứ không biết người ra quyết định.
- **Không thu hồi riêng một người.** Bob nghỉ việc, hệ thống phải thay key của cả nhóm hoặc vẫn để Bob dùng bản sao cũ.
- **Không kiểm soát quyền khác nhau.** Alice được đọc tất cả khách hàng, Bob chỉ được đọc khách hàng của mình, nhưng key chung có một policy.
- **Bán kính ảnh hưởng lớn.** Lộ key ở một máy có thể làm mọi dữ liệu trong scope của key bị truy cập.
- **Dễ trở thành “quyền quản trị trá hình”.** API key cấp quyền rộng để tiện tích hợp được dùng thay user authentication.
- **Khó phân biệt abuse với hoạt động thường.** Rate limit, quota và alert theo key trộn lưu lượng của nhiều nguồn.

Giải pháp không chỉ là “thêm header `X-User-Id`” vì client tự có thể điền bất kỳ user ID nào. Cần **xác thực user ở một trust boundary đáng tin**, hoặc dùng token ủy quyền được cấp bởi hệ thống nhận diện/ủy quyền hợp lệ.

### Đối chiếu ba thiết kế

| Thiết kế | Principal đáng tin | Phù hợp cho |
| --- | --- | --- |
| Một API key chung cho cả team | Một client/team, **không phải từng nhân viên** | Ít phù hợp cho thao tác theo quyền người dùng |
| API key riêng cho mỗi integration/workload | Service account của từng workload | Service-to-service, quota, audit theo client |
| User login + OAuth2 delegated access token | User subject và client identity từ issuer tin cậy | Hành động thay người dùng có scopes, consent, expiry |

Có hệ thống cấp **personal API key** cho từng user. Khi đó có thể quy về tài khoản sở hữu key trong database, nhưng vẫn **không chứng minh người đang cầm key chính là user tại thời điểm gọi**. Personal API key thường là credential dài hạn, bị sao chép hoặc chia sẻ; nên có quyền hạn, hạn sống và revoke riêng, không đồng nhất với login có MFA/recent authentication.

## 5. Authentication khác Authorization

- **Authentication:** key có hợp lệ không? Nếu hợp lệ, **client/service account nào** là principal?
- **Authorization:** client đó có quyền gọi action này, với tài nguyên/tenant này, trong trạng thái hiện tại không?

Một lỗi phổ biến:

~~~text
if (apiKeyExists(requestKey)) {
    return repository.findById(requestedId); // nguy hiểm
}
~~~

Key hợp lệ không nghĩa được đọc mọi ID. Nếu `requestedId` thuộc tenant khác, thiếu điều kiện owner/scope/tenant sẽ tạo lỗ hổng **Broken Object Level Authorization (BOLA/IDOR)**.

Thiết kế đúng:

~~~text
verified = credentialStore.verify(requestKey)
if verified invalid/expired/revoked -> deny
if REPORT_READ not in verified.scopes -> deny
record = repository.findByIdAndTenantId(requestedId, verified.tenantId)
if absent -> deny/not found theo policy
return projection được phép
~~~

Pseudocode trên nhấn mạnh kiểm tra nguồn **tenant từ metadata đã xác minh**, không lấy tenant theo một HTTP header do client tự ý sửa. Nếu server cho phép một integration truy cập nhiều tenant, phạm vi đó cũng phải được ràng buộc rõ và audit.

## 6. API key so với các cơ chế xác thực khác

| Cơ chế | Credential trình trong request | Principal thường là | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- | --- |
| API key | Chuỗi bí mật, thường qua custom header | Client/service account, đôi khi user sở hữu key | Đơn giản, dễ cấp cho integration | Không tự có delegation, user consent, chuẩn scope/expiry |
| HTTP Basic | Username/password trong `Authorization` | User hoặc service account | Chuẩn HTTP đơn giản | Credential dài hạn gửi mỗi request, phải dùng TLS |
| Cookie + server session | Session ID | User từ session server | Browser-friendly, revoke session | Cần quản lý session, cookie/CSRF |
| OAuth2 client credentials | Access token từ authorization server | Client application/service account | Cơ chế cấp token, scope, lifetime, policy tập trung | **Không có user cuối** trong client credentials flow |
| OAuth2 delegated access token | Access token có user subject/client context theo issuer | User + client được ủy quyền | Phù hợp user consent, audience/scopes/expiry | Cần AS/resource server và validation chuẩn |
| JWT | Định dạng token JSON có chữ ký/MAC | Tùy claims/issuer | Có thể validate offline theo thiết kế | JWT là **format**, không tự chứng minh đúng quyền/issuer/audience |
| mTLS client certificate | Chứng chỉ client trong TLS handshake | Client/workload đã cấp chứng chỉ | Ràng buộc tới private key/cert, quản lý identity máy | Vận hành PKI, rotation, proxy/trust chain |

**OAuth2 client credentials cũng không phải user delegation.** Nó có thể phù hợp hơn key tĩnh nếu cần access token ngắn hạn, issuer/audience/scopes và rotation. Muốn làm “thay mặt Alice”, cần luồng đăng nhập và ủy quyền user có căn cứ, không đơn giản cấp một key có tên Alice.

API key thường là bearer credential: ai giữ được key dùng được trong phạm vi của key. Đừng gọi một chuỗi tự chế là `Authorization: Bearer` rồi mặc nhiên coi nó đáp ứng toàn bộ chuẩn OAuth2; phải xác định rõ validator và semantics.

## 7. Nguyên tắc thiết kế credential API key

### 7.1. Tạo key đủ entropy

Secret phải sinh từ **cryptographically secure random number generator** (CSPRNG), không phải username, timestamp hoặc UUID dự đoán theo mô hình không phù hợp. Với key server-to-server, có thể sinh 32 byte ngẫu nhiên (256 bit) rồi encode bằng hex hoặc base64url.

Ví dụ shell minh họa:

~~~bash
openssl rand -hex 32
~~~

Lệnh in một key ngẫu nhiên trên stdout. **Không copy key thực vào tài liệu, chat hoặc source code**. Hãy lưu ở secret manager phù hợp; nếu tạo trên máy thật cần cân nhắc shell history, terminal recording và clipboard.

### 7.2. Phân biệt public key ID và secret

Thiết kế phổ biến:

~~~text
ak_live_<public_key_id>_<random_secret>
~~~

Đây là **format ý tưởng**, không phải tiêu chuẩn chung. `public_key_id` giúp server tìm bản ghi nhanh; `random_secret` là phần cần giữ bí mật. Không biến key ID thành secret.

Kho metadata ví dụ:

~~~text
key_id       = k_1042
client_id    = orders-worker
tenant_id    = north
environment  = production
scopes       = RECORD_READ
secret_hash  = <digest-or-keyed-digest>
created_at   = ...
expires_at   = ...
revoked_at   = null
last_used_at = ...
~~~

Với token entropy cao, server có thể lưu digest SHA-256 của secret để so sánh, hoặc keyed HMAC digest với server-side pepper theo thiết kế bảo mật. Khóa nhỏ/dễ đoán không thể “cứ hash SHA-256 là an toàn”; phải tăng entropy, kiểm soát rate limit và cân nhắc KDF khi threat model yêu cầu.

**Hiển thị raw key một lần tại lúc cấp**, không cung cấp endpoint “xem lại bí mật cũ” nếu hệ thống không cần. Rotation nên tạo key mới.

### 7.3. Key riêng theo client, environment và mục đích

Không dùng một key production chung cho staging, cron job, mobile app, hệ thống đối tác và nhân viên. Mỗi workload nên có identity độc lập để revoke và audit.

Một quy tắc đặt tên:

~~~text
client:inventory-sync-prod
client:analytics-export-staging
client:crm-partner-42
~~~

Tên là public metadata, không phải secret. Dùng quyền `INVENTORY_READ` hoặc `REPORT_EXPORT` cụ thể. Không mặc định key cấp cho service account có `ROLE_ADMIN`.

### 7.4. Scope, tenant, resource, quota

Cấp quyền **least privilege**:

~~~text
Key K1: client=report-bot, tenant=north, scopes=[RECORD_READ]
Key K2: client=inventory-sync, tenant=south, scopes=[STOCK_READ, STOCK_UPDATE]
Key K3: client=billing-reconcile, scopes=[INVOICE_RECONCILE], no human access
~~~

Ngoài quyền theo route, cần resource-level check: nếu key K1 gọi `/api/records/201` thuộc tenant `south`, phải từ chối ngay cả khi K1 có `RECORD_READ`.

Rate limit/quota nên tính theo client/key và phối hợp IP, tenant, endpoint cost, concurrency. Nó giảm abuse nhưng **không thay authentication hay authorization**. Request quá ngưỡng có thể trả `429 Too Many Requests` theo policy; không phải `401` hoặc `403`.

### 7.5. Hạn dùng, revoke, rotation

Mỗi key nên có vòng đời:

~~~text
CREATED -> ACTIVE -> ROTATING -> REVOKED / EXPIRED
~~~

Quy trình rotation an toàn:

1. Cấp key mới với phạm vi tương đương/tối thiểu.
2. Phân phối qua secret manager hoặc kênh bảo mật.
3. Triển khai caller dùng key mới.
4. Giám sát logs/metrics theo key ID (không log secret).
5. Thu hồi key cũ sau thời gian chồng lấp cần thiết.
6. Xác minh key cũ bị từ chối.

Khi nghi bị lộ, cần khả năng **revoke ngay** và điều tra scope tác động. Không kỳ vọng chỉ xóa key khỏi Git history sẽ làm credential đã lộ mất hiệu lực. Với cached verification, phải có cơ chế invalidation/TTL đủ ngắn để thu hồi có hiệu lực theo mục tiêu bảo mật.

### 7.6. Lưu và truyền an toàn

- TLS bắt buộc; key trong plaintext HTTP có thể bị lộ trên đường truyền.
- Đưa vào `X-API-Key` hoặc `Authorization` theo contract, **không** query string.
- Không log header chứa key, không ghi vào APM traces, analytics, screenshots, bug reports.
- Tránh hardcode key trong ứng dụng mobile/SPA phân phối cho người dùng cuối: ai có file/app đều có khả năng trích xuất key.
- Dùng secret manager, workload identity, environment injection hoặc cơ chế cấp credential phù hợp.
- Không tin `X-User-Id`, `X-Tenant-Id` từ Internet như bằng chứng đã xác thực. Chỉ tin identity đã xác minh hoặc headers do proxy tin cậy ký/thiết lập qua trust boundary rõ.
- Cân nhắc mTLS, IP restrictions, signed requests có timestamp/nonce, short-lived tokens khi rủi ro replay cao; mỗi biện pháp có yêu cầu triển khai riêng.

## 8. Ma trận lỗi thiết kế thường gặp

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Một key chung cho toàn bộ công ty | Không tách client/user, khó revoke | Mỗi workload/đối tác/tenant dùng key riêng |
| Đặt user ID trong header và tin nó | Caller có thể giả mạo người dùng | Dùng user authentication/delegation đáng tin |
| Key hợp lệ nghĩa đọc mọi tài nguyên | BOLA/IDOR, cross-tenant disclosure | Kiểm tra scope + tenant + object-level authorization |
| Key trong URL/query string | URL thường bị log/ghi lịch sử | Dùng header, mask secrets trong logs |
| Key trong JS browser/mobile app | Credential có thể bị trích xuất | Backend proxy hoặc user-based auth flow |
| Không expiry/revoke | Key mất là bị lạm dụng kéo dài | Lifecycle, revoke, rotation |
| Key ngắn/dễ đoán | Brute force/guessing | CSPRNG entropy cao |
| Chỉ hash key yếu rồi nghĩ an toàn | Hash không tăng entropy của secret | Generate key đủ mạnh, rate limit |
| So sánh secret bằng xử lý chuỗi tùy tiện | Có thể lộ qua timing/logic | So sánh digest constant-time phù hợp |
| Ghi raw key vào log | Tăng xác suất bị chiếm quyền | Redact, log key ID và metadata đã kiểm soát |
| Không rate limit/quota | Key hợp lệ có thể đốt tài nguyên | Limits theo key, tenant, endpoint cost |
| Coi key là MFA hoặc xác thực người thật | Thiếu proof-of-user | Login/step-up khi cần |
| Trả lỗi phân biệt quá chi tiết | Lộ trạng thái key/username | Error contract không tiết lộ secret details |
| Toàn bộ quyền là ADMIN | Blast radius lớn | Least privilege, explicit scopes |
| Cache key revoked quá lâu | Token cũ tiếp tục được chấp nhận | Revocation propagation/short TTL |
| Lấy client ID từ body thay vì từ key | Đổi danh tính dễ dàng | Principal từ credential đã xác minh |

## 9. Tích hợp với Spring Security: không có “quyền user thần kỳ” từ key

Trong Spring Security Servlet, authorization dựa trên `Authentication`, thường chứa:

- `principal`: identity đã xác minh, ở đây là client/service account;
- `authorities`: quyền được cấp cho identity;
- `credentials`: secret nhận được trong request; **không nên giữ raw key sau khi xác minh**;
- `isAuthenticated`: trạng thái xác thực.

Tích hợp API key thường cần một authentication mechanism rõ ràng, ví dụ custom filter hoặc `AuthenticationFilter` + `AuthenticationConverter` + `AuthenticationProvider`, thay vì đoán Spring Security tự hiểu mọi header `X-API-Key`.

Luồng:

~~~text
HTTP GET /api/records/101
  X-API-Key: <secret>
      |
      v
ApiKeyAuthFilter (Servlet)
      |
      +-- missing --> chưa có Authentication --> rule yêu cầu login --> 401
      |
      +-- invalid/expired/revoked --> 401, không chạy controller
      |
      +-- valid --> ApiPrincipal(clientId, tenantId)
                   authorities=[RECORD_READ]
                         |
                         v
                SecurityContextHolder
                         |
                         v
                AuthorizationFilter:
                hasAuthority("RECORD_READ")?
                         |
                         v
                Controller / Service / Repository:
                record.tenantId == principal.tenantId?
                         |
                    allow / deny
~~~

**Chú ý:** Authentication xảy ra trước, authorization sau. `hasAuthority("RECORD_READ")` chỉ kiểm tra action-level permission; ranh giới tenant/owner thực tế vẫn phải kiểm soát tại domain/data layer.

## 10. Demo Java 17+ chạy được với Spring Boot 3.5.x

Ứng dụng demo nhận **một API key riêng cho service `client:reporting-job`** thuộc tenant `north`, có duy nhất `RECORD_READ`. Dùng HTTP header `X-API-Key`. Demo cố ý không có user login, giúp thấy rõ key nhận diện **client**, không phải nhân viên.

Hành vi:

- `GET /api/public`: ai cũng có thể truy cập.
- `GET /api/whoami`: cần key hợp lệ, trả về client ID + tenant đã xác minh.
- `GET /api/records/101`: key hợp lệ và scope `RECORD_READ` đọc được bản ghi tenant north.
- `GET /api/records/201`: key hợp lệ nhưng khác tenant south nên không tìm thấy trong scope (404 theo policy demo).
- `POST /api/records`: key chỉ có quyền đọc, trả 403.
- Key thiếu/sai: truy cập protected endpoint trả 401.

**Cảnh báo:** Mẫu này dùng một key trong environment để minh họa đường đi authentication. Nó **không phải hệ quản trị key production**: chưa có database nhiều key, revoke động, quota, audit, key prefix rotation hoặc mTLS. Những phần đó được giải thích ở các mục tiếp theo.

### 10.1. Cấu trúc dự án

~~~text
api-key-demo/
  pom.xml
  src/main/java/com/example/apikey/
    ApiKeyDemoApplication.java
    ApiPrincipal.java
    ApiKeyRegistry.java
    ApiKeyAuthFilter.java
    SecurityConfig.java
    ApiRecordStore.java
    ApiController.java
  src/test/java/com/example/apikey/
    ApiKeySecurityTests.java
~~~

Cần **JDK 17+**, **Maven 3.9+**, Spring Boot **3.5.7** (Servlet/Spring MVC). Ví dụ API của Spring Security dòng 6.5; khi nâng Spring Boot/Spring Security, đọc migration guide của version đích.

### 10.2. File pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>api-key-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
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
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
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

### 10.3. File ApiKeyDemoApplication.java

~~~java
package com.example.apikey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiKeyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiKeyDemoApplication.class, args);
    }
}
~~~

### 10.4. File ApiPrincipal.java

~~~java
package com.example.apikey;

import java.security.Principal;

public record ApiPrincipal(String clientId, String tenantId)
        implements Principal {

    @Override
    public String getName() {
        return clientId;
    }
}
~~~

Vì `ApiPrincipal` implement `Principal`, `Authentication.getName()` sẽ phản ánh client ID; nó **không phải username**. Tenant ID ở đây chỉ đến từ key registry đáng tin.

### 10.5. File ApiKeyRegistry.java

~~~java
package com.example.apikey;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Optional;
import java.util.Set;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ApiKeyRegistry {

    public record KeyIdentity(
        String clientId,
        String tenantId,
        Set<String> authorities
    ) {}

    private final byte[] expectedDigest;

    public ApiKeyRegistry(Environment environment) {
        String key = environment.getProperty("DEMO_API_KEY");

        if (key == null || key.length() < 24) {
            throw new IllegalStateException(
                "Set DEMO_API_KEY to a random 24+ character demo secret"
            );
        }
        this.expectedDigest = sha256(key);
    }

    public Optional<KeyIdentity> verify(String candidate) {
        if (candidate == null
                || candidate.isBlank()
                || candidate.length() > 512) {
            return Optional.empty();
        }

        byte[] receivedDigest = sha256(candidate);
        if (!MessageDigest.isEqual(expectedDigest, receivedDigest)) {
            return Optional.empty();
        }

        return Optional.of(new KeyIdentity(
            "client:reporting-job",
            "north",
            Set.of("RECORD_READ")
        ));
    }

    private static byte[] sha256(String input) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return digest.digest(input.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

**Giải thích thiết kế:**

- Lấy key qua Spring `Environment` từ biến môi trường `DEMO_API_KEY`; **không hardcode secret trong source**.
- Chỉ giữ SHA-256 digest để so khớp. `MessageDigest.isEqual` dùng so sánh byte arrays giảm nguy cơ so sánh chuỗi chênh lệch timing; nó không bảo đảm mọi nhánh trong luồng verification là constant-time tuyệt đối.
- Demo chỉ có **một key** và không hỗ trợ revoke động; metadata của key được khai báo server-side. Production cần key ID/public prefix, registry bền vững, expiry, revocation và scope per key.
- Điều kiện `key.length() >= 24` chỉ kiểm tra **độ dài**, không chứng minh entropy. **Luôn sinh bằng CSPRNG**; key 24 ký tự toàn chữ A vẫn là key yếu.
- Hash SHA-256 hợp lý cho **secret entropy cao được sinh ngẫu nhiên**; nếu key từ password yếu, SHA-256 đơn thuần không chống đoán dictionary hiệu quả.
- Code cố ý không lưu raw candidate trong `Authentication`, response hoặc logs.
- Không có mã gắn user ID vào key; principal là client identity.

### 10.6. File ApiKeyAuthFilter.java

~~~java
package com.example.apikey;

import java.io.IOException;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public class ApiKeyAuthFilter extends OncePerRequestFilter {

    private final ApiKeyRegistry registry;

    public ApiKeyAuthFilter(ApiKeyRegistry registry) {
        this.registry = registry;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {

        String provided = request.getHeader("X-API-Key");

        if (provided == null) {
            // Không tự grant quyền. AuthorizationFilter sẽ yêu cầu
            // Authentication đối với endpoint protected.
            chain.doFilter(request, response);
            return;
        }

        var identity = registry.verify(provided);
        if (identity.isEmpty()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        var client = identity.get();
        var principal = new ApiPrincipal(
            client.clientId(),
            client.tenantId()
        );

        List<SimpleGrantedAuthority> authorities =
            client.authorities().stream()
                .map(SimpleGrantedAuthority::new)
                .toList();

        var authentication = new UsernamePasswordAuthenticationToken(
            principal,
            null,
            authorities
        );

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);

        chain.doFilter(request, response);
    }
}
~~~

Filter này nhận key từ header, xác minh rồi tạo authentication đã được đánh dấu authenticated bằng constructor ba tham số có authorities. Principal là `ApiPrincipal(clientId, tenantId)`.

**Điểm cần lưu ý:**

- Demo không định nghĩa filter là `@Component` hoặc `@Bean`; nó chỉ được tạo bởi security chain ở file tiếp theo. Điều này tránh một filter bị đăng ký đồng thời vào Servlet container và Spring Security chain.
- Không gán `ROLE_USER` hoặc username chỉ vì có API key. Token đại diện service account.
- Khi key sai, filter trả 401. Khi thiếu key, filter cho request tiếp tục để policy `authenticated`/`hasAuthority` xử lý; public path vẫn được phép.
- Servlet security filter chain quản lý việc dọn `SecurityContextHolder` sau request. Nếu viết integration tùy biến hoặc thread/async riêng, phải kiểm tra context propagation/cleanup để không rò principal.
- Đây là filter minh họa, **chưa có chống header trùng lặp, yêu cầu định dạng key cụ thể, replay protection, logging audit, key expiration, rate limit hay error contract chuẩn**. Production cần thêm các biện pháp đó và kiểm thử.

### 10.7. File SecurityConfig.java

~~~java
package com.example.apikey;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            ApiKeyRegistry registry
    ) throws Exception {
        http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((request, response, ex) ->
                    response.sendError(
                        HttpServletResponse.SC_UNAUTHORIZED))
                .accessDeniedHandler((request, response, ex) ->
                    response.sendError(
                        HttpServletResponse.SC_FORBIDDEN)))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/whoami")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/records/**")
                    .hasAuthority("RECORD_READ")
                .requestMatchers(HttpMethod.POST, "/api/records")
                    .hasAuthority("RECORD_WRITE")
                .anyRequest().denyAll());

        http.addFilterBefore(
            new ApiKeyAuthFilter(registry),
            UsernamePasswordAuthenticationFilter.class
        );

        return http.build();
    }
}
~~~

**Tại sao như vậy?**

- `securityMatcher("/api/**")` giới hạn chain minh họa chỉ cho API. Trong sản phẩm thật có các URL khác, cần đảm bảo **mọi endpoint nhạy cảm đều match một security chain**. Nếu thêm route ngoài `/api/**` mà không có chain khác, route đó có thể không được bảo vệ bởi cấu hình này.
- `SessionCreationPolicy.STATELESS`: Spring Security không dùng server-side `HttpSession` để lưu/khôi phục authentication. Mỗi request có key phải được xác minh lại; không tự sinh phiên login từ key.
- CSRF bị disable **chỉ trong API chain demo dùng credential trình qua header do client chủ động gắn và không có cookie-based login**. Không áp dụng lời khuyên này cho ứng dụng browser sử dụng session cookie, HTTP Basic được browser tự gửi hoặc các cơ chế ambient credentials. Khi tích hợp nhiều auth mechanisms phải đánh giá CSRF riêng.
- `httpBasic` và `formLogin` tắt để kết quả test rõ và không có authentication pathway khác.
- `AuthorizationFilter` yêu cầu quyền `RECORD_READ` hoặc `RECORD_WRITE` đúng HTTP method, còn tenant là nhiệm vụ của repository/service.
- `authenticationEntryPoint` trả 401 khi request chưa được xác thực; `accessDeniedHandler` trả 403 khi principal hợp lệ nhưng thiếu quyền.
- Không kết luận riêng key đã được cho phép đọc mọi tài liệu vì rule route chỉ là **coarse-grained**.

### 10.8. File ApiRecordStore.java

~~~java
package com.example.apikey;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
public class ApiRecordStore {

    public record ApiRecord(
        long id,
        String tenantId,
        String title
    ) {}

    private final Map<Long, ApiRecord> records = Map.of(
        101L, new ApiRecord(101L, "north", "North report"),
        201L, new ApiRecord(201L, "south", "South report")
    );

    public Optional<ApiRecord> findScoped(long id, String tenantId) {
        return Optional.ofNullable(records.get(id))
            .filter(record -> record.tenantId().equals(tenantId));
    }
}
~~~

Kho dữ liệu demo tự áp điều kiện tenant do principal đã xác minh cung cấp. Với database production, ưu tiên truy vấn scoped như `WHERE id = :id AND tenant_id = :tenantId`; đừng đọc tài liệu xuyên tenant rồi tùy ý quyết định có gửi ra hay không ở frontend.

### 10.9. File ApiController.java

~~~java
package com.example.apikey;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    private final ApiRecordStore store;

    public ApiController(ApiRecordStore store) {
        this.store = store;
    }

    @GetMapping("/api/public")
    public Map<String, String> publicInfo() {
        return Map.of("status", "public");
    }

    @GetMapping("/api/whoami")
    public Map<String, String> whoami(Authentication authentication) {
        ApiPrincipal principal =
            (ApiPrincipal) authentication.getPrincipal();

        return Map.of(
            "clientId", principal.clientId(),
            "tenantId", principal.tenantId()
        );
    }

    @GetMapping("/api/records/{id}")
    public ResponseEntity<Map<String, Object>> record(
            @PathVariable long id,
            Authentication authentication
    ) {
        ApiPrincipal principal =
            (ApiPrincipal) authentication.getPrincipal();

        return store.findScoped(id, principal.tenantId())
            .map(record -> ResponseEntity.ok(
                Map.<String, Object>of(
                    "id", record.id(),
                    "title", record.title()
                )
            ))
            .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping("/api/records")
    public ResponseEntity<Void> createPlaceholder() {
        // Demo chỉ mô phỏng endpoint có permission WRITE.
        // Không thực sự tạo bản ghi hoặc cập nhật cơ sở dữ liệu.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
~~~

Cảnh báo: `createPlaceholder` không thực hiện mutation; nó chỉ tồn tại để minh họa rule `RECORD_WRITE`. Key demo không có quyền đó nên không gọi được endpoint. Trong ứng dụng thật, mutation phải được bảo vệ tại service/domain boundary và tuân thủ transaction/tenant policy.

### 10.10. Sinh secret, chạy và thử HTTP

**Bash/macOS/Linux** (ví dụ sinh key bằng OpenSSL):

~~~bash
export DEMO_API_KEY="$(openssl rand -hex 32)"
mvn spring-boot:run
~~~

Nếu máy thiếu OpenSSL, dùng secret manager hoặc CSPRNG khác phù hợp. Để thử request trong cùng shell:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/whoami
curl -i -H "X-API-Key: invalid-secret" http://localhost:8080/api/whoami
curl -i -H "X-API-Key: $DEMO_API_KEY" http://localhost:8080/api/whoami
curl -i -H "X-API-Key: $DEMO_API_KEY" http://localhost:8080/api/records/101
curl -i -H "X-API-Key: $DEMO_API_KEY" http://localhost:8080/api/records/201
curl -i -X POST -H "X-API-Key: $DEMO_API_KEY" http://localhost:8080/api/records
~~~

**Windows PowerShell 5.1+** có thể sinh 32 random bytes rồi đưa vào environment cho tiến trình Maven:

~~~powershell
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$env:DEMO_API_KEY = -join ($bytes | ForEach-Object { $_.ToString("x2") })
mvn spring-boot:run
~~~

Trên PowerShell, dùng `curl.exe` thay vì alias `curl` nếu cần:

~~~powershell
curl.exe -i -H ("X-API-Key: " + $env:DEMO_API_KEY) http://localhost:8080/api/whoami
~~~

Đừng chạy lệnh `echo $DEMO_API_KEY` để dán raw key vào báo cáo; xác minh key tồn tại bằng độ dài hoặc metadata của secret manager, không bằng cách phát tán credential.

**Kết quả kỳ vọng theo code** (không phải log chạy trong bài viết):

| Request | HTTP | Nội dung/ý nghĩa |
| --- | --- | --- |
| Không key → `GET /api/public` | 200 | JSON `{"status":"public"}` |
| Không key → `GET /api/whoami` | 401 | Chưa có authentication |
| Key sai → `GET /api/whoami` | 401 | Credential không hợp lệ |
| Key hợp lệ → `GET /api/whoami` | 200 | `clientId=client:reporting-job`, `tenantId=north` |
| Key hợp lệ → `GET /api/records/101` | 200 | Record tenant north |
| Key hợp lệ → `GET /api/records/201` | 404 | Record tenant south nằm ngoài scope |
| Key hợp lệ → `POST /api/records` | 403 | Chỉ `RECORD_READ`, thiếu `RECORD_WRITE` |

Status 404 trong demo là lựa chọn policy nhằm không tiết lộ record khác tenant, **không phải quy tắc bắt buộc cho mọi hệ thống**. Một sản phẩm có thể chọn 403/404 phù hợp contract và privacy policy.

## 11. Kiểm thử với MockMvc

File `src/test/java/com/example/apikey/ApiKeySecurityTests.java`:

~~~java
package com.example.apikey;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "DEMO_API_KEY=example-test-secret-for-local-integration-only-123"
})
@AutoConfigureMockMvc
class ApiKeySecurityTests {

    private static final String KEY =
        "example-test-secret-for-local-integration-only-123";

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotRequireKey() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }

    @Test
    void missingKeyCannotUseProtectedApi() throws Exception {
        mvc.perform(get("/api/whoami"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidKeyIsRejected() throws Exception {
        mvc.perform(get("/api/whoami")
                .header("X-API-Key", "wrong-secret"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validKeyIdentifiesClientNotUser() throws Exception {
        mvc.perform(get("/api/whoami")
                .header("X-API-Key", KEY))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.clientId")
                .value("client:reporting-job"))
            .andExpect(jsonPath("$.tenantId").value("north"));
    }

    @Test
    void validKeyCanReadScopedRecord() throws Exception {
        mvc.perform(get("/api/records/101")
                .header("X-API-Key", KEY))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(101));
    }

    @Test
    void sameKeyCannotReadOtherTenant() throws Exception {
        mvc.perform(get("/api/records/201")
                .header("X-API-Key", KEY))
            .andExpect(status().isNotFound());
    }

    @Test
    void readOnlyKeyCannotWrite() throws Exception {
        mvc.perform(post("/api/records")
                .header("X-API-Key", KEY))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
mvn clean test
~~~

Test cung cấp key qua Spring Boot test properties nên **không cần biến môi trường thật** khi chỉ chạy test. Đây là chuỗi test cố định, không phải secret production.

Những test quan trọng:

- **401:** missing/invalid key bị từ chối.
- **200:** key hợp lệ tạo client principal, có quyền đọc đúng tenant.
- **404:** key hợp lệ nhưng không được thấy record khác tenant.
- **403:** key hợp lệ nhưng thiếu scope write.

**Lưu ý về xác minh:** Đây là project mẫu đã trình bày đầy đủ về cấu trúc và code, nhưng trong tài liệu chưa thực hiện Maven build/test. Chỉ coi `BUILD SUCCESS` là kết quả sau khi bạn chạy thật và kiểm tra môi trường/version. Nếu sửa cấu hình filter, security chain hoặc Servlet container, hãy cập nhật integration tests tương ứng.

## 12. Java thuần: chứng minh key của client không phải user

Nếu chưa chạy Spring Boot, chương trình Java 17 sau minh họa quyền theo client và tenant, **không phải chương trình authentication thật**.

Tạo file `ClientScopeDemo.java`:

~~~java
import java.util.Set;

public class ClientScopeDemo {

    record Client(String id, String tenant, Set<String> scopes) {}

    static boolean canRead(Client client, String resourceTenant) {
        return client.scopes().contains("RECORD_READ")
            && client.tenant().equals(resourceTenant);
    }

    public static void main(String[] args) {
        Client reporter = new Client(
            "client:reporting-job",
            "north",
            Set.of("RECORD_READ")
        );

        System.out.println(canRead(reporter, "north"));
        System.out.println(canRead(reporter, "south"));

        Client writerOnly = new Client(
            "client:writer",
            "north",
            Set.of("RECORD_WRITE")
        );
        System.out.println(canRead(writerOnly, "north"));
    }
}
~~~

Lệnh:

~~~bash
javac ClientScopeDemo.java
java ClientScopeDemo
~~~

Stdout chính xác:

~~~text
true
false
false
~~~

Dòng đầu: đúng scope và tenant. Dòng hai: đúng scope nhưng sai tenant. Dòng ba: đúng tenant nhưng thiếu `RECORD_READ`. **Không có dòng nào chứng minh Alice/Bob đã login**: cả hai objects đều là client identities.

## 13. Khi một API key được cấp “cho người dùng”

Một số dịch vụ cho phép user tạo **personal API key**. Metadata có thể chứa `owner_user_id` và scopes, nên backend biết tài khoản đã phát hành key. Tuy vậy:

- Người khác có thể đánh cắp hoặc được chia sẻ key; request không chứng minh chủ tài khoản đang điều khiển.
- Token có thể tồn tại sau phiên đăng nhập, dù user đã logout.
- Nếu user bị vô hiệu hóa, scope hoặc membership thay đổi, key cần được re-evaluate/revoke theo policy.
- Không xem việc có personal key tương đương user **vừa vượt qua MFA** hoặc vừa thực hiện một giao dịch có xác nhận.
- Audit cần phân biệt **key ID**, **tài khoản sở hữu**, **thực thể đang chạy** và **user chủ ý thao tác**. Đây là các trường có thể khác nhau.

Nếu sản phẩm yêu cầu một ứng dụng bên thứ ba thao tác thay user, cân nhắc luồng OAuth2/OIDC delegated authorization được thiết kế đúng, có scopes, audience, expiry, user consent và token revocation. Nếu hệ thống cần biết user hiện tại trong một request server-to-server, phải truyền delegation proof đã được xác minh, không dùng header user ID tự khai.

### Không nhầm “service account” với “con người”

**Service account** là một identity máy/workload. Có thể có owner hoặc team chịu trách nhiệm vận hành, nhưng owner vận hành khác với end-user principal. Một integration có `REPORT_READ` để tổng hợp dữ liệu được phép vẫn không thể tự ý đổi password của người dùng hoặc truy cập hồ sơ cá nhân không nằm trong scope.

## 14. Từ một key demo tới key registry production

Thiết kế tối thiểu của một registry:

~~~sql
-- Schema chỉ mang tính định hướng, cần điều chỉnh theo DB/threat model.
CREATE TABLE api_credentials (
    key_id          VARCHAR(80) PRIMARY KEY,
    client_id       VARCHAR(120) NOT NULL,
    tenant_id       VARCHAR(120),
    secret_digest   VARCHAR(128) NOT NULL,
    scopes          VARCHAR(1000) NOT NULL,
    environment     VARCHAR(40) NOT NULL,
    created_at      TIMESTAMP NOT NULL,
    expires_at      TIMESTAMP,
    revoked_at      TIMESTAMP,
    last_used_at    TIMESTAMP
);
~~~

Không lưu raw key trong bảng. `scopes` dưới dạng một chuỗi chỉ để dễ minh họa schema, production thường cần quan hệ riêng/JSON schema được validate và version policy rõ. Tránh việc client có thể thay đổi `client_id`/`tenant_id` khi gửi request.

Quy trình request:

~~~text
1. Parse format/key id; reject kích thước/header bất thường
2. Tìm record theo public key ID
3. So sánh phần secret bằng digest/HMAC constant-time phù hợp
4. Xác minh environment, expiration, revoked, account/client active
5. Tạo principal client ID/tenant + authorities từ DB
6. Thực hiện request authorization
7. Domain/service kiểm tra owner/tenant của tài nguyên
8. Cập nhật metrics/audit qua key ID, không log raw secret
~~~

Cần design cụ thể cho concurrent rotation và cache: nếu cache metadata còn active sau revoke, key cũ có thể hoạt động vượt quá yêu cầu. Đặt thời gian cache phù hợp hoặc có invalidation. Cần phân biệt **401 invalid credential**, **403 thiếu quyền**, **404 không thấy record** và **429 vượt rate limit** theo API contract.

### Phản ứng khi key lộ

1. Tạm vô hiệu hóa/revoke key bị nghi ngờ càng sớm càng tốt.
2. Xác định key ID, client, scopes, tenant, môi trường và thời gian bị lộ.
3. Kiểm tra logs/metrics theo ID, không truy xuất giá trị raw secret lên nơi không bảo mật.
4. Cấp key mới qua kênh bảo mật, cập nhật client, thử nghiệm request.
5. Thu hồi chắc chắn key cũ; đánh giá dữ liệu đã bị đọc/chỉnh sửa.
6. Sửa nguồn lộ key: Git repository, CI logs, tracing, browser app, config file, email hoặc ticket.
7. Nếu nghi có truy cập trái phép, thực hiện quy trình incident response phù hợp.

Chỉ xóa dòng key trong source mà không revoke server-side là **chưa xử lý sự cố**.

## 15. Rate limiting, quotas và abuse prevention

API key hữu ích để gắn traffic vào client và áp dụng quota:

~~~text
key_id: k_1042
plan: basic
request_limit: 1000 requests / hour
concurrent_limit: 5
max_export_size: 1000 rows
allowed_http_methods: GET
~~~

Đây là policy minh họa, không phải lời khuyên cố định cho mọi API.

Tuy nhiên:

- Không có rate limit thì một key hợp lệ vẫn có thể gây tiêu tốn tài nguyên hoặc trích xuất dữ liệu hàng loạt.
- Một key bị lộ có thể dùng hết quota của khách hàng chính đáng.
- Rate limit theo IP đơn thuần có thể bị vượt qua bởi botnet hoặc ảnh hưởng người dùng chung NAT.
- Cần phối hợp per-key, per-tenant, per-user (nếu có user identity), per-route và “cost-based” limits.
- `429 Too Many Requests` có ý nghĩa khác authentication/authorization. Không dùng rate limiting thay cho access control.

Theo OWASP, API key giúp nhận diện client/giới hạn lạm dụng nhưng **không nên là lớp bảo vệ duy nhất cho tài nguyên nhạy cảm hoặc giá trị cao**. Với tài nguyên đó, cần kết hợp strong authentication, authorization, monitoring và phù hợp business context.

## 16. Câu hỏi kiến trúc và lựa chọn cơ chế

| Bối cảnh | Hướng tiếp cận đáng cân nhắc | Vì sao |
| --- | --- | --- |
| Script nội bộ đọc báo cáo không gắn user | Key riêng cho workload, scopes hẹp; hoặc OAuth2 client credentials | Client identity và quyền máy |
| Đối tác tích hợp API theo hợp đồng | Key riêng theo đối tác + quotas, hạn và revoke; hoặc OAuth2 | Trách nhiệm và audit theo client |
| Ứng dụng web thao tác thay user đã login | User session/OIDC/OAuth2 delegated access | Cần user subject và quyền cá nhân |
| Mobile app phát hành công khai | Không nhúng secret dài hạn vào app; dùng user flow/backend mediation | Mobile secret dễ bị trích xuất |
| Giao dịch tài chính nhạy cảm | Strong authentication, user authorization, step-up/MFA; có thể mTLS/transaction proof | Key một mình không đủ |
| Hệ thống cần revoke từng phiên và hạn ngắn | Token có issuer/lifetime/revocation phù hợp | Key static dài hạn có nhiều giới hạn |
| Batch job cần chạy độc lập con người | Service account với key hoặc short-lived workload credential | Không gán nhầm quyền người dùng |

**Không có công nghệ nào thay được việc hiểu principal.** Nếu user action cần “Alice đồng ý”, một service account token chỉ chứng minh “service này có quyền gọi API”, không đủ để khẳng định consent của Alice.

## 17. Những điều cần phân biệt khi đọc logs

Ví dụ một dòng audit tốt (không chứa secret):

~~~json
{
  "requestId": "req-xyz",
  "clientId": "client:reporting-job",
  "keyId": "k_1042",
  "tenantId": "north",
  "action": "RECORD_READ",
  "resourceId": 101,
  "outcome": "ALLOWED"
}
~~~

Nếu request thực sự được thực hiện thay một user, audit nên có trường end-user đáng tin **từ delegated auth**, phân biệt với client ID. Không điền `userId` chỉ từ header không được xác minh.

Rủi ro khi log: key value, Authorization header, query string có token, request body chứa PII, session cookie, full JWT, raw usernames không cần thiết. Ghi tối thiểu đủ để điều tra và tuân thủ yêu cầu lưu trữ/bảo vệ dữ liệu.

## 18. Câu hỏi tự luyện

**Bài 1.** API key của ứng dụng CRM dùng chung cho 50 nhân viên. API biết key thuộc CRM. Có đủ bằng chứng rằng Alice gửi request không? Vì sao?

**Bài 2.** Một key có `RECORD_READ` và tenant `north`. Caller gửi `GET /api/records/201`, trong đó record 201 thuộc `south`. Nếu server chỉ kiểm tra authority rồi trả record, lỗi bảo mật là gì?

**Bài 3.** Tại sao lưu API key trong JavaScript bundle của SPA công khai không thể coi là bí mật? Đề xuất một phương án nhận diện user thích hợp.

**Bài 4.** Backend tin `X-User-Id: alice` đi kèm API key của service account. Điều gì xảy ra nếu client thay `alice` thành `admin`? Nên xác thực user theo cơ chế nào?

**Bài 5.** Khi một nhân viên rời nhóm, có một key được dùng chung. Vì sao thu hồi quyền của nhân viên ở database chưa chắc ngăn người đó dùng key? Cách tổ chức credentials nào tốt hơn?

**Bài 6.** Với key đã lộ qua Git, vì sao git commit xóa file chưa đủ? Viết quy trình revoke/rotation.

**Bài 7.** Phân biệt 401, 403, 404, 429 trong demo và trong thiết kế production.

**Bài 8.** Tại sao token client credentials của OAuth2 không được coi là “user login token”? Khi nào cần delegated access token?

**Bài 9.** Tại sao nên lưu hash của key entropy cao thay vì raw key? Vì sao SHA-256 không cứu được key có entropy thấp?

**Bài 10.** Có nên tắt CSRF trên mọi security chain chỉ vì một API chain dùng custom header không? Vì sao?

### Đáp án gợi ý

1. Không; key đại diện cho credential/client, không tự gắn vào người đang điều khiển.
2. BOLA/cross-tenant unauthorized access; phải filter tài nguyên theo tenant/owner từ metadata đáng tin.
3. JS bundle đọc được từ client; dùng login/OIDC/delegated token phù hợp hoặc backend trung gian.
4. Có thể giả mạo user; dùng subject từ token được ký và xác minh hoặc session user đã xác thực.
5. Bản sao key chung vẫn còn; key theo workload/user với revoke và scope riêng hoặc delegation.
6. Credential đã bị sao chép, cần revoke server-side, cấp mới, cập nhật hệ thống, điều tra.
7. 401 chưa/không có credential hợp lệ; 403 hợp lệ nhưng thiếu quyền; 404 ngoài phạm vi thấy tài nguyên theo policy; 429 vượt limit.
8. Client credentials đại diện ứng dụng; user delegation cần luồng cấp token có user subject và consent phù hợp.
9. Hash hạn chế lộ raw secret khi DB compromise; key yếu vẫn đoán được offline.
10. Không. Phải đánh giá CSRF theo authentication mechanism từng chain, đặc biệt browser session/cookie.

## 19. Tổng kết

API key là một credential hữu ích để **định danh và quản lý client/workload**, nhưng không tự động xác nhận danh tính **người dùng cuối** hoặc quyền trên mọi tài nguyên. Dùng một khóa chung cho nhiều ứng dụng/người làm mất khả năng truy vết, phân quyền chi tiết và thu hồi độc lập.

Thiết kế đúng thường có các yếu tố:

1. **Principal rõ ràng:** key đại diện client hay user sở hữu key? Đừng đồng nhất hai khái niệm.
2. **Quyền tối thiểu:** scope/action/tenant/resource checks, deny by default.
3. **Credential an toàn:** entropy cao, TLS, không lộ raw key, lưu digest và quản lý secret.
4. **Vòng đời:** expiration, rotation, revoke, incident response, quản lý từng client/thiết bị.
5. **Enforcement:** authentication trong Spring Security filter chain; authorization ở route và domain/service.
6. **Audit/giới hạn:** key ID, client ID, tenant, quota, rate limit, không log secret.
7. **Khi cần user consent:** dùng user authentication và delegation flow phù hợp, không giả danh bằng header.

### Tài liệu tham khảo

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Servlet Security Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [OWASP — API Security Top 10 (2023)](https://api-security.owasp.org/editions/2023/en/0x11-t10/)
- [OWASP — API1:2023 Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/)
