# `matchIfMissing` và quyết định bật hay tắt khi không khai báo thuộc tính

**Chủ đề:** Spring Boot Auto Configuration  
**Nhóm kiến thức:** Điều kiện thuộc tính (`@ConditionalOnProperty`)  
**Câu hỏi trọng tâm:** Khi người dùng **không viết** một cấu hình trong `application.yml`, Spring Boot nên đăng ký bean tương ứng hay bỏ qua? `matchIfMissing` quyết định điều gì, và làm thế nào đặt mặc định an toàn, dễ kiểm thử?

## 1. Cơ chế cốt lõi

Trong Spring Boot, `@ConditionalOnProperty` yêu cầu Spring kiểm tra một hoặc nhiều thuộc tính trong `Environment` trước khi đăng ký cấu hình hoặc bean:

```java
@Bean
@ConditionalOnProperty(prefix = "demo.reports", name = "enabled")
ReportJob reportJob() {
    return new ReportJob();
}
```

Thuộc tính được kiểm tra là `demo.reports.enabled`.

Theo mặc định, điều kiện khớp khi **có thuộc tính** và giá trị chuỗi của nó **khác `"false"`** (không phân biệt hoa/thường). Khi thuộc tính hoàn toàn không có trong `Environment`, điều kiện **không khớp**, nên bean sẽ không được đăng ký.

`matchIfMissing` cho phép thay đổi **chỉ tình huống thuộc tính bị thiếu**:

```java
@ConditionalOnProperty(
    prefix = "demo.reports",
    name = "enabled",
    matchIfMissing = true
)
```

- `matchIfMissing = false` (mặc định): thiếu thuộc tính → **không khớp** → bean/nhánh cấu hình không được đăng ký.
- `matchIfMissing = true`: thiếu thuộc tính → **khớp** → bean/nhánh cấu hình được đăng ký (nếu không bị các điều kiện khác loại bỏ).
- Khi thuộc tính **đã có**, `matchIfMissing` không quyết định kết quả; Spring xét giá trị của thuộc tính theo `havingValue` hoặc quy tắc mặc định.

`matchIfMissing` là một lựa chọn **mặc định khi cấu hình vắng mặt**, không phải lệnh ép bật chức năng bất kể người dùng cấu hình gì.

## 2. Bảng quyết định chuẩn

Giả sử chỉ có một điều kiện áp dụng cho `demo.reports.enabled`, không có điều kiện phụ khác, `havingValue` để mặc định (`""`):

| Giá trị hiệu lực trong `Environment` | `matchIfMissing = false` | `matchIfMissing = true` | Vì sao? |
| --- | --- | --- | --- |
| Không có thuộc tính | Không khớp | **Khớp** | Dựa vào `matchIfMissing` |
| `"true"` | **Khớp** | **Khớp** | Có thuộc tính và không phải `"false"` |
| `"false"` | Không khớp | Không khớp | Có thuộc tính, giá trị bằng `"false"` |
| `"FALSE"` | Không khớp | Không khớp | So sánh không phân biệt hoa/thường |
| `"off"` | **Khớp** | **Khớp** | Với `havingValue=""`, chuỗi `"off"` *không phải* `"false"` |
| `"0"` | **Khớp** | **Khớp** | `"0"` không tự động đồng nghĩa với `"false"` trong điều kiện này |
| `""` (khai báo khóa nhưng để trống) | **Khớp** | **Khớp** | Khóa tồn tại và giá trị không phải `"false"` |

**Phân biệt “thiếu” với “có nhưng rỗng”:**

```properties
# Thuộc tính không có:
# demo.reports.enabled hoàn toàn không xuất hiện

# Thuộc tính có nhưng giá trị rỗng:
demo.reports.enabled=
```

Hai trường hợp này có thể dẫn tới kết quả khác nhau. Ở ví dụ mặc định, dòng thứ hai được coi là thuộc tính có giá trị rỗng; điều kiện thường khớp vì giá trị rỗng không bằng `"false"`.

**Cảnh báo về `off`, `0`, `no`:** Những chuỗi này có thể được diễn giải thành `false` trong các cơ chế bind Boolean khác của Spring Boot. `@ConditionalOnProperty` với `havingValue` mặc định áp dụng quy tắc so sánh chuỗi riêng: không được mặc định rằng mọi chuỗi “giống false” đều tắt chức năng. Đối với feature flag Boolean chặt chẽ, nên dùng `havingValue = "true"`.

## 3. Chọn mặc định OFF hay ON theo mục đích thiết kế

### 3.1. Mặc định OFF: người dùng phải chủ động bật

Phù hợp với chức năng tùy chọn, cần chuẩn bị hạ tầng/chi phí, hoặc có tác động nhạy cảm:

```java
@Bean
@ConditionalOnProperty(
    prefix = "demo.reports",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
ReportJob reportJob() {
    return new ReportJob();
}
```

Cách dùng:

```yaml
# application.yml
demo:
  reports:
    enabled: true
```

Khi không khai báo `demo.reports.enabled` hoặc khai báo `false`, điều kiện không khớp. Người vận hành phải bật rõ ràng bằng `true`.

Một ví dụ thường gặp là dịch vụ gửi email tự động. Nếu môi trường mới chưa cấu hình SMTP đầy đủ, mặc định không đăng ký tác vụ tự gửi sẽ tránh các lần gửi ngoài ý muốn. Tuy nhiên, **điều kiện Spring chỉ quyết định đăng ký bean**; cần thiết kế riêng để bảo đảm không có đường gửi email khác được kích hoạt.

### 3.2. Mặc định ON: chức năng là hành vi tiêu chuẩn, cho phép tắt rõ ràng

Phù hợp khi hành vi đã được xác định là mặc định của sản phẩm, cấu hình bỏ qua là một trường hợp bình thường, và người dùng có quyền opt-out:

```java
@Bean
@ConditionalOnProperty(
    prefix = "demo.reports",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
ReportJob reportJob() {
    return new ReportJob();
}
```

Hệ quả:

- Không viết thuộc tính → điều kiện khớp, tạo `ReportJob`.
- `demo.reports.enabled=true` → điều kiện khớp.
- `demo.reports.enabled=false` → không khớp.
- `demo.reports.enabled=off` → **không khớp** khi `havingValue="true"`; chỉ chuỗi `"true"` mới đáp ứng giá trị yêu cầu.

Lưu ý cuối: `matchIfMissing=true` với `havingValue="true"` **không** có nghĩa là thiếu thuộc tính tương đương “đã cấu hình giá trị true”. Nó có nghĩa là condition cho phép thiếu khóa. Hai trạng thái đều có thể tạo bean, nhưng việc bind giá trị vào các đối tượng cấu hình khác vẫn tuân theo cơ chế riêng.

## 4. `havingValue` và `matchIfMissing` tác động lên hai nhánh khác nhau

`@ConditionalOnProperty` có hai bước suy luận:

1. **Có thuộc tính hiệu lực hay không?** Nếu không có, dùng `matchIfMissing`.
2. **Nếu có thuộc tính, giá trị có đúng không?** Nếu `havingValue` là chuỗi không rỗng, so sánh chuỗi không phân biệt hoa/thường với giá trị yêu cầu. Nếu `havingValue=""` (mặc định), kiểm tra giá trị khác `"false"`.

Ví dụ khi khóa hiện diện:

| Giá trị thuộc tính | `havingValue=""` | `havingValue="true"` | `havingValue="false"` | `havingValue="strict"` |
| --- | --- | --- | --- | --- |
| `"true"` | Khớp | Khớp | Không | Không |
| `"false"` | Không | Không | Khớp | Không |
| `"strict"` | Khớp | Không | Không | Khớp |
| `"off"` | Khớp | Không | Không | Không |

Nếu thuộc tính **vắng mặt**, mọi cột `havingValue` đều nhường quyền quyết định cho `matchIfMissing`.

Ví dụ dễ gây bất ngờ:

```java
@ConditionalOnProperty(
    prefix = "demo.reports",
    name = "mode",
    havingValue = "strict",
    matchIfMissing = true
)
```

Điều kiện khớp trong **hai** tình huống: `demo.reports.mode=strict` **hoặc** `demo.reports.mode` hoàn toàn không có. Nếu yêu cầu nghiệp vụ là “chỉ chạy strict mode khi chỉ rõ `strict`”, phải để `matchIfMissing=false`.

## 5. Bài thực hành độc lập với `ApplicationContextRunner`

Bài thực hành dùng **Java 17**, **Spring Boot 3.3.5**, **JUnit 5**. Nó tạo application context nhỏ trực tiếp trong test, không cần chạy máy chủ web.

### 5.1. Cấu trúc tệp

```text
conditional-property-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── PropertyConditionTest.java
```

Nội dung `pom.xml`:

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
    <artifactId>conditional-property-demo</artifactId>
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

Tạo `src/test/java/demo/PropertyConditionTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class PropertyConditionTest {

    static final class ReportJob {
    }

    @AutoConfiguration
    static class DisabledByDefaultConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "demo.reports",
                name = "enabled",
                havingValue = "true"
        )
        ReportJob reportJob() {
            return new ReportJob();
        }
    }

    @AutoConfiguration
    static class EnabledByDefaultConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "demo.reports",
                name = "enabled",
                havingValue = "true",
                matchIfMissing = true
        )
        ReportJob reportJob() {
            return new ReportJob();
        }
    }

    private final ApplicationContextRunner disabledByDefault =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(DisabledByDefaultConfiguration.class)
            );

    private final ApplicationContextRunner enabledByDefault =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(EnabledByDefaultConfiguration.class)
            );

    @Test
    void noPropertyMeansOffWhenMatchIfMissingIsFalse() {
        disabledByDefault.run(context ->
                assertThat(context).doesNotHaveBean(ReportJob.class)
        );
    }

    @Test
    void noPropertyMeansOnWhenMatchIfMissingIsTrue() {
        enabledByDefault.run(context ->
                assertThat(context).hasSingleBean(ReportJob.class)
        );
    }

    @Test
    void explicitTrueTurnsFeatureOnInEitherMode() {
        disabledByDefault
                .withPropertyValues("demo.reports.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(ReportJob.class)
                );

        enabledByDefault
                .withPropertyValues("demo.reports.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(ReportJob.class)
                );
    }

    @Test
    void explicitFalseTurnsFeatureOffEvenWithMatchIfMissingTrue() {
        enabledByDefault
                .withPropertyValues("demo.reports.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(ReportJob.class)
                );
    }

    @Test
    void offStringDoesNotMatchExplicitHavingValueTrue() {
        enabledByDefault
                .withPropertyValues("demo.reports.enabled=off")
                .run(context ->
                        assertThat(context).doesNotHaveBean(ReportJob.class)
                );
    }

    @Test
    void emptyPresentPropertyIsNotTheSameAsMissing() {
        enabledByDefault
                .withPropertyValues("demo.reports.enabled=")
                .run(context ->
                        assertThat(context).doesNotHaveBean(ReportJob.class)
                );
    }
}
```

Chạy:

```bash
mvn test
```

**Kết quả mong đợi:** `Tests run: 6, Failures: 0, Errors: 0, Skipped: 0` trong báo cáo Maven Surefire (định dạng log có thể khác theo phiên bản plugin). Không có stdout tùy biến từ mã test. Các assertion cho thấy chính xác:

- Bỏ trống khóa → context `disabledByDefault` không có `ReportJob`, context `enabledByDefault` có một bean.
- Khi khóa có giá trị `false`, `matchIfMissing=true` không “cứu” điều kiện.
- Khi kết hợp `havingValue="true"`, giá trị hiện diện nhưng là `"off"` hoặc rỗng không được coi là `"true"`.
- Mỗi phương thức test tạo và đóng context riêng; không bị ảnh hưởng bởi bean từ test khác.

Nếu bạn muốn kiểm tra quy tắc **mặc định** `havingValue=""` cho chuỗi `"off"` hoặc giá trị rỗng, hãy bỏ `havingValue="true"` khỏi **cả hai** điều kiện rồi đổi lại các assertion tương ứng. Không chỉnh assertion theo kết quả mong muốn mà vẫn giữ cấu hình cũ.

## 6. `application.yml`, biến môi trường và “thuộc tính thực sự bị thiếu”

Trong ứng dụng Spring Boot thực tế, thuộc tính không chỉ đến từ tệp `application.yml`. `Environment` có thể tổng hợp cấu hình từ nhiều nguồn như tệp properties/YAML, cấu hình theo profile, biến môi trường, JVM system properties, đối số dòng lệnh và các nguồn được thêm bởi ứng dụng.

Ví dụ:

```yaml
# application.yml
demo:
  reports:
    enabled: false
```

Bây giờ, một nơi khác có thể ghi đè giá trị. Ví dụ chạy ứng dụng với:

```bash
java -jar app.jar --demo.reports.enabled=true
```

`@ConditionalOnProperty` kiểm tra **giá trị hiệu lực** trong `Environment` sau quy tắc ưu tiên nguồn cấu hình. Bạn không thể kết luận “thiếu” chỉ vì chưa thấy khóa trong một tệp YAML cụ thể. Cần kiểm tra mọi nguồn áp dụng, gồm profile đang bật và deployment configuration.

Trong môi trường triển khai chuẩn, ví dụ tên biến môi trường tương ứng:

```text
DEMO_REPORTS_ENABLED=false
```

Khi kiểm tra điều kiện, hãy đối chiếu tên chuẩn (`demo.reports.enabled`), cách ánh xạ tên cấu hình của Spring Boot và giá trị cuối cùng của `Environment`. Không đoán có hay không chỉ từ một file.

## 7. Các khác biệt dễ nhầm

### 7.1. `matchIfMissing` không giống giá trị mặc định của `@Value`

```java
@Value("${demo.reports.enabled:true}")
private boolean enabled;
```

Dòng trên cung cấp **giá trị fallback cho chỗ injection**, không tự động thêm khóa vào mọi `PropertySource` và không đồng nghĩa với thay đổi `@ConditionalOnProperty`. Bạn có thể đồng thời có một trường Java nhận `true` nhờ placeholder default và một conditional annotation đánh giá khóa là “missing”.

Tương tự, một field initializer:

```java
@ConfigurationProperties(prefix = "demo.reports")
class ReportsProperties {
    private boolean enabled = true;
}
```

thiết lập mặc định cho đối tượng được bind; nó không bảo đảm condition đã nhìn thấy thuộc tính `demo.reports.enabled` được thêm vào `Environment`. Nếu cần cả hai cùng một chính sách, hãy làm rõ cấu hình mặc định và kiểm thử bằng một context đầy đủ.

### 7.2. `matchIfMissing` không phải toggle động

Các điều kiện đăng ký bean được đánh giá khi container xây dựng application context. Việc sửa biến môi trường hoặc `application.yml` sau khi ứng dụng khởi động **không tự động** đăng ký hoặc gỡ bean khỏi context đang chạy. Nếu cần bật/tắt ở runtime, phải thiết kế cơ chế thay đổi hành vi riêng và xem xét vòng đời của bean.

### 7.3. Nhiều khóa trong `name` là phép AND

```java
@ConditionalOnProperty(
    prefix = "demo.reports",
    name = {"enabled", "scheduler-enabled"},
    havingValue = "true",
    matchIfMissing = false
)
```

Cả `demo.reports.enabled` **và** `demo.reports.scheduler-enabled` đều phải đáp ứng; nếu một khóa thiếu, điều kiện không khớp. Nếu chuyển `matchIfMissing=true`, một khóa bị thiếu được xem là **đạt điều kiện riêng của khóa đó**, nhưng khóa còn lại nếu hiện diện mà sai giá trị vẫn khiến toàn bộ điều kiện không khớp. Không thể diễn giải `name` nhiều phần tử là OR.

### 7.4. Một khóa collection không thể được đánh giá đáng tin như khóa scalar

`@ConditionalOnProperty(name = "demo.targets")` có thể không khớp khi chỉ có `demo.targets[0]` trong `Environment`. Nếu điều kiện phụ thuộc nội dung list/map, nên dùng custom `Condition` hoặc đưa một khóa cờ scalar rõ ràng vào cấu hình. `matchIfMissing` không khắc phục vấn đề xác định thuộc tính collection.

### 7.5. Kết quả condition còn phụ thuộc điều kiện khác

```java
@AutoConfiguration
@ConditionalOnClass(ReportJob.class)
@ConditionalOnProperty(
        prefix = "demo.reports",
        name = "enabled",
        matchIfMissing = true
)
class ReportsAutoConfiguration {
    // ...
}
```

Ngay cả khi `matchIfMissing=true` khớp vì không có khóa, cấu hình vẫn không được kích hoạt nếu thiếu class cần thiết hoặc một `@Conditional` khác không khớp. Bởi vậy, “matchIfMissing bật bean” là cách nói tắt; chính xác hơn là nó cho phép **điều kiện thuộc tính** khớp ở nhánh missing.

## 8. Kiểm tra lỗi cấu hình bằng dữ liệu thực

Khi kỳ vọng mặc định ON/OFF không xảy ra, kiểm tra lần lượt:

1. **Đúng khóa chưa?** `prefix="demo.reports"` + `name="enabled"` tạo `demo.reports.enabled`; xem lỗi gõ tên, dấu gạch ngang hoặc profile.
2. **Khóa thực sự vắng mặt?** Kiểm tra nguồn cấu hình hiệu lực, không chỉ một tệp. Dùng `Environment.getProperty("demo.reports.enabled")` khi có thể quan sát an toàn trong ứng dụng/test.
3. **Đúng giá trị?** `false`, `off`, `0`, rỗng có thể khác nhau ở condition; kiểm tra xem đã khai báo `havingValue` hay chưa.
4. **Đúng mặc định?** `matchIfMissing` bỏ trống đồng nghĩa `false`.
5. **Đặt annotation đúng scope?** Annotation trên lớp cấu hình có thể loại cả tập bean; annotation trên một phương thức `@Bean` chỉ áp cho bean definition của phương thức ấy.
6. **Có điều kiện khác không?** Kiểm tra classpath, bean hiện hữu, web application type hoặc thứ tự auto-configuration.

Các công cụ hỗ trợ:
- Khởi động ứng dụng Spring Boot với `--debug` để xem *Condition Evaluation Report*.
- Nếu có Spring Boot Actuator và endpoint được bật/expose phù hợp, xem `/actuator/conditions`.
- Với test, sử dụng `ApplicationContextRunner` để chạy rõ ràng mọi tổ hợp: missing, `true`, `false`, chuỗi lạ và cấu hình bị ghi đè.

Tránh dùng `@ConditionalOnExpression` chỉ để thay cho `matchIfMissing`; SpEL tạo thêm độ phức tạp không cần thiết khi điều kiện chỉ là một cờ cấu hình.

## 9. Bài tập tự kiểm tra

**Bài 1.** Có `@ConditionalOnProperty(name="app.audit.enabled", matchIfMissing=true)` và `application.yml` không chứa thuộc tính. Bean có được đăng ký không?  
**Giải:** Điều kiện thuộc tính **khớp**. Bean được đăng ký nếu các điều kiện khác cũng cho phép. Không cần có dòng `app.audit.enabled: true` trong YAML để `matchIfMissing` phát huy tác dụng.

**Bài 2.** Giữ annotation trên nhưng đặt `app.audit.enabled=false`. Kết quả?  
**Giải:** **Không khớp**. Khóa đã có nên không xét `matchIfMissing`; mặc định `havingValue=""` không nhận `"false"`.

**Bài 3.** Muốn chỉ bật xử lý khi người dùng chủ động đặt `app.audit.enabled=true`, khai báo gì?  
**Giải:**

```java
@ConditionalOnProperty(
    name = "app.audit.enabled",
    havingValue = "true",
    matchIfMissing = false
)
```

**Bài 4.** Có annotation `havingValue="strict", matchIfMissing=true`; nếu thiếu property thì sao?  
**Giải:** **Khớp** do missing branch. Nếu mục tiêu là “chỉ chạy khi ghi strict”, đổi `matchIfMissing=false`.

**Bài 5.** Property được ghi `app.audit.enabled=off`; điều kiện mặc định không khai báo `havingValue` có khớp không?  
**Giải:** **Có**, bởi `"off"` khác `"false"`. Để tính chất Boolean rõ ràng, dùng `havingValue="true"` và test trạng thái `"off"`/rỗng.

## 10. Ghi nhớ và quy tắc thực tế

- Khi **thiếu khóa**, `matchIfMissing` quyết định condition có khớp hay không. Giá trị mặc định của nó là `false`.
- Khi **khóa đã hiện diện**, `havingValue` (hoặc quy tắc “khác false” nếu bỏ trống) mới quyết định.
- Thiết kế **default OFF** cho chức năng cần bật chủ động; thiết kế **default ON** khi đó thực sự là hành vi mặc định mong muốn và có đường tắt rõ ràng.
- Khi dùng feature flag Boolean, cặp `havingValue="true"` với `matchIfMissing` được chọn tường minh giúp tránh các chuỗi `"off"`, `"0"` hay rỗng bị hiểu là bật.
- Luôn test riêng *missing* và *explicit false*. Đó là hai nhánh logic khác nhau của điều kiện.

### Nguồn tham khảo

- [Spring Boot Reference — Creating Your Own Auto-configuration, Property Conditions](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot API — `@ConditionalOnProperty`](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
