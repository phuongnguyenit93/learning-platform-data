# Phân biệt GET, POST, PUT, DELETE khi gán quyền truy cập

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, cùng một đường dẫn API có thể phục vụ nhiều thao tác khác nhau. Một người dùng có quyền xem đơn hàng chưa chắc có quyền tạo đơn hàng mới, sửa địa chỉ giao hàng hoặc xóa đơn hàng. Vì thế, chỉ bảo vệ `/api/orders/**` bằng quy tắc chung “đã xác thực” thường chưa đủ: cần phân biệt **HTTP method**, **quyền mà access token được cấp**, và **quyền của chủ thể đối với tài nguyên cụ thể**.

Ví dụ cùng một tài nguyên:

```http
GET /api/orders/ORD-123 HTTP/1.1
Authorization: Bearer ACCESS_TOKEN
```

```http
PUT /api/orders/ORD-123 HTTP/1.1
Authorization: Bearer ACCESS_TOKEN
Content-Type: application/json

{"deliveryAddress": "Updated address"}
```

Hai request có đường dẫn giống nhau nhưng ý định khác nhau. Với Spring Security Servlet, có thể sử dụng `requestMatchers(HttpMethod.GET, ...)` và `requestMatchers(HttpMethod.PUT, ...)` để đặt các chính sách riêng ngay ở **HTTP authorization layer**.

Bài học này tập trung vào cách gán quyền cho **GET, POST, PUT, DELETE**, đồng thời giải thích các trường hợp liên quan như `PATCH`, `HEAD`, `OPTIONS`, CORS, CSRF, thứ tự rule, phương thức không được hỗ trợ, method security và quyền trên từng bản ghi.

## 1. HTTP method mang ý nghĩa gì?

HTTP method mô tả **ngữ nghĩa hành động được yêu cầu đối với tài nguyên**, không phải tự nó là một quyền bảo mật. Khi thiết kế REST API, người ta thường quy ước:

| Method | Ý nghĩa HTTP phổ biến | Ví dụ Orders API | Quyền API có thể yêu cầu |
|---|---|---|---|
| **GET** | Lấy biểu diễn tài nguyên; **safe** theo ngữ nghĩa HTTP | `GET /api/orders/123` | `orders.read` |
| **POST** | Yêu cầu tài nguyên đích xử lý payload theo ngữ nghĩa của endpoint; thường tạo hoặc thực thi tác vụ | `POST /api/orders` | `orders.create` hoặc `orders.write` |
| **PUT** | Tạo/thay thế trạng thái của tài nguyên đích bằng biểu diễn đã gửi, theo hợp đồng | `PUT /api/orders/123` | `orders.update` hoặc `orders.write` |
| **DELETE** | Yêu cầu xóa liên kết giữa URI và chức năng của tài nguyên, thường là xóa/đánh dấu xóa | `DELETE /api/orders/123` | `orders.delete` hoặc `orders.write` |

Đây là **ánh xạ minh họa**, không phải quy định của OAuth 2.0 rằng GET luôn ứng với scope `read`, POST luôn ứng với `write`. OAuth scope là các chuỗi do Authorization Server và Resource Server thống nhất. Spring Security không tự suy ra `GET → read` hay `DELETE → admin` nếu ứng dụng chưa cấu hình.

### 1.1. Safe và idempotent không phải đồng nghĩa với “công khai”

HTTP có hai tính chất dễ bị nhầm với quyền:

- **Safe method:** client không yêu cầu một thay đổi trạng thái có ý nghĩa nghiệp vụ từ việc gọi method. GET và HEAD được định nghĩa là safe. Logging, thống kê hoặc thay đổi trạng thái phụ trợ do server thực hiện không tự làm GET mất tính safe nếu đó không phải ý định thao tác được client yêu cầu.
- **Idempotent method:** nhiều request giống nhau có cùng *hiệu ứng dự định lên trạng thái server* như một request, dù status code, log hoặc side effect phụ trợ có thể khác. GET, PUT và DELETE là idempotent theo ngữ nghĩa HTTP; POST không được đảm bảo idempotent bởi định nghĩa method.

**Safe không có nghĩa dữ liệu được công khai.** `GET /api/salaries` có thể là endpoint chỉ nhân sự có quyền mới được đọc. **Idempotent không có nghĩa ít nguy hiểm.** `DELETE /api/accounts/123` vẫn là hành động nghiêm trọng dù gọi lặp lại không tạo thêm lần xóa theo ý nghĩa HTTP.

### 1.2. PUT và DELETE không giống POST

`PUT /api/orders/123` thường hướng đến tài nguyên có URI xác định và biểu diễn đích. Nếu API cho phép **PUT tạo mới khi tài nguyên chưa tồn tại**, một caller chỉ có quyền “update existing order” có thể vô tình được tạo đơn hàng mới nếu service không phân biệt trường hợp này. Khi hợp đồng không cho phép upsert, service cần từ chối trường hợp tài nguyên chưa tồn tại; nếu cho phép, phải áp chính sách create phù hợp.

`DELETE` có thể là xóa mềm (*soft delete*), xóa thật hoặc thay đổi trạng thái nghiệp vụ. Quyền cần thiết dựa trên **tác động**, không chỉ tên phương thức. Một token có `orders.write` chưa chắc được phép xóa dữ liệu tuân thủ quy định lưu trữ.

`POST` đặc biệt đa dạng: có thể tạo đơn hàng, hủy đơn hàng, thực hiện thanh toán, hoặc thậm chí chỉ thực hiện tìm kiếm với payload phức tạp. Vì vậy không nên gán mọi POST vào một quyền ghi duy nhất mà không xét endpoint.

## 2. Ba tầng quyết định quyền trong Resource Server

Một request có access token phải vượt qua nhiều điều kiện:

```mermaid
flowchart TD
    A["HTTP request: method + path + Bearer token"] --> B["BearerTokenAuthenticationFilter"]
    B --> C{"Token hợp lệ?<br/>issuer, audience, chữ ký, thời gian"}
    C -->|"Không"| X["401 / invalid_token"]
    C -->|"Có"| D["Authentication có GrantedAuthority"]
    D --> E{"HTTP method + path<br/>khớp rule và có quyền?"}
    E -->|"Không"| Y["403 / insufficient_scope nếu phù hợp"]
    E -->|"Có"| F["Controller / Service"]
    F --> G{"Owner, tenant, trạng thái<br/>và policy dữ liệu hợp lệ?"}
    G -->|"Không"| Z["403 hoặc 404 theo policy"]
    G -->|"Có"| H["Thực hiện thao tác"]
```

| Tầng | Cần biết điều gì? | Ví dụ |
|---|---|---|
| **Authentication** | Access token do ai phát hành, còn hợp lệ và dành cho API nào? | `iss` đúng, `aud=orders-api`, chữ ký hợp lệ, `exp` còn hạn |
| **HTTP authorization** | Người gọi có quyền thực hiện loại thao tác trên route này không? | GET cần `SCOPE_orders.read`, DELETE cần `SCOPE_orders.delete` |
| **Business authorization** | Chủ thể có quyền thao tác trên **đơn hàng cụ thể** trong trạng thái hiện tại không? | Người dùng thuộc đúng tenant và là owner, hoặc có quyền admin được duyệt |

Token có `SCOPE_orders.delete` không tự chứng minh người gọi được xóa đơn hàng `ORD-123` của người khác. Ngược lại, người dùng có thể sở hữu đơn hàng nhưng access token hiện tại chỉ được cấp `orders.read`; request DELETE vẫn phải bị từ chối.

## 3. Scope OAuth và GrantedAuthority trong Spring Security

Authorization Server có thể phát hành JWT access token chứa:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read orders.create orders.update",
  "exp": 1893459600
}
```

Ví dụ chỉ mô tả payload; đây không phải token đã ký hợp lệ. Khi `JwtDecoder` xác minh token và `JwtAuthenticationConverter` dùng mapping phổ biến, Spring Security chuyển scopes thành các `GrantedAuthority`:

```text
orders.read   -> SCOPE_orders.read
orders.create -> SCOPE_orders.create
orders.update -> SCOPE_orders.update
```

Các rule như `hasAuthority("SCOPE_orders.read")` kiểm tra authority ở `Authentication` của request hiện tại. Chuỗi `SCOPE_` là tiền tố mặc định của Spring Security, **không phải tiền tố mà Authorization Server bắt buộc phải ghi vào claim `scope`**.

Với opaque token, Resource Server dùng introspection để lấy scope được cấp; Spring Security cũng có thể chuyển các scopes đó thành `SCOPE_...` authorities. Khi dùng converter tùy biến, prefix và claim name có thể khác, nên HTTP rules phải khớp với authorities **thực tế** được tạo.

### 3.1. Không dùng hasRole để kiểm tra scope mặc định

```java
.hasAuthority("SCOPE_orders.read") // kiểm tra authority đúng tên
.hasRole("ADMIN")                  // theo mặc định kiểm tra ROLE_ADMIN
```

`hasRole("orders.read")` thường kiểm tra `ROLE_orders.read`, không phải `SCOPE_orders.read`. Việc một tên scope nhìn giống role không làm Spring Security tự hiểu chúng tương đương.

### 3.2. Có quyền “write” có mặc nhiên có quyền “read” không?

Không. Các scope không có quan hệ phân cấp tự động:

```text
SCOPE_orders.write
    không tự đồng nghĩa
SCOPE_orders.read
```

Nếu hệ thống muốn quyền ghi bao hàm quyền đọc, phải biểu diễn rõ bằng chính sách, ví dụ dùng `hasAnyAuthority("SCOPE_orders.read", "SCOPE_orders.write")` cho GET, hoặc cấp cả hai scope trong token. Không nên suy diễn hierarchy từ cách đặt tên.

## 4. Gán quyền khác nhau bằng requestMatchers(HttpMethod, ...)

Trong Spring Security Servlet 6+, cấu hình authorization thường dùng:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers(HttpMethod.PUT, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .anyRequest().authenticated()
)
```

Đây là một **mẫu minh họa ban đầu**: GET dùng read, còn POST/PUT/DELETE dùng write. Nó giúp thấy sự khác biệt theo method nhưng có giới hạn:

- Tất cả POST/PUT/DELETE dùng chung write, không tách tạo, sửa và xóa.
- Pattern rộng có thể bao gồm các route nghiệp vụ rất khác nhau.
- `anyRequest().authenticated()` cho phép một số method/path khác đi qua chỉ vì token hợp lệ, dù chưa có quy tắc scope cho chúng.

Đối với API có nhiều thao tác nhạy cảm, nên gán quyền **theo cặp (HTTP method, đường dẫn có ý nghĩa nghiệp vụ)** và kết thúc bằng fallback phù hợp.

### 4.1. Ví dụ chi tiết cho Orders API

Thiết kế endpoint và scope:

| Request | Chức năng | Authority yêu cầu |
|---|---|---|
| `GET /api/orders` | Liệt kê đơn được xem | `SCOPE_orders.read` |
| `GET /api/orders/{id}` | Xem chi tiết đơn | `SCOPE_orders.read` |
| `POST /api/orders` | Tạo đơn | `SCOPE_orders.create` |
| `PUT /api/orders/{id}` | Thay thế/cập nhật theo hợp đồng API | `SCOPE_orders.update` |
| `DELETE /api/orders/{id}` | Xóa/hủy kiểu DELETE theo hợp đồng | `SCOPE_orders.delete` |
| `POST /api/orders/{id}/cancel` | Hủy đơn bằng một lệnh nghiệp vụ | `SCOPE_orders.cancel` |

Mỗi authority là chuỗi được Authorization Server và Resource Server thống nhất, không có tên nào được Spring Security tạo ra chỉ vì HTTP method. Ví dụ `orders.cancel` chỉ tồn tại nếu hệ thống thiết kế/cấp scope đó.

### 4.2. Cấu hình Servlet hoàn chỉnh theo method và route

Ví dụ sử dụng Spring Boot 3.x, Spring Security 6+ và Spring MVC:

```groovy
// build.gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

```yaml
# application.yml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
```

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            // Ví dụ REST API dùng Bearer trong Authorization header,
            // không dùng cookie/session làm credential cho thao tác ghi.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/health").permitAll()

                // HEAD có ý nghĩa giống GET nhưng không trả response body.
                .requestMatchers(HttpMethod.HEAD,
                    "/api/orders", "/api/orders/{orderId}")
                    .hasAuthority("SCOPE_orders.read")

                .requestMatchers(HttpMethod.GET,
                    "/api/orders", "/api/orders/{orderId}")
                    .hasAuthority("SCOPE_orders.read")

                // Lệnh hủy là quyền riêng, không xem mọi POST là tạo.
                .requestMatchers(HttpMethod.POST,
                    "/api/orders/{orderId}/cancel")
                    .hasAuthority("SCOPE_orders.cancel")

                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")

                .requestMatchers(HttpMethod.PUT,
                    "/api/orders/{orderId}")
                    .hasAuthority("SCOPE_orders.update")

                .requestMatchers(HttpMethod.DELETE,
                    "/api/orders/{orderId}")
                    .hasAuthority("SCOPE_orders.delete")

                // Những method/path chưa được cho phép rõ ràng sẽ bị từ chối.
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Ở đây:

1. `oauth2ResourceServer(...jwt...)` bật xử lý Bearer token.
2. JWT decoder kiểm tra chữ ký/issuer/thời gian và audience theo cấu hình/validator đang dùng.
3. Spring Security ánh xạ scope thành `SCOPE_...` authorities.
4. `requestMatchers(HttpMethod.X, path)` khớp **cả method và đường dẫn**, rồi áp chính sách tương ứng.
5. `anyRequest().denyAll()` từ chối mọi đường chưa được liệt kê trong chain này, giúp tránh vô tình thêm endpoint mới mà quên scope.
6. Service vẫn cần quyết định chủ thể nào được sửa/hủy/xóa một đơn cụ thể.

Ví dụ dùng pattern `"/api/orders/{orderId}"` theo matcher path của Spring MVC/Spring Security hiện đại khi ứng dụng có MVC. Cách diễn giải path patterns có thể phụ thuộc loại matcher, Servlet path và phiên bản. Khi ứng dụng có context path hoặc Servlet mapping đặc thù, phải đảm bảo matcher trùng URI thực tế mà Spring Security quan sát.

**Chú ý `/api/orders` và `/api/orders/{orderId}` là hai đường khác nhau**. Quy tắc cho collection chưa chắc bao phủ item. Một pattern như `/api/orders/**` có thể rộng hơn dự kiến; cần cân nhắc phạm vi tất cả endpoint con.

### 4.3. Sắp xếp rule để tránh rule rộng nuốt rule hẹp

Spring Security đánh giá các authorization rules theo thứ tự khai báo và dùng **quy tắc khớp đầu tiên** trong chain đang xử lý request. Ví dụ sai:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.DELETE, "/api/orders/{orderId}")
        .hasAuthority("SCOPE_orders.delete")
    .anyRequest().denyAll())
```

Rule đầu không giới hạn method. Một request:

```http
DELETE /api/orders/ORD-123 HTTP/1.1
Authorization: Bearer TOKEN_WITH_ORDERS_READ
```

đã khớp `"/api/orders/**"`, vì vậy **quy tắc DELETE cụ thể phía sau không được dùng**. Đây là ví dụ về việc scope read có thể bị áp nhầm cho thao tác xóa.

Cách đúng: đặt các ngoại lệ/cặp method-path cụ thể trước, sau đó mới đến rule rộng hoặc fallback.

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.DELETE, "/api/orders/{orderId}")
        .hasAuthority("SCOPE_orders.delete")
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().denyAll())
```

Nhưng đặt cụ thể trước **không đủ** nếu rule rộng phía sau vẫn cho phép những method nhạy cảm không được liệt kê. Khi cấu hình phân quyền theo phương thức, nên hạn chế các matcher không gắn method cho khu vực API (ngoại trừ những endpoint thật sự công khai hoặc có policy thống nhất cho mọi method).

### 4.4. permitAll theo path cũng mở cho những method khác

Ví dụ:

```java
.requestMatchers("/public/health").permitAll()
```

nghĩa là path này được phép theo **mọi HTTP method được matcher đó áp dụng**, không chỉ GET. Nếu controller chỉ hỗ trợ GET, POST có thể trả 405 ở tầng MVC; nhưng security layer đã cho qua. Nếu yêu cầu bảo vệ chặt theo method:

```java
.requestMatchers(HttpMethod.GET, "/public/health").permitAll()
.requestMatchers(HttpMethod.HEAD, "/public/health").permitAll()
```

Cần đặt các rule này trước `anyRequest().denyAll()`. Không dùng một matcher public quá rộng như `"/public/**"` nếu folder đó về sau có endpoint POST thay đổi trạng thái.

## 5. Mapping cơ bản: GET đọc, POST tạo, PUT sửa, DELETE xóa

### 5.1. GET: đọc, nhưng không mặc định ai cũng được đọc

Ví dụ:

```http
GET /api/orders/ORD-123 HTTP/1.1
Authorization: Bearer TOKEN_WITH_ORDERS_READ
```

Tại tầng HTTP:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/{orderId}")
    .hasAuthority("SCOPE_orders.read")
```

Sau đó tại service:

- User có thực sự thuộc tenant của order?
- User là owner hay có quyền đọc thay mặt người khác?
- Order có dữ liệu nhạy cảm cần role bổ sung không?
- Trường nào được phép trả ra cho loại principal này?

**GET là safe theo ngữ nghĩa HTTP, không phải được phép bỏ xác thực hoặc ownership check.** Ví dụ `GET /api/orders/{id}/invoice` có thể cần một scope nhạy cảm hơn như `invoices.read`.

Đừng thiết kế GET để có side effect mà client chủ động yêu cầu, ví dụ `GET /api/orders/123/delete`. Link preview, crawler hoặc hệ thống prefetch có thể gọi GET; đặt tác vụ xóa sau GET vừa sai ngữ nghĩa HTTP, vừa làm chính sách “GET = read” trở nên nguy hiểm.

### 5.2. POST: cần phân biệt tạo mới và lệnh nghiệp vụ

Ví dụ tạo đơn:

```http
POST /api/orders HTTP/1.1
Authorization: Bearer TOKEN_WITH_ORDERS_CREATE
Content-Type: application/json

{"items": [{"sku": "SKU-001", "quantity": 1}]}
```

Rule:

```java
.requestMatchers(HttpMethod.POST, "/api/orders")
    .hasAuthority("SCOPE_orders.create")
```

Nhưng một POST khác có thể là:

```http
POST /api/orders/ORD-123/cancel HTTP/1.1
Authorization: Bearer TOKEN_WITH_ORDERS_CANCEL
```

Nên yêu cầu `SCOPE_orders.cancel` riêng nếu hủy đơn mang rủi ro lớn hơn tạo đơn. Không coi mọi POST dưới `"/api/orders/**"` là tạo đơn.

Ngoài ra, có API dùng:

```http
POST /api/orders/search HTTP/1.1
Content-Type: application/json

{"filters": {"status": ["PAID", "SHIPPED"]}}
```

**Dù là POST, thao tác này có thể chỉ đọc dữ liệu.** Tùy thiết kế, nó có thể cần `SCOPE_orders.read` chứ không phải `SCOPE_orders.create`. Chọn scope dựa trên **chức năng và tác động nghiệp vụ**, không máy móc theo tên method.

### 5.3. PUT: thay thế, sửa và nguy cơ upsert

Ví dụ:

```http
PUT /api/orders/ORD-123 HTTP/1.1
Authorization: Bearer TOKEN_WITH_ORDERS_UPDATE
Content-Type: application/json

{"deliveryAddress": "Updated address"}
```

Nếu API thực sự dùng PUT cho **thay thế toàn bộ biểu diễn**, server cần tài liệu hóa các trường bắt buộc và xử lý các trường thiếu đúng hợp đồng. Nếu chỉ sửa một phần, PATCH thường phù hợp hơn hoặc PUT phải được API mô tả rõ ràng.

Quy tắc HTTP:

```java
.requestMatchers(HttpMethod.PUT, "/api/orders/{orderId}")
    .hasAuthority("SCOPE_orders.update")
```

Chưa đủ để quyết định:

- Đơn hàng đã giao có được đổi địa chỉ không?
- Người dùng có được sửa đơn của người khác không?
- Những trường như tổng tiền, chủ đơn, tenant hoặc trạng thái có được client chỉnh không?
- Nếu URI không tồn tại, PUT được phép tạo mới hay bắt buộc trả 404?

Đặc biệt, nếu PUT có thể **upsert**, đừng chỉ dựa `SCOPE_orders.update` rồi vô tình cho phép tạo mới. Có thể cấm tạo qua PUT hoặc yêu cầu `orders.create` khi tài nguyên chưa tồn tại, kiểm tra sau khi xác định trạng thái ở service.

### 5.4. DELETE: idempotent nhưng rất nhạy cảm

```http
DELETE /api/orders/ORD-123 HTTP/1.1
Authorization: Bearer TOKEN_WITH_ORDERS_DELETE
```

Rule:

```java
.requestMatchers(HttpMethod.DELETE, "/api/orders/{orderId}")
    .hasAuthority("SCOPE_orders.delete")
```

Ngoài scope, service có thể yêu cầu:

- Đơn thuộc tenant và principal được phép.
- Đơn chưa được thanh toán/gửi đi, hoặc đáp ứng điều kiện hủy.
- Dữ liệu không chịu yêu cầu lưu trữ pháp lý.
- Có lưu audit hoặc chuyển sang trạng thái archived theo chính sách.

DELETE **idempotent** không có nghĩa phản hồi luôn giống nhau: xóa lần đầu có thể trả 204, lần sau 404, nhưng hiệu ứng dự định “tài nguyên không còn” vẫn có thể idempotent. Một số API không cho client DELETE tài nguyên đã hoàn thành mà dùng nghiệp vụ POST cancel; khi đó chính sách phải theo endpoint thật.

## 6. Scope đơn giản hay scope chi tiết?

Có hai mô hình phổ biến, cả hai đều hợp lệ nếu được thiết kế nhất quán.

### 6.1. Mô hình read/write

```text
GET                  -> SCOPE_orders.read
POST, PUT, DELETE    -> SCOPE_orders.write
```

Ưu điểm:

- Dễ hiểu và dễ cấp scope.
- Phù hợp API nhỏ, thao tác ghi có độ nhạy tương đương.

Giới hạn:

- Caller chỉ cần sửa địa chỉ đơn hàng cũng có thể được DELETE nếu các endpoint đều yêu cầu `orders.write`.
- Khó áp chính sách đặc thù cho refund/cancel/export.

### 6.2. Mô hình chi tiết theo khả năng nghiệp vụ

```text
GET /api/orders/{id}              -> SCOPE_orders.read
POST /api/orders                  -> SCOPE_orders.create
PUT /api/orders/{id}              -> SCOPE_orders.update
DELETE /api/orders/{id}           -> SCOPE_orders.delete
POST /api/orders/{id}/cancel      -> SCOPE_orders.cancel
POST /api/orders/search           -> SCOPE_orders.read
```

Ưu điểm:

- Hỗ trợ nguyên tắc **least privilege**: token chỉ có quyền đúng với chức năng cần dùng.
- Tách thao tác nhạy cảm khỏi thao tác ghi thông thường.
- Dễ diễn giải các quyền API cho client và quản trị viên.

Giới hạn:

- Cần quản lý thêm scope trong Authorization Server.
- Nếu đặt quá nhiều scope chi tiết tới mức tương đương từng record, token/phân quyền sẽ khó quản lý; quyền theo từng record thường nên nằm ở domain service/policy store.

Một phương án thực tế là dùng scope **chức năng** ở HTTP layer, còn ownership, tenant, vai trò quản trị và trạng thái resource ở service layer.

### 6.3. Scope không tự có quan hệ kế thừa

`SCOPE_orders.delete` không tự bao hàm `SCOPE_orders.read`. Nếu một admin có quyền tất cả thao tác, hãy biểu diễn rõ:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/{orderId}")
    .hasAnyAuthority(
        "SCOPE_orders.read",
        "SCOPE_orders.admin")
```

Đoạn trên là quan hệ **OR**: có một trong hai authorities là đủ. Nếu rule yêu cầu **đồng thời** hai điều kiện, cần policy/AuthorizationManager cho logic AND. Không trộn `hasRole("ADMIN")` với `SCOPE_...` nếu chưa chắc converters tạo đúng `ROLE_ADMIN`.

## 7. GET, HEAD, OPTIONS, PATCH và các method khác

Dù bài tập trung vào bốn method chính, một Resource Server an toàn phải biết **những phương thức khác được xử lý thế nào**.

### 7.1. HEAD: gần GET nhưng là method riêng khi match authorization

Theo HTTP, HEAD giống GET về việc chọn thông tin response nhưng không trả body. Spring MVC có thể hỗ trợ HEAD cho handler được khai báo `@GetMapping`.

Tuy nhiên, `HttpMethod.GET` và `HttpMethod.HEAD` là **hai giá trị khác nhau**. Khi rule chỉ match:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/{orderId}")
    .hasAuthority("SCOPE_orders.read")
```

đừng tự giả định matcher đó luôn khớp HEAD. Nên quyết định rõ:

```java
.requestMatchers(HttpMethod.HEAD, "/api/orders/{orderId}")
    .hasAuthority("SCOPE_orders.read")
```

Nếu HEAD bị fallback denyAll, client chỉ có quyền đọc có thể nhận 403 với HEAD mặc dù GET được phép. Đây có thể là chính sách đúng hoặc lỗi UX, tùy hợp đồng.

HEAD cũng có thể lộ metadata nhạy cảm như sự tồn tại của resource, kích thước hoặc thời gian sửa đổi. Không mở toàn bộ HEAD cho anonymous chỉ vì không có body.

### 7.2. OPTIONS và CORS preflight

Khi browser thực hiện cross-origin request với `Authorization` header hoặc một request không thuộc loại đơn giản, nó thường gửi **CORS preflight**:

```http
OPTIONS /api/orders/ORD-123 HTTP/1.1
Origin: https://shop.example.com
Access-Control-Request-Method: DELETE
Access-Control-Request-Headers: authorization
```

Preflight thường **không gửi Bearer access token của request thật**. Nếu authentication filter từ chối preflight như một request cần bearer, browser có thể không bao giờ thực hiện DELETE thật, dù token của user có quyền.

Giải pháp khuyến nghị trong Spring Security Servlet là cấu hình **CORS trước Security authorization** cho các origin/method/header được phép, ví dụ thông qua `CorsConfigurationSource` và `http.cors(...)`:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://shop.example.com"));
    cors.setAllowedMethods(List.of(
        "GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS"));
    cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
    cors.setAllowCredentials(false);
    cors.setMaxAge(3600L);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cors);
    return source;
}
```

Và trong `SecurityFilterChain`:

```java
.cors(Customizer.withDefaults())
```

Đây là cấu hình mẫu cho API dùng Bearer header do JavaScript gửi tường minh, không dùng cookie làm credential. Trong hệ thống có cookies, `allowCredentials` và danh sách origins cần thiết kế riêng; không bật wildcard origins kết hợp credential thiếu kiểm soát.

**CORS không phải authorization:** cho phép origin thực hiện preflight **không có nghĩa** POST/PUT/DELETE thực sự được cấp scope. Request tiếp theo vẫn phải đi qua Bearer authentication và method-specific authorization.

Không nên chỉ giải quyết lỗi preflight bằng một rule mở mọi `OPTIONS` cho toàn hệ thống mà không hiểu CORS filter/matcher; có những OPTIONS request không phải CORS preflight và chính sách của API có thể khác.

### 7.3. PATCH: sửa một phần, không tự hưởng quyền PUT

Một API có thể có:

```http
PATCH /api/orders/ORD-123 HTTP/1.1
Authorization: Bearer TOKEN_WITH_ORDERS_UPDATE
Content-Type: application/merge-patch+json

{"deliveryAddress": "New address"}
```

Nếu hỗ trợ PATCH, hãy thêm rule riêng:

```java
.requestMatchers(HttpMethod.PATCH, "/api/orders/{orderId}")
    .hasAuthority("SCOPE_orders.update")
```

Hoặc yêu cầu một scope khác nếu thao tác patch có quyền khác với PUT. `HttpMethod.PUT` không tự match PATCH; nếu dùng `anyRequest().authenticated()` làm fallback, PATCH có thể được cho qua mà không cần scope update.

### 7.4. TRACE và method không được phép

Một API thông thường ít có lý do bật `TRACE`, `CONNECT` hoặc method không được mô tả trong hợp đồng. Chính sách `anyRequest().denyAll()` giúp chặn các đường chưa khai báo tại authorization layer. Đồng thời, web server/proxy và controller phải cấu hình tập method hỗ trợ phù hợp; authorization không thay toàn bộ kiểm soát giao thức ở hạ tầng.

## 8. Phân biệt 401, 403, 404 và 405

Việc gán quyền theo method liên quan trực tiếp đến cách ứng dụng trả lỗi.

| HTTP status | Ý nghĩa thường gặp | Ví dụ |
|---|---|---|
| **401 Unauthorized** | Request thiếu hoặc không có authentication hợp lệ | GET protected không Bearer, token sai chữ ký hoặc hết hạn |
| **403 Forbidden** | Authentication có thể hợp lệ nhưng không được phép | DELETE với token chỉ có `orders.read` |
| **404 Not Found** | Tài nguyên/route không tồn tại hoặc domain chọn che giấu sự tồn tại | Order ID không tồn tại, hoặc API không tiết lộ order thuộc người khác |
| **405 Method Not Allowed** | Tài nguyên/handler không hỗ trợ HTTP method đó | `POST /api/orders/123` khi controller chỉ khai GET/PUT/DELETE |

**Các kết quả này phụ thuộc thứ tự xử lý.** Spring Security filter chain thường chạy trước controller. Với `anyRequest().denyAll()`, một method không được cho phép có thể bị từ chối ở security layer (403 sau xác thực) **trước khi** Spring MVC có cơ hội xác định 405. Tương tự, unauthenticated request có thể nhận 401 thay vì 404.

Do đó không nên dùng quy tắc “mọi method không hỗ trợ phải luôn trả 405” làm giả định trong bảo mật. Nếu API cần 405 nhất quán vì hợp đồng công khai, phải thiết kế có chủ đích để không làm lộ dữ liệu hoặc bỏ qua auth.

### 8.1. Mô tả luồng thiếu scope

```http
DELETE /api/orders/ORD-123 HTTP/1.1
Authorization: Bearer VALID_READ_ONLY_TOKEN
```

Giả sử token:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

Trong thực tế token còn cần chữ ký và thời hạn hợp lệ, không được hiểu payload trên là đủ để xác thực. Sau authentication, `Authentication` có `SCOPE_orders.read` nhưng thiếu `SCOPE_orders.delete`. Rule DELETE từ chối → thường **403**. Bearer access denied handler có thể gửi `WWW-Authenticate` với `error="insufficient_scope"` theo RFC 6750 tùy cấu hình.

Nếu token hết hạn, request **không tới bước so sánh scope theo cách bình thường** mà bị từ chối ở authentication → thường **401** và Bearer `invalid_token`.

### 8.2. Không biến thiếu scope thành quyền mặc định

Đừng viết custom code:

```java
// Anti-pattern minh họa: KHÔNG dùng.
if (!authenticationHas("SCOPE_orders.delete")) {
    // Quyền thiếu => cho chạy lệnh xóa để giữ tương thích
    deleteOrder();
}
```

Một quyền không được cấp phải dẫn đến từ chối hoặc một đường nghiệp vụ đã được thiết kế, không phải fallback “allow”.

## 9. Cấu hình nhiều SecurityFilterChain: bảo vệ đủ đường dẫn

Trong ứng dụng lớn có thể có nhiều chain:

```text
/internal/** -> Basic/service authentication
/api/**      -> OAuth2 Resource Server JWT
Các URL khác -> fallback security policy
```

Ví dụ:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
```

Các imports của ví dụ gồm `org.springframework.core.annotation.Order`, `HttpMethod`, `HttpSecurity`, `SecurityFilterChain` và `Customizer`. Trong hệ thống thật, định nghĩa đầy đủ chain cho các URL nội bộ và các loại authentication của chúng.

**Khác nhau quan trọng:**

- `securityMatcher("/api/**")` xác định request nào **đi vào chain**.
- `requestMatchers(HttpMethod.GET, "...")` xác định rule authorization **bên trong chain đã chọn**.

`FilterChainProxy` chọn **SecurityFilterChain phù hợp đầu tiên** theo thứ tự; nó không gộp rules của mọi chain lại với nhau. Nếu một URL không khớp chain nào, nó có thể **không chịu Spring Security web filters** như dự kiến. Fallback chain giúp hệ thống tránh “khoảng trống” khi đã tự khai báo các chain có matcher giới hạn.

### 9.1. Hai mức thứ tự độc lập

Có hai câu hỏi riêng:

1. **Chain order:** request đi qua chain nào? `@Order(1)` ưu tiên trước `@Order(2)` khi các matcher cùng khớp.
2. **Rule order:** trong chain đó, matcher authorization nào khớp đầu tiên? Rule theo method/path có thể bị rule path rộng đặt trước che mất.

Một cấu hình sai ở bất kỳ mức nào đều có thể khiến quyền GET bị dùng cho POST/DELETE hoặc khiến endpoint không có filter Resource Server.

## 10. Mapping path phải khớp với handler thật

Đặt rule theo method chỉ đúng nếu **đường dẫn được match đúng**.

Ví dụ controller:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{orderId}")
    public OrderDto getOrder(@PathVariable String orderId) {
        return orders.getOrder(orderId);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public OrderDto create(@RequestBody CreateOrderCommand command) {
        return orders.create(command);
    }

    @PutMapping("/{orderId}")
    public OrderDto update(
            @PathVariable String orderId,
            @RequestBody UpdateOrderCommand command) {
        return orders.update(orderId, command);
    }

    @DeleteMapping("/{orderId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable String orderId) {
        orders.delete(orderId);
    }
}
```

Các class `OrderService`, `OrderDto` và command DTOs là thành phần ứng dụng chưa được định nghĩa ở đây; ví dụ chỉ để thấy sự liên hệ giữa URL/method mapping trong controller với authorization matcher.

Với `@RequestMapping("/api/orders")`, Spring MVC có thể gắn:

- `@PostMapping` → POST `/api/orders`.
- `@GetMapping("/{orderId}")` → GET `/api/orders/{orderId}`.
- `@PutMapping("/{orderId}")` → PUT `/api/orders/{orderId}`.
- `@DeleteMapping("/{orderId}")` → DELETE `/api/orders/{orderId}`.

Khi đổi controller mapping (ví dụ từ `/api/orders/{id}` sang `/api/v2/orders/{id}`), phải cập nhật security matcher và policy tương ứng. Một rule không còn khớp với handler mới có thể dẫn đến từ chối ngoài dự kiến hoặc, khi fallback quá rộng, mở quyền quá mức.

### 10.1. Pattern rộng có thể bao gồm endpoint không mong muốn

`"/api/orders/**"` có thể bao gồm:

```text
/api/orders
/api/orders/ORD-123
/api/orders/ORD-123/notes
/api/orders/ORD-123/export
/api/orders/ORD-123/cancel
```

Điều kiện cụ thể phụ thuộc path matcher; trên thực tế mẫu rộng có thể bắt nhiều route hơn mong muốn. Nếu `GET /api/orders/ORD-123/export` có dữ liệu tài chính nhạy cảm, có thể cần scope `orders.export` thay vì `orders.read`.

**Nguyên tắc:** áp rule từ đặc thù tới tổng quát và có fallback deny. Không dựa chỉ vào đuôi `/**` để kết luận tất cả endpoint bên dưới có cùng mức nhạy cảm.

### 10.2. Đường dẫn có path variable không phải một scope riêng

Các ID như `ORD-123` trong URL là dữ liệu do caller chọn. Một rule:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/{orderId}")
    .hasAuthority("SCOPE_orders.read")
```

không tự kiểm tra rằng `orderId` thuộc `sub` trong token. Nếu client đổi `ORD-123` thành `ORD-999`, Spring Security vẫn khớp cùng route và cùng scope. **Object-level authorization** phải dựa vào dữ liệu sở hữu/tenant ở service hoặc một policy decision point tương đương.

## 11. Phân quyền đối tượng: method scope là điều kiện cần, không phải đủ

Ví dụ JWT sau khi xác thực:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read orders.update",
  "tenant_id": "tenant-a"
}
```

Một controller nhận principal đã được xác minh:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

public record CurrentActor(
    String issuer,
    String subject,
    String tenantId
) {}

@GetMapping("/api/orders/{orderId}")
public OrderDto readOrder(
        @PathVariable String orderId,
        @AuthenticationPrincipal Jwt jwt) {

    CurrentActor actor = new CurrentActor(
        jwt.getIssuer().toString(),
        jwt.getSubject(),
        jwt.getClaimAsString("tenant_id")
    );
    return orderService.readVisibleTo(actor, orderId);
}
```

Đoạn trên minh họa controller method và record (đặt trong các file/class phù hợp khi triển khai thật), giả định `orderService` đã được injection. Nó chỉ nên chạy sau authentication JWT được cấu hình đúng. Với opaque token, controller cần nhận `Authentication`/`OAuth2AuthenticatedPrincipal` thay vì ép mọi principal thành `Jwt`.

Ở service:

```java
public OrderDto readVisibleTo(CurrentActor actor, String orderId) {
    Order order = repository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    boolean sameTenant =
        order.getTenantId().equals(actor.tenantId());

    boolean isOwner =
        order.getOwnerIssuer().equals(actor.issuer()) &&
        order.getOwnerSubject().equals(actor.subject());

    if (!sameTenant || !isOwner) {
        throw new AccessDeniedException("Order access denied");
    }
    return mapper.toDto(order);
}
```

Ví dụ mô tả policy “chỉ chủ đơn hàng trong đúng tenant được xem”, không bao gồm trường hợp admin/delegation. Khi có role quản trị, vẫn phải định nghĩa chính xác điều kiện vượt owner và không dựa vào claim role không được xác minh.

### 11.1. PUT/DELETE cần kiểm tra trạng thái tài nguyên

Ngay cả khi client có `SCOPE_orders.update` hoặc `SCOPE_orders.delete`, service có thể cần:

```text
UPDATE:
  order thuộc đúng owner và tenant
  order chưa shipped
  không sửa các trường server-owned như price/owner/tenant

DELETE:
  order thuộc đúng owner và tenant
  order chưa được thanh toán hoặc đủ điều kiện xóa
  không vi phạm chính sách lưu giữ/audit
```

Chính sách business này được áp sau bước xác thực/authorization theo method. Thao tác có thể cần transaction/locking phù hợp để tránh trạng thái thay đổi giữa lúc kiểm tra và lúc ghi.

### 11.2. Method security là lớp bổ sung

Khi bật:

```java
@EnableMethodSecurity
```

có thể đặt thêm bảo vệ tại service:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDto read(String orderId) {
        return readWithBusinessPolicy(orderId);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.delete')")
    public void delete(String orderId) {
        deleteWithBusinessPolicy(orderId);
    }
}
```

Các method `readWithBusinessPolicy`, `deleteWithBusinessPolicy` là thành phần ví dụ, chưa định nghĩa. **Method security kiểm tra authority nhưng không tự thay thế ownership check** trừ khi application bổ sung expression/AuthorizationManager có policy dữ liệu cụ thể.

Trong cấu hình proxy mặc định, **self-invocation** (một method trong bean gọi method được annotation bảo vệ của chính bean đó) có thể bỏ qua Spring AOP proxy. Vì vậy không nên coi `@PreAuthorize` là biện pháp duy nhất để bảo vệ mọi luồng nội bộ nếu kiến trúc có self-call.

## 12. Authentication hợp lệ không phải quyền gọi mọi method

Với JWT, Resource Server cần có `JwtDecoder` tin cậy để kiểm tra:

- Chữ ký JWS, algorithm và khóa.
- Issuer `iss`.
- Audience `aud` dành cho API.
- Hạn dùng `exp` và thời điểm hiệu lực `nbf`.
- Những claim bắt buộc khác theo token profile.

Ví dụ:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences: orders-api
```

Trong các phiên bản Boot hỗ trợ `audiences`, property này có thể ràng buộc audience cho decoder tự cấu hình. Khi ứng dụng tự khai báo `JwtDecoder`, các validator cần được cấu hình tương ứng; không tự giả định Boot vẫn gắn mọi property vào bean tùy biến.

### 12.1. JWT ký đúng không có nghĩa được DELETE

Token có:

```text
iss = trusted issuer
aud = orders-api
exp còn hạn
scope = orders.read
```

đã có thể hoàn thành authentication, nhưng DELETE vẫn phải bị từ chối. Authorization Server đã xác thực user/client và cấp **scope read**, không phải “mọi quyền trên resource”.

### 12.2. Client Credentials có thể là service principal

Token từ client credentials có thể đại diện cho một service:

```text
client_id = nightly-order-job
scope = orders.read
```

Không mặc định `Authentication.getName()` là một người dùng tương tác. API vẫn dùng method-based scope và policy tài nguyên/tenant phù hợp cho service identity. Nếu một job cần xóa dữ liệu, nên cấp một quyền riêng có giới hạn; không dùng credential admin rộng chỉ để giải quyết một tác vụ nhỏ.

### 12.3. OIDC ID token không phải access token cho API

OIDC ID token thường được cấp cho OIDC client để hiểu kết quả đăng nhập. Nó không thay cho access token của Resource Server, dù chứa `sub` và có chữ ký đúng. API phải kiểm tra đúng token profile và audience; có một `id_token` không tự tạo `SCOPE_orders.read`.

## 13. CSRF và CORS: method ghi có đặc điểm bảo mật riêng

### 13.1. CSRF bảo vệ trước credential tự gửi bởi browser

Các method POST, PUT, DELETE thường làm thay đổi trạng thái. Nếu ứng dụng dùng cookie/session hoặc cơ chế credential được browser tự đính kèm, **CSRF** là mối lo cần đánh giá.

Ví dụ:

```java
.csrf(AbstractHttpConfigurer::disable)
```

có thể hợp lý với một **API thuần Bearer token trong `Authorization` header**, nơi browser không tự gắn token vào request cross-site mà không có code của client. Nhưng nếu cùng ứng dụng dùng session cookie hoặc HTTP Basic trong trình duyệt để thực hiện thao tác ghi, việc tắt CSRF toàn cục có thể không phù hợp.

Không nên coi “đây là REST API” hoặc “có JWT” là điều kiện đủ để vô hiệu CSRF. Phải xét **credential được gửi bằng cách nào và browser có thể tự đính kèm không**.

### 13.2. CORS không cấp scope

Phản hồi CORS cho phép browser biết origin nào được phép đọc response qua chính sách trình duyệt. Nó không thay xác thực bearer hay quy tắc `hasAuthority`. Một request `DELETE` đi qua CORS preflight vẫn cần token chứa scope phù hợp ở request thật.

Việc cấu hình CORS phải xét cả `OPTIONS` preflight lẫn các method thực tế được cho phép. Không dùng `permitAll()` cho POST/PUT/DELETE chỉ để khắc phục lỗi CORS.

## 14. Idempotency, method override và reverse proxy

### 14.1. HTTP idempotency khác idempotency key của nghiệp vụ

DELETE và PUT được định nghĩa có tính idempotent trong ngữ nghĩa HTTP, nhưng đó không phải biện pháp chống gửi lại giao dịch hoặc bảo vệ khỏi thao tác trái quyền. Đối với POST thanh toán/đặt hàng, hệ thống có thể cần **idempotency key** để tránh tạo trùng khi client retry:

```http
POST /api/orders HTTP/1.1
Authorization: Bearer TOKEN_WITH_ORDERS_CREATE
Idempotency-Key: request-1234
Content-Type: application/json

{"items": [{"sku": "SKU-001", "quantity": 1}]}
```

`Idempotency-Key` là một quy ước API; phải có logic lưu trữ, đồng bộ, ràng buộc principal/scope/request và thời hạn phù hợp. Chỉ có header này không tự đảm bảo chống tạo trùng. Nó cũng không cấp `orders.create`.

### 14.2. HTTP method override có thể làm lệch kết quả authorization

Một số stack cũ hỗ trợ `X-HTTP-Method-Override` hoặc form parameter `_method` để biểu diễn PUT/DELETE qua POST. Nếu proxy, servlet filter và Spring Security nhìn thấy method **không thống nhất**, có thể xuất hiện sai lệch:

```text
HTTP layer ban đầu: POST /api/orders/123
Method override filter: đổi thành DELETE
Spring Security nhìn thấy method nào?
Spring MVC handler nhận method nào?
```

Nếu Spring Security cho phép POST theo scope create, nhưng controller cuối nhận DELETE, đó là sai ranh giới phân quyền. Hãy đảm bảo **thứ tự filter và cách diễn giải method thống nhất** hoặc vô hiệu hóa method override khi API không cần. Không tin header override do client tự đặt nếu chưa được thiết kế rõ.

### 14.3. HEAD và GET không nên bị proxy chuyển đổi tùy tiện

Proxy có thể tối ưu cache hoặc thực hiện health check bằng HEAD/GET. Ở tầng ứng dụng, chính sách phải phản ánh method thực tế Spring Security nhận. Nếu proxy biến method, cần biết hành vi và không để các biến đổi làm bỏ qua authorization của API.

## 15. Kiểm thử phân quyền theo method

Khi kiểm thử, cần phân biệt hai phần:

1. **JWT authentication/decoder:** xác minh chữ ký, issuer, audience, thời hạn và chuyển token thành Authentication.
2. **HTTP authorization:** với Authentication đã được tạo, request GET/POST/PUT/DELETE có được phép theo authorities hay không?

Spring Security Test hỗ trợ `MockMvc` và `jwt()` request post processor để kiểm tra tầng thứ hai.

### 15.1. Minh họa test method-specific authorization

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersHttpAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void getRequiresReadScope() throws Exception {
        mockMvc.perform(get("/api/orders/ORD-123")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void postRequiresCreateScope() throws Exception {
        mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"items\":[]}")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }
}
```

Đoạn code là ví dụ cách test policy, không phải test suite hoàn chỉnh: cần controller/service và dữ liệu test tương thích để GET có thể trả 200, và cấu hình CSRF như của API mẫu để POST không bị chặn bởi CSRF trước khi đến rule authority. Nếu test độc lập HTTP layer, có thể mock controller/service thay vì gọi database thật.

`jwt().authorities(...)` **gán sẵn Authentication cho test**, vì thế nó không chứng minh rằng JWT bearer string được parser/decoder kiểm chứng hoặc `scope`/`scp` được converter mặc định ánh xạ đúng. Muốn test phần đó, cần integration test với JWT được ký bằng test key, decoder/JWKS test và Bearer header thật.

### 15.2. Test ma trận GET, POST, PUT, DELETE

| Request | Token authorities | Kết quả tầng HTTP authorization mong đợi |
|---|---|---|
| GET `/api/orders/123` | `SCOPE_orders.read` | Cho phép đi vào controller/service |
| GET `/api/orders/123` | Chỉ `SCOPE_orders.create` | Từ chối |
| POST `/api/orders` | `SCOPE_orders.create` | Cho phép đi vào controller/service |
| POST `/api/orders` | Chỉ `SCOPE_orders.read` | Từ chối |
| PUT `/api/orders/123` | `SCOPE_orders.update` | Cho phép đi vào controller/service |
| PUT `/api/orders/123` | Chỉ `SCOPE_orders.create` | Từ chối |
| DELETE `/api/orders/123` | `SCOPE_orders.delete` | Cho phép đi vào controller/service |
| DELETE `/api/orders/123` | Chỉ `SCOPE_orders.update` | Từ chối |
| POST `/api/orders/123/cancel` | `SCOPE_orders.cancel` | Cho phép đi vào controller/service |
| POST `/api/orders/123/cancel` | Chỉ `SCOPE_orders.create` | Từ chối |
| PATCH `/api/orders/123` (chưa khai rule) | Bất kỳ scope nào | Fallback từ chối theo policy |
| HEAD `/api/orders/123` | `SCOPE_orders.read` | Cho phép nếu có HEAD rule |

“Cho phép đi vào service” **không cam kết HTTP 200/201/204**, vì request còn có thể sai payload, không tìm thấy resource hoặc vi phạm ownership/tenant policy.

### 15.3. Test các tình huống thiếu xác thực và thiếu quyền

Phân biệt:

- **Không gửi Bearer token** đến GET protected: thường 401.
- **JWT hết hạn/sai chữ ký/sai issuer/audience**: thường 401.
- **JWT hợp lệ, thiếu scope**: thường 403.
- **JWT hợp lệ, scope đủ nhưng không có quyền trên order cụ thể**: service từ chối (403/404 theo policy).
- **Method chưa được khai nhưng token hợp lệ**: với fallback denyAll có thể trả 403 trước khi controller đánh giá 405.
- **CORS preflight hợp lệ**: phải được xử lý theo cấu hình CORS, không yêu cầu bearer như request thật.

Với method-specific rules, test quan trọng nhất là **cùng path, đổi HTTP method, quyền phải thay theo**. Chỉ test GET thành công không chứng minh DELETE được bảo vệ đúng.

### 15.4. Test thứ tự rule

Một cấu hình có rule rộng đặt trước:

```java
.requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.DELETE, "/api/orders/{orderId}")
    .hasAuthority("SCOPE_orders.delete")
```

phải được nhận diện là rủi ro: DELETE có thể khớp rule đầu. Một test với **read-only token thực hiện DELETE** giúp phát hiện bug kiểu này; mong đợi request **không** vào service xóa.

## 16. Những tình huống dễ gây nhầm

| Sai lầm | Hậu quả | Hướng xử lý |
|---|---|---|
| Chỉ match `"/api/orders/**"` mà không giới hạn method | Quyền read có thể áp cả DELETE | Dùng `requestMatchers(HttpMethod.X, ...)`, rule cụ thể trước |
| `.anyRequest().authenticated()` sau vài rule read/write | Method chưa khai có thể chỉ cần token hợp lệ | Cân nhắc `denyAll()` cho API cần allowlist |
| Nghĩ GET luôn public | Lộ dữ liệu nhạy cảm | GET vẫn cần scope/ownership đúng |
| Nghĩ POST luôn ghi | POST search có thể chỉ đọc, POST cancel có thể nhạy cảm hơn create | Chọn authority theo nghiệp vụ endpoint |
| Nghĩ PUT chỉ update | PUT có thể tạo mới theo hợp đồng | Cấm upsert hoặc kiểm tra quyền create khi cần |
| Nghĩ DELETE idempotent thì không cần quyền đặc biệt | Xóa dữ liệu trái phép | Kiểm tra scope delete và trạng thái resource |
| Chỉ có rule GET, quên HEAD | HEAD bị từ chối hoặc đi qua fallback khác | Quyết định chính sách HEAD rõ ràng |
| Bỏ qua OPTIONS preflight | Browser request có bearer không chạy được | Cấu hình CORS đúng; vẫn bảo vệ request thật |
| Cho phép mọi OPTIONS, tưởng đã xử lý CORS | CORS policy và authorization bị trộn | Dùng CORS filter/config nguồn đáng tin |
| Có PUT rule nhưng không có PATCH rule | PATCH bị từ chối hoặc lọt fallback quá rộng | Khai PATCH riêng nếu API hỗ trợ |
| Dùng `hasRole("orders.read")` | Không trùng `SCOPE_orders.read` | Dùng `hasAuthority` với prefix đúng |
| Nghĩ scope write tự bao gồm read/delete | Mở quyền theo giả định không có trong OAuth | Định nghĩa quan hệ quyền minh bạch |
| Token có scope đúng nhưng audience sai | Token substitution giữa API | Xác minh `aud` trước authorization |
| Token có `SCOPE_orders.delete` thì xóa được mọi order | Broken Object Level Authorization | Kiểm tra owner/tenant/business state |
| Custom JwtDecoder bỏ issuer/time validators | JWT không hợp lệ có thể được chấp nhận | Giữ validator mặc định và bổ sung yêu cầu |
| Nhiều chain chỉ bảo vệ `/api/**`, quên URL khác | Đường ngoài matcher có thể không có security filter | Tạo fallback chain hoặc matcher bao phủ |
| HTTP method override xảy ra sau khi security match | Có thể gán quyền theo method khác handler cuối | Thống nhất thứ tự filter/proxy, hoặc tắt override |
| Tắt CSRF vì “dùng JWT” khi còn session cookie | Rủi ro CSRF ở thao tác ghi | Xem xét nguồn credential của từng luồng |
| Dùng test JWT mock để khẳng định chữ ký JWT hợp lệ | Bỏ sót decoder/claim validation | Tách authorization tests và authentication integration tests |

## 17. Quy trình thiết kế phân quyền method cho một API

Khi phát triển một nhóm endpoint mới, có thể thực hiện theo trình tự:

1. **Liệt kê mọi route và method thực tế** từ Spring MVC mappings, không chỉ tên URI chung.
2. **Mô tả hiệu ứng nghiệp vụ** của mỗi endpoint: đọc, tạo, thay thế, cập nhật một phần, xóa, hủy, refund, export, search...
3. **Thiết kế scope theo nguyên tắc tối thiểu**: `orders.read`, `orders.create`, `orders.update`, `orders.delete` hoặc đơn giản hơn khi hợp đồng thật sự cho phép.
4. **Thống nhất với Authorization Server** về scope mà client có thể yêu cầu và được cấp, audience của token và loại principal.
5. **Ánh xạ scope thành GrantedAuthority** trong JWT/opaque Resource Server, thường bằng tiền tố `SCOPE_`.
6. **Khai rule method/path cụ thể trước**, đặc biệt thao tác nhạy cảm hoặc endpoint có cùng method nhưng quyền khác nhau.
7. **Đặt fallback từ chối** cho những route/method chưa xác định, tránh vô tình cho phép endpoint mới.
8. **Xử lý HEAD, OPTIONS/CORS và PATCH** theo hợp đồng, không để một method bị quên.
9. **Cấu hình CSRF phù hợp nguồn credential** và xử lý method override/proxy một cách nhất quán.
10. **Áp quyền trên từng đối tượng và trạng thái** trong service; URL ID không phải bằng chứng sở hữu.
11. **Kiểm thử ma trận method × authority**, đặc biệt token read-only gọi PUT/DELETE và token không có scope truy cập route mới.
12. **Phân biệt lỗi authentication, authorization và routing** khi quan sát 401/403/404/405.

### 17.1. Sơ đồ quyết định

```mermaid
flowchart TD
    A["Request vào API"] --> B{"Đã qua Bearer authentication?<br/>Token hợp lệ và đúng audience?"}
    B -->|"Không"| X["401"]
    B -->|"Có"| C{"SecurityFilterChain nào khớp request?"}
    C -->|"Không"| W["Khoảng trống nguy hiểm nếu không có fallback"]
    C -->|"Có"| D{"Method + path khớp rule nào đầu tiên?"}
    D -->|"Rule denyAll"| Y["403"]
    D -->|"Rule scope"| E{"Authentication có authority yêu cầu?"}
    E -->|"Không"| Y
    E -->|"Có"| F{"Policy owner/tenant/trạng thái?"}
    F -->|"Không"| Z["403/404 theo policy"]
    F -->|"Có"| G["Controller/Service xử lý"]
```

Sơ đồ là mô hình khái niệm để hiểu các lớp; trên thực tế **chain selection xảy ra trước authentication**, nên thứ tự xử lý thật là `FilterChainProxy chọn chain → authentication filters → authorization rules → controller/service`. Nếu một URL không khớp chain nào, không thể giả định nó đã qua Bearer authentication.

## 18. Tổng kết

Một cách ghi nhớ ngắn:

```text
HTTP method cho biết loại yêu cầu:
  GET      -> thường đọc
  POST     -> thường tạo / thực thi lệnh
  PUT      -> thường thay thế / cập nhật (có thể upsert)
  DELETE   -> thường xóa / chuyển trạng thái

OAuth scope cho biết phạm vi đã được cấp:
  orders.read / orders.create / orders.update / orders.delete

Spring Security biểu diễn scope dưới dạng authorities:
  SCOPE_orders.read / SCOPE_orders.create / ...

HTTP authorization áp rule:
  requestMatchers(HttpMethod, path).hasAuthority(...)

Business authorization kiểm tra:
  Đúng owner? Đúng tenant? Trạng thái cho phép? Đúng trường dữ liệu?
```

**GET, POST, PUT và DELETE phải được xem là những điều kiện phân quyền riêng khi chúng dẫn đến tác động và mức rủi ro khác nhau.** Spring Security cho phép thể hiện điều đó bằng `requestMatchers(HttpMethod.X, "...")`. Nhưng method chỉ là **một phần** của quyết định: còn phải xác minh access token, đối chiếu scope/authority theo hợp đồng, kiểm tra đường dẫn, thứ tự rules và quyền trên bản ghi thật.

Tránh hai cực đoan: **không bảo vệ tất cả method bằng một rule `authenticated()` quá rộng**, nhưng cũng **không gán quyền máy móc kiểu “mọi POST đều create, mọi GET đều public”**. Chính sách tốt được thiết kế từ hành vi nghiệp vụ của từng endpoint, rồi được thể hiện tường minh trong Spring Security.

## Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): GET/HEAD/POST/PUT/DELETE, safe và idempotent methods, 405.
- [RFC 5789 — PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789): semantics của PATCH.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token và scope.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer authentication, insufficient_scope và lỗi.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access-token claims và audience.
- [Spring Security Reference — Authorize HTTP Requests (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `requestMatchers`, `hasAuthority`, first-match rules.
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT authentication và scope mapping.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection và authorities.
- [Spring Security Reference — Multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `securityMatcher`, chain order và `HttpSecurity`.
- [Spring Security Reference — CORS (Servlet)](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): preflight và CORS configuration.
- [Spring Security Reference — CSRF (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): bảo vệ thao tác ghi và điều kiện CSRF.
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize` và bảo vệ service.
