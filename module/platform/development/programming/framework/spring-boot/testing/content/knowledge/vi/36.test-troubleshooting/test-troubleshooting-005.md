# Thiếu bean trong slice, import dư và vòng phụ thuộc cấu hình

## 1. Mục tiêu của bài học

Một trong những lỗi dễ làm mất thời gian nhất khi kiểm thử Spring Boot là test vừa chạy đã dừng với `Failed to load ApplicationContext`. Người đọc nhìn vào thông báo cuối cùng, thêm `@Import` cho vài class, bật `spring.main.allow-circular-references=true` hoặc đổi tất cả sang `@SpringBootTest`. Test có thể xanh tạm thời nhưng nguyên nhân thực tế chưa được giải quyết: **test slice cố tình không nạp bean ngoài phạm vi**, một import quá rộng kéo thêm cả cấu hình không cần thiết, hoặc bean graph chứa vòng phụ thuộc khiến Spring không thể tạo các bean.

Bài này thuộc nhóm **Chẩn đoán lỗi kiểm thử** của module **Spring Boot - testing**, có đề bài chính **Thiếu bean trong slice, import dư và vòng phụ thuộc cấu hình**.

Sau khi hoàn thành, bạn có thể:

1. Phân biệt **`NoSuchBeanDefinitionException`**, **`NoUniqueBeanDefinitionException`**, **`UnsatisfiedDependencyException`**, **`BeanCreationException`** và **`BeanCurrentlyInCreationException`**.
2. Hiểu vì sao `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@RestClientTest`, `@WebFluxTest` không nạp toàn bộ business services như `@SpringBootTest`.
3. Chọn chính xác giữa `@MockBean`, `@Import`, `@TestConfiguration`, `@EnableConfigurationProperties` và `@SpringBootTest`.
4. Tránh import cả một `@Configuration` chứa database client, messaging, scheduling, security hoặc `@ComponentScan` chỉ để có một helper.
5. Nhận diện **vòng constructor injection**, vòng ở `@Bean` factory methods, vòng giữa test configurations và hiện tượng phụ thuộc ngầm khi cấu hình bị import thừa.
6. Dùng `ApplicationContextRunner` để kiểm tình huống context **dự kiến khởi động lỗi** mà không khiến JUnit suite đỏ.
7. Tái hiện một project Java 17, Spring Boot 3.3.5, Gradle/JUnit Jupiter với các slices MVC, JPA, JSON và full context hoạt động đúng.
8. Biết cách đọc **root cause đầu tiên** của startup failure, thay vì chỉ sửa theo dòng lỗi cuối.
9. Chẩn đoán các bẫy như explicit `@ComponentScan`, `@ContextConfiguration`, security filters, component scanning, package hierarchy và cache failure threshold.
10. Viết regression tests cho đúng bean graph sau khi sửa và phân biệt lỗi environment với lỗi wiring.

**Nguyên tắc:** Đừng đặt mục tiêu “làm sao để mọi bean xuất hiện trong slice”. Mục tiêu là **lấy đúng tập bean cần thiết cho câu hỏi mà test đang kiểm**. Một test MVC chỉ cần controller, MVC infrastructure và collaborators được mô phỏng có chủ đích; một test repository chỉ cần JPA/repository/entity; một full-context integration test mới phải chứng minh toàn bộ wiring.

## 2. Mô hình tư duy: Spring context là đồ thị dependency

Hãy tưởng tượng một ứng dụng bán hàng:

~~~text
PurchaseController
  |
  +--> PurchaseService
  |       |
  |       +--> PurchaseRepository
  |                 |
  |                 +--> DataSource / JPA EntityManager
  |
  +--> CustomerLabelFormatter

ApiExceptionHandler
~~~

Trong **full application context**, Spring có thể tạo controller, service, repository, formatter và cơ sở dữ liệu. Nhưng khi dùng `@WebMvcTest(PurchaseController.class)`, Spring Boot chỉ đưa phần web phù hợp vào test context; `@Service`, repository thông thường và helper `@Component` không tự động có mặt.

~~~text
@WebMvcTest(PurchaseController.class)
  |
  +--> PurchaseController
  +--> MVC infrastructure, Jackson, ControllerAdvice...
  +--> PurchaseService?       KHÔNG tự nạp
  +--> PurchaseRepository?    KHÔNG tự nạp
  +--> CustomerLabelFormatter? KHÔNG tự nạp nếu chỉ là @Component
~~~

Nếu constructor của `PurchaseController` yêu cầu `PurchaseService` mà test chưa tạo collaborator, Spring không thể tạo controller. Trong trường hợp đó, **thiếu bean là thiết kế bình thường của slice**, không phải Spring “quên scan”.

Cách xử lý tùy mục tiêu:

- Kiểm request mapping/JSON/status của controller: dùng `@MockBean PurchaseService`.
- Kiểm logic helper formatter thật trong MVC: dùng `@Import(CustomerLabelFormatter.class)`.
- Kiểm repository/SQL: dùng `@DataJpaTest`, không import toàn bộ controller/service.
- Kiểm wiring end-to-end trong ứng dụng: dùng `@SpringBootTest` với database/test dependencies thích hợp.
- Kiểm một bean graph nhỏ thất bại do wiring: dùng `ApplicationContextRunner` hoặc `AnnotationConfigApplicationContext` độc lập.

Một **slice test** không phải “full-context chạy nhanh hơn”; nó có **hợp đồng bean visibility riêng**.

## 3. Đọc exception cho đúng: lớp ngoài và root cause

Các chuỗi lỗi hay gặp:

~~~text
java.lang.IllegalStateException:
  Failed to load ApplicationContext
Caused by: org.springframework.beans.factory.UnsatisfiedDependencyException:
  Error creating bean 'purchaseController'
Caused by: org.springframework.beans.factory.NoSuchBeanDefinitionException:
  No qualifying bean of type 'PurchaseService' available
~~~

Chỉ nhìn `IllegalStateException` sẽ dễ nghĩ toàn bộ Spring context có lỗi. Thực tế root cause là **không có bean PurchaseService** trong test context. Với `@WebMvcTest`, điều này thường là vì slice loại business service khỏi component scanning.

Một chuỗi khác:

~~~text
BeanCreationException: Error creating bean 'alpha'
Caused by: UnsatisfiedDependencyException:
  Error creating bean 'beta'
Caused by: BeanCurrentlyInCreationException:
  Requested bean 'alpha' is currently in creation
~~~

Đây là vòng phụ thuộc. Cách giải không phải thêm `@MockBean` lung tung mà là kiểm thiết kế graph `Alpha -> Beta -> Alpha`.

### 3.1. Phân loại nhanh

| Loại lỗi | Ý nghĩa thường gặp | Đầu tiên cần kiểm |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | Không có bean đúng type/qualifier | Slice filter, package scan, @Import/@MockBean |
| `UnsatisfiedDependencyException` | Dependency của một constructor/field/bean method không thỏa | Đọc nested cause, bean cần dependency nào |
| `NoUniqueBeanDefinitionException` | Có nhiều ứng viên, Spring không chọn được một | @Qualifier, @Primary, tên bean |
| `BeanCurrentlyInCreationException` | Bean đang được tạo lại khi chưa hoàn tất; thường circular reference | Đồ thị constructor/@Bean methods |
| `BeanCreationException` | Bean factory/init/@PostConstruct/property/conversion fail | Root cause sâu hơn |
| `BeanDefinitionOverrideException` | Hai definitions trùng tên trong chế độ không cho override | Các @Import/@ComponentScan mang bean trùng |
| `ConfigurationPropertiesBindException` | Bind property vào type không hợp lệ | Prefix, keys, validation, active profile |
| `ClassNotFoundException` / `NoClassDefFoundError` | Classpath/dependency version sai hoặc thiếu | Gradle dependencies/Boot BOM |
| `Failed to configure a DataSource` | DB auto-configuration không có URL/driver phù hợp | Test slice, embedded DB, properties |
| `ApplicationContext failure threshold exceeded` | Context key đã fail trước đó; Spring ngừng thử tiếp | Tìm **lần lỗi đầu tiên**, không sửa threshold trước |

**Không phải mọi “No qualifying bean” đều do slice:** có thể class nằm ngoài scan root, bị `@Profile` loại, `@ConditionalOnProperty` không match, qualifier sai, một `@Bean` method không được import, hay dependency chưa có trên classpath.

### 3.2. Hướng lần ngược stacktrace

1. Tìm test class và annotation tạo context.
2. Tìm dòng `Error creating bean with name ...`.
3. Theo `Caused by` đến root cause thực.
4. Xác định bean đó **có nên thuộc scope test này không**.
5. Đọc bean constructor và các dependency type/qualifier.
6. Kiểm config source, active profiles, conditional annotations, nested @TestConfiguration.
7. Chọn fix nhỏ nhất: mock một collaborator, import đúng bean, cấu hình test data, hoặc đổi test scope.
8. Chạy riêng failing test và toàn test module; đối chiếu error sau sửa.

Đừng tìm một class có tên “config” rồi import vô điều kiện.

## 4. Các test slice và bean mặc định được cung cấp

| Annotation Boot 3.3 | Mục tiêu | Beans thông thường được quan tâm | Không nên kỳ vọng |
| --- | --- | --- | --- |
| `@WebMvcTest` | HTTP mapping, controller, MVC validation, serialization | Controllers, controller advice, MVC converters/filters/configurer phù hợp | Business @Service, repository, arbitrary @Component |
| `@WebFluxTest` | Reactive web controller | Reactive controllers, WebFlux codecs, WebTestClient | Business services/repositories tùy ý |
| `@DataJpaTest` | JPA entities/repositories | EntityManager, JPA repository, embedded DB nếu có | MVC controller và regular services |
| `@JdbcTest` | JDBC query / JdbcTemplate | DataSource, JdbcTemplate, transactions | Business services và MVC |
| `@DataJdbcTest` | Spring Data JDBC | Repositories Data JDBC và JDBC layer | Toàn bộ app |
| `@JsonTest` | JSON serialization/deserialization | ObjectMapper, Jackson modules, JacksonTester | Service/HTTP server |
| `@RestClientTest` | HTTP client adapter | RestTemplateBuilder/RestClient.Builder, MockRestServiceServer theo support | Remote server thật, toàn app |
| `@GraphQlTest` | GraphQL controller/schema test | GraphQlTester và GraphQL slice components | Business graph đầy đủ |
| `@SpringBootTest` | Full Spring wiring, app integration | Phần lớn beans phù hợp main config/classpath | Không tự bảo đảm external DB/Redis hoạt động nếu thiếu setup |

Danh sách là hướng dẫn phạm vi, không mô tả toàn bộ auto-configuration. Một slice có các **type exclude filters** và chỉ một tập auto-configurations đã chọn; một `@Import`, `@ComponentScan` tùy ý có thể phá sự tách biệt đó.

### 4.1. @WebMvcTest

Trong Boot 3.3, `@WebMvcTest` chọn các thành phần MVC như `@Controller`, `@ControllerAdvice`, `@JsonComponent`, `Converter`, `Filter`, `HandlerInterceptor`, `WebMvcConfigurer` và các loại infrastructure thích hợp. **Regular @Component và @Service không được scan như full application**. Vì vậy collaborator của controller cần `@MockBean` hoặc import có chủ đích.

### 4.2. @DataJpaTest

`@DataJpaTest` tự cấu hình JPA, scan `@Entity`/repositories và thường dùng embedded database có trên test classpath. Test mặc định transactional, rollback sau method. `@Service` nghiệp vụ không tự được scan. Nếu test repository cần converter custom, hãy import đúng converter; nếu logic service là đối tượng cần kiểm, chuyển sang một integration test có chủ đích.

### 4.3. @JsonTest

`@JsonTest` phù hợp với Jackson serialization contract và `JacksonTester<T>`, không nên import REST controller/database chỉ để serialize một DTO. Nếu thiếu một Jackson module, import module/configuration cần thiết thay vì full application graph.

### 4.4. Cảnh báo phối hợp nhiều slices

Spring Boot **không hỗ trợ gắn nhiều test slice annotations như `@WebMvcTest` và `@DataJpaTest` trên cùng test class** để ghép hai halves. Nếu thực sự cần tích hợp MVC và repository, dùng `@SpringBootTest` + `@AutoConfigureMockMvc` hoặc chỉ một slice kết hợp các `@AutoConfigure...` rất có chủ đích. Không cố “đánh lừa” test type filters.

## 5. Chọn @MockBean, @Import, @TestConfiguration hay full context?

### @MockBean — thay collaborator để test boundary

~~~java
@WebMvcTest(PurchaseController.class)
class PurchaseWebSliceTest {

    @MockBean
    PurchaseService service;
}
~~~

Trong Boot 3.3, `@MockBean` bổ sung hoặc thay thế một bean trong Spring test `ApplicationContext`, khác `@Mock` chỉ tạo Mockito object ngoài Spring. Với controller test chỉ quan tâm mapping, response và error, mock service là lựa chọn thường đúng.

`@MockBean` không có nghĩa unit test business service; bạn cần test riêng `PurchaseService` với repository fake/mock hoặc full JPA integration.

### @Import — đưa đúng collaborator thật vào scope

~~~java
@WebMvcTest(PurchaseController.class)
@Import(CustomerLabelFormatter.class)
class PurchaseWebSliceTest {
}
~~~

`CustomerLabelFormatter` là helper ít dependency, không kết nối DB/network. Import cụ thể class này giúp controller thật dùng business formatting thật mà không kéo toàn bộ application service/repository graph.

`@Import` cũng có thể import `@Configuration` class chứa nhiều `@Bean`, nên phải kiểm nó sẽ kéo những gì. Một import nằm trên annotation base test áp dụng cho hàng chục classes có thể làm contexts lớn và khó chẩn đoán.

### @TestConfiguration — tạo test-only beans

~~~java
@SpringBootTest
class PaymentIntegrationTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class StubConfiguration {
        @Bean
        ExternalPaymentGateway paymentGateway() {
            return new FakePaymentGateway();
        }
    }
}
~~~

Đây là **snippet minh họa**, chưa có khai báo FakePaymentGateway. Trong Boot, nested `@TestConfiguration` có thể bổ sung cấu hình test bên cạnh main application configuration. Nó khác một nested plain `@Configuration` có thể được coi là primary test configuration thay thế việc khám phá main app.

Không đặt toàn bộ fake services trong một `@TestConfiguration` global rồi import khắp tests; mỗi fixture nên có scope/ownership rõ.

### @EnableConfigurationProperties — đưa config properties vào slice

~~~java
@WebMvcTest(PurchaseController.class)
@EnableConfigurationProperties(PurchaseViewProperties.class)
class PurchaseConfigurationTest {
}
~~~

Snippet minh họa. Các regular `@ConfigurationProperties` beans không luôn được scan trong slice. Nếu controller/advice/mapper cần properties class thật, đăng ký class đó có chủ đích và cung cấp test properties phù hợp.

### @SpringBootTest — kiểm full wiring

~~~java
@SpringBootTest(
    classes = DiagnosticApplication.class)
@AutoConfigureMockMvc
class FullHttpWiringTest {
}
~~~

Khi bài test đòi controller → service → repository → database, việc mock service làm mất mục tiêu integration. `@SpringBootTest` cùng database test setup là lựa chọn phù hợp. Không coi đây là “sửa” một @WebMvcTest thiếu bean nếu ban đầu chỉ muốn MVC mapping.

## 6. Import dư: hiệu ứng domino và tín hiệu nhận biết

Một cấu hình production có thể chứa:

~~~text
BillingConfiguration
  |
  +--> PaymentGatewayClient
          |
          +--> OAuthTokenProvider
                  |
                  +--> SecretStoreClient
                          |
                          +--> CloudCredentials

  +--> WebhookPublisher
          |
          +--> KafkaTemplate
                  |
                  +--> Kafka ProducerFactory
~~~

Nếu một `@WebMvcTest` chỉ cần một format converter nhưng bạn thêm:

~~~java
@Import(BillingConfiguration.class)
~~~

Spring có thể buộc tạo nhiều bean không liên quan. Failure ban đầu “thiếu một mapper” được thay bằng “thiếu CloudCredentials”, “Kafka bootstrap server không thể kết nối” hoặc “BeanCurrentlyInCreation”. Test vẫn không tập trung vào MVC.

### Dấu hiệu của import dư

- Startup time của `@WebMvcTest` gần bằng `@SpringBootTest`.
- Log bắt đầu tạo DataSource, Kafka/Redis clients dù test chỉ gọi MockMvc.
- `UnsatisfiedDependencyException` xuất hiện ở bean không thuộc layer đang test.
- Test chạy được trên laptop có env vars nhưng fail CI thiếu credentials.
- Context cache keys rất đa dạng do mỗi test import một cấu hình khác nhau.
- `@MockBean` mọc thêm từng lớp để bù cho beans bị import vô tình.
- Một `@Import` chung làm test vô tình phụ thuộc network.

**Cách sửa:** bỏ import rộng, nhập đúng helper/mapper/configuration nhỏ. Nếu graph thực sự cần mọi tầng, chủ động chọn full-context test và dựng fixtures theo đúng điều kiện.

## 7. Những import/configuration có thể vô tình phá slice

### 7.1. @ComponentScan khai báo lại trên main application

~~~java
@SpringBootApplication
@ComponentScan("com.example")
public class DiagnosticApplication {
}
~~~

Đây là **anti-pattern minh họa**, không có trong runnable project. Theo hướng dẫn Spring Boot, explicit `@ComponentScan` đặt trên class `@SpringBootApplication` có thể làm mất các exclude filters mà Boot dùng cho test slices, khiến `@DataJpaTest` nạp cả regular components và configs.

**Nên:** giữ `@SpringBootApplication` không kèm component scan tùy ý nếu package layout hợp lý, hoặc tách component scan đặc thù sang cấu hình riêng chỉ import khi cần. Không vội thêm `excludeFilters` bừa nếu có thể giải quyết bằng cấu trúc package.

### 7.2. @Import auto-configuration bằng annotation không phù hợp

Khi muốn thêm một **auto-configuration** vào slice, Spring Boot khuyến nghị `@ImportAutoConfiguration(...)`, **không** dùng plain `@Import(...)` để nhập auto-configuration vì Boot xử lý auto-configurations theo cơ chế riêng.

~~~java
@JdbcTest
@ImportAutoConfiguration(IntegrationAutoConfiguration.class)
class JdbcWithIntegrationTest {
}
~~~

Snippet minh họa, không nằm trong runnable lab. `@Import` phù hợp cho **regular configuration/helper classes**; `@ImportAutoConfiguration` dành cho Boot auto-configuration bổ sung.

### 7.3. Test @ContextConfiguration(classes = ...) vô tình thay primary config

Nếu gắn nested `@Configuration` như primary source hoặc truyền `classes` không chứa main app configuration trong `@SpringBootTest`, test có thể mất component scanning, entities hoặc repositories dự kiến. Đừng sửa bằng việc import mọi class. Xác định configuration source thực sự có hiệu lực.

### 7.4. Main application chứa cấu hình chuyên biệt quá sớm

Một `@SpringBootApplication` cùng `@EnableMongoAuditing`, `@EnableScheduling` hoặc các custom import trên top-level có thể khiến slices kéo cấu hình không cần. Đưa cấu hình chuyên biệt sang class `@Configuration` ở phạm vi rõ ràng, chỉ import ở test cần nó.

## 8. Vòng phụ thuộc: không chỉ “bean thiếu”

Một vòng constructor injection:

~~~text
AlphaService ---> BetaService
      ^               |
      |_______________|
~~~

Code minh họa:

~~~java
final class AlphaService {
    AlphaService(BetaService beta) {}
}
final class BetaService {
    BetaService(AlphaService alpha) {}
}
~~~

Không thể tạo `AlphaService` trước `BetaService` vì cần `BetaService` hoàn tất; cũng không thể tạo `BetaService` trước `AlphaService`. Spring thường báo `BeanCurrentlyInCreationException` dưới chuỗi `UnsatisfiedDependencyException`/`BeanCreationException`.

### 8.1. Không bật circular references để né lỗi

Trong Spring Boot hiện đại, circular references được vô hiệu hóa theo mặc định. Thuộc tính:

~~~properties
spring.main.allow-circular-references=true
~~~

không phải hướng sửa được khuyến nghị; ngay cả khi bật, **vòng constructor injection thuần túy không thể giải quyết bằng setter early references**. Bật setting có thể che mùi thiết kế và tạo hành vi khó debug.

### 8.2. Sửa đồ thị phụ thuộc

Tách trách nhiệm:

~~~text
Trước:
  InvoiceService --> NotificationService
        ^                  |
        |__________________|

Sau:
  InvoiceService ---> NotificationPort
  NotificationService ---> InvoiceEvents
  ApplicationService điều phối cả hai
~~~

Một port/event/higher-level orchestrator có thể bỏ vòng bằng cách làm rõ dependency direction. Đừng thay một constructor bằng `@Lazy` chỉ để test xanh nếu domain graph vẫn không có hướng rõ.

### 8.3. @Lazy và ObjectProvider

`@Lazy` hoặc `ObjectProvider<T>` có thể trì hoãn resolution và phù hợp một số use cases chính đáng như optional dependency, plugin lookup hoặc startup laziness. Nhưng nó không tự sửa **business cycle**; một code path gọi lazy bean sau startup vẫn có thể recursion/logic bug. Với constructor cycles, ưu tiên **refactor**, không coi @Lazy là mặc định.

### 8.4. Vòng giữa @Bean methods

~~~java
@Configuration(proxyBeanMethods = false)
class CycleConfig {
    @Bean Alpha alpha(Beta beta) {
        return new Alpha(beta);
    }

    @Bean Beta beta(Alpha alpha) {
        return new Beta(alpha);
    }
}
~~~

Đây là **mẫu lỗi minh họa**, giả sử Alpha/Beta có constructors tương ứng. Parameter dependency tạo vòng. Đặt `proxyBeanMethods=false` **không** xóa vòng do method parameters; nó chỉ thay cách proxy những calls tới @Bean methods trên configuration class.

### 8.5. Vòng do @Configuration constructor injection

Nếu `WebConfig` constructor cần `SecurityConfig` còn `SecurityConfig` constructor cần `WebConfig`, cả hai là bean definitions cấu hình không thể được dựng xong. Không vá bằng import cả hai vào slice; sửa hướng dependency hoặc tách config properties/constants/interface.

## 9. Project runnable: Java 17 + Spring Boot 3.3.5 + Gradle

Dự án nhỏ minh họa:

- Production app có `PurchaseController`, `PurchaseService`, `PurchaseRepository`, JPA entity `Purchase`, `CustomerLabelFormatter`, `ApiErrorHandler`.
- MVC slice **mock service** và **import đúng formatter**.
- JPA slice dùng H2 test database và xác minh service không được scan trong slice.
- JSON slice chỉ kiểm DTO/Jackson, không cần DB.
- Full-context test kiểm Controller → Service → Repository với MockMvc.
- `ApplicationContextRunner` kiểm **missing dependency**, **circular constructor injection**, **unnecessary extra registration** và **ambiguous bean** như các negative demonstrations, nhưng mọi JUnit test vẫn PASS khi phát hiện lỗi dự kiến.

Không cần Docker, external PostgreSQL hay real HTTP port. H2 chỉ nằm trong **test runtime**; nếu chạy application production, phải cấu hình DataSource thật thay vì dựa vào H2 test dependency.

### 9.1. Cây thư mục

~~~text
slice-diagnostics-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/slicediag/
    │   ├── DiagnosticApplication.java
    │   ├── model/Purchase.java
    │   ├── model/PurchaseRepository.java
    │   ├── model/PurchaseNotFoundException.java
    │   ├── service/PurchaseService.java
    │   ├── web/CustomerLabelFormatter.java
    │   ├── web/PurchaseDto.java
    │   ├── web/PurchaseController.java
    │   └── web/ApiErrorHandler.java
    └── test/
        ├── resources/application.properties
        └── java/com/example/slicediag/
            ├── PurchaseWebSliceTest.java
            ├── PurchaseJpaSliceTest.java
            ├── PurchaseJsonSliceTest.java
            ├── PurchaseFullContextTest.java
            └── ContextGraphDiagnosticsTest.java
~~~

Gradle Wrapper binary/scripts cần được sinh bằng Gradle hoặc có sẵn trong repository. Markdown không chứa binary `gradle-wrapper.jar`.

### 9.2. settings.gradle

~~~groovy
rootProject.name = 'slice-diagnostics-lab'
~~~

### 9.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testRuntimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'skipped', 'failed'
        exceptionFormat 'full'
        showStandardStreams = false
    }
}
~~~

**Vì sao có JPA và H2?** Để mô phỏng một hệ thống nhiều tầng, cho thấy `@WebMvcTest` không có repository/DataSource mặc dù project có JPA dependency. `@DataJpaTest` cần embedded DB trong test; H2 testRuntimeOnly đáp ứng bài lab. Không có network server bên ngoài.

**Vì sao không thêm spring-boot-starter-security?** Security filter chain có thể trả 401/403 trước controller, làm phân tâm khỏi lỗi bean graph. Dự án production có Security cần kiểm đúng configuration/access, không tắt security chỉ để làm test xanh.

### 9.4. src/test/resources/application.properties

~~~properties
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
~~~

Config test đảm bảo H2 schema được tạo bởi Hibernate trong full context/data slice. Trong production, schema phải được quản lý bởi migrations và cấu hình database riêng; không sao chép `create-drop` sang production.

### 9.5. DiagnosticApplication.java

~~~java
package com.example.slicediag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiagnosticApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiagnosticApplication.class, args);
    }
}
~~~

Không khai báo thêm `@ComponentScan` tùy ý, vì Spring Boot tự scan subpackages thuộc `com.example.slicediag` và vẫn giữ các slice type filters.

## 10. Data model và Spring Data repository

### 10.1. src/main/java/com/example/slicediag/model/Purchase.java

~~~java
package com.example.slicediag.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchases")
public class Purchase {

    @Id
    private Long id;

    @Column(nullable = false)
    private String customer;

    @Column(nullable = false)
    private long totalCents;

    protected Purchase() {
    }

    public Purchase(Long id, String customer, long totalCents) {
        this.id = id;
        this.customer = customer;
        this.totalCents = totalCents;
    }

    public Long getId() {
        return id;
    }

    public String getCustomer() {
        return customer;
    }

    public long getTotalCents() {
        return totalCents;
    }
}
~~~

Constructor protected rỗng phù hợp JPA. Dùng Java 17 và `jakarta.persistence` (không dùng `javax.persistence` từ Boot 2.x). Khóa id được gán trong fixture, không cần generated sequences.

### 10.2. src/main/java/com/example/slicediag/model/PurchaseRepository.java

~~~java
package com.example.slicediag.model;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseRepository
        extends JpaRepository<Purchase, Long> {
}
~~~

Spring Data JPA tạo implementation từ interface trong `@DataJpaTest` hoặc full application context khi JPA auto-configuration phù hợp. `@WebMvcTest` không tự load repository này.

### 10.3. src/main/java/com/example/slicediag/model/PurchaseNotFoundException.java

~~~java
package com.example.slicediag.model;

public class PurchaseNotFoundException
        extends RuntimeException {

    public PurchaseNotFoundException(long id) {
        super("Purchase not found: " + id);
    }
}
~~~

Exception là domain signal. Trong MVC boundary, `ApiErrorHandler` chuyển nó thành HTTP 404; không biến thành “missing bean” chỉ vì service throw exception ở runtime.

## 11. Service, formatter và REST controller

### 11.1. src/main/java/com/example/slicediag/service/PurchaseService.java

~~~java
package com.example.slicediag.service;

import com.example.slicediag.model.Purchase;
import com.example.slicediag.model.PurchaseNotFoundException;
import com.example.slicediag.model.PurchaseRepository;

import org.springframework.stereotype.Service;

@Service
public class PurchaseService {

    private final PurchaseRepository repository;

    public PurchaseService(PurchaseRepository repository) {
        this.repository = repository;
    }

    public Purchase find(long id) {
        return repository.findById(id)
            .orElseThrow(
                () -> new PurchaseNotFoundException(id));
    }
}
~~~

Constructor injection bộc lộ dependency rõ. Trong full context, Spring tìm repository bean. Trong MVC slice, service sẽ không tự xuất hiện, vì vậy controller cần mock service nếu mục đích chỉ là kiểm MVC.

### 11.2. src/main/java/com/example/slicediag/web/CustomerLabelFormatter.java

~~~java
package com.example.slicediag.web;

import org.springframework.stereotype.Component;

@Component
public class CustomerLabelFormatter {

    public String format(String customer) {
        if (customer == null || customer.isBlank()) {
            throw new IllegalArgumentException(
                "customer must not be blank");
        }
        return "Khách: " + customer.trim();
    }
}
~~~

Helper này không phụ thuộc DB hoặc network. `@Component` làm nó có trong **full context**, nhưng `@WebMvcTest` không tự scan arbitrary components. Khi muốn thực hiện formatter thật trong slice, dùng **`@Import(CustomerLabelFormatter.class)`**.

### 11.3. src/main/java/com/example/slicediag/web/PurchaseDto.java

~~~java
package com.example.slicediag.web;

public record PurchaseDto(
        long id,
        String customerLabel,
        long totalCents) {
}
~~~

DTO record chạy trên Java 17, Jackson serialize thành JSON fields `id`, `customerLabel`, `totalCents`.

### 11.4. src/main/java/com/example/slicediag/web/PurchaseController.java

~~~java
package com.example.slicediag.web;

import com.example.slicediag.model.Purchase;
import com.example.slicediag.service.PurchaseService;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/purchases")
public class PurchaseController {

    private final PurchaseService service;
    private final CustomerLabelFormatter formatter;

    public PurchaseController(
            PurchaseService service,
            CustomerLabelFormatter formatter) {

        this.service = service;
        this.formatter = formatter;
    }

    @GetMapping("/{id}")
    public PurchaseDto find(@PathVariable long id) {
        Purchase purchase = service.find(id);

        return new PurchaseDto(
            purchase.getId(),
            formatter.format(purchase.getCustomer()),
            purchase.getTotalCents());
    }
}
~~~

Controller cần **hai dependencies**: business `PurchaseService` và formatter. Slice cần mock dependency business, import formatter thật. Full context scan tự tạo cả hai.

### 11.5. src/main/java/com/example/slicediag/web/ApiErrorHandler.java

~~~java
package com.example.slicediag.web;

import com.example.slicediag.model.PurchaseNotFoundException;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(PurchaseNotFoundException.class)
    public ResponseEntity<ApiError> purchaseMissing() {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("PURCHASE_NOT_FOUND"));
    }

    public record ApiError(String code) {
    }
}
~~~

`@RestControllerAdvice` được `@WebMvcTest` đưa vào MVC scope theo filter; không cần import toàn bộ production configuration để có handler. Nếu advice của dự án phụ thuộc external service, nên cân nhắc tách logic và thiết kế mock phù hợp.



## 12. MVC slice đúng: một mock và một import hẹp

**src/test/java/com/example/slicediag/PurchaseWebSliceTest.java**

~~~java
package com.example.slicediag;

import com.example.slicediag.model.Purchase;
import com.example.slicediag.model.PurchaseNotFoundException;
import com.example.slicediag.model.PurchaseRepository;
import com.example.slicediag.service.PurchaseService;
import com.example.slicediag.web.CustomerLabelFormatter;
import com.example.slicediag.web.PurchaseController;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(PurchaseController.class)
@Import(CustomerLabelFormatter.class)
class PurchaseWebSliceTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ApplicationContext context;

    @Autowired
    CustomerLabelFormatter formatter;

    @MockBean
    PurchaseService service;

    @Test
    void controllerUsesMockedServiceAndRealFormatter()
            throws Exception {

        when(service.find(7L))
            .thenReturn(new Purchase(7L, " An ", 1999L));

        mvc.perform(get("/api/purchases/7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.customerLabel")
                .value("Khách: An"))
            .andExpect(jsonPath("$.totalCents")
                .value(1999));

        verify(service).find(7L);
    }

    @Test
    void controllerAdviceConvertsDomainErrorTo404()
            throws Exception {

        when(service.find(404L))
            .thenThrow(new PurchaseNotFoundException(404L));

        mvc.perform(get("/api/purchases/404"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code")
                .value("PURCHASE_NOT_FOUND"));
    }

    @Test
    void sliceContainsMockButNotRepositoryBean() {
        assertTrue(mockingDetails(service).isMock());
        assertNotNull(formatter);

        assertEquals(
            0,
            context.getBeanNamesForType(
                PurchaseRepository.class).length);
    }
}
~~~

### 12.1. Vì sao test này compile/start được?

`@WebMvcTest(PurchaseController.class)` tạo MVC infrastructure, controller và advice. `@MockBean PurchaseService` bổ sung bean đủ type cho constructor controller. `@Import(CustomerLabelFormatter.class)` thêm **một helper** vào context. Repository/DataSource không cần và không được tự nạp.

**Không thay `@MockBean` bằng Mockito `@Mock`** khi controller được Spring tạo: `@Mock` chỉ thuộc object trong JUnit test class, Spring sẽ không tự inject nó vào controller bean. Nếu dùng `@InjectMocks` với controller tự khởi tạo, đó là một pure unit test khác, không kiểm MVC annotations/serialization.

### 12.2. Vì sao không @Import(PurchaseService.class)?

Trong ví dụ, `PurchaseService` có constructor cần `PurchaseRepository`. Import service thật làm phát sinh tiếp một missing bean repository trong MVC slice. Sau đó import repository/JPA/DataSource sẽ làm mất mục tiêu MVC isolation. Nếu muốn kiểm repository thật, hãy dùng `@SpringBootTest` + H2/DB thích hợp.

### 12.3. Tại sao dùng @MockBean trên class có @Service?

Trong Boot 3.3, `@MockBean` có thể **đăng ký mock mới** khi type không có trong slice, hoặc thay bean hiện có khi suitable. Vì vậy không cần đưa implementation service vào slice trước. Đây là API chính thức của Boot 3.3. Với Boot 3.4+ một số mock APIs được deprecate/tiến hóa, nên luôn đối chiếu version BOM; bài không dùng `@MockitoBean` của Spring Framework 6.2 để tránh import sai trong Boot 3.3.

### 12.4. Một green MVC test không chứng minh service/repository wiring

Khi service mock trả `Purchase`, controller test pass dù repository implementation production đang lỗi. Đó là lý do project có các test JPA và full-context riêng.

## 13. JPA slice đúng: repository có, service không

**src/test/java/com/example/slicediag/PurchaseJpaSliceTest.java**

~~~java
package com.example.slicediag;

import com.example.slicediag.model.Purchase;
import com.example.slicediag.model.PurchaseRepository;
import com.example.slicediag.service.PurchaseService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.context.ApplicationContext;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;

import static org.junit.jupiter.api.Assertions.*;

@DataJpaTest
class PurchaseJpaSliceTest {

    @Autowired
    PurchaseRepository repository;

    @Autowired
    TestEntityManager entityManager;

    @Autowired
    ApplicationContext context;

    @Test
    void repositoryPersistsAndReadsEntity() {
        entityManager.persistAndFlush(
            new Purchase(7L, "An", 1999L));
        entityManager.clear();

        Purchase result = repository.findById(7L)
            .orElseThrow();

        assertEquals(7L, result.getId());
        assertEquals("An", result.getCustomer());
        assertEquals(1999L, result.getTotalCents());
    }

    @Test
    void dataJpaSliceHasRepositoryButNotService() {
        assertNotNull(repository);

        assertThrows(
            NoSuchBeanDefinitionException.class,
            () -> context.getBean(PurchaseService.class));
    }

    @Test
    void repositoryCanDeleteOwnFixture() {
        repository.save(new Purchase(
            8L, "Bình", 5000L));

        assertTrue(repository.existsById(8L));

        repository.deleteById(8L);

        assertFalse(repository.existsById(8L));
    }
}
~~~

### 13.1. Vì sao assertThrows ở đây không phải một test lỗi?

Trong **JPA slice**, thiếu business service là **kết quả dự kiến**. Test chứng minh repository có mặt và service không bị import dư. Nó không khiến context startup fail: test chủ động hỏi `context.getBean(PurchaseService.class)` và xác nhận exception chính xác.

Nếu developer thêm một `@Import(PurchaseService.class)` vào base `@DataJpaTest` vì nghĩ “càng đầy đủ càng tốt”, test thứ hai sẽ fail. Đó là một regression guard hợp lý chống import dư.

### 13.2. Rollback và test data

`@DataJpaTest` mặc định chạy transaction và rollback sau mỗi test method. `TestEntityManager.persistAndFlush` giúp dữ liệu được ghi tới DB trước khi đọc, và `clear()` làm assertion tránh chỉ nhìn persistence context cấp một. H2 chỉ là lab persistence, **không thay PostgreSQL-specific integration tests** nếu production dùng native SQL/lock/dialect riêng.

### 13.3. Tại sao full-context khác JPA slice?

Full-context test có controller, service, repository, formatter và advice. JPA slice chỉ cần entity/repository/EntityManager. Nếu muốn kiểm `PurchaseService.find` chính thức, viết unit test với mock/fake repository hoặc full-context integration test; đừng bẻ JPA slice thành full app bằng hàng loạt imports.

## 14. JSON slice: serialization độc lập web/database

**src/test/java/com/example/slicediag/PurchaseJsonSliceTest.java**

~~~java
package com.example.slicediag;

import com.example.slicediag.web.PurchaseDto;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.junit.jupiter.api.Assertions.*;

@JsonTest
class PurchaseJsonSliceTest {

    @Autowired
    JacksonTester<PurchaseDto> json;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void serializesContractFieldsWithoutWebContext()
            throws Exception {

        PurchaseDto dto = new PurchaseDto(
            7L, "Khách: An", 1999L);

        String serialized = json.write(dto).getJson();
        JsonNode document = objectMapper.readTree(serialized);

        assertEquals(7L, document.get("id").longValue());
        assertEquals(
            "Khách: An",
            document.get("customerLabel").asText());
        assertEquals(
            1999L,
            document.get("totalCents").longValue());
    }

    @Test
    void deserializesDtoWithJacksonTester()
            throws Exception {

        String input =
            "{\"id\":7,\"customerLabel\":\"Khách: An\","
                + "\"totalCents\":1999}";

        PurchaseDto result = json.parseObject(input);

        assertEquals(7L, result.id());
        assertEquals("Khách: An", result.customerLabel());
        assertEquals(1999L, result.totalCents());
    }
}
~~~

`@JsonTest` không cần HTTP server, service hay repository để kiểm contract Jackson. Nếu gặp `No qualifying bean of type JacksonTester<T>`, kiểm đúng dependency `spring-boot-starter-test`, annotation `@JsonTest`, generic type và Spring Boot auto-configuration; đừng import cả MVC/controller chỉ để lấy ObjectMapper.

## 15. Full-context integration: cần wiring thật thì đừng mock sai mục tiêu

**src/test/java/com/example/slicediag/PurchaseFullContextTest.java**

~~~java
package com.example.slicediag;

import com.example.slicediag.model.Purchase;
import com.example.slicediag.model.PurchaseRepository;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(classes = DiagnosticApplication.class)
@AutoConfigureMockMvc
class PurchaseFullContextTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    PurchaseRepository repository;

    @BeforeEach
    void seedFixture() {
        repository.deleteAll();
        repository.save(new Purchase(
            7L, " An ", 1999L));
    }

    @Test
    void fullBeanGraphWorksThroughController()
            throws Exception {

        mvc.perform(get("/api/purchases/7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.customerLabel")
                .value("Khách: An"))
            .andExpect(jsonPath("$.totalCents")
                .value(1999));
    }

    @Test
    void missingPurchaseGoesThroughRealService()
            throws Exception {

        mvc.perform(get("/api/purchases/404"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code")
                .value("PURCHASE_NOT_FOUND"));
    }
}
~~~

Đây là test cần controller, service, formatter, repository và H2 ở cùng ApplicationContext. Không mock service vì test đang kiểm **real wiring**.

Dùng `@AutoConfigureMockMvc` để kiểm HTTP MVC dispatch/serialization nhưng **không mở server socket**. Nếu cần một bài kiểm qua TCP port thật, có thể thêm `@SpringBootTest(webEnvironment=RANDOM_PORT)` với RestClient/TestRestTemplate, nhưng chi phí và transaction boundaries sẽ khác.

### 15.1. Vì sao seed trong @BeforeEach?

Một full-context test có thể reuse Spring ApplicationContext giữa các methods. Nếu dữ liệu H2 từ test trước còn lại, một test phụ thuộc thứ tự có thể pass sai. `repository.deleteAll(); save(...)` tạo fixture ổn định cho hai methods. Trong môi trường DB thật, dùng DB riêng/test schema/transactions và cleanup phù hợp, không xóa dữ liệu ngoài test-owned database.

### 15.2. Phân biệt lỗi wiring với lỗi truy vấn

Nếu full-context test fail `UnsatisfiedDependencyException` do repository không có, kiểm JPA auto-config/DataSource/entities. Nếu context start được nhưng GET trả 500 từ SQL, xem repository/query/transaction. Không chữa cả hai bằng mock repository: mock làm mất integration coverage.

## 16. Negative tests an toàn bằng ApplicationContextRunner

Một test **cố ý thiếu bean hoặc cố ý có vòng phụ thuộc** không nên được viết thành `@SpringBootTest` fail ở class initialization: điều đó khiến toàn suite đỏ và có thể kéo theo “failure threshold exceeded” ở các tests khác.

`ApplicationContextRunner` tạo một context nhỏ và cung cấp một callback để assert rằng startup **dự kiến fail**. Vì context này nằm trong một runner riêng và được đóng sau callback, nó không làm bẩn Spring TestContext cache của các `@SpringBootTest` tests.

**src/test/java/com/example/slicediag/ContextGraphDiagnosticsTest.java**

~~~java
package com.example.slicediag;

import com.example.slicediag.web.CustomerLabelFormatter;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.BeanCurrentlyInCreationException;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.*;

class ContextGraphDiagnosticsTest {

    private static boolean causeContains(
            Throwable failure,
            Class<? extends Throwable> type) {

        Throwable cursor = failure;
        while (cursor != null) {
            if (type.isInstance(cursor)) {
                return true;
            }
            cursor = cursor.getCause();
        }
        return false;
    }

    static class MissingSecrets {
    }

    static class NeedsSecrets {
        NeedsSecrets(MissingSecrets secrets) {
        }
    }

    static class Alpha {
        Alpha(Beta beta) {
        }
    }

    static class Beta {
        Beta(Alpha alpha) {
        }
    }

    static class ExtraAuditClient {
        ExtraAuditClient(MissingSecrets secrets) {
        }
    }

    interface PaymentGateway {
    }

    static class CardGateway implements PaymentGateway {
    }

    static class BankGateway implements PaymentGateway {
    }

    static class PaymentHandler {
        PaymentHandler(PaymentGateway gateway) {
        }
    }

    @Test
    void missingBeanHasNoSuchBeanDefinitionRootCause() {
        new ApplicationContextRunner()
            .withBean(NeedsSecrets.class)
            .run(context -> {
                assertNotNull(context.getStartupFailure());
                assertTrue(causeContains(
                    context.getStartupFailure(),
                    NoSuchBeanDefinitionException.class));
            });
    }

    @Test
    void constructorCycleIsDetectableByCauseChain() {
        new ApplicationContextRunner()
            .withBean(Alpha.class)
            .withBean(Beta.class)
            .run(context -> {
                assertNotNull(context.getStartupFailure());
                assertTrue(causeContains(
                    context.getStartupFailure(),
                    BeanCurrentlyInCreationException.class));
            });
    }

    @Test
    void oneUnnecessaryBeanCanBreakAHealthyContext() {
        new ApplicationContextRunner()
            .withBean(CustomerLabelFormatter.class)
            .run(context ->
                assertNull(context.getStartupFailure()));

        new ApplicationContextRunner()
            .withBean(CustomerLabelFormatter.class)
            .withBean(ExtraAuditClient.class)
            .run(context -> {
                assertNotNull(context.getStartupFailure());
                assertTrue(causeContains(
                    context.getStartupFailure(),
                    NoSuchBeanDefinitionException.class));
            });
    }

    @Test
    void multipleCandidatesNeedQualifierOrPrimary() {
        new ApplicationContextRunner()
            .withBean(CardGateway.class)
            .withBean(BankGateway.class)
            .withBean(PaymentHandler.class)
            .run(context -> {
                assertNotNull(context.getStartupFailure());
                assertTrue(causeContains(
                    context.getStartupFailure(),
                    NoUniqueBeanDefinitionException.class));
            });
    }
}
~~~

### 16.1. Test missing bean

`NeedsSecrets` chỉ có constructor cần `MissingSecrets`. Runner chỉ đăng ký `NeedsSecrets`, nên Spring không tìm được dependency và startup fail. Test tìm `NoSuchBeanDefinitionException` trong chain. **JUnit test này pass khi phát hiện startup failure đúng loại**, không phải vì ứng dụng thật có lỗi.

### 16.2. Test constructor cycle

Runner đăng ký `Alpha` và `Beta` với hai constructors tham chiếu ngược. Spring đi theo dependency chain rồi phát hiện bean đang trong quá trình tạo. `BeanCurrentlyInCreationException` là tín hiệu điển hình cần tìm. Đừng khẳng định luôn là top-level exception: nó thường được bọc trong các `BeanCreationException`/`UnsatisfiedDependencyException`.

### 16.3. Test “import dư”

Runner A chỉ có `CustomerLabelFormatter`: context khởi động được. Runner B thêm `ExtraAuditClient` yêu cầu `MissingSecrets` chưa đăng ký: context fail. Điều này mô phỏng hiệu ứng của một `@Import`/component scan kéo thêm một bean không liên quan vào MVC slice. Cách sửa không phải đăng ký tất cả secrets, mà là bỏ **bean không cần thiết** khỏi test scope.

### 16.4. Test nhiều candidate

Runner chứa hai implementations `PaymentGateway`, rồi constructor `PaymentHandler` chỉ nhận interface. Spring không tự biết chọn Card hay Bank; `NoUniqueBeanDefinitionException` là root cause điển hình. Trong ứng dụng thật:

~~~java
@Service
class PaymentHandler {
    PaymentHandler(
        @Qualifier("cardGateway") PaymentGateway gateway) {
    }
}
~~~

Đây là snippet sửa hướng injection; giả sử bean tên `cardGateway` thực sự tồn tại. Có thể dùng `@Primary` trên implementation được chọn theo design, nhưng đừng gắn `@Primary` bừa chỉ để loại exception nếu hai implementations phục vụ use cases khác nhau.

### 16.5. Không assert full error message

Spring Boot 3.3.5, Framework, Mockito và các Java versions có thể thay chi tiết stacktrace và bean name prefixes. Test nên assert **exception class trong cause chain** và behavior, không hardcode một chuỗi lỗi 300 ký tự. Log đầy đủ vẫn cần để chẩn đoán khi test fail trên CI.



## 17. Bao nhiêu phương thức test và kết quả mong đợi?

Dự án đầy đủ có **14 `@Test` methods**:

| Test class | Số @Test | Điều đang kiểm |
| --- | ---: | --- |
| `PurchaseWebSliceTest` | 3 | MVC slice, mock service, import formatter, controller advice |
| `PurchaseJpaSliceTest` | 3 | JPA repo/H2, service không được scan |
| `PurchaseJsonSliceTest` | 2 | Jackson DTO serialization/deserialization |
| `PurchaseFullContextTest` | 2 | Controller -> Service -> JPA repository thật |
| `ContextGraphDiagnosticsTest` | 4 | Missing dependency, constructor cycle, import dư, multi-bean |
| **Tổng** | **14** | Positive wiring + intentional negative diagnostic |

Code được thiết kế theo **Java 17, Spring Boot 3.3.5, Gradle**; bài viết **không khẳng định đã chạy Gradle/JUnit** trong môi trường soạn. Expected là cả 14 methods pass trên môi trường có dependencies, H2 và JDK phù hợp. Một số negative tests pass **vì chúng khẳng định lỗi được phát hiện chính xác**, không phải vì lỗi được đưa vào main Spring application.

### 17.1. Lệnh chạy

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy riêng các nhóm:

~~~bash
./gradlew test --tests 'com.example.slicediag.PurchaseWebSliceTest'
./gradlew test --tests 'com.example.slicediag.PurchaseJpaSliceTest'
./gradlew test --tests 'com.example.slicediag.PurchaseJsonSliceTest'
./gradlew test --tests 'com.example.slicediag.PurchaseFullContextTest'
./gradlew test --tests 'com.example.slicediag.ContextGraphDiagnosticsTest'
~~~

Nếu project chưa có Gradle Wrapper nhưng bạn đã cài Gradle tương thích:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Kiểm Java và Gradle:

~~~bash
java --version
./gradlew --version
~~~

### 17.2. Xem báo cáo

~~~text
build/reports/tests/test/index.html
build/test-results/test/TEST-com.example.slicediag.PurchaseWebSliceTest.xml
build/test-results/test/TEST-com.example.slicediag.PurchaseJpaSliceTest.xml
build/test-results/test/TEST-com.example.slicediag.PurchaseJsonSliceTest.xml
build/test-results/test/TEST-com.example.slicediag.PurchaseFullContextTest.xml
build/test-results/test/TEST-com.example.slicediag.ContextGraphDiagnosticsTest.xml
~~~

Không tự tạo expected stdout cố định cho Spring context startup/Gradle because timestamps, thread names, startup time và H2 configuration khác máy. Các JSON assertions trong tests là những output contract cụ thể của application code.

### 17.3. Lưu ý về cache và test execution

Một lần `./gradlew test` có thể trả `UP-TO-DATE` khi không thay source. Nếu cần thực sự chạy lại test để chẩn đoán:

~~~bash
./gradlew test --rerun-tasks --stacktrace
~~~

Gradle task cache **không phải** Spring TestContext cache. Khi context fail trước đó trong cùng JVM, Spring Framework 6.1 có thể báo **failure threshold exceeded** cho những attempts sau; root cause thường xuất hiện ở log **lần đầu** cho context cache key ấy.

## 18. Thao tác biến thể để thấy failure thật

Các bước mutation dưới đây chỉ nên thực hiện trên **bản sao/branch test sandbox**, hoàn nguyên sau khi quan sát. Đừng đưa intentionally failing config vào main.

### 18.1. Bỏ @MockBean

Trong `PurchaseWebSliceTest`, xóa:

~~~java
@MockBean
PurchaseService service;
~~~

Sau đó khởi động MVC slice: constructor của `PurchaseController` cần `PurchaseService` nhưng slice không có. Mong đợi root cause `NoSuchBeanDefinitionException` hoặc wrapper `UnsatisfiedDependencyException`. **Sửa:** khôi phục mock vì đây là controller boundary test; không import service + repository + database.

### 18.2. Bỏ @Import(formatter)

Xóa:

~~~java
@Import(CustomerLabelFormatter.class)
~~~

Formatter chỉ là regular `@Component` nên không thuộc mặc định MVC slice. Controller thiếu formatter. **Sửa:** import đúng class vì test muốn formatter thật.

### 18.3. Import service thật vào MVC

Thêm:

~~~java
@Import(PurchaseService.class)
~~~

đồng thời bỏ mock service. Spring giờ cần `PurchaseRepository`, nhưng repository không nằm trong MVC slice; lỗi chỉ **dịch từ thiếu service sang thiếu repository**. Đừng thêm tiếp `@Import(PurchaseRepository.class)`, `@EnableJpaRepositories` và DataSource setup; hãy quay lại mock service hoặc chuyển sang `@SpringBootTest` nếu mục tiêu là integration.

### 18.4. Bỏ H2 test dependency

Xóa `testRuntimeOnly 'com.h2database:h2'` nhưng vẫn chạy JPA/full tests mà không cung cấp DataSource. Có thể gặp DataSource configuration failure, không phải vòng phụ thuộc. Sửa bằng test DB phù hợp hoặc Testcontainers; không tạo mock DataSource nếu test mục tiêu là JPA persistence thật.

### 18.5. Thêm vòng dependency production

Tạm thời tạo hai beans `Alpha`/`Beta` có constructor phụ thuộc nhau và cho Spring scan. `BeanCurrentlyInCreationException` có thể xuất hiện ở context startup. Hoàn nguyên và refactor graph. Không thêm `spring.main.allow-circular-references=true` như cách chữa mặc định.

### 18.6. Bật explicit @ComponentScan trên main class

Thử một bản copy của `DiagnosticApplication` có `@ComponentScan("com.example.slicediag")`. Theo Boot docs, điều này có thể làm mất slice exclude filters, khiến MVC/JPA slices thấy ngoài ý muốn nhiều beans. Không áp dụng vào production chỉ để chứng minh anti-pattern; giữ test application package scan mặc định.

### 18.7. Import một @Configuration rộng

Nếu application có `BillingConfiguration` tạo secrets, Kafka/HTTP clients, thử import trong MVC test sandbox. Ghi lại bean đầu tiên fail và graph bị kéo vào. Sửa bằng import một helper phù hợp hoặc mock một **port** ở đúng boundary.

### 18.8. Thay @MockBean bằng @Mock

Mockito `@Mock` chỉ tạo object thuộc test instance, không inject vào Spring context. `PurchaseController` vẫn thiếu service. Đây là bài học phân biệt Mockito unit test và Spring slice integration.

## 19. Một bảng quyết định giúp sửa đúng lỗi

| Mục tiêu test | Lỗi gặp phải | Cách sửa ưu tiên | Tránh |
| --- | --- | --- | --- |
| Chỉ controller status/JSON | Thiếu @Service | `@MockBean` service | @Import toàn service/repository |
| Controller + helper formatter thật | Thiếu formatter | `@Import` một helper | @ComponentScan toàn app |
| JPA repo test | Thiếu business service | Không dùng service trong slice | Import controller/service |
| JPA repo test | Thiếu DataSource | Embedded DB hoặc Testcontainers config | Fake DB nếu cần SQL thật |
| JSON DTO | Thiếu JacksonTester | @JsonTest đúng + starter-test | @SpringBootTest không lý do |
| Full integration | Thiếu repository | Kiểm main scan/JPA/DB config | Mock repo khi cần full wiring |
| Hai bean cùng interface | NoUniqueBeanDefinitionException | @Qualifier/@Primary đúng semantics | Chọn ngẫu nhiên implementation |
| Bean A -> B -> A | BeanCurrentlyInCreationException | Refactor dependency direction | allow-circular-references=true |
| Extra external client startup | @Import rộng | Bỏ extra import, tách config | Add credentials cho test không dùng client |
| Missing property bean | @ConfigurationProperties không scan | @EnableConfigurationProperties đúng type | Import cả production config tree |
| Multiple contexts fail cùng key | Failure threshold exceeded | Xem root error đầu tiên | Tăng threshold để che |
| Security 401/403 trước controller | Security filter chain/credentials | Mock user/auth config theo contract | Disable all filters vô điều kiện |

### Một lỗi có thể có nhiều nguyên nhân

Ví dụ `No qualifying bean of type PurchaseService` có thể là:

- MVC slice cố ý loại service.
- Full context dùng component scan root đặt sai package.
- `@Profile("prod")` không active ở test.
- `@ConditionalOnProperty` không match.
- Bean factory method chỉ có trong một config chưa được import.
- Type được inject có qualifier khác bean đã đăng ký.
- Cấu hình test vô tình thay primary configuration source.

Đừng quyết định sửa chỉ từ type exception. Hỏi **Spring context nào đang được tạo** và **tại sao bean đó được hoặc không được đăng ký**.

## 20. @TestConfiguration: nested, top-level và scope

Một nuance quan trọng của Spring Boot testing:

**Nested plain `@Configuration`:** có thể được xem như một nguồn cấu hình thay thế main application configuration trong test class. Nếu mục tiêu là thêm một bean nhỏ vào context đã dùng main application config, việc dùng nhầm plain nested `@Configuration` có thể làm mất bean khác.

**Nested `@TestConfiguration`:** nhằm **bổ sung** test-only beans cùng main application configuration, khi được Spring Boot phát hiện trong test class phù hợp.

**Top-level `@TestConfiguration`:** thường không tự bị component scan như production `@Configuration`; khi muốn dùng thì import rõ ràng. Đây là cơ chế hữu ích để test fixtures không rò vào production app.

### Ví dụ test-only config nhỏ

~~~java
@TestConfiguration(proxyBeanMethods = false)
class StubBillingConfiguration {

    @Bean
    BillingGateway billingGateway() {
        return request -> BillingResult.approved();
    }
}
~~~

Đây là snippet minh họa với `BillingGateway`/`BillingResult` giả định. Test cần gateway thật từ fake có thể `@Import(StubBillingConfiguration.class)` khi phù hợp. Không tự đặt tên bean trùng production nếu chưa hiểu overriding policy.

### Lỗi trùng bean definitions

Khi imported test config tạo bean cùng name với bean production trong Boot mặc định **không cho bean-definition overriding**, có thể nhận `BeanDefinitionOverrideException` hoặc ambiguous type. Dùng một trong các chiến lược có chủ đích:

- `@MockBean` để replace collaborator trong Boot3.3 test.
- `@Primary` cho một alternative bean nếu cả hai cần tồn tại nhưng injection có preferred candidate.
- `@Qualifier` khi mỗi consumer cần một named strategy.
- Exclude/tách production configuration khi test scope chỉ cần fake.
- Sử dụng profile/condition được định nghĩa rõ, không tự bật bean override toàn cục.

**Không mặc định bật `spring.main.allow-bean-definition-overriding=true`** để “sửa” một import trùng. Có thể làm test vô tình kiểm bean khác production.

## 21. @ConfigurationProperties và conditional auto-configurations

Một test slice có thể thiếu configuration properties bean vì regular `@ConfigurationProperties` không được scan mặc định. Ví dụ một formatter dựa vào `PurchaseViewProperties(prefix,locale)` có thể cần:

~~~java
@WebMvcTest(PurchaseController.class)
@EnableConfigurationProperties(PurchaseViewProperties.class)
@TestPropertySource(
    properties = "purchase.label-prefix=Khách")
class PurchaseConfigSliceTest {
}
~~~

Đây là snippet minh họa, không thuộc runnable project. Nếu `PurchaseViewProperties` dùng constructor binding/validation, cần supply properties hợp lệ cho test. Không import `AllProductionPropertiesConfiguration` để kéo thêm credentials và clients không liên quan.

Một bean có thể không hiện vì conditional:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "mail",
    name = "enabled",
    havingValue = "true")
MailSender mailSender() {
    return new RealMailSender();
}
~~~

Đây là snippet minh họa, giả định MailSender/RealMailSender có sẵn. Nếu property không match, BeanDefinition không được tạo — đây có thể là **hành vi mong muốn**. Đọc **Condition Evaluation Report** hoặc bật debug có chọn lọc thay vì thêm @Import bất kỳ.

### Condition Evaluation Report

Spring Boot cung cấp thông tin condition matches/negative matches để chẩn đoán auto-configurations. Bật logging cần thiết trong test runtime, ví dụ:

~~~properties
logging.level.org.springframework.boot.autoconfigure=DEBUG
~~~

Tùy thời điểm startup và logging initialization, một `ConditionEvaluationReportLoggingListener` trong `ApplicationContextRunner` cũng có thể hữu ích. Không cần bật toàn `org.springframework=TRACE` trên CI lâu dài vì log quá lớn. Nếu failure xảy ra trước log setup, xem Gradle `--stacktrace` và exception chain.

## 22. Lỗi từ Spring Security trong @WebMvcTest

Một test MVC có thể trả **401/403** thay vì 200 vì security filters đang active, ngay cả khi controller/service bean graph hoàn toàn hợp lệ. Đây **không phải** `NoSuchBeanDefinitionException`. Nếu app production dùng Spring Security, `@WebMvcTest` thường tích hợp Spring Security auto-configuration theo classpath.

Các lựa chọn đúng khi security là một phần hợp đồng:

- Dùng `@WithMockUser` từ `spring-security-test` để tạo principal/roles phù hợp.
- Với CSRF-protected POST, dùng `with(csrf())` theo policy và request type.
- Kiểm 401/403 cho unauthenticated/unauthorized paths.
- Nếu scope chỉ là serialization không cần security, có thể tách thành `@JsonTest`.
- Chỉ disable filters có chủ đích khi muốn một isolated MVC mapper test và đã có security contract tests khác.

**Đừng thêm @MockBean service hoặc @Import security config chỉ vì nhận 403.** Đọc response status trước, xác định vấn đề thuộc security layer hay context startup.

## 23. Lỗi từ repository và transaction trong @DataJpaTest

Khi JPA slice fail, phân biệt:

1. **Không có repository bean:** package scan, interface generic, entity discovery hoặc auto-configuration.
2. **Có repository nhưng query fail:** JPQL/derived query method không hợp entity properties.
3. **Không có DataSource:** thiếu embedded DB trên test classpath hoặc connection properties.
4. **SQL migration/init fail:** Flyway/Liquibase/schema scripts lỗi.
5. **Persistence context che assertion:** EntityManager trả object cache thay vì DB read; dùng flush/clear đúng chỗ.
6. **Transaction rollback không đúng kỳ vọng:** test không transaction, async boundary hoặc data setup khác transaction.
7. **Import service vào slice làm phát sinh nhiều deps:** test scope sai.

Nếu production dùng PostgreSQL native queries, H2 có thể tạo kết quả khác. `@DataJpaTest` với Testcontainers PostgreSQL và `@AutoConfigureTestDatabase(replace=NONE)` trong Boot 3.3 là lựa chọn phù hợp khi cần dialect thật.

Không dùng `@ImportAutoConfiguration` để kéo toàn production app chỉ vì thiếu một converter hoặc callback cần thiết; import đúng type/config nhỏ.

## 24. Context cache ảnh hưởng chẩn đoán như thế nào?

Spring TestContext cache dùng context configuration key để tái sử dụng ApplicationContext giữa tests. Nếu bạn thêm `@MockBean`, `@Import`, profiles hoặc properties khác nhau, cache key có thể thay đổi, làm số context loads tăng.

Nếu context K startup fail, trong Spring Framework 6.1+ failure threshold mặc định **1**, các test sau dùng cùng key có thể bị chặn nhanh với lỗi:

~~~text
ApplicationContext failure threshold (1) exceeded
~~~

Dòng này thường xuất hiện **sau lần đầu fail**, không phải root cause mới. Để chẩn đoán:

1. Tìm test class đầu tiên startup context K.
2. Tìm stacktrace và `Caused by` của lần fail đầu.
3. Xem các config differences làm context key khác.
4. Nếu Gradle fork nhiều JVM, mỗi worker có cache/failure counters riêng; tách log theo PID.
5. Đừng bật `spring.test.context.failure.threshold=1000000` để che lỗi thật.

Một @MockBean service cố định có thể dùng lại cache tốt giữa nhiều MVC tests cùng metadata; các variations mock quá tùy ý có thể sinh contexts khác nhau. Nhưng **không tái sử dụng bằng cách làm các tests lệ thuộc global mutable mock state**.

## 25. Từng bước chẩn đoán một ca thực tế

Giả sử CI báo:

~~~text
PurchaseWebSliceTest > controllerUsesMockedServiceAndRealFormatter FAILED
IllegalStateException: Failed to load ApplicationContext
Caused by: UnsatisfiedDependencyException:
  Error creating bean 'purchaseController'
Caused by: NoSuchBeanDefinitionException:
  No qualifying bean of type 'PurchaseService'
~~~

### Bước 1. Xác minh test annotation

Test dùng `@WebMvcTest(PurchaseController.class)`. Đây là slice MVC, không phải full context.

### Bước 2. Vẽ dependency graph controller

Constructor cần `PurchaseService` và `CustomerLabelFormatter`.

### Bước 3. So expected bean scope

PurchaseService là @Service business -> không tự có. Formatter chỉ @Component -> cũng không tự có. MVC/advice lại nằm trong slice.

### Bước 4. Chọn fix theo boundary

Mock business service, import **chỉ** formatter:

~~~java
@WebMvcTest(PurchaseController.class)
@Import(CustomerLabelFormatter.class)
class PurchaseWebSliceTest {
    @MockBean PurchaseService service;
}
~~~

### Bước 5. Không import repository/database

Nếu bạn phải import cả PurchaseRepository/JPA/DataSource để controller test chạy, scope đang sai. Dùng full context test khác nếu muốn test các layers thật.

### Bước 6. Kiểm thêm status/error tests

Khi context start, test 200/404/JSON fields. Một context nạp thành công **chưa chứng minh** controller mapping đúng.

### Bước 7. Chạy riêng + full suite

~~~bash
./gradlew test --tests 'com.example.slicediag.PurchaseWebSliceTest' --stacktrace
./gradlew test --rerun-tasks --stacktrace
~~~

Nếu riêng pass nhưng full suite fail, kiểm shared state, context cache variations, annotations chung, test order/parallelism và môi trường CI.

## 26. Failure mode: import dư làm thay đổi loại lỗi

Một ca điển hình:

~~~text
Ban đầu:
  @WebMvcTest
  Missing PurchaseService -> NoSuchBeanDefinitionException

Developer sửa sai:
  @Import(AllServiceConfiguration.class)

Sau đó:
  Missing MessageBrokerClient -> UnsatisfiedDependencyException

Developer tiếp tục:
  @MockBean MessageBrokerClient
  @Import(ExternalSecretsConfiguration.class)

Sau đó:
  Missing cloud credentials / circular config graph
~~~

Đây là **symptom migration**, không phải tiến trình sửa từng dependency. Với MVC test, quay lại xác định boundary: mock service, import formatter hẹp. Với full integration, phải có explicit test infrastructure cho broker/secret store tương ứng; đừng ép slice trở thành một full context không kiểm soát.

### Cách tìm import gây lỗi

- Xem annotations của test class và meta-annotations ở abstract base class.
- Xem `@Import`, `@ImportAutoConfiguration`, `@ComponentScan`, `@TestConfiguration`, `@ContextConfiguration`.
- Xem imports từ custom composed annotations.
- Kiểm `@Bean` methods trong imported configs và constructors chúng tạo.
- Tắt/bỏ **từng import không cần thiết trong test sandbox**, không sửa production global config ngẫu nhiên.
- Dùng Condition Evaluation Report nếu bean đến từ auto-configuration.
- Ghi lại bean đầu tiên có cause chain liên quan, không chỉ bean cuối trong stacktrace.

## 27. Vòng dependency và cách refactor có kiểm chứng

Nếu `InvoiceService` gọi `NotificationService` và `NotificationService` lại inject `InvoiceService`, cần tìm quyết định kiến trúc:

- Ai sở hữu transaction chính?
- Notification nên nhận event/DTO immutable hay gọi lại invoice service?
- Có nên có một application orchestrator điều phối cả hai?
- Có thể tách read-only port khỏi write service không?
- Một bean cần tham chiếu kia trong **constructor** hay chỉ cần một event publisher tại runtime?
- Có thể đưa shared logic vào component độc lập không?

Ví dụ hướng refactor:

~~~java
public interface PurchaseEvents {
    void published(long purchaseId);
}

@Service
public final class PurchaseService {
    private final PurchaseEvents events;
    // ...
}

@Component
public final class EmailPurchaseListener {
    // Lắng nghe event, không inject PurchaseService ngược.
}
~~~

Snippet **mang tính sơ đồ kiến trúc**, không phải file Java runnable vì thiếu method implementations và imports. Tránh nhét event bus chỉ để chữa một vòng nhỏ; nếu hai services không cần tách, có thể gom logic trong một service hoặc tách shared utility rõ ràng hơn.

### Test sau refactor

- `ApplicationContextRunner` tạo hai components mới và assert no failure.
- Unit tests xác minh orchestration gọi port đúng.
- `@SpringBootTest` integration xác minh real components được wire.
- Với event async, cần kiểm transaction boundary/retry/idempotency riêng, không mặc định event đã xử lý đồng bộ.

## 28. Các lỗi thường gặp với @MockBean

**Lỗi A — dùng Mockito @Mock thay @MockBean:** Spring không thấy bean. Sửa bằng Boot test mock trong context hoặc tạo controller thuần với `@InjectMocks` nếu mục tiêu unit test.

**Lỗi B — @MockBean type sai:** Controller inject interface A, test mock class B không thuộc type đó; chọn đúng type/qualifier.

**Lỗi C — nhiều beans cùng type:** Có thể cần name/qualifier cụ thể hoặc @Primary; không tạo thêm mock thứ ba khiến ambiguity nặng hơn.

**Lỗi D — mock quá sâu:** Mock repository, DataSource, HTTP client và service trong cùng MVC test có thể che design error; mock ngay tại boundary cần thiết.

**Lỗi E — when trong @BeforeAll nhưng mock reset per method:** Boot test mock reset/lifecycle có thể khiến stub không tồn tại ở method. Đặt stubbing trong từng test hoặc @BeforeEach theo policy.

**Lỗi F — muốn mock behavior trong context refresh:** Nếu bean cần output đã stub trong quá trình ApplicationContext khởi tạo, stubbing khi test method bắt đầu là **quá muộn**. Dùng `@TestConfiguration` với bean stub đã setup trước refresh hoặc test architecture phù hợp.

**Lỗi G — cố dùng API mới với BOM cũ:** Bài Boot 3.3 sử dụng `org.springframework.boot.test.mock.mockito.MockBean`. Khi nâng Boot/Spring Framework, xác minh API deprecations/migrations trước khi đổi annotations.

## 29. Những lỗi hay gặp với @Import

**Import một class regular:** `@Import(CustomerLabelFormatter.class)` trong MVC slice có nghĩa rõ.

**Import một @Configuration:** Có thể đăng ký hàng loạt @Bean, kích hoạt @Import tiếp, custom component scan hoặc external clients. Đọc graph trước khi dùng.

**Import AutoConfiguration bằng @Import:** Spring Boot khuyến nghị `@ImportAutoConfiguration` cho auto-configurations trong slices; plain @Import có thể không tôn trọng intended ordering/condition semantics như Boot auto-config mechanism.

**Import cả @SpringBootApplication:** Thường phá mục tiêu slice, khiến full component scan/auto-config. Chọn đúng test type thay vì import app root vô điều kiện.

**Import config chứa @EnableScheduling/@EnableKafka:** Có thể khởi tạo background threads/listeners và external connections làm test flaky. Chỉ bật trong integration test cần kiểm các behaviors đó.

**Import nested plain @Configuration:** Có thể thay config source hoặc tham gia scanning khác dự kiến. Khi cần bổ sung test bean, ưu tiên `@TestConfiguration` đúng semantics.

**Import production repository config vào MVC:** Bắt đầu kéo JPA/DataSource, thêm cost và failure modes. Với service boundary mock, không cần.

## 30. Vì sao @Lazy không phải sửa vòng dependency mặc định?

`@Lazy` có thể inject proxy hoặc trì hoãn bean resolution trong một số trường hợp. Điều này có thể giúp một dependency thực sự optional/lazy (ví dụ plugin registry hoặc expensive adapter). Nhưng:

1. Business cycle vẫn còn về logic.
2. Khi proxy được gọi, vấn đề có thể chỉ xuất hiện muộn hơn ở runtime.
3. Khó hiểu startup order và transactional proxies.
4. Có thể tạo recursion đến stack overflow thay vì exception rõ lúc startup.
5. Không giúp thiết kế đúng unit of work/trách nhiệm.
6. Có thể làm test pass startup nhưng fail khi gọi use case thật.

Nếu test được sửa bằng `@Lazy`, cần thêm integration test gọi **đường code thực sự dùng cả hai beans**. Thông thường refactor dependency direction vẫn dễ bảo trì và ít rủi ro hơn.

## 31. Vì sao không bật bean definition overriding mặc định?

Một error khác với circular dependency:

~~~text
BeanDefinitionOverrideException:
  Invalid bean definition with name 'purchaseService'
  ... cannot register ... another definition already bound
~~~

Điều này thường có nghĩa cùng tên bean được định nghĩa hai lần. Nguồn có thể là `@TestConfiguration` và production config, duplicate @ComponentScan hoặc cả @Import rộng.

Bật:

~~~properties
spring.main.allow-bean-definition-overriding=true
~~~

có thể khiến bean mới thay bean cũ theo thứ tự registration, làm test chạy trên **implementation khác mong đợi**. Sửa đúng hơn: đặt tên/qualifier rõ, chọn bean fixture theo test scope, dùng @MockBean khi cần replace, hoặc loại import dư.

Đừng nhầm bean definition overriding với circular reference setting; hai thuộc tính giải quyết hai lỗi khác nhau và đều có nguy cơ che vấn đề thiết kế.

## 32. Quy trình debug bằng Gradle và logging

### 32.1. Lệnh chạy riêng test

~~~bash
./gradlew test \
  --tests 'com.example.slicediag.PurchaseWebSliceTest' \
  --stacktrace --info
~~~

`--stacktrace` cho Gradle exception chain, `--info` làm log chi tiết hơn. Với Spring context creation failures, luôn xem JUnit XML/HTML test reports.

### 32.2. Log bean/condition có chọn lọc

~~~properties
logging.level.org.springframework.beans.factory.support=DEBUG
logging.level.org.springframework.boot.autoconfigure=DEBUG
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Chỉ bật trong một diagnostic run; nếu bật toàn suite, log có thể rất lớn. Một số lỗi xảy ra trước logging initialization, nên đọc root cause exception luôn quan trọng.

### 32.3. In bean names trong test context đã start

~~~java
String[] names =
    context.getBeanNamesForType(PurchaseService.class);

assertEquals(0, names.length);
~~~

Đây là pattern phù hợp khi muốn xác nhận một slice không chứa service. Không chạy bean inspection trong một context **đã fail startup**; lúc đó dùng cause chain/runner và condition evaluation report.

### 32.4. Quan sát test slices có Spring cache keys riêng

Hai MVC test classes dùng khác `@MockBean`/`@Import` có thể tạo cache keys khác nhau. Khi thêm cấu hình để chữa thiếu bean, benchmark startup/hit rate. Nhưng **không bỏ một mock cần thiết chỉ để tăng context reuse**.

### 32.5. Nếu chỉ fail trong CI

Kiểm JDK/Gradle/Boot versions, environment profiles, secrets availability, case-sensitive package names, test classpath, H2 runtime dependency, conditional beans và clock/OS assumptions. Không tự cho rằng lỗi khác máy là “Spring cache bug”.

## 33. Từ lỗi sang chiến lược kiểm thử đúng layer

Một codebase lành mạnh thường có:

- **Unit Java tests:** logic service/domain với mocks/fakes, không Spring.
- **@JsonTest:** DTO mapping/serialization.
- **@WebMvcTest:** HTTP contracts/MVC mapping/validation/advice, mock business collaborators.
- **@DataJpaTest:** JPA mappings/query/transactions, database được kiểm soát.
- **@RestClientTest:** outgoing HTTP adapter với mock server, không gọi network thật.
- **@SpringBootTest**: full DI/auto-config/integration flows.
- **RANDOM_PORT tests**: khi cần socket-level behavior, hiểu transaction boundaries.
- **Containerized service tests:** database/broker wire protocol thật khi cần.

Không có yêu cầu mọi business behavior phải được test bằng tất cả layers. Mỗi test nên trả lời một câu hỏi duy nhất, có graph vừa đủ, nhanh và dễ chẩn đoán. Khi context không load, có thể nhìn scope và xác định collaborator thiếu mà không phải đoán toàn app.

## 34. Bài tập thực hành

**Bài A — thiếu service:** Xóa `@MockBean PurchaseService` khỏi MVC test, ghi exception chain thật và khôi phục mock đúng type.

**Bài B — thiếu helper:** Xóa `@Import(CustomerLabelFormatter.class)`, ghi bean nào thiếu. Thêm lại import hẹp.

**Bài C — import dư:** Thử thêm `@Import(PurchaseService.class)` sau khi bỏ mock. Quan sát lỗi chuyển sang thiếu repository, giải thích vì sao đó là sửa sai mục tiêu.

**Bài D — JPA slice:** Assert repository tồn tại nhưng service không có. Thử thêm @Import service và so context bootstrap/time.

**Bài E — @JsonTest:** Thêm field mới vào DTO record và viết test JSON contract; không cần MVC app.

**Bài F — full context:** Chạy `PurchaseFullContextTest` với H2; kiểm 200/404 qua real service/repository.

**Bài G — constructor cycle:** Dùng `ApplicationContextRunner` đăng ký Alpha/Beta rồi assert cause chain có `BeanCurrentlyInCreationException`.

**Bài H — refactor cycle:** Tách một interface/port hoặc orchestrator, viết positive runner test xác minh context không fail.

**Bài I — ambiguous beans:** Đăng ký CardGateway/BankGateway và PaymentHandler, xác định `NoUniqueBeanDefinitionException`; sửa bằng @Qualifier hoặc @Primary theo yêu cầu.

**Bài J — @TestConfiguration:** Thêm một test-only bean nhỏ bằng nested @TestConfiguration; so với nested plain @Configuration.

**Bài K — broad component scan:** Trong sandbox, thêm explicit @ComponentScan vào application, so behavior @WebMvcTest/@DataJpaTest; hoàn nguyên.

**Bài L — condition:** Thêm @ConditionalOnProperty vào một bean và bật/tắt property, kiểm negative matches trong report.

**Bài M — @ConfigurationProperties:** Tạo một record config properties, dùng @EnableConfigurationProperties trong MVC slice và assert values.

**Bài N — external client import:** Dựng config có client phụ thuộc credential, thử import dư vào MVC test và ghi failure origin.

**Bài O — mock reset:** Dùng stubbing trong @BeforeEach, kiểm mock reset between methods, không giả định @BeforeAll stubs giữ mãi.

**Bài P — security:** Nếu thêm starter-security, test 401/403 và @WithMockUser phù hợp; không tắt filters mù.

**Bài Q — cache failure threshold:** Tạo failing context trong class sandbox, quan sát lần đầu và lần sau với Spring Framework 6.1.

**Bài R — DB Testcontainers:** Đổi @DataJpaTest H2 sang PostgreSQL container, kiểm dialect-specific query; không thay production DB bằng H2 vĩnh viễn.

**Bài S — gradle diagnostics:** Chạy test riêng với --stacktrace --info và lưu JUnit XML để đối chiếu root cause.

**Bài T — context performance:** Đếm số unique context configurations khi có nhiều @MockBean/@Import; chỉ tối ưu sau khi giữ correctness.

**Bài U — singleton state:** Viết một test lạm dụng @DirtiesContext, sau đó thay bằng cleanup dữ liệu/mocks và đo startup time.

**Bài V — review:** Chọn một failing slice trong codebase thật, viết dependency graph 2–3 tầng rồi đưa ra fix tối thiểu có lý do.

## 35. Checklist trước khi kết luận đã sửa

- [ ] Đã đọc root cause `Caused by` của lần fail đầu?
- [ ] Xác định đúng test annotation và bean graph scope?
- [ ] Biết missing bean thuộc controller/service/repository/configuration/conditional?
- [ ] @WebMvcTest không bị biến thành full app bằng @Import dư?
- [ ] Business collaborator trong MVC slice được mock có chủ đích?
- [ ] Helper thật được @Import đúng class/config hẹp?
- [ ] Không nhầm @Mock Mockito với @MockBean của Spring?
- [ ] Dùng API annotations hợp Spring Boot version hiện tại?
- [ ] @DataJpaTest chỉ nạp entity/repository và đúng test database?
- [ ] @JsonTest không kéo web/database khi không cần?
- [ ] @SpringBootTest chỉ dùng khi thực sự cần full wiring?
- [ ] Không kết hợp nhiều @...Test slices trên cùng class?
- [ ] Đã kiểm explicit @ComponentScan/primary test configuration?
- [ ] @TestConfiguration được dùng để bổ sung config đúng semantics?
- [ ] @ImportAutoConfiguration được chọn cho Boot auto-config bổ sung?
- [ ] @ConfigurationProperties test bean được đăng ký có chủ đích?
- [ ] Phân biệt NoSuchBeanDefinition và NoUniqueBeanDefinition?
- [ ] Khi có nhiều implementations, @Qualifier/@Primary phản ánh business intent?
- [ ] Constructor cycle đã được refactor, không chỉ bật allow-circular-references?
- [ ] Không dùng @Lazy như cách chữa mặc định để giấu graph cycle?
- [ ] Không bật bean-definition-overriding chỉ vì duplicate import?
- [ ] @DirtiesContext chỉ dùng khi context thật sự bị làm bẩn?
- [ ] Nếu có failure threshold exceeded, đã tìm root failure trước đó?
- [ ] Security 401/403 được phân loại khác context startup failure?
- [ ] JUnit negative tests chạy bằng runner riêng và PASS khi bắt lỗi mong đợi?
- [ ] Mockito stubbing và reset không gây test order dependency?
- [ ] Test data và transactions được cleanup đúng scope?
- [ ] Sau sửa đã chạy test class riêng và toàn module?
- [ ] Các test reports chứng minh cases thực thi, không chỉ Gradle UP-TO-DATE?
- [ ] Không bỏ business assertions chỉ để context load thành công?
- [ ] Không kéo external secrets/network vào một slice vốn không cần chúng?

## 36. Tài liệu tham khảo chính thức

Các liên kết hữu ích cho **Spring Boot 3.3.5, Spring Framework 6.1, JUnit Jupiter và Java 17**:

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @WebMvcTest, @DataJpaTest, @JsonTest, mock beans, @TestConfiguration và component scan filters.
- [Spring Boot 3.3 — Test Slices Appendix](https://docs.spring.io/spring-boot/3.3/appendix/test-auto-configuration/slices.html): những auto-configurations tương ứng từng slice.
- [Spring Boot 3.3 — @MockBean Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): đăng ký/replace mocks trong test context.
- [Spring Boot — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): kiểm context success/failure/conditional bean graphs.
- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html): constructor injection và vòng tham chiếu.
- [Spring Framework — TestContext Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): cache keys và khác biệt config.
- [Spring Framework — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/failure-threshold.html): mặc định 1 từ Framework 6.1.
- [Spring Framework — @Import](https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html): importing configuration classes.
- [Spring Data JPA — Repositories](https://docs.spring.io/spring-data/jpa/reference/repositories.html): repository infrastructure.
- [JUnit Jupiter — Assertions](https://docs.junit.org/5.10.0/user-guide/index.html#writing-tests-assertions): assertThrows và test failure semantics.
- [Gradle — Testing in Java](https://docs.gradle.org/current/userguide/java_testing.html): test filtering, reports, JUnit Platform.

**Ghi nhớ:** Một thiếu bean trong slice thường là **dấu hiệu scope bị hiểu sai**, không phải lý do để nhập toàn bộ production config. Dùng `@MockBean` cho business collaborator ở MVC boundary, `@Import` cho helper thật, `@DataJpaTest` cho repository, `@SpringBootTest` cho full graph. Khi thêm import làm lỗi chuyển sang external services hoặc vòng phụ thuộc, hãy **giảm graph** thay vì tăng imports. Dùng `ApplicationContextRunner` cho intentional failing configurations, đọc nguyên nhân gốc và refactor cycles theo dependency direction rõ.
