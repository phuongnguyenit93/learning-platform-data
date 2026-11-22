# Áp dụng nhiều customizer theo thứ tự xác định

## 1. Customizer là điểm mở rộng gì?

Trong Spring Boot Auto Configuration, một *customizer* thường là một bean chứa thao tác tùy biến đối tượng đang được framework hoặc một auto-configuration xây dựng. Thay vì mỗi module tự tạo lại toàn bộ đối tượng, module có thể đăng ký một bean thực thi giao diện callback, còn **bên sở hữu đối tượng đích** sẽ tập hợp và gọi các callback đó.

Ví dụ thực tế của Spring Boot 3.3:

- `WebServerFactoryCustomizer<T>` tùy biến web server factory trước khi web server được khởi động.
- `Jackson2ObjectMapperBuilderCustomizer` tùy biến `Jackson2ObjectMapperBuilder`, giữ lại phần lớn cơ chế tự động cấu hình Jackson của Boot.
- Các thư viện nội bộ có thể tự định nghĩa `PaymentClientCustomizer`, `PipelineCustomizer` hoặc một interface tương tự, rồi áp dụng danh sách bean mở rộng lúc tạo đối tượng chính.

Khi **nhiều customizer** cùng tác động lên một đối tượng, thứ tự có thể ảnh hưởng trực tiếp đến kết quả: customizer A đặt timeout, B ghi đè timeout; customizer X đăng ký bước xử lý, Y cần bước đó tồn tại. Vì vậy cần xác định: **ai thu thập các customizer, ai quyết định thứ tự, callback chạy lúc nào, và cách xử lý xung đột**.

Mục tiêu của bài:

1. Hiểu `@Order`, `Ordered` và cách Spring sắp xếp nhiều bean theo thứ tự xác định.
2. Biết thu thập và áp dụng qua `ObjectProvider<T>.orderedStream()` hoặc danh sách bean được Spring inject.
3. Phân biệt **thứ tự áp dụng customizer** với **thứ tự đăng ký auto-configuration** và **thứ tự khởi tạo bean**.
4. Thiết kế extension point có hợp đồng rõ ràng, tránh phụ thuộc vào thứ tự quét lớp hoặc trùng priority.
5. Kiểm chứng bằng chương trình test độc lập với Java 17+, Spring Boot 3.3 và `ApplicationContextRunner`.

## 2. Vì sao thứ tự tạo ra kết quả khác nhau?

Giả sử có đối tượng builder chứa cấu hình:

```text
mode = "standard"
interceptors = []
```

Ba customizer cùng làm việc trên builder:

| Customizer | Hành động | Ý định |
| --- | --- | --- |
| `DefaultModeCustomizer` | `mode = "basic"` | Đặt mặc định |
| `AddAuditCustomizer` | Thêm `"audit"` vào interceptors | Đăng ký chức năng bổ sung |
| `OverrideModeCustomizer` | `mode = "strict"` | Ghi đè cấu hình cuối |

Nếu chạy `DefaultModeCustomizer` trước `OverrideModeCustomizer`, kết quả cuối của `mode` là `strict`. Nếu đổi ngược, `mode` lại thành `basic`. Với các phép thêm vào danh sách, thứ tự phần tử cũng là một phần của hành vi quan sát được. **Không có một quy tắc chung kiểu “customizer cuối luôn đúng”**: cái sau có thể ghi đè property, hoặc chỉ bổ sung dữ liệu, hoặc báo lỗi do invariant bị phá vỡ. Kết quả phụ thuộc hợp đồng của đối tượng đích và cách từng callback thay đổi nó.

Từ đó suy ra hai trách nhiệm tách biệt:

- **Tác giả customizer** gán priority phù hợp và viết callback chỉ làm việc thuộc phạm vi mình sở hữu.
- **Bên tiêu thụ customizer** phải lấy đúng các bean, sắp thứ tự theo hợp đồng đã chọn và gọi tuần tự trên đúng đối tượng đích.

Chỉ đánh dấu `@Order` mà bên tiêu thụ không sắp xếp danh sách hoặc không gọi callback thì **chưa tạo ra bất kỳ trình tự áp dụng nào**.

## 3. Các cơ chế ordering của Spring

### 3.1. `@Order`: số nhỏ được ưu tiên chạy trước

Spring Framework cung cấp `org.springframework.core.annotation.Order`:

```java
@Bean
@Order(10)
PipelineCustomizer normalizeCustomizer() {
    return draft -> draft.addStep("normalize");
}

@Bean
@Order(30)
PipelineCustomizer auditCustomizer() {
    return draft -> draft.addStep("audit");
}
```

Đây là **mảnh mã** đặt trong một lớp `@Configuration`, giả định `PipelineCustomizer` là functional interface và `draft` có method `addStep`. Khi được tập hợp bằng một cơ chế **có tôn trọng thứ tự**, bean order `10` được áp dụng trước bean order `30`. Nguyên tắc chung là **giá trị số càng thấp, ưu tiên càng cao**.

Giá trị order có thể âm, bằng 0 hoặc dương. Spring có các hằng `Ordered.HIGHEST_PRECEDENCE` và `Ordered.LOWEST_PRECEDENCE`. Không nên tự ý gán cực trị cho mọi customizer: như vậy sẽ khiến quy tắc giữa module khó phối hợp. Dành các dải giá trị được công bố rõ cho từng giai đoạn, chẳng hạn `0–99` cho mặc định, `100–199` cho biến đổi nghiệp vụ, `200–299` cho kiểm tra cuối, nếu extension point do bạn sở hữu có nhu cầu như vậy. Đây là **quy ước thiết kế**, không phải quy định của Spring.

Có thể gắn `@Order` lên **lớp component** hoặc **phương thức `@Bean`**. `@Order` trên phương thức `@Bean` hữu ích khi cùng một class implementation tạo ra nhiều bean nhưng mỗi bean cần priority riêng.

### 3.2. `Ordered`: giá trị order lấy từ instance

Thay vì annotation, class có thể triển khai `org.springframework.core.Ordered`:

```java
final class OrderedAuditCustomizer implements PipelineCustomizer, Ordered {

    @Override
    public int getOrder() {
        return 30;
    }

    @Override
    public void customize(PipelineDraft draft) {
        draft.addStep("audit");
    }
}
```

Mã này minh họa **một class phụ thuộc các kiểu `PipelineCustomizer` và `PipelineDraft` của ứng dụng**; cần import `org.springframework.core.Ordered` trong tệp thật. Cách này có thể phù hợp nếu priority là một phần của implementation hoặc cần xác định theo tham số cấu hình lúc khởi tạo. Vì Spring so sánh được instance đã được tạo, việc thu thập và sắp thứ tự có thể **khởi tạo các customizer**; không nên giả định đây chỉ là thao tác trên metadata.

Nếu một bean đồng thời có `Ordered` và `@Order`, hãy xác định rõ nguồn order mà comparator sử dụng và tránh khai báo hai giá trị mâu thuẫn. Với một extension point do bạn viết, thường nên chọn **một cách khai báo ưu tiên thống nhất** cho mỗi implementation.

### 3.3. `PriorityOrdered`: nhóm ưu tiên đặc biệt

`PriorityOrdered` kế thừa `Ordered` và được Spring xử lý như một **nhóm ưu tiên trước** nhóm chỉ triển khai `Ordered`. Vì vậy không thể chỉ lấy mọi số `getOrder()` rồi coi toàn bộ danh sách là một phép so sánh số đơn giản khi trộn `PriorityOrdered` với `Ordered`. Đây thường là hợp đồng dùng cho hạ tầng framework như các post-processor. Với customizer ứng dụng thông thường, `@Order` hoặc `Ordered` là đủ, đơn giản hơn.

### 3.4. Không khai báo order và trường hợp bằng nhau

Customizer không chỉ định priority thường được xem là có mức ưu tiên thấp theo quy tắc của comparator. **Không dựa vào thứ tự quét component, tên file, tên bean hay thứ tự khai báo method để điều khiển callback.**

Nếu hai customizer cùng priority, không nên xem thứ tự tương đối là một hợp đồng ổn định giữa các bản Spring, profile hoặc cách import. Khi thứ tự giữa chúng làm thay đổi kết quả, hãy **gán giá trị khác nhau**, hoặc gộp những thao tác phụ thuộc chặt chẽ vào một customizer. Cũng có thể xây dựng một thứ tự phụ rõ ràng trong extension point của riêng mình, nhưng cần công bố và kiểm thử hợp đồng đó.

## 4. Thu thập và áp dụng đúng thứ tự

### 4.1. Khuyến nghị cho auto-configuration: `ObjectProvider<T>.orderedStream()`

`ObjectProvider<T>` cho phép lấy các bean cùng loại theo nhu cầu. Phương thức:

```java
customizers.orderedStream()
    .forEach(customizer -> customizer.customize(builder));
```

trả về **sequential Stream đã sắp xếp** theo order comparator chung của BeanFactory. Trong Spring application context thông thường, comparator này xét `Ordered` và `@Order`. `forEach` tuần tự trên stream đó gọi từng customizer theo thứ tự đã được sắp. Mỗi callback nhận **cùng một builder** để thay đổi trạng thái trước khi builder tạo ra đối tượng cuối cùng.

So sánh ba cách:

| Cách thu thập | Có đảm bảo ưu tiên `@Order`/`Ordered` không? | Ghi chú |
| --- | --- | --- |
| `ObjectProvider<T>.orderedStream()` | **Có, theo order comparator của factory** | Rõ ý đồ nhất cho một danh sách customizer tùy chọn |
| Inject `List<T>` hoặc `T[]` qua Spring | **Có, trong autowiring collection tiêu chuẩn** | Spring sắp xếp matching beans theo order metadata |
| `ObjectProvider<T>.stream()` / `iterator()` | **Không cam kết thứ tự ưu tiên** | Thường gần registration order, nhưng không là hợp đồng ứng dụng |
| Tự gọi `getBeansOfType()` rồi duyệt `Map.values()` | **Không tự cam kết thứ tự `@Order`** | Nếu dùng map, phải sắp xếp đúng cách trước khi gọi callback |

Đối với danh sách inject qua Spring, có thể viết:

```java
@Bean
Pipeline pipeline(List<PipelineCustomizer> customizers) {
    PipelineDraft draft = new PipelineDraft();
    customizers.forEach(customizer -> customizer.customize(draft));
    return draft.build();
}
```

Đây là **mảnh mã** sử dụng các class ứng dụng. Spring sắp các bean matching type theo ordering metadata khi autowire list. Dùng `ObjectProvider<PipelineCustomizer>` thường thuận tiện trong auto-configuration vì thể hiện rõ việc **có thể không có customizer nào**, đồng thời trì hoãn việc resolve tới thời điểm thực sự cần.

### 4.2. Thời điểm apply do bên tiêu thụ quy định

Có hai lúc khác nhau:

1. Khi Spring đăng ký **bean definition** của các customizer.
2. Khi code gọi `customize(target)` trên **bean instance** đã được resolve.

`@Order` quyết định vị trí tương đối trong tập hợp được Spring sắp xếp; nó **không tự kích hoạt callback** lúc đăng ký definition. Nếu customizer là bean thông thường, constructor của nó có thể chạy trước hoặc sau một customizer khác theo dependency graph, nhưng callback chỉ chạy khi người tiêu thụ gọi.

Ví dụ cần phân biệt:

- `@AutoConfiguration(after = OtherAutoConfiguration.class)`: tác động **thứ tự xử lý auto-configuration/bean definitions**, nhất là khi các `@ConditionalOnBean`, `@ConditionalOnMissingBean` quan tâm definition đã có hay chưa.
- `@DependsOn("otherCustomizer")`: tác động **thứ tự khởi tạo bean instances** theo dependency, không tự sắp thứ tự chạy `customize()`.
- `@Order(10)` trên customizer: mô tả **thứ tự ưu tiên khi component được sắp**; bên tiêu thụ phải tôn trọng thứ tự ấy.
- `@Primary`: chọn một bean ưu tiên khi injection kiểu đơn lẻ có nhiều ứng viên; **không** phải cách bỏ customizer khác khỏi danh sách `ObjectProvider<T>`.

Nhớ rằng `@Order` trên **class `@Configuration`** chỉ có ý nghĩa trong việc đánh giá lớp configuration; nó **không tự truyền** giá trị order xuống tất cả method `@Bean` nằm trong class ấy. Muốn mỗi customizer do `@Bean` tạo có thứ tự, đặt `@Order` trên chính method hoặc implementation, hay dùng `Ordered`.

## 5. Hợp đồng extension point khi có nhiều customizer

Giả sử bạn sở hữu `PipelineCustomizer` trong một starter nội bộ. Hợp đồng nên trả lời rõ:

1. **Đối tượng đích:** callback thay đổi builder/configuration trước khi `build()` hay có thể thay đổi đối tượng đang chạy? Khuyến nghị áp dụng trước khi tạo/freeze đối tượng chính.
2. **Dạng thay đổi:** setter kiểu “lần cuối thắng”, bổ sung vào collection, hay validation chỉ đọc? Đừng trộn các hành vi này mà không định nghĩa ưu tiên.
3. **Thứ tự:** có support `@Order`, `Ordered`, hay order cố định khác? Priority mặc định ra sao? Hai customizer bằng thứ tự có quan trọng không?
4. **Nguồn bean:** lấy toàn bộ bean matching type, hay lọc bằng qualifier/`@ConditionalOnProperty`? Bean của module chưa được import sẽ không xuất hiện trong danh sách.
5. **Lúc gọi:** apply một lần khi xây dựng singleton, mỗi request, hay mỗi lần tạo prototype? Tránh hiểu nhầm “bean đã tạo” là “callback đã chạy”.
6. **Xử lý lỗi:** callback throw exception thì fail-fast khi startup hay bỏ qua? Với cấu hình hạ tầng quan trọng, fail-fast kèm thông điệp rõ thường dễ kiểm soát hơn silently ignore.
7. **Bất biến:** sau tất cả customizer cần kiểm tra giá trị bắt buộc, cấu hình trùng lặp, số lần đăng ký interceptor hoặc giới hạn hiệu năng.
8. **Tính lặp:** nếu mục tiêu có thể được tùy biến nhiều lần, callback có an toàn khi gọi lại không? Tránh thêm cùng một interceptor nhiều lần mà không có idempotency.

Bộ quy tắc này giúp mở rộng mà không bắt người dùng thay toàn bộ auto-configuration hoặc phụ thuộc vào bean name nội bộ. Đối với cùng một property có nhiều customizer, có thể công bố thứ tự “mặc định trước, tinh chỉnh sau, validate cuối”. Nếu một hành vi cần chắc chắn **không ai được ghi đè về sau**, đừng coi `@Order` là cơ chế an toàn tuyệt đối: cần kiểm tra invariant khi hoàn tất, hoặc thiết kế API builder hạn chế việc thay đổi trái phép.

## 6. Ví dụ Java 17+ đầy đủ, dùng Spring Boot 3.3

Bài test sau mô phỏng một auto-configuration cung cấp `Pipeline` mặc định. Người dùng đăng ký ba customizer với các order `30`, `10` và `20` **không theo thứ tự tăng** trong source code. Auto-configuration lấy tất cả customizer qua `ObjectProvider.orderedStream()` và áp dụng lên một `PipelineDraft` trước khi tạo `Pipeline`.

Tạo tệp `src/test/java/example/customizers/OrderedCustomizerTests.java` trong dự án có Java 17+, Spring Boot 3.3.x, dependency `spring-boot-starter-test` (JUnit Jupiter, AssertJ) và JUnit Platform:

```java
package example.customizers;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

import static org.assertj.core.api.Assertions.assertThat;

class OrderedCustomizerTests {

    @FunctionalInterface
    interface PipelineCustomizer {
        void customize(PipelineDraft draft);
    }

    static final class PipelineDraft {
        private final List<String> stages = new ArrayList<>();
        private String mode = "standard";

        void addStage(String name) {
            stages.add(name);
        }

        void setMode(String mode) {
            this.mode = mode;
        }

        Pipeline build() {
            return new Pipeline(List.copyOf(stages), mode);
        }
    }

    static final class Pipeline {
        private final List<String> stages;
        private final String mode;

        Pipeline(List<String> stages, String mode) {
            this.stages = stages;
            this.mode = mode;
        }

        List<String> stages() {
            return stages;
        }

        String mode() {
            return mode;
        }
    }

    @AutoConfiguration
    static class PipelineAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(Pipeline.class)
        Pipeline pipeline(ObjectProvider<PipelineCustomizer> customizers) {
            PipelineDraft draft = new PipelineDraft();
            customizers.orderedStream()
                    .forEach(customizer -> customizer.customize(draft));
            return draft.build();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomizersConfiguration {

        @Bean
        @Order(30)
        PipelineCustomizer finalCustomizer() {
            return draft -> {
                draft.addStage("final");
                draft.setMode("fast");
            };
        }

        @Bean
        @Order(10)
        PipelineCustomizer baseCustomizer() {
            return draft -> {
                draft.addStage("base");
                draft.setMode("base");
            };
        }

        @Bean
        @Order(20)
        PipelineCustomizer validateCustomizer() {
            return draft -> draft.addStage("validate");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserPipelineConfiguration {
        @Bean
        Pipeline pipeline() {
            return new Pipeline(List.of("user"), "custom");
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            PipelineAutoConfiguration.class));

    @Test
    void appliesAllCustomizersInOrder() {
        runner.withUserConfiguration(CustomizersConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Pipeline.class);
                    Pipeline pipeline = context.getBean(Pipeline.class);
                    assertThat(pipeline.stages())
                            .containsExactly("base", "validate", "final");
                    assertThat(pipeline.mode()).isEqualTo("fast");
                });
    }

    @Test
    void noCustomizersKeepsDefaultValues() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(Pipeline.class);
            Pipeline pipeline = context.getBean(Pipeline.class);
            assertThat(pipeline.stages()).isEmpty();
            assertThat(pipeline.mode()).isEqualTo("standard");
        });
    }

    @Test
    void userPipelineMakesDefaultAutoConfigurationBackOff() {
        runner.withUserConfiguration(
                    UserPipelineConfiguration.class,
                    CustomizersConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Pipeline.class);
                    Pipeline pipeline = context.getBean(Pipeline.class);
                    assertThat(pipeline.stages()).containsExactly("user");
                    assertThat(pipeline.mode()).isEqualTo("custom");
                });
    }
}
```

### 6.1. Chạy test

Ở thư mục dự án chứa Gradle wrapper đã cấu hình JUnit Platform:

```bash
./gradlew test --tests example.customizers.OrderedCustomizerTests
```

Nếu dùng Maven có Surefire/JUnit 5:

```bash
./mvnw -Dtest=OrderedCustomizerTests test
```

**Kết quả kỳ vọng:** ba test PASS. Chuỗi stdout của Gradle/Maven phụ thuộc version và cấu hình logging, nên không khẳng định một dòng output cố định.

### 6.2. Vì sao code hoạt động như vậy?

**Test `appliesAllCustomizersInOrder`:** ba bean được khai báo theo thứ tự source là `final`, `base`, `validate`, nhưng `orderedStream()` sắp theo `@Order`: `10 → 20 → 30`. Do đó `stages()` đúng bằng `["base", "validate", "final"]`. `baseCustomizer` đặt mode `base`; `finalCustomizer` chạy sau và đặt mode `fast`, nên kết quả cuối là `fast`. Test kiểm tra cả **thứ tự callback** và **trường hợp ghi đè thuộc tính**.

**Test `noCustomizersKeepsDefaultValues`:** không có bean `PipelineCustomizer` nào, `ObjectProvider.orderedStream()` cho tập rỗng; vẫn tạo được `Pipeline` mặc định `mode = "standard"` và danh sách stage rỗng. Đây là lợi ích của extension point tùy chọn: starter hoạt động khi không ai tùy biến.

**Test `userPipelineMakesDefaultAutoConfigurationBackOff`:** ứng dụng tự khai báo `Pipeline` nên `@ConditionalOnMissingBean(Pipeline.class)` loại bỏ pipeline mặc định trong auto-configuration. Những customizer do người dùng đăng ký vẫn là bean, nhưng vì **không có default pipeline builder nào gọi chúng**, chúng không được áp dụng lên instance `Pipeline` do người dùng tự tạo. Đây là hợp đồng quan trọng: tùy biến chỉ diễn ra ở bên tiêu thụ callback; nó không “tự động tiêm” vào mọi đối tượng cùng kiểu.

### 6.3. Ý nghĩa của các annotation

- `@AutoConfiguration` đánh dấu phần cung cấp đối tượng mặc định; trong test, nó được nhập tường minh bằng `AutoConfigurations.of(...)`.
- `@ConditionalOnMissingBean(Pipeline.class)` giúp auto-configuration nhường chỗ khi ứng dụng cung cấp đối tượng cuối. Đây là điều kiện bean definition, không tự liên quan đến thứ tự chạy callback.
- `@Configuration(proxyBeanMethods = false)` khai báo các bean tùy biến của người dùng.
- `@Bean @Order(...)` đặt thứ tự trên **từng bean customizer**.
- `ObjectProvider<PipelineCustomizer>` thu thập mọi bean matching type; `orderedStream()` cho đúng thứ tự và `forEach` áp dụng lần lượt.
- `List.copyOf(stages)` tạo bản sao không thay đổi của danh sách stage trong đối tượng đầu ra; tránh builder còn mutable làm thay đổi cấu hình sau `build()`.

Ví dụ test trên là một tệp Java hoàn chỉnh trong dự án Spring Boot test phù hợp. Nó **không yêu cầu** đăng ký nested auto-configuration trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` vì test đã cung cấp tường minh. Đối với starter production, auto-configuration được khám phá qua file imports này theo tài liệu Spring Boot 3.3.

## 7. Thực tế Spring Boot: nhiều customizer của web server và Jackson

### 7.1. `WebServerFactoryCustomizer`

Spring Boot 3.3 cung cấp `WebServerFactoryCustomizer<T extends WebServerFactory>` để cho bean mở rộng nhận web server factory trước lúc máy chủ khởi động. Ví dụ khai báo customizer ứng dụng cho servlet web server:

```java
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.servlet.server.ConfigurableServletWebServerFactory;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(100)
public class MyServerPortCustomizer
        implements WebServerFactoryCustomizer<ConfigurableServletWebServerFactory> {

    @Override
    public void customize(ConfigurableServletWebServerFactory factory) {
        factory.setPort(9090);
    }
}
```

Đây là **class hoàn chỉnh trong project Spring Boot 3.3 Servlet**; lưu thành `MyServerPortCustomizer.java` và bổ sung package tương ứng của dự án. Nó không cần tự gọi `customize`: Spring Boot có cơ chế tiêu thụ những bean thuộc interface này. Trong tài liệu Boot 3.3, các customizer web-server auto-configured thường có order `0` và được xử lý trước customizer của người dùng nếu người dùng không chỉ định thứ tự khác. `@Order(100)` ở đây chủ ý thể hiện “đến sau order 0” theo hợp đồng sort tương ứng.

**Cảnh báo vòng đời:** `WebServerFactoryCustomizer` thường được gọi từ `WebServerFactoryCustomizerBeanPostProcessor` ở giai đoạn rất sớm của `ApplicationContext`. Chính API Spring Boot lưu ý có thể nên lấy dependency một cách lazy thay vì ép autowire sớm những bean phức tạp vào customizer. Không làm side effect như gọi network hoặc truy cập bean hạ tầng chưa sẵn sàng trong callback này.

Nếu hai customizer đều gọi `factory.setPort(...)` thì lần set sau thường quyết định port cuối, nhưng property không nên bị nhiều module tranh chấp. Hãy dùng `server.port` khi chỉ cần một cấu hình cổng đơn giản; chỉ dùng customizer khi thực sự cần lập trình trực tiếp trên factory.

### 7.2. `Jackson2ObjectMapperBuilderCustomizer`

Trong Spring Boot 3.3, `Jackson2ObjectMapperBuilderCustomizer` cho phép thay đổi cấu hình builder của Jackson mà vẫn dùng luồng auto-configuration mặc định. Có thể có nhiều bean customizer như: chọn định dạng ngày, đăng ký serializer/module, tinh chỉnh naming strategy. Nếu hai customizer đặt **cùng một property** trên builder, thứ tự áp dụng có thể thay đổi kết quả.

Ví dụ minh họa ý định:

```java
@Bean
@Order(100)
Jackson2ObjectMapperBuilderCustomizer useSnakeCase() {
    return builder -> builder.propertyNamingStrategy(
            com.fasterxml.jackson.databind.PropertyNamingStrategies.SNAKE_CASE);
}
```

Đoạn này cần import `org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer`, `@Bean` và `@Order`; đặt trong một class cấu hình phù hợp có Jackson trên classpath. Đừng dựa vào một giá trị `@Order` bất kỳ để thắng mọi customizer của thư viện: phải xem thứ tự thực tế, default và hợp đồng của Spring Boot. Nên kiểm tra **ObjectMapper cuối cùng** bằng serialization test.

Nếu nhu cầu chỉ là cấu hình property được hỗ trợ như `spring.jackson.property-naming-strategy`, ưu tiên dùng property rõ ràng. Customizer phù hợp cho các biến đổi khó thể hiện bằng property hoặc khi thực sự xây dựng extension point.

### 7.3. Sự khác biệt với customizer do bạn tự định nghĩa

Spring Boot biết và tự gọi các loại customizer **mà chính Boot có cơ chế hỗ trợ**. Một interface `MyCustomizer` do bạn tự tạo **không tự được gọi** chỉ vì có bean implements interface và `@Order`. Bạn phải viết consumer, ví dụ trong `@Bean` factory method, thu thập và áp dụng callback bằng `orderedStream()` như phần test.

## 8. Xử lý nhiều customizer cùng sửa một cấu hình

Đừng coi ordering là lời giải duy nhất cho mọi xung đột. Hãy xác định loại thao tác:

| Kiểu thao tác | Ví dụ | Cần chú ý |
| --- | --- | --- |
| Gán lại cùng property | A đặt timeout `5s`, B đặt `10s` | “Lần set sau thắng” thường đúng với setter đơn giản; cần công bố chính sách |
| Thêm phần tử | A thêm `AuthFilter`, B thêm `AuditFilter` | Thứ tự danh sách có thể tác động luồng request; kiểm tra phần tử trùng |
| Đăng ký handler theo key | A và B cùng đăng ký key `json` | Nên phát hiện trùng key hoặc xác định quyền ghi đè rõ |
| Đọc và validate | C kiểm tra timeout trong phạm vi cho phép | Nên chạy sau những thay đổi liên quan, tránh validate trạng thái chưa hoàn tất |
| Hoàn thiện builder | D gọi `build()` hoặc khóa cấu hình | Customizer sau đó có thể không sửa được; quy định rõ giai đoạn finalize |

Một pattern rõ ràng là **chuỗi giai đoạn**:

1. Customizer mặc định thiết lập thông số an toàn.
2. Customizer tùy chọn được cấu hình bằng property.
3. Customizer nghiệp vụ thêm interceptor/handler.
4. Một bước validation/finalize **do bên sở hữu builder gọi riêng** sau tất cả callback để kiểm tra bất biến.

Dù có thể gán cho validator thứ tự lớn nhất, một bước finalize tách hẳn ra khỏi tập customizer sẽ dễ bảo đảm hơn rằng không có customizer nào chỉnh sửa sau khi validate. Với cùng một key quan trọng, có thể fail-fast nếu hai callback cùng tranh quyền thiết lập, thay vì giải quyết mâu thuẫn bằng một con số `@Order` tùy tiện.

### Idempotency

Nếu consumer có thể gọi các customizer nhiều lần trên cùng builder, callback thêm vào list có thể tạo phần tử trùng. Chẳng hạn:

```java
void customize(PipelineDraft draft) {
    draft.addStage("audit");
}
```

Đây là mảnh mã đơn giản, chưa idempotent. Thiết kế có thể yêu cầu builder kiểm tra `contains("audit")` hoặc lưu stage theo key duy nhất. Không cần ép idempotency cho mọi callback nếu hợp đồng bảo đảm mỗi builder chỉ được customizer một lần; nhưng phải làm rõ để người viết extension không hiểu sai.

## 9. Thứ tự không rõ ràng và cách kiểm chứng

### 9.1. Những sai lầm điển hình

- **Chỉ đặt `@Order` trên các class customizer nhưng tự duyệt `getBeansOfType().values()`:** map không bảo đảm ưu tiên `@Order`. Dùng `orderedStream()` hoặc sort theo một comparator đúng.
- **Suy luận theo thứ tự khai báo `@Bean`:** source order không là hợp đồng gọi callback.
- **Nhầm `@Order` với `@DependsOn`:** cái đầu sắp thứ tự trong collection được consumer xử lý, cái sau quy định thứ tự **khởi tạo instance**.
- **Dùng `@AutoConfiguration(after=...)` để điều khiển callback:** cái này định thứ tự xử lý auto-configuration và ảnh hưởng điều kiện bean definition, không tự đổi thứ tự áp dụng một danh sách customizer.
- **Đặt `@Order` trên lớp `@Configuration` và nghĩ các bean trong lớp thừa hưởng:** mỗi customizer bean phải mang order riêng nếu cần.
- **Dùng `@Primary` để “chọn customizer thắng”:** nếu consumer thu thập tất cả customizer theo kiểu, `@Primary` không làm các bean còn lại biến mất. Nó chủ yếu giúp chọn ứng viên khi inject dependency kiểu đơn lẻ.
- **Để hai customizer có cùng order rồi mong kết quả ổn định:** cần giá trị phân biệt hoặc hợp đồng thứ tự phụ.
- **Gán giá trị order tuyệt đối nhưng không xem thư viện đang dùng:** một extension point có thể đặt sẵn các khoảng order hoặc có thêm xử lý priority riêng. Luôn đối chiếu API và test.
- **Customizer có dependency về chính đối tượng đang được tạo:** có thể dẫn tới vòng phụ thuộc nếu consumer phải tạo customizer để build đối tượng đó. Tách cấu hình input khỏi đối tượng kết quả.
- **Thực thi callback quá sớm:** đặc biệt với web server factory, không ép khởi tạo hạ tầng phức tạp khi BeanPostProcessor đang hoạt động.
- **Tin rằng startup thành công là đủ:** cần kiểm thử trạng thái **cuối cùng** của builder hoặc sản phẩm sau khi áp dụng toàn bộ customizer.

### 9.2. Kiểm tra đúng điều cần chứng minh

Trước tiên xác định bean customizer có được đăng ký và được nhận diện đúng type không. Sau đó kiểm tra **thứ tự callback được gọi**, chứ không chỉ thứ tự constructor của customizer. Nếu muốn quan sát thực tế, có thể ghi tên callback vào một `List<String>` trong test như bài `Pipeline` ở trên. Cuối cùng, kiểm tra **trạng thái kết quả** mà hệ thống dùng thật, ví dụ mode, timeout, danh sách interceptor hay JSON serialized.

Một bộ test tối thiểu cho extension point do nhóm tự viết nên bao gồm:

1. Không có customizer → vẫn tạo được đối tượng mặc định.
2. Một customizer → thay đổi mong đợi được áp dụng.
3. Nhiều customizer với order khác nhau → thứ tự áp dụng và trạng thái cuối chính xác.
4. Hai customizer cùng sửa một property → chính sách xung đột được kiểm chứng.
5. Thêm hoặc bớt customizer bằng conditional bean → consumer chỉ lấy những bean phù hợp.
6. Có user-defined product và auto-configuration back-off → hiểu rõ customizer còn được tiêu thụ hay không.

`ApplicationContextRunner` phù hợp với starter/auto-configuration vì tạo context độc lập cho mỗi case và dễ khẳng định bean presence/absence, final object state. Dùng `ConditionEvaluationReport` khi nghi ngờ một customizer không được đăng ký vì condition; dùng trace callback khi nghi ngờ thứ tự. Hai dạng bằng chứng giải quyết hai lớp vấn đề khác nhau.

## 10. Câu hỏi tự kiểm tra

1. Có ba customizer gán `@Order(200)`, `@Order(10)`, `@Order(100)`. Nếu consumer dùng `ObjectProvider.orderedStream()`, thứ tự áp dụng là gì? **10, 100, 200**.
2. Có cả `@Order(10)` và `@Order(10)`, nhưng kết quả phụ thuộc ai chạy sau. Nên làm gì? **Cho order khác nhau hoặc gom thao tác phụ thuộc vào một customizer; không dựa vào vị trí khai báo source**.
3. `@Order(5)` trên một customizer có buộc constructor của nó chạy trước bean order 10 không? **Không.** Nó mô tả thứ tự khi sắp xếp, không trực tiếp điều khiển singleton startup.
4. Một nhóm đặt `@AutoConfiguration(after = OtherConfig.class)` nhưng callbacks vẫn không theo thứ tự mong đợi. Vì sao? **After sắp thứ tự định nghĩa auto-configuration, không phải thứ tự apply customizer.**
5. `ObjectProvider.stream()` có cùng cam kết thứ tự với `orderedStream()` không? **Không.** `orderedStream()` nêu rõ hợp đồng sort; `stream()` không cam kết ordering.
6. Một customizer của người dùng có `@Order(100)` và web-server customizer mặc định order 0. Người dùng mong callback của mình đến sau. Có hợp lý không? **Có nếu extension point dùng ordering tương ứng**; cần đối chiếu cấu hình thực tế và các customizer khác, không lấy đó làm bảo đảm cho mọi bean.
7. Chỉ tạo bean `PipelineCustomizer` và gắn `@Order`, nhưng không có code nào gọi `customize`. Pipeline có thay đổi không? **Không.** Consumer phải thực sự áp dụng callback.
8. Starter đã `@ConditionalOnMissingBean(Pipeline.class)` và người dùng tự tạo `Pipeline`. Các customizer mà starter định áp dụng có còn tự chạy trên pipeline người dùng không? **Không**, trừ khi người dùng hoặc một cơ chế khác chủ động gọi chúng.
9. Hai customizer cùng set timeout, cái có order lớn hơn chạy sau. Có luôn nên để cái sau thắng không? **Không bắt buộc.** Cần định nghĩa quyền sở hữu property và kiểm tra xung đột/validation theo hợp đồng extension point.

## 11. Tài liệu đối chiếu (Spring Boot 3.3 / Spring Framework 6.1)

- [Spring Framework 6.1 — ObjectProvider.orderedStream()](https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/beans/factory/ObjectProvider.html): trả sequential stream đã sắp theo order comparator chung, xét `Ordered`/`@Order` trong standard context.
- [Spring Framework 6.1 — Ordered](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/Ordered.html): số càng nhỏ, priority càng cao; cùng số không mang bảo đảm thứ tự tương đối.
- [Spring Framework 6.1 — Bean annotation](https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/context/annotation/Bean.html): `@Bean` method có thể mang `@Order`, nhưng ordering không quyết định singleton startup.
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): bean `WebServerFactoryCustomizer` và thứ tự customizer mặc định.
- [Spring Boot 3.3 — WebServerFactoryCustomizer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/server/WebServerFactoryCustomizer.html): callback được gọi trước khi web server khởi động và lưu ý lifecycle rất sớm.
- [Spring Boot 3.3 — Jackson auto-configuration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jackson/package-summary.html): `Jackson2ObjectMapperBuilderCustomizer`.
