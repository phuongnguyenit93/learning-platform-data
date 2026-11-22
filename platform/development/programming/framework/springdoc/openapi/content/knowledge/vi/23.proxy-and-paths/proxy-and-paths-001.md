# Context path, servlet path và đường dẫn tài liệu tùy chỉnh

Khi triển khai Spring Boot cùng springdoc-openapi, URL mà người dùng nhìn thấy có thể khác URL mà ứng dụng nhận ở bên trong. Một hệ thống có thể chạy sau reverse proxy, nằm dưới một context path, dùng servlet mapping riêng hoặc đặt đường dẫn OpenAPI/Swagger UI tùy chỉnh. Nếu ghép nhầm các lớp này, trang Swagger UI có thể mở được nhưng không tải được OpenAPI JSON, redirect sang host nội bộ hoặc gửi request Try it out tới sai prefix.

Để cấu hình đúng, cần xác định từng lớp chịu trách nhiệm cho phần nào của URL:

1. Reverse proxy quyết định public host, scheme, port và có thể thêm hoặc loại một path prefix.
2. Context path đặt tiền tố cho toàn bộ ứng dụng servlet.
3. Servlet path đặt tiền tố cho DispatcherServlet của Spring MVC.
4. WebFlux có base path riêng cho các web handler.
5. springdoc đặt path riêng cho OpenAPI document và trang Swagger UI.

Các lớp này có thể được kết hợp, nhưng không nên khai báo cùng một prefix ở nhiều nơi nếu request không thực sự đi qua tất cả các lớp đó.

## 1. Nhìn URL theo từng thành phần

Một URL đầy đủ có dạng:

~~~text
https://api.example.com/platform/shop/mvc/api/orders
|      host       |proxy |context|servlet|controller
~~~

Trong ví dụ này:

| Thành phần | Giá trị | Nơi cấu hình |
| --- | --- | --- |
| Scheme | https | TLS tại proxy và forwarded headers |
| Host | api.example.com | DNS, reverse proxy, Forwarded hoặc X-Forwarded-Host |
| Proxy prefix | /platform | Routing/rewrite tại reverse proxy; có thể truyền bằng X-Forwarded-Prefix nếu proxy đã strip prefix |
| Context path | /shop | server.servlet.context-path trên Servlet stack |
| Servlet path | /mvc | spring.mvc.servlet.path cho DispatcherServlet |
| Controller mapping | /api/orders | @RequestMapping, @GetMapping hoặc route tương ứng |

Không phải ứng dụng nào cũng cần đủ các thành phần này. Phần lớn ứng dụng chỉ cần controller mapping và có thể thêm context path hoặc proxy prefix.

## 2. Phân biệt context path và servlet path

Hai khái niệm này thường bị nhầm vì đều xuất hiện như một đoạn prefix trong URL.

**Context path** là đường dẫn gốc của một web application trong servlet container. Nó áp dụng cho toàn bộ ứng dụng servlet, bao gồm controller, tài nguyên tĩnh, Swagger UI và OpenAPI endpoint.

**Servlet path** là đường dẫn mà servlet cụ thể được đăng ký để nhận request. Trong Spring MVC, spring.mvc.servlet.path đặt prefix cho DispatcherServlet; nó không phải context path của toàn bộ ứng dụng.

| Tiêu chí | Context path | Servlet path |
| --- | --- | --- |
| Phạm vi | Toàn bộ servlet web application | DispatcherServlet hoặc servlet được map |
| Thuộc tính Spring Boot | server.servlet.context-path | spring.mvc.servlet.path |
| Có tác động đến springdoc? | Có; UI và OpenAPI nằm dưới context path | Có thể ảnh hưởng mapping của MVC; cần kiểm tra tương thích thực tế |
| Dùng khi | Muốn ứng dụng chạy dưới một prefix chung | Cần map DispatcherServlet dưới một prefix riêng |
| Có dùng cho WebFlux? | Không dùng servlet context path | Không dùng servlet path |

Nếu mục tiêu chỉ là đặt toàn bộ ứng dụng dưới /shop, hãy bắt đầu với context path. Không thêm spring.mvc.servlet.path chỉ để tạo thêm một đoạn URL mà không có yêu cầu về servlet mapping.

## 3. Đặt context path cho Spring MVC

Với ứng dụng servlet Spring Boot, cấu hình server.servlet.context-path:

~~~yaml
server:
  servlet:
    context-path: /shop
~~~

Giả sử controller có mapping:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping
    List<OrderResponse> list() {
        return orderService.findAll();
    }
}
~~~

Đường dẫn bên ngoài của operation trở thành:

~~~text
http://localhost:8080/shop/api/orders
~~~

springdoc cũng nằm dưới context path. Với cấu hình mặc định, các URL thường là:

| Tài nguyên | URL |
| --- | --- |
| Swagger UI | /shop/swagger-ui.html |
| OpenAPI JSON | /shop/v3/api-docs |
| OpenAPI YAML | /shop/v3/api-docs.yaml |
| Swagger UI config | /shop/v3/api-docs/swagger-config |

Đây là các URL mặc định; nếu ứng dụng thay path của springdoc hoặc cấu hình management port, URL thực tế sẽ khác.

springdoc FAQ cũng xác nhận Swagger UI được đặt dưới context path, ví dụ context path /foo thì UI có URL /foo/swagger-ui.html.

## 4. Đặt servlet path cho DispatcherServlet

Trong Spring MVC, có thể đặt servlet mapping prefix bằng:

~~~yaml
spring:
  mvc:
    servlet:
      path: /mvc
~~~

Khi đó, request tới DispatcherServlet thường có dạng:

~~~text
/mvc/api/orders
~~~

Nếu đồng thời có context path /shop, URL servlet có thể có dạng:

~~~text
/shop/mvc/api/orders
~~~

Tuy nhiên, spring.mvc.servlet.path có một giới hạn quan trọng: Spring Boot dùng PathPatternParser làm chiến lược matching mặc định và chiến lược này không tương thích với việc cấu hình DispatcherServlet bằng path prefix. Không đổi sang servlet path nếu chưa kiểm tra rõ hệ quả với phiên bản Spring Boot, Spring MVC và springdoc đang dùng.

Nếu cần servlet mapping riêng, hãy xác minh:

- Ứng dụng khởi động được với path matching strategy đã chọn.
- Controller mapping hoạt động ở URL có servlet prefix.
- /v3/api-docs hoặc custom OpenAPI path vẫn được map đúng.
- Swagger UI tải được swagger-config và các tài nguyên WebJar.
- Các route bảo mật trong Spring Security khớp servlet path thực tế.

Với yêu cầu đơn giản là thêm prefix cho toàn ứng dụng, context path thường dễ dự đoán hơn servlet path.

## 5. Dùng base path cho Spring WebFlux

Ứng dụng reactive không sử dụng server.servlet.context-path hoặc spring.mvc.servlet.path. Spring Boot cung cấp spring.webflux.base-path để đặt base path cho các web handler:

~~~yaml
spring:
  webflux:
    base-path: /shop
~~~

Nếu ứng dụng WebFlux có route /api/orders, URL sẽ nằm dưới base path /shop/api/orders. Các endpoint springdoc được đăng ký trong cùng web application cũng cần được kiểm tra dưới base path này.

Không trộn cấu hình Servlet và WebFlux trong cùng hướng dẫn:

| Stack | Prefix của ứng dụng |
| --- | --- |
| Spring MVC / Servlet | server.servlet.context-path |
| DispatcherServlet trong Spring MVC | spring.mvc.servlet.path |
| Spring WebFlux | spring.webflux.base-path |

Nếu ứng dụng dùng WebFlux phía sau proxy, forwarded headers được xử lý bởi cơ chế của web server hoặc ForwardedHeaderTransformer, không phải ForwardedHeaderFilter của Servlet stack.

## 6. Đổi đường dẫn OpenAPI JSON/YAML

springdoc mặc định cung cấp OpenAPI JSON ở /v3/api-docs. Có thể thay bằng springdoc.api-docs.path:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
~~~

Khi đó JSON document được cung cấp ở path tùy chỉnh /openapi, tương đối với context path hoặc base path của ứng dụng. Ví dụ với context path /shop:

~~~text
/shop/openapi
~~~

springdoc cũng cung cấp YAML. Khi đổi API docs path, hãy kiểm tra chính xác URL YAML mà phiên bản springdoc đang sinh ra, thay vì giả định path cũ vẫn tồn tại. Với path /openapi, endpoint YAML thường được cung cấp theo dạng /openapi.yaml.

Có thể tắt endpoint tài liệu bằng:

~~~yaml
springdoc:
  api-docs:
    enabled: false
~~~

Việc tắt OpenAPI endpoint không đồng nghĩa với việc tắt Swagger UI theo cùng một thuộc tính. Nếu muốn tắt cả hai, cấu hình springdoc.swagger-ui.enabled riêng và kiểm tra endpoint thực tế.

## 7. Đổi đường dẫn trang Swagger UI

Để đổi URL HTML của Swagger UI, dùng springdoc.swagger-ui.path:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs.html
~~~

Với context path /shop, trang UI được mở tại:

~~~text
/shop/docs.html
~~~

Có thể kết hợp path OpenAPI và path Swagger UI:

~~~yaml
server:
  servlet:
    context-path: /shop

springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs.html
~~~

Các URL public mong đợi:

| Tài nguyên | URL |
| --- | --- |
| Swagger UI | /shop/docs.html |
| OpenAPI JSON | /shop/openapi |
| OpenAPI YAML | Kiểm tra endpoint YAML tương ứng với custom docs path |
| Swagger config | Kiểm tra endpoint config được sinh theo docs path |

springdoc.swagger-ui.path thay đổi URL HTML của giao diện; nó không đổi path API nghiệp vụ và cũng không tự thay đổi URL public của reverse proxy.

## 8. Phân biệt path tùy chỉnh của UI và URL của OpenAPI document

Swagger UI cần biết nơi tải OpenAPI document. Thông thường springdoc sinh cấu hình Swagger UI trỏ tới OpenAPI endpoint tương ứng.

Hai thuộc tính có vai trò khác nhau:

| Thuộc tính | Tác động |
| --- | --- |
| springdoc.swagger-ui.path | URL HTML mà người dùng mở để xem giao diện |
| springdoc.api-docs.path | URL JSON của hợp đồng OpenAPI |
| springdoc.swagger-ui.config-url | URL lấy Swagger UI configuration |
| springdoc.swagger-ui.url | URL của một OpenAPI document được chỉ định trực tiếp |

Chỉ đặt swagger-ui.path không thay đổi endpoint JSON. Chỉ đặt api-docs.path cũng không nhất thiết đổi URL HTML của giao diện.

Nếu cần trỏ Swagger UI tới một file OpenAPI bên ngoài hoặc tài liệu được host ở nơi khác, có thể dùng springdoc.swagger-ui.url hoặc cấu hình nhiều URL theo tính năng Swagger UI. Khi đó phải kiểm tra CORS và quyền truy cập của browser tới nguồn tài liệu đó.

Nếu tự đặt config-url, hãy bảo đảm URL trỏ tới endpoint Swagger UI config thực sự tồn tại. Một config-url cũ có thể khiến UI mở được HTML nhưng hiển thị lỗi không tải được cấu hình.

## 9. Kết hợp context path và custom docs path

Ví dụ đầy đủ cho Spring MVC:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /inventory

springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs.html
~~~

Giả sử controller mapping là /api/products, các URL nội bộ:

~~~text
GET http://localhost:8080/inventory/api/products
GET http://localhost:8080/inventory/openapi
GET http://localhost:8080/inventory/docs.html
~~~

Nếu có group tên admin, OpenAPI group thường nằm dưới docs path, ví dụ:

~~~text
http://localhost:8080/inventory/openapi/admin
~~~

Hãy xác minh endpoint group sau khi đổi springdoc.api-docs.path; không hard-code /v3/api-docs/{group} vào portal hoặc script nếu path đã được tùy chỉnh.

## 10. Reverse proxy có thể thêm hoặc loại path prefix

Reverse proxy thường cung cấp một URL public và chuyển tiếp request tới URL backend khác.

Ví dụ:

~~~text
Client:
https://api.example.com/platform/openapi

Proxy chuyển tiếp:
http://spring-app:8080/openapi
~~~

Trong trường hợp này, proxy đã loại prefix /platform trước khi chuyển request. Ứng dụng chỉ nhìn thấy /openapi, nên nếu cần sinh link public đúng, proxy phải truyền thông tin prefix gốc bằng X-Forwarded-Prefix.

Các header forwarded thường gặp:

| Header | Ý nghĩa |
| --- | --- |
| Forwarded | Header chuẩn RFC 7239 mang thông tin host/proto và thông tin proxy |
| X-Forwarded-For | IP client ban đầu hoặc chuỗi proxy |
| X-Forwarded-Host | Host mà client dùng ở phía public |
| X-Forwarded-Port | Port public |
| X-Forwarded-Proto | Scheme public, ví dụ https |
| X-Forwarded-Prefix | Path prefix public đã bị proxy loại khỏi request trước khi forward |

X-Forwarded-Prefix không phải header để tùy ý thêm một path mới. Nó biểu diễn prefix ban đầu đã bị loại bỏ trên đường chuyển tiếp.

Nếu proxy giữ nguyên prefix trong request gửi tới ứng dụng, không gửi cùng prefix thêm lần nữa như thể nó đã bị strip. Nếu vừa giữ prefix vừa để ứng dụng ghép prefix forwarded, URL có thể bị lặp /platform/platform/....

## 11. Ví dụ Nginx strip prefix và truyền forwarded headers

Ví dụ proxy công bố ứng dụng dưới /platform, sau đó loại prefix trước khi gửi request đến backend:

~~~nginx
location /platform/ {
    proxy_pass http://spring-app:8080/;

    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Prefix /platform;
}
~~~

Với cấu hình proxy_pass có URI / như trên, Nginx thay phần path khớp với location bằng URI của proxy_pass, do đó /platform/openapi được chuyển tới backend dưới /openapi. Cần kiểm tra cấu hình rewrite thực tế nếu location hoặc proxy_pass của dự án khác ví dụ.

Từ phía client:

~~~text
https://api.example.com/platform/openapi
https://api.example.com/platform/docs.html
~~~

Từ phía backend:

~~~text
http://spring-app:8080/openapi
http://spring-app:8080/docs.html
~~~

Proxy cần xóa hoặc ghi đè forwarded headers do client gửi từ Internet trước khi thiết lập giá trị tin cậy. Không để client tự chọn X-Forwarded-Host, X-Forwarded-Proto hoặc X-Forwarded-Prefix rồi để ứng dụng dùng chúng để sinh URL.

## 12. Xử lý forwarded headers theo phiên bản Spring Boot

Spring Boot và Spring Framework đã thay đổi tên property và cách xử lý forwarded headers qua các phiên bản. Hãy dùng cấu hình khớp với phiên bản dependency của ứng dụng.

**Spring Boot 2.2 đến các dòng Boot 3.x** thường dùng:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Giá trị framework sử dụng cơ chế forwarded header của Spring Framework. Với Servlet stack, đó là ForwardedHeaderFilter; với reactive stack, Spring Framework sử dụng ForwardedHeaderTransformer. Tùy web server và loại header, có thể chọn strategy native nếu server hỗ trợ đầy đủ.

**Spring Boot 4.x hiện hành** dùng namespace mới cho forwarded headers:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: web-server
        use-prefix: true
~~~

strategy: web-server dùng hỗ trợ forwarded header của embedded web server. use-prefix: true bật xử lý X-Forwarded-Prefix; theo tài liệu Spring Boot 4.2, header prefix này bị bỏ qua theo mặc định.

Nếu web server không hỗ trợ đầy đủ hoặc cần cơ chế chung của Spring Framework, có thể dùng:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: framework
        use-prefix: true
~~~

Không chép lẫn hai thế hệ property vào cùng cấu hình mà không kiểm tra version. Tài liệu springdoc FAQ vẫn có ví dụ server.forward-headers-strategy; tài liệu Spring Boot mới hơn dùng server.request.header.forwarded.*. Luôn ưu tiên property reference đúng phiên bản Boot đang chạy.

## 13. ForwardedHeaderFilter và ForwardedHeaderTransformer

Spring Framework cung cấp hai cơ chế tùy theo web stack:

| Web stack | Cơ chế của Spring Framework |
| --- | --- |
| Servlet / Spring MVC | ForwardedHeaderFilter |
| Reactive / Spring WebFlux | ForwardedHeaderTransformer |

Chúng điều chỉnh thông tin request để phản ánh scheme, host, port và prefix public dựa trên forwarded headers. Nhờ đó, framework và springdoc có thể sinh redirect, link và server URL phù hợp với địa chỉ client nhìn thấy.

Trong Spring Boot, nên ưu tiên property cấu hình forwarded header có sẵn trước khi tự đăng ký filter hoặc transformer. Tránh đăng ký hai cơ chế cùng xử lý một bộ header nếu chưa hiểu thứ tự và tác động của chúng.

Nếu chỉ muốn loại forwarded headers mà không tin giá trị của chúng, Spring Framework cung cấp chế độ removeOnly trên các thành phần tương ứng. Đây là lựa chọn hữu ích khi ứng dụng không nằm sau một proxy đáng tin cậy nhưng vẫn cần loại header giả do client gửi.

## 14. Rủi ro bảo mật của forwarded headers

Ứng dụng không thể tự biết header forwarded do proxy tin cậy thêm vào hay do client độc hại gửi trực tiếp. Nếu backend có thể truy cập trực tiếp từ Internet và vẫn tin X-Forwarded-Host, attacker có thể tác động tới URL được sinh ra.

Ví dụ rủi ro:

- OpenAPI server URL bị sinh với host do attacker kiểm soát.
- Redirect trỏ sang host không mong muốn.
- Link trong trang Swagger UI trỏ sang domain giả.
- Log hoặc audit ghi nhận sai IP/protocol gốc.
- Chính sách dựa trên host hoặc scheme bị đánh lừa.

Biện pháp:

1. Chỉ tin forwarded headers từ proxy/load balancer thuộc trust boundary.
2. Proxy phải xóa forwarded headers do client gửi và tự ghi giá trị chuẩn.
3. Giới hạn truy cập trực tiếp tới backend bằng network policy hoặc firewall khi phù hợp.
4. Cấu hình trusted proxy/IP range cho web server nếu cơ chế đó hỗ trợ.
5. Không cho phép host hoặc prefix tùy ý từ client được dùng để tạo URL public.
6. Kiểm tra URL sinh ra trong OpenAPI và redirect ở môi trường staging.

## 15. Khi nào cần ServerBaseUrlCustomizer?

springdoc có ServerBaseUrlCustomizer để điều chỉnh server base URL được suy ra khi tạo tài liệu. Có thể dùng khi đã xử lý forwarded headers đúng nhưng vẫn cần quy tắc riêng, chẳng hạn loại port nội bộ hoặc chuẩn hóa base URL.

Ví dụ:

~~~java
import org.springdoc.core.customizers.ServerBaseUrlCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiServerUrlConfig {

    @Bean
    ServerBaseUrlCustomizer serverBaseUrlCustomizer() {
        return serverBaseUrl -> {
            if (serverBaseUrl.startsWith("http://spring-app:")) {
                return serverBaseUrl.replace(
                    "http://spring-app:8080",
                    "https://api.example.com"
                );
            }
            return serverBaseUrl;
        };
    }
}
~~~

Đây là ví dụ minh họa nguyên tắc, không phải quy tắc thay thế proxy configuration. Trong production, tránh hard-code host nếu ứng dụng có nhiều domain hoặc môi trường. Có thể lấy public base URL từ cấu hình được quản lý theo môi trường.

Nếu customizer phải cắt chuỗi host/port bằng logic phức tạp, hãy cân nhắc dùng URI/URL API và kiểm tra scheme, host, port, path riêng rẽ. Không dùng replace rộng có thể vô tình thay đổi path hoặc host hợp lệ.

## 16. Tách URL public khỏi server URL trong OpenAPI

OpenAPI có servers để mô tả base URL mà client dùng khi gọi API. Khi springdoc suy ra server URL từ request, forwarded headers có thể ảnh hưởng tới host, scheme, port và prefix được sinh.

Ví dụ hợp đồng public mong muốn:

~~~yaml
servers:
  - url: https://api.example.com/platform
    description: Public API gateway
paths:
  /api/orders:
    get:
      responses:
        '200':
          description: Danh sách đơn hàng
~~~

Khi Swagger UI gửi request, URL được ghép từ server URL và path của operation. Nếu server URL thiếu /platform, request Try it out có thể bỏ qua proxy route. Nếu server URL chứa /platform/platform, request sẽ lặp prefix.

Không thêm context path hoặc proxy prefix vào cả servers.url và path operation nếu operation path đã chứa prefix đó. Hãy quyết định phần nào thuộc server base URL và phần nào thuộc path của API.

Nếu dùng OpenAPI bean để khai báo servers tĩnh, giá trị tĩnh có thể không phản ánh nhiều host hoặc nhiều môi trường. Khi đó cần cấu hình theo profile hoặc cơ chế tùy biến phù hợp; đừng kỳ vọng forwarded headers thay đổi một servers object đã được cố định theo cách riêng của ứng dụng.

## 17. Kiểm tra URL sau khi triển khai

Kiểm thử nên được thực hiện ở cả hai vị trí: gọi trực tiếp backend và gọi qua public proxy.

Ví dụ cấu hình:

- Context path: /shop
- OpenAPI path: /openapi
- Swagger UI path: /docs.html
- Proxy prefix public: /platform và proxy strip prefix trước khi forward

Các URL dự kiến:

| Vị trí | URL |
| --- | --- |
| Backend OpenAPI JSON | http://localhost:8080/shop/openapi |
| Backend Swagger UI | http://localhost:8080/shop/docs.html |
| Public OpenAPI JSON | https://api.example.com/platform/shop/openapi |
| Public Swagger UI | https://api.example.com/platform/shop/docs.html |

Gọi thử:

~~~bash
curl -i http://localhost:8080/shop/openapi
curl -i http://localhost:8080/shop/docs.html

curl -i https://api.example.com/platform/shop/openapi
curl -i https://api.example.com/platform/shop/docs.html
~~~

Nếu proxy strip /platform, backend nhận /shop/openapi; header X-Forwarded-Prefix: /platform giúp framework tái tạo URL public. Nếu proxy giữ nguyên /platform khi forward, phải thiết kế lại mapping và không cộng prefix lần nữa.

Kiểm tra Swagger UI trong browser:

1. Trang HTML mở được tại URL public.
2. Request tải swagger-config trả về 200.
3. URL OpenAPI JSON trong cấu hình là URL public, không phải hostname hoặc port backend.
4. OpenAPI JSON tải được từ browser.
5. Các tài nguyên JS/CSS/WebJar không bị 404.
6. Server URL trong document dùng https và host public đúng.
7. Try it out gửi request tới URL có đúng proxy/context prefix.
8. Không có prefix bị thiếu hoặc lặp.

## 18. Lỗi thường gặp và cách khoanh vùng

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| /swagger-ui.html trả 404 khi có context path | Quên thêm context path | Mở URL có /context-path/swagger-ui.html |
| Trang UI mở được nhưng spec 404 | UI config vẫn trỏ tới docs path cũ | Kiểm tra swagger-config và springdoc.api-docs.path |
| OpenAPI JSON có host backend | Chưa xử lý forwarded host/proto | Kiểm tra forwarded headers và strategy |
| OpenAPI server URL dùng http dù public là https | Proxy không truyền X-Forwarded-Proto hoặc ứng dụng không xử lý | Kiểm tra proxy và forwarded-header strategy |
| URL public thiếu prefix | Proxy strip prefix nhưng không gửi X-Forwarded-Prefix hoặc ứng dụng bỏ qua header | Kiểm tra header và cấu hình prefix support |
| URL có /platform/platform | Prefix đã được giữ trong request nhưng lại được cộng thêm từ forwarded header | Chọn một cách xử lý prefix nhất quán |
| UI mở được nhưng JS/CSS 404 | Base path hoặc proxy rewrite không nhất quán với WebJar path | Kiểm tra Network tab và các request tài nguyên |
| MVC controller 404 sau khi thêm servlet path | DispatcherServlet mapping và path matching không tương thích | Kiểm tra PathPatternParser và spring.mvc.servlet.path |
| Backend hoạt động nhưng proxy trả 502/404 | Proxy location, rewrite hoặc upstream mapping sai | Ghi lại path trước/sau proxy và kiểm tra access log |
| Swagger UI Try it out gọi localhost | Server URL hoặc OpenAPI config được sinh từ request nội bộ | Kiểm tra servers, forwarded host và customizer |
| Redirect đổi sang host lạ | Forwarded headers không được lọc tại trust boundary | Xóa header client gửi và chỉ tin proxy đáng tin cậy |

Khi debug, ghi lại ba URL riêng biệt: URL client gọi, URL proxy gửi tới backend và URL OpenAPI/Swagger UI tự sinh. Điều này giúp xác định prefix bị thêm hoặc bị mất ở lớp nào.

## 19. Checklist trước khi đổi path

- [ ] Xác định ứng dụng chạy Spring MVC hay Spring WebFlux.
- [ ] Xác định context path hoặc WebFlux base path có cần thiết không.
- [ ] Chỉ dùng servlet path khi thật sự cần map DispatcherServlet riêng.
- [ ] Kiểm tra giới hạn PathPatternParser nếu dùng spring.mvc.servlet.path.
- [ ] Đặt springdoc.api-docs.path cho OpenAPI JSON.
- [ ] Đặt springdoc.swagger-ui.path cho HTML UI.
- [ ] Kiểm tra URL swagger-config sau khi đổi docs path.
- [ ] Xác định proxy giữ hay strip public prefix.
- [ ] Cấu hình X-Forwarded-Prefix chỉ khi prefix đã bị strip.
- [ ] Chọn forwarded-header strategy đúng phiên bản Spring Boot.
- [ ] Cấu hình proxy xóa header forwarded không tin cậy.
- [ ] Kiểm tra servers trong OpenAPI dùng host, scheme và prefix public.
- [ ] Test UI, spec JSON/YAML và Try it out qua public proxy.
- [ ] Test cả URL backend để tách lỗi ứng dụng khỏi lỗi proxy.

## 20. Quy trình triển khai khuyến nghị

1. Chạy ứng dụng ở local với URL mặc định và xác nhận /v3/api-docs cùng /swagger-ui.html.
2. Thêm context path hoặc WebFlux base path nếu ứng dụng cần prefix nội bộ.
3. Đổi OpenAPI path và Swagger UI path bằng thuộc tính springdoc khi cần.
4. Kiểm tra lại JSON, YAML, swagger-config và tài nguyên UI ở local.
5. Cấu hình reverse proxy và xác định rõ prefix được giữ hay strip.
6. Truyền Forwarded hoặc X-Forwarded-* từ proxy đáng tin cậy.
7. Bật forwarded-header support phù hợp phiên bản Spring Boot và web stack.
8. Kiểm tra OpenAPI servers và các link trong Swagger UI từ public URL.
9. Chạy test qua proxy để xác nhận redirect, docs endpoint và Try it out.
10. Giữ kiểm soát trust boundary để client không thể giả forwarded headers.

Khi mỗi lớp chỉ chịu trách nhiệm cho phần prefix của nó, URL controller, OpenAPI document và Swagger UI sẽ nhất quán giữa local, staging và production. springdoc có thể sinh tài liệu chính xác sau proxy mà không cần hard-code mọi URL vào annotation hoặc mã controller.

## Tài liệu tham khảo

- [springdoc-openapi – FAQ: Deploy behind a reverse proxy](https://springdoc.org/faq.html)
- [springdoc-openapi – Getting Started and default/custom paths](https://springdoc.org/getting-started.html)
- [springdoc-openapi – Core Properties](https://springdoc.org/core-properties.html)
- [Spring Boot – Embedded Web Servers: Forwarded Headers and Prefix Support](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Boot – Servlet Web Applications and Path Matching](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot – Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Framework – ForwardedHeaderTransformer](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [RFC 7239 – Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)
