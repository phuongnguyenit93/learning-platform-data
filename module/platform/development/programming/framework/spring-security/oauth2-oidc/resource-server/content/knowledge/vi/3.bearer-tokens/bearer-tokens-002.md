# Authorization: Bearer và cấu trúc yêu cầu HTTP có token

Trong OAuth 2.0, một **Resource Server** cung cấp API được bảo vệ và chỉ xử lý những yêu cầu đáp ứng chính sách xác thực, phân quyền. Cách phổ biến nhất để client gửi **access token** đến Resource Server là đặt token trong HTTP request header:

~~~http
Authorization: Bearer <ACCESS_TOKEN>
~~~

Ở đây, `<ACCESS_TOKEN>` là **ký hiệu giữ chỗ để đọc tài liệu**, không được gửi kèm dấu `<` và `>` vào request thật. Client thay toàn bộ ký hiệu này bằng chuỗi access token nhận từ Authorization Server. Giá trị `Bearer` là **authentication scheme**, còn chuỗi phía sau là **credential**.

Bài học giải thích cú pháp header, vị trí của nó trong một HTTP request, cách đọc các trường hợp GET/POST/HTTP/2, quan hệ với JWT và opaque token, phản hồi 401/403, và cách Spring Security Resource Server sử dụng header này trong thực tế.

## 1. Vì sao Resource Server cần access token?

Trong kiến trúc OAuth 2.0, client thường không gửi mật khẩu người dùng cho API. Sau khi hoàn thành một quy trình cấp quyền phù hợp, client nhận access token từ **Authorization Server** rồi trình token khi gọi **Resource Server**. Resource Server kiểm tra token trước khi cho phép thao tác trên tài nguyên.

~~~mermaid
sequenceDiagram
    participant U as User / Client
    participant AS as Authorization Server / OIDC Provider
    participant RS as Resource Server (API)
    U->>AS: Luồng cấp quyền OAuth 2.0
    AS-->>U: access_token
    U->>RS: GET /api/profile + Authorization: Bearer token
    RS->>RS: Trích token, xác thực và phân quyền
    alt Hợp lệ và đủ quyền
        RS-->>U: 200 OK + dữ liệu
    else Thiếu / sai token
        RS-->>U: 401 Unauthorized
    else Đã xác thực nhưng thiếu quyền
        RS-->>U: 403 Forbidden
    end
~~~

Access token là **thông tin cho phép truy cập tài nguyên**, không phải mật khẩu tài khoản và cũng không nhất thiết là một JWT. Trong OpenID Connect (OIDC), phản hồi có thể còn có **ID token** để client nhận thông tin định danh người dùng; ID token **không thay thế access token** khi gọi API. Spring Security OAuth 2.0 Resource Server được cấu hình để xác thực access token phù hợp với API.

## 2. Mổ xẻ dòng `Authorization: Bearer ...`

HTTP sử dụng field `Authorization` để client gửi thông tin xác thực cho tài nguyên đang yêu cầu. Với Bearer token, cách viết thông dụng là:

~~~text
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9....
└───────────┘  └────┘ └───────────────────────────────────────────┘
 Tên header     Scheme               Access token
~~~

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| `Authorization` | Tên HTTP header mang credential | `Authorization` |
| `:` | Dấu phân cách tên và giá trị header | `:` |
| `Bearer` | Loại cơ chế xác thực; server hiểu đây là Bearer credential | `Bearer` |
| Dấu cách sau `Bearer` | Phân tách scheme và token | `Bearer eyJ...` |
| `<ACCESS_TOKEN>` | Chuỗi token thực được cấp phát | JWT ba phân đoạn hoặc opaque token |

Chữ **Bearer** nghĩa là bên **đang nắm giữ token** có thể trình token để sử dụng các quyền mà token mang lại. Token thuộc loại Bearer không mặc nhiên ràng buộc với khóa riêng hay thiết bị của client. Vì vậy, **lộ token có thể dẫn đến truy cập trái phép trong thời gian token còn hiệu lực**.

### Cú pháp trên HTTP

Theo mô hình `Authorization` trong HTTP và phương thức truyền Bearer token của RFC 6750, giá trị header gồm `Bearer`, ít nhất một dấu cách, rồi đến chuỗi token.

~~~http
Authorization: Bearer abc.def.ghi
~~~

Chuỗi `abc.def.ghi` ở đây chỉ minh họa hình dạng JWT. Token thật không nhất thiết có dấu chấm.

Những điểm cần nhớ:

- Tên field HTTP **không phân biệt chữ hoa/chữ thường**: `Authorization` và `authorization` là cùng một header theo quy tắc HTTP.
- Authentication scheme `Bearer` cũng được nhận diện không phân biệt hoa/thường theo quy tắc của HTTP authentication, nhưng nên ghi thống nhất `Bearer` để dễ đọc và tương thích.
- Sau scheme là **giá trị token thuần**; không bọc trong dấu nháy kép, không thêm tiền tố `Bearer` lần thứ hai, không kèm các ký tự placeholder.
- Không tách một token thành nhiều dòng hoặc nhét xuống dòng vào giá trị header. HTTP client thông thường sẽ kiểm soát việc mã hóa header; dữ liệu đầu vào không được gây CR/LF injection.
- Tránh gửi đồng thời nhiều cách truyền cùng một Bearer token trong một request. Ví dụ vừa đặt `Authorization` vừa gắn `access_token` vào URL là cách sử dụng không đúng tinh thần RFC 6750.

Ví dụ đối chiếu:

~~~text
ĐÚNG:  Authorization: Bearer abc.def.ghi

SAI:   Authorization: abc.def.ghi
       # Thiếu authentication scheme Bearer.

SAI:   Authorization: Bearer Bearer abc.def.ghi
       # Lặp lại scheme trong giá trị token.

SAI:   Authorization: Bearer "abc.def.ghi"
       # Dấu nháy kép không thuộc token.

SAI:   Authorization: Bearer <ACCESS_TOKEN>
       # Nếu gửi nguyên văn thì đây chỉ là placeholder.
~~~

Lưu ý các dòng `SAI` thể hiện lỗi **so với giá trị token mong muốn trong ví dụ**, không phải tất cả đều có cùng mã lỗi hoặc cùng nguyên nhân parser trên mọi máy chủ.

## 3. Một HTTP request có Bearer token gồm những gì?

Xét yêu cầu GET tới API:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
User-Agent: orders-client/1.0

~~~

Hình thức này là request HTTP/1.1 mang tính minh họa. Trong request thật, client thay placeholder bằng access token; dòng trống kết thúc phần header. Với GET không có request body, không cần tự thêm `Content-Type`.

| Dòng/thành phần | Ý nghĩa |
|---|---|
| `GET /api/orders/42 HTTP/1.1` | **Request line**: phương thức, đường dẫn tài nguyên (request target), phiên bản HTTP |
| `Host: api.example.test` | Host đích; bắt buộc với HTTP/1.1 |
| `Authorization: Bearer ...` | Credential để Resource Server xác thực |
| `Accept: application/json` | Client mong muốn định dạng phản hồi JSON |
| `User-Agent: orders-client/1.0` | Thông tin nhận diện HTTP client; không phải bằng chứng xác thực |
| Dòng trống | Ranh giới giữa phần header và phần body (nếu có) |
| Body (tùy phương thức) | Dữ liệu nghiệp vụ như JSON; Bearer token vẫn ở header |

**Đường dẫn không chứa Bearer token.** Dấu `?` trong một URL query có thể mang tham số lọc hoặc phân trang, nhưng không nên chứa access token. Việc đặt token trong query dễ làm token lộ qua lịch sử trình duyệt, log của proxy/server, công cụ phân tích và các hệ thống quan sát URL.

### Request POST có JSON body

Request vẫn dùng header `Authorization`, nhưng thêm metadata mô tả payload:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
Content-Type: application/json
Content-Length: 21

{"sku":"A42","qty":2}
~~~

Ở đây:

- `Authorization` dùng cho **xác thực**.
- `Content-Type` cho biết **định dạng dữ liệu gửi lên**.
- `Content-Length: 21` là kích thước payload JSON minh họa theo byte trong UTF-8; HTTP client thường tự điền đúng giá trị này.
- Body `{"sku":"A42","qty":2}` là **nội dung nghiệp vụ**, không phải nơi chứa credential.

Không nhất thiết phải có body với mọi POST, và những phương thức như PUT/PATCH cũng có thể sử dụng cùng header Authorization. Bearer token không bị giới hạn ở `GET` hay `POST`: phương thức nào có được phép thực hiện hay không phụ thuộc **quy tắc phân quyền của API**, không phụ thuộc vào sự tồn tại của header một cách độc lập.

## 4. Khi dùng HTTPS, URL và header được truyền thế nào?

Ví dụ URL:

~~~text
https://api.example.test/api/orders/42
│       │                │
Scheme  Host             Path
~~~

Trình duyệt hoặc HTTP client gửi request qua kết nối TLS đến máy chủ phù hợp. Với HTTPS, **header Authorization, path và body** được bảo vệ trên đường truyền bằng TLS giữa các điểm kết thúc TLS. DNS và một số metadata kết nối vẫn có thể quan sát được tùy hạ tầng; không suy luận rằng TLS che giấu mọi metadata.

Khi ứng dụng nằm sau reverse proxy/API gateway:

~~~mermaid
flowchart LR
    A["Client"] -->|"HTTPS + Authorization: Bearer"| B["API Gateway / Reverse Proxy"]
    B -->|"Forward request theo cấu hình"| C["Spring Security Resource Server"]
    C --> D["Controller / Service"]
~~~

Hệ thống phải cấu hình gateway để chuyển tiếp credential đúng cách tới dịch vụ **được phép nhận token**. Nếu gateway bỏ header `Authorization`, Resource Server sẽ thấy request không có Bearer token và có thể trả `401`. Nếu gateway đã xác thực token trước, cần quy định rõ dịch vụ phía sau tin cậy thông tin nào, thay vì coi header tự tạo từ client là thông tin định danh đáng tin.

**`Authorization` không phải `Proxy-Authorization`**: header thứ hai liên quan đến xác thực với proxy, không thay thế Bearer credential của API. Khi qua nhiều hop, cần bảo vệ kết nối giữa các service và chỉ chuyển token đến đúng service nhận.

## 5. HTTP/2 và HTTP/3 có gì khác?

Ví dụ HTTP/1.1 là dạng văn bản dễ học. HTTP/2 và HTTP/3 truyền header theo cơ chế mã hóa/truyền khung của giao thức, không dùng nguyên văn request line kiểu `GET /... HTTP/1.1`. Các thông tin tương đương được biểu diễn bằng pseudo-header:

~~~http
:method: GET
:scheme: https
:authority: api.example.test
:path: /api/orders/42
authorization: Bearer <ACCESS_TOKEN>
accept: application/json
~~~

Trong HTTP/2 và HTTP/3, tên header được viết **chữ thường**, vì vậy thường thấy `authorization` thay cho `Authorization`; ý nghĩa không đổi. Pseudo-header `:method`, `:scheme`, `:authority`, `:path` không phải những header ứng dụng tùy ý có thể thêm theo cách thông thường. HTTP library chịu trách nhiệm tạo request hợp lệ theo phiên bản kết nối.

Đối với lập trình viên Spring, **không cần viết riêng mã đọc token cho từng HTTP version**. Spring Security nhận thông tin từ abstraction HTTP phù hợp với runtime, sau đó thực hiện xác thực Bearer token.

## 6. JWT và opaque token đều truyền bằng Bearer header

**Vị trí của access token trong request không quyết định định dạng token.** Một Resource Server có thể được cấu hình để xác thực JWT hoặc thực hiện introspection của opaque token; client vẫn sử dụng cùng cú pháp:

~~~http
Authorization: Bearer <ACCESS_TOKEN>
~~~

### 6.1. JWT access token

JWT compact ký số phổ biến có dạng:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Ví dụ payload sau khi giải mã phần claim có thể có:

~~~json
{
  "iss": "https://idp.example.test/realms/demo",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1924992000
}
~~~

Claim mẫu minh họa mục đích:

| Claim | Công dụng |
|---|---|
| `iss` | Issuer: bên phát hành token |
| `sub` | Subject: định danh principal |
| `aud` | Audience: tài nguyên/dịch vụ token hướng tới |
| `exp` | Mốc hết hạn |
| `nbf` | Thời điểm token bắt đầu có hiệu lực, nếu có |
| `scope` hoặc `scp` | Các scope/quyền được cấp theo token |

Các claim của JWT **không được coi là đáng tin chỉ vì giải mã Base64URL thành công**. Resource Server phải kiểm tra chữ ký, thuật toán và khóa được tin cậy, tính hợp lệ về thời gian, issuer và audience yêu cầu trước khi sử dụng claim làm cơ sở phân quyền.

### 6.2. Opaque access token

Opaque token có thể là chuỗi ngẫu nhiên, chẳng hạn:

~~~http
Authorization: Bearer tkn_f7a91c2b8e4d6a50
~~~

Resource Server không suy ra quyền hoặc danh tính từ hình dạng chuỗi. Nó thường gọi **OAuth 2.0 token introspection endpoint** của Authorization Server và chỉ chấp nhận token khi token active và đáp ứng chính sách API. Đoạn `tkn_f7a91c2b8e4d6a50` cũng chỉ là token giả để minh họa.

Không thể nhận diện một token là “an toàn” chỉ qua việc nó có hai dấu chấm như JWT hay có tiền tố `tkn_`. **Hợp đồng giữa Authorization Server, client và Resource Server** xác định token format và phương thức xác thực.

### 6.3. Access token khác ID token

Khi dùng OIDC, client có thể nhận cả `access_token` và `id_token`. Vị trí sử dụng cần rõ:

| Token | Bên nhận chính | Mục đích |
|---|---|---|
| OAuth 2.0 access token | Resource Server / API | Quyền truy cập tài nguyên |
| OIDC ID token | OIDC client (relying party) | Thông tin về sự kiện xác thực/danh tính |
| Refresh token (nếu có) | OAuth 2.0 client gửi tới token endpoint | Xin access token mới theo quy định của Authorization Server |

Không gửi refresh token trực tiếp đến API dưới dạng `Authorization: Bearer ...`. Cũng không dùng ID token làm access token chỉ vì nó có định dạng JWT và chứa claim `sub`.

## 7. Tạo request có Bearer token từ các HTTP client

### 7.1. cURL trên terminal

Giả sử biến môi trường `ACCESS_TOKEN` đã chứa access token thực; cách đặt biến phụ thuộc shell và hệ thống cấp token.

**Bash/Zsh:**

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json" \
  "https://api.example.test/api/orders/42"
~~~

Với POST JSON:

~~~bash
curl -i \
  -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  --data '{"sku":"A42","qty":2}' \
  "https://api.example.test/api/orders"
~~~

`-i` yêu cầu in response header để quan sát status và `WWW-Authenticate`. Tránh đặt token trực tiếp trong shell history; không đưa output có credential thật vào issue tracker, tài liệu chia sẻ hoặc nhật ký.

**Windows PowerShell:**

~~~powershell
$token = $env:ACCESS_TOKEN
curl.exe -i -H "Authorization: Bearer $token" -H "Accept: application/json" "https://api.example.test/api/orders/42"
~~~

Dùng `curl.exe` để gọi chương trình cURL trực tiếp trên Windows, tránh sự khác biệt của alias `curl` trong một số phiên bản PowerShell.

### 7.2. JavaScript `fetch`

~~~javascript
async function getOrder(accessToken, orderId) {
  const response = await fetch(
    "https://api.example.test/api/orders/" + encodeURIComponent(orderId),
    {
      method: "GET",
      headers: {
        "Authorization": "Bearer " + accessToken,
        "Accept": "application/json"
      }
    }
  );

  if (!response.ok) {
    throw new Error("API request failed: HTTP " + response.status);
  }

  return response.json();
}
~~~

Hàm nhận `accessToken` đã được cấp qua luồng OAuth 2.0 phù hợp. Ví dụ **không** mô tả cách lấy hoặc lưu trữ token trong trình duyệt; client không được tự biến ID token thành access token.

### 7.3. Java `RestClient` và `WebClient`

Spring cung cấp helper `HttpHeaders.setBearerAuth(String)` để gắn token vào header. Truyền **chuỗi token thuần**, không truyền cả tiền tố `Bearer `:

~~~java
import org.springframework.web.client.RestClient;

public class OrderApiClient {
    private final RestClient client = RestClient.create("https://api.example.test");

    public String getOrder(String accessToken, String orderId) {
        return client.get()
            .uri("/api/orders/{id}", orderId)
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);
    }
}
~~~

`RestClient` phù hợp cho cách gọi đồng bộ ở Spring Framework hiện đại. Với ứng dụng reactive, có thể dùng `WebClient` theo cách tương đương:

~~~java
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public class ReactiveOrderApiClient {
    private final WebClient client =
        WebClient.create("https://api.example.test");

    public Mono<String> getOrder(String accessToken, String orderId) {
        return client.get()
            .uri("/api/orders/{id}", orderId)
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

Trong Postman, Insomnia hoặc công cụ HTTP tương tự, chọn kiểu **Bearer Token** rồi thường chỉ nhập token thuần; công cụ tự thêm scheme `Bearer`. Nếu nhập `Bearer abc.def.ghi` vào chính ô Bearer Token, request có thể thành `Authorization: Bearer Bearer abc.def.ghi`.

### 7.4. Body JSON không thay thế Authorization header

~~~javascript
async function createOrder(accessToken, order) {
  const response = await fetch("https://api.example.test/api/orders", {
    method: "POST",
    headers: {
      "Authorization": "Bearer " + accessToken,
      "Content-Type": "application/json",
      "Accept": "application/json"
    },
    body: JSON.stringify(order)
  });

  if (!response.ok) {
    throw new Error("Cannot create order: HTTP " + response.status);
  }

  return response.json();
}
~~~

Token nằm ở `Authorization`; body chứa dữ liệu `order`. Đưa token vào field JSON như `{"accessToken":"..."}` không tự động làm Spring Security nhận được Bearer credential và không phải cơ chế chuẩn mặc định.

## 8. Spring Security đọc `Authorization: Bearer` như thế nào?

Đối với **Servlet Resource Server** (thường dùng Spring MVC), đường xử lý điển hình:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Spring Security Filter Chain"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D["Trích token từ Authorization header"]
    D --> E["AuthenticationManager"]
    E --> F["Xác thực JWT hoặc introspect opaque token"]
    F --> G["Authentication + GrantedAuthority"]
    G --> H["Kiểm tra quyền theo endpoint"]
    H --> I["Controller"]
~~~

`BearerTokenAuthenticationFilter` nhận credential và chuyển cho `AuthenticationManager`. Với JWT, Resource Server dùng `JwtDecoder` và validators; với opaque token, nó sử dụng `OpaqueTokenIntrospector`. Sau xác thực, Spring Security tạo `Authentication` kèm authorities để kiểm tra quyền truy cập.

Ví dụ cấu hình Spring MVC bảo vệ `GET /api/orders/**` bằng scope `orders.read`:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
~~~

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ApiSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

`issuer-uri` ở đây là URL ví dụ. Với issuer thực, Spring Security có thể kiểm tra chữ ký, issuer và mốc thời gian của JWT; nếu ứng dụng yêu cầu giới hạn `aud`, cần bổ sung audience validation. **Có header Authorization không đồng nghĩa token sẽ được chấp nhận**: token phải hợp lệ và có đủ quyền theo rule.

Trên **WebFlux**, đầu mối tương ứng là `SecurityWebFilterChain`, `AuthenticationWebFilter`, `ServerHttpSecurity` và các thành phần reactive. Dù Spring MVC hay WebFlux, HTTP client vẫn gửi cú pháp giống hệt:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>

~~~

Spring Security JWT Resource Server thường chuyển `scope = "orders.read profile"` thành authorities `SCOPE_orders.read` và `SCOPE_profile`. Rule `hasAuthority("SCOPE_orders.read")` kiểm tra đúng scope. Sau HTTP authorization, service vẫn phải kiểm tra quyền đối với **đơn hàng cụ thể**, chẳng hạn chủ sở hữu hoặc tenant.

## 9. HTTP 401, 403 và `WWW-Authenticate`

**`Authorization`** là header request do client gửi. **`WWW-Authenticate`** là header response dùng để thông báo cơ chế xác thực và, khi phù hợp, nguyên nhân bị từ chối.

### 9.1. Thiếu access token

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Accept: application/json

~~~

Với endpoint yêu cầu xác thực, phản hồi thường là:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"

~~~

`realm="orders-api"` minh họa không gian bảo vệ do API định nghĩa. Khi request không có credential, server thường không cần gửi mã lỗi Bearer chi tiết trong challenge.

### 9.2. Token hết hạn hoặc không hợp lệ

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"

~~~

Server có thể thêm:

~~~http
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token", error_description="The access token expired"
~~~

`invalid_token` thường liên quan đến token hết hạn, bị thu hồi, hỏng, hoặc không đáp ứng validation. Thực tế header lỗi có thể khác tùy cấu hình và cách hạn chế lộ chi tiết nội bộ.

### 9.3. Token hợp lệ nhưng không đủ scope

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.read"

~~~

`scope="orders.read"` mô tả quyền cần có, **không tự cấp quyền** cho client. Client phải xin quyền hợp lệ từ Authorization Server theo chính sách.

### 9.4. Request Bearer sai cấu trúc

Nếu request truyền token bằng nhiều phương thức cùng lúc, hoặc tham số Bearer sai quy cách, RFC 6750 mô tả lỗi `invalid_request` thường gắn với `400 Bad Request`. Tuy vậy, status thực tế còn phụ thuộc tầng từ chối (HTTP parser, reverse proxy, bearer token resolver, security filter, custom policy). Không nên khẳng định mọi header sai đều trả `400`.

| Tình huống | Status thường gặp | Ý nghĩa |
|---|---|---|
| Không có credential ở endpoint yêu cầu xác thực | `401` | Cần Bearer token hợp lệ |
| Access token sai, bị thu hồi hoặc hết hạn | `401` | `invalid_token` |
| Access token hợp lệ, không đủ quyền | `403` | `insufficient_scope` hoặc rule phân quyền |
| Request Bearer sai cấu trúc | `400` trong trường hợp `invalid_request` | Request không hợp lệ |
| Token hợp lệ và đủ quyền | Do controller quyết định | Tiếp tục xử lý nghiệp vụ |

Token ký đúng bởi issuer nhưng sai **audience của API** cũng cần bị từ chối trong quá trình xác thực nếu Resource Server cấu hình audience validator. Đây thường là `401`, không phải `403` do thiếu scope.

## 10. Browser và CORS preflight với Authorization

Khi JavaScript trên `https://app.example.test` gọi `https://api.example.test`, request là **cross-origin**. Header `Authorization` không thuộc nhóm CORS-safelisted request headers, vì vậy browser thường thực hiện **preflight OPTIONS**:

~~~http
OPTIONS /api/orders/42 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization

~~~

Một phản hồi có thể là:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Authorization, Content-Type
Vary: Origin

~~~

Sau preflight hợp lệ, trình duyệt mới gửi request chứa token:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json

~~~

**Preflight thường không mang Bearer credential.** Nếu ứng dụng bắt xác thực cho mọi OPTIONS trước khi xử lý CORS, browser có thể hiện lỗi CORS dù Bearer token dùng cho request thật hoàn toàn hợp lệ. Cần cấu hình CORS hợp lý cho origin, method, header và tích hợp đúng thứ tự với Spring Security. CORS là chính sách trình duyệt, **không thay thế** authentication/authorization của Resource Server. cURL không thực thi hạn chế CORS như browser.

## 11. Những nơi không nên đặt Bearer token

RFC 6750 mô tả Authorization header và những phương thức khác như form-encoded body, URI query trong các điều kiện cụ thể. Với API hiện đại, **đặt token ở header là lựa chọn ưu tiên**:

| Vị trí | Ví dụ | Đánh giá |
|---|---|---|
| Header `Authorization` | `Authorization: Bearer token123` | **Khuyến nghị** khi dùng HTTPS |
| URL query | `/api/orders?access_token=token123` | **Tránh** vì log, history, analytics dễ ghi lại URL |
| Form body `application/x-www-form-urlencoded` | `access_token=token123` | Chỉ cân nhắc nếu có yêu cầu tương thích giao thức cụ thể |
| JSON body | `{"accessToken":"token123"}` | Không phải Bearer credential mặc định của Spring Security |
| Header tùy biến | `X-Access-Token: token123` | Không được nhận trừ khi API có cơ chế riêng |
| Cookie | `Cookie: access_token=token123` | Thuộc mô hình khác; cần đánh giá CSRF, session và origin |

Spring Security Resource Server mặc định ưu tiên trích token từ `Authorization`. Nếu muốn lấy token từ nơi khác, phải cấu hình `BearerTokenResolver` ở Servlet hoặc converter phù hợp ở WebFlux. Không bật nhiều nguồn nhận token chỉ để tiện test mà thiếu chính sách kiểm soát rõ.

## 12. Bảo vệ token trên đường truyền và trong ứng dụng

Bearer token là credential có thể bị người khác sử dụng nếu chiếm được; vì vậy:

1. **Bắt buộc dùng HTTPS** giữa client và API; bảo vệ các đường kết nối nội bộ phù hợp với mô hình hạ tầng.
2. **Không ghi token thật vào log** của ứng dụng, proxy, APM, browser console, CI hoặc công cụ theo dõi lỗi.
3. **Không nhúng token trong URL**, kể cả khi debug; tránh token xuất hiện trong browser history và access log.
4. **Chỉ chuyển token tới API dự kiến**; đặc biệt thận trọng khi redirect hoặc gọi sang host của bên thứ ba.
5. **Giới hạn thời hạn, scope, audience** theo nhu cầu sử dụng, giảm thiệt hại nếu token bị lộ.
6. **Xác thực chữ ký/issuer/time/audience** và áp dụng phân quyền nghiệp vụ tại Resource Server.
7. **Không gửi refresh token hoặc ID token cho API** thay cho access token.
8. **Chọn nơi lưu token dựa trên loại client và rủi ro**, nhất là XSS/storage/session trong browser.

TLS bảo vệ dữ liệu khi truyền giữa các điểm kết thúc TLS, nhưng proxy, gateway và service có thể nhìn thấy header sau khi giải mã. Cần kiểm soát quyền truy cập và quy tắc redaction ở các thành phần này.

## 13. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `401` dù client đã đặt token | Header không tới API, biến môi trường rỗng, token hết hạn | Kiểm tra cách tạo request, gateway, thời gian token |
| `401` với token vừa phát hành | Sai issuer, JWK, audience, thuật toán hoặc token type | Đối chiếu chính sách xác thực của API |
| `401` khi dùng công cụ Bearer Token | Truyền cả scheme vào ô đã tự thêm `Bearer` | Chỉ nhập token thuần |
| `401` với `Authorization: Basic ...` | Nhầm HTTP authentication scheme | Dùng `Bearer` và access token đúng |
| `403` dù token hợp lệ | Thiếu scope/authority hoặc thiếu quyền nghiệp vụ | Kiểm tra mapping `SCOPE_*` và policy |
| Browser báo CORS, cURL chạy được | OPTIONS preflight bị chặn hoặc cấu hình CORS thiếu | Kiểm tra request/response preflight |
| Backend không nhìn thấy `Authorization` | Proxy/gateway không forward header | Kiểm tra cơ chế forwarding an toàn |
| Token trong query không được nhận | Mặc định Spring đọc Bearer từ header | Chuyển token vào `Authorization` |
| API A chấp nhận token, API B từ chối | Token không dành cho audience/issuer/scope của API B | Cấp token phù hợp với API B |

Khi debug, cần tách ba trường hợp: **không gửi đúng credential**, **xác thực thất bại**, và **xác thực thành công nhưng phân quyền thất bại**. Không sửa lỗi 401 bằng cách vô hiệu hóa JWT validation hoặc mở quyền mọi URL.

## 14. Ví dụ nhận diện request và response

**A. GET endpoint công khai** không nhất thiết cần token:

~~~http
GET /public/catalog HTTP/1.1
Host: api.example.test
Accept: application/json

~~~

Nếu `/public/catalog` được đặt `permitAll`, thiếu header `Authorization` là bình thường.

**B. GET endpoint bảo vệ** cần Bearer token:

~~~http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json

~~~

**C. POST JSON** có cả header xác thực và body:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Content-Type: application/json
Accept: application/json
Content-Length: 21

{"sku":"A42","qty":2}
~~~

**D. Token hợp lệ nhưng thiếu `orders.write`**:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.write"

~~~

**E. Token hết hạn**:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"

~~~

Client cần xin access token mới bằng quy trình OAuth 2.0 hợp lệ; gửi lặp lại chính token đã hết hạn không giải quyết vấn đề.

## 15. Câu hỏi tự kiểm tra

**1. Client có access token `abc.def.ghi`. Header nào đúng?**

~~~http
Authorization: Bearer abc.def.ghi
~~~

Token nằm sau scheme `Bearer`, không bọc thêm nháy kép.

**2. POST đã có `Content-Type: application/json`, vậy API có thể xác thực chưa?** Chưa. Header này chỉ cho biết định dạng body, không thay thế Bearer credential.

**3. Vì sao 401 khác 403?** `401` thường nghĩa là credential thiếu hoặc không hợp lệ; `403` thường nghĩa là xác thực được nhưng thiếu quyền theo chính sách.

**4. JWT giải mã Base64URL thành công đã đáng tin chưa?** Chưa. Phải kiểm tra chữ ký, issuer, thời hạn, audience và validation khác theo hệ thống trước khi sử dụng claims.

**5. Vì sao browser gửi OPTIONS không có token?** Đó thường là CORS preflight để hỏi server có cho phép gửi header `Authorization` trong request thật hay không.

## 16. Tổng kết

Một request được bảo vệ bởi Bearer authentication mang **method, path, các HTTP header** và dòng xác thực:

~~~http
Authorization: Bearer <ACCESS_TOKEN>
~~~

Với GET, token ở header dù không có body. Với POST/PUT/PATCH, token **vẫn ở header**, còn body chứa dữ liệu nghiệp vụ. Dù Resource Server chạy **Spring MVC/Servlet** hay **Spring WebFlux**, cú pháp HTTP client gửi là như nhau. Spring Security sẽ trích token, xác minh JWT hoặc introspect opaque token, tạo principal, ánh xạ authorities và kiểm tra quyền.

Luôn sử dụng **HTTPS**, gửi đúng **access token** tới đúng API, tránh URL/query/log chứa token, kiểm tra **issuer/audience/thời hạn/scope** và phân biệt **401** với **403** khi xử lý phản hồi.

## Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — Servlet Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — Reactive Bearer Tokens](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — Servlet Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
