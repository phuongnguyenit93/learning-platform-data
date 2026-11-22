# Cấu hình Spring Security tương ứng với Servlet hoặc Reactive

## 1. Vì sao phải bảo vệ endpoint tài liệu?

Springdoc OpenAPI thường cung cấp nhiều endpoint phục vụ tài liệu và giao diện thử API. Với cấu hình mặc định, ứng dụng có thể công khai:

| Endpoint mặc định | Vai trò |
|---|---|
| **/v3/api-docs** | OpenAPI document dạng JSON |
| **/v3/api-docs.yaml** | OpenAPI document dạng YAML |
| **/v3/api-docs/{group}** | Tài liệu JSON của một document group |
| **/v3/api-docs/{group}.yaml** | Tài liệu YAML của một document group |
| **/v3/api-docs/swagger-config** | Cấu hình mà Swagger UI dùng để tải tài liệu |
| **/swagger-ui.html** | Đường dẫn vào Swagger UI, thường chuyển hướng tới trang giao diện |
| **/swagger-ui/** | HTML, JavaScript, CSS và tài nguyên của Swagger UI |

OpenAPI document có thể tiết lộ path nội bộ, tên operation, cấu trúc request/response, security scheme, tên dịch vụ và một phần thông tin kiến trúc. Swagger UI còn cho phép người dùng thử request trực tiếp. Vì vậy, môi trường production thường cần kiểm soát ai được đọc tài liệu và ai được dùng giao diện thử API.

Springdoc tạo tài liệu; Spring Security thực thi quyền truy cập HTTP. Cấu hình bảo vệ phải bao phủ cả endpoint JSON/YAML lẫn trang và tài nguyên Swagger UI. Chỉ khóa trang giao diện nhưng để endpoint tài liệu công khai vẫn cho phép người khác tải đặc tả trực tiếp.

Bài này trình bày hai cấu hình Spring Security riêng biệt theo web stack:

- **Servlet**: dùng SecurityFilterChain với Spring MVC hoặc ứng dụng servlet.
- **Reactive**: dùng SecurityWebFilterChain với Spring WebFlux.

Hai loại chain thuộc hai kiến trúc xử lý request khác nhau. Chọn đúng loại theo ứng dụng; không cấu hình lẫn SecurityFilterChain và SecurityWebFilterChain cho cùng một web stack.

## 2. Xác định đúng các đường dẫn cần bảo vệ

Trước khi viết security rule, hãy xác định đường dẫn thực tế mà ứng dụng đang expose. Springdoc có các thuộc tính để đổi endpoint:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs
~~~

Khi thay đổi cấu hình, endpoint tài liệu mặc định có thể trở thành:

- **/openapi** cho OpenAPI JSON.
- **/openapi.yaml** cho YAML.
- **/openapi/{group}** và **/openapi/{group}.yaml** cho document group.
- **/openapi/swagger-config** cho cấu hình Swagger UI.
- **/docs** cho entry point của Swagger UI; trang này có thể chuyển tiếp tới tài nguyên giao diện.

Đường dẫn tài nguyên Swagger UI vẫn cần được xác minh qua Network tab. Tùy phiên bản, cách override trang, cấu hình tài nguyên và reverse proxy, browser có thể tải thêm các URL khác.

Không nên chỉ bảo vệ một URL đơn lẻ như /v3/api-docs. Pattern /v3/api-docs/** bao phủ tài liệu group và swagger-config trong cấu trúc mặc định. Tương tự, /swagger-ui/** bao phủ các file tĩnh của giao diện, còn /swagger-ui.html là entry point cần tính đến.

Nếu dùng custom path, thêm đúng path đó vào security matcher. Sau khi khởi động ứng dụng, mở Network tab để liệt kê tất cả request mà Swagger UI thực hiện; dùng danh sách đó để kiểm tra matcher có bỏ sót endpoint nào không.

## 3. Chọn chính sách truy cập cho tài liệu

Có ba mô hình thường gặp:

| Chính sách | Cách áp dụng | Khi phù hợp |
|---|---|---|
| Công khai | Cho phép anonymous đọc tài liệu | API public, tài liệu không chứa thông tin nhạy cảm |
| Yêu cầu đăng nhập | Người dùng phải xác thực mới tải tài liệu | Tài liệu dành cho nhân viên hoặc đối tác |
| Yêu cầu role riêng | Chỉ nhóm được cấp quyền như API_DOCS mới truy cập | Tài liệu nội bộ hoặc giao diện thử API production |

Không có một chính sách đúng cho mọi môi trường. Tài liệu public có thể được phát hành trên developer portal; tài liệu nội bộ thường cần authentication và authorization. Một số tổ chức tắt Swagger UI ở production nhưng vẫn xuất bản OpenAPI artifact qua kênh phân phối được kiểm soát.

Cần tách hai quyết định:

1. Ai được xem OpenAPI document và Swagger UI?
2. Ai được gọi các operation thật trong API?

Người có quyền xem tài liệu chưa chắc có quyền gọi API. Ngược lại, một client được phép gọi API cũng không nhất thiết cần truy cập Swagger UI. Hai chính sách cần được cấu hình và kiểm thử độc lập.

## 4. Bảo vệ tài liệu trong ứng dụng Servlet

Với Spring MVC hoặc ứng dụng servlet, Spring Security sử dụng SecurityFilterChain. Có thể tạo một chain riêng cho tài liệu và một chain khác cho API nghiệp vụ.

Ví dụ chỉ người dùng có role API_DOCS mới truy cập tài liệu:

~~~java
@Configuration
@EnableWebSecurity
public class ServletSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain documentationSecurity(HttpSecurity http)
            throws Exception {
        return http
            .securityMatcher(
                "/v3/api-docs/**",
                "/v3/api-docs.yaml",
                "/swagger-ui/**",
                "/swagger-ui.html"
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().hasRole("API_DOCS")
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Trong ví dụ:

- Chain thứ nhất chỉ khớp các URL tài liệu.
- hasRole("API_DOCS") yêu cầu authority tương ứng là ROLE_API_DOCS.
- HTTP Basic được dùng làm ví dụ xác thực đơn giản; thông tin người dùng và cách xác thực phải được cấu hình trong ứng dụng.
- Chain thứ hai xử lý các request còn lại và yêu cầu đăng nhập.

Order(1) làm chain tài liệu được xét trước. Spring Security dùng chain đầu tiên khớp request; chain thứ hai là fallback cho các đường dẫn còn lại. Nếu ứng dụng có nhiều chain hơn, cần kiểm tra thứ tự và matcher để không tạo khoảng trống mà request không được bảo vệ.

Nếu muốn tài liệu công khai, có thể đổi rule trong chain đầu:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .anyRequest().permitAll()
)
~~~

Chain ứng dụng vẫn tiếp tục bảo vệ API nghiệp vụ. permitAll cho tài liệu không có nghĩa mọi endpoint khác đều được công khai.

## 5. Bảo vệ tài liệu bằng một SecurityFilterChain

Nếu ứng dụng chưa cần tách chain, có thể đặt rule tài liệu cùng rule API trong một chain:

~~~java
@Bean
SecurityFilterChain applicationSecurity(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(
                "/v3/api-docs/**",
                "/v3/api-docs.yaml",
                "/swagger-ui/**",
                "/swagger-ui.html"
            ).hasRole("API_DOCS")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Cách này ngắn gọn và phù hợp khi toàn bộ ứng dụng dùng cùng cơ chế xác thực. Tuy nhiên, khi tài liệu có chính sách khác API nghiệp vụ, tách chain giúp phạm vi và thứ tự rule rõ hơn.

Với một chain chung, thứ tự matcher rất quan trọng. Rule cụ thể cho tài liệu cần đứng trước rule tổng quát anyRequest(). Nếu đặt anyRequest() trước, các matcher sau nó không còn được áp dụng.

Nếu cần dùng form login hoặc OAuth2 login thay cho HTTP Basic, thay cơ chế xác thực tương ứng và kiểm tra cách Swagger UI tải JSON. Khi fetch OpenAPI document, redirect tới trang HTML đăng nhập có thể khiến giao diện nhận HTML thay vì JSON. Với endpoint tài liệu, cần chọn cách trả 401/403 hoặc luồng xác thực phù hợp để client xử lý đúng.

## 6. Cấu hình tài liệu công khai trong Servlet

Một số hệ thống muốn công khai tài liệu nhưng yêu cầu đăng nhập cho API:

~~~java
@Bean
@Order(1)
SecurityFilterChain documentationSecurity(HttpSecurity http)
        throws Exception {
    return http
        .securityMatcher(
            "/v3/api-docs/**",
            "/v3/api-docs.yaml",
            "/swagger-ui/**",
            "/swagger-ui.html"
        )
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().permitAll()
        )
        .build();
}

@Bean
@Order(2)
SecurityFilterChain applicationSecurity(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Chain tài liệu chỉ mở các endpoint tài liệu. Chain nghiệp vụ cho phép một vùng API public và yêu cầu đăng nhập với các API còn lại.

Nếu tài liệu chứa operation nội bộ, server hostname riêng, schema nhạy cảm hoặc ví dụ không nên công khai, hãy cân nhắc yêu cầu role thay vì permitAll. Việc OpenAPI document không chứa secret không có nghĩa mọi thông tin trong đó đều phù hợp để phát hành công khai.

## 7. Bảo vệ tài liệu trong ứng dụng Reactive

Với Spring WebFlux, Spring Security dùng SecurityWebFilterChain và ServerHttpSecurity. Không dùng HttpSecurity hoặc SecurityFilterChain của servlet trong cấu hình reactive.

Ví dụ tạo chain riêng cho tài liệu:

~~~java
@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityWebFilterChain documentationSecurity(ServerHttpSecurity http) {
        ServerWebExchangeMatcher documentationPaths =
            new OrServerWebExchangeMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                    "/v3/api-docs/**"
                ),
                new PathPatternParserServerWebExchangeMatcher(
                    "/v3/api-docs.yaml"
                ),
                new PathPatternParserServerWebExchangeMatcher(
                    "/swagger-ui/**"
                ),
                new PathPatternParserServerWebExchangeMatcher(
                    "/swagger-ui.html"
                )
            );

        return http
            .securityMatcher(documentationPaths)
            .authorizeExchange(authorize -> authorize
                .anyExchange().hasRole("API_DOCS")
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain applicationSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(authorize -> authorize
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Trong ví dụ:

- PathPatternParserServerWebExchangeMatcher so khớp path trên reactive exchange.
- OrServerWebExchangeMatcher kết hợp các path cần bảo vệ.
- Chain đầu xử lý endpoint tài liệu.
- Chain sau xử lý request còn lại.
- hasRole("API_DOCS") yêu cầu authority ROLE_API_DOCS.

Các lớp matcher thuộc Spring Security WebFlux. Import cụ thể cần theo phiên bản Spring Security của dự án. Nếu đã đổi springdoc.api-docs.path hoặc springdoc.swagger-ui.path, hãy thay các pattern mặc định bằng path đang sử dụng.

## 8. Cho phép công khai tài liệu trong Reactive

Nếu OpenAPI document và Swagger UI được phép truy cập công khai, chỉ thay rule của chain tài liệu:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain documentationSecurity(ServerHttpSecurity http) {
    ServerWebExchangeMatcher documentationPaths =
        new OrServerWebExchangeMatcher(
            new PathPatternParserServerWebExchangeMatcher(
                "/v3/api-docs/**"
            ),
            new PathPatternParserServerWebExchangeMatcher(
                "/v3/api-docs.yaml"
            ),
            new PathPatternParserServerWebExchangeMatcher(
                "/swagger-ui/**"
            ),
            new PathPatternParserServerWebExchangeMatcher(
                "/swagger-ui.html"
            )
        );

    return http
        .securityMatcher(documentationPaths)
        .authorizeExchange(authorize -> authorize
            .anyExchange().permitAll()
        )
        .build();
}
~~~

Chain ứng dụng vẫn phải được khai báo để bảo vệ các route nghiệp vụ. Không nên bỏ chain fallback chỉ vì chain tài liệu đã hoạt động; request không khớp matcher tài liệu sẽ được xử lý bởi chain khác hoặc có thể không được bảo vệ nếu không có chain phù hợp.

Trong ứng dụng reactive, thứ tự Order và phạm vi matcher cũng quan trọng như Servlet. Hãy kiểm tra một request tài liệu, một request API public và một request API yêu cầu đăng nhập để xác minh từng chain được chọn đúng.

## 9. Đổi endpoint tài liệu thì phải đổi security matcher

Giả sử cấu hình Springdoc đổi endpoint:

~~~yaml
springdoc:
  api-docs:
    path: /internal/openapi
  swagger-ui:
    path: /developer/docs
~~~

Security matcher cần bao phủ các URL mới:

- /internal/openapi
- /internal/openapi.yaml cho YAML mặc định
- /internal/openapi/** cho group và swagger-config
- /developer/docs
- Các URL tài nguyên Swagger UI thực tế được browser tải, thường là /swagger-ui/**

Với cấu hình Servlet, một matcher minh họa cho các đường dẫn này là:

~~~java
.securityMatcher(
    "/internal/openapi/**",
    "/internal/openapi.yaml",
    "/swagger-ui/**",
    "/swagger-ui.html",
    "/developer/docs"
)
~~~

Trong Reactive, dùng cùng các pattern đó với PathPatternParserServerWebExchangeMatcher.

Không giả định custom UI path thay thế toàn bộ resource path. Entry point có thể redirect tới một trang khác. Hãy mở URL UI và xem Network tab để xác định đường dẫn HTML, JavaScript, CSS, swagger-config và OpenAPI document.

Nếu ứng dụng chạy dưới context path hoặc reverse proxy prefix, xác minh path mà Spring Security matcher nhìn thấy và path mà browser gọi. Tránh thêm prefix hai lần hoặc bỏ sót prefix do gateway rewrite.

## 10. Bảo vệ cả JSON, YAML, group và swagger-config

Một lỗi phổ biến là chỉ khóa JSON mặc định nhưng quên các endpoint liên quan. Hãy rà soát:

| Loại request | Ví dụ | Có cần rule không? |
|---|---|---|
| JSON mặc định | GET /v3/api-docs | Có |
| YAML mặc định | GET /v3/api-docs.yaml | Có |
| Tài liệu group | GET /v3/api-docs/partner | Có |
| YAML group | GET /v3/api-docs/partner.yaml | Có |
| Swagger config | GET /v3/api-docs/swagger-config | Có |
| Entry point UI | GET /swagger-ui.html | Có |
| UI resources | GET /swagger-ui/index.html, CSS, JS | Có |
| Operation API | GET/POST /api/** | Theo chính sách API nghiệp vụ |

Pattern /v3/api-docs/** thường bao phủ các endpoint tài liệu con. Endpoint YAML mặc định có thể nằm ở dạng suffix .yaml trên path gốc; kiểm tra matcher và hành vi của phiên bản Springdoc đang chạy để chắc chắn nó được bảo vệ.

Không cần cho phép mọi request vào /v3/** nếu chỉ muốn bảo vệ OpenAPI document. Hãy dùng matcher hẹp để không vô tình mở các endpoint actuator hoặc endpoint hệ thống khác.

## 11. Phân biệt quyền xem tài liệu và quyền gọi API

Swagger UI thực hiện hai loại request:

1. Tải giao diện, swagger-config và OpenAPI document.
2. Gọi operation API khi người dùng bấm Try it out.

Các request tải tài liệu đi tới endpoint Springdoc. Các request Try it out đi tới endpoint nghiệp vụ được mô tả trong OpenAPI. Hai nhóm có thể dùng security chain và credential khác nhau.

Ví dụ người dùng có role API_DOCS được phép tải tài liệu, nhưng operation POST /api/orders vẫn cần OAuth2 scope orders.write. Việc tải được Swagger UI không cấp scope đó. Người dùng phải xác thực theo Security Scheme được khai báo cho API và backend phải kiểm tra token/quyền ở runtime.

Ngược lại, một service account có quyền gọi API không nhất thiết được cấp role đọc tài liệu. Đây là lựa chọn phân quyền độc lập.

Với tài liệu OpenAPI, khai báo @SecurityScheme và @SecurityRequirement giúp Swagger UI biết cách yêu cầu credential cho operation. Spring Security hoặc resource server mới là nơi xác minh credential khi request tới API.

## 12. Không vô hiệu hóa CSRF chỉ để Swagger UI hoạt động

Spring Security bật CSRF protection theo cấu hình mặc định trong nhiều mô hình servlet có session. Swagger UI có thể gửi các request thay đổi dữ liệu như POST, PUT, PATCH hoặc DELETE khi người dùng chọn Try it out.

Nếu ứng dụng dùng session cookie và CSRF protection, request thay đổi dữ liệu phải gửi CSRF token hợp lệ. Chỉ bảo vệ endpoint tài liệu bằng HTTP Basic không tự giải quyết CSRF cho API nghiệp vụ.

Không nên tắt CSRF toàn ứng dụng chỉ để Swagger UI gọi được POST. Hãy chọn chính sách dựa trên cơ chế xác thực thực tế:

- Nếu API dùng session cookie, duy trì CSRF protection và cung cấp token theo cơ chế ứng dụng.
- Nếu API stateless dùng bearer token trong Authorization header và không dựa vào cookie tự động gửi, có thể cấu hình CSRF theo mô hình stateless phù hợp.
- Nếu chỉ muốn đọc tài liệu, endpoint Springdoc chủ yếu là GET; không cần tắt CSRF toàn cục vì lý do này.

Trong WebFlux, CSRF cũng cần được cấu hình theo cách ứng dụng xác thực và sử dụng cookie. Không sao chép cấu hình disable CSRF từ ví dụ stateless sang ứng dụng session-based.

## 13. CORS khi Swagger UI và API khác origin

Nếu Swagger UI được phục vụ từ một host nhưng API nằm ở host khác, browser áp dụng CORS. Tải OpenAPI document và gọi operation có thể là hai luồng cross-origin riêng biệt.

Cần cấu hình CORS cho đúng origin của Swagger UI, method và header cần thiết. Nếu dùng Authorization header hoặc API key header, preflight OPTIONS có thể được gửi trước request thật. Nếu dùng cookie, cần cấu hình credential và origin cụ thể.

Một số điểm cần kiểm tra:

- Origin của trang Swagger UI.
- Origin của OpenAPI document.
- Server URL trong OpenAPI document.
- Allowed methods và allowed headers.
- Access-Control-Allow-Credentials nếu dùng cookie.
- Access-Control-Expose-Headers nếu giao diện cần đọc response header.
- Preflight OPTIONS có bị security rule chặn trước khi CORS được xử lý không.

CORS không thay thế authentication. Cho phép origin gửi request không có nghĩa người dùng được cấp quyền truy cập API.

## 14. Dùng profile để tắt Swagger UI ở môi trường không cần

Một lựa chọn khác là không bật giao diện hoặc OpenAPI endpoint ở môi trường production:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

Có thể đặt cấu hình này trong profile production nếu quy trình phát hành không cần phục vụ tài liệu trực tiếp từ ứng dụng. OpenAPI artifact vẫn có thể được tạo trong CI và phân phối qua kho tài liệu hoặc developer portal có kiểm soát.

Cần hiểu sự khác nhau:

- api-docs.enabled: false tắt việc phục vụ OpenAPI document qua Springdoc.
- swagger-ui.enabled: false tắt Swagger UI.
- Security rule bảo vệ endpoint đang bật.
- Việc tắt tài liệu không tự bảo vệ API nghiệp vụ.

Nếu chỉ tắt Swagger UI nhưng OpenAPI endpoint còn hoạt động, người khác vẫn có thể tải JSON/YAML trực tiếp. Nếu mục tiêu là không công bố tài liệu, hãy kiểm tra cả hai thuộc tính và thử truy cập các URL sau khi khởi động profile production.

## 15. Kiểm tra role và authentication provider

Ví dụ hasRole("API_DOCS") kiểm tra authority ROLE_API_DOCS. Nếu hệ thống dùng authority tên API_DOCS không có prefix, có thể dùng:

~~~java
.hasAuthority("API_DOCS")
~~~

Không nhầm hasRole với hasAuthority:

| Rule | Authority được kiểm tra |
|---|---|
| hasRole("API_DOCS") | ROLE_API_DOCS |
| hasAuthority("API_DOCS") | API_DOCS |

Tài khoản truy cập tài liệu phải được cấp role/authority qua UserDetailsService, LDAP, OAuth2 login, JWT converter hoặc hệ thống identity provider mà ứng dụng đang dùng.

Nếu dùng OAuth2 Resource Server, token cần có claim/authority ánh xạ thành quyền đọc tài liệu. Nếu dùng OIDC login với session, người dùng phải được cấp role tương ứng. Security chain chỉ kiểm tra quyền; nó không tự tạo tài khoản hoặc cấp role.

Không nhúng username/password vào application.yml hoặc source code. Dùng secret management và identity provider theo quy trình vận hành của tổ chức.

## 16. Bảo vệ Swagger UI khi dùng Basic Auth hoặc OIDC login

HTTP Basic có thể phù hợp với môi trường nội bộ đơn giản, nhưng browser có thể lưu thông tin xác thực trong thời gian phiên hoạt động. Cần dùng HTTPS và tài khoản riêng có quyền tối thiểu.

Với hệ thống có SSO, có thể bảo vệ trang tài liệu bằng OIDC login hoặc cơ chế đăng nhập tập trung. Khi đó, cần kiểm tra:

- Swagger UI page có chuyển hướng đăng nhập đúng không.
- Fetch swagger-config và OpenAPI JSON có giữ được phiên xác thực không.
- Khi hết session, giao diện nhận được trạng thái phù hợp thay vì HTML login page giả dạng JSON.
- API Try it out có dùng credential phù hợp với security scheme của operation không.
- Redirect URI và cookie policy đúng với domain triển khai.

Một phiên OIDC dùng để truy cập trang tài liệu không tự động tạo access token có scope phù hợp cho mọi API. Nếu operation yêu cầu OAuth2 bearer token, hãy cấu hình scheme và luồng authorize tương ứng.

## 17. Các lỗi thường gặp khi bảo vệ tài liệu

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Swagger UI mở được nhưng OpenAPI JSON trả 401 | Rule hoặc credential cho swagger-config/document chưa phù hợp |
| /v3/api-docs bị khóa nhưng group document vẫn công khai | Matcher chỉ bao phủ URL gốc, thiếu /v3/api-docs/** |
| JSON được bảo vệ nhưng YAML vẫn công khai | Chưa kiểm tra endpoint YAML và pattern suffix |
| Swagger UI bị 404 sau khi bật security | Thiếu /swagger-ui.html hoặc /swagger-ui/** |
| Browser nhận HTML login page thay vì JSON | Form login redirect áp dụng cho fetch tài liệu |
| Người có role vẫn nhận 403 | Authority không khớp ROLE_ prefix hoặc token converter |
| API docs được bảo vệ nhưng API operation vẫn public | Chỉ cấu hình chain tài liệu, chưa cấu hình API chain |
| Người xem tài liệu gọi được API ngoài quyền | Backend chưa kiểm tra security scheme/scope hoặc authorization rule |
| Reactive app không áp dụng rule | Dùng nhầm servlet chain hoặc matcher không thuộc WebFlux |
| Một request không khớp chain nào | Thiếu fallback chain hoặc thứ tự matcher sai |
| Try it out POST bị 403 | CSRF token thiếu hoặc CORS preflight bị chặn |
| UI tải được tài liệu nhưng gọi API cross-origin thất bại | CORS, server URL hoặc credential mode không đúng |
| Đổi springdoc path nhưng docs vẫn mở công khai | Security matcher vẫn dùng đường dẫn mặc định |
| Đã tắt Swagger UI nhưng JSON vẫn truy cập được | Chưa tắt api-docs hoặc chưa bảo vệ OpenAPI endpoint |

Khi điều tra, kiểm tra status code, redirect chain, response Content-Type và request path trong Network tab. Sau đó xác định chain nào đã khớp và rule nào quyết định quyền truy cập.

## 18. Checklist kiểm thử trước khi phát hành

Nên kiểm tra cả người dùng có quyền và không có quyền:

| Request | Người chưa xác thực | Người có role API_DOCS |
|---|---|---|
| Tải Swagger UI entry point | 401/403 hoặc được phép theo chính sách | 200/redirect hợp lệ |
| Tải UI CSS/JS | 401/403 hoặc được phép theo chính sách | 200 |
| Tải swagger-config | 401/403 hoặc được phép theo chính sách | 200 |
| Tải OpenAPI JSON | 401/403 hoặc được phép theo chính sách | 200 |
| Tải OpenAPI YAML | 401/403 hoặc được phép theo chính sách | 200 |
| Tải tài liệu group | 401/403 hoặc được phép theo chính sách | 200 |
| Gọi API nghiệp vụ | Theo rule của API | Vẫn phải có credential/scope của API nếu cần |

Bổ sung kiểm thử:

1. Endpoint mặc định và endpoint đã đổi path.
2. Tài liệu JSON, YAML và swagger-config.
3. Từng document group.
4. Swagger UI entry point và static resources.
5. API public và API yêu cầu authentication.
6. User có role tài liệu nhưng không có scope nghiệp vụ.
7. Request Try it out với GET và request thay đổi dữ liệu.
8. CORS preflight khi UI khác origin.
9. CSRF nếu API dùng session cookie.
10. Profile production khi đã tắt tài liệu.

Có thể dùng MockMvc cho Servlet và WebTestClient cho Reactive. Ngoài status code, hãy xác minh response Content-Type, redirect location và nội dung JSON để phát hiện trang login HTML bị trả về nhầm cho OpenAPI client.

## 19. Nguyên tắc cấu hình Spring Security cho tài liệu

Khi bảo vệ Springdoc OpenAPI, hãy áp dụng các nguyên tắc:

1. Xác định đúng web stack: Servlet dùng SecurityFilterChain, Reactive dùng SecurityWebFilterChain.
2. Bao phủ OpenAPI JSON/YAML, group documents, swagger-config, UI entry point và static resources.
3. Cập nhật matcher khi đổi springdoc.api-docs.path hoặc springdoc.swagger-ui.path.
4. Tách quyền xem tài liệu khỏi quyền gọi API nghiệp vụ.
5. Dùng role/authority riêng nếu tài liệu chỉ dành cho nhóm được phép.
6. Giữ fallback security chain cho các request còn lại.
7. Không tắt CSRF toàn ứng dụng chỉ để Try it out hoạt động.
8. Cấu hình CORS theo origin và credential thực tế.
9. Dùng profile để tắt cả Swagger UI và OpenAPI endpoint nếu môi trường không cần phục vụ tài liệu.
10. Kiểm tra bằng MockMvc/WebTestClient và browser Network tab trước khi phát hành.

Springdoc quyết định tài liệu và giao diện nào được tạo; Spring Security quyết định ai được tải chúng. Cấu hình đúng theo Servlet hoặc Reactive giúp bảo vệ toàn bộ đường dẫn tài liệu, đồng thời giữ chính sách xác thực cho API nghiệp vụ độc lập. Khi kiểm tra cả endpoint tài liệu, tài nguyên giao diện và request Try it out, nhóm phát triển tránh được tình trạng khóa một phần nhưng vẫn để lộ tài liệu qua URL khác.

