# Thuộc tính bật hoặc tắt Swagger UI

springdoc-openapi có thể công bố đặc tả OpenAPI và cung cấp Swagger UI để người phát triển đọc, tìm kiếm và thử các operation của API. Trong nhiều môi trường, hai chức năng này cần được điều khiển độc lập: nhóm phát triển có thể cần giao diện Swagger UI ở local hoặc development, trong khi production chỉ cung cấp tài liệu cho một pipeline được kiểm soát hoặc tắt hoàn toàn việc công bố tài liệu.

Thuộc tính chính để điều khiển giao diện là **springdoc.swagger-ui.enabled**. Thuộc tính này bật hoặc tắt Swagger UI khi ứng dụng có starter UI. Đặc tả OpenAPI JSON/YAML được điều khiển riêng bằng **springdoc.api-docs.enabled**. Hiểu rõ sự khác nhau giữa hai thuộc tính giúp tránh tình trạng đã tắt giao diện nhưng tài liệu JSON vẫn công khai, hoặc Swagger UI không thể tải đặc tả do endpoint OpenAPI bị tắt.

## 1. Vai trò của Swagger UI trong ứng dụng Spring Boot

Swagger UI là giao diện web đọc đặc tả OpenAPI. Khi tích hợp qua springdoc-openapi, ứng dụng thường cung cấp:

- Một trang vào Swagger UI, mặc định thường là /swagger-ui.html.
- Các tài nguyên tĩnh như JavaScript, CSS và hình ảnh dưới /swagger-ui/**.
- Đặc tả OpenAPI JSON tại /v3/api-docs.
- Đặc tả OpenAPI YAML tại /v3/api-docs.yaml.
- Các đặc tả riêng cho document group tại /v3/api-docs/{group}.

Swagger UI đọc đặc tả OpenAPI rồi dựng giao diện theo path, method, parameter, request body, response và security scheme. Người dùng có thể xem schema, thử request và quan sát response nếu API cùng các chính sách bảo mật cho phép.

Swagger UI là thành phần giao diện. OpenAPI JSON/YAML là tài liệu hợp đồng mà Swagger UI hiển thị. Hai thành phần có liên quan nhưng không phải cùng một endpoint hay cùng một thuộc tính cấu hình.

## 2. Thuộc tính springdoc.swagger-ui.enabled

Để bật Swagger UI:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
~~~

Để tắt Swagger UI:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
~~~

Thuộc tính springdoc.swagger-ui.enabled là cờ Boolean trong cấu hình Spring Boot. Khi dùng starter có giao diện Swagger UI, giá trị mặc định thường là bật. Khai báo rõ true hoặc false giúp cấu hình theo môi trường dễ đọc và dễ kiểm tra hơn.

Thuộc tính này điều khiển việc tích hợp Swagger UI. Nó không thay thế springdoc.api-docs.enabled, không thay đổi các endpoint nghiệp vụ và không tự áp dụng authentication hoặc authorization cho những endpoint tài liệu còn hoạt động.

Nếu ứng dụng chỉ có starter API-only, không có thành phần Swagger UI để bật. Khi đó, đặt springdoc.swagger-ui.enabled: true không tự bổ sung thư viện giao diện còn thiếu.

## 3. Phân biệt Swagger UI với OpenAPI JSON/YAML

Để điều khiển tài liệu đầy đủ, cần hiểu hai thuộc tính:

| Thuộc tính | Chức năng |
|---|---|
| springdoc.swagger-ui.enabled | Bật hoặc tắt giao diện Swagger UI |
| springdoc.api-docs.enabled | Bật hoặc tắt endpoint sinh OpenAPI JSON/YAML |

OpenAPI endpoint mặc định thường gồm /v3/api-docs và /v3/api-docs.yaml. Swagger UI thường tải JSON từ endpoint OpenAPI này để dựng giao diện.

Ví dụ tắt Swagger UI nhưng giữ đặc tả:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: true
~~~

Trong cấu hình này, người dùng không có giao diện Swagger UI do ứng dụng cung cấp, nhưng endpoint OpenAPI vẫn có thể truy cập theo security policy của ứng dụng.

Ví dụ tắt cả hai:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: false
~~~

Đây thường là cấu hình phù hợp khi môi trường không cần công bố giao diện hoặc đặc tả qua ứng dụng đang chạy.

## 4. Bốn trạng thái kết hợp thường gặp

Swagger UI và OpenAPI document có thể được bật/tắt độc lập:

| Swagger UI | OpenAPI docs | Kết quả |
|---|---|---|
| Bật | Bật | Swagger UI có thể tải đặc tả OpenAPI nội bộ và hiển thị API |
| Tắt | Bật | Không có giao diện UI; JSON/YAML vẫn được cung cấp |
| Bật | Tắt | UI không thể tải endpoint OpenAPI nội bộ mặc định; chỉ hữu ích nếu được cấu hình dùng một đặc tả bên ngoài hoặc nguồn khác |
| Tắt | Tắt | Cả UI và endpoint OpenAPI nội bộ đều bị tắt |

Trạng thái bật UI nhưng tắt OpenAPI nội bộ cần được cấu hình có chủ đích. Ví dụ, Swagger UI có thể được dùng như một viewer cho file đặc tả đã xuất bản ở máy chủ khác. Khi đó, phải khai báo URL đặc tả ngoài và bảo đảm browser truy cập được URL đó.

Không nên bật Swagger UI nhưng tắt OpenAPI rồi kỳ vọng UI vẫn tự tìm được API của ứng dụng. Nếu không có nguồn đặc tả thay thế, giao diện sẽ không có document để hiển thị.

## 5. Bật Swagger UI trong môi trường phát triển

Có thể bật Swagger UI trong application-dev.yml:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    path: /docs
  api-docs:
    enabled: true
~~~

Khi profile dev đang hoạt động, truy cập đường dẫn UI đã cấu hình:

~~~text
http://localhost:8080/docs
~~~

Đường dẫn /docs là ví dụ tùy biến. Nếu không khai báo springdoc.swagger-ui.path, hãy dùng đường dẫn mặc định của phiên bản đang cài, thường là /swagger-ui.html.

Trong môi trường phát triển, UI giúp nhóm kiểm tra request/response, xem schema và thử API nhanh. Tuy nhiên, nếu ứng dụng sử dụng dữ liệu thật hoặc kết nối dịch vụ nhạy cảm, vẫn cần cấu hình Spring Security phù hợp ngay cả trong môi trường development.

## 6. Tắt Swagger UI trong production bằng profile

Một cách thường dùng là bật UI ở local/dev và tắt UI ở production:

application.yml:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
  api-docs:
    enabled: true
~~~

application-prod.yml:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: false
~~~

Khi profile prod được kích hoạt, các giá trị trong application-prod.yml ghi đè cấu hình tương ứng từ file mặc định. Hãy xác nhận profile thực sự hoạt động trong môi trường triển khai.

Nếu production vẫn cần OpenAPI JSON cho API gateway, pipeline kiểm thử hoặc portal tài liệu riêng, có thể giữ api-docs.enabled: true trong khi tắt swagger-ui.enabled.

Không nên suy ra rằng production tự động dùng profile prod. Spring Boot chỉ nạp file profile khi profile đó được kích hoạt bằng cấu hình triển khai, biến môi trường hoặc tham số dòng lệnh.

## 7. Kích hoạt profile bằng biến môi trường hoặc command line

Có thể kích hoạt profile production bằng biến môi trường:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
~~~

Hoặc truyền tham số khi chạy ứng dụng:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Có thể ghi đè trực tiếp thuộc tính:

~~~bash
java -jar app.jar --springdoc.swagger-ui.enabled=false
~~~

Trong môi trường container, biến môi trường thường được đặt trong cấu hình deployment hoặc manifest của nền tảng. Không cần sửa file JAR để đổi trạng thái Swagger UI giữa các môi trường.

Sau khi khởi động, hãy kiểm tra log hoặc Actuator environment/configuration diagnostics theo chính sách vận hành để xác nhận profile và giá trị property thực tế. Không bật endpoint Actuator nhạy cảm công khai chỉ để xem cấu hình.

## 8. Dùng biến môi trường cho thuộc tính Swagger UI

Spring Boot hỗ trợ relaxed binding từ tên property sang biến môi trường. Thuộc tính:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
~~~

có thể được ghi đè bằng biến:

~~~bash
SPRINGDOC_SWAGGER_UI_ENABLED=false
~~~

Tương tự, để điều khiển OpenAPI document:

~~~bash
SPRINGDOC_API_DOCS_ENABLED=false
~~~

Biến môi trường hữu ích khi cùng một artifact được triển khai ở nhiều môi trường. Hãy kiểm tra chính tả, dấu gạch dưới và giá trị Boolean. Các giá trị true và false rõ ràng hơn những chuỗi tùy ý.

Trong Kubernetes, Docker Compose hoặc nền tảng cloud, biến cần được khai báo ở đúng container/process chạy Spring Boot. Đặt biến ở máy build nhưng không truyền tới container runtime sẽ không thay đổi cấu hình của ứng dụng đang chạy.

## 9. Thứ tự ưu tiên cấu hình

Một thuộc tính có thể được khai báo ở nhiều nguồn. Spring Boot áp dụng quy tắc precedence của externalized configuration; nguồn có độ ưu tiên cao hơn sẽ ghi đè nguồn thấp hơn.

Trong các tình huống phổ biến, thứ tự từ thấp đến cao thường là:

1. Giá trị mặc định trong ứng dụng.
2. File cấu hình đóng gói như application.yml.
3. File cấu hình theo profile như application-prod.yml.
4. Biến môi trường của tiến trình.
5. Java system properties.
6. Tham số dòng lệnh của ứng dụng.

Thứ tự đầy đủ còn có các nguồn cấu hình khác như config data được import, test properties và DevTools. Khi có xung đột, hãy kiểm tra tài liệu externalized configuration của đúng phiên bản Spring Boot.

Ví dụ, file production đặt:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
~~~

nhưng lệnh khởi động lại truyền:

~~~bash
java -jar app.jar --springdoc.swagger-ui.enabled=true
~~~

thì tham số command line có thể ghi đè giá trị trong file. Vì vậy, khi UI vẫn xuất hiện dù đã sửa YAML, cần kiểm tra các nguồn cấu hình có độ ưu tiên cao hơn và giá trị thực tế của tiến trình.

## 10. Tùy biến URL Swagger UI

Thuộc tính springdoc.swagger-ui.path thay đổi đường dẫn vào giao diện:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    path: /api-docs-ui
~~~

Người dùng truy cập:

~~~text
http://localhost:8080/api-docs-ui
~~~

Path tùy biến không phải là biện pháp bảo mật. Đổi /swagger-ui.html thành /api-docs-ui chỉ thay URL truy cập, không giới hạn ai có quyền xem. Hãy dùng Spring Security hoặc lớp bảo vệ ở gateway nếu tài liệu cần xác thực.

Khi đổi path, cập nhật các rule Spring Security, reverse proxy, ingress, smoke test và hướng dẫn vận hành. Cũng cần xác minh đường dẫn tài nguyên tĩnh mà UI tải sau khi redirect.

## 11. Tùy biến URL OpenAPI mà Swagger UI sử dụng

Swagger UI cần biết URL đặc tả. Mặc định, springdoc thường trỏ tới tài liệu do ứng dụng sinh ra. Có thể cấu hình một URL cụ thể:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    url: /v3/api-docs
~~~

Nếu dùng đặc tả đã xuất bản ở máy chủ khác:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    url: https://docs.example.com/contracts/store-api.json
~~~

Khi dùng URL ngoài, browser phải truy cập được địa chỉ đó. Nếu khác origin, máy chủ cung cấp đặc tả cần cấu hình CORS phù hợp. HTTPS page không nên tải spec qua HTTP vì mixed content có thể bị browser chặn.

Thuộc tính url chọn một nguồn đặc tả. Với nhiều document group hoặc nhiều API, có thể cấu hình danh sách springdoc.swagger-ui.urls theo cú pháp được hỗ trợ bởi phiên bản đang dùng.

## 12. Dùng nhiều đặc tả trong Swagger UI

Ví dụ cấu hình danh sách tài liệu:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Partner API
        url: /v3/api-docs/partner
      - name: Internal API
        url: /v3/api-docs/internal
~~~

Swagger UI có thể hiển thị danh sách để người dùng chọn document. Mỗi URL phải trả về một OpenAPI document hợp lệ và phải được truy cập theo chính sách bảo mật tương ứng.

Nếu group internal cần quyền cao hơn public, chỉ ẩn group khỏi dropdown không đủ để bảo vệ. Phải phân quyền endpoint /v3/api-docs/internal tại server hoặc gateway. Người dùng có thể gọi URL trực tiếp mà không cần dùng giao diện.

Tên và cấu trúc thuộc tính urls cần tuân theo binding model của phiên bản springdoc đang sử dụng. Khi cấu hình YAML phức tạp, kiểm tra giá trị đã bind và URL request thực tế trong Developer Tools.

## 13. Kết hợp bật/tắt UI với API docs theo từng nhu cầu

Một số cấu hình mẫu:

**Development:**

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
  api-docs:
    enabled: true
~~~

**Production, chỉ cho pipeline lấy JSON:**

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: true
~~~

**Production, không phát hành tài liệu:**

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: false
~~~

**Swagger UI đọc đặc tả ngoài:**

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    url: https://docs.example.com/contracts/store-api.json
  api-docs:
    enabled: false
~~~

Ví dụ cuối chỉ phù hợp khi Swagger UI không cần document nội bộ do ứng dụng sinh ra và URL ngoài có thể được truy cập an toàn. Nếu cấu hình group hoặc URL ngoài, hãy kiểm tra chúng có bị ghi đè bởi các thuộc tính url/urls khác hay không.

## 14. Tắt UI bằng property hay bỏ starter UI?

Có hai cách khác nhau:

| Cách | Khi phù hợp | Hệ quả |
|---|---|---|
| springdoc.swagger-ui.enabled=false | Cùng một artifact cần bật UI ở dev và tắt UI ở production | Giữ dependency UI trong artifact nhưng vô hiệu hóa tích hợp theo cấu hình |
| Dùng starter API-only hoặc bỏ starter UI | Dự án không cần Swagger UI ở bất kỳ môi trường nào | Không đóng gói thành phần Swagger UI, chỉ giữ khả năng sinh OpenAPI nếu dùng API starter |

Nếu mọi môi trường đều không cần giao diện, dùng starter API-only giúp giảm dependency và tài nguyên không cần thiết. Nếu nhóm phát triển cần UI ở local nhưng production cần tắt, property theo profile thường tiện hơn.

Đổi dependency cần cập nhật build file và kiểm tra dependency tree. Đổi property cần triển khai lại ứng dụng để cấu hình mới được nạp.

## 15. Thuộc tính bật/tắt không phải công tắc runtime

springdoc.swagger-ui.enabled là cấu hình được đọc trong quá trình khởi tạo Spring Application Context. Thay đổi biến môi trường hoặc file YAML sau khi ứng dụng đã chạy thường không làm bean và endpoint tự thay đổi trạng thái ngay lập tức.

Để áp dụng giá trị mới, thông thường cần:

1. Cập nhật cấu hình môi trường.
2. Khởi động lại hoặc rollout ứng dụng.
3. Xác minh instance mới đã nạp cấu hình.
4. Kiểm tra URL UI và OpenAPI document sau rollout.

Không xem đây là một feature flag có thể bật/tắt tức thời qua HTTP request. Nếu cần điều khiển truy cập động, hãy dùng cơ chế authorization phù hợp; không xây endpoint cho phép người dùng tùy ý bật Swagger UI trong production.

## 16. Kết hợp với Spring Security

Tắt Swagger UI không đồng nghĩa endpoint OpenAPI đã được bảo vệ. Nếu springdoc.api-docs.enabled vẫn là true, người dùng có thể tiếp tục tải JSON/YAML theo đường dẫn tài liệu nếu security policy cho phép.

Ví dụ chỉ cho phép authority DOCS_READ truy cập UI và OpenAPI:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(
        "/swagger-ui.html",
        "/swagger-ui/**",
        "/v3/api-docs",
        "/v3/api-docs/**",
        "/v3/api-docs.yaml"
    ).hasAuthority("DOCS_READ")
    .anyRequest().authenticated()
);
~~~

Nếu dùng path tùy biến, cập nhật matcher tương ứng. Với nhiều SecurityFilterChain, kiểm tra thứ tự và securityMatcher để request tài liệu không bị một chain ít hạn chế hơn xử lý trước.

Nếu mục tiêu là không phát hành tài liệu trong production, tắt cả UI và OpenAPI bằng property rồi xác minh endpoint thực tế. Nếu mục tiêu là chỉ cho một nhóm người đọc, giữ endpoint cần thiết và bảo vệ bằng authentication/authorization thay vì chỉ ẩn UI.

## 17. Tác động tới reverse proxy, gateway và cache

Trong môi trường production, đường dẫn công khai có thể khác đường dẫn backend. Khi thay springdoc.swagger-ui.path, cần cập nhật:

- Ingress hoặc reverse proxy route.
- API gateway route và policy.
- Spring Security matcher.
- Health/smoke test và monitoring.
- Link tài liệu trong portal hoặc hướng dẫn nội bộ.

Nếu UI bị tắt nhưng CDN vẫn cache HTML hoặc JavaScript cũ, người dùng có thể còn thấy giao diện trong một khoảng thời gian. Nếu OpenAPI JSON được cache, nội dung tài liệu cũ cũng có thể tiếp tục được phục vụ.

Sau khi thay đổi trạng thái:

1. Rollout ứng dụng.
2. Xác minh endpoint tại origin.
3. Xác minh endpoint qua domain/gateway công khai.
4. Purge cache nếu có nội dung UI/spec cũ cần loại bỏ.
5. Kiểm tra bằng cửa sổ ẩn danh hoặc client không dùng cache.

Không dựa vào kết quả trên localhost để kết luận cấu hình production đã được áp dụng.

## 18. Kiểm tra trạng thái Swagger UI sau khi bật

Khi bật UI, kiểm tra các URL:

~~~bash
curl -i http://localhost:8080/swagger-ui.html
curl -i http://localhost:8080/v3/api-docs
~~~

Trang vào Swagger UI có thể trả redirect tới tài nguyên HTML của UI. Vì vậy, hãy kiểm tra cả Location và URL đích thay vì yêu cầu /swagger-ui.html luôn trả 200.

Trong browser:

- Trang Swagger UI có tải được HTML, CSS và JavaScript không?
- UI có tải đúng URL OpenAPI document không?
- Document trả 200 và JSON parse được không?
- Danh sách group có đúng không?
- Nút Authorize và Try it out có hoạt động theo security policy không?
- Có lỗi CORS, mixed content hoặc 401/403 không?

Nếu trang UI mở được nhưng hiện Failed to load API definition, kiểm tra request OpenAPI trong Network panel. Lỗi có thể nằm ở api-docs.enabled, URL đặc tả, security, proxy hoặc CORS.

## 19. Kiểm tra trạng thái sau khi tắt

Khi springdoc.swagger-ui.enabled=false, kiểm tra điểm vào UI và tài nguyên tĩnh. Tùy phiên bản, cấu hình path và security filter, kết quả có thể là 404 hoặc phản hồi từ lớp bảo vệ như 401/403. Điều quan trọng là không còn giao diện Swagger UI được phục vụ theo policy mong muốn.

~~~bash
curl -i http://localhost:8080/swagger-ui.html
curl -i http://localhost:8080/swagger-ui/index.html
~~~

Nếu chỉ tắt UI nhưng giữ OpenAPI:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
~~~

Các endpoint JSON/YAML vẫn có thể trả 200. Đây là hành vi đúng nếu springdoc.api-docs.enabled=true và policy cho phép truy cập.

Nếu đã tắt cả hai, kiểm tra endpoint JSON, YAML, UI và từng group. Không kết luận thành công chỉ vì trang /swagger-ui.html không mở được; document endpoint có thể vẫn hoạt động.

## 20. Kiểm thử cấu hình bằng Spring Boot

Có thể viết integration test cho các profile hoặc cấu hình khác nhau. Ví dụ test khi UI được tắt và OpenAPI vẫn bật:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "springdoc.swagger-ui.enabled=false",
    "springdoc.api-docs.enabled=true"
})
@AutoConfigureMockMvc
class SwaggerUiDisabledTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void openApiDocumentRemainsAvailable() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ));
    }
}
~~~

Test trên xác minh OpenAPI JSON vẫn được cung cấp. Việc xác minh UI bị tắt cần thêm request tới đường dẫn UI và assertion phù hợp với cách ứng dụng/security filter trả phản hồi trong phiên bản đang dùng.

Nếu kiểm tra profile, dùng @ActiveProfiles("prod") trong một test riêng hoặc chạy ứng dụng với profile production trong môi trường kiểm thử. Tránh chỉ kiểm tra property trong file; cần xác minh endpoint thật.

Với WebFlux, dùng WebTestClient thay cho MockMvc nếu ứng dụng chạy reactive stack. Đừng thêm cả hai test client chỉ vì ví dụ trên dùng MVC.

## 21. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Tắt Swagger UI nhưng /v3/api-docs vẫn trả 200 | Chỉ đặt swagger-ui.enabled=false | Tắt thêm api-docs.enabled nếu không muốn công bố spec |
| Swagger UI không xuất hiện ở dev | Profile đang active đặt enabled=false hoặc thiếu starter UI | Kiểm tra profile, dependency và giá trị property |
| UI vẫn xuất hiện ở production | Profile prod chưa active hoặc property bị nguồn ưu tiên cao ghi đè | Kiểm tra active profiles, environment và command line |
| Đặt enabled: false sai cấp YAML | Property không bind vào springdoc.swagger-ui.enabled | Kiểm tra thụt lề và tên property |
| UI mở nhưng không tải được spec | OpenAPI bị tắt, URL sai hoặc bị security chặn | Kiểm tra api-docs.enabled, url và Network |
| UI bật nhưng không có giao diện | Chỉ dùng starter API-only | Thêm starter UI tương ứng với MVC/WebFlux |
| Đổi swagger-ui.path nhưng vẫn dùng URL cũ | Link, security matcher hoặc proxy chưa cập nhật | Đồng bộ toàn bộ đường dẫn |
| Tắt UI nhưng browser vẫn thấy trang cũ | Browser/CDN cache tài nguyên cũ | Kiểm tra origin và purge cache phù hợp |
| UI group không tải được | URL group sai hoặc group endpoint bị chặn | Kiểm tra urls, group path và authorization |
| Đã tắt cả hai nhưng JSON vẫn có | Instance cũ, profile sai, property bị ghi đè hoặc gateway cache | Kiểm tra cấu hình runtime và gọi trực tiếp origin |
| Nghĩ đổi property sẽ áp dụng ngay | Property được đọc khi khởi tạo context | Restart hoặc rollout ứng dụng |

## 22. Quy trình cấu hình và xác minh

Thực hiện theo thứ tự:

1. Xác định môi trường cần Swagger UI: local, dev, test, staging hay production.
2. Xác định có cần công bố OpenAPI JSON/YAML ở môi trường đó không.
3. Chọn starter UI hoặc API-only đúng với MVC/WebFlux.
4. Đặt springdoc.swagger-ui.enabled và springdoc.api-docs.enabled rõ ràng.
5. Cấu hình theo profile hoặc biến môi trường nếu các môi trường có chính sách khác nhau.
6. Kiểm tra nguồn cấu hình có độ ưu tiên cao hơn có ghi đè property không.
7. Đồng bộ swagger-ui.path, OpenAPI path, security matcher và gateway route.
8. Khởi động hoặc rollout ứng dụng để nạp cấu hình mới.
9. Kiểm tra UI, JSON, YAML và từng document group trực tiếp.
10. Kiểm tra lại qua domain production và sau lớp cache/proxy.
11. Tự động hóa integration test cho các tổ hợp UI/docs cần hỗ trợ.
12. Ghi nhận chính sách đã chọn và kết quả xác minh cho từng môi trường.

## 23. Ghi nhớ

- springdoc.swagger-ui.enabled bật hoặc tắt giao diện Swagger UI.
- springdoc.api-docs.enabled điều khiển endpoint OpenAPI JSON/YAML.
- Tắt UI không đồng nghĩa tắt OpenAPI document.
- UI bật nhưng docs nội bộ tắt cần một URL đặc tả ngoài hoặc nguồn khác.
- Dùng profile, biến môi trường hoặc command line để điều khiển theo môi trường.
- Kiểm tra precedence vì command line và biến môi trường có thể ghi đè YAML.
- springdoc.swagger-ui.path đổi URL giao diện, không phải biện pháp bảo mật.
- Dùng starter API-only nếu không cần UI ở bất kỳ môi trường nào.
- Property được nạp khi ứng dụng khởi động; thường cần restart/rollout để áp dụng.
- Nếu cần giới hạn người đọc, dùng Spring Security hoặc gateway; ẩn UI không bảo vệ document endpoint.
- Xác minh trạng thái bằng request thực tế tới UI, JSON, YAML và group, cả ở origin lẫn domain công khai.

Để quản lý Swagger UI theo môi trường, hãy cấu hình springdoc.swagger-ui.enabled riêng với springdoc.api-docs.enabled. Bật UI ở môi trường phát triển, tắt ở production khi không cần giao diện, và quyết định rõ có tiếp tục cung cấp OpenAPI JSON/YAML hay không. Sau mỗi lần thay đổi, kiểm tra endpoint thực tế qua đúng đường đi triển khai để xác nhận cấu hình đã có hiệu lực.
