# Client secret protection

## Mục tiêu học tập

Trong chương **Client credentials** của học phần **Token Security Fundamentals**, **client secret protection** là việc bảo vệ thông tin xác thực dùng để một **confidential OAuth Client** chứng minh danh tính với **Authorization Server (AS)**. Nếu secret của một ứng dụng bị lộ, attacker có thể cố đóng giả ứng dụng để xin access token, duy trì quyền truy cập hoặc lạm dụng phạm vi quyền đã được AS cấp cho client đó. Việc dùng HTTPS hay ký JWT access token **không tự giải quyết** sự cố lộ client secret.

Sau bài này, bạn có thể:

1. Phân biệt **`client_id`**, **`client_secret`**, **access token**, **refresh token**, khóa ký JWT của AS và các khóa dùng cho sender-constrained token.
2. Xác định môi trường nào **có thể** giữ client secret (confidential backend) và môi trường nào **không thể** giữ secret chia sẻ như bí mật (SPA/native app).
3. Thiết kế vòng đời secret: **tạo bằng CSPRNG → phân phối an toàn → lưu trữ → sử dụng → giám sát → xoay vòng → thu hồi/hủy**.
4. Sử dụng `client_secret_basic` tại token endpoint qua HTTPS và hiểu giới hạn của các phương thức xác thực client khác.
5. Tránh lộ secret qua source code, CI/CD, container image, biến môi trường, file cấu hình, URL, log, trace, crash dump và reverse proxy.
6. Xây dựng chiến lược **zero/low-downtime rotation**, xử lý secret bị nghi lộ và phân biệt việc thu hồi client credential với thu hồi access token đã phát hành.
7. Áp dụng các nguyên tắc đó vào **Spring Security, BFF và giao tiếp microservices**, cùng bài kiểm thử lỗi và quyền đa tenant.

## 1. Client secret là gì và tại sao cần bảo vệ?

Trong OAuth 2.0, Client là ứng dụng xin quyền sử dụng tài nguyên được bảo vệ. Khi một **confidential client** được AS đăng ký sử dụng **client secret**, secret đóng vai trò như **thông tin xác thực dùng chung** giữa Client và AS.

~~~text
Client ID:      billing-worker
Client secret:  <HIGH_ENTROPY_SECRET_FROM_SECURE_STORE>
Grant allowed:  client_credentials
Target API:     billing-api
Scope allowed:  billing:read
~~~

`client_id` là tên/định danh đăng ký của ứng dụng, **không phải mật khẩu**. `client_secret` là credential có thể cho phép bên nắm giữ chứng minh mình là confidential client tương ứng, theo phương thức xác thực được AS hỗ trợ.

### Client secret không phải access token

| Thành phần | Dùng ở đâu? | Ai phát hành/quản lý? | Khi bị lộ |
|---|---|---|---|
| **`client_id`** | Authorization/token request, metadata và audit. | AS đăng ký. | Thường không phải một bí mật; không được coi là bằng chứng xác thực. |
| **Client secret** | Client xác thực với **AS token endpoint** và endpoint AS phù hợp. | AS/registration, lưu phía Client và AS theo mô hình bảo mật. | Attacker có thể thử đóng giả Client để **xin token mới**. |
| **Access token** | Client trình cho **Resource Server (RS)**. | AS phát hành dựa trên grant và policy. | Bản sao bearer token còn hiệu lực có thể bị dùng lại trong đúng phạm vi quyền. |
| **Refresh token** | Client dùng tại **AS token endpoint** để xin access token mới. | AS phát hành nếu policy cho phép. | Có thể duy trì quyền truy cập lâu dài tới khi hết hạn/thu hồi. |
| **Khóa ký JWT của AS** | AS ký, RS xác minh JWT access token theo key trust. | AS quản lý, thường là khóa bất đối xứng. | Rủi ro giả mạo token nếu khóa ký bí mật bị chiếm. |
| **Private key DPoP/mTLS** | Chứng minh quyền sử dụng khóa/chứng chỉ ở các thời điểm đã định. | Client quản lý khóa tương ứng theo profile. | Attacker dùng được khóa có thể vượt qua một phần sender binding. |

**Không đưa `client_secret` tới RS như thể đó là `Authorization: Bearer` token.** RS cần access token đúng audience, scope, issuer và thời hạn; client secret được thiết kế để AS xác thực Client, không phải để API nghiệp vụ nhận diện caller.

### Hai cấp độ thiệt hại khác nhau

- **Lộ một access token ngắn hạn:** attacker có thể thử dùng token đó trong thời gian còn hiệu lực, đúng audience/scope và điều kiện khác.
- **Lộ client secret còn hiệu lực:** attacker có thể thử **xin thêm access token mới** với danh tính Client, thậm chí sau khi token cũ đã hết hạn, cho đến khi credential bị thu hồi hoặc policy chặn.

Mức độ nghiêm trọng phụ thuộc grant mà Client được dùng. Một Client chỉ được cấp `billing:read` cho một tenant gây hậu quả khác hẳn Client được cấp quyền quản trị nhiều API. **Quyền tối thiểu và bảo vệ secret phải đi cùng nhau.**

## 2. Mô hình tin cậy: ai cần biết secret?

~~~mermaid
sequenceDiagram
    participant C as Billing Worker (confidential client)
    participant Vault as Secret Manager
    participant AS as Authorization Server
    participant RS as Billing API
    C->>Vault: Lấy credential theo workload identity/policy
    Vault-->>C: Secret hoặc khả năng sử dụng credential
    C->>AS: POST /token qua TLS + client authentication
    AS->>AS: Xác thực credential; xét grant, resource, scope, tenant
    AS-->>C: Access token cho billing-api
    C->>RS: Authorization: Bearer <ACCESS_TOKEN>
    RS->>RS: Verify token, audience, scope và quyền hóa đơn
    RS-->>C: Dữ liệu đã được phân quyền
~~~

Trong mô hình dùng shared client secret:

1. **AS** có dữ liệu xác minh credential được đăng ký của Client.
2. **Client backend** có quyền truy xuất/sử dụng credential theo chính sách.
3. **Secret manager hoặc workload runtime** có thể quản lý phân phối/giải mã credential theo ranh giới tin cậy.
4. **RS không cần biết client secret** để xác minh access token.
5. **Browser/frontend/public app không được nhận secret** chỉ để tiện gọi AS.

### Một nguyên tắc thiết kế đơn giản

> Client secret chỉ nên xuất hiện ở những thành phần **thực sự phải sử dụng nó để xác thực Client**, và trong **khoảng thời gian cần thiết**.

Việc sao chép secret qua thêm service, container, log hoặc môi trường kiểm thử sẽ tăng số nơi attacker có thể lấy được credential.

## 3. Khi nào không nên dùng client secret?

**Client secret là credential cho confidential client, không phải cách biến public client thành confidential client.**

### SPA/browser JavaScript

Một SPA được phân phối tới browser người dùng:

~~~javascript
// ANTI-PATTERN: đừng đưa client secret vào bundle của trình duyệt.
const clientId = "shop-spa";
const clientSecret = "NOT_A_SECRET_ON_THE_CLIENT";
~~~

Dù code đã được minify, obfuscate, encode Base64 hoặc build-time injected, người dùng/attacker có thể xem bundle, runtime và các request phát ra. Secret chung **không còn là bí mật đáng tin**.

Đối với SPA trực tiếp làm OAuth Client, dùng mô hình **public client** và **Authorization Code + PKCE** khi AS hỗ trợ; bảo vệ redirect, state/transaction, browser token storage và XSS. Không dùng **Client Credentials flow** trực tiếp trong frontend để lấy quyền service.

### Native/mobile app

Client secret cài sẵn trong APK/IPA/desktop binary có thể bị trích xuất từ gói cài đặt hoặc môi trường chạy. Ứng dụng native thông thường cũng là **public client** trong OAuth, cần sử dụng system browser/external user-agent, Authorization Code + PKCE và kho lưu trữ token phù hợp nền tảng.

Một thiết bị có hardware-backed keystore có thể tăng bảo vệ **khóa gắn riêng với thiết bị**, nhưng **một shared client secret được phân phối cho mọi thiết bị** vẫn không trở thành bí mật toàn hệ thống chỉ nhờ đó.

### Backend/BFF

Backend/Backend for Frontend (BFF) nằm trong môi trường kiểm soát được có thể là **confidential client** nếu giữ được credential, vận hành token endpoint và session an toàn.

~~~text
Browser -> BFF:
    session cookie HttpOnly; Secure; SameSite

BFF -> Authorization Server:
    Authorization Code + PKCE + client authentication

BFF -> Resource Server:
    access token đúng audience/scope
~~~

Browser **không cần nhìn thấy client secret**. BFF cũng phải chống CSRF, XSS điều khiển phiên, session hijacking và lưu trữ access/refresh token phía backend.

### Khi có lựa chọn thay shared secret

Nếu AS và hạ tầng hỗ trợ, cân nhắc **`private_key_jwt`**, **mTLS client authentication** hoặc cơ chế **workload identity federation** để tránh đặt một shared static secret lâu dài tại nhiều nơi. Việc chuyển sang cơ chế khác **không loại bỏ quản lý credential**: private key, chứng chỉ, workload identity hoặc token assertion vẫn cần bảo vệ và phân quyền.

## 4. Mô hình đe dọa với client secret

### Cách secret có thể bị lộ

| Đường lộ | Tình huống | Ranh giới bị phá |
|---|---|---|
| **Source/repository** | Secret hardcode trong `application.yml`, test fixture, commit cũ hoặc pull request. | Người đọc source/history có credential. |
| **CI/CD** | Workflow in biến môi trường, dùng lệnh debug, artifact chứa config. | Build runner/log có secret. |
| **Container image** | Secret nằm trong `Dockerfile ENV`, `ARG`, layer hoặc file build. | Bất kỳ ai kéo image/đọc layer có thể tìm credential. |
| **Runtime/host** | File secret world-readable, process dump, backup, shell history. | Attacker có quyền đọc hệ thống lấy credential. |
| **Kubernetes/Orchestrator** | Quyền đọc Secret quá rộng hoặc secret nằm trong manifest công khai. | Workload/nhân sự không có nhu cầu truy cập. |
| **HTTP transport** | Secret đưa vào query string, HTTP không TLS, proxy log request body/header. | Credential xuất hiện ngoài AS và Client. |
| **Observability** | APM/trace thu thập `Authorization` hoặc request payload. | Hệ thống giám sát trở thành kho credential. |
| **SSRF/metadata endpoint** | App bị ép gọi internal secret endpoint/metadata không kiểm soát. | Attacker gián tiếp lấy credential hoặc token. |
| **Insider/compromised service** | Principal có quyền đọc vault quá rộng hoặc máy bị chiếm. | Credential được dùng trái mục đích. |

~~~mermaid
flowchart TD
    A["Attacker muốn có quyền Client"] --> B{"Có thể lấy client secret?"}
    B --> C["Source / image / CI artifact"]
    B --> D["Logs / traces / proxy"]
    B --> E["Vault / runtime / host"]
    C --> F["Credential còn hiệu lực"]
    D --> F
    E --> F
    F --> G{"AS chấp nhận client authentication?"}
    G -- Có --> H["AS xét grant + resource + scope + tenant"]
    H --> I["Có thể cấp token trong quyền của client"]
    I --> J["RS kiểm tra token, action, object và tenant"]
    G -- Không --> K["Từ chối client"]
~~~

Mục tiêu không chỉ là “giấu secret”. **Registration/policy tại AS** và **authorization tại RS** vẫn cần giới hạn thiệt hại khi secret bị lộ. Một ứng dụng chỉ cần đọc một API không nên có credential xin scope quản trị toàn tổ chức.

## 5. Tạo client secret đủ mạnh

### Entropy quan trọng hơn độ dài nhìn bằng mắt

Secret phải **khó đoán và độc lập** với user ID, client ID, timestamp, tên hệ thống hoặc password dễ nhớ. Tạo bằng **cryptographically secure pseudorandom number generator (CSPRNG)**, không dùng `java.util.Random`, `Math.random()` hoặc chuỗi mẫu.

Ví dụ Java tạo **32 byte ngẫu nhiên** (~256 bit entropy lý tưởng khi nguồn ngẫu nhiên phù hợp) rồi mã hóa Base64URL không padding:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

final class ClientSecretGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    static String generate() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
~~~

Đây là ví dụ **sinh chuỗi ngẫu nhiên**, **không phải** implementation đầy đủ của AS. Việc cấp, lưu, hiển thị một lần, xác minh và thu hồi secret cần một quy trình registration có audit/phân quyền.

### Những anti-pattern phải tránh

~~~text
client_secret = client_id
client_secret = "password123"
client_secret = "billing-worker-2026"
client_secret = md5(client_id)
client_secret = timestamp + random_small_number
client_secret = same_shared_secret_for_every_service
~~~

Một chuỗi dài nhưng có cấu trúc dự đoán được vẫn yếu. **Không phát cùng một secret cho nhiều Client**: khi một dịch vụ bị lộ, kẻ tấn công không nên dùng credential đó để mạo danh các dịch vụ khác.

### Secret là opaque value

Không gắn quyền vào cấu trúc secret như `tenant-a:admin:2026` rồi phân tích chuỗi để quyết định quyền. **AS mới là nguồn đáng tin** về danh tính client, grant types, audience và scope. Secret chỉ là credential; quyền thay đổi phải được AS/RS áp dụng qua policy.

### Tránh tiết lộ trong khâu cấp ban đầu

Nếu AS cần hiển thị secret để quản trị viên sao chép vào kho an toàn, nên hỗ trợ **hiển thị một lần**, kênh bảo mật và xác thực quản trị phù hợp. Không gửi secret qua email/chat/ticket văn bản thuần hoặc đính kèm vào báo cáo audit. Sau khi cấp, lưu **thông tin nhận diện phiên bản hoặc fingerprint không thể dùng xác thực** phục vụ vận hành thay vì in lại toàn bộ secret.

## 6. Client authentication bằng `client_secret_basic`

Trong OAuth 2.0 (RFC 6749), một confidential client có thể xác thực tại token endpoint bằng HTTP Basic theo cấu hình của AS. Với `client_credentials`:

~~~http
POST /token HTTP/1.1
Host: auth.example.test
Authorization: Basic <STANDARD_BASE64_OF_FORM_ENCODED_CLIENT_ID_AND_SECRET>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=billing%3Aread
~~~

**Chú ý:** HTTP Basic dùng **Base64 chuẩn**, không phải Base64URL, và Base64 **không phải mã hóa bảo mật**. Client ID và secret cần được **form-encode theo quy tắc RFC 6749 `2.3.1` trước khi ghép bằng dấu `:` và Base64-encode**. Ưu tiên thư viện OAuth đã xử lý chuẩn thay vì tự lắp chuỗi.

### Điều kiện tối thiểu

1. Token endpoint dùng **HTTPS** với TLS certificate verification bật.
2. Client authentication method phải **khớp registration** của client.
3. Không đưa secret vào query string, URL path, redirect URI hay authorization request qua browser.
4. Không ghi `Authorization` header vào access log, trace, error report hoặc HTTP debug log.
5. AS **giới hạn rate**, báo lỗi phù hợp và không tiết lộ secret đúng/sai qua thông báo quá chi tiết.
6. AS kiểm tra grant, scope, resource và tenant **sau khi xác thực client**, không tự cấp quyền chỉ vì secret đúng.

### Token response minh họa

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<ACCESS_TOKEN_FOR_BILLING_API>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "billing:read"
}
~~~

Client secret **không xuất hiện trong token response**. Access token có thể là JWT hoặc opaque token. Theo RFC 6749, với Client Credentials, refresh token **SHOULD NOT** được cấp; thông thường Client dùng credential của chính mình xin access token mới khi cần.

### Vì sao không dùng secret ở Resource Server?

~~~http
GET /invoices HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN_FOR_BILLING_API>
~~~

Billing API phải xác minh token và quyền; nó **không nên** đòi `client_secret` của billing-worker. Nếu nhiều API bắt caller gửi cùng shared secret trực tiếp, mỗi API trở thành nơi có thể lộ credential gốc và phá vỡ ranh giới giữa **client authentication tại AS** và **access-token authorization tại RS**.

## 7. So sánh các phương thức xác thực Client

| Phương thức | Credential thực tế | Ưu điểm | Trách nhiệm/rủi ro |
|---|---|---|---|
| **`client_secret_basic`** | Shared client secret qua HTTP Basic tại token endpoint. | Được hỗ trợ rộng trong OAuth 2.0. | Cần bảo vệ secret, TLS, header/log redaction và rotation. |
| **`client_secret_post`** | Shared secret trong body form POST. | Hỗ trợ trong một số AS/client. | Body có thể bị log; không nên chọn nếu có phương thức tốt hơn, phải dùng TLS. |
| **`client_secret_jwt`** | Assertion JWT ký bằng HMAC với shared secret. | Không gửi lại secret thô trong mỗi assertion. | Vẫn là shared secret; phải bảo vệ khóa HMAC và kiểm tra assertion đầy đủ. |
| **`private_key_jwt`** | JWT assertion ký bằng private key của Client. | AS có thể xác minh bằng public key; không cần AS giữ shared secret thô. | Quản lý khóa, `iss`/`sub`/`aud`, hạn dùng, `jti` và rotation. |
| **mTLS client authentication** | TLS client certificate và khả năng sử dụng private key. | Xác thực client ở lớp TLS phù hợp backend-to-backend. | PKI, certificate lifecycle, proxy termination/trust boundary. |
| **Workload identity federation** (khi AS hỗ trợ) | Assertion ngắn hạn từ hệ thống định danh workload đáng tin. | Có thể giảm shared static secret dài hạn. | Phải chặn giả workload identity, audience/issuer confusion và cấp quyền quá rộng. |

### `client_secret_jwt` không phải access token JWT

Ở phương thức này, Client tạo **client assertion** được ký bằng shared secret và gửi tới AS. Token JWT assertion này **xác thực Client**, không đại diện cho quyền gọi Orders/Billing API. AS phải xác minh audience dành cho token endpoint/AS, issuer/subject client, thời hạn, thuật toán HMAC cho phép, nonce/`jti` khi profile yêu cầu và các điều kiện liên quan.

**Đừng tái sử dụng client secret làm khóa ký access token của AS**. Hai ranh giới tin cậy và vòng đời khóa khác nhau. Tương tự, không dùng secret để ký JWT tự chế rồi cho RS coi như token AS cấp.

### Chọn phương thức không phải “càng phức tạp càng tốt”

Khi chọn, cần xem khả năng của AS, tầng TLS/proxy, secret manager/keystore, quy trình rotation, latency và mô hình đe dọa. `private_key_jwt` hoặc mTLS có thể giảm nhu cầu chia sẻ secret với AS theo cách khác, nhưng một private key bị lộ vẫn gây hậu quả lớn. **Điều quan trọng là cơ chế được kiểm chứng và vận hành đúng.**

## 8. Lưu trữ phía Client: secret manager thay vì source code

Một quy tắc mạnh: **application code chỉ tham chiếu tên/cấu hình credential, còn giá trị thật được cấp qua kênh runtime có kiểm soát**.

### So sánh vị trí lưu

| Nơi lưu | Rủi ro | Khuyến nghị |
|---|---|---|
| **Git source**, kể cả private repo | History, fork, artifact và người đọc repo có thể giữ bản sao lâu dài. | **Không commit secret**; quét cả commit/history khi nghi lộ. |
| **`application.yml` chứa plaintext secret** | Bí mật đi theo source/package/config backup. | Dùng external configuration, vault injection hoặc secret store. |
| **Environment variable** | Dễ inject nhưng có thể bị lộ trong debug, process inspection, crash dump, quyền runtime. | Chỉ dùng nếu môi trường/đường nạp được bảo vệ; không coi env là kho bí mật tuyệt đối. |
| **File mount từ secret store** | Có thể bị đọc nếu ACL sai, container volume/shared path rò rỉ. | Mount read-only, giới hạn principal/permissions, rotate và không ghi file ra image. |
| **Vault/KMS/secret manager** | Cần quản lý chính sách truy cập, identity và availability của kho. | Thường phù hợp khi có audit, RBAC, encryption at rest, versioning và rotation. |
| **Container image/layer** | Secret có thể tồn tại trong registry/layer ngay cả sau lệnh xóa file. | Không bake secret bằng `ARG`/`ENV` hoặc copy file secret vào image. |
| **Log/APM/backup** | Nhiều hệ thống phục vụ điều tra lại vô tình lưu credential. | Redaction, hạn chế quyền và chính sách retention phù hợp. |

### Một nguyên tắc cấp quyền cho secret manager

~~~text
Workload identity: billing-worker-prod
Allowed secret:    /prod/oauth/billing-worker/client-secret
Allowed operation: read/use current approved version
Denied:            /prod/oauth/* for every other client
Denied:            list-all-secrets, change-policy, delete-all-secrets
~~~

Tên secret/đường dẫn trên là minh họa. Nếu dùng workload identity tại runtime, ứng dụng không cần một **vault password tĩnh** được hardcode để lấy client secret. Nhưng cần bảo vệ identity/metadata/credential cho phép truy cập vault, nếu không chỉ chuyển điểm yếu sang một secret khác.

### Không truyền qua tham số dòng lệnh

Tránh:

~~~text
java -jar billing.jar --client-secret=<REAL_SECRET>
curl -u billing-worker:<REAL_SECRET> https://auth.example.test/token
~~~

Giá trị có thể lọt vào shell history, process command line, CI logs hoặc crash diagnostics. Dùng OAuth library và cơ chế nạp secret an toàn; không dùng `-v`/debug trace trong môi trường chạy thật để in credential.

## 9. Cấp credential qua CI/CD, container và Kubernetes

### CI/CD

Một pipeline cần client secret để chạy integration test hoặc deploy phải:

1. Cấp quyền chỉ cho **job/environment cần thiết**, không đặt secret tổ chức vào toàn bộ pipeline.
2. Không expose secret cho **untrusted pull request** hoặc code không được duyệt.
3. Không in full environment, HTTP headers, deployment manifests đã render hoặc stack trace chứa secret.
4. Giới hạn retention và quyền xem log/artifact.
5. Xóa secret khỏi temporary files/cache và xử lý cả runner bị nghi chiếm quyền.
6. Nếu được hỗ trợ, dùng **short-lived workload federation** thay shared static credential trong CI.

### Container image

Không đưa client secret vào `Dockerfile ARG`, `ENV`, layer hoặc build artifact. Việc chạy `RUN rm secret.txt` ở layer sau **không xóa chắc chắn dữ liệu khỏi layer trước**. Image nên có thể được phát hành và quét độc lập mà **không chứa credential sản xuất**.

### Kubernetes Secrets không tự bảo đảm bí mật tuyệt đối

Kubernetes có resource **Secret**, nhưng dữ liệu thường được biểu diễn Base64 trong manifest/API. **Base64 là biểu diễn, không phải mã hóa bảo mật.** Cần bảo vệ control plane, etcd/encryption-at-rest nếu dùng, RBAC, service account, admission policy và luồng đưa secret tới pod.

~~~text
Namespace:      production
Workload:       billing-worker
Secret source:  secret manager / Kubernetes Secret theo kiến trúc
Mount:          read-only trong container cần sử dụng
Access:         chỉ service account đã được cấp quyền
Audit:          ai đọc/đổi phiên bản credential và khi nào
~~~

Không đưa manifest chứa giá trị secret đã Base64-encode vào repo rồi cho rằng đó là đã mã hóa. Cũng không cấp quyền `get/list/watch secrets` cho mọi service account trong namespace.

### Rotate trong runtime

Một runtime có thể nạp secret **qua environment variable khi khởi động** hoặc **qua mount được cập nhật**. Hai cơ chế có hành vi khác nhau:

- Biến môi trường của process hiện tại **không tự thay đổi** khi secret manager xoay phiên bản.
- File mount có thể được cập nhật tùy nền tảng/integration, nhưng ứng dụng có thể **cache giá trị cũ** trong bộ nhớ.
- Không mặc định rằng cập nhật vault đồng nghĩa mọi instance bắt đầu dùng secret mới ngay.
- Cần cơ chế reload/restart có kiểm soát và phiên bản credential có thể quan sát được **mà không in giá trị bí mật**.

## 10. Bảo vệ credential trong khi truyền

### HTTPS/TLS không được bỏ qua

Token endpoint nhận `client_secret_basic` hoặc `client_secret_post` phải dùng HTTPS với **server certificate validation** đầy đủ. Không bỏ xác minh TLS certificate hoặc chấp nhận mọi certificate khi môi trường gặp lỗi:

~~~text
BAD:
  trustAllCertificates = true
  disableHostnameVerification = true
  POST secret to http://auth.internal/token

GOOD:
  use https://auth.example.test/token
  validate TLS chain and hostname
  use a configured trust store and secured proxy paths
~~~

“AS nằm trên mạng nội bộ” không đủ để biến HTTP plaintext thành kênh an toàn. Mạng service mesh, reverse proxy, ingress, egress và sidecar cũng cần phân tích nơi TLS bắt đầu/kết thúc.

### Reverse proxy và API gateway

Nếu proxy kết thúc TLS:

- Xác định proxy có nhìn thấy **Authorization header chứa client secret** hay không.
- Không log header, request body hoặc bản sao packet vô tình chứa credential.
- Bảo vệ kết nối proxy → AS backend; xác thực proxy hoặc dùng TLS/mTLS giữa các thành phần nếu cần.
- Xóa/ghi đè forwarded headers không đáng tin; không cho client Internet tự tạo metadata giả.
- Giới hạn những gateway/route được phép tiếp cận token endpoint.

### Không đặt client secret vào URL

~~~http
GET /token?client_id=billing-worker&client_secret=<SECRET> HTTP/1.1
Host: auth.example.test
~~~

**Đây là anti-pattern.** URL/query thường xuất hiện trong access log, browser history, monitoring, proxy cache hoặc referer tùy hoàn cảnh. OAuth token endpoint yêu cầu request theo phương thức và định dạng phù hợp, không dùng GET chứa secret.

## 11. Logging, telemetry và quản lý rò rỉ vô tình

### Những nơi thường bị quên

| Thành phần | Dữ liệu có thể vô tình ghi | Biện pháp |
|---|---|---|
| **HTTP client debug** | `Authorization: Basic ...`, request form `client_secret`. | Tắt/sanitize sensitive headers và body logging. |
| **Gateway/reverse proxy** | Header/token endpoint request, traces. | Redact trước khi gửi telemetry, tách access log phù hợp. |
| **APM/OpenTelemetry exporter** | HTTP headers, exception attributes, URL. | Allowlist safe fields, lọc credential đầu nguồn. |
| **Application exception** | Full request, config object và environment. | Không serialize secret/config, lỗi có mã phân loại. |
| **Support ticket** | Screenshot màn hình secret, curl command hoặc log raw. | Thay bằng fingerprint/version, xóa bản sao và rotate nếu nghi lộ. |
| **Crash dump/heap dump** | Secret trong String/memory. | Hạn chế quyền tạo/xem, mã hóa/lưu giữ an toàn, xóa theo retention. |
| **Test report/recording** | HTTP cassette chứa request thật. | Fake credential, redaction, hạn chế môi trường và quyền. |

### Audit vẫn cần đủ khả năng điều tra

Không ghi **giá trị** secret, nhưng có thể ghi:

~~~json
{
  "event": "oauth.client_authentication",
  "client_id": "billing-worker",
  "environment": "prod",
  "credential_version": "v7",
  "result": "denied",
  "reason": "credential_expired",
  "correlation_id": "audit-987"
}
~~~

`credential_version` là định danh vận hành **không thể dùng thay secret**. Một fingerprint không thể đảo từ secret có entropy cao cũng có thể giúp so khớp vụ việc nếu chính sách an toàn cho phép, nhưng không cần ghi bản hash của secret ở mọi request.

### Đừng tin duy nhất “masking ở màn hình”

Một UI hiển thị `******` không chứng minh backend, network trace hoặc log không chứa secret thật. Biện pháp redaction phải được áp dụng **trước khi thông tin nhạy cảm rời khỏi ranh giới kiểm soát**, không chỉ khi trình bày giao diện.

## 12. Authorization Server nên lưu và xác minh secret như thế nào?

AS giữ **registration và trạng thái credential** của client: ID, loại secret/khóa, chính sách, phiên bản, thời hạn và trạng thái thu hồi. Không lưu hoặc trả plaintext secret nhiều hơn mức hệ thống thật sự cần.

### Một thiết kế xác minh khả thi

Đối với **secret ngẫu nhiên có entropy cao**, AS có thể lưu **giá trị kiểm chứng một chiều** thay cho raw plaintext nếu thiết kế giao thức và phần mềm cho phép. Có thể dùng hàm hash/MAC phù hợp có kiểm soát, hoặc credential-verifier backend đã được kiểm chứng; với secret có entropy thấp như mật khẩu, cần cách lưu password hashing phù hợp và tốt nhất **không phát secret yếu ngay từ đầu**.

~~~text
Client registration:
    client_id             = billing-worker
    credential_version    = v7
    verifier              = <ONE_WAY_VERIFIER_NOT_USABLE_AS_SECRET>
    state                 = active
    created_at            = <TIMESTAMP>
    expires_at            = <TIMESTAMP_OR_POLICY>
    allowed_grants        = {client_credentials}
    allowed_resources     = {billing-api}
    allowed_scopes        = {billing:read}
~~~

**Lưu ý:** nếu một AS có nhiệm vụ yêu cầu phục hồi raw secret cho một cơ chế đặc thù, cần đánh giá riêng **encrypted secret storage** và khả năng giải mã, thay vì giả vờ một chiều là luôn đủ. **Không tự sáng tạo thuật toán băm, mã hóa hoặc cách so sánh** để thay hệ thống AS đã được kiểm chứng.

### Những điểm AS cần thực thi

1. Chỉ chấp nhận **client authentication method đã đăng ký** và thuật toán có allowlist phù hợp.
2. So sánh credential/credential verifier theo cách **không tạo lỗ hổng timing rõ ràng**, sử dụng thư viện đáng tin.
3. Xác minh credential còn **active**, đúng client, đúng phạm vi sử dụng và chưa bị thu hồi.
4. Chặn brute force, credential stuffing, các lần thử token endpoint bất thường theo chính sách rate limiting/monitoring.
5. Có thể hỗ trợ **nhiều credential version đang active tạm thời** để rotate an toàn.
6. Không cho việc Client xác thực thành công tự động cấp **scope/audience ngoài policy**.
7. Không phản hồi raw secret qua endpoint đọc registration, introspection hoặc các API audit.

### Tránh credential confusion

Một client có thể tồn tại nhiều phiên bản secret trong giai đoạn rotate. AS phải đối chiếu với **đúng client_id và bản ghi active**, không kiểm tra xem secret “có tồn tại đâu đó trong toàn bộ hệ thống” rồi nhận diện sai client. Không nhận request có nhiều phương thức client authentication mâu thuẫn mà tùy ý chọn credential có quyền cao hơn.

## 13. Xoay vòng client secret không gây gián đoạn

**Rotation** là việc thay secret cũ bằng secret mới theo chính sách. Nên thực hiện **định kỳ theo mức rủi ro** và bắt buộc khi có dấu hiệu credential bị lộ. Một hệ thống nhiều instance cần quy trình có điều kiện và giám sát, không đơn giản là thay chuỗi trong file rồi restart một máy.

### Quy trình zero/low-downtime điển hình

~~~mermaid
sequenceDiagram
    participant Op as Operator / Automation
    participant AS as Authorization Server
    participant Vault as Secret Manager
    participant W1 as Worker Instance 1
    participant W2 as Worker Instance 2
    Op->>AS: Tạo credential v8, giữ v7 active có giới hạn
    AS-->>Op: Secret v8 một lần qua kênh bảo mật
    Op->>Vault: Lưu v8, đánh dấu phiên bản hiện hành/được triển khai
    Op->>W1: Rolling reload/redeploy để dùng v8
    Op->>W2: Rolling reload/redeploy để dùng v8
    W1->>AS: Xin token bằng v8
    AS-->>W1: Thành công nếu policy hợp lệ
    W2->>AS: Xin token bằng v8
    AS-->>W2: Thành công nếu policy hợp lệ
    Op->>Op: Kiểm tra mọi worker đã chuyển v8
    Op->>AS: Thu hồi v7 (kết thúc overlap)
    AS-->>Op: v7 không còn được chấp nhận
~~~

### Từng bước và điểm kiểm tra

1. **Inventory:** xác định client ID, environment, instance/job nào đang sử dụng secret, những nơi có bản sao và người sở hữu.
2. **Tạo mới:** AS phát secret v8 bằng CSPRNG; đăng ký hoạt động theo policy, có thể cho phép đồng tồn tại v7/v8 **trong cửa sổ ngắn**.
3. **Phân phối:** lưu v8 vào secret manager, không gửi qua ticket/email/chat, không commit vào CI/CD.
4. **Chuyển runtime:** rolling restart/reload các instance và scheduled jobs; quan sát xác thực bằng **credential version**, không in secret.
5. **Xác minh:** kiểm tra token endpoint chấp nhận v8 và các workload thực sự lấy token đúng resource/scope.
6. **Kết thúc overlap:** vô hiệu hóa v7 sau khi xác nhận không còn sử dụng, theo deadline có hạn.
7. **Dọn dấu vết:** loại bản sao cũ khỏi kho runtime/tài liệu/backup trong khả năng; cập nhật audit và kế hoạch rotation tiếp.

### Nếu AS chỉ cho một active secret

Không phải AS nào cũng hỗ trợ nhiều credential version hoạt động cùng lúc. Nếu thay secret làm **vô hiệu hóa v7 ngay lập tức**, cần có quy trình cutover khác: chuẩn bị triển khai gần như đồng bộ, chọn thời điểm bảo trì hoặc chuyển sang phương thức client authentication có rotation thuận lợi hơn. **Không giả định zero downtime khi nhà cung cấp không hỗ trợ**.

### Thời gian overlap là một rủi ro

Hai secret cùng active tăng số credential có thể bị lạm dụng. Không giữ v7 “để đề phòng” vô thời hạn. Thiết lập deadline, telemetry phiên bản và cảnh báo nếu v7 vẫn được dùng sau thời điểm dự kiến.

### Rotation client secret khác với rotation JWT signing key

- **Client secret rotation:** thay credential dùng để Client xác thực với **AS**.
- **AS signing key rotation:** thay khóa AS dùng để ký JWT, RS cần cập nhật/trust JWKS tương ứng.
- **Refresh token rotation:** thay refresh token trong grant để giảm tác động khi token bị đánh cắp.

Ba hoạt động có mục đích/vòng đời khác nhau. **Không đồng nhất thay client secret với việc tất cả access token cũ sẽ bị thu hồi.**

## 14. Thu hồi secret và ứng phó khi nghi bị lộ

### Tình huống: secret được commit vào repository

Một developer vô tình thêm secret sản xuất vào source. Sau đó xóa dòng secret và tạo commit mới.

**Điều này chưa đủ**, vì secret có thể còn trong Git history, clone, artifact, CI cache hoặc bản sao đã được người khác đọc. Hành động ưu tiên:

1. **Xem secret là đã lộ**, xác định client/environment/quyền bị ảnh hưởng và phạm vi rủi ro.
2. **Thu hồi/rotate secret** tại AS theo mức độ khẩn cấp; nếu nguy cơ cao, có thể phải ngừng Client tạm thời để chặn cấp token mới.
3. **Cập nhật secret manager/runtime** bằng credential mới theo quy trình cutover phù hợp.
4. Kiểm tra token đã phát hành, **scope/audience/tenant**, và dấu vết token endpoint/client auth bất thường.
5. Xử lý **access/refresh token đã phát hành** theo cơ chế AS/RS và chính sách thu hồi.
6. Tìm và giảm bản sao trong logs, history, artifact, container registry, backups; làm sạch nơi công khai **sau khi đã vô hiệu hóa credential**.
7. Điều tra nguyên nhân, cập nhật secret scanning/policy, access control và cảnh báo.

### Khi attacker có client secret

~~~mermaid
flowchart TD
    A["Nghi client secret bị lộ"] --> B["Xác định client, grant, audience, scope và tenant"]
    B --> C{"Có khả năng attacker xin token mới?"}
    C -- Có / chưa rõ --> D["Rotate/revoke credential; cân nhắc disable client"]
    C -- Không rõ --> D
    D --> E["Thay credential cho workload hợp lệ"]
    E --> F["Điều tra AS token issuance và RS access audit"]
    F --> G["Xem xét revoke token/grant, rút ngắn TTL hoặc kiểm tra trạng thái"]
    G --> H["Sửa nguồn lộ và xác minh không còn dùng secret cũ"]
~~~

### Access token đã phát hành có tự vô hiệu không?

**Không nhất thiết.** Đổi hoặc thu hồi client secret thường chặn **client authentication mới**, nhưng access token đã phát hành có thể:

- Còn hiệu lực nếu RS xác minh **JWT signature/`exp` offline** và không kiểm tra trạng thái thu hồi.
- Bị chặn nếu token introspection/denylist/AS policy/RS state cho phép thu hồi tương ứng.
- Có thời hạn ngắn hơn hoặc bị ràng buộc với khóa/chứng chỉ người gửi, giảm phạm vi lạm dụng theo thiết kế.

**Không tuyên bố đã thu hồi toàn bộ truy cập** chỉ dựa trên việc v7 đã bị AS vô hiệu hóa. Cần đánh giá token/grant và các Resource Server liên quan.

### Bảng thời điểm sự cố

| Thời điểm | Cần hành động gì? | Vì sao? |
|---|---|---|
| **Ngay khi phát hiện** | Giới hạn credential có thể dùng, bảo vệ bằng chứng, xác định phạm vi. | Chặn tiếp tục xin token. |
| **Trong quá trình thay thế** | Chuyển workload hợp lệ sang credential mới, giám sát failed auth/success auth theo version. | Không mở một đường fallback không kiểm soát. |
| **Sau khi thu hồi secret cũ** | Kiểm tra token đã phát và quyền truy cập RS, xử lý revocation/TTL. | Secret cũ chết không đồng nghĩa token cũ chết. |
| **Sau sự cố** | Secret scanning, vault RBAC, logging redaction, incident postmortem. | Ngăn tái diễn. |

## 15. Spring Security: cấu hình không hardcode client secret

### Registration cho service backend

Ví dụ Spring Boot application dùng OAuth 2.0 Client Credentials:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          billing-service:
            provider: company-auth
            client-id: billing-worker
            client-secret: ${BILLING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - billing:read
        provider:
          company-auth:
            token-uri: https://auth.example.test/token
~~~

**`${BILLING_CLIENT_SECRET}` là placeholder cấu hình Spring** trỏ tới giá trị runtime, **không** phải secret thật. Cần cung cấp biến/cấu hình đó qua pipeline/workload/secret manager có kiểm soát. Không dùng mặc định kiểu `${BILLING_CLIENT_SECRET:dev-secret}` trong production, vì có thể vô tình chạy với một giá trị yếu.

Lưu ý:

- `token-uri` dùng HTTPS và phải kiểm tra TLS certificate hợp lệ.
- `client-secret` không có nghĩa rằng Spring tự bảo vệ source/CI/runtime của credential.
- Client Credentials không cần trình duyệt; **không** lưu secret ở SPA.
- Nếu AS cần `resource` (RFC 8707), phải cấu hình **custom token request** theo API/framework hỗ trợ; ví dụ trên không tự bảo đảm audience.

### AuthorizedClientManager sử dụng token thay cho code tự viết

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
class BillingOAuthConfig {
    @Bean
    OAuth2AuthorizedClientManager serviceClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {
        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Mã trên minh họa một **backend service**, không phụ thuộc HTTP servlet request của end-user. Spring có thể lấy lại access token còn hạn hoặc yêu cầu token mới tùy provider/authorized client store, nhưng vẫn cần cấu hình TLS, token cache, expiry skew, secret source, retry và failure handling đúng môi trường.

### Client chỉ dùng access token tại API

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.web.client.RestClient;

final class BillingApiClient {
    private final OAuth2AuthorizedClientManager manager;
    private final RestClient api = RestClient.create();

    BillingApiClient(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    String readInvoices() {
        OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
                .withClientRegistrationId("billing-service")
                .principal("billing-worker-service")
                .build();
        OAuth2AuthorizedClient authorized = manager.authorize(request);
        if (authorized == null || authorized.getAccessToken() == null) {
            throw new IllegalStateException("Service authorization unavailable");
        }
        String tokenValue = authorized.getAccessToken().getTokenValue();
        return api.get()
                .uri("https://api.example.test/invoices")
                .headers(headers -> headers.setBearerAuth(tokenValue))
                .retrieve()
                .body(String.class);
    }
}
~~~

`principal("billing-worker-service")` trong API quản lý authorized client **không tự tạo claim `sub` cho token**; AS quyết định service principal theo registration/policy. Ví dụ giả định token Bearer cho Billing. Nếu token là **DPoP-bound** hoặc **certificate-bound**, client HTTP phải thực hiện cơ chế sender proof phù hợp; không dùng ví dụ Bearer này để bỏ qua yêu cầu ràng buộc.

### Khi cần debug lỗi client authentication

Không bật logging toàn bộ Basic header hoặc dump biến môi trường. Hãy kiểm tra:

~~~text
client_registration_id   = billing-service
client_auth_method       = client_secret_basic
credential_version       = v8       # metadata, không phải giá trị secret
token_endpoint           = https://auth.example.test/token
auth_result              = invalid_client
runtime_version          = deployment-42
~~~

Kiểm tra version được triển khai, vault policy, TLS trust, sự trùng khớp client registration với AS và trạng thái rotation. **Không trả secret ra UI hoặc log để “so sánh nhanh”.**

## 16. Client secret protection trong BFF và hệ thống nhiều service

### BFF dùng Authorization Code

Confidential BFF có thể xác thực Client khi đổi authorization code; việc giữ client secret phía server không thay:

- **PKCE S256** để ràng buộc authorization code với verifier từng giao dịch.
- `state`, issuer, redirect URI, session binding và kiểm tra callback.
- User consent/AS policy theo client, resource và scope.
- Bảo vệ session cookie `HttpOnly; Secure; SameSite` và phòng chống CSRF.
- Bảo vệ access/refresh token phía backend và thu hồi khi logout/consent changes.

**Client secret xác thực ứng dụng**, không tự chứng minh user đã đồng ý cho `orders:read` hoặc có quyền đọc đơn của tenant khác.

### Microservices

Giả sử:

~~~text
Orders Service -> Billing API:
    client_id = orders-to-billing
    scope     = billing:read
    aud       = billing-api

Reports Worker -> Reports API:
    client_id = reports-worker
    scope     = reports:export
    aud       = reports-api
~~~

Nên có **client registration/credential tách biệt** khi ranh giới quyền khác nhau, thay vì đưa một shared `platform-admin-secret` cho mọi service. Tách credential giúp thu hồi riêng, audit chính xác và giảm mức ảnh hưởng khi một service bị xâm nhập.

### Multi-tenant

Client secret hợp lệ cho một client có quyền `billing:read` **không chứng minh quyền đọc hóa đơn mọi tenant**.

~~~text
Verified service client: billing-worker
Allowed tenant:          tenant-a
Access token audience:   billing-api
Access token scope:      billing:read

Requested invoice:       inv-999
Invoice tenant:          tenant-b

=> DENY nếu không có ủy quyền cross-tenant riêng.
~~~

AS có thể ràng buộc client với tenant/policy; RS còn phải kiểm tra invoice thực tế và quyền service. Header `X-Tenant-Id` hay query `tenant=...` do caller truyền **không tự chứng minh** entitlement. Tránh **confused deputy**: backend có service credential mạnh không được thay caller ít quyền để trả dữ liệu không được phép.

## 17. Client secret và các biện pháp bảo vệ token sau cấp

### Secret bảo vệ bước xin token, không bảo vệ mọi bước dùng token

~~~mermaid
flowchart LR
    C["Client: giữ client secret"] -->|"Xác thực với AS"| A["Authorization Server"]
    A -->|"Cấp access token"| T["Access token đúng aud/scope/TTL"]
    T -->|"Client trình với RS"| R["Resource Server"]
    R -->|"Verify token + permission"| D["Dữ liệu được phép"]
~~~

Nếu access token là **bearer**, attacker có bản sao còn hạn có thể thử dùng tại RS mà **không cần client secret**, trong phạm vi token được chấp nhận.

| Lớp bảo vệ | Giải quyết câu hỏi | Không tự bảo đảm |
|---|---|---|
| **Client secret/client auth** | Ai đang xin token tại AS? | Ai đang trình bearer token ở RS? |
| **PKCE khi dùng Authorization Code** | Code có được đổi bằng verifier đúng giao dịch? | Token bị sao chép sau khi cấp không bị replay. |
| **Audience + scope** | Token dành cho API/action nào? | Chủ thể được phép đọc mọi bản ghi? |
| **JWT signature/introspection** | Token có hợp lệ và do issuer tin cậy cấp? | Holder hiện tại có private key của Client? |
| **DPoP** | Caller có thể ký proof bằng khóa ràng buộc với token và request? | XSS/malware không thể dùng khóa trong client? |
| **mTLS certificate-bound token** | Token khớp certificate client trong kết nối TLS? | Secret/key bị lộ hoặc proxy không bị cấu hình sai? |
| **RS object authorization** | Principal/service được quyền trên object/tenant cụ thể? | Không cần bảo vệ token/credential? |

### Sender-constrained token

Nếu threat model yêu cầu giảm lạm dụng token bị sao chép, có thể kết hợp:

- **DPoP (RFC 9449):** ràng buộc access token với public JWK thumbprint `cnf.jkt` và yêu cầu proof JWS có `htm`, `htu`, `iat`, `jti`, `ath`, nonce khi được yêu cầu.
- **mTLS-bound access token (RFC 8705):** ràng buộc token với certificate thumbprint `cnf["x5t#S256"]`; RS kiểm tra certificate thật của kết nối TLS.

**Client authentication bằng mTLS tại AS không tự bảo đảm access token đã được certificate-bound với RS.** AS phải phát đúng binding, RS phải enforce đúng chứng chỉ/proof. Dù vậy, attacker sử dụng được private key hoặc môi trường Client vẫn có thể tiếp tục lạm dụng quyền; cần kết hợp quản lý workload và authorization.

### Thu hồi có nhiều điểm

Khi một client secret lộ, đội vận hành cần xem xét **ít nhất ba đối tượng**:

1. **Client credential**: AS không được tiếp tục chấp nhận credential cũ khi đã thu hồi.
2. **Authorization grant/refresh token**: có thể cần revoke theo chính sách nếu tồn tại.
3. **Access token đã phát hành**: RS phải có cách nhận biết trạng thái nếu cần thu hồi sớm, hoặc chấp nhận giới hạn TTL theo rủi ro.

Không đồng nhất ba trạng thái này.

## 18. Ma trận kiểm thử Client secret protection

Giả sử `billing-worker` là confidential client được AS cho phép `client_credentials`, chỉ xin token `aud=billing-api` với `scope=billing:read` cho tenant A.

| Trường hợp | Kỳ vọng | Điều chứng minh |
|---|---|---|
| Client xác thực bằng secret đúng, grant/resource/scope hợp lệ | **AS có thể cấp token**. | Credential và policy cùng hợp lệ. |
| Caller chỉ biết `client_id`, không biết secret | **AS từ chối**, thường `invalid_client`. | ID không phải credential. |
| Caller đưa secret sai một ký tự | **AS từ chối**. | Secret phải khớp verifier. |
| Client dùng secret đã bị revoke | **AS từ chối** dù runtime còn lưu chuỗi cũ. | Credential lifecycle. |
| Client dùng secret hết hạn | **AS từ chối** theo policy. | Expiry enforcement. |
| SPA nhúng client secret vào JavaScript bundle | **Bị đánh giá sai kiến trúc**; không coi là confidential. | Secret public không bí mật. |
| Secret được đặt trong Git commit/CI log | **Phát hiện và coi như lộ**, rotate/điều tra. | Secret scanning và incident response. |
| Secret nằm trong Docker image layer | **Không đạt yêu cầu**; rebuild an toàn và rotate nếu đã lộ. | Supply chain protection. |
| Kubernetes Secret bị Base64-encode và commit công khai | **Không đạt yêu cầu**; Base64 không mã hóa. | Orchestrator hardening. |
| Workload A có quyền đọc secret của workload B | **Từ chối theo RBAC/secret policy**. | Least privilege của secret manager. |
| Client gửi secret qua HTTP plaintext | **Không chấp nhận thiết kế**. | TLS protection. |
| Client gửi secret trong query URL | **Không chấp nhận**. | Không lộ qua URL/log. |
| Token endpoint nhận đồng thời secret Basic và secret POST khác nhau | **Từ chối hoặc xử lý đúng profile**, không chọn tùy tiện. | Tránh credential confusion. |
| Secret đúng nhưng Client xin `payments:refund` ngoài policy | **AS không cấp scope đó**. | Client auth không thay authorization. |
| Secret đúng, xin token `aud=orders-api` ngoài registration | **AS từ chối hoặc không cấp resource đó**. | Audience limitation. |
| Trong rotation, v7 và v8 được cho phép tạm thời | **Cả hai chỉ hoạt động trong cửa sổ overlap đã định**. | Controlled rotation. |
| Đã hết overlap, worker tiếp tục dùng v7 | **AS từ chối**, cảnh báo workload chưa cập nhật. | Không giữ secret cũ mãi mãi. |
| v8 được cập nhật ở vault nhưng process vẫn giữ v7 trong env | **Phát hiện và redeploy/reload an toàn**. | Runtime secret refresh. |
| Attacker dùng credential đã lộ trước khi revoke | **Có nguy cơ được cấp token trong quyền client**. | Secret compromise impact. |
| Secret đã revoke nhưng JWT access token cũ còn hạn | **Có thể vẫn dùng** nếu RS chỉ verify offline. | Credential revoke khác token revoke. |
| Billing token gửi Orders API | **Orders từ chối**. | Audience validation. |
| Token `billing:read` dùng hoàn tiền | **RS từ chối**, thường 403. | Scope limitation. |
| Token đúng scope nhưng invoice thuộc tenant B | **RS từ chối**. | Tenant/object authorization. |
| Attacker có bearer token nhưng không biết client secret | **Vẫn có nguy cơ replay token**. | Client auth khác sender proof. |
| Access token DPoP-bound thiếu proof hoặc key không khớp | **RS từ chối**. | Enforce token binding. |
| Token endpoint tạm lỗi, ứng dụng fallback sang static admin token | **Không được phép**, phải fail closed. | Không bypass do availability. |
| Log scrubbed nhưng APM vẫn ghi Basic Authorization | **Không đạt**; sửa cả telemetry pipeline. | Redaction end-to-end. |
| Secret manager unavailable và ứng dụng không có credential hợp lệ | **Không tự nhận dạng client thành công**. | Fail closed. |

Kiểm thử cần chạy qua **token endpoint, secret manager/runtime và Resource Server**; chỉ kiểm tra mã Java có gọi `setBearerAuth` **không chứng minh client secret được bảo vệ**, cũng không chứng minh quyền truy cập đúng audience/tenant.

## 19. Tình huống suy luận

**Tình huống A — Client secret trong SPA.** Một nhóm muốn tránh OAuth login nên đưa `client_secret` vào bundle JavaScript để gọi `grant_type=client_credentials`. Điều gì sai?

**Giải thích:** Bundle JavaScript là môi trường công khai; người dùng hoặc attacker có thể trích xuất secret và xin token service. SPA là public client trong mô hình đó; dùng Authorization Code + PKCE cho quyền user hoặc BFF/backend giữ quyền service theo kiến trúc phù hợp.

**Tình huống B — Secret được Base64.** Một Docker image chứa `CLIENT_SECRET_BASE64` và tại runtime giải mã trước khi gọi AS. Có được coi là bảo vệ secret?

**Giải thích:** Không. Base64 chỉ mã hóa biểu diễn, không bảo mật. Người có image/khả năng xem cấu hình vẫn khôi phục được secret. Cần lấy secret từ kênh runtime bảo vệ, không bake vào image.

**Tình huống C — Đúng secret, sai scope.** Billing Worker xác thực với AS thành công nhưng xin `payments:refund` dù chỉ được `billing:read`. AS nên cấp không?

**Giải thích:** Không. Xác thực client chỉ chứng minh credential, không cho phép vượt grant/scope/tenant policy.

**Tình huống D — Rotate secret nhưng token vẫn chạy.** Secret v7 đã bị AS thu hồi; một JWT access token phát trước đó vẫn còn hạn 10 phút và RS kiểm tra offline. Token còn được dùng không?

**Giải thích:** Có thể. Thay credential chặn xin token mới bằng v7, không tự vô hiệu access token đã cấp. Cần TTL hoặc cơ chế thu hồi/trạng thái ở RS nếu yêu cầu.

**Tình huống E — Two-version rotation.** Một hệ thống có 20 worker instance; AS cho v7/v8 cùng hoạt động trong thời gian ngắn. Đội triển khai đã chuyển 19 máy sang v8, còn một máy dùng v7. Có nên revoke v7 ngay?

**Giải thích:** Cần quyết định theo deadline, rủi ro và mục tiêu availability; quan sát credential version để cập nhật máy cuối hoặc chấp nhận máy đó lỗi an toàn sau khi revoke. **Không kéo dài overlap vô hạn**, cũng không tự bật bypass client authentication.

**Tình huống F — Password trong Basic header.** Developer thấy header `Authorization: Basic ...` đã là Base64 nên cho rằng an toàn qua HTTP. Đúng không?

**Giải thích:** Sai. Base64 đảo ngược được; credential phải đi qua HTTPS/TLS được xác minh và không bị ghi vào log.

**Tình huống G — Dùng secret làm Bearer token.** Một client gọi Billing API với `Authorization: Bearer <CLIENT_SECRET>`. RS có nên chấp nhận?

**Giải thích:** Không. Client secret dành cho client authentication tại AS; RS phải nhận access token dành cho Billing, đúng issuer, audience, scope và quyền object.

**Tình huống H — Secret ở vault nhưng logger in ra.** App lấy secret từ vault đúng cách, sau đó bật HTTP client debug log in cả Basic Authorization. Có an toàn không?

**Giải thích:** Không. Secret manager bảo vệ chỗ lưu, nhưng logging phá bảo mật khi sử dụng. Cần redaction ở application/HTTP client/proxy/APM, đánh giá secret đã lộ và rotate khi phù hợp.

**Tình huống I — mTLS thay shared secret.** Một team chuyển từ client_secret_basic sang mTLS client authentication và kết luận không còn cần quản lý credential. Có đúng?

**Giải thích:** Không. Client certificate/private key cũng phải lưu, giới hạn quyền, rotate và xử lý khi lộ. Ngoài ra, mTLS client auth ở AS không tự tạo mTLS-bound access token ở RS.

**Tình huống J — One secret for all services.** Mười microservices dùng chung `platform-client-secret` với `scope=admin` để giảm cấu hình. Nguy cơ?

**Giải thích:** Một service bị chiếm có thể làm lộ quyền chung của nhiều service, gây khó audit/thu hồi riêng. Nên tách client registration, credential và scope/audience theo nhiệm vụ.

**Tình huống K — Tenant do caller khai.** Service có `billing:read` cho tenant A, nhưng caller gửi `X-Tenant-Id: tenant-b`. Được lấy hóa đơn tenant B không?

**Giải thích:** Không nếu thiếu quyền tenant B. Header là đầu vào không tin cậy; RS phải kiểm tra entitlement từ nguồn tin cậy và dữ liệu invoice thật.

**Tình huống L — AS rate limit gây 503.** Token endpoint có sự cố; worker định thử anonymous API call hoặc bỏ token validator tạm. Nên làm gì?

**Giải thích:** Không bypass. Sử dụng cache token hợp lệ theo policy nếu còn hạn, retry/backoff có giới hạn, circuit breaker và báo lỗi khi không thể xác thực. Availability không là lý do bỏ kiểm tra danh tính.

## Checklist triển khai Client secret protection

1. **Xác định client type:** chỉ đặt shared client secret trong confidential backend có khả năng giữ credential; SPA/native không giữ bí mật chung đáng tin.
2. **Áp dụng least privilege:** một client ID/credential cho đúng workload; giới hạn grant types, resource/audience, scope và tenant.
3. **Tạo secret mạnh:** CSPRNG, entropy cao, riêng từng client; không đoán từ ID/timestamp, không dùng lại trên nhiều service.
4. **Cấp và lưu an toàn:** secret manager/vault hoặc hệ thống tương đương, RBAC, audit, mã hóa at rest, hạn chế người có quyền đọc/sử dụng.
5. **Không đưa secret vào source/artifact:** Git, container image/layer, CI test report, Helm manifests công khai hoặc tài liệu vận hành.
6. **Kiểm soát runtime:** workload identity, mount/config bảo vệ, quyền file/process, hạn chế dump/debug và hiểu hành vi refresh khi rotate.
7. **Client authentication đúng chuẩn:** HTTPS token endpoint, `client_secret_basic` hoặc method đăng ký, không gửi secret trong query/redirect hoặc nhiều method mâu thuẫn.
8. **Redact end-to-end:** HTTP client, application, gateway, APM, crash dump, backup và support; không in Basic/secret/token.
9. **AS enforce credential lifecycle:** active/expiry/version/revocation, rate limits, chống credential confusion, không trả raw secret khi đọc registration.
10. **Rotation có kế hoạch:** tạo v mới, chuyển runtime, xác minh tất cả instance, kết thúc overlap và revoke v cũ; có phương án nếu AS chỉ hỗ trợ một active secret.
11. **Incident playbook:** coi commit/log lộ là compromise, rotate/revoke, điều tra token đã cấp, đánh giá access/refresh token, dọn bản sao và sửa nguyên nhân.
12. **Không nhầm token lifecycle:** revoke client secret khác revoke grant, refresh token và access token; xử lý RS state/TTL theo yêu cầu.
13. **Bảo vệ access token:** issuer, audience, scope, exp/nbf, loại token, DPoP/mTLS-bound nếu cần; RS vẫn phân quyền trên tenant/object.
14. **Kiểm thử phủ định:** secret sai/cũ/hết hạn, rate limit, lộ CI/image/log, rotation nhiều instance, audience/scope sai, tenant chéo, AS downtime và replay token.

## Ghi nhớ

**Client secret protection là bảo vệ credential dùng để confidential OAuth Client xác thực với Authorization Server**, không phải bảo vệ một “token” có thể gửi trực tiếp tới Resource Server. `client_id` công khai; secret phải **đủ entropy, được giữ ngoài mã nguồn, chỉ phân phối cho workload cần dùng qua secret manager/kênh bảo vệ và chỉ gửi tới token endpoint qua HTTPS**. Cần quản lý **quyền tối thiểu, logging redaction, vòng đời/rotation và ứng phó sự cố**. Với frontend công khai, **không nhúng client secret**; khi được hỗ trợ, cân nhắc private-key JWT, mTLS hoặc workload federation thay secret tĩnh. Nếu secret bị lộ, attacker có thể cố **xin access token mới**; nhưng **thay secret không tự vô hiệu hóa mọi access token đã phát hành**. AS vẫn phải giới hạn grant/resource/scope; RS vẫn phải xác minh token, audience, scope và quyền trên từng object/tenant. Bảo vệ secret, token transport, token storage và chống bearer replay là các lớp kiểm soát bổ sung, không thay thế nhau.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework (Client Authentication và Client Credentials)](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [Spring Security Reference — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
