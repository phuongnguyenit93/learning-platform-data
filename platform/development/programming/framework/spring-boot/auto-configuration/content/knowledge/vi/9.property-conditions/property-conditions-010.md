# @ConditionalOnExpression và rủi ro tham chiếu bean khiến khởi tạo quá sớm

## 1. Mục tiêu và phạm vi

`@ConditionalOnExpression` là annotation điều kiện của Spring Boot Auto Configuration. Nó cho phép đăng ký một lớp cấu hình hoặc một phương thức `@Bean` **chỉ khi biểu thức Spring Expression Language (SpEL) trả về `true`**.

Vấn đề quan trọng của bài học là **cách viết biểu thức**: điều kiện đọc property từ `Environment` thường không đụng tới instance bean, nhưng một biểu thức như `@clientSettings.enabled` lại **tham chiếu Spring bean**. Việc phân giải bean này có thể khiến bean khởi tạo quá sớm trong quá trình `ApplicationContext` refresh, trước khi các bước hậu xử lý bình thường được thực hiện. Đặc biệt, binding `@ConfigurationProperties` có thể không áp dụng đầy đủ, khiến giá trị bean chưa hoàn chỉnh và làm điều kiện kết luận sai.

Sau bài học, người học cần nắm được: cú pháp SpEL cơ bản; sự khác biệt giữa placeholder `${...}` và bean reference `@beanName`; cơ chế khởi tạo sớm; ví dụ trước–sau; cách thay bằng `@ConditionalOnProperty`/`Condition`; cách kiểm thử và chẩn đoán.

## 2. Cơ chế hoạt động của `@ConditionalOnExpression`

Annotation thuộc package `org.springframework.boot.autoconfigure.condition` và dùng thuộc tính `value` chứa biểu thức SpEL:

```java
@ConditionalOnExpression("${demo.enabled:false}")
```

Trong ví dụ này, Spring lấy property `demo.enabled` từ `Environment`, thay thế placeholder, rồi đánh giá biểu thức. Nếu property không tồn tại thì lấy `false` theo giá trị mặc định sau dấu hai chấm. Giá trị biểu thức cuối cùng phải có ý nghĩa boolean: `true` để điều kiện khớp, `false` để không khớp.

Có thể kết hợp biểu thức logic và số học:

```java
@ConditionalOnExpression(
    "${demo.enabled:false} and ${demo.pool-size:0} >= 8"
)
```

Ví dụ `application.yml`:

```yaml
demo:
  enabled: true
  pool-size: 12
```

Điều kiện trên khớp vì cả hai mệnh đề đều đúng. Các biến thể:

| `demo.enabled` | `demo.pool-size` | Điều kiện khớp? |
| --- | --- | --- |
| Thiếu | Thiếu | Không, mặc định `false` và `0` |
| `false` | `12` | Không |
| `true` | `4` | Không |
| `true` | `8` | Có |
| `true` | `12` | Có |

Các phép toán phổ biến của SpEL gồm `and`/`or` hoặc `&&`/`||`, `!`, `==`, `!=`, `>`, `>=`, `<`, `<=`. Hãy dùng dấu ngoặc khi có nhiều điều kiện để người đọc hiểu rõ thứ tự ưu tiên. Nếu phần thay thế property tạo thành biểu thức không hợp lệ (ví dụ đưa chuỗi chữ vào vị trí cần số), đánh giá điều kiện có thể báo lỗi lúc khởi động.

Annotation có thể đặt ở hai mức:

- **Trên lớp `@Configuration` hoặc `@AutoConfiguration`:** kết quả điều kiện ảnh hưởng việc đăng ký cấu hình và các `@Bean` của cấu hình đó.
- **Trên phương thức `@Bean`:** chỉ phương thức tương ứng bị điều kiện kiểm soát.

Mặc định thuộc tính `value` là `"true"`, nhưng annotation không có biểu thức thường không mang lại lợi ích kiểm soát tính năng. Điều kiện này **được đánh giá khi Spring xử lý cấu hình và đăng ký bean**, không phải callback chạy lại mỗi khi cấu hình hoặc dữ liệu runtime đổi.

## 3. Khác nhau giữa placeholder và bean reference

| Cú pháp | Đối tượng được truy cập | Tác động đến vòng đời bean |
| --- | --- | --- |
| `${demo.enabled:false}` | Giá trị trong `Environment`, với mặc định `false` | Bản thân placeholder không cần tạo bean |
| `@clientSettings` | Bean tên `clientSettings` trong BeanFactory | Có thể gọi lấy instance bean và làm bean khởi tạo sớm |
| `@clientSettings.enabled` | Bean instance rồi đọc thuộc tính `enabled` | Có rủi ro khởi tạo sớm và đọc trạng thái chưa hoàn chỉnh |
| `@clientSettings.isEnabled()` | Bean instance rồi gọi phương thức | Có các rủi ro trên, cộng thêm tác dụng phụ của method |

Ký hiệu `@clientSettings` bên **trong chuỗi SpEL** là một *bean reference*. Nó khác hoàn toàn ký hiệu `@ConditionalOnExpression` của annotation trong Java. Nếu tên bean chứa dấu chấm, SpEL sử dụng cú pháp dạng `@'some.bean'`. Nhưng biết cú pháp này **không có nghĩa nên dùng bean reference bên trong startup condition**.

### Câu hỏi trọng tâm

Biểu thức `@ConditionalOnExpression("@clientSettings.enabled")` có thật sự chỉ “đọc một boolean” không?

**Không.** Trước khi đọc boolean, SpEL phải lấy được đối tượng `clientSettings`. Nếu bean mới chỉ có definition mà chưa được khởi tạo, việc giải quyết tham chiếu có thể khiến `BeanFactory` **tạo đối tượng đó ngay**, vào thời điểm container đang dựng cấu hình. Phần nguy hiểm không nằm ở toán tử boolean mà ở bước lấy instance.

## 4. Chuỗi sự kiện dẫn đến khởi tạo quá sớm

Giả sử trong một auto-configuration có phương thức:

```java
@Bean
@ConditionalOnExpression("@clientSettings.enabled")
FeatureClient featureClient() {
    return new FeatureClient();
}
```

Đây là **đoạn minh họa**, giả định đã có bean definition tên `clientSettings` được đăng ký ở cấu hình khác; `FeatureClient` là một lớp ứng dụng. Chỉ riêng đoạn này chưa phải tệp Java chạy độc lập.

Một trình tự có thể xảy ra:

1. Spring bắt đầu `refresh()`, đọc các cấu hình và bean definitions.
2. Trong giai đoạn đánh giá điều kiện cho phương thức `featureClient()`, `OnExpressionCondition` yêu cầu đánh giá SpEL.
3. SpEL gặp `@clientSettings`. Bean resolver chuyển yêu cầu đó thành việc tìm/lấy bean theo tên từ `BeanFactory`.
4. Vì bean chưa có instance, BeanFactory có thể **khởi tạo bean ngay trong lúc condition đang được xử lý**.
5. Ở thời điểm quá sớm này, các `BeanPostProcessor` cần thiết có thể chưa được đăng ký/áp dụng đầy đủ. Instance vì thế có nguy cơ bỏ qua một số bước như bind cấu hình, validation, tạo proxy hoặc xử lý khác.
6. Điều kiện đọc trạng thái instance và quyết định đăng ký `FeatureClient`. Kết quả có thể sai so với kỳ vọng dựa trên giá trị cấu hình.

**Spring Boot chính thức cảnh báo**: tham chiếu bean trong `@ConditionalOnExpression` làm bean có thể được khởi tạo rất sớm trong quá trình context refresh; hậu quả là bean có thể không đủ điều kiện để được post-process, ví dụ `@ConfigurationProperties` binding, và trạng thái của bean có thể chưa hoàn chỉnh.

Điều cần phân biệt:

- **Bean definition được đăng ký:** Spring biết *cách* tạo bean.
- **Bean được khởi tạo:** đã có instance.
- **Bean đã qua hậu xử lý:** các bước cần thiết của lifecycle đã được áp dụng.

Ba trạng thái này không đồng nghĩa. Đánh giá một điều kiện đăng ký chỉ cần metadata/property thì **không nên ép** chuyển ngay sang trạng thái khởi tạo instance. Nếu bean được lấy quá sớm, Spring không có cam kết sẽ “chạy bù” toàn bộ hậu xử lý còn thiếu sau đó.

Không phải mọi biểu thức chứa `@bean` đều khởi tạo bean trong tất cả tình huống: nếu bean đã có instance, không cần tạo lần nữa; nếu một nhánh SpEL bị bỏ qua do short-circuit, phần tham chiếu cũng có thể chưa chạy. Tuy nhiên, dựa vào các tình huống tình cờ này để coi bean reference là an toàn sẽ khiến cấu hình phụ thuộc vào thứ tự khởi động.

## 5. Ví dụ lỗi: `@ConfigurationProperties` bị đọc trước khi bind

Xét một class cấu hình do ứng dụng định nghĩa:

```java
package example.demo;

public final class ClientSettings {
    private boolean enabled;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

Một cấu hình khác đăng ký nó dưới dạng bean được bind từ `application.yml`:

```java
@Bean
@ConfigurationProperties(prefix = "demo.client")
ClientSettings clientSettings() {
    return new ClientSettings();
}
```

Giá trị cấu hình mong muốn:

```yaml
demo:
  client:
    enabled: true
```

Thông thường, Spring tạo `ClientSettings` rồi áp dụng cơ chế cấu hình để field `enabled` nhận `true`. Nhưng nếu trong auto-configuration có điều kiện:

```java
@ConditionalOnExpression("@clientSettings.enabled")
```

thì bean `clientSettings` có thể bị tạo **trước hậu xử lý binding** và vẫn mang giá trị `false` mặc định Java. Khi đó điều kiện có thể không khớp dù property `demo.client.enabled=true`. Ngay cả khi một lần khởi động cụ thể cho kết quả đúng, cách thiết kế vẫn phụ thuộc không cần thiết vào thời điểm tạo bean.

**Đây là kịch bản giải thích rủi ro**, không phải khẳng định mọi Spring Boot application đều quan sát chính xác kết quả `false` trên mọi phiên bản và mọi cách cấu hình. Kết quả cụ thể còn phụ thuộc thứ tự đăng ký các bean và BeanPostProcessor, nhưng cơ chế rủi ro đã được tài liệu Spring Boot xác nhận.

Những lỗi có thể đi kèm khi truy cập bean trong SpEL:

- Bean chưa được đăng ký: resolver không tìm thấy tên bean và đánh giá biểu thức có thể làm context khởi động thất bại.
- Getter/method trong biểu thức thực hiện I/O, gọi service, hoặc khởi tạo đối tượng phụ thuộc trước thời điểm mong muốn.
- Bean bị khởi tạo trước cơ chế tạo proxy như AOP hoặc trước một bộ hậu xử lý khác, dẫn tới hành vi khác mong đợi.
- Một chu trình phụ thuộc vòng có thể bộc lộ trong giai đoạn điều kiện thay vì lúc khởi tạo bean thông thường.
- Điều kiện dựa vào dữ liệu mutable của bean khiến hành vi bootstrap khó đoán và khó tái hiện khi thay đổi thứ tự auto-configuration.

## 6. Cách thay thế an toàn và mục đích sử dụng

### 6.1. Chỉ cần bật/tắt tính năng: `@ConditionalOnProperty`

```java
@Bean
@ConditionalOnProperty(
    prefix = "demo.client",
    name = "enabled",
    havingValue = "true"
)
FeatureClient featureClient() {
    return new FeatureClient();
}
```

Cách này chỉ đọc **property** `demo.client.enabled`, không cần tạo `ClientSettings`. Với `havingValue="true"`, điều kiện khớp khi giá trị property tương ứng `true`. `matchIfMissing` mặc định `false` nên nếu không có property thì điều kiện không khớp. Đây thường là lựa chọn đầu tiên cho cờ bật/tắt.

### 6.2. Cần kết hợp boolean và ngưỡng số: SpEL chỉ dùng placeholder

```java
@Bean
@ConditionalOnExpression(
    "${demo.client.enabled:false} and ${demo.client.pool-size:0} >= 8"
)
FeatureClient featureClient() {
    return new FeatureClient();
}
```

Vẫn sử dụng SpEL, nhưng chỉ dựa trên các property trong `Environment`; **không dùng `@clientSettings`**. Test nên bao phủ khi thiếu property, sai kiểu dữ liệu, và giá trị đúng ngay tại biên `8`.

### 6.3. Quy tắc phức tạp: viết `Condition` chỉ đọc `Environment`

Tạo tệp `src/main/java/example/conditions/PoolCapacityCondition.java`:

```java
package example.conditions;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class PoolCapacityCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {
        boolean enabled = context.getEnvironment()
                .getProperty("demo.client.enabled", Boolean.class, false);
        int poolSize = context.getEnvironment()
                .getProperty("demo.client.pool-size", Integer.class, 0);
        return enabled && poolSize >= 8;
    }
}
```

Dùng trong một lớp `@Configuration` (mảnh mã, với các import và kiểu ứng dụng tương ứng):

```java
@Bean
@Conditional(PoolCapacityCondition.class)
FeatureClient featureClient() {
    return new FeatureClient();
}
```

Ở đây `matches` chỉ lấy dữ liệu từ `Environment`, **không truy cập instance bean**. Nếu số property không thể chuyển đổi thành `Integer`, ứng dụng có thể báo lỗi chuyển đổi ngay trong quá trình đánh giá; muốn thông báo cấu hình rõ hơn hãy thiết kế validation riêng cho dữ liệu cấu hình. `PoolCapacityCondition` không nên tự gọi network, cơ sở dữ liệu hoặc tạo những bean phụ thuộc, vì nó cũng chạy trong giai đoạn cấu hình.

### 6.4. Muốn kiểm tra bean có tồn tại: `@ConditionalOnBean`

```java
@Bean
@ConditionalOnBean(ClientSettings.class)
FeatureClient featureClient() {
    return new FeatureClient();
}
```

Trường hợp này kiểm tra sự tồn tại của bean theo kiểu trong các bean definition đã được xử lý, **không đọc giá trị `enabled` của instance**. Vì vậy nó chỉ thay thế được yêu cầu “có bean `ClientSettings`”, không thay thế được yêu cầu “client đang được bật”. Các điều kiện dựa trên bean definition cũng phụ thuộc thứ tự cấu hình; nên đặt trong auto-configuration và kiểm thử thứ tự nếu cấu hình phụ thuộc lẫn nhau.

### Bảng chọn nhanh

| Mục đích | Công cụ phù hợp |
| --- | --- |
| Bật khi `demo.enabled=true` | `@ConditionalOnProperty` |
| Bật khi các property so sánh qua một biểu thức đơn giản | `@ConditionalOnExpression` với `${...}` |
| Quy tắc cấu hình phức tạp, cần kiểm tra dữ liệu rõ ràng | `Condition` chỉ đọc `Environment` |
| Bật khi có bean một kiểu/tên nhất định | `@ConditionalOnBean` |
| Bật khi thiếu bean một kiểu/tên nhất định | `@ConditionalOnMissingBean` |
| Bật/tắt liên tục theo trạng thái đang chạy của bean | Logic runtime; điều kiện đăng ký startup không phải công cụ phù hợp |

## 7. Ví dụ test chạy được với Java 17+ và Spring Boot 3.3

Đây là một tệp test hoàn chỉnh, minh họa `@ConditionalOnExpression` an toàn chỉ từ property và so sánh với `@ConditionalOnProperty`. Không có `@beanName` trong biểu thức.

Tạo `src/test/java/example/conditions/ExpressionConditionTests.java` trong một dự án Spring Boot 3.3.x có dependency `spring-boot-starter-test` (JUnit Jupiter và AssertJ) và đã bật JUnit Platform:

```java
package example.conditions;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class ExpressionConditionTests {

    static final class FastPathMarker {}
    static final class EnabledFlagMarker {}

    @AutoConfiguration
    static class DemoAutoConfiguration {

        @Bean
        @ConditionalOnExpression(
                "${demo.fast-mode:false} and ${demo.min-size:0} >= 10"
        )
        FastPathMarker fastPathMarker() {
            return new FastPathMarker();
        }

        @Bean
        @ConditionalOnProperty(
                prefix = "demo",
                name = "fast-mode",
                havingValue = "true"
        )
        EnabledFlagMarker enabledFlagMarker() {
            return new EnabledFlagMarker();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(DemoAutoConfiguration.class));

    @Test
    void noPropertiesCreatesNeitherBean() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(FastPathMarker.class);
            assertThat(context).doesNotHaveBean(EnabledFlagMarker.class);
        });
    }

    @Test
    void disabledFeatureCreatesNeitherBean() {
        runner.withPropertyValues(
                "demo.fast-mode=false",
                "demo.min-size=20"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(FastPathMarker.class);
            assertThat(context).doesNotHaveBean(EnabledFlagMarker.class);
        });
    }

    @Test
    void enabledButSmallPoolCreatesOnlyFlagBean() {
        runner.withPropertyValues(
                "demo.fast-mode=true",
                "demo.min-size=4"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(FastPathMarker.class);
            assertThat(context).hasSingleBean(EnabledFlagMarker.class);
        });
    }

    @Test
    void enabledAndLargePoolCreatesBothBeans() {
        runner.withPropertyValues(
                "demo.fast-mode=true",
                "demo.min-size=12"
        ).run(context -> {
            assertThat(context).hasSingleBean(FastPathMarker.class);
            assertThat(context).hasSingleBean(EnabledFlagMarker.class);
        });
    }
}
```

Lệnh chạy khi project có Gradle wrapper và `test` dùng JUnit Platform:

```bash
./gradlew test --tests example.conditions.ExpressionConditionTests
```

Trong dự án Maven có cấu hình JUnit 5/Surefire, dùng `./mvnw -Dtest=ExpressionConditionTests test`. Kết quả kỳ vọng là **bốn test PASS**; không có một chuỗi stdout cố định cho mọi cấu hình build.

| Trường hợp | `FastPathMarker` — SpEL | `EnabledFlagMarker` — property |
| --- | --- | --- |
| Không cung cấp property | Không có | Không có |
| `fast-mode=false`, `min-size=20` | Không có | Không có |
| `fast-mode=true`, `min-size=4` | Không có | Có |
| `fast-mode=true`, `min-size=12` | Có | Có |

Các test xác nhận ngữ nghĩa điều kiện và giá trị mặc định. Chúng **không giả định** rằng mọi ví dụ có `@beanName` đều cho cùng một lỗi trên mọi cấu hình. Muốn chứng minh một bean cụ thể bị khởi tạo sớm trong dự án, cần theo dõi thêm thời điểm constructor chạy, binding và BeanPostProcessor tương ứng trong các context độc lập.

## 8. Quan sát và chẩn đoán trên dự án thực tế

1. **Kiểm tra chuỗi SpEL:** tìm `@beanName`, `@beanName.property`, lời gọi getter hoặc method. Đó là dấu hiệu condition đang dựa vào instance bean.
2. **Kiểm tra property gốc:** dùng chính key từ `Environment`, kiểm tra default trong `${...}`, kiểu boolean/số và trường hợp thiếu key. Đừng nhầm một property có cùng tên với thuộc tính bean.
3. **Bật báo cáo điều kiện:** chạy ứng dụng Spring Boot với `--debug` để xem `ConditionEvaluationReport`, hoặc gắn listener vào `ApplicationContextRunner` trong test. Report cho biết lý do khớp/không khớp, không nhất thiết tự chứng minh thứ tự toàn bộ post-processing.
4. **Quan sát vòng đời:** log các thời điểm tạo bean, bind `@ConfigurationProperties` và gắn `BeanPostProcessor` nếu nghi ngờ instance được lấy trong lúc condition đang chạy.
5. **So sánh trước–sau:** thay expression tham chiếu bean bằng điều kiện property tương đương. Kiểm tra kết quả đăng ký bean và trạng thái bean đã bind.
6. **Bao phủ nhánh biên:** property thiếu, `true`, `false`, ngưỡng đúng bằng giới hạn, sai kiểu dữ liệu và điều kiện chỉ có bean definition.

Trong test có thể dùng `ConditionEvaluationReportLoggingListener` như mảnh mã sau (thêm import và đặt vào chuỗi thiết lập runner):

```java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

// Ví dụ trong phần cấu hình ApplicationContextRunner:
.withInitializer(
    ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)
)
```

Đoạn này là mảnh mã minh họa chứ không phải một tệp Java độc lập. `ApplicationContextRunner` dựng context riêng cho từng case, giúp tránh việc bean được tạo trong test trước tác động sang case sau.

## 9. Lỗi phổ biến và bài tập tự kiểm tra

### Lỗi phổ biến

- **Cho rằng SpEL chỉ “đọc thuộc tính”:** `@service.enabled` trước hết phải phân giải bean `service`, có thể kích hoạt khởi tạo.
- **Nhầm bean đã đăng ký với bean đã sẵn sàng:** có bean definition chưa nói lên các giai đoạn binding/proxy/validation đã hoàn tất.
- **Dùng `@ConditionalOnExpression` cho một boolean đơn giản:** nên ưu tiên `@ConditionalOnProperty`, nhất là khi muốn dễ giải thích và kiểm thử.
- **Tưởng `@ConditionalOnBean` kiểm tra thuộc tính bean:** nó chỉ kiểm tra presence theo bean metadata mà nó quan sát được.
- **Dùng trạng thái runtime để thay đổi cấu trúc bean:** condition chỉ được đánh giá trong quá trình đăng ký, không tự đăng ký lại bean sau khi ứng dụng chạy.
- **Không xử lý giá trị mặc định và kiểu số:** placeholder thiếu, số không hợp lệ hoặc phép so sánh sai kiểu có thể làm logic condition khác ý định.
- **Cho rằng khởi tạo sớm rồi Spring sẽ tự hậu xử lý bù:** Spring Boot cảnh báo bean khởi tạo quá sớm có thể không đủ điều kiện được hậu xử lý như dự kiến.

### Tự kiểm tra

1. Biểu thức `${demo.enabled:false}` có yêu cầu bean `demo` không? **Không.** Nó lấy property trực tiếp từ `Environment`.
2. Vì sao `@ConditionalOnExpression("@clientSettings.enabled")` có thể kết luận `false` dù `demo.client.enabled=true`? **Vì bean có thể được tạo và đọc trước bước binding `@ConfigurationProperties`.**
3. Cần điều kiện đúng khi `demo.enabled=true`. Lựa chọn gọn và an toàn? **`@ConditionalOnProperty(prefix="demo", name="enabled", havingValue="true")`.**
4. Cần kiểm tra `demo.pool-size >= 8` nhưng tuyệt đối không lấy instance bean. Làm sao? **Dùng SpEL chỉ với placeholder cấu hình hoặc `Condition` đọc `Environment`.**
5. Sau khi context đã khởi động, đổi `demo.enabled` từ false sang true có tự tạo bean bị bỏ qua trước đó không? **Không.** Phải thiết kế cơ chế runtime riêng nếu cần thay đổi động.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration, SpEL Expression Conditions](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): giải thích cảnh báo khởi tạo bean rất sớm, hậu xử lý và `@ConfigurationProperties` binding.
- [Spring Framework — SpEL Bean References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html): cú pháp `@beanName` và cách bean resolver tham chiếu bean.
- [Spring Boot — ConditionalOnExpression API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnExpression.html): ngữ nghĩa annotation và giá trị mặc định của `value`.
