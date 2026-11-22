# BeanDefinitionOverrideException do đăng ký trùng tên ngoài cơ chế nhường chỗ

`BeanDefinitionOverrideException` xuất hiện khi Spring cố đăng ký một `BeanDefinition` mới bằng **tên đã được dùng trong cùng BeanFactory**, trong khi chính sách ghi đè đang tắt. Với Spring Boot 3.3, `spring.main.allow-bean-definition-overriding` mặc định là `false`, vì vậy xung đột tên thường làm ApplicationContext khởi động thất bại ngay trong giai đoạn đăng ký bean definition.

Trong custom starter, lỗi này thường xuất hiện khi bean mặc định của auto-configuration và bean do ứng dụng khai báo cùng chiếm một tên, nhưng điều kiện `@ConditionalOnMissingBean` không nhận diện được bean của ứng dụng. Nó cũng có thể đến từ hai lớp `@Configuration`, hai component được scan hoặc hai module cùng khai báo một tên bean.

**Cần phân biệt hai lỗi:**

- `BeanDefinitionOverrideException`: hai bean definition tranh cùng một **tên**; lỗi xảy ra khi đăng ký definition.
- `NoUniqueBeanDefinitionException`: nhiều bean có **cùng kiểu nhưng tên khác nhau**; context có thể khởi động, nhưng một điểm inject theo kiểu không xác định được bean cần dùng.

`@Primary` và `@Qualifier` giúp giải quyết trường hợp thứ hai. Chúng không giải quyết xung đột hai definition cùng tên.

## 1. Bean name được tạo như thế nào?

Spring quản lý bean bằng một định danh trong registry. Tên này có thể được khai báo trực tiếp hoặc sinh theo quy ước.

| Cách khai báo | Tên mặc định hoặc tên được dùng |
| --- | --- |
| `@Bean` trên method `paymentGateway()` | `paymentGateway` |
| `@Bean("partnerGateway")` | `partnerGateway` |
| `@Bean(name = {"gateway", "paymentGateway"})` | `gateway` là bean name chính; `paymentGateway` là alias |
| `@Component` trên class `PaymentGatewayClient` | `paymentGatewayClient` theo component-name convention |
| `@Component("gateway")` | `gateway` |
| XML `<bean id="gateway" ...>` | `gateway` |
| Đăng ký qua `BeanDefinitionRegistry` | Tên được truyền vào thao tác đăng ký |

Tên method `@Bean` là một nguồn xung đột dễ bị bỏ sót. Hai method ở hai configuration class khác nhau vẫn có thể sinh cùng bean name nếu cùng tên method hoặc cùng khai báo `@Bean("...")`.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class LocalGatewayConfiguration {
    @Bean
    PaymentGateway paymentGateway() {
        return new LocalPaymentGateway();
    }
}

@Configuration(proxyBeanMethods = false)
class PartnerGatewayConfiguration {
    @Bean
    PaymentGateway paymentGateway() {
        return new PartnerPaymentGateway();
    }
}
```

Cả hai method đều đăng ký bean tên `paymentGateway`. Việc hai object có class khác nhau không làm cho hai tên trở thành duy nhất. Nếu ứng dụng cần cả hai implementation, hãy đặt hai tên khác nhau và inject bằng `@Qualifier`, hoặc inject một collection/map các bean cùng kiểu.

Một bean có thể có alias. Alias cũng chiếm một tên trong registry; không dùng một alias làm tên chính cho bean khác.

## 2. `BeanDefinitionOverrideException` thực sự báo điều gì?

`BeanDefinitionOverrideException` là một subclass của `BeanDefinitionStoreException`. Nó mô tả một lần đăng ký definition không hợp lệ, thường là một definition mới được đăng ký bằng tên đã có trong registry trong lúc overriding bị tắt.

Exception cung cấp các thông tin hữu ích:

- `getBeanName()`: tên đang bị trùng.
- `getBeanDefinition()`: definition mới đang được đăng ký.
- `getExistingDefinition()`: definition đã chiếm tên trước đó.
- `getResourceDescription()`: nguồn mô tả của definition mới.

Thông báo thường có dạng:

```text
The bean 'paymentGateway' could not be registered.
A bean with that name has already been defined in ...
and overriding is disabled.
```

Chi tiết thông báo phụ thuộc phiên bản và nguồn đăng ký. Hãy lấy tên bean trong exception làm điểm bắt đầu, sau đó tìm **cả definition cũ lẫn definition mới**. Chỉ nhìn tên class trong stack trace thường chưa đủ để xác định module nào đã đăng ký bean trước.

### 2.1. Chính sách mặc định của Spring Boot

Trong Spring Boot 3.3, thuộc tính:

```properties
spring.main.allow-bean-definition-overriding=false
```

có giá trị mặc định `false`. Khi để `false`, một lần đăng ký bean definition khác cùng tên sẽ bị từ chối.

Có thể bật:

```properties
spring.main.allow-bean-definition-overriding=true
```

Khi bật, definition được đăng ký sau có thể thay definition đã có. Kết quả phụ thuộc thứ tự đăng ký và có thể che giấu xung đột do component scan, import hoặc starter. Đây là một chính sách thay thế toàn cục cho ứng dụng, không phải cách sửa condition của auto-configuration.

**Lưu ý về Spring Framework thuần:** `DefaultListableBeanFactory` có giá trị mặc định riêng là cho phép bean definition overriding. Spring Boot đặt chính sách mặc định của ứng dụng Boot thành `false`. Vì vậy không suy rộng giá trị mặc định của bean factory thuần sang Spring Boot.

## 3. Vì sao cơ chế backoff có thể không ngăn được lỗi?

`@ConditionalOnMissingBean` là cơ chế để auto-configuration chỉ đăng ký bean mặc định khi bean phù hợp chưa tồn tại. Annotation có thể kiểm tra theo kiểu hoặc theo tên.

### 3.1. Backoff theo kiểu

Ví dụ auto-configuration:

```java
@AutoConfiguration
public class GatewayAutoConfiguration {
    @Bean("paymentGateway")
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway defaultGateway() {
        return new DefaultPaymentGateway();
    }
}
```

Ứng dụng cung cấp implementation riêng:

```java
@Configuration(proxyBeanMethods = false)
class UserGatewayConfiguration {
    @Bean("partnerGateway")
    PaymentGateway partnerGateway() {
        return new PartnerPaymentGateway();
    }
}
```

Mặc dù tên bean người dùng là `partnerGateway`, kiểu `PaymentGateway` đã có. Điều kiện theo kiểu không khớp, nên method `defaultGateway()` không đăng ký bean mặc định. Chỉ có `partnerGateway`.

Đây thường là contract phù hợp cho starter: ứng dụng được tự chọn bean name, miễn là cung cấp implementation của kiểu mở rộng mà starter công bố.

### 3.2. Backoff theo tên

Giả sử auto-configuration khai báo:

```java
@Bean("paymentGateway")
@ConditionalOnMissingBean(name = "paymentGateway")
PaymentGateway defaultGateway() {
    return new DefaultPaymentGateway();
}
```

Nếu ứng dụng khai báo `partnerGateway` cùng kiểu `PaymentGateway`, điều kiện theo tên vẫn khớp vì chưa có bean mang tên `paymentGateway`. Kết quả là hai bean cùng kiểu nhưng khác tên.

Context có thể khởi động thành công, nhưng inject `PaymentGateway` mà không chỉ định qualifier có thể ném `NoUniqueBeanDefinitionException`. Đây không phải `BeanDefinitionOverrideException`, bởi registry không có hai definition cùng tên.

Chỉ dùng condition theo tên khi **bean name chính là contract** mà starter yêu cầu. Nếu muốn người dùng có thể đặt tên tùy ý, ưu tiên condition theo kiểu.

### 3.3. Condition kiểm tra kiểu không phát hiện được tên đã bị chiếm bởi kiểu khác

Đây là trường hợp dễ tạo ra `BeanDefinitionOverrideException` dù đã có `@ConditionalOnMissingBean`:

```java
@Configuration(proxyBeanMethods = false)
class UserConfiguration {
    @Bean("paymentGateway")
    String paymentGatewayAlias() {
        return "reserved-name";
    }
}
```

Trong khi đó, auto-configuration có:

```java
@Bean("paymentGateway")
@ConditionalOnMissingBean(PaymentGateway.class)
PaymentGateway defaultGateway() {
    return new DefaultPaymentGateway();
}
```

Bean hiện có tên `paymentGateway` nhưng kiểu khai báo là `String`. Condition kiểm tra `PaymentGateway.class`, không tìm thấy bean phù hợp nên cho phép method default chạy. Khi Spring đăng ký definition mới cũng mang tên `paymentGateway`, registry phát hiện tên đã được sử dụng và ném exception.

Điều kiện theo kiểu trả lời câu hỏi “đã có bean kiểu này chưa?”. Nó không phải một khóa bảo vệ mọi bean name mà method `@Bean` sắp dùng.

### 3.4. Return type của `@Bean` ảnh hưởng đến điều kiện theo kiểu

Spring Boot khuyến nghị khai báo kiểu trả về của `@Bean` càng cụ thể càng tốt. Condition được đánh giá dựa trên thông tin kiểu mà method signature cung cấp.

Ví dụ:

```java
@Bean("partnerGateway")
Object partnerGateway() {
    return new PartnerPaymentGateway();
}
```

Nếu auto-configuration kiểm tra `@ConditionalOnMissingBean(PaymentGateway.class)`, return type `Object` có thể không cung cấp đủ metadata để condition nhận ra bean `PaymentGateway` trước khi instance được tạo.

Khai báo contract type phù hợp:

```java
@Bean("partnerGateway")
PaymentGateway partnerGateway() {
    return new PartnerPaymentGateway();
}
```

Nếu API cần một implementation cụ thể, có thể khai báo concrete type. Nếu starter chỉ phụ thuộc interface, khai báo interface làm return type cũng đủ để condition theo interface hoạt động.

### 3.5. Thứ tự xử lý condition cũng quan trọng

Bean condition chỉ có thể đánh giá những bean definition đã được xử lý tới thời điểm condition chạy. Spring Boot khuyến nghị đặt `@ConditionalOnBean` và `@ConditionalOnMissingBean` trên auto-configuration, vì auto-configuration được áp dụng sau các user-defined bean definitions.

Nếu đặt condition trong một configuration thông thường được component scan hoặc import theo thứ tự không phù hợp, condition có thể chạy trước khi bean cần kiểm tra được đăng ký. Kết quả là default được thêm vào, rồi một definition khác xuất hiện cùng tên.

`@AutoConfiguration(after = ...)` và `before = ...` dùng để mô tả quan hệ thứ tự giữa các auto-configuration. Chúng điều khiển thứ tự đăng ký bean definition; không thay thế condition và không tự giải quyết hai method cùng tên.

## 4. Phân biệt các tình huống dễ nhầm

| Hiện tượng | Kết quả thường gặp | Hướng xử lý |
| --- | --- | --- |
| Hai definition cùng bean name, overriding tắt | `BeanDefinitionOverrideException` | Tìm hai nguồn đăng ký; sửa tên hoặc điều kiện. |
| Hai bean cùng type, bean name khác nhau | Context có thể chạy; inject theo type có thể gây `NoUniqueBeanDefinitionException` | Dùng `@Qualifier`, `@Primary` hoặc collection injection. |
| User bean cùng type với default bean và auto-config có `@ConditionalOnMissingBean(Type.class)` | Auto-config back off | Đây là hành vi override mặc định mong muốn. |
| User bean cùng type nhưng condition kiểm tra một bean name khác | Default có thể vẫn được tạo; có thể phát sinh nhiều bean cùng type | Sửa condition theo contract type/name. |
| User bean chiếm cùng tên nhưng khác type, auto-config chỉ kiểm tra type | Condition có thể vẫn match và đăng ký trùng tên | Dùng tên riêng hoặc condition phù hợp với contract. |
| Cùng bean được khai báo từ hai configuration class | Có thể trùng tên | Kiểm tra `@Bean` method name, `@Bean(name=...)` và các nguồn import/scan. |

Không dùng `@Primary` để sửa `BeanDefinitionOverrideException`. `@Primary` chỉ được xét khi Spring đã có nhiều candidate hợp lệ cho một dependency; nó không cho phép registry lưu hai definition cùng tên.

## 5. Quy trình chẩn đoán theo exception

Khi ứng dụng không khởi động, đi theo thứ tự sau:

1. **Lấy bean name từ exception.** Ví dụ `paymentGateway`. Tìm chính xác tên này trong `@Bean`, `@Component`, XML, `@Import` và code đăng ký programmatic.
2. **Đọc cả hai definition.** Xác định definition cũ và definition mới đến từ configuration class, component hay module nào. Dùng `getResourceDescription()` và `getBeanDefinition()` nếu cần điều tra bằng debugger.
3. **Kiểm tra bean name được sinh tự động.** Hai method `@Bean` có thể trùng tên method; hai component cùng simple class name có thể tạo tên mặc định giống nhau; alias cũng có thể chiếm tên.
4. **Đọc condition ở đúng nơi đăng ký.** Condition kiểm tra theo type hay name? `@ConditionalOnMissingBean` có nằm trên auto-configuration được Boot nạp sau user configuration không?
5. **Kiểm tra return type.** Nếu condition dựa vào type, method `@Bean` của user phải khai báo return type thể hiện contract cần kiểm tra.
6. **Kiểm tra component scan và imports.** Auto-configuration nên được liệt kê trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, không được đưa vào component scan như configuration thông thường. Kiểm tra các package scan quá rộng hoặc import trùng đường đi.
7. **Kiểm tra profile/property.** Hai configuration có thể cùng hoạt động trong một môi trường dù dự định chỉ một cấu hình được bật. Kiểm tra `@Profile`, `@ConditionalOnProperty` và các nguồn cấu hình thực tế.
8. **Đọc Condition Evaluation Report.** Chạy với `--debug` hoặc bật report trong test để biết condition nào match và condition nào không match.

Ví dụ, nếu exception nêu `paymentGateway`, hãy tìm toàn bộ khai báo có tên đó. Đừng bắt đầu bằng việc đổi tên ngẫu nhiên: trước tiên xác định hai bean đó là hai implementation cần tồn tại đồng thời hay hai ứng viên đang cạnh tranh cho cùng một vai trò.

## 6. Cách sửa theo nguyên nhân

### 6.1. Hai implementation thực sự cần tồn tại

Đặt tên riêng:

```java
@Configuration(proxyBeanMethods = false)
class GatewayConfiguration {
    @Bean("localGateway")
    PaymentGateway localGateway() {
        return new LocalPaymentGateway();
    }

    @Bean("partnerGateway")
    PaymentGateway partnerGateway() {
        return new PartnerPaymentGateway();
    }
}
```

Khi cần một implementation cụ thể, inject rõ ràng:

```java
@Service
class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(@Qualifier("partnerGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Nếu service cần sử dụng tất cả implementation, inject `List<PaymentGateway>` hoặc `Map<String, PaymentGateway>`. Có thể dùng `@Primary` nếu có một lựa chọn mặc định cho các injection point không chỉ định qualifier.

### 6.2. User bean phải thay thế default của starter

Đặt condition trên bean mặc định của auto-configuration:

```java
@AutoConfiguration
public class GatewayAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway defaultGateway() {
        return new DefaultPaymentGateway();
    }
}
```

Ứng dụng cung cấp bean theo contract:

```java
@Configuration(proxyBeanMethods = false)
class ApplicationGatewayConfiguration {
    @Bean
    PaymentGateway paymentGateway() {
        return new PartnerPaymentGateway();
    }
}
```

Auto-configuration được xử lý sau user configuration và nhìn thấy bean `PaymentGateway`, vì vậy không đăng ký default. Không cần ép hai bean có cùng tên để biểu diễn ý nghĩa override.

Nếu contract thật sự yêu cầu một bean name cụ thể, dùng `@ConditionalOnMissingBean(name = "...")` và yêu cầu user cung cấp đúng tên đó. Hãy ghi rõ quy ước này trong tài liệu starter.

### 6.3. Hai configuration không nên cùng hoạt động

Nếu mỗi configuration đại diện cho một lựa chọn loại trừ lẫn nhau, dùng property hoặc profile để chọn đúng một:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "payment.gateway",
        name = "provider",
        havingValue = "local"
)
class LocalGatewayConfiguration {
    // Đăng ký localGateway.
}

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "payment.gateway",
        name = "provider",
        havingValue = "partner"
)
class PartnerGatewayConfiguration {
    // Đăng ký partnerGateway.
}
```

Cấu hình:

```properties
payment.gateway.provider=partner
```

Không để hai configuration cùng match trong cùng một profile nếu chúng đăng ký chung tên. Nếu cần một implementation mặc định, thiết kế một nhánh default riêng và kiểm thử các tổ hợp property.

### 6.4. Component scan đang nạp cùng cấu hình qua nhiều đường

Thu hẹp `@ComponentScan` về package ứng dụng thực sự cần scan. Không component-scan package chứa auto-configuration của starter. Với starter, đăng ký auto-configuration qua file imports và dùng `@Import` cho các configuration cụ thể cần thiết.

Việc khai báo cùng một auto-configuration trong imports và component scan là dấu hiệu cấu trúc cần sửa. Không dựa vào thứ tự quét để quyết định definition nào thắng.

### 6.5. Chỉ bật overriding khi đó là chính sách có chủ đích

Có thể đặt `spring.main.allow-bean-definition-overriding=true` để hỗ trợ một ứng dụng legacy cố ý thay definition theo cùng tên. Nhưng khi đó definition đăng ký sau có thể thay definition trước; thứ tự cấu hình trở thành một phần hành vi runtime.

Trước khi bật, cần xác nhận:

- Hai definition thực sự đại diện cho một vai trò và việc thay thế là chủ đích.
- Thứ tự đăng ký ổn định, có test.
- Không có module hoặc starter khác vô tình dùng chung tên.
- Người vận hành hiểu bean nào được giữ lại trong từng profile.

Không dùng `true` như biện pháp sửa mặc định cho starter. Với một library/starter có nhiều consumer, tên riêng và backoff theo contract giúp hành vi dễ dự đoán hơn.

## 7. Ví dụ hoàn chỉnh: tái hiện và kiểm thử lỗi bằng Spring Boot 3.3.5

Ví dụ dưới đây kiểm tra năm tình huống:

1. Không có user bean thì default được tạo.
2. User bean cùng type nhưng tên khác khiến auto-configuration back off theo type.
3. Condition chỉ theo tên không back off khi user bean có tên khác; kết quả là nhiều bean cùng type.
4. Một bean khác type chiếm cùng tên khiến condition theo type không phát hiện và đăng ký thất bại.
5. Auto-configuration thiếu backoff và user bean cùng tên gây `BeanDefinitionOverrideException`.

### 7.1. POM và cấu trúc

```text
bean-name-lab/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── BeanNameCollisionTests.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>bean-name-lab</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 7.2. File test đầy đủ

Tạo `src/test/java/demo/BeanNameCollisionTests.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.support.BeanDefinitionOverrideException;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class BeanNameCollisionTests {

    record Sender(String id) {
    }

    @AutoConfiguration
    static class TypeBasedAutoConfiguration {
        @Bean("sender")
        @ConditionalOnMissingBean(Sender.class)
        Sender defaultSender() {
            return new Sender("default");
        }
    }

    @AutoConfiguration
    static class NameBasedAutoConfiguration {
        @Bean("sender")
        @ConditionalOnMissingBean(name = "sender")
        Sender defaultSender() {
            return new Sender("default");
        }
    }

    @AutoConfiguration
    static class UnconditionalAutoConfiguration {
        @Bean("sender")
        Sender defaultSender() {
            return new Sender("default");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserSenderConfiguration {
        @Bean("partnerSender")
        Sender partnerSender() {
            return new Sender("partner");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserWrongTypeConfiguration {
        @Bean("sender")
        String senderName() {
            return "reserved-name";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserSameNameConfiguration {
        @Bean("sender")
        Sender userSender() {
            return new Sender("user");
        }
    }

    private ApplicationContextRunner runnerFor(Class<?> autoConfiguration) {
        return new ApplicationContextRunner()
                .withAllowBeanDefinitionOverriding(false)
                .withConfiguration(AutoConfigurations.of(autoConfiguration));
    }

    @Test
    void defaultSenderIsCreatedWhenNoUserSenderExists() {
        runnerFor(TypeBasedAutoConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(Sender.class))
                            .containsOnlyKeys("sender");
                    assertThat(context.getBean(Sender.class).id())
                            .isEqualTo("default");
                });
    }

    @Test
    void userSenderOfSameTypeMakesDefaultBackOff() {
        runnerFor(TypeBasedAutoConfiguration.class)
                .withUserConfiguration(UserSenderConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(Sender.class))
                            .containsOnlyKeys("partnerSender");
                    assertThat(context.getBean(Sender.class).id())
                            .isEqualTo("partner");
                });
    }

    @Test
    void nameConditionDoesNotBackOffForAnotherName() {
        runnerFor(NameBasedAutoConfiguration.class)
                .withUserConfiguration(UserSenderConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(Sender.class))
                            .containsOnlyKeys("partnerSender", "sender");
                    assertThat(context.getBeansOfType(Sender.class))
                            .hasSize(2);
                    assertThatThrownBy(() -> context.getBean(Sender.class))
                            .isInstanceOf(NoUniqueBeanDefinitionException.class);
                });
    }

    @Test
    void typeConditionCannotDetectAnotherTypeUsingTheSameName() {
        runnerFor(TypeBasedAutoConfiguration.class)
                .withUserConfiguration(UserWrongTypeConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    BeanDefinitionOverrideException.class
                            );
                });
    }

    @Test
    void missingBackoffOnDefaultBeanCausesSameNameCollision() {
        runnerFor(UnconditionalAutoConfiguration.class)
                .withUserConfiguration(UserSameNameConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    BeanDefinitionOverrideException.class
                            );
                });
    }
}
```

Chạy trong thư mục `bean-name-lab` bằng JDK 17+ và Maven:

```bash
mvn test
```

**Kết quả mong đợi:** năm test thành công. Hai test cuối xác nhận context thất bại với root cause là `BeanDefinitionOverrideException`; test thứ ba xác nhận hai bean khác tên nhưng cùng type dẫn tới `NoUniqueBeanDefinitionException` khi lookup theo type. Maven Surefire báo `Tests run: 5, Failures: 0, Errors: 0, Skipped: 0` nếu toàn bộ test pass.

## 8. Các lỗi chẩn đoán thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đổi class implementation nhưng lỗi trùng tên vẫn còn | Bean name đến từ method name hoặc `@Bean(name=...)`, không phải class name | Kiểm tra tên definition và alias. |
| Thêm `@Primary` nhưng context vẫn fail | Registry không cho đăng ký hai definition cùng tên | Sửa bean name hoặc điều kiện; `@Primary` không áp dụng ở bước đăng ký. |
| Có `@ConditionalOnMissingBean` nhưng vẫn trùng tên | Condition kiểm tra sai type/name hoặc không nhìn thấy metadata của user bean | Kiểm tra annotation attributes, return type và thời điểm condition chạy. |
| Context khởi động nhưng inject theo type bị lỗi | Có nhiều bean cùng type nhưng khác name | Dùng qualifier, primary hoặc collection injection. |
| Chỉ lỗi trong một profile | Hai configuration cùng được kích hoạt trong profile đó | Kiểm tra `@Profile`, `@ConditionalOnProperty` và cấu hình môi trường. |
| Chỉ lỗi khi thêm một starter | Starter đăng ký bean trùng tên hoặc auto-configuration bị component scan ngoài dự kiến | Tìm bean name trong dependency, kiểm tra imports và package scan. |
| Bật overriding thì ứng dụng chạy nhưng bean sai | Definition đăng ký sau đã thay definition trước | Xác định thứ tự và loại bỏ collision thay vì dựa vào thay thế ngầm. |
| Condition không nhìn thấy bean do user khai báo | Method `@Bean` khai báo return type quá rộng, ví dụ `Object` | Trả về type contract cụ thể để condition có thể nhận diện. |

## 9. Checklist trước khi sửa lỗi

- [ ] Đọc chính xác bean name trong `BeanDefinitionOverrideException`.
- [ ] Xác định definition cũ và definition mới, cùng resource/configuration tạo ra chúng.
- [ ] Kiểm tra tên mặc định của `@Bean`, tên `@Component`, explicit name và alias.
- [ ] Xác định hai bean có cùng name hay chỉ cùng type.
- [ ] Đọc `@ConditionalOnMissingBean`: kiểm tra theo type hay name?
- [ ] Xác nhận return type của method `@Bean` thể hiện type condition cần tìm.
- [ ] Xác nhận condition nằm trong auto-configuration và được xử lý sau user configuration.
- [ ] Kiểm tra component scan, `@Import`, file `AutoConfiguration.imports`, profile và property.
- [ ] Nếu hai implementation cùng tồn tại, đặt bean name khác nhau và dùng qualifier/primary phù hợp.
- [ ] Nếu user bean thay default, kiểm thử bằng `ApplicationContextRunner` với overriding tắt.
- [ ] Chỉ bật `spring.main.allow-bean-definition-overriding=true` khi thay thế cùng tên là chính sách được thiết kế và kiểm thử có chủ đích.

**Ghi nhớ:** `BeanDefinitionOverrideException` là xung đột ở **bean name trong registry**. Cơ chế `@ConditionalOnMissingBean` chỉ giúp auto-configuration nhường chỗ khi điều kiện theo type hoặc name thực sự khớp. Hãy tìm hai nguồn đăng ký, kiểm tra type/name mà condition đánh giá và sửa contract bean cho rõ ràng. Nếu hai bean có tên khác nhau nhưng cùng type, xử lý bằng qualifier/primary; nếu hai definition cùng tên, phải giải quyết xung đột đăng ký trước khi đến bước inject.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Creating Your Own Auto-configuration và `@ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — Common Application Properties (`spring.main.allow-bean-definition-overriding`): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html
- Spring Framework 6.1 API — `BeanDefinitionOverrideException`: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionOverrideException.html
- Spring Framework 6.1 API — `DefaultListableBeanFactory`: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/support/DefaultListableBeanFactory.html