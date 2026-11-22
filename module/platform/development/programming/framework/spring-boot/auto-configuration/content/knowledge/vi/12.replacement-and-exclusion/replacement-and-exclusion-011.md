# Kiểm tra tác động dây chuyền khi loại bean nền mà cấu hình khác đang cần

## 1. Vì sao một thao tác loại trừ có thể ảnh hưởng nhiều cấu hình?

Một bean nền (infrastructure/foundation bean) là đối tượng mà các bean hoặc cơ chế cấu hình khác dựa vào để hoạt động: `DataSource` cho JDBC/JPA, `TransactionManager` cho giao dịch, `CacheManager` cho cache, `ObjectMapper` cho JSON, hoặc một client chung do starter nội bộ cung cấp.

Khi loại auto-configuration tạo bean nền, tác động **không dừng lại ở một bean**. Những cấu hình phụ thuộc vào bean đó có thể:

1. **Không còn khớp điều kiện**: `@ConditionalOnBean(FoundationService.class)` trở thành false, nên bean phụ thuộc **không được đăng ký**. Ứng dụng có thể vẫn khởi động, nhưng mất chức năng.
2. **Thất bại lúc khởi tạo**: một bean vẫn được đăng ký nhưng cần `FoundationService` qua constructor hoặc tham số `@Bean`; Spring không tìm được ứng viên phù hợp và quá trình khởi động thất bại.
3. **Chuyển sang nhánh dự phòng**: một cấu hình `@ConditionalOnMissingBean` hoặc `@ConditionalOnProperty` khác có thể bắt đầu khớp, tạo bean mặc định/thay thế. Đây có thể là chủ đích hoặc thay đổi hành vi ngoài mong muốn.
4. **Vẫn dùng được bean của người dùng**: nếu ứng dụng cung cấp bean nền cùng contract, các consumer có thể hoạt động dù auto-configuration cung cấp default đã bị loại.
5. **Tiếp tục khởi động nhưng lỗi ở runtime**: phụ thuộc tùy chọn (`ObjectProvider`, `Optional`) hoặc code truy xuất bean khi cần có thể làm việc phát hiện thiếu phụ thuộc bị trì hoãn cho đến khi tính năng được gọi.

Vì vậy, kiểm tra tác động dây chuyền cần nhìn vào **đồ thị các bean và điều kiện**, thay vì chỉ kiểm tra xem cấu hình được exclude có xuất hiện trong log hay không.

### Mô hình phụ thuộc

```mermaid
flowchart TD
    A["FoundationAutoConfiguration"] -->|đăng ký mặc định| B["FoundationService"]
    B -->|@ConditionalOnBean| C["DependentService (tùy điều kiện)"]
    B -->|tham số @Bean bắt buộc| D["StrictConsumerService"]
    B -->|phụ thuộc tùy chọn| E["Optional consumer"]
    X["Loại FoundationAutoConfiguration"] -.->|mất default| B
    B -.->|vắng mặt| F["C: không đăng ký"]
    B -.->|vắng mặt| G["D: khởi động lỗi"]
    B -.->|vắng mặt| H["E: nhánh không có dependency"]
    U["Bean người dùng cùng contract"] -->|có thể thay default| B
```

Sơ đồ mô tả **các nhánh có thể xảy ra**. Chỉ riêng việc loại `FoundationAutoConfiguration` **không bắt buộc** làm biến mất `FoundationService` nếu bean đó còn được cung cấp từ một nơi khác.

## 2. Xác định chính xác thứ bị loại

### 2.1. Loại một auto-configuration không đồng nghĩa xóa bean theo kiểu

Spring Boot cho phép loại một lớp auto-configuration, chẳng hạn:

```java
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class Application {
}
```

Đây là đoạn minh họa và yêu cầu import `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration` cùng `org.springframework.boot.autoconfigure.SpringBootApplication`. Cách khác là cấu hình:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Hoặc, khi muốn chỉ định bằng chuỗi trong Java:

```java
@SpringBootApplication(
    excludeName = "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class Application {
}
```

Ba cách trên nói rằng **Spring Boot không áp dụng auto-configuration được nêu tên** qua cơ chế auto-configuration import. Chúng **không xóa** một `DataSource` do ứng dụng khai báo riêng; cũng không có nghĩa mọi auto-configuration liên quan JDBC/JPA đều tự động bị exclude theo tên.

Điểm cần nhớ:

- `exclude` và `excludeName` của `@SpringBootApplication`, hoặc property `spring.autoconfigure.exclude`, nhằm vào **auto-configuration candidate**, không phải bất kỳ `@Configuration` hay `@Bean` tùy ý.
- Exclude một lớp không xóa thư viện khỏi classpath. `@ConditionalOnClass` ở các cấu hình khác vẫn có thể match.
- Một bean cùng kiểu do cấu hình người dùng, starter khác hoặc parent context cung cấp có thể vẫn tồn tại.
- Loại auto-configuration có thể làm mất **nhiều bean do lớp đó hoặc cấu hình lồng bên trong nó cung cấp**, không chỉ một tên bean mà ta đang chú ý.
- Không nên coi việc sửa số thứ tự `@Order` hoặc dùng `@DependsOn` là cách “khôi phục” bean definition đã bị loại. Chúng giải quyết bài toán thứ tự, không tạo lại cấu hình bị exclude.

### 2.2. Thay thế bean mặc định là một cơ chế khác

Cấu hình starter thường dùng:

```java
@Bean
@ConditionalOnMissingBean(FoundationService.class)
FoundationService foundationService() {
    return new FoundationService("default");
}
```

Nếu người dùng đăng ký `FoundationService` phù hợp, default ở trên **nhường chỗ**, trong khi các auto-configuration khác vẫn có thể dùng bean của người dùng. Đây là kiểu mở rộng ổn định hơn nếu mục tiêu chỉ là **thay thế cách xây dựng một bean nền**.

**Chỉ exclude cả auto-configuration** khi thực sự muốn vô hiệu hóa chức năng mà nó cung cấp và đã xem xét các consumer liên quan. Nếu chỉ muốn đổi connection settings, serializer, cache backend hoặc bean implementation, trước tiên tìm API tùy chỉnh/property/bean override mà thư viện hỗ trợ.

### 2.3. Đừng nhầm ba trạng thái

| Trạng thái | Provider auto-configuration | Bean nền trong context | Hệ quả có thể xảy ra |
| --- | --- | --- | --- |
| Default bình thường | Có, điều kiện match | Có default | Consumer tiếp tục dùng default |
| Provider bị exclude, không có thay thế | Không | Không | Conditional consumer bị bỏ; consumer bắt buộc có thể lỗi |
| Provider bị exclude, có bean của người dùng | Không | Có bean custom | Conditional consumer có thể tiếp tục hoạt động |
| Provider có mặt nhưng `@ConditionalOnMissingBean` nhường chỗ | Có, default method không match | Có bean custom | Các bean khác trong cùng cấu hình vẫn có thể được đăng ký |

**Cần kiểm tra bean thực tế bằng kiểu/tên/qualifier**, không chỉ tìm xem lớp auto-configuration có được nạp hay không.

## 3. Ba dạng tác động dây chuyền phải phân biệt

### 3.1. “Mất chức năng trong im lặng” do `@ConditionalOnBean`

```java
@AutoConfiguration(after = FoundationAutoConfiguration.class)
public class DependentAutoConfiguration {

    @Bean
    @ConditionalOnBean(FoundationService.class)
    public DependentService dependentService(FoundationService foundation) {
        return new DependentService("uses:" + foundation.origin());
    }
}
```

Đây là đoạn minh họa, giả định các type đã được định nghĩa. Nếu không có bean `FoundationService` khi condition được đánh giá, Spring **không đăng ký** `dependentService`. Vì không có factory method cần được gọi, ứng dụng có thể khởi động thành công mà không còn `DependentService`.

Quan trọng: `@ConditionalOnBean` kiểm tra những bean definition đã được xử lý đến thời điểm đó. Trong auto-configuration, khai báo `after = FoundationAutoConfiguration.class` giúp cấu hình consumer được xử lý **sau** cấu hình provider, nhưng không bảo đảm khởi tạo instance theo thứ tự đó. Bean do người dùng khai báo thường được xử lý trước các auto-configuration.

### 3.2. “Khởi động thất bại” do phụ thuộc bắt buộc

```java
@Bean
StrictConsumerService strictConsumerService(
        FoundationService foundationService) {
    return new StrictConsumerService(
            "strict:" + foundationService.origin());
}
```

Khi bean này vẫn được đăng ký mà không còn `FoundationService`, Spring không thể resolve tham số bắt buộc. Một nguyên nhân gốc thường là `NoSuchBeanDefinitionException`, được bọc trong `UnsatisfiedDependencyException` hoặc ngoại lệ tạo bean tùy đường đi.

Việc thêm `@DependsOn("foundationService")` **không sửa được** bean đã vắng mặt. Nó chỉ yêu cầu bean theo tên phải khởi tạo trước; nếu không có bean tên đó, lỗi vẫn xảy ra.

### 3.3. “Đổi hành vi” do fallback hoặc phụ thuộc tùy chọn

Một consumer có thể chủ động xử lý việc bean nền vắng mặt:

```java
@Bean
ReportingService reportingService(
        ObjectProvider<FoundationService> provider) {
    FoundationService foundation = provider.getIfAvailable();
    return foundation == null
            ? new ReportingService("offline")
            : new ReportingService("online:" + foundation.origin());
}
```

Đây là đoạn minh họa với `ReportingService` chưa định nghĩa, yêu cầu import `org.springframework.beans.factory.ObjectProvider`. Consumer **vẫn đăng ký được**, nhưng chuyển sang chế độ `offline`. Điều này chỉ đúng nếu contract nghiệp vụ thực sự cho phép hoạt động thiếu nền tảng đó.

Ở cấu hình khác, `@ConditionalOnMissingBean(FoundationService.class)` có thể bắt đầu match và cung cấp fallback; cần kiểm tra xem fallback sử dụng đúng dữ liệu, môi trường, security policy hoặc transaction semantics hay không.

**Khởi động thành công không đủ để kết luận an toàn**: có thể mất một consumer, bật fallback không mong muốn hoặc chỉ lỗi khi có request/job đầu tiên.

## 4. Ví dụ chạy được với Spring Boot 3.3.5 và Java 17+

Ta xây một ứng dụng có hai auto-configuration:

- `FoundationAutoConfiguration` tạo `FoundationService("default")` khi ứng dụng chưa có bean cùng kiểu.
- `DependentAutoConfiguration` tạo `DependentService` **khi có** `FoundationService`; đồng thời có một `StrictConsumerService` được bật bằng property để mô phỏng trường hợp phụ thuộc bắt buộc.

Ứng dụng cũng cho phép khai báo bean nền custom. Ta chạy **cùng một JAR** với các lựa chọn exclude/custom để nhìn thấy ảnh hưởng dây chuyền trực tiếp.

### 4.1. Cấu trúc dự án

```text
cascade-check-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── demo/
    │   │       ├── api/
    │   │       │   ├── FoundationService.java
    │   │       │   ├── DependentService.java
    │   │       │   └── StrictConsumerService.java
    │   │       ├── app/
    │   │       │   └── DemoApplication.java
    │   │       └── autoconfigure/
    │   │           ├── FoundationAutoConfiguration.java
    │   │           └── DependentAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/demo/app/
            └── DependencyCascadeTests.java
```

Các lớp auto-configuration nằm **ngoài** package scan `demo.app` và được Spring Boot nạp qua file `AutoConfiguration.imports`. Cách này phản ánh cơ chế starter của Spring Boot 3.x, thay vì vô tình component-scan các lớp auto-configuration.

### 4.2. `pom.xml`

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
    <artifactId>cascade-check-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 4.3. Ba kiểu dữ liệu trong `demo.api`

**`src/main/java/demo/api/FoundationService.java`**

```java
package demo.api;

public record FoundationService(String origin) {
}
```

**`src/main/java/demo/api/DependentService.java`**

```java
package demo.api;

public record DependentService(String description) {
}
```

**`src/main/java/demo/api/StrictConsumerService.java`**

```java
package demo.api;

public record StrictConsumerService(String description) {
}
```

Ta dùng `record` của Java 17 để kết quả dễ quan sát. Các record không tự chứa logic Spring; việc tạo và liên kết bean nằm ở các lớp cấu hình.

### 4.4. Provider: `src/main/java/demo/autoconfigure/FoundationAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.api.FoundationService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class FoundationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(FoundationService.class)
    public FoundationService foundationService() {
        return new FoundationService("default");
    }
}
```

Bean mặc định có hai đặc điểm: phụ thuộc vào việc **auto-configuration được áp dụng**, và nhường chỗ nếu đã có một `FoundationService` phù hợp. Khi loại cả `FoundationAutoConfiguration`, phương thức factory này không còn cơ hội tạo default.

### 4.5. Consumer: `src/main/java/demo/autoconfigure/DependentAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.api.DependentService;
import demo.api.FoundationService;
import demo.api.StrictConsumerService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = FoundationAutoConfiguration.class)
public class DependentAutoConfiguration {

    @Bean
    @ConditionalOnBean(FoundationService.class)
    public DependentService dependentService(
            FoundationService foundationService) {
        return new DependentService(
                "uses:" + foundationService.origin());
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "strict",
            havingValue = "true")
    public StrictConsumerService strictConsumerService(
            FoundationService foundationService) {
        return new StrictConsumerService(
                "strict:" + foundationService.origin());
    }
}
```

Hai consumer có **cách đối phó khác nhau** với việc thiếu bean nền:

- `dependentService()` có `@ConditionalOnBean` nên tự **không đăng ký** khi không có bean nền.
- `strictConsumerService()` **chỉ** có điều kiện property `demo.strict=true`; khi property bật mà bean nền thiếu, Spring vẫn cố tạo bean và **thất bại do dependency bắt buộc**.

`@AutoConfiguration(after = FoundationAutoConfiguration.class)` sắp thứ tự xử lý bean definitions để `@ConditionalOnBean` thấy provider nếu provider có mặt. Nó **không** khiến Spring tự sinh `FoundationService` khi provider bị loại.

### 4.6. Đăng ký auto-configuration candidate

Tạo file chính xác tại **`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**:

```text
demo.autoconfigure.DependentAutoConfiguration
demo.autoconfigure.FoundationAutoConfiguration
```

Trong ví dụ, ta chủ ý liệt kê consumer trước provider trong file. Spring Boot sắp thứ tự ứng dụng auto-configuration theo metadata `after`; không lấy thứ tự khởi tạo bean từ vị trí của các dòng này.

### 4.7. Ứng dụng chính: `src/main/java/demo/app/DemoApplication.java`

```java
package demo.app;

import demo.api.DependentService;
import demo.api.FoundationService;
import demo.api.StrictConsumerService;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "provide-custom-foundation",
            havingValue = "true")
    public FoundationService customFoundationService() {
        return new FoundationService("custom");
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(DemoApplication.class, args)) {

            FoundationService foundation =
                    context.getBeanProvider(FoundationService.class)
                            .getIfAvailable();

            DependentService dependent =
                    context.getBeanProvider(DependentService.class)
                            .getIfAvailable();

            StrictConsumerService strict =
                    context.getBeanProvider(StrictConsumerService.class)
                            .getIfAvailable();

            System.out.println("foundation=" +
                    (foundation == null ? "none" : foundation.origin()));

            System.out.println("dependent=" +
                    (dependent == null ? "none" : dependent.description()));

            System.out.println("strict=" +
                    (strict == null ? "none" : strict.description()));
        }
    }
}
```

Bean do người dùng khai báo qua `customFoundationService()` chỉ xuất hiện khi `demo.provide-custom-foundation=true`. Nếu bean đó xuất hiện, `@ConditionalOnMissingBean(FoundationService.class)` trong provider auto-configuration sẽ nhường chỗ; nếu provider auto-configuration đã bị loại, bean custom vẫn tồn tại vì nó thuộc ứng dụng.

### 4.8. Build và chạy bốn kịch bản

Cần JDK 17+, Maven và kết nối tải dependencies cho lần build đầu. Tại thư mục `cascade-check-demo`:

```bash
mvn -q test
mvn -q -DskipTests package
```

**Kịch bản A — không exclude: provider và consumer mặc định đều có mặt**

```bash
java -jar target/cascade-check-demo-0.0.1-SNAPSHOT.jar --spring.main.banner-mode=off --logging.level.root=OFF
```

Dòng stdout của chương trình:

```text
foundation=default
dependent=uses:default
strict=none
```

`FoundationAutoConfiguration` tạo bean nền default; `DependentAutoConfiguration` thấy bean đó và cung cấp `DependentService`. Bean strict không đăng ký vì property chưa bật.

**Kịch bản B — exclude provider, không khai báo bean thay thế**

```bash
java -jar target/cascade-check-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=demo.autoconfigure.FoundationAutoConfiguration --spring.main.banner-mode=off --logging.level.root=OFF
```

Dòng stdout của chương trình:

```text
foundation=none
dependent=none
strict=none
```

`FoundationAutoConfiguration` bị loại, bean `FoundationService` không được cung cấp nơi nào khác. `@ConditionalOnBean` trên consumer không match nên `DependentService` cũng biến mất: đây là tác động **dây chuyền trong im lặng**. Ứng dụng vẫn khởi động thành công.

**Kịch bản C — exclude provider nhưng cung cấp bean nền custom**

```bash
java -jar target/cascade-check-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=demo.autoconfigure.FoundationAutoConfiguration --demo.provide-custom-foundation=true --spring.main.banner-mode=off --logging.level.root=OFF
```

Dòng stdout:

```text
foundation=custom
dependent=uses:custom
strict=none
```

Dù provider mặc định bị loại, ứng dụng vẫn cung cấp `FoundationService("custom")`, nên consumer có điều kiện tiếp tục hoạt động. Đây là ví dụ về **thay thế đúng contract thay vì chỉ xóa default**.

**Kịch bản D — exclude provider nhưng bật consumer bắt buộc**

```bash
java -jar target/cascade-check-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=demo.autoconfigure.FoundationAutoConfiguration --demo.strict=true --spring.main.banner-mode=off
```

**Kỳ vọng:** ứng dụng **không khởi động được**, do `strictConsumerService(FoundationService foundationService)` cần một bean mà context không có. Log khởi động thông thường sẽ báo lỗi tạo bean/không resolve được `FoundationService`, có thể có `UnsatisfiedDependencyException` và nguyên nhân sâu là `NoSuchBeanDefinitionException`. **Không cố định nguyên văn stack trace** vì thông báo và đường dẫn cause có thể thay đổi theo phiên bản môi trường.

Kịch bản này khác B: cùng thiếu bean nền nhưng B có thể khởi động còn D lỗi. Sự khác biệt nằm ở **hợp đồng dependency của từng consumer**, không nằm ở cơ chế exclude.

### 4.9. Ma trận kết quả

| Kịch bản | Provider default | Bean custom | `DependentService` | `StrictConsumerService` | Context |
| --- | --- | --- | --- | --- | --- |
| A. Mặc định | Có | Không | Có | Không (property false) | Khởi động |
| B. Exclude provider | Không | Không | Không (condition false) | Không (property false) | Khởi động, thiếu chức năng |
| C. Exclude + custom bean | Không | Có | Có, dùng custom | Không (property false) | Khởi động |
| D. Exclude + strict=true | Không | Không | Không | Factory cần bean thiếu | **Khởi động thất bại** |
| E. Không exclude + strict=true | Có | Không | Có | Có, dùng default | Khởi động |
| F. Exclude + custom + strict=true | Không | Có | Có, dùng custom | Có, dùng custom | Khởi động |

Hai kịch bản E/F là bước kiểm tra thêm để bảo đảm strict consumer không bị chính cấu hình của nó vô tình loại bỏ khi bean nền thực sự tồn tại.

## 5. Kiểm thử tự động tác động dây chuyền bằng `ApplicationContextRunner`

Với starter, nên kiểm tra **các trạng thái bean quan trọng trong context**, thay vì chỉ assert chương trình có chạy hay không. `ApplicationContextRunner` giúp tạo context nhỏ với đúng tập auto-configuration và bean do người dùng cung cấp.

Phần sau là **một file test Java đầy đủ**, phù hợp với `spring-boot-starter-test` đã khai báo trong `pom.xml`. Tạo **`src/test/java/demo/app/DependencyCascadeTests.java`**:

```java
package demo.app;

import demo.api.DependentService;
import demo.api.FoundationService;
import demo.api.StrictConsumerService;
import demo.autoconfigure.DependentAutoConfiguration;
import demo.autoconfigure.FoundationAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class DependencyCascadeTests {

    private final ApplicationContextRunner bothAutoConfigs =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            FoundationAutoConfiguration.class,
                            DependentAutoConfiguration.class));

    @Test
    void bothPresentCreatesDependentService() {
        bothAutoConfigs.run(context -> {
            assertThat(context).hasSingleBean(FoundationService.class);
            assertThat(context).hasSingleBean(DependentService.class);
            assertThat(context).doesNotHaveBean(StrictConsumerService.class);

            assertThat(context.getBean(FoundationService.class).origin())
                    .isEqualTo("default");
            assertThat(context.getBean(DependentService.class).description())
                    .isEqualTo("uses:default");
        });
    }

    @Test
    void missingProviderAlsoRemovesConditionalConsumer() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        DependentAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(FoundationService.class);
                    assertThat(context).doesNotHaveBean(DependentService.class);
                    assertThat(context).hasNotFailed();
                });
    }

    @Test
    void customProviderRestoresConsumer() {
        bothAutoConfigs
                .withBean(FoundationService.class,
                        () -> new FoundationService("custom"))
                .run(context -> {
                    assertThat(context).hasSingleBean(FoundationService.class);
                    assertThat(context).hasSingleBean(DependentService.class);
                    assertThat(context.getBean(FoundationService.class).origin())
                            .isEqualTo("custom");
                    assertThat(context.getBean(DependentService.class)
                            .description())
                            .isEqualTo("uses:custom");
                });
    }

    @Test
    void requiredConsumerWithoutProviderFailsStartup() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        DependentAutoConfiguration.class))
                .withPropertyValues("demo.strict=true")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .isNotNull();
                });
    }

    @Test
    void requiredConsumerWithProviderStarts() {
        bothAutoConfigs
                .withPropertyValues("demo.strict=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(StrictConsumerService.class);
                    assertThat(context.getBean(StrictConsumerService.class)
                            .description())
                            .isEqualTo("strict:default");
                });
    }
}
```

Chạy:

```bash
mvn -q test
```

Khi cả năm test đều pass, ta đã kiểm tra các nhánh: mặc định, thiếu provider, custom provider, dependency bắt buộc gây lỗi và dependency bắt buộc có provider.

**Giới hạn cần hiểu rõ:** test “thiếu provider” ở trên mô phỏng hệ quả bằng cách **không đưa `FoundationAutoConfiguration` vào context**. Nó kiểm tra chính xác logic consumer khi bean nền vắng mặt, nhưng **không phải test tích hợp trực tiếp của property `spring.autoconfigure.exclude`**. Các lệnh chạy JAR ở mục 4.8 kiểm tra riêng đường đi exclude thật sự của `SpringApplication`. Hai loại kiểm thử bổ sung cho nhau.

Nếu cần test rộng hơn về cấu hình môi trường, auto-configuration import và startup path thật, dùng `@SpringBootTest` với các property/profile tách biệt hoặc chạy ứng dụng trong môi trường kiểm thử tích hợp, rồi kiểm tra bean và kết quả nghiệp vụ.

## 6. Quy trình rà soát dây chuyền trong dự án thực tế

Trước khi loại một bean nền hay cả auto-configuration, lập một bảng kiểm dựa trên **các consumer thực tế**:

### Bước 1 — xác định provider và contract

Ghi lại:

- **Bean nào** dự kiến biến mất: type, bean name, qualifier và interface hợp đồng.
- **Ai cung cấp**: auto-configuration nào, `@Bean` nào, hoặc cấu hình ứng dụng nào.
- **Điều kiện tạo**: `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean`, `@ConditionalOnBean`; điều kiện nằm ở cấp **class** hay từng **`@Bean`**.
- **Có đường thay thế không**: bean của người dùng, bean từ starter khác, fallback hoặc parent context.
- **Loại trừ bằng cách nào**: `@SpringBootApplication(exclude=...)`, `excludeName`, `spring.autoconfigure.exclude` hay tắt bằng property được starter cung cấp.

Không suy luận “loại bean X” từ tên của một lớp auto-configuration: lớp đó có thể tạo nhiều bean khác nhau, và một số bean là dependency nền cho phần còn lại.

### Bước 2 — đi theo cạnh phụ thuộc trực tiếp và gián tiếp

Kiểm tra từng consumer bằng các cơ chế sau:

| Consumer dùng bean nền như thế nào? | Khi bean nền mất | Kiểm chứng |
| --- | --- | --- |
| Constructor injection / tham số `@Bean` bắt buộc | Có thể lỗi tạo bean khi consumer còn được đăng ký | Test context failure và nguyên nhân gốc |
| `@ConditionalOnBean` | Bean/config consumer có thể không đăng ký | Assert vắng mặt và hậu quả nghiệp vụ |
| `@ConditionalOnSingleCandidate` | Có thể không match nếu không có đúng ứng viên phù hợp | Assert danh sách ứng viên và outcome |
| `@ConditionalOnMissingBean` | Fallback có thể bắt đầu được đăng ký | Assert loại bean và config default mới |
| `ObjectProvider` / `Optional` | Consumer có thể tự chuyển nhánh hoặc lỗi muộn khi lấy bean | Gọi cả nhánh có/không provider |
| `@DependsOn("name")` | Nếu bean tên được chỉ định không tồn tại, khởi tạo consumer có thể lỗi | Assert lifecycle và bean name chính xác |
| Consumer gọi `ApplicationContext.getBean(...)` trong runtime | Có thể khởi động rồi lỗi ở lần sử dụng | Integration test đường nghiệp vụ thực tế |
| Consumer còn điều kiện `@ConditionalOnClass` | Classpath không đổi khi exclude nên condition class có thể vẫn match | Xem bean conditions và dependencies thực tế |

Sau khi tìm được consumer B, xem **ai phụ thuộc vào B**. Đây là bước tìm **tác động bắc cầu** A → B → C. Ví dụ loại `FoundationService` khiến `DependentService` biến mất, kéo theo một `@ConditionalOnBean(DependentService.class)` khác không match nữa.

Không phải mọi cạnh quan hệ sẽ dẫn tới lỗi khởi động. Cần ghi rõ **bean bị bỏ có chủ ý**, **bean fallback mới**, **thay đổi hành vi**, **lỗi startup** hay **lỗi runtime**.

### Bước 3 — kiểm tra thứ tự đánh giá condition

Với `@ConditionalOnBean`/`@ConditionalOnMissingBean`, điều kiện được đánh giá dựa trên **những bean definitions đã được xử lý tới thời điểm đó**. Nếu provider và consumer ở các auto-configuration khác nhau, khai báo đúng metadata:

```java
@AutoConfiguration(after = FoundationAutoConfiguration.class)
public class DependentAutoConfiguration {
    // Bean conditions của consumer.
}
```

Metadata `after` giúp condition của consumer thấy provider khi provider auto-configuration có mặt. Tuy nhiên nó **không biến một provider đã bị exclude thành provider đang tồn tại** và không bảo đảm thứ tự tạo instance.

Nếu việc thiếu bean vẫn xảy ra dù đã khai báo provider, kiểm tra thêm return type khai báo của `@Bean`, generic types, tên/qualifier, điều kiện khác và context hierarchy. Một bean implementation tồn tại ở Java source không có nghĩa bean definition của nó đã được đăng ký.

### Bước 4 — chạy ma trận trước và sau thay đổi

Ít nhất cần phân biệt:

1. Baseline: bean nền mặc định có mặt.
2. Exclude: provider mặc định vắng mặt, không có replacement.
3. Custom: bean nền custom có mặt, auto-configuration vẫn bật nhưng default nhường chỗ.
4. Exclude + custom: không còn provider mặc định nhưng vẫn có bean theo contract.
5. Cấu hình consumer bắt buộc/optional tương ứng.
6. Đường nghiệp vụ thực tế: request, scheduled job hoặc message handler vẫn chạy đúng chức năng mong muốn.

Đối với mỗi dòng, ghi **context có khởi động không**, **số bean theo type/name**, **condition nào match**, **consumer nào xuất hiện**, **fallback nào xuất hiện** và **kết quả nghiệp vụ**. Đừng chỉ assert không có exception.

### Bước 5 — dùng báo cáo condition để tìm nguyên nhân

Để xem **Condition Evaluation Report**, có thể khởi động Spring Boot với:

```bash
java -jar target/cascade-check-demo-0.0.1-SNAPSHOT.jar --debug
```

Khi dùng Spring Boot Actuator và endpoint được cấu hình phù hợp, có thể xem thông tin điều kiện qua endpoint `/actuator/conditions`. Endpoint này **không mặc định đồng nghĩa được phép truy cập công khai**; cần cấu hình exposure và bảo mật theo ứng dụng.

Tìm trong báo cáo:

- Provider auto-configuration bị exclude hay chỉ condition không match?
- `@ConditionalOnBean` ở consumer không match vì không thấy bean nào?
- `@ConditionalOnMissingBean` của một fallback mới bắt đầu match?
- Cấu hình khác có vẫn match `@ConditionalOnClass` nhưng fail vì thiếu dependency thật?
- Bean custom đã đăng ký đúng type/name/qualifier chưa?

Phân biệt **“negative match của condition”** (hành vi lọc đăng ký bình thường) với **“bean creation failure”** (lỗi tạo instance khi dependency không resolve được). Không đánh đồng hai trường hợp dù cùng có nguyên nhân sâu là thiếu foundation.

### Bước 6 — đưa các kiểm tra vào test thường xuyên

Một test suite cho starter nên bảo vệ ít nhất ba hợp đồng:

- **Back-off**: provider default nhường chỗ đúng khi có bean custom; không tạo thêm bean gây mơ hồ.
- **Graceful absence**: nếu foundation không bắt buộc, consumer không đăng ký hoặc chuyển fallback **có chủ đích**.
- **Required dependency**: nếu foundation là bắt buộc, một lỗi khởi động rõ ràng hoặc điều kiện kích hoạt chính xác xảy ra thay vì bỏ qua âm thầm.

Với dependency bắc cầu, kiểm tra cả downstream bean và hành vi sử dụng thật; tránh test chỉ assert một bean nền bị loại mà bỏ qua B/C đang cần nó.

## 7. Cách sửa khi phát hiện tác động không mong muốn

**Trường hợp A — chỉ muốn thay implementation nhưng vẫn cần hạ tầng.** Không exclude provider auto-configuration nếu nó còn tạo nhiều thành phần dùng chung. Hãy khai báo bean custom theo contract được hỗ trợ và cho default `@ConditionalOnMissingBean` nhường chỗ. Kiểm tra bean count để tránh nhiều ứng viên cùng kiểu.

**Trường hợp B — consumer thực sự không có ý nghĩa khi thiếu nền.** Đặt `@ConditionalOnBean(FoundationService.class)` tại đúng lớp/`@Bean` consumer. Nếu lớp chứa cả các bean khác không phụ thuộc foundation, đặt condition **trên từng bean cần thiết** để tránh mất thêm chức năng.

**Trường hợp C — consumer cần foundation để làm việc.** Giữ dependency injection bắt buộc và cung cấp foundation hợp lệ; có thể dùng `@ConditionalOnBean` để chỉ bật consumer khi dependency có mặt, nếu đó là hợp đồng thiết kế mong muốn. Không dùng `@Autowired(required=false)` hoặc fallback `null` tùy tiện chỉ để che lỗi cấu hình nghiêm trọng.

**Trường hợp D — cần chế độ hoạt động khi thiếu nền.** Thiết kế fallback minh bạch, có test riêng cho chế độ degraded. Cần quyết định liệu sử dụng fallback có thay đổi tính nhất quán dữ liệu, transaction, cache hoặc security hay không; tránh để `@ConditionalOnMissingBean` vô tình chọn một implementation không phù hợp production.

**Trường hợp E — cần tắt cả chức năng.** Exclude provider/consumer hoặc dùng property bật tắt do starter hỗ trợ; đánh giá phạm vi đầy đủ. Nếu lớp auto-configuration đang trộn bean nền và bean không liên quan, cân nhắc tách auto-configuration theo nhóm trách nhiệm để có thể tắt một nhóm mà không ảnh hưởng nhóm khác.

**Trường hợp F — “sửa” bằng `@DependsOn` hoặc `@Order` vẫn lỗi.** Kiểm tra lại bài toán: `@DependsOn` chỉ áp đặt quan hệ khởi tạo bean **đã có**, `@Order` chủ yếu sắp thứ tự ứng viên/callback; `@AutoConfiguration(after=...)` sắp thứ tự xử lý **định nghĩa bean**. Không công cụ nào tự tái tạo một bean đã bị exclude.

## 8. Những lỗi nhận định thường gặp

1. **“Exclude một auto-configuration thì mọi bean của cùng thư viện biến mất.”** Sai: các bean được tạo từ cấu hình ứng dụng, auto-configuration khác hoặc import khác có thể vẫn còn. Phải kiểm tra bean registry sau khởi động.
2. **“Đã khởi động được thì không có tác động dây chuyền.”** Sai: `@ConditionalOnBean` có thể làm consumer bị bỏ hoàn toàn, hoặc fallback có thể hoạt động mà không báo lỗi.
3. **“Có class trên classpath nghĩa là có bean.”** Sai: `@ConditionalOnClass` và `@ConditionalOnBean` kiểm tra hai điều kiện khác nhau; exclude auto-configuration không xóa file JAR dependency.
4. **“`@ConditionalOnMissingBean` luôn tìm toàn bộ bean có thể xuất hiện sau này.”** Sai: condition xét các bean definitions đã được xử lý; vì vậy thứ tự xử lý auto-configuration và khai báo return type rất quan trọng.
5. **“Loại provider rồi thêm `@DependsOn` ở consumer sẽ tự ổn.”** Sai: bean được phụ thuộc vẫn không tồn tại; `@DependsOn` không thay thế dependency hoặc bean definition.
6. **“Đổi bean name nhưng giữ type thì `@ConditionalOnBean` không thấy.”** Chưa chắc: condition thường so theo **type** nếu được khai báo bằng class; name/qualifier và type phải được kiểm tra theo đúng hợp đồng cụ thể.
7. **“Dùng bean optional luôn an toàn hơn bean bắt buộc.”** Không mặc nhiên: optional chỉ thay đổi lúc lỗi xuất hiện và nhánh thực thi; có thể che giấu việc mất hạ tầng thiết yếu.
8. **“Thay thế một default bean tức là phải loại cả auto-configuration.”** Không: nhiều starter chủ động hỗ trợ custom bean qua `@ConditionalOnMissingBean`; thay thế theo contract có thể giữ nguyên các consumer và hạ tầng khác.
9. **“Chỉ cần test provider mất.”** Chưa đủ: phải test consumer B/C, fallback, startup failure và hành vi nghiệp vụ chính.
10. **“Chỉ cần nhìn thứ tự source file.”** Sai: Spring Boot sắp thứ tự auto-configuration qua metadata, còn thứ tự khởi tạo bean dựa trên dependency graph. Cần phân biệt **bean definition availability** và **bean instance creation**.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Loại `FoundationAutoConfiguration` nhưng ứng dụng tự khai báo `FoundationService`. `@ConditionalOnBean(FoundationService.class)` ở consumer luôn false?  
**Trả lời:** Không. Nếu bean custom phù hợp đã được đăng ký khi condition đánh giá, condition vẫn có thể match.

**Câu 2.** Consumer dùng `@ConditionalOnBean`, ứng dụng chạy bình thường sau khi exclude provider. Như vậy không còn lỗi?  
**Trả lời:** Chưa đủ kết luận. Consumer có thể bị bỏ hoàn toàn; cần kiểm tra chức năng mà consumer đại diện và các downstream bean.

**Câu 3.** Một consumer có tham số factory `FoundationService foundationService` và không có condition, provider bị exclude. Điều gì có thể xảy ra?  
**Trả lời:** Consumer còn được đăng ký nhưng Spring không resolve được dependency, khiến context khởi động thất bại.

**Câu 4.** `@AutoConfiguration(after = FoundationAutoConfiguration.class)` có giúp tự tạo lại foundation sau khi exclude không?  
**Trả lời:** Không. Nó chỉ quy định thứ tự xử lý các auto-configuration candidate đang được áp dụng.

**Câu 5.** Muốn thay implementation của bean nền mà không mất các bean khác, nên kiểm tra khả năng nào trước?  
**Trả lời:** API/properties tùy chỉnh của starter và cơ chế `@ConditionalOnMissingBean` cho phép bean custom thay thế default.

**Câu 6.** Vì sao test với `ApplicationContextRunner` và test chạy JAR với `spring.autoconfigure.exclude` cùng cần thiết?  
**Trả lời:** Runner giúp cô lập điều kiện và dependency của từng bean; chạy JAR kiểm chứng đường đi thật của Spring Boot từ auto-configuration import và exclusion property.

## Tài liệu chính thức

- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html): cách tắt auto-configuration qua `exclude`, `excludeName` hoặc `spring.autoconfigure.exclude`.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): `AutoConfiguration.imports`, thứ tự `before`/`after`, bean conditions và cách test auto-configuration.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/index.html): `spring-boot-starter-test` và hạ tầng kiểm thử.
- [Spring Boot API — `@ConditionalOnBean`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html) và [`@ConditionalOnMissingBean`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): điều kiện theo bean đã được xử lý.
- [Spring Boot API — `@AutoConfiguration`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): metadata sắp thứ tự cấu hình.
