# Tạo và thu hồi API key cho tài khoản dịch vụ trong Spring Security

**API key** là một credential bí mật cho phép ứng dụng hoặc tiến trình máy truy cập API theo một danh tính và chính sách đã cấp. Trong hệ thống Spring Security, API key cho **tài khoản dịch vụ (service account)** thường dùng để xác thực job ETL, worker, backend tích hợp, hệ thống giám sát hoặc một ứng dụng gọi ứng dụng khác. Tạo được một chuỗi ngẫu nhiên mới chỉ là bước đầu; một triển khai đầy đủ phải quản lý **chủ sở hữu, tenant, scopes, hạn dùng, lưu verifier, kiểm chứng từng request, xoay vòng, thu hồi tức thời theo chính sách và audit**.

Bài thực hành này dẫn từ thiết kế dữ liệu đến REST API, Spring Security Servlet filter, Java 17 chạy độc lập, ví dụ SQL, kiểm thử và quy trình vận hành. Nó phân biệt **credential bí mật** với **identity/service account** và **quyền truy cập tài nguyên**, tránh biến việc sở hữu một key thành quyền admin vô hạn.

**Kết quả học tập:** bạn có thể phát hành API key với entropy cao, **chỉ trả raw key một lần**, lưu verifier thay vì plaintext, cấu hình xác thực stateless cho đường dẫn service API, áp quyền least privilege, tạo key thay thế không gián đoạn và thu hồi key cũ có kiểm chứng. Các ví dụ học tập không phải hệ thống production đã hoàn chỉnh; chỗ nào cần database, KMS, queue, Spring Boot hoặc nghiệp vụ bổ sung sẽ được nói rõ.

## 1. Ba khái niệm cần tách biệt

| Khái niệm | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **Service account** | `svc-order-sync` thuộc tenant A | Danh tính máy, trạng thái, chủ quản, quyền nền |
| **API key record** | Key ID công khai `9c...`, expiry và scopes | Một credential thuộc account, có thể thu hồi riêng |
| **Raw API key** | `sk_live_v1_{keyId}.{randomSecret}` | Bí mật bearer mà caller chứng minh đang sở hữu |
| **Authentication** | Principal `svc-order-sync` đã kiểm chứng | Xác định service nào gọi |
| **Authorization** | `orders:read` trên tenant A | Kiểm endpoint/resource/action có được phép |
| **Actor quản trị key** | Người quản trị hoặc workload có `keys:manage` | Ai có quyền tạo/thu hồi credential |

Một service account có thể sở hữu **nhiều API key** để phục vụ rotation. Thu hồi **một key** không nhất thiết khóa toàn bộ account; vô hiệu hóa account phải khiến **mọi key** của nó mất hiệu lực, kể cả key chưa hết hạn.

**API key không phải password của nhân viên**, không phải tài khoản con người và thường không có MFA ở mỗi lần gọi. Đừng cho phép một service key tự đăng nhập trang quản trị tương tác trừ khi đó là một giao thức riêng được thiết kế có chủ đích.

### Mô hình quyền hiệu lực

Một API key không được phép tự nâng quyền vượt service account. Có thể mô hình hóa:

~~~text
Effective permissions =
    service_account.permissions
  ∩ api_key.scopes
  ∩ tenant/resource policy
  ∩ endpoint/action requirements
~~~

Nếu account chỉ được `orders:read`, việc client gửi `scope=orders:write` khi xin key không thể tạo quyền write. Nếu account bị disabled hoặc tenant bị suspend, mọi request phải bị từ chối, bất kể chữ ký/digest của key còn hợp lệ.

## 2. Bài toán và yêu cầu chấp nhận

Giả sử hệ thống có worker `order-exporter` cần **đọc danh sách đơn hàng** của tenant A, nhưng không được xóa hoặc sửa đơn hàng. Hệ thống cần:

1. Quản trị viên đủ quyền tạo service account thuộc tenant A.
2. Người quản trị tạo API key với nhãn và scope `orders:read`, TTL 30 ngày theo policy.
3. Server sinh secret bằng CSPRNG, lưu **hash/HMAC verifier**, trả raw key **chỉ trong response lúc tạo**.
4. Worker lưu raw key trong secret manager; request mang key qua HTTPS, không đặt trong URL.
5. Server xác thực key, kiểm key active, chưa expired, owner account active, tenant và scope.
6. Worker chuẩn bị thay key trước khi key cũ hết hạn.
7. Quản trị viên revoke key cũ; các requests dùng key cũ sau thời điểm thu hồi bị từ chối.
8. Audit ai tạo/thu hồi, key ID, reason, thời điểm và kết quả; **không ghi raw key**.

### Tiêu chí kiểm thử

| Thao tác | Kết quả mong đợi |
| --- | --- |
| Tạo key hợp lệ | 201, trả `keyId`, `apiKey` một lần, `expiresAt` |
| Tạo bởi actor thiếu quyền | 403, không phát hành key |
| Tạo scope vượt quyền account | 403/422 theo contract, không mở rộng quyền |
| GET bằng key hợp lệ có scope | 200 nếu resource policy cũng cho phép |
| GET bằng key sai/không tồn tại | 401 generic |
| POST yêu cầu scope write nhưng key chỉ có read | 403 |
| Key hết hạn | 401 |
| Key revoked | 401 ngay khi hệ thống đã nhận state mới |
| Account disabled | Key còn digest đúng cũng không được phép |
| Key cũ revoked, key mới active | Cũ 401; mới vẫn gọi được |
| Request không có key trên machine API | 401 |
| Key bị lộ trong log/repo | Cần revoke/rotate và điều tra, không coi “đã xóa log” là đủ |

Lưu ý: **401** là chưa xác thực hoặc credential không hợp lệ, **403** là đã xác thực nhưng không đủ quyền. Nếu chính sách chống information disclosure yêu cầu, body cho các lý do key invalid khác nhau nên được giữ chung.

## 3. Chọn API key đúng chỗ, không lạm dụng

API key phù hợp với một số machine-to-machine integrations khi hệ thống quản lý vòng đời credential và quyền hạn tương xứng. Tuy nhiên, nó là **bearer secret**: ai có secret có thể dùng nó cho tới khi expired/revoked hoặc bị một cơ chế bổ sung ngăn chặn.

Không nên chỉ dựa vào API key cho tài nguyên tài chính/đặc biệt nhạy cảm nếu rủi ro yêu cầu độ bảo đảm cao hơn. Cân nhắc **mTLS**, OAuth2 client credentials với short-lived access tokens, workload identity/federation hoặc chữ ký request có replay defense khi threat model phù hợp.

| Nhu cầu | Công cụ nên cân nhắc |
| --- | --- |
| Một worker nội bộ đơn giản có ít scopes | API key ngẫu nhiên + rotation/revocation |
| Nhiều workloads trên cloud có managed identity | Workload identity thay secret tĩnh |
| Client credentials và token ngắn hạn | OAuth2 client credentials |
| Ràng buộc client vào chứng chỉ | mTLS hoặc certificate-bound tokens |
| User đăng nhập với MFA | OIDC/SAML/password + MFA, không phải service API key |
| Yêu cầu chống replay ở tầng message | Signed requests với nonce/timestamp phù hợp |

Mục tiêu là dùng credential có vòng đời quản lý được, không áp một giải pháp cho mọi hệ thống.

## 4. Threat model trước khi triển khai

| Mối đe dọa | Điểm xâm nhập | Biện pháp |
| --- | --- | --- |
| Secret bị lộ | Git, CI log, stack trace, support ticket | Show once, secret manager, scanning, redaction, revoke |
| Đoán key hàng loạt | Endpoint public | CSPRNG 256 bit, rate limit, audit |
| Stolen key dùng ngoài hệ thống | Máy của attacker | TTL ngắn hợp lý, scope hẹp, optional mTLS/IP restriction |
| Key hợp lệ nhưng vượt tenant | Thiếu resource authorization | Account/tenant/resource checks ở backend |
| Privilege escalation lúc tạo key | Người xin tự chọn scope quá rộng | Quyền quản trị + scope intersection |
| Key đã revoke vẫn dùng được | Cache auth stale | Cache invalidation và upper bound TTL |
| Key hết hạn vẫn hợp lệ | Chỉ check digest, quên expiry | Enforce expiry ở mỗi authentication |
| Tài khoản disabled nhưng key còn hoạt động | Không kiểm account state | Check account active trong verification |
| Database/secret store mất kết nối | Fallback cho qua | Fail closed, báo 503 khi thích hợp |
| API key dùng như admin token | Phân loại credential sai | Tách admin management auth khỏi service API |
| Replay một request đã ghi nhận | Bearer secret không ràng buộc request | TLS + cân nhắc mTLS/signed request nếu cần |
| Log injection | Label/header chứa CRLF | Structured logs, validation, allowlist fields |

Không có “API key tuyệt đối an toàn” chỉ vì định dạng nhìn dài. Cần bảo vệ **từ lúc phát hành đến khi thu hồi**, cả ở client, transit, server, storage và operations.

## 5. Kiến trúc end-to-end

~~~text
Quản trị viên đã đăng nhập (admin OIDC/session + MFA theo policy)
        |
        | POST /admin/service-accounts/{accountId}/keys
        | {label, scopes, expiresAt}
        v
Management API
        | Verify actor permission + tenant ownership
        | Validate scope <= account permission policy
        | Generate random key secret
        | Store keyed verifier, metadata, expiration, audit
        v
201 Created {keyId, apiKey ONE TIME, expiresAt}
        |
        | Người triển khai chuyển raw key vào Secret Manager
        v
Worker / service client
        | HTTPS Authorization: ApiKey <raw-secret>
        v
Spring Security machine API (/svc/**)
        | Parse public keyId / secret
        | Lookup key metadata by ID
        | Verify HMAC/digest (constant-time comparison)
        | Check revokedAt, expiry, account active, tenant
        | Construct authenticated service principal
        v
Authorization: key scopes + account entitlement + resource policy
        |
        +--> 200 data (nếu được phép)
        +--> 401 unknown/invalid/revoked/expired
        +--> 403 authenticated but insufficient permissions
~~~

**Ranh giới quản trị và thực thi:** endpoint tạo/thu hồi key phải sử dụng cơ chế xác thực quản trị đủ mạnh, không mặc định cho key có quyền đối với `/svc/**` tự mở rộng scopes của chính nó.

### Đề xuất tách endpoints

| Endpoint | Caller | Ý nghĩa |
| --- | --- | --- |
| `POST /admin/service-accounts/{id}/keys` | Actor có quyền quản lý keys | Tạo key cho account |
| `GET /admin/service-accounts/{id}/keys` | Actor được phân quyền | Liệt kê **metadata**, không raw secret |
| `DELETE /admin/service-accounts/{id}/keys/{keyId}` | Actor có quyền thu hồi | Revoke key |
| `POST /admin/service-accounts/{id}/keys/{keyId}/rotate` | Actor đủ quyền, tùy API contract | Phát hành key mới, quản lý overlap |
| `GET /svc/orders/{id}` | Service với key active và scope | Đọc dữ liệu theo tenant/resource |

Thao tác `rotate` không nên tự âm thầm làm mất key cũ trước khi caller đã lưu key mới và triển khai thành công, trừ khi policy là emergency rotation. Quy trình rotate cần **trạng thái, timeline, trách nhiệm và rollback plan** rõ.

## 6. Định dạng key: public ID + secret đủ entropy

Một định dạng thực dụng:

~~~text
sk_live_v1_{keyId}.{randomSecret}
~~~

Trong đó:

- `sk_live_v1_` là prefix giúp nhận diện loại key/môi trường/phiên bản cú pháp, **không phải bằng chứng bảo mật**.
- `keyId` là UUID công khai, dùng tìm metadata trong DB; nó **không phải secret**.
- `randomSecret` chứa tối thiểu 32 bytes từ CSPRNG (256 bit), encode base64url không padding thành 43 ký tự.
- Dấu `.` ngăn phần ID và secret, giúp parse không phải thử tất cả records.

Ví dụ giả, **không phải credential thật**:

~~~text
sk_live_v1_01234567-89ab-4def-8012-3456789abcde.{43-base64url-chars}
~~~

Không dùng `UUID.randomUUID()` một mình như toàn bộ secret nếu policy yêu cầu entropy cao và có thể nâng cấp. UUID v4 có entropy thấp hơn 256-bit random token; UUID phù hợp làm **public identifier**, còn secret nên được sinh riêng.

Tránh: mật khẩu người dùng, timestamp, incremental number, MAC address, account ID, tên host, `Random` của Java hoặc chuỗi do client tự cung cấp làm secret.

**Khả năng đoán:** nếu secret thực sự có 256 bit entropy độc lập, brute-force trực tiếp là không khả thi về thực tiễn. Nhưng key bị trộm qua log/CI/git vẫn có thể dùng ngay; entropy không bảo vệ khỏi rò rỉ.

### Không gộp quyền vào string token

Raw key không cần chứa role/admin/tenant có thể sửa được. Server lưu metadata key → service account → tenant và scopes, rồi kiểm từ kho đáng tin. Một token dạng opaque random secret đơn giản giúp **thu hồi ngay theo ID** mà không cần JWT blacklist.

## 7. Thiết kế cơ sở dữ liệu có tenant isolation

Ví dụ PostgreSQL (schema minh họa, cần điều chỉnh migration, index, audit fields và RLS cho môi trường thực):

~~~sql
CREATE TABLE service_account (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name VARCHAR(120) NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('ACTIVE', 'DISABLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, tenant_id)
);

CREATE TABLE service_api_key (
    id UUID PRIMARY KEY,
    service_account_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    label VARCHAR(120) NOT NULL,
    verifier BYTEA NOT NULL,
    verifier_key_version SMALLINT NOT NULL,
    created_by_actor_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    FOREIGN KEY (service_account_id, tenant_id)
        REFERENCES service_account (id, tenant_id),
    CHECK (expires_at > created_at)
);

CREATE TABLE service_api_key_scope (
    key_id UUID NOT NULL REFERENCES service_api_key(id),
    scope VARCHAR(120) NOT NULL,
    PRIMARY KEY (key_id, scope)
);

CREATE INDEX idx_api_key_account
    ON service_api_key (tenant_id, service_account_id);
~~~

Ý nghĩa các ràng buộc:

- ID key có thể truy vấn trực tiếp bằng primary key; **không tìm bằng raw secret**.
- `verifier BYTEA` lưu kết quả HMAC/digest, không lưu full key.
- `verifier_key_version` cho phép phiên bản hóa pepper key phía server.
- Composite foreign key đảm bảo key không gắn account thuộc tenant khác.
- `revoked_at` nullable là trạng thái thu hồi bền vững.
- `expires_at` luôn có giá trị để chặn key vĩnh viễn ngoài ý định.
- Scope nằm ở bảng riêng cho audit/review/quản lý quyền.
- `last_used_at` chỉ là metadata vận hành; không cập nhật đồng bộ trên mọi call nếu làm tăng contention.

**Một câu lệnh xóa row chưa chắc tốt hơn revoke.** Lưu `revoked_at` phục vụ audit, incident response và chống cấp lại nhầm. Raw secret **không được hồi sinh** chỉ vì admin đặt lại cột `revoked_at=NULL`.

Nếu dùng soft-delete account, phải bảo đảm verifier luôn kiểm trạng thái account. Có thể bổ sung RLS cho admin queries và composite checks cho tenant trong application/service layer.

## 8. Verifier: tại sao không lưu plaintext API key?

Nếu database lưu nguyên chuỗi `sk_live_...`, một bản sao DB bị lộ đủ để attacker dùng mọi key active. Với token ngẫu nhiên entropy cao, có thể lưu **cryptographic digest** của token thay plaintext, hoặc dùng **HMAC-SHA-256** với khóa bí mật (pepper) do server/KMS quản lý.

Một quy trình HMAC có public key ID:

~~~text
raw key: prefix + keyId + "." + randomSecret

lookup: keyId -> keyRecord
verify:
    presentedVerifier = HMAC-SHA256(pepper, keyId + "." + randomSecret)
    compare constant-time to keyRecord.verifier

then:
    check expiresAt, revokedAt, serviceAccount.status,
    tenant/scope/resource policy
~~~

**HMAC khác encryption:** server không giải mã được raw secret từ verifier. API `GET /keys` phải chỉ trả metadata. Nếu mất raw key, giải pháp là **tạo key mới**, không phải “xem lại mật khẩu”.

### SHA-256 có đủ không?

Với secret thực sự ngẫu nhiên 256-bit, SHA-256 digest nhanh là một verifier hợp lý: attacker không thể thử một dictionary người dùng thường chọn như với password. HMAC với server-side pepper tăng lớp bảo vệ khi database bị lộ mà KMS key chưa lộ.

So sánh:

| Loại credential | Entropy thường gặp | Lưu verifier |
| --- | --- | --- |
| Password do người dùng chọn | Thấp/khó đoán | Slow salted password hash (Argon2id/bcrypt/PBKDF2 theo policy) |
| API key sinh từ CSPRNG 32 bytes | Cao, 256 bit | SHA-256 digest hoặc HMAC-SHA-256 keyed verifier |
| JWT signed token | Mang claims/chữ ký | Xác minh chữ ký/issuer/audience/expiry; revocation có cơ chế riêng |
| mTLS client certificate | Public/private key cryptography | Chứng chỉ và trust policy, không phải API key hash |

**Pepper rotation:** nếu thay HMAC key mà không còn raw API key, bạn không thể tính lại verifier dưới pepper mới. Giải pháp là giữ pepper versions cho các key chưa expired trong KMS, ép rotate/reissue keys, hoặc revoke theo kế hoạch. Không chỉ đổi giá trị env rồi khiến mọi key hiện tại đồng loạt hỏng mà không báo trước.

**Constant-time comparison:** dùng `MessageDigest.isEqual(byte[],byte[])` cho verifier fixed-length; không dùng `Arrays.equals` hoặc so sánh string khi bí mật liên quan. Kiểm key length/cú pháp trước khi tính HMAC để tránh xử lý input quá lớn; so sánh constant-time không tự xóa timing khác do DB lookup, trạng thái account hoặc network.

## 9. Phát hành khóa: cấp đúng chủ và quyền

Một API tạo key theo hợp đồng minh họa:

~~~http
POST /admin/service-accounts/123e4567-e89b-42d3-a456-426614174000/keys HTTP/1.1
Authorization: Bearer <admin-access-token>
Content-Type: application/json

{
  "label": "order-export-prod",
  "scopes": ["orders:read"],
  "expiresInDays": 30
}
~~~

Response lần đầu **duy nhất** (giá trị placeholder):

~~~http
HTTP/1.1 201 Created
Cache-Control: no-store
Content-Type: application/json

{
  "keyId": "123e4567-e89b-42d3-a456-426614174999",
  "apiKey": "<new-raw-key-shown-once>",
  "label": "order-export-prod",
  "scopes": ["orders:read"],
  "expiresAt": "2026-12-06T00:00:00Z"
}
~~~

Đừng đưa full key vào `Location`, query, audit event, tracing baggage, email thông thường hoặc log response. Nếu UI cần nút copy, chỉ hiện tại trang kết quả tạo key, cảnh báo người quản trị lưu vào nơi an toàn; **không có API “show again”**.

Quy trình server:

1. Xác thực actor quản trị qua kênh riêng; áp MFA/step-up nếu policy.
2. Kiểm actor được quản lý service account này và tenant của nó.
3. Validate nhãn, ngày hết hạn, số key tối đa/account, scopes từ allowlist do server quản lý.
4. Tính quyền được phép: requested scopes phải là tập con của account entitlement và quyền actor được cấp key.
5. Sinh `keyId` + secret mới bằng `SecureRandom`; không nhận raw secret từ browser.
6. Tính HMAC/digest verifier; ghi DB transaction với key metadata, scopes, audit event.
7. Chỉ **sau commit thành công** mới trả raw secret cho client; tránh trả một key không hề tồn tại trong DB.
8. Response `Cache-Control: no-store`; không ghi raw body vào logs/APM.
9. Người nhận đưa secret vào Secret Manager, không dán vào source code/CI variables không được bảo vệ.

**Điều kiện nguyên tử:** nếu transaction lưu key thất bại, không được tuyên bố đã cấp key. Nếu HTTP response mất sau commit, raw key không thể lấy lại từ verifier — người quản trị phải tạo key khác; thiết kế UX/idempotency phù hợp để tránh tạo quá nhiều key không dùng.

### Chặn privilege escalation

Một request muốn `["orders:read","orders:delete","keys:manage"]` không được hợp lệ chỉ vì JSON đúng cú pháp. Bằng chính sách của server:

~~~text
account entitled:       orders:read, orders:write
actor may grant:        orders:read
requested:              orders:read, orders:delete
result:                 DENY (không âm thầm cho delete)
~~~

Tự giảm scopes thay vì deny có thể che sai cấu hình; nên chọn rõ một trong hai contract và báo lại requested vs granted scopes cho actor được ủy quyền, **không công bố thông tin tenant khác**.

## 10. Gọi API bằng key: chỉ qua HTTPS và header

Ví dụ request từ worker:

~~~http
GET /svc/orders/42 HTTP/1.1
Host: api.example.org
Authorization: ApiKey <sk_live_v1_keyId.secret>
Accept: application/json
~~~

`ApiKey` ở đây là **custom authorization scheme** của ứng dụng, không phải OAuth2 `Bearer`. Nếu dùng `X-API-Key` theo API contract khác, mọi điều về redaction và TLS vẫn áp dụng. Tránh trộn `Authorization: Bearer` cho JWT với API key opaque rồi đoán nội dung token theo prefix trong cùng filter mà không có policy rõ.

Không truyền key qua:

~~~text
GET /svc/orders?api_key=...
GET /svc/orders#api_key=...
Cookie: api_key=...   (trừ khi có thiết kế cookie/CSRF riêng)
~~~

Query và fragment có nguy cơ xuất hiện trong browser history, referrer, proxy logs, APM hoặc analytics. Key trong header vẫn có nguy cơ bị ghi vào log; cấu hình **redact Authorization** tại ingress, ứng dụng và tracing.

Với command-line:

~~~bash
# Ví dụ cú pháp, thay biến bằng giá trị từ secret manager.
curl --fail-with-body \
  --header "Authorization: ApiKey $SERVICE_API_KEY" \
  "https://api.example.org/svc/orders/42"
~~~

Không paste raw key vào shell history/ticket/CI logs. Trong shell khác nhau cú pháp biến có thể khác; câu lệnh trên dùng shell kiểu Bash. Tránh chạy với `curl -v` khi output có thể hiển thị Authorization hoặc token trong môi trường chia sẻ.

## 11. Java 17 độc lập: vòng đời phát hành, kiểm tra, thu hồi

Chương trình sau chạy bằng **JDK 17+ không cần Spring**, minh họa end-to-end:

- Sinh 32 bytes từ `SecureRandom`.
- Token gồm prefix + UUID ID + base64url secret; **không in raw token**.
- Lưu HMAC-SHA-256 verifier, tenant, service account, scope, expiry, revoked flag.
- Tra key ID rồi kiểm HMAC bằng `MessageDigest.isEqual`.
- Chỉ cho key active, còn hạn và đúng verifier.
- Issue key mới trước khi revoke key cũ.
- Kiểm expiry bằng đồng hồ giả lập để stdout ổn định.

**Đây là lab lưu trong memory**, chưa có DB transaction, KMS, HTTP/TLS, rate limiting, tenant account state, authorization hay audit production. HMAC key giả lập được tạo mới trong JVM; production nạp pepper an toàn từ KMS/secret manager và có key-version.

### Tệp ServiceApiKeyLifecycleDemo.java

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.Base64;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class ServiceApiKeyLifecycleDemo {

    private static final String PREFIX = "sk_demo_";
    private static final SecureRandom RANDOM = new SecureRandom();

    record Issued(String id, String token) {}

    record KeyRow(
            String owner,
            String tenant,
            Set<String> scopes,
            byte[] verifier,
            Instant expiresAt,
            Instant revokedAt) {}

    record Identity(String owner, String tenant, Set<String> scopes) {}

    static final class DemoClock extends Clock {
        private Instant now = Instant.parse("2026-01-01T00:00:00Z");

        public ZoneId getZone() { return ZoneOffset.UTC; }

        public Clock withZone(ZoneId zone) {
            return Clock.fixed(now, zone);
        }

        public Instant instant() { return now; }

        void advance(Duration duration) { now = now.plus(duration); }
    }

    private final Map<String, KeyRow> store = new ConcurrentHashMap<>();
    private final byte[] pepper;
    private final Clock clock;

    ServiceApiKeyLifecycleDemo(byte[] pepper, Clock clock) {
        if (pepper == null || pepper.length < 32) {
            throw new IllegalArgumentException("HMAC key too short");
        }
        this.pepper = pepper.clone();
        this.clock = Objects.requireNonNull(clock);
    }

    private byte[] verifierFor(String publicId, String secret) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(pepper, "HmacSHA256"));
            return mac.doFinal(
                    (publicId + "." + secret)
                            .getBytes(StandardCharsets.US_ASCII));
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("HMAC unavailable", ex);
        }
    }

    Issued issue(
            String owner, String tenant, Set<String> scopes, Duration ttl) {

        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException("Invalid TTL");
        }

        String id = UUID.randomUUID().toString();
        byte[] randomSecret = new byte[32];
        RANDOM.nextBytes(randomSecret);

        String encoded = Base64.getUrlEncoder()
                .withoutPadding().encodeToString(randomSecret);
        Arrays.fill(randomSecret, (byte) 0);

        byte[] verifier = verifierFor(id, encoded);
        KeyRow row = new KeyRow(
                owner, tenant, Set.copyOf(scopes), verifier,
                clock.instant().plus(ttl), null);
        store.put(id, row);

        return new Issued(id, PREFIX + id + "." + encoded);
    }

    Optional<Identity> authenticate(String presented) {
        if (presented == null
                || presented.length() != PREFIX.length() + 36 + 1 + 43
                || !presented.startsWith(PREFIX)) {
            return Optional.empty();
        }

        int dot = presented.indexOf('.', PREFIX.length());
        if (dot != PREFIX.length() + 36) {
            return Optional.empty();
        }

        String id = presented.substring(PREFIX.length(), dot);
        String secret = presented.substring(dot + 1);
        try {
            UUID.fromString(id);
            byte[] decoded = Base64.getUrlDecoder().decode(secret);
            if (decoded.length != 32
                    || !Base64.getUrlEncoder().withoutPadding()
                            .encodeToString(decoded).equals(secret)) {
                return Optional.empty();
            }
            Arrays.fill(decoded, (byte) 0);
        } catch (IllegalArgumentException ex) {
            return Optional.empty();
        }

        KeyRow row = store.get(id);
        if (row == null) {
            return Optional.empty();
        }

        byte[] candidate = verifierFor(id, secret);
        if (!MessageDigest.isEqual(candidate, row.verifier())
                || row.revokedAt() != null
                || !clock.instant().isBefore(row.expiresAt())) {
            return Optional.empty();
        }

        return Optional.of(
                new Identity(row.owner(), row.tenant(), row.scopes()));
    }

    boolean revoke(String id) {
        return store.computeIfPresent(id, (key, row) ->
                row.revokedAt() != null ? row : new KeyRow(
                        row.owner(), row.tenant(), row.scopes(),
                        row.verifier(), row.expiresAt(), clock.instant()))
                != null;
    }

    public static void main(String[] args) {
        DemoClock clock = new DemoClock();
        byte[] pepper = new byte[32];
        RANDOM.nextBytes(pepper);

        ServiceApiKeyLifecycleDemo service =
                new ServiceApiKeyLifecycleDemo(pepper, clock);
        Arrays.fill(pepper, (byte) 0);

        Issued oldKey = service.issue(
                "svc-export", "tenant-a",
                Set.of("orders:read"), Duration.ofHours(1));

        System.out.println("Key format valid = "
                + oldKey.token().startsWith(PREFIX));
        System.out.println("Old key active = "
                + service.authenticate(oldKey.token()).isPresent());
        System.out.println("Read scope = "
                + service.authenticate(oldKey.token()).orElseThrow()
                        .scopes().contains("orders:read"));
        System.out.println("Write scope = "
                + service.authenticate(oldKey.token()).orElseThrow()
                        .scopes().contains("orders:write"));

        int secretStart = oldKey.token().indexOf('.') + 1;
        char first = oldKey.token().charAt(secretStart);
        String tampered = oldKey.token().substring(0, secretStart)
                + (first == 'A' ? "B" : "A")
                + oldKey.token().substring(secretStart + 1);

        System.out.println("Tampered accepted = "
                + service.authenticate(tampered).isPresent());

        Issued replacement = service.issue(
                "svc-export", "tenant-a",
                Set.of("orders:read"), Duration.ofHours(2));

        System.out.println("Replacement active = "
                + service.authenticate(replacement.token()).isPresent());

        service.revoke(oldKey.id());

        System.out.println("Revoked old accepted = "
                + service.authenticate(oldKey.token()).isPresent());
        System.out.println("New key still active = "
                + service.authenticate(replacement.token()).isPresent());

        clock.advance(Duration.ofHours(3));

        System.out.println("Expired accepted = "
                + service.authenticate(replacement.token()).isPresent());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ServiceApiKeyLifecycleDemo.java
java ServiceApiKeyLifecycleDemo
~~~

Stdout **chính xác**, không phụ thuộc raw key/UUID ngẫu nhiên:

~~~text
Key format valid = true
Old key active = true
Read scope = true
Write scope = false
Tampered accepted = false
Replacement active = true
Revoked old accepted = false
New key still active = true
Expired accepted = false
~~~

Giải thích từng kết quả:

- Key được sinh ngẫu nhiên, HMAC verifier phù hợp nên xác thực thành công.
- Identity mang scope `orders:read`; nó không tự được `orders:write`.
- Đổi một ký tự trong secret khiến HMAC không khớp.
- Key mới được issue **trước khi** revoke key cũ; hai keys có thể cùng hoạt động trong giai đoạn overlap ngắn.
- Thu hồi key cũ không ảnh hưởng key mới của cùng account.
- Đồng hồ tăng thêm 3 giờ làm TTL của key còn lại hết hạn.

**Giới hạn lab cần nhớ:** `ConcurrentHashMap` không thay transaction của database; `revoke(id)` trong lab không kiểm actor/tenant/quyền nên **tuyệt đối không expose nó như REST endpoint**. Việc `Arrays.fill(randomSecret)` giảm thời gian giữ byte[] trong memory nhưng không xóa được các String bất biến đã được tạo; code Java production vẫn phải bảo vệ heap dumps, logs và secret exposure.

## 12. Từ lab sang database service: các invariant bắt buộc

Một service cấp key production nên bảo đảm:

- `issueKey(accountId, requestedScopes, ttl, actor)` chỉ thành công sau khi actor/tenant/account/scope được xác thực và DB transaction commit.
- `findById(keyId)` chỉ trả verifier/metadata cho internal verifier; public admin list không trả verifier hoặc raw secret.
- `verify(raw)` từ chối format sai, key không tồn tại, digest sai, revoked, expired, account disabled và tenant không hợp lệ.
- `revoke(tenantId, accountId, keyId, actor)` kiểm ownership/permission và dùng cập nhật nguyên tử.
- `listKeys(accountId)` chỉ trả label, key ID, created/expiry/revoked/lastUsed/scope; không có một con đường “show raw”.
- `rotate(...)` cấp một record mới và có kế hoạch chuyển traffic trước khi revoke cũ.
- Dữ liệu audit lưu trong transaction/outbox nếu yêu cầu bằng chứng bền vững.

**Phân biệt verifier và quyền truy cập:** Digest match chỉ chứng minh caller biết secret. Việc tenant/account/resource có được phép truy cập cần kiểm **sau đó**. Một key thật của tenant A không được đọc dữ liệu tenant B chỉ vì URL ID trùng.

## 13. Thu hồi: thiết kế endpoint và cập nhật nguyên tử

Một REST contract minh họa:

~~~http
DELETE /admin/service-accounts/123e4567-e89b-42d3-a456-426614174000/keys/123e4567-e89b-42d3-a456-426614174999 HTTP/1.1
Authorization: Bearer <admin-access-token>
~~~

Response có thể là `204 No Content` khi thao tác thu hồi đã được ghi bền vững. Với DELETE idempotent, gọi lại sau khi đã revoke vẫn có thể trả 204 theo contract; không được vì retry mà **tạo lại trạng thái ACTIVE**.

SQL pattern minh họa (phải chạy sau actor/tenant checks):

~~~sql
UPDATE service_api_key
SET revoked_at = now()
WHERE id = :key_id
  AND service_account_id = :account_id
  AND tenant_id = :tenant_id
  AND revoked_at IS NULL
RETURNING id, revoked_at;
~~~

Khi câu lệnh trả 0 row, có thể do key chưa tồn tại, đã revoke hoặc không thuộc tenant/account; API quản trị chọn 204/404 theo chính sách và **không tiết lộ tài nguyên tenant khác**. Muốn audit idempotent mà không duplicate event, định nghĩa rõ phiên bản trạng thái và transaction.

Với quyền cao, có thể dùng policy `keys:revoke` tách khỏi `keys:create`. Không cho một service account đang bị xâm nhập tự phát key quyền rộng bằng cách gọi management API nếu key không được cấp quyền/step-up tương ứng.

### Revoke một key khác với disable một account

- Revoke key K1: K1 invalid, K2 vẫn có thể active.
- Disable account A: mọi K thuộc A phải bị verifier từ chối.
- Revoke tất cả keys của account: transaction/batch update đúng tenant và có audit.
- Xóa một resource hoặc đổi tenant policy: không sửa key bytes; authorization ở resource áp chính sách mới.

Đừng giải quyết mất quyền bằng cách chờ tất cả keys hết hạn, nhất là nếu nghi ngờ secret bị lộ.

## 14. Thu hồi tức thời và vấn đề cache

“Thu hồi tức thời” chỉ đúng khi mỗi node biết trạng thái revoked mới trước khi chấp nhận request. Nếu service cache một verdict `keyId -> authenticated=true` trong 30 phút, revoke ở database có thể chưa có hiệu lực tới 30 phút sau.

| Cách lookup | Ưu điểm | Nhược điểm/điều kiện |
| --- | --- | --- |
| DB lookup mỗi request | Revocation gần thời điểm commit | DB latency/load và availability |
| Redis cache metadata với TTL rất ngắn | Giảm DB load | Cửa sổ stale state đến TTL |
| Event-driven cache invalidation | Phản ứng nhanh | Phải xử lý lost events, node offline |
| Local cache không giới hạn TTL | Nhanh | **Không thể bảo đảm thu hồi kịp thời** |
| Signed self-contained token dài hạn | Không cần lookup | Thu hồi trước expiry cần denylist/introspection |

Nếu chính sách yêu cầu revoke có hiệu lực trong `N` giây, phải đo propagation delay trên nhiều nodes và thiết kế bounded staleness/strong consistency phù hợp. Không hứa “ngay lập tức” khi vẫn cho phép cache stale không giới hạn.

Với request đã được xác thực **trước** thời điểm revoke, thao tác đang chạy có thể vẫn hoàn tất, trừ khi hệ thống kiểm lại khi thực hiện hành động quan trọng. Định nghĩa rõ ranh giới “new requests after revocation” và các hành động nhạy cảm.

## 15. Rotation không gián đoạn bằng hai key song song

**Key rotation** là thay credential theo kế hoạch, không chỉ revoke. Quy trình an toàn:

~~~text
T0: K1 đang active, worker dùng K1
 |
T1: Tạo K2 cùng account, scopes tối thiểu, TTL mới
 |   K1 active, K2 active
 |
T2: Lưu K2 vào secret manager, rollout tới worker
 |
T3: Smoke-test gọi API bằng K2, đo traffic và errors
 |
T4: Xác nhận không còn workload cần K1
 |
T5: Revoke K1, invalidate caches
 |
T6: Test K1 -> 401, K2 -> 200; audit hoàn tất
~~~

Giai đoạn overlap phải **ngắn, có deadline và owner**; không cho nhiều keys vô hạn tích tụ. Nếu K1 bị compromise, bỏ overlap và revoke ngay, sau đó xử lý downtime bằng playbook emergency.

**Không hiển thị lại K1** từ database khi “xoay vòng”: verifier không giải mã được. K2 là secret hoàn toàn mới, không derive từ K1. Nếu K2 rollout thất bại trước revoke, rollback về K1 khi còn active; sau revoke thì không “unrevoke” K1 mà phát hành key khác nếu cần.

### Quản lý TTL và cảnh báo hết hạn

Có thể đặt chính sách ví dụ:

- Default TTL 30 ngày cho integration tương đối ổn định;
- TTL ngắn hơn cho môi trường test/ephemeral workload;
- Thông báo khi còn 7, 3, 1 ngày;
- Key cũ bị revoke sau rollout và overlap window;
- Chủ account phải kiểm inventory và key chưa dùng.

Đây là **ví dụ policy**, không phải con số bắt buộc cho mọi hệ thống. Chọn TTL theo threat model, khả năng tự động hóa và chi phí vận hành; không tạo key vô thời hạn mà không có phê duyệt đặc biệt.

## 16. Spring Security Servlet: filter xác thực API key

Spring Security **không tự biết API key riêng của bạn nằm ở đâu hay kiểm verifier như thế nào**. Cần dùng cơ chế authentication phù hợp: custom filter + verifier, hoặc `AuthenticationFilter`/`AuthenticationProvider` với một token riêng. Ví dụ sau chọn một filter đơn giản cho **machine-only stateless endpoints**.

### Contract nội bộ

Các interface/record ứng dụng:

~~~java
package demo.servicekeys;

import java.util.Set;

public record ServiceIdentity(
        String serviceAccountId,
        String tenantId,
        Set<String> scopes) {}

public interface ServiceApiKeyVerifier {
    // Trả null khi key không hợp lệ/revoked/expired/account disabled.
    // Lỗi hạ tầng thật phải ném exception để fail closed.
    ServiceIdentity verify(String rawApiKey);
}
~~~

**Đây là hai file Java riêng** (ServiceIdentity.java và ServiceApiKeyVerifier.java); không đặt đồng thời hai khai báo `public` trong một file. Implementation `ServiceApiKeyVerifier` thực phải tra DB, tính HMAC, so sánh, kiểm expiry/account/tenant và trả identity từ server-side metadata. Nó **không bao giờ nhận authorities từ request**.

Để đơn giản, contract trả `null` cho lỗi credential; production có thể dùng sealed result hoặc typed exception để phân biệt invalid key và infrastructure failure, miễn không lộ chi tiết nhạy cảm ra caller.

### Lớp filter

Tệp **ServiceApiKeyFilter.java**:

~~~java
package demo.servicekeys;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.HttpHeaders;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class ServiceApiKeyFilter extends OncePerRequestFilter {

    private final ServiceApiKeyVerifier verifier;

    public ServiceApiKeyFilter(ServiceApiKeyVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String header = request.getHeader(HttpHeaders.AUTHORIZATION);

        if (header == null) {
            // Để AuthorizationFilter từ chối request thiếu credential.
            chain.doFilter(request, response);
            return;
        }

        if (header.length() > 256 || !header.startsWith("ApiKey ")) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        String raw = header.substring("ApiKey ".length());
        ServiceIdentity identity = verifier.verify(raw);

        if (identity == null) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        var authorities = identity.scopes().stream()
                .map(scope -> new SimpleGrantedAuthority("SCOPE_" + scope))
                .toList();

        Authentication authenticated =
                new PreAuthenticatedAuthenticationToken(
                        identity, null, authorities);

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authenticated);
        SecurityContextHolder.setContext(context);

        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

**Lưu ý:**

- Filter chỉ chấp nhận scheme `ApiKey ` trong đường dẫn service mà chain kiểm soát.
- Nó không đặt raw key vào `Authentication.getCredentials()`, không log header, không tạo session.
- `PreAuthenticatedAuthenticationToken` với constructor 3 tham số đại diện identity đã **được verifier tin cậy kiểm trước**; tuyệt đối không tạo token đã authenticated từ raw input chưa xác minh.
- Authorities được tạo từ **scopes do server đọc từ DB**, không từ header khách hàng.
- `SecurityContextHolder.clearContext()` trong `finally` bảo vệ thread; Spring Security chain cũng có cleanup lifecycle. Filter không dùng context cũ khi key invalid.
- Nếu verifier/database gặp sự cố, không được “cho qua” như credential hợp lệ; cần một handler lỗi hạ tầng được thiết kế và không để stack trace chứa dữ liệu nhạy cảm.
- Để đơn giản, ví dụ chưa xác minh tenant resource ID trong controller/service: **phải làm thêm**.

**Không đăng ký filter hai lần.** Trong Spring Boot, một Filter bean `@Component` có thể bị Servlet container auto-register đồng thời với SecurityFilterChain. Trong ví dụ dưới đây, tạo filter bằng `new ServiceApiKeyFilter(verifier)` tại chain và **không tạo thêm @Component bean cho filter**.

## 17. Cấu hình SecurityFilterChain stateless riêng

Mảnh cấu hình Spring Security Servlet 6.x/7.x:

~~~java
@Bean
@Order(1)
SecurityFilterChain serviceApiChain(
        HttpSecurity http, ServiceApiKeyVerifier verifier)
        throws Exception {

    return http
            .securityMatcher("/svc/**")
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                    .securityContextRepository(
                            new NullSecurityContextRepository()))
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/svc/orders/**")
                        .hasAuthority("SCOPE_orders:read")
                    .anyRequest().denyAll())
            .exceptionHandling(exceptions -> exceptions
                    .authenticationEntryPoint(
                            (req, res, error) ->
                                    res.sendError(HttpServletResponse.SC_UNAUTHORIZED)))
            .addFilterAfter(
                    new ServiceApiKeyFilter(verifier),
                    LogoutFilter.class)
            .build();
}
~~~

Đặt method trong Spring `@Configuration` và import:

~~~java
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.authentication.logout.LogoutFilter;
~~~

**Mảnh cấu hình cần ứng dụng Spring Boot Servlet thật**, các lớp `ServiceApiKeyFilter`/`ServiceApiKeyVerifier` và verifier bean. Không có user/password store trong machine-only chain. Spring Security 6/7 dùng lambda DSL; filter custom được thêm **sau LogoutFilter và trước AuthorizationFilter** để principal sẵn sàng khi kiểm quyền. Tài liệu Spring Security khuyến nghị xác định vị trí custom authentication filters dựa trên security filter ordering.

**Về CSRF:** chỉ disable CSRF trong chain `/svc/**` khi endpoint này **thực sự stateless, chỉ dùng header credential do client kiểm soát và không dựa session cookie tự gửi bởi browser**. Đừng sao chép `csrf.disable()` sang một web/admin chain sử dụng cookie. Với browser admin management API, giữ CSRF protection theo mô hình authentication.

**Thiếu key:** `AuthorizationFilter` đánh giá unauthenticated request và entry point trả 401 trong cấu hình này. **Key hợp lệ nhưng thiếu scope:** authorization trả 403 (điều kiện cấu hình AccessDeniedHandler/entry point đúng). Tests phải xác minh cả hai.

### Authorization ở controller và resource

Ví dụ một endpoint (mảnh Spring MVC):

~~~java
@GetMapping("/svc/orders/{id}")
public OrderDto readOrder(
        @PathVariable String id,
        @AuthenticationPrincipal ServiceIdentity caller) {

    return orderService.findOrderForTenant(
            caller.tenantId(), id, caller.serviceAccountId());
}
~~~

`@AuthenticationPrincipal` đọc principal do filter dựng; `orderService` phải thực sự kiểm quyền với tenant và record. Không chỉ tin `/orders/{id}` là an toàn vì key có `orders:read`: một key của tenant A vẫn không được trả order của tenant B.

Nếu một account có nhiều scopes, dùng `hasAuthority("SCOPE_orders:read")` là một lớp; backend service phải kiểm action/resource/tenant ở lớp dữ liệu.

## 18. Có nên dùng AuthenticationProvider thay vì filter tự verify?

Với hệ thống lớn, bạn có thể tách:

~~~text
HTTP filter: parse Authorization header
      |
      v
Unauthenticated ServiceApiKeyAuthenticationToken(rawKey)
      |
      v
AuthenticationManager / ProviderManager
      |
      v
ServiceApiKeyAuthenticationProvider
      | supports(custom token class)
      | verify digest/account/tenant
      v
Authenticated ServiceAccountPrincipal + authorities
      |
      v
SecurityContext, authorization
~~~

Ưu điểm:

- Đúng cơ chế `AuthenticationManager` của Spring Security;
- Provider được test riêng;
- Hỗ trợ event publisher và thống kê auth;
- Dễ phối hợp nhiều credential types nếu định nghĩa rõ ranh giới.

Nhưng **đừng tự suy Spring có class `ServiceApiKeyAuthenticationToken`**; đó là lớp ứng dụng phải viết, thường extends `AbstractAuthenticationToken`. Provider cần trả authenticated token **chỉ sau khi xác minh**; `supports(...)` không quá rộng; nếu custom Manager tự dựng, gắn `AuthenticationEventPublisher` phù hợp.

Bài thực hành dùng filter trực tiếp để dễ theo dõi; khi chuyển sang provider, giữ nguyên các yêu cầu về cryptography, revocation, authorization và stateless context. Việc đưa raw key vào một `UsernamePasswordAuthenticationToken` có thể gây nhầm password login; token chuyên dụng rõ nghĩa hơn.

## 19. Scope không phải role, và tenant là một chiều độc lập

Một số hệ thống gán `ROLE_SERVICE` và cho qua mọi endpoint. Đây là anti-pattern nếu service account chỉ cần đọc vài resources.

Phân biệt:

| Field | Ví dụ | Nguồn |
| --- | --- | --- |
| Principal type | SERVICE_ACCOUNT | Kết quả verification của server |
| Service account ID | Opaque UUID | Database đáng tin |
| Tenant ID | tenant A | Account/key metadata, không nhận từ client làm nguồn truth |
| Key ID | UUID key record | Token public prefix + lookup |
| Key scopes | orders:read | Đã được cấp trong DB, không phải query |
| Account entitlements | orders:read, inventory:read | Policy của service account |
| Resource authorization | Order thuộc tenant A? | Controller/service/repository |

Với trường hợp:

~~~text
Key K1:
  owner = svc-export
  tenant = A
  scopes = orders:read

Request:
  GET /svc/orders/999
  order 999 thuộc tenant B

Authentication: VALID
Scope authorization: ORDERS_READ = YES
Resource authorization: TENANT_MATCH = NO
HTTP result: 403 hoặc 404 theo policy
~~~

Không để client chọn tenant bằng header `X-Tenant-ID` rồi coi đó là quyền. Header có thể chỉ là một yêu cầu chọn tenant; server phải kiểm tenant đó thuộc quyền principal. Nếu hệ thống có impersonation/delegation, cần audit actor và subject riêng.

## 20. Kiểm thử với MockMvc và test verifier

Bộ kiểm thử thực tế nên có **hai lớp**:

1. **Verifier tests**: cryptographic secret generation/digest, active/expired/revoked/account-disabled, tenant/scopes.
2. **HTTP filter tests**: request thiếu/sai key → 401; key hợp lệ → principal và authorities đúng; đúng key thiếu scope → 403; không session; controller kiểm tenant/resource.

Mảnh test Spring Boot Servlet + Spring Security Test (cần test app, verifier stub và protected endpoint):

~~~java
// Pseudocode JUnit/MockMvc: ServiceApiKeyVerifier stub từ test context.
when(verifier.verify("valid-test-key"))
        .thenReturn(new ServiceIdentity(
                "svc-export", "tenant-a", Set.of("orders:read")));

mockMvc.perform(get("/svc/orders/42")
        .header("Authorization", "ApiKey valid-test-key"))
        .andExpect(status().isOk());

mockMvc.perform(get("/svc/orders/42"))
        .andExpect(status().isUnauthorized());

mockMvc.perform(get("/svc/orders/42")
        .header("Authorization", "ApiKey invalid-test-key"))
        .andExpect(status().isUnauthorized());
~~~

Đây là **mảnh test**, không biên dịch độc lập; cần Mockito/Spring Test imports, application controllers/service stubs phù hợp và filter chain đã đăng ký. Nếu test verifier thật yêu cầu định dạng `sk_demo_...`, dùng stub hoặc tạo key thật từ fixture thay vì gửi placeholder như ví dụ.

Để kiểm 403 với read-only key, cần route write được cấu hình:

~~~java
.requestMatchers(HttpMethod.POST, "/svc/orders/**")
    .hasAuthority("SCOPE_orders:write")
~~~

Với POST từ client machine-only stateless, CSRF policy phải thống nhất chain. Dùng key có `orders:read` gửi POST và assert 403. Không chỉ test `GET` rồi tuyên bố “scopes đã enforce”.

### Test không rò context giữa requests

~~~text
Request A: GET /svc/orders/42 + valid key -> 200, service principal
Request B: GET /svc/orders/42 WITHOUT key -> 401
Request C: GET /svc/orders/42 + revoked key -> 401
~~~

Đây phải là ba HTTP requests độc lập đi qua `FilterChainProxy`. Không tạo `@WithMockUser` cho cả class vì nó có thể khiến missing-key request vẫn authenticated giả, che lỗi. Trong test production cần thêm controller/check để xác nhận user A không rò qua request B.

## 21. Kiểm thử database, expiry và concurrency

| Test | Kết quả mong đợi |
| --- | --- |
| CSPRNG 32 bytes | Secret format đúng, nhiều keys khác nhau |
| Same account cấp K1 và K2 | ID và verifier khác nhau |
| Raw secret không lưu DB | Chỉ verifier/metadata xuất hiện |
| HMAC key version đúng | Verifier được chọn theo version |
| Thay một ký tự secret | Verify fail |
| Token có URL encoding/lỗi format | Reject trước DB hoặc theo parser strict |
| Key ID không tồn tại | 401 generic |
| TTL đúng biên | `now < expiresAt` mới active; bằng expiry thì inactive |
| revokedAt khác NULL | 401 |
| Account disabled | 401 dù verifier đúng |
| K1 revoked, K2 active | K1 401, K2 200 |
| Tenant A key truy cập B | 403/404 dù scope có |
| Requested scope không được actor/account cấp | Không issue key |
| Concurrent revoke/authenticate | Đảm bảo requests mới sau commit thấy state theo policy |
| Database unavailable | Fail closed; không cho qua bằng cached stale vô hạn |
| Nhiều nodes | K1 revoked được áp theo SLO toàn hệ thống |
| Pepper version rotation | Key cũ còn được verify theo policy hoặc được migrate qua reissue |
| Duplicate API create retry | Không ghi quá nhiều credentials ngoài dự kiến |
| Delete key retry | Idempotent, không khôi phục credential |
| Admin list keys | Không có raw key/verifier |
| Credential trong logs | Không xuất hiện ở access logs/trace/ticket |

**Chú ý property tests:** một token sai format cực dài phải bị từ chối nhanh; không parse/ghi nguyên vào logs; không dùng exception message trực tiếp làm audit payload. Một token syntactically valid nhưng secret sai phải fail dù key ID tồn tại.

## 22. Last-used, observability và audit

Những sự kiện quan trọng:

| Event type | Metadata có thể lưu | Không được lưu |
| --- | --- | --- |
| `API_KEY_CREATED` | actorRef, serviceAccountId, keyId, tenantRef, scopes, expiry, time | Raw key, pepper, full response body |
| `API_KEY_ROTATION_STARTED` | keyId cũ, keyId mới, owner, deadline | Raw K1/K2 |
| `API_KEY_REVOKED` | actorRef, keyId, reason code, timestamp | Raw key |
| `API_KEY_AUTH_SUCCESS` | keyId/opaqueRef, service principalRef, route template, time | Credential header |
| `API_KEY_AUTH_FAILURE` | category INVALID/EXPIRED/REVOKED theo quyền nội bộ, request ID | Raw key hoặc untrusted ID |
| `API_KEY_EXPIRY_WARNING` | owner, expiresAt, keyId | Token đầy đủ |
| `SERVICE_ACCOUNT_DISABLED` | actor, accountId, tenant, time | Credential data |

Để tránh lộ account/key existence, response bên ngoài có thể luôn là một lỗi xác thực generic; **telemetry nội bộ** chỉ được phân loại khi nguồn dữ liệu đáng tin. Không đưa user-input token/keyId vào Prometheus metric labels — sẽ gây high cardinality và có thể rò credential.

Với `last_used_at`, mỗi request update DB ngay có thể tạo row contention và giảm throughput. Có thể cập nhật theo batch/throttle bằng event queue, nhưng phải hiểu rằng “lần dùng cuối” là dữ liệu **xấp xỉ** nếu async. Không dùng last_used mơ hồ làm căn cứ duy nhất để revoke tự động trong trường hợp quan trọng.

Truy cập audit logs phải có RBAC và retention riêng. Nếu event publisher của Spring chỉ dùng in-memory listener, nó **không bảo đảm durable audit**; dùng transactional outbox hoặc một giải pháp có giao nhận đáng tin khi compliance yêu cầu.

## 23. Quản lý raw key ở phía client

Một worker cần lấy secret từ Secret Manager hoặc cơ chế workload secret injection:

~~~text
CI/CD provision key -> Secret Manager version
                       |
                       v
                Deployment references secret version
                       |
                       v
                 Worker reads at startup/refresh
                       |
                       v
               HTTPS Authorization: ApiKey ...
~~~

Không đặt secret trong:

- Source code hoặc `application.yml` commit lên Git;
- Container image layers;
- Terminal shell history hay screenshot;
- Query parameter/logged URL;
- Crash report/exception context;
- CI artifact, test reports hoặc debug logging;
- Raw environment dumps;
- Tracing baggage hoặc telemetry attributes.

Environment variables có thể là một phương thức injection ở một số nền tảng, nhưng không mặc nhiên an toàn nếu process dumps, diagnostics hoặc người có quyền host có thể đọc. Đánh giá theo threat model, ưu tiên secret store có RBAC/rotation và kiểm logging cẩn thận.

Khi rotate, cập nhật secret manager **theo version**, rollout xác định và giám sát tỷ lệ 401. Không gửi raw key cho support qua chat hoặc email. Nếu key bị lộ, revoke và issue key mới; việc “xóa commit chứa key” không bảo đảm bản sao Git history/CI cache đã bị xóa.

## 24. Tài khoản dịch vụ và chủ quản vòng đời

Một account máy vẫn cần người chịu trách nhiệm:

| Trường | Tại sao cần |
| --- | --- |
| Owner team / on-call | Nhận cảnh báo key sắp hết hạn hoặc bị lộ |
| Purpose/description | Biết worker nào cần key |
| Allowed tenants | Giới hạn boundary dữ liệu |
| Scopes approved | Least privilege và review định kỳ |
| Environment | Không dùng key staging ở production |
| Last used / status | Phát hiện key bỏ quên hoặc bị misuse |
| Creation actor / approver | Audit |
| Expiry / rotation deadline | Không có key vô thời hạn ngoài ý định |
| Revocation contact/runbook | Xử lý sự cố nhanh |

**Không cấp mọi key vào một service account chung như `system-admin`.** Nếu một key bị lộ, không thể xác định workload nào gây ra, và blast radius quá rộng. Mỗi workload hoặc nhóm tích hợp có ranh giới trách nhiệm rõ nên có account/key riêng với scopes hẹp.

Nếu service account không còn owner hoặc job đã ngừng hoạt động, cần lịch review để disable account/revoke keys; đừng chờ nó hết hạn mà không ai biết.

## 25. Các anti-pattern thường gặp

| Anti-pattern | Vì sao sai | Thay thế |
| --- | --- | --- |
| Raw API key lưu plaintext trong DB | DB leak = credential compromise | SHA-256/HMAC verifier |
| Key chỉ là UUID hoặc timestamp | Dễ không đủ entropy theo policy | UUID ID + 32-byte CSPRNG secret |
| Token tạo bằng `Random` | Không dùng cho secret mật mã | `SecureRandom` |
| API trả raw key mỗi lần GET | Secret sống mãi ở nhiều hệ thống | Show once |
| Key không có expiry/revoke | Không thể xử lý incident | TTL + revoke state |
| Cho key tạo scope tùy ý | Privilege escalation | Actor/account scope intersection |
| Scope check nhưng bỏ tenant/resource | Cross-tenant data leak | Authorization ở resource layer |
| Query parameter chứa key | Leak qua logs/referrer | TLS + header |
| Key trong metrics label | Leak + high cardinality | Opaque eventId/reasonCode |
| Authentication bypass khi DB outage | Fail-open | Fail closed, quan sát lỗi hạ tầng |
| Cache verdict vô thời hạn | Revoked key vẫn hoạt động | Bound TTL/invalidation |
| Không có audit actor tạo/revoke | Không truy vết được | Audit trail bền vững theo policy |
| Dùng API key như password web user | Bỏ MFA/session policy | Tách machine và human flows |
| Filter đăng ký hai lần | Authentication/cleanup không đúng | Chỉ một SecurityFilterChain registration |
| Tắt CSRF mọi chain để key API chạy | Rủi ro với browser session | Cấu hình machine-only chain riêng |
| Disable account chỉ đổi UI status | Key vẫn gọi API | Verifier kiểm account state |
| Dùng hash password chậm cho key ngẫu nhiên rồi nghẽn | Có thể làm tăng CPU bị abuse | Digest/HMAC phù hợp entropy |
| HMAC key bị thay không có version | Hàng loạt key bất ngờ invalid | Pepper version và migration |
| Revoke K1 trước khi triển khai K2 | Downtime | Rotation với overlap ngắn |
| Unrevoke key bị lộ | Có thể khôi phục credential compromise | Issue mới, không hồi sinh key cũ |

## 26. Incident response: phát hiện API key bị lộ

Nếu secret xuất hiện trong log, Git, ticket, CI hoặc bị nghi exfiltration:

1. **Xác nhận key ID/owner và phạm vi ảnh hưởng** qua metadata được bảo vệ, không lan truyền raw key thêm.
2. **Revoke ngay** key nghi lộ nếu rủi ro yêu cầu; không chờ rotation theo lịch.
3. Xóa hoặc cô lập các bản sao rò rỉ, kiểm lịch sử repository/CI artifact/backups; không cho rằng xóa một file đã làm secret an toàn.
4. Issue key mới theo scope tối thiểu, đưa vào Secret Manager, rollout an toàn.
5. Kiểm logs/audit các lần sử dụng key theo thời gian, route, resource/tenant và nguồn đáng tin.
6. Xem có cần revoke các keys khác cùng account hoặc disable account không.
7. Báo owner/on-call/security team theo runbook; không gửi raw key trong incident channel.
8. Tìm root cause: body logging, URL query, credential in crash dump, copy paste hay quyền CI quá rộng.
9. Cập nhật detection rule, secret scanning, retention policy và bài test để ngăn tái diễn.
10. Ghi incident/audit outcome nhưng không lưu raw credential làm bằng chứng công khai.

Một lần sử dụng key trước revoke có thể đã gây tác động dữ liệu; thu hồi credential **không đảo ngược hành động đã hoàn tất**. Cần điều tra resource access và recovery riêng.

## 27. Bài thực hành tổng hợp từng bước

**Bước 1 — Thiết kế account và quyền.** Tạo service account `svc-export` chỉ được đọc orders thuộc tenant A, có owner team và trạng thái ACTIVE.

**Bước 2 — Thiết kế data model.** Tạo bảng service_account, service_api_key, service_api_key_scope với khóa ngoại composite tenant, expiry và revokedAt. Đặt policy indexes/audit.

**Bước 3 — Viết issuer.** CSPRNG 32 bytes, public key ID, format version; không dùng raw secret do client cung cấp. Tính HMAC với pepper từ KMS, lưu key version.

**Bước 4 — Viết management API.** Tạo key chỉ sau actor authentication, RBAC, tenant ownership, scopes allowlist; trả raw key đúng một lần và response no-store.

**Bước 5 — Cấu hình client.** Lưu vào secret manager, dùng HTTPS Authorization header, không log raw key.

**Bước 6 — Viết verifier.** Parse strictly bounded, lookup by key ID, verify HMAC constant-time, kiểm revocation/expiry/account/tenant; trả ServiceIdentity trusted hoặc failure.

**Bước 7 — Gắn Spring Security.** Tạo filter authentication stateless trong chain `/svc/**`, map scopes sang authorities, bảo đảm filter chạy trước AuthorizationFilter và không bị đăng ký hai lần.

**Bước 8 — Kiểm quyền resource.** Dùng `hasAuthority("SCOPE_orders:read")` và service/repository kiểm tenant + row ID.

**Bước 9 — Kiểm thử.** Gọi bằng key đúng/sai, đã revoke, hết hạn, disable account, scopes khác nhau, tenant khác nhau và request không key.

**Bước 10 — Rotate.** Phát hành K2, rollout, xác nhận traffic, revoke K1, test cả K1 401 và K2 200.

**Bước 11 — Vận hành.** Audit, expiry reminders, owner inventory, secret scanning, cache revocation SLO, incident response và metrics không chứa secrets.

### Điều kiện hoàn thành

- Không có nơi nào public API có thể đọc lại raw key cũ.
- Service không có quyền quản lý key nếu chỉ cần đọc orders.
- Thu hồi key cũ có hiệu lực trong SLO đã công bố.
- Thay key thành công mà không phải tắt authentication.
- Có test tenant isolation và không phát hiện credential trong logs.
- Cơ chế HMAC pepper/version có kế hoạch rotation.
- Không có request nào không authenticated vẫn được vào `/svc/**`.

## 28. Câu hỏi thường gặp

**Tại sao không lưu API key bằng BCrypt giống password?**

Nếu API key là 32 bytes ngẫu nhiên do CSPRNG tạo, entropy cao khiến dictionary attack không khả thi. Digest/HMAC mật mã nhanh với lookup public key ID thường phù hợp. Password của con người entropy thấp nên cần password hashing có cost/salt. Mọi chọn lựa vẫn cần threat model, bảo vệ DB và keys.

**Key ID có phải giữ bí mật không?**

Không. Nó dùng định vị record. Tuy nhiên public ID vẫn có thể là thông tin vận hành nên không xuất hiện bừa trong URL ngoài phạm vi. **Biết key ID không được giúp xác thực** nếu không có random secret.

**Thu hồi key đã hết hạn có cần không?**

Expiry đã làm key vô hiệu; vẫn có thể revoke để đánh dấu compromise và audit. Không được vì key expired mà bỏ qua yêu cầu lưu dấu sự cố hoặc dọn inventory.

**Có thể giảm quyền bằng cách xóa scope khỏi record không?**

Có thể theo policy, nhưng phải đồng bộ cache/authorization và có audit. Nhiều hệ thống ưu tiên issue key mới với scopes mới rồi revoke key cũ để thay đổi quyền có tính lịch sử rõ. **Không âm thầm mở rộng quyền của key hiện tại** khi account được cấp role mới.

**Vì sao revoke key vẫn có request 200?**

Có thể request đã qua authentication trước commit revoke, một node giữ cache stale, session được tạo sai từ key hoặc service không kiểm revocation ở request mới. Điều tra timeline, cache TTL, node và token/session architecture.

**API key bị mất thì có thể hiển thị lại không?**

Không nếu chỉ lưu one-way verifier. Tạo key mới, thay cấu hình client, revoke key cũ không còn kiểm soát. “Show once” là tính năng bảo mật, không phải thiếu UX.

**Có cần mỗi request kiểm DB không?**

Phụ thuộc latency, availability và revocation SLO. Cache ngắn/invalidation có thể phù hợp, nhưng phải tính rõ cửa sổ stale. Với tài nguyên rất nhạy cảm, có thể dùng introspection/DB check hoặc credential khác ràng buộc mạnh hơn.

## 29. Checklist cuối cùng

1. Service account có ID, tenant, owner, trạng thái và entitlement rõ?
2. Actor quản trị được xác thực/phân quyền trước khi tạo/thu hồi?
3. Token có public key ID tách biệt với random secret ít nhất 256 bit?
4. Secret do `SecureRandom` tạo và chỉ hiện một lần?
5. DB chỉ lưu verifier (SHA-256/HMAC), metadata, scopes, timestamps — không raw key?
6. Pepper từ KMS/secret manager có version và kế hoạch rotation?
7. Verifier parse bounded, constant-time check và fail closed khi store lỗi?
8. Key revoked/expired/account-disabled có bị từ chối ở request mới?
9. Authorization có giao scopes với account/tenant/resource policy?
10. Machine endpoints dùng header qua HTTPS, không query/cookie/secret log?
11. Spring Security chain stateless có filter trước authorization, không đăng ký hai lần và không lẫn web admin flow?
12. Rotation K1→K2 có overlap ngắn, deadline và test K1 401/K2 200?
13. Cache revocation có TTL/invalidation đáp ứng SLO và đo nhiều nodes?
14. Admin list/logs/audit không chứa key plaintext và không có đường show again?
15. Có regression tests cho invalid/expired/revoked/tenant/privilege escalation/concurrency?
16. Có người chịu trách nhiệm, expiry alerts, inventory, secret-scanning và incident runbook?

**Kết luận:** Tạo API key cho service account không dừng ở sinh chuỗi bí mật. Thiết kế an toàn cần **identity/service account**, **credential record**, **secret được hiển thị một lần**, **verifier một chiều**, **thời hạn và scopes tối thiểu**, **Spring Security authentication stateless**, **authorization theo tenant/resource**, cùng **rotation/revocation có kiểm chứng**. Nếu luôn kiểm key active và owner policy, không ghi raw secret vào hệ thống quan sát và có thể thay khóa theo kế hoạch, API key trở thành một credential vận hành có kiểm soát thay vì một “mật khẩu vĩnh viễn” không ai dám thu hồi.

### Tài liệu tham khảo

- OWASP — Secrets Management Cheat Sheet (creation, rotation, revocation, expiration): https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP — REST Security Cheat Sheet (API keys, rate limiting): https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP — API Security Top 10: https://owasp.org/API-Security/editions/2023/en/0x11-t10/
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Servlet Security Filters and Custom Filters: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — SecurityContext Persistence: https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Authentication Events: https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- Spring Security — MockMvc Authentication Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Oracle Java SE 17 — SecureRandom API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html
- Oracle Java SE 17 — MessageDigest API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
- Oracle Java SE 17 — Mac API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html
