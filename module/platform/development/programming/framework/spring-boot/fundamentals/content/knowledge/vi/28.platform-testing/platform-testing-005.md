# ApplicationContextRunner cho cấu hình và điều kiện có phạm vi hẹp

Trong một ứng dụng Spring Boot, không phải lỗi nào cũng nằm ở logic của service hoặc REST controller. Nhiều lỗi xuất hiện ngay từ lúc Spring dựng `ApplicationContext`: một bean không được đăng ký dù property đã bật, hai bean cạnh tranh cùng một kiểu, auto-configuration không lùi lại khi người dùng định nghĩa bean riêng, hoặc một điều kiện `@ConditionalOnClass` hoạt động sai khi dependency vắng mặt.

Nếu dùng `@SpringBootTest` cho mọi tình huống trên, test có thể phải khởi tạo quá nhiều thứ: component scanning, DataSource, web server giả lập, security configuration và các auto-configurations không liên quan. Điều cần kiểm tra đôi khi chỉ là một câu hỏi rất hẹp:

> Với tập bean, classpath và properties cụ thể, Spring có tạo đúng bean này hay không?

**`ApplicationContextRunner`** là công cụ trong Spring Boot Test được thiết kế cho những câu hỏi như vậy. Nó tạo một Spring context nhỏ theo cấu hình do test chủ động khai báo, chạy callback để kiểm tra kết quả, rồi đóng context. Đây là lựa chọn đặc biệt phù hợp cho **cấu hình Spring, điều kiện đăng ký bean và auto-configuration có phạm vi hẹp**, chứ không phải công cụ thay thế mọi kiểu integration test.

Bài học trình bày từ API cơ bản đến kiểm thử `@ConditionalOnProperty`, `@ConditionalOnMissingBean`, `@ConditionalOnClass`, thứ tự cấu hình, classpath giả lập, context startup failure, debugging condition report và những giới hạn khi so với `@SpringBootTest`. Ví dụ tập trung vào Spring Boot có các API `ApplicationContextRunner` và `AutoConfigurations`; package import và một số API phụ trợ có thể khác giữa các thế hệ framework.

## 1. Tại sao cần kiểm thử cấu hình Spring?

Giả sử ứng dụng có một thư viện gửi audit log và muốn cung cấp auto-configuration:

- Khi `demo.audit.enabled=true`, tự tạo `AuditSink` mặc định.
- Khi property bị tắt hoặc không có, không tạo `AuditSink` mặc định.
- Nếu ứng dụng đã khai báo một `AuditSink` riêng, auto-configuration phải **back off** thay vì tạo thêm bean.
- Nếu một dependency tùy chọn vắng mặt, cấu hình liên quan không được kích hoạt.
- Nếu người dùng cấu hình sai, lỗi cần rõ ràng và dự đoán được.

Những yêu cầu này là về **bean registration**, không phải về HTTP response hay nội dung được lưu trong database.

Một kiểm thử tốt phải xác nhận điều kiện **có** và **không**:

| Tình huống | Kết quả mong đợi |
|---|---|
| Audit enabled, chưa có bean tùy chỉnh | Có đúng một `AuditSink` mặc định |
| Audit disabled | Không tạo `AuditSink` mặc định |
| Không có property, mặc định disabled | Không tạo `AuditSink` mặc định |
| Audit enabled, đã có bean người dùng | Dùng bean người dùng, không tạo bean mặc định |
| Thiếu thư viện tùy chọn | Auto-configuration phụ thuộc thư viện đó không hoạt động |
| Thiếu bean bắt buộc | Context báo lỗi startup theo hợp đồng đã định |

`ApplicationContextRunner` cho phép dựng riêng từng tình huống mà không phải tạo toàn bộ application.

## 2. ApplicationContextRunner là gì?

Class chính:

~~~java
org.springframework.boot.test.context.runner.ApplicationContextRunner
~~~

Một cách dùng cơ bản:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner();
~~~

Runner là một **builder-like test utility**. Bạn thêm cấu hình, properties, beans hoặc classloader mong muốn, sau đó gọi `run(...)`.

~~~java
contextRunner
        .withUserConfiguration(MyConfiguration.class)
        .withPropertyValues("demo.feature.enabled=true")
        .run(context -> {
            assertThat(context).hasSingleBean(MyService.class);
        });
~~~

Trong callback, biến `context` là một **assertable context** do Spring Boot Test cung cấp. Nó cho phép:

- Kiểm tra bean có tồn tại không.
- Lấy bean cụ thể ra để kiểm tra state/behavior.
- Kiểm tra context startup thành công hay thất bại.
- Quan sát những property được đưa vào `Environment`.
- Kiểm tra cấu hình có đúng số lượng bean hoặc loại bean mong muốn không.

Sau khi callback kết thúc, runner quản lý việc đóng context thử nghiệm. Thường không cần tự gọi `context.close()`.

### Điểm mạnh nằm ở sự chủ động

Khác với một test full application, runner không chủ động tìm mọi cấu hình trong dự án chỉ vì test nằm cùng package. Bạn khai báo cụ thể các configuration classes hoặc auto-configurations muốn đưa vào context.

Điều này giúp kết quả dễ giải thích: nếu bean không xuất hiện, phạm vi nghi vấn thường chỉ gồm cấu hình và dependencies bạn đã cung cấp.

## 3. So sánh với @SpringBootTest

| Tiêu chí | `ApplicationContextRunner` | `@SpringBootTest` |
|---|---|---|
| Mục tiêu | Kiểm thử cấu hình/conditions có phạm vi hẹp | Kiểm thử một ứng dụng Spring Boot với phạm vi rộng hơn |
| Cách xác định cấu hình | Khai báo tường minh bằng runner | Có thể tìm main configuration và áp dụng bootstrap của Boot |
| Chi phí khởi tạo | Thường thấp hơn | Thường cao hơn tùy ứng dụng |
| Component scanning | Không tự quét toàn bộ project | Có thể thực hiện theo cấu hình ứng dụng |
| Auto-configuration | Chỉ những cấu hình được đưa vào theo cách tương ứng | Thường là tập auto-configurations của ứng dụng |
| Database/web infrastructure | Không cần nếu không được thêm | Có thể được tạo hoặc yêu cầu thêm |
| Property scenarios | Tạo từng scenario ngắn bằng `withPropertyValues` | Có thể dùng test properties/profiles và test context |
| Điều kiện thiếu class | Có `FilteredClassLoader` tiện lợi | Khó mô phỏng classpath khác trong cùng test |
| End-to-end HTTP/database | Không phải mục tiêu chính | Phù hợp hơn khi kết hợp test facilities thích hợp |
| Phát hiện lỗi wiring toàn ứng dụng | Chỉ trong subset đã khai báo | Bao phủ rộng hơn |

### Không phải runner luôn tốt hơn

Nếu bạn cần biết REST controller đã được security filter bảo vệ đúng không, JPA mapping có khởi động với database thật không, hay toàn bộ application có start thành công không, một test rộng hơn phù hợp hơn.

Nếu bạn chỉ cần xác nhận điều kiện `@ConditionalOnProperty` với ba giá trị property, dựng full context có thể không cần thiết.

**Chọn công cụ dựa trên phạm vi cần chứng minh**, không dựa trên tốc độ test đơn thuần.

## 4. Dependency và import cần thiết

Thông thường dự án Spring Boot test có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Với Gradle Kotlin DSL:

~~~kotlin
dependencies {
    testImplementation(
        "org.springframework.boot:spring-boot-starter-test"
    )
}

tasks.test {
    useJUnitPlatform()
}
~~~

Một test thường import:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.autoconfigure.AutoConfigurations;

import static org.assertj.core.api.Assertions.assertThat;
~~~

Các annotation Spring tùy ví dụ còn có:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
~~~

`ApplicationContextRunner` là **test utility**, nên đặt ở test source set/scope. Không cần đưa `spring-boot-test` vào runtime dependency của ứng dụng production chỉ để dùng runner trong unit/integration tests.

## 5. Ví dụ nhỏ nhất: một @Configuration, một bean

Tạo cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
class ClockConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Kiểm thử:

~~~java
class ClockConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(ClockConfiguration.class);

    @Test
    void registersClock() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(Clock.class);

            Clock clock = context.getBean(Clock.class);
            assertThat(clock.getZone()).isEqualTo(ZoneOffset.UTC);
        });
    }
}
~~~

Ý nghĩa từng phần:

1. `new ApplicationContextRunner()` tạo runner ban đầu.
2. `withUserConfiguration(ClockConfiguration.class)` đưa class cấu hình người dùng vào context thử nghiệm.
3. `run(context -> ...)` tạo context mới, đánh giá bean definitions rồi gọi assertion.
4. `hasSingleBean(Clock.class)` xác nhận trong context có đúng một bean kiểu `Clock`.
5. `context.getBean(Clock.class)` cho phép kiểm tra giá trị trả về thực tế.

Test không yêu cầu main Spring Boot application và không cần khởi động web server.

### Tại sao có proxyBeanMethods=false?

Trong những configuration class đơn giản, `@Configuration(proxyBeanMethods = false)` giúp sử dụng chế độ không tạo proxy nhằm chặn lời gọi giữa các `@Bean` methods. Nó phù hợp khi các bean methods không trực tiếp gọi nhau để lấy singleton dependency.

Đây là một tối ưu/thiết kế configuration class; nó **không phải công tắc** bật/tắt `ApplicationContextRunner`. Runner hoạt động với cả cấu hình thông thường và cấu hình kiểu này.

## 6. Runner tạo context mới cho từng run

Một runner có thể được khai báo là field của test:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withUserConfiguration(ClockConfiguration.class);
~~~

Sau đó dùng nhiều lần:

~~~java
@Test
void firstScenario() {
    contextRunner.run(context -> {
        assertThat(context).hasSingleBean(Clock.class);
    });
}

@Test
void secondScenario() {
    contextRunner.run(context -> {
        assertThat(context).hasSingleBean(Clock.class);
    });
}
~~~

Mỗi lời gọi `run` khởi tạo một context độc lập và đóng nó sau khi callback kết thúc. Không nên lưu một bean lấy từ callback để dùng sau khi context đã đóng, nhất là khi bean giữ kết nối, executor hoặc resource có lifecycle.

### Runner có thể được tùy biến mà không sửa field gốc

Ví dụ:

~~~java
private final ApplicationContextRunner baseRunner =
        new ApplicationContextRunner()
                .withUserConfiguration(ClockConfiguration.class);

@Test
void scenarioWithExtraProperty() {
    baseRunner
            .withPropertyValues("demo.mode=fast")
            .run(context -> {
                assertThat(context.getEnvironment()
                        .getProperty("demo.mode"))
                        .isEqualTo("fast");
            });
}
~~~

Các `with...` methods tạo cấu hình runner dẫn xuất theo API thiết kế để có thể tái sử dụng. Điều này giúp các scenario giữ cùng baseline mà không để properties của test trước vô tình chảy sang test sau.

### Không reuse ApplicationContext sau callback

Đoạn sau thể hiện ý tưởng không nên làm:

~~~java
AtomicReference<MyService> ref = new AtomicReference<>();

contextRunner.run(context -> {
    ref.set(context.getBean(MyService.class));
});

// Bean có thể thuộc context đã đóng:
ref.get().execute();
~~~

Hãy đặt assertion hoặc lời gọi cần kiểm tra trong callback, hoặc tạo một test context với lifecycle do test framework quản lý nếu cần quan sát trạng thái dài hơn.

## 7. Kiểm thử @ConditionalOnProperty

Đây là một use case phổ biến nhất cho `ApplicationContextRunner`.

Giả sử ứng dụng có interface ghi nhận audit:

~~~java
public interface AuditSink {
    void record(String eventName);
}
~~~

Implementation mặc định:

~~~java
public final class ConsoleAuditSink implements AuditSink {

    @Override
    public void record(String eventName) {
        System.out.println("AUDIT: " + eventName);
    }
}
~~~

Auto-configuration:

~~~java
@AutoConfiguration
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.audit",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    @ConditionalOnMissingBean(AuditSink.class)
    AuditSink auditSink() {
        return new ConsoleAuditSink();
    }
}
~~~

`@ConditionalOnProperty` quyết định có đăng ký bean khi property có giá trị yêu cầu; `matchIfMissing = false` có nghĩa thiếu property thì điều kiện không match.

### Một runner dành riêng cho auto-configuration

~~~java
class AuditAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AuditAutoConfiguration.class
                            )
                    );

    @Test
    void registersAuditSinkWhenEnabled() {
        contextRunner
                .withPropertyValues("demo.audit.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditSink.class);
                    assertThat(context.getBean(AuditSink.class))
                            .isInstanceOf(ConsoleAuditSink.class);
                });
    }

    @Test
    void doesNotRegisterAuditSinkWhenDisabled() {
        contextRunner
                .withPropertyValues("demo.audit.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AuditSink.class);
                });
    }

    @Test
    void doesNotRegisterAuditSinkWhenPropertyMissing() {
        contextRunner.run(context -> {
            assertThat(context).doesNotHaveBean(AuditSink.class);
        });
    }
}
~~~

Test phân biệt ba scenario rõ ràng. Không cần tạo ba `@SpringBootTest` classes hoặc ba startup configurations để chạy những điều kiện đơn giản này.

### Kiểm tra chính xác contract, không chỉ assert context starts

Một test chỉ làm:

~~~java
contextRunner.run(context ->
        assertThat(context).hasNotFailed()
);
~~~

có thể pass ngay cả khi bean mục tiêu không được đăng ký. Với conditional configuration, cần kiểm tra **sự hiện diện, sự vắng mặt và kiểu bean phù hợp**.

## 8. Hiểu đúng các trạng thái của ConditionalOnProperty

Với cấu hình:

~~~java
@ConditionalOnProperty(
        prefix = "demo.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
~~~

kết quả khái quát:

| `demo.audit.enabled` | Điều kiện match? |
|---|---|
| `true` | Có |
| `false` | Không |
| Không khai báo | Không |
| Một chuỗi khác, ví dụ `enabled` | Không khi `havingValue="true"` |

Nếu `havingValue` không được đặt, semantics của `@ConditionalOnProperty` không nên được hiểu như Java boolean parse đơn thuần trong mọi trường hợp; điều kiện thường coi property hiện diện và không bằng `false` là match. Vì vậy, với công tắc boolean, việc ghi rõ `havingValue = "true"` có thể làm contract dễ hiểu hơn.

### matchIfMissing=true

~~~java
@ConditionalOnProperty(
        prefix = "demo.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
~~~

Trong trường hợp property vắng mặt, điều kiện có thể match. Điều này phù hợp với feature bật mặc định và chỉ tắt khi cấu hình rõ `false`.

Khi kiểm thử, phải có test cho **missing property**; chỉ kiểm tra true/false sẽ không chứng minh semantics mặc định.

### Đừng dùng một test để khẳng định cả precedence

`withPropertyValues` đặt property vào context runner. Nó giúp kiểm tra giá trị được cung cấp cho condition, nhưng không tự kiểm chứng toàn bộ precedence của command line, environment variables và Config Data trong một SpringApplication thật. Nếu mục tiêu là precedence xuyên nhiều nguồn, cần test ở phạm vi phù hợp hơn.

## 9. withPropertyValues nhận nhiều cặp key=value

Ví dụ:

~~~java
contextRunner
        .withPropertyValues(
                "demo.audit.enabled=true",
                "demo.audit.prefix=ORDER",
                "demo.audit.batch-size=25"
        )
        .run(context -> {
            Environment environment = context.getEnvironment();

            assertThat(
                    environment.getProperty("demo.audit.prefix")
            ).isEqualTo("ORDER");

            assertThat(
                    environment.getProperty(
                            "demo.audit.batch-size",
                            Integer.class
                    )
            ).isEqualTo(25);
        });
~~~

Định dạng tham số là chuỗi property assignment. Nó hữu ích khi test một tập thông số cụ thể liên quan đến bean.

### Một chuỗi property không tự cấu hình mọi thứ

Nếu auto-configuration đọc `@ConfigurationProperties`, binding cần infrastructure phù hợp. Nếu bean đọc `Environment` trực tiếp, property có thể được truy cập từ Environment. Nếu không có configuration class hoặc binding đăng ký, việc thêm property đơn thuần **không tự tạo bean**.

### Chọn giá trị dễ phân biệt

Nếu đang kiểm tra property binding, nên sử dụng giá trị không trùng default để chắc chắn cấu hình được áp dụng:

~~~java
.withPropertyValues("demo.audit.batch-size=37")
~~~

Sau đó assert `37` thay vì một giá trị có thể cũng là default của code.

## 10. withUserConfiguration và withConfiguration khác nhau

Hai API dễ bị nhầm:

~~~java
.withUserConfiguration(UserProvidedConfiguration.class)
~~~

và:

~~~java
.withConfiguration(
        AutoConfigurations.of(MyAutoConfiguration.class)
)
~~~

Cả hai đều thêm cấu hình vào context runner, nhưng thể hiện **vai trò khác nhau**.

| API | Thường dùng cho |
|---|---|
| `withUserConfiguration(...)` | Những configuration classes do ứng dụng/người dùng cung cấp |
| `withConfiguration(AutoConfigurations.of(...))` | Những auto-configuration classes cần kiểm tra |
| `withBean(...)` | Đăng ký một bean đơn lẻ cho scenario |
| `withInitializer(...)` | Thêm initialization logic cụ thể cho context |
| `withPropertyValues(...)` | Chọn giá trị Environment cho scenario |

Spring Boot auto-configurations có các quy tắc ordering và back-off với user beans. Khi kiểm thử cơ chế này, dùng API phản ánh đúng vai trò sẽ giúp mô phỏng gần với cách auto-configuration được tiêu thụ.

### Ví dụ hai lớp cấu hình

~~~java
contextRunner
        .withUserConfiguration(CustomAuditConfiguration.class)
        .withConfiguration(
                AutoConfigurations.of(AuditAutoConfiguration.class)
        )
        .withPropertyValues("demo.audit.enabled=true")
        .run(context -> {
            assertThat(context).hasSingleBean(AuditSink.class);
        });
~~~

Mục tiêu là kiểm tra khi người dùng đã cung cấp bean, auto-configuration không tạo thêm bean mặc định nếu có `@ConditionalOnMissingBean` phù hợp.

### Runner không tự nạp mọi auto-configuration của ứng dụng

Chỉ khai báo:

~~~java
new ApplicationContextRunner()
~~~

không tương đương với khởi động toàn ứng dụng bằng `@SpringBootApplication`. Cần đưa những auto-configurations muốn kiểm tra vào runner một cách chủ động.

Điều này vừa là lợi ích isolation vừa là giới hạn: một test hẹp có thể pass dù integration toàn ứng dụng còn lỗi vì một cấu hình khác không được đưa vào context.

## 11. Kiểm thử @ConditionalOnMissingBean: back-off

Một thư viện Spring Boot starter tốt thường cung cấp implementation mặc định nhưng để ứng dụng chủ sử dụng bean tùy chỉnh.

Giả sử `AuditAutoConfiguration` đã khai báo:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "demo.audit",
        name = "enabled",
        havingValue = "true"
)
@ConditionalOnMissingBean(AuditSink.class)
AuditSink auditSink() {
    return new ConsoleAuditSink();
}
~~~

Tạo bean tùy chỉnh:

~~~java
public final class InMemoryAuditSink implements AuditSink {

    private final List<String> records = new ArrayList<>();

    @Override
    public void record(String eventName) {
        records.add(eventName);
    }

    public List<String> records() {
        return List.copyOf(records);
    }
}
~~~

Test bằng `withBean`:

~~~java
@Test
void backsOffWhenCustomBeanExists() {
    contextRunner
            .withPropertyValues("demo.audit.enabled=true")
            .withBean(AuditSink.class, InMemoryAuditSink::new)
            .run(context -> {
                assertThat(context).hasSingleBean(AuditSink.class);

                assertThat(context.getBean(AuditSink.class))
                        .isInstanceOf(InMemoryAuditSink.class);
            });
}
~~~

Test này kiểm tra hai điều:

1. Chỉ một bean có kiểu `AuditSink` được dùng.
2. Bean đó là custom implementation, không phải `ConsoleAuditSink` mặc định.

Nếu chỉ kiểm tra bean tồn tại, test không phát hiện trường hợp auto-configuration tạo sai hai bean rồi xảy ra ambiguity ở một service khác.

### Vì sao @ConditionalOnMissingBean cần quan tâm ordering?

Điều kiện `@ConditionalOnMissingBean` đánh giá bean definitions đã được đăng ký tại thời điểm tương ứng. Trong auto-configuration, nó được thiết kế để chạy sau user configuration trong những ngữ cảnh phù hợp.

Nếu tùy tiện đặt condition đó trên user configuration hoặc tổ chức thứ tự xử lý không đúng, kết quả có thể khác mong đợi. `ApplicationContextRunner` với `AutoConfigurations.of(...)` giúp kiểm tra ranh giới này theo đúng mục đích.

### Test cả hướng ngược lại

Đừng chỉ kiểm tra back-off. Cần kiểm tra không có custom bean thì default thực sự được tạo:

~~~java
@Test
void usesDefaultWhenNoCustomBean() {
    contextRunner
            .withPropertyValues("demo.audit.enabled=true")
            .run(context -> {
                assertThat(context).hasSingleBean(AuditSink.class);
                assertThat(context.getBean(AuditSink.class))
                        .isInstanceOf(ConsoleAuditSink.class);
            });
}
~~~

## 12. Đăng ký bean giả mà không cần full mocking infrastructure

`withBean` hữu ích để cấp một collaborator đơn giản cho configuration đang test.

Giả sử một service cần `RemoteClient`:

~~~java
public interface RemoteClient {
    String fetchStatus();
}
~~~

Một implementation dùng cho test:

~~~java
public final class StubRemoteClient implements RemoteClient {

    @Override
    public String fetchStatus() {
        return "OK";
    }
}
~~~

Runner:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(StatusConfiguration.class)
        .withBean(RemoteClient.class, StubRemoteClient::new)
        .run(context -> {
            assertThat(context).hasSingleBean(StatusService.class);
            assertThat(context.getBean(StatusService.class).status())
                    .isEqualTo("OK");
        });
~~~

Nếu chỉ cần kiểm tra wiring và condition, một fake/stub đơn giản thường dễ hiểu hơn thêm Mockito annotations, Spring test mocks hoặc khởi động một remote service.

### Fake không có nghĩa test integration đã hoàn tất

Stub chỉ chứng minh configuration tạo service dùng dependency được cung cấp. Nó không chứng minh HTTP client thật tương thích với endpoint, TLS, timeout hoặc serialization. Những phần đó thuộc một test khác.

## 13. Kiểm thử @ConditionalOnBean

Một auto-configuration có thể chỉ hoạt động khi collaborator đã tồn tại:

~~~java
@AutoConfiguration
public class ReportingAutoConfiguration {

    @Bean
    @ConditionalOnBean(AuditSink.class)
    ReportingService reportingService(AuditSink auditSink) {
        return new ReportingService(auditSink);
    }
}
~~~

Hai scenario:

~~~java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                ReportingAutoConfiguration.class
                        )
                );

@Test
void doesNotCreateReportingServiceWithoutAuditSink() {
    runner.run(context -> {
        assertThat(context).doesNotHaveBean(
                ReportingService.class
        );
    });
}

@Test
void createsReportingServiceWhenAuditSinkExists() {
    runner.withBean(AuditSink.class, InMemoryAuditSink::new)
            .run(context -> {
                assertThat(context).hasSingleBean(
                        ReportingService.class
                );
            });
}
~~~

`ReportingService` là class nghiệp vụ minh họa có constructor nhận `AuditSink`.

### Phụ thuộc vào thứ tự đăng ký definitions

`@ConditionalOnBean` và `@ConditionalOnMissingBean` dựa trên thông tin bean definitions có sẵn tại thời điểm điều kiện được đánh giá. Với các auto-configurations phụ thuộc nhau, có thể cần `@AutoConfiguration(after = ...)` hoặc cấu hình ordering tương ứng.

Nếu test chỉ cung cấp một configuration class nhưng ứng dụng thật có nhiều auto-configurations liên quan, hãy xác định thứ tự nào là một phần của contract và đưa các cấu hình cần thiết vào cùng runner.

## 14. Test nhiều auto-configurations có liên quan

Ví dụ:

~~~java
@AutoConfiguration
public class CoreAuditAutoConfiguration {

    @Bean
    AuditSink auditSink() {
        return new ConsoleAuditSink();
    }
}
~~~

Một cấu hình bổ sung:

~~~java
@AutoConfiguration(after = CoreAuditAutoConfiguration.class)
public class ReportingAutoConfiguration {

    @Bean
    @ConditionalOnBean(AuditSink.class)
    ReportingService reportingService(AuditSink auditSink) {
        return new ReportingService(auditSink);
    }
}
~~~

Runner:

~~~java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(
                        CoreAuditAutoConfiguration.class,
                        ReportingAutoConfiguration.class
                )
        )
        .run(context -> {
            assertThat(context).hasSingleBean(AuditSink.class);
            assertThat(context).hasSingleBean(ReportingService.class);
        });
~~~

Điều này vẫn là **test có phạm vi hẹp**: chỉ hai auto-configuration classes được đưa vào, thay vì toàn bộ ứng dụng.

### Không thử nghiệm ordering bằng cách phụ thuộc tình cờ vào thứ tự khai báo

Nếu auto-configuration B phải chạy sau A, thể hiện điều đó bằng metadata ordering rõ ràng. Test nên xác nhận contract cuối, không dựa vào một thứ tự ngẫu nhiên do reflection/classpath mang lại.

## 15. @ConditionalOnClass và classpath có điều kiện

Một auto-configuration thường chỉ được áp dụng nếu một thư viện tùy chọn tồn tại:

~~~java
@AutoConfiguration
@ConditionalOnClass(OptionalAuditLibrary.class)
public class OptionalAuditAutoConfiguration {

    @Bean
    AuditExtension auditExtension() {
        return new AuditExtension();
    }
}
~~~

Các class `OptionalAuditLibrary` và `AuditExtension` là ví dụ minh họa. Ý nghĩa condition: chỉ áp dụng configuration khi dependency được nhận diện trên classpath tương ứng.

Để kiểm thử khi dependency **có**, class này hiện diện trong test runtime. Nhưng làm sao kiểm tra khi dependency **không có** mà không xóa dependency khỏi toàn bộ dự án?

Spring Boot Test cung cấp `FilteredClassLoader`.

## 16. FilteredClassLoader: mô phỏng thiếu một class

Import:

~~~java
import org.springframework.boot.test.context.FilteredClassLoader;
~~~

Runner:

~~~java
@Test
void doesNotCreateExtensionWhenOptionalLibraryMissing() {
    contextRunner
            .withClassLoader(
                    new FilteredClassLoader(
                            OptionalAuditLibrary.class
                    )
            )
            .run(context -> {
                assertThat(context).doesNotHaveBean(
                        AuditExtension.class
                );
            });
}
~~~

Ví dụ giả định `contextRunner` đã đưa `OptionalAuditAutoConfiguration` vào `AutoConfigurations.of(...)`.

`FilteredClassLoader` cho phép làm cho những class/package được chọn không hiển thị đối với quá trình class loading mà condition sử dụng, từ đó kiểm tra nhánh vắng dependency mà không phải tạo một project build mới.

### Kiểm tra cả nhánh có class

~~~java
@Test
void createsExtensionWhenOptionalLibraryAvailable() {
    contextRunner.run(context -> {
        assertThat(context).hasSingleBean(AuditExtension.class);
    });
}
~~~

Như vậy test xác nhận cả positive path và negative path.

### Chú ý giới hạn của mô phỏng classpath

`FilteredClassLoader` là một công cụ kiểm thử classloading, không phải việc thực sự xóa JAR khỏi ứng dụng đóng gói. Nếu configuration chủ động tham chiếu class tùy chọn trong method signature hoặc static initializer, vẫn có thể gặp lỗi linkage/class resolution trong những tình huống cụ thể.

Một auto-configuration tốt cần tổ chức optional dependency boundaries an toàn, ví dụ cách đặt `@ConditionalOnClass` ở configuration class phù hợp thay vì để những kiểu không hiện diện bị JVM bắt buộc giải quyết quá sớm.

## 17. Khi thiếu class, cấu hình nên không tạo bean hay phải fail?

Hai kiểu contract khác nhau:

**Optional integration:**

~~~text
Optional library absent
        |
        v
Do not register integration bean
        |
        v
Application can still start
~~~

**Required dependency:**

~~~text
Required collaborator absent
        |
        v
Service cannot be constructed
        |
        v
Context startup fails with clear cause
~~~

`ApplicationContextRunner` có thể kiểm thử cả hai.

Không nên dùng `@ConditionalOnClass` để âm thầm bỏ qua một chức năng **bắt buộc** nhưng rồi ứng dụng vẫn trả kết quả thành công sai. Phải quyết định dependency nào là optional, dependency nào là required.

## 18. Kiểm thử context startup failure có chủ đích

Một cấu hình có dependency bắt buộc:

~~~java
@Configuration(proxyBeanMethods = false)
class BrokenReportingConfiguration {

    @Bean
    ReportingService reportingService(
            AuditSink auditSink
    ) {
        return new ReportingService(auditSink);
    }
}
~~~

Nếu không có `AuditSink`, Spring không thể tạo bean từ method này.

Test:

~~~java
@Test
void failsWhenRequiredAuditSinkMissing() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    BrokenReportingConfiguration.class
            )
            .run(context -> {
                assertThat(context).hasFailed();

                assertThat(context.getStartupFailure())
                        .hasRootCauseInstanceOf(
                                NoSuchBeanDefinitionException.class
                        );
            });
}
~~~

Runner cho phép callback vẫn quan sát được **startup failure**. Nếu dùng một Spring Test context thông thường mà setup thất bại, test framework có thể dừng trước khi phương thức test chạy; kiểm tra thông tin thất bại có chủ đích sẽ khó hơn.

### Khi nào test failure là hợp lý?

- Configuration yêu cầu một collaborator nhưng không được cung cấp.
- Property bắt buộc thiếu và application phải fail fast.
- Hai bean xung đột tên/kiểu theo chính sách không cho phép.
- Constructor/configuration properties có validation thất bại.
- Thư viện tùy chọn bị cấu hình sai mà hệ thống phải phát hiện sớm.

Đừng viết test mong fail cho một tình huống đáng ra auto-configuration phải back off. Trước hết hãy xác định contract của cấu hình.

### Không assert quá chặt nguyên văn exception message

Exception message có thể thay đổi theo phiên bản Spring hoặc Java. Nếu không cần chứng minh một thông điệp cụ thể của ứng dụng, thường nên assert loại lỗi, root cause hoặc thành phần lỗi có ý nghĩa thay vì toàn bộ chuỗi message.

## 19. Kiểm thử @ConfigurationProperties trong context nhỏ

Nhiều auto-configurations dùng typed properties thay vì đọc `Environment` trực tiếp.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "demo.audit")
public class AuditProperties {

    private boolean enabled;
    private int batchSize = 100;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }
}
~~~

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(AuditProperties.class)
class AuditPropertiesConfiguration {
}
~~~

Test:

~~~java
@Test
void bindsAuditProperties() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    AuditPropertiesConfiguration.class
            )
            .withPropertyValues(
                    "demo.audit.enabled=true",
                    "demo.audit.batch-size=37"
            )
            .run(context -> {
                assertThat(context).hasSingleBean(
                        AuditProperties.class
                );

                AuditProperties props =
                        context.getBean(AuditProperties.class);

                assertThat(props.isEnabled()).isTrue();
                assertThat(props.getBatchSize()).isEqualTo(37);
            });
}
~~~

### Binder không hoạt động chỉ vì class có annotation

`@ConfigurationProperties` mô tả cách bind, nhưng class phải được đăng ký theo cơ chế phù hợp, ví dụ `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan`. Với context nhỏ, nên đăng ký tường minh những thành phần cần thiết.

### Test default values

Thêm test không đặt `demo.audit.batch-size`:

~~~java
@Test
void usesDefaultBatchSize() {
    runner.run(context -> {
        AuditProperties properties =
                context.getBean(AuditProperties.class);

        assertThat(properties.getBatchSize())
                .isEqualTo(100);
    });
}
~~~

`runner` ở ví dụ được hiểu là một `ApplicationContextRunner` đã đăng ký `AuditPropertiesConfiguration`.

Các default values là một phần quan trọng của contract. Nếu thiếu property nhưng startup vẫn thành công với giá trị không mong muốn, test chỉ kiểm tra “bean tồn tại” sẽ bỏ sót lỗi.

## 20. Kiểm thử invalid configuration properties

Có thể đặt Bean Validation constraints cho properties:

~~~java
@ConfigurationProperties(prefix = "demo.client")
@Validated
public class ClientProperties {

    @Min(1)
    private int poolSize = 4;

    public int getPoolSize() {
        return poolSize;
    }

    public void setPoolSize(int poolSize) {
        this.poolSize = poolSize;
    }
}
~~~

Khi có provider Bean Validation và cơ chế binding/validation phù hợp, `pool-size=0` phải vi phạm ràng buộc.

Runner:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(
                ClientPropertiesConfiguration.class
        )
        .withPropertyValues("demo.client.pool-size=0")
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                    .isNotNull();
        });
~~~

Ví dụ giả định `ClientPropertiesConfiguration` dùng `@EnableConfigurationProperties(ClientProperties.class)` và test runtime có `spring-boot-starter-validation` hoặc Bean Validation provider tương ứng.

### Vì sao cần nói rõ provider?

Nếu test classpath không có validation implementation, behavior có thể khác với môi trường production. Một test negative validation chỉ có giá trị khi infrastructure thực sự tương ứng với thứ bạn muốn bảo vệ.

### Phân biệt lỗi binding và lỗi constraint

- `demo.client.pool-size=abc` có thể gây lỗi chuyển đổi string sang integer.
- `demo.client.pool-size=0` chuyển đổi được sang số nhưng vi phạm `@Min(1)`.
- Thiếu `pool-size` có thể dùng default `4`.

Ba nhánh này nên được kiểm thử riêng nếu chúng là contract cấu hình quan trọng.

## 21. Test @ConditionalOnSingleCandidate và @Primary

Một auto-configuration có thể cần đúng một candidate để inject theo kiểu:

~~~java
@AutoConfiguration
public class MailReportAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(MailSender.class)
    MailReportService mailReportService(
            MailSender mailSender
    ) {
        return new MailReportService(mailSender);
    }
}
~~~

`MailSender` và `MailReportService` là những kiểu minh họa.

Các scenario cần nghĩ tới:

| Context có | Kỳ vọng thường gặp |
|---|---|
| Không có `MailSender` | Không có `MailReportService` |
| Một `MailSender` | Có `MailReportService` |
| Hai `MailSender`, không có lựa chọn ưu tiên | Condition có thể không match |
| Hai `MailSender`, một bean là primary | Có thể có một candidate duy nhất theo semantics condition |

Có thể dùng `withBean` hoặc `withUserConfiguration` để đăng ký từng scenario.

### Vì sao kiểm thử ambiguity?

Nếu auto-configuration tạo một bean bằng constructor nhận một interface nhưng ứng dụng cung cấp hai implementations, context có thể lỗi hoặc có hành vi không mong muốn. Test hẹp giúp phát hiện ranh giới này trước khi thư viện được tích hợp vào ứng dụng lớn.

## 22. @ConditionalOnMissingBean kiểm tra theo type, name hay annotation?

`@ConditionalOnMissingBean` có nhiều cách xác định bean cần vắng mặt. Ví dụ theo type:

~~~java
@ConditionalOnMissingBean(AuditSink.class)
~~~

hoặc theo bean name khi contract thật sự định nghĩa bằng tên:

~~~java
@ConditionalOnMissingBean(name = "defaultAuditSink")
~~~

Hai điều kiện không tương đương.

Ví dụ có một custom `AuditSink` tên `customAuditSink`:

- Condition theo **type** có thể nhận ra bean đã tồn tại và back off.
- Condition theo **name** `defaultAuditSink` vẫn có thể match nếu không có bean tên đó, dẫn tới tạo thêm `AuditSink`.

Khi test, chọn scenario phản ánh API extension point thật của starter: thư viện hứa “người dùng có thể override bằng một bean kiểu AuditSink” hay “phải đặt bean đúng tên”?

### Đừng assert chỉ theo bean name nếu contract là theo type

~~~java
assertThat(context).hasSingleBean(AuditSink.class);
~~~

thường có ý nghĩa tốt hơn:

~~~java
assertThat(context).hasBean("auditSink");
~~~

nếu library cho phép người dùng khai báo tên bất kỳ.

Ngược lại, khi name là contract (ví dụ một integration tìm bean theo tên cố định), kiểm tra tên cụ thể là hợp lý.

## 23. Dùng ConditionEvaluationReport để giải thích điều kiện

Khi một auto-configuration không match, kết quả “bean không có” có thể là đúng hoặc sai. Để điều tra, Spring Boot có **condition evaluation report** ghi lại một số kết quả đánh giá conditions.

Một cách bật log condition report trong test là dùng initializer phù hợp:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withInitializer(
                        ConditionEvaluationReportLoggingListener
                                .forLogLevel(LogLevel.INFO)
                )
                .withConfiguration(
                        AutoConfigurations.of(
                                AuditAutoConfiguration.class
                        )
                );
~~~

Ví dụ sử dụng những kiểu `ConditionEvaluationReportLoggingListener` và `LogLevel` thuộc Spring Boot. Khi chạy, thông tin đánh giá điều kiện có thể xuất hiện ở logging output của test tùy logging configuration.

### Report giúp trả lời điều gì?

Một condition report có thể giúp xác định:

- Auto-configuration nào có match?
- `@ConditionalOnClass` có tìm thấy dependency không?
- `@ConditionalOnProperty` nhận giá trị property nào?
- `@ConditionalOnBean` có thấy collaborator không?
- Vì sao một nhánh bị loại khỏi bean registration?

Nếu muốn kiểm tra report theo chương trình, có API `ConditionEvaluationReport`. Tuy nhiên, đừng biến test thành assertion phụ thuộc quá chặt vào wording nội bộ của report. Khi mục tiêu là contract, vẫn nên assert bean existence/absence hoặc startup failure.

### Report không tự sửa lỗi

Nếu condition report cho thấy bean không được tạo vì thiếu class, cần quyết định đó là hành vi expected của optional integration hay dependency project bị cấu hình sai.

## 24. Kiểm thử custom @Conditional

Đôi khi dự án có một condition tùy chỉnh:

~~~java
public class LocalModeCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        String mode = context.getEnvironment()
                .getProperty("demo.processing.mode", "remote");

        return "local".equals(mode);
    }
}
~~~

Cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
public class LocalProcessingConfiguration {

    @Bean
    @Conditional(LocalModeCondition.class)
    ProcessingClient localClient() {
        return new LocalProcessingClient();
    }
}
~~~

Runner:

~~~java
@Test
void enablesLocalClientForLocalMode() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    LocalProcessingConfiguration.class
            )
            .withPropertyValues(
                    "demo.processing.mode=local"
            )
            .run(context -> {
                assertThat(context).hasSingleBean(
                        ProcessingClient.class
                );
            });
}
~~~

Negative scenario:

~~~java
@Test
void omitsLocalClientForRemoteMode() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    LocalProcessingConfiguration.class
            )
            .withPropertyValues(
                    "demo.processing.mode=remote"
            )
            .run(context -> {
                assertThat(context).doesNotHaveBean(
                        ProcessingClient.class
                );
            });
}
~~~

### Đừng biến Condition thành nơi thực hiện nghiệp vụ

`Condition.matches(...)` được Spring gọi trong quá trình đăng ký cấu hình. Nó nên quyết định cấu hình dựa trên metadata và Environment một cách tương đối rẻ, không nên gọi API bên ngoài, ghi database hoặc tạo side effects khó kiểm soát.

Một test hẹp có thể phát hiện sai logic điều kiện, nhưng không sửa được những vấn đề kiến trúc nếu condition thực hiện quá nhiều công việc.

## 25. Kiểm thử @Profile bằng ApplicationContextRunner

`@Profile` là một condition khác của Spring:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("dev")
public class DeveloperToolsConfiguration {

    @Bean
    DeveloperTools developerTools() {
        return new DeveloperTools();
    }
}
~~~

Nếu chỉ cần kiểm tra property-based condition, `withPropertyValues` thường đủ. Với `@Profile`, phải phân biệt việc đặt một property trong Environment với **chủ động kích hoạt profiles trong context**.

Một cách rõ ràng là thiết lập active profile qua initializer:

~~~java
new ApplicationContextRunner()
        .withInitializer(context ->
                context.getEnvironment()
                        .setActiveProfiles("dev")
        )
        .withUserConfiguration(
                DeveloperToolsConfiguration.class
        )
        .run(context -> {
            assertThat(context).hasSingleBean(
                    DeveloperTools.class
            );
        });
~~~

Việc thiết lập profile phải diễn ra trước khi configuration class được đánh giá. `withInitializer` được dùng để chuẩn bị Environment trong giai đoạn context initialization.

### Không giả định withPropertyValues tự thực hiện toàn bộ SpringApplication bootstrap

Test runner tạo một context hẹp, không mô phỏng toàn bộ quá trình Config Data và profile activation của `SpringApplication.run`. Nếu test thật sự cần hiểu `application-dev.yml` được nạp theo precedence, `spring.config.import` hoặc profile groups được mở rộng ra sao, nên chọn test scope tương ứng với SpringApplication bootstrap.

### Test default profile riêng

Nếu không có active profile, Spring Environment sử dụng default profiles khi đánh giá conditions. Có thể đặt default profile qua initializer và kiểm tra `@Profile("local")`. Hãy phân biệt `getActiveProfiles()` và `getDefaultProfiles()` khi khẳng định kết quả.

## 26. Dùng ApplicationContextInitializer khi cần custom Environment

`withInitializer(...)` cho phép đưa một `ApplicationContextInitializer` vào quy trình dựng context.

Ví dụ:

~~~java
new ApplicationContextRunner()
        .withInitializer(context -> {
            context.getEnvironment()
                    .setActiveProfiles("local");

            context.getEnvironment()
                    .setDefaultProfiles("default");
        })
        .withUserConfiguration(
                LocalOnlyConfiguration.class
        )
        .run(context -> {
            assertThat(context).hasSingleBean(
                    LocalService.class
            );
        });
~~~

Ở ví dụ, `LocalOnlyConfiguration` đăng ký `LocalService` khi `local` active.

Có thể dùng initializer cho:

- Thêm custom property sources.
- Thiết lập active/default profiles.
- Đăng ký bean factory settings.
- Chuẩn bị một phần environment đặc biệt mà condition cần đọc.
- Gắn condition evaluation logging listener.

Không nên đưa cả quá trình bootstrap production vào initializer chỉ để test một condition đơn giản. Nếu test setup phức tạp hơn chính configuration đang được kiểm tra, có thể scope đã chọn chưa phù hợp.

## 27. Kiểm thử @ConditionalOnResource

Một số auto-configuration chỉ hoạt động khi một classpath resource tồn tại:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(
        resources = "classpath:demo/schema.json"
)
public class SchemaSupportConfiguration {

    @Bean
    SchemaSupport schemaSupport() {
        return new SchemaSupport();
    }
}
~~~

Một context runner có thể dùng cùng configuration để kiểm tra behavior trong test classpath có/không có resource phù hợp.

Với trường hợp cần mô phỏng resource vắng mặt mà không thay project structure, có thể chọn một test classloader hoặc test fixture arrangement có kiểm soát, tùy khả năng của phiên bản Spring Boot Test đang sử dụng.

### Điều quan trọng

- `classpath:demo/schema.json` khác với đường dẫn filesystem tùy ý.
- File phải có trong classpath mà context runner thật sự nhìn thấy.
- Một resource còn nằm trong `src/test/resources` có thể hiện diện ở test runtime nhưng không có trong production artifact.
- Không nên dùng test pass với resource test-only để chứng minh production image đóng gói đúng file.

Đối với artifact packaging/resource inclusion, cần kiểm thử chính JAR/image được phát hành.

## 28. Test auto-configuration cần chốt đúng điều kiện thiếu dependency

Hãy hình dung một starter optional integration:

~~~text
AuditClient on classpath?
        |
   +----+----+
   |         |
  Không      Có
   |         |
   v         v
No audit     demo.audit.enabled?
bean             |
             +---+---+
             |       |
            No      Yes
             |       |
             v       v
          No bean   Custom AuditSink exists?
                         |
                    +----+----+
                    |         |
                   Yes        No
                    |         |
                    v         v
                 Back off   Create default
~~~

Một bộ test có ý nghĩa cần chạm đến những nhánh này:

1. Dependency không có.
2. Dependency có nhưng feature tắt.
3. Dependency có và feature bật.
4. Feature bật và bean tùy chỉnh tồn tại.

Không nhất thiết kiểm tra mọi tổ hợp property khác nếu chúng không tạo thêm behavior có ý nghĩa. Nhưng **mỗi quyết định conditional chính** cần ít nhất một test chứng minh nhánh quan trọng.

## 29. Kiểm thử bean alias/name và @Primary khi cần

Một số cấu hình tạo nhiều beans cùng interface:

~~~java
@Configuration(proxyBeanMethods = false)
class GatewayConfiguration {

    @Bean
    @Primary
    Gateway primaryGateway() {
        return new MainGateway();
    }

    @Bean
    Gateway backupGateway() {
        return new BackupGateway();
    }
}
~~~

Runner:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(GatewayConfiguration.class)
        .run(context -> {
            assertThat(context).hasBean("primaryGateway");
            assertThat(context).hasBean("backupGateway");

            assertThat(context.getBean(Gateway.class))
                    .isInstanceOf(MainGateway.class);
        });
~~~

Ví dụ các kiểu `Gateway`, `MainGateway`, `BackupGateway` là thành phần minh họa.

`hasSingleBean(Gateway.class)` **không phù hợp** ở đây vì context có hai beans kiểu `Gateway`. Test cần phản ánh đúng contract: có hai beans nhưng một bean `@Primary` được ưu tiên khi inject theo type.

### Không nên test mọi implementation detail

Nếu thư viện công khai contract “có một Gateway dùng được”, việc assert tên bean nội bộ có thể làm test mong manh khi refactor. Nhưng nếu một bean name là extension point người dùng dựa vào, đó lại là một phần contract đáng kiểm tra.

## 30. ApplicationContextRunner và vòng đời của beans

Runner không chỉ xử lý bean definitions; nó còn refresh và đóng context nên những lifecycle callbacks có thể chạy.

Ví dụ:

~~~java
public final class ManagedClient implements AutoCloseable {

    private boolean closed;

    public boolean isClosed() {
        return closed;
    }

    @Override
    public void close() {
        closed = true;
    }
}
~~~

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
class ManagedClientConfiguration {

    @Bean(destroyMethod = "close")
    ManagedClient managedClient() {
        return new ManagedClient();
    }
}
~~~

Trong callback, bean chưa bị đóng bởi teardown:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(
                ManagedClientConfiguration.class
        )
        .run(context -> {
            ManagedClient client =
                    context.getBean(ManagedClient.class);

            assertThat(client.isClosed()).isFalse();
        });
~~~

Sau callback, runner sẽ đóng context theo lifecycle test. Nếu cần kiểm tra một destruction callback, có thể ghi state vào một object bên ngoài context theo cách kiểm soát được; không nên truy cập một bean đã đóng để làm công việc nghiệp vụ.

### Tránh resource leaks trong cấu hình test

Một configuration class vô tình tạo thread pool không được shutdown hoặc client giữ socket có thể khiến test suite không thoát hoặc ảnh hưởng test khác. Kiểm thử config hẹp giúp nhìn rõ lifecycle ownership, nhưng vẫn cần `destroyMethod`, `@PreDestroy` hoặc resource cleanup đúng.

## 31. Test một failure scenario mà không cần chạy toàn bộ ứng dụng

Một lợi ích đáng kể là kiểm tra đường lỗi có chủ đích. Ví dụ cấu hình yêu cầu property bắt buộc:

~~~java
@Configuration(proxyBeanMethods = false)
class RequiredEndpointConfiguration {

    @Bean
    EndpointClient endpointClient(Environment environment) {
        String url = environment.getRequiredProperty(
                "demo.client.url"
        );
        return new EndpointClient(url);
    }
}
~~~

Test khi thiếu property:

~~~java
@Test
void failsWhenUrlMissing() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    RequiredEndpointConfiguration.class
            )
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .isNotNull();
            });
}
~~~

Test khi property tồn tại:

~~~java
@Test
void createsClientWhenUrlProvided() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    RequiredEndpointConfiguration.class
            )
            .withPropertyValues(
                    "demo.client.url=https://example.test"
            )
            .run(context -> {
                assertThat(context).hasSingleBean(
                        EndpointClient.class
                );
            });
}
~~~

`EndpointClient` là type giả định có constructor nhận URL string; ví dụ chỉ kiểm tra bean construction, không gọi mạng.

### Không dùng một URL thật để test cấu hình

Một test chỉ cần kiểm tra property binding và bean creation nên dùng URL giả hợp lệ hoặc fake client. Nếu test vô tình gọi endpoint thật, nó sẽ chậm, flaky và phụ thuộc môi trường ngoài mà không chứng minh thêm điều kiện đang kiểm tra.

## 32. Runner và ApplicationContext type

`ApplicationContextRunner` phù hợp với **non-web application context** hoặc các configuration concerns không cần mô phỏng web infrastructure.

Spring Boot Test còn có các runner khác cho trường hợp cần web context:

- `WebApplicationContextRunner` cho một số kịch bản servlet web context.
- `ReactiveWebApplicationContextRunner` cho kịch bản reactive web context tương ứng.

Chọn runner đúng khi điều kiện phụ thuộc loại ứng dụng web:

~~~java
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET
)
~~~

hoặc:

~~~java
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.REACTIVE
)
~~~

Nếu dùng `ApplicationContextRunner` không-web để kiểm tra một condition chỉ match servlet web application, kết quả không match là **đúng theo loại context**, không phải lỗi condition.

### Runner web không thay thế full HTTP integration test

`WebApplicationContextRunner` tạo loại context phù hợp để kiểm tra web-related bean configuration. Nó không mặc nhiên là một request-level test có server thật, TLS, reverse proxy hoặc đầy đủ security filter chain.

Khi cần gửi HTTP request thật và kiểm tra response, hãy dùng công cụ kiểm thử web tương ứng như MockMvc/WebTestClient hoặc test với server, tùy phạm vi.

## 33. ApplicationContextRunner và auto-configuration imports

Một auto-configuration trong Spring Boot có thể được đăng ký để ứng dụng tiêu thụ qua cơ chế auto-configuration imports. Trong các thế hệ Spring Boot hiện đại, metadata thường nằm trong:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

File đó liệt kê fully qualified names của những auto-configuration classes.

Khi dùng runner:

~~~java
.withConfiguration(
        AutoConfigurations.of(MyAutoConfiguration.class)
)
~~~

test có thể đưa trực tiếp auto-configuration vào context. Điều này rất hữu ích để kiểm tra nội dung auto-configuration, nhưng **không tự chứng minh rằng packaging metadata đã đăng ký class đúng trong JAR**.

### Hai câu hỏi phải test ở hai lớp

1. “Nếu auto-configuration được nạp, conditions và beans có đúng không?” → `ApplicationContextRunner` rất phù hợp.
2. “Khi thư viện này được đưa vào ứng dụng thật, auto-configuration có được discover qua imports metadata không?” → cần kiểm thử packaging/auto-configuration import ở mức integration phù hợp.

Một starter có thể có auto-configuration class hoàn toàn đúng nhưng quên đưa tên class vào imports file; runner test trực tiếp class vẫn pass. Vì thế không nên dùng runner test để kết luận toàn bộ starter packaging đã đúng.

## 34. ApplicationContextRunner không tự đọc application.yml đầy đủ

Một nhầm lẫn thường gặp: vì runner dùng Spring Boot Test nên nó sẽ tự nạp mọi `application.yml`, `application-dev.yml` và `spring.config.import` như `SpringApplication.run`.

Runner được thiết kế cho **context hẹp**. Khi bạn dùng:

~~~java
new ApplicationContextRunner()
        .withPropertyValues("demo.mode=test")
~~~

bạn chủ động cung cấp property trong context. Nó không mặc nhiên chạy toàn bộ Config Data bootstrap giống production.

Nếu test cần xác nhận:

- `spring.config.import` có nạp đúng file bên ngoài không.
- Profile-specific files được merge/override như mong đợi không.
- Command-line/environment precedence của `SpringApplication` đúng không.
- Configuration tree secrets có được đọc khi bootstrap không.

thì cần một test phù hợp với **SpringApplication/Config Data loading** hoặc integration test phạm vi rộng hơn.

### Scope hẹp là ưu điểm, không phải hạn chế vô nghĩa

Việc không nạp toàn bộ config từ dự án giúp test deterministic hơn, tránh để kết quả phụ thuộc vào một file development mà người viết test không hề chủ động chọn.

## 35. Chú ý khi condition phụ thuộc web, database hoặc service ngoài

Một conditional configuration có thể kiểm tra classpath hoặc properties, nhưng bean được tạo bên trong lại khởi tạo connection pool, gọi network hoặc mở thread.

Nếu mục tiêu chỉ là xác nhận condition, nên:

- Tách creation logic khỏi remote connection side effects.
- Cung cấp fake collaborators bằng `withBean`.
- Cấu hình bean creation an toàn cho test.
- Tránh để conditional bean constructor thực hiện công việc tốn kém.
- Không đưa cả DataSource và JPA stack vào test nếu điều kiện không cần chúng.

Nếu cần kiểm tra DataSource thực sự hoạt động, đó là bài toán integration test khác với condition test hẹp.

### Test hẹp không bảo đảm hiệu năng production

Một context có ba bean khởi động nhanh không chứng minh ứng dụng thật với hàng trăm beans cũng khởi động nhanh. Runner có thể đo hành vi local của configuration, nhưng không phải benchmark đầy đủ startup time.

## 36. Một test matrix thực dụng cho auto-configuration

Giả sử một thư viện Spring Boot starter có các điều kiện:

~~~text
demo.audit.enabled=true
          AND
AuditClient class exists
          AND
No user-defined AuditSink
          |
          v
Register ConsoleAuditSink
~~~

Bảng kiểm thử:

| Scenario | Property enabled | Optional class | Custom bean | Kỳ vọng |
|---|---|---|---|---|
| A | Không | Có | Không | Không tạo sink |
| B | Có | Có | Không | Tạo default sink |
| C | Có | Không | Không | Không tạo default sink |
| D | Có | Có | Có | Dùng custom sink, không tạo default |
| E | Missing | Có | Không | Theo default của property condition |
| F | Có | Có | Có hai custom beans | Kiểm tra contract ambiguity nếu cần |

Mỗi scenario nên tự mô tả điều kiện và assertion:

~~~java
@Test
void createsDefaultWhenEnabledAndDependencyAvailable() {
    runner.withPropertyValues("demo.audit.enabled=true")
            .run(context -> {
                assertThat(context).hasSingleBean(AuditSink.class);
            });
}
~~~

Đặt tên test phản ánh **nguyên nhân** chứ không chỉ kết quả như `test1`, `test2`.

### Test cả nhánh âm giúp phát hiện condition quá rộng

Nếu chỉ test B, một auto-configuration luôn tạo bean kể cả khi property false vẫn có thể pass. Các nhánh A, C và E làm rõ giới hạn của condition.

## 37. Những lỗi thường gặp khi dùng ApplicationContextRunner

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Bean không được tạo | Chưa đưa configuration class vào runner | Dùng `withUserConfiguration` hoặc `withConfiguration` |
| Property condition không match | Sai key/value hoặc thiếu default semantics | Kiểm tra `withPropertyValues` và `havingValue` |
| Context có nhiều bean ngoài ý muốn | Custom bean không làm auto-config back off | Kiểm tra `@ConditionalOnMissingBean` và ordering |
| Context fails vì thiếu collaborator | Chưa đăng ký required bean | Dùng `withBean` hoặc sửa contract config |
| Test vắng class không hoạt động | Classloader không được lọc đúng | Dùng `FilteredClassLoader`, kiểm tra class thật |
| Test pass nhưng starter không tự nạp trong app | Thiếu auto-configuration imports metadata | Kiểm thử packaging/discovery |
| Test pass nhưng ứng dụng thật lỗi | Test scope thiếu cấu hình tương tác | Thêm integration test phù hợp |
| `@Profile` không match | Chỉ đặt property, không kích hoạt profile trong context | Dùng initializer thiết lập profile |
| `@ConfigurationProperties` không được bind | Chưa đăng ký properties type/binder | Dùng `@EnableConfigurationProperties` phù hợp |
| Negative validation không fail | Không có Bean Validation provider | Kiểm tra test dependencies và infrastructure |
| Lỗi assertion sau callback | Bean/context đã đóng | Đặt assertion bên trong `run` |
| Web condition không match | Dùng runner không-web | Chọn `WebApplicationContextRunner` hoặc reactive tương ứng |
| Test bắt exception rồi mất nguyên nhân | Assert message quá chung hoặc catch nhầm | Kiểm tra `getStartupFailure()` |
| Failure test không tới callback trong test rộng | Framework startup fail trước test method | Dùng runner để kiểm tra lỗi có chủ đích |
| Điều kiện phụ thuộc thứ tự | Auto-config ordering sai | Khai báo ordering và test các cấu hình liên quan |
| Test quá chậm | Tạo bean hạ tầng ngoài scope | Giảm configuration và dùng fake dependency |

### Đầu tiên hãy hỏi: bạn đang thử điều gì?

Nếu đang thử “bean có được đăng ký khi một property bật?”, đừng tạo database thật. Nếu đang thử “cấu hình database kết nối được?”, runner nhỏ không đủ. Ranh giới của test phải nhất quán với câu hỏi cần chứng minh.

## 38. Điều nên tránh: biến runner thành full application test

Một anti-pattern:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(
                StoreApplication.class,
                SecurityConfiguration.class,
                JpaConfiguration.class,
                WebConfiguration.class,
                MessagingConfiguration.class,
                SchedulerConfiguration.class
        )
        .run(context -> {
            assertThat(context).hasSingleBean(MyFeature.class);
        });
~~~

Nếu `StoreApplication` chứa `@SpringBootApplication`, component scan và auto-configuration rộng có thể được kích hoạt, làm mất lợi thế isolation. Khi dùng quá nhiều configuration classes, test trở nên chậm và khó hiểu.

**Cách sửa:** tạo một configuration nhỏ hoặc auto-configuration class đúng phạm vi, thêm fake dependencies, và kiểm tra bean mục tiêu.

Nếu thật sự cần toàn bộ ứng dụng, dùng `@SpringBootTest` sẽ truyền đạt ý định rõ hơn.

## 39. Điều nên tránh: dùng runner để kiểm tra business logic thuần

Nếu service chỉ có một phương thức tính giá và không phụ thuộc Spring configuration:

~~~java
public final class DiscountCalculator {

    public BigDecimal apply(
            BigDecimal amount,
            BigDecimal discount
    ) {
        return amount.subtract(discount);
    }
}
~~~

thì test thuần Java đơn giản hơn:

~~~java
@Test
void subtractsDiscount() {
    DiscountCalculator calculator =
            new DiscountCalculator();

    assertThat(
            calculator.apply(
                    new BigDecimal("100"),
                    new BigDecimal("15")
            )
    ).isEqualByComparingTo("85");
}
~~~

Không cần khởi tạo `ApplicationContextRunner` chỉ để gọi một method không phụ thuộc DI/conditional configuration.

## 40. Điều nên tránh: test implementation details quá mức

Một test cấu hình có thể trở nên mong manh khi assert:

- Tên bean nội bộ không phải public contract.
- Thứ tự registration không ảnh hưởng behavior.
- Toàn bộ exception message của Spring Framework.
- Class name của proxy thay vì kiểu/behavior của bean.
- Số lượng mọi bean trong context thay vì bean liên quan.
- Dòng log chính xác khi condition report được in ra.

Thay vào đó, tập trung vào những điều ứng dụng chủ hoặc module khác thực sự dựa vào:

- Có bean đúng interface khi điều kiện bật.
- Không tạo default khi user đã override.
- Chọn bean đúng khi có nhiều candidates.
- Fail fast khi cấu hình bắt buộc thiếu.
- Property được bind đúng kiểu/default.
- Không tải integration khi optional dependency vắng.

### Một test có thể là tài liệu cho starter

Nếu các tên test và assertions thể hiện những contract trên, chúng cũng giúp người dùng starter hiểu cách tùy chỉnh library mà không phải đọc toàn bộ mã auto-configuration.

## 41. Một ví dụ đầy đủ: mini starter có nhiều điều kiện

Bài toán: một module cung cấp audit sink mặc định chỉ khi:

1. Property `demo.audit.enabled=true`.
2. Không có custom `AuditSink`.

Định nghĩa:

~~~java
public interface AuditSink {
    void record(String action);
}
~~~

~~~java
public final class ConsoleAuditSink implements AuditSink {

    @Override
    public void record(String action) {
        System.out.println("AUDIT: " + action);
    }
}
~~~

Auto-configuration:

~~~java
@AutoConfiguration
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.audit",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    @ConditionalOnMissingBean(AuditSink.class)
    AuditSink auditSink() {
        return new ConsoleAuditSink();
    }
}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AuditAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AuditAutoConfiguration.class
                            )
                    );

    @Test
    void enabledCreatesDefaultBean() {
        runner.withPropertyValues("demo.audit.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(AuditSink.class);

                    assertThat(context.getBean(AuditSink.class))
                            .isInstanceOf(ConsoleAuditSink.class);
                });
    }

    @Test
    void disabledDoesNotCreateBean() {
        runner.withPropertyValues("demo.audit.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(AuditSink.class);
                });
    }

    @Test
    void missingPropertyDoesNotCreateBean() {
        runner.run(context -> {
            assertThat(context)
                    .doesNotHaveBean(AuditSink.class);
        });
    }

    @Test
    void customBeanOverridesDefault() {
        runner.withPropertyValues("demo.audit.enabled=true")
                .withBean(
                        AuditSink.class,
                        InMemoryAuditSink::new
                )
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(AuditSink.class);

                    assertThat(context.getBean(AuditSink.class))
                            .isInstanceOf(InMemoryAuditSink.class);
                });
    }
}
~~~

`InMemoryAuditSink` là test implementation đã giới thiệu trước đó.

Bốn test thể hiện đầy đủ contract cơ bản:

- Bật: có default.
- Tắt: không có default.
- Thiếu property: không có default.
- Có custom bean: auto-configuration không tạo thêm bean.

Nếu thư viện còn `@ConditionalOnClass`, thêm một test `FilteredClassLoader` cho nhánh thiếu dependency. Nếu cấu hình có binding properties, thêm test giá trị mặc định và invalid values.

### Vì sao ví dụ này đủ hẹp?

Không có REST controller, DataSource, security filter, JPA repository hoặc external service. Test chỉ tạo những bean ảnh hưởng đến audit configuration. Nếu một test thất bại, người bảo trì có thể tập trung vào hai conditions thay vì xem toàn bộ bootstrap logs của ứng dụng.

## 42. Test naming và cách tổ chức trong project

Một cấu trúc thường gặp:

~~~text
src/
├── main/
│   └── java/com/example/audit/
│       ├── AuditAutoConfiguration.java
│       ├── AuditSink.java
│       └── ConsoleAuditSink.java
└── test/
    └── java/com/example/audit/
        └── AuditAutoConfigurationTests.java
~~~

Nếu module là một Spring Boot starter, có thể tách auto-configuration module và starter module. Nhưng điều đó không làm thay đổi nguyên lý test: kiểm tra đúng configuration class, bean contract và các điều kiện môi trường/classpath.

Đặt tên test rõ:

~~~text
enabledCreatesDefaultBean
disabledDoesNotCreateBean
missingPropertyDoesNotCreateBean
customBeanOverridesDefault
missingOptionalLibraryDisablesIntegration
invalidPoolSizeFailsStartup
~~~

Tên test phản ánh behavior trong điều kiện cụ thể, giúp người bảo trì hiểu mục tiêu ngay khi đọc báo cáo test.

### Không gom mọi điều kiện vào một callback

Một callback khổng lồ không tự làm test tốt hơn:

~~~java
runner.run(context -> {
    // Hai mươi assertions cho nhiều feature không liên quan...
});
~~~

Nếu các conditions độc lập, tách scenario giúp failure chỉ rõ nhánh điều kiện sai và giảm công điều tra.

## 43. Khi nào cần mở rộng test lên integration level?

Sau khi một auto-configuration được kiểm thử qua runner, vẫn có những khoảng trống:

- Cấu hình có thực sự được discover từ imports metadata không?
- Nó có xung đột với auto-configurations khác trong application không?
- Bean tương tác với DataSource thật đúng không?
- Security/filter chain đúng khi chạy web server không?
- App có nạp được profile/config files production-like không?
- Container image hoặc native executable có chạy đúng không?
- API request/response có đáp ứng contract bên ngoài không?

Các câu hỏi này không được trả lời chỉ bởi `ApplicationContextRunner`.

Một chiến lược cân bằng:

~~~text
Unit tests (logic Java)
         |
         v
ApplicationContextRunner tests
  (conditions, bean wiring, property binding)
         |
         v
Focused integration tests
  (DB, web, messaging)
         |
         v
Full application / artifact smoke tests
         |
         v
Runtime deployment checks
~~~

Mỗi tầng có mục tiêu và chi phí riêng. Dùng runner để giảm rủi ro cấu hình sớm, chứ không dùng nó để loại bỏ những kiểm thử cần thiết ở tầng trên.

## 44. Một checklist thiết kế bài test hẹp

Khi kiểm thử một configuration class hoặc auto-configuration, nên tự đặt các câu hỏi:

1. **Bean mục tiêu là gì?** Xác định type/name contract cần bảo vệ.
2. **Điều kiện nào quyết định sự tồn tại?** Property, classpath, bean, resource, web type hay profile?
3. **Nhánh thiếu cấu hình có được định nghĩa rõ?** Mặc định on hay off?
4. **Có custom bean override không?** `@ConditionalOnMissingBean` phải back off thế nào?
5. **Có dependency tùy chọn không?** Mô phỏng thiếu class bằng `FilteredClassLoader`.
6. **Có giá trị properties cần bind không?** Kiểm tra cả default và non-default value.
7. **Có invalid input cần fail fast không?** Kiểm tra `getStartupFailure()`.
8. **Có thứ tự giữa các auto-configurations không?** Xác định metadata ordering.
9. **Có web context dependency không?** Chọn runner web/reactive phù hợp.
10. **Test có vô tình gọi network/database thật không?** Dùng fake/stub khi chỉ cần wiring.
11. **Có đang assert chi tiết nội bộ không cần thiết không?** Tập trung vào public behavior.
12. **Có kiểm tra cả nhánh có và không?** Một positive assertion thường chưa đủ.
13. **Có đang giả định runner nạp application.yml tự động không?** Cung cấp properties tường minh.
14. **Có kiểm tra toàn bộ application ở nơi khác không?** Runner không thay thế integration tests.
15. **Callback có giữ resource sau khi context đóng không?** Đặt assertions trong `run`.

Checklist trên là định hướng khi **thiết kế test**, không phải yêu cầu viết toàn bộ mọi testcase cho mỗi bean. Với một configuration đơn giản, có thể chỉ cần hai hoặc ba test rõ ràng.

## Kết luận

`ApplicationContextRunner` là công cụ Spring Boot Test phù hợp để kiểm tra **các cấu hình và điều kiện đăng ký bean có phạm vi hẹp**. Nó tạo context theo những configuration classes, beans, properties và classloader do test cung cấp, cho phép assert trực tiếp sự tồn tại của bean, back-off behavior và startup failure, rồi đóng context sau callback.

Những API quan trọng gồm `withUserConfiguration(...)` cho cấu hình ứng dụng, `withConfiguration(AutoConfigurations.of(...))` cho auto-configuration, `withPropertyValues(...)` để thay đổi Environment, `withBean(...)` để cung cấp collaborator tùy chỉnh và `withClassLoader(new FilteredClassLoader(...))` để mô phỏng thiếu optional dependency. `withInitializer(...)` giúp chuẩn bị những điều kiện đặc biệt như active profiles hoặc condition report.

Giá trị lớn nhất của runner là **kiểm soát phạm vi**: muốn biết một auto-configuration có tạo đúng `AuditSink` khi property bật, bạn không cần khởi động database, HTTP server hay toàn bộ ứng dụng. Đồng thời, cần hiểu ranh giới của nó: runner không tự kiểm chứng packaging imports metadata, toàn bộ Config Data bootstrap, HTTP behavior hay artifact production. Kết hợp test hẹp bằng `ApplicationContextRunner` với các integration tests có mục tiêu sẽ tạo một nền tảng kiểm thử Spring Boot vừa nhanh, vừa dễ chẩn đoán và đủ tin cậy khi hệ thống phát triển.
