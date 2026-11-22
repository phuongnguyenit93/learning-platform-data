# Bean `@Primary` không tự làm biến mất mọi bean mặc định

**Chủ đề:** Spring Boot Auto Configuration  
**Nhóm kiến thức:** Thay thế và loại trừ (override, back-off, exclusion)  
**Câu hỏi trung tâm:** Khi ứng dụng khai báo một bean `@Primary`, vì sao Spring vẫn có thể giữ bean mặc định do auto-configuration tạo ra? Muốn bean mặc định không được đăng ký thì phải làm gì?

## 1. Kết luận cần hiểu trước

`@Primary` của Spring Framework **chỉ đánh dấu bean được ưu tiên khi có nhiều ứng viên cho một điểm tiêm dependency đơn trị**. Nó **không xóa bean khác**, không tự tắt toàn bộ auto-configuration và không tự động ngăn các phương thức `@Bean` mặc định chạy.

Ví dụ:

```java
@Bean
@Primary
MessageSender customSender() {
    return new CustomMessageSender();
}

@Bean
MessageSender defaultSender() {
    return new DefaultMessageSender();
}
```

Ở đây Spring có thể giữ **cả hai bean**: `customSender` và `defaultSender`. Khi một bean khác yêu cầu đúng một `MessageSender`, Spring thường chọn `customSender` vì nó là ứng viên `@Primary` duy nhất. Nhưng việc chọn một đối tượng để tiêm **không đồng nghĩa** bean còn lại bị gỡ khỏi `ApplicationContext`.

Nếu mong muốn **không đăng ký** `defaultSender` khi đã có bean người dùng, logic đó phải được thể hiện bằng một điều kiện phù hợp như `@ConditionalOnMissingBean(MessageSender.class)` ở phía auto-configuration. Bản thân `@Primary` không thay thế được điều kiện này.

> Phân biệt ba khái niệm: **đăng ký bean** (bean tồn tại hay không), **lựa chọn bean để inject** (bean nào được dùng tại một điểm tiêm), và **loại trừ auto-configuration** (cấu hình nào không được tham gia). Chúng diễn ra với mục tiêu khác nhau.

## 2. Hai giai đoạn khác nhau: đăng ký bean và phân giải dependency

### 2.1. Giai đoạn đăng ký định nghĩa bean

Spring đọc các cấu hình `@Configuration`, `@Bean` và auto-configuration. Mỗi phương thức có thể tạo một `BeanDefinition` nếu được phép đăng ký bởi điều kiện tương ứng.

Ví dụ, một cấu hình mặc định không có condition:

```java
@AutoConfiguration
class SenderAutoConfiguration {

    @Bean
    DefaultMessageSender defaultSender() {
        return new DefaultMessageSender();
    }
}
```

Chừng nào cấu hình được áp dụng và không có ràng buộc khác ngăn nó, `defaultSender` vẫn được đăng ký. Việc ứng dụng có `@Primary CustomMessageSender` không phải điều kiện loại bỏ bean này.

Nếu muốn mặc định chỉ xuất hiện khi chưa có loại dịch vụ tương ứng:

```java
@AutoConfiguration
class SenderAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    DefaultMessageSender defaultSender() {
        return new DefaultMessageSender();
    }
}
```

`@ConditionalOnMissingBean(MessageSender.class)` kiểm tra bean đáp ứng yêu cầu kiểu `MessageSender` đã được nhận diện ở giai đoạn đánh giá condition. Một bean người dùng thuộc kiểu đó, dù **có hay không có `@Primary`**, vẫn có thể làm fallback không được đăng ký.

### 2.2. Giai đoạn giải quyết một dependency đơn

Khi một consumer cần một `MessageSender`, Spring phải chọn ứng viên:

```java
final class NotificationService {
    private final MessageSender sender;

    NotificationService(MessageSender sender) {
        this.sender = sender;
    }
}
```

Nếu có hai bean cùng kiểu và chỉ `customSender` là `@Primary`, quá trình autowire có thể chọn `customSender`. Nhưng toàn bộ bean vẫn hiện diện trong factory.

Sơ đồ:

```text
Configuration + Auto-configuration
           |
           v
    Đánh giá điều kiện đăng ký
           |
           +-- customSender  [@Primary] --------+
           |                                    |
           +-- defaultSender [không @Primary] --+--> BeanFactory có 2 bean
                                                 |
                                    Injection cần 1 MessageSender
                                                 |
                                      Chọn customSender
                                                 |
                            defaultSender vẫn có thể được truy cập
```

**Mấu chốt:** `@Primary` hỗ trợ lựa chọn ứng viên đã tồn tại. Nó không có vai trò “dọn dẹp” các bean khác khỏi `BeanFactory`.

## 3. Các tình huống cần phân biệt

Xét `MessageSender` là interface; `CustomMessageSender` và `DefaultMessageSender` đều implements interface này.

| Bean do ứng dụng cung cấp | Quy tắc bean mặc định | Số bean `MessageSender` thường có | Kết quả |
| --- | --- | ---: | --- |
| `@Primary CustomMessageSender` | `@Bean DefaultMessageSender` không condition | 2 | Custom được ưu tiên khi inject đơn, default vẫn tồn tại |
| `CustomMessageSender` không `@Primary` | `@Bean DefaultMessageSender` không condition | 2 | Inject đơn theo type có thể mơ hồ; cần qualifier/primary |
| `@Primary CustomMessageSender` | `@ConditionalOnMissingBean(MessageSender.class)` | 1 | Default nhường chỗ vì đã có bean phù hợp kiểu interface |
| `CustomMessageSender` không `@Primary` | `@ConditionalOnMissingBean(MessageSender.class)` | 1 | Default cũng nhường chỗ; `@Primary` không phải điều kiện cần |
| `@Primary CustomMessageSender` | `@ConditionalOnMissingBean(DefaultMessageSender.class)` | 2 | Chưa có đúng kiểu `DefaultMessageSender` nên default vẫn được đăng ký |
| Không có `MessageSender` của ứng dụng | `@ConditionalOnMissingBean(MessageSender.class)` | 1 | Default được đăng ký làm fallback |

Bảng giả định cấu hình người dùng được xử lý **trước** auto-configuration và các bean có kiểu được suy luận chính xác. Trong dự án thật, thứ tự đăng ký, kiểu trả về phương thức `@Bean`, phạm vi `ApplicationContext` và điều kiện khác có thể tác động kết quả.

Điểm dễ nhầm nhất nằm ở hai điều kiện sau:

```java
@ConditionalOnMissingBean(MessageSender.class)
```

và

```java
@ConditionalOnMissingBean(DefaultMessageSender.class)
```

Chúng **không giống nhau**. Điều kiện đầu tiên có nghĩa “không có bean nào phù hợp interface `MessageSender`”; điều kiện thứ hai có nghĩa “chưa có bean phù hợp implementation `DefaultMessageSender`”. Nếu người dùng đã khai báo `CustomMessageSender`, điều kiện theo implementation vẫn có thể khớp và tạo thêm default.

## 4. `@Primary` tác động đến đâu?

Theo Spring Framework, `@Primary` có tác dụng trong các trường hợp có **nhiều ứng viên cùng phù hợp cho dependency đơn**. Nếu chỉ có một bean phù hợp, không cần `@Primary` để chọn. Nếu có đúng một ứng viên `@Primary` trong số các ứng viên phù hợp, ứng viên đó thường được ưu tiên.

Ví dụ:

```java
@Bean
@Primary
MessageSender customSender() {
    return new CustomMessageSender();
}

@Bean
MessageSender defaultSender() {
    return new DefaultMessageSender();
}
```

Kết quả:

- `NotificationService(MessageSender sender)` có thể nhận `customSender`.
- `applicationContext.getBean("defaultSender")` vẫn có thể lấy bean mặc định.
- Tiêm `List<MessageSender>`, `Map<String, MessageSender>` hoặc mảng theo kiểu thường vẫn nhận các bean phù hợp, kể cả bean không `@Primary`.
- `@Qualifier("defaultSender")` là một cách chọn rõ bean mặc định tại điểm tiêm tương ứng; không nên kỳ vọng `@Primary` luôn lấn át qualifier chỉ định rõ.

Ví dụ consumer cần chọn mặc định dù một ứng viên khác là primary:

```java
@Bean
NotificationService defaultNotificationService(
        @Qualifier("defaultSender") MessageSender sender) {
    return new NotificationService(sender);
}
```

Đoạn mã là minh họa bên trong một configuration và cần các lớp `NotificationService`/`MessageSender` đã được định nghĩa. `@Qualifier` có thể thu hẹp tập ứng viên trước bước chọn primary.

**Nếu có hai bean đều đánh dấu `@Primary` cho cùng một dependency** và không còn cách chọn đơn trị, Spring có thể báo lỗi mơ hồ ứng viên. Việc thêm `@Primary` bừa bãi không bảo đảm sửa được `NoUniqueBeanDefinitionException`; hãy kiểm tra cả số bean, qualifier, name và điểm injection.

`@Primary` có thể đặt trên phương thức `@Bean` hoặc trên lớp component phù hợp. Với bean được tạo qua phương thức `@Bean`, cách trực tiếp và rõ ràng là đặt `@Primary` lên **chính phương thức factory**.

## 5. Chạy kiểm thử: `@Primary` lựa chọn bean nhưng không xóa bean

Bài thực hành dưới đây dùng **Java 17**, **Spring Boot 3.3.5**, **JUnit 5**, `ApplicationContextRunner`. Nó xác minh cùng một ứng dụng có thể chứa hai bean nhưng injection vẫn chọn được primary. Sau đó thay đổi điều kiện fallback để thấy sự khác biệt trong **số bean thực sự được đăng ký**.

### 5.1. Tạo dự án Maven

Cấu trúc:

```text
primary-vs-default-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── PrimaryAndDefaultBeanTest.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>primary-vs-default-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 5.2. Viết test hoàn chỉnh

Tạo tệp `src/test/java/demo/PrimaryAndDefaultBeanTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnSingleCandidate;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import static org.assertj.core.api.Assertions.assertThat;

class PrimaryAndDefaultBeanTest {

    interface Formatter {
        String format(String text);
    }

    static final class CustomFormatter implements Formatter {
        @Override
        public String format(String text) {
            return "custom:" + text;
        }
    }

    static final class DefaultFormatter implements Formatter {
        @Override
        public String format(String text) {
            return "default:" + text;
        }
    }

    record Selection(String value) {
    }

    @Configuration(proxyBeanMethods = false)
    static class UserPrimaryConfiguration {
        @Bean
        @Primary
        CustomFormatter customFormatter() {
            return new CustomFormatter();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserWithoutPrimaryConfiguration {
        @Bean
        CustomFormatter customFormatter() {
            return new CustomFormatter();
        }
    }

    @AutoConfiguration
    static class UnconditionalDefaultAutoConfiguration {
        @Bean
        DefaultFormatter defaultFormatter() {
            return new DefaultFormatter();
        }
    }

    @AutoConfiguration
    static class InterfaceFallbackAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(Formatter.class)
        DefaultFormatter defaultFormatter() {
            return new DefaultFormatter();
        }
    }

    @AutoConfiguration
    static class ConcreteFallbackAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(DefaultFormatter.class)
        DefaultFormatter defaultFormatter() {
            return new DefaultFormatter();
        }
    }

    @AutoConfiguration(after = UnconditionalDefaultAutoConfiguration.class)
    static class SingleCandidateAutoConfiguration {
        @Bean
        @ConditionalOnSingleCandidate(Formatter.class)
        Selection selection(Formatter formatter) {
            return new Selection(formatter.format("hello"));
        }
    }

    @Test
    void primaryChoosesSingleInjectionButLeavesDefaultBean() {
        new ApplicationContextRunner()
                .withUserConfiguration(UserPrimaryConfiguration.class)
                .withConfiguration(AutoConfigurations.of(
                        UnconditionalDefaultAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(Formatter.class))
                            .containsKeys("customFormatter", "defaultFormatter")
                            .hasSize(2);
                    assertThat(context.getBean(Formatter.class))
                            .isInstanceOf(CustomFormatter.class);
                    assertThat(context.getBean("defaultFormatter"))
                            .isInstanceOf(DefaultFormatter.class);
                });
    }

    @Test
    void fallbackByInterfaceBacksOffEvenIfUserBeanIsPrimary() {
        new ApplicationContextRunner()
                .withUserConfiguration(UserPrimaryConfiguration.class)
                .withConfiguration(AutoConfigurations.of(
                        InterfaceFallbackAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(Formatter.class);
                    assertThat(context).doesNotHaveBean("defaultFormatter");
                    assertThat(context.getBean(Formatter.class))
                            .isInstanceOf(CustomFormatter.class);
                });
    }

    @Test
    void fallbackByInterfaceAlsoBacksOffWithoutPrimary() {
        new ApplicationContextRunner()
                .withUserConfiguration(UserWithoutPrimaryConfiguration.class)
                .withConfiguration(AutoConfigurations.of(
                        InterfaceFallbackAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(Formatter.class);
                    assertThat(context).doesNotHaveBean("defaultFormatter");
                });
    }

    @Test
    void fallbackByConcreteTypeStillCreatesDefaultBean() {
        new ApplicationContextRunner()
                .withUserConfiguration(UserPrimaryConfiguration.class)
                .withConfiguration(AutoConfigurations.of(
                        ConcreteFallbackAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(Formatter.class)).hasSize(2);
                    assertThat(context).hasBean("defaultFormatter");
                    assertThat(context.getBean(Formatter.class))
                            .isInstanceOf(CustomFormatter.class);
                });
    }

    @Test
    void fallbackCreatesDefaultWhenNoUserBeanExists() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        InterfaceFallbackAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(Formatter.class);
                    assertThat(context.getBean(Formatter.class))
                            .isInstanceOf(DefaultFormatter.class);
                });
    }

    @Test
    void singleCandidateConditionCanUsePrimaryAmongTwoBeans() {
        new ApplicationContextRunner()
                .withUserConfiguration(UserPrimaryConfiguration.class)
                .withConfiguration(AutoConfigurations.of(
                        UnconditionalDefaultAutoConfiguration.class,
                        SingleCandidateAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(Formatter.class)).hasSize(2);
                    assertThat(context).hasSingleBean(Selection.class);
                    assertThat(context.getBean(Selection.class).value())
                            .isEqualTo("custom:hello");
                });
    }

    @Test
    void singleCandidateConditionDoesNotMatchTwoNonPrimaryBeans() {
        new ApplicationContextRunner()
                .withUserConfiguration(UserWithoutPrimaryConfiguration.class)
                .withConfiguration(AutoConfigurations.of(
                        UnconditionalDefaultAutoConfiguration.class,
                        SingleCandidateAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(Formatter.class)).hasSize(2);
                    assertThat(context).doesNotHaveBean(Selection.class);
                });
    }
}
```

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn test
```

**Kết quả dự kiến:** cả bảy test đều qua. Maven Surefire thường hiển thị một dòng tương tự:

```text
Tests run: 7, Failures: 0, Errors: 0, Skipped: 0
```

Mã không gọi `System.out.println`, vì vậy không có stdout riêng cần so khớp; log Maven có thể khác tùy phiên bản và môi trường.

Kết quả mà các assertion kiểm tra:

1. Bean do người dùng đặt `@Primary` được chọn cho lookup đơn theo `Formatter`, nhưng bean mặc định **vẫn tồn tại** nếu auto-configuration đăng ký nó vô điều kiện.
2. Điều kiện `@ConditionalOnMissingBean(Formatter.class)` **nhường chỗ** khi đã có `CustomFormatter`; việc bean đó có `@Primary` hay không không đổi kết luận.
3. Nếu condition chỉ tìm `DefaultFormatter`, sự hiện diện của `CustomFormatter` không chặn việc đăng ký một `DefaultFormatter` khác.
4. Khi không có `Formatter` nào do người dùng khai báo, fallback theo interface được đăng ký.
5. `@ConditionalOnSingleCandidate(Formatter.class)` là **một điều kiện khác**: nó có thể khớp khi có nhiều bean cùng kiểu nhưng có một primary đủ để xác định ứng viên đơn; không có primary, hai ứng viên làm điều kiện đó không khớp.

Thí nghiệm tách các nhánh thành nhiều `ApplicationContextRunner` để tránh bean từ bài test này can thiệp bài test khác. Thứ tự xử lý cho `SingleCandidateAutoConfiguration` được khai báo `after = UnconditionalDefaultAutoConfiguration.class` để kiểm tra sau khi default đã được thêm vào.

## 6. Vì sao điều kiện `@ConditionalOnMissingBean` có thể không loại được default?

Có ít nhất bốn nguyên nhân phổ biến, và không nguyên nhân nào được tự động chữa bằng `@Primary`.

### 6.1. Auto-configuration không có condition phù hợp

```java
@Bean
DefaultFormatter defaultFormatter() {
    return new DefaultFormatter();
}
```

Phương thức này đăng ký bean theo cấu hình; `@Primary CustomFormatter` không chặn nó. Phải sửa **logic đăng ký** nếu đó là bean của module mình quản lý, hoặc cấu hình cách tắt/loại trừ auto-configuration khi làm việc với thư viện.

### 6.2. Condition kiểm tra sai kiểu

So sánh:

```java
// Chỉ bỏ fallback nếu đã có implementation cụ thể này:
@ConditionalOnMissingBean(DefaultFormatter.class)

// Bỏ fallback nếu đã có bất kỳ Formatter thích hợp nào:
@ConditionalOnMissingBean(Formatter.class)
```

Nếu contract của thư viện là “người dùng có thể thay thế bằng implementation bất kỳ của `Formatter`”, điều kiện theo interface phù hợp hơn. Nếu thư viện thực sự cần đăng ký một `DefaultFormatter` dù đã có formatter khác, condition theo implementation là một chính sách khác, và có thể hoàn toàn có chủ đích.

### 6.3. Condition chỉ biết bean definition đã xử lý đến lúc đó

`@ConditionalOnMissingBean` **không phải phép quét tương lai**. Nó xét những định nghĩa bean đã được nhận diện khi đánh giá. Vì vậy:

- Đặt condition ở auto-configuration, nơi cấu hình ứng dụng thường được xử lý trước.
- Nếu auto-configuration A cung cấp một bean và auto-configuration B phụ thuộc vào sự hiện diện của bean đó, khai báo thứ tự phù hợp với `@AutoConfiguration(after = ...)` hoặc cơ chế thứ tự tương ứng.
- Bộc lộ kiểu đủ cụ thể trong chữ ký `@Bean`. Một `@Bean Formatter formatter()` trả về `new DefaultFormatter()` không nhất thiết giúp condition tìm `DefaultFormatter.class` biết được implementation tại thời điểm bean chưa được khởi tạo.

`@Primary` không bổ sung thông tin kiểu implementation vào chữ ký phương thức factory và không khiến condition đã chạy trước được đánh giá lại.

### 6.4. Condition có phạm vi tìm kiếm khác dự kiến

`@ConditionalOnMissingBean` có các tùy chọn như `value`, `type`, `name`, `annotation`, `ignored`, `search`. Điều kiện theo tên khác điều kiện theo type. Thuộc tính `search` có thể giới hạn phạm vi tìm bean trong phân cấp parent/child contexts.

Ví dụ:

```java
@ConditionalOnMissingBean(name = "defaultFormatter")
```

Điều này kiểm tra sự vắng mặt của **tên** `defaultFormatter`, không phải sự vắng mặt của mọi implementation `Formatter`. Bean `customFormatter` dù `@Primary` vẫn không làm điều kiện theo tên trên tự thất bại.

Trong trường hợp có parent context hoặc bean được cấu hình không phải autowire candidate, cần đọc đúng API của phiên bản đang dùng và quan sát Condition Evaluation Report; đừng suy đoán chỉ dựa trên annotation `@Primary`.

## 7. `@ConditionalOnSingleCandidate`: trường hợp `@Primary` thực sự ảnh hưởng đến condition

Điều kiện `@ConditionalOnSingleCandidate(Formatter.class)` trả lời câu hỏi:

> “Ở thời điểm kiểm tra, Spring có thể xác định một ứng viên duy nhất để inject cho `Formatter` không?”

Nếu có **đúng một bean** phù hợp, điều kiện khớp. Nếu có **nhiều bean** nhưng một bean primary thích hợp, điều kiện cũng có thể khớp. Nếu có nhiều ứng viên ngang nhau, điều kiện thường không khớp.

Đây là điểm khác biệt với `@ConditionalOnMissingBean`, vốn hỏi liệu có bean thỏa yêu cầu hay chưa:

| Điều kiện | Có `CustomFormatter @Primary` + `DefaultFormatter` | Ý nghĩa |
| --- | --- | --- |
| `@ConditionalOnMissingBean(Formatter.class)` | Không khớp | Vì đã có bean loại `Formatter` |
| `@ConditionalOnBean(Formatter.class)` | Khớp | Vì đã có bean loại `Formatter` |
| `@ConditionalOnSingleCandidate(Formatter.class)` | Có thể khớp | Vì một primary giúp phân giải ứng viên đơn |
| Inject một `Formatter` không qualifier | Thường chọn custom | Do ưu tiên primary |
| Inject `List<Formatter>` | Thường có cả hai | Primary không tự lọc collection |

Vì vậy, `@Primary` **có thể là tín hiệu cho một điều kiện chọn ứng viên đơn**, nhưng nó **không phải điều kiện xóa fallback**. Khi dùng `@ConditionalOnSingleCandidate`, vẫn phải bảo đảm thứ tự auto-configuration và khả năng suy luận kiểu.

## 8. Ba mục tiêu thay thế khác nhau và cơ chế phù hợp

### Mục tiêu A: Giữ nhiều implementation nhưng chọn một cái mặc định khi inject

Dùng `@Primary` hoặc `@Qualifier`:

```java
@Bean
@Primary
Formatter customFormatter() {
    return new CustomFormatter();
}
```

Nếu cần cả default và custom ở các luồng khác nhau, đây có thể là thiết kế hợp lý. Consumer nhận collection vẫn có thể nhìn thấy cả hai.

### Mục tiêu B: Có user bean thì không tạo fallback của starter

Đặt điều kiện trên bean mặc định thuộc auto-configuration mình kiểm soát:

```java
@Bean
@ConditionalOnMissingBean(Formatter.class)
DefaultFormatter defaultFormatter() {
    return new DefaultFormatter();
}
```

Với kiểu trả về `DefaultFormatter`, container có thông tin kiểu cụ thể; với target condition `Formatter.class`, fallback nhường chỗ cho một implementation khác của interface. Hai quyết định thiết kế được khai báo rõ ràng.

### Mục tiêu C: Tắt hẳn một auto-configuration cụ thể

Khi không muốn một cấu hình tự động của Spring Boot tham gia, hãy dùng cơ chế **exclude** đúng class auto-configuration:

```java
@SpringBootApplication(
    exclude = SomeLibraryAutoConfiguration.class
)
public class Application {
}
```

Đây là đoạn minh họa, cần class `SomeLibraryAutoConfiguration` có thật, và không phải một chương trình chạy độc lập. Trong ứng dụng thực tế, phải loại đúng auto-configuration được công bố là có thể exclude; không dùng một tên class giả.

Một cách khác là khai báo tên class cấu hình cần loại bằng:

```properties
spring.autoconfigure.exclude=com.example.library.SomeLibraryAutoConfiguration
```

Lệnh cấu hình này cũng mang tính minh họa: class phải đúng với thư viện đang dùng. Không được tùy tiện exclude cấu hình chứa nhiều hạ tầng khác mà chưa xem tác động. Nếu starter có property bật/tắt chính thức, ưu tiên cơ chế đó khi phù hợp.

**Không nhầm với bean definition overriding:** hai bean khác tên nhưng cùng interface có thể cùng tồn tại mà không cần bật `spring.main.allow-bean-definition-overriding`. Cho phép overriding theo tên không giải quyết tổng quát vấn đề hai bean cùng loại.

## 9. Cách chẩn đoán khi thấy “đã @Primary nhưng bean default vẫn tồn tại”

Hãy kiểm tra có thứ tự:

1. **Đếm và liệt kê bean theo kiểu.** `applicationContext.getBeansOfType(Formatter.class)` cho biết số và tên bean thực tế sau khi context được khởi tạo.
2. **Xác định bean nào primary.** Kiểm tra `@Primary` trên phương thức `@Bean`/component hoặc metadata bean definition; đừng suy ra từ tên bean.
3. **Xác định điểm injection.** Đó là một dependency đơn, `List`, `Map`, `ObjectProvider` hay một dependency có `@Qualifier`? Cách chọn ứng viên có thể khác nhau.
4. **Đọc logic tạo default.** Nó không có condition, dùng `@ConditionalOnMissingBean` theo interface, implementation hay tên, hoặc còn các điều kiện khác?
5. **Xem thứ tự và return type.** Khi condition chạy, bean người dùng hoặc bean của auto-configuration trước đã được nhận diện chưa? Chữ ký `@Bean` có bộc lộ loại được condition tìm không?
6. **Đọc Condition Evaluation Report** bằng `--debug`, Actuator `/actuator/conditions` nếu đã bật/expose phù hợp, hoặc listener trong `ApplicationContextRunner`. Tìm kết quả của `OnBeanCondition` để biết vì sao fallback được đăng ký.
7. **Viết phép thử tối thiểu** cho hai trường hợp: không có user bean và có user bean. Nếu test cần nhiều bean, thêm test khẳng định `@Primary` chỉ quyết định injection.

Ví dụ kiểm tra bean sau startup trong một context đã có:

```java
Map<String, Formatter> beans =
        applicationContext.getBeansOfType(Formatter.class);

beans.forEach((name, bean) ->
        System.out.println(name + " = " + bean.getClass().getSimpleName()));
```

Đây là đoạn mã minh họa bên trong phương thức Java, cần biến `applicationContext` kiểu `ApplicationContext` và interface `Formatter` của ứng dụng. Tên bean và thứ tự duyệt không nên được dùng như hợp đồng thứ tự mặc định; kiểm tra membership theo tên và type sẽ ổn định hơn.

## 10. Những lỗi thường gặp

**Lỗi 1 — “Tôi đã `@Primary`, vậy Boot sẽ không tạo bean mặc định.”**  
Sai vì `@Primary` điều khiển ưu tiên injection, không phải chính sách đăng ký bean. Xem `@ConditionalOnMissingBean` và các condition của starter.

**Lỗi 2 — “Có hai bean cùng interface chắc chắn lỗi startup.”**  
Không hẳn. Hai bean cùng loại có thể tồn tại bình thường; lỗi thường xuất hiện khi có một điểm injection đơn không phân giải được ứng viên. Primary hoặc qualifier có thể làm dependency rõ ràng.

**Lỗi 3 — “`@ConditionalOnMissingBean(DefaultFormatter.class)` sẽ nhường chỗ cho mọi implementation của `Formatter`.”**  
Không. Nó chỉ xét yêu cầu loại `DefaultFormatter`. Muốn chính sách “bất kỳ formatter nào” thì kiểm tra `Formatter.class`.

**Lỗi 4 — “Tất cả bean mặc định của Spring Boot sẽ biến mất khi tạo một bean primary.”**  
Không. Các auto-configuration/bean khác có condition khác nhau, và primary không phải một công tắc toàn cục.

**Lỗi 5 — “Chỉ cần bật `spring.main.allow-bean-definition-overriding=true`.”**  
Cờ này liên quan đến định nghĩa bean trùng tên, không tự động gỡ các bean khác tên cùng interface và có thể che giấu lỗi thiết kế.

**Lỗi 6 — “Một `List<Formatter>` sẽ chỉ chứa bean primary.”**  
Không. Dependency tập hợp thường bao gồm tất cả bean phù hợp theo điều kiện phân giải, chứ không lọc chỉ primary.

**Lỗi 7 — “Thêm `@Primary` sửa được mọi `NoUniqueBeanDefinitionException`.”**  
Không. Nếu có nhiều primary, qualifier xung đột, kiểu bean không phù hợp hoặc điểm injection cần lựa chọn khác, vẫn có thể lỗi.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Auto-configuration có `@Bean DefaultFormatter defaultFormatter()` không condition. Người dùng thêm `@Primary CustomFormatter customFormatter()`. Có bao nhiêu bean `Formatter`?  
**Trả lời:** Thông thường **hai**. `@Primary` quyết định ứng viên ưu tiên cho injection đơn, không xóa `defaultFormatter`.

**Câu 2.** Đổi factory mặc định thành `@ConditionalOnMissingBean(Formatter.class)`. Có còn default khi custom đã tồn tại và được nhận diện trước điều kiện?  
**Trả lời:** Không. Condition theo interface không khớp vì đã có `Formatter`; hiệu ứng này **không đòi hỏi** custom phải `@Primary`.

**Câu 3.** Nếu condition lại là `@ConditionalOnMissingBean(DefaultFormatter.class)` thì sao?  
**Trả lời:** `CustomFormatter` không thỏa kiểu `DefaultFormatter`, nên bean mặc định **có thể tiếp tục được đăng ký**. Hai bean tồn tại; primary vẫn có thể là lựa chọn cho injection `Formatter` đơn.

**Câu 4.** Khi có hai bean `Formatter` và một primary, `@ConditionalOnSingleCandidate(Formatter.class)` có thể khớp không?  
**Trả lời:** Có, vì một primary có thể làm ứng viên đơn được xác định. Condition này khác với `@ConditionalOnMissingBean`.

**Câu 5.** Muốn consumer nhận đúng bean mặc định dù đã có primary khác thì dùng gì?  
**Trả lời:** Dùng `@Qualifier` hoặc một cách chỉ định bean tương thích rõ ràng tại điểm injection; đừng cố xóa `@Primary` trên bean không liên quan.

**Câu 6.** Muốn loại bỏ toàn bộ auto-configuration của một thư viện, nên đặt `@Primary` ở đâu?  
**Trả lời:** Không dùng `@Primary` cho mục đích này. Dùng cơ chế cấu hình/condition chính thức của thư viện hoặc exclude đúng auto-configuration, sau khi xem các bean bị ảnh hưởng.

## 12. Tổng kết kiến thức

`@Primary` có nhiệm vụ **ưu tiên chọn bean** trong một tập ứng viên khi inject một dependency đơn trị. Nó **không quyết định số bean được đăng ký** và không tự loại các bean mặc định khác.

Để thiết kế khả năng tùy biến của Spring Boot đúng:

1. Xác định contract thay thế: theo **interface**, **implementation** hay **tên**.
2. Đặt `@ConditionalOnMissingBean` phù hợp trên cấu hình fallback, kiểm soát thứ tự xử lý và khai báo kiểu trả về đủ thông tin.
3. Dùng `@Primary` khi mục đích là ưu tiên một bean trong nhiều bean cùng tồn tại.
4. Dùng `@ConditionalOnSingleCandidate` khi điều kiện cần “có thể xác định một ứng viên để autowire”, có tính đến primary.
5. Dùng property/exclude auto-configuration khi mục đích là tắt hẳn cơ chế đăng ký, không cố dùng `@Primary` như công tắc tắt.

### Tài liệu tham khảo chính thức

- [Spring Framework — Fine-tuning Annotation-based Autowiring with `@Primary`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [Spring Framework — Javadoc `@Primary`](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/context/annotation/Primary.html)
- [Spring Boot — Creating Your Own Auto-configuration, Bean Conditions](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Javadoc `@ConditionalOnMissingBean`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Spring Boot 3.3 — Javadoc `@ConditionalOnSingleCandidate`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html)
