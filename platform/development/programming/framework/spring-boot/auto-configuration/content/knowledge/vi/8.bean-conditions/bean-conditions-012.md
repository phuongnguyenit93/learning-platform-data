# Hai cấu hình mặc định cùng thỏa `@ConditionalOnMissingBean`: thứ tự quyết định điều gì?

Trong Spring Boot Auto Configuration, hai thư viện hoặc hai module có thể cùng muốn cung cấp một bean mặc định cho **cùng một kiểu dịch vụ**. Cả hai đều viết `@ConditionalOnMissingBean` để nhường chỗ cho bean do ứng dụng tự định nghĩa. Khi chưa có bean nào, nhìn qua cả hai đều “đủ điều kiện”. Vậy cuối cùng ai cung cấp bean?

**Ý chính:** Điều kiện được đánh giá khi Spring **xử lý và đăng ký bean definition**, dựa trên các definition đã được xử lý **tới thời điểm đó**. Nếu cấu hình A được áp dụng trước, A có thể đăng ký bean trước; khi tới B, điều kiện “thiếu bean” của B không còn thỏa. Vì vậy, **thứ tự giữa các auto-configuration có thể quyết định cấu hình mặc định nào thắng**. Đây không phải phép kiểm tra đồng thời trên một ảnh chụp bất biến của toàn bộ cấu hình.

## 1. Phân biệt các khái niệm

- **Bean definition:** thông tin Spring đăng ký về bean (tên, kiểu, cách tạo…), có thể đã tồn tại trước khi đối tượng bean thực sự được khởi tạo.
- **`@ConditionalOnMissingBean`:** chỉ khớp khi chưa có bean *phù hợp với tiêu chí tìm kiếm* trong những bean definition mà context đã xử lý. Có thể tìm theo `value`/`type`, `name`, annotation và phạm vi context; trên một phương thức `@Bean`, nếu không chỉ định kiểu, mặc định suy ra từ **kiểu trả về khai báo** của phương thức.
- **Auto-configuration:** một lớp cấu hình mặc định được Spring Boot thu thập và sắp thứ tự theo cơ chế auto-configuration. Các định nghĩa bean của ứng dụng thường được đăng ký trước các auto-configuration, nhờ đó cấu hình mặc định có thể *back off* khi người dùng đã cung cấp bean.
- **Thứ tự áp dụng cấu hình** khác với **thứ tự khởi tạo bean**. `@AutoConfiguration(before = …)`/`after = …` chi phối thứ tự đăng ký definition; thời điểm tạo instance còn tùy thuộc dependency, `@DependsOn`, lazy initialization và vòng đời context.

Điều kiện “thiếu” luôn gắn với **một tiêu chí cụ thể**. Ví dụ `@ConditionalOnMissingBean(PaymentGateway.class)` xem có bean kiểu `PaymentGateway` hay chưa, chứ không tự hỏi “trên toàn bộ hệ thống còn bất kỳ bean nào không?”.

## 2. Điều gì xảy ra với hai mặc định cạnh tranh?

Giả sử hai auto-configuration đều có một phương thức:

```java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
PaymentGateway gateway() {
    // Trả về implementation của từng thư viện.
    return ...; // Mã minh họa, không phải phương thức độc lập để biên dịch.
}
```

Giả sử ban đầu **không có** `PaymentGateway` do người dùng cung cấp và A được xử lý trước B:

| Thời điểm | Bean definition kiểu `PaymentGateway` đã có? | Hành động |
| --- | --- | --- |
| Trước khi xử lý A | Chưa | Điều kiện của A khớp. |
| Xử lý A | Chưa, tại lúc xét điều kiện | A đăng ký definition `gatewayA`. |
| Xử lý B | Có `gatewayA` từ A | Điều kiện của B không khớp; `gatewayB` không được đăng ký. |
| Sau xử lý cấu hình | Có một mặc định từ A | Khi cần, Spring mới khởi tạo bean tương ứng. |

Nếu B đứng trước A thì **B có thể thắng theo cách đối xứng**. Câu “cả hai cùng thỏa” chỉ đúng nếu ta xét *trạng thái ban đầu một cách trừu tượng*; trong thực tế, mỗi điều kiện được xét khi đến lượt xử lý và có thể nhìn thấy kết quả đăng ký trước đó.

Nếu ứng dụng **tự khai báo** một `PaymentGateway`, cả A và B (khi là auto-configuration được xử lý sau bean của người dùng) đều thường *back off*: không đăng ký bean mặc định của mình.

**Lưu ý:** Nếu A kiểm tra thiếu `GatewayA` còn B kiểm tra thiếu `GatewayB`, hai điều kiện có thể **đều khớp** ngay cả khi `GatewayA` và `GatewayB` đều triển khai `PaymentGateway`. Muốn cạnh tranh cùng một vị trí mặc định, hãy kiểm tra **cùng kiểu hợp đồng** như `PaymentGateway.class`. Kiểm tra theo **tên** và theo **kiểu** cũng có thể cho kết quả khác nhau.

## 3. Ví dụ kiểm chứng chạy được: Java 17 và Spring Boot 3.x

Ví dụ dưới đây không cần dựng ứng dụng web: `ApplicationContextRunner` tạo một context nhỏ và cho phép kiểm tra chính xác auto-configuration nào đăng ký bean. Hai cấu hình khai báo cùng điều kiện; A được đặt **trước** B một cách tường minh. Thứ tự truyền lớp vào `AutoConfigurations.of(…)` cố ý là B rồi A để nhấn mạnh việc Boot sắp xếp theo metadata của auto-configuration.

Tạo cấu trúc:

```text
bean-order-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── CompetingDefaultsTest.java
```

**`pom.xml`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-order-demo</artifactId>
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

**`src/test/java/demo/CompetingDefaultsTest.java`**:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CompetingDefaultsTest {

    interface Gateway {
        String provider();
    }

    // A phải được áp dụng trước B.
    @AutoConfiguration(before = BetaAutoConfiguration.class)
    static class AlphaAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(Gateway.class)
        Gateway alphaGateway() {
            return () -> "alpha";
        }
    }

    @AutoConfiguration
    static class BetaAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(Gateway.class)
        Gateway betaGateway() {
            return () -> "beta";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserConfiguration {

        @Bean
        Gateway userGateway() {
            return () -> "user";
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(
                            BetaAutoConfiguration.class,
                            AlphaAutoConfiguration.class));

    @Test
    void alphaWinsWhenNoUserBeanExists() {
        runner.run(context -> {
            assertThat(context.getBeansOfType(Gateway.class))
                    .containsOnlyKeys("alphaGateway");
            assertThat(context.getBean(Gateway.class).provider())
                    .isEqualTo("alpha");
        });
    }

    @Test
    void userBeanMakesBothDefaultsBackOff() {
        runner.withUserConfiguration(UserConfiguration.class).run(context -> {
            assertThat(context.getBeansOfType(Gateway.class))
                    .containsOnlyKeys("userGateway");
            assertThat(context.getBean(Gateway.class).provider())
                    .isEqualTo("user");
        });
    }
}
```

Chạy ở thư mục `bean-order-demo`:

```bash
mvn test
```

**Kết quả mong đợi:** cả hai kiểm thử thành công; trong test thứ nhất chỉ có bean `alphaGateway`, trong test thứ hai chỉ có bean `userGateway`. Đoạn test không in ra stdout ứng dụng nên không giả định một dòng console cố định; log Maven và số liệu tổng hợp có thể khác theo môi trường.

Giải thích:

1. `AlphaAutoConfiguration` có quan hệ `before = BetaAutoConfiguration.class`, nên phải được áp dụng trước `BetaAutoConfiguration`, bất kể thứ tự hai lớp trong lời gọi `AutoConfigurations.of`.
2. Khi định nghĩa `alphaGateway` được đăng ký, `@ConditionalOnMissingBean(Gateway.class)` của B thấy đã có bean phù hợp và rút lui.
3. Khi có `UserConfiguration`, `userGateway` có sẵn trước các auto-configuration; vì vậy cả A và B đều rút lui.
4. Nếu đổi annotation của A thành `@AutoConfiguration(after = BetaAutoConfiguration.class)` và đổi kỳ vọng của test đầu thành `betaGateway`/`"beta"`, B sẽ là mặc định thắng. Đó là thay đổi trong ví dụ để tự thực hành, không phải một nhánh mã đồng thời.

Ví dụ này dùng các lớp auto-configuration lồng trong **test** và nạp trực tiếp bằng `AutoConfigurations.of`. Trong một **starter thật**, đặt các lớp auto-configuration ở package riêng, tránh bị component scan thu nhận, và liệt kê tên lớp đầy đủ trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` (Spring Boot 3.x). Không dùng thứ tự dòng của file imports như hợp đồng quy định ai thắng.

## 4. Chọn và cố định thứ tự đúng cách

Khi hai auto-configuration có quan hệ ưu tiên cụ thể:

```java
// Trích đoạn lớp cấu hình thực tế:
@AutoConfiguration(before = SecondaryGatewayAutoConfiguration.class)
public class PrimaryGatewayAutoConfiguration {
    // @Bean với @ConditionalOnMissingBean(Gateway.class)
}
```

Hoặc phát biểu phía cấu hình cần chạy **sau**:

```java
@AutoConfiguration(after = PrimaryGatewayAutoConfiguration.class)
public class SecondaryGatewayAutoConfiguration {
    // @Bean với @ConditionalOnMissingBean(Gateway.class)
}
```

Các cách tương đương là `@AutoConfigureBefore` và `@AutoConfigureAfter`. Với quan hệ trực tiếp giữa hai cấu hình, `before/after` dễ hiểu và bền hơn việc ngầm dựa vào tên lớp, thứ tự dependency hoặc thứ tự dòng trong `AutoConfiguration.imports`. Với các auto-configuration độc lập không cần tham chiếu trực tiếp nhau, Spring Boot cũng có `@AutoConfigureOrder` để đặt mức ưu tiên tổng quát; nó không nên thay thế một quan hệ phụ thuộc cụ thể có thể diễn đạt bằng `before/after`.

Đừng nhầm:

- `@Order` trên bean, `@Primary` hay `@Qualifier` quyết định ưu tiên/sự lựa chọn trong các ngữ cảnh khác (ví dụ injection); chúng **không bảo đảm thứ tự xử lý của hai auto-configuration** để giải quyết điều kiện thiếu bean.
- `@DependsOn` chi phối quan hệ khởi tạo, **không** khiến một bean definition được xét trước để điều kiện của cấu hình khác nhìn thấy.
- Đảo thứ tự hai dependency trong `pom.xml` hay hai dòng trong file imports không phải cách đáng tin để quy định mặc định nào thắng.
- Sử dụng `@ConditionalOnMissingBean` trong cấu hình người dùng thông thường có thể gây kết quả phụ thuộc vào lịch đăng ký definition. Spring Boot khuyến nghị dùng điều kiện này ở **auto-configuration**, nơi các bean định nghĩa bởi ứng dụng thường đã được xử lý.

Nếu hai nhà cung cấp thực ra đại diện cho **hai lựa chọn chức năng khác nhau**, nên có cơ chế chọn lựa chủ động: chẳng hạn mỗi nhánh dùng `@ConditionalOnProperty` với giá trị riêng (và quy định rõ nhánh mặc định), hoặc chỉ kích hoạt một auto-configuration bằng điều kiện classpath/phạm vi phù hợp. `before/after` giải quyết ưu tiên **khi cả hai cùng hợp lệ**, nhưng không thay thế thiết kế lựa chọn provider.

## 5. Chẩn đoán khi kết quả khác kỳ vọng

1. **Xác định bean mục tiêu.** Cả hai nhánh có thật sự kiểm tra `@ConditionalOnMissingBean(Gateway.class)`, hay mỗi nhánh tự suy ra kiểu trả về khác nhau? Có nhánh kiểm tra `name` thay vì `type`? Chú ý cả `search` đối với context cha/con.
2. **Kiểm tra thứ tự auto-configuration.** Có khai báo `@AutoConfiguration(before/after)` hoặc `@AutoConfigureBefore/After` đúng hai lớp auto-config thực tế không? Chúng có được nạp qua cơ chế auto-config (thay vì component scan hoặc `@Import` thông thường) không?
3. **Xem Condition Evaluation Report.** Với ứng dụng Boot có thể khởi động cùng `--debug` hoặc cấu hình log để thấy condition nào matched/did not match; trong test dùng `ConditionEvaluationReportLoggingListener`. Thông báo “found bean …” chỉ ra điều kiện sau đã nhìn thấy definition nào.
4. **Kiểm tra bean được đăng ký, không chỉ instance được khởi tạo.** Bean có thể là lazy nhưng definition vẫn tồn tại và khiến `@ConditionalOnMissingBean` không khớp.
5. **Viết test cho cả ba tình huống quan trọng:** không có bean do người dùng khai báo, có bean của người dùng, và một nhánh auto-configuration bị vô hiệu. `ApplicationContextRunner` giúp khóa hợp đồng hành vi của starter qua nâng cấp.

### Các lỗi dễ mắc

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Mặc định B thắng dù muốn A | B được áp dụng trước hoặc A không đủ điều kiện vì lý do khác | Khai báo quan hệ `before/after` và xem report. |
| Có cả hai bean, injection theo kiểu bị mơ hồ | Điều kiện kiểm tra hai kiểu/tên khác nhau, hoặc cấu hình không được xử lý như auto-config | Cho cả hai kiểm tra cùng kiểu hợp đồng; kiểm tra cách đăng ký. |
| Có bean custom nhưng default vẫn được thêm | Bean custom được đăng ký quá muộn, hoặc kiểu khai báo/tiêu chí condition không khớp | Đưa custom bean vào cấu hình người dùng và xác nhận kiểu đủ cụ thể. |
| Đã thêm `@Primary` nhưng vẫn có hai bean | `@Primary` không loại bean khác | Sửa điều kiện và thứ tự đăng ký; dùng `@Primary` chỉ khi thật sự muốn phân giải injection. |
| Dùng `@Order`/`@DependsOn` nhưng kết quả không đổi | Nhầm thứ tự injection/khởi tạo với thứ tự đăng ký | Dùng metadata dành riêng cho auto-configuration. |

## 6. Bài tự kiểm tra

- Nếu A và B cùng dùng `@ConditionalOnMissingBean(Gateway.class)`, không có bean người dùng, A được áp dụng trước: bean nào được đăng ký? **A**, với giả định không có điều kiện khác cản A.
- Nếu thêm `@Bean Gateway customGateway()` từ cấu hình người dùng: A hay B còn tạo mặc định không? **Không**, khi bean đó đã được đăng ký trước lúc hai auto-configuration được xét.
- Nếu A kiểm tra thiếu `AlphaGateway.class` còn B kiểm tra thiếu `BetaGateway.class`: có đảm bảo chỉ một `Gateway` không? **Không**; hai điều kiện tìm hai kiểu khác nhau.
- Nếu dùng `@AutoConfiguration(after = B.class)` cho A thì thay đổi gì? **B có ưu tiên được áp dụng trước A**, vì vậy B có thể đăng ký mặc định trước và A back off.
- Muốn chắc chắn thứ tự tạo đối tượng cũng giống thứ tự auto-configuration? **Không thể suy ra** chỉ từ `before/after`; hãy xem dependency và vòng đời bean.

**Ghi nhớ:** `@ConditionalOnMissingBean` là cơ chế **back off tại thời điểm xét định nghĩa bean**. Để hai cấu hình mặc định cạnh tranh cùng một kiểu hoạt động dự đoán được, hãy (1) dùng chung tiêu chí kiểu bean, (2) đặt thứ tự auto-configuration tường minh nếu có ưu tiên và (3) kiểm thử cả mặc định lẫn bean tùy biến của người dùng.

### Tài liệu tham khảo

- Spring Boot Reference — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot API — `@AutoConfiguration`: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html