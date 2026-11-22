# Phân biệt nhường chỗ có điều kiện với ghi đè định nghĩa bean cùng tên trong Spring Boot

Trong **Spring Boot Auto Configuration**, người viết starter thường muốn cung cấp một bean mặc định nhưng cho phép ứng dụng tự chọn implementation khác. Có hai thuật ngữ dễ bị gọi chung là “override bean”: **nhường chỗ có điều kiện (conditional backoff)** và **ghi đè bean definition cùng tên (bean definition overriding)**. Chúng là hai cơ chế khác nhau, tác động ở những thời điểm khác nhau và không nên dùng thay thế cho nhau.

**Điểm cần nhớ:**

- **Backoff với `@ConditionalOnMissingBean`:** auto-configuration kiểm tra liệu bean phù hợp đã tồn tại trong những definition được xử lý hay chưa. Nếu có, **bean mặc định không được đăng ký**. Bean tùy chỉnh của ứng dụng được giữ nguyên, kể cả khi nó có **tên khác** tên bean mặc định.
- **Bean definition overriding:** có một bean definition đã đăng ký dưới tên `gateway`, sau đó một definition khác cũng được đăng ký dưới đúng tên `gateway`. Nếu registry cho phép ghi đè, definition thứ hai có thể **thay thế** definition trước; nếu không, thường có lỗi đăng ký.
- **Mặc định Spring Boot 3.x:** thuộc tính `spring.main.allow-bean-definition-overriding` bằng `false`. Việc cung cấp bean tùy chỉnh bằng backoff đúng cách **không đòi hỏi** bật thuộc tính này.

Lời nói “custom bean override auto-configuration” trong tài liệu Spring Boot thường có nghĩa **auto-configuration back off**; nó không tự động đồng nghĩa với thao tác thay bean definition cùng tên.

## 1. Phân biệt tên bean, kiểu bean và bean definition

Một **bean definition** là metadata mà container dùng để quản lý bean: tên, kiểu, cách tạo đối tượng, scope, dependency, factory method… Definition thường được đăng ký trước khi Spring tạo **instance** thực tế.

- **Bean name** là định danh trong một bean registry, chẳng hạn `"paymentGateway"`. Với `@Bean`, tên mặc định thường là tên phương thức; `@Bean("specialGateway")` chỉ định tên rõ ràng.
- **Bean type** là kiểu Java, ví dụ interface `PaymentGateway`. Hai tên khác nhau vẫn có thể cùng kiểu.
- **Bean instance** là đối tượng thực được khởi tạo. Thay đổi definition lúc dựng context và thay đối tượng đã tạo là hai việc khác nhau.

Ví dụ minh họa trong lớp cấu hình:

```java
interface PaymentGateway {
    String provider();
}

@Bean("specialGateway")
PaymentGateway gateway() {
    return () -> "partner";
}
```

Đây là **trích đoạn minh họa**, chưa phải file Java độc lập. Tên bean là `specialGateway`, còn kiểu hợp đồng là `PaymentGateway`.

| Trường hợp | Có trùng bean name? | Có cùng bean type? | Hệ quả |
| --- | :---: | :---: | --- |
| `alphaGateway` và `betaGateway` đều là `PaymentGateway` | Không | Có | Không phải overriding theo tên; có thể mơ hồ khi inject theo kiểu. |
| Hai definition đều tên `gateway`, kiểu khác nhau | Có | Không | Xung đột/ghi đè definition theo **tên**. |
| Hai definition đều tên `gateway`, cùng kiểu | Có | Có | Vẫn là xung đột/ghi đè theo **tên**. |
| User bean tên `customGateway` kiểu `PaymentGateway`; auto-config kiểm tra missing theo `PaymentGateway.class` | Không cần | Có | Auto-config **nhường chỗ theo kiểu**. |

`@Primary` và `@Qualifier` giúp chọn **bean được inject** khi có nhiều bean phù hợp. Chúng không xóa definition và không tự đăng ký đè một bean cùng tên.

## 2. Backoff với `@ConditionalOnMissingBean`

Cấu hình mặc định có thể viết:

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class PaymentGatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway defaultGateway() {
        return new DefaultPaymentGateway();
    }
}
```

`PaymentGateway` và `DefaultPaymentGateway` ở đây là kiểu giả định của dự án. Đoạn trên minh họa cách đặt annotation; ví dụ Maven/JUnit đầy đủ nằm ở phần 5.

Nếu ứng dụng cung cấp:

```java
@Bean("customGateway")
PaymentGateway customGateway() {
    return new PartnerPaymentGateway();
}
```

thì Spring Boot, khi xử lý auto-configuration sau bean của người dùng, thấy đã có bean phù hợp kiểu `PaymentGateway`. Condition `@ConditionalOnMissingBean(PaymentGateway.class)` **không khớp**, vì vậy definition tên `defaultGateway` **không được thêm**. Không có thao tác đăng ký trùng tên: `customGateway` được giữ nguyên.

Nếu user không có bean phù hợp, condition khớp và định nghĩa mặc định `defaultGateway` được đăng ký. Có thể biểu diễn như sau:

```text
Đã có user bean kiểu PaymentGateway?
  ├─ Có    → không đăng ký defaultGateway (BACKOFF)
  └─ Không → đăng ký defaultGateway (DEFAULT)
```

### Condition kiểm tra theo kiểu hay theo tên?

Hai lựa chọn sau có ý nghĩa khác nhau:

```java
// Bất kỳ bean PaymentGateway phù hợp nào đã có cũng khiến default back off.
@ConditionalOnMissingBean(PaymentGateway.class)

// Chỉ xét có bean với tên "paymentGateway" hay chưa.
@ConditionalOnMissingBean(name = "paymentGateway")
```

Một user bean `@Bean("customGateway")` kiểu `PaymentGateway` khiến **điều kiện theo kiểu** không khớp, nhưng condition **chỉ theo tên** có thể vẫn khớp do không có bean tên `paymentGateway`. Hậu quả là Spring có thể đăng ký thêm bean cùng kiểu, khác tên. Vì thế, khi interface là điểm mở rộng chính của starter, nên kiểm tra **interface**, không phụ thuộc tên mà ứng dụng tùy ý đặt.

`@ConditionalOnMissingBean` còn có các thuộc tính như `type`, `annotation`, `ignored`, `parameterizedContainer` và `search` (phạm vi xét giữa context hiện tại/cha). Không nên diễn giải mọi cách khai báo đa thuộc tính như một phép “OR” đơn giản; đọc đúng quy tắc kết hợp condition nếu starter dùng nhiều tiêu chí.

Nếu không truyền tham số và đặt annotation trên phương thức `@Bean`, Spring Boot sử dụng **kiểu trả về khai báo** của phương thức để suy luận kiểu cần tìm:

```java
@Bean
@ConditionalOnMissingBean
PaymentGateway defaultGateway() {
    return new DefaultPaymentGateway();
}
```

Trong một starter có nhiều implementation, viết tường minh `@ConditionalOnMissingBean(PaymentGateway.class)` thường giúp người đọc hiểu rõ contract.

### Backoff xảy ra khi nào?

Condition được đánh giá khi framework **xử lý và đăng ký bean definition**. Nó dựa vào những bean definition đã xử lý **tới thời điểm đó**, không phải một lượt kiểm tra toàn bộ bean tương lai. Spring Boot khuyến nghị dùng `@ConditionalOnMissingBean` trong **auto-configuration**, vì bean do ứng dụng khai báo thường được xử lý trước.

Khi hai auto-configuration cùng muốn cung cấp `PaymentGateway` mặc định, một lớp được xử lý trước có thể đăng ký default rồi khiến lớp sau back off. Khi kết quả phụ thuộc thứ tự, dùng metadata thứ tự auto-configuration như `@AutoConfiguration(before = …)`/`after = …` và viết test cho trường hợp có/không có bean người dùng.

**Backoff không xóa bean nào:** nếu condition không khớp, phương thức default không tạo bean definition. Không có định nghĩa cũ nào phải bị thay thế.

## 3. Ghi đè bean definition cùng tên

Giả sử registry đang chứa:

```text
bean name: "gateway"
bean definition: DefaultGateway
```

Sau đó một thành phần đăng ký:

```text
bean name: "gateway"
bean definition: CustomGateway
```

Tên **giống hệt** nhau trong **cùng một registry**. Đây là tình huống bean definition overriding:

- Với `allowBeanDefinitionOverriding=false`, thao tác đăng ký trùng tên có thể dẫn tới `BeanDefinitionOverrideException`.
- Với `allowBeanDefinitionOverriding=true`, definition mới có thể **thay** definition cũ. Kết quả phụ thuộc định nghĩa nào được đăng ký **sau**.
- Việc ghi đè là thay **metadata definition** dùng cho bean name đó, không phải thao tác sửa trực tiếp trạng thái Java object đã khởi tạo trước đó.
- Một số đường xử lý đặc biệt của Spring (chẳng hạn cấu hình Java và component scan) có thể bỏ qua một định nghĩa trùng tên tương thích hoặc có quy tắc xử lý khác. Vì vậy không được khẳng định *mọi* cặp phương thức `@Bean` trùng tên luôn ném cùng một exception. Để kiểm chứng rõ cơ chế registry, phần 5 sẽ dùng `registerBeanDefinition` trực tiếp.

Trong một ứng dụng Spring Boot 3.x, tùy chọn:

```properties
spring.main.allow-bean-definition-overriding=false
```

là **mặc định**. Nếu chủ đích bật:

```properties
spring.main.allow-bean-definition-overriding=true
```

thì các trường hợp ghi đè definition được registry cho phép có thể diễn ra. Một đường cấu hình khác là gọi:

```java
// Trích đoạn nằm trong main(String[] args) của ứng dụng có MyApplication:
SpringApplication application = new SpringApplication(MyApplication.class);
application.setAllowBeanDefinitionOverriding(true);
application.run(args);
```

**Không dùng flag global này làm cách mặc định để custom hóa starter.** Nó có thể che tình trạng hai thư viện vô tình đăng ký bean cùng tên. Nó cũng không xử lý vấn đề **hai bean cùng kiểu nhưng khác tên** gây mơ hồ injection, vì đó không phải xung đột tên definition.

## 4. So sánh cơ chế: khác nhau ở điều kiện và thao tác

| Thuộc tính | Conditional backoff | Bean definition overriding |
| --- | --- | --- |
| API tiêu biểu | `@ConditionalOnMissingBean` | `DefaultListableBeanFactory.registerBeanDefinition` và tùy chọn cho phép override |
| Điểm quyết định | Lúc **đánh giá condition** trước khi đăng ký default | Lúc **đăng ký tên đã tồn tại** |
| Khi đã có bean phù hợp | **Bỏ qua việc đăng ký** default | Có thể cố đăng ký definition **trùng tên** |
| Có cần trùng bean name? | **Không**; condition có thể theo kiểu | **Có**, trong cùng registry |
| Điều kiện theo kiểu? | Có thể chọn theo kiểu hoặc tên | Trùng tên mới là yếu tố của overriding |
| Bean definition cũ bị thay? | **Không** | **Có thể**, nếu registry cho phép |
| Boot mặc định chặn ghi đè? | Backoff vẫn bình thường | Nhiều đường đăng ký trùng tên bị chặn |
| Phụ thuộc thứ tự? | Có: condition chỉ thấy definition đã xử lý | Có: definition đến sau có thể thay trước |
| Thực hành trong starter | Nên dùng để cung cấp default có thể tùy biến | Chỉ dùng khi có yêu cầu cụ thể và hiểu rõ rủi ro |

**Hai luồng khác nhau:**

```text
BACKOFF
UserConfig đăng ký customGateway : PaymentGateway
  → AutoConfig xét @ConditionalOnMissingBean(PaymentGateway.class)
  → không khớp vì đã có PaymentGateway
  → KHÔNG đăng ký defaultGateway
  → customGateway vẫn là lựa chọn của ứng dụng

OVERRIDING
Registry đăng ký tên "gateway" -> DefaultGateway
  → Registry nhận đăng ký tên "gateway" -> CustomGateway
  → Nếu không cho phép override: lỗi đăng ký
  → Nếu cho phép override: thay definition dưới tên "gateway"
```

Có thể dùng chữ “thay” để mô tả *kết quả ứng dụng*, nhưng về kỹ thuật **không đăng ký default** và **thay definition đã có** là hai cơ chế riêng.

## 5. Ví dụ chạy được: Java 17 + Spring Boot 3.3.5 + JUnit 5

Một bộ test thực hành sẽ chứng minh đủ bốn khía cạnh:

1. Không có user bean → auto-configuration đăng ký default.
2. User bean **khác tên** nhưng cùng kiểu → auto-configuration **back off**.
3. Hai definition **cùng tên** → lỗi khi tắt overriding, thay definition khi bật.
4. Hai definition **khác tên cùng kiểu** → cùng tồn tại, có thể báo `NoUniqueBeanDefinitionException` khi tìm một bean duy nhất theo kiểu.

**Tách cơ chế kiểm chứng:** `ApplicationContextRunner` thể hiện cách Spring Boot áp dụng auto-configuration. `DefaultListableBeanFactory` thể hiện hành vi bean definition registry một cách trực tiếp; trong test registry, flag được đặt tường minh nên không nhầm mặc định của Spring Framework core với mặc định Spring Boot.

### 5.1. Cấu trúc dự án

```text
bean-backoff-lab/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── BackoffVersusOverrideTest.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>bean-backoff-lab</artifactId>
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

`src/test/java/demo/BackoffVersusOverrideTest.java`:

```java
package demo;

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

class BackoffVersusOverrideTest {

    interface Gateway {
        String name();
    }

    public static class DefaultGateway implements Gateway {
        @Override
        public String name() {
            return "default";
        }
    }

    public static class CustomGateway implements Gateway {
        @Override
        public String name() {
            return "custom";
        }
    }

    public static class AlternativeGateway implements Gateway {
        @Override
        public String name() {
            return "alternative";
        }
    }

    @AutoConfiguration
    static class GatewayAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(Gateway.class)
        Gateway defaultGateway() {
            return new DefaultGateway();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserConfiguration {

        @Bean("myGateway")
        Gateway myGateway() {
            return new CustomGateway();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            GatewayAutoConfiguration.class));

    @Test
    void defaultIsRegisteredWhenNoUserBeanExists() {
        runner.run(context -> {
            assertThat(context.getBeansOfType(Gateway.class))
                    .containsOnlyKeys("defaultGateway");
            assertThat(context.getBean(Gateway.class).name())
                    .isEqualTo("default");
        });
    }

    @Test
    void userBeanMakesDefaultBackOffWithoutMatchingName() {
        runner.withUserConfiguration(UserConfiguration.class)
                .run(context -> {
                    assertThat(context.getBeansOfType(Gateway.class))
                            .containsOnlyKeys("myGateway");
                    assertThat(context.getBean(Gateway.class).name())
                            .isEqualTo("custom");
                    assertThat(context.containsBean("defaultGateway"))
                            .isFalse();
                });
    }

    @Test
    void duplicateNameFailsWhenOverridingIsDisabled() {
        DefaultListableBeanFactory factory =
                new DefaultListableBeanFactory();
        factory.setAllowBeanDefinitionOverriding(false);

        factory.registerBeanDefinition(
                "sharedGateway",
                new RootBeanDefinition(DefaultGateway.class));

        assertThatThrownBy(() -> factory.registerBeanDefinition(
                "sharedGateway",
                new RootBeanDefinition(AlternativeGateway.class)))
                .isInstanceOf(BeanDefinitionOverrideException.class);

        assertThat(factory.getBean("sharedGateway", Gateway.class).name())
                .isEqualTo("default");
    }

    @Test
    void duplicateNameReplacesDefinitionWhenEnabled() {
        DefaultListableBeanFactory factory =
                new DefaultListableBeanFactory();
        factory.setAllowBeanDefinitionOverriding(true);

        factory.registerBeanDefinition(
                "sharedGateway",
                new RootBeanDefinition(DefaultGateway.class));
        factory.registerBeanDefinition(
                "sharedGateway",
                new RootBeanDefinition(AlternativeGateway.class));

        assertThat(factory.getBean("sharedGateway", Gateway.class).name())
                .isEqualTo("alternative");
        assertThat(factory.getBeanDefinitionCount()).isEqualTo(1);
    }

    @Test
    void sameTypeDifferentNamesAreNotDefinitionOverrides() {
        DefaultListableBeanFactory factory =
                new DefaultListableBeanFactory();
        factory.setAllowBeanDefinitionOverriding(false);

        factory.registerBeanDefinition(
                "firstGateway",
                new RootBeanDefinition(DefaultGateway.class));
        factory.registerBeanDefinition(
                "secondGateway",
                new RootBeanDefinition(AlternativeGateway.class));

        assertThat(factory.getBeanNamesForType(Gateway.class))
                .containsExactlyInAnyOrder("firstGateway", "secondGateway");

        assertThatThrownBy(() -> factory.getBean(Gateway.class))
                .isInstanceOf(NoUniqueBeanDefinitionException.class);
    }
}
```

Trong thư mục `bean-backoff-lab`, dùng JDK 17+ và Maven:

```bash
mvn test
```

**Kết quả mong đợi:** năm bài test thành công. Maven Surefire thường ghi `Tests run: 5, Failures: 0, Errors: 0, Skipped: 0` trong báo cáo; những dòng log khác có thể thay đổi theo môi trường. Các test không gọi `System.out.println`, nên không giả định một dòng stdout nghiệp vụ.

| Kiểm thử | Hành vi được xác minh |
| --- | --- |
| `defaultIsRegisteredWhenNoUserBeanExists` | Có `defaultGateway` khi thiếu bean người dùng. |
| `userBeanMakesDefaultBackOffWithoutMatchingName` | Có `myGateway` và **không có** `defaultGateway` dù tên hai bean khác nhau. |
| `duplicateNameFailsWhenOverridingIsDisabled` | `BeanDefinitionOverrideException` và definition ban đầu vẫn được giữ. |
| `duplicateNameReplacesDefinitionWhenEnabled` | `sharedGateway` theo definition thứ hai, số definition còn 1. |
| `sameTypeDifferentNamesAreNotDefinitionOverrides` | Hai tên cùng kiểu tồn tại; tra cứu duy nhất theo kiểu bị mơ hồ. |

**Giải thích khả năng chạy:**

- Các lớp implementation trong test là `public static` và có constructor không tham số, nên `RootBeanDefinition` có thể khởi tạo.
- `GatewayAutoConfiguration` là auto-configuration **lồng trong test**; runner nạp nó bằng `AutoConfigurations.of` nên không cần tạo file imports trong bài thực hành.
- `UserConfiguration` được nạp như cấu hình ứng dụng qua `withUserConfiguration`; auto-configuration được xử lý sau, vì vậy điều kiện thiếu bean nhìn thấy `myGateway`.
- Ba test về registry cố ý gọi `registerBeanDefinition` **trước khi tạo instance bằng `getBean`**. Chúng xác minh sự thay thế **definition**, không mô phỏng ghi đè một singleton đang được sử dụng ở runtime.
- Trong một starter thật, đưa class auto-configuration vào `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, dùng tên lớp đầy đủ từng dòng.

### 5.3. Tự mở rộng bài test

Thử đổi condition trong `GatewayAutoConfiguration` thành:

```java
// Chỉ thay annotation trong ví dụ, không phải file độc lập:
@ConditionalOnMissingBean(name = "defaultGateway")
```

Bean do người dùng tên `myGateway` không đáp ứng điều kiện kiểm tra **tên `defaultGateway`**. Vì vậy default có thể được đăng ký thêm, dẫn đến hai bean cùng kiểu `Gateway` nhưng tên khác. Đây là bài tập để quan sát **khác biệt giữa backoff theo tên và backoff theo kiểu**; nếu áp dụng thay đổi, các assertion ở test thứ hai phải đổi tương ứng.

Thử gọi `factory.setAllowBeanDefinitionOverriding(true)` ở test trùng tên đang kỳ vọng exception và kiểm tra lại loại behavior. Việc đổi flag chỉ kiểm soát hành vi registry khi trùng **tên**, không làm `@ConditionalOnMissingBean` tự biến thành cơ chế override.

## 6. Cách thiết kế khả năng tùy biến trong starter

Một starter cung cấp `PaymentGateway` nên:

1. **Định nghĩa interface rõ ràng** mà ứng dụng có thể tự implement.
2. **Đăng ký bean mặc định trong auto-configuration** với `@ConditionalOnMissingBean(PaymentGateway.class)`. Nếu cần điều kiện classpath, property hoặc môi trường web, kết hợp các condition tương ứng.
3. **Để ứng dụng dùng tên bean tùy chọn**, miễn nó công bố đúng kiểu `PaymentGateway`. Tránh buộc người dùng khai báo lại đúng tên internal của starter.
4. **Kiểm thử cả hai ngả**: không có custom bean và có custom bean; thêm thử nghiệm khi hai auto-configuration cạnh tranh cùng kiểu nếu starter có fallback.
5. **Không dựa vào bật bean definition overriding global** để thực hiện extension point thông thường.

Với yêu cầu có **nhiều implementation cùng tồn tại**, nên đặt tên riêng và dùng `@Qualifier`, `@Primary`, hoặc inject collection `List<PaymentGateway>` / `Map<String, PaymentGateway>` theo nhu cầu. Đây là cơ chế lựa chọn dependency, không phải backoff hay definition overriding.

Nếu thật sự cần **ghi đè definition cùng tên** do một framework tích hợp có hợp đồng riêng, phải xác nhận flag, đường đăng ký, thời điểm đăng ký và tên bean ổn định; thêm integration test để quan sát kết quả trong context thực. Tránh đặt giả định rằng một bean trong thư viện sẽ luôn được đăng ký trước hoặc sau chỉ vì thứ tự dependency trong `pom.xml`.

## 7. Chẩn đoán lỗi: nhìn tên bean trước, rồi nhìn condition

### Gặp `BeanDefinitionOverrideException`

- Đọc thông báo lỗi để xác định **bean name** trùng và hai nguồn definition.
- Kiểm tra có phương thức `@Bean`/component scan tạo cùng tên ngoài ý muốn không. Hai bean cùng tên có thể đến từ hai module, package khác nhau.
- Nếu bean của thư viện phải nhường chỗ, sửa auto-configuration dùng condition phù hợp và test; đặt tên khác nhau cho hai implementation hợp lệ.
- Chỉ cân nhắc `spring.main.allow-bean-definition-overriding=true` khi thật sự muốn cơ chế đăng ký thay definition, đã hiểu thứ tự và ảnh hưởng với các thư viện khác.

### Gặp `NoUniqueBeanDefinitionException`

Thường có **nhiều bean khác tên cùng kiểu** và một chỗ inject đang yêu cầu bean duy nhất. Hãy quyết định có chủ ý nhiều implementation không. Nếu chỉ cần một default, kiểm tra condition có tìm theo đúng **kiểu interface** hay chỉ theo tên. Nếu cần nhiều implementation, dùng qualifier/primary/collection thích hợp. Bật overriding **không** giải quyết nếu không có tên trùng.

### Bean tùy chỉnh đã có nhưng default vẫn được tạo

- Condition default xét `PaymentGateway.class`, implementation cụ thể hay `name`?
- Chữ ký `@Bean` của người dùng khai báo kiểu đủ cụ thể chưa? Trả về `Object` có thể làm điều kiện theo interface không nhận ra definition đúng lúc.
- Bean custom có được nạp **trước** auto-configuration không? Nó nằm ở context hiện tại hay cha/con? Xem thuộc tính `search` nếu dùng hierarchy.
- Auto-configuration có đang được nạp đúng qua file imports không? Có condition khác ở mức lớp và mức phương thức không?

Có thể bật `--debug` khi chạy ứng dụng Spring Boot để xem **Condition Evaluation Report**, hoặc dùng Actuator `/actuator/conditions` nếu đã bật và được phép truy cập. Với starter, `ApplicationContextRunner` đặc biệt tiện để cô lập điều kiện.

### Bật overriding nhưng bean sau cùng không như ý

Kiểm tra **đường đăng ký** và **thứ tự thực tế**, vì bean definition overriding theo tên không hàm ý bean của người dùng luôn thắng. Một số đường xử lý `@Configuration`/component scan có quy tắc xử lý definition đặc biệt. Hãy tạo integration test cho đúng bộ dependency của ứng dụng, thay vì suy luận từ thứ tự dòng imports.

## 8. Sai lầm phổ biến

| Quan niệm sai | Thực tế |
| --- | --- |
| “Custom bean phải có cùng tên với bean mặc định.” | Backoff theo kiểu không cần tên giống nhau. |
| “`@ConditionalOnMissingBean` xóa default đã đăng ký.” | Nó ngăn việc **đăng ký default** khi condition không khớp. |
| “Hai bean cùng kiểu là đã ghi đè nhau.” | Khác tên thì không phải definition overriding. |
| “`@Primary` làm một definition thay definition kia.” | `@Primary` tác động tới lựa chọn khi injection. |
| “Bật bean definition overriding giúp mọi custom bean thắng.” | Nếu cho phép override, definition đăng ký sau có thể thay trước; không đảm bảo nguồn thắng. |
| “Overriding mặc định được bật trong Spring Boot 3.” | Thuộc tính `spring.main.allow-bean-definition-overriding` mặc định `false`. |
| “`@ConditionalOnMissingBean` nhìn thấy mọi bean sẽ đăng ký trong tương lai.” | Condition chỉ xét những definition đã được xử lý tới lúc đánh giá. |
| “Hai `@Bean` trùng tên luôn ném cùng một lỗi bất kể cách nạp.” | Các đường xử lý/scan có quy tắc riêng; kiểm tra tình huống thực tế. |
| “Cho phép overriding thì mọi xung đột injection đều hết.” | Nhiều bean **khác tên cùng kiểu** vẫn có thể tạo injection ambiguity. |

## 9. Tự kiểm tra

**Câu 1.** Starter đăng ký `defaultGateway` với `@ConditionalOnMissingBean(Gateway.class)`, ứng dụng tự khai báo `@Bean("myGateway") Gateway custom()`. Có cần bật overriding không?  
**Đáp án:** Không. Auto-configuration back off theo kiểu `Gateway` khi thấy user bean; default không được đăng ký.

**Câu 2.** Có hai definition cùng tên `sharedGateway` trong một registry đã tắt overriding. Điều gì có thể xảy ra khi definition thứ hai được đăng ký?  
**Đáp án:** Lỗi `BeanDefinitionOverrideException` trong đường đăng ký từ chối trùng tên.

**Câu 3.** Hai bean tên `bankGateway` và `cardGateway` đều implement `Gateway`. Đây là overriding?  
**Đáp án:** Không, vì khác tên. Khi inject một `Gateway` duy nhất có thể cần `@Qualifier` hoặc `@Primary`.

**Câu 4.** Vì sao `@ConditionalOnMissingBean(name = "defaultGateway")` không nhất thiết back off khi có user bean tên `myGateway` cùng kiểu?  
**Đáp án:** Condition chỉ tìm **tên** `defaultGateway`, không tự coi tên `myGateway` là đã có.

**Câu 5.** Bật `spring.main.allow-bean-definition-overriding=true` có đồng nghĩa bean của ứng dụng luôn giành ưu tiên không?  
**Đáp án:** Không. Kết quả ghi đè phụ thuộc definition nào được đăng ký sau và đường đăng ký.

**Câu 6.** Nếu auto-configuration cạnh tranh khác được xử lý trước và đã đăng ký bean cùng interface, condition thiếu bean của auto-configuration sau sẽ ra sao?  
**Đáp án:** Thường không khớp và mặc định của lớp sau rút lui, giả sử hai condition kiểm tra cùng kiểu hợp đồng và không có điều kiện đặc biệt khác.

**Kết luận:** **Conditional backoff** quyết định **không đăng ký** bean default khi đã có bean phù hợp; **bean definition overriding** quyết định có thay definition **đã đăng ký cùng tên** hay không. Với extension point trong Spring Boot starter, ưu tiên backoff đúng kiểu, giữ mặc định chống ghi đè tên và kiểm chứng bằng test. Khi có lỗi, phân biệt **trùng tên**, **trùng kiểu**, thứ tự đánh giá condition và thứ tự đăng ký definition.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — `@ConditionalOnMissingBean` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot 3.3 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — `SpringApplication` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework 6.1 — `BeanDefinitionOverrideException` API: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionOverrideException.html