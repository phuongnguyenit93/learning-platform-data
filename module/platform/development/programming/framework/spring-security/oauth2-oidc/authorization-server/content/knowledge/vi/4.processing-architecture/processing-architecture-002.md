# Thứ tự filter chain, securityMatcher và requestMatcher

## 1. Vì sao thứ tự filter chain quan trọng với Authorization Server?

Khi triển khai **OAuth 2.0 / OpenID Connect Authorization Server** bằng **Spring Security** và **Spring Authorization Server** trong ứng dụng Spring Boot, một HTTP request có thể đi vào nhiều nhóm chức năng: endpoint cấp token, endpoint OIDC, trang đăng nhập người dùng, API nghiệp vụ hoặc tài nguyên tĩnh. Những nhóm này thường cần **cơ chế xác thực, phiên đăng nhập và chính sách bảo vệ khác nhau**.

Spring Security cho phép định nghĩa nhiều bean <code>SecurityFilterChain</code>. Tuy nhiên, một request **không chạy lần lượt qua tất cả các chain phù hợp**. <code>FilterChainProxy</code> chọn **chain đầu tiên có matcher khớp** trong danh sách đã sắp thứ tự, sau đó chạy các filter của chain ấy. Quy tắc này khiến việc đặt <code>@Order</code>, <code>securityMatcher</code> và <code>requestMatchers</code> đúng vị trí có ảnh hưởng trực tiếp tới tính đúng đắn và an toàn của Authorization Server.

Mục tiêu của bài:

1. Phân biệt **thứ tự giữa các SecurityFilterChain**, **thứ tự filter bên trong một chain** và **thứ tự luật phân quyền**.
2. Giải thích chính xác <code>securityMatcher</code>, <code>requestMatchers</code> và <code>anyRequest</code> được đánh giá ở đâu.
3. Cấu hình các chain riêng cho Spring Authorization Server, API Bearer token và giao diện đăng nhập.
4. Lần theo một request thực tế, chẩn đoán lỗi chain bị bắt nhầm, endpoint không được bảo vệ hoặc bị trả về 404/401/403 ngoài ý muốn.
5. Kiểm chứng thứ tự chain bằng các phép thử Spring Security, không chỉ nhìn vào cấu hình.

Ví dụ xuyên suốt: ứng dụng có **Authorization Server** ở <code>/oauth2/**</code> và các endpoint OIDC, **Orders API** ở <code>/api/orders/**</code>, cùng trang <code>/login</code> phục vụ đăng nhập bằng biểu mẫu.

## 2. Bức tranh tổng thể: request đi qua đâu?

Trong ứng dụng Spring MVC chạy trên Servlet, đường đi tổng quát như sau:

~~~mermaid
flowchart TD
    A["HTTP request đến Servlet container"] --> B["DelegatingFilterProxy: springSecurityFilterChain"]
    B --> C["FilterChainProxy"]
    C --> D{"Chọn SecurityFilterChain đầu tiên có matches(request) = true"}
    D --> E["Các security filter của chain được chọn"]
    D --> N["Không có chain khớp: request không được Spring Security bảo vệ"]
    E --> F{"Filter có xử lý hoặc kết thúc request?"}
    F -- "Có" --> G["Trả redirect / response / lỗi xác thực"]
    F -- "Không" --> H["DispatcherServlet / controller / tài nguyên đích"]
    N --> H
~~~

Các thành phần có vai trò khác nhau:

| Thành phần | Trách nhiệm |
| --- | --- |
| <code>DelegatingFilterProxy</code> | Nối cơ chế Servlet Filter của container với bean Spring tên <code>springSecurityFilterChain</code>. |
| <code>FilterChainProxy</code> | Giữ danh sách <code>SecurityFilterChain</code> và chọn **chain đầu tiên** phù hợp request. |
| <code>SecurityFilterChain</code> | Gồm một <code>RequestMatcher</code> quyết định chain có áp dụng hay không và danh sách filter theo thứ tự của chain đó. |
| Filter bảo mật | Thực hiện các công việc như quản lý security context, CSRF, xác thực client, xử lý OAuth 2.0/OIDC endpoint, xác thực Bearer token, xử lý exception hoặc phân quyền. |
| <code>AuthorizationFilter</code> | Thực thi chính sách được cấu hình bởi <code>authorizeHttpRequests</code>, khi request đã được chọn vào chain chứa filter này. |

Spring Authorization Server triển khai nhiều endpoint thông qua **security filter**, chẳng hạn <code>OAuth2AuthorizationEndpointFilter</code> và <code>OAuth2TokenEndpointFilter</code>. Một endpoint có thể được xử lý xong trong filter mà không đi đến controller Spring MVC.

Vì vậy, cần phân biệt:

- **Chain có khớp không?** Do matcher của <code>SecurityFilterChain</code> quyết định.
- **Filter nào chạy, theo thứ tự nào?** Do cấu hình filter của chain được chọn quyết định.
- **Request có được phép vào tài nguyên không?** Do các cơ chế xác thực, phân quyền và kiểm soát khác của chain quyết định.

## 3. Ba loại “thứ tự” dễ bị nhầm lẫn

### 3.1. Thứ tự giữa các SecurityFilterChain

Khai báo <code>@Order(1)</code>, <code>@Order(2)</code>, <code>@Order(3)</code> trên các bean <code>SecurityFilterChain</code> cho phép quy định chain nào được xem xét trước. **Giá trị thứ tự thấp hơn có mức ưu tiên cao hơn**.

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http) throws Exception {
    // Matcher hẹp cho các endpoint của Authorization Server
    // ...
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    // Matcher /api/**
    // ...
    return http.build();
}

@Bean
@Order(3)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    // Không đặt securityMatcher => chain bắt các request còn lại
    // ...
    return http.build();
}
~~~

<code>FilterChainProxy</code> duyệt theo thứ tự và dừng ở **chain đầu tiên khớp**. Nếu chain thứ nhất bắt tất cả request, chain thứ hai và thứ ba sẽ không có cơ hội xử lý request nào, dù rule bên trong các chain sau hoàn toàn đúng.

Trong cấu hình thực tế, đặt **matcher cụ thể lên trước** và **chain dự phòng bao quát ở sau cùng**. Đừng phụ thuộc vào thứ tự tình cờ của các bean nếu nhiều chain có thể khớp cùng đường dẫn.

### 3.2. Thứ tự filter *bên trong* một SecurityFilterChain

Sau khi chọn chain, Spring Security thực thi các filter của chain theo **thứ tự filter riêng do Spring Security quản lý**. Ví dụ, filter cần xây dựng security context thường phải chạy trước những bước sử dụng thông tin xác thực; cơ chế xác thực phải sẵn sàng khi luật phân quyền được áp dụng.

Các filter liên quan tới Authorization Server có thể bao gồm filter xác thực client, authorization endpoint, token endpoint và các endpoint bổ sung; vị trí thực tế phụ thuộc phiên bản Spring Security/Spring Authorization Server và những configurer đã bật. **Không coi sơ đồ ví dụ hoặc thứ tự liệt kê tên filter trong tài liệu là thứ tự cố định cho mọi phiên bản.**

<code>@Order</code> trên **bean <code>SecurityFilterChain</code>** chỉ sắp thứ tự giữa các chain, không sắp thứ tự các filter bên trong. Nếu phải chèn filter tùy biến, sử dụng các API phù hợp của <code>HttpSecurity</code>, ví dụ:

~~~java
http.addFilterBefore(customAuditFilter, AuthorizationFilter.class);
// Hoặc addFilterAfter(...), addFilterAt(...) khi có yêu cầu cụ thể.
~~~

Không thêm filter vào vị trí tùy ý chỉ để “chạy trước tất cả”; cần xác định nó phải chạy sau bước xác thực nào, có cần security context hay không, và có vô tình ghi log secret, authorization code hoặc access token không.

### 3.3. Thứ tự luật <code>requestMatchers</code> trong một chain

Trong <code>authorizeHttpRequests</code>, các luật được xét theo **thứ tự khai báo**; luật khớp đầu tiên quyết định yêu cầu phân quyền.

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.write")
    .anyRequest().denyAll()
);
~~~

<code>anyRequest()</code> áp dụng cho **những request còn lại trong chain hiện tại**. Không đặt <code>anyRequest()</code> trước các rule cụ thể. Với endpoint cùng path nhưng khác HTTP method, nên phân biệt method rõ ràng như ví dụ trên.

Ba loại thứ tự có thể cùng tồn tại:

| Cấp | Cấu hình thường gặp | Tác động |
| --- | --- | --- |
| Chọn chain | <code>@Order</code> + <code>securityMatcher</code> | Chain nào chịu trách nhiệm với request |
| Chạy filter | Thứ tự filter do framework/configurer quản lý | Xác thực, xử lý endpoint, phân quyền diễn ra như thế nào |
| Chọn luật | <code>requestMatchers(...)</code> trong <code>authorizeHttpRequests</code> | Điều kiện cho phép/từ chối trong chain đã được chọn |

## 4. <code>securityMatcher</code> và <code>requestMatchers</code>: khác nhau ở đâu?

### 4.1. <code>securityMatcher</code> quyết định phạm vi cả chain

~~~java
http.securityMatcher("/api/**");
~~~

Lệnh này tạo hoặc thiết lập matcher để **chỉ các request API** đi qua chain đang cấu hình. Khi đường dẫn không khớp, <code>FilterChainProxy</code> tiếp tục tìm chain tiếp theo. Các filter và luật phân quyền của chain hiện tại **không được thực thi** cho request không khớp.

Nếu không khai báo <code>securityMatcher</code>, chain thường có matcher mặc định khớp mọi request. Vì vậy, một chain không có matcher rõ ràng đặt ở vị trí ưu tiên cao có thể “nuốt” toàn bộ các chain sau.

<code>securityMatcher</code> cũng nhận một <code>RequestMatcher</code> được tạo riêng, ví dụ matcher do Spring Authorization Server cung cấp hoặc một tổ hợp <code>OrRequestMatcher</code>. Không nên tự đoán rằng tất cả OAuth/OIDC endpoint đều nằm trong một mẫu path chung.

### 4.2. <code>requestMatchers</code> chọn luật phân quyền, không chọn chain

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    );
~~~

Đối với <code>GET /api/public/ping</code>, chain API được chọn trước; bên trong chain, luật <code>/api/public/**</code> cho phép truy cập mà không cần đăng nhập. Điều này **không có nghĩa filter bảo mật bị bỏ qua**: các filter áp dụng cho chain vẫn được thực thi; <code>permitAll()</code> chỉ thể hiện quyết định phân quyền cho request.

Đối với <code>GET /login</code>, chain API không khớp; dù có thêm <code>.requestMatchers("/login").permitAll()</code> **bên trong chain API**, rule đó cũng không bao giờ được áp dụng cho <code>/login</code>.

### 4.3. Phân biệt với các RequestMatcher khác

<code>RequestMatcher</code> là interface tổng quát có phương thức <code>matches(HttpServletRequest)</code>. Nó được sử dụng ở nhiều tầng:

- <code>http.securityMatcher(...)</code>: matcher của **cả SecurityFilterChain**.
- <code>authorizeHttpRequests().requestMatchers(...)</code>: matcher của **luật phân quyền**.
- Matcher bên trong filter xác thực: ví dụ filter xử lý <code>/oauth2/token</code> chỉ hành động trên request endpoint thích hợp.
- Matcher của exception handling hoặc CSRF: xác định cách xử lý **một nhóm request cụ thể**.

Đừng coi hai method có từ “matcher” là thay thế cho nhau. Chúng có cùng nền tảng đối sánh request nhưng khác **vị trí trong quá trình xử lý**.

### 4.4. Bảng tình huống

Giả sử có chain thứ nhất <code>securityMatcher("/api/**")</code> và chain thứ hai dự phòng khớp mọi request:

| Request | Chain được chọn | Luật đánh giá |
| --- | --- | --- |
| <code>GET /api/orders/42</code> | API | Rule GET <code>/api/orders/**</code> |
| <code>POST /api/orders</code> | API | Rule POST <code>/api/orders</code> |
| <code>GET /login</code> | Dự phòng | Rule trong chain dự phòng |
| <code>POST /oauth2/token</code> | Dự phòng nếu không có chain AS trước đó | Không có filter cấp token của AS nếu chưa cấu hình chain đó |

Hàng cuối là một lỗi cấu hình quan trọng: **thêm <code>permitAll()</code> cho <code>/oauth2/token</code> trong chain dự phòng không tự tạo ra token endpoint**. Endpoint được cung cấp bởi các filter của Spring Authorization Server và phải nằm trong chain chứa configurer đó.

## 5. Thiết kế chain cho Spring Authorization Server

### 5.1. Vì sao nên tách Authorization Server khỏi chain giao diện?

Authorization Server có cả request từ **trình duyệt** và **máy khách OAuth 2.0**:

- <code>GET /oauth2/authorize</code>: cần phiên đăng nhập của người dùng; có thể chuyển hướng đến <code>/login</code>.
- <code>POST /oauth2/token</code>: client đổi authorization code, gửi refresh token hoặc dùng grant thích hợp; cần xác thực client và xử lý theo giao thức OAuth 2.0.
- Các endpoint metadata/JWK/OIDC: có yêu cầu giao thức và mức bảo vệ riêng.
- <code>/login</code>: thường được cung cấp bởi <code>formLogin</code> ở **chain giao diện**, không phải token endpoint.

Nếu dồn tất cả vào chain giao diện với cấu hình giống nhau, request token có thể nhận HTML redirect đăng nhập thay vì phản hồi giao thức; ngược lại, nếu ép toàn hệ thống thành stateless Bearer API, quá trình người dùng đăng nhập tương tác có thể không hoạt động như mong đợi.

### 5.2. Sử dụng <code>getEndpointsMatcher()</code> của Authorization Server

Spring Authorization Server có <code>OAuth2AuthorizationServerConfigurer</code> và matcher của tập endpoint mà configurer quản lý:

~~~java
OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
    OAuth2AuthorizationServerConfigurer.authorizationServer();

http
    .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
    .with(authorizationServerConfigurer, authorizationServer ->
        authorizationServer.oidc(Customizer.withDefaults())
    );
~~~

Đây là **cách biểu đạt phạm vi chính xác hơn** so với <code>securityMatcher("/oauth2/**")</code>, bởi một số endpoint OIDC/metadata có thể dùng path như <code>/.well-known/openid-configuration</code>, <code>/userinfo</code> hoặc <code>/connect/logout</code>, và các path có thể được tùy chỉnh bằng <code>AuthorizationServerSettings</code>.

Matcher do Authorization Server cung cấp phản ánh những endpoint mà configurer đã cấu hình. Khi bật OIDC, phải tính đến các endpoint OIDC liên quan; không giả định mọi endpoint có sẵn hoặc được bật mặc định ở mọi phiên bản.

### 5.3. Ví dụ ba chain: Authorization Server, API, ứng dụng Web

Đoạn dưới là cấu hình minh họa cho ứng dụng **Spring Security Servlet** với phong cách API Spring Authorization Server hỗ trợ <code>OAuth2AuthorizationServerConfigurer.authorizationServer()</code> và <code>HttpSecurity.with(...)</code>. Các <code>import</code> được lược bỏ để tập trung vào thứ tự. Hãy đối chiếu API với phiên bản thực tế và cấu hình thêm các bean nền tảng: registered client, authorization/consent service, khóa ký và <code>JwtDecoder</code> nếu dùng endpoint OIDC/JWT.

~~~java
@Configuration
@EnableWebSecurity
public class SecurityChainsConfiguration {

    // Chain 1: các endpoint do Authorization Server quản lý.
    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, as ->
                as.oidc(Customizer.withDefaults())
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated()
            )
            .exceptionHandling(exceptions -> exceptions
                .defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)
                )
            )
            // Phục vụ những endpoint OIDC cần Bearer access token,
            // ví dụ UserInfo khi endpoint này được bật.
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    // Chain 2: API nghiệp vụ chỉ nhận Bearer token.
    @Bean
    @Order(2)
    SecurityFilterChain apiSecurityFilterChain(
            HttpSecurity http) throws Exception {

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            // Chỉ tắt CSRF trong chain API này nếu API thực sự chỉ
            // sử dụng Bearer token, không xác thực bằng cookie/session.
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    // Chain 3: giao diện đăng nhập và các trang còn lại.
    @Bean
    @Order(3)
    SecurityFilterChain applicationSecurityFilterChain(
            HttpSecurity http) throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Đọc cấu hình theo từng trách nhiệm:**

1. Chain **thứ nhất** giữ các filter OAuth 2.0/OIDC của Authorization Server và các chính sách endpoint giao thức. <code>getEndpointsMatcher()</code> giới hạn đúng phạm vi. Khi request trình duyệt chưa xác thực cần đăng nhập, entry point chuyển hướng đến <code>/login</code>.
2. Chain **thứ hai** chỉ khớp <code>/api/**</code>, yêu cầu Bearer token JWT và authority phù hợp từng route. Cấu hình stateless/CSRF ở đây được giới hạn ở API **chỉ dùng Bearer token**. Nếu API chấp nhận cookie/session hoặc có các cơ chế xác thực tự động khác của trình duyệt, phải thiết kế lại chống CSRF.
3. Chain **thứ ba** không đặt <code>securityMatcher</code> nên đóng vai trò **fallback**; <code>formLogin</code> cung cấp cơ chế đăng nhập cần thiết cho luồng authorization code tương tác.

<code>oauth2ResourceServer().jwt()</code> ở chain thứ nhất phục vụ những endpoint OIDC cần đọc Bearer token; ở chain API, nó xác thực access token gọi Orders API. Đây là hai phạm vi bảo vệ khác nhau dù có thể cùng sử dụng decoder. Với API cần giới hạn audience, hãy cấu hình <code>JwtDecoder</code> và <code>OAuth2TokenValidator</code> phù hợp; **việc chọn đúng chain không thay cho việc kiểm tra issuer, audience, thời hạn và scope**.

Ví dụ giả định có một <code>JwtDecoder</code> và nguồn khóa phù hợp với Authorization Server. Nếu Authorization Server và Resource Server tách thành hai ứng dụng, mỗi ứng dụng có cấu hình chain của riêng mình; không cần sao chép cả ba chain vào mọi dịch vụ.

### 5.4. Tại sao <code>/login</code> không thuộc chain Authorization Server?

Khi người dùng chưa có session gửi <code>GET /oauth2/authorize</code>, filter xử lý giao thức có thể yêu cầu xác thực. Entry point cho trình duyệt chuyển hướng đến <code>/login</code>. Trình duyệt gửi request mới:

1. <code>/login</code> **không khớp** matcher endpoint của Authorization Server, vì đây là trang đăng nhập ứng dụng.
2. Request tiếp tục qua chain API nhưng cũng không khớp <code>/api/**</code>.
3. Chain Web dự phòng khớp và <code>formLogin</code> xử lý trang đăng nhập và credential.
4. Sau khi đăng nhập thành công, trình duyệt quay lại quá trình <code>/oauth2/authorize</code> theo cơ chế lưu request/redirect phù hợp.

Nếu chỉ đăng ký Authorization Server chain mà không có chain tương ứng cho trang đăng nhập, một chuyển hướng đến <code>/login</code> chưa chắc hoạt động. Nếu tự đặt trang đăng nhập là <code>/signin</code>, phải cấu hình <code>loginPage</code>, route, quyền truy cập công khai và đường dẫn xử lý form cho khớp với chain giao diện.

### 5.5. Đường đi của năm request

~~~mermaid
flowchart LR
    R["Request"] --> AS{"Order 1: AS endpoints?"}
    AS -- "Có" --> A["AS chain: OAuth2/OIDC filters"]
    AS -- "Không" --> API{"Order 2: /api/**?"}
    API -- "Có" --> B["API chain: Bearer + scope"]
    API -- "Không" --> C["Order 3: Web chain: formLogin"]
~~~

| Request | Chain đầu tiên khớp | Xử lý chủ yếu |
| --- | --- | --- |
| <code>GET /oauth2/authorize</code> | Authorization Server | Authorization endpoint, yêu cầu người dùng đăng nhập khi cần |
| <code>POST /oauth2/token</code> | Authorization Server | Client authentication, token endpoint và grant xử lý |
| <code>GET /.well-known/openid-configuration</code> | Authorization Server nếu OIDC metadata endpoint được bật | Cung cấp discovery metadata theo chính sách endpoint |
| <code>GET /login</code> | Web | Trang đăng nhập/form login |
| <code>GET /api/orders/42</code> | API | Kiểm tra Bearer token, scope và quyền với order |

Trong một request, không tồn tại chuỗi “AS chain chạy xong rồi chuyển sang API chain”. Chuyển hướng từ <code>/oauth2/authorize</code> đến <code>/login</code> là **một HTTP request mới**, nên quá trình chọn chain chạy lại.

## 6. Luồng chi tiết của Authorization Code + PKCE

Hãy xét client <code>orders-web</code> bắt đầu Authorization Code Flow có PKCE:

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant P as FilterChainProxy
    participant AS as Authorization Server chain
    participant W as Web chain
    participant C as OAuth Client
    B->>P: GET /oauth2/authorize?...
    P->>AS: Chọn chain theo endpoints matcher
    AS-->>B: Redirect /login nếu chưa xác thực
    B->>P: GET /login
    P->>W: Chọn fallback Web chain
    W-->>B: Hiển thị trang đăng nhập
    B->>P: POST /login + CSRF token
    P->>W: Xác thực form và tạo phiên
    W-->>B: Redirect về authorization request
    B->>P: GET /oauth2/authorize?...
    P->>AS: Chain AS; xác thực/consent/policy
    AS-->>B: Redirect client với authorization code
    C->>P: POST /oauth2/token + code + code_verifier
    P->>AS: Chain AS; xác thực client và grant
    AS-->>C: Access token / ID Token nếu OIDC
~~~

Từ góc nhìn filter chain:

- PKCE, kiểm tra client, redirect URI, authorization code và các yêu cầu OIDC là trách nhiệm của **các thành phần giao thức** được kích hoạt trong chain AS, không phải điều kiện <code>requestMatchers().authenticated()</code> tự kiểm tra hết.
- <code>authorizeHttpRequests().anyRequest().authenticated()</code> ở chain AS là lớp chính sách tổng quát. Nó không thay thế bộ lọc dành riêng cho endpoint và không phải lý do để tự ý <code>permitAll()</code> cho token endpoint.
- Các request đăng nhập sử dụng **chain Web**, thường có session và CSRF phù hợp cho form. Không vô hiệu hóa CSRF toàn ứng dụng để sửa lỗi POST ở một endpoint OAuth.
- <code>POST /oauth2/token</code> là một request **mới từ client**, thường không có phiên trình duyệt của người dùng; việc xác thực client/grant nằm trong cơ chế của Authorization Server.

Luồng thực tế có thể khác tùy loại client, phương thức xác thực client, yêu cầu consent, phương thức login và endpoint được bật. Sơ đồ mô tả **đường chọn chain**, không liệt kê tất cả thông điệp giao thức.

## 7. Xây dựng matcher đúng cho nhiều đường dẫn

### 7.1. Không thay matcher AS bằng <code>"/oauth2/**"</code>

Một cấu hình dễ mắc:

~~~java
// Minh họa lỗi: chỉ bắt /oauth2/**, bỏ sót những endpoint OIDC/metadata khác.
http
    .securityMatcher("/oauth2/**")
    .with(authorizationServerConfigurer, configurer ->
        configurer.oidc(Customizer.withDefaults()));
~~~

Hậu quả: <code>/.well-known/openid-configuration</code>, <code>/userinfo</code> hoặc các endpoint tùy biến ngoài <code>/oauth2/**</code> có thể rơi sang chain khác, không đi qua đúng filter endpoint. Sửa bằng <code>authorizationServerConfigurer.getEndpointsMatcher()</code> và đối chiếu danh sách endpoint thực tế của phiên bản, <code>AuthorizationServerSettings</code> và các tính năng đã bật.

### 7.2. Cấu hình một chain cho nhiều nhóm API

Khi thật sự cần một chain bao phủ nhiều phạm vi, có thể dùng matcher kết hợp:

~~~java
RequestMatcher apiEndpoints = new OrRequestMatcher(
    new AntPathRequestMatcher("/api/**"),
    new AntPathRequestMatcher("/internal/**")
);

http.securityMatcher(apiEndpoints);
~~~

Ví dụ cho thấy ý nghĩa **OR** của các matcher. Trong phiên bản Spring Security mới, hãy ưu tiên matcher URL/path phù hợp stack MVC/Servlet đang dùng; một số matcher cũ như <code>AntPathRequestMatcher</code> đã bị deprecate trong các phiên bản mới và có hướng thay thế bằng <code>PathPatternRequestMatcher</code>. Không trộn lẫn nhiều cơ chế đối sánh đường dẫn khi chưa xác định rõ <code>servletPath</code> và context path.

Nhiều phiên bản còn hỗ trợ cú pháp <code>securityMatcher("/api/**", "/internal/**")</code>. Trong codebase lớn, một <code>RequestMatcher</code> được đặt tên rõ ràng thường dễ kiểm thử và kiểm soát hơn.

### 7.3. Đường dẫn, servlet path và context path

Ví dụ ứng dụng deploy dưới context path <code>/identity</code>, nên URL bên ngoài là <code>/identity/oauth2/token</code>. Trong Servlet Security, nhiều matcher URL được đánh giá trên path tương ứng **không bao gồm context path**. Thêm <code>/identity</code> một cách máy móc vào mẫu <code>"/oauth2/**"</code> có thể khiến matcher không khớp.

Nếu ứng dụng dùng servlet path riêng, nhiều servlet hoặc có reverse proxy thay đổi prefix, cơ chế đối sánh có thể khác nhau theo matcher và phiên bản framework. Phải kiểm tra **requestURI, contextPath, servletPath, pathInfo**, cấu hình forwarding headers và cách match được lựa chọn; viết integration test dùng đúng cấu hình deploy thay vì suy từ URL người dùng thấy.

### 7.4. <code>permitAll</code> không đồng nghĩa bỏ qua bảo mật

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/assets/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Các request tài nguyên tĩnh vẫn đi qua chain được chọn. Nhờ đó, các security header và filter bảo mật có thể tiếp tục được áp dụng. Trái lại, cấu hình kiểu <code>web.ignoring()</code> loại request ra khỏi chuỗi Spring Security, chỉ nên dùng khi thật sự có lý do và hiểu hệ quả. Đối với endpoint ứng dụng cần công khai, thường ưu tiên <code>permitAll()</code>.

## 8. Các lỗi cấu hình phổ biến

### Lỗi 1: Chain bao quát được đặt đầu tiên

~~~java
@Bean
@Order(1)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(authorize ->
        authorize.anyRequest().authenticated());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {
    // Các filter Authorization Server
    // ...
    return http.build();
}
~~~

Chain Web có matcher mặc định khớp mọi request, nên Authorization Server chain **không bao giờ được chọn**. Sửa bằng cách đặt AS chain matcher hẹp ở vị trí ưu tiên cao và fallback Web ở cuối.

### Lỗi 2: Đặt luật API ở bên trong chain chỉ khớp AS

~~~java
http
    .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
        .anyRequest().authenticated()
    );
~~~

Rule <code>/api/orders/**</code> không được sử dụng khi request API không khớp matcher của chain AS. Cần một chain API riêng (hoặc tổ chức lại phạm vi của chain một cách có chủ đích).

### Lỗi 3: Dùng <code>permitAll()</code> để “mở” token endpoint

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/oauth2/token").permitAll()
    .anyRequest().authenticated()
);
~~~

Đây chỉ là rule phân quyền; nó **không tạo ra** <code>OAuth2TokenEndpointFilter</code>, không tự kích hoạt kiểm tra client hoặc grant, và không thay thế cấu hình Authorization Server. Ngược lại, tùy ý mở quyền endpoint giao thức có thể phá vỡ giả định bảo mật. Sử dụng configurer AS đúng và để cơ chế giao thức xử lý các yêu cầu đặc thù.

### Lỗi 4: Ép mọi request vào cấu hình stateless API

~~~java
http
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .csrf(csrf -> csrf.disable());
~~~

Nếu đặt chính sách này vào chain bao quát cả trang đăng nhập, luồng Authorization Code dựa trên phiên trình duyệt có thể bị ảnh hưởng; việc tắt CSRF cho form login cũng không phù hợp. Tách trách nhiệm theo chain và chỉ áp dụng stateless/CSRF exception tại nơi đã xác định mô hình xác thực.

### Lỗi 5: Đổi thứ tự filter bằng <code>@Order</code> của chain

<code>@Order(1)</code> trên một <code>SecurityFilterChain</code> không đưa một custom filter lên trước <code>OAuth2ClientAuthenticationFilter</code> hoặc <code>AuthorizationFilter</code> bên trong. Cần xác định vị trí bằng API thêm filter của <code>HttpSecurity</code> và hiểu tác dụng phụ với session/security context.

### Lỗi 6: Phủ tất cả endpoint bằng một mẫu path và quên OIDC

<code>securityMatcher("/oauth2/**")</code> bỏ qua các endpoint có đường dẫn khác nếu cấu hình AS/OIDC thực sự cần chúng. Dùng matcher từ configurer và kiểm tra khi bật/tắt endpoint, thay đổi <code>AuthorizationServerSettings</code>.

### Lỗi 7: Không có chain dự phòng

Nếu chỉ cấu hình AS chain với matcher hạn chế mà không có chain phù hợp cho <code>/login</code> hoặc route khác, các route không khớp **không được bảo vệ bởi Spring Security**. Chúng có thể trả 404 do ứng dụng không có route, nhưng 404 không chứng minh rằng route đã được bảo vệ. Xác định rõ chain cho mọi vùng URL dự kiến và có fallback khi cần.

### Lỗi 8: Đánh giá 401/403 mà không xác định chain

HTTP 401 hoặc 403 có thể xuất phát từ các bước rất khác nhau. Một request trả 302 đến <code>/login</code> cũng không chứng tỏ đã đi qua Authorization Server chain. Cần kiểm tra **chain nào được chọn, filter nào xử lý và request matcher của filter đó có khớp** trước khi sửa rule phân quyền.

## 9. Cách chẩn đoán request đi qua chain nào

### 9.1. Xem dấu vết Spring Security trong môi trường phát triển

Có thể bật logging để quan sát quá trình chọn chain và các filter liên quan:

~~~properties
# Chỉ bật khi chẩn đoán trong môi trường phát triển.
logging.level.org.springframework.security=TRACE
~~~

Tùy phiên bản, log từ <code>FilterChainProxy</code> có thể hiển thị request đang được bảo vệ và quá trình kiểm tra matcher. Nên xem thêm log của Spring Authorization Server khi cần truy vết xử lý endpoint. Tránh bật logging chi tiết ở production: request OAuth 2.0 có thể chứa credential, code hoặc token và log có thể làm lộ thông tin nhạy cảm.

Khi thấy <code>/oauth2/token</code> bị trả về HTML login page, kiểm tra theo thứ tự:

1. AS chain đã được đăng ký và đặt trước fallback chưa?
2. Matcher <code>getEndpointsMatcher()</code> của AS có khớp token endpoint đang cấu hình không?
3. Có chain khác với matcher rộng bắt request trước không?
4. Endpoint filter AS có được thêm đúng vào chain không?
5. Response phát sinh từ filter xác thực client, endpoint OAuth hay entry point mặc định?

### 9.2. Kiểm thử trực tiếp chain đầu tiên khớp

Với Spring Security Test, có thể dựng <code>MockHttpServletRequest</code> rồi xác định chain đầu tiên khớp trong <code>FilterChainProxy</code>. Ví dụ giả định đã nạp cấu hình ba chain ở trên và test dùng AssertJ/JUnit:

~~~java
@Autowired
FilterChainProxy springSecurityFilterChain;

private SecurityFilterChain firstMatchingChain(
        String method, String path) {

    MockHttpServletRequest request =
        new MockHttpServletRequest(method, path);
    request.setServletPath(path);

    return springSecurityFilterChain.getFilterChains().stream()
        .filter(chain -> chain.matches(request))
        .findFirst()
        .orElseThrow(() -> new AssertionError(
            "No security chain matches " + method + " " + path));
}

@Test
void tokenEndpointUsesAuthorizationServerChain() {
    SecurityFilterChain chain =
        firstMatchingChain("POST", "/oauth2/token");

    assertThat(chain.getFilters()).anyMatch(
        filter -> filter instanceof OAuth2TokenEndpointFilter
    );
}

@Test
void apiRequestUsesApiChain() {
    SecurityFilterChain chain =
        firstMatchingChain("GET", "/api/orders/42");

    assertThat(chain.getFilters())
        .anyMatch(filter ->
            filter instanceof BearerTokenAuthenticationFilter)
        .noneMatch(filter ->
            filter instanceof OAuth2TokenEndpointFilter);
}

@Test
void loginRequestUsesWebChain() {
    SecurityFilterChain chain =
        firstMatchingChain("POST", "/login");

    assertThat(chain.getFilters()).anyMatch(
        filter -> filter instanceof UsernamePasswordAuthenticationFilter
    );
}
~~~

Đây là kiểm thử **định tuyến chain và thành phần filter**, không phải kiểm thử đầy đủ OAuth 2.0. Cần thêm integration test với <code>MockMvc</code> hoặc HTTP client thực, cấu hình context/servlet path tương ứng và kiểm tra hành vi: redirect authorization, xử lý token request, client authentication, CSRF/form login, xác minh JWT, issuer/audience/scope và quyền API.

Nếu muốn xác minh một filter thực sự đã xử lý request, cần thực hiện request và kiểm tra response hoặc hiệu ứng mong đợi. Việc filter **có mặt** trong chain chỉ xác nhận thành phần được gắn vào chain, chưa chứng minh matcher riêng của filter đã kích hoạt hay token đã được kiểm tra.

### 9.3. Ma trận kiểm thử tối thiểu

| Tình huống | Điều cần xác minh |
| --- | --- |
| <code>GET /oauth2/authorize</code> chưa đăng nhập | Vào AS chain; điều hướng đăng nhập đúng; không rơi vào API chain |
| <code>POST /oauth2/token</code> thiếu thông tin client hợp lệ | Vào AS chain; nhận phản hồi lỗi giao thức phù hợp, không phải HTML login |
| OIDC discovery endpoint được bật | Khớp AS chain và trả metadata đúng cấu hình |
| <code>GET /login</code>, <code>POST /login</code> | Vào Web chain; xử lý form, session và CSRF theo cấu hình |
| <code>GET /api/orders/42</code> không có Bearer token | Vào API chain; từ chối nếu cần authentication |
| Access token đúng scope nhưng sai audience | Resource Server từ chối token (nếu cấu hình audience validator) |
| Access token đúng audience nhưng thiếu scope | API từ chối quyền cần thiết |
| Access token đúng scope/audience nhưng không có quyền với order | Service/domain từ chối theo quyền dữ liệu |
| Thay đổi context path / servlet path | Matcher vẫn chọn đúng chain khi chạy dưới đường dẫn thực tế |
| Route không xác định, ví dụ <code>/unknown</code> | Fallback chain áp dụng trước khi xử lý 404 hay policy khác |

## 10. Những điểm an toàn cần nhớ

**Chọn chain đúng là điều kiện cần, không phải toàn bộ bảo mật OAuth 2.0/OIDC.** Cần phối hợp nhiều tầng:

- **Endpoint routing:** matcher của Authorization Server chọn đúng chain, kể cả các endpoint OIDC đang bật.
- **Client authentication và grant validation:** filter/component giao thức kiểm tra loại grant, client, redirect URI, PKCE, code, token... theo chức năng endpoint.
- **User authentication và session:** chain Web xử lý đăng nhập tương tác và chống CSRF khi cần.
- **Access token validation:** Resource Server kiểm tra token, issuer, thời hạn, audience và các điều kiện profile phù hợp.
- **Authorization:** scope/authority hạn chế hành động; tầng nghiệp vụ tiếp tục kiểm tra chủ sở hữu, tổ chức, tenant hoặc đối tượng dữ liệu cụ thể.

Một access token có chữ ký hợp lệ không tự động được dùng ở mọi API. Một request có <code>permitAll()</code> cũng không đồng nghĩa loại bỏ mọi filter kiểm tra. Và một route trả 404 chưa chắc đã đi qua bất kỳ chain bảo mật nào.

## 11. Bài tập tự thực hành

Giả sử ứng dụng có các route:

- Authorization Server: <code>/oauth2/authorize</code>, <code>/oauth2/token</code>, <code>/oauth2/jwks</code>.
- OIDC: <code>/.well-known/openid-configuration</code>, <code>/userinfo</code> khi được bật.
- API: <code>/api/catalog/**</code>, <code>/api/billing/**</code>.
- Giao diện Web: <code>/login</code>, <code>/admin/**</code>, <code>/assets/**</code>.

Hãy thực hiện:

1. Vẽ trình tự các chain, xác định matcher của từng chain và đặt <code>@Order</code>.
2. Thiết kế rule để <code>GET /api/catalog/**</code> cần <code>SCOPE_catalog.read</code>, còn <code>/api/billing/**</code> có chính sách riêng.
3. Giải thích vì sao <code>/userinfo</code> có thể không được bảo vệ đúng nếu dùng matcher <code>"/oauth2/**"</code>.
4. Dự đoán kết quả khi đưa chain Web bắt mọi request lên <code>@Order(1)</code>.
5. Viết kiểm thử xác nhận <code>/oauth2/token</code> vào AS chain, <code>/api/catalog/10</code> vào API chain và <code>/login</code> vào Web chain.
6. Thêm một route <code>/public/status</code> và phân biệt cách xử lý bằng <code>permitAll()</code> trong fallback với việc loại route khỏi Spring Security.

Một thiết kế tốt phải chỉ rõ **matcher của từng chain**, **thứ tự chọn chain**, **luật phân quyền trong chain** và **trách nhiệm của các filter xác thực**. Khi thay đổi endpoint hoặc thêm chức năng OIDC, cập nhật cả ma trận kiểm thử.

## 12. Tài liệu đối chiếu

- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): <code>DelegatingFilterProxy</code>, <code>FilterChainProxy</code>, <code>SecurityFilterChain</code> và thứ tự filter.
- [Spring Security — Java Configuration / Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): nhiều <code>SecurityFilterChain</code>, <code>@Order</code>, <code>securityMatcher</code> và <code>requestMatchers</code>.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): thứ tự luật, <code>permitAll</code>, <code>denyAll</code> và matcher cho authorization.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): <code>OAuth2AuthorizationServerConfigurer</code> và các endpoint của Authorization Server.
- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): cấu hình cơ bản với security filter chain của Authorization Server và trang đăng nhập.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh access token và ánh xạ authority.
