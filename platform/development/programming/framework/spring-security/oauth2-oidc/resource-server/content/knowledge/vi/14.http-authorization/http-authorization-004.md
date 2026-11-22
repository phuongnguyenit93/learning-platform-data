# Thứ tự khớp quy tắc và quy tắc mặc định cho các yêu cầu còn lại

Trong **Spring Security OAuth 2.0/OIDC Resource Server** sử dụng Servlet, cấu hình phân quyền HTTP thường được khai báo bằng `HttpSecurity.authorizeHttpRequests(...)`. Một API có thể có endpoint công khai, endpoint chỉ yêu cầu đăng nhập, endpoint yêu cầu scope riêng và endpoint quản trị. Để các chính sách này hoạt động đúng, không chỉ cần viết đúng `hasAuthority(...)` hoặc `authenticated()` mà còn phải hiểu **quy tắc nào được xét trước** và **những request không khớp bất kỳ quy tắc cụ thể nào sẽ được xử lý ra sao**.

Quy tắc cốt lõi:

> Trong danh sách quy tắc của `authorizeHttpRequests`, Spring Security duyệt các `RequestMatcher` theo **thứ tự đã khai báo**; **quy tắc khớp đầu tiên** quyết định chính sách phân quyền cho request đó. Những quy tắc phía sau không được dùng để “cứu” một quyết định từ chối đã xảy ra ở quy tắc phía trước.

Vì vậy, thường đặt **quy tắc cụ thể trước**, **quy tắc bao quát sau**, và một **quy tắc mặc định cho các request còn lại** ở cuối. Đối với API nhạy cảm, một chiến lược an toàn là `anyRequest().denyAll()` để những endpoint mới không tự xuất hiện dưới một chính sách quá rộng; trong các hệ thống có yêu cầu khác, `anyRequest().authenticated()` cũng có thể phù hợp nhưng phải hiểu rõ giới hạn của nó.

Bài này tập trung vào **Phân quyền HTTP** trong ngữ cảnh Resource Server nhận Bearer JWT hoặc opaque token. Các ví dụ dùng Spring Boot, Spring Security Servlet và Java; có đối chiếu với WebFlux khi cần. URI, scope, tên API và issuer đều là dữ liệu minh họa.

## 1. Phân biệt xác thực token và quyết định phân quyền HTTP

Client gửi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

Trong Resource Server, Spring Security kiểm tra access token và xây dựng một `Authentication` đã xác thực. Với JWT, `JwtDecoder` xác minh chữ ký, issuer, thời gian, audience theo cấu hình và `JwtAuthenticationConverter` thường ánh xạ claim `scope` hoặc `scp` thành các `GrantedAuthority` như `SCOPE_orders.read`. Với opaque token, `OpaqueTokenIntrospector` xác thực thông qua introspection endpoint đáng tin và tạo principal/authorities.

Sau khi authentication phù hợp, authorization mới xét **request nào đang được gọi** và **rule tương ứng có được thỏa không**.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Spring Security FilterChainProxy"]
    B --> C["Bearer token authentication (nếu có)"]
    C --> D["AuthorizationFilter"]
    D --> E["RequestMatcherDelegatingAuthorizationManager"]
    E --> F{"Quy tắc khớp đầu tiên"}
    F --> G["permitAll"]
    F --> H["authenticated"]
    F --> I["hasAuthority / hasRole"]
    F --> J["denyAll"]
    G --> K["Tiếp tục tới ứng dụng"]
    H --> L{"Điều kiện đạt?"}
    I --> L
    J --> M["Từ chối"]
    L -->|Có| K
    L -->|Không| M
~~~

Các ví dụ OAuth 2.0/OIDC thường nói đến **token scope**, nhưng `authorizeHttpRequests` không mặc định biết mỗi URL cần scope nào. Chính ứng dụng phải viết ánh xạ endpoint → rule. Chẳng hạn:

~~~text
GET  /api/orders/**  → SCOPE_orders.read
POST /api/orders     → SCOPE_orders.create
GET  /api/admin/**   → ROLE_ADMIN
GET  /health/public  → permitAll
Phần còn lại         → denyAll hoặc authenticated theo thiết kế
~~~

**Xác thực thành công không đồng nghĩa được phép truy cập mọi endpoint.** Token đúng chữ ký và chưa hết hạn vẫn có thể bị `403 Forbidden` nếu thiếu scope. Ngược lại, `permitAll()` không biến một JWT sai thành JWT hợp lệ: nếu client tự gửi Bearer token không hợp lệ tới một URL công khai trong chain có Bearer authentication, filter xác thực có thể từ chối request trước khi rule `permitAll` được đánh giá.

## 2. “Thứ tự khớp” thực sự có nghĩa gì?

`authorizeHttpRequests` tạo một tập các ánh xạ:

~~~text
RequestMatcher 1  → AuthorizationManager 1
RequestMatcher 2  → AuthorizationManager 2
RequestMatcher 3  → AuthorizationManager 3
...
RequestMatcher N  → AuthorizationManager N
~~~

Khi một request tới:

1. Spring Security lấy thông tin request HTTP (method, path và các thuộc tính khác tùy matcher).
2. Nó kiểm tra matcher đầu tiên.
3. Nếu matcher không khớp, chuyển xuống matcher tiếp theo.
4. Nếu matcher khớp, dùng **authorization manager đi kèm** để quyết định cho phép hay từ chối.
5. Không tiếp tục xét các matcher sau chỉ vì authorization manager của matcher đã khớp trả kết quả từ chối.

Ví dụ:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
~~~

Request `GET /api/admin/users` khớp `/api/**` **trước** `/api/admin/**`. Vì vậy nó chịu `authenticated()`, **không phải** `hasRole("ADMIN")`. Một người dùng thường chỉ cần được xác thực là có thể vượt qua HTTP rule đó, dù developer dự định bảo vệ URL admin bằng role.

Viết lại thứ tự:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
)
~~~

Lúc này `/api/admin/users` được xét ở matcher admin trước, nên phải có `ROLE_ADMIN` theo default role prefix.

### 2.1. Không có “ưu tiên tự động cho pattern dài hơn”

Không nên giả định `/api/admin/**` được Spring Security tự ưu tiên hơn `/api/**` chỉ vì nó cụ thể hơn hoặc dài hơn. Trong mô hình khai báo bằng `authorizeHttpRequests`, **thứ tự khai báo** là một phần chính sách.

| Matcher đầu tiên khớp | Matcher phía sau | Kết quả thực tế |
|---|---|---|
| `/api/** → authenticated` | `/api/admin/** → hasRole("ADMIN")` | HTTP rule admin có thể không bao giờ được áp cho URL admin |
| `/api/admin/** → hasRole("ADMIN")` | `/api/** → authenticated` | Admin cần `ROLE_ADMIN`; URL API khác cần authenticated |
| `/** → permitAll` | `/api/** → authenticated` | Request có thể được phép quá rộng |
| `/api/orders/** → hasAuthority("SCOPE_orders.read")` | `POST /api/orders → hasAuthority("SCOPE_orders.create")` | Nếu POST được matcher đầu tiên bao phủ, nó bị áp sai rule đọc |

Dòng cuối minh họa thêm một yếu tố: matcher **không giới hạn HTTP method** thường áp dụng cho nhiều phương thức. Không phải cứ viết matcher đúng đường dẫn là đúng chính sách.

### 2.2. Một lần khớp không có nghĩa một lần cho phép

Nếu request khớp:

~~~java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
~~~

nhưng principal không có `ROLE_ADMIN`, Spring Security **từ chối**. Nó không chuyển sang rule phía sau `.requestMatchers("/api/**").authenticated()` để thử lại. Đây là thuộc tính quan trọng ngăn “fallback sang rule dễ hơn”, đồng thời là lý do phải xác định thứ tự trước khi triển khai.

### 2.3. Tên `RequestMatcher` quan trọng hơn hình dạng chuỗi

`requestMatchers(...)` có nhiều overload, và matcher có thể xét method, URL path, dispatcher type hoặc điều kiện khác. Semantics của chuỗi path phụ thuộc loại matcher được Spring Security chọn/cấu hình và phiên bản framework, chẳng hạn matcher tích hợp với Spring MVC hay các matcher chuyên dụng.

Đừng nghĩ `requestMatchers("/api/**")` đang chạy một thuật toán regex tùy ý. Khi có yêu cầu phức tạp, hãy chọn rõ implementation matcher phù hợp và xác minh các đường dẫn có dấu slash, URI encoding, servlet path hoặc proxy prefix theo kiến trúc triển khai. Dù vậy, **đối với cùng một danh sách rule**, quy tắc đầu tiên khớp vẫn là điểm thiết kế cần giữ.

## 3. Ví dụ cơ bản: Resource Server với nhiều mức quyền

Giả sử API quản lý đơn hàng có:

| Endpoint | Quyền truy cập mong muốn |
|---|---|
| `GET /public/catalog` | Công khai |
| `GET /api/orders/**` | Bearer token với `orders.read` |
| `POST /api/orders` | Bearer token với `orders.create` |
| `PUT /api/orders/{id}` | Bearer token với `orders.update` |
| `DELETE /api/orders/{id}` | Bearer token với `orders.delete` |
| `/api/admin/**` | Role quản trị đã được issuer/ứng dụng ánh xạ tin cậy |
| `/api/profile` | Principal đã xác thực |
| Tất cả đường dẫn khác | Từ chối theo chính sách mặc định `denyAll` |

### 3.1. Dependencies

Ví dụ Spring Boot dùng Servlet/Spring MVC và JWT:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 3.2. Cấu hình trusted issuer

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
~~~

Issuer URI phải đến từ hợp đồng với Authorization Server. Resource Server cũng nên xác minh audience dành riêng cho Orders API, ví dụ `orders-api`, bằng property/validator thích hợp của phiên bản framework. **Chỉ tin issuer chưa đảm bảo token được phát hành cho API này.**

### 3.3. SecurityFilterChain có thứ tự rule rõ ràng

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersApiSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/catalog")
                    .permitAll()
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .requestMatchers(HttpMethod.PUT, "/api/orders/*")
                    .hasAuthority("SCOPE_orders.update")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/*")
                    .hasAuthority("SCOPE_orders.delete")
                .requestMatchers("/api/profile")
                    .authenticated()
                .anyRequest()
                    .denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Ở đây các matcher admin đứng trước, sau đó là các endpoint API phân theo **method**, rồi profile và `anyRequest().denyAll()` ở cuối. Nếu ứng dụng có thêm một endpoint, nó không tự được chấp nhận cho tới khi chính sách phân quyền được khai báo.

**Đây là ví dụ security rules, chưa phải project runnable hoàn chỉnh**: các controller, service, validator audience, quyền sở hữu bản ghi và chính sách CSRF/session/CORS tùy loại client cần được thiết kế riêng.

#### Cẩn thận khi dùng `/api/orders/*`

Pattern một dấu sao thường dùng để mô tả một đoạn path, còn `/**` thường bao phủ nhiều đoạn. Chi tiết matching do loại `RequestMatcher` quyết định. Nếu nghiệp vụ chỉ cho sửa `/api/orders/{id}`, nên xác định rõ URL shape, phương thức, route có nested segments hay không và kiểm tra kết quả bằng HTTP tests. Không dùng `/**` rộng hơn chỉ để “cho match được” khi mục tiêu thực là một ID trong một segment.

### 3.4. Token scope trở thành authority nào?

JWT được phát hành bởi issuer tin cậy có payload minh họa:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.create",
  "exp": 1924992000
}
~~~

Sau validation, converter mặc định thông dụng ánh xạ:

~~~text
scope = orders.read orders.create
    ↓
GrantedAuthority("SCOPE_orders.read")
GrantedAuthority("SCOPE_orders.create")
~~~

Do đó request `GET /api/orders/42` đạt rule đọc, và `POST /api/orders` đạt rule tạo nếu tất cả điều kiện khác phù hợp. Token này **không có** `SCOPE_orders.delete` nên request DELETE tương ứng bị từ chối ở authorization.

Claim `scope` từ JWT chỉ đáng tin **sau khi** decoder xác minh chữ ký và các điều kiện issuer/time/audience/profile theo hợp đồng. Nếu dùng opaque token, authorities được xây từ kết quả introspection đáng tin thay cho JWT decoder.

### 3.5. Rule HTTP không thay quyền trên từng đơn hàng

Một principal có `SCOPE_orders.read` vẫn không nhất thiết được xem **mọi** đơn hàng. Rule HTTP kiểm tra loại thao tác; service còn phải kiểm tra đơn hàng thuộc đúng user/tenant, hoặc được chia sẻ theo policy.

~~~text
HTTP authorization:
    Có SCOPE_orders.read?
             ↓
Service authorization:
    Order thuộc subject/tenant được phép?
             ↓
Trả dữ liệu nghiệp vụ
~~~

Không dùng `anyRequest().authenticated()` thay cho những kiểm tra cấp bản ghi. Quy tắc mặc định là “cửa vào” ở mức HTTP, không phải toàn bộ mô hình phân quyền ứng dụng.

## 4. Quy tắc mặc định cho các yêu cầu còn lại

Sau những matcher cụ thể, ứng dụng thường khai báo `anyRequest()` như một rule cuối cùng áp dụng cho request chưa được match trong **security chain hiện tại**. Việc chọn rule này thể hiện **chính sách bảo mật mặc định** của API.

| Rule cuối | Điều kiện để request còn lại đi tiếp | Đặc điểm sử dụng |
|---|---|---|
| `anyRequest().denyAll()` | Không request còn lại nào được phép bởi rule đó | **Default deny / allowlist endpoint**; tốt cho API cần kiểm soát bề mặt truy cập chặt |
| `anyRequest().authenticated()` | Principal đã xác thực hợp lệ | Chặn anonymous, nhưng không bắt buộc scope riêng; cần đánh giá kỹ với các endpoint nhạy cảm |
| `anyRequest().permitAll()` | Cho phép ở tầng HTTP authorization | Thích hợp cho chain được thiết kế dành riêng tài nguyên công khai; rất rủi ro nếu đặt làm mặc định cho API bảo vệ |
| `anyRequest().hasAuthority("SCOPE_api.access")` | Principal có một authority bắt buộc | Dùng khi **tất cả** endpoint còn lại thực sự chia sẻ cùng một quyền |
| `anyRequest().hasRole("USER")` | Principal có role theo default prefix | Phù hợp khi chính sách mọi URL còn lại đòi role đó; không thay object-level checks |

### 4.1. `denyAll`: ưu tiên không cấp quyền ngoài dự kiến

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/catalog").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.create")
    .anyRequest().denyAll()
)
~~~

Giả sử tháng sau một developer thêm `GET /api/reports/export` nhưng chưa cập nhật security rules. Nếu endpoint đi qua chain này, nó sẽ bị **denyAll**, thay vì vô tình được dùng chỉ vì client có access token bất kỳ. Đây là một lợi ích thực tế của chính sách **fail closed**.

Điểm cần hiểu: `denyAll()` chỉ từ chối những request **đã tới rule cuối trong chain đang được chọn**. Nó không tự bao trùm request đi qua một `SecurityFilterChain` khác hoặc **không khớp bất kỳ chain nào**. Phần nhiều chain được giải thích riêng bên dưới.

### 4.2. `authenticated`: cần xác thực, nhưng quyền vẫn có thể quá rộng

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/catalog").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
~~~

Với `anyRequest().authenticated()`, các URL như `/api/profile`, `/api/preferences` hay một endpoint mới `/api/payments/refund` đều chỉ yêu cầu authentication trừ khi có rule cụ thể đứng trước. Đối với dữ liệu nhạy cảm và thao tác thay đổi trạng thái, điều này có thể là **thiếu phân quyền**, vì nhiều token hợp lệ không nhất thiết được phép thực hiện những thao tác đó.

`authenticated()` hữu ích khi API hoặc khu vực hiện tại có chính sách thống nhất “mọi principal đã xác thực được phép truy cập”, chẳng hạn trang thông tin cá nhân luôn giới hạn ở **chính người gọi** bởi service. Tuy nhiên, cần có thiết kế giới hạn dữ liệu và review các endpoint mới.

### 4.3. `permitAll`: không có nghĩa mọi filter khác đều bị bỏ qua

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
)
~~~

`permitAll()` **không yêu cầu authority để vào endpoint**, nhưng request vẫn đi qua security filter chain đã chọn. Các cơ chế như CORS, security headers, firewall, Bearer token authentication hoặc filter tùy chỉnh có thể vẫn xử lý request.

Ví dụ, `GET /public/catalog` không có Bearer token có thể được phép. Nhưng một request tới chính URL này mang `Authorization: Bearer invalid-token` có thể bị Resource Server **từ chối ở tầng authentication trước khi `permitAll` được xét**. Không suy luận “public endpoint thì token sai cũng chắc chắn bỏ qua được”.

Nếu yêu cầu một nhóm đường dẫn công khai phải hoàn toàn không áp Bearer authentication, có thể thiết kế **security chain riêng** hoặc lựa chọn filter phù hợp. Điều đó phải được thiết kế và kiểm tra rõ, không tự động suy ra từ `permitAll()`.

### 4.4. Vì sao `anyRequest` phải ở cuối?

`anyRequest()` đại diện matcher bao quát những request còn lại. Sau khi dùng nó, không còn chỗ logic cho các rule phía dưới. Trong builder Spring Security hiện đại, việc khai báo thêm matcher sau `anyRequest()` có thể bị từ chối khi cấu hình vì `anyRequest` đã xác định phần catch-all.

**Không nên viết**:

~~~java
// PHẢN VÍ DỤ — đừng đặt anyRequest ở đầu rồi thêm rule sau.
.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
)
~~~

Thay vì mong matcher sau còn được áp dụng, hãy viết tất cả rule cụ thể **trước** rồi đặt `anyRequest` cuối cùng.

### 4.5. Có bắt buộc khai báo `anyRequest` không?

Tránh dựa vào hành vi “implicit default” khi không có rule catch-all, vì kết quả có thể khó suy luận từ sự kết hợp framework version, security chain và DSL. Hãy **khai báo rõ** chính sách còn lại bằng `anyRequest().denyAll()` hoặc `anyRequest().authenticated()` theo hợp đồng.

Điều quan trọng không phải một con số version cụ thể mà là **người đọc file cấu hình nhận thấy ngay endpoint không có rule riêng sẽ như thế nào**. Một security policy không nên phụ thuộc vào developer nhớ một giá trị mặc định ngầm.

## 5. Thứ tự rule theo HTTP method

Một path có thể hỗ trợ nhiều phương thức HTTP, và mỗi phương thức có hậu quả khác nhau:

~~~text
GET    /api/orders/42  → đọc
PUT    /api/orders/42  → cập nhật
DELETE /api/orders/42  → xóa
~~~

Nếu viết:

~~~java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.DELETE, "/api/orders/**")
    .hasAuthority("SCOPE_orders.delete")
~~~

thì request DELETE có thể khớp rule đầu `/api/orders/**` và **chỉ yêu cầu quyền đọc**. Không nên đặt matcher “mọi method” của cùng resource trước rule đặc thù với method.

### 5.1. Đặt các method nhạy cảm trước

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.DELETE, "/api/orders/*")
        .hasAuthority("SCOPE_orders.delete")
    .requestMatchers(HttpMethod.PUT, "/api/orders/*")
        .hasAuthority("SCOPE_orders.update")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.create")
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().denyAll()
)
~~~

Khi mọi rule liên quan đều khai báo method cụ thể, việc lỡ khai báo một rule “mọi method” ít xảy ra hơn. Nếu ứng dụng còn `PATCH`, phải có rule riêng hoặc từ chối nó ở default catch-all.

### 5.2. Mặc định an toàn cho method chưa biết

Giả sử controller thêm `PATCH /api/orders/42` nhưng chưa bổ sung policy. Với catch-all `denyAll`, request bị chặn. Với catch-all `authenticated`, mọi principal đã xác thực có thể vượt HTTP authorization và dựa vào controller/service để tự kiểm tra quyền.

Đối với các endpoint write/delete, default deny giúp giảm nguy cơ “đường dẫn mới đi qua auth nhưng không có scope phù hợp”. Tuy nhiên, service vẫn phải kiểm tra owner/tenant, và HTTP method security không thay thế các chính sách chống CSRF cho ứng dụng có cookie-based authentication.

### 5.3. HTTP `HEAD` và `OPTIONS`

Hành vi các method phụ thuộc mapping controller, servlet stack và matcher. `HEAD` có thể được xử lý gần với `GET` trong những cấu hình MVC, nhưng **đừng giả định rule GET luôn bao phủ HEAD theo cách bạn mong đợi**. Nếu metadata/resource có yêu cầu bảo mật, phải xác định policy cho HEAD tương ứng.

`OPTIONS` có thể là:

- **CORS preflight** từ browser, thường không mang Bearer token.
- Một request OPTIONS bình thường tới endpoint, không nhất thiết là preflight.

Hai trường hợp không đồng nghĩa. Đừng tự cho phép mọi `OPTIONS /**` mà chưa xét mục đích và cấu hình CORS. Phần CORS bên dưới đề cập cách xử lý thông dụng.

## 6. Một mô hình phân quyền theo phạm vi và độ nhạy cảm

Thay vì chỉ đặt `denyAll` cuối rồi coi như mọi URL được an toàn, nên phân loại các khu vực HTTP.

| Khu vực | Ví dụ | Rule nên bắt đầu xem xét |
|---|---|---|
| Public | `/public/catalog` | `permitAll`, chỉ cho phép method/path cần thiết |
| Read API | `GET /api/orders/**` | `SCOPE_orders.read` |
| Write API | `POST /api/orders` | `SCOPE_orders.create` |
| Modify API | `PUT/PATCH /api/orders/{id}` | `SCOPE_orders.update` |
| Delete API | `DELETE /api/orders/{id}` | `SCOPE_orders.delete` |
| Admin | `/api/admin/**` | Role admin hoặc permission chuyên biệt được ánh xạ đáng tin |
| Authenticated user info | `/api/profile` | `authenticated` + chỉ trả identity của caller |
| Internal management | `/actuator/**` hoặc endpoints nội bộ | Chain/điều kiện riêng, giới hạn network, quyền và visibility |
| Unknown/new endpoints | Không được phân loại | `denyAll` theo lựa chọn default-deny |

Sự phân loại này giúp code review nhanh: **endpoint mới được thêm vào nhóm nào và cần rule nào?** Không nên “mở tạm” bằng `permitAll` hoặc `authenticated` rồi quên thay lại.

### 6.1. Không đồng nhất `hasRole` với OAuth 2.0 scope

Trong Spring Security, `hasRole("ADMIN")` thường đòi authority `ROLE_ADMIN` theo default role prefix. JWT Resource Server mặc định thường ánh xạ `scope="orders.read"` thành `SCOPE_orders.read`. Hai namespace khác nhau:

~~~text
scope = orders.admin      → SCOPE_orders.admin
role  = ADMIN             → ROLE_ADMIN (nếu có custom mapping tin cậy)
~~~

Nếu issuer có claim `roles` nhưng ứng dụng chưa cấu hình converter, `hasRole("ADMIN")` có thể luôn từ chối vì `ROLE_ADMIN` không được tạo. Không sửa lỗi bằng cách bỏ `hasRole` hoặc chuyển admin endpoint sang `authenticated`; hãy làm rõ nguồn và ánh xạ authority đáng tin.

### 6.2. Quy tắc chung dùng `hasAnyAuthority`

Khi đúng hợp đồng, có thể cho một endpoint chấp nhận một trong nhiều scope:

~~~java
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAnyAuthority("SCOPE_reports.read", "SCOPE_reports.admin")
~~~

Điều này biểu diễn **OR giữa các authorities** cho một matcher. Nhưng đừng lạm dụng khi policy yêu cầu **cùng lúc** nhiều điều kiện, chẳng hạn phải có scope đúng **và** thuộc tenant hợp lệ. Khi chính sách phức tạp, cân nhắc `AuthorizationManager` tùy chỉnh hoặc method/domain authorization.

### 6.3. Giữ service-level authorization

Ví dụ:

~~~text
GET /api/orders/42
JWT principal sub = user-123
authorities = [SCOPE_orders.read]

Order 42:
  owner = user-456
~~~

HTTP rule có thể đạt nhưng **không đồng nghĩa request được trả nội dung đơn hàng**. Nếu service không kiểm tra owner/tenant, API có nguy cơ Broken Object Level Authorization. Rule catch-all không giải quyết được lỗi phân quyền dữ liệu cấp bản ghi.

## 7. `permitAll`, `anonymous` và `authenticated` khác nhau thế nào?

Một số rule Spring Security phổ biến:

| Rule | Ý định |
|---|---|
| `permitAll()` | Cho phép request tại tầng authorization bất kể principal có được xác thực hay không |
| `denyAll()` | Từ chối request |
| `authenticated()` | Yêu cầu principal đã xác thực, không chỉ anonymous |
| `anonymous()` | Dành cho request được xem là anonymous |
| `fullyAuthenticated()` | Yêu cầu mức xác thực đầy đủ theo trust resolver; có ý nghĩa khi có remember-me |
| `hasAuthority("...")` | Yêu cầu đúng authority được khai báo |
| `hasRole("...")` | Kiểm tra role theo quy tắc role prefix |

Trong API Bearer JWT không sử dụng remember-me, `fullyAuthenticated` có thể cho kết quả tương tự `authenticated` đối với nhiều request, nhưng không nên xem hai rule đồng nghĩa trong mọi kiến trúc Spring Security.

Một trang login dạng browser có thể dùng `anonymous()` theo thiết kế, nhưng một Resource Server API thuần Bearer thường không có nhu cầu đó. Nếu có login session và Bearer token trong cùng ứng dụng, cần xác định request matcher, các authentication mechanism và policy riêng.

### 7.1. Public không có nghĩa bỏ qua xác thực token sai

~~~text
GET /public/catalog

Không Authorization header:
    → permitAll có thể cho phép

Authorization: Bearer invalid-token:
    → BearerTokenAuthenticationFilter có thể từ chối
       trước khi AuthorizationFilter áp permitAll
~~~

Đừng viết client cố gửi một Bearer token rỗng/hết hạn tới mọi endpoint công khai rồi cho rằng ứng dụng phải bỏ qua. Ở phía server, nếu muốn tách endpoint public khỏi Bearer authentication, cần thiết kế chuỗi filter phù hợp.

### 7.2. Lỗi 401 và 403 khi rule không đạt

| Trường hợp | Kết quả thường thấy |
|---|---|
| Request tới endpoint `authenticated()` không có token | 401 |
| Request có Bearer JWT sai chữ ký/hết hạn | 401 |
| JWT hợp lệ thiếu `SCOPE_orders.read` | 403 |
| JWT hợp lệ thiếu `ROLE_ADMIN` | 403 |
| Request `denyAll` từ principal đã xác thực | Thường 403 |
| Request `denyAll` từ anonymous | Có thể kích hoạt entry point 401 tùy cơ chế xử lý |
| Request `permitAll` không có token | Thường được phép đi tiếp |
| Request `permitAll` mang Bearer token không hợp lệ | Có thể 401 ở filter authentication |

Đây là những trạng thái **thường gặp**, không phải khẳng định bất biến: `AuthenticationEntryPoint`, `AccessDeniedHandler`, security chain và exception handling có thể quyết định chi tiết response khác.

## 8. Hai tầng thứ tự khác nhau: chọn `SecurityFilterChain` và chọn rule

Trong ứng dụng Servlet có nhiều `SecurityFilterChain`, **không chỉ tồn tại một danh sách matcher**. Cần phân biệt hai tầng:

1. **Tầng chọn chain**: `FilterChainProxy` xét các `SecurityFilterChain` theo thứ tự và chọn **chain đầu tiên khớp request**.
2. **Tầng HTTP authorization**: trong chain đã chọn, `AuthorizationFilter` dùng các matcher của `authorizeHttpRequests`, lại chọn **rule đầu tiên khớp request**.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["FilterChainProxy"]
    B --> C{"SecurityFilterChain đầu tiên nào khớp?"}
    C -->|"Chain @Order(1)"| D["Chain A: /api/**"]
    C -->|"Chain @Order(2)"| E["Chain B: phần còn lại"]
    C -->|"Không chain nào"| X["Không được Spring Security bảo vệ bởi chain nào"]
    D --> F["authorizeHttpRequests trong A"]
    E --> G["authorizeHttpRequests trong B"]
    F --> H["Rule A1 → A2 → ... → anyRequest"]
    G --> I["Rule B1 → B2 → ... → anyRequest"]
    H --> J["Quyết định authorization"]
    I --> J
~~~

**Một `anyRequest().denyAll()` trong Chain A không áp dụng cho request chưa từng được Chain A chọn.** Đây là điểm đặc biệt quan trọng nếu API có chain riêng cho `/api/**`, chain riêng cho form login hoặc endpoint công khai và management endpoints.

### 8.1. `securityMatcher` quyết định phạm vi chain

Ví dụ:

~~~java
http.securityMatcher("/api/**");
~~~

Ý nghĩa: `SecurityFilterChain` được cấu hình qua `http` này chỉ có cơ hội bảo vệ các request khớp `/api/**`. Nếu request là `GET /docs/index.html`, chain này không được chọn chỉ vì bên trong có `anyRequest()`.

### 8.2. `requestMatchers` bên trong `authorizeHttpRequests` quyết định rule

Ví dụ:

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest().denyAll()
    );
~~~

Ở đây:

- `securityMatcher("/api/**")` là **phạm vi áp dụng của chain**.
- `requestMatchers(GET, "/api/orders/**")` là **phạm vi của một rule** bên trong chain.
- `anyRequest().denyAll()` xử lý những request còn lại **trong chain API**.
- `/docs/index.html` không thuộc chain này; nó cần được bảo vệ bởi một chain khác hoặc được quản lý theo chính sách đã biết.

### 8.3. `@Order` quyết định thứ tự chọn chain

Mẫu có hai chain: chain API đứng trước và chain fallback đứng sau.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class MultiChainSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/catalog")
                    .permitAll()
                .anyRequest().denyAll()
            )
            .build();
    }
}
~~~

Đây là một **phương án cấu hình thay thế**, không sao chép vào cùng ứng dụng với bean `SecurityFilterChain` toàn cục ở phần trước. Chain 1 dùng Bearer JWT authentication và bảo vệ `/api/**`. Chain 2 không khai báo `securityMatcher`, nên đóng vai trò **fallback** cho những request không match chain trước. Chính sách cụ thể của Chain 2 cho phép catalog công khai và từ chối những URL khác.

**Nếu yêu cầu `/api/profile` cũng cần hoạt động**, phải khai báo rule và endpoint trong Chain API trước `anyRequest().denyAll()`. Nếu có endpoint `/actuator/health` hoặc trang tài liệu, cần thiết kế và khai báo policy trong chain phù hợp. Ví dụ cố ý không tự mở toàn bộ actuator và docs.

### 8.4. Thứ tự chain cũng là “first match wins”

Sai:

~~~java
@Order(1)
SecurityFilterChain broadChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .build();
}
~~~

Nếu chain này không giới hạn `securityMatcher` và đứng trước một chain API được cấu hình ở thứ tự thấp hơn, nó có thể **bắt mọi request trước**, khiến chain API phía sau không được chọn.

Không có cơ chế “thử chain thứ hai nếu chain đầu tiên từ chối”. Giống rule nội bộ, **chain đầu tiên khớp là chain được dùng**. Nếu chain đầu không khớp thì mới xét chain kế tiếp.

### 8.5. Nếu không có chain nào khớp?

Đây là rủi ro lớn hơn việc chọn một rule quá rộng. Giả sử chỉ có một chain:

~~~java
@Bean
SecurityFilterChain onlyApiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
        .build();
}
~~~

Một request `GET /internal/reports` không khớp `/api/**`. Nếu **không có SecurityFilterChain khác**, nó có thể đi qua ứng dụng mà không được Spring Security bảo vệ bằng các filters của chain này. Việc đường dẫn có tồn tại hay không còn phụ thuộc controller/servlet, nhưng **không nên xem `denyAll` trong chain API là lớp bảo vệ toàn cục**.

Giải pháp thực tế là định nghĩa một **fallback chain** match những request còn lại với `denyAll` hoặc một chính sách rõ ràng. Ngoài ra, endpoint nằm ở management port/servlet context khác có thể có cơ chế bảo vệ riêng; phải xét phạm vi triển khai thực tế.

## 9. Quy tắc public path và chain API: tránh mở quá rộng

Khi một dự án trộn tài nguyên công khai với API bearer, có hai cách tổ chức phổ biến.

### 9.1. Một chain, một danh sách quy tắc

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/catalog").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
)
~~~

Ưu điểm: ngắn, dễ đọc cho ứng dụng nhỏ. Nhược điểm: `/api/**.authenticated()` là chính sách **rộng**, nên cần đặt các endpoint yêu cầu scope riêng **trước** nó và bảo đảm những endpoint mới không được mở ngoài ý muốn.

### 9.2. Nhiều chain theo khu vực

~~~text
@Order(1) /public/**   → chain công khai có security headers/CORS thích hợp
@Order(2) /api/**      → chain OAuth 2.0 Resource Server
@Order(3) fallback     → denyAll
~~~

Ưu điểm: tách các authentication mechanism, CORS và policy rõ hơn. Nhược điểm: cần kiểm soát **thứ tự chain**, phạm vi matcher, tính bao phủ và cấu hình filter.

Ví dụ một public-only chain:

~~~java
@Bean
@Order(1)
SecurityFilterChain publicChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/public/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/catalog")
                .permitAll()
            .anyRequest().denyAll()
        )
        .build();
}
~~~

Chain này không bật `oauth2ResourceServer()`, nên đối với route công khai của chain, Bearer authentication không được kích hoạt chỉ vì client gửi header Bearer. Dù vậy, các security filters khác của chain vẫn có thể thực thi. Khi dùng nhiều chain, phải thiết kế thêm API chain và fallback, không chỉ copy publicChain đứng một mình.

### 9.3. Không dùng `web.ignoring()` thay cho `permitAll()` một cách tùy tiện

Một số ứng dụng cũ cấu hình bỏ qua security cho static resources. Khi dùng cơ chế bỏ qua qua `WebSecurityCustomizer.ignoring()`, request có thể **không đi qua Spring Security filter chain**, khác với `permitAll()` vẫn giữ các filter trong chain.

Đối với endpoint công khai cần headers bảo vệ, CORS, context hoặc audit ở tầng Spring Security, thường ưu tiên thiết kế chain và `permitAll()` phù hợp thay vì bỏ qua toàn bộ filters. Chỉ dùng ignoring khi hiểu rõ hệ quả và kiểm soát route chính xác; đừng bỏ qua cả `/api/**` để giải quyết tạm một lỗi 401.

## 10. CORS preflight, OPTIONS và thứ tự xử lý

Browser gọi API cross-origin thường gửi **CORS preflight** trước khi gửi request có header `Authorization`:

~~~http
OPTIONS /api/orders/42 HTTP/1.1
Origin: https://shop.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight **không giống request GET thật** và thường không có Bearer token. Nếu security filter yêu cầu JWT cho preflight trước khi CORS được xử lý, browser có thể báo lỗi CORS dù người dùng đang có token hợp lệ.

### 10.1. Ưu tiên cấu hình CORS đúng ranh giới

Trong Spring Security:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

http.cors(withDefaults());
~~~

Cấu hình CORS phù hợp cần được cung cấp từ Spring MVC hoặc bean `CorsConfigurationSource` mà Spring Security có thể sử dụng. Ví dụ:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://shop.example.test"));
    config.setAllowedMethods(
        List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
    config.setAllowedHeaders(List.of("Authorization", "Content-Type"));

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
~~~

Đây là cấu hình CORS minh họa cho API có browser client từ một origin đã biết. Khi dùng cookies/cross-origin credentials, cần policy `allowCredentials` và `allowedOrigins` phù hợp, không kết hợp wildcard origin bừa bãi. CORS **không phải** cơ chế xác thực Bearer token; JWT vẫn cần được Resource Server kiểm tra trên request thực.

### 10.2. Có nên dùng `OPTIONS /** → permitAll` không?

Một số ví dụ mở mọi OPTIONS:

~~~java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

Đây là một chính sách phân quyền HTTP, **không tự cấu hình đầy đủ CORS**. Nó có thể cho phép cả những OPTIONS request không phải preflight và vẫn không sinh đúng `Access-Control-Allow-*` headers cho browser.

Nên ưu tiên `http.cors(...)` và cấu hình origin/method/header, đảm bảo xử lý preflight ở đúng vị trí trước authentication khi cần. Nếu tổ chức vẫn chọn rule OPTIONS để tương thích kiến trúc, hãy giới hạn và kiểm thử nó như một rule riêng; đừng dùng rule đó để vô hiệu hóa auth của những method thực.

### 10.3. CORS không làm thay đổi nguyên tắc thứ tự rule

Sau khi preflight được xử lý, request thật như `GET /api/orders/42` vẫn phải đi qua JWT authentication và matcher yêu cầu `SCOPE_orders.read`. Không được coi “Origin được phép” là quyền gọi API: một request từ origin hợp lệ nhưng token sai hoặc thiếu scope vẫn phải bị từ chối.

## 11. Dispatcher type: REQUEST, FORWARD, ERROR

Servlet có nhiều kiểu dispatch ngoài request ban đầu, chẳng hạn `FORWARD` và `ERROR`. Trong một số ứng dụng, Spring Security còn thực thi authorization khi có dispatch mới; kết quả phụ thuộc cấu hình dispatcher types và security filter registration.

Ví dụ một ứng dụng muốn cho phép dispatch nội bộ đến error page:

~~~java
import jakarta.servlet.DispatcherType;

http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().denyAll()
);
~~~

Ý nghĩa: rule `ERROR` đứng trước matcher URL có thể cho phép error dispatch tới error handling, trong khi request HTTP gốc vẫn phải qua authentication/authorization. Điều này **không có nghĩa mọi ứng dụng phải mở ERROR/FORWARD vô điều kiện**.

### 11.1. Vì sao cần thận trọng với `FORWARD`?

Nếu một endpoint công khai có thể forward đến controller/path nhạy cảm, rule `dispatcherTypeMatchers(FORWARD).permitAll()` quá rộng có thể làm mất lớp kiểm soát ở bước dispatch sau. Cần xét ai có quyền tạo forward, path đích và service authorization.

Chỉ thêm rule dispatcher type khi có nhu cầu rõ ràng và hiểu hệ quả. Đặt nó trước những matcher khác nếu dự định nó được xét ưu tiên; nhưng không biến nó thành “lối tắt” vượt qua phân quyền nghiệp vụ.

### 11.2. URL lỗi và status code

Nếu `/error` hoặc endpoint hiển thị lỗi cần xử lý anonymous request, có thể phải cấu hình rule tương ứng theo route/thực thi. Không công bố stack trace, claims JWT, headers Authorization hoặc exception nội bộ trong body chỉ vì đã cho phép đường dẫn lỗi.

## 12. Pattern khớp URL và những trường hợp dễ bỏ sót

Một rule HTTP chỉ an toàn khi matcher nhận diện đúng đường dẫn mà ứng dụng thực sự xử lý. Với các hệ thống có gateway, servlet path, API versioning hoặc encoded URL, phải xác định matcher theo cấu hình framework.

### 12.1. Slash cuối và đường dẫn lồng

Những path này không nên được coi luôn tương đương:

~~~text
/api/orders
/api/orders/
/api/orders/42
/api/orders/42/items
~~~

Tùy matcher và MVC configuration, trailing slash có thể được xử lý khác nhau. Đừng mặc định `/api/orders/*` bao phủ tất cả nested endpoints hoặc `/api/orders/**` chỉ bao phủ đúng một ID.

Nếu endpoint write/delete được phép ở `/api/orders/{id}`, cần bảo đảm rule có phạm vi tương ứng. Dùng catch-all `denyAll` là cách giảm hậu quả khi path mới xuất hiện ngoài quy tắc đã thiết kế.

### 12.2. Context path, servlet path và reverse proxy

Giả sử client gọi:

~~~text
https://gateway.example.test/shop/api/orders/42
~~~

Gateway có thể strip prefix `/shop` trước khi chuyển request đến ứng dụng, hoặc ứng dụng có `server.servlet.context-path`. Matcher trong Spring Security được áp trên request đã đi vào servlet container theo semantics của matcher được chọn. Vì vậy **đừng sao chép nguyên đường dẫn public của gateway vào matcher mà không xác định path ứng dụng thực sự thấy**.

Đối với nhiều servlet mappings hoặc servlet path phức tạp, dùng API matcher được framework hỗ trợ và cấu hình base path/servlet path rõ ràng; không chỉ thêm `/**` để né lỗi 404/403.

### 12.3. Encoded paths và HTTP firewall

Các dạng như encoded slash, dấu chấm, semicolon/matrix parameters hoặc path traversal cần được xử lý nhất quán giữa gateway, servlet container và Spring Security. Các phiên bản Spring Security có cơ chế HTTP firewall, nhưng không nên tùy tiện nới firewall để một matcher “match được”. Chênh lệch normalization giữa proxy và app có thể tạo đường dẫn bỏ qua policy nếu không được kiểm soát.

### 12.4. Phương thức HTTP phải được xét cùng path

Một matcher `/api/orders/**` không giới hạn method có thể áp cho GET, POST, PUT, PATCH, DELETE và OPTIONS. Nếu ứng dụng cần **read-only** ở một nhánh, phải viết rule có method cụ thể hoặc chính sách từ chối các method còn lại.

### 12.5. API versioning

~~~text
/api/v1/orders/**
/api/v2/orders/**
~~~

Một rule cho `/api/v1/**` không tự áp cho `/api/v2/**` nếu matcher không khớp. Với default deny, API v2 mới có thể bị chặn cho đến khi chính sách được bổ sung. Đây là hành vi đáng mong muốn khi tổ chức có quy trình review policy cho mỗi phiên bản API.

## 13. Kiểm tra thứ tự quy tắc bằng bảng tình huống

Giả sử một API có chính sách:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/catalog").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.create")
    .requestMatchers("/api/profile").authenticated()
    .anyRequest().denyAll()
)
~~~

### 13.1. Ma trận chọn rule

| Request | Matcher đầu tiên khớp | Policy được áp dụng |
|---|---|---|
| `GET /public/catalog` | GET `/public/catalog` | `permitAll` |
| `POST /public/catalog` | `anyRequest` | `denyAll` |
| `GET /api/admin/users` | `/api/admin/**` | `hasRole("ADMIN")` |
| `POST /api/admin/users` | `/api/admin/**` | `hasRole("ADMIN")` |
| `GET /api/orders/42` | GET `/api/orders/**` | `hasAuthority("SCOPE_orders.read")` |
| `POST /api/orders` | POST `/api/orders` | `hasAuthority("SCOPE_orders.create")` |
| `DELETE /api/orders/42` | `anyRequest` | `denyAll` (chưa có rule DELETE riêng trong mẫu này) |
| `GET /api/profile` | `/api/profile` | `authenticated` |
| `GET /api/reports/export` | `anyRequest` | `denyAll` |
| `GET /unknown` | `anyRequest` | `denyAll` |

Khi request không match rule cụ thể, `anyRequest` bảo đảm có một chính sách rõ ràng trong chain. **Đây mới là bảng matcher**, chưa phải bảng HTTP status: request tới `hasRole("ADMIN")` còn cần principal có role và có thể chịu thêm policy nghiệp vụ.

### 13.2. Ma trận token và authorization

Giả sử JWT đã qua signature, issuer, audience, expiry validation:

| Request | Authorities đã xác thực | Kết quả ở HTTP authorization |
|---|---|---|
| `GET /public/catalog` | Không có token | Cho phép ở rule công khai |
| `GET /api/orders/42` | `SCOPE_orders.read` | Cho phép tại HTTP layer |
| `GET /api/orders/42` | `SCOPE_orders.create` | Từ chối vì thiếu quyền đọc |
| `POST /api/orders` | `SCOPE_orders.create` | Cho phép tại HTTP layer |
| `POST /api/orders` | `SCOPE_orders.read` | Từ chối vì thiếu quyền tạo |
| `GET /api/admin/users` | `ROLE_ADMIN` | Cho phép tại HTTP layer |
| `GET /api/admin/users` | `SCOPE_orders.read` | Từ chối vì thiếu `ROLE_ADMIN` |
| `GET /api/profile` | Đã xác thực, authorities rỗng | Cho phép tại HTTP layer theo `authenticated` |
| `GET /api/reports/export` | `ROLE_ADMIN` và mọi scope khác | Từ chối do catch-all `denyAll` |

Điểm cuối đáng chú ý: **`denyAll` vẫn từ chối admin**. Nó biểu diễn lựa chọn không cho bất kỳ request chưa được phân loại nào đi qua, không phải “chỉ chặn anonymous”.

## 14. Tạo HTTP tests phát hiện sai thứ tự

Với Spring Security Test, có thể dùng `MockMvc` và `jwt()` request post processor để kiểm tra **quy tắc HTTP authorization** mà không cần token thật từ IdP.

~~~gradle
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Giả sử dự án đã có controller cho các URL được test và security chain ở mục 13, một ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void readRequiresReadScope() throws Exception {
        mvc.perform(
                get("/api/orders/42")
                    .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read")
                    ))
            )
            .andExpect(status().isOk());
    }

    @Test
    void readScopeDoesNotGrantAdminRoute() throws Exception {
        mvc.perform(
                get("/api/admin/users")
                    .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read")
                    ))
            )
            .andExpect(status().isForbidden());
    }

    @Test
    void newEndpointIsDeniedEvenWithAuthenticatedJwt() throws Exception {
        mvc.perform(
                get("/api/reports/export")
                    .with(jwt().authorities(
                        new SimpleGrantedAuthority("ROLE_ADMIN")
                    ))
            )
            .andExpect(status().isForbidden());
    }
}
~~~

**Lưu ý về ví dụ test**:

- Đây là mẫu test cấu hình **HTTP authorization** và giả định controller/service của các đường dẫn thành công hoạt động, ví dụ `GET /api/orders/42` trả HTTP 200 khi người gọi được phép. Nếu controller chưa tồn tại, response thành công có thể là 404 thay vì 200.
- `jwt()` từ `spring-security-test` giả lập principal đã xác thực với authorities đã chọn. Nó **không kiểm tra chữ ký JWT, JWK Set, issuer, audience, expiry** như một request Bearer token thực.
- Những test integration khác cần gửi JWT thử nghiệm **có chữ ký thật** qua `Authorization: Bearer` và cấu hình decoder/JWK đáng tin để xác minh tầng authentication.
- Nếu sử dụng opaque token, có các helper/mocks tương ứng để kiểm tra HTTP rule, còn introspection integration cần được thử riêng.

### 14.1. Test cụ thể lỗi quy tắc bao quát đứng trước

Giả sử ai đó vô tình viết:

~~~java
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
~~~

Test `readScopeDoesNotGrantAdminRoute` sẽ phát hiện vấn đề nếu HTTP request tới admin với JWT có `SCOPE_orders.read` nhưng không có `ROLE_ADMIN` vẫn được cho qua HTTP authorization. Khi đó điểm sửa là **đưa matcher admin lên trước** hoặc thiết kế lại quy tắc, không sửa test để chấp nhận kết quả yếu hơn.

### 14.2. Test method, không chỉ path

Một test GET thành công không chứng minh DELETE cùng URL bị chặn đúng:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;

@Test
void deleteIsDeniedWithoutDeletePolicy() throws Exception {
    mvc.perform(
            delete("/api/orders/42")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read")
                ))
        )
        .andExpect(status().isForbidden());
}
~~~

Đoạn test minh họa giả định **cấu hình Resource Server dùng Bearer token không bị một lớp CSRF riêng trả 403 trước HTTP authorization**. Với ứng dụng dùng cookie/session và CSRF, test thao tác thay đổi trạng thái có thể cần CSRF token hợp lệ để phân biệt lỗi CSRF với lỗi authority. Dù kết quả đều là 403, mục đích test khác nhau; không nên nhầm một 403 do CSRF với bằng chứng quyền DELETE đã được cấu hình đúng.

### 14.3. Test đường dẫn ngoài scope chain

Khi có nhiều `SecurityFilterChain`, test không chỉ `/api/**` mà còn:

~~~text
/public/catalog
/docs/index.html
/actuator/health
/internal/reports
/api/v2/orders/42
~~~

Mục tiêu là xác định **chain nào được chọn** và **rule nào trong chain đó áp dụng**. Một test `/api/orders` thành công không chứng minh `/internal/reports` có được Spring Security bảo vệ.

### 14.4. Những trường hợp test không nên thiếu

| Tình huống | Mục tiêu |
|---|---|
| Anonymous gọi URL public | `permitAll` đúng phạm vi |
| Anonymous gọi protected endpoint | Yêu cầu xác thực |
| Authenticated nhưng thiếu authority | `hasAuthority` thật sự từ chối |
| JWT có authority đúng | Rule tương ứng cho đi tiếp |
| Non-admin gọi URL admin | Matcher admin đứng trước matcher rộng |
| GET có quyền đọc, DELETE chỉ có quyền đọc | Rule method không bị rule chung nuốt |
| URL mới chưa có rule cụ thể | Catch-all `denyAll` hoạt động |
| URL ngoài `securityMatcher` của API chain | Fallback chain bảo vệ request |
| CORS preflight từ origin được phép | CORS được xử lý đúng mà không hạ bảo mật GET/POST thật |
| Encoded/trailing-slash path | Không có đường dẫn bất ngờ vượt matcher |
| ERROR/FORWARD dispatch nếu ứng dụng dùng | Chính sách dispatch không mở đường bypass |

## 15. Khi dùng `anyRequest().authenticated()` cần quyết định thêm gì?

`anyRequest().authenticated()` không sai trong mọi hệ thống. Nó phù hợp khi bạn **cố ý cho tất cả endpoint chưa phân loại ở chain đó dùng chung chính sách “cần xác thực”**. Nhưng nó cần các điều kiện bổ trợ.

### 15.1. API chỉ đọc dữ liệu của chính caller

Ví dụ `GET /api/me` hoặc `GET /api/preferences` chỉ trả dữ liệu của principal hiện tại. `authenticated()` có thể đủ ở HTTP layer **nếu**:

1. Service không nhận một user ID tùy ý rồi trả dữ liệu của người khác.
2. Subject/issuer/tenant được dùng nhất quán.
3. Response không chứa thông tin nhạy cảm ngoài contract.
4. Các mutation endpoints có rule thích hợp.
5. Mọi endpoint mới được review về authorization nghiệp vụ.

Như vậy, `authenticated()` là điều kiện cần ở tầng HTTP, còn quyền trên dữ liệu phải được bảo vệ bằng thiết kế service.

### 15.2. API đa scope

Với Orders API, token `orders.read` và token `orders.create` có khả năng khác nhau. Nếu catch-all `authenticated` áp cho những write endpoint chưa phân loại, client chỉ có `orders.read` có thể vượt HTTP rule của write endpoint. Vì vậy policy cần tách các method/route nhạy cảm rõ ràng hoặc chọn `denyAll` cho unknown endpoints.

### 15.3. API đa tenant

`authenticated()` chỉ xác nhận request có principal hợp lệ theo cơ chế authentication. Nó **không mặc nhiên biết tenant nào được phép truy cập tài nguyên nào**. Token có thể thuộc tenant A mà request lại tham chiếu dữ liệu tenant B. Cần ràng buộc tenant ở token validation nếu hợp đồng yêu cầu, và ở domain authorization khi truy cập bản ghi.

### 15.4. API nhận token từ nhiều issuer

Khi một API tin nhiều issuer, cùng một authority string như `SCOPE_reports.read` có thể có ngữ nghĩa khác nhau giữa các nhà phát hành. Cần quản lý danh sách issuer đáng tin, audience, token profile và authority mapping theo từng bên; không để `authenticated()` mở toàn bộ endpoint chỉ vì một issuer có thể phát hành access token cho hệ thống.

## 16. Lỗi thường gặp khi cấu hình thứ tự

### 16.1. Đặt matcher rộng trước matcher admin

~~~java
// PHẢN VÍ DỤ:
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
~~~

Admin URL bị matcher rộng chiếm trước, khiến rule role phía sau không được dùng. Hướng xử lý: đặt matcher admin trước.

### 16.2. Đặt GET/POST/DELETE dưới matcher không giới hạn method

~~~java
// PHẢN VÍ DỤ:
.requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.DELETE, "/api/orders/**")
    .hasAuthority("SCOPE_orders.delete")
~~~

DELETE có thể khớp rule read. Hướng xử lý: phân method rõ ràng, đặt rule hẹp trước, giữ fallback deny.

### 16.3. Đặt `permitAll` cho `/**`

~~~java
// PHẢN VÍ DỤ:
.requestMatchers("/**").permitAll()
.requestMatchers("/api/**").authenticated()
~~~

Matcher quá rộng khiến phần API đi vào policy public, rule bảo vệ phía sau bị bỏ qua.

### 16.4. Đặt `anyRequest` rồi khai báo rule phía sau

~~~java
// PHẢN VÍ DỤ:
.anyRequest().authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
~~~

Đây không phải cấu trúc “default trước, exception sau”. Builder có thể từ chối cấu hình; về ý nghĩa, catch-all đã chiếm toàn bộ request.

### 16.5. Có `denyAll` trong API chain nhưng quên fallback chain

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().denyAll());
~~~

Quy tắc này không áp cho `/internal/**` nếu request không đi vào chain API. Cần xác định chính sách cho các request nằm ngoài phạm vi chain.

### 16.6. Public matcher quá rộng

~~~java
// PHẢN VÍ DỤ nếu chỉ muốn health public:
.requestMatchers("/actuator/**").permitAll()
~~~

Pattern có thể mở nhiều endpoint management hơn ý định, gồm những endpoint không nên public. Hãy dùng URL/endpoint matcher chính xác, cấu hình management exposure và kiểm soát network theo chính sách.

### 16.7. Dùng `hasRole("ADMIN")` nhưng JWT chỉ có `SCOPE_admin`

`hasRole("ADMIN")` thường yêu cầu `ROLE_ADMIN`; JWT scope mặc định trở thành `SCOPE_admin`. Nếu muốn role, phải có converter ánh xạ từ nguồn tin cậy, hoặc chọn một authority scope cụ thể theo hợp đồng.

### 16.8. Chỉ có `authenticated` nhưng quên object-level authorization

Token hợp lệ không cho quyền xem đơn hàng bất kỳ. HTTP authorization phải được kết hợp với kiểm tra owner, tenant và các chính sách domain.

### 16.9. Mở mọi OPTIONS để giải quyết lỗi CORS

`OPTIONS /** → permitAll` không tự tạo CORS headers, cũng không thay cấu hình origin/method/header được phép. Cần xử lý CORS preflight đúng tầng và giữ auth trên request thực.

### 16.10. Tắt CSRF không phân biệt kiểu ứng dụng

Bearer token thường được gửi chủ động qua Authorization header; nhưng ứng dụng đồng thời dùng cookies/session có những rủi ro CSRF riêng. Không tắt CSRF chỉ vì muốn test POST/DELETE dễ hơn hoặc vì cấu hình OAuth Resource Server đang có mặt.

### 16.11. Đổi Servlet context path hoặc gateway prefix mà quên matcher

Các route do gateway expose không nhất thiết giống path tại servlet. Nên xác minh request path thực tế được matcher nhìn thấy; không làm rộng `/**` chỉ để tránh việc endpoint bị 403.

### 16.12. Dựa vào 401/403 để kết luận matcher chính xác

Một request 403 có thể do CSRF, domain authorization, thiếu scope hoặc `denyAll`. Một request 401 có thể do Bearer token invalid trước khi vào rule. Để hiểu đường đi, cần tách tầng authentication, matching và authorization, sử dụng test phù hợp thay vì suy ra toàn bộ chính sách từ status code duy nhất.

## 17. Đối chiếu với Spring WebFlux

Ở WebFlux, ứng dụng dùng `ServerHttpSecurity` và `SecurityWebFilterChain` thay cho `HttpSecurity` và `SecurityFilterChain`. API khai báo authorization thường là `authorizeExchange(...)`, dùng `pathMatchers(...)` và `anyExchange()`. **Ý tưởng thứ tự vẫn giống nhau: các matcher được xét theo thứ tự khai báo và rule đầu tiên khớp được áp dụng.**

### 17.1. Ví dụ reactive Resource Server

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveOrdersSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/public/catalog")
                    .permitAll()
                .pathMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Các request có scope phù hợp vẫn phải vượt JWT verification thông qua `ReactiveJwtDecoder`. Đối với opaque token, dùng cấu hình reactive introspection tương ứng. Không dùng bean `SecurityFilterChain` Servlet để thay cho `SecurityWebFilterChain` trong WebFlux.

### 17.2. So sánh các API khái niệm

| Ý định | Servlet | WebFlux |
|---|---|---|
| Cấu hình security chain | `HttpSecurity` | `ServerHttpSecurity` |
| Kết quả builder | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Phân quyền request | `authorizeHttpRequests` | `authorizeExchange` |
| Match path/method | `requestMatchers(...)` | `pathMatchers(...)` |
| Rule catch-all | `anyRequest()` | `anyExchange()` |
| Chỉ cho qua anonymous và authenticated | `permitAll()` | `permitAll()` |
| Yêu cầu authentication | `authenticated()` | `authenticated()` |
| Yêu cầu authority | `hasAuthority("SCOPE_...")` | `hasAuthority("SCOPE_...")` |
| Từ chối các request còn lại | `anyRequest().denyAll()` | `anyExchange().denyAll()` |

Ở WebFlux cũng có thể có **nhiều `SecurityWebFilterChain`**, với thứ tự và matcher chọn chain. Cần đặt chain cho API nhạy cảm trước chain bao quát và có fallback rõ ràng. Đừng để một chain matcher quá rộng chiếm hết request trước chain hẹp.

### 17.3. Reactive CORS và preflight

Trên WebFlux, CORS cũng cần được xử lý trước khi yêu cầu Bearer authentication làm thất bại preflight. `cors(...)` và các cơ chế cấu hình nguồn CORS của WebFlux có API riêng; không copy bean Servlet `UrlBasedCorsConfigurationSource` và mong tất cả chi tiết giống nhau.

Nguyên tắc không đổi: browser origin được phép **không đồng nghĩa đã được authorization**; GET/POST thật vẫn phải qua JWT/opaque authentication và kiểm tra scope.

## 18. Thiết kế chính sách mặc định theo ba kiểu ứng dụng

Không có một catch-all phù hợp cho mọi sản phẩm. Nên lựa chọn theo ý định truy cập thay vì dùng theo thói quen.

### 18.1. Resource Server nghiệp vụ nhạy cảm

Đặc điểm:

- Có các HTTP operation đòi scope/permission cụ thể.
- Endpoint mới phải qua security review.
- Có nhiều tenant, dữ liệu cá nhân hoặc thao tác thay đổi trạng thái.

Mẫu khuyến nghị:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/catalog").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.create")
    .requestMatchers(HttpMethod.DELETE, "/api/orders/*")
        .hasAuthority("SCOPE_orders.delete")
    .anyRequest().denyAll()
)
~~~

**Lợi ích:** endpoint/method mới bị từ chối mặc định. **Giới hạn:** phải cập nhật rule khi thêm endpoint hợp lệ, đồng thời kiểm tra quyền dữ liệu ở service. Với API phức tạp, có thể cần nhiều chain hoặc `AuthorizationManager` chuyên biệt.

### 18.2. Khu vực chỉ dành cho người dùng đã đăng nhập

Đặc điểm:

- Tất cả endpoint trong phạm vi được thiết kế chỉ hiển thị dữ liệu **của principal hiện tại**.
- Không có thao tác yêu cầu scope đặc biệt hoặc đã được bảo vệ ở method/domain layer.
- Đội phát triển chấp nhận trách nhiệm review các endpoint mới trong phạm vi này.

Có thể chọn:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
)
~~~

**Rủi ro:** một endpoint nhạy cảm mới sẽ được dùng bởi bất kỳ principal đã xác thực nào nếu không có rule riêng. Vì vậy cần khẳng định rõ đây là chủ đích, không coi nó tương đương default deny.

### 18.3. Endpoint/tài nguyên công khai có chain riêng

Đặc điểm:

- Chỉ cho phép một số URL và method cụ thể không cần token.
- Muốn tách Bearer authentication khỏi khu vực public.
- Vẫn muốn một số security headers/CORS và visibility theo thiết kế.

Có thể dùng:

~~~text
Public SecurityFilterChain:
    securityMatcher("/public/**")
    GET /public/catalog → permitAll
    anyRequest           → denyAll

Bearer API SecurityFilterChain:
    securityMatcher("/api/**")
    GET /api/orders/**   → SCOPE_orders.read
    ...
    anyRequest           → denyAll

Fallback SecurityFilterChain:
    anyRequest           → denyAll
~~~

Việc đặt thứ tự chain phải bảo đảm **public matcher và API matcher không vô tình giao nhau theo cách khó dự đoán**. Chain fallback bảo vệ các đường dẫn không được phân loại, trong khi public chain vẫn chỉ cho phép một bộ URL đã biết.

### 18.4. Vì sao không có catch-all “thần kỳ” cho tất cả?

Một rule cuối duy nhất không thể vừa biểu diễn chính xác role của admin, scope đọc/ghi, tài nguyên public và quyền sở hữu đơn hàng. `anyRequest` là **chính sách mặc định**, không phải bộ máy suy luận quyền tự động. Cần kết hợp:

~~~text
Trusted token validation
     +
HTTP method/path authorization
     +
Method-level authorization nếu cần
     +
Object/tenant ownership policy
     +
Fallback cho route chưa phân loại
~~~

## 19. Một tình huống thay đổi cấu hình qua thời gian

Ngày đầu, API chỉ có hai endpoint:

~~~text
GET /api/orders/{id}   → read
POST /api/orders       → create
~~~

Policy:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.create")
    .anyRequest().denyAll()
)
~~~

Ngày sau, team thêm:

~~~text
DELETE /api/orders/{id}
~~~

### 19.1. Nếu catch-all là `denyAll`

DELETE chưa được khai báo rule sẽ bị từ chối ở HTTP authorization. Developer phải thêm:

~~~java
.requestMatchers(HttpMethod.DELETE, "/api/orders/*")
    .hasAuthority("SCOPE_orders.delete")
~~~

vào **trước** `anyRequest().denyAll()` và bảo đảm controller/service kiểm tra ownership/tenant. Đây là thay đổi có chủ đích, dễ review.

### 19.2. Nếu catch-all là `authenticated`

DELETE mới có thể vượt HTTP authorization với bất kỳ JWT hợp lệ nào, bao gồm token chỉ có scope đọc, **nếu không có rule khác chặn**. Không có gì trong `authenticated()` tự suy ra DELETE cần `orders.delete`.

Vì vậy, khi xây API đa quyền, default deny giúp tránh vô tình nới policy vì thêm controller mà quên security matcher.

### 19.3. Nếu một matcher đọc rộng được thêm sai vị trí

Giả sử trong lúc refactor, developer chuyển sang:

~~~java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.DELETE, "/api/orders/*")
    .hasAuthority("SCOPE_orders.delete")
.anyRequest().denyAll()
~~~

Rule DELETE có thể bị che bởi matcher đầu và chỉ cần read scope. **Catch-all `denyAll` không giúp sửa một matcher rộng đã khớp trước nó.** Do đó cần kiểm tra cả thứ tự matcher cụ thể, không chỉ biết có `anyRequest().denyAll()` cuối cùng.

## 20. Checklist khi review `authorizeHttpRequests`

Khi đọc một cấu hình Spring Security Resource Server, có thể đặt các câu hỏi sau:

| Câu hỏi | Vì sao quan trọng? |
|---|---|
| Security chain nào nhận request trước? | Tránh chain rộng nuốt chain API |
| Có fallback chain bảo vệ request ngoài scope không? | Tránh URL không được bảo vệ khi chẳng chain nào khớp |
| Matcher admin/write có đứng trước matcher rộng không? | Tránh policy mạnh bị matcher yếu che |
| Các rule có xét HTTP method không? | Tránh GET quyền đọc áp cho POST/DELETE |
| `anyRequest` đã được khai báo rõ ở cuối chưa? | Có default policy dễ đọc |
| Default là `denyAll`, `authenticated` hay `permitAll`? | Mỗi lựa chọn có hậu quả khác nhau với endpoint mới |
| Public matcher có cho phép quá nhiều URL/method không? | Tránh mở management/internal endpoints |
| Scope từ JWT/opaque có được ánh xạ đúng authority không? | Tránh 403 hoặc quyền không đúng ý định |
| API đã kiểm tra issuer, audience, token validity chưa? | Phân quyền chỉ có ý nghĩa sau authentication đáng tin |
| CORS preflight có được xử lý đúng không? | Tránh lỗi browser và việc mở OPTIONS quá rộng |
| Có route phụ thuộc ERROR/FORWARD dispatch không? | Tránh bypass/đứt error page do policy dispatcher |
| Có kiểm tra quyền chủ sở hữu/tenant ở service không? | Ngăn lộ dữ liệu giữa người dùng |
| HTTP tests có bao phủ request thành công và request bị từ chối không? | Phát hiện lỗi thứ tự matcher và default policy |
| Có test URL mới/không tồn tại trong rule không? | Xác nhận fallback thật sự được áp |
| Gateway, context path, servlet path đã nhất quán chưa? | Tránh matcher khác với path ứng dụng xử lý |

**Đừng xem các dòng `permitAll()`, `authenticated()`, `hasAuthority(...)` và `denyAll()` như một tập không có thứ tự.** Thứ tự là một phần của thiết kế quyền truy cập; chỉ một matcher bao quát đặt sai vị trí có thể thay đổi policy của rất nhiều endpoint.

## 21. Bài tập tự kiểm tra

### Bài tập 1: matcher nào được dùng?

Cho:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
~~~

**Câu hỏi:** `GET /api/admin/users` dùng rule nào?

**Đáp án:** `/api/** → authenticated()`. Matcher này đứng trước và đã khớp. Rule `hasRole("ADMIN")` ở sau không được xét. Cần đảo vị trí hai matcher.

### Bài tập 2: token hợp lệ nhưng không có scope

Cho:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.anyRequest().denyAll()
~~~

**Câu hỏi:** JWT đúng issuer/audience và còn hạn, nhưng chỉ có `SCOPE_profile`, gọi `GET /api/orders/42`?

**Đáp án:** Token được xác thực thành công, nhưng HTTP authorization từ chối do thiếu `SCOPE_orders.read`. Thông thường response là 403, không phải chuyển xuống `anyRequest`.

### Bài tập 3: endpoint mới

Cho:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.anyRequest().denyAll()
~~~

**Câu hỏi:** Developer thêm `DELETE /api/orders/42` mà quên thêm security rule; kết quả mong đợi?

**Đáp án:** DELETE không match matcher GET và rơi vào `anyRequest().denyAll()` của chain, nên bị từ chối. Chỉ thêm rule DELETE rõ ràng khi đã định nghĩa quyền `orders.delete` và policy nghiệp vụ.

### Bài tập 4: nhiều chain

Cho:

~~~text
Chain A @Order(1):
  securityMatcher("/api/**")
  anyRequest().denyAll()

Không có chain B.
~~~

**Câu hỏi:** `GET /internal/reports` có được Chain A chặn không?

**Đáp án:** Không. Nó không khớp `securityMatcher("/api/**")` nên không đi qua Chain A. Cần xác định một fallback chain hoặc security coverage khác cho request ngoài `/api/**`.

### Bài tập 5: public endpoint nhận Bearer token sai

Cho:

~~~java
.requestMatchers("/public/**").permitAll()
.anyRequest().authenticated()
~~~

và cùng chain bật `oauth2ResourceServer(...jwt(...))`.

**Câu hỏi:** Nếu client gửi JWT sai tới `/public/catalog`, `permitAll()` có bảo đảm response 200 không?

**Đáp án:** Không. Bearer authentication filter có thể phát hiện token invalid và trả lỗi authentication trước khi authorization rule `permitAll` chạy. Nếu cần public chain không xác thực Bearer, hãy thiết kế chain riêng có phạm vi rõ ràng.

### Bài tập 6: POST bị rule GET nuốt?

Cho:

~~~java
.requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders").hasAuthority("SCOPE_orders.create")
.anyRequest().denyAll()
~~~

**Câu hỏi:** Có chắc POST yêu cầu `SCOPE_orders.create` không?

**Đáp án:** Không chắc. Nếu matcher rộng đầu tiên khớp POST path theo semantics matcher đang dùng, request bị áp `SCOPE_orders.read` thay vì rule create. Để tránh lỗi, không dùng matcher không giới hạn HTTP method đứng trước rule ghi có cùng phạm vi path.

### Bài tập 7: thế nào là chính sách default-deny đầy đủ?

**Đáp án:** Không chỉ có `anyRequest().denyAll()` trong một chain. Cần bảo đảm mọi request nhạy cảm được chọn bởi một chain bảo vệ phù hợp, những rule cụ thể có thứ tự đúng, và các request không được phân loại đi tới catch-all deny trong chain/fallback. Tầng service vẫn phải kiểm tra quyền trên dữ liệu.

## 22. Ghi nhớ

Có thể hình dung quá trình phân quyền HTTP Servlet thành hai lần “first match wins”:

~~~text
HTTP REQUEST
   |
   v
FilterChainProxy
   |
   +-- Chọn SecurityFilterChain đầu tiên khớp
   |      (securityMatcher, @Order)
   |
   v
Authentication trong chain đã chọn
   |
   v
authorizeHttpRequests
   |
   +-- Chọn RequestMatcher đầu tiên khớp
   |      (method, path, dispatcher type...)
   |
   +-- Áp AuthorizationManager của matcher đó
   |      permitAll / authenticated /
   |      hasAuthority / hasRole / denyAll
   |
   v
Controller/service nếu được phép
   |
   v
Kiểm tra owner/tenant/quyền nghiệp vụ khi cần
~~~

**Ba nguyên tắc thực hành cần giữ:**

1. **Cụ thể trước, bao quát sau:** admin, write/delete, method và đường dẫn nhạy cảm phải được ưu tiên trước matcher rộng.
2. **Catch-all cuối cùng có chủ đích:** `anyRequest().denyAll()` phù hợp với chính sách deny-by-default; `authenticated()` chỉ phù hợp khi thực sự muốn cho mọi principal đã xác thực vào các URL còn lại; `permitAll()` không nên là fallback vô tình của API bảo vệ.
3. **Bao phủ toàn bộ chain:** `anyRequest` chỉ có hiệu lực trong chain đã được chọn. Với nhiều `SecurityFilterChain`, cần thứ tự `@Order`, `securityMatcher` và fallback chain phù hợp để không để lại đường dẫn ngoài phạm vi bảo vệ.

Thực thi đúng **thứ tự khớp quy tắc** và **quy tắc mặc định cho các request còn lại** giúp một Resource Server không chỉ xác thực access token đúng, mà còn hạn chế việc token hợp lệ bị sử dụng ngoài phạm vi endpoint, method và quyền được thiết kế.

## Tài liệu tham khảo

- [Spring Security — Authorize HTTP Requests (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Java Configuration / Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive Authorization / Authorize Exchanges](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — Spring Security Test](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP — API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
