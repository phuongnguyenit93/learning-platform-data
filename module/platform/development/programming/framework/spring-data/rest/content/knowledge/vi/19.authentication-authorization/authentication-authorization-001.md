# Tích hợp SecurityFilterChain với các đường dẫn Spring Data REST

Spring Data REST tự động công bố repository thành các REST endpoint. Khi thêm Spring Security, cần cấu hình SecurityFilterChain để kiểm soát quyền truy cập vào API root, collection, item, association, search và các endpoint metadata. Quy tắc phải khớp với base path và HTTP method thực tế mà Spring Data REST công bố.

SecurityFilterChain bảo vệ request ở tầng HTTP. Nó quyết định request nào cần xác thực, authority nào được yêu cầu và request nào được phép đi tiếp. Nếu ứng dụng còn có service được gọi từ nhiều entry point, hãy kết hợp thêm method security để bảo vệ thao tác nghiệp vụ tại ranh giới service.

## 1. Spring Data REST công bố những đường dẫn nào?

Giả sử repository được công bố dưới base path /api:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
~~~

Spring Data REST có thể công bố các đường dẫn theo dạng:

| Tài nguyên | Ví dụ đường dẫn | Mục đích |
|---|---|---|
| API root | /api | Khám phá các repository resource. |
| Collection | /api/orders | Đọc hoặc tạo tập hợp đơn hàng. |
| Item | /api/orders/42 | Đọc, cập nhật hoặc xóa một đơn hàng. |
| Association | /api/orders/42/customer | Đọc hoặc thay đổi liên kết customer. |
| Search | /api/orders/search/by-status | Gọi query method được công bố. |
| Profile | /api/profile | Đọc metadata/profile của API. |

Đường dẫn cụ thể phụ thuộc vào RepositoryRestConfiguration, @RepositoryRestResource, @RestResource và query method thực tế. Ví dụ trên dùng path orders; nếu repository đổi path hoặc ứng dụng đổi base path, các matcher bảo mật cũng phải được cập nhật.

Trước khi viết matcher, hãy xác định base path và các endpoint mà ứng dụng thực sự công bố từ cấu hình đã biết. Không nên đoán một đường dẫn chỉ vì tên repository hoặc entity.

## 2. SecurityFilterChain làm việc ở đâu?

SecurityFilterChain là chuỗi filter xử lý HTTP request trước khi request đến controller hoặc Spring Data REST handler. Trong cấu hình phổ biến, Spring Security thực hiện các việc:

1. Nhận diện request và chọn SecurityFilterChain phù hợp.
2. Áp dụng cơ chế xác thực như session, HTTP Basic hoặc bearer token.
3. Đánh giá các quy tắc authorization theo thứ tự matcher.
4. Từ chối request nếu người gọi chưa xác thực hoặc không có authority.
5. Chuyển request hợp lệ tới Spring MVC/Spring Data REST.

Cấu hình security ở tầng request phù hợp để bảo vệ nhóm đường dẫn và HTTP method. Ví dụ, người dùng có ORDER_READ được GET collection và item, còn người có ORDER_CREATE được POST collection.

Không nên nhầm việc request được xác thực với việc request được phép thực hiện. Một người dùng có thể đăng nhập thành công nhưng vẫn thiếu authority cần thiết cho endpoint cụ thể.

## 3. Cấu hình SecurityFilterChain cơ bản

Ví dụ sau bảo vệ base path /api và phân quyền theo HTTP method:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.OPTIONS, "/api/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/profile").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("ORDER_READ")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("ORDER_CREATE")
                .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("ORDER_UPDATE")
                .requestMatchers(HttpMethod.PATCH, "/api/orders/**")
                    .hasAuthority("ORDER_UPDATE")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("ORDER_DELETE")
                .requestMatchers("/api/**").denyAll()
                .anyRequest().authenticated()
            )
            .build();
    }
}
~~~

Các matcher được đánh giá theo thứ tự khai báo. Quy tắc cụ thể cần đứng trước quy tắc tổng quát. Nếu đặt requestMatchers("/api/**").denyAll() lên trước, các matcher phía sau sẽ không được áp dụng cho request thuộc /api.

Trong ví dụ, OPTIONS được cho phép để hỗ trợ preflight CORS; cấu hình CORS thực tế vẫn cần khai báo origin, method và header được phép. Không nên cho phép mọi HTTP method trên toàn bộ API chỉ để làm cho preflight hoạt động.

Quy tắc cuối anyRequest().authenticated() yêu cầu xác thực cho các đường dẫn còn lại. Hãy điều chỉnh theo chính sách ứng dụng và bảo đảm không vô tình công bố endpoint quản trị hoặc endpoint nội bộ.

## 4. Phân quyền collection và item theo HTTP method

Collection và item thường hỗ trợ các thao tác khác nhau:

- GET collection: đọc danh sách.
- POST collection: tạo tài nguyên.
- GET item: đọc một tài nguyên.
- PUT item: thay thế hoặc cập nhật tài nguyên theo semantics của endpoint.
- PATCH item: cập nhật một phần.
- DELETE item: xóa tài nguyên.

Có thể dùng matcher theo method và path:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders", "/api/orders/**")
        .hasAuthority("ORDER_READ")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("ORDER_CREATE")
    .requestMatchers(HttpMethod.PUT, "/api/orders/**")
        .hasAuthority("ORDER_UPDATE")
    .requestMatchers(HttpMethod.PATCH, "/api/orders/**")
        .hasAuthority("ORDER_UPDATE")
    .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
        .hasAuthority("ORDER_DELETE")
    .anyRequest().authenticated()
)
~~~

Cần kiểm tra matcher path theo phiên bản Spring Security và cách ứng dụng khai báo request matcher. Các pattern có thể khớp nhiều endpoint con hơn dự kiến. Nếu muốn chỉ cho phép GET trên collection và item, hãy xác định rõ path và test cả endpoint association/search.

Một quy tắc GET rộng cho /api/orders/** cũng có thể bao phủ các đường dẫn con như association hoặc search. Nếu association có quyền riêng, hãy đặt matcher cụ thể cho nó trước matcher rộng hoặc thiết kế matcher theo từng nhóm endpoint.

## 5. Bảo vệ association endpoints

Spring Data REST có thể công bố association resource để đọc hoặc thay đổi quan hệ giữa các entity. Ví dụ:

~~~text
GET    /api/orders/42/customer
PUT    /api/orders/42/customer
DELETE /api/orders/42/customer
~~~

Các thao tác association có thể làm thay đổi dữ liệu nghiệp vụ dù URL không phải collection hoặc item CRUD thông thường. Vì vậy, không nên bỏ qua chúng khi thiết kế authorization.

Ví dụ yêu cầu authority riêng cho việc thay đổi liên kết customer:

~~~java
.requestMatchers(
    HttpMethod.PUT,
    "/api/orders/*/customer"
).hasAuthority("ORDER_ASSIGN_CUSTOMER")
.requestMatchers(
    HttpMethod.DELETE,
    "/api/orders/*/customer"
).hasAuthority("ORDER_REMOVE_CUSTOMER")
~~~

Các pattern trên chỉ minh họa đường dẫn association đã biết. Nếu association có nhiều cấp hoặc tên khác, hãy dùng path thực tế đã công bố. Cũng cần xem xét quan hệ collection, ví dụ /api/orders/42/items, vì POST/DELETE ở đó có thể thêm hoặc gỡ phần tử quan hệ.

Nếu matcher tổng quát cho phép mọi request POST hoặc PUT dưới /api/orders/**, nó có thể vô tình cho phép sửa association bằng authority CRUD thông thường. Hãy đặt quy tắc association cụ thể trước quy tắc rộng.

## 6. Bảo vệ search endpoints

Query method có thể được công bố dưới /search, ví dụ:

~~~text
GET /api/orders/search/by-status?status=CONFIRMED
~~~

Search endpoint thường chỉ đọc dữ liệu, nhưng dữ liệu được truy vấn có thể nhạy cảm. Hãy gán quyền phù hợp:

~~~java
.requestMatchers(
    HttpMethod.GET,
    "/api/orders/search/**"
).hasAuthority("ORDER_READ")
~~~

Nếu có search cho dữ liệu nhạy cảm hoặc chức năng quản trị, hãy đặt authority riêng. Ví dụ, tìm kiếm mọi khách hàng có thể cần CUSTOMER_READ_ALL thay vì quyền đọc một tài nguyên mà người dùng sở hữu.

Đặt matcher search cụ thể trước matcher GET tổng quát nếu chính sách search khác với quyền đọc item. Kiểm tra cả tên query method thực tế và việc method có được công bố bằng @RestResource hay không.

## 7. API root, profile và metadata

API root giúp client khám phá repository resources. Các endpoint profile hoặc metadata cũng có thể tiết lộ cấu trúc domain, tên thuộc tính hoặc các link mà ứng dụng công bố.

Có thể cho phép người dùng đã xác thực đọc API root:

~~~java
.requestMatchers(HttpMethod.GET, "/api").authenticated()
.requestMatchers(HttpMethod.GET, "/api/profile").authenticated()
~~~

Nếu metadata được xem là công khai, có thể dùng permitAll cho đúng đường dẫn GET đã xác định. Không nên cho phép toàn bộ /api/** chỉ vì muốn client đọc API root.

Profile và API root không nhất thiết chứa dữ liệu nghiệp vụ, nhưng vẫn có thể tiết lộ bề mặt API. Hãy chọn chính sách phù hợp với mô hình triển khai và yêu cầu bảo mật.

## 8. Dùng authority và role nhất quán

Spring Security hỗ trợ kiểm tra authority và role. hasAuthority("ORDER_READ") so sánh tên authority chính xác. hasRole("ADMIN") thường kiểm tra authority ROLE_ADMIN theo role prefix mặc định.

Ví dụ:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("ORDER_READ")
.requestMatchers("/api/admin/**")
    .hasRole("ADMIN")
~~~

Nên dùng authority cho quyền thao tác cụ thể như ORDER_READ, ORDER_APPROVE hoặc ORDER_EXPORT. Role thường đại diện cho nhóm người dùng như ADMIN, SUPPORT hoặc AUDITOR.

Đừng trộn lẫn hai quy ước tên. Nếu cấu hình cấp quyền dùng ROLE_ORDER_READ, thì hasAuthority("ORDER_READ") sẽ không khớp. Hãy thống nhất cách cấp GrantedAuthority trong UserDetails, JWT converter hoặc cơ chế authentication đang sử dụng.

## 9. Phân tách nhiều SecurityFilterChain khi cần

Ứng dụng có thể có nhiều loại request với cơ chế bảo vệ khác nhau, ví dụ API stateless dùng bearer token và giao diện web dùng session. Khi đó có thể định nghĩa nhiều SecurityFilterChain và dùng securityMatcher để chọn chain:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("ORDER_READ")
            .anyRequest().authenticated()
        )
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

securityMatcher chọn toàn bộ request thuộc chain; requestMatchers bên trong chain quyết định authorization cho từng request đã được chọn.

Chain API cần được đặt thứ tự phù hợp và có matcher rõ ràng. Request không khớp chain đầu sẽ được xét tới chain tiếp theo. Nếu không có chain phù hợp, request có thể không được bảo vệ theo chính sách mong muốn; vì vậy hãy bảo đảm có chain mặc định bao phủ các request còn lại.

Không tạo nhiều chain chỉ để chia nhỏ vài matcher nếu một chain duy nhất đã đủ rõ ràng. Nhiều chain làm tăng độ phức tạp khi debug vì phải xác định chain nào đang xử lý request.

## 10. Authentication, session và bearer token

SecurityFilterChain cấu hình authorization nhưng cũng kết hợp với cơ chế xác thực.

Với API dùng session, ứng dụng có thể dùng form login hoặc cơ chế đăng nhập phù hợp. Với API stateless, có thể cấu hình OAuth2 Resource Server để xác thực JWT:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("ORDER_READ")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
        .build();
}
~~~

JWT cần được chuyển thành Authentication và GrantedAuthority đúng quy ước mà matcher sử dụng. Nếu token chứa scope như orders.read, Spring Resource Server thường ánh xạ scope thành authority có tiền tố SCOPE_; khi đó matcher có thể dùng hasAuthority("SCOPE_orders.read") hoặc cấu hình converter riêng.

Không nên mặc định rằng claim role trong JWT tự động trở thành ROLE_ADMIN. Cần cấu hình JwtAuthenticationConverter nếu token dùng claim hoặc prefix khác mặc định.

Với session cookie, cần xem xét CSRF cho các request thay đổi dữ liệu. Với API bearer token stateless, cách cấu hình CSRF phụ thuộc việc credential có được trình duyệt tự động gửi hay không. Chỉ tắt CSRF khi mô hình xác thực và rủi ro của ứng dụng cho phép; không sao chép cấu hình stateless cho API đang dùng session cookie.

## 11. CORS và preflight request

Khi JavaScript client chạy từ origin khác, trình duyệt có thể gửi OPTIONS preflight trước request thực tế. Cần cấu hình CORS trong Spring Security:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.com"));
    config.setAllowedMethods(List.of(
        "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"
    ));
    config.setAllowedHeaders(List.of(
        "Authorization", "Content-Type", "Accept", "If-Match"
    ));
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
~~~

Bật CORS trong chain:

~~~java
http.cors(Customizer.withDefaults());
~~~

Nếu dùng credentials, hãy khai báo origin cụ thể; không dùng wildcard origin cùng credential. CORS chỉ quyết định trình duyệt có được phép đọc response cross-origin hay không. Nó không thay thế authentication hoặc authorization.

Không nên cho phép OPTIONS bằng cách mở mọi request. Hãy để CORS xử lý preflight và giới hạn các origin, method, header theo nhu cầu thực tế.

## 12. Kết hợp request authorization với method security

Một request có thể đi qua SecurityFilterChain rồi gọi service nghiệp vụ. Quyền ở tầng HTTP bảo vệ đường dẫn; method security bảo vệ thao tác cụ thể tại service.

Ví dụ:

~~~java
@Service
public class OrderService {

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    @Transactional
    public void approve(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
            .orElseThrow(() -> new EntityNotFoundException("Order not found"));

        order.approve();
    }
}
~~~

SecurityFilterChain có thể cho phép nhóm người có ORDER_READ truy cập GET endpoint. Nhưng chỉ người có ORDER_APPROVE mới gọi được phương thức approve qua Spring proxy.

Điều này hữu ích nếu cùng service được gọi từ controller khác, scheduler hoặc message consumer. Tuy nhiên, method security hoạt động qua Spring AOP proxy; self-invocation trong cùng bean có thể bỏ qua interceptor. Hãy gọi qua bean proxy hoặc tách thao tác được bảo vệ sang service riêng.

Không nên đặt toàn bộ quy tắc quyền chỉ trong controller vì một entry point khác có thể gọi service mà không đi qua controller đó.

## 13. Quy tắc matcher phải phản ánh quyền trên từng thao tác

Một cách tổ chức là nhóm endpoint theo quyền:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/search/**")
        .hasAuthority("ORDER_READ")
    .requestMatchers(HttpMethod.GET, "/api/orders", "/api/orders/**")
        .hasAuthority("ORDER_READ")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("ORDER_CREATE")
    .requestMatchers(HttpMethod.PUT, "/api/orders/**")
        .hasAuthority("ORDER_UPDATE")
    .requestMatchers(HttpMethod.PATCH, "/api/orders/**")
        .hasAuthority("ORDER_UPDATE")
    .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
        .hasAuthority("ORDER_DELETE")
    .requestMatchers("/api/**").denyAll()
    .anyRequest().authenticated()
)
~~~

Đây là ví dụ nền; ứng dụng cần điều chỉnh cho các association, action endpoint, profile, search và repository khác. Nếu một association POST/PUT có quyền riêng, hãy đặt matcher cụ thể cho nó trước matcher tổng quát.

Quy tắc denyAll cho phần còn lại của API là một cách đóng mặc định: endpoint mới được công bố sẽ bị từ chối cho đến khi được gán quyền. Điều này hữu ích khi repository hoặc query method mới được thêm vào và vô tình mở rộng bề mặt API.

Khi ứng dụng có nhiều repository, hãy nhóm matcher theo domain hoặc tạo helper method để cấu hình dễ đọc. Tránh tạo một pattern quá rộng khiến quyền của một resource vô tình áp dụng cho resource khác.

## 14. Kiểm thử SecurityFilterChain với MockMvc

Cần kiểm tra cả request được phép và request bị từ chối. Ví dụ:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderSecurityIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(authorities = "ORDER_READ")
    void readerCanGetOrders() throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "ORDER_READ")
    void readerCannotCreateOrder() throws Exception {
        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"status\":\"DRAFT\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousUserCannotReadOrders() throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Status cho request anonymous phụ thuộc authentication entry point. Với HTTP Basic hoặc bearer API, thường nhận 401; với form login, request có thể được redirect tới trang đăng nhập. Hãy viết assertion theo cơ chế xác thực thực tế của ứng dụng.

Bài test cần kiểm tra ít nhất:

- Anonymous không truy cập được endpoint cần xác thực.
- Người có ORDER_READ đọc được collection và item.
- Người chỉ có ORDER_READ không được POST, PUT, PATCH hoặc DELETE.
- Người có authority tương ứng thực hiện được thao tác được phép.
- Association và search endpoint tuân thủ quyền riêng.
- API root và profile theo đúng chính sách đã chọn.
- OPTIONS preflight hoạt động với origin và header được phép.
- Endpoint mới hoặc chưa có matcher bị denyAll nếu dùng default-deny.

Nếu test repository endpoint tự động, hãy dùng đúng base path và relation đã cấu hình. Không chỉ test controller tự viết vì Spring Data REST handler có thể có các đường dẫn khác.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| GET collection bị 403 | Authority không khớp hoặc matcher path sai. | Kiểm tra GrantedAuthority, base path và HTTP method. |
| POST được phép ngoài dự kiến | Matcher POST quá rộng hoặc thứ tự matcher sai. | Đặt matcher cụ thể trước pattern tổng quát. |
| Association vẫn sửa được | Matcher CRUD chung đã bao phủ association. | Thêm matcher association cụ thể và quyền riêng. |
| Search endpoint bị từ chối | Chưa có matcher cho /search/** hoặc quyền không phù hợp. | Bổ sung matcher search theo chính sách dữ liệu. |
| API root không truy cập được | Chỉ cấu hình matcher cho repository path. | Xác định chính sách và thêm matcher GET /api. |
| CORS preflight trả 401/403 | OPTIONS hoặc CORS chưa được cấu hình đúng. | Bật http.cors và khai báo origin/method/header phù hợp. |
| JWT đã hợp lệ nhưng vẫn 403 | Claim không ánh xạ thành authority mà matcher yêu cầu. | Kiểm tra JwtAuthenticationConverter và prefix. |
| Quy tắc service không chạy | Method security chưa bật hoặc self-invocation bỏ qua proxy. | Bật @EnableMethodSecurity và gọi qua Spring bean proxy. |
| Endpoint mới tự động bị mở | Có matcher rộng cho phép toàn bộ API. | Dùng default-deny và bổ sung quyền tường minh. |

## 16. Quy trình triển khai

Khi tích hợp SecurityFilterChain với Spring Data REST:

1. Xác định base path của Spring Data REST và repository path được công bố.
2. Liệt kê collection, item, association, search, API root và profile endpoint cần bảo vệ.
3. Xác định quyền theo HTTP method và nghiệp vụ, bao gồm quyền riêng cho association hoặc dữ liệu nhạy cảm.
4. Cấu hình matcher cụ thể trước matcher tổng quát.
5. Chọn authentication phù hợp: session, HTTP Basic trong môi trường phù hợp hoặc bearer token/JWT.
6. Cấu hình CSRF theo mô hình credential thực tế.
7. Cấu hình CORS cho origin, method và header thực sự cần dùng.
8. Dùng default-deny cho phần API chưa được cấp quyền nếu chính sách yêu cầu.
9. Bật method security cho các thao tác service quan trọng được gọi từ nhiều entry point.
10. Viết MockMvc integration test cho request được phép, bị từ chối, association, search, API root và preflight.
11. Kiểm tra lại khi thêm repository, query method hoặc thay đổi base path vì bề mặt endpoint có thể thay đổi.

SecurityFilterChain kiểm soát request tới các đường dẫn Spring Data REST theo HTTP method và authority. Hãy xác định đúng base path, bảo vệ cả collection, item, association, search và metadata, đồng thời sắp xếp matcher từ cụ thể đến tổng quát. Kết hợp request authorization với method security, CORS/CSRF phù hợp và integration test sẽ giúp API giữ quyền truy cập nhất quán khi repository hoặc endpoint thay đổi.
