# ConditionOutcome, thông điệp khớp và thông điệp không khớp

## 1. Mục tiêu: một điều kiện cần cả kết quả lẫn lý do

Khi Spring Boot xử lý auto-configuration, mỗi condition trả lời một câu hỏi: cấu hình hoặc bean definition có được phép tham gia context hiện tại hay không? Giá trị boolean cho biết **khớp hay không khớp**. Khi debug, chỉ biết true/false thường chưa đủ: ta còn cần biết **vì sao** condition đưa ra kết quả đó.

Spring Boot biểu diễn câu trả lời bằng `ConditionOutcome`:

- `isMatch()` cho biết condition khớp (`true`) hay không khớp (`false`).
- `getMessage()` cung cấp thông điệp chẩn đoán đi kèm; có thể là `null` nếu outcome không có message.
- `match(...)` và `noMatch(...)` tạo outcome tương ứng; có thể truyền chuỗi hoặc `ConditionMessage` để giải thích kết quả.

Spring Boot thu thập các outcome vào `ConditionEvaluationReport`. Report nhóm chúng theo **source** (configuration class hoặc phương thức `@Bean`). Mỗi entry `ConditionAndOutcome` liên kết một implementation `Condition` với `ConditionOutcome` của nó; nhóm `ConditionAndOutcomes` cho biết tất cả condition của source đó có cùng khớp hay không.

Bài này đi từ API nhỏ nhất đến báo cáo toàn ứng dụng, gồm cách tự viết condition có message, cách đọc outcome trong test, cách phân biệt positive/negative matches của Actuator và một project Java 17/JUnit 5 có thể chạy với Spring Boot 3.3.x.

## 2. ConditionOutcome là gì?

`ConditionOutcome` là một **giá trị kết quả**, không phải annotation và cũng không tự quyết định thời điểm Spring chạy condition. Một condition được Spring gọi qua hợp đồng `Condition.matches(...)`. Các condition nội bộ của Spring Boot thường kế thừa `SpringBootCondition`; lớp nền này yêu cầu implementation cung cấp `getMatchOutcome(...)` thay vì tự trả boolean, rồi xử lý logging và ghi nhận outcome theo cơ chế của Boot.

Mô hình:

```text
Spring evaluates a Condition
          |
          v
SpringBootCondition.getMatchOutcome(...)
          |
          v
      ConditionOutcome
       /          \
  isMatch=true  isMatch=false
       |             |
       v             v
source được     source bị loại
cho phép         bởi condition
       \             /
        \           /
         ConditionEvaluationReport
                   |
                   v
        log / debug / Actuator / test
```

Một outcome có hai thành phần về ý nghĩa:

| Thành phần | API | Câu hỏi được trả lời |
| --- | --- | --- |
| Trạng thái | `isMatch()` | Điều kiện có khớp không? |
| Lý do | `getMessage()` / `getConditionMessage()` | Điều gì dẫn tới kết quả này? |

Thông điệp là dữ liệu dành cho người đọc. Nó có thể thay đổi khi implementation, phiên bản, tên bean hoặc đầu vào thay đổi. Vì vậy, code điều khiển phải dựa trên `isMatch()`; log/report dùng message để giải thích. Tránh parse message bằng regex để quyết định logic nghiệp vụ.

### 2.1. Các factory method thường dùng

```java
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;

ConditionOutcome positive =
        ConditionOutcome.match("Found bean 'catalogService'");

ConditionOutcome negative =
        ConditionOutcome.noMatch("No CatalogService bean was found");

ConditionOutcome positiveWithoutMessage = ConditionOutcome.match();
ConditionOutcome negativeWithoutMessage = ConditionOutcome.noMatch();
```

Đây là đoạn Java minh họa có thể biên dịch trong một class Java 17 có method phù hợp. Hai outcome đầu có message; hai outcome cuối chỉ có boolean và message có thể là `null`. Khi tự viết condition cho thư viện, nên tạo message có ích thay vì dùng factory không message.

`ConditionOutcome` cũng có overload nhận `ConditionMessage`. `ConditionMessage` là API hỗ trợ xây dựng message theo cấu trúc và phong cách thống nhất; nó hữu ích cho condition có nhiều loại kết quả hoặc nhiều bean được tìm thấy. Nếu một câu message rõ ràng đã đủ, overload `String` dễ đọc và phù hợp.

### 2.2. Match và no-match không có nghĩa là startup thành công/thất bại

Một condition **no-match** thường chỉ có nghĩa Spring bỏ qua một configuration hoặc bean definition. Đây có thể là hành vi đúng, ví dụ:

- `@ConditionalOnMissingBean` không khớp vì user đã cung cấp bean thay thế.
- `@ConditionalOnClass` không khớp vì dependency tùy chọn không có.
- `@ConditionalOnProperty` không khớp vì tính năng đang tắt.

Một condition **match** chỉ có nghĩa source qua được condition đó. Configuration vẫn có thể không được tạo vì condition khác không khớp, hoặc context có thể fail về sau do binding, dependency injection hay khởi tạo bean.

Vì vậy:

- `match` không đảm bảo toàn bộ ứng dụng khởi động thành công.
- `no-match` không mặc nhiên là lỗi.
- Chỉ nhìn một message không đủ để kết luận cả source được đăng ký; phải xem tất cả condition thuộc source đó.

## 3. Tự viết condition có message bằng SpringBootCondition

Khi cần một quy tắc riêng, hãy kế thừa `SpringBootCondition`. API yêu cầu implement `getMatchOutcome(ConditionContext, AnnotatedTypeMetadata)` và trả về `ConditionOutcome`.

Ví dụ: một cấu hình chỉ được bật khi container đã có bean kiểu `CatalogService`.

```java
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class CatalogPresentCondition extends SpringBootCondition {

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        String[] beanNames = context.getBeanFactory()
                .getBeanNamesForType(CatalogService.class, true, false);

        if (beanNames.length == 0) {
            return ConditionOutcome.noMatch(
                    "No CatalogService bean was visible at condition evaluation time");
        }

        return ConditionOutcome.match(
                "Found CatalogService bean(s): "
                        + String.join(", ", beanNames));
    }
}
```

Đây là ví dụ condition; `CatalogService` là kiểu của ứng dụng/library và cần được định nghĩa ở nơi dùng. Các tham số của `getBeanNamesForType` trong ví dụ có ý nghĩa:

- `includeNonSingletons=true`: cho phép xét cả bean không phải singleton.
- `allowEagerInit=false`: không chủ động khởi tạo `FactoryBean` hoặc bean chỉ để suy luận kiểu trong lần dò này; việc nhận diện phụ thuộc metadata container đang có.
- Mảng rỗng dẫn đến `noMatch` với lý do cụ thể; nếu tìm thấy một hay nhiều tên bean thì `match` kèm danh sách tên.

Condition này chỉ là minh họa về cách tạo outcome. Nếu mục tiêu chỉ là kiểm tra bean thông thường, ưu tiên annotation sẵn có `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean` vì chúng diễn đạt ý định rõ ràng và xử lý các quy tắc riêng của Boot. Chỉ tạo custom condition khi annotation có sẵn không biểu đạt đủ chính sách.

### 3.1. Vì sao kế thừa SpringBootCondition?

`SpringBootCondition` là lớp nền cho condition tích hợp với cơ chế log và condition report của Spring Boot. Nó thực hiện `matches(...)` cuối cùng, gọi `getMatchOutcome(...)` và ghi nhận outcome theo source đang được xử lý.

Nếu tự triển khai trực tiếp interface Spring Framework `Condition`, bạn chỉ phải trả boolean từ `matches(...)`. Cách đó phù hợp với điều kiện Spring thuần, nhưng không tự có cùng trải nghiệm message/report của `SpringBootCondition`. Khi mục tiêu là condition có lý do trong Spring Boot diagnostics, kế thừa `SpringBootCondition` là lựa chọn tự nhiên.

Không override `matches(...)` của `SpringBootCondition`; method này là `final`. Hãy đặt logic trong `getMatchOutcome(...)` và trả outcome đúng.

### 3.2. Viết message có thể hành động

Một message tốt nên giúp người vận hành biết cần làm gì tiếp theo:

| Message mơ hồ | Message hữu ích hơn |
| --- | --- |
| `Condition failed` | `No CatalogService bean was visible when CatalogDiagnosticConfiguration was evaluated` |
| `Feature disabled` | `demo.search.enabled was false; SearchClient configuration was skipped` |
| `Missing dependency` | `Required class com.example.sdk.SearchClient was not found on the runtime classpath` |
| `Invalid config` | `Property demo.search.endpoint must be an absolute HTTPS URI` |

Message nên ngắn, nêu đúng input/điều kiện thất bại và gợi ý cách khắc phục. Không ghi token, password, access key, nội dung request, thông tin cá nhân hoặc cấu hình bí mật vào message. Condition report thường được đưa vào log hoặc endpoint quản trị; hãy xem nó như dữ liệu vận hành có thể được nhiều người có quyền truy cập đọc.

## 4. ConditionEvaluationReport tổ chức outcome như thế nào?

`ConditionEvaluationReport` là report của Spring Boot, ghi nhận chi tiết việc đánh giá condition để phục vụ logging và diagnostics. API chính:

| API | Ý nghĩa |
| --- | --- |
| `ConditionEvaluationReport.get(beanFactory)` | Lấy report cho `ConfigurableListableBeanFactory`; nếu chưa có report, API có thể tạo report mới |
| `ConditionEvaluationReport.find(beanFactory)` | Thử tìm report đang có; có thể trả `null` |
| `getConditionAndOutcomesBySource()` | Map source → nhóm các cặp condition/outcome |
| `getExclusions()` | Danh sách auto-configuration đã bị exclude |
| `getUnconditionalClasses()` | Những configuration class được đánh giá nhưng không mang condition |
| `getParent()` | Report của parent BeanFactory, nếu có |

Map source có thể chứa key là tên class đầy đủ hoặc tên phương thức bean theo dạng:

```text
com.example.CatalogAutoConfiguration
com.example.CatalogAutoConfiguration#catalogService
com.example.CatalogAutoConfiguration#catalogDiagnostic
```

Dấu `#` phân cách class và method. Đừng đoán tên từ tên bean runtime: source thường phản ánh **phương thức @Bean được đánh giá**, còn bean name có thể được tùy chỉnh bằng `@Bean("customName")`. Với nested configuration, dùng `SomeConfiguration.class.getName()` để tạo class name đúng, kể cả ký tự `$`.

### 4.1. ConditionAndOutcome: một cặp điều kiện và kết quả

`ConditionEvaluationReport.ConditionAndOutcome` cung cấp hai accessor:

- `getCondition()` trả về implementation `Condition` đã được đánh giá.
- `getOutcome()` trả về `ConditionOutcome` tương ứng.

Cặp này giúp phân biệt nhiều loại condition cùng tham gia vào một source. Ví dụ, một bean method có cả điều kiện property và condition bean; khi debug, bạn cần biết **condition nào** đưa ra message đang đọc.

### 4.2. ConditionAndOutcomes: toàn bộ condition của một source

`ConditionEvaluationReport.ConditionAndOutcomes` là một tập hợp có thể duyệt (`Iterable`) các `ConditionAndOutcome`. Nó cung cấp `isFullMatch()`:

- `true` khi **tất cả** outcome trong nhóm đều match.
- `false` nếu có ít nhất một outcome no-match.

Giả sử cùng một bean method chịu ba điều kiện:

| Condition | Outcome |
| --- | --- |
| Class SDK có mặt | match |
| Property feature bật | match |
| Bean nền tảng đã tồn tại | no-match |

Từng condition có message riêng, nhưng `isFullMatch()` của source là `false`. Vì vậy, đừng thấy một message “matched” trong report rồi kết luận bean method được đăng ký; hãy đọc cả nhóm và xác định outcome no-match nào chặn source.

### 4.3. Positive và negative matches trong report

Actuator Conditions Evaluation Report tổ chức dữ liệu theo application context:

- `contexts`: các context được đánh chỉ mục bằng context id.
- `positiveMatches`: source mà các condition được ghi nhận đều khớp; mỗi source có danh sách condition và message.
- `negativeMatches`: source bị loại; mỗi source có `notMatched` (các condition không khớp) và `matched` (các condition khác vẫn khớp).
- `unconditionalClasses`: danh sách configuration class không có condition.
- `parentId`: id của parent context nếu có.

Điểm dễ đọc nhầm: trong `negativeMatches`, mảng `matched` vẫn có thể chứa condition thành công. Source nằm trong negative matches vì **ít nhất một condition không khớp**, không phải vì mọi condition đều sai.

Ví dụ rút gọn về cấu trúc:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "com.example.CatalogAutoConfiguration#catalogService": [
          {
            "condition": "OnClassCondition",
            "message": "@ConditionalOnClass found required class"
          }
        ]
      },
      "negativeMatches": {
        "com.example.SearchAutoConfiguration#searchClient": {
          "notMatched": [
            {
              "condition": "OnPropertyCondition",
              "message": "demo.search.enabled was false"
            }
          ],
          "matched": [
            {
              "condition": "OnClassCondition",
              "message": "Required SDK class was present"
            }
          ]
        }
      },
      "unconditionalClasses": []
    }
  }
}
```

Đây là JSON minh họa để đọc cấu trúc, không phải output cố định của một ứng dụng. Message thật do condition tạo ra; tên source và số condition phụ thuộc cấu hình đang chạy.

## 5. Đọc report trực tiếp trong code và test

Sau khi context đã refresh, có thể lấy report và duyệt theo source:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

Map<String, ConditionEvaluationReport.ConditionAndOutcomes> bySource =
        report.getConditionAndOutcomesBySource();

bySource.forEach((source, outcomes) -> {
    System.out.println(source + " -> fullMatch=" + outcomes.isFullMatch());

    for (ConditionEvaluationReport.ConditionAndOutcome item : outcomes) {
        Condition condition = item.getCondition();
        ConditionOutcome outcome = item.getOutcome();

        System.out.println("  condition="
                + condition.getClass().getSimpleName());
        System.out.println("  match=" + outcome.isMatch());
        System.out.println("  message=" + outcome.getMessage());
    }
});
```

Đây là đoạn code minh họa bên trong một test callback hoặc một thành phần chẩn đoán có quyền truy cập `ConfigurableListableBeanFactory context`. Cần import:

```java
import java.util.Map;

import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.context.annotation.Condition;
```

Nếu `getMessage()` trả `null`, in chuỗi `null` là bình thường; đừng giả định mọi condition đều cung cấp message. Nếu chỉ muốn xem một configuration, lọc theo prefix source class thay vì in toàn bộ report.

Khi muốn tránh tạo report mới chỉ vì thao tác kiểm tra, dùng `ConditionEvaluationReport.find(beanFactory)` và kiểm tra null. Trong test với condition của Spring Boot đã chạy, `get(...)` thường thuận tiện vì report đã được ghi nhận.

### 5.1. Lọc một bean method cụ thể

```java
String source = CatalogAutoConfiguration.class.getName()
        + "#catalogDiagnostic";

ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

ConditionEvaluationReport.ConditionAndOutcomes outcomes =
        report.getConditionAndOutcomesBySource().get(source);

if (outcomes != null) {
    System.out.println("fullMatch=" + outcomes.isFullMatch());
    for (ConditionEvaluationReport.ConditionAndOutcome item : outcomes) {
        System.out.println(item.getCondition().getClass().getName()
                + " => " + item.getOutcome().isMatch()
                + " : " + item.getOutcome().getMessage());
    }
}
```

Tên `catalogDiagnostic` phải đúng tên phương thức `@Bean` trong ví dụ của bạn. Nếu key trả về `null`, hãy kiểm tra:

1. Source class có thật sự được chọn và đánh giá không?
2. Điều kiện bị đặt ở cấp class hay method? Nếu ở cấp class, key có thể chỉ là tên class.
3. Bạn đang đọc report của đúng BeanFactory/context không?
4. Cấu hình bị exclude hoặc bị loại trước khi method condition được đánh giá?
5. Custom condition có kế thừa `SpringBootCondition` để ghi nhận message vào Boot report không?

Đừng tự thêm entry vào report để “sửa” key không tìm thấy; hãy tìm nguyên nhân cấu hình chưa được đánh giá.

## 6. Message của condition có sẵn thường nói gì?

Spring Boot có các condition nội bộ quen thuộc. Report thường hiển thị tên implementation như `OnClassCondition`, `OnBeanCondition`, `OnPropertyCondition` hoặc `OnWebApplicationCondition`.

| Condition | Ví dụ message mang ý nghĩa match | Ví dụ message mang ý nghĩa no-match |
| --- | --- | --- |
| `@ConditionalOnClass` | Tìm thấy các class bắt buộc trên runtime classpath | Không tìm thấy class được yêu cầu |
| `@ConditionalOnBean` | Đã tìm thấy bean theo type/name/annotation yêu cầu | Chưa tìm thấy bean đáp ứng tiêu chí |
| `@ConditionalOnMissingBean` | Không tìm thấy bean cạnh tranh, nên bean mặc định có thể đăng ký | Đã có bean, nên bean mặc định nhường chỗ |
| `@ConditionalOnProperty` | Property có giá trị phù hợp `havingValue` | Property thiếu hoặc giá trị không phù hợp |
| `@ConditionalOnWebApplication` | Context hiện tại phù hợp loại web được yêu cầu | Không phải web application hoặc sai loại Servlet/Reactive |

Các câu trong bảng là diễn giải, không phải literal message để copy vào assertion. Message thực có thể chứa tên class, kiểu bean, tên property, search strategy, context hoặc chi tiết version.

Ví dụ message tích cực của `@ConditionalOnMissingBean` có thể diễn đạt rằng chưa tìm thấy bean kiểu yêu cầu; message tiêu cực có thể nói bean cụ thể đã tồn tại. Đọc theo ngữ nghĩa của annotation:

- Với `@ConditionalOnMissingBean`, **match** thường có nghĩa “có thể đăng ký default”.
- Với `@ConditionalOnBean`, **match** có nghĩa “đã tìm thấy dependency cần thiết”.
- Cùng một cụm “did not find bean” có thể là tin tốt cho condition MissingBean nhưng là lý do thất bại cho condition OnBean. Luôn đọc tên condition trước message.

## 7. Thực hành: tạo report có cả match và no-match

Project dưới đây tạo ba trường hợp trên cùng một loại auto-configuration:

1. Có source bean: `@ConditionalOnBean` match, `@ConditionalOnMissingBean` no-match, custom condition match.
2. Không có source bean: `@ConditionalOnBean` no-match, `@ConditionalOnMissingBean` match, custom condition no-match.
3. User cung cấp source bean: các condition nhìn thấy user bean và cho kết quả tương ứng.

Bộ test kiểm tra cả **bean cuối cùng** và **ConditionOutcome trong report**, thay vì chỉ nhìn một phía.

### 7.1. Cấu trúc project

```text
condition-outcome-lab/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/ConditionOutcomeEvidenceTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'condition-outcome-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}

test {
    useJUnitPlatform()
}
```

Cần JDK 17+ và Gradle tương thích. Starter test cung cấp JUnit 5, AssertJ, Spring Boot test context runner và các dependency cần cho ví dụ.

### 7.2. File Java hoàn chỉnh

Tạo `src/test/java/demo/ConditionOutcomeEvidenceTest.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionOutcomeEvidenceTest {

    record CatalogService(String origin) {}

    record CatalogDependent(String description) {}

    record CatalogDiagnostic(String description) {}

    @AutoConfiguration
    static class CatalogSourceAutoConfiguration {

        @Bean
        CatalogService sourceCatalog() {
            return new CatalogService("auto-configuration");
        }
    }

    @AutoConfiguration(after = CatalogSourceAutoConfiguration.class)
    static class CatalogConditionAutoConfiguration {

        @Bean
        @ConditionalOnBean(CatalogService.class)
        CatalogDependent catalogDependent() {
            return new CatalogDependent("catalog is available");
        }

        @Bean
        @ConditionalOnMissingBean(CatalogService.class)
        CatalogService fallbackCatalog() {
            return new CatalogService("fallback");
        }

        @Bean
        @Conditional(CatalogPresentCondition.class)
        CatalogDiagnostic catalogDiagnostic() {
            return new CatalogDiagnostic("custom condition matched");
        }
    }

    public static class CatalogPresentCondition extends SpringBootCondition {

        @Override
        public ConditionOutcome getMatchOutcome(
                ConditionContext context,
                AnnotatedTypeMetadata metadata) {

            String[] names = context.getBeanFactory()
                    .getBeanNamesForType(CatalogService.class, true, false);

            if (names.length == 0) {
                return ConditionOutcome.noMatch(
                        "No CatalogService bean was visible at condition evaluation time");
            }

            return ConditionOutcome.match(
                    "Found CatalogService bean(s): "
                            + String.join(", ", names));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCatalogConfiguration {

        @Bean
        CatalogService userCatalog() {
            return new CatalogService("user");
        }
    }

    private ApplicationContextRunner runner(Class<?>... autoConfigurations) {
        return new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(autoConfigurations));
    }

    private ConditionEvaluationReport.ConditionAndOutcome outcomeFor(
            AssertableApplicationContext context,
            String beanMethod) {

        String source = CatalogConditionAutoConfiguration.class.getName()
                + "#" + beanMethod;

        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(context.getBeanFactory());

        var group = report.getConditionAndOutcomesBySource().get(source);
        assertThat(group).as("Report source " + source).isNotNull();

        List<ConditionEvaluationReport.ConditionAndOutcome> entries =
                new ArrayList<>();
        group.forEach(entries::add);

        assertThat(entries).as("Expected one condition for " + source)
                .hasSize(1);

        return entries.get(0);
    }

    @Test
    void sourceBeanProducesMatchAndMissingBeanNoMatch() {
        // Cố ý truyền consumer trước; metadata after vẫn sắp xếp source trước.
        runner(CatalogConditionAutoConfiguration.class,
                CatalogSourceAutoConfiguration.class)
                .run(context -> {
                    assertThat(context).hasBean("sourceCatalog");
                    assertThat(context).hasBean("catalogDependent");
                    assertThat(context).doesNotHaveBean("fallbackCatalog");
                    assertThat(context).hasBean("catalogDiagnostic");

                    var dependent = outcomeFor(context, "catalogDependent");
                    assertThat(dependent.getOutcome().isMatch()).isTrue();
                    assertThat(dependent.getOutcome().getMessage()).isNotBlank();

                    var fallback = outcomeFor(context, "fallbackCatalog");
                    assertThat(fallback.getOutcome().isMatch()).isFalse();
                    assertThat(fallback.getOutcome().getMessage()).isNotBlank();

                    var custom = outcomeFor(context, "catalogDiagnostic");
                    assertThat(custom.getCondition())
                            .isInstanceOf(CatalogPresentCondition.class);
                    assertThat(custom.getOutcome().isMatch()).isTrue();
                    assertThat(custom.getOutcome().getMessage())
                            .contains("sourceCatalog");
                });
    }

    @Test
    void absentSourceProducesNoMatchAndFallbackMatch() {
        runner(CatalogConditionAutoConfiguration.class)
                .run(context -> {
                    assertThat(context).doesNotHaveBean("sourceCatalog");
                    assertThat(context).doesNotHaveBean("catalogDependent");
                    assertThat(context).hasBean("fallbackCatalog");
                    assertThat(context).doesNotHaveBean("catalogDiagnostic");

                    var dependent = outcomeFor(context, "catalogDependent");
                    assertThat(dependent.getOutcome().isMatch()).isFalse();
                    assertThat(dependent.getOutcome().getMessage()).isNotBlank();

                    var fallback = outcomeFor(context, "fallbackCatalog");
                    assertThat(fallback.getOutcome().isMatch()).isTrue();
                    assertThat(fallback.getOutcome().getMessage()).isNotBlank();

                    var custom = outcomeFor(context, "catalogDiagnostic");
                    assertThat(custom.getOutcome().isMatch()).isFalse();
                    assertThat(custom.getOutcome().getMessage())
                            .contains("No CatalogService bean");
                });
    }

    @Test
    void userBeanIsVisibleToAutoConfigurationConditions() {
        runner(CatalogConditionAutoConfiguration.class)
                .withUserConfiguration(UserCatalogConfiguration.class)
                .run(context -> {
                    assertThat(context).hasBean("userCatalog");
                    assertThat(context).hasBean("catalogDependent");
                    assertThat(context).doesNotHaveBean("fallbackCatalog");
                    assertThat(context).hasBean("catalogDiagnostic");
                    assertThat(context.getBean(CatalogService.class).origin())
                            .isEqualTo("user");

                    assertThat(outcomeFor(context, "catalogDependent")
                            .getOutcome().isMatch()).isTrue();
                    assertThat(outcomeFor(context, "fallbackCatalog")
                            .getOutcome().isMatch()).isFalse();
                    assertThat(outcomeFor(context, "catalogDiagnostic")
                            .getOutcome().getMessage()).contains("userCatalog");
                });
    }
}
```

### 7.3. Chạy và hiểu kết quả

Chạy trong thư mục project:

```bash
gradle test --tests demo.ConditionOutcomeEvidenceTest
```

Nếu dùng Gradle Wrapper trên Linux/macOS:

```bash
./gradlew test --tests demo.ConditionOutcomeEvidenceTest
```

Trên Windows:

```powershell
.\gradlew.bat test --tests demo.ConditionOutcomeEvidenceTest
```

Kết quả mong đợi là **3 test passed**. Đây là kết quả kỳ vọng của ví dụ; log Gradle thực tế còn phụ thuộc phiên bản, test logging và môi trường. Bài này không giả định một stdout cố định.

Ma trận đọc kết quả:

| Kịch bản | Bean cuối | `catalogDependent` outcome | `fallbackCatalog` outcome | Custom outcome |
| --- | --- | --- | --- | --- |
| Có source auto-config | Source + dependent + diagnostic | match | no-match | match, message có `sourceCatalog` |
| Không có source | Fallback | no-match | match | no-match, message nêu không tìm thấy |
| Có user source | User + dependent + diagnostic | match | no-match | match, message có `userCatalog` |

Hai ý nghĩa quan trọng:

- `@ConditionalOnMissingBean` match khi không có source nghĩa là fallback được phép đăng ký. Nó không phải “tìm thấy bean”.
- Trong test có source, `fallbackCatalog` không tồn tại và outcome của condition MissingBean là no-match. Đó là hành vi đúng, không phải lỗi.

Bộ test cố tình đảo thứ tự tham số truyền vào `AutoConfigurations.of` ở test đầu. Quan hệ `after` trong metadata mới là hợp đồng ordering; đừng dùng thứ tự mảng đầu vào để kết luận condition chạy trước hay sau.

## 8. Xem report trong ứng dụng đang chạy

### 8.1. Bật debug log

Cách nhanh nhất khi điều tra một ứng dụng Spring Boot là chạy với:

```bash
java -jar app.jar --debug
```

Hoặc cấu hình `debug=true`. Spring Boot sẽ ghi condition evaluation report vào log trong quá trình startup. Tìm source class/method và đọc tên condition cùng message. Không nhầm các log này với log khởi tạo instance: condition report nói về **quyết định cấu hình**, không phải toàn bộ timeline lifecycle.

### 8.2. Dùng Actuator endpoint /actuator/conditions

Nếu ứng dụng có Spring Boot Actuator, endpoint `conditions` có thể trả report dạng JSON. Ví dụ cấu hình expose:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: conditions,health,info
```

Sau khi ứng dụng chạy, gửi request:

```bash
curl http://localhost:8080/actuator/conditions
```

Endpoint có thể chưa được expose hoặc bị bảo vệ bởi security policy; cấu hình access phù hợp với môi trường. Không mở endpoint diagnostics ra Internet công khai chỉ để tiện debug. Report có tên class, property và các thông tin cấu hình nội bộ; custom message tuyệt đối không được chứa secret.

### 8.3. Đọc đúng phần JSON

Khi source xuất hiện trong `positiveMatches`, mọi condition ghi cho source đều khớp. Khi source xuất hiện trong `negativeMatches`:

- `notMatched` cho biết condition nào không khớp.
- `matched` cho biết những condition khác của source vẫn khớp.
- Source bị xếp negative vì ít nhất một condition no-match.

Nếu source hoàn toàn không xuất hiện, điều đó không chứng minh condition đã no-match. Có thể class chưa được chọn làm candidate, bị exclude, không được import hoặc không thuộc context report đang xem. Kiểm tra `contexts`, `parentId`, `unconditionalClasses` và `getExclusions()` khi cần.

## 9. Phân tích message: đọc theo condition, không chỉ theo câu chữ

Một số message thường gặp và cách diễn giải:

| Condition trong report | Message (ý nghĩa minh họa) | Cách hiểu |
| --- | --- | --- |
| `OnClassCondition` | Required class was found | Dependency có trên runtime classpath; điều kiện lớp khớp |
| `OnClassCondition` | Did not find required class | Dependency tùy chọn vắng; source bị loại |
| `OnBeanCondition` + `@ConditionalOnBean` | Found bean 'catalogService' | Đã tìm thấy bean đáp ứng tiêu chí |
| `OnBeanCondition` + `@ConditionalOnBean` | Did not find any beans | Dependency bean chưa hiện diện/không đủ metadata |
| `OnBeanCondition` + `@ConditionalOnMissingBean` | Did not find any beans | Không có bean cạnh tranh; default có thể đăng ký |
| `OnBeanCondition` + `@ConditionalOnMissingBean` | Found bean 'catalogService' | Đã có bean; default phải nhường chỗ |
| `OnPropertyCondition` | Property matched | Giá trị property thỏa cấu hình |
| `OnPropertyCondition` | Did not find property / did not match | Property thiếu hoặc sai giá trị |
| `OnWebApplicationCondition` | Not a servlet web application | Context không phù hợp loại web được yêu cầu |

Cùng một câu “did not find any beans” có thể là **lý do match** cho `@ConditionalOnMissingBean` và **lý do no-match** cho `@ConditionalOnBean`. Tên condition quyết định ý nghĩa của message.

Khi đọc report thật, hãy ghi lại bốn yếu tố:

1. **Source:** class hay method nào đang được xét?
2. **Condition:** annotation/implementation nào đưa ra outcome?
3. **Outcome:** match hay no-match?
4. **Message:** bean, class, property hoặc search strategy nào giải thích kết quả?

Nếu message chỉ nói “no beans found”, xác minh thêm type được yêu cầu, tên bean, parent context/search strategy và kiểu trả về của factory method. Đừng kết luận sai thứ tự chỉ từ một dòng message.

## 10. Các giới hạn và lỗi thường gặp

### 10.1. Message có thể null

`ConditionOutcome.getMessage()` có thể trả `null`. Khi log thủ công, dùng xử lý null:

```java
String message = outcome.getMessage();
System.out.println(message == null ? "(no diagnostic message)" : message);
```

Không gọi `message.contains(...)` khi chưa kiểm tra null.

### 10.2. Một source có nhiều outcome

Một bean method có thể chịu nhiều condition. `isFullMatch()` chỉ true khi tất cả outcome khớp. Khi report xếp source vào negative matches, đọc toàn bộ `notMatched` và `matched` để tìm condition chặn.

### 10.3. Report không phải event log

`ConditionEvaluationReport` không ghi thời điểm constructor chạy, bean nào được khởi tạo trước, số lần gọi method hay thứ tự request. Nó là báo cáo **condition evaluation**. Để theo dõi lifecycle, dùng log khởi tạo, `ApplicationStartup` hoặc instrumentation phù hợp; đừng suy luận timeline instance từ thứ tự JSON.

### 10.4. Không phải mọi Condition đều tự có message trong Boot report

Custom class implement trực tiếp Spring `Condition` có thể trả boolean nhưng không tự đi qua cơ chế ghi nhận của `SpringBootCondition`. Nếu muốn message được log/ghi report theo cơ chế Boot, kế thừa `SpringBootCondition` và trả `ConditionOutcome`. Đừng tự thêm các message giả vào report.

### 10.5. Source không tồn tại trong map

Nếu không tìm thấy key, đừng ngay lập tức kết luận outcome là false. Có thể:

- Configuration bị exclude.
- Configuration không được import/discover.
- Condition ở cấp class đã loại nó trước khi method condition được xét.
- Đang xem report của context khác (parent/child hoặc management context).
- Key source được ghi ở class thay vì method.
- Bạn dùng tên bean thay vì tên method trong source key.

### 10.6. Message không phải API ổn định để parse

Message hướng đến con người và có thể đổi giữa patch/minor release. Trong test, ưu tiên assert `isMatch()`, bean tồn tại/vắng mặt và loại condition. Chỉ assert một phần message của custom condition do bạn sở hữu khi message đó là hợp đồng chẩn đoán mà bạn chủ động duy trì. Với message nội bộ của Boot, đọc để debug, tránh khóa test vào nguyên văn toàn bộ câu.

### 10.7. Đọc sai report của parent/child context

Mỗi BeanFactory có report riêng; `ConditionEvaluationReport` cung cấp `getParent()` để xem report cha. Trong ứng dụng có management context riêng hoặc context hierarchy, xác định đúng context id trên Actuator. Bean ở parent có thể được condition tìm thấy tùy search strategy, nhưng report của child vẫn là report được nhóm theo context của nó.

## 11. Quy trình chẩn đoán theo thứ tự

Khi một bean không xuất hiện như mong đợi, thực hiện theo trình tự:

1. **Xác nhận symptom bằng bean:** kiểm tra tên bean, type, số lượng và bean thực tế được inject. Dùng `ApplicationContextRunner` để tạo context nhỏ nếu cần.
2. **Tìm source:** dùng class name đầy đủ và `#beanMethod` trong `getConditionAndOutcomesBySource()`.
3. **Đọc cả nhóm:** kiểm tra `isFullMatch()` và duyệt từng `ConditionAndOutcome`; không dừng ở condition đầu tiên.
4. **Phân loại condition:** classpath, property, bean presence, web application, resource, expression hay custom condition?
5. **Đọc message:** ghi lại type/name/property và nguyên nhân cụ thể; xác nhận message không bị null.
6. **Đối chiếu bean definition/type metadata:** với `@ConditionalOnBean`, xem definition đã được xử lý chưa, kiểu trả về của `@Bean` có đủ cụ thể không, `FactoryBean` có công bố object type không.
7. **Kiểm tra context và ordering:** auto-configuration có được import, exclude hoặc sắp thứ tự đúng không? Condition được xét trong context nào?
8. **Tái hiện bằng test:** tạo hai context đối chứng (có/không bean hoặc có/không property), assert bean và outcome.
9. **Sửa đúng tầng:** classpath dependency, property, type metadata, auto-config ordering, user override hoặc custom condition.
10. **Giữ regression test:** assert trạng thái bean và outcome; không chỉ kiểm tra ứng dụng khởi động thành công.

### 11.1. Bảng quyết định nhanh

| Triệu chứng | Nơi kiểm tra đầu tiên | Hướng sửa thường gặp |
| --- | --- | --- |
| Bean default vẫn được tạo dù user bean đã có | Outcome của `@ConditionalOnMissingBean` và type user bean | Kiểm tra return type, search strategy và thứ tự auto-config |
| Bean phụ thuộc không xuất hiện | Outcome của `@ConditionalOnBean` | Đảm bảo source definition đã được xử lý và type nhận diện được |
| Cấu hình bị loại dù dependency có trong build file | `OnClassCondition` và runtime classpath | Sửa dependency scope/runtime classpath |
| Feature không bật dù property đã khai báo | `OnPropertyCondition` | Kiểm tra prefix, key, giá trị, `havingValue` và `matchIfMissing` |
| Có cả matched và notMatched trong negative report | Tất cả outcome của source | Xác định điều kiện no-match đang chặn source |
| Report không có source cần tìm | Exclusions, candidates, context id và class-level condition | Kiểm tra discovery/import và đúng BeanFactory |
| Custom condition không có message trong report | Condition class có kế thừa `SpringBootCondition`? | Override `getMatchOutcome` và trả `ConditionOutcome` |

## 12. Checklist khi viết custom Condition

- [ ] Condition chỉ đọc metadata/environment/registry cần thiết; không khởi tạo toàn bộ dependency để quyết định.
- [ ] Kế thừa `SpringBootCondition` khi cần logging và condition report của Boot.
- [ ] Implement `getMatchOutcome(...)`, không override `matches(...)`.
- [ ] Trả `ConditionOutcome.match(...)` hoặc `ConditionOutcome.noMatch(...)` đúng với kết quả.
- [ ] Message giải thích dữ liệu đã kiểm tra và lý do; không chứa secret.
- [ ] Xử lý trường hợp BeanFactory/metadata không có như dự kiến.
- [ ] Không dùng message để điều khiển logic; dùng `isMatch()`.
- [ ] Kiểm tra cả match và no-match bằng test context độc lập.
- [ ] Đọc report theo source class/method và kiểm tra tất cả outcome.
- [ ] Không assert nguyên văn message nội bộ của Spring Boot trong test dài hạn.
- [ ] Kiểm tra đúng context nếu có parent/child hoặc management context.
- [ ] Phân biệt condition no-match hợp lệ với lỗi startup thực sự.

**Ghi nhớ:** `ConditionOutcome` trả lời hai điều: **match hay no-match**, và **vì sao**. `ConditionEvaluationReport` tập hợp những kết quả đó theo source để người vận hành và người phát triển truy nguyên cấu hình. Khi debug, đọc tên condition trước, trạng thái tiếp theo, rồi mới diễn giải message; sau đó đối chiếu với bean thực tế trong context. Đây là cách tránh nhầm một no-match có chủ đích với lỗi auto-configuration.

## Tài liệu chính thức

- Spring Boot 3.3 API — `ConditionOutcome`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html
- Spring Boot 3.3 API — `SpringBootCondition`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html
- Spring Boot 3.3 API — `ConditionEvaluationReport`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.3 API — `ConditionEvaluationReport.ConditionAndOutcome`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.ConditionAndOutcome.html
- Spring Boot 3.3 API — `ConditionMessage`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionMessage.html
- Spring Boot 3.3 Actuator — Conditions Evaluation Report: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
