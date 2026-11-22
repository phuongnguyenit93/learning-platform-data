# Đọc ConditionEvaluationReport để kiểm chứng cấu hình

> **Chương:** Tùy biến tự động cấu hình
> **Module:** `SPRING_CLOUD_CORE` — hiểu các nền tảng cốt lõi của Spring Cloud trong hệ thống phân tán, đặc biệt Spring Cloud Commons, Context, cấu hình bên ngoài và tương thích phiên bản với Spring Boot. Người học tìm hiểu refresh scope, discovery, service registry, giao tiếp dịch vụ và cách kiểm thử, vận hành các abstraction chung.
> **Trọng tâm:** `ConditionEvaluationReport` cho biết các điều kiện của Spring Boot auto-configuration đã được đánh giá như thế nào, vì sao một cấu hình được áp dụng hoặc bị bỏ qua. Bài học hướng dẫn đọc báo cáo từ log, Actuator và test để xác định dependency, bean hoặc property đang khiến cấu hình hoạt động khác kỳ vọng.

## 1. Vì sao cần đọc ConditionEvaluationReport?

Spring Boot tự động cấu hình nhiều thành phần dựa trên classpath, bean hiện có, property trong `Environment`, loại ứng dụng và các điều kiện khác. Ví dụ, một auto-configuration có thể chỉ tạo bean khi thư viện cần thiết xuất hiện trên classpath; một bean mặc định có thể chỉ được tạo nếu ứng dụng chưa khai báo bean thay thế.

Khi một thành phần không xuất hiện, chỉ nhìn vào kết quả cuối cùng thường chưa đủ để biết nguyên nhân. Có thể thiếu dependency, property không có giá trị mong đợi, ứng dụng đang chạy ở chế độ non-web, bean do người dùng khai báo khiến auto-configuration lùi lại hoặc lớp cấu hình đã bị exclude.

`ConditionEvaluationReport` ghi lại kết quả đánh giá các condition mà Spring Boot sử dụng cho cấu hình và auto-configuration. Báo cáo cho biết:

- source cấu hình hoặc bean method nào được kiểm tra;
- condition nào match và condition nào không match;
- thông điệp giải thích kết quả;
- các auto-configuration class bị exclude;
- các lớp được đánh giá nhưng không có điều kiện;
- quan hệ với parent context khi có context hierarchy.

Báo cáo giúp trả lời câu hỏi: *Spring Boot đã quyết định điều gì, dựa trên điều kiện nào?* Nó là công cụ chẩn đoán quá trình cấu hình, không phải danh sách đầy đủ mọi bean đang hoạt động và cũng không thay thế việc kiểm tra hành vi của ứng dụng.

### Kết quả học tập

Sau bài này, người học có thể:

1. giải thích vai trò của `ConditionEvaluationReport` trong auto-configuration;
2. bật báo cáo bằng `--debug` hoặc `-Ddebug`;
3. đọc `positiveMatches` và `negativeMatches` từ Actuator;
4. hiểu ý nghĩa condition name, message và source;
5. nhận diện lỗi do classpath, bean, property, resource hoặc web application condition;
6. kiểm tra danh sách exclusions và context hierarchy;
7. truy vấn report qua API khi cần chẩn đoán trong test;
8. sử dụng `ApplicationContextRunner` và `ConditionEvaluationReportLoggingListener`;
9. xây dựng quy trình kiểm chứng cấu hình có thể lặp lại.

## 2. Condition và kết quả đánh giá

### 2.1. Auto-configuration sử dụng điều kiện

Auto-configuration class thường được đánh dấu bằng `@AutoConfiguration`. Spring Boot nạp các candidate được liệt kê trong file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` của các JAR tương ứng. Các annotation `@Conditional*` xác định khi nào cấu hình được áp dụng.

Một số điều kiện thường gặp:

| Annotation/condition | Câu hỏi được kiểm tra |
| --- | --- |
| `@ConditionalOnClass` | Class được yêu cầu có trên classpath không? |
| `@ConditionalOnMissingClass` | Class được chỉ định có vắng mặt không? |
| `@ConditionalOnBean` | Bean phù hợp đã có trong BeanFactory chưa? |
| `@ConditionalOnMissingBean` | Chưa có bean phù hợp để auto-configuration tạo bean mặc định phải không? |
| `@ConditionalOnProperty` | Property có tồn tại và thỏa giá trị yêu cầu không? |
| `@ConditionalOnResource` | Resource được chỉ định có tồn tại không? |
| `@ConditionalOnWebApplication` | Context có phải web application theo loại yêu cầu không? |
| `@ConditionalOnExpression` | Biểu thức SpEL có trả về true không? |

Một auto-configuration có thể kết hợp nhiều điều kiện. Chỉ cần một điều kiện bắt buộc không match, cấu hình hoặc bean method tương ứng có thể không được đăng ký.

### 2.2. ConditionOutcome

Mỗi lần đánh giá condition có một kết quả `ConditionOutcome`. Kết quả gồm trạng thái match và thông điệp giải thích.

- `isMatch()` trả về `true` nếu condition match.
- `getMessage()` trả về thông điệp giải thích; giá trị có thể null nếu condition không cung cấp message.

Ví dụ message:

```text
@ConditionalOnClass found required class 'com.acme.Client'
@ConditionalOnProperty (acme.client.enabled=true) matched
@ConditionalOnMissingBean (types: com.acme.Client) found beans of type 'com.acme.Client'
@ConditionalOnClass did not find required class 'com.acme.Client'
```

Hãy đọc message như bằng chứng về điều kiện đã kiểm tra. Ví dụ, message của `@ConditionalOnMissingBean` cho biết bean đã tồn tại hay chưa; điều đó giải thích vì sao bean mặc định có thể được tạo hoặc bị bỏ qua.

### 2.3. Source của một kết quả

Báo cáo nhóm condition theo source. Source thường là tên đầy đủ của auto-configuration class hoặc tên bean method, ví dụ:

```text
com.acme.autoconfigure.AcmeClientAutoConfiguration
com.acme.autoconfigure.AcmeClientAutoConfiguration#acmeClient
```

Khi source là một bean method, phần sau ký tự `#` cho biết method nào đang được xét. Điều này hữu ích khi một auto-configuration có nhiều bean và mỗi bean có điều kiện riêng.

### 2.4. Positive và negative match

Một source có thể được trình bày theo hai nhóm chính:

- **Positive match:** các condition cần thiết cho source đều match, nên source đủ điều kiện được áp dụng.
- **Negative match:** source có ít nhất một condition không match, nên source không được áp dụng theo tổ hợp điều kiện đó.

Trong báo cáo chi tiết, negative match còn có thể liệt kê:
- `notMatched`: các condition không match;
- `matched`: các condition khác đã match trong cùng source.

Điều này đặc biệt quan trọng với cấu hình kết hợp nhiều condition. Một source nằm trong negative matches không có nghĩa tất cả điều kiện của nó đều thất bại. Hãy tìm condition nằm trong `notMatched` để xác định nguyên nhân trực tiếp.

## 3. Bật báo cáo trong lúc khởi động

### 3.1. Dùng tham số --debug

Cách nhanh nhất để xem các quyết định auto-configuration là thêm `--debug` khi chạy ứng dụng:

```bash
java -jar application.jar --debug
```

Với Maven hoặc Gradle, có thể truyền argument tương ứng cho task chạy ứng dụng. Khi chạy trực tiếp bằng JVM, có thể dùng system property:

```bash
java -Ddebug -jar application.jar
```

Spring Boot ghi báo cáo điều kiện vào log trong quá trình khởi động. Hãy tìm phần có tiêu đề gần với `CONDITIONS EVALUATION REPORT` hoặc tên auto-configuration đang cần kiểm tra.

`--debug` bật chế độ chẩn đoán cho quyết định auto-configuration; nó không có nghĩa toàn bộ logger của ứng dụng sẽ được chuyển sang DEBUG.

### 3.2. Tìm source cần kiểm tra

Khi log có nhiều trang điều kiện, không nên đọc từ đầu đến cuối một cách thủ công. Hãy:

1. tìm tên auto-configuration class liên quan tới tính năng đang thiếu;
2. tìm bean method nếu chỉ một bean không xuất hiện;
3. đọc condition name;
4. đọc message của condition không match;
5. đối chiếu với dependency, bean và property của ứng dụng.

Ví dụ, nếu `AcmeClient` không được tạo, tìm source `AcmeClientAutoConfiguration#acmeClient`. Nếu report cho biết `@ConditionalOnClass` không tìm thấy `com.acme.Client`, kiểm tra dependency runtime và phiên bản thư viện.

### 3.3. Khi nào nên bật debug?

Nên bật trong các trường hợp:

- tính năng auto-configuration không xuất hiện sau khi thêm starter;
- bean mặc định bị lùi lại ngoài dự kiến;
- nâng cấp Spring Boot hoặc Spring Cloud làm thay đổi điều kiện;
- cấu hình chỉ hoạt động ở một profile hoặc môi trường;
- test context khác với ứng dụng chạy thực tế.

Không cần bật trong mọi lần chạy production. Log report có thể dài và chứa tên class, dependency, property hoặc chi tiết cấu trúc nội bộ.

## 4. Đọc báo cáo qua Actuator

### 4.1. Conditions endpoint

Nếu ứng dụng có Spring Boot Actuator, endpoint `conditions` cung cấp báo cáo ở dạng JSON. Đường dẫn HTTP mặc định là:

```text
GET /actuator/conditions
```

Để expose endpoint qua HTTP, có thể cấu hình:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
```

Nếu danh sách `include` đã được cấu hình ở nơi khác, hãy hợp nhất `conditions` vào danh sách đó thay vì vô tình loại bỏ các endpoint hiện có. Endpoint cần dependency Actuator và phải được expose theo chính sách quản trị của ứng dụng.

Ví dụ gọi endpoint:

```bash
curl -sS http://localhost:8080/actuator/conditions
```

### 4.2. Cấu trúc JSON

Báo cáo JSON có cấu trúc theo application context:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "com.acme.AcmeAutoConfiguration#acmeClient": [
          {
            "condition": "OnClassCondition",
            "message": "@ConditionalOnClass found required class 'com.acme.Client'"
          },
          {
            "condition": "OnPropertyCondition",
            "message": "@ConditionalOnProperty (acme.client.enabled=true) matched"
          }
        ]
      },
      "negativeMatches": {
        "com.acme.OtherAutoConfiguration#otherClient": {
          "notMatched": [
            {
              "condition": "OnPropertyCondition",
              "message": "@ConditionalOnProperty (acme.other.enabled=true) did not find property 'acme.other.enabled'"
            }
          ],
          "matched": [
            {
              "condition": "OnClassCondition",
              "message": "@ConditionalOnClass found required class 'com.acme.OtherClient'"
            }
          ]
        }
      },
      "unconditionalClasses": [],
      "parentId": null
    }
  }
}
```

Đây là cấu trúc minh họa rút gọn. Nội dung và số lượng condition phụ thuộc ứng dụng, classpath và phiên bản Spring Boot.

Các trường quan trọng:

| Trường | Ý nghĩa |
| --- | --- |
| `contexts` | Các application context được lập chỉ mục theo ID |
| `positiveMatches` | Source có các condition cần thiết đã match |
| `negativeMatches` | Source có ít nhất một condition không match |
| `notMatched` | Các condition thất bại trong source |
| `matched` | Các condition đã thành công trong source negative |
| `unconditionalClasses` | Các configuration class được đánh giá nhưng không có condition |
| `parentId` | ID của parent context nếu có |

### 4.3. Đọc một negative match

Giả sử endpoint trả về:

```json
{
  "negativeMatches": {
    "com.acme.AcmeClientAutoConfiguration#acmeClient": {
      "notMatched": [
        {
          "condition": "OnPropertyCondition",
          "message": "@ConditionalOnProperty (acme.client.enabled=true) did not find property 'acme.client.enabled'"
        }
      ],
      "matched": [
        {
          "condition": "OnClassCondition",
          "message": "@ConditionalOnClass found required class 'com.acme.Client'"
        }
      ]
    }
  }
}
```

Có thể diễn giải theo thứ tự:

1. Source đang xét là bean method `acmeClient`.
2. Class `com.acme.Client` đã có mặt nên class condition match.
3. Property `acme.client.enabled` không được tìm thấy nên property condition không match.
4. Vì thiếu điều kiện property bắt buộc, bean method không được áp dụng.

Bước sửa hợp lý là kiểm tra property trong effective Environment: file cấu hình đã được nạp chưa, profile nào đang active, biến môi trường có đúng tên không và cấu hình triển khai có ghi đè giá trị không.

### 4.4. Bảo vệ endpoint conditions

Conditions endpoint tiết lộ tên auto-configuration, classpath và lý do bật/tắt tính năng. Hãy giới hạn quyền truy cập bằng Spring Security hoặc cơ chế quản trị của nền tảng.

Trong production, chỉ expose endpoint qua management network, xác thực và authorization phù hợp; cân nhắc không expose qua HTTP công khai. Không đưa response nguyên vẹn vào ticket hoặc log công khai nếu nó chứa chi tiết nội bộ của ứng dụng.

## 5. Nhận diện nguyên nhân theo loại condition

### 5.1. OnClassCondition

Ví dụ message:

```text
@ConditionalOnClass did not find required class 'com.acme.Client'
```

Kiểm tra:

- dependency có trong runtime classpath không;
- dependency bị đánh dấu optional hoặc excluded không;
- dependency scope có chỉ tồn tại khi compile/test không;
- phiên bản thư viện có đổi package/class không;
- ứng dụng có class loader riêng hoặc module boundary không.

Kiểm tra dependency tree của đúng artifact và đúng runtime profile. Có dependency trong file build chưa chứng minh class xuất hiện trong runtime classpath cuối cùng.

### 5.2. OnBeanCondition

Ví dụ:

```text
@ConditionalOnMissingBean found beans of type 'com.acme.Client'
```

Điều này thường có nghĩa ứng dụng đã cung cấp bean phù hợp, vì vậy bean mặc định được phép lùi lại. Đây là hành vi extension point phổ biến, không nhất thiết là lỗi.

Nếu bean mặc định biến mất ngoài dự kiến:

- tìm bean cùng type hoặc cùng name đã được khai báo;
- kiểm tra `@Bean`, component scan và test configuration;
- kiểm tra context hierarchy và `SearchStrategy`;
- kiểm tra return type của `@Bean` method;
- xác minh thứ tự định nghĩa bean khi có nhiều auto-configuration.

`@ConditionalOnBean` và `@ConditionalOnMissingBean` phụ thuộc các bean definition đã được xử lý tại thời điểm đánh giá. Spring Boot khuyến nghị dùng các bean condition này trong auto-configuration vì auto-configuration được nạp sau các user bean definition.

### 5.3. OnPropertyCondition

Ví dụ:

```text
@ConditionalOnProperty (acme.client.enabled=true) did not find property 'acme.client.enabled'
```

Kiểm tra property thực sự có mặt trong Environment không, và kiểm tra giá trị sau khi áp dụng profile, environment variable, command-line argument và các nguồn ghi đè.

Với `@ConditionalOnProperty`:

- mặc định, property tồn tại và không bằng chuỗi `false` thì được xem là match;
- `havingValue` cho phép yêu cầu một giá trị cụ thể;
- `matchIfMissing` quyết định condition có match khi property vắng mặt hay không;
- nếu khai báo nhiều tên property, tất cả phải thỏa điều kiện.

Ví dụ:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.client",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class AcmeClientAutoConfiguration {
    // ...
}
```

Với cấu hình trên, property phải có giá trị `true`. Nếu property bị thiếu hoặc mang giá trị khác, auto-configuration không match.

### 5.4. OnWebApplicationCondition

Nếu message cho biết ứng dụng không phải servlet hoặc reactive web application theo yêu cầu, hãy kiểm tra:

- starter web nào đang có mặt;
- application type mà Spring Boot suy ra;
- cấu hình test runner có tạo đúng loại context không;
- ứng dụng có chạy ở non-web mode không.

Một auto-configuration cho servlet stack có thể không được áp dụng trong reactive context và ngược lại. Đừng thêm dependency web chỉ để làm report chuyển sang positive match nếu kiến trúc không cần web server.

### 5.5. OnResourceCondition

Nếu resource condition không match, kiểm tra resource path, classpath, profile và cách đóng gói artifact. Một file có trong source tree có thể không nằm trong JAR cuối cùng hoặc có đường dẫn khác khi deploy.

### 5.6. Nested conditions

Một số điều kiện là tổ hợp như `AnyNestedCondition`, `AllNestedConditions` hoặc `NoneNestedConditions`. Message có thể dài và mô tả nhiều nhánh con.

Không dừng ở tên condition tổng hợp. Hãy đọc các nhánh được liệt kê để biết:
- nhánh nào match;
- nhánh nào không match;
- quy tắc tổng thể yêu cầu tất cả, ít nhất một hay không nhánh nào match.

Điều này tránh việc sửa nhầm property hoặc dependency không liên quan.

## 6. Kiểm tra exclusions và context hierarchy

### 6.1. Auto-configuration bị exclude

Một class có thể bị loại khỏi quá trình auto-configuration thông qua:

- thuộc tính `spring.autoconfigure.exclude`;
- thuộc tính `exclude` hoặc `excludeName` trên `@SpringBootApplication` / `@EnableAutoConfiguration`;
- cấu hình của test hoặc bootstrap tùy môi trường.

Ví dụ:

```yaml
spring:
  autoconfigure:
    exclude:
      - com.acme.autoconfigure.AcmeClientAutoConfiguration
```

Nếu class xuất hiện trong danh sách exclusions, hãy xác minh đây có phải chủ đích của ứng dụng không. Tìm cả cấu hình theo profile và tham số triển khai vì chúng có thể bổ sung exclusion ở runtime.

### 6.2. Parent và child ApplicationContext

Một số ứng dụng có nhiều context, ví dụ context cha và context con của web server hoặc các context được tạo riêng. Conditions endpoint nhóm báo cáo theo context ID và có thể cung cấp `parentId`.

Khi một bean không xuất hiện, cần kiểm tra context đang sở hữu bean đó. Bean ở parent có thể được nhìn thấy từ child theo quy tắc hierarchy; bean ở child không tự động được nhìn thấy từ parent.

`ConditionEvaluationReport` cũng có `getParent()` để truy cập report của parent BeanFactory nếu có. Vì vậy, đừng chỉ đọc report của một context khi ứng dụng có hierarchy.

### 6.3. Unconditional classes

`unconditionalClasses` liệt kê các configuration class đã được đánh giá nhưng không có điều kiện. Chúng không phải lỗi hoặc danh sách các class được áp dụng theo cùng semantics với positive match. Hãy dùng trường này để hiểu phần cấu hình luôn được nạp trong context.

## 7. Truy vấn ConditionEvaluationReport bằng Java

### 7.1. Lấy report từ BeanFactory

API `ConditionEvaluationReport.find(BeanFactory)` có thể tìm report đã tồn tại và trả về `null` nếu không tìm thấy. Dùng `find` khi chỉ muốn quan sát report có sẵn; `get` có thể tạo report nếu chưa tồn tại.

Ví dụ:

```java
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.context.ConfigurableApplicationContext;

public class ConditionReportPrinter {

    public void print(ConfigurableApplicationContext context) {
        ConditionEvaluationReport report =
                ConditionEvaluationReport.find(context.getBeanFactory());

        if (report == null) {
            System.out.println("No condition report found");
            return;
        }

        report.getConditionAndOutcomesBySource().forEach((source, outcomes) -> {
            System.out.println(
                    source + " fullMatch=" + outcomes.isFullMatch()
            );

            outcomes.forEach(item -> {
                var outcome = item.getOutcome();
                System.out.printf(
                        "  condition=%s match=%s message=%s%n",
                        item.getCondition().getClass().getSimpleName(),
                        outcome.isMatch(),
                        outcome.getMessage()
                );
            });
        });

        System.out.println("Exclusions: " + report.getExclusions());
    }
}
```

`getConditionAndOutcomesBySource()` trả map từ source sang tập kết quả condition. Mỗi `ConditionAndOutcome` cung cấp condition và outcome tương ứng; `ConditionAndOutcomes.isFullMatch()` cho biết tất cả outcome trong nhóm có match hay không.

Đây là API chẩn đoán cấp thấp. Trong ứng dụng thông thường, nên ưu tiên log `--debug` hoặc Actuator thay vì viết logic nghiệp vụ phụ thuộc vào report nội bộ.

### 7.2. Đọc report của parent context

Nếu cần điều tra context hierarchy:

```java
ConditionEvaluationReport parentReport = report.getParent();

if (parentReport != null) {
    System.out.println(
            parentReport.getConditionAndOutcomesBySource().keySet()
    );
}
```

Không giả định parent report luôn tồn tại. Hãy kiểm tra null và xác định context nào đang chứa cấu hình cần phân tích.

### 7.3. Vì sao không nên dùng report làm feature flag?

Condition report mô tả quyết định lúc cấu hình context. Nó không phải API điều khiển feature runtime và không tự phản ánh mọi thay đổi sau startup.

Nếu ứng dụng cần quyết định nghiệp vụ theo property hoặc trạng thái runtime, hãy dùng cấu hình có kiểu, bean/service hoặc feature flag service tương ứng. Không truy vấn condition report trong request path để quyết định nghiệp vụ.

## 8. Kiểm thử với ApplicationContextRunner

### 8.1. Tạo context nhỏ cho một auto-configuration

`ApplicationContextRunner` giúp tạo context riêng với một tập auto-configuration và property được xác định rõ. Điều này hữu ích để kiểm tra từng tổ hợp classpath, bean và property mà không cần khởi động toàn bộ ứng dụng.

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeClientAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AcmeClientAutoConfiguration.class
                            )
                    );

    @Test
    void createsDefaultClientWhenEnabled() {
        this.contextRunner
                .withPropertyValues("acme.client.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(AcmeClient.class)
                );
    }

    @Test
    void doesNotCreateClientWhenDisabled() {
        this.contextRunner
                .withPropertyValues("acme.client.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AcmeClient.class)
                );
    }
}
```

Mỗi test mô tả một tổ hợp điều kiện. Test có thể bổ sung user configuration, property values hoặc classloader để xác minh các nhánh khác nhau.

### 8.2. In report trong test

Có thể dùng `ConditionEvaluationReportLoggingListener` để in báo cáo ở mức INFO hoặc DEBUG:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class AcmeConditionReportTests {

    @Test
    void printsConditionReport() {
        new ApplicationContextRunner()
                .withInitializer(
                        ConditionEvaluationReportLoggingListener
                                .forLogLevel(LogLevel.INFO)
                )
                .run(context -> {
                    // Assertions cho bean và cấu hình cần kiểm chứng.
                });
    }
}
```

Listener đặc biệt hữu ích khi một test context có kết quả khác với ứng dụng thực tế. Hãy đọc report cùng assertion: report giải thích condition, assertion xác nhận bean/hành vi mà test yêu cầu.

### 8.3. Kiểm tra classpath thiếu dependency

`FilteredClassLoader` cho phép mô phỏng một class hoặc package không có mặt trong context test. Đây là cách kiểm tra `@ConditionalOnClass` có thực sự khiến auto-configuration lùi lại không.

Ví dụ:

```java
import org.springframework.boot.test.context.FilteredClassLoader;

this.contextRunner
        .withClassLoader(new FilteredClassLoader(AcmeClient.class))
        .run(context ->
                assertThat(context).doesNotHaveBean(AcmeClient.class)
        );
```

Test này kiểm chứng nhánh thiếu class. Trong test thực tế, cần bảo đảm class bị lọc là dependency tùy chọn và cấu hình không tham chiếu trực tiếp tới kiểu đó theo cách khiến class được load trước khi condition được đánh giá.

### 8.4. Kiểm tra bean do người dùng cung cấp

Để xác nhận auto-configuration lùi lại khi người dùng có bean riêng:

```java
@Configuration(proxyBeanMethods = false)
static class UserClientConfiguration {

    @Bean
    AcmeClient customAcmeClient() {
        return new AcmeClient("custom");
    }
}
```

```java
this.contextRunner
        .withUserConfiguration(UserClientConfiguration.class)
        .run(context -> {
            assertThat(context).hasSingleBean(AcmeClient.class);
            assertThat(context).hasBean("customAcmeClient");
        });
```

Test cần xác minh cả số lượng bean và bean nào được dùng. Chỉ kiểm tra context khởi động thành công không đủ để chứng minh auto-configuration đã lùi lại đúng cách.

## 9. Quy trình debug thực tế

Khi một tính năng không được auto-configure, có thể làm theo trình tự:

1. **Xác định kết quả mong đợi.** Ghi rõ bean hoặc tính năng nào cần xuất hiện và trong profile nào.
2. **Xác nhận dependency runtime.** Kiểm tra starter và dependency cuối cùng có chứa class mà auto-configuration yêu cầu không.
3. **Bật report.** Chạy với `--debug` hoặc gọi `/actuator/conditions` nếu endpoint đã được bảo vệ và expose.
4. **Tìm đúng source.** Tìm auto-configuration class hoặc bean method tương ứng.
5. **Đọc notMatched.** Xác định condition đầu tiên hoặc condition bắt buộc không match; đọc cả các nhánh nested.
6. **Kiểm tra Environment.** Đối chiếu property hiệu lực, profile active và nguồn ghi đè.
7. **Kiểm tra bean hiện có.** Tìm bean do ứng dụng hoặc test tạo ra khiến `@ConditionalOnMissingBean` không match.
8. **Kiểm tra exclusions.** Xác nhận class không bị loại bởi annotation hoặc `spring.autoconfigure.exclude`.
9. **Đọc source auto-configuration.** Kiểm tra các annotation condition, thứ tự và return type của bean method.
10. **Tạo test tái hiện.** Dùng `ApplicationContextRunner` để cô lập tổ hợp property, bean và classpath gây lỗi.
11. **Xác nhận kết quả.** Kiểm tra bean thực tế và hành vi của ứng dụng sau khi sửa.

### Ví dụ: bean mặc định không xuất hiện

Tình huống: thêm starter Acme nhưng `AcmeClient` không được tạo.

Report cho biết:

```text
AcmeClientAutoConfiguration#acmeClient
OnClassCondition: matched
OnPropertyCondition: matched
OnBeanCondition: @ConditionalOnMissingBean found beans of type 'com.acme.AcmeClient'
```

Diễn giải:

- Dependency cần thiết đã có.
- Property bật tính năng đã đúng.
- Một bean `AcmeClient` đã tồn tại nên bean mặc định không được tạo.

Bước tiếp theo là tìm nơi khai báo bean hiện có và xác định nó có phải bean thay thế được chủ đích hay không. Nếu không, kiểm tra component scan, test configuration hoặc một auto-configuration khác đang tạo bean đó.

### Ví dụ: property có trong file nhưng condition vẫn không match

Tình huống: `application-prod.yml` có `acme.client.enabled=true` nhưng report nói property không tìm thấy.

Kiểm tra lần lượt:

- `prod` có nằm trong active profiles không;
- file nằm đúng vị trí và được nạp trong môi trường deploy không;
- tên property có sai prefix hoặc spelling không;
- file cấu hình ngoài có ghi đè bằng nguồn khác không;
- giá trị có bị set thành rỗng hoặc false qua environment variable không;
- auto-configuration đang đọc property có đúng namespace/version không.

Dùng `/actuator/env` hoặc log cấu hình có kiểm soát để xác minh effective Environment. Endpoint `env` có thể chứa dữ liệu nhạy cảm, vì vậy cần bảo vệ tương tự các endpoint quản trị khác.

## 10. Giới hạn và lỗi diễn giải thường gặp

| Cách hiểu sai | Cách hiểu đúng |
| --- | --- |
| Positive match nghĩa bean chắc chắn đã được khởi tạo | Nó cho biết source đủ điều kiện; cần kiểm tra bean definition/bean thực tế và các bước sau đó |
| Negative match nghĩa tất cả condition đều thất bại | Chỉ cần ít nhất một condition cần thiết không match; xem `notMatched` và `matched` |
| Không thấy source trong positive matches nghĩa là bị lỗi | Có thể source nằm trong negative matches, bị exclude hoặc không phải candidate trong runtime |
| Bean mặc định không có nghĩa starter không hoạt động | `@ConditionalOnMissingBean` có thể chủ động lùi lại khi user bean đã tồn tại |
| Report phản ánh mọi thay đổi runtime | Report ghi quyết định condition trong quá trình cấu hình context |
| `--debug` bật toàn bộ log DEBUG | Nó bật báo cáo quyết định auto-configuration |
| Conditions endpoint an toàn để expose công khai | Endpoint tiết lộ cấu trúc nội bộ, cần giới hạn truy cập |
| Sửa property đầu tiên nhìn thấy là đủ | Phải kiểm tra effective Environment, profile và nguồn override |
| Một report đại diện cho mọi context | Mỗi context có report riêng; xem cả parent/child khi có hierarchy |

Report cũng không thay thế các công cụ khác:

- `/actuator/beans` cho biết bean được đăng ký trong context;
- `/actuator/configprops` cho biết cấu hình đã bind vào `@ConfigurationProperties`;
- `/actuator/env` cho biết các property source và giá trị Environment theo chính sách sanitization;
- log startup và exception giúp xác định lỗi tạo bean hoặc lỗi runtime sau khi condition đã match.

## 11. Checklist kiểm chứng cấu hình

Trước khi kết luận một auto-configuration hoạt động đúng, hãy xác nhận:

- [ ] Starter và dependency runtime cần thiết có mặt.
- [ ] Auto-configuration class là candidate được nạp.
- [ ] Không có exclusion ngoài ý muốn.
- [ ] Các class condition cần thiết đều match.
- [ ] Property condition đọc đúng effective value và active profile.
- [ ] Bean condition không bị một bean ngoài dự kiến làm thay đổi.
- [ ] Web application condition phù hợp loại context.
- [ ] Đã đọc đủ các nhánh nested condition.
- [ ] Đã kiểm tra đúng context ID và parent context nếu có hierarchy.
- [ ] Bean thực tế có trong context và có đúng implementation.
- [ ] Có test tái hiện điều kiện quan trọng bằng ApplicationContextRunner.
- [ ] Conditions endpoint chỉ được expose cho người có quyền quản trị.

## 12. Bài tập vận dụng

### Bài tập 1 — Thiếu class trên runtime classpath

Report cho thấy `OnClassCondition` không tìm thấy `com.acme.Client` dù dependency đã được khai báo trong file build.

Hãy nêu các nguyên nhân có thể khiến class không xuất hiện trong runtime classpath và cách kiểm chứng artifact sau khi đóng gói.

### Bài tập 2 — Auto-configuration lùi lại

`AcmeClientAutoConfiguration#acmeClient` không match vì `@ConditionalOnMissingBean` tìm thấy một bean cùng type.

Hãy xác định các nguồn có thể tạo bean đó và đề xuất cách kiểm tra bean name, type và context hierarchy.

### Bài tập 3 — Property condition không match

Một property được đặt trong file cấu hình nhưng report nói property không tồn tại.

Hãy lập thứ tự kiểm tra active profile, property source, environment variable, command-line argument, spelling, `havingValue` và `matchIfMissing`.

### Bài tập 4 — Nested condition

Một auto-configuration dùng `AnyNestedCondition` gồm hai nhánh. Một nhánh match, nhánh còn lại không match, nhưng source vẫn ở negative matches.

Hãy giải thích sự khác biệt giữa kết quả của từng nhánh và kết quả cuối cùng của condition tổng hợp.

### Bài tập 5 — Conditions endpoint

Ứng dụng chỉ cho phép truy cập `/actuator/health`. Người vận hành muốn đọc conditions report qua HTTP.

Hãy đề xuất cấu hình exposure, authentication, authorization và network policy để chỉ nhóm vận hành có thể truy cập endpoint.

### Bài tập 6 — Test context và production khác nhau

Auto-configuration match trong test nhưng không match trong production.

Hãy liệt kê các yếu tố cần so sánh: classpath, active profile, Environment, user bean, loại application context, exclusions và phiên bản Spring Boot.

### Tự kiểm tra nhanh

1. `ConditionEvaluationReport` ghi lại điều gì? **Kết quả đánh giá các condition của cấu hình và auto-configuration.**
2. Cờ nào in báo cáo auto-configuration lúc startup? **`--debug` hoặc system property `-Ddebug`.**
3. Actuator endpoint nào cung cấp báo cáo JSON? **`/actuator/conditions`.**
4. `positiveMatches` cho biết điều gì? **Các source có các condition cần thiết đã match.**
5. `negativeMatches.notMatched` có ý nghĩa gì? **Các condition không match trong source đó.**
6. `negativeMatches.matched` có ý nghĩa gì? **Các condition khác đã match trong source negative.**
7. API nào tìm report hiện có từ BeanFactory? **`ConditionEvaluationReport.find(beanFactory)`.**
8. API nào có thể tạo report nếu chưa tồn tại? **`ConditionEvaluationReport.get(beanFactory)`.**
9. Công cụ nào giúp kiểm thử auto-configuration trong context nhỏ? **`ApplicationContextRunner`.**
10. Listener nào in report trong test? **`ConditionEvaluationReportLoggingListener`.**
11. Report có chứng minh bean đã được khởi tạo không? **Không; cần kiểm tra context và hành vi thực tế.**
12. Vì sao cần bảo vệ conditions endpoint? **Nó tiết lộ tên class, dependency và chi tiết cấu hình nội bộ.**

**Thông điệp cốt lõi:** `ConditionEvaluationReport` giải thích vì sao Spring Boot áp dụng hoặc bỏ qua một auto-configuration bằng cách ghi lại từng condition và message. Hãy tìm đúng source, đọc các condition không match, kiểm tra classpath, bean, property, exclusions và context hierarchy; sau đó xác nhận kết quả bằng bean thực tế và test có kiểm soát. Kết hợp `--debug`, Actuator `conditions` và `ApplicationContextRunner` giúp quá trình chẩn đoán có bằng chứng và có thể lặp lại.

**Tài liệu tham khảo:**

- [Spring Boot — Troubleshoot Auto-configuration](https://docs.spring.io/spring-boot/4.0/how-to/application.html#howto.application.troubleshoot-auto-configuration)
- [Spring Boot Actuator — Conditions Evaluation Report](https://docs.spring.io/spring-boot/api/rest/actuator/conditions.html)
- [Spring Boot API — ConditionEvaluationReport](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot API — ConditionAndOutcomes](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.ConditionAndOutcomes.html)

Cấu trúc JSON, endpoint access và một số API có thể khác giữa các phiên bản Spring Boot. Đối chiếu reference của phiên bản thực tế trong dependency management của dự án trước khi áp dụng.
