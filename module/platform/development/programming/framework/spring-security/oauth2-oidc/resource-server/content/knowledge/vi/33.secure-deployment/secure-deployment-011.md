# Rà soát endpoint công khai và xác nhận không có chuỗi bảo mật bị bỏ sót

## 1. Mục tiêu: biết mọi đường vào ứng dụng đang được bảo vệ thế nào

Một ứng dụng Spring Security có thể có nhiều endpoint hơn những controller mà nhóm phát triển thường nhìn thấy. Ngoài API nghiệp vụ còn có health check, actuator, static resources, error handler, OAuth callback, servlet riêng, WebSocket, GraphQL hoặc route được khai báo bằng functional router. Một endpoint mới cũng có thể được thêm vào mà không ai cập nhật security matcher.

Rủi ro xuất hiện khi một đường dẫn lọt khỏi SecurityFilterChain, một matcher quá rộng vô tình mở cả nhóm API, hoặc một chain chuyên biệt không có fallback chain bao phủ phần còn lại.

Mục tiêu của việc rà soát là trả lời được bốn câu hỏi:

1. Ứng dụng thực sự expose những URL và HTTP methods nào?
2. Endpoint nào được phép truy cập ẩn danh, endpoint nào cần authentication và endpoint nào cần authority cụ thể?
3. Mỗi request được xử lý bởi SecurityFilterChain nào?
4. Có test chứng minh cả endpoint công khai lẫn endpoint được bảo vệ, bao gồm method và path variations, không?

**Nguyên tắc mặc định:** mọi request đều phải đi qua một security chain có chủ đích. Endpoint công khai được khai báo rõ ràng trong allowlist; phần còn lại yêu cầu authentication hoặc bị từ chối.

## 2. Phân biệt securityMatcher và requestMatchers

Hai loại matcher có vai trò khác nhau.

| Matcher | Vị trí | Câu hỏi |
| --- | --- | --- |
| securityMatcher(...) | Chọn một SecurityFilterChain | Request này có thuộc chain này không? |
| requestMatchers(...) | Bên trong authorizeHttpRequests | Trong chain đã chọn, request này được permit, authenticate hay kiểm tra authority? |

Ví dụ:

```java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers(HttpMethod.GET, "/api/catalog/public/**")
            .permitAll()
        .requestMatchers("/api/admin/**")
            .hasAuthority("SCOPE_admin")
        .anyRequest()
            .authenticated())
    .oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
```

Trong ví dụ:

- securityMatcher("/api/**") chọn chain cho mọi request thuộc /api/**.
- requestMatchers(HttpMethod.GET, "/api/catalog/public/**") chỉ mở các GET thuộc đường dẫn catalog public.
- /api/admin/** yêu cầu authority SCOPE_admin.
- Các request còn lại trong chain /api/** phải authenticated.

Nếu bỏ securityMatcher, chain mặc định có thể áp dụng cho mọi request. Nếu có nhiều chain, việc chọn chain phụ thuộc thứ tự và matcher của từng chain.

### 2.1. Một request chỉ đi vào chain đầu tiên khớp

Khi có nhiều SecurityFilterChain, Spring Security kiểm tra theo thứ tự @Order. Chain đầu tiên có securityMatcher khớp sẽ xử lý request; các chain phía sau không tiếp tục áp dụng cho cùng request đó.

```text
Incoming request
      │
      ▼
SecurityFilterChain @Order(1)
      │ match?
      ├── yes ──> dùng chain này, dừng chọn chain
      │
      └── no
           ▼
SecurityFilterChain @Order(2)
      │ match?
      ├── yes ──> dùng chain này, dừng chọn chain
      │
      └── no
           ▼
SecurityFilterChain @Order(3)
      │
      └── ...
```

Đây là lý do một chain chuyên biệt không tự động bảo vệ phần còn lại của ứng dụng. Nếu không có chain nào khớp, request có thể không đi qua Spring Security filter chain.

### 2.2. anyRequest() chỉ bao phủ request trong chain đã chọn

Ví dụ:

```java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(authorize -> authorize
        .anyRequest().authenticated());
```

anyRequest().authenticated() ở đây chỉ áp dụng cho request thuộc /api/**. Nó không bảo vệ /admin/**, /internal/**, /actuator/** hoặc endpoint khác nằm ngoài matcher.

Hãy đọc anyRequest() cùng với securityMatcher, không tách hai phần khi review.

## 3. Xây dựng endpoint inventory trước khi viết allowlist

Không thể chứng minh mọi endpoint được bảo vệ nếu không biết toàn bộ endpoint đang tồn tại. Hãy tạo inventory theo URL **và HTTP method**, không chỉ theo tên controller.

Một inventory hữu ích có các trường:

| Trường | Nội dung |
| --- | --- |
| HTTP method | GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS hoặc ALL |
| Route | Route template, ví dụ /api/orders/{orderId} |
| Handler | Controller/method hoặc functional route |
| Nhóm | Public, authenticated, role/scope protected, internal, management |
| Chain | Security chain dự kiến xử lý |
| Lý do công khai | Lý do nghiệp vụ và chủ sở hữu endpoint |
| Test | Tên test chứng minh policy |
| Exposure | Internet, internal network, management port hoặc gateway-only |

Ví dụ:

| Method | Route | Phân loại | Chính sách |
| --- | --- | --- | --- |
| GET | /api/catalog/public/** | Public | permitAll |
| GET | /api/orders/** | Authenticated | SCOPE_orders:read |
| POST | /api/orders/** | Authenticated | SCOPE_orders:write |
| DELETE | /api/admin/users/** | Restricted | SCOPE_admin |
| GET | /actuator/health | Operational public/internal | Chỉ công khai health tổng quát theo deployment |
| GET | /actuator/env | Sensitive management | Không public |
| POST | /oauth2/token | Protocol endpoint | Chỉ tồn tại nếu ứng dụng thực sự đóng vai Authorization Server |

Không copy nguyên bảng minh họa vào production. Owner của API phải xác nhận route, methods, exposure và business reason.

### 3.1. Nguồn endpoint cần rà soát

Ít nhất kiểm tra các nguồn sau:

1. **Spring MVC controllers:** @RequestMapping, @GetMapping, @PostMapping và các mapping kế thừa.
2. **Functional routes:** RouterFunction, RouterFunctions.route và route được đăng ký qua bean.
3. **Actuator:** endpoint được expose qua management.endpoints.web.exposure.include, management port và base path.
4. **Servlet/filter mappings:** servlet riêng, dispatcher servlet bổ sung, file upload hoặc endpoint do thư viện đăng ký.
5. **Error handling:** /error, error controller, exception handler và dispatcher type.
6. **Static resources:** favicon, assets, documentation UI, file download.
7. **Protocol callbacks:** OAuth/OIDC login callback, logout callback, webhook và endpoint nhận sự kiện.
8. **Realtime endpoints:** WebSocket handshake, SockJS, SSE và GraphQL HTTP/WebSocket.
9. **Infrastructure routing:** ingress, API gateway, reverse proxy, path rewrite và management port.
10. **Các context riêng:** application context path, servlet path và management context path.

Controller inventory không thể nhìn thấy mọi servlet, actuator endpoint, gateway route hoặc WebSocket handshake. Vì vậy phải kết hợp mã ứng dụng với cấu hình triển khai.

### 3.2. Kiểm tra route theo HTTP method

Một path có thể có nhiều policy khác nhau theo method:

```text
GET    /api/orders/{id}  -> SCOPE_orders:read
PATCH  /api/orders/{id}  -> SCOPE_orders:write
DELETE /api/orders/{id}  -> SCOPE_orders:delete
```

Nếu chỉ ghi inventory theo path, nhóm review có thể bỏ sót một method ghi dữ liệu. Mỗi method được hỗ trợ phải có policy rõ ràng.

Không giả định HEAD hoặc OPTIONS luôn được bảo vệ giống GET. Hãy kiểm tra hành vi thực tế của framework, CORS và route.

## 4. Lập danh sách endpoint public có chủ đích

Một endpoint được gọi là public khi người dùng không cần authentication để truy cập. Public không đồng nghĩa endpoint không có validation, rate limit, authorization nghiệp vụ hoặc kiểm soát abuse.

Ví dụ các endpoint có thể được công khai:

- Catalog hoặc danh sách dữ liệu công khai.
- Landing page hoặc nội dung hướng dẫn.
- Health endpoint tổng quát phục vụ load balancer nếu chính sách vận hành cho phép.
- Callback được thiết kế public theo một protocol và có cơ chế xác minh riêng.
- Static assets không chứa dữ liệu riêng tư.

Ví dụ các endpoint thường không nên public:

- Dữ liệu người dùng, đơn hàng hoặc tài khoản.
- Endpoint admin/management.
- Actuator env, configprops, heapdump, mappings, beans, loggers nếu không có lớp bảo vệ riêng.
- Metrics chứa thông tin nội bộ hoặc dữ liệu tenant.
- Endpoint export/download dữ liệu.
- Endpoint thay đổi trạng thái, tạo giao dịch hoặc thực hiện hành động nhạy cảm.

Với mỗi endpoint public, ghi rõ:

1. Ai là người tiêu thụ endpoint?
2. Dữ liệu nào có thể được trả về?
3. Có cần rate limiting, abuse protection hoặc cache policy không?
4. Endpoint có nhận input ảnh hưởng đến dữ liệu hoặc chi phí không?
5. Ai sở hữu quyết định public?
6. Test nào sẽ phát hiện endpoint bị đổi method hoặc route ngoài ý muốn?

Không giữ endpoint public chỉ vì nó đã tồn tại lâu hoặc vì một test hiện tại cần gọi được.

## 5. permitAll và web.ignoring khác nhau thế nào?

Hai cơ chế này không tương đương.

### 5.1. permitAll: vẫn đi qua Spring Security

Ví dụ:

```java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/public/**").permitAll()
        .anyRequest().authenticated());
```

Request tới /public/** không cần authenticated principal để vượt qua authorization rule. Nhưng request vẫn đi qua security filter chain. Các filter liên quan vẫn có thể xử lý:

- Security headers.
- CORS integration.
- Security context lifecycle.
- CSRF protection nếu được bật.
- Request firewall.
- Các filter khác đã cấu hình trong chain.

Nếu Resource Server filter cũng nằm trong chain, Bearer token được gửi kèm có thể vẫn được parse và authenticate trước khi authorization rule permitAll được đánh giá.

### 5.2. web.ignoring: bỏ qua security filter chain

Ví dụ:

```java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
            .requestMatchers("/assets/**", "/favicon.ico");
}
```

Các request khớp web.ignoring không đi qua Spring Security filter chain. Chúng bỏ qua những filter mà chain cung cấp, bao gồm security headers, security context, CSRF và authorization rules của Spring Security.

Chỉ cân nhắc cơ chế này cho tài nguyên thực sự không cần bất kỳ xử lý nào của security chain. Với phần lớn endpoint HTTP, permitAll rõ ràng và dễ kiểm soát hơn.

### 5.3. Bảng so sánh

| Hành vi | permitAll | web.ignoring |
| --- | --- | --- |
| Request đi qua Spring Security chain | Có | Không |
| Security headers do chain thêm | Có thể áp dụng | Không từ chain bị bỏ qua |
| SecurityContext/filter chain | Có | Không |
| CORS/CSRF/security filters | Theo cấu hình chain | Không từ chain bị bỏ qua |
| Authorization rule | Cho phép anonymous | Không chạy rule của chain |
| Dùng cho API public | Thường phù hợp | Tránh dùng |
| Dùng cho static resources | Có thể dùng | Có thể dùng trong trường hợp hẹp, có chủ đích |

Spring Security hiện đại hỗ trợ permitAll mà không cần ép ứng dụng đọc session để tìm authentication nếu request không cần nó. Vì vậy, không nên chọn web.ignoring chỉ để tiết kiệm một lần kiểm tra session.

## 6. Cấu hình một chain mặc định theo nguyên tắc deny by default

Với Resource Server đơn giản, một chain bao phủ toàn bộ ứng dụng thường dễ review nhất:

```java
@Bean
SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers(
                            HttpMethod.GET,
                            "/api/catalog/public/**")
                        .permitAll()
                    .requestMatchers(
                            HttpMethod.GET,
                            "/actuator/health")
                        .permitAll()
                    .requestMatchers(
                            HttpMethod.GET,
                            "/api/orders/**")
                        .hasAuthority("SCOPE_orders:read")
                    .requestMatchers(
                            HttpMethod.POST,
                            "/api/orders/**")
                        .hasAuthority("SCOPE_orders:write")
                    .requestMatchers("/api/admin/**")
                        .hasAuthority("SCOPE_admin")
                    .anyRequest()
                        .authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .build();
}
```

Các rule cụ thể được đặt trước rule tổng quát. anyRequest().authenticated() nằm cuối để mọi route chưa được phân loại vẫn yêu cầu authentication.

### 6.1. Public không có nghĩa là bỏ authentication filter

Vì Resource Server filter vẫn hoạt động, request public không có Bearer token có thể được truy cập. Nhưng nếu client gửi một Bearer token malformed hoặc hết hạn, authentication có thể thất bại trước khi permitAll được xét và response sẽ là 401.

Đây là hành vi cần quyết định rõ:

- Nếu endpoint public chỉ cho anonymous request và token hợp lệ là tùy chọn, cần thiết kế cách xử lý optional authentication có chủ đích.
- Nếu endpoint public vẫn dùng authentication khi token hợp lệ để cá nhân hóa nội dung, thường nên từ chối token sai thay vì âm thầm bỏ qua lỗi.
- Nếu endpoint public không cần identity, có thể dùng chain không cài Resource Server filter cho nhóm route đó; khi ấy Bearer header sẽ không được xác thực trong chain đó.

Không viết test chỉ với request không có token rồi kết luận mọi cách gọi tới endpoint public đều hoạt động như nhau.

### 6.2. permitAll không bỏ qua method security

Authorization ở HTTP layer và method security là hai lớp riêng.

Ví dụ endpoint được permitAll, nhưng controller gọi service có:

```java
@PreAuthorize("hasAuthority('SCOPE_internal:read')")
public PublicData readData() {
    // ...
}
```

Anonymous request vẫn có thể bị method security từ chối. Khi review public endpoint, phải kiểm tra cả:

- Request matcher trong SecurityFilterChain.
- @PreAuthorize, @PostAuthorize, @Secured và method interceptor.
- Authorization trong service/domain layer.
- Quyền sở hữu object, tenant và các kiểm tra nghiệp vụ.

Không xóa method-level security chỉ để làm endpoint public chạy qua test.

## 7. Nhiều SecurityFilterChain: luôn có fallback

Ứng dụng có thể tách chain theo API, actuator hoặc khu vực public. Mỗi chain cần có matcher rõ và thứ tự xác định.

Ví dụ ba nhóm:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers(
                            HttpMethod.GET,
                            "/api/catalog/public/**")
                        .permitAll()
                    .requestMatchers("/api/admin/**")
                        .hasAuthority("SCOPE_admin")
                    .anyRequest()
                        .authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .build();
}

@Bean
@Order(2)
SecurityFilterChain publicPagesChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/public/**", "/health")
            .authorizeHttpRequests(authorize -> authorize
                    .anyRequest().permitAll())
            .build();
}

@Bean
@Order(3)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(authorize -> authorize
                    .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .build();
}
```

Đây là minh họa cho ứng dụng Resource Server. Chain thứ nhất xử lý /api/**; chain thứ hai xử lý hai nhóm public page; chain cuối không có securityMatcher, nên bao phủ phần còn lại.

### 7.1. Những điểm cần kiểm tra khi review nhiều chain

- Chain có @Order xác định và không bị chain rộng hơn đứng trước chiếm request ngoài dự kiến.
- securityMatcher của từng chain không chồng lấn ngoài ý muốn.
- Chain public không vô tình bao phủ /api/admin/** hoặc /actuator/**.
- Chain fallback không bị thiếu.
- Mọi chain cần OAuth2 Resource Server đều cấu hình oauth2ResourceServer.
- Cấu hình CORS, CSRF, session policy và security headers phù hợp từng chain.
- Không có chain rỗng hoặc matcher quá rộng chỉ để mở một endpoint.

### 7.2. Chain public có thể không xác thực Bearer header

Trong ví dụ trên, publicPagesChain không cài oauth2ResourceServer. Vì vậy request tới /public/** được xử lý như anonymous theo chain đó; Bearer header không được Resource Server filter của chain này xác minh.

Nếu yêu cầu của ứng dụng là token sai phải bị từ chối ngay cả trên public route, hãy đưa endpoint vào chain có Resource Server filter và dùng permitAll ở authorization layer. Hãy ghi rõ contract và test đúng hành vi mong muốn.

### 7.3. Tránh chain matcher catch-all đứng quá sớm

Một chain có securityMatcher("/**") và @Order(1) sẽ khớp gần như mọi request, khiến các chain phía sau không được chọn. Nếu chain này có rule khác, các endpoint có thể nhận policy sai.

Chỉ dùng catch-all chain làm fallback cuối cùng hoặc khi ứng dụng thực sự chỉ có một chain.

## 8. Kiểm soát Actuator và management endpoints

Actuator là nguồn endpoint thường bị bỏ quên vì nó không nằm trong controller nghiệp vụ.

Ví dụ cấu hình expose:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

exposure.include quyết định endpoint nào được expose qua web; nó không tự quyết định endpoint đó public hay protected.

Một policy thường gặp:

| Actuator endpoint | Chính sách gợi ý |
| --- | --- |
| /actuator/health | Public hoặc internal-only, trả thông tin tổng quát. |
| /actuator/health/liveness | Chỉ mở theo nhu cầu orchestrator. |
| /actuator/health/readiness | Chỉ mở theo nhu cầu load balancer/orchestrator. |
| /actuator/info | Chỉ public nếu nội dung được duyệt. |
| /actuator/metrics | Protected/internal-only. |
| /actuator/prometheus | Internal network hoặc scrape identity riêng. |
| /actuator/env | Không public. |
| /actuator/configprops | Không public. |
| /actuator/heapdump | Không public. |
| /actuator/beans, /actuator/mappings | Protected; có thể tiết lộ cấu trúc nội bộ. |
| /actuator/loggers | Protected; có thể thay đổi mức log. |

### 8.1. Dùng EndpointRequest cho Actuator

Spring Security cung cấp matcher theo Actuator endpoint, tránh phụ thuộc hoàn toàn vào chuỗi URL:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;

@Bean
@Order(1)
SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
    return http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers(
                            EndpointRequest.to("health", "info"))
                        .permitAll()
                    .anyRequest()
                        .hasAuthority("SCOPE_ops"))
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .build();
}
```

Ví dụ giả định management endpoints dùng cùng Resource Server authentication. Nếu Actuator ở management port riêng hoặc dùng network identity khác, cấu hình chain và deployment boundary theo kiến trúc đó.

### 8.2. Health details không nên public

Health response có thể tiết lộ database name, hostname, dependency URL, trạng thái queue hoặc thông tin hạ tầng. Chỉ public trạng thái tối thiểu cần thiết. Cấu hình management.endpoint.health.show-details và health contributors theo yêu cầu vận hành.

### 8.3. Management port là một boundary bổ sung

Một management port riêng giúp giới hạn network exposure nhưng không thay authorization. Vẫn cần firewall/network policy chỉ cho phép scraper/orchestrator phù hợp, authentication/authorization cho endpoint nhạy cảm, kiểm tra ingress không route management port ra Internet và kiểm thử cấu hình production.

## 9. CORS preflight, OPTIONS và endpoint public

Browser có thể gửi CORS preflight trước request thực:

```http
OPTIONS /api/orders HTTP/1.1
Origin: https://shop.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
```

Preflight không phải request nghiệp vụ và thường không có Bearer token. Hãy cấu hình CORS để xử lý preflight trước bước authorization phù hợp:

```java
http
    .cors(Customizer.withDefaults())
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/catalog/public/**").permitAll()
        .anyRequest().authenticated());
```

Không nên mở toàn bộ OPTIONS trên mọi path chỉ để browser preflight chạy được. CORS phải giới hạn origin, methods và headers theo API contract.

### 9.1. CORS không phải authorization

CORS là chính sách browser kiểm soát việc JavaScript ở origin khác đọc response. Nó không ngăn curl, mobile app hoặc server-to-server client gọi API.

Một endpoint trả Access-Control-Allow-Origin không có nghĩa endpoint đã được bảo vệ. Ngược lại, permitAll không tự cấu hình CORS.

### 9.2. Test cả preflight và request thực

Với endpoint browser-facing, test:

1. OPTIONS preflight từ origin được phép.
2. OPTIONS preflight từ origin không được phép.
3. POST/PUT/PATCH/DELETE thực với Bearer token hợp lệ.
4. Request thực không có token.
5. Request thực có token thiếu scope.

Không chỉ test OPTIONS rồi kết luận method thay đổi dữ liệu được bảo vệ.

## 10. CSRF và endpoint public thay đổi trạng thái

permitAll chỉ cho phép authorization ở HTTP layer. Nó không tắt CSRF protection.

Với API chỉ nhận Bearer token trong Authorization header và không dùng cookie authentication, nhiều ứng dụng Resource Server stateless có thể disable CSRF cho API theo threat model đã xác định.

Nhưng nếu browser tự động gửi cookie/session để authenticate, endpoint public hoặc endpoint authenticated có thao tác thay đổi trạng thái vẫn cần được xem xét về CSRF.

Ví dụ:

```java
http
    .csrf(csrf -> csrf
        .ignoringRequestMatchers("/api/**"))
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/public/**").permitAll()
        .anyRequest().authenticated());
```

Đây chỉ là ví dụ khi /api/** thực sự dùng bearer header và không dựa vào cookie để authenticate. Không copy cấu hình này sang ứng dụng browser/session mà chưa đánh giá CSRF.

Một endpoint public dùng POST để đăng ký newsletter vẫn có thể bị abuse, spam hoặc CSRF tùy cách xác thực và tác động. Public không có nghĩa không cần rate limit, validation hoặc abuse controls.

## 11. Path matching: các biến thể dễ bị bỏ sót

Matcher chỉ an toàn khi semantics của nó khớp với route mà servlet thực sự nhận.

Các trường hợp cần rà soát:

- Trailing slash: /api/public và /api/public/.
- Path variable: /api/orders/{id}.
- Wildcard: /api/** và /api/*.
- HTTP method: GET so với POST/DELETE.
- Context path và servlet path.
- Reverse proxy rewrite hoặc prefix như /gateway/app.
- URL encoding, encoded slash và ký tự phân cách.
- Duplicate slash, matrix parameters và path normalization.
- Servlet mapping khác DispatcherServlet mặc định.

Không tự giả định /api/public/** có cùng semantics giữa AntPathMatcher, MVC matcher và PathPattern. Phiên bản Spring Framework/Spring Security và cấu hình matcher ảnh hưởng cách match.

### 11.1. Test path như ứng dụng thực sự nhận

Nếu ingress rewrite /shop/api/orders thành /api/orders, test ở MockMvc chỉ nhìn path sau rewrite. Cần thêm kiểm thử deployment/integration ở gateway để xác nhận external path không bypass policy.

Nếu ứng dụng có server.servlet.context-path hoặc custom servlet path, cấu hình matcher tương ứng và test path có context path thực tế.

### 11.2. Không dùng matcher substring

Tránh tự viết logic như:

```java
if (request.getRequestURI().contains("/public/")) {
    // Bypass authentication
}
```

Substring có thể match path ngoài dự kiến. Dùng request matcher rõ ràng và kiểm thử cả đường dẫn gần giống:

```text
/api/public/catalog
/api/public-admin/catalog
/api/admin/public/catalog
/api/publicity/catalog
```

Chỉ path được thiết kế public mới được phép anonymous.

## 12. Error dispatch và /error

Spring Boot có thể forward request lỗi tới /error. Đây là một dispatch khác với request ban đầu.

Khi review, phân biệt:

- Request trực tiếp tới /error.
- Error dispatch do servlet container tạo.
- Authorization rule áp dụng theo dispatcher type.
- Error response có thể tiết lộ exception, route hoặc thông tin nội bộ.

Nếu cần permit error dispatch để framework tạo response chuẩn, hãy giới hạn theo dispatcher type và kiểm tra behavior thực tế. Không mở mọi request tới /error chỉ vì ứng dụng có error page.

Ví dụ matcher theo dispatcher type:

```java
import jakarta.servlet.DispatcherType;

http.authorizeHttpRequests(authorize -> authorize
        .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
        .requestMatchers("/public/**").permitAll()
        .anyRequest().authenticated());
```

Rule trên chỉ minh họa cách giới hạn theo dispatcher type. Test riêng request trực tiếp tới /error và error dispatch; không giả định hai trường hợp có cùng policy.

## 13. Tự động liệt kê Spring MVC mappings

Có thể dùng RequestMappingHandlerMapping trong test để phát hiện controller route mới chưa được thêm vào security inventory.

Ví dụ skeleton cho Spring Framework 6:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

import java.util.Set;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class EndpointInventoryTest {

    @Autowired
    RequestMappingHandlerMapping handlerMapping;

    private static final Set<String> APPROVED_ROUTES = Set.of(
            "GET /api/catalog/public/**",
            "GET /api/orders/{id}",
            "POST /api/orders",
            "DELETE /api/admin/users/{id}");

    @Test
    void everyControllerMappingIsClassified() {
        Set<String> discovered = handlerMapping.getHandlerMethods()
                .keySet()
                .stream()
                .flatMap(info -> {
                    Set<String> patterns = info.getPatternValues();
                    Set<RequestMethod> methods =
                            info.getMethodsCondition().getMethods();

                    if (methods.isEmpty()) {
                        return patterns.stream()
                                .map(path -> "ALL " + path);
                    }

                    return patterns.stream()
                            .flatMap(path -> methods.stream()
                                    .map(method ->
                                            method.name() + " " + path));
                })
                .collect(Collectors.toSet());

        assertThat(discovered)
                .as("Every MVC route must have an explicit security classification")
                .containsAll(APPROVED_ROUTES);

        assertThat(APPROVED_ROUTES)
                .as("New MVC routes must be reviewed and added to the inventory")
                .containsAll(discovered);
    }
}
```

Đây là skeleton cần điều chỉnh theo route thật của ứng dụng. Mappings không chỉ có một method có thể được biểu diễn là ALL; nếu dùng params, headers, consumes hoặc produces để phân biệt handler, hãy đưa các điều kiện đó vào inventory khi chúng ảnh hưởng security policy.

### 13.1. Inventory test không thay thế security tests

Test trên chỉ phát hiện mapping MVC mới hoặc thiếu phân loại. Nó chưa chứng minh matcher trong security chain có đúng, endpoint public thực sự truy cập được anonymous, endpoint protected thực sự trả 401/403 khi cần, Actuator/servlet/functional route đã được liệt kê hoặc gateway/ingress không expose route khác.

Hãy kết hợp inventory test với MockMvc và deployment tests.

### 13.2. Mở rộng inventory ngoài MVC

Thêm nguồn route riêng cho Actuator endpoint discovery, RouterFunction/functional endpoints, Servlet registration và filter mapping, WebSocket handshake, management port và gateway/ingress route definitions.

Nếu ứng dụng có nhiều module, tổng hợp inventory của tất cả module vào một manifest review được.

## 14. Kiểm thử public endpoint bằng MockMvc

Một public endpoint phải truy cập được khi không có authentication:

```java
@Test
void publicCatalogCanBeReadWithoutAuthentication() throws Exception {
    mockMvc.perform(get("/api/catalog/public/items"))
            .andExpect(status().isOk());
}
```

Không cần dùng with(user(...)) hoặc with(jwt()) trong test này; mục tiêu là chứng minh anonymous access.

### 14.1. Kiểm thử theo danh sách route

Ví dụ parameterized test:

```java
static Stream<Arguments> publicRequests() {
    return Stream.of(
            arguments(get("/api/catalog/public/items")),
            arguments(get("/health")),
            arguments(get("/public/documentation"))
    );
}

@ParameterizedTest
@MethodSource("publicRequests")
void approvedPublicRoutesAllowAnonymous(
        MockHttpServletRequestBuilder request) throws Exception {

    mockMvc.perform(request)
            .andExpect(status().is2xxSuccessful());
}
```

Các route trong ví dụ phải tồn tại và trả 2xx theo contract thực tế. Nếu health endpoint có thể trả 503 khi dependency lỗi, assert security behavior riêng thay vì bắt buộc status 200.

### 14.2. Test method không được public

Nếu chỉ GET được public, POST cùng path phải yêu cầu authentication hoặc bị từ chối:

```java
@Test
void publicCatalogGetDoesNotMakePostPublic() throws Exception {
    mockMvc.perform(post("/api/catalog/public/items")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"name\":\"unexpected\"}"))
            .andExpect(status().isUnauthorized());
}
```

Kết quả có thể là 401 nếu path được xử lý bởi Resource Server chain và chưa authenticated; nếu method không được map hoặc bị method rule từ chối, kết quả có thể là 404/405 tùy thứ tự xử lý. Hãy chọn một route POST thật trong ứng dụng để kiểm tra policy thay vì dựa vào một path không tồn tại.

## 15. Kiểm thử protected endpoint

Với Resource Server dùng Bearer token, kiểm tra ba trạng thái:

1. Không có token → 401.
2. Token hợp lệ nhưng thiếu authority → 403.
3. Token hợp lệ và có authority → request được phép.

Ví dụ:

```java
@Test
void ordersRequireAuthentication() throws Exception {
    mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
}

@Test
void authenticatedUserWithoutReadScopeGetsForbidden() throws Exception {
    mockMvc.perform(get("/api/orders")
                    .with(jwt().authorities(
                            new SimpleGrantedAuthority(
                                    "SCOPE_profile:read"))))
            .andExpect(status().isForbidden());
}

@Test
void userWithReadScopeCanReadOrders() throws Exception {
    mockMvc.perform(get("/api/orders")
                    .with(jwt().authorities(
                            new SimpleGrantedAuthority(
                                    "SCOPE_orders:read"))))
            .andExpect(status().isOk());
}
```

jwt() phù hợp ở đây để kiểm tra authorization rules với principal đã được dựng sẵn. Nó không chứng minh chữ ký/JWKS/issuer của Bearer token; các phần đó cần signed-token integration tests riêng.

## 16. Kiểm tra token trên endpoint public

Nếu endpoint public nằm trong chain có Resource Server filter, cần quyết định rõ cách xử lý khi caller gửi token:

| Request | Hành vi thường gặp |
| --- | --- |
| Không có Authorization header | permitAll cho phép anonymous. |
| Bearer token hợp lệ | Authentication có thể được thiết lập; authorization vẫn cho phép. |
| Bearer token hết hạn/sai chữ ký | Authentication filter có thể trả 401 trước authorization. |
| Authorization header không theo Bearer scheme | Resource Server có thể bỏ qua tùy resolver; kiểm tra contract. |

Test hành vi đã chọn:

```java
@Test
void publicRouteRejectsInvalidBearerWhenResourceServerFilterIsPresent()
        throws Exception {

    mockMvc.perform(get("/api/catalog/public/items")
                    .header(
                            HttpHeaders.AUTHORIZATION,
                            "Bearer definitely-not-a-jwt"))
            .andExpect(status().isUnauthorized());
}
```

Test này chỉ đúng nếu public route nằm trong chain có Bearer Resource Server filter. Nếu route thuộc chain không cài Resource Server filter, Bearer header có thể không được xác thực và request vẫn public. Hãy ghi rõ hành vi này trong endpoint contract.

Không âm thầm bỏ qua token invalid để biến request thành anonymous trừ khi ứng dụng có optional-authentication design đã được review.

## 17. Kiểm tra endpoint không được liệt kê vẫn bị bảo vệ

Đây là test quan trọng để phát hiện chain gap.

Nếu dùng một fallback chain có anyRequest().authenticated(), một path chưa được khai báo nhưng vẫn đi vào application phải yêu cầu authentication trước khi đến handler:

```java
@Test
void unclassifiedPathStillHitsFallbackSecurityChain() throws Exception {
    mockMvc.perform(get("/__security_probe__/not-a-real-route"))
            .andExpect(status().isUnauthorized());
}
```

Với token hợp lệ, request có thể vượt authentication rồi trả 404 vì không có handler. Điều đó chứng minh fallback chain đã áp dụng trước bước MVC route resolution.

Test này cần được đặt trong test application context có cùng fallback chain với production. Nếu ứng dụng có nhiều servlet/context path, tạo probe cho từng boundary.

### 17.1. Không dùng 404 làm bằng chứng endpoint được bảo vệ

Một request không tồn tại có thể trả 404 do MVC mà không chứng minh security policy của route thật. Ngược lại, khi security filter chạy trước MVC, request không tồn tại có thể trả 401 nếu chưa authenticated.

Hãy test endpoint thật và test fallback riêng. Không dùng một kết quả 404 duy nhất để kết luận không có lỗ hổng.

## 18. Kiểm tra các path gần giống public path

Nếu /api/public/** được mở, hãy test các path có tên gần giống:

```text
GET /api/public/items
GET /api/public-admin/users
GET /api/admin/public/users
GET /api/publicity/items
POST /api/public/items
DELETE /api/public/items/123
```

Chỉ request đã được duyệt mới được anonymous. Các path khác phải theo protected fallback hoặc không tồn tại.

Có thể tạo parameterized tests với một danh sách negative cases:

```java
static Stream<Arguments> protectedLookalikeRequests() {
    return Stream.of(
            arguments(get("/api/public-admin/users")),
            arguments(get("/api/admin/public/users")),
            arguments(get("/api/publicity/items")),
            arguments(post("/api/public/items")),
            arguments(delete("/api/public/items/123"))
    );
}

@ParameterizedTest
@MethodSource("protectedLookalikeRequests")
void lookalikePathsDoNotInheritPublicAccess(
        MockHttpServletRequestBuilder request) throws Exception {

    mockMvc.perform(request)
            .andExpect(status().isUnauthorized());
}
```

Điều chỉnh negative cases theo route thực tế để mỗi request có ý nghĩa. Nếu method không tồn tại, hãy kiểm tra chain bằng request tới handler thật hoặc kiểm tra FilterChainProxy thay vì suy ra policy từ 404/405.

## 19. Test security headers trên public endpoints

Một endpoint permitAll vẫn nên nhận các security headers được cấu hình trong chain, chẳng hạn:

- X-Content-Type-Options.
- Cache-Control phù hợp.
- X-Frame-Options hoặc CSP theo loại ứng dụng.
- HSTS khi chạy HTTPS và cấu hình phù hợp.

Ví dụ:

```java
@Test
void publicEndpointStillReceivesSecurityHeaders() throws Exception {
    mockMvc.perform(get("/api/catalog/public/items"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "X-Content-Type-Options", "nosniff"));
}
```

Header cụ thể phụ thuộc Spring Security configuration và loại response. Nếu dùng web.ignoring, các header do Spring Security chain thêm sẽ không có; đây là một lý do khác để ưu tiên permitAll cho endpoint HTTP.

## 20. FilterChainProxy và cách xác định chain được chọn

Trong test hoặc debug, có thể inspect FilterChainProxy để xem chain nào được chọn cho một request. Đây là công cụ hỗ trợ xác định matcher/order; đừng để test phụ thuộc quá nhiều vào thứ tự nội bộ của toàn bộ filter nếu không cần.

Một kiểm tra ở mức khái niệm:

```java
@Autowired
FilterChainProxy springSecurityFilterChain;

MockHttpServletRequest request =
        new MockHttpServletRequest("GET", "/api/orders");

List<Filter> filters =
        springSecurityFilterChain.getFilters(request);

assertThat(filters).isNotEmpty();
```

API getFilters và cách tạo request phải phù hợp version Spring Security/Servlet. Kiểm tra cụ thể Bearer filter trong chain nếu đó là yêu cầu của test, nhưng ưu tiên integration test qua MockMvc để xác minh behavior đầu cuối.

### 20.1. Debug logging không phải giải pháp production

Spring Security debug mode có thể giúp quan sát filter chain khi phát triển. Không bật debug logging rộng trong production chỉ để tìm matcher vì request/header hoặc chi tiết nội bộ có thể xuất hiện trong log.

Khi debug:

- Dùng môi trường test/dev.
- Dùng dữ liệu giả.
- Giới hạn thời gian bật.
- Không capture Authorization header hoặc token.
- Tắt debug sau khi xác định vấn đề.

## 21. Endpoint OAuth/OIDC và callback

Một Resource Server thuần túy thường không tự expose mọi endpoint OAuth. Nếu cùng ứng dụng còn có OAuth2 Client login, Authorization Server hoặc OIDC Provider, endpoint protocol phải được phân loại riêng.

| Endpoint | Ý nghĩa | Cách review |
| --- | --- | --- |
| /oauth2/authorization/{registrationId} | Bắt đầu OAuth2 login | Public entry point theo login flow. |
| /login/oauth2/code/{registrationId} | Redirect callback từ Authorization Server | Phải xử lý state/correlation và protocol validation; không coi như business API thông thường. |
| /logout | Kết thúc session/login | Kiểm tra HTTP method, CSRF và logout contract. |
| /oauth2/token | Token Endpoint của Authorization Server | Chỉ có nếu app là AS; client authentication và grant policy bắt buộc theo profile. |
| /.well-known/openid-configuration | Provider metadata | Chỉ public nếu app đóng vai OIDC Provider và nội dung được thiết kế công khai. |
| /oauth2/jwks | Public signing keys | Có thể public khi app là issuer; không chứa private key. |

Không permitAll hàng loạt prefix /oauth2/** chỉ vì một callback hoặc metadata endpoint cần public. Mỗi endpoint protocol có contract riêng.

## 22. Static resources và tài liệu API

Static assets như CSS, JavaScript, ảnh và favicon thường không cần authentication. Có thể dùng permitAll:

```java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers(
                "/assets/**",
                "/favicon.ico",
                "/webjars/**")
            .permitAll()
        .anyRequest().authenticated());
```

Tuy nhiên, kiểm tra:

- Static directory không chứa backup, source map nhạy cảm, config hoặc file export.
- File upload/download không bị nhầm thành static asset public.
- API documentation UI và OpenAPI JSON có được public theo policy không.
- Swagger UI không làm lộ schema nội bộ hoặc endpoint admin.
- Cache headers không làm rò dữ liệu cá nhân giữa người dùng.

Đường dẫn /static/** có thể chứa cả nội dung public và private nếu ứng dụng tự phục vụ file. Không mở toàn bộ prefix chỉ vì một vài ảnh cần public.

## 23. Những nguồn exposure ngoài Spring Security

Một ứng dụng có security chain đúng vẫn có thể bị expose ngoài dự kiến bởi deployment:

- Ingress route trỏ thẳng tới service/port nội bộ.
- Gateway bỏ authentication cho path prefix sai.
- Reverse proxy rewrite path trước khi matcher kiểm tra.
- Management port được mở ra Internet.
- Kubernetes Service/NodePort/LoadBalancer expose port phụ.
- Static hosting bucket public.
- WebSocket endpoint có handshake policy riêng.
- Một servlet/filter được mount ở context path khác.

Rà soát phải kết hợp:

1. Route trong code.
2. SecurityFilterChain và matcher.
3. Actuator/application properties.
4. Gateway/ingress/proxy configuration.
5. Network exposure và port mapping.
6. Integration test qua URL/port mà client thực sự truy cập.

Đừng coi việc một route không xuất hiện trong RequestMappingHandlerMapping là bằng chứng nó không thể truy cập từ Internet.

## 24. Quy trình review endpoint công khai

Một quy trình thực tế có thể đi theo thứ tự:

1. **Thu thập:** xuất inventory từ MVC mappings, Actuator, functional routes, servlet registrations và gateway.
2. **Chuẩn hóa:** ghi mỗi route cùng HTTP method, context path và exposure.
3. **Phân loại:** public, authenticated, authority-protected, internal-only hoặc protocol-specific.
4. **Phê duyệt:** mỗi public route có owner và lý do.
5. **Ánh xạ:** xác định chain và matcher xử lý route.
6. **Kiểm tra fallback:** mọi request chưa phân loại vẫn được bảo vệ.
7. **Kiểm tra method/path:** negative cases cho method khác, path gần giống, trailing slash và context path.
8. **Kiểm tra layer bổ sung:** method security, CSRF, CORS, object authorization, rate limiting.
9. **Kiểm tra deployment:** gateway, ingress, management port và external routing.
10. **Tự động hóa:** inventory test, anonymous tests, protected tests và negative matcher tests chạy trong CI.

Khi endpoint mới được thêm, pull request cần cập nhật inventory và security test cùng lúc.

## 25. Ma trận kiểm thử bảo mật

| Case | Request | Credential | Kỳ vọng |
| --- | --- | --- | --- |
| PUB-01 | GET endpoint public đã duyệt | Không có | 2xx theo contract |
| PUB-02 | GET endpoint public trong chain có Bearer filter | Token hợp lệ | Được phép |
| PUB-03 | GET endpoint public trong chain có Bearer filter | Token sai | 401 theo policy |
| PROT-01 | GET endpoint protected | Không có | 401 |
| PROT-02 | GET endpoint protected | Token hợp lệ, thiếu scope | 403 |
| PROT-03 | GET endpoint protected | Token đúng scope | 2xx |
| PROT-04 | POST endpoint write | Token chỉ có read | 403 |
| PROT-05 | DELETE endpoint restricted | Token thiếu admin | 403 |
| MATCH-01 | Path gần giống public prefix | Không có | Không được public |
| MATCH-02 | Method khác trên public path | Không có | Không được public ngoài contract |
| CHAIN-01 | Request thuộc specialized chain | Theo policy chain | Đúng chain |
| CHAIN-02 | Request không thuộc specialized chain | Không có | Fallback vẫn bảo vệ |
| ACT-01 | GET health tổng quát | Không có | Theo policy health |
| ACT-02 | GET actuator/env | Không có | 401/403 hoặc không expose |
| CORS-01 | OPTIONS preflight origin hợp lệ | Không có | CORS response phù hợp |
| CORS-02 | OPTIONS preflight origin lạ | Không có | Không cấp CORS permission |
| CSRF-01 | Public state-changing endpoint có cookie context | Không có CSRF token | Bị từ chối nếu CSRF policy yêu cầu |
| ERR-01 | Error dispatch | Theo dispatcher policy | Error response an toàn |
| HDR-01 | GET endpoint public | Không có | Security headers theo cấu hình |
| GAP-01 | Request tới path chưa phân loại | Không có | Fallback yêu cầu authentication |

Status cụ thể phải theo contract của ứng dụng. Ví dụ endpoint không tồn tại có thể trả 404/405 thay vì 401 tùy thứ tự xử lý; hãy dùng endpoint thật để chứng minh authorization.

## 26. Những sai lầm thường gặp

1. **Chỉ review controller:** bỏ sót Actuator, servlet, functional routes, WebSocket và gateway.
2. **Chỉ ghi path mà quên method:** GET public có thể khiến nhóm mở nhầm POST/DELETE.
3. **Nhầm securityMatcher với requestMatchers:** một cái chọn chain, một cái chọn authorization rule bên trong chain.
4. **Cho rằng anyRequest().authenticated() bảo vệ toàn ứng dụng:** nó chỉ áp dụng trong chain đã chọn.
5. **Không có fallback chain:** request ngoài các matcher chuyên biệt có thể không đi qua Spring Security.
6. **Đặt catch-all chain quá sớm:** chain rộng có thể chiếm request của chain chuyên biệt.
7. **Dùng web.ignoring cho API public:** bỏ qua cả security filters và headers.
8. **Permit cả prefix rộng:** một route public có thể vô tình mở endpoint admin/private cùng prefix.
9. **Permit mọi OPTIONS:** bỏ qua CORS policy và có thể làm matcher quá rộng.
10. **Coi CORS là authorization:** CORS không bảo vệ API khỏi non-browser clients.
11. **Coi permitAll là bỏ qua method security:** @PreAuthorize và domain policy vẫn có thể từ chối.
12. **Coi health endpoint vô hại:** health details có thể tiết lộ hạ tầng.
13. **Tắt CSRF cho mọi endpoint:** không phù hợp nếu browser dùng cookie/session authentication.
14. **Chỉ test anonymous request:** bỏ sót behavior khi caller gửi token invalid trên public route.
15. **Chỉ test status 4xx:** không phân biệt authentication failure và authorization denial.
16. **Bật Spring Security debug trong production:** có thể lộ request/security details.
17. **Không test reverse proxy rewrite:** external path có thể khác path matcher nhận.
18. **Coi inventory test là security test đầy đủ:** inventory chỉ phát hiện route, không chứng minh policy.

## 27. Checklist hoàn tất review

- [ ] Có inventory đầy đủ route và HTTP method.
- [ ] Đã rà soát MVC, functional routes, Actuator, servlet, error, protocol và realtime endpoints.
- [ ] Đã rà soát ingress, gateway, reverse proxy, management port và context path.
- [ ] Mỗi endpoint có classification và owner.
- [ ] Mọi public endpoint có lý do và data exposure được duyệt.
- [ ] Public allowlist giới hạn method và path cụ thể.
- [ ] Rule cụ thể đứng trước rule tổng quát.
- [ ] Hiểu rõ chain nào được chọn cho từng request.
- [ ] Mỗi specialized chain có matcher/order rõ ràng.
- [ ] Có fallback chain bảo vệ phần còn lại.
- [ ] Không có matcher catch-all đứng sai thứ tự.
- [ ] Dùng permitAll cho phần lớn HTTP endpoints public.
- [ ] web.ignoring chỉ dùng cho trường hợp hẹp, có lý do.
- [ ] Đã kiểm tra behavior của Bearer token invalid trên public route.
- [ ] Đã kiểm tra method security và object/tenant authorization.
- [ ] CORS preflight được cấu hình theo origin/method/header allowlist.
- [ ] CSRF được đánh giá theo cách credential thực sự được gửi.
- [ ] Actuator endpoints được expose và bảo vệ riêng.
- [ ] Có tests cho anonymous, missing token, insufficient scope và authorized token.
- [ ] Có negative tests cho path gần giống và method khác.
- [ ] Có test chứng minh fallback chain bảo vệ path chưa phân loại.
- [ ] Có test inventory phát hiện route mới chưa được review.
- [ ] Security headers và error handling được kiểm tra trên public routes.

## 28. Câu hỏi tự kiểm tra

**1. securityMatcher dùng để làm gì?** Chọn SecurityFilterChain xử lý request.

**2. requestMatchers dùng để làm gì?** Chọn authorization rule bên trong chain đã được chọn.

**3. anyRequest().authenticated() có bảo vệ path ngoài securityMatcher không?** Không.

**4. Điều gì xảy ra khi không có SecurityFilterChain nào khớp?** Request có thể không đi qua Spring Security filter chain.

**5. Khi có nhiều chain, chain nào được chọn?** Chain đầu tiên theo thứ tự có matcher khớp request.

**6. Vì sao cần fallback chain?** Bảo vệ request không thuộc chain chuyên biệt.

**7. permitAll có bỏ qua security filters không?** Không; nó chỉ cho phép authorization ở rule đó.

**8. web.ignoring có khác permitAll không?** Có; request bị ignoring bỏ qua Spring Security filter chain.

**9. Public endpoint có thể trả 401 khi gửi token sai không?** Có, nếu Resource Server Bearer filter nằm trong chain và authentication thất bại trước authorization.

**10. permitAll có bỏ qua @PreAuthorize không?** Không.

**11. CORS có thay authentication/authorization không?** Không.

**12. Có nên permit mọi OPTIONS không?** Không; cấu hình CORS preflight theo policy cụ thể.

**13. exposure.include của Actuator có làm endpoint public không?** Không; nó chỉ expose endpoint qua web, security vẫn phải được cấu hình.

**14. Vì sao phải inventory theo method?** Cùng path có thể có GET public nhưng POST/DELETE cần quyền.

**15. Có thể chỉ dùng RequestMappingHandlerMapping để inventory mọi endpoint không?** Không; còn Actuator, servlet, functional, WebSocket và gateway routes.

**16. Vì sao test một path không tồn tại có thể chưa đủ?** Kết quả 404/405 không chứng minh policy của endpoint thật.

**17. Khi nào dùng web.ignoring?** Chỉ với tài nguyên thực sự không cần security chain và có đánh giá tác động.

**18. Vì sao phải test external path qua gateway?** Rewrite và ingress có thể làm path thực tế khác matcher trong ứng dụng.

**19. Security debug có nên bật ở production không?** Không; chỉ bật ngắn hạn ở môi trường kiểm soát với dữ liệu giả.

**20. Bằng chứng tốt nhất rằng không có security gap là gì?** Inventory đầy đủ, chain fallback rõ ràng, policy được phân loại và các integration tests chứng minh cả public lẫn protected behavior.

## 29. Tài liệu tham khảo

- **Spring Security Reference — Java Configuration / Multiple HttpSecurity instances:** cấu hình nhiều SecurityFilterChain, thứ tự và matcher. https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- **Spring Security Reference — Authorize HTTP Requests:** requestMatchers, permitAll, authenticated và authorization rules. https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- **Spring Security Reference — Web Security:** WebSecurityCustomizer và ignoring requests. https://docs.spring.io/spring-security/reference/servlet/architecture.html
- **Spring Boot Reference — Actuator Endpoints:** expose và cấu hình management endpoints. https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- **Spring Boot Reference — Actuator Security:** bảo vệ management endpoints. https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- **Spring Security Reference — CORS:** CORS processing trong security chain. https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- **Spring Security Reference — CSRF:** CSRF protection và cấu hình theo application architecture. https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- **Spring Security Reference — Testing MockMvc:** kiểm thử request authorization và security behavior. https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- **OWASP Authorization Cheat Sheet:** deny by default và kiểm tra quyền ở mọi request. https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- **OWASP Attack Surface Analysis Cheat Sheet:** inventory và rà soát attack surface. https://cheatsheetseries.owasp.org/cheatsheets/Attack_Surface_Analysis_Cheat_Sheet.html

## 30. Kết luận

Rà soát endpoint public là công việc kiểm kê toàn bộ bề mặt truy cập và chứng minh mỗi request đi qua một policy có chủ đích. Hãy lập inventory theo path và HTTP method, phân loại public/authenticated/restricted, xác định chain xử lý và giữ một fallback chain bảo vệ mọi request còn lại.

Trong Spring Security, securityMatcher chọn filter chain; requestMatchers chọn authorization rule bên trong chain. permitAll cho anonymous truy cập nhưng request vẫn đi qua security filters; web.ignoring bỏ qua toàn bộ chain và chỉ phù hợp với trường hợp hẹp. Nhiều chain phải có thứ tự rõ ràng, không để catch-all chain chiếm request ngoài dự kiến và không để request rơi khỏi mọi chain.

Cuối cùng, kết hợp inventory test với MockMvc tests cho public routes, protected routes, methods khác, token invalid, thiếu scope, path gần giống, Actuator và fallback. Kiểm tra thêm gateway, ingress, context path, CORS, CSRF và method security. Chỉ khi route mới được phát hiện, policy được phân loại và test chứng minh behavior ở đúng boundary thì nhóm mới có cơ sở tin rằng không còn endpoint vô tình bị bỏ sót.
