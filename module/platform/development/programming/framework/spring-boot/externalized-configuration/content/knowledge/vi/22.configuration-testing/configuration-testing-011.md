# Cô lập biến môi trường, System properties và trạng thái dùng chung giữa các test

> **Chủ đề:** Spring Boot Externalized Configuration  
> **Nhóm:** Kiểm thử cấu hình

## 1. Tại sao một test cấu hình có thể làm hỏng test khác?

Spring Boot đọc cấu hình từ nhiều nguồn: `application.yml`, `application.properties`, profile-specific files, file imported, biến môi trường hệ điều hành, Java system properties, JSON application properties, command-line arguments và property sources bổ sung bởi framework kiểm thử.

Trong một test, người lập trình thường muốn thay đổi `client.timeout` hoặc `feature.enabled` để kiểm tra hai nhánh nghiệp vụ. Nhưng một số thao tác lại thay đổi **trạng thái toàn tiến trình JVM**, không chỉ dữ liệu của một test case. Nếu không phục hồi đúng cách hoặc chạy song song, test sau có thể thấy giá trị do test trước để lại.

Ví dụ nguy hiểm:

~~~java
@Test
void usesFastMode() {
    System.setProperty("demo.client.mode", "fast");
    // Kiểm tra nhánh fast...
}

@Test
void usesDefaultMode() {
    // Có thể vô tình đọc demo.client.mode=fast
    // từ test trước, không phải giá trị mặc định.
}
~~~

Khi chạy mỗi test riêng, cả hai có thể pass. Khi chạy cả suite, test `usesDefaultMode` thất bại vì nhận `fast`. Nếu test execution chạy song song, giá trị có thể thay đổi ngay khi một test khác khởi tạo bean.

Đây gọi là **test interference** hoặc **shared-state leakage**: một case ảnh hưởng tới input hoặc trạng thái mà case khác đang sử dụng. Với cấu hình, lỗi đặc biệt khó nhận ra vì `Environment` kết hợp nhiều nguồn có ưu tiên khác nhau và một bean đã bind thường không tự cập nhật sau khi property source đổi.

### Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Phân biệt phạm vi của OS environment, Java system properties, Spring `Environment` và test property sources.
2. Hiểu tại sao `System.setProperty` là mutation JVM-wide và cách restore đúng trạng thái gốc.
3. Biết cách sử dụng `ApplicationContextRunner`, `@SpringBootTest(properties)`, `@TestPropertySource` và `@ActiveProfiles` để tránh sửa global state.
4. Hiểu `@DynamicPropertySource`, vòng đời tài nguyên và rủi ro của Spring TestContext cache.
5. Áp dụng `@ResourceLock` hoặc tách process khi thực sự cần thao tác global state.
6. Cô lập static fields, mutable singleton beans, mock servers, databases, testcontainers, clocks và files.
7. Kiểm tra precedence có chủ đích mà không phụ thuộc biến môi trường trên laptop hoặc CI.
8. Chẩn đoán những test chỉ thất bại khi chạy toàn suite hoặc khi parallel execution.
9. Giữ secret thật ngoài test resources và logs.

## 2. Bản đồ các loại trạng thái dùng chung

| Dữ liệu hoặc công cụ | Phạm vi thông thường | Rủi ro đối với test khác | Chiến lược |
| --- | --- | --- | --- |
| `System.getenv` | Environment của process | Các test cùng JVM thấy cùng nguồn env | Inject qua Spring/test source hoặc tạo process riêng |
| `System.getProperties` | JVM-wide mutable map | Test khác có thể đọc giá trị bị thay đổi | Tránh sửa; nếu cần, lưu/restore và serialize |
| `@SpringBootTest(properties)` | Test ApplicationContext | Có thể reuse context theo cache key | Giá trị tường minh cho test context |
| `@TestPropertySource` | Test context | Cache có thể reuse bean trong context | Khai báo nguồn riêng, cleanup state |
| `ApplicationContextRunner` | Context tạo bởi mỗi lần `run` | Ít rủi ro nếu app không truy cập globals | Dùng cho binding và auto-configuration tests |
| `MockEnvironment` | Java object trong test | Chỉ khi object bị chia sẻ | Tạo object mới per test |
| `@DynamicPropertySource` | Test context + supplier | Context cache và resource lifecycle | Quản lý tài nguyên động đúng vòng đời |
| Static field | JVM/classloader | Nhiễm trạng thái hoặc race | Tránh mutable static hoặc reset/lock |
| Singleton Spring bean | ApplicationContext | Bị chia sẻ khi context cache reuse | Reset, recreate context khi cần |
| Database/container | Tài nguyên bên ngoài JVM | Dữ liệu và kết nối chia sẻ | Transaction/cleanup/schema riêng |
| Mock HTTP server | Port và server process | Port collision, state sót lại | Dynamic port, close đúng lifecycle |
| Tệp test | Filesystem | Đụng cùng đường dẫn | `@TempDir`, unique filenames |
| Timezone/Locale/default clock | Global hoặc instance | Kết quả phụ thuộc máy chạy | Inject `Clock`, tránh đổi global defaults |

Nguyên tắc là chọn phạm vi nhỏ nhất để cung cấp input của test. Nếu muốn hai giá trị khác nhau cho cùng một key, nên tạo **hai context với nguồn riêng** hơn là sửa một JVM property chung giữa những test có thể chạy đồng thời.

## 3. OS environment, JVM System properties và Spring Environment

### 3.1. OS environment variables

Ví dụ chạy ứng dụng:

~~~bash
export DEMO_CLIENT_TIMEOUT=5s
java -jar app.jar
~~~

Trong Java:

~~~java
String timeout = System.getenv("DEMO_CLIENT_TIMEOUT");
~~~

Environment được cấp khi process được tạo. Java **không có API chuẩn, an toàn, di động** để sửa biến môi trường của chính JVM như sửa một `HashMap` thông thường.

Một số thư viện dùng reflection hoặc kỹ thuật phụ thuộc implementation để thay `System.getenv`, nhưng cách này có thể bị cấm bởi Java module encapsulation, không bảo đảm nhất quán giữa JDK và dễ xung đột với parallel tests. Không nên dựa vào nó như cách mặc định để kiểm thử.

### 3.2. JVM System properties

Có thể cấp bằng JVM option:

~~~bash
java -Ddemo.client.timeout=5s -jar app.jar
~~~

Hoặc sửa khi chạy:

~~~java
System.setProperty("demo.client.timeout", "5s");
String value = System.getProperty("demo.client.timeout");
~~~

`System.properties` là trạng thái dùng chung của JVM. Tất cả các tests và threads trong cùng process có thể thấy cùng key/value. Khi test dùng `System.setProperty`, nó không chỉ thiết lập một bản cấu hình cho riêng `ApplicationContext` của test.

### 3.3. Spring Environment

Spring `Environment` có nhiều `PropertySource` và áp dụng precedence:

~~~java
import org.springframework.core.env.Environment;

public class ClientConfigService {
    private final Environment env;

    public ClientConfigService(Environment env) {
        this.env = env;
    }

    public String timeout() {
        return env.getProperty("demo.client.timeout");
    }
}
~~~

Một test Spring có thể đưa một property source dành riêng cho context, làm `env.getProperty` trả `2s` trong khi `System.getProperty("demo.client.timeout")` vẫn là `5s`. Đây không phải lỗi: hai API có nguồn và phạm vi khác nhau.

### 3.4. Direct System.getenv bỏ qua nguồn test

Giả sử:

~~~java
String mode = System.getenv("DEMO_MODE");
~~~

Test:

~~~java
@SpringBootTest(properties = "demo.mode=test")
class ModeTest {}
~~~

Annotation làm Spring biết `demo.mode=test`. Nó **không sửa `System.getenv("DEMO_MODE")`**. Nếu production code vẫn gọi `System.getenv` trực tiếp, nó có thể trả dữ liệu từ CI hoặc máy developer bất chấp giá trị test.

Để dễ test, nên đưa cấu hình vào một `@ConfigurationProperties` bean hoặc inject `Environment` rồi truyền vào service. Khi đó test có thể kiểm soát nguồn mà không can thiệp tới environment của OS process.

## 4. Dùng @ConfigurationProperties để tách logic khỏi nguồn cấu hình

Ví dụ record cho Spring Boot 3 và Java 17+:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "demo.client")
public record DemoClientProperties(
        @DefaultValue("3s") Duration timeout,
        @DefaultValue("false") boolean enabled,
        @DefaultValue("2") int retries
) {}
~~~

Business service dùng typed object:

~~~java
package com.example.demo.service;

import com.example.demo.config.DemoClientProperties;

public class ClientPolicyService {

    private final DemoClientProperties config;

    public ClientPolicyService(DemoClientProperties config) {
        this.config = config;
    }

    public boolean shouldRetry(int currentAttempt) {
        return config.enabled()
                && currentAttempt < config.retries();
    }
}
~~~

Một unit test không cần môi trường Spring:

~~~java
@Test
void policyDoesNotRetryWhenDisabled() {
    DemoClientProperties config =
            new DemoClientProperties(
                    Duration.ofSeconds(3), false, 2
            );

    ClientPolicyService service =
            new ClientPolicyService(config);

    assertThat(service.shouldRetry(1)).isFalse();
}
~~~

Test không cần tạo JVM property hoặc OS environment variable. Đối với unit logic, đây thường là mức cô lập tốt nhất.

### 4.1. Test binding riêng với test nghiệp vụ

Có hai câu hỏi khác nhau:

- Binder có chuyển `demo.client.timeout=3s` thành `Duration.ofSeconds(3)` đúng không?
- Service có dùng thuộc tính `enabled=false` để quyết định retry đúng không?

Câu đầu cần test binding. Câu sau có thể dùng object trực tiếp. Gộp cả hai thành một `@SpringBootTest` lớn thường làm test chậm, phụ thuộc nhiều trạng thái bên ngoài và khó chẩn đoán hơn.

## 5. System.setProperty: lưu và phục hồi đúng

Khi bắt buộc phải test mã legacy đọc `System.getProperty` trực tiếp, hãy restore **đúng trạng thái gốc**.

~~~java
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class TemporaryPropertyTest {

    @Test
    void readsTemporaryValue() {
        String key = "demo.client.timeout";
        String previous = System.getProperty(key);

        try {
            System.setProperty(key, "2s");
            assertThat(System.getProperty(key)).isEqualTo("2s");
        } finally {
            if (previous == null) {
                System.clearProperty(key);
            } else {
                System.setProperty(key, previous);
            }
        }
    }
}
~~~

Nếu ban đầu key không tồn tại, phải `clearProperty`. Nếu nó đã có `5s`, phải restore `5s`. Luôn gọi `System.clearProperty` ở `@AfterEach` có thể xóa đi cấu hình hợp lệ mà một test khác hoặc JVM launcher đã cung cấp.

### 5.1. Cleanup vẫn chưa giải quyết parallel race

Ví dụ:

~~~text
Test A: save previous value
Test A: set demo.client.timeout = 2s
          Test B: read demo.client.timeout -> 2s
Test A: restore previous value
~~~

Test B đã đọc nhầm giá trị giữa lúc A đang thực thi. `finally` chỉ khôi phục **sau scope**, không làm property riêng tư cho từng thread.

Vì vậy, nếu có thể, tránh global mutations hoàn toàn. Nếu không thể, cần chạy tuần tự những test liên quan hoặc dùng cơ chế khóa tài nguyên mà **tất cả** tests chạm vào resource đều tuân thủ.

### 5.2. Helper AutoCloseable giảm lỗi teardown

~~~java
final class SystemPropertyScope implements AutoCloseable {

    private final String key;
    private final String previous;

    private SystemPropertyScope(String key, String nextValue) {
        this.key = key;
        this.previous = System.getProperty(key);
        System.setProperty(key, nextValue);
    }

    static SystemPropertyScope set(String key, String value) {
        return new SystemPropertyScope(key, value);
    }

    @Override
    public void close() {
        if (previous == null) {
            System.clearProperty(key);
        } else {
            System.setProperty(key, previous);
        }
    }
}
~~~

Dùng try-with-resources:

~~~java
@Test
void usesScopedSystemProperty() {
    try (SystemPropertyScope ignored =
                 SystemPropertyScope.set("legacy.mode", "test")) {
        assertThat(System.getProperty("legacy.mode"))
                .isEqualTo("test");
    }
}
~~~

Utility giảm lỗi quên cleanup nhưng không giải quyết race giữa hai threads. Không sử dụng trong parallel suites nếu không có chính sách serializing truy cập global property.

## 6. JUnit ResourceLock khi có global state

JUnit Jupiter có cơ chế `@ResourceLock` để các tests khai báo chung một resource không truy cập xung đột khi parallel execution được bật:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

@ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE
)
class LegacySystemPropertiesTest {

    @Test
    void testLegacyReader() {
        String previous = System.getProperty("legacy.mode");
        try {
            System.setProperty("legacy.mode", "test");
            // Kiểm tra logic legacy...
        } finally {
            if (previous == null) {
                System.clearProperty("legacy.mode");
            } else {
                System.setProperty("legacy.mode", previous);
            }
        }
    }
}
~~~

### 6.1. ResourceLock không phải phép màu

- Nó điều phối các tests có khai báo resource lock phù hợp trong engine của JUnit.
- Test khác không khai báo lock vẫn có thể đọc/sửa key ở thời điểm không phù hợp.
- Background thread hoặc third-party tool không tự tuân theo lock.
- Lock không tự restore giá trị; `finally` vẫn cần thiết.
- Nếu khóa ở phạm vi quá rộng, test suite chậm vì phải chạy tuần tự.

`@Isolated` cũng có thể dùng cho những test classes không nên chạy đồng thời với test classes khác theo mô hình JUnit, nhưng vẫn phải quản lý teardown đúng.

### 6.2. Không dùng ThreadLocal để giả lập System properties

`System.getProperty` không tự đọc từ một `ThreadLocal`. Nếu code dưới test gọi API toàn JVM, đặt một biến ThreadLocal trong test không làm API đó đổi behavior.

Cách bền hơn là refactor service để nhận `ConfigurationProvider` hoặc typed properties theo dependency injection; chỉ để test process-wide cho code buộc phải kiểm tra chính hành vi JVM.

## 7. ApplicationContextRunner: cô lập test binding trong các context nhỏ

Spring Boot có `ApplicationContextRunner` để tạo context mới theo từng case, đặc biệt phù hợp khi cần test `@ConfigurationProperties`, auto-configuration và conditional beans.

Ví dụ:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.client")
public record ClientProperties(
        Duration timeout,
        int retries
) {}
~~~

Test:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.junit.jupiter.api.Test;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ClientPropertiesBindingTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void bindsFastConfiguration() {
        runner.withPropertyValues(
                "demo.client.timeout=1s",
                "demo.client.retries=2"
        ).run(context -> {
            ClientProperties properties =
                    context.getBean(ClientProperties.class);

            assertThat(properties.timeout())
                    .isEqualTo(Duration.ofSeconds(1));
            assertThat(properties.retries()).isEqualTo(2);
        });
    }

    @Test
    void bindsSlowConfiguration() {
        runner.withPropertyValues(
                "demo.client.timeout=10s",
                "demo.client.retries=5"
        ).run(context -> {
            ClientProperties properties =
                    context.getBean(ClientProperties.class);

            assertThat(properties.timeout())
                    .isEqualTo(Duration.ofSeconds(10));
            assertThat(properties.retries()).isEqualTo(5);
        });
    }
}
~~~

Hai test dùng các `ApplicationContext` khác nhau do runner tạo cho từng lần `run`. Chúng không cần `System.setProperty`.

### 7.1. Lưu ý về runner nền

`withPropertyValues` trả ra một runner được cấu hình với các property. Nên dùng nó như một biến thể dành cho test case thay vì tạo một global mutable registry.

Nếu runner nền đã có `demo.client.timeout=3s`, một test muốn kiểm tra “thiếu timeout” phải dùng runner **không cấp timeout từ đầu**. Không thể diễn giải “test không override timeout” là “không có timeout”.

### 7.2. Runner không xóa static state của code dưới test

Nếu một bean trong context gọi `System.setProperty` hoặc ghi vào static cache, những side effects này vẫn có thể còn sau khi context đóng. Mô hình runner là một công cụ tốt để cô lập **Spring configuration scope**, không phải sandbox hoàn toàn của JVM.

## 8. @SpringBootTest(properties): input tường minh cho integration test

Đối với test cần khởi động application context đầy đủ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "demo.client.timeout=2s",
    "demo.client.retries=4"
})
class ClientIntegrationTest {

    @Autowired
    ClientProperties properties;

    @Test
    void usesTestValues() {
        assertThat(properties.retries()).isEqualTo(4);
    }
}
~~~

`@SpringBootTest(properties)` đưa những giá trị vào nguồn property của context kiểm thử. Nó thường có ưu tiên cao so với config data thông thường. Test có input rõ ràng, không phụ thuộc việc developer đã export biến gì trước khi chạy.

### 8.1. Một test property không sửa System.getenv

Ngay cả khi test chỉ định `demo.client.timeout=2s`, lời gọi `System.getenv("DEMO_CLIENT_TIMEOUT")` vẫn tra cứu OS process environment. Nếu một class trực tiếp gọi API đó, cần thiết kế abstraction phù hợp hoặc test trong process riêng.

### 8.2. Không cần mở toàn bộ ứng dụng cho mọi testcase

Một `@SpringBootTest` có thể khởi tạo database pools, message listeners, schedulers và nhiều auto-configurations ngoài phạm vi đang kiểm tra. Điều đó khiến test chậm và tạo thêm shared state. Nếu chỉ muốn test Binder, sử dụng `ApplicationContextRunner` hoặc `MockEnvironment` thường phù hợp hơn.

### 8.3. Test class có input khác nên được nhận diện đúng

Spring TestContext framework dùng nhiều thành phần để xác định context cache key, trong đó có các test property sources. Test classes với cấu hình khác nhau có thể có cache keys khác. Nhưng không nên giả định mỗi test method chắc chắn tạo một context mới hoặc mỗi test class có một context duy nhất; cơ chế cache tồn tại để tái sử dụng khi cấu hình tương thích.

## 9. @TestPropertySource và @ActiveProfiles

### 9.1. Inline test properties

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest
@TestPropertySource(properties = {
    "demo.client.timeout=4s",
    "demo.client.retries=3"
})
class ClientTestSourceIT {}
~~~

`@TestPropertySource` của Spring TestContext bổ sung nguồn test properties cho context. Đây là phương án phù hợp để không phải mutate global System properties.

### 9.2. Đọc file .properties dành cho test

~~~java
@TestPropertySource(
        locations = "classpath:/test-config/client.properties"
)
~~~

File `src/test/resources/test-config/client.properties`:

~~~properties
demo.client.timeout=4s
demo.client.retries=3
~~~

Test file giúp nhóm những giá trị dùng chung theo một module. Tuy nhiên, tránh dùng một file chung bị test khác sửa trong lúc chạy.

### 9.3. Không dùng TestPropertySource để nạp YAML nhiều document theo Boot

Một nhầm lẫn phổ biến:

~~~java
@TestPropertySource(
        locations = "classpath:/application-test.yml"
)
~~~

`@TestPropertySource` không tương đương pipeline Spring Boot Config Data cho YAML và profile-activated documents. Nếu cần test logic `application-test.yml`, `spring.config.activate.on-profile` hay `spring.config.import`, dùng một Spring Boot test context thực sự nạp Config Data theo các quy tắc tương ứng.

### 9.4. Chọn test profile

~~~java
import org.springframework.test.context.ActiveProfiles;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@ActiveProfiles("test")
class CatalogWithTestProfileIT {}
~~~

Khi profile `test` active, Boot có thể nạp `application-test.yml` ở config locations phù hợp.

`@ActiveProfiles` không tự xóa mọi property khác. Nếu key chưa được cấp ở file test, nó vẫn có thể lấy từ `application.yml`, imported config, OS environment hoặc một property source khác theo precedence.

### 9.5. Không gộp quá nhiều lớp override

Một test có cả `@SpringBootTest(properties)`, `@TestPropertySource`, `@DynamicPropertySource` và nhiều profiles có thể khó đọc. Chỉ tạo nhiều nguồn trùng key khi mục tiêu thực sự là test precedence; nếu không, chọn nguồn đơn giản và rõ ý nghĩa nhất.

## 10. MockEnvironment và Binder: kiểm thử precedence trong phạm vi object

Khi muốn kiểm tra quy tắc nhiều nguồn mà không phụ thuộc CI env, dùng `MockEnvironment` và `MapPropertySource`.

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.MapPropertySource;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class PrecedenceTest {

    @Test
    void higherPriorityPropertyWins() {
        MockEnvironment environment = new MockEnvironment();

        environment.getPropertySources().addLast(
                new MapPropertySource(
                        "defaults",
                        Map.of(
                                "lesson.labels.owner", "core",
                                "lesson.labels.region", "global"
                        )
                )
        );

        environment.getPropertySources().addFirst(
                new MapPropertySource(
                        "overrides",
                        Map.of(
                                "lesson.labels.region", "apac",
                                "lesson.labels.stage", "test"
                        )
                )
        );

        Map<String, String> labels = Binder.get(environment)
                .bind(
                        "lesson.labels",
                        Bindable.mapOf(String.class, String.class)
                )
                .orElse(Map.of());

        assertThat(labels)
                .containsEntry("owner", "core")
                .containsEntry("region", "apac")
                .containsEntry("stage", "test");
    }
}
~~~

Ở đây:

- `MockEnvironment` là object mới trong test.
- `defaults` và `overrides` là các nguồn được kiểm soát.
- `addFirst` đặt override ở mức ưu tiên cao.
- Binder kết hợp map entries và lấy `region=apac`.
- Không cần sửa `System.getProperties` hoặc OS environment.

### 10.1. Đây không phải full Config Data integration test

Test trên xác minh property resolution và Binder với các nguồn giả lập. Nó không tự đọc file `application-prod.yml`, profile-activated documents hoặc config import. Nếu muốn kiểm tra **cách Spring Boot chọn và nạp file thật**, cần test sử dụng pipeline Config Data.

## 11. TestPropertyValues: một công cụ khác cho test scope

Spring Boot `TestPropertyValues` có thể tạo các nguồn property phục vụ kiểm thử.

~~~java
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.mock.env.MockEnvironment;

MockEnvironment environment = new MockEnvironment();

TestPropertyValues.of(
        "demo.client.timeout=3s",
        "demo.client.retries=2"
).applyTo(environment);
~~~

Cách này hữu ích khi bạn cần một `Environment` xác định trong test. Không tạo ra side effects JVM-wide giống `System.setProperty`.

### 11.1. Áp dụng trước khi bind

Nếu bean đã được bind từ một source trước đó, đưa property mới vào `Environment` không làm bean tự rebind. Test muốn kiểm tra cấu hình startup nên thêm nguồn **trước khi bean/context khởi tạo**.

### 11.2. Không chia sẻ một mutable Environment giữa tests

Nếu `MockEnvironment` nằm trong static field và nhiều test cùng add/remove `PropertySource`, bạn lại tạo shared state mới. Tạo mới mỗi test trừ khi thực sự cần tái sử dụng với lifecycle rõ ràng.

## 12. DynamicPropertySource: nguồn động cho Testcontainers và server ports

Một số giá trị chỉ được biết sau khi tạo tài nguyên, ví dụ cổng ngẫu nhiên của mock HTTP server hoặc JDBC URL của Testcontainers.

Spring Test có `@DynamicPropertySource`:

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

class DatabaseTestBase {

    static final String TEST_URL =
            "jdbc:postgresql://localhost:55432/demo";

    @DynamicPropertySource
    static void registerDatabaseUrl(
            DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> TEST_URL);
    }
}
~~~

Đây chỉ là minh họa supplier; URL cố định không bảo đảm có database thật. Trong integration test, URL nên được lấy từ container/server mà fixture tạo.

### 12.1. Dynamic source có precedence cao

Các property đăng ký bằng `@DynamicPropertySource` thường có precedence cao hơn `@TestPropertySource`, OS environment, JVM system properties và các nguồn thông thường. Nếu hai annotation cấp cùng `spring.datasource.url`, giá trị động có thể thắng.

Khi debug, cần kiểm tra **nguồn đang có hiệu lực**, không chỉ đọc một dòng trong `application-test.yml`.

### 12.2. Supplier có thể động nhưng client đã tạo không động

Một supplier có thể trả value mới trong lần tra cứu sau, nhưng DataSource hoặc HTTP client đã tạo có thể vẫn giữ thông tin cũ. Không nhầm **dynamic property lookup** với **automatic client reconfiguration**.

### 12.3. Dynamic method được kế thừa và context cache

Nếu các subclasses kế thừa cùng `@DynamicPropertySource` method nhưng cần giá trị dynamic khác nhau, Spring TestContext cache có thể tái sử dụng context không đúng kỳ vọng. Trong tình huống này, có thể dùng `@DirtiesContext` hoặc thiết kế context/resources sao cho giá trị và vòng đời tương ứng rõ ràng.

## 13. Testcontainers: chia sẻ container nhưng cô lập dữ liệu

Ví dụ Spring Boot test dùng PostgreSQL Testcontainers:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class DatabaseIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.datasource.url",
                POSTGRES::getJdbcUrl
        );
        registry.add(
                "spring.datasource.username",
                POSTGRES::getUsername
        );
        registry.add(
                "spring.datasource.password",
                POSTGRES::getPassword
        );
    }

    @Test
    void loadsContext() {
        // Test sẽ sử dụng DB được container cấp.
    }
}
~~~

Cần đúng dependencies, Docker/runtime và driver. Ví dụ cho thấy cách dùng lifecycle của container với Spring test properties.

### 13.1. Static container không có nghĩa database tự sạch

Container có thể được chia sẻ trong một test class; dữ liệu được insert từ test A có thể vẫn tồn tại khi test B chạy. Cần transaction rollback, cleanup scripts hoặc schema/database riêng, tùy yêu cầu.

### 13.2. Context cache và vòng đời container có thể không khớp

Nếu container dừng khi class A kết thúc nhưng Spring context của A còn trong TestContext cache, class B có thể vô tình tái sử dụng DataSource trỏ tới port đã đóng. Điều này tạo lỗi connection refused, không phải lỗi annotation `@DynamicPropertySource`.

Nên chọn một chính sách:

- Container sống cùng hoặc lâu hơn context liên quan.
- Context không được tái sử dụng sau khi container bị dừng.
- External data được reset giữa tests.
- Port/URL không hardcode nếu có thể dùng dynamic ports.

### 13.3. ServiceConnection cũng không loại bỏ shared state

Spring Boot có cơ chế `@ServiceConnection` trong những phiên bản được hỗ trợ để đưa connection details vào auto-configuration. Cách này có thể tiện hơn khai báo URL thủ công, nhưng vẫn phải quản lý container lifecycle và dữ liệu dùng chung.

## 14. Spring TestContext cache và các singleton mutable

`@SpringBootTest` thường tham gia cơ chế cache ApplicationContext của Spring TestContext. Một context có thể được dùng lại cho nhiều test methods hoặc classes khi cấu hình và cache key tương ứng.

### 14.1. Vì sao cache hữu ích?

Khởi động Spring Boot context có thể tốn thời gian: scan classes, load auto-configuration, tạo bean, khởi tạo clients, chuẩn bị schema. Dùng lại context giúp suite nhanh hơn.

### 14.2. Vì sao cache có thể gây rò rỉ?

Giả sử singleton bean:

~~~java
@Component
public class FeatureRegistry {

    private final Map<String, Boolean> flags =
            new ConcurrentHashMap<>();

    public void enable(String name) {
        flags.put(name, true);
    }

    public boolean enabled(String name) {
        return flags.getOrDefault(name, false);
    }

    public void clear() {
        flags.clear();
    }
}
~~~

Test A gọi `enable("beta")`. Test B, khi dùng lại context, có thể thấy `beta=true`. Việc cả hai đều dùng `@ActiveProfiles("test")` không đảm bảo bean được reset.

### 14.3. Khắc phục

- Reset state bằng fixture khi an toàn.
- Thiết kế service tránh mutable singleton test data.
- Dùng instance/fixture theo test.
- Khi context thực sự bị thay đổi không thể reset đáng tin cậy, dùng `@DirtiesContext`.

Ví dụ:

~~~java
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS
)
class MutatesApplicationContextIT {}
~~~

`@DirtiesContext` làm context bị loại khỏi cache theo chính sách annotation. Nó **không** tự xóa `System.properties`, static caches, database records hay file tạm. Cần cleanup những nguồn đó độc lập.

### 14.4. Không lạm dụng @DirtiesContext

Dirtied contexts phải khởi tạo lại, khiến suite chậm. Với những state nhỏ có thể reset, cleanup đúng thường tiết kiệm hơn. Tránh dùng `@DirtiesContext` như phản xạ cho mọi lỗi order-dependent mà chưa biết nguồn rò rỉ.

## 15. Khi cần kiểm tra System.getenv thật: child process

Nếu đề bài kiểm thử yêu cầu xác nhận ứng dụng xử lý **OS environment thực tế ở thời điểm process startup**, một child JVM có ranh giới cô lập rõ hơn reflection hack.

Ví dụ `ProcessBuilder`:

~~~java
import java.util.concurrent.TimeUnit;

public class ChildEnvironmentTestHelper {

    public static void runChild() throws Exception {
        ProcessBuilder builder =
                new ProcessBuilder("java", "-version");

        builder.environment().put(
                "DEMO_CLIENT_TIMEOUT",
                "2s"
        );
        builder.redirectErrorStream(true);

        Process process = builder.start();
        boolean exited = process.waitFor(
                30, TimeUnit.SECONDS
        );

        if (!exited) {
            process.destroyForcibly();
            throw new IllegalStateException(
                    "Child process exceeded timeout"
            );
        }
    }
}
~~~

`java -version` là lệnh minh họa cách cấp environment cho child; nó không kiểm thử Spring Boot Binder. Muốn test tích hợp thật, thay bằng một Java fixture hoặc Spring Boot app ở child process có thể đọc và báo **một giá trị demo không nhạy cảm**, sau đó kiểm tra exit code/output.

### 15.1. Lợi ích

- Child nhận môi trường trước khi JVM khởi động.
- `System.getenv` trong child có thể đọc giá trị thử nghiệm.
- Static state và System properties của child không ảnh hưởng parent JVM.
- Hai test có thể tạo child processes với environment khác nhau.

### 15.2. Chi phí

- Process startup tốn thời gian.
- Phải thu output và ngăn process treo.
- Cần timeout, cleanup và tránh port collision.
- Không đưa secret thật vào command-line args hoặc logs.
- Nên chọn thư mục tạm và cổng riêng cho mỗi process khi parallel.

Chỉ dùng process-level test khi thật sự cần kiểm chứng OS environment hoặc bootstrap lifecycle. Với unit test của Spring property binding, runner hoặc MockEnvironment thường là đủ.

## 16. Static fields và những trạng thái khác ngoài Environment

Rò rỉ trạng thái không chỉ đến từ cấu hình.

### 16.1. Static cache

~~~java
public final class GlobalCache {
    public static final Map<String, String> VALUES =
            new ConcurrentHashMap<>();
}
~~~

Nếu test A lưu `VALUES.put("mode","fast")`, test B có thể đọc lại giá trị đó. Cleanup ở `@AfterEach` hữu ích khi test chạy tuần tự, nhưng khi parallel, clear của A có thể xóa dữ liệu đang dùng bởi B.

Giải pháp đúng là **không chia sẻ mutable global fixture** hoặc phân vùng state bằng key/session riêng, kèm isolation được kiểm chứng.

### 16.2. Đồng hồ và timezone

Code gọi `Instant.now()` phụ thuộc đồng hồ hệ thống; các test có thể fail khi thời điểm đổi ngày. Thay vì sửa timezone JVM:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneOffset.UTC
);
~~~

Inject `Clock`:

~~~java
public class ExpiryService {

    private final Clock clock;

    public ExpiryService(Clock clock) {
        this.clock = clock;
    }

    public boolean expired(Instant expiresAt) {
        return !Instant.now(clock).isBefore(expiresAt);
    }
}
~~~

Test có input thời gian cố định mà không phải đổi `TimeZone.setDefault` toàn process.

### 16.3. Locale và các default toàn JVM

`Locale.setDefault`, `TimeZone.setDefault` và một số cấu hình bảo mật/SSL là trạng thái global. Khi test buộc sửa chúng, phải restore và kiểm soát concurrency. Đừng sử dụng global defaults khi logic có thể nhận Locale/ZoneId/Clock như dependency.

### 16.4. Async threads và schedulers

Một test có thể khởi chạy async task rồi kết thúc trước khi task hoàn tất. Task tiếp tục sửa cache hoặc gửi message khiến test sau gặp side effects. Cần await/cancel/cleanup theo đúng lifecycle; đóng context chưa chắc đủ nếu code tự tạo threads không được quản lý.

## 17. Filesystem: dùng TempDir và tránh đường dẫn dùng chung

Không nên để nhiều tests ghi vào `./config/application.yml` thật hoặc một file `/tmp/test-config.yml` cố định.

JUnit `@TempDir`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.assertj.core.api.Assertions.assertThat;

class ConfigFileTest {

    @TempDir
    Path tempDir;

    @Test
    void createsIndependentFile() throws Exception {
        Path properties = tempDir.resolve(
                "client-test.properties"
        );

        Files.writeString(
                properties,
                "demo.client.timeout=2s\n"
        );

        assertThat(Files.readString(properties))
                .contains("demo.client.timeout=2s");
    }
}
~~~

### 17.1. Config Data location phải cấp đúng thời điểm

Nếu test muốn Spring Boot nạp một file bên ngoài thông qua `spring.config.location`, property này được dùng ở giai đoạn sớm của config processing. Cần cấp location đúng trước khi Spring Boot xác định Config Data files, không phải sửa System properties tùy ý sau khi context đã khởi tạo.

Khi cần test bootstrap thực sự, có thể dựng Spring Boot process riêng với working directory/temp config được chỉ định rõ.

### 17.2. Không coi file tồn tại là bằng chứng đã bind

Một test assert file có chuỗi `timeout=10s` không chứng minh Spring Boot dùng giá trị ấy. Còn phải kiểm tra file được nạp, profile hoạt động, precedence và bean/client đã nhận giá trị cuối.

## 18. Database, queue và mock server: nguồn nhiễm state ngoài JVM

### 18.1. Database

Hai test cùng dùng schema:

~~~java
@Test
void createsRecord() {
    repository.save(new Customer("alice"));
}

@Test
void expectsEmptyDatabase() {
    assertThat(repository.count()).isZero();
}
~~~

Nếu bản ghi từ test đầu còn tồn tại, test thứ hai sẽ fail. Có thể dùng transaction rollback, cleanup SQL, schema riêng hoặc database/container riêng tùy phạm vi test.

Lưu ý: `@Transactional` trên test không tự rollback các tác động từ async threads, remote systems hoặc tác vụ có transaction khác. Hãy kiểm tra ranh giới giao dịch thật.

### 18.2. Message broker

Một topic/queue dùng chung có thể làm test B nhận message của A. Cần consumer group riêng, correlation IDs, cleanup hoặc tài nguyên test độc lập.

### 18.3. HTTP mock server

Một mock server sử dụng port cố định có thể va chạm khi suite chạy song song hoặc hai CI jobs cùng chạy. Dùng dynamic port và đưa URL vào test context qua `@DynamicPropertySource` hoặc test property source được tạo đúng thời điểm.

### 18.4. External state không bị reset bởi @DirtiesContext

Một context đóng không có nghĩa PostgreSQL tables bị truncate, Kafka topic bị xóa hoặc mock server state tự reset. Mỗi tài nguyên bên ngoài cần lifecycle và cleanup riêng.

## 19. Chọn tầng test phù hợp để cô lập tốt nhất

| Tầng | Mục đích | Công cụ | Ưu điểm |
| --- | --- | --- | --- |
| Unit | Kiểm tra service với config đã xác định | Tạo typed object và inject trực tiếp | Nhanh, không phụ thuộc JVM globals |
| Binder | Chuyển kiểu, Map/List, relaxed binding | `MockEnvironment` + `Binder` | Kiểm soát property sources tường minh |
| Small context | Auto-configuration, conditional beans | `ApplicationContextRunner` | Bật context nhỏ, cô lập các case |
| Integration context | Profile, bean graph, startup | `@SpringBootTest`, test sources | Kiểm tra phối hợp Spring Boot |
| External integration | DB, queue, HTTP provider | Testcontainers, mocks | Kiểm tra kết nối thật có kiểm soát |
| Process/bootstrap | OS env và JVM flags thật | ProcessBuilder hoặc test launcher | Tách JVM/state mạnh |

Đừng khởi động cả application context khi chỉ cần xác nhận một method `shouldRetry`. Ngược lại, nếu mục tiêu là test profile activation của file `application-prod.yml`, MockEnvironment đơn thuần chưa chứng minh Boot đã nạp đúng Config Data.

## 20. Test có điều kiện và validation khi thiếu property

Ví dụ:

~~~java
import java.net.URI;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "partner.client")
@Validated
public record PartnerClientProperties(
        @NotNull URI endpoint
) {}
~~~

Nếu test muốn xác nhận thiếu `partner.client.endpoint` làm startup fail, phải dựng context **không có property đó từ bất kỳ test source hay nguồn nền có hiệu lực nào**. Một test class có `@SpringBootTest(properties = "partner.client.endpoint=...")` sẽ che mất trường hợp missing.

Với `ApplicationContextRunner`, có thể tạo một runner không cấp endpoint, đăng ký `PartnerClientProperties` cùng Bean Validation infrastructure phù hợp, rồi assert context failure.

Đây là lý do test inputs phải được khai báo riêng và rõ; không nên dựa vào thứ tự của test trước đã xóa hoặc giữ property nào.

### 20.1. Những case thường cần test

- Property bắt buộc thiếu hoàn toàn.
- Property có chuỗi rỗng.
- Sai kiểu, ví dụ `timeout=not-a-duration`.
- Giá trị không đạt constraint như retries âm.
- Nested group thiếu và `@NotNull`/`@Valid`.
- Profile-specific override.
- Dynamic property source từ container.
- Cùng key ở hai sources với precedence xác định.

Mỗi case nên thiết kế nguồn đầu vào đủ để kết luận. Không cần thay đổi global JVM property cho một test validation thông thường.

## 21. Khi test chỉ fail trên CI hoặc fail theo thứ tự

Các triệu chứng thường gặp:

| Triệu chứng | Nguyên nhân đáng nghi | Cách điều tra |
| --- | --- | --- |
| Test riêng pass, full suite fail | Global mutation hoặc context cache | Tìm System.setProperty, static fields, singleton state |
| Chạy lại đảo thứ tự thấy kết quả khác | Test trước để lại dữ liệu | Restore, reset fixture và external state |
| Chỉ fail khi parallel | Race trên globals, DB, port hoặc file | Lock/serialization, tách tài nguyên |
| Chỉ fail ở CI | Env vars, locale, timezone, working directory khác | Kiểm soát test inputs |
| DynamicPropertySource trả URL cũ | Resource đã dừng, context cache reuse | Điều chỉnh lifecycle, dirties context nếu cần |
| @ActiveProfiles("test") nhưng property bất ngờ | Nguồn khác có precedence cao hơn | Kiểm tra effective property sources |
| Context mới pass, cached context fail | Mutable singleton state | Reset bean hoặc dùng context riêng |
| @DirtiesContext không giải quyết | Global/static/DB state chưa reset | Cleanup đúng phạm vi |
| Test file cấu hình bị sửa | Shared filename và nhiều writers | @TempDir, tránh modify source |
| Chỉ fail khi suite chạy nhiều JVM forks | Port/database/file system state chia sẻ | Unique namespaces, dynamic ports |
| Secret thật xuất hiện trong logs | Dump env/system properties hoặc record toString | Chỉ log key không nhạy cảm |
| Chạy sau một test async thất bại | Background task chưa dừng | Await/cancel và quản lý scheduler |

### Quy trình điều tra

1. Tái hiện bằng cách chạy test riêng.
2. Chạy cùng một nhóm test nghi ngờ.
3. Kiểm tra thứ tự và parallel execution mode.
4. Tìm `System.setProperty`, `clearProperty`, `setProperties` trong code.
5. Tìm static mutable state, singleton beans và context cache.
6. Kiểm tra `@DynamicPropertySource` suppliers và container/server lifecycle.
7. Kiểm tra test fixtures, files, database và message queues.
8. Xác định các input phụ thuộc OS/CI không được khai báo.
9. Chuyển cấu hình qua context-local sources hoặc object injection.
10. Chạy lại suite với parallel/order khác để xác nhận không còn phụ thuộc ngầm.

Không dump toàn bộ `System.getenv()` hoặc `System.getProperties()` vào CI logs để tìm lỗi: nhiều môi trường chứa credentials và thông tin nhạy cảm.

## 22. Anti-patterns và cách thay thế

### Anti-pattern A — setProperty trong BeforeAll rồi quên teardown

~~~java
@BeforeAll
static void setUp() {
    System.setProperty("demo.mode", "test");
}
~~~

Biến toàn JVM bị ảnh hưởng từ lúc setup cho đến khi ai đó sửa lại. Thay bằng `@SpringBootTest(properties="demo.mode=test")` nếu cần Spring context, hoặc restore đúng trạng thái gốc với lock nếu bắt buộc.

### Anti-pattern B — AfterEach luôn clearProperty

~~~java
@AfterEach
void cleanup() {
    System.clearProperty("demo.mode");
}
~~~

Nếu property đã tồn tại trước test với giá trị có chủ đích, cách cleanup này xóa luôn giá trị đó. Cần lưu/restore chính xác.

### Anti-pattern C — giả định Mutable JavaBean sẽ tự cập nhật

Một class `@ConfigurationProperties` có setter không tự được rebind chỉ vì test sửa file hoặc Spring Environment. Muốn giá trị khác, dựng context mới hoặc thiết kế refresh rõ ràng.

### Anti-pattern D — sửa OS env bằng reflection

Cách này không di động và gây race. Dùng test sources hoặc một JVM riêng khi cần OS env thật.

### Anti-pattern E — static final đọc getenv quá sớm

~~~java
static final String MODE = System.getenv("DEMO_MODE");
~~~

Giá trị được chụp khi class load. Sau đó test property source trong Spring không thay đổi nó. Nên refactor sang configuration injection.

### Anti-pattern F — Testcontainers dùng chung mà dữ liệu không được reset

Một container database có thể còn records của test trước. Hãy cleanup hoặc tách schema/test IDs; metadata Spring context không làm DB sạch.

### Anti-pattern G — @DirtiesContext ở khắp nơi

Dirtied contexts gây tốn chi phí khởi tạo lại và không xử lý globals. Chỉ sử dụng khi context thực sự bị làm bẩn.

### Anti-pattern H — cố định port cho nhiều test servers

Dynamic port và dynamic property registration thường phù hợp hơn, nhất là trong CI chạy song song.

## 23. Checklist trước khi bật parallel execution

- [ ] Không có `System.setProperty` thiếu restore.
- [ ] Tests chạm global properties dùng chung một chính sách ResourceLock/serialization.
- [ ] Không sửa `System.getenv` bằng reflection.
- [ ] Test inputs được khai báo bằng context property sources khi phù hợp.
- [ ] `@ActiveProfiles` và file test-specific được kiểm soát.
- [ ] ApplicationContext cache không tái sử dụng singleton bị mutate ngoài ý muốn.
- [ ] `@DynamicPropertySource` và container lifecycle tương thích.
- [ ] Database và message queues có chính sách cleanup hoặc phân vùng.
- [ ] Mock servers dùng dynamic ports.
- [ ] Tệp test dùng `@TempDir`, tránh ghi source files.
- [ ] Timezone, Locale và Clock không phụ thuộc vào máy chạy.
- [ ] Không có background task chạy tiếp sau test rồi gây side effects.
- [ ] Những fixture có cleanup vẫn hoạt động khi assertion thất bại.
- [ ] Không in credentials qua env dumps, logs hay exceptions.
- [ ] Test process-level environment được tách JVM khi thực sự cần.
- [ ] Test hoàn toàn có thể chạy độc lập mà không đòi một test khác chạy trước.
- [ ] Test có cơ chế phát hiện cấu hình sai ngay khi khởi động.

## 24. Bài tập thực hành

### Bài tập A — System property bị rò rỉ

Viết test A set `lesson.mode=fast` bằng `System.setProperty` và test B kỳ vọng giá trị default. Chạy riêng và chạy cùng suite. Sau đó áp dụng `try/finally`. Giải thích vì sao cleanup không đủ khi parallel execution.

### Bài tập B — Cấu hình cô lập với ApplicationContextRunner

Tạo record `LessonProperties(Duration timeout,int retries)`. Dùng hai calls `withPropertyValues` với `timeout=1s` và `timeout=10s`. Assert hai context bind đúng và không sửa global property.

### Bài tập C — TestPropertySource và ActiveProfiles

Tạo `application.yml`, `application-test.yml` và một tệp `test-overrides.properties`. Dùng `@ActiveProfiles("test")` và `@TestPropertySource` để dự đoán giá trị cuối, kiểm tra precedence của các nguồn.

### Bài tập D — Binder với hai nguồn

Dùng `MockEnvironment` và hai `MapPropertySource`. Nguồn thấp cấp `lesson.labels.owner=core` và `region=global`; nguồn cao cấp `region=apac` và `stage=test`. Bind `Map<String,String>`. Xác nhận ba keys đúng.

### Bài tập E — DynamicPropertySource

Chạy mock HTTP server có port ngẫu nhiên. Đăng ký `lesson.api.base-url` bằng dynamic property supplier. Test URL được bind. Sau đó dừng server và phân tích vì sao context cache reuse có thể làm test khác trỏ port đã chết.

### Bài tập F — Child JVM

Dùng `ProcessBuilder.environment().put("LESSON_MODE","test")` để chạy một Java fixture child đọc `System.getenv`. Chứng minh parent JVM environment không thay đổi.

### Bài tập G — Static state

Tạo một static Map và hai tests có thao tác put/get. Thử chạy parallel. Chọn giải pháp tách state theo test, reset fixture, khóa hoặc refactor bỏ static global.

### Bài tập H — Cached Spring singleton

Tạo bean đếm số lần gọi. Viết hai integration tests cùng dùng context cache. Dự đoán rủi ro state. Giải quyết bằng cleanup hoặc context riêng và phân tích chi phí.

### Bài tập I — Testcontainers database

Chạy PostgreSQL container test. Test A insert row, test B mong database sạch. Dùng rollback hoặc cleanup để tránh phụ thuộc thứ tự, sau đó bật parallel với chiến lược tách dữ liệu phù hợp.

### Bài tập J — Kiểm tra cấu hình thiếu

Tạo `@ConfigurationProperties` có endpoint bắt buộc. Viết một context runner không cấp endpoint và mong validation fail; viết case khác cấp đúng endpoint. Không dựa vào một property được set bởi test trước.

## 25. Runbook khi test chỉ fail trên CI

1. Ghi nhận JDK, OS, test runner, chế độ parallel và số JVM forks.
2. Chạy test thất bại độc lập.
3. Chạy test trong nhóm nhỏ với những tests có thể ảnh hưởng.
4. Kiểm tra giá trị input cấu hình **không nhạy cảm**.
5. Tìm global mutation, static caches và mutable singleton beans.
6. Kiểm tra TestContext cache và property sources.
7. Kiểm tra Testcontainers, mock server, ports và lifecycle.
8. Kiểm tra database state, file tạm và working directory.
9. Kiểm tra Clock/Locale/Timezone.
10. Thay mutation bằng per-test property source khi có thể.
11. Dùng ResourceLock/serialization cho code không thể loại bỏ global state.
12. Chạy lại với thứ tự khác/parallel và xác nhận tính tái lập.
13. Không in toàn bộ environment hoặc secrets vào log để debug.

## 26. Tổng kết

- **OS environment là input của process**; test Spring property sources không tự sửa `System.getenv`.
- **JVM System properties là mutable shared state**; `System.setProperty` ảnh hưởng mọi tests trong cùng JVM.
- **Restore bằng finally** bảo vệ sau khi test hoàn tất nhưng không loại bỏ race trong lúc chạy song song.
- **`ApplicationContextRunner`, `MockEnvironment`, `@SpringBootTest(properties)` và `@TestPropertySource`** thường là những cách cô lập input cấu hình rõ ràng hơn.
- **`@ActiveProfiles`** giúp chọn profile nhưng không làm các nguồn khác biến mất.
- **`@DynamicPropertySource`** cần quản lý vòng đời của container/mock server và context cache.
- **`@DirtiesContext`** chỉ quản lý Spring context; không reset Java globals, file, DB hay queue ngoài context.
- **Static fields, singleton state, filesystem, timezone, ports và external services** đều có thể khiến suite bị ảnh hưởng lẫn nhau.
- **Child process** là ranh giới rõ khi cần test OS environment thật tại startup.
- Mục tiêu là test tái lập được khi chạy riêng, chạy cả suite, chạy song song và trên CI, trong khi không tiết lộ secret.

## Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, precedence và binding.
- [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest` và test contexts.
- [Spring Boot Reference — Test Utilities](https://docs.spring.io/spring-boot/reference/testing/test-utilities.html): `ApplicationContextRunner` và test helpers.
- [Spring Framework Reference — Property Sources in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html): `@TestPropertySource`.
- [Spring Framework Reference — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): `@DynamicPropertySource`.
- [Spring Framework Reference — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): cache keys và context reuse.
- [Spring Framework Reference — @DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html): loại context khỏi cache.
- [JUnit Jupiter — Parallel Execution](https://docs.junit.org/current/user-guide/#writing-tests-parallel-execution): `@ResourceLock` và `@Isolated`.
- [JUnit Jupiter — @TempDir](https://docs.junit.org/current/user-guide/#writing-tests-built-in-extensions-TempDirectory): quản lý thư mục tạm cho test.
- [Testcontainers Java](https://java.testcontainers.org/): container lifecycle, dynamic ports và integration testing.
