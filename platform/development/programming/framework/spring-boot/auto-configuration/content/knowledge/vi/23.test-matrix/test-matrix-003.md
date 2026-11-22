# Không có bean người dùng, có bean thay thế và có nhiều ứng viên

## 1. Mục tiêu và tình huống cần giải quyết

Một auto-configuration thường cung cấp bean mặc định để ứng dụng có thể chạy ngay sau khi thêm starter. Đồng thời, thư viện cần nhường quyền cho ứng dụng khi người dùng tự khai báo implementation. Vấn đề trở nên phức tạp khi ứng dụng có **nhiều bean cùng kiểu**: auto-configuration có nên tạo thêm bean mặc định không, và một bean khác phụ thuộc vào kiểu đó có thể được tạo hay không?

Spring Boot cung cấp hai condition rất quan trọng nhưng có ý nghĩa khác nhau:

- `@ConditionalOnMissingBean`: chỉ khớp khi **không có bean nào** đáp ứng tiêu chí được kiểm tra trong BeanFactory tại thời điểm condition được đánh giá. Đây là cơ chế phổ biến để tạo default bean và cho phép người dùng override.
- `@ConditionalOnSingleCandidate`: chỉ khớp khi có bean phù hợp và Spring có thể xác định **một candidate duy nhất để autowire**. Nếu có nhiều bean, một bean được đánh dấu `@Primary` có thể làm condition khớp.

Bài này dùng ví dụ `GreetingService` và `GreetingClient` để phân tích bốn tình huống:

1. Không có bean `GreetingService` do người dùng khai báo.
2. Người dùng khai báo đúng một bean thay thế.
3. Người dùng khai báo nhiều bean nhưng không có primary candidate.
4. Người dùng khai báo nhiều bean và có một bean `@Primary`.

Sau bài học, bạn cần phân biệt được **không tồn tại**, **có thể chọn một**, và **có nhiều candidate nhập nhằng**; biết cách đặt thứ tự auto-configuration; hiểu vai trò của `@Primary`, `@Qualifier`, `List<T>` và `ObjectProvider<T>`; và viết test riêng cho từng tổ hợp.

Phạm vi: Spring Boot 3.3.13, Spring Framework 6.1 và Java 17+.

## 2. Hai câu hỏi khác nhau: có bean nào không, và có chọn được một bean không?

Giả sử ứng dụng có một kiểu:

```java
public interface GreetingService {
    String greet(String name);
}
```

Hai condition tương ứng với hai câu hỏi:

| Condition | Câu hỏi | Khớp khi |
| --- | --- | --- |
| `@ConditionalOnMissingBean(GreetingService.class)` | Có bean nào phù hợp với `GreetingService` đã được đăng ký chưa? | Không có bean phù hợp |
| `@ConditionalOnSingleCandidate(GreetingService.class)` | Có thể chọn được một `GreetingService` để autowire không? | Có một bean, hoặc nhiều bean nhưng xác định được primary candidate |

Hai câu hỏi không phải hai cách viết khác nhau cho cùng một điều kiện.

### 2.1. `@ConditionalOnMissingBean` là phép kiểm tra sự vắng mặt

Ví dụ:

```java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() {
    return new DefaultGreetingService();
}
```

Khi Spring xử lý method này:

- Nếu chưa có bean nào phù hợp với `GreetingService`, method được đăng ký và default bean có thể được tạo.
- Nếu người dùng đã có một bean `GreetingService`, default method back off.
- Nếu người dùng đã có hai hoặc nhiều bean `GreetingService`, default method vẫn back off. Chỉ cần **có ít nhất một bean phù hợp** là điều kiện missing không còn khớp.

`@Primary` không thay đổi phép kiểm tra này. Một bean primary vẫn là bean tồn tại; nhiều bean với một primary cũng vẫn khiến `@ConditionalOnMissingBean` không khớp.

### 2.2. `@ConditionalOnSingleCandidate` kiểm khả năng phân giải một dependency

Ví dụ:

```java
@Bean
@ConditionalOnSingleCandidate(GreetingService.class)
GreetingClient greetingClient(GreetingService service) {
    return new GreetingClient(service);
}
```

Condition này hỏi liệu Spring có thể chọn một candidate khi cần autowire `GreetingService` hay không.

- Không có bean phù hợp: condition không khớp.
- Có đúng một bean: condition khớp.
- Có nhiều bean và không có primary candidate: condition không khớp.
- Có nhiều bean và một primary candidate: condition khớp; dependency một giá trị có thể được phân giải qua primary.

**“Single candidate” không đồng nghĩa “chỉ có đúng một bean trong context”.** Có thể có hai, ba hoặc nhiều bean, nhưng một bean `@Primary` được chọn làm candidate mặc định cho injection một giá trị.

Javadoc Spring Boot 3.3.13 mô tả rõ rằng condition vẫn khớp khi nhiều bean cùng kiểu tồn tại nhưng có primary candidate; điều kiện tương đương với việc autowire một bean theo kiểu đó có thể thành công.

## 3. Ma trận kết quả cho 0, 1 và nhiều bean

Giả sử starter cung cấp hai auto-configuration theo thứ tự:

1. `DefaultGreetingAutoConfiguration` đăng ký default `GreetingService` khi thiếu bean.
2. `GreetingClientAutoConfiguration` đăng ký `GreetingClient` khi có single candidate `GreetingService`.

Kết quả:

| Bean do ứng dụng khai báo | Default service từ starter | `@ConditionalOnMissingBean` | `@ConditionalOnSingleCandidate` | Client từ starter |
| --- | --- | --- | --- | --- |
| Không có | Được tạo | Khớp | Khớp với default bean | Được tạo |
| Một custom bean | Back off | Không khớp | Khớp với custom bean | Được tạo |
| Hai custom bean, không primary | Back off | Không khớp | Không khớp | Không được tạo |
| Hai custom bean, một primary | Back off | Không khớp | Khớp với primary candidate | Được tạo |

Ở hàng “hai custom bean, không primary”, context vẫn có thể khởi động bình thường nếu không có bean nào bắt buộc inject trực tiếp một `GreetingService` đơn lẻ. Client bị condition bỏ qua nên không tạo ra lỗi ambiguity tại method đó.

Nếu một bean khác vẫn inject `GreetingService` mà không dùng qualifier và không có primary, Spring có thể ném `NoUniqueBeanDefinitionException` khi tạo bean phụ thuộc. Condition của auto-configuration không tự sửa mọi injection point trong ứng dụng.

## 4. Tình huống 1: không có bean người dùng — starter tạo default

Đây là trường hợp cơ bản nhất. Ứng dụng thêm starter nhưng không cung cấp implementation.

```text
Application user beans:
  GreetingService: 0

DefaultGreetingAutoConfiguration:
  @ConditionalOnMissingBean(GreetingService.class) -> MATCH
  register defaultGreetingService

GreetingClientAutoConfiguration:
  @ConditionalOnSingleCandidate(GreetingService.class) -> MATCH
  register greetingClient
```

Ví dụ default implementation:

```java
public final class DefaultGreetingService implements GreetingService {

    @Override
    public String greet(String name) {
        return "default: " + name;
    }
}
```

Khi default service đã được đăng ký, client có thể nhận nó qua constructor/method injection:

```java
public final class GreetingClient {

    private final GreetingService service;

    public GreetingClient(GreetingService service) {
        this.service = service;
    }

    public String greet(String name) {
        return this.service.greet(name);
    }
}
```

Thiết kế này tạo trải nghiệm “thêm starter là chạy”: người dùng không phải tự viết bean nếu chấp nhận default behavior. Bean default vẫn có thể được thay thế sau này bằng cách khai báo bean cùng kiểu trước khi auto-configuration đánh giá condition.

## 5. Tình huống 2: người dùng có một bean thay thế — default back off

Ứng dụng cung cấp implementation riêng:

```java
@Configuration(proxyBeanMethods = false)
class CustomGreetingConfiguration {

    @Bean
    GreetingService customGreetingService() {
        return name -> "custom: " + name;
    }
}
```

Khi auto-configuration xử lý:

- Bean `customGreetingService` đã được đăng ký.
- `@ConditionalOnMissingBean(GreetingService.class)` không khớp.
- Starter không đăng ký default service.
- `@ConditionalOnSingleCandidate(GreetingService.class)` khớp vì chỉ có một candidate.
- `GreetingClient` nhận custom service.

Kết quả:

```text
GreetingService beans: 1
Default service: absent
Client: present
client.greet("Ada") -> custom: Ada
```

Đây là hành vi back off thông thường mà Spring Boot hướng tới trong starter: cung cấp default khi người dùng chưa cấu hình, và tôn trọng custom bean khi đã có.

### 5.1. Vì sao condition cần nằm trong auto-configuration?

Bean condition chỉ có thể xét những bean definition mà context đã xử lý **tới thời điểm condition được đánh giá**. Nếu đặt logic tương tự trong một cấu hình tùy ý được xử lý quá sớm, bean của ứng dụng có thể chưa được nhìn thấy và default bean có thể được đăng ký ngoài ý muốn.

Spring Boot khuyến nghị sử dụng `@ConditionalOnBean` và `@ConditionalOnMissingBean` trên auto-configuration classes. Auto-configuration được xử lý sau các user-defined bean definitions, nhờ đó default bean có thể nhường quyền đúng cách.

## 6. Tình huống 3: nhiều bean, không có primary — default vẫn back off

Ứng dụng có hai implementation:

```java
@Configuration(proxyBeanMethods = false)
class MultipleGreetingConfiguration {

    @Bean("formalGreetingService")
    GreetingService formalGreetingService() {
        return name -> "Good day, " + name;
    }

    @Bean("casualGreetingService")
    GreetingService casualGreetingService() {
        return name -> "Hi, " + name;
    }
}
```

Khi context xử lý auto-configuration:

- Có ít nhất một bean `GreetingService` nên default service back off.
- Có hai candidate cùng kiểu.
- Không có `@Primary` nên Spring không thể tự chọn một candidate cho injection một giá trị.
- `@ConditionalOnSingleCandidate` không khớp.
- `GreetingClient` mặc định không được đăng ký.

Kết quả:

```text
GreetingService beans: 2
Default service: absent
Single candidate: no
Client: absent
```

Đây là tình huống cần chủ động quyết định chính sách của thư viện. Starter không nên âm thầm chọn bean đầu tiên dựa trên thứ tự đăng ký nếu API của nó yêu cầu một chiến lược duy nhất.

### 6.1. Nếu inject trực tiếp một bean đơn lẻ thì sao?

Ví dụ:

```java
@Bean
GreetingClient greetingClient(GreetingService service) {
    return new GreetingClient(service);
}
```

Nếu có hai bean `GreetingService` và không có primary/qualifier phù hợp, khi Spring tạo `GreetingClient`, dependency không thể được phân giải và context có thể thất bại với `NoUniqueBeanDefinitionException`.

Dùng `@ConditionalOnSingleCandidate` trên bean method là một cách để chỉ đăng ký client khi dependency đơn lẻ có thể được chọn. Condition tránh đăng ký một bean mà dependency bắt buộc của nó đang nhập nhằng.

### 6.2. Nếu client cần tất cả implementation thì không dùng single candidate

Nếu nghiệp vụ muốn chạy cả formal và casual service, hãy nhận collection:

```java
@Bean
GreetingBatchClient greetingBatchClient(
    List<GreetingService> services
) {
    return new GreetingBatchClient(services);
}
```

Hoặc dùng `ObjectProvider<GreetingService>` để tra cứu linh hoạt:

```java
@Bean
GreetingBatchClient greetingBatchClient(
    ObjectProvider<GreetingService> services
) {
    return new GreetingBatchClient(
        services.orderedStream().toList()
    );
}
```

Với collection, nhiều bean là điều hợp lệ; không cần ép chúng thành một candidate duy nhất. Nếu thứ tự xử lý có ý nghĩa, dùng `@Order`/`Ordered` và một quy tắc rõ ràng.

## 7. Tình huống 4: nhiều bean và có một @Primary — có thể chọn một

Nếu một implementation được coi là lựa chọn mặc định, đánh dấu nó bằng `@Primary`:

```java
@Configuration(proxyBeanMethods = false)
class PrimaryGreetingConfiguration {

    @Bean("formalGreetingService")
    @Primary
    GreetingService formalGreetingService() {
        return name -> "Good day, " + name;
    }

    @Bean("casualGreetingService")
    GreetingService casualGreetingService() {
        return name -> "Hi, " + name;
    }
}
```

Lúc này:

- Cả hai bean `GreetingService` vẫn tồn tại.
- `@ConditionalOnMissingBean` vẫn không khớp vì đã có bean.
- `@ConditionalOnSingleCandidate` khớp vì có một primary candidate.
- Injection `GreetingService` một giá trị chọn bean primary.
- Injection `List<GreetingService>` vẫn nhận cả hai implementation.

Kết quả:

```text
GreetingService beans: 2
Primary candidate: formalGreetingService
Default service: absent
Single candidate: yes
Client: present
client.greet("Ada") -> Good day, Ada
```

**`@Primary` không xóa hoặc loại bean còn lại.** Nó chỉ giúp Spring ưu tiên một candidate trong những tình huống cần một dependency đơn lẻ. Nếu cần tất cả implementation, dùng collection; nếu cần một bean cụ thể theo tên/role, dùng qualifier.

### 7.1. Khi có nhiều bean primary?

Không nên cấu hình nhiều candidate cùng được đánh dấu primary cho cùng kiểu rồi kỳ vọng Spring tự chọn. Nếu không thể xác định một primary duy nhất, injection một giá trị vẫn có thể nhập nhằng và `@ConditionalOnSingleCandidate` không thể dựa vào một lựa chọn rõ ràng.

Hãy thiết kế một primary candidate cho kiểu cần chọn, hoặc chuyển sang qualifier/collection và quy tắc chọn riêng.

## 8. @Qualifier, @Primary, @Order và collection có nhiệm vụ khác nhau

| Cơ chế | Dùng khi | Tác động |
| --- | --- | --- |
| `@Primary` | Có nhiều bean cùng kiểu và muốn một bean là mặc định cho injection đơn | Ưu tiên một candidate |
| `@Qualifier` | Injection point biết chính xác bean/nhóm bean cần dùng | Chọn theo qualifier được khai báo |
| `@Order` / `Ordered` | Cần sắp xếp nhiều bean trong collection/ordered stream | Quy định thứ tự, không loại bean |
| `List<T>` | Cần nhận mọi implementation phù hợp | Inject nhiều bean |
| `Map<String,T>` | Cần nhận nhiều bean và truy cập theo bean name | Key là tên bean Spring |
| `ObjectProvider<T>.orderedStream()` | Cần tra cứu 0/N bean một cách linh hoạt, theo thứ tự | Stream có thể rỗng hoặc chứa nhiều candidate |
| `@ConditionalOnSingleCandidate` | Auto-configuration chỉ tạo bean khi một dependency có thể được chọn đơn lẻ | Gate bean theo khả năng chọn candidate |
| `@ConditionalOnMissingBean` | Auto-configuration cần tạo default khi chưa có bean phù hợp | Back off khi đã có bean |

Ví dụ dùng qualifier:

```java
@Bean
GreetingClient formalClient(
    @Qualifier("formalGreetingService") GreetingService service
) {
    return new GreetingClient(service);
}
```

`@Qualifier` là lựa chọn tường minh tại injection point. Nó không xóa bean khác khỏi context. Cũng không nên giả định rằng thêm qualifier trên một method parameter sẽ khiến mọi condition `@ConditionalOnSingleCandidate` coi context chỉ có một bean; condition này đánh giá khả năng xác định candidate theo quy tắc của nó, đặc biệt là primary candidate.

**Không dùng `@Order` thay cho `@Primary`.** Order sắp xếp collection; primary giúp phân giải injection một giá trị. Bean có order nhỏ nhất không tự trở thành bean được chọn cho mọi dependency đơn.

## 9. Thứ tự auto-configuration là yếu tố quyết định condition nhìn thấy bean nào

Cả `@ConditionalOnMissingBean` và `@ConditionalOnSingleCandidate` chỉ nhìn thấy những bean definition đã được xử lý tại thời điểm đánh giá. Vì vậy, khi một auto-configuration phụ thuộc vào bean do auto-configuration khác cung cấp, cần khai báo thứ tự rõ ràng.

Ví dụ:

```java
@AutoConfiguration
public class DefaultGreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}

@AutoConfiguration(after = DefaultGreetingAutoConfiguration.class)
public class GreetingClientAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(GreetingService.class)
    GreetingClient greetingClient(GreetingService service) {
        return new GreetingClient(service);
    }
}
```

Quan hệ `after` bảo đảm auto-configuration tạo client được xử lý sau auto-configuration cung cấp default service. Khi đó:

- Không có user bean: default service đã được đăng ký trước khi kiểm tra client.
- Có một custom bean: default service back off, client nhìn thấy custom bean.
- Có nhiều custom bean không primary: default back off, client condition không khớp.
- Có nhiều custom bean một primary: default back off, client condition khớp nhờ primary candidate.

**Không dùng thứ tự dòng trong `AutoConfiguration.imports` làm quy tắc dependency.** Khai báo `before`/`after` hoặc `beforeName`/`afterName` trên auto-configuration theo quan hệ thực tế. Thứ tự áp dụng auto-configuration ảnh hưởng thứ tự đăng ký bean definitions; nó không tự quy định thứ tự khởi tạo mọi bean instance.

## 10. Ví dụ kiểm thử Java 17+ chạy độc lập bằng ApplicationContextRunner

Ví dụ này kiểm chứng bốn tình huống trong một dự án Maven. `ApplicationContextRunner` tạo context cô lập cho từng kịch bản; `AutoConfigurations.of(...)` nạp các auto-configuration cần test; `withUserConfiguration(...)` thêm bean do ứng dụng cung cấp.

### 10.1. Cấu trúc

```text
single-candidate-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── GreetingAutoConfigurationTests.java
```

### 10.2. File `pom.xml`

```xml
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

    <groupId>demo</groupId>
    <artifactId>single-candidate-demo</artifactId>
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

### 10.3. File `src/test/java/demo/GreetingAutoConfigurationTests.java`

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

class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    DefaultGreetingAutoConfiguration.class,
                    GreetingClientAutoConfiguration.class
                )
            );

    interface GreetingService {
        String greet(String name);
    }

    static final class DefaultGreetingService implements GreetingService {
        @Override
        public String greet(String name) {
            return "default: " + name;
        }
    }

    static final class GreetingClient {
        private final GreetingService service;

        GreetingClient(GreetingService service) {
            this.service = service;
        }

        String greet(String name) {
            return this.service.greet(name);
        }
    }

    @AutoConfiguration
    static class DefaultGreetingAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(GreetingService.class)
        GreetingService greetingService() {
            return new DefaultGreetingService();
        }
    }

    @AutoConfiguration(after = DefaultGreetingAutoConfiguration.class)
    static class GreetingClientAutoConfiguration {

        @Bean
        @ConditionalOnSingleCandidate(GreetingService.class)
        GreetingClient greetingClient(GreetingService service) {
            return new GreetingClient(service);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class OneUserServiceConfiguration {

        @Bean
        GreetingService customGreetingService() {
            return name -> "custom: " + name;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoUserServicesConfiguration {

        @Bean("formalGreetingService")
        GreetingService formalGreetingService() {
            return name -> "formal: " + name;
        }

        @Bean("casualGreetingService")
        GreetingService casualGreetingService() {
            return name -> "casual: " + name;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoServicesWithPrimaryConfiguration {

        @Bean("primaryGreetingService")
        @Primary
        GreetingService primaryGreetingService() {
            return name -> "primary: " + name;
        }

        @Bean("secondaryGreetingService")
        GreetingService secondaryGreetingService() {
            return name -> "secondary: " + name;
        }
    }

    @Test
    void createsDefaultWhenNoUserBeanExists() {
        this.contextRunner.run(context -> {
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context).hasSingleBean(GreetingClient.class);

            assertThat(context.getBean(GreetingService.class))
                .isInstanceOf(DefaultGreetingService.class);

            assertThat(context.getBean(GreetingClient.class).greet("Ada"))
                .isEqualTo("default: Ada");
        });
    }

    @Test
    void backsOffWhenOneUserBeanExists() {
        this.contextRunner
            .withUserConfiguration(OneUserServiceConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(GreetingService.class);
                assertThat(context).hasSingleBean(GreetingClient.class);

                assertThat(context.getBean(GreetingClient.class).greet("Ada"))
                    .isEqualTo("custom: Ada");
            });
    }

    @Test
    void skipsSingleCandidateClientWhenMultipleBeansHaveNoPrimary() {
        this.contextRunner
            .withUserConfiguration(TwoUserServicesConfiguration.class)
            .run(context -> {
                assertThat(context.getBeanNamesForType(GreetingService.class))
                    .hasSize(2);

                assertThat(context)
                    .doesNotHaveBean(GreetingClient.class);
            });
    }

    @Test
    void usesPrimaryWhenMultipleBeansExist() {
        this.contextRunner
            .withUserConfiguration(TwoServicesWithPrimaryConfiguration.class)
            .run(context -> {
                assertThat(context.getBeanNamesForType(GreetingService.class))
                    .hasSize(2);

                assertThat(context).hasSingleBean(GreetingClient.class);

                assertThat(context.getBean(GreetingClient.class).greet("Ada"))
                    .isEqualTo("primary: Ada");
            });
    }
}
```

### 10.4. Chạy test

Yêu cầu: JDK 17+, Maven 3.8+ và quyền tải dependency. Tại thư mục `single-candidate-demo` chạy:

```bash
mvn clean test
```

Kết quả logic cần được xác nhận qua bốn test:

| Test | Assertion chính | Kết quả |
| --- | --- | --- |
| `createsDefaultWhenNoUserBeanExists` | Có một service mặc định và một client | Pass |
| `backsOffWhenOneUserBeanExists` | Chỉ có custom service, client dùng custom service | Pass |
| `skipsSingleCandidateClientWhenMultipleBeansHaveNoPrimary` | Có hai service, client không được tạo | Pass |
| `usesPrimaryWhenMultipleBeansExist` | Có hai service, client dùng primary service | Pass |

Maven Surefire sẽ báo bốn test thành công và `BUILD SUCCESS` nếu tất cả assertion đều đúng. Thời gian chạy, banner/log và định dạng báo cáo phụ thuộc môi trường; bảng trên là kết quả hành vi mong đợi, không phải toàn bộ stdout cố định.

### 10.5. Vì sao cần hai auto-configuration riêng?

Nếu default service và client condition đặt tùy tiện trong một cấu hình duy nhất, thứ tự đăng ký bean method có thể khiến condition của client được đánh giá trước khi default bean definition được xử lý. Tách chúng thành hai auto-configuration và khai báo `after` diễn đạt dependency rõ ràng:

- Cấu hình thứ nhất chịu trách nhiệm cung cấp service mặc định nếu thiếu.
- Cấu hình thứ hai chỉ tạo client khi service đã có một candidate có thể autowire.

Đây cũng là cách làm rõ hợp đồng giữa các auto-configuration trong một starter thực tế.

## 11. Các biến thể thiết kế khi có nhiều ứng viên

### 11.1. Nhiều implementation nhưng client chỉ cần một lựa chọn cấu hình sẵn

Nếu người dùng cần chỉ định chính xác implementation nào được dùng, có thể cung cấp property:

```properties
acme.greeting.service=primaryGreetingService
```

Starter đọc property và chọn bean theo tên/qualifier bằng một cơ chế rõ ràng. Khi đó không nên dựa hoàn toàn vào `@Primary` nếu nghiệp vụ yêu cầu cấu hình động hoặc nhiều nhóm chiến lược.

Cần xác định behavior khi property thiếu, sai tên hoặc trỏ tới bean không tồn tại: dùng default, fail-fast hay tắt client. Đừng để một chuỗi tùy ý được coi như bean hợp lệ mà không kiểm tra.

### 11.2. Nhiều implementation đều cần chạy

Nếu tất cả implementation đều có vai trò, hãy nhận `List<GreetingService>` hoặc `ObjectProvider<GreetingService>`. Đặt `@Order` để xác định pipeline khi thứ tự ảnh hưởng kết quả. Không dùng `@ConditionalOnSingleCandidate` vì condition đó được thiết kế cho dependency một candidate.

### 11.3. Bắt buộc phải có đúng một bean

Nếu nghiệp vụ đòi **đúng một bean thực tế**, `@ConditionalOnSingleCandidate` không đủ để kiểm số lượng vì nhiều bean với một primary vẫn làm condition khớp.

Hãy đếm candidate hoặc viết validation riêng:

```java
List<GreetingService> services =
    provider.orderedStream().toList();

if (services.size() != 1) {
    throw new IllegalStateException(
        "Expected exactly one GreetingService, found " + services.size()
    );
}
```

Đây là ví dụ minh họa dùng `ObjectProvider<GreetingService>` đã được inject. Chính sách này khác với “có thể chọn một bean để autowire”. Chỉ dùng khi yêu cầu nghiệp vụ thực sự cấm nhiều bean.

### 11.4. Nhiều bean nhưng có qualifier cụ thể

`@Qualifier` hữu ích khi một bean phụ thuộc một vai trò cụ thể:

```java
@Bean
GreetingClient formalClient(
    @Qualifier("formalGreetingService") GreetingService service
) {
    return new GreetingClient(service);
}
```

Đây là cách lựa chọn rõ ràng tại injection point. Nếu auto-configuration có điều kiện đăng ký client, hãy thiết kế condition tương ứng với chính sách qualifier đó; không giả định `@ConditionalOnSingleCandidate` tự hiểu mọi qualifier của từng injection point.

## 12. Lỗi phổ biến và cách khắc phục

| Lỗi / hiểu nhầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Nghĩ `@ConditionalOnMissingBean` chỉ back off khi có đúng một custom bean | Condition kiểm tra sự vắng mặt; một hay nhiều bean đều khiến nó không khớp | Test cả một và nhiều custom bean |
| Nghĩ `@Primary` làm các bean khác biến mất | Primary chỉ ưu tiên candidate cho injection đơn | Dùng collection khi cần tất cả; kiểm số lượng bằng bean names |
| Nghĩ `@ConditionalOnSingleCandidate` nghĩa là chỉ có đúng một bean | Nhiều bean với primary candidate vẫn khớp | Nếu cần đúng một, đếm collection/provider |
| Dùng `@Order` để chọn một bean cho injection đơn | Order sắp xếp collection, không thay primary/qualifier | Dùng `@Primary` hoặc `@Qualifier` |
| Inject `GreetingService` đơn lẻ khi có hai bean không primary | Spring không biết chọn bean nào | Dùng qualifier, primary hoặc collection |
| Đặt bean condition trong cấu hình được xử lý quá sớm | Condition chỉ thấy bean definitions đã được xử lý | Dùng auto-configuration và khai báo `after` khi phụ thuộc cấu hình khác |
| Dùng `@ConditionalOnMissingBean` để quyết định pipeline cần đúng một plugin | Missing bean chỉ kiểm vắng mặt, không kiểm cardinality | Dùng `@ConditionalOnSingleCandidate` hoặc validation số lượng tùy yêu cầu |
| Tưởng client condition khớp thì bean client chắc chắn tạo thành công | Dependency khác hoặc constructor có thể lỗi | Kiểm thử context và bean thực tế |
| Chỉ test trường hợp không có custom bean | Không phát hiện lỗi back off, ambiguity và primary | Test ma trận 0/1/N và có/không primary |
| Dùng một bean name cố định nhưng không có qualifier | Bean name không tự động chọn injection candidate trong mọi trường hợp | Khai báo `@Qualifier` đúng nơi cần chọn |

## 13. Quy trình kiểm thử ma trận cho starter

Khi phát triển auto-configuration có default service và bean phụ thuộc vào service đó, nên có ít nhất các test sau:

1. **Không có user bean:** default được đăng ký; client được tạo; kết quả dùng default.
2. **Một user bean:** default back off; client dùng implementation của ứng dụng.
3. **Hai user bean không primary:** default back off; condition single candidate không khớp; xác nhận client không được đăng ký nếu đó là chính sách.
4. **Hai user bean, một primary:** default back off; client được tạo và dùng primary.
5. **Nhiều bean cùng primary hoặc cấu hình primary nhập nhằng:** xác nhận lỗi/behavior được mong muốn; không giả định có lựa chọn duy nhất.
6. **User bean có qualifier:** kiểm tra injection point cụ thể nếu starter hỗ trợ qualifier-based selection.
7. **Context cha/con:** nếu bean có thể nằm ở parent context, kiểm tra thuộc tính `search` của condition và context hierarchy.
8. **Điều kiện khác:** kết hợp property, classpath và bean conditions để chắc chắn một condition không che lấp lỗi của condition khác.

`ApplicationContextRunner` phù hợp cho các tổ hợp này vì mỗi test tạo context có cấu hình rõ ràng. Khi nhiều auto-configuration tham gia, `AutoConfigurations.of(...)` sử dụng cùng quy tắc sắp xếp như ứng dụng Spring Boot.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Người dùng khai báo hai bean `GreetingService` không có `@Primary`. `@ConditionalOnMissingBean(GreetingService.class)` có khớp không?  
**Đáp án:** Không. Có ít nhất một bean phù hợp nên default service back off.

**Câu 2.** Với hai bean cùng kiểu và một bean primary, `@ConditionalOnSingleCandidate(GreetingService.class)` có khớp không?  
**Đáp án:** Có. Spring xác định được primary candidate cho injection đơn.

**Câu 3.** `@ConditionalOnSingleCandidate` có bảo đảm context chỉ có đúng một `GreetingService` không?  
**Đáp án:** Không. Có thể có nhiều bean, miễn là một candidate primary có thể được xác định.

**Câu 4.** `@Primary` có làm `@ConditionalOnMissingBean` khớp lại không?  
**Đáp án:** Không. Primary vẫn là bean tồn tại; missing condition vẫn không khớp.

**Câu 5.** Có hai service không primary, nhưng client muốn dùng tất cả. Nên inject gì?  
**Đáp án:** `List<GreetingService>` hoặc `ObjectProvider<GreetingService>`; nếu thứ tự quan trọng, dùng `orderedStream()` và quy định `@Order`.

**Câu 6.** Vì sao client auto-configuration nên chạy sau default service auto-configuration?  
**Đáp án:** Condition chỉ nhìn bean definitions đã xử lý. Khai báo `after` giúp client condition nhìn thấy default service nếu cấu hình đó đã đăng ký bean.

**Câu 7.** Muốn bắt buộc đúng một bean, có thể chỉ dùng `@ConditionalOnSingleCandidate` không?  
**Đáp án:** Không. Nhiều bean với một primary vẫn khớp. Cần đếm bean/candidate và tự validation nếu cardinality chính xác là yêu cầu.

**Câu 8.** `@Order(1)` và `@Order(2)` có chọn bean order 1 cho injection đơn không?  
**Đáp án:** Không. Order chủ yếu sắp xếp các bean trong collection/ordered stream; injection đơn dùng primary/qualifier và quy tắc candidate.

## 15. Ghi nhớ và tài liệu tham khảo

- `@ConditionalOnMissingBean` kiểm tra **không có bean phù hợp**; chỉ cần một hoặc nhiều bean tồn tại là default back off.
- `@ConditionalOnSingleCandidate` kiểm tra **có thể xác định một candidate để autowire**; một primary candidate cho phép condition khớp dù nhiều bean cùng tồn tại.
- `@Primary` ưu tiên một bean cho injection đơn; không loại bean khác và không làm collection chỉ còn một phần tử.
- `@Qualifier` chọn theo ý định cụ thể của injection point; `@Order` sắp xếp nhiều bean; collection nhận tất cả candidate phù hợp.
- Bean conditions chỉ thấy những bean definition đã được xử lý. Đặt condition trên auto-configuration và dùng `@AutoConfiguration(after = ...)` khi phụ thuộc cấu hình khác.
- Ma trận test tối thiểu nên gồm 0 bean, 1 custom bean, nhiều bean không primary và nhiều bean có primary.

Tài liệu chính thức Spring Boot 3.3.13 / Spring Framework 6.1:

1. [`@ConditionalOnMissingBean` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html) — điều kiện chỉ khớp khi không có bean đáp ứng tiêu chí trong BeanFactory; lưu ý về thứ tự bean definitions.
2. [`@ConditionalOnSingleCandidate` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html) — nhiều bean vẫn khớp nếu có primary candidate.
3. [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html) — bean conditions, thứ tự auto-configuration và ApplicationContextRunner.
4. [`@Primary` Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/context/annotation/Primary.html).
5. [`@Qualifier` Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/beans/factory/annotation/Qualifier.html).
6. [`@Order` Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/core/annotation/Order.html).
7. [`ApplicationContextRunner` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html).
