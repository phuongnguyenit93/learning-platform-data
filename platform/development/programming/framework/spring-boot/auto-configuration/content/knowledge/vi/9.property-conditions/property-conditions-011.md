# Thiết kế khóa bật tính năng rõ ràng và lập bảng trường hợp đầu vào cho điều kiện

## 1. Mục tiêu: một feature flag phải có hợp đồng có thể kiểm chứng

Trong Spring Boot Auto Configuration, ta thường muốn chỉ tạo bean của một tính năng khi người vận hành **chủ động bật** tính năng đó. Ví dụ: module báo cáo chỉ đăng ký `ReportService` khi thuộc tính `demo.reports.enabled=true`.

Bài học thuộc nhóm **Điều kiện thuộc tính**, tập trung vào hai kỹ năng đi cùng nhau:

1. **Thiết kế khóa bật tính năng** có tên, ý nghĩa, mặc định và hành vi khi gặp giá trị sai rõ ràng.
2. **Lập bảng trường hợp đầu vào** cho `@ConditionalOnProperty` để dự đoán chính xác khi nào bean/cấu hình sẽ được đăng ký, rồi kiểm chứng bằng một ví dụ chạy được.

Khác biệt giữa **không khai báo thuộc tính**, **khai báo `false`**, **khai báo rỗng** và **khai báo chuỗi lạ** là trọng tâm. Các giá trị này có thể dẫn đến kết quả khác nhau tùy cách khai báo điều kiện.

## 2. Cách @ConditionalOnProperty thực sự đánh giá điều kiện

Annotation `org.springframework.boot.autoconfigure.condition.ConditionalOnProperty` kiểm tra giá trị thuộc tính trong Spring `Environment` khi Spring đang xây dựng application context.

Một điều kiện rõ ràng cho tính năng chỉ bật khi nhận giá trị `true`:

```java
@ConditionalOnProperty(
    prefix = "demo.reports",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
```

Đây là đoạn annotation minh họa; nó phải được đặt lên lớp cấu hình hoặc phương thức `@Bean` thích hợp. Khóa hoàn chỉnh là `demo.reports.enabled`:

- `prefix = "demo.reports"`: phần đầu của khóa; Spring thêm dấu chấm khi ghép nếu cần.
- `name = "enabled"`: phần tên còn lại. `value` là alias của `name`, nên chỉ cần dùng một trong hai.
- `havingValue = "true"`: **chỉ khớp khi giá trị thuộc tính bằng chuỗi `true`, không phân biệt chữ hoa/chữ thường**.
- `matchIfMissing = false`: **không khớp khi khóa vắng mặt** trong `Environment`.

Bốn thuộc tính trên có các mặc định quan trọng:

| Thuộc tính annotation | Mặc định | Ý nghĩa |
|---|---|---|
| `prefix` | `""` | Không có prefix |
| `name` / `value` | `{}` | Cần chỉ định tên khóa cần kiểm tra |
| `havingValue` | `""` | Nếu không chỉ định, giá trị hiện diện phải **khác `false`** |
| `matchIfMissing` | `false` | Khóa bị thiếu thì điều kiện không khớp |

**Đặc biệt:** Mặc định `havingValue=""` **không đồng nghĩa** với `havingValue="true"`. Với mặc định, chuỗi `yes`, `1`, `unexpected`, thậm chí chuỗi rỗng có thể làm điều kiện khớp vì chúng không bằng `false`. Vì vậy, với một khóa bật/tắt kiểu Boolean mong muốn, nên khai báo `havingValue="true"` một cách tường minh.

Spring Boot so sánh giá trị theo chuỗi, không nên suy diễn đây là phép chuyển đổi Boolean với mọi từ đồng nghĩa như `yes` hay `1`. Cũng đừng diễn giải `matchIfMissing` như một giá trị cấu hình mặc định: nó chỉ ảnh hưởng khi **không tìm thấy khóa**.

### Quy tắc với nhiều tên khóa

Nếu khai báo:

```java
@ConditionalOnProperty(
    prefix = "demo.reports",
    name = {"enabled", "storage-ready"},
    havingValue = "true",
    matchIfMissing = false
)
```

thì **tất cả** khóa `demo.reports.enabled` và `demo.reports.storage-ready` đều phải khớp. Đây là phép **AND**, không phải OR. Nếu một khóa vắng mặt hoặc có giá trị `false` thì cả điều kiện không khớp. Chỉ sử dụng nhiều khóa khi thật sự muốn tất cả điều kiện cùng đúng; nếu ý định là “một trong nhiều khóa”, cần thiết kế điều kiện khác.

## 3. Thiết kế khóa bật tính năng có hợp đồng rõ ràng

Lấy ví dụ một tính năng tạo báo cáo theo lô:

| Thành phần hợp đồng | Lựa chọn cho ví dụ | Lý do |
|---|---|---|
| Tên khóa | `demo.reports.enabled` | Tên theo namespace và chức năng cụ thể |
| Kiểu giá trị mong muốn | Boolean logic: `true` hoặc `false` | Tránh trạng thái mơ hồ |
| Giá trị mặc định nghiệp vụ | `false` | Tính năng chỉ chạy khi được bật chủ động |
| Điều kiện kích hoạt | `havingValue="true"` | Không coi `yes`, `1` hoặc lỗi gõ là bật |
| Thiếu khóa | `matchIfMissing=false` | Cấu hình vắng mặt không âm thầm bật |
| Khi tắt | Không tạo bean `ReportService` tùy chọn | Thể hiện ranh giới tính năng tại lúc khởi tạo context |
| Thời điểm áp dụng | Khi khởi tạo/refresh context | Thay đổi cấu hình sau khi context đã chạy không mặc nhiên đánh giá lại điều kiện |

**Nguyên tắc đặt tên và diễn đạt:**

- Dùng tên đầy đủ, ngắn gọn và một nghĩa: `demo.reports.enabled` diễn đạt “bật tính năng reports” rõ hơn `reports`, `flag1` hay `disable-reporting=false`.
- Ưu tiên khóa khẳng định `enabled` với giá trị `true/false`. Tránh hai lần phủ định như `disable-feature=false` khiến người đọc dễ đảo nghĩa.
- Dùng dạng khóa chuẩn **lowercase kebab-case** cho từng đoạn có nhiều từ, ví dụ `demo.report-export.enabled`, và phân tách namespace bằng dấu chấm.
- Quyết định **mặc định khi vắng mặt** trước khi viết annotation. Với tính năng mới có chi phí, phụ thuộc hoặc tác dụng phụ, thường chọn rõ ràng trạng thái tắt khi thiếu; nếu tương thích ngược đòi hỏi bật mặc định thì phải tài liệu hóa lý do và thử trường hợp thiếu.
- Ghi rõ **đơn vị cấu hình**: bật bean trên toàn application context, không phải công tắc cho từng HTTP request/người dùng. Nếu cần bật/tắt theo người dùng hay ngay lập tức khi hệ thống đang chạy, cần cơ chế runtime riêng.
- Đặt tên property và bean theo đúng chức năng. Nếu chỉ vô hiệu hóa bean, những nơi inject bean đó cũng phải được thiết kế để chịu được việc bean không tồn tại hoặc có một implementation mặc định phù hợp.

Ví dụ `application.yml` (chủ động tắt ở cấu hình mặc định):

```yaml
demo:
  reports:
    enabled: false
```

Để bật trong môi trường được chọn, người vận hành có thể ghi:

```properties
demo.reports.enabled=true
```

Trong một ứng dụng Spring Boot chạy bằng `SpringApplication`, có thể đặt thuộc tính từ command line như `--demo.reports.enabled=true`. Việc ghi trong file, môi trường hay command line đều là nguồn cấu hình; **giá trị cuối cùng trong `Environment` theo thứ tự ưu tiên nguồn cấu hình** mới được điều kiện xét. Ví dụ, option command line mặc định có thể ghi đè giá trị từ `application.yml`.

Với khóa ví dụ này, biến môi trường thông dụng tương ứng là `DEMO_REPORTS_ENABLED=true`. Quy tắc đặt tên biến môi trường trong Spring Boot là đổi dấu chấm thành gạch dưới, bỏ dấu gạch ngang trong tên thuộc tính, rồi viết hoa; hãy kiểm tra mapping thực tế nếu dùng tên phức tạp.

## 4. Ma trận đầu vào: đừng chỉ thử true và false

Để không nhầm lẫn, phân biệt bốn cách khai báo điều kiện cùng kiểm tra khóa `demo.reports.enabled`:

- **A — Bật tường minh:** `havingValue="true", matchIfMissing=false`. Đây là hợp đồng của bài.
- **B — Mặc định của annotation:** `havingValue="", matchIfMissing=false`. Chỉ loại giá trị `false` khi khóa có mặt.
- **C — Bật nếu thiếu:** `havingValue="true", matchIfMissing=true`. Có thể hợp cho tính năng vốn bật mặc định, nhưng phải chọn có chủ đích.
- **D — Khớp false hoặc thiếu:** `havingValue="false", matchIfMissing=true`. Minh họa riêng về nhánh tắt; không đồng nghĩa “mọi thứ khác true”.

Trong bảng, **Có** = điều kiện khớp và bean/cấu hình *có thể* được đăng ký; **Không** = điều kiện không khớp. Giả sử không có các điều kiện khác cản trở bean.

| Giá trị thực tế trong Environment | A: true + thiếu=false | B: mặc định + thiếu=false | C: true + thiếu=true | D: false + thiếu=true |
|---|:---:|:---:|:---:|:---:|
| **Không có khóa** | Không | Không | **Có** | **Có** |
| `"true"` | **Có** | **Có** | **Có** | Không |
| `"TRUE"` | **Có** | **Có** | **Có** | Không |
| `"false"` | Không | Không | Không | **Có** |
| `"FALSE"` | Không | Không | Không | **Có** |
| `""` (chuỗi rỗng có tồn tại) | Không | **Có** | Không | Không |
| `"yes"` | Không | **Có** | Không | Không |
| `"1"` | Không | **Có** | Không | Không |
| `"0"` | Không | **Có** | Không | Không |
| `"unexpected"` | Không | **Có** | Không | Không |

Lưu ý trong bảng:
- **Không có khóa** khác với **khóa có giá trị rỗng**. `matchIfMissing` chỉ được tham khảo khi khóa thực sự không hiện diện.
- `"TRUE"` và `"FALSE"` được so sánh không phân biệt hoa/thường. Dù vậy, trong file cấu hình nên thống nhất ghi `true` và `false` bằng chữ thường để dễ đọc.
- Với `havingValue=""` mặc định, bất kỳ chuỗi nào **không bằng `false`** đều khớp. Đây là nguyên nhân lỗi rất thường gặp nếu dùng annotation thiếu `havingValue="true"`.
- Một giá trị lạ có thể khiến điều kiện A **không tạo bean mà không ném lỗi cấu hình**. Nếu hợp đồng vận hành yêu cầu từ chối giá trị không hợp lệ ngay khi khởi động, phải bổ sung validation cho cấu hình hoặc điều kiện tùy chỉnh; bản thân điều kiện trên không phải bộ kiểm định toàn bộ input.

### Ma trận nghiệp vụ cần cam kết cho tính năng reports

| Tình huống kiểm thử | Cấu hình minh họa | Kết quả mong đợi với điều kiện A |
|---|---|---|
| Không cấu hình | Xóa khóa khỏi mọi PropertySource áp dụng | Tính năng **tắt** |
| Bật chuẩn | `demo.reports.enabled=true` | Tính năng **bật** |
| Tắt chuẩn | `demo.reports.enabled=false` | Tính năng **tắt** |
| Biến thể hoa/thường | `demo.reports.enabled=TRUE` | **Bật**, do so sánh không phân biệt hoa/thường |
| Giá trị rỗng | `demo.reports.enabled=` | **Tắt** |
| Lỗi gõ | `demo.reports.enabled=treu` | **Tắt**; xem xét bổ sung validation để báo lỗi rõ hơn |
| Giá trị Boolean không chuẩn | `demo.reports.enabled=yes` hoặc `1` | **Tắt** |
| File mặc định false, ghi đè true | Một PropertySource ưu tiên cao hơn đặt `true` | **Bật**, vì Spring dùng giá trị cuối cùng trong Environment |
| File mặc định true, ghi đè false | Một PropertySource ưu tiên cao hơn đặt `false` | **Tắt** |

Khi đưa tính năng vào CI, nên biến các dòng này thành phép thử có dự đoán được: **input cụ thể → context có hay không có bean → ứng dụng có còn khởi động được khi tính năng tắt?** Chỉ thử `true/false` là thiếu các ca quan trọng.

## 5. Ví dụ chạy được với Java 17 và Spring Boot 3.3

Chương trình sau tạo một `AnnotationConfigApplicationContext` mới **cho từng input**; mỗi lần chỉ thêm một giá trị property (hoặc không thêm để mô phỏng thiếu khóa), rồi kiểm tra bean `reportService` có được tạo hay không.

Cấu trúc dự án Maven tối thiểu:

```text
feature-flag-matrix/
├── pom.xml
└── src/main/java/demo/FeatureFlagMatrixDemo.java
```

**`pom.xml`** (chọn Spring Boot 3.3.13 làm phiên bản minh họa ổn định trong dòng 3.3):

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

    <groupId>demo</groupId>
    <artifactId>feature-flag-matrix</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/FeatureFlagMatrixDemo.java`:**

```java
package demo;

import java.util.Map;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;

public class FeatureFlagMatrixDemo {

    private static final String FLAG = "demo.reports.enabled";

    public static class ReportService {
        public String report() {
            return "Report ready";
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ReportConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "demo.reports",
                name = "enabled",
                havingValue = "true",
                matchIfMissing = false)
        public ReportService reportService() {
            return new ReportService();
        }
    }

    private static void check(String label, String value) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            if (value != null) {
                context.getEnvironment().getPropertySources().addFirst(
                        new MapPropertySource("scenario",
                                Map.of(FLAG, value)));
            }

            context.register(ReportConfiguration.class);
            context.refresh();

            System.out.println(label + " -> "
                    + context.containsLocalBean("reportService"));
        }
    }

    public static void main(String[] args) {
        check("(missing)", null);
        check("true", "true");
        check("TRUE", "TRUE");
        check("false", "false");
        check("FALSE", "FALSE");
        check("(empty)", "");
        check("yes", "yes");
        check("1", "1");
        check("unexpected", "unexpected");
    }
}
```

Từ thư mục chứa `pom.xml`, yêu cầu JDK 17+ và Maven, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.FeatureFlagMatrixDemo
```

Các dòng chương trình in ra `stdout`:

```text
(missing) -> false
true -> true
TRUE -> true
false -> false
FALSE -> false
(empty) -> false
yes -> false
1 -> false
unexpected -> false
```

**Vì sao mã cho đúng kết quả?**

1. Ở mỗi lần gọi `check`, chương trình tạo context mới, tránh bean hoặc PropertySource của tình huống trước ảnh hưởng tình huống sau.
2. Giá trị `null` được dùng **chỉ trong mã kiểm thử** để biểu diễn *không thêm khóa vào Environment*. Giá trị đó không được đưa vào `Map.of` vì Java không chấp nhận value null trong `Map.of`.
3. `MapPropertySource` đặt giá trị cụ thể vào Environment trước `context.refresh()`, nên `@ConditionalOnProperty` đánh giá đúng input.
4. `context.containsLocalBean("reportService")` xác nhận bean có được đăng ký ở chính context kiểm thử. Chỉ khi chuỗi đầu vào bằng `true` không phân biệt hoa/thường thì điều kiện A khớp.
5. Context đóng sau từng ca nhờ `try-with-resources`. Đây là **minh họa kiểm tra điều kiện ở giai đoạn khởi tạo**, không phải API để bật/tắt bean nóng ở runtime.

Ví dụ dùng trực tiếp các class Spring cần thiết qua `spring-boot-starter`; không đòi database, HTTP server hay viết `@SpringBootApplication`. Nếu muốn kiểm thử auto-configuration thật trong mã nguồn Spring Boot, một lựa chọn thuận tiện khác là `ApplicationContextRunner` của `spring-boot-test`: truyền `withPropertyValues(...)`, kiểm tra bean bằng AssertJ, và dùng một runner không có khóa để thử trường hợp thiếu.

## 6. Đưa điều kiện vào auto-configuration thực tế

Đoạn dưới đây minh họa cách điều kiện bảo vệ một bean trong cấu hình tự động. `ReportService` là kiểu ứng dụng tự định nghĩa trong ví dụ ở trên:

```java
@AutoConfiguration
public class ReportsAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.reports",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    @ConditionalOnMissingBean(ReportService.class)
    ReportService reportService() {
        return new ReportService();
    }
}
```

Đây là **đoạn minh họa bên trong một starter/auto-configuration**, không phải file Java chạy độc lập: cần import `@AutoConfiguration`, `@Bean`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean`, có kiểu `ReportService` và đăng ký auto-configuration bằng cơ chế của Spring Boot.

Hai điều kiện mang hai trách nhiệm khác nhau:

- `@ConditionalOnProperty`: **cờ tính năng có cho phép tạo bean này không?**
- `@ConditionalOnMissingBean`: **nếu tính năng được bật, người dùng đã cung cấp bean thay thế phù hợp chưa?**

Với cờ tắt, bean mặc định không được tạo, dù chưa có bean cùng kiểu. Với cờ bật và người dùng đã cung cấp bean phù hợp, điều kiện `@ConditionalOnMissingBean` giúp auto-configuration nhường quyền.

Hãy kiểm thử cả trường hợp tính năng tắt nhưng thành phần khác vẫn bắt buộc inject `ReportService`. Nếu một controller/service không thể hoạt động khi thiếu bean, cần thiết kế luồng phụ thuộc phù hợp: bảo vệ cả cấu hình liên quan, dùng implementation thay thế, hoặc thay đổi ranh giới optional dependency. “Bean không được tạo” không có nghĩa “toàn ứng dụng chắc chắn khởi động thành công”.

## 7. Vận hành và kiểm soát cấu hình qua nhiều môi trường

Trong hệ thống thật, cùng một khóa có thể được đặt trong `application.yml`, file profile-specific, biến môi trường, config server hoặc command line. Spring Boot hợp nhất các PropertySource theo thứ tự ưu tiên; **điều kiện dùng giá trị thắng cuộc**.

Ví dụ về hợp đồng triển khai:

| Môi trường | Cấu hình đề xuất | Mục đích |
|---|---|---|
| Local development | `demo.reports.enabled=false` | Không bật tác vụ báo cáo không cần thiết |
| Integration test bật feature | `demo.reports.enabled=true` | Kiểm tra nhánh có bean |
| Integration test tắt feature | `demo.reports.enabled=false` hoặc không khai báo | Kiểm tra nhánh không có bean |
| Production | Giá trị được quyết định rõ trong cấu hình triển khai | Tránh phụ thuộc vào giả định của người vận hành |

Đây là **gợi ý hợp đồng**, không phải quy tắc bắt buộc cho mọi tính năng. Nếu feature phải mặc định bật do yêu cầu tương thích ngược, ghi rõ lựa chọn `matchIfMissing=true` trong tài liệu và bổ sung test cho trường hợp không có khóa. Không thay đổi `matchIfMissing` tùy tiện vì đó là thay đổi hành vi deploy.

Từ góc độ vận hành, nên tài liệu hóa thêm: chủ sở hữu cờ, môi trường được phép bật, tác dụng phụ khi bật, phụ thuộc cần có, cách kiểm tra bean/health và kế hoạch dọn cờ khi feature đã ổn định. Với cờ tạm thời phục vụ rollout, theo dõi để tránh tích lũy những nhánh cấu hình không còn được dùng.

**Cờ bật bean là điều kiện khi khởi tạo context.** Sửa file/biến môi trường khi ứng dụng đang chạy không khiến `@ConditionalOnProperty` tự kiểm tra lại rồi thêm/xóa bean. Thông thường cần tạo lại hoặc khởi động lại context; nếu cần điều khiển runtime, dùng một cơ chế runtime feature flag riêng và thiết kế nhất quán trạng thái của các request đang xử lý.

**Không dùng feature flag làm ranh giới phân quyền hay bảo mật.** Có/không có bean chỉ là một khía cạnh của cấu hình ứng dụng; quyền truy cập vẫn cần được kiểm soát tại những điểm thích hợp.

## 8. Các lỗi thường gặp và cách phát hiện

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| Gõ `enabled=yes` mà bean vẫn được tạo | Dùng `havingValue=""` mặc định, chỉ loại `false` | Đặt `havingValue="true"` |
| Không khai báo flag nhưng bean vẫn có | `matchIfMissing=true`, hoặc bean được tạo từ nơi khác | Xác nhận default, xem bean definitions và báo cáo condition |
| Đã ghi `false` nhưng bean vẫn có | Bean khác cung cấp cùng kiểu/tên, hoặc PropertySource ưu tiên cao ghi đè | Kiểm tra giá trị cuối trong Environment và nguồn bean |
| Cấu hình `true` nhưng bean không xuất hiện | Sai tên khóa, bị override, sai chữ trong `havingValue`, điều kiện bổ sung, hoặc lỗi đăng ký | Kiểm tra full key, danh sách condition và cấu hình được import |
| Hai giá trị `enabled` và `storage-ready`, một true một false; bean không có | Khi `name` là mảng, mọi khóa phải khớp | Xác nhận định nghĩa AND, lập test đủ mọi tổ hợp |
| Test chỉ chạy với `true/false` | Bỏ sót missing, blank, typo và case | Dùng ma trận đầu vào ở mục 4 |
| Mong thay đổi flag tức thời sau khi startup | Condition đã được đánh giá trong giai đoạn tạo bean definitions | Thiết kế cơ chế runtime riêng hoặc restart context |
| Thuộc tính danh sách chỉ có `values[0]` mà condition trên `values` không khớp | `@ConditionalOnProperty` không kiểm tra collection một cách đáng tin cậy | Sử dụng custom condition cho yêu cầu trên collection |

### Cách quan sát điều kiện

Trong ứng dụng Spring Boot thông thường, bật chế độ debug bằng `--debug` để xem **Condition Evaluation Report**. Nếu dùng Spring Boot Actuator và đã bật/expose endpoint tương ứng, `/actuator/conditions` cung cấp thông tin condition matches để điều tra.

Khi cần chẩn đoán chính xác, ghi nhận cùng lúc: tên khóa đầy đủ, giá trị cuối cùng trong Environment (không in secret), các thuộc tính `havingValue` / `matchIfMissing`, tên bean cần xuất hiện, và điều kiện bổ sung như `@ConditionalOnMissingBean`. Không chỉ nhìn mỗi dòng `application.yml` vì có thể bị ghi đè từ nguồn khác.

## 9. Bài tập áp dụng

**Bài tập 1 — Nguy cơ bật ngoài dự kiến.** Một cấu hình dùng:

```java
@ConditionalOnProperty(prefix = "demo.reports", name = "enabled")
```

Người vận hành nhập `demo.reports.enabled=treu`. Bean có thể được tạo không?

**Đáp án:** Có. Vì mặc định `havingValue=""` chỉ loại giá trị `false`, chuỗi `treu` vẫn khớp. Nếu mong chỉ chấp nhận bật khi `true`, sửa thành `havingValue="true", matchIfMissing=false`.

**Bài tập 2 — Mặc định khi thiếu.** Cấu hình có `havingValue="true", matchIfMissing=true`, nhưng file deploy đặt `enabled=false`. Điều kiện khớp không?

**Đáp án:** Không. `matchIfMissing=true` chỉ có tác dụng **khi thiếu khóa**; ở đây khóa có tồn tại và chứa `false`.

**Bài tập 3 — Phải bật hai điều kiện.** Có `name={"enabled", "storage-ready"}`, `havingValue="true"`. Người vận hành đặt `enabled=true`, `storage-ready=false`. Kết quả?

**Đáp án:** Không khớp; mọi tên khóa đều phải khớp. Khi cả hai là `true` mới thỏa điều kiện.

**Bài tập 4 — Ghi đè môi trường.** `application.yml` có `enabled=false` nhưng lệnh khởi động Spring Boot truyền `--demo.reports.enabled=true`. Kết quả?

**Đáp án:** Với cấu hình `SpringApplication` thông thường cho phép property từ command line, giá trị command line có ưu tiên cao hơn file config nên điều kiện bật tường minh khớp. Nếu ứng dụng tùy chỉnh tắt khả năng thêm property từ command line, cần xét thứ tự PropertySource thực tế.

## 10. Ghi nhớ và checklist trước khi bàn giao một feature flag

1. Khóa có nghĩa rõ ràng, ổn định: `<namespace>.<feature>.enabled`.
2. Định nghĩa hành vi của **true, false, missing, blank, giá trị lạ**.
3. Với bật tường minh, sử dụng `havingValue="true", matchIfMissing=false`.
4. Không quên mặc định `havingValue=""` chỉ kiểm tra giá trị **khác false**.
5. Lập ma trận và kiểm thử ít nhất: thiếu khóa, true, false, chữ hoa, chuỗi rỗng, chuỗi không hợp lệ, ghi đè từ nguồn ưu tiên cao.
6. Kiểm tra cả **bean có được tạo hay không** và **ứng dụng có khởi động đúng khi tính năng tắt**.
7. Ghi rõ feature flag của auto-configuration được đánh giá khi tạo context, không tự hoạt động như công tắc runtime.

### Tài liệu chính thức

- [Spring Boot 3.3 — ConditionalOnProperty](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
