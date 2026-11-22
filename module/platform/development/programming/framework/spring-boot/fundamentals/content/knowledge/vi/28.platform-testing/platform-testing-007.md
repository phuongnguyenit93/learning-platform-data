# Kiểm thử profile, property và cách hiện thực được lựa chọn

Trong Spring Boot, cùng một interface có thể có nhiều cách triển khai tùy môi trường: implementation giả lập để chạy local/test, implementation kết nối hệ thống thật khi production, hoặc implementation tùy một feature flag. Khi điều kiện chọn sai, ứng dụng có thể khởi động với **bean không mong muốn**, thiếu bean bắt buộc hoặc có nhiều bean cùng type gây lỗi dependency injection.

Kiểm thử những trường hợp này cần trả lời nhiều hơn câu hỏi “profile có active không?”:

- **Profile nào thực sự được kích hoạt trong test context?**
- **Property nào đang có hiệu lực và có được bind/chuyển kiểu đúng không?**
- **Condition nào được đánh giá là đúng/sai?**
- **Có bao nhiêu bean cùng một contract, và Spring chọn implementation nào?**
- **Khi thiếu một điều kiện bắt buộc, ứng dụng fail-fast hay fallback đúng thiết kế?**

Bài học sử dụng Spring Boot Test, Spring Test và `ApplicationContextRunner` để kiểm thử **profile, property và implementation selection** ở mức nền tảng. Các ví dụ được viết để cho thấy rõ ranh giới giữa *cấu hình đầu vào*, *quyết định tạo bean* và *hành vi của bean được chọn*.

## 1. Vì sao việc chọn implementation cần được kiểm thử?

Giả sử hệ thống có interface gửi thông báo:

```java
public interface NotificationChannel {
    String channelName();
}
```

Hai implementation giả lập:

```java
public final class LocalNotificationChannel
        implements NotificationChannel {

    @Override
    public String channelName() {
        return "local";
    }
}
```

```java
public final class RemoteNotificationChannel
        implements NotificationChannel {

    @Override
    public String channelName() {
        return "remote";
    }
}
```

Các tên `local` và `remote` trong ví dụ chỉ là tín hiệu quan sát loại bean được chọn. Method `channelName()` không gọi network; không có external system thật trong các bài kiểm thử.

Yêu cầu vận hành:

1. Khi **không có profile `prod`**, dùng `LocalNotificationChannel`.
2. Khi có **profile `prod` và property `integration.notifications.enabled=true`**, dùng `RemoteNotificationChannel`.
3. Khi có **profile `prod` nhưng property không bật**, **không tạo channel**. Nếu service yêu cầu một channel bắt buộc, ứng dụng cần báo lỗi cấu hình thay vì âm thầm dùng local.

Một bảng quyết định:

| Active profiles | `integration.notifications.enabled` | Bean được mong đợi |
|---|---|---|
| Không chỉ định | Không có | Local |
| `dev` | Không có | Local |
| `test` | `false` | Local |
| `prod` | `true` | Remote |
| `prod` | `false` | Không có |
| `prod` | Không có | Không có |
| `dev,prod` | `true` | Remote |

Nếu test chỉ kiểm tra `Environment.getActiveProfiles()` trả về `prod`, test **chưa chứng minh** Spring đã đăng ký `RemoteNotificationChannel`.

Mục tiêu thực sự là kiểm tra quyết định cuối cùng của container.

## 2. Một ví dụ cấu hình làm nền tảng

Tạo configuration:

```java
package com.example.notification;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean("localNotificationChannel")
    @Profile("!prod")
    public NotificationChannel localNotificationChannel() {
        return new LocalNotificationChannel();
    }

    @Bean("remoteNotificationChannel")
    @Profile("prod")
    @ConditionalOnProperty(
        prefix = "integration.notifications",
        name = "enabled",
        havingValue = "true"
    )
    public NotificationChannel remoteNotificationChannel() {
        return new RemoteNotificationChannel();
    }
}
```

Đây là cấu hình **chỉ tạo một trong hai implementation hoặc không tạo cái nào**, tùy tổ hợp profile/property.

Mỗi cơ chế có vai trò riêng:

- `@Profile("!prod")`: chỉ đăng ký bean local nếu `prod` không active.
- `@Profile("prod")`: chỉ xét bean remote nếu `prod` active.
- `@ConditionalOnProperty(...)`: chỉ đăng ký bean remote khi flag bằng giá trị mong đợi.
- `@Bean("...")`: đặt tên bean rõ ràng để test có thể xác nhận cả tên và type.

Không thêm `@Component` vào hai implementation trong ví dụ này, vì các object đã được tạo qua `@Bean`. Nếu vừa component-scan implementation vừa khai báo `@Bean` tương ứng, bạn có thể vô tình tạo bean trùng.

## 3. Hiểu đúng điều kiện của ví dụ

Có thể viết điều kiện logic:

```text
Local được tạo  = NOT prod

Remote được tạo = prod AND notifications.enabled=true
```

Bởi vì `prod` và `!prod` đối nhau, hai bean không thể cùng được đăng ký từ **hai method này** tại cùng một context.

Nhưng vẫn có trạng thái không bean:

```text
prod active
    │
    ▼
Local bị loại
    │
    ▼
notifications.enabled=false hoặc không có
    │
    ▼
Remote bị loại
    │
    ▼
Không có NotificationChannel do configuration này cung cấp
```

Trạng thái “không có bean” không tự là bug nếu đây là chính sách fail-fast có chủ ý. Ngược lại, nếu production bắt buộc có sender, test nên chứng minh thiếu flag khiến việc tạo service phụ thuộc bị từ chối, thay vì cho hệ thống chạy với một fallback nguy hiểm.

**Lưu ý thiết kế:** `!prod` có nghĩa “không có prod”, không chỉ “dev hoặc test”. Khi bổ sung môi trường `staging` hoặc `demo`, bean local cũng có thể xuất hiện. Trong hệ thống thật, hãy cân nhắc biểu thức dương như `dev | test` nếu chỉ muốn hai môi trường đó, rồi test đầy đủ từng môi trường.

## 4. Các tầng kiểm thử cần phân biệt

Có ba lớp kiểm thử có thể dùng cho bài toán này.

| Lớp | Đối tượng | Chi phí tương đối | Phù hợp |
|---|---|---|---|
| Unit test thuần Java | Implementation/service method | Thấp | Logic của từng implementation |
| Context test hẹp bằng `ApplicationContextRunner` | Bean definitions, profile/property conditions, binding | Thấp đến vừa | Ma trận lựa chọn bean |
| `@SpringBootTest` | Spring Boot application context thực tế của test | Vừa đến cao | Kiểm tra wiring/integration và behavior tổng thể |

Ví dụ unit test:

```java
@Test
void localChannelReportsItsIdentity() {
    NotificationChannel channel =
            new LocalNotificationChannel();

    assertEquals("local", channel.channelName());
}
```

Test này chứng minh **class local hoạt động như code của nó định nghĩa**. Nó **không** chứng minh Spring đã chọn class local trong profile dev.

Để kiểm tra điều kiện của container, test phải dựng Spring context có profile và property phù hợp.

## 5. Test dependencies

Trong project Spring Boot thông dụng, starter test cung cấp Spring Test, JUnit Jupiter, AssertJ và những thư viện cần thiết khác theo version/BOM phù hợp.

Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Các code snippet phía dưới giả định project đang dùng JUnit Jupiter và những import Java/Spring phù hợp. Số version cụ thể được quản lý bởi build của project, không cần copy một version ngẫu nhiên từ ví dụ.

Với Spring Boot thuộc những dòng khác nhau, API mock bean hoặc test annotation bổ sung có thể thay đổi. Những bài test lựa chọn bean bên dưới ưu tiên **context thật và assertions**, tránh che mất behavior bằng cách mock cả bean cần chọn.

## 6. @SpringBootTest: khởi động context để test

`@SpringBootTest` là annotation trung tâm cho các integration tests của Spring Boot.

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
    classes = NotificationConfiguration.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("dev")
class LocalNotificationContextTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void selectsLocalChannel() {
        NotificationChannel channel =
                context.getBean(NotificationChannel.class);

        assertNotNull(channel);
        assertEquals("local", channel.channelName());
    }
}
```

Test này chỉ định một configuration class tối thiểu và chọn non-web context để tập trung vào bean selection.

Cần phân biệt:

- `classes = NotificationConfiguration.class`: xác định nguồn cấu hình cho test.
- `webEnvironment = NONE`: không khởi tạo embedded web server cho test này.
- `@ActiveProfiles("dev")`: đặt active profile của Spring Test context.
- `ApplicationContext.getBean(...)`: đọc bean mà container đã chọn.

Nếu bạn bỏ `classes`, Spring Boot test sẽ tìm cấu hình khởi động thích hợp theo các quy tắc test bootstrap. Điều đó có thể kéo thêm auto-configuration hoặc bean không liên quan, làm test nặng hơn.

## 7. @ActiveProfiles là gì?

`@ActiveProfiles` thuộc Spring Test, dùng để đặt **tên profile active** cho application context trong test.

```java
@ActiveProfiles("dev")
```

hoặc:

```java
@ActiveProfiles({"prod", "cloud"})
```

Trường hợp sau kích hoạt **hai tên profile độc lập**. Đừng nhầm với profile expression:

```java
@Profile("prod & cloud")
```

`@Profile` là biểu thức kiểm tra bean condition; `@ActiveProfiles` là tập tên profile mà test kích hoạt.

Ví dụ:

```java
@Component
@Profile("dev & cloud")
class CloudDeveloperTool {
}
```

Test đúng:

```java
@SpringBootTest
@ActiveProfiles({"dev", "cloud"})
class CloudDeveloperToolTest {
}
```

Không nên viết `@ActiveProfiles("dev & cloud")` rồi mặc định Spring sẽ hiểu đó là biểu thức AND. Nó là khai báo tên profile cho test, không phải pointcut hay expression parser của `@Profile`.

## 8. Test local implementation được chọn

Với `NotificationConfiguration` của phần 2:

```java
@SpringBootTest(
    classes = NotificationConfiguration.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("dev")
class DevNotificationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void createsExactlyOneLocalChannel() {
        String[] names =
                context.getBeanNamesForType(NotificationChannel.class);

        assertEquals(1, names.length);
        assertEquals("localNotificationChannel", names[0]);

        NotificationChannel channel =
                context.getBean(NotificationChannel.class);

        assertInstanceOf(LocalNotificationChannel.class, channel);
        assertEquals("local", channel.channelName());
    }
}
```

Test này kiểm tra ba tầng:

1. **Count:** chỉ một bean của interface.
2. **Name/type:** bean được chọn là local implementation.
3. **Behavior:** method trả nhận diện đúng.

`assertInstanceOf` thuộc JUnit Jupiter phiên bản phù hợp; nếu project dùng phiên bản khác, có thể dùng `assertTrue(LocalNotificationChannel.class.isInstance(channel))`.

**Không chỉ assert rằng local bean tồn tại.** Nếu remote bean cũng vô tình được đăng ký, test chỉ kiểm tra local presence có thể vẫn pass. Assertion “exactly one” bắt được lỗi chồng lấp cấu hình.

## 9. Truyền property vào @SpringBootTest

`@SpringBootTest` cho phép khai báo properties chỉ áp dụng cho test context:

```java
@SpringBootTest(
    classes = NotificationConfiguration.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "integration.notifications.enabled=true"
    }
)
@ActiveProfiles("prod")
class ProductionNotificationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void selectsRemoteChannel() {
        NotificationChannel channel =
                context.getBean(NotificationChannel.class);

        assertInstanceOf(RemoteNotificationChannel.class, channel);
        assertEquals("remote", channel.channelName());
        assertEquals(
                1,
                context.getBeanNamesForType(
                        NotificationChannel.class
                ).length
        );
    }
}
```

Đây là cách cấu hình tường minh một bối cảnh test:

- Profile `prod` active.
- Flag `integration.notifications.enabled=true`.
- Remote implementation phải được chọn.
- Local implementation phải không được đăng ký theo profile condition.

Property từ `@SpringBootTest(properties = ...)` là property source dành cho test, thường override nhiều cấu hình file/application thông thường. Nếu cùng lúc có nhiều cơ chế ghi đè test properties, cần hiểu precedence cụ thể và tránh tạo xung đột không cần thiết.

## 10. Không có flag trong prod: test trạng thái không bean

Trong ví dụ này, production không bật notifications thì không có `NotificationChannel`.

```java
@SpringBootTest(
    classes = NotificationConfiguration.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "integration.notifications.enabled=false"
    }
)
@ActiveProfiles("prod")
class DisabledProductionNotificationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void doesNotCreateAnyNotificationChannel() {
        assertEquals(
                0,
                context.getBeanNamesForType(
                        NotificationChannel.class
                ).length
        );
    }
}
```

Test này có thể khởi động thành công vì chỉ load `NotificationConfiguration`, không có service nào bắt buộc phải inject `NotificationChannel`.

Nếu ứng dụng thật có:

```java
@Service
public class NotificationService {

    private final NotificationChannel channel;

    public NotificationService(NotificationChannel channel) {
        this.channel = channel;
    }
}
```

và bean service này được load, trường hợp prod không có channel có thể khiến context fail startup vì thiếu dependency. Đây là behavior đáng kiểm tra thêm ở mức integration.

**Hai yêu cầu test khác nhau:**

- *Cấu hình không đăng ký channel khi flag false.*
- *Ứng dụng fail-fast nếu chức năng bắt buộc phụ thuộc vào channel mà lại không được cấu hình.*

Đừng đánh đồng chúng. Cùng một property có thể hợp lý ở một optional subsystem, nhưng là lỗi nghiêm trọng ở một mandatory subsystem.

## 11. Viết bảng trường hợp trước khi viết code

Một ma trận kiểm thử giúp tránh bỏ sót nhánh:

| ID | Profiles | Property | Expected channel | Expected count |
|---|---|---|---|---:|
| P1 | Không chỉ định | Không có | Local | 1 |
| P2 | `dev` | Không có | Local | 1 |
| P3 | `test` | false | Local | 1 |
| P4 | `prod` | true | Remote | 1 |
| P5 | `prod` | false | Không có | 0 |
| P6 | `prod` | missing | Không có | 0 |
| P7 | `dev,prod` | true | Remote | 1 |

P7 đặc biệt quan trọng: Spring cho phép nhiều profile cùng active. `@Profile("!prod")` không match nếu prod active, dù dev cũng active.

Một ma trận có cả **positive**, **negative**, **missing** và **mixed-profile** cases thường có giá trị hơn một test chỉ chạy với profile dev.

## 12. ApplicationContextRunner để test cấu hình nhanh

`ApplicationContextRunner` thuộc Spring Boot Test, giúp dựng những context nhỏ có điều kiện kiểm soát được, rồi đưa context vào callback assertions.

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class NotificationConfigurationRunnerTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(
                    NotificationConfiguration.class
                );

    @Test
    void selectsLocalWhenNoProdProfile() {
        runner.run(context -> {
            assertThat(context)
                    .hasSingleBean(NotificationChannel.class);

            NotificationChannel channel =
                    context.getBean(NotificationChannel.class);

            assertThat(channel)
                    .isInstanceOf(LocalNotificationChannel.class);

            assertThat(channel.channelName())
                    .isEqualTo("local");
        });
    }
}
```

Đặc điểm hữu ích:

- Không phải chạy toàn bộ Spring Boot application.
- Dễ thêm/bớt property và user configuration.
- Dễ kiểm tra bean count, bean type và startup failure.
- Mỗi lời gọi `run(...)` có vòng đời context riêng được quản lý bởi runner.
- Rất phù hợp với unit/integration-style tests của auto-configuration.

Tuy vậy, context nhỏ không nhất thiết tải toàn bộ bean, filter và auto-configuration của production app. Kết quả đúng với configuration đã đăng ký trong runner; để xác nhận wiring toàn ứng dụng, cần thêm một số `@SpringBootTest`.

## 13. Dùng ApplicationContextRunner với property

Ví dụ property false không tạo remote bean trong prod:

```java
@Test
void prodWithDisabledFlagHasNoChannel() {
    runner
        .withInitializer(context ->
            context.getEnvironment().setActiveProfiles("prod")
        )
        .withPropertyValues(
            "integration.notifications.enabled=false"
        )
        .run(context -> {
            assertThat(context)
                    .doesNotHaveBean(NotificationChannel.class);
        });
}
```

Ví dụ property true:

```java
@Test
void prodWithEnabledFlagSelectsRemote() {
    runner
        .withInitializer(context ->
            context.getEnvironment().setActiveProfiles("prod")
        )
        .withPropertyValues(
            "integration.notifications.enabled=true"
        )
        .run(context -> {
            assertThat(context)
                    .hasSingleBean(NotificationChannel.class);

            NotificationChannel channel =
                    context.getBean(NotificationChannel.class);

            assertThat(channel)
                    .isInstanceOf(RemoteNotificationChannel.class);

            assertThat(channel.channelName())
                    .isEqualTo("remote");
        });
}
```

Ở các đoạn này, `runner` là field đã khai báo trong `NotificationConfigurationRunnerTest` ở phần trước.

**Vì sao dùng `setActiveProfiles("prod")`?** `ApplicationContextRunner` là công cụ dựng context nhỏ, không tự mô phỏng toàn bộ quy trình Spring Boot startup/config-data theo mọi đặc điểm của ứng dụng. Việc đặt trực tiếp active profiles trên Environment của context làm ý định test rõ ràng. Đừng giả định chỉ thêm một property `spring.profiles.active=prod` bằng `withPropertyValues(...)` sẽ luôn tương đương với cơ chế activate profile tại giai đoạn bootstrap của ứng dụng thật.

## 14. Test nhiều profile với ApplicationContextRunner

Muốn kiểm tra trường hợp `prod` và `dev` cùng active:

```java
@Test
void prodWinsTheExplicitSelectionEvenWithDevActive() {
    runner
        .withInitializer(context ->
            context.getEnvironment()
                .setActiveProfiles("dev", "prod")
        )
        .withPropertyValues(
            "integration.notifications.enabled=true"
        )
        .run(context -> {
            assertThat(context)
                    .hasSingleBean(NotificationChannel.class);

            assertThat(
                context.getBean(NotificationChannel.class)
                       .channelName()
            ).isEqualTo("remote");
        });
}
```

Không có khái niệm tự động “prod ưu tiên dev” trong ví dụ này. Kết quả remote xảy ra vì:

1. `prod` active nên `@Profile("prod")` match.
2. `!prod` sai nên bean local bị loại.
3. `integration.notifications.enabled=true` nên condition của bean remote match.

Kết quả được suy ra từ **biểu thức điều kiện**, không phải ưu tiên ngầm của tên profile.

## 15. Kiểm thử một implementation bị loại

Khi chỉ cần chứng minh bean sai không tồn tại, dùng assertion trực tiếp:

```java
@Test
void devDoesNotRegisterRemoteImplementation() {
    runner
        .withInitializer(context ->
            context.getEnvironment().setActiveProfiles("dev")
        )
        .run(context -> {
            assertThat(context)
                    .hasSingleBean(NotificationChannel.class);

            assertThat(context)
                    .doesNotHaveBean(RemoteNotificationChannel.class);
        });
}
```

**Lưu ý:** nếu bean method khai báo return type là interface, việc test Spring bean type resolution có thể phụ thuộc vào metadata và lúc bean thực sự được khởi tạo. Cách ổn định khác là lấy danh sách bean của contract rồi xác nhận class của object thực tế:

```java
NotificationChannel actual =
        context.getBean(NotificationChannel.class);

assertThat(actual)
        .isInstanceOf(LocalNotificationChannel.class);
```

Trong trường hợp muốn kiểm tra bean name tường minh:

```java
assertThat(context.containsBean("localNotificationChannel"))
        .isTrue();

assertThat(context.containsBean("remoteNotificationChannel"))
        .isFalse();
```

Các cách kiểm tra type, name và behavior bổ sung cho nhau. Đừng chỉ phụ thuộc một bean name nếu tên đó không phải một phần contract của module.

## 16. Kiểm thử expected failure khi thiếu dependency

Một configuration thuần chỉ tạo các candidate channels. Để kiểm tra cấu hình không hợp lệ làm ứng dụng thất bại, đăng ký thêm một consumer cần channel:

```java
public class NotificationCoordinator {

    private final NotificationChannel channel;

    public NotificationCoordinator(NotificationChannel channel) {
        this.channel = channel;
    }

    public String currentMode() {
        return channel.channelName();
    }
}
```

Factory configuration:

```java
@Configuration(proxyBeanMethods = false)
public class NotificationCoordinatorConfiguration {

    @Bean
    NotificationCoordinator notificationCoordinator(
            NotificationChannel channel) {
        return new NotificationCoordinator(channel);
    }
}
```

Test:

```java
@Test
void prodWithoutEnabledFlagFailsFast() {
    runner
        .withUserConfiguration(
            NotificationCoordinatorConfiguration.class
        )
        .withInitializer(context ->
            context.getEnvironment().setActiveProfiles("prod")
        )
        .withPropertyValues(
            "integration.notifications.enabled=false"
        )
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                    .isNotNull();
        });
}
```

Khi Spring cố tạo `NotificationCoordinator` mà không tìm được `NotificationChannel`, startup có thể thất bại vì dependency không được đáp ứng.

Test này có hai lợi ích:

- Kiểm tra *không có fallback âm thầm*.
- Bảo vệ chính sách “production phải có cấu hình rõ ràng”.

Để test thông báo lỗi chi tiết, hãy hiểu loại exception chain của version đang chạy thay vì so khớp toàn bộ exception text dễ thay đổi.

## 17. @TestPropertySource là gì?

`@TestPropertySource` thuộc Spring Test, cho phép bổ sung properties hoặc property files dành riêng cho test context.

Ví dụ:

```java
import org.springframework.test.context.TestPropertySource;

@SpringBootTest(
    classes = NotificationConfiguration.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("prod")
@TestPropertySource(properties = {
    "integration.notifications.enabled=true"
})
class NotificationWithTestPropertySourceTest {
}
```

Có thể dùng resource file dạng properties:

```java
@TestPropertySource(
    locations = "classpath:notification-test.properties"
)
```

và tạo `src/test/resources/notification-test.properties`:

```properties
integration.notifications.enabled=true
```

**Chú ý về định dạng:** `@TestPropertySource(locations=...)` theo cơ chế mặc định của Spring Test đọc property resources theo contract được hỗ trợ, phổ biến là `.properties`. Không nên tự giả định mọi file `.yml` trong `locations` sẽ được parse như Spring Boot config data nếu không có cấu hình factory phù hợp.

## 18. @SpringBootTest(properties) hay @TestPropertySource?

Cả hai có thể thêm test properties. Chọn một cách chính cho mỗi nhóm test để giảm xung đột.

| Nhu cầu | Lựa chọn thuận tiện |
|---|---|
| Một hoặc vài key riêng cho một integration test | `@SpringBootTest(properties=...)` |
| Một file `.properties` dùng chung cho bộ test | `@TestPropertySource(locations=...)` |
| Test thuần conditional configuration với nhiều tổ hợp | `ApplicationContextRunner.withPropertyValues(...)` |
| Giá trị do database/container được khởi tạo trong test tạo ra | `@DynamicPropertySource` |
| Load `application-dev.yml` theo profile | `@ActiveProfiles("dev")` trong Spring Boot test |

Không nên trộn nhiều nguồn đặt cùng key trừ khi đang **cố ý test precedence**. Một test phụ thuộc vào chuỗi override phức tạp dễ khó hiểu và khó bảo trì.

Khi cần xác minh giá trị thực tế, có thể inject `Environment` và kiểm tra `getProperty(...)`, nhưng hãy nhớ property có mặt chưa đủ chứng minh bean được chọn đúng.

## 19. Test property default và missing

`@ConditionalOnProperty` có những semantics quan trọng. Với:

```java
@ConditionalOnProperty(
    prefix = "integration.notifications",
    name = "enabled",
    havingValue = "true"
)
```

mặc định `matchIfMissing=false`. Do đó, nếu key hoàn toàn vắng mặt, condition không match.

Viết test:

```java
@Test
void missingFlagDoesNotSelectRemote() {
    runner
        .withInitializer(context ->
            context.getEnvironment().setActiveProfiles("prod")
        )
        .run(context -> {
            assertThat(context)
                    .doesNotHaveBean(NotificationChannel.class);
        });
}
```

Một configuration khác có thể dùng `matchIfMissing=true`:

```java
@ConditionalOnProperty(
    prefix = "feature.audit",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
```

Khi đó, **missing** và **explicit false** là hai tình huống khác nhau. Cần test cả hai.

Bảng hành vi khái quát cho `havingValue="true"`:

| Property | `matchIfMissing=false` | `matchIfMissing=true` |
|---|---:|---:|
| Missing | Không match | Match |
| `true` | Match | Match |
| `false` | Không match | Không match |
| Giá trị khác `true` | Không match | Không match |

Nếu bỏ `havingValue`, semantics của `@ConditionalOnProperty` khác: thông thường property chỉ cần tồn tại và không phải `false`. Đừng suy ra tất cả property conditions đều là boolean checks giống nhau.

## 20. Đọc property thực sự được dùng trong test

Để kiểm tra cấu hình hiệu lực, inject `Environment`:

```java
@SpringBootTest(
    classes = NotificationConfiguration.class,
    properties = "integration.notifications.enabled=true",
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("prod")
class NotificationEnvironmentTest {

    @Autowired
    Environment environment;

    @Test
    void propertyIsEffective() {
        assertEquals(
                "true",
                environment.getProperty(
                        "integration.notifications.enabled"
                )
        );
    }
}
```

Test này hữu ích để phân biệt property không được nạp và bean condition sai. Nhưng nó **không thay thế** test bean selection:

```java
assertEquals(
    "remote",
    context.getBean(NotificationChannel.class)
           .channelName()
);
```

Đọc Environment chứng minh **input configuration**. Đọc ApplicationContext chứng minh **output của quy trình đăng ký bean**.

## 21. Test @ConfigurationProperties và typed binding

Một property có thể tồn tại ở dạng String nhưng bị bind sai kiểu, hoặc object properties không được đăng ký.

Ví dụ:

```yaml
app:
  client:
    timeout: 5s
    max-attempts: 3
```

Typed properties:

```java
package com.example.notification;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        Duration timeout,
        int maxAttempts
) {
}
```

Đăng ký property object trong context test:

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
class ClientPropertiesConfiguration {
}
```

Test bằng `ApplicationContextRunner`:

```java
@Test
void bindsClientProperties() {
    new ApplicationContextRunner()
        .withUserConfiguration(
            ClientPropertiesConfiguration.class
        )
        .withPropertyValues(
            "app.client.timeout=5s",
            "app.client.max-attempts=3"
        )
        .run(context -> {
            assertThat(context)
                    .hasSingleBean(ClientProperties.class);

            ClientProperties properties =
                    context.getBean(ClientProperties.class);

            assertThat(properties.timeout())
                    .isEqualTo(Duration.ofSeconds(5));

            assertThat(properties.maxAttempts())
                    .isEqualTo(3);
        });
}
```

Ở đây, test chứng minh Spring Boot **đã chuyển chuỗi `5s` thành `Duration`** và bind `max-attempts` vào Java property `maxAttempts`.

Nếu class properties chưa được đăng ký, việc đặt `app.client.timeout` trong Environment không tự sinh ra `ClientProperties` bean.

## 22. Test lỗi binding và validation

Xét cấu hình sai:

```properties
app.client.timeout=not-a-duration
```

Với properties object được bind trong quá trình khởi tạo, Spring có thể ném lỗi vì không chuyển chuỗi trên thành `Duration`.

Test:

```java
@Test
void invalidDurationFailsContextStartup() {
    new ApplicationContextRunner()
        .withUserConfiguration(
            ClientPropertiesConfiguration.class
        )
        .withPropertyValues(
            "app.client.timeout=not-a-duration",
            "app.client.max-attempts=3"
        )
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                    .isNotNull();
        });
}
```

Đây là test **conversion failure**.

**Validation failure** là trường hợp khác: giá trị có thể chuyển kiểu nhưng không hợp lệ theo nghiệp vụ, ví dụ `max-attempts=-1`. Khi cần constraint như `@Min(0)` hoặc timeout dương, phải định nghĩa validation trên properties object và bảo đảm validation infrastructure được bật. Không nên nghĩ Spring tự từ chối mọi số âm chỉ vì field có tên `maxAttempts`.

## 23. Test @Value cho một property đơn

`@Value` có thể được dùng thay cho `@ConfigurationProperties` khi bean chỉ cần một giá trị đơn lẻ.

Ví dụ:

```java
@Component
public class WelcomeMessage {

    private final String prefix;

    public WelcomeMessage(
            @Value("${app.welcome.prefix:Hello}") String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        return prefix + " " + name;
    }
}
```

Test context với property:

```java
@SpringBootTest(
    classes = WelcomeMessage.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "app.welcome.prefix=Chao"
)
class WelcomeMessageTest {

    @Autowired
    WelcomeMessage message;

    @Test
    void usesConfiguredPrefix() {
        assertEquals("Chao Linh", message.greet("Linh"));
    }
}
```

Nếu cần test default `Hello`, tạo context khác không cung cấp property. Không đổi biến môi trường giữa hai test methods rồi kỳ vọng context đang cached sẽ tự được rebind.

## 24. @DynamicPropertySource dành cho giá trị được tạo lúc test

Nhiều integration test cần port/URL động của database, message broker hoặc HTTP test server. Ghi cố định URL trong YAML dễ gây xung đột giữa máy phát triển và CI.

Spring Test cung cấp `@DynamicPropertySource` để thêm properties do code test tạo ra.

Ví dụ tối giản, không cần container thật:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class DynamicPortExampleTest {

    @DynamicPropertySource
    static void dynamicProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "integration.remote.port",
            () -> 18081
        );
    }

    @Autowired
    Environment environment;

    @Test
    void dynamicPropertyIsVisible() {
        assertEquals(
                18081,
                environment.getProperty(
                    "integration.remote.port",
                    Integer.class
                )
        );
    }
}
```

Trong use case thực tế, supplier thường lấy port từ một container/server đã được khởi tạo. Các property động có precedence cao trong Spring Test; cần tránh cùng key được đặt từ nhiều nguồn mà không có chủ đích.

Chú ý `@DynamicPropertySource` được xử lý khi Spring Test chuẩn bị context. Nó không phải một API để tự động đổi bean configuration giữa các test methods sau khi context đã được refresh.

## 25. Kiểm thử với database/container thật

Khi ứng dụng chọn implementation dựa trên sự có mặt của một integration, đôi khi test cần sử dụng Testcontainers hoặc một service thật được cô lập.

Ví dụ mục tiêu:

- Profile `integration` active.
- Database container chạy trên port ngẫu nhiên.
- Dynamic properties cung cấp URL/credentials cho datasource.
- Bean repository thật được tạo và có thể truy cập.

Một test dạng này kiểm tra toàn bộ wiring và behavior tốt hơn một `ApplicationContextRunner` chỉ tạo bean definitions.

Tuy nhiên, **đừng dùng external integration chỉ để chứng minh một `@ConditionalOnProperty` hoạt động**. Test hẹp đủ cho logic chọn bean; integration test với external resource nên dành cho behavior thực sự phụ thuộc resource.

Để test deterministic:

1. Quản lý vòng đời external resource trong fixture.
2. Không dùng chung database production.
3. Tạo data riêng và cleanup rõ.
4. Không phụ thuộc port cố định nếu có thể tránh.
5. Truyền properties động từ fixture thay vì hard-code.
6. Cân nhắc tốc độ và resource usage trong CI.

## 26. Profile-specific YAML và @ActiveProfiles

Spring Boot có thể nạp các tệp như:

```text
application.yml
application-dev.yml
application-prod.yml
```

khi chạy với active profile phù hợp.

Ví dụ:

```yaml
# src/main/resources/application.yml
app:
  client:
    timeout: 10s
```

```yaml
# src/main/resources/application-dev.yml
app:
  client:
    timeout: 2s
```

Test:

```java
@SpringBootTest
@ActiveProfiles("dev")
class DevTimeoutConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void usesDevTimeout() {
        assertEquals(
                "2s",
                environment.getProperty("app.client.timeout")
        );
    }
}
```

Trong Spring Boot test có config-data loading tương ứng, profile dev khiến file `application-dev.yml` được xét theo quy tắc Boot.

Nếu test có property override từ `@SpringBootTest(properties = "app.client.timeout=5s")`, giá trị runtime có thể trở thành `5s`, không còn là giá trị từ profile YAML. Hãy xác định test đang xác minh **profile-specific config loading** hay **override từ test**; tránh trộn cả hai mục đích.

## 27. Default profile khác active profile

Khi không chỉ định active profiles, Spring sử dụng **default profiles** theo quy tắc của Environment.

Ví dụ bean:

```java
@Bean
@Profile("default")
public NotificationChannel defaultChannel() {
    return new LocalNotificationChannel();
}
```

Có thể được đăng ký khi không có active profile và default profile hiệu lực là `default`.

Trong khi đó:

```java
@Profile("!prod")
```

khớp trong nhiều trường hợp khác, như `dev` hoặc `test`, miễn `prod` không active.

Đây là hai điều kiện khác nhau, nên test:

- Không có active profile.
- Có `dev` active.
- Có `prod` active.
- Có custom default profile nếu ứng dụng sử dụng.

Đặc biệt, test không đặt `@ActiveProfiles` không nhất thiết mô phỏng production: một số môi trường test còn có test properties, startup arguments hoặc active profiles do base class/annotation kế thừa.

## 28. Biểu thức profile AND, OR, NOT trong test

Spring `@Profile` hỗ trợ expression:

```java
@Profile("(dev | staging) & cloud & !maintenance")
```

Nếu dùng `@ActiveProfiles({"dev", "cloud"})`, expression trên đúng.

Nếu active là `{"dev", "cloud", "maintenance"}`, expression sai.

Ví dụ:

```java
@Test
void profileExpressionCanBeCheckedDirectly() {
    MockEnvironment environment = new MockEnvironment();
    environment.setActiveProfiles("dev", "cloud");

    assertTrue(
        environment.acceptsProfiles(
            Profiles.of("(dev | staging) & cloud & !maintenance")
        )
    );
}
```

Cần import `MockEnvironment` từ Spring Test và `Profiles` từ Spring Core.

Test `Profiles.of(...)` rất nhanh nhưng chỉ xác minh **logic expression**. Để chứng minh bean được chọn trong context thực tế, cần thêm test configuration với `@Profile` tương ứng.

## 29. @Profile nhận mảng không giống AND

Hai khai báo sau **không tương đương**:

```java
@Profile({"dev", "cloud"})
```

và:

```java
@Profile("dev & cloud")
```

Khai báo đầu là **dev OR cloud**; khai báo sau là **dev AND cloud**.

Một test hữu ích:

```text
Active: dev only

@Profile({"dev", "cloud"}) -> match
@Profile("dev & cloud")  -> không match
```

Khi dùng `@ActiveProfiles({"dev", "cloud"})`, **cả hai profile được kích hoạt** nên cả hai điều kiện trên đều match. Điều này có thể che lỗi thiết kế nếu bạn chỉ test trường hợp cả hai cùng active.

Hãy thêm ít nhất một test “chỉ dev” và một test “chỉ cloud” nếu ý định AND/OR quan trọng.

## 30. Kiểm tra @Primary và @Qualifier

Có trường hợp ứng dụng cố tình đăng ký **nhiều beans cùng type** nhưng muốn chọn một bằng `@Primary` hoặc `@Qualifier`.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class GatewayConfiguration {

    @Bean("primaryGateway")
    @Primary
    NotificationChannel primaryGateway() {
        return new LocalNotificationChannel();
    }

    @Bean("backupGateway")
    NotificationChannel backupGateway() {
        return new RemoteNotificationChannel();
    }
}
```

Khi inject theo type:

```java
@Service
public class ChannelConsumer {

    private final NotificationChannel channel;

    public ChannelConsumer(NotificationChannel channel) {
        this.channel = channel;
    }

    public String mode() {
        return channel.channelName();
    }
}
```

`@Primary` làm một bean được ưu tiên khi có nhiều candidates phù hợp trong một số injection points.

Nhưng lưu ý:

- Cả `primaryGateway` và `backupGateway` **đều tồn tại**.
- `getBeansOfType(NotificationChannel.class)` có thể trả hai beans.
- `@Primary` không có nghĩa Spring không tạo backup bean.
- Một `@Qualifier("backupGateway")` có thể chỉ định implementation khác.

Test nên phân biệt **bean được đăng ký** với **bean được inject vào consumer**.

## 31. Test bean được inject, không chỉ count

Ví dụ muốn xác minh consumer nhận primary:

```java
@Test
void consumerUsesPrimaryGateway() {
    new ApplicationContextRunner()
        .withUserConfiguration(
            GatewayConfiguration.class,
            ChannelConsumerConfiguration.class
        )
        .run(context -> {
            assertThat(
                context.getBeansOfType(NotificationChannel.class)
            ).hasSize(2);

            ChannelConsumer consumer =
                    context.getBean(ChannelConsumer.class);

            assertThat(consumer.mode())
                    .isEqualTo("local");
        });
}
```

Configuration tạo consumer:

```java
@Configuration(proxyBeanMethods = false)
class ChannelConsumerConfiguration {

    @Bean
    ChannelConsumer channelConsumer(NotificationChannel channel) {
        return new ChannelConsumer(channel);
    }
}
```

Ví dụ này cho thấy:

- Cả hai beans được tạo.
- Constructor injection chọn bean primary.
- Behavior sau injection phản ánh implementation được chọn.

Nếu đổi một implementation mà test chỉ kiểm tra có hai beans, test có thể bỏ sót regression ở resolution của injection point.

## 32. Test @ConditionalOnMissingBean và fallback

Một mẫu auto-configuration phổ biến: tạo default bean **khi người dùng chưa cung cấp** implementation.

```java
@Configuration(proxyBeanMethods = false)
public class DefaultChannelAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationChannel.class)
    NotificationChannel defaultChannel() {
        return new LocalNotificationChannel();
    }
}
```

Test fallback:

```java
@Test
void createsDefaultWhenNoUserBean() {
    new ApplicationContextRunner()
        .withUserConfiguration(
            DefaultChannelAutoConfiguration.class
        )
        .run(context ->
            assertThat(context)
                .hasSingleBean(NotificationChannel.class)
        );
}
```

Test user override:

```java
@Configuration(proxyBeanMethods = false)
class CustomChannelConfiguration {

    @Bean
    NotificationChannel customChannel() {
        return new RemoteNotificationChannel();
    }
}
```

```java
@Test
void backsOffWhenUserDefinesChannel() {
    new ApplicationContextRunner()
        .withUserConfiguration(
            CustomChannelConfiguration.class,
            DefaultChannelAutoConfiguration.class
        )
        .run(context -> {
            assertThat(context)
                    .hasSingleBean(NotificationChannel.class);

            assertThat(
                context.getBean(NotificationChannel.class)
            ).isInstanceOf(RemoteNotificationChannel.class);
        });
}
```

Trong auto-configuration thực tế, thứ tự xử lý bean definitions và điều kiện `@ConditionalOnMissingBean` có ý nghĩa. Cấu hình mặc định thường cần được tổ chức để điều kiện được đánh giá sau khi user configuration thích hợp đã được xét. Khi test, dùng ordering/auto-configuration registration đúng với thiết kế module, không dựa vào may rủi thứ tự scan.

**Chú ý:** `@ConditionalOnMissingBean` không phải `@Profile`. Nó kiểm tra bean candidates, không kiểm tra tên môi trường.

## 33. @TestConfiguration và test-only beans

Một số integration tests cần thêm bean test-only, ví dụ fake external clock, fake service hoặc fixture provider.

`@TestConfiguration` của Spring Boot giúp mô tả configuration dành cho test:

```java
@TestConfiguration(proxyBeanMethods = false)
class FixedClockTestConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

Có thể import vào test:

```java
@SpringBootTest
@Import(FixedClockTestConfiguration.class)
class ClockIntegrationTest {
    // Kiểm thử các bean dùng Clock cố định.
}
```

Tuy nhiên, thêm test-only bean có thể **làm thay đổi** kết quả `@ConditionalOnMissingBean`, `@Primary` hoặc auto-configuration, khiến bạn không còn test behavior của cấu hình production gốc.

Nếu mục tiêu là kiểm tra Bean A có được Boot tự tạo không, không nên vô tình thay A bằng fake rồi kết luận auto-configuration đã hoạt động. Ghi rõ test context đang có những bean overrides nào.

## 34. Mock bean có thể che lỗi lựa chọn implementation

Khi test controller, nhiều người thay service thật bằng mock để cô lập web layer. Đây là phương pháp hợp lý cho unit/slice testing, nhưng **không phù hợp làm bằng chứng rằng Spring đã chọn đúng service implementation**.

Ví dụ ý tưởng:

```java
@MockitoBean
NotificationChannel notificationChannel;
```

`@MockitoBean` là cơ chế bean override của Spring Test trong các dòng Spring Framework mới phù hợp. Một số dự án Spring Boot cũ dùng `@MockBean`, nhưng annotation và vòng đời hỗ trợ khác theo version.

Nếu mock thay thế `NotificationChannel`, test có thể pass ngay cả khi local/remote selection không đúng như deployment thực tế.

Hãy chọn:

- **Test controller contract:** mock service dependency khi cần isolation.
- **Test profile/condition selection:** giữ configuration và bean candidates thật, kiểm tra type/name/count.
- **Test end-to-end integration:** dùng test fixture hoặc external resource thích hợp.

Không có một kỹ thuật mock nào thay thế được mọi lớp kiểm thử.

## 35. Test slice không nhất thiết load đủ beans

`@WebMvcTest`, `@DataJpaTest` và các test slices khác tập trung vào một phần application context.

Ví dụ `@WebMvcTest(OrderController.class)` không nhất thiết load tất cả `@Service`, `@ConfigurationProperties` hoặc configuration conditions trong ứng dụng.

Nếu test slice thiếu bean, có thể do slice cố ý giới hạn components, chứ không phải profile/condition bị sai.

Khi muốn kiểm tra **Spring chọn implementation nào trong application**, ưu tiên:

- `ApplicationContextRunner` với configuration được khai báo rõ.
- `@SpringBootTest` với classes/profiles/properties phù hợp.

Khi chỉ test HTTP mapping, serialization hoặc validation ở controller, slice test thường gọn hơn.

**Không kết luận từ một slice test rằng bean luôn vắng mặt trong full application context.**

## 36. Context caching ảnh hưởng các test ra sao?

Spring Test có cơ chế **ApplicationContext caching** để tái sử dụng context giữa những test có cùng cấu hình phù hợp.

Một context cache key có thể phụ thuộc vào:

- Configuration classes được nạp.
- Active profiles.
- Inline test properties và property sources.
- Context initializers.
- Một số test customizers, mock/bean override hoặc dynamic property configuration.
- Các yếu tố bootstrap/context hierarchy khác.

Hệ quả thực tế: đổi `System.setProperty(...)` giữa hai test methods **không có nghĩa** context đã được khởi tạo sẽ tạo lại beans và đánh giá `@ConditionalOnProperty` lần nữa.

Ví dụ cách làm dễ gây sai:

```java
@Test
void first() {
    System.setProperty("integration.notifications.enabled", "true");
    // Mong context tự được rebuild: không đúng.
}
```

Bean definitions đã được quyết định khi context được xây. Với profile/property selection, thường nên dùng **test classes có cấu hình riêng** hoặc `ApplicationContextRunner` tạo context độc lập cho từng case.

## 37. @DirtiesContext: khi nào cần?

`@DirtiesContext` đánh dấu context cache không còn phù hợp để tái sử dụng.

Ví dụ:

```java
@SpringBootTest
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS
)
class MutatingContextTest {
}
```

Điều này có thể cần khi test thực sự thay đổi trạng thái context theo cách ảnh hưởng test khác.

Nhưng không nên dùng `@DirtiesContext` như cách mặc định cho mọi case profile/property:

- Nó làm test suite chậm hơn.
- Nó không thay thế việc chỉ định property source đúng trước khi context được dựng.
- Nó có thể che dấu test state leaking.
- Nó không bảo đảm external resources như database được reset nếu bạn không quản lý chúng riêng.

Nếu chỉ cần nhiều tổ hợp flags, `ApplicationContextRunner` thường rẻ và rõ hơn.

## 38. Unit test với MockEnvironment

Khi chỉ muốn xác minh profile expression, có thể dùng `MockEnvironment` mà không cần Spring Boot context:

```java
@Test
void prodAndCloudExpressionMatches() {
    MockEnvironment env = new MockEnvironment();

    env.setActiveProfiles("prod", "cloud");

    assertTrue(
        env.acceptsProfiles(
            Profiles.of("prod & cloud")
        )
    );

    assertFalse(
        env.acceptsProfiles(
            Profiles.of("dev & !prod")
        )
    );
}
```

Với named property:

```java
@Test
void exposesPropertyForSimpleLogic() {
    MockEnvironment env = new MockEnvironment()
        .withProperty("feature.audit.enabled", "true");

    assertEquals(
        "true",
        env.getProperty("feature.audit.enabled")
    );
}
```

`MockEnvironment` test logic ở cấp Environment. Nó không tạo configuration bean hoặc chạy `@ConditionalOnProperty` nếu không có Spring context.

Dùng nó như bài test phụ cho logic biểu thức, không thay thế test container wiring.

## 39. Ma trận property precedence trong test

Khi cùng key được khai báo ở nhiều nơi, Spring Boot có quy tắc precedence của property sources. Với test, các nguồn bổ sung như inline properties hoặc dynamic properties có thể được ưu tiên cao hơn file application thông thường.

Một bảng thiết kế thử nghiệm:

| Nguồn | Ví dụ | Mục tiêu test |
|---|---|---|
| `application.yml` | `mode=local` | Cấu hình mặc định |
| `application-prod.yml` | `mode=remote` | Cấu hình theo profile |
| `@SpringBootTest(properties=...)` | `mode=test-remote` | Override trong test |
| `@TestPropertySource` | `mode=simulated` | Test-specific property source |
| `@DynamicPropertySource` | URL/port từ fixture | Dynamic runtime values |

Không nên gắn nhãn thứ tự tuyệt đối cho mọi cặp nếu chưa biết version và cơ chế bootstrap của ứng dụng; điều quan trọng là **kiểm chứng property hiệu lực** bằng `Environment` rồi **kiểm chứng bean selection** bằng `ApplicationContext`.

Nếu đang kiểm thử precedence, hãy tạo một test riêng có tên thể hiện rõ giả thuyết: “inline test property overrides config data”. Tránh để test business logic phụ thuộc vào nhiều nguồn override khó nhìn thấy.

## 40. Kiểm tra nguyên nhân khi nhiều beans cùng type

Giả sử có:

```java
@Bean
@Profile("dev | test")
NotificationChannel localChannel() { /* ... */ }

@Bean
@Profile("test | staging")
NotificationChannel anotherChannel() { /* ... */ }
```

Khi `test` active, **cả hai** expressions đều đúng. Nếu một service chỉ inject `NotificationChannel` theo type và không có `@Primary`/`@Qualifier`, có thể xảy ra `NoUniqueBeanDefinitionException`.

Một bài test hữu ích:

```java
@Test
void testProfileDetectsAmbiguousConfiguration() {
    new ApplicationContextRunner()
        .withUserConfiguration(
            OverlappingChannelConfiguration.class,
            NotificationCoordinatorConfiguration.class
        )
        .withInitializer(context ->
            context.getEnvironment().setActiveProfiles("test")
        )
        .run(context -> {
            assertThat(context).hasFailed();
        });
}
```

`OverlappingChannelConfiguration` là configuration minh họa phải tự khai báo các bean như trên; test kiểm tra việc thiếu quy tắc chọn khi hai implementation cùng tồn tại.

Nếu thiết kế mong cả hai beans cùng có mặt, thay vì fail hãy inject `List<NotificationChannel>` hoặc `Map<String, NotificationChannel>`, hoặc dùng `@Qualifier` để chọn một bean cụ thể.

Test phải phản ánh **contract lựa chọn** của consumer, không mặc định rằng nhiều beans luôn là bug.

## 41. Kiểm tra bean selected theo type, tên và hành vi

Có ba cách xác nhận khác nhau:

**Theo type:**

```java
NotificationChannel channel =
        context.getBean(NotificationChannel.class);

assertThat(channel)
        .isInstanceOf(RemoteNotificationChannel.class);
```

**Theo tên bean:**

```java
assertThat(context.containsBean("remoteNotificationChannel"))
        .isTrue();

assertThat(context.containsBean("localNotificationChannel"))
        .isFalse();
```

**Theo hành vi:**

```java
assertThat(channel.channelName())
        .isEqualTo("remote");
```

Cùng với count:

```java
assertThat(context)
        .hasSingleBean(NotificationChannel.class);
```

Kết hợp các assertions này khi bean selection là behavior cần bảo vệ. Chỉ kiểm tra tên bean thường quá phụ thuộc implementation detail; chỉ kiểm tra behavior có thể không phát hiện hai beans trùng type nếu chúng trả kết quả giống nhau.

## 42. Kiểm thử fail-fast hay fallback

Có hai chính sách hợp lệ, nhưng phải chọn rõ:

### Chính sách A — Fail-fast

Trong production, nếu thiếu cấu hình remote thì application không thể hoàn thành startup.

Ưu điểm:

- Phát hiện lỗi triển khai sớm.
- Tránh âm thầm dùng implementation không an toàn.
- Dễ giám sát deployment failure.

Rủi ro:

- Cấu hình thiếu tạm thời có thể làm service unavailable.
- Cần thông báo lỗi rõ và quy trình cấu hình đầy đủ.

### Chính sách B — Fallback

Khi remote không được bật, dùng local/no-op implementation.

Ưu điểm:

- Có thể giữ ứng dụng hoạt động khi tính năng phụ là optional.
- Phù hợp với mode offline hoặc dev/test.

Rủi ro:

- Có thể che lỗi production nếu fallback không đáp ứng yêu cầu.
- Có thể khiến hệ thống báo thành công nhưng không thực hiện side effect mong muốn.

Test cần ghi rõ policy. Ví dụ có một `NoOpNotificationChannel` cho optional notifications nhưng không dùng local fake sender làm fallback trong hệ thống đòi hỏi gửi thông báo bắt buộc.

Một cấu hình không nên “tự động chọn cái gì đó” khi không biết nghiệp vụ yêu cầu gì.

## 43. Kiểm thử với @ConditionalOnExpression và phức hợp conditions

Một số project sử dụng conditions phức hợp:

```java
@Bean
@Profile("prod & cloud")
@ConditionalOnProperty(
    prefix = "integration.notifications",
    name = "enabled",
    havingValue = "true"
)
NotificationChannel remoteChannel() {
    return new RemoteNotificationChannel();
}
```

Để bean được đăng ký, **cả** profile expression và property condition phải match.

Tạo ma trận:

| Active profiles | enabled | Remote expected |
|---|---|---|
| `prod,cloud` | true | Có |
| `prod` | true | Không |
| `cloud` | true | Không |
| `prod,cloud` | false | Không |
| `prod,cloud` | missing | Không |
| `prod,cloud,maintenance` | true | Có nếu không có điều kiện phủ định maintenance |

Đừng nghĩ annotation `@Profile("prod & cloud")` là SpEL. Nó dùng Spring profile-expression grammar (`&`, `|`, `!`). `@ConditionalOnExpression` là một điều kiện khác, dựa trên expression và có các rủi ro/semantics riêng.

Với nhiều nhánh, test từng tổ hợp được chọn theo risk thay vì chỉ happy path.

## 44. Khi bean thiếu vì package scanning

Không phải mọi bean vắng mặt đều do profile hoặc property.

Ví dụ application main class ở:

```text
com.example.orders.OrdersApplication
```

nhưng service nằm ở:

```text
com.another.team.NotificationService
```

Nếu component scan mặc định chỉ bao phủ package của main class và các package con, service ở package ngoài có thể không được phát hiện.

Khi test `ApplicationContextRunner.withUserConfiguration(...)`, bạn có thể thêm configuration thủ công nên test pass, nhưng full application vẫn không scan đúng.

Phải kiểm tra:

1. Bean được tạo bởi `@Bean` hay `@Component`?
2. Configuration có được import/scan?
3. Có `@Profile` hoặc `@Conditional...` không?
4. Test context load những classes nào?
5. Production application scan những package nào?

Có thể thêm một integration test `@SpringBootTest` tải main application configuration để xác nhận bean thực sự tồn tại khi chạy theo cách triển khai.

## 45. Khi property có mà bean vẫn sai

Một pipeline debug hợp lý:

```text
Property source
       │
       ▼
Spring Environment
       │
       ├── Profile conditions
       │
       ├── ConditionalOnProperty
       │
       └── ConfigurationProperties binder
       │
       ▼
Bean definitions
       │
       ▼
Dependency injection
       │
       ▼
Implementation được consumer sử dụng
```

Nếu kết quả sai, hãy hỏi lần lượt:

- Property được đặt đúng tên và đúng nguồn chưa?
- Có một nguồn ưu tiên cao hơn ghi đè không?
- Profile thực sự active trong context chưa?
- Điều kiện `havingValue`/`matchIfMissing` có đúng contract không?
- Configuration class có được đăng ký không?
- Có nhiều candidate beans và `@Primary`/`@Qualifier` ảnh hưởng không?
- Consumer có được inject bean thật hay một mock/test override?
- Test đang chạy trên context giống production hay một slice hẹp?

Dò từ input tới output thường nhanh hơn việc đoán Spring “chọn sai” chỉ từ một exception.

## 46. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| Test xác nhận profile active nhưng bean không tồn tại | Configuration chưa được scan/import, hoặc condition khác không match | Kiểm tra ApplicationContext và bean definitions |
| Dev test pass nhưng prod chọn local | Biểu thức profile quá rộng hoặc cấu hình prod không được nạp | Test prod với property thực tế |
| Hai implementation cùng được tạo | Các expressions chồng lấp | Thiết kế condition loại trừ nhau hoặc dùng qualifier/primary |
| `NoUniqueBeanDefinitionException` | Nhiều beans cùng type, consumer cần một | Test count và injection resolution |
| `NoSuchBeanDefinitionException` trong prod | Không condition nào match | Xác định fail-fast hay fallback được yêu cầu |
| Property false vẫn tạo bean | `havingValue`/mặc định condition bị hiểu sai | Test true/false/missing riêng |
| `@ActiveProfiles("prod & cloud")` không hoạt động như mong đợi | Đây không phải cách kích hoạt hai tên profile | Dùng `@ActiveProfiles({"prod", "cloud"})` |
| `@Profile({"dev","test"})` không cần cả hai | Mảng có OR semantics | Dùng `@Profile("dev & test")` cho AND |
| Test với `System.setProperty` không cập nhật bean | Context đã được cache và created | Tách context/test class hoặc dùng ContextRunner |
| Test slice không thấy service | Slice không load mọi component | Dùng `@SpringBootTest` hoặc explicit context runner |
| Mock làm mất implementation thật | Bean override che selection | Không mock bean đang được kiểm thử |
| `@Value` property có, nhưng configprops không thấy | `configprops` chỉ phản ánh properties beans tương ứng | Test injection point hoặc Environment |
| YAML profile không được nạp | Sai active profiles, file name hoặc config-data loading context | Kiểm tra Boot startup context và property sources |
| Lỗi chuyển Duration | Property không đúng format hoặc converter thiếu | Test binding failure và format |
| Test cục bộ pass, production fail | Khác dependency, classpath, profile, env, scanned modules | Bổ sung integration test của main app |
| Test chậm bất thường | Quá nhiều `@SpringBootTest`/`@DirtiesContext` | Dùng ApplicationContextRunner cho ma trận cấu hình |

## 47. Quy trình thực hành để thiết kế bộ test

Một quy trình có thể áp dụng khi thêm một configuration có nhiều implementations:

1. Viết **contract**: service nào cần interface nào và khi nào phải có implementation.
2. Vẽ ma trận profile/property, bao gồm missing và mixed-profile.
3. Thiết kế conditions loại trừ nhau hoặc xác định rõ resolution khi nhiều beans cùng tồn tại.
4. Viết `ApplicationContextRunner` tests cho từng dòng của ma trận.
5. Assert **bean count**, concrete type/name và behavior khi phù hợp.
6. Thêm test dự kiến startup failure nếu thiếu bean là lỗi triển khai.
7. Thêm test `@ConfigurationProperties` binding/validation nếu selection phụ thuộc typed config.
8. Thêm một vài `@SpringBootTest` cho integration wiring của main application.
9. Tránh mock đúng bean mà bạn đang muốn kiểm tra selection.
10. Kiểm tra profile-specific YAML và test property precedence khi có ảnh hưởng thực tế.
11. Giữ test deterministic, tránh phụ thuộc hệ thống ngoài nếu bài test chỉ nhằm kiểm tra condition.
12. Khi thất bại, thu hẹp bằng Environment/ConditionEvaluationReport và bean inventory thay vì đổi ngẫu nhiên annotation.

## 48. Bài tập thực hành

### Bài tập A — Hai implementations theo profile

Tạo `PaymentGateway` với `FakePaymentGateway` và `RemotePaymentGateway`. Dùng `@Profile("!prod")` và `@Profile("prod")`. Viết hai test `@SpringBootTest` có `@ActiveProfiles("dev")` và `@ActiveProfiles("prod")`, rồi xác nhận concrete type của bean.

### Bài tập B — Thêm một property gate

Chỉ tạo remote gateway nếu `payment.remote.enabled=true`. Test cả true, false và missing khi profile prod active. Đặt kỳ vọng fail-fast hoặc không tạo bean theo contract.

### Bài tập C — Test ma trận với ApplicationContextRunner

Tạo một `ApplicationContextRunner` chung cho configuration, dùng `withInitializer(...)` để thay active profiles và `withPropertyValues(...)` để thay flags. Assert count/type cho mọi dòng của bảng quyết định.

### Bài tập D — Profile expression

Tạo bean chỉ có với `@Profile("(dev | staging) & cloud")`. Kiểm tra với `dev`, `dev,cloud`, `staging,cloud` và `prod,cloud`. Giải thích vì sao `@ActiveProfiles({"dev","cloud"})` khác với truyền một chuỗi `"dev & cloud"`.

### Bài tập E — @Primary và @Qualifier

Đăng ký hai beans cùng interface và một bean `@Primary`. Test rằng cả hai tồn tại nhưng consumer mặc định nhận primary. Sau đó dùng `@Qualifier` cho consumer khác và xác nhận implementation còn lại.

### Bài tập F — @ConditionalOnMissingBean

Tạo auto-configuration cung cấp default `Clock` nếu ứng dụng chưa có clock. Test trạng thái thiếu bean và trạng thái user-defined clock. Xác nhận default configuration back off khi user bean có mặt.

### Bài tập G — @ConfigurationProperties

Bind `integration.client.timeout=5s` vào `Duration` và `max-attempts=3` vào `int`. Test giá trị đúng, property missing, malformed Duration và negative attempts khi có validation.

### Bài tập H — Dynamic property

Tạo một test server/container có port động; dùng `@DynamicPropertySource` cung cấp endpoint URL cho Spring test context. Giải thích vì sao không hard-code port và vì sao supplier cần có vòng đời phù hợp.

### Bài tập I — Context caching

Viết hai test methods dùng chung `@SpringBootTest` context, thử đổi Java system property giữa methods. Quan sát vì sao bean configuration không tự được rebuild và sửa bộ test bằng các context độc lập.

### Bài tập J — Test slice

Tạo `@WebMvcTest` cho controller có dependency service. Quan sát service không tự được load theo slice. Đề xuất test phù hợp để kiểm tra HTTP contract và test khác để kiểm tra profile/property selection.

### Bài tập K — Fallback hay fail-fast

Trong production nếu flag remote thiếu, so sánh hai giải pháp: dùng local fallback hoặc fail-fast. Chọn behavior hợp lý với một giao dịch quan trọng, rồi viết test thể hiện quyết định.

### Bài tập L — Debug một lựa chọn sai

Giả sử bean remote xuất hiện khi `dev` active. Đặt giả thuyết về `@Profile`, property condition, scanning, duplicate bean declaration và mock override. Xây test kiểm tra từ Environment đến ApplicationContext để tìm nguyên nhân.

## 49. Tổng kết

1. **Kiểm thử profile** không dừng ở việc đọc active profile names: phải chứng minh bean phù hợp được đăng ký hoặc bị loại.
2. **`@ActiveProfiles`** kích hoạt các tên profile trong Spring Test context; nó không phải profile-expression parser.
3. **`@Profile("dev & cloud")`** dùng AND, còn **`@Profile({"dev","cloud"})`** dùng OR.
4. **`@SpringBootTest(properties=...)`** và `@TestPropertySource` cung cấp test-specific properties.
5. **`ApplicationContextRunner`** phù hợp để kiểm tra nhanh nhiều tổ hợp profile/property và điều kiện đăng ký bean.
6. Với context runner, có thể đặt active profiles trực tiếp qua initializer để diễn đạt rõ test scenario.
7. **`@ConditionalOnProperty`** cần được test ít nhất các trường hợp true, false và missing, đặc biệt khi `havingValue`/`matchIfMissing` có ý nghĩa.
8. **Bean selection** nên được xác nhận bằng count, name, type và behavior, không chỉ bằng việc Environment có một key.
9. Khi có **`@Primary`** hoặc **`@Qualifier`**, kiểm tra bean consumer thật sự nhận, không chỉ đếm beans.
10. **`@ConditionalOnMissingBean`** giúp default configuration rút lui khi có user implementation; thứ tự cấu hình cần được hiểu và test.
11. **`@ConfigurationProperties`** cần được test cả binding thành typed fields và validation khi thích hợp.
12. **`@DynamicPropertySource`** giúp cung cấp giá trị do test resource tạo ra, nhưng không làm context tự rebind sau khi được refresh.
13. **Context caching** giúp test nhanh hơn, nhưng làm cách đổi `System.setProperty` giữa các methods không đáng tin để kiểm tra bean registration.
14. **Mock và test slices** có thể rất hữu ích nhưng có thể che logic lựa chọn implementation đang cần test.
15. **Fail-fast và fallback** là hai chính sách khác nhau; test phải phản ánh yêu cầu nghiệp vụ.
16. Các điều kiện Spring được đánh giá trong quá trình xây dựng context; thay đổi runtime property không tự đổi implementation đang được inject.
17. Một bộ test tốt kết hợp **test hẹp nhiều tổ hợp** với **một vài integration tests thật** để chứng minh configuration được load đúng từ main app.
18. Khi kết quả sai, điều tra theo thứ tự: profile/property nguồn → condition → bean definitions → dependency injection → behavior.

**Tư duy cốt lõi:** bài kiểm thử cấu hình đáng tin cậy phải trả lời **“Với tập profile và property này, Spring sẽ tạo đúng bao nhiêu bean, chọn implementation nào cho consumer và điều gì xảy ra khi điều kiện không hợp lệ?”** Trả lời được ba câu hỏi này giúp bạn bắt lỗi cấu hình trước khi chúng xuất hiện trong deployment thực tế.
