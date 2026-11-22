# Resource Server không tự cấp mới hoặc làm mới token của client

Trong kiến trúc **OAuth 2.0 và OpenID Connect (OIDC)**, **Resource Server** là dịch vụ cung cấp tài nguyên được bảo vệ bằng access token. Nó xác thực access token đi kèm một request, kiểm tra quyền truy cập và trả kết quả của API. Khi token hết hạn hoặc không hợp lệ, Resource Server phải từ chối request; nó **không tự tạo access token mới, không tự đổi refresh token và không cấp token thay thế cho client**.

Đây là ranh giới quan trọng khi xây dựng API bằng **Spring Security OAuth 2.0 Resource Server**. Việc kiểm tra token của request đi vào khác về bản chất với việc xin token cho request đi ra hoặc gia hạn quyền truy cập thay người dùng.

## 1. Ai chịu trách nhiệm về vòng đời token?

Xét một hệ thống có ứng dụng web gọi Orders API:

| Vai trò | Ví dụ | Trách nhiệm chính |
| --- | --- | --- |
| **Resource Owner** | Người dùng sở hữu các đơn hàng | Là bên có thẩm quyền đối với quyền truy cập tài nguyên theo mô hình của hệ thống |
| **Client** | Ứng dụng web, ứng dụng di động, backend/BFF | Xin access token, sử dụng token để gọi API và xin token mới khi cần |
| **Authorization Server** | Keycloak, nhà cung cấp OAuth 2.0/OIDC, Spring Authorization Server | Xử lý yêu cầu cấp quyền và phát hành access token; xử lý refresh grant khi hỗ trợ |
| **Resource Server** | Orders API dùng Spring Security Resource Server | Nhận bearer access token, xác thực token và quyết định quyền truy cập API |

Một hệ thống có thể đồng thời triển khai nhiều vai trò trong cùng một ứng dụng; bảng trên mô tả **vai trò logic**, không bắt buộc là bốn máy chủ vật lý. Việc một API có thể truy cập metadata hoặc JWKS của Authorization Server không biến nó thành hệ thống phát hành token.

~~~text
                     Xin token / refresh
    +----------+ --------------------------> +----------------------+
    |  Client  | <-------------------------- | Authorization Server |
    +----------+      Access token          +----------------------+
         |
         | HTTP Authorization: Bearer <access-token>
         v
    +-----------------+
    | Resource Server |
    | - Kiểm tra token|
    | - Kiểm tra quyền|
    +-----------------+
         |
         +------> 200 OK / 401 Unauthorized / 403 Forbidden
~~~

**Quy tắc nền tảng:** Resource Server **tiêu thụ/kiểm tra access token**; Authorization Server **phát hành token**; Client **quản lý việc xin và sử dụng token**.

## 2. Resource Server xử lý một request như thế nào?

Client gửi request đến API:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
Accept: application/json
~~~

Trong một ứng dụng Spring Security Resource Server, quá trình xử lý thường diễn ra như sau:

1. **Trích xuất bearer token** từ HTTP header `Authorization`.
2. **Xác thực token**. Với JWT, API kiểm tra chữ ký, issuer, thời hạn và các claim khác theo cấu hình; cần kiểm tra audience để bảo đảm token dành cho đúng API. Với opaque token, API có thể dùng token introspection do issuer cung cấp.
3. **Thiết lập ngữ cảnh xác thực** cho request, ví dụ `JwtAuthenticationToken` và authorities được ánh xạ từ scope/claim hợp lệ.
4. **Kiểm tra quyền**: quyền ở endpoint, phương thức HTTP và cả quyền nghiệp vụ với bản ghi, tenant hoặc chủ sở hữu.
5. **Trả dữ liệu hoặc từ chối request** tùy kết quả.

Resource Server **không** cần có refresh token của client để thực hiện năm bước trên. Nó cũng không tự kéo dài claim `exp`, tự ký JWT mới, gọi token endpoint thay client, hoặc chuyển đổi một bearer token hết hạn thành token hợp lệ.

### Kiểm tra JWT không phải là làm mới token

JWT thường có thông tin như:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

Đây là payload minh họa, **không phải token hoàn chỉnh**. `exp` là thời điểm hết hạn; `iss` là issuer; `aud` thể hiện đối tượng sử dụng dự kiến. Resource Server chỉ được chấp nhận JWT khi những kiểm tra cần thiết thành công. Đọc được payload Base64 không chứng minh chữ ký hợp lệ.

Nếu token đã hết hạn, việc API lấy khóa công khai mới từ JWKS **không gia hạn JWT đó**. JWKS phục vụ xác minh chữ ký, không phục vụ cấp access token. API cũng không được tự sửa `exp` rồi coi token đó là token được Authorization Server cấp.

### Introspection cũng không phải refresh

Với opaque token, Resource Server có thể hỏi introspection endpoint xem token hiện tại có `active` hay không, cùng với các thuộc tính cần thiết. Câu trả lời chỉ liên quan đến **tình trạng của token đang kiểm tra**. Nếu token không còn hoạt động, API từ chối request; introspection không tự phát hành token mới.

## 3. Access token hết hạn: trình tự xử lý đúng

Giả sử client đã có access token A, nhưng token đó hết hạn trước khi gọi Orders API:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant RS as Resource Server
    participant AS as Authorization Server

    C->>RS: GET /api/orders + access token A (đã hết hạn)
    RS->>RS: Kiểm tra token, phát hiện hết hạn
    RS-->>C: 401 Unauthorized (invalid_token)
    Note over RS: Không phát hành hoặc refresh token
    C->>AS: Xin token mới bằng grant được hỗ trợ
    alt Được phép cấp token
        AS-->>C: Access token B
        C->>RS: Gọi API với Bearer token B
        RS->>RS: Xác thực B và kiểm tra quyền
        RS-->>C: Dữ liệu hoặc lỗi phù hợp
    else Không thể cấp token
        AS-->>C: Phản hồi lỗi token endpoint
        Note over C: Xử lý hết phiên / xin cấp quyền lại
    end
~~~

Lưu ý:

- **Resource Server chỉ từ chối request hiện tại**, không mặc định hủy toàn bộ tài khoản hoặc phiên đăng nhập của người dùng.
- **Client chủ động** xin token mới nếu có cơ chế được cấp quyền.
- **Authorization Server** quyết định có phát hành token mới theo grant, chính sách, trạng thái đăng nhập, thời hạn và quyền của client hay không.
- Token B, nếu được cấp, phải **được Resource Server xác thực lại**. Token mới không có nghĩa client tự động được truy cập mọi endpoint hay mọi bản ghi.

Với JWT, thông thường API xác thực chữ ký và các claim tại chỗ. Với opaque token, API có thể tham vấn introspection. Hai cách này chỉ thay đổi **cách kiểm tra** access token, không thay đổi **ai phải làm mới** token.

## 4. Ý nghĩa của HTTP 401 và 403

API dùng bearer token thường biểu thị lỗi xác thực/phân quyền qua HTTP status và, khi thích hợp, `WWW-Authenticate`:

| Tình huống | Phản hồi thường gặp | Cách client nên hiểu |
| --- | --- | --- |
| Không gửi bearer token đến endpoint yêu cầu xác thực | **401 Unauthorized** | Request thiếu thông tin xác thực |
| Access token hết hạn, sai chữ ký, không được chấp nhận | **401 Unauthorized**, có thể kèm `invalid_token` | Token hiện tại không hợp lệ; xác định xem có thể xin token mới hay không |
| Access token hợp lệ nhưng thiếu scope/quyền truy cập | **403 Forbidden**, có thể kèm `insufficient_scope` | Token không đủ quyền; refresh không nhất thiết giải quyết vấn đề |
| Chủ thể có scope đọc nhưng không được đọc đơn hàng cụ thể | Thường **403**, hoặc mã khác theo thiết kế nghiệp vụ | Cần kiểm tra quyền trên đối tượng; không mặc định là lỗi token hết hạn |

Ví dụ phản hồi khi token không hợp lệ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Length: 0
~~~

Ví dụ phản hồi khi thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
Content-Length: 0
~~~

Các phản hồi là **minh họa**; entry point, access denied handler và cấu hình ứng dụng có thể ảnh hưởng header/body thực tế. Cũng cần tránh đưa quá nhiều chi tiết nhạy cảm về lý do xác thực thất bại ra bên ngoài.

**Không nên thiết kế client cứ thấy 401 là refresh vô hạn.** 401 có nhiều nguyên nhân ngoài hết hạn token. Cũng không nên tự refresh trên 403: nếu tài khoản không có `orders.write` hoặc không sở hữu đơn hàng, token mới với cùng quyền không thay đổi kết luận.

## 5. Client lấy access token mới bằng cách nào?

### 5.1. Refresh token grant

Nếu Authorization Server đã cấp refresh token và cho phép sử dụng, client gửi refresh token đến **token endpoint của Authorization Server**:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<refresh-token>
~~~

Đây là request minh họa; đường dẫn token endpoint, thông tin xác thực client, các tham số và hình thức truyền credential phụ thuộc nhà cung cấp cùng loại client.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AS as Authorization Server
    participant API as Resource Server
    C->>AS: Token endpoint, grant_type=refresh_token
    AS->>AS: Kiểm tra refresh token, client và chính sách
    alt Refresh hợp lệ
        AS-->>C: Access token mới (+ refresh token mới nếu có rotation)
        C->>API: Request với access token mới
        API-->>C: Kết quả theo token và quyền
    else Refresh không hợp lệ
        AS-->>C: Lỗi, ví dụ invalid_grant
        Note over C: Cấp quyền lại/đăng nhập lại hoặc báo lỗi
    end
~~~

Refresh token có thể đã hết hạn, bị thu hồi hoặc chưa từng được cấp. Một số Authorization Server sử dụng **refresh token rotation**: phát hành refresh token mới và vô hiệu hóa token trước đó sau mỗi lần refresh. Khi có nhiều request đồng thời, client cần đồng bộ việc refresh và lưu token mới để tránh dùng lại refresh token cũ.

**Không gửi refresh token đến Orders API.** Nó là thông tin xác thực có giá trị cao, thường chỉ dành cho token endpoint. Việc cho API nghiệp vụ nhận hoặc lưu refresh token làm tăng nơi có thể rò rỉ bí mật và gây nhầm trách nhiệm.

### 5.2. Chạy lại luồng cấp quyền

Với ứng dụng đăng nhập người dùng, nếu không có refresh token hợp lệ, client có thể bắt đầu **Authorization Code flow** mới, thường kèm **PKCE**. Authorization Server quyết định có cần người dùng đăng nhập hoặc đồng ý cấp quyền lại hay không.

Ví dụ: SPA gọi Orders API nhận 401 vì access token hết hạn. Ứng dụng xử lý trạng thái token phía client và mở luồng cấp quyền mới khi cần. Orders API không tự chuyển hướng trình duyệt đến nhà cung cấp OIDC để xin token thay SPA.

### 5.3. Client Credentials cho giao tiếp máy–máy

Một backend service có thể dùng grant **Client Credentials** để xin access token nhân danh chính nó. Khi token hết hạn, service thường **xin access token mới bằng Client Credentials**, thay vì dùng refresh token:

~~~mermaid
sequenceDiagram
    participant C as Reporting Service (Client)
    participant AS as Authorization Server
    participant RS as Inventory API (Resource Server)
    C->>AS: client_credentials
    AS-->>C: Access token A
    C->>RS: API request + Bearer A
    RS-->>C: Kết quả
    Note over C: Token A hết hạn
    C->>AS: client_credentials lần tiếp theo
    AS-->>C: Access token B
    C->>RS: API request + Bearer B
    RS-->>C: Kết quả
~~~

Luồng này không cần một người dùng cuối tham gia từng lần cấp token. Resource Server vẫn chỉ nhận và xác minh bearer access token.

## 6. Cấu hình Spring Security Resource Server: những gì có và không có

Với Spring Boot và Spring Security dành cho Servlet stack, dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Một cấu hình Resource Server xác thực JWT:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

`issuer-uri` cho biết issuer đáng tin cậy để hỗ trợ khám phá metadata/khóa xác minh và xác thực token. Cấu hình này **không tạo token endpoint**, không cấp refresh token và không tự thêm chức năng OAuth2 Client.

Ví dụ `SecurityFilterChain` bảo vệ API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Ý nghĩa của cấu hình:

- `oauth2ResourceServer(...jwt(...))` kích hoạt xử lý Bearer JWT **trên request đến API**.
- Resource Server có thể xác thực token bằng `JwtDecoder` và thiết lập `Authentication` để áp dụng quy tắc phân quyền.
- Trong cấu hình phổ biến, scope `orders.read` ánh xạ thành authority `SCOPE_orders.read`; issuer dùng claim khác cần mapping riêng.
- `SessionCreationPolicy.STATELESS` phù hợp với API không dựa vào HTTP session để xác thực.
- Lệnh tắt CSRF trong ví dụ **chỉ dành cho API thuần Bearer token, không dùng cookie xác thực tự động đính kèm**. Với ứng dụng có cookie phiên, cần đánh giá và giữ bảo vệ CSRF phù hợp.
- `hasAuthority(...)` chỉ bảo vệ quyền ở mức endpoint/phương thức. API vẫn phải xác minh người dùng được quyền truy cập **đúng bản ghi đơn hàng** và tenant tương ứng.

Khi JWT hết hạn, Spring Security từ chối token trong lớp xác thực. Không có thao tác mặc định nào chuyển sang token endpoint của issuer để xin access token mới rồi tiếp tục controller như thể request ban đầu đã hợp lệ.

### Bên trong bộ lọc Resource Server

~~~text
HTTP Request / Authorization: Bearer <jwt>
                  |
                  v
    BearerTokenAuthenticationFilter
                  |
                  v
       JwtAuthenticationProvider
                  |
                  v
              JwtDecoder
                  |
         Xác minh token/JWT
                  |
                  v
        Authentication hợp lệ
                  |
                  v
       Authorization rules
                  |
                  v
         Controller / Service
~~~

Trường hợp xác minh thất bại, luồng bị dừng với lỗi xác thực thích hợp. Nếu token hợp lệ nhưng không đủ quyền, luồng bị từ chối tại bước phân quyền. **Không bước nào ở sơ đồ trên là refresh token grant.**

Với JWT, Resource Server nên kiểm tra những điều kiện cần thiết theo hợp đồng với Authorization Server, đặc biệt **audience** khi API phải chỉ nhận token dành cho chính mình. Chữ ký hợp lệ và cùng issuer không mặc nhiên chứng minh token được cấp cho mọi API.

### Nếu Authorization Server phát hành opaque token

Resource Server có thể dùng introspection theo cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: YOUR_INTROSPECTION_CLIENT_ID
          client-secret: YOUR_INTROSPECTION_CLIENT_SECRET
~~~

Đây là **các giá trị giữ chỗ**. Trong triển khai thực tế, dùng endpoint đúng của issuer và lấy credentials từ cơ chế quản lý bí mật. API cần cấu hình chế độ `opaqueToken` thay cho `jwt` để sử dụng introspection. Việc hỏi trạng thái token tại introspection endpoint vẫn **không** tạo token mới.

## 7. Một ứng dụng có thể đồng thời là Resource Server và OAuth2 Client

Xét API Gateway/BFF hoặc service A vừa xử lý request đến vừa gọi service B:

~~~text
Trình duyệt / ứng dụng khác
            |
            | Bearer token X
            v
        Service A
      /           \
     /             \
Resource Server   OAuth2 Client
kiểm tra token X  xin hoặc quản lý token Y
                       |
                       | Bearer token Y
                       v
                 Service B (Resource Server)
~~~

- **Token X** dùng cho request đi vào A. Phần Resource Server của A xác minh X và quyền truy cập A.
- **Token Y** dùng cho request A gọi B. Phần OAuth2 Client của A có thể xin và quản lý Y theo grant được cấu hình.
- **Lấy token Y mới** là hành vi của OAuth2 Client, **không phải** Resource Server tự gia hạn token X.
- Nếu có **token relay**, A có thể chuyển tiếp token X trong những trường hợp token và chính sách thực sự cho phép; không được mặc định chuyển tiếp token chỉ dành cho audience của A sang B. Token relay không phải refresh.

Trong Spring Security, các thành phần như `OAuth2AuthorizedClientManager` và `OAuth2AuthorizedClientProvider` thuộc chức năng **OAuth2 Client** có thể hỗ trợ cấp/làm mới token cho lời gọi API đi ra khi được cấu hình, có grant phù hợp và Authorization Server cho phép. Còn `oauth2ResourceServer()` xử lý bearer token của request đi vào.

| Chức năng Spring Security | Vai trò chính |
| --- | --- |
| **OAuth2 Resource Server** | Xác thực access token, bảo vệ endpoint API |
| **OAuth2 Client / OAuth2 Login** | Tham gia flow OAuth 2.0/OIDC, xin và quản lý token cho client, xử lý đăng nhập của ứng dụng |
| **Spring Authorization Server** | Cung cấp authorization/token endpoint, phát hành token |

Chỉ thêm dependency OAuth2 Client không bảo đảm token tự được refresh trong mọi tình huống. Hành vi thực tế phụ thuộc authorized-client storage, client registration, provider/grant, refresh token còn hiệu lực và cách cấu hình thành phần gọi API.

## 8. OIDC có thay đổi trách nhiệm làm mới token không?

**Không.** OIDC bổ sung khả năng **xác thực người dùng cuối** dựa trên OAuth 2.0, nhưng không thay đổi việc Resource Server dùng access token để bảo vệ API.

| Token | Mục đích | Bên sử dụng |
| --- | --- | --- |
| **Access token** | Cho phép kiểm soát truy cập tài nguyên | Client gửi đến Resource Server |
| **ID token** | Chứa thông tin về lần xác thực người dùng dành cho OIDC client | OIDC client xác minh để phục vụ đăng nhập |
| **Refresh token** | Xin access token mới nếu được cấp và được phép | Client gửi đến Authorization Server |

**Không dùng ID token thay access token khi gọi API. Không gửi refresh token đến Resource Server.**

Ví dụ, người dùng đăng nhập qua OIDC tại Authorization Server. Ứng dụng nhận thông tin xác thực cho phiên đăng nhập và access token để gọi Orders API. Khi access token hết hạn, ứng dụng thực hiện quy trình xin token mới hoặc đăng nhập/cấp quyền lại nếu cần. Orders API vẫn giữ vai trò tiếp nhận và xác minh access token, không quyết định phiên OIDC của ứng dụng còn cần làm mới như thế nào.

## 9. Các tình huống dễ hiểu nhầm

### “API cấu hình `issuer-uri` rồi, sao không tự refresh?”

`issuer-uri` hỗ trợ API xác định issuer tin cậy và dữ liệu cần thiết để **xác minh token**. Nó không cung cấp refresh token của client, không làm API trở thành OAuth2 Client và không tự tạo request `grant_type=refresh_token`.

### “JWT hết hạn, API có thể sửa `exp` rồi ký lại để dùng tiếp?”

Không nên. Token được phát hành theo khóa và chính sách của Authorization Server. Việc một Resource Server tự cấp lại token bên ngoài cơ chế được thiết kế sẽ phá ranh giới tin cậy. Nếu muốn giảm số lần người dùng đăng nhập lại, hãy thiết kế vòng đời access token và refresh token đúng ở phía client/Authorization Server.

### “API gọi introspection endpoint, như vậy đã làm mới token?”

Không. **Introspection** hỏi token hiện tại có còn được chấp nhận không. **Refresh** là việc client xin token mới từ token endpoint, theo một grant và chính sách cấp quyền cụ thể.

### “Nếu response là 403, cứ refresh token rồi retry?”

Không nên. `403 Forbidden` thường phản ánh thiếu quyền, chẳng hạn thiếu `orders.write` hoặc không được phép xem đơn hàng của người khác. Access token mới với cùng quyền vẫn có thể bị từ chối.

### “Logout hoặc revoke rồi sao JWT cũ vẫn có thể được API chấp nhận?”

Với JWT được xác minh **offline**, Resource Server có thể không hỏi Authorization Server về trạng thái thu hồi trên từng request. Một JWT đã phát hành có thể tiếp tục được chấp nhận cho đến khi hết hạn nếu API chỉ kiểm tra chữ ký, thời hạn và claim mà không có cơ chế thu hồi bổ sung. Yêu cầu thu hồi gần như tức thời cần chiến lược riêng như introspection, danh sách từ chối được đồng bộ hoặc thời hạn access token ngắn. Đây là bài toán **xác minh và thu hồi token**, không phải làm mới token cho client.

### “Client có refresh token, API có cần nhận hoặc lưu refresh token đó?”

Thông thường không. Client bảo vệ refresh token và trao đổi với Authorization Server. Resource Server cần thông tin để **xác minh access token và phân quyền**, không cần nắm bí mật refresh của client.

### “Một backend có thể vừa là Authorization Server vừa là Resource Server?”

Có thể, nếu thiết kế và triển khai cả hai vai trò. Nhưng khi backend phát hành token, đó là **chức năng Authorization Server được xây dựng có chủ đích**; việc bật Spring Security Resource Server không tự tạo chức năng cấp token.

## 10. Cách xử lý token hết hạn trong hệ thống thực tế

**Ở Resource Server:**

1. Kiểm tra token đúng loại, issuer, chữ ký/trạng thái, thời hạn, audience và quy tắc phân quyền cần thiết.
2. Trả **401** khi request không có thông tin xác thực hợp lệ; trả **403** khi xác thực phù hợp nhưng thiếu quyền.
3. Không nhận refresh token trên các endpoint API nghiệp vụ, không tự ký lại JWT, không trả token mới thay Authorization Server.
4. Ghi log đủ phục vụ chẩn đoán nhưng **không ghi nguyên access token, refresh token hoặc client secret**.
5. Kiểm tra quyền trên từng tài nguyên, không chỉ dựa vào scope chung.

**Ở Client:**

1. Theo dõi thời hạn access token khi có thông tin đáng tin cậy; xin token mới trước khi hết hạn nếu phù hợp.
2. Nếu được cấp refresh token, gửi đến token endpoint theo quy trình và chính sách của Authorization Server. Nếu không, thực hiện lại grant phù hợp, chẳng hạn Authorization Code + PKCE hoặc Client Credentials.
3. Khi cần retry một request sau 401, chỉ thử lại có kiểm soát với token mới; tránh vòng lặp retry vô hạn.
4. Đồng bộ các refresh request chạy đồng thời, nhất là khi Authorization Server bật refresh token rotation.
5. Nếu refresh thất bại, dọn trạng thái token không còn hợp lệ và kích hoạt quy trình đăng nhập/cấp quyền lại hoặc trả lỗi thích hợp cho tác nhân gọi.

**Ở Authorization Server:** quản lý việc phát hành token, grant được phép, thông tin xác thực client, thời hạn token, rotation, revocation và chính sách cấp lại quyền truy cập.

## 11. Tóm tắt theo loại request

| Yêu cầu | Client | Authorization Server | Resource Server |
| --- | --- | --- | --- |
| Đăng nhập OIDC | Khởi tạo/hoàn tất flow | Xác thực và phát hành token theo chính sách | Chưa tham gia nếu chưa có API request |
| Làm mới access token bằng refresh token | Gửi refresh grant | Kiểm tra và cấp token mới nếu hợp lệ | Không tham gia |
| Service cần token bằng Client Credentials | Gửi grant tương ứng | Xác thực client và cấp access token | Không tham gia |
| Gọi API với access token hợp lệ | Gửi Bearer token | Có thể không tham gia từng request JWT | Xác thực và kiểm tra quyền |
| Gọi API bằng access token hết hạn | Nhận lỗi; quyết định xin token mới | Chỉ xử lý nếu client gửi yêu cầu cấp/refresh | Từ chối request, thường bằng 401 |
| Gọi API thiếu scope hoặc quyền đối tượng | Xử lý trạng thái không đủ quyền | Chỉ cấp quyền khác nếu có flow/chính sách cho phép | Từ chối thao tác, thường bằng 403 |

**Ghi nhớ:** Một Spring Security Resource Server từ chối access token hết hạn là **đang bảo vệ API đúng trách nhiệm**. Việc lấy access token mới thuộc về **Client và Authorization Server**; việc quyết định token mới có được phép truy cập đúng tài nguyên hay không vẫn thuộc về **Resource Server và quy tắc nghiệp vụ**.
