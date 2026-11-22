# Rủi ro dùng spring.main.allow-bean-definition-overriding để che xung đột thiết kế

## 1. Bản chất vấn đề và mục tiêu

Trong Spring Boot Auto Configuration, hai cấu hình có thể cùng định nghĩa một bean dưới **cùng một tên**, dù chúng xuất phát từ hai lớp khác nhau, một thư viện starter và ứng dụng, hoặc hai đường import/component scan. Khi đăng ký bean definition thứ hai với tên đã có, Spring gặp **xung đột định danh**.

Spring Boot 3.3 mặc định đặt `spring.main.allow-bean-definition-overriding=false` để phát hiện trường hợp này trong quá trình khởi động. Bật `true` có thể cho phép một bean definition thay thế definition khác, khiến ứng dụng vượt qua lỗi khởi động. Tuy nhiên, cấu hình “chạy được” chưa có nghĩa quan hệ giữa các bean đã được thiết kế đúng: bean bị thay thế có thể đang sở hữu cấu hình quan trọng, điều kiện back-off chưa được áp dụng, hoặc hai thành phần vốn cần cùng tồn tại nhưng lại dùng trùng tên.

Mục tiêu bài học:

1. Hiểu chính xác `spring.main.allow-bean-definition-overriding` kiểm soát điều gì và **không** kiểm soát điều gì.
2. Phân biệt **trùng tên bean**, **nhiều bean cùng kiểu**, và **ghi đè giá trị property**.
3. Phân tích rủi ro khi bật overriding toàn cục và cách khắc phục theo ý định kiến trúc.
4. Áp dụng `@ConditionalOnMissingBean`, tên bean rõ ràng, `@Primary`, `@Qualifier`, `@Profile` hoặc `@ConditionalOnProperty` đúng ngữ cảnh.
5. Kiểm tra bằng Java 17+, Spring Boot 3.3 và JUnit 5.

## 2. Bean definition overriding thực sự là gì?

Một `BeanDefinition` mô tả cách Spring tạo bean: tên, kiểu/factory method, scope, điều kiện, autowiring và metadata liên quan. Trong cùng một BeanFactory, bean definition thường được quản lý theo **bean name**.

Giả sử hai cấu hình định nghĩa cùng tên `messageSender`:

```java
@Configuration(proxyBeanMethods = false)
class FileSenderConfiguration {

    @Bean("messageSender")
    MessageSender fileSender() {
        return new FileMessageSender();
    }
}

@Configuration(proxyBeanMethods = false)
class SmtpSenderConfiguration {

    @Bean("messageSender")
    MessageSender smtpSender() {
        return new SmtpMessageSender();
    }
}
```

Đây là **đoạn mã minh họa**, giả định `MessageSender`, `FileMessageSender` và `SmtpMessageSender` do ứng dụng cung cấp. Khi cả hai definition cùng được xử lý trong cùng BeanFactory, chúng tranh chấp tên `messageSender`. Vấn đề là **trùng tên**, không phải “có hai lớp cùng triển khai interface” một cách tự thân.

Cấu hình Spring Boot trong `application.yml`:

```yaml
spring:
  main:
    allow-bean-definition-overriding: false
```

Với giá trị `false` (cũng là **mặc định Spring Boot 3.3**), hành vi đăng ký trùng tên thường bị từ chối. Một lỗi điển hình là `BeanDefinitionOverrideException`, có thông tin bean name và hai bean definitions liên quan. Tùy đường đăng ký, xung đột có thể được phát hiện ở một bước khác và xuất hiện dưới exception khác; đừng chỉ dựa vào tên exception để kết luận toàn bộ nguyên nhân.

Nếu đổi thành:

```yaml
spring:
  main:
    allow-bean-definition-overriding: true
```

container có thể chấp nhận **đăng ký lại cùng tên**. Trong tình huống dùng `BeanDefinitionRegistry.registerBeanDefinition(...)` trực tiếp, definition đăng ký sau sẽ thay thế definition trước. Điều này **không** có nghĩa Spring tạo hai instance rồi “ghép” chúng, cũng không có hợp đồng chung rằng một lớp cấu hình cụ thể luôn thắng trong mọi cơ chế scanning/import.

### Kết quả của một quyết định cho phép ghi đè

| Câu hỏi | Khi `false` | Khi `true` |
| --- | --- | --- |
| Đăng ký lần thứ hai cùng tên vào registry thông thường | Bị từ chối bằng lỗi | Có thể thay thế definition cùng tên |
| Có hợp nhất cấu hình của hai definition? | Không | **Không** |
| Có bảo đảm bean “đúng nghiệp vụ” thắng? | Không áp dụng, xung đột lộ ra | **Không** |
| Hai bean khác tên nhưng cùng interface có được phép tồn tại? | Có | Có |
| Có giải quyết mọi lỗi autowiring? | Không | Không |
| Có thay đổi ưu tiên các `application.yml`/property sources? | Không | Không |

**Phạm vi:** giá trị `spring.main.allow-bean-definition-overriding` là chính sách Spring Boot thiết lập trên bean factory khi khởi động thông qua `SpringApplication`. Một `DefaultListableBeanFactory` tạo thủ công trong unit test có thể có chính sách mặc định khác, vì thế test trực tiếp factory phải đặt cờ rõ ràng để mô phỏng hành vi Spring Boot.

## 3. Phân biệt ba dạng “trùng” dễ bị nhầm

### 3.1. Trùng **bean name**: đối tượng của property này

```java
@Bean("messageSender")
MessageSender a() { /* ... */ }

@Bean("messageSender")
MessageSender b() { /* ... */ }
```

Đây là hai ý định đăng ký definition vào **cùng một tên**. Chính sách bean definition overriding có liên quan. Đoạn mã chỉ mô tả ý tưởng; nếu đặt trong một cấu hình cụ thể, cách Spring ConfigurationClass parser xử lý còn phụ thuộc đặc điểm hai `@Bean` methods và quy tắc cấu hình.

### 3.2. Khác tên, **cùng kiểu**: thường là vấn đề chọn ứng viên injection

```java
@Bean("fileSender")
MessageSender fileSender() { /* ... */ }

@Bean("smtpSender")
MessageSender smtpSender() { /* ... */ }
```

Hai bean này **không trùng tên**. Chúng có thể cùng tồn tại dù overriding bị tắt. Tuy nhiên injection một `MessageSender` mà không có tiêu chí chọn có thể gây `NoUniqueBeanDefinitionException`. Bật `allow-bean-definition-overriding=true` **không** giải quyết tình trạng nhiều ứng viên cùng kiểu khác tên. Khi đây là hai chiến lược hợp lệ, có thể dùng `@Qualifier` hoặc `@Primary` để chọn bean phù hợp.

### 3.3. Trùng **property key**: không phải bean definition overriding

Nếu property `demo.timeout` xuất hiện trong nhiều `PropertySource`, Spring Boot áp dụng thứ tự ưu tiên của externalized configuration để quyết định **giá trị property cuối cùng**. Cơ chế đó **khác** đăng ký lại bean name. `spring.main.allow-bean-definition-overriding` không kiểm soát `application.yml` ghi đè biến môi trường, command-line argument, profile configuration hay các nguồn property khác.

Đây là phân biệt quan trọng khi một nhóm nói “cấu hình B override cấu hình A”: trước hết phải biết họ đang nói đến **property value**, **bean definition**, hay **ứng viên được inject**.

## 4. Vì sao bật `true` để chữa lỗi thường che vấn đề thiết kế?

### 4.1. Mất tính tường minh: không biết bean nào được giữ lại

Một dependency, starter hoặc thư viện mới có thể đưa thêm bean cùng tên. Nếu cho phép overriding, ứng dụng có thể tiếp tục chạy với **definition khác**. Những cấu hình gắn với definition cũ (ví dụ scope, qualifiers, init/destroy methods, factory method hoặc property configuration) có thể không còn tác dụng theo dự kiến.

Dựa vào “cấu hình được quét trước/sau” để chọn winner là cách làm không ổn định: thứ tự import, điều kiện theo classpath, profile, version library và thời điểm đăng ký bean có thể thay đổi. Không nên coi **“bean ghi sau”** là một hợp đồng nghiệp vụ.

### 4.2. Lỗi chỉ xuất hiện ở môi trường khác

Một test context có thể nạp ít starter hơn production; một profile khác có thể bổ sung thêm cấu hình; một môi trường có thêm dependency. Với overriding bật toàn cục, **hai tập bean khác nhau** có thể đều khởi động thành công nhưng hành vi lại khác.

Ví dụ, `messageSender` trong môi trường test là stub an toàn, còn ở production bị definition gửi SMTP thật thay thế hoặc ngược lại. Nếu mục tiêu là test override có chủ đích, nên đặt sự thay thế ở **phạm vi test** bằng cấu hình/annotation test thích hợp, không bật chính sách ghi đè toàn cục cho mọi môi trường.

### 4.3. Che thiếu sót trong thiết kế auto-configuration

Một starter có thể khai báo `DefaultMessageSender` không điều kiện, trong khi ứng dụng định nghĩa `CustomMessageSender` cùng tên. Đặt `true` để ứng dụng khởi động không giải quyết việc starter đã **không nhường chỗ cho cấu hình người dùng**.

Thiết kế auto-configuration thông thường là **back off theo điều kiện**, chẳng hạn:

```java
@AutoConfiguration
class MessageSenderAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender defaultMessageSender() {
        return new DefaultMessageSender();
    }
}
```

Nếu người dùng đã khai báo bean `MessageSender` có thể được nhận diện trước khi điều kiện được đánh giá, auto-configuration **không đăng ký** bean mặc định. Đó là sự thay thế **có chủ đích bằng điều kiện**, khác với việc cố đăng ký hai bean name trùng nhau rồi để bean factory loại một bên.

**Lưu ý thứ tự:** `@ConditionalOnMissingBean` chỉ xét những bean definitions đã được xử lý đến lúc đánh giá. Spring Boot khuyến nghị điều kiện này trong auto-configuration vì bean do người dùng khai báo được xử lý trước; giữa các auto-configuration có phụ thuộc, có thể cần `@AutoConfiguration(after=...)`. Nên khai báo return type `@Bean` rõ ràng để điều kiện theo kiểu nhận diện được mà không cần khởi tạo instance.

### 4.4. Che trách nhiệm sở hữu của bean

Nếu hai module đều tự khai báo `transactionManager`, `objectMapper` hoặc `httpClient`, cần xác định module nào sở hữu cấu hình mặc định, module nào là bên tiêu thụ và khi nào ứng dụng được phép tùy biến. Một cờ toàn cục không diễn đạt được các quy tắc ấy.

Hậu quả thực tế có thể gồm: serializer được thay đổi ngoài ý muốn, mất interceptor hoặc timeout, mapper không còn module cần thiết, client dùng sai credential, bean bị mất lifecycle hook, và các phụ thuộc khác nhận instance khác mong đợi. Những rủi ro này **phụ thuộc bean bị thay thế**, không phải mọi ứng dụng bật cờ đều chắc chắn gặp đồng thời tất cả lỗi.

## 5. Các giải pháp đúng theo ý định

### 5.1. Hai cấu hình **không nên cùng hoạt động**: loại trừ nguồn đăng ký thừa

Trước hết tìm vì sao cùng một bean được đăng ký hai lần:

- Cấu hình vừa được `@Import` thủ công, vừa được quét qua component scan.
- Auto-configuration bị đưa vào component scan trái với cách khai báo qua `AutoConfiguration.imports`.
- Một starter cũ và một starter mới đều khai báo hạ tầng cùng tên.
- Một `@Configuration` thử nghiệm bị nạp vào production, hoặc hai profile cấu hình được bật đồng thời.
- Một `@Bean` thủ công trùng định danh với bean do thư viện cấu hình.

Cách khắc phục là sửa đường import/scan, thu hẹp phạm vi, bỏ bean không cần thiết hoặc thay cấu hình tương ứng. Đừng đổi tên tùy tiện nếu đó là **hai định nghĩa cho cùng một trách nhiệm duy nhất**; trước hết xác định definition nào thật sự thuộc kiến trúc.

### 5.2. Thư viện cung cấp default, ứng dụng được phép tùy biến: `@ConditionalOnMissingBean`

Ví dụ dưới đây minh họa **hợp đồng back-off theo kiểu**, không cần người dùng đặt trùng tên với bean mặc định.

```java
@AutoConfiguration
class SenderAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender defaultSender() {
        return new DefaultMessageSender();
    }
}

@Configuration(proxyBeanMethods = false)
class ApplicationSenderConfiguration {
    @Bean
    MessageSender customSender() {
        return new CustomMessageSender();
    }
}
```

Hai lớp trên là **mảnh mã minh họa**, cần có interface và implementation của ứng dụng. Khi user configuration được xử lý trước và `customSender` đã được nhận diện là `MessageSender`, `defaultSender` sẽ **back off**. Không có hai definitions trùng tên và không cần `allow-bean-definition-overriding=true`.

Nếu hợp đồng đòi **tên cố định** thay vì kiểu, có thể dùng `@ConditionalOnMissingBean(name="messageSender")`. Cần chọn đúng tiêu chí: theo kiểu để “người dùng cung cấp bất kỳ implementation nào”, theo tên để “chỉ một định danh đặc biệt được phép”. Điều kiện theo kiểu có thể không đạt ý định nếu ứng dụng cần **nhiều bean** cùng interface; lúc đó thiết kế bean names/qualifiers rõ hơn.

### 5.3. Hai implementation **đều cần tồn tại**: tên riêng + `@Qualifier`/`@Primary`

```java
@Configuration(proxyBeanMethods = false)
class SenderConfiguration {
    @Bean("smtpSender")
    @Primary
    MessageSender smtpSender() {
        return new SmtpMessageSender();
    }

    @Bean("fileSender")
    MessageSender fileSender() {
        return new FileMessageSender();
    }

    @Bean
    DispatchJob dispatchJob(
            @Qualifier("fileSender") MessageSender sender) {
        return new DispatchJob(sender);
    }
}
```

Đoạn này là **mảnh mã ứng dụng** với các kiểu do dự án định nghĩa. Hai bean có tên khác nhau nên không có collision theo tên. `@Primary` chọn mặc định khi inject theo kiểu mà không có qualifier; `@Qualifier("fileSender")` chọn rõ chiến lược còn lại tại injection point. **`@Primary` và `@Qualifier` không làm hai định nghĩa cùng tên trở nên hợp lệ.**

### 5.4. Chỉ chọn **một biến thể**: `@Profile` hoặc `@ConditionalOnProperty`

Nếu chỉ một implementation được phép hoạt động theo môi trường/cấu hình, diễn đạt sự loại trừ bằng điều kiện thay vì thay đè definition:

```java
@Bean("messageSender")
@ConditionalOnProperty(
    prefix = "demo.sender",
    name = "mode",
    havingValue = "smtp"
)
MessageSender smtpSender() {
    return new SmtpMessageSender();
}

@Bean("messageSender")
@ConditionalOnProperty(
    prefix = "demo.sender",
    name = "mode",
    havingValue = "file"
)
MessageSender fileSender() {
    return new FileMessageSender();
}
```

Đây là **hai mảnh khai báo giả định nằm trong cấu hình hợp lệ**. Với `demo.sender.mode=smtp` hoặc `file`, chỉ một phương thức khớp điều kiện. Nếu property thiếu hoặc nhận giá trị khác, cả hai không được đăng ký. Để tránh việc đồng thời khớp khi mở rộng điều kiện hoặc gặp các góc cạnh khi cùng tên `@Bean` trong một class, cách dễ bảo trì hơn là đặt từng biến thể trong **lớp `@Configuration` riêng** có điều kiện ở lớp, hoặc chọn bean bằng một factory method duy nhất. Hãy thêm test theo mode.

Ví dụ một configuration per profile cũng hợp lý khi môi trường thật sự quyết định implementation. Với `@Profile("test")` và `@Profile("prod")`, cần bảo đảm profile mong muốn không bị bật đồng thời nếu cả hai dùng cùng bean name; không mặc định rằng hai profile bất kỳ loại trừ nhau.

### 5.5. Thay thế chỉ để test: giới hạn trong test context

Nếu cần fake/mock/stub trong kiểm thử, dùng cơ chế test thích hợp (`@TestConfiguration` được cấu hình rõ, mock override theo phiên bản Spring Boot/Spring Test, hoặc `ApplicationContextRunner` khởi tạo riêng). Đảm bảo cấu hình test không lọt vào runtime. Test nên chứng minh **bean nào được inject**, không chỉ “context chạy qua”.

Bật `spring.main.allow-bean-definition-overriding=true` trong toàn hệ thống để cho một test vượt qua không phải mô hình thay thế có chủ đích: nó mở cổng cho mọi xung đột khác cùng tên và có thể làm khác biệt giữa test và production khó phát hiện.

## 6. Thực hành Java 17+, Spring Boot 3.3: test hành vi thật

Các test dưới đây tách hai lớp vấn đề: **(A) hành vi đăng ký trùng tên của `DefaultListableBeanFactory`** và **(B) back-off hợp lệ của Spring Boot auto-configuration**. Chúng là các tình huống độc lập, không cần tạo web server.

Đặt nguyên tệp vào `src/test/java/example/overriding/BeanDefinitionOverridingTests.java` trong dự án Java 17+ và Spring Boot 3.3.x có `spring-boot-starter-test`, JUnit Jupiter và AssertJ:

```java
package example.overriding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.support.BeanDefinitionOverrideException;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class BeanDefinitionOverridingTests {

    interface Sender {
        String id();
    }

    public static final class DefaultSender implements Sender {
        @Override
        public String id() {
            return "default";
        }
    }

    public static final class CustomSender implements Sender {
        @Override
        public String id() {
            return "custom";
        }
    }

    @Test
    void duplicateNameFailsWhenOverridingDisabled() {
        DefaultListableBeanFactory factory =
                new DefaultListableBeanFactory();
        factory.setAllowBeanDefinitionOverriding(false);
        factory.registerBeanDefinition(
                "messageSender",
                new RootBeanDefinition(DefaultSender.class));

        assertThatThrownBy(() -> factory.registerBeanDefinition(
                "messageSender",
                new RootBeanDefinition(CustomSender.class)))
                .isInstanceOf(BeanDefinitionOverrideException.class)
                .hasMessageContaining("messageSender");

        assertThat(factory.getBean("messageSender", Sender.class).id())
                .isEqualTo("default");
    }

    @Test
    void enabledOverridingReplacesDefinitionInRegistry() {
        DefaultListableBeanFactory factory =
                new DefaultListableBeanFactory();
        factory.setAllowBeanDefinitionOverriding(true);
        factory.registerBeanDefinition(
                "messageSender",
                new RootBeanDefinition(DefaultSender.class));
        factory.registerBeanDefinition(
                "messageSender",
                new RootBeanDefinition(CustomSender.class));

        assertThat(factory.getBeanDefinitionCount()).isEqualTo(1);
        assertThat(factory.getBean("messageSender", Sender.class).id())
                .isEqualTo("custom");
    }

    @Test
    void distinctNamesOfSameTypeAreNotDefinitionOverride() {
        DefaultListableBeanFactory factory =
                new DefaultListableBeanFactory();
        factory.setAllowBeanDefinitionOverriding(false);
        factory.registerBeanDefinition(
                "defaultSender",
                new RootBeanDefinition(DefaultSender.class));
        factory.registerBeanDefinition(
                "customSender",
                new RootBeanDefinition(CustomSender.class));

        assertThat(factory.getBeanDefinitionCount()).isEqualTo(2);
        assertThat(factory.getBeanNamesForType(Sender.class))
                .containsExactlyInAnyOrder(
                        "defaultSender",
                        "customSender");

        assertThatThrownBy(() -> factory.getBean(Sender.class))
                .isInstanceOf(NoUniqueBeanDefinitionException.class);
    }

    @AutoConfiguration
    static class SenderAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(Sender.class)
        Sender defaultSender() {
            return new DefaultSender();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ApplicationSenderConfiguration {
        @Bean
        Sender customSender() {
            return new CustomSender();
        }
    }

    @Test
    void autoConfigurationBacksOffForUserBean() {
        new ApplicationContextRunner()
                .withUserConfiguration(ApplicationSenderConfiguration.class)
                .withConfiguration(
                        AutoConfigurations.of(
                                SenderAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(Sender.class);
                    assertThat(context.getBean(Sender.class).id())
                            .isEqualTo("custom");
                    assertThat(context.containsBean("defaultSender"))
                            .isFalse();
                });
    }

    @Test
    void autoConfigurationProvidesDefaultWhenNoUserBean() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                SenderAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(Sender.class);
                    assertThat(context.getBean(Sender.class).id())
                            .isEqualTo("default");
                });
    }
}
```

**Lệnh chạy** tại project có Gradle wrapper và cấu hình `test` sử dụng JUnit Platform:

```bash
./gradlew test --tests example.overriding.BeanDefinitionOverridingTests
```

Với Maven đã tích hợp JUnit 5/Surefire:

```bash
./mvnw -Dtest=BeanDefinitionOverridingTests test
```

**Kết quả kỳ vọng:** năm test PASS; stdout chính xác tùy cấu hình Gradle/Maven và logging. Lưu ý test thứ nhất và thứ hai **đặt cờ trực tiếp** trên `DefaultListableBeanFactory` để kiểm tra đúng cơ chế registry. Trong ứng dụng Spring Boot thông thường, property `spring.main.allow-bean-definition-overriding` sẽ cấu hình chính sách tương ứng qua `SpringApplication`. Đó là hai đường thiết lập cùng một loại chính sách, không có nghĩa đọc property vào một factory tạo thủ công sẽ tự thay đổi factory ấy.

### Cách đọc từng test

1. `duplicateNameFailsWhenOverridingDisabled`: đăng ký `messageSender` lần thứ hai bị chặn, definition cũ còn lại; tên bean được nêu trong exception.
2. `enabledOverridingReplacesDefinitionInRegistry`: khi cho phép override trong tình huống registry trực tiếp, lần đăng ký sau thay definition trước; chỉ còn một definition với tên đó và instance lấy ra có hành vi `custom`.
3. `distinctNamesOfSameTypeAreNotDefinitionOverride`: hai definition **khác tên** cùng interface vẫn tồn tại khi overriding tắt; lấy bean bằng kiểu duy nhất gây lỗi không xác định được ứng viên. Phải dùng tên, qualifier hoặc primary khi thiết kế cần cả hai.
4. `autoConfigurationBacksOffForUserBean`: user bean xuất hiện; điều kiện `@ConditionalOnMissingBean(Sender.class)` ngăn default bean được đăng ký. Không có cuộc cạnh tranh trùng tên.
5. `autoConfigurationProvidesDefaultWhenNoUserBean`: thiếu user bean thì auto-configuration đăng ký implementation mặc định.

Các lớp `@AutoConfiguration` lồng trong tệp test được cung cấp tường minh qua `AutoConfigurations.of(...)`. Trong thư viện production, Spring Boot khám phá auto-configuration thông qua `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Không tự thêm cấu hình test này vào runtime ứng dụng.

## 7. Tình huống trước–sau: vì sao tắt lỗi không đồng nghĩa giải quyết lỗi

**Trước:** ứng dụng có `ApplicationSenderConfiguration` khai báo `@Bean("messageSender")` trả về `CustomSender`. Starter thứ ba cũng khai báo `@Bean("messageSender")` trả về `DefaultSender` mà không kiểm tra có bean người dùng hay chưa.

- Khi overriding bị tắt, context có thể dừng với lỗi trùng tên bean. Lỗi chỉ ra **hai nơi cùng tuyên bố sở hữu một định danh**.
- Khi bật `true`, context có thể đi tiếp với một definition thắng theo quá trình đăng ký. Nếu mặc định của starter thắng, ứng dụng có thể mất tùy chỉnh mà đội phát triển kỳ vọng. Nếu user bean thắng, vấn đề quyền sở hữu vẫn chưa được diễn đạt thành hợp đồng.
- Hành vi sẽ khó dự đoán hơn nếu version starter, điều kiện classpath hoặc đường import thay đổi.

**Sau:** starter cung cấp `@ConditionalOnMissingBean(Sender.class)`, còn ứng dụng dùng `@Bean Sender customSender()`. Vì auto-configuration được áp dụng sau các definition do người dùng khai báo, default back off; cấu hình duy nhất còn lại phản ánh rõ ý định: **starter cung cấp mặc định, ứng dụng có quyền thay**.

Nếu hai sender phục vụ **hai kênh khác nhau** và đều phải tồn tại, giải pháp không phải back-off theo toàn bộ kiểu `Sender` mà là **đặt tên riêng** và chọn tại điểm inject, ví dụ `@Qualifier("smtpSender")` và `@Qualifier("fileSender")`. Trước khi dùng điều kiện, phải xác định liệu thiết kế muốn **một bean duy nhất** hay **nhiều bean cùng tồn tại**.

## 8. Chẩn đoán lỗi đăng ký trùng tên theo thứ tự

1. **Đọc thông báo lỗi thực tế.** Với `BeanDefinitionOverrideException`, chú ý `beanName`, definition đang tồn tại, definition mới và nơi chúng được định nghĩa; nếu lỗi đến từ scanning hoặc parser, tìm loại exception tương ứng. Không đổi property trước khi biết các nguồn đăng ký.
2. **Tìm tất cả nguồn định nghĩa tên trùng.** Kiểm tra `@Bean("...")`, tên phương thức `@Bean` mặc định, `@Component("...")`, `@Named`, `@Import`, scanning, file auto-configuration imports và khai báo từ library.
3. **Xác định hợp đồng nghiệp vụ.** Chỉ một implementation hợp lệ tại một thời điểm, hay hai bean khác nhau cần cùng tồn tại? Ai sở hữu default và ai được phép tùy biến?
4. **Chọn đúng cách giải quyết.** Xóa đăng ký thừa; dùng back-off theo type/name; thêm điều kiện môi trường; hoặc đặt tên riêng và qualifier/primary. Đừng dùng cờ toàn cục thay cho quy tắc này.
5. **Kiểm tra thứ tự auto-configuration và kiểu trả về.** `@ConditionalOnMissingBean` dựa trên metadata đã được xử lý; bean có return type quá chung hoặc điều kiện đặt quá sớm có thể làm default không chịu back off. Chỉ thêm `after` khi thật sự cần giữa các auto-configuration.
6. **Test các tổ hợp tối thiểu.** Không có user bean; có user bean; có cả hai nguồn cấu hình do lỗi; các profile khác nhau; có/không có starter tùy chọn. Xác nhận **tên và instance được dùng**, không chỉ context khởi động.
7. **Giữ chính sách nghiêm ngặt sau khi sửa.** `false` cho thấy xung đột còn hay không. Nếu cần bật `true` cho một trường hợp tương thích đặc biệt, ghi rõ phạm vi, lý do, thứ tự được kiểm soát và một test xác thực definition chiến thắng; không xem đó là phương án mặc định.

Có thể chạy ứng dụng Spring Boot với chế độ debug để xem báo cáo điều kiện:

```bash
java -jar app.jar --debug
```

Lệnh giả định đã có executable JAR tên `app.jar`. Báo cáo condition hữu ích khi `@ConditionalOnMissingBean` không khớp như dự tính, nhưng một xung đột bean name không nhất thiết được giải thích hết chỉ từ condition report. Cần đối chiếu thêm lỗi bean definition và nguồn đăng ký.

Nếu đang kiểm tra cờ trong môi trường chạy thật, cú pháp command-line là:

```bash
java -jar app.jar --spring.main.allow-bean-definition-overriding=false
```

Giữ giá trị `false` khi chẩn đoán là cách để thấy rõ các xung đột thay vì để chúng bị thay thế. Không cần thêm property này vào file cấu hình nếu đã dùng giá trị mặc định.

## 9. Các hiểu lầm và lỗi phổ biến

- **“Bật `true` thì Spring tự chọn bean tốt nhất.”** Sai. Nó cho phép cơ chế đăng ký lại cùng tên; không đánh giá chất lượng, ưu tiên nghiệp vụ hay khả năng tương thích của bean thay thế.
- **“Override chỉ xảy ra khi hai class có cùng kiểu.”** Sai. Tiêu chí cốt lõi là **trùng bean name**, không bắt buộc cùng class hoặc cùng interface.
- **“Có hai bean cùng interface là bean definition overriding.”** Sai khi hai bean có tên khác nhau. Trường hợp này có thể gây nhập nhằng injection nhưng không phải collision theo tên.
- **“`@Primary` giải quyết hai bean cùng tên.”** Sai. `@Primary` chỉ ưu tiên một ứng viên theo kiểu khi nhiều bean **khác tên** cùng có thể inject.
- **“`@Qualifier` làm Spring cho phép đăng ký trùng tên.”** Sai. Qualifier phục vụ chọn ứng viên ở injection point.
- **“`@ConditionalOnMissingBean` là tên khác của overriding.”** Sai. Back-off ngăn tạo definition mặc định khi đã có bean phù hợp; overriding thay thế definition sau khi cả hai cố đăng ký cùng tên.
- **“Cứ cho auto-configuration đến sau thì nó ghi đè chắc chắn đúng.”** Sai. Thứ tự định nghĩa không phải hợp đồng chọn bean; cần điều kiện phù hợp, nhất là khi default phải nhường user bean.
- **“Test chạy xanh khi `true` tức là không còn xung đột.”** Sai. Chỉ có thể kết luận context trong điều kiện test đó đã vượt qua giai đoạn đăng ký, không có nghĩa definition bị che không làm sai hành vi.
- **“Chỉnh cờ này sẽ thay precedence của `application.yml`.”** Sai. Externalized configuration property precedence là cơ chế riêng.
- **“Mọi xung đột `@Bean` đều sinh cùng một exception.”** Không nhất thiết. Lỗi có thể xuất hiện ở scanning, parsing hoặc registry; kiểm tra stack trace và định nghĩa cụ thể.
- **“Đặt `@Profile` trên hai bean dùng cùng tên thì chúng tự động loại trừ nhau.”** Chỉ đúng nếu profile hoặc điều kiện thực sự **loại trừ** nhau trong môi trường xét; phải test tổ hợp được phép kích hoạt.
- **“Bật overriding giải quyết được dependency vòng hoặc thiếu bean.”** Không. Những vấn đề này thuộc dependency graph, cấu hình điều kiện hoặc lifecycle khác.

## 10. Bài tập tự kiểm tra

1. `@Bean("mailClient")` trong cấu hình A trả về `SmtpClient`, cấu hình B trả về `FakeClient` cũng với tên `mailClient`. Đây là lỗi gì? **Trùng bean name**; chính sách bean definition overriding liên quan.
2. Có bean `smtpClient` và `fakeClient` đều triển khai `MailClient`. Bật overriding có giải quyết `NoUniqueBeanDefinitionException` khi inject `MailClient` không? **Không.** Cần biểu diễn lựa chọn bằng `@Primary`, `@Qualifier` hoặc thay cấu trúc injection.
3. Starter cung cấp `DefaultSender`, ứng dụng muốn inject `CustomSender` thay mặc định. Cách làm phù hợp nhất? **Dùng `@ConditionalOnMissingBean(Sender.class)` tại default của auto-configuration**, bảo đảm thứ tự bean definition đúng.
4. Một team đặt `spring.main.allow-bean-definition-overriding=true` sau khi thêm dependency mới và hết lỗi khởi động. Có thể coi là đã sửa không? **Không.** Cần xác định bean nào bị thay thế, vì sao có hai definition cùng tên và hành vi nào được giữ.
5. Muốn thay đổi giá trị `demo.timeout` theo môi trường, có cần cờ này không? **Không.** Hãy dùng externalized configuration/profile/property sources, tách biệt với đăng ký bean.
6. Trong unit test `DefaultListableBeanFactory`, bật ghi đè và đăng ký lần lượt hai definition cùng tên. Kết quả của ví dụ test là gì? **Registry chỉ giữ definition mới của tên đó**, vì vậy `getBean("messageSender")` tạo `CustomSender`.
7. Khi bật `@Profile("test")` và `@Profile("prod")` trên hai definitions cùng tên, giả định điều gì phải được kiểm tra? **Hai profile không bị kích hoạt đồng thời** trong môi trường mà muốn chỉ có một bean.

## 11. Nguồn đối chiếu chính thức (baseline Spring Boot 3.3)

- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.main.allow-bean-definition-overriding`, mặc định `false`, kiểm soát đăng ký lại bean definition cùng tên.
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html): cách cấu hình chính sách bean definition overriding khi khởi động.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): `@ConditionalOnMissingBean`, thứ tự xử lý bean definition và cơ chế back-off.
- [Spring Framework — BeanDefinitionOverrideException API](https://docs.spring.io/spring-framework/docs/6.1.6/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionOverrideException.html): exception khi một bean definition mới cố đăng ký cùng tên mà overriding bị cấm.
- [Spring Framework — DefaultListableBeanFactory API](https://docs.spring.io/spring-framework/docs/6.1.6/javadoc-api/org/springframework/beans/factory/support/DefaultListableBeanFactory.html): `setAllowBeanDefinitionOverriding` và quản lý bean definitions.
