# Kiểm tra cả đường đi được phép lẫn đường đi phải bị từ chối

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, cấu hình phân quyền HTTP không chỉ nhằm làm cho người dùng có access token hợp lệ gọi được API. Điều quan trọng ngang bằng là **mọi request không được phép phải bị chặn đúng chỗ**: thiếu token, token không hợp lệ, thiếu scope, sai HTTP method, sai URL hoặc không có quyền trên bản ghi cụ thể.

Nếu chỉ thử `GET /api/orders/42` với một token đủ quyền rồi thấy HTTP 200, ta mới biết **một trường hợp được phép hoạt động**. Ta chưa biết:

- Người không có token có truy cập được endpoint không?
- Token chỉ có quyền xem có vô tình gọi được endpoint xóa/hủy đơn không?
- `POST` đến URL chỉ được phép `GET` có bị từ chối không?
- Một endpoint mới hoặc một URL không khớp rule có được bảo vệ không?
- Một token từ issuer khác, sai audience hoặc chữ ký sai có bị từ chối **trước** khi tạo principal không?
- Người có scope đọc có bị chặn khi cố đọc đơn hàng thuộc tenant khác không?

**Bài học này tập trung vào kiểm thử hai chiều của HTTP authorization: đường đi phải cho phép (positive paths) và đường đi phải từ chối (negative paths)**, trong bối cảnh một API Spring Security nhận OAuth 2.0 Bearer access token. Mục tiêu là chứng minh chính sách áp dụng đúng với **HTTP method + URL + danh tính/token + authority + tài nguyên nghiệp vụ**, thay vì chỉ chứng minh một “happy path”.

> **Nguyên tắc:** Một rule bảo mật chỉ được kiểm chứng đủ khi có cả bằng chứng **người đủ quyền được vào** và **người thiếu quyền hoặc gửi request sai đường bị chặn**. Với Resource Server, phải tách kiểm thử **authentication (401)**, **authorization (403/404 theo chính sách)** và **business/data policy**. Mọi trường hợp ngoài hợp đồng cần mặc định bị từ chối.

## 1. Phân biệt “đường đi” theo nhiều chiều

Ở đây, “đường đi” không chỉ có nghĩa là URL. Nó là **đường xử lý request đi qua security filter chain, authorization và tầng nghiệp vụ**.

Giả sử một hệ thống bán hàng gồm:

- **Shop Web:** OAuth2 Client xin access token cho người dùng hoặc dịch vụ.
- **Identity Server:** Authorization Server phát hành JWT access token đã ký.
- **Orders API:** Spring Security Resource Server xác minh token và bảo vệ endpoint.
- **Order Service/Database:** quyết định quyền trên các đơn hàng, tenant và trạng thái thực tế.

Một request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
~~~

Có ít nhất bốn lớp cần xem xét:

| Lớp | Câu hỏi | Ví dụ trường hợp nên bị từ chối |
| --- | --- | --- |
| **Authentication** | Caller đã cung cấp credential được xác minh chưa? | Không token, chữ ký JWT sai, issuer/audience sai, token hết hạn |
| **HTTP authorization** | Method + URL có được caller mang authority này truy cập không? | Có `orders.read` nhưng gọi `POST /api/orders` |
| **Method authorization** | Phương thức nghiệp vụ có yêu cầu thêm permission/role không? | Token có scope nhưng thiếu permission hủy |
| **Resource/data policy** | Caller được truy cập **đối tượng cụ thể** này không? | Có quyền đọc đơn nhưng đơn 42 thuộc tenant khác |

Một response 200 ở lớp HTTP chưa khẳng định data policy đúng. Một response 403 cũng chưa chứng minh JWT đã bị từ chối vì sai chữ ký. Cần biết **request bị chặn ở lớp nào và vì sao**.

~~~mermaid
flowchart TD
    A["HTTP request: method + path + Bearer token"]
    B["SecurityFilterChain được chọn"]
    C["JwtDecoder: verify signature và validate claims"]
    D{"Authentication hợp lệ?"}
    E["401 / lỗi xác thực"]
    F["authorizeHttpRequests: method + URL + authorities"]
    G{"Rule cho phép?"}
    H["403 / deny theo policy"]
    I["Method security và resource policy"]
    J{"Được quyền trên resource?"}
    K["Trả kết quả nghiệp vụ"]

    A --> B --> C --> D
    D -->|Không| E
    D -->|Có| F --> G
    G -->|Không| H
    G -->|Có| I --> J
    J -->|Không| H
    J -->|Có| K
~~~

Sơ đồ là mô hình khái niệm. Với endpoint public, có thể không yêu cầu authentication; các request vô danh vẫn đi qua lựa chọn filter chain và rule `permitAll()`. Phản hồi cụ thể tùy cách cấu hình Spring Security, entry point, access denied handler và policy nghiệp vụ.

## 2. Định nghĩa hợp đồng HTTP trước khi viết test

Một API có thể thống nhất bảng quyền như sau:

| HTTP method | URL | Ai được phép | Quy tắc thêm |
| --- | --- | --- | --- |
| `GET` | `/api/public/catalog` | Public, không cần Bearer token | Chỉ dữ liệu catalog công khai |
| `GET` | `/api/orders` | Token có `orders.read` | Chỉ trả đơn mà caller được phép xem |
| `GET` | `/api/orders/{id}` | Token có `orders.read` | Kiểm tra owner/tenant của đơn |
| `POST` | `/api/orders` | Token có `orders.write` | Kiểm tra quyền tạo trong tenant |
| `POST` | `/api/orders/{id}/cancel` | Token có `orders.cancel` | Kiểm tra quyền hủy, owner và trạng thái |
| Các method/URL khác dưới `/api/**` | Không có rule được cấp | **Deny** | Chỉ mở khi có thay đổi hợp đồng có chủ đích |
| Đường dẫn ngoài `/api/**` | Phụ thuộc chain khác | **Deny** trong ví dụ | Không để không có chain bảo vệ |

Các scope `orders.read`, `orders.write` và `orders.cancel` là **tên theo hợp đồng minh họa**, không phải quyền chuẩn do OAuth 2.0 định nghĩa. Đội Client, Authorization Server và Orders API phải thống nhất ý nghĩa scope, audience và quy tắc cấp token.

Một chính sách được kiểm tra tốt cần nêu đủ:

1. **Đường đi được phép:** endpoint cụ thể, method cụ thể, authentication/authority cụ thể.
2. **Đường đi bị từ chối:** token vắng/sai, quyền thấp hơn, URL gần giống, method khác và tài nguyên không thuộc quyền.
3. **Default:** request không khớp rule có được từ chối không?
4. **Biên giữa các chain:** đường ngoài `securityMatcher` có được một chain khác bảo vệ không?
5. **Mã lỗi dự kiến:** lỗi xác thực hay lỗi quyền, hoặc 404 do không muốn lộ tài nguyên?

## 3. 401 và 403 phản ánh hai loại thất bại khác nhau

Hai response thường thấy:

| Mã | Ý nghĩa điển hình ở Bearer Resource Server | Ví dụ |
| --- | --- | --- |
| **401 Unauthorized** | Chưa có authentication hợp lệ cho resource được bảo vệ | Không Bearer token, JWT sai chữ ký, hết hạn, sai issuer/audience |
| **403 Forbidden** | Đã xác thực nhưng không có quyền theo rule | Token hợp lệ có `orders.read` nhưng endpoint yêu cầu `orders.write` |
| **404 Not Found** | Tài nguyên không tồn tại, hoặc API chủ động che giấu sự tồn tại theo policy | Đơn thuộc tenant khác, chính sách không tiết lộ ID |

Phân biệt này giúp test phát hiện sai lớp lỗi:

- Nếu JWT chữ ký sai lại được xử lý tới controller, **authentication đã bị vượt qua**.
- Nếu token hợp lệ nhưng thiếu scope mà API trả 200, **HTTP authorization đang thiếu hoặc sai rule**.
- Nếu scope đúng nhưng lấy được đơn tenant khác, **data policy có lỗ hổng**.

**Không nên mặc định mọi negative test phải trả 403.** Request vô danh đến endpoint bảo vệ thường gặp 401; người đã xác thực nhưng thiếu quyền thường gặp 403. Với đường chưa có controller hoặc chain đặc biệt, có thể gặp 404 hoặc một mã khác. Test phải kiểm tra kết quả theo **hợp đồng thực tế**, đồng thời khẳng định không có hành động được bảo vệ nào xảy ra.

Đặc biệt, `permitAll()` có nghĩa **không yêu cầu quyền để truy cập endpoint đó**, không phải “bỏ qua mọi filter”. Nếu Client gửi **Bearer token không hợp lệ** tới endpoint công khai, filter xác thực có thể từ chối request trước khi đến rule `permitAll()`. Nên test trường hợp public **không gửi Bearer token**, thay vì tự suy rằng token giả cũng phải trả 200.

## 4. Cấu hình HTTP authorization mẫu theo hướng deny-by-default

Ví dụ dùng **Spring Boot 3 / Spring Security 6** và Java 17+, với Orders API nhận OAuth2 JWT access token.

### 4.1. Dependency và issuer

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}

app:
  security:
    expected-audience: ${OAUTH_API_AUDIENCE}
~~~

JWT Resource Server phải xác minh **chữ ký, issuer, thời hạn, audience và loại token** theo hợp đồng. Chỉ vì cấu hình `issuer-uri` và `jwk-set-uri` không có nghĩa mọi phiên bản tự kiểm tra audience theo ý ứng dụng; cần thiết lập validator audience rõ ràng khi cần. Phần kiểm thử JWT thật sẽ được phân biệt với `MockMvc.jwt()` ở mục 8.

### 4.2. SecurityFilterChain phân quyền theo cả method và path

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain ordersApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/catalog")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.GET, "/api/orders/{id}")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(
                    HttpMethod.POST, "/api/orders/{id}/cancel")
                    .hasAuthority("SCOPE_orders.cancel")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll())
            .build();
    }
}
~~~

Cấu hình này minh họa:

- **Chain thứ nhất** chỉ xử lý `/api/**`, ưu tiên theo `@Order(1)`.
- Trong API chain, **đường public được mở rất hẹp**: chỉ `GET /api/public/catalog`.
- Từng thao tác đọc, tạo và hủy đơn có **method/path và scope** riêng.
- `anyRequest().denyAll()` trong API chain chặn tất cả API request khác, kể cả URL mới chưa có rule.
- **Fallback chain** chặn đường nằm ngoài `/api/**` trong ví dụ, để một request không bị bỏ qua Spring Security chỉ vì không khớp chain đầu tiên.

Đây là thiết kế minh họa cho REST API **dùng Bearer token, không dùng cookie/session để xác thực**; vì thế API chain tắt CSRF và dùng stateless session. Nếu cùng ứng dụng phục vụ giao diện web dùng cookie hoặc các endpoint đặc biệt, phải thiết kế CSRF và filter chain phù hợp, không copy việc tắt CSRF sang mọi chain.

### 4.3. Tại sao `securityMatcher` và `requestMatchers` khác nhau?

**`securityMatcher("/api/**")`** xác định **toàn bộ SecurityFilterChain có được áp dụng cho request không**.

**`requestMatchers(...)`** trong `authorizeHttpRequests` xác định **rule phân quyền trong chain đã được chọn**.

~~~text
Incoming request
   |
   +-- Chain @Order(1), securityMatcher("/api/**")?
   |      |
   |      +-- Có -> áp dụng rule GET/POST/denyAll của API chain
   |
   +-- Nếu chưa chain nào match -> chain @Order(2)
                         |
                         +-- denyAll
~~~

Nếu chỉ khai báo chain đầu và không có chain nào bảo vệ `/admin/**`, request ngoài `/api/**` có thể **không đi qua chain mà ta tưởng đang bảo vệ mọi đường**. Do đó, khi có nhiều chain, phải kiểm thử **đường trong chain**, **đường ngoài chain** và **đường chồng lấp**.

### 4.4. Thứ tự rule trong `authorizeHttpRequests`

Các matcher thường được xét theo thứ tự khai báo; một rule quá rộng đứng trước có thể che mất rule đặc thù:

~~~java
// Ví dụ SAI: rule rộng có thể bắt trước rule hẹp.
.requestMatchers("/api/**").permitAll()
.requestMatchers(HttpMethod.POST, "/api/orders/{id}/cancel")
    .hasAuthority("SCOPE_orders.cancel")
~~~

Khi matcher đầu đã cho phép mọi request, rule sau có thể không còn được áp dụng. Vì thế **đặt rule hẹp trước, rule rộng sau, kết thúc bằng denyAll** là một nguyên tắc dễ kiểm soát.

Không giả định chỉ cần code có chuỗi `hasAuthority("SCOPE_orders.cancel")` là endpoint hủy đơn chắc chắn được bảo vệ. Cần **negative test** chứng minh caller thiếu scope thật sự bị từ chối.

## 5. Ma trận positive và negative cho HTTP routes

Sau khi có hợp đồng endpoint, chuyển nó thành test matrix. Đừng chỉ chọn một token “admin” có tất cả scopes để chạy mọi endpoint, vì nó không phát hiện được rule quá rộng.

| # | Method và path | Principal / token | Kỳ vọng |
| --- | --- | --- | --- |
| P1 | `GET /api/public/catalog` | Không Bearer token | **200** |
| P2 | `GET /api/orders` | JWT hợp lệ, `orders.read` | Qua lớp HTTP, trả dữ liệu theo policy |
| P3 | `GET /api/orders/42` | JWT hợp lệ, `orders.read` | Qua lớp HTTP, tiếp tục kiểm tra owner/tenant |
| P4 | `POST /api/orders` | JWT hợp lệ, `orders.write` | Qua lớp HTTP, tiếp tục policy tạo đơn |
| P5 | `POST /api/orders/42/cancel` | JWT hợp lệ, `orders.cancel` | Qua lớp HTTP, tiếp tục policy hủy |
| N1 | `GET /api/orders/42` | Không token | **401** điển hình |
| N2 | `GET /api/orders/42` | JWT hợp lệ, chỉ `orders.write` | **403** |
| N3 | `POST /api/orders` | JWT hợp lệ, chỉ `orders.read` | **403** |
| N4 | `POST /api/orders/42/cancel` | JWT hợp lệ, chỉ `orders.write` | **403** |
| N5 | `POST /api/orders/42/refund` | JWT hợp lệ, nhiều scopes | **403** vì không có rule |
| N6 | `GET /api/orders/42/notes` | JWT hợp lệ, `orders.read` | **403** vì không có rule cho subpath |
| N7 | `POST /api/public/catalog` | JWT hợp lệ | **403** vì chỉ GET public |
| N8 | `GET /internal/secrets` | JWT hợp lệ | Bị chặn bởi fallback chain |
| N9 | `GET /api/orders/42` | JWT sai chữ ký | Bị từ chối ở authentication |
| N10 | `GET /api/orders/42` | JWT đúng chữ ký nhưng sai audience | Bị từ chối ở authentication |
| N11 | `GET /api/orders/42` | JWT đủ `orders.read` nhưng sai tenant | Bị từ chối ở policy dữ liệu |

**Kỳ vọng của P2–P5 không tự động là 200 ở ứng dụng thật**: nếu resource không tồn tại, payload không hợp lệ hoặc policy nghiệp vụ không cho phép, API có thể trả lỗi phù hợp. Trong unit test HTTP-only với controller giả đơn giản, ta có thể dùng 200 để chứng minh rule cho phép đi qua. Khi test đầy đủ hệ thống, phải kiểm tra chính xác kết quả nghiệp vụ mong muốn.

### 5.1. Vì sao cần test một scope không liên quan?

Nếu chỉ thử token không có scope nào, một lỗi mapping nhẹ có thể vẫn từ chối và test pass. Token có **`orders.write` nhưng thiếu `orders.read`** mạnh hơn, vì nó chứng minh permission không bị xem là quyền tổng quát.

Tương tự, token `orders.cancel` **không tự có** `orders.write` hoặc `orders.read`, trừ khi hợp đồng và policy có quy tắc bao hàm rõ ràng. Không giả định mọi scope có quan hệ kế thừa.

### 5.2. Vì sao cần test URL gần giống?

Một matcher kiểu `/api/orders/**` có thể bao phủ nhiều subpath hơn tác giả mong muốn. Nếu sau này thêm `/api/orders/{id}/refund` hoặc `/api/orders/{id}/export` mà rule GET/POST quá rộng, endpoint mới có thể nhận quyền cũ không phù hợp.

Viết test từ chối cho **subpath chưa khai báo** giúp phát hiện thay đổi “mở rộng âm thầm”. Có thể dùng **negative-space testing**: chọn những request nằm **ngoài tập được phép** nhưng nhìn rất giống request hợp lệ.

## 6. MockMvc: test chính sách HTTP một cách có kiểm soát

`spring-security-test` cung cấp `SecurityMockMvcRequestPostProcessors.jwt()` để gắn một `JwtAuthenticationToken` giả lập vào request kiểm thử. Cách này rất hữu ích khi mục tiêu là **rule method/path và authorities**, vì không cần dựng Authorization Server, ký JWT hay tải JWKS trong mỗi test.

**Giới hạn quan trọng:** `jwt()` **không chứng minh chữ ký, issuer, audience hoặc `JwtDecoder` thật hoạt động**. Nó thiết lập trạng thái authentication cho test. Vì vậy dùng nó để test **HTTP authorization**; dùng integration test với **Bearer JWT ký thật** để kiểm tra biên authentication.

### 6.1. Một controller thử nghiệm tối giản

Để các test không phụ thuộc database, giả sử có controller test chỉ trả text:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
class DemoOrdersController {

    @GetMapping("/public/catalog")
    String catalog() {
        return "public-catalog";
    }

    @GetMapping("/orders")
    String listOrders() {
        return "orders";
    }

    @GetMapping("/orders/{id}")
    String readOrder(@PathVariable String id) {
        return "order:" + id;
    }

    @PostMapping("/orders")
    String createOrder() {
        return "created";
    }

    @PostMapping("/orders/{id}/cancel")
    String cancelOrder(@PathVariable String id) {
        return "cancelled:" + id;
    }
}
~~~

Đây **không phải controller production**: nó cố ý không có kiểm tra owner, tenant, trạng thái hoặc persistence. Nó chỉ cho test thấy request đã **qua được lớp HTTP authorization**. Tầng data policy cần kiểm thử riêng.

### 6.2. Test được phép và bị từ chối

Ví dụ với **Spring Boot 3 / Spring Security 6**, JUnit Jupiter và MockMvc:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers = DemoOrdersController.class)
@Import({ApiSecurityConfig.class, HttpAuthorizationTest.TestDecoder.class})
class HttpAuthorizationTest {

    @Autowired
    MockMvc mvc;

    // Chỉ là decoder placeholder cho test rules bằng jwt() giả lập.
    // Không dùng nó trong test xác minh JWT ký thật.
    @TestConfiguration
    static class TestDecoder {
        @Bean
        JwtDecoder jwtDecoder() {
            return token -> {
                throw new JwtException("Real JWT validation is tested separately");
            };
        }
    }

    @Test
    void publicGetIsAllowedWithoutBearerToken() throws Exception {
        mvc.perform(get("/api/public/catalog"))
            .andExpect(status().isOk());
    }

    @Test
    void readScopeMayUseGetOrder() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void writeScopeMayCreateOrder() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isOk());
    }

    @Test
    void cancelScopeMayCancelOrder() throws Exception {
        mvc.perform(post("/api/orders/42/cancel")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.cancel"))))
            .andExpect(status().isOk());
    }

    @Test
    void protectedGetWithoutTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unrelatedScopeCannotReadOrder() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void readScopeCannotCreateOrder() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeScopeCannotCancelOrder() throws Exception {
        mvc.perform(post("/api/orders/42/cancel")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void unlistedActionIsDeniedEvenWithValidAuthorities() throws Exception {
        mvc.perform(post("/api/orders/42/refund")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"),
                    new SimpleGrantedAuthority("SCOPE_orders.write"),
                    new SimpleGrantedAuthority("SCOPE_orders.cancel"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void publicPathIsNotAutomaticallyPublicForPost() throws Exception {
        mvc.perform(post("/api/public/catalog")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownSubpathIsDenied() throws Exception {
        mvc.perform(get("/api/orders/42/notes")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void pathOutsideApiIsNotUnprotected() throws Exception {
        mvc.perform(get("/internal/secrets")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().is4xxClientError());
    }
}
~~~

Ví dụ minh họa một bộ test cho các **method/URL đã quy định**. `DemoOrdersController` và `ApiSecurityConfig` được định nghĩa ở những đoạn trước. `TestDecoder` trả lỗi với JWT dạng chuỗi thật để test không vô tình trộn với bài kiểm tra chữ ký; các request có `jwt()` được cài sẵn authentication do công cụ kiểm thử cung cấp. Với test mà `jwt()` tạo sẵn authorities, **cấu hình chuyển claim scope thành authority chưa được kiểm thử**.

Đường `/internal/secrets` đi qua fallback chain; mã cụ thể có thể là 403 theo cấu hình ví dụ. Assertion ở đây kiểm tra **không mở đường truy cập**, nhưng với một hệ thống có hợp đồng mã lỗi rõ, nên kiểm tra đúng mã và xác nhận không có side effect.

### 6.3. Vì sao test cả `GET` lẫn `POST` trên URL giống nhau?

`GET /api/public/catalog` được phép không kéo theo `POST /api/public/catalog` được phép. HTTP matcher nên kết hợp **method + path**. Nếu dùng một rule:

~~~java
.requestMatchers("/api/public/catalog").permitAll()
~~~

không giới hạn method, nó có thể mở nhiều method hơn dự kiến. Negative test `POST` giúp phát hiện điều đó.

Tương tự, `POST /api/orders/{id}/cancel` không đồng nghĩa `GET` hoặc `DELETE` trên URL này được phép. Tạo test riêng cho method bất ngờ:

~~~java
@Test
void getCancelEndpointIsDenied() throws Exception {
    mvc.perform(get("/api/orders/42/cancel")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.cancel"))))
        .andExpect(status().isForbidden());
}
~~~

Đối với một API production, Spring MVC cũng có thể tự xử lý `HEAD`, `OPTIONS` hoặc trả `405 Method Not Allowed` khi không có handler tương ứng. Cần xác định hợp đồng mong muốn và kiểm thử behavior thực tế, không mặc định mọi method không mong muốn luôn trả đúng một mã 403.

## 7. Kiểm thử không chỉ status mà cả việc controller có được gọi không

Một negative test mạnh hơn kiểm tra response:

~~~text
Không đủ quyền -> 403
VÀ service.createOrder(...) không được gọi
VÀ không có bản ghi nào được tạo/cập nhật
~~~

Tại lớp web có thể dùng `@MockitoBean` của Spring Framework 6.2+/Spring Boot phù hợp hoặc `@MockBean` trong các phiên bản Spring Boot 3 cũ để mock service, rồi xác nhận:

~~~java
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

// Sau một request bị chặn ở filter chain:
verify(orderService, never()).createOrder(
        org.mockito.ArgumentMatchers.any());
~~~

Đây là **đoạn minh họa đặt trong test có mock orderService**, không phải test hoàn chỉnh độc lập. Nó nhắc một nguyên tắc quan trọng: kết quả “forbidden” chỉ đáng tin nếu request thật sự không tạo ra side effect nghiệp vụ trước khi bị từ chối.

Trong hệ thống có database, queue hoặc event, integration test nên kiểm tra không có write/event được thực hiện nếu authorization thất bại. Nếu lỗi HTTP xảy ra **sau khi** nghiệp vụ đã chạy, status 403 cuối cùng không đủ bảo vệ dữ liệu.

## 8. `jwt()` không tương đương JWT ký thật: kiểm thử biên xác thực riêng

Trong test ở mục 6:

~~~java
.with(jwt().authorities(
    new SimpleGrantedAuthority("SCOPE_orders.read")))
~~~

công cụ kiểm thử **cấp một authentication đã có authorities** cho request. Nó không dùng private key test để ký JWT, không gọi JWKS, không áp dụng mọi validator issuer/audience/time như decoder production.

Vì vậy test này là một bằng chứng tốt cho:

- Method/path có yêu cầu authority đúng hay không.
- Endpoint bị chặn khi **authentication giả lập** thiếu authority.
- Thứ tự `requestMatchers`, `denyAll` và lựa chọn filter chain.

Nhưng **không chứng minh**:

- JWT sai chữ ký bị từ chối.
- Token issuer lạ bị từ chối.
- Token có `aud` của API khác bị từ chối.
- JWT hết hạn bị từ chối.
- Mapping từ claim `scope` hoặc nested roles thành `GrantedAuthority` hoạt động đúng.

### 8.1. Ma trận kiểm thử JWT thật

Khi kiểm thử ở lớp JWT decoder + SecurityFilterChain, hãy gửi token **được ký thật bằng khóa test**, dùng một JWKS mock đáng tin:

| Token | JWT verification | HTTP authorization | Kết quả kỳ vọng |
| --- | --- | --- | --- |
| Ký đúng, issuer/audience/time đúng, scope `orders.read` | Thành công | `GET /api/orders/42` được phép theo scope | Qua security layer |
| Chữ ký bị thay đổi | Thất bại | Chưa được xét quyền | Từ chối, thông thường 401 |
| Ký bằng private key không nằm trong JWKS tin cậy | Thất bại | Chưa được xét quyền | Từ chối |
| Đúng chữ ký, `iss` khác issuer tin cậy | Thất bại validation | Chưa được xét quyền | Từ chối |
| Đúng chữ ký, `aud = billing-api` | Thất bại validation | Chưa được xét quyền | Từ chối |
| Đúng chữ ký nhưng `exp` đã qua | Thất bại validation | Chưa được xét quyền | Từ chối |
| JWT hợp lệ, chỉ `orders.write` | Thành công | `GET` yêu cầu `orders.read` | 403 |
| JWT hợp lệ, `orders.read` | Thành công | `POST /api/orders` yêu cầu `orders.write` | 403 |
| JWT hợp lệ, đủ scope nhưng sai owner | Thành công | HTTP rule cho qua | Data policy từ chối |

Một test signed JWT nên có các thành phần:

~~~text
Test-only RSA/EC signing key
  |
  +-- Private key: chỉ trong fixture để ký JWT
  +-- Public key: công bố qua mock JWKS

Mock Authorization Server/JWKS
  |
  +-- issuer / jwks_uri tin cậy cho test

Spring Security Resource Server
  |
  +-- JwtDecoder thật
  +-- issuer/audience/time validators
  +-- JwtAuthenticationConverter thật
  +-- SecurityFilterChain thật

MockMvc hoặc HTTP test client
  |
  +-- Authorization: Bearer <signed-JWT>
~~~

Đừng dùng private key production làm fixture và đừng gửi access token thật lên các website decode token. Có thể dùng **Nimbus JOSE/JWT**, MockWebServer hoặc WireMock để ký token và công bố public JWK trong test. Token test có `iss`, `aud` và `scope` phù hợp; một biến thể sửa chữ ký hoặc claims để xác nhận từ chối.

### 8.2. Test signed JWT phải đi qua filter chain thực

Pseudocode của một integration test:

~~~java
// Pseudocode: signedJwt(...) ký bằng khóa test được JWKS mock công bố.
String goodToken = signedJwt(
        "trusted-test-issuer",
        "orders-api",
        "orders.read");

mockMvc.perform(get("/api/orders/42")
        .header("Authorization", "Bearer " + goodToken))
    .andExpect(status().isOk());

String wrongAudience = signedJwt(
        "trusted-test-issuer",
        "billing-api",
        "orders.read");

mockMvc.perform(get("/api/orders/42")
        .header("Authorization", "Bearer " + wrongAudience))
    .andExpect(status().isUnauthorized());
~~~

Đây là **pseudocode về kịch bản**, cần helper ký JWT, JWKS test server, decoder và controller thực tế của dự án. Khác biệt cốt lõi với `.with(jwt())` là **request chứa nguyên chuỗi Bearer JWT** để filter xác thực và decoder thực sự xử lý.

### 8.3. Kiểm tra converter bằng test riêng

Nếu issuer đặt scope ở claim `scp` hoặc roles trong `realm_access.roles`, có thể test:

1. `JwtAuthenticationConverter` có chuyển claim theo hợp đồng thành `GrantedAuthority` chính xác không?
2. Scope có prefix `SCOPE_` không? Role có prefix `ROLE_` không?
3. Claim lạ hoặc role của Resource Server khác có bị bỏ qua không?
4. Sau khi converter được gắn vào chain, HTTP rule có nhận đúng authorities không?

**Không nên viết test HTTP với `jwt().authorities(...)` rồi kết luận converter production chắc chắn đúng**, bởi vì chính test đã gắn trực tiếp quyền thay cho converter.

## 9. Kiểm thử chính xác thứ tự và mức độ rộng của matcher

### 9.1. Thứ tự rule có thể thay đổi kết quả

Ví dụ:

~~~java
// Nguy hiểm: rule rộng đặt trước.
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders/{id}/cancel")
    .hasAuthority("SCOPE_orders.cancel")
~~~

Tùy matcher, rule đầu có thể bắt cả request hủy và cho người chỉ có `orders.read` đi qua. Negative test cần có:

~~~text
POST /api/orders/42/cancel + only SCOPE_orders.read
=> MUST DENY
~~~

Trong ví dụ chuẩn ở mục 4, từng method/path được khai báo cụ thể nên tránh được kiểu chồng lấp đó. Nếu phải dùng wildcard, hãy viết test cho **mọi thao tác nhạy cảm nằm dưới wildcard**.

### 9.2. Kiểm thử URL gần giống và cách normalize path

Các request đáng kiểm tra:

~~~text
GET /api/orders/42
GET /api/orders/42/
GET /api/orders/42/notes
GET /api/orders/42/export
GET /api/orders/42%2Fnotes
GET /api/orders//42
GET /API/orders/42
GET /api/orders/42;param=value
~~~

Không phải mọi request trong ví dụ được Spring Security hoặc servlet container xử lý như nhau. Một số bị **HTTP firewall** từ chối ngay, một số bị normalize/route khác theo Spring MVC, proxy hoặc cài đặt path matching, và một số không có handler. Kiểm thử phải dựa trên cấu hình hạ tầng thật để xác nhận **không có đường vòng qua policy**, thay vì đoán mã HTTP cố định.

Những vấn đề nên chú ý:

- **Trailing slash** có được xem như cùng route hay không?
- **Encoded slash** và semicolon content có bị proxy/server/firewall xử lý khác nhau không?
- **Case sensitivity** của URL có thống nhất giữa gateway, Security và MVC không?
- **Context path/servlet path** có làm matcher khác đường request mà controller thấy không?
- Gateway có rewrite `/api/v1/orders` thành `/api/orders`, trong khi security rule đang áp dụng ở lớp nào?

Một thiết kế tốt đặt rule theo **đường thực tế mà SecurityFilterChain nhận được** và kiểm thử ở ranh giới thực tế đó.

### 9.3. Method không mong muốn

Nếu chỉ hỗ trợ `GET /api/orders/{id}`, hãy xem xét:

~~~text
POST /api/orders/42
PUT /api/orders/42
PATCH /api/orders/42
DELETE /api/orders/42
HEAD /api/orders/42
OPTIONS /api/orders/42
~~~

Không áp dụng một kỳ vọng chung cho mọi method. Ví dụ `OPTIONS` có thể là **CORS preflight** từ browser, được xử lý theo chính sách CORS, còn `HEAD` có thể liên quan hành vi Spring MVC của GET mapping. Điều cần chứng minh là **một method không được cấp quyền không thực hiện thao tác dữ liệu được bảo vệ**.

## 10. Multiple SecurityFilterChain: test vùng được bảo vệ và vùng bỏ sót

Một ứng dụng có thể có các chain:

~~~text
@Order(1): /api/**   -> Bearer JWT, scope rules
@Order(2): /admin/** -> web login, CSRF, ROLE_ADMIN
@Order(3): **        -> denyAll
~~~

Việc phân nhiều chain thường có lý do chính đáng, nhưng cần test:

| Đường đi | Chain mong đợi | Negative test quan trọng |
| --- | --- | --- |
| `/api/orders/42` | API JWT | Thiếu token hoặc scope phải bị chặn |
| `/api/public/catalog` | API JWT | Anonymous GET được; POST không tự public |
| `/admin/reports` | Admin chain | JWT API không tự thay thế session/admin role |
| `/internal/jobs` | Chain phù hợp hoặc fallback | Không bị bỏ qua tất cả chain |
| `/actuator/**` | Theo policy quản trị riêng | Không vô tình public endpoints nhạy cảm |

Khi nhiều chain cùng có khả năng match, **thứ tự @Order** quyết định chain được chọn trước. Một matcher `/**` đặt quá sớm có thể che khuất chain JWT. Ngược lại, một chain chỉ match `/api/**` nhưng không có fallback có thể bỏ sót đường quản trị không nằm trong API.

**Không chỉ test rule trong một chain; hãy test cả “ranh giới” giữa các chain.** Nếu hệ thống có management port/Actuator ngoài application port, việc bảo vệ endpoints đó có thể nằm trong cấu hình riêng và cần bài test tương ứng.

## 11. Positive/negative phải xét cả authority và identity

Một người có `orders.read` không đương nhiên được xem mọi đơn hàng. Với Resource Server, **JWT xác thực danh tính và scope**, còn dữ liệu có thể áp đặt owner/tenant/nhóm được giao.

Ví dụ token đã xác minh:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-A",
  "exp": 1893459600
}
~~~

Các case:

| Case | Đơn hàng | Claim và scope | Kỳ vọng |
| --- | --- | --- | --- |
| D1 — owner hợp lệ | Order 42: owner `user-842`, tenant A | `orders.read`, subject `user-842` | Cho xem nếu policy đầy đủ phù hợp |
| D2 — sai owner | Order 43: owner `user-999`, tenant A | `orders.read`, subject `user-842` | Từ chối nếu chỉ được xem đơn của mình |
| D3 — sai tenant | Order 44: tenant B | `orders.read`, tenant A | Từ chối |
| D4 — role hỗ trợ đúng tenant | Order 44: tenant A | Role/permission hỗ trợ hợp lệ | Cho qua khi đúng assignment |
| D5 — service token không phải người dùng | Order 42: owner `user-842` | `client_credentials` với `sub` dịch vụ | Không tự áp dụng quyền user |

Một cách tổ chức:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') and " +
    "@orderAccess.canRead(authentication, #id)")
public OrderDto getOrder(String id) {
    return orders.findDtoById(id)
            .orElseThrow(OrderNotFoundException::new);
}
~~~

`orderAccess` và `orders` là thành phần nghiệp vụ minh họa. `canRead(...)` cần sử dụng danh tính/tenant **đã xác minh** và dữ liệu bản ghi server-side, không chỉ so sánh URL parameter với header do Client đặt. `@PreAuthorize` cần bật `@EnableMethodSecurity` và được thực thi qua Spring proxy theo cấu hình phù hợp.

Negative test ở đây nên kiểm tra **same scope, different resource ownership**. Nó phát hiện kiểu lỗ hổng IDOR/BOLA (insecure direct object reference / broken object level authorization), vốn không thể được phát hiện chỉ bằng test `hasAuthority("SCOPE_orders.read")`.

## 12. Test các biến thể về principal và role

Không phải mọi access token đại diện cho người dùng cuối. Trong `client_credentials`, token có thể đại diện một dịch vụ; trong hệ thống multi-tenant, cùng một role có thể có hiệu lực trong tenant A nhưng không trong tenant B.

Nên thiết kế thêm các trường hợp:

- Token user có scope đọc nhưng không có role/permission nghiệp vụ bắt buộc → **deny**.
- Token user đủ scope và permission nhưng không thuộc tenant của đối tượng → **deny**.
- Token service có scope nội bộ riêng, gọi đúng endpoint dịch vụ → **allow** nếu chính sách service cho phép.
- Token service gửi đến endpoint chỉ dành cho người dùng → **deny**.
- Token từ issuer khác với cùng `sub` và `roles` → **deny** nếu không thuộc issuer tin cậy.
- Token có role của resource khác, ví dụ `billing_admin`, gọi Orders API → **không cấp quyền Orders**.

Nếu Resource Server dùng `JwtAuthenticationConverter` tùy chỉnh, cần test mapping role/permission riêng: `hasRole("ORDER_SUPPORT")` thường đối chiếu `ROLE_ORDER_SUPPORT`; `hasAuthority("SCOPE_orders.read")` đối chiếu authority có prefix `SCOPE_`. Một chữ sai hoặc thiếu prefix có thể khiến tất cả request hợp lệ bị chặn, hoặc tệ hơn, rule không thực sự được áp dụng nơi cần.

## 13. Kiểm thử CORS và CSRF mà không vô tình mở authorization

### 13.1. CORS preflight khác request API thực

Browser có thể gửi:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://shop.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

CORS preflight không mang ý nghĩa “người dùng đã được phép tạo đơn”. Nó hỏi server có cho phép browser gửi request cross-origin hay không. Nếu hệ thống hỗ trợ CORS, nên cấu hình `http.cors(...)` cùng một `CorsConfigurationSource` phù hợp và test:

1. Origin được phép + preflight hợp lệ → phản hồi CORS đúng hợp đồng.
2. Origin không được phép → không cấp quyền cross-origin.
3. Request **POST thật** sau preflight vẫn cần Bearer token và `orders.write`.

**CORS không thay thế authentication/authorization.** Một API có CORS mở đúng cấu hình vẫn phải từ chối Client không có scope. Đừng xử lý vấn đề preflight bằng cách `permitAll("/api/**")`.

### 13.2. CSRF phụ thuộc cơ chế credential

Ví dụ `csrf(AbstractHttpConfigurer::disable)` ở mục 4 phù hợp với giả định **REST API chỉ dùng Bearer token trong Authorization header**, không có authentication dựa trên session cookie. Nếu cùng ứng dụng có login web bằng cookie, cần chính sách CSRF riêng cho luồng đó.

Negative test về HTTP method và quyền vẫn cần thiết dù đã tắt CSRF ở API chain. **Tắt CSRF không có nghĩa cho phép POST/DELETE vô điều kiện**; các rule scope và policy nghiệp vụ vẫn phải chặn request thiếu quyền.

## 14. Kiểm thử những đường mới được thêm về sau

HTTP authorization thường có rủi ro khi ứng dụng phát triển. Ban đầu API chỉ có:

~~~text
GET  /api/orders
GET  /api/orders/{id}
POST /api/orders
~~~

Sau đó nhóm nghiệp vụ thêm:

~~~text
POST /api/orders/{id}/refund
GET  /api/orders/{id}/export
DELETE /api/orders/{id}
~~~

Nếu cấu hình dùng wildcard quá rộng như:

~~~java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

thì endpoint refund/delete có thể bị bảo vệ bằng một scope đọc không phù hợp hoặc nhận mức quyền ngoài dự kiến. Với **default deny**, các endpoint mới chưa có rule sẽ bị chặn cho đến khi nhóm phát triển định nghĩa quyền và test cho chúng.

Một chiến lược là duy trì **danh mục endpoint/contract**:

~~~yaml
# Tài liệu chính sách ví dụ, không phải YAML Spring tự đọc.
endpoints:
  - method: GET
    path: /api/public/catalog
    access: public
  - method: GET
    path: /api/orders/{id}
    required_scope: orders.read
    data_policy: owner_or_assigned_support
  - method: POST
    path: /api/orders/{id}/cancel
    required_scope: orders.cancel
    data_policy: owner_and_cancellable_status
  - method: POST
    path: /api/orders/{id}/refund
    access: deny_until_approved
default_access: deny
~~~

Khi thêm một route, code review nên yêu cầu **ít nhất một positive case và những negative cases quan trọng**. Với thao tác nhạy cảm, test thêm việc không tạo side effects khi bị từ chối.

## 15. Những lỗi kiểm thử dễ tạo cảm giác an toàn giả

### “Một token admin gọi được mọi endpoint nên security ổn”

Test chỉ có token quyền cao không chứng minh quyền tối thiểu. Nó không phát hiện việc scope đọc được phép hủy đơn, hoặc user tenant A đọc được tenant B. Cần token **quyền ít hơn** làm negative cases.

### “Có `anyRequest().authenticated()` là đủ”

Rule này chỉ đòi caller có authentication, không tự kiểm tra scope, role hoặc tenant. Trong một API yêu cầu quyền theo thao tác, `authenticated()` có thể quá rộng. Dùng khi hợp đồng thực sự chỉ cần login; không dùng thay `hasAuthority(...)` cho mọi thao tác.

### “Có `permitAll()` trên health endpoint thì mọi method đều nên pass”

Nếu chỉ định `GET` công khai, những method khác cần được xét riêng. Một matcher không ràng buộc method có thể vô tình mở cả `POST`.

### “Test dùng `jwt()` pass nghĩa là chữ ký JWT đã được kiểm tra”

Không. `jwt()` giả lập authentication; cần signed JWT integration test riêng cho signature/JWKS/issuer/audience/time.

### “MockMvc không cần Spring Security filter”

Nếu filter của Spring Security không được gắn vào MockMvc, test có thể trả 200 dù cấu hình security production không được áp dụng. Khi dùng `@WebMvcTest`/`@AutoConfigureMockMvc` với Spring Security, bảo đảm filter chain được nạp đúng và có negative test không token chứng minh nó thực sự đang chạy.

### “Response 403 chứng minh controller không chạy”

Không chắc nếu có exception handler hoặc business logic trả 403 **sau khi side effect**. Test thao tác nhạy cảm nên kiểm tra service không bị gọi hoặc dữ liệu không thay đổi.

### “URL đúng là đủ, HTTP method không quan trọng”

Sai. `GET`, `POST`, `DELETE` có ý nghĩa nghiệp vụ và mức rủi ro khác nhau; matcher rộng theo path có thể bỏ qua phân quyền theo method.

### “DenyAll cuối API chain bảo vệ toàn bộ ứng dụng”

Không nếu chain chỉ match `/api/**` và không có fallback. Cần kiểm thử mọi request nằm ngoài `securityMatcher`.

### “Endpoint không có controller thì không cần test”

Một route hiện tại trả 404 có thể được thêm controller về sau. Negative-space test và default deny là cách bảo vệ khỏi việc route mới tự mở quyền.

### “Scope đúng nghĩa là được truy cập bản ghi bất kỳ”

Sai. Scope ở HTTP layer thường là quyền loại thao tác; owner, tenant, assignment và trạng thái cần được kiểm tra tại tầng nghiệp vụ.

## 16. Thiết kế bộ test ngắn gọn nhưng đủ chiều

Một cấu trúc test suite dễ bảo trì:

~~~text
src/test/java/...
  HttpAuthorizationTest
    - public routes
    - allowed routes by scope
    - missing token
    - insufficient scope
    - wrong HTTP method
    - unexpected URL
    - fallback chain

  JwtVerificationIntegrationTest
    - trusted signature / issuer / audience
    - bad signature
    - expired / nbf not reached
    - wrong issuer / audience / token type
    - custom authority converter

  OrderAccessPolicyTest
    - own order
    - other owner's order
    - other tenant
    - support role and assignment
    - service principal cannot impersonate user

  OrderWriteSecurityIntegrationTest
    - authorized write has intended side effect
    - denied write has zero side effects
~~~

**Không phải mọi dự án bắt buộc phải tách đúng bốn class**. Ý tưởng là giữ rõ ranh giới: HTTP matchers, xác thực token, ánh xạ authority và quyền trên dữ liệu. Khi một test thất bại, nhóm phát triển biết lớp nào cần xem xét.

### 16.1. Một ma trận test tối thiểu cho một endpoint nhạy cảm

Ví dụ `POST /api/orders/{id}/cancel`:

| Trạng thái token/caller | Đơn hàng | Phản hồi/kết quả phải đạt |
| --- | --- | --- |
| Không token | Bất kỳ | Authentication từ chối |
| JWT chữ ký sai | Bất kỳ | Authentication từ chối |
| JWT hợp lệ nhưng sai audience | Bất kỳ | Authentication từ chối |
| JWT hợp lệ, chỉ `orders.read` | Bất kỳ | 403, không hủy |
| JWT hợp lệ, chỉ `orders.write` | Bất kỳ | 403, không hủy |
| JWT hợp lệ, có `orders.cancel` | Đơn không thuộc quyền | 403/404 theo policy, không hủy |
| JWT hợp lệ, có `orders.cancel` | Đơn đã giao vận không cho hủy | Từ chối theo policy, không hủy |
| JWT hợp lệ, có `orders.cancel` | Đơn thuộc quyền và trạng thái cho hủy | Hủy đúng một lần theo nghiệp vụ |
| JWT hợp lệ, `orders.cancel` | URL `/api/orders/{id}/refund` | Default deny, không refund |
| JWT hợp lệ, `orders.cancel` | Method `GET` trên cancel path | Không thực thi hủy |

Từ đây có thể mở rộng cho bất kỳ endpoint nhạy cảm nào. Điểm khác biệt lớn so với happy-path-only testing là **mỗi quyền có ranh giới âm cần được kiểm chứng**.

### 16.2. Checklist khi review pull request thay đổi phân quyền

1. Endpoint mới có rule **method + path** rõ ràng chưa?
2. Default `denyAll()` có chặn request ngoài hợp đồng không?
3. Đường ngoài `securityMatcher` có chain bảo vệ không?
4. Test public endpoint có chứng minh anonymous **được vào**, và method khác **không tự được mở** không?
5. Test protected endpoint có cả **scope đủ → allow** và **scope sai/thiếu → deny** không?
6. Test thiếu Bearer token có bị từ chối ở authentication không?
7. Test JWT sai issuer/audience/chữ ký/hết hạn có dùng **token ký thật** qua decoder không?
8. Test authority converter có phản ánh đúng claim `scope`/roles/permissions không?
9. Test tenant/owner của một đối tượng cụ thể có chặn truy cập ngang hàng không?
10. Test thao tác bị từ chối có kiểm tra không tạo side effect không?
11. Test behavior của trailing slash, method đặc biệt, gateway rewrite và CORS theo hạ tầng thật chưa?
12. Trong production, có log/correlation ID đủ chẩn đoán mà không ghi Bearer token hoặc secret không?

## 17. Bài tập tình huống

**Tình huống 1:** API có rule `GET /api/orders/**` yêu cầu `orders.read`. Một developer thêm `GET /api/orders/42/export`. Test token `orders.read` trả 200. Có đủ an toàn không?

**Chưa.** Endpoint export có thể chứa dữ liệu nhạy cảm hơn read đơn; phải định nghĩa scope/policy riêng nếu cần. Test negative giúp phát hiện matcher quá rộng đang cho phép quyền không phù hợp.

**Tình huống 2:** Test `GET /api/orders/42` với `jwt().authorities("SCOPE_orders.read")` pass. Có chứng minh token sai audience sẽ bị từ chối không?

**Không.** `jwt()` không đi qua `JwtDecoder` thật. Cần integration test với Bearer JWT ký thật và audience sai.

**Tình huống 3:** Token hợp lệ có `orders.write` được gửi tới `GET /api/orders/42`. Kết quả hợp đồng là gì?

**403** nếu API chỉ yêu cầu và cấp riêng `orders.read` cho endpoint GET, không có quy tắc `orders.write` bao hàm `orders.read`. Test này phát hiện việc scope bị hiểu quá rộng.

**Tình huống 4:** `GET /api/public/catalog` anonymous trả 200, nhưng `POST /api/public/catalog` cũng trả 200. Vì sao nguy hiểm?

Rule `permitAll()` có thể đang áp dụng theo path mà không giới hạn method. Cần sửa matcher và thêm negative test cho POST/PUT/DELETE.

**Tình huống 5:** `GET /internal/secrets` không khớp `securityMatcher("/api/**")`. Có chắc đã bị chặn?

**Không nếu không có filter chain nào khác.** Cần fallback/default chain hoặc cơ chế bảo vệ tương đương; test đường ngoài API.

**Tình huống 6:** Người dùng có `orders.read` được phép gọi controller xem đơn 42, nhưng đơn 42 thuộc tenant khác. Test HTTP scope pass; kết luận phân quyền an toàn?

**Không.** Phải có test quyền đối tượng, kiểm tra owner/tenant/assignment trên bản ghi thật và từ chối dữ liệu không thuộc phạm vi.

**Tình huống 7:** Request hủy đơn bị trả 403, nhưng log database cho thấy status đơn đã đổi thành CANCELLED. Có thể coi negative test pass?

**Không.** Side effect đã diễn ra trước khi từ chối. Cần đưa authorization trước thao tác và bổ sung assertion không có write/event khi bị deny.

---

## Kết luận

Kiểm thử **HTTP authorization** trong Spring Security Resource Server phải chứng minh **cả hai hướng**: request hợp lệ với method, path và scope đúng **được đi qua** lớp bảo mật; request thiếu authentication, sai token, thiếu authority, sai method, nằm ngoài đường được cấp hoặc vi phạm quyền trên tài nguyên **bị từ chối**.

Một chiến lược đáng tin gồm **rule method + path cụ thể**, `anyRequest().denyAll()`, fallback bảo vệ đường ngoài `securityMatcher`, bộ test MockMvc có cả positive/negative cases, integration test **Bearer JWT ký thật** cho `JwtDecoder`, và test ownership/tenant cùng **không có side effect khi bị deny**. `jwt()` là công cụ rất tốt để kiểm tra rule theo authority, nhưng không thay thế kiểm thử xác minh JWT. Mục tiêu cuối cùng không phải “có một request trả 200”, mà là **chỉ những request đúng hợp đồng mới có thể gây ra hành động nghiệp vụ được bảo vệ**.
