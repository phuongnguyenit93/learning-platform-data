# Quan hệ giữa cấu hình CORS riêng của exporter và Spring MVC trong Spring Data REST

## Mục tiêu

Một ứng dụng có thể đồng thời cung cấp hai nhóm endpoint:

- **Spring Data REST resources:** collection, item, search và association được xuất từ repository.
- **Spring MVC endpoints:** controller do ứng dụng tự viết, ví dụ báo cáo, upload, dashboard hoặc API nghiệp vụ.

Cả hai đều chạy trong ứng dụng Spring MVC, nhưng cấu hình CORS của chúng không mặc nhiên dùng chung một registry.

Điểm quan trọng nhất trong tài liệu Spring Data REST là: **CORS đã cấu hình cho Spring MVC không được tự động áp dụng cho Spring Data REST.** Nếu ứng dụng dùng cả repository exporter và controller riêng, cần xác định rõ endpoint thuộc nhóm nào và cấu hình CORS tương ứng.

Bài này giải thích sự khác biệt giữa hai cơ chế, cách cấu hình từng bên, cách phối hợp với `@CrossOrigin` và Spring Security, cũng như cách kiểm thử preflight để tránh lỗi khi browser gọi API từ origin khác.

## 1. CORS giải quyết vấn đề gì?

CORS (Cross-Origin Resource Sharing) là cơ chế để server khai báo những origin nào được phép đọc response từ browser. Origin gồm ba thành phần:

- Scheme, ví dụ `https`.
- Host, ví dụ `app.example.com`.
- Port, ví dụ `443` hoặc `8080`.

Hai URL có cùng host nhưng khác scheme hoặc port vẫn có thể là hai origin khác nhau. Ví dụ:

~~~text
Frontend: https://app.example.com
Backend:  https://api.example.com
~~~

Browser xem đây là cross-origin request. Nếu frontend dùng JavaScript để gọi backend, server phải trả các CORS response headers phù hợp để browser cho phép script đọc response.

Ví dụ header:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Authorization, Content-Type
~~~

CORS là chính sách do browser thực thi. Nó không phải cơ chế xác thực hoặc phân quyền của server. Một client không chạy trong browser, chẳng hạn curl, Postman hoặc một backend service khác, không bị Same-Origin Policy của browser ràng buộc.

Vì vậy, cấu hình CORS đúng không thay thế Spring Security, authorization hoặc kiểm tra quyền trên từng tài nguyên.

## 2. Hai nhóm endpoint trong cùng ứng dụng

Giả sử ứng dụng có:

~~~text
Spring Data REST:
  /api/people
  /api/people/42
  /api/people/search
  /api/people/42/address

Spring MVC:
  /mvc-api/reports
  /mvc-api/imports
  /mvc-api/dashboard
~~~

Spring Data REST dùng repository exporter và các HandlerMapping riêng của nó để tạo REST resources. Spring MVC xử lý các controller được khai báo bằng `@RestController`, `@Controller` hoặc các controller mapping tương ứng.

Do đó, không nên nghĩ rằng chỉ cần cấu hình một `WebMvcConfigurer.addCorsMappings("/**")` là mọi endpoint trong ứng dụng đều tự động được Spring Data REST chấp nhận.

Tài liệu Spring Data REST ghi rõ cấu hình CORS hiện có của Spring Web MVC không được áp dụng cho Spring Data REST. Spring Data REST cung cấp registry riêng thông qua callback `RepositoryRestConfigurer.configureRepositoryRestConfiguration(config, cors)`.

## 3. Cấu hình CORS riêng cho Spring Data REST exporter

Cách cấu hình toàn cục cho repository resources là triển khai `RepositoryRestConfigurer` và sử dụng tham số `CorsRegistry` mà framework truyền vào:

~~~java
@Component
public class DataRestCorsConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        cors.addMapping("/people/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods(
                "GET", "POST", "PUT", "PATCH", "DELETE")
            .allowedHeaders(
                "Authorization",
                "Content-Type",
                "If-Match",
                "If-None-Match")
            .exposedHeaders("ETag", "Location")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

Các import chính:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
~~~

Ví dụ giới hạn CORS cho các resource có path bắt đầu bằng `/people/`:

- `allowedOrigins`: origin của frontend được phép gọi.
- `allowedMethods`: các HTTP method mà browser được phép thực hiện.
- `allowedHeaders`: request headers mà frontend được phép gửi.
- `exposedHeaders`: response headers mà JavaScript được phép đọc.
- `allowCredentials`: có cho phép credential như cookie hay HTTP authentication gắn với browser request hay không.
- `maxAge`: thời gian browser có thể cache kết quả preflight, tính bằng giây.

Nếu ứng dụng đặt Spring Data REST base path, ví dụ `/api`, hãy kiểm tra mapping pattern có khớp với path mà handler thực tế nhận được trong ứng dụng. Dùng integration test với URL đã triển khai để xác nhận mapping thay vì đoán từ tên repository.

Tài liệu Spring Data REST dùng ví dụ `cors.addMapping("/person/**")` trong callback này. Đây là registry dành riêng cho exporter, không phải registry lấy từ `WebMvcConfigurer`.

## 4. Cấu hình CORS cho Spring MVC controllers

Với controller do ứng dụng tự viết, cấu hình toàn cục thông qua `WebMvcConfigurer.addCorsMappings`:

~~~java
@Configuration
public class MvcCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/mvc-api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT", "DELETE")
            .allowedHeaders(
                "Authorization",
                "Content-Type",
                "X-Request-Id")
            .exposedHeaders("Location")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

Các import chính:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
~~~

Cấu hình này áp dụng cho các handler được Spring MVC quản lý và khớp với path pattern `/mvc-api/**`.

Có thể dùng `@CrossOrigin` trên controller hoặc method khi chỉ một endpoint cần policy riêng:

~~~java
@RestController
@RequestMapping("/mvc-api/reports")
@CrossOrigin(
    origins = "https://app.example.com",
    methods = {RequestMethod.GET},
    maxAge = 3600
)
public class ReportController {

    @GetMapping
    public ReportSummary getReport() {
        return new ReportSummary();
    }
}
~~~

`@CrossOrigin` ở cấp class áp dụng cho các method của controller; annotation ở method cho phép cấu hình chi tiết hơn cho endpoint cụ thể.

Đây là cấu hình Spring MVC. Nó không thay thế registry CORS riêng của Spring Data REST exporter.

## 5. So sánh hai registry

| Nội dung | Spring Data REST exporter | Spring MVC |
| --- | --- | --- |
| Extension point toàn cục | `RepositoryRestConfigurer` | `WebMvcConfigurer` |
| Callback | `configureRepositoryRestConfiguration(config, cors)` | `addCorsMappings(registry)` |
| Registry | `CorsRegistry` được Spring Data REST truyền vào | `CorsRegistry` của Spring MVC |
| Endpoint chính | Repository collection, item, search, association | Controller tự viết |
| Annotation theo endpoint | `@CrossOrigin` trên repository | `@CrossOrigin` trên controller/method |
| Tự dùng cấu hình của bên kia? | Không tự nhận cấu hình MVC hiện có | Không dùng registry Spring Data REST làm cấu hình MVC |

Có thể đăng ký cả hai configurer trong cùng ApplicationContext. Ví dụ:

~~~text
ApplicationContext
    |
    +-- DataRestCorsConfiguration
    |       |
    |       +-- RepositoryRestConfigurer
    |               |
    |               +-- /api/people/**
    |               +-- /api/orders/**
    |
    +-- MvcCorsConfiguration
            |
            +-- WebMvcConfigurer
                    |
                    +-- /mvc-api/**
                    +-- /admin-api/**
~~~

Hai cấu hình có thể dùng cùng origin và cùng danh sách header, nhưng phải được khai báo ở đúng extension point. Nếu chỉ thêm mapping ở Spring MVC mà không cấu hình Spring Data REST, browser có thể gọi được custom controller nhưng vẫn bị CORS khi gọi repository resource.

## 6. Cấu hình CORS theo từng repository bằng @CrossOrigin

Ngoài registry toàn cục, Spring Data REST hỗ trợ `@CrossOrigin` trên repository interface. Annotation này áp dụng cho toàn bộ repository:

~~~java
@CrossOrigin(
    origins = "https://app.example.com",
    methods = {
        RequestMethod.GET,
        RequestMethod.POST,
        RequestMethod.DELETE
    },
    maxAge = 3600
)
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Cách này phù hợp khi repository có policy khác với các repository còn lại. Ví dụ:

- People chỉ cho frontend nội bộ đọc và tạo.
- PublicCatalog chỉ cho phép GET từ website công khai.
- InternalAudit không mở CORS cho browser frontend.

Theo tài liệu Spring Data REST, `@CrossOrigin` mặc định cho phép tất cả origins và HTTP methods. Vì vậy, không nên dùng annotation trống trên repository chứa dữ liệu nhạy cảm trong production nếu chưa có chủ đích.

Khi dùng `@CrossOrigin` và global CORS registry đồng thời, Spring Data REST hỗ trợ kết hợp cấu hình toàn cục với cấu hình chi tiết. Hãy kiểm tra kết quả thực tế của các giá trị được kết hợp; không mặc định rằng hai policy sẽ được giao nhau theo nguyên tắc “cấu hình chặt hơn thắng”.

## 7. @RepositoryRestController và custom controller nằm cạnh repository

Spring Data REST hỗ trợ CORS của Spring MVC trên custom controller được đánh dấu `@RepositoryRestController`:

~~~java
@RepositoryRestController
public class PersonCustomController {

    @CrossOrigin(
        origins = "https://app.example.com",
        maxAge = 3600
    )
    @RequestMapping(
        path = "/people/export",
        method = RequestMethod.GET,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ExportResult exportPeople() {
        return new ExportResult();
    }
}
~~~

Một chi tiết quan trọng trong tài liệu Spring Data REST: controller có annotation `@RepositoryRestController` có thể kế thừa cấu hình `@CrossOrigin` từ repository liên quan.

Điều này hữu ích khi custom endpoint chia sẻ base path và policy với repository resource. Tuy nhiên, controller `@RestController` thông thường không tự động kế thừa CORS policy từ repository chỉ vì nó gọi cùng service hoặc truy cập cùng entity.

Phân biệt:

- `@RepositoryRestController`: custom controller tích hợp với Spring Data REST, có thể kế thừa cấu hình CORS từ repository liên quan.
- `@RestController`: controller Spring MVC thông thường, dùng CORS mapping của MVC hoặc `@CrossOrigin` riêng.
- Repository interface: policy `@CrossOrigin` áp dụng cho các REST resources do repository exporter tạo.

## 8. Cấu hình nào được kết hợp với nhau?

Trong Spring MVC, global CORS mapping có thể kết hợp với local `@CrossOrigin` trên controller/method. Quy tắc kết hợp của Spring thường cộng dồn các danh sách như origins, methods và headers. Với thuộc tính chỉ nhận một giá trị như `allowCredentials` hoặc `maxAge`, cấu hình local có thể ghi đè cấu hình global.

Spring Data REST cũng cho phép kết hợp global registry của exporter với cấu hình `@CrossOrigin` chi tiết. Tuy nhiên, hai registry toàn cục của Spring MVC và Spring Data REST vẫn là hai điểm cấu hình độc lập.

Ví dụ:

~~~java
// Cấu hình toàn cục của Spring Data REST
cors.addMapping("/people/**")
    .allowedOrigins("https://app.example.com")
    .allowedMethods("GET", "POST")
    .maxAge(1800);
~~~

~~~java
// Cấu hình chi tiết trên một repository
@CrossOrigin(
    origins = "https://admin.example.com",
    methods = {RequestMethod.GET, RequestMethod.DELETE}
)
public interface AdminRepository
        extends JpaRepository<AdminRecord, Long> {
}
~~~

Khi có nhiều cấu hình chồng lấn, hãy kiểm tra response headers cuối cùng cho từng route. Đừng dùng một annotation rộng để vô tình mở thêm origin hoặc method mà policy toàn cục dự định hạn chế.

Đặc biệt, nếu bật credentials, không dùng wildcard origin `*` với `allowCredentials(true)`. Hãy khai báo origin cụ thể hoặc dùng `allowedOriginPatterns` với pattern được kiểm soát.

## 9. Spring Security và thứ tự xử lý CORS

Nếu ứng dụng dùng Spring Security, CORS phải được xử lý trước bước xác thực. Browser preflight request thường không gửi cookie phiên như `JSESSIONID`. Nếu Spring Security yêu cầu authentication trước khi CORS được xử lý, request OPTIONS có thể bị từ chối trước khi browser nhận được response CORS cần thiết.

Spring Security hỗ trợ CORS trong filter chain:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/**", "/mvc-api/**")
                    .authenticated()
                .anyRequest().denyAll()
            );

        return http.build();
    }
}
~~~

Spring Security có thể sử dụng một `CorsConfigurationSource` để cấu hình CORS ở filter layer. Ví dụ:

~~~java
@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {

    CorsConfiguration configuration = new CorsConfiguration();
    configuration.setAllowedOrigins(
            List.of("https://app.example.com"));
    configuration.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
    configuration.setAllowedHeaders(
            List.of("Authorization", "Content-Type", "If-Match"));
    configuration.setAllowCredentials(true);
    configuration.setMaxAge(3600L);

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

    source.registerCorsConfiguration("/api/**", configuration);
    source.registerCorsConfiguration("/mvc-api/**", configuration);

    return source;
}
~~~

Khi có bean `UrlBasedCorsConfigurationSource`, Spring Security có thể dùng nguồn này cho `http.cors()`. Đây là một lớp xử lý ở filter chain, khác với hai registry được khai báo qua `RepositoryRestConfigurer` và `WebMvcConfigurer`.

Spring Security cũng có thể dùng CORS configuration của Spring MVC nếu Spring MVC có mặt và không có `CorsConfigurationSource` riêng. Không nên suy ra từ điều đó rằng Spring Security tự động dùng registry riêng của Spring Data REST. Nếu cấu hình filter-level CORS, hãy bảo đảm source bao phủ cả route exporter và custom MVC cần thiết, rồi kiểm thử toàn bộ filter chain.

Tránh để nhiều lớp CORS cùng thêm các header mâu thuẫn. Hãy xác định lớp nào xử lý preflight và kiểm tra response thực tế để bảo đảm chỉ có policy nhất quán.

## 10. Preflight request và các header cần thiết

Browser thường gửi preflight OPTIONS trước actual request khi request dùng method hoặc header không thuộc nhóm đơn giản.

Ví dụ frontend muốn gửi PATCH với Authorization và Content-Type:

~~~http
OPTIONS /api/people/42
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization, content-type
~~~

Server cần xác nhận:

- Origin có nằm trong allowed origins không?
- PATCH có được phép không?
- Authorization và Content-Type có nằm trong allowed headers không?
- Nếu dùng cookie/credential, policy có cho phép credentials không?

Một response preflight thành công có thể chứa:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Authorization, Content-Type
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin
~~~

Browser sau đó mới gửi actual request. Status code cụ thể của preflight có thể khác tùy handler; điều quan trọng là response có các CORS headers hợp lệ.

Nếu frontend gửi header tùy chỉnh như `If-Match`, `X-Request-Id` hoặc `X-CSRF-TOKEN`, hãy thêm chúng vào allowed headers. Nếu JavaScript cần đọc response header như `ETag`, `Location` hoặc `X-Total-Count`, cần thêm vào exposed headers.

`Access-Control-Allow-Headers` quyết định request header browser được phép gửi; `Access-Control-Expose-Headers` quyết định response header JavaScript được phép đọc. Hai danh sách này phục vụ hai hướng khác nhau.

## 11. Credential, cookie và CSRF

Nếu frontend dùng cookie phiên hoặc credential browser, cấu hình phải cho phép credentials:

~~~java
.allowCredentials(true)
.allowedOrigins("https://app.example.com")
~~~

Không kết hợp `allowCredentials(true)` với `allowedOrigins("*")`. Browser không chấp nhận wildcard origin trong response có credential. Cấu hình origin cụ thể giúp giới hạn rõ domain được tin cậy.

CORS và CSRF giải quyết hai vấn đề khác nhau:

- CORS quyết định browser có được đọc response cross-origin hay không.
- CSRF bảo vệ server trước request giả mạo được gửi bằng credential của người dùng.

Nếu ứng dụng dùng session cookie và cho phép frontend gửi cookie, cần cấu hình CSRF token phù hợp. Việc thêm origin vào CORS không tự vô hiệu hóa CSRF protection và cũng không chứng minh request là hợp lệ.

Không bật credentials chỉ vì frontend gặp lỗi CORS. Chỉ bật khi use case thực sự cần cookie hoặc credential được browser gửi tự động; dùng HTTPS và giới hạn origin cụ thể.

## 12. Ví dụ một ứng dụng có cả Spring Data REST và MVC

Giả sử frontend ở `https://app.example.com`. Repository API nằm dưới `/api`, custom MVC nằm dưới `/mvc-api`.

Cấu hình Spring Data REST:

~~~java
@Component
public class DataRestCorsConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        cors.addMapping("/people/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
            .allowedHeaders("Authorization", "Content-Type", "If-Match")
            .exposedHeaders("ETag", "Location")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

Cấu hình Spring MVC:

~~~java
@Configuration
public class MvcCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/mvc-api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST")
            .allowedHeaders("Authorization", "Content-Type")
            .exposedHeaders("X-Request-Id")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

Cách phân chia:

| Request | Cấu hình cần kiểm tra |
| --- | --- |
| GET collection `/api/people` | Spring Data REST CORS |
| PATCH item `/api/people/42` | Spring Data REST CORS và Security filter nếu có |
| GET association `/api/people/42/address` | Spring Data REST CORS |
| GET custom report `/mvc-api/reports` | Spring MVC CORS |
| POST custom import `/mvc-api/imports` | Spring MVC CORS |
| Custom `@RepositoryRestController` | CORS của Spring Data REST/repository và cấu hình method-level liên quan |

Đừng chỉ kiểm thử một URL. Collection, item, search, association và custom controller có thể đi qua handler khác nhau.

## 13. Kiểm thử CORS bằng MockMvc

Nên kiểm tra preflight riêng cho repository exporter và custom MVC controller.

### Preflight tới Spring Data REST

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class DataRestCorsTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void allowsConfiguredOriginToPatchRepositoryResource()
            throws Exception {

        mockMvc.perform(options("/api/people/42")
                .header(HttpHeaders.ORIGIN,
                        "https://app.example.com")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                        "PATCH")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "authorization,content-type"))
            .andExpect(status().is2xxSuccessful())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    "https://app.example.com"))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                    containsString("PATCH")));
    }
}
~~~

### Preflight tới Spring MVC controller

~~~java
@Test
void allowsConfiguredOriginToCallMvcController()
        throws Exception {

    mockMvc.perform(options("/mvc-api/reports")
            .header(HttpHeaders.ORIGIN,
                    "https://app.example.com")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "GET"))
        .andExpect(status().is2xxSuccessful())
        .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com"));
}
~~~

### Origin không được phép

~~~java
@Test
void doesNotAllowUnknownOrigin() throws Exception {

    mockMvc.perform(options("/api/people/42")
            .header(HttpHeaders.ORIGIN,
                    "https://untrusted.example")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "PATCH"))
        .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
}
~~~

Các test là ví dụ khung; hãy điều chỉnh base path, route, status code và header theo phiên bản Spring Data REST, Spring MVC và Spring Security của ứng dụng.

Nếu Security filter xử lý preflight trước HandlerMapping, chạy test với Security filter được bật. Test chỉ dùng MockMvc không có filter có thể bỏ qua đúng lớp đang gây lỗi trong production.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Custom MVC controller gọi được nhưng repository resource bị CORS | Chỉ cấu hình WebMvcConfigurer | Thêm cấu hình qua RepositoryRestConfigurer |
| Repository resource gọi được nhưng custom controller bị CORS | Chỉ cấu hình CORS cho exporter | Thêm WebMvcConfigurer hoặc @CrossOrigin trên MVC controller |
| OPTIONS trả 401/403 trước khi vào controller | Security xử lý authentication trước preflight | Bật CORS trong Security filter chain và đặt xử lý CORS trước authentication |
| GET hoạt động nhưng PATCH/PUT bị chặn | Allowed methods thiếu method ghi | Thêm method thực tế vào allowedMethods |
| Request có Authorization bị chặn | Authorization không nằm trong allowedHeaders | Thêm Authorization vào allowedHeaders |
| JavaScript không đọc được ETag | ETag chưa được expose | Thêm ETag vào exposedHeaders |
| Cookie không được gửi | allowCredentials chưa bật hoặc origin dùng wildcard | Dùng origin cụ thể và allowCredentials(true) khi thực sự cần |
| Annotation @CrossOrigin không có tác dụng với SDR | Annotation đặt trên custom controller thông thường hoặc route không thuộc repository | Dùng repository annotation hoặc RepositoryRestConfigurer phù hợp |
| Cấu hình MVC tưởng đã áp dụng cho SDR nhưng không | Hai registry độc lập | Kiểm tra và cấu hình cả hai extension point |
| Có nhiều Access-Control-Allow-Origin header | Nhiều filter/configuration layer cùng thêm header | Xác định một nơi xử lý chính và đồng bộ policy |
| CORS cho phép nhưng request vẫn 403 | Authorization/CSRF từ chối request | Kiểm tra Spring Security; CORS không cấp quyền |
| Test preflight pass nhưng browser vẫn lỗi | Thiếu header thực tế, credentials, Vary hoặc filter production khác test | Xem Network tab và response headers của OPTIONS lẫn actual request |

## 15. Quy trình triển khai

1. Liệt kê toàn bộ endpoint và phân loại endpoint do Spring Data REST hay Spring MVC xử lý.
2. Xác định frontend origins theo từng môi trường.
3. Cấu hình repository resources qua `RepositoryRestConfigurer`.
4. Cấu hình custom MVC endpoints qua `WebMvcConfigurer` hoặc `@CrossOrigin`.
5. Nếu dùng `@RepositoryRestController`, kiểm tra policy kế thừa từ repository liên quan.
6. Chỉ cho phép method và header thực sự cần thiết.
7. Chỉ expose response headers mà JavaScript cần đọc.
8. Bật credentials khi cần cookie/session và dùng origin cụ thể.
9. Nếu có Spring Security, bảo đảm preflight được xử lý trước authentication và filter-level CORS không xung đột với handler-level configuration.
10. Kiểm thử OPTIONS cho collection, item, association, search và custom MVC routes.
11. Kiểm tra cả actual request sau preflight và các response header của nó.
12. Không xem CORS là authorization; giữ nguyên security rules và CSRF protection phù hợp.

## Tài liệu tham khảo

- [Spring Data REST 5.1.2 — Configuring CORS](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-cors.html): repository `@CrossOrigin`, custom `@RepositoryRestController`, global exporter `CorsRegistry` và lưu ý cấu hình Spring MVC không áp dụng cho Spring Data REST.
- [Spring Framework — CORS in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): `WebMvcConfigurer`, `@CrossOrigin`, preflight, credentials và cách kết hợp global/local CORS.
- [Spring Security 7.1 — CORS Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): xử lý CORS trước authentication, `CorsConfigurationSource`, `http.cors()` và tích hợp với MVC.
- [Spring Framework API — CorsConfiguration](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/CorsConfiguration.html): allowed origins, methods, headers, credentials, exposed headers và max age.
