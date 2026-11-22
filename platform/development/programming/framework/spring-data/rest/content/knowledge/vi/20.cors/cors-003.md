# Cấu hình CORS cho Controller tùy chỉnh của Spring Data REST

## 1. Mục tiêu

Khi frontend chạy ở origin khác với backend, trình duyệt áp dụng same-origin policy và có thể chặn JavaScript đọc response. CORS (Cross-Origin Resource Sharing) cho phép server công bố những origin, HTTP method và header nào được phép truy cập tài nguyên từ trình duyệt.

Trong ứng dụng có Spring Data REST, cần phân biệt hai nhóm endpoint:

- **Repository endpoint và custom controller trong URI space của Spring Data REST:** dùng CORS configuration của Spring Data REST, @CrossOrigin trên repository hoặc custom @RepositoryRestController, hay RepositoryRestConfigurer.
- **Custom controller Spring MVC thông thường:** dùng @CrossOrigin hoặc WebMvcConfigurer.addCorsMappings.

Điểm dễ nhầm là global CORS mapping khai báo bằng WebMvcConfigurer không tự động áp dụng cho Spring Data REST endpoints. Hãy xác định controller đang được xử lý bởi handler mapping nào trước khi chọn cách cấu hình.

## 2. Origin và same-origin policy

Một origin được xác định bởi scheme, host và port. Ví dụ:

    http://localhost:3000
    http://localhost:8080
    https://localhost:3000
    https://app.example.com

Đường dẫn /customers không phải một phần của origin. https://app.example.com khác https://admin.example.com dù hai ứng dụng có thể gọi cùng backend.

Nếu frontend ở http://localhost:3000 gọi backend ở http://localhost:8080, request là cross-origin. Server cần trả CORS response headers phù hợp để trình duyệt cho phép frontend đọc response.

CORS chủ yếu là cơ chế kiểm soát truy cập từ trình duyệt. curl hoặc Postman không tự thực thi chính sách CORS của browser; request bằng các công cụ đó có thể thành công dù browser vẫn báo CORS error.

## 3. Preflight request hoạt động như thế nào?

Với một số request cross-origin, trình duyệt gửi request kiểm tra trước (preflight) bằng HTTP OPTIONS. Preflight thường xảy ra khi request dùng PUT, PATCH, DELETE, header tùy chỉnh hoặc content type không thuộc nhóm simple request.

Ví dụ browser muốn gửi PATCH có Authorization và Content-Type:

    OPTIONS /api/customers/42
    Origin: https://app.example.com
    Access-Control-Request-Method: PATCH
    Access-Control-Request-Headers: authorization, content-type, if-match

Server kiểm tra origin, method và request headers có được phép không. Response preflight hợp lệ có thể chứa:

    HTTP/1.1 200 OK
    Access-Control-Allow-Origin: https://app.example.com
    Access-Control-Allow-Methods: GET, POST, PATCH
    Access-Control-Allow-Headers: Authorization, Content-Type, If-Match
    Access-Control-Max-Age: 3600

Sau khi preflight được chấp nhận, trình duyệt mới gửi request PATCH thực tế. Với request đơn giản không cần preflight, browser có thể gửi request trước rồi chỉ cho JavaScript đọc response nếu CORS response headers hợp lệ.

Access-Control-Request-Method cho biết method mà browser muốn dùng ở request thật. Access-Control-Request-Headers liệt kê request headers cần được cho phép. Spring CORS infrastructure có thể xử lý preflight mà không cần controller thực hiện nghiệp vụ OPTIONS.

## 4. Xác định loại custom controller

**Controller tích hợp với Spring Data REST**

Dùng @RepositoryRestController khi custom handler ánh xạ vào URI space của repository và cần tận dụng base path, message converters, exception handling cùng các tích hợp của Spring Data REST. Loại controller này hỗ trợ @CrossOrigin trên method/class và có thể kế thừa CORS configuration từ repository liên quan.

**Controller Spring MVC thông thường**

Dùng @RestController cho endpoint độc lập không cần xử lý như repository resource. Cấu hình CORS bằng @CrossOrigin hoặc global mapping qua WebMvcConfigurer.

Không chọn cách cấu hình chỉ dựa vào tên class. Annotation điều khiển handler mapping và đường đi request; đó là yếu tố quyết định CORS configuration nào được áp dụng.

## 5. Cấu hình @RepositoryRestController bằng @CrossOrigin

Ví dụ custom endpoint trả về bản tóm tắt Customer trong URI space của Spring Data REST:

    @RepositoryRestController
    public class CustomerSummaryController {

        private final CustomerService customerService;

        public CustomerSummaryController(
                CustomerService customerService) {
            this.customerService = customerService;
        }

        @CrossOrigin(
            origins = "https://app.example.com",
            methods = RequestMethod.GET,
            allowedHeaders = {
                "Authorization",
                "Content-Type",
                "X-Request-Id"
            },
            exposedHeaders = {
                "ETag",
                "Link"
            },
            maxAge = 3600
        )
        @GetMapping(
            path = "/customers/{id}/summary",
            produces = MediaType.APPLICATION_JSON_VALUE
        )
        @ResponseBody
        public CustomerSummary getSummary(
                @PathVariable Long id) {
            return customerService.getSummary(id);
        }
    }

Trong ví dụ:

- origins giới hạn frontend được phép gọi endpoint.
- methods cho phép GET.
- allowedHeaders khai báo request headers browser được phép gửi.
- exposedHeaders cho phép JavaScript đọc một số response headers.
- maxAge cho browser cache kết quả preflight trong số giây được chỉ định.

Các giá trị trong ví dụ là minh họa. Thay origin, path và headers theo frontend cùng API thực tế. Có thể đặt @CrossOrigin ở cấp class nếu mọi method có cùng chính sách; đặt ở cấp method khi từng endpoint cần chính sách riêng.

## 6. Kế thừa CORS từ repository liên quan

Spring Data REST hỗ trợ @CrossOrigin trực tiếp trên repository interface:

    @CrossOrigin(
        origins = "https://app.example.com",
        methods = {
            RequestMethod.GET,
            RequestMethod.POST,
            RequestMethod.PATCH
        },
        allowedHeaders = {
            "Authorization",
            "Content-Type",
            "If-Match"
        },
        exposedHeaders = {
            "ETag",
            "Location"
        },
        maxAge = 3600
    )
    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {
    }

Custom controller được đánh dấu @RepositoryRestController có thể kế thừa @CrossOrigin configuration từ repository liên quan. Điều này hữu ích khi custom route chia sẻ repository base path và cần cùng chính sách origin.

Nếu method của custom controller cần chính sách khác, có thể cấu hình @CrossOrigin riêng ở method hoặc class. Kiểm tra quy tắc kết hợp global và local configuration trong phiên bản Spring Framework/Spring Data REST đang dùng.

Không mặc định mọi custom controller đều gắn với một repository. Nếu controller không có repository liên quan, hãy cấu hình CORS tường minh trên handler hoặc theo cơ chế phù hợp với loại controller.

## 7. Cấu hình CORS toàn cục cho Spring Data REST

Có thể cấu hình nhiều Spring Data REST endpoint trong một RepositoryRestConfigurer:

    @Component
    public class SpringDataRestCorsConfig
            implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {

            cors.addMapping("/customers/**")
                .allowedOrigins("https://app.example.com")
                .allowedMethods(
                    "GET",
                    "POST",
                    "PUT",
                    "PATCH",
                    "DELETE"
                )
                .allowedHeaders(
                    "Authorization",
                    "Content-Type",
                    "If-Match",
                    "If-None-Match",
                    "X-Request-Id"
                )
                .exposedHeaders(
                    "ETag",
                    "Location",
                    "Link"
                )
                .allowCredentials(true)
                .maxAge(3600);
        }
    }

configureRepositoryRestConfiguration nhận CorsRegistry để cấu hình CORS cho Spring Data REST. Mapping /customers/** chỉ áp dụng cho path khớp mẫu đó trong URI space của Spring Data REST.

Có thể thêm mapping riêng cho repository khác thay vì mở quyền cho toàn bộ /**. Khi thay đổi base path bằng RepositoryRestConfiguration, hãy kiểm tra path thực tế mà mapping nhận được.

Đừng nhầm RepositoryRestConfigurer với WebMvcConfigurer. Spring Data REST có CORS registry riêng; global Spring MVC CORS configuration không tự áp dụng cho repository REST endpoints.

## 8. Cấu hình CORS cho @RestController thông thường

Nếu custom endpoint là Spring MVC controller thông thường, có thể dùng WebMvcConfigurer:

    @Configuration
    public class WebCorsConfig implements WebMvcConfigurer {

        @Override
        public void addCorsMappings(CorsRegistry registry) {
            registry.addMapping("/custom/**")
                .allowedOrigins("https://app.example.com")
                .allowedMethods(
                    "GET",
                    "POST",
                    "PATCH",
                    "DELETE"
                )
                .allowedHeaders(
                    "Authorization",
                    "Content-Type",
                    "X-Request-Id"
                )
                .exposedHeaders(
                    "Location",
                    "ETag"
                )
                .allowCredentials(true)
                .maxAge(3600);
        }
    }

Hoặc cấu hình ngay trên controller:

    @RestController
    @RequestMapping("/custom/reports")
    @CrossOrigin(
        origins = "https://app.example.com",
        methods = {
            RequestMethod.GET,
            RequestMethod.POST
        },
        allowedHeaders = {
            "Authorization",
            "Content-Type"
        },
        exposedHeaders = {
            "Location",
            "ETag"
        },
        maxAge = 3600
    )
    public class ReportController {

        @GetMapping("/{id}")
        public Report getReport(@PathVariable Long id) {
            // ...
        }
    }

Cấu hình MVC ở trên áp dụng cho custom MVC controller. Nếu endpoint được xử lý như Spring Data REST endpoint, hãy dùng CORS configuration của Spring Data REST hoặc @CrossOrigin trên custom @RepositoryRestController phù hợp.

Không tạo hai global mapping chồng lấn với origin/method/header khác nhau nếu chưa hiểu cách Spring kết hợp chúng. Cấu hình trùng lặp có thể dẫn tới response header CORS mâu thuẫn hoặc khó chẩn đoán.

## 9. allowedHeaders và exposedHeaders khác nhau

| Cấu hình | Ý nghĩa | Ví dụ |
|---|---|---|
| allowedHeaders | Request header browser được phép gửi tới server | Authorization, Content-Type, If-Match |
| exposedHeaders | Response header JavaScript được phép đọc | ETag, Location, Link |

Ví dụ frontend gửi If-Match để cập nhật resource có ETag. Header này cần nằm trong allowedHeaders.

Nếu frontend cần đọc ETag mới sau update, ETag cần nằm trong exposedHeaders. Server có thể gửi ETag trong response nhưng JavaScript không đọc được qua Fetch/XHR nếu thiếu cấu hình expose.

Tương tự, Location hữu ích sau POST tạo resource; Link có thể chứa quan hệ hypermedia mà client cần đọc. Chỉ expose response headers thật sự cần thiết.

## 10. Credentialed requests và origin wildcard

Nếu frontend gửi cookie/session hoặc dùng chế độ fetch credentials include, server cần cho phép credentials:

    fetch("https://api.example.com/custom/profile", {
      method: "GET",
      credentials: "include"
    });

Cấu hình server cần bật allowCredentials(true) và chỉ định origin cụ thể, ví dụ https://app.example.com.

Không kết hợp allowedOrigins("*") với allowCredentials(true). CORS specification không cho phép wildcard origin cùng credentialed request. Nếu cần nhóm subdomain động, Spring hỗ trợ allowedOriginPatterns; pattern vẫn cần được giới hạn cẩn thận.

Nếu frontend tự thêm Bearer token trong Authorization header, header đó phải được cho phép trong allowedHeaders. Việc gửi header Authorization thủ công không nhất thiết yêu cầu bật cookie credentials; chỉ bật credentials khi request thật sự cần gửi cookie, HTTP authentication hoặc thông tin xác thực trình duyệt tương ứng.

CORS không thay thế authentication, authorization hoặc CSRF protection. Cho phép một origin gửi request không có nghĩa caller từ origin đó được quyền đọc hay sửa mọi dữ liệu.

## 11. Kết hợp với Spring Security

CORS cần được xử lý trước authorization filter của Spring Security. Preflight OPTIONS thường không mang cookie session, nên nếu security yêu cầu authenticated trước khi CORS xử lý, request có thể bị trả 401/403 dù request thật có thể được xác thực.

Với Spring Security hiện đại, bật CORS integration trong SecurityFilterChain:

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http) throws Exception {

        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.OPTIONS,
                    "/**"
                ).permitAll()
                .anyRequest().authenticated()
            )
            .build();
    }

Đoạn code minh họa thứ tự tích hợp; .cors(...) cần có CORS configuration source hoặc cơ chế tích hợp tương thích với ứng dụng. Nếu khai báo CorsConfigurationSource riêng cho filter chain, hãy đăng ký path pattern, origins, methods và headers khớp với custom endpoint. Nếu dùng nhiều CORS configuration layer, tránh trả các Access-Control-Allow-Origin header trùng hoặc mâu thuẫn.

Cho phép OPTIONS qua security matcher không tự tạo CORS response headers. Nó chỉ giúp preflight có thể đi tới CORS processing phù hợp. Không mở toàn bộ request thật cho anonymous user chỉ để khắc phục preflight.

Nếu dùng @RepositoryRestController, hãy kiểm tra preflight trên chính URI đó khi Spring Security bật. Đừng chỉ kiểm tra một @RestController khác rồi suy ra repository controller đã hoạt động giống hệt.

## 12. Kiểm tra bằng curl

Có thể gửi preflight thủ công để quan sát response header:

    curl -i -X OPTIONS "http://localhost:8080/customers/42/summary" -H "Origin: https://app.example.com" -H "Access-Control-Request-Method: PATCH" -H "Access-Control-Request-Headers: authorization,content-type,if-match"

Kiểm tra các header:

- Access-Control-Allow-Origin có đúng origin frontend không.
- Access-Control-Allow-Methods có PATCH không.
- Access-Control-Allow-Headers có Authorization, Content-Type và If-Match không.
- Access-Control-Allow-Credentials có xuất hiện nếu request dùng credentials không.
- Access-Control-Max-Age có đúng giá trị cấu hình không.

Sau đó thử request thật có Origin:

    curl -i "http://localhost:8080/customers/42/summary" -H "Origin: https://app.example.com" -H "Accept: application/json"

curl chỉ giúp xem server trả header gì; nó không thực thi browser CORS policy. Hãy kiểm tra thêm từ browser ở đúng origin frontend để xác nhận JavaScript có đọc được response.

## 13. Kiểm thử CORS bằng MockMvc

Với Spring MVC hoặc custom repository controller, có thể viết integration test gửi Origin và preflight headers:

    @SpringBootTest
    @AutoConfigureMockMvc
    class CustomerCorsTest {

        @Autowired
        private MockMvc mockMvc;

        @Test
        void allowsConfiguredOriginForPreflight()
                throws Exception {

            mockMvc.perform(options(
                    "/customers/42/summary")
                    .header(
                        "Origin",
                        "https://app.example.com"
                    )
                    .header(
                        "Access-Control-Request-Method",
                        "PATCH"
                    )
                    .header(
                        "Access-Control-Request-Headers",
                        "authorization,content-type,if-match"
                    ))
                .andExpect(status().isOk())
                .andExpect(header().string(
                    "Access-Control-Allow-Origin",
                    "https://app.example.com"
                ))
                .andExpect(header().string(
                    "Access-Control-Allow-Methods",
                    org.hamcrest.Matchers.containsString("PATCH")
                ));
        }
    }

Status của preflight có thể khác tùy handler mapping và cấu hình; hãy assert response contract thực tế của ứng dụng. Điều quan trọng là response có origin, method và headers phù hợp, không bị Spring Security chặn trước CORS.

Có thể kiểm tra origin không được phép:

    mockMvc.perform(options("/customers/42/summary")
            .header("Origin", "https://unknown.example")
            .header(
                "Access-Control-Request-Method",
                "PATCH"
            ))
        .andExpect(status().isForbidden());

403 là hành vi thường gặp với preflight bị từ chối trong Spring CORS processing; điều chỉnh theo error handling và cấu hình thực tế. Cũng nên kiểm tra request thật có Access-Control-Allow-Origin và exposed headers mong đợi.

## 14. Lỗi thường gặp

**Dùng WebMvcConfigurer cho Spring Data REST endpoint**

Global MVC CORS mapping không tự áp dụng cho Spring Data REST. Dùng RepositoryRestConfigurer hoặc @CrossOrigin trên repository/custom RepositoryRestController.

**Nhầm @RestController với @RepositoryRestController**

Hai annotation đưa request qua các cơ chế handler mapping khác nhau. Xác định controller cần tích hợp vào repository URI space hay là endpoint MVC độc lập.

**Chỉ cho phép GET nhưng frontend gửi PATCH**

Preflight yêu cầu PATCH sẽ không qua nếu allowedMethods thiếu PATCH. Khai báo đúng method thực tế, không chỉ OPTIONS.

**Thiếu request header trong allowedHeaders**

Authorization, Content-Type, If-Match hoặc header tùy chỉnh có thể làm preflight thất bại nếu không được cho phép.

**Không expose ETag hoặc Location**

Server có thể trả các header này nhưng JavaScript không đọc được nếu thiếu exposedHeaders.

**Dùng wildcard cùng credentials**

Không dùng allowedOrigins wildcard khi allowCredentials=true. Chỉ định origin cụ thể hoặc dùng allowedOriginPatterns được giới hạn.

**Spring Security chặn OPTIONS**

Preflight không có session cookie như request thật. Đảm bảo CORS được xử lý trước authorization và cấu hình security cho phép preflight tới đúng CORS handler.

**Cấu hình CORS nhưng quên authentication**

CORS chỉ điều khiển browser cross-origin access. Nó không xác thực caller và không phân quyền dữ liệu.

**Kiểm tra bằng curl rồi kết luận browser hoạt động**

curl không enforce CORS. Cần kiểm tra từ browser ở origin thật, đồng thời xem Network tab để xác định preflight và request thật.

## 15. Bài tập thực hành

Giả sử frontend chạy tại https://app.example.com và backend có Spring Data REST cùng custom endpoint trả Customer summary:

1. Tạo custom endpoint trong repository URI space bằng @RepositoryRestController.
2. Dùng @CrossOrigin để chỉ cho phép origin frontend và method endpoint cần.
3. Khai báo allowedHeaders cho Authorization, Content-Type và X-Request-Id.
4. Expose ETag, Location hoặc Link nếu frontend cần đọc các header này.
5. Tạo RepositoryRestConfigurer để cấu hình CORS toàn cục cho một repository path.
6. Tạo một @RestController độc lập và cấu hình CORS riêng bằng WebMvcConfigurer.
7. Xác nhận MVC global mapping không tự cấu hình Spring Data REST repository endpoint.
8. Bật Spring Security và kiểm tra OPTIONS preflight không bị chặn trước CORS.
9. Gửi preflight bằng curl và kiểm tra Access-Control-Allow-Origin, Methods, Headers.
10. Mở frontend trong browser và gọi endpoint; kiểm tra cả preflight lẫn request thật.
11. Thử origin không được phép, method không được phép và header không được phép.
12. Nếu dùng cookie credentials, kiểm tra explicit origin, allowCredentials và CSRF policy.
13. Viết MockMvc integration test cho origin hợp lệ và origin bị từ chối.

Câu hỏi tự kiểm tra:

- Origin gồm những thành phần nào?
- Khi nào browser gửi OPTIONS preflight?
- Vì sao WebMvcConfigurer global CORS không tự áp dụng cho Spring Data REST?
- Khi nào dùng @RepositoryRestController và khi nào dùng @RestController?
- allowedHeaders khác exposedHeaders ở điểm nào?
- Vì sao ETag cần được expose nếu frontend phải đọc nó?
- Vì sao wildcard origin không được dùng cùng credentialed request?
- Vì sao CORS phải được xử lý trước Spring Security?
- CORS có thay thế authentication, authorization hoặc CSRF protection không?

## 16. Ghi nhớ

- CORS cho phép server khai báo origin, method và headers mà browser được phép dùng.
- Xác định endpoint thuộc Spring Data REST hay Spring MVC trước khi cấu hình.
- Spring Data REST hỗ trợ @CrossOrigin trên repository và custom @RepositoryRestController.
- RepositoryRestConfigurer nhận CorsRegistry để cấu hình CORS toàn cục cho Spring Data REST.
- WebMvcConfigurer.addCorsMappings cấu hình MVC endpoints; mapping này không tự áp dụng cho Spring Data REST.
- Preflight OPTIONS kiểm tra origin, method và request headers trước request thật.
- allowedHeaders cho phép request headers; exposedHeaders cho JavaScript đọc response headers.
- Credentialed request cần origin cụ thể; không dùng wildcard origin với allowCredentials=true.
- CORS phải được xử lý trước Spring Security authorization.
- CORS không thay thế authentication, authorization hoặc CSRF protection.
- Kiểm tra bằng browser và integration test; curl chỉ giúp quan sát response headers.

## Tài liệu tham khảo

- Spring Data REST Reference — Configuring CORS: https://docs.spring.io/spring-data/rest/reference/customizing/configuring-cors.html
- Spring Framework Reference — CORS support in Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Security Reference — CORS integration: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Data REST Reference — Custom REST controllers: https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html
