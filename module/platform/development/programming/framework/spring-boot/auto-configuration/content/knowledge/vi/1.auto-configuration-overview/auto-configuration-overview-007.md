# Phạm vi tự cấu hình khi xây ứng dụng và khi phát triển thư viện dùng chung

> Ngữ cảnh: Spring Boot 3.3.x, Java 17+. Chủ đề thuộc phần **Bức tranh tự cấu hình**. Ví dụ dưới đây dùng Spring Boot 3.3.13 để minh họa API của nhánh 3.3; khi triển khai hệ thống thật, chọn phiên bản Spring Boot còn được hỗ trợ và kiểm tra tương thích thư viện.

## 1. Kết quả cần nắm

Sau bài này, bạn cần phân biệt hai vai trò:
- **Người xây ứng dụng**: sử dụng những auto-configuration có sẵn, cung cấp cấu hình và bean riêng khi cần, kiểm soát cấu hình nào được áp dụng.
- **Người phát triển thư viện dùng chung**: cung cấp một auto-configuration có điều kiện để ứng dụng khác nhận được cấu hình mặc định khi thêm dependency, nhưng vẫn có thể điều chỉnh hoặc thay thế.

Điểm quyết định là **quyền sở hữu cấu hình**. Ứng dụng quyết định bean và hành vi cuối cùng của chính nó; thư viện chỉ nên cung cấp mặc định an toàn khi đủ điều kiện.

## 2. Auto-configuration thực sự làm gì?

Khi khởi động một ứng dụng có `@SpringBootApplication` (bao gồm `@EnableAutoConfiguration`), Spring Boot tìm các lớp auto-configuration được công bố trong dependency, xét các điều kiện của chúng rồi đăng ký các bean phù hợp. Những điều kiện thường gặp dựa trên classpath, bean đã có, thuộc tính cấu hình và loại ứng dụng.

```text
Ứng dụng khai báo dependency + application.properties + @Bean riêng
                              |
                              v
@SpringBootApplication -> chọn auto-configuration candidates
                              |
                              v
            Đánh giá điều kiện (class / bean / property / web)
                              |
                +-------------+-------------+
                |                           |
            khớp điều kiện             không khớp
                |                           |
       đăng ký bean mặc định       bỏ qua cấu hình đó
                |
      ApplicationContext thực tế
```

Ví dụ quen thuộc: có `spring-boot-starter-jdbc` và driver JDBC thích hợp thì Boot có thể cấu hình `DataSource` và các bean JDBC liên quan, tùy vào thuộc tính và các bean hiện có. Nếu ứng dụng tự khai báo một `DataSource` phù hợp, cấu hình mặc định tương ứng thường **back off** (nhường chỗ). Không thể suy ra rằng chỉ cần một dependency là mọi bean liên quan chắc chắn xuất hiện: điều kiện khác vẫn có thể không đạt.

Cần tách ba cơ chế:
- **Component scanning** tìm `@Component`, `@Service`, `@Configuration`... trong phạm vi package mà ứng dụng quét.
- **Auto-configuration** nhập các cấu hình đã được khai báo làm ứng viên rồi lọc bằng condition; không phải quét ngẫu nhiên mọi class trong mọi JAR.
- **`@ConfigurationProperties`** ánh xạ giá trị từ `Environment` vào object cấu hình; bản thân annotation này không đủ để bean chứa properties được đăng ký nếu chưa có cơ chế kích hoạt tương ứng.

## 3. Phạm vi trách nhiệm khi bạn xây một ứng dụng

Ứng dụng là nơi định nghĩa yêu cầu nghiệp vụ, kết nối thật, security policy, bộ nhớ đệm, vận hành và cách tùy biến cuối cùng. Vì vậy, thông thường bạn:

1. **Chọn starter/dependency** tương ứng tính năng cần dùng; hiểu starter mang vào classpath những thư viện nào.
2. **Cấu hình qua properties** khi Boot đã có tham số phù hợp, chẳng hạn `spring.datasource.url` hoặc một key do thư viện công bố.
3. **Khai báo bean riêng** khi cần một implementation hoặc chính sách khác. Kiểm tra điều kiện back-off của chính auto-configuration liên quan trước khi kỳ vọng bean mặc định biến mất.
4. **Loại trừ auto-configuration cụ thể** khi chủ động không dùng cơ chế đó, thay vì loại bỏ bừa toàn bộ starter.
5. **Quan sát kết quả điều kiện** khi hành vi khởi động không như mong đợi; classpath, property, nhiều bean cùng type và thứ tự xử lý có thể ảnh hưởng.

Ví dụ, một ứng dụng có thể loại trừ cấu hình JDBC mặc định nếu tự quản lý hoàn toàn tầng kết nối:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Đây là **đoạn minh họa riêng** cho ứng dụng có dependency chứa `DataSourceAutoConfiguration`, không ghép cùng demo `DemoApplication` ở mục 5. Cũng có thể dùng `spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration` khi cần kiểm soát qua cấu hình. Chỉ exclude nếu đã xác định rõ ảnh hưởng đến các bean phụ thuộc.

**Không cần tự viết starter cho cấu hình chỉ dùng trong một ứng dụng.** Với cấu hình nội bộ, `@Configuration` và `@Bean` thường rõ ràng, dễ kiểm soát hơn. Một cấu hình có thể được tái sử dụng trong vài module cùng một ứng dụng mà chưa cần trở thành auto-configuration công khai.

## 4. Phạm vi trách nhiệm khi bạn phát triển thư viện dùng chung

Thư viện phục vụ nhiều ứng dụng với dependency và chính sách khác nhau. Thiết kế hợp lý thường có ba lớp trách nhiệm:

| Thành phần | Chứa gì? | Phạm vi trách nhiệm |
| --- | --- | --- |
| `greeter-core` | API, model, implementation thuần | Cung cấp chức năng; không cần Spring Boot để chạy nghiệp vụ |
| `greeter-autoconfigure` | `@AutoConfiguration`, condition, bean mặc định, configuration properties | Kết nối core vào Spring Boot khi điều kiện phù hợp |
| `greeter-spring-boot-starter` | Khai báo dependency thuận tiện cho người dùng | Kéo các thành phần cần thiết vào classpath; thường không chứa logic nghiệp vụ |

Đây là **cách tách module khi đóng gói thật**, không phải yêu cầu mọi thư viện nhỏ đều có ba JAR. Demo ở mục 5 đặt các thành phần trong cùng một project để nhìn rõ đường đi; khi phát hành thư viện, chuyển chúng sang các artifact riêng tương ứng.

Một auto-configuration tốt phải có các đặc tính sau:

- **Có điều kiện kích hoạt**: ví dụ `@ConditionalOnClass` khi dependency tích hợp có mặt, `@ConditionalOnProperty` để bật/tắt tính năng, `@ConditionalOnWebApplication` khi chỉ chạy trong môi trường web.
- **Không chiếm quyền cấu hình của ứng dụng**: dùng `@ConditionalOnMissingBean` cho bean mặc định có thể thay thế; đặt tên key/property riêng theo namespace của thư viện.
- **Không tự ý quét component của ứng dụng**: lớp auto-configuration được đăng ký qua tệp `AutoConfiguration.imports`; dùng `@Import` rõ ràng nếu cần thêm cấu hình nội bộ, thay vì `@ComponentScan` diện rộng.
- **Không phụ thuộc vào thứ tự may rủi**: nếu cần thứ tự giữa các auto-configuration, dùng thuộc tính `before`/`after` của `@AutoConfiguration`; lưu ý thứ tự đăng ký định nghĩa bean khác với thứ tự khởi tạo bean.
- **Tách phần tích hợp tùy chọn**: nếu loại thư viện bên ngoài thực sự optional, tránh để kiểu dữ liệu vắng mặt lọt vào chữ ký method sẽ bị JVM tải quá sớm; có thể cô lập bằng lớp `@Configuration(proxyBeanMethods = false)` lồng với `@ConditionalOnClass`.
- **Đóng gói có thể khám phá**: cung cấp tệp imports đúng đường dẫn và metadata properties để IDE hỗ trợ người dùng; có test tình huống bật, tắt, ghi đè và thiếu dependency.

## 5. Ví dụ xuyên suốt: ứng dụng dùng auto-configuration của thư viện

Demo dùng **một Maven project** để học cơ chế mà không cần xuất bản JAR trước. Đường package `com.example.app` của ứng dụng cố ý khác `com.example.greeter.autoconfigure`; nhờ đó auto-configuration được nạp qua imports, không bị component scanning của ứng dụng “nhặt” nhầm.

### 5.1. Cấu trúc tệp

```text
greeter-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/
    │   │       ├── app/DemoApplication.java
    │   │       └── greeter/
    │   │           ├── GreeterClient.java
    │   │           └── autoconfigure/
    │   │               ├── GreeterProperties.java
    │   │               └── GreeterAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/greeter/autoconfigure/
            └── GreeterAutoConfigurationTest.java
```

### 5.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <groupId>com.example</groupId>
    <artifactId>greeter-demo</artifactId>
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

Cần JDK 17+ và Maven 3.x. Starter cơ bản cung cấp Spring Boot runtime và auto-configuration cần cho demo; test starter cung cấp JUnit 5 và AssertJ.

### 5.3. Core không phụ thuộc Spring

`src/main/java/com/example/greeter/GreeterClient.java`

```java
package com.example.greeter;

import java.util.Objects;

public final class GreeterClient {
    private final String prefix;

    public GreeterClient(String prefix) {
        this.prefix = Objects.requireNonNull(prefix, "prefix");
    }

    public String greet(String name) {
        return prefix + ", " + name + "!";
    }
}
```

`GreeterClient` chỉ định nghĩa hành vi chào; nó không biết `@Bean`, `ApplicationContext` hay cách đọc properties. Vì vậy có thể dùng và kiểm thử độc lập bên ngoài Spring.

### 5.4. Properties có namespace của thư viện

`src/main/java/com/example/greeter/autoconfigure/GreeterProperties.java`

```java
package com.example.greeter.autoconfigure;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "acme.greeter")
public record GreeterProperties(
        @DefaultValue("Xin chào") String prefix
) {
}
```

Object này nhận `acme.greeter.prefix` từ cấu hình ứng dụng. `@DefaultValue` cung cấp giá trị khi key chưa được đặt. Để nó trở thành bean được bind, auto-configuration ở bước tiếp theo dùng `@EnableConfigurationProperties`.

### 5.5. Auto-configuration cung cấp mặc định có điều kiện

`src/main/java/com/example/greeter/autoconfigure/GreeterAutoConfiguration.java`

```java
package com.example.greeter.autoconfigure;

import com.example.greeter.GreeterClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreeterClient.class)
@ConditionalOnProperty(
        prefix = "acme.greeter",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
@EnableConfigurationProperties(GreeterProperties.class)
public class GreeterAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreeterClient.class)
    GreeterClient greeterClient(GreeterProperties properties) {
        return new GreeterClient(properties.prefix());
    }
}
```

Phân tích từng ranh giới:
- `@AutoConfiguration` đánh dấu đây là cấu hình mặc định do Boot quản lý.
- `@ConditionalOnClass` chỉ xét cấu hình khi `GreeterClient` có trên classpath. Trong demo, class này luôn có vì cùng project; trong thư viện tách JAR, condition hữu ích khi dependency là tùy chọn.
- `@ConditionalOnProperty` cho phép `acme.greeter.enabled=false` tắt *toàn bộ* cấu hình này; nếu key không có, `matchIfMissing=true` cho phép bật mặc định.
- `@EnableConfigurationProperties` đăng ký và bind `GreeterProperties`.
- `@ConditionalOnMissingBean(GreeterClient.class)` đăng ký client mặc định chỉ khi context chưa có bean phù hợp cùng type do ứng dụng cung cấp.

Điểm tinh tế: khi tắt `acme.greeter.enabled`, auto-configuration **không tạo bean mặc định**. Điều đó không cấm ứng dụng tự khai báo `GreeterClient`. Tương tự, `@ConditionalOnMissingBean` là điều kiện trên bean mặc định, không phải cơ chế khóa hay ghi đè bean của ứng dụng.

### 5.6. Công bố auto-configuration bằng metadata resource

Tạo tệp **đúng chính tả và đúng đường dẫn**:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.greeter.autoconfigure.GreeterAutoConfiguration
```

Mỗi dòng chứa tên đầy đủ của một lớp auto-configuration. Spring Boot 3.x dùng tệp này để tìm ứng viên khi ứng dụng khởi động. Chỉ đặt `@AutoConfiguration` lên class nhưng không công bố nó qua imports sẽ **không làm thư viện tự động được nạp** trong ứng dụng tiêu thụ. Đừng dựa vào `spring.factories` với khóa `EnableAutoConfiguration` như cơ chế đăng ký chính của Spring Boot 3.x.

### 5.7. Ứng dụng tiêu thụ sử dụng bean mà không import thủ công

`src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import com.example.greeter.GreeterClient;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner printGreeting(GreeterClient client) {
        return args -> System.out.println(client.greet("Lan"));
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Với cấu hình mặc định và không có bean `GreeterClient` khác, log chạy ứng dụng **có chứa dòng**:

```text
Xin chào, Lan!
```

Spring Boot còn in startup log tùy môi trường; đây là dòng output của `ApplicationRunner`, không phải toàn bộ stdout.

Thử thêm `src/main/resources/application.properties`:

```properties
acme.greeter.prefix=Chào mừng
```

Chạy lại, dòng từ runner trở thành:

```text
Chào mừng, Lan!
```

Nếu thay bằng `acme.greeter.enabled=false` mà không khai báo bean khác, `ApplicationRunner` yêu cầu `GreeterClient` sẽ không được thỏa mãn; ứng dụng **khởi động thất bại vì thiếu bean**. Đây là kết quả có chủ ý, cho thấy ứng dụng tiêu thụ phải xử lý trường hợp tính năng được tắt, chẳng hạn khai báo runner có điều kiện, thay vì giả định bean luôn tồn tại.

### 5.8. Ứng dụng giành quyền quyết định bằng bean riêng

Đặt lại `application.properties` về trống hoặc bỏ key `enabled`, rồi bổ sung vào trong `DemoApplication`:

```java
@Bean
GreeterClient customGreeterClient() {
    return new GreeterClient("Chào từ ứng dụng");
}
```

Đây là **đoạn thêm vào class ở mục 5.7**, không phải một file Java độc lập. Vì ứng dụng đã có bean cùng type, `@ConditionalOnMissingBean` khiến phương thức `greeterClient(...)` của thư viện không đăng ký bean mặc định. Runner nhận bean do ứng dụng tạo và in:

```text
Chào từ ứng dụng, Lan!
```

Bài học kiến trúc: **starter cung cấp mặc định, ứng dụng có quyền override**. Nếu thư viện cứ đăng ký bean vô điều kiện, sẽ dễ phát sinh trùng bean, phụ thuộc thứ tự hoặc cấu hình khó dự đoán.

## 6. Ma trận quyết định: cấu hình đặt ở đâu?

| Nhu cầu | Nơi hợp lý | Vì sao? |
| --- | --- | --- |
| URL endpoint, credential, chính sách retry riêng cho một service | `application.properties` / secret store / `@Configuration` trong ứng dụng | Giá trị và chính sách phụ thuộc môi trường vận hành của ứng dụng |
| Chọn một implementation riêng cho ứng dụng | `@Bean` tại ứng dụng | App sở hữu quyết định; thư viện nên back off |
| Khởi tạo client mặc định lặp lại ở nhiều ứng dụng khi dependency hiện diện | Auto-configuration của thư viện | Giảm boilerplate và dùng chung quy ước |
| Chia sẻ thuật toán, API không phụ thuộc framework | Core library | Dễ test, dễ tái sử dụng ngoài Spring |
| Cho người dùng thêm một dependency để bật bộ tích hợp | Starter | Đơn giản hóa dependency quản lý từ phía ứng dụng |
| Cần bật/tắt hoặc tinh chỉnh tính năng của thư viện | `@ConfigurationProperties` + condition trong auto-configuration | Có hợp đồng cấu hình ổn định cho ứng dụng |
| Thay hoàn toàn cách Spring Boot tự cấu hình một subsystem | Bean riêng hoặc exclude đúng auto-configuration | Kiểm soát có chủ đích, tránh cấu hình chồng chéo |

**Ranh giới quan trọng:** auto-configuration của thư viện không nên ép các chính sách nghiệp vụ, địa chỉ production, secret, lịch job, database migration hay quyết định bảo mật cụ thể lên mọi ứng dụng. Những việc đó cần tùy biến rõ ràng hoặc opt-in phù hợp.

## 7. Điều kiện và thứ tự: những gì cần hiểu trước khi tự viết starter

| Cơ chế | Ý nghĩa | Cẩn trọng |
| --- | --- | --- |
| `@ConditionalOnClass(X.class)` | Class `X` hiện diện trên classpath | Với class thực sự optional, cô lập code có chữ ký phụ thuộc vào class đó |
| `@ConditionalOnMissingBean(X.class)` | Chưa có bean phù hợp theo type/name/điều kiện tìm kiếm | Kết quả phụ thuộc bean definitions đã được xử lý; dùng hợp lý trong auto-configuration |
| `@ConditionalOnBean(X.class)` | Đã có bean tương ứng | Xem rõ nguồn tạo bean và thứ tự cấu hình |
| `@ConditionalOnProperty` | Khớp key/value trong `Environment` | Xác định mặc định khi key vắng mặt; key sai chính tả có thể khiến condition không khớp |
| `@ConditionalOnWebApplication` | Chỉ kích hoạt trong web application phù hợp | Phân biệt servlet và reactive khi cần |
| `@AutoConfiguration(after = ...)` | Xác định thứ tự xử lý các auto-configuration | **Không** đảm bảo thứ tự tạo instance của bean; dependency injection mới ảnh hưởng vòng đời tạo bean |

Một sai lầm hay gặp là đặt `@ConditionalOnMissingBean` trên cấu hình ứng dụng thông thường và mong nó luôn nhìn thấy mọi bean sẽ xuất hiện sau đó. Condition đánh giá theo những định nghĩa đã xử lý ở thời điểm ấy. Trong thư viện, đăng ký qua auto-configuration giúp cho điều kiện về bean chạy sau các định nghĩa bean ứng dụng, phù hợp cơ chế back-off.

Với tích hợp optional, có thể dùng cách cô lập sau thay vì khai báo method trực tiếp trên cấu hình luôn được load:

```java
@AutoConfiguration
public class OptionalClientAutoConfiguration {
    @org.springframework.context.annotation.Configuration(proxyBeanMethods = false)
    @org.springframework.boot.autoconfigure.condition.ConditionalOnClass(
            name = "com.vendor.OptionalClient"
    )
    static class OptionalClientConfiguration {
        // Đặt @Bean method có kiểu com.vendor.OptionalClient tại đây
        // trong module được biên dịch với vendor API.
    }
}
```

Đây là **sơ đồ minh họa không độc lập chạy được**: code của bean bị lược bỏ vì yêu cầu API `com.vendor.OptionalClient` cụ thể. Ý chính là giữ các chữ ký phụ thuộc thư viện tùy chọn trong cấu hình được bảo vệ bằng class condition. Với thư viện phức tạp, cần kiểm tra cả classpath và phiên bản API tương thích.

## 8. Kiểm thử hợp đồng auto-configuration bằng ApplicationContextRunner

Thay vì chỉ chạy toàn ứng dụng, hãy test những tổ hợp điều kiện mà người dùng thư viện có thể gặp. Tạo file `src/test/java/com/example/greeter/autoconfigure/GreeterAutoConfigurationTest.java`:

```java
package com.example.greeter.autoconfigure;

import com.example.greeter.GreeterClient;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreeterAutoConfigurationTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(GreeterAutoConfiguration.class));

    @Test
    void createsDefaultClientWhenEnabled() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(GreeterClient.class);
            assertThat(context.getBean(GreeterClient.class).greet("Lan"))
                    .isEqualTo("Xin chào, Lan!");
        });
    }

    @Test
    void usesConfiguredPrefix() {
        runner.withPropertyValues("acme.greeter.prefix=Hello")
                .run(context -> assertThat(
                        context.getBean(GreeterClient.class).greet("Lan"))
                        .isEqualTo("Hello, Lan!"));
    }

    @Test
    void skipsDefaultWhenDisabled() {
        runner.withPropertyValues("acme.greeter.enabled=false")
                .run(context -> assertThat(context)
                        .doesNotHaveBean(GreeterClient.class));
    }

    @Test
    void backsOffWhenApplicationProvidesClient() {
        runner.withUserConfiguration(UserGreeterConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(GreeterClient.class);
                    assertThat(context.getBean(GreeterClient.class).greet("Lan"))
                            .isEqualTo("Tự chọn, Lan!");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGreeterConfiguration {

        @Bean
        GreeterClient userGreeterClient() {
            return new GreeterClient("Tự chọn");
        }
    }
}
```

Chạy `mvn test`. Các test này kiểm tra **4 hợp đồng**: có mặc định, có property tùy biến, tắt bằng property và nhường chỗ cho bean người dùng. `ApplicationContextRunner` tạo context độc lập nên không cần khởi động toàn bộ app. Nếu thư viện phụ thuộc class tùy chọn, bổ sung test với `FilteredClassLoader` để mô phỏng dependency vắng mặt. Ngoài ra, test đóng gói JAR hoặc consumer project cần xác minh đường dẫn `AutoConfiguration.imports` thực sự có trong artifact: runner chủ động chỉ định class auto-configuration, nên **không thể tự nó chứng minh khả năng khám phá qua imports file**.

## 9. Chẩn đoán khi “thêm starter mà bean không xuất hiện”

Lần lượt kiểm tra:

1. **Dependency đã nằm trong runtime classpath chưa?** Dependency chỉ ở test scope, bị exclude transitively, hoặc khác phiên bản có thể khiến `@ConditionalOnClass` thất bại.
2. **Tệp imports có đúng vị trí?** Với thư viện tự viết, kiểm tra JAR chứa `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` và đúng tên class.
3. **Condition nào không match?** Chạy ứng dụng với `--debug` (ví dụ `mvn spring-boot:run -Dspring-boot.run.arguments=--debug`) để xem condition evaluation report; phân biệt positive/negative matches. Chỉ bật debug khi điều tra vì output dài.
4. **App đã có bean riêng chưa?** `@ConditionalOnMissingBean` có thể đã back off, hoặc có hơn một ứng viên cùng type làm injection mơ hồ.
5. **Property có sai tên/sai giá trị?** `enabled=false`, prefix bị gõ sai, profile/biến môi trường ghi đè có thể khiến điều kiện hay binding đổi hành vi.
6. **Có bị exclude không?** Kiểm tra `@SpringBootApplication(exclude=...)` và `spring.autoconfigure.exclude`.
7. **Có trộn package scanning với imports không?** Một class auto-configuration bị scan thủ công có thể đăng ký ngoài vòng đời kỳ vọng và gây kết quả khó giải thích.

Nếu ứng dụng có Actuator, endpoint `/actuator/conditions` cũng có thể cung cấp báo cáo điều kiện khi đã cấu hình cho phép truy cập. Không mở công khai endpoint chẩn đoán chứa chi tiết hệ thống trên production mà không kiểm soát quyền truy cập.

Với thư viện, có thể thêm `spring-boot-configuration-processor` như annotation processor để sinh metadata key cấu hình cho IDE; kiểm tra `META-INF/spring-configuration-metadata.json` trong JAR. Metadata IDE hỗ trợ khám phá thuộc tính, **không phải** điều kiện tạo bean và không thay thế imports file.

## 10. Các lỗi thiết kế phổ biến và cách tránh

- **Đặt `@Component` hoặc `@ComponentScan` diện rộng vào starter**: thư viện vô tình bắt bean của ứng dụng hoặc phụ thuộc cấu trúc package. Thay bằng imports + `@AutoConfiguration` + `@Bean`/`@Import` có kiểm soát.
- **Tạo bean mặc định không có `@ConditionalOnMissingBean`**: ứng dụng khó thay thế, có thể gặp bean trùng/mơ hồ. Xác định type và chính sách override ngay từ đầu.
- **Lẫn chính sách nghiệp vụ vào mặc định thư viện**: một timeout/retry/security setting không phù hợp mọi consumer. Cung cấp properties, default có giải thích, cách override và test.
- **Coi “có class trên classpath” là đủ**: class chỉ là một điều kiện; property, bean và môi trường cũng có thể chặn.
- **Hiểu nhầm `@AutoConfiguration(after=...)` tạo bean theo thứ tự**: chỉ tác động thứ tự áp dụng cấu hình; quan hệ phụ thuộc và lifecycle Spring quyết định thứ tự khởi tạo.
- **Dùng `@ConditionalOnClass` trực tiếp trên `@Bean` trả về kiểu của dependency có thể vắng mặt**: JVM có thể cần tải kiểu trước khi điều kiện được xét; cô lập bằng lớp cấu hình điều kiện.
- **Viết test happy path mà không test back-off/tắt tính năng**: bản đầu chạy được nhưng thư viện xung đột với custom bean của consumer.
- **Bỏ qua tương thích phiên bản**: auto-configuration là lớp tích hợp với API Spring Boot/Spring và thư viện thứ ba. Cần quản lý version matrix, thay đổi API và test consumer thật.

## 11. Bài tập tự kiểm tra

1. Nếu ứng dụng thêm starter nhưng muốn tự tạo `GreeterClient`, cấu hình nên đặt ở đâu? **Trong ứng dụng** qua `@Bean`; auto-configuration cung cấp mặc định phải back off.
2. Nếu muốn mọi ứng dụng có dependency nhận được client mặc định theo properties, đặt logic ở đâu? **Trong auto-configuration của thư viện**, công bố qua `AutoConfiguration.imports` và bảo vệ bằng condition.
3. Nếu `acme.greeter.enabled=false` nhưng ứng dụng vẫn tự định nghĩa `GreeterClient`, bean có tồn tại không? **Có**, vì property condition chỉ ngăn phần cấu hình tự động của thư viện.
4. Nếu một JAR có `@AutoConfiguration` nhưng không có imports file, có được Boot tự tìm ra như một auto-configuration chuẩn không? **Không**; cần đăng ký candidates đúng chuẩn (trừ khi ứng dụng chủ động import/scan class đó bằng cách khác).
5. Nếu test `ApplicationContextRunner` pass nhưng ứng dụng tiêu thụ không thấy bean, ưu tiên điều tra gì? **Classpath, metadata imports trong JAR, condition report và cấu hình hiện tại**.

## 12. Ghi nhớ phạm vi

Khi **xây ứng dụng**, bạn chọn dependency, cấu hình và bean cuối cùng theo yêu cầu chạy thực tế. Khi **xây thư viện dùng chung**, bạn thiết kế một tập mặc định có điều kiện, có khả năng bị thay thế, có properties rõ ràng và được phát hiện qua metadata. Hai bên hợp tác qua cơ chế auto-configuration; ứng dụng giữ quyền kiểm soát.

Tài liệu chính thức để tra cứu sâu hơn:
- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot — Using Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Spring Boot API — `@AutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
