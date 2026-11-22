# Giao diện không tải được swagger-config hoặc tài nguyên tĩnh

## 1. Nhận diện đúng loại lỗi trước khi sửa

Swagger UI có thể mở được trang HTML nhưng vẫn không hiển thị API. Trường hợp này thường không phải lỗi controller hay schema ngay từ đầu. Giao diện cần tải nhiều tài nguyên và gọi ít nhất một endpoint cấu hình trước khi lấy OpenAPI document.

Một lượt tải trang thường có các bước:

1. Trình duyệt mở URL Swagger UI, ví dụ /swagger-ui.html.
2. Ứng dụng trả HTML hoặc redirect tới trang index.
3. Trình duyệt tải JavaScript, CSS, font và các tài nguyên giao diện.
4. Swagger UI tải swagger-config để biết URL của OpenAPI document và các tùy chọn giao diện.
5. Swagger UI gọi OpenAPI JSON/YAML, thường là /v3/api-docs.
6. Giao diện phân tích document và render operation, schema cùng security metadata.

Lỗi ở mỗi bước tạo ra triệu chứng khác nhau. Trang trắng, biểu tượng loading không dừng, thông báo Failed to load API definition hoặc lỗi JavaScript không đủ để kết luận nguyên nhân.

Cần xác định request nào thất bại trong Browser Developer Tools, sau đó đối chiếu status code, redirect, response body, Content-Type và URL thực tế.

## 2. Phân biệt ba nhóm tài nguyên

Khi điều tra, hãy chia request thành ba nhóm:

| Nhóm | Ví dụ URL | Vai trò |
|---|---|---|
| Trang giao diện | /swagger-ui.html, /swagger-ui/index.html | Trả HTML để khởi tạo Swagger UI |
| Tài nguyên tĩnh | /swagger-ui/swagger-ui-bundle.js, swagger-ui.css, favicon hoặc WebJar assets | Chạy và định dạng giao diện |
| Tài liệu và cấu hình | /v3/api-docs/swagger-config, /v3/api-docs | Cung cấp cấu hình và OpenAPI document |

Tên file tĩnh cụ thể phụ thuộc phiên bản Swagger UI được đóng gói. Hãy xem Network tab để biết chính xác tài nguyên nào bị lỗi.

swagger-config thường chứa thông tin URL document hoặc danh sách document, tên document mặc định và một số cấu hình UI. OpenAPI JSON/YAML là hợp đồng thực tế chứa paths, operations, schemas, responses và security.

Nếu swagger-config không tải được, UI có thể không biết phải lấy document ở đâu. Nếu swagger-config tải thành công nhưng OpenAPI document lỗi, trang có thể render được khung UI nhưng không hiển thị operation.

## 3. Dùng Network tab để tìm request đầu tiên thất bại

Mở Developer Tools của trình duyệt, chọn Network, bật Preserve log rồi tải lại trang Swagger UI.

Kiểm tra theo thứ tự:

- Document request tới /swagger-ui.html hoặc URL UI đã cấu hình.
- Redirect tới /swagger-ui/index.html nếu có.
- JavaScript bundle và CSS.
- Request swagger-config.
- Request /v3/api-docs hoặc URL document được cấu hình.
- Các request tới server API nếu đang thử operation.

Ghi lại cho request lỗi:

- Request URL đầy đủ.
- HTTP status.
- Method.
- Response Content-Type.
- Response body hoặc phần đầu response.
- Redirect chain.
- Initiator.
- Console error tương ứng.

Không chỉ nhìn status ở dòng đầu. Một request có thể trả 302 tới login page, sau đó redirect tới trang HTML trả 200. Swagger UI nhận HTML thay vì JSON và báo lỗi parse, dù request cuối cùng nhìn có vẻ thành công.

Nếu có nhiều lỗi, xử lý request gốc đầu tiên. Các lỗi JS hoặc render phía sau có thể chỉ là hệ quả của một file bundle hay config không tải được.

## 4. Kiểm tra các endpoint mặc định

Với cấu hình Springdoc phổ biến, các URL thường dùng là:

~~~text
/swagger-ui.html
/swagger-ui/index.html
/v3/api-docs/swagger-config
/v3/api-docs
/v3/api-docs.yaml
~~~

Không phải ứng dụng nào cũng dùng đúng các path mặc định. Các property có thể đổi API docs path, Swagger UI path hoặc URL document.

Thử từng URL từ cùng môi trường mà trình duyệt đang truy cập:

~~~bash
curl -i http://localhost:8080/swagger-ui.html
curl -i http://localhost:8080/v3/api-docs/swagger-config
curl -i http://localhost:8080/v3/api-docs
~~~

Dùng -i để xem status và response headers. Khi cần kiểm tra redirect, trước tiên đừng tự động theo redirect. Sau đó có thể dùng -L để xem response cuối cùng.

Nếu chạy sau context path, ví dụ /catalog, hãy thử URL công khai có prefix:

~~~bash
curl -i https://api.example.com/catalog/v3/api-docs/swagger-config
~~~

Một endpoint trả 404 trong khi endpoint khác trả 200 thường giúp khoanh vùng cấu hình path, security hoặc resource mapping.

## 5. Kiểm tra đúng Springdoc starter

Swagger UI static assets thường được cung cấp bởi starter có hậu tố ui. Ví dụ:

- Spring MVC: springdoc-openapi-starter-webmvc-ui.
- Spring WebFlux: springdoc-openapi-starter-webflux-ui.

Nếu ứng dụng chỉ dùng API-only starter, OpenAPI JSON/YAML có thể hoạt động trong khi Swagger UI assets không được đóng gói.

Ví dụ dependency Maven cho Spring MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>PINNED_COMPATIBLE_VERSION</version>
</dependency>
~~~

Với WebFlux, chọn artifact webflux-ui tương ứng. Thay PINNED_COMPATIBLE_VERSION bằng release tương thích với Spring Boot và Java của ứng dụng.

Không thêm cả webmvc-ui và webflux-ui chỉ để sửa lỗi static resource. Chọn starter khớp web stack. Nếu chỉ cần document cho CI hoặc developer portal, API-only starter là lựa chọn hợp lý, nhưng khi đó không mong đợi Swagger UI có sẵn.

## 6. Kiểm tra cấu hình bật/tắt API docs và Swagger UI

Các property thường cần kiểm tra:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
    path: /swagger-ui.html
~~~

api-docs.enabled điều khiển endpoint OpenAPI. swagger-ui.enabled điều khiển giao diện Swagger UI tích hợp.

Một số cấu hình có thể tắt Swagger UI trong production nhưng vẫn giữ OpenAPI endpoint. Khi đó /v3/api-docs hoạt động nhưng URL giao diện không được phục vụ.

Ngược lại, nếu api-docs.enabled bị tắt, Swagger UI có thể tải được HTML và JS nhưng không lấy được document.

Kiểm tra cấu hình cuối cùng sau khi Spring Boot hợp nhất application.yml, profile-specific YAML, environment variables và command-line arguments. Đừng chỉ đọc một file cấu hình rồi kết luận property đang có giá trị đó ở runtime.

## 7. Phân biệt lỗi swagger-config và lỗi OpenAPI document

Swagger UI thường tải cấu hình từ endpoint swagger-config. Với cấu hình mặc định, endpoint này thường là /v3/api-docs/swagger-config.

Nếu request này trả 404, 401, 403 hoặc HTML, UI có thể không biết URL OpenAPI cần tải.

Nếu swagger-config trả JSON hợp lệ nhưng document URL bên trong sai, bước tiếp theo tới /v3/api-docs sẽ thất bại.

Hãy mở response swagger-config và xem các trường liên quan như url hoặc urls. Sau đó copy đúng URL document và gọi trực tiếp bằng curl.

Không hard-code config URL mặc định nếu ứng dụng đã đổi springdoc.api-docs.path hoặc swagger-ui.config-url. Kiểm tra output thực tế của phiên bản Springdoc đang chạy.

## 8. Cấu hình config-url và document URL

Springdoc cho phép cấu hình URL swagger-config và URL OpenAPI document qua các property của Swagger UI. Tên property và cách binding cần đối chiếu tài liệu của phiên bản đang dùng.

Ví dụ cấu hình minh họa:

~~~yaml
springdoc:
  swagger-ui:
    config-url: /v3/api-docs/swagger-config
    url: /v3/api-docs
    disable-swagger-default-url: true
~~~

config-url trỏ tới endpoint cấu hình Swagger UI. url trỏ tới một OpenAPI document cụ thể. Nếu dùng nhiều document, có thể cấu hình danh sách urls thay vì một url.

Không cấu hình url và urls mâu thuẫn. Nếu dùng GroupedOpenApi, hãy trỏ tới đúng group document. disable-swagger-default-url giúp tránh việc Swagger UI hiển thị document mặc định không liên quan khi cấu hình API document của ứng dụng chưa được tải đúng.

Nếu API docs path đã đổi, cập nhật cả config URL và document URL theo cấu hình thật. Không đoán rằng đổi api-docs.path sẽ tự sửa mọi URL hard-code trong HTML hoặc reverse proxy.

## 9. Kiểm tra response Content-Type và body

Một endpoint có thể trả status 200 nhưng nội dung không phải JSON hoặc JavaScript mong đợi.

Ví dụ lỗi thường gặp:

- swagger-config trả text/html vì bị redirect tới trang login.
- /v3/api-docs trả JSON error wrapper của gateway.
- JavaScript bundle trả HTML 404 page.
- CSS trả Content-Type text/html.
- Proxy trả trang maintenance thay cho tài nguyên.
- API docs trả body rỗng do filter hoặc response transformation.

Dùng curl:

~~~bash
curl -i http://localhost:8080/v3/api-docs/swagger-config
curl -i http://localhost:8080/v3/api-docs
curl -I http://localhost:8080/swagger-ui/swagger-ui-bundle.js
~~~

Kiểm tra Content-Type và vài dòng đầu body. swagger-config và OpenAPI JSON cần là JSON; JS và CSS cần được phục vụ với MIME type phù hợp.

Không chấp nhận file HTML chỉ vì status là 200. Nếu endpoint yêu cầu authentication, cần xử lý redirect và credential đúng thay vì bỏ qua nội dung response.

## 10. Spring Security chặn swagger-config hoặc static resources

Một filter chain yêu cầu authentication cho mọi request có thể chặn cả Swagger UI và OpenAPI endpoint.

Ví dụ minh họa cho ứng dụng Servlet:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(
            "/swagger-ui.html",
            "/swagger-ui/**",
            "/v3/api-docs",
            "/v3/api-docs/**"
        ).hasRole("API_DOCS")
        .anyRequest().authenticated()
    );

    return http.build();
}
~~~

Nếu tài liệu được phép truy cập công khai trong môi trường tương ứng, có thể dùng permitAll cho các matcher này. Nếu tài liệu nội bộ, dùng role hoặc scope riêng.

Điểm quan trọng là phải bao gồm cả trang UI, static assets, swagger-config và OpenAPI document. Chỉ cho phép /swagger-ui.html mà chặn /swagger-ui/** thì HTML có thể tải nhưng JS/CSS bị 401 hoặc 403.

Không mở toàn bộ ứng dụng để sửa lỗi tài liệu. Chỉ điều chỉnh matcher cho các đường dẫn cần thiết và giữ authorization cho API nghiệp vụ.

## 11. Kiểm tra thứ tự SecurityFilterChain và matcher

Ứng dụng có thể có nhiều SecurityFilterChain với securityMatcher khác nhau. Request Swagger UI có thể được xử lý bởi một chain khác với API nghiệp vụ.

Khi điều tra:

1. Xem chain nào match request /swagger-ui/**.
2. Kiểm tra thứ tự @Order của các chain.
3. Kiểm tra matcher có dùng context path hay không.
4. Kiểm tra rule nào được áp dụng trước.
5. Kiểm tra authentication entry point có redirect sang login.
6. Kiểm tra CSRF chỉ khi request method hoặc flow thực sự cần.

Các request GET tới UI và document thường không cần CSRF token, nhưng nếu ứng dụng có cấu hình CSRF hoặc custom filter đặc biệt, hãy xác minh behavior thực tế. Không tắt CSRF toàn ứng dụng chỉ để Swagger UI tải được.

Nếu UI được bảo vệ bằng session cookie, browser cần giữ session khi gọi swagger-config và OpenAPI document. Nếu dùng bearer token, cấu hình tài liệu và cách UI gửi token cần phù hợp với security scheme.

## 12. Xử lý redirect tới login page

Một dấu hiệu thường gặp là swagger-config trả 302 tới /login. Nếu curl theo redirect, response cuối cùng có thể là 200 HTML.

Kiểm tra mà không follow redirect:

~~~bash
curl -i http://localhost:8080/v3/api-docs/swagger-config
~~~

Nếu response là 302 và Location trỏ tới login, request đang bị Spring Security hoặc proxy authentication chặn.

Nếu policy yêu cầu login, hãy bảo đảm trình duyệt đã đăng nhập và session cookie được gửi tới cùng origin. Nếu CI cần tải document, dùng credential có quyền đọc docs và kiểm tra response không phải HTML.

Không dùng curl -L rồi chỉ nhìn status cuối cùng. Cần kiểm tra cả redirect chain để tránh coi trang login là OpenAPI document.

## 13. Static resource mapping bị thay đổi hoặc ghi đè

Swagger UI bundle thường được phục vụ từ tài nguyên đóng gói trong dependency. Cấu hình WebMvcConfigurer, ResourceHandlerRegistry hoặc custom ResourceResolver có thể vô tình thay đổi mapping.

Các nguyên nhân:

- Ứng dụng định nghĩa resource handler bắt tất cả path và không cho fallback.
- Custom path pattern bắt /swagger-ui/** trước handler của WebJar.
- Static resource location bị thay thế.
- Resource chain hoặc version strategy không resolve được asset.
- Một controller mapping vô tình chiếm URL /swagger-ui/**.
- Context path hoặc servlet path bị tính sai.

Nếu đã cấu hình addResourceHandlers, hãy kiểm tra mapping cho static assets và đảm bảo không ghi đè mapping do Springdoc/Swagger UI cần.

Không thêm resource handler mới một cách mù quáng. Trước tiên kiểm tra response của asset và mapping hiện tại. Nếu lỗi chỉ xuất hiện sau khi thêm custom resource configuration, tạm thời đối chiếu với cấu hình tối thiểu trong nhánh test để xác định xung đột.

## 14. MIME type và X-Content-Type-Options

Trình duyệt có thể chặn JavaScript hoặc CSS nếu server trả MIME type không đúng, đặc biệt khi response có header X-Content-Type-Options: nosniff.

Ví dụ:

- File .js cần được phục vụ với MIME type JavaScript.
- File .css cần Content-Type text/css.
- HTML page cần Content-Type text/html.
- OpenAPI JSON cần Content-Type application/json.

Nếu một file JS trả application/json hoặc text/html, xem lại proxy, static resource handler và error page mapping.

Không xóa nosniff để che lỗi MIME type. Hãy sửa Content-Type ở nguồn phục vụ tài nguyên. Header bảo vệ trình duyệt nên được giữ theo security policy.

## 15. Reverse proxy và context path

Ứng dụng có thể chạy tại root path nội bộ nhưng được công bố dưới một prefix:

~~~text
Public URL:
https://api.example.com/catalog/swagger-ui.html

Internal application:
http://catalog-service:8080/swagger-ui.html
~~~

Nếu reverse proxy không chuyển tiếp prefix đúng, trang HTML có thể tải nhưng các request tương đối tới /swagger-ui/** hoặc /v3/api-docs/** bị gửi sai path.

Kiểm tra:

- Context path của Spring Boot.
- Prefix mà ingress hoặc reverse proxy thêm/bỏ.
- Location header trong redirect.
- URL swagger-config trong HTML/JS.
- URL document trong swagger-config.
- Forwarded headers và public scheme/host.
- Đường dẫn static assets được browser gọi.

Nếu ứng dụng dùng server.servlet.context-path=/catalog, các URL public cần phản ánh context path đó. Không thêm prefix hai lần nếu proxy đã rewrite path trước khi chuyển vào ứng dụng.

## 16. Forwarded headers và public URL

Khi ứng dụng chạy sau proxy, Spring Boot có thể cần xử lý Forwarded hoặc X-Forwarded-* headers để tạo URL đúng.

Ví dụ cấu hình thường gặp:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Giá trị chính xác phụ thuộc Spring Boot version và kiến trúc proxy. Có thể cần ForwardedHeaderFilter hoặc cấu hình native tùy môi trường.

Proxy phải loại bỏ header forwarded do client tự gửi rồi tự thiết lập giá trị đáng tin cậy. Nếu ứng dụng tin header tùy ý, attacker có thể khiến document hoặc redirect chứa host/scheme giả.

Nếu swagger-config hoặc OpenAPI document sinh URL nội bộ như http://localhost:8080, kiểm tra public host, scheme, prefix và forwarded header chain. Đừng sửa bằng cách hard-code URL production trong mọi profile nếu ứng dụng cần chạy nhiều môi trường.

## 17. CORS khi UI và OpenAPI document khác origin

Nếu Swagger UI được host ở một origin và OpenAPI document ở origin khác, browser áp dụng same-origin policy.

Ví dụ:

~~~text
Swagger UI:
https://docs.example.com

OpenAPI document:
https://api.example.com/v3/api-docs
~~~

Server cung cấp document cần cho phép origin của docs site qua CORS. Nếu UI thử gọi API ở origin khác, API server cũng cần policy CORS phù hợp.

Cần kiểm tra:

- Access-Control-Allow-Origin có khớp origin của trang UI không.
- OPTIONS preflight có được xử lý không.
- Authorization header có được cho phép không.
- Cookie/session có cần credentials không.
- Không dùng wildcard origin cùng credentialed request.

Nếu UI và document cùng origin, tránh cấu hình CORS rộng không cần thiết. CORS không thay thế authentication và không quyết định ai có quyền đọc tài liệu.

## 18. Content Security Policy chặn JavaScript hoặc CSS

CSP có thể chặn script, style, font hoặc fetch của Swagger UI. Console thường hiển thị thông báo Refused to load hoặc connect vì vi phạm policy.

Kiểm tra các directive:

- script-src cho JavaScript bundle.
- style-src cho CSS.
- font-src cho font nếu bundle dùng.
- img-src cho logo hoặc hình ảnh.
- connect-src cho swagger-config, OpenAPI document và API server.

Nếu dùng CDN, origin CDN phải được cho phép theo đúng directive. Nếu self-host assets, ưu tiên cùng origin để giảm số nguồn bên ngoài.

Không đặt CSP thành wildcard để xử lý nhanh. Xác định request bị chặn và chỉ thêm nguồn cần thiết. Nếu dùng nonce hoặc hash cho inline script, cấu hình trang Swagger UI cần tương thích với policy đó.

## 19. Cache cũ hoặc asset version không đồng bộ

Browser cache, reverse proxy cache hoặc CDN cache có thể giữ HTML/JS cũ trong khi ứng dụng đã nâng Springdoc hoặc Swagger UI.

Triệu chứng:

- Trang mới tham chiếu file bundle đã bị thay tên.
- JS cũ gọi endpoint config không còn tồn tại.
- swagger-config còn cache URL document cũ.
- Một số người dùng gặp lỗi nhưng tab ẩn danh hoạt động.
- Sau deploy, một replica phục vụ asset version khác replica còn lại.

Kiểm tra response headers Cache-Control, ETag, Last-Modified và Age. Thử hard reload hoặc cache disabled trong DevTools để xác định có phải stale asset hay không.

Không xóa cache ở mọi lớp ngay khi thấy lỗi. Trước tiên xác minh HTML, JS và swagger-config đang thuộc cùng một version. Sau đó điều chỉnh cache policy hoặc versioned asset strategy phù hợp.

## 20. Kiểm tra cấu hình document group hoặc URL tùy chỉnh

Nếu ứng dụng có nhiều GroupedOpenApi, swagger-config có thể trỏ tới một group không còn tồn tại hoặc sai tên.

Ví dụ group partner thường có document URL dạng:

~~~text
/v3/api-docs/partner
~~~

Kiểm tra group name, pathsToMatch, packagesToScan và endpoint thực tế. Nếu group bị đổi tên, cập nhật swagger-ui.url hoặc danh sách urls.

Nếu cấu hình nhiều document, kiểm tra cả urlsPrimaryName hoặc tên document mặc định theo property/version đang dùng. Một cấu hình sai có thể làm UI tải được nhưng không chọn đúng document.

Không lấy URL của Swagger UI làm URL OpenAPI. swagger-ui.path là đường dẫn giao diện; api-docs.path là đường dẫn document. Hai property có nhiệm vụ khác nhau.

## 21. Checklist chẩn đoán bằng curl

Có thể chạy lần lượt các lệnh sau trong môi trường ứng dụng đang hoạt động:

~~~bash
curl -i http://localhost:8080/swagger-ui.html

curl -i http://localhost:8080/swagger-ui/index.html

curl -i http://localhost:8080/v3/api-docs/swagger-config

curl -i http://localhost:8080/v3/api-docs

curl -I http://localhost:8080/swagger-ui/swagger-ui-bundle.js
~~~

Nếu dùng context path hoặc custom path, thay URL tương ứng. Nếu endpoint yêu cầu authentication, thêm credential an toàn từ secret store.

Diễn giải kết quả:

- HTML UI lỗi: kiểm tra UI starter, path và security.
- JS/CSS lỗi: kiểm tra WebJar/static mapping, MIME type, CSP và proxy.
- swagger-config lỗi: kiểm tra config-url, security, redirect và api-docs path.
- OpenAPI JSON lỗi: kiểm tra api-docs enabled, group, customizer và exception log.
- Mọi request trả 200 nhưng UI lỗi: kiểm tra Content-Type, body, browser console và phiên bản asset.

## 22. Kiểm tra bằng MockMvc

Có thể dùng MockMvc để xác minh các endpoint chính trong ứng dụng Servlet:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SwaggerUiResourceTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void shouldServeOpenApiDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ))
            .andExpect(jsonPath("$.openapi").exists());
    }

    @Test
    void shouldServeSwaggerConfiguration() throws Exception {
        mockMvc.perform(get("/v3/api-docs/swagger-config"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ));
    }
}
~~~

Đường dẫn swagger-config có thể thay đổi theo api-docs.path và config-url. Hãy dùng URL thực tế của dự án.

Static asset test có thể kiểm tra một bundle path cụ thể, nhưng tên file thay đổi theo Swagger UI version. Tránh hard-code tên asset nếu dependency upgrade thường xuyên; có thể kiểm tra trang UI và dùng browser smoke test để xác nhận các tài nguyên được tham chiếu tải thành công.

Với WebFlux, dùng WebTestClient. MockMvc/WebTestClient không mô phỏng đầy đủ reverse proxy, CSP của browser hoặc CDN; các phần đó cần integration test ở môi trường gần production.

## 23. Kiểm tra bằng Browser smoke test

Sau khi endpoint server trả đúng, mở Swagger UI bằng browser và xác minh:

1. Trang HTML tải thành công.
2. Không có lỗi JavaScript trong Console.
3. Các bundle JS/CSS trả 200 với MIME type đúng.
4. swagger-config trả JSON hợp lệ.
5. URL document trong config truy cập được.
6. OpenAPI document có paths và components mong đợi.
7. Tag và operation hiển thị.
8. Authorize hoạt động theo security scheme.
9. Try it out gọi đúng host và path trong môi trường test.
10. Không có lỗi CORS/CSP hoặc redirect ngoài ý muốn.

Nếu trang chạy sau proxy, thực hiện smoke test bằng URL public, không chỉ localhost. Cấu hình proxy là một phần của đường dẫn mà người dùng thực sự sử dụng.

## 24. Bảng triệu chứng và nguyên nhân

| Triệu chứng | Request cần kiểm tra đầu tiên | Nguyên nhân thường gặp |
|---|---|---|
| Trang Swagger UI 404 | /swagger-ui.html | Thiếu UI starter hoặc path đổi |
| Trang tải nhưng trống | JS/CSS bundle | Static resource 404, CSP hoặc MIME type |
| Failed to load remote configuration | swagger-config | Security, redirect, config-url sai |
| Failed to load API definition | OpenAPI JSON/YAML | api-docs disabled, sai URL, 401/404/5xx |
| Swagger UI hiện Petstore/default API | swagger-config | URL document của ứng dụng chưa được cấu hình đúng |
| Chỉ lỗi sau deploy | Mọi request dưới public prefix | Reverse proxy, context path hoặc forwarded headers |
| Local chạy, domain khác lỗi | swagger-config/document | CORS, CSP hoặc proxy |
| Một số user lỗi, user khác không | JS/CSS/config cache | Browser/CDN stale cache |
| UI tải được nhưng Try it out lỗi | API operation request | CORS hoặc security API, không phải static UI |
| JSON document trả HTML | swagger-config hoặc /v3/api-docs | Redirect login hoặc error page |

Bảng này giúp chọn request cần kiểm tra; kết luận cuối cùng phải dựa trên response và log thực tế.

## 25. Quy trình xử lý lỗi theo thứ tự

Khi Swagger UI không hiển thị API:

1. Mở Network tab và tìm request đầu tiên thất bại.
2. Xác nhận trang UI có được phục vụ không.
3. Xác nhận JS/CSS/WebJar assets có trả 200 và MIME type đúng.
4. Kiểm tra swagger-config có trả JSON hay bị redirect/chặn.
5. Đọc URL document trong swagger-config.
6. Gọi trực tiếp OpenAPI JSON/YAML và validate body.
7. Kiểm tra starter, api-docs.enabled và swagger-ui.enabled.
8. Kiểm tra Spring Security matcher và thứ tự filter chain.
9. Kiểm tra context path, reverse proxy và forwarded headers.
10. Kiểm tra CORS/CSP nếu có cross-origin hoặc CDN.
11. Kiểm tra cache khi lỗi chỉ xuất hiện sau deploy hoặc trên một số browser.
12. Chạy MockMvc/WebTestClient và browser smoke test.

Không thay nhiều property cùng lúc. Sửa một nguyên nhân, chạy lại các request liên quan rồi xác nhận lỗi đã hết. Điều này giúp tránh tạo thêm lỗi mới và giữ được nguyên nhân gốc.

## 26. Nguyên tắc phòng tránh

Để Swagger UI tải ổn định:

1. Chọn đúng UI starter theo Spring MVC hoặc WebFlux.
2. Giữ API docs và Swagger UI enabled ở những môi trường cần dùng.
3. Quản lý rõ swagger-ui.path, config-url và document URL.
4. Bảo vệ đồng thời UI, static assets, swagger-config và OpenAPI document theo cùng policy phù hợp.
5. Kiểm tra response Content-Type và body, không chỉ status 200.
6. Không để login redirect bị hiểu nhầm thành document JSON.
7. Giữ static resource mapping không xung đột với WebJar.
8. Cấu hình context path và reverse proxy nhất quán.
9. Chỉ tin forwarded headers từ proxy được kiểm soát.
10. Cấu hình CORS và CSP theo origin thực tế, không mở wildcard tùy tiện.
11. Kiểm soát cache và version của asset khi deploy.
12. Test endpoint document trong CI và chạy browser smoke test cho URL public.

Swagger UI phụ thuộc đồng thời vào trang HTML, tài nguyên tĩnh, swagger-config và OpenAPI document. Khi kiểm tra từng request theo đúng thứ tự, đối chiếu status, Content-Type, body và redirect, nhóm phát triển có thể xác định chính xác lỗi nằm ở dependency, security, mapping, proxy hay browser policy thay vì thay đổi cấu hình một cách mò mẫm.

## 27. Tài liệu tham khảo

- Springdoc OpenAPI documentation: https://springdoc.org/
- Springdoc configuration properties: https://springdoc.org/properties.html
- Swagger UI configuration: https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/
- Spring Security request authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Boot forwarded headers: https://docs.spring.io/spring-boot/reference/howto/webserver.html

