# Tách cấu hình phát triển, kiểm thử và production trong Spring Data REST

## 1. Mục tiêu và nguyên tắc

Một ứng dụng Spring Data REST thường được chạy ở ít nhất ba môi trường:

- **Development (dev)**: lập trình viên chạy ứng dụng trên máy cá nhân, dùng database và dịch vụ tích hợp dành cho phát triển, bật log chi tiết để điều tra lỗi.
- **Testing (test)**: chạy unit test và integration test với dữ liệu cô lập, cấu hình xác định, không kết nối nhầm tới database thật.
- **Production (prod)**: phục vụ người dùng thật, lấy thông tin kết nối và secret từ môi trường triển khai, giới hạn thông tin chẩn đoán và dùng cấu hình database an toàn.

Spring Boot hỗ trợ tách các cấu hình này bằng **Spring Profiles** và **Externalized Configuration**. Cùng một mã nguồn và cùng một file JAR có thể chạy ở các môi trường khác nhau; môi trường quyết định cấu hình được nạp lúc khởi động.

Nguyên tắc nên áp dụng:

1. Đặt giá trị dùng chung trong application.yml.
2. Đặt phần khác biệt theo môi trường trong application-dev.yml, application-test.yml và application-prod.yml.
3. Chọn profile khi khởi động bằng biến môi trường, JVM system property hoặc command-line argument.
4. Đưa mật khẩu, token, private key và thông tin nhạy cảm ra khỏi source code và artifact.
5. Chỉ để cấu hình test dùng dữ liệu test; không để dev hoặc test tự động trở thành cấu hình production.
6. Dùng cùng artifact đã build qua các môi trường và thay đổi cấu hình runtime theo môi trường.

## 2. Spring Profile hoạt động như thế nào?

Profile là tên một nhóm cấu hình hoặc bean được bật trong Environment. Khi profile dev được kích hoạt, Spring Boot nạp cấu hình chung và cấu hình riêng cho dev. Các bean đánh dấu @Profile("dev") cũng có thể được đăng ký trong application context.

Ví dụ cấu trúc file:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-test.yml
  application-prod.yml
~~~

application.yml luôn là cấu hình chung. File application-{profile}.yml chỉ được áp dụng khi profile tương ứng đang active. Ví dụ, khi active prod, Spring Boot nạp application.yml rồi áp dụng các giá trị trong application-prod.yml; giá trị profile-specific ghi đè giá trị chung khi cùng một property xuất hiện ở cả hai nơi.

Có thể bật nhiều profile cùng lúc, ví dụ dev,metrics. Khi nhiều profile cùng định nghĩa một property, profile được xử lý sau có thể ghi đè giá trị trước. Chỉ bật nhiều profile khi có chủ đích rõ ràng, tránh kết hợp dev với prod khiến cấu hình khó dự đoán.

Nếu không đặt profile active, Spring dùng profile mặc định tên default. Có thể đổi tên profile mặc định bằng spring.profiles.default. Với ứng dụng cần buộc môi trường triển khai khai báo profile tường minh, có thể đặt spring.profiles.default: none trong file chung. Khi đó, nếu quên đặt profile, các file application-dev.yml, application-test.yml và application-prod.yml sẽ không được chọn theo profile.

**Không đặt spring.profiles.active hoặc spring.profiles.default trong file profile-specific** như application-prod.yml hoặc trong document được kích hoạt bằng spring.config.activate.on-profile. Các thuộc tính này phải nằm trong document không gắn profile hoặc được truyền từ bên ngoài ứng dụng. Cách rõ ràng nhất cho deployment là đặt SPRING_PROFILES_ACTIVE tại môi trường chạy.

## 3. Tạo cấu hình dùng chung

Ví dụ src/main/resources/application.yml:

~~~yaml
spring:
  application:
    name: spring-data-rest-api
  profiles:
    default: none
  data:
    rest:
      base-path: /api
      default-page-size: 20
      max-page-size: 100
      detection-strategy: annotated

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
~~~

Giải thích:

- spring.application.name đặt tên ứng dụng.
- spring.profiles.default: none tránh âm thầm dùng profile default khi deployment chưa khai báo profile.
- spring.data.rest.base-path: /api đặt prefix chung cho các repository endpoint, ví dụ /api/orders.
- default-page-size và max-page-size giới hạn kích thước trang mặc định và tối đa của collection endpoint.
- detection-strategy: annotated chỉ export repository được đánh dấu bằng @RepositoryRestResource (trừ các trường hợp được cấu hình export riêng). Đây là cách chủ động kiểm soát repository nào xuất hiện trong REST API.
- management.endpoints.web.exposure.include chỉ expose các Actuator endpoint cần dùng. Không mở toàn bộ endpoint chỉ để tiện debug.
- management.endpoint.health.show-details: never không trả chi tiết health cho mọi người gọi endpoint.

Nếu ứng dụng không dùng YAML, có thể viết cùng các property trong application.properties. Nên thống nhất một định dạng trong cả dự án; khi .properties và YAML cùng tồn tại tại một vị trí, .properties có độ ưu tiên cao hơn.

Với detection-strategy: annotated, repository cần được export tường minh, ví dụ:

~~~java
@RepositoryRestResource(
    path = "orders",
    collectionResourceRel = "orders"
)
public interface OrderRepository extends JpaRepository<Order, UUID> {
}
~~~

Ví dụ này giả định ứng dụng dùng Spring Data JPA. Với Spring Data MongoDB, Cassandra hoặc module lưu trữ khác, repository sẽ kế thừa interface tương ứng của module đó. Việc giới hạn repository được export giúp kiểm soát bề mặt API, nhưng **không thay thế xác thực và phân quyền**. Các endpoint có dữ liệu nhạy cảm vẫn cần Spring Security và quy tắc authorization phù hợp.

## 4. Cấu hình Development

Tạo src/main/resources/application-dev.yml:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/spring_data_rest_dev
    username: spring_dev
  jpa:
    hibernate:
      ddl-auto: update

logging:
  level:
    org.springframework.data.rest: DEBUG
    org.hibernate.SQL: DEBUG

server:
  error:
    include-message: always
~~~

Trong ví dụ này:

- Database là PostgreSQL cài trên máy phát triển.
- ddl-auto: update tiện cho vòng lặp phát triển cục bộ, nhưng không nên dùng trong production.
- Log DEBUG hỗ trợ quan sát hoạt động của Spring Data REST và SQL. Nếu log chứa dữ liệu nhạy cảm, cần điều chỉnh trước khi chia sẻ log.
- server.error.include-message: always chỉ phù hợp với môi trường local có kiểm soát; không bật rộng rãi ở production vì thông báo lỗi có thể tiết lộ chi tiết nội bộ.

Mật khẩu database được truyền riêng bằng biến môi trường SPRING_DATASOURCE_PASSWORD; không ghi mật khẩu vào file cấu hình được commit. Nếu dùng một database local không cần mật khẩu, hãy cấu hình đúng theo database của nhóm và vẫn giữ nguyên nguyên tắc không đưa credential thật vào Git.

Chạy trên macOS/Linux:

~~~bash
SPRING_PROFILES_ACTIVE=dev ./mvnw spring-boot:run
~~~

Chạy trên Windows PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
.\mvnw.cmd spring-boot:run
~~~

Hoặc chạy JAR đã build:

~~~bash
java -jar target/spring-data-rest-api.jar --spring.profiles.active=dev
~~~

Sau khi khởi động, kiểm tra log startup để xác nhận profile dev được active và gọi endpoint theo base path đã cấu hình, ví dụ GET http://localhost:8080/api/orders.

Nếu dự án không dùng JPA, bỏ phần spring.datasource và spring.jpa rồi thay bằng property của persistence module thực tế. Spring Data REST không bắt buộc mọi ứng dụng phải dùng cùng một loại database.

## 5. Cấu hình Testing

Tạo src/main/resources/application-test.yml:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:spring_data_rest_test;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
  jpa:
    hibernate:
      ddl-auto: create-drop

logging:
  level:
    org.springframework.data.rest: WARN
    root: WARN
~~~

Cấu hình này dành cho ứng dụng Spring Data REST dùng JPA và có H2 trong test dependencies. Database in-memory được tạo riêng cho test; schema được tạo khi context khởi động và loại bỏ khi context kết thúc. Không đưa dữ liệu production vào test database.

Nếu integration test phụ thuộc hành vi riêng của PostgreSQL, MySQL hoặc database thật đang dùng, nên chạy test trên đúng engine bằng Testcontainers hoặc một database test riêng. H2 có thể khác database production về kiểu dữ liệu, SQL dialect, constraint và transaction behavior.

Kích hoạt profile test trong Spring TestContext bằng @ActiveProfiles:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class OrderRestIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesOrderCollection() throws Exception {
        mockMvc.perform(get("/api/orders")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists());
    }
}
~~~

Các static import thường dùng:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
~~~

Test giả định repository đã được export tại /api/orders và ứng dụng có Spring MVC MockMvc test support. Điều chỉnh path và media type nếu ứng dụng tùy biến REST mapping.

Chạy test:

~~~bash
./mvnw test
~~~

Hoặc trên Windows:

~~~powershell
.\mvnw.cmd test
~~~

@ActiveProfiles("test") yêu cầu Spring TestContext kích hoạt profile test khi tạo application context. Nhờ đó integration test không phụ thuộc vào profile đang đặt trong terminal của lập trình viên. Nếu test dùng @SpringBootTest(properties = ...), @DynamicPropertySource hoặc @TestPropertySource, hãy nhớ các nguồn cấu hình dành riêng cho test có độ ưu tiên cao và có thể ghi đè giá trị trong file profile.

## 6. Cấu hình Production

Tạo src/main/resources/application-prod.yml:

~~~yaml
spring:
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate

logging:
  level:
    root: INFO

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: when-authorized
      probes:
        enabled: true
~~~

Ví dụ này vẫn giả định ứng dụng dùng Spring Data JPA:

- ddl-auto: validate yêu cầu Hibernate kiểm tra schema hiện có thay vì tự sửa schema khi ứng dụng khởi động. Dùng Flyway, Liquibase hoặc quy trình migration của tổ chức để thay đổi schema trước khi triển khai.
- open-in-view: false tránh giữ persistence context mở trong toàn bộ thời gian xử lý web request; kiểm tra và xử lý fetch strategy phù hợp trước khi bật.
- Log mặc định ở mức INFO; chỉ tăng log tạm thời khi có kế hoạch, phạm vi và thời hạn rõ ràng.
- Health details chỉ hiển thị cho người đã được cấp quyền phù hợp.
- Liveness và readiness probe hữu ích khi triển khai trên Kubernetes hoặc nền tảng hỗ trợ health probe.

Không đặt URL database, username, password, token hay private key thật trong file application-prod.yml. Hãy truyền chúng bằng secret manager, environment variable hoặc config tree do nền tảng triển khai mount vào container.

Ví dụ environment variables cho production:

~~~text
SPRING_PROFILES_ACTIVE=prod
SPRING_DATASOURCE_URL=jdbc:postgresql://db.internal:5432/spring_data_rest
SPRING_DATASOURCE_USERNAME=spring_app
SPRING_DATASOURCE_PASSWORD=<secret supplied by deployment platform>
~~~

Spring Boot relaxed binding chuyển tên property thành tên environment variable: dấu chấm thành dấu gạch dưới, bỏ dấu gạch ngang và chuyển thành chữ hoa. Vì vậy spring.datasource.password tương ứng SPRING_DATASOURCE_PASSWORD.

Có thể dùng config tree nếu nền tảng mount secret thành file. Ví dụ các file:

~~~text
/run/secrets/
  spring.datasource.username
  spring.datasource.password
~~~

Thêm vào application-prod.yml:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Spring Boot sẽ đọc tên file trong config tree thành tên property. Nếu dùng cách này, cấu hình mount secret phải tồn tại khi ứng dụng production khởi động; không đặt giá trị mặc định cho secret bắt buộc để tránh ứng dụng chạy với credential không mong muốn.

Kích hoạt production profile khi chạy:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar target/spring-data-rest-api.jar
~~~

Hoặc truyền profile trực tiếp:

~~~bash
java -jar target/spring-data-rest-api.jar --spring.profiles.active=prod
~~~

Trên nền tảng container/orchestrator, nên đặt profile và secret trong cấu hình deployment của workload. Không đóng gói secret vào JAR hoặc Docker image. Dùng cùng một artifact đã được kiểm thử để promote qua các môi trường; chỉ thay đổi runtime configuration.

## 7. Thứ tự ưu tiên cấu hình

Spring Boot tổng hợp property từ nhiều nguồn. Một nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị của nguồn thấp hơn. Với các nguồn thường dùng, có thể nhớ theo thứ tự tăng dần như sau:

1. Giá trị mặc định do ứng dụng đặt.
2. File cấu hình trong classpath, gồm application.yml và file profile-specific.
3. File cấu hình bên ngoài JAR.
4. OS environment variables.
5. Java system properties.
6. SPRING_APPLICATION_JSON.
7. Command-line arguments.
8. Một số nguồn dành riêng cho test như @SpringBootTest(properties=...), @DynamicPropertySource và @TestPropertySource có thể có độ ưu tiên cao hơn các nguồn runtime thông thường.

Thứ tự đầy đủ có thêm các nguồn như @PropertySource, JNDI và servlet context parameters. Hãy xem tài liệu Externalized Configuration khi cần xác định chính xác nguồn thắng trong một tình huống cụ thể.

Ví dụ, nếu application-prod.yml đặt server.port: 8080 nhưng deployment cung cấp SERVER_PORT=9090, giá trị từ environment variable sẽ được dùng. Command-line argument --server.port=9091 có thể ghi đè tiếp giá trị đó.

Một số điểm cần nhớ:

- File profile-specific ghi đè file chung khi cùng property được định nghĩa.
- File cấu hình bên ngoài JAR có thể ghi đè file đóng gói trong JAR.
- Với nhiều profile active, thứ tự profile ảnh hưởng giá trị cuối cùng.
- Không nhúng spring.profiles.active trong application-prod.yml; chọn profile từ runtime.
- Nếu dùng spring.config.location, danh sách location này thay thế các vị trí cấu hình mặc định. Nếu muốn bổ sung vị trí, xem xét spring.config.additional-location.
- Spring Boot nạp application.properties và các biến thể YAML ở những vị trí cấu hình chuẩn. Nên tránh để hai định dạng cùng định nghĩa một property.

## 8. Phân biệt Spring Profiles và @Profile

File application-{profile}.yml quyết định giá trị cấu hình được nạp. Annotation @Profile quyết định bean hoặc configuration class nào được đăng ký.

Ví dụ chỉ đăng ký một bean hỗ trợ phát triển:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("dev")
class DevelopmentConfiguration {

    // Khai báo bean chỉ dành cho môi trường development.
}
~~~

Có thể dùng @Profile trên @Component, @Configuration, @ConfigurationProperties hoặc bean method theo quy tắc của Spring. Không dùng profile để thay thế authorization: một endpoint hoặc repository chứa dữ liệu nhạy cảm vẫn phải được bảo vệ bằng Spring Security và chính sách phân quyền.

Với cấu hình ứng dụng riêng có nhiều trường, ưu tiên gom chúng vào class @ConfigurationProperties có kiểu dữ liệu rõ ràng và validation. Cách này giúp phát hiện cấu hình thiếu hoặc sai kiểu ngay khi khởi động thay vì rải nhiều chuỗi @Value trong service.

## 9. Actuator và kiểm tra trạng thái khi triển khai

Nếu dùng Spring Boot Actuator, endpoint health mặc định được expose qua HTTP tại /actuator/health. Khi bật health probes, có thể kiểm tra:

- /actuator/health/liveness: ứng dụng có còn sống và có nên tiếp tục chạy hay cần restart.
- /actuator/health/readiness: ứng dụng đã sẵn sàng nhận traffic hay chưa.

Khi triển khai Kubernetes, cấu hình liveness probe và readiness probe trỏ tới các endpoint tương ứng. Không đưa việc kiểm tra database hoặc dịch vụ ngoài vào liveness một cách máy móc: nếu database dùng chung tạm thời lỗi, Kubernetes có thể restart hàng loạt instance và làm tình hình xấu hơn. Readiness có thể xét phụ thuộc bên ngoài nếu quyết định đó phù hợp với cách hệ thống xử lý lỗi.

Chỉ expose các Actuator endpoint cần thiết. Tránh expose env, configprops, beans, heapdump hoặc * công khai vì các endpoint này có thể cung cấp thông tin nội bộ hoặc dữ liệu nhạy cảm. Nếu cần dùng để chẩn đoán, bảo vệ bằng Spring Security, network policy hoặc cơ chế kiểm soát truy cập của nền tảng.

## 10. Checklist trước khi deploy

### Development

- [ ] Profile dev được bật rõ ràng khi chạy local.
- [ ] Database local tách khỏi database test và production.
- [ ] Credential local không được commit vào Git.
- [ ] Log chi tiết và error message chỉ bật trong môi trường local có kiểm soát.
- [ ] Không đưa mock service hoặc dữ liệu giả vào profile production.

### Testing

- [ ] Test dùng @ActiveProfiles("test") hoặc cấu hình tương đương.
- [ ] Database test được tạo/cô lập và làm sạch theo vòng đời test.
- [ ] Integration test kiểm tra repository endpoint, base path, HAL response và các hành vi quan trọng.
- [ ] Test không đọc hoặc ghi vào database production.
- [ ] Nếu phụ thuộc SQL/dialect riêng, test với cùng loại database như production.

### Production

- [ ] Deployment đặt SPRING_PROFILES_ACTIVE=prod.
- [ ] Database URL và credential đến từ secret manager, environment variable hoặc config tree.
- [ ] Không có password, token hoặc private key trong source, JAR hay image.
- [ ] Schema được migration trước deploy; Hibernate không tự cập nhật schema production.
- [ ] Repository được export có chủ đích và endpoint có xác thực/phân quyền.
- [ ] Chỉ expose Actuator endpoint cần thiết; health details được bảo vệ.
- [ ] Health probes phù hợp với nền tảng triển khai.
- [ ] Cùng một artifact đã qua test được promote lên production.

## 11. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| Ứng dụng luôn dùng cấu hình mặc định | Chưa bật profile hoặc tên file không đúng | Kiểm tra SPRING_PROFILES_ACTIVE, tên application-{profile}.yml và log startup. |
| application-prod.yml không được nạp | Profile prod chưa active hoặc file đặt sai vị trí | Đặt SPRING_PROFILES_ACTIVE=prod; kiểm tra file nằm trong classpath hoặc external config location được khai báo. |
| spring.profiles.active báo lỗi trong file profile | Đặt thuộc tính active trong application-prod.yml hoặc document profile-specific | Chuyển việc chọn profile sang environment variable, system property hoặc command line. |
| Giá trị YAML không được dùng | Environment variable, system property hoặc command line có độ ưu tiên cao hơn | Kiểm tra property source đang override; xác nhận tên environment variable đúng relaxed binding. |
| Mật khẩu database không được bind | Sai tên biến môi trường hoặc secret chưa được mount | Với spring.datasource.password, dùng SPRING_DATASOURCE_PASSWORD; xác nhận deployment cung cấp biến hoặc config tree. |
| Test kết nối nhầm database local | Test không kích hoạt profile test | Dùng @ActiveProfiles("test"), xác nhận test datasource và không dựa vào biến môi trường của máy developer. |
| Test H2 pass nhưng production lỗi SQL | H2 khác engine hoặc dialect production | Chạy integration test với database tương ứng bằng Testcontainers hoặc database test riêng. |
| /api/orders trả 404 | Base path sai, repository chưa export hoặc mapping khác | Kiểm tra spring.data.rest.base-path, detection-strategy và @RepositoryRestResource trên repository. |
| /actuator/health/liveness trả 404 | Health probes chưa được bật hoặc Actuator chưa có trong classpath | Kiểm tra dependency Actuator và management.endpoint.health.probes.enabled. |
| Không đọc được chi tiết health | show-details là never hoặc người gọi chưa được authorize | Giữ mặc định an toàn ở production; cấu hình role và security nếu operator cần xem chi tiết. |
| Production không khởi động do ddl-auto: validate | Schema chưa được migration hoặc không tương thích entity | Chạy migration đúng phiên bản trước khi triển khai, kiểm tra schema và cấu hình kết nối. |

Để xác định property cuối cùng đến từ nguồn nào, Spring Boot có thể hỗ trợ chẩn đoán bằng env và configprops Actuator endpoint. Chỉ expose tạm thời trong môi trường được bảo vệ; các giá trị nhạy cảm mặc định được sanitize nhưng endpoint vẫn tiết lộ cấu trúc cấu hình nội bộ.

## 12. Tài liệu tham khảo chính thức

- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): kích hoạt profile, profile mặc định, include, profile group và file cấu hình theo profile.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): thứ tự ưu tiên property source, profile-specific file, environment variables, config import và configuration tree.
- [Spring Data REST — Getting Started / Basic Settings](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): repository detection strategy, base path và các property cấu hình Spring Data REST.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): danh sách property được Spring Boot hỗ trợ, gồm spring.data.rest.*, spring.datasource.* và management.*.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure, bảo vệ endpoint, health details, liveness và readiness probes.
- [Spring Framework — Context Configuration with Environment Profiles](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/env-profiles.html): dùng @ActiveProfiles trong Spring TestContext.
- [Spring Framework — Integration Testing](https://docs.spring.io/spring-framework/reference/testing/integration.html): kiểm thử wiring, persistence và ứng dụng Spring mà không cần triển khai lên application server.
