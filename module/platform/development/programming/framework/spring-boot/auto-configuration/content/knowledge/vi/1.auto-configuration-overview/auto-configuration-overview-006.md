# Cấu hình mặc định có điều kiện và cơ chế nhường chỗ cho người dùng (back-off)

> **Ngữ cảnh:** Spring Boot — auto-configuration, phần “Bức tranh tự cấu hình”. Bài tập trung vào cách Spring Boot chỉ đăng ký cấu hình mặc định khi đủ điều kiện và để cấu hình do ứng dụng cung cấp được ưu tiên theo cơ chế back-off. Ví dụ sử dụng Java 17 và Spring Boot 3.5.7 để có thể tái lập; nguyên lý điều kiện/back-off cũng áp dụng cho các bản Spring Boot hiện đại, nhưng tên các auto-configuration cụ thể có thể khác giữa các phiên bản.

## 1. Vì sao cần cấu hình mặc định có điều kiện?

Trong Spring Framework, ứng dụng khai báo bean trong `ApplicationContext` bằng `@Configuration`, `@Bean`, component scan hoặc những cơ chế đăng ký bean khác. Spring Boot thêm **auto-configuration** để cung cấp các bean/cấu hình phù hợp với thư viện, môi trường và những gì ứng dụng **đã tự khai báo**.

Ví dụ: khi ứng dụng có thư viện JDBC, có đủ điều kiện kết nối và chưa tự cung cấp `DataSource`, Spring Boot có thể cấu hình `DataSource` tương ứng. Nếu ứng dụng đã có `DataSource` do mình khai báo, phần cấu hình mặc định tương ứng sẽ **nhường chỗ** (back off). Đây là quyết định có điều kiện tại thời điểm dựng context, không phải cơ chế liên tục thay đổi bean sau khi chạy.

Hai câu hỏi khác nhau cần trả lời khi đọc bất kỳ auto-configuration nào:

1. **Nó có được xét áp dụng không?** Phụ thuộc điều kiện classpath, loại ứng dụng web/không web, thuộc tính `Environment`, bean đã tồn tại, tài nguyên,...
2. **Nếu được xét, bean mặc định cụ thể có được đăng ký không?** Thường có `@ConditionalOnMissingBean` ở mức `@Bean`; từng bean có thể nhường chỗ độc lập.

**Back-off không có nghĩa là xóa hay thay bean đã tạo.** Thông thường, Spring Boot bỏ qua việc đăng ký **bean mặc định** khi nhận thấy người dùng đã khai báo bean phù hợp.

## 2. Cơ chế xử lý theo thứ tự

```text
@SpringBootApplication
    └─ bao gồm @EnableAutoConfiguration
          └─ tìm ứng viên auto-configuration trong
             META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
               └─ đánh giá điều kiện trên lớp cấu hình
                    └─ xử lý các @Bean và điều kiện riêng
                         ├─ phù hợp, thiếu bean do người dùng cung cấp
                         │    └─ đăng ký bean mặc định
                         └─ không phù hợp hoặc đã có bean tương ứng
                              └─ không đăng ký bean mặc định
```

- `@SpringBootApplication` bao gồm `@EnableAutoConfiguration`, `@ComponentScan` và `@SpringBootConfiguration`. **Component scan** tìm component của ứng dụng; **auto-configuration** nạp các lớp cấu hình được khai báo là ứng viên. Hai cơ chế này có nhiệm vụ khác nhau.
- Auto-configuration có thể chứa nhiều bean. Một bean back off **không đồng nghĩa** toàn bộ lớp auto-configuration bị vô hiệu hóa, trừ khi điều kiện đặt ở **cấp lớp** làm cả lớp không được áp dụng.
- Spring Boot xử lý các định nghĩa cấu hình của người dùng trước các auto-configuration được nhập theo cơ chế chuẩn, để `@ConditionalOnMissingBean` có thể thấy bean do ứng dụng khai báo. Các điều kiện phụ thuộc bean chỉ nhìn thấy những **bean definition đã được xử lý đến thời điểm đánh giá**, nên thứ tự xử lý quan trọng.
- Thứ tự auto-configuration (`@AutoConfiguration(after = ...)`, `before = ...`, hoặc `@AutoConfigureAfter`) liên quan đến **thứ tự xử lý định nghĩa bean**, không quyết định thứ tự khởi tạo bean runtime; thứ tự tạo instance còn do dependency/`@DependsOn` quyết định.

## 3. Những điều kiện thường gặp

| Annotation | Điều kiện | Ví dụ áp dụng và chú ý |
| --- | --- | --- |
| `@ConditionalOnClass` | Class có trên classpath | Chỉ mở cấu hình cho JDBC, Jackson hoặc thư viện tích hợp khi API cần thiết hiện diện. |
| `@ConditionalOnMissingClass` | Class không có trên classpath | Chọn phương án dự phòng khi thiếu thư viện. |
| `@ConditionalOnBean` | Có bean thỏa điều kiện loại/tên | Chỉ tạo một thành phần phụ thuộc khi thành phần nền đã tồn tại. |
| `@ConditionalOnMissingBean` | Chưa có bean thỏa điều kiện loại/tên | Mẫu **back-off** phổ biến nhất: không tạo mặc định nếu ứng dụng cung cấp bean tương ứng. |
| `@ConditionalOnSingleCandidate` | Có một ứng viên bean thích hợp để autowire | Hữu ích cho cấu hình phụ thuộc một bean được chọn rõ, kể cả trường hợp có `@Primary`. |
| `@ConditionalOnProperty` | Property trong `Environment` đáp ứng điều kiện | Bật/tắt tùy chọn cấu hình, dùng `havingValue` và `matchIfMissing` để diễn đạt rõ. |
| `@ConditionalOnResource` | Resource được tìm thấy | Chỉ nạp cấu hình khi một file/resource hiện diện. |
| `@ConditionalOnWebApplication` / `@ConditionalOnNotWebApplication` | Loại ứng dụng | Phân biệt cấu hình áp dụng cho web và non-web; có thể chỉ rõ servlet hoặc reactive khi cần. |
| `@ConditionalOnExpression` | Biểu thức SpEL đánh giá là đúng | Ít nên dùng nếu điều kiện đơn giản đã đủ; tham chiếu bean trong biểu thức có thể khiến bean khởi tạo quá sớm. |

`@ConditionalOnProperty(prefix = "demo.clock", name = "enabled", havingValue = "true", matchIfMissing = true)` có ý nghĩa:

| Giá trị `demo.clock.enabled` | Kết quả |
| --- | --- |
| Không khai báo | **Khớp**, vì `matchIfMissing = true`. |
| `true` | **Khớp** `havingValue = "true"`. |
| `false` | **Không khớp**. |
| Giá trị khác, ví dụ `other` | **Không khớp** với `havingValue = "true"`. |

Nếu **không khai báo `havingValue`**, cách khớp mặc định của `@ConditionalOnProperty` là property **có mặt và giá trị không bằng `false`**; không nên hiểu nó đơn giản là ép kiểu boolean rồi kiểm tra. Một property bị thiếu mặc định không khớp nếu `matchIfMissing` chưa bật.

## 4. Ví dụ hoàn chỉnh: mặc định `Clock` và nhường chỗ khi có bean tùy chỉnh

Ta muốn thư viện cung cấp `Clock.systemUTC()` như mặc định. Ứng dụng sử dụng thư viện có thể khai báo một `Clock` riêng để thay thế hoặc tắt hoàn toàn *auto-configuration của Clock* bằng property `demo.clock.enabled=false`.

Ví dụ gồm các file dưới đây trong một Maven project. File Java nằm đúng đường dẫn tương ứng với `package`. Đặt auto-configuration tại `dev.example.clock`, **ngoài** nhánh component scan `dev.example.app` để tránh vô tình nạp hai lần.

### 4.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>dev.example</groupId>
    <artifactId>conditional-clock</artifactId>
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

### 4.2. `src/main/java/dev/example/clock/ClockAutoConfiguration.java`

```java
package dev.example.clock;

import java.time.Clock;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
    prefix = "demo.clock",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class ClockAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    Clock defaultClock() {
        return Clock.systemUTC();
    }
}
```

- Điều kiện **cấp lớp** cho phép bật mặc định, đồng thời cho phép tắt bằng property.
- Điều kiện **cấp phương thức** tìm bean `Clock` đang hiện diện. Khi đã có bean phù hợp, `defaultClock` không được đăng ký. Đặt `Clock.class` rõ ràng để không phụ thuộc việc suy luận kiểu từ chữ ký method.
- `Clock` là lớp thuộc JDK, nên ví dụ này nhấn mạnh **back-off theo bean và property**. Trong auto-configuration cho thư viện tùy chọn, thường bổ sung `@ConditionalOnClass(ThirdPartyClient.class)` ở **lớp cấu hình lồng nhau riêng** khi chữ ký `@Bean` tham chiếu đến class có thể vắng mặt; điều kiện đặt trực tiếp lên method không phải lúc nào cũng ngăn class loading lỗi khi kiểu trả về bị thiếu.

### 4.3. Đăng ký ứng viên auto-configuration

Tạo file đúng tên `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, nội dung **một dòng**:

```text
dev.example.clock.ClockAutoConfiguration
```

Trong Spring Boot 3.x trở lên, đây là cơ chế chuẩn để công bố các ứng viên auto-configuration từ JAR. Chỉ đặt annotation `@AutoConfiguration` mà không đăng ký qua imports (và không import thủ công ở nơi khác) sẽ **không đủ** để ứng dụng tự tìm thấy lớp này.

### 4.4. Ứng dụng kiểm tra trạng thái

File `src/main/java/dev/example/app/DemoApplication.java`:

```java
package dev.example.app;

import java.time.Clock;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(DemoApplication.class, args)) {
            Map<String, Clock> clocks = context.getBeansOfType(Clock.class);
            System.out.println("clock.count=" + clocks.size());
            clocks.forEach((name, clock) ->
                System.out.println("clock." + name + ".zone=" + clock.getZone())
            );
        }
    }
}
```

Từ thư mục chứa `pom.xml`, chạy:

```bash
mvn -q spring-boot:run
```

Trong trường hợp mặc định, phần dòng do ứng dụng in ra là:

```text
clock.count=1
clock.defaultClock.zone=Z
```

Đây là **các dòng in bởi chương trình**, không phải toàn bộ log Spring Boot. `Z` là cách `ZoneOffset.UTC` hiển thị. Khi không có bean `Clock` do ứng dụng cung cấp và property không tắt, auto-configuration tạo `defaultClock`.

### 4.5. Thêm bean của ứng dụng: back-off

Tạo file `src/main/java/dev/example/app/UserClockConfiguration.java`:

```java
package dev.example.app;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class UserClockConfiguration {

    @Bean
    Clock businessClock() {
        return Clock.fixed(
            Instant.parse("2025-01-01T00:00:00Z"),
            ZoneId.of("Asia/Ho_Chi_Minh")
        );
    }
}
```

Khởi động lại `mvn -q spring-boot:run`. Kết quả liên quan:

```text
clock.count=1
clock.businessClock.zone=Asia/Ho_Chi_Minh
```

`ClockAutoConfiguration` vẫn là ứng viên được xét; nhưng `@ConditionalOnMissingBean(Clock.class)` thấy bean `businessClock` và **không đăng ký** `defaultClock`. Tên bean tùy chỉnh không cần giống tên mặc định vì điều kiện đang xét **theo kiểu `Clock`**. Bean mặc định không được tạo rồi thay thế; nó không được đăng ký ngay từ đầu.

Nếu chạy cùng cấu hình tùy chỉnh với `--demo.clock.enabled=false`, kết quả vẫn có `businessClock`. Property trên `ClockAutoConfiguration` chỉ tắt **auto-configuration đó**, không xóa bean tự khai báo.

Để thử điều kiện property **không có bean tùy chỉnh**, tạm bỏ file `UserClockConfiguration.java` khỏi source hoặc bỏ annotation `@Configuration` trên lớp đó rồi chạy:

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.clock.enabled=false
```

Phần dòng do chương trình in:

```text
clock.count=0
```

Khi đó, không có cấu hình mặc định và cũng không có cấu hình người dùng. Đây là nhánh khác với back-off do bean tùy chỉnh.

## 5. Đọc đúng ý nghĩa của back-off

| Trạng thái | Điều kiện property | Có bean `Clock` của ứng dụng? | `defaultClock` | Kết quả |
| --- | --- | --- | --- | --- |
| A. Mặc định | Khớp | Không | Đăng ký | 1 bean `Clock` mặc định |
| B. Người dùng tự cấu hình | Khớp | Có | Back off | 1 bean `Clock` tùy chỉnh |
| C. Tắt auto-configuration | Không khớp | Không | Không đăng ký | 0 bean `Clock` |
| D. Tắt auto-configuration nhưng người dùng vẫn khai báo | Không khớp | Có | Không đăng ký | Bean tùy chỉnh vẫn tồn tại |

**Điểm cần phân biệt:**

- **Back-off**: điều kiện bean thiếu không còn đúng, nên phần mặc định không đăng ký. Đây là hành vi phối hợp giữa ứng dụng và auto-configuration.
- **Exclusion**: dùng `@SpringBootApplication(exclude = SomeAutoConfiguration.class)`, `@EnableAutoConfiguration(exclude = ...)` hoặc `spring.autoconfigure.exclude` để loại một lớp auto-configuration khỏi danh sách xét; thường dành cho trường hợp không muốn cấu hình đó được áp dụng. Không phải mọi auto-configuration đều cần exclude mới tùy biến được.
- **Property override**: đổi giá trị `application.properties`/`application.yml` để sửa tham số của bean do Boot tạo, *nếu auto-configuration có cung cấp property tương ứng*. Thay đổi property không đồng nghĩa khai báo bean mới.
- **`@Primary`**: giải quyết lựa chọn ưu tiên khi inject giữa nhiều bean cùng kiểu; **không làm một bean mặc định biến mất**. Nếu auto-configuration không có back-off và tạo thêm bean cùng kiểu, `@Primary` chỉ có thể giúp chọn bean lúc inject, không ngăn bean còn lại được tạo.
- **`@ConditionalOnMissingBean(name = "x")`** kiểm tra tên; **`@ConditionalOnMissingBean(SomeType.class)`** kiểm tra kiểu. Không thể suy ra cơ chế back-off chỉ từ tên method `@Bean`.

## 6. Viết điều kiện đúng vị trí, đúng thứ tự

Một auto-configuration thường có cấu trúc:

```java
@AutoConfiguration
@ConditionalOnClass(SomeLibraryApi.class)
class SomeLibraryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SomeLibraryClient.class)
    SomeLibraryClient someLibraryClient() {
        return new SomeLibraryClient();
    }
}
```

Đoạn này **minh họa cấu trúc**, không tự biên dịch vì `SomeLibraryApi`/`SomeLibraryClient` là tên đại diện cho API thư viện. Khi viết thật, chỉ tham chiếu đến kiểu có trong dependency tương ứng và kiểm tra tình huống dependency vắng mặt.

Những giới hạn quan trọng:

1. `@ConditionalOnMissingBean` và `@ConditionalOnBean` nhìn vào **bean definition đã được xử lý**. Nếu dùng thiếu suy nghĩ trong cấu hình thường của ứng dụng, việc bean khác được đăng ký trước hay sau có thể đổi kết quả. Spring Boot khuyến nghị tập trung các bean condition này trong auto-configuration được xử lý sau cấu hình người dùng.
2. Nếu một class tùy chọn có thể **vắng mặt**, tránh đặt nó làm kiểu trả về `@Bean` trong một cấu hình đã bị JVM nạp trước khi điều kiện method được xét. Dùng nested `@Configuration(proxyBeanMethods = false)` có `@ConditionalOnClass` ở cấp lớp, hoặc thiết kế tách biệt phù hợp.
3. Điều kiện cấp lớp ảnh hưởng **toàn bộ lớp**; điều kiện cấp method chỉ ảnh hưởng **bean của method đó**. Muốn một bean nhường chỗ mà bean khác vẫn được tạo, hãy đặt điều kiện tại bean tương ứng.
4. Cân nhắc cả **bean hierarchy** (cha/con). Thuộc tính `search` của các điều kiện bean cho phép giới hạn nơi tìm. Mặc định có thể xét qua context cha, nên khi có nhiều context không nên chỉ nhìn một danh sách bean trong context con.
5. Khi định nghĩa `@Bean`, khai báo kiểu trả về **cụ thể và chính xác** để Spring có metadata đủ tốt khi đánh giá điều kiện. Trả về một kiểu quá tổng quát như `Object` có thể làm cơ chế kiểm tra kiểu bean không nhận ra bean tương ứng như mong muốn.
6. Với nhiều bean cùng kiểu, đừng giả định `@ConditionalOnMissingBean` quyết định bean nào sẽ inject. Nó quyết định có tạo mặc định hay không; quy tắc chọn bean ở injection là vấn đề khác.

## 7. Kiểm thử cả ba nhánh bằng `ApplicationContextRunner`

Thêm file `src/test/java/dev/example/clock/ClockAutoConfigurationTest.java`. Unit test dựng context nhỏ, chỉ nhập auto-configuration đang kiểm tra; vì vậy không cần chạy toàn bộ ứng dụng.

```java
package dev.example.clock;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ClockAutoConfigurationTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(ClockAutoConfiguration.class)
            );

    @Test
    void registersDefaultWhenClockIsMissing() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(Clock.class);
            assertThat(context.getBean(Clock.class).getZone())
                .isEqualTo(ZoneOffset.UTC);
            assertThat(context).hasBean("defaultClock");
        });
    }

    @Test
    void backsOffWhenUserProvidesClock() {
        runner.withUserConfiguration(UserConfig.class)
            .run(context -> {
                assertThat(context).hasSingleBean(Clock.class);
                assertThat(context).doesNotHaveBean("defaultClock");
                assertThat(context.getBean(Clock.class).instant())
                    .isEqualTo(Instant.parse("2025-01-01T00:00:00Z"));
            });
    }

    @Test
    void disablesDefaultWhenPropertyIsFalse() {
        runner.withPropertyValues("demo.clock.enabled=false")
            .run(context ->
                assertThat(context).doesNotHaveBean(Clock.class)
            );
    }

    @Configuration(proxyBeanMethods = false)
    static class UserConfig {
        @Bean
        Clock businessClock() {
            return Clock.fixed(
                Instant.parse("2025-01-01T00:00:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh")
            );
        }
    }
}
```

Chạy:

```bash
mvn -q test
```

Ba bài kiểm tra lần lượt xác nhận **có default**, **default back off**, và **default bị tắt bởi property**. Nếu chạy từ IDE, các test dùng JUnit Jupiter; dependency `spring-boot-starter-test` trong `pom.xml` đã cung cấp bộ test thường dùng của Spring Boot. Test ở trên có thể chạy dù ứng dụng thật không khai báo `UserClockConfiguration`, vì mỗi `ApplicationContextRunner` tạo một context riêng và test thứ hai bổ sung `UserConfig` độc lập.

Lưu ý: `ApplicationContextRunner` chủ yếu để kiểm thử context JVM; tài liệu Spring Boot lưu ý runner này không làm việc khi chạy test **bên trong native image**.

## 8. Chẩn đoán khi bean mặc định không xuất hiện

Khi ứng dụng thiếu bean mà bạn nghĩ Boot sẽ cung cấp, hãy đọc **Condition Evaluation Report**:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

Hoặc với JAR đã build:

```bash
java -jar target/conditional-clock-1.0.0.jar --debug
```

Có thể xem report qua endpoint Actuator `/actuator/conditions` nếu ứng dụng đã thêm Actuator và cho phép expose endpoint đó. Endpoint thường **không được expose qua HTTP theo mặc định**; hãy cấu hình bảo mật và quyền truy cập phù hợp thay vì mở công khai mọi endpoint.

Khi đọc report, tìm tên class và method auto-configuration: **positive matches** là điều kiện khớp, **negative matches** cho biết điều kiện nào không khớp và vì sao. Chẳng hạn, khi có `businessClock`, một điều kiện `@ConditionalOnMissingBean(Clock.class)` không khớp là **tín hiệu back-off hoạt động đúng**, không nhất thiết là lỗi.

Quy trình kiểm tra ngắn:

1. **Ứng viên có được nạp không?** Kiểm tra `@SpringBootApplication`, file `AutoConfiguration.imports` và class đã nằm trong dependency/JAR.
2. **Classpath có đúng không?** `@ConditionalOnClass` có thể không khớp do thiếu dependency hoặc class chỉ có ở test scope.
3. **Property thực nhận là gì?** Kiểm tra tên, prefix, profile, môi trường, `havingValue`, `matchIfMissing`; đừng suy đoán từ một file cấu hình khi có nhiều nguồn property.
4. **Có bean theo kiểu/tên đã tồn tại chưa?** Phân biệt bean người dùng, bean từ cấu hình khác và cách Spring nhận dạng kiểu từ chữ ký `@Bean`.
5. **Điều kiện đặt ở cấp lớp hay method?** Thất bại cấp lớp chặn mọi method; thất bại cấp method chỉ chặn bean đó.
6. **Có nhiều bean cùng kiểu không?** Nếu lỗi là `NoUniqueBeanDefinitionException`, vấn đề liên quan đến chọn bean/injection; kiểm tra `@Primary`, `@Qualifier`, không suy ra back-off hỏng.

## 9. Lỗi hiểu sai thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Có starter là Spring Boot luôn tạo mọi bean.” | Starter đem dependency vào classpath; mỗi auto-configuration còn phải vượt các điều kiện của nó. |
| “`@ConditionalOnMissingBean` sẽ xóa bean mặc định khi bean mới xuất hiện sau startup.” | Điều kiện quyết định đăng ký bean definition trong quá trình dựng context; không phải cơ chế thay bean động. |
| “Tên `businessClock` khác `defaultClock` nên không back off.” | Điều kiện đang kiểm tra **kiểu `Clock`**, không phụ thuộc tên bean. |
| “Có `@Primary` là mặc định sẽ không được tạo.” | `@Primary` chọn ưu tiên khi inject, không triệt tiêu bean definition. |
| “`@ConditionalOnProperty` luôn kiểm tra boolean.” | Cách khớp phụ thuộc `havingValue`, `matchIfMissing` và giá trị property. |
| “Chỉ cần đánh dấu `@AutoConfiguration` là Boot sẽ quét thấy.” | Một auto-configuration cung cấp qua JAR phải được đăng ký trong `AutoConfiguration.imports`; không dựa vào component scan. |
| “Điều kiện classpath trên `@Bean` chắc chắn tránh được lỗi tải lớp.” | Nếu chữ ký method tham chiếu class thiếu, JVM có thể xử lý kiểu đó quá sớm; tách cấu hình có điều kiện ở cấp lớp. |
| “Negative match luôn là lỗi.” | Back-off thường là **negative match có chủ đích** khi đã có bean do người dùng cung cấp. |

## 10. Câu hỏi tự kiểm tra

1. Nếu `@ConditionalOnMissingBean(PaymentClient.class)` nằm trên `@Bean`, ứng dụng đã khai báo `PaymentClient` tên `stripeClient`, bean mặc định có được đăng ký không? **Không**, vì điều kiện theo kiểu đã không còn đúng.
2. Nếu `@ConditionalOnProperty(name = "demo.enabled", havingValue = "true", matchIfMissing = false)` và property không xuất hiện, điều kiện có khớp không? **Không**.
3. Nếu một auto-configuration gồm ba `@Bean` và chỉ một bean back off, hai bean còn lại có tự động biến mất không? **Không**, chúng vẫn được xét theo điều kiện riêng và điều kiện cấp lớp.
4. Khi người dùng tạo bean có `@Primary`, có thể kết luận cấu hình mặc định chắc chắn back off không? **Không**; phải xem auto-configuration có `@ConditionalOnMissingBean` theo kiểu/tên tương ứng hay không.
5. Muốn biết vì sao `DataSourceAutoConfiguration` không tạo bean, nên xem gì trước? **Condition Evaluation Report**, classpath, property và bean đã khai báo.

## Tài liệu tham khảo chính thức

- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): bật/tắt, thay thế dần cấu hình mặc định và báo cáo điều kiện.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): đăng ký `AutoConfiguration.imports`, condition annotation, thứ tự xử lý, back-off và `ApplicationContextRunner`.
- [Spring Boot — Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): điều kiện expose và bảo vệ endpoint giám sát.
