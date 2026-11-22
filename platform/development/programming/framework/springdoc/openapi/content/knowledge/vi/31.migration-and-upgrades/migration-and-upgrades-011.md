# Kiểm tra lại bảo mật, proxy, UI và xuất đặc tả trong CI

Nâng cấp Spring Boot, Spring Security hoặc springdoc-openapi có thể làm thay đổi cách ứng dụng công bố tài liệu API, cách request đi qua reverse proxy, cách Swagger UI tải OpenAPI document và cách pipeline sinh file JSON/YAML. Ứng dụng có thể khởi động thành công nhưng tài liệu lại trả 401/403, Swagger UI bị trang trắng, OAuth redirect về HTTP nội bộ, server URL chứa hostname của container hoặc CI lưu nhầm một document rỗng.

Sau mỗi lần nâng cấp cần kiểm tra lại toàn bộ luồng tài liệu từ runtime đến consumer. Bài này tập trung vào bốn mặt:

1. **Security:** ai được xem OpenAPI, mở Swagger UI và thực hiện Try it out?
2. **Reverse proxy:** host, scheme, port, context path và prefix công khai có được nhận diện đúng?
3. **Swagger UI:** giao diện, cấu hình, OAuth redirect và API docs URL có còn hoạt động?
4. **CI export:** pipeline có sinh đúng tài liệu, validate, so sánh và lưu artifact của commit đang build không?

## 1. Vì sao phải kiểm tra lại sau nâng cấp?

Các thành phần có vòng đời riêng. Một thay đổi ở một lớp có thể làm hỏng lớp khác:

~~~mermaid
flowchart TD
    A["Browser / API consumer"] --> B["Reverse proxy / ingress"]
    B --> C["Spring Security filter chain"]
    C --> D["Spring Boot web server"]
    D --> E["springdoc-openapi"]
    E --> F["OpenAPI JSON/YAML"]
    E --> G["Swagger UI"]
    H["CI build"] --> I["Start app with docs profile"]
    I --> E
    F --> J["Validate / semantic diff"]
    J --> K["Store release artifact"]
~~~

Ví dụ:

- Spring Security thay đổi matcher khiến /v3/api-docs bị bảo vệ ngoài dự kiến.
- Reverse proxy đổi cách gửi X-Forwarded-*; OpenAPI servers sinh URL nội bộ thay vì URL public.
- Springdoc nâng major làm thay đổi starter, default path hoặc Swagger UI assets.
- API docs path được đổi nhưng springdoc.swagger-ui.config-url vẫn trỏ tới đường dẫn cũ.
- CI chạy profile khác production nên file OpenAPI thiếu operation hoặc chứa endpoint nội bộ.
- Gradle/Maven plugin không còn khởi chạy ứng dụng theo cách cũ sau khi nâng version.

Không chỉ kiểm tra ứng dụng có trả HTTP 200. Cần xác minh đúng người dùng nhận đúng tài liệu, đúng URL và đúng nội dung.

## 2. Xác định nhánh springdoc theo Spring Boot

Trước khi kiểm tra cấu hình, xác nhận phiên bản nền tảng và starter:

| Spring Boot | Nhánh springdoc | Ghi chú migration |
|---|---|---|
| 2.x và 1.x | springdoc 1.8.0 là nhánh open-source cuối | Không dùng starter 2.x/3.x |
| 3.x | springdoc 2.x | Dùng các starter springdoc-openapi-starter-* tương ứng |
| 4.x | springdoc 3.x | Kiểm tra lại starter, dependency bắc cầu và các thay đổi của Spring Framework 7 |

Không chỉ đổi version trong dependency rồi kết luận migration hoàn tất. Kiểm tra dependency tree để phát hiện hai nhánh springdoc cùng tồn tại, swagger-core bị override hoặc Swagger UI WebJar cũ còn được kéo vào.

Với Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3,org.webjars
~~~

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency springdoc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-ui --configuration runtimeClasspath
~~~

Ghi lại các giá trị trước và sau nâng cấp:

- Spring Boot và Spring Framework.
- springdoc starter và phiên bản swagger-core.
- Swagger UI assets được đóng gói.
- Spring Security.
- Web server (Tomcat, Jetty hoặc Reactor Netty).
- Java runtime và Gradle/Maven wrapper.

Ma trận tương thích chính thức của springdoc phân biệt rõ Boot 2, Boot 3 và Boot 4. Dùng đúng tài liệu theo nhánh đang chạy thay vì sao chép property từ hướng dẫn của major khác.

## 3. Kiểm tra lại security cho OpenAPI và Swagger UI

Hai endpoint thường được springdoc phục vụ mặc định:

| Endpoint | Nội dung |
|---|---|
| /v3/api-docs | OpenAPI document dạng JSON |
| /v3/api-docs.yaml | OpenAPI document dạng YAML |
| /v3/api-docs/swagger-config | Cấu hình mà Swagger UI dùng để tải document |
| /swagger-ui.html | URL vào giao diện Swagger UI |
| /swagger-ui/** | HTML, JavaScript, CSS và tài nguyên giao diện |

Đường dẫn thực tế có thể khác nếu ứng dụng đặt context path hoặc tùy chỉnh springdoc properties. Hãy kiểm tra endpoint sau khi cấu hình, không giả định path mặc định luôn đúng.

### Chọn chính sách truy cập theo môi trường

Trước khi nâng cấp, xác định tài liệu API thuộc một trong các mô hình:

- Public documentation: ai cũng có thể xem tài liệu, nhưng API nghiệp vụ vẫn có authorization riêng.
- Internal documentation: chỉ người dùng hoặc mạng nội bộ được phép xem.
- Restricted production documentation: tắt Swagger UI và/hoặc API docs ở production, chỉ xuất artifact trong CI.
- Documentation behind SSO: yêu cầu đăng nhập và quyền riêng cho nhóm phát triển hoặc vận hành.

OpenAPI document có thể tiết lộ path nội bộ, tên schema, luồng xác thực, response và operation chưa công bố. Việc cho phép đọc tài liệu không tự cấp quyền gọi API, nhưng thông tin này vẫn có thể hữu ích cho người dò tìm bề mặt tấn công.

### Ví dụ tách security chain cho tài liệu nội bộ

Ví dụ sau yêu cầu role API_DOCS cho Swagger UI và API docs, còn các request khác đi qua chain ứng dụng:

~~~java
@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiDocumentation(HttpSecurity http) throws Exception {
        return http
            .securityMatcher(
                "/swagger-ui.html",
                "/swagger-ui/**",
                "/v3/api-docs",
                "/v3/api-docs.yaml",
                "/v3/api-docs/**"
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().hasRole("API_DOCS")
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain application(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là ví dụ cho ứng dụng Servlet dùng Basic Authentication ở vùng tài liệu và form login ở vùng ứng dụng. Thay authentication mechanism theo hệ thống thật. Nếu dùng OAuth2 Resource Server, SSO hoặc API gateway, cấu hình matcher và filter chain phải khớp cơ chế đó.

securityMatcher giới hạn những request mà chain thứ nhất xử lý; requestMatchers bên trong chain xác định quyền. Chain thứ hai chỉ xử lý request không khớp chain thứ nhất. Thứ tự @Order rất quan trọng.

Nếu tài liệu được phép public, có thể dùng permitAll() cho đúng các path tài liệu. Không mở toàn bộ /** chỉ để Swagger UI hoạt động. Cũng không thêm web.ignoring() cho tất cả tài nguyên tĩnh nếu điều đó bỏ qua các filter cần thiết.

### Kiểm tra CSRF và Try it out

Swagger UI có thể gửi GET, POST, PUT, PATCH và DELETE thông qua Try it out. Nếu ứng dụng dùng session/cookie authentication, Spring Security CSRF protection có thể chặn các request thay đổi trạng thái khi UI không gửi CSRF token.

Sau nâng cấp hãy kiểm tra:

- Trang Swagger UI có tải được không?
- Authorize có gửi credential đúng scheme không?
- Request GET có thành công không?
- Request POST/PUT/PATCH/DELETE có nhận CSRF token khi ứng dụng yêu cầu không?
- API trả 401, 403 hay 404 trong từng trường hợp?

Không tắt CSRF toàn cục chỉ để làm nút Try it out hoạt động. Với session-based application, tích hợp token theo cơ chế CSRF của Spring Security. Với API stateless dùng bearer token, chỉ cân nhắc miễn CSRF cho đúng API matcher khi kiến trúc xác thực thực sự không dựa vào cookie tự động gửi kèm.

springdoc có cấu hình CSRF cho Swagger UI, gồm bật hỗ trợ và tên cookie/header. Ví dụ:

~~~yaml
springdoc:
  swagger-ui:
    csrf:
      enabled: true
      cookie-name: XSRF-TOKEN
      header-name: X-XSRF-TOKEN
~~~

Tên cookie và header phải khớp cấu hình CSRF thực tế của ứng dụng. Kiểm tra property này trong tài liệu của đúng nhánh springdoc đang dùng.

## 4. Kiểm tra CORS sau khi đổi domain hoặc proxy

Nếu Swagger UI được phục vụ ở một origin còn API ở origin khác, browser sẽ áp dụng CORS. Những request có Authorization header hoặc content type không đơn giản có thể tạo preflight OPTIONS.

Spring Security yêu cầu CORS được xử lý trước bước authorization để preflight không bị từ chối chỉ vì chưa có cookie/session. Có thể cấu hình CORS:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration configuration = new CorsConfiguration();
    configuration.setAllowedOrigins(
        List.of("https://docs.example.com")
    );
    configuration.setAllowedMethods(
        List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
    );
    configuration.setAllowedHeaders(
        List.of("Authorization", "Content-Type", "X-XSRF-TOKEN")
    );
    configuration.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", configuration);
    return source;
}
~~~

Trong Security chain:

~~~java
http.cors(Customizer.withDefaults());
~~~

Chỉ cho phép origin thực sự cần thiết. Khi allowCredentials bật, không dùng wildcard origin. Nếu Swagger UI và API cùng origin, không cần mở CORS chỉ vì đang dùng Swagger UI.

## 5. Kiểm tra forwarded headers và reverse proxy

Khi ứng dụng chạy sau ingress, load balancer hoặc reverse proxy, ứng dụng có thể nhìn thấy:

~~~text
http://10.20.0.15:8080/internal
~~~

Trong khi consumer phải truy cập:

~~~text
https://api.example.com/platform
~~~

Proxy có thể gửi các header:

- Forwarded theo RFC 7239.
- X-Forwarded-Host.
- X-Forwarded-Port.
- X-Forwarded-Proto.
- X-Forwarded-For.
- X-Forwarded-Prefix.

Các header này ảnh hưởng redirect, link được tạo trong HTML/JSON và URL server được springdoc suy ra. Nếu ứng dụng không xử lý chúng đúng, Swagger UI có thể tải API docs từ host nội bộ hoặc tạo Try it out request tới HTTP thay vì HTTPS.

### Property của Spring Boot 3.x

Spring Boot 3.5 dùng server.forward-headers-strategy:

~~~yaml
server:
  forward-headers-strategy: NATIVE
~~~

Các giá trị thường dùng:

| Giá trị | Ý nghĩa |
|---|---|
| NONE | Không xử lý forwarded headers |
| NATIVE | Dùng khả năng xử lý của web server |
| FRAMEWORK | Dùng Spring Framework ForwardedHeaderFilter hoặc ForwardedHeaderTransformer |

NATIVE thường phù hợp khi Tomcat/Jetty/Netty hỗ trợ header mà proxy gửi. FRAMEWORK dùng xử lý tổng quát của Spring Framework nếu web server không đáp ứng.

### Property của Spring Boot 4.x

Spring Boot 4 chuyển sang namespace mới:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: web-server
        use-prefix: true
~~~

Các lựa chọn strategy hiện hành:

| Giá trị | Ý nghĩa |
|---|---|
| none | Không xử lý forwarded headers |
| web-server | Dùng hỗ trợ của web server |
| framework | Dùng hỗ trợ forwarded header của Spring Framework |

Trong Boot 4, use-prefix: true bật xử lý X-Forwarded-Prefix. Mặc định prefix này bị bỏ qua. Nếu proxy bỏ /platform trước khi forward tới ứng dụng nhưng không khôi phục prefix, các link Swagger UI và OpenAPI có thể bị thiếu đoạn đường dẫn công khai.

Không giữ nguyên server.forward-headers-strategy khi chuyển từ Boot 3 sang Boot 4 mà không kiểm tra property mới. Property cũ có thể không còn được bind như mong muốn.

### Chỉ tin forwarded headers từ proxy đáng tin cậy

Forwarded headers có thể bị client gửi giả nếu proxy không xóa header do người dùng cung cấp rồi tự ghi lại giá trị chuẩn. Hãy cấu hình ingress/proxy:

1. Xóa hoặc ghi đè Forwarded và X-Forwarded-* từ request bên ngoài.
2. Tạo lại header từ kết nối thực tế và cấu hình route.
3. Chỉ cho phép ứng dụng nhận traffic từ proxy đáng tin cậy.
4. Nếu dùng Tomcat, cấu hình trusted/internal proxies phù hợp.
5. Không đặt trust-all proxy trong production.

Không bật forwarded-header processing một cách mù quáng khi ứng dụng có thể bị truy cập trực tiếp từ Internet.

### Kiểm tra context path và prefix

Nếu ứng dụng dùng server.servlet.context-path, spring.webflux.base-path hoặc proxy strip prefix, phải kiểm tra đường dẫn thực tế ở cả bốn nơi:

- URL Swagger UI.
- URL swagger-config.
- URL /v3/api-docs hoặc custom API docs path.
- servers trong OpenAPI document.

Nếu khai báo servers tĩnh bằng @OpenAPIDefinition, giá trị đó có thể không phản ánh URL được suy ra từ request. Sau nâng cấp, kiểm tra document JSON thực tế thay vì giả định forwarded headers sẽ tự sửa mọi server URL.

## 6. Kiểm tra các đường dẫn springdoc và Swagger UI

Các property quan trọng:

~~~yaml
springdoc:
  api-docs:
    path: /v3/api-docs
    enabled: true
  swagger-ui:
    path: /swagger-ui.html
    enabled: true
    config-url: /v3/api-docs/swagger-config
    oauth2-redirect-url: /swagger-ui/oauth2-redirect.html
~~~

Tên property YAML dùng kebab-case; property trong application.properties có thể viết theo dạng dot notation tương ứng.

Sau khi nâng cấp, xác minh:

- springdoc.api-docs.path có đúng path mà security matcher cho phép không?
- springdoc.swagger-ui.config-url có trỏ tới đúng swagger-config endpoint không?
- OAuth redirect URL có đúng host, HTTPS scheme, context path và prefix không?
- Reverse proxy có rewrite URL và trả MIME type cho JavaScript/CSS đúng không?
- Không có hai dependency Swagger UI khác phiên bản cùng được đóng gói không?

Nếu đổi API docs path mà không cập nhật security matcher hoặc config-url, Swagger UI có thể tải được HTML nhưng không tải được OpenAPI document.

### Tùy chọn giao diện cần kiểm tra lại

| Property | Điều cần xác minh |
|---|---|
| springdoc.swagger-ui.path | Đường dẫn HTML có redirect đúng không |
| springdoc.swagger-ui.config-url | URL cấu hình có tồn tại và được phép truy cập không |
| springdoc.swagger-ui.oauth2-redirect-url | OAuth callback có đúng URL public không |
| springdoc.swagger-ui.try-it-out-enabled | Có bật mặc định Try it out theo policy không |
| springdoc.swagger-ui.supported-submit-methods | Những HTTP method nào được phép gửi từ UI |
| springdoc.swagger-ui.persist-authorization | Credential có được giữ qua refresh hay không |
| springdoc.swagger-ui.deep-linking | Link tới tag/operation có hoạt động không |
| springdoc.swagger-ui.doc-expansion | Mức mở rộng mặc định có phù hợp không |

tryItOutEnabled chỉ điều khiển trạng thái mặc định. supportedSubmitMethods giới hạn các method có thể thử; mảng rỗng sẽ tắt Try it out nhưng không xóa operation khỏi document. Khi cấu hình qua Spring Boot, dùng prefix springdoc.swagger-ui và dạng property mà phiên bản springdoc hỗ trợ; YAML có thể dùng kebab-case tương ứng với tên option camelCase của Swagger UI.

Không bật queryConfigEnabled chỉ để tiện override cấu hình qua URL. Tùy chọn này bị vô hiệu hóa từ springdoc 1.6.0 và có cảnh báo bảo mật liên quan.

### Credential persistence

persistAuthorization mặc định tắt. Nếu bật, Swagger UI có thể giữ dữ liệu Authorize sau khi refresh. Trước khi giữ lại tùy chọn này sau migration, cần xem:

- Máy tính có dùng chung hoặc trình duyệt kiosk không?
- Token có được lưu lâu hơn mong muốn không?
- Chính sách logout và session expiry có xóa credential khỏi UI không?
- OAuth flow có sử dụng PKCE khi phù hợp không?

Không dùng persistAuthorization để khắc phục lỗi token bị mất mà chưa đánh giá rủi ro lưu credential.

## 7. Kiểm tra lại OpenAPI security scheme

Swagger UI chỉ hiển thị nút Authorize theo security scheme mà OpenAPI document mô tả. Spring Security bảo vệ request runtime; @SecurityScheme và security mô tả cơ chế bảo mật trong tài liệu. Hai lớp phải nhất quán.

Ví dụ Bearer JWT:

~~~java
@Configuration
@OpenAPIDefinition(
    security = @SecurityRequirement(name = "bearerAuth")
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class OpenApiSecurityConfiguration {
}
~~~

Sau nâng cấp, kiểm tra trong JSON:

- components.securitySchemes.bearerAuth còn tồn tại không?
- security ở cấp root hoặc operation có đúng phạm vi không?
- Endpoint public có vô tình bị gắn security requirement không?
- Endpoint cần role/scope riêng có được mô tả rõ không?
- Swagger UI gửi Authorization: Bearer ... đúng không?

Khai báo security scheme không bật xác thực ở runtime. Ngược lại, Spring Security có thể bắt buộc đăng nhập nhưng OpenAPI không khai báo security, khiến client generator không biết cách gửi credential.

## 8. Bật hoặc tắt tài liệu theo môi trường

Có thể tắt API docs endpoint và Swagger UI độc lập:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

Nếu production không phục vụ tài liệu, đặt cấu hình này trong profile production và xác minh cả /v3/api-docs, /v3/api-docs.yaml, /v3/api-docs/swagger-config, /swagger-ui.html và /swagger-ui/** đều không còn truy cập được.

Nếu pipeline cần sinh tài liệu, dùng profile riêng:

~~~yaml
# application-openapi.yml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

CI chỉ cần API docs endpoint; không cần phải mở Swagger UI. Điều này giảm bề mặt giao diện trong tiến trình tạm dùng để xuất tài liệu.

Không dùng profile openapi để vô tình bật các endpoint quản trị hoặc debug không có trong production. So sánh cấu hình profile với cấu hình triển khai và ghi rõ các khác biệt có chủ đích.

## 9. Xuất OpenAPI trong CI sau nâng cấp

Mục tiêu của CI là tạo artifact từ đúng commit, đúng profile và đúng API group. Với springdoc-openapi-gradle-plugin 2.x, task generateOpenApiDocs tự khởi động ứng dụng, tải document và dừng ứng dụng. Task cũ forkedSpringBootRun/forkedSpringBootStop của plugin 1.x không còn được dùng trong 2.x.

Ví dụ cấu hình Kotlin DSL:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "4.2.0"
    id("org.springdoc.openapi-gradle-plugin") version "2.1.0"
}

openApi {
    apiDocsUrl.set("http://localhost:8080/v3/api-docs")
    outputDir.set(layout.buildDirectory.dir("openapi"))
    outputFileName.set("service-openapi.json")
    waitTimeInSeconds.set(90)

    customBootRun {
        args.set(listOf("--spring.profiles.active=openapi"))
    }
}
~~~

Ví dụ version Spring Boot cần khớp release đang dùng trong dự án; không sao chép số version này nếu dự án chưa nâng lên Boot 4.2. Plugin cần Gradle 8.0 trở lên. Từ plugin 2.1, build phải khai báo Spring Boot Gradle plugin tường minh.

Chạy:

~~~bash
./gradlew clean test generateOpenApiDocs
~~~

Kết quả với cấu hình trên:

~~~text
build/openapi/service-openapi.json
~~~

Nếu ứng dụng có nhiều group, cấu hình groupedApiMappings và lưu từng document thành artifact riêng. Không gộp public/admin/partner API vào một file nếu chúng có audience hoặc policy khác nhau.

### Cấu hình profile và port ổn định

CI cần kiểm soát:

- Spring profile được dùng để sinh tài liệu.
- Port và context path của ứng dụng tạm.
- API docs path tùy chỉnh.
- Database/service test mà ứng dụng cần để khởi động.
- Feature flag làm thay đổi controller hoặc schema.
- Server URL và forwarded headers.
- Security profile cho phép tiến trình CI tải tài liệu.

Nếu CI dùng random port, apiDocsUrl phải nhận được port thực tế hoặc dùng cấu hình port cố định riêng cho job. Tránh hai job đồng thời tranh chấp cùng port trên một runner.

Không để task CI phụ thuộc vào một ứng dụng đã chạy sẵn từ bước khác nếu plugin được cấu hình để tự khởi động ứng dụng. Điều đó có thể khiến task tải nhầm document từ tiến trình cũ hoặc môi trường khác.

## 10. Validate và so sánh file sau khi export

Sau khi sinh tài liệu, kiểm tra file tồn tại, không rỗng và parse được:

~~~bash
test -s build/openapi/service-openapi.json
jq -e '.openapi and .info.title and (.paths | length > 0)' \
  build/openapi/service-openapi.json
~~~

Các kiểm tra cơ bản cần xác minh:

- openapi có giá trị version hợp lệ.
- info.title và info.version đúng release.
- servers chứa URL phù hợp môi trường công bố.
- paths không rỗng và có đủ operation dự kiến.
- components.securitySchemes và security đúng policy.
- Không xuất hiện internal/admin endpoint ngoài phạm vi.

Tiếp theo, chạy OpenAPI validator phù hợp với version document và semantic diff với baseline đã được review. Nếu có breaking change, CI cần tạo report và yêu cầu review; không tự động cập nhật baseline chỉ để làm pipeline xanh.

Ví dụ kiểm tra semantic diff bằng oasdiff:

~~~bash
oasdiff validate build/openapi/service-openapi.json
oasdiff breaking \
  api/openapi-baseline.yaml \
  build/openapi/service-openapi.json
oasdiff changelog \
  api/openapi-baseline.yaml \
  build/openapi/service-openapi.json
~~~

Lưu file OpenAPI và report diff làm artifact gắn với commit/build number. Artifact của CI không đồng nghĩa đã publish tài liệu lên production portal.

## 11. Pipeline mẫu

Một pipeline có thể tách build, export, validate và lưu artifact:

~~~yaml
steps:
  - name: Build and test
    run: ./gradlew clean test

  - name: Generate OpenAPI
    run: ./gradlew generateOpenApiDocs

  - name: Validate OpenAPI
    run: oasdiff validate build/openapi/service-openapi.json

  - name: Check breaking changes
    run: >
      oasdiff breaking --fail-on ERR
      api/openapi-baseline.yaml
      build/openapi/service-openapi.json

  - name: Upload OpenAPI artifact
    uses: actions/upload-artifact@v4
    with:
      name: openapi-description
      path: build/openapi/service-openapi.json
~~~

Đây là ví dụ dạng GitHub Actions; CI khác có thể thay bước upload bằng artifact store tương ứng. Đảm bảo lệnh oasdiff có sẵn trên runner và version được pin theo policy của dự án.

Nên lưu thêm metadata:

- Commit SHA.
- Build number.
- Spring Boot và springdoc version.
- Spring profile và API group.
- OpenAPI info.version.
- Ngày tạo snapshot.

Không đưa secret, token hoặc environment variable nhạy cảm vào artifact metadata.

## 12. Bộ kiểm tra hồi quy sau nâng cấp

Chạy cùng một ma trận test trước và sau khi nâng cấp:

| Nhóm | Kiểm tra | Kết quả mong đợi |
|---|---|---|
| Security | Người chưa đăng nhập truy cập docs nội bộ | 401 hoặc 403 theo policy |
| Security | Người có role tài liệu truy cập docs | 200 |
| Security | Người có role tài liệu gọi API nghiệp vụ không được cấp quyền | 403 |
| Security | API docs bị tắt trong production profile | Endpoint không được phục vụ |
| Proxy | Truy cập qua HTTPS public hostname | Redirect và link dùng HTTPS |
| Proxy | Truy cập qua prefix công khai | UI và API docs giữ đúng prefix |
| Proxy | Truy cập trực tiếp bằng header giả từ Internet | Proxy xóa/ghi đè header không đáng tin |
| UI | Swagger UI tải HTML, JS, CSS | Không có 404 hoặc lỗi MIME |
| UI | Swagger config và OpenAPI document | Tải đúng URL và đúng API group |
| UI | Authorize với bearer/OAuth | Gửi đúng credential và redirect URI |
| UI | Try it out GET và write operation | Kết quả khớp auth, CSRF và CORS policy |
| Export | CI sinh file JSON/YAML | File tồn tại, không rỗng, parse được |
| Export | servers và paths | Đúng URL public và đúng operation |
| Contract | Semantic diff với baseline | Breaking change được báo và review |
| Artifact | File và report được lưu | Gắn với commit/build chính xác |

### Smoke test bằng curl

Kiểm tra API docs endpoint:

~~~bash
curl -i https://api.example.com/v3/api-docs
curl -i https://api.example.com/v3/api-docs.yaml
~~~

Kiểm tra Swagger UI:

~~~bash
curl -I https://api.example.com/swagger-ui.html
curl -I https://api.example.com/swagger-ui/index.html
curl -I https://api.example.com/v3/api-docs/swagger-config
~~~

Nếu tài liệu được bảo vệ, chạy thêm request không credential và request có credential hợp lệ. Ghi nhận status code và Location header của redirect. Không chỉ kiểm tra bằng browser đã có session vì session cũ có thể che giấu lỗi authentication.

### Kiểm tra OpenAPI server URL qua proxy

Tải document qua public URL rồi xem field servers:

~~~bash
curl -fsS https://api.example.com/platform/v3/api-docs \
  | jq '.servers, (.paths | keys[0:5])'
~~~

Kết quả phải dùng hostname, scheme và prefix mà consumer thực sự gọi. Nếu servers bị hard-code, kiểm tra annotation/configuration đã khai báo thay vì chỉ sửa forwarded header.

## 13. Kiểm tra riêng các thay đổi cấu hình phổ biến

| Thay đổi sau migration | Hồi quy thường gặp | Cách xác minh |
|---|---|---|
| Spring Boot 3 lên 4 | Property forwarded header cũ không còn đúng namespace | Kiểm tra server.request.header.forwarded.* |
| springdoc 2 lên 3 | Starter, dependency và UI assets đổi major | Kiểm tra dependency tree và endpoint mặc định |
| Spring Security nâng major | Matcher hoặc filter chain đổi hành vi | Test từng role với MockMvc hoặc HTTP thật |
| Đổi context path | Swagger config URL thiếu context path | Kiểm tra redirect và Network tab |
| Thêm ingress prefix | X-Forwarded-Prefix bị bỏ qua | Bật hỗ trợ prefix đúng Boot version |
| Bật OAuth2/SSO mới | Redirect URI hoặc CORS sai origin | Test authorization code/PKCE và callback |
| Đổi docs path | Security matcher hoặc config-url vẫn cũ | Kiểm tra cả swagger-config và JSON/YAML |
| Đổi Gradle plugin | Task lifecycle hoặc output path khác | Chạy task trên runner sạch và kiểm tra artifact |
| Đổi API group | Export chỉ chứa một group hoặc sai filter | Kiểm tra từng file và path set |

## 14. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| /v3/api-docs trả 401 | Endpoint nằm sau authentication | Kiểm tra security matcher và quyền truy cập |
| /v3/api-docs trả 403 dù đã đăng nhập | Thiếu authority/role hoặc CSRF cho request không an toàn | Kiểm tra role và request method |
| Swagger UI HTML mở nhưng trang trắng | Config URL hoặc document URL sai | Xem Network/Console và tải swagger-config trực tiếp |
| Swagger UI bị 404 sau deploy | Context path hoặc proxy prefix bị mất | Kiểm tra redirect và forwarded prefix |
| servers chứa http://localhost:8080 | Forwarded headers không được xử lý hoặc servers hard-code | Kiểm tra proxy và OpenAPI configuration |
| OAuth callback về host nội bộ | Scheme/host được suy ra sai | Kiểm tra forwarded host/proto và redirect URI đăng ký |
| Try it out báo CORS | Origin, method hoặc Authorization header chưa được cho phép | Cấu hình CORS cụ thể và xử lý preflight trước security |
| Try it out POST bị 403 | CSRF token thiếu hoặc role không đủ | Kiểm tra CSRF integration và authorization |
| Swagger UI không có Authorize | OpenAPI thiếu security scheme | Kiểm tra components.securitySchemes và security |
| CI export ra file rỗng | App chưa sẵn sàng, sai profile hoặc API docs bị tắt | Kiểm tra startup log, wait time và docs profile |
| CI export thiếu operation | Profile, group hoặc path filter khác | So sánh config và path set với baseline |
| CI tải document từ ứng dụng cũ | Port bị dùng bởi tiến trình khác | Dùng port riêng, dọn tiến trình và kiểm tra process log |
| Artifact dùng URL nội bộ | CI sinh document từ host/port nội bộ | Cấu hình server URL cho artifact hoặc sinh qua proxy test |
| Diff lớn sau nâng springdoc | Schema serialization hoặc model converter thay đổi | Validate, semantic diff và review schema |
| Production vẫn mở docs ngoài ý muốn | Profile disable không được nạp hoặc config override | Kiểm tra effective configuration và smoke test production profile |

## 15. Quy trình migration có thể lặp lại

Trước khi nâng cấp:

1. Lưu snapshot OpenAPI hiện tại.
2. Ghi lại endpoint, security policy, Swagger UI config và public server URL.
3. Lưu dependency tree và phiên bản Spring Boot/springdoc/Security.
4. Ghi lại kết quả smoke test qua proxy và trong mạng nội bộ.
5. Ghi lại output path và lệnh export CI.

Sau khi nâng cấp:

1. Xác nhận dependency graph chỉ có một nhánh springdoc phù hợp.
2. Kiểm tra effective configuration, đặc biệt forwarded headers và API docs path.
3. Chạy test security cho docs, UI, API và các role liên quan.
4. Truy cập qua reverse proxy thật hoặc môi trường staging có cấu hình tương đương.
5. Mở Swagger UI, kiểm tra config URL, Authorize, OAuth redirect và Try it out.
6. Sinh JSON/YAML từ CI bằng profile và group đã thống nhất.
7. Validate document, kiểm tra servers, paths, security và schema.
8. Chạy semantic diff với snapshot trước nâng cấp.
9. Review breaking changes và cập nhật baseline sau khi được chấp thuận.
10. Chỉ publish artifact sau khi các kiểm tra bắt buộc đều đạt.

Giữ lại kết quả trước/sau nâng cấp giúp truy nguyên khi một lỗi chỉ xuất hiện ở staging hoặc production.

## 16. Checklist hoàn tất migration

- [ ] Spring Boot và springdoc nằm trong nhánh tương thích.
- [ ] Dependency tree không có starter hoặc swagger-core bị trùng/override ngoài ý muốn.
- [ ] API docs path và Swagger UI path đã được xác minh.
- [ ] Security matcher bao phủ đúng docs, config và static UI assets.
- [ ] Quyền xem tài liệu được tách khỏi quyền gọi API nghiệp vụ.
- [ ] CSRF không bị tắt toàn cục chỉ để hỗ trợ Try it out.
- [ ] CORS preflight hoạt động trước authorization khi có cross-origin.
- [ ] Security scheme trong OpenAPI khớp authentication runtime.
- [ ] OAuth redirect URL dùng đúng HTTPS host và public prefix.
- [ ] Forwarded-header property đúng với Boot major.
- [ ] Proxy xóa/ghi đè forwarded headers không đáng tin.
- [ ] X-Forwarded-Prefix được xử lý khi proxy strip prefix.
- [ ] servers trong document dùng URL public dự kiến.
- [ ] Swagger UI tải đúng swagger-config và OpenAPI document.
- [ ] persistAuthorization và queryConfigEnabled được review theo policy bảo mật.
- [ ] Production profile tắt hoặc bảo vệ docs theo chủ đích.
- [ ] CI sinh tài liệu từ commit/profile/group xác định.
- [ ] Artifact JSON/YAML parse được và có đủ operation.
- [ ] Semantic diff được review trước khi cập nhật baseline.
- [ ] Report và artifact được lưu cùng commit/build.

## 17. Tài liệu tham khảo chính thức

- [springdoc-openapi Compatibility](https://github.com/springdoc/springdoc-openapi#compatibility): chọn nhánh springdoc theo Spring Boot.
- [springdoc-openapi v2 Properties](https://springdoc.org/v2/properties.html): cấu hình cho Spring Boot 3.x.
- [springdoc-openapi Core Properties](https://springdoc.org/core-properties.html): cấu hình API docs hiện hành.
- [Swagger UI Properties](https://springdoc.org/ui-properties.html): path, config URL, OAuth redirect, Try it out, CSRF và giao diện.
- [Spring Boot 3.5 – Running Behind a Front-end Proxy](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): server.forward-headers-strategy và forwarded headers.
- [Spring Boot 4 – Running Behind a Front-end Proxy](https://docs.spring.io/spring-boot/how-to/webserver.html): server.request.header.forwarded.* và forwarded prefix.
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): matcher và thứ tự authorization rule.
- [Spring Security – CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): xử lý preflight trước security.
- [springdoc-openapi Gradle Plugin](https://github.com/springdoc/springdoc-openapi-gradle-plugin): generateOpenApiDocs và cấu hình export.

## Kết luận

Migration hoàn tất khi ứng dụng vừa chạy đúng vừa công bố đúng hợp đồng ở môi trường thực tế. Hãy kiểm tra security cho từng endpoint tài liệu, forwarded headers và prefix sau reverse proxy, Swagger UI cùng OAuth/CSRF/CORS, rồi sinh OpenAPI từ CI bằng profile và API group đã kiểm soát. Đặc biệt, property proxy của Spring Boot 3 và Boot 4 khác namespace; giữ cấu hình cũ sau khi nâng major có thể làm server URL và redirect sai dù ứng dụng vẫn trả 200. Cuối cùng, validate document, kiểm tra servers/paths/security, so sánh semantic diff với baseline và lưu artifact theo commit trước khi publish.
