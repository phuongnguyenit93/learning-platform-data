# Kho lưu Proxy Granting Ticket, thời hạn và bảo vệ bí mật trong CAS Proxy

> **Chủ đề:** Spring Security – federation · **Nhóm:** CAS Proxy. Bài học trình bày cách một ứng dụng CAS-enabled nhận và cất giữ **Proxy Granting Ticket (PGT)**, liên kết PGT với kết quả kiểm chứng **Service Ticket (ST)** hoặc **Proxy Ticket (PT)** bằng **PGTIOU**, dùng PGT xin **Proxy Ticket mới** cho backend, quản lý thời hạn/thu hồi và bảo vệ PGT như một **bí mật ủy quyền có khả năng dùng lại**. Các ví dụ tích hợp Spring Security/Apereo CAS chỉ là fragment cần cấu hình dependency, CAS Server, TLS và service registry thật; chương trình độc lập ở cuối dùng Java 17+.

## 1. Vì sao cần kho PGT?

Một ứng dụng web A (CAS service) đã đăng nhập user thông qua CAS. Nó cần gọi backend B, cũng được CAS bảo vệ, **thay mặt user**. Backend B không thấy browser nên không có TGC/TGT của user; việc A gửi nguyên cookie hay mật khẩu user sang B là sai ranh giới tin cậy.

**CAS Proxy Authentication** giải quyết bằng chuỗi:

```text
Browser/user               Service A                CAS Server             Backend B
     |                         |                         |                      |
     | login A                 |                         |                      |
     |------------------------>|                         |                      |
     |<--------- CAS /login?service=A ------------------>|                      |
     |<--------- redirect ?ticket=ST-A ------------------|                      |
     |------------------------>|                         |                      |
     |                         | /serviceValidate         |                      |
     |                         | ST-A + service=A         |                      |
     |                         | pgtUrl=A/proxyreceptor   |                      |
     |                         |------------------------>|                      |
     |                         |<--- callback pgtId + pgtIou                     |
     |                         |    CAS -> A/proxyreceptor|                      |
     |                         |<-- XML success + pgtIou -|                      |
     |                         | match IOU, bind PGT      |                      |
     |                         | to validated user       |                      |
     |                         |                         |                      |
     |                         | /proxy?pgt=PGT&targetService=B                  |
     |                         |------------------------>|                      |
     |                         |<------ PT-B ------------|                      |
     |                         |----------------------------------------------->|
     |                         |                        PT-B (service=B)        |
     |                         |                         |<---- /proxyValidate --|
     |                         |                         |---- CAS result ----->|
     |                         |<------------------------------- data -----------|
```

Điểm khác biệt trọng tâm:

- **ST**: cấp khi browser login một service, **ngắn hạn và chỉ dùng một lần kiểm chứng**.
- **PGT**: bí mật cấp cho A trong quá trình ticket validation, có thể dùng **nhiều lần** để xin PT; phải kiểm soát như credential ủy quyền.
- **PT**: ticket dành **một backend targetService cụ thể**, được B kiểm chứng, thường **chỉ một lần** như ST.
- **PGTIOU**: chuỗi liên kết bản tin callback mang PGT với XML validation result có cùng IOU; **không dùng để gọi /proxy** và không phải PGT.

PGT có thể bị dùng nhiều lần trong thời gian còn hiệu lực, nên một PGT lộ ra có rủi ro lớn hơn ST dùng một lần. Tập trung của bài này là **vòng đời PGT và kho lưu PGT ở service A**, không phải lưu mọi ST/PT vào cùng một bảng.

### Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Vẽ đúng luồng CAS `/serviceValidate` → `pgtUrl` callback → `PGTIOU` → kho PGT → `/proxy` → `/proxyValidate`.
2. Phân biệt **PGT, PGTIOU, ST, PT, TGT và TGC**, đặc biệt “PGT dùng nhiều lần” khác “ST/PT một lần”.
3. Thiết kế kho PGT có khóa tra cứu, **binding CAS server / tenant / user / session / service A**, trạng thái và TTL.
4. Quản lý **temporary callback store** tách khỏi **active PGT vault** để tránh dùng PGT chưa được liên kết với validation result tin cậy.
5. Định nghĩa hết hạn theo **CAS Server policy + app storage policy + session/logout/revocation**, không chọn TTL cứng rồi cho rằng CAS sẽ chấp nhận mãi.
6. Bảo vệ PGT trong RAM/Redis/DB/HSM-KMS, transit/callback/logs/backup và quá trình rotation.
7. Dùng `ProxyGrantingTicketStorage`, `Cas20ProxyTicketValidator` và `CasAuthenticationFilter` của Spring Security CAS đúng vai trò và phân biệt fragment với ứng dụng runnable.
8. Biết lúc nào phải xóa PGT, xin PGT mới, kiểm tra CAS proxy chain và không dùng `acceptAnyProxy=true` tùy tiện.
9. Chạy một demo Java 17 mô phỏng **PGTIOU binding, AES-GCM storage, TTL, session isolation và revoke** có stdout xác định.

## 2. Các ticket và secret không đồng nhất

| Thành phần | Ai phát/giữ? | Sử dụng | One-time? | Lưu ở đâu? |
| --- | --- | --- | --- | --- |
| **TGT** — Ticket Granting Ticket | CAS Server ticket registry | Làm nền cho phiên SSO/user, cấp tickets | Không theo semantics ST | CAS Server; không đưa cho service A |
| **TGC** — Ticket Granting Cookie | Browser ↔ CAS origin | CAS tìm TGT/SSO session | Cookie theo CAS policy | Browser cookie jar scoped CAS |
| **ST** — Service Ticket | CAS Server → browser → A | A xác thực CAS login | **Có**, một validation attempt | Không giữ dài hạn trong app |
| **PGT** — Proxy Granting Ticket | CAS Server → HTTPS callback của A | A xin nhiều PT cho backend | **Không**; reuse được trong policy/time window | **Protected PGT vault** của A |
| **PGTIOU** | CAS Server → callback và XML validation response | Correlate PGT callback với ST/PT validation result | **Correlation single-use** ở app | Temporary IOU mapping với TTL rất ngắn |
| **PT** — Proxy Ticket | CAS Server → A → backend B | B xác thực lệnh delegated cho B | **Có**, ngắn hạn/một validation | Chỉ chuyển đến target B, không cache cho nhiều calls |
| **Local HttpSession** | Service A backend + browser cookie | Giữ local authenticated principal | Session lifecycle | Session store; **khác PGT vault** |

Một PGT không phải “global password” hay OAuth refresh token chuẩn, nhưng về rủi ro nó **giống credential dài hơi dùng xin credential ngắn hạn**. Ai lấy được PGT có thể cố yêu cầu CAS cấp PT cho targets mà PGT và service authorization cho phép, cho đến khi hết hạn/thu hồi.

### 2.1. PGT và CAS TGT có quan hệ thế nào?

PGT được CAS phát trong ngữ cảnh một client đã được CAS xác thực và có ticket validation hợp lệ; CAS quản lý quan hệ với SSO grant/client. Theo CAS protocol, **PGT phải hết hiệu lực khi client whose authentication is proxied đăng xuất khỏi CAS**.

Điều này **không** có nghĩa ứng dụng có thể đọc TGT/TGC hay luôn được CAS gửi một logout callback thành công. Cần phân biệt:

- CAS Server chịu trách nhiệm **không chấp nhận PGT đã hết hạn/thu hồi**.
- Service A chịu trách nhiệm **không tiếp tục giữ/cố dùng PGT** sau session logout, policy expiry, tenant unlink, credential compromise hoặc nhận revocation signal.
- Nếu sự kiện CAS SLO không đến vì network outage, service A có thể còn ciphertext PGT trong vault đến local TTL, **nhưng CAS vẫn phải từ chối PGT đã bị server revoke**. Không coi local cache hit là proof CAS còn chấp nhận.
- Khi CAS Server restart/ticket registry thay đổi khiến PGT không còn, A phải fail closed và tái thực hiện flow được phê duyệt; không tái kích hoạt PGT cũ.

### 2.2. PGT không phải PT

A dùng PGT gọi:

```http
GET /cas/proxy?pgt=PGT-FAKE&targetService=https%3A%2F%2Fbackend.example.org%2Fapi HTTP/1.1
Host: sso.example.org
```

Đây là **HTTP transcript giả lập** để thấy tham số theo CAS protocol; **không đưa PGT thật trong ví dụ, tài liệu công khai hoặc access logs**. CAS kiểm tra PGT còn hợp lệ, A có quyền proxy tới `targetService` và phát `PT`. Backend B dùng PT gọi CAS `/proxyValidate` rồi mới tin username/proxy chain.

Một PGT có thể xin PT lần 1, 2, 3… khi còn hiệu lực; nhưng **mỗi PT phải ràng buộc đúng targetService và dùng một lần**, không dùng PT từ B sang C hoặc replay nhiều calls. Khi B là stateless REST API cần nhiều lệnh, A thường xin **PT mới cho mỗi xác thực** hoặc dùng protocol cache được quản lý riêng theo contract, không kéo dài PT thành bearer token tùy ý.

## 3. Luồng nhận PGT và PGTIOU thật chi tiết

Giả sử:

```text
CAS Server:      https://sso.example.org/cas
Service A:       https://portal.example.org/login/cas
PGT callback A:  https://portal.example.org/login/cas/proxyreceptor
Backend B:       https://backend.example.org/api
```

Địa chỉ đều là **giả lập** và cần public HTTPS/service registry/certificate hợp lệ khi triển khai thật.

### 3.1. Bước 1: A validate ST, yêu cầu PGT

Sau khi browser trả `ST-A` về `/login/cas`, A gọi CAS backchannel:

```http
GET /cas/serviceValidate?service=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas&ticket=ST-A&pgtUrl=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas%2Fproxyreceptor HTTP/1.1
Host: sso.example.org
```

`service` phải khớp service identity khi ST được cấp. `pgtUrl` là **public callback URL nhận PGT** do A đăng ký và được CAS tin, không phải URL backend B.

**Không hoán đổi** `pgtUrl` với `targetService`: pgtUrl thuộc A và dùng nhận bí mật; targetService thuộc B và dùng xin PT sau đó.

### 3.2. Bước 2: CAS gọi ngược pgtUrl qua HTTPS

Sau khi xác định điều kiện cấp PGT, CAS kết nối HTTPS đến `pgtUrl` của A và truyền:

```http
GET /login/cas/proxyreceptor?pgtId=PGT-SECRET-EXAMPLE&pgtIou=PGTIOU-EXAMPLE HTTP/1.1
Host: portal.example.org
```

Đây là **server-to-server callback CAS → A**, không phải browser user điều hướng đến proxy receptor. Cả `pgtId` và `pgtIou` xuất hiện trong URL query theo giao thức, nên phải **redact ở ingress, reverse proxy, access logs, WAF và APM**.

CAS sẽ kiểm tra TLS endpoint/certificate của A theo policy. CAS protocol yêu cầu callback trả HTTP 200 cho luồng PGT thành công; 3xx redirects có thể được CAS server xử lý theo spec/implementation, nhưng production nên có **URL ổn định không redirect**, trả 200 sau khi lưu thành công, tránh lộ PGT qua redirect/log.

Tại A, proxy receptor **chưa được quyền gắn PGT cho bất kỳ username tùy ý**. Nó chỉ nên stage một bản ghi pending theo IOU, có TTL rất ngắn, chống duplicates và đủ điều kiện network/trust.

### 3.3. Bước 3: CAS trả kết quả validate ST kèm PGTIOU

CAS trả XML qua response cho request `/serviceValidate` của backend A:

```xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
    <cas:proxyGrantingTicket>PGTIOU-EXAMPLE</cas:proxyGrantingTicket>
  </cas:authenticationSuccess>
</cas:serviceResponse>
```

**Dễ nhầm:** nội dung `cas:proxyGrantingTicket` là **PGTIOU**, **không phải PGT secret**. Chuỗi PGT thật nằm ở `pgtId` gửi trực tiếp qua callback.

Chỉ sau khi CAS validation result thật sự là `authenticationSuccess` đối với **ST/PT, service ID và CAS Server đáng tin**, A mới được dùng PGTIOU ở XML để tìm pending PGT và **gắn PGT với principal/session/tenant đã xác thực**. Nếu validation fail, không có PGTIOU hợp lệ hoặc IOU lookup thất bại, **không cấp proxy capability**.

### 3.4. Bước 4: correlate PGTIOU

```text
CAS->A callback                    A->CAS validation response
pgtIou = PGTIOU-123                cas:proxyGrantingTicket = PGTIOU-123
pgtId  = PGT-SECRET-456            cas:user = alice (validated)
        |                                      |
        +----------- same IOU -----------------+
                         |
               validate provenance and state
                         |
               bind PGT-SECRET-456 to
               CAS origin + tenant + alice + local session
                         |
                    active PGT vault
```

**Không** chấp nhận callback như login token, và không gán `pgtId` cho user chỉ vì một người gửi query `?pgtIou=...`. Một attacker có thể gửi fake callback HTTP request, đặc biệt khi proxy receptor public. PGTIOU có entropy ngẫu nhiên và được xác nhận từ **CAS backchannel validation response**, giúp tránh trust một callback trần.

### 3.5. Bước 5: dùng PGT lấy PT

Khi A cần gọi B:

1. A xác định **user/session hiện hành** từ local authenticated SecurityContext/session, không từ browser query `subject=alice`.
2. Kiểm tra policy user/tenant, backend B nằm trong **allowed targetServices** và app session không bị logout/expired.
3. Tra active vault theo key scope; đọc PGT vào memory trong thời gian ngắn, không in ra log.
4. A gọi CAS `/proxy?pgt=PGT...&targetService=B` qua **HTTPS đã kiểm chứng certificate/hostname**, log redacted.
5. CAS cấp PT nếu PGT còn hiệu lực và service policy cho phép.
6. A gửi PT **chỉ tới B**, B kiểm chứng qua `/proxyValidate`, kiểm tra proxy chain/authorization trước khi xử lý request.
7. Nếu `/proxy` báo PGT invalid/expired, A **xóa active entry**, không tự retry cùng PGT vô hạn hoặc downgrade bằng service ticket cũ.

**An toàn:** A không được lấy PGT từ request của browser và cũng không xuất PGT qua REST response cho frontend. PGT phải ở server-side vault/credential store, do backend A chỉ sử dụng ở HTTPS backchannel.

## 4. Kho PGT cần lưu những gì?

Một thiết kế an toàn thường có **hai tầng bản ghi**:

1. **Pending PGTIOU store:** bản ghi sống rất ngắn từ CAS callback trước khi XML validation xác nhận user.
2. **Active PGT vault:** bản ghi PGT đã được liên kết với authentication/user/session và được dùng để xin PT khi cần.

### 4.1. Pending store: chỉ stage, không sử dụng

| Trường | Ví dụ | Mục đích |
| --- | --- | --- |
| `pgtIouLookupKey` | HMAC/digest của `PGTIOU-...` | Tìm cặp IOU/PGT; hạn chế log raw IOU |
| `encryptedPgtId` | AES-GCM ciphertext | Giữ PGT bí mật trong cache |
| `receivedAt` | UTC instant | Quản lý thời gian callback |
| `expiresAt` | receivedAt + short pending TTL | Không để orphan callback giữ PGT lâu |
| `casOriginHint` | CAS connector identity tin cậy nếu có | Hỗ trợ scope/diagnostic, **không tự chứng minh caller** |
| `state` | PENDING | Chưa thể dùng xin PT |
| `nonce/version` | Crypto metadata | Decrypt và rotate key |

**Pending callback không biết chắc username**, vì user được xác nhận ở **validation response**. Không được tạo active mapping cho `alice` từ một form query do người ngoài gửi.

### 4.2. Active vault: credential đã ràng buộc

Một bản ghi active có thể gồm:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `tenantId` / `registrationId` | Ranh giới dữ liệu và CAS integration |
| `casServerId` | CAS Server issuer/base URL đã duyệt, không lấy từ browser |
| `serviceId` | CAS service A đã nhận ST/PT; tránh dùng sai service |
| `localSessionKey` | Opaque authenticated session reference hoặc identity context an toàn |
| `subjectKey` | Username/subject sau CAS validation, namespace theo CAS/tenant |
| `pgtCiphertext` | PGT được mã hóa, **không lưu plaintext** |
| `encryptionKeyId` | KMS/secret key version dùng giải mã |
| `issued/linkedAt` | Thời điểm A liên kết validation result với PGT |
| `expiresAt` | **Local upper bound** của quyền sử dụng, không vượt policy |
| `status` | ACTIVE / EXPIRED / REVOKED / ROTATING |
| `sourceIouProofId` | Correlation record ID không chứa raw secret |
| `lastUsedAt`, `lastProxyTarget` | Telemetry an toàn, target ID từ allowlist |

**Khóa tra cứu không nên chỉ là username/email.** Một user có thể đăng nhập ở hai browser sessions; hai tenants có thể có user cùng NameID; một CAS Server có thể phục vụ nhiều services. Lookup bằng `username` duy nhất có thể trả PGT sai ngữ cảnh và làm cross-user/tenant delegation.

### 4.3. Ví dụ schema cho thiết kế vault (mang tính minh họa)

```sql
-- MÔ HÌNH LƯU TRỮ, không phải DDL production hoàn chỉnh.
CREATE TABLE cas_pgt_vault (
    tenant_id           VARCHAR(128) NOT NULL,
    cas_server_id       VARCHAR(256) NOT NULL,
    service_id          VARCHAR(256) NOT NULL,
    session_key_hash    VARCHAR(128) NOT NULL,
    subject_key_hash    VARCHAR(128) NOT NULL,
    ciphertext          BLOB NOT NULL,
    nonce               BLOB NOT NULL,
    key_version         VARCHAR(64) NOT NULL,
    linked_at           TIMESTAMP NOT NULL,
    expires_at          TIMESTAMP NOT NULL,
    status              VARCHAR(16) NOT NULL,
    PRIMARY KEY (tenant_id, cas_server_id,
                 service_id, session_key_hash)
);
```

Schema thật cần indexing/uniqueness/TTL jobs, transaction isolation, encryption AAD, retention, HMAC lookup keys, access policies và audit. Một string hash username đơn giản không đủ chống dictionary attack; với PII trong lookup keys có thể dùng keyed HMAC hoặc pseudonymous ID được quản trị. `ciphertext` không đồng nghĩa “an toàn nếu database user có quyền đọc key”.

### 4.4. Đặt khóa tra cứu theo scope thay vì chỉ IOU

Giai đoạn pending dùng `PGTIOU` làm correlation key vì callback và XML validation response gặp nhau tại giá trị này. Giai đoạn active phải dùng **scope được xác thực**; IOU không nên tồn tại như access key công khai cho PT-issuing API.

Một cách đặt key:

```text
PENDING KEY:
  HMAC(k_lookup, casServerId || pgtIou)
  (short-lived, one-time bind)

ACTIVE KEY:
  tenantId || casServerId || serviceId || authenticatedSessionKey
  + store subject identity as validated attribute
  (never derive from untrusted request parameters)
```

Trong môi trường nhiều CAS Servers, cùng tên user hoặc cùng tenant không đồng nghĩa cùng trust. Nếu một ticket/request thuộc CAS A thì vault của CAS B **không** được trả ra PGT A.

## 5. Thời hạn: bốn đồng hồ không thể gộp

### 5.1. Các loại TTL quan trọng

| Thành phần | Ai quyết định? | Mục đích | Hành vi khi hết hạn |
| --- | --- | --- | --- |
| ST/PT validity | CAS Server policy/protocol | Ticket ngắn hạn/one-time | Validation reject; không replay |
| **PGT server expiration** | CAS Server PGT policy, TGT/session lifecycle | Đến khi nào CAS còn chấp nhận PGT để xin PT | `/proxy` từ chối |
| **Pending IOU TTL** | Ứng dụng A | Cho callback/validation result có thời gian correlate | Hủy pending PGT nếu không match |
| **Active vault TTL** | Ứng dụng A security/storage policy | Không giữ PGT local quá lâu | Không decrypt/use nữa, xóa entry |
| Local HttpSession expiry | Service A session manager | Tuổi phiên authenticated user ở A | Xóa PGT gắn session nếu policy là session-bound |
| CAS SSO logout/expiry | CAS Server | Kết thúc quyền SSO/delegation liên quan | PGT server phải hết hiệu lực khi user logout CAS |

**Không hardcode** “PGT sống 8 giờ” như điều chắc chắn của giao thức. CAS Protocol nói PGT **MUST expire on CAS logout**, nhưng thời hạn tuyệt đối/idle timeout có thể do **Apereo CAS version và deployed policy** quyết định. Client thường không được cung cấp một `expiresAt` chính xác trong CAS 2.0 validation XML, nên không thể suy từ `pgtIou` hoặc `pgtId`.

### 5.2. Chính sách effective expiration

Về ý tưởng:

\[
T_{\text{effective}}=\min(T_{\text{local-limit}}, T_{\text{CAS-PGT-expiry}}, T_{\text{session-expiry}}, T_{\text{revocation}})
\]

Trong đó:

- `T_local-limit`: upper-bound do A tự đặt, ví dụ business session policy/maximum PGT retention.
- `T_CAS-PGT-expiry`: nếu CAS có cách báo thời hạn đáng tin thì dùng; nếu không, **không giả định** một số lớn mà coi là server TTL.
- `T_session-expiry`: nếu PGT được gắn với phiên authenticated thì logout/timeout dừng quyền sử dụng ngay.
- `T_revocation`: CAS logout, user unlink/tenant revoke, nghi ngờ lộ credential hoặc khóa encryption bị compromise → đóng ngay, không chờ TTL.

Khi CAS Server từ chối PGT, client phải xóa/bỏ hiệu lực local entry dù local `expiresAt` chưa đến. **Local TTL chỉ là upper-bound về lưu trữ/sử dụng, không chứng minh PGT vẫn hợp lệ tại CAS**.

### 5.3. Pending TTL phải rất ngắn

PGT callback có thể đến **trước** khi validator parse XML response hoặc ngược lại tùy scheduling. Vì vậy:

- Pending store chờ correlation trong một cửa sổ nhỏ được tính từ request/response timings thực tế.
- Thiết kế asynchronous callback/validation nên có bounded wait/retry đọc storage **không tái-validate ST**; ST có single-use semantics.
- Nếu quá thời hạn, xóa encrypted PGT pending và fail closed; không tự tạo proxy access cho user.
- Duplicated `pgtIou` phải reject hoặc xử lý idempotency **theo contract rõ**, tuyệt đối không overwrite một PGT hợp lệ bằng giá trị attacker gửi.
- Nếu CAS validator báo failure hoặc thiếu `cas:proxyGrantingTicket`, cleanup mọi pending record liên quan thay vì “lấy PGT mới nhất”.

Không dùng unbounded in-memory map cho orphaned callbacks; attacker có thể lấp đầy heap bằng nhiều PGTIOU giả. Cần size/rate limits, expiry and delete, ingress filters và monitoring.

### 5.4. Đặt TTL minh họa có chú thích

```yaml
# Chỉ là chính sách ứng dụng minh họa, KHÔNG phải
# thuộc tính cấu hình chính thức của Spring Security CAS.
cas-proxy-vault:
  pending-correlation-ttl: PT30S
  active-local-upper-bound: PT20M
  cleanup-interval: PT1M
  max-pending-items: 10000
  delete-on-local-logout: true
  delete-on-cas-slo: true
  fail-closed-on-cas-rejection: true
```

Các giá trị `PT30S`, `PT20M`, `PT1M`, `10000` chỉ minh họa cách biểu đạt `Duration`, **không phải khuyến nghị cố định cho mọi hệ thống**. Phải đo callback latency, CAS PGT expiration, session policy, SLA, scale và compliance thực. Nếu CAS PGT policy ngắn hơn local 20 phút thì CAS vẫn từ chối sau server expiry.

### 5.5. CAS ticket policy phụ thuộc release

Apereo CAS có cấu hình **Proxy-Granting Ticket expiration policy** theo phiên bản. Không copy property names từ “development” docs sang production release mà chưa xác minh. Kiểm tra đúng **CAS server version**, config catalog và test thực tế: CAS logout, idle/max lifetime, clock skew, ticket-registry eviction, cluster failover.

Đừng tăng CAS PGT timeout thật dài chỉ để che một lỗi vault lookup, proxy callback hoặc session mapping. Việc tăng TTL làm kéo dài cửa sổ khi PGT bị lộ.

## 6. Thu hồi PGT: hết hạn khác logout và incident

### 6.1. Sự kiện nào phải xóa/bỏ hiệu lực?

| Sự kiện | Phía service A | Phía CAS Server |
| --- | --- | --- |
| User logout local ở A | **Xóa active entry** gắn phiên/user theo policy | CAS TGT có thể còn, PGT có thể còn server-side |
| User logout khỏi CAS | Xóa khi nhận SLO/revocation hoặc theo local TTL; không dùng tiếp | **PGT phải hết hiệu lực** theo protocol |
| User session A timeout | Không dùng PGT từ phiên hết hạn | CAS có thể chưa logout |
| User đổi account / unlink CAS | Revocation scope cũ, không reuse PGT | Có thể cần server-side revoke tùy API/policy |
| Tenant bị disable / backend access bị revoke | Xóa tất cả PGT scope tenant và chặn `/proxy` | Có thể thay đổi service proxy authorization |
| PGT bị nghi lộ | Xóa/blacklist, gọi CAS revoke/logout nếu hỗ trợ; incident response | Thu hồi server-side là quan trọng |
| Rotation của encryption key vault | Re-encrypt hoặc chấp nhận mất vault/re-login theo policy | **Không** tự rotate CAS PGT |
| CAS Server trả invalid PGT | Drop local entry, thông báo reauth/regrant phù hợp | Không chấp nhận cũ |

**Một lệnh `DELETE` trong Redis của A không làm CAS Server revoke PGT.** Nếu PGT thực sự lộ, cần xử lý ở CAS Server (expire/revoke TGT/PGT, chính sách đăng xuất) và kiểm tra các PT đã được cấp tùy khả năng server/backend; xóa client ciphertext chỉ ngăn A dùng tiếp.

### 6.2. CAS SLO không được coi 100% tin cậy về delivery

CAS Server có thể gửi logout notifications đến registered services. Nhưng mạng/ứng dụng có thể lỗi, callback có thể bị chặn hoặc session store thiếu state. Vì vậy:

- CAS Server enforce PGT expiry/revocation độc lập.
- Service A duy trì local TTL, logout hooks, periodic cleanup và xử lý `/proxy` failures.
- Nếu một SLO notification không có hiệu lực, local vault vẫn không được phép dùng PGT quá local session lifetime đã định.
- Các sự kiện logout/revoke phải idempotent, không cần giữ PGT secret trong event payload.

### 6.3. Không “refresh PGT” bằng cách tạo ST giả

PGT không phải JWT tự gia hạn bằng cách giải signature. Nếu PGT hết hạn, để nhận PGT mới phải qua luồng CAS authentication/ticket validation phù hợp (có thể dùng existing CAS SSO nếu policy cho phép), tạo callback/IOU mới. Không gửi lại ST cũ, không tự build `PGT-...`, không nhân bản giá trị PGT lâu dài.

## 7. Bảo vệ bí mật PGT trong storage

### 7.1. Nguyên tắc tối thiểu

- **Không plaintext persistent PGT** trong database/Redis, log, metrics, browser storage, session cookie, source code, exception message hoặc CI artifacts.
- Encryption at rest bằng **AEAD**, ví dụ AES-256-GCM, với key từ KMS/HSM/secret manager, rotation và ACL rõ ràng.
- TLS/mTLS thích hợp cho traffic giữa app ↔ store, app ↔ CAS và CAS ↔ pgtUrl.
- Quyền truy cập vault **chỉ cho backend có trách nhiệm xin PT**, không cho frontend, service B hoặc jobs chung.
- Data model tách tenant/CAS/user/session; use encryption AAD để gắn ciphertext với scope, chống copy ciphertext từ tenant A sang B.
- PGT đã lấy khỏi store chỉ hiện diện trong heap lâu nhất cần thiết để gọi CAS `/proxy`, không dump memory/core heap không được mã hóa trong môi trường thông thường.
- Secrets và root encryption keys không chia sẻ qua nhiều tenants khi blast radius/compliance yêu cầu cô lập.

### 7.2. Vì sao Base64 và hash không đủ?

Base64 chỉ encode bytes, không bảo vệ bí mật. One-way hash PGT có thể giúp **so khớp** hoặc audit an toàn nếu có key, nhưng khi A cần gọi `/proxy?pgt=...`, A phải có khả năng lấy lại PGT plaintext. Vì vậy **không thể chỉ hash PGT rồi mong gọi /proxy được**; dùng reversible encryption trong vault, hoặc đặt việc gọi CAS vào một credential broker được phân quyền (để app không bao giờ có direct decrypt privilege).

### 7.3. Encryption model đề xuất

```text
App receives PGT over HTTPS callback (brief plaintext)
                |
                v
Encrypt with AEAD
  key from KMS / envelope encryption
  nonce unique per key
  AAD = tenant + CAS server + service + local session + subject
                |
                v
Store nonce + ciphertext + authTag + keyVersion + expiresAt
                |
                v
For authorized backend call:
  verify session / scope / targetService / not expired
  decrypt briefly -> CAS /proxy over verified HTTPS
  scrub buffers when feasible; never log PGT
```

Trong AES-GCM, tránh **reusing nonce với cùng key**; dùng unique random nonce đủ mạnh (thường 96 bit) hoặc nonce scheme đã quản trị. Mỗi encryption operation nên có AAD dựa trên **immutable trusted identity**, không lấy tenant/subject từ browser form.

**Key rotation khác PGT rotation:** đổi KMS key version và re-encrypt ciphertext không tạo một PGT mới ở CAS; nó chỉ đổi cách A giữ PGT. Khi nghi PGT lộ, cần server-side revoke/regrant, không chỉ re-encrypt DB row.

### 7.4. Nếu kho là Redis

Redis có thể hữu ích cho multi-node PGTIOU correlation và active vault nhưng không mặc định là “secret vault”. Cần:

- TLS và authentication/ACL; service account chỉ được đọc/ghi namespace của chính ứng dụng/tenant nếu khả thi.
- TTL server-side trên cả pending và active keys; không chỉ Java `if(expired)`.
- Atomic `SET NX EX` hoặc Lua/transaction logic để tránh callback giả overwrite IOU trước validation.
- Atomic consume/move pending→active; tránh hai validators cùng bind một IOU.
- Namespace per tenant/CAS; không quét `KEYS *` trong request path.
- Encryption trước khi ghi; kiểm tra replication, persistence, backup, admin console, support tooling và snapshot dump.
- Rate limits, maximum pending count, reaper/metrics và memory eviction strategy phù hợp.
- Secret key **không** để ngay trong cùng Redis database hoặc cùng IAM permission với ciphertext.

Ngay cả khi Redis có TLS và disk encryption, admin access, snapshots, AOF hoặc debugging có thể làm lộ plaintext nếu ứng dụng lưu raw PGT. Encrypt PGT tại application/credential broker trước khi gửi Redis.

### 7.5. Nếu kho là RDBMS

Dùng column ciphertext + keyVersion + nonce, transactional update và index expiration. Với hàng mới:

1. Dùng committed pending record sau callback, không active trước CAS validation success.
2. Transactional lookup by IOU + expiration + expected status.
3. Bind user/tenant/session sau validation; chuyển hoặc tạo active credential; xóa pending.
4. Reject duplicate validation/late callback và ghi audit reason.
5. Expiry job xóa ciphertext/records, backup retention policy rõ.
6. Không để `SELECT *`, database query logging hoặc ORM `toString()` in secret fields.

Nếu DB backup đã chứa PGT ciphertext, vẫn cần backup encryption và retention; xóa row active không đảm bảo tất cả historical ciphertext biến mất ngay. Phải phân biệt **xóa metadata local** và **CAS Server revocation**.

### 7.6. In-memory storage chỉ phù hợp khi nào?

Một `ConcurrentHashMap` hoặc `ProxyGrantingTicketStorageImpl` trong-memory có thể dùng cho demo/single-node test, nhưng production phải giải quyết:

- Mất pending callback khi app restart.
- CAS callback đến pod A nhưng validator xử lý ở pod B.
- Không có TTL/cleanup hiệu quả, có thể leak memory.
- Key vật lý chung JVM; heap dump có thể chứa PGT.
- Logout ở node A không xóa PGT node B.
- Không có encrypted persistent store hoặc audit đáng tin.

Spring Security docs nêu ví dụ `ProxyGrantingTicketStorageImpl` in-memory **không nên dùng trong ứng dụng thực** nếu không xử lý bảo vệ và `cleanup()` hết hạn. Với nhiều pods, dùng shared/distributed implementation hoặc kiến trúc callback affinity có ràng buộc rõ; điều khiển TTL và store encryption theo nhu cầu.

## 8. Bảo vệ đường callback pgtUrl

### 8.1. CAS phải kết nối callback HTTPS tin cậy

CAS protocol yêu cầu dùng HTTPS callback để cấp PGT và kiểm tra certificate endpoint. Cấu hình `pgtUrl` phải:

- Là URL công khai **được A quản trị**, ví dụ `https://portal.example.org/login/cas/proxyreceptor`.
- Được CAS Server/service registry cho phép theo security policy.
- Có TLS certificate/hostname hợp lệ mà CAS Server xác minh.
- Route đúng qua reverse proxy về `CasAuthenticationFilter` hoặc proxy-receptor handler của A.
- Trả 200 khi nhận/lưu pending PGT thành công, tránh redirect tùy tiện.
- Không nhận `pgtUrl` từ query input của user hoặc config không được duyệt.

**Lưu ý trust hai chiều:** CAS kiểm tra **A là callback HTTPS endpoint đúng**. Nhưng ở phía A, kết nối TLS vào A **không tự chứng minh người gọi là CAS Server** trừ khi dùng mutual TLS (mTLS) hoặc cơ chế caller authentication khác. Cần bảo vệ callback bằng ingress allowlist, mTLS giữa CAS–A, network segmentation và quan trọng nhất là **PGTIOU correlation với CAS validation response**.

### 8.2. Callback giả mạo và preemptive IOU

Một attacker có thể gọi:

```http
GET /login/cas/proxyreceptor?pgtId=PGT-ATTACKER&pgtIou=PGTIOU-GUESS HTTP/1.1
Host: portal.example.org
```

Không được:

- Coi callback là login thành công;
- Gắn ngay PGT đó với user từ request;
- Tạo `Authentication` hoặc `HttpSession` chỉ vì có hai query parameters;
- Cho phía browser gọi API `/proxy` với pgtId bất kỳ.

PGTIOU phải là giá trị ngẫu nhiên khó đoán; A chỉ promote nếu IOU khớp validation result thật của ST/PT từ **CAS Server tin cậy**. Đồng thời reject duplicate IOU/pending overwrite, quá TTL và callback from unapproved network/mTLS identity khi khả thi.

### 8.3. Đừng biến callback thành endpoint đăng xuất hay download

`/login/cas/proxyreceptor` là endpoint CAS server-to-service để nhận secret. Nó không phải page người dùng xem, không trả `pgtId` trong response body, không render HTML chứa ticket, không log query. Nếu callback không được Spring filter nhận, trả 404/reject có kiểm soát, không fallback vào controller ghi raw request parameters ra console.

### 8.4. Reverse proxy và forwarded headers

Giả sử:

```text
External: https://portal.example.org/app/login/cas/proxyreceptor
Ingress:  /app/ -> /
Internal: http://portal-service:8080/login/cas/proxyreceptor
```

Khi đó:

- `Cas20ProxyTicketValidator.proxyCallbackUrl` phải là **external HTTPS** callback.
- `CasAuthenticationFilter.proxyReceptorUrl` là **local servlet path** phù hợp rewrite, ví dụ `/login/cas/proxyreceptor`.
- CAS Server phải trust endpoint TLS public.
- Proxy phải strip/overwrite untrusted `Forwarded`/`X-Forwarded-*`/Host headers và không nhận arbitrary callback host.
- Bật Spring forwarded strategy chỉ khi ingress có trusted header sanitation; tránh double-prefix.
- Nếu CAS callback nhận 301/302, nên sửa path/HTTPS/canonical URL để callback trả trực tiếp 200.

**Không nhầm:** HTTP reverse proxy đứng trước app khác hoàn toàn với CAS **Proxy Granting Ticket**; Nginx không làm một ứng dụng tự có khả năng xin PT.

## 9. Spring Security CAS: các thành phần cho PGT

Spring Security CAS integration thường gồm:

| Thành phần | Tác dụng |
| --- | --- |
| `CasAuthenticationEntryPoint` | Redirect browser đến CAS /login khi A chưa authenticated |
| `CasAuthenticationFilter` | Nhận ST ở callback A và có thể nhận PGT callback ở `proxyReceptorUrl` |
| `CasAuthenticationProvider` | Validate ticket, tạo authenticated principal theo policy |
| `ServiceProperties` | Service URL A dùng khi issue/validate ST |
| `Cas20ProxyTicketValidator` | Gọi CAS validation với `pgtUrl` để xin PGT và dùng storage correlation |
| `ProxyGrantingTicketStorage` | Nhận/lưu cặp `pgtIou→pgtId` để validator có thể lấy PGT |
| `CasProxyDecider` / trusted proxy policy | Xác định proxy chain nào chấp nhận khi app ở vai trò backend |
| `Cas20ProxyRetriever` / CAS client equivalent | Dùng PGT xin PT từ CAS `/proxy` tùy API phiên bản |
| `TicketValidator` | Server-to-server CAS validation, không dựa browser tự verify |

**Khác nhau giữa A và B:** Service A là CAS **proxying client** giữ PGT để xin PT. Backend B là CAS **proxied target** nhận PT và verify chain/trust, thường không cần giữ PGT trừ khi B tiếp tục proxy tới C.

### 9.1. Dependencies minh họa

```xml
<!-- Fragment Maven, cần Spring Boot parent/BOM và version tương thích -->
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-cas</artifactId>
</dependency>
```

CAS client APIs có khác biệt package theo lịch sử: tài liệu mới dùng `org.apereo.cas.client.*`, một số ví dụ cũ dùng `org.jasig.cas.client.*`. Đừng copy cả hai vào cùng source; chọn artifact/version đang build và kiểm tra javadoc. Spring Boot không tự cấu hình PGT vault từ một YAML tự đặt nếu chưa có bean tương ứng.

### 9.2. Chia sẻ đúng ProxyGrantingTicketStorage

Fragment Java cho **Spring Security CAS client tương thích phiên bản tài liệu**:

```java
import org.apereo.cas.client.proxy.ProxyGrantingTicketStorage;
import org.apereo.cas.client.proxy.ProxyGrantingTicketStorageImpl;
import org.apereo.cas.client.validation.Cas20ProxyTicketValidator;
import org.springframework.security.cas.web.CasAuthenticationFilter;

// FRAGMENT: không phải class độc lập.
// In-memory storage này chỉ phù hợp bài học/test; production
// phải dùng vault có TTL/cleanup, security và cluster semantics.
ProxyGrantingTicketStorage pgtStorage =
        new ProxyGrantingTicketStorageImpl();

Cas20ProxyTicketValidator validator =
        new Cas20ProxyTicketValidator("https://sso.example.org/cas");

validator.setProxyCallbackUrl(
        "https://portal.example.org/login/cas/proxyreceptor");
validator.setProxyGrantingTicketStorage(pgtStorage);

CasAuthenticationFilter casFilter = new CasAuthenticationFilter();
casFilter.setProxyReceptorUrl("/login/cas/proxyreceptor");
casFilter.setProxyGrantingTicketStorage(pgtStorage);

// Còn phải cấu hình filter's AuthenticationManager, service URL,
// CasAuthenticationProvider với đúng validator, filter ordering,
// reverse proxy route và registered service tại CAS.
```

**Tại sao cùng một storage object?** CAS gửi callback `pgtIou,pgtId` đến filter/receptor, còn validator đọc `pgtIou` trong CAS XML validation response. Nếu hai bên dùng **hai kho không chia sẻ**, validator sẽ không tìm thấy cặp cần đối chiếu.

**Với nhiều pods:** hai biến Java trỏ cùng bean **chỉ trong một JVM** không giải quyết callback pod A → validation pod B. Cần storage backend shared và atomic IOU correlation/TTL, hoặc topology đảm bảo affinity với kiểm thử failover rõ.

### 9.3. Kết nối validator với CasAuthenticationProvider

```java
import org.springframework.security.cas.authentication.CasAuthenticationProvider;

// FRAGMENT: provider chưa sẵn sàng hoạt động nếu thiếu
// ServiceProperties, AuthenticationUserDetailsService và key.
CasAuthenticationProvider provider = new CasAuthenticationProvider();
provider.setTicketValidator(validator);
provider.setServiceProperties(serviceProperties);
provider.setKey("portal-cas-proxy-provider");

// serviceProperties là bean ServiceProperties với service URL A.
// Phải bổ sung user-details mapping và đưa provider vào
// AuthenticationManager, filter đã cấu hình ở mục trước.
```

PGT sẽ chỉ có khi CAS Server/registered service cho phép proxy và callback/validation thành công. Việc gắn `Cas20ProxyTicketValidator` **không tự tạo mã bảo vệ vault** hoặc đảm bảo credentials được lưu vào KMS/Redis an toàn.

### 9.4. cleanup và expiration

Spring Security docs ghi chú cần dọn expired tickets bằng `ProxyGrantingTicketStorage.cleanup()` nếu dùng implementation có API tương ứng. Có thể có scheduler quản lý cleanup theo CAS client version; **không tự định nghĩa một cron 24 giờ rồi để PGT pending sống quá lâu**.

Cần phân biệt:

- Cleanup của **PGTIOU mapping store** do CAS client sử dụng.
- TTL/revocation của **active PGT vault** do ứng dụng quản trị.
- CAS Server **PGT expiration policy** do CAS Server enforce.

Chỉ gọi `cleanup()` cho pending IOU store không tự xóa mọi active credentials gắn session. Ngược lại, delete local PGT không thu hồi CAS PGT thật; cần định nghĩa cả hai vòng đời.

### 9.5. Đừng gán tất cả công dụng cho một implementation

`ProxyGrantingTicketStorage` của CAS client chủ yếu giải bài toán **correlate callback PGTIOU→PGT**. Nó không mặc định thực hiện đầy đủ:

- Tenant/session-specific authorization cho việc dùng PGT;
- KMS envelope encryption;
- Distributed CAS logout/revocation;
- Per-targetService allowlist;
- Multi-region consistency;
- Compliance/audit retention.

Nếu app dùng kho PGT hoạt động lâu hơn callback handshake, hãy thiết kế **một active credential vault/service facade** có chính sách riêng, chỉ expose thao tác “xin PT cho target được duyệt”, không expose raw PGT qua controller.

## 10. Xin Proxy Ticket từ PGT và bảo vệ targetService

Ví dụ A cần gọi backend B:

```text
A scope = (tenant-a, CAS-A, service-A, session-42, alice)
    |
    |  lookup active PGT (encrypted)
    |  check notExpired/notRevoked/local user still authenticated
    |  check targetService in explicit allowlist
    v
CAS /proxy?pgt=<PGT_SECRET>&targetService=<BACKEND_B_URL>
    |
    v
CAS response with PT for backend B
    |
    v
A -> backend B, sends PT via approved CAS ticket mechanism
    |
    v
B -> CAS /proxyValidate, verifies PT and trusted proxy chain
    |
    v
B applies its own authorization
```

Trong CAS protocol, `/proxy` có tham số `pgt` và `targetService`. Kênh này là **backend-to-CAS HTTPS**, nhưng vì protocol dùng query parameters, phải cấu hình **redaction ở A HTTP client, CAS Server access logs, reverse proxies, APM**. Không gửi PGT tới backend B và không echo trong URL response cho browser.

### 10.1. TargetService allowlist

PGT có thể xin PT cho nhiều targets tùy CAS proxy policies. A phải thêm local policy:

| Target | Được phép? | Lý do |
| --- | --- | --- |
| `https://api-b.example.org/cas-proxy` | Có | Backend được phê duyệt cho A |
| `https://api-c.example.org/cas-proxy` | Có khi feature cần | Ràng buộc tenant/business privilege |
| `http://internal-unknown:8080` | Không | Không dùng cleartext hoặc arbitrary host |
| `https://attacker.example/receive` | Không | Cấm arbitrary targetService từ browser |

Nếu người dùng gửi `?targetService=https://attacker.example` và A lấy nguyên chuỗi làm `/proxy` target, có nguy cơ **deputy confused / proxy credential abuse / SSRF**. Chỉ sử dụng target IDs/URLs đã allowlist bởi backend, kiểm tra authorization của user/tenant cho chức năng cần gọi.

### 10.2. Backend phải xác minh PT và proxy chain

Backend B không tin chỉ vì PT có prefix `PT-`. Nó dùng CAS `/proxyValidate` hoặc endpoint tương ứng, kiểm tra:

- Ticket được CAS cấp cho đúng `targetService` B.
- Ticket còn thời hạn, chưa sử dụng, validation success.
- Proxy chain có những proxied services được B tin, không arbitrary proxy.
- CAS server TLS/issuer và client configuration đúng.
- Principal/attributes/tenant phù hợp authorization của B.

Một số ví dụ Spring Security CAS hiển thị `acceptAnyProxy=true` cho mục đích minh họa. **Không dùng giá trị này làm mặc định production**, vì nó có thể cho phép chuỗi proxies từ nguồn không phê duyệt. Thiết kế `CasProxyDecider`, trusted proxy callback identities và service policies theo danh sách cho phép.

### 10.3. PGT lỗi không được fallback sang password hay ST cũ

Nếu `/proxy` trả lỗi “PGT invalid/expired”:

1. Mark/remove vault entry tương ứng, không làm rò PGT trong exception.
2. Không retry cùng PGT vô hạn hay tự sửa prefix.
3. Không dùng một ST đã consume thay PGT.
4. Nếu business flow cho phép, yêu cầu người dùng thực hiện lại CAS SSO/authentication để lấy ST mới, validate và xin PGT mới.
5. Nếu CAS Server outage, fail closed và hiển thị lỗi tạm thời; không cho backend B nhận một token chưa verify.

## 11. Java 17 thuần: mô phỏng pending PGTIOU, encrypted vault, TTL và logout

Chương trình sau **chạy được bằng JDK 17 trở lên**; không cần Spring/CAS dependency. Nó mô tả:

- Callback nhận `pgtIou` và `pgtId`, **chỉ stage pending**.
- **Không dùng PGT trước khi** một validation result đáng tin trả đúng IOU.
- Khi có validated IOU và authenticated principal, tạo active entry bound với **tenant, CAS server, local session và user**.
- PGT trong map được niêm phong bằng **AES-GCM** và AAD theo scope (dù demo giữ key trong memory).
- Có **pending TTL**, **active local TTL**, subject/session/tenant isolation, multiple-use read và revoke do logout.
- Không in PGT secret trong console.

**Giới hạn cực kỳ quan trọng:** đây là **mô hình local**, không phải CAS proxy protocol implementation. `receiveCallback` giả định caller/network được bảo vệ và `bindValidatedIou` giả định đã có một CAS validation response thật — chương trình **không** tự gọi CAS, không kiểm tra ST/PT, không xác minh TLS hoặc signature, không cấp PT, không có CAS Server policy/revocation. String `PGT-DEMO-SECRET` không đủ entropy. AES key tạo tại runtime chỉ minh họa phép mã hóa; production dùng KMS/HSM/envelope encryption, multi-node storage và authorization audit.

Lưu file `PgtVaultLifecycleDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class PgtVaultLifecycleDemo {
    record Scope(String tenant, String casServer, String sessionId) {}
    record Sealed(byte[] nonce, byte[] ciphertext) {}
    record Pending(Sealed sealed, Instant expiresAt) {}
    record Active(String subject, Sealed sealed, Instant expiresAt) {}

    static final class Vault {
        private final SecretKey key;
        private final SecureRandom random = new SecureRandom();
        private final Map<String, Pending> pending = new HashMap<>();
        private final Map<Scope, Active> active = new HashMap<>();

        Vault() throws Exception {
            KeyGenerator gen = KeyGenerator.getInstance("AES");
            gen.init(256);
            key = gen.generateKey();
        }

        private Sealed seal(byte[] bytes, String aad) throws Exception {
            byte[] nonce = new byte[12];
            random.nextBytes(nonce);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key,
                    new GCMParameterSpec(128, nonce));
            cipher.updateAAD(aad.getBytes(StandardCharsets.UTF_8));
            return new Sealed(nonce, cipher.doFinal(bytes));
        }

        private byte[] open(Sealed sealed, String aad) throws Exception {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key,
                    new GCMParameterSpec(128, sealed.nonce()));
            cipher.updateAAD(aad.getBytes(StandardCharsets.UTF_8));
            return cipher.doFinal(sealed.ciphertext());
        }

        private String aad(Scope scope, String subject) {
            return scope.tenant() + "|" + scope.casServer()
                    + "|" + scope.sessionId() + "|" + subject;
        }

        boolean receiveCallback(
                String iou, String pgt, Instant now, Duration ttl)
                throws Exception {
            if (iou == null || pgt == null
                    || ttl.isNegative() || ttl.isZero()
                    || pending.containsKey(iou)) {
                return false;
            }

            byte[] bytes = pgt.getBytes(StandardCharsets.UTF_8);
            try {
                pending.put(iou, new Pending(
                    seal(bytes, "pending:" + iou), now.plus(ttl)));
                return true;
            } finally {
                Arrays.fill(bytes, (byte) 0);
            }
        }

        boolean bindValidatedIou(
                String iou, Scope scope, String subject,
                Instant now, Duration localTtl) throws Exception {
            Pending record = pending.remove(iou);
            if (record == null || !now.isBefore(record.expiresAt())
                    || localTtl.isNegative() || localTtl.isZero()) {
                return false;
            }

            byte[] bytes = open(record.sealed(), "pending:" + iou);
            try {
                active.put(scope, new Active(
                    subject, seal(bytes, aad(scope, subject)),
                    now.plus(localTtl)));
                return true;
            } finally {
                Arrays.fill(bytes, (byte) 0);
            }
        }

        boolean usable(
                Scope scope, String subject, Instant now) throws Exception {
            Active record = active.get(scope);
            if (record == null || !record.subject().equals(subject)
                    || !now.isBefore(record.expiresAt())) {
                return false;
            }

            byte[] bytes = open(
                    record.sealed(), aad(scope, subject));
            try {
                // Mô phỏng khả năng đọc PGT nội bộ, KHÔNG xác minh
                // PGT còn hợp lệ ở CAS hoặc tạo Proxy Ticket.
                return bytes.length > 0;
            } finally {
                Arrays.fill(bytes, (byte) 0);
            }
        }

        void revokeLocalSession(Scope scope) {
            active.remove(scope);
        }
    }

    public static void main(String[] args) throws Exception {
        Instant now = Instant.parse("2026-11-07T00:00:00Z");
        Scope a = new Scope("tenant-a", "cas-a", "session-A");
        Scope otherSession =
                new Scope("tenant-a", "cas-a", "session-B");
        Scope otherTenant =
                new Scope("tenant-b", "cas-a", "session-A");

        Vault vault = new Vault();

        System.out.println("Callback staged: " +
            vault.receiveCallback("PGTIOU-ONE", "PGT-DEMO-SECRET",
                now, Duration.ofSeconds(10)));

        System.out.println("Before IOU validation: " +
            vault.usable(a, "alice", now));

        System.out.println("Validated IOU bound: " +
            vault.bindValidatedIou("PGTIOU-ONE", a, "alice",
                now, Duration.ofSeconds(120)));

        System.out.println("Owner can use PGT: " +
            vault.usable(a, "alice", now));
        System.out.println("Wrong subject denied: " +
            vault.usable(a, "bob", now));
        System.out.println("Other session denied: " +
            vault.usable(otherSession, "alice", now));
        System.out.println("Other tenant denied: " +
            vault.usable(otherTenant, "alice", now));

        System.out.println("PGT reusable locally: " +
            vault.usable(a, "alice", now.plusSeconds(1)));
        System.out.println("Local TTL expired: " +
            vault.usable(a, "alice", now.plusSeconds(120)));

        vault.revokeLocalSession(a);
        System.out.println("After local logout: " +
            vault.usable(a, "alice", now.plusSeconds(2)));

        vault.receiveCallback(
            "PGTIOU-LATE", "PGT-OTHER-DEMO",
            now, Duration.ofSeconds(10));
        System.out.println("Late IOU rejected: " +
            vault.bindValidatedIou(
                "PGTIOU-LATE", a, "alice",
                now.plusSeconds(11), Duration.ofSeconds(120)));
    }
}
```

Biên dịch và chạy:

```bash
javac PgtVaultLifecycleDemo.java
java PgtVaultLifecycleDemo
```

Stdout **chính xác** (nonce và AES key ngẫu nhiên, nhưng các kết quả boolean cố định):

```text
Callback staged: true
Before IOU validation: false
Validated IOU bound: true
Owner can use PGT: true
Wrong subject denied: false
Other session denied: false
Other tenant denied: false
PGT reusable locally: true
Local TTL expired: false
After local logout: false
Late IOU rejected: false
```

### 11.1. Giải thích các kiểm tra

1. `Callback staged=true`: trong mô hình, callback lưu encrypted PGT ở trạng thái pending; chưa gắn user.
2. `Before IOU validation=false`: pending không phải active credential, backend A không thể sử dụng.
3. `Validated IOU bound=true`: giả định CAS validation response đã thành công và đưa cùng IOU, nên A liên kết secret với `tenant-a/cas-a/session-A/alice`.
4. `Owner can use PGT=true`: scope + subject đúng và local TTL còn hạn; ứng dụng thật vẫn phải hỏi CAS `/proxy` để biết PGT thực sự còn hợp lệ.
5. `Wrong subject/Other session/Other tenant=false`: ngăn lấy nhầm PGT theo user/session/tenant.
6. `PGT reusable locally=true`: khác ST/PT, PGT không bị consume chỉ vì vault đọc lần đầu; ở CAS vẫn có thể hết hạn/revoked bất kỳ lúc nào.
7. `Local TTL expired=false`: thời điểm đúng ngưỡng expiry được xem là hết hiệu lực.
8. `After local logout=false`: local revoke đóng quyền dùng PGT dù thời điểm kiểm tra là trước TTL gốc.
9. `Late IOU rejected=false`: pending callback hết hạn không được promote thành credential active.

### 11.2. Vì sao demo không phải production PGT vault?

- Map chưa thread-safe/atomic cho nhiều callbacks/requests; không dùng `HashMap` cho multi-thread shared state.
- Demo đặt secret từ Java `String`, không thể zero hóa String; temporary plaintext có thể vẫn trong heap/GC. `Arrays.fill` chỉ giảm lifetime của một byte buffer.
- AES key nằm trong JVM và mất khi restart; không có KMS, key version, key rotation, encrypted backups hoặc multi-pod access.
- `receiveCallback` không xác minh client certificate của CAS/ingress, không có CAS server allowlist và không có cap cho pending map.
- `bindValidatedIou` tin caller truyền “validated” mà không thực hiện actual ST/PT validation — production phải chỉ gọi nó sau trusted validator result.
- `usable` chỉ thử decrypt + đọc bytes; **không biết CAS đã revoke PGT hay chưa**, không gọi `/proxy`, không kiểm tra targetService. Không dùng boolean này để cho qua backend authorization.
- Không có session invalidation hook/SLO listener, CAS ticket-registry expiry, TTL cleanup job, logout fan-out hoặc distributed transaction.
- Không có audit/metrics/circuit breaker và xử lý failure CAS.

Demo giúp hình dung **hai pha pending→active, confidentiality và local time/scope guards**; CAS client chuẩn và vault triển khai thực mới đảm nhiệm authentication/ticket handling.

## 12. Kiểm thử end-to-end: CAS Server, A và Backend B

### 12.1. Happy path phải quan sát được

1. Browser đăng nhập A qua CAS; CAS phát ST đúng service A.
2. A validate ST với đúng service URL và `pgtUrl` đã duyệt.
3. CAS callback HTTPS tới proxy receptor A, truyền `pgtIou` và `pgtId`; A tạo pending entry **không log secret**.
4. CAS trả `authenticationSuccess` kèm `cas:proxyGrantingTicket = PGTIOU`.
5. A xác minh XML response từ trusted CAS backend và liên kết IOU với pending; active vault bind đúng user/tenant/session.
6. A gọi một nghiệp vụ cần B; local authorization và targetService allowlist pass.
7. A lấy PGT qua vault, gọi CAS `/proxy` bằng HTTPS; CAS cấp PT B.
8. A chuyển PT cho B qua cơ chế CAS proxy ticket được hỗ trợ; B gọi CAS `/proxyValidate`, kiểm tra proxy chain.
9. B trả dữ liệu trong quyền; A trả response cho browser. **PGT không ra browser**.
10. Một nghiệp vụ B khác có thể xin **PT mới** bằng cùng PGT khi còn hiệu lực, nếu CAS/authorization cho phép.
11. User logout A/CAS; vault entry local bị xóa, CAS PGT server-side bị revoke theo policy/logout.

### 12.2. Negative tests bắt buộc

| Tình huống | Kỳ vọng |
| --- | --- |
| Callback gửi PGT nhưng ST validation fail | Không tạo active PGT |
| Callback mang IOU không có trong validation XML | Xóa/reject pending |
| Validation XML có IOU nhưng không có pending PGT | Không cấp proxy quyền |
| IOU chưa/đã hết hạn | Reject promotion |
| Duplicate IOU callback với PGT khác | Reject; không overwrite secret |
| Callback từ untrusted IP/TLS identity (theo architecture) | Reject ở ingress/mTLS/network layer |
| pgtUrl HTTP, invalid cert hoặc hostname mismatch | CAS không cấp PGT thành công |
| pgtUrl reverse proxy trả 404/302 loop | Proxy negotiation fail, điều tra routing |
| `/serviceValidate` chỉ HTTP 200 nhưng XML authenticationFailure | Không chấp nhận PGT |
| Wrong service URL khi validate ST | CAS INVALID_SERVICE; ST consume |
| TGT/CAS SSO logout nhưng local vault còn encrypted PGT | `/proxy` bị CAS reject, vault bỏ entry |
| Local user logout A nhưng CAS TGT còn | Active PGT A bị revoke theo local policy |
| PGT hết local TTL | Không decrypt/call CAS |
| PGT server-side đã expire trước local TTL | CAS reject; A invalidate entry |
| PGT của tenant A dùng cho user/tenant B | Reject local scope |
| PGT của session X dùng ở session Y | Reject local scope |
| Browser đưa `pgtId` trong request gọi backend A | Ignore/reject; không dùng raw PGT |
| A dùng `targetService` attacker chọn | Reject target allowlist |
| Backend B chấp nhận arbitrary proxy chain | Security test fail; tighten trusted proxy policy |
| PT đã validate thử lại | Reject replay |
| PT của B dùng ở C | Reject service binding |
| Redis plaintext `PGT-...` hoặc AOF dump lộ secret | Security QA FAIL |
| APM/WAF/Nginx log callback query chứa `pgtId` | Security QA FAIL |
| CAS /proxy backend request log raw `pgt` | Security QA FAIL |
| Pending map flood với 100k fake callbacks | Bounded rejection/rate limit, no heap exhaustion |
| CAS callback tới pod A, validator tới pod B | IOU correlation qua shared storage hoặc fail closed |
| Hai validation workers bind cùng IOU | Chỉ một transaction atomic thành công |
| KMS key revoked/unavailable | Fail closed, không trả plaintext/retry insecure |
| Corrupt ciphertext/auth tag | AEAD decrypt fail, revoke entry/audit |
| Clock tiến tới đúng `expiresAt` | Expired, không sử dụng |
| Logout/SLO đến đồng thời với call `/proxy` | Consistency/race behavior theo policy, không để credential đã revoked dùng lại |
| PGT còn trong backup sau xóa active | Retention/cryptographic erase/incident policy được xem xét |

### 12.3. Unit test kho + integration test protocol là hai cấp

**Vault unit test** chứng minh TTL, encryption, IOU correlation, scope isolation, concurrency/revoke. Nó **không** chứng minh CAS Server thật đã cấp PGT đúng hoặc backend B đã validate PT.

**CAS integration test** chứng minh service registry, TLS callback, XML `cas:proxyGrantingTicket`, `/proxy` semantics, CAS Server PGT expiration, PT single-use và trusted proxy chain. Không viết CAS mock “luôn authenticationSuccess” rồi tuyên bố security integration PASS.

### 12.4. Kiểm thử concurrency và restart

Một test đáng làm:

```text
CAS Server callback PGTIOU-X vào pod A
            |
            v
Shared pending store commit + TTL
            |
CAS /serviceValidate response được xử lý ở pod B
            |
            v
B lookup/consume PGTIOU-X atomically
            |
            v
B bind user/session/tenant -> encrypted active PGT
            |
            v
Pod C đọc active PGT theo đúng scope để xin PT
```

Nếu có session affinity, phải test cả failover/callback vào pod khác. Trong trường hợp pending record mất do restart trước promotion, kết quả **fail closed**, user/caller cần flow xác thực/proxy grant mới; **không dựng PGT từ PGTIOU** hoặc chấp nhận username từ query callback.

## 13. Logging và vận hành không làm lộ PGT

### 13.1. Mẫu audit nên có

```json
{
  "event": "cas_pgt_vault_transition",
  "service": "portal",
  "tenant": "tenant-a",
  "cas_server_id": "corp-cas",
  "state": "ACTIVE",
  "reason_code": "IOU_CORRELATED",
  "local_expiry_seconds": 1200,
  "request_id": "evt-742"
}
```

Dữ liệu là **ví dụ giả lập**. Không đưa `pgtId`, `pgtIou`, `ticket`, TGC, session cookie, principal email/NameID hoặc HTTP query thô vào metrics/audit thường. Hash/HMAC public-friendly references vẫn phải đánh giá khả năng linkability và privacy. Dùng bounded labels từ allowlist để tránh cardinality explosion.

### 13.2. Những nơi có thể vô tình lộ PGT

- Nginx `$request_uri` hoặc ingress default access log chứa callback query.
- APM/trace http.url đầy đủ chứa `pgtId=...` hoặc CAS `/proxy?pgt=...`.
- HTTP client debug log request URL/query.
- `Exception.getMessage()` có full URL query.
- Cache debug tooling, Redis CLI transcripts, AOF/snapshots.
- ORM `toString()` / JSON serialization in error response.
- Heap dumps, crash dumps, support archives, unencrypted backups.
- Code review screenshots, cURL history hoặc CI test artifacts.

**Thiết lập redaction ở từng tầng**. Việc app logger không in PGT là chưa đủ nếu ingress hoặc CAS Server vẫn ghi query string. Mọi test log/trace cần dùng fake credentials và có scanner để phát hiện `pgtId=`, `pgt=`, `PGT-`, `PGTIOU-` trong fields không được phép.

### 13.3. Metrics phù hợp

| Metric | Ý nghĩa |
| --- | --- |
| `cas_pgt_callback_total{result}` | Callback success/invalid/duplicate |
| `cas_pgt_iou_bind_total{result}` | Tỉ lệ correlate IOU |
| `cas_pgt_pending_entries` | Phát hiện pending growth/flood |
| `cas_pgt_active_entries` | Capacity/retention, không lộ user labels |
| `cas_pgt_expiry_total{reason}` | Local TTL/CAS server rejection/revoke |
| `cas_proxy_ticket_request_total{result,target}` | CAS `/proxy` thành công/thất bại |
| `cas_proxy_backend_validation_total{result}` | Backend `/proxyValidate` failures |
| `cas_pgt_decrypt_failure_total` | KMS/key mismatch/ciphertext tamper |
| `cas_pgt_storage_latency_seconds` | Redis/DB/KMS access latency |

Không gắn raw IOU/PGT, session key, NameID, email hoặc arbitrary `targetService` do browser gửi vào metric labels.

## 14. Incident response khi nghi PGT bị lộ

1. **Khoanh vùng:** CAS server, services, tenants, sessions, impacted targets và time window; không copy raw PGT qua chat/ticket.
2. **Dừng sử dụng:** revoke local vault entries theo scope, chặn proxy capability từ A nếu cần, disable affected service registration/target policy khi phù hợp.
3. **Thu hồi phía CAS:** phối hợp CAS admin invalidate TGT/PGT/SLO sessions hoặc endpoint quản trị được hỗ trợ; chỉ xóa local Redis row là chưa đủ.
4. **Đánh giá PT đã cấp:** backend logs/proxy chain/authorization events đã redacted, thời hạn PT, possible unauthorized actions; PT thường one-time nhưng có thể đã được dùng.
5. **Khôi phục an toàn:** sửa nguyên nhân lộ (access logging, APM, Redis ACL, mTLS, compromised key), rotate encryption key nếu cần, yêu cầu reauthentication/regrant.
6. **Giám sát:** phát hiện bất thường CAS `/proxy` requests, targetService list, concurrent requests, repeated invalid PGT, unusual proxy chain.
7. **Kết thúc:** test toàn bộ callback/TTL/revoke, xác minh không còn raw secrets trong logging pipeline, cập nhật runbook và ticket-retention policy.

**Không lấy “đã re-encrypt old PGT” làm bằng chứng secret không còn lộ**: nếu credential đã bị sao chép, chỉ CAS server-side revocation (hoặc expiration thực) mới ngăn bản sao đó tiếp tục được dùng.

## 15. Những lỗi thiết kế phổ biến

| Anti-pattern | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Lưu PGT plaintext trong HttpSession/browser cookie | Browser/session leak; PGT có thể được dùng nhiều lần | Server-side encrypted vault, session-bound authorization |
| Lưu PGT vào query để gửi frontend | Ticket leak qua logs/referrer/history | Chỉ backend gọi CAS `/proxy` |
| Dùng `PGTIOU` thay `PGT` ở CAS /proxy | IOU chỉ correlation token | Lấy PGT từ callback đã correlate |
| Gán PGT từ callback trực tiếp cho username query | Callback có thể giả; chưa có validation success | Pending state + trusted CAS validation result |
| Lưu PGT theo username làm map key duy nhất | Cross-session/cross-tenant collision | Composite scope và kiểm tra quyền |
| Một global PGT cho mọi tenants | Cross-tenant delegated access | Per-tenant/CAS/service isolation |
| TTL active vô hạn vì CAS tự revoke | Local leak/backup exposure, SLO loss | Local upper-bound + cleanup + server revocation |
| Coi local TTL chưa hết là PGT server còn hợp lệ | CAS logout/expiry có thể đến sớm hơn | CAS `/proxy` result là nguồn truth, fail closed |
| Chỉ xóa Redis sau PGT compromise | Bản PGT đã copy vẫn dùng được tại CAS | Revoke CAS PGT/TGT + investigate |
| Dùng `ProxyGrantingTicketStorageImpl` in-memory cho nhiều pods | Callback/validator không chung state | Shared encrypted store + atomic IOU binding |
| Không gọi cleanup cho pending records | Memory growth, orphaned secrets | TTL, bounded pending entries, cleanup |
| Bật `acceptAnyProxy=true` ở backend | Chấp nhận proxy chain không phê duyệt | Trusted proxy allowlist/decider |
| CAS callback pgtUrl HTTP hoặc self-signed cert trust-all | PGT bị lộ/intercept | HTTPS + cert validation, approved callback |
| Bỏ logging nhưng APM vẫn capture request.url | Raw PGT trong traces | Redaction ở mọi tầng |
| Cho browser chọn targetService arbitrary | Confused deputy/SSRF | Service/target allowlist và user authorization |
| Bảo vệ DB bằng Base64 | Không mã hóa | AEAD + KMS + ACL + backups |
| Reuse PT nhiều calls | PT one-time, sẽ replay fail | Xin PT mới khi cần |
| Rotate KMS key rồi tưởng CAS PGT đã đổi | KMS và CAS credential khác nhau | Revoke/regrant CAS khi PGT compromise |
| Đồng bộ CAS/TGT expiry = HttpSession TTL | Hai hệ thống vòng đời khác nhau | Policy riêng + sự kiện revoke/timeout |

## 16. Checklist production

- [ ] Đã xác định khi nào service A cần Proxy Authentication thay vì service ticket login thông thường.
- [ ] PGT, PGTIOU, PT, ST, TGT/TGC và local session được phân biệt đúng.
- [ ] CAS Server/service registry cho phép proxy theo đúng trust và targetService policies.
- [ ] Service A validate ST/PT bằng HTTPS trusted CAS Server trước khi link PGT với principal.
- [ ] `pgtUrl` là public HTTPS callback đã duyệt; TLS/hostname/certificate được CAS xác minh.
- [ ] `Cas20ProxyTicketValidator.proxyCallbackUrl` khớp local `CasAuthenticationFilter.proxyReceptorUrl` sau proxy routing.
- [ ] Callback GET `pgtIou,pgtId` chỉ ghi pending encrypted, không tạo session/role.
- [ ] IOU được correlate với CAS authenticationSuccess XML; pending record được consume atomically, không duplicate overwrite.
- [ ] Active vault key có tenant, CAS server, local authenticated session/service và subject binding.
- [ ] Kho PGT có encryption AEAD/KMS, key version/AAD/nonce đúng, TLS+ACL+backup policies.
- [ ] Pending TTL ngắn, bounded count, cleanup job và duplicate/race controls.
- [ ] Active local TTL tối đa theo policy, không giả định CAS PGT server TTL cố định.
- [ ] Local logout/session expiry/CAS SLO/tenant unlink/compromise đều dẫn tới revoke đúng scope.
- [ ] CAS Server PGT logout expiration được test trên release thực tế.
- [ ] CAS `/proxy` result invalid/expired làm xóa local entry; không fail open hoặc tự tái dùng ST cũ.
- [ ] Backend B kiểm chứng PT bằng `/proxyValidate` và trusted proxy chain; không `acceptAnyProxy=true` không kiểm soát.
- [ ] TargetService allowlist + per-user authorization trước khi A xin PT.
- [ ] Multi-node/region callback, pending store, active vault và CAS ticket registry có atomicity/consistency phù hợp.
- [ ] Ingress/WAF/APM/HTTP client/CAS Server logs đều redact PGT/IOU/ticket/cookies/PII.
- [ ] Không xuất PGT cho browser, JavaScript, cookie, API response hoặc error page.
- [ ] Backup/restore/retention/encryption key loss và incident response đã được thử.
- [ ] Negative tests cho callback forged, IOU mismatch, expired, replay, wrong tenant/session, stale CAS, tampered ciphertext và SLO.
- [ ] Cấu hình/class/packages được kiểm tra theo Spring Security và CAS client versions thực tế.

## 17. Câu hỏi ôn tập

**1. PGT và Service Ticket khác nhau lớn nhất ở đâu?**  
PGT có thể dùng nhiều lần để xin PT trong thời gian CAS cho phép; ST là ticket đăng nhập dành riêng service và chỉ hợp lệ cho một lần validation.

**2. PGTIOU có dùng gọi `/proxy?pgt=...` được không?**  
Không. PGTIOU chỉ ghép callback `pgtId` với `cas:proxyGrantingTicket` trong XML validation result. Dùng **PGT** thật trong backend CAS /proxy request.

**3. Vì sao CAS Server callback pgtUrl trước rồi XML response mới về A?**  
CAS cần chuyển PGT secret qua HTTPS direct callback, còn XML trả một IOU để A liên kết secret với ticket validation result/principal. Không đưa PGT trực tiếp qua browser.

**4. Có thể gán PGT ngay khi callback GET mang `pgtId` không?**  
Không. Callback có thể bị giả; cần pending store và IOU correlation sau successful validation từ trusted CAS.

**5. PGT còn local TTL 10 phút nhưng user vừa logout CAS, có dùng để xin PT được không?**  
Không. CAS protocol yêu cầu PGT hết hiệu lực khi client logout CAS. Local store phải revoke khi có signal và xử lý CAS rejection.

**6. Kho PGT lưu theo username có đủ không?**  
Không. Cần phân biệt tenant, CAS server, service, local authenticated session và user identity tránh cross-tenant/session delegated access.

**7. Nếu chỉ hash PGT thì sao xin Proxy Ticket?**  
CAS `/proxy` cần PGT plaintext; hash một chiều không thể khôi phục. Dùng encrypted vault hoặc credential broker để gửi PGT từ backend được phép.

**8. PGT stored encrypted trong Redis có nghĩa là CAS đã revoke khi Redis key bị xóa?**  
Không. Xóa Redis chỉ ngăn app dùng; bản sao PGT bên ngoài có thể còn hiệu lực tại CAS tới khi server revoke/expire.

**9. Vì sao `ProxyGrantingTicketStorage` phải được chia sẻ giữa filter và validator?**  
Filter nhận IOU/PGT từ CAS callback, validator có IOU trong XML; cùng store giúp ghép đúng secret. Với multi-pod cần distributed shared store hoặc topology được thiết kế/test.

**10. Một callback pgtUrl HTTPS có tự chứng minh người gọi là CAS Server không?**  
Không. TLS ở A xác thực endpoint A với caller, trừ mTLS/caller authentication. A phải giới hạn inbound và dùng IOU từ trusted validation response.

**11. Có nên dùng `acceptAnyProxy=true` ở backend B không?**  
Không làm default. Backend cần kiểm soát danh sách trusted proxy services/chain theo policy.

**12. PT có thể dùng cho 10 lần REST calls B không?**  
Không theo semantics ticket single-use. A cần cấp mới PT hoặc có thiết kế authentication cache riêng theo contract không làm bypass CAS validation.

**13. CAS Server và app A khác nhau về TTL PGT ra sao?**  
CAS quyết định PGT server validity; A áp local upper-bound và revoke/cleanup. Local TTL không kéo dài được credential đã hết ở CAS.

**14. Có thể dùng `TGT` thay PGT để gọi CAS /proxy?**  
Không. TGT là CAS SSO grant, không phải `pgt` API parameter cho service A. TGC thuộc browser CAS origin.

**15. Khi KMS key bị lộ thì xử lý thế nào?**  
Đánh giá ciphertext và PGT có thể bị decrypt; rotate KMS/key material, re-encrypt nơi an toàn, đồng thời revoke/regrant các CAS PGT bị ảnh hưởng nếu có nguy cơ secret đã lộ.

**16. Nên làm gì khi CAS callback đã stage PGT nhưng validation XML không có IOU?**  
Không promote; xóa pending theo TTL hoặc rollback cleanup, điều tra callback/certificate/service policy, không tự chọn PGT “mới nhất”.

## 18. Tài liệu chuẩn và tham khảo

- [Apereo CAS — CAS Protocol 2.0 Specification](https://apereo.github.io/cas/8.0.x/protocol/CAS-Protocol-V2-Specification.html): `pgtUrl`, `pgtId`, `pgtIou`, `/proxy`, PGT multi-use, expire on CAS logout và ticket validation.
- [Apereo CAS — CAS Protocol 3.0 Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): `/serviceValidate`, `/proxyValidate`, `/proxy`, PGTIOU và proxy chain; development documentation có thể không khớp production release.
- [Apereo CAS — Proxy Authentication](https://apereo.github.io/cas/development/authentication/Configuring-Proxy-Authentication.html): proxy-enabled registered services, callback TLS, PGT issuance, alternative encrypted PGT return extension; kiểm tra đúng release.
- [Apereo CAS — Proxy Granting Ticket Policies](https://apereo.github.io/cas/development/ticketing/Configuring-Ticket-Expiration-Policy-PGT.html): expiration settings theo phiên bản CAS, không đoán runtime default.
- [Spring Security — CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): `ProxyGrantingTicketStorage`, `Cas20ProxyTicketValidator`, `CasAuthenticationFilter`, proxy callback/storage wiring và reminder về cleanup.
- [Spring Security — CasAuthenticationFilter Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html): `proxyReceptorUrl`/`proxyGrantingTicketStorage` và filter role.
- [Spring Security — CAS Modules](https://docs.spring.io/spring-security/reference/modules.html): `spring-security-cas` dependency.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): key lifecycle/KMS/storage/revocation.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): secret store ACL, rotation và audit.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): tránh log secrets/tickets, structured audit.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): trusted HTTPS và certificates.

**Ghi nhớ:** **PGT là bí mật ủy quyền dùng lại để xin Proxy Tickets**, không phải ST một lần và không phải `PGTIOU`. Service A chỉ cất PGT sau **callback HTTPS + IOU correlation với kết quả CAS ticket validation đáng tin**, lưu trong vault **mã hóa, phân vùng theo tenant/user/session/CAS server, có TTL, cleanup và revoke**. CAS Server phải từ chối PGT khi CAS logout/expiry; xóa local storage không tự revoke bản sao PGT ở CAS. Backend B chỉ nhận **PT đúng targetService và proxy chain được duyệt**. Bí mật PGT tuyệt đối không được lộ qua browser, callback logs, Redis dumps, APM, HTTP query logs hay support artifacts.