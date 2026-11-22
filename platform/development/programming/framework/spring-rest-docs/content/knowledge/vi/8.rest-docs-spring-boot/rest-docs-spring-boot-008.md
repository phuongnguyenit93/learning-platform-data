# Cấu hình profile, port và base URI theo môi trường

## 1. Ba lớp cấu hình cần phân biệt

Trong chương Spring Boot của học phần SPRING_REST_DOCS, bài này hướng dẫn tách cấu hình môi trường ứng dụng, địa chỉ client thực tế và URI được Spring REST Docs ghi vào snippet. Ba lớp này có mục đích khác nhau và không nên dùng thay thế nhau.

| Lớp | Ví dụ | Tác động |
| --- | --- | --- |
| Profile ứng dụng | @ActiveProfiles("test"), application-test.yml | Chọn bean và property khi tạo Spring context. |
| HTTP client | @SpringBootTest(RANDOM_PORT), @LocalServerPort | Chọn server và cổng mà request thực sự gọi. |
| URI trong snippet | uriScheme, uriHost, uriPort | Chọn URL hiển thị trong tài liệu, không đổi server thật. |

Sau bài học, bạn có thể chọn profile test, khởi động embedded server bằng RANDOM_PORT, cấu hình base URI của WebTestClient/REST Assured, tùy biến URL snippet và đưa các cấu hình này vào CI an toàn.

Ví dụ dùng Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter và Java 17+. Với Boot 4.x, cần dùng package/module test đúng major version.

## 2. Profile cho môi trường kiểm thử

Spring profile cho phép ứng dụng chọn cấu hình khi tạo ApplicationContext. Trong test, @ActiveProfiles("test") yêu cầu Spring Test kích hoạt profile test.

File application-test.yml có thể chứa cấu hình riêng:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:catalog-test;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
  jpa:
    hibernate:
      ddl-auto: create-drop
```

Đây là ví dụ cho H2 và JPA; bỏ property không liên quan nếu project không dùng chúng. Không sao chép credential production vào profile test.

```java
@SpringBootTest
@ActiveProfiles("test")
class CatalogApplicationTest {
    // ...
}
```

Khi cần override một vài property cho một test class, dùng @SpringBootTest(properties = {...}) hoặc @TestPropertySource(properties = {...}). Test nên khai báo profile rõ ràng, không dựa vào profile đang bật trong shell của developer.

## 3. Cổng server: RANDOM_PORT và @LocalServerPort

| Chế độ | Hành vi | Server lắng nghe port? |
| --- | --- | --- |
| MOCK | Web application context dạng mock. | Không |
| RANDOM_PORT | Khởi động embedded server trên port được cấp động. | Có |
| DEFINED_PORT | Khởi động server trên port cấu hình. | Có |
| NONE | Không khởi động web environment. | Không |

Với CI và test chạy song song, RANDOM_PORT thường an toàn hơn DEFINED_PORT vì không yêu cầu port 8080 luôn rảnh.

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class CatalogHttpIntegrationTest {
    @LocalServerPort
    int port;
}
```

Spring Boot chọn port khi server khởi động; @LocalServerPort nhận port thực. Không hard-code 8080. Nếu tự dựng REST Assured hoặc HTTP client khác, đưa port được inject vào cấu hình client.

## 4. Base URI của HTTP client

Với WebFlux, @AutoConfigureWebTestClient cung cấp WebTestClient. Khi kết hợp @SpringBootTest(RANDOM_PORT), client được Boot cấu hình để gọi embedded server.

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@AutoConfigureWebTestClient
@AutoConfigureRestDocs(outputDir = "build/generated-snippets/status-http")
class StatusHttpDocumentationTest {
    @Autowired
    WebTestClient client;

    @Test
    void status() {
        client.get().uri("/api/status")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("UP")
            .consumeWith(document("status-get"));
    }
}
```

Nếu dùng WebTestClient.bindToController(...) hoặc bindToApplicationContext(...), client bind trực tiếp vào controller/context; đó không phải bằng chứng HTTP qua cổng server.

Với REST Assured, cấu hình RequestSpecification bằng port đã inject:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@ExtendWith(RestDocumentationExtension.class)
class StatusRestAssuredDocumentationTest {
    @LocalServerPort
    int port;
    RequestSpecification spec;

    @BeforeEach
    void configure(RestDocumentationContextProvider context) {
        spec = new RequestSpecBuilder()
            .setBaseUri("http://localhost")
            .setPort(port)
            .addFilter(documentationConfiguration(context))
            .build();
    }
}
```

Base URI thực tế là http://localhost:<port-ngẫu-nhiên>. Dependency cần có spring-restdocs-restassured. Cấu hình filter REST Docs thủ công tường minh; không trộn với auto-configuration trên cùng client.

## 5. URI hiển thị trong snippet

```java
@AutoConfigureRestDocs(
    outputDir = "build/generated-snippets/catalog-http",
    uriScheme = "https",
    uriHost = "api.example.com",
    uriPort = 443
)
```

Giả sử request thực đi tới http://localhost:53127/api/catalog, snippet có thể hiển thị https://api.example.com/api/catalog. uriScheme, uriHost và uriPort chỉ thay URI được ghi; chúng không bật TLS, không đổi port server và không thay base URL của client.

Với từng operation, có thể dùng modifyUris() làm operation preprocessor để đổi host/schema trong bản ghi tài liệu. Xác minh snippet sau khi thay đổi và chú ý giữ base path đúng.

## 6. Context path và base path

Với Spring MVC servlet, server.servlet.context-path đặt prefix runtime. Với WebFlux, property tương ứng là spring.webflux.base-path.

```yaml
server:
  servlet:
    context-path: /catalog
```

Khi controller có @GetMapping("/products"), URL đầy đủ của servlet app là /catalog/products. Client cần gọi đúng prefix. Nếu base URL của client đã chứa context path thì không thêm prefix lần nữa trong URI. Cấu hình context path là routing thật, khác với uriHost/uriScheme/uriPort chỉ dùng để trình bày snippet.

Nếu production chạy sau reverse proxy với prefix /gateway/catalog trong khi ứng dụng nội bộ phục vụ /catalog, việc rewrite thuộc gateway/deployment. Có thể preprocess URI snippet để mô tả URL public, nhưng cần integration test riêng nếu muốn xác minh gateway thực sự.

## 7. Property có giá trị động

Khi database container hoặc mock server có port động, dùng @DynamicPropertySource để đưa giá trị vào Spring Environment thay vì hard-code trong application-test.yml.

```java
@DynamicPropertySource
static void partnerProperties(DynamicPropertyRegistry registry) {
    registry.add("partner.base-url", () -> partnerServer.url("/").toString());
}
```

Ví dụ giả định MockWebServer đã được khởi động trước khi Spring context đọc dynamic property. Với Testcontainers, có thể đăng ký supplier như container::getJdbcUrl sau khi container được khởi tạo.

Phân biệt @LocalServerPort (port của ứng dụng), @DynamicPropertySource (port/URL của dependency ngoài) và @AutoConfigureRestDocs(uriPort=...) (port trình bày trong snippet).

## 8. Kết hợp profile và REST Docs

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@AutoConfigureRestDocs(
    outputDir = "build/generated-snippets/catalog-http",
    uriScheme = "https",
    uriHost = "api.example.com",
    uriPort = 443
)
class CatalogHttpDocumentationTest {
    // Inject client, gửi request tới embedded server, rồi document(...).
}
```

Profile chọn cấu hình runtime; RANDOM_PORT khởi động embedded server; client gửi request tới server thực; outputDir chọn nơi ghi snippet; uriScheme/uriHost/uriPort chỉ chọn URI hiển thị trong snippet.

## 9. Gradle, Maven và CI

Với Gradle, outputDir và input của Asciidoctor phải trùng nhau:

```groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets/catalog-http')

tasks.named('test') {
    useJUnitPlatform()
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir.get().asFile
}
```

Nếu HTTP test nằm trong task integrationTest, Asciidoctor phải phụ thuộc task đó. Với Maven, nếu outputDir là target/generated-snippets/catalog-http, attribute snippets cần trỏ tới thư mục tương ứng dưới project.build.directory. Hãy chạy Asciidoctor sau nhóm test sinh snippet; prepare-package phù hợp với test chạy phase test, nhưng không phù hợp nếu snippet chỉ được tạo ở Failsafe verify.

CI nên chạy test và dựng tài liệu trong cùng pipeline. Ví dụ: ./gradlew clean test asciidoctor. Cấp secret và endpoint phụ thuộc qua secret store/environment hoặc mock service; không commit token, mật khẩu production hoặc URL nội bộ nhạy cảm vào profile test.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test dùng nhầm profile production | Thiếu @ActiveProfiles("test") hoặc biến môi trường tác động. | Kích hoạt profile rõ ràng, kiểm tra property trong test context. |
| @LocalServerPort không inject được | Không chạy RANDOM_PORT/DEFINED_PORT. | Dùng @SpringBootTest(RANDOM_PORT) với web stack. |
| REST Assured gọi sai port | Hard-code 8080 hoặc thiếu port inject. | Dùng @LocalServerPort và setPort(port). |
| Snippet ghi localhost:random-port | REST Docs ghi URI test server. | Đặt uriScheme, uriHost, uriPort. |
| Snippet có host public nhưng request gửi host đó | Nhầm URI snippet với base URL client. | Giữ client trỏ test server; cấu hình REST Docs riêng. |
| Context path lặp hai lần | Prefix có trong base URL và request path. | Chỉ thêm prefix một lần. |
| Dynamic property dùng port chưa sẵn sàng | Container/mock server chưa start. | Khởi động resource trước context. |
| Asciidoctor không tìm snippet | outputDir và attribute snippets khác nhau. | Đồng bộ hai đường dẫn và operation ID. |

## 11. Bài thực hành

Tạo API Catalog và hoàn thành:

1. Tạo application-test.yml với database/property dành riêng cho test; bật @ActiveProfiles("test").
2. Dùng @SpringBootTest(RANDOM_PORT), lấy port qua @LocalServerPort.
3. Gửi request bằng WebTestClient nếu WebFlux hoặc REST Assured nếu REST Assured; kiểm tra status, JSON và header.
4. Cấu hình snippet hiển thị https://api.example.com trong khi client vẫn gọi embedded server local.
5. Thêm context path, quan sát URL client và snippet; xác nhận prefix không lặp.
6. Dùng @DynamicPropertySource cấp URL mock server hoặc JDBC URL Testcontainers.
7. Chạy build sạch và Asciidoctor trong CI; xác nhận snippet mới, không có secret và không chứa port ngẫu nhiên ngoài ý muốn.

**Tiêu chí hoàn thành:** phân biệt profile, client base URI và URI snippet; test dùng port động; tài liệu hiển thị URL đúng; base path chỉ xử lý một lần; không có secret production trong snippet; CI tái tạo tài liệu độc lập với máy phát triển.

## 12. Tài liệu tham khảo

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html)
- [Spring Boot 3.5 — AutoConfigureRestDocs API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/restdocs/AutoConfigureRestDocs.html)
- [Spring Boot 3.5 — LocalServerPort API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/server/LocalServerPort.html)
- [Spring REST Docs — Configuration: Documented URIs](https://docs.spring.io/spring-restdocs/reference/configuration/uris.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
