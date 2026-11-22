# Hoàn thiện bộ kiểm thử hợp đồng, lỗi và cấu hình triển khai

## Mục tiêu

Một API Spring Data REST có thể hoạt động đúng ở máy phát triển nhưng vẫn phá vỡ client khi thay đổi đường dẫn, relation HAL, media type, status code, cấu trúc lỗi hoặc cấu hình triển khai. Bộ kiểm thử hoàn chỉnh cần khóa các hành vi công khai đó và xác minh ứng dụng khởi động đúng với cấu hình của từng môi trường.

Bài này kết hợp năm phần:

1. Kiểm thử hợp đồng HTTP/HAL bằng MockMvc.
2. Sinh tài liệu API từ kiểm thử bằng Spring REST Docs.
3. Chuẩn hóa và kiểm tra phản hồi lỗi.
4. Quản lý profile, cấu hình ngoài artifact, secret và health endpoint khi triển khai.
5. Kiểm thử tích hợp với cơ sở dữ liệu thật bằng Testcontainers; bổ sung Spring Cloud Contract khi có service consumer độc lập.

Ví dụ dùng Java, JUnit Jupiter, Spring Boot, Spring Data REST và Spring Data JPA. Hãy dùng Spring Boot BOM và Spring Cloud release train tương thích với phiên bản Boot của dự án; không tự ghép các version mới nhất của từng thư viện.

## 1. Xác định hợp đồng API cần bảo vệ

Hợp đồng HTTP là tập hợp những gì client quan sát được qua request và response. Với Spring Data REST, hợp đồng thường gồm:

- URI gốc, base path, collection path và item path.
- HTTP methods được hỗ trợ: GET, POST, PUT, PATCH, DELETE.
- Content negotiation: request Accept, Content-Type và media type trả về.
- Status code, Location, ETag và các header có ý nghĩa với client.
- HAL link relation như self, search, profile, next và tên relation trong _embedded.
- Tên trường, kiểu dữ liệu, nullability, projection và cấu trúc representation.
- Quy tắc phân trang, sắp xếp, tìm kiếm và association.
- Cách xử lý validation, resource không tồn tại, xung đột và lỗi xác thực/phân quyền.

Để relation ổn định, khai báo rõ collection path và relation khi đó là một phần của hợp đồng:

~~~java
@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people"
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Nếu client đang phụ thuộc vào relation **people**, việc đổi relation thành **persons** có thể phá client ngay cả khi endpoint vẫn trả HTTP 200. Tương tự, đổi field, projection, media type hoặc status code cũng là thay đổi hợp đồng.

Nên kiểm tra các hành vi mà client thật sự dùng. Tránh khóa các chi tiết ngẫu nhiên như ID sinh tự động, thứ tự field JSON, hostname của môi trường CI hoặc timestamp không có ý nghĩa nghiệp vụ.

## 2. Kiểm thử hợp đồng bằng MockMvc

MockMvc gọi đầy đủ Spring MVC request handling thông qua DispatcherServlet và request/response giả lập, không cần chạy HTTP server. Nó phù hợp để kiểm tra mapping, data binding, message conversion, validation, exception handler và response của Spring Data REST trong application context.

Ví dụ dưới đây giả định ứng dụng cấu hình base path là **/api** và collection relation là **people**:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PeopleApiContractTest {

    private static final MediaType HAL_JSON =
        MediaType.parseMediaType("application/hal+json");

    @Autowired
    private MockMvc mvc;

    @Autowired
    private PersonRepository people;

    @Test
    void rootPublishesPeopleRelation() throws Exception {
        mvc.perform(get("/api").accept(HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(HAL_JSON))
            .andExpect(jsonPath("$._links.people.href").exists());
    }

    @Test
    void collectionUsesExpectedHalRelation() throws Exception {
        mvc.perform(get("/api/people").accept(HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$.page.size").exists());
    }

    @Test
    void createsPersonAndReturnsLocation() throws Exception {
        String email = "contract-" + UUID.randomUUID() + "@example.test";

        mvc.perform(post("/api/people")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(HAL_JSON)
                .content("""
                    {
                      "name": "Mai",
                      "email": "%s"
                    }
                    """.formatted(email)))
            .andExpect(status().isCreated())
            .andExpect(header().exists(HttpHeaders.LOCATION));

        assertThat(people.existsByEmail(email)).isTrue();
    }

    @Test
    void unknownItemReturnsNotFound() throws Exception {
        mvc.perform(get("/api/people/999999999").accept(HAL_JSON))
            .andExpect(status().isNotFound());
    }
}
~~~

Ví dụ dùng **PersonRepository.existsByEmail(...)** để kiểm tra persistence; bổ sung finder method tương ứng nếu repository chưa có. Kiểm thử tạo mới nên dùng dữ liệu duy nhất để các lần chạy không phụ thuộc nhau.

Khi chạy test trong ứng dụng thật, hãy bổ sung import tĩnh cho MockMvc request builders, result matchers, JSONPath, AssertJ và các lớp Spring cần thiết. Đoạn mã minh họa hành vi cần kiểm tra; endpoint, entity và validator phải khớp cấu hình dự án.

### Kiểm tra lỗi và content negotiation

Một bộ contract test nên có ít nhất các trường hợp sau:

| Tình huống | Request | Hành vi cần khẳng định |
|---|---|---|
| Đọc root | GET /api, Accept HAL JSON | 200, media type HAL, relation công khai tồn tại |
| Đọc collection | GET /api/people | 200, _embedded relation và page metadata đúng |
| Tạo hợp lệ | POST với JSON hợp lệ | 201, Location trỏ đến item vừa tạo |
| Dữ liệu sai | POST hoặc PATCH không đạt validation | Lỗi client, thường 400; dữ liệu không hợp lệ không được lưu |
| Item không tồn tại | GET /api/people/{id-không-tồn-tại} | 404 |
| Media type không hỗ trợ | POST với Content-Type không được hỗ trợ | 415 |
| Accept không được hỗ trợ | GET với Accept không có representation phù hợp | 406 |
| Method không được export | Gọi method không hỗ trợ trên resource | 405 |
| Thiếu xác thực | Request tới resource được bảo vệ | 401 theo security configuration |
| Không đủ quyền | User đã xác thực nhưng thiếu authority | 403 theo security configuration |
| Xung đột nghiệp vụ | Lệnh không hợp lệ với trạng thái hiện tại | 409 nếu API quy định conflict |
| Sai precondition | If-Match không còn khớp | 412 nếu API dùng conditional request |

Status cụ thể phụ thuộc cấu hình Spring Security, validation, exception handler và loại endpoint. Test phải ghi nhận hợp đồng thực tế đã chọn cho ứng dụng, không mặc định mọi lỗi đều là 400.

Khi kiểm tra HAL, hãy xác nhận relation trong **_links** và **_embedded**. Không hard-code toàn bộ absolute URL nếu host hoặc context path thay đổi giữa local, CI và production. Nếu cần kiểm tra đường dẫn, so sánh path hoặc dùng matcher theo suffix.

Với pagination, tạo đủ dữ liệu để có nhiều trang rồi kiểm tra page size, page number, sort và link next/prev. Với search resource, kiểm tra cả relation search lẫn query parameter. Với association, xác minh URI liên kết và media type của request.

## 3. Sinh tài liệu hợp đồng bằng Spring REST Docs

Spring REST Docs tạo tài liệu từ những request/response đã được kiểm thử. Khi endpoint đổi status, header hoặc body, test và snippet sẽ cùng báo thay đổi. Cách này giúp tài liệu phản ánh hành vi thực tế.

Thêm dependency test:

~~~xml
<dependency>
    <groupId>org.springframework.restdocs</groupId>
    <artifactId>spring-restdocs-mockmvc</artifactId>
    <scope>test</scope>
</dependency>
~~~

Dùng dependency management của dự án hoặc khai báo version Spring REST Docs tương thích nếu BOM không quản lý nó.

Ví dụ test tạo snippet mặc định:

~~~java
@ExtendWith(RestDocumentationExtension.class)
@SpringBootTest
class PeopleDocumentationTest {

    private static final MediaType HAL_JSON =
        MediaType.parseMediaType("application/hal+json");

    @Autowired
    private WebApplicationContext context;

    private MockMvc mvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        this.mvc = MockMvcBuilders.webAppContextSetup(context)
            .apply(documentationConfiguration(documentation))
            .build();
    }

    @Test
    void documentsPeopleCollection() throws Exception {
        mvc.perform(get("/api/people").accept(HAL_JSON))
            .andExpect(status().isOk())
            .andDo(document("people-collection"));
    }
}
~~~

Spring REST Docs mặc định tạo các snippet như curl-request, http-request, http-response, request-body và response-body. Có thể bổ sung snippet cho request fields, response fields và HAL links khi muốn tài liệu mô tả rõ từng trường và relation.

Trong tài liệu Asciidoctor, include snippet được sinh trong thư mục output của test, ví dụ:

~~~asciidoc
== People collection

include::{snippets}/people-collection/http-request.adoc[]
include::{snippets}/people-collection/http-response.adoc[]
~~~

Đưa bước chạy test và build tài liệu vào CI. Nếu snippet không được sinh, build tài liệu phải thất bại thay vì phát hành tài liệu cũ. Không sửa thủ công file generated snippets; cập nhật test và chạy lại để tái tạo.

### Khi nào dùng Spring Cloud Contract

MockMvc contract tests và Spring REST Docs phù hợp để bảo vệ API của chính ứng dụng. Khi có service consumer độc lập, Spring Cloud Contract bổ sung consumer-driven contracts:

- Producer định nghĩa request/response contract.
- Plugin tạo test phía producer để xác minh implementation đáp ứng contract.
- Stubs được đóng gói và publish để consumer dùng trong integration test.
- Stub Runner tải stub và chạy HTTP stub server cho các service cộng tác.

Ví dụ contract HTTP tối giản có thể khai báo method, path, header và status:

~~~yaml
description: read the people collection
request:
  method: GET
  url: /api/people
  headers:
    Accept: application/hal+json
response:
  status: 200
  headers:
    Content-Type: application/hal+json
~~~

Cú pháp chi tiết và matcher có thể mở rộng theo DSL Groovy hoặc YAML của Spring Cloud Contract. Nếu dự án dùng Spring Cloud Contract, import đúng Spring Cloud BOM tương thích với Spring Boot; không chỉ thêm một version plugin tùy ý.

Spring Cloud Contract không thay thế test HAL representation trong ứng dụng. Hãy giữ test xác minh relation, embedded resource, media type và pagination ở producer. Dùng stub cho consumer để consumer không phải khởi động toàn bộ hệ thống phụ thuộc.

## 4. Thiết kế hợp đồng lỗi ổn định

Client cần biết status, loại lỗi và cách xử lý tiếp theo. Một error contract tốt có:

- HTTP status phản ánh đúng lớp lỗi.
- Mã lỗi ổn định để client xử lý bằng code, không phân tích message.
- Thông điệp ngắn, không tiết lộ SQL, stack trace, tên bảng, đường dẫn file hoặc secret.
- Correlation/request ID để truy vết log.
- Field errors khi dữ liệu đầu vào không hợp lệ.
- Một cấu trúc nhất quán trong phạm vi API do ứng dụng kiểm soát.

### Spring Data REST và ngoại lệ repository

Spring Data REST có exception handling riêng cho các controller do framework quản lý. Ví dụ, khi Spring Validator báo lỗi, framework ném **RepositoryConstraintViolationException**; ngoại lệ này chứa đối tượng **Errors** và kế thừa **DataIntegrityViolationException**. Spring Data REST có handler riêng cho request repository.

Vì vậy, hãy kiểm tra response thật của endpoint Spring Data REST trong MockMvc. Đừng giả định một **@RestControllerAdvice** dành cho custom controller sẽ tự thay thế toàn bộ cách xử lý lỗi của repository exporter. Nếu cần custom handler nằm trong API base path và dùng cấu hình, message converter cùng exception handling của Spring Data REST, xem xét **@RepositoryRestController** cho endpoint tùy chỉnh.

### Problem Details cho custom MVC endpoint

Spring Framework hỗ trợ Problem Details theo RFC 9457 qua **ProblemDetail**, **ErrorResponse** và **ResponseEntityExceptionHandler**. Spring Boot có thể bật xử lý Problem Details cho lỗi Spring MVC tích hợp bằng:

~~~yaml
spring:
  mvc:
    problemdetails:
      enabled: true
~~~

Với lỗi nghiệp vụ từ custom controller, có thể trả ProblemDetail từ exception handler:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ResourceConflictException.class)
    ProblemDetail handleConflict(ResourceConflictException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "The resource cannot be changed in its current state."
        );

        problem.setType(
            URI.create("https://api.example.test/problems/resource-conflict")
        );
        problem.setTitle("Resource conflict");
        problem.setProperty("code", "RESOURCE_CONFLICT");

        return problem;
    }
}
~~~

Response có dạng:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
~~~

~~~json
{
  "type": "https://api.example.test/problems/resource-conflict",
  "title": "Resource conflict",
  "status": 409,
  "detail": "The resource cannot be changed in its current state.",
  "code": "RESOURCE_CONFLICT"
}
~~~

Trong ví dụ, **ResourceConflictException** là exception nghiệp vụ do ứng dụng định nghĩa. Field **code** là extension property của ProblemDetail. Không đưa message của exception gốc ra response nếu message có thể chứa dữ liệu nội bộ.

Kiểm thử custom error contract:

~~~java
@Test
void returnsProblemDetailsForBusinessConflict() throws Exception {
    mvc.perform(get("/api/custom/conflict"))
        .andExpect(status().isConflict())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON
        ))
        .andExpect(jsonPath("$.type").value(
            "https://api.example.test/problems/resource-conflict"
        ))
        .andExpect(jsonPath("$.status").value(409))
        .andExpect(jsonPath("$.code").value("RESOURCE_CONFLICT"));
}
~~~

Endpoint trong test phải thực sự phát sinh **ResourceConflictException**. Nếu custom endpoint nằm trong Spring Data REST URI space và cần dùng các converter/exception handling của exporter, cân nhắc **@RepositoryRestController**. Hãy viết test riêng cho từng loại endpoint vì response handler và media type có thể khác nhau.

### Bảng phân loại lỗi

| HTTP status | Ý nghĩa thường gặp | Ví dụ |
|---|---|---|
| 400 Bad Request | Request không hợp lệ | JSON sai cú pháp, validation thất bại |
| 401 Unauthorized | Chưa xác thực | Thiếu hoặc token không hợp lệ |
| 403 Forbidden | Không được phép | User không có authority |
| 404 Not Found | Không có resource | ID không tồn tại |
| 405 Method Not Allowed | Method không được hỗ trợ | DELETE trên resource chỉ đọc |
| 406 Not Acceptable | Không có representation phù hợp với Accept | Client yêu cầu media type không được cung cấp |
| 409 Conflict | Xung đột với trạng thái hiện tại | Trùng unique business key hoặc state transition bị cấm |
| 412 Precondition Failed | Điều kiện request không còn đúng | If-Match không khớp ETag hiện tại |
| 415 Unsupported Media Type | Request Content-Type không được hỗ trợ | Gửi XML đến endpoint chỉ nhận JSON |
| 500 Internal Server Error | Lỗi ngoài dự kiến | Lỗi lập trình hoặc hạ tầng chưa được ánh xạ |

Không chuyển mọi exception thành 200 hoặc 400. Giữ status đúng giúp proxy, retry policy và client phân biệt lỗi có thể sửa từ request, lỗi cần xác thực, xung đột và lỗi server.

## 5. Quản lý cấu hình theo môi trường

Không hard-code database URL, mật khẩu, API token hoặc base path production trong Java. Spring Boot hỗ trợ cấu hình ngoài artifact bằng application.properties/YAML, profile-specific files, environment variables, system properties, command-line arguments và configuration trees.

### Dùng cấu hình có kiểu và validation

Với nhóm cấu hình riêng của ứng dụng, ưu tiên **@ConfigurationProperties** thay vì rải nhiều **@Value**:

~~~java
@ConfigurationProperties(prefix = "app.api")
@Validated
public record ApiProperties(
    @NotBlank String basePath,
    @Min(1) @Max(200) int defaultPageSize
) {
}
~~~

Đăng ký scan ở lớp ứng dụng:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Cấu hình YAML:

~~~yaml
app:
  api:
    base-path: /api
    default-page-size: 25

spring:
  data:
    rest:
      base-path: /api
~~~

Nếu dùng validation annotation, bảo đảm dependency Jakarta Validation provider có trong classpath. Khi giá trị cấu hình thiếu hoặc không hợp lệ, ứng dụng nên thất bại ngay lúc khởi động thay vì nhận request rồi mới phát hiện.

### Tách profile

Ví dụ cấu trúc:

~~~text
src/main/resources/
  application.yaml
  application-dev.yaml
  application-test.yaml
  application-prod.yaml
~~~

File chung chỉ giữ default an toàn. File profile chứa những khác biệt không nhạy cảm như log level, datasource driver, pool size hoặc endpoint path. Kích hoạt profile từ môi trường triển khai:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

Có thể đặt profile qua command line:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Spring Boot dùng profile-specific configuration để ghi đè cấu hình chung. Property source có độ ưu tiên cao hơn có thể ghi đè giá trị trong file đã đóng gói. Vì thế, khi giá trị thực tế khác YAML, hãy kiểm tra profile đang active và nguồn property được ưu tiên; đừng chỉ sửa file mặc định.

Không đặt **spring.profiles.active** bên trong một file profile-specific. Kích hoạt profile từ file cấu hình chung, environment variable, system property hoặc command line.

### Đưa secret ra ngoài artifact

Có thể inject cấu hình database bằng environment variables:

~~~text
SPRING_DATASOURCE_URL=jdbc:postgresql://db-host:5432/app
SPRING_DATASOURCE_USERNAME=app_user
SPRING_DATASOURCE_PASSWORD=<secret-from-secret-store>
SPRING_PROFILES_ACTIVE=prod
~~~

Không commit giá trị thật vào repository, Docker image, log hoặc file cấu hình được đóng gói. Với Kubernetes Secret hoặc Docker Secret được mount thành file, Spring Boot hỗ trợ configuration tree:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Tên file trong cây cấu hình trở thành property name. Ví dụ file secret tên **spring.datasource.password** có thể cung cấp property cùng tên; cấu trúc thư mục cũng có thể biểu diễn các segment property. Chỉ dùng **optional:** khi ứng dụng thực sự có thể khởi động an toàn nếu thư mục đó không tồn tại. Với secret bắt buộc ở production, để cấu hình fail-fast khi secret bị thiếu.

Không in secret ra log để kiểm tra binding. Nếu cần xác minh cấu hình, log tên profile và trạng thái đã có cấu hình, không log giá trị nhạy cảm.

## 6. Cấu hình vận hành và Actuator

Một cấu hình production cơ bản có thể như sau:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
~~~

Chỉ expose các Actuator endpoint cần thiết. Spring Boot mặc định chỉ expose **health** qua HTTP; endpoint bổ sung có thể tiết lộ thông tin cấu hình, môi trường, bean hoặc metric. Bảo vệ management endpoint bằng network policy và Spring Security; không mở toàn bộ endpoint bằng dấu ***** trên mạng công khai.

### Liveness và readiness

Khi chạy trên Kubernetes, Spring Boot Actuator cung cấp:

- **/actuator/health/liveness**: instance có còn khả năng hoạt động hoặc tự phục hồi không.
- **/actuator/health/readiness**: instance đã sẵn sàng nhận traffic chưa.

Liveness nên phản ánh trạng thái nội bộ của process. Không gắn kiểm tra database hoặc dịch vụ dùng chung vào liveness một cách máy móc: nếu database tạm ngừng, Kubernetes có thể restart đồng loạt các instance và làm sự cố nặng hơn.

Readiness có thể cân nhắc phụ thuộc bên ngoài nếu dependency đó thật sự quyết định instance có thể phục vụ request hay không. Đưa dependency dùng chung vào readiness cần cân nhắc ảnh hưởng khi toàn bộ instance cùng chuyển sang unready.

Ví dụ probe trong Kubernetes:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 10
~~~

Nếu đặt **management.server.port** riêng, probe phải dùng đúng port đó. Hãy xác minh endpoint thực sự được expose và có thể truy cập từ kubelet trong môi trường triển khai.

## 7. Kiểm thử cấu hình và cơ sở dữ liệu thật

Kiểm thử hợp đồng bằng MockMvc xác minh MVC và Spring Data REST, nhưng database giả lập có thể không phản ánh constraint, dialect, transaction và migration của database production. Với những luồng phụ thuộc database, dùng Testcontainers để chạy database thật trong Docker.

Thêm dependency test tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
~~~

Ví dụ khai báo container thành Spring bean và dùng **@ServiceConnection**:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class PostgresTestConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
~~~

Import cấu hình vào integration test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@Import(PostgresTestConfiguration.class)
class PeopleDatabaseIntegrationTest {

    @Autowired
    private PersonRepository people;

    @Test
    void persistsAndReadsPerson() {
        Person saved = people.save(new Person(
            "Mai",
            "mai-" + UUID.randomUUID() + "@example.test"
        ));

        assertThat(people.findById(saved.getId())).isPresent();
    }
}
~~~

Ví dụ giả định entity có constructor tương ứng và project đã có PostgreSQL driver. **@ServiceConnection** yêu cầu module **spring-boot-testcontainers**; Docker phải sẵn sàng trên máy hoặc CI runner. Với Spring Boot phiên bản cũ chưa hỗ trợ service connection, cấu hình URL/user/password bằng **@DynamicPropertySource** hoặc cách đăng ký property phù hợp với phiên bản đó.

Ưu tiên quản lý container theo lifecycle của Spring context khi test context được cache. Đừng để JUnit dừng container trong khi ApplicationContext còn được tái sử dụng bởi test khác. Testcontainers phù hợp để xác minh schema migration, unique constraint, transaction rollback, paging và query behavior trên đúng loại database.

### Kiểm thử binding cấu hình

Có thể truyền property test trực tiếp vào Spring Boot test:

~~~java
@SpringBootTest(properties = {
    "app.api.base-path=/test-api",
    "app.api.default-page-size=10"
})
class ApiPropertiesTest {

    @Autowired
    private ApiProperties properties;

    @Test
    void bindsConfiguredValues() {
        assertThat(properties.basePath()).isEqualTo("/test-api");
        assertThat(properties.defaultPageSize()).isEqualTo(10);
    }
}
~~~

Bổ sung test context khởi động thất bại khi page size bằng 0 hoặc base path để trống. Kiểm thử này xác nhận cấu hình invalid được phát hiện trước khi deploy.

Nếu dùng profile-specific file, kiểm tra profile cần thiết đã active trong integration test và CI. Không để test vô tình dùng giá trị từ máy developer.

## 8. Tích hợp các bước vào CI/CD

Một pipeline có thể thực hiện theo thứ tự:

1. **Compile và unit test:** kiểm tra domain rule, mapper, service và validator.
2. **HTTP contract tests:** chạy MockMvc cho root, collection, CRUD, search, pagination, association, media type, security và error response.
3. **REST Docs:** sinh snippet từ test và build tài liệu; fail nếu snippet bắt buộc không được tạo.
4. **Database integration tests:** chạy Testcontainers, apply migrations, kiểm tra transaction và persistence.
5. **Package:** tạo artifact/container image từ cùng một commit đã được kiểm thử.
6. **Configuration validation:** cung cấp biến môi trường bắt buộc và xác minh application context khởi động bằng profile mục tiêu.
7. **Deploy và smoke test:** kiểm tra health/readiness, API root, media type, authentication và một request đọc an toàn.
8. **Theo dõi sau deploy:** kiểm tra lỗi HTTP, startup failure, migration và readiness; có phương án rollback artifact nếu smoke test thất bại.

Không dùng dữ liệu production trong test. Dùng database tạm, tài khoản test và secret của CI. Build tài liệu và test contract cần chạy lại khi thay đổi repository annotation, projection, DTO, exception handler, security hoặc base path.

### Smoke test sau triển khai

Ví dụ kiểm tra health và API root:

~~~bash
curl -fsS http://localhost:8080/actuator/health/readiness
curl -i -H "Accept: application/hal+json" https://api.example.test/api
~~~

Lệnh đầu phải thành công khi instance sẵn sàng. Lệnh thứ hai nên trả đúng media type, status và relation root theo hợp đồng đã kiểm thử. Nếu API yêu cầu authentication, bổ sung credential lấy từ secret store của pipeline; không ghi token vào script hoặc log.

## 9. Khắc phục lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| MockMvc trả 404 cho toàn bộ endpoint | Sai base path, repository chưa được scan hoặc repository không được export | Kiểm tra **spring.data.rest.base-path**, repository package và export configuration |
| Root có link nhưng collection test fail | Relation hoặc collection path thay đổi | Kiểm tra **path**, **collectionResourceRel** và JSONPath |
| HAL response bị trả 406 | Accept không khớp media type được hỗ trợ | Gửi Accept phù hợp, thường **application/hal+json** |
| POST trả 415 | Content-Type không được converter hỗ trợ | Gửi Content-Type **application/json** hoặc media type endpoint yêu cầu |
| POST trả 400 | JSON không bind được hoặc validator từ chối | Kiểm tra body, field constraint và response lỗi |
| Test mong 404 nhưng nhận 200/204 | ID test trùng dữ liệu hoặc endpoint có semantics khác | Dùng ID không tồn tại đã kiểm soát và kiểm tra resource mapping |
| ProblemDetail không xuất hiện | Endpoint đang được xử lý bởi Spring Data REST handler riêng, Boot property chưa bật hoặc version chưa hỗ trợ | Phân biệt custom MVC endpoint với repository endpoint; kiểm tra version và exception handling |
| REST Docs không tạo snippet | Test chưa gọi **document(...)**, output directory hoặc task build sai | Kiểm tra REST Docs extension/configuration và test report |
| Spring Cloud Contract test không được sinh | Plugin/BOM không tương thích hoặc contract DSL sai | Kiểm tra Spring Cloud release train, plugin và log contract verifier |
| Testcontainers không khởi động | Docker daemon không chạy, image không tải được hoặc CI không cấp container runtime | Kiểm tra Docker availability, image access và runner permission |
| Test pass local nhưng fail CI | Profile, env var, timezone, DB version hoặc secret khác nhau | Khai báo test config tường minh và dùng container cùng database engine |
| Giá trị cấu hình không đúng như YAML | Environment variable, command line hoặc external config ghi đè | Kiểm tra active profiles và property source precedence |
| App không khởi động ở production | Thiếu config/secret hoặc binding validation thất bại | Kiểm tra tên env var, mounted config tree và required property |
| Health báo UP nhưng traffic vẫn không đến | Readiness probe sai path/port hoặc endpoint chưa expose | Kiểm tra health group, management port, security và Kubernetes probe |
| Instance liên tục restart khi DB lỗi | Liveness phụ thuộc external database | Giữ liveness cho trạng thái nội bộ; đánh giá dependency ở readiness |

## 10. Checklist trước khi phát hành

- [ ] Root URI và collection/item URI đúng với cấu hình production.
- [ ] HAL relation, _embedded, search, paging và media type được khóa bằng contract test.
- [ ] POST/PUT/PATCH/DELETE có test cho cả trường hợp hợp lệ và lỗi.
- [ ] Status code 400, 401, 403, 404, 405, 406, 409, 412 và 415 được kiểm tra ở nơi API hỗ trợ.
- [ ] Custom business errors có error code ổn định và không lộ chi tiết nội bộ.
- [ ] Spring Data REST validation errors được kiểm tra qua đúng repository endpoint.
- [ ] REST Docs được sinh từ test và tài liệu được build trong CI.
- [ ] Consumer-driven contract được dùng khi có service consumer độc lập và được quản lý bằng Spring Cloud BOM tương thích.
- [ ] Cấu hình riêng của ứng dụng dùng **@ConfigurationProperties** và có validation.
- [ ] Profile production được kích hoạt từ môi trường triển khai.
- [ ] Database credential và token nằm trong secret store hoặc configuration tree.
- [ ] Actuator chỉ expose endpoint cần thiết và có bảo vệ phù hợp.
- [ ] Liveness không phụ thuộc tùy tiện vào database/dịch vụ dùng chung.
- [ ] Readiness path/port khớp Kubernetes probe.
- [ ] Testcontainers kiểm tra database engine và migration cần thiết.
- [ ] CI chạy contract test, REST Docs, integration test và smoke test sau deploy.

## 11. Tài liệu chính thức

- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): kiểm thử đầy đủ Spring MVC request handling mà không cần server thật.
- [Spring Framework — MockMvc Overview](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html): phạm vi kiểm thử mapping, binding, conversion, validation và exception handling.
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): cấu hình MockMvc, generated snippets và build tài liệu.
- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/configuration/default-snippets.html): các snippet request/response mặc định.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): mô tả request/response contract và tạo stub.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): tải và chạy stub cho consumer integration tests.
- [Spring Data REST — Reference](https://docs.spring.io/spring-data/rest/reference/): repository resources, representations, validation, security và conditional requests.
- [RepositoryRestExceptionHandler API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/RepositoryRestExceptionHandler.html): exception handler dành cho Spring Data REST controllers.
- [RepositoryConstraintViolationException API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/RepositoryConstraintViolationException.html): ngoại lệ validation của Spring Data REST và access tới Errors.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): ProblemDetail, ErrorResponse, ResponseEntityExceptionHandler và RFC 9457.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property source precedence, environment variables, configuration trees và @ConfigurationProperties validation.
- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): profile-specific files, active profiles và profile groups.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure, access control và Kubernetes probes.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): quản lý container, @ServiceConnection và lifecycle trong Spring test context.
