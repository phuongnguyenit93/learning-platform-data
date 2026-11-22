# ConditionEvaluationReport để giải thích điều kiện khớp hoặc không khớp

Spring Boot có nhiều cơ chế đăng ký bean theo điều kiện. Một cấu hình có thể chỉ được kích hoạt khi một class nằm trên classpath, một property có giá trị cụ thể, một bean khác đã tồn tại, hoặc ứng dụng đang chạy trong môi trường web. Cách làm này giúp thư viện và ứng dụng chỉ tạo những thành phần phù hợp với môi trường hiện tại.

Khi một bean không xuất hiện như mong đợi, câu hỏi thường gặp là: **điều kiện nào đã được kiểm tra, điều kiện nào khớp, và điều kiện nào khiến cấu hình bị bỏ qua?** Spring Boot cung cấp **`ConditionEvaluationReport`** để ghi lại kết quả đánh giá các điều kiện cấu hình. Report này giúp giải thích vì sao một auto-configuration hoặc configuration có điều kiện được áp dụng hay không được áp dụng.

Trong chương **Cấu hình theo điều kiện** của *Spring Boot Fundamentals*, bài học này hướng dẫn cách đọc condition evaluation report, bật log chẩn đoán, xem endpoint Actuator, viết cấu hình có điều kiện và kiểm thử cả trường hợp khớp lẫn không khớp.

## 1. Vì sao Spring Boot cần đánh giá điều kiện?

Giả sử một ứng dụng có tính năng audit tùy chọn. Nhóm muốn:

- Khi property `feature.audit.enabled=true`, Spring tạo `AuditService`.
- Khi property không có hoặc mang giá trị khác, tính năng audit không được bật.
- Nếu ứng dụng đã có implementation riêng, cấu hình mặc định có thể nhường chỗ cho bean do ứng dụng cung cấp.

Thay vì viết nhiều câu lệnh điều kiện thủ công trong `main`, Spring Boot cho phép mô tả điều kiện ngay trên configuration class hoặc bean method:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true"
)
class AuditConfiguration {

    @Bean
    AuditService auditService() {
        return new AuditService();
    }
}
```

Khi Spring xử lý configuration class, nó đánh giá điều kiện `@ConditionalOnProperty`. Nếu điều kiện khớp, cấu hình được xử lý và bean definition có thể được đăng ký. Nếu điều kiện không khớp, cấu hình đó được bỏ qua.

Các annotation điều kiện thường gặp:

| Annotation | Điều kiện tiêu biểu |
| --- | --- |
| `@ConditionalOnClass` | Một hoặc nhiều class có mặt trên classpath |
| `@ConditionalOnMissingClass` | Một hoặc nhiều class không có trên classpath |
| `@ConditionalOnBean` | Đã có bean phù hợp trong context/registry tại thời điểm đánh giá |
| `@ConditionalOnMissingBean` | Chưa có bean phù hợp tại thời điểm đánh giá |
| `@ConditionalOnProperty` | Property có mặt hoặc có giá trị đáp ứng điều kiện |
| `@ConditionalOnResource` | Tài nguyên được chỉ định tồn tại |
| `@ConditionalOnWebApplication` | Ứng dụng thuộc loại web phù hợp |
| `@ConditionalOnNotWebApplication` | Ứng dụng không thuộc loại web được xét |
| `@ConditionalOnExpression` | Biểu thức SpEL cho kết quả phù hợp |

Điều kiện giúp cấu hình linh hoạt, nhưng cũng khiến việc tìm nguyên nhân bean không xuất hiện khó hơn nếu chỉ nhìn vào class Java. Condition evaluation report cung cấp bằng chứng về quá trình này.

## 2. ConditionEvaluationReport là gì?

`ConditionEvaluationReport` là một cấu trúc dữ liệu của Spring Boot ghi lại kết quả đánh giá các condition trong quá trình xử lý cấu hình. Nó được sử dụng để giải thích kết quả của auto-configuration và những configuration có điều kiện.

Report có thể lưu các thông tin như:

- Nguồn cấu hình hoặc bean definition được đánh giá.
- Các condition đã được kiểm tra.
- Kết quả khớp hoặc không khớp của từng condition.
- Thông điệp giải thích vì sao condition trả về kết quả đó.
- Các auto-configuration bị loại trừ.
- Các cấu hình không cần điều kiện được ghi nhận như unconditional classes.

Ví dụ một kết quả minh họa:

```text
Positive matches:
  AuditAutoConfiguration:
    - @ConditionalOnProperty (feature.audit.enabled=true) matched
      (property 'feature.audit.enabled' found with value 'true')

Negative matches:
  MetricsExportAutoConfiguration:
    - @ConditionalOnClass did not find required class
      'com.example.metrics.Exporter'
```

Đây là output giả lập để giải thích cách đọc, không phải log được lấy từ một ứng dụng cụ thể.

### 2.1. Report không phải danh sách toàn bộ object đang tồn tại

ConditionEvaluationReport trả lời câu hỏi về **quá trình đánh giá điều kiện cấu hình**. Nó không phải:

- Danh sách mọi bean instance hiện có.
- Dependency tree Maven hoặc Gradle.
- Log mọi lần gọi method trong ứng dụng.
- Báo cáo sức khỏe của database hoặc hệ thống bên ngoài.
- Công cụ theo dõi điều kiện thay đổi liên tục trong runtime.

Một bean có thể không tồn tại vì class chưa được component scan, configuration chưa được import, module chưa có trên classpath hoặc bean definition bị đăng ký theo cách khác. Không phải mọi nguyên nhân đều tương ứng với một dòng negative match trong report.

### 2.2. Report được tạo trong quá trình khởi động

Condition evaluation gắn với quá trình Spring xử lý configuration và đăng ký bean definitions. Report phản ánh những điều kiện được đánh giá trong quá trình đó. Nếu thay đổi property hoặc classpath, thông thường cần tạo context mới hoặc khởi động lại ứng dụng để điều kiện được đánh giá lại.

Đừng xem report như một dashboard cập nhật khi property thay đổi trong lúc ứng dụng đang chạy. Nó chủ yếu là công cụ chẩn đoán cấu hình tại startup.

## 3. Hiểu positive match và negative match

Khi đọc report, hai nhóm kết quả quan trọng nhất là **Positive matches** và **Negative matches**.

### 3.1. Positive match

Positive match cho biết condition hoặc configuration đã đáp ứng điều kiện tương ứng. Ví dụ:

```text
Positive matches:
  AuditConfiguration:
    - @ConditionalOnProperty (feature.audit.enabled=true) matched
```

Điều này cho biết property được đánh giá là phù hợp. Nếu configuration có phương thức `@Bean` và không có điều kiện khác ngăn cản, bean definition có thể được đăng ký.

Tuy nhiên, positive match của một condition **không bảo đảm toàn bộ ứng dụng đã khởi động thành công**. Một bean khác vẫn có thể thiếu dependency, constructor có thể thất bại hoặc một điều kiện tiếp theo có thể không khớp.

### 3.2. Negative match

Negative match cho biết một condition đã được đánh giá nhưng không đáp ứng điều kiện. Ví dụ:

```text
Negative matches:
  AuditConfiguration:
    - @ConditionalOnProperty (feature.audit.enabled=true)
      did not find property 'enabled'
```

Thông điệp giúp phân biệt các trường hợp:

- Property không tồn tại.
- Property có giá trị khác với giá trị yêu cầu.
- Class bắt buộc không có trên classpath.
- Một bean cần thiết chưa được đăng ký tại thời điểm condition được đánh giá.
- Ứng dụng không thuộc loại web mà configuration yêu cầu.

Không nên chỉ nhìn chữ “negative” rồi kết luận đây là lỗi. Nhiều negative match là hoàn toàn bình thường: cấu hình dành cho MongoDB không cần được bật khi ứng dụng chỉ dùng PostgreSQL, hoặc cấu hình web không cần xuất hiện trong một ứng dụng command-line.

### 3.3. Một configuration có thể có nhiều condition

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.audit.AuditClient")
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true"
)
class AuditAutoConfiguration {

    @Bean
    AuditService auditService() {
        return new AuditService();
    }
}
```

Để configuration được áp dụng, các điều kiện liên quan phải thỏa theo semantics của chúng. Nếu class có mặt nhưng property chưa bật, configuration vẫn không được kích hoạt. Nếu property bật nhưng class cần thiết không có, cấu hình cũng có thể không được áp dụng.

Khi đọc report, cần xem **toàn bộ các condition liên quan**, không dừng ở condition đầu tiên có chữ matched.

## 4. Cấu trúc thông tin thường gặp trong report

Một report có thể được biểu diễn theo các nhóm:

| Nhóm | Ý nghĩa |
| --- | --- |
| Positive matches | Các cấu hình/condition đã khớp |
| Negative matches | Các cấu hình/condition không khớp |
| Exclusions | Các auto-configuration đã bị loại trừ tường minh |
| Unconditional classes | Các cấu hình được ghi nhận không cần đánh giá condition theo cách thông thường |

Tên và cấu trúc hiển thị có thể khác đôi chút giữa log, endpoint Actuator và phiên bản Spring Boot. Khi phân tích, hãy tập trung vào source, condition và outcome message.

### 4.1. Source

Source thường là tên class cấu hình, bean method hoặc nguồn metadata mà condition được gắn vào. Ví dụ:

```text
com.example.audit.AuditAutoConfiguration
com.example.audit.AuditAutoConfiguration#auditService
```

Nếu condition nằm trên class, source có thể chỉ tới class. Nếu condition nằm trên phương thức `@Bean`, source có thể chỉ tới bean method. Điều này giúp xác định chính xác cấu hình nào bị ảnh hưởng.

### 4.2. Condition

Condition cho biết loại điều kiện đã được đánh giá, chẳng hạn:

- `OnClassCondition` cho các điều kiện classpath.
- `OnBeanCondition` cho điều kiện liên quan tới bean.
- `OnPropertyCondition` cho property.
- `OnWebApplicationCondition` cho loại ứng dụng web.

Tên condition là implementation nội bộ của Spring Boot cho annotation/contract điều kiện tương ứng. Người học Fundamentals nên ưu tiên đọc thông điệp và annotation gốc trong source trước khi tìm sâu vào class implementation.

### 4.3. Outcome message

Thông điệp là phần hữu ích nhất khi chẩn đoán. Nó thường cho biết điều kiện khớp hay không và chi tiết nào đã được tìm thấy hoặc thiếu.

Ví dụ:

```text
@ConditionalOnProperty (feature.audit.enabled=true) matched
(found property 'enabled' with value 'true')
```

hoặc:

```text
@ConditionalOnClass did not find required class
'com.example.audit.AuditClient'
```

Hãy dùng outcome message để xác định bước kiểm tra tiếp theo thay vì suy đoán từ tên cấu hình.

## 5. Bật ConditionEvaluationReport bằng debug mode

Một cách nhanh để xem report khi phát triển là bật debug mode của Spring Boot.

### 5.1. Dùng command line

Chạy ứng dụng với tham số:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
```

Hoặc chạy executable JAR:

```bash
java -jar target/app.jar --debug
```

Với Gradle:

```bash
./gradlew bootRun --args='--debug'
```

Trên Windows PowerShell, có thể dùng wrapper tương ứng:

```powershell
.\mvnw.cmd spring-boot:run -Dspring-boot.run.arguments=--debug
.\gradlew.bat bootRun --args='--debug'
```

Tham số `--debug` bật chế độ debug của Spring Boot để hiển thị condition evaluation report trong log startup theo cấu hình logging hiện tại. Nó không đồng nghĩa đặt toàn bộ ứng dụng ở mức TRACE.

### 5.2. Bật qua application.properties

Có thể cấu hình:

```properties
debug=true
```

Hoặc YAML:

```yaml
debug: true
```

Đây là cấu hình hữu ích trong môi trường phát triển hoặc khi điều tra startup. Không nên bật debug tùy tiện trong production nếu chưa xem xét lượng log và thông tin được ghi ra.

### 5.3. Report xuất hiện ở đâu?

Khi ứng dụng khởi động, tìm phần có tiêu đề tương tự:

```text
CONDITIONS EVALUATION REPORT
```

Trong report, tập trung vào source liên quan tới bean/configuration cần điều tra. Log có thể dài vì Spring Boot kiểm tra nhiều auto-configuration, nên hãy tìm tên class hoặc property liên quan trước.

### 5.4. Debug mode không sửa điều kiện

`--debug` chỉ hỗ trợ hiển thị thông tin chẩn đoán. Nó không tự:

- Bật property đang thiếu.
- Thêm class vào classpath.
- Đăng ký bean bị thiếu.
- Sửa cấu hình profile.
- Thay đổi thứ tự auto-configuration.

Nếu report cho thấy condition không khớp, cần sửa nguyên nhân ở cấu hình hoặc dependency phù hợp rồi khởi động lại.

## 6. Xem condition report qua Spring Boot Actuator

Nếu ứng dụng có Spring Boot Actuator, endpoint `conditions` có thể cung cấp thông tin condition evaluation dưới dạng dữ liệu HTTP.

### 6.1. Thêm Actuator dependency

Với Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Với Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
```

Dependency này cung cấp endpoint quản trị Actuator, nhưng không có nghĩa mọi endpoint đều tự được public qua HTTP.

### 6.2. Expose conditions endpoint

Ví dụ cấu hình:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
```

Sau khi ứng dụng khởi động với web server và Actuator phù hợp, endpoint thường được truy cập tại:

```text
GET /actuator/conditions
```

Nếu Actuator dùng base path khác hoặc management server chạy cổng riêng, URL thực tế sẽ thay đổi theo cấu hình.

### 6.3. Đọc dữ liệu endpoint

Response có thể có cấu trúc JSON gồm các phần:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "com.example.audit.AuditAutoConfiguration": [
          {
            "condition": "OnPropertyCondition",
            "message": "feature.audit.enabled matched"
          }
        ]
      },
      "negativeMatches": {
        "com.example.metrics.MetricsAutoConfiguration": [
          {
            "condition": "OnClassCondition",
            "message": "required class was not found"
          }
        ]
      },
      "exclusions": [],
      "unconditionalClasses": []
    }
  }
}
```

Đây là JSON giả lập rút gọn để minh họa ý nghĩa dữ liệu. Response thật chứa các source và message do ứng dụng cùng phiên bản Spring Boot tạo ra.

### 6.4. Bảo vệ endpoint conditions

Condition report có thể tiết lộ:

- Những thư viện nào có mặt trên classpath.
- Những tính năng nào đang được bật.
- Tên cấu hình nội bộ.
- Một số chi tiết về môi trường và dependency.

Vì vậy, không nên expose endpoint này cho mọi người dùng Internet. Trong môi trường production, cần kiểm soát exposure, authentication, authorization và network access theo chính sách vận hành. Chỉ expose endpoint khi có nhu cầu chẩn đoán được xác định rõ.

## 7. Ví dụ điều tra @ConditionalOnProperty

Xét cấu hình audit:

```java
package com.example.audit;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class AuditConfiguration {

    @Bean
    AuditService auditService() {
        return new AuditService();
    }
}
```

Giả sử `AuditService` là class có constructor phù hợp.

### 7.1. Trường hợp property bằng true

`application.yml`:

```yaml
feature:
  audit:
    enabled: true
```

Condition có thể khớp vì property tồn tại và giá trị đáp ứng `havingValue = "true"`. Report có thể ghi positive match cho `AuditConfiguration`.

### 7.2. Trường hợp property bằng false

```yaml
feature:
  audit:
    enabled: false
```

Condition không khớp vì giá trị thực tế không bằng `true`. Report ghi negative outcome và giải thích property không đáp ứng yêu cầu.

### 7.3. Trường hợp property bị thiếu

Nếu không khai báo `feature.audit.enabled`, với `matchIfMissing = false`, condition không khớp. Đây là hành vi mặc định phổ biến của `@ConditionalOnProperty` khi không có property, trừ khi chủ động đặt `matchIfMissing = true`.

### 7.4. Trường hợp có property nhưng khác cách viết

`@ConditionalOnProperty` so sánh giá trị theo quy tắc của annotation và property source. Nếu cấu hình dùng một chuỗi như `yes` trong khi condition yêu cầu `true`, không nên giả định nó luôn được xem là khớp. Hãy dùng giá trị boolean tường minh và nhất quán để tránh nhầm lẫn.

## 8. Ví dụ điều tra @ConditionalOnClass

Một auto-configuration chỉ nên được kích hoạt khi thư viện cần thiết có mặt:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.search.SearchClient")
class SearchConfiguration {

    @Bean
    SearchService searchService() {
        return new SearchService();
    }
}
```

Nếu `SearchClient` có mặt trên classpath, condition có thể khớp. Nếu class không tồn tại, cấu hình bị bỏ qua.

Report giúp phân biệt:

- Dependency chưa được khai báo hoặc không được resolve.
- Dependency có mặt nhưng cấu hình vẫn không được import/scan.
- Condition có class đã khớp nhưng một condition khác của cùng configuration không khớp.

Khi điều tra classpath, kết hợp report với dependency tree của Maven/Gradle. Condition report nói rằng class được tìm thấy hay không tại runtime; dependency tree giải thích thư viện nào đưa class đó vào.

### 8.1. Vì sao dùng thuộc tính name?

`@ConditionalOnClass` hỗ trợ khai báo class bằng `value` hoặc `name`. Dạng `name` là chuỗi tên class và hữu ích trong một số trường hợp cần tránh tham chiếu trực tiếp đến class tùy chọn khi configuration được nạp.

Trong auto-configuration dành cho thư viện tùy chọn, việc đặt condition trên configuration class phù hợp có thể tránh tải các kiểu không có mặt trên classpath. Với cấu hình phức tạp, cần xem hướng dẫn thiết kế auto-configuration của phiên bản Spring Boot đang dùng.

## 9. Ví dụ điều tra @ConditionalOnMissingBean

Một auto-configuration có thể cung cấp implementation mặc định nếu ứng dụng chưa tự khai báo:

```java
@Configuration(proxyBeanMethods = false)
class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
```

Nếu chưa có bean kiểu `GreetingService` tại thời điểm điều kiện được đánh giá, cấu hình mặc định có thể khớp. Nếu ứng dụng đã có bean phù hợp, condition không khớp và bean mặc định sẽ được bỏ qua.

Ví dụ ứng dụng tự cung cấp:

```java
@Configuration
class CustomGreetingConfiguration {

    @Bean
    GreetingService greetingService() {
        return new CustomGreetingService();
    }
}
```

Khi cả hai cấu hình được xử lý theo thứ tự phù hợp, `GreetingAutoConfiguration` có thể back off vì bean do ứng dụng cung cấp đã tồn tại.

### 9.1. Back-off là hành vi có chủ đích

Trong auto-configuration, `@ConditionalOnMissingBean` thường giúp người dùng thay thế mặc định. Negative match ở đây không nhất thiết là lỗi; nó có thể chứng minh ứng dụng đã cung cấp implementation riêng.

Report giúp trả lời:

- Auto-configuration mặc định đã được xem xét chưa?
- Bean nào đã khiến `@ConditionalOnMissingBean` không khớp?
- Cấu hình mặc định có bị bỏ qua đúng như mong đợi không?

### 9.2. Thời điểm đánh giá có ý nghĩa

`@ConditionalOnMissingBean` đánh giá những bean definitions mà Spring đã biết tại thời điểm condition chạy. Vì vậy, thứ tự xử lý configuration và auto-configuration có thể ảnh hưởng kết quả.

Trong auto-configuration, nên sử dụng thứ tự và cơ chế cấu hình được Spring Boot hỗ trợ. Không nên dựa vào thứ tự tình cờ của component scan để đảm bảo bean tùy chỉnh luôn được nhìn thấy trước.

## 10. Exclusions trong condition report

Một ứng dụng có thể loại trừ auto-configuration tường minh:

```java
@SpringBootApplication(
        exclude = DataSourceAutoConfiguration.class
)
public class ToolApplication {
    public static void main(String[] args) {
        SpringApplication.run(ToolApplication.class, args);
    }
}
```

Hoặc dùng property:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Report có thể ghi nhận các auto-configuration bị loại trừ trong phần exclusions.

Điều này khác với negative match:

| Trường hợp | Ý nghĩa |
| --- | --- |
| Negative match | Condition đã được đánh giá và không đáp ứng |
| Exclusion | Auto-configuration bị loại trừ tường minh theo cấu hình |
| Không xuất hiện trong report | Có thể chưa được phát hiện/đánh giá, hoặc không thuộc phạm vi report |

Nếu một auto-configuration bị exclude, đừng cố tìm một negative condition message như thể nó đã được đánh giá bình thường. Hãy kiểm tra cả danh sách exclusions và cấu hình `spring.autoconfigure.exclude` hoặc thuộc tính `exclude` trên annotation.

## 11. Unconditional classes có nghĩa gì?

Report có thể có nhóm `unconditionalClasses`. Nhóm này ghi nhận những configuration class không cần kết quả conditional match theo cách thông thường để được xử lý.

Không nên hiểu unconditional là:

- Tất cả bean bên trong chắc chắn được tạo thành công.
- Không có dependency nào cần thiết.
- Bean không chịu ảnh hưởng của các condition khác tại method hoặc cấu hình lồng nhau.

Nó chỉ mô tả cách class được xử lý ở tầng condition report. Bean vẫn có thể gặp lỗi khi tạo instance, thiếu dependency hoặc có điều kiện riêng tại method.

## 12. Đọc report theo một quy trình điều tra

Khi một bean không xuất hiện, hãy điều tra theo thứ tự:

### Bước 1: Xác định bean hoặc tính năng đang thiếu

Ghi lại:

- Tên bean hoặc type mong đợi.
- Configuration class hoặc auto-configuration dự kiến tạo bean.
- Property, dependency và profile liên quan.

Đừng bắt đầu bằng việc tìm một dòng bất kỳ trong report. Cần biết source nào có trách nhiệm đăng ký bean.

### Bước 2: Xác nhận configuration có được phát hiện không

Kiểm tra:

- Class có trên classpath không?
- Package có được component scan không?
- Configuration có được import không?
- Auto-configuration có được đăng ký đúng metadata không?
- Có bị loại trừ tường minh không?

Nếu class chưa từng được đưa vào quá trình xử lý configuration, report có thể không có negative match như mong đợi.

### Bước 3: Tìm source trong report

Tìm tên configuration hoặc bean method. Đọc toàn bộ các outcome liên quan thay vì chỉ xem dòng đầu tiên.

### Bước 4: Xác định condition không khớp

Ví dụ:

- Property bị thiếu hoặc sai giá trị.
- Classpath thiếu class.
- Bean cần thiết chưa tồn tại.
- Bean đã tồn tại khiến missing-bean condition back off.
- Ứng dụng không thuộc loại web phù hợp.
- Resource được yêu cầu không tìm thấy.

### Bước 5: Sửa ở đúng tầng

| Nguyên nhân | Nơi nên kiểm tra/sửa |
| --- | --- |
| Property sai hoặc thiếu | `application.yml`, environment variable, command-line args, profile |
| Class không có trên classpath | Maven/Gradle dependency và runtime packaging |
| Bean bắt buộc chưa đăng ký | Component scan, `@Import`, `@Bean`, auto-configuration |
| Missing-bean condition back off | Bean tùy chỉnh, type/qualifier, thứ tự cấu hình |
| Auto-configuration bị exclude | `exclude` trên annotation hoặc `spring.autoconfigure.exclude` |
| Sai loại ứng dụng web | Starter, application type và cấu hình web |

### Bước 6: Khởi động lại và đọc report mới

Điều kiện thường được đánh giá trong lúc xây dựng context. Sau khi thay đổi property hoặc dependency, tạo một lần khởi động mới để kiểm tra kết quả. So sánh source và outcome trước/sau sẽ cho thấy thay đổi đã tác động đúng chưa.

## 13. ConditionEvaluationReport và lỗi khởi động

Condition report rất hữu ích khi cấu hình bị bỏ qua, nhưng không phải mọi lỗi startup đều là condition mismatch.

Ví dụ:

- `NoSuchBeanDefinitionException` có thể xuất hiện vì configuration không được import, component scan sai hoặc một condition không khớp.
- `BeanCreationException` có thể xuất hiện sau khi condition đã khớp và bean definition được đăng ký, nhưng constructor hoặc initialization thất bại.
- Lỗi kết nối database có thể xảy ra khi bean datasource đã được đăng ký và bắt đầu khởi tạo.
- Lỗi class loading có thể xuất hiện khi một method hoặc constructor được thực thi, dù một số điều kiện classpath trước đó đã khớp.

Vì vậy, hãy kết hợp:

1. Condition evaluation report để hiểu cấu hình được chọn.
2. Stack trace để hiểu bean nào tạo thất bại và nguyên nhân gốc.
3. Dependency tree để hiểu thư viện runtime.
4. Property/profile đang active để xác minh nguồn cấu hình.

Không nên dùng report thay thế stack trace hoặc dùng một positive match làm bằng chứng rằng bean đã khởi tạo thành công.

## 14. Kiểm thử điều kiện bằng ApplicationContextRunner

Spring Boot cung cấp `ApplicationContextRunner` để kiểm thử auto-configuration trong một context nhỏ. Nó giúp kiểm tra condition khớp hoặc không khớp mà không phải khởi chạy toàn bộ web server.

Giả sử auto-configuration:

```java
package com.example.audit;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true"
)
public class AuditAutoConfiguration {

    @Bean
    AuditService auditService() {
        return new AuditService();
    }
}
```

Với một thư viện auto-configuration được đóng gói thành JAR, class cần được đăng ký trong file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

File này chứa tên đầy đủ của auto-configuration class, mỗi class trên một dòng. Trong test, `AutoConfigurations.of(...)` có thể nạp trực tiếp cấu hình mà không phụ thuộc vào việc tạo JAR starter hoàn chỉnh.

### 14.1. Test khi property được bật

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class AuditAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AuditAutoConfiguration.class)
                    );

    @Test
    void createsAuditServiceWhenEnabled() {
        contextRunner
                .withPropertyValues("feature.audit.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditService.class);
                });
    }
}
```

Khi property bằng true, condition khớp và bean được đăng ký. Test kiểm tra kết quả context.

### 14.2. Test khi property bị thiếu hoặc false

```java
@Test
void doesNotCreateAuditServiceWhenPropertyIsMissing() {
    contextRunner.run(context -> {
        assertThat(context).doesNotHaveBean(AuditService.class);
    });
}

@Test
void doesNotCreateAuditServiceWhenDisabled() {
    contextRunner
            .withPropertyValues("feature.audit.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(AuditService.class);
            });
}
```

Ba test tạo thành một ma trận đơn giản:

| Property | Kết quả mong đợi |
| --- | --- |
| Không có | Không đăng ký `AuditService` |
| `true` | Có một `AuditService` |
| `false` | Không đăng ký `AuditService` |

### 14.3. Kiểm thử back-off khi ứng dụng có bean riêng

Nếu auto-configuration dùng `@ConditionalOnMissingBean`, có thể cung cấp một bean thử nghiệm trước:

```java
@Test
void backsOffWhenApplicationProvidesAuditService() {
    contextRunner
            .withUserConfiguration(CustomAuditConfiguration.class)
            .withPropertyValues("feature.audit.enabled=true")
            .run(context -> {
                assertThat(context).hasSingleBean(AuditService.class);
                assertThat(context.getBean(AuditService.class))
                        .isInstanceOf(CustomAuditService.class);
            });
}
```

Ví dụ giả định `CustomAuditConfiguration` khai báo một `@Bean AuditService` trả về `CustomAuditService` và auto-configuration đã được bổ sung `@ConditionalOnMissingBean(AuditService.class)`. Mục tiêu là chứng minh cấu hình mặc định nhường chỗ cho bean do ứng dụng cung cấp.

### 14.4. Vì sao dùng ApplicationContextRunner?

Nó tạo context thử nghiệm có phạm vi nhỏ, cho phép:

- Thêm property values riêng cho từng test.
- Đưa configuration hoặc auto-configuration vào context.
- Thêm bean tùy chỉnh để kiểm tra back-off.
- Xác nhận bean có hoặc không có.
- Đóng context sau mỗi lần chạy.

Đây là cách kiểm chứng trực tiếp điều kiện cấu hình tốt hơn việc chỉ kiểm tra bằng mắt nội dung annotation.

## 15. Xem report bằng API trong mã nguồn

Trong những tình huống cần chẩn đoán sâu hơn, Spring Boot có class `ConditionEvaluationReport` trong package `org.springframework.boot.autoconfigure.condition`. Report được gắn với bean factory trong quá trình xử lý cấu hình.

Về mặt khái niệm, có thể truy xuất report từ một bean factory có hỗ trợ và xem các source/outcome đã được ghi nhận. Một đoạn minh họa ở mức API:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(beanFactory);

report.getConditionAndOutcomesBySource().forEach((source, outcomes) -> {
    System.out.println("Source: " + source);
    System.out.println("Full match: " + outcomes.isFullMatch());
    outcomes.forEach(conditionAndOutcome -> {
        System.out.println(
                conditionAndOutcome.getOutcome().getMessage()
        );
    });
});
```

Đây là ví dụ nâng cao phụ thuộc API của dòng Spring Boot cụ thể. Khi dùng trực tiếp trong project, cần import đúng class và kiểm tra chữ ký API trong phiên bản dependency đang dùng. Với phần lớn ứng dụng, debug log hoặc Actuator conditions endpoint là cách quan sát thuận tiện hơn.

Không nên xây logic nghiệp vụ dựa trên việc đọc condition report nội bộ. Report là công cụ chẩn đoán; quyết định bật/tắt tính năng nên được thể hiện qua configuration properties, conditional annotations hoặc cơ chế cấu hình công khai.

## 16. Những giới hạn cần hiểu khi đọc report

### 16.1. Không có source trong report chưa chứng minh condition khớp

Một cấu hình có thể không xuất hiện vì:

- Class chưa được scan/import hoặc không nằm trong danh sách auto-configuration.
- Auto-configuration bị exclude.
- Condition chưa được đánh giá do cấu hình không tham gia quá trình xử lý.
- Một cơ chế đăng ký khác đã cung cấp bean.
- Phiên bản hoặc cách hiển thị report có khác biệt.

Do đó, trước tiên xác nhận configuration có được phát hiện hay không.

### 16.2. Report không phải toàn bộ dependency graph

Nếu condition classpath không khớp, report có thể nói class không tìm thấy. Nó không nhất thiết nói dependency nào đáng lẽ phải cung cấp class đó. Hãy dùng Maven `dependency:tree` hoặc Gradle `dependencyInsight` để truy nguồn dependency.

### 16.3. Report không bảo đảm bean instance tạo thành công

Một configuration có thể match và đăng ký bean definition. Khi container tạo instance, constructor có thể thất bại vì thiếu dependency hoặc cấu hình không hợp lệ. Khi đó cần đọc stack trace và lỗi khởi tạo.

### 16.4. Kết quả phụ thuộc thời điểm đánh giá

Đặc biệt với `@ConditionalOnBean` và `@ConditionalOnMissingBean`, thứ tự xử lý configuration và bean definitions có ý nghĩa. Một bean được đăng ký quá muộn có thể không được nhìn thấy tại thời điểm condition được đánh giá.

### 16.5. Report là thông tin nhạy cảm ở một mức độ nhất định

Endpoint Actuator hoặc log report có thể tiết lộ cấu trúc thư viện và tính năng. Chỉ bật và chia sẻ ở phạm vi cần thiết, đặc biệt trong môi trường production.

## 17. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| Bean không xuất hiện, không thấy negative match tương ứng | Configuration chưa được phát hiện/import hoặc bị exclude | Kiểm tra component scan, `@Import`, auto-configuration metadata và exclusions |
| Property condition không khớp | Sai key, thiếu property, sai giá trị hoặc profile chưa active | Xem property source, profile và outcome message |
| Class condition không khớp | Class không có trong runtime classpath hoặc classloader không nhìn thấy | Kiểm tra dependency tree và artifact runtime |
| Missing-bean condition không khớp | Đã có bean cùng type/định danh phù hợp | Kiểm tra bean tùy chỉnh và source tạo bean |
| Positive match nhưng context vẫn fail | Bean definition đã đăng ký nhưng instance hoặc dependency tạo thất bại | Đọc stack trace, constructor và các dependency |
| Endpoint conditions trả 404 | Actuator chưa có, endpoint chưa expose hoặc base path khác | Kiểm tra dependency, exposure và management path |
| Endpoint trả 401/403 | Security policy chặn truy cập | Kiểm tra authentication/authorization cho management endpoint |
| Report quá dài | Nhiều auto-configuration được đánh giá | Tìm source liên quan và lọc log thay vì đọc tuần tự mọi dòng |

### 17.1. Không sửa bằng cách bật tất cả feature

Nếu report cho thấy một condition không khớp, đừng bật property hoặc thêm dependency một cách tùy tiện chỉ để biến negative match thành positive. Trước hết xác định cấu hình đó có thực sự cần trong ứng dụng không.

Ví dụ, một ứng dụng command-line không cần web server. Việc ép một auto-configuration web khớp có thể làm tăng dependency và thay đổi kiểu ứng dụng mà không đem lại giá trị.

## 18. Quy trình thực hành từ đầu đến cuối

Giả sử team báo rằng bean `AuditService` không được tạo sau khi deploy:

1. **Xác định cấu hình:** tìm `AuditConfiguration` hoặc `AuditAutoConfiguration` chịu trách nhiệm tạo bean.
2. **Kiểm tra property:** xác nhận `feature.audit.enabled` có giá trị nào trong môi trường deploy, profile nào đang active và property đến từ nguồn nào.
3. **Bật report:** chạy với `--debug` trong môi trường chẩn đoán hoặc sử dụng Actuator conditions endpoint đã được bảo vệ.
4. **Tìm source:** đọc positive/negative outcomes của cấu hình audit.
5. **Đối chiếu dependency:** nếu classpath condition không khớp, xem runtime dependency tree và artifact đóng gói.
6. **Kiểm tra bean tùy chỉnh:** nếu missing-bean condition back off, xác định bean nào đã được cung cấp và có đúng type không.
7. **Sửa đúng nguyên nhân:** cập nhật property, dependency, import hoặc cấu hình bean theo yêu cầu.
8. **Khởi động lại và xác nhận:** xem report mới, kiểm tra bean xuất hiện và kiểm thử luồng audit thực tế.

Khi báo cáo cho nhóm, nên ghi rõ:

```text
Configuration source:
Condition:
Expected value/state:
Observed value/state:
Report outcome:
Root cause:
Change made:
Verification:
```

Mẫu này giúp phân biệt bằng chứng, nguyên nhân và hành động sửa, thay vì chỉ nói “Spring không tạo bean”.

## 19. Bài tập thực hành

### Bài tập 1 – Đọc property condition

Tạo `AuditConfiguration` với:

```java
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
```

Khởi động ba lần với property lần lượt không có, `false` và `true`. Bật `--debug`, tìm source audit và ghi lại outcome của mỗi lần.

### Bài tập 2 – Đọc classpath condition

Tạo cấu hình có `@ConditionalOnClass(name = "com.example.search.SearchClient")`. Chạy project khi dependency cung cấp class có mặt và khi bỏ dependency đó. So sánh report với dependency tree.

### Bài tập 3 – Kiểm tra back-off

Tạo auto-configuration dùng `@ConditionalOnMissingBean`. Chạy một lần không có bean tùy chỉnh và một lần có bean do ứng dụng khai báo. Xem report giải thích vì sao cấu hình mặc định match hoặc back off.

### Bài tập 4 – Phân biệt exclusion và negative match

Loại một auto-configuration bằng `spring.autoconfigure.exclude`. Quan sát phần exclusions và so sánh với một cấu hình được đánh giá nhưng không thỏa condition.

### Bài tập 5 – Kiểm tra qua Actuator

Thêm `spring-boot-starter-actuator`, expose `conditions` trong môi trường local và gọi `GET /actuator/conditions`. Tìm source cấu hình cần điều tra trong JSON. Sau đó bỏ exposure hoặc bảo vệ endpoint theo yêu cầu môi trường.

### Bài tập 6 – Viết ApplicationContextRunner test

Viết ba test cho property condition:

- Property thiếu: bean không tồn tại.
- Property false: bean không tồn tại.
- Property true: bean tồn tại.

Thêm một test cung cấp bean tùy chỉnh để xác nhận auto-configuration mặc định back off khi có `@ConditionalOnMissingBean`.

## 20. Những điều cần nhớ

`ConditionEvaluationReport` giúp giải thích **vì sao các điều kiện cấu hình được đánh giá là khớp hoặc không khớp** trong quá trình khởi tạo Spring context. Đây là công cụ chẩn đoán quan trọng khi một auto-configuration hoặc bean có điều kiện không xuất hiện như mong đợi.

Hãy nhớ:

- Positive match cho biết condition đáp ứng; negative match cho biết condition đã được đánh giá nhưng không đáp ứng.
- Negative match không mặc nhiên là lỗi. Một số cấu hình không cần thiết trong ứng dụng hiện tại.
- Report thường ghi source, condition và outcome message; exclusions và unconditional classes là các nhóm thông tin bổ sung.
- `--debug` hoặc `debug=true` giúp hiển thị condition evaluation report trong log startup.
- Actuator endpoint `/actuator/conditions` cung cấp dữ liệu qua HTTP khi Actuator có mặt và endpoint được expose.
- `@ConditionalOnProperty`, `@ConditionalOnClass`, `@ConditionalOnBean` và `@ConditionalOnMissingBean` giải quyết các loại điều kiện khác nhau.
- Một positive match không bảo đảm bean instance khởi tạo thành công; vẫn cần đọc stack trace khi context fail.
- Nếu source không xuất hiện, kiểm tra component scan, import, auto-configuration metadata và exclusions trước khi kết luận.
- Dùng `ApplicationContextRunner` để kiểm thử có kiểm soát cả trường hợp condition khớp, không khớp và cấu hình mặc định back off.

Khi điều tra bean không xuất hiện, hãy lần theo chuỗi **configuration được phát hiện → condition được đánh giá → outcome được ghi nhận → bean definition được đăng ký hoặc bỏ qua → bean instance được tạo**. ConditionEvaluationReport giúp nhìn thấy phần quyết định theo điều kiện; kết hợp nó với dependency tree, property đang active và stack trace sẽ giúp xác định đúng nguyên nhân.
