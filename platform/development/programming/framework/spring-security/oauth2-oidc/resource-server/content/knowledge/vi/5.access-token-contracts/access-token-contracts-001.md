# Xác định API nhận token, nhà phát hành được tin cậy và mục đích truy cập

Một **OAuth 2.0 Resource Server** không nên chấp nhận access token chỉ vì token có chữ ký đúng hoặc do một hệ thống đăng nhập quen thuộc phát hành. Trước khi xử lý request, API phải xác định rõ ba yếu tố của **hợp đồng access token**:

1. **API nào được phép nhận token?** Đây là **đối tượng nhận** (audience/resource), thường thể hiện bằng claim `aud` trong JWT hoặc thông tin tương đương từ cơ chế introspection.
2. **Nhà phát hành nào được tin cậy?** Đây là **issuer** (bên phát hành), thường thể hiện bằng claim `iss`, gắn với một bộ khóa và quy tắc xác thực được cấu hình trước.
3. **Token được dùng để làm gì?** Đây là **mục đích và phạm vi quyền**, thể hiện bởi `scope`/`scp`, các policy theo tài nguyên và đôi khi là những claim đặc thù đã được thỏa thuận.

Ba câu hỏi tương ứng với **đúng nơi nhận**, **đúng nguồn cấp**, và **đúng mục đích**. Tách chúng ra sẽ ngăn việc một token hợp lệ về mật mã nhưng dành cho hệ thống khác lại được dùng để truy cập API hiện tại.

Bài học lấy bối cảnh module **Spring Security OAuth 2.0 OIDC Resource Server**. Các endpoint, issuer, audience, scope và token xuất hiện dưới đây là ví dụ giả lập; cần thay bằng giá trị đã được đội quản trị Authorization Server và API thống nhất.

## 1. Vị trí của Resource Server trong luồng OAuth 2.0 và OIDC

Một client nhận access token từ **Authorization Server** rồi gửi đến **Resource Server** để truy cập tài nguyên. Nếu Authorization Server cũng cung cấp OpenID Connect, nó đóng vai trò **OpenID Provider** đối với OIDC client. Điều này không làm thay đổi nguyên tắc: API sử dụng **access token**, không thay bằng **ID token**.

~~~mermaid
sequenceDiagram
    participant Client as OAuth 2.0 Client
    participant AS as Authorization Server / OIDC Provider
    participant Orders as Orders API (Resource Server)
    Client->>AS: Yêu cầu token theo grant phù hợp
    Note over AS: Kiểm tra client, quyền và resource được yêu cầu
    AS-->>Client: access_token với issuer, audience, scope
    Client->>Orders: Authorization: Bearer <access_token>
    Orders->>Orders: 1. Issuer có tin cậy?
    Orders->>Orders: 2. Audience có dành cho Orders API?
    Orders->>Orders: 3. Scope/policy có cho phép thao tác?
    Orders-->>Client: 2xx hoặc 401/403
~~~

Yêu cầu có thể là:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

Header `Authorization: Bearer ...` chỉ **vận chuyển credential**. Nó không cho biết token có hợp lệ không, có được phát hành cho Orders API không, hoặc có quyền đọc đơn hàng 42 không. Những điều kiện đó phải được kiểm tra tại Resource Server theo hợp đồng đã định.

## 2. Phân biệt issuer, audience, scope và principal

| Thành phần | Câu hỏi cần trả lời | Ví dụ | Điều kiện an toàn |
|---|---|---|---|
| `iss` — issuer | **Ai** phát hành token? | `https://login.example.test/realms/company` | Phải thuộc danh sách issuer API tin cậy, so khớp chính xác và xác minh chữ ký/nguồn token |
| `aud` — audience | Token **dành cho API/resource nào**? | `orders-api` | Phải chứa định danh audience được API này chấp nhận |
| `scope` / `scp` | Token được phép thực hiện **nhóm hành động nào**? | `orders.read orders.create` | Scope cần được ánh xạ và kiểm tra cho thao tác cụ thể |
| `sub` — subject | Token **đại diện cho ai/cái gì**? | `user-123` hoặc service principal | Chỉ sử dụng sau khi token đã xác thực; không mặc nhiên là tài khoản người dùng |
| `client_id` hoặc claim client tương đương | **Client nào** được cấp token? | `web-orders-client` | Hữu ích khi policy yêu cầu giới hạn client, nhưng không thay audience |
| `exp` / `nbf` / `iat` | Token **có hiệu lực trong khoảng nào**? | Unix timestamp | Kiểm tra hết hạn và mốc bắt đầu hiệu lực; cân nhắc sai lệch đồng hồ |
| `azp` (nếu có) | Authorized party theo profile token/nhà cung cấp | `web-orders-client` | Phải hiểu theo issuer/profile cụ thể; không mặc nhiên có ở mọi access token |
| Tenant/organization claim (nếu có) | Dữ liệu thuộc **tổ chức nào**? | `tenant-42` | Kiểm tra ràng buộc tenant và đối tượng nghiệp vụ theo thiết kế riêng |

Một JWT có thể chứa các claim trên, nhưng không có nghĩa **mọi access token đều phải có đủ chúng**. Các claim bắt buộc được xác định bởi token profile, quy ước của Authorization Server và yêu cầu của API. Với **opaque token**, các thuộc tính tương đương có thể đến từ introspection response hoặc policy đã được bảo đảm giữa các hệ thống.

### Ba điều kiện thường bị nhầm thành một

Giả sử có hai API trong cùng hệ thống:

~~~text
Authorization Server: https://login.example.test/realms/company

Orders API:
    Audience = orders-api
    Scope    = orders.read, orders.create

Billing API:
    Audience = billing-api
    Scope    = invoices.read, invoices.pay
~~~

Token có `iss` đúng bằng `https://login.example.test/realms/company` và `aud = ["billing-api"]` vẫn **không được** Orders API chấp nhận, dù hai API cùng tin cậy một issuer. Tương tự, token có `aud = ["orders-api"]` chưa đủ để gọi endpoint tạo đơn hàng nếu chỉ có scope `orders.read`.

**Issuer xác định nguồn phát hành; audience xác định nơi sử dụng; scope xác định loại hành động.** Việc biết client ID hay subject không thay thế bất kỳ điều kiện nào trong ba điều kiện đó.

## 3. Xác định API nhận token: audience và resource identity

Đầu tiên, đội thiết kế API cần thống nhất một **resource identifier** ổn định cho chính API. Ví dụ:

~~~text
Orders API identifier: orders-api
Billing API identifier: billing-api
~~~

Hoặc sử dụng định danh URI:

~~~text
Orders API identifier: https://api.example.test/orders
Billing API identifier: https://api.example.test/billing
~~~

Không có quy tắc bắt buộc mọi hệ thống phải dùng đúng một kiểu chuỗi cho `aud`. Điều quan trọng là **Authorization Server thực sự phát hành claim audience theo hợp đồng**, và Resource Server kiểm tra đúng giá trị đã được thống nhất. Nếu audience là URI, URI đó đóng vai trò định danh; nó không nhất thiết là URL mà mọi request sẽ gọi đến hoặc một endpoint có thể tải nội dung bằng HTTP.

Ví dụ token JWT phát hành đúng cho Orders API:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1924992000
}
~~~

Một access token chỉ nên được cấp với audience phù hợp với những Resource Server có thể xử lý token. Một token có audience quá rộng hoặc được mọi API dùng chung có thể dẫn đến **token substitution / confused deputy**: API này chấp nhận token vốn được cấp cho API khác.

### Audience không giống URL của từng endpoint

Ví dụ các request sau có thể dùng cùng audience `orders-api`:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Content-Type: application/json
~~~

`aud = "orders-api"` xác định **cả tài nguyên API được phép nhận token**. Việc request đến `GET /api/orders/42` hay `POST /api/orders` được giải quyết tiếp bằng **scope và quy tắc phân quyền**, không buộc mỗi URL phải có một audience riêng.

Ngược lại, nếu một API gateway có chung hostname cho nhiều backend, đừng tự suy ra rằng `aud = api.example.test` luôn đủ phân biệt mọi dịch vụ phía sau. Cần một ranh giới resource rõ ràng cho từng nhóm dữ liệu hoặc dịch vụ có chính sách truy cập độc lập.

### Audience có thể là mảng

Trong JWT, `aud` có thể biểu diễn một chuỗi đơn hoặc một mảng chuỗi theo chuẩn JWT. Ví dụ:

~~~json
{
  "aud": ["orders-api", "reporting-api"]
}
~~~

Resource Server phải kiểm tra **có audience được phép của mình** trong tập audience. Chỉ vì token chứa thêm audience không có nghĩa là nên chấp nhận mọi trường hợp multi-audience; chính sách cấp phát có thể yêu cầu token chỉ nhắm tới một API, hoặc một tập resource đã được phê duyệt. Hãy kiểm soát việc phát hành token nhiều audience để hạn chế phạm vi lộ token.

### Resource Indicators trong yêu cầu cấp token

OAuth 2.0 Resource Indicators (RFC 8707) cho phép client chỉ định **resource đích** bằng tham số `resource` nếu Authorization Server hỗ trợ. Ví dụ một request `client_credentials` dạng form:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Authorization: Basic <BASE64_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=orders.read&resource=https%3A%2F%2Fapi.example.test%2Forders
~~~

Giá trị `resource` được mã hóa form đúng quy tắc. Server có thể dùng resource indicator để quyết định audience của token; **không giả định `resource` và `aud` sẽ là cùng một chuỗi literal** nếu hệ thống áp dụng phép ánh xạ định danh. RFC 8707 là một khả năng của Authorization Server: việc gửi tham số `resource` không bảo đảm nó được hỗ trợ hay token luôn có `aud` chính xác theo mong đợi. Luôn đọc hợp đồng và kiểm tra token thực tế.

## 4. Xác định nhà phát hành được tin cậy: issuer

**Issuer** là danh tính của Authorization Server phát hành token. Trong JWT, claim `iss` thường là một URI và phải được so khớp **chính xác** với giá trị API đã cấu hình:

~~~text
Trusted issuer: https://login.example.test/realms/company
JWT "iss":      https://login.example.test/realms/company   → khớp
JWT "iss":      https://login.example.test/realms/personal  → không khớp
JWT "iss":      https://login.evil.test/realms/company      → không khớp
~~~

Đừng dùng kiểm tra đơn giản kiểu chuỗi có chứa `login.example.test`, bỏ qua tenant/realm, hoặc tự động tin mọi issuer có tên miền gần giống. Dấu gạch chéo cuối URI, path realm và cách chuẩn hóa có thể làm thay đổi giá trị issuer; cấu hình phải theo đúng metadata và token thực được cấp.

### Metadata, JWK Set và chữ ký

Với JWT access token có chữ ký số, Resource Server cần kiểm tra:

1. **Issuer đã tin cậy**: `iss` khớp với issuer được cấu hình.
2. **Khóa phù hợp và đáng tin**: chữ ký được xác minh bằng key từ JWK Set hoặc nguồn khóa **gắn với issuer đã tin cậy**.
3. **Thuật toán ký được cho phép**: giới hạn danh sách thuật toán phù hợp với chính sách, không giao quyền chọn trust cho dữ liệu chưa xác thực trong token.
4. **Thời gian hợp lệ**: token không hết hạn, chưa sử dụng trước `nbf`, và những giới hạn thời gian bổ sung được áp dụng.
5. **Audience và chính sách API**: kiểm tra các điều kiện ứng dụng; không dừng ở việc chữ ký đúng.

Đối với OpenID Provider hoặc Authorization Server có metadata, ứng dụng có thể lấy thông tin cấu hình qua endpoint discovery đã được xác định từ issuer. Trường `jwks_uri` trong metadata mô tả JWK Set được sử dụng để xác minh chữ ký. **JWK Set không tự định nghĩa issuer nào đáng tin**: nếu chỉ lấy khóa theo URL do token chưa xác minh chỉ ra, API có thể bị dẫn tới nguồn khóa của kẻ tấn công.

~~~mermaid
flowchart TD
    A["Trusted issuer cấu hình trước"] --> B["Discovery / metadata"]
    B --> C["JWK Set của issuer"]
    D["JWT nhận từ client"] --> E["Đọc header + claims như dữ liệu chưa tin"]
    C --> F["Xác minh chữ ký với thuật toán được phép"]
    E --> F
    F --> G["Kiểm tra exp, nbf, iss"]
    G --> H["Kiểm tra aud của API"]
    H --> I["Kiểm tra scope, policy, resource ownership"]
    I --> J["Cho phép xử lý request"]
~~~

Header JWT có thể chứa `kid` để gợi ý key trong tập khóa tin cậy. `kid` **không phải URL được phép tự tải**; những tham số như `jku` hoặc `x5u` nếu được hỗ trợ cần tuân thủ chính sách trust nghiêm ngặt. Không bật chấp nhận thuật toán `none` và không dựa vào thuật toán do token tự khai báo để bỏ qua allowlist của Resource Server.

### Key rotation và tính sẵn sàng

Authorization Server có thể thay đổi khóa ký. Resource Server thường cần cơ chế tải và cache JWK Set, cập nhật khi phát hành khóa mới và xử lý sự cố mạng theo chính sách. Khóa cũ có thể phải được duy trì trong thời gian các token đã phát hành còn hiệu lực. Thiết kế rotation là **hợp đồng vận hành** giữa đội Authorization Server và API, không phải lý do để tạm bỏ qua kiểm tra chữ ký.

### Một API tin cậy nhiều issuer

Trong hệ thống đa tổ chức hoặc đa môi trường, API có thể tin cậy nhiều issuer **đã được phê duyệt**. Khi đó:

- Xác định danh sách issuer và tập khóa tương ứng; không đăng ký issuer mới chỉ vì claim `iss` trong token có giá trị lạ.
- Chọn bộ xác thực theo issuer đã được allowlist, rồi kiểm tra chữ ký và `iss` bằng bộ đó.
- Kiểm tra **audience, scope và tenant** riêng cho từng issuer nếu hợp đồng khác nhau.
- Tránh dùng cùng quy tắc phân quyền cho mọi issuer nếu cùng tên scope nhưng ngữ nghĩa khác nhau.

Spring Security có các cơ chế `AuthenticationManagerResolver` hoặc resolver reactive để chọn authentication manager khi chạy đa issuer. Dù dùng cơ chế nào, trust decision phải xuất phát từ cấu hình tin cậy, không phải từ claim chưa xác thực.

## 5. Xác định mục đích truy cập: scope và policy

Issuer và audience xác nhận token đến từ đúng nhà phát hành và dành cho đúng API. Resource Server vẫn phải quyết định **token được phép làm việc gì**.

Một bảng quyền đơn giản cho Orders API:

| API operation | HTTP endpoint | Scope cần có | Kiểm tra nghiệp vụ bổ sung |
|---|---|---|---|
| Xem danh sách đơn của chính mình | `GET /api/orders` | `orders.read` | Lọc theo subject/tenant |
| Xem một đơn cụ thể | `GET /api/orders/{id}` | `orders.read` | Chủ đơn hàng hoặc người có quyền xem |
| Tạo đơn | `POST /api/orders` | `orders.create` | Khách hàng hoạt động; sản phẩm hợp lệ |
| Hủy đơn | `POST /api/orders/{id}/cancel` | `orders.cancel` | Trạng thái đơn và quyền chủ sở hữu |
| Xem toàn bộ đơn để quản trị | `GET /api/admin/orders` | `orders.admin.read` | Vai trò, tenant và policy quản trị |

Đây là **ví dụ hợp đồng quyền**, không phải danh sách scope được OAuth 2.0 quy định sẵn. Tên và ngữ nghĩa scope do hệ thống thiết kế và Authorization Server chấp thuận.

### Scope không đồng nhất với role

Ví dụ claim:

~~~json
{
  "scope": "orders.read orders.create"
}
~~~

Trong cấu hình JWT Resource Server thông thường, Spring Security ánh xạ `scope` hoặc `scp` thành các authority có tiền tố `SCOPE_`, ví dụ `SCOPE_orders.read` và `SCOPE_orders.create`. Điều đó khác với role như `ROLE_ADMIN`.

Một người giữ scope `orders.read` không tự nhiên được phép xem **mọi** đơn hàng. Nó chỉ cho phép loại thao tác đọc theo hợp đồng; sau đó API phải kiểm tra chủ sở hữu, tenant, trạng thái dữ liệu và điều kiện nghiệp vụ. Đặc biệt, không xem `sub` trong token là bằng chứng rằng path parameter `/orders/{id}` thuộc subject đó nếu chưa tra cứu và kiểm tra dữ liệu.

### Scope phải phù hợp với grant và principal

Với luồng người dùng ủy quyền (chẳng hạn Authorization Code + PKCE), token có thể đại diện cho một người dùng và các quyền đã cho phép client thực hiện. Với `client_credentials`, token thường đại diện cho **ứng dụng/dịch vụ**, không đại diện cho một người dùng cụ thể.

~~~text
Authorization Code:
  client = web-orders
  subject = user-123
  scope = orders.read
  mục đích = xem đơn hàng thuộc user-123

Client Credentials:
  client = inventory-sync
  subject = service principal (tùy token profile)
  scope = orders.read
  mục đích = đồng bộ theo quyền cấp cho service
~~~

Không suy diễn rằng mọi claim `sub` đều là tài khoản người thật. Nếu một endpoint chỉ cho phép truy cập **thay mặt người dùng**, cần có chính sách kiểm tra loại principal, loại grant hoặc các claim được bảo đảm trong token profile; chỉ kiểm tra scope chung có thể chưa đủ.

### Mục đích giao dịch không chỉ nằm trong scope

Một scope `payments.execute` có thể chỉ cho phép yêu cầu thực hiện thanh toán, nhưng **số tiền tối đa, tài khoản thụ hưởng, thời điểm, trạng thái phê duyệt** vẫn do policy nghiệp vụ quyết định. Một số kiến trúc dùng authorization details, rich authorization requests hoặc policy engine. Các trường bổ sung chỉ có ý nghĩa khi Authorization Server và Resource Server đã thống nhất cách cấp, kiểm tra và diễn giải.

## 6. Hợp đồng access token mẫu cho Orders API

Trước khi code, hai đội cần có một tài liệu hợp đồng độc lập với cấu hình framework:

| Mục | Giá trị minh họa | Ai chịu trách nhiệm |
|---|---|---|
| Resource Server | Orders API | Đội API |
| Resource identifier / expected audience | `orders-api` | Đội API + Authorization Server |
| Trusted issuer | `https://login.example.test/realms/company` | Đội bảo mật/identity |
| Token type | OAuth 2.0 access token; JWT ký số theo profile đã thỏa thuận | Authorization Server |
| JWK source | Metadata của trusted issuer, trỏ tới JWK Set được kiểm soát | Authorization Server + API |
| Allowed signing algorithms | Danh sách đã phê duyệt trong triển khai | Đội bảo mật |
| Required audience | `aud` chứa `orders-api` | API |
| Validity | `exp`, `nbf`, `iss` và giới hạn token age nếu hợp đồng có | API + Authorization Server |
| Scopes | `orders.read`, `orders.create`, `orders.cancel`, `orders.admin.read` | Product/security + API |
| Principal | End user hoặc service principal tùy grant, được phân biệt rõ | Authorization Server + API |
| Tenant boundary | Tenant của token phải phù hợp tenant của tài nguyên | API |
| Token transport | `Authorization: Bearer <token>` qua HTTPS | Client + API |
| Failure responses | `401` cho credential sai/thiếu; `403` cho thiếu quyền | API |
| Key rotation | Chính sách phát hành khóa mới và duy trì khóa cũ trong thời gian token còn hiệu lực | Authorization Server + vận hành |
| Observability | Request ID và mã lỗi; không log raw token | API + gateway |

Một tài liệu như vậy trả lời được những câu hỏi mà một vài property Spring Boot không mô tả hết: **issuer nào hợp lệ, audience nào hợp lệ, scope nào gắn với hành động nào, và dữ liệu nào được phép trả về cho principal**.

### JWT ví dụ theo hợp đồng

Payload minh họa:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "web-orders-client",
  "scope": "orders.read orders.create",
  "iat": 1924988400,
  "nbf": 1924988400,
  "exp": 1924992000
}
~~~

Đây là **payload minh họa**, không phải JWT có chữ ký có thể dùng để gọi API. Khi phát hành thực tế, Authorization Server cần ký token bằng thuật toán/key được Resource Server tin cậy. Các giá trị thời gian chỉ phục vụ ví dụ, không hàm ý token còn hiệu lực tại thời điểm đọc bài.

Để xử lý `GET /api/orders/42`, API kiểm tra từng bước:

1. Bearer credential có mặt và parse được.
2. Chữ ký/thuật toán/key hợp lệ theo trusted issuer.
3. Claim `iss` khớp trusted issuer.
4. Token đang trong thời gian có hiệu lực.
5. `aud` chứa `orders-api`.
6. Authority được ánh xạ bao gồm `SCOPE_orders.read`.
7. Đơn hàng 42 thuộc subject/tenant được phép truy cập, hoặc principal có quyền đọc hợp lệ theo policy.

Không bước nào phía sau được dùng để bỏ qua một bước xác thực bắt buộc phía trước.

## 7. Thực thi hợp đồng issuer + audience với Spring Security Resource Server

### 7.1. Cấu hình JWT cơ bản

Với Spring Boot và Spring MVC, các dependency thường dùng là:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Nếu chỉ cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
~~~

Spring Boot có thể cấu hình `JwtDecoder` theo issuer; Spring Security sẽ kiểm tra chữ ký, thời gian hiệu lực và issuer theo cấu hình mặc định thích hợp. **Điều đó chưa tự đảm bảo token có đúng audience của Orders API.** Chính sách yêu cầu `aud = orders-api` phải được khai báo và thực thi riêng, hoặc dùng cấu hình audience chính thức của phiên bản framework đang sử dụng nếu có.

Để minh họa đầy đủ và dễ nhìn thấy hợp đồng, ví dụ sau tự tạo decoder bean với validator rõ ràng cho issuer và audience.

### 7.2. Cấu hình tập trung và không trùng nguồn sự thật

Trong `application.yml`:

~~~yaml
app:
  security:
    jwt:
      issuer: https://login.example.test/realms/company
      audience: orders-api
~~~

Đây là namespace cấu hình **do ứng dụng định nghĩa**, không phải auto-configuration property có sẵn của Spring Boot. Bean phía dưới sử dụng chính hai giá trị này. Khi dùng cách tự định nghĩa `JwtDecoder`, không cần duy trì thêm một issuer thứ hai không đồng bộ ở `spring.security.oauth2.resourceserver.jwt.issuer-uri`.

### 7.3. Bean `JwtDecoder` kiểm tra issuer và audience

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class OrdersJwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withIssuerLocation(issuer)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> targetAudience = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Access token was not issued for this API",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                targetAudience
            )
        );
        return decoder;
    }
}
~~~

Cách đọc:

- `withIssuerLocation(issuer)` dùng issuer **được cấu hình trước** để xây dựng decoder và tìm metadata/JWK phù hợp; không lấy issuer lạ trong token rồi tự tin cậy.
- `JwtValidators.createDefaultWithIssuer(issuer)` tạo các kiểm tra thời gian và issuer mặc định phù hợp.
- `targetAudience` xác nhận danh sách `jwt.getAudience()` chứa đúng audience `orders-api`.
- `DelegatingOAuth2TokenValidator` yêu cầu các validator cùng áp dụng, không chỉ cần một điều kiện đúng.
- Khi audience không phù hợp, decoder từ chối token ở **bước xác thực**. Rule scope trong controller chưa cần chạy.

API ví dụ đang giả định **chỉ một issuer và một audience**. Nếu có nhiều issuer, cần resolver và một chính sách trust rõ ràng cho từng issuer; không đơn giản xóa `iss` validator hoặc cho phép audience bất kỳ.

Đoạn code còn giả định dùng loại JWT có thuật toán chữ ký tương thích cấu hình decoder. Trong sản phẩm thật, phải xác định **JWS algorithms được phép** cùng nguồn JWK được tin cậy. Không dựa vào header `alg` hoặc `jku` do token tự khai báo để mở rộng nguồn tin cậy.

### 7.4. Định nghĩa quyền URL bằng `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersHttpSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .requestMatchers(HttpMethod.POST, "/api/orders/*/cancel")
                    .hasAuthority("SCOPE_orders.cancel")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Lưu ý ví dụ này giả định **API thuần Bearer stateless, không dùng cookie/session để xác thực trình duyệt**, nên có thể vô hiệu hóa CSRF cho API. Nếu cùng ứng dụng còn sử dụng đăng nhập dựa trên cookie/session, cần thiết kế CSRF và security filter chains theo đúng các endpoint có nguy cơ; không sao chép `csrf.disable()` cho toàn hệ thống.

Các rule trên xác nhận scope sau khi decoder đã kiểm tra issuer và audience. `anyRequest().denyAll()` cố tình đóng các đường dẫn không thuộc hợp đồng minh họa; ứng dụng thực cần định nghĩa rõ health endpoints, CORS và các endpoint khác cần phục vụ.

**Thứ tự thực tế:** nhận request → `BearerTokenAuthenticationFilter` trích Bearer token → `AuthenticationManager`/`JwtAuthenticationProvider` xác thực qua `JwtDecoder` → chuyển scope sang authorities → `AuthorizationFilter` và policy kiểm tra quyền → controller/service.

### 7.5. Nếu dùng WebFlux

Đối với Spring WebFlux, mục tiêu **issuer/audience/scope** không đổi; tuy nhiên HTTP stack và decoder dùng các giao diện reactive:

| Chức năng | Servlet / Spring MVC | Reactive / WebFlux |
|---|---|---|
| Xây dựng security chain | `HttpSecurity` | `ServerHttpSecurity` |
| Bean security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| JWT implementation | `NimbusJwtDecoder` | `NimbusReactiveJwtDecoder` |
| Quy tắc URL | `authorizeHttpRequests` / `requestMatchers` | `authorizeExchange` / `pathMatchers` |
| Security context | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |

Ví dụ khai báo HTTP rule tương ứng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveOrdersSecurityConfig {

    @Bean
    SecurityWebFilterChain ordersChain(ServerHttpSecurity http) {
        return http
            .csrf(csrf -> csrf.disable())
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .pathMatchers(HttpMethod.POST, "/api/orders/*/cancel")
                    .hasAuthority("SCOPE_orders.cancel")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Quyết định tắt CSRF ở đây cũng chỉ áp dụng cho API thuần Bearer theo cùng giả định với Servlet. Với WebFlux, bean decoder tùy chỉnh phải là `ReactiveJwtDecoder` và sử dụng API reactive; không đặt `JwtDecoder` của Servlet vào nơi cần giao diện reactive. Ví dụ kiểm tra audience ở Servlet có thể được chuyển tương đương bằng validator của `NimbusReactiveJwtDecoder`, với cùng trusted issuer và danh sách audience đã thỏa thuận.

## 8. Hợp đồng với opaque token và introspection

Không phải mọi access token đều có thể đọc các claim trực tiếp như JWT. Với **opaque token**, Resource Server thường gọi **introspection endpoint** (RFC 7662) của Authorization Server để nhận trạng thái và các thuộc tính token.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Orders API
    participant AS as Trusted Authorization Server
    C->>API: Authorization: Bearer opaque-token
    API->>AS: Introspect token qua endpoint tin cậy
    AS-->>API: active + scope + subject + audience (nếu được cung cấp)
    API->>API: Kiểm tra chính sách resource và quyền
    API-->>C: 2xx / 401 / 403
~~~

Phản hồi introspection ví dụ có thể là:

~~~json
{
  "active": true,
  "iss": "https://login.example.test/realms/company",
  "aud": ["orders-api"],
  "client_id": "web-orders-client",
  "sub": "user-123",
  "scope": "orders.read",
  "exp": 1924992000
}
~~~

Trong RFC 7662, `active` là tín hiệu quan trọng nhưng **không tự động chứng minh token có audience phù hợp**. Các trường như `iss` và `aud` có thể được trả về tùy Authorization Server và profile. Vì thế cần làm rõ với đội Identity:

1. **Endpoint introspection nào được tin cậy**, xác thực Resource Server với endpoint ra sao, và giao tiếp qua TLS thế nào?
2. Introspection có chỉ trả `active: true` cho token phù hợp với resource đang gọi không, hay trả trạng thái chung cho mọi token của issuer?
3. Nếu nhiều Resource Server dùng cùng endpoint, làm sao phân biệt token dành cho Orders API và Billing API?
4. Scope và principal trả về có cùng ý nghĩa như với JWT không?
5. Khi timeout hoặc introspection không khả dụng, hệ thống **từ chối theo chính sách an toàn** ra sao; có cache không và cache ảnh hưởng thời gian thu hồi token thế nào?

Nếu introspection response không chứa audience, **không được suy ra rằng token mặc nhiên dành cho API**. Hợp đồng phải bảo đảm resource binding bằng chính sách tại Authorization Server/introspection, bằng dữ liệu liên quan đáng tin cậy, hoặc bằng bước validation do API kiểm soát.

Ví dụ Spring Boot property để sử dụng opaque token:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: orders-api
          client-secret: ${ORDERS_INTROSPECTION_SECRET}
~~~

`ORDERS_INTROSPECTION_SECRET` là tên biến môi trường minh họa. Không commit giá trị bí mật vào repository. Servlet có `OpaqueTokenIntrospector`, còn WebFlux có `ReactiveOpaqueTokenIntrospector`. Nếu cần audience validation riêng khi introspection trả thuộc tính bổ sung, hãy thực hiện qua cơ chế tùy biến introspector/policy phù hợp trước khi chấp nhận principal.

## 9. Phân biệt `aud`, `client_id`, `azp` và `sub` trong quyết định truy cập

Các claim về client và subject thường bị dùng nhầm làm audience:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "mobile-shop",
  "azp": "mobile-shop",
  "scope": "orders.read"
}
~~~

Ý nghĩa theo hợp đồng:

- `aud = orders-api`: xác định **API được phép nhận** token.
- `client_id = mobile-shop`: cho biết **client nhận/cầm token** nếu token profile bảo đảm claim này.
- `azp = mobile-shop`: claim **authorized party** nếu issuer phát hành, cần diễn giải theo profile cụ thể (rất phổ biến trong OIDC ID token, nhưng không bắt buộc ở mọi OAuth access token).
- `sub = user-123`: principal mà token đại diện theo cách Authorization Server định nghĩa.
- `scope = orders.read`: quyền thao tác đọc đã cấp trong token.

Nếu policy nói “Chỉ client `mobile-shop` được gọi endpoint này”, API cần **client identity validation** ngoài issuer, audience và scope. Nếu policy nói “User chỉ xem đơn hàng của mình”, API cần kiểm tra `sub` với chủ sở hữu thật của đơn hàng. Không thể dùng `client_id` để suy ra tài nguyên nhận token hoặc dùng `aud` để suy ra người sở hữu dữ liệu.

### Quyền của client và quyền của user là hai lớp

Xét một ứng dụng quản trị:

~~~text
Client: admin-console
User:   analyst-17
Scope:  orders.admin.read
Aud:    orders-api
~~~

API có thể yêu cầu đồng thời client nằm trong danh sách cho phép, user có quyền quản trị thuộc tổ chức, scope hợp lệ và tenant đúng. Nếu chỉ kiểm tra `scope`, endpoint có nguy cơ chấp nhận một service token hoặc delegated token không phù hợp loại đối tượng mà nghiệp vụ yêu cầu.

## 10. Một token đi qua nhiều API: không tự động được “đưa tiếp”

Giả sử Client gọi Orders API rồi Orders API cần gọi Billing API:

~~~mermaid
flowchart LR
    C["Client"] -->|"Access token A: aud=orders-api"| O["Orders API"]
    O -->|"Access token B: aud=billing-api"| B["Billing API"]
~~~

Nếu Orders API nhận token có audience `orders-api` rồi chuyển **nguyên token đó** sang Billing API, Billing API phải từ chối token vì `aud` không dành cho mình. Việc hai API cùng tin cậy issuer không có nghĩa chúng chia sẻ quyền sử dụng token.

Các hướng thiết kế hợp lệ tùy trường hợp:

| Tình huống | Cách tiếp cận |
|---|---|
| Orders API gọi Billing API bằng danh tính service | Lấy access token mới qua client credentials dành cho `billing-api` |
| Orders API cần gọi thay mặt user | Cân nhắc OAuth 2.0 Token Exchange (RFC 8693) hoặc luồng được Authorization Server hỗ trợ để nhận token mới với audience/scope phù hợp |
| API gateway bảo vệ nhiều backend | Làm rõ gateway là Resource Server cuối cùng hay mỗi backend cũng là Resource Server riêng; thiết kế trust và audience phù hợp |
| Một token cần dùng ở nhiều resource theo chính sách | Quy định rõ multi-audience và hậu quả khi một resource bị lộ token |

Không “giải quyết” audience mismatch bằng cách tắt validator ở Billing API. Điều đó làm mất ranh giới giữa các tài nguyên.

## 11. Multi-tenant: issuer đáng tin chưa chắc đủ để xác định tenant

Trong một SaaS đa tổ chức, hai request có thể cùng issuer, audience và scope nhưng thuộc **tenant khác nhau**:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "tenant_id": "tenant-A",
  "scope": "orders.read"
}
~~~

Nếu request gọi `GET /tenants/tenant-B/orders/42`, API phải kiểm tra điều kiện **tenant của principal phù hợp tài nguyên được yêu cầu**, hoặc quyền cross-tenant hợp lệ. Không được dùng path tenant do client gửi để tự chọn “quyền tenant” mà không đối chiếu với dữ liệu đáng tin.

Hai mô hình nhận dạng tenant thường gặp:

- **Issuer theo tenant**: mỗi tenant có một issuer riêng. API cần allowlist/registry issuer theo tenant và ánh xạ tenant chính xác sau xác thực.
- **Issuer dùng chung cho nhiều tenant**: tenant được mô tả bằng claim hoặc dữ liệu khác theo hợp đồng. API cần validator và policy phân quyền tenant.

Một claim như `tenant_id` không thuộc tập claim bắt buộc chung của JWT access token. Tên, ý nghĩa và nguồn tin cậy phải được thỏa thuận rõ, bao gồm quy tắc khi claim thiếu, không hợp lệ hoặc bị trùng giữa các issuer.

## 12. Quy tắc xử lý HTTP 401 và 403 theo hợp đồng token

| Tình huống | Phân loại | Phản hồi điển hình |
|---|---|---|
| Không có Bearer token ở endpoint bắt buộc xác thực | Thiếu credential | `401 Unauthorized` |
| Chữ ký JWT không hợp lệ hoặc thuật toán/key không được tin cậy | Authentication thất bại | `401 Unauthorized` |
| `iss` không thuộc trusted issuer | Authentication thất bại | `401 Unauthorized` |
| `aud` không chứa định danh Orders API | Authentication thất bại | `401 Unauthorized` |
| Token hết hạn hoặc chưa tới `nbf` | Authentication thất bại | `401 Unauthorized` |
| Opaque token có `active: false` | Authentication thất bại | `401 Unauthorized` |
| Token hợp lệ, thiếu `orders.read` | Authorization thất bại | `403 Forbidden` |
| Token hợp lệ, có scope nhưng yêu cầu đơn thuộc tenant khác | Authorization thất bại | `403 Forbidden`, hoặc chính sách che giấu tài nguyên có thể dùng `404` |
| Token hợp lệ, scope đúng, dữ liệu thuộc quyền principal | Được xử lý nghiệp vụ | `2xx` hoặc status do nghiệp vụ quyết định |

Các phản hồi mẫu theo Bearer Token Usage (RFC 6750):

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
~~~

Đây là **ví dụ**. Header chính xác còn phụ thuộc Spring Security, gateway và custom policy. Đừng để API tiết lộ token, chi tiết cấu hình khóa hoặc thông tin nội bộ không cần thiết trong response lỗi.

## 13. Tình huống đúng/sai: cùng issuer chưa đủ

Giả định Orders API có hợp đồng:

~~~text
TRUSTED_ISSUER = https://login.example.test/realms/company
EXPECTED_AUD   = orders-api
READ_SCOPE     = orders.read
~~~

| Access token | Kết quả khi `GET /api/orders/42` | Lý do |
|---|---|---|
| Issuer đúng, audience đúng, chưa hết hạn, scope `orders.read`, thuộc tài nguyên hợp lệ | Chấp nhận về mặt bảo mật API | Đúng nguồn, đúng nơi nhận, đúng quyền |
| Issuer đúng, audience `billing-api`, scope `orders.read` | Từ chối ở authentication | Token dành cho API khác |
| Issuer `https://login.evil.test`, audience `orders-api`, scope `orders.read` | Từ chối ở authentication | Issuer không tin cậy |
| Issuer đúng, audience đúng, chỉ có `orders.create` | Từ chối ở authorization | Không có quyền đọc |
| Issuer đúng, audience đúng, scope đọc, token hết hạn | Từ chối ở authentication | Token không còn hiệu lực |
| Issuer đúng, audience đúng, scope đọc, chữ ký sai | Từ chối ở authentication | Không chứng minh được tính toàn vẹn/token origin |
| ID token có `aud = web-orders-client` | Từ chối làm API access token | Sai loại token và audience |
| Issuer đúng, audience đúng, scope đọc, đơn hàng thuộc người/tenant khác | Từ chối ở authorization | Quyền nghiệp vụ không đạt |

**Thứ tự đánh giá rất quan trọng:** API chỉ sử dụng claims để phân quyền khi chúng đến từ token đã được xác thực theo trusted issuer và các ràng buộc bắt buộc. Trước thời điểm đó, JWT header/payload chỉ là dữ liệu do request mang tới.

## 14. Các lỗi thiết kế hợp đồng thường gặp

### 14.1. Chỉ cấu hình `issuer-uri` rồi mặc định API đã “chọn đúng token”

Spring Security có thể xác minh chữ ký, issuer và thời hạn nhờ `issuer-uri`. Nếu API yêu cầu `aud = orders-api`, audience validation vẫn cần được khai báo/kiểm tra phù hợp. Một Authorization Server cấp token cho nhiều API thì kiểm tra issuer đơn độc không phân biệt nơi nhận.

### 14.2. So khớp issuer quá rộng

Không dùng kiểm tra substring, suffix tùy tiện hoặc chấp nhận mọi realm chỉ vì hostname trông giống nhau. Các issuer dưới cùng một hệ thống identity có thể phục vụ các tenant hoặc môi trường có trust policy khác nhau. **Khóa hợp lệ của issuer A** không làm issuer B tự nhiên được tin cậy.

### 14.3. Tin URL khóa được nhúng trong JWT

Thông tin `kid`, `jku`, `x5u` và `alg` trong JOSE header ban đầu vẫn là dữ liệu của một token **chưa xác thực**. Không cho phép token tự chọn JWK Set hoặc algorithm ngoài danh sách đã được cấu hình/phê duyệt. Nguồn khóa phải được gắn với issuer đã tin cậy.

### 14.4. Dùng scope thay audience

Nếu token dành cho Billing API nhưng tình cờ có claim `scope = orders.read`, Orders API vẫn phải từ chối nếu `aud` không phù hợp. Scope định nghĩa **hành động**, không định nghĩa **nơi nhận** token.

### 14.5. Dùng audience thay quyền nghiệp vụ

`aud = orders-api` không nói token được phép đọc, tạo, hủy đơn hàng; nó chỉ định đúng Resource Server. Muốn phân quyền thao tác phải kiểm tra scope/authority và policy áp dụng cho tài nguyên.

### 14.6. Dùng ID token làm access token

Trong OIDC, ID token được phát hành để client biết thông tin xác thực của người dùng. ID token có thể có chữ ký hợp lệ, `sub` và `iss` đúng, nhưng audience thường hướng tới client, không phải Resource Server. API cần xác thực **access token** đúng profile của nó.

### 14.7. Giả định token `client_credentials` luôn có end-user

Token client credentials thường đại diện cho một service/client. Việc API gán token đó cho một user cụ thể chỉ dựa vào `sub` không được bảo đảm. Hợp đồng phải mô tả sự khác nhau giữa quyền ứng dụng và quyền người dùng.

### 14.8. Tin `active: true` là đã thỏa mọi điều kiện

Trong introspection, `active: true` phản ánh trạng thái token theo Authorization Server. Nó có thể chưa đủ để chứng minh audience/scope/tenant của Orders API. Cần chính sách resource binding và kiểm tra quyền tương ứng.

### 14.9. Chuyển nguyên token cho mọi dịch vụ downstream

Token dành cho Orders API không tự động được Billing API sử dụng. Nếu cần gọi API khác, hãy xin token phù hợp với destination và cơ chế delegation đã được phê duyệt.

### 14.10. Coi `jti` là cơ chế thu hồi token tự động

`jti` có thể là định danh token, nhưng Resource Server không tự biết token đã bị thu hồi chỉ vì có claim này. Với JWT xác minh cục bộ, cần thiết kế token lifetime, revocation strategy, event propagation hoặc cơ chế kiểm tra khác theo rủi ro hệ thống.

## 15. Một tình huống tích hợp hoàn chỉnh giữa Client, Authorization Server và Orders API

Giả sử sản phẩm yêu cầu người dùng xem đơn hàng của mình:

**Bước 1 — Đội API công bố hợp đồng:**

~~~text
API:               Orders API
Audience:          orders-api
Trusted issuer:    https://login.example.test/realms/company
Required scope:    orders.read
Protected route:   GET /api/orders/{id}
Principal:         end user, theo token profile đã thống nhất
Additional rule:   order.ownerId == authenticatedPrincipal.subject
~~~

**Bước 2 — Đội Authorization Server cấu hình resource và quyền:**

- Client `web-orders-client` được phép yêu cầu quyền `orders.read` theo grant và consent/policy phù hợp.
- Token cấp cho Orders API phải có audience `orders-api`.
- Access token có issuer đã thống nhất, thời hạn phù hợp, và chữ ký theo khóa công khai mà API được phép xác thực.
- Claim nhận diện user/client và tenant được công bố theo profile, tránh để API tự đoán ý nghĩa.

**Bước 3 — Client lấy token và gọi API:**

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN_FOR_ORDERS_API>
Accept: application/json
~~~

**Bước 4 — Resource Server xác thực:**

~~~text
Trích Bearer token
    ↓
Kiểm tra chữ ký + thuật toán + nguồn khóa
    ↓
Kiểm tra iss == trusted issuer
    ↓
Kiểm tra exp/nbf và ràng buộc thời gian
    ↓
Kiểm tra aud chứa orders-api
    ↓
Tạo Authentication từ principal và authorities
    ↓
Kiểm tra scope orders.read
    ↓
Tải đơn 42, kiểm tra ownerId/tenant theo nghiệp vụ
    ↓
Trả tài nguyên hoặc từ chối
~~~

**Bước 5 — Khi thay đổi hợp đồng:** Nếu Authorization Server đổi issuer, định danh audience, cấu trúc scope hoặc token profile, API phải được cập nhật có kiểm soát. Nếu issuer đổi khóa ký, đội vận hành cần bảo đảm JWK discovery/cache và chính sách rotation hoạt động; không được bỏ validation để tránh gián đoạn.

## 16. Những quyết định cần được xác nhận trước khi tích hợp thật

| Chủ đề | Câu hỏi cần trả lời rõ trong đặc tả |
|---|---|
| Resource identity | Audience chính thức của API là gì? Có trường hợp multi-audience không? |
| Issuer trust | API cho phép issuer nào cho production/staging? Có trust tách theo tenant không? |
| Token format | JWT hay opaque? Nếu JWT dùng token profile, thuật toán và JWK Set nào? |
| Token validity | TTL tối đa, clock skew, `nbf`, `exp`, chính sách revocation và key rotation? |
| Client profile | Grant nào được phép? Có phân biệt delegated user với service principal? |
| Access rights | Scope nào cho từng HTTP operation? Có policy về subject, tenant, ownership? |
| Custom claims | Claim client, tenant, organization, roles lấy từ đâu và ý nghĩa chính xác là gì? |
| Introspection | Opaque token được xác minh ở endpoint nào; endpoint bảo đảm resource binding ra sao? |
| Multi-API calls | Có token exchange hoặc xin token mới cho downstream không? |
| Failure contract | 401/403 và mã lỗi nào trả về; có cần `WWW-Authenticate`/`scope`? |
| Transport | Chỉ nhận Bearer header qua HTTPS hay có ngoại lệ giao thức được duyệt? |
| Logging | Field nào được log; token, secret và dữ liệu định danh được che như thế nào? |
| Ownership | Ai chịu trách nhiệm thay đổi issuer, audience, scope, key và tài liệu tích hợp? |

Đặc tả nên mô tả **giá trị cụ thể, nguồn cung cấp và chủ sở hữu** của mỗi quy tắc. Những câu chung chung như “JWT hợp lệ” hay “client được phân quyền” thường chưa đủ để hai nhóm triển khai chính xác cùng một hợp đồng.

## 17. Gợi ý các kịch bản kiểm thử hợp đồng

Với ví dụ Orders API, bộ kiểm tra tích hợp có thể bao gồm:

| Kịch bản | Điều kiện | Kỳ vọng |
|---|---|---|
| Đúng issuer/audience/scope | JWT ký hợp lệ, chưa hết hạn, `aud = orders-api`, có `orders.read` | Cho vào tầng nghiệp vụ |
| Sai issuer | JWT được issuer khác phát hành | Từ chối xác thực |
| Sai audience | JWT được cấp cho `billing-api` | Từ chối xác thực |
| Thiếu audience bắt buộc | JWT không có `aud` hoặc audience rỗng | Từ chối xác thực theo hợp đồng |
| Token hết hạn | `exp` đã qua | Từ chối xác thực |
| Token chưa có hiệu lực | `nbf` lớn hơn thời điểm hợp lệ | Từ chối xác thực |
| Chữ ký sai | Payload/chữ ký đã bị sửa, hoặc ký bằng khóa không tin cậy | Từ chối xác thực |
| Thuật toán không được phép | Token sử dụng JWS algorithm ngoài allowlist | Từ chối xác thực |
| Thiếu scope | Token hợp lệ chỉ có `orders.create` khi gọi GET | Từ chối phân quyền |
| Sai tenant | Token hợp lệ thuộc tenant A truy cập dữ liệu tenant B | Từ chối theo policy |
| Token service gọi endpoint dành cho user | Không có ngữ cảnh end-user theo hợp đồng | Từ chối theo policy |
| Opaque token inactive | Introspection trả `active: false` | Từ chối xác thực |
| Endpoint không có token | Endpoint bảo vệ thiếu `Authorization` | Yêu cầu xác thực |
| Token của API A bị forwarding tới API B | `aud` không dành cho B | B từ chối xác thực |

Khi sử dụng `spring-security-test`, **mock JWT** rất tiện để kiểm thử rule scope/authority của controller. Tuy nhiên, mock JWT thường bỏ qua decoder thật nên **không chứng minh** issuer discovery, chữ ký, audience validator hoặc introspection đã hoạt động đúng. Những điều kiện này cần kiểm thử tích hợp qua decoder/token hoặc hệ thống kiểm thử token riêng.

## 18. Ghi nhớ hợp đồng nhận access token

Một Resource Server nên coi việc chấp nhận token là một chuỗi điều kiện bắt buộc:

~~~text
Token được chấp nhận cho request
  =
  Đúng loại access token theo hợp đồng
  AND Chữ ký / introspection đáng tin
  AND Issuer thuộc danh sách tin cậy
  AND Token còn hiệu lực
  AND Audience dành cho API hiện tại
  AND Scope/authority phù hợp thao tác
  AND Chính sách chủ thể, tenant, tài nguyên được thỏa
~~~

**API nhận token** được nhận diện bằng audience/resource identity. **Nhà phát hành tin cậy** được xác định bằng issuer, metadata, khóa và thuật toán đã phê duyệt. **Mục đích truy cập** được thực thi bằng scope, authority và kiểm tra dữ liệu nghiệp vụ. Ba lớp này cần tồn tại đồng thời; bỏ một lớp có thể làm API chấp nhận token sai ngữ cảnh dù các lớp còn lại có vẻ hợp lệ.

Với Spring Security Resource Server, `issuer-uri` là nền tảng hữu ích cho xác thực JWT, nhưng hợp đồng thực tế phải mở rộng đến **audience validation**, quyền thao tác và quyền truy cập từng tài nguyên. Đó là cách triển khai nguyên tắc **token được cấp cho đúng API, bởi đúng nhà phát hành và để thực hiện đúng công việc**.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth 2.0 Resource Server Opaque Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
