# Luân chuyển bí mật, chứng chỉ và thông tin kết nối

## 1. Vì sao rotation là yêu cầu kiến trúc của microservices?

Một microservice thường kết nối nhiều hệ thống: database, cache, message broker, hệ thống định danh, API bên thứ ba và những service nội bộ. Những kết nối này dùng mật khẩu, API key, OAuth client secret, private key, TLS certificate, token, hoặc định danh workload. Ngoài bí mật, ứng dụng cần endpoint, hostname, port, truststore và các thuộc tính kết nối.

**Rotation (luân chuyển)** là quá trình thay thế phiên bản credential, key, certificate hoặc cấu hình kết nối đang dùng bằng phiên bản mới, chuyển consumer sang phiên bản mới và ngừng chấp nhận phiên bản cũ. Rotation xảy ra định kỳ hoặc khẩn cấp khi credential bị lộ, bị thu hồi quyền, sắp hết hạn, khi đổi provider hoặc thay hạ tầng.

Một thay đổi tưởng đơn giản có thể khiến hệ thống gián đoạn:

- Database đã đổi password, nhưng các instance còn dùng giá trị cũ.
- Chứng chỉ TLS mới đã triển khai, nhưng client chưa tin CA mới.
- Identity Provider ký JWT bằng khóa mới, nhưng service kiểm tra token còn cache public key cũ.
- DNS trỏ sang database mới, nhưng connection pool vẫn giữ phiên TCP tới máy cũ.
- Secret Manager cập nhật version mới, nhưng biến môi trường JVM chỉ được nạp lúc khởi động.
- Một batch job chạy hàng tuần vẫn cần key cũ và chỉ phát hiện lỗi sau khi key bị revoke.

**Mục tiêu của rotation tốt:** giảm thời gian credential cũ có thể bị lợi dụng, giữ đúng quyền hạn và duy trì khả năng phục vụ trong phạm vi SLO đã cam kết.

Sau bài học, bạn có thể lập inventory bí mật, chọn cách chuyển đổi có hoặc không có thời gian chồng lấn, xử lý reload của connection pool/TLS/JWKS, thiết kế giám sát và khôi phục, và phân biệt rotation định kỳ với ứng phó lộ credential.

## 2. Phân loại thứ cần luân chuyển

| Loại | Ví dụ | Điểm đặc biệt |
| --- | --- | --- |
| Password/secret truy cập | PostgreSQL password, Redis ACL secret | Consumer cần dùng version mới khi mở kết nối mới |
| API key | Key của payment provider, webhook sender | Provider có thể chỉ hỗ trợ một key hoặc nhiều key |
| OAuth client credential | Client secret, private key JWT, mTLS client cert | Phụ thuộc chính sách đăng ký client của IdP |
| TLS leaf certificate | Cert HTTPS của ingress hoặc service | SAN, chain, private key, expiry và reload |
| Root/intermediate CA | Trust bundle của client/service mesh | Phải phối hợp trust cả hai bên trước cutover |
| Signing key | JWT issuer key, webhook HMAC key | Verifier phải biết key mới; key cũ cần thời gian hết hiệu lực |
| Encryption key | KMS key, data-encryption key | Dữ liệu cũ có thể vẫn cần key cũ để giải mã |
| Workload identity | Chứng chỉ/token ngắn hạn của service | Gia hạn tự động, gắn với trust domain và identity |
| Connection configuration | DB hostname, broker endpoints, DNS, port | DNS cache, pool, ACL, TLS hostname và dữ liệu di trú |

**Certificate công khai không phải secret**, nhưng private key tương ứng là secret. **Endpoint không nhất thiết là secret**, nhưng thay endpoint có thể tác động nghiêm trọng như thay credential vì client tiếp tục giữ kết nối hoặc xác minh hostname sai.

Renewal, rotation và revocation khác nhau:

- **Renewal:** gia hạn credential/certificate; đôi khi giữ cùng key material.
- **Rotation:** chuyển sang một phiên bản hoặc khóa/danh tính mới.
- **Revocation:** làm bản cũ mất hiệu lực trước hoặc khi hết hạn; có thể gây lỗi cho consumer chưa chuyển.

Không dùng một quy trình chung mà bỏ qua các khác biệt này.

## 3. Inventory, chủ sở hữu và ranh giới phụ thuộc

Trước khi rotate, cần biết credential thuộc về ai, được cấp ở đâu và ai đang tiêu thụ.

```text
Checkout Service
     |
     +--> PostgreSQL: db username/password + JDBC URL
     +--> Kafka: SASL credential + CA trust
     +--> Payment Provider: API key
     +--> Identity Provider: JWKS public key cache
     +--> Orders Service: mTLS certificate
```

Với từng dependency, inventory tối thiểu nên ghi:

| Thuộc tính | Nội dung |
| --- | --- |
| Credential ID/version | Định danh không chứa giá trị secret; trạng thái active/retiring |
| Owner | Nhóm chịu trách nhiệm cấp, phân quyền, revoke, phê duyệt |
| Consumer | Service instances, worker, cron, DR, environment, partner |
| Storage | Secret Manager, Vault, mounted secret file, KMS, workload identity |
| Access scope | Principal, role, tenant, allowed endpoints, ACL |
| Expiry/TTL | Hạn dùng, thời điểm rotate tiếp theo, thời gian grace |
| Distribution | SDK fetch, volume, environment variable, agent, sidecar |
| Reload | Hot reload, close/recreate pool, rolling restart |
| Overlap | Provider có chấp nhận đồng thời old và new không? |
| Evidence | Audit/metrics xác nhận consumer chuyển sang version mới |
| Recovery | Bước dừng an toàn; cách tái cấp nếu old bị revoke |

Inventory cần bao gồm các job ít chạy, instance dự phòng, hệ thống đối tác và các replica chưa nâng cấp. Một secret không còn được khai báo trong cấu hình hiện tại vẫn có thể còn xuất hiện trong connection, cache hoặc một worker chưa restart.

## 4. Vòng đời và chiến lược chuyển phiên bản

Một vòng đời phù hợp có bốn trạng thái:

```text
STAGED   → ACTIVE   → RETIRING   → REVOKED
đã cấp     đang dùng   còn overlap  không được chấp nhận
```

Nếu nhà cung cấp hỗ trợ đồng thời hai credential, quy trình **expand → switch → contract** thường ít gián đoạn hơn cutover tức thời:

1. **Prepare:** tạo credential mới với quyền cần thiết, bảo vệ tại Secret Manager/PKI, kiểm tra cấu trúc/expiry.
2. **Expand:** cấu hình bên xác thực chấp nhận old và new trong khoảng chuyển tiếp hữu hạn.
3. **Canary:** một số consumer dùng new, xác minh tạo kết nối mới và thực hiện thao tác nghiệp vụ.
4. **Switch:** rollout mọi consumer; drain pool hoặc session cũ; quan sát lỗi và usage version.
5. **Contract:** thu hồi old khi các consumer liên quan không còn cần nó.
6. **Post-check:** old bị từ chối, new tiếp tục hoạt động, inventory và audit được cập nhật.

```text
Old accepted  ─────────────────┐
New accepted       ──────────────────────────────>
                 ^          ^            ^
              publish    canary+rollout  revoke old
```

**Khoảng chồng lấn không nên kéo dài vô hạn.** Nó giúp chuyển đổi an toàn nhưng cũng đồng nghĩa cả hai credential cùng có thể bị lợi dụng nếu bị lộ.

Nếu provider chỉ cho phép một key active, không có overlap thực sự. Khi đó cần chuẩn bị cutover, kiểm tra khả năng cập nhật đồng thời, đường truyền cấu hình, thời gian downtime được phép và phương án khôi phục. Không giả định hai credential luôn có thể cùng tồn tại.

## 5. Rotation database password và các connection đang sống

Giả sử Orders Service kết nối PostgreSQL bằng tài khoản `orders_app_v1`. Nếu server thay password trước khi tất cả consumer cập nhật, connection đã xác thực có thể còn sống, trong khi **connection mới** dùng password cũ sẽ bị từ chối. Pool có thể che lỗi đến khi autoscale, restart hoặc mất kết nối.

### Cách an toàn khi DB cho phép hai principal

1. Tạo `orders_app_v2`, gán đúng quyền tối thiểu.
2. Lưu credential mới vào Secret Manager, không ghi trong repository.
3. Kiểm tra kết nối mới và quyền đọc/ghi cần thiết từ canary.
4. Deploy từng instance dùng v2, xác nhận readiness rồi chuyển traffic.
5. Để instance v1 hoàn tất request đang chạy, đóng/drain pool.
6. Theo dõi session v1, job nền và consumer ít chạy.
7. Revoke account v1 khi không còn nhu cầu.

Ví dụ SQL minh họa vai trò, không chứa mật khẩu thật:

```sql
CREATE ROLE orders_app_v2 LOGIN;

-- Gán role nghiệp vụ theo chính sách quyền tối thiểu.
GRANT orders_application_role TO orders_app_v2;
```

Cú pháp và khả năng cấp quyền thay đổi theo DBMS. Cần kiểm tra cả quyền schema, bảng, sequence, default privilege, row-level security và connection limit; không nhân bản một role admin cho tiện.

### Nếu DB chỉ hỗ trợ đổi password cùng principal

Khả năng zero-downtime phụ thuộc DBMS: một số hệ hỗ trợ dual passwords hoặc grace period, một số không. Nếu không có overlap, phải thiết kế cutover theo môi trường thực tế và có thể cần bảo trì ngắn. Không tự khẳng định một DB nào đó chấp nhận mật khẩu cũ sau khi đã thay.

### Connection pool và Java

HikariCP và các pool khác có thể giữ connection cũ; thay secret trong một store không buộc pool tự đổi password. Cần trả lời:

- Pool tạo connection mới bằng nguồn credential hiện tại hay giá trị cố định từ startup?
- Có hỗ trợ reload DataSource thật sự không?
- Khi thay DataSource, các giao dịch đang chạy được drain thế nào?
- Connection timeout, idle/max lifetime và retry có làm bão reconnect khi backend chuyển không?

Trong nhiều hệ thống Spring Boot, **rolling restart** với readiness/drain dễ kiểm soát hơn thay trực tiếp DataSource đang hoạt động. Hot reload chỉ nên dùng khi đã kiểm chứng lifecycle của pool và thư viện.

## 6. API keys và OAuth client secret

API key có thể bị gắn với account, phạm vi API, IP allowlist, quota hoặc một merchant cụ thể. Một key mới không mặc nhiên có cùng quyền và quota.

Quy trình:
- Nếu provider cho phép, tạo second key và bật cả old/new.
- Cấp key mới qua secret store; một canary dùng key mới gọi thao tác an toàn.
- Kiểm tra 401/403, rate-limit, callback và chức năng thật sự.
- Rollout theo consumer; ghi nhận key/version nào còn traffic.
- Disable key cũ và xác nhận nó không còn hoạt động.

Đối với OAuth client secret, Client ID có thể giữ nguyên nhưng secret thay đổi; các chi tiết overlap/rotation do IdP quy định. Nếu client xác thực bằng `private_key_jwt` hoặc mTLS, rotation liên quan signing key hoặc client certificate thay vì chuỗi password.

Trong trường hợp provider không hỗ trợ dual keys, cần bản đồ consumer đầy đủ và điều phối cutover. Không đưa credential mới vào CI log, ticket, email, command history hoặc tham số URL để thuận tiện cho quá trình chuyển đổi.

## 7. TLS certificate rotation: leaf cert khác CA rotation

Kết nối TLS dùng:
- Certificate và private key của server.
- Truststore/CA bundle của client.
- Thông tin hostname/SAN và thuật toán được hỗ trợ.
- Với mTLS, thêm certificate client và truststore phía server.

### Đổi leaf certificate nhưng giữ CA

Nếu CA không đổi và client vẫn tin chain, thường có thể cấp leaf mới rồi reload ingress/server:

```text
Trusted CA
    ├── old leaf (expires soon)
    └── new leaf (valid, correct SAN)
```

Kiểm tra: SAN hợp hostname thực, chain đầy đủ, private key khớp certificate, key usage/EKU, hạn dùng và cấu hình TLS. Với Java service tự sở hữu SSLContext, đừng mặc định tiến trình sẽ đọc lại file chứng chỉ trên đĩa; có thể cần tạo client/server context mới hoặc rolling restart.

Client đang giữ connection TLS cũ có thể tiếp tục dùng session trước cutover. Phải kiểm tra **handshake của connection mới**, không chỉ request qua connection có sẵn.

### Đổi root/intermediate CA

Chuyển trusted root cần phối hợp hai phía:

```text
Bước 1: Client tin Old CA
Bước 2: Client tin Old CA + New CA
Bước 3: Server trình certificate chain từ New CA
Bước 4: Client chỉ tin New CA
Bước 5: Retire Old CA
```

Nếu server chuyển ở bước 3 trước khi client hoàn tất bước 2, lỗi `unknown_ca` xảy ra. Nếu dùng certificate pinning, phải triển khai pin mới hoặc pin dự phòng trước cutover. Không tắt xác minh certificate/hostname để “chữa” lỗi chuyển CA.

Theo dõi `tls_handshake_failures`, `certificate_expiry_seconds`, serial/issuer an toàn trong audit và kết quả handshake từ các client ở từng region/mạng.

## 8. mTLS, certificate workload và rotation tự động

Trong service mesh, workload identity có thể được cấp certificate ngắn hạn và tự gia hạn. Điều này giảm phụ thuộc vào mật khẩu tĩnh, nhưng tạo trách nhiệm vận hành:

- CA/issuer và agent có sẵn để renew trước expiry.
- Workload lấy đúng danh tính service/namespace/trust domain.
- Peer nhận được trust bundle mới đủ sớm.
- Policy service-to-service vẫn phân quyền theo workload identity.
- Hệ thống biết phải làm gì khi cert hết hạn hoặc control plane tạm mất.
- Thu hồi một workload bị xâm nhập không dựa duy nhất vào chờ cert tự hết hạn nếu rủi ro quá cao.

Ví dụ `spiffe://prod.example/ns/orders/sa/orders-service` là identity của workload. Nó **không thay thế** quyền của người dùng cuối đối với hóa đơn, tài khoản hay dữ liệu nghiệp vụ.

Nếu TLS được terminate ở sidecar, service mesh có thể sở hữu vòng đời certificate. Nếu ứng dụng Java tự làm TLS, nhóm phát triển phải xác minh cách nạp lại keystore/truststore và close/recreate connection theo phiên bản chứng chỉ mới.

## 9. Signing key rotation cho JWT và JWKS

Đổi signing key có thêm một chiều thời gian: token cũ có thể **chưa hết hạn**, nên consumer vẫn cần khả năng kiểm tra chữ ký old trong khoảng hợp lệ.

Với JWT chữ ký bất đối xứng, Identity Provider thường công bố public keys qua JWKS; header token có `kid` để chọn key. Một quy trình định kỳ điển hình:

1. Publish `NEW` public key vào JWKS cùng `OLD`.
2. Chờ/cưỡng chế resource servers cập nhật cache và thử xác minh bằng new key.
3. Issuer bắt đầu ký JWT mới bằng `NEW`, có `kid` thích hợp.
4. Chờ token ký bằng `OLD` hết hạn, tính cả clock skew và cache.
5. Gỡ `OLD` khỏi JWKS theo chính sách.

```text
JWKS:       [OLD] → [OLD, NEW] ──────────→ [NEW]
JWT signer:  OLD ──────────────→ NEW ─────────>
Consumer:   refresh keys, verify both during overlap
```

Lỗi điển hình: issuer ký với new trước khi verifier có thể tải new, gây 401 hàng loạt. Lỗi đối xứng: gỡ old khỏi JWKS quá sớm khiến token chưa hết hạn bị từ chối.

Đừng tin tùy ý URL hay thuật toán tự khai từ token để tải key. Verifier phải ràng buộc issuer, audience, thuật toán và nguồn JWKS tin cậy. Khi private signing key bị compromise, có thể cần vô hiệu hóa ngay token đã ký bằng key đó; không giữ overlap dài chỉ để tránh gián đoạn.

Webhook HMAC secret rotation cũng cần old/new verifier trong giai đoạn chuyển nếu provider hỗ trợ. So sánh chữ ký bằng thao tác constant-time, giới hạn số key được thử và không log raw secret.

## 10. Encryption key rotation và dữ liệu lịch sử

Mật khẩu mới dùng cho kết nối mới; nhưng **encryption key mới không tự giải mã được ciphertext cũ**.

Với envelope encryption:

```text
KMS Key Encryption Key (KEK)
       |
       +-- bọc Data Encryption Key (DEK)
                     |
                     +-- DEK mã hóa dữ liệu
```

Khi rotate KEK, phiên bản cũ có thể vẫn phải tồn tại để unwrap DEK cũ. Nếu cần hủy key cũ, phải rewrap hoặc re-encrypt dữ liệu được bảo vệ, cả backup/snapshot/DR nếu áp dụng. Lưu key ID/version cùng metadata ciphertext để biết key nào dùng giải mã.

Đổi alias active trên KMS **không có nghĩa** dữ liệu lịch sử đã được mã hóa lại. Xóa key version đang cần giải mã có thể khiến dữ liệu mất khả năng khôi phục. Rotation key phải có kế hoạch khôi phục dữ liệu và quy trình kiểm chứng riêng, không chỉ kiểm tra application đang chạy.

## 11. Đổi hostname, port và endpoint kết nối

Một thay đổi DB primary hay broker cũng ảnh hưởng rotation:

```text
old-db.internal:5432 → new-db.internal:5432
                  |
                  +--> DNS cache
                  +--> JDBC URL / pool
                  +--> NetworkPolicy / firewall
                  +--> TLS hostname / SAN
                  +--> DB users / roles / data replication
```

Những điểm phải kiểm tra:

- **DNS TTL/cache:** record đổi không bảo đảm mọi JVM, proxy và SDK lập tức giải lại tên.
- **Connection pool:** connection cũ tiếp tục tới IP cũ; cần drain/reconnect.
- **TLS:** certificate endpoint mới phải hợp lệ cho hostname mà client yêu cầu.
- **Networking:** route và ACL đến địa chỉ mới đã được cấp trước cutover.
- **Credential:** database hoặc broker đích có principal và quyền tương ứng.
- **Data:** trạng thái replication, transaction và failover đã an toàn.
- **Rollback:** quay lại primary cũ có thể gây split-brain hoặc mất write sau cutover.

Đối với Kafka, bootstrap servers là nơi lấy metadata; client còn kết nối đến `advertised.listeners` của broker. Chỉ đổi bootstrap hostname đôi khi chưa đủ.

Nên tách đổi endpoint và đổi credential thành các change riêng nếu deadline/kiến trúc cho phép, để dễ khoanh vùng lỗi.

## 12. Đưa secret mới tới microservice

| Cơ chế | Đặc tính | Chú ý |
| --- | --- | --- |
| Secret Manager SDK | IAM, audit, version, lấy khi cần | TTL cache, mạng, quota và bootstrap |
| Mounted file/CSI | Có thể thay dữ liệu file mà không rebuild image | App phải reload; atomic update và quyền file |
| Environment variable | Dễ cấu hình cho ứng dụng cũ | Tiến trình đang chạy thường không tự nhận giá trị mới |
| Vault/sidecar agent | Agent renew và phân phối credential | Agent availability, file ownership, reload |
| Workload identity ngắn hạn | Giảm password tĩnh | Renewal, clock skew, token cache, trust boundary |

Không đưa secret vào Git, Docker image, static build artifact hoặc log. Nếu dùng Kubernetes, `Secret` là đối tượng chứa dữ liệu nhạy cảm nhưng cần cấu hình thêm RBAC, encryption at rest và audit phù hợp. Environment variables lấy từ Kubernetes Secret thường chỉ phản ánh giá trị lúc container khởi động; mounted volume có thể cập nhật nhưng ứng dụng phải đọc lại. Cấu hình mount theo `subPath` có đặc điểm cập nhật riêng.

Ví dụ Spring Boot nhận credential khi startup:

```yaml
spring:
  datasource:
    url: REPLACE_WITH_ENV_ORDERS_DB_URL
    username: REPLACE_WITH_ENV_ORDERS_DB_USER
    password: REPLACE_WITH_ENV_ORDERS_DB_PASSWORD
```

Các placeholder trên minh họa **những giá trị cần được cấu hình từ secret store hoặc environment**, không phải YAML dành để deploy nguyên văn. Việc map property từ environment và xử lý injection phụ thuộc cơ chế triển khai.

Thay nội dung trong Secret Manager không làm bean Spring hoặc HikariCP tự động dùng version mới nếu application chưa hỗ trợ reload. Với phần lớn ứng dụng, rollout mới theo secret version rõ ràng là lựa chọn dự đoán được.

## 13. Rolling deployment, readiness và kết nối mới

Một quy trình cập nhật workload:

```text
New secret version available
              |
              v
Canary pod starts with NEW
              |
              v
Connect to dependency + exercise safe operation
              |
              v
Readiness passes → receive traffic
              |
              v
Progressive rollout of remaining replicas
              |
              v
Old replicas drain → close old pools
              |
              v
Old credential usage reaches zero
```

Phân biệt:
- **Liveness:** process còn hoạt động, không nhất thiết chứng minh mọi credential đã cập nhật.
- **Readiness:** instance có đủ điều kiện nhận request; cần kiểm tra đường kết nối liên quan mà không gây tải nguy hiểm.
- **Synthetic test/canary:** xác minh **mở kết nối mới** và thực hiện operation nghiệp vụ, không chỉ kiểm tra một HTTP 200 của health endpoint.

Tránh rollout đồng loạt khiến hàng trăm pool mở lại connection cùng lúc; dùng cadence, concurrency limits và backoff/jitter cho reconnect. Khi ứng dụng có giao dịch dài, cần preStop/drain và timeout hợp lý thay vì đóng pool ngay khi service vừa bị rút khỏi load balancer.

## 14. Metrics, audit và chứng cứ hoàn tất

Theo dõi tối thiểu theo dependency, service và credential version không nhạy cảm:

| Chỉ số | Ý nghĩa |
| --- | --- |
| `credential_age_days` / `rotation_last_success` | Tuổi và lần rotate gần nhất |
| `certificate_expiry_seconds` | Thời gian còn lại trước khi cert hết hạn |
| `auth_failures_total` | DB auth, SASL, OAuth 401/403 và credential reject |
| `tls_handshake_failures_total` | CA/hostname/certificate mismatch |
| `new_connections_total` | Kiểm tra tạo connection mới sau khi đổi |
| `connection_pool_active` / `pending` | Nghẽn pool và reconnect storm |
| `old_credential_usage` | Consumer chưa chuyển sang bản mới |
| `rotation_phase_failures_total` | Lỗi ở prepare, canary, switch, revoke |
| `request_error_rate` và `p95_latency` | Tác động tới người dùng cuối |

Tên metric là ví dụ; implementation thật có thể khác. Không đặt password, private key, bearer token hoặc connection string chứa secret vào metrics labels, spans hay log. Nếu dùng key ID/certificate serial để đo version, cần kiểm soát cardinality và quyền xem telemetry.

**Rotation hoàn tất khi:** mọi consumer cần thiết tạo connection mới bằng credential mới, chức năng thực tế vẫn chạy, old không còn usage trong khoảng quan sát phù hợp, old đã bị vô hiệu hóa và thử nghiệm tiêu cực xác nhận old bị từ chối. Chỉ nhìn trạng thái “new version created” của secret store chưa đủ.

## 15. Rollback khác incident response

### Rotation định kỳ

Trong giai đoạn overlap, nếu canary thất bại, có thể dừng rollout và tạm quay về old khi old còn an toàn. Sau khi revoke, việc “bật lại old” có thể trái chính sách hoặc không còn khả thi; nên cấp phiên bản mới phù hợp thay vì khôi phục secret đã bị hủy.

### Secret hoặc private key bị lộ

Khi có bằng chứng compromise:
1. Khoanh vùng credential, consumer, quyền và khả năng truy cập trái phép.
2. Ưu tiên giảm thời gian old có thể bị sử dụng: revoke/disable khẩn cấp nếu rủi ro yêu cầu, ngay cả khi gián đoạn có kiểm soát.
3. Cấp secret/key mới từ môi trường tin cậy và phân phối lại cho các consumer.
4. Kiểm tra access audit, thao tác bất thường và thay đổi quyền/persistence.
5. Tìm bản sao bị lộ ở Git history, CI logs, tickets, backup, container layer, crash dump.
6. Ghi rõ phạm vi ảnh hưởng, bước khôi phục và cập nhật kế hoạch phòng ngừa.

Với JWT signing key bị lộ, tokens ký bằng old có thể không còn tin cậy; cần phương án hủy hiệu lực, bắt đăng nhập lại hoặc kiểm tra bổ sung. Với encryption key bị lộ, cần đánh giá và có thể re-encrypt dữ liệu; chỉ tạo key mới không bảo vệ lại ciphertext đã bị sao chép.

**Lưu ý rollback dữ liệu:** sau khi đổi database primary, quay connection về primary cũ có thể mất transaction đã ghi vào primary mới. Khôi phục connection và khôi phục tính nhất quán là hai bài toán khác nhau.

## 16. Failure modes thường gặp

| Triệu chứng | Nguyên nhân gốc hay gặp | Phòng ngừa |
| --- | --- | --- |
| Service chỉ lỗi sau restart | Connection cũ còn sống, password mới chưa được nạp | Canary thử startup và tạo connection mới |
| 401 sau đổi JWT signing key | JWKS cache chưa có public key mới | Publish new key trước khi đổi signer |
| Token cũ bị từ chối dù chưa hết hạn | Gỡ old key quá sớm | Đo TTL token, skew và cache |
| TLS handshake `unknown_ca` | Client chưa có new root CA | Dual trust trước server cutover |
| TLS hostname mismatch | Endpoint mới có SAN sai | Kiểm tra certificate theo hostname thực |
| Pool cạn connection sau deploy | Reconnect đồng loạt/credential mới bị reject | Progressive rollout và pool sizing |
| Batch job hỏng một tuần sau | Consumer ít chạy bị bỏ khỏi inventory | Inventory mọi consumer và kiểm tra định kỳ |
| Đổi KMS key rồi mất dữ liệu | Old key bị hủy trước khi rewrap ciphertext | Giữ key giải mã cho dữ liệu cũ |
| Secret file cập nhật nhưng app dùng cũ | Không có reload contract | Hot reload kiểm chứng hoặc rolling restart |
| Kafka client không nối được broker mới | Advertised endpoint/ACL sai | Kiểm tra bootstrap và broker endpoints |
| Secret mới lộ trong log | Debug dump/cấu hình in credential | Redaction, access control, secret handling |

## 17. Workflow automation an toàn

```text
Discover consumers + owner
             |
             v
Issue NEW with least privilege
             |
             v
Store NEW securely, record version
             |
             v
Enable overlap if supported
             |
             v
Canary + new-connection validation
             |
             v
Rollout consumers progressively
             |
             v
Observe OLD usage = 0
             |
             v
Revoke OLD, negative test
             |
             v
Audit + schedule next rotation
```

Automation cần các đặc tính:
- **Idempotent:** chạy lại không tạo vô hạn credential hoặc revoke nhầm bản active.
- **Version-aware:** mọi bước gắn ID/version, không dựa mù vào “latest”.
- **Least privilege:** controller chỉ có quyền cần để issue/revoke loại secret được giao.
- **Time-bound:** overlap có giới hạn; báo động khi quá deadline.
- **Recoverable:** dừng an toàn tại canary/rollout; không tự revoke khi migration chưa xác minh.
- **Concurrency-safe:** không cho hai workflow cùng rotate một principal mà không điều phối.
- **Observable:** event từng phase, chủ thể thay đổi và kết quả, không log secret.
- **Failure-aware:** Secret Manager/CA outage cần chính sách rõ cho service đang phục vụ và credential sắp hết hạn.

Mỗi provider phải có adapter theo semantics của nó. Đừng áp cùng một tác vụ “set password, restart all, revoke” cho DB credential, CA và signing key.

## 18. Bài tập áp dụng

**Bài 1 — Inventory.** Vẽ kiến trúc Checkout gọi PostgreSQL, Kafka và Payment Provider. Với mỗi đường, ghi owner, credential type, storage, consumer, TTL và cách reload. Bổ sung ít nhất một cron/worker ít chạy.

**Bài 2 — Database credential.** Thiết kế rotation từ `orders_app_v1` sang `orders_app_v2` bằng rolling deployment. Ghi tiêu chí canary, cách drain HikariCP, cách nhận diện connection cũ và thời điểm thu hồi v1.

**Bài 3 — Root CA.** Một nửa client vẫn chỉ tin old CA trong khi server định triển khai cert từ new CA. Hãy sắp thứ tự update truststore, server cert và retire root. Nêu phép thử handshake từ client thực.

**Bài 4 — JWT key.** Token sống tối đa 30 phút, JWKS cache 10 phút. Hãy lập timeline publish new key, đổi signer, chờ token cũ hết hạn rồi gỡ old key. Trình bày khác biệt khi old key bị lộ.

**Bài 5 — Endpoint.** Database chuyển sang hostname mới. Phân tích DNS/JVM cache, connection pool, TLS SAN, firewall, replication và rollback không gây split-brain.

**Bài 6 — Automation.** Xây state machine `STAGED → ACTIVE → RETIRING → REVOKED` và điều kiện chuyển trạng thái. Cho biết khi nào phải dừng và gọi operator thay vì tự động revoke.

## 19. Ghi nhớ

- **Rotation là một thay đổi xuyên nhiều thành phần**, từ issuer/provider, secret store tới service, connection pool và audit.
- **Expand → switch → contract** chỉ thực hiện được khi old+new có thể cùng được chấp nhận; nếu không, thiết kế cutover có chủ đích.
- **Chứng chỉ leaf, CA root, JWT signing key và encryption key có vòng đời khác nhau**; đặc biệt dữ liệu cũ có thể cần key cũ để giải mã.
- **DNS, TLS truststore, JWKS cache, JVM configuration và connection pool** có thể giữ trạng thái cũ sau khi cấu hình trung tâm đã thay.
- **Kiểm tra kết nối mới và restart/canary**, không chỉ dựa vào kết nối đang sống hoặc trạng thái secret store.
- **Không revoke credential cũ khi chưa có bằng chứng migration đủ**, trừ khi sự cố bảo mật yêu cầu cắt quyền khẩn cấp.
- **Không lộ secret** qua Git, image, CI logs, diagnostics, telemetry hoặc tài liệu hướng dẫn triển khai.

### Đọc thêm

- NIST SP 800-57 Part 1 — Recommendation for Key Management: https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final
- RFC 5280 — X.509 Certificate and CRL Profile: https://www.rfc-editor.org/rfc/rfc5280
- RFC 7517 — JSON Web Key (JWK): https://www.rfc-editor.org/rfc/rfc7517
- RFC 8725 — JSON Web Token Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- Kubernetes Secrets: https://kubernetes.io/docs/concepts/configuration/secret/
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- SPIFFE Concepts: https://spiffe.io/docs/latest/spiffe-about/overview/

Tham số và cơ chế reload/revocation cụ thể phụ thuộc DBMS, Identity Provider, Secret Manager, service mesh và thư viện đang chạy. Cần đối chiếu tài liệu triển khai hiện tại trước khi áp dụng vào production.
