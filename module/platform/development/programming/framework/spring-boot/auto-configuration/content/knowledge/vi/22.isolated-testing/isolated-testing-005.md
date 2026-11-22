# `withBean` để cung cấp bean người dùng cho thí nghiệm với `ApplicationContextRunner`

Khi kiểm thử một Spring Boot auto-configuration, ta thường cần mô phỏng tình huống ứng dụng **đã tự khai báo một bean**. Ví dụ, starter cung cấp `PaymentGateway` mặc định bằng `@ConditionalOnMissingBean`; test cần chứng minh bean mặc định được đăng ký khi chưa có gateway, nhưng nhường chỗ khi người dùng cung cấp implementation riêng.

`ApplicationContextRunner` có phương thức `withBean` để thêm bean vào context thử nghiệm mà không cần tạo thêm một lớp `@Configuration` chỉ để khai báo một phương thức `@Bean`. Phương thức này giúp kiểm soát rõ **tên bean, kiểu bean, cách tạo instance và một số thuộc tính của bean definition**. Nó đặc biệt hữu ích khi viết nhiều thí nghiệm nhỏ với những tổ hợp bean khác nhau.

**Điểm cần nhớ:** `withBean` đăng ký một bean người dùng vào **context do runner tạo cho test**. Nó không sửa ứng dụng đang chạy và cũng không tự động thay thế một bean đã tồn tại. Auto-configuration chỉ back off khi condition của nó thực sự nhận diện bean đó, chẳng hạn kiểm tra đúng kiểu `PaymentGateway.class` hoặc đúng bean name.

## 1. `withBean` giải quyết vấn đề gì?

Giả sử starter có auto-configuration:

```java
@AutoConfiguration
public class PaymentGatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway defaultPaymentGateway() {
        return new DefaultPaymentGateway();
    }
}
```

Đây là đoạn minh họa: `PaymentGateway` và `DefaultPaymentGateway` là kiểu do dự án định nghĩa. Khi test, ta muốn dựng hai tình huống:

- Không có bean `PaymentGateway` nào: auto-configuration đăng ký `defaultPaymentGateway`.
- Có bean `PaymentGateway` do ứng dụng cung cấp: phương thức default back off.

Nếu dùng `withUserConfiguration`, ta có thể tạo một lớp cấu hình riêng:

```java
@Configuration(proxyBeanMethods = false)
static class UserConfiguration {

    @Bean
    PaymentGateway customPaymentGateway() {
        return new PartnerPaymentGateway();
    }
}
```

Sau đó truyền vào runner bằng `withUserConfiguration(UserConfiguration.class)`. Cách này phù hợp khi muốn kiểm thử cả một nhóm cấu hình, nhiều phương thức `@Bean`, `@Import`, điều kiện riêng hoặc logic khởi tạo.

Nhưng nếu chỉ cần thêm **một bean cụ thể** để kiểm tra điều kiện backoff, `withBean` ngắn và trực tiếp hơn:

```java
new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(
                PaymentGatewayAutoConfiguration.class
        ))
        .withBean(
                "customPaymentGateway",
                PaymentGateway.class,
                () -> new PartnerPaymentGateway()
        )
        .run(context -> {
            // Kiểm tra bean custom và việc default back off.
        });
```

Runner sẽ tạo một context mới cho lần chạy đó, đăng ký bean người dùng, nạp auto-configuration rồi gọi callback để test quan sát context. Sau callback, context được đóng. Mỗi lần gọi `run` là một thí nghiệm độc lập, không chia sẻ bean instance của context trước đó trừ khi chính test cố ý đưa chung object bên ngoài vào supplier.

## 2. Các overload của `withBean`

Trong Spring Boot 3.3, `withBean` được khai báo trên `AbstractApplicationContextRunner` và được kế thừa bởi `ApplicationContextRunner`, `WebApplicationContextRunner` và `ReactiveWebApplicationContextRunner`.

Có bốn dạng thường dùng:

| Cách gọi | Ý nghĩa |
| --- | --- |
| `withBean(Class<T> type, Object... constructorArgs)` | Đăng ký bean theo kiểu; Spring dùng constructor resolution với các đối số được cung cấp. Tên bean được sinh bởi `BeanNameGenerator` của context. |
| `withBean(String name, Class<T> type, Object... constructorArgs)` | Như trên nhưng chỉ định tên bean. Có thể truyền `null` cho name để dùng tên được sinh tự động. |
| `withBean(Class<T> type, Supplier<T> supplier, BeanDefinitionCustomizer... customizers)` | Đăng ký bean theo kiểu và tự cung cấp supplier tạo instance; tên được sinh tự động. |
| `withBean(String name, Class<T> type, Supplier<T> supplier, BeanDefinitionCustomizer... customizers)` | Kết hợp tên bean rõ ràng, supplier và các tùy chỉnh bean definition. |

Ví dụ dùng constructor arguments:

```java
runner.withBean(PaymentGateway.class, "sandbox");
```

Ví dụ chỉ định tên và supplier:

```java
runner.withBean(
        "customGateway",
        PaymentGateway.class,
        () -> new PartnerPaymentGateway()
);
```

Nếu constructor có nhiều tham số, các đối số truyền vào được dùng trong quá trình Spring giải quyết constructor; các dependency còn lại có thể được autowire theo quy tắc thông thường. Nếu cần toàn quyền kiểm soát cách tạo đối tượng, dùng supplier.

**Lưu ý về builder:** mỗi lời gọi `withBean` trả về **một runner mới đã được tùy chỉnh**, không sửa runner ban đầu. Vì thế phải nối lời gọi hoặc giữ kết quả:

```java
ApplicationContextRunner customRunner =
        baseRunner.withBean(
                "customGateway",
                PaymentGateway.class,
                () -> new PartnerPaymentGateway()
        );

customRunner.run(context -> {
    // Thí nghiệm có customGateway.
});

baseRunner.run(context -> {
    // Runner gốc vẫn là thí nghiệm không có customGateway.
});
```

Nếu gọi `baseRunner.withBean(...)` rồi bỏ qua giá trị trả về, bean sẽ không được thêm vào lần chạy của `baseRunner` ban đầu.

## 3. Dùng `withBean` để kiểm tra `@ConditionalOnMissingBean`

Đây là tình huống quan trọng nhất khi phát triển starter. Bean do ứng dụng cung cấp thường phải được nhận diện theo **kiểu hợp đồng**, để người dùng được tự chọn tên bean.

Ví dụ:

```java
@AutoConfiguration
public class GatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway defaultGateway() {
        return new PaymentGateway("default");
    }
}
```

Trong test, thêm một bean khác tên nhưng cùng kiểu:

```java
runner.withBean(
        "partnerGateway",
        PaymentGateway.class,
        () -> new PaymentGateway("partner")
).run(context -> {
    assertThat(context.getBeansOfType(PaymentGateway.class))
            .containsOnlyKeys("partnerGateway");

    assertThat(context.getBean(PaymentGateway.class).id())
            .isEqualTo("partner");

    assertThat(context).doesNotHaveBean("defaultGateway");
});
```

Kết quả mong đợi: `partnerGateway` tồn tại; `defaultGateway` không được đăng ký. Không có thao tác ghi đè bean definition cùng tên. Condition theo kiểu nhìn thấy bean người dùng và **ngăn method default đăng ký**.

### 3.1. Phải khớp tiêu chí condition

Giả sử auto-configuration dùng condition theo tên:

```java
@Bean
@ConditionalOnMissingBean(name = "defaultGateway")
PaymentGateway defaultGateway() {
    return new PaymentGateway("default");
}
```

Nếu test cung cấp `partnerGateway`, condition trên vẫn có thể khớp vì **chưa có bean tên `defaultGateway`**. Kết quả có thể là hai bean cùng kiểu:

```text
partnerGateway : PaymentGateway
defaultGateway : PaymentGateway
```

Khi đó, truy vấn một bean duy nhất theo kiểu có thể ném `NoUniqueBeanDefinitionException` nếu không có ứng viên `@Primary` hoặc qualifier phù hợp. Đây không phải lỗi của `withBean`; test đã mô phỏng chính xác điều kiện theo tên mà source yêu cầu.

Vì vậy, trước khi viết test, đọc annotation condition ở **đúng cấp**:

- `@ConditionalOnMissingBean(PaymentGateway.class)`: kiểm tra bean theo kiểu hợp đồng.
- `@ConditionalOnMissingBean(name = "defaultGateway")`: kiểm tra bean theo tên.
- `@ConditionalOnMissingBean` không có thuộc tính chỉ định trên phương thức `@Bean`: Spring Boot có thể suy luận kiểu từ kiểu trả về khai báo của method.

Một test hữu ích phải mô phỏng đúng contract của auto-configuration. Đừng đổi tên bean test cho đến khi assertion chạy qua; nếu condition theo tên thì tên chính là một phần của đầu vào cần kiểm chứng.

## 4. Cung cấp nhiều bean cùng kiểu và kiểm tra ambiguity

`withBean` có thể được gọi nhiều lần để đăng ký nhiều implementation:

```java
runner
    .withBean("bankGateway", PaymentGateway.class,
            () -> new PaymentGateway("bank"))
    .withBean("cardGateway", PaymentGateway.class,
            () -> new PaymentGateway("card"))
    .run(context -> {
        assertThat(context.getBeansOfType(PaymentGateway.class))
                .containsOnlyKeys("bankGateway", "cardGateway");

        assertThatThrownBy(() -> context.getBean(PaymentGateway.class))
                .isInstanceOf(NoUniqueBeanDefinitionException.class);
    });
```

Đoạn trên giả định có một record hoặc class `PaymentGateway` nhận chuỗi id. Hai bean khác tên cùng kiểu có thể cùng tồn tại. Khi inject một `PaymentGateway` duy nhất, Spring không biết nên chọn bean nào nếu không có thêm quy tắc.

Đây là cách kiểm thử hữu ích khi starter cho phép nhiều plugin, nhiều strategy hoặc nhiều implementation cùng interface. Có thể kiểm tra danh sách qua `getBeansOfType`, `getBeanNamesForType` hoặc `ObjectProvider<PaymentGateway>.stream()` thay vì yêu cầu một bean duy nhất.

### 4.1. Đặt bean ưu tiên bằng `BeanDefinitionCustomizer`

Overload supplier nhận thêm `BeanDefinitionCustomizer` để sửa metadata của definition trước khi bean được dùng. Ví dụ đánh dấu một bean là `primary`:

```java
runner
    .withBean(
            "preferredGateway",
            PaymentGateway.class,
            () -> new PaymentGateway("preferred"),
            definition -> definition.setPrimary(true)
    )
    .withBean(
            "secondaryGateway",
            PaymentGateway.class,
            () -> new PaymentGateway("secondary")
    )
    .run(context -> {
        assertThat(context.getBean(PaymentGateway.class).id())
                .isEqualTo("preferred");
    });
```

`@Primary` không xóa bean còn lại. Cả hai vẫn tồn tại; quy tắc primary chỉ giúp Spring chọn bean phù hợp khi một injection point yêu cầu một `PaymentGateway` duy nhất.

### 4.2. Tùy chỉnh lazy và scope

Cũng có thể dùng customizer để kiểm tra vòng đời bean:

```java
// Đăng ký bean lazy:
.withBean(
        "lazyGateway",
        PaymentGateway.class,
        () -> new PaymentGateway("lazy"),
        definition -> definition.setLazyInit(true)
)

// Đăng ký bean prototype:
.withBean(
        "prototypeGateway",
        PaymentGateway.class,
        () -> new PaymentGateway("prototype"),
        definition -> definition.setScope(
                ConfigurableBeanFactory.SCOPE_PROTOTYPE
        )
)
```

- `setLazyInit(true)` hoãn tạo singleton cho tới khi có yêu cầu lấy bean. Supplier không được gọi chỉ vì runner đã được cấu hình.
- `setScope(SCOPE_PROTOTYPE)` làm Spring tạo instance mới cho mỗi lần lấy bean theo scope prototype.
- Nếu không đặt scope khác, bean thông thường dùng singleton scope.

Supplier không nhất thiết chạy ngay lúc gọi `withBean`. Với singleton không lazy, Spring thường gọi supplier trong lúc refresh context để tạo bean. Với lazy singleton, supplier được gọi ở lần truy xuất đầu. Với prototype, supplier có thể được gọi mỗi lần yêu cầu instance.

Không dùng một object mutable duy nhất tạo sẵn ở ngoài rồi trả đi trả lại từ supplier cho nhiều context. Nên tạo object mới bên trong supplier để mỗi lần chạy có vòng đời riêng.

## 5. Ví dụ hoàn chỉnh: Java 17, Spring Boot 3.3.5 và JUnit 5

Bộ test dưới đây kiểm tra sáu hành vi:

1. Không có user bean thì auto-configuration đăng ký default.
2. Bean thêm bằng supplier và tên rõ ràng khiến condition theo kiểu back off.
3. Overload constructor arguments có thể tạo user bean.
4. Condition theo tên có thể vẫn đăng ký default khi user bean cùng kiểu nhưng tên khác.
5. Nhiều bean cùng kiểu gây ambiguity; customizer `setPrimary(true)` giúp chọn một bean.
6. Supplier lazy chỉ chạy khi bean được yêu cầu.

### 5.1. Cấu trúc dự án

```text
withbean-lab/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── WithBeanExperimentTest.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>withbean-lab</artifactId>
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

### 5.2. File test đầy đủ

Tạo `src/test/java/demo/WithBeanExperimentTest.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class WithBeanExperimentTest {

    public record PaymentGateway(String id) {
    }

    @AutoConfiguration
    public static class TypeBasedGatewayAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(PaymentGateway.class)
        PaymentGateway defaultGateway() {
            return new PaymentGateway("default");
        }
    }

    @AutoConfiguration
    public static class NameBasedGatewayAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(name = "defaultGateway")
        PaymentGateway defaultGateway() {
            return new PaymentGateway("default");
        }
    }

    private final ApplicationContextRunner typeRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            TypeBasedGatewayAutoConfiguration.class
                    ));

    private final ApplicationContextRunner nameRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            NameBasedGatewayAutoConfiguration.class
                    ));

    @Test
    void defaultBeanIsRegisteredWhenNoUserBeanExists() {
        typeRunner.run(context -> {
            assertThat(context).hasNotFailed();

            assertThat(context.getBeansOfType(PaymentGateway.class))
                    .containsOnlyKeys("defaultGateway");

            assertThat(context.getBean(PaymentGateway.class).id())
                    .isEqualTo("default");
        });
    }

    @Test
    void namedSupplierBeanMakesTypeBasedConditionBackOff() {
        typeRunner.withBean(
                        "partnerGateway",
                        PaymentGateway.class,
                        () -> new PaymentGateway("partner")
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    assertThat(context.getBeansOfType(PaymentGateway.class))
                            .containsOnlyKeys("partnerGateway");

                    assertThat(context.getBean(PaymentGateway.class).id())
                            .isEqualTo("partner");

                    assertThat(context).doesNotHaveBean("defaultGateway");
                });
    }

    @Test
    void constructorArgumentsCanCreateUserBean() {
        typeRunner.withBean(PaymentGateway.class, "constructor-user")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(PaymentGateway.class);

                    assertThat(context.getBean(PaymentGateway.class).id())
                            .isEqualTo("constructor-user");

                    assertThat(context).doesNotHaveBean("defaultGateway");
                });
    }

    @Test
    void nameBasedConditionDoesNotBackOffForDifferentBeanName() {
        nameRunner.withBean(
                        "partnerGateway",
                        PaymentGateway.class,
                        () -> new PaymentGateway("partner")
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    assertThat(context.getBeansOfType(PaymentGateway.class))
                            .containsOnlyKeys(
                                    "partnerGateway",
                                    "defaultGateway"
                            );
                });
    }

    @Test
    void multipleBeansCanBeInspectedAndPrimaryCanSelectOne() {
        typeRunner
                .withBean(
                        "bankGateway",
                        PaymentGateway.class,
                        () -> new PaymentGateway("bank")
                )
                .withBean(
                        "cardGateway",
                        PaymentGateway.class,
                        () -> new PaymentGateway("card")
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    assertThat(context.getBeansOfType(PaymentGateway.class))
                            .containsOnlyKeys("bankGateway", "cardGateway");

                    assertThatThrownBy(
                            () -> context.getBean(PaymentGateway.class)
                    ).isInstanceOf(NoUniqueBeanDefinitionException.class);
                });

        typeRunner
                .withBean(
                        "preferredGateway",
                        PaymentGateway.class,
                        () -> new PaymentGateway("preferred"),
                        definition -> definition.setPrimary(true)
                )
                .withBean(
                        "secondaryGateway",
                        PaymentGateway.class,
                        () -> new PaymentGateway("secondary")
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    assertThat(context.getBeansOfType(PaymentGateway.class))
                            .containsOnlyKeys(
                                    "preferredGateway",
                                    "secondaryGateway"
                            );

                    assertThat(context.getBean(PaymentGateway.class).id())
                            .isEqualTo("preferred");
                });
    }

    @Test
    void lazySupplierRunsOnlyWhenBeanIsRequested() {
        AtomicInteger supplierCalls = new AtomicInteger();

        typeRunner.withBean(
                        "lazyGateway",
                        PaymentGateway.class,
                        () -> {
                            supplierCalls.incrementAndGet();
                            return new PaymentGateway("lazy");
                        },
                        definition -> definition.setLazyInit(true)
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(supplierCalls.get()).isZero();

                    assertThat(context.getBean(
                            "lazyGateway",
                            PaymentGateway.class
                    ).id()).isEqualTo("lazy");

                    assertThat(supplierCalls.get()).isEqualTo(1);
                });
    }
}
```

Chạy từ thư mục `withbean-lab` bằng JDK 17+ và Maven:

```bash
mvn test
```

**Kết quả mong đợi:** sáu phương thức test thành công; test thứ năm tạo hai context độc lập để kiểm tra ambiguity và primary. Maven Surefire thường báo `Tests run: 6, Failures: 0, Errors: 0, Skipped: 0`. Test không gọi `System.out.println` nên không có stdout nghiệp vụ cố định.

### 5.3. Đọc kết quả theo từng thí nghiệm

| Test | Đầu vào của runner | Kết quả quan sát |
| --- | --- | --- |
| `defaultBeanIsRegisteredWhenNoUserBeanExists` | Chỉ nạp type-based auto-configuration | Có duy nhất `defaultGateway`. |
| `namedSupplierBeanMakesTypeBasedConditionBackOff` | `partnerGateway` kiểu `PaymentGateway` được tạo bằng supplier | Chỉ còn `partnerGateway`; default không đăng ký. |
| `constructorArgumentsCanCreateUserBean` | `withBean(PaymentGateway.class, "constructor-user")` | Spring dùng constructor của `PaymentGateway` để tạo bean; condition theo kiểu back off. |
| `nameBasedConditionDoesNotBackOffForDifferentBeanName` | User bean `partnerGateway`, condition kiểm tra tên `defaultGateway` | Cả `partnerGateway` và `defaultGateway` tồn tại. |
| `multipleBeansCanBeInspectedAndPrimaryCanSelectOne` | Hai user bean cùng kiểu; sau đó thử lại với một bean primary | Trường hợp đầu tra cứu theo kiểu bị mơ hồ; trường hợp sau chọn `preferredGateway`. |
| `lazySupplierRunsOnlyWhenBeanIsRequested` | Supplier với customizer `setLazyInit(true)` | Counter bằng 0 trước lookup và bằng 1 sau lần lookup đầu. |

Điểm đáng chú ý ở test thứ năm: mỗi lời gọi `run` tạo context riêng. Hai gateway của thí nghiệm đầu không rò sang thí nghiệm primary tiếp theo. Runner gốc `typeRunner` cũng không bị biến đổi; mỗi chuỗi `withBean` trả một runner mới.

## 6. `withBean` khác gì `withUserConfiguration` và `@Bean`?

| Cách làm | Phù hợp khi | Ví dụ |
| --- | --- | --- |
| `withBean` | Cần thêm một bean cụ thể để mô phỏng đầu vào cho condition hoặc injection. | Thêm custom `PaymentGateway` với supplier. |
| `withUserConfiguration` | Cần kiểm thử cấu hình ứng dụng có nhiều bean, `@Import`, condition, factory method hoặc logic cấu hình. | Nạp `UserGatewayConfiguration.class`. |
| `withPropertyValues` | Cần thay đổi Environment để kiểm tra `@ConditionalOnProperty` hoặc binding. | `withPropertyValues("payment.gateway=partner")`. |
| `withInitializer` | Cần chạy thao tác khởi tạo context trước refresh hoặc đăng ký thành phần đặc biệt. | Thêm `ApplicationContextInitializer`. |
| `withParent` | Cần mô phỏng context hierarchy và điều kiện tìm bean ở ancestor. | Cung cấp parent ApplicationContext cho runner. |

`withBean` phù hợp với đầu vào đơn giản và tường minh. Nếu muốn kiểm thử việc Spring xử lý một lớp cấu hình người dùng thực tế, hãy tạo lớp `@Configuration` và nạp bằng `withUserConfiguration`; cách này chứng minh đường cấu hình của chính ứng dụng.

Ví dụ, muốn kiểm tra một user configuration có factory method và property condition:

```java
@Configuration(proxyBeanMethods = false)
static class UserGatewayConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "payment",
            name = "gateway",
            havingValue = "partner"
    )
    PaymentGateway partnerGateway() {
        return new PaymentGateway("partner");
    }
}
```

Khi đó, dùng `withUserConfiguration(UserGatewayConfiguration.class)` kết hợp `withPropertyValues`. Đừng mô phỏng cấu hình phức tạp bằng supplier nếu mục tiêu test là chính hành vi xử lý annotation và factory method.

## 7. Thứ tự đăng ký, trùng tên và lỗi thường gặp

### 7.1. Bean được thêm sau regular user configuration

Theo API của Spring Boot, các bean từ `withBean` được đăng ký sau các regular user configuration và theo thứ tự gọi `withBean`. Auto-configuration được nạp theo cơ chế deferred import, nhờ vậy bean người dùng là đầu vào phù hợp để kiểm tra các condition backoff của auto-configuration.

Tuy nhiên, không nên dựa vào `withBean` để kiểm soát thứ tự giữa nhiều auto-configuration không có quan hệ rõ ràng. Nếu hai auto-configuration cạnh tranh cùng một kiểu, hãy khai báo `before/after` hoặc order thích hợp và kiểm thử riêng.

### 7.2. `withBean` không phải API thay thế bean definition

Nếu test đăng ký `withBean("gateway", ...)` trong khi một cấu hình người dùng khác đã đăng ký bean cùng tên `gateway`, có thể xảy ra xung đột bean definition. Khi chế độ overriding bị tắt, context có thể thất bại với `BeanDefinitionOverrideException`.

Runner có `withAllowBeanDefinitionOverriding(true)` để kiểm thử riêng tình huống ghi đè definition cùng tên. Nhưng **không bật nó chỉ để ép test backoff thành công**. Việc bật overriding có thể che lỗi condition: thay vì default tự nhường chỗ, một definition cùng tên có thể bị thay bởi definition khác.

Đối với test `@ConditionalOnMissingBean`, nên dùng một bean có tên rõ ràng và kiểm tra đúng kiểu hoặc tên mà condition thực sự tìm kiếm.

### 7.3. Những lỗi hay gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Default vẫn xuất hiện dù đã gọi `withBean` | Condition kiểm tra tên hoặc kiểu khác với bean test; hoặc condition đặt ở một source khác | Đọc đúng annotation và kiểm tra tên/kiểu bean trong context. |
| Context thất bại vì trùng tên | Bean test và bean cấu hình cùng đăng ký một tên | Đặt tên khác nếu đang kiểm tra backoff; chỉ test overriding khi đó là mục tiêu riêng. |
| Không thấy bean test trong context | Đã gọi `withBean` nhưng bỏ qua runner trả về | Nối builder hoặc giữ runner mới trong biến. |
| Supplier chưa chạy | Bean được đánh dấu lazy và chưa được truy xuất | Gọi `getBean` hoặc kiểm tra đúng thời điểm tạo instance. |
| Supplier chạy ngay lúc refresh | Bean là singleton non-lazy mặc định | Dùng customizer `setLazyInit(true)` nếu muốn kiểm tra lazy. |
| `getBean(Type.class)` báo không duy nhất | Nhiều bean cùng kiểu và không có primary/qualifier | Kiểm tra map bean names, dùng `@Primary`/qualifier hoặc duyệt nhiều bean. |
| Test chỉ pass khi bật overriding | Condition backoff có thể sai hoặc hai bean bị đăng ký trùng tên | Bỏ overriding và kiểm tra lại điều kiện; không che lỗi thiết kế. |
| Một test làm ảnh hưởng test khác | Dùng chung context/object mutable ngoài supplier hoặc lưu trạng thái ngoài runner | Mỗi `run` tạo context mới; tạo bean trong supplier và tránh chia sẻ mutable state. |
| Test khởi động lỗi nhưng assertion không chỉ ra nguyên nhân | `run` vẫn đưa failed context vào callback | Dùng `hasNotFailed()` hoặc đọc startup failure trước khi truy xuất bean. |

### 7.4. Phân biệt bean definition với bean instance

`withBean` đăng ký **definition** trước. Supplier là cách tạo instance khi Spring cần tạo bean. Vì vậy:

- Condition như `@ConditionalOnMissingBean` thường xét metadata/bean definitions; không cần gọi supplier để biết kiểu bean đã đăng ký.
- `@Lazy` có thể hoãn instance creation, nhưng definition vẫn tồn tại để condition nhìn thấy.
- `SCOPE_PROTOTYPE` khiến supplier có thể được gọi nhiều lần, mỗi lần lấy bean.
- Một supplier có side effect như mở socket hoặc kết nối database nên chỉ được dùng trong test nếu side effect được kiểm soát; ưu tiên supplier tạo object nhỏ, xác định.

## 8. Checklist viết thí nghiệm bằng `withBean`

1. Đọc condition của auto-configuration: kiểm tra theo kiểu, tên, annotation hay property?
2. Chọn overload phù hợp: constructor args nếu muốn Spring tự resolve constructor; supplier nếu muốn kiểm soát instance.
3. Chỉ định bean name khi assertion hoặc condition phụ thuộc tên; nếu không, có thể dùng tên tự sinh.
4. Nếu cần primary, lazy hoặc scope, dùng `BeanDefinitionCustomizer`.
5. Gọi `withBean` trên runner và **giữ runner mới** mà phương thức trả về.
6. Mỗi trường hợp cần một `run` để có context độc lập.
7. Assert cả bean names/types và hành vi cần kiểm chứng; không chỉ kiểm tra context khởi động.
8. Với nhiều bean cùng kiểu, test ambiguity hoặc quy tắc `@Primary`/`@Qualifier` rõ ràng.
9. Không bật bean definition overriding để che condition không khớp.
10. Nếu context thất bại, kiểm tra startup failure trước khi gọi bean.

**Ghi nhớ:** `withBean` là cách gọn để đưa **bean người dùng giả lập** vào một thí nghiệm `ApplicationContextRunner`. Dùng overload constructor arguments cho cách tạo thông thường; dùng supplier khi cần kiểm soát instance; dùng customizer khi cần chỉnh primary, lazy hoặc scope. Để kiểm tra auto-configuration backoff, quan trọng nhất là bean test phải khớp **đúng tiêu chí condition**. Một bean cùng kiểu nhưng khác tên có thể khiến condition theo kiểu back off, trong khi condition theo tên vẫn đăng ký default.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 API — `AbstractApplicationContextRunner.withBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/AbstractApplicationContextRunner.html
- Spring Boot 3.3 API — `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.3 — Testing Your Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Framework 6.1 API — `BeanDefinitionCustomizer`: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/config/BeanDefinitionCustomizer.html
- Spring Boot 3.3 API — `AutoConfigurations`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurations.html