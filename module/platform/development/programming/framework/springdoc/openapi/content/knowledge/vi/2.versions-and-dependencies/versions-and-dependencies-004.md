# Chọn starter cho Spring MVC hoặc WebFlux

Để springdoc-openapi sinh tài liệu đúng với ứng dụng, hãy chọn starter theo web stack mà Spring Boot thực sự khởi chạy: Spring MVC hay Spring WebFlux. Sau đó chọn biến thể có Swagger UI nếu cần giao diện thử API, hoặc biến thể API-only nếu chỉ cần endpoint OpenAPI JSON/YAML cho CI, API portal hay công cụ khác.

Hai quyết định này độc lập:

1. **Web stack:** MVC hay WebFlux.
2. **Cách phân phối tài liệu:** API-only hay có Swagger UI.

Không chọn starter chỉ dựa trên việc project có dùng Reactor, WebClient hoặc một dependency reactive. Một ứng dụng MVC vẫn có thể dùng WebClient; điều đó không biến server thành WebFlux.

## 1. Bốn starter thường dùng

Với springdoc-openapi từ phiên bản 2 trở lên, bảng lựa chọn chính là:

| Web stack của ứng dụng | Chỉ xuất OpenAPI JSON/YAML | Có Swagger UI |
|---|---|---|
| Spring MVC / Servlet | springdoc-openapi-starter-webmvc-api | springdoc-openapi-starter-webmvc-ui |
| Spring WebFlux / Reactive | springdoc-openapi-starter-webflux-api | springdoc-openapi-starter-webflux-ui |

Tên artifact phản ánh hai thông tin:

- webmvc hoặc webflux cho biết integration tương ứng với web stack.
- api hoặc ui cho biết phạm vi tài liệu được cung cấp.

Starter API-only cung cấp OpenAPI endpoints mà không đóng gói giao diện Swagger UI. Starter UI tích hợp Swagger UI cùng phần sinh OpenAPI tương ứng với web stack. Với nhu cầu thông thường, chọn đúng một starter cho ứng dụng.

Không thêm cả api và ui starter cùng loại chỉ để có cả JSON lẫn Swagger UI. UI starter đã bao gồm phần cần thiết để cung cấp OpenAPI document và giao diện. Việc khai báo hai starter cùng chức năng thường chỉ làm dependency graph phức tạp hơn.

## 2. Xác định ứng dụng đang chạy Spring MVC hay WebFlux

Hãy xem dependency khởi tạo server và loại ApplicationContext, không chỉ xem kiểu trả về của một controller.

| Dấu hiệu | Spring MVC | Spring WebFlux |
|---|---|---|
| Starter web chính | spring-boot-starter-web | spring-boot-starter-webflux |
| Mô hình server | Servlet stack | Reactive stack |
| Abstraction chính | DispatcherServlet, Servlet filters | HttpHandler, WebFilter |
| Controller phổ biến | @RestController, @RequestMapping | @RestController, @RequestMapping |
| Kiểu trả về thường gặp | DTO, ResponseEntity, List | Mono, Flux, ResponseEntity<Mono<T>> |
| Functional endpoint | Servlet MVC functional routing | RouterFunction, HandlerFunction, ServerRequest |
| Codec/converter | HttpMessageConverter | HttpMessageReader, HttpMessageWriter |

Annotation-based controller của MVC và WebFlux có hình thức gần giống nhau. Chỉ nhìn @RestController hoặc @GetMapping thì chưa đủ để kết luận web stack.

Ví dụ MVC:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping
    List<ProductResponse> findAll() {
        return productService.findAll();
    }
}
~~~

Ví dụ WebFlux:

~~~java
@RestController
@RequestMapping("/api/products")
class ReactiveProductController {

    @GetMapping
    Flux<ProductResponse> findAll() {
        return productService.findAll();
    }
}
~~~

Hai ví dụ có cùng kiểu annotation, nhưng ứng dụng cần starter springdoc phù hợp với web stack được Spring Boot cấu hình.

## 3. Kiểm tra dependency nền của ứng dụng

Với Maven, mở pom.xml và xác định starter web:

~~~xml
<!-- Spring MVC / Servlet -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Hoặc:

~~~xml
<!-- Spring WebFlux / Reactive -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Với Gradle:

~~~kotlin
// Spring MVC / Servlet
implementation("org.springframework.boot:spring-boot-starter-web")

// Hoặc Spring WebFlux / Reactive
implementation("org.springframework.boot:spring-boot-starter-webflux")
~~~

Không thêm cả hai starter web chỉ để thử xem starter springdoc nào chạy. Trước hết xác định server stack mà ứng dụng được thiết kế để sử dụng.

## 4. Trường hợp classpath có cả MVC và WebFlux

Spring Boot có một quy tắc dễ gây nhầm: nếu cả spring-boot-starter-web và spring-boot-starter-webflux có mặt trên classpath, Spring MVC được ưu tiên theo mặc định. Spring Boot chọn hành vi này vì nhiều ứng dụng MVC thêm WebFlux chủ yếu để dùng WebClient, không phải để chuyển server sang reactive stack.

Ví dụ một ứng dụng MVC dùng WebClient:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Nếu ứng dụng vẫn khởi chạy Servlet/MVC, hãy dùng springdoc-openapi-starter-webmvc-api hoặc springdoc-openapi-starter-webmvc-ui tùy nhu cầu tài liệu. Việc dùng WebClient không phải lý do để chọn WebFlux starter.

Nếu thật sự muốn chạy WebFlux dù classpath có MVC, Spring Boot cho phép đặt application type tường minh:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Chỉ làm vậy khi toàn bộ ứng dụng được thiết kế và kiểm thử như một reactive server. Việc ép application type không tự chuyển controller, filter, security configuration hoặc thư viện Servlet sang WebFlux.

Khi nghi ngờ loại application context, kiểm tra log khởi động, bean DispatcherServlet/HttpHandler, cấu hình web application type và dependency tree. Đừng suy luận từ một class Reactor có mặt trong project.

## 5. Chọn API-only hay Swagger UI

### Chọn API-only khi

- OpenAPI document được lấy bởi API portal hoặc developer portal khác.
- CI cần tải JSON/YAML để lint, diff, generate SDK hoặc kiểm thử contract.
- Tổ chức không muốn nhúng giao diện Swagger UI vào service.
- Tài liệu được phát hành qua một host hoặc hệ thống khác.
- Muốn giảm tài nguyên giao diện tĩnh được đóng gói trong ứng dụng.

Starter API-only:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Nếu server là WebFlux, thay artifact bằng springdoc-openapi-starter-webflux-api.

### Chọn Swagger UI khi

- Developer cần xem operation, parameter, schema và response ngay trong ứng dụng.
- Nhóm muốn dùng Try it out để gọi thử endpoint.
- Ứng dụng cung cấp tài liệu tương tác trong môi trường local, test hoặc nội bộ.

Starter UI cho MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Starter UI cho WebFlux:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Ví dụ dùng phiên bản 3.2.0 dành cho Spring Boot 4. Nếu ứng dụng dùng Spring Boot 3, phải dùng dòng springdoc 2.x; không copy nguyên version 3.2.0 vào project Boot 3.

## 6. Ma trận tương thích Spring Boot và springdoc

Chọn đúng web stack chưa đủ; major version của springdoc cũng phải tương thích với major version Spring Boot.

| Spring Boot | Dòng springdoc | Tài liệu tương ứng | Ghi chú |
|---|---|---|---|
| 4.x | 3.x | springdoc.org | Dòng hiện hành cho Boot 4 |
| 3.x | 2.x | springdoc.org/v2 | Dòng dành cho Boot 3 |
| 2.x và 1.x | 1.8.0 | springdoc.org/v1 | Nhánh cũ, đã kết thúc hỗ trợ mã nguồn mở |

Tại thời điểm soạn bài, tài liệu chính thức hiển thị springdoc 3.2.0 cho Spring Boot 4 và springdoc 2.10.0 cho Spring Boot 3. Các version này là ví dụ theo tài liệu hiện hành; khi tạo project mới, kiểm tra compatibility matrix và release notes để chọn patch release phù hợp.

Không dùng springdoc 3.x với Spring Boot 3 chỉ vì số phiên bản mới hơn. Không dùng springdoc 2.x với Boot 4. Không trộn artifact v1 với starter v2/v3 trong cùng dependency graph.

### Artifact ở springdoc v1 khác tên starter hiện hành

Nếu duy trì ứng dụng Spring Boot 1.x/2.x cũ, tài liệu v1 dùng các artifact không có tiền tố starter:

| Nhu cầu | MVC trong v1 | WebFlux trong v1 |
|---|---|---|
| API document | springdoc-openapi-webmvc-core | springdoc-openapi-webflux-core |
| Swagger UI | springdoc-openapi-ui | springdoc-openapi-webflux-ui |

Đây là tên artifact của nhánh v1. Từ v2, module được chuyển sang các starter như springdoc-openapi-starter-webmvc-api và springdoc-openapi-starter-webflux-ui. Khi nâng cấp v1 lên v2, cần theo migration guide thay vì chỉ đổi version.

## 7. Cấu hình Maven cho Spring MVC

Ví dụ project Spring Boot 4 dùng MVC và cần Swagger UI:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>3.2.0</version>
    </dependency>
</dependencies>
~~~

Nếu chỉ cần OpenAPI document, thay webmvc-ui bằng webmvc-api:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Không khai báo đồng thời hai dependency trên nếu không có lý do module hóa cụ thể. Chọn đúng một trong hai theo nhu cầu.

## 8. Cấu hình Maven cho WebFlux

Ví dụ project Spring Boot 4 dùng WebFlux và cần Swagger UI:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
        <version>3.2.0</version>
    </dependency>
</dependencies>
~~~

Nếu chỉ cần OpenAPI document, thay webflux-ui bằng webflux-api:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-api</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Không thêm webmvc-ui vào ứng dụng WebFlux hoặc webflux-ui vào ứng dụng MVC chỉ vì muốn thử Swagger UI. Chọn module tương ứng với server stack.

## 9. Cấu hình Gradle cho MVC và WebFlux

Với Gradle Groovy DSL, MVC + Swagger UI:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springdoc:springdoc-openapi-starter-webmvc-ui:3.2.0'
}
~~~

WebFlux + Swagger UI:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springdoc:springdoc-openapi-starter-webflux-ui:3.2.0'
}
~~~

API-only cho MVC:

~~~groovy
implementation 'org.springdoc:springdoc-openapi-starter-webmvc-api:3.2.0'
~~~

API-only cho WebFlux:

~~~groovy
implementation 'org.springdoc:springdoc-openapi-starter-webflux-api:3.2.0'
~~~

Với Kotlin DSL, cú pháp dependency tương ứng là:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:3.2.0")
}
~~~

Thay hai artifact theo ma trận khi dùng WebFlux hoặc API-only. Trong dự án thực tế, nên khai báo version springdoc tại một nơi và pin version đã kiểm tra tương thích.

## 10. Dùng dependency management và tránh lệch version

Spring Boot parent/BOM quản lý version của các dependency Spring Boot. Nó không có nghĩa mọi thư viện bên thứ ba, bao gồm springdoc-openapi, đều được quản lý theo cùng một version.

Với Maven:

- Dùng spring-boot-starter-parent hoặc import Spring Boot dependency BOM theo cấu trúc project.
- Khai báo một property springdoc.version.
- Dùng cùng version cho các artifact springdoc nếu cần thêm module mở rộng.
- Không override riêng swagger-core hoặc swagger-annotations nếu chưa có lý do và kiểm tra tương thích.

Với Gradle:

- Dùng Spring Boot plugin và dependency management theo cấu hình project.
- Pin version springdoc trong version catalog hoặc biến tập trung.
- Kiểm tra dependencyInsight khi có nhiều version được kéo vào.

Ví dụ version catalog:

~~~toml
[versions]
springdoc = "3.2.0"

[libraries]
springdoc-webmvc-ui = {
  module = "org.springdoc:springdoc-openapi-starter-webmvc-ui",
  version.ref = "springdoc"
}
~~~

Không dùng version động như latest.release trong build production. Version động có thể làm dependency graph thay đổi giữa hai lần build dù source không đổi.

## 11. Các dependency không nên thêm trùng

Springdoc starter kéo theo các module cần thiết cho chức năng mà nó cung cấp. Vì vậy:

- Không thêm swagger-core thủ công chỉ để springdoc sinh OpenAPI.
- Không thêm swagger-annotations riêng nếu chỉ cần các annotation đã được starter cung cấp.
- Không thêm swagger-ui artifact riêng khi đã dùng springdoc UI starter.
- Không thêm cả API-only và UI starter cùng web stack nếu không có kiến trúc module rõ ràng.
- Không thêm cả MVC và WebFlux springdoc starter trong một ứng dụng chỉ có một server stack.

Nếu cần một extension đặc biệt, đọc module guide và dependency tree trước khi thêm. Việc khai báo trực tiếp một transitive dependency có thể ép version không tương thích với springdoc hoặc Spring Boot.

## 12. Kiểm tra dependency tree

Với Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Hoặc kiểm tra riêng một dependency:

~~~bash
./gradlew dependencyInsight \
  --dependency springdoc-openapi \
  --configuration runtimeClasspath
~~~

Kiểm tra các dấu hiệu:

- Chỉ có một nhánh web stack chủ đích.
- Starter springdoc có hậu tố webmvc hoặc webflux đúng với ứng dụng.
- Không có artifact v1 lẫn starter v2/v3.
- Không có hai version swagger-core/swagger-annotations cạnh tranh.
- Swagger UI chỉ có mặt nếu chọn UI starter.

Nếu dependency được đưa vào bởi module nội bộ, kiểm tra dependency path thay vì xóa ngẫu nhiên một artifact trong cache.

## 13. Các endpoint kiểm tra sau khi chọn starter

Với starter API-only hoặc UI, OpenAPI document mặc định thường có:

| URL | Kết quả mong đợi |
|---|---|
| /v3/api-docs | OpenAPI document dạng JSON |
| /v3/api-docs.yaml | OpenAPI document dạng YAML |

Với UI starter, Swagger UI thường có thể truy cập tại:

| URL | Mục đích |
|---|---|
| /swagger-ui.html | URL vào giao diện Swagger UI, thường redirect |
| /swagger-ui/index.html | Trang giao diện tĩnh |
| /v3/api-docs/swagger-config | Cấu hình mà Swagger UI tải |

URL thực tế còn phụ thuộc context path, springdoc.api-docs.path, springdoc.swagger-ui.path, reverse proxy và cấu hình security.

Sau khi chạy ứng dụng, thử:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
curl -i http://localhost:8080/swagger-ui.html
~~~

Nếu dùng API-only, việc /swagger-ui.html trả 404 là bình thường. Đừng kết luận starter bị lỗi khi ứng dụng được thiết kế không cung cấp giao diện.

## 14. Chọn starter cho WebFlux functional endpoints

Spring WebFlux hỗ trợ cả annotation-based controllers và functional endpoints:

- Annotation-based: @RestController, @GetMapping, @PostMapping.
- Functional: RouterFunction<ServerResponse> kết hợp HandlerFunction.

springdoc có hỗ trợ functional endpoints. Với các route cần mô tả rõ operation, có thể dùng @RouterOperation hoặc @RouterOperations để gắn metadata OpenAPI vào route.

Ví dụ route:

~~~java
@Configuration
class ProductRoutes {

    @Bean
    RouterFunction<ServerResponse> productRouter(ProductHandler handler) {
        return RouterFunctions.route()
            .GET("/api/products", handler::findAll)
            .POST("/api/products", handler::create)
            .build();
    }
}
~~~

Khi mô tả functional route, bổ sung metadata operation theo hướng dẫn springdoc tương ứng:

~~~java
@Bean
@RouterOperations({
    @RouterOperation(
        path = "/api/products",
        method = RequestMethod.GET,
        beanClass = ProductHandler.class,
        beanMethod = "findAll",
        operation = @Operation(
            operationId = "findProducts",
            summary = "Liệt kê sản phẩm"
        )
    )
})
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET("/api/products", handler::findAll)
        .build();
}
~~~

Đây là ví dụ rút gọn để minh họa metadata route; import và cấu trúc bean cần khớp với phiên bản springdoc đang dùng. Functional endpoint không phải lý do để chọn MVC starter; nếu server là WebFlux, vẫn chọn webflux-api hoặc webflux-ui.

## 15. Spring Security không quyết định MVC hay WebFlux

Spring Security có integration riêng cho Servlet và Reactive stack. Chọn starter springdoc theo web stack, sau đó cấu hình quyền truy cập OpenAPI/Swagger UI theo security model đang dùng.

Ví dụ:

- Ứng dụng MVC dùng spring-boot-starter-security với Servlet filter chain: chọn webmvc-api hoặc webmvc-ui.
- Ứng dụng WebFlux dùng reactive security: chọn webflux-api hoặc webflux-ui.

Nếu chỉ cần OpenAPI document và không cần giao diện, API-only thường là lựa chọn gọn hơn. Nhưng API-only không tự làm document public hoặc an toàn; endpoint /v3/api-docs vẫn chịu security rules của ứng dụng.

Nếu dùng UI starter, phải kiểm tra quyền cho cả tài nguyên Swagger UI, swagger-config và OpenAPI document. Không mở toàn bộ API nghiệp vụ chỉ để giao diện tải được.

## 16. Khi nào chọn API-only cho CI hoặc API portal?

Một service production có thể không cần Swagger UI nhúng trong ứng dụng. CI có thể tải document, kiểm tra rồi lưu thành artifact:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  -o target/openapi.json
~~~

Pipeline sau đó có thể:

1. Validate OpenAPI document.
2. Chạy lint theo quy tắc tổ chức.
3. So sánh với document release trước.
4. Sinh SDK hoặc tài liệu portal.
5. Lưu document làm build artifact.

Trong mô hình này, API-only giảm thành phần giao diện cần triển khai. Nếu API portal tải document qua HTTP, cấu hình authentication, network access và CORS phù hợp với cách portal truy cập; API-only không tự cấu hình các chính sách đó.

## 17. Dấu hiệu chọn nhầm starter

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| MVC app không tạo OpenAPI document | Đang dùng webflux starter | Đổi sang webmvc starter |
| WebFlux app thiếu OpenAPI integration | Đang dùng webmvc starter | Đổi sang webflux starter |
| /v3/api-docs hoạt động nhưng Swagger UI 404 | Đang dùng API-only starter | Thêm UI starter đúng web stack nếu cần UI |
| Swagger UI có nhưng document 404 | Security/path/context path hoặc cấu hình endpoint | Kiểm tra swagger-config và URL docs |
| Project có cả MVC và WebFlux nhưng chạy MVC | Spring Boot ưu tiên MVC khi cả hai starter có mặt | Kiểm tra application type và chọn webmvc starter nếu đúng chủ đích |
| Project dùng WebClient nhưng server là MVC | Nhầm WebClient với WebFlux server | Giữ webmvc starter |
| Có lỗi class/method không tìm thấy sau khi thêm springdoc | Lẫn major version hoặc dependency bị override | Kiểm tra compatibility matrix và dependency tree |
| Swagger UI tài nguyên bị trùng hoặc version lệch | Thêm swagger-ui thủ công cùng UI starter | Bỏ dependency trùng sau khi xác minh |
| Chỉ API group bị lỗi | URL group hoặc security matcher sai | Kiểm tra /v3/api-docs/{group} và quyền truy cập |
| Functional route không xuất hiện trong document | Thiếu metadata route hoặc cấu hình annotation | Dùng @RouterOperation/@RouterOperations theo docs |

## 18. Quy trình lựa chọn trong một project mới

1. Xác định Spring Boot major version.
2. Kiểm tra dependency khởi tạo web server: MVC hay WebFlux.
3. Nếu cả hai có mặt, xác định application type thực tế; nhớ rằng MVC được ưu tiên mặc định.
4. Chọn đúng dòng springdoc tương thích với Spring Boot.
5. Quyết định cần API-only hay Swagger UI.
6. Thêm đúng một starter tương ứng.
7. Không khai báo lại các dependency đã được starter kéo theo nếu không có nhu cầu cụ thể.
8. Chạy dependency tree để phát hiện module hoặc version trùng.
9. Khởi động ứng dụng và kiểm tra /v3/api-docs.
10. Nếu dùng UI starter, kiểm tra /swagger-ui.html và /v3/api-docs/swagger-config.
11. Nếu có Spring Security, xác minh quyền cho tài liệu và API theo policy.
12. Nếu có WebFlux functional routes, khai báo metadata operation và kiểm tra route được sinh ra.

## 19. Tài liệu tham khảo

- [springdoc-openapi – Getting Started](https://springdoc.org/getting-started.html): starter hiện hành, version ví dụ và URL Swagger UI/OpenAPI.
- [springdoc-openapi – Modules](https://springdoc.org/modules.html): phân biệt Web MVC, WebFlux, API-only và UI starters.
- [springdoc-openapi v2 – Getting Started](https://springdoc.org/v2/getting-started.html): starter và version cho Spring Boot 3.
- [springdoc-openapi v2 – Modules](https://springdoc.org/v2/modules.html): artifact MVC/WebFlux API và UI trong dòng v2.
- [springdoc-openapi – Compatibility Matrix](https://springdoc.org/#what-is-the-compatibility-matrix-of-spring-boot-with-springdoc-openapi-): quan hệ major version Spring Boot và springdoc.
- [springdoc-openapi v1 – Getting Started](https://springdoc.org/v1/getting-started.html): artifact của nhánh cũ cho Spring Boot 1.x/2.x.
- [springdoc-openapi – Migrating from v1](https://springdoc.org/v2/migrating-from-springdoc-v1.html): ánh xạ artifact v1 sang starter v2.
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): WebFlux, functional endpoints và hành vi khi cả MVC/WebFlux cùng có trên classpath.
- [Spring Boot – Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): Spring MVC và Servlet stack.

## 20. Tổng kết áp dụng

Hãy chọn webmvc starter nếu server thực tế chạy Spring MVC; chọn webflux starter nếu server chạy Spring WebFlux. Sau đó chọn hậu tố api khi chỉ cần OpenAPI JSON/YAML hoặc hậu tố ui khi cần Swagger UI. Kiểm tra thêm major version Spring Boot để dùng đúng dòng springdoc: 3.x cho Boot 4, 2.x cho Boot 3 và 1.8.0 cho các ứng dụng Boot 1/2 cũ.

Dependency đúng giúp springdoc tích hợp vào đúng web stack, nhưng chưa thay thế việc kiểm tra security, URL sau reverse proxy và contract được sinh ra. Sau khi thêm starter, hãy xác minh /v3/api-docs; nếu đã chọn UI, xác minh thêm Swagger UI và cấu hình swagger-config trước khi đưa tài liệu vào quy trình phát triển.
