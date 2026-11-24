# Log issuer, client ID và subject có kiểm soát

> **Chương:** Observability  
> **Module:** SECURITY_TOKEN_SECURITY_FUNDAMENTALS  
> **Bối cảnh:** Quan sát vòng đời token bảo mật và hoạt động OAuth 2.0/OIDC; phân biệt JWT, opaque token, access token, refresh token; kiểm tra claims, scope, audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao log **issuer (iss), client ID và subject (sub)** hữu ích cho điều tra xác thực và phân quyền.
2. Phân biệt dữ liệu được phép ghi log với credential hoặc claim nhạy cảm không được ghi.
3. Thiết kế schema log có cấu trúc, allowlist field, mã hóa định danh và kiểm soát quyền truy cập.
4. Chọn cách ghi issuer/client/subject theo mức độ nhạy cảm, nhu cầu correlation và yêu cầu riêng tư.
5. Tránh đưa subject hoặc client ID vào metric labels gây cardinality cao và rò rỉ dữ liệu.
6. Kiểm thử redaction, pseudonymization, retention, audit trail và khả năng điều tra sự cố mà không lưu raw token.

## 1. Vì sao cần log issuer, client ID và subject?

Trong hệ thống OAuth 2.0/OIDC, một request thường đi qua nhiều thành phần: API gateway, resource server, authorization server, service-to-service client và các hệ thống quan sát. Khi có lỗi 401/403, token bị thu hồi hoặc một client gọi API bất thường, đội vận hành cần biết:

- Token được phát hành bởi **issuer** nào?
- OAuth client nào đang yêu cầu token hoặc gọi resource?
- Chủ thể **subject** nào được token đại diện?
- Request được xác thực thành công hay thất bại?
- Resource server đã chấp nhận audience/scope nào?
- Quyết định authorization được đưa ra ở đâu và theo policy nào?

Các trường **iss**, **client_id** và **sub** có giá trị trong correlation và audit. Nhưng chúng cũng có thể tiết lộ topology identity, tên ứng dụng nội bộ, định danh người dùng hoặc thông tin liên kết tài khoản. Vì vậy, log phải có mục đích rõ ràng, chỉ ghi các trường cần thiết, giới hạn người đọc và có thời hạn lưu phù hợp.

**Nguyên tắc:** Ghi lại *ngữ cảnh xác thực đã được xác minh* ở dạng có kiểm soát; không ghi credential dùng để chứng minh danh tính.

~~~mermaid
flowchart LR
    R["Incoming request"] --> V["Token validation<br/>issuer, signature/introspection,<br/>audience, expiry"]
    V --> C["Build safe auth context<br/>issuer alias, client alias,<br/>subject reference"]
    C --> L["Structured security log"]
    C --> M["Low-cardinality metrics"]
    L --> SIEM["Restricted log platform"]
    M --> MON["Metrics / dashboards"]
~~~

Log, metric và audit event có mục đích khác nhau. Log có thể giữ chi tiết theo request với quyền truy cập hạn chế; metric nên tổng hợp theo nhãn ít giá trị; audit trail ghi các hành động bảo mật quan trọng với tính toàn vẹn và retention riêng.

## 2. Hiểu đúng issuer, client ID và subject

### Issuer (iss)

**Issuer** định danh Authorization Server đã phát hành token. Resource server dùng issuer để chọn cấu hình tin cậy, public key/JWKS hoặc introspection endpoint phù hợp.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.com/realms/workforce"
}
~~~

Có thể log một **issuer alias** đã đăng ký như **workforce-idp** thay vì URI đầy đủ. Alias giúp vận hành nhận diện nguồn token nhưng tránh vô tình đưa URL nội bộ, realm, tenant naming hoặc chi tiết triển khai vào log phổ thông.

Chỉ lấy issuer từ token **sau khi** token được xác minh theo cấu hình issuer được phép. Nếu token có issuer không được tin cậy, không dùng giá trị iss tự khai làm định danh đáng tin; ghi một mã như **untrusted_issuer** và một reason code phù hợp.

### Client ID (client_id)

**Client ID** định danh OAuth client đã đăng ký, ví dụ service, web application hoặc batch worker. Nó thường không phải secret, nhưng vẫn có thể tiết lộ tên ứng dụng, cấu trúc hệ thống, quan hệ giữa service hoặc môi trường.

Nên ánh xạ client ID sang **client alias** được quản lý, ví dụ **orders-service-prod**, **mobile-app-prod** hoặc **partner-17**. Nếu cần giữ raw client ID cho điều tra, chỉ ghi ở audit stream được giới hạn quyền và có retention được phê duyệt.

Không nhầm các khái niệm:

- **client_id** nhận diện OAuth client theo authorization server.
- **sub** nhận diện subject của token theo issuer.
- **azp** trong OpenID Connect có thể biểu diễn authorized party trong một số ID token.
- **act** có thể biểu diễn actor trong một số token profile.
- Workload identity từ mTLS/service mesh là danh tính kết nối, không tự động đồng nhất với OAuth client ID.

Không phải token nào cũng có mọi claim trên. Hãy theo token profile và metadata thực tế của Authorization Server.

### Subject (sub)

**Subject** là định danh chủ thể mà token đại diện. Subject có thể là người dùng, service account hoặc một loại principal khác tùy grant và issuer.

Ví dụ:

~~~json
{
  "sub": "user-92841",
  "client_id": "orders-service"
}
~~~

Subject thường có khả năng liên kết tới tài khoản thật. Vì vậy, ghi raw subject trong mọi application log có thể tạo ra một kho dữ liệu theo dõi hành vi người dùng. Cách mặc định phù hợp hơn là dùng **subject reference đã pseudonymize** cho log vận hành thông thường; chỉ ghi raw subject trong audit có kiểm soát khi có yêu cầu nghiệp vụ/pháp lý rõ ràng.

Subject chỉ được tin sau khi token hoặc introspection response được xác minh. Không lấy subject từ header như X-User-Id, request body hoặc trace baggage do client tự gửi.

## 3. Xác minh trước khi ghi log

Log identity fields từ token trước khi xác thực có thể khiến hệ thống ghi nhận dữ liệu giả do attacker tự tạo. Một request có JWT giả với sub=admin không được tạo log như thể admin đã thực sự gọi API.

### JWT access token

Trước khi dùng claims cho log:

- Xác minh chữ ký bằng key thuộc issuer tin cậy.
- Chỉ cho phép thuật toán đã cấu hình; không để token tự chọn thuật toán ngoài policy.
- Kiểm tra **iss**, **aud**, **exp**, **nbf** nếu có và token profile.
- Phân biệt access token với ID token; không dùng ID token thay access token cho resource API.
- Ánh xạ client_id, sub, tenant và scope theo schema thực tế của issuer.
- Nếu token không hợp lệ, chỉ log reason code và nguồn request ở mức an toàn; không tin claims chưa xác minh.

### Opaque access token

Opaque token không thể tự giải mã để lấy claims. Resource server thường dùng introspection hoặc cơ chế tra cứu được bảo vệ. Chỉ ghi active, subject, client metadata hoặc scope sau khi introspection response được xác minh và gắn với request đang xử lý.

Nếu introspection timeout hoặc lỗi, ghi trạng thái **introspection_unavailable** hoặc mã lỗi tương đương. Không suy ra subject/client từ chuỗi opaque token.

### Client authentication

Khi log hoạt động ở token endpoint, client identity nên lấy từ kết quả xác thực client như HTTP Basic, private_key_jwt, mTLS hoặc cơ chế đã đăng ký. Không ghi client ID được lấy từ body request như một client đã xác thực trước khi credential được kiểm tra.

## 4. Phân loại dữ liệu: ghi gì và không ghi gì?

| Trường | Log vận hành mặc định | Audit hạn chế | Lưu ý |
|---|---|---|---|
| Issuer alias | Có | Có | Alias từ registry tin cậy |
| Raw issuer URI | Chỉ khi cần | Có thể | Có thể lộ realm/topology |
| Client alias | Có | Có | Tên ổn định, không chứa secret |
| Raw client_id | Tùy policy | Có thể | Có thể tiết lộ tên service/partner |
| Raw subject | Thường không | Chỉ khi cần | Có thể là định danh cá nhân |
| Subject reference HMAC | Có thể | Có thể | Pseudonymous, vẫn cần bảo vệ |
| Audience/resource alias | Có | Có | Dùng giá trị đã đăng ký |
| Scope/authority | Có chọn lọc | Có | Chỉ ghi scope cần thiết; tránh dump toàn bộ claims |
| Token type | Có | Có | Ví dụ access_token, opaque/jwt |
| Token expiry bucket | Có thể | Có thể | Tránh ghi claims không cần thiết |
| Token value / Authorization header | **Không** | **Không** | Credential bearer |
| Refresh token | **Không** | **Không** | Credential có thể cấp access token mới |
| Client secret / password | **Không** | **Không** | Bí mật xác thực |
| Private key / key material | **Không** | **Không** | Không ghi ở bất kỳ log nào |
| Toàn bộ JWT payload | **Không** | **Không** | Có thể chứa PII và quyền nhạy cảm |
| Raw cookie/session | **Không** | **Không** | Có thể cho phép chiếm phiên |

Không nên log Authorization header, cookie, refresh token, client assertion, private key, secret hoặc toàn bộ request/response token endpoint. Việc log một JWT đã ký vẫn có thể làm lộ bearer credential; chữ ký không biến token thành dữ liệu công khai.

## 5. Pseudonymization subject để correlation có kiểm soát

Nếu đội vận hành cần biết nhiều request có cùng subject mà không cần biết danh tính thật, có thể dùng **HMAC-SHA-256** với khóa pseudonymization được quản lý riêng.

Ví dụ tạo subject reference:

~~~text
subject_ref = HMAC-SHA-256(
    dedicated_log_key,
    environment + issuer_alias + tenant_id + subject
)
~~~

Các thành phần issuer và tenant giúp tránh va chạm giữa hai subject có cùng chuỗi ID nhưng thuộc issuer/tenant khác nhau. Environment giúp tách dữ liệu staging và production. Có thể thêm purpose/domain separator như **auth-log-subject-v1** để cùng một subject không tạo ra cùng reference trong các mục đích xử lý khác nhau.

### Ví dụ Java

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public final class SubjectPseudonymizer {

    private final SecretKey logKey;
    private final String keyVersion;
    private final String environment;

    public SubjectPseudonymizer(
            SecretKey logKey,
            String keyVersion,
            String environment
    ) {
        this.logKey = logKey;
        this.keyVersion = keyVersion;
        this.environment = environment;
    }

    public String reference(
            String issuerAlias,
            String tenantId,
            String subject
    ) throws GeneralSecurityException {
        String canonical = String.join(
            "\n",
            "auth-log-subject-v1",
            environment,
            issuerAlias,
            tenantId == null ? "" : tenantId,
            subject
        );

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(logKey);

        byte[] digest = mac.doFinal(
            canonical.getBytes(StandardCharsets.UTF_8)
        );

        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
    }

    public String keyVersion() {
        return keyVersion;
    }
}
~~~

Khóa HMAC phải được lấy từ KMS/secret manager với quyền tối thiểu, không hardcode trong source code hoặc lưu chung với log. Tạo đối tượng Mac mới cho mỗi lần gọi vì Mac không được thiết kế để dùng đồng thời từ nhiều thread. Trong production, nên xử lý exception theo kiểu fail closed đối với việc phát hành subject reference, đồng thời tránh fallback sang ghi raw subject.

### Pseudonymization không phải anonymization

HMAC subject reference vẫn có thể được dùng để liên kết hành vi của cùng một chủ thể qua nhiều sự kiện. Người có khóa hoặc quyền truy cập dữ liệu mapping có thể liên hệ reference với danh tính thật. Vì vậy:

- Xem subject reference là dữ liệu pseudonymous cần kiểm soát.
- Không đưa reference vào dashboard công khai hoặc metric labels.
- Giới hạn thời gian lưu và người có quyền tra cứu.
- Có kế hoạch rotation khóa pseudonymization.
- Ghi key version để diễn giải dữ liệu qua các giai đoạn đổi khóa.
- Không dùng cùng một HMAC key cho log, analytics, marketing hoặc các mục đích khác.

Nếu cần correlation ổn định trong một khoảng thời gian, key version có thể được giữ theo retention window. Khi rotate key, reference mới sẽ khác; không nên giữ khóa cũ vô thời hạn chỉ để duy trì khả năng liên kết.

## 6. Thiết kế structured log schema

Log nên là event có cấu trúc thay vì nối toàn bộ claims thành một chuỗi khó kiểm soát.

Ví dụ event an toàn:

~~~json
{
  "event": "oauth_access_token_validation",
  "outcome": "success",
  "reason_code": "validated",
  "issuer_alias": "workforce-idp",
  "client_alias": "orders-service-prod",
  "subject_ref": "hmac:v3:Q2x...",
  "subject_ref_key_version": "v3",
  "tenant_alias": "tenant-a",
  "audience": "orders-api",
  "scope_summary": ["orders.read"],
  "token_format": "jwt",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "service": "orders-api",
  "environment": "production",
  "timestamp": "2026-11-23T10:30:00Z"
}
~~~

Giá trị trong ví dụ là dữ liệu giả. subject_ref không phải token và không thể dùng để gọi API, nhưng vẫn cần được bảo vệ như dữ liệu pseudonymous.

### Schema nên có các nhóm field

| Nhóm | Field gợi ý | Mục đích |
|---|---|---|
| Event | event, timestamp, outcome, reason_code | Hiểu điều gì đã xảy ra |
| Request | trace_id, request_id, route, method | Correlate request |
| Service | service, environment, deployment_version | Xác định thành phần xử lý |
| Issuer | issuer_alias | Nhận diện nguồn token đã xác minh |
| Client | client_alias, grant_type | Nhận diện OAuth client |
| Subject | subject_ref, key_version | Correlation có kiểm soát |
| Authorization | audience, scope_summary, policy_decision | Hiểu quyền được dùng |
| Token metadata | token_format, token_type, expiry_bucket | Điều tra vòng đời token |
| Failure | reason_code, validation_stage | Phân loại lỗi |

Không cần ghi tất cả field cho mọi event. Chỉ ghi trường liên quan tới quyết định và mục đích điều tra. Không serialize đối tượng Jwt, Authentication hoặc request security context trực tiếp vì có thể chứa token value và claims không cần thiết.

## 7. Ví dụ ghi log trong Spring/Java

Giả sử ứng dụng dùng Spring Security Resource Server và đã xác minh JWT trước khi controller/service được gọi. Có thể tạo một audit event từ các trường allowlist.

Ví dụ với SLF4J 2.x fluent logging:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

public class TokenAuditLogger {

    private static final Logger log =
        LoggerFactory.getLogger("SECURITY_AUDIT");

    private final SubjectPseudonymizer pseudonymizer;
    private final IssuerRegistry issuerRegistry;
    private final ClientRegistry clientRegistry;
    private final TenantRegistry tenantRegistry;

    public TokenAuditLogger(
            SubjectPseudonymizer pseudonymizer,
            IssuerRegistry issuerRegistry,
            ClientRegistry clientRegistry,
            TenantRegistry tenantRegistry
    ) {
        this.pseudonymizer = pseudonymizer;
        this.issuerRegistry = issuerRegistry;
        this.clientRegistry = clientRegistry;
        this.tenantRegistry = tenantRegistry;
    }

    public void accepted(
            JwtAuthenticationToken authentication,
            String tenantId,
            String traceId
    ) throws GeneralSecurityException {
        var jwt = authentication.getToken();

        String issuerAlias = issuerRegistry.aliasForVerifiedIssuer(
            jwt.getIssuer()
        );
        String clientAlias = clientRegistry.aliasForVerifiedClientOrUnknown(
            jwt.getClaimAsString("client_id")
        );
        String tenantAlias = tenantRegistry.aliasForVerifiedTenantOrUnknown(
            tenantId
        );
        String subjectRef = pseudonymizer.reference(
            issuerAlias,
            tenantId,
            jwt.getSubject()
        );

        log.atInfo()
            .addKeyValue("event", "oauth_access_token_validation")
            .addKeyValue("outcome", "success")
            .addKeyValue("issuer_alias", issuerAlias)
            .addKeyValue("client_alias", clientAlias)
            .addKeyValue("subject_ref", subjectRef)
            .addKeyValue(
                "subject_ref_key_version",
                pseudonymizer.keyVersion()
            )
            .addKeyValue("tenant_alias", tenantAlias)
            .addKeyValue("trace_id", traceId)
            .addKeyValue("token_format", "jwt")
            .log("Access token validated");
    }
}
~~~

Đây là ví dụ minh họa; cần điều chỉnh theo phiên bản Spring Security và SLF4J. IssuerRegistry, ClientRegistry và TenantRegistry phải ánh xạ từ metadata đã xác minh sang alias được quản lý. Hàm aliasForVerifiedClientOrUnknown xử lý trường hợp token không có claim client_id bằng một giá trị không định danh như unknown/not_applicable; không đoán từ header. tenantId truyền vào pseudonymizer phải là tenant context đã được server xác minh; log chỉ ghi tenant alias.

Nếu ứng dụng dùng opaque token, tạo event từ Authentication/introspection metadata đã xác minh. Không cố gọi getToken() như JWT khi principal thực tế không phải JwtAuthenticationToken.

### Log lỗi validation

Với token sai chữ ký hoặc issuer không tin cậy, không được ghi subject/client claims chưa xác minh như danh tính thực. Ví dụ event lỗi:

~~~json
{
  "event": "oauth_access_token_validation",
  "outcome": "failure",
  "reason_code": "invalid_signature",
  "issuer_alias": "untrusted",
  "client_alias": "unknown",
  "subject_ref": null,
  "validation_stage": "jwt_signature",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
~~~

Có thể log issuer alias dựa trên cấu hình request/route hoặc nguồn xác minh đã chọn, nhưng phải phân biệt rõ configured_issuer với verified_issuer. Không ghi sub từ token lỗi để tránh attacker làm bẩn audit bằng định danh tùy ý.

## 8. Issuer và client ID: alias, normalization và allowlist

Issuer/client ID nên được ánh xạ qua registry được cấu hình, thay vì tự động lấy bất kỳ chuỗi nào từ token rồi ghi nguyên văn.

### Issuer registry

- Lưu danh sách issuer URI chính xác đã tin cậy.
- Ánh xạ URI sang alias ngắn, ổn định.
- Không tự normalize theo cách có thể làm hai issuer khác nhau trở thành một.
- Không theo redirect hoặc URL do token tự khai để tải JWKS.
- Với issuer không nhận diện, ghi untrusted cùng reason code.

### Client registry

- Ánh xạ client ID đã xác minh sang alias vận hành.
- Tách production/staging và môi trường đối tác.
- Có trạng thái enabled/disabled và owner để hỗ trợ điều tra.
- Không đưa secret, certificate private key hoặc assertion vào registry log.
- Không ghi client ID tự khai từ request như một client đã xác thực.

### Chuẩn hóa và kiểm soát độ dài

Giới hạn kích thước field log, lọc ký tự điều khiển và newline để tránh log injection. Không cắt chuỗi một cách tùy tiện trước khi kiểm tra alias vì có thể làm hai ID khác nhau trùng nhau. Dùng alias registry và mã reason cố định để giữ schema ổn định.

## 9. Không đưa subject/client ID vào metric labels

Metrics thường được lưu với nhãn (labels/tags). Nếu thêm subject hoặc client ID có số lượng lớn vào metric, cardinality tăng mạnh và có thể làm hệ thống metrics tốn bộ nhớ, chậm truy vấn hoặc từ chối ingest.

**Không nên:**

~~~text
http_requests_total{
  subject="user-92841",
  client_id="client-unique-123",
  tenant_id="tenant-very-many"
}
~~~

**Nên dùng nhãn có tập giá trị giới hạn:**

~~~text
token_validation_total{
  issuer_alias="workforce-idp",
  token_format="jwt",
  outcome="success",
  reason_code="validated"
}
~~~

Ví dụ metric phù hợp:

- token_validation_total{issuer_alias, token_format, outcome, reason_code}
- token_exchange_total{client_class, audience_alias, outcome}
- token_introspection_duration_seconds{issuer_alias, outcome}
- authorization_denied_total{service, policy_code, resource_type}
- jwt_unknown_kid_total{issuer_alias}

Tránh label sub, raw client_id, token ID, email, tenant ID tự do hoặc URL đầy đủ có identifier. Nếu cần phân tích theo client, dùng client_class hoặc nhóm client có số lượng giới hạn.

### Log và metric phục vụ hai nhu cầu khác nhau

- Log: chi tiết từng sự kiện, subject reference có kiểm soát, trace ID, reason code.
- Metric: tổng hợp số lượng, latency và outcome với label cardinality thấp.
- Trace: liên kết các service hop; chỉ thêm identity attributes nếu đã đánh giá privacy/cardinality, không gắn raw token.

Không dùng metrics như kho audit và không dùng log thay cho metric tổng hợp.

## 10. Correlation qua nhiều microservices

Một request có thể đi qua gateway, Orders Service, Inventory Service và Payment Service. Để điều tra, cần correlation mà không chuyển token vào log.

~~~mermaid
sequenceDiagram
    participant G as API Gateway
    participant O as Orders Service
    participant I as Inventory Service
    participant P as Payment Service
    G->>O: Request + trace context
    Note over G,O: Log issuer/client alias<br/>subject_ref + trace_id
    O->>I: Request + token phù hợp Inventory API
    Note over O,I: Giữ trace_id; không log bearer token
    I-->>O: Response
    O->>P: Request + token phù hợp Payment API
    Note over O,P: Log actor/client alias<br/>subject_ref theo policy
    P-->>O: Response
    O-->>G: Response
~~~

### Trace ID không phải token ID

- **trace_id** liên kết các span của cùng một distributed trace.
- **request_id** nhận diện một request hoặc operation theo quy ước hệ thống.
- **subject_ref** liên kết sự kiện theo một subject đã pseudonymize.
- **jti** là JWT ID nếu token có claim đó; không dùng nó thay trace ID và cân nhắc pseudonymize nếu cần ghi.
- **access token** là credential; không đưa vào trace baggage, span event hoặc propagation header ngoài mục đích giao thức.

Không nhận trace context tùy ý từ Internet mà không kiểm soát kích thước và tính hợp lệ. W3C trace context là metadata tracing, không phải bằng chứng xác thực hoặc authorization.

### Token exchange

Khi service đổi token để gọi downstream, log có thể ghi:

- Subject reference của chủ thể được đại diện.
- Client alias/actor alias đã xác minh.
- Audience alias của token mới.
- Scope được cấp ở dạng allowlist hoặc summary.
- Outcome và trace ID.

Không log subject_token, actor_token, access_token mới hoặc refresh token. Nếu token exchange thất bại, ghi reason code như invalid_subject_token, unauthorized_client, invalid_target hoặc mã nội bộ đã chuẩn hóa, không ghi raw request body.

## 11. Phân loại event và reason code

Dùng reason code cố định để log có thể tổng hợp và cảnh báo mà không phải phân tích chuỗi lỗi tự do.

| Event | Outcome/reason code gợi ý | Ý nghĩa |
|---|---|---|
| Token validation | validated | Token được chấp nhận |
| Token validation | invalid_signature | Chữ ký không hợp lệ |
| Token validation | untrusted_issuer | Issuer không nằm trong trust configuration |
| Token validation | audience_mismatch | Token không dành cho API |
| Token validation | expired | Token hết hạn |
| Token validation | not_yet_valid | Token chưa có hiệu lực |
| Token validation | revoked_or_inactive | Token không còn active |
| Client authentication | invalid_client | Client không xác thực được |
| Token exchange | exchange_denied | Policy không cho phép đổi token |
| Authorization | insufficient_scope | Thiếu scope |
| Authorization | tenant_mismatch | Tenant context không khớp |
| Authorization | resource_access_denied | Không có quyền trên resource |
| Introspection | introspection_unavailable | Không thể xác minh trạng thái token |

Không ghi toàn bộ exception message vào reason code vì message có thể chứa URL, request data, subject hoặc credential. Có thể lưu exception class và error category đã được lọc ở log kỹ thuật có quyền truy cập phù hợp.

## 12. Quyền truy cập, retention và bảo vệ log

Log identity có thể chứa dữ liệu cá nhân hoặc thông tin nhạy cảm về hệ thống. Cần bảo vệ log như một tài sản bảo mật.

### Access control

- Chỉ nhóm vận hành/security/audit có nhiệm vụ mới được đọc stream chứa subject reference.
- Tách log vận hành phổ thông khỏi audit stream có raw subject nếu thực sự cần.
- Dùng RBAC/ABAC, SSO và MFA cho hệ thống log.
- Ghi audit việc tìm kiếm, export và truy cập log nhạy cảm.
- Không cho mọi developer hoặc vendor có quyền đọc production identity logs mặc định.
- Mã hóa khi truyền và khi lưu; quản lý khóa riêng với log data.

### Retention

- Định nghĩa retention theo mục đích: troubleshooting, security investigation, audit và yêu cầu pháp lý.
- Xóa hoặc aggregate dữ liệu khi hết thời hạn.
- Không giữ raw subject lâu hơn nhu cầu được phê duyệt.
- Kiểm tra bản sao ở backup, archive, SIEM và data lake; retention phải áp dụng cho toàn bộ bản sao.
- Có quy trình legal hold nếu cần nhưng phải được kiểm soát và audit.

### Integrity

Với audit event quan trọng, cân nhắc log append-only, immutable storage, checksum/signature hoặc cơ chế chống sửa/xóa tùy yêu cầu. Bảo vệ log khỏi service đang bị xâm nhập có thể ghi event giả; dùng workload identity và quyền ghi riêng theo nguồn.

## 13. Log injection và dữ liệu do attacker kiểm soát

Các giá trị claim hoặc header có thể chứa ký tự điều khiển, newline, chuỗi rất dài hoặc Unicode khó phân biệt. Nếu log trực tiếp, attacker có thể tạo log giả, phá cấu trúc JSON hoặc làm sai dashboard.

Kiểm soát:

- Chỉ lấy identity từ token đã xác minh hoặc client authentication result.
- Ưu tiên alias registry thay vì log chuỗi tự do.
- Validate độ dài và encoding; escape đúng theo JSON encoder.
- Không nối chuỗi log bằng dữ liệu đầu vào chưa encode.
- Giữ reason code trong enum/allowlist.
- Giới hạn số field và kích thước event.
- Kiểm thử CR/LF, control characters, Unicode confusables và duplicate header.
- Không ghi raw token để debug parsing.

Ví dụ không an toàn:

~~~java
log.info("Authentication failed for subject: " + rawSubject);
~~~

Cách tốt hơn là log field đã được xác minh/biến đổi bằng structured logger:

~~~java
log.atWarn()
    .addKeyValue("event", "token_validation")
    .addKeyValue("outcome", "failure")
    .addKeyValue("reason_code", "untrusted_issuer")
    .addKeyValue("subject_ref", null)
    .log("Token rejected");
~~~

Không dùng placeholder hoặc redaction sau khi đã ghi secret vào log sink; ngăn dữ liệu nhạy cảm đi vào event ngay từ đầu.

## 14. Kiểm thử log không làm lộ credential

Cần có automated tests xác nhận log schema và redaction.

| Test case | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| Token hợp lệ | Gửi JWT hợp lệ | Có issuer/client alias và subject_ref theo policy |
| Token sai chữ ký | Sửa signature hoặc dùng key sai | Không log subject chưa xác minh |
| Issuer lạ | Dùng issuer ngoài allowlist | issuer_alias=untrusted; reason code phù hợp |
| Thiếu client_id | Dùng token profile không có claim đó | client_alias=unknown/not_applicable; không suy đoán |
| Subject nhạy cảm | Subject có email/định danh cá nhân | Log phổ thông chỉ chứa subject_ref |
| Raw Authorization header | Gửi bearer token | Không xuất hiện trong log |
| Refresh token | Gọi token endpoint | Không xuất hiện trong log |
| Client secret | Gửi credential sai | Không xuất hiện trong exception/log |
| CR/LF injection | Claim/metadata có newline | Event vẫn là một record hợp lệ, field được encode |
| Subject dài bất thường | Chuỗi vượt giới hạn | Bị từ chối hoặc xử lý theo policy, không làm phình log |
| Pseudonymization key rotation | Đổi key version | Reference đổi theo version, không ghi raw subject |
| Metric cardinality | Nhiều subject/client ID | Không tạo label theo subject/raw client ID |
| Access control | User không có quyền tìm log | Bị từ chối và hành động bị audit |
| Retention | Hết thời hạn | Dữ liệu bị xóa/aggregate theo policy |

### Kiểm tra log output bằng test appender

Có thể dùng test appender hoặc in-memory log collector để thu event trong test. Sau khi gửi request có token giả, kiểm tra log:

- Có event và reason code mong đợi.
- Có issuer/client alias đúng khi token đã xác minh.
- Subject chỉ xuất hiện dưới dạng pseudonymized reference trong log vận hành.
- Không có chuỗi token, secret, cookie hoặc raw Authorization header.
- Log event hợp lệ JSON và không thể bị tách thành record giả bằng newline.
- Không có claims ngoài allowlist.

Không đưa token thật vào fixture. Dùng token giả với dữ liệu test không phải định danh người thật.

## 15. Ví dụ điều tra sự cố

### Tình huống A — Một client liên tục nhận 401

Dashboard metric cho thấy token_validation_total với issuer_alias=partner-idp và outcome=failure tăng. Log event cho thấy:

- issuer_alias = partner-idp
- client_alias = partner-sync
- reason_code = audience_mismatch
- service = orders-api
- trace_id có thể liên kết với request upstream

Đội vận hành có thể xác định client đang dùng token dành cho API khác mà không cần xem bearer token hoặc subject thật.

### Tình huống B — Subject có nhiều lần gọi API bất thường

Security team tìm các log có cùng subject_ref trong một khoảng thời gian và so sánh service, outcome, audience và trace. Nếu cần xác định danh tính thật, việc tra mapping phải qua quy trình được cấp quyền, có lý do và audit.

Không đưa subject_ref thành label metrics hoặc dashboard ai cũng truy cập được. Reference vẫn cho phép liên kết hoạt động của một người dùng.

### Tình huống C — Token giả tự khai sub=admin

Attacker gửi JWT sai chữ ký với payload sub=admin. Resource server từ chối ở bước signature validation. Log chỉ ghi:

~~~json
{
  "event": "oauth_access_token_validation",
  "outcome": "failure",
  "reason_code": "invalid_signature",
  "issuer_alias": "untrusted",
  "subject_ref": null
}
~~~

Như vậy hệ thống không tạo audit event gây hiểu nhầm rằng administrator đã thực hiện request.

### Tình huống D — Một client đã bị disable vẫn xuất hiện

Log cho thấy client_alias=old-billing-client cùng reason_code=invalid_client. Đội vận hành có thể theo dõi số lần credential cũ được dùng, nguồn service và thời điểm request. Không ghi secret đã bị disable; nếu cần đối chiếu version, log một credential_version_id không nhạy cảm được quản lý.

## 16. Checklist thiết kế production

- Issuer/client ID/subject được lấy sau xác minh hay từ input chưa tin cậy?
- Issuer URI có được ánh xạ sang alias allowlist?
- Client ID có được ánh xạ sang client alias ổn định?
- Subject có được pseudonymize theo issuer, tenant, environment và purpose?
- Có thật sự cần raw subject trong audit không? Ai được đọc và trong bao lâu?
- Có log access token, refresh token, Authorization header, cookie, client secret hoặc private key ở bất kỳ tầng nào không?
- Structured log schema có field allowlist và reason code cố định không?
- Có giới hạn kích thước, escape control characters và chống log injection?
- Subject/client ID có bị đưa vào metric labels hoặc span attributes không cần thiết?
- Trace ID được dùng để correlation thay vì truyền bearer token?
- Log access có RBAC/MFA, audit search/export, encryption và retention?
- Pseudonymization key có được quản lý/rotate độc lập với log data?
- Có automated test xác nhận raw credential không xuất hiện trong log?
- Với JWT và opaque token, log identity fields chỉ sau khi validation/introspection thành công?
- Có phân biệt verified issuer/client với untrusted claim trong failure events?

## 17. Tổng kết

Log **issuer, client ID và subject** giúp điều tra nguồn token, OAuth client và chủ thể được đại diện trong hệ thống nhiều service. Tuy nhiên, các trường này phải được lấy từ kết quả xác thực đã tin cậy, ghi theo schema có cấu trúc và giới hạn đúng mục đích.

Trong log vận hành, nên ưu tiên **issuer alias**, **client alias** và **subject reference được pseudonymize**. Raw subject chỉ nên xuất hiện trong audit stream khi có nhu cầu được phê duyệt, quyền truy cập và retention phù hợp. Không bao giờ ghi raw access token, refresh token, Authorization header, client secret hoặc private key.

Metrics cần dùng label cardinality thấp; distributed tracing dùng trace ID để nối các service hop. Log phải được bảo vệ bằng access control, encryption, retention, integrity và automated redaction tests. **Observability tốt giúp giải thích quyết định xác thực/phân quyền mà không biến hệ thống log thành nơi lưu trữ credential hoặc hồ sơ hành vi không được kiểm soát.**
