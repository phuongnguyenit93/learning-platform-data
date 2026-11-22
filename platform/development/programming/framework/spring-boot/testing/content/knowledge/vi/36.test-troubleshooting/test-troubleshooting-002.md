# Failed to load ApplicationContext và truy nguyên lỗi đầu tiên

## 1. Bắt đầu từ một thông báo dễ gây hiểu nhầm

Khi viết Spring Boot integration test, đôi lúc cả lớp JUnit đỏ trước khi bất kỳ assertion nghiệp vụ nào được chạy:

~~~text
java.lang.IllegalStateException:
  Failed to load ApplicationContext for
  [WebMergedContextConfiguration@... testClass=...]
~~~

Một vài test tiếp theo có thể hiện một thông báo khác:

~~~text
java.lang.IllegalStateException:
  ApplicationContext failure threshold (1) exceeded:
  skipping repeated attempt to load context for [...]
~~~

Nếu chỉ đọc dòng cuối ở màn hình IDE, bạn rất dễ kết luận sai rằng Spring TestContext cache đã bị hỏng, hoặc tăng timeout/reset cache là cách sửa. Thực tế, `Failed to load ApplicationContext` thường là **lớp bọc (wrapper)** quanh lỗi xảy ra **trong quá trình dựng context**: thiếu bean, bind cấu hình sai, database không kết nối được, bean factory throw exception, thiếu profile, migration fail, cấu hình web slice chưa đủ hoặc Testcontainers không sẵn sàng.

Từ **Spring Framework 6.1 trở lên**, TestContext có chính sách **context failure threshold**. Mặc định threshold là **1**: với cùng **context cache key**, lần load thất bại đầu tiên được ghi nhận; những lần load sau có thể bị **bỏ qua có chủ đích** và chỉ báo threshold exceeded. Dòng “skipping repeated attempt” là **hậu quả của lỗi trước đó**, không phải nguyên nhân gốc. Spring Framework 6.2 — nền tảng của Spring Boot 3.5 — cũng có hành vi này.

**Nguyên tắc quan trọng nhất:** Tìm **lần khởi tạo context thất bại đầu tiên theo thời gian cho cache key đang xét**, đọc toàn bộ chuỗi exception `Caused by` của lần đó, sau đó xác nhận bằng một thí nghiệm thay đổi **một nguyên nhân cụ thể**. Đừng lấy lỗi threshold của test thứ 10 làm root cause.

Bài này thuộc nhóm **Chẩn đoán lỗi kiểm thử** và tập trung đúng chủ đề **“Failed to load ApplicationContext và truy nguyên lỗi đầu tiên”**. Ví dụ có dự án **Java 17 / Spring Boot 3.5.16 / Maven / JUnit 5** với:
- Các test bình thường chứng minh context/web slice hoạt động.
- Những test `*ReproducerIT` cố ý làm context fail, **không được Surefire chạy mặc định**.
- Một test dùng `ApplicationContextRunner` bắt startup failure **như dữ liệu để assert**, không làm test suite phải đỏ.
- Bản đồ đọc stack trace, condition evaluation report, Spring profiles/configuration, bean injection, Testcontainers, SQL migration và giới hạn của Spring TestContext cache.

### Kết quả học tập

Sau bài, bạn có thể:

1. Phân biệt lỗi **test assertion**, lỗi **tạo JUnit test instance**, lỗi **Spring TestContext bootstrap** và lỗi **Spring ApplicationContext refresh**.
2. Nhận biết `IllegalStateException: Failed to load ApplicationContext` là wrapper, không phải loại lỗi nguồn.
3. Xác định **test/context cache key đầu tiên fail** thay vì chỉ xem test xuất hiện đầu tiên trong danh sách đỏ.
4. Đi đúng chuỗi `BeanCreationException` → `UnsatisfiedDependencyException` → `NoSuchBeanDefinitionException` hoặc các lỗi khác.
5. Hiểu tại sao `ApplicationContext failure threshold (1) exceeded` không có đủ thông tin để sửa.
6. Bật `debug=true` hoặc log `ConditionEvaluationReportLoggingListener` khi báo cáo auto-configuration có giá trị chẩn đoán.
7. Kiểm `@SpringBootTest`, `@WebMvcTest`, `@ActiveProfiles`, `@TestConfiguration`, `@MockitoBean` và property binding.
8. Phân biệt thiếu bean thực sự với bean bị loại vì test slice, profile/conditional annotation hoặc thiếu auto-configuration.
9. Chẩn đoán lỗi DataSource, Flyway/Liquibase, Testcontainers, HTTP server, port và logging initialization.
10. Dùng `ApplicationContextRunner`/`getStartupFailure()` viết regression test cho auto-configuration/startup failure.
11. Chạy đúng một reproducer với Maven Surefire và đọc `target/surefire-reports`, không che lỗi bằng rerun failures.
12. Biết khi nào phải sửa cấu hình, khi nào nâng phạm vi test, khi nào dùng mock, và khi nào cần kiểm external dependency thực.
13. Tránh workaround rủi ro như đặt failure threshold cực lớn vĩnh viễn, bật lazy initialization để giấu lỗi, xóa toàn bộ test hoặc disable security/transaction.
14. Viết báo cáo lỗi có **triệu chứng, root cause, evidence, sửa đổi và phép thử xác nhận**.

## 2. Context được tạo trước cả test method

### 2.1. Spring Boot test startup flow

Một JUnit Jupiter class:

~~~java
@SpringBootTest
class OrdersIntegrationTest {

    @Autowired
    OrderService service;

    @Test
    void processesOrder() {
        // ...
    }
}
~~~

Có thể fail **trước khi vào `processesOrder()`**, bởi SpringExtension/TestContext phải bootstrap/inject test instance. Sơ đồ giản lược:

~~~text
JUnit Jupiter discovers test
    |
    v
SpringExtension / TestContextManager
    |
    +-- resolve test configuration and cache key
    +-- look up cached ApplicationContext
    |
    +-- cache MISS:
    |       |
    |       v
    |   SpringBootContextLoader / SpringApplication
    |       |
    |       +-- prepare Environment / active profiles
    |       +-- process @Configuration / auto-config conditions
    |       +-- register bean definitions
    |       +-- instantiate non-lazy singleton beans
    |       +-- create datasource/listeners/clients/web infrastructure
    |       +-- bind and validate configuration properties
    |       +-- invoke bean initializers/migrations
    |       +-- finish context refresh
    |
    +-- cache HIT -> use existing context
    |
    v
Dependency injection into test instance
    |
    v
@BeforeEach
    |
    v
@Test method + assertions
~~~

Lỗi xảy ra tại một bước `SpringApplication/context refresh` có thể làm test method **chưa từng bắt đầu**. Vì thế, một assertion trong `@Test` không thể bắt lỗi bootstrap đó bằng `assertThrows(...)`: JUnit không vào test body. Để test startup failure như một giá trị dữ liệu, dùng `ApplicationContextRunner` (phần 10) hoặc tự xây context có kiểm soát.

### 2.2. Phân biệt bốn lớp lỗi

| Triệu chứng | Ranh giới hỏng | Hướng đầu tiên |
| --- | --- | --- |
| `AssertionFailedError: expected...` | Test body thực thi xong nhưng assertion sai | Kiểm actual/expected, fixture |
| `ParameterResolutionException` hoặc lỗi JUnit extension | JUnit/test instance/test parameter | Kiểm parameter resolver, extension |
| `Failed to load ApplicationContext` | Spring TestContext chưa dựng được context | Lấy first startup failure + `Caused by` |
| `ApplicationContext failure threshold exceeded` | Spring TestContext đã ghi nhận fail cho cùng key | Tìm lần fail **trước** trong log/reports |
| `No qualifying bean of type ...` | Bean injection/autowiring | Scan/slice/profile/conditional/qualifier |
| `BindException` / `ConfigurationPropertiesBindException` | Environment → typed config | Property source/value/validation |
| `Unable to open JDBC Connection` | External DB / pool / network | JDBC URL, credentials, DB readiness |
| `FlywayException` / SQL syntax | Schema migration/init | Migration version, dialect, permissions |
| `WebServerException` / Port in use | Embedded server startup | Port/webEnvironment |
| `ClassNotFoundException` / `NoClassDefFoundError` | Classpath/version | Dependencies/test scope/binary compatibility |
| `BeanCurrentlyInCreationException` | Bean creation cycle | Dependency graph/refactor |
| `NoSuchMethodError` / `AbstractMethodError` | Binary incompatibility | BOM alignment, dependency tree |

Bảng trên là **định hướng**, không thay thế việc đọc actual stack trace. Các exception wrappers có thể xếp nhiều tầng, thứ tự và message khác theo versions.

### 2.3. Tên exception ngoài cùng chưa đủ

Một stack trace có thể như:

~~~text
IllegalStateException: Failed to load ApplicationContext
  Caused by: UnsatisfiedDependencyException:
    Error creating bean with name 'auditController'
  Caused by: UnsatisfiedDependencyException:
    Error creating bean with name 'auditService'
  Caused by: NoSuchBeanDefinitionException:
    No qualifying bean of type 'AuditSink'
~~~

Vấn đề action được thường nằm ở **AuditSink không có bean hợp lệ trong context này**, chứ không phải `auditController` cần “tăng timeout”. Nhưng chưa chắc “thêm một `@Component`” là sửa đúng: bean có thể bị loại vì slice hoặc active profile, có thể thiếu implementation, hoặc mock đang replace nhầm type.

### 2.4. “Lỗi đầu tiên” có hai nghĩa

**Theo thời gian:** Lần bootstrap đầu tiên của một context cache key trong suite, trước khi threshold suppress lần tiếp theo. Đây là điều bắt buộc tìm khi nhiều tests cùng báo fail.

**Theo chuỗi nguyên nhân:** Exception bên ngoài dẫn vào `Caused by`, kết thúc ở nguyên nhân sâu. “Deepest cause” thường gần lỗi kỹ thuật trực tiếp (ví dụ `ConnectException: Connection refused`), nhưng “lý do phải sửa” đôi khi ở mức cao hơn (ví dụ URL lấy nhầm từ profile). Không chỉ cắt dòng `Caused by` cuối rồi kết luận môi trường mạng hỏng.

Lập luận đúng là:
1. **First failing startup attempt** (theo suite log).
2. **Exception chain** của attempt đó.
3. **First actionable misconfiguration** phù hợp bằng chứng.
4. **Reproduction/fix verification**.

### 2.5. Đừng bỏ qua APPLICATION FAILED TO START

Spring Boot có `FailureAnalyzer` cho một số lỗi startup, giúp in thông báo:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:
Parameter 0 of constructor in ... required a bean of type
'com.example.AuditSink' that could not be found.

Action:
Consider defining a bean of type 'com.example.AuditSink'
in your configuration.
~~~

Đây là **minh họa**, không phải output cố định của project. Boot có thể render các analyzer khác nhau tùy exception. Hãy đọc `Description` và `Action`, nhưng vẫn đối chiếu stack trace và cấu hình thực tế; analyzer không thay bạn quyết định có nên `@MockitoBean`, `@Import` hay sửa component scan.

## 3. Context failure threshold: nguồn của “lỗi thứ hai” gây nhiễu

### 3.1. Chính sách từ Spring Framework 6.1

Trong Spring Framework 6.1 và 6.2:
- TestContext cache một `ApplicationContext` cho các tests có cấu hình cùng một cache key.
- Nếu lần load cho key này fail, framework ghi số lần thất bại.
- `spring.test.context.failure.threshold` mặc định là **1**.
- Một attempt tiếp theo với **cùng cache key** có thể bị **skip ngay lập tức** vì ngưỡng đã đạt.
- Exception khi skip thường là `IllegalStateException` với thông báo `ApplicationContext failure threshold (1) exceeded`.
- Mục tiêu: tránh tốn thời gian khởi động lại một context chắc chắn fail vì cấu hình/external resource đã sai trong test run.

Thông báo skip không chứa đầy đủ chuỗi exception của lần bootstrap đầu. Nếu IDE chỉ hiện tab của lớp cuối, người học dễ bỏ qua gốc lỗi.

### 3.2. Cache key không đơn giản là test class

Spring TestContext xác định unique context configuration từ các thành phần như:
- `@ContextConfiguration` classes/locations/initializers/loader.
- `@ActiveProfiles`.
- `@TestPropertySource` properties/files.
- `@DynamicPropertySource` methods.
- `contextCustomizers` (bao gồm Spring Boot test features và `@MockitoBean`/`@MockitoSpyBean` overrides).
- Parent context, web resource base path.
- Web environment và các thuộc tính test config liên quan.

Hai classes có annotation/cấu hình giống nhau có thể reuse một context key. Một lớp thêm `@MockitoBean` hoặc test property riêng có thể hình thành cache key khác, dù cùng application main class. Do đó:
- Không tự kết luận “class B chịu threshold của class A” chỉ vì đặt cùng package.
- Không tự kết luận “mỗi class đều có first failure riêng”.
- Xem cấu hình được ghi trong `MergedContextConfiguration` và TestContext cache DEBUG logs.

### 3.3. Minh họa timeline

~~~text
09:00:00 Test A loads key K
        -> bean creation fails (AuditSink missing)
        -> startup failure count(K)=1
        -> full BeanCreationException/NoSuchBeanDefinitionException log

09:00:01 Test B asks for same key K
        -> failure threshold(1) exceeded
        -> no second full bootstrap attempt
        -> quick IllegalStateException explaining skip

09:00:02 Test C asks for different key K2
        -> framework may actually attempt another bootstrap
        -> error chain may differ, depending configuration
~~~

Đừng gọi Test B là “hỏng do cache” rồi sửa bằng `@DirtiesContext` tràn lan. Nó thường chỉ báo rằng Test A đã thất bại trước đó.

### 3.4. Thay threshold để chẩn đoán, không phải fix

Có thể chạy một lần với:

~~~bash
mvn -Dtest=MissingSinkFirstReproducerIT,MissingSinkSecondReproducerIT \
    -Dspring.test.context.failure.threshold=1000000 test
~~~

Đây là lệnh chẩn đoán: tăng threshold rất lớn khiến Spring thử load lại cho một cache key đã fail thay vì bỏ qua sớm. **Nó không sửa missing bean, invalid property hoặc DB downtime.** Nó làm test suite chậm, lặp rất nhiều startup logs, tốn tài nguyên và có thể gây nhiễu khi Docker/DB chịu tải.

Cũng không nên giảm threshold xuống 0: tài liệu chính thức yêu cầu **positive integer**. Mặc định 1 là tối ưu hợp lý cho phần lớn builds. Sau khi tìm được nguyên nhân, trả configuration về mặc định.

### 3.5. Vì sao chỉ rerun một test có thể giúp?

Chạy một failing class/method trong **JVM test run mới**:
- Spring TestContext cache static mới.
- Chưa có failure count cho key đó.
- Bạn dễ thấy **full first startup exception**.

Ví dụ:

~~~bash
mvn -Dtest=MissingSinkFirstReproducerIT test
~~~

Nếu build tool dùng fork khác hoặc giữ JVM test runner sống, xét lại assumption về reset. Khi test chỉ fail trong suite, chạy riêng có thể PASS vì không còn order dependency; khi đó cần tái hiện bằng tập tests + order/parallel conditions, không chỉ một class.

### 3.6. Context cache tối đa 32 và LRU

Spring Framework 6.2 mặc định cache tối đa **32 contexts**, eviction theo LRU. Có thể bật:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

hoặc cấu hình logger qua test runtime. DEBUG logs giúp xem hit/miss/cache size, nhưng **cache hit không có nghĩa context startup chưa từng fail ở cấu hình khác**; và cùng class name trong hai JVM forks không chia sẻ static cache.

Không thay `spring.test.context.cache.maxSize` chỉ để tránh đọc root cause. Cache size là công cụ quản lý hiệu năng và vòng đời context, không phải cách sửa bean dependency.

## 4. Quy trình truy nguyên lỗi đầu tiên trong 10 bước

### Bước 1 — Lưu nguyên log của lần FAIL

Đừng chỉ screenshot 10 dòng cuối. Lưu:
- Full stdout/stderr của test process.
- Maven Surefire XML/TXT report.
- Spring Boot startup `APPLICATION FAILED TO START` block nếu có.
- First `Failed to load ApplicationContext` block.
- Caused-by chain đầy đủ.
- Build command, JDK, Boot version, active profiles, test class set.
- Context cache/threshold messages nếu suite có nhiều fails.

Nếu log rất dài, tạo artifact trong CI và lọc trên **bản gốc đã lưu**, không xóa raw log ngay từ đầu.

### Bước 2 — Phân biệt test startup failure với assertion

Nếu `@Test` body chưa được gọi, đừng sửa Mockito verify/AssertJ expectation. Tìm vấn đề context lifecycle/setup. Nếu `@Test` đã chạy và failed assertion, nó là bài toán khác (trừ khi test body tự gọi SpringApplication/refresh).

### Bước 3 — Tìm attempt chronologically first

Tìm **lần đầu** xuất hiện:
- `Error creating bean with name ...`.
- `APPLICATION FAILED TO START`.
- `Failed to load ApplicationContext` **không phải threshold skip**.
- `Exception encountered during context initialization`.
- DataSource/JPA/Flyway/Testcontainers startup exception.

Trong suite chạy parallel, log lines của các contexts có thể interleave. Lọc theo test name, logger thread, `MergedContextConfiguration` hoặc unique context config; “dòng đầu tiên của toàn file” có thể thuộc một context key khác không liên quan.

### Bước 4 — Đọc từ ngoài vào trong

Ghi cây:

~~~text
OUTER:
  IllegalStateException: Failed to load ApplicationContext
CAUSE:
  UnsatisfiedDependencyException: auditController
CAUSE:
  UnsatisfiedDependencyException: auditService
ROOT TECHNICAL:
  NoSuchBeanDefinitionException: AuditSink
ACTIONABLE:
  @WebMvcTest chỉ nạp controller, thiếu service collaborator;
  test nên @MockitoBean AuditService hoặc import cấu hình đúng.
~~~

Không mặc định thêm mock vào full application integration test nếu mục tiêu là kiểm real services. Quyết định fix dựa vào test scope.

### Bước 5 — Xác nhận active profile và property sources

Kiểm:
- `@ActiveProfiles` có đúng tên?
- `application-test.yml`/`application-integration.properties` thực sự được load?
- `@SpringBootTest(properties=...)` có override giá trị?
- Environment variables/CI secrets có thiếu?
- `@TestPropertySource` có khiến config khác môi trường local?
- `@DynamicPropertySource` supplier có trả endpoint chưa sẵn sàng?
- Bean `@Profile`/`@ConditionalOnProperty` có active?

Một property trống hoặc sai kiểu có thể làm Boot binder fail trong lúc dựng bean; cần nhìn **property name, rejected value và origin** trong bind error, nhưng redact secrets.

### Bước 6 — Tách test slice với full context

`@WebMvcTest` chỉ nạp MVC infrastructure + controllers và một số MVC-related beans, không tự nạp mọi `@Service`/`@Repository`. Constructor controller yêu cầu service có thể gây `NoSuchBeanDefinitionException`. Với controller unit/slice test, `@MockitoBean` phù hợp. Với integration test cần real service, có thể dùng `@SpringBootTest` + `@AutoConfigureMockMvc` hoặc `@Import` đúng collaborator — không ép slice nạp toàn application nếu không cần.

### Bước 7 — Kiểm external dependency

Nếu deepest cause là network/JDBC:
- Container đã start và **ready**?
- Mapped host/port thực của Testcontainers?
- DataSource client có giữ stale port từ context cache không?
- JDBC URL/schema/user/password/driver có đúng?
- Flyway/Liquibase migrations có permission/SQL compatibility?
- Database in-memory H2 đã được seed/SQL init đúng?
- Broker/Redis/S3 test endpoint có chạy không?

Nếu external service chưa ready, dùng readiness/wait strategy, đừng `Thread.sleep(10000)` không có condition.

### Bước 8 — Bật condition report có mục đích

Spring Boot có `FailureAnalyzer` và `ConditionEvaluationReport` để giải thích các điều kiện auto-configuration match/nonmatch. Bật `debug=true` hoặc:

~~~properties
logging.level.org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener=DEBUG
~~~

Nếu dùng lệnh chạy app:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Khi test chứ không phải main app fail, hãy áp logging/debug vào **test environment tương ứng** (ví dụ `@SpringBootTest(properties = "debug=true")` trong một bản chẩn đoán hoặc system/test properties). Chú ý một test property mới có thể thay **context cache key**, nên không dùng kết quả ấy để suy hoàn toàn về threshold behavior của suite ban đầu.

**Không** suy rằng “Negative matches” trong condition report tự động là lỗi. Hầu hết auto-configurations cố ý không match. Chọn những entries trực tiếp liên quan bean đang thiếu.

### Bước 9 — Thay một biến và kiểm lại

Ví dụ:
- Thêm đúng `@MockitoBean AuditService` trong MVC slice, không sửa 10 dependencies.
- Sửa `demo.client.attempts=0` thành giá trị hợp lệ.
- Đăng ký `AuditSink` trong đúng component scan.
- Dùng `@ServiceConnection` đúng container/lifetime.
- Fix một migration script đang lỗi.

Chạy một test hẹp để chứng minh nguyên nhân biến mất; sau đó chạy lớp/suite đã fail.

### Bước 10 — Đảm bảo không có false green

Kiểm:
- Số test **executed**, không chỉ Maven exit code.
- Không có `@Disabled`/conditional skip khiến test biến mất.
- Không dùng `rerunFailingTestsCount` che failure ban đầu.
- Không disable validation/auto-config/security chỉ để context start nếu điều đó làm mất contract.
- Không tăng failure threshold vĩnh viễn.
- Khi thay profile/test slice, vẫn kiểm đúng layer được yêu cầu.
- Regresion test nên assert **behavior thật sau context startup**.

## 5. Cách đọc stack trace để tới root cause có thể sửa

### 5.1. BeanCreationException vs UnsatisfiedDependencyException

`BeanCreationException` có nghĩa Spring không tạo xong một bean. Nó có thể do:
- Constructor ném exception.
- Method `@Bean` throw.
- Dependency injection không giải được.
- `@PostConstruct`/`InitializingBean` fail.
- Configuration binding/validation fail.
- Database migration/connection trong initializer.

`UnsatisfiedDependencyException` là dạng cụ thể khi không giải được dependency. Nó thường có parameter index/type và bean chain.

Không sửa cả chuỗi theo từng bean: một missing dependency ở đáy có thể gây 10 lỗi tạo bean phía trên.

### 5.2. NoSuchBeanDefinitionException

Ví dụ:

~~~text
No qualifying bean of type
'com.example.diagnostics.AuditSink' available:
expected at least 1 bean which qualifies as autowire candidate
~~~

Checklist:
- Implementation có `@Component`/`@Service`/`@Repository` hoặc `@Bean` không?
- Class nằm **dưới package scan** của `@SpringBootApplication` không?
- Test là `@WebMvcTest`/`@DataJpaTest`/`@JsonTest` slice?
- Bean chỉ có trong profile bị tắt?
- `@ConditionalOnProperty`/`@ConditionalOnClass` không match?
- Bean bị exclude/override?
- Bean có scope/lifecycle phù hợp?
- Dependency có thực sự nên mock trong slice không?

Cần phân biệt **“không tồn tại trong test context này”** với **“không tồn tại trong production application”**.

### 5.3. NoUniqueBeanDefinitionException

Ví dụ:

~~~text
No qualifying bean of type 'PaymentGateway' available:
expected single matching bean but found 2: stripeGateway,fakeGateway
~~~

Đây không phải missing bean. Chọn `@Qualifier`, `@Primary`, profile/conditional registration hoặc injection collection một cách rõ ràng. Không thêm `@MockitoBean` bừa làm candidate ambiguity nặng thêm.

### 5.4. BeanCurrentlyInCreationException

Có thể liên quan circular dependency:

~~~text
ServiceA -> ServiceB -> ServiceA
~~~

Spring Boot thường không khuyến khích/không cho phép circular dependencies mặc định. Sửa bằng tách responsibility, event-driven boundary, lazy provider khi thật sự hợp lý; không bật `spring.main.allow-circular-references=true` chỉ để làm test xanh mà không hiểu cycle.

### 5.5. ConfigurationPropertiesBindException

Ví dụ:

~~~text
Failed to bind properties under 'demo.client'
to com.example.diagnostics.ClientProperties

Property: demo.client.attempts
Value: "0"
Reason: must be greater than or equal to 1
~~~

Đây là **shape minh họa**, không phải nguyên văn một lần chạy. Root issue nằm ở **rejected property** và constraint. Kiểm:
- Property source nào thắng theo precedence?
- Profile/test annotation override hay CI env?
- Binding tên kebab-case/camelCase có đúng?
- Kiểu số/duration/URL/enum có hợp lệ?
- Bean Validation provider có trên classpath?
- Config class đã được đăng ký bằng `@EnableConfigurationProperties`/`@ConfigurationPropertiesScan`?
- Custom converter có load trong context?

### 5.6. NoClassDefFoundError và NoSuchMethodError

Một dependency có thể biên dịch được nhưng runtime test classpath khác:
- Dependency `test` vs `runtime`/`provided` sai.
- Spring Boot BOM và phiên bản Spring Framework/Mockito/Jackson bị override không tương thích.
- Một transitive dependency bị exclude.
- Java bytecode version mới hơn JDK đang chạy.
- Shaded jar/classloader khác nhau.

Dùng:

~~~bash
mvn dependency:tree
mvn -version
java -version
~~~

Không fix bằng cách copy một jar ngẫu nhiên vào classpath hoặc downgrade Spring từng module tùy tiện. Để Boot BOM quản lý aligned versions khi có thể.

### 5.7. Exception ở test instance không phải context refresh

Một `@Autowired` field trong test không inject được đôi khi lỗi xảy ra khi Spring TestContext post-process test instance, **sau khi ApplicationContext load**. Stack trace có thể là `UnsatisfiedDependencyException` liên quan test class chứ không có outer `Failed to load ApplicationContext`. Cần phân biệt stage trước khi sửa configuration. Đừng gộp mọi test injection issue vào context failure threshold.

## 6. Dự án Java 17 / Spring Boot 3.5.16 để tái hiện và sửa lỗi

### 6.1. Mục tiêu thiết kế

Một ứng dụng audit đơn giản:
- `AuditController` có endpoint `GET /audit/{id}`.
- `AuditService` cần một `AuditSink`.
- `ConsoleAuditSink` là Spring component mặc định và chỉ log synthetic event, không gọi external service.
- `ClientProperties` chứa `demo.client.endpoint` và `demo.client.attempts`, được bind + validate.
- Main Spring Boot app cấu hình đúng nên **healthy tests PASS**.

Các deliberate failures:
1. `MissingSinkFirstReproducerIT`/`MissingSinkSecondReproducerIT` cùng chỉ rõ một **isolated Spring Boot config thiếu AuditSink**. Khi chạy cả hai trong cùng TestContext cache key, class đầu có failure chain; class sau có thể báo threshold exceeded.
2. `BadBindingReproducerIT` override `demo.client.endpoint` rỗng và `attempts=0`, gây bind validation failure.
3. `MissingMvcDependencyReproducerIT` dùng `@WebMvcTest` mà không mock collaborator `AuditService`, làm MVC slice thiếu bean.

Những `*ReproducerIT` **cố ý fail**. Maven Surefire mặc định thường chỉ tự phát hiện các pattern như `*Test`/`*Tests`/`Test*`/`*TestCase`, **không tự chạy `*IT`**. Lệnh `-Dtest=...` bên dưới sẽ yêu cầu chạy reproducer cụ thể để xem root cause. Đừng đặt deliberate failures dưới tên `*Test` rồi làm `mvn test` mặc định fail toàn bộ vì bài học.

### 6.2. Cây file

~~~text
first-context-failure-lab/
├── pom.xml
├── src/main/
│   ├── java/com/example/diagnostics/
│   │   ├── DiagnosticsApplication.java
│   │   ├── ClientProperties.java
│   │   ├── AuditSink.java
│   │   ├── ConsoleAuditSink.java
│   │   ├── AuditService.java
│   │   └── AuditController.java
│   └── resources/application.properties
└── src/test/java/com/example/diagnostics/
    ├── FullContextHealthyTest.java
    ├── MvcSliceHealthyTest.java
    ├── PropertiesOverrideHealthyTest.java
    ├── ContextRunnerFailureInspectionTest.java
    ├── PlainAuditServiceTest.java
    ├── IsolatedMissingSinkConfiguration.java
    ├── MissingSinkFirstReproducerIT.java
    ├── MissingSinkSecondReproducerIT.java
    ├── BadBindingReproducerIT.java
    └── MissingMvcDependencyReproducerIT.java
~~~

Không cần Docker/DB trong runnable main sample. Các failure types external DB/Testcontainers/Flyway sẽ được phân tích bằng các **mẫu chẩn đoán riêng** để tránh một lab nhỏ có 10 external dependencies chỉ để sinh lỗi startup.

### 6.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>first-context-failure-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Giải thích:
- `spring-boot-starter-web` cung cấp Spring MVC, Jackson và web auto-config cho controller/slice.
- `spring-boot-starter-validation` cung cấp Jakarta Bean Validation implementation (thường Hibernate Validator).
- `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ, Mockito, Spring Test, Spring Boot `ApplicationContextRunner`.
- Dùng Boot BOM (parent) quản lý versions, không đặt riêng một Spring Framework major khác.
- Java 17 được Spring Boot 3.5 hỗ trợ.
- `@MockitoBean` là API của Spring Framework 6.2 trong package `org.springframework.test.context.bean.override.mockito`; không dùng `@MockBean` cũ khi ví dụ được viết cho 3.5.

### 6.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=first-context-failure-lab

demo.client.endpoint=https://example.invalid/api
demo.client.attempts=3

# Chỉ phục vụ application demo; unit/slice tests không cần port 8080.
server.port=0
~~~

`example.invalid` là URL dành cho ví dụ, không có cuộc gọi network thật. Dòng `server.port=0` chọn random local port **nếu** application được start với embedded server. `@SpringBootTest(webEnvironment=NONE)` không mở server dù property này tồn tại. Nó không liên quan context failure threshold.

### 6.5. DiagnosticsApplication.java

`src/main/java/com/example/diagnostics/DiagnosticsApplication.java`:

~~~java
package com.example.diagnostics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ClientProperties.class)
public class DiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                DiagnosticsApplication.class, args);
    }
}
~~~

`@SpringBootApplication` scan package `com.example.diagnostics` và subpackages. `@EnableConfigurationProperties(ClientProperties.class)` đăng ký typed configuration bean. Việc đặt main class ở package gốc đúng giúp Spring Boot test tìm primary configuration theo quy tắc tìm ngược package.

### 6.6. ClientProperties.java

`src/main/java/com/example/diagnostics/ClientProperties.java`:

~~~java
package com.example.diagnostics;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "demo.client")
@Validated
public class ClientProperties {

    @NotBlank
    private String endpoint;

    @Min(1)
    private int attempts;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public int getAttempts() {
        return attempts;
    }

    public void setAttempts(int attempts) {
        this.attempts = attempts;
    }
}
~~~

Với `demo.client.endpoint` hợp lệ và `attempts=3`, bean bind/validate bình thường. Với endpoint blank hoặc attempts 0, Bean Validation reject trong startup. Vì failure thuộc typed config binding, Boot có thể hiển thị `ConfigurationPropertiesBindException`/`BindValidationException` hoặc analyzer description; hãy dựa vào actual stack trace chứ không hard-code một wrapper type trong mọi môi trường.

### 6.7. AuditSink.java

`src/main/java/com/example/diagnostics/AuditSink.java`:

~~~java
package com.example.diagnostics;

public interface AuditSink {

    void publish(String id);
}
~~~

Interface này là dependency bắt buộc của `AuditService`. Nếu không có bean implementation hoặc mock trong test context, Spring không thể tạo service. Trong project, production-like implementation ở file kế tiếp đã được đăng ký; deliberate isolated reproducer cố tình **không nạp nó**.

### 6.8. ConsoleAuditSink.java

`src/main/java/com/example/diagnostics/ConsoleAuditSink.java`:

~~~java
package com.example.diagnostics;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class ConsoleAuditSink implements AuditSink {

    private static final Logger log =
            LoggerFactory.getLogger(ConsoleAuditSink.class);

    @Override
    public void publish(String id) {
        log.info("event=audit_requested id={}", id);
    }
}
~~~

Log ở đây là một side effect giả lập, không phải durable audit store hay Kafka producer. Test không nên tuyên bố “audit đã ghi vĩnh viễn” chỉ vì logger được gọi. Với bài học này, mục tiêu là context wiring/bean discovery.

### 6.9. AuditService.java

`src/main/java/com/example/diagnostics/AuditService.java`:

~~~java
package com.example.diagnostics;

import org.springframework.stereotype.Service;

@Service
public class AuditService {

    private final AuditSink sink;

    public AuditService(AuditSink sink) {
        this.sink = sink;
    }

    public String record(String id) {
        sink.publish(id);
        return "recorded:" + id;
    }
}
~~~

Constructor injection khiến dependency graph rõ: `AuditController → AuditService → AuditSink`. Khi `AuditSink` không tồn tại trong một isolated context, lỗi dễ xác định. Trong full app, `ConsoleAuditSink` là component hợp lệ, nên chain resolve được.

### 6.10. AuditController.java

`src/main/java/com/example/diagnostics/AuditController.java`:

~~~java
package com.example.diagnostics;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/audit")
public class AuditController {

    private final AuditService service;

    public AuditController(AuditService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Map<String, String> get(@PathVariable String id) {
        return Map.of(
                "status", service.record(id));
    }
}
~~~

Trong **full `@SpringBootTest`**, Spring scan controller/service/sink. Trong **`@WebMvcTest(AuditController.class)`**, Spring Boot hạn chế context tới MVC slice nên `AuditService` thông thường **không được scan**. Đó là sự khác biệt có chủ đích, không phải “Spring quên chạy @Service”.

## 7. Những test đúng phải PASS

### 7.1. FullContextHealthyTest.java

`src/test/java/com/example/diagnostics/FullContextHealthyTest.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class FullContextHealthyTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    AuditService service;

    @Autowired
    ClientProperties properties;

    @Test
    void loadsAllRequiredBeansWithValidProperties() {
        assertThat(context.containsBean("auditService"))
                .isTrue();
        assertThat(context.containsBean("consoleAuditSink"))
                .isTrue();
        assertThat(properties.getEndpoint())
                .isEqualTo("https://example.invalid/api");
        assertThat(properties.getAttempts())
                .isEqualTo(3);
    }

    @Test
    void realServiceDependencyChainWorks() {
        assertThat(service.record("healthy_441"))
                .isEqualTo("recorded:healthy_441");
    }
}
~~~

Hai methods cùng Spring context; nếu setup bị hỏng, chúng fail trước body. Khi context load tốt, chúng kiểm bean wiring/config và một behavior thật. Annotation `webEnvironment=NONE` giúp demo không start embedded servlet server; không phải cứ `@SpringBootTest` là luôn mở port.

### 7.2. MvcSliceHealthyTest.java

`src/test/java/com/example/diagnostics/MvcSliceHealthyTest.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(AuditController.class)
class MvcSliceHealthyTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    AuditService service;

    @Test
    void returnsAStubbedAuditResult() throws Exception {
        given(service.record("mvc_441"))
                .willReturn("recorded:mvc_441");

        mvc.perform(get("/audit/mvc_441"))
                .andExpect(status().isOk())
                .andExpect(
                        jsonPath("$.status")
                                .value("recorded:mvc_441"));

        verify(service).record("mvc_441");
    }

    @Test
    void usesItsOwnMockBehaviorForAnotherRequest()
            throws Exception {
        given(service.record("other_441"))
                .willReturn("recorded:other_441");

        mvc.perform(get("/audit/other_441"))
                .andExpect(status().isOk())
                .andExpect(
                        jsonPath("$.status")
                                .value("recorded:other_441"));

        verify(service).record("other_441");
    }
}
~~~

**Đây là bản sửa đúng của MVC slice reproducer:** `@MockitoBean AuditService` cấp collaborator trong web slice. Test kiểm controller mapping/JSON/MVC, **không** tuyên bố integration của real service → sink cũng đã được kiểm. Với full service integration, dùng `@SpringBootTest` hoặc import dependencies phù hợp.

### 7.3. PropertiesOverrideHealthyTest.java

`src/test/java/com/example/diagnostics/PropertiesOverrideHealthyTest.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
                "demo.client.endpoint=https://fixed.invalid/api",
                "demo.client.attempts=5"
        })
class PropertiesOverrideHealthyTest {

    @Autowired
    ClientProperties properties;

    @Test
    void bindsOverriddenValidValues() {
        assertThat(properties.getEndpoint())
                .isEqualTo("https://fixed.invalid/api");
        assertThat(properties.getAttempts())
                .isEqualTo(5);
    }
}
~~~

Lớp này tạo test config/property set khác `FullContextHealthyTest`, nên **context cache key có thể khác**. Đó không phải lỗi cache fragmentation bất thường: nó đang kiểm một configuration variant thực. Nó chứng minh sửa binding contract chứ không chỉ disable `@Validated`.

### 7.4. PlainAuditServiceTest.java

`src/test/java/com/example/diagnostics/PlainAuditServiceTest.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class PlainAuditServiceTest {

    @Test
    void verifiesPureJavaWiringWithoutSpringContext() {
        AuditSink sink = mock(AuditSink.class);
        AuditService service = new AuditService(sink);

        assertThat(service.record("unit_441"))
                .isEqualTo("recorded:unit_441");

        verify(sink).publish("unit_441");
    }
}
~~~

Plain unit test **không cần tạo Spring ApplicationContext**, nên không xuất hiện failure threshold hoặc Boot startup. Nó rất tốt để kiểm Java logic độc lập, nhưng **không chứng minh production bean scan, profile, configuration binding hoặc web layer**.

## 8. Các reproducer cố ý FAIL: giữ ngoài default Maven tests

### 8.1. IsolatedMissingSinkConfiguration.java

`src/test/java/com/example/diagnostics/IsolatedMissingSinkConfiguration.java`:

~~~java
package com.example.diagnostics;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Bean;

@SpringBootConfiguration
@EnableAutoConfiguration
public class IsolatedMissingSinkConfiguration {

    @Bean
    AuditService isolatedAuditService(AuditSink sink) {
        return new AuditService(sink);
    }
}
~~~

Đây là một **isolated Boot configuration**, không có `@ComponentScan`, vì vậy nó không đăng ký `ConsoleAuditSink`. `@EnableAutoConfiguration` cho Boot infrastructure hoạt động, nhưng không tự tạo implementation domain `AuditSink`. Bean factory method yêu cầu một `AuditSink` không có trong context → startup fail.

**Điểm khó dễ bỏ sót:** File này trong test classpath, cùng package với main app. Khi `@SpringBootTest(classes=IsolatedMissingSinkConfiguration.class)` được chỉ định **tường minh**, Boot dùng config riêng này. Trong healthy tests không chỉ định nó; Boot tìm `DiagnosticsApplication` qua primary configuration discovery. Vì `@SpringBootConfiguration` không được tự component-scan như `@Component` thông thường, config repro không phải một bean được đưa vào full app chỉ vì nó nằm cùng package.

### 8.2. MissingSinkFirstReproducerIT.java

`src/test/java/com/example/diagnostics/MissingSinkFirstReproducerIT.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(
        classes = IsolatedMissingSinkConfiguration.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class MissingSinkFirstReproducerIT {

    @Test
    void contextCannotStartWithoutAnAuditSink() {
        // JUnit không vào method vì context refresh đã FAIL.
    }
}
~~~

Chạy tách biệt:

~~~bash
mvn -Dtest=MissingSinkFirstReproducerIT test
~~~

**Kết quả mong đợi là exit code khác 0** và full stack trace startup failure. Không đổi tên test thành `*Test` trong suite CI thông thường. Một deliberate-failure reproduction không phải regression test xanh; mục đích duy nhất là nhìn exact failure path.

### 8.3. MissingSinkSecondReproducerIT.java

`src/test/java/com/example/diagnostics/MissingSinkSecondReproducerIT.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(
        classes = IsolatedMissingSinkConfiguration.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class MissingSinkSecondReproducerIT {

    @Test
    void sameContextKeyMayBeSkippedAfterFirstFailure() {
        // Có thể báo failure threshold exceeded.
    }
}
~~~

Hai classes dùng cùng explicit classes, web environment và không có test properties/bean override riêng. Khi được chạy trong **cùng test JVM/cache**, chúng thường chia sẻ Spring context cache key. Tùy test order, lớp nào được load trước sẽ cho full first failure, lớp sau có thể cho threshold skip. **Không** cần classes thật sự chạy theo tên “First”/“Second”; người đọc phải xác định lần fail theo log.

Chạy:

~~~bash
mvn -Dtest=MissingSinkFirstReproducerIT,MissingSinkSecondReproducerIT \
    -DtrimStackTrace=false test
~~~

Đặt test hai classes trong cùng Maven invocation để quan sát threshold/cache reuse; không chạy bằng hai shell commands riêng rồi kết luận cache đã hoạt động qua processes.

### 8.4. BadBindingReproducerIT.java

`src/test/java/com/example/diagnostics/BadBindingReproducerIT.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
                "demo.client.endpoint=",
                "demo.client.attempts=0"
        })
class BadBindingReproducerIT {

    @Test
    void invalidConfigCannotBeValidated() {
        // Test body không chạy; properties validation FAIL.
    }
}
~~~

Trong `ClientProperties`, `endpoint` có `@NotBlank`, `attempts` có `@Min(1)`. Boot config binding nên fail khi values không hợp lệ. Đây là **ví dụ gốc lỗi khác missing bean**: không thêm `AuditSink`/`@MockitoBean` để chữa binding.

Lệnh:

~~~bash
mvn -Dtest=BadBindingReproducerIT test
~~~

Khi phân tích, tìm `demo.client.endpoint`/`demo.client.attempts`, rejected values, reason constraints và property origin. Một exception `BindValidationException` trong chain có thể cho chẩn đoán giá trị sai tốt hơn 20 dòng bean wrappers bên ngoài.

### 8.5. MissingMvcDependencyReproducerIT.java

`src/test/java/com/example/diagnostics/MissingMvcDependencyReproducerIT.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;

@WebMvcTest(AuditController.class)
class MissingMvcDependencyReproducerIT {

    @Test
    void mvcSliceCannotConstructControllerWithoutService() {
        // Web slice thiếu bean AuditService.
    }
}
~~~

Lệnh:

~~~bash
mvn -Dtest=MissingMvcDependencyReproducerIT test
~~~

Đây là lỗi **test-slice wiring**, không nhất thiết là production misconfiguration. Sửa bằng `@MockitoBean AuditService` (xem `MvcSliceHealthyTest`) nếu mục tiêu là controller contract. Đừng đổi toàn bộ project từ `@WebMvcTest` sang `@SpringBootTest` chỉ để mọi collaborators tự xuất hiện mà không xem chi phí/phạm vi kiểm thử.

### 8.6. Vì sao không assert lỗi trong các @SpringBootTest reproducer?

Code như:

~~~java
@Test
void expectsStartupError() {
    assertThatThrownBy(() -> doSomething())
            .isInstanceOf(IllegalStateException.class);
}
~~~

sẽ **không được thực thi** nếu Spring TestContext load fail trước khi test body. `@SpringBootTest` không biến startup failure thành một exception có thể catch trong method. Để kiểm “khi bean missing, context failure có root cause đúng” mà test vẫn xanh, dùng `ApplicationContextRunner` trong lớp tiếp theo.

## 9. ApplicationContextRunner: bắt startup exception trong một JUnit test xanh

### 9.1. Vì sao ApplicationContextRunner phù hợp?

`ApplicationContextRunner` trong `spring-boot-test` cho phép dựng một **context nhỏ độc lập** với user configuration và inspect:
- Có khởi tạo thành công không?
- Bean nào tồn tại/không tồn tại?
- Startup failure là exception gì?
- Nguyên nhân sâu nhất là exception nào?
- Property/auto-configuration conditions thay đổi điều gì?

Nó không dùng `@SpringBootTest` để khởi tạo context trước test instance. Do đó, một test có thể **kỳ vọng context fail** và assert failure **mà bản thân JUnit vẫn PASS**. Nó không sử dụng cơ chế failure threshold/cache của Spring TestContext theo cách `@SpringBootTest` dùng; đừng xem kết quả runner như chứng minh threshold = 1.

### 9.2. ContextRunnerFailureInspectionTest.java

`src/test/java/com/example/diagnostics/ContextRunnerFailureInspectionTest.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ContextRunnerFailureInspectionTest {

    @Configuration(proxyBeanMethods = false)
    static class MissingSinkConfig {

        @Bean
        AuditService auditService(AuditSink sink) {
            return new AuditService(sink);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ExplodingBeanConfig {

        @Bean
        String simulatedDependency() {
            throw new IllegalStateException(
                    "CONFIG_FAULT_DEMO_441");
        }
    }

    private static Throwable deepestCause(Throwable failure) {
        Throwable current = failure;

        while (current.getCause() != null
                && current.getCause() != current) {
            current = current.getCause();
        }

        return current;
    }

    @Test
    void reportsMissingBeanAsRootCauseWithoutFailingJunit() {
        new ApplicationContextRunner()
                .withUserConfiguration(MissingSinkConfig.class)
                .run(context -> {
                    assertThat(context).hasFailed();

                    Throwable failure =
                            context.getStartupFailure();

                    assertThat(failure).isNotNull();

                    Throwable root = deepestCause(failure);

                    assertThat(root).isInstanceOf(
                            NoSuchBeanDefinitionException.class);

                    assertThat(root.getMessage())
                            .contains(AuditSink.class.getName());
                });
    }

    @Test
    void reportsThrownInitializerCauseWithoutFullBootTest() {
        new ApplicationContextRunner()
                .withUserConfiguration(ExplodingBeanConfig.class)
                .run(context -> {
                    assertThat(context).hasFailed();

                    Throwable failure =
                            context.getStartupFailure();

                    assertThat(failure).isNotNull();

                    Throwable root = deepestCause(failure);

                    assertThat(root)
                            .isInstanceOf(
                                    IllegalStateException.class)
                            .hasMessage(
                                    "CONFIG_FAULT_DEMO_441");
                });
    }
}
~~~

### 9.3. Những assertions trên chứng minh gì?

**MissingSinkConfig test:**
- Cố tạo một `AuditService` nhưng không có `AuditSink`.
- Context runner báo startup failure.
- Deepest cause mang kiểu `NoSuchBeanDefinitionException` và type cần tìm.
- Bài test JUnit PASS vì **startup failure chính là kết quả dự kiến** trong context runner.

**ExplodingBeanConfig test:**
- Một `@Bean` factory method cố tình ném `IllegalStateException`.
- Spring bọc nó trong exception bean creation.
- Root throwable giữ marker xác định, nên test không chỉ dựa vào outer `BeanCreationException` text.

**Giới hạn:** `deepestCause(...)` là tiện ích tìm exception sâu nhất, không phải một general framework phân tích mọi multi-cause exception (suppressed, composite errors, cycle không thể quy về một leaf). Với lỗi thực, hãy đọc cả chain và property/configuration context. Một `ConnectException` ở đáy không cho biết URL được chọn từ profile nào.

### 9.4. Vì sao không dùng ApplicationContextRunner cho mọi @SpringBootTest?

Runner tốt cho **nhánh auto-configuration và wiring nhỏ**. Nếu cần kiểm:
- Web MVC filter chain thật;
- Database transaction;
- Kafka broker;
- Security filter;
- JPA repositories;
- Đa module component scan;
- Toàn bộ production-style `SpringApplication`;

thì vẫn cần slice/full integration tests phù hợp. `ApplicationContextRunner` không tự tạo một môi trường Spring Boot đầy đủ với mọi auto-config và resource nếu bạn không đăng ký chúng.

## 10. Chạy đúng project và đọc kết quả

### 10.1. Bộ test mặc định (không gồm deliberate failures)

~~~bash
mvn -q clean test
~~~

Những lớp `*Test` được thiết kế để PASS:
- `FullContextHealthyTest`: **2** JUnit methods.
- `MvcSliceHealthyTest`: **2** methods.
- `PropertiesOverrideHealthyTest`: **1** method.
- `PlainAuditServiceTest`: **1** method.
- `ContextRunnerFailureInspectionTest`: **2** methods.

Tổng **8 JUnit methods dự kiến** khi Surefire discovery/configuration giữ mặc định và tests không bị skip. Các `*ReproducerIT` không thuộc default include patterns của Surefire. **Maven chưa được chạy khi biên soạn bài**, vì vậy “8 methods expected” không phải một test report đã đo được.

### 10.2. Reproduce missing bean và failure threshold

~~~bash
mvn -Dtest=MissingSinkFirstReproducerIT,MissingSinkSecondReproducerIT \
    -DtrimStackTrace=false test
~~~

**Kỳ vọng:** Maven báo FAIL là đúng mục đích của reproducer. Xem first full exception trước bất kỳ threshold-skip exception cùng cache key. Nếu Surefire/chạy test bị fork thành JVMs khác nhau, chúng có thể không chia sẻ context failure count; khi ấy đọc fork config hoặc chạy trong một JVM để quan sát cơ chế.

### 10.3. Reproduce property binding

~~~bash
mvn -Dtest=BadBindingReproducerIT \
    -DtrimStackTrace=false test
~~~

Tìm các thông tin:
- `ClientProperties`.
- `demo.client.endpoint`, `demo.client.attempts`.
- `must not be blank` / `must be greater than or equal to 1`.
- Property origin nếu Boot binder in ra.
- Không để mình bị dẫn lệch bởi outer `BeanCreationException`.

### 10.4. Reproduce web slice missing dependency

~~~bash
mvn -Dtest=MissingMvcDependencyReproducerIT \
    -DtrimStackTrace=false test
~~~

So sánh với:

~~~bash
mvn -Dtest=MvcSliceHealthyTest test
~~~

Khác biệt thiết yếu là `@MockitoBean AuditService` trong slice test đúng, không phải bật thêm networking/timeout.

### 10.5. Đọc Surefire reports

Sau Maven test, kiểm:

~~~text
target/surefire-reports/
    com.example.diagnostics.FullContextHealthyTest.txt
    TEST-com.example.diagnostics.FullContextHealthyTest.xml
    ...
~~~

Tập tin/định dạng có thể khác theo Surefire provider/version/config. Một test context failure thường nằm ở testcase error **trước test body**. Xem full report của **lớp có first context startup failure**.

Bash/Linux/macOS có thể dùng:

~~~bash
grep -R -n -E "Failed to load ApplicationContext|failure threshold|Caused by:|APPLICATION FAILED" target/surefire-reports
~~~

Windows PowerShell:

~~~powershell
Get-ChildItem target/surefire-reports -File |
  Select-String -Pattern 'Failed to load ApplicationContext',
                         'failure threshold',
                         'Caused by:',
                         'APPLICATION FAILED'
~~~

**Đừng chỉ lấy dòng match rồi vứt surrounding stack trace.** Mở report tương ứng để đọc 20–100 dòng trước/sau. Khi nhiều tests chạy parallel, marker cùng file không tự chứng minh chúng là cùng context key.

### 10.6. Đường đọc log đề xuất

~~~text
1. Build/test command, Java/Boot version
2. First startup error chronologically for target context key
3. Spring Boot "APPLICATION FAILED TO START" Description + Action
4. First "Error creating bean with name..."
5. Caused-by chain until actionable reason
6. Condition evaluation report only for relevant auto-config
7. Active profiles/property origin and classpath
8. Candidate fix and narrow regression test
9. Full affected suite; verify executed vs skipped/flaky
~~~

Không nhảy thẳng tới mục 9 chỉ vì fix làm test method đơn lẻ PASS. Một implementation có thể thiếu collaborator ở một profile khác hoặc một test slice khác.

## 11. Lỗi thiếu bean và lựa chọn sửa đúng

### 11.1. Thiếu component scan

Một main class:

~~~java
@SpringBootApplication
public class ShopApplication { }
~~~

nằm trong package `com.example.shop` thì default component scan dưới package đó. Service implementation ở `com.other.module` có thể không được phát hiện. Đưa main class về common root package, thêm explicit `@Import`/`@ComponentScan` một cách có chủ đích hoặc cung cấp bean configuration — thay vì cứ thêm `@Autowired(required=false)` để lấp chỗ trống.

### 11.2. @Profile

~~~java
@Profile("integration")
@Component
class RealAuditSink implements AuditSink {
    // ...
}
~~~

Nếu `@ActiveProfiles("test")` mà chỉ có `integration` bean, missing dependency là behavior đúng theo config. Sửa:
- Chọn profile cần test;
- Cấp fake bean trong test;
- Hoặc có default strategy phù hợp product behavior.

Đừng bật mọi profile đồng thời để tránh hiểu lỗi; nó có thể tạo duplicate candidates, security/provider conflicts hoặc external calls ngoài dự kiến.

### 11.3. @ConditionalOnProperty

~~~java
@ConditionalOnProperty(
    prefix = "feature.audit",
    name = "enabled",
    havingValue = "true")
@Bean
AuditSink auditSink() {
    // ...
}
~~~

Nếu test không set property, bean có thể bị loại có chủ đích. Condition report có thể cho biết property missing/nonmatching. Xem `matchIfMissing`/`havingValue`/property origin trước khi cho rằng Spring không scan.

### 11.4. @MockitoBean

Spring Framework 6.2 `@MockitoBean` có thể replace hoặc create mock bean trong test context. Trong MVC slice, controller dependency là một mock phù hợp; trong full integration test, việc mock repository/service có thể che chính wiring/transaction cần chứng minh.

**Không sửa bằng cách mock mọi bean** khi root cause là production missing configuration. Dùng mock chỉ khi boundary test thực sự chấp nhận collaborator thay thế.

### 11.5. @TestConfiguration vs @Configuration lồng trong test

Spring Boot:
- Nested `@TestConfiguration` thường **bổ sung** cho primary application configuration.
- Nested `@Configuration` trong một test có thể được dùng **thay** primary config khi test loader tìm cấu hình phù hợp.
- `@Import(MyTestConfig.class)` cho phép nạp test collaborators một cách tường minh.
- `@SpringBootTest(classes=...)` chọn app/config classes tường minh.

Một class bỗng “mất toàn bộ services” sau khi thêm nested configuration có thể do test đã thay nguồn bootstrap. Phân biệt config override intentional với accidentally replacing main app config.

### 11.6. Bean name/qualifier mismatch

Nếu có nhiều implementations:
- Dùng `@Qualifier("...")` theo contract.
- Chọn `@Primary` nếu có default thật.
- Inject `List<AuditSink>`/`Map<String, AuditSink>` khi business cần tất cả.
- Sửa bean definitions cho rõ, không bắt Mockito nhặt “một bean bất kỳ”.

## 12. Configuration binding: lỗi nổi trong startup

### 12.1. Property source precedence

Một config value có thể đến từ:
- `application.properties`/YAML.
- Profile-specific config.
- JVM system properties.
- Environment variables.
- `@TestPropertySource`.
- `@SpringBootTest(properties=...)`.
- `@DynamicPropertySource`.
- ConfigData imports/external secrets.
- Command line app arguments.

Khi một binding fail, hỏi **giá trị nào đã thắng**, không chỉ “trong file của tôi ghi đúng”. Một env var CI có thể override local config; secret provider không sẵn sàng có thể khiến placeholder không resolve.

### 12.2. @ConfigurationProperties + @Validated

Với Bean Validation provider:
- `@NotBlank` reject null/empty/whitespace-only.
- `@Min(1)` reject 0/negative integer.
- `@NotNull` phải đặt cho object reference khi muốn cấm null.
- `@Valid` cần cho nested object cascaded validation.
- Binding type conversion có thể fail **trước** validation (ví dụ string chữ ở integer field).

Đừng disable `@Validated` để context start nếu chính yêu cầu là fail-fast config invalid. Sửa value hoặc constraints theo business contract.

### 12.3. Missing @ConfigurationProperties registration

Class chỉ gắn `@ConfigurationProperties` chưa chắc đã là Spring bean. Phải đăng ký thông qua `@EnableConfigurationProperties`, `@ConfigurationPropertiesScan` hoặc bean definition tương ứng. Nếu không có registration, injection có thể báo missing bean; đó là lỗi khác validation failure của **bean đã tồn tại**.

### 12.4. Duration/URL/type parsing

Ví dụ:

~~~properties
demo.connect-timeout=not-a-duration
demo.max-attempts=not-a-number
~~~

Nếu properties class cần `Duration` hoặc `int`, binder có thể báo conversion/binding exception. Không nhận nhầm thành network timeout: ứng dụng có thể fail **trước khi gọi network**.

### 12.5. Redact configuration trong logs

Các bind errors có thể chứa rejected property value. Khi property là password/token, redaction cần thiết trong log/CI artifacts. Không paste live credentials hoặc JDBC URL có password vào bug report. `/actuator/env` (nếu được bật) cũng cần security và sanitized values.

## 13. DataSource, JPA, migrations và Testcontainers

### 13.1. Thiếu JDBC URL hoặc driver

~~~text
Failed to configure a DataSource:
'url' attribute is not specified and no embedded datasource
could be configured
~~~

Đây là diagnostic shape có thể xuất hiện khi có JDBC/JPA starter nhưng không có suitable DataSource config. Kiểm:
- Có thực sự cần database trong test này?
- H2/HSQL/Derby test dependency đã có chưa?
- Đúng profile properties cho production-like DB?
- Driver tương ứng có trên test runtime classpath?
- `@AutoConfigureTestDatabase` có thay bằng embedded DB không?
- Có `@ServiceConnection` hoặc `@DynamicPropertySource` khi dùng Testcontainers?
- Chỉ một DataSource hay nhiều qualifiers?

Không thêm H2 vào test chỉ để làm context xanh nếu yêu cầu là kiểm PostgreSQL-specific SQL/locks/migrations.

### 13.2. JDBC connect refused

~~~text
org.postgresql.util.PSQLException:
  Connection to localhost:5432 refused

Caused by: java.net.ConnectException:
  Connection refused
~~~

Có thể do:
- DB container chưa start/ready.
- Host/port sai.
- Docker mapped port là port động, không phải 5432 ở host.
- Test profile trỏ DB production/dev không mong muốn.
- CI network/TLS/firewall.
- Client pool giữ URL cũ từ context được cache.
- Container đã bị JUnit `@Container` stop nhưng Spring context vẫn cached.

**Lý do action được** có thể là sai lifecycle của Testcontainers, không phải thiếu câu lệnh `Thread.sleep`.

### 13.3. @Container lifetime vs cached context

Với Testcontainers JUnit 5 extension:
- `@Testcontainers` + static `@Container` được quản lý theo **test class**.
- Spring `ApplicationContext` có thể cached **qua nhiều test classes**.
- Sau class A, JUnit có thể stop container; class B reuse context/DataSource tới mapped port cũ.
- Class B có thể fail `Failed to load ApplicationContext` hoặc fail ở first query tùy startup timing/cache path.

Với Spring Boot 3.5, dùng **Spring-managed container bean** qua `@TestConfiguration @Bean @ServiceConnection` khi muốn lifetime container khớp context; hoặc singleton container JVM không gắn JUnit `@Container` với ownership/cleanup rõ.

**Không tự suy** rằng một lỗi connection ở test method chắc chắn là failure to load context; nếu context đã load và DB chết sau, lỗi xảy ra tại runtime query.

### 13.4. Flyway/Liquibase migration

Một startup failure có thể là:

~~~text
BeanCreationException: Error creating bean 'flywayInitializer'
Caused by: FlywayMigrateException:
  Migration V7__orders.sql failed
Caused by: SQLException:
  relation already exists / invalid SQL syntax
~~~

Đây là minh họa. Kiểm:
- Migration version/history.
- SQL dialect và DB version.
- Quyền tạo bảng/schema.
- Data leftover từ test trước.
- Migration ordering/baseline.
- Parallel migrations cùng database/schema.
- Transaction support của migration.
- H2 mode không giống PostgreSQL production.

Đừng disable Flyway chỉ để test qua nếu mục tiêu là bảo đảm schema production khởi tạo đúng. Với controller slice không cần DB, tránh nạp database infrastructure không cần thiết.

### 13.5. JPA/Hibernate lỗi mapping

Những nguyên nhân hay gặp:
- Duplicate entity mapping/table/column names.
- Invalid `mappedBy`/relationship annotation.
- Hibernate schema validation mismatch.
- Named query parse error.
- Converter không được scan.
- Entity package khác scan scope.
- Database dialect/driver mismatch.

JPA `EntityManagerFactory` startup exception thường được bọc qua `BeanCreationException`. Đọc Hibernate exception trong cause chain rồi xác định mapping cụ thể; tăng TestContext failure threshold không sửa mapping.

### 13.6. Broker/Redis startup

Kafka/Rabbit/Redis failures có thể gây:
- Producer factory bean init failure.
- Listener container fail/timeout.
- Connection factory exception.
- Wrong bootstrap servers/network.
- Bean `@PostConstruct` gọi external dependency quá sớm.
- Testcontainers image chưa ready.

Kiểm test có thật sự cần broker để test business logic không. Khi cần, dùng integration test với container sống đúng lifecycle và wait readiness; khi không, mock adapter hoặc dùng unit/slice boundary rõ.

## 14. ConditionEvaluationReport: đọc đúng, không đoán

### 14.1. Report ghi những điều kiện auto-config

`ConditionEvaluationReport` bao gồm positive/negative condition matches và exclusions/unconditional classes. Nó giúp trả lời:
- Vì sao `DataSourceAutoConfiguration` hoạt động?
- Vì sao `MongoAutoConfiguration` không match?
- Vì sao một conditional bean bị bỏ qua?
- Vì sao Security/Web MVC/JPA config lại được nạp?
- Config class nào có condition match hoặc nonmatch?

**Không có nghĩa một “Negative match” là lỗi.** Phần lớn auto-configurations không liên quan app đều nonmatch hợp lệ.

### 14.2. Bật debug theo đúng test environment

Đối với main app:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Đối với `@SpringBootTest`:

~~~java
@SpringBootTest(properties = "debug=true")
class ContextDiagnosisTest {
}
~~~

Đây là snippet, không phải file trong runnable lab. Test properties có thể thay context cache key; vì vậy dùng để chẩn đoán **nhánh auto-config** và quay lại exact original test configuration để verify root cause. Nếu CI log quá lớn, bật debug riêng trong diagnostic build.

### 14.3. Khi report có ích nhất

Report hữu ích khi error là **conditional wiring**: beans/auto-config có hay không vì classpath, property hoặc web environment. Với `NoClassDefFoundError`/JDK incompatibility, report có thể không được dựng xong; dùng dependency tree/full exception stack trước.

### 14.4. Không nhầm FailureAnalyzer với JUnit report

Boot `FailureAnalyzer` có thể in “Description/Action”. JUnit `test report` phân loại error/failure/skipped. Một `FailureAnalyzer` message là **startup troubleshooting help**, không phải kết quả assertion, và có thể không có analyzer cho một custom exception.

## 15. Test slice: thường là nguyên nhân bị hiểu nhầm

### 15.1. @WebMvcTest

Nạp MVC scope, không tự nạp mọi `@Service`. Nếu controller constructor cần service:
- `@MockitoBean` phù hợp để kiểm HTTP mapping/validation/JSON.
- `@Import(Service.class)` chỉ khi bạn muốn real service với đủ collaborators.
- `@SpringBootTest + @AutoConfigureMockMvc` nếu muốn full context, chấp nhận chi phí.
- Đừng thêm `@ComponentScan` quá rộng vào test chỉ để sửa một missing bean, vì có thể phá slice boundaries.

### 15.2. @DataJpaTest

Tập trung JPA entities/repositories, thường embedded test DB (tùy config/test auto-configuration). Nó không nạp toàn service/web stack. Một repository test inject controller sẽ fail vì test scope sai; fix bằng đúng slice hoặc full test.

### 15.3. @JsonTest

Nạp JSON serializers/converters, không tự nạp service dependencies. Nếu một Jackson Module custom bị thiếu, xem `@Import`/test config và slice include rules. Không cần full Boot context cho DTO mapping thuần.

### 15.4. @WebFluxTest

WebFlux slice cũng giới hạn bean scope. Kiểm reactive controller collaborator bằng `@MockitoBean`/`@Import` phù hợp, và dùng `WebTestClient`. Không copy nguyên `@WebMvcTest` imports/MockMvc sang WebFlux rồi đoán type errors.

### 15.5. @SpringBootTest

Tải nhiều auto-configurations và Spring beans hơn, nên lỗi DB, external clients, migration hoặc security config có thể xuất hiện sớm hơn. Đôi khi lỗi chỉ lộ với full context là **hợp lý**, bởi test này đang kiểm phạm vi tích hợp lớn hơn.

### 15.6. Controller không phải bean?

Nếu test target sai class/package, `@WebMvcTest` có thể không thấy controller bạn nghĩ. Kiểm:
- Class dưới component scan?
- Annotation là `@RestController`/`@Controller`?
- Explicit `controllers = SomeController.class` đúng?
- Inner configuration replacement?
- Mapper/filter/advice có được include không?

Đừng sửa bằng cách mock controller; như vậy bạn có thể mất behavior đang muốn test.

## 16. ApplicationContext và TestContext cache: tránh sửa sai chỗ

### 16.1. @DirtiesContext không phải thuốc chữa mọi lỗi

`@DirtiesContext` đánh dấu context cache không tái sử dụng. Nó hữu ích khi test làm bẩn singleton/ApplicationContext state. Với thiếu bean/invalid property, force-reload sẽ tái hiện **cùng lỗi** và khiến suite chậm hơn. Với failure threshold, context vốn chưa load thành công; tạo context key mới không làm missing dependency biến mất.

### 16.2. @MockitoBean đổi cache key

Một `@MockitoBean` override được coi là context customizer, có thể làm các classes có test configs khác nhau không reuse cùng context. Không so threshold messages giữa hai test classes có bean overrides khác nhau rồi kết luận framework không nhất quán.

### 16.3. @DynamicPropertySource và stale endpoints

Testcontainers dynamic URL có thể thay khi container restart. `@DynamicPropertySource` supplier đọc giá trị khi config được dựng; DataSource của một cached context không tự re-initialize mỗi khi port đổi. Nếu test fail sau class boundary, kiểm container ownership/context lifetime, không chỉ database credentials.

### 16.4. Forked JVM reset static cache

Spring TestContext cache là process-local static. Maven Surefire `forkCount`, `reuseForks` và IDE processes ảnh hưởng reuse. Chạy hai classes trong hai Maven commands độc lập thường không tái hiện threshold skip xuyên runs. Để nghiên cứu threshold, cần cùng cache key và **cùng JVM**.

### 16.5. Parallel test logs bị xen kẽ

Nếu classes chạy song song, “first failure toàn file” có thể thuộc một context key khác. Hãy phân nhóm:
- Config class/test class.
- Active profile.
- Properties/bean overrides.
- Exception stack trace.
- Thread/log timestamp.
- Context cache DEBUG statistics.

Sau đó tìm first failure **trong nhóm key cụ thể**, không dùng random ordering phỏng đoán.

## 17. Đọc Maven/Surefire/JUnit result đúng cách

### 17.1. Error vs failure

Một JUnit **error** thường có exception ngoài assertion, như context failed setup. Một assertion expected/actual mismatch có thể được report là **failure**. Surefire XML schema/runner details khác nhau, nên đọc exception type/message và test stage chứ không suy hoàn toàn từ nhãn errors/failures.

### 17.2. Trích xuất thông tin hiệu quả

Lưu:
- `mvn -version`.
- Parent/BOM version.
- `-Dtest=...` selection.
- `-DtrimStackTrace=false` khi cần full causes.
- Full root cause and bean name.
- Context cache config/log.
- Test executed/skipped counts.

Đừng gửi raw full `application.properties` nếu có secrets; redacted values đủ để chẩn đoán precedence/config.

### 17.3. RerunFailures không chữa context startup

Surefire `rerunFailingTestsCount` có thể rerun thất bại, nhưng nếu config missing bean, mọi attempts vẫn fail hoặc tạo thêm threshold messages. Nếu external service flaky, rerun PASS có thể che một vấn đề readiness/timeout. Giữ initial error trong report và phân tích.

### 17.4. Một lần PASS riêng không chứng minh suite đã sửa

Các lỗi phụ thuộc:
- Test execution order.
- Shared ContextCache.
- Static beans.
- Testcontainers class-level lifetime.
- External DB state.
- Parallel mocks.
- CI env vars.
- Dynamic ports.
- Scheduled/asynchronous startup tasks.

Sau khi fix, chạy đúng failing suite (cùng test scope/profile/forks) rồi broader suite. Nếu chỉ test hẹp PASS, ghi rõ phạm vi đã xác nhận.

### 17.5. Không để deliberate repro tests lọt CI mặc định

Một `*ReproducerIT` intentional failure nên:
- Có tên/README rõ “expected startup failure”.
- Được run bằng `-Dtest` khi cần.
- Không nằm trong Surefire default includes.
- Không bị vô tình đưa vào Failsafe `integration-test/verify` nếu CI đã cấu hình `*IT` patterns, trừ khi test job thật sự **mong đợi exit code khác 0**.
- Nếu cần regression CI xanh cho failure path, chuyển sang `ApplicationContextRunner`/programmatic assertion.

## 18. Bản đồ root cause thường gặp

| Root signal | Nhánh lỗi gốc cần điều tra | Phép kiểm tốt nhất |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | Scan/profile/slice/conditional/import | Kiểm actual bean definitions; thêm đúng mock/import |
| `NoUniqueBeanDefinitionException` | Nhiều candidates | @Qualifier/@Primary/conditional |
| `BeanCurrentlyInCreationException` | Circular dependency | Vẽ graph/refactor |
| `ConfigurationPropertiesBindException` | Value/format/validation sai | Property origin/rejected key |
| `Could not resolve placeholder` | Missing property/secret | Test profile/config data |
| `Failed to configure a DataSource` | Thiếu URL/embedded DB/driver | Datasource auto-config/driver |
| `Communications link failure` / `Connection refused` | DB/network/container not ready | URL/host/mapped port/readiness |
| `FlywayMigrateException` | Migration/schema SQL | Migration history/first failed script |
| `BeanCreationException: entityManagerFactory` | ORM mapping/schema/dialect | Hibernate root exception |
| `WebServerException: Port already in use` | Server config | RANDOM_PORT/NONE or free port |
| `ClassNotFoundException` | Classpath missing | Dependency scope/tree |
| `NoSuchMethodError` | Dependency binary mismatch | BOM/dependency tree |
| `APPLICATION FAILED TO START` | Boot analyzer output | Read Description/Action + causes |
| `failure threshold exceeded` | Earlier load failed for same key | Find first full attempt |
| `Context is no longer active` | Context closed/dirty while test using it | @DirtiesContext/parallel tests |
| `Docker environment not found` | Testcontainers runtime | Docker daemon/CI permissions |
| `Port 0?`/request errors after startup | Context may be fine; request layer | HTTP config/MockMvc/webEnvironment |
| `OutOfMemoryError` at boot | Resource pressure | Heap/memory leak/context count |

Với mỗi tín hiệu, lưu **class name/bean name/property key** cụ thể. Không áp giải pháp của lỗi A cho mọi trường hợp có outer `Failed to load ApplicationContext`.

## 19. Anti-pattern khi chẩn đoán

### 19.1. Chỉ xem exception của test cuối cùng

Test cuối có thể chỉ là `failure threshold exceeded`. Hãy tìm first attempt của context key, không xem skip message là root cause.

### 19.2. Tìm “Caused by” cuối mà bỏ toàn chain

Deepest `ConnectException` cho biết connection refused, nhưng URL sai có thể do profile override ở lớp cao hơn. Giữ cả chuỗi và property origin.

### 19.3. Tắt mọi @AutoConfiguration để context chạy

Việc exclude `DataSourceAutoConfiguration`, Security auto-config hoặc Flyway có thể làm test xanh nhưng khiến phạm vi test khác production. Chỉ exclude khi test slice **cố ý không cần** integration đó.

### 19.4. Bật lazy initialization để giấu lỗi

`spring.main.lazy-initialization=true` có thể trì hoãn tạo bean hỏng tới lúc request/call đầu tiên. Nó không chữa dependency/config, và test context load PASS có thể là false confidence. Khi yêu cầu startup phải fail-fast, giữ eager init/validation.

### 19.5. Mock toàn bộ collaborator

Một full integration test mock service/repository/DB client bị thiếu có thể không còn kiểm configuration đang hỏng. Dùng mock ở boundary được chấp nhận, giữ real adapters khi mục tiêu là integration startup.

### 19.6. @DirtiesContext trên mọi class

Nó phá cache reuse, tăng thời gian suite, không sửa missing bean/property. Chỉ dùng khi context state thực sự bẩn.

### 19.7. Tăng failure threshold rất lớn trong CI thường trực

Điều này khiến Spring repeatedly attempt load một context fail. Startup logs dài hơn nhưng bug còn, test suite chậm và dễ gây quá tải external resources.

### 19.8. Tăng timeout bất kể root cause

Database port không listen sẽ không sửa bằng 120 giây timeout; missing bean cũng không. Tune timeout khi có evidence backend sẵn sàng chậm/CI resource contention.

### 19.9. Copy application-prod.yml sang test không kiểm tra

Có thể trỏ tới production DB/broker, credentials hoặc activate scheduled jobs. Test config phải cô lập external resources và tuân thủ secret management.

### 19.10. Chạy reproducer intentional failure trong default suite

Khi `*ReproducerIT` bị Failsafe discovery, CI có thể đỏ ngoài ý muốn. Tách rõ integration test xanh và manual reproducer đỏ; dùng `ApplicationContextRunner` cho regression test.

### 19.11. Dùng random dependency version

Spring Boot BOM quản lý cả Framework/Spring Test/Jackson/Mockito. Override tùy tiện có thể tạo `NoSuchMethodError` rồi dẫn tới context failure ở nơi xa nguyên nhân.

### 19.12. Chỉ nhìn Maven exit code

Một build có thể xanh vì tests bị skip/disabled hoặc chỉ được rerun. Đọc executed count, failed/errors/skipped và Surefire reports.

### 19.13. Thay property khiến cache key đổi rồi so threshold

Thêm `debug=true` có thể tạo cache key khác; bạn đã thay thí nghiệm. Dùng nó để hiểu conditions, quay về exact original config để xác nhận failure.

### 19.14. Xóa toàn bộ ~/.m2

Nếu thật sự có dependency corruption, cần evidence như checksum/download error. Nếu exception là `NoSuchBeanDefinitionException` do slice, xóa Maven cache không có ích và gây tốn thời gian.

### 19.15. Thấy “Connection refused” rồi gọi mạng là lỗi

Với Testcontainers, có thể resource đã bị stop per-class trong khi Spring context còn cached; đây là lifecycle mismatch. Kiểm container ID/mapped port/client lifecycle trước khi đổ lỗi CI network.

### 19.16. Xóa database test sau lỗi context

Database có thể chứa data cần điều tra; cleanup global cũng làm hỏng tests khác. Dùng isolated test schema/targeted cleanup và log sanitized.

### 19.17. Sửa code bằng @Autowired(required=false)

Biến dependency bắt buộc thành nullable chỉ làm bean tạo được, nhưng có thể NPE/bug sau startup. Chỉ dùng optional dependencies khi behavior fallback được thiết kế/kiểm thử.

### 19.18. Đo root cause bằng thứ tự class name

`FirstReproducerIT` chưa chắc được chạy trước `SecondReproducerIT`. Surefire/JUnit order có thể đổi. Dựa logs, không dựa tên.

### 19.19. Dùng test-level @Transactional để chữa startup lỗi

Transaction trên JUnit method thường chưa mở lúc context bootstrap. Nó không chữa BeanCreationException/DataSource config. Với lỗi runtime DB/rollback, kiểm transaction boundary riêng.

### 19.20. Không chạy full suite sau fix

Fix MVC slice có thể giúp một test xanh, nhưng một full context profile integration khác vẫn missing AuditSink. Sửa và kiểm từng phạm vi có trách nhiệm.

## 20. Checklist khi nhận ticket "Failed to load ApplicationContext"

- [ ] Đã ghi đúng test class/method và test command?
- [ ] Biết failure xảy ra trước hay trong test body?
- [ ] Đã thu full stdout/stderr + Surefire report?
- [ ] Đã chọn đúng Spring context cache key đang fail?
- [ ] Đã tìm **startup attempt đầu tiên** cho key này?
- [ ] Có threshold exceeded messages không? Có bỏ qua chúng khi tìm root cause không?
- [ ] Đã đọc toàn bộ chuỗi Caused by?
- [ ] Đã xác định **actionable cause**, không chỉ deepest technical cause?
- [ ] Có Spring Boot FailureAnalyzer Description/Action hữu ích không?
- [ ] Đã xem active profiles/test properties/Environment precedence?
- [ ] Đã xác định test scope: @SpringBootTest hay slice?
- [ ] Missing bean thật hay bean bị loại bởi slice/conditional/profile?
- [ ] NoSuchBean hay NoUniqueBean?
- [ ] Có bean cycle/configuration override ngoài ý muốn?
- [ ] ConfigurationProperties đã được register/bind/validate đúng?
- [ ] Classpath/BOM/JDK versions được kiểm?
- [ ] Khi lỗi DB, đã kiểm URL, driver, credentials redacted, readiness?
- [ ] Khi dùng Testcontainers, resource lifetime khớp context cache?
- [ ] Khi Flyway/Liquibase lỗi, đã đọc migration đầu tiên fail?
- [ ] Có dùng DEBUG condition evaluation report đúng lúc?
- [ ] Không diễn giải tất cả negative condition matches là lỗi?
- [ ] Có chạy một reproducer hẹp với full stack trace?
- [ ] Có tránh thay 5 settings một lúc?
- [ ] Có sửa đúng tầng thay vì mock/disable mọi thứ?
- [ ] Có regression test xanh cho root cause?
- [ ] Không đưa deliberate fail repro vào default tests?
- [ ] Không tăng failure threshold làm permanent workaround?
- [ ] Không bật lazy initialization để che startup bug?
- [ ] Có chạy lại **failing suite** và kiểm executed/skipped/flaky counts?
- [ ] CI artifacts không lộ credentials/PII?
- [ ] Báo cáo có kết luận kèm evidence và remaining limitations?

## 21. Bài tập thực hành

1. Chạy `mvn clean test` của lab, đếm 8 methods dự kiến và ghi nhớ đó là expected chứ chưa phải kết quả đã chạy trong tài liệu.
2. Chạy `MissingSinkFirstReproducerIT`, tìm outer `Failed to load ApplicationContext`.
3. Truy nguyên đến `NoSuchBeanDefinitionException: AuditSink` trong reproducer.
4. Chạy hai MissingSink `*IT` trong một Maven invocation; tìm class/attempt first full failure và class bị threshold skip.
5. Bật `spring.test.context.failure.threshold=1000000` một lần; phân biệt repeated startup attempts với fix.
6. Thay threshold về mặc định; giải thích vì sao policy giúp fail-fast.
7. Chạy `BadBindingReproducerIT`, ghi property names và validation constraints bị reject.
8. Sửa endpoint/attempts để chạy `PropertiesOverrideHealthyTest`, không disable `@Validated`.
9. Chạy `MissingMvcDependencyReproducerIT` rồi `MvcSliceHealthyTest`; giải thích `@MockitoBean`.
10. Tự xóa `@MockitoBean` khỏi MVC healthy test trong branch học tập và chứng minh failure trở lại.
11. Thêm một `@Profile("integration")` cho `ConsoleAuditSink`, chỉ chạy profile `test`; chẩn đoán missing bean mới.
12. Thêm `@ConditionalOnProperty` cho sink, dùng condition report tìm negative match.
13. Tạo hai `AuditSink` implementations, phân biệt `NoUniqueBeanDefinitionException` với missing bean.
14. Thêm nested `@Configuration` vào test và xem nó có vô tình thay application config không.
15. So sánh nested `@TestConfiguration` và `@Import` để bổ sung collaborator.
16. Dùng `ApplicationContextRunner` tạo context thiếu bean, assert root cause mà JUnit PASS.
17. Dùng runner với bean factory ném IllegalStateException; verify marker trong deepest cause.
18. Chạy diagnostics với `debug=true`, tìm relevant entries trong ConditionEvaluationReport.
19. Thay `demo.client.attempts` bằng chữ không parse được; phân biệt conversion vs Bean Validation.
20. Thêm `@ConfigurationProperties` class nhưng quên registration, xác định nó không phải bind validation failure.
21. Tạo một `@SpringBootTest(webEnvironment=RANDOM_PORT)` test có main app đúng; phân biệt startup port với MOCK/NONE.
22. Tạo class chạy server fixed port đang dùng; xem Boot FailureAnalyzer và sửa bằng random port khi phù hợp.
23. Thêm dependency JDBC starter không có URL/driver trong một module thử nghiệm; tìm Datasource failure analyzer.
24. Viết Spring Boot Testcontainers variant với PostgreSQL service connection; inject failure khi Docker unavailable và phân loại.
25. Tạo migration SQL lỗi trong DB test riêng; tìm first failed migration, không disable Flyway.
26. Cho test A stop @Container per class nhưng test B reuse cached context, xem stale endpoint; refactor bằng managed container bean.
27. Chạy trong CI với 2 Surefire forks; giải thích vì sao failure count/cache không share qua JVM.
28. Bật parallel classes, lọc startup logs theo context key thay vì file line đầu tiên.
29. Kiểm một `NoSuchMethodError` do override Spring module version, rồi sửa dependency alignment bằng BOM.
30. Tạo bug report một trang có startup attempt, BeanCreationException chain, root reason, fix và regression test evidence.

## 22. Bảng quyết định nhanh

| Câu hỏi | Nếu có | Hành động |
| --- | --- | --- |
| Có `failure threshold exceeded`? | Có | Tìm first startup exception của cùng cache key |
| Test method đã chạy? | Chưa | Tập trung TestContext/bean/env/bootstrap |
| Deepest cause là missing bean? | Có | Xác định bean bị exclude hay chưa đăng ký |
| Test dùng MVC/JPA slice? | Có | Sửa collaborator trong slice/mock/import đúng |
| Có property bind/validation error? | Có | Tìm source/value/reason, sửa config |
| DB/broker connection refused? | Có | Kiểm endpoint, readiness, container lifecycle |
| Có Flyway/Hibernate failure? | Có | Kiểm migration/mapping/schema đầu tiên fail |
| Có ClassNotFound/NoSuchMethod? | Có | Kiểm dependency tree/BOM/JDK |
| Failure chỉ trong suite? | Có | Kiểm cache key, order/parallel, shared state |
| Failure chỉ sau class A? | Có | Kiểm @DirtiesContext/container stop/mock/reset |
| Có ApplicationContextRunner check xanh? | Có | Nó chứng minh failure branch hẹp, không thay full app |
| Sửa xong một test PASS? | Có | Chạy lại exact failing suite và verify reports |
| Debug property làm context key đổi? | Có | Quay lại original config để confirm |
| Build xanh nhờ tests bị skip? | Có | Không chấp nhận là QA pass |

## 23. Mẫu báo cáo chẩn đoán cho nhóm

Một báo cáo có ích cần mô tả evidence và boundaries:

~~~text
Symptom:
  SpringBootTest fails before @Test body.
  Several subsequent classes show failure threshold exceeded.

First failing context key:
  classes=[...], activeProfiles=[test], customizers=[...]
  first startup failure was in ...Test at ...

Exception chain:
  IllegalStateException Failed to load ApplicationContext
    -> UnsatisfiedDependencyException auditService
      -> NoSuchBeanDefinitionException AuditSink

Root diagnosis:
  @WebMvcTest was limited to MVC beans and did not provide AuditService.
  The production full application has a valid AuditSink bean;
  the defect was the test slice wiring, not a production dependency.

Fix:
  Add @MockitoBean AuditService in the MVC slice.
  Keep full-context integration test for real AuditService -> AuditSink.

Validation:
  Run narrow MvcSliceHealthyTest, then full affected suite.
  Record executed/failed/skipped/flaky counts and context cache data.

Caveat:
  Mockito collaborator proves controller contract only, not real sink delivery.
~~~

Đây là **mẫu định dạng**, không phải log hoặc kết quả thực thi của một CI run. Không ghi tên người dùng, password, token hoặc JDBC connection strings nhạy cảm vào báo cáo.

## 24. Kết luận

`Failed to load ApplicationContext` là **điểm bắt đầu điều tra**, không phải lời giải thích root cause. Với Spring Framework 6.2, một failure đầu tiên có thể bị che bởi các thông báo **context failure threshold (1) exceeded** của những tests sau cùng cache key. Muốn chẩn đoán chính xác, tìm **attempt đầu tiên theo thời gian**, lần theo `Caused by`, xác định bean/property/external resource thực sự hỏng và phân biệt lỗi của **test scope** với lỗi của **application production**.

Dùng `FailureAnalyzer`, `ConditionEvaluationReport`, targeted Maven `-Dtest` và `ApplicationContextRunner` để thu bằng chứng. Đừng tăng timeout/threshold, thêm `@DirtiesContext`, mock toàn bộ dependency hay bật lazy initialization chỉ để tránh nhìn thấy failure. Một fix đáng tin là **thay đổi nguyên nhân cụ thể** rồi chạy lại original failing test/suite, kiểm actual JUnit executed counts và giữ regression test cho đúng ranh giới.

## 25. Tài liệu chính thức

- Spring Framework 6.2 — Context Failure Threshold: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/failure-threshold.html
- Spring Framework 6.2 — Context Caching (cache keys, max size 32, LRU, JVM forks): https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework 6.2 — TestContext Framework key abstractions: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/key-abstractions.html
- Spring Framework 6.2 — @DynamicPropertySource: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Spring Framework 6.2 — TestContext Parallel Test Execution: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html
- Spring Boot 3.5.16 — SpringApplication Startup Failure / FailureAnalyzer / Debug Conditions: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5.16 — Testing Spring Boot Applications / @WebMvcTest / @MockitoBean: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5.16 — ApplicationContextRunner / Auto-configuration tests: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5.16 — @ConfigurationProperties Validation / Externalized Config: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot 3.5.16 — Testcontainers and Service Connections: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Boot 3.5.16 — Database Initialization: https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html
- Spring Boot 3.5.16 — Flyway/Liquibase and SQL databases: https://docs.spring.io/spring-boot/3.5/reference/data/sql.html
- Spring Framework 6.2 — MockitoBean/MockitoSpyBean Test Bean Overrides: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html
- Maven Surefire — Selecting Tests with -Dtest: https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html
- Maven Surefire — Understanding report files and test results: https://maven.apache.org/surefire/maven-surefire-plugin/examples/reporting.html
