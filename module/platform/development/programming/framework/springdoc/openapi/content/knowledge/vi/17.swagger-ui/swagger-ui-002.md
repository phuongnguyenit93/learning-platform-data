# Đường dẫn giao diện, tài nguyên tĩnh và swagger-config

Swagger UI trong một ứng dụng Spring Boot không chỉ là một trang HTML đơn lẻ. Springdoc phục vụ một entry point để mở giao diện, các tài nguyên tĩnh như JavaScript/CSS, một endpoint cấu hình cho Swagger UI và một hoặc nhiều OpenAPI document. Các thành phần này có URL và nhiệm vụ riêng.

Khi cần đổi đường dẫn Swagger UI, thay logo/style, chuyển API docs sang path riêng, cấu hình OAuth redirect hoặc xử lý lỗi tải giao diện, cần xác định đúng thành phần đang được thay đổi. Đổi URL HTML không tự di chuyển file JavaScript/CSS; đổi URL OpenAPI không tự đổi config URL; thay file tĩnh cũng không sửa nội dung OpenAPI.

Bài học tập trung vào cách Springdoc kết nối các phần đó, cách cấu hình trong application.yml, cách tùy biến tài nguyên giao diện và cách kiểm tra route thật trong Spring MVC/WebFlux.

## 1. Bốn thành phần tạo nên Swagger UI

Trong cấu hình thông thường, có bốn nhóm tài nguyên:

| Thành phần | Ví dụ URL mặc định | Vai trò |
| --- | --- | --- |
| Entry point HTML | /swagger-ui.html | URL người dùng mở để vào giao diện |
| Static resources | /swagger-ui/** | JavaScript, CSS, favicon, index và các file giao diện |
| Swagger UI configuration | /v3/api-docs/swagger-config | Cung cấp URL document và cấu hình UI |
| OpenAPI document | /v3/api-docs, /v3/api-docs.yaml | Đặc tả API JSON/YAML mà UI hiển thị |

Luồng hoạt động:

~~~text
Browser
   |
   | GET /swagger-ui.html
   v
Springdoc welcome endpoint
   |
   | redirect/forward to Swagger UI index
   v
/swagger-ui/index.html
   |
   | GET /swagger-ui/swagger-ui.css
   | GET /swagger-ui/swagger-ui-bundle.js
   | GET /swagger-ui/swagger-initializer.js
   v
Swagger UI assets
   |
   | GET /v3/api-docs/swagger-config
   v
Swagger UI configuration
   |
   | GET /v3/api-docs or /v3/api-docs/{group}
   v
OpenAPI document
   |
   v
Render API operations and schemas
~~~

Đây là sơ đồ logic. Đường dẫn asset cụ thể và cách redirect/forward có thể khác theo phiên bản Swagger UI, Springdoc, context path và cấu hình triển khai. Khi cần xác minh, dùng Network tab để xem request thực tế.

## 2. Dependency nào cung cấp Swagger UI?

Với Spring Boot 3 và Spring MVC, starter thông dụng là:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Với Spring WebFlux, chọn starter tương ứng:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Ví dụ dùng Springdoc 2.10.0 cho nhánh Spring Boot 3 tương thích. Hãy chọn phiên bản theo compatibility matrix của dự án, không sao chép version này sang mọi nhánh Boot.

Starter UI đóng gói tích hợp Swagger UI chính thức và tự đăng ký tài nguyên cùng endpoint cần thiết. Thông thường không cần tự thêm swagger-ui-dist hoặc tự copy JavaScript/CSS vào project.

Nếu chỉ cần OpenAPI JSON/YAML mà không cần giao diện, dùng starter API-only phù hợp. Không nên thêm starter UI chỉ để tạo document nếu ứng dụng không cần phục vụ Swagger UI.

## 3. Đường dẫn mặc định

Với ứng dụng không có context path hoặc prefix proxy:

| Tài nguyên | URL |
| --- | --- |
| Swagger UI entry point | /swagger-ui.html |
| Swagger UI index | /swagger-ui/index.html |
| OpenAPI JSON | /v3/api-docs |
| OpenAPI YAML | /v3/api-docs.yaml |
| Swagger UI config | /v3/api-docs/swagger-config |

Ví dụ ứng dụng chạy tại localhost:8080:

~~~text
http://localhost:8080/swagger-ui.html
http://localhost:8080/swagger-ui/index.html
http://localhost:8080/v3/api-docs/swagger-config
http://localhost:8080/v3/api-docs
http://localhost:8080/v3/api-docs.yaml
~~~

Hai URL HTML đầu có thể đi qua redirect hoặc welcome handler tùy phiên bản. URL đầu là entry point thân thiện được Springdoc công bố; URL thứ hai giúp kiểm tra trực tiếp tài nguyên index.

## 4. Đổi đường dẫn HTML bằng springdoc.swagger-ui.path

Property springdoc.swagger-ui.path dùng để thay đổi URL entry point của giao diện:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs/api.html
~~~

Người dùng mở:

~~~text
http://localhost:8080/docs/api.html
~~~

Property này điều chỉnh endpoint HTML/welcome. Nó không đổi API docs path và cũng không có nghĩa toàn bộ tài nguyên JavaScript/CSS được chuyển sang thư mục /docs.

Các asset vẫn được phục vụ bởi resource handler của Swagger UI. Vì vậy, khi cấu hình custom path, hãy kiểm tra cả entry point lẫn request asset trong Network.

## 5. Đổi API docs path độc lập với UI path

OpenAPI document có property riêng:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs/api.html
~~~

Trong cấu hình này:

- Giao diện mở tại /docs/api.html.
- OpenAPI JSON được phục vụ tại /openapi.
- OpenAPI YAML thường được phục vụ tại /openapi.yaml.
- Swagger UI config được phục vụ dưới API docs base path, ví dụ /openapi/swagger-config.

Không dùng springdoc.swagger-ui.path để đổi URL JSON. Cũng không dùng springdoc.api-docs.path để đổi URL HTML.

Sau khi thay path, mở trực tiếp document và config endpoint để xác nhận chúng thực sự hoạt động. Nếu UI không tải được document, kiểm tra cấu hình nguồn trong swagger-config trước khi đổi thêm property.

## 6. Cấu hình đầy đủ trong application.yml

Ví dụ cấu hình một document:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /openapi
  swagger-ui:
    enabled: true
    path: /docs/api.html
    url: /openapi
    disable-swagger-default-url: true
    try-it-out-enabled: true
    display-request-duration: true
    deep-linking: true
~~~

Ý nghĩa:

- api-docs.enabled bật endpoint OpenAPI.
- api-docs.path đổi base path của JSON/YAML và config endpoint.
- swagger-ui.enabled bật giao diện.
- swagger-ui.path đổi entry point HTML.
- swagger-ui.url chỉ định một document để UI tải.
- disable-swagger-default-url tắt URL Petstore mẫu.
- try-it-out-enabled bật Try it out mặc định.
- display-request-duration hiển thị thời gian request thử.
- deep-linking bật liên kết trực tiếp tới tag/operation.

Property dùng trong YAML theo relaxed binding của Spring Boot. Tên trong bảng tài liệu có thể viết theo camelCase; trong application.yml nên dùng kebab-case nhất quán.

## 7. Bảng các property quan trọng

| Property | Mặc định | Mục đích |
| --- | --- | --- |
| springdoc.swagger-ui.path | /swagger-ui.html | Entry point HTML |
| springdoc.swagger-ui.enabled | true | Bật/tắt Swagger UI |
| springdoc.swagger-ui.config-url | /v3/api-docs/swagger-config | URL lấy cấu hình UI |
| springdoc.swagger-ui.url | Không đặt | Một OpenAPI document tùy chỉnh |
| springdoc.swagger-ui.urls | Không đặt | Danh sách nhiều document/group |
| springdoc.swagger-ui.urls-primary-name | Không đặt | Document mặc định trong danh sách |
| springdoc.swagger-ui.oauth2-redirect-url | /swagger-ui/oauth2-redirect.html | Callback OAuth2 |
| springdoc.swagger-ui.disable-swagger-default-url | false | Tắt URL Petstore mẫu |
| springdoc.api-docs.path | /v3/api-docs | Base path của OpenAPI document |
| springdoc.api-docs.enabled | true | Bật/tắt API docs endpoint |

Đây là các property phục vụ cấu hình URL và hành vi tải giao diện. Swagger UI còn có nhiều property khác cho layout, filter, sort, expansion, OAuth và CSRF; chỉ cấu hình những mục cần thiết để tránh tạo ra hành vi khó dự đoán.

## 8. swagger-config là gì?

Swagger UI cần biết document nào sẽ được tải và các tùy chọn nào cần áp dụng. Springdoc cung cấp endpoint cấu hình, mặc định:

~~~text
/v3/api-docs/swagger-config
~~~

Endpoint này trả JSON cấu hình. Ví dụ rút gọn:

~~~json
{
  "configUrl": "/v3/api-docs/swagger-config",
  "url": "/v3/api-docs",
  "validatorUrl": ""
}
~~~

Response thực tế có thể có thêm các trường về OAuth, URLs, layout, filtering, deep linking hoặc các property khác. Không nên dựa vào ví dụ rút gọn để giả định toàn bộ JSON cấu hình.

swagger-config không phải OpenAPI document. Nó là cấu hình cho UI. OpenAPI document mới chứa info, paths, components, security schemes và các schema API.

## 9. Phân biệt config-url, url và urls

Ba property có vai trò khác nhau:

| Property | Câu hỏi được trả lời |
| --- | --- |
| config-url | Swagger UI lấy file cấu hình ở đâu? |
| url | Swagger UI tải một OpenAPI document nào? |
| urls | Swagger UI cho chọn giữa những document nào? |

Ví dụ:

~~~yaml
springdoc:
  swagger-ui:
    config-url: /v3/api-docs/swagger-config
    url: /v3/api-docs
~~~

Nếu config-url trỏ đến file cấu hình ngoài, file đó phải tồn tại và trả về JSON cấu hình hợp lệ cho Swagger UI. Springdoc không tự tạo một file tùy ý ở server khác.

Property url dùng cho một document. Nếu urls được khai báo, danh sách urls được ưu tiên và url đơn sẽ bị bỏ qua theo cấu hình Swagger UI của Springdoc.

## 10. Dùng document OpenAPI tĩnh thay cho document sinh động

Swagger UI có thể tải một file OpenAPI tĩnh đặt trong static resources của Spring Boot:

~~~text
src/
  main/
    resources/
      static/
        specs/
          public-api.yaml
~~~

Cấu hình:

~~~yaml
springdoc:
  swagger-ui:
    url: /specs/public-api.yaml
    disable-swagger-default-url: true
~~~

Khi đó UI đọc file tĩnh public-api.yaml. Endpoint /v3/api-docs có thể vẫn tồn tại, nhưng không nhất thiết là nguồn mà UI đang sử dụng.

Trường hợp này hữu ích khi:

- Document được build từ pipeline khác.
- API contract được quản lý độc lập với ứng dụng runtime.
- Muốn hiển thị tài liệu của một service khác.
- Muốn phát hành một snapshot OpenAPI đã được duyệt.

Nhược điểm là file tĩnh không tự cập nhật khi controller thay đổi. Pipeline phải có trách nhiệm tạo, kiểm tra và thay thế file đúng phiên bản.

## 11. Tải nhiều document bằng urls

Khi ứng dụng có nhiều API group, cấu hình danh sách:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Partner API
        url: /v3/api-docs/partner
      - name: Admin API
        url: /v3/api-docs/admin
    urls-primary-name: Public API
~~~

Swagger UI sẽ hiển thị danh sách lựa chọn trên thanh Topbar. Tên và URL trong danh sách phải duy nhất vì Swagger UI sử dụng chúng làm định danh.

Các URL này phải được Springdoc tạo ra hoặc phải trỏ tới các document tĩnh đang tồn tại. Chỉ thêm một phần tử vào urls không tự tạo OpenAPI group.

## 12. Đăng ký group ở Springdoc

Ví dụ khai báo group bằng Java:

~~~java
@Configuration
public class OpenApiGroupConfiguration {

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

Các document tương ứng thường có đường dẫn:

~~~text
/v3/api-docs/public
/v3/api-docs/partner
~~~

Tên group trong URL phải khớp với group đã khai báo. Nếu UI hiển thị tên Public API nhưng URL trỏ /v3/api-docs/public-v2 trong khi bean tên public, document có thể trả 404.

## 13. Khai báo group bằng application.yml

Có thể dùng group-configs:

~~~yaml
springdoc:
  group-configs:
    - group: public
      display-name: Public API
      paths-to-match:
        - /api/public/**
    - group: partner
      display-name: Partner API
      paths-to-match:
        - /api/partner/**
~~~

Khi đó các URL group được tạo theo tên:

~~~text
/v3/api-docs/public
/v3/api-docs/partner
~~~

Không khai báo cùng một group bằng cả bean Java và group-configs nếu không có chủ đích rõ ràng. Tránh trùng tên group hoặc các bộ lọc path chồng lấn gây document khó hiểu.

## 14. OAuth2 redirect resource

Swagger UI sử dụng một trang callback để hoàn tất OAuth2 authorization flow. Property tương ứng:

~~~yaml
springdoc:
  swagger-ui:
    oauth2-redirect-url: https://api.example.com/swagger-ui/oauth2-redirect.html
~~~

Giá trị mặc định thường là /swagger-ui/oauth2-redirect.html. Nếu UI được phục vụ dưới context path hoặc reverse proxy prefix, callback URL phải phản ánh URL mà browser truy cập được.

Khi OAuth2 redirect lỗi, kiểm tra:

- URL callback trong cấu hình UI.
- Redirect URI đã đăng ký tại Identity Provider.
- Scheme HTTPS/HTTP.
- Host, port và context path.
- Proxy prefix.
- CSP hoặc policy của browser có chặn callback không.

Không nhúng client secret vào cấu hình Swagger UI chạy trên browser production. Client secret được gửi xuống trình duyệt không còn là bí mật.

## 15. Tài nguyên tĩnh nằm ở đâu trong ứng dụng?

Springdoc sử dụng Swagger UI WebJar. Các tài nguyên gốc được đóng gói trong classpath theo cấu trúc:

~~~text
META-INF/
  resources/
    webjars/
      swagger-ui/
        {swagger.version}/
          index.html
          swagger-ui-bundle.js
          swagger-ui.css
          swagger-ui-standalone-preset.js
          favicon-32x32.png
          ...
~~~

Đây là vị trí tài nguyên bên trong dependency, không phải thư mục source mà ứng dụng cần tự tạo. Springdoc/Spring resource handling phục vụ chúng qua các URL web tương ứng.

Các tài nguyên thường gặp:

| File | Vai trò |
| --- | --- |
| index.html | Trang khởi tạo Swagger UI |
| swagger-ui-bundle.js | JavaScript bundle chính |
| swagger-ui-standalone-preset.js | Preset giao diện standalone |
| swagger-ui.css | CSS giao diện |
| favicon-32x32.png | Favicon |
| swagger-initializer.js | Khởi tạo cấu hình UI, tùy cách đóng gói/phiên bản |

Không sửa trực tiếp file trong JAR của dependency. Thay đổi trong JAR sẽ mất khi dependency được cập nhật và khó tái lập giữa các môi trường.

## 16. Static resource URL và classpath location không phải một

Một tài nguyên có thể nằm trong WebJar nhưng được expose bằng URL đã được Springdoc ánh xạ. Ví dụ browser có thể yêu cầu:

~~~text
/swagger-ui/swagger-ui.css
/swagger-ui/swagger-ui-bundle.js
/swagger-ui/index.html
~~~

Trong khi resource gốc nằm dưới META-INF/resources/webjars/swagger-ui/{version}/ trong classpath.

Do đó, khi debug:

- Dùng URL trong Network để kiểm tra request từ browser.
- Dùng classpath location để hiểu tài nguyên được đóng gói ở đâu.
- Dùng Spring resource handler/transformer để tùy biến.

Không suy ra URL public chỉ bằng cách ghép nguyên đường dẫn classpath vào host.

## 17. Tránh xung đột với static index.html của ứng dụng

Spring Boot có thể phục vụ trang welcome từ static/index.html hoặc public/index.html. Nếu ứng dụng đã có trang chủ riêng, entry point Swagger UI ở root có thể tạo xung đột hoặc thay đổi trang mặc định.

Springdoc khuyến nghị đặt UI ở một path riêng:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs/swagger.html
~~~

Ví dụ:

- Trang chủ ứng dụng: /
- Swagger UI: /docs/swagger.html
- OpenAPI JSON: /v3/api-docs

Tách các path giúp tránh việc route mặc định của UI cạnh tranh với welcome page của ứng dụng.

## 18. Dùng swagger-ui.use-root-path

Springdoc có property:

~~~yaml
springdoc:
  swagger-ui:
    use-root-path: true
~~~

Property này yêu cầu Swagger UI có thể được truy cập trực tiếp ở root path của ứng dụng. Chỉ bật khi ứng dụng thực sự muốn dành root cho UI.

Nếu ứng dụng đã có trang chủ hoặc static index.html, hãy kiểm tra xung đột trước khi bật. Có thể chọn custom path thay thế để giữ trang chủ.

Không nhầm use-root-path với server.servlet.context-path. Một property điều khiển vị trí UI trong ứng dụng; property còn lại đặt prefix cho toàn bộ ứng dụng MVC.

## 19. Bảo toàn static resource configuration của Spring Boot

Spring Boot tự phục vụ static resources từ các vị trí mặc định như:

- classpath:/static/
- classpath:/public/
- classpath:/resources/
- classpath:/META-INF/resources/

Nếu tự khai báo WebMvcConfigurer hoặc ResourceHandlerRegistry, hãy kiểm tra cấu hình có thay thế mapping mặc định hay không.

Ví dụ cấu hình quá rộng:

~~~java
@Configuration
public class StaticResourceConfiguration implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/**")
            .addResourceLocations("classpath:/custom-static/");
    }
}
~~~

Handler /** có thể chiếm cả các URL mà Swagger UI cần, tùy thứ tự và cấu hình resource handler. Khi asset trả 404 hoặc HTML thay vì JavaScript/CSS, rà soát custom resource handler trước khi thay dependency.

Nếu chỉ cần thêm một thư mục static riêng, dùng pattern hẹp:

~~~java
registry.addResourceHandler("/assets/**")
    .addResourceLocations("classpath:/custom-assets/");
~~~

Không đăng ký handler quá rộng nếu không hiểu rõ thứ tự mapping và fallback của Spring MVC.

## 20. Tùy biến giao diện bằng Swagger UI properties

Nhiều thay đổi không cần sửa static files. Có thể cấu hình bằng property:

~~~yaml
springdoc:
  swagger-ui:
    doc-expansion: none
    operations-sorter: alpha
    tags-sorter: alpha
    display-operation-id: true
    display-request-duration: true
    default-models-expand-depth: 1
    default-model-expand-depth: 1
    filter: true
    deep-linking: true
    try-it-out-enabled: true
~~~

Một số lựa chọn:

| Property | Tác dụng |
| --- | --- |
| doc-expansion | Mức mở rộng tag/operation mặc định |
| operations-sorter | Sắp xếp operation theo path hoặc HTTP method |
| tags-sorter | Sắp xếp tag |
| display-operation-id | Hiển thị operationId |
| display-request-duration | Hiển thị thời gian request |
| default-models-expand-depth | Mức mở rộng Models |
| filter | Bật ô lọc operation |
| deep-linking | Tạo URL liên kết tới operation/tag |
| try-it-out-enabled | Bật Try it out mặc định |

Những property này thay đổi hành vi UI, không đổi schema OpenAPI. Nếu muốn sửa request/response contract, cần sửa controller/DTO/annotation hoặc OpenAPI customizer.

## 21. Giới hạn HTTP method được phép Try it out

Có thể cấu hình những method mà UI cho phép thử:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - post
      - put
      - patch
      - delete
~~~

Nếu danh sách rỗng, Try it out bị tắt cho tất cả operation nhưng operation vẫn được hiển thị.

Đây là giới hạn giao diện, không phải chính sách bảo vệ API. Người dùng vẫn có thể gọi endpoint bằng curl, Postman hoặc HTTP client khác. Server phải tự xác thực và phân quyền.

## 22. Persist authorization và lưu token trong browser

Swagger UI có property persist-authorization để giữ thông tin xác thực qua refresh/đóng trình duyệt:

~~~yaml
springdoc:
  swagger-ui:
    persist-authorization: false
~~~

Mặc định không nên bật persistence nếu không có yêu cầu rõ ràng. Nếu bật, token có thể tiếp tục tồn tại trong browser storage/session theo cơ chế của UI và làm tăng rủi ro trên máy dùng chung.

Không đưa token thật vào URL, query parameter, source code hoặc file OpenAPI. Hãy dùng cơ chế Authorize và chính sách bảo mật phù hợp với môi trường.

## 23. Cấu hình validatorUrl

Swagger UI không mặc định phải gọi một dịch vụ validation từ xa. Property validator-url cho phép chỉ định validator:

~~~yaml
springdoc:
  swagger-ui:
    validator-url: ""
~~~

Nếu tổ chức có validator nội bộ, có thể đặt URL tương ứng. Nếu dùng validator bên ngoài, cần xem xét document có thông tin nội bộ hay không và chính sách gửi dữ liệu ra ngoài.

Validator giúp kiểm tra tính hợp lệ của OpenAPI document; nó không xác nhận rằng endpoint runtime hoạt động đúng hoặc server tuân thủ toàn bộ hợp đồng.

## 24. Tắt Swagger UI và API docs độc lập

Tắt UI:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
~~~

Tắt API docs:

~~~yaml
springdoc:
  api-docs:
    enabled: false
~~~

Hai cấu hình độc lập:

- Tắt UI nhưng giữ API docs để pipeline hoặc client tải JSON/YAML.
- Tắt API docs khiến UI không thể tải document do ứng dụng sinh, trừ khi được cấu hình dùng document khác.
- Tắt cả hai trong môi trường không công bố tài liệu.

Tắt Swagger UI không chặn các API business. Bảo vệ endpoint bằng Spring Security hoặc gateway.

## 25. Swagger UI trên Actuator management port

Trong một số kiến trúc, có thể expose UI qua management port:

~~~yaml
springdoc:
  use-management-port: true

management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include: openapi, swagger-ui
~~~

Khi bật tính năng này, các endpoint có thể được expose dưới management base path tùy cấu hình Actuator và phiên bản Springdoc.

Management port thường là bề mặt quản trị nội bộ. Cần cấu hình network policy, authentication và authorization phù hợp; không mở management port ra internet chỉ để tiện truy cập Swagger UI.

## 26. Tùy biến static resource bằng SwaggerIndexPageTransformer

Khi property không đủ để tùy biến HTML/CSS/JavaScript, Springdoc cung cấp extension point để transform Swagger UI resources. Tài liệu Springdoc mô tả tài nguyên WebJar và cách mở rộng SwaggerIndexPageTransformer.

Ví dụ transformer dưới đây dựa trên extension point của Springdoc v2 cho Spring MVC vì signature sử dụng HttpServletRequest. Với WebFlux, cần dùng các kiểu request/resource phù hợp của stack reactive.

Một transformer có thể:

- Đọc Resource gốc.
- Kiểm tra loại tài nguyên.
- Tạo nội dung đã biến đổi.
- Trả TransformedResource.
- Gọi super.transform cho tài nguyên không cần thay đổi.

Ví dụ logic rút gọn cho một resource:

~~~java
public Resource transform(
        HttpServletRequest request,
        Resource resource,
        ResourceTransformerChain chain) throws IOException {

    if (resource.toString().contains("swagger-ui.css")) {
        try (InputStream input = resource.getInputStream()) {
            String css = new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
            );

            String customized = css.replace(
                "old-value",
                "new-value"
            );

            return new TransformedResource(
                resource,
                customized.getBytes(StandardCharsets.UTF_8)
            );
        }
    }

    return super.transform(request, resource, chain);
}
~~~

Đây là phần thân minh họa cho extension point, không phải một class hoàn chỉnh có thể biên dịch độc lập. Class transformer thực tế cần kế thừa SwaggerIndexPageTransformer, gọi constructor phù hợp của phiên bản Springdoc đang dùng và đăng ký bean SwaggerIndexTransformer. Các kiểu constructor có thể thay đổi giữa các phiên bản.

Chỉ transform đúng resource cần sửa. Không đọc toàn bộ JavaScript/CSS vào bộ nhớ rồi thay chuỗi tùy tiện nếu có thể dùng một file theme nhỏ hoặc cơ chế cấu hình đơn giản hơn.

## 27. Đăng ký transformer bean

Trong mô hình Springdoc v2, tài liệu chính thức minh họa bean kiểu SwaggerIndexTransformer:

~~~java
@Configuration
public class SwaggerUiResourceConfiguration {

    @Bean
    SwaggerIndexTransformer swaggerIndexTransformer(
            SwaggerUiConfigProperties uiProperties,
            SwaggerUiOAuthProperties oauthProperties,
            SwaggerUiConfigParameters configParameters,
            SwaggerWelcomeCommon welcome) {

        return new BrandSwaggerIndexTransformer(
            uiProperties,
            oauthProperties,
            configParameters,
            welcome
        );
    }
}
~~~

BrandSwaggerIndexTransformer là class do ứng dụng triển khai và kế thừa transformer tương ứng. Constructor phải chuyển các dependency cần thiết cho superclass theo API của version Springdoc được quản lý trong dự án.

Vì đây là extension point gần với nội bộ tích hợp Swagger UI, cần kiểm tra lại signature khi nâng Springdoc. Không nên copy class transformer từ một major version cũ sang version mới mà không biên dịch và kiểm tra UI.

## 28. Tránh sửa file trong dependency JAR

Không nên:

- Giải nén WebJar rồi chỉnh trực tiếp swagger-ui-bundle.js.
- Sửa index.html bên trong JAR tại local Maven/Gradle cache.
- Copy toàn bộ static assets vào project mà không có quy trình đồng bộ version.
- Ghi đè mọi resource path bằng một handler /**.

Các cách này tạo ra bản fork không được quản lý. Khi Springdoc nâng Swagger UI, file cũ có thể không còn tương thích với initializer hoặc cấu trúc resource mới.

Ưu tiên theo thứ tự:

1. Dùng property chính thức.
2. Dùng file OpenAPI tĩnh hoặc URL tùy chỉnh nếu chỉ cần đổi nguồn document.
3. Dùng transformer extension point khi cần thay đổi resource.
4. Chỉ duy trì bản UI tùy biến riêng khi có yêu cầu sản phẩm rõ ràng và có kiểm thử sau mỗi lần nâng dependency.

## 29. Security filter phải cho phép đúng các resource cần thiết

Khi dùng Spring Security, Swagger UI có thể cần truy cập:

- Entry point HTML.
- /swagger-ui/** static assets.
- swagger-config endpoint.
- OpenAPI JSON/YAML.
- OAuth2 redirect page.
- Group document nếu dùng nhiều API group.

Ví dụ cho môi trường development:

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

Nếu docs cần bảo vệ, thay permitAll bằng role/scope phù hợp cho toàn bộ nhóm URL. Không chỉ mở HTML mà chặn CSS/JS/config/document, vì UI sẽ tải được trang nhưng không thể render API.

Đừng coi việc ẩn Swagger UI là bảo vệ business endpoint. Security filter chain vẫn phải kiểm tra mọi route theo chính sách ứng dụng.

## 30. Context path và custom path

Nếu ứng dụng có context path:

~~~yaml
server:
  servlet:
    context-path: /catalog
springdoc:
  swagger-ui:
    path: /docs/api.html
  api-docs:
    path: /openapi
~~~

URL public có thể là:

~~~text
/catalog/docs/api.html
/catalog/openapi
/catalog/openapi.yaml
/catalog/openapi/swagger-config
~~~

Context path là prefix chung của ứng dụng. springdoc.swagger-ui.path và springdoc.api-docs.path là path bên trong context của ứng dụng. Tránh thêm /catalog vào cả context path lẫn property path, nếu không URL có thể bị lặp prefix.

## 31. Reverse proxy và prefix bên ngoài

Ứng dụng có thể chạy nội bộ ở:

~~~text
http://service:8080
~~~

Nhưng người dùng truy cập:

~~~text
https://api.example.com/catalog
~~~

Reverse proxy có thể kết thúc TLS và thêm prefix. Khi proxy không chuyển forwarded headers đúng, Swagger UI có thể sinh URL tuyệt đối trỏ tới host nội bộ hoặc thiếu prefix.

Cần kiểm tra:

- Forwarded hoặc X-Forwarded-Proto.
- X-Forwarded-Host.
- X-Forwarded-Port.
- X-Forwarded-Prefix nếu proxy thêm path prefix.
- server.forward-headers-strategy của Spring Boot.
- URL tuyệt đối trong swagger-config và OpenAPI servers.

Chỉ tin forwarded headers đến từ proxy đáng tin cậy. Không cho client internet tự quyết định host/protocol mà ứng dụng dùng để sinh URL.

## 32. Kiểm tra static assets bằng Browser Network

Khi giao diện lỗi, mở DevTools:

1. Mở trang Swagger UI.
2. Nhấn F12 và chọn Network.
3. Reload trang.
4. Lọc theo swagger-ui, css, js, favicon hoặc api-docs.
5. Kiểm tra status, Request URL, Content-Type và Response.

Một số dấu hiệu:

| Request | Lỗi thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| /swagger-ui.html | 404 | Custom path, context path, starter UI |
| /swagger-ui/index.html | 404 | Static resource mapping, web stack, custom handler |
| swagger-ui.css | 404 | Resource handler hoặc static path bị ghi đè |
| swagger-ui-bundle.js | 404 | WebJar dependency/resource path |
| swagger-config | 401/403 | Spring Security hoặc gateway |
| OpenAPI document | 404 | api-docs.path, group, enabled |
| oauth2-redirect.html | 404 | OAuth redirect URL, prefix hoặc security |

Nếu HTML trả 200 nhưng JavaScript/CSS trả 404, lỗi nằm ở static resource path hoặc handler, không phải OpenAPI schema.

## 33. Kiểm tra Content-Type của static resource

Browser cần nhận đúng loại nội dung:

- CSS phải có Content-Type phù hợp như text/css.
- JavaScript phải có MIME type JavaScript.
- HTML phải được phục vụ như text/html.
- OpenAPI JSON phải được parse như JSON.

Nếu server trả trang HTML login cho request JavaScript, browser có thể báo lỗi MIME type hoặc cú pháp JavaScript. Hãy kiểm tra response body và status, không chỉ nhìn thông báo Console.

Nếu resource bị trả về với Content-Type text/html hoặc application/octet-stream, rà soát custom ResourceHandler, gateway rewrite và cấu hình MIME/static resource.

## 34. Xung đột với custom index.html

Nếu ứng dụng có trang chủ tại:

~~~text
src/main/resources/static/index.html
~~~

Swagger UI hoặc welcome handler có thể tạo xung đột route tùy cách cấu hình. Dùng path riêng:

~~~yaml
springdoc:
  swagger-ui:
    path: /developer/swagger.html
~~~

Sau đó giữ:

- / cho trang chủ ứng dụng.
- /developer/swagger.html cho Swagger UI.
- /v3/api-docs cho OpenAPI document.

Kiểm tra response của root URL và custom UI URL sau khi đóng gói ứng dụng, không chỉ khi chạy IDE.

## 35. Test entry point và static resource bằng MockMvc

Có thể viết integration test cho các route quan trọng:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SwaggerUiResourceTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void servesSwaggerUiIndex() throws Exception {
        mockMvc.perform(get("/swagger-ui/index.html"))
            .andExpect(status().isOk());
    }

    @Test
    void servesSwaggerUiStylesheet() throws Exception {
        mockMvc.perform(get("/swagger-ui/swagger-ui.css"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.valueOf("text/css")
            ));
    }

    @Test
    void servesOpenApiDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ));
    }
}
~~~

Test này giả định Spring MVC và URL mặc định. Nếu ứng dụng dùng WebFlux, dùng WebTestClient. Nếu đã đổi path hoặc phiên bản Swagger UI trả asset URL khác, điều chỉnh test theo request URL thực tế đã quan sát.

## 36. Test swagger-config

Có thể xác minh endpoint cấu hình:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SwaggerUiConfigTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void servesSwaggerConfig() throws Exception {
        String json = mockMvc.perform(get("/v3/api-docs/swagger-config"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode config = objectMapper.readTree(json);

        assertThat(
            config.path("url").asText().contains("/v3/api-docs")
            || config.path("urls").isArray()
        ).isTrue();
    }
}
~~~

Test giả định cấu hình một document mặc định. Nếu dùng document tĩnh, urls hoặc config-url tùy chỉnh, assertion phải kiểm tra nguồn mong đợi của ứng dụng thay vì khóa vào /v3/api-docs.

## 37. Chẩn đoán lỗi 404

Khi URL UI hoặc resource trả 404, phân loại trước:

| URL bị lỗi | Điều tra |
| --- | --- |
| Custom HTML path | springdoc.swagger-ui.path, enabled, context path |
| /swagger-ui/index.html | Starter UI, static resource handler, web stack |
| CSS/JS | WebJar dependency, handler /**, proxy rewrite |
| swagger-config | api-docs.path, config-url, security |
| OpenAPI group | Tên group, bean GroupedOpenApi, urls list |
| OAuth redirect | oauth2-redirect-url, prefix, route static |

Nếu toàn bộ /swagger-ui/** trả 404, kiểm tra dependency starter và việc cấu hình WebMvcConfigurer có thay thế resource handler mặc định không.

Nếu chỉ một file CSS/JS trả 404, kiểm tra đường dẫn cụ thể mà browser yêu cầu và xem artifact có chứa resource đó không.

## 38. Chẩn đoán lỗi 401/403

Nếu HTML trả 200 nhưng config hoặc asset bị 401/403:

- Xem SecurityFilterChain có bảo vệ /swagger-ui/** không.
- Xem matcher có bao gồm /v3/api-docs/swagger-config và document URL không.
- Xem gateway có yêu cầu session cho static resources không.
- Xem redirect login có trả HTML thay cho JSON/JavaScript không.
- Nếu docs nội bộ, bảo đảm người dùng có quyền tải toàn bộ tài nguyên cần thiết.

Không mở toàn bộ API business chỉ để giải quyết lỗi tải Swagger UI. Điều chỉnh matcher cho đúng phạm vi tài liệu.

## 39. Chẩn đoán giao diện trắng hoặc lỗi JavaScript

Nếu HTML và asset trả 200 nhưng giao diện trắng:

1. Mở Console và đọc lỗi JavaScript đầu tiên.
2. Kiểm tra Network có tải swagger-config thành công không.
3. Kiểm tra document URL trả JSON/YAML hợp lệ.
4. Kiểm tra response không phải HTML login/error page.
5. Kiểm tra CSP có chặn script/style không.
6. Kiểm tra custom index.html hoặc transformer có làm hỏng initializer.
7. Kiểm tra asset version có đồng bộ với Swagger UI package không.

Không nên sửa schema OpenAPI khi Console báo lỗi JavaScript bundle hoặc index.html. Hãy sửa đúng lớp giao diện trước.

## 40. Chẩn đoán URL bị sai sau reverse proxy

Nếu Swagger UI mở được nhưng CSS/JS/config trỏ về host nội bộ:

- Kiểm tra request URL trong Network.
- Kiểm tra context path và proxy prefix.
- Kiểm tra forwarded headers.
- Kiểm tra springdoc.swagger-ui.config-url nếu đã override.
- Kiểm tra URL tuyệt đối trong swagger-ui.url hoặc urls.
- Kiểm tra oauth2-redirect-url.

Nếu cấu hình một URL tuyệt đối trong swagger-ui.url, hãy xác minh URL đó đúng với từng môi trường. URL tuyệt đối có thể bỏ qua origin mà browser đang mở.

## 41. Chọn property hay transformer?

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Đổi URL mở Swagger UI | springdoc.swagger-ui.path |
| Đổi URL OpenAPI JSON/YAML | springdoc.api-docs.path |
| Chọn một file OpenAPI tĩnh | springdoc.swagger-ui.url |
| Hiển thị nhiều group/document | springdoc.swagger-ui.urls |
| Đổi config endpoint | springdoc.swagger-ui.config-url |
| Đổi OAuth callback | springdoc.swagger-ui.oauth2-redirect-url |
| Đổi cách sắp xếp/hiển thị | Swagger UI properties |
| Sửa nội dung index/CSS/JS ở mức resource | SwaggerIndexPageTransformer |
| Thay đổi API schema/operation | OpenAPI annotation/customizer, không phải static resource |

Chọn đúng extension point giúp giảm độ phức tạp và tránh fork tài nguyên Swagger UI không cần thiết.

## 42. Checklist trước khi triển khai

- [ ] Đã chọn đúng starter WebMVC hoặc WebFlux UI.
- [ ] springdoc.swagger-ui.path không xung đột trang chủ ứng dụng.
- [ ] springdoc.api-docs.path được cấu hình độc lập.
- [ ] swagger-config URL có thể truy cập.
- [ ] url hoặc urls trỏ tới document thực sự tồn tại.
- [ ] Group name và URL group khớp nhau.
- [ ] Static assets CSS/JS trả 200 và đúng Content-Type.
- [ ] OAuth redirect URL đúng host, scheme và context path.
- [ ] Security filter cho phép hoặc bảo vệ đúng toàn bộ UI/config/document resources.
- [ ] Không sửa trực tiếp resource trong dependency JAR.
- [ ] Custom resource handler không ghi đè /swagger-ui/**.
- [ ] Reverse proxy chuyển forwarded headers theo cấu hình đáng tin cậy.
- [ ] Không dùng client secret trong Swagger UI production.
- [ ] Có test cho UI index, asset, swagger-config và OpenAPI document.
- [ ] Đã kiểm tra lại sau khi build/deploy artifact thực tế.

## Kết luận

Swagger UI gồm entry point HTML, static assets, swagger-config và OpenAPI document. springdoc.swagger-ui.path điều chỉnh URL mở giao diện; springdoc.api-docs.path điều chỉnh URL document; config-url xác định nơi UI lấy cấu hình; url/urls xác định document mà UI tải. Các file CSS/JavaScript được đóng gói trong WebJar và phục vụ qua resource handler.

Hãy ưu tiên cấu hình property chính thức cho các thay đổi URL và hành vi UI. Chỉ dùng SwaggerIndexPageTransformer khi thật sự cần biến đổi static resource. Khi xảy ra lỗi, xác định request nào đang hỏng qua Network, kiểm tra status và Content-Type, rồi sửa đúng route, resource handler, security matcher hoặc proxy. Như vậy giao diện sẽ ổn định qua các lần nâng Springdoc và Swagger UI.

## Tài liệu tham khảo

- [Springdoc OpenAPI — Configuration Properties](https://springdoc.org/properties.html)
- [Springdoc OpenAPI v2 — Getting Started](https://springdoc.org/v2/getting-started.html)
- [Springdoc OpenAPI v2 — Swagger UI features and static resource customization](https://springdoc.org/v2/)
- [Swagger UI — Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [Spring Boot — Static Content](https://docs.spring.io/spring-boot/reference/web/servlet.html)
