# Truy vết @Import và cấu hình lồng nhau theo từng nhánh lựa chọn

## Mục tiêu học tập

Khi đọc mã auto-configuration của Spring Boot, một bean thường không xuất hiện trực tiếp trong lớp cấu hình đầu tiên mà ta mở. Cấu hình gốc có thể dùng `@Import` để đưa thêm class, một `ImportSelector` có thể chọn class theo metadata hoặc môi trường, và các lớp `@Configuration` lồng nhau có thể chỉ được xử lý khi điều kiện tương ứng khớp.

Bài học này hướng dẫn cách **lần theo đường đi của một cấu hình từ điểm vào đến bean cuối cùng**. Trọng tâm là quan hệ giữa `@Import`, `ImportSelector`, `DeferredImportSelector`, nested configuration và các condition ở từng nhánh.

Sau bài học, bạn có thể:

- Phân biệt import class trực tiếp với import thông qua selector hoặc registrar.
- Truy vết một nhánh cấu hình từ `@EnableAutoConfiguration` hoặc class cấu hình gốc.
- Hiểu vì sao một nested configuration có thể không được xử lý khi điều kiện không khớp.
- Phân biệt thời điểm parse configuration, đăng ký bean definition và khởi tạo bean.
- Dùng `ApplicationContextRunner` để xác minh từng nhánh mà không phải khởi động toàn bộ ứng dụng.
- Tìm đúng điểm trong source code Spring Framework và Spring Boot khi cần giải thích vì sao một bean xuất hiện hoặc bị bỏ qua.

## 1. Bắt đầu từ điểm vào: ai đưa configuration vào context?

Một class được chú thích `@Configuration` không tự động có mặt trong mọi application context. Nó phải được Spring phát hiện thông qua một cơ chế phù hợp, ví dụ:

- Được đăng ký trực tiếp khi tạo context.
- Được component scan tìm thấy.
- Được một class cấu hình khác đưa vào bằng `@Import`.
- Được trả về từ `ImportSelector` hoặc `DeferredImportSelector`.
- Được đăng ký theo một cơ chế auto-configuration như Spring Boot.

Trong ứng dụng Spring Boot thông thường, `@SpringBootApplication` bao gồm `@EnableAutoConfiguration`. Cơ chế auto-configuration của Boot đưa một `DeferredImportSelector` vào luồng xử lý cấu hình. Selector này tìm danh sách auto-configuration candidates, áp dụng exclusions và các bộ lọc điều kiện phù hợp, rồi đưa các class được chọn vào quá trình parse.

Vì vậy, khi truy vết một bean không nên bắt đầu bằng cách tìm tên bean trong toàn bộ repository rồi dừng ở method `@Bean`. Hãy hỏi trước: **class chứa method đó được đưa vào context bằng đường nào?**

### Sơ đồ tổng quát

~~~text
@SpringBootApplication
        |
        +-- @EnableAutoConfiguration
        |       |
        |       +-- AutoConfigurationImportSelector
        |               |
        |               +-- đọc AutoConfiguration.imports
        |               +-- lọc/exclude/sắp xếp candidates
        |               +-- chọn auto-configuration
        |
        +-- các @Configuration do ứng dụng khai báo
                |
                +-- @Import trực tiếp
                |       +-- Configuration class
                |       +-- ImportSelector
                |       +-- ImportBeanDefinitionRegistrar
                |
                +-- nested @Configuration
                        +-- kiểm tra điều kiện
                        +-- xử lý nhánh phù hợp
~~~

Đây là sơ đồ khái niệm. Luồng thực tế có thể lồng nhiều cấp import và nhiều điều kiện; không phải mọi ứng dụng đều sử dụng tất cả nhánh trên.

## 2. Bốn dạng import cần nhận diện

### 2.1. Import trực tiếp một configuration class

~~~java
@Configuration(proxyBeanMethods = false)
@Import(TransportConfiguration.class)
class ApplicationFeatureConfiguration {
}
~~~

Spring nhận class `TransportConfiguration` làm một nguồn cấu hình cần xử lý. Nếu class đó lại có `@Import`, Spring tiếp tục đi theo import mới. Đây là cách dễ đọc nhất khi tập class cần đưa vào đã biết rõ tại thời điểm biên dịch.

Có thể import nhiều class:

~~~java
@Configuration(proxyBeanMethods = false)
@Import({
    HttpTransportConfiguration.class,
    RetryConfiguration.class
})
class ApplicationFeatureConfiguration {
}
~~~

Việc khai báo class trong `@Import` không đồng nghĩa tất cả bean method bên trong chắc chắn được đăng ký: class configuration vẫn chịu ảnh hưởng của các condition và điều kiện riêng của từng bean method.

### 2.2. Import một class thông thường

`@Import` không chỉ dành cho class mang `@Configuration`. Một class được import có thể được đăng ký như một bean/component definition, tùy loại class và annotation của nó. Tuy nhiên, nếu mục đích là khai báo một nhóm `@Bean` và điều kiện cấu hình, hãy dùng một configuration class rõ ràng.

### 2.3. ImportSelector: chọn class động

`ImportSelector` cho phép quyết định danh sách class cần import dựa trên `AnnotationMetadata` của class đang import selector. Selector trả về **tên đầy đủ của class**, không trực tiếp tạo bean.

~~~java
public class TransportImportSelector implements ImportSelector {

    @Override
    public String[] selectImports(AnnotationMetadata importingClassMetadata) {
        return new String[] {
            HttpTransportConfiguration.class.getName()
        };
    }
}
~~~

Đây là đoạn minh họa. Có thể đọc annotation metadata để lựa chọn class dựa trên thuộc tính của annotation kích hoạt, hoặc implement các interface `Aware` để nhận `Environment`, `ResourceLoader` và các collaborator được Spring hỗ trợ.

Cách dùng:

~~~java
@Configuration(proxyBeanMethods = false)
@Import(TransportImportSelector.class)
class TransportFeatureConfiguration {
}
~~~

Khi parse `TransportFeatureConfiguration`, Spring gọi selector để lấy danh sách import. Class selector không phải một bean nghiệp vụ của ứng dụng; vai trò của nó là **cung cấp danh sách cấu hình được import**.

### 2.4. DeferredImportSelector: chọn sau các configuration thông thường

`DeferredImportSelector` mở rộng `ImportSelector`, nhưng được xử lý **sau khi các cấu hình thông thường đã được parse**. Điều này hữu ích khi việc lựa chọn phụ thuộc vào trạng thái cấu hình tổng thể đã được đọc.

Spring Boot sử dụng cơ chế này trong `AutoConfigurationImportSelector` để đưa auto-configuration vào sau các cấu hình ứng dụng thông thường. Nhờ đó, các điều kiện bean trong auto-configuration có thể được đánh giá sau khi các cấu hình người dùng đã được xử lý theo mô hình mà Boot thiết kế.

Không nên dùng `DeferredImportSelector` chỉ vì muốn code có vẻ linh hoạt hơn. Chọn:
- `@Import(Config.class)` khi tập class cố định và biết trước.
- `ImportSelector` khi danh sách import cần được tính động trong giai đoạn parse.
- `DeferredImportSelector` khi việc chọn import cần diễn ra sau cấu hình thông thường, giống luồng auto-configuration.
  
### 2.5. ImportBeanDefinitionRegistrar: đăng ký definition bằng code

`ImportBeanDefinitionRegistrar` là cơ chế nâng cao cho trường hợp cần đăng ký `BeanDefinition` bằng API của container, thay vì trả về danh sách configuration class. Nó nhận `BeanDefinitionRegistry` và có thể đăng ký các definition theo metadata/điều kiện đã xác định.

Không nên dùng registrar cho mọi tình huống. Nếu một class `@Configuration` với `@Bean` đã biểu đạt rõ ý định, cách đó thường dễ đọc, dễ test và dễ bảo trì hơn.

## 3. Cấu hình lồng nhau: mỗi nhánh có điều kiện riêng

Một configuration class có thể khai báo các static nested class khác mang `@Configuration`. Spring có thể nhận diện các member configuration class này trong lúc xử lý class cha. Mỗi nested class có thể có condition riêng để Spring chỉ xử lý nhánh phù hợp.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class TransportConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "demo.transport",
            name = "mode",
            havingValue = "http")
    static class HttpConfiguration {

        @Bean
        TransportClient httpTransportClient() {
            return () -> "http";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "demo.transport",
            name = "mode",
            havingValue = "queue")
    static class QueueConfiguration {

        @Bean
        TransportClient queueTransportClient() {
            return () -> "queue";
        }
    }
}
~~~

Đây là đoạn minh họa. `TransportClient` là interface do ứng dụng/thư viện định nghĩa. Khi `demo.transport.mode=http`, nested `HttpConfiguration` khớp và đăng ký bean HTTP; nhánh queue không khớp. Khi giá trị là `queue`, kết quả ngược lại.

**Nested configuration nên là static.** Một inner class không static cần instance của class bao ngoài để khởi tạo, không phù hợp với cách Spring xử lý một configuration độc lập. Dùng `static` giúp mỗi nhánh là một cấu hình riêng, có thể được parse và đăng ký độc lập.

### 3.1. Nested configuration tự được nhận diện

Khi một nested class là member configuration class của một class `@Configuration`, Spring có thể phát hiện nó trong quá trình xử lý class cha. Vì vậy, không phải lúc nào cũng cần ghi thêm `@Import(NestedClass.class)` cho chính nested member đó.

Điều này có ý nghĩa khi đọc source: mở class cha, xem các static nested class có annotation `@Configuration`, rồi kiểm tra condition của từng lớp. Một nhánh có thể được phát hiện nhưng bị bỏ qua vì condition không khớp.

### 3.2. Nested configuration được import tường minh

Một cách khác là giữ các nested class trong một holder không phải configuration, sau đó import từng nhánh:

~~~java
final class TransportBranches {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "demo.transport",
            name = "mode",
            havingValue = "http")
    static class HttpConfiguration {
        @Bean
        TransportClient httpTransportClient() {
            return () -> "http";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "demo.transport",
            name = "mode",
            havingValue = "queue")
    static class QueueConfiguration {
        @Bean
        TransportClient queueTransportClient() {
            return () -> "queue";
        }
    }
}

@Configuration(proxyBeanMethods = false)
@Import({
    TransportBranches.HttpConfiguration.class,
    TransportBranches.QueueConfiguration.class
})
class ImportedTransportConfiguration {
}
~~~

Ở đây, class holder `TransportBranches` chỉ tổ chức mã nguồn; nó không tự là configuration. `ImportedTransportConfiguration` đưa hai nhánh vào context. Mỗi nhánh tự quyết định có được xử lý hay không bằng condition của nó.

Hai cách (member configuration được phát hiện tự động và nested class được import tường minh) phục vụ các mục đích khác nhau. Khi đọc mã, hãy kiểm tra cả **quan hệ member class** lẫn danh sách `@Import`; đừng kết luận một nested class không được dùng chỉ vì không thấy nó trong imports array.

### 3.3. Điều kiện ở class và điều kiện ở method

Điều kiện ở class:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(prefix = "demo.transport", name = "mode", havingValue = "http")
static class HttpConfiguration {
    @Bean
    TransportClient httpTransportClient() { ... }
    @Bean
    HttpMetrics httpMetrics() { ... }
}
~~~

Nếu condition của class không khớp, configuration class đó bị bỏ qua, do đó các bean method trong nhánh cũng không được đăng ký.

Điều kiện ở method:

~~~java
@Configuration(proxyBeanMethods = false)
static class HttpConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "demo.transport", name = "metrics", havingValue = "true")
    HttpMetrics httpMetrics() { ... }
}
~~~

Ở đây configuration vẫn có thể được xử lý và các bean method không có condition riêng vẫn có thể được đăng ký; chỉ bean `httpMetrics` bị điều kiện kiểm soát.

Khi đọc một nhánh, hãy xác định condition nào áp dụng lên **toàn bộ class**, condition nào áp dụng lên **một bean method**, và điều kiện có bị kế thừa qua class cha/nested class hay không.

## 4. Truy vết một nhánh từ @Import đến bean

Hãy dùng một chuỗi câu hỏi cố định:

1. **Điểm vào là gì?** Ai đăng ký configuration gốc: component scan, `@Import`, auto-configuration imports hay test runner?
2. **Import đi theo dạng nào?** Class trực tiếp, selector, deferred selector hay registrar?
3. **Class nào được chọn?** Với selector, đọc `selectImports(...)` và các điều kiện/metadata nó dùng.
4. **Có nhánh lồng nhau không?** Kiểm tra static member `@Configuration`, nested imports và các configuration được import tiếp.
5. **Condition nào được đánh giá?** Đọc `@Conditional`, `@Profile`, `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`.
6. **Bean definition nào được đăng ký?** Tìm method `@Bean`, component hoặc registrar đã tạo definition.
7. **Bean có thực sự được khởi tạo không?** Kiểm tra dependency graph, scope, lazy initialization và lỗi khi tạo bean.

Không nên nhảy từ bước 1 đến bước 7. Nếu một bean không tồn tại, nguyên nhân có thể nằm ở bước chọn configuration hoặc condition chứ chưa hề đến constructor.

### Bản đồ luồng

~~~text
Configuration gốc
   |
   +-- @Import(Class)
   |       |
   |       +-- parse class được import
   |               |
   |               +-- @Import tiếp / nested @Configuration
   |
   +-- @Import(ImportSelector)
   |       |
   |       +-- selectImports(metadata)
   |               |
   |               +-- parse các class name được trả về
   |
   +-- @Import(DeferredImportSelector)
   |       |
   |       +-- xử lý sau configuration thông thường
   |
   +-- điều kiện class / nested branch
           |
           +-- condition không khớp --> bỏ qua nhánh
           |
           +-- condition khớp
                   |
                   +-- đọc @Bean methods / registrar
                           |
                           +-- đăng ký BeanDefinition
                                   |
                                   +-- dependency injection
                                           |
                                           +-- tạo instance
~~~

Sơ đồ thể hiện các bước logic, không phải mọi nhánh đều đi qua tất cả node.

## 5. Điểm đọc source code Spring Framework và Spring Boot

Khi muốn hiểu hành vi thực tế thay vì chỉ đọc annotation, hãy mở đúng lớp triển khai theo thứ tự.

### 5.1. Spring Framework 6.1: parse configuration

| Lớp / phương thức | Câu hỏi cần trả lời |
| --- | --- |
| `ConfigurationClassPostProcessor#processConfigBeanDefinitions` | Ai khởi chạy quá trình xử lý configuration bean definitions? |
| `ConfigurationClassParser#parse` | Các cấu hình gốc được parse như thế nào? |
| `ConfigurationClassParser#processConfigurationClass` | Một configuration class được kiểm tra và xử lý ra sao? |
| `ConfigurationClassParser#doProcessConfigurationClass` | Các annotation, imports và member classes được duyệt ở đâu? |
| `ConfigurationClassParser#processImports` | Import class, selector và registrar được phân nhánh thế nào? |
| `ConfigurationClassParser#processMemberClasses` | Nested configuration classes được phát hiện ra sao? |
| `ConditionEvaluator#shouldSkip` | Condition được đánh giá ở phase nào và khi nào class bị bỏ qua? |
| `ConfigurationClassBeanDefinitionReader#loadBeanDefinitions` | Các configuration class đã parse được chuyển thành bean definitions ra sao? |

Tên method có thể thay đổi giữa các phiên bản Framework; khi đọc mã, hãy mở tag/version đúng với dependency của dự án. Các tên trên là điểm bắt đầu tiêu biểu cho Spring Framework 6.1.

### 5.2. Spring Boot 3.3: auto-configuration import

| Lớp / thành phần | Vai trò |
| --- | --- |
| `@EnableAutoConfiguration` | Bật cơ chế auto-configuration trong ứng dụng |
| `AutoConfigurationImportSelector` | Deferred selector đưa các auto-configuration candidates vào quá trình parse |
| `AutoConfigurationImportSelector#getAutoConfigurationEntry` | Lấy candidates, exclusions và kết quả lọc |
| `AutoConfiguration.imports` | Resource liệt kê các auto-configuration class của thư viện |
| `@AutoConfiguration` | Đánh dấu một lớp auto-configuration và khai báo quan hệ thứ tự |
| `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean` | Lọc class/bean theo điều kiện |

Khi truy vết một auto-configuration của Boot, cần phân biệt:
- **Danh sách candidate:** class có được liệt kê trong resource không?
- **Danh sách đã chọn:** class có bị exclude/filter không?
- **Configuration parsing:** class được parse nhưng có condition nào skip không?
- **Bean registration:** class được xử lý nhưng bean method có condition riêng nào không?
- **Bean creation:** definition tồn tại nhưng instance có tạo thành công không?

Đây là năm trạng thái khác nhau. Chỉ nhìn file `AutoConfiguration.imports` không đủ để kết luận bean sẽ tồn tại.

## 6. Ví dụ kiểm chứng: @Import các nested branch theo property

Ví dụ test hoàn chỉnh dưới đây import hai nested configuration class. Mỗi nhánh được bảo vệ bằng `@ConditionalOnProperty`. Khi chọn HTTP, chỉ bean HTTP được đăng ký; khi chọn queue, chỉ bean queue; khi giá trị khác, không có nhánh nào được chọn.

**Tệp:** `src/test/java/example/trace/ImportBranchSelectionTest.java`

~~~java
package example.trace;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

class ImportBranchSelectionTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TransportConfiguration.class);

    @Test
    void selectsHttpBranch() {
        runner.withPropertyValues("demo.transport.mode=http")
                .run(context -> {
                    assertThat(context).hasSingleBean(TransportClient.class);
                    assertThat(context.getBean(TransportClient.class).mode())
                            .isEqualTo("http");
                    assertThat(context.containsBean("httpTransportClient")).isTrue();
                    assertThat(context.containsBean("queueTransportClient")).isFalse();
                });
    }

    @Test
    void selectsQueueBranch() {
        runner.withPropertyValues("demo.transport.mode=queue")
                .run(context -> {
                    assertThat(context).hasSingleBean(TransportClient.class);
                    assertThat(context.getBean(TransportClient.class).mode())
                            .isEqualTo("queue");
                    assertThat(context.containsBean("httpTransportClient")).isFalse();
                    assertThat(context.containsBean("queueTransportClient")).isTrue();
                });
    }

    @Test
    void selectsNoBranchForUnsupportedMode() {
        runner.withPropertyValues("demo.transport.mode=other")
                .run(context ->
                        assertThat(context).doesNotHaveBean(TransportClient.class));
    }

    @Test
    void selectsNoBranchWhenPropertyIsMissing() {
        runner.run(context ->
                assertThat(context).doesNotHaveBean(TransportClient.class));
    }

    interface TransportClient {
        String mode();
    }

    static class TransportBranches {

        @Configuration(proxyBeanMethods = false)
        @ConditionalOnProperty(
                prefix = "demo.transport",
                name = "mode",
                havingValue = "http")
        static class HttpConfiguration {

            @Bean
            TransportClient httpTransportClient() {
                return () -> "http";
            }
        }

        @Configuration(proxyBeanMethods = false)
        @ConditionalOnProperty(
                prefix = "demo.transport",
                name = "mode",
                havingValue = "queue")
        static class QueueConfiguration {

            @Bean
            TransportClient queueTransportClient() {
                return () -> "queue";
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import({
        TransportBranches.HttpConfiguration.class,
        TransportBranches.QueueConfiguration.class
    })
    static class TransportConfiguration {
    }
}
~~~

### Đọc kết quả test

- `withUserConfiguration(TransportConfiguration.class)` đưa cấu hình gốc vào context.
- `@Import` đưa cả hai nested configuration class vào quá trình parse.
- Condition trên `HttpConfiguration` và `QueueConfiguration` được đánh giá riêng.
- Chỉ configuration khớp mới đăng ký bean method của nó.
- Nếu không có property hoặc giá trị không nằm trong hai lựa chọn, cả hai nhánh đều bị bỏ qua; context vẫn có thể khởi động vì không có bean bắt buộc nào được inject.

**Điều kiện chạy:** Java 17+, Spring Boot 3.3.x, dependency test `spring-boot-starter-test` và Gradle project đã quản lý version bằng Spring Boot plugin/BOM.

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chạy tại module chứa test:

~~~bash
# Linux/macOS
./gradlew test --tests "example.trace.ImportBranchSelectionTest"

# Windows
gradlew.bat test --tests "example.trace.ImportBranchSelectionTest"
~~~

**Kết quả kỳ vọng:** bốn test PASS. Test kiểm chứng bằng AssertJ, không có `System.out.println`, nên không có stdout nội dung cố định. Output Gradle phụ thuộc test logging. Mã test được trình bày để chạy trong dự án tương ứng; cần thực thi lệnh trên dependency graph thực tế để xác nhận build.

## 7. Ví dụ kiểm chứng ImportSelector theo Environment

Khi danh sách import phải được lựa chọn động, có thể dùng `ImportSelector`. Ví dụ dưới đây dùng `EnvironmentAware` để đọc mode và trả về tên configuration class tương ứng.

~~~java
public class ModeImportSelector
        implements ImportSelector, EnvironmentAware {

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public String[] selectImports(AnnotationMetadata importingClassMetadata) {
        String mode = environment.getProperty("demo.transport.mode", "none");

        return switch (mode) {
            case "http" -> new String[] {
                HttpTransportConfiguration.class.getName()
            };
            case "queue" -> new String[] {
                QueueTransportConfiguration.class.getName()
            };
            default -> new String[0];
        };
    }
}
~~~

Đây là đoạn minh họa; cần import `ImportSelector`, `EnvironmentAware`, `Environment`, `AnnotationMetadata` và các configuration class. Selector được gắn vào class gốc:

~~~java
@Configuration(proxyBeanMethods = false)
@Import(ModeImportSelector.class)
class SelectedTransportConfiguration {
}
~~~

Khác với cách import hai class rồi để condition quyết định:
- `ImportSelector` chỉ trả về nhánh đã chọn.
- Condition trên nested configuration vẫn có thể được dùng như lớp bảo vệ bổ sung.
- Selector không tự tạo bean; các class được trả về tiếp tục được Spring parse như cấu hình.

### Khi nào selector nên đọc annotation metadata?

Nếu lựa chọn phụ thuộc vào một annotation do thư viện định nghĩa, hãy đọc metadata của class đang import thay vì buộc selector phụ thuộc trực tiếp vào property global. Ví dụ một annotation `@EnableTransport(mode = "http")` có thể meta-annotate với `@Import(ModeImportSelector.class)`; selector đọc thuộc tính `mode` từ `AnnotationMetadata`.

Đây là hướng phù hợp cho một API kiểu `@Enable...` do thư viện cung cấp. Nếu chỉ cần chọn theo property của Spring Boot, một vài nested config với `@ConditionalOnProperty` có thể dễ hiểu hơn selector tự viết.

## 8. Import lồng nhiều cấp và cách lần theo đệ quy

Một import có thể dẫn tới class cấu hình khác, rồi class đó lại import thêm:

~~~text
RootConfiguration
    |
    +-- @Import(FeatureConfiguration)
                |
                +-- @Import(TransportConfiguration)
                |           |
                |           +-- @Import(HttpConfiguration)
                |
                +-- @Import(RetryConfiguration)
~~~

Khi đọc source, đừng dừng lại sau lần import đầu tiên. Với mỗi class được import, tiếp tục kiểm tra:
- `@Import` trên chính class đó.
- Các nested `@Configuration` class.
- `ImportSelector` và `DeferredImportSelector`.
- Condition ở cấp class và bean method.
- `@Bean` method phụ thuộc bean nào.

Spring quản lý configuration class đã được parse để tránh xử lý lặp vô hạn khi có quan hệ import vòng hoặc cùng class được import từ nhiều đường. Tuy vậy, một thiết kế có import cycle khó đọc và nên được đơn giản hóa nếu không có lý do rõ ràng.

### Import cycle không phải cách tổ chức module

Nếu `A` import `B` và `B` import `A`, đừng dựa vào cơ chế deduplicate để coi đây là thiết kế tốt. Quan hệ phụ thuộc hai chiều làm khó xác định trách nhiệm và khiến condition/ordering khó suy luận. Hãy tìm một configuration composition class làm điểm kết nối hoặc tách API chung ra module riêng.

## 9. Phân biệt import, component scan và auto-configuration imports

| Cơ chế | Cách tìm class | Khi nên dùng |
| --- | --- | --- |
| `@Import(Config.class)` | Chỉ định class tường minh | Composition cố định, dễ truy vết |
| `@Import(ImportSelector.class)` | Selector trả về class name | Danh sách cấu hình động |
| `@ComponentScan` | Quét package và subpackage | Tìm component theo package boundary |
| `AutoConfiguration.imports` | Spring Boot đọc danh sách auto-configuration của thư viện | Công bố auto-configuration từ starter |
| `@ImportResource` | Nạp bean definitions từ resource, ví dụ XML | Tích hợp cấu hình XML hiện có |

Không nên dùng component scan rộng chỉ để tìm auto-configuration. Với thư viện Spring Boot, công bố class qua `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` để Boot quản lý candidate list và exclusions.

Cũng không nhầm file `AutoConfiguration.imports` với `@Import` trong source code. Boot sử dụng `AutoConfigurationImportSelector` (một deferred selector) để đọc danh sách đó, áp dụng lọc và sắp xếp, rồi đưa các class được chọn vào configuration parser.

## 10. Condition được áp dụng ở những lớp nào?

Các condition có thể xuất hiện ở nhiều tầng:

| Vị trí | Ví dụ | Phạm vi ảnh hưởng |
| --- | --- | --- |
| Configuration gốc | `@ConditionalOnProperty` trên root config | Cả nhánh cấu hình gốc và nội dung được xử lý bên trong |
| Nested configuration | `@ConditionalOnClass` trên optional branch | Toàn bộ bean method trong nhánh |
| Bean method | `@ConditionalOnMissingBean` trên một `@Bean` | Riêng bean được method khai báo |
| Profile | `@Profile("dev")` | Class/bean mang profile đó |
| Selector | `selectImports(...)` trả về tập class khác nhau | Tập configuration được đưa vào parse |

Điều kiện class-level giúp loại bỏ cả một nhánh trước khi xử lý bean methods. Điều kiện method-level chỉ ảnh hưởng bean method tương ứng; các bean method khác trong cùng configuration vẫn có thể được đăng ký.

Khi parent config bị bỏ qua vì condition không khớp, các nested config nằm trong nhánh đó không được xử lý qua parent. Khi một nested config được import riêng từ đường khác, nó có thể được xét theo đường import riêng đó. Vì vậy, khi đọc mã có nhiều đường import, cần truy vết **tất cả đường đi** đến cùng một class trước khi kết luận condition của parent có loại bỏ class đó hay không.

## 11. Đăng ký bean definition khác với khởi tạo bean

Một lỗi phân tích phổ biến là nhìn thấy `@Bean` trong source rồi kết luận bean chắc chắn đã được tạo. Cần phân biệt:

1. Configuration class được tìm thấy.
2. Configuration class vượt qua condition.
3. Bean method được đọc và một `BeanDefinition` được đăng ký.
4. Bean được yêu cầu bởi context hoặc dependency graph.
5. Instance được tạo, inject dependencies và initialize thành công.

Ví dụ bean có `@Lazy` có thể có definition nhưng chưa được khởi tạo cho đến khi được yêu cầu. Bean theo scope prototype cũng không được tạo theo cùng cách singleton eager. Một bean có thể được đăng ký nhưng lỗi constructor hoặc dependency khiến việc khởi tạo thất bại.

`@Import` điều khiển việc đưa class cấu hình vào quá trình xử lý; nó **không phải lệnh gọi constructor của tất cả bean ngay lập tức**.

## 12. Cách debug trong dự án thật

### 12.1. Bật Condition Evaluation Report

Khởi động ứng dụng với:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot sẽ in Condition Evaluation Report. Hãy tìm tên auto-configuration hoặc condition liên quan, rồi đối chiếu với:
- Class có nằm trong candidate list không?
- Class có bị exclude không?
- `OnClassCondition`, `OnPropertyCondition`, `OnBeanCondition` khớp hay không?
- Bean method có điều kiện riêng nào không?

Report hữu ích cho condition của Spring Boot; nó không thay thế việc đọc đường `@Import` và selector trong source.

### 12.2. Dùng breakpoint theo thứ tự

Khi cần debug sâu trong IDE, có thể đặt breakpoint tại:
- `ConfigurationClassParser#processImports`: xem class nào đang import class nào.
- `ConfigurationClassParser#processMemberClasses`: xem nested configuration nào được phát hiện.
- `ConditionEvaluator#shouldSkip`: xem class hoặc method bị skip do condition.
- `ConfigurationClassBeanDefinitionReader#loadBeanDefinitionsForBeanMethod`: xem bean method nào tạo definition.

Các method nội bộ có thể thay đổi theo version; hãy checkout source tương ứng dependency thực tế. Khi không muốn debug framework, dùng log condition và test context nhỏ thường đủ để thu hẹp vấn đề.

### 12.3. Lập bảng trace cho từng bean

Khi review một bean, ghi lại một dòng cho mỗi lớp:

| Tầng | Thông tin cần ghi |
| --- | --- |
| Entry | Configuration gốc và cơ chế đăng ký |
| Import | Class trực tiếp / selector / deferred selector / registrar |
| Branch | Nested config hoặc class được selector trả về |
| Condition | Condition class-level và method-level, kết quả mong đợi |
| Definition | Tên bean, kiểu, factory method |
| Dependency | Constructor/method dependencies |
| Creation | Eager/lazy, scope, lỗi khởi tạo nếu có |

Bảng này giúp phân biệt “không được import”, “bị condition skip”, “không đăng ký bean definition” và “đã đăng ký nhưng tạo instance thất bại”.

## 13. Những lỗi thường gặp khi truy vết

1. **Chỉ tìm method `@Bean` mà không tìm configuration chứa nó.** Hãy truy ngược cách class được đăng ký.
2. **Nghĩ rằng `@Import` luôn tạo bean ngay.** Nó đưa class vào quá trình parse; condition và bean lifecycle vẫn tiếp tục.
3. **Bỏ qua selector.** Nếu `@Import` trỏ tới `ImportSelector`, phải đọc `selectImports` và các metadata/environment mà nó sử dụng.
4. **Không phân biệt `ImportSelector` với `DeferredImportSelector`.** Selector deferred được xử lý sau các cấu hình thông thường; đây là nền tảng quan trọng của auto-configuration Boot.
5. **Bỏ qua nested config.** Một class static member có `@Configuration` có thể được phát hiện trong lúc parse class cha dù không có trong imports array.
6. **Cho rằng condition trên bean method bảo vệ kiểu optional ở chữ ký.** Khi kiểu có thể thiếu, đặt classpath condition trên configuration riêng để class chứa chữ ký đó có thể bị bỏ qua.
7. **Nhầm condition class-level với method-level.** Một class bị skip thì các bean method của nhánh đó không được đăng ký; một method bị skip không tự loại các method khác.
8. **Nhầm AutoConfiguration.imports với component scan.** Đây là hai cơ chế khám phá class khác nhau.
9. **Nhầm registration order với instantiation order.** Thứ tự parse/đăng ký bean definition không đồng nghĩa thứ tự constructor chạy.
10. **Chỉ test nhánh thành công.** Hãy test cả property thiếu, giá trị không hỗ trợ, nhánh khác và trường hợp bean bị override.
11. **Không xét import từ nhiều đường.** Một nested class có thể được import trực tiếp ở nơi khác dù parent branch ban đầu không được chọn.
12. **Đọc source version khác với dependency.** Framework internals thay đổi; cần khớp version của source jar/tag.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Một class gốc có `@Import(ModeSelector.class)`. Cần đọc file nào để biết nhánh nào được chọn?

**Đáp án:** Đọc implementation `ModeSelector#selectImports`, các metadata/Environment mà nó sử dụng và các class name được trả về.

**Câu 2.** Hai nested `@Configuration` được import cùng lúc, mỗi lớp có `@ConditionalOnProperty` khác nhau. Cả hai có nhất thiết đăng ký bean không?

**Đáp án:** Không. Mỗi class condition được đánh giá riêng; chỉ nhánh có điều kiện khớp mới được xử lý.

**Câu 3.** Vì sao Spring Boot dùng `DeferredImportSelector` cho auto-configuration?

**Đáp án:** Để xử lý auto-configuration sau các cấu hình thông thường, cho phép cơ chế lựa chọn/điều kiện auto-configuration hoạt động theo thứ tự Boot thiết kế.

**Câu 4.** `@Import(Config.class)` có đồng nghĩa tất cả bean trong `Config` đã khởi tạo xong không?

**Đáp án:** Không. Import đưa cấu hình vào quá trình parse; sau đó condition quyết định definition nào được đăng ký, và container mới tạo bean theo lifecycle/dependency.

**Câu 5.** Khi một bean không xuất hiện, nên kiểm tra theo thứ tự nào?

**Đáp án:** Điểm vào → import/selector → nested branch → condition → bean definition → bean creation.

## 15. Ghi nhớ khi đọc mã auto-configuration

Để truy vết chính xác, hãy lần theo đường đi từ class gốc:

- Xác định **entry point** và cách configuration được đăng ký.
- Theo từng `@Import`, đọc selector/registrar nếu có.
- Kiểm tra nested configuration class và condition ở từng nhánh.
- Phân biệt class được chọn với class vượt qua condition.
- Xác nhận bean definition được đăng ký trước khi điều tra khởi tạo bean.
- Dùng `ApplicationContextRunner` để tái hiện từng nhánh bằng test nhỏ.

Khi đọc code, một nhánh không xuất hiện có thể đã bị loại từ lúc chọn import, lúc kiểm tra condition hoặc lúc đăng ký bean method. Xác định đúng giai đoạn sẽ giúp sửa đúng nguyên nhân và tránh thêm `@Import` hoặc đổi condition một cách cảm tính.

### Tài liệu tham khảo chính thức

- [Spring Framework 6.1 — Java-based Container Configuration and @Import](https://docs.spring.io/spring-framework/reference/6.1/core/beans/java/composing-configuration-classes.html)
- [Spring Framework 6.1 — @Import Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Import.html)
- [Spring Framework 6.1 — ImportSelector Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ImportSelector.html)
- [Spring Framework 6.1 — DeferredImportSelector Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
