# @AutoConfigureBefore và @AutoConfigureAfter khi khai báo quan hệ thứ tự

## 1. Mục tiêu và vấn đề cần giải quyết

Trong Spring Boot, nhiều lớp **auto-configuration** cùng đóng góp các bean definition vào một `ApplicationContext`. Một cấu hình có thể cung cấp bean nền tảng, còn cấu hình khác chỉ nên hoạt động sau khi các bean definition nền tảng đã được xem xét. Nếu Spring Boot áp dụng chúng không đúng quan hệ mong muốn, những điều kiện như `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean` có thể cho kết quả khác dự kiến.

Ví dụ: `EngineAutoConfiguration` cung cấp bean `Engine`; `ReportAutoConfiguration` chỉ tạo `ReportService` nếu đã có bean `Engine`. Ta muốn Spring Boot **áp dụng cấu hình Engine trước cấu hình Report**, bất kể thứ tự hai tên lớp xuất hiện trong danh sách auto-configuration.

Hai annotation trong package `org.springframework.boot.autoconfigure` thể hiện quan hệ này:

- `@AutoConfigureBefore`: cấu hình **đang được chú thích** cần được áp dụng **trước** cấu hình được chỉ định.
- `@AutoConfigureAfter`: cấu hình **đang được chú thích** cần được áp dụng **sau** cấu hình được chỉ định.

Bài này giúp bạn đọc đúng chiều phụ thuộc, chọn dạng khai báo bằng class hoặc class name, phân biệt **thứ tự áp dụng auto-configuration** với **thứ tự khởi tạo bean**, và kiểm thử quan hệ bằng Spring Boot 3.3 / Java 17+.

## 2. Hiểu đúng từ “trước” và “sau”

Giả sử có hai auto-configuration:

```text
EngineAutoConfiguration
       │
       │ cung cấp bean definition Engine
       ▼
ReportAutoConfiguration
       │
       │ @ConditionalOnBean(Engine.class)
       ▼
ReportService bean definition (nếu điều kiện khớp)
```

Một trong hai cách sau có thể diễn đạt cùng quan hệ thứ tự:

```java
// Đặt trên EngineAutoConfiguration:
@AutoConfigureBefore(ReportAutoConfiguration.class)

// Hoặc đặt trên ReportAutoConfiguration:
@AutoConfigureAfter(EngineAutoConfiguration.class)
```

Đây là **các đoạn annotation minh họa**, không phải một chương trình Java độc lập.

Nếu `A` cần được áp dụng trước `B` thì:

| Annotation được đặt ở đâu? | Cách viết | Quan hệ tạo ra |
|---|---|---|
| Trên `A` | `@AutoConfigureBefore(B.class)` | `A → B` |
| Trên `B` | `@AutoConfigureAfter(A.class)` | `A → B` |
| Trên `A` | `@AutoConfigureAfter(B.class)` | `B → A` |
| Trên `B` | `@AutoConfigureBefore(A.class)` | `B → A` |

**Chủ thể của annotation luôn là lớp đang mang annotation.** Chẳng hạn `@AutoConfigureAfter(EngineAutoConfiguration.class)` trên `ReportAutoConfiguration` có nghĩa “Report đi **sau Engine**”, không phải “Engine đi sau Report”.

### Điều mà annotation thực sự bảo đảm

Các annotation này đưa ra **chỉ dẫn thứ tự áp dụng các lớp auto-configuration** khi Spring Boot sắp xếp các cấu hình được chọn. Thứ tự này tác động đến **thứ tự đăng ký và đánh giá bean definition**, từ đó quan trọng với những điều kiện kiểm tra bean đã được xử lý ở thời điểm đánh giá.

Chúng **không buộc các đối tượng bean phải được khởi tạo theo cùng thứ tự**. Việc tạo bean khi runtime tuân theo dependency injection, các tham số constructor/`@Bean`, `@DependsOn`, lazy initialization và cơ chế lifecycle liên quan.

Ví dụ, cả hai bean definition được đăng ký theo thứ tự Engine rồi Report nhưng Spring vẫn có thể tạo instance theo trình tự khác khi quan hệ phụ thuộc cho phép. Nếu `ReportService` nhận `Engine` qua constructor, Spring sẽ giải quyết dependency khi tạo `ReportService`. Không nên dùng `@AutoConfigureBefore` như một giải pháp cho yêu cầu “đối tượng này phải chạy hàm khởi tạo trước đối tượng kia”.

## 3. API: class reference, class name và cú pháp hiện đại

Hai annotation chuyên dụng hỗ trợ hai thuộc tính:

| Annotation | Thuộc tính | Kiểu | Diễn giải |
|---|---|---|---|
| `@AutoConfigureBefore` | `value` | `Class<?>[]` | Những auto-configuration phải được áp dụng sau lớp hiện tại |
| `@AutoConfigureBefore` | `name` | `String[]` | Tên đầy đủ của các auto-configuration phải đi sau |
| `@AutoConfigureAfter` | `value` | `Class<?>[]` | Những auto-configuration phải được áp dụng trước lớp hiện tại |
| `@AutoConfigureAfter` | `name` | `String[]` | Tên đầy đủ của các auto-configuration phải đi trước |

Ví dụ khi module hiện tại có thể tham chiếu trực tiếp đến class đích:

```java
@AutoConfiguration
@AutoConfigureAfter(EngineAutoConfiguration.class)
public class ReportAutoConfiguration {
    // ...
}
```

Đây là mảnh minh họa của lớp cấu hình, giả sử `EngineAutoConfiguration` có sẵn trong classpath khi biên dịch. Với nhiều đích:

```java
@AutoConfigureAfter({
    EngineAutoConfiguration.class,
    StorageAutoConfiguration.class
})
```

Cấu hình hiện tại phải được xét sau **cả hai** cấu hình đích; chú thích không bắt buộc thứ tự giữa `EngineAutoConfiguration` và `StorageAutoConfiguration` khi chưa có quan hệ riêng.

Nếu muốn tránh phụ thuộc compile-time vào class có thể chỉ tồn tại ở một starter khác, dùng thuộc tính `name`:

```java
@AutoConfiguration
@AutoConfigureAfter(name = "com.example.engine.EngineAutoConfiguration")
public class ReportAutoConfiguration {
    // ...
}
```

Giá trị phải là **tên class đầy đủ**, không phải tên bean hoặc đường dẫn file. Với class lồng nhau, tài liệu API yêu cầu dạng tên JVM có ký tự `$`, ví dụ `com.example.Outer$InnerAutoConfiguration`.

Từ Spring Boot 2.7 trở đi, `@AutoConfiguration` còn có các thuộc tính tương ứng và thường được dùng trực tiếp:

```java
@AutoConfiguration(after = EngineAutoConfiguration.class)
public class ReportAutoConfiguration {
    // ...
}
```

```java
@AutoConfiguration(
    beforeName = "com.example.report.ReportAutoConfiguration")
public class EngineAutoConfiguration {
    // ...
}
```

Bảng tương đương trong Spring Boot 3.3:

| Annotation chuyên dụng | Thuộc tính tương đương của `@AutoConfiguration` |
|---|---|
| `@AutoConfigureBefore(A.class)` | `@AutoConfiguration(before = A.class)` |
| `@AutoConfigureBefore(name = "pkg.A")` | `@AutoConfiguration(beforeName = "pkg.A")` |
| `@AutoConfigureAfter(A.class)` | `@AutoConfiguration(after = A.class)` |
| `@AutoConfigureAfter(name = "pkg.A")` | `@AutoConfiguration(afterName = "pkg.A")` |

**Khuyến nghị:** trong code mới sử dụng `@AutoConfiguration(before = …, after = …)` nếu phù hợp để gom thông tin trên một annotation; hai annotation chuyên dụng vẫn có ý nghĩa và vẫn được hỗ trợ trong Spring Boot 3.3. Chọn một cách thể hiện nhất quán. Không cần khai báo cùng một quan hệ ở hai đầu nếu chỉ một bên đã diễn đạt đủ; việc khai báo hai đầu trong ví dụ chạy dưới đây chỉ để người học nhìn thấy cả hai annotation.

### Vị trí hợp lệ và điều kiện áp dụng

Các chỉ dẫn trước/sau được Spring Boot sử dụng khi **sắp xếp các auto-configuration được import**. Chúng không tự động thêm class đích vào danh sách import. Nếu `EngineAutoConfiguration` không được chọn/không tồn tại, `@AutoConfigureAfter(EngineAutoConfiguration.class)` không khiến Engine được bật lên.

Trong Spring Boot 3.3, một auto-configuration công bố bởi thư viện cần được liệt kê trong file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng là tên đầy đủ của một class auto-configuration. Không nên đưa các class này vào component scan thông thường hoặc giả định rằng đặt `@AutoConfigureAfter` trên một class `@Configuration` bất kỳ sẽ khiến Spring sắp lại mọi cấu hình được đăng ký thủ công theo cùng cơ chế.

## 4. Vì sao thứ tự đặc biệt quan trọng với điều kiện bean?

Xem tình huống gồm hai cấu hình:

```java
// Auto-configuration cung cấp Engine:
@Bean
Engine engine() {
    return new Engine();
}

// Auto-configuration khác chỉ tạo ReportService khi đã có Engine:
@Bean
@ConditionalOnBean(Engine.class)
ReportService reportService(Engine engine) {
    return new ReportService(engine);
}
```

Đây là mã rút gọn minh họa; `Engine` và `ReportService` là các kiểu ứng dụng tự định nghĩa.

`@ConditionalOnBean` thường dựa trên những bean definition mà Spring Boot **đã xử lý đến thời điểm điều kiện được đánh giá**. Nếu class có `@ConditionalOnBean(Engine.class)` bị xét trước khi bean definition của Engine được thêm vào, điều kiện có thể không khớp, dù sau đó Engine vẫn xuất hiện.

Quan hệ `ReportAutoConfiguration after EngineAutoConfiguration` giúp sắp xếp việc **xét các cấu hình tự động** để bean definition nền tảng có cơ hội được đăng ký trước.

Điều này không có nghĩa chỉ cần thêm `@AutoConfigureAfter` là bean bảo đảm tồn tại. Engine vẫn có thể không được tạo khi:

- `EngineAutoConfiguration` không được import hoặc bị exclude.
- Điều kiện trên chính `EngineAutoConfiguration`/phương thức `@Bean` của Engine không khớp.
- Một configuration khác thay thế Engine, hoặc cách khai báo loại/tên bean không đáp ứng yêu cầu `@ConditionalOnBean`.
- Bean definition tồn tại nhưng quá trình khởi tạo bean sau đó thất bại do dependency không hợp lệ.

Thứ tự là **một điều kiện cần để xử lý đúng tình huống phụ thuộc vào bean definition đã đăng ký**, không phải quy tắc tự động vượt qua mọi điều kiện khác.

### Ví dụ quyết định

| Auto-config Engine | Auto-config Report | Quan hệ sắp xếp | Kết quả kỳ vọng với `@ConditionalOnBean(Engine.class)` |
|---|---|---|---|
| Được chọn, tạo Engine | Được chọn | Engine trước Report | Report có thể tạo `ReportService` |
| Bị loại khỏi danh sách | Được chọn | Report khai báo after Engine | Không có Engine thì điều kiện Report không khớp |
| Được chọn nhưng điều kiện tạo Engine không khớp | Được chọn | Engine trước Report | Report không khớp nếu không có Engine từ nguồn khác |
| Được chọn | Không được chọn | Engine khai báo before Report | Chỉ có phần Engine |
| Được chọn | Được chọn | Không có quan hệ tường minh | Kết quả có thể phụ thuộc thứ tự áp dụng; không dựa vào thứ tự dòng trong file để suy luận |

Với tình huống không có quan hệ tường minh, không nên khẳng định chắc chắn sẽ sai hoặc đúng: thứ tự thực tế còn phụ thuộc metadata, các ràng buộc khác và bộ sắp xếp. Hãy khai báo quan hệ cần thiết thay vì phụ thuộc vào một thứ tự trùng hợp.

## 5. Ví dụ Java 17+, Spring Boot 3.3: kiểm thử quan hệ trước/sau

Ví dụ này dựng một dự án Maven nhỏ. `EngineAutoConfiguration` có `@AutoConfigureBefore`; `ReportAutoConfiguration` có `@AutoConfigureAfter`. Bài test cố ý liệt kê **Report trước Engine** trong `AutoConfigurations.of(...)`, rồi xác nhận Spring Boot vẫn xử lý quan hệ thứ tự đúng.

Cấu trúc:

```text
ordering-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/order/
    │   │   ├── Engine.java
    │   │   ├── ReportService.java
    │   │   ├── EngineAutoConfiguration.java
    │   │   └── ReportAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/demo/order/
        └── AutoConfigurationOrderTest.java
```

### 5.1. Maven: pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo.order</groupId>
    <artifactId>ordering-demo</artifactId>
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

`spring-boot-starter` cung cấp các lớp Spring Boot/Spring Framework; `spring-boot-starter-test` cung cấp `ApplicationContextRunner`, JUnit 5 và AssertJ để kiểm tra kết quả. Không cần database hay máy chủ HTTP.

### 5.2. Kiểu bean nền tảng: Engine.java

```java
package demo.order;

public record Engine(String name) {
}
```

`record` là cú pháp Java 17 hợp lệ. Một đối tượng `Engine` mang tên giúp test xác định xem bean mặc định hay bean người dùng được chọn.

### 5.3. Kiểu phụ thuộc: ReportService.java

```java
package demo.order;

public record ReportService(Engine engine) {
}
```

`ReportService` cần `Engine`. Quan hệ này thể hiện dependency injection khi **tạo instance**; nó tách biệt với chỉ dẫn sắp xếp **auto-configuration class**.

### 5.4. Auto-configuration cung cấp Engine

File `EngineAutoConfiguration.java`:

```java
package demo.order;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigureBefore;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@AutoConfigureBefore(ReportAutoConfiguration.class)
public class EngineAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Engine.class)
    Engine engine() {
        return new Engine("auto-engine");
    }
}
```

Ở đây, `@AutoConfigureBefore(ReportAutoConfiguration.class)` yêu cầu Engine được **áp dụng trước Report**. `@ConditionalOnMissingBean` nhường quyền nếu người dùng đã tự cung cấp bean `Engine` phù hợp.

### 5.5. Auto-configuration phụ thuộc Engine

File `ReportAutoConfiguration.java`:

```java
package demo.order;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigureAfter;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@AutoConfigureAfter(EngineAutoConfiguration.class)
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnBean(Engine.class)
    @ConditionalOnMissingBean(ReportService.class)
    ReportService reportService(Engine engine) {
        return new ReportService(engine);
    }
}
```

`@AutoConfigureAfter(EngineAutoConfiguration.class)` thể hiện cùng chiều **Engine → Report**. Khi Engine bean definition đã được đăng ký, điều kiện `@ConditionalOnBean(Engine.class)` có thể khớp và `ReportService` được tạo, trừ khi đã có bean thay thế.

Trong hệ thống sản xuất chỉ cần một quan hệ trước/sau được khai báo phù hợp ở một phía; ví dụ đặt cả hai annotation để trực quan hóa cú pháp, không phải yêu cầu bắt buộc.

### 5.6. Công bố auto-configuration cho ứng dụng thực tế

Tạo file `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` có đúng nội dung:

```text
demo.order.EngineAutoConfiguration
demo.order.ReportAutoConfiguration
```

Spring Boot dùng file này để khám phá auto-configuration của thư viện. Thứ tự dòng trong file **không phải API để mô tả quan hệ phụ thuộc**: quan hệ nghiệp vụ được khai báo bằng metadata `@AutoConfigureBefore`/`@AutoConfigureAfter` hoặc các thuộc tính tương đương trên `@AutoConfiguration`.

Ở bài test `ApplicationContextRunner` bên dưới, ta nêu rõ class cần đưa vào context để kiểm tra; việc đó không thay thế file imports trong một thư viện phát hành thật.

### 5.7. Kiểm thử auto-configuration

File `AutoConfigurationOrderTest.java`:

```java
package demo.order;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationOrderTest {

    @Test
    void bothConfigurationsApplyInRequiredOrder() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        ReportAutoConfiguration.class,
                        EngineAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(Engine.class);
                    assertThat(context).hasSingleBean(ReportService.class);
                    assertThat(context.getBean(ReportService.class).engine())
                            .isSameAs(context.getBean(Engine.class));
                    assertThat(context.getBean(Engine.class).name())
                            .isEqualTo("auto-engine");
                });
    }

    @Test
    void reportConfigurationAloneDoesNotInventEngine() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        ReportAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(Engine.class);
                    assertThat(context).doesNotHaveBean(ReportService.class);
                });
    }

    @Test
    void engineConfigurationAloneDoesNotInventReportService() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        EngineAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(Engine.class);
                    assertThat(context).doesNotHaveBean(ReportService.class);
                });
    }

    @Test
    void userEngineOverridesDefaultWithoutBreakingReport() {
        new ApplicationContextRunner()
                .withUserConfiguration(UserEngineConfiguration.class)
                .withConfiguration(AutoConfigurations.of(
                        ReportAutoConfiguration.class,
                        EngineAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(Engine.class);
                    assertThat(context).hasSingleBean(ReportService.class);
                    Engine engine = context.getBean(Engine.class);
                    assertThat(engine.name()).isEqualTo("user-engine");
                    assertThat(context.getBean(ReportService.class).engine())
                            .isSameAs(engine);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserEngineConfiguration {
        @Bean
        Engine engine() {
            return new Engine("user-engine");
        }
    }
}
```

Từ thư mục `ordering-demo` chứa `pom.xml`, với JDK 17+ và Maven:

```bash
mvn test
```

**Kết quả mong đợi:** bốn phương thức test đều PASS. Báo cáo Maven Surefire cần có tổng cộng **4 tests, 0 failures, 0 errors**, giả sử dự án chỉ có lớp test trên. Log Maven cụ thể phụ thuộc phiên bản Maven/Surefire nên không giả định một bản stdout nguyên xi.

Giải thích từng tình huống:

1. **Cả hai auto-config tồn tại:** dù input `AutoConfigurations.of(Report, Engine)` liệt kê ngược, bộ sắp xếp auto-configuration tôn trọng quan hệ Engine trước Report. `Engine` và `ReportService` đều được đăng ký; Report dùng chính bean Engine.
2. **Chỉ có Report:** `@AutoConfigureAfter` không import Engine thay. Không thấy bean `Engine` nên `@ConditionalOnBean(Engine.class)` không khớp; ReportService vắng mặt.
3. **Chỉ có Engine:** `@AutoConfigureBefore` không import Report thay. Chỉ có bean Engine; không có ReportService.
4. **Người dùng tự cung cấp Engine:** cấu hình người dùng được runner xử lý trước các auto-config; `@ConditionalOnMissingBean(Engine.class)` giúp Engine mặc định nhường quyền. Report vẫn nhìn thấy Engine người dùng và đăng ký ReportService.

**Lưu ý kiểm thử:** `ApplicationContextRunner` tạo context cho từng test để cô lập điều kiện. `AutoConfigurations.of(...)` mô phỏng sắp thứ tự auto-configuration tương tự ứng dụng thật; đây là cách kiểm tra phù hợp hơn việc gọi `context.register(…)` bằng tay rồi suy đoán thứ tự parse các `@Configuration` thông thường.

## 6. Bảng lựa chọn cách khai báo

| Bạn cần diễn đạt | Viết ở đâu? | Gợi ý |
|---|---|---|
| `A` phải đi trước `B` | `A`: `@AutoConfigureBefore(B.class)` | Dùng khi A biết B và có dependency compile-time phù hợp |
| `B` phải đi sau `A` | `B`: `@AutoConfigureAfter(A.class)` | Dùng khi B phụ thuộc bean definition do A cung cấp |
| Cần quan hệ sau mà class đích có thể không có khi biên dịch | `@AutoConfigureAfter(name = "pkg.A")` | Dùng tên class đầy đủ, tránh tham chiếu trực tiếp |
| Viết auto-config mới với `@AutoConfiguration` | `@AutoConfiguration(after = A.class)` | Cú pháp tích hợp, tương đương `@AutoConfigureAfter` |
| Chỉ muốn ưu tiên chung giữa các auto-config độc lập | `@AutoConfigureOrder` | Cân nhắc khi không có dependency cụ thể |
| Muốn bean A được tạo trước bean B | Dependency injection hoặc `@DependsOn` | Không dùng quan hệ auto-configuration làm cơ chế lifecycle |
| Muốn xếp thứ tự các phần tử được inject dưới dạng List | `@Order` / `Ordered` theo ngữ cảnh | Đây là bài toán thứ tự collection/extension, khác sắp auto-configuration |

### BEFORE hay AFTER: chọn phía nào?

Nếu tác giả của `ReportAutoConfiguration` biết chắc nó phụ thuộc vào Engine thì cách dễ đọc là:

```java
@AutoConfiguration(after = EngineAutoConfiguration.class)
public class ReportAutoConfiguration {
    // chỉ có thể đóng góp ReportService nếu Engine phù hợp
}
```

Nếu tác giả Engine muốn tuyên bố rằng một nhóm auto-configuration khác phải được xét sau nó, `before` cũng hợp lý. Tuy nhiên, đừng tạo mối phụ thuộc hai chiều không cần thiết hoặc buộc module nền tảng import lớp từ module phụ thuộc chỉ để viết `before`; khi đó dùng `after` ở phía phụ thuộc hoặc khai báo bằng tên chuỗi là tự nhiên hơn.

## 7. Các quan hệ phức tạp: đồ thị, nhiều mục tiêu và vòng lặp

Một chuỗi hợp lệ:

```text
StorageAutoConfiguration
          │
          ▼
EngineAutoConfiguration
          │
          ▼
ReportAutoConfiguration
```

Có thể biểu diễn bằng:

```java
// Trên EngineAutoConfiguration:
@AutoConfigureAfter(StorageAutoConfiguration.class)

// Trên ReportAutoConfiguration:
@AutoConfigureAfter(EngineAutoConfiguration.class)
```

Từ hai quan hệ này suy ra Storage trước Engine và Engine trước Report. Không cần gắn số thứ tự tuyệt đối cho từng lớp.

Nếu `MetricsAutoConfiguration` hoàn toàn độc lập, đồ thị không xác định vị trí tương đối duy nhất giữa Metrics với ba lớp trên. Một ràng buộc **trước/sau** thường là **thứ tự tương đối**, không phải cam kết thứ tự toàn cục cho mọi auto-configuration.

### Tránh chu kỳ

Ví dụ sai về thiết kế:

```java
// Trên AAutoConfiguration:
@AutoConfigureAfter(BAutoConfiguration.class)

// Trên BAutoConfiguration:
@AutoConfigureAfter(AAutoConfiguration.class)
```

Hai chỉ dẫn yêu cầu A sau B **và** B sau A, không có thứ tự hợp lệ thỏa cả hai. Đừng cố “sửa” bằng cách đổi sang `@AutoConfigureOrder`; cần xem lại ranh giới chức năng, tách bean trung gian, hoặc loại bỏ một ràng buộc không thật sự cần thiết.

Không nên suy đoán trước thông báo lỗi hoặc chiến lược giải quyết chính xác cho mọi phiên bản khi gặp cycle. Điểm quan trọng là **thiết kế đồ thị phụ thuộc không có chu trình** và kiểm thử khởi tạo context với những tổ hợp auto-configuration liên quan.

### Ràng buộc vào auto-configuration không được chọn

Việc ghi:

```java
@AutoConfigureAfter(name =
        "com.example.optional.OptionalClientAutoConfiguration")
```

không buộc `OptionalClientAutoConfiguration` phải tồn tại trong classpath hoặc được import. Khi class đích vắng mặt, quan hệ đó không tạo ra bean. Nếu cấu hình hiện tại thật sự cần một class thư viện, hãy dùng thêm `@ConditionalOnClass` hoặc cơ chế điều kiện thích hợp để thể hiện yêu cầu, độc lập với sắp xếp thứ tự.

## 8. Những nhầm lẫn cần tránh

### Nhầm 1: “After nghĩa là bean khởi tạo sau”

**Không đúng.** Ý nghĩa là **auto-configuration được áp dụng sau**. Thứ tự tạo bean phụ thuộc quan hệ dependency. Một bean có thể bị tạo trễ do `@Lazy`; một bean khác có thể được tạo sớm do dependency chain. Nếu cần kiểm soát thứ tự khởi tạo vì side effect, hãy thiết kế dependency rõ, cân nhắc `@DependsOn`, hoặc dùng lifecycle callback thích hợp.

### Nhầm 2: “Có khai báo after thì tự động bật auto-config đích”

**Không đúng.** `@AutoConfigureAfter` không phải `@Import`, không phải dependency của Maven/Gradle và cũng không xóa điều kiện `@ConditionalOnClass`. Nó chỉ định quan hệ giữa các ứng viên đã tham gia quá trình auto-configuration.

### Nhầm 3: “Thứ tự trong AutoConfiguration.imports chính là thứ tự cuối”

**Không nên dựa vào.** File imports công bố **ứng viên**. Spring Boot còn sắp xếp auto-config theo metadata và những quan hệ đã khai báo. Tương tự, thứ tự truyền class vào `AutoConfigurations.of(...)` trong test không nên dùng để diễn đạt dependency thay cho annotations.

### Nhầm 4: “@Order, @AutoConfigureOrder và @DependsOn tương đương”

Chúng phục vụ những nhu cầu khác nhau:

- `@AutoConfigureBefore`/`@AutoConfigureAfter`: quan hệ tương đối giữa **auto-configuration classes**.
- `@AutoConfigureOrder`: thứ tự ưu tiên tổng quát cho các auto-configuration khi không có quan hệ phụ thuộc cụ thể; không thay thế dependency graph.
- `@Order`/`Ordered`: thứ tự của nhiều đối tượng, phần tử extension, bean được inject theo collection hoặc thành phần của Spring tùy điểm áp dụng.
- `@DependsOn`: quan hệ phụ thuộc **khởi tạo/huỷ** giữa bean instances trong cùng context theo hợp đồng Spring.

Đừng dùng annotation ở lớp này để sửa sự cố thuộc lớp khác.

### Nhầm 5: “@ConditionalOnBean sẽ nhìn thấy tất cả bean trong ứng dụng”

**Không đúng ở mọi thời điểm.** Điều kiện được đánh giá khi cấu hình/định nghĩa bean đang được xử lý. Một bean có thể xuất hiện sau đó mà điều kiện đã hoàn thành. Vì thế thứ tự áp dụng auto-configuration và cách khai báo return type của `@Bean` đều ảnh hưởng đến khả năng điều kiện xác định sự tồn tại của bean.

### Nhầm 6: “Sắp xếp auto-config áp dụng cho mọi @Configuration bất kỳ”

**Không phải cam kết chung.** Spring Boot sử dụng metadata auto-configuration cho tập các ứng viên auto-configuration được import theo cơ chế của Boot. Với cấu hình ứng dụng thông thường, thứ tự đăng ký bằng `@Import`, component scanning và cách Spring xử lý configuration có cơ chế riêng. Đừng dựa vào `@AutoConfigureAfter` để kiểm soát thứ tự chạy mọi class Spring `@Configuration`.

## 9. Checklist khi khai báo quan hệ thứ tự

Trước khi thêm annotation, trả lời:

1. **Lớp nào tạo bean definition trước?** Xác định tên auto-config và bean type cụ thể, thay vì giả định vì tên package.
2. **Ai phụ thuộc vào ai?** Vẽ một mũi tên A → B rồi đối chiếu xem `@AutoConfigureBefore` nằm ở A hay `@AutoConfigureAfter` nằm ở B.
3. **Đó có thật là auto-configuration không?** Cả hai class cần tham gia quy trình import auto-config khi áp dụng thực tế; class đích vắng mặt không được annotation tự nạp.
4. **Có dependency compile-time không?** Nếu không hoặc dependency optional, cân nhắc `name`/`beforeName`/`afterName`.
5. **Có chu kỳ không?** Xem các quan hệ đã có để bảo đảm đồ thị có thứ tự khả thi.
6. **Có nhầm lẫn với bean lifecycle không?** Nếu mục tiêu là tạo/khởi tạo instance theo thứ tự, cần giải quyết ở mức dependency bean.
7. **Đã thử các tổ hợp chưa?** Chạy test có cả hai cấu hình, chỉ có A, chỉ có B và trường hợp người dùng cung cấp bean thay thế.

Trong một ứng dụng có nhiều starter, nên xem **Condition Evaluation Report** khi bean không xuất hiện. Chạy Spring Boot với `--debug` hoặc xem endpoint Actuator `/actuator/conditions` (nếu được cài đặt, bật và expose) để biết điều kiện nào đã khớp hoặc không khớp. Kết hợp với kiểm tra danh sách auto-config thực sự được import thay vì chỉ đọc mỗi annotation.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** `MailAutoConfiguration` cần bean do `TransportAutoConfiguration` đóng góp. Muốn Mail được áp dụng sau Transport, đặt annotation gì trên Mail?

**Đáp án:** `@AutoConfigureAfter(TransportAutoConfiguration.class)` hoặc `@AutoConfiguration(after = TransportAutoConfiguration.class)`.

**Câu 2.** Đặt `@AutoConfigureBefore(A.class)` trên B có nghĩa gì?

**Đáp án:** B được áp dụng trước A; không phải A trước B.

**Câu 3.** A khai báo after B, nhưng B không được import vào application. A có tự động khiến B xuất hiện không?

**Đáp án:** Không. Quan hệ thứ tự không có tác dụng kích hoạt class đích hoặc đăng ký bean thay class đích.

**Câu 4.** A được áp dụng trước B, như vậy bean A chắc chắn được khởi tạo trước bean B?

**Đáp án:** Không. Thứ tự áp dụng auto-configuration quyết định thứ tự đăng ký các bean definition, còn khởi tạo instance phụ thuộc dependency và lifecycle.

**Câu 5.** Một thư viện muốn sắp `ReportAutoConfiguration` sau `com.vendor.storage.StorageAutoConfiguration` nhưng không muốn phụ thuộc biên dịch vào thư viện vendor. Cách khai báo hợp lý?

**Đáp án:** `@AutoConfigureAfter(name = "com.vendor.storage.StorageAutoConfiguration")` hoặc `@AutoConfiguration(afterName = "com.vendor.storage.StorageAutoConfiguration")`.

## 11. Tổng kết

- `@AutoConfigureBefore(Target.class)`: **lớp hiện tại trước Target**.
- `@AutoConfigureAfter(Target.class)`: **lớp hiện tại sau Target**.
- `@AutoConfiguration(before = …, after = …, beforeName = …, afterName = …)` là cú pháp tương đương trong Spring Boot 3.3.
- Quan hệ này chỉ áp dụng trong **sắp xếp auto-configuration** và ảnh hưởng **bean definition/condition evaluation**, không quy định thứ tự tạo object bean hay tự động import cấu hình được tham chiếu.
- Khi thứ tự là một phụ thuộc thật, dùng quan hệ rõ ràng, tránh cycle, và xác minh bằng `ApplicationContextRunner` với các trường hợp có/không có auto-config liên quan.

### Tài liệu chính thức

- [Spring Boot 3.3 — AutoConfigureBefore](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html)
- [Spring Boot 3.3 — AutoConfigureAfter](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html)
- [Spring Boot 3.3 — AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot — Testing Auto-configuration with ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
