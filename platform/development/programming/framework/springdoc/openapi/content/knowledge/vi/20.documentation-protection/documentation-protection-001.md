# Phân biệt quyền đọc đặc tả, quyền mở giao diện và quyền gọi API

Một ứng dụng Spring Boot có thể công bố tài liệu API qua Swagger UI và OpenAPI JSON/YAML, đồng thời cung cấp các endpoint nghiệp vụ cho client. Ba bề mặt này thường liên quan nhưng có quyền truy cập khác nhau:

1. **Swagger UI:** trang web và các tài nguyên tĩnh để người dùng duyệt tài liệu.
2. **OpenAPI document:** JSON/YAML mô tả paths, operations, schema, security và responses.
3. **API runtime:** endpoint thực thi nghiệp vụ, đọc hoặc thay đổi dữ liệu.

Mở trang Swagger UI không đồng nghĩa người dùng được tải đặc tả; tải được đặc tả không có nghĩa họ được gọi API; và tắt giao diện Swagger UI cũng không bảo vệ endpoint. Cần thiết kế chính sách truy cập riêng cho từng bề mặt, sau đó kiểm tra bằng request thực tế.

## 1. Ba bề mặt truy cập độc lập

Với cấu hình mặc định của springdoc-openapi, các đường dẫn thường gặp là:

| Bề mặt | Đường dẫn mặc định thường gặp | Nội dung |
|---|---|---|
| Swagger UI redirect | /swagger-ui.html | Chuyển hướng tới giao diện |
| Swagger UI assets | /swagger-ui/** | HTML, JavaScript, CSS và tài nguyên giao diện |
| OpenAPI JSON | /v3/api-docs | Đặc tả OpenAPI dạng JSON |
| OpenAPI YAML | /v3/api-docs.yaml | Đặc tả OpenAPI dạng YAML |
| Grouped OpenAPI | /v3/api-docs/{group} | Đặc tả của một document group |

Đường dẫn có thể thay đổi theo springdoc.swagger-ui.path và springdoc.api-docs.path. Nếu ứng dụng dùng context path hoặc reverse proxy, URL công khai còn có thể khác URL nội bộ.

Ba bề mặt có thể được bảo vệ khác nhau:

- Người dùng được mở Swagger UI nhưng không được tải spec sẽ thấy trang giao diện nhưng phần operation có thể không tải được.
- Người dùng tải trực tiếp được OpenAPI JSON vẫn có thể không mở được Swagger UI.
- Người dùng có thể không được truy cập tài liệu nhưng vẫn gọi API bằng client khác nếu endpoint runtime cho phép.
- Người dùng có thể truy cập tài liệu nhưng bị API từ chối vì thiếu token hoặc quyền.

Hãy quyết định rõ ai được đọc tài liệu, ai được mở giao diện và ai được thực thi từng API.

## 2. Tách quyền đọc tài liệu khỏi quyền gọi API

Một chính sách thường gặp ở hệ thống nội bộ:

- Thành viên nhóm phát triển hoặc vận hành có quyền DOCS_READER để mở Swagger UI và tải đặc tả.
- API nghiệp vụ yêu cầu bearer token và scope phù hợp.
- Endpoint công khai chỉ mở một số thao tác đọc dữ liệu.
- Endpoint quản trị yêu cầu role hoặc authority riêng.

Ví dụ ma trận quyền:

| Principal | Swagger UI | OpenAPI JSON/YAML | GET catalog | GET orders | POST orders |
|---|---:|---:|---:|---:|---:|
| Anonymous | Không | Không | Có | Không | Không |
| DOCS_READER | Có | Có | Có | Theo token API | Theo token API |
| API_USER có orders.read | Theo chính sách docs | Theo chính sách docs | Có | Có | Không |
| API_USER có orders.write | Theo chính sách docs | Theo chính sách docs | Có | Theo quyền đọc | Có |

Bảng trên minh họa hai nhóm credential có thể khác nhau. Quyền DOCS_READER không tự cấp orders.read hoặc orders.write. Tương tự, có scope gọi API không nhất thiết cấp quyền xem tài liệu nội bộ.

Có thể dùng cùng một hệ thống định danh nhưng tách authority cho tài liệu và nghiệp vụ. Cách này giúp thu hồi quyền docs mà không phải thay đổi quyền gọi API.

## 3. Security requirement trong OpenAPI không bảo vệ endpoint tài liệu

Các annotation như @SecurityScheme và @SecurityRequirement mô tả cơ chế xác thực mà client dùng khi gọi operation được ghi trong tài liệu.

Ví dụ bearer token:

~~~java
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
@Configuration
class OpenApiSecurityConfiguration {
}
~~~

Gắn vào operation API:

~~~java
@GetMapping("/api/me")
@Operation(
    summary = "Lấy hồ sơ hiện tại",
    security = @SecurityRequirement(name = "bearerAuth")
)
public ProfileResponse getProfile() {
    return profileService.current();
}
~~~

Khai báo này tạo metadata trong OpenAPI. Nó không áp dụng quyền truy cập cho /swagger-ui.html hoặc /v3/api-docs. Các đường dẫn tài liệu phải được kiểm soát bởi Spring Security, reverse proxy hoặc lớp bảo vệ tương ứng.

Ngược lại, cấu hình Spring Security chặn /v3/api-docs không tự làm cho mọi operation trong tài liệu có security requirement. Cần kiểm tra cả security policy runtime lẫn security metadata được sinh ra.

## 4. Cấu hình đường dẫn tài liệu mặc định

Trước khi viết SecurityFilterChain, xác định chính xác các URL được springdoc phục vụ. Cấu hình mặc định thường gồm:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
    path: /swagger-ui.html
~~~

Có thể thay đổi đường dẫn:

~~~yaml
springdoc:
  api-docs:
    path: /internal/openapi
  swagger-ui:
    path: /internal/docs
~~~

Khi đổi path, endpoint JSON và YAML, redirect của Swagger UI và grouped documents có thể thay đổi theo cấu hình. Security matcher phải cập nhật tương ứng.

Không giả định matcher /v3/api-docs/** sẽ bảo vệ một path tùy chỉnh như /internal/openapi. Hãy mở ứng dụng và kiểm tra URL thực tế trước khi hoàn thiện chính sách.

## 5. Bảo vệ tài liệu bằng SecurityFilterChain riêng

Có thể dùng một SecurityFilterChain cho tài liệu và một chain khác cho API nghiệp vụ. Cách này làm rõ sự khác biệt giữa credential đọc docs và bearer token gọi API.

Ví dụ dưới đây dùng HTTP Basic cho tài liệu nội bộ và JWT Resource Server cho API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain documentationChain(HttpSecurity http)
            throws Exception {

        http
            .securityMatcher(
                "/swagger-ui.html",
                "/swagger-ui/**",
                "/v3/api-docs",
                "/v3/api-docs/**",
                "/v3/api-docs.yaml"
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().hasRole("DOCS_READER")
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {

        http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/catalog/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
~~~

Các điểm quan trọng:

- Chain tài liệu chỉ khớp Swagger UI và OpenAPI endpoints.
- Chain API chỉ khớp /api/**.
- Chain được chọn theo thứ tự; request đi vào chain đầu tiên có matcher phù hợp.
- DOCS_READER là role dành cho người đọc tài liệu.
- API kiểm tra scope riêng như SCOPE_orders.read và SCOPE_orders.write.
- Fallback chain từ chối các đường dẫn không được khai báo.

hasRole("DOCS_READER") thường kiểm tra authority ROLE_DOCS_READER. Ứng dụng cần có UserDetailsService, authentication provider hoặc cơ chế đăng nhập tương ứng để cấp role đó. Ví dụ chỉ minh họa cấu trúc chain; cần tích hợp nguồn người dùng thực tế.

Chain tài liệu dùng HTTP Basic để trình duyệt có thể xác thực khi tải HTML, JavaScript và OpenAPI document. Chỉ dùng Basic qua HTTPS và quản lý mật khẩu bằng cơ chế an toàn.

## 6. Vì sao tách chain tài liệu và API?

Nếu gom tất cả vào một quy tắc anyRequest().authenticated(), người dùng có thể phải dùng cùng một loại credential cho docs và API. Điều đó không phải lúc nào cũng phù hợp.

Tách chain cho phép:

- Dùng đăng nhập nội bộ hoặc HTTP Basic cho trang docs.
- Dùng bearer JWT cho API.
- Cấp role DOCS_READER riêng.
- Áp dụng CSRF và session policy phù hợp từng bề mặt.
- Dễ kiểm tra thứ tự matcher và tránh vô tình mở endpoint.

Cần chú ý rằng chỉ chain đầu tiên khớp request được sử dụng. Nếu chain API được đặt trước và matcher quá rộng, request tài liệu có thể bị xử lý bởi chain API. Nếu chain docs dùng matcher /**, nó có thể bắt nhầm mọi endpoint. Hãy giới hạn matcher theo đúng URL.

Với ứng dụng lớn, có thể dùng nhiều filter chain hơn, nhưng mỗi chain cần có phạm vi rõ ràng và thứ tự được kiểm thử.

## 7. Trường hợp công khai tài liệu

Nếu tài liệu được phép truy cập công khai, có thể cho phép các đường dẫn docs:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(
        "/swagger-ui.html",
        "/swagger-ui/**",
        "/v3/api-docs",
        "/v3/api-docs/**",
        "/v3/api-docs.yaml"
    ).permitAll()
    .anyRequest().authenticated()
)
~~~

Điều này chỉ mở giao diện và đặc tả. Các API nghiệp vụ vẫn có thể yêu cầu JWT hoặc role riêng.

Trước khi công khai, hãy rà soát xem spec có chứa:

- Endpoint quản trị hoặc nội bộ.
- Tên hệ thống, path hoặc thông tin hạ tầng không muốn công bố.
- Schema chứa trường nội bộ.
- Mô tả quy trình nghiệp vụ nhạy cảm.
- Server URL của môi trường staging hoặc development.
- Example chứa dữ liệu thật hoặc thông tin bí mật.

Không đưa password, token, API key hoặc dữ liệu cá nhân thật vào example và description. OpenAPI là tài liệu có thể được tải và lưu trữ ngoài ứng dụng.

## 8. Bảo vệ Swagger UI nhưng cho phép tải OpenAPI JSON

Một số tổ chức muốn developer dùng công cụ riêng để lấy spec nhưng không cung cấp giao diện Swagger UI cho mọi người.

Có thể cấu hình riêng:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/swagger-ui.html", "/swagger-ui/**")
        .hasRole("DOCS_UI_USER")
    .requestMatchers(
        "/v3/api-docs",
        "/v3/api-docs/**",
        "/v3/api-docs.yaml"
    ).hasRole("SPEC_READER")
    .anyRequest().authenticated()
)
~~~

Khi đó người có DOCS_UI_USER mới mở giao diện, còn SPEC_READER có thể tải JSON/YAML bằng curl hoặc công cụ code generation.

Nếu Swagger UI cần tải spec từ /v3/api-docs, người mở giao diện cũng phải có quyền SPEC_READER hoặc cơ chế truy cập tương đương. Nếu không, trang HTML có thể tải thành công nhưng danh sách operation bị lỗi do request lấy spec nhận 401/403.

Nếu hai quyền được cấp cho cùng nhóm, có thể dùng cùng role cho cả hai path để cấu hình đơn giản hơn.

## 9. Cho phép giao diện nhưng chặn đặc tả trực tiếp

Chính sách ngược lại cũng có thể xảy ra: một nhóm người dùng được truy cập giao diện thông qua reverse proxy hoặc session, trong khi endpoint spec trực tiếp được giới hạn.

Tuy nhiên, Swagger UI cần tải OpenAPI document để dựng operation. Nếu UI và spec ở cùng ứng dụng, việc chặn spec sẽ khiến UI không hoạt động trừ khi có một proxy hoặc backend trung gian được cấp quyền đọc spec.

Không thể chỉ mở trang HTML rồi kỳ vọng Swagger UI tự biết toàn bộ schema. Giao diện cần dữ liệu OpenAPI từ URL cấu hình hoặc tài liệu được nhúng.

Nếu mục tiêu là cho người dùng xem tài liệu đã render nhưng không tải file spec gốc, cần thiết kế kênh phân phối phù hợp và đánh giá rằng nội dung hiển thị vẫn có thể được trích xuất từ trình duyệt.

## 10. Grouped OpenAPI cũng cần được bảo vệ

Khi sử dụng GroupedOpenApi, springdoc có thể công bố nhiều tài liệu, ví dụ:

- /v3/api-docs/public
- /v3/api-docs/partner
- /v3/api-docs/admin

Các group thường vẫn nằm dưới path gốc /v3/api-docs, nhưng cần xác minh endpoint thực tế trong ứng dụng. Matcher /v3/api-docs/** thường bao phủ group path; endpoint gốc và YAML cần được khai báo phù hợp.

Nếu public và admin có chính sách khác nhau, không nên chỉ dùng một matcher chung cho toàn bộ group. Có thể tạo matcher cụ thể trước matcher tổng quát:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/v3/api-docs/admin").hasRole("ADMIN_DOCS")
    .requestMatchers("/v3/api-docs/partner").hasRole("PARTNER_DOCS")
    .requestMatchers(
        "/v3/api-docs",
        "/v3/api-docs/public",
        "/v3/api-docs.yaml"
    ).permitAll()
    .anyRequest().authenticated()
)
~~~

Thứ tự matcher trong cùng một authorization rule quan trọng: rule cụ thể cần đặt trước rule tổng quát. Nếu matcher tổng quát được xử lý trước, rule riêng cho admin có thể không được áp dụng như dự định.

Nếu Swagger UI dùng một group cụ thể, cấu hình URL spec tương ứng và xác minh quyền tải group đó. Không để UI vô tình tải nhầm tài liệu admin trong khi người dùng chỉ được phép đọc public API.

## 11. Đường dẫn tùy chỉnh và reverse proxy

Nếu cấu hình:

~~~yaml
springdoc:
  api-docs:
    path: /internal/openapi
  swagger-ui:
    path: /internal/docs
~~~

thì SecurityFilterChain cần bảo vệ các đường dẫn tùy chỉnh, ví dụ /internal/docs, tài nguyên UI tương ứng và /internal/openapi cùng các biến thể/group nếu có.

Khi triển khai sau reverse proxy, đường dẫn bên ngoài có thể được rewrite. Ví dụ public URL /docs có thể được chuyển tiếp tới /swagger-ui.html. Security policy ở proxy và trong ứng dụng cần nhất quán.

Kiểm tra:

- Context path của Spring Boot.
- springdoc.api-docs.path.
- springdoc.swagger-ui.path.
- Proxy prefix và rewrite rule.
- Forwarded headers.
- URL mà Swagger UI dùng để tải spec.
- URL server mà Try it out dùng để gọi API.

Không chỉ kiểm tra URL nội bộ. Hãy kiểm tra từ mạng và hostname mà người dùng thực sự sử dụng.

## 12. Swagger UI Authorize không phải quyền đọc trang docs

Nút Authorize trong Swagger UI dùng security scheme của OpenAPI để cấu hình credential cho các request API được gửi qua Try it out.

Nó thường không thay thế cơ chế đăng nhập để tải chính trang Swagger UI hoặc file spec ban đầu.

Ví dụ:

- Trình duyệt cần đăng nhập để tải /swagger-ui/index.html.
- Trình duyệt cần quyền đọc /v3/api-docs để lấy đặc tả.
- Sau khi UI tải xong, người dùng nhập bearer token qua Authorize để gọi /api/orders.

Đây là ba bước xác thực có thể dùng các credential hoặc chính sách khác nhau. Nếu bảo vệ docs bằng HTTP Basic/session, còn API dùng JWT, Swagger UI có thể dùng Basic để tải tài liệu và bearer token cho request nghiệp vụ.

Đừng giả định token nhập ở nút Authorize đã được gửi khi trình duyệt tải file OpenAPI lúc khởi tạo giao diện.

## 13. supportedSubmitMethods không bảo vệ API

Cấu hình springdoc.swagger-ui.supportedSubmitMethods có thể giới hạn method được gửi bằng Try it out. Ví dụ chỉ cho phép GET:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
~~~

Hoặc tắt toàn bộ Try it out:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods: []
~~~

Các cấu hình này chỉ thay đổi khả năng gọi thử trong Swagger UI. Người dùng vẫn có thể gửi POST, PUT, PATCH hoặc DELETE bằng curl, Postman hay ứng dụng khác nếu backend cho phép.

Muốn bảo vệ API, cần cấu hình authorization tại runtime. Muốn bảo vệ tài liệu, cần bảo vệ Swagger UI và OpenAPI endpoints. Không dùng một cấu hình thay thế cho hai việc còn lại.

## 14. CSRF và CORS theo từng bề mặt

Nếu dùng HTTP Basic hoặc session cookie cho docs, trình duyệt có thể tự gửi credential trong các request tiếp theo. Với ứng dụng dựa trên cookie/session, cần đánh giá CSRF theo chính sách Spring Security.

Swagger UI chủ yếu tải trang, tài nguyên và spec bằng GET. Nếu có thao tác API ghi dữ liệu từ Try it out bằng cookie session, request có thể cần CSRF token.

CORS chỉ liên quan khi Swagger UI và API/spec ở các origin khác nhau. Cần cho phép đúng origin, method và header như Authorization, Content-Type. CORS không thay thế authentication và không ngăn curl/Postman.

Với API stateless dùng bearer token trong Authorization header, cấu hình CSRF có thể khác với ứng dụng session-based. Chỉ tắt CSRF khi mô hình xác thực và cách trình duyệt gửi credential đã được đánh giá.

## 15. Tắt Swagger UI hoặc OpenAPI document

springdoc cho phép tắt giao diện hoặc endpoint đặc tả bằng cấu hình:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: false
~~~

Tắt Swagger UI sẽ ngừng cung cấp giao diện. Tắt api-docs sẽ ngừng cung cấp tài liệu động. Tùy cấu hình và phiên bản, cần kiểm tra endpoint thực tế sau khi khởi động.

Việc tắt docs không tự bảo vệ API. Các endpoint nghiệp vụ vẫn được xử lý bởi controller và SecurityFilterChain. Ngược lại, giữ OpenAPI JSON nhưng tắt UI vẫn cho phép consumer tải spec nếu endpoint JSON được mở.

Có thể dùng profile riêng để bật docs trong development và tắt hoặc giới hạn trong production. Hãy bảo đảm config cuối cùng được nạp đúng profile.

## 16. Kiểm tra quyền truy cập bằng curl

Kiểm tra từng bề mặt riêng. Ví dụ khi docs yêu cầu HTTP Basic:

~~~bash
# Không có credential: dự kiến 401
curl -i http://localhost:8080/swagger-ui.html
curl -i http://localhost:8080/v3/api-docs

# Có quyền đọc docs: dự kiến 200
curl -i -u docs-reader:REPLACE_WITH_SECRET \
  http://localhost:8080/v3/api-docs

# Tải giao diện
curl -i -u docs-reader:REPLACE_WITH_SECRET \
  http://localhost:8080/swagger-ui/index.html
~~~

Kiểm tra API bằng bearer token:

~~~bash
# Không token: thường 401 với endpoint yêu cầu xác thực
curl -i http://localhost:8080/api/orders

# Token hợp lệ nhưng thiếu scope: thường 403
curl -i http://localhost:8080/api/orders \
  -H "Authorization: Bearer REPLACE_WITH_TOKEN"

# Token có scope phù hợp: có thể được phép
curl -i http://localhost:8080/api/orders \
  -H "Authorization: Bearer REPLACE_WITH_TOKEN"
~~~

Thay credential bằng thông tin thử nghiệm được cấp qua secret manager hoặc biến môi trường. Không commit mật khẩu hoặc token vào script.

Status cụ thể phụ thuộc authentication entry point và policy. Một endpoint công khai có thể trả 200 không cần token; một endpoint không tồn tại có thể trả 404; gateway cũng có thể thay đổi response.

## 17. Kiểm thử ma trận quyền

Có thể tạo test tích hợp cho từng loại principal:

| Test case | Swagger UI | OpenAPI spec | API protected |
|---|---:|---:|---:|
| Anonymous | 401/403 | 401/403 | 401 |
| User không có DOCS_READER | 403 | 403 | Theo scope API |
| DOCS_READER | 200 | 200 | 401 nếu không có bearer token |
| JWT có orders.read | Theo role docs | Theo role docs | 200 với GET orders |
| JWT chỉ có orders.read gọi POST | Theo role docs | Theo role docs | 403 |
| JWT có orders.write | Theo role docs | Theo role docs | 200/201 tùy operation |

Có thể dùng MockMvc và Spring Security Test để xác minh matcher và authority. Với HTTP Basic, test có thể dùng helper httpBasic; với resource server, có thể dùng jwt() để giả lập scope.

Ví dụ:

~~~java
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
~~~

Và kiểm tra người không có quyền docs:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isUnauthorized());
~~~

Test thực tế cần nạp đúng SecurityFilterChain và cấu hình user. Nếu dùng @WebMvcTest, hãy import cấu hình security và mock các dependency controller cần thiết. Nếu test JWT bằng jwt(), nhớ rằng helper giả lập Authentication; nó không xác minh chữ ký token thật.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Swagger UI tải được nhưng không có operation | Request lấy OpenAPI JSON bị 401/403 hoặc URL spec sai |
| OpenAPI JSON truy cập công khai dù UI bị chặn | Chỉ bảo vệ /swagger-ui/**, quên /v3/api-docs |
| UI bị chặn nhưng API vẫn gọi được | Quyền docs và quyền API là hai chính sách riêng |
| API yêu cầu JWT nhưng Swagger UI không gửi token | Thiếu security requirement hoặc chưa Authorize |
| Nút Authorize không giúp tải spec | Credential cho API không tự được dùng để tải trang/spec |
| Group admin bị lộ | Matcher tổng quát permitAll đứng trước matcher group riêng |
| YAML không được bảo vệ | Quên endpoint /v3/api-docs.yaml |
| Đổi api-docs.path nhưng vẫn truy cập được URL cũ | Matcher hoặc cấu hình proxy chưa đồng bộ |
| Mọi request đều vào docs chain | securityMatcher quá rộng hoặc thứ tự chain sai |
| Docs user gọi được API ghi dữ liệu | Đã cấp nhầm authority hoặc API chain quá rộng |
| Tắt Swagger UI nhưng API vẫn truy cập được | Tắt docs không ảnh hưởng endpoint runtime |
| Browser lỗi CORS | UI và API khác origin nhưng CORS chưa cho phép |

## 19. Quy trình triển khai chính sách

Khi triển khai bảo vệ tài liệu:

1. Liệt kê URL Swagger UI, OpenAPI JSON/YAML và mọi grouped document.
2. Liệt kê API runtime và phân loại endpoint public/protected.
3. Xác định nhóm người được đọc tài liệu và nhóm người được gọi API.
4. Chọn credential cho docs: session, Basic, gateway SSO hoặc cơ chế nội bộ.
5. Cấu hình SecurityFilterChain với matcher cụ thể và thứ tự rõ ràng.
6. Cấu hình API security riêng theo token, role và scope.
7. Cấu hình Swagger UI URL để tải đúng spec và đúng group.
8. Xác minh CORS/CSRF nếu có browser cross-origin hoặc cookie.
9. Kiểm thử anonymous, docs reader, API user thiếu scope và API user đủ quyền.
10. Kiểm tra từ public hostname qua reverse proxy, không chỉ localhost.
11. Rà soát nội dung spec trước khi công bố và theo dõi thay đổi quyền.

## 20. Checklist

- [ ] Đã phân biệt Swagger UI, OpenAPI JSON/YAML và API runtime.
- [ ] Đã liệt kê tất cả docs path, bao gồm YAML và grouped documents.
- [ ] Đã quyết định tài liệu công khai hay nội bộ.
- [ ] Swagger UI và OpenAPI document có quyền truy cập phù hợp.
- [ ] Quyền DOCS_READER tách khỏi scope gọi API.
- [ ] SecurityFilterChain matcher chính xác và thứ tự không chồng lấn.
- [ ] API endpoints được bảo vệ độc lập bằng authentication/authorization.
- [ ] OpenAPI security requirement khớp chính sách API thực tế.
- [ ] Swagger UI tải được spec bằng credential phù hợp.
- [ ] CORS/CSRF đúng với origin và mô hình cookie/token.
- [ ] supportedSubmitMethods không bị xem là biện pháp bảo vệ backend.
- [ ] Đã kiểm tra profile và custom paths trong môi trường triển khai.
- [ ] Đã test anonymous, docs reader, token thiếu scope và token đủ scope.
- [ ] Đã kiểm tra qua reverse proxy/public URL.
- [ ] Không có secret hoặc dữ liệu nhạy cảm trong tài liệu.

## 21. Nguồn tra cứu

- [springdoc-openapi – tài liệu chính thức](https://springdoc.org/)
- [Spring Security – Multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – HTTP Basic](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [OpenAPI Specification – Security Requirement Object](https://spec.openapis.org/oas/latest.html#security-requirement-object)

Swagger UI, OpenAPI JSON/YAML và API runtime là ba bề mặt truy cập khác nhau. Hãy cấp quyền đọc tài liệu riêng, bảo vệ endpoint nghiệp vụ bằng authentication và authorization, đồng thời xác minh Swagger UI có thể tải đúng spec. Chỉ khi kiểm tra cả ba bề mặt bằng request thực tế, chính sách bảo vệ tài liệu mới phản ánh đúng cách ứng dụng được sử dụng.
