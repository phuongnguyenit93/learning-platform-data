# Token trong secret manager

Một backend cần gọi Invoice API bằng OAuth 2.0 access token. Để lấy token, backend phải chứng minh danh tính với Authorization Server (AS), chẳng hạn bằng **client secret** hoặc một khóa riêng. Có nên lưu access token, refresh token, client secret và khóa ký JWT chung vào một secret manager rồi đọc lại ở mỗi API request?

**Không nên mặc định làm vậy.** Secret manager là công cụ hữu ích để **lưu, phân quyền, cấp phát và kiểm toán bí mật**, nhưng mỗi loại token có **vòng đời, mức độ nhạy cảm và đặc tính truy cập khác nhau**. Một access token chỉ sống vài phút thường thích hợp để cache ngắn hạn trong bộ nhớ của service; một client secret ít đổi có thể phù hợp với secret manager; một refresh token theo từng phiên người dùng có thể cần kho dữ liệu giao dịch mã hóa và cơ chế rotation nguyên tử; còn khóa riêng dùng ký JWT có thể nên **ở trong KMS/HSM** để ứng dụng gọi chức năng ký mà không xuất khóa ra ngoài.

Trong chương **Token storage** của module **Security Token Security Fundamentals**, bài học này tập trung vào câu hỏi: **bí mật nào nên nằm trong secret manager, ai được đọc, đọc khi nào, bảo vệ vòng đời ra sao và giới hạn của giải pháp này là gì?** Kiến thức liên quan trực tiếp đến JWT, opaque token, access token, refresh token, OAuth 2.0/OIDC, issuer/audience/scope, thu hồi và phòng chống đánh cắp hoặc phát lại token.

## 1. Secret manager làm gì và không làm gì?

**Secret manager** là dịch vụ/quy trình quản lý bí mật của ứng dụng, thường cung cấp một số khả năng như:

- **Lưu trữ bảo vệ:** mã hóa dữ liệu khi lưu, bảo vệ khi truyền, kiểm soát truy cập theo danh tính.
- **Phân quyền:** chỉ workload/nhân sự được phép mới có quyền đọc hoặc cập nhật một secret cụ thể.
- **Versioning:** có thể lưu các phiên bản secret và hỗ trợ chuyển đổi khi rotation.
- **Audit:** ghi nhận ai/ứng dụng nào truy cập bí mật, ở đâu, khi nào, bằng quyền gì.
- **Lifecycle:** hỗ trợ tạo, cập nhật, vô hiệu hóa, xóa hoặc phối hợp rotation tùy loại secret và sản phẩm.
- **Tích hợp workload identity:** service có thể xác thực với secret manager bằng danh tính máy/chạy ứng dụng thay cho một mật khẩu lâu dài.

Đây là **các khả năng có thể có**, không phải lời hứa mọi sản phẩm secret manager đều tự động thực hiện tất cả. Cần kiểm năng lực cụ thể và ràng buộc vận hành của giải pháp đã chọn.

### Secret manager không phải các thành phần này

| Thành phần | Nhiệm vụ chính | Khác gì với secret manager? |
|---|---|---|
| **Authorization Server (AS)** | Cấp, kiểm grant và có thể thu hồi OAuth token | Secret manager **không tự quyết định** client được cấp `scope`/`aud` nào |
| **Resource Server (RS)** | Kiểm token và quyền ở từng API | Việc token nằm trong vault không khiến API tự cho phép truy cập |
| **KMS/HSM** | Quản lý khóa và thao tác mật mã như ký/giải mã | Có thể giữ khóa **không xuất được**; secret manager chủ yếu trả giá trị secret nếu được phép |
| **Token cache** | Giữ access token ngắn hạn để không xin lại liên tục | Thường là bộ nhớ process/cache có TTL; không cần bền vững như secret manager |
| **Session/refresh-grant database** | Lưu phiên, grant, trạng thái rotation, token family | Cần giao dịch/compare-and-set/reuse detection; secret versioning không mặc nhiên thay thế |
| **Introspection endpoint** | AS cho RS biết token còn active và ngữ cảnh phù hợp hay không | Kho bí mật **không thay** kiểm trạng thái token |
| **Configuration store** | Quản lý cấu hình không nhạy cảm | Audience identifier hay endpoint public không nhất thiết là bí mật |

**Quy tắc:** Secret manager bảo vệ **dữ liệu bí mật khi lưu và khi cấp cho workload được phép**, không tự bảo vệ việc ứng dụng sử dụng bí mật đúng giao thức sau khi đã nhận được nó.

## 2. Phân loại dữ liệu: lưu gì ở đâu?

Một sai lầm thường gặp là gọi mọi chuỗi liên quan OAuth là “token” và cho chúng cùng một chính sách lưu trữ.

| Dữ liệu | Thời hạn & đối tượng sử dụng | Vị trí lưu thường hợp lý | Cảnh báo |
|---|---|---|---|
| **OAuth client secret** của confidential client | Thường dài hơn access token; backend dùng xác thực với AS | **Secret manager**, workload được quyền đọc | Cần rotation và không dùng trong SPA/mobile public client như bí mật đáng tin |
| **Khóa riêng cho `private_key_jwt` hoặc mTLS client** | Credential của service để xác thực với AS | **KMS/HSM hoặc keystore được quản trị**, tùy thiết kế | Ưu tiên không xuất khóa nếu có cơ chế ký phù hợp; quản trị chứng chỉ/khóa riêng |
| **Khóa riêng ký JWT của AS** | Khóa mật mã có tác động tới mọi token do issuer phát hành | **KMS/HSM hoặc key store bảo vệ chặt** | Không đặt trong cấu hình client/RS; khóa công khai JWKS là câu chuyện khác |
| **Access token JWT/opaque ngắn hạn của service** | Thường phút; dùng gọi RS | **Cache bộ nhớ có TTL**, xin mới qua AS khi cần | Không ghi log, không truy xuất secret manager cho mỗi API call |
| **Refresh token dài hơn của một backend cố định** | Bí mật cấp quyền xin access token mới | **Secret manager** có thể phù hợp nếu vòng đời và concurrency đơn giản | Phải xử lý rotation, token bị đánh cắp và cập nhật phiên bản an toàn |
| **Refresh token riêng cho hàng nghìn người dùng/BFF** | Gắn từng grant/phiên, đổi thường xuyên | **Session/grant store mã hóa** với KMS, chính sách phân quyền và giao dịch | Secret manager theo từng user không mặc nhiên tối ưu cho throughput/atomic rotation |
| **Digest refresh token phía AS** | AS tra cứu và phát hiện reuse | **Database trạng thái grant/family**, lưu hash/HMAC phù hợp | AS thường không cần lưu plaintext opaque refresh token |
| **DPoP private key** | Khóa chứng minh người gửi token | Keystore/secure element phù hợp với client | Không cho workload khác đọc hoặc dùng key tùy tiện |
| **ID token OIDC** | Thông tin xác thực trả cho client | Session/auth context theo kiến trúc | Không lưu như credential chung để gọi API nghiệp vụ |
| **JWKS public keys / `kid` / `aud` config** | Metadata công khai hoặc không bí mật | Cache/config được quản trị và kiểm tin cậy | Public key không trở thành secret chỉ vì nằm trong JWT flow |

Đây là **gợi ý kiến trúc theo đặc tính dữ liệu**, không phải yêu cầu của OAuth rằng các loại secret phải nằm ở một công nghệ cố định. Ví dụ, một hệ thống chỉ có vài service với refresh token được luân phiên không thường xuyên có thể lưu trong vault, nhưng cần thiết kế cập nhật nhất quán; hệ thống có hàng triệu phiên người dùng có thể dùng DB mã hóa và khóa do KMS quản trị.

## 3. Threat model: secret manager giải quyết rủi ro nào?

Hãy theo dõi vòng đời một client secret:

~~~mermaid
flowchart LR
    I["Workload identity"] --> M["Secret manager / KMS"]
    M -->|"Read theo IAM và TLS"| A["Backend trong runtime"]
    A -->|"Client authentication"| AS["Authorization Server"]
    AS -->|"Access token"| A
    A -->|"Bearer access token"| RS["Resource Server"]
~~~

Secret manager có thể giảm rủi ro **secret nằm rải rác trong source code, file cấu hình, CI/CD variables và bản sao trên nhiều host**. Nhưng từ lúc secret được trả về cho backend, bí mật có thể xuất hiện trong **RAM, request đến AS, error dump, log, APM, proxy hoặc thư viện HTTP**. Nếu process bị chiếm quyền với đúng danh tính workload, attacker có thể đọc secret hoặc **gọi trực tiếp secret manager bằng quyền của process**.

### Mô hình rủi ro theo lớp

| Tấn công/sự cố | Secret manager có giúp? | Điều kiện bảo vệ thêm |
|---|---|---|
| Secret vô tình được commit vào Git | Giúp chuyển secret ra khỏi repo | Scan secret, vô hiệu hóa credential đã lộ, bảo vệ CI |
| Developer đọc được mọi secret production | IAM/RBAC có thể ngăn | Tách quyền deploy, vận hành, debug và break-glass |
| Ổ đĩa/backup của kho secret bị truy cập trái phép | Encryption at rest có thể giảm rủi ro | Quản trị khóa, quyền decrypt, backup/retention |
| Hacker có quyền chạy mã trong workload được phép | **Không đủ** | Giới hạn workload IAM, cô lập runtime, egress control, giám sát |
| JWT bearer access token bị lấy từ RAM | **Không chặn** sau khi token đã được cấp | TTL ngắn, scope/audience hẹp, DPoP/mTLS khi phù hợp, RS authorization |
| Refresh token bị lộ và bị đổi tại AS | Kho bảo vệ giúp giảm khả năng lộ, nhưng không tự chặn replay | Rotation/reuse detection, client binding, revoke grant |
| Service vô tình ghi Authorization header ra log | **Không tự sửa log** | Redaction ở SDK, gateway, tracer, APM, exception |
| Token hết hạn hoặc `aud` sai | **Không liên quan** tới cất giữ secret | AS/RS xác minh theo OAuth profile |
| Tài khoản quản trị secret manager bị chiếm | Có thể ảnh hưởng rất rộng | MFA, JIT access, approval, audit, phân vùng môi trường |

**Bảo vệ tốt khi lưu không đồng nghĩa an toàn sau khi sử dụng.** Với bearer token, ai có chuỗi token hợp lệ có thể xuất trình nó tại resource server được phép mà không cần truy cập lại secret manager.

## 4. Secret zero: ứng dụng xác thực với secret manager bằng gì?

Nếu ứng dụng phải có một **mật khẩu dài hạn để mở secret manager**, ta lại cần tìm chỗ cất mật khẩu đó — đây là bài toán **secret zero**.

### Ưu tiên workload identity

Thay vì chép một `VAULT_ROOT_TOKEN` hoặc cloud access key vào environment variable, có thể cho workload chứng minh danh tính bằng cơ chế được môi trường chạy hỗ trợ, ví dụ:

- **Managed workload identity** gắn với ứng dụng chạy trên cloud hoặc máy ảo.
- **OIDC workload identity federation** trong pipeline/deployment, có ràng buộc issuer, audience, subject và điều kiện tin cậy.
- **Service identity** được xác thực bằng mTLS/certificate, cơ chế SPIFFE/SPIRE hoặc hệ thống tương đương khi đã thiết kế đúng.
- **Kubernetes service account token có audience ràng buộc**, thời hạn và cách kiểm được secret manager tin cậy, thay vì token mặc định có quyền quá rộng.

Luồng truy cập lý tưởng:

~~~mermaid
sequenceDiagram
    participant App as Billing Worker
    participant ID as Workload Identity Provider
    participant Vault as Secret Manager
    participant AS as OAuth Authorization Server
    participant API as Invoice API
    App->>ID: Lấy bằng chứng danh tính workload ngắn hạn
    ID-->>App: Identity assertion phù hợp audience
    App->>Vault: Authenticate / read secret được phép
    Vault->>Vault: Kiểm danh tính, IAM policy, audit
    Vault-->>App: Client credential được phép
    App->>AS: Client authentication + grant/scope/resource
    AS-->>App: Access token ngắn hạn
    App->>API: Gọi API bằng token
    API->>API: Kiểm issuer, aud, exp, scope và quyền dữ liệu
~~~

**Giới hạn quyền ở cả hai chặng:** workload identity cho phép đọc **một secret cụ thể**, còn AS quyết định client được cấp **scope/audience nào**. Đọc được client secret không làm AS bỏ kiểm grant; access token đúng chữ ký không làm RS bỏ kiểm tenant/object permission.

### Những điều cần cấm trong bootstrap

1. Không nhúng **root/admin vault token** vào image, init script, Helm values hoặc file được commit.
2. Không để service production đọc secret của mọi environment/tenant.
3. Không tin một `client_id` hoặc service-account name do HTTP caller tự gửi làm workload identity.
4. Không ghi identity assertion, access token để gọi vault hoặc credential AS vào log.
5. Không đặt quyền `list/read/update/delete` chung khi workload chỉ cần **read**; tách writer/rotation actor.

Credential truy cập secret manager cũng có **TTL, refresh, revoke và audit riêng**. Việc dùng workload identity không có nghĩa service được quyền tự nâng vai trò.

## 5. Thiết kế namespace, IAM và môi trường

Hãy giả định hệ thống có môi trường `dev`, `staging` và `prod`; mỗi môi trường có Billing Worker và Payment Worker. Một tổ chức nhiều tenant còn có dữ liệu theo khách hàng.

~~~text
prod/
  billing-worker/
    oauth-client-credential
    trusted-issuer-config  (không nhất thiết là secret)
  payment-worker/
    oauth-client-credential

staging/
  billing-worker/
    oauth-client-credential
~~~

Tên chỉ minh họa cách phân tách. Một chính sách tối thiểu:

| Principal | Resource | Quyền cần cấp |
|---|---|---|
| `prod/billing-worker` | `prod/billing-worker/oauth-client-credential` | **Read** |
| `prod/payment-worker` | `prod/payment-worker/oauth-client-credential` | **Read** |
| `prod/billing-worker` | Secret của Payment Worker | **Deny** |
| `staging/billing-worker` | Secret production | **Deny** |
| Rotation controller được ủy quyền | Secret cụ thể cần rotate | **Write/version** theo quy trình, không mặc nhiên quyền toàn vault |
| Security auditor | Access/event metadata được phân quyền | **Read audit**, không cần xem plaintext secret |

Tách **danh tính thực thi**, **danh tính deploy**, **nhân viên đọc log** và **nhân viên quản trị secret**. Một pipeline CI có quyền deploy không nhất thiết được phép tải mọi plaintext secret production. Có thể cần break-glass, dual control và alert khi truy cập ngoài giờ, nhưng không cấp những quyền đó cho ứng dụng thông thường.

### Multi-tenant không chỉ là đặt tên khác nhau

Với hàng nghìn tenant, không nên dựa vào việc ứng dụng tự nối chuỗi `tenantId` từ URL rồi đọc một secret bất kỳ:

~~~text
UNSAFE:
  secretName = "prod/" + request.query.tenantId + "/token"
~~~

Đầu vào HTTP không chứng minh quyền tenant. Phải kiểm danh tính caller, quyền gắn tenant và ánh xạ tenant → secret đã được kiểm soát **trước** khi chọn secret; IAM của workload còn phải hạn chế phạm vi được đọc. Nếu một service cần đọc secret nhiều tenant, phải thiết kế broker/policy kiểm quyền ở cấp tài nguyên chứ không cấp quyền wildcard rồi tin frontend chọn đúng tenant.

## 6. Mã hóa khi lưu, khi truyền và trong bộ nhớ

### Encryption at rest không phải toàn bộ bí mật

Secret manager thường mã hóa secret khi lưu, có thể dùng KMS và envelope encryption. Ý tưởng:

~~~text
plaintext secret
    -> encrypt với data encryption key (DEK)
    -> ciphertext lưu trong secret manager
    -> DEK được bảo vệ bởi key-encryption key (KEK)/KMS
~~~

Khả năng kỹ thuật cụ thể tùy sản phẩm. Bảo mật phải xét cả người được quyền gọi **decrypt/read**; nếu principal bị chiếm đã có quyền đó, việc ciphertext được mã hóa trên ổ đĩa không ngăn được việc lấy plaintext qua API hợp pháp.

### Encryption in transit

Kênh application → secret manager và application → AS phải dùng **TLS được xác minh đúng**; tránh bỏ kiểm chứng chứng chỉ để xử lý lỗi môi trường. Các hop nội bộ/proxy cũng thuộc threat model. Dữ liệu secret không nên xuất hiện trong URL/query, nơi dễ bị lưu bởi access log, lịch sử hoặc tracing.

### Plaintext trong runtime

Sau khi lấy secret, ứng dụng phải dùng nó để xác thực hoặc ký. Khi đó plaintext/key material có thể xuất hiện trong RAM:

- Không xuất secret ra `stdout`/`stderr`, exception message, heap dump được chia sẻ hoặc hệ thống APM.
- Giới hạn thời gian giữ trong RAM và khả năng truy cập giữa các module.
- Ưu tiên thư viện nhận mảng byte/char hoặc **signing handle** thay vì tự chuyển bí mật qua nhiều immutable string.
- Nếu dùng `byte[]` hoặc `char[]`, có thể xóa mảng khi xong; nhưng **không bảo đảm** mọi bản sao trong HTTP library/JVM đã biến mất.
- Không đưa secret vào environment variable chỉ vì nó “không ở trong Git”: process inspection, child process, diagnostic dump hoặc cấu hình container có thể làm lộ tùy môi trường.

**Không nên tuyên bố “secret manager bảo đảm token không bao giờ bị lộ”**. Nó giảm vùng lộ khi cất giữ và kiểm soát truy cập, trong khi bảo vệ lúc sử dụng là trách nhiệm của ứng dụng và hạ tầng chạy.

## 7. Token access ngắn hạn: cache ở runtime thay vì đọc vault mọi request

Với một confidential client gọi API bằng `client_credentials`:

~~~text
Billing Worker --(workload identity)--> Secret Manager
      lấy OAuth client credential khi cần
Billing Worker --(token request)------> Authorization Server
      nhận access token expires_in=900
Billing Worker --(bearer)------------> Invoice API
      tái sử dụng access token tới gần hết hạn
~~~

**Vì sao không lưu access token vào secret manager cho từng request?**

1. Access token có TTL ngắn, thường chỉ cần dùng trong **một runtime hoặc một tập workload**.
2. Mỗi lần đọc secret manager có latency, quota, phí vận hành và dependency tới một dịch vụ trung tâm.
3. Token bị lộ vẫn có thể được dùng tại RS nếu là bearer; vault không làm token trở thành sender-constrained.
4. Phân phối một access token cho quá nhiều workload làm **tăng số nơi token có thể bị sao chép**.
5. Việc cache trong RAM với hạn ngắn có thể đơn giản hơn và giảm tải AS/vault.

**Cần tránh cực đoan ngược lại:** Nếu nhiều replica liên tục xin token mới, AS có thể bị `token issuance storm`. Có thể dùng cache/single-flight **trong từng process**, jitter khi refresh, giới hạn request theo client và cơ chế chia sẻ có kiểm soát khi thực sự cần. Chia sẻ access token giữa tất cả replica chỉ nên làm sau khi đánh giá bề mặt rò rỉ, quyền workload và kiến trúc sender binding.

### Nguyên tắc cache

| Điều kiện | Chính sách gợi ý |
|---|---|
| **Thời hạn** | Cache không vượt `expires_in` hoặc `exp` thực tế; refresh trước hạn bằng khoảng đệm và jitter |
| **Khóa cache** | Phân biệt issuer, client, resource/audience, scope và loại token; không dùng một token cho mọi API |
| **Lỗi AS** | Nếu token cache còn hợp lệ và policy cho phép có thể tiếp tục dùng; không dùng token đã hết hạn |
| **Lỗi secret manager** | Không tự fallback sang secret hardcode; dùng credential/cache đang hợp lệ trong giới hạn định sẵn hoặc fail safely |
| **Đồng thời** | Single-flight/token acquisition lock để nhiều request không đồng loạt xin token |
| **Đổi secret** | Refresh credential cache theo version/TTL và xử lý phiên bản cũ trong quá trình rotation |
| **Log** | Ghi correlation ID, expiry/rate và mã lỗi; không ghi access token |

### Tại resource server

Invoice API không quan tâm client cất credential trong vault hay memory. Nó cần xác minh **chính access token nhận được**:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "billing-worker",
  "aud": "invoice-api",
  "scope": "invoice:read",
  "iat": 1800000000,
  "exp": 1800000900
}
~~~

JWT trên chỉ là payload minh họa, **không phải token được ký**. API cần xác minh chữ ký/khóa, issuer, audience, thời gian, đúng access-token profile, scope và quyền nghiệp vụ. Với **opaque access token**, API có thể dùng introspection của AS. Token lấy từ secret manager **không được tự tin tưởng hơn** token lấy qua kênh phát hành hợp lệ khác.

## 8. Java: một TokenProvider dùng secret manager an toàn

Ví dụ sau dùng **Java 17 và interface giả định** để biểu diễn cách tích hợp. Đây là **mã minh họa về kiến trúc**, không phải SDK của một cloud/vendor. Token provider xin access token theo `client_credentials`, cache ngắn hạn và chỉ đọc secret khi cần cấp token mới.

~~~java
interface SecretReader {
    // Implementation dùng workload identity trong SDK/sidecar.
    // Không nhận arbitrary credentials từ HTTP request để chọn quyền đọc.
    SecretValue read(String allowedSecretName);
}

interface SecretValue extends AutoCloseable {
    char[] copyAsChars();
    String version();
    @Override void close();
}

interface OAuthClient {
    IssuedToken clientCredentials(
        String clientId, char[] clientSecret, String resource,
        String scope);
}

record IssuedToken(String accessToken, long expiresInSeconds,
                   String tokenType) {}

record CacheEntry(String accessToken, Instant expiresAt) {}

final class ServiceAccessTokenProvider {
    private static final Duration EXPIRY_SKEW = Duration.ofSeconds(45);
    private final SecretReader secretReader;
    private final OAuthClient oauth;
    private final Clock clock;
    private CacheEntry cache;

    ServiceAccessTokenProvider(SecretReader secrets, OAuthClient oauth,
                               Clock clock) {
        this.secretReader = secrets;
        this.oauth = oauth;
        this.clock = clock;
    }

    // synchronized = single-flight trong MỘT process, không qua nhiều pod.
    synchronized String tokenForInvoiceApi() {
        Instant now = clock.instant();
        if (cache != null &&
            now.plus(EXPIRY_SKEW).isBefore(cache.expiresAt())) {
            return cache.accessToken();
        }

        try (SecretValue value =
                 secretReader.read("prod/billing/oauth-client-secret")) {
            char[] secret = value.copyAsChars();
            try {
                IssuedToken issued = oauth.clientCredentials(
                    "billing-worker", secret,
                    "https://api.example.test/invoices",
                    "invoice:read");
                if (!"Bearer".equalsIgnoreCase(issued.tokenType()) ||
                    issued.expiresInSeconds() <= 60 ||
                    issued.accessToken() == null ||
                    issued.accessToken().isBlank()) {
                    throw new IllegalStateException(
                        "Invalid token endpoint response");
                }
                cache = new CacheEntry(
                    issued.accessToken(),
                    now.plusSeconds(issued.expiresInSeconds()));
                return cache.accessToken();
            } finally {
                Arrays.fill(secret, '\0');
            }
        }
    }
}
~~~

**Các giới hạn của ví dụ cần hiểu đúng:**

- `OAuthClient` phải thực hiện client authentication và token endpoint HTTPS đúng chuẩn, kiểm AS tin cậy, xử lý OAuth error, retry/backoff và `resource` **chỉ khi AS hỗ trợ**. `resource` là Resource Indicators theo RFC 8707, không phải tên claim tự khai.
- Đơn vị `expiresInSeconds` là giây; lấy thời điểm nhận response làm mốc cache chỉ là **xấp xỉ**, production nên tính thêm latency, clock skew và hạn sử dụng thực tế đã được AS cam kết.
- `synchronized` chỉ đồng bộ trong **một JVM**. Nhiều replica có cache riêng; rate limit và jitter cần được cân nhắc để không flood AS.
- `char[]` được xóa giúp giảm thời gian tồn tại một bản sao credential, nhưng SDK/HTTP client vẫn có thể tạo bản sao khác. `String accessToken` trong JVM không dễ xóa trước GC; phải giảm khả năng dump/lộ và giữ TTL thích hợp.
- Token response không tự chứng minh quyền đối tượng; **Invoice API** vẫn phải kiểm `aud` và `scope`, cùng quyền dữ liệu. Client provider không thể dùng `expires_in` để kết luận server đã chấp nhận access token.
- Tên secret cố định nằm trong code chỉ là **identifier**, không phải credential. Trong triển khai thật, nên cấu hình danh sách tên được phép và có review/IAM policy.
- Nếu AS yêu cầu `private_key_jwt` hoặc mTLS, nên dùng cơ chế ký/keystore phù hợp thay vì kéo private key vào `char[]` theo cách này.

## 9. Refresh token: vì sao secret manager có thể chưa đủ?

Giả sử BFF giữ refresh token để gọi API thay mặt người dùng. Sau mỗi lần refresh thành công, AS sử dụng **refresh token rotation**:

~~~text
R0 --refresh--> access token A1 + refresh token R1
R0 = USED
R1 = ACTIVE
~~~

Nếu BFF lưu R0 trong secret manager nhưng **không cập nhật nguyên tử** sang R1, nhiều instance có thể đọc cùng R0 và gọi token endpoint đồng thời:

~~~mermaid
sequenceDiagram
    participant B1 as BFF replica 1
    participant B2 as BFF replica 2
    participant V as Secret Manager
    participant AS as Authorization Server
    B1->>V: Read refresh token R0
    B2->>V: Read refresh token R0
    B1->>AS: Refresh R0
    AS-->>B1: A1 + R1, R0 đã USED
    B2->>AS: Refresh R0
    AS-->>B2: invalid_grant / reuse detected
    Note over V,AS: AS có thể revoke cả family do reuse
~~~

**Versioning secret không mặc nhiên là compare-and-set đúng nghĩa**. Có sản phẩm quản lý version/label nhưng không hỗ trợ thao tác **đọc version N → cập nhật N+1 nếu N vẫn hiện hành** như một giao dịch ứng dụng. Và kể cả khi vault cập nhật atomically, **AS đã tiêu thụ R0 trong một hệ thống khác**, nên hai bước không nằm trong cùng một transaction phân tán.

### Những yêu cầu tối thiểu khi lưu refresh token phía client

1. **Mỗi phiên/grant có owner rõ:** Client ID, user/session, token family/grant, scope và quyền liên quan phải được liên kết từ nguồn tin cậy.
2. **Mã hóa secret tại nơi lưu:** Có phân quyền tách biệt giữa người dùng/tenant và workload; không lưu plaintext trong log hoặc backup tùy tiện.
3. **Single-flight refresh:** Chỉ một worker/instance được gọi AS với refresh token hiện hành cho một phiên, sử dụng lock/lease/CAS đáng tin.
4. **Cập nhật token mới cẩn thận:** Sau khi AS trả R1, ứng dụng phải lưu R1 một cách nhất quán, tránh mất response/ghi lỗi.
5. **Không replay R0 vô hạn:** `invalid_grant` phải dẫn đến xử lý phiên không còn hợp lệ hoặc flow xác thực lại theo chính sách.
6. **Revocation và incident handling:** Logout, reuse, thay quyền hoặc nghi bị đánh cắp phải dừng refresh và có thể revoke family tại AS.
7. **Retention:** Xóa giá trị cũ/backup theo chính sách, đồng thời không phá cơ chế reuse detection phía AS.

Với số lượng phiên người dùng lớn, giải pháp phổ biến về **đặc tính dữ liệu** là **session/refresh-grant DB có transaction**, mã hóa giá trị refresh token bằng key do KMS quản lý, và cache/lock theo từng phiên. Secret manager có thể quản lý **khóa mã hóa**, còn DB lưu ciphertext có khóa tra cứu và version. Lựa chọn này cần đánh giá năng lực đội ngũ, quy mô và yêu cầu pháp lý/vận hành; không phải cứ là DB mã hóa thì an toàn hơn vault.

### Khác biệt giữa phía client và Authorization Server

| Thành phần | Cần làm gì với refresh token? | Cách lưu có thể phù hợp |
|---|---|---|
| **Client/BFF** | Cần lấy **giá trị token thực** để gửi tới `/token` lần tới | Secret được mã hóa có thể giải mã khi cần, với concurrency control |
| **Authorization Server** | Cần tra token đã phát hành, xác định trạng thái ACTIVE/USED/REVOKED, lineage | Token opaque entropy cao có thể lưu **hash/HMAC digest** và metadata family trong DB; không cần plaintext |

Phía AS cần **phát hiện reuse và revoke token hậu duệ**, không chỉ cất giữ bí mật. Chuyển tất cả refresh token sang secret manager không thay thế mô hình grant/family của AS.

## 10. Quản lý rotation và versioning của secret đúng cách

**Secret rotation** (đổi client secret/khóa) và **refresh token rotation** (đổi token sau mỗi refresh) có cơ chế khác nhau.

### Client secret rotation

Một trình tự khả thi khi AS hỗ trợ **hai credential chồng lấn**:

1. Tạo **client secret mới** hoặc credential mới ở AS theo quyền được phép.
2. Lưu secret mới thành một version trong secret manager; quyền đọc vẫn chỉ cho đúng workload.
3. Deploy/refresh client để dùng version mới; kiểm request token endpoint có thành công không.
4. Giám sát lỗi `invalid_client` và khả năng các replica đã chuyển sang secret mới.
5. Vô hiệu secret cũ ở AS khi các client đã chuyển; giới hạn khoảng chồng lấn.
6. Loại bỏ quyền đọc/version cũ theo retention và kiểm lại log/audit.

**Nếu AS không hỗ trợ chồng lấn**, cần một kế hoạch cutover có phối hợp/downtime hoặc chiến lược khác. Không giả định mọi OAuth AS cho nhiều client secret đồng thời; không đổi secret trong vault trước rồi mong AS tự nhận bản mới.

### Signing key rotation

Đối với AS ký JWT bằng khóa bất đối xứng, nên xét:

- **Khóa riêng** được quản lý trong HSM/KMS hoặc hệ thống key storage thích hợp; ưu tiên ký qua API mà không export key.
- **Khóa công khai/JWKS** cần được công bố cho RS và có thể được cache theo policy; đây **không phải secret**.
- Thời điểm đổi `kid`/khóa ký phải tính tới **các access token còn hạn** và caching JWKS tại resource server.
- Không xóa khóa xác minh cũ quá sớm khiến token hợp lệ bị từ chối ngoài kế hoạch, trừ trường hợp **khóa đã bị xâm phạm** cần xử lý khẩn cấp.
- Đổi khóa ký **không tự thu hồi refresh token** hay thay thế quản trị grant.

### Rotation secret không đồng nghĩa revoke token đã phát hành

Nếu client secret bị lộ và được thay:

- Secret cũ nên bị vô hiệu ở AS theo chính sách.
- **Access token đã phát hành** trước đó có thể vẫn hợp lệ cho tới `exp` hoặc đến khi RS kiểm revocation.
- **Refresh token** có thể cần bị revoke, rebind hoặc áp dụng chính sách mới để không tiếp tục cấp access token cho phiên bị nghi xâm phạm.

Tương tự, xóa version chứa bearer access token trong secret manager **không khiến resource server đang xác minh token đó tự động từ chối**. Phải xử lý trạng thái token ở AS/RS.

## 11. Khi secret manager không khả dụng: cache, fallback và circuit breaker

Một backend có thể phụ thuộc vào cả secret manager và AS. Nếu bí mật chỉ tồn tại trong vault còn vault bị gián đoạn, việc xin token mới có thể thất bại, dù cache access token hiện hành vẫn còn hạn.

| Tình huống | Hành vi gợi ý | Điều không nên làm |
|---|---|---|
| Vault outage nhưng có access token hợp lệ trong cache | Có thể dùng tiếp **đến hạn được phép**, theo policy | Kéo dài `exp` hoặc bỏ kiểm token ở RS |
| Vault outage, access token đã hết hạn | Fail safely hoặc retry có backoff/circuit breaker | Dùng token hết hạn hoặc hardcode emergency secret trong code |
| AS outage nhưng token còn hạn | Tiếp tục request với token hiện hành nếu RS chấp nhận | Flood AS bằng refresh request trên mỗi API call |
| AS outage khi refresh token rotation đang xử lý | Bảo toàn trạng thái phiên, xử lý timeout/retry theo policy | Giả định request chưa được AS xử lý và replay R0 liên tục |
| Secret version bị revoke | Ngừng dùng credential đã bị vô hiệu, invalidate cache cần thiết | Giữ secret cũ trong memory vô hạn |
| KMS/keystore không ký được | Chặn phát hành token/credential liên quan theo chính sách, cảnh báo | Tắt xác minh signature hoặc chuyển sang khóa mặc định không an toàn |

**Fail-open** ở tầng “được đọc secret” hoặc “cho phép sử dụng token chưa xác minh” thường biến outage thành lỗ hổng. Khác với một quota phụ trợ, **xác thực và phân quyền cốt lõi không được bỏ qua** chỉ để duy trì availability.

### Cân bằng cache với rotation và revoke

Cache credential trong process giúp giảm latency nhưng làm chậm việc nhận ra secret mới hoặc secret bị thu hồi. Nên có:

- TTL cache **hữu hạn** và cơ chế invalidate theo sự kiện khi khả thi.
- Giám sát `secret_version`/thời điểm refresh cache mà **không log secret**.
- Kế hoạch khi version cũ bị revoke đột ngột: xoá cache và thử đọc version mới qua danh tính hợp lệ, không lặp vô hạn.
- Quota và jitter khi nhiều replica cùng lấy secret hoặc cùng xin access token sau một sự cố.
- Phân biệt lỗi **không được phép đọc secret (403)** với **lỗi mạng (timeout/5xx)** để không retry vô hạn một chính sách IAM từ chối.

## 12. Quan sát, audit và phân quyền cho vận hành

Một hệ thống có secret manager nên ghi nhận **truy cập secret** chứ không ghi **giá trị secret**:

| Sự kiện | Có thể ghi | Không nên ghi |
|---|---|---|
| Workload đọc secret | Workload ID, tên/ID secret, version, thời gian, kết quả, correlation ID | Plaintext client secret, refresh token, private key |
| Rotation credential | Actor có quyền, version cũ/mới, trạng thái cutover, rollback plan | Chuỗi secret mới trong ticket/chat/log |
| Cấp access token | Client ID đã xác minh, grant type, resource, scope dạng metadata có kiểm soát, expiry, request ID | Toàn bộ access token/refresh token |
| Secret access bị từ chối | Principal, policy reason ở log nội bộ, resource, tần suất | Secret plaintext, dữ liệu tenant khác |
| Refresh reuse | Grant/family ID nội bộ, loại sự kiện, correlation ID | Refresh token đã bị phát lại |
| Incident revoke | Secret/token/grant scope, actor, lý do, thời điểm và hệ thống bị ảnh hưởng | Khóa riêng hoặc token trong báo cáo sự cố |

Lưu ý **metadata cũng có thể nhạy cảm**: tên secret có thể tiết lộ sản phẩm/tenant; subject ID có thể là dữ liệu cá nhân. Hạn chế truy cập audit log, đặt retention hợp lý và tránh metric labels có số lượng cực lớn theo từng session/token.

### Kiểm tra đặc quyền tối thiểu có đang được thực thi?

1. Một service chỉ cần **đọc** credential của mình có bị từ chối khi thử **update/delete** không?
2. Một service staging có bị từ chối đọc secret production không?
3. Một tenant/workload có đọc được token hoặc secret của tenant khác qua thay ID/path không?
4. Một nhân viên chỉ có quyền xem log có đọc được plaintext secret hoặc backup không?
5. Khi workload identity hết hạn, bị revoke hoặc đổi audience, secret manager có từ chối không?
6. Khi secret version cũ bị vô hiệu, hệ thống có ngừng sử dụng sau TTL/invalidation hợp lý không?

**Secret access log** hữu ích để phát hiện workload đột nhiên đọc nhiều secret không liên quan. Tuy nhiên, audit phải được bảo vệ để tránh chính log trở thành điểm lộ thông tin.

## 13. Sự cố token/secret bị lộ: cần revoke ở đúng nơi

Giả sử một nhân viên vô tình đưa **client secret** của Billing Worker lên ticket công khai. Cách xử lý không phải chỉ “xóa ticket và secret khỏi vault”.

### Quy trình ứng phó theo lớp

1. **Ngăn tiếp tục lộ:** gỡ khỏi nơi công khai, chặn logging, kiểm tra image/config/CI; giả định secret đã có thể bị sao chép.
2. **Xác định loại bí mật:** OAuth client secret, refresh token, access token hay private key? Ai được quyền dùng và tác động có thể đến đâu?
3. **Vô hiệu tại hệ thống phát hành/xác thực:** đổi/revoke client secret tại AS, revoke refresh grant/token family nếu cần, vô hiệu khóa bị xâm phạm theo quy trình khóa.
4. **Cập nhật secret manager:** tạo version mới, ràng buộc workload IAM, xóa/vô hiệu version cũ đúng trình tự để không phá dịch vụ một cách vô ý.
5. **Xử lý token đã phát hành:** xem xét TTL, audience/scope, introspection/denylist hoặc chính sách thu hồi tại RS. Chỉ xóa secret khỏi vault **không đủ**.
6. **Rà soát audit:** ai đã đọc secret, các request cấp token nào bất thường, có access token nào được dùng trái phép, dữ liệu tài nguyên nào bị truy cập.
7. **Phục hồi và phòng ngừa:** secrets scanning, least privilege, không log, rate limit issuance, kiểm tenant, rehearsal rotation.

Một **khóa ký JWT bị lộ** có thể cho phép kẻ tấn công tạo token giả mà RS tin cậy nếu khóa vẫn được chấp nhận; mức độ nghiêm trọng khác với một access token của một client bị lộ. Do đó phạm vi revoke và phản ứng cần **phân loại theo bí mật và trust boundary**.

### Ai có quyền “xem secret” khi xử lý sự cố?

Không nên tự động yêu cầu đội hỗ trợ chụp màn hình hoặc gửi plaintext secret qua chat/ticket. Khi cần điều tra, ưu tiên **secret ID, version, audit event, fingerprint hoặc timestamp**, cấp quyền tạm thời có phê duyệt nếu thực sự phải xem dữ liệu, và thu hồi quyền sau đó.

## 14. Kiểm thử: đừng chỉ xác nhận “đọc được secret”

| Kịch bản | Thiết lập | Kết quả kỳ vọng |
|---|---|---|
| **Workload hợp lệ** | Billing Worker dùng identity đúng, đọc credential của mình | Thành công qua TLS, chỉ secret được phép |
| **Workload khác quyền** | Payment Worker xin secret Billing | **Deny**, có audit, không trả giá trị |
| **Sai môi trường** | Staging identity xin prod secret | **Deny** |
| **Dữ liệu tenant không hợp lệ** | Client đổi `tenant_id` trong request để chọn secret | Không đọc secret tenant khác |
| **Identity giả/expired** | Bằng chứng workload sai issuer/audience/expiry | Secret manager từ chối authentication |
| **Token access ngắn hạn** | Nhiều API request khi token còn hạn | Dùng cache theo policy, không đọc vault/request token liên tục |
| **Access token sai audience** | Token `aud=report-api` gọi Invoice API | RS từ chối, bất kể secret từng nằm trong vault |
| **Access token hết hạn** | Vault/AS không khả dụng nhưng token cũ hết `exp` | Không gọi API bằng token hết hạn |
| **Vault bị gián đoạn** | Timeout/5xx khi đọc secret | Backoff/circuit breaker; không fallback secret hardcode |
| **Client secret rotation** | AS và vault có version cũ/mới theo cutover | Client chuyển đúng, không tạo outage ngoài kế hoạch; old credential được revoke |
| **Đổi secret ở vault nhưng quên AS** | Version vault mới chưa được AS đăng ký | Không giả định thay đổi ở vault làm AS chấp nhận |
| **Xóa secret cũ** | Access token đã phát hành vẫn đang sống | RS tuân thủ token expiry/revocation riêng, không coi vault deletion là revoke |
| **Refresh rotation đồng thời** | Hai BFF replica cùng đọc R0 | Không tạo hai nhánh refresh trái chính sách; single-flight/CAS/AS reuse detection |
| **Response R1 bị mất** | AS đã dùng R0 nhưng BFF không lưu R1 | Không replay R0 vô hạn; recovery/reauth phù hợp |
| **Secret dump/log leak** | Kiểm access log, tracer, crash report được phép | Không có token/secret plaintext |
| **KMS ký JWT không xuất khóa** | AS gọi sign bằng handle | Ứng dụng không cần quyền export private key |
| **Lỗi IAM** | Quyền read bị thu hồi | Workload không tiếp tục đọc bằng identity đã revoke |
| **Secret manager bị chiếm danh tính đọc** | Kiểm phạm vi quyền của workload | Chỉ có thể đọc tập secret tối thiểu, có cảnh báo/anomaly detection |
| **DPoP/mTLS binding** | Attacker lấy token string nhưng không có khóa | API/AS từ chối theo profile sender-constrained |
| **Cross-region outage** | Một region secret manager lỗi | Fallback/khả dụng theo policy mà không bỏ xác thực |

### Bài tập tình huống

Hệ thống có ba thành phần:

~~~text
Billing Worker:
  OAuth client_id = billing-worker
  Client secret   = prod/billing/oauth-client-secret
  Access token    = aud=invoice-api, scope=invoice:read, TTL=15 phút

Invoice API:
  Chấp nhận token aud=invoice-api

Auth Server:
  Cấp access token bằng client_credentials
~~~

**Câu 1. Nên lưu access token 15 phút làm secret manager version mới sau mỗi lần cấp không?**

**Thường không cần.** Billing Worker nên cache access token theo TTL/expiry trong runtime, xin mới khi gần hết hạn. Cấp hàng loạt version access token làm tăng trạng thái bí mật, độ trễ và nguy cơ lộ mà không tự tăng bảo mật.

**Câu 2. Nếu Billing Worker cần client secret để xin token, lấy bí mật bằng cách nào?**

Dùng **workload identity đã được xác thực**, IAM read đúng secret, kênh TLS được kiểm và cache credential theo giới hạn phù hợp. Không gắn root vault token vào container để “dễ chạy”.

**Câu 3. Nếu attacker đánh cắp access token hiện hành trong RAM, việc client secret ở vault có cứu được không?**

**Không trực tiếp.** Với bearer access token, attacker vẫn có thể dùng token tại Invoice API trong thời gian hiệu lực và phạm vi được cấp. Cần giới hạn scope/audience/TTL, sender-binding khi phù hợp, rate limit và quyền dữ liệu tại RS.

**Câu 4. Nếu client secret bị lộ, chỉ xóa secret manager version cũ có đủ không?**

**Không.** Phải vô hiệu credential cũ tại **AS**, triển khai credential mới đúng trình tự, xem xét revoke token/grant liên quan và điều tra audit.

**Câu 5. Nếu thay grant của Billing Worker bằng refresh token R0 được rotation, có thể cho nhiều replica tự đọc R0 từ vault rồi cùng refresh không?**

**Không nên.** Cần coordination/single-flight và cập nhật token theo trạng thái. Vault versioning không bảo đảm AS refresh rotation được thực hiện một lần trên toàn hệ thống; race có thể kích hoạt reuse detection và thu hồi family.

**Câu 6. Với hệ thống một triệu phiên người dùng, có bắt buộc đặt từng refresh token trong secret manager không?**

**Không.** Cần một thiết kế lưu trữ có khả năng kiểm soát quyền, mã hóa, giao dịch và xử lý rotation; DB ciphertext có khóa KMS quản trị là một lựa chọn, nhưng phải đánh giá quy mô, retention và threat model. AS cần lưu trạng thái grant/family theo cách phù hợp để chống replay.

## 15. Checklist thiết kế token trong secret manager

1. **Phân loại đúng bí mật:** Access token, refresh token, client secret, private key, ID token hay metadata công khai? Có phân biệt JWT/opaque và bearer/sender-constrained?
2. **Chọn kho theo vòng đời:** Access token ngắn hạn có cần cache RAM; refresh grant động có cần DB giao dịch; private key có nên ở KMS/HSM?
3. **Giải bài toán secret zero:** Workload dùng managed identity/federation thay vì hardcode root vault token?
4. **Least privilege:** IAM read/write tách biệt; service, môi trường và tenant được cô lập; không wildcard không cần thiết?
5. **Bảo vệ khi lưu/truyền:** Encryption at rest, KMS key policy, TLS, backup và log redaction có đúng trust boundary?
6. **Bảo vệ lúc runtime:** Giảm thời gian giữ plaintext, tránh heap/log/crash exposure, cô lập process và egress?
7. **Cache hợp lý:** Token cache gắn issuer/client/audience/scope và expiry, không đọc vault/AS trên mọi request?
8. **Rotation an toàn:** Client secret/key rotation phối hợp AS, có version/cutover, không nhầm với refresh token rotation?
9. **Refresh token dynamic:** Có single-flight, transaction/CAS, reuse detection và kế hoạch lost-response/reauth?
10. **Revoke đúng chỗ:** Xóa secret khỏi vault có đi kèm vô hiệu tại AS/RS khi cần, không giả định vault tự revoke OAuth token?
11. **Không bỏ token validation:** RS vẫn kiểm `iss`, chữ ký/introspection, `aud`, `exp`, scope, token profile và quyền đối tượng?
12. **Availability không đổi lấy bypass:** Outage vault/KMS có backoff, cache hợp lệ, circuit breaker và fail safely?
13. **Audit không lộ secret:** Chỉ log metadata cần thiết; giới hạn người được xem audit và retention?
14. **Thử đường tấn công:** IAM sai môi trường/tenant, workload bị chiếm, access token bị đánh cắp, concurrent refresh, revoked version và logging leak?

**Ghi nhớ:** Secret manager là **một lớp bảo vệ cho việc cất giữ và phân phối bí mật**, không phải nơi mặc định phải chứa **mọi token**. Để lựa chọn đúng, hãy bắt đầu từ **loại token, ai được sử dụng, tuổi thọ, tần suất thay đổi và yêu cầu giao dịch**. Credential dài hạn của backend có thể nằm trong secret manager; khóa ký quan trọng có thể cần KMS/HSM; access token ngắn hạn thường nên được cache với TTL; refresh token theo phiên cần bảo vệ rotation và trạng thái grant. Sau cùng, **OAuth AS phải cấp quyền đúng**, **Resource Server phải xác minh token và phân quyền**, và **xóa secret trong vault không thay thế việc revoke token ở nơi có thẩm quyền**.

### Chuẩn và tài liệu tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** access token, refresh token, client authentication và token endpoint.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** quyền sử dụng bearer token khi có chuỗi token và các rủi ro lưu/truyền.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ OAuth, public client, refresh token rotation và giảm nguy cơ lộ token.
- **RFC 7519 — JSON Web Token (JWT):** claims `iss`, `aud`, `exp` và xác minh JWT.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile JWT access token và các claims OAuth.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm trạng thái và ngữ cảnh token tại Resource Server.
- **RFC 7009 — OAuth 2.0 Token Revocation:** cơ chế vô hiệu token/grant, khác việc xóa bản sao trong secret manager.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** xác định resource dự kiến khi yêu cầu token.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** xác thực client và access token ràng buộc chứng chỉ.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** ràng buộc token với khóa người gửi.
- **OWASP Secrets Management Cheat Sheet:** các nguyên tắc bảo vệ secret, phân quyền, rotation, logging và xử lý vòng đời.
