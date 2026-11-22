# Swagger UI trả 404 dù endpoint đặc tả vẫn hoạt động

Một ứng dụng Spring Boot có thể trả OpenAPI JSON bình thường tại /v3/api-docs, nhưng khi mở /swagger-ui.html lại nhận HTTP 404. Hiện tượng này thường có nghĩa là phần sinh OpenAPI vẫn hoạt động, trong khi route giao diện, static resource của Swagger UI hoặc đường dẫn đi qua proxy chưa được đăng ký hay định tuyến đúng.

Hai endpoint phục vụ hai mục đích khác nhau:

- /v3/api-docs là endpoint trả OpenAPI document do springdoc sinh.
- /swagger-ui.html là điểm vào giao diện Swagger UI. Springdoc thường chuyển hướng điểm vào này sang trang index.html nằm trong WebJar.

Vì vậy, việc JSON hoạt động không chứng minh Swagger UI đã được đóng gói và phục vụ. Cần tìm chính xác request nào trong chuỗi tải giao diện trả 404: URL HTML ban đầu, trang index.html, file JavaScript/CSS, hay endpoint swagger-config.

## 1. Nhận diện đúng triệu chứng

Một lượt tải Swagger UI thường có nhiều request:

1. Browser gọi /swagger-ui.html.
2. Springdoc trả redirect tới trang giao diện, thường là /swagger-ui/index.html.
3. Browser tải swagger-ui.css, swagger-ui-bundle.js và các static resource khác.
4. Swagger UI gọi /v3/api-docs/swagger-config.
5. Từ cấu hình nhận được, UI tải OpenAPI document như /v3/api-docs.

Có thể hình dung chuỗi request như sau:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant S as Spring Boot
    B->>S: GET /swagger-ui.html
    S-->>B: 3xx Location: /swagger-ui/index.html
    B->>S: GET /swagger-ui/index.html
    S-->>B: HTML 200
    B->>S: GET JavaScript/CSS assets
    S-->>B: Assets 200
    B->>S: GET /v3/api-docs/swagger-config
    S-->>B: Config JSON 200
    B->>S: GET /v3/api-docs
    S-->>B: OpenAPI JSON 200
~~~

Path asset và redirect có thể thay đổi theo version, custom path hoặc resource resolver. Hãy lấy URL thực tế từ response `Location` và browser Network tab.

Nếu chỉ nhìn request đầu tiên trong tab Network, có thể bỏ sót request thực sự gây lỗi.

| Request bị lỗi | Dấu hiệu | Hướng kiểm tra đầu tiên |
|---|---|---|
| /swagger-ui.html trả 404 ngay | Không có redirect hoặc response là trang 404 của ứng dụng/proxy | Starter UI, property enabled/path, context path, management port |
| /swagger-ui.html redirect nhưng /swagger-ui/index.html trả 404 | Điểm vào tồn tại nhưng tài nguyên giao diện không được tìm thấy | WebJar, static resource mapping, đóng gói dependency |
| index.html trả 200 nhưng JS/CSS trả 404 | Trang HTML tải được nhưng giao diện trắng hoặc lỗi | Static path pattern, resource locations, reverse proxy prefix |
| HTML và JS/CSS trả 200 nhưng swagger-config trả 404 | UI mở được nhưng không biết phải tải tài liệu nào | configUrl, api-docs.path, custom path |
| swagger-config trả 200 nhưng OpenAPI URL trả 404 | UI đã chạy, URL document trong config sai | url, urls, group path, context path |
| 3xx tới trang đăng nhập | Security entry point chuyển hướng request | Kiểm tra authentication và URL cuối trong redirect chain |
| 401/403 | Request bị Spring Security từ chối | Authorization rules, authority và SecurityFilterChain |
| 404 từ gateway nhưng ứng dụng trả 200 | Proxy/ingress rewrite hoặc route public sai | So sánh request trực tiếp và request qua proxy |
| 500 | Lỗi khi khởi tạo config hoặc resolve resource | Đọc server log và exception gốc |

HTTP 404 khác với 401 và 403. Nếu ứng dụng có cơ chế cố ý che endpoint khi chưa đăng nhập, security handler có thể trả 404; khi đó cần kiểm tra security log và test bằng identity có quyền.

## 2. Kiểm tra dependency trước tiên

Đây là nguyên nhân thường gặp nhất khi /v3/api-docs hoạt động nhưng Swagger UI không tồn tại: ứng dụng chỉ thêm starter API, không thêm starter UI.

Springdoc cung cấp các starter riêng:

| Web stack | Chỉ tạo OpenAPI JSON/YAML | Có thêm Swagger UI |
|---|---|---|
| Spring MVC | springdoc-openapi-starter-webmvc-api | springdoc-openapi-starter-webmvc-ui |
| Spring WebFlux | springdoc-openapi-starter-webflux-api | springdoc-openapi-starter-webflux-ui |

Nếu project dùng spring-boot-starter-web (Spring MVC), dependency cần có UI là:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

Nếu project dùng spring-boot-starter-webflux, chọn:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

Định nghĩa springdoc.version trong Maven properties hoặc version catalog của Gradle bằng một bản tương thích với Spring Boot đang dùng. Ma trận major version thông dụng:

| Spring Boot | Nhánh springdoc |
|---|---|
| 2.x | 1.x |
| 3.x | 2.x |
| 4.x | 3.x |

Không chọn starter MVC cho ứng dụng WebFlux hoặc ngược lại. Khi nâng major version Spring Boot, hãy kiểm tra compatibility matrix và migration guide của springdoc trước khi cập nhật dependency.

### 2.1. Kiểm tra dependency thực tế

Với Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springdoc:*,org.webjars:*
~~~

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency springdoc-openapi-starter-webmvc-ui --configuration runtimeClasspath
./gradlew dependencyInsight --dependency springdoc-openapi-starter-webflux-ui --configuration runtimeClasspath
~~~

Với Maven, có thể giới hạn cây dependency ở runtime:

~~~bash
mvn dependency:tree -Dscope=runtime -Dincludes=org.springdoc:*
~~~

Đối chiếu dependency tree với loại web starter của ứng dụng. Nếu chỉ thấy springdoc-openapi-starter-webmvc-api hoặc springdoc-openapi-starter-webflux-api, OpenAPI endpoint có thể hoạt động mà không có Swagger UI. Hãy thêm đúng starter UI thay vì thêm một bản Swagger UI rời không tương thích.

File build có khai báo starter chưa đủ: dependency phải xuất hiện trong runtime artifact đang chạy. Với executable JAR, kiểm tra BOOT-INF/lib để xác nhận UI starter và WebJar được đóng gói. Nếu local hoạt động nhưng container trả 404, kiểm tra image có copy đúng JAR mới hay không và tránh deploy nhầm artifact cũ.

Nếu dependency graph có cả spring-boot-starter-web và spring-boot-starter-webflux, đừng suy luận web stack chỉ từ một dependency. Spring Boot có thể chọn Spring MVC khi cả hai stack cùng có mặt; kiểm tra startup log và condition evaluation report để biết auto-configuration nào thực sự hoạt động. Sau đó dùng starter UI tương ứng với stack được chọn và loại dependency không cần thiết nếu có thể.

Không khai báo đồng thời các starter MVC và WebFlux chỉ để thử khắc phục 404. Chọn stack thực tế của ứng dụng và loại bỏ dependency trùng hoặc phiên bản cũ còn sót.

## 3. Phân biệt các property điều khiển UI và OpenAPI

Springdoc có property độc lập cho tài liệu và giao diện:

| Property | Ý nghĩa |
|---|---|
| springdoc.api-docs.enabled | Bật/tắt endpoint OpenAPI |
| springdoc.api-docs.path | Đường dẫn endpoint OpenAPI JSON |
| springdoc.swagger-ui.enabled | Bật/tắt Swagger UI |
| springdoc.swagger-ui.path | Đường dẫn HTML entry của Swagger UI |
| springdoc.swagger-ui.configUrl | URL JSON cấu hình mà Swagger UI tải |
| springdoc.swagger-ui.url | URL của một OpenAPI document tùy chỉnh |
| springdoc.swagger-ui.urls | Danh sách OpenAPI document để UI hiển thị dạng chọn nhóm |

Ví dụ cấu hình cơ bản:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
    path: /swagger-ui.html
~~~

Nếu springdoc.swagger-ui.enabled=false trong profile đang chạy, /v3/api-docs vẫn có thể trả 200 trong khi giao diện không được đăng ký.

Hãy kiểm tra cả cấu hình profile và biến môi trường. Ví dụ:

~~~bash
SPRINGDOC_SWAGGER_UI_ENABLED=false
SPRINGDOC_SWAGGER_UI_PATH=/docs/api.html
~~~

Tên property có thể được ghi đè bởi application-prod.yml, biến môi trường, system property hoặc command-line argument. Đừng chỉ đọc application.yml rồi kết luận giá trị đang chạy.

Đặc biệt, so sánh cấu hình hiệu lực giữa local và production. Profile production có thể tắt UI, đổi custom path, tắt static mapping hoặc áp dụng security chain khác; deployment cũng có thể đang chạy artifact cũ. Nếu cần dùng Actuator env, configprops hoặc conditions để điều tra, chỉ truy cập trong môi trường quản trị đã bảo vệ và không công khai các endpoint này.

### 3.1. Đổi path HTML không đồng nghĩa đổi path OpenAPI

Ví dụ muốn đặt UI tại /docs/api.html nhưng vẫn giữ OpenAPI JSON tại /v3/api-docs:

~~~yaml
springdoc:
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /docs/api.html
~~~

URL cần mở là:

~~~text
http://localhost:8080/docs/api.html
~~~

Nếu chỉ đổi springdoc.swagger-ui.path rồi vẫn truy cập /swagger-ui.html, request cũ có thể trả 404 theo đúng cấu hình.

Ngược lại, nếu đổi springdoc.api-docs.path, hãy kiểm tra swagger-config để biết UI đang được cấu hình tải document từ URL nào. Không nhầm configUrl với URL của OpenAPI spec:

- configUrl trỏ tới JSON cấu hình Swagger UI.
- url trỏ tới OpenAPI document.

Khi dùng external OpenAPI file hoặc nhiều group, kiểm tra url/urls và urlsPrimaryName trong cấu hình UI. Chỉ override configUrl khi thực sự muốn UI lấy cấu hình từ endpoint khác.

Nếu muốn Swagger UI đọc một OpenAPI file tĩnh thay cho document sinh động, có thể đặt file tại classpath resource path như `src/main/resources/static/open-api.json`, rồi cấu hình `springdoc.swagger-ui.url: /open-api.json`. Khi đó `url` phải trỏ tới file spec có thể tải trực tiếp; `configUrl` vẫn trỏ tới JSON cấu hình Swagger UI. Hai URL không thay thế nhau.

## 4. Kiểm tra context path và servlet path

Nếu ứng dụng khai báo context path:

~~~yaml
server:
  servlet:
    context-path: /catalog
~~~

thì URL phải bao gồm context path:

~~~text
http://localhost:8080/catalog/swagger-ui.html
http://localhost:8080/catalog/v3/api-docs
~~~

Springdoc FAQ cũng xác nhận Swagger UI nằm dưới context path của ứng dụng. Vì vậy, /swagger-ui.html tại root server có thể 404 trong khi /catalog/v3/api-docs vẫn hoạt động.

Với WebFlux, kiểm tra spring.webflux.base-path nếu ứng dụng có base path. Với Spring MVC, kiểm tra server.servlet.context-path và spring.mvc.servlet.path nếu đã cấu hình servlet prefix.

Không cộng context path hai lần. Nếu reverse proxy đã đưa prefix vào URL công khai và ứng dụng cũng đặt context path tương tự, kiểm tra xem proxy đang giữ hay strip prefix trước khi forward.

## 5. Kiểm tra static resources và WebJar

Springdoc không chỉ trả một controller HTML. Swagger UI gồm các file static được đóng gói trong WebJar, ví dụ:

- index.html
- swagger-ui-bundle.js
- swagger-ui-standalone-preset.js
- swagger-ui.css
- favicon và các resource phụ trợ

Spring Boot phục vụ static resource thông qua ResourceHttpRequestHandler. Mặc định, Spring Boot tìm static content ở các vị trí classpath như:

- META-INF/resources
- resources
- static
- public

WebJar được phục vụ qua đường dẫn /webjars/** theo cấu hình mặc định của Spring Boot.

Do đó, có thể gặp tình huống:

- /swagger-ui.html redirect thành công.
- /swagger-ui/index.html trả 404.
- /v3/api-docs vẫn trả JSON bình thường.

Đây là dấu hiệu cần kiểm tra static resource handler hoặc WebJar dependency.

### 5.1. Kiểm tra các property thay đổi resource mapping

Các property sau có thể làm thay đổi hoặc tắt mapping mặc định:

| Property | Ảnh hưởng |
|---|---|
| spring.mvc.static-path-pattern | Đổi URL pattern dùng để phục vụ static resources |
| spring.webflux.static-path-pattern | Đổi URL pattern static resources trong WebFlux |
| spring.web.resources.static-locations | Thay danh sách vị trí classpath/filesystem được tìm kiếm |
| spring.web.resources.add-mappings | Tắt/bật static resource mappings |
| spring.mvc.webjars-path-pattern | Đổi path pattern cho WebJar |
| spring.webflux.webjars-path-pattern | Đổi path pattern WebJar trong WebFlux |

Ví dụ cấu hình sau chuyển static resources sang /assets/**:

~~~yaml
spring:
  mvc:
    static-path-pattern: /assets/**
~~~

Trong khi Swagger UI cần tải resource tại các URL như /swagger-ui/** và /webjars/**, pattern /assets/** có thể khiến các URL đó không được phục vụ. Nếu không có yêu cầu đặc biệt, bỏ cấu hình custom và khôi phục mapping mặc định /**.

Nếu cấu hình spring.web.resources.static-locations, cần bảo đảm các vị trí chứa WebJar và resource của ứng dụng vẫn được tìm kiếm. Property này thay thế danh sách mặc định; không nên chỉ giữ một thư mục classpath:/static/ rồi giả định resource nằm trong dependency JAR vẫn được tìm thấy.

Nếu đặt:

~~~yaml
spring:
  web:
    resources:
      add-mappings: false
~~~

Spring Boot sẽ tắt static resource mappings. OpenAPI JSON vẫn có thể được phục vụ bởi controller riêng, nhưng các file JavaScript/CSS của Swagger UI sẽ không còn được phân phối qua resource handler mặc định.

### 5.2. Kiểm tra cấu hình MVC tùy chỉnh

Rà soát các thành phần sau nếu ứng dụng từng tùy chỉnh web stack:

- Class có @EnableWebMvc.
- Class kế thừa WebMvcConfigurationSupport.
- WebMvcConfigurer#addResourceHandlers.
- Class có @EnableWebFlux.
- Class kế thừa WebFluxConfigurationSupport.
- WebFluxConfigurer#addResourceHandlers.
- ResourceHandlerRegistry.
- Cấu hình resource chain hoặc custom ResourceResolver.
- spring.mvc.static-path-pattern hoặc spring.webflux.static-path-pattern.
- spring.mvc.webjars-path-pattern hoặc spring.webflux.webjars-path-pattern.

@EnableWebMvc chuyển quyền cấu hình MVC sang ứng dụng và làm Spring Boot MVC auto-configuration lùi lại. Tương tự, @EnableWebFlux làm WebFlux auto-configuration lùi lại. Nếu một trong hai cấu hình này được thêm để xử lý chức năng khác, hãy kiểm tra lại resource handler cho Swagger UI.

Không xóa toàn bộ custom MVC configuration chỉ vì Swagger UI 404. Xác định handler nào đã thay đổi mapping, rồi khôi phục đúng static/WebJar resource path mà ứng dụng cần.

### 5.3. Kiểm tra nội dung artifact

Với Spring MVC đóng gói executable JAR, src/main/webapp không phải vị trí phù hợp để lưu Swagger UI hoặc static resource của ứng dụng; thư mục này thường bị bỏ qua khi build JAR. Spring WebFlux không dùng src/main/webapp. Ưu tiên classpath locations như src/main/resources/static cho static content do ứng dụng tự quản lý; Swagger UI của springdoc được đóng gói trong WebJar dependency.

Kiểm tra JAR ứng dụng có WebJar dependency:

~~~bash
jar tf target/application.jar | findstr /i "swagger-ui webjars"
~~~

Executable JAR thường chứa dependency lồng trong BOOT-INF/lib. Lệnh trên cho biết WebJar nào được đóng gói. Để kiểm tra nội dung bên trong, lấy đúng JAR Swagger UI từ dependency cache rồi chạy:

~~~bash
jar tf swagger-ui-webjar.jar | findstr /i "META-INF/resources/webjars/swagger-ui index.html"
~~~

Nếu WebJar không có trong runtime artifact, quay lại dependency tree và scope của dependency. Nếu WebJar có mặt nhưng URL vẫn 404, tập trung vào resource mapping, resolver hoặc proxy.

Không tự thêm webjars-locator-core như một cách sửa mặc định. Trước tiên xác định phiên bản Spring Boot, springdoc, WebJar locator đang được dùng và môi trường chạy. Một số lỗi chỉ xuất hiện với một tổ hợp phiên bản hoặc application server cụ thể; thêm một locator version tùy ý có thể tạo xung đột dependency mới.

Nếu ứng dụng đã có landing page tại root như public/index.html, kiểm tra xem route mặc định của Swagger UI có va chạm với welcome page hay không. Có thể chuyển UI sang một path riêng, ví dụ springdoc.swagger-ui.path=/swagger-ui/api-docs.html.

Springdoc FAQ cũng khuyến nghị dùng path riêng khi ứng dụng đã sở hữu nội dung tại root. Giữ trang chủ ở / và UI ở một path như /docs/swagger-ui.html giúp phân biệt welcome page với Swagger UI entry point.

## 6. Kiểm tra Spring Security

Nếu security policy yêu cầu xác thực cho mọi request, Swagger UI và static resources cũng có thể bị chặn. Hãy phân biệt:

- 401: chưa xác thực hoặc token không hợp lệ.
- 403: đã xác thực nhưng không đủ quyền.
- 302: chuyển sang trang login theo cấu hình form login.
- 404: route/resource không tồn tại hoặc ứng dụng cố ý che endpoint.

Ví dụ bảo vệ tài liệu bằng authority riêng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers(
                            "/swagger-ui.html",
                            "/swagger-ui/**",
                            "/webjars/**",
                            "/v3/api-docs/**"
                    ).hasAuthority("DOCS_READ")
                    .anyRequest().authenticated()
            )
            .build();
}
~~~

Ví dụ trên dùng authority DOCS_READ cho toàn bộ tài liệu. Ứng dụng cần có cơ chế authentication và cấp authority tương ứng. Nếu dùng path tùy chỉnh, thêm path UI và OpenAPI document đã đổi vào matcher. Nếu dùng context path, Spring Security thường match path bên trong ứng dụng, không bao gồm context path.

Nếu ứng dụng có nhiều SecurityFilterChain, kiểm tra securityMatcher và thứ tự của từng chain. Request có thể được xử lý bởi chain khác với chain bạn vừa chỉnh. Spring Security áp dụng rule đầu tiên khớp request; thêm permitAll ở cuối danh sách không ghi đè rule đã match trước đó. Khi browser tải assets dưới /webjars/**, kiểm tra matcher cho path đó riêng.

Nếu tài liệu được phép công khai, dùng `permitAll()` trên đúng các URL UI/config/spec trong `authorizeHttpRequests` thay vì loại các request này khỏi security filter chain bằng `web.ignoring()`. Cách này vẫn giữ các security headers của Spring Security. Với tài liệu nội bộ, tiếp tục yêu cầu authority/role phù hợp như ví dụ ở trên.

Trong môi trường phát triển có thể cho phép các URL docs để kiểm tra giao diện, nhưng ở production cần áp dụng chính sách truy cập phù hợp với dữ liệu mà OpenAPI document công bố. Không tắt toàn bộ Spring Security để sửa 404.

## 7. Kiểm tra reverse proxy và URL prefix

Ứng dụng có thể chạy đúng tại http://localhost:8080, nhưng qua Nginx, ingress hoặc load balancer lại trả 404.

Ví dụ URL công khai:

~~~text
https://api.example.com/catalog/swagger-ui.html
~~~

Trong khi proxy forward request vào ứng dụng ở:

~~~text
http://application:8080/swagger-ui.html
~~~

Nếu proxy strip /catalog nhưng không chuyển thông tin prefix đúng cách, Springdoc có thể sinh redirect hoặc resource URL thiếu prefix. Browser sau đó gọi /swagger-ui/index.html ở root host và nhận 404.

Kiểm tra:

1. Proxy có giữ hay strip prefix /catalog?
2. Proxy có chuyển X-Forwarded-Prefix hoặc Forwarded phù hợp không?
3. Ứng dụng đã bật forwarded-header support đúng theo Spring Boot version chưa?
4. Redirect Location có giữ public host, scheme và prefix không?
5. Các request JS/CSS và swagger-config có đi qua cùng route proxy không?

Với Spring Boot 3.x, có thể dùng Spring Framework forwarded header support:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Với Spring Boot 4.x, cấu hình forwarded header được tổ chức lại dưới server.request.header.forwarded. Ví dụ dùng Spring Framework strategy và bật prefix:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: framework
        use-prefix: true
~~~

Chọn strategy phù hợp với proxy và web server đang sử dụng. Chỉ tin forwarded headers từ proxy đáng tin cậy; không cấu hình ứng dụng tin các header do bất kỳ client bên ngoài gửi lên.

Ở mức API của framework, Servlet stack có thể dùng `ForwardedHeaderFilter`, còn reactive stack có `ForwardedHeaderTransformer`. Spring Boot có thể tự cấu hình cách xử lý forwarded headers qua property theo từng major version; tránh đăng ký thêm filter/transformer thủ công nếu auto-configuration đã xử lý cùng chức năng.

Nếu proxy không forward prefix, cần sửa routing tại proxy hoặc cấu hình public path nhất quán. Không sửa springdoc.swagger-ui.path để bù cho một proxy đang strip prefix sai.

## 8. Kiểm tra khi dùng Actuator management port

Nếu cấu hình:

~~~yaml
springdoc:
  use-management-port: true

management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include:
          - openapi
          - swagger-ui
~~~

thì tài liệu và UI được expose dưới management base path, ví dụ:

~~~text
http://localhost:9090/actuator/openapi
http://localhost:9090/actuator/swagger-ui
~~~

Trong chế độ này, các property path thông thường như springdoc.swagger-ui.path và springdoc.api-docs.path không còn được áp dụng theo cách thông thường. Nếu tiếp tục truy cập /swagger-ui.html trên application port, bạn có thể nhận 404 dù endpoint OpenAPI vẫn đang hoạt động ở management port.

Management port cần được cấu hình tách biệt với application port để dùng cách expose này.

Kiểm tra management.server.port, management.endpoints.web.base-path, management.endpoints.web.exposure.include và springdoc.use-management-port trước khi thay đổi URL.

### 8.1. Dùng Actuator mappings để xác nhận route đã đăng ký

Nếu ứng dụng có Actuator và nhóm vận hành được phép truy cập, /actuator/mappings giúp xác định handler và resource mapping đã được đăng ký:

~~~text
/actuator/mappings
~~~

Tìm các mapping liên quan tới Swagger UI entry/welcome route, swagger-config, OpenAPI JSON và resource handler cho UI assets. Nếu API-docs mapping có mặt nhưng UI entry route không có, kiểm tra UI starter và điều kiện auto-configuration. Nếu entry route có nhưng asset không được map, kiểm tra static resource/WebJar configuration.

Không bật /actuator/mappings công khai để điều tra. Output có thể tiết lộ cấu trúc endpoint và thông tin triển khai; bảo vệ endpoint bằng network policy và Spring Security.

## 9. Quy trình chẩn đoán bằng curl

Chạy các lệnh trên cùng host, port, context path và authentication mà browser đang sử dụng.

### 9.1. Xác nhận OpenAPI document

~~~bash
curl -i http://localhost:8080/v3/api-docs
~~~

Kết quả mong đợi là HTTP 200 và JSON có trường openapi, info, paths.

### 9.2. Kiểm tra URL entry của Swagger UI

~~~bash
curl -i http://localhost:8080/swagger-ui.html
~~~

Nếu route tồn tại, response thường là redirect (3xx) tới trang Swagger UI. Xem header Location để biết URL kế tiếp.

Theo redirect:

~~~bash
curl -i -L http://localhost:8080/swagger-ui.html
~~~

Nếu response cuối cùng là 404, xác định URL cuối trong redirect chain. Đừng chỉ nhìn status của request đầu tiên.

### 9.3. Kiểm tra trực tiếp index và WebJar resources

~~~bash
curl -i http://localhost:8080/swagger-ui/index.html
curl -i http://localhost:8080/webjars/swagger-ui/swagger-ui.css
~~~

URL WebJar thực tế có thể phụ thuộc version và resource resolver. Hãy lấy URL từ tab Network hoặc HTML đã trả về để kiểm tra đúng file đang được browser yêu cầu.

### 9.4. Kiểm tra swagger-config

~~~bash
curl -i http://localhost:8080/v3/api-docs/swagger-config
~~~

Response mong đợi là JSON cấu hình UI. Kiểm tra các trường như url, urls, configUrl và oauth2RedirectUrl nếu có. Nếu đã đổi springdoc.api-docs.path, hãy kiểm tra URL trong config có trỏ tới document mới hay không.

### 9.5. Kiểm tra cả chuỗi bằng header-only request

~~~bash
curl -sS -D - -o /dev/null http://localhost:8080/swagger-ui.html
curl -sS -L -D - -o /dev/null http://localhost:8080/swagger-ui.html
curl -sS -D - -o /dev/null http://localhost:8080/swagger-ui/index.html
curl -sS -D - -o /dev/null http://localhost:8080/v3/api-docs/swagger-config
~~~

So sánh status, Location, Content-Type và URL cuối cùng. Nếu dùng context path /catalog, thêm prefix đó vào từng request.

## 10. Kiểm tra trong browser DevTools

Mở Developer Tools → Network, bật Preserve log và Disable cache, sau đó reload trang Swagger UI.

Lọc theo Doc, JS, CSS và xem:

- Request đầu tiên tới /swagger-ui.html.
- Redirect chain và Location.
- Request index.html.
- Các request .js, .css, favicon.
- Request /v3/api-docs/swagger-config.
- Request OpenAPI JSON/YAML.

Đối chiếu cột Status và Initiator:

| Quan sát | Kết luận có khả năng |
|---|---|
| HTML entry 404 | Route UI hoặc path/context sai |
| HTML entry 302, index 404 | Static/WebJar mapping hoặc proxy prefix sai |
| HTML 200, JS/CSS 404 | Resource URL không được phục vụ |
| JS/CSS 200, config 404 | configUrl hoặc API docs path sai |
| Config 200, spec 404 | url/urls trong config sai |
| Các request 401/403 | Security policy |
| Local chạy, public URL lỗi | Reverse proxy/ingress/base path |

Nếu browser nhận HTML login page với status 200 hoặc 302 thay vì JSON ở swagger-config, kiểm tra authentication redirect. Một response HTML không phải OpenAPI config hợp lệ.

## 11. Bật log để xác định handler xử lý request

Trong môi trường kiểm thử, có thể bật log Spring MVC resource handler:

~~~yaml
logging:
  level:
    org.springframework.web.servlet.DispatcherServlet: DEBUG
    org.springframework.web.servlet.handler: TRACE
    org.springframework.web.servlet.resource: TRACE
~~~

Nếu ứng dụng dùng WebFlux, bật log cho reactive handler/resource package tương ứng:

~~~yaml
logging:
  level:
    org.springframework.web.reactive.DispatcherHandler: DEBUG
    org.springframework.web.reactive.handler: TRACE
    org.springframework.web.reactive.resource: TRACE
~~~

Tìm các thông tin:

- Request được map tới controller nào?
- Request được map tới ResourceHttpRequestHandler hay không?
- Resource handler đang tìm trong classpath locations nào?
- Resource có được resolve từ WebJar hay không?
- Có NoResourceFoundException hoặc NoHandlerFoundException không?
- Request có bị security filter từ chối hoặc redirect không?

Sau khi xác định xong, tắt TRACE ở môi trường production nếu không cần thiết vì log có thể rất nhiều.

## 12. MockMvc regression test

Nên có integration test để xác nhận cả OpenAPI endpoint và Swagger UI entry vẫn được phục vụ sau khi nâng Spring Boot hoặc springdoc.

Ví dụ với Spring MVC:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SwaggerUiAvailabilityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void openApiDocumentIsAvailable() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.openapi").exists())
                .andExpect(jsonPath("$.paths").exists());
    }

    @Test
    void swaggerUiEntryRedirectsToItsPage() throws Exception {
        mockMvc.perform(get("/swagger-ui.html"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().exists("Location"));
    }

    @Test
    void swaggerUiIndexIsAvailable() throws Exception {
        mockMvc.perform(get("/swagger-ui/index.html"))
                .andExpect(status().isOk());
    }

    @Test
    void swaggerUiConfigurationIsAvailable() throws Exception {
        mockMvc.perform(get("/v3/api-docs/swagger-config"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.url").exists());
    }
}
~~~

Ví dụ giả định dùng đường dẫn mặc định, starter MVC UI và không có security policy chặn các request trong test. Nếu ứng dụng dùng context path, custom UI path, custom configUrl hoặc security, điều chỉnh request và thêm authentication phù hợp.

swagger-ui.html có thể redirect tới URL nội bộ thay đổi theo cấu hình/phiên bản; test nên kiểm tra có redirect và index resource hoạt động, thay vì cố định toàn bộ query string trong Location.

Nếu docs được bảo vệ, bổ sung test cho người dùng có và không có quyền. Ví dụ dưới đây giả định security policy trả 401 khi request chưa xác thực; nếu ứng dụng dùng form login hoặc cố ý che route, điều chỉnh assertion theo policy thực tế:

~~~java
import org.springframework.security.test.context.support.WithMockUser;

@Test
@WithMockUser(authorities = "DOCS_READ")
void apiDocsAreAvailableToDeveloper() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk());
}

@Test
void apiDocsAreNotAvailableWithoutAuthentication() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isUnauthorized());
}
~~~

Test riêng entry point, swagger-config, assets và document. Một request được phép không chứng minh mọi URL trong chuỗi tải UI cũng được phép.

MockMvc kiểm tra handler và resource mapping trong application context. Nó không kiểm tra reverse proxy, DNS, TLS termination hoặc routing của ingress; cần thêm smoke test qua URL public sau khi deploy.

## 13. Các lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chỉ có springdoc-openapi-starter-webmvc-api | Starter chỉ tạo OpenAPI document | Thêm springdoc-openapi-starter-webmvc-ui |
| Dùng MVC UI starter cho WebFlux | Starter không khớp web stack | Chọn springdoc-openapi-starter-webflux-ui |
| Build có UI starter nhưng production vẫn 404 | Runtime artifact/container image cũ hoặc dependency bị loại khỏi runtime | Kiểm tra runtime dependency tree, BOOT-INF/lib và image đang deploy |
| springdoc.swagger-ui.enabled=false | UI bị tắt trong profile hoặc environment | Bật UI trong môi trường cần dùng và kiểm tra effective property |
| Truy cập URL cũ sau khi đổi springdoc.swagger-ui.path | UI entry đã chuyển path | Mở custom path đúng |
| Bỏ qua server.servlet.context-path | Thiếu context prefix | Thêm context path vào URL |
| spring.mvc.static-path-pattern đổi thành /assets/** | Swagger UI static resources không khớp mapping | Khôi phục /** hoặc thiết kế lại static mapping |
| spring.web.resources.add-mappings=false | Static resources bị tắt | Bật lại nếu cần phục vụ Swagger UI |
| @EnableWebMvc hoặc custom resource handler | Boot MVC auto-configuration không còn quản lý mapping như trước | Rà soát resource handlers và WebJar locations |
| Thiếu WebJar trong runtime artifact | Dependency scope/exclusion hoặc starter sai | Sửa dependency và kiểm tra JAR đóng gói |
| Proxy strip prefix nhưng không forward prefix | Redirect/resource URL thiếu base path | Đồng bộ proxy route và forwarded-header strategy |
| springdoc.use-management-port=true | UI chuyển sang management port/base path | Mở /actuator/swagger-ui trên management port |
| Security chặn static resource | UI/index/config không được phép truy cập | Cập nhật matcher đúng với chính sách docs |
| UI tải được nhưng config URL 404 | configUrl hoặc API docs path không khớp | Kiểm tra swagger-config và property liên quan |
| src/main/webapp chứa resource nhưng app đóng gói JAR | Nội dung thư mục không được đóng gói như mong đợi | Đặt resource trong classpath static locations hoặc dùng WAR phù hợp |
| Chỉ lỗi qua gateway | Rewrite/strip prefix hoặc forwarded headers không khớp | So sánh Location, request path và header giữa public URL với ứng dụng |
| Mapping không xuất hiện trong Actuator | Auto-configuration không tạo route hoặc profile/condition không thỏa | Kiểm tra /actuator/mappings và condition report trong môi trường được bảo vệ |

## 14. Quy trình xử lý sự cố theo thứ tự

1. **Xác nhận đúng URL**: kiểm tra context path, custom UI path, management port và proxy prefix.
2. **Xác nhận đúng dependency**: dùng UI starter đúng với MVC/WebFlux và Spring Boot major version.
3. **Kiểm tra property hiệu lực**: springdoc.swagger-ui.enabled, springdoc.swagger-ui.path, springdoc.api-docs.path và profile.
4. **Theo redirect**: ghi lại URL trong Location, không chỉ xem status của /swagger-ui.html.
5. **Kiểm tra index resource**: gọi trực tiếp /swagger-ui/index.html.
6. **Kiểm tra WebJar**: xem dependency tree và nội dung JAR.
7. **Kiểm tra static mapping**: static-path-pattern, static-locations, add-mappings, WebMvcConfigurer và @EnableWebMvc.
8. **Kiểm tra security**: phân biệt 401/403/302 với 404 thực sự.
9. **Kiểm tra config**: tải /v3/api-docs/swagger-config, xác nhận URL OpenAPI được trỏ tới.
10. **Kiểm tra proxy**: so sánh request localhost và public URL, forwarded headers và prefix.
11. **Kiểm tra log mapping**: xác định handler/resource resolver nào trả 404.
12. **Thêm regression test**: kiểm tra OpenAPI, Swagger UI entry, index và swagger-config.

Không thêm dependency hoặc thay hàng loạt resource configuration khi chưa xác định request cụ thể bị 404. Sửa đúng lớp gây lỗi rồi chạy lại toàn bộ request chain.

## 15. Checklist review

- [ ] /v3/api-docs trả HTTP 200.
- [ ] Dependency có starter UI đúng với Spring MVC hoặc WebFlux.
- [ ] springdoc major version tương thích với Spring Boot.
- [ ] springdoc.swagger-ui.enabled có giá trị hiệu lực là true.
- [ ] URL UI khớp springdoc.swagger-ui.path.
- [ ] Context path/base path đã được tính vào URL.
- [ ] /swagger-ui.html redirect tới URL hợp lệ.
- [ ] /swagger-ui/index.html trả HTTP 200.
- [ ] JavaScript, CSS và WebJar resources trả HTTP 200.
- [ ] /v3/api-docs/swagger-config trả JSON hợp lệ.
- [ ] url hoặc urls trỏ tới OpenAPI document có thể truy cập.
- [ ] Static resource mapping không bị tắt hoặc chuyển khỏi Swagger/WebJar path.
- [ ] JAR runtime chứa Swagger UI WebJar dependency.
- [ ] Security rules cho UI, WebJar và docs đúng với policy.
- [ ] Reverse proxy chuyển prefix/forwarded headers đúng.
- [ ] Nếu dùng management port, UI được mở dưới Actuator path.
- [ ] Có MockMvc test và smoke test qua public URL.

## 16. Tài liệu tham khảo

- [springdoc-openapi – Getting Started và Swagger UI support](https://springdoc.org/index.html#swagger-ui-support)
- [springdoc-openapi – Configuration properties](https://springdoc.org/properties.html)
- [springdoc-openapi – FAQ: Reverse proxy](https://springdoc.org/index.html#how-can-i-deploy-springdoc-openapi-starter-webmvc-ui-behind-a-reverse-proxy)
- [springdoc-openapi – FAQ: Context path](https://springdoc.org/index.html#what-is-the-url-of-the-swagger-ui-when-i-set-a-different-context-path)
- [Spring Boot 3.5 – Static content and WebJars](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Boot 3.5 – Forwarded headers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot current – Static content and WebJars](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot current – WebFlux static content and WebJars](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Boot current – Forwarded headers](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [springdoc-openapi – Swagger UI availability test](https://github.com/springdoc/springdoc-openapi/blob/main/springdoc-openapi-starter-webmvc-ui/src/test/java/test/org/springdoc/ui/app1/SpringDocApp1Test.java)

Swagger UI 404 trong khi OpenAPI JSON hoạt động thường là sự cố riêng của UI starter, đường dẫn HTML, static/WebJar resource hoặc routing. Hãy theo redirect và xác định request đầu tiên trả 404; sau đó kiểm tra dependency, property, context path, resource handler, security và reverse proxy theo đúng lớp. Khi cả HTML entry, index, JavaScript/CSS, swagger-config và OpenAPI document đều trả đúng response, Swagger UI mới thực sự sẵn sàng cho người dùng.
