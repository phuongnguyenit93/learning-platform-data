# `Failed to load ApplicationContext` và nguyên nhân đầu tiên

`Failed to load ApplicationContext` là thông báo tổng quát cho biết Spring Test không thể tạo hoặc làm mới application context cần thiết để chạy test. Đây thường không phải lỗi gốc. Nguyên nhân thực tế nằm trong exception lồng bên dưới: một bean không được tạo, dependency không được tìm thấy, property không hợp lệ, database không kết nối được, migration thất bại hoặc cấu hình auto-configuration không thỏa điều kiện.

Khi gặp lỗi này, hãy tìm lần khởi tạo context thất bại đầu tiên và lần theo chuỗi `Caused by` đến exception giải thích được vì sao Spring không thể tạo context. Đừng bắt đầu bằng cách sửa test method hoặc tăng timeout một cách ngẫu nhiên: test method thường chưa được gọi vì Spring thất bại ngay trong giai đoạn bootstrap.

## Thông báo này xuất hiện ở giai đoạn nào?

Spring TestContext Framework tạo `ApplicationContext` trước khi thực thi test cần context đó. TestContext bootstrapper đọc cấu hình, dựng context, refresh bean factory và khởi tạo các singleton cần thiết. Nếu một bước bắt buộc thất bại, Spring ném exception và test dừng trước phần thân test method.

Ví dụ log thường gặp:

```text
java.lang.IllegalStateException: Failed to load ApplicationContext

Caused by: org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'orderService'

Caused by: org.springframework.beans.factory.UnsatisfiedDependencyException:
Error creating bean with name 'orderService':
Unsatisfied dependency expressed through constructor parameter 0

Caused by: org.springframework.beans.factory.NoSuchBeanDefinitionException:
No qualifying bean of type 'com.example.store.PaymentGateway' available
```

Exception ngoài cùng là lỗi bootstrap do Spring Test báo lại. Các exception bên trong cho biết Spring đang tạo bean nào và dependency nào bị thiếu. Trong ví dụ này, việc sửa assertion của `orderService` không có ích; context không thể tạo bean vì thiếu `PaymentGateway`.

Một trường hợp khác:

```text
java.lang.IllegalStateException: Failed to load ApplicationContext

Caused by: org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'entityManagerFactory'

Caused by: org.hibernate.exception.JDBCConnectionException:
Unable to obtain JDBC Connection

Caused by: org.postgresql.util.PSQLException:
Connection to localhost:5432 refused
```

Ở đây lỗi khởi đầu không nằm trong entity mapping hay test assertion. Database không nhận kết nối tại endpoint được cấu hình. Cần kiểm tra database/container đã sẵn sàng, URL, port mapping, credentials và lifecycle của tài nguyên test.

## Cách đọc exception chain

Một stack trace thường có nhiều lớp bọc exception. Hãy đọc theo thứ tự sau:

1. **Thông báo ngoài cùng:** xác định framework hoặc test runner đang báo lỗi gì và context nào đang được khởi tạo.
2. **Các exception `Caused by`:** tìm bean name, constructor parameter, field, property, resource hoặc thao tác thất bại đầu tiên có ý nghĩa.
3. **Exception gốc ở tầng thấp:** nếu có, xác định lỗi hệ thống cụ thể như connection refused, authentication failed, file not found, class not found hoặc SQL syntax error.
4. **Stack frame đầu tiên thuộc code dự án:** tìm cấu hình, factory method, constructor hoặc `@Bean` method đã kích hoạt lỗi.

Ví dụ một chuỗi có thể đi qua `IllegalStateException` → `BeanCreationException` → `UnsatisfiedDependencyException` → `NoSuchBeanDefinitionException`. Hãy xem cả chuỗi, không chỉ dòng cuối. `BeanCreationException` thường cho biết bean đang được tạo; `UnsatisfiedDependencyException` chỉ ra injection point; `NoSuchBeanDefinitionException` chỉ ra kiểu bean không có candidate phù hợp.

Không phải lúc nào exception sâu nhất cũng là nguyên nhân cần sửa đầu tiên. Một exception thấp tầng có thể là hệ quả của cấu hình sai ở tầng trên, hoặc một lỗi `BeanCreationException` có thể chứa message rõ hơn exception cuối. Chọn exception đầu tiên giải thích được hành động thất bại, rồi xác nhận bằng bean name, property key, resource hoặc stack frame thuộc dự án.

### Phân biệt root cause với lỗi được bọc

Các loại exception thường gặp:

| Exception | Thường cho biết |
|---|---|
| `IllegalStateException: Failed to load ApplicationContext` | TestContext không thể tạo context; đây thường là wrapper tổng quát |
| `BeanCreationException` | Một bean không thể khởi tạo hoặc xử lý lifecycle |
| `UnsatisfiedDependencyException` | Không thể inject dependency vào constructor, field hoặc method |
| `NoSuchBeanDefinitionException` | Không có bean phù hợp với kiểu hoặc qualifier cần thiết |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng phù hợp mà injection point không chọn được một bean |
| `BeanDefinitionOverrideException` | Các bean definition xung đột tên và không được phép override |
| `BeanCurrentlyInCreationException` | Có thể tồn tại dependency cycle hoặc truy cập bean khi còn đang tạo |
| `BindException` / `ConfigurationPropertiesBindException` | Property không thể bind sang kiểu cấu hình mong muốn |
| `PlaceholderResolutionException` / lỗi unresolved placeholder | Một `${...}` không tìm được giá trị |
| `DataAccessResourceFailureException` / JDBC exception | Database hoặc kết nối dữ liệu gặp lỗi |
| `FlywayException` / Liquibase exception | Migration hoặc schema validation thất bại |
| `ClassNotFoundException` / `NoClassDefFoundError` | Thiếu class/dependency ở runtime hoặc classpath test không đồng bộ |
| `NoSuchMethodError` / `AbstractMethodError` | Các thư viện binary không tương thích version |

Tên exception là manh mối, không phải kết luận tự động. Hãy đọc message, cause và stack frame để biết exception được ném ở đâu và vì sao.

## “Nguyên nhân đầu tiên” và Spring context failure threshold

Từ Spring Framework 6.1, Spring TestContext có cơ chế *context failure threshold*. Mặc định, một context cache key chỉ được thử khởi tạo một lần. Nếu lần đầu thất bại, những lần test sau yêu cầu đúng context key đó có thể bị bỏ qua mà không thử khởi tạo lại.

Log ở những lần sau có thể trông như sau:

```text
ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context
```

Thông báo này không phải nguyên nhân gốc. Nó nói rằng Spring đã biết lần khởi tạo context tương ứng thất bại trước đó và không muốn lặp lại một lần bootstrap tốn thời gian. Hãy tìm exception đầy đủ của lần thất bại đầu tiên trong output test, log CI hoặc report của test runner.

Giá trị mặc định của threshold là `1`. Có thể cấu hình bằng system property:

```text
-Dspring.test.context.failure.threshold=1
```

Ví dụ tăng threshold trong lúc chẩn đoán:

```text
-Dspring.test.context.failure.threshold=3
```

Tăng threshold chỉ cho phép Spring thử lại nhiều lần hơn đối với cùng context cache key. Nó không sửa bean, property hoặc hạ tầng bị lỗi và thường không phải giải pháp cuối cùng. Nếu nguyên nhân là database chưa chạy, thử lại nhiều lần có thể chỉ tạo thêm log và kéo dài suite.

Nếu test chạy trên Spring Framework cũ hơn 6.1, thông báo failure threshold này có thể không xuất hiện. Hãy kiểm tra version Spring Test thực tế thay vì giả định mọi dự án đều có cơ chế này.

## Context cache khiến lỗi xuất hiện ở test khác

Spring TestContext cache `ApplicationContext` để các test có cấu hình tương đương có thể dùng chung context. Cache key được tạo từ những metadata như cấu hình classes, context loader, initializers, active profiles, property sources, context customizers, parent context và web resource path.

Do đó, một lỗi có thể được nhìn thấy ở nhiều test class:

```text
OrderControllerTest       -> Failed to load ApplicationContext
OrderServiceIntegrationTest -> ApplicationContext failure threshold exceeded
PaymentFlowTest           -> ApplicationContext failure threshold exceeded
```

Các class có thể đang yêu cầu cùng một context cache key. Test class thứ hai và thứ ba chưa chắc có lỗi độc lập; chúng có thể chỉ nhận lại trạng thái thất bại đã được cache từ lần đầu.

Hãy xác định test class nào khởi tạo context key đó đầu tiên. Kiểm tra annotation và cấu hình dùng chung, ví dụ `@SpringBootTest`, `@ActiveProfiles`, `@TestPropertySource`, `@DynamicPropertySource`, `@Import` và nested test configuration. Nếu một class dùng property hoặc profile khác, nó có thể tạo cache key khác và thực sự khởi tạo context riêng.

Không vội thêm `@DirtiesContext` vào tất cả test. Annotation này loại context khỏi cache theo thời điểm được chỉ định, nhưng không sửa cấu hình sai. Nếu bean vẫn thiếu hoặc database vẫn không kết nối, context mới cũng sẽ thất bại.

## Quy trình chẩn đoán có thứ tự

### Bước 1: Xác nhận lần thất bại đầu tiên

Tìm lần xuất hiện đầu tiên của `Failed to load ApplicationContext` trong log đầy đủ. Sau đó tìm toàn bộ phần `Caused by` liên quan đến lần đó. Đừng chỉ xem summary ở cuối Gradle/Maven hoặc thông báo failure threshold của test chạy sau.

Trong CI, tải test report và log gốc của task. Một summary như `Tests failed` hoặc `ApplicationContext failure threshold exceeded` không chứa đủ dữ kiện để kết luận.

### Bước 2: Xác định context đang được nạp

Ghi lại các metadata sau từ test class:

- `@SpringBootTest` hay `@ContextConfiguration`?
- Có chỉ định `classes` không? Nếu không, cấu hình chính được tìm thấy ở package nào?
- Có `@ActiveProfiles`, `@TestPropertySource` hoặc inline `properties` không?
- Có `@DynamicPropertySource`, `@Import`, `@TestConfiguration` hoặc initializer riêng không?
- Web environment là `MOCK`, `RANDOM_PORT`, `DEFINED_PORT` hay `NONE`?
- Test có dùng parent/child context, `@WebAppConfiguration` hoặc cấu hình servlet riêng không?

Context cần chẩn đoán là context được tạo từ toàn bộ các metadata này, không chỉ từ tên test class.

### Bước 3: Tìm bean hoặc resource đầu tiên thất bại

Nếu log có `Error creating bean with name '...'`, tìm bean đó trong cấu hình hoặc component. Xem bean được tạo bằng component scan, `@Bean` factory method, auto-configuration hay test configuration.

Nếu log có constructor parameter hoặc field, đối chiếu kiểu dependency, qualifier và profile. Nếu lỗi nằm trong factory method, mở đúng method để xác định thao tác gây lỗi.

Nếu log chỉ ra property hoặc resource, tìm nơi property được khai báo và nguồn ưu tiên của nó. Nếu lỗi nằm ở datasource, broker hoặc HTTP client, xác minh endpoint bằng cấu hình thực tế mà test context đang nhận.

### Bước 4: Phân loại nguyên nhân

Nhóm lỗi giúp giới hạn nơi cần kiểm tra:

| Nhóm | Dấu hiệu | Nơi kiểm tra trước |
|---|---|---|
| Cấu hình chính | Không tìm thấy `@SpringBootConfiguration`, nhiều candidate | Package test, `classes`, cấu trúc cấu hình Boot |
| Component scan/import | Thiếu service, repository hoặc configuration bean | `@SpringBootApplication`, `@ComponentScan`, `@Import`, package boundary |
| Dependency injection | `NoSuchBeanDefinitionException`, `NoUniqueBeanDefinitionException` | Constructor/field injection, `@Qualifier`, `@Primary`, profile |
| Dependency cycle | `BeanCurrentlyInCreationException` | Chuỗi phụ thuộc giữa constructor và factory methods |
| Property binding | Invalid value, unresolved placeholder, bind failure | `application*.yml`, environment, inline properties, `@ConfigurationProperties` |
| Database | Connection refused, authentication failed, SQL/migration error | Container readiness, URL, port, credentials, driver, schema và migration |
| Messaging/cache/search | Timeout, connection refused, incompatible protocol | Broker/service lifecycle, mapped port, credentials, client version |
| Web server | Port in use, servlet context initialization failure | `webEnvironment`, `server.port`, filter/servlet registration |
| Classpath/version | `NoClassDefFoundError`, `NoSuchMethodError` | Dependency tree, BOM và version Spring/Boot/library |
| Bean initialization side effect | Constructor hoặc `@PostConstruct` gọi dịch vụ ngoài | Initialization logic, network access, test profile và readiness |

### Bước 5: Thay đổi một nguyên nhân rồi chạy lại test liên quan

Sau khi đã có giả thuyết cụ thể, thay đổi một cấu hình hoặc dependency tại một thời điểm. Chạy test class gây lỗi đầu tiên để xem context có thể khởi tạo hay không. Khi context đã khởi tạo, chạy các test dùng chung context key để xác nhận lỗi lan truyền đã biến mất.

Không thay đồng thời profile, database, component scan và mock configuration. Nếu nhiều biến cùng thay đổi, rất khó xác định điều gì thực sự giải quyết lỗi.

## Các nhóm nguyên nhân phổ biến

### Không tìm thấy cấu hình ứng dụng

Với `@SpringBootTest`, Boot thường dò class `@SpringBootConfiguration` từ package của test đi ngược lên package cha. Nếu test đặt ngoài package tree hoặc dự án có nhiều ứng dụng Boot, việc dò tìm có thể thất bại hoặc chọn sai cấu hình.

Chỉ rõ class ứng dụng:

```java
@SpringBootTest(classes = StoreApplication.class)
class OrderIntegrationTest {
}
```

Với Spring Test thuần, kiểm tra `@ContextConfiguration(classes = ...)`, resource XML hoặc initializer. Đừng dùng `@SpringBootTest` cho một ứng dụng không có cấu hình Boot chỉ để cố khởi động context.

### Thiếu bean hoặc có nhiều bean cùng kiểu

Ví dụ lỗi thiếu bean:

```text
No qualifying bean of type 'PaymentGateway' available
```

Kiểm tra bean có được scan/import hay không, profile có kích hoạt cấu hình tạo bean không, và điều kiện `@ConditionalOnProperty`/`@ConditionalOnClass` có thỏa không.

Nếu có nhiều implementation:

```text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2: stripeGateway, mockGateway
```

Hãy chọn bean bằng `@Qualifier`, đánh dấu một implementation là `@Primary` nếu đó là default thực sự, hoặc giới hạn cấu hình test để chỉ có implementation cần dùng. Không thêm một mock bean có cùng type mà không kiểm tra xung đột với bean production.

### Property bị thiếu hoặc không bind được

Một cấu hình như:

```java
@ConfigurationProperties(prefix = "payments")
@Validated
public record PaymentProperties(
        @NotBlank String apiUrl,
        @NotBlank String merchantId) {
}
```

có thể làm context thất bại nếu `payments.api-url` hoặc `payments.merchant-id` thiếu, sai tên hoặc không hợp lệ. Kiểm tra active profile và property source đang thực sự được nạp. `@TestPropertySource`, `@SpringBootTest(properties = ...)`, environment variables và `@DynamicPropertySource` có thể cung cấp giá trị khác nhau.

Ví dụ khai báo property riêng cho test:

```java
@SpringBootTest(properties = {
        "payments.api-url=https://payments.test.invalid",
        "payments.merchant-id=test-merchant"
})
class PaymentServiceIntegrationTest {
}
```

Nếu giá trị cần lấy từ container hoặc server khởi động động, dùng `@DynamicPropertySource`. Bảo đảm supplier trả endpoint còn sống tại thời điểm Spring khởi tạo bean sử dụng property đó.

### Database chưa sẵn sàng hoặc datasource sai

Với Testcontainers, container đã được tạo chưa chắc database đã sẵn sàng nhận connection. Kiểm tra wait strategy, startup timeout và log container. Lấy JDBC URL từ API container thay vì tự đoán port.

Với `@DataJpaTest`, Spring Boot có thể thay datasource bằng embedded database nếu cấu hình cho phép. Nếu test phải dùng database container, cấu hình `@AutoConfigureTestDatabase(replace = Replace.NONE)` phù hợp với version Boot đang dùng.

Nếu kết nối thành công nhưng context vẫn lỗi ở `entityManagerFactory`, kiểm tra dialect, schema, migration, entity mapping và extension database. Một lỗi Flyway/Liquibase lúc startup thường khiến context không thể refresh.

### Auto-configuration không được kích hoạt như mong đợi

Spring Boot auto-configuration phụ thuộc classpath, properties và điều kiện. Một dependency bị thiếu có thể khiến cấu hình không được bật; một property bị đổi có thể khiến bean không còn được tạo.

Khởi chạy ứng dụng/test với chế độ debug để xem condition evaluation report:

```properties
debug=true
```

Hoặc truyền `--debug` cho Spring Boot application. Report cho biết auto-configuration nào được match, không match và điều kiện nào không thỏa. Nó hữu ích khi bean mong đợi được tạo bởi auto-configuration nhưng không xuất hiện.

Không nên bật debug lâu dài cho toàn bộ suite nếu output quá lớn. Bật tạm trong test class hoặc task tái hiện lỗi để thu thập thông tin cần thiết.

### Dependency version hoặc classpath không tương thích

Các lỗi như `NoSuchMethodError`, `AbstractMethodError`, `NoClassDefFoundError` thường chỉ ra binary incompatibility hoặc thiếu dependency. Kiểm tra Spring Boot BOM, Spring Framework modules, Hibernate, database driver và thư viện test.

Đừng chữa lỗi version bằng cách thêm một JAR rời vào test runtime mà không hiểu dependency graph. Dùng dependency management đồng bộ của Spring Boot hoặc platform mà dự án đã chọn. So sánh runtime classpath của test với ứng dụng khi chạy.

### Bean khởi tạo gọi dịch vụ ngoài

Một constructor, `@PostConstruct`, `InitializingBean#afterPropertiesSet()` hoặc `@Bean` factory method có thể thực hiện HTTP call, đọc file, kết nối broker hoặc gọi secret manager. Khi dịch vụ ngoài không có trong môi trường test, context thất bại dù test không hề gọi chức năng đó.

Ưu tiên để constructor và bean initialization chỉ tạo object và kiểm tra cấu hình cơ bản. Chuyển công việc network hoặc side effect sang phương thức được gọi rõ ràng sau khi context đã sẵn sàng. Nếu startup behavior là yêu cầu cần kiểm tra, cung cấp dịch vụ test tương thích và xác nhận readiness trước khi tạo context.

## Dùng Spring Boot condition report và failure analysis

Spring Boot có `FailureAnalyzers` cho nhiều lỗi khởi động quen thuộc. Thay vì chỉ đọc `Failed to load ApplicationContext`, tìm phần `APPLICATION FAILED TO START` hoặc `Failure Analysis` trong log:

```text
***************************
APPLICATION FAILED TO START
***************************

Description:

Parameter 0 of constructor in ... required a bean of type ...
that could not be found.

Action:

Consider defining a bean of type ... in your configuration.
```

Phần này có thể chỉ ra mô tả ngắn và hành động gợi ý. Nó không thay thế stack trace, nhưng là manh mối tốt để tìm cấu hình cần sửa.

Nếu nghi ngờ auto-configuration, bật `debug=true` để có condition evaluation report. Nếu nghi ngờ bean creation, giữ stack trace đầy đủ và tìm bean name/constructor parameter. Nếu nghi ngờ property, bật log phù hợp cho configuration binding và kiểm tra nguồn giá trị mà Environment đang dùng; tránh in secret vào log.

## Tái hiện lỗi với một test nhỏ

Khi một suite lớn có nhiều test cùng thất bại, hãy tạo cách tái hiện nhỏ nhất dùng cùng context metadata. Ví dụ, nếu lỗi xuất hiện với một `@SpringBootTest` profile `integration`, hãy chạy riêng test class đầu tiên với đúng profile và property sources đó.

Một context smoke test có thể giúp xác nhận cấu hình:

```java
@SpringBootTest
@ActiveProfiles("integration")
class IntegrationContextSmokeTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void createsRequiredInfrastructureBeans() {
        assertThat(context.getBean(OrderService.class)).isNotNull();
        assertThat(context.getBean(OrderRepository.class)).isNotNull();
    }
}
```

Smoke test không thay thế test hành vi, nhưng có thể tách lỗi bootstrap khỏi lỗi logic. Khi context không thể khởi tạo, assertion trong method vẫn chưa được chạy; stack trace bootstrap mới là dữ liệu cần phân tích.

Với auto-configuration riêng, `ApplicationContextRunner` có thể tạo context nhỏ và kiểm tra điều kiện mà không cần khởi động toàn ứng dụng:

```java
class PaymentAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            PaymentAutoConfiguration.class));

    @Test
    void createsGatewayWhenEnabled() {
        contextRunner
                .withPropertyValues("payments.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(PaymentGateway.class);
                });
    }
}
```

`ApplicationContextRunner` đặc biệt hữu ích khi phát triển auto-configuration hoặc muốn kiểm tra điều kiện tạo bean độc lập. Nó không chứng minh full application context khởi động được; test `@SpringBootTest` vẫn cần thiết cho integration behavior của toàn ứng dụng.

## Thu thập log hữu ích khi chạy test

Khi test thất bại trong CI, cần giữ lại output đầy đủ của test runner và report XML/HTML. Với Gradle, có thể chạy một test cụ thể và yêu cầu stack trace đầy đủ:

```bash
./gradlew test --tests 'com.example.store.OrderIntegrationTest' --stacktrace --info
```

Với Maven Surefire:

```bash
mvn -Dtest=OrderIntegrationTest -DtrimStackTrace=false test
```

Đây là ví dụ lệnh chẩn đoán; việc chạy build thuộc quy trình của người thực hiện task, không phải bước soạn bài này. Hãy dùng cú pháp phù hợp wrapper và build tool của dự án.

Trong log, giữ lại phần từ lần đầu context bắt đầu refresh đến exception cuối cùng trong cause chain. Nếu chỉ chia sẻ một đoạn log, đừng bỏ các dòng `Caused by`, bean name, property key hoặc stack frame đầu tiên thuộc code dự án. Khi log chứa credentials, token hoặc URL có thông tin nhạy cảm, hãy che các giá trị đó trước khi chia sẻ.

## Khi nào nên dùng @DirtiesContext?

`@DirtiesContext` đánh dấu context bị thay đổi và cần loại khỏi cache. Spring sẽ đóng context theo mode được chọn và tạo context mới khi test sau cần nó.

Annotation này phù hợp khi test thay đổi trạng thái singleton bean hoặc cấu hình context mà không thể khôi phục an toàn. Nó không phải cách sửa mặc định cho `Failed to load ApplicationContext`.

Nếu context thất bại ngay trong lần đầu bootstrap, `@DirtiesContext` không thể tạo ra bean bị thiếu, sửa property hoặc khởi động database. Hãy sửa nguyên nhân gốc trước. Chỉ dùng `@DirtiesContext` nếu đã xác định lỗi liên quan đến context state bị test trước làm bẩn, hoặc cần bảo đảm context được đóng sau một test có side effect cấp context.

## Checklist chẩn đoán nhanh

Khi gặp `Failed to load ApplicationContext`, lần lượt trả lời các câu hỏi:

1. Đây có phải lần bootstrap đầu tiên của context key hay chỉ là failure-threshold skip?
2. Exception ngoài cùng bọc lỗi gì? Các `Caused by` đầu tiên chỉ ra bean, property hoặc resource nào?
3. Test đang nạp cấu hình chính nào, profile nào và web environment nào?
4. Dependency thất bại là bean nội bộ, property, classpath hay dịch vụ ngoài?
5. Nếu là dịch vụ ngoài, endpoint có đúng và service đã readiness chưa?
6. Nếu là auto-configuration, condition report nói điều kiện nào không thỏa?
7. Sau khi sửa một nguyên nhân, test class đầu tiên có khởi tạo context thành công không?
8. Các test dùng chung context cache key có còn nhận lỗi cũ không?

## Bảng phân biệt thông báo và hành động

| Thông báo trong log | Cách hiểu | Việc cần làm đầu tiên |
|---|---|---|
| `Failed to load ApplicationContext` | Context bootstrap thất bại | Đọc cause chain của lần đầu tiên |
| `failure threshold exceeded` | Spring bỏ qua lần thử lặp lại cho context key đã thất bại | Tìm log của lần bootstrap đầu tiên |
| `NoSuchBeanDefinitionException` | Thiếu bean phù hợp | Kiểm tra scan/import/profile/conditional và injection type |
| `NoUniqueBeanDefinitionException` | Có nhiều bean candidate | Kiểm tra `@Qualifier`, `@Primary` và test configuration |
| `Could not resolve placeholder` | Thiếu property | Kiểm tra profile và property sources |
| `Failed to bind properties` | Giá trị cấu hình không bind/validate được | Kiểm tra prefix, tên key, kiểu dữ liệu và constraint |
| `Connection refused` | Endpoint không nhận kết nối | Kiểm tra service readiness, host và mapped port |
| `FlywayValidateException` | Migration history hoặc checksum/schema không hợp lệ | Kiểm tra migration files và database state |
| `Port already in use` | Web server không bind được cổng | Dùng `RANDOM_PORT` hoặc giải phóng cổng test |
| `NoSuchMethodError` | Binary version không tương thích | Kiểm tra dependency management và runtime classpath |

`Failed to load ApplicationContext` chỉ là dấu hiệu rằng Spring không thể hoàn thành bootstrap. Chẩn đoán hiệu quả bắt đầu từ lần thất bại đầu tiên, xác định bean hoặc tài nguyên đầu tiên không thể tạo, rồi kiểm tra đúng cấu hình và hạ tầng liên quan. Khi phân biệt được lỗi gốc với thông báo lặp do context cache, bạn sẽ tránh sửa nhầm test method, thêm `@DirtiesContext` không cần thiết hoặc tăng threshold mà không giải quyết nguyên nhân.
