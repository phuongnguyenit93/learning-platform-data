# Quản lý mật khẩu kết nối, client secret, khóa ký và bí mật ứng dụng

## 1. Mục tiêu và phạm vi

Trong một ứng dụng Spring Boot, việc đăng nhập người dùng chỉ là một phần của bảo mật. Bản thân ứng dụng cũng phải chứng minh danh tính khi kết nối PostgreSQL, LDAP, Redis, SMTP, OAuth2 Authorization Server, hệ thống đối tác hoặc secret manager. Nếu hệ thống phát hành JWT, nó còn có private signing key; nếu chỉ kiểm tra JWT, nó cần xác minh public keys và nguồn phát hành. Những dữ liệu này có **mức nhạy cảm, nơi lưu, quyền truy cập và chu kỳ rotation khác nhau**.

Đề bài nằm trong nhóm **Vận hành** của module **Spring Security - authentication**. Bài tập trung vào cách **cấp phát, lưu, phân phối, tiêu thụ, xoay vòng, thu hồi và kiểm toán** secrets, thay vì chỉ đặt một mật khẩu vào file cấu hình rồi cho rằng đã an toàn.

Sau bài, bạn có thể:

1. Phân biệt password của người dùng với mật khẩu service account, OAuth2 client secret, API key, private signing key, encryption key và public JWK.
2. Chọn đúng nơi lưu: secret manager, KMS/HSM, workload identity, mounted file hoặc environment variable với threat model cụ thể.
3. Sử dụng Spring Boot 3.5/Java 17+ externalized configuration, config trees và các property names chuẩn của OAuth2 client.
4. Hiểu cách resource server kiểm tra JWT bằng public JWKS mà không giữ private signing key.
5. Thiết kế rotation không gián đoạn **khi hệ thống phụ thuộc hỗ trợ**, gồm key ID, active version, overlap, readiness check và revoke.
6. Xử lý sự cố lộ mật khẩu/khóa, ngăn rò qua Git, CI/CD, container, log, tracing, Actuator và HTTP.
7. Chạy chương trình Java 17 mô phỏng key rotation và ví dụ Spring Security đọc password từ cấu hình ngoài.
8. Viết test và checklist kiểm chứng **fail-closed, least privilege, không log bí mật, session/token và operational readiness**.

Đây là kiến thức vận hành bảo mật. Các mẫu trong bài là môi trường học tập, không phải chứng nhận phù hợp chuẩn bảo mật hay một hệ thống IAM/JWT issuer hoàn chỉnh.

## 2. Phân loại: cái gì bí mật, cái gì không?

| Loại dữ liệu | Có cần giữ bí mật? | Mục đích |
| --- | --- | --- |
| Mật khẩu kết nối JDBC | **Có** | Service account kết nối database |
| LDAP bind password | **Có** | Dịch vụ lookup/authenticate qua directory |
| Redis/Kafka/SMTP credentials | **Có** | Xác thực với hạ tầng |
| OAuth2 client ID | Thường **không** | Định danh client |
| OAuth2 client secret | **Có** | Confidential client chứng minh danh tính với authorization server |
| API key, webhook HMAC secret | **Có** | Xác thực máy hoặc tính toàn vẹn request |
| JWT RSA/EC private signing key | **Rất nhạy cảm** | Tạo chữ ký JWT |
| JWT public verification key/JWKS | Thường **không cần giấu** | Verify chữ ký, nhưng phải xác thực nguồn và thuật toán |
| JWT symmetric HS256 key | **Có** | Vừa ký vừa verify MAC |
| Session signing/encryption key | **Có** | Chống giả mạo cookie/session token khi cơ chế sử dụng |
| Encryption key/AES key | **Có** | Giải mã/mã hóa dữ liệu |
| TLS private key | **Có** | Chứng minh quyền sở hữu certificate |
| TLS public certificate | Không, nhưng phải đáng tin | Trust và xác minh server/client |
| Password do người dùng nhập | **Có** | Authentication người dùng; lưu bằng password hash, không lưu plaintext |
| Secret name/version | Tùy mức bảo mật | Metadata để định tuyến và kiểm toán |

**Đừng nhầm client ID với client secret.** Client ID không phải mật khẩu thay thế; trong confidential client, secret mới là shared credential. **Đừng nhầm public key với private key.** Public JWKS có thể xuất bản cho resource servers, nhưng private key của signer không được xuất hiện trong JWKS public.

**Không reuse một giá trị** giữa JWT signing, API key, database password, encryption và OAuth2 client authentication. Các bí mật độc lập làm giảm thiệt hại nếu một integration bị xâm phạm.

## 3. Password người dùng khác secret của service như thế nào?

**End-user password** chỉ cần được **xác minh**, vì vậy server nên lưu một salted, slow password verifier qua `PasswordEncoder`, như Argon2id/bcrypt/PBKDF2 theo chính sách. Không cần biết lại password nguyên bản. Không giữ bản rõ bằng reversible encryption trong bảng users chỉ để tiện gửi email hoặc debug.

**Service credential** nhiều khi phải được **sử dụng thực sự**: JDBC driver gửi password để bắt tay với DB, OAuth2 client gửi client secret đến token endpoint, hoặc hệ thống ký JWT dùng private key. Vì vậy lưu duy nhất một hash không đủ cho phần tiêu thụ. Service secret cần một nguồn đáng tin (managed secret store, dynamic credential, KMS/HSM) và một đường phân phối an toàn.

| Tiêu chí | Password user | Secret ứng dụng |
| --- | --- | --- |
| Phục hồi bản rõ sau khi lưu? | Không | Có thể cần hoặc phải gọi KMS/HSM |
| Nơi lưu | Salted password hash | Secrets manager, credential provider, KMS/HSM |
| Đổi định kỳ? | Không tự động áp dụng; NIST không khuyến nghị buộc đổi vô căn cứ | Theo policy, TTL, rủi ro và giới hạn provider |
| Khi lộ | Reset mật khẩu, bảo vệ account và sessions | Revoke/reissue, rollout consumers, điều tra hệ thống phụ thuộc |
| Quyền | User identity và policy | Workload/service account identity, IAM, least privilege |

NIST SP 800-63B-4 khuyến cáo **không bắt người dùng đổi mật khẩu định kỳ** nếu không có bằng chứng bị compromise. Đừng áp dụng nguyên xi lời khuyên đó cho client secret hoặc signing key của ứng dụng: các bí mật máy có threat model, lease và vòng đời khác.

## 4. Threat model: bí mật rò rỉ qua những đường nào?

Các vị trí nguy hiểm:

- Repository: `application-prod.yml`, `.env`, keystore, private key PEM, file backup, test fixture lấy từ production.
- Git history, pull request comments, forks và source-code mirror: xóa một commit mới **không thu hồi** secret đã lộ.
- Docker image/JAR, build cache, SBOM, CI artifacts, Helm values; secret có thể còn trong một layer cũ.
- CI/CD logs: debug shell, `set -x`, job outputs, variables bị echo, process arguments.
- Process: environment variables, command line, heap dump, core dump, live debug, JMX, container exec.
- HTTP: Authorization header, cookie, API key, OAuth callback, refresh token, connection URL có userinfo, URL query/referrer.
- Actuator: `/env`, `/configprops`, `/heapdump`, `/logfile`, custom error/health endpoint.
- Proxy/APM: raw headers/body, traces, structured logs, error reports, metrics tags.
- Kubernetes: ServiceAccount/RBAC quá rộng, người có quyền đọc Secrets hoặc tạo pod để mount chúng; etcd encryption chưa bật.
- Secrets manager: root/admin token hard-code, workload identity cấp quá quyền, audit thiếu hoặc cross-environment access.
- Network: gửi password tới một token endpoint/JWKS/DB host bị attacker kiểm soát vì TLS verification bị tắt.

**Câu hỏi kiểm toán:** ai sinh secret; ai có quyền đọc; secret nằm trong storage/backup nào; đường nào mang nó tới process; nó còn sống bao lâu; có thể thu hồi nhanh không; và ai nhận cảnh báo khi có truy cập bất thường?

## 5. Vòng đời chuẩn của một bí mật ứng dụng

```text
Inventory / owner / classification
         |
         v
Generate or provision (CSPRNG, HSM, IdP, DB)
         |
         v
Store securely (version, TTL, IAM, audit)
         |
         v
Deliver to authorized workload (TLS, identity, mount)
         |
         v
Use only for intended purpose (least privilege)
         |
         v
Monitor access, expiry and failures
         |
         v
Issue version v2 -> controlled rollout -> validate v2
         |
         +-- overlap v1/v2 if backend supports it
         |
         v
Revoke v1 -> remove stale references -> audit cleanup
```

Inventory nên có: secret ID/reference, môi trường, owner/on-call, permissions, consumers, creation time, version, last rotation, expiry/lease, dependent services, recovery steps, revocation endpoint và incident runbook. **Inventory không cần lưu bản rõ của secret.**

Một secret có thể tồn tại ở nhiều **bản copy**: manager, secret projection volume, process heap, connection pool, cached configuration, backup, log và CI artifact. Rotation chỉ thật sự hoàn thành khi đã xử lý mọi consumer và copy còn có khả năng bị sử dụng.

OWASP Secrets Management Cheat Sheet nhấn mạnh: tạo đủ ngẫu nhiên, quyền tối thiểu, lưu/truyền an toàn, rotation, revocation, expiration và audit. **Bảo mật khi lưu** phải đi kèm **kiểm soát khi dùng**.

## 6. Tạo bí mật có đủ entropy

Đối với random machine credentials, dùng **CSPRNG**. Ví dụ tạo 32 bytes ngẫu nhiên và encode hex:

```bash
# Lệnh lab trên máy quản lý secrets; bảo vệ terminal/stdout.
openssl rand -hex 32
```

32 bytes = 256 bits entropy trước khi encode. Kết quả có 64 ký tự hexadecimal, phù hợp làm **một random token** khi protocol chấp nhận. Không tự động biến giá trị này thành RSA/EC private key hoặc certificate: asymmetric keys phải được tạo bằng key generator/KMS/HSM đúng loại thuật toán, key usage, key size và policy.

**Không dùng** `Math.random()`, ngày tháng, secret viết trong README, chuỗi dễ đoán hoặc client ID làm signing key. Không commit giá trị được sinh. Trong sản phẩm thật, ưu tiên đưa output trực tiếp vào secret manager theo đường an toàn thay vì copy thủ công qua chat hoặc issue tracker.

Với JWT HS256, secret key phải có entropy và chiều dài phù hợp thuật toán; một password thông thường không phải key HMAC tốt. Với private signing key, cân nhắc KMS/HSM **không export** để process không cần giữ raw private bytes.

## 7. Chọn chỗ lưu secret: trade-off cụ thể

| Nguồn | Điểm mạnh | Hạn chế |
| --- | --- | --- |
| Hard-code vào Java/YAML rồi commit | Dễ thử | **Không dùng cho giá trị thật** |
| File `.env` không commit | Tiện local | Rủi ro backup, IDE, file permissions, chia sẻ máy |
| Environment variables | Boot đọc tự nhiên | Có thể lộ qua process inspection, debug, dumps và CI |
| Mounted secret file | Không cần CLI argument; file permissions rõ | Pod/node access; thay file chưa chắc reload bean |
| Kubernetes Secret | Tích hợp với deployment/RBAC | Base64 không phải encryption; RBAC, etcd, exec access cần được bảo vệ |
| Central secret manager | IAM, audit, version, lease, policy | Phụ thuộc bootstrap trust/availability |
| Dynamic DB credentials | TTL ngắn, revoke dễ hơn | Quản lý lease và connection pool phức tạp |
| KMS/HSM | Private key được bảo vệ, key usage rõ | Latency, authorization, SDK và availability |
| Cloud workload identity | Giảm static secrets | Cần federation/trust configuration đúng |

**Environment variable không phải hộp an toàn tuyệt đối.** Nó hữu ích hơn hard-code trong Git, nhưng vẫn hiển diện cho các công cụ và process có quyền phù hợp. **Kubernetes Secret không phải encrypted secret vault mặc định** chỉ vì được đặt tên là Secret.

Dùng **định danh workload riêng** cho dev/staging/prod. Một worker production đọc secret của chính nó, không có quyền duyệt toàn bộ keys trong namespace hoặc gọi admin API của Vault.

## 8. Spring Boot 3.5: externalized configuration

Spring Boot có PropertySources, environment variables, config imports và configuration trees. Ví dụ YAML **minh họa**:

```yaml
spring:
  datasource:
    url: "${DB_JDBC_URL}"
    username: "${DB_USERNAME}"
    password: "${DB_PASSWORD}"

app:
  partner:
    client-id: "${PARTNER_CLIENT_ID}"
    client-secret: "${PARTNER_CLIENT_SECRET}"
```

Đây là configuration fragment, **chưa chạy độc lập** nếu thiếu JDBC driver, DB server và client code. Không lưu mật khẩu thật trong các properties này; `${...}` là Spring placeholder được thay lúc runtime.

### 8.1. Fail-closed thay vì default yếu

Không dùng:

```yaml
spring:
  datasource:
    password: "${DB_PASSWORD:password123}"
```

Một môi trường production thiếu biến sẽ vô tình sử dụng mật khẩu mặc định. Nên bắt buộc cung cấp secret, validate quyền và giới hạn startup khi không có. Nếu app cho phép một chức năng chạy không cần secret, **mode đó phải được xác định rõ** chứ không tự mở tất cả endpoints.

### 8.2. Mounted config trees

Spring Boot 3.5 chính thức hỗ trợ:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/myapp/"
```

File tree do platform mount:

```text
/run/secrets/myapp/
    app.partner.client-id
    app.partner.client-secret
    spring.datasource.password
```

Tên file trở thành property key, file content là value. Mount read-only với quyền filesystem phù hợp. `optional:configtree:/run/secrets/myapp/` chỉ phù hợp khi thiếu thư mục secret là **hợp lệ theo thiết kế**; với secrets bắt buộc, nên fail-fast.

**Không mặc định hot reload:** file secret thay đổi ở Kubernetes hoặc secret manager không có nghĩa `@Value`, `ClientRegistration`, Hikari pool và JWT signer đang hoạt động được cập nhật tự động. Cần xác định cơ chế refresh, bean recreation, connection recycling và rolling restart.

### 8.3. Property precedence và override

Một giá trị có thể đến từ application.yml, env, imported config, command-line args và custom source. Nếu máy production cho phép người không đáng tin sửa command-line args hoặc config override, secret thật có thể bị thay hoặc redirect tới endpoint khác.

Đừng chỉ hỏi “secret có nằm trong Vault không?”. Hỏi thêm “**giá trị nào thực tế được Spring dùng** và ai có quyền ghi source đó?”. Test cấu hình trên deployment thật, không chỉ test source code.

## 9. Kubernetes Secret, workload identity và Vault

Một Deployment có thể mount Secret qua volume:

```yaml
# Trích đoạn Pod template, không phải manifest hoàn chỉnh.
spec:
  serviceAccountName: inventory-api
  containers:
    - name: app
      image: registry.example.com/inventory-api:stable
      volumeMounts:
        - name: secrets
          mountPath: /run/secrets/myapp
          readOnly: true
  volumes:
    - name: secrets
      secret:
        secretName: inventory-api-runtime
        defaultMode: 0400
```

**Không** commit một manifest chứa `stringData` với giá trị production. Cấp secret thông qua pipeline có quyền đúng hoặc external secrets operator quản lý; giới hạn quyền đọc Secret, quyền `exec`, tạo pod và access node. Kiểm tra etcd encryption at rest theo platform.

Spring Cloud Vault tích hợp qua Config Data API:

```yaml
spring:
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.internal.example"
```

Đây chỉ là skeleton. Cần starter/BOM Spring Cloud phù hợp với Spring Boot, Vault backend paths, CA trust và authentication. **Không** bỏ root token vào YAML rồi gọi là secrets management. Dùng Kubernetes auth, cloud IAM hoặc phương thức workload identity được vận hành đúng; cấp `read` cho đúng đường dẫn cần dùng, không cấp rộng `list/write/delete/admin`.

Nếu Vault cấp dynamic DB credentials có lease, cần thiết kế renew/revoke và thay connections khi gần expiry. Khi Vault unavailable, quyết định rõ app fail-closed, dùng cache đã được cho phép hoặc degraded mode có kiểm soát; không fallback vào password hard-coded.

## 10. Mật khẩu DB, LDAP, SMTP và broker

### 10.1. Database service account và connection pool

```yaml
spring:
  datasource:
    url: "${DB_JDBC_URL}"
    username: "${DB_USERNAME}"
    password: "${DB_PASSWORD}"
    hikari:
      maximum-pool-size: 10
      connection-timeout: 5000
```

Mỗi service cần DB principal với quyền tối thiểu. Service chỉ đọc không cần quyền DDL, tạo user hoặc quản trị server. Bảo vệ TLS/trust certificate, network egress và dữ liệu trong connection URL; không log `jdbc:...user=...password=...`.

**Rotation khó hơn đổi một property**:

1. Cấp v2: user mới, password mới hoặc dynamic DB lease theo khả năng database.
2. Cập nhật consumers và tạo kết nối mới với v2.
3. Theo dõi pool active/idle và lỗi authentication khi kết nối mới.
4. Chờ các instance đã rollout và job định kỳ đã chuyển.
5. Thu hồi v1; nếu compromise, cân nhắc terminate session/connection cũ.
6. Xóa bản sao secret cũ trong CI, backup theo policy, temporary files và caches.

Một DB có thể **không hỗ trợ hai password đồng thời** cho cùng principal. Không hứa zero-downtime overlap trong trường hợp backend không cho phép; có thể cần hai principals hoặc cutover có bảo trì. Thay password không luôn đóng các connections đã mở.

### 10.2. LDAP bind credentials

Bind DN/password cho directory lookup cần read-only role, search base hẹp và LDAPS/StartTLS với certificate verification. Tách **mật khẩu người dùng đang login** khỏi **bind secret của service**. Khi rotate, xem xét directory replicas, replication delay và mọi ứng dụng dùng bind account; một shared bind account toàn công ty tạo blast radius lớn.

### 10.3. Redis, Kafka, SMTP và webhook

- Redis ACL user riêng, hạn chế commands/key prefixes và mạng.
- Kafka SASL credentials với topic ACL riêng; không log `sasl.jaas.config`.
- SMTP credential có rate limit/scope gửi thư, không dùng tài khoản admin chung.
- Webhook HMAC secret để verify signature trên raw body, timestamp và replay window; tách khỏi API authentication key.
- Không nhúng secret vào URI có userinfo/URL query vì dễ lộ trong access logs, metrics, HTTP redirects và diagnostics.

## 11. OAuth2 client secret và Spring Security ClientRegistration

Client ID thường chỉ định danh ứng dụng; client secret chứng minh danh tính của **confidential client** ở token endpoint. Secret **không phải** access token, refresh token hoặc session cookie. **Không đóng gói client secret vào SPA JavaScript hoặc mobile app**: một public client không thể giữ một shared secret an toàn trước người dùng/attacker.

Spring Security `ClientRegistration` giữ `clientId`, `clientSecret`, `clientAuthenticationMethod`, `authorizationGrantType` và provider URLs. Spring Boot hỗ trợ ví dụ:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner:
            provider: partner
            client-id: "${PARTNER_OAUTH_CLIENT_ID}"
            client-secret: "${PARTNER_OAUTH_CLIENT_SECRET}"
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope:
              - inventory.read
        provider:
          partner:
            token-uri: "${PARTNER_OAUTH_TOKEN_URI}"
```

Đây là đoạn configuration **không đủ để tự tạo một client chạy được**: cần OAuth2 Client dependency, phương thức lấy token qua `OAuth2AuthorizedClientManager` hoặc integration tương ứng, IdP thật và TLS trust. Không đặt client secret trong browser.

### 11.1. Những phương pháp xác thực client

- `client_secret_basic`: server gửi client ID/secret qua HTTP Basic tới **token endpoint** trên HTTPS.
- `client_secret_post`: secret trong POST body khi provider hỗ trợ, phải bảo vệ logging.
- `private_key_jwt`: client ký assertion bằng private key; authorization server verify với public key đã đăng ký.
- mTLS: client dùng certificate/private key đã đăng ký với IdP.
- Workload identity/federation: một số nền tảng cho phép tránh long-lived client secret.

**`private_key_jwt` của OAuth client không phải chữ ký access token do authorization server cấp.** Hai đối tượng, audience, keys, key owners và flows khác nhau. Chuyển cơ chế client auth phải được IdP hỗ trợ và triển khai tương thích, không chỉ đổi một dòng YAML.

### 11.2. Rotation client secret

Nếu IdP cho **hai secrets active**, cấp v2, cập nhật secret store, rollout clients, xác minh token exchange, quan sát traffic và revoke v1. Nếu IdP chỉ cho **một secret**, cần cutover đồng bộ, client registration mới hoặc maintenance window.

Lỗi `invalid_client` có thể do secret hết hạn, client authentication method không khớp hoặc credentials sai; không tự retry vô hạn. Đổi client secret **không tự thu hồi access token đã phát**. Khi lộ client secret, xem xét revoke tokens/refresh tokens và giới hạn TTL theo khả năng IdP.

## 12. JWT signing keys: private signer và public verification

```text
Authorization Server / issuer
    |
    | private RSA/EC signing key trong KMS/HSM
    | ký JWT, header kid=v2, alg=RS256/ES256
    v
Signed JWT  ----------------------> Resource Server
                                        |
                                        | Lấy public JWK từ issuer tin cậy
                                        | Chọn public key theo kid
                                        | Kiểm tra signature và allowed alg
                                        | Kiểm tra iss/aud/exp/nbf/scopes
                                        v
                                   Authorization
```

Một Spring Security Resource Server dùng JWT bất đối xứng **không cần private signing key**; nó dùng public JWK/JWKS đáng tin. Public key có thể publish qua HTTPS, nhưng không chấp nhận một JWKS URL tùy tiện từ `jku`/`x5u` do attacker cung cấp trong JWT header.

Cấu hình resource server **minh họa**:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://idp.example.com/realms/inventory"
          jwk-set-uri: "https://idp.example.com/realms/inventory/protocol/openid-connect/certs"
```

Cần `spring-boot-starter-oauth2-resource-server`, TLS trust và JWT validator cho audience/claims theo API. Khi khai báo trực tiếp `jwk-set-uri` cùng `issuer-uri`, resource server có thể khởi động không cần discovery endpoint phản hồi ngay và vẫn kiểm tra `iss`. URI JWKS là theo IdP, không có một path chuẩn cho mọi provider.

**Không đặt private key vào resource server chỉ để verify.** Không publish JWK chứa RSA private exponent, EC private scalar hoặc symmetric `k` trong JWKS public.

### 12.1. Khóa đối xứng HS256 khác RSA/EC

HS256 là HMAC: server nào biết secret để verify cũng có khả năng ký một MAC hợp lệ. Nếu secret bị sao chép tới nhiều microservices, một service bị chiếm có thể giả mạo JWT. Với nhiều verifiers, ưu tiên thiết kế asymmetric signature để resource servers chỉ có public key.

Không tin thuật toán do JWT header tự chọn; cấu hình allowed algorithms, issuer/audience, token type và hạn dùng rõ. Không chấp nhận `alg=none` hoặc algorithm-confusion fallback.

### 12.2. Key rotation bằng kid và JWKS overlap

```text
T0: issuer ký bằng private v1, public JWKS có v1.
T1: tạo private v2 trong KMS/HSM, public JWKS có v1 + v2.
T2: xác nhận resource servers đã lấy public v2.
T3: issuer chuyển sang ký JWT mới với kid=v2.
T4: tiếp tục chấp nhận token v1 hợp lệ trong overlap.
T5: sau max token TTL + clock skew + JWKS cache margin,
    bỏ public v1, revoke/destroy private v1 theo policy.
```

**Nếu private v1 bị lộ:** không chờ token hết hạn một cách máy móc. Phải xử lý khẩn cấp: dừng tin cậy v1, thu hồi sessions/tokens nếu khả thi, thông báo client đăng nhập lại và đánh giá breach. `kid` chỉ là định danh chọn key, không phải trust proof.

Spring Security `NimbusJwtEncoder` có thể ký JWT với `JWKSource`, nhưng một KMS/HSM non-exportable key có thể cần signer integration/issuer service riêng. Không đưa private PEM nguyên văn vào application.yml hoặc log để “cho tiện”.

### 12.3. Signing key không thay encryption key

JWT signature chỉ bảo vệ authenticity/integrity, **không làm payload bí mật**. Encryption key dùng để giải mã data; khi rotate cần giữ khả năng decrypt ciphertext v1 hoặc re-encrypt dữ liệu trước khi thu hồi key cũ. Không xóa encryption v1 khi vẫn còn dữ liệu phụ thuộc nó. Không dùng cùng bytes cho signing, encryption, TLS và webhook MAC.

## 13. Java 17 độc lập: mô phỏng key rotation không lộ khóa

Đoạn code dùng Java 17 JDK, sinh hai khóa ngẫu nhiên 256-bit tại runtime, ký một payload mẫu bằng HMAC-SHA256 và kiểm tra khi v1/v2 cùng active rồi sau khi revoke v1. **Đây không phải JWT**; mục tiêu là hiểu trust registry/version/cutover. Chương trình không in raw key.

Lưu file `KeyRotationDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class KeyRotationDemo {

    record Signature(String kid, byte[] value) {}

    static byte[] hmac(byte[] key, byte[] payload)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(payload);
    }

    static boolean verify(
            Map<String, byte[]> active,
            Signature signature,
            byte[] payload) throws GeneralSecurityException {
        byte[] key = active.get(signature.kid());
        return key != null && MessageDigest.isEqual(
            hmac(key, payload), signature.value());
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        SecureRandom rng = new SecureRandom();
        byte[] v1 = new byte[32];
        byte[] v2 = new byte[32];
        rng.nextBytes(v1);
        rng.nextBytes(v2);

        byte[] data = "example-event"
            .getBytes(StandardCharsets.UTF_8);

        Map<String, byte[]> trusted = new HashMap<>();
        trusted.put("v1", v1);
        trusted.put("v2", v2);

        Signature oldSig = new Signature("v1", hmac(v1, data));
        Signature newSig = new Signature("v2", hmac(v2, data));

        System.out.println("v1 during overlap: "
            + verify(trusted, oldSig, data));
        System.out.println("v2 during overlap: "
            + verify(trusted, newSig, data));

        trusted.remove("v1");

        System.out.println("v1 after revoke: "
            + verify(trusted, oldSig, data));
        System.out.println("v2 after revoke: "
            + verify(trusted, newSig, data));

        Arrays.fill(v1, (byte) 0);
        Arrays.fill(v2, (byte) 0);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 KeyRotationDemo.java
java KeyRotationDemo
```

Stdout chính xác dù key bytes sinh ngẫu nhiên:

```text
v1 during overlap: true
v2 during overlap: true
v1 after revoke: false
v2 after revoke: true
```

**Giải thích:** trong overlap, verifier chấp nhận cả v1 và v2; sau revoke, v1 bị từ chối. Trong hệ JWT ký bất đối xứng, issuer giữ **private keys** và verifier nhận **public keys**, không dùng chung mảng secret như ví dụ HMAC. `Arrays.fill` chỉ xóa hai arrays mà code sở hữu; không bảo đảm mọi bản copy trong JVM/native crypto provider đã bị xóa.

## 14. Spring Boot 3.5.16 và Java 17: lấy secret từ môi trường

Một project nhỏ chứng minh password **không nằm trong source**, startup **fail nếu thiếu password bắt buộc**, và HTTP response không tiết lộ bí mật. Nó dùng HTTP Basic cho **localhost lab**, không phải giải pháp IAM production. Bên ngoài localhost, HTTP Basic phải dùng TLS đúng; credential Basic chỉ được encode base64, không mã hóa.

### 14.1. Cấu trúc project

```text
secret-injection-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/secret/SecretInjectionApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/demo/secret/SecretInjectionApplicationTests.java
```

### 14.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>secret-injection-demo</artifactId>
    <version>1.0.0</version>
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
```

### 14.3. application.yml

```yaml
server:
  port: 8080

app:
  demo:
    operator: "${DEMO_OPERATOR:operator}"
    password: "${DEMO_OPERATOR_PASSWORD}"
```

Không có default password yếu. Đối với variant mounted files, có thể dùng configtree thay vì env, nhưng phải loại bỏ/điều chỉnh placeholder chưa được cấp và test đúng property precedence. Không trộn hai đường inject mà không biết nguồn nào được chọn.

### 14.4. SecretInjectionApplication.java

```java
package demo.secret;

import java.security.Principal;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SecretInjectionApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecretInjectionApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${app.demo.operator}") String operator,
            @Value("${app.demo.password}") String password) {
        if (password == null || password.length() < 20) {
            throw new IllegalStateException(
                "Required demo operator secret is missing or short");
        }

        UserDetails operatorUser = User.withUsername(operator)
            .password(encoder.encode(password))
            .roles("OPERATOR")
            .build();
        return new InMemoryUserDetailsManager(operatorUser);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()
                .requestMatchers("/private/**").hasRole("OPERATOR")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .build();
    }

    @GetMapping("/health")
    Map<String, String> health() {
        return Map.of("status", "up");
    }

    @GetMapping("/private/me")
    Map<String, String> me(Principal principal) {
        return Map.of("principal", principal.getName());
    }
}
```

**Thiết kế có chủ đích:**

- Giá trị password được inject từ external property; không in ra logs/JSON.
- Bean từ chối startup nếu password thiếu hoặc quá ngắn theo policy **demo**. Đó không phải quy tắc cho mọi password user trong NIST.
- Password demo được BCrypt hash khi tạo `UserDetails` để kiểm tra credential, không lưu plaintext trong user store.
- `/private/**` vẫn yêu cầu `ROLE_OPERATOR`; lấy được secret không nên tự cấp quyền nghiệp vụ cho mọi path.
- Stateless Basic authentication sẽ kiểm tra credentials mỗi request; không dùng Basic ngoài TLS trong môi trường thật.
- Mã không có endpoint mutation. Nếu bổ sung POST từ browser với Basic credentials, vẫn phải đánh giá CSRF vì browser có thể tự gửi cached credentials.
- Bean được tạo lúc startup. **Rotation password trong secret manager không tự đổi BCrypt verifier đang dùng**; phải refresh/recreate hoặc rollout.
- `String` secret có thể nằm trong JVM heap; ứng dụng không thể đảm bảo zeroization tuyệt đối. Với secrets quan trọng, ưu tiên managed credentials/KMS.

### 14.5. Chạy local

```bash
# Bash/Linux/macOS; chỉ dùng secret ngẫu nhiên dành cho bài lab.
export DEMO_OPERATOR='operator'
export DEMO_OPERATOR_PASSWORD="$(openssl rand -hex 24)"
mvn spring-boot:run
```

Nếu dùng PowerShell, khai báo biến môi trường qua `$env:DEMO_OPERATOR` và `$env:DEMO_OPERATOR_PASSWORD` theo syntax tương ứng. Đừng copy một secret production vào terminal lab.

Ở terminal khác:

```bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/private/me
curl -i --user operator http://localhost:8080/private/me
```

Câu lệnh cuối hỏi password tương tác; đừng truyền raw password trong command-line argument vì process listing/shell history có thể giữ lại. Kỳ vọng `/health` trả 200 với `{"status":"up"}`, anonymous `/private/me` trả 401, correct Basic credentials trả 200 với `{"principal":"operator"}`. Sai password trả 401. Nếu không có env secret lúc startup, ứng dụng fail thay vì bật anonymous access.

## 15. MockMvc: test fail-closed và không leak

Tạo `src/test/java/demo/secret/SecretInjectionApplicationTests.java`:

```java
package demo.secret;

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
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "app.demo.operator=operator",
    // Chuỗi synthetic chỉ phục vụ test, không phải production secret.
    "app.demo.password=synthetic-test-only-credential-123456"
})
@AutoConfigureMockMvc
class SecretInjectionApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicHealthIsAvailable() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("up"));
    }

    @Test
    void anonymousCannotReadProtectedResource() throws Exception {
        mvc.perform(get("/private/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongCredentialIsRejected() throws Exception {
        mvc.perform(get("/private/me")
                .with(httpBasic("operator", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void correctCredentialReturnsOnlyIdentity() throws Exception {
        mvc.perform(get("/private/me")
                .with(httpBasic(
                    "operator",
                    "synthetic-test-only-credential-123456")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal").value("operator"))
            .andExpect(jsonPath("$.password").doesNotExist());
    }
}
```

Chạy `mvn test`. Dự kiến **4 test pass** nếu dependency và môi trường phù hợp; đây là dự đoán trên mã, không phải kết quả chạy Maven thực tế. Test fixture dùng giá trị **giả**, không có bí mật production trong source.

Bổ sung test riêng cho startup **thiếu property**, deployment RBAC không cho đọc secret của workload khác, Vault/token endpoint downtime, rotation v1/v2, log redaction và JWKS cache. MockMvc **không chứng minh** Kubernetes Secret ACL hoặc KMS policy đã an toàn.

## 16. Rotation và downtime: không có một cách cho mọi secret

### 16.1. Quy trình tổng quát

```text
Inventory dependencies, owner, TTL và rollback constraints
   |
Create/provision v2
   |
Deploy v2 to consumers (secret manager, configs, pods)
   |
Test new DB connections / OAuth token exchange / JWT validation
   |
Overlap v1 and v2 if supported; monitor old-version use
   |
Revoke v1, terminate stale connections if required
   |
Audit, clean backups/caches, close change
```

**Đừng revoke v1 trước khi biết chính xác consumers đã chuyển v2**, trừ trường hợp lộ secret đòi hỏi containment khẩn cấp và chấp nhận tác động dịch vụ.

| Bí mật | Đặc thù khi rotate |
| --- | --- |
| DB password | Có thể cần user thứ hai/dual password; Hikari pool còn connections cũ |
| LDAP bind password | Replication, account policy, apps chia sẻ bind account |
| OAuth client secret | Provider có cho overlap nhiều secrets active không? Access tokens cũ có thể vẫn valid |
| JWT signing key | Publish public v2 trước; signer đổi kid; giữ public v1 đến khi JWT v1 hết hạn |
| JWT HS256 secret | Mọi verifier giữ shared secret; cần phân phối đủ v2 trước lúc signer chuyển |
| Encryption key | Cần decrypt dữ liệu cũ và re-encrypt trước khi phá v1 |
| TLS certificate/private key | Trust chain, SAN, expiry, OCSP/CRL/certificate policy |
| Webhook HMAC | Key version, signed raw body và replay window |
| Session signing key | Cookie/session tokens cũ có thể bị invalidated ngay nếu xóa key |

### 16.2. Xác minh readiness trước revoke

- Mọi pods và batch jobs đã nạp v2.
- Fresh DB connections mới dùng credentials v2, không chỉ connections cũ đang tồn tại.
- `invalid_client`, DB auth failures, JWKS kid misses, 401/5xx không tăng bất thường.
- JWT issuer phát token với `kid=v2`, tất cả resource servers verify được token v2.
- JWKS public v1 tiếp tục có trong overlap khi token v1 còn hợp lệ.
- Kịch bản rollback không tự đưa app trở lại v1 đã revoke.
- Version/age/access metadata được báo, **không log plaintext hoặc sensitive fingerprint**.

## 17. Khi bí mật bị lộ: incident response

**Revoke/rotate ở nguồn cấp phát là bước quyết định.** Xóa một dòng khỏi Git không làm secret bị lộ vô hiệu.

Quy trình:

1. Xác định loại secret, version, quyền và nguồn lộ (Git, log, CI, dump, Vault, device).
2. Contain attacker: revoke exposed credential/key, hạn chế network/IAM, cấp secret mới nếu phù hợp.
3. Xác định blast radius: dữ liệu, token/session, service accounts, downstream resources và third parties.
4. Cập nhật consumers, đo lỗi xác thực, vô hiệu stale pools/caches/sessions theo threat model.
5. Nếu private signing key lộ, xem xét **ngừng tin mọi token ký bằng key cũ**, logout/re-authentication và emergency JWKS update.
6. Nếu DB password lộ, đánh giá existing connections và các truy vấn đã xảy ra, không chỉ đổi mật khẩu.
7. Quét Git history, forks, artifacts, backups, central logs và CI; xử lý bản sao và quyền theo retention policy.
8. Bảo toàn evidence có kiểm soát, audit các lần đọc secret, incident timeline và hành vi đáng ngờ.
9. Bổ sung scanning, least privilege, shorter TTL, workload identity và runbook.
10. Thông báo security owners/khách hàng theo policy và nghĩa vụ pháp lý phù hợp.

**Không in raw secret vào ticket hoặc chat để điều tra**. Dùng reference/version, môi trường, thời điểm và correlation ID đã bảo vệ.

## 18. Observability, Actuator và CI/CD

Không log:

- `System.getenv()` toàn bộ hoặc `@ConfigurationProperties.toString()` chứa secret;
- `Authorization`, `Cookie`, `X-API-Key`, OAuth refresh/access tokens, CSRF token, private PEM;
- SQL/JDBC connection URL có password, Kafka JAAS config, SMTP credentials;
- raw request/response ở token endpoint, redirect query chứa code/token;
- session IDs, heap dumps và config files qua Actuator publicly exposed.

Actuator có cơ chế sanitization cho một số endpoints, nhưng **không phải lý do để mở `/actuator/env`, `/configprops`, `/heapdump`, `/logfile` công khai**. Bảo vệ authentication/authorization, egress, retention, support access và xác nhận bằng test thực tế.

Log an toàn ưu tiên **metadata**:

```text
event=SECRET_ROTATION_COMPLETED
secret_ref=prod/inventory/oauth-client
version=v2
consumer=inventory-api
result=SUCCESS
correlation_id=rotate-4382
```

Đây là log mẫu, không phải output Spring mặc định. Một fingerprint của password yếu có thể cho phép offline guessing; nếu có version ID từ manager, ưu tiên version ID.

Với CI/CD:

- Secret scanning ở pre-commit/PR/pipeline và khi audit Git history.
- Không đóng secret vào container image hoặc build artifacts.
- Inject secret vào job dùng nó, least-privileged CI identity, hạn ngắn.
- Không truyền password trong command-line args, URL hay shell trace.
- Không bật HTTP wire logging chứa headers/token ở production.
- Dùng workload identity/OIDC federation khi có thể thay static CI token.
- Kiểm tra rollback và emergency rotation runbook.

## 19. Ma trận lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| App không resolve `DB_PASSWORD` | Không inject secret hoặc property precedence sai | Kiểm tra secret reference/identity, fail-closed; không default yếu |
| DB login lỗi sau deploy | Version app/DB lệch | Kiểm tra pool và fresh connections, rotate theo thứ tự |
| DB vẫn hoạt động với password đã revoke | Old connections chưa bị đóng | Recycle/terminate khi yêu cầu |
| OAuth token endpoint trả `invalid_client` | Secret sai/hết hạn hoặc auth method không khớp | Đối chiếu IdP registration và v2 |
| Client secret đổi nhưng access token cũ vẫn hoạt động | Token expiry/revocation khác client secret | Quản lý token lifecycle riêng |
| JWT v2 bị từ chối | JWKS cache thiếu `kid=v2`, issuer/aud/alg sai | Publish public v2 trước, kiểm tra validation |
| JWT v1 bị từ chối quá sớm | Gỡ public v1 trước token TTL | Overlap nếu không bị compromise |
| Key xuất hiện trong public JWKS | Lỡ publish private JWK hoặc symmetric key | Xử lý incident, revoke/rotate ngay |
| Kubernetes Secret đổi mà app không nhận | Bean/pool chỉ đọc lúc startup | Rolling restart/refresh đúng resource |
| Actuator lộ connection password | Endpoint/config sanitize sai | Restrict Actuator, revoke key và audit |
| Password lộ qua build logs | Shell echo/debug hoặc tool in env | Redact, restrict pipeline, revoke |
| Local fallback secret chạy ở prod | Dùng default giá trị yếu | Bỏ fallback, startup validation |
| Một service đọc được secret của nhiều team | IAM/RBAC quá rộng | Workload-specific policy |
| Signing key bị lộ ở resource server | Đưa private key tới mọi verifier | Dùng asymmetric public verification, rotate |
| Key v1 đã revoke nhưng rollback cần v1 | Release cũ chứa credential cũ | Build rollback compatible với v2 |
| Token URI từ request không tin cậy | Credential exfiltration/SSRF | Pin endpoints và TLS trust |

**Trình tự chẩn đoán:** secret source → quyền workload → version/expiry → TLS endpoint → app reload/pool → Spring Security client/JWT validation → redacted logs → incident policy.

## 20. Checklist triển khai thực tế

- [ ] Inventory đầy đủ mọi DB/LDAP/broker/OAuth/JWT/TLS/API/webhook secret, có owner và rotation runbook.
- [ ] Không dùng chung một secret cho nhiều môi trường hoặc nhiều mục đích.
- [ ] Không có production secret trong Git, CI artifact, image, logs, heap dump hoặc Actuator response.
- [ ] Secrets được CSPRNG/KMS/IdP cấp đúng cơ chế, entropy và key usage.
- [ ] Workload IAM chỉ đọc secrets của chính nó; không có Vault root token trong app.
- [ ] TLS verification và outbound endpoint allowlist đúng.
- [ ] Spring Boot property source được kiểm soát; thiếu secret → fail-closed.
- [ ] Mounted file/config tree không bị hiểu nhầm thành hot reload tự động.
- [ ] Kết nối DB/LDAP được rotate với connection pool và job consumers.
- [ ] OAuth client secret khác access token, chỉ ở confidential server-side.
- [ ] Issuer JWT giữ private signing key; resource server chỉ có public JWKS.
- [ ] JWT rotation có kid, public-key overlap, TTL, cache margin, emergency revoke.
- [ ] Encryption key rotation có kế hoạch re-encrypt/decrypt legacy data.
- [ ] Incident response đã thử tình huống secret lộ, kể cả Git history/backups.
- [ ] Có telemetry theo secret version nhưng không tiết lộ secret.
- [ ] Test được false/expired/missing secret, ACL, key rotation, rollback và KMS/Vault failures.

## 21. Câu hỏi tự kiểm tra

1. Vì sao **client ID** không phải **client secret**?
2. Tại sao password người dùng lưu hash còn service password có thể cần recoverable secret store?
3. Kubernetes Secret base64 có phải encryption không?
4. Thay secret file trong Kubernetes có tự reload `@Value` bean không?
5. `private_key_jwt` dùng cho client authentication khác JWT access token signature thế nào?
6. Resource server có cần private RSA signing key để verify JWT không?
7. Vì sao cần publish public v2 trước lúc signer ký JWT với v2?
8. `kid` có đủ để tin JWT từ một issuer chưa được xác thực không?
9. Khi nào có thể xóa public v1 sau rotation bình thường?
10. Khi private v1 bị lộ, có nên chờ hết JWT TTL hay khẩn cấp revoke?
11. Vì sao đổi DB password không luôn đóng connections cũ?
12. OAuth client secret đổi có thu hồi access tokens đã cấp không?
13. Có nên đặt client secret trong SPA/mobile bundle không?
14. Vì sao không dùng chung một HMAC key giữa mọi microservices?
15. Đổi encryption key có cần xử lý ciphertext cũ không?
16. Nếu thiếu secret bắt buộc lúc startup thì hành vi an toàn là gì?
17. Có nên log hash/fingerprint mọi password để debug không?
18. Vì sao xóa secret khỏi commit mới chưa giải quyết lộ secret?
19. Điều gì khiến workload identity tốt hơn long-lived static secret ở một số môi trường?
20. MockMvc test xanh có chứng minh Vault RBAC hoặc Kubernetes volume ACL an toàn không?

## 22. Tài liệu chính thức

- Spring Boot 3.5 – Externalized Configuration và Configuration Trees: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot – OAuth2 Client Configuration: https://docs.spring.io/spring-boot/reference/security/oauth2.html
- Spring Security 6.5 – OAuth2 ClientRegistration: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/core.html
- Spring Security – OAuth2 Resource Server JWT/JWKS: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security – NimbusJwtEncoder API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusJwtEncoder.html
- Spring Security – Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Cloud Vault – Quick Start: https://docs.spring.io/spring-cloud-vault/reference/quickstart.html
- Spring Cloud Vault – ConfigData API: https://docs.spring.io/spring-cloud-vault/reference/config-data.html
- OWASP – Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP – Key Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html
- OWASP – Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- NIST SP 800-63B-4 – Authentication and Passwords: https://pages.nist.gov/800-63-4/sp800-63b.html
- RFC 7517 – JSON Web Key (JWK): https://www.rfc-editor.org/rfc/rfc7517
- RFC 7518 – JSON Web Algorithms (JWA): https://www.rfc-editor.org/rfc/rfc7518
- RFC 8725 – JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
