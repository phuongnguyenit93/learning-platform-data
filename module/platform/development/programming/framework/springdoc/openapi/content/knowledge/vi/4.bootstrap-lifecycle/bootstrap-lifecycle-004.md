# Mở Swagger UI và xác minh nguồn đặc tả đang được tải

Swagger UI là giao diện trình duyệt để xem và thử các operation được mô tả trong OpenAPI document. Khi mở trang Swagger UI, trình duyệt còn tải một file cấu hình, sau đó mới tải OpenAPI JSON/YAML theo URL được cấu hình. Vì vậy, nhìn thấy trang Swagger UI chưa đủ để khẳng định giao diện đang đọc đúng tài liệu của ứng dụng hiện tại.

Với springdoc-openapi trong Spring Boot, cần phân biệt ba URL:

1. **Swagger UI URL:** trang HTML/JavaScript mà người dùng mở, thường là **/swagger-ui.html**.
2. **Swagger configuration URL:** endpoint trả cấu hình cho Swagger UI, mặc định là **/v3/api-docs/swagger-config**.
3. **OpenAPI document URL:** endpoint trả đặc tả JSON/YAML, mặc định là **/v3/api-docs** hoặc **/v3/api-docs.yaml**.

Bài thực hành này hướng dẫn mở UI, lần theo request trong trình duyệt, xác minh URL nguồn, kiểm tra nội dung document và xử lý lỗi thường gặp khi đổi path, dùng nhiều group, triển khai dưới context path hoặc reverse proxy.

## 1. Hiểu luồng tải Swagger UI

Khi người dùng truy cập trang UI, luồng thông thường diễn ra như sau:

~~~text
Browser
   |
   | GET /swagger-ui.html
   v
Springdoc Swagger UI resource
   |
   | Load Swagger UI JavaScript/CSS
   |
   | GET /v3/api-docs/swagger-config
   v
Swagger UI configuration
   |
   | Reads url / urls / configUrl
   |
   | GET /v3/api-docs
   | or /v3/api-docs/{group}
   v
OpenAPI JSON/YAML
   |
   v
Render operations, schemas and responses
~~~

Trong cấu hình mặc định, swagger-config thường chỉ ra URL tài liệu **/v3/api-docs**. Nếu ứng dụng khai báo nhiều **GroupedOpenApi**, cấu hình có thể chứa danh sách **urls** để người dùng chọn document.

Mỗi request là một điểm kiểm tra riêng. Trang UI có thể tải thành công nhưng swagger-config trả 401/404; swagger-config có thể tải thành công nhưng URL document trả 404; document có thể tải được nhưng chứa operation của group hoặc một môi trường khác.

## 2. Các URL mặc định của Springdoc

Với Spring MVC hoặc WebFlux và starter Springdoc UI tương ứng, các URL phổ biến là:

| Mục đích | URL mặc định | Nội dung |
| --- | --- | --- |
| Trang Swagger UI | /swagger-ui.html | Entry point/redirect đến UI |
| Tài nguyên UI | /swagger-ui/index.html | Trang UI tĩnh |
| OpenAPI JSON | /v3/api-docs | Đặc tả ở định dạng JSON |
| OpenAPI YAML | /v3/api-docs.yaml | Đặc tả ở định dạng YAML |
| Swagger UI config | /v3/api-docs/swagger-config | URL document và các thiết lập UI |

URL có thể thay đổi theo server.servlet.context-path, WebFlux base path, cấu hình Springdoc hoặc reverse proxy. Bảng trên là đường dẫn trong ứng dụng khi không có prefix bổ sung.

Mở lần lượt các URL sau trong cùng môi trường:

~~~text
http://localhost:8080/swagger-ui.html
http://localhost:8080/v3/api-docs/swagger-config
http://localhost:8080/v3/api-docs
http://localhost:8080/v3/api-docs.yaml
~~~

Nếu dùng HTTPS, hostname hoặc port khác, thay base URL theo địa chỉ ứng dụng đang chạy. Không mặc định rằng URL local giống URL production.

## 3. Phân biệt URL giao diện và URL đặc tả

Hai property sau có mục đích khác nhau:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs
  api-docs:
    path: /openapi
~~~

Trong ví dụ:

- Swagger UI entry point là **/docs**.
- OpenAPI JSON là **/openapi**.
- OpenAPI YAML thường là **/openapi.yaml**.
- Swagger UI config mặc định được phục vụ dưới API docs path, ví dụ **/openapi/swagger-config**.

Đổi **springdoc.swagger-ui.path** chỉ đổi đường dẫn mở giao diện. Nó không tự đổi URL OpenAPI document. Đổi **springdoc.api-docs.path** mới đổi base path của document và swagger-config.

Sau khi đổi path, hãy mở URL mới và kiểm tra swagger-config đang trỏ tới document mới. Nếu UI vẫn cố tải **/v3/api-docs**, có thể một URL đã được override hoặc trình duyệt đang dùng cấu hình cũ.

## 4. Cấu hình entry point Swagger UI

Ví dụ dùng application.yml:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs
    enabled: true
  api-docs:
    enabled: true
~~~

Khi đó người dùng mở:

~~~text
http://localhost:8080/docs
~~~

Property **springdoc.swagger-ui.enabled** bật/tắt giao diện. **springdoc.api-docs.enabled** bật/tắt endpoint đặc tả. Hai property độc lập:

- Có thể bật OpenAPI JSON/YAML nhưng tắt Swagger UI để client hoặc pipeline lấy document.
- Có thể tắt cả hai khi môi trường không được phép công bố tài liệu.
- Nếu UI bật nhưng API docs tắt, UI không thể tải document trừ khi được cấu hình dùng nguồn đặc tả bên ngoài.

Không nên nhầm việc ẩn UI với bảo vệ API. Tắt Swagger UI không chặn controller endpoint; bảo vệ endpoint phải được cấu hình ở Spring Security hoặc gateway.

## 5. Mở trực tiếp swagger-config

Đây là bước quan trọng để xác định Swagger UI được yêu cầu tải document nào.

Mở:

~~~text
http://localhost:8080/v3/api-docs/swagger-config
~~~

Response thường là JSON có một số trường cấu hình, ví dụ:

~~~json
{
  "configUrl": "/v3/api-docs/swagger-config",
  "url": "/v3/api-docs",
  "validatorUrl": ""
}
~~~

Đây là ví dụ rút gọn để minh họa. Các trường thực tế có thể khác theo phiên bản Swagger UI, Springdoc và cấu hình ứng dụng.

Hãy tìm những trường sau:

| Trường | Vai trò |
| --- | --- |
| configUrl | URL mà UI dùng để lấy cấu hình |
| url | Một URL OpenAPI document đơn |
| urls | Danh sách document, thường dùng cho nhiều group |
| urls.primaryName | Tên document được chọn mặc định trong một số cấu hình |
| oauth2RedirectUrl | URL callback của Swagger UI OAuth2 |
| validatorUrl | Dịch vụ xác thực document nếu được cấu hình |

Điều cần xác minh là URL trong cấu hình có đúng base path, context path, group và môi trường không. Nếu cấu hình chứa **url: /v3/api-docs**, UI sẽ tải đường dẫn đó theo origin hiện tại của trang.

## 6. Xác minh request thật bằng Browser DevTools

Không chỉ đọc JSON cấu hình; hãy kiểm tra request mà trình duyệt thực sự gửi:

1. Mở Swagger UI.
2. Nhấn **F12** để mở Developer Tools.
3. Chọn tab **Network**.
4. Bật **Preserve log** nếu trang có redirect.
5. Tải lại trang bằng **Ctrl+R**.
6. Lọc theo **api-docs**, **swagger-config** hoặc **openapi**.
7. Chọn request swagger-config và xem Request URL, Status Code, Response.
8. Tìm request document như /v3/api-docs, chọn nó và xem Response.
9. Kiểm tra Initiator để biết request được khởi tạo từ UI/config nào.

Các cột cần chú ý:

| Thuộc tính | Cần xác nhận |
| --- | --- |
| Request URL | Đúng hostname, port, context path và group |
| Status Code | 200 khi tải thành công |
| Content-Type | JSON/YAML phù hợp với request |
| Response | Có openapi, info, paths, components |
| Initiator | Request được tạo từ Swagger UI/config dự kiến |
| Redirect | Không bị chuyển sang trang login hoặc URL môi trường khác |

Nếu thấy UI hiển thị nội dung cũ, bật **Disable cache** trong Network khi DevTools đang mở rồi tải lại. Chỉ dùng bước này để loại trừ cache trình duyệt; nếu response từ server vẫn cũ, kiểm tra cache/proxy/CDN phía trước ứng dụng.

## 7. Kiểm tra OpenAPI JSON bằng trình duyệt hoặc curl

Mở trực tiếp document:

~~~text
http://localhost:8080/v3/api-docs
~~~

Một document hợp lệ thường có các thành phần cấp cao:

~~~json
{
  "openapi": "3.0.1",
  "info": {
    "title": "Book API",
    "version": "v1"
  },
  "paths": {},
  "components": {}
}
~~~

Giá trị openapi trong ví dụ chỉ minh họa; phiên bản thực tế phụ thuộc cấu hình Springdoc. Không nhầm info.version (phiên bản API do ứng dụng mô tả) với version của thư viện Springdoc hoặc Spring Boot.

Trên terminal có curl:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs/swagger-config
curl -i http://localhost:8080/v3/api-docs.yaml
~~~

**-i** giúp xem HTTP status và response headers. Khi cần lưu nội dung để diff:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
curl -fsS http://localhost:8080/v3/api-docs/swagger-config -o swagger-config.json
~~~

Các lệnh trên ghi file vào thư mục terminal hiện tại. Hãy chọn thư mục làm việc phù hợp và tránh commit document chứa thông tin nội bộ nếu repository không có chủ đích lưu chúng.

## 8. Kiểm tra document có đúng ứng dụng và đúng phiên bản không

Khi document tải thành công, xác minh nội dung:

- info.title có đúng tên API/service.
- info.version có đúng version hợp đồng mà nhóm công bố.
- servers có base URL đúng môi trường nếu được khai báo.
- paths có endpoint vừa triển khai.
- components.schemas có DTO mong đợi.
- components.securitySchemes có cơ chế xác thực dự kiến.
- Response và request body có đúng schema.
- Không xuất hiện endpoint nội bộ không thuộc audience của document.

Ví dụ kiểm tra bằng mắt:

~~~json
{
  "paths": {
    "/api/books": {
      "get": {
        "summary": "Tìm kiếm sách"
      }
    }
  }
}
~~~

Nếu Swagger UI hiển thị đúng tiêu đề nhưng thiếu endpoint mới, có thể UI đang tải một group hoặc một file OpenAPI khác. Hãy đối chiếu swagger-config.url/urls và request document trong Network trước khi sửa controller.

## 9. Cấu hình nguồn document bằng springdoc.swagger-ui.url

Ứng dụng có thể yêu cầu Swagger UI tải một OpenAPI document cụ thể:

~~~yaml
springdoc:
  swagger-ui:
    url: /v3/api-docs
~~~

Property **url** hữu ích khi cần chỉ định nguồn tài liệu đơn, ví dụ một path tùy chỉnh hoặc document được cung cấp bởi ứng dụng. URL tương đối thường được phân giải theo origin/base URL của trang UI; URL tuyệt đối có thể trỏ sang host khác.

Nếu **url** được cấu hình, hãy xác minh giá trị đó trong swagger-config và Network. Đừng giả định đổi springdoc.api-docs.path sẽ tự cập nhật mọi URL được hard-code trong cấu hình UI.

Không dùng URL trỏ tới môi trường development trong cấu hình production. Một URL tuyệt đối sai có thể khiến UI tải document từ host khác dù ứng dụng hiện tại trả OpenAPI JSON đúng.

## 10. Chọn một document trong nhiều OpenAPI group

Khi ứng dụng có nhiều GroupedOpenApi, mỗi group có document riêng. Ví dụ:

~~~java
@Configuration
public class OpenApiGroups {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner")
            .pathsToMatch("/api/partner/**")
            .build();
    }
}
~~~

Các document thường có URL:

~~~text
/v3/api-docs/public
/v3/api-docs/partner
~~~

Có thể mở trực tiếp từng URL để kiểm tra group:

~~~text
http://localhost:8080/v3/api-docs/public
http://localhost:8080/v3/api-docs/partner
~~~

Nếu document group trả 404, kiểm tra tên group đúng với **group("...")**, ứng dụng đã khởi động với bean đó và request path có đúng api-docs base path không.

## 11. Hiển thị danh sách group trong Swagger UI

Có thể cấu hình nhiều document trong application.yml:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Partner API
        url: /v3/api-docs/partner
    urls-primary-name: Public API
~~~

Swagger UI sẽ hiển thị danh sách để chọn Public API hoặc Partner API. **urls-primary-name** chọn document mặc định theo tên trong danh sách; hãy xác minh tên trong response swagger-config vì cách biểu diễn có thể khác theo phiên bản.

Mỗi group cần có URL riêng và trả đúng document. Chỉ khai báo tên trong UI không tạo group ở Springdoc; group phải được đăng ký bằng GroupedOpenApi hoặc cơ chế cấu hình tương ứng.

## 12. Phân biệt url, urls và configUrl

Ba trường dễ bị nhầm:

| Trường | Dùng khi nào |
| --- | --- |
| url | UI tải một document |
| urls | UI cho phép chọn trong nhiều document |
| configUrl | UI tải file cấu hình Swagger UI |

Nếu cấu hình **urls**, hãy xác minh từng URL trong danh sách đều truy cập được. Nếu **configUrl** trỏ sai, UI có thể không tải được các thiết lập dù OpenAPI document vẫn tồn tại.

Khi điều tra lỗi, mở trực tiếp config URL trước. Sau đó lấy đúng url hoặc từng phần tử urls từ response và mở từng document. Cách này xác định chính xác lỗi nằm ở config hay document.

## 13. Đổi API docs path

Ví dụ đổi OpenAPI endpoint:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
~~~

Sau khi khởi động lại ứng dụng, kiểm tra:

~~~text
GET /openapi
GET /openapi.yaml
GET /openapi/swagger-config
~~~

Nếu Swagger UI dùng URL mặc định cũ, hãy kiểm tra response cấu hình và cập nhật nguồn document nếu cần:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs
    url: /openapi
~~~

Đây là ví dụ dùng một document đơn. Nếu ứng dụng dùng **urls** cho nhiều group, cấu hình danh sách phải trỏ tới các URL group dưới API docs path mới.

## 14. Triển khai dưới context path

Spring Boot MVC có thể chạy dưới context path:

~~~yaml
server:
  servlet:
    context-path: /catalog
~~~

Trong trường hợp này, URL public thường có prefix /catalog:

~~~text
/catalog/swagger-ui.html
/catalog/v3/api-docs/swagger-config
/catalog/v3/api-docs
~~~

Nếu đặt springdoc.api-docs.path: /openapi, URL tương ứng sẽ nằm dưới context path:

~~~text
/catalog/openapi
~~~

Đừng thêm context path hai lần. Cần phân biệt path cấu hình bên trong ứng dụng với URL public mà browser nhìn thấy.

Với Spring WebFlux, base path thường được cấu hình qua **spring.webflux.base-path**. Cách triển khai và servlet-specific property khác nhau; hãy xác minh đúng web stack của ứng dụng.

## 15. Reverse proxy và forwarded headers

Trong production, ứng dụng có thể chạy ở http://service:8080, nhưng client truy cập qua https://api.example.com/catalog. Reverse proxy có thể thêm prefix, kết thúc TLS và chuyển tiếp request đến app.

Nếu ứng dụng không xử lý forwarded headers đúng, swagger-config hoặc OpenAPI servers có thể chứa:

- http thay vì https.
- Host nội bộ như service:8080.
- Thiếu prefix /catalog.
- URL tuyệt đối trỏ sai host hoặc port.

Spring Boot có property điều khiển forwarded headers strategy:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Giá trị phù hợp phụ thuộc reverse proxy, container và cách header được chuyển tiếp. Proxy cần thiết lập các header như Forwarded hoặc X-Forwarded-Proto, X-Forwarded-Host, X-Forwarded-Port, X-Forwarded-Prefix theo cấu hình đã thống nhất.

Chỉ tin forwarded headers từ proxy đáng tin cậy. Nếu ứng dụng nhận trực tiếp request từ internet và chấp nhận header do client tự gửi, host/scheme được suy ra có thể bị giả mạo. Cấu hình proxy phải loại bỏ header không tin cậy trước khi ghi header chính thức.

Sau khi thay đổi, kiểm tra cả:

1. swagger-config mà browser tải.
2. servers trong OpenAPI document.
3. Request URL của document trong Network.
4. URL thực tế mà Swagger UI dùng khi bấm Try it out.

## 16. Kiểm tra Try it out đang gửi request đến đâu

Swagger UI có thể tải document đúng nhưng gửi request thử đến base URL sai. Điều này thường liên quan đến **servers** trong OpenAPI.

Ví dụ document:

~~~yaml
servers:
  - url: https://api.example.com/catalog
paths:
  /api/books:
    get:
      summary: Tìm sách
~~~

Try it out sẽ kết hợp server URL và path để tạo request. Nếu servers là http://localhost:8080, người dùng production có thể vô tình gọi localhost trên máy của họ.

Hãy kiểm tra:

- servers[0].url trong OpenAPI JSON.
- Request URL khi bấm Execute.
- Scheme, host, port và prefix.
- Proxy/gateway có route path đó tới service đúng không.

Nếu server URL phụ thuộc môi trường, có thể cấu hình qua @OpenAPIDefinition(servers = ...), bean OpenAPI hoặc cơ chế sinh URL phù hợp. Tránh hard-code URL production trong source dùng chung cho mọi môi trường.

## 17. Phân biệt document do ứng dụng sinh và document tĩnh

Swagger UI không bắt buộc phải tải document do Springdoc sinh tại /v3/api-docs. UI cũng có thể tải một file OpenAPI tĩnh hoặc URL từ hệ thống khác.

Ví dụ cấu hình UI tải file tĩnh:

~~~yaml
springdoc:
  swagger-ui:
    url: /specs/public-api.yaml
~~~

Khi đó:

- /v3/api-docs vẫn có thể tồn tại nhưng không phải nguồn UI đang dùng.
- swagger-config.url có thể trỏ /specs/public-api.yaml.
- Nội dung UI hiển thị phụ thuộc file tĩnh và cache/hosting của file đó.

Đây là nguyên nhân phổ biến khiến sửa controller nhưng Swagger UI không thay đổi: UI đang đọc một file OpenAPI khác. Hãy xác định request document thực tế trước khi sửa code.

## 18. Kiểm tra HTTP status và Content-Type

Một document JSON tải đúng thường trả status 200 và Content-Type tương ứng với JSON, thường là application/json. YAML có thể trả application/vnd.oai.openapi hoặc content type phù hợp do phiên bản/framework cấu hình.

Không kết luận lỗi chỉ dựa trên một Content-Type duy nhất. Hãy kiểm tra status, body và khả năng parser của Swagger UI.

| Status | Ý nghĩa cần điều tra |
| --- | --- |
| 200 | Request thành công; kiểm tra body có phải document đúng không |
| 301/302/307/308 | Có redirect; xác minh đích có phải login/proxy/path mới |
| 401 | Cần xác thực hoặc credential không hợp lệ |
| 403 | Đã đến server nhưng bị policy từ chối |
| 404 | Sai path, group, context path hoặc endpoint bị disable |
| 406 | Content negotiation không phù hợp |
| 500 | Lỗi tạo document, converter, bean hoặc customizer |

Nếu swagger-config trả 200 nhưng document trả 401/403, UI có thể hiện lỗi tải đặc tả. Cần quyết định docs có public hay protected và cấu hình authentication cho cả config URL lẫn document URL nhất quán.

## 19. Khi Swagger UI hiển thị trang nhưng không có operation

Kiểm tra theo thứ tự:

1. Network có request đến swagger-config không?
2. swagger-config có url hoặc urls hợp lệ không?
3. Request document có status 200 không?
4. Response có openapi và paths không?
5. paths có operation mong đợi không?
6. UI có đang chọn đúng group không?
7. Console có báo lỗi parse JSON/YAML, CORS hoặc resolve $ref không?

Nếu document có paths: {} hoặc không có endpoint, kiểm tra Springdoc scanning, group path filters, controller mapping và springdoc.packages-to-scan/paths-to-match nếu đã cấu hình.

Nếu document có operation nhưng UI không render, kiểm tra document có hợp lệ, version OpenAPI có được Swagger UI đang dùng hỗ trợ và mọi $ref đều resolve được.

## 20. Khi swagger-config trả 404

Các nguyên nhân thường gặp:

- springdoc.api-docs.enabled=false.
- springdoc.api-docs.path đã đổi nhưng UI/config URL vẫn dùng path cũ.
- Request thiếu context path hoặc proxy prefix.
- Security/gateway rewrite URL sai.
- Ứng dụng đang dùng starter không có OpenAPI endpoint mong muốn.
- Phiên bản Springdoc không tương thích với Spring Boot/Web stack.

Kiểm tra endpoint bằng curl:

~~~bash
curl -i http://localhost:8080/v3/api-docs/swagger-config
~~~

Nếu URL này 404, mở trực tiếp /v3/api-docs. Nếu cả hai đều 404, xem property springdoc.api-docs.path, springdoc.api-docs.enabled, dependency starter và startup log. Nếu /v3/api-docs hoạt động nhưng swagger-config không có, kiểm tra path và cấu hình UI.

## 21. Khi document trả 401 hoặc 403

Nếu Spring Security bảo vệ docs, cần cho phép hoặc yêu cầu credential đúng cho các URL:

- Swagger UI entry point và static assets.
- Swagger config endpoint.
- OpenAPI JSON/YAML endpoint.
- Các URL group nếu dùng nhiều document.

Ví dụ matcher cho tài liệu public:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        "/swagger-ui.html",
        "/swagger-ui/**",
        "/v3/api-docs/**"
    ).permitAll()
    .anyRequest().authenticated()
);
~~~

Nếu tài liệu nội bộ, thay permitAll() bằng role/scope phù hợp và bảo đảm người dùng có thể lấy cả config lẫn document. Chỉ cho phép trang UI nhưng chặn swagger-config hoặc OpenAPI JSON thì giao diện vẫn không thể hiển thị API.

Nếu docs nằm sau gateway, kiểm tra gateway có áp dụng cùng policy cho mọi endpoint tài liệu không. Đừng mở business API chỉ để Swagger UI tải được.

## 22. Khi UI vẫn tải document cũ

Có nhiều lớp cache:

- Browser cache.
- Service worker nếu ứng dụng có PWA.
- Reverse proxy hoặc CDN.
- Cache của hệ thống static hosting.
- File OpenAPI tĩnh được build vào artifact.
- Một URL group khác với URL bạn đang kiểm tra.

Quy trình:

1. Bật Disable cache trong Network và reload.
2. Mở URL document trực tiếp ở tab mới.
3. So sánh response headers như ETag, Last-Modified, Cache-Control.
4. Gọi document bằng curl để loại trừ cache UI.
5. Xác minh host và path document trong swagger-config.
6. Kiểm tra file tĩnh/build artifact nếu UI dùng URL ngoài Springdoc.

Nếu curl cũng trả document cũ, vấn đề nằm ở server, proxy, CDN hoặc artifact được deploy; xóa cache trình duyệt sẽ không giải quyết được.

## 23. Cấu hình Swagger UI tắt URL Petstore mặc định

Một số cấu hình Swagger UI có thể sử dụng URL mẫu Petstore khi không có document URL mong muốn. Có thể chủ động tắt default URL:

~~~yaml
springdoc:
  swagger-ui:
    disable-swagger-default-url: true
    url: /v3/api-docs
~~~

Sau đó kiểm tra swagger-config phải trỏ đến document của ứng dụng. Nếu dùng nhiều group, khai báo urls thay cho url và xác nhận danh sách group.

Không chỉ nhìn giao diện để kết luận nguồn. Luôn kiểm tra request document trong Network vì UI có thể hiển thị một nguồn cấu hình cũ hoặc URL mẫu.

## 24. Kiểm tra bằng integration test

Có thể dùng MockMvc để xác minh API docs và swagger-config được phục vụ:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SwaggerUiBootstrapTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void servesOpenApiDocument() throws Exception {
        String body = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode document = objectMapper.readTree(body);
        assertThat(document.path("openapi").asText()).startsWith("3.");
        assertThat(document.path("paths").isObject()).isTrue();
    }

    @Test
    void servesSwaggerUiConfiguration() throws Exception {
        String body = mockMvc.perform(get("/v3/api-docs/swagger-config"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode config = objectMapper.readTree(body);
        assertThat(
            config.path("url").asText().contains("/v3/api-docs")
            || config.path("urls").isArray()
        ).isTrue();
    }
}
~~~

Đây là ví dụ cho cấu hình mặc định với một document. Nếu dự án đổi api-docs.path, dùng group hoặc cấu hình URL tĩnh, hãy thay assertion theo hợp đồng thực tế. Test không nên khóa vào một URL mặc định khi ứng dụng chủ ý cấu hình URL khác.

## 25. Kiểm tra group trong integration test

Với group public, test trực tiếp URL group:

~~~java
@Test
void servesPublicGroupDocument() throws Exception {
    String body = mockMvc.perform(get("/v3/api-docs/public"))
        .andExpect(status().isOk())
        .andReturn()
        .getResponse()
        .getContentAsString();

    JsonNode document = objectMapper.readTree(body);
    assertThat(document.path("paths").has("/api/public/books")).isTrue();
    assertThat(document.path("paths").has("/api/internal/jobs")).isFalse();
}
~~~

Test trên kiểm tra nội dung group, không kiểm tra quyền đọc document. Nếu group internal cần bảo vệ, thêm test security riêng cho URL /v3/api-docs/internal.

## 26. Checklist xác minh nguồn đặc tả

- [ ] Đã mở đúng Swagger UI entry point.
- [ ] Đã phân biệt UI URL với API docs URL.
- [ ] swagger-config tải thành công.
- [ ] Đã đọc url hoặc urls trong swagger-config.
- [ ] URL document trỏ đúng host, port, context path và group.
- [ ] Request document trong Network trả 200.
- [ ] Content-Type và body phù hợp JSON/YAML.
- [ ] info.title và info.version đúng API.
- [ ] paths có endpoint dự kiến.
- [ ] components.schemas và security schemes đúng.
- [ ] servers dùng base URL đúng môi trường.
- [ ] Try it out gửi request đến host/path đúng.
- [ ] Không còn URL Petstore hoặc URL development ngoài ý muốn.
- [ ] Đã kiểm tra context path/reverse proxy nếu deploy sau gateway.
- [ ] Đã xác định cache browser/proxy/CDN khi document cũ.
- [ ] Có integration test cho document/config/group quan trọng.

## 27. Quy trình xử lý sự cố nhanh

Khi người dùng báo Swagger UI trống hoặc hiển thị sai API, thực hiện:

1. Mở trang Swagger UI và ghi nhận URL đầy đủ.
2. Mở swagger-config theo API docs path hiện tại.
3. Đọc url hoặc từng phần tử urls.
4. Mở trực tiếp document được chỉ định.
5. Xác minh info, paths, components và servers.
6. Dùng Network kiểm tra status, redirect, content type và response body.
7. Nếu sai path, kiểm tra springdoc.swagger-ui.path, springdoc.api-docs.path, context path và proxy prefix.
8. Nếu sai document, kiểm tra url, urls, GroupedOpenApi và file tĩnh.
9. Nếu bị từ chối, kiểm tra security cho cả UI/config/document.
10. Nếu nội dung cũ, loại trừ browser cache rồi kiểm tra proxy/CDN/artifact.
11. Viết integration test cho URL và group sau khi sửa.

## Kết luận

Mở được Swagger UI chỉ xác nhận trình duyệt tải được giao diện. Để biết giao diện đang hiển thị đúng API, cần lần theo swagger-config, đọc URL trong url/urls, rồi kiểm tra response OpenAPI JSON/YAML mà trình duyệt thực sự tải. URL giao diện, URL cấu hình và URL document là ba thành phần riêng; context path, group, reverse proxy và cache có thể làm chúng lệch nhau.

Hãy kiểm tra theo thứ tự UI → swagger-config → OpenAPI document → servers/Try it out. Khi có đủ bằng chứng từ Network hoặc curl, bạn sẽ xác định được lỗi nằm ở giao diện, cấu hình nguồn, endpoint tài liệu, routing hay cache mà không cần đoán từ ảnh chụp Swagger UI.

## Tài liệu tham khảo

- [Springdoc OpenAPI — Documentation](https://springdoc.org/)
- [Springdoc OpenAPI — Properties and Swagger UI configuration](https://springdoc.org/properties.html)
- [Springdoc OpenAPI v2 — Properties](https://springdoc.org/v2/)
- [Swagger UI — Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
