# withPropertyValues để thiết lập từng trường hợp thuộc tính

> **Spring Boot Auto Configuration → Kiểm thử độc lập.** Bài học tập trung vào cách dùng ApplicationContextRunner.withPropertyValues(...) để tạo những lần khởi chạy context với bộ thuộc tính riêng. Ta sẽ kiểm thử điều kiện bật/tắt auto-configuration, giá trị mặc định khi thiếu property, binding vào @ConfigurationProperties, kiểu dữ liệu lồng nhau, trường hợp giá trị sai, và bean do ứng dụng thay thế. Ví dụ sử dụng Java 17+, Maven và Spring Boot 3.3.13.

## 1. Vì sao phải thiết lập property riêng cho từng test?

Auto-configuration thường thay đổi hành vi dựa trên cấu hình môi trường. Một starter có thể tạo bean khi:

- Người dùng bật một feature bằng property.
- Một dependency có trên classpath.
- Một bean nền đã tồn tại.
- Ứng dụng chưa cung cấp bean thay thế.
- Một số giá trị cấu hình đã được bind thành công.

Nếu chỉ chạy một test với một cấu hình cố định, ta chưa biết các trường hợp còn lại có hoạt động đúng không. Ví dụ:
- Khi property không tồn tại, bean có nên được tạo không?
- Khi property là false, auto-configuration có thực sự dừng không?
- Khi property là true, các giá trị URL, timeout và số lần thử có được bind đúng không?
- Nếu giá trị timeout sai định dạng, context có báo lỗi rõ ràng không?
- Nếu ứng dụng cung cấp bean riêng, cấu hình mặc định có nhường không?

Spring Boot cung cấp ApplicationContextRunner để tạo một context nhỏ cho từng kịch bản. Phương thức withPropertyValues(...) cho phép truyền các cặp key=value ngay trong test, không cần sửa application.properties hoặc biến môi trường của máy.

Mỗi lần gọi run(...) tạo một ApplicationContext mới, thực hiện refresh, chạy callback kiểm thử và đóng context sau callback. Vì vậy, mỗi test có thể chọn bộ property riêng và tránh rò rỉ trạng thái giữa các trường hợp.

## 2. withPropertyValues(...) hoạt động thế nào?

Cú pháp cơ bản:

~~~java
new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(
                NoticeAutoConfiguration.class
        ))
        .withPropertyValues(
                "acme.notice.enabled=true",
                "acme.notice.timeout=750ms"
        )
        .run(context -> {
            // assertions
        });
~~~

Mỗi phần tử là một chuỗi theo dạng:

~~~text
property.name=value
~~~

Ví dụ:

~~~java
.withPropertyValues(
        "acme.notice.enabled=true",
        "acme.notice.endpoint=https://api.example.test/v1",
        "acme.notice.timeout=750ms",
        "acme.notice.max-attempts=5"
)
~~~

Spring Boot đưa các giá trị này vào Environment của context kiểm thử. Khi auto-configuration được đánh giá hoặc bean cấu hình được bind, chúng được đọc như property thông thường.

Một số quy tắc:
- Mỗi property là một chuỗi riêng trong varargs.
- Dùng đúng tên property công khai mà thư viện hỗ trợ.
- Phân cách tên và giá trị bằng dấu bằng đầu tiên.
- Dùng dạng kebab-case cho tên property để thống nhất với cấu hình Spring Boot.
- Giá trị vẫn là chuỗi khi được truyền vào runner; Binder hoặc condition chuyển đổi/so sánh theo contract tương ứng.
- Không cần tạo application.properties chỉ để kiểm tra một giá trị.
- Không ghi secret thật vào test; dùng giá trị giả, không nhạy cảm.

### 2.1. Thiết lập một property

~~~java
runner.withPropertyValues("acme.notice.enabled=true")
        .run(context -> {
            assertThat(context).hasSingleBean(NoticeClient.class);
        });
~~~

### 2.2. Thiết lập nhiều property cùng lúc

~~~java
runner.withPropertyValues(
        "acme.notice.enabled=true",
        "acme.notice.timeout=1s",
        "acme.notice.max-attempts=4"
).run(context -> {
    // kiểm tra toàn bộ cấu hình trong cùng một context
});
~~~

Các giá trị cùng nằm trong một context nên có thể kiểm tra cả điều kiện và binding cùng lúc. Ví dụ, enabled quyết định auto-configuration có áp dụng; timeout và max-attempts được bind vào bean properties nếu cấu hình đã được bật.

### 2.3. Không khai báo property cũng là một trường hợp cần test

~~~java
runner.run(context -> {
    assertThat(context).doesNotHaveBean(NoticeClient.class);
});
~~~

Không gọi withPropertyValues(...) nghĩa là runner không thêm các property đó. Đây là cách kiểm tra hành vi khi người dùng chưa cấu hình gì.

Không nên thay trường hợp thiếu property bằng chuỗi "null". Giá trị chuỗi null, giá trị rỗng và property không tồn tại là các trạng thái khác nhau.

## 3. withPropertyValues và @ConditionalOnProperty

Một auto-configuration thường dùng @ConditionalOnProperty để bật/tắt bean theo cấu hình.

Ví dụ:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.notice",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class NoticeAutoConfiguration {
    // bean definitions
}
~~~

Với khai báo trên:

| Property trong test | Điều kiện | Kết quả |
| --- | --- | --- |
| Không có acme.notice.enabled | matchIfMissing=false | Không match |
| acme.notice.enabled=true | havingValue=true | Match |
| acme.notice.enabled=false | havingValue=true | Không match |
| acme.notice.enabled=anything-else | havingValue=true | Không match |

Khi khai báo havingValue="true", condition yêu cầu giá trị property bằng true theo cách so sánh không phân biệt chữ hoa/thường. Trong cấu hình thực tế, nên dùng true/false chữ thường để dễ đọc.

Nếu bỏ havingValue, quy tắc mặc định của @ConditionalOnProperty là property phải có mặt và giá trị không bằng false. Đây là khác biệt quan trọng: một property có giá trị "maybe" có thể được coi là match khi không chỉ định havingValue, trong khi havingValue="true" yêu cầu giá trị true rõ ràng.

### 3.1. Kiểm thử khi property không tồn tại

~~~java
@Test
void missingEnabledPropertyDoesNotCreateClient() {
    runner.run(context -> {
        assertThat(context).doesNotHaveBean(NoticeClient.class);
    });
}
~~~

Test này xác nhận matchIfMissing=false. Nếu ai đó đổi cấu hình thành matchIfMissing=true, test sẽ thất bại và báo thay đổi contract mặc định.

### 3.2. Kiểm thử khi bật feature

~~~java
@Test
void trueEnablesNoticeClient() {
    runner.withPropertyValues("acme.notice.enabled=true")
            .run(context -> {
                assertThat(context).hasSingleBean(NoticeClient.class);
            });
}
~~~

### 3.3. Kiểm thử khi tắt feature

~~~java
@Test
void falseDisablesNoticeClient() {
    runner.withPropertyValues("acme.notice.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(NoticeClient.class);
            });
}
~~~

Hai test true/false nên tách riêng. Khi một test thất bại, tên test cho biết ngay kịch bản nào bị sai.

### 3.4. Property có nhiều điều kiện

Nếu auto-configuration cần nhiều property cùng bật:

~~~java
@ConditionalOnProperty(
        prefix = "acme.notice",
        name = {"enabled", "audit-enabled"},
        havingValue = "true",
        matchIfMissing = false
)
~~~

Mặc định, tất cả tên trong danh sách phải đáp ứng điều kiện. Test nên bao gồm đủ tổ hợp:

~~~java
@Test
void bothFlagsMustBeTrue() {
    runner.withPropertyValues(
            "acme.notice.enabled=true",
            "acme.notice.audit-enabled=true"
    ).run(context ->
            assertThat(context).hasSingleBean(NoticeClient.class)
    );

    runner.withPropertyValues(
            "acme.notice.enabled=true",
            "acme.notice.audit-enabled=false"
    ).run(context ->
            assertThat(context).doesNotHaveBean(NoticeClient.class)
    );

    runner.withPropertyValues(
            "acme.notice.enabled=false",
            "acme.notice.audit-enabled=true"
    ).run(context ->
            assertThat(context).doesNotHaveBean(NoticeClient.class)
    );
}
~~~

Mỗi lần run là một context mới. Không có property từ lần đầu tự động được mang sang lần tiếp theo.

## 4. Phân biệt condition và configuration properties binding

Hai cơ chế này giải quyết hai việc khác nhau:

- @ConditionalOnProperty quyết định một cấu hình hoặc bean có được đăng ký hay không.
- @ConfigurationProperties đọc và chuyển các property thành object có kiểu dữ liệu.

Ví dụ:

~~~properties
acme.notice.enabled=true
acme.notice.endpoint=https://api.example.test/v1
acme.notice.timeout=750ms
acme.notice.max-attempts=5
~~~

enabled điều khiển điều kiện. endpoint, timeout và max-attempts cung cấp cấu hình cho bean.

Một test tốt cần xác nhận cả hai:
1. Bean có xuất hiện khi condition match không?
2. Bean nhận đúng các giá trị được bind không?

Nếu chỉ assert hasSingleBean, ta biết bean tồn tại nhưng chưa chứng minh cấu hình đã được áp dụng.

## 5. Ví dụ dự án hoàn chỉnh

Lab này tạo auto-configuration cho NoticeClient. Bean chỉ xuất hiện khi acme.notice.enabled=true. Các property khác được bind vào NoticeProperties và dùng để tạo client.

### 5.1. Cấu trúc thư mục

~~~text
notice-property-tests/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/notice/
    │   │   ├── NoticeClient.java
    │   │   └── autoconfigure/
    │   │       ├── NoticeProperties.java
    │   │       └── NoticeAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/acme/notice/autoconfigure/
            └── NoticeAutoConfigurationPropertyTest.java
~~~

### 5.2. pom.xml

Tệp pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme.notice</groupId>
    <artifactId>notice-property-tests</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

spring-boot-autoconfigure cung cấp annotation và cơ chế auto-configuration. spring-boot-starter-test cung cấp JUnit 5, AssertJ và Spring Boot test support, bao gồm ApplicationContextRunner.

### 5.3. NoticeClient.java

Tệp src/main/java/com/acme/notice/NoticeClient.java:

~~~java
package com.acme.notice;

import java.net.URI;
import java.time.Duration;

public record NoticeClient(
        URI endpoint,
        Duration timeout,
        int maxAttempts) {

    public String send(String message) {
        return "sent:" + message;
    }
}
~~~

Client giữ ba giá trị đã cấu hình. Phương thức send trong lab trả kết quả xác định để test tập trung vào property binding; nó không thực hiện HTTP request thật.

### 5.4. NoticeProperties.java

Tệp src/main/java/com/acme/notice/autoconfigure/NoticeProperties.java:

~~~java
package com.acme.notice.autoconfigure;

import java.net.URI;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.notice")
public class NoticeProperties {

    private boolean enabled;
    private URI endpoint = URI.create("https://api.example.test/notice");
    private Duration timeout = Duration.ofSeconds(2);
    private int maxAttempts = 3;
    private List<String> tags = new ArrayList<>();
    private Map<String, String> headers = new LinkedHashMap<>();

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public Map<String, String> getHeaders() {
        return headers;
    }

    public void setHeaders(Map<String, String> headers) {
        this.headers = headers;
    }
}
~~~

Các giá trị khởi tạo là default:
- endpoint mặc định trỏ đến domain ví dụ.
- timeout mặc định là 2 giây.
- maxAttempts mặc định là 3.
- tags và headers mặc định là collection rỗng.

Không dùng endpoint ví dụ để gửi request thật. Đây chỉ là giá trị kiểm thử để quan sát Binder.

### 5.5. NoticeAutoConfiguration.java

Tệp src/main/java/com/acme/notice/autoconfigure/NoticeAutoConfiguration.java:

~~~java
package com.acme.notice.autoconfigure;

import com.acme.notice.NoticeClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.notice",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
@EnableConfigurationProperties(NoticeProperties.class)
public class NoticeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NoticeClient.class)
    NoticeClient noticeClient(NoticeProperties properties) {
        return new NoticeClient(
                properties.getEndpoint(),
                properties.getTimeout(),
                properties.getMaxAttempts()
        );
    }
}
~~~

Cấu hình này có hai lớp điều kiện:
- Điều kiện trên lớp yêu cầu enabled=true. Nếu thiếu hoặc false, cấu hình không áp dụng.
- Điều kiện trên bean cho phép ứng dụng tự cung cấp NoticeClient. Khi đã có bean phù hợp, factory method mặc định không đăng ký thêm bean.

@EnableConfigurationProperties đăng ký và bind NoticeProperties khi auto-configuration được áp dụng.

### 5.6. AutoConfiguration.imports

Tạo file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
com.acme.notice.autoconfigure.NoticeAutoConfiguration
~~~

File này cần thiết khi module được dùng như một auto-configuration JAR trong ứng dụng Spring Boot. Tuy nhiên, các test bên dưới dùng AutoConfigurations.of(NoticeAutoConfiguration.class), nghĩa là chúng nạp class cấu hình trực tiếp để tập trung kiểm tra property condition và binding. Cách test này **không kiểm chứng việc Boot phát hiện imports metadata trong JAR**; cần một consumer test hoặc test đóng gói riêng cho mục đích đó.

## 6. Viết test cho từng trường hợp property

Tệp src/test/java/com/acme/notice/autoconfigure/NoticeAutoConfigurationPropertyTest.java:

~~~java
package com.acme.notice.autoconfigure;

import java.net.URI;
import java.time.Duration;

import com.acme.notice.NoticeClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class NoticeAutoConfigurationPropertyTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            NoticeAutoConfiguration.class
                    ));

    @Test
    void missingEnabledPropertyDoesNotCreateClient() {
        runner.run(context -> {
            assertThat(context)
                    .doesNotHaveBean(NoticeClient.class);

            assertThat(context)
                    .doesNotHaveBean(NoticeProperties.class);
        });
    }

    @Test
    void enabledPropertyCreatesClientAndBindsValues() {
        runner.withPropertyValues(
                "acme.notice.enabled=true",
                "acme.notice.endpoint=https://api.example.test/v1",
                "acme.notice.timeout=750ms",
                "acme.notice.max-attempts=5",
                "acme.notice.tags[0]=billing",
                "acme.notice.tags[1]=priority",
                "acme.notice.headers[x-region]=apac"
        ).run(context -> {
            assertThat(context).hasSingleBean(NoticeClient.class);
            assertThat(context).hasSingleBean(NoticeProperties.class);

            NoticeProperties properties =
                    context.getBean(NoticeProperties.class);

            assertThat(properties.isEnabled()).isTrue();
            assertThat(properties.getEndpoint())
                    .isEqualTo(URI.create("https://api.example.test/v1"));
            assertThat(properties.getTimeout())
                    .isEqualTo(Duration.ofMillis(750));
            assertThat(properties.getMaxAttempts()).isEqualTo(5);
            assertThat(properties.getTags())
                    .containsExactly("billing", "priority");
            assertThat(properties.getHeaders())
                    .containsEntry("x-region", "apac");

            NoticeClient client = context.getBean(NoticeClient.class);
            assertThat(client.endpoint())
                    .isEqualTo(properties.getEndpoint());
            assertThat(client.timeout())
                    .isEqualTo(properties.getTimeout());
            assertThat(client.maxAttempts())
                    .isEqualTo(5);
            assertThat(client.send("hello"))
                    .isEqualTo("sent:hello");
        });
    }

    @Test
    void falsePropertyDoesNotCreateClient() {
        runner.withPropertyValues("acme.notice.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(NoticeClient.class);
                    assertThat(context)
                            .doesNotHaveBean(NoticeProperties.class);
                });
    }

    @Test
    void defaultValuesAreUsedWhenOnlyEnabledIsSet() {
        runner.withPropertyValues("acme.notice.enabled=true")
                .run(context -> {
                    NoticeProperties properties =
                            context.getBean(NoticeProperties.class);

                    assertThat(properties.getEndpoint())
                            .isEqualTo(
                                URI.create("https://api.example.test/notice")
                            );
                    assertThat(properties.getTimeout())
                            .isEqualTo(Duration.ofSeconds(2));
                    assertThat(properties.getMaxAttempts()).isEqualTo(3);
                    assertThat(properties.getTags()).isEmpty();
                    assertThat(properties.getHeaders()).isEmpty();
                });
    }

    @Test
    void userProvidedClientMakesAutoConfigurationBackOff() {
        NoticeClient customClient = new NoticeClient(
                URI.create("https://custom.example.test/notice"),
                Duration.ofMillis(100),
                1
        );

        runner.withPropertyValues("acme.notice.enabled=true")
                .withBean(NoticeClient.class, () -> customClient)
                .run(context -> {
                    assertThat(context).hasSingleBean(NoticeClient.class);
                    assertThat(context.getBean(NoticeClient.class))
                            .isSameAs(customClient);
                });
    }

    @Test
    void malformedDurationCausesContextStartupFailure() {
        runner.withPropertyValues(
                "acme.notice.enabled=true",
                "acme.notice.timeout=not-a-duration"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
        });
    }

    @Test
    void eachPropertyCaseUsesAnIndependentContext() {
        runner.withPropertyValues("acme.notice.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(NoticeClient.class)
                );

        runner.withPropertyValues("acme.notice.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(NoticeClient.class)
                );

        runner.run(context ->
                assertThat(context).doesNotHaveBean(NoticeClient.class)
        );
    }
}
~~~

Test class giữ một runner nền không có property. Mỗi test gọi withPropertyValues(...) để tạo một runner đã cấu hình cho kịch bản đó. Runner nền không bị thay đổi; các lần run độc lập nhau.

### 6.1. Test property bị thiếu

Test missingEnabledPropertyDoesNotCreateClient không truyền property nào. Kết quả mong đợi là không có NoticeClient và cũng không có NoticeProperties, vì condition nằm trên toàn lớp auto-configuration.

Nếu đổi matchIfMissing thành true, test này sẽ phát hiện hành vi mặc định đã thay đổi.

### 6.2. Test bật và binding nhiều kiểu dữ liệu

Test enabledPropertyCreatesClientAndBindsValues thiết lập nhiều property trong cùng một lần chạy:
- boolean: enabled=true.
- URI: endpoint.
- Duration: timeout=750ms.
- integer: max-attempts=5.
- List: tags[0], tags[1].
- Map: headers[x-region].

Binder chuyển các chuỗi thành kiểu Java tương ứng. Test kiểm tra cả object NoticeProperties lẫn NoticeClient được tạo từ object đó.

Cách này phát hiện lỗi tên property, lỗi conversion và lỗi factory method không sử dụng giá trị đã bind.

### 6.3. Test property false

Test falsePropertyDoesNotCreateClient bảo vệ hành vi tắt rõ ràng. Khi feature bị tắt, bean mặc định không xuất hiện.

Nếu cấu hình chỉ đặt condition trên factory method thay vì cả lớp, NoticeProperties có thể vẫn tồn tại. Trong lab này condition nằm trên lớp nên cả cấu hình properties cũng không được đăng ký.

### 6.4. Test default values

Người dùng có thể chỉ bật feature mà không khai báo mọi thuộc tính. Test defaultValuesAreUsedWhenOnlyEnabledIsSet xác nhận giá trị khởi tạo trong NoticeProperties được giữ lại.

Default value là một phần của API cấu hình công khai. Khi thay timeout mặc định hoặc số lần thử mặc định, test sẽ giúp phát hiện thay đổi hành vi có thể ảnh hưởng consumer.

### 6.5. Test bean do ứng dụng cung cấp

Test userProvidedClientMakesAutoConfigurationBackOff đưa một bean vào runner bằng withBean(...). Vì auto-configuration dùng @ConditionalOnMissingBean, bean mặc định không được tạo cạnh tranh.

Kiểm tra isSameAs xác nhận context trả đúng instance do test cung cấp. Đây là kiểm thử hợp đồng override, không chỉ kiểm tra bean count.

### 6.6. Test giá trị sai định dạng

Test malformedDurationCausesContextStartupFailure truyền một chuỗi không chuyển đổi được thành Duration. Vì NoticeProperties được đăng ký và bind khi context khởi động, context phải thất bại.

Trong test thật, hãy kiểm tra startup failure và nguyên nhân gốc nếu cần chẩn đoán cụ thể. Không nên phụ thuộc vào toàn bộ chuỗi thông báo exception vì wording có thể thay đổi theo phiên bản Binder.

### 6.7. Test tính độc lập giữa các lần chạy

Test eachPropertyCaseUsesAnIndependentContext chạy cùng runner nền ba lần:
1. enabled=true.
2. enabled=false.
3. Không có property.

Mỗi lần có kết quả riêng. Test này minh họa cách tái sử dụng runner mà không tái sử dụng ApplicationContext hoặc property source của lần trước.

## 7. Chạy test và đọc kết quả

Từ thư mục chứa pom.xml:

~~~bash
mvn clean test
~~~

Kết quả mong đợi là toàn bộ test trong NoticeAutoConfigurationPropertyTest thành công. Số test của class mẫu là 7.

Maven có thể in thêm thông tin thời gian, phiên bản plugin và tổng số test tùy môi trường. Không nên viết test dựa trên toàn bộ dòng log Maven; dùng assertion trong test làm bằng chứng chính.

Nếu test malformed duration thất bại vì context không báo lỗi, kiểm tra:
- NoticeProperties có được đăng ký bằng @EnableConfigurationProperties không?
- Property condition có match để cấu hình được áp dụng không?
- Test có thực sự gọi bean properties khiến binding diễn ra không?
- Property name có đúng prefix và field không?
- Kiểu field có hỗ trợ conversion mong muốn không?

## 8. Các dạng property thường gặp trong withPropertyValues

### 8.1. Boolean

~~~java
.withPropertyValues(
        "acme.notice.enabled=true",
        "acme.notice.audit-enabled=false"
)
~~~

Dùng boolean cho feature flag. Với @ConditionalOnProperty havingValue="true", chỉ bật rõ ràng bằng true. Không dùng các từ tùy ý như on, yes hoặc enabled nếu contract của thư viện chưa định nghĩa chúng.

### 8.2. Integer và decimal

~~~java
.withPropertyValues(
        "acme.notice.max-attempts=4",
        "acme.notice.failure-rate=0.25"
)
~~~

Binder chuyển đổi sang int, long, double hoặc kiểu số tương ứng. Test nên kiểm tra biên hợp lệ và giá trị không hợp lệ nếu thư viện có quy tắc validation.

### 8.3. Duration

~~~java
.withPropertyValues(
        "acme.notice.timeout=750ms",
        "acme.notice.idle-timeout=2s"
)
~~~

Spring Boot hỗ trợ bind Duration từ các dạng đơn vị như ns, us, ms, s, m, h và d. Dùng hậu tố đơn vị tường minh giúp test dễ đọc. Nếu dùng giá trị không có đơn vị, ý nghĩa có thể phụ thuộc cấu hình @DurationUnit hoặc quy ước của field; hãy ghi rõ trong tài liệu.

### 8.4. Data size

~~~java
.withPropertyValues(
        "acme.notice.buffer-size=16KB"
)
~~~

Với field kiểu DataSize, Binder có thể chuyển đổi các đơn vị như B, KB, MB và GB theo quy tắc Spring Boot. Test nên xác nhận giá trị byte thực tế, không chỉ kiểm tra chuỗi đầu vào.

### 8.5. URI và URL

~~~java
.withPropertyValues(
        "acme.notice.endpoint=https://api.example.test/v1"
)
~~~

Nếu field là URI, test kiểm tra giá trị URI sau conversion. Nếu field là String, Binder không tự bảo đảm URL hợp lệ; khi đó cần validate riêng.

### 8.6. List và array

~~~java
.withPropertyValues(
        "acme.notice.tags[0]=billing",
        "acme.notice.tags[1]=priority"
)
~~~

Indexed notation phù hợp khi test thứ tự phần tử. Có thể dùng chuỗi phân tách dấu phẩy cho một số kiểu binding, nhưng indexed notation rõ ràng hơn khi giá trị phần tử có thể chứa ký tự phân tách.

### 8.7. Map

~~~java
.withPropertyValues(
        "acme.notice.headers[x-region]=apac",
        "acme.notice.headers[x-client]=consumer-test"
)
~~~

Dạng ngoặc vuông giữ nguyên key có dấu gạch nối hoặc ký tự cần bảo toàn. Test nên kiểm tra cả key và value trong Map sau binding.

### 8.8. Nested properties

Với cấu trúc:

~~~java
public class RetryProperties {
    private int maxAttempts = 3;
    private Duration backoff = Duration.ofMillis(200);

    // getters and setters
}
~~~

và field retry trong NoticeProperties, có thể truyền:

~~~java
.withPropertyValues(
        "acme.notice.retry.max-attempts=5",
        "acme.notice.retry.backoff=500ms"
)
~~~

Dấu chấm biểu thị đường dẫn đến thuộc tính lồng nhau. Test cần xác nhận cả object con được tạo và giá trị bên trong được bind.

## 9. Kết hợp property condition và nhiều bean

Một auto-configuration có thể đăng ký nhiều bean với điều kiện khác nhau. Ví dụ:
- NoticeClient yêu cầu acme.notice.enabled=true.
- NoticeAuditPublisher yêu cầu acme.notice.audit.enabled=true và một bean AuditSink.
- NoticeMetricsBinder yêu cầu bean MeterRegistry.

Không nên gom mọi condition vào một lớp nếu các bean không cùng phụ thuộc. Nếu condition ở cấp lớp, một property có thể vô tình chặn toàn bộ bean.

Ví dụ cấu hình lồng:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.notice",
        name = "enabled",
        havingValue = "true"
)
public class NoticeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    NoticeClient noticeClient() {
        return new NoticeClient();
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "acme.notice.audit",
            name = "enabled",
            havingValue = "true"
    )
    static class AuditConfiguration {

        @Bean
        @ConditionalOnMissingBean
        NoticeAuditPublisher noticeAuditPublisher(AuditSink sink) {
            return new NoticeAuditPublisher(sink);
        }
    }
}
~~~

Có thể test từng tổ hợp:

~~~java
@Test
void auditRequiresBothCoreAndAuditFlags() {
    runner.withPropertyValues(
            "acme.notice.enabled=true",
            "acme.notice.audit.enabled=true"
    ).withBean(AuditSink.class, AuditSink::new)
     .run(context -> {
         assertThat(context).hasSingleBean(NoticeClient.class);
         assertThat(context).hasSingleBean(NoticeAuditPublisher.class);
     });

    runner.withPropertyValues(
            "acme.notice.enabled=true",
            "acme.notice.audit.enabled=false"
    ).withBean(AuditSink.class, AuditSink::new)
     .run(context -> {
         assertThat(context).hasSingleBean(NoticeClient.class);
         assertThat(context).doesNotHaveBean(NoticeAuditPublisher.class);
     });
}
~~~

Đây là ví dụ cấu trúc minh họa; các type AuditSink, NoticeAuditPublisher cần được định nghĩa trong dự án nếu muốn biên dịch test. Điểm chính là test từng tổ hợp flag và bean dependency, thay vì chỉ test trạng thái tất cả đều bật.

## 10. withPropertyValues so với các cách cung cấp property khác

| Cách | Phạm vi | Khi phù hợp |
| --- | --- | --- |
| ApplicationContextRunner.withPropertyValues | Một runner/context kiểm thử | Kiểm tra auto-configuration nhanh và cô lập |
| @SpringBootTest(properties = ...) | Spring Boot application context trong integration test | Kiểm tra ứng dụng rộng hơn với property riêng |
| @TestPropertySource | Test dùng Spring TestContext Framework | Cấu hình test qua annotation hoặc file property |
| @DynamicPropertySource | Đăng ký property động trong integration test | Giá trị được cấp từ Testcontainers hoặc tài nguyên khởi tạo lúc test |
| withSystemProperties | System properties trong runner | Kiểm tra hành vi phụ thuộc system property cụ thể |

Ví dụ với full application context:

~~~java
@SpringBootTest(properties = {
        "acme.notice.enabled=true",
        "acme.notice.timeout=500ms"
})
class NoticeApplicationTest {
}
~~~

Cách này kiểm tra ứng dụng đầy đủ hơn nhưng khởi tạo context nặng hơn. Với condition của một auto-configuration, ApplicationContextRunner thường nhanh và tập trung hơn.

Không dùng withPropertyValues để thay thế Testcontainers hoặc kiểm thử kết nối thật. Nó thiết lập cấu hình; nó không tạo database, broker hay HTTP server.

## 11. Cách tổ chức test để tránh lỗi và khó đọc

### 11.1. Mỗi test nên mô tả một kịch bản

Tên test nên nói rõ điều kiện và kết quả:
- missingEnabledPropertyDoesNotCreateClient
- trueEnablesNoticeClient
- falseDisablesNoticeClient
- customClientMakesAutoConfigurationBackOff
- malformedTimeoutFailsContext

Tránh gom mọi assertion vào một test khổng lồ. Khi một kịch bản thất bại, ta cần biết property nào và hành vi nào cần điều tra.

### 11.2. Tạo helper cho cấu hình lặp lại

Nếu nhiều test cần feature bật, có thể tạo helper:

~~~java
private ApplicationContextRunner enabledRunner() {
    return runner.withPropertyValues("acme.notice.enabled=true");
}
~~~

Sau đó:

~~~java
enabledRunner().run(context -> {
    assertThat(context).hasSingleBean(NoticeClient.class);
});
~~~

Helper chỉ nên gom cấu hình chung. Nếu mỗi test cần giá trị khác nhau, truyền property trực tiếp để kịch bản dễ nhìn.

### 11.3. Không thay đổi runner nền bằng trạng thái mutable tự tạo

ApplicationContextRunner được thiết kế theo phong cách fluent: các phương thức cấu hình trả về runner đã được cấu hình. Có thể giữ một runner nền rồi tạo biến thể cho từng test.

Không lưu ApplicationContext vào static field để dùng lại giữa test. Context cần được đóng sau callback; giữ lại reference có thể gây dùng bean sau shutdown hoặc làm test phụ thuộc thứ tự chạy.

### 11.4. Assertion cả presence và absence

Test condition nên xác nhận:
- Bean cần có xuất hiện đúng một lần.
- Bean không được phép xuất hiện thực sự vắng mặt.
- Bean thay thế là instance đúng.
- Properties đã bind có giá trị mong đợi.

Chỉ kiểm tra context không fail là chưa đủ. Một context có thể khởi động thành công nhưng auto-configuration không tạo bean nào do condition sai.

### 11.5. Kiểm tra lỗi cấu hình có chủ đích

Nếu property sai định dạng, test nên xác nhận context thất bại. Nếu giá trị hợp lệ nhưng ngoài phạm vi nghiệp vụ, có thể dùng Bean Validation hoặc validation trong constructor để từ chối cấu hình. Khi thêm validation, phải khai báo dependency cần thiết và kiểm thử thông báo/lỗi theo contract.

## 12. Những giới hạn và điểm cần cẩn thận

- ApplicationContextRunner thường dùng context không phải web; nếu cấu hình phụ thuộc Servlet hoặc Reactive web application type, dùng WebApplicationContextRunner hoặc ReactiveWebApplicationContextRunner tương ứng.
- AutoConfigurations.of(...) nạp class cấu hình trực tiếp. Nó không kiểm chứng file AutoConfiguration.imports đã được đóng gói đúng trong JAR.
- withPropertyValues(...) thiết lập property cho context kiểm thử; nó không chứng minh biến môi trường hoặc cấu hình production đã được triển khai đúng.
- @ConditionalOnProperty không phải cách tốt để kiểm tra sự tồn tại của một collection chỉ có indexed entries; dùng điều kiện hoặc logic binding phù hợp cho trường hợp đó.
- Property conversion có thể thành công về kiểu dữ liệu nhưng vẫn sai về nghiệp vụ. Ví dụ timeout bằng 0 có thể bind thành công nhưng không phù hợp với ứng dụng.
- Giá trị mặc định là một phần của API công khai; thay đổi default có thể làm thay đổi hành vi consumer.
- Nếu condition đặt ở cấp lớp, tất cả bean và configuration properties trong lớp chịu điều kiện đó.
- Nếu chỉ một bean cần property riêng, đặt condition tại bean hoặc nested configuration tương ứng để không chặn phần còn lại.
- Khi nhiều property bắt buộc cùng match, phải test cả tổ hợp thiếu, false và true.
- Nếu test chỉ nạp auto-configuration class bằng AutoConfigurations.of, vẫn cần một test đóng gói/consumer riêng để xác nhận discovery metadata.

## 13. Lỗi phổ biến khi dùng withPropertyValues

1. **Viết sai key:** test truyền acme.notice.enable nhưng code chờ acme.notice.enabled. Test có thể pass theo nhánh không tạo bean và che lỗi đánh máy.
2. **Dùng dấu hai chấm thay dấu bằng:** mỗi phần tử nên theo dạng key=value.
3. **Nhầm property vắng mặt với giá trị rỗng:** không truyền key khác với truyền key=.
4. **Chỉ test giá trị true:** không phát hiện default khi thiếu property hoặc nhánh false.
5. **Không test matchIfMissing:** thay đổi default có thể phá contract mà test không báo.
6. **Không kiểm tra binding:** bean có thể được tạo nhưng timeout/endpoint vẫn giữ default.
7. **Dùng giá trị Duration không rõ đơn vị:** khiến test khó đọc hoặc phụ thuộc quy ước ngầm.
8. **Dùng property sai prefix:** condition không match hoặc Binder không bind field.
9. **Gom nhiều kịch bản vào một test:** khó biết assertion nào thất bại và trạng thái nào gây lỗi.
10. **Tái sử dụng context thay vì runner:** trạng thái bean và singleton có thể rò rỉ giữa test.
11. **Tưởng runner kiểm tra AutoConfiguration.imports:** AutoConfigurations.of nạp class trực tiếp; metadata cần test riêng.
12. **Tưởng property test tạo tài nguyên thật:** thiết lập URL không khởi động database hoặc server.
13. **Không test giá trị sai định dạng:** lỗi conversion chỉ xuất hiện khi context bind properties.
14. **Đặt condition quá rộng:** tắt một integration làm mất các bean không liên quan.
15. **Chỉ assert context đã khởi động:** cần assert bean có/vắng và giá trị được bind.
16. **Dùng secret thật:** test phải dùng dữ liệu giả, tránh đưa thông tin xác thực vào source và báo cáo.
17. **Cho rằng property truyền vào runner thay đổi application.properties:** nó chỉ thuộc context test, không sửa file cấu hình.
18. **Không kiểm tra user override:** starter có thể tạo bean mặc định cạnh tranh với bean ứng dụng.

## 14. Quy trình viết một bộ property test

1. Liệt kê các property điều khiển condition và binding.
2. Ghi rõ default khi property thiếu.
3. Xác định giá trị hợp lệ, không hợp lệ và biên.
4. Tạo ApplicationContextRunner với auto-configuration cần kiểm tra.
5. Viết test riêng cho property thiếu.
6. Viết test cho true và false.
7. Truyền nhiều property cùng lúc để kiểm tra binding.
8. Kiểm tra default values khi chỉ bật feature.
9. Kiểm tra bean override bằng withBean.
10. Kiểm tra conversion failure hoặc validation failure.
11. Kiểm tra mỗi lần run dùng context độc lập.
12. Chạy mvn clean test.
13. Nếu cần xác minh metadata hoặc ứng dụng thật, bổ sung consumer/integration test riêng.

## 15. Checklist nghiệm thu

- [ ] Runner được cấu hình bằng AutoConfigurations.of đúng lớp cần test.
- [ ] Test có trường hợp property không tồn tại.
- [ ] Test có trường hợp property true.
- [ ] Test có trường hợp property false.
- [ ] matchIfMissing được kiểm chứng.
- [ ] havingValue được kiểm chứng.
- [ ] Nhiều property được truyền trong cùng một lần chạy khi cần.
- [ ] Configuration properties được kiểm tra sau binding.
- [ ] Kiểu dữ liệu boolean, số, Duration, URI, list/map được kiểm tra nếu có dùng.
- [ ] Default values được kiểm tra.
- [ ] Giá trị sai định dạng được kiểm tra nếu có ý nghĩa.
- [ ] Bean do user cung cấp khiến auto-configuration back off.
- [ ] Mỗi test chạy trong context độc lập.
- [ ] Assertion xác nhận bean có/vắng, không chỉ context khởi động.
- [ ] Không dùng secret thật trong test.
- [ ] Đã phân biệt property test với kiểm thử metadata/JAR và kết nối thật.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** withPropertyValues nhận chuỗi theo dạng nào?  
**Đáp án:** Mỗi phần tử có dạng key=value, ví dụ acme.notice.enabled=true.

**Câu 2.** Làm thế nào kiểm tra khi property không tồn tại?  
**Đáp án:** Gọi runner.run(...) mà không thêm withPropertyValues cho property đó, rồi assert bean có/vắng theo matchIfMissing.

**Câu 3.** withPropertyValues có sửa application.properties không?  
**Đáp án:** Không. Nó thêm property vào Environment của context kiểm thử.

**Câu 4.** Vì sao cần kiểm tra cả condition lẫn NoticeProperties?  
**Đáp án:** Condition quyết định bean có được đăng ký; configuration binding quyết định bean nhận giá trị cấu hình nào.

**Câu 5.** Cách thiết lập list trong test là gì?  
**Đáp án:** Có thể dùng indexed property như acme.notice.tags[0]=billing và acme.notice.tags[1]=priority.

**Câu 6.** Làm thế nào xác nhận bean do ứng dụng cung cấp được ưu tiên?  
**Đáp án:** Thêm bean bằng withBean(...), bật property, rồi assert context chỉ có một bean và instance trả về chính là bean tùy chỉnh.

**Câu 7.** ApplicationContextRunner có kiểm tra imports metadata trong JAR không?  
**Đáp án:** Không khi dùng AutoConfigurations.of(Class...). Cách đó nạp class trực tiếp; cần consumer hoặc packaged integration test để kiểm tra discovery metadata.

**Câu 8.** Vì sao nên tách test true, false và missing?  
**Đáp án:** Ba trạng thái bảo vệ ba nhánh contract khác nhau, giúp phát hiện thay đổi default và lỗi condition dễ hơn.

## 17. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 Reference — Testing Your Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing).
- [Spring Boot 3.3 Javadoc — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html).
- [Spring Boot 3.3 Javadoc — AbstractApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/AbstractApplicationContextRunner.html).
- [Spring Boot 3.3 Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [Spring Boot 3.3 Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties).
- [Spring Boot 3.3 Javadoc — ConditionalOnProperty](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html).