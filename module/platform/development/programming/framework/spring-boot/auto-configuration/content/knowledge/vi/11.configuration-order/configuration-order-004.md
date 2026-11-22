# `@AutoConfigureOrder` cho mức ưu tiên giữa các cấu hình tự động trong Spring Boot

Khi phát triển **Spring Boot starter** hoặc tích hợp nhiều thư viện, đôi khi các auto-configuration cùng muốn đăng ký bean mặc định. Thứ tự xử lý các cấu hình khi đó có thể tác động đến kết quả của `@ConditionalOnBean` và `@ConditionalOnMissingBean`. Spring Boot cung cấp `@AutoConfigureOrder` để đặt **mức ưu tiên tổng quát giữa các auto-configuration** theo giá trị số.

**Quy tắc chính:** giá trị `order` **càng nhỏ thì độ ưu tiên càng cao**, tức auto-configuration được áp dụng **sớm hơn** trong quá trình xử lý cấu hình. Ví dụ, `@AutoConfigureOrder(-100)` đứng trước `@AutoConfigureOrder(100)` khi không có ràng buộc thứ tự khác. Sự ưu tiên này liên quan đến **đăng ký bean definition**, không phải thứ tự chạy constructor hoặc thời điểm khởi tạo bean.

## 1. `@AutoConfigureOrder` là gì?

Annotation nằm trong package:

```java
import org.springframework.boot.autoconfigure.AutoConfigureOrder;
```

Khai báo trên lớp auto-configuration:

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigureOrder;

@AutoConfiguration
@AutoConfigureOrder(-100)
public class HighPriorityAutoConfiguration {
    // Định nghĩa bean, các điều kiện áp dụng...
}

@AutoConfiguration
@AutoConfigureOrder(100)
public class LowPriorityAutoConfiguration {
    // Định nghĩa bean, các điều kiện áp dụng...
}
```

Hai lớp bên trên là **minh họa annotation**; trong dự án Java thực tế, mỗi lớp `public` phải nằm ở file mang đúng tên lớp. Ví dụ kiểm thử chạy được với đầy đủ cấu trúc file ở phần 4.

`@AutoConfigureOrder` là biến thể dành riêng cho auto-configuration của cơ chế `@Order` trong Spring Framework. Với Spring Boot 3.x:

- `@AutoConfigureOrder(-100)`: độ ưu tiên cao hơn `@AutoConfigureOrder(0)` và `@AutoConfigureOrder(100)`.
- `@AutoConfigureOrder(0)`: mức mặc định của annotation; khi không khai báo mức ưu tiên riêng, auto-configuration không được dành lợi thế số âm.
- `@AutoConfigureOrder(100)`: độ ưu tiên thấp hơn hai cấu hình ở trên, được xét muộn hơn trong thứ tự theo giá trị số.
- Có thể dùng các hằng số `Ordered.HIGHEST_PRECEDENCE` và `Ordered.LOWEST_PRECEDENCE` thay cho số nguyên, nhưng cần biết các hằng số này biểu thị hai đầu của thang ưu tiên và không tự tạo ràng buộc phụ thuộc giữa hai lớp.

Giá trị `order` là **một mức ưu tiên**, không phải số thứ tự dòng trong một danh sách. Không nên suy ra thứ tự ổn định giữa hai cấu hình **cùng giá trị** chỉ từ `@AutoConfigureOrder`, hoặc dựa vào thứ tự khai báo dependency để giải quyết cạnh tranh.

## 2. Mức ưu tiên ảnh hưởng tới giai đoạn nào?

Spring Boot tìm các auto-configuration, xác định thứ tự áp dụng rồi xử lý những lớp còn đủ điều kiện. Trong Spring Boot 3.x, một starter riêng thường công bố các ứng viên ở:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng là **tên lớp đầy đủ**, ví dụ:

```text
com.example.starter.PrimaryMessageAutoConfiguration
com.example.starter.FallbackMessageAutoConfiguration
```

File imports giúp Spring Boot **tìm thấy** các auto-configuration. `@AutoConfigureOrder` giúp sắp thứ tự **các ứng viên đã được tìm thấy**. Annotation này không tự đăng ký một lớp chưa có trong cơ chế nạp auto-configuration và không phải cách sắp xếp mọi `@Configuration` thông thường trong ứng dụng.

Phân biệt ba thời điểm:

1. **Tìm và sắp thứ tự auto-configuration:** Boot thu thập và sắp theo metadata, gồm mức `@AutoConfigureOrder` và các quan hệ `before/after` nếu có.
2. **Xử lý lớp cấu hình, đăng ký bean definition:** Spring đánh giá điều kiện và đăng ký các định nghĩa bean. `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean` có thể bị tác động bởi **những bean definition đã được xử lý tới thời điểm đó**.
3. **Tạo bean instance:** Container khởi tạo đối tượng khi cần, xét dependency, `@DependsOn`, lazy initialization và vòng đời context. Thứ tự ở bước 1 **không bảo đảm** constructor của bean được chạy theo thứ tự tương tự.

Ví dụ: A có `@AutoConfigureOrder(-100)` và B có `@AutoConfigureOrder(100)`. A có thể được xử lý trước B, nhưng nếu bean do A khai báo **phụ thuộc vào bean do B khai báo**, Spring vẫn có thể tạo bean của B trước để thỏa dependency. Không nên dùng `@AutoConfigureOrder` thay `@DependsOn` hoặc dependency injection.

## 3. Vì sao thứ tự có thể làm thay đổi bean mặc định?

Giả sử hai auto-configuration đều muốn cung cấp một implementation của cùng interface `MessageService`:

```java
// Đoạn rút gọn của cấu hình A:
@Bean
@ConditionalOnMissingBean(MessageService.class)
MessageService primaryMessageService() {
    return () -> "primary";
}

// Đoạn rút gọn của cấu hình B:
@Bean
@ConditionalOnMissingBean(MessageService.class)
MessageService fallbackMessageService() {
    return () -> "fallback";
}
```

Giả sử không có bean `MessageService` của người dùng và A có mức `-100` còn B có mức `100`:

| Bước | Trạng thái đã được xử lý | Kết quả |
| --- | --- | --- |
| Trước A | Chưa có bean definition `MessageService` | A đủ điều kiện xét “missing bean”. |
| Xử lý A | A đăng ký `primaryMessageService` | Definition của A đã tồn tại. |
| Xử lý B | B thấy đã có bean cùng kiểu | `@ConditionalOnMissingBean(MessageService.class)` của B không khớp; B rút lui. |
| Sau khi xử lý | Chỉ có mặc định A | Bean instance được khởi tạo khi container cần. |

Nếu A bị vô hiệu hóa bởi một condition khác (`@ConditionalOnProperty`, `@ConditionalOnClass`…), B có thể trở thành mặc định. Nếu ứng dụng **tự khai báo** `MessageService`, cả hai auto-configuration thông thường đều phải *back off* khi dùng đúng điều kiện thiếu bean. `@AutoConfigureOrder` không được phép “ghi đè quyền chọn bean của người dùng”.

Có hai giới hạn cần hiểu:

- **Mức ưu tiên không tự loại bean.** Nếu cả A và B đều tạo `MessageService` mà không kiểm tra `@ConditionalOnMissingBean`, cả hai bean có thể tồn tại. Khi inject đơn thuần theo kiểu, Spring có thể báo không biết chọn bean nào, trừ khi đã có cơ chế phân giải như `@Qualifier` hoặc `@Primary`.
- **Điều kiện xét theo kiểu/tên đã khai báo.** Nếu A kiểm tra thiếu `ServiceA.class` còn B kiểm tra thiếu `ServiceB.class`, hai condition có thể cùng khớp dù hai implementation đều triển khai cùng interface. Muốn chỉ một mặc định chung, hãy kiểm tra **cùng một kiểu hợp đồng**.

## 4. Ví dụ Java 17 / Spring Boot 3.x: ưu tiên, fallback và quyền ghi đè

Ví dụ này gồm hai auto-configuration cạnh tranh một bean `MessageService`. Lớp chính có `@AutoConfigureOrder(-100)`, lớp dự phòng có `@AutoConfigureOrder(100)`. Thêm `@ConditionalOnProperty` để chứng minh: nếu cấu hình chính bị vô hiệu hóa, cấu hình dự phòng sẽ được chọn. Thử nghiệm thứ ba cho thấy bean của ứng dụng được ưu tiên hơn cả hai mặc định.

### 4.1. Tạo dự án Maven

```text
auto-order-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── AutoConfigureOrderTest.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>auto-order-demo</artifactId>
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

### 4.2. File test hoàn chỉnh

Tạo `src/test/java/demo/AutoConfigureOrderTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.AutoConfigureOrder;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigureOrderTest {

    interface MessageService {
        String source();
    }

    @AutoConfiguration
    @AutoConfigureOrder(-100)
    @ConditionalOnProperty(
            prefix = "demo.primary",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    static class PrimaryMessageAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(MessageService.class)
        MessageService primaryMessageService() {
            return () -> "primary";
        }
    }

    @AutoConfiguration
    @AutoConfigureOrder(100)
    static class FallbackMessageAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(MessageService.class)
        MessageService fallbackMessageService() {
            return () -> "fallback";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserConfiguration {

        @Bean
        MessageService userMessageService() {
            return () -> "user";
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            FallbackMessageAutoConfiguration.class,
                            PrimaryMessageAutoConfiguration.class
                    ));

    @Test
    void smallerOrderValueWinsWhenBothAreEligible() {
        runner.run(context -> {
            assertThat(context.getBeansOfType(MessageService.class))
                    .containsOnlyKeys("primaryMessageService");

            assertThat(context.getBean(MessageService.class).source())
                    .isEqualTo("primary");
        });
    }

    @Test
    void fallbackWinsWhenPrimaryIsDisabled() {
        runner.withPropertyValues("demo.primary.enabled=false")
                .run(context -> {
                    assertThat(context.getBeansOfType(MessageService.class))
                            .containsOnlyKeys("fallbackMessageService");

                    assertThat(context.getBean(MessageService.class).source())
                            .isEqualTo("fallback");
                });
    }

    @Test
    void userProvidedBeanOverridesBothDefaults() {
        runner.withUserConfiguration(UserConfiguration.class)
                .run(context -> {
                    assertThat(context.getBeansOfType(MessageService.class))
                            .containsOnlyKeys("userMessageService");

                    assertThat(context.getBean(MessageService.class).source())
                            .isEqualTo("user");
                });
    }
}
```

Chạy từ thư mục `auto-order-demo` với **JDK 17+** và Maven:

```bash
mvn test
```

**Kết quả mong đợi:** ba kiểm thử được chạy và đều thành công. Maven Surefire thường tổng hợp dạng `Tests run: 3, Failures: 0, Errors: 0, Skipped: 0`, còn các dòng log phụ thuộc phiên bản Maven và môi trường. Code test không gọi `System.out.println`, nên không có stdout nghiệp vụ cần giả định.

| Kiểm thử | Giá trị cấu hình | Bean `MessageService` sau khi nạp context |
| --- | --- | --- |
| `smallerOrderValueWinsWhenBothAreEligible` | `demo.primary.enabled` không đặt | `primaryMessageService`, trả về `"primary"` |
| `fallbackWinsWhenPrimaryIsDisabled` | `demo.primary.enabled=false` | `fallbackMessageService`, trả về `"fallback"` |
| `userProvidedBeanOverridesBothDefaults` | Có `UserConfiguration` | `userMessageService`, trả về `"user"` |

**Giải thích quan trọng:**

1. `AutoConfigurations.of(Fallback…, Primary…)` cố ý truyền lớp **dự phòng trước lớp chính**. Khi được dùng như nguồn auto-configuration, Boot vẫn áp dụng metadata `@AutoConfigureOrder` để sắp lại mức ưu tiên. Thứ tự truyền vào hàm không phải API để chọn cấu hình thắng.
2. Khi chưa có bean của người dùng và điều kiện property của primary khớp, `-100` được áp dụng sớm hơn `100`. Bean definition `primaryMessageService` được đăng ký; tới fallback, `@ConditionalOnMissingBean` thấy đã có kiểu `MessageService` nên không đăng ký fallback.
3. Khi property có giá trị `false`, class cấu hình primary không được áp dụng; fallback tạo bean mặc định.
4. `withUserConfiguration(UserConfiguration.class)` đưa bean do ứng dụng tự định nghĩa vào context trước các auto-configuration. Cả primary lẫn fallback cùng nhường chỗ cho `userMessageService`.
5. Hai lớp auto-configuration trong bài nằm **bên trong file test** và được nạp trực tiếp qua `AutoConfigurations.of`, vì vậy không cần tạo file `AutoConfiguration.imports` cho bộ test. Khi đóng gói **starter thật**, mỗi auto-configuration thường là lớp top-level có tên đầy đủ trong file imports của jar.

### 4.3. Điều gì xảy ra nếu đổi mức ưu tiên?

Thử đổi:

```java
// Trích đoạn để thực hành, không phải file Java độc lập:
@AutoConfigureOrder(200)  // Primary giờ có số lớn hơn Fallback (100).
```

Sau thay đổi, khi cả hai đủ điều kiện và không có ràng buộc thứ tự khác, fallback sẽ được áp dụng trước, đăng ký bean của nó và khiến primary rút lui. Kiểm thử thứ nhất đang kỳ vọng `primaryMessageService` sẽ **thất bại**, vì thế cần đổi kỳ vọng thành `fallbackMessageService`/`"fallback"` nếu thực sự muốn hành vi mới. Bài tập này minh họa hậu quả của việc đổi order; không phải lời khuyên thay đổi cấu hình sản phẩm một cách tùy ý.

## 5. So sánh `@AutoConfigureOrder` với các công cụ sắp thứ tự khác

| Công cụ | Ý nghĩa | Khi nên dùng |
| --- | --- | --- |
| `@AutoConfigureOrder(n)` | Đặt ưu tiên **tổng quát** cho auto-configuration; số nhỏ hơn được ưu tiên sớm hơn. | Các auto-configuration độc lập, muốn định mức ưu tiên chung mà không tham chiếu trực tiếp nhau. |
| `@AutoConfiguration(before = Other.class)` | Diễn đạt A cần được áp dụng **trước một auto-configuration cụ thể**. | Có quan hệ cụ thể với một cấu hình khác. |
| `@AutoConfiguration(after = Other.class)` | Diễn đạt A cần được áp dụng **sau một auto-configuration cụ thể**. | A cần các bean definition do Other đăng ký trước khi xét condition. |
| `@AutoConfigureBefore` / `@AutoConfigureAfter` | Chú thích độc lập tương ứng với `before`/`after`; còn có cách tham chiếu bằng tên. | Cùng trường hợp như hai thuộc tính trên, hoặc khi viết theo kiểu annotation riêng. |
| `@Order` / `Ordered` | Cơ chế order chung của Spring, ví dụ sắp danh sách thành phần nhận qua injection theo quy tắc tương ứng. | Không dùng làm hợp đồng ưu tiên giữa các **auto-configuration**. |
| `@DependsOn` | Yêu cầu bean phụ thuộc được khởi tạo trước một bean khác. | Khi cần kiểm soát quan hệ **khởi tạo instance**, không phải thứ tự đánh giá `@ConditionalOnMissingBean`. |
| `@Primary` / `@Qualifier` | Phân giải bean nào được chọn để inject khi có nhiều bean cùng kiểu. | Khi chủ đích cho phép nhiều bean cùng tồn tại. |

**Khi có quan hệ cụ thể, hãy ưu tiên diễn đạt bằng `before/after`.** Ví dụ một auto-configuration cần xem bean definition do `WebMvcAutoConfiguration` đăng ký, nên biểu diễn quan hệ đó trực tiếp sẽ rõ nghĩa hơn việc tự đoán một số nguyên để giành vị trí. Tránh ghép metadata số và `before/after` với những ý định mâu thuẫn: điều này làm logic khó đọc và khó bảo trì.

Ví dụ quan hệ trực tiếp:

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;

@AutoConfiguration(after = BaseClientAutoConfiguration.class)
public class ClientMetricsAutoConfiguration {
    // Chỉ kiểm tra/đăng ký bean sau BaseClientAutoConfiguration.
}
```

Đây là **trích đoạn**; `BaseClientAutoConfiguration` cần là class tồn tại và có thể tham chiếu trong dự án. Nếu thư viện không muốn phụ thuộc trực tiếp vào class khác, `afterName` có thể chỉ định tên lớp đầy đủ dạng chuỗi. Cần phân biệt cú pháp đó với giá trị số của `@AutoConfigureOrder`.

## 6. Cách áp dụng trong starter thật

Một quy trình thiết kế hợp lý:

1. **Xác định điều kiện kích hoạt:** classpath, property, web stack, hoặc sự có mặt/thiếu bean. `@AutoConfigureOrder` không thay thế bất kỳ điều kiện nào.
2. **Đánh giá có phụ thuộc cụ thể hay không:** nếu A cần B được xử lý trước, dùng `@AutoConfiguration(after = B.class)` hoặc `afterName`.
3. **Chỉ định mức ưu tiên khi cần:** nếu các auto-configuration không phụ thuộc trực tiếp nhau nhưng muốn có thứ tự ưu tiên tổng quát, thêm `@AutoConfigureOrder`. Ghi chú rõ lý do chọn số để người bảo trì không nhầm ý nghĩa.
4. **Khai báo điều kiện back off:** khi cung cấp bean mặc định, dùng `@ConditionalOnMissingBean` với kiểu thích hợp; tránh tạo hai mặc định cạnh tranh do chọn tiêu chí khác nhau.
5. **Đăng ký đúng cơ chế:** đưa class auto-configuration vào `AutoConfiguration.imports`; không dựa vào `@ComponentScan` để nạp các lớp này.
6. **Kiểm thử các đường đi:** có và không có bean người dùng; cấu hình ưu tiên đủ/không đủ điều kiện; các starter bổ sung trên classpath; nâng cấp Spring Boot.

Đừng dựa vào vị trí dòng trong `AutoConfiguration.imports`, thứ tự khai báo `<dependency>` của Maven hoặc thứ tự truyền class ở một nơi khác như hợp đồng ưu tiên. Các thông tin này không diễn đạt đúng quan hệ mong muốn như annotation dành riêng cho auto-configuration.

Nếu cấu hình ở **hai thư viện không do cùng nhóm kiểm soát**, việc gắn `@AutoConfigureOrder` vào thư viện của bạn chỉ là một phần của bài toán. Thư viện kia có thể khai báo `before/after` hoặc điều kiện khác. Hãy kiểm thử **kết quả container thực tế** với tổ hợp dependency cần hỗ trợ, thay vì suy luận rằng “số của mình nhỏ nhất thì chắc chắn thắng trong mọi ứng dụng”.

## 7. Chẩn đoán lỗi thực tế

### 7.1. Không thấy auto-configuration xuất hiện

- Kiểm tra file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` của starter, tên class đúng và dependency thật sự có trên classpath.
- Xem auto-configuration có bị exclude bởi `@SpringBootApplication(exclude = …)` hoặc thuộc tính `spring.autoconfigure.exclude` không.
- Xác định condition lớp: `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnWebApplication`… Có thể cấu hình không được áp dụng dù đã có order.
- Chạy ứng dụng với `--debug` và xem **Condition Evaluation Report** hoặc Actuator `/actuator/conditions` (nếu được bật và cho phép truy cập) để xem lý do khớp/không khớp. Với unit test, dùng `ApplicationContextRunner` như ví dụ.

### 7.2. Một bean mặc định “thắng” khác kỳ vọng

- Cả hai có dùng **cùng kiểu** trong `@ConditionalOnMissingBean` không? Phân biệt kiểu interface với kiểu triển khai và điều kiện theo **tên**.
- Có một bean do người dùng khai báo trước auto-configuration không? Nếu có, hành vi đúng thường là cả hai mặc định rút lui.
- Có `@AutoConfiguration(before/after)` hoặc `@AutoConfigureBefore/After` ở một trong hai thư viện không? Có thêm condition nào khác khiến cấu hình dự kiến bị bỏ qua?
- Có phải lớp đó được nạp như **auto-configuration** hay chỉ là `@Configuration` được component scan/import thủ công? `@AutoConfigureOrder` được thiết kế cho đường nạp auto-configuration.
- Thử dùng `ApplicationContextRunner` để cô lập các lớp đang cạnh tranh và xác nhận bean nào được đăng ký.

### 7.3. Bean khởi tạo theo thứ tự khác dù số order đã đúng

Đây không nhất thiết là lỗi. `@AutoConfigureOrder` quy định thứ tự **áp dụng cấu hình**, còn tạo đối tượng phụ thuộc vào constructor injection, `@DependsOn`, `@Lazy`, yêu cầu từ các bean khác và vòng đời Spring. Nếu cần chắc chắn instance B sẵn sàng khi A khởi tạo, nên biểu diễn dependency bằng constructor hoặc một quan hệ vòng đời thích hợp.

### 7.4. Những lỗi phổ biến

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Nghĩ số lớn hơn là ưu tiên cao hơn | Cấu hình kỳ vọng có thể được xử lý sau | Nhớ **số nhỏ hơn → sớm hơn**. |
| Dùng `@Order` trên bean để thay `@AutoConfigureOrder` | Không đạt mục tiêu sắp auto-configuration | Đặt `@AutoConfigureOrder` trên lớp auto-configuration. |
| Dùng `@AutoConfigureOrder` để “ghi đè” bean tùy chỉnh | Vẫn có nguy cơ xung đột với thiết kế back off | Dùng đúng `@ConditionalOnMissingBean` và kiểm thử bean do người dùng cung cấp. |
| Muốn thứ tự **tạo instance** bằng số order | Constructor không chạy theo thứ tự tưởng tượng | Dùng dependency injection/`@DependsOn` nếu có phụ thuộc khởi tạo. |
| Nhiều lớp cùng `@AutoConfigureOrder(0)` rồi tin rằng imports bảo đảm thứ tự | Hành vi dễ phụ thuộc cấu trúc hoặc thay đổi phiên bản | Khai báo quan hệ `before/after` khi thứ tự là yêu cầu thực sự. |
| Lớp auto-config không được nạp nhưng chỉ kiểm tra order | Annotation không có cơ hội được dùng | Kiểm tra file imports, exclude, condition và report. |
| Hai bean cùng kiểu không có back off | Có thể gây `NoUniqueBeanDefinitionException` khi inject | Thiết kế điều kiện thiếu bean hoặc phân giải bằng `@Primary`/`@Qualifier` theo mục đích. |

## 8. Câu hỏi tự kiểm tra

**Câu 1:** A dùng `@AutoConfigureOrder(-20)`, B dùng `@AutoConfigureOrder(20)`; cả hai là auto-configuration hợp lệ và không có ràng buộc thứ tự khác. Ai được ưu tiên áp dụng sớm hơn?  
**Đáp án:** A vì `-20 < 20`.

**Câu 2:** Cả A và B đều có `@ConditionalOnMissingBean(PaymentService.class)`, không có bean người dùng. A được áp dụng trước B và đăng ký thành công một `PaymentService`. B có tiếp tục đăng ký mặc định không?  
**Đáp án:** Thông thường không, vì khi B được xét thì bean definition cùng kiểu đã tồn tại.

**Câu 3:** Nếu A được ưu tiên trước B, có được kết luận bean do A định nghĩa luôn được **khởi tạo trước** bean do B định nghĩa không?  
**Đáp án:** Không. Đó là giai đoạn khác, chịu ảnh hưởng của dependency và vòng đời bean.

**Câu 4:** Muốn A luôn được áp dụng **sau chính xác B** vì A kiểm tra bean của B, nên chọn gì?  
**Đáp án:** `@AutoConfiguration(after = B.class)` (hoặc `@AutoConfigureAfter(B.class)`) diễn đạt rõ quan hệ hơn một con số order tổng quát.

**Câu 5:** Một ứng dụng đã tự khai báo `PaymentService` phù hợp. A có `@AutoConfigureOrder(-1000)` và `@ConditionalOnMissingBean(PaymentService.class)`. A có tạo bean mặc định để “chiến thắng” bean của ứng dụng không?  
**Đáp án:** Không. Bean của ứng dụng thường đã có trước các auto-configuration; điều kiện thiếu bean không khớp và A rút lui.

**Câu 6:** Hai auto-configuration cùng mức `0`, không có quan hệ `before/after`. Có thể dựa vào thứ tự hai dòng imports để coi thứ tự là API ổn định không?  
**Đáp án:** Không nên. Nếu thứ tự quan trọng, biểu diễn yêu cầu bằng metadata rõ ràng và thêm test.

## Ghi nhớ

`@AutoConfigureOrder` cung cấp **ưu tiên số giữa các auto-configuration**, với **giá trị nhỏ hơn được áp dụng sớm hơn**. Thứ tự đó có thể quyết định bean definition nào xuất hiện trước, vì các điều kiện bean được đánh giá theo những gì Spring đã xử lý. Nó **không tự loại bean**, **không thay thế điều kiện**, **không quy định thời điểm khởi tạo instance** và **không thay thế quan hệ `before/after` khi có phụ thuộc cụ thể**. Với starter thực tế, dùng đúng cơ chế nạp auto-configuration, thiết kế back off và kiểm thử nhiều tổ hợp cấu hình.

### Tài liệu tham khảo chính thức

- Spring Boot Reference — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot API — `@AutoConfigureOrder`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/AutoConfigureOrder.html
- Spring Boot API — `@AutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot API — `@ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html