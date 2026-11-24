# Service account và machine identity

## 1. Vì sao dịch vụ cần một danh tính riêng?

Trong hệ thống phân tán, không chỉ con người mới truy cập tài nguyên được bảo vệ. Một tiến trình xử lý đơn hàng gọi API kho, một job chạy mỗi đêm ghi báo cáo, một workload Kubernetes truy cập cơ sở dữ liệu hoặc một thiết bị IoT gửi dữ liệu đều cần trả lời:

1. **Ai đang gọi?** Đó là tiến trình, dịch vụ, workload hay thiết bị nào?
2. **Bên gọi chứng minh danh tính bằng gì?** Secret, khóa riêng, chứng chỉ, token gắn với workload hay cơ chế khác?
3. **Được quyền làm gì?** Truy cập API/tài nguyên nào, scope nào, tenant nào, trong bao lâu?
4. **Danh tính và quyền sẽ bị thu hồi ra sao?** Khi workload bị xóa, credential lộ hoặc nhiệm vụ kết thúc, hệ thống ngăn việc sử dụng tiếp như thế nào?

Các câu hỏi này thuộc phần **Authentication** của nền tảng token security. Trong OAuth 2.0/OIDC, một machine identity có thể được authorization server (AS) xác thực rồi cấp **access token** để gọi resource server. Khả năng đăng nhập của máy và quyền truy cập mà token thể hiện cần được quản lý tách biệt.

**Tình huống xuyên suốt:** Dịch vụ `orders-worker` cần đọc tồn kho từ `inventory-api`. Yêu cầu đúng là token dành cho `inventory-api`, có quyền `inventory.read`, thời hạn ngắn và gắn với danh tính `orders-worker`. Không nên dùng tài khoản cá nhân của nhân viên hay access token của một người dùng ngẫu nhiên để chạy tác vụ tự động.

## 2. Phân biệt service account, machine identity và các loại credential

### 2.1. Các thuật ngữ dễ nhầm

| Thuật ngữ | Ý nghĩa | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| **Machine identity / workload identity** | Danh tính phi con người của phần mềm, tiến trình, thiết bị hoặc workload | `spiffe://prod.example/ns/orders/sa/orders-worker` | Danh tính là chủ thể được tin; không nhất thiết là một tài khoản trong cơ sở dữ liệu |
| **Service account** | Bản ghi/tài khoản được hệ thống dùng để biểu diễn một dịch vụ hoặc workload | `orders-worker` trong IAM/Kubernetes | Một cách cụ thể để định danh máy; ý nghĩa và khả năng khác nhau theo nền tảng |
| **Principal** | Chủ thể được chính sách xác thực và phân quyền đánh giá | `client_id=orders-worker` | Có thể là user, service, role hoặc workload |
| **Credential** | Bằng chứng để chứng minh danh tính | Client secret, private key, certificate, workload assertion | Phải được bảo vệ và xoay vòng |
| **Access token** | Quyền truy cập được cấp cho client để gọi resource server | Bearer JWT hoặc opaque token | Phải đúng audience, scope, thời hạn và chính sách |
| **ID token** | Thông tin xác thực về end-user cho OIDC client | OIDC JWT với `aud` là client ID | Không dùng thay access token để gọi API |
| **Refresh token** | Credential để xin access token mới theo grant được hỗ trợ | Chuỗi cấp cùng một số luồng OAuth | Thông thường không cần và không được cấp trong client credentials flow |

**Machine identity không đồng nghĩa với access token.** Danh tính `orders-worker` có thể tồn tại lâu dài theo vòng đời dịch vụ, trong khi mỗi access token đại diện cho quyền ngắn hạn của dịch vụ đó đối với **một resource cụ thể**. Một service account cũng có thể sở hữu nhiều loại credential; sự hiện diện của credential không tự chứng minh quyền gọi mọi API.

### 2.2. Người dùng và máy khác nhau ở điểm nào?

| Khía cạnh | Danh tính con người | Danh tính máy |
| --- | --- | --- |
| Chủ thể | Nhân viên, khách hàng | Dịch vụ, cron job, container, thiết bị |
| Cách xác thực thường gặp | Mật khẩu, passkey, MFA, đăng nhập liên kết | Private key, mTLS, client secret, workload federation |
| OAuth flow hay gặp | Authorization Code + PKCE, OIDC login | Client Credentials; JWT assertion; token exchange theo kiến trúc |
| Vòng đời | Tạo/ngừng tài khoản, phiên đăng nhập của người dùng | Triển khai, scale, thay instance, rotate credential, xóa workload |
| Quyền | Theo vai trò và ngữ cảnh người dùng | Theo nhiệm vụ và môi trường của service |
| Rủi ro nổi bật | Chiếm tài khoản và phiên | Lộ secret/token, giả mạo workload, quyền quá rộng, identity tồn tại sau khi service ngừng |

Một dịch vụ **có thể thực hiện yêu cầu thay mặt người dùng**. Khi đó cần mô hình ủy quyền/chuyển tiếp danh tính phù hợp; không được mặc định rằng token cấp cho chính dịch vụ cũng bao hàm quyền của mọi người dùng. Phần này sẽ được phân biệt rõ ở mục 9.

## 3. Chuỗi tin cậy khi máy gọi API

Danh tính máy đi qua hai ranh giới: **xác thực client ở authorization server** và **xác minh access token ở resource server**.

~~~mermaid
sequenceDiagram
    autonumber
    participant W as orders-worker (machine identity)
    participant AS as Authorization Server
    participant API as inventory-api (resource server)
    W->>AS: Chứng minh danh tính (secret / key / mTLS / assertion)
    AS->>AS: Xác thực client và chính sách cấp quyền
    AS-->>W: Access token (aud=inventory-api, scope=inventory.read)
    W->>API: GET /inventory + Bearer access token
    API->>API: Tin issuer/JWKS hoặc introspection endpoint đã cấu hình
    API->>API: Kiểm tra aud, exp, scope, tenant và quyền tài nguyên
    API-->>W: 200 hoặc từ chối 401/403
~~~

Những thành phần cần được phân biệt:

- **Issuer/AS tin cậy:** Nguồn có thẩm quyền phát hành token mà resource server được cấu hình để chấp nhận.
- **Credential chứng minh machine identity:** Dùng ở bước xin token; ví dụ private key của `orders-worker`. Không tự động mang credential này sang resource server.
- **Access token:** Kết quả cấp quyền ngắn hạn, dùng khi gọi `inventory-api`. Resource server phải kiểm tra token dành cho mình, ngay cả khi chữ ký hợp lệ.
- **Chính sách phân quyền của API:** `inventory.read` có thể cho phép đọc tồn kho; nó không mặc nhiên cho phép thay đổi số lượng hoặc truy cập mọi tenant.

Resource server không thể dựa vào việc client tự khai `client_id` trong HTTP header. Nó phải nhận danh tính/quyền đã được AS xác minh qua token tin cậy hoặc một cơ chế xác thực trực tiếp được thiết kế riêng.

## 4. Máy chứng minh danh tính bằng cách nào?

### 4.1. Shared secret / OAuth client secret

Client được đăng ký tại AS với `client_id` và `client_secret`. Khi xin token, client cung cấp secret để AS xác thực.

**Ưu điểm:** dễ tích hợp cho dịch vụ máy chủ truyền thống. **Nhược điểm:** một bản sao secret bị lộ có thể bị dùng để giả mạo client; việc phân phối và xoay vòng secret khó khi số instance lớn. Secret cần được lưu trong secret manager hoặc cơ chế quản lý bí mật phù hợp, truyền qua TLS, không đưa vào source code, image, log hay file cấu hình công khai.

Secret không phải access token. Không truyền `client_secret` đến `inventory-api` thay cho `Authorization: Bearer ...`.

### 4.2. Khóa riêng và JWT client assertion

Thay cho shared secret, client có thể ký một **client assertion** bằng private key của mình, còn AS kiểm tra bằng public key được đăng ký. Ví dụ OAuth `private_key_jwt` (theo cơ chế JWT client authentication) đưa assertion ngắn hạn tới token endpoint.

Một assertion điển hình có các claims như:

~~~json
{
  "iss": "orders-worker",
  "sub": "orders-worker",
  "aud": "https://auth.example.test/oauth2/token",
  "iat": 1795400000,
  "exp": 1795400060,
  "jti": "unique-request-id"
}
~~~

Giá trị thời gian và địa chỉ ở trên chỉ nhằm minh họa cấu trúc. Ở cơ chế này `aud` của **client assertion** thường là token endpoint/định danh AS theo hợp đồng, **khác** với `aud` của **access token** được cấp cho `inventory-api`. Assertion chứng minh client kiểm soát private key; AS vẫn quyết định cấp quyền và scope nào. Cần xác minh chữ ký, issuer/subject, audience, thời gian và chống sử dụng lại assertion theo chính sách AS. Private key phải được bảo vệ bằng KMS/HSM hoặc secret store thích hợp khi có thể.

### 4.3. Mutual TLS (mTLS)

Client trình chứng chỉ trong bắt tay TLS; AS (hoặc API được cấu hình xác thực trực tiếp) xác minh chuỗi chứng chỉ và ánh xạ danh tính. OAuth 2.0 có cơ chế xác thực client bằng mTLS và access token ràng buộc với chứng chỉ (RFC 8705).

Với **certificate-bound access token**, chỉ người cầm token là chưa đủ: bên gọi còn phải chứng minh quyền sở hữu private key tương ứng với chứng chỉ. Đây là cách giảm rủi ro token bearer bị sao chép, nhưng tất cả thành phần cần hỗ trợ xác minh ràng buộc này.

### 4.4. Workload identity và federation

Nhiều nền tảng có thể chứng thực một workload đang chạy bằng bằng chứng ngắn hạn do nền tảng quản lý:

- Kubernetes service account token được chiếu vào Pod theo scope/audience và thời hạn.
- Identity của cloud workload được cấp thông qua cơ chế của nhà cung cấp và/hoặc token exchange.
- SPIFFE/SPIRE cấp danh tính workload với X.509-SVID hoặc JWT-SVID cho môi trường hỗ trợ.

Một **Security Token Service (STS)** hoặc AS có thể tin issuer của nền tảng, xác minh assertion từ workload và **đổi lấy access token đích** với audience/scope phù hợp (mô hình token exchange RFC 8693 khi được hỗ trợ). Cách này giảm nhu cầu đưa secret dài hạn vào container, nhưng phải cấu hình chặt quan hệ tin cậy: issuer nào, namespace/service account nào, audience nào và workload nào được impersonate role nào.

**Điểm then chốt:** Không phải token nào mang nhãn “service account” cũng là OAuth access token mà mọi API phải nhận. Token chỉ có ý nghĩa đối với **bên xác minh đã được thiết lập tin cậy** và mục đích/audience tương ứng.

## 5. OAuth 2.0 Client Credentials: luồng máy gọi máy

Grant `client_credentials` của OAuth 2.0 (RFC 6749, `4.4) thường được dùng khi **confidential client** truy cập tài nguyên bằng quyền của chính client hoặc quyền đã được thỏa thuận trước, không cần người dùng tương tác.

### 5.1. Từng bước

1. Đăng ký `orders-worker` làm OAuth client tại AS, xác định cơ chế xác thực client và quyền được cấp.
2. Khi cần làm việc, client xác thực với token endpoint của AS và xin scope `inventory.read`, có thể kèm resource indicator/audience theo cách AS hỗ trợ.
3. AS kiểm tra credential cùng chính sách, sau đó phát hành access token ngắn hạn cho `inventory-api`.
4. Client gửi access token đến API bằng header `Authorization: Bearer <token>` qua HTTPS.
5. API xác minh token (JWT/JWKS hoặc opaque/introspection), audience, scope và quyền tài nguyên.
6. Khi token hết hạn, client xác thực lại với AS để xin access token mới. Theo RFC 6749, **refresh token không nên được cấp cho client credentials grant**.

Ví dụ request cấp token bằng HTTP Basic client authentication:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <base64-cua-client-id-va-client-secret-da-ma-hoa-dung-quy-tac>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
~~~

HTTP Basic chỉ mã hóa biểu diễn thông tin; **Base64 không bảo mật secret**. Giao tiếp phải dùng HTTPS. Đây là ví dụ request: tên endpoint, cơ chế chọn audience và danh sách scope phụ thuộc AS thực tế.

Phản hồi có thể là:

~~~json
{
  "access_token": "<chuoi-access-token>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory.read"
}
~~~

`expires_in=300` nghĩa là token có thời hạn 300 giây tính từ khi được cấp. Chuỗi access token có thể là JWT hoặc opaque; **client không được tự suy đoán quyền từ hình thức chuỗi**. Một số AS trả thêm metadata, một số AS dùng resource indicator theo RFC 8707 để nhắm token tới API.

API được gọi bằng:

~~~http
GET /v1/inventory/sku-123 HTTP/1.1
Host: inventory.example.test
Authorization: Bearer <access-token>
~~~

Không gửi client secret, private key hay refresh token trong request này. Một access token dành cho `inventory-api` không được tái sử dụng tùy ý tại `billing-api`.

### 5.2. Những điều client credentials **không** chứng minh

- Token không tự có “người dùng hiện tại”; `sub` có thể biểu diễn client/service theo profile của AS, hoặc có ngữ nghĩa khác được AS quy định.
- Không có bước người dùng đồng ý trên mỗi request. Vì vậy quyền của service account phải được giới hạn ngay từ cấu hình IAM/AS.
- Không phải OIDC ID token để đăng nhập người dùng. **OIDC ≠ mọi OAuth token đều là ID token**.
- Không tự động cho phép thao tác nhạy cảm với mọi bản ghi. API vẫn phải kiểm tra policy, tenant và quyền trên tài nguyên.

## 6. Resource server xác minh machine access token

Giả sử AS đã cấp JWT access token sau:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "orders-worker",
  "client_id": "orders-worker",
  "aud": ["inventory-api"],
  "scope": "inventory.read",
  "iat": 1795400000,
  "exp": 1795400300,
  "jti": "token-unique-id"
}
~~~

Payload chỉ minh họa claims; một payload JSON thuần **không phải token hợp lệ** nếu chưa được ký và xác minh theo profile. Resource server không lấy `sub`, `client_id`, `scope` hoặc `aud` từ JSON do client gửi ngoài kênh token tin cậy.

Đối với **JWT access token**, API cần:

1. Chỉ tin issuer `https://auth.example.test` đã cấu hình; lấy public keys qua JWKS được issuer đó công bố và xác minh thuật toán/chữ ký bằng thư viện uy tín.
2. Bắt buộc `iss` khớp issuer, `aud` chứa `inventory-api`, `exp` chưa hết hạn, `nbf`/`iat` và token profile hợp lệ khi áp dụng. Không xem `kid` hay URL `jku` trong token là nguồn tin cậy độc lập.
3. Kiểm tra đây là **access token** dành cho resource server, không nhầm ID token của OIDC client hoặc JWT client assertion với access token.
4. Đọc `scope` theo profile/hợp đồng của AS và yêu cầu `inventory.read` cho endpoint đọc; áp dụng thêm tenant, account và policy của hệ thống.

Với **opaque access token**, API gọi **introspection endpoint được cấu hình của AS có thẩm quyền** qua TLS với credential của resource server, kiểm tra `active` cùng ràng buộc resource/audience/scope và các điều kiện chính sách. `active: true` không tự động cho phép đọc mọi tài nguyên. Khi introspection lỗi hoặc không xác minh được, API phải **fail closed**.

**Phân biệt hai quyết định:**

| Kiểm tra | Ví dụ câu hỏi | Nếu không đạt |
| --- | --- | --- |
| Authentication/validation | Token có do AS tin cậy phát hành, còn hiệu lực và dành cho API này không? | Từ chối token, thường HTTP 401 |
| Authorization | Machine identity này có scope và quyền đọc SKU của tenant hiện tại không? | Từ chối thao tác, thường HTTP 403 |

Quy ước status HTTP còn phụ thuộc nguyên nhân và RFC 6750; khi lỗi hạ tầng introspection, cần phân biệt lỗi dịch vụ với token bị từ chối để giám sát, nhưng tuyệt đối không cấp quyền mặc định.

## 7. Ví dụ Kubernetes service account và workload token

Một Kubernetes **ServiceAccount** là danh tính cho các tiến trình chạy trong Pod khi tương tác với Kubernetes API và các tích hợp tin issuer của Kubernetes. Có thể khai báo:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-worker
  namespace: orders
automountServiceAccountToken: false
~~~

`automountServiceAccountToken: false` hạn chế tự động mount token mặc định; với workload cần token mục đích cụ thể, có thể yêu cầu **projected service account token**:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-worker
  namespace: orders
spec:
  serviceAccountName: orders-worker
  automountServiceAccountToken: false
  containers:
    - name: worker
      image: registry.example.test/orders-worker:1.0
      volumeMounts:
        - name: workload-identity
          mountPath: /var/run/workload-identity
          readOnly: true
  volumes:
    - name: workload-identity
      projected:
        sources:
          - serviceAccountToken:
              path: token
              audience: workload-federation
              expirationSeconds: 3600
~~~

Đây là ví dụ cấu hình minh họa; `workload-federation` phải khớp audience mà **bên nhận assertion** (ví dụ STS) đã cấu hình. Token nằm tại `/var/run/workload-identity/token` bên trong container, và kubelet có thể làm mới projected token trước khi hết hạn. Ứng dụng/SDK phải đọc lại token khi cần, tránh giữ bản sao token cũ vô thời hạn.

Luồng dùng token này để gọi API ngoài Kubernetes:

~~~mermaid
flowchart LR
    P["Pod: orders-worker"] -->|"Projected SA assertion"| STS["STS / Authorization Server"]
    STS -->|"Xác minh issuer + namespace/SA + aud"| POLICY["Workload federation policy"]
    POLICY -->|"Cấp access token aud=inventory-api"| P
    P -->|"Bearer access token"| API["inventory-api"]
    API -->|"JWT validation hoặc introspection"| AS["Nguồn token đã được tin"]
~~~

**Tránh hiểu nhầm:** Service account token có audience dành cho Kubernetes API hoặc STS **không mặc nhiên được** `inventory-api` chấp nhận. API chỉ nhận token trực tiếp nếu đã **chủ động tin issuer, profile, audience và chính sách** của loại token đó. Một ứng dụng có thể chỉ cần token exchange để nhận access token chuẩn của AS mà API đã tin.

Không tạo các service account token Secret dài hạn chỉ vì “dễ sử dụng”; ưu tiên TokenRequest/projected short-lived tokens khi nền tảng và tích hợp hỗ trợ. Một ServiceAccount không tự được quyền quản trị Kubernetes: quyền Kubernetes API đến từ RBAC binding tương ứng.

### 7.1. Vai trò của SPIFFE/SPIRE

Trong hệ thống mesh hoặc môi trường đa nền tảng, SPIFFE ID như `spiffe://prod.example/ns/orders/sa/orders-worker` có thể làm định danh workload. SPIRE hoặc một hệ thống tương đương xác thực workload và cấp SVID theo cơ chế thích hợp. Hai dạng thường gặp là **X.509-SVID** cho mTLS và **JWT-SVID** để trình bằng chứng JWT cho bên nhận có thỏa thuận tin cậy.

Không xem JWT-SVID là OAuth access token một cách tự động; nếu dùng để gọi API OAuth, hệ thống cần ánh xạ và cấp token theo mô hình đã thiết kế. Bên xác minh phải kiểm tra trust domain, audience, thời hạn và bằng chứng đúng profile.

## 8. Java/Spring: cấu hình client credentials cho service

Trong Spring Boot/Spring Security, ứng dụng đóng vai trò **OAuth2 client** để tự xin access token trước khi gọi API khác. Ví dụ cấu hình dưới đây giả sử AS đã đăng ký client `orders-worker` và cấp scope `inventory.read`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-as:
            token-uri: https://auth.example.test/oauth2/token
        registration:
          inventory:
            provider: company-as
            client-id: orders-worker
            client-secret: ${ORDERS_WORKER_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: inventory.read
~~~

Biến `ORDERS_WORKER_CLIENT_SECRET` là **ví dụ cách tham chiếu secret**, không nên hardcode giá trị thật. Secret manager, cơ chế inject secret và phân quyền truy cập secret phải được cấu hình phù hợp môi trường. Khi triển khai federation/mTLS/private_key_jwt, sử dụng client authentication phù hợp thay cho shared secret.

Ví dụ Java sử dụng authorized client manager để lấy/cập nhật access token theo client credentials:

~~~java
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService clients) {

    var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
            registrations, clients);

    manager.setAuthorizedClientProvider(
            OAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build());

    return manager;
}

// Trong service gọi inventory-api:
OAuth2AuthorizeRequest authRequest = OAuth2AuthorizeRequest
        .withClientRegistrationId("inventory")
        .principal("orders-worker")
        .build();

OAuth2AuthorizedClient client = authorizedClientManager.authorize(authRequest);
if (client == null || client.getAccessToken() == null) {
    throw new IllegalStateException("Khong lay duoc access token");
}

String accessToken = client.getAccessToken().getTokenValue();
String inventory = restClient.get()
        .uri("https://inventory.example.test/v1/inventory/sku-123")
        .headers(headers -> headers.setBearerAuth(accessToken))
        .retrieve()
        .body(String.class);
~~~

Đoạn code minh họa cách dùng trong bean/lớp ứng dụng, giả định đã cấu hình `restClient` và import các lớp Spring Security cần thiết. `principal("orders-worker")` là khóa ngữ cảnh mà client manager dùng để quản lý authorized client; nó **không tự xác thực hoặc tạo danh tính**. AS xác thực client từ cơ chế cấu hình token endpoint. Cần lưu ý đồng bộ refresh/retry khi nhiều request song song và chỉ lưu access token trong bộ nhớ/cache được bảo vệ theo chính sách.

Ở phía `inventory-api`, Spring Security resource server cần xác thực bearer token bằng `issuer-uri`/JWKS hoặc introspection URI đã tin. Phải thêm validation audience `inventory-api`, kiểm tra scope và quy tắc nghiệp vụ. Cấu hình OAuth2 client ở `orders-worker` **không thay thế** việc xác minh token ở API đích.

## 9. Service identity khác với “thay mặt người dùng”

Xét ba tình huống:

| Tình huống | Chủ thể cần phân quyền | Cách suy nghĩ |
| --- | --- | --- |
| Job mỗi đêm tổng hợp tồn kho | Chính service/job | Client credentials với scope nghiệp vụ phù hợp |
| User Alice bấm “xem đơn hàng”, frontend gọi backend | Alice và client đang thao tác | User-delegated access token, kiểm tra `sub` và quyền của Alice |
| Backend A gọi backend B để hoàn thành tác vụ của Alice | Có thể cần cả Alice lẫn identity của A | Dùng mô hình delegation/token exchange được AS và API hỗ trợ; giữ thông tin actor, subject và audience khi cần |

**Không được lấy service token có quyền lớn để bỏ qua quyền của Alice.** Nếu backend nhận request từ Alice rồi dùng service token để tải đơn hàng, backend vẫn phải kiểm tra Alice có quyền với đơn hàng đó trước khi thao tác, hoặc sử dụng một mô hình ủy quyền chuẩn có thể kiểm chứng ở backend B.

Ngược lại, không nên dùng access token của nhân viên hệ thống để chạy batch job lâu dài. Khi nhân viên nghỉ việc, thay MFA hoặc hết phiên, hệ thống vận hành sẽ hỏng; nghiêm trọng hơn là dấu vết audit bị gán cho cá nhân thay vì service thực sự.

## 10. Vòng đời của machine identity và token

Một thiết kế an toàn quản lý cả **identity lâu dài** và **credential/token ngắn hạn**:

| Giai đoạn | Hành động | Điểm kiểm soát |
| --- | --- | --- |
| 1. Đăng ký | Tạo identity riêng cho `orders-worker` theo môi trường/tenant | Owner, mục đích, nhãn môi trường, người chịu trách nhiệm |
| 2. Gán quyền | Cho phép scope `inventory.read` và audience `inventory-api` | Least privilege, không dùng wildcard nếu không cần |
| 3. Bootstrap | Cấp secret/khóa/chứng chỉ hoặc tạo quan hệ tin cậy federation | Chỉ workload đúng mới lấy được credential |
| 4. Xác thực | Workload chứng minh danh tính với AS/STS | Kiểm tra credential, issuer, assertion, mTLS hoặc attestation theo cơ chế |
| 5. Cấp token | AS phát hành access token ngắn hạn | Ràng buộc audience/scope, TTL, chủ thể, sender khi hỗ trợ |
| 6. Sử dụng | Client gửi token đến đúng API | TLS; API xác minh issuer, trạng thái, audience và authorization |
| 7. Gia hạn | Xin token mới khi gần hết hạn | Re-authenticate/re-exchange; cache có kiểm soát; không giả định refresh token |
| 8. Xoay vòng/thu hồi | Rotate secret/key, revoke credential và token khi hỗ trợ | Kịch bản khẩn cấp, kiểm tra JWKS/introspection cache |
| 9. Ngừng sử dụng | Xóa workload, hủy binding và xóa identity/credential không còn cần | Kiểm toán identity mồ côi, hủy quyền tại AS/IAM |

**Thu hồi credential ≠ thu hồi access token đã phát hành.** Nếu một secret bị lộ rồi được rotate, token JWT đã cấp trước đó có thể còn hợp lệ tới `exp` nếu API xác minh ngoại tuyến và không có denylist/introspection bổ sung. Cần hiểu rõ giới hạn của từng AS và resource server.

Với opaque token, introspection có thể phản ánh trạng thái thu hồi sớm hơn, nhưng cache phản hồi `active: true` tạo một cửa sổ chấp nhận token đã bị rút. Với JWT, chọn TTL ngắn và chiến lược key rotation/denylist tùy mức rủi ro. Với credential dạng chứng chỉ, rotation còn liên quan đến trust anchor và hiệu lực chứng chỉ.

### 10.1. Thời hạn và nơi lưu

- **Client secret/private key:** lưu trong thành phần bí mật chuyên dụng, giới hạn quyền đọc, audit truy cập và rotate theo lịch/biến cố. Với private key, tránh xuất khóa ra khỏi KMS/HSM nếu kiến trúc cho phép.
- **Access token:** hạn chế lưu lâu, ưu tiên bộ nhớ hoặc cache bảo vệ, không đưa vào URL, log, crash report, metrics label hoặc hệ thống theo dõi có nhiều người truy cập.
- **Projected workload token:** chỉ mount vào container cần dùng, giữ audience hẹp và hỗ trợ đọc lại khi nền tảng rotate.
- **Backup/CI/CD:** không đóng gói secret vào Docker image, artifact hay repository; bảo vệ cả pipeline và quyền deploy vì chúng có thể mint hoặc truy cập token.

## 11. Mối đe dọa thực tế và phòng thủ

| Mối đe dọa | Điều có thể xảy ra | Biện pháp |
| --- | --- | --- |
| **Secret bị commit vào Git** | Bên khác giả mạo client để xin token | Secret scanning, revoke/rotate ngay, secret manager, audit những token đã cấp |
| **Access token trong log** | Bên đọc log dùng token như bearer | Redact header, tránh log token, TTL ngắn, audience hẹp, giám sát |
| **Quyền service account quá rộng** | Compromise một job dẫn đến thao tác chéo hệ thống | Tách identity cho từng service/môi trường, scope/role tối thiểu |
| **Lạm dụng metadata endpoint** | SSRF hoặc process bị chiếm lấy credential của workload/cloud | Chặn SSRF, hạn chế egress, bảo vệ metadata service, ràng buộc workload identity |
| **Giả mạo workload assertion** | Kẻ khác đổi assertion lấy token quyền cao | Kiểm tra issuer, chữ ký, audience, namespace, service account, subject và binding |
| **Dùng token sai audience** | Token từ API A bị đem gọi API B | API B kiểm tra audience của chính nó, không chỉ kiểm tra chữ ký |
| **Phát lại bearer token** | Token bị chép có thể dùng lại tới khi hết hạn | mTLS/DPoP sender constraint khi hỗ trợ; TTL ngắn, TLS, giảm lộ token |
| **Identity mồ côi** | Tác vụ đã xóa nhưng secret/role vẫn hiệu lực | Kiểm kê định kỳ, tự động deprovision, hết hạn credential |
| **Xác minh chữ ký không gắn issuer** | Token tự ký được chấp nhận vì khóa lấy từ URL trong token | JWKS/issuer allowlist, kiểm tra `alg`, `iss`, `aud` và profile |
| **Cache trạng thái quá lâu** | Token đã revoke vẫn được API dùng | TTL cache theo mức rủi ro, không vượt `exp`, hỗ trợ invalidation khi cần |

**Bearer token là quyền theo người cầm token**: không có gì trong một bearer token tự động chứng minh người gửi hiện tại chính là workload đã được cấp token. DPoP (RFC 9449) hoặc certificate-bound token (RFC 8705), khi được tích hợp và xác minh đúng, giúp giảm khả năng sử dụng token đánh cắp bằng cách ràng buộc token với khóa/chứng chỉ.

Một trường `jti` độc nhất trong JWT hoặc access token **không tự chống replay**. Để phát hiện tái sử dụng, bên xác minh phải thực sự lưu trạng thái/áp dụng chính sách replay, hoặc dùng một cơ chế proof-of-possession thích hợp.

## 12. Thiết kế theo ba kịch bản

### Kịch bản A: Worker truyền thống gọi inventory API

**Yêu cầu:** Job chạy trong máy chủ VM, chỉ cần đọc tồn kho, AS hỗ trợ client credentials và secret manager.

**Thiết kế:** Đăng ký OAuth client `orders-worker-prod`; lấy secret từ secret manager; dùng `client_credentials` với scope `inventory.read`; AS cấp token `aud=inventory-api` TTL ngắn; `inventory-api` xác minh token và kiểm tra quyền. Tách client `orders-worker-dev` khỏi production để tránh dùng credential chéo môi trường.

**Kiểm tra lỗi:** Nếu đổi `aud` sang `billing-api`, request đọc inventory bị từ chối dù token ký hợp lệ.

### Kịch bản B: Pod Kubernetes gọi API cloud

**Yêu cầu:** Có nhiều Pod scale liên tục; không muốn gắn một client secret dài hạn vào mọi Pod.

**Thiết kế:** Dùng service account riêng và projected token audience dành cho STS; STS tin issuer Kubernetes và binding của namespace/service account; STS đổi assertion lấy token dành cho cloud API. Pod đọc lại projected token sau rotation; thu hẹp quyền ở cả Kubernetes RBAC, federation policy và API IAM.

**Kiểm tra lỗi:** Assertion từ namespace khác hoặc sai audience phải bị STS từ chối, kể cả hai workload cùng cluster.

### Kịch bản C: API xử lý yêu cầu của end-user qua nhiều service

**Yêu cầu:** Alice được phép đọc đơn hàng của mình; service A cần gọi service B.

**Thiết kế:** Giữ ranh giới quyền user và service: dùng user delegation/token exchange khi được hỗ trợ, hoặc kiểm tra quyền của Alice trước khi service A thực hiện thao tác có đặc quyền ở B. API B chỉ tin access token dành cho mình, đồng thời áp dụng chính sách actor/subject nếu có.

**Kiểm tra lỗi:** User Bob không được đọc đơn hàng Alice chỉ vì backend có service token mạnh hơn.

## 13. Checklist vận hành và tự kiểm tra

Trước khi đưa một machine identity vào production, kiểm tra:

1. **Identity:** Có identity riêng cho dịch vụ, môi trường, tenant và owner rõ ràng chưa? Có tránh dùng tài khoản nhân viên không?
2. **Bootstrap trust:** AS/STS kiểm tra đúng credential, issuer, key, chứng chỉ, namespace/SA và audience của assertion chưa?
3. **Token:** Token có thời hạn ngắn, đúng scope và audience, và đúng loại access token chưa? Có dùng refresh token sai mô hình không?
4. **Resource server:** Có xác minh issuer, chữ ký hoặc introspection, thời hạn, audience, scope và chính sách nghiệp vụ không?
5. **Secret và replay:** Credential/token có được bảo vệ khỏi log, source code, metadata SSRF và đọc trái phép không? Có cân nhắc sender constraint khi cần không?
6. **Vòng đời:** Có rotation, thu hồi khẩn cấp, deprovision, kiểm toán identity mồ côi và giám sát token issuance/401/403 không?

**Câu hỏi 1:** Service account của Kubernetes có tự động là OAuth client đã đăng ký ở AS bên ngoài không?

**Trả lời:** Không. Cần cơ chế trust/federation hoặc đăng ký client cụ thể. Một projected service account token có thể làm assertion tại STS nếu STS tin issuer, subject và audience tương ứng.

**Câu hỏi 2:** API có nên chấp nhận access token chỉ vì JWT có chữ ký đúng và `scope=inventory.read` không?

**Trả lời:** Không. API còn phải tin issuer/key source, kiểm tra token profile, `aud=inventory-api`, thời hạn và quyền theo tài nguyên/tenant.

**Câu hỏi 3:** Rotate `client_secret` có làm tất cả JWT access token đã cấp trước đó vô hiệu ngay không?

**Trả lời:** Không nhất thiết. Việc thu hồi access token còn tùy AS, cơ chế token, TTL và quy trình resource server kiểm tra trạng thái/denylist.

**Câu hỏi 4:** Khi job không có người dùng đăng nhập, có cần ID token hoặc refresh token để gọi API không?

**Trả lời:** Thông thường chỉ cần access token thông qua client credentials hoặc token exchange phù hợp. ID token phục vụ OIDC authentication của người dùng; refresh token nhìn chung không được cấp với client credentials grant.

## Tài liệu chuẩn tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749), mục `4.4`: client credentials và refresh token.
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền access token và xử lý lỗi.
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): JWT assertions.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác minh opaque token và trạng thái `active`.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): đổi assertion/token qua STS.
- [RFC 8705 — OAuth 2.0 mTLS](https://www.rfc-editor.org/rfc/rfc8705) và [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained tokens.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): yêu cầu token dành cho resource cụ thể.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725), [RFC 9068 — JWT Access Token Profile](https://www.rfc-editor.org/rfc/rfc9068): kiểm tra JWT và access token đúng mục đích.
- [Kubernetes — Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/) và [Projected Volumes](https://kubernetes.io/docs/concepts/storage/projected-volumes/): workload identity/token projection.
- [SPIFFE — Overview](https://spiffe.io/docs/latest/spiffe-about/overview/): danh tính workload và SVID.

**Kết luận:** Service account là một cách biểu diễn **machine identity**, credential là bằng chứng để xác thực identity, còn **access token** là quyền truy cập được cấp cho API trong phạm vi và thời hạn xác định. Thiết kế an toàn yêu cầu tin đúng issuer/STS, xác minh audience và scope, bảo vệ credential, thu hồi quyền và quản lý toàn bộ vòng đời workload.
