# Cấu hình audience cho API thay vì chỉ dùng client_id của ứng dụng giao diện

Khi kết nối **Spring Security OAuth 2.0/OIDC Resource Server** với một **Authorization Server/Identity Provider (IdP)**, một lỗi thiết kế rất dễ gặp là lấy `client_id` của ứng dụng giao diện rồi coi đó là **audience hợp lệ của mọi access token gửi đến API**. Ứng dụng giao diện và API lại đảm nhận **hai vai trò khác nhau** trong OAuth 2.0:

- Ứng dụng giao diện (SPA, mobile app, server-rendered web hoặc BFF) thường là **OAuth client**, được đăng ký với một `client_id` để yêu cầu cấp token.
- Backend Orders API, Payments API hay Reports API là **Resource Server**. Mỗi API phải kiểm tra access token có được phát hành **cho chính resource/API đó** hay không, thông thường qua claim `aud` (audience) hoặc một cơ chế ràng buộc resource tương đương do nhà phát hành bảo đảm.

Một access token có chữ ký hợp lệ, `iss` đúng, còn hạn và mang `scope=orders.read` **chưa chắc** được phép gọi Orders API. Nếu `aud` của token chỉ nói token dành cho một ứng dụng khác, Resource Server không nên chấp nhận nó chỉ vì một scope trông quen thuộc.

> **Nguyên tắc chính:** Xác định audience của **API/resource đang bảo vệ**, rồi yêu cầu access token chứa audience ấy. **Không mặc định dùng `client_id` của frontend làm audience của API.** Trong một số hệ thống, mã đăng ký của **chính API** cũng được sử dụng làm audience; điều này khác hoàn toàn với việc lấy `client_id` của ứng dụng giao diện.

Bài học thuộc chương **Tích hợp nhà phát hành** của module **Spring Security OAuth 2.0 OIDC Resource Server**. Các ví dụ trình bày Java/Spring Security Servlet và WebFlux, OAuth/OIDC flows, cấu hình phía nhà phát hành, phân quyền scope, kiểm thử và các trường hợp dễ nhầm khi dùng những nhà cung cấp danh tính khác nhau. URI, tên ứng dụng và mã định danh đều là **dữ liệu minh họa**.

## 1. Bắt đầu từ đúng ba vai trò

Giả sử nền tảng bán hàng có:

| Thành phần | Vai trò | Định danh minh họa |
|---|---|---|
| Shop Web SPA | **OAuth client** / giao diện | `shop-spa-client` |
| Orders API | **Resource Server** | `https://api.example.test/orders` |
| Payments API | **Resource Server** | `https://api.example.test/payments` |
| Login Service | **Authorization Server / OIDC Provider** | `https://login.example.test/realms/shop` |

Frontend đưa người dùng đến trang đăng nhập và thực hiện OAuth 2.0 Authorization Code + PKCE theo hợp đồng với nhà phát hành. Sau khi được cấp access token, frontend gửi token đến Orders API:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

Orders API phải xác minh **token dành cho Orders API**, không chỉ token được cấp trong phiên đăng nhập của Shop Web.

~~~mermaid
flowchart LR
    U["Người dùng"] --> F["Shop Web SPA"]
    F -->|"Authorization Code + PKCE, client_id=shop-spa-client"| AS["Authorization Server / OIDC Provider"]
    AS -->|"Access token dành cho Orders API"| F
    F -->|"Bearer access token"| API["Orders API / Resource Server"]
    API -->|"Verify signature, iss, aud, time, scopes"| API
~~~

Trong thực tế, BFF có thể giữ token ở backend thay vì trình duyệt, mobile app có phương thức tương tác khác, nhưng **OAuth client** và **resource nhận token** vẫn là hai khái niệm tách biệt.

### 1.1. `client_id` trả lời câu hỏi nào?

`client_id` là mã định danh của một OAuth client đã đăng ký tại Authorization Server. Nó thường được dùng trong authorization request hoặc token request để xác định **ứng dụng đang yêu cầu token**.

Ví dụ các tham số đăng nhập minh họa:

~~~text
GET https://login.example.test/authorize
    ?response_type=code
    &client_id=shop-spa-client
    &redirect_uri=https%3A%2F%2Fshop.example.test%2Fcallback
    &scope=openid%20profile%20orders.read
    &state=<RANDOM_STATE>
    &code_challenge=<PKCE_CHALLENGE>
    &code_challenge_method=S256
~~~

Request thực phải được URL-encode đúng cách và sử dụng `state`, PKCE ngẫu nhiên/an toàn. `client_id` thường là **định danh công khai**, không phải bí mật xác thực client. Với SPA public client, không được nhúng client secret rồi coi nó an toàn.

### 1.2. `aud` trả lời câu hỏi nào?

Claim `aud` của JWT xác định **đối tượng dự kiến nhận token**. Với OAuth access token dùng JWT profile thích hợp, audience thường xác định **Resource Server/API**.

Access token hợp lệ cho Orders API có thể mang:

~~~json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["https://api.example.test/orders"],
  "client_id": "shop-spa-client",
  "scope": "orders.read",
  "iat": 1924988400,
  "exp": 1924992000
}
~~~

Các trường trên chỉ là **payload minh họa**, không phải token đã ký; `exp` và `iat` trong ví dụ không được dùng làm thời hạn thực tế. Các nhà phát hành có thể dùng `azp`, `client_id`, `appid` hoặc metadata khác để mô tả client được cấp token; đó là **thông tin khác** với audience.

Đọc bằng ngôn ngữ nghiệp vụ:

~~~text
iss       → Ai phát hành token?
sub       → Chủ thể nào được mô tả trong token?
aud       → Token nhằm gửi cho resource/API nào?
client_id → Client nào đã yêu cầu/được cấp token?
scope     → Phạm vi quyền nào được cấp?
exp/nbf   → Token có hiệu lực về thời gian không?
~~~

Không phải token nào cũng chứa mọi field theo cùng tên; **hợp đồng token profile với issuer quyết định điều gì bắt buộc**. Với Resource Server, cần làm rõ audience/resource binding là gì và cách bảo đảm nó.

### 1.3. `aud` không phải `scope` và cũng không phải `iss`

| Câu hỏi | Trường thường dùng | Ví dụ |
|---|---|---|
| Ai là nhà phát hành tin cậy? | `iss` | `https://login.example.test/realms/shop` |
| Token dành cho API nào? | `aud` | `https://api.example.test/orders` |
| Token được cấp cho client nào? | `client_id` hoặc metadata provider tương đương | `shop-spa-client` |
| Token được làm những thao tác gì? | `scope` / `scp` | `orders.read orders.create` |
| Token thuộc subject nào? | `sub` | `user-123` |

Chữ ký JWS hợp lệ **không tự chứng minh audience phù hợp**. Issuer đúng **không có nghĩa mọi token do issuer đó phát hành đều có thể dùng ở mọi API**. Scope đúng **không sửa được audience sai**.

## 2. Hai loại JWT thường bị đánh đồng: ID token và access token

OIDC đưa thêm khái niệm **ID token**, thường cũng là JWT. ID token được phát hành cho **OIDC client** để xác thực thông tin đăng nhập của người dùng, không phải một access token tổng quát dùng gọi bất kỳ Resource Server API nào.

### 2.1. ID token có `aud=client_id` là bình thường

Ví dụ payload ID token của Shop Web:

~~~json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": "shop-spa-client",
  "exp": 1924992000,
  "iat": 1924988400
}
~~~

Theo OIDC Core, ID token có audience xác định **client dự kiến nhận ID token**. Việc `aud=shop-spa-client` ở đây có thể **hoàn toàn đúng** cho **ID token**.

### 2.2. Access token dành cho Orders API phải khác về mục đích

Ví dụ access token:

~~~json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": "https://api.example.test/orders",
  "client_id": "shop-spa-client",
  "scope": "orders.read",
  "exp": 1924992000
}
~~~

| Trường | ID token | Access token cho Orders API |
|---|---|---|
| Mục đích | Chứng thực danh tính cho OIDC client | Cho phép client gọi resource trong phạm vi cấp quyền |
| Audience điển hình | `shop-spa-client` | `https://api.example.test/orders` |
| Bên nhận dự kiến | OIDC client | Orders API |
| Dùng làm `Authorization: Bearer` cho API? | **Không mặc định được phép** | Đúng loại credential theo hợp đồng API |

Nếu Orders API chấp nhận ID token chỉ vì ID token cũng có chữ ký từ issuer tin cậy và `aud=shop-spa-client`, hệ thống có nguy cơ **token substitution/confused-deputy**: một token được phát hành cho mục đích khác bị dùng tại resource không dành cho nó.

### 2.3. Đừng “sửa” lỗi ID token bằng cách đổi API audience thành frontend client ID

~~~text
API báo 401 vì aud của ID token là shop-spa-client
    ↓
Developer cấu hình API audience = shop-spa-client
    ↓
ID token có thể vượt bước audience
~~~

Giải pháp đúng là **client lấy đúng access token cho Orders API** và Resource Server xác minh audience của resource. Không hạ chính sách resource để chấp nhận ID token làm Bearer access token.

Để chống nhầm loại token, có thể cần thêm **token type/profile validation** (ví dụ `typ=at+jwt` theo JWT access token profile RFC 9068, khi issuer áp profile này), ràng buộc issuer/client và claims bắt buộc. **Audience là cần thiết nhưng không phải biện pháp duy nhất** chống dùng nhầm token.

## 3. Các token được cùng issuer phát hành vẫn có thể dành cho resource khác nhau

Giả sử Shop Web gọi cả Orders và Payments API. Hai access token có thể cùng `iss`, `sub` và `client_id=shop-spa-client`, nhưng khác audience:

~~~text
Token O:
  aud   = https://api.example.test/orders
  scope = orders.read

Token P:
  aud   = https://api.example.test/payments
  scope = payments.read
~~~

Orders API nên chấp nhận Token O, từ chối Token P. Payments API nên chấp nhận Token P, từ chối Token O, ngay cả khi hai token cùng issuer, cùng subject và cùng frontend client.

### 3.1. Vì sao chỉ kiểm tra scope chưa đủ?

Scope là thông tin **quyền được cấp** nhưng không luôn phân biệt resource. Một số hệ thống có scope phổ biến như `read`, `api.read` hoặc `profile`. Nếu API A và API B chỉ kiểm tra scope `read`, token cho A có thể bị dùng tại B nếu audience bị bỏ qua.

~~~text
Bad:
  signature valid AND issuer trusted AND scope=read
  → cho qua mọi API sử dụng scope read

Better:
  signature valid AND issuer trusted
  AND audience contains THIS_API
  AND scope matches THIS_ENDPOINT
  → cho phép thao tác theo đúng resource
~~~

### 3.2. Audience và scope phối hợp như hai lớp

~~~mermaid
flowchart TD
    A["Bearer access token"] --> B{"Signature / issuer / time hợp lệ?"}
    B -->|Không| X["401 / authentication rejected"]
    B -->|Có| C{"aud chứa Orders API?"}
    C -->|Không| X
    C -->|Có| D["Tạo Authentication và authorities"]
    D --> E{"Có SCOPE_orders.read cho GET?"}
    E -->|Không| Y["403 / authorization denied"]
    E -->|Có| F["Kiểm tra order owner / tenant"]
    F --> G["Trả dữ liệu nếu đủ quyền"]
~~~

Đường đi này cho thấy kiểm tra audience nằm ở **token validation** trước authorization. Token hợp lệ cho Orders API nhưng thiếu scope vẫn là token được xác thực; nó bị chặn bởi rule quyền ở tầng HTTP/method.

### 3.3. Resource-level audience chưa thay thế object-level authorization

Token `aud=orders-api` và `scope=orders.read` không nhất thiết cho phép xem **mọi** đơn hàng. Service vẫn cần kiểm tra `sub`, tenant, chủ sở hữu đơn hàng, phân quyền đối tác và chính sách nghiệp vụ. Audience trả lời “token dành cho API này”, **không trả lời “được phép truy cập mọi bản ghi”**.

## 4. Lựa chọn audience thực sự của API

Audience **không phải** một chuỗi do Resource Server tự đặt tùy ý mà phía issuer không biết. Đây là một phần của **hợp đồng giữa nhà phát hành, OAuth client và resource**:

1. Xác định **Resource Server nào** sẽ nhận access token.
2. Đăng ký/khai báo **resource identifier** hoặc API registration tại nhà phát hành.
3. Yêu cầu nhà phát hành cấp access token **cho resource identifier ấy** bằng cơ chế được hỗ trợ.
4. Xem access token được phát hành trong môi trường test và xác nhận giá trị `aud` theo hợp đồng.
5. Cấu hình Resource Server yêu cầu **đúng audience được phát hành**, đồng thời kiểm tra issuer, chữ ký, thời gian và quyền.

Ví dụ thông tin thiết kế:

~~~yaml
oauth-resource-contract:
  authorization-server-issuer: https://login.example.test/realms/shop
  oauth-client-id: shop-spa-client
  resource-name: orders-api
  resource-audience: https://api.example.test/orders
  accepted-scope-for-reading: orders.read
~~~

Đây là tài liệu mô tả **hợp đồng minh họa**, **không phải** một Spring Boot YAML property được framework tự hiểu. Trong project, chỉ các thuộc tính được bind vào cấu hình Spring Security/bean tương ứng mới có hiệu lực.

### 4.1. Audience có nhất thiết là URL thật có thể truy cập?

Không. Audience có thể là một URI resource, một application identifier hoặc giá trị khác được issuer và API **thỏa thuận chính xác** theo token profile. Ví dụ:

~~~text
https://api.example.test/orders
api://orders-api
orders-api
<API_APPLICATION_ID>
~~~

Một URL được dùng làm identifier **không bắt buộc là endpoint HTTP có thể GET được**. Tuy nhiên, identifier nên ổn định, rõ phạm vi resource, nhất quán giữa các môi trường và không bị trùng với client khác.

### 4.2. Không lấy public host từ `Host` header để làm audience

Giả sử API được public qua:

~~~text
https://api.example.test/orders
~~~

nhưng traffic được gateway chuyển tới:

~~~text
http://orders-service.cluster.local
~~~

Không lấy `Host`, `X-Forwarded-Host` hoặc đường dẫn inbound để tự suy ra expected audience cho từng request. Những header đó có thể bị ảnh hưởng bởi reverse proxy hoặc request ngoài ý muốn. Audience phải là một **giá trị cấu hình được tin cậy**, hoặc một bảng ánh xạ resource/route do hệ thống quản lý rõ ràng.

### 4.3. Có nên dùng `client_id` của chính API làm audience?

**Có thể**, nếu nhà phát hành dùng **API application registration identifier** làm audience của access token. Điều quan trọng là phân biệt:

~~~text
SPA application / OAuth client:
    client_id = shop-spa-client

Orders API application/resource:
    application id = orders-api-registration

Access token:
    aud = orders-api-registration  // có thể đúng theo issuer contract
~~~

Trường hợp này **khác** việc đặt `aud=shop-spa-client` chỉ vì frontend đang sử dụng client ID đó. Tên thuộc tính ở console của IdP có thể gây nhầm: một resource/API đôi khi cũng được đăng ký dưới dạng “application” với một client/application ID, nhưng **vai trò nhận token của nó vẫn là resource**.

### 4.4. Phân tách dev, staging và production

Các môi trường có thể có resource registrations riêng:

| Môi trường | Audience minh họa |
|---|---|
| Development | `https://api.dev.example.test/orders` |
| Staging | `https://api.staging.example.test/orders` |
| Production | `https://api.example.test/orders` |

Đừng để API production chấp nhận vô điều kiện cả audience của dev/staging chỉ để tiện test. Nếu hệ thống cố ý dùng chung một resource identifier qua nhiều môi trường, phải có giới hạn issuer, keys, tenant, network và policy tương ứng; một token test không được phép trở thành credential có hiệu lực ở production do cấu hình trust quá rộng.

## 5. Nhà phát hành phải cấp access token cho resource nào?

Chỉnh cấu hình **Resource Server** chỉ quyết định token nào API **chấp nhận**, **không tự khiến Authorization Server phát hành một `aud` mới**.

~~~mermaid
flowchart TD
    A["API định nghĩa expected audience"] --> B["AS đăng ký resource/API và scopes"]
    B --> C["OAuth client yêu cầu quyền gọi resource"]
    C --> D["AS phát hành access token đúng aud"]
    D --> E["Client gửi Bearer token tới API"]
    E --> F["API verify chữ ký, iss, aud, thời gian"]
    F --> G["API authorize scope và quyền tài nguyên"]
~~~

Nếu API yêu cầu `aud=https://api.example.test/orders` nhưng issuer vẫn chỉ phát token `aud=shop-spa-client`, mọi request Bearer tương ứng sẽ bị từ chối **đúng theo policy mới**. Cần sửa **đường cấp token/hợp đồng issuer**, không bỏ audience validator để tránh 401.

### 5.1. OAuth 2.0 Resource Indicators — RFC 8707

RFC 8707 mô tả tham số `resource` để client nêu tài nguyên dự kiến truy cập khi yêu cầu authorization hoặc token. Ví dụ yêu cầu authorization theo chuẩn, **nếu Authorization Server hỗ trợ**:

~~~text
GET /authorize
  ?response_type=code
  &client_id=shop-spa-client
  &redirect_uri=https%3A%2F%2Fshop.example.test%2Fcallback
  &scope=openid%20orders.read
  &resource=https%3A%2F%2Fapi.example.test%2Forders
  &code_challenge=<PKCE_CHALLENGE>
  &code_challenge_method=S256
  &state=<RANDOM_STATE>
~~~

Sau khi đổi code lấy token (có PKCE), Authorization Server **có thể** phát access token dành cho resource đã chỉ định. Việc hỗ trợ tham số `resource`, cách phát hành `aud`, cho phép nhiều resource và trường hợp không được ủy quyền đều phụ thuộc AS profile/policy.

Không được mặc định “thêm `resource` vào mọi OAuth URL thì mọi IdP sẽ hiểu”; phải xem hợp đồng provider. Tham số `audience` trong một số provider cũng là **mở rộng riêng** chứ không phải tên thay thế được chuẩn hóa cho mọi AS.

### 5.2. Scope không chắc chắn tự chọn đúng audience

~~~text
Requested scopes: orders.read
~~~

Trừ khi IdP đã liên kết scope với API/resource một cách rõ ràng, chỉ yêu cầu `orders.read` chưa chắc nhận được access token có `aud=orders-api`. Một số nhà phát hành xác định audience từ resource identifier hoặc API permissions; số khác từ client scope mapper; số khác từ tham số issuer-specific.

Vì vậy khi tích hợp, kiểm tra ba thứ đồng thời:

~~~text
Client request:
    resource / API permission / provider-specific audience

Issued access token:
    aud = expected API resource

Resource Server:
    expected audience validator = cùng giá trị
~~~

### 5.3. Không sửa JWT bằng cách thay payload phía frontend

JWT dạng JWS có claims được ký. Nếu frontend sửa `aud` trong payload rồi ghép lại token, chữ ký **không còn hợp lệ**. Nếu một client tự tạo JWT mang audience mong muốn bằng khóa riêng không được tin, Resource Server cũng phải từ chối.

~~~text
Sai:
    Frontend decode JWT → sửa aud → encode lại → gửi API

Đúng:
    Client yêu cầu AS cấp access token cho Orders API
    AS ký/phát hành token
    API verify key/issuer/audience/token policy
~~~

### 5.4. Cần quyền nào để gọi API?

Audience xác nhận token **được nhắm tới resource**. Để thao tác cụ thể, API còn kiểm tra scope/authority. Ví dụ:

| API | Audience | Operation | Authority yêu cầu |
|---|---|---|---|
| Orders API | `https://api.example.test/orders` | GET đơn hàng | `SCOPE_orders.read` |
| Orders API | `https://api.example.test/orders` | POST đơn hàng | `SCOPE_orders.create` |
| Payments API | `https://api.example.test/payments` | GET thanh toán | `SCOPE_payments.read` |

Hai token cùng audience Orders API có thể có scope khác nhau. Không được xem “đúng audience” là cấp quyền mọi endpoint; cũng không xem “đúng scope” là bù được audience sai.

## 6. Trình tự tích hợp issuer và Resource Server

Một quy trình kỹ thuật nên thực hiện theo thứ tự:

**Bước 1 — Chốt issuer tin cậy.** Ví dụ `https://login.example.test/realms/shop`, phân biệt realm/tenant/environment. Dùng metadata/JWKS từ nguồn tin cậy và kiểm tra JOSE algorithms cho phép.

**Bước 2 — Xác định API resource identifier.** Ví dụ `https://api.example.test/orders`. Phía API phải có **expected audience** độc lập với mã của frontend.

**Bước 3 — Đăng ký API và scopes.** Tại issuer, đăng ký Orders API resource, `orders.read`/`orders.create`, grant/consent/permissions dành cho frontend theo policy.

**Bước 4 — Cấu hình frontend/BFF lấy đúng access token.** Dùng Authorization Code + PKCE với browser/public client; khai báo resource/API permissions hoặc provider-specific audience trong authorization/token request nếu IdP hỗ trợ.

**Bước 5 — Cấu hình API kiểm tra signature/issuer/time/audience.** Audience phải được so sánh với **identifier của resource**, không phải `shop-spa-client`.

**Bước 6 — Gắn HTTP/method authorization.** Mapping `scope`/`scp` thành `SCOPE_*` và bảo vệ từng method/route; kiểm tra object/tenant ở tầng nghiệp vụ.

**Bước 7 — Thử đúng và sai.** Cần ít nhất token đúng API, token dành cho API khác, token ID token dành cho frontend, JWT hết hạn và token hợp lệ nhưng thiếu scope.

**Bước 8 — Theo dõi rollout.** Quan sát tăng `invalid_token` theo phân loại issuer/audience mà không log raw token hoặc claims cá nhân. Khi có 401 do sai audience, sửa đường cấp token hoặc đồng bộ resource identifier, không mở rộng allowlist tùy tiện.

## 7. Spring Security Servlet: cấu hình JWT audience cho Orders API

Spring Security OAuth 2.0 Resource Server dùng `JwtDecoder` để xác minh Bearer JWT. Đối với JWT ký, decoder thường thực hiện **signature validation** bằng khóa đáng tin rồi áp bộ `OAuth2TokenValidator<Jwt>` cho issuer, thời gian và những claims theo yêu cầu.

### 7.1. Dependencies

Ví dụ Spring Boot Servlet/Spring MVC:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Trong ứng dụng thực, JWT/JOSE dependencies phải tương thích với phiên bản Spring Security đang chạy. Khi dùng Spring Boot starter hiện đại, các thành phần Resource Server/JOSE phù hợp thường được đưa vào qua dependency management.

### 7.2. Cách dùng cấu hình audience được Spring Boot hỗ trợ

Ở các phiên bản Spring Boot có hỗ trợ cấu hình audiences cho JWT Resource Server, ứng dụng có thể dùng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
          audiences:
            - https://api.example.test/orders
~~~

Mục đích:

- `issuer-uri`: giúp Resource Server cấu hình trust đối với nhà phát hành và xác minh claim `iss`.
- `audiences`: yêu cầu access token có audience được chấp nhận theo cơ chế auto-configuration của phiên bản đang sử dụng.

**Lưu ý phiên bản:** kiểm tra tài liệu cấu hình Spring Boot **đúng phiên bản dự án** và xác minh property `spring.security.oauth2.resourceserver.jwt.audiences` có được bind/áp dụng thật. Những phiên bản cũ không hỗ trợ property này có thể bỏ qua hoặc báo cấu hình không phù hợp; **đừng coi một dòng YAML chưa được framework nhận là audience validator đang chạy**.

Khi ứng dụng tự cung cấp bean `JwtDecoder` hoặc ghi đè Resource Server decoder trong `SecurityFilterChain`, một số auto-configuration của Spring Boot **không còn áp dụng**; phải chủ động đưa audience validator vào decoder được dùng thật.

### 7.3. Cách chủ động: cấu hình custom `JwtDecoder`

Để kiểm soát hợp đồng một cách tường minh, ta khai báo:

~~~yaml
app:
  security:
    jwt:
      issuer: https://login.example.test/realms/shop
      jwks-uri: https://login.example.test/realms/shop/protocol/openid-connect/certs
      audience: https://api.example.test/orders
~~~

Nhóm `app.security.jwt.*` là **thuộc tính do ứng dụng tự tạo**, không tự có hiệu lực nếu chưa có bean Java đọc chúng. Đường JWKS chỉ là URI minh họa; issuer thật có thể công bố JWK Set ở URL khác.

Một bean decoder:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class OrdersJwtDecoderConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwks-uri}") String jwksUri,
            @Value("${app.security.jwt.audience}") String apiAudience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwksUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> expectedAudience = jwt ->
            jwt.getAudience().contains(apiAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Access token audience is not accepted",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                expectedAudience
            )
        );

        return decoder;
    }
}
~~~

#### Vì sao cần cả default validator và audience validator?

`NimbusJwtDecoder.setJwtValidator(...)` **thay thế** bộ validator trên decoder. Nếu chỉ gắn:

~~~java
decoder.setJwtValidator(expectedAudience);
~~~

thì những kiểm tra issuer/thời gian mặc định có thể bị mất. Trong mẫu đúng, `JwtValidators.createDefaultWithIssuer(issuer)` cung cấp bộ kiểm tra mặc định theo issuer và thời gian cho phiên bản Spring Security đang dùng, rồi `DelegatingOAuth2TokenValidator` kết hợp với kiểm tra audience. Nếu token profile yêu cầu `exp` **bắt buộc tồn tại**, token type, tenant hay ràng buộc khác, cần bổ sung validator tương ứng.

**Việc kiểm tra audience là phép so sánh trên token đã được decode/xác minh.** `jwt.getAudience()` trả danh sách audience theo cách Spring Security biểu diễn claims. Không lấy `aud` từ một payload chưa xác minh để tự tạo principal; phải dùng decoder/JWS validation tin cậy.

#### Thuật toán và khóa phải thuộc danh sách cho phép

`jwsAlgorithm(SignatureAlgorithm.RS256)` minh họa issuer ký bằng RS256. **Không phải mọi issuer đều dùng RS256**. Hãy xác định thuật toán thực được nhà phát hành hỗ trợ và allowlist nó cùng nguồn JWKS tin cậy; đừng tự tin `alg` hay `jku` do Bearer token gửi lên để quyết định fetch khóa từ URL bất kỳ.

Nếu đã có `issuer-uri` và cần JWKS URI cụ thể, việc cung cấp cùng issuer và JWK Set đúng hợp đồng có thể giảm phụ thuộc metadata discovery lúc khởi động, nhưng Resource Server vẫn phải bảo vệ quá trình lấy/refresh public keys.

### 7.4. Gắn HTTP authorization vào API

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersHttpSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Ở đây có **hai ranh giới**:

1. `JwtDecoder` yêu cầu **audience dành cho Orders API** và token có issuer/chữ ký/thời gian phù hợp.
2. `authorizeHttpRequests` yêu cầu **scope cụ thể theo HTTP method**.

Nếu token có `aud=payments-api`, nó bị loại ở **authentication** trước khi `hasAuthority("SCOPE_orders.read")` được đánh giá. Nếu token có audience đúng nhưng thiếu scope, nó có thể được xác thực rồi bị từ chối ở **authorization**.

Đây là ví dụ security rules, chưa phải ứng dụng runnable đầy đủ: cần controller/service, dependency management, properties thực, audience registration tại issuer, CSRF/CORS/session policy phù hợp và object-level authorization khi xử lý dữ liệu.

### 7.5. Không cấu hình bằng frontend client ID

Phản ví dụ:

~~~yaml
app:
  security:
    jwt:
      audience: shop-spa-client  # SAI nếu đây chỉ là OAuth client của frontend
~~~

Thay bằng resource identifier đúng:

~~~yaml
app:
  security:
    jwt:
      audience: https://api.example.test/orders
~~~

Nếu một provider dùng **API application/client registration ID** làm audience, nhập đúng ID của **API registration** theo hợp đồng, không tự thay bằng ID của SPA. Tên chuỗi có thể khác, nhưng **vai trò và mục đích nhận token** mới quyết định đúng/sai.

## 8. WebFlux Resource Server: audience validator ở `ReactiveJwtDecoder`

Với WebFlux, kiểu cấu hình tương ứng là `ReactiveJwtDecoder` và `SecurityWebFilterChain`. Quy tắc bảo mật giữ nguyên nhưng có đường xử lý bất đồng bộ.

### 8.1. Dependencies reactive

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 8.2. Bean decoder thực với audience riêng của API

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
class OrdersReactiveJwtConfiguration {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwks-uri}") String jwksUri,
            @Value("${app.security.jwt.audience}") String apiAudience) {

        NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
            .withJwkSetUri(jwksUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> expectedAudience = jwt ->
            jwt.getAudience().contains(apiAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "JWT is not intended for Orders API",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                expectedAudience
            )
        );

        return decoder;
    }
}
~~~

`setJwtValidator(...)` cũng **thay** validators đang gắn vào reactive decoder. Ghép lại issuer/time defaults cùng audience để không vô tình bỏ một lớp kiểm tra khi tùy chỉnh.

### 8.3. HTTP security reactive

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersReactiveHttpSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Trong reactive stack, `ReactiveJwtDecoder.decode(...)` trả `Mono<Jwt>`. JWT sai audience phát lỗi xác thực và không sinh principal hợp lệ; không viết `onErrorResume(...)` để trả một `Jwt`/`Authentication` giả nếu token không được xác minh.

### 8.4. Khác biệt Servlet và WebFlux

| Trách nhiệm | Servlet | WebFlux |
|---|---|---|
| Security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Nimbus implementation | `NimbusJwtDecoder` | `NimbusReactiveJwtDecoder` |
| Cấu hình URL authorization | `authorizeHttpRequests` | `authorizeExchange` |
| Scope authority | `SCOPE_orders.read` | `SCOPE_orders.read` |
| Audience validation | `OAuth2TokenValidator<Jwt>` | `OAuth2TokenValidator<Jwt>` gắn vào decoder reactive |

Không dùng `SecurityFilterChain` Servlet để mong tự bảo vệ ứng dụng WebFlux thuần reactive. Cần chắc chắn chain/decoder phù hợp **đúng loại runtime** mà application đang chạy.

## 9. Khác nhau giữa các nhà phát hành: không sao chép nguyên cấu hình

Những nhà cung cấp danh tính khác nhau có cách đăng ký API và đưa audience vào access token không giống nhau. **Spring Resource Server chỉ nên chấp nhận các giá trị mà issuer thực sự phát hành theo hợp đồng**, không dựa vào tên property trong một ví dụ của nhà cung cấp khác.

### 9.1. Provider cho phép đăng ký “API Identifier”

Một số nhà phát hành, ví dụ cách tổ chức API của Auth0, cho phép khai báo API với một **identifier** và yêu cầu access token cho API đó bằng tham số **`audience` riêng của provider**.

Luồng ý tưởng:

~~~text
Application:
    Client ID = shop-spa-client

API Registration:
    Identifier = https://api.example.test/orders

Authorization request do SDK hỗ trợ:
    audience = https://api.example.test/orders
    scope    = orders.read

Access token:
    aud      = https://api.example.test/orders
~~~

Ví dụ tham số minh họa:

~~~text
GET /authorize
  ?response_type=code
  &client_id=shop-spa-client
  &audience=https%3A%2F%2Fapi.example.test%2Forders
  &scope=openid%20orders.read
  &redirect_uri=https%3A%2F%2Fshop.example.test%2Fcallback
  &code_challenge=<PKCE_CHALLENGE>
  &code_challenge_method=S256
  &state=<RANDOM_STATE>
~~~

**Quan trọng:** `audience` trong authorization request ở đây là **cơ chế do provider hỗ trợ**, không phải tham số OAuth 2.0 chuẩn được mọi Authorization Server bắt buộc nhận. Nếu SDK/IdP không có nó, phải dùng cơ chế resource/API permission thích hợp của nhà phát hành đó.

### 9.2. Keycloak: Audience Mapper và client scopes

Trong hệ thống dựa trên Keycloak, một lựa chọn có thể là cấu hình **client scopes** và **Audience mapper** để đưa định danh resource client của API vào `aud` trong access token.

Ví dụ theo ý tưởng:

~~~text
Realm: shop

Client frontend:
    shop-spa-client

Resource/API client:
    orders-api

Mapper theo client scope:
    included client audience = orders-api
    add to access token = true

Result (minh họa):
    aud = ["orders-api", ...]
~~~

Tùy phiên bản/cấu hình Keycloak, API resource có thể dùng client ID làm audience hoặc mapper thêm một **custom audience**. Việc scope được gắn default/optional, quyền yêu cầu scope và các policy role mapping ảnh hưởng token nào nhận được `aud`.

Những điểm cần xác nhận trên token thử nghiệm:

1. Token dành cho Orders API thật sự có `aud=orders-api` hoặc custom audience đã chốt.
2. Token của frontend dành cho resource khác **không tự có** Orders audience chỉ vì đăng nhập cùng realm.
3. Audience mapper được áp cho **access token**, không nhầm với ID token.
4. Scope/roles dùng để phân quyền ở Orders API được ánh xạ tin cậy.
5. Nếu một mapper vô tình thêm mọi API audience cho mọi token, cần đánh giá lại mức độ cô lập giữa resources.

Không nên sửa Orders API thành `expectedAudience="account"` chỉ vì token hiện nhận được có một audience mặc định dạng `account`; trước hết phải xác định đó có phải resource ID được cấp cho Orders API hay không.

### 9.3. Microsoft Entra ID: phân biệt ID của SPA và ID của API registration

Một kiến trúc Entra ID có thể có **hai app registrations**:

~~~text
App registration 1: Shop SPA
    client/application ID = SPA_CLIENT_ID

App registration 2: Orders API
    client/application ID = ORDERS_API_APP_ID
    exposed delegated scope = orders.read
    application ID URI = api://ORDERS_API_APP_ID
~~~

Frontend yêu cầu scope do **Orders API app registration** expose:

~~~text
scope=api://ORDERS_API_APP_ID/orders.read
~~~

Access token phát hành cho API có thể dùng **API application/client ID** hoặc **resource URI** làm `aud`, phụ thuộc token version và cấu hình resource/issuer. Giá trị kỳ vọng phải được xác định theo **hợp đồng Entra của đúng token version và API registration**, không tùy tiện mặc định một chuỗi.

Điểm cần phân biệt:

~~~text
SPA_CLIENT_ID:
    client thực hiện yêu cầu token (không phải audience Orders API)

ORDERS_API_APP_ID:
    application registration của API
    có thể chính là giá trị aud của access token theo provider contract
~~~

Ngoài audience, Entra token có thể dùng các claims như `scp` cho delegated permissions, `roles` cho application permissions, `azp` hoặc `appid` cho calling client tùy phiên bản/profile. Resource Server vẫn cần issuer/tenant validation và ánh xạ permissions đúng; không thay audience check bằng `azp`/`appid`.

### 9.4. Bảng so sánh cách nghĩ, không phải cấu hình dùng chung

| Mô hình nhà phát hành | Định danh request từ client | Audience API thường dựa trên |
|---|---|---|
| AS hỗ trợ RFC 8707 | `resource=<resource URI>` | Resource identifier theo hợp đồng |
| Provider hỗ trợ tham số `audience` riêng | `audience=<API identifier>` | API identifier đã đăng ký |
| Keycloak với audience mapper | Client scope/mapping phù hợp | API client ID hoặc custom audience |
| Microsoft Entra ID | API exposed scopes/permissions | ID hoặc URI của **API registration** theo token version |

**Không có quy tắc “aud phải luôn là URL” hoặc “aud phải luôn là GUID”.** Quy tắc đúng là **issuer phát token cho resource nào, Resource Server yêu cầu đúng resource đó**.

## 10. Khi frontend nhận token sai audience: xử lý từ đâu?

Một tình huống thực tế:

~~~text
Client configuration:
    client_id = shop-spa-client

Observed access token:
    aud = shop-spa-client

Orders API configuration:
    expected audience = https://api.example.test/orders

Result:
    HTTP 401 invalid_token
~~~

Không nên kết luận ngay “Resource Server lỗi”. Có thể:

- Frontend gửi **ID token** thay vì access token.
- Client đang yêu cầu token cho default resource khác.
- AS chưa đăng ký Orders API hoặc chưa cấp client permission để gọi nó.
- Frontend/SDK chưa truyền `resource`/provider-specific `audience`.
- Token được cache trước khi đổi resource/scope.
- API và AS đang dùng **khác môi trường/tenant**.
- API xác định audience identifier sai so với chính resource registration.

### 10.1. Các bước chẩn đoán

**Một:** xác định Bearer header đang mang **access token** hay ID token. Không in nguyên token vào log để điều tra.

**Hai:** xác nhận đúng `iss` và chữ ký từ issuer đáng tin bằng thư viện verifier/decoder. Chỉ sau khi xác minh, kiểm tra claims `aud`, `scope`/`scp`, `client_id`/`azp` được dùng cho chẩn đoán trong môi trường bảo mật.

**Ba:** đối chiếu giá trị `aud` với **API identifier** đã đăng ký tại issuer, không so với frontend client ID.

**Bốn:** xác nhận authorization/token request thực sự yêu cầu resource/API permission phù hợp, và AS cho phép frontend client nhận token đó.

**Năm:** cập nhật client request hoặc cấu hình issuer để cấp token đúng audience. Sau đó chỉ chấp nhận đúng audience trong Spring Resource Server.

**Sáu:** chạy negative tests với token cấp cho Payments API, ID token frontend và token sai issuer.

### 10.2. Token cache phía client có thể gây nhầm

Nhiều OAuth client libraries cache token theo account, resource/scope hoặc cơ chế riêng. Nếu frontend đổi cách yêu cầu token nhưng tiếp tục dùng access token cũ, API vẫn thấy `aud` sai.

Giải pháp là dùng API thư viện để yêu cầu **token cho đúng resource/scope** và tôn trọng cache key semantics, token lifecycle và consent. Không sửa tay JWT payload hoặc tắt audience validation. Không khuyên người dùng xóa dữ liệu tùy tiện nếu thư viện hỗ trợ cách lấy token đúng scope/resource.

### 10.3. BFF và server-rendered web

Với BFF, trình duyệt có thể chỉ giữ session cookie với BFF, còn BFF là OAuth client giữ access token phía server. Khi BFF gọi Orders API, chính **access token BFF lấy từ issuer** cũng phải có audience dành cho Orders API.

Không vì client là confidential backend mà audience được phép bỏ qua. `client_id` của BFF chỉ xác định caller client, còn resource nhận token vẫn là Orders API.

### 10.4. Mobile/public clients

Mobile client có thể dùng Authorization Code + PKCE tương tự SPA. `client_id` của mobile app và audience Orders API vẫn phải tách biệt. Việc mobile app không giữ được client secret an toàn càng khiến việc cấu hình token đúng resource và kiểm tra server-side không thể bị thay bằng tin tưởng một ID gửi từ client.

## 11. Khi API được đăng ký như một “OAuth client” tại issuer

Đây là nguồn nhầm lẫn rất phổ biến. Một IdP có thể gọi mọi đăng ký là “client” hoặc “app”, bao gồm cả frontend và backend APIs. Khi ấy có hai ID:

~~~text
frontendOauthClientId = shop-spa-client
ordersApiAppClientId  = orders-api
~~~

Nếu issuer phát access token:

~~~json
{
  "aud": "orders-api",
  "client_id": "shop-spa-client",
  "scope": "orders.read"
}
~~~

thì `aud=orders-api` **đúng** theo cách tổ chức này. Đừng hiểu câu “audience không phải client_id frontend” thành “audience tuyệt đối không bao giờ được là client ID”. Nó **có thể là client/application ID của API** khi đó chính là resource identifier được issuer dùng.

### 11.1. Đặt tên cấu hình để tránh nhập nhằng

Thay vì:

~~~yaml
app:
  security:
    client-id: shop-spa-client
~~~

rồi dùng `client-id` để kiểm tra `aud`, hãy phân biệt rõ:

~~~yaml
app:
  oauth:
    frontend-client-id: shop-spa-client
  security:
    jwt:
      expected-resource-audience: orders-api
~~~

Đây là property **tự định nghĩa**, phải map vào Java config khi sử dụng. Cách đặt tên rõ ràng tránh developer vô tình thay một biến dùng đăng nhập frontend rồi nới/chặn policy của Resource Server.

### 11.2. `azp` hoặc `client_id` vẫn có thể được kiểm tra riêng

Một API đôi khi chỉ cho phép một tập OAuth clients cụ thể gọi nó, dù token cùng audience. Khi đó có thể kiểm tra thêm **client allowlist**:

~~~text
Token accepted =
    trusted issuer/signature/time
    AND aud = Orders API
    AND client_id/azp thuộc danh sách client được cho phép (nếu yêu cầu)
    AND HTTP scope đủ cho endpoint
~~~

Đây là **lớp policy bổ sung**, không phải thay audience check bằng client allowlist. Cũng cần xác định claim đúng cho token profile: không tự đồng nhất `azp`, `appid` và `client_id` giữa mọi provider.

## 12. Claim `aud` có một hay nhiều giá trị?

Theo JWT, `aud` có thể là một chuỗi hoặc một mảng các định danh audience, tùy token profile. Hai payload đều có thể biểu diễn một audience:

~~~json
{
  "aud": "https://api.example.test/orders"
}
~~~

~~~json
{
  "aud": ["https://api.example.test/orders"]
}
~~~

Với Spring Security, `Jwt.getAudience()` thường cho một `List<String>` đã được chuẩn hóa từ claim JWT. Vì vậy validator:

~~~java
jwt.getAudience().contains(expectedAudience)
~~~

diễn đạt **token có ít nhất một audience là resource mong đợi**.

### 12.1. Token đa audience

Một access token có thể chứa:

~~~json
{
  "aud": [
    "https://api.example.test/orders",
    "https://api.example.test/payments"
  ],
  "scope": "orders.read payments.read"
}
~~~

Orders API kiểm tra `aud` chứa Orders identifier; Payments API kiểm tra `aud` chứa Payments identifier. Nếu issuer **chủ động hỗ trợ và cho phép** token đa resource, cả hai API có thể nhận token theo hợp đồng đó. Nhưng không nên coi đây là lựa chọn mặc định tốt nhất.

**Đánh đổi bảo mật:** một Bearer token bị lộ có thể dùng tại nhiều resources hơn nếu nó mang nhiều audiences. Cần xác định scope riêng từng API, giới hạn phát hành, thời hạn và token binding theo risk policy. Nhiều tổ chức chọn access token **resource-specific** để giảm phạm vi sử dụng.

### 12.2. Khi nào phải chấp nhận chính xác một audience?

Nếu API/issuer yêu cầu token chỉ dành cho Orders API, có thể đặt rule chặt hơn:

~~~java
OAuth2TokenValidator<Jwt> singleAudience = jwt -> {
    boolean valid = jwt.getAudience().size() == 1
        && jwt.getAudience().contains("https://api.example.test/orders");
    return valid
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Unexpected audiences", null));
};
~~~

Điều kiện này khác `contains(...)`: token có cả Orders và Payments audiences sẽ **bị từ chối**. Chỉ dùng khi issuer profile bảo đảm đúng chính sách single-audience; nếu issuer hợp lệ phát token đa audience, rule chặt hơn có thể gây lỗi tương thích.

### 12.3. Thời kỳ chuyển đổi identifier

Khi đổi audience từ `orders-api-v1` sang `https://api.example.test/orders`, có thể cần một cửa sổ ngắn chấp nhận hai giá trị để tránh cắt ngang các token chưa hết hạn:

~~~java
import java.util.Set;

Set<String> allowedApiAudiences = Set.of(
    "orders-api-v1",
    "https://api.example.test/orders"
);

OAuth2TokenValidator<Jwt> audienceDuringMigration = jwt -> {
    boolean matches = jwt.getAudience().stream()
        .anyMatch(allowedApiAudiences::contains);
    return matches
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Wrong resource", null));
};
~~~

Đây là **migration policy minh họa**. Nó cho phép **bất kỳ một** audience thuộc allowlist, không yêu cầu token chỉ có một audience. Chỉ bật khi cả hai identifier thực sự là **cùng một resource/trust boundary**. Nếu muốn không chấp nhận audiences khác xen kẽ, phải thêm rule tương ứng.

Không thêm `shop-spa-client` vào allowlist chỉ để ID token/frontend token vượt validation. Có ngày kết thúc migration rõ, theo dõi token issuer thay đổi và gỡ identifier cũ sau khi vòng đời token kết thúc.

### 12.4. Tránh so sánh bằng “chứa chuỗi con”

Phản ví dụ:

~~~java
// SAI: có thể chấp nhận identifier gần giống hoặc không liên quan.
boolean accepted = jwt.getAudience().stream()
    .anyMatch(aud -> aud.contains("orders"));
~~~

Các giá trị:

~~~text
https://api.example.test/orders
https://evil.example.test/orders-mock
https://api.example.test/orders-admin
orders-test
~~~

có thể cùng chứa “orders” nhưng đại diện cho resources khác nhau. **So sánh chính xác trên identifier đã được phê duyệt**, không dùng substring, regex quá rộng hay prefix tùy tiện để làm audience policy.

## 13. Nhiều issuer hoặc nhiều tenant: audience phải gắn với trust context

Một Resource Server có thể chấp nhận token từ nhiều Authorization Servers (nhiều realm, tenant, đối tác). Khi ấy không thể chỉ có một global `expectedAudience` mà bỏ qua mối quan hệ với issuer.

Ví dụ:

| Issuer đã tin cậy | Resource audience tương ứng |
|---|---|
| `https://login.partner-a.example.test/realm/orders` | `orders-api-partner-a` |
| `https://login.partner-b.example.test/realm/orders` | `https://api.example.test/orders` |

Mỗi issuer có thể có:

- Bộ public keys riêng.
- Allowed signing algorithms riêng.
- Resource identifier và token profile riêng.
- Cách mã hóa scopes/roles/client identity riêng.
- Chính sách thời gian, tenant và token type riêng.

### 13.1. Không chọn JWKS URI từ claim `iss` chưa xác minh mà không có allowlist

Một JWT chưa được xác minh có thể mang:

~~~json
{
  "iss": "https://attacker.example.test",
  "aud": "https://api.example.test/orders",
  "scope": "orders.read"
}
~~~

Nếu Resource Server đọc `iss` rồi **tự tải JWKS từ issuer bất kỳ**, kẻ tấn công có thể dựng issuer của mình, ký token bằng khóa của họ và khiến hệ thống vô tình tin token đó.

Với multi-issuer, phải có **registry issuer được phê duyệt** và lựa chọn `JwtDecoder`/`ReactiveJwtDecoder` tương ứng theo policy. Claim `iss` ở thời điểm chọn decoder có thể dùng làm **gợi ý định tuyến vào allowlist**, nhưng **chỉ sau signature/claims validation** mới coi nó là thông tin đáng tin.

### 13.2. Policy theo cặp issuer–audience

Một cấu trúc hợp đồng:

~~~text
Issuer A:
    trusted keys A
    expected aud A = orders-api-partner-a

Issuer B:
    trusted keys B
    expected aud B = https://api.example.test/orders

Token from A with aud B:
    reject (trừ khi hợp đồng A được cho phép cấp token cho B)
~~~

Không xem các issuer có quyền tương đương chỉ vì họ dùng cùng một audience string hoặc cùng một scope name. Nếu issuer A và issuer B dùng `SCOPE_orders.read` với nghĩa khác nhau, cần mapping/authorization riêng để tránh cấp quyền chéo.

### 13.3. Tenant ID không thay thế audience

Ví dụ token:

~~~json
{
  "iss": "https://login.example.test/tenant-a",
  "tid": "tenant-a",
  "aud": "billing-api",
  "scope": "orders.read"
}
~~~

Đúng tenant chưa đủ: audience vẫn là Billing API. Ngược lại, token đúng audience Orders API cũng không cho phép đọc đơn hàng của tenant khác. Hai kiểm tra phục vụ mục đích khác nhau:

~~~text
audience validation → token dành cho Orders API
tenant validation   → token thuộc tenant được chấp nhận
domain permission   → order được phép truy cập bởi principal/tenant
~~~

### 13.4. Nhiều security chains không mặc nhiên bảo đảm mỗi API đúng audience

Một ứng dụng có:

~~~text
/orders/**   → Orders endpoints
/payments/** → Payments endpoints
~~~

Nếu cả hai cùng dùng **một JwtDecoder chỉ kiểm tra một audience chung cho frontend**, các URL vẫn có thể nhận token không đúng resource. Có thể tổ chức nhiều `SecurityFilterChain`/`SecurityWebFilterChain`, mỗi chain gắn decoder/validator phù hợp, hoặc có một thiết kế token policy nhất quán cho API gateway cùng downstream resource.

Trong Spring Security, thứ tự chain thường chọn **chain đầu tiên khớp**. Cần kiểm tra chain có thực sự sử dụng decoder/resource audience dự kiến, không dựa vào việc “đã khai báo một bean audience validator đâu đó”.

## 14. Microservices, API Gateway và token relay

Audience có ý nghĩa đặc biệt khi một request đi qua nhiều dịch vụ:

~~~mermaid
flowchart LR
    UI["Frontend"] -->|"Token aud=Orders API"| GW["Gateway"]
    GW -->|"Bearer token"| O["Orders API"]
    O -->|"Gọi Payments API?"| P["Payments API"]
~~~

Token của frontend có `aud=Orders API` **không tự nhiên trở thành** token hợp lệ cho Payments API. Nếu Orders API chuyển nguyên Bearer token đó sang Payments API, Payments API kiểm tra đúng audience sẽ từ chối — đây có thể là **hành vi bảo mật mong muốn**.

### 14.1. Các cách thiết kế cuộc gọi downstream

| Mô hình | Điều kiện |
|---|---|
| **Token relay** | Chỉ phù hợp nếu downstream được issuer cho phép nhận chính token đó (audience/resource binding tương ứng) và risk policy chấp thuận |
| **Client credentials** | Orders API lấy service token mới dành cho Payments API theo service identity và permissions |
| **OAuth 2.0 Token Exchange (RFC 8693)** | Nếu AS hỗ trợ, đổi token/ủy quyền sang token dành cho downstream resource, giữ ràng buộc delegation thích hợp |
| **Gateway-issued internal identity** | Chỉ trong mô hình trust nội bộ được thiết kế, có xác thực service-to-service và chính sách chống giả mạo phù hợp |

Không giải quyết lỗi downstream 401 bằng cách cho Payments API chấp nhận frontend `client_id` như audience hoặc tắt audience check toàn hệ thống.

### 14.2. Gateway đã verify token thì downstream có cần kiểm tra lại không?

Tùy trust boundary. Nếu downstream được truy cập độc lập hoặc từ nhiều nguồn, nó nên xác thực access token và kiểm tra audience riêng. Nếu gateway là **điểm kiểm soát duy nhất được bảo đảm**, downstream có thể dựa trên một cơ chế identity/authorization được truyền nội bộ với bảo mật mạnh, nhưng đó phải là kiến trúc tin cậy chủ động — không phải suy luận “gateway kiểm tra issuer nên mọi service bỏ audience”.

### 14.3. Một token chung cho nhiều APIs có thể tăng rủi ro

Token có:

~~~json
{
  "aud": ["orders-api", "payments-api", "reports-api"],
  "scope": "orders.read payments.read reports.read"
}
~~~

có thể được chấp nhận tại ba resource nếu mỗi API áp `contains(...)`. Cần cân nhắc **phạm vi thiệt hại nếu token lộ**, các quyền tối thiểu và khả năng thu hồi. Access token riêng từng resource thường giúp hạn chế token replay sang API khác.

## 15. Khi Resource Server dùng opaque token/introspection

Audience không chỉ quan trọng với JWT ký. Nếu Resource Server dùng `oauth2ResourceServer().opaqueToken(...)` và RFC 7662 introspection, issuer có thể trả:

~~~json
{
  "active": true,
  "sub": "user-123",
  "client_id": "shop-spa-client",
  "scope": "orders.read",
  "aud": "https://api.example.test/orders",
  "exp": 1924992000
}
~~~

Resource Server vẫn phải chắc chắn access token dành cho Orders API. `active=true` chỉ nói token đang active theo ngữ nghĩa của AS, **không luôn đủ chứng minh resource binding**.

### 15.1. RFC 7662 không bảo đảm response luôn có `aud`

Introspection response có thể trả các metadata theo hợp đồng và quyền của caller introspection. Nếu Orders API bắt buộc audience:

- Thống nhất AS trả `aud` hoặc metadata resource tương đương.
- Hoặc yêu cầu AS **thực thi resource binding** khi quyết định `active` đối với introspection client của Orders API.
- Hoặc bổ sung một cơ chế xác minh resource đáng tin do tổ chức quản lý.
- Nếu không có đủ bằng chứng, **từ chối** thay vì coi thiếu `aud` là “chấp nhận tất cả”.

### 15.2. Ví dụ custom `OpaqueTokenIntrospector` kiểm tra audience

Giả sử có một `OpaqueTokenIntrospector` delegate đã thực hiện introspection với AS đáng tin:

~~~java
import java.util.Collection;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

final class AudienceCheckingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String expectedAudience;

    AudienceCheckingIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedAudience) {
        this.delegate = delegate;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Object aud = principal.getAttribute("aud");
        boolean accepted =
            (aud instanceof String value
                && expectedAudience.equals(value))
            || (aud instanceof Collection<?> values
                && values.contains(expectedAudience));

        if (!accepted) {
            throw new BadOpaqueTokenException(
                "Token audience does not match this API");
        }

        return principal;
    }
}
~~~

Đây là **decorator minh họa**, không phải một class của Spring Security có sẵn. Nó phải được gắn vào **introspector thực sự mà Resource Server sử dụng**. Nếu response không có `aud` và AS không cung cấp một bằng chứng binding khác theo hợp đồng, decorator từ chối token.

Các hệ thống có format `aud` khác (ví dụ một dữ liệu introspection-specific) cần bộ chuyển đổi metadata được định nghĩa riêng; không suy ngẫu nhiên từ `client_id` của frontend để thay thế.

### 15.3. Lỗi AS không được biến thành bỏ qua audience

Nếu introspection trả timeout, 5xx hoặc response thiếu trường bắt buộc, không tự tạo `OAuth2AuthenticatedPrincipal` với `aud=orders-api` để “giữ API hoạt động”. Không có kết quả xác minh đáng tin thì không cấp authentication. Nếu dùng cache introspection, chỉ dựa vào kết quả đã xác minh còn hiệu lực theo freshness/revocation policy.

## 16. Kiểm thử audience validator riêng biệt

Nên kiểm tra audience theo **hai tầng**:

1. **Unit test validator**: chứng minh policy so sánh audience đúng/sai, kể cả string/list, multi-audience và thiếu claim.
2. **Integration test Resource Server**: chứng minh Bearer JWT được **decoder thật** kiểm tra signature, issuer, audience, time trước khi tạo `Authentication`.

Nếu chỉ làm tầng một, có thể viết validator đúng nhưng quên gắn nó vào decoder HTTP thực. Nếu chỉ làm tầng hai bằng một JWT sai nhiều thứ cùng lúc, status 401 không chứng minh audience validator đã được dùng.

### 16.1. Tách validator thành class tái sử dụng

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class ApiAudienceValidator implements OAuth2TokenValidator<Jwt> {

    private final String expectedAudience;

    public ApiAudienceValidator(String expectedAudience) {
        if (expectedAudience == null || expectedAudience.isBlank()) {
            throw new IllegalArgumentException(
                "Expected API audience must be configured");
        }
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt token) {
        if (token.getAudience().contains(expectedAudience)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Access token is not intended for this resource",
                null
            )
        );
    }
}
~~~

Đặc điểm:

- `expectedAudience` do **server configuration** cung cấp, không lấy từ header/request input.
- Dùng so sánh chính xác `String.equals` qua `contains(...)`.
- Nếu claim `aud` không có hoặc không chứa resource identifier, validator trả lỗi.
- Thông báo lỗi **không echo token hoặc audience raw** ra response công khai.
- Đây chỉ là **claims validator**: chữ ký và issuer vẫn phải được kiểm tra bởi decoder/bộ validator được kết hợp.

Khi dùng class này trong decoder:

~~~java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        new ApiAudienceValidator(apiAudience)
    )
);
~~~

### 16.2. Unit test audience policy bằng `Jwt` tổng hợp

Dependency test:

~~~gradle
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Ví dụ:

~~~java
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.assertj.core.api.Assertions.assertThat;

class ApiAudienceValidatorTest {

    private static final String ORDERS =
        "https://api.example.test/orders";
    private static final String PAYMENTS =
        "https://api.example.test/payments";

    private final ApiAudienceValidator validator =
        new ApiAudienceValidator(ORDERS);

    private Jwt jwtWithAudiences(List<String> audiences) {
        Instant now = Instant.now();
        return Jwt.withTokenValue("test-only-placeholder")
            .header("alg", "RS256")
            .claim("iss", "https://login.example.test/realms/shop")
            .claim("aud", audiences)
            .issuedAt(now.minusSeconds(30))
            .expiresAt(now.plusSeconds(300))
            .build();
    }

    @Test
    void acceptsOrdersAudience() {
        var result = validator.validate(
            jwtWithAudiences(List.of(ORDERS)));
        assertThat(result.getErrors()).isEmpty();
    }

    @Test
    void rejectsPaymentsAudience() {
        var result = validator.validate(
            jwtWithAudiences(List.of(PAYMENTS)));
        assertThat(result.getErrors()).isNotEmpty();
    }

    @Test
    void allowsMultipleAudiencesWhenOrdersIsIncluded() {
        var result = validator.validate(
            jwtWithAudiences(List.of(PAYMENTS, ORDERS)));
        assertThat(result.getErrors()).isEmpty();
    }

    @Test
    void rejectsEmptyAudience() {
        var result = validator.validate(
            jwtWithAudiences(List.of()));
        assertThat(result.getErrors()).isNotEmpty();
    }
}
~~~

**Phạm vi của test này:** `Jwt.withTokenValue(...)` **không tạo JWT đã được ký** và cũng không gọi `JwtDecoder`. Nó chỉ kiểm tra một đối tượng `Jwt` do test dựng, sau đó trực tiếp gọi audience validator. Nó chứng minh logic **so sánh audience**, không chứng minh chữ ký, issuer/time hoặc wiring HTTP.

### 16.3. Test string vs array `aud`

Nếu issuer có thể trả một audience dạng chuỗi hoặc mảng, test thêm:

~~~text
aud = "https://api.example.test/orders"
aud = ["https://api.example.test/orders"]
aud = ["https://api.example.test/payments",
       "https://api.example.test/orders"]
aud = []
aud = missing
~~~

Để kiểm tra **claim conversion thật**, tạo JWT compact có chữ ký theo từng dạng payload rồi giải mã bằng `JwtDecoder` thực. Nếu test chỉ dựng `Jwt` object bằng builder, đang kiểm tra **đầu vào đã được chuẩn hóa** và chưa bao phủ serializer/parser của JWT JSON.

## 17. Kiểm thử HTTP với access token ký thật

Một cấu hình audience bảo mật phải được kiểm tra qua chính security filter chain đang chạy, không chỉ bằng unit test.

### 17.1. Ma trận tối thiểu

| Case | JWS signature | Issuer | Audience | Scope | Mong đợi |
|---|---|---|---|---|---|
| Token đúng | Đúng | Đúng | Orders API | `orders.read` | HTTP 200 nếu controller cho phép |
| Token sai audience | **Đúng** | Đúng | Payments API | `orders.read` | **401** |
| Token mang ID-token-like audience | Đúng | Đúng | Frontend client ID | Không có scope API | **401** nếu audience/profile kiểm soát đúng |
| Token sai issuer | Đúng | Sai | Orders API | `orders.read` | **401** |
| Token sai chữ ký | Sai | Đúng | Orders API | `orders.read` | **401** |
| Token hết hạn | Đúng | Đúng | Orders API | `orders.read` | **401** |
| Token thiếu scope | Đúng | Đúng | Orders API | `orders.create` | **403** |
| Không có token | Không áp dụng | Không áp dụng | Không áp dụng | Không áp dụng | **401** trên endpoint protected |

**Case sai audience phải được ký bằng cùng khóa tin cậy** với token đúng. Nếu token sai audience đồng thời sai chữ ký, 401 có thể chỉ chứng minh JWS verification từ chối và **không chứng minh audience validation**.

### 17.2. Tạo access token thử nghiệm bằng Nimbus JOSE/JWT

Một helper tạo token **có chữ ký RS256 thật**:

~~~java
import java.security.interfaces.RSAPrivateKey;
import java.time.Instant;
import java.util.Date;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

static String signedAccessToken(
        RSAPrivateKey testPrivateKey,
        String audience,
        String scope) throws JOSEException {

    Instant now = Instant.now();
    JWTClaimsSet claims = new JWTClaimsSet.Builder()
        .issuer("https://login.example.test/realms/shop")
        .subject("test-user")
        .audience(audience)
        .issueTime(Date.from(now.minusSeconds(30)))
        .notBeforeTime(Date.from(now.minusSeconds(30)))
        .expirationTime(Date.from(now.plusSeconds(300)))
        .claim("client_id", "shop-spa-client")
        .claim("scope", scope)
        .build();

    SignedJWT jwt = new SignedJWT(
        new JWSHeader.Builder(JWSAlgorithm.RS256)
            .keyID("test-key")
            .build(),
        claims
    );
    jwt.sign(new RSASSASigner(testPrivateKey));
    return jwt.serialize();
}
~~~

Để chạy integration test, tạo RSA key pair trong **test runtime** và cấu hình decoder thật tin đúng **test public key**. Trong production, decoder phải dùng JWKS/key từ issuer thật; **không** để private key test hoặc trust key test lọt vào production configuration.

### 17.3. Servlet: gửi JWT thật bằng `MockMvc`

Giả sử test application đã gắn `NimbusJwtDecoder` thật dùng test public key, issuer/time/audience validators và một controller `GET /api/orders/42`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersAudienceHttpTest {

    @Autowired
    MockMvc mockMvc;

    // Phải được khởi tạo bởi test fixture có public key tương ứng.
    RSAPrivateKey testPrivateKey;

    @Test
    void wrongResourceAudienceIsRejected() throws Exception {
        String token = signedAccessToken(
            testPrivateKey,
            "https://api.example.test/payments",
            "orders.read"
        );

        mockMvc.perform(get("/api/orders/42")
                .header("Authorization", "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Đây là **mẫu integration test**: để chạy phải cung cấp `testPrivateKey` bằng fixture/bean có lifecycle rõ, dùng đúng public key của cặp trong decoder, đồng thời tạo route/controller và issuer property như mô tả. Không thể chỉ dán class này vào production project rồi mặc định có key pair/controller.

### 17.4. WebFlux: gửi JWT thật qua `WebTestClient`

Với WebFlux và `NimbusReactiveJwtDecoder` thật:

~~~java
webTestClient
    .get()
    .uri("/api/orders/42")
    .headers(h -> h.setBearerAuth(
        signedAccessToken(
            testPrivateKey,
            "https://api.example.test/payments",
            "orders.read"
        )
    ))
    .exchange()
    .expectStatus().isUnauthorized();
~~~

Khi chuyển token sang `aud=https://api.example.test/orders`, cùng key/issuer/time/scope phải được chấp nhận ở authentication; nếu endpoint có controller và business policy cho phép, có thể nhận HTTP 200. Với token đúng audience nhưng `scope=orders.create`, rule GET đòi `orders.read` sẽ thường trả 403.

### 17.5. Vì sao `mockJwt()` và `jwt()` test helper chưa đủ?

Spring Security Test cung cấp `mockJwt()` cho WebFlux và `jwt()` cho Servlet. Chúng thường **tiêm vào context một authentication giả lập** để kiểm thử authorization, **không gọi decoder thật**. Ví dụ:

~~~java
// Có ích cho test HTTP authorization, KHÔNG chứng minh aud verification.
mockMvc.perform(get("/api/orders/42")
    .with(jwt().jwt(token -> token
        .claim("aud", "https://api.example.test/payments"))));
~~~

Đoạn này cần static import tương ứng khi dùng trong code test thực. Giá trị `aud` sai trong `mockJwt()`/`jwt()` có thể **vẫn được coi là principal đã xác thực**, vì mục tiêu của helper là bỏ qua token verification để test quyền.

Nếu muốn chứng minh **decoder có kiểm tra audience**, cần dùng **Bearer JWT ký thật** và để request đi qua `JwtDecoder`/`ReactiveJwtDecoder` thật. Có thể thêm unit test validator để cô lập nguyên nhân.

### 17.6. Bảo vệ CI và test fixtures

- Chỉ dùng private key sinh riêng trong test, không lấy signing key thật từ AS.
- Không commit raw access token thực của người dùng vào repository.
- Không in JWT trong assertion error, console log, trace hoặc artifact của CI.
- Tạo `exp` tương đối theo thời gian test để positive control không hết hạn sau vài tháng.
- Test JWT expired phải đặt `exp` đủ xa trong quá khứ để vượt clock skew.
- Không dùng ID token thật làm test fixture nếu không có môi trường/dữ liệu cho phép; có thể tạo JWT giả lập mang ID-token-like audience bằng test key.
- Nếu dùng JWKS HTTP test server, chỉ phục vụ public key ở loopback và dọn server sau test.

## 18. Bảng chẩn đoán các lỗi audience thường gặp

| Triệu chứng | Khả năng xảy ra | Cách xử lý an toàn |
|---|---|---|
| Access token có `aud=shop-spa-client` | Gửi ID token hoặc issuer phát token cho frontend/default audience | Xác nhận token type; yêu cầu **access token cho API resource** |
| Access token có `aud=payments-api` khi gọi Orders API | Client chọn nhầm resource/scope hoặc relay token sai | Yêu cầu token cho Orders API, không nới audience allowlist |
| Token issuer/chữ ký đúng nhưng 401 | Audience/time/profile validation từ chối | Đối chiếu API registration, không lộ raw JWT |
| Token audience đúng nhưng GET trả 403 | Thiếu `SCOPE_orders.read` hoặc quyền nghiệp vụ | Kiểm tra scope grant và HTTP/domain authorization |
| `aud` là API application GUID thay vì URI | Provider dùng ID của API registration cho token version này | Cấu hình đúng **API ID**, không phải SPA ID |
| `aud` không có | Token profile không có audience hoặc token không đúng loại/resource | Làm rõ issuance contract; từ chối nếu audience bắt buộc |
| Thêm `audiences` YAML nhưng token sai resource vẫn 200 | Property không được bind hoặc custom decoder ghi đè auto-configuration | Xác minh Spring Boot version và decoder thật |
| Thêm audience validator rồi token hết hạn được nhận | `setJwtValidator` thay mất default timestamp validators | Ghép `JwtValidators.createDefaultWithIssuer(...)` với audience |
| Frontend vẫn gửi token audience cũ | Client SDK cache/resource request chưa cập nhật | Yêu cầu token đúng resource theo SDK |
| Production chấp nhận token staging | Issuer/audience allowlist trộn môi trường | Tách trust configuration và test cross-env |
| Token dành cho API khác vẫn gọi được | Resource Server chỉ kiểm tra issuer/scope | Bổ sung resource audience validation |
| Một API tự lấy audience từ `Host` header | Expected audience bị ảnh hưởng bởi request | Dùng trusted configuration |
| JWT test sai audience vẫn pass `mockJwt()` | Test helper bypass decoder/validators | Dùng JWT ký thật qua Bearer HTTP |
| Token đa audience được nhận | Validator dùng `contains` | Xác định có được phép multi-resource hay không |
| Downstream từ chối incoming token | Token chỉ dành cho upstream API | Dùng token đúng downstream hoặc token exchange |
| Introspection `active=true` nhưng không có `aud` | AS chưa trả metadata resource | Thống nhất AS resource binding, fail closed khi thiếu bằng chứng |

### 18.1. Không đồng nhất mọi 401

~~~text
Token authentication errors:
    malformed token
    invalid JWS signature
    issuer not trusted
    audience mismatch
    expired / not-before
    token type/profile mismatch

Infrastructure errors:
    JWKS endpoint unavailable
    introspection timeout
    trusted key not currently available

Authorization errors:
    insufficient scope / role
    tenant/owner access denied
~~~

Nhiều lỗi authentication thường dẫn đến HTTP 401; authorization của principal đã xác thực thường dẫn đến 403. Lỗi hạ tầng có thể dùng status khác tùy exception handling. Khi chẩn đoán, cần biết **tầng thất bại** mà không phát tán credential hoặc claims nhạy cảm cho client.

### 18.2. Không lộ raw JWT khi xử lý lỗi

Không log:

~~~text
Authorization: Bearer eyJ...
client_secret=...
Full decoded claims from every request
~~~

Nên log loại lỗi với cardinality giới hạn:

~~~text
event=jwt_validation_failed reason=wrong_audience api=orders
event=jwt_validation_failed reason=invalid_issuer api=orders
event=jwt_validation_failed reason=expired api=orders
event=http_authorization_denied reason=insufficient_scope api=orders
~~~

Nếu cần correlation, dùng request/trace ID do hệ thống tạo. Không dùng raw token, `sub` hoặc `jti` làm metric label. Khi đánh giá token từ staging, chỉ kiểm tra claims trong môi trường được phép và qua công cụ đáng tin, không đưa access token thật lên website debug không được phê duyệt.

## 19. Những phản ví dụ có nguy cơ bảo mật

### 19.1. Lấy `client_id` của frontend làm audience mặc định

~~~java
// PHẢN VÍ DỤ:
String expectedAudience = frontendClientId;
~~~

Trừ khi contract quy định **chính giá trị đó là resource identifier của API** (rất khác với client ID frontend đơn thuần), cách này có thể chấp nhận token dành cho client chứ không dành cho API.

### 19.2. Chỉ kiểm tra issuer

~~~java
// PHẢN VÍ DỤ nếu API cần audience nhưng không bổ sung validator.
decoder.setJwtValidator(
    JwtValidators.createDefaultWithIssuer(issuer)
);
~~~

Điều này thiếu ràng buộc resource; token của cùng issuer dành cho API khác có thể được chấp nhận nếu những điều kiện còn lại đúng.

### 19.3. Chỉ kiểm tra scope

~~~java
// PHẢN VÍ DỤ nếu decoder không validate resource audience.
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

`hasAuthority` kiểm tra quyền trên principal **đã xác thực**, không tự đảm bảo token được phát hành cho Orders API. Phải có audience validation ở tầng token.

### 19.4. Cho qua khi `aud` không tồn tại

~~~java
// PHẢN VÍ DỤ:
boolean valid = jwt.getAudience().isEmpty()
    || jwt.getAudience().contains(expectedAudience);
~~~

Nếu hợp đồng access token bắt buộc có API audience, **thiếu `aud` là lỗi**, không phải “chấp nhận audience bất kỳ”.

### 19.5. Dùng substring hoặc wildcard không có hợp đồng

~~~java
// PHẢN VÍ DỤ:
boolean valid = jwt.getAudience().stream()
    .anyMatch(aud -> aud.startsWith("https://api.example.test/"));
~~~

Một prefix chung có thể bao phủ Orders, Payments, Admin và những API mới. Nếu API chỉ được nhận token Orders, phải kiểm tra **resource identifier chính xác**.

### 19.6. Dùng `aud` chưa xác minh để tin claims khác

~~~java
// PHẢN VÍ DỤ:
Map<String, Object> claims = decodeBase64Payload(rawJwt);
if (claims.get("aud").equals(expectedAudience)) {
    return makeAuthenticationFromClaims(claims);
}
~~~

`aud` trong JWT chưa xác minh có thể do attacker tự sửa. Chỉ sử dụng claims làm bằng chứng sau khi decoder verify chữ ký, allowed algorithm, trusted key và validators cần thiết.

### 19.7. Trộn `aud` của API với `azp` của caller

`azp`/`client_id` có thể cho biết calling client, nhưng không nhất thiết xác định resource nhận token. Một token có `azp=shop-spa-client` vẫn có thể dành cho Payments API. Nếu cần giới hạn caller, thêm client allowlist **ngoài** audience validation.

### 19.8. Cấu hình audience từ dữ liệu do client gửi

~~~java
// PHẢN VÍ DỤ:
String expectedAudience = request.getHeader("X-Expected-Audience");
~~~

Nếu người gửi tự chỉ định expected audience, họ có thể làm chính sách mất ý nghĩa. API resource identifiers phải đến từ **server-side trust configuration**.

### 19.9. Cho mọi API cùng một audience frontend

Orders, Payments và Admin API cùng chấp nhận `aud=shop-spa-client` sẽ khó phân biệt token nào thực sự cấp cho API nào, làm tăng nguy cơ replay xuyên dịch vụ. Một audience chung chỉ hợp lý nếu thực sự có **một resource/trust boundary thống nhất** và policy bổ sung, không phải vì tránh cấu hình issuer cho từng API.

### 19.10. Bỏ qua token type vì “đã có audience”

Audience là điều kiện quan trọng nhưng không nhất thiết đủ ngăn token substitution. Nếu issuer có nhiều JWT token types, có thể cần ràng buộc **access token profile**, `typ` hoặc các claims bắt buộc. Không tự áp `typ` cứng nếu issuer không dùng profile đó; cần thống nhất hợp đồng phát hành.

## 20. Tình huống triển khai qua ba giai đoạn

Giả sử Shop Web ban đầu chỉ dùng OIDC login, sau đó thêm Orders API.

### 20.1. Giai đoạn 1: chỉ đăng nhập OIDC

~~~text
Shop Web:
    client_id = shop-spa-client
    scope = openid profile

ID token:
    aud = shop-spa-client
~~~

Ở giai đoạn này, chưa có lý do để Orders API chấp nhận ID token của frontend. Token được phát hành cho **client identity flow**, không cho Orders API.

### 20.2. Giai đoạn 2: đăng ký resource Orders API

~~~text
Issuer:
    API/resource identifier = https://api.example.test/orders
    scopes = orders.read, orders.create
    client permissions:
        shop-spa-client được phép yêu cầu scopes

Frontend:
    yêu cầu access token cho resource Orders API
~~~

Tùy nhà phát hành, dùng `resource` RFC 8707, `audience` provider-specific hoặc API exposed scopes/mapper. Đảm bảo AS trả access token có `aud` đúng resource và không phát token cho clients chưa được phép.

### 20.3. Giai đoạn 3: bảo vệ Orders API

~~~text
Spring Resource Server:
    verify signature + trusted issuer
    require audience = https://api.example.test/orders
    require expiration/time validity

GET /api/orders/**:
    require SCOPE_orders.read

POST /api/orders:
    require SCOPE_orders.create

Service:
    require owner/tenant policy
~~~

Kiểm thử cho cả **token cũ sai audience**, token mới đúng audience và token hợp lệ thiếu scope. Sau rollout, token sai audience bị 401 là kết quả bảo mật mong muốn; client phải lấy đúng token.

### 20.4. Khi một API cần đổi audience identifier

Giả sử Orders API đổi resource ID từ `orders-api-v1` sang `https://api.example.test/orders`. Một quá trình migration có thể là:

1. Đăng ký resource identifier mới ở issuer và cấu hình đường cấp token mới.
2. Đảm bảo frontend/BFF có thể yêu cầu token dành cho resource mới.
3. Trong một cửa sổ ngắn được phê duyệt, API chấp nhận **hai identifier của cùng resource**, nếu không làm mở rộng trust boundary.
4. Theo dõi lượng token issuer phát hành theo identifier mới, không log raw token.
5. Đợi token dùng identifier cũ hết vòng đời phù hợp, sau đó gỡ legacy audience.
6. Chạy lại negative test: token cho Payments API và ID token frontend vẫn bị từ chối.

Nếu token mới bị 401 do issuer chưa được cấu hình, không thêm `shop-spa-client` vào allowlist cho nhanh. Sự cố cần giải quyết là **phát hành token cho resource đúng**, không phải mở cửa API cho token client-centric.

## 21. Bài tập tự kiểm tra

### Bài tập 1 — Token nào dành cho Orders API?

Cho:

~~~text
Frontend OAuth client ID = shop-spa-client
Orders API audience = orders-api

Token A:
    iss = trusted issuer
    aud = shop-spa-client
    scope = orders.read

Token B:
    iss = trusted issuer
    aud = orders-api
    scope = orders.read
~~~

**Câu hỏi:** Token nào nên vượt audience check của Orders API?

**Đáp án:** Token B, giả sử chữ ký, thời gian và token profile đều đúng. Token A không dành cho Orders API dù có cùng scope.

### Bài tập 2 — Vì sao ID token có `aud=client_id`?

**Câu trả lời:** Với OIDC, ID token được cấp cho **client** để chứng thực thông tin đăng nhập, nên audience thường là client ID. Resource Server API không được dùng điều đó làm lý do chấp nhận ID token thay access token.

### Bài tập 3 — API application ID và SPA client ID

Cho hệ thống:

~~~text
SPA client ID = SPA-123
API app registration ID = API-456
Issuer phát access token aud = API-456
~~~

**Câu hỏi:** Có được dùng `API-456` làm expected audience dù nó cũng là một application/client registration ID?

**Đáp án:** Có, **nếu issuer dùng chính API registration ID làm resource audience**. Không được thay bằng `SPA-123` chỉ vì SPA là OAuth client lấy token.

### Bài tập 4 — `aud` có nhiều giá trị

Cho:

~~~json
{
  "aud": ["orders-api", "payments-api"],
  "scope": "orders.read"
}
~~~

**Câu hỏi:** `jwt.getAudience().contains("orders-api")` trả true có nghĩa thiết kế hoàn toàn an toàn chưa?

**Đáp án:** Chưa đủ. Nó đúng với chính sách “ít nhất một audience là Orders”, nhưng phải kiểm tra issuer có cho phép token đa-resource không, scope/resource binding, nguy cơ replay và authorization nghiệp vụ. Nếu policy chỉ cho đúng một audience, cần validator chặt hơn.

### Bài tập 5 — Frontend đổi client ID

Giả sử Shop Web thay `client_id` từ `shop-spa-client-v1` sang `shop-spa-client-v2` nhưng vẫn gọi cùng Orders API.

**Câu hỏi:** Orders API có nên tự đổi expected audience theo frontend client ID không?

**Đáp án:** Không. Resource audience của Orders API có thể giữ nguyên. Nếu API giới hạn những OAuth clients được gọi, cập nhật **client allowlist/consent policy riêng**, không thay audience resource bằng một frontend ID.

### Bài tập 6 — JWT đúng chữ ký, sai audience

Token được ký bằng key issuer tin cậy, `iss`/`exp` đúng, `scope=orders.read` nhưng `aud=payments-api`. Resource Server cần xử lý gì?

**Đáp án:** Từ chối token ở bước **authentication/claims validation**, thường trả 401; không chuyển sang HTTP authorization để cấp phép dựa trên `orders.read`.

### Bài tập 7 — Token đúng audience, thiếu scope

Token đúng issuer/chữ ký/time, `aud=orders-api`, chỉ có `scope=orders.create`, nhưng client gọi GET cần `orders.read`.

**Đáp án:** Authentication có thể thành công; authorization từ chối vì thiếu `SCOPE_orders.read`, thường HTTP 403. Đây không phải lỗi audience.

### Bài tập 8 — Một JWKS cho nhiều APIs

Issuer sử dụng cùng JWK Set để ký token cho Orders và Payments APIs. Có thể chỉ kiểm tra chữ ký và issuer rồi chấp nhận ở cả hai không?

**Đáp án:** Không. Việc cùng ký bằng trusted issuer key không làm token cho Payments tự hợp lệ với Orders. Mỗi Resource Server vẫn phải kiểm tra resource audience hoặc bằng chứng binding tương đương.

### Bài tập 9 — Introspection không trả `aud`

AS trả `active=true`, `scope=orders.read` nhưng không có audience. Có được mặc định token dành cho Orders API?

**Đáp án:** Không, trừ khi có **hợp đồng đáng tin khác** bảo đảm AS đã kiểm tra resource binding cho introspection client của Orders API. Nếu không đủ bằng chứng theo policy, phải từ chối và thống nhất lại hợp đồng AS.

### Bài tập 10 — Gateway relay sang Payments

Shop Web nhận access token `aud=orders-api`, gateway đưa tới Orders API, Orders API chuyển nó sang Payments API. Payments API từ chối 401; có nên cho Payments chấp nhận token audience Orders không?

**Đáp án:** Không nên nới kiểm tra chỉ để relay hoạt động. Cần thiết kế token cho Payments API, client credentials, OAuth Token Exchange hoặc mô hình relay được issuer/architectural trust policy phê duyệt.

## 22. Checklist tích hợp nhà phát hành với API audience

### 22.1. Trước khi code

- [ ] Có sơ đồ xác định rõ **OAuth client**, **Authorization Server**, **Resource Server**.
- [ ] Biết `client_id` của frontend/BFF và **resource identifier của API** là hai vai trò khác nhau.
- [ ] Đã chốt issuer/realm/tenant và allowed signing algorithms.
- [ ] Đã chốt audience **đúng theo token profile của issuer**.
- [ ] Biết audience là URI, API application/client ID hay identifier khác theo provider.
- [ ] Biết cơ chế frontend yêu cầu access token cho resource: `resource`, provider-specific `audience` hoặc API exposed scopes/mapper.
- [ ] Đã phân biệt ID token và access token.
- [ ] Có danh sách scopes/permissions mà API cần.

### 22.2. Trong Spring Security

- [ ] JWT signature được xác minh bằng khóa/JWKS tin cậy.
- [ ] Claim `iss` được kiểm tra đối với trusted issuer.
- [ ] `aud` được kiểm tra theo **expected API audience**, không dựa vào frontend client ID.
- [ ] `exp`/`nbf` và những claims/profile bắt buộc được kiểm tra theo hợp đồng.
- [ ] Nếu dùng `setJwtValidator(...)`, vẫn ghép default issuer/time validators.
- [ ] Nếu dùng Spring Boot `jwt.audiences`, đã xác nhận property được phiên bản framework hỗ trợ và decoder thật áp dụng nó.
- [ ] HTTP method/path yêu cầu scopes/authorities phù hợp.
- [ ] Tenant/owner authorization được thực thi ở service/domain khi cần.
- [ ] Nếu multi-issuer, mỗi issuer có keys/audience/token profile phù hợp.
- [ ] Nếu opaque introspection, xác nhận AS cung cấp hoặc thực thi resource binding.
- [ ] Không bật wildcard/prefix audience matching ngoài policy.

### 22.3. Trong kiểm thử và vận hành

- [ ] Positive test: token đúng issuer, đúng audience, scope được chấp nhận.
- [ ] Negative test: token khác API nhưng cùng issuer, scope tương tự bị từ chối.
- [ ] Negative test: token ID-token-like dành cho frontend bị từ chối.
- [ ] Negative test: JWT sai chữ ký/sai issuer/hết hạn bị từ chối.
- [ ] Positive authentication nhưng thiếu scope tạo lỗi authorization, không bị nhầm với audience.
- [ ] Test JWT audience dùng **decoder thật**, không chỉ `mockJwt()`/`jwt()`.
- [ ] Không trộn token/keys của dev, staging và production.
- [ ] Raw access token/claims nhạy cảm không bị log trong lỗi 401/403.
- [ ] Token relay sang downstream chỉ được phép theo resource binding/trust contract.
- [ ] Có kế hoạch migrate audience identifier khi cần, cùng thời điểm gỡ legacy.

## 23. Tóm tắt

Hãy nhớ sự khác nhau giữa ba chuỗi:

~~~text
Frontend OAuth client:
    client_id = shop-spa-client

Authorization Server:
    iss = https://login.example.test/realms/shop

Orders Resource Server:
    expected aud = https://api.example.test/orders
~~~

Một access token dành cho Orders API có thể mang cả:

~~~json
{
  "iss": "https://login.example.test/realms/shop",
  "client_id": "shop-spa-client",
  "aud": "https://api.example.test/orders",
  "scope": "orders.read"
}
~~~

Điều này không mâu thuẫn: **`client_id` là bên xin token; `aud` là bên nhận token.** Tên audience có thể là URI API hoặc ID của **API application registration** theo issuer contract; điều quan trọng là không tự lấy client ID **của frontend** làm định danh resource.

Với Spring Security Resource Server, một cấu hình đáng tin cần kết hợp:

~~~text
trusted JWS key / issuer
    AND signature / allowed alg
    AND issuer + time / token profile validation
    AND audience = THIS API
    AND scope / HTTP authorization
    AND domain / tenant ownership checks
~~~

**Lỗi audience thường phải được sửa từ cả hai phía:** Authorization Server phải **phát hành access token cho đúng resource**, còn Resource Server phải **kiểm tra đúng resource audience**. Chỉ sửa frontend `client_id` hoặc bỏ validator có thể làm ứng dụng hoạt động bề ngoài nhưng phá vỡ ranh giới sử dụng access token giữa các APIs.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT), Audience Claim](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — NimbusJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Spring Security — JwtValidators Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtValidators.html)
- [Spring Boot — OAuth2 Resource Server Properties](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Keycloak Server Administration — Protocol Mappers / Client Scopes](https://www.keycloak.org/docs/latest/server_admin/)
- [Auth0 — API Authorization / Access Tokens](https://auth0.com/docs/secure/tokens/access-tokens)
- [Microsoft Identity Platform — Access Tokens](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens)
