# Điều kiện bean chỉ quan sát những định nghĩa đã được xử lý tại thời điểm đánh giá

> **Quy tắc cốt lõi:** Khi Spring Boot đánh giá `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean`, điều kiện chỉ nhìn thấy các bean definition mà `ApplicationContext` đã xử lý tại **thời điểm đó**. Nó không biết trước các bean definition sẽ được đăng ký ở bước tiếp theo, dù chúng có thể tồn tại khi ứng dụng khởi động xong.

Đây là quy tắc quan trọng khi thiết kế **Spring Boot Auto Configuration**, đặc biệt khi một auto-configuration phụ thuộc bean do auto-configuration khác cung cấp hoặc khi cần cung cấp bean mặc định nhưng vẫn cho phép ứng dụng tự ghi đè.

## 1. “Đã được xử lý” là gì?

Một **bean definition** là thông tin Spring dùng để quản lý một bean: kiểu bean, tên, cách tạo, phạm vi, v.v. Việc một definition đã được đăng ký **khác** với việc đối tượng bean đã được khởi tạo.

Hình dung quá trình bắt đầu của một ứng dụng:

1. Spring xử lý các cấu hình người dùng, đăng ký những bean definition tương ứng.
2. Spring Boot xử lý các auto-configuration theo thứ tự đã xác định, bổ sung bean definition từ các lớp này nếu điều kiện cho phép.
3. Container tạo các bean cần thiết, tiêm dependency và hoàn tất khởi động; thứ tự tạo đối tượng phụ thuộc quan hệ dependency và các ràng buộc khởi tạo.

Tại bước 2, giả sử cấu hình A đã đăng ký definition của `Clock`, còn cấu hình B chưa được xử lý: điều kiện kiểm tra `Clock` sẽ thấy definition từ A, nhưng không thể nhìn trước những definition mà B dự định đăng ký. Bean khai báo `@Lazy` vẫn có thể được điều kiện nhận diện nếu **definition** của nó đã tồn tại, dù đối tượng chưa được khởi tạo.

| Điều kiện | Câu hỏi nó trả lời ở thời điểm kiểm tra | Hệ quả của definition đến sau |
| --- | --- | --- |
| `@ConditionalOnBean(Clock.class)` | Đã có bean phù hợp kiểu `Clock` trong phạm vi tìm kiếm chưa? | Không thể dùng bean xuất hiện sau để làm điều kiện lúc này thành đúng. |
| `@ConditionalOnMissingBean(Clock.class)` | Hiện **chưa** có bean phù hợp kiểu `Clock` phải không? | Có thể đã đăng ký fallback trước khi một cấu hình khác khai báo `Clock`. |

“Phù hợp” không chỉ dựa vào chữ trong tên lớp: Boot đối chiếu loại bean, tên hoặc annotation được chỉ định; phạm vi tìm kiếm trong cây `ApplicationContext` và khả năng bean được coi là ứng viên cũng có ảnh hưởng. Ví dụ về vấn đề thứ tự dưới đây giả định cùng một context và những bean thông thường có thể được autowire.

**Không nhầm lẫn ba chuyện:** một class có trên classpath ≠ một bean definition đã đăng ký ≠ một object bean đã được tạo. `@ConditionalOnClass` xét classpath; các điều kiện bean xét registry/factory ở lúc đánh giá; còn `@DependsOn` chủ yếu chi phối thứ tự khởi tạo bean.

## 2. Tại sao thứ tự xử lý có thể đổi kết quả?

Xét hai auto-configuration cùng ứng dụng:

- `ClockAutoConfiguration` tạo một bean `Clock` mặc định.
- `ClockConsumerAutoConfiguration` chỉ tạo `ClockReader` nếu đã có bean `Clock`.

Nếu cấu hình consumer được đánh giá **trước** khi definition `Clock` xuất hiện, `@ConditionalOnBean(Clock.class)` có thể không khớp và `ClockReader` bị bỏ qua. Khi definition `Clock` được đăng ký sau đó, Spring Boot không tự “quay lại” đăng ký phương thức `@Bean` đã bị loại vì điều kiện trước đó.

Tương tự, nếu một auto-configuration kiểm tra `@ConditionalOnMissingBean(Clock.class)` quá sớm, nó có thể tạo fallback trong khi một auto-configuration khác chưa kịp đăng ký một `Clock`. Nếu cấu hình phía sau đăng ký `Clock` không có điều kiện tương ứng, ứng dụng có thể có nhiều bean cùng kiểu và gây mơ hồ khi tiêm dependency.

**Vì thế, thứ tự có ý nghĩa ở pha đăng ký bean definition.** `@AutoConfiguration(after = ...)` hoặc `@AutoConfigureAfter` là cách khai báo quan hệ thứ tự giữa các auto-configuration. Chúng **không** bảo đảm bean nào được tạo thành đối tượng trước, cũng không thay thế `@DependsOn` hoặc dependency injection khi thật sự cần thứ tự khởi tạo.

## 3. Ví dụ Java 17+ — khai báo đúng thứ tự

Ví dụ sau dùng Spring Boot 3.x. Ba class Java thuộc package `example.autoconfig`; package này nên nằm ngoài phạm vi component scan của ứng dụng vì auto-configuration được nạp bằng cơ chế auto-configuration, không nên bị scan như cấu hình người dùng.

**Tệp `src/main/java/example/autoconfig/ClockAutoConfiguration.java`:**

~~~java
package example.autoconfig;

import java.time.Clock;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ClockAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(Clock.class)
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
~~~

Khi chưa có bean `Clock` phù hợp, Boot đăng ký definition `appClock`. Nếu ứng dụng đã định nghĩa `Clock` riêng, điều kiện không khớp và phương thức này không đóng góp bean mặc định. Việc ghi rõ `Clock.class` cũng giúp người đọc thấy chính xác kiểu đang kiểm tra; với `@ConditionalOnMissingBean` đặt trên `@Bean` và không chỉ định kiểu/tên, Boot có thể suy ra kiểu từ kiểu trả về của phương thức.

**Tệp `src/main/java/example/autoconfig/ClockReader.java`:**

~~~java
package example.autoconfig;

import java.time.Clock;
import java.time.Instant;

public record ClockReader(Clock clock) {
    public Instant now() {
        return clock.instant();
    }
}
~~~

`ClockReader` là một đối tượng phụ thuộc `Clock`; nó dùng `Clock` đã được container tiêm vào, không tự tạo đồng hồ mới.

**Tệp `src/main/java/example/autoconfig/ClockConsumerAutoConfiguration.java`:**

~~~java
package example.autoconfig;

import java.time.Clock;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = ClockAutoConfiguration.class)
@ConditionalOnBean(Clock.class)
public class ClockConsumerAutoConfiguration {
    @Bean
    public ClockReader clockReader(Clock clock) {
        return new ClockReader(clock);
    }
}
~~~

Giải thích từng mấu chốt:

1. `after = ClockAutoConfiguration.class` yêu cầu Boot xử lý auto-configuration cung cấp `Clock` trước auto-configuration tiêu thụ `Clock`.
2. `@ConditionalOnBean(Clock.class)` ở **cấp lớp** chỉ cho phép đăng ký phần cấu hình consumer khi tại lúc xét đã có bean `Clock` phù hợp. Nếu điều kiện đặt trên một phương thức `@Bean` riêng lẻ, nó chỉ điều khiển việc đăng ký bean từ phương thức đó.
3. Tham số `Clock clock` của `clockReader` là dependency khi tạo đối tượng; nó không làm điều kiện ở cấp lớp tự động nhìn thấy một definition chưa đăng ký.

Để Boot 3.x khám phá hai auto-configuration khi chúng nằm trong một thư viện, thêm tệp:

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

~~~text
example.autoconfig.ClockConsumerAutoConfiguration
example.autoconfig.ClockAutoConfiguration
~~~

Thứ tự viết các dòng trong tệp **không** là cách khai báo phụ thuộc. Boot sắp thứ tự auto-configuration dựa trên metadata, trong đó quan hệ `after` ở ví dụ này yêu cầu `ClockAutoConfiguration` được xử lý trước `ClockConsumerAutoConfiguration`. Để kiểm thử mà không đóng gói thư viện, có thể nạp trực tiếp các lớp bằng `ApplicationContextRunner` như phần tiếp theo.

### Hai tình huống cần phân biệt

**A. Ứng dụng không tự định nghĩa `Clock`:**

- `ClockAutoConfiguration` thấy thiếu `Clock` nên đăng ký `appClock` mặc định.
- Đến lượt `ClockConsumerAutoConfiguration`, definition `Clock` đã hiện diện nên điều kiện đúng và `clockReader` được đăng ký.
- Khi khởi tạo `ClockReader`, Spring tiêm bean `Clock` hiện có.

**B. Ứng dụng có `@Bean Clock customClock()` do người dùng định nghĩa:**

- Boot xử lý bean definition do người dùng khai báo trước auto-configuration.
- `@ConditionalOnMissingBean(Clock.class)` không khớp, vì vậy `appClock` mặc định không được đăng ký.
- `@ConditionalOnBean(Clock.class)` của consumer vẫn khớp và `clockReader` dùng `customClock`.

Các kết luận trên giả định chỉ có một bean `Clock` phù hợp; với nhiều ứng viên, việc tiêm còn cần quan tâm `@Primary`, qualifier hoặc tên bean.

## 4. Kiểm chứng bằng ApplicationContextRunner

Trong một dự án Spring Boot 3.x có dependency `spring-boot-starter-test`, tạo tệp `src/test/java/example/autoconfig/ClockAutoConfigurationTest.java`:

~~~java
package example.autoconfig;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ClockAutoConfigurationTest {
    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(
                            ClockConsumerAutoConfiguration.class,
                            ClockAutoConfiguration.class));

    @Test
    void registersDefaultClockBeforeConsumer() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(Clock.class);
            assertThat(context).hasSingleBean(ClockReader.class);
            assertThat(context).hasBean("appClock");
        });
    }

    @Test
    void userClockMakesDefaultBackOff() {
        runner.withUserConfiguration(UserClockConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Clock.class);
                    assertThat(context).hasSingleBean(ClockReader.class);
                    assertThat(context).hasBean("customClock");
                    assertThat(context).doesNotHaveBean("appClock");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserClockConfiguration {
        @Bean
        Clock customClock() {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC);
        }
    }
}
~~~

Chạy trong dự án Maven hoặc Gradle đã cấu hình JUnit 5:

~~~bash
mvn test -Dtest=ClockAutoConfigurationTest
# Hoặc với Gradle:
./gradlew test --tests example.autoconfig.ClockAutoConfigurationTest
~~~

**Kết quả mong đợi:** cả hai phép thử đều PASS. Test đầu xác nhận fallback và bean tiêu thụ cùng tồn tại. Test thứ hai xác nhận bean do người dùng khai báo đã được biết trước lúc xét fallback; Boot không đăng ký `appClock` nhưng vẫn tạo `ClockReader`. Không suy diễn từ vị trí hai class trong lệnh `AutoConfigurations.of(...)`: runner xử lý thứ tự auto-configuration giống luồng ứng dụng.

## 5. Cách đọc lỗi và xử lý có hệ thống

Khi `@ConditionalOnBean` bất ngờ **không khớp** hoặc `@ConditionalOnMissingBean` tạo fallback ngoài ý muốn:

1. **Kiểm tra chính xác bean đang tìm:** kiểu (`value`/`type`), tên (`name`), annotation, khả năng bean được coi là ứng viên, và tham số `search` nếu có phân cấp context. Có class trên classpath không có nghĩa bean definition đã được đăng ký.
2. **Xác định ai tạo bean definition và khi nào:** bean do ứng dụng khai báo hay đến từ auto-configuration khác? Nếu đến từ auto-configuration khác, quan hệ `before`/`after` có được khai báo đúng trên các auto-configuration không?
3. **Kiểm tra kiểu trả về của `@Bean`:** metadata về kiểu cần đủ cụ thể để Boot nhận diện điều kiện trước khi tạo object. Ví dụ, không khai báo kiểu trả về quá chung như `Object` khi condition cần tìm một kiểu cụ thể.
4. **Xem Condition Evaluation Report:** khởi động với `--debug` hoặc đọc endpoint Actuator `/actuator/conditions` khi Actuator được cài đặt và endpoint đã được cho phép truy cập. Báo cáo cho biết điều kiện nào khớp/không khớp và lý do; đối chiếu nó với thứ tự auto-configuration thực tế.
5. **Tái hiện bằng `ApplicationContextRunner`:** thử riêng các trường hợp “không có bean”, “có bean do người dùng”, “bean do auto-configuration khác cung cấp” và “thay đổi thứ tự”.

Đừng dùng `@DependsOn` để sửa lỗi bean condition không nhìn thấy definition: `@DependsOn` giải quyết phụ thuộc khi **tạo bean**, còn vấn đề ở đây xảy ra khi **đăng ký definition**. Cũng đừng dùng `@Primary` để che việc fallback bị tạo thừa; `@Primary` chủ yếu giải quyết chọn bean lúc injection.

## 6. Các điểm dễ hiểu sai

- **“Bean có lúc cuối thì `@ConditionalOnBean` chắc chắn đúng.”** Sai. Điều kiện đã được xét trước đó có thể không thấy bean này.
- **“`@ConditionalOnMissingBean` nghĩa là toàn bộ context mãi mãi không có bean đó.”** Sai. Nó kiểm tra phần registry đã xử lý tại thời điểm xét, không tiên đoán tương lai.
- **“Cần bean được instantiate rồi mới được tính là có.”** Sai. Definition phù hợp đã đăng ký có thể đủ; không cần gọi `getBean()` để ép khởi tạo.
- **“Sắp thứ tự auto-configuration cũng sắp thứ tự constructor được gọi.”** Sai. Đó là hai giai đoạn khác nhau.
- **“Dùng hai annotation này tùy ý trong cấu hình người dùng cũng an toàn.”** Không nên mặc định như vậy. Khuyến nghị chính thức của Spring Boot là dùng chúng trong auto-configuration vì Boot xử lý auto-configuration sau các definition do người dùng khai báo.
- **“Chỉ cần tên class khớp là điều kiện sẽ khớp.”** Không đầy đủ. Điều kiện có thể dựa trên type, name, annotation, context hierarchy; một số definition không đủ điều kiện làm ứng viên.

## 7. Tự kiểm tra hiểu bài

1. Một `@Bean` có `@Lazy` đã đăng ký definition nhưng chưa được tạo object. `@ConditionalOnBean` có thể nhìn thấy nó không? **Có**, nếu bean phù hợp các tiêu chí tìm kiếm.
2. Consumer auto-configuration bị đánh giá trước provider; provider sau đó đăng ký bean đúng type. Consumer có tự được kích hoạt lại không? **Không**, không có cơ chế tự quay lại đăng ký bean đã bị bỏ qua vì điều kiện đó; cần sửa thứ tự xử lý.
3. Thư viện muốn cung cấp service mặc định nhưng nhường cho bean do ứng dụng khai báo. Nên đặt gì và ở đâu? **`@ConditionalOnMissingBean(Service.class)` trên bean mặc định thuộc auto-configuration**, với kiểu trả về `@Bean` đủ rõ ràng; nếu phụ thuộc một auto-configuration khác thì khai báo thứ tự thích hợp.

## Tài liệu đối chiếu

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): bean conditions, thứ tự auto-configuration, khuyến nghị về `@Bean` return type và `ApplicationContextRunner`.
- [Spring Boot 3.3 API — ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): quy tắc “processed so far”, các tiêu chí tìm kiếm và cách suy ra kiểu trả về.
- [Spring Boot 3.3 API — ConditionalOnBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html): điều kiện dựa trên bean definition đã xử lý.

**Ghi nhớ:** điều kiện bean là một câu hỏi về trạng thái registry **tại thời điểm đánh giá**. Khi nó phụ thuộc bean từ auto-configuration khác, hãy thiết kế đúng thứ tự đăng ký definition và xác nhận bằng một bài kiểm thử context nhỏ.
