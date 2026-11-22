# Starter chỉ cung cấp đặc tả so với starter kèm giao diện

springdoc-openapi có hai nhóm starter chính cho mỗi kiểu ứng dụng Spring: starter chỉ cung cấp OpenAPI document và starter tích hợp thêm Swagger UI. Chọn đúng artifact giúp kiểm soát dependency, kích thước ứng dụng, bề mặt triển khai và cách người dùng xem tài liệu.

Hai nhóm này đều có thể tạo OpenAPI JSON/YAML từ controller, model và annotation. Khác biệt quan trọng là starter có giao diện sẽ đóng gói thêm Swagger UI cùng tài nguyên web cần thiết để hiển thị và tương tác với document.

Bài này so sánh các artifact Spring MVC và WebFlux, cách chọn theo môi trường, dependency Maven/Gradle, endpoint được cung cấp, cấu hình, bảo mật, triển khai và kiểm thử sau khi thay starter.

## 1. Phân biệt hai vai trò

Một ứng dụng springdoc có thể cung cấp hai khả năng độc lập:

- **Sinh đặc tả:** phân tích Spring controller, mapping, DTO, validation và OpenAPI annotations để tạo document.
- **Hiển thị đặc tả:** cung cấp giao diện web để người dùng duyệt operation, xem schema, nhập credential và thử request.

Starter API chỉ cung cấp khả năng sinh đặc tả. Starter UI cung cấp cả sinh đặc tả và giao diện Swagger UI.

~~~text
                  Spring Boot application
                           |
                    springdoc integration
                           |
                 Generate OpenAPI document
                           |
                 /v3/api-docs (JSON/YAML)
                           |
             +-------------+-------------+
             |                           |
        API starter                 UI starter
             |                           |
       OpenAPI document          OpenAPI document
             |                           |
    External portal/client       Swagger UI assets
    generator/CI consumer         /swagger-ui/**
                                         |
                                   Try it out
                                         |
                                    API endpoints
~~~

Không nên xem Swagger UI là thành phần bắt buộc để tạo OpenAPI. Một pipeline có thể xuất document cho API portal hoặc code generator mà không cần giao diện nằm trong ứng dụng.

## 2. Bốn artifact chính

springdoc cung cấp starter tương ứng với Spring MVC và Spring WebFlux:

| Nền tảng | Chỉ sinh OpenAPI | Sinh OpenAPI và kèm Swagger UI |
|---|---|---|
| Spring MVC | `springdoc-openapi-starter-webmvc-api` | `springdoc-openapi-starter-webmvc-ui` |
| Spring WebFlux | `springdoc-openapi-starter-webflux-api` | `springdoc-openapi-starter-webflux-ui` |

Các artifact thuộc group `org.springdoc`.

Ví dụ tọa độ Maven:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

Bản UI thay artifact bằng:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

Với WebFlux, thay `webmvc` bằng `webflux`.

Không thêm cả hai starter API và UI cùng nền tảng chỉ để có đủ tính năng. Starter UI đã bao gồm phần tích hợp API document cần thiết; thêm API starter song song thường là dependency dư thừa.

## 3. Chọn starter theo Spring MVC hay WebFlux

Trước khi quyết định có Swagger UI hay không, xác định web stack của ứng dụng.

**Spring MVC** thường dùng:

- `spring-boot-starter-web`.
- `@RestController` với Servlet stack.
- `springdoc-openapi-starter-webmvc-api` hoặc `webmvc-ui`.

**Spring WebFlux** thường dùng:

- `spring-boot-starter-webflux`.
- Controller reactive hoặc functional routes.
- `springdoc-openapi-starter-webflux-api` hoặc `webflux-ui`.

Không chọn WebFlux starter chỉ vì một service method trả về `Mono` hoặc `Flux`. Hãy xác định web application type thực tế và dependency nền tảng mà Spring Boot khởi tạo.

Một ứng dụng nên dùng starter phù hợp với web stack đã chọn. Tránh đưa đồng thời MVC và WebFlux starter vào cùng classpath nếu không có kiến trúc hỗn hợp được thiết kế và kiểm tra rõ ràng.

## 4. API starter cung cấp những gì?

API starter tích hợp springdoc với Spring để tạo OpenAPI document. Các endpoint mặc định thường dùng:

~~~text
GET /v3/api-docs
GET /v3/api-docs.yaml
~~~

JSON document mô tả:

- Phiên bản OpenAPI.
- Thông tin API trong `info`.
- Server URL.
- Paths và operations.
- Parameters.
- Request bodies.
- Responses và status codes.
- Components và schemas.
- Security schemes và requirements.
- Tags, examples và extensions.

API starter không đóng gói giao diện Swagger UI. Vì vậy, ứng dụng vẫn có thể cung cấp tài liệu máy đọc được cho portal, generator hoặc công cụ kiểm thử mà không cần tài nguyên giao diện.

API starter không có nghĩa OpenAPI là file tĩnh. Document vẫn có thể được sinh động từ controller và cấu hình tại runtime, trừ khi pipeline chủ động export thành artifact tĩnh.

## 5. UI starter cung cấp thêm những gì?

UI starter bao gồm tích hợp OpenAPI document và tài nguyên Swagger UI. Các đường dẫn mặc định thường gặp:

~~~text
/swagger-ui.html
/swagger-ui/index.html
/v3/api-docs
/v3/api-docs.yaml
~~~

Đường dẫn `/swagger-ui.html` thường chuyển hướng tới trang UI thực tế. URL cụ thể có thể thay đổi theo cấu hình, context path hoặc reverse proxy.

Swagger UI cho phép:

- Duyệt tag và operation.
- Xem parameter, request body và response schema.
- Xem ví dụ request/response.
- Sử dụng nút Authorize để nhập credential.
- Thử gọi API bằng Try it out.
- Chọn server được khai báo trong OpenAPI document.
- Duyệt nhiều document nếu được cấu hình.

UI starter không thay thế Spring Security, authentication server hay authorization của API. Nó chỉ cung cấp giao diện tương tác với contract và gửi request tới endpoint theo cấu hình.

## 6. Khác biệt về dependency footprint

UI starter phải mang thêm dependency và tài nguyên web để phục vụ giao diện. Thông thường dependency tree sẽ có WebJar `swagger-ui` cùng các thành phần tích hợp UI.

API starter có footprint nhỏ hơn vì không cần đóng gói Swagger UI assets.

| Khía cạnh | API starter | UI starter |
|---|---|---|
| OpenAPI JSON/YAML | Có | Có |
| Sinh document từ Spring | Có | Có |
| Swagger UI assets | Không | Có |
| Trang duyệt API tích hợp | Không | Có |
| Try it out tích hợp | Không | Có |
| Dependency WebJar Swagger UI | Không cần | Có |
| Dùng với API portal bên ngoài | Phù hợp | Vẫn dùng được |
| Phù hợp ứng dụng chỉ xuất contract | Phù hợp | Thường dư dependency |

Kích thước tăng thực tế phụ thuộc phiên bản, dependency management và cách đóng gói. Hãy kiểm tra dependency tree hoặc executable archive thay vì ước lượng theo tên artifact.

## 7. Khi nào chọn API starter?

Chọn API starter khi ứng dụng chỉ cần công bố OpenAPI document cho consumer hoặc pipeline khác.

Các tình huống phổ biến:

- CI khởi động ứng dụng, tải `/v3/api-docs` rồi validate contract.
- OpenAPI Generator dùng document để sinh SDK.
- API portal tập trung của tổ chức đọc JSON/YAML từ nhiều service.
- Tài liệu được lưu trong artifact repository hoặc Git.
- Swagger UI được host ở một web application riêng.
- Production chỉ công bố contract cho hệ thống nội bộ được kiểm soát.
- Muốn giảm dependency và không cần giao diện trong service.

Ví dụ, một microservice có thể xuất OpenAPI JSON qua endpoint nội bộ; API portal riêng chịu trách nhiệm hiển thị tài liệu cho developer.

Trong mô hình này, service vẫn cần bảo đảm document chính xác, có version và được bảo vệ đúng chính sách. Không có Swagger UI không có nghĩa endpoint OpenAPI nên được mở công khai mặc định.

## 8. Khi nào chọn UI starter?

Chọn UI starter khi người dùng cần truy cập tài liệu tương tác ngay trong ứng dụng Spring Boot.

Các trường hợp thường gặp:

- Developer cần thử endpoint trong môi trường local.
- QA cần xem schema và gửi request thủ công.
- Ứng dụng nội bộ có nhóm API nhỏ và chưa có portal tập trung.
- Demo hoặc sandbox cần giao diện tài liệu đi kèm.
- Nhóm vận hành cần kiểm tra operation và authentication trong môi trường kiểm thử.

UI tích hợp giúp giảm công việc triển khai một trang tài liệu riêng. Tuy nhiên, production cần cân nhắc ai được truy cập UI, document và các operation được mô tả.

Nếu giao diện chỉ cần trong local/dev, có thể bật UI ở profile đó và tắt hoặc không đóng gói UI trong artifact production.

## 9. Maven: cấu hình API-only cho Spring MVC

Ví dụ dependency API-only:

~~~xml
<properties>
    <springdoc.version>2.x.y</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
~~~

Dùng version tương thích với Spring Boot đang sử dụng. Placeholder `2.x.y` trong ví dụ minh họa dòng springdoc dành cho Spring Boot 3; với Spring Boot 4, chọn dòng springdoc 3.x. Trong cả hai trường hợp, thay placeholder bằng release cụ thể được quản lý trong dự án.

Với cấu hình này, ứng dụng có thể sinh OpenAPI JSON/YAML. Không có Swagger UI tích hợp nếu không có dependency UI khác được thêm vào.

## 10. Maven: cấu hình UI cho Spring MVC

Nếu cần Swagger UI, dùng artifact UI:

~~~xml
<properties>
    <springdoc.version>2.x.y</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
~~~

Không cần khai báo thêm `springdoc-openapi-starter-webmvc-api` để có `/v3/api-docs`. UI starter đã cung cấp tích hợp API document.

Không tự thêm `org.webjars:swagger-ui` với version tùy ý nếu starter đã quản lý dependency đó. Ghi đè WebJar có thể tạo ra khác biệt giữa springdoc và phiên bản Swagger UI được đóng gói.

## 11. Maven: cấu hình cho Spring WebFlux

API-only:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-api</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

Kèm UI:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

Giữ `spring-boot-starter-webflux` làm web stack của ứng dụng. Không thêm `spring-boot-starter-web` chỉ để Swagger UI hoạt động; UI starter của WebFlux được thiết kế cho stack reactive tương ứng.

## 12. Gradle: API-only và UI starter

Với Gradle Groovy DSL, API-only:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation "org.springdoc:springdoc-openapi-starter-webmvc-api:$springdocVersion"
}
~~~

UI:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation "org.springdoc:springdoc-openapi-starter-webmvc-ui:$springdocVersion"
}
~~~

Với Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation(
        "org.springdoc:springdoc-openapi-starter-webmvc-api:$springdocVersion"
    )
}
~~~

Để chuyển sang UI, thay artifact `webmvc-api` bằng `webmvc-ui`.

Khai báo version ở một nơi dùng chung, chẳng hạn version catalog hoặc Gradle property. Không để các module trong cùng ứng dụng kéo các version springdoc khác nhau.

## 13. Cấu hình endpoint OpenAPI

Có thể thay đổi đường dẫn document:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
~~~

Khi đó endpoint JSON mặc định chuyển thành:

~~~text
/openapi
~~~

Endpoint YAML tương ứng được phục vụ theo cấu hình path và extension mà phiên bản springdoc hỗ trợ, thường là `/openapi.yaml`.

Thuộc tính `springdoc.api-docs.enabled` điều khiển việc cung cấp API docs:

~~~yaml
springdoc:
  api-docs:
    enabled: true
~~~

Nếu đặt `false`, endpoint OpenAPI bị tắt. Khi đó Swagger UI mặc định không thể tải document từ endpoint này trừ khi được cấu hình đọc một OpenAPI URL khác.

Đừng đổi path mà quên cập nhật CI script, API portal, security matcher và Swagger UI config.

## 14. Cấu hình Swagger UI

Các thuộc tính giao diện nằm dưới `springdoc.swagger-ui`:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    path: /docs
    operations-sorter: alpha
    tags-sorter: alpha
    display-operation-id: true
~~~

`enabled` bật/tắt Swagger UI khi UI starter hiện diện. `path` tùy chỉnh đường dẫn truy cập giao diện; các sorter điều khiển thứ tự hiển thị.

Nếu dùng API-only starter, đặt `springdoc.swagger-ui.enabled=true` không tự thêm Swagger UI dependency hoặc static assets. Cấu hình chỉ có tác dụng khi phần UI đã có trong runtime classpath.

Có thể tắt UI nhưng vẫn giữ OpenAPI endpoint:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: true
~~~

Cấu hình này hữu ích khi dùng UI starter trong profile cần document nhưng không muốn phục vụ giao diện. Nếu muốn loại dependency UI khỏi production artifact, dùng API starter cho artifact production sẽ rõ ràng hơn.

## 15. Swagger UI đọc document ở đâu?

Theo mặc định, Swagger UI tích hợp đọc OpenAPI document do cùng ứng dụng springdoc cung cấp, thường là `/v3/api-docs`.

Nếu UI được host riêng, nó có thể tải spec từ một URL khác:

~~~yaml
springdoc:
  swagger-ui:
    url: https://docs.example.com/contracts/orders/openapi.json
~~~

Khi dùng URL ngoài, kiểm tra:

- Browser có truy cập được host đó không.
- CORS có cho phép tải document không.
- URL có cần authentication không.
- TLS certificate có hợp lệ không.
- Spec có server URL đúng với môi trường cần thử không.

Một UI độc lập cũng có thể đọc nhiều document qua cấu hình URL list. API service không nhất thiết phải đóng gói UI chỉ vì tài liệu được xem bằng Swagger UI ở một nơi khác.

## 16. Phân biệt API docs endpoint và Swagger UI endpoint

Hai endpoint có vai trò khác nhau:

| Endpoint | Vai trò | Ai thường sử dụng |
|---|---|---|
| `/v3/api-docs` | OpenAPI JSON | Parser, portal, generator, developer |
| `/v3/api-docs.yaml` | OpenAPI YAML | Người review, tool hỗ trợ YAML |
| `/swagger-ui/index.html` | Tài nguyên giao diện | Developer, QA |
| `/swagger-ui.html` | Đường dẫn tiện dụng/redirect | Người dùng trình duyệt |

API starter cung cấp document endpoint. UI starter bổ sung các đường dẫn giao diện.

Nếu chỉ kiểm tra `/swagger-ui.html`, bạn chưa chứng minh OpenAPI JSON hợp lệ. Nếu chỉ kiểm tra `/v3/api-docs`, bạn chưa chứng minh static assets và UI đã hoạt động.

## 17. Tắt UI trong production

Có thể dùng profile để điều khiển UI:

~~~yaml
# application-dev.yml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
~~~

~~~yaml
# application-prod.yml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

Cấu hình này giữ OpenAPI endpoint trong production nhưng tắt giao diện.

Nếu production không cần endpoint OpenAPI runtime, có thể tắt cả hai:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

Nếu pipeline cần contract artifact, hãy export ở build/test stage trước khi tạo artifact production, hoặc dùng một profile/ứng dụng chuyên phục vụ tài liệu.

Lưu ý: tắt UI bằng property không loại bỏ dependency Swagger UI khỏi executable JAR nếu bạn vẫn đóng gói UI starter. Muốn giảm footprint thực sự, chọn API starter trong build production.

## 18. Bảo vệ API docs và Swagger UI

OpenAPI document có thể tiết lộ:

- Internal path.
- Tên operation và schema.
- Header và security scheme.
- Server URL.
- Error model.
- Các tính năng nội bộ không dành cho public consumer.

Swagger UI còn cho phép người dùng tương tác với API qua Try it out. Vì vậy, cần xác định chính sách truy cập cho cả document và giao diện.

Một số cách bảo vệ:

- Chỉ cho phép truy cập từ mạng nội bộ.
- Yêu cầu authentication cho `/v3/api-docs/**`.
- Bảo vệ `/swagger-ui/**` và đường dẫn UI.
- Dùng profile để không bật UI ở production public.
- Xuất spec đã lọc riêng cho consumer bên ngoài.
- Không đưa endpoint quản trị hoặc thông tin nhạy cảm vào public document.

Ẩn operation bằng `@Hidden` chỉ ảnh hưởng tài liệu; nó không thay thế authorization của endpoint. Security scheme trong OpenAPI cũng chỉ mô tả cơ chế bảo mật, không tự cấu hình Spring Security.

## 19. Spring Security matcher cần bao phủ đúng endpoint

Nếu ứng dụng bảo vệ tài liệu, matcher phải khớp đường dẫn thực tế. Ví dụ cấu hình minh họa:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {

    http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers(
            "/v3/api-docs/**",
            "/swagger-ui/**",
            "/swagger-ui.html"
        ).hasRole("API_DOCS")
        .anyRequest().authenticated()
    );

    return http.build();
}
~~~

Đây chỉ là ví dụ policy. Ứng dụng cần cấu hình authentication, CSRF và các filter phù hợp với cách triển khai thực tế.

Nếu dùng path tùy chỉnh như `/openapi` hoặc `/docs`, cập nhật matcher tương ứng. Nếu UI public nhưng JSON docs được bảo vệ, Swagger UI có thể tải trang thành công nhưng request lấy document bị 401/403.

Không mở toàn bộ `/v3/**` hoặc `/swagger-ui/**` cho anonymous chỉ để UI chạy nếu chính sách yêu cầu xác thực.

## 20. Try it out và CORS

Swagger UI gửi request trực tiếp từ trình duyệt của người dùng tới API server được chọn trong document. Nếu UI và API khác origin, trình duyệt áp dụng CORS.

Các lỗi thường gặp:

- Swagger UI tải được nhưng Try it out bị CORS.
- Preflight OPTIONS bị chặn.
- Authorization header không được cho phép.
- Server URL trong OpenAPI trỏ tới hostname nội bộ.
- Browser không gửi cookie do SameSite hoặc credential policy.

Để khắc phục, cấu hình CORS ở API server hoặc gateway theo origin, method và header thực tế. Không dùng wildcard credentials trong production.

API-only starter không có Try it out tích hợp, nên không phát sinh CORS cho một UI nội bộ trong service. Tuy nhiên, portal/UI bên ngoài vẫn phải tuân theo CORS khi gọi API hoặc tải document trực tiếp từ browser.

## 21. Dùng API starter với API portal tập trung

Một kiến trúc phổ biến là mỗi service xuất OpenAPI JSON, còn một portal riêng tổng hợp tài liệu:

~~~text
orders-service  ---- /v3/api-docs ----+
                                      |
billing-service ---- /v3/api-docs ----+--> API portal
                                      |
catalog-service ---- /v3/api-docs ----+
                                             |
                                      Developer browser
~~~

Các service dùng API starter. Portal có thể:

- Định kỳ lấy spec.
- Nhận artifact từ CI.
- Lưu document theo version.
- Hiển thị nhiều service trong một giao diện.
- Phân quyền theo team hoặc product.
- Tạo SDK từ contract đã được duyệt.

Mô hình này tách trách nhiệm: service sở hữu contract; portal sở hữu trải nghiệm duyệt tài liệu.

Cần tránh để portal lấy một document runtime không ổn định rồi tự coi đó là bản release. Hãy gắn artifact với commit, API version và trạng thái validation.

## 22. Dùng API starter cho CI và code generation

Pipeline có thể khởi động ứng dụng bằng profile CI, tải OpenAPI JSON và chạy validator/generator:

~~~bash
curl -fsS \
  http://localhost:8080/v3/api-docs \
  -o target/openapi.json
~~~

Sau đó:

~~~bash
openapi-generator-cli validate -i target/openapi.json
~~~

Sinh client thử nghiệm:

~~~bash
openapi-generator-cli generate \
  -i target/openapi.json \
  -g java \
  -o target/generated-client
~~~

CI không cần mở Swagger UI để thực hiện các bước này. API starter giúp runtime chỉ chứa phần sinh document cần thiết.

Nếu export nhiều group, tải từng endpoint group và kiểm tra độc lập. Nếu API docs được bảo vệ, pipeline cần credential từ secret store và phải tránh ghi token vào log.

## 23. Kiểm tra dependency tree Maven

Dùng Maven để kiểm tra springdoc và Swagger UI:

~~~bash
mvn dependency:tree \
  -Dincludes=org.springdoc,org.webjars
~~~

Với API-only, không nên thấy WebJar Swagger UI được kéo vào chỉ bởi springdoc starter API.

Với UI starter, dependency tree thường hiển thị artifact `org.webjars:swagger-ui` hoặc dependency UI tương ứng.

Nếu Swagger UI vẫn xuất hiện khi dùng API starter, tìm xem dependency khác có kéo nó vào hay không. Đừng kết luận từ tên dependency trực tiếp; hãy kiểm tra toàn bộ runtime dependency tree.

## 24. Kiểm tra dependency insight Gradle

Với Gradle:

~~~bash
./gradlew dependencyInsight \
  --dependency swagger-ui \
  --configuration runtimeClasspath
~~~

Có thể kiểm tra nhóm springdoc:

~~~bash
./gradlew dependencies \
  --configuration runtimeClasspath
~~~

Dùng output để xác định dependency nào kéo Swagger UI vào runtime. Nếu có nhiều version, xử lý conflict bằng dependency management phù hợp thay vì exclude tùy tiện.

Sau khi thay starter, chạy test và kiểm tra executable archive để chắc rằng UI assets không còn trong artifact API-only.

## 25. Kiểm tra nội dung executable JAR

Với Spring Boot executable JAR, có thể kiểm tra dependency được đóng gói:

~~~bash
jar tf target/application.jar | findstr /i "swagger-ui"
~~~

Nếu dùng API-only và không có dependency khác mang Swagger UI, thường không thấy nested library hoặc tài nguyên Swagger UI.

Với UI starter, kiểm tra `BOOT-INF/lib` để xác nhận WebJar được đóng gói.

Cấu trúc archive phụ thuộc build plugin và packaging. Hãy xem kết quả như một phép xác minh dependency, không dựa vào một tên file cố định cho mọi version.

## 26. Smoke test cho API starter

Với API-only, kiểm tra OpenAPI document:

~~~bash
curl -i http://localhost:8080/v3/api-docs
~~~

Kiểm tra YAML:

~~~bash
curl -i http://localhost:8080/v3/api-docs.yaml
~~~

Kiểm tra nội dung JSON:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs |
  jq '{openapi, info, pathCount: (.paths | length)}'
~~~

API-only không cần test trang Swagger UI vì không cung cấp giao diện. Thay vào đó, test endpoint document, schema quan trọng, security scheme và group.

Nếu endpoint trả 404, kiểm tra starter đúng web stack, `springdoc.api-docs.enabled`, custom path và component scan trước khi kết luận dependency hỏng.

## 27. Smoke test cho UI starter

Với UI starter, kiểm tra cả document và giao diện:

~~~bash
curl -i http://localhost:8080/v3/api-docs
~~~

~~~bash
curl -I http://localhost:8080/swagger-ui/index.html
~~~

Mở URL UI trong trình duyệt và xác minh:

- Trang HTML tải thành công.
- JavaScript/CSS assets không bị 404.
- Document URL được tải thành công.
- Tag và operation xuất hiện.
- Schema và security scheme hiển thị đúng.
- Try it out gửi request tới đúng server.

Nếu HTML trả 200 nhưng UI trống, xem browser console và network tab. Nguyên nhân thường là document URL, security, CORS hoặc static asset chứ không phải việc sinh OpenAPI.

## 28. Integration test cho API-only

Ví dụ WebTestClient:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class OpenApiEndpointTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void publishesOpenApiDocument() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.openapi").exists()
            .jsonPath("$.info.title").isNotEmpty()
            .jsonPath("$.paths").exists();
    }
}
~~~

Test này xác minh API document endpoint hoạt động. Nếu ứng dụng dùng MVC, có thể dùng MockMvc thay WebTestClient.

Không viết test chỉ kiểm tra HTTP 200. Nên xác nhận operation quan trọng, request schema, response schema và security requirement để phát hiện tài liệu rỗng hoặc thiếu metadata.

## 29. Integration test cho UI starter

Test server-side có thể kiểm tra route UI:

~~~java
@Test
void servesSwaggerUiEntryPoint() {
    webTestClient.get()
        .uri("/swagger-ui/index.html")
        .exchange()
        .expectStatus().isOk();
}
~~~

Tùy cấu hình static resource và redirect, có thể cần kiểm tra `/swagger-ui.html` hoặc đường dẫn UI tùy chỉnh. Một test HTTP không xác minh JavaScript đã render đúng trong browser; cần browser smoke test khi UI là tính năng quan trọng.

Giữ riêng test document và test UI để biết lỗi nằm ở generation hay static assets.

## 30. Chuyển từ UI starter sang API starter

Nếu hiện tại dùng UI starter nhưng muốn chỉ cung cấp document:

1. Thay `springdoc-openapi-starter-webmvc-ui` bằng `springdoc-openapi-starter-webmvc-api` hoặc WebFlux tương ứng.
2. Xóa cấu hình Swagger UI không còn dùng.
3. Giữ cấu hình `springdoc.api-docs` cần thiết.
4. Cập nhật security matcher nếu đường dẫn UI không còn tồn tại.
5. Kiểm tra portal hoặc CI vẫn tải `/v3/api-docs`.
6. Kiểm tra dependency tree không còn Swagger UI WebJar.
7. Kiểm tra executable JAR.
8. Chạy integration test cho JSON/YAML.
9. Cập nhật hướng dẫn developer để dùng portal hoặc tài liệu bên ngoài.

Không xóa annotation OpenAPI chỉ vì bỏ UI. Annotation và controller vẫn cần thiết để tạo document.

## 31. Chuyển từ API starter sang UI starter

Nếu cần giao diện tích hợp:

1. Thay artifact API bằng artifact UI cùng web stack.
2. Không giữ cả API và UI starter song song.
3. Kiểm tra dependency version và WebJar.
4. Bật `springdoc.swagger-ui.enabled`.
5. Xác định URL UI và OpenAPI document.
6. Cấu hình authentication/CORS nếu cần.
7. Bảo đảm server URL trong spec trỏ đúng môi trường.
8. Smoke test HTML, assets và document.
9. Test Try it out với endpoint có quyền truy cập.
10. Cập nhật security policy cho UI và docs.

Không cần thay controller, DTO hoặc OpenAPI annotations chỉ vì đổi starter từ API sang UI.

## 32. Quản lý version springdoc và Spring Boot

Starter API và UI phải dùng cùng dòng version springdoc tương thích với Spring Boot.

Quy tắc chọn major version phổ biến:

| Spring Boot | Dòng springdoc thường tương ứng |
|---|---|
| Spring Boot 4.x | springdoc 3.x |
| Spring Boot 3.x | springdoc 2.x |
| Spring Boot 2.x | Nhánh springdoc 1.x; cần kiểm tra trạng thái hỗ trợ và yêu cầu nâng cấp |

Đây là định hướng theo major line. Hãy kiểm tra bảng compatibility và release notes để chọn patch/minor cụ thể, nhất là khi Spring Boot có minor release mới.

Không ghép `webmvc-api` từ một version với `webmvc-ui` từ version khác. Không tự nâng swagger-core hoặc swagger-ui WebJar riêng lẻ nếu chưa xác minh tương thích với springdoc.

## 33. Tránh dependency trùng và xung đột

Các lỗi dependency thường gặp:

- Thêm đồng thời `webmvc-api` và `webmvc-ui`.
- Dùng cả MVC và WebFlux starter mà không chủ ý.
- Giữ Springfox cùng springdoc sau migration.
- Tự thêm swagger-ui WebJar với version khác.
- Override swagger-core/swagger-annotations ngoài dependency management.
- Khai báo springdoc version khác nhau ở các module.

Cách kiểm tra:

~~~bash
mvn dependency:tree -Dverbose
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Giải quyết conflict ở dependency management hoặc version catalog. Không dùng exclusion hàng loạt trước khi hiểu dependency nào cần class hoặc resource bị loại.

## 34. Ứng dụng multi-module

Trong ứng dụng multi-module, starter thường nên được khai báo ở module chạy Spring Boot, nơi sở hữu ApplicationContext và web server.

Ví dụ:

~~~text
orders-parent
  orders-domain
  orders-application
  orders-web
  orders-service
~~~

Module `orders-service` hoặc `orders-web` có thể sở hữu starter web và springdoc. Domain module chỉ chứa model nghiệp vụ, không nên kéo Swagger UI dependency nếu không cần.

Nếu module dùng chung DTO có OpenAPI annotations, dependency annotation có thể được quản lý theo cách riêng, nhưng cần bảo đảm version thống nhất và không kéo web starter vào domain module.

Đừng để mỗi module con khai báo một springdoc starter khác nhau rồi tạo classpath khó dự đoán.

## 35. Dùng UI ngoài ứng dụng

Nếu tổ chức có một Swagger UI hoặc API portal tập trung, các service có thể dùng API-only starter. UI bên ngoài tải document từ URL của service hoặc từ artifact đã xuất.

Khi UI ngoài tải trực tiếp từ service, xem xét:

- CORS cho browser origin.
- Authentication của endpoint document.
- Network route từ browser tới service.
- Public server URL trong OpenAPI.
- TLS và certificate.
- Version của document được hiển thị.
- Cache của portal và CDN.

Nếu portal lấy spec qua backend thay vì browser, CORS có thể không liên quan tới bước tải document, nhưng portal vẫn phải kiểm soát quyền truy cập và tính mới của artifact.

## 36. Chọn artifact cho từng môi trường

Một dự án có thể chọn starter khác nhau theo build variant hoặc module, nhưng cần tránh tạo một runtime classpath không nhất quán.

Các cách thường dùng:

- **Local development:** UI starter để developer thử API.
- **CI export job:** API starter để tải và validate document.
- **Production service:** API starter nếu cần runtime docs; tắt docs nếu policy yêu cầu.
- **Central documentation portal:** API starter ở service và UI ở portal.
- **Sandbox public:** UI starter nếu có chính sách bảo vệ rõ ràng.

Nếu Maven profile hoặc Gradle configuration thay đổi dependency theo môi trường, hãy kiểm tra dependency graph và artifact của từng profile. Chỉ thay property `springdoc.swagger-ui.enabled` không thay thế việc chọn dependency phù hợp nếu mục tiêu là giảm package size.

## 37. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| `/v3/api-docs` chạy nhưng Swagger UI 404 | Đang dùng API starter hoặc UI bị tắt |
| `swagger-ui.enabled=true` nhưng không có UI | Property không tự thêm UI dependency |
| UI tải được nhưng không hiện operation | Document URL sai, docs bị chặn hoặc JSON lỗi |
| HTML UI 200 nhưng JavaScript/CSS 404 | Static assets hoặc reverse proxy path sai |
| API starter vẫn có WebJar Swagger UI | Dependency khác kéo WebJar vào |
| Thêm cả API và UI starter | Dependency dư hoặc version conflict |
| UI gọi API bị CORS | Browser origin khác API origin |
| UI trả 401 khi tải document | Security matcher bảo vệ docs nhưng UI không có credential |
| `/v3/api-docs` 404 | Sai starter web stack, path tùy chỉnh hoặc api-docs bị disable |
| YAML endpoint 404 | Cấu hình endpoint hoặc phiên bản cần kiểm tra |
| API portal hiển thị spec cũ | Portal cache hoặc artifact chưa được cập nhật |
| UI production vẫn được đóng gói dù disable | UI starter vẫn nằm trong runtime dependency |
| MVC/WebFlux bean không hoạt động như dự kiến | Chọn starter không khớp application type |
| Nâng Boot làm lỗi springdoc | Dùng sai major line hoặc patch chưa tương thích |

## 38. Quy trình quyết định

Trước khi thêm dependency, trả lời lần lượt:

1. Ứng dụng đang dùng Spring MVC hay WebFlux?
2. Có cần endpoint OpenAPI JSON/YAML không?
3. Người dùng có cần Swagger UI ngay trong service không?
4. Nếu có UI, nó chỉ dùng ở local/dev hay cả production?
5. Có API portal tập trung hoặc UI ngoài không?
6. Endpoint docs và UI được bảo vệ thế nào?
7. Có cần giảm runtime dependency footprint không?
8. Spring Boot version tương ứng với springdoc major line nào?
9. CI sẽ export và validate document ở bước nào?
10. Test nào xác minh document và UI riêng biệt?

Nếu chỉ cần contract machine-readable, chọn API starter. Nếu cần giao diện tích hợp, chọn UI starter. Nếu đã có portal riêng, thường không cần đóng gói Swagger UI trong từng microservice.

## 39. Checklist trước khi phát hành

- [ ] Đã xác định web stack Spring MVC hoặc WebFlux.
- [ ] Đã chọn đúng artifact API hoặc UI.
- [ ] Không thêm đồng thời API và UI starter cùng stack.
- [ ] Version springdoc tương thích với Spring Boot.
- [ ] Không có Springfox hoặc Swagger UI WebJar dư thừa.
- [ ] API-only vẫn cung cấp OpenAPI JSON/YAML theo yêu cầu.
- [ ] UI starter phục vụ đúng trang và static assets.
- [ ] `springdoc.api-docs.enabled` phù hợp policy.
- [ ] `springdoc.swagger-ui.enabled` được đặt đúng môi trường.
- [ ] Security matcher bảo vệ docs và UI theo chính sách.
- [ ] Server URL và reverse proxy path đúng.
- [ ] CORS được cấu hình nếu UI gọi API khác origin.
- [ ] CI tải và validate OpenAPI document.
- [ ] Group document được kiểm tra nếu có.
- [ ] Dependency tree và executable archive đã được kiểm tra.
- [ ] Có test riêng cho API docs và Swagger UI.
- [ ] Không coi việc ẩn UI là biện pháp bảo vệ API.

## 40. Nguồn tra cứu

- [springdoc-openapi – Documentation](https://springdoc.org/)
- [springdoc-openapi – Getting Started](https://springdoc.org/#getting-started)
- [springdoc-openapi – Configuration Properties](https://springdoc.org/properties.html)
- [springdoc-openapi – FAQ](https://springdoc.org/faq.html)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [Swagger UI – Usage](https://swagger.io/docs/open-source-tools/swagger-ui/usage/installation/)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [Spring Boot – Managing Dependencies](https://docs.spring.io/spring-boot/reference/using/build-systems.html)

API starter và UI starter cùng sinh OpenAPI document; UI starter bổ sung Swagger UI assets và các đường dẫn giao diện. Chọn API-only khi contract được tiêu thụ bởi CI, SDK generator hoặc portal tập trung. Chọn UI khi cần trải nghiệm duyệt và thử API ngay trong service. Luôn khớp starter với MVC/WebFlux, quản lý version theo Spring Boot, kiểm tra dependency tree và bảo vệ riêng document endpoint lẫn giao diện.
