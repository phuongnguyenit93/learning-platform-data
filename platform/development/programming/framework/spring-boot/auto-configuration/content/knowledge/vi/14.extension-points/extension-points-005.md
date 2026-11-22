# Chọn `@ConditionalOnSingleCandidate` khi cấu hình chỉ hỗ trợ một thành phần nền

## 1. Bài toán: có bean chưa đủ, cần biết có một ứng viên duy nhất hay không

Trong một ứng dụng Spring, có thể tồn tại nhiều bean cùng kiểu. Ví dụ, ứng dụng đăng ký hai `PaymentGateway` cho hai nhà cung cấp, hai `ObjectMapper` cho hai định dạng, hoặc nhiều `DataSource` cho các database khác nhau.

Một auto-configuration có thể cần đúng **một thành phần nền có thể được chọn khi inject theo kiểu**. Nếu không có bean nào, tính năng không thể hoạt động. Nếu có nhiều bean mà Spring không biết nên chọn bean nào, việc tạo consumer cũng không an toàn.

Spring Boot cung cấp:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnSingleCandidate;
```

`@ConditionalOnSingleCandidate` cho phép cấu hình/bean chỉ được đăng ký khi Spring **xác định được một ứng viên duy nhất** cho kiểu bean được chỉ định.

Điểm quan trọng: “một ứng viên” không nhất thiết có nghĩa “chỉ có đúng một bean definition”. Điều kiện có thể match trong hai trường hợp:

- Chỉ có **một bean phù hợp** với kiểu được kiểm tra.
- Có nhiều bean phù hợp, nhưng Spring xác định được **một bean `@Primary` duy nhất** để làm ứng viên mặc định khi inject theo kiểu.

Ngược lại, nếu có nhiều bean cùng kiểu và không có một primary duy nhất, điều kiện không match. Nếu không có bean phù hợp, điều kiện cũng không match.

Điều kiện này hữu ích khi một thành phần chỉ hỗ trợ **một backend mặc định**, một client nền, một serializer hoặc một implementation được chọn theo kiểu. Nó giúp tránh đăng ký consumer trong trạng thái mà dependency injection theo kiểu không thể xác định ứng viên.

## 2. Quy tắc match của `@ConditionalOnSingleCandidate`

### 2.1. Bảng trường hợp

Giả sử kiểu nền cần kiểm tra là `FoundationClient`.

| Bean `FoundationClient` đã đăng ký | Có ứng viên duy nhất? | Condition | Lý do |
| --- | --- | --- | --- |
| Không có bean | Không | **No match** | Không có thành phần nền để sử dụng |
| Một bean, không có `@Primary` | Có | **Match** | Chỉ một ứng viên |
| Hai bean, không có `@Primary` | Không | **No match** | Không thể chọn một ứng viên mặc định |
| Hai bean, đúng một bean `@Primary` | Có | **Match** | Bean primary là ứng viên mặc định |
| Nhiều bean, nhiều primary gây mơ hồ | Không xác định được duy nhất | **No match** | Không có một primary duy nhất để chọn |

`@ConditionalOnSingleCandidate` kiểm tra **bean definitions/candidates đã được đăng ký** khi condition được đánh giá. Nó không cần tạo tất cả object rồi mới đếm instance. Đây là một condition trong giai đoạn xử lý cấu hình của Spring Boot.

### 2.2. “Single candidate” không phải “single bean”

Ví dụ ứng dụng có:

```java
@Bean
@Primary
FoundationClient mainClient() {
    return new HttpFoundationClient("main");
}

@Bean
FoundationClient backupClient() {
    return new HttpFoundationClient("backup");
}
```

Giả sử `HttpFoundationClient` triển khai `FoundationClient`. Context có **hai bean** cùng kiểu, nhưng `mainClient` được đánh dấu `@Primary`. Khi một consumer inject đúng một tham số `FoundationClient`, Spring có thể chọn `mainClient`. Vì vậy, `@ConditionalOnSingleCandidate(FoundationClient.class)` có thể match.

`@Primary` không xóa `backupClient`, không làm collection chỉ còn một phần tử và không biến hai bean thành một bean. Nó chỉ xác định ứng viên ưu tiên cho những điểm inject đơn phù hợp.

Nếu consumer cần tất cả client, hãy inject `List<FoundationClient>` hoặc `Map<String, FoundationClient>`. Trong trường hợp đó, điều kiện single candidate thường không phải công cụ phù hợp, vì yêu cầu nghiệp vụ là **hỗ trợ nhiều ứng viên**.

### 2.3. Condition không tự chọn bean để truyền vào

`@ConditionalOnSingleCandidate` chỉ trả lời: **“Có thể xác định một ứng viên duy nhất cho kiểu này không?”** Nó không tự truyền object vào method, không tạo bean và không tự đánh dấu bean nào là primary.

Việc inject thực tế vẫn do Spring thực hiện:

```java
@Bean
@ConditionalOnSingleCandidate(FoundationClient.class)
FeatureService featureService(FoundationClient foundationClient) {
    return new FeatureService(foundationClient.id());
}
```

Khi có hai bean nhưng một bean là `@Primary`, condition có thể match và tham số `foundationClient` được inject từ primary bean. Khi có hai bean không primary, condition không match, nên phương thức `featureService()` không được dùng để đăng ký bean.

Nếu một method có qualifier cụ thể, hãy xem xét cả hợp đồng qualifier của injection point. Không dựa vào `@ConditionalOnSingleCandidate` để thay thế một chính sách chọn bean theo tên hoặc theo tenant. Condition kiểm tra khả năng xác định một candidate theo kiểu; nếu nghiệp vụ cần chọn rõ `mainClient` hay `backupClient`, dùng `@Qualifier` hoặc cấu hình tường minh.

## 3. Phân biệt với các condition và annotation gần nghĩa

### 3.1. `@ConditionalOnBean` — có ít nhất một bean phù hợp

`@ConditionalOnBean` kiểm tra sự tồn tại của bean phù hợp. Nó không khẳng định rằng chỉ có một ứng viên để inject theo kiểu.

```java
@Bean
@ConditionalOnBean(FoundationClient.class)
ClientRegistry clientRegistry() {
    return new ClientRegistry();
}
```

Nếu có một hoặc nhiều bean `FoundationClient`, điều kiện tồn tại bean có thể match. Tuy nhiên, nếu một bean khác có tham số `FoundationClient` đơn và context có hai ứng viên không primary, method đó vẫn có thể lỗi khi Spring tạo bean.

Chọn `@ConditionalOnBean` khi tính năng chỉ cần **ít nhất một bean tồn tại**, hoặc consumer tự quản lý nhiều ứng viên. Chọn `@ConditionalOnSingleCandidate` khi consumer cần **một ứng viên duy nhất có thể inject theo kiểu**.

### 3.2. `@ConditionalOnMissingBean` — default nhường chỗ khi đã có bean

`@ConditionalOnMissingBean` giải quyết một câu hỏi khác: **“Đã có bean phù hợp để thay thế default chưa?”**

```java
@Bean
@ConditionalOnMissingBean(FoundationClient.class)
FoundationClient defaultFoundationClient() {
    return new HttpFoundationClient("default");
}
```

Nếu ứng dụng đã khai báo một hoặc nhiều `FoundationClient`, default có thể nhường chỗ. Condition này rất phổ biến trong starter để người dùng thay implementation.

Nhưng khi người dùng khai báo **hai** `FoundationClient` không primary, default vẫn có thể nhường chỗ trong khi một consumer cần single candidate lại không được đăng ký. Vì vậy, “default đã nhường chỗ” không đồng nghĩa “mọi consumer đều có thể hoạt động”.

### 3.3. `@Primary` — ưu tiên một bean khi inject đơn

`@Primary` là metadata cho quá trình chọn ứng viên trong dependency injection. Nó không tự kiểm tra điều kiện tạo bean và không loại bỏ bean khác.

Ví dụ:

```java
@Bean
@Primary
FoundationClient primaryClient() {
    return new HttpFoundationClient("primary");
}
```

Khi có nhiều `FoundationClient`, bean primary có thể làm cho `@ConditionalOnSingleCandidate` match. Nếu chỉ có một bean, không cần `@Primary`.

### 3.4. `@Qualifier` — chọn theo nhãn/ngữ nghĩa cụ thể

`@Qualifier` cho phép một injection point chọn một bean trong nhóm theo qualifier:

```java
@Bean
FeatureService featureService(
        @Qualifier("backupClient") FoundationClient client) {
    return new FeatureService(client.id());
}
```

Đoạn trên là ví dụ về dependency injection theo qualifier, không phải cách thay thế condition single-candidate. Nếu tính năng luôn dùng `backupClient`, nó không cần một “ứng viên mặc định duy nhất” theo kiểu; nó cần một bean có qualifier cụ thể. Thiết kế condition và dependency theo đúng hợp đồng đó.

### 3.5. Bảng so sánh tổng hợp

| Cơ chế | Câu hỏi | Hai bean cùng kiểu, không primary |
| --- | --- | --- |
| `@ConditionalOnBean` | Có bean phù hợp hay không? | Thường **match** |
| `@ConditionalOnSingleCandidate` | Có thể xác định một candidate duy nhất không? | **No match** |
| `@ConditionalOnMissingBean` | Chưa có bean phù hợp để default nhường chỗ? | **No match** đối với default |
| `@Primary` | Bean nào được ưu tiên khi inject đơn? | Không tự giải quyết nếu không có primary duy nhất |
| `@Qualifier` | Injection point cần bean có qualifier nào? | Có thể chọn rõ bean được chỉ định |

## 4. Đặt condition ở cấp class hay từng `@Bean`?

### 4.1. Cấp class: toàn bộ nhóm cấu hình cần một ứng viên duy nhất

```java
@AutoConfiguration
@ConditionalOnSingleCandidate(FoundationClient.class)
public class FoundationFeatureAutoConfiguration {

    @Bean
    public FeatureService featureService(FoundationClient client) {
        return new FeatureService(client.id());
    }

    @Bean
    public FeatureMetrics featureMetrics() {
        return new FeatureMetrics();
    }
}
```

Đây là đoạn minh họa; các kiểu `FoundationClient`, `FeatureService` và `FeatureMetrics` cần được định nghĩa. Nếu không xác định được một candidate duy nhất, **toàn bộ** `FoundationFeatureAutoConfiguration` không được áp dụng. Cả `FeatureService` lẫn `FeatureMetrics` đều không được cung cấp từ lớp này.

Dùng cấp class khi **mọi bean trong nhóm đều chỉ có ý nghĩa nếu có một foundation duy nhất**. Nếu `FeatureMetrics` có thể hoạt động độc lập, đặt condition ở cấp class sẽ vô tình loại cả metrics.

### 4.2. Cấp method: chỉ bean phụ thuộc single candidate bị điều kiện

```java
@AutoConfiguration
public class SharedFeatureAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(FoundationClient.class)
    public FeatureService featureService(FoundationClient client) {
        return new FeatureService(client.id());
    }

    @Bean
    public FeatureMetrics featureMetrics() {
        return new FeatureMetrics();
    }
}
```

Trong ví dụ này, `featureService` chỉ xuất hiện khi có một candidate duy nhất. `featureMetrics` vẫn được đăng ký trong cả trường hợp không có client, hoặc có nhiều client mơ hồ, nếu không có condition khác ngăn nó.

**Quy tắc chọn vị trí:** đặt điều kiện tại phạm vi nhỏ nhất bao phủ đúng những bean cần cùng một điều kiện. Đừng đặt ở class chỉ để giảm số annotation nếu lớp đó chứa nhiều bean có mức phụ thuộc khác nhau.

### 4.3. Kết hợp với back-off trong starter

Một starter thường cần hai việc:

1. Cung cấp default foundation nếu ứng dụng chưa có client.
2. Chỉ bật feature nếu Spring có thể xác định một client duy nhất.

Có thể tách thành hai auto-configuration:

```java
@AutoConfiguration
public class FoundationClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(FoundationClient.class)
    public FoundationClient foundationClient() {
        return new HttpFoundationClient("default");
    }
}
```

```java
@AutoConfiguration(after = FoundationClientAutoConfiguration.class)
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(FoundationClient.class)
    public FeatureService featureService(FoundationClient client) {
        return new FeatureService(client.id());
    }
}
```

Cấu hình provider được xử lý trước consumer để bean definition mặc định có cơ hội được đăng ký trước khi single-candidate condition được đánh giá. Nếu ứng dụng có một client custom, default nhường chỗ và feature dùng client đó. Nếu ứng dụng có nhiều client custom nhưng không có primary, default nhường chỗ nhưng feature cũng không match.

`@AutoConfiguration(after = ...)` điều khiển **thứ tự xử lý auto-configuration**, còn `@ConditionalOnSingleCandidate` kiểm tra candidate hiện có. Hai cơ chế bổ trợ nhau, không thay thế nhau.

## 5. Ví dụ chạy được với Spring Boot 3.3.5 và Java 17+

Ví dụ xây một starter giả lập có `FoundationClient` và `FeatureService`. Ứng dụng có thể khởi động ở bốn trạng thái:

- **Default:** chỉ có một client mặc định.
- **Primary:** có hai client custom, một client được đánh dấu `@Primary`.
- **Ambiguous:** có hai client custom, không có primary.
- **No provider:** loại auto-configuration tạo client mặc định và không khai báo client custom.

Ta quan sát số bean client và việc `FeatureService` có được đăng ký hay không.

### 5.1. Cấu trúc thư mục

```text
single-candidate-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── api/
    │   │   │   ├── FoundationClient.java
    │   │   │   └── FeatureService.java
    │   │   ├── app/
    │   │   │   └── DemoApplication.java
    │   │   └── autoconfigure/
    │   │       ├── FoundationClientAutoConfiguration.java
    │   │       └── FeatureAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/demo/app/
        └── SingleCandidateConditionTests.java
```

### 5.2. `pom.xml`

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
    <artifactId>single-candidate-demo</artifactId>
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

### 5.3. `src/main/java/demo/api/FoundationClient.java`

```java
package demo.api;

public interface FoundationClient {
    String id();
}
```

### 5.4. `src/main/java/demo/api/FeatureService.java`

```java
package demo.api;

public record FeatureService(String description) {
}
```

### 5.5. `src/main/java/demo/autoconfigure/FoundationClientAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.api.FoundationClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class FoundationClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(FoundationClient.class)
    public FoundationClient foundationClient() {
        return () -> "default";
    }
}
```

Khi không có `FoundationClient` nào do ứng dụng cung cấp, default này được đăng ký. Khi ứng dụng khai báo một hoặc nhiều client custom, default nhường chỗ để không tạo thêm một candidate không được yêu cầu.

### 5.6. `src/main/java/demo/autoconfigure/FeatureAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.api.FeatureService;
import demo.api.FoundationClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnSingleCandidate;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = FoundationClientAutoConfiguration.class)
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(FoundationClient.class)
    public FeatureService featureService(FoundationClient client) {
        return new FeatureService("uses:" + client.id());
    }
}
```

Bean `FeatureService` chỉ được tạo nếu có một candidate duy nhất. Tham số `FoundationClient client` dùng chính quy tắc chọn candidate của Spring; khi có hai bean nhưng một bean primary, client primary được truyền vào.

### 5.7. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
demo.autoconfigure.FeatureAutoConfiguration
demo.autoconfigure.FoundationClientAutoConfiguration
```

Hai lớp được đăng ký là auto-configuration candidate. File cố ý đặt consumer trước provider để minh họa rằng Spring Boot xử lý metadata `after` thay vì lấy thứ tự dòng trong file làm hợp đồng phụ thuộc. Tên lớp phải là fully-qualified class name chính xác.

### 5.8. `src/main/java/demo/app/DemoApplication.java`

```java
package demo.app;

import demo.api.FeatureService;
import demo.api.FoundationClient;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@SpringBootApplication
public class DemoApplication {

    @Bean
    @Primary
    @ConditionalOnProperty(
            prefix = "demo",
            name = "clients",
            havingValue = "primary")
    public FoundationClient primaryClient() {
        return () -> "primary";
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "clients",
            havingValue = "primary")
    public FoundationClient secondaryClient() {
        return () -> "secondary";
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "clients",
            havingValue = "ambiguous")
    public FoundationClient clientA() {
        return () -> "A";
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "clients",
            havingValue = "ambiguous")
    public FoundationClient clientB() {
        return () -> "B";
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(DemoApplication.class, args)) {

            int clientCount =
                    context.getBeansOfType(FoundationClient.class).size();

            FeatureService feature =
                    context.getBeanProvider(FeatureService.class)
                            .getIfAvailable();

            System.out.println("clients=" + clientCount);
            System.out.println("feature=" +
                    (feature == null ? "none" : feature.description()));
        }
    }
}
```

Các bean custom được tạo bởi cấu hình của ứng dụng. Trong chế độ `primary`, `primaryClient` và `secondaryClient` cùng tồn tại, nhưng chỉ `primaryClient` có `@Primary`. Trong chế độ `ambiguous`, `clientA` và `clientB` không có primary.

### 5.9. Build và chạy bốn kịch bản

Cần JDK 17+, Maven và kết nối tải dependencies khi build lần đầu. Tại thư mục `single-candidate-demo`:

```bash
mvn -q -DskipTests package
```

**Kịch bản A — chỉ có default client**

```bash
java -jar target/single-candidate-demo-0.0.1-SNAPSHOT.jar --spring.main.banner-mode=off --logging.level.root=OFF
```

Dòng output do ứng dụng in:

```text
clients=1
feature=uses:default
```

Chỉ có một `FoundationClient` mặc định, nên condition match và `FeatureService` sử dụng client đó.

**Kịch bản B — hai client custom, một primary**

```bash
java -jar target/single-candidate-demo-0.0.1-SNAPSHOT.jar --demo.clients=primary --spring.main.banner-mode=off --logging.level.root=OFF
```

Output:

```text
clients=2
feature=uses:primary
```

Default nhường chỗ vì ứng dụng đã cung cấp client. Có hai bean nhưng một bean primary, nên Spring xác định được candidate duy nhất; feature được đăng ký và inject `primaryClient`.

**Kịch bản C — hai client custom, không primary**

```bash
java -jar target/single-candidate-demo-0.0.1-SNAPSHOT.jar --demo.clients=ambiguous --spring.main.banner-mode=off --logging.level.root=OFF
```

Output:

```text
clients=2
feature=none
```

Default vẫn nhường chỗ vì đã có client. Nhưng không có primary duy nhất và có hai ứng viên, nên `@ConditionalOnSingleCandidate` không match; `FeatureService` không được đăng ký. Ứng dụng vẫn khởi động thành công vì bean feature có điều kiện.

**Kịch bản D — loại provider mặc định, không có client thay thế**

```bash
java -jar target/single-candidate-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=demo.autoconfigure.FoundationClientAutoConfiguration --spring.main.banner-mode=off --logging.level.root=OFF
```

Output:

```text
clients=0
feature=none
```

Không còn client nền và cũng không có consumer phụ thuộc được tạo. Đây là hành vi an toàn nếu feature là tùy chọn. Nếu một bean khác vẫn inject `FoundationClient` bắt buộc mà không có condition bảo vệ, context có thể thất bại khi khởi động.

## 6. Kiểm thử bằng `ApplicationContextRunner`

Một starter nên kiểm tra các trường hợp: không có client, một client, nhiều client không primary, nhiều client có primary. `ApplicationContextRunner` giúp xác nhận condition và bean kết quả trong context nhỏ, không cần khởi động toàn bộ ứng dụng.

Tạo file **`src/test/java/demo/app/SingleCandidateConditionTests.java`**:

```java
package demo.app;

import demo.api.FeatureService;
import demo.api.FoundationClient;
import demo.autoconfigure.FeatureAutoConfiguration;
import demo.autoconfigure.FoundationClientAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import static org.assertj.core.api.Assertions.assertThat;

class SingleCandidateConditionTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            FoundationClientAutoConfiguration.class,
                            FeatureAutoConfiguration.class));

    @Test
    void oneDefaultClientIsSingleCandidate() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(FoundationClient.class);
            assertThat(context).hasSingleBean(FeatureService.class);
            assertThat(context.getBean(FeatureService.class).description())
                    .isEqualTo("uses:default");
        });
    }

    @Test
    void multipleClientsWithPrimaryHaveSingleCandidate() {
        runner.withUserConfiguration(PrimaryClients.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(FoundationClient.class))
                            .hasSize(2);
                    assertThat(context).hasSingleBean(FeatureService.class);
                    assertThat(context.getBean(FeatureService.class).description())
                            .isEqualTo("uses:primary");
                });
    }

    @Test
    void multipleClientsWithoutPrimaryHaveNoSingleCandidate() {
        runner.withUserConfiguration(AmbiguousClients.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(FoundationClient.class))
                            .hasSize(2);
                    assertThat(context).doesNotHaveBean(FeatureService.class);
                });
    }

    @Test
    void noClientMeansFeatureIsNotRegistered() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        FeatureAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(FoundationClient.class);
                    assertThat(context).doesNotHaveBean(FeatureService.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class PrimaryClients {

        @Bean
        @Primary
        FoundationClient primaryClient() {
            return () -> "primary";
        }

        @Bean
        FoundationClient secondaryClient() {
            return () -> "secondary";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AmbiguousClients {

        @Bean
        FoundationClient clientA() {
            return () -> "A";
        }

        @Bean
        FoundationClient clientB() {
            return () -> "B";
        }
    }
}
```

Chạy toàn bộ test:

```bash
mvn -q test
```

Bốn test bảo vệ các hợp đồng quan trọng:

- Một bean duy nhất: condition match.
- Hai bean và một primary: condition match, inject primary.
- Hai bean không primary: condition không match, context vẫn chạy.
- Không có bean: condition không match, feature không xuất hiện.

Test này kiểm tra trực tiếp **logic condition trong context**. Các lệnh chạy JAR ở mục 5.9 bổ sung kiểm thử đường khởi động thực tế với property `spring.autoconfigure.exclude` và bean tùy chỉnh của ứng dụng.

## 7. Cách dùng trong auto-configuration thực tế

### 7.1. Khi nên chọn `@ConditionalOnSingleCandidate`

Nên cân nhắc khi một tính năng:

- Chỉ hỗ trợ một `DataSource` mặc định và không biết tự định tuyến giữa nhiều datasource.
- Tạo một adapter cần một `CacheManager` duy nhất được chọn.
- Cung cấp service phụ thuộc vào một `ObjectMapper` mặc định.
- Cần một client chung và cho phép ứng dụng đánh dấu client ưu tiên bằng `@Primary`.
- Chỉ có một backend được hỗ trợ tại một thời điểm; nhiều backend không primary là cấu hình chưa rõ ràng.

### 7.2. Khi không nên dùng

Không dùng condition này nếu:

- Consumer được thiết kế để làm việc với **nhiều backend** và có thể nhận `List<T>`/`Map<String,T>`.
- Tính năng luôn dùng một bean cụ thể theo `@Qualifier` hoặc theo property.
- Chỉ cần biết có ít nhất một bean; `@ConditionalOnBean` phù hợp hơn.
- Đang tạo default và muốn nhường chỗ khi ứng dụng đã khai báo bean; `@ConditionalOnMissingBean` đúng mục tiêu hơn.
- Nhiều candidate là trạng thái hợp lệ nhưng chưa có primary vì thiết kế sử dụng định tuyến theo tenant/request. Khi đó cần cơ chế routing rõ ràng, không nên ép một primary giả chỉ để condition match.

### 7.3. Phân biệt điều kiện ở cấp class và method trong starter

Một cấu hình có thể tạo hai bean:

- `FeatureService` cần một `FoundationClient` duy nhất.
- `FeatureHealthIndicator` chỉ cần biết hệ thống có ít nhất một `FoundationClient` để hiển thị trạng thái tổng quát.

Nếu gắn `@ConditionalOnSingleCandidate` ở cấp class, `FeatureHealthIndicator` cũng bị loại khi có hai client không primary. Có thể đây là hành vi sai nếu health indicator có thể kiểm tra cả hai.

Thiết kế phù hợp hơn:

```java
@AutoConfiguration
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(FoundationClient.class)
    public FeatureService featureService(FoundationClient client) {
        return new FeatureService(client.id());
    }

    @Bean
    @ConditionalOnBean(FoundationClient.class)
    public FeatureHealthIndicator featureHealthIndicator(
            ObjectProvider<FoundationClient> clients) {
        return new FeatureHealthIndicator(clients.stream().count());
    }
}
```

Đây là ví dụ thiết kế, giả định các kiểu `FeatureService` và `FeatureHealthIndicator` tồn tại. Bean đầu yêu cầu một candidate đơn; bean thứ hai có thể xử lý một tập hợp client. Condition và cách inject cần nhất quán với yêu cầu của từng thành phần.

## 8. Các lỗi thường gặp và cách chẩn đoán

1. **Nhầm “một candidate” với “một bean”.** Có hai bean nhưng một bean primary vẫn có thể match. Hãy kiểm tra bean count và primary metadata.
2. **Cho rằng `@Primary` loại bỏ bean phụ.** Không. Bean phụ vẫn tồn tại; collection injection vẫn có thể nhận cả hai. `@Primary` chỉ chọn ứng viên ưu tiên trong các điểm inject đơn phù hợp.
3. **Dùng `@ConditionalOnBean` rồi inject một tham số đơn khi có nhiều ứng viên.** Condition có thể match dù dependency injection sau đó mơ hồ. Nếu consumer bắt buộc một candidate, dùng `@ConditionalOnSingleCandidate`.
4. **Dùng `@ConditionalOnSingleCandidate` để tạo default.** Đây không phải condition back-off. Default bean thường dùng `@ConditionalOnMissingBean`; consumer mới là nơi cần kiểm tra candidate duy nhất.
5. **Đặt condition quá rộng ở cấp class.** Một bean cần single candidate có thể khiến các bean độc lập khác biến mất. Chuyển condition xuống đúng method.
6. **Cho rằng qualifier tự làm condition match.** Qualifier giúp chọn bean ở một injection point cụ thể. Condition single-candidate kiểm tra khả năng xác định candidate theo kiểu và primary; đừng dùng nó thay cho một chính sách chọn bean theo tên/tenant.
7. **Quên thứ tự xử lý auto-configuration.** Nếu provider là auto-configuration khác, dùng `@AutoConfiguration(after = ProviderAutoConfiguration.class)` khi consumer condition cần thấy bean definition của provider. `after` không tạo bean nếu provider bị exclude.
8. **Kiểm tra condition sau khi bean đã khởi tạo.** Condition đánh giá metadata bean trong quá trình xử lý cấu hình, không phải phép đếm object được gọi sau mỗi request.
9. **Chỉ test ứng dụng mặc định.** Một test với một bean không phát hiện lỗi khi có hai bean. Cần test zero, one, multiple-with-primary và multiple-without-primary.
10. **Thêm `@Primary` để che sự mơ hồ không được thiết kế.** Chỉ đánh dấu primary nếu đó thực sự là ứng viên mặc định theo nghiệp vụ. Nếu ứng dụng cần định tuyến rõ ràng giữa nhiều backend, tạo router/selector thay vì ép một bean thắng.

Khi condition không match như dự kiến, bật `--debug` để xem Condition Evaluation Report. Kiểm tra lớp auto-configuration có được import không, bean definition có được đăng ký trước khi condition chạy không, kiểu bean có đúng không và có một primary duy nhất không. Nếu ứng dụng đã khởi động nhưng feature vắng mặt, đó có thể là **negative match có chủ ý**, không phải lỗi tạo bean.

## 9. Quy tắc nhớ nhanh

- **Không có bean:** `@ConditionalOnSingleCandidate` không match.
- **Một bean:** match, không cần `@Primary`.
- **Nhiều bean, một primary:** match; injection đơn có thể chọn primary.
- **Nhiều bean, không có primary duy nhất:** không match.
- **Chỉ cần ít nhất một bean:** cân nhắc `@ConditionalOnBean`.
- **Cung cấp default nếu chưa có bean:** dùng `@ConditionalOnMissingBean`.
- **Chọn một bean theo tên/nhãn cụ thể:** dùng `@Qualifier` và cấu hình phù hợp.
- **Điều kiện chỉ áp dụng cho một bean:** đặt trên method `@Bean`; chỉ đặt trên class khi mọi bean trong lớp cần cùng điều kiện.

Câu hỏi tự kiểm tra cuối cùng: **“Tính năng này cần một bean bất kỳ, cần đúng một ứng viên có thể inject theo kiểu, hay cần một bean cụ thể theo qualifier?”** Trả lời đúng câu hỏi đó sẽ giúp chọn condition phù hợp và tránh làm mất chức năng khi ứng dụng mở rộng thêm backend.

## Tài liệu chính thức

- [Spring Boot 3.3 — `@ConditionalOnSingleCandidate` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html): quy tắc match khi một candidate có thể được xác định.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): bean conditions, thứ tự auto-configuration, `AutoConfiguration.imports` và kiểm thử.
- [Spring Boot 3.3 — `@ConditionalOnBean` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html): kiểm tra sự tồn tại của bean.
- [Spring Boot 3.3 — `@ConditionalOnMissingBean` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): cơ chế back-off cho default bean.
- [Spring Framework 6.1 — `@Primary` API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Primary.html): chọn bean ưu tiên khi có nhiều ứng viên cho injection point đơn.
- [Spring Framework — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html): collection injection, qualifier và quy tắc chọn bean.
