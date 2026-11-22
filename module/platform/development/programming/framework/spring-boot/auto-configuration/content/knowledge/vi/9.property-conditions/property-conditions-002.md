# @ConditionalOnProperty: ý nghĩa mặc định khi thuộc tính tồn tại và giá trị khác `false`

## Mục tiêu bài học

Trong Spring Boot Auto Configuration, `@ConditionalOnProperty` quyết định một cấu hình hoặc một bean có được đăng ký hay không dựa trên giá trị thuộc tính trong `Environment`. Bài này tập trung vào **hành vi mặc định**: khi không chỉ định `havingValue` và `matchIfMissing`, điều kiện chỉ khớp nếu thuộc tính **có tồn tại** và giá trị của nó **khác chuỗi `false` (không phân biệt chữ hoa/chữ thường)**.

Sau bài học, bạn có thể đọc đúng điều kiện; dự đoán kết quả với thuộc tính thiếu, `true`, `false` hoặc một chuỗi bất kỳ; phân biệt mặc định với `havingValue="true"` và `matchIfMissing=true`; viết test để xác nhận thực tế.

## 1. Vì sao cần điều kiện theo thuộc tính?

Một thư viện có thể cung cấp tính năng ghi sự kiện, gửi thông báo hoặc bật một bộ tích hợp. Ứng dụng cần bật/tắt chức năng thông qua cấu hình thay vì sửa mã nguồn.

Ví dụ một bean chỉ được đăng ký khi cấu hình `demo.audit.enabled` đáp ứng điều kiện:

~~~java
@AutoConfiguration
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "demo.audit", name = "enabled")
    AuditSink auditSink() {
        return event -> "AUDIT: " + event;
    }
}
~~~

Đây là **đoạn minh họa**: `AuditSink` giả định là functional interface có phương thức `String write(String event)`. Trong một dự án thực tế, định nghĩa interface và đăng ký auto-configuration cần nằm trong những tệp phù hợp.

Thuộc tính được kiểm tra có tên đầy đủ là `demo.audit.enabled` (`prefix` + dấu chấm + `name`). Spring Boot dùng giá trị có hiệu lực trong `Environment` tại lúc điều kiện được đánh giá. Khi điều kiện không khớp, định nghĩa bean của phương thức mang annotation không được đăng ký. Điều đó khác với việc tạo bean rồi đặt trạng thái `enabled=false` bên trong đối tượng.

## 2. Quy tắc mặc định: **tồn tại** và **không phải `false`**

Định nghĩa:

~~~java
@ConditionalOnProperty(prefix = "demo.audit", name = "enabled")
~~~

về ý nghĩa tương đương với việc sử dụng các giá trị thuộc tính mặc định của annotation:

~~~java
@ConditionalOnProperty(
    prefix = "demo.audit",
    name = "enabled",
    havingValue = "",
    matchIfMissing = false
)
~~~

Lưu ý: `havingValue=""` ở đây là **ký hiệu mặc định của annotation**, có nghĩa là “không yêu cầu một giá trị cụ thể; chấp nhận mọi giá trị trừ `false`”. Nó **không** có nghĩa là “chỉ khớp khi giá trị thuộc tính rỗng”.

Để điều kiện khớp, cả hai yêu cầu phải đúng:

1. `Environment` chứa thuộc tính `demo.audit.enabled` với giá trị không phải `null`.
2. Giá trị đó, khi so sánh dạng chuỗi và không phân biệt chữ hoa/chữ thường, **không bằng `"false"`**.

Nếu thuộc tính hoàn toàn không được khai báo, `matchIfMissing=false` khiến điều kiện không khớp. Đây là điểm khác biệt giữa **không tồn tại** và **tồn tại với một giá trị khác `false`**.

### Bảng chân trị của hành vi mặc định

| Giá trị có hiệu lực của `demo.audit.enabled` | Điều kiện mặc định khớp? | Giải thích |
| --- | --- | --- |
| Không khai báo / không có trong `Environment` | **Không** | `matchIfMissing=false` |
| `true` | **Có** | Có thuộc tính, giá trị khác `false` |
| `TRUE`, `TrUe` | **Có** | Phép so sánh không phân biệt hoa/thường |
| `false` | **Không** | Bằng chuỗi `false` |
| `FALSE`, `FaLsE` | **Không** | Vẫn bằng `false` khi bỏ qua hoa/thường |
| `yes`, `on` | **Có** | Khác chuỗi `false` |
| `no`, `off` | **Có** | Dù người đọc có thể hiểu là “tắt”, chúng không phải chuỗi `false` |
| `0` hoặc `1` | **Có** | Không chuyển thành boolean rồi mới đánh giá |
| `staging` hoặc một chuỗi tùy ý | **Có** | Vẫn khác `false` |
| Chuỗi rỗng `""` nhưng thuộc tính **thực sự hiện diện** | **Có** | Có khóa thuộc tính và giá trị không bằng `false` |

**Điểm dễ nhầm:** `@ConditionalOnProperty` mặc định **không** có nghĩa là “chỉ khớp khi giá trị boolean là `true`”. Nó kiểm tra chuỗi giá trị có hiệu lực. Do đó `enabled=off` hoặc `enabled=0` vẫn có thể đăng ký bean. Nếu mục tiêu là chỉ bật khi cấu hình chỉ rõ `true`, hãy viết `havingValue="true"`.

Với cấu hình lấy từ YAML, properties, biến môi trường hoặc tham số dòng lệnh, cách biểu diễn giá trị có thể chịu ảnh hưởng của cơ chế đọc cấu hình. Khi phân tích, hãy xét **giá trị chuỗi thực tế được `Environment` cung cấp**, thay vì suy đoán từ cách người đọc hiểu các từ như “off”.

## 3. `havingValue` thay đổi phép so sánh như thế nào?

Thuộc tính `havingValue` cho phép yêu cầu một giá trị cụ thể:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "demo.audit",
    name = "enabled",
    havingValue = "true"
)
AuditSink auditSink() {
    return event -> "AUDIT: " + event;
}
~~~

Ở cấu hình này, `demo.audit.enabled=off`, `0` và `staging` **không** khớp nữa. Giá trị `true` hoặc `TRUE` thì khớp. Nếu thuộc tính vắng mặt, mặc định vẫn **không** khớp.

Bảng so sánh các lựa chọn phổ biến:

| Giá trị thuộc tính | Không khai báo `havingValue` | `havingValue="true"` | `havingValue="false"` | `havingValue="staging"` |
| --- | --- | --- | --- | --- |
| `true` | Có | Có | Không | Không |
| `false` | Không | Không | Có | Không |
| `staging` | Có | Không | Không | Có |
| `off` | Có | Không | Không | Không |
| Thiếu thuộc tính | Không | Không | Không | Không |

So sánh `havingValue` cũng không phân biệt chữ hoa/chữ thường. Ví dụ, `havingValue="staging"` có thể khớp `STAGING`.

**Lựa chọn thực tế:** Với một cờ bật/tắt rõ ràng, nên dùng `havingValue="true"` để tránh vô tình bật chức năng vì một giá trị không mong đợi. Với một thuộc tính mang ý nghĩa “mọi giá trị trừ `false` đều bật”, mặc định có thể là chủ đích đúng, nhưng cần được ghi rõ trong tài liệu cấu hình.

## 4. `matchIfMissing` chỉ thay đổi trường hợp **không có thuộc tính**

Mặc định `matchIfMissing=false`. Nếu muốn chức năng được bật khi người dùng không khai báo cấu hình, có thể đặt `matchIfMissing=true`:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "demo.audit",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
AuditSink auditSink() {
    return event -> "AUDIT: " + event;
}
~~~

Khi đó:

- **Thiếu** `demo.audit.enabled`: điều kiện khớp, vì `matchIfMissing=true`.
- `demo.audit.enabled=true`: điều kiện khớp, vì thỏa `havingValue="true"`.
- `demo.audit.enabled=false`: điều kiện **không** khớp.
- `demo.audit.enabled=off`: điều kiện **không** khớp, vì `off` khác `true`.

`matchIfMissing=true` **không** có nghĩa là “bỏ qua kiểm tra giá trị”. Nó chỉ quyết định kết quả khi thuộc tính **thực sự không hiện diện**. Một giá trị đã hiện diện nhưng không thỏa `havingValue` vẫn làm điều kiện thất bại.

Hai kiểu thiết kế có ý nghĩa khác nhau:

~~~java
// Có mặt và khác "false" thì chạy; thiếu thuộc tính thì không chạy.
@ConditionalOnProperty(prefix = "demo.audit", name = "enabled")

// Thiếu thuộc tính cũng chạy; có mặt thì bắt buộc phải bằng "true".
@ConditionalOnProperty(
    prefix = "demo.audit",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
~~~

## 5. Ví dụ kiểm chứng chạy được: Spring Boot 3.3 + JUnit 5

Ví dụ dưới đây dùng `ApplicationContextRunner` tạo từng context độc lập để xác minh các nhánh. Ba auto-configuration khác nhau dùng **cùng kiểu `AuditSink`**, nhưng được nạp bởi **ba runner riêng biệt**, nên không cạnh tranh đăng ký bean với nhau.

**Tệp:** `src/test/java/example/condition/ConditionalOnPropertyDefaultTest.java`

~~~java
package example.condition;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionalOnPropertyDefaultTest {

    private final ApplicationContextRunner defaultRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(DefaultAuditConfiguration.class));

    private final ApplicationContextRunner strictRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(StrictAuditConfiguration.class));

    private final ApplicationContextRunner missingAllowedRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(MissingAllowedAuditConfiguration.class));

    @Test
    void missingPropertyDoesNotMatchByDefault() {
        defaultRunner.run(context ->
                assertThat(context).doesNotHaveBean(AuditSink.class));
    }

    @Test
    void anyPresentValueExceptFalseMatchesByDefault() {
        for (String value :
                new String[] {"true", "TRUE", "yes", "off", "0", "staging", ""}) {
            defaultRunner.withPropertyValues("demo.audit.enabled=" + value)
                    .run(context -> {
                        assertThat(context).hasSingleBean(AuditSink.class);
                        assertThat(context.getBean(AuditSink.class).write("ok"))
                                .isEqualTo("AUDIT: ok");
                    });
        }
    }

    @Test
    void falseIsRejectedRegardlessOfLetterCase() {
        for (String value : new String[] {"false", "FALSE", "FaLsE"}) {
            defaultRunner.withPropertyValues("demo.audit.enabled=" + value)
                    .run(context ->
                            assertThat(context).doesNotHaveBean(AuditSink.class));
        }
    }

    @Test
    void havingValueTrueRequiresTheWordTrue() {
        strictRunner.withPropertyValues("demo.audit.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(AuditSink.class));

        strictRunner.withPropertyValues("demo.audit.enabled=TRUE")
                .run(context ->
                        assertThat(context).hasSingleBean(AuditSink.class));

        strictRunner.withPropertyValues("demo.audit.enabled=off")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AuditSink.class));

        strictRunner.run(context ->
                assertThat(context).doesNotHaveBean(AuditSink.class));
    }

    @Test
    void matchIfMissingAllowsAbsenceButNotExplicitlyWrongValues() {
        missingAllowedRunner.run(context ->
                assertThat(context).hasSingleBean(AuditSink.class));

        missingAllowedRunner.withPropertyValues("demo.audit.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(AuditSink.class));

        missingAllowedRunner.withPropertyValues("demo.audit.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AuditSink.class));

        missingAllowedRunner.withPropertyValues("demo.audit.enabled=off")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AuditSink.class));
    }

    interface AuditSink {
        String write(String event);
    }

    @AutoConfiguration
    static class DefaultAuditConfiguration {

        @Bean
        @ConditionalOnProperty(prefix = "demo.audit", name = "enabled")
        AuditSink auditSink() {
            return event -> "AUDIT: " + event;
        }
    }

    @AutoConfiguration
    static class StrictAuditConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "demo.audit",
                name = "enabled",
                havingValue = "true")
        AuditSink auditSink() {
            return event -> "AUDIT: " + event;
        }
    }

    @AutoConfiguration
    static class MissingAllowedAuditConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "demo.audit",
                name = "enabled",
                havingValue = "true",
                matchIfMissing = true)
        AuditSink auditSink() {
            return event -> "AUDIT: " + event;
        }
    }
}
~~~

**Yêu cầu để chạy:** Java 17+, Spring Boot 3.3.x; test classpath có `spring-boot-starter-test`. Trong một dự án Gradle có plugin/BOM Spring Boot quản lý dependency, phần test có thể khai báo:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Lệnh chạy trong module/dự án chứa tệp test:

~~~bash
# Linux / macOS
./gradlew test --tests "example.condition.ConditionalOnPropertyDefaultTest"

# Windows PowerShell / CMD
gradlew.bat test --tests "example.condition.ConditionalOnPropertyDefaultTest"
~~~

**Kết quả mong đợi:** 5 test pass. `ApplicationContextRunner` đóng từng context sau callback. Trong test thứ hai, các chuỗi `"off"`, `"0"` và chuỗi rỗng vẫn tạo `AuditSink`, chứng minh annotation không thực hiện phép ép kiểu boolean trước khi so sánh. Test thứ ba khẳng định `false` được nhận biết không phân biệt hoa/thường. Hai test cuối làm rõ vai trò độc lập của `havingValue` và `matchIfMissing`. Các assertion không in `AUDIT: ok` ra stdout; thông tin Gradle hiển thị tùy cấu hình test logging.

Ví dụ là test độc lập trong một tệp: các lớp `@AutoConfiguration` lồng nhau được nạp **tường minh** qua `AutoConfigurations.of(...)`. Nếu chuyển thành auto-configuration production ở thư viện, cần khai báo lớp production trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` để Spring Boot tự phát hiện.

## 6. Nhìn vào cấu hình thực tế

Ví dụ `application.yml`:

~~~yaml
demo:
  audit:
    enabled: true
~~~

Đoạn bean có điều kiện mặc định sẽ được đăng ký. Đổi thành `enabled: false` thì điều kiện không khớp. Nếu xóa hẳn `enabled` thì cũng **không khớp**, vì `matchIfMissing=false`.

Với `application.properties`:

~~~properties
demo.audit.enabled=off
~~~

Nếu giá trị có hiệu lực trong `Environment` đúng là chuỗi `off`, **điều kiện mặc định vẫn khớp**. Đây là lý do cờ bật/tắt thông thường nên có `havingValue="true"` khi ứng dụng chỉ muốn cho phép giá trị `true`.

Ví dụ khi chạy chương trình:

~~~bash
java -jar app.jar --demo.audit.enabled=false
~~~

Thuộc tính dòng lệnh thường có mức ưu tiên cao hơn giá trị mặc định trong tệp cấu hình. Hãy kiểm tra giá trị **cuối cùng** mà `Environment` nhìn thấy: một giá trị trong `application.yml` không tự đảm bảo đó là giá trị được điều kiện sử dụng nếu có nguồn thuộc tính khác ghi đè.

Trong auto-configuration, nên dùng tiền tố ngắn, rõ nghĩa và key theo quy ước chữ thường có dấu gạch ngang khi có nhiều từ, ví dụ `demo.audit.log-enabled`.

## 7. Một số chi tiết mở rộng liên quan trực tiếp

### Có nhiều thuộc tính trong `name`

~~~java
@ConditionalOnProperty(
    prefix = "demo.audit",
    name = {"enabled", "remote-enabled"}
)
~~~

Cả `demo.audit.enabled` **và** `demo.audit.remote-enabled` phải hiện diện, đồng thời mỗi giá trị đều khác `false`, thì điều kiện mặc định mới khớp. Thiếu một key hoặc có một key bằng `false` đều khiến điều kiện không khớp. `havingValue`, nếu được đặt, áp dụng cho từng thuộc tính được liệt kê.

### Đặt trên class hay trên `@Bean`

~~~java
@AutoConfiguration
@ConditionalOnProperty(prefix = "demo.audit", name = "enabled")
public class AuditAutoConfiguration {
    // Các @Bean bên trong chỉ được xử lý khi điều kiện class khớp.
}
~~~

Nếu đặt trên **class**, điều kiện kiểm soát việc class cấu hình đó được đăng ký và xử lý. Nếu đặt trên **phương thức `@Bean`**, điều kiện kiểm soát riêng bean được khai báo bởi phương thức ấy. Chọn phạm vi nhỏ nhất phản ánh đúng ý định: không vô tình tắt các bean độc lập chỉ vì một cờ tính năng.

### Không dùng để kiểm tra collection theo tên gốc

`@ConditionalOnProperty(prefix="demo", name="items")` không đảm bảo khớp khi nguồn cấu hình chỉ có `demo.items[0]`, `demo.items[1]` mà không có `demo.items`. Với điều kiện phụ thuộc vào nội dung collection, cân nhắc viết một `Condition` chuyên biệt hoặc thiết kế thuộc tính cờ đơn giản thay vì dựa vào kiểm tra key kiểu này.

### Khác với việc bind boolean

`@ConfigurationProperties` có thể ánh xạ cấu hình vào một thuộc tính Java kiểu `boolean`; điều đó không có nghĩa `@ConditionalOnProperty` mặc định sẽ áp dụng cùng cách chuyển đổi boolean. Điều kiện này xét **giá trị thuộc tính theo chuỗi** trong `Environment`. Vì vậy, kiểm tra “khác `false`” là quy tắc điều kiện, không phải lời khẳng định rằng mọi giá trị còn lại đều là boolean `true`.

## 8. Lỗi thường gặp và cách chẩn đoán

1. **Nghĩ rằng thuộc tính thiếu sẽ bật tính năng theo mặc định.** Thực tế mặc định là `matchIfMissing=false`; muốn bật khi thiếu phải khai báo rõ `matchIfMissing=true`.
2. **Nghĩ rằng `0`, `no` hoặc `off` giống `false`.** Với `havingValue` mặc định, đây là các chuỗi khác `false` và có thể làm điều kiện khớp. Dùng `havingValue="true"` nếu cần đúng cờ boolean rõ ràng.
3. **Hiểu `havingValue=""` là chỉ khớp giá trị rỗng.** Đây là giá trị đặc biệt biểu thị cách kiểm tra mặc định; không tương đương kiểm tra `property.equals("")`.
4. **Cho rằng `matchIfMissing=true` làm mọi giá trị hợp lệ.** Nó chỉ tác động lên trường hợp thiếu; giá trị đã có vẫn phải đáp ứng phép so sánh.
5. **Nhầm `prefix` và `name`.** `prefix="demo.audit", name="enabled"` tạo key `demo.audit.enabled`; đọc nhầm `demo.enabled` sẽ dẫn đến kết luận sai.
6. **Chỉ xem giá trị trong một tệp cấu hình.** Giá trị cuối cùng có thể đến từ nguồn có độ ưu tiên cao hơn như dòng lệnh hoặc biến môi trường. Chẩn đoán dựa trên `Environment` đã hợp nhất.
7. **Gắn điều kiện lên toàn bộ auto-configuration khi chỉ muốn điều khiển một bean.** Phạm vi annotation ảnh hưởng tập bean được đăng ký.
8. **Không kiểm tra nhánh thiếu thuộc tính.** Test chỉ với `true` và `false` sẽ không phát hiện cấu hình sai `matchIfMissing`.

Có thể khởi động ứng dụng với `--debug` để xem **Condition Evaluation Report**, hoặc thêm `ConditionEvaluationReportLoggingListener` vào `ApplicationContextRunner` khi cần debug test. Báo cáo cho biết điều kiện nào khớp/không khớp; hãy tìm `OnPropertyCondition`, tên key được kiểm tra và giá trị mong đợi.

## 9. Tự kiểm tra

**Câu 1:** `@ConditionalOnProperty(name="demo.feature.enabled")`, trong `Environment` không có key này. Bean có được tạo không?

**Đáp án:** Không. `matchIfMissing=false` là mặc định.

**Câu 2:** Key tồn tại với `demo.feature.enabled=off`. Có khớp khi không khai báo `havingValue` không?

**Đáp án:** Có. `off` là chuỗi khác `false`; annotation không mặc nhiên chuyển `off` thành boolean false.

**Câu 3:** Cùng key, đặt `havingValue="true"` và `matchIfMissing=true`. Với giá trị `false`, điều kiện khớp không?

**Đáp án:** Không. `matchIfMissing` chỉ xử lý khi key vắng mặt, không bỏ qua giá trị sai đã hiện diện.

**Câu 4:** `name={"enabled","ready"}`; `enabled=true`, `ready=false`. Có khớp mặc định không?

**Đáp án:** Không. Tất cả key được chỉ định phải thỏa điều kiện, và `ready=false` làm điều kiện thất bại.

## 10. Kết luận áp dụng

Nhớ công thức khi **không cấu hình thêm tham số**:

> `@ConditionalOnProperty` khớp khi **key tồn tại** trong `Environment` **và giá trị không bằng chuỗi `false`** (không phân biệt hoa/thường).

Đối với cờ bật/tắt yêu cầu người dùng ghi rõ `true`, dùng `havingValue="true"`. Đối với tính năng mặc định bật khi không cấu hình, kết hợp `havingValue="true", matchIfMissing=true`. Luôn kiểm tra ba nhánh riêng: **thiếu key**, **`false`**, **giá trị khác `false`** để không nhầm ý nghĩa mặc định.

### Tài liệu chính thức

- [Spring Boot 3.3 — Javadoc `@ConditionalOnProperty`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration (Property Conditions, Testing)](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
