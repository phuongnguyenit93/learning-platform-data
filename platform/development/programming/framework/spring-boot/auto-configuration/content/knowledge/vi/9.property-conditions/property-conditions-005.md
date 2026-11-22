# Nhiều tên thuộc tính trong một @ConditionalOnProperty: tất cả phải cùng khớp

## 1. Vấn đề cần giải quyết

Trong **Spring Boot Auto-configuration**, một bean hoặc cả một lớp cấu hình có thể chỉ được đăng ký nếu **nhiều điều kiện cấu hình** đều được bật. Ví dụ, ứng dụng chỉ nên khởi tạo dịch vụ gửi báo cáo kèm nhật ký kiểm toán khi đồng thời:

- \`app.reports.enabled=true\`: tính năng báo cáo được bật;
- \`app.reports.audit-enabled=true\`: khả năng ghi nhật ký kiểm toán được bật.

Annotation **\`@ConditionalOnProperty\`** hỗ trợ kiểm tra nhiều khóa bằng cách khai báo một mảng trong thuộc tính **\`name\`** (hoặc alias **\`value\`**).

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

// Đoạn minh họa annotation; các class và phương thức được định nghĩa
// trong ví dụ chạy được ở phần kiểm thử.
@ConditionalOnProperty(
    prefix = "app.reports",
    name = {"enabled", "audit-enabled"},
    havingValue = "true"
)
~~~

**Quy tắc quan trọng nhất: nhiều tên trong cùng \`@ConditionalOnProperty\` có quan hệ AND (VÀ).** Mỗi thuộc tính được kiểm tra riêng theo cùng bộ quy tắc, và toàn bộ điều kiện chỉ **match** khi **tất cả** thuộc tính đều match. Có một khóa không đạt thì điều kiện chung không đạt.

Ví dụ trên tương đương phép kiểm tra về mặt ý nghĩa:

~~~text
match(app.reports.enabled, havingValue="true")
AND
match(app.reports.audit-enabled, havingValue="true")
~~~

Các thuộc tính được tìm trong **Spring Environment** khi Spring xử lý điều kiện đăng ký bean; chúng có thể đến từ \`application.yml\`, \`application.properties\`, biến môi trường, tham số dòng lệnh và các PropertySource khác.

## 2. Cú pháp và cách Spring Boot ghép tên thuộc tính

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

// Đây là đoạn minh họa: ReportPublisher là kiểu do ứng dụng/thư viện định nghĩa.
@AutoConfiguration
class ReportAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "app.reports",
        name = {"enabled", "audit-enabled"},
        havingValue = "true",
        matchIfMissing = false
    )
    ReportPublisher reportPublisher() {
        return new ReportPublisher();
    }
}
~~~

Ý nghĩa từng phần:

| Thuộc tính annotation | Tác dụng |
| --- | --- |
| \`prefix = "app.reports"\` | Phần đầu dùng chung cho mọi tên; dấu chấm được thêm tự động khi cần |
| \`name = {"enabled", "audit-enabled"}\` | Hai tên độc lập cần kiểm tra, không phải một chuỗi ghép |
| \`havingValue = "true"\` | **Mỗi** tên phải mang giá trị chuỗi \`"true"\` |
| \`matchIfMissing = false\` | Nếu **bất kỳ** tên bắt buộc nào vắng mặt, tên đó không đạt; đây là mặc định |
| \`value\` | Alias của \`name\`, cũng nhận \`String[]\` |

Với cách khai báo trên, hai khóa đầy đủ là \`app.reports.enabled\` và \`app.reports.audit-enabled\`.

**Viết đúng tên:** tài liệu Spring Boot khuyến nghị tên thuộc tính theo **dashed notation**, chữ thường và dùng dấu gạch nối giữa các từ, ví dụ \`audit-enabled\`. Phần \`prefix\` nên là đường dẫn cấu hình như \`app.reports\`; không cần thêm dấu chấm cuối. Tránh ghi \`name = {"app.reports.enabled", "app.reports.audit-enabled"}\` đồng thời với \`prefix = "app.reports"\`, vì như vậy sẽ lặp tiền tố.

Cách viết thay thế có cùng ý nghĩa:

~~~java
// value là alias của name, không phải phép OR.
// Đoạn minh họa, đặt trên class hoặc phương thức thích hợp.
@ConditionalOnProperty(
    prefix = "app.reports",
    value = {"enabled", "audit-enabled"},
    havingValue = "true"
)
~~~

## 3. Bảng chân trị: có đủ hai khóa và cùng đạt yêu cầu

Với điều kiện:

~~~java
@ConditionalOnProperty(
    prefix = "app.reports",
    name = {"enabled", "audit-enabled"},
    havingValue = "true"
)
~~~

Giả sử Environment có các giá trị sau:

| \`app.reports.enabled\` | \`app.reports.audit-enabled\` | Toàn bộ điều kiện | Giải thích |
| --- | --- | --- | --- |
| \`true\` | \`true\` | **MATCH** | Cả hai cùng bằng giá trị mong đợi |
| \`true\` | \`false\` | **KHÔNG MATCH** | Khóa thứ hai không đạt |
| \`false\` | \`true\` | **KHÔNG MATCH** | Khóa thứ nhất không đạt |
| \`false\` | \`false\` | **KHÔNG MATCH** | Cả hai không đạt |
| \`true\` | Vắng mặt | **KHÔNG MATCH** | Thiếu khóa thứ hai; \`matchIfMissing=false\` |
| Vắng mặt | \`true\` | **KHÔNG MATCH** | Thiếu khóa thứ nhất |
| Vắng mặt | Vắng mặt | **KHÔNG MATCH** | Hai khóa đều thiếu |
| \`yes\` | \`true\` | **KHÔNG MATCH** | \`havingValue="true"\` đòi giá trị \`true\`, không phải \`yes\` |
| \`true\` | \`true\`; thêm một khóa khác = \`false\` | **MATCH** | Khóa ngoài danh sách \`name\` không liên quan |

Trong bảng, “vắng mặt” nghĩa là Environment **không chứa** thuộc tính được kiểm tra; giá trị \`false\` là thuộc tính **có tồn tại nhưng không đạt** điều kiện \`havingValue="true"\`.

### Ví dụ trong application.yml

~~~yaml
app:
  reports:
    enabled: true
    audit-enabled: true
~~~

Hai thuộc tính cùng match, nên phương thức \`@Bean\` có điều kiện ở mục 2 có thể được xét đăng ký.

Chỉ cần đổi một dòng:

~~~yaml
app:
  reports:
    enabled: true
    audit-enabled: false
~~~

Kết quả là **không match**, dù \`app.reports.enabled\` vẫn là \`true\`.

Cấu hình tương đương với \`application.properties\`:

~~~properties
app.reports.enabled=true
app.reports.audit-enabled=true
~~~

Không viết \`name = "enabled,audit-enabled"\` nếu muốn hai khóa: cú pháp đó là một phần tử chuỗi duy nhất, không tạo thành hai tên trong mảng. Hãy dùng **\`name = {"enabled", "audit-enabled"}\`**.

## 4. \`havingValue\` áp dụng giống nhau cho mọi tên

Một annotation **không có mảng giá trị mong đợi riêng cho từng property**. \`havingValue\` là một \`String\` duy nhất và được áp dụng cho **tất cả** tên trong \`name\`.

Ví dụ:

~~~java
@ConditionalOnProperty(
    prefix = "app.reports",
    name = {"enabled", "audit-enabled"},
    havingValue = "true"
)
~~~

Ở đây cả hai thuộc tính cần bằng \`true\`.

Nếu không khai báo \`havingValue\`, giá trị mặc định là chuỗi rỗng \`""\`. Trong chế độ mặc định, mỗi khóa phải **có mặt** và giá trị của nó **khác chuỗi \`false\`**. Không có \`havingValue\` **không đồng nghĩa** với “chỉ chấp nhận đúng \`true\`”.

| Giá trị một khóa đang hiện diện | \`havingValue=""\` (mặc định) | \`havingValue="true"\` | \`havingValue="false"\` | \`havingValue="ready"\` |
| --- | --- | --- | --- | --- |
| \`true\` | Match | Match | Không | Không |
| \`false\` | Không | Không | Match | Không |
| \`ready\` | Match | Không | Không | Match |
| \`yes\` | Match | Không | Không | Không |

Ví dụ sau **có thể match** dù \`mode\` không phải boolean:

~~~java
@ConditionalOnProperty(
    prefix = "app",
    name = {"feature-flag", "mode"}
)
~~~

~~~properties
app.feature-flag=true
app.mode=preview
~~~

Cả \`true\` và \`preview\` đều là giá trị hiện diện, khác \`false\`. Vì vậy nếu cần biểu đạt **hai công tắc boolean phải thật sự bật**, hãy dùng \`havingValue="true"\` rõ ràng. Spring Boot các bản có \`@ConditionalOnBooleanProperty\` cũng cung cấp lựa chọn chuyên cho boolean; cần đối chiếu phiên bản dự án.

### Hai thuộc tính cần hai giá trị mong đợi khác nhau thì sao?

Chẳng hạn cần \`app.reports.enabled=true\` **và** \`app.reports.mode=async\`. Không thể đặt \`havingValue\` thành một mảng như \`{"true", "async"}\` trong cùng một \`@ConditionalOnProperty\`: kiểu của \`havingValue\` là \`String\`.

Ở các phiên bản Spring Boot hỗ trợ annotation lặp lại (ví dụ dòng 3.5 và 4.x), có thể viết:

~~~java
// Hai điều kiện trên cùng phần tử cùng phải match (AND).
@ConditionalOnProperty(
    prefix = "app.reports",
    name = "enabled",
    havingValue = "true"
)
@ConditionalOnProperty(
    prefix = "app.reports",
    name = "mode",
    havingValue = "async"
)
~~~

Đoạn trên là ví dụ annotation; đặt nó trên một phương thức \`@Bean\` hoặc lớp cấu hình. Với các phiên bản cũ không hỗ trợ \`@Repeatable\` cho annotation này, có thể cân nhắc kết hợp bằng cấu trúc condition phù hợp hoặc viết custom \`Condition\`. Luôn kiểm tra Javadoc của **phiên bản Spring Boot đang dùng** trước khi sao chép cú pháp annotation lặp.

## 5. \`matchIfMissing\` khi kiểm tra nhiều tên

Thuộc tính \`matchIfMissing\` điều khiển kết quả **cho từng tên bị thiếu**. Nó **không** thay đổi toán tử AND giữa các tên.

Ví dụ:

~~~java
@ConditionalOnProperty(
    prefix = "app.reports",
    name = {"enabled", "audit-enabled"},
    havingValue = "true",
    matchIfMissing = true
)
~~~

Từng khóa được đánh giá như sau:

- Nếu **có mặt**, khóa phải thỏa \`havingValue="true"\`.
- Nếu **không có mặt**, khóa được xem là đạt vì \`matchIfMissing=true\`.
- Kết quả toàn bộ vẫn bằng **AND** của hai kết quả.

| \`enabled\` | \`audit-enabled\` | Kết quả với \`havingValue="true", matchIfMissing=true\` |
| --- | --- | --- |
| \`true\` | \`true\` | Match |
| \`true\` | Vắng mặt | Match |
| Vắng mặt | \`true\` | Match |
| Vắng mặt | Vắng mặt | Match |
| \`false\` | Vắng mặt | **Không match** |
| Vắng mặt | \`false\` | **Không match** |
| \`true\` | \`false\` | **Không match** |

Điểm dễ sai: **\`matchIfMissing=true\` không bỏ qua giá trị sai của khóa hiện diện.** Nó chỉ thay đổi cách xử lý **vắng mặt**. Với hai khóa đều không tồn tại, điều kiện có thể match, vì mỗi tên thiếu đều được coi là đạt. Nếu yêu cầu nghiệp vụ là *bắt buộc khai báo và bật cả hai*, hãy để \`matchIfMissing=false\` (mặc định).

## 6. Chương trình kiểm thử thực tế bằng ApplicationContextRunner

Ví dụ dưới đây dành cho dự án **Java 17+ / Spring Boot 3.5.x**, có các dependency \`spring-boot-starter\` và \`spring-boot-starter-test\`, dùng JUnit Jupiter và AssertJ. Mỗi lớp auto-configuration trong test tạo một kiểu marker để người học kiểm tra có/không có bean trong context.

Tạo file **\`src/test/java/example/MultiplePropertyConditionTests.java\`**:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class MultiplePropertyConditionTests {

    static final class StrictMarker {
    }

    static final class DefaultMarker {
    }

    static final class MissingAllowedMarker {
    }

    @AutoConfiguration
    static class StrictAutoConfiguration {
        @Bean
        @ConditionalOnProperty(
                prefix = "app.reports",
                name = {"enabled", "audit-enabled"},
                havingValue = "true")
        StrictMarker strictMarker() {
            return new StrictMarker();
        }
    }

    @AutoConfiguration
    static class DefaultAutoConfiguration {
        @Bean
        @ConditionalOnProperty(
                prefix = "app.reports",
                name = {"enabled", "audit-enabled"})
        DefaultMarker defaultMarker() {
            return new DefaultMarker();
        }
    }

    @AutoConfiguration
    static class MissingAllowedAutoConfiguration {
        @Bean
        @ConditionalOnProperty(
                prefix = "app.reports",
                name = {"enabled", "audit-enabled"},
                havingValue = "true",
                matchIfMissing = true)
        MissingAllowedMarker missingAllowedMarker() {
            return new MissingAllowedMarker();
        }
    }

    private final ApplicationContextRunner strictRunner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(StrictAutoConfiguration.class));

    private final ApplicationContextRunner defaultRunner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(DefaultAutoConfiguration.class));

    private final ApplicationContextRunner missingAllowedRunner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(MissingAllowedAutoConfiguration.class));

    @Test
    void bothTrueMatch() {
        strictRunner.withPropertyValues(
                "app.reports.enabled=true",
                "app.reports.audit-enabled=true"
        ).run(context ->
                assertThat(context).hasSingleBean(StrictMarker.class));
    }

    @Test
    void secondFalsePreventsMatch() {
        strictRunner.withPropertyValues(
                "app.reports.enabled=true",
                "app.reports.audit-enabled=false"
        ).run(context ->
                assertThat(context).doesNotHaveBean(StrictMarker.class));
    }

    @Test
    void firstFalsePreventsMatch() {
        strictRunner.withPropertyValues(
                "app.reports.enabled=false",
                "app.reports.audit-enabled=true"
        ).run(context ->
                assertThat(context).doesNotHaveBean(StrictMarker.class));
    }

    @Test
    void missingSecondPropertyPreventsMatch() {
        strictRunner.withPropertyValues(
                "app.reports.enabled=true"
        ).run(context ->
                assertThat(context).doesNotHaveBean(StrictMarker.class));
    }

    @Test
    void bothMissingPreventMatch() {
        strictRunner.run(context ->
                assertThat(context).doesNotHaveBean(StrictMarker.class));
    }

    @Test
    void havingValueTrueRejectsOtherStrings() {
        strictRunner.withPropertyValues(
                "app.reports.enabled=yes",
                "app.reports.audit-enabled=true"
        ).run(context ->
                assertThat(context).doesNotHaveBean(StrictMarker.class));
    }

    @Test
    void defaultModeAcceptsValuesOtherThanFalse() {
        defaultRunner.withPropertyValues(
                "app.reports.enabled=yes",
                "app.reports.audit-enabled=preview"
        ).run(context ->
                assertThat(context).hasSingleBean(DefaultMarker.class));
    }

    @Test
    void defaultModeRejectsAnExplicitFalse() {
        defaultRunner.withPropertyValues(
                "app.reports.enabled=yes",
                "app.reports.audit-enabled=false"
        ).run(context ->
                assertThat(context).doesNotHaveBean(DefaultMarker.class));
    }

    @Test
    void matchIfMissingTrueAllowsOneMissingKey() {
        missingAllowedRunner.withPropertyValues(
                "app.reports.enabled=true"
        ).run(context ->
                assertThat(context).hasSingleBean(MissingAllowedMarker.class));
    }

    @Test
    void matchIfMissingTrueAllowsBothMissingKeys() {
        missingAllowedRunner.run(context ->
                assertThat(context).hasSingleBean(MissingAllowedMarker.class));
    }

    @Test
    void matchIfMissingTrueStillRejectsExplicitFalse() {
        missingAllowedRunner.withPropertyValues(
                "app.reports.enabled=false"
        ).run(context ->
                assertThat(context)
                        .doesNotHaveBean(MissingAllowedMarker.class));
    }
}
~~~

Với Maven Wrapper ở thư mục gốc dự án:

~~~bash
./mvnw test -Dtest=MultiplePropertyConditionTests
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd test -Dtest=MultiplePropertyConditionTests
~~~

**Kết quả kỳ vọng:** **11 test đều PASS**. Không phụ thuộc vào một chuỗi stdout cố định vì log của Maven/Surefire thay đổi theo phiên bản. Điểm kiểm chứng là bean marker chỉ tồn tại đúng trong các trường hợp bảng quyết định cho phép.

**Vì sao dùng \`ApplicationContextRunner\`?** Nó tạo một ApplicationContext nhỏ cho từng tổ hợp property, áp dụng auto-configuration đã chọn và cho phép kiểm chứng trực tiếp việc bean có được đăng ký hay không. Cách này tránh phải khởi động toàn bộ ứng dụng web và đặc biệt phù hợp khi kiểm tra các annotation điều kiện của Spring Boot.

**Lưu ý khi áp dụng dự án:** đối với class \`@AutoConfiguration\` trong thư viện/starter thực tế, cần đăng ký class trong \`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports\`; trong test trên, \`AutoConfigurations.of(...)\` đã nạp trực tiếp class cần kiểm thử. Không bắt buộc tạo tệp imports chỉ để chạy test này.

## 7. Dòng xử lý điều kiện và giới hạn

Về mặt tư duy, Spring Boot có thể được hiểu là đang thực hiện:

~~~text
Tên đầy đủ = prefix + "." + từng name

Đối với từng tên:
  Nếu Environment không có thuộc tính:
    kết quả tên = matchIfMissing
  Nếu Environment có thuộc tính:
    Nếu havingValue là chuỗi rỗng (mặc định):
      kết quả tên = giá trị khác "false"
    Nếu havingValue được chỉ rõ:
      kết quả tên = giá trị khớp havingValue

Kết quả cuối = kết quả tên 1 AND tên 2 AND ... AND tên N
~~~

Đây là **mô hình giải thích**, không phải mã nguồn nguyên văn của Spring Boot. Với ví dụ \`name={"enabled","audit-enabled"}\`, điều kiện đánh giá hai tên đầy đủ **riêng biệt** rồi mới đưa ra kết quả chung.

### Đặt annotation ở đâu?

- Trên **\`@Bean\`**: nếu điều kiện không match, chỉ bean do phương thức đó định nghĩa bị bỏ qua; bean khác trong cùng lớp cấu hình vẫn có thể được xét.
- Trên lớp **\`@AutoConfiguration\`** hoặc lớp **\`@Configuration\`**: nếu điều kiện không match, các bean thuộc cấu hình đó sẽ không được đăng ký thông qua lớp ấy.
- Việc đánh giá diễn ra khi Spring xử lý điều kiện cấu hình, nên **thay đổi một property trong file sau khi ứng dụng đã khởi động thường không tự tạo hoặc xóa bean**. Cần khởi động lại hoặc sử dụng cơ chế làm mới cấu hình riêng nếu dự án thực sự có hỗ trợ.

### Các trường hợp không nên dùng máy móc

**Nhiều tên không phải OR.** Khi nghiệp vụ là "bật nếu A **hoặc** B", một \`name={"A","B"}\` là sai về logic. Hãy thiết kế điều kiện OR riêng, chẳng hạn custom \`Condition\` hoặc công cụ kết hợp condition tương thích với phiên bản Boot.

**Kiểm tra collection/map:** Javadoc cảnh báo \`@ConditionalOnProperty\` không đáng tin cậy để suy ra sự tồn tại của collection chỉ từ các phần tử indexed. Chẳng hạn một khóa \`app.targets[0]\` tồn tại không nhất thiết khiến kiểm tra \`name="targets"\` match. Với yêu cầu về dữ liệu collection/map, dùng cơ chế binding và điều kiện chuyên biệt phù hợp.

**Thuộc tính được ghi ở nhiều nguồn:** Spring Environment lấy giá trị theo thứ tự ưu tiên các PropertySource. Một khóa có thể đã được đặt trong \`application.yml\` nhưng bị override bởi tham số dòng lệnh hay biến môi trường. Điều kiện kiểm tra **giá trị hiệu lực mà Environment trả về**, không chỉ nội dung một file.

**Ký pháp tên:** dùng dashed notation theo khuyến nghị của Spring Boot. Với môi trường có biến môi trường, cơ chế ánh xạ tên tùy PropertySource/Boot có thể ảnh hưởng đến giá trị được resolve; tốt nhất kiểm tra chính xác giá trị trong Environment khi gỡ lỗi.

## 8. Lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Chỉ bật \`enabled=true\` nhưng bean vẫn vắng mặt | Thiếu \`audit-enabled\` và \`matchIfMissing=false\` | Khai báo cả hai, hoặc cân nhắc lại yêu cầu nghiệp vụ |
| \`enabled=true\`, \`audit-enabled=false\` nhưng kỳ vọng có bean | Nhầm nhiều \`name\` là OR | Hiểu AND; nếu cần OR hãy tạo điều kiện khác |
| \`enabled=yes\` nhưng \`havingValue="true"\` không match | Dùng so sánh giá trị cụ thể, \`yes\` khác \`true\` | Đặt giá trị \`true\` theo yêu cầu |
| Đặt \`name="enabled,audit-enabled"\` | Một chuỗi đơn thay vì mảng hai chuỗi | Dùng \`name={"enabled", "audit-enabled"}\` |
| Hai thuộc tính cần hai giá trị khác nhau | Một \`havingValue\` áp dụng cho tất cả | Tách điều kiện có \`havingValue\` khác nhau nếu phiên bản hỗ trợ |
| \`matchIfMissing=true\` khiến bean xuất hiện khi chưa cấu hình | Cả hai khóa thiếu vẫn được xem là đạt | Dùng mặc định \`false\` nếu phải khai báo rõ |
| Đặt annotation trên cả lớp khiến nhiều bean biến mất | Phạm vi điều kiện bao trùm toàn cấu hình | Đưa điều kiện xuống \`@Bean\` cần kiểm tra |
| Không khớp dù file YAML có vẻ chính xác | Giá trị hiệu lực bị override hoặc tên thuộc tính khác | Kiểm tra Environment và báo cáo điều kiện |

### Chẩn đoán bằng Spring Boot

Khi không thấy bean như mong đợi, có thể bật **debug** khi chạy ứng dụng Spring Boot:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Hoặc chạy file JAR đã đóng gói với \`--debug\`. Báo cáo điều kiện (**Conditions Evaluation Report**) giúp thấy auto-configuration nào match/không match và nguyên nhân. Nếu dự án dùng Actuator và cho phép truy cập endpoint tương ứng, endpoint **\`/actuator/conditions\`** cũng cung cấp dữ liệu điều kiện. Không nên công khai các endpoint chẩn đoán nội bộ nếu môi trường triển khai không yêu cầu.

Trong test, nên ưu tiên **\`ApplicationContextRunner\`** với các trường hợp **đủ cả khóa, thiếu từng khóa, có giá trị false, và cả hai thiếu**. Những trường hợp này phát hiện nhanh lỗi hiểu nhầm AND với OR.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** \`@ConditionalOnProperty(prefix="app", name={"a","b"}, havingValue="true")\` và cấu hình \`app.a=true\`, \`app.b=false\`. Bean có được tạo không?

**Đáp án:** Không. Hai điều kiện con có quan hệ **AND** và \`b\` không thỏa giá trị mong đợi.

**Câu 2.** Vẫn annotation trên nhưng chỉ có \`app.a=true\`, còn \`app.b\` hoàn toàn vắng mặt. Có match không?

**Đáp án:** Không. \`matchIfMissing\` mặc định là \`false\`, nên thiếu \`b\` khiến điều kiện chung không match.

**Câu 3.** Nếu đặt \`matchIfMissing=true\` thì hai khóa đều vắng mặt có match không?

**Đáp án:** Có, vì mỗi khóa thiếu được coi là đạt. Tuy nhiên một khóa hiện diện với giá trị \`false\` vẫn làm điều kiện không match nếu \`havingValue="true"\`.

**Câu 4.** Nếu bỏ \`havingValue\`, \`app.a=preview\` và \`app.b=true\` có match không?

**Đáp án:** Có, bởi mặc định mỗi khóa cần hiện diện và giá trị của nó không bằng \`false\`.

**Câu 5.** Cần \`app.a=true\` và \`app.b=async\`. Có thể đặt \`havingValue={"true","async"}\` không?

**Đáp án:** Không. \`havingValue\` có kiểu \`String\`, không phải \`String[]\`. Hãy tách điều kiện theo từng giá trị mong đợi (khi phiên bản hỗ trợ annotation lặp) hoặc xây dựng condition tổng hợp phù hợp.

## 10. Tài liệu tham khảo chính thức

- Spring Boot 3.5 Javadoc — \`@ConditionalOnProperty\`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 4.0 Javadoc — \`@ConditionalOnProperty\`: https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot Reference — Creating Your Own Auto-configuration, mục Property Conditions: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
