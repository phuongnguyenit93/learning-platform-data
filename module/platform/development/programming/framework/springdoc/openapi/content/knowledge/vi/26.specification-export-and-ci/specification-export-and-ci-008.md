# Cấp cấu hình kiểm thử thay vì phụ thuộc dịch vụ production khi build

Khi xuất OpenAPI trong CI, springdoc-openapi cần một Spring Boot application đang chạy để tạo tài liệu từ controller, model, annotation và cấu hình hiện có. Quy trình export vì vậy có thể vô tình khởi tạo database production, gọi identity provider, kết nối Kafka, gửi request đến dịch vụ đối tác hoặc đọc secret của môi trường thật nếu build dùng cấu hình mặc định.

Cách an toàn và ổn định là tạo một profile dành riêng cho việc xuất tài liệu, ví dụ profile openapi. Profile này cung cấp cấu hình kiểm thử, dữ liệu giả hoặc dịch vụ thay thế cho những dependency không cần thiết để tạo đặc tả. Ứng dụng vẫn khởi tạo các controller và thành phần springdoc cần quét; chỉ các tích hợp bên ngoài được thay bằng cấu hình phù hợp với CI.

Bài học này trình bày cách tổ chức profile, thay thế dependency production, chạy ứng dụng tạm thời để lấy OpenAPI JSON, lưu artifact và kiểm tra kết quả trước khi phát hành.

## 1. Vì sao build không nên phụ thuộc dịch vụ production?

springdoc-openapi thường tạo tài liệu tại runtime từ Spring application context. Khi CI cần xuất file OpenAPI, ứng dụng phải khởi động đủ để springdoc phát hiện endpoint, schema, security scheme và metadata.

Nếu ứng dụng dùng cấu hình production trong quá trình này, build có thể gặp các vấn đề:

- Không thể khởi động khi database production không truy cập được.
- Build phụ thuộc secret, credential hoặc certificate của môi trường thật.
- Một bean gọi API đối tác ngay khi khởi tạo hoặc trong quá trình tạo tài liệu.
- Kafka, RabbitMQ hoặc scheduler tạo kết nối và chạy tác vụ ngoài ý muốn.
- CI không có quyền truy cập mạng nội bộ production.
- Kết quả export thay đổi theo dữ liệu, trạng thái hoặc cấu hình của dịch vụ bên ngoài.
- Build có thể vô tình gửi email, phát message hoặc thực hiện side effect.

Việc tạo OpenAPI chủ yếu cần metadata của ứng dụng. Nó thường không cần dữ liệu nghiệp vụ production hay quyền gọi dịch vụ thật. Vì vậy, nên cung cấp một môi trường khởi động riêng, có dữ liệu và tích hợp kiểm thử xác định.

## 2. Tách cấu hình export khỏi cấu hình production

Spring Boot hỗ trợ profile-specific configuration. Có thể tạo file application-openapi.yml để chứa cấu hình dành riêng cho việc xuất tài liệu:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-prod.yml
  application-openapi.yml
~~~

Profile openapi được kích hoạt khi chạy ứng dụng trong CI. Các thuộc tính trong application-openapi.yml ghi đè giá trị tương ứng từ application.yml.

Ví dụ:

~~~yaml
# application-openapi.yml
server:
  port: 18080

spring:
  application:
    name: catalog-service

springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false

app:
  jobs:
    enabled: false
  messaging:
    consumers-enabled: false
  integrations:
    inventory:
      mode: stub
    payment:
      mode: stub
~~~

Các thuộc tính app.jobs, app.messaging và app.integrations là ví dụ thuộc cấu hình riêng của ứng dụng. Chúng chỉ có tác dụng khi code của ứng dụng thực sự đọc và áp dụng chúng, chẳng hạn bằng @ConfigurationProperties hoặc @ConditionalOnProperty. Không có quy tắc mặc định nào trong Spring Boot tự tắt scheduler hoặc consumer chỉ vì các key này xuất hiện.

Không đặt password production, API key, client secret hay private key vào profile export. Nếu một thành phần cần credential để khởi động, hãy cấp credential kiểm thử riêng hoặc thay thế thành phần đó bằng adapter giả.

## 3. Profile export không phải profile production rút gọn

Profile export cần giữ những thành phần cần thiết để springdoc nhìn thấy hợp đồng API:

- Controller hoặc functional route.
- DTO, record, enum và model được dùng trong request/response.
- Các annotation OpenAPI và validation.
- Security scheme và operation metadata.
- Cấu hình nhóm tài liệu nếu dự án dùng GroupedOpenApi.
- Bean cần thiết để tạo application context.

Các thành phần thường có thể thay thế hoặc tắt có kiểm soát:

- HTTP client gọi dịch vụ đối tác.
- Message listener và consumer nền.
- Scheduler, batch job hoặc tác vụ gửi thông báo.
- Kết nối identity provider bên ngoài nếu ứng dụng có thể dùng cấu hình xác thực kiểm thử.
- Database thật, nếu có thể thay bằng database tạm hoặc test double phù hợp.

Không tắt component scan hoặc loại bỏ toàn bộ controller để làm ứng dụng khởi động nhanh. Làm vậy có thể khiến tài liệu export thiếu endpoint. Mục tiêu là thay thế dependency không cần thiết, đồng thời giữ nguyên phần định nghĩa API cần công bố.

## 4. Thay thế adapter gọi dịch vụ bên ngoài

Nên đặt tích hợp bên ngoài sau một interface để có thể thay implementation theo profile. Ví dụ ứng dụng cần tra cứu tồn kho:

~~~java
interface InventoryGateway {
    InventoryItem findBySku(String sku);
}

record InventoryItem(
    String sku,
    int availableQuantity
) {
}
~~~

Implementation production gọi dịch vụ thật:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.client.RestTemplate;

@Component
@Profile("!openapi")
class HttpInventoryGateway implements InventoryGateway {

    private final RestTemplate restTemplate;

    HttpInventoryGateway(
            RestTemplateBuilder builder,
            @Value("${app.integrations.inventory.base-url}") String baseUrl) {
        this.restTemplate = builder
            .rootUri(baseUrl)
            .build();
    }

    @Override
    public InventoryItem findBySku(String sku) {
        return restTemplate.getForObject(
            "/items/{sku}",
            InventoryItem.class,
            sku
        );
    }
}
~~~

Implementation dùng trong profile export:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("openapi")
class OpenApiStubConfiguration {

    @Bean
    InventoryGateway inventoryGateway() {
        return sku -> new InventoryItem(sku, 25);
    }
}
~~~

Khi profile openapi hoạt động, Spring tạo bean giả. Ở các profile khác, Spring tạo HTTP adapter production. Controller và service vẫn phụ thuộc vào interface InventoryGateway nên không cần thay đổi chữ ký endpoint.

Cần bảo đảm chỉ có một implementation được đăng ký trong mỗi profile. Nếu implementation production không được gắn profile hoặc điều kiện phù hợp, ứng dụng có thể gặp lỗi có nhiều bean cùng kiểu.

Stub ở đây chỉ giúp application context khởi động và cho phép các luồng cần inventory có kết quả xác định. Nó không thay thế kiểm thử tích hợp HTTP với dịch vụ inventory thật. Các kiểm thử giao tiếp cần một môi trường riêng như WireMock hoặc Testcontainers.

## 5. Dùng ConditionalOnProperty cho tích hợp tùy chọn

Nếu ứng dụng đã dùng property để bật/tắt tích hợp, có thể điều khiển bằng profile export:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ProductionMessagingConfiguration {

    @Bean
    @ConditionalOnProperty(
        name = "app.messaging.consumers-enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    MessageConsumer messageConsumer() {
        return new MessageConsumer();
    }
}
~~~

Trong application-openapi.yml:

~~~yaml
app:
  messaging:
    consumers-enabled: false
~~~

Ví dụ trên chỉ có ý nghĩa nếu ứng dụng kiểm soát việc tạo consumer bằng đúng property đó. Với Spring Kafka, RabbitMQ hoặc thư viện khác, hãy kiểm tra cấu hình listener/container tương ứng; chỉ ngăn tạo một bean consumer không nhất thiết đã tắt toàn bộ auto-configuration hoặc connection factory.

Nếu ứng dụng cần giữ các bean messaging để tạo schema hoặc metadata, hãy tắt hoạt động nhận message thay vì loại bỏ những bean cần thiết. Không dùng một thuộc tính giả định của framework nếu chưa xác nhận nó tồn tại trong phiên bản đang dùng.

## 6. Database kiểm thử cho quá trình khởi động

Một số ứng dụng kết nối database ngay khi khởi động vì JPA, Flyway, Liquibase hoặc repository. Nếu CI chỉ cần sinh tài liệu, không nên trỏ đến database production.

Có ba lựa chọn phổ biến:

| Lựa chọn | Khi phù hợp | Điểm cần kiểm tra |
|---|---|---|
| H2 hoặc database in-memory | Schema đơn giản, tương thích với H2 | Khác biệt dialect, kiểu dữ liệu và SQL migration |
| Testcontainers | Cần database tạm cùng engine với production | CI phải có môi trường chạy container |
| Repository/service test double | Không cần truy cập database khi tạo tài liệu | Phải thay thế đúng dependency và giữ controller trong context |

Nếu dùng H2, có thể cấu hình:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:openapi;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  jpa:
    hibernate:
      ddl-auto: create-drop
~~~

Cấu hình này chỉ phù hợp khi entity mapping có thể khởi tạo với H2 và không phụ thuộc SQL riêng của production database. Nếu ứng dụng dùng migration không tương thích H2, hãy dùng Testcontainers với cùng loại database hoặc thay thế repository ở một test context chuyên biệt.

Nếu chạy ứng dụng đã đóng gói bằng Spring Boot Maven Plugin, dependency test scope không tự động nằm trong runtime classpath của tiến trình ứng dụng. Có thể thêm database kiểm thử ở runtime scope trong Maven profile export riêng để nó không đi vào artifact production. Nếu dùng @SpringBootTest chạy trong test process, dependency test scope có thể được dùng trực tiếp.

Không tắt Flyway hoặc Liquibase một cách máy móc. Nếu ứng dụng cần schema để khởi tạo repository, hãy chạy migration trên database tạm tương thích. Chỉ tắt migration khi đã xác nhận application context không cần schema đó.

## 7. Giữ security scheme trong tài liệu mà không phụ thuộc identity provider production

springdoc có thể mô tả Bearer, OAuth2 hoặc OpenID Connect mà không cần gọi identity provider production để sinh tài liệu. Security scheme là metadata OpenAPI; việc xác minh token runtime là một hoạt động riêng.

Trong profile export:
- Cho phép tiến trình CI đọc endpoint tài liệu OpenAPI.
- Giữ security scheme và security requirement của API.
- Không đưa client secret production vào cấu hình.
- Nếu JWT decoder cần khóa hoặc issuer để khởi tạo, dùng public key/JWK kiểm thử hoặc JwtDecoder giả trong test context.
- Không vô hiệu hóa authentication của toàn bộ API chỉ để plugin tải được tài liệu.

Với Spring MVC/Spring Security, có thể cho phép riêng endpoint tài liệu trong filter chain dành cho profile export:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@Profile("openapi")
class OpenApiSecurityConfiguration {

    @Bean
    SecurityFilterChain openApiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/v3/api-docs/**",
                    "/v3/api-docs.yaml"
                ).permitAll()
                .anyRequest().authenticated()
            )
            .build();
    }
}
~~~

Nếu ứng dụng đã có SecurityFilterChain khác, cần cấu hình profile để không tạo hai chain cạnh tranh ngoài ý muốn. Có thể tích hợp rule cho endpoint tài liệu vào chain hiện có. Với WebFlux, dùng SecurityWebFilterChain và matcher tương ứng thay vì cấu hình Servlet ở trên.

Đường dẫn trong ví dụ là mặc định. Nếu đã đổi springdoc.api-docs.path hoặc dùng group endpoint, hãy cập nhật matcher cho đúng. Việc permitAll trong profile openapi không đồng nghĩa mở tài liệu production; profile này chỉ được kích hoạt trong tiến trình CI dùng để export.

## 8. Xuất OpenAPI bằng springdoc-openapi Maven Plugin

springdoc-openapi-maven-plugin gọi endpoint OpenAPI của ứng dụng đang chạy và ghi response thành file. Plugin không thay thế Spring Boot runtime và không tự khởi tạo toàn bộ dependency ứng dụng. Vì vậy, phải khởi động ứng dụng với profile export trước khi chạy goal generate.

Một quy trình Maven thường dùng:

1. Build ứng dụng.
2. Khởi động Spring Boot ở phase pre-integration-test.
3. Kích hoạt profile openapi trong JVM ứng dụng.
4. Gọi endpoint /v3/api-docs ở phase integration-test.
5. Ghi JSON vào thư mục build.
6. Dừng ứng dụng ở phase post-integration-test.

Ví dụ cấu hình plugin trong Maven profile:

~~~xml
<profiles>
    <profile>
        <id>openapi-export</id>

        <dependencies>
            <dependency>
                <groupId>com.h2database</groupId>
                <artifactId>h2</artifactId>
                <scope>runtime</scope>
            </dependency>
        </dependencies>

        <build>
            <plugins>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                    <executions>
                        <execution>
                            <id>start-openapi-app</id>
                            <phase>pre-integration-test</phase>
                            <goals>
                                <goal>start</goal>
                            </goals>
                        </execution>
                        <execution>
                            <id>stop-openapi-app</id>
                            <phase>post-integration-test</phase>
                            <goals>
                                <goal>stop</goal>
                            </goals>
                        </execution>
                    </executions>
                    <configuration>
                        <jvmArguments>
                            -Dspring.profiles.active=openapi
                        </jvmArguments>
                    </configuration>
                </plugin>

                <plugin>
                    <groupId>org.springdoc</groupId>
                    <artifactId>springdoc-openapi-maven-plugin</artifactId>
                    <version>1.4</version>
                    <executions>
                        <execution>
                            <id>export-openapi</id>
                            <phase>integration-test</phase>
                            <goals>
                                <goal>generate</goal>
                            </goals>
                        </execution>
                    </executions>
                    <configuration>
                        <apiDocsUrl>http://localhost:18080/v3/api-docs</apiDocsUrl>
                        <outputFileName>openapi.json</outputFileName>
                        <outputDir>${project.build.directory}/openapi</outputDir>
                    </configuration>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
~~~

Ví dụ dùng H2 ở runtime scope nhưng chỉ bên trong profile Maven openapi-export. Khi build production không kích hoạt profile này, dependency H2 không được thêm vào artifact production.

Thay version plugin bằng version đã được dự án phê duyệt và kiểm tra tương thích với Maven/Spring Boot hiện tại. Nếu dùng dependency management riêng, bổ sung version H2 hoặc BOM phù hợp.

Chạy quy trình:

~~~bash
mvn -B -Popenapi-export clean verify
~~~

Khi Maven chạy profile này, Spring Boot Maven Plugin khởi động ứng dụng ở port 18080 với profile openapi. springdoc plugin gọi URL đã cấu hình và ghi file vào target/openapi/openapi.json.

Các phase rất quan trọng: nếu export chạy trước khi ứng dụng sẵn sàng, plugin không lấy được tài liệu. Nếu app không dừng sau khi export, tiến trình CI có thể bị treo hoặc chiếm port ở job tiếp theo. Khi một phase thất bại khiến lifecycle không chạy đến post-integration-test, pipeline nên có bước cleanup tiến trình trong phần luôn chạy của CI.

Nếu api-docs path đã được tùy chỉnh, thay URL trong apiDocsUrl. Nếu cần xuất group riêng, dùng endpoint group tương ứng, ví dụ /v3/api-docs/public, và tạo một execution/output file riêng cho từng group.

## 9. Đảm bảo cấu hình export không bị kích hoạt trong production

Profile openapi nên chỉ được bật tường minh ở job xuất tài liệu. Không đặt spring.profiles.active=openapi trong application.yml hoặc biến môi trường production.

Một số nguyên tắc:
- Chỉ dùng Maven profile openapi-export trong job export.
- JVM chạy ứng dụng export được bật spring.profiles.active=openapi.
- Production deployment tiếp tục dùng profile production riêng.
- Không để profile openapi ghi đè cấu hình chung nếu profile đó có thể vô tình được kích hoạt ngoài CI.
- Không đóng gói secret kiểm thử cố định có thể bị dùng nhầm ở production.
- Có thể kiểm tra active profile trong startup log để xác nhận tiến trình đang dùng openapi.

Profile Maven và Spring profile có vai trò khác nhau. Maven profile openapi-export quyết định dependency/plugin nào được thêm vào build. Spring profile openapi quyết định cấu hình và bean nào được nạp khi ứng dụng chạy. Dùng cùng tên giúp dễ nhớ nhưng hai profile không tự kích hoạt lẫn nhau; cần cấu hình JVM hoặc environment để truyền Spring profile vào tiến trình ứng dụng.

## 10. Dùng test context thay cho tiến trình ứng dụng đóng gói

Một lựa chọn khác là tạo integration test bằng @SpringBootTest. Test context có thể dùng @TestConfiguration, Mockito hoặc test bean để thay thế dependency mà không đưa implementation giả vào artifact ứng dụng.

Ví dụ định hướng:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "spring.profiles.active=openapi",
        "springdoc.api-docs.enabled=true"
    }
)
@Import(OpenApiTestOverrides.class)
class OpenApiExportTest {
    // Lấy OpenAPI document qua HTTP và ghi thành file build.
}
~~~

Trong test context, có thể thay repository/client bằng bean kiểm thử và dùng port ngẫu nhiên để tránh xung đột. Test có thể gọi endpoint /v3/api-docs rồi lưu response vào thư mục build.

Ưu điểm là dependency test có sẵn và không cần khởi chạy một JVM ứng dụng riêng. Tuy nhiên, test phải thực sự lấy response HTTP từ application context để kiểm tra đúng cấu hình web và springdoc. Chỉ khởi tạo OpenAPI bean trực tiếp có thể bỏ qua các vấn đề liên quan đến endpoint, security filter, context path hoặc serialization.

Nếu dùng cách này, bảo đảm test chạy trong phase CI phù hợp, file được ghi vào thư mục build và test thất bại khi endpoint docs không trả về tài liệu hợp lệ.

## 11. Gradle và các hệ thống CI khác

springdoc-openapi-maven-plugin là Maven plugin. Dự án Gradle có thể dùng integration test hoặc một task CI tự khởi động ứng dụng với profile openapi rồi tải endpoint tài liệu.

Quy trình Gradle tương đương:
1. Build executable application hoặc test runtime.
2. Chạy ứng dụng với Spring profile openapi.
3. Chờ health/readiness endpoint hoặc kiểm tra endpoint docs sẵn sàng.
4. Tải /v3/api-docs hoặc endpoint group.
5. Lưu response vào build/openapi/openapi.json.
6. Dừng ứng dụng kể cả khi bước tải tài liệu thất bại.
7. Validate file trước khi upload artifact.

Không nên dùng sleep cố định làm điều kiện duy nhất để biết ứng dụng đã sẵn sàng. Dùng health check hoặc retry có giới hạn đến khi endpoint docs phản hồi, sau đó báo lỗi rõ ràng nếu hết thời gian chờ.

Dù dùng GitHub Actions, GitLab CI, Jenkins hay hệ thống khác, hãy giữ profile export và artifact path nhất quán. CI runner cần có quyền tải dependencies, khởi chạy database/container nếu có và ghi artifact vào workspace của job.

## 12. Kiểm tra file OpenAPI sau khi export

Một file tồn tại chưa có nghĩa là tài liệu hợp lệ. Sau khi export, nên kiểm tra ít nhất:

- File tồn tại và không rỗng.
- JSON parse thành công.
- Có trường openapi và phiên bản nằm trong phạm vi dự án hỗ trợ.
- Có info.title và info.version.
- Các path quan trọng được công bố.
- Request/response schema không bị thiếu do profile đã loại nhầm bean.
- Security scheme và security requirement vẫn xuất hiện.
- Server URL không trỏ nhầm localhost, hostname container hoặc URL nội bộ.
- Không có credential, token hoặc secret bị đưa vào description/example.
- Các schema composition và constraint đúng phiên bản OpenAPI.

Có thể thêm validator OpenAPI vào CI để kiểm tra cấu trúc tài liệu. Nếu dự án có baseline, dùng công cụ diff hợp đồng để phát hiện thay đổi breaking trước khi merge hoặc publish.

Không nên chỉ so sánh kích thước file. Thứ tự key, metadata hoặc formatting có thể thay đổi mà hợp đồng không đổi; ngược lại, một file cùng kích thước vẫn có thể chứa thay đổi không tương thích.

## 13. Kiểm tra profile export có tạo tài liệu tương đương profile production không

Profile export thay thế dependency bên ngoài, nhưng phải giữ metadata API. Hãy kiểm tra những thành phần sau giữa profile export và môi trường ứng dụng bình thường:

| Thành phần | Điều cần giữ nhất quán |
|---|---|
| Controller/functional route | Path, method, operationId, tag |
| DTO và schema | Property, type, required, validation constraint |
| OpenAPI annotations | Summary, description, response, example |
| Security | Scheme, scope và security requirement |
| GroupedOpenApi | Tên group, path/include/exclude |
| Customizer | Schema và operation được bổ sung |
| Jackson | Naming strategy, module và serialization metadata |

Một stub service có thể trả dữ liệu giả nhưng không được thay controller bằng một controller rút gọn có hợp đồng khác. Nếu profile export bỏ qua một bean tạo operation metadata, tài liệu sinh ra sẽ không phản ánh hợp đồng thực tế.

Nên có kiểm tra tự động xác nhận một số path và schema quan trọng tồn tại trong file export. Khi thay đổi cấu hình profile, hãy rà lại những assertion này để tránh việc tài liệu bị thiếu endpoint mà build vẫn thành công.

## 14. Lỗi thường gặp

**Build dùng application-prod.yml.** Ứng dụng cố kết nối database, identity provider hoặc dịch vụ thật. Kích hoạt profile openapi riêng khi chạy tiến trình export.

**Chỉ thêm application-openapi.yml nhưng không bật profile.** Spring Boot không tự chọn file đó. Truyền spring.profiles.active=openapi vào JVM hoặc environment của tiến trình.

**Tạo stub bean nhưng implementation production vẫn được đăng ký.** Spring có thể báo nhiều bean cùng kiểu hoặc chọn nhầm adapter. Dùng @Profile hoặc @ConditionalOnProperty cho cả hai implementation.

**Đưa H2 vào test scope rồi chạy app đã đóng gói.** Dependency không có trong runtime classpath của tiến trình. Dùng Maven profile export với runtime scope hoặc chạy trong test context.

**Tắt database/messaging toàn cục.** Application context có thể không khởi tạo hoặc mất bean cần thiết. Chỉ thay thế/tắt thành phần gây side effect theo profile.

**Mở toàn bộ API không cần xác thực.** Chỉ cho phép endpoint tài liệu trong profile export; giữ security scheme và authorization của operation.

**Dùng production identity provider để tạo OpenAPI.** Việc export không cần token production. Dùng test key/JWK hoặc decoder giả nếu ứng dụng cần khởi tạo thành phần JWT.

**Gọi endpoint docs trước khi ứng dụng sẵn sàng.** Plugin nhận lỗi kết nối. Bảo đảm lifecycle start hoàn tất và endpoint đã phản hồi trước goal generate.

**Không dừng ứng dụng sau export.** CI runner còn tiến trình và port bị chiếm. Gắn goal stop đúng phase và có cleanup khi pipeline thất bại.

**Profile export bỏ mất controller hoặc customizer.** File JSON hợp lệ nhưng thiếu operation. Giữ application context và kiểm tra path/schema bắt buộc.

**Dùng dữ liệu hoặc URL nội bộ trong tài liệu.** Kiểm tra servers, examples và descriptions để loại hostname nội bộ, token hoặc secret trước khi upload artifact.

## 15. Checklist cho pipeline xuất OpenAPI

- [ ] Có Spring profile riêng dành cho export, ví dụ openapi.
- [ ] Có application-openapi.yml với port và cấu hình kiểm thử.
- [ ] Profile export không chứa secret production.
- [ ] Tích hợp HTTP bên ngoài được thay bằng stub, WireMock hoặc service kiểm thử.
- [ ] Database dùng in-memory/test container phù hợp hoặc repository test double.
- [ ] Consumer, scheduler và batch side effect được tắt có chủ đích.
- [ ] Controller, DTO, security metadata và OpenAPI customizer vẫn được nạp.
- [ ] Endpoint tài liệu được cho phép trong phạm vi tiến trình CI.
- [ ] Maven/Gradle kích hoạt đúng Spring profile.
- [ ] Ứng dụng được khởi động trước khi gọi endpoint docs.
- [ ] OpenAPI JSON/YAML được ghi vào artifact path xác định.
- [ ] Ứng dụng được dừng cả khi export thất bại.
- [ ] File được parse và validate.
- [ ] Path, schema, server URL và security scheme được kiểm tra.
- [ ] Có contract diff hoặc baseline check trước khi publish.

## Tài liệu tham khảo

- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): cấu hình và kích hoạt profile theo môi trường.
- [Spring Boot Maven Plugin – Start and Stop](https://docs.spring.io/spring-boot/maven-plugin/run.html): chạy ứng dụng trong Maven lifecycle.
- [springdoc-openapi Maven Plugin](https://github.com/springdoc/springdoc-openapi-maven-plugin): gọi endpoint OpenAPI và ghi tài liệu vào file trong build.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): thứ tự ưu tiên và cách nạp cấu hình.
- [Spring Framework – Environment Profiles](https://docs.spring.io/spring-framework/reference/core/beans/environment.html#beans-definition-profiles): điều kiện tạo bean theo profile.
- [Testcontainers](https://testcontainers.com/): tạo dependency kiểm thử tạm thời như database và dịch vụ hạ tầng.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): cấu trúc và quy tắc của tài liệu OpenAPI.
