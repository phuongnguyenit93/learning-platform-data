# ConditionEvaluationReport và cách tra cứu kết quả theo nguồn cấu hình

## 1. Mục tiêu: tìm được vì sao một tính năng tự cấu hình có hoặc không xuất hiện

Khi một bean do Spring Boot auto-configuration cung cấp không xuất hiện, chỉ nhìn vào file `application.yml` thường chưa đủ để kết luận nguyên nhân. Có thể điều kiện `@ConditionalOnProperty` không khớp, class phụ thuộc không có trên classpath, một bean người dùng đã khiến `@ConditionalOnMissingBean` back off, ứng dụng đã exclude auto-configuration, hoặc một điều kiện web/servlet không thỏa.

Spring Boot ghi nhận kết quả đánh giá các điều kiện trong **`ConditionEvaluationReport`**. Report này cho biết:

- Cấu hình hoặc phương thức bean nào là **source** của điều kiện.
- Condition nào đã được đánh giá.
- Kết quả khớp hay không khớp.
- Thông điệp giải thích do condition cung cấp.
- Các lớp auto-configuration bị exclude và các lớp không có điều kiện.

Có một điểm rất dễ nhầm khi tra cứu: **source trong `ConditionEvaluationReport` là nguồn khai báo điều kiện (configuration class hoặc bean method); nó không phải `PropertySource` đã cung cấp giá trị cho một khóa cấu hình.** Muốn biết giá trị `acme.export.enabled` đến từ file nào, biến môi trường hay command line, cần tra cứu `Environment` riêng.

Bài này hướng dẫn cả hai chiều:

1. Tìm kết quả condition theo class/bean method trong report.
2. Tìm nguồn và origin của property đã làm condition khớp hoặc không khớp.
3. Đối chiếu giá trị raw trong Environment với giá trị đã bind vào `@ConfigurationProperties`.
4. Kiểm chứng bằng Java 17+ và Spring Boot 3.3.

## 2. ConditionEvaluationReport là gì?

`org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport` là lớp Spring Boot dùng để **ghi lại kết quả đánh giá condition**. Các condition thường gặp là:

- `@ConditionalOnClass` / `@ConditionalOnMissingClass`: kiểm tra class có hoặc không có trên classpath.
- `@ConditionalOnProperty`: kiểm tra một thuộc tính trong Spring `Environment`.
- `@ConditionalOnBean` / `@ConditionalOnMissingBean`: kiểm tra bean phù hợp đã có hay chưa.
- `@ConditionalOnWebApplication` / `@ConditionalOnNotWebApplication`: kiểm tra loại ứng dụng.
- Các condition tùy chỉnh triển khai Spring `Condition`.

Mỗi lần condition được đánh giá, report lưu một bộ thông tin gồm:

| Thành phần | Ý nghĩa |
|---|---|
| `source` | Lớp cấu hình hoặc phương thức bean mà condition gắn vào |
| `condition` | Đối tượng condition thực hiện kiểm tra |
| `outcome` | Kết quả khớp/không khớp cùng thông điệp giải thích |

Một condition có thể khớp trong khi một condition khác trên cùng source không khớp. Vì vậy report cần cho thấy **từng outcome**, không chỉ một trạng thái chung của class.

### Source trong report là gì?

Ví dụ:

```java
@AutoConfiguration
public class ExportAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "acme.export",
        name = "enabled",
        havingValue = "true")
    ExportClient exportClient() {
        return new ExportClient();
    }
}
```

Nếu condition nằm trên phương thức `exportClient()`, source trong report thường được biểu diễn theo dạng:

```text
com.acme.ExportAutoConfiguration#exportClient
```

Nếu condition gắn trên cả lớp cấu hình, source có thể là tên lớp:

```text
com.acme.ExportAutoConfiguration
```

Do đó, khi tra cứu theo source, hãy tìm **tên fully qualified của class hoặc tên method**. Dấu `#` phân tách class và method trong dạng hiển thị thường gặp.

### Report không phải danh sách bean đã khởi tạo

Condition khớp có nghĩa là điều kiện cho phép cấu hình/bean definition đi tiếp. Điều đó không bảo đảm object bean đã được khởi tạo thành công: dependency injection, constructor, factory method hoặc lifecycle vẫn có thể thất bại về sau. Ngược lại, một bean cùng kiểu có thể được cung cấp bởi cấu hình khác dù auto-configuration đang xét không khớp.

Hãy phân biệt:

- **Condition match:** điều kiện cho phép một nhánh cấu hình.
- **Bean definition:** định nghĩa bean được đăng ký vào BeanFactory.
- **Bean instance:** object thực tế được tạo khi Spring cần khởi tạo bean.

Report trả lời câu hỏi về **điều kiện**, không thay thế việc kiểm tra bean definition, instance hoặc lỗi khởi tạo.

## 3. Cấu trúc dữ liệu của report và cách đọc theo source

Trong API Spring Boot 3.3, lớp `ConditionEvaluationReport` cung cấp các phương thức quan trọng:

| API | Công dụng |
|---|---|
| `getConditionAndOutcomesBySource()` | Lấy `Map` kết quả condition, nhóm theo source |
| `getExclusions()` | Danh sách tên class đã bị exclude khỏi đánh giá condition |
| `getUnconditionalClasses()` | Các class được đánh giá nhưng không có condition |
| `getParent()` | Report của parent BeanFactory nếu có |
| `get(beanFactory)` | Lấy report gắn với BeanFactory |
| `find(beanFactory)` | Thử tìm report; có thể trả về `null` |

Giá trị của `getConditionAndOutcomesBySource()` là:

```java
Map<String, ConditionEvaluationReport.ConditionAndOutcomes>
```

Mỗi entry có key là source (class hoặc method) và value là tập `ConditionAndOutcome`. Tập này có thể duyệt bằng vòng `for-each`; `isFullMatch()` trả `true` khi **mọi outcome trong source đều khớp**.

Mỗi `ConditionAndOutcome` cung cấp:

- `getCondition()`: condition đã được chạy.
- `getOutcome()`: kết quả condition.

Với `ConditionOutcome`:

- `isMatch()` cho biết condition khớp hay không.
- `getMessage()` trả về thông điệp giải thích; có thể `null`.

### Ví dụ cấu trúc report ở dạng dễ đọc

Giả sử source `ExportAutoConfiguration#exportClient` có condition property khớp:

```text
source: com.acme.ExportAutoConfiguration#exportClient
  condition: OnPropertyCondition
  outcome: MATCH
  message: @ConditionalOnProperty (...) matched
```

Nếu khóa cấu hình không thỏa:

```text
source: com.acme.ExportAutoConfiguration#exportClient
  condition: OnPropertyCondition
  outcome: NO MATCH
  message: @ConditionalOnProperty (...) did not find/does not match ...
```

Đây là **mô hình minh họa**, nội dung message thực tế phụ thuộc condition, phiên bản và giá trị đầu vào. Không nên viết script phụ thuộc vào toàn bộ câu message vì đó là nội dung chẩn đoán; hãy dùng key source, tên condition và trạng thái outcome để phân loại, rồi đọc message khi cần hiểu chi tiết.

### Positive và negative match

Report thường được trình bày thành hai nhóm:

| Nhóm | Ý nghĩa |
|---|---|
| `positiveMatches` | Source có các condition được khớp |
| `negativeMatches` | Source không đạt đầy đủ điều kiện; có thể xem condition không khớp và condition khác đã khớp |
| `unconditionalClasses` | Các lớp không có condition trong report |

Với một source có nhiều condition, chỉ cần một condition bắt buộc không khớp thì cấu hình có thể không được áp dụng, dù các condition còn lại đã khớp. Khi xem `negativeMatches`, đừng chỉ đọc dòng đầu; đọc cả phần `notMatched` và `matched` để biết chính xác điều kiện nào chặn cấu hình.

## 4. Cách 1: bật report khi khởi động bằng --debug

Đây là cách nhanh nhất khi cần chẩn đoán ứng dụng đang chạy hoặc ứng dụng không khởi động được.

Nếu chạy executable JAR:

```bash
java -jar app.jar --debug
```

Hoặc bật thuộc tính:

```properties
debug=true
```

Spring Boot sẽ in thêm báo cáo quyết định auto-configuration ra log. Báo cáo thường chứa các nhóm positive matches và negative matches cùng lý do.

**Debug mode không có nghĩa mọi logger trong ứng dụng đều chuyển sang DEBUG.** Spring Boot chỉ bật thêm thông tin cho một nhóm logger quan trọng; mục tiêu ở đây là xem report điều kiện. Nếu cần bật logger cụ thể, có thể cấu hình:

```properties
logging.level.org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener=DEBUG
```

Một API khác là `ConditionEvaluationReportLoggingListener`, một `ApplicationContextInitializer` ghi report ở mức DEBUG; từ Spring Boot 3.0 có factory method `forLogLevel(...)` để chọn log level cho report. Thông thường không cần tự đăng ký listener nếu chỉ muốn xem báo cáo bằng `--debug`.

### Khi nào dùng --debug?

- Bean tự cấu hình không xuất hiện sau khi khởi động.
- Muốn biết condition classpath, property hay bean đang không khớp.
- Ứng dụng fail startup và cần xem toàn bộ các quyết định auto-configuration.
- Đang phát triển starter/auto-configuration và cần xác minh thứ tự condition.

Khi chỉ cần chẩn đoán một property, đừng dừng ở report. Tiếp tục tra nguồn property ở mục 7 để xác định vì sao giá trị condition nhận được khác dự đoán.

## 5. Cách 2: xem report qua Spring Boot Actuator /conditions

Nếu ứng dụng đã dùng Spring Boot Actuator, endpoint `conditions` trả report ở dạng JSON.

Thêm dependency vào Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Cấu hình expose các endpoint cần dùng trong `application.properties`:

```properties
management.endpoints.web.exposure.include=health,info,conditions,env,configprops
```

Sau khi ứng dụng khởi động, gọi:

```bash
curl http://localhost:8080/actuator/conditions
```

Endpoint mặc định là `/actuator/conditions` nếu không thay base path. Nếu ứng dụng đổi `management.endpoints.web.base-path` thì URL cũng đổi theo.

### Cấu trúc JSON quan trọng

Response có cấu trúc chính:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "com.acme.ExportAutoConfiguration#exportClient": [
          {
            "condition": "OnPropertyCondition",
            "message": "..."
          }
        ]
      },
      "negativeMatches": {
        "com.acme.CacheAutoConfiguration#cacheClient": {
          "notMatched": [
            {
              "condition": "OnClassCondition",
              "message": "..."
            }
          ],
          "matched": [
            {
              "condition": "OnPropertyCondition",
              "message": "..."
            }
          ]
        }
      },
      "unconditionalClasses": [
        "com.acme.CommonAutoConfiguration"
      ]
    }
  }
}
```

Đây là JSON **minh họa cấu trúc**, không phải output của một ứng dụng cụ thể.

| JSON path | Ý nghĩa |
|---|---|
| `contexts` | Các application context, được định danh theo id |
| `contexts.*.positiveMatches` | Source có condition khớp |
| `contexts.*.negativeMatches` | Source không đạt đầy đủ condition |
| `negativeMatches.*.notMatched` | Các condition không khớp |
| `negativeMatches.*.matched` | Các condition khác đã khớp trong cùng source |
| `contexts.*.unconditionalClasses` | Các class không có condition |
| `contexts.*.parentId` | Id của parent context nếu có |

Nếu ứng dụng có nhiều context (ví dụ root và child), phải chọn đúng entry dưới `contexts`. Không giả định luôn chỉ có một key `application`.

### Tra cứu một source cụ thể bằng jq

Endpoint trả về report; không phải API tìm kiếm server-side theo tên class. Có thể lọc JSON tại máy:

```bash
curl -s http://localhost:8080/actuator/conditions \
  | jq '.contexts.application.positiveMatches["com.acme.ExportAutoConfiguration#exportClient"]'
```

Tra source trong nhóm negative:

```bash
curl -s http://localhost:8080/actuator/conditions \
  | jq '.contexts.application.negativeMatches["com.acme.ExportAutoConfiguration#exportClient"]'
```

Nếu không biết source chính xác, liệt kê key trước:

```bash
curl -s http://localhost:8080/actuator/conditions \
  | jq '.contexts.application.positiveMatches | keys'
```

Hoặc:

```bash
curl -s http://localhost:8080/actuator/conditions \
  | jq '.contexts.application.negativeMatches | keys'
```

Sau đó copy đúng key vào câu lệnh lọc. Dấu `#` trong tên source là ký tự của key JSON, không phải fragment URL.

## 6. Cách 3: đọc ConditionEvaluationReport trực tiếp bằng Java

Khi viết integration test hoặc công cụ chẩn đoán nội bộ, có thể truy cập report từ BeanFactory.

Ví dụ:

```java
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;

ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

report.getConditionAndOutcomesBySource().forEach((source, outcomes) -> {
    System.out.println("SOURCE: " + source);
    System.out.println("FULL MATCH: " + outcomes.isFullMatch());

    for (ConditionEvaluationReport.ConditionAndOutcome item : outcomes) {
        System.out.println(
                "  condition=" + item.getCondition().getClass().getSimpleName());
        System.out.println(
                "  matched=" + item.getOutcome().isMatch());
        System.out.println(
                "  message=" + item.getOutcome().getMessage());
    }
});
```

Đoạn code này giả định `context` là `AnnotationConfigApplicationContext` hoặc context cụ thể có `getBeanFactory()` trả `ConfigurableListableBeanFactory`. Với các kiểu context khác, cần lấy đúng BeanFactory của context đang điều tra.

Để chỉ xem một source:

```java
var sourceEntry = report.getConditionAndOutcomesBySource()
        .entrySet()
        .stream()
        .filter(entry ->
                entry.getKey().contains("ExportAutoConfiguration#exportClient"))
        .findFirst();

sourceEntry.ifPresent(entry -> {
    System.out.println("Source: " + entry.getKey());
    System.out.println("Full match: " + entry.getValue().isFullMatch());

    for (var item : entry.getValue()) {
        System.out.println(item.getCondition().getClass().getSimpleName()
                + " -> " + item.getOutcome().isMatch()
                + " : " + item.getOutcome().getMessage());
    }
});
```

Nếu không tìm thấy source, cần kiểm tra:
- Class có thật sự được nạp/đánh giá trong context đó không?
- Condition nằm trên class hay bean method?
- Source key thực tế có đúng package/class/method không?
- Class có bị exclude hoặc chưa được import không?
- Có đang đọc report của parent/child BeanFactory khác không?

Không nên coi việc không tìm thấy source là condition đã khớp hoặc không khớp; có thể source chưa được đánh giá nên chưa có entry.

### Các API bổ trợ

```java
report.getExclusions();
report.getUnconditionalClasses();
report.getParent();
```

- `getExclusions()` hữu ích khi nghi ngờ auto-configuration đã bị exclude.
- `getUnconditionalClasses()` cho biết các class được ghi nhận mà không có condition.
- `getParent()` giúp tiếp tục xem report của parent BeanFactory khi ứng dụng có context hierarchy.

`ConditionEvaluationReport.get(beanFactory)` lấy report, còn `find(beanFactory)` dùng khi muốn thử tìm report và chấp nhận trường hợp không có report. Không dùng report của context cha để kết luận condition ở context con mà chưa xác định phạm vi.

## 7. “Nguồn” của condition khác “nguồn” của property

Đây là phần quan trọng nhất khi đề bài yêu cầu tra cứu kết quả theo nguồn cấu hình.

Có hai câu hỏi khác nhau:

| Câu hỏi | Nơi tra cứu | Ví dụ |
|---|---|---|
| Condition của class/method nào khớp? | `ConditionEvaluationReport` / `/actuator/conditions` | `ExportAutoConfiguration#exportClient` |
| Giá trị property đến từ nguồn nào? | Spring `Environment` / `/actuator/env/{property.name}` | `application-prod.yml`, environment variable, command line |
| Giá trị đã bind vào object properties là gì? | `/actuator/configprops/{prefix}` hoặc object trong code | `ExportProperties.format` |

**Không có quan hệ một-một giữa source trong report và PropertySource.** Một method `@Bean` có thể có nhiều condition, và một condition có thể đọc nhiều property. Report ghi kết quả condition, nhưng không phải lúc nào cũng cho biết file/dòng gốc của từng property. Muốn biết nguồn thật, phải hỏi Environment.

### 7.1. Tra một property bằng Actuator /env

Gọi:

```bash
curl http://localhost:8080/actuator/env/acme.export.enabled
```

Với property tồn tại, response cung cấp thông tin dạng:

```json
{
  "property": {
    "source": "Config resource 'class path resource [application-prod.yml]'",
    "value": "true"
  },
  "propertySources": [
    {
      "name": "commandLineArgs"
    },
    {
      "name": "systemProperties"
    },
    {
      "name": "systemEnvironment"
    },
    {
      "name": "Config resource 'class path resource [application-prod.yml]'",
      "property": {
        "value": "true",
        "origin": "class path resource [application-prod.yml] - 4:13"
      }
    }
  ]
}
```

Đây là response **minh họa** để hiểu trường dữ liệu; nguồn, giá trị và origin thật tùy ứng dụng. Cần chú ý:

- `property.source` cho biết nguồn được chọn cho property đang truy vấn.
- `property.value` là giá trị hiệu lực, nếu có.
- `propertySources` liệt kê các PropertySource theo thứ tự ưu tiên.
- `propertySources[].property.origin` có thể cho biết file/dòng hoặc vị trí gốc của property nếu nguồn hỗ trợ origin tracking.
- Nếu key không có trong Environment, trường `property` có thể vắng mặt.

Endpoint `env` còn hỗ trợ truy vấn toàn Environment tại `/actuator/env`, nhưng khi gỡ lỗi nên truy vấn **một key cụ thể** để giảm nhiễu và tránh đọc những cấu hình không liên quan.

### 7.2. Xem thứ tự nguồn cấu hình

Nếu `application.yml` đặt:

```yaml
acme:
  export:
    enabled: false
```

nhưng command line chạy ứng dụng với:

```bash
java -jar app.jar --acme.export.enabled=true
```

thì `/actuator/env/acme.export.enabled` có thể cho thấy giá trị hiệu lực `true` đến từ nguồn command line; file YAML vẫn tồn tại nhưng có ưu tiên thấp hơn. Condition `@ConditionalOnProperty(havingValue="true")` vì vậy có thể khớp.

Ngược lại, nếu command line đặt `false` trong khi file YAML đặt `true`, giá trị hiệu lực là `false` và condition không khớp (với SpringApplication mặc định và không có nguồn ưu tiên cao hơn khác).

Không nên suy luận nguồn thắng chỉ từ thứ tự các file được nhìn thấy trong repository. Profile, `spring.config.import`, custom PropertySource và test property source có thể làm thứ tự thực tế thay đổi.

### 7.3. Xem giá trị đã bind vào @ConfigurationProperties

Nếu thư viện có:

```java
@ConfigurationProperties(prefix = "acme.export")
public class ExportProperties {
    private boolean enabled;
    private String format = "csv";

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getFormat() {
        return format;
    }

    public void setFormat(String format) {
        this.format = format;
    }
}
```

thì endpoint:

```bash
curl http://localhost:8080/actuator/configprops/acme.export
```

giúp quan sát bean `@ConfigurationProperties` đã bind dưới prefix đó. Dùng `env` để tìm nguồn property và dùng `configprops` để xem giá trị đã bind; hai endpoint trả lời hai câu hỏi khác nhau.

Mặc định endpoint có thể che/sanitize các giá trị nhạy cảm tùy chính sách. Không nên tắt sanitization chỉ để tiện debug trong môi trường thật.

## 8. Ghép ba bằng chứng để tìm nguyên nhân

Giả sử bean `exportClient` không xuất hiện. Một cách điều tra có trình tự:

1. Mở `/actuator/conditions` hoặc chạy `--debug`, tìm source `com.acme.ExportAutoConfiguration#exportClient`.
2. Nếu source ở `negativeMatches`, đọc `notMatched` để biết condition nào chặn. Nếu là `OnPropertyCondition`, ghi nhận key và expected value trong message.
3. Gọi `/actuator/env/acme.export.enabled` để biết giá trị hiệu lực và PropertySource/origin.
4. Nếu condition liên quan tới bean type, xem `/actuator/beans` hoặc report của các auto-config tạo bean phụ thuộc.
5. Nếu condition khớp nhưng bean vẫn không dùng được, xem lỗi khởi tạo và dependency của bean; report không bảo đảm constructor/factory method đã chạy thành công.
6. Nếu property đúng nhưng object cấu hình khác dự kiến, xem `/actuator/configprops/acme.export` và kiểm tra default, relaxed binding, validation hoặc kiểu dữ liệu.

### Ma trận đọc kết quả

| Condition report | Environment | Kết luận nên kiểm tra |
|---|---|---|
| Property condition không khớp | Giá trị thiếu | Kiểm tra `matchIfMissing` và key có được nạp không |
| Property condition không khớp | Giá trị `false` từ command line | Nguồn ưu tiên cao đang tắt feature |
| Property condition không khớp | Giá trị sai như `treu` | Lỗi gõ/giá trị không đúng `havingValue` |
| Property condition khớp | Giá trị `true` đúng | Xem các condition khác, missing-bean và lỗi tạo instance |
| Bean condition không khớp | Property condition vẫn khớp | Kiểm tra bean cùng kiểu đã có, `SearchStrategy` và thời điểm đăng ký |
| Condition source không xuất hiện | Không tìm thấy class trong candidate | Kiểm tra imports, exclude, classpath và context đang xem |
| Condition source không xuất hiện | Bean vẫn tồn tại | Bean có thể đến từ cấu hình người dùng hoặc auto-config khác |

Không kết luận từ một dòng duy nhất. Một cấu hình có thể có condition ở cấp class và ở từng phương thức `@Bean`; report có thể có nhiều entry liên quan tới cùng một tính năng.

## 9. Ví dụ chạy được: xem report theo source và property source

Ví dụ dưới đây dùng **Java 17+**, Spring Boot 3.3.13 và Maven. Nó tạo hai nguồn cấu hình mô phỏng: `applicationConfig` ở ưu tiên thấp và `deployment` ở ưu tiên cao. Mỗi kịch bản tạo một context mới, đánh giá `@ConditionalOnProperty`, rồi in:

- Giá trị property hiệu lực.
- PropertySource thắng.
- Source condition được tìm thấy trong `ConditionEvaluationReport`.
- Kết quả condition và việc bean có tồn tại ở context hay không.

### 9.1. Cấu trúc

```text
condition-report-demo/
├── pom.xml
└── src/main/java/demo/report/
    └── ConditionReportDemo.java
```

### 9.2. pom.xml

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
    <artifactId>condition-report-demo</artifactId>
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
</project>
```

### 9.3. ConditionReportDemo.java

```java
package demo.report;

import java.util.Map;

import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.PropertySource;

public class ConditionReportDemo {

    private static final String ENABLED = "acme.export.enabled";

    @Configuration(proxyBeanMethods = false)
    static class ExportConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "acme.export",
                name = "enabled",
                havingValue = "true",
                matchIfMissing = false)
        String exportClient() {
            return "export-ready";
        }
    }

    private static void inspect(String enabledValue) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            var propertySources = context.getEnvironment().getPropertySources();

            // Nguồn ưu tiên thấp: mô phỏng application.yml.
            propertySources.addLast(new MapPropertySource(
                    "applicationConfig",
                    Map.of(ENABLED, "false")));

            // Nguồn ưu tiên cao: mô phỏng cấu hình triển khai.
            propertySources.addFirst(new MapPropertySource(
                    "deployment",
                    Map.of(ENABLED, enabledValue)));

            context.register(ExportConfiguration.class);
            context.refresh();

            String winningPropertySource = "<missing>";
            for (PropertySource<?> source : propertySources) {
                if (source.containsProperty(ENABLED)) {
                    winningPropertySource = source.getName();
                    break;
                }
            }

            ConditionEvaluationReport report =
                    ConditionEvaluationReport.get(context.getBeanFactory());

            var reportSource = report.getConditionAndOutcomesBySource()
                    .entrySet()
                    .stream()
                    .filter(entry ->
                            entry.getKey().contains(
                                    "ExportConfiguration#exportClient"))
                    .findFirst()
                    .orElseThrow(() -> new IllegalStateException(
                            "Condition source was not recorded"));

            System.out.printf(
                    "enabled=%s effective=%s propertySource=%s "
                            + "reportSourceFound=true conditionMatched=%s bean=%s%n",
                    enabledValue,
                    context.getEnvironment().getProperty(ENABLED),
                    winningPropertySource,
                    reportSource.getValue().isFullMatch(),
                    context.containsBean("exportClient"));
        }
    }

    public static void main(String[] args) {
        inspect("true");
        inspect("false");
    }
}
```

Từ thư mục `condition-report-demo` chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.report.ConditionReportDemo
```

Để dùng `exec:java`, thêm plugin vào phần `build/plugins` của `pom.xml` nếu Maven project chưa có:

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>exec-maven-plugin</artifactId>
    <version>3.3.0</version>
</plugin>
```

**Hai dòng do chương trình in ra:**

```text
enabled=true effective=true propertySource=deployment reportSourceFound=true conditionMatched=true bean=true
enabled=false effective=false propertySource=deployment reportSourceFound=true conditionMatched=false bean=false
```

Giải thích:

1. `applicationConfig` được thêm bằng `addLast`; nó cung cấp `false` nhưng có ưu tiên thấp.
2. `deployment` được thêm bằng `addFirst`; nó cung cấp giá trị cao hơn và là nguồn thắng cho key.
3. Mỗi lần `inspect(...)` tạo context mới, nên tình huống `true` không ảnh hưởng lần chạy `false`.
4. `ConditionEvaluationReport.get(context.getBeanFactory())` lấy report gắn với BeanFactory hiện tại.
5. `getConditionAndOutcomesBySource()` trả về map; code lọc source chứa `ExportConfiguration#exportClient` rồi đọc `isFullMatch()`.
6. `containsBean("exportClient")` xác nhận bean thực sự được đăng ký ở context. Đây là phép kiểm tra riêng với report.
7. Kết quả cho thấy **source của condition** và **PropertySource của giá trị** là hai thông tin khác nhau: source condition là phương thức `exportClient`; property source thắng là `deployment`.

Ví dụ này dùng `AnnotationConfigApplicationContext` để minh họa trực tiếp API report và condition của Spring Boot; trong ứng dụng thực tế, auto-configuration thường được Boot import qua `AutoConfiguration.imports` và Actuator cung cấp endpoint JSON cho việc điều tra từ xa.

## 10. Các lỗi thường gặp khi đọc report

| Nhầm lẫn | Thực tế | Cách sửa |
|---|---|---|
| Tưởng source trong report là file YAML | Source là class/method khai báo condition | Dùng `/actuator/env/{key}` để tìm PropertySource |
| Chỉ nhìn positiveMatches | Bean có thể vắng do condition nằm trong negativeMatches | Tra cả positive và negative source |
| Chỉ đọc message đầu tiên | Một source có nhiều condition | Đọc mọi entry của source và xem condition không khớp |
| Condition match nghĩa bean đã chạy constructor | Report chỉ phản ánh điều kiện | Kiểm tra bean, dependency và lỗi khởi tạo riêng |
| Không tìm thấy source nghĩa condition false | Source có thể chưa được đánh giá, bị exclude hoặc không được import | Kiểm tra candidate/imports, exclusions và context |
| Đọc report ở context cha để kết luận context con | Report gắn theo BeanFactory/context | Xem đúng context id và `getParent()` |
| Giá trị trong `application.yml` khác với report nên nghĩ Boot lỗi | Có thể env/CLI/system property/profile ghi đè | Dùng `/actuator/env/{property.name}` |
| configprops hiển thị default nên nghĩ Environment có key | Default Java của object có thể không phải PropertySource | So sánh `env` và `configprops` |
| Property condition khớp nhưng bean không dùng được | Một condition khác hoặc quá trình tạo bean có thể lỗi | Kiểm tra full source, dependencies và startup log |
| Tìm kiếm chuỗi message cố định trong script | Message là nội dung chẩn đoán, có thể đổi theo phiên bản | Dựa trên source key, condition class và outcome |

## 11. Quy trình điều tra chuẩn

Khi một tính năng thư viện không được auto-config như mong đợi:

1. **Xác định bean cần kiểm tra** và auto-configuration/method được cho là tạo bean đó.
2. Bật `--debug` hoặc gọi `GET /actuator/conditions`.
3. Tìm source key dạng `FullyQualifiedAutoConfiguration#beanMethod`; xem toàn bộ condition outcomes.
4. Nếu `OnPropertyCondition` không khớp, gọi `GET /actuator/env/{property.name}` để xác định giá trị cuối, nguồn và origin.
5. Nếu dùng `@ConfigurationProperties`, gọi `GET /actuator/configprops/{prefix}` để so sánh object đã bind.
6. Nếu `OnBeanCondition` không khớp, kiểm tra bean type/name, `SearchStrategy`, context hierarchy và thời điểm đăng ký bean definition.
7. Nếu mọi condition đều khớp nhưng ứng dụng vẫn lỗi, kiểm tra log khởi tạo bean và dependency; report không thay thế stack trace.
8. Lưu lại source, condition, outcome, message, property key, winning PropertySource và origin trong bug report để có thể tái hiện.

## 12. Bảo vệ các endpoint chẩn đoán

`conditions` thường chứa tên class, tên bean và lý do cấu hình được bật/tắt. `env` có thể tiết lộ cấu hình triển khai; `configprops` có thể cho biết giá trị đã bind. Khi expose qua HTTP:

- Chỉ expose endpoint thực sự cần thiết.
- Giới hạn truy cập bằng Spring Security, mạng nội bộ hoặc cơ chế quản lý tương đương.
- Giữ sanitization của giá trị nhạy cảm; không đưa password, token hoặc secret vào log/debug report.
- Không mở toàn bộ endpoint Actuator ra Internet chỉ để tra một condition.
- Nếu chỉ cần debug một lần, có thể bật `--debug` trong môi trường kiểm thử thay vì expose endpoint quản trị lâu dài.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Trong `getConditionAndOutcomesBySource()`, key `com.acme.ExportAutoConfiguration#exportClient` biểu diễn điều gì?

**Đáp án:** Source của condition: lớp `ExportAutoConfiguration` và phương thức bean `exportClient`. Nó không phải tên file cấu hình hay PropertySource.

**Câu 2.** Muốn biết `acme.export.enabled=true` đến từ command line hay `application-prod.yml`, xem endpoint nào?

**Đáp án:** `/actuator/env/acme.export.enabled`. Report conditions cho biết condition khớp hay không; endpoint env cho biết nguồn property và origin.

**Câu 3.** `positiveMatches` có chứng minh bean instance đã được khởi tạo thành công không?

**Đáp án:** Không. Nó chứng minh condition/source được đánh giá là khớp. Quá trình tạo instance và dependency có thể thất bại sau đó.

**Câu 4.** `negativeMatches` cho thấy một source có một condition khớp và một condition không khớp. Source có được xem là full match không?

**Đáp án:** Không. `ConditionAndOutcomes.isFullMatch()` chỉ true khi tất cả outcome trong source đều khớp.

**Câu 5.** Không thấy class trong `positiveMatches` lẫn `negativeMatches`. Có thể kết luận nó bị condition property chặn không?

**Đáp án:** Không. Class có thể chưa được import/đánh giá, bị exclude, không nằm trong candidate list, hoặc đang xem sai context. Cần kiểm tra imports, exclusions và context trước.

## 14. Ghi nhớ

- **`ConditionEvaluationReport`** ghi kết quả condition theo source là configuration class hoặc bean method.
- **`getConditionAndOutcomesBySource()`** cho phép truy vấn từng source, duyệt condition và đọc `isMatch()/getMessage()`.
- **`--debug`** là cách nhanh để xem report trong log.
- **`/actuator/conditions`** trả report JSON theo application context, positive matches và negative matches.
- **`/actuator/env/{property.name}`** mới là nơi tra cứu giá trị property, PropertySource thắng và origin.
- **`/actuator/configprops/{prefix}`** cho biết giá trị đã bind vào bean `@ConfigurationProperties`.
- Report condition không phải bằng chứng bean instance đã khởi tạo thành công; hãy kết hợp với bean state và log runtime.

### Tài liệu chính thức

- [Spring Boot 3.3 — ConditionEvaluationReport API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html)
- [Spring Boot 3.3 — ConditionEvaluationReportLoggingListener API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html)
- [Spring Boot 3.3 — Conditions Actuator Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html)
- [Spring Boot 3.3 — Environment Actuator Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/env.html)
- [Spring Boot 3.3 — Configuration Properties Actuator Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/configprops.html)
