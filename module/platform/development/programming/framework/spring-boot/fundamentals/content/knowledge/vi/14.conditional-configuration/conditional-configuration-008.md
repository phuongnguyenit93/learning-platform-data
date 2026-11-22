# @ConditionalOnResource và điều kiện tài nguyên

Một ứng dụng Spring Boot đôi khi chỉ nên đăng ký một phần cấu hình khi một file hoặc tài nguyên cần thiết có mặt. Ví dụ, module báo cáo có thể chỉ hoạt động khi file mẫu `templates/report.html` được đóng gói trong ứng dụng; một adapter đọc schema chỉ nên được tạo khi file schema tồn tại; hoặc một cấu hình mặc định chỉ phù hợp khi có một resource đi kèm thư viện.

Spring Boot cung cấp annotation **`@ConditionalOnResource`** để biểu đạt điều kiện này. Khi các resource được chỉ định tồn tại theo cơ chế phân giải tài nguyên của Spring, điều kiện khớp và cấu hình hoặc bean được phép đăng ký. Nếu resource không tồn tại, phần cấu hình được đánh dấu sẽ không được áp dụng.

Annotation này giúp cấu hình bean theo sự hiện diện của tài nguyên. Nó không đọc và kiểm tra nội dung file, không xác nhận định dạng file hợp lệ và không tự theo dõi thay đổi của file sau khi application context đã khởi động.

Bài học trình bày cách khai báo điều kiện tài nguyên trên class cấu hình và phương thức `@Bean`, cách dùng resource location như `classpath:` và `file:`, tác động khi có nhiều resource, cách kiểm thử hai nhánh điều kiện và những lỗi thường gặp.

## 1. Điều kiện tài nguyên là gì?

Trong Spring, **resource** là một cách trừu tượng hóa tài nguyên mà ứng dụng có thể đọc, chẳng hạn:

- File được đóng gói trong classpath.
- File bên ngoài ứng dụng trên filesystem.
- Một resource được truy cập thông qua URL hoặc cơ chế ResourceLoader phù hợp.
- Tài nguyên được cung cấp bởi một thư viện hoặc module khác.

Ví dụ, dự án có file:

~~~text
src/main/resources/
└── templates/
    └── report.html
~~~

Sau khi build, resource này thường được đưa vào classpath của ứng dụng với đường dẫn:

~~~text
templates/report.html
~~~

Nếu cấu hình chỉ nên được bật khi file đó có mặt, ta có thể dùng:

~~~java
@ConditionalOnResource(resources = "classpath:templates/report.html")
~~~

`@ConditionalOnResource` là annotation thuộc Spring Boot, trong package:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnResource;
~~~

Annotation này được xây dựng trên cơ chế condition của Spring. Nó kiểm tra sự tồn tại của các resource location được khai báo thông qua `ResourceLoader` trong quá trình đánh giá cấu hình.

### 1.1. Khi nào điều kiện khớp?

Giả sử cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:templates/report.html")
public class ReportTemplateConfiguration {
    // Các bean chỉ được đăng ký khi resource tồn tại.
}
~~~

Hai tình huống:

| Trạng thái resource | Kết quả điều kiện |
| --- | --- |
| `templates/report.html` có trên classpath | Điều kiện khớp; Spring xử lý cấu hình |
| Resource không tìm thấy | Điều kiện không khớp; cấu hình được đánh dấu không được áp dụng |

Điều kiện được đánh giá trong quá trình Spring xử lý cấu hình và đăng ký bean definition. Nó không phải câu lệnh chạy mỗi lần một method nghiệp vụ được gọi.

Nếu resource xuất hiện sau khi context đã khởi động, Spring không tự động đăng ký lại bean chỉ vì file vừa được tạo. Muốn đánh giá lại điều kiện, cần một vòng đời context phù hợp, thường là khởi động hoặc refresh context mới.

### 1.2. Annotation này thuộc Spring Boot

`@ConditionalOnResource` nằm trong `spring-boot-autoconfigure`, package `org.springframework.boot.autoconfigure.condition`. Nó không phải annotation core của Spring Framework như `@Conditional`.

Trong ứng dụng Spring Boot thông thường, các starter và cấu hình Boot đưa `spring-boot-autoconfigure` vào dependency graph. Nếu sử dụng Spring Framework thuần mà không có module Spring Boot Autoconfigure, không thể import annotation này chỉ từ `spring-context`.

## 2. Đặt @ConditionalOnResource trên class cấu hình

Cách dùng phổ biến là đặt annotation trên một class `@Configuration`.

Giả sử module báo cáo chỉ hoạt động khi có file mẫu:

~~~text
src/main/resources/
└── templates/
    └── report.html
~~~

Tạo class cấu hình:

~~~java
package com.example.report;

import org.springframework.boot.autoconfigure.condition.ConditionalOnResource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:templates/report.html")
public class ReportTemplateConfiguration {

    @Bean
    public Resource reportTemplate(ResourceLoader resourceLoader) {
        return resourceLoader.getResource("classpath:templates/report.html");
    }

    @Bean
    public ReportService reportService(Resource reportTemplate) {
        return new ReportService(reportTemplate);
    }
}
~~~

`ReportService` là class ứng dụng nhận resource qua constructor:

~~~java
package com.example.report;

import org.springframework.core.io.Resource;

public class ReportService {
    private final Resource reportTemplate;

    public ReportService(Resource reportTemplate) {
        this.reportTemplate = reportTemplate;
    }

    public boolean hasTemplate() {
        return reportTemplate.exists();
    }
}
~~~

Khi `templates/report.html` có mặt:

1. Spring đánh giá điều kiện trên `ReportTemplateConfiguration`.
2. `ResourceLoader` xác định resource tồn tại.
3. Cấu hình được xử lý.
4. Hai bean definition `reportTemplate` và `reportService` được đăng ký.
5. Khi cần tạo `ReportService`, Spring cung cấp bean `Resource` qua constructor.

Khi file không tồn tại, cấu hình không khớp và cả hai bean method trong class cấu hình này không được đăng ký từ cấu hình đó.

Đặt condition trên toàn class hữu ích khi **một nhóm bean cùng phụ thuộc vào một tài nguyên**. Nó giúp tránh tình trạng một bean bị bỏ qua nhưng bean khác vẫn được đăng ký và yêu cầu dependency không tồn tại.

## 3. Đặt @ConditionalOnResource trên một phương thức @Bean

Nếu chỉ một bean cần resource, có thể đặt condition trực tiếp trên factory method.

~~~java
package com.example.report;

import org.springframework.boot.autoconfigure.condition.ConditionalOnResource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

@Configuration(proxyBeanMethods = false)
public class OptionalReportConfiguration {

    @Bean
    @ConditionalOnResource(resources = "classpath:templates/optional-report.html")
    public Resource optionalReportTemplate(ResourceLoader resourceLoader) {
        return resourceLoader.getResource(
                "classpath:templates/optional-report.html"
        );
    }
}
~~~

Trong trường hợp này:

- Class cấu hình vẫn được xử lý.
- Bean definition `optionalReportTemplate` chỉ được đăng ký khi resource tồn tại.
- Những bean method khác trong class không chịu điều kiện này, trừ khi chúng có condition riêng hoặc class chứa chúng cũng được đánh dấu condition.

Điều này phù hợp khi một class cấu hình cung cấp nhiều bean độc lập, chỉ một bean trong số đó cần file tùy chọn.

### 3.1. Cẩn thận với dependency bắt buộc tới bean có điều kiện

Giả sử có service được component scan độc lập:

~~~java
@Service
public class ReportService {
    public ReportService(Resource optionalReportTemplate) {
        // ...
    }
}
~~~

Nếu `optionalReportTemplate` không được đăng ký vì file không tồn tại, `ReportService` vẫn được scan và vẫn yêu cầu `Resource` trong constructor. Context có thể thất bại do không tìm thấy bean phù hợp.

Đây là lỗi thiết kế thường gặp: **bean bị điều kiện loại bỏ nhưng consumer của nó vẫn luôn được đăng ký**.

Có một số cách xử lý tùy ý nghĩa ứng dụng:

- Đặt condition trên cả cấu hình/service cần resource.
- Dùng `ObjectProvider<Resource>` nếu dependency thực sự tùy chọn và consumer có logic xử lý khi không có bean.
- Dùng một implementation mặc định khác nếu nghiệp vụ cho phép.
- Dùng `@ConditionalOnMissingBean` hoặc condition khác để cấu hình fallback thích hợp.

Ví dụ dùng `ObjectProvider`:

~~~java
@Service
public class ReportService {
    private final ObjectProvider<Resource> templateProvider;

    public ReportService(ObjectProvider<Resource> templateProvider) {
        this.templateProvider = templateProvider;
    }

    public boolean hasTemplate() {
        Resource resource = templateProvider.getIfAvailable();
        return resource != null && resource.exists();
    }
}
~~~

Đoạn này minh họa cách truy xuất bean tùy chọn; nếu ứng dụng có nhiều bean `Resource` không liên quan, cần qualifier hoặc một abstraction riêng để chọn đúng template.

Không nên inject `Resource` chung chung trong một ứng dụng có nhiều loại resource. Tạo kiểu riêng như `ReportTemplate` hoặc qualifier tường minh thường rõ ràng hơn.

## 4. Resource location và các prefix thường dùng

`@ConditionalOnResource` nhận các chuỗi resource location. Việc phân giải resource sử dụng `ResourceLoader` của Spring, vì vậy nên ghi rõ prefix để người đọc biết ứng dụng đang kiểm tra nguồn nào.

### 4.1. classpath:

Dùng cho resource được đóng gói trong classpath:

~~~java
@ConditionalOnResource(resources = "classpath:templates/report.html")
~~~

Ví dụ vị trí source:

~~~text
src/main/resources/templates/report.html
~~~

Sau khi build, file thường nằm trong classpath tại `templates/report.html`, dù nó có thể nằm bên trong executable JAR chứ không phải một file rời trên filesystem.

Một số ví dụ khác:

~~~java
@ConditionalOnResource(resources = "classpath:config/defaults.yml")
@ConditionalOnResource(resources = "classpath:schemas/order-v1.json")
@ConditionalOnResource(resources = "classpath:messages/errors.properties")
~~~

`classpath:` đặc biệt hữu ích khi resource là một phần của ứng dụng hoặc thư viện.

### 4.2. file:

Dùng khi cần kiểm tra một file trên filesystem:

~~~java
@ConditionalOnResource(resources = "file:/opt/myapp/config/report-template.html")
~~~

Ví dụ này giả định môi trường triển khai có file ở đường dẫn tương ứng. Đường dẫn thực tế phụ thuộc hệ điều hành và cách triển khai.

Với file bên ngoài, cần nhớ:

- File có thể tồn tại trên máy lập trình nhưng không tồn tại trong container hoặc máy production.
- Đường dẫn tương đối phụ thuộc working directory của tiến trình và cách ResourceLoader diễn giải location.
- Nên cấu hình đường dẫn theo môi trường thay vì hard-code một đường dẫn chỉ đúng trên máy cá nhân.
- Việc resource có mặt tại thời điểm khởi động không bảo đảm file luôn còn đó trong suốt thời gian ứng dụng chạy.

Nếu resource location cần thay đổi theo môi trường hoặc cấu hình, hãy xem xét dùng property và một cơ chế condition phù hợp; `@ConditionalOnResource` nhận resource location được khai báo trong annotation.

### 4.3. URL resource

Spring Resource abstraction có thể hỗ trợ các URL prefix tùy `ResourceLoader` được sử dụng. Ví dụ, một URL có thể được biểu diễn như:

~~~java
@ConditionalOnResource(resources = "https://example.invalid/config/report.json")
~~~

Tuy nhiên, không nên mặc định dùng URL mạng làm điều kiện khởi động ứng dụng. Việc kiểm tra tồn tại một resource từ xa có thể phụ thuộc mạng, DNS, quyền truy cập, timeout và hành vi của resource implementation. Một dịch vụ ngoài tạm thời không truy cập được có thể làm thay đổi kết quả startup.

Với cấu hình production, thường nên đóng gói resource trong classpath hoặc kiểm tra file local được quản lý rõ ràng. Nếu cần kiểm tra một dịch vụ từ xa đang khỏe mạnh, hãy dùng cơ chế health check/availability phù hợp thay vì dùng điều kiện resource như một phép kiểm tra kết nối tổng quát.

### 4.4. Không prefix và cách phân giải mặc định

Spring `ResourceLoader` có quy tắc riêng khi location không có prefix. Với implementation mặc định phổ biến, location không prefix được xem như classpath resource. Tuy nhiên, để cấu hình rõ ràng và dễ di chuyển, nên viết `classpath:` hoặc `file:` thay vì dựa vào cách hiểu ngầm.

## 5. Khi khai báo nhiều resources thì điều kiện hoạt động ra sao?

Thuộc tính `resources` nhận một mảng chuỗi:

~~~java
@Configuration
@ConditionalOnResource(resources = {
        "classpath:schemas/order.json",
        "classpath:schemas/customer.json"
})
public class SchemaConfiguration {
    // ...
}
~~~

Trong cấu hình này, các resource được liệt kê là những tài nguyên cần có. Điều kiện chỉ khớp khi **tất cả resource được chỉ định đều tồn tại**.

| order.json | customer.json | Kết quả |
| --- | --- | --- |
| Có | Có | Khớp |
| Có | Không | Không khớp |
| Không | Có | Không khớp |
| Không | Không | Không khớp |

Nếu yêu cầu là “chỉ cần một trong nhiều file tồn tại”, `@ConditionalOnResource` không diễn đạt trực tiếp phép OR đó bằng cách liệt kê nhiều phần tử trong cùng annotation. Có thể tạo các cấu hình condition riêng hoặc viết custom condition thể hiện phép OR theo nhu cầu.

Ví dụ tách hai cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:templates/pdf-report.html")
class PdfReportConfiguration {
    // Bean của PDF report.
}

@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:templates/csv-report.html")
class CsvReportConfiguration {
    // Bean của CSV report.
}
~~~

Mỗi cấu hình được đánh giá độc lập. Nếu một file có mặt, cấu hình tương ứng có thể được áp dụng.

## 6. Điều kiện được đánh giá vào thời điểm nào?

`@ConditionalOnResource` là một condition trong quá trình xử lý cấu hình của Spring. Nó được đánh giá khi container đang phân tích cấu hình và quyết định bean definition nào được đăng ký.

Chu trình khái quát:

~~~text
SpringApplication khởi động
          │
          ▼
Chuẩn bị ApplicationContext
          │
          ▼
Đọc cấu hình và metadata
          │
          ▼
Gặp @ConditionalOnResource
          │
          ▼
ResourceLoader kiểm tra resource location
          │
      ┌───┴────┐
      ▼        ▼
   Tồn tại   Không tồn tại
      │        │
      ▼        ▼
 Condition   Condition
  khớp      không khớp
      │        │
      ▼        ▼
Đăng ký     Bỏ qua phần
bean        cấu hình/bean
definition  được đánh dấu
~~~

Điều kiện không chạy lại trên mỗi HTTP request và cũng không tự đăng ký bean khi file xuất hiện sau startup.

Nếu resource được tạo hoặc xóa khi ứng dụng đang chạy, các bean đã đăng ký không tự thay đổi theo. Muốn cấu hình phản ánh trạng thái mới, cần một chiến lược refresh/restart context hoặc một thiết kế đọc resource động ở runtime.

### 6.1. Phân biệt điều kiện startup và kiểm tra runtime

Hai yêu cầu sau khác nhau:

**Yêu cầu A:** “Chỉ đăng ký `ReportService` nếu file mẫu đã có lúc ứng dụng khởi động.”

`@ConditionalOnResource` phù hợp.

**Yêu cầu B:** “Mỗi lần tạo báo cáo, kiểm tra file hiện vẫn tồn tại; nếu bị xóa thì xử lý lỗi.”

Đây là logic runtime. Service cần kiểm tra `Resource.exists()` hoặc xử lý lỗi khi đọc file ở thời điểm sử dụng. `@ConditionalOnResource` không đảm bảo file vẫn tồn tại sau startup.

Không dùng condition startup để thay thế kiểm tra lỗi khi truy cập tài nguyên thực tế.

## 7. @ConditionalOnResource chỉ kiểm tra tồn tại, không xác thực nội dung

Giả sử file `classpath:schemas/order.json` có mặt nhưng chứa JSON sai cú pháp.

~~~json
{
  "orderId":
~~~

Điều kiện tài nguyên vẫn có thể khớp vì resource tồn tại. `@ConditionalOnResource` không parse JSON để xác nhận nội dung hợp lệ.

Tương tự, annotation không bảo đảm:

- File có thể đọc thành công bằng user chạy ứng dụng.
- Nội dung file đúng schema hoặc đúng phiên bản.
- File có dữ liệu không rỗng.
- File có đủ quyền truy cập cần thiết.
- Resource không bị xóa hoặc thay đổi sau khi condition đã được đánh giá.
- Hệ thống bên ngoài liên quan đến file đang hoạt động.

Nếu cần xác thực nội dung, hãy thực hiện ở bước phù hợp:

- Dùng parser để đọc và kiểm tra định dạng.
- Dùng Bean Validation hoặc schema validation.
- Kiểm tra quyền truy cập và xử lý `IOException`.
- Đưa kiểm tra bắt buộc vào startup logic nếu ứng dụng không thể chạy khi cấu hình sai.
- Dùng health indicator cho trạng thái runtime cần quan sát.

`@ConditionalOnResource` chỉ trả lời một câu hỏi hẹp: **resource location được chỉ định có hiện diện theo ResourceLoader hay không?**

## 8. So sánh với các condition khác của Spring Boot

Spring Boot có nhiều annotation condition. Chọn đúng loại giúp cấu hình diễn đạt chính xác điều kiện cần.

| Annotation | Điều kiện chính | Ví dụ |
| --- | --- | --- |
| `@ConditionalOnResource` | Resource location tồn tại | `classpath:templates/report.html` |
| `@ConditionalOnClass` | Một class có trên classpath | `com.fasterxml.jackson.databind.ObjectMapper` |
| `@ConditionalOnMissingClass` | Một class không có trên classpath | Tùy chọn thư viện chưa được cài |
| `@ConditionalOnProperty` | Property có giá trị hoặc trạng thái phù hợp | `report.enabled=true` |
| `@ConditionalOnBean` | Bean phù hợp đã được đăng ký | `DataSource` |
| `@ConditionalOnMissingBean` | Chưa có bean phù hợp | Cung cấp implementation mặc định |
| `@ConditionalOnWebApplication` | Ứng dụng thuộc loại web phù hợp | Cấu hình web server |

Ví dụ:

### 8.1. Resource tồn tại

~~~java
@Configuration
@ConditionalOnResource(resources = "classpath:reports/template.html")
class ReportConfiguration {
}
~~~

Câu hỏi: file mẫu có mặt không?

### 8.2. Property bật tính năng

~~~java
@Configuration
@ConditionalOnProperty(
        prefix = "reports",
        name = "enabled",
        havingValue = "true"
)
class ReportFeatureConfiguration {
}
~~~

Câu hỏi: cấu hình `reports.enabled` có bật tính năng không?

### 8.3. Class có trên classpath

~~~java
@Configuration
@ConditionalOnClass(name = "com.example.pdf.PdfRenderer")
class PdfIntegrationConfiguration {
}
~~~

Câu hỏi: thư viện có cung cấp class cần thiết không?

### 8.4. Bean đã được đăng ký

~~~java
@Configuration
@ConditionalOnBean(DataSource.class)
class DatabaseReportConfiguration {
}
~~~

Câu hỏi: container có bean `DataSource` phù hợp không?

Các điều kiện có thể kết hợp nếu cấu hình cần nhiều điều kiện:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.pdf.PdfRenderer")
@ConditionalOnResource(resources = "classpath:reports/pdf-template.html")
@ConditionalOnProperty(
        prefix = "reports.pdf",
        name = "enabled",
        havingValue = "true"
)
class PdfReportConfiguration {
    // Chỉ áp dụng khi các điều kiện được khai báo đều khớp.
}
~~~

Khi kết hợp nhiều condition trên cùng một cấu hình, chúng tạo thành yêu cầu AND: từng điều kiện phải khớp để cấu hình được áp dụng.

## 9. Ví dụ thực tế: bật tính năng dựa trên file mẫu

Giả sử ứng dụng chỉ cung cấp chức năng tạo thư mời nếu file HTML mẫu được đóng gói.

Cấu trúc:

~~~text
src/main/
├── java/com/example/invitation/
│   ├── InvitationApplication.java
│   ├── InvitationService.java
│   └── InvitationTemplateConfiguration.java
└── resources/
    └── templates/
        └── invitation.html
~~~

File `invitation.html`:

~~~html
<!doctype html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Thư mời</title>
</head>
<body>
    <h1>Xin chào!</h1>
    <p>Bạn được mời tham gia sự kiện.</p>
</body>
</html>
~~~

Cấu hình:

~~~java
package com.example.invitation;

import org.springframework.boot.autoconfigure.condition.ConditionalOnResource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:templates/invitation.html")
public class InvitationTemplateConfiguration {

    @Bean
    public Resource invitationTemplate(ResourceLoader resourceLoader) {
        return resourceLoader.getResource(
                "classpath:templates/invitation.html"
        );
    }

    @Bean
    public InvitationService invitationService(Resource invitationTemplate) {
        return new InvitationService(invitationTemplate);
    }
}
~~~

Service:

~~~java
package com.example.invitation;

import org.springframework.core.io.Resource;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class InvitationService {
    private final Resource template;

    public InvitationService(Resource template) {
        this.template = template;
    }

    public String loadTemplate() throws IOException {
        try (var inputStream = template.getInputStream()) {
            return new String(
                    inputStream.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
~~~

Nếu file có mặt trong `src/main/resources`, cấu hình có thể được áp dụng và service được tạo. Nếu file không được đóng gói, cấu hình không khớp; cả `Resource` bean lẫn `InvitationService` trong class cấu hình đó đều không được đăng ký.

Ví dụ này đọc nội dung file lúc method `loadTemplate()` được gọi. Condition chỉ kiểm tra sự hiện diện khi startup; nếu resource bị mất sau đó, thao tác đọc vẫn có thể ném `IOException`.

## 10. Cấu hình file bên ngoài ứng dụng

Không phải resource nào cũng nên được đóng gói trong JAR. Một số ứng dụng cho phép triển khai file mẫu hoặc schema bên ngoài để cập nhật mà không build lại artifact.

Ví dụ file:

~~~text
/opt/invitation/config/invitation.html
~~~

Condition:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(
        resources = "file:/opt/invitation/config/invitation.html"
)
public class ExternalInvitationConfiguration {
    // ...
}
~~~

Nếu file tồn tại tại thời điểm condition được đánh giá, cấu hình có thể được đăng ký.

Tuy nhiên, hard-code đường dẫn như trên làm cấu hình gắn với một môi trường cụ thể. Nếu đường dẫn thay đổi theo deployment, có thể cần custom condition hoặc một cơ chế cấu hình khác để đưa giá trị property vào quyết định.

Một lưu ý quan trọng: annotation `@ConditionalOnResource` nhận resource location cố định trong metadata. Nó không cung cấp thuộc tính placeholder tùy ý để thay thế như một giá trị cấu hình runtime trong mọi trường hợp. Nếu yêu cầu là “đường dẫn lấy từ `app.template-location`”, có thể dùng một custom `Condition` đọc `Environment`, hoặc dùng `@ConditionalOnProperty` để điều khiển cấu hình rồi để bean đọc property và kiểm tra resource.

Ví dụ kết hợp property:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "invitation",
        name = "template-enabled",
        havingValue = "true"
)
public class InvitationFeatureConfiguration {

    @Bean
    public InvitationService invitationService(
            Environment environment,
            ResourceLoader resourceLoader) {

        String location = environment.getRequiredProperty(
                "invitation.template-location"
        );

        Resource resource = resourceLoader.getResource(location);
        if (!resource.exists()) {
            throw new IllegalStateException(
                    "Invitation template does not exist: " + location
            );
        }

        return new InvitationService(resource);
    }
}
~~~

Cấu hình:

~~~properties
invitation.template-enabled=true
invitation.template-location=file:/opt/invitation/config/invitation.html
~~~

Ở ví dụ này, `@ConditionalOnProperty` quyết định có bật feature hay không; factory method đọc đường dẫn cấu hình, kiểm tra resource và tạo service. Nếu resource bắt buộc mà không có, ứng dụng báo lỗi rõ ràng trong lúc tạo bean.

Nếu chỉ cần condition theo một đường dẫn cố định, `@ConditionalOnResource` ngắn gọn hơn. Nếu đường dẫn là property động, cần thiết kế một cách đọc property phù hợp.

## 11. Kiểm thử cả trường hợp resource có và không có

Vì condition được đánh giá trong quá trình tạo context, có thể viết integration test dùng những resource test riêng.

Ví dụ test resource:

~~~text
src/test/resources/
└── conditional/
    └── feature-present.txt
~~~

Cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:conditional/feature-present.txt")
class ConditionalFeatureConfiguration {

    @Bean
    FeatureService featureService() {
        return new FeatureService();
    }
}
~~~

Test context khi resource có mặt:

~~~java
class ConditionalFeatureConfigurationTest {

    @Test
    void registersBeanWhenResourceExists() {
        try (var context = new AnnotationConfigApplicationContext(
                ConditionalFeatureConfiguration.class)) {

            assertTrue(context.containsBean("featureService"));
        }
    }
}
~~~

Để kiểm tra nhánh không có resource, dùng một location không tồn tại:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:conditional/missing.txt")
class MissingResourceConfiguration {

    @Bean
    FeatureService featureService() {
        return new FeatureService();
    }
}
~~~

Test:

~~~java
@Test
void skipsBeanWhenResourceIsMissing() {
    try (var context = new AnnotationConfigApplicationContext(
            MissingResourceConfiguration.class)) {

        assertFalse(context.containsBean("featureService"));
    }
}
~~~

Các đoạn test cần import JUnit 5 và Spring Context; `FeatureService` là class đơn giản được định nghĩa trong test hoặc source phù hợp.

### 11.1. Vì sao dùng src/test/resources?

Resource trong `src/test/resources` thường được đưa vào test classpath, nên test có thể xác nhận condition với file mẫu mà không cần đặt resource đó trong artifact production.

Nhưng điều này cũng tạo ra một điểm cần chú ý: test pass vì file có trên test classpath không chứng minh file đã được đóng gói trong executable JAR production. Nếu resource là bắt buộc khi chạy thật, cần bảo đảm nó nằm ở `src/main/resources` hoặc được cung cấp đúng tại môi trường triển khai.

### 11.2. Kiểm tra bean definition thay vì chỉ gọi method

Mục tiêu của `@ConditionalOnResource` là điều khiển việc đăng ký cấu hình/bean. Vì vậy test nên xác nhận bean có hoặc không có trong context, thay vì chỉ gọi factory method bằng Java thuần.

Một lời gọi trực tiếp:

~~~java
new ConditionalFeatureConfiguration().featureService();
~~~

không đi qua quá trình condition evaluation của Spring. Nó không kiểm tra hành vi của `@ConditionalOnResource`.

## 12. Quan sát condition evaluation trong Spring Boot

Khi cấu hình không được áp dụng, có thể bật chế độ debug để xem báo cáo điều kiện auto-configuration:

~~~bash
java -jar application.jar --debug
~~~

Hoặc trong môi trường phát triển, bật debug cho ứng dụng theo cách chạy tương ứng.

Condition evaluation report có thể giúp xác định cấu hình nào khớp và cấu hình nào không khớp. Với condition resource, báo cáo thường cung cấp lý do liên quan đến resource được yêu cầu hoặc resource bị thiếu.

Một số điểm cần nhớ:

- Tên JAR `application.jar` trong ví dụ cần thay bằng artifact thật.
- Báo cáo condition hỗ trợ chẩn đoán; nó không thay thế việc kiểm tra đường dẫn và nội dung đóng gói.
- Nếu cấu hình là component scan thông thường hoặc một cấu hình tùy chỉnh, chi tiết hiển thị có thể khác các auto-configuration report phổ biến.
- Hãy đọc log startup và exception gốc nếu lỗi xuất hiện trong quá trình tạo bean sau khi condition khớp.

## 13. Những lỗi thường gặp

### 13.1. Sai đường dẫn classpath

**Triệu chứng:** File có trong source nhưng condition không khớp.

Nguyên nhân có thể:

- File đặt trong thư mục khác.
- Sai chữ hoa/chữ thường trong tên file khi chạy trên filesystem phân biệt hoa thường.
- Quên prefix `classpath:`.
- Resource nằm trong `src/test/resources`, nhưng đang kiểm tra runtime production.
- File không được đóng gói vào JAR do cấu hình build.

Cách kiểm tra: đối chiếu đường dẫn dưới `src/main/resources` với đường dẫn classpath, rồi kiểm tra nội dung artifact build.

Ví dụ:

~~~text
src/main/resources/templates/report.html
              ↓
classpath:templates/report.html
~~~

Không thêm `src/main/resources/` vào classpath location; đó là đường dẫn source, không phải đường dẫn resource trong classpath.

### 13.2. Nhầm file filesystem với classpath resource

Nếu file nằm ngoài JAR:

~~~text
/opt/myapp/report.html
~~~

thì:

~~~java
@ConditionalOnResource(resources = "classpath:report.html")
~~~

không kiểm tra file bên ngoài đó. Dùng location tương ứng:

~~~java
@ConditionalOnResource(resources = "file:/opt/myapp/report.html")
~~~

`classpath:` và `file:` chỉ đến hai nguồn khác nhau.

### 13.3. Condition không khớp nhưng service vẫn được tạo

Nếu condition chỉ đặt trên một `@Bean` method mà service khác được component scan độc lập và yêu cầu bean đó, context có thể báo thiếu dependency.

Cách xử lý: đặt condition trên cả nhóm cấu hình cần resource, hoặc làm dependency tùy chọn và xử lý trường hợp không có.

### 13.4. File có mặt nhưng ứng dụng vẫn lỗi khi đọc

`@ConditionalOnResource` chỉ kiểm tra tồn tại. File có thể không đọc được, sai encoding, nội dung lỗi hoặc bị thay đổi sau startup.

Cách xử lý: xử lý exception khi mở resource và validate nội dung ở nơi phù hợp. Nếu file là điều kiện bắt buộc để ứng dụng hoạt động, có thể kiểm tra nội dung trong quá trình initialization để fail fast với thông báo rõ ràng.

### 13.5. Condition chỉ được đánh giá lúc startup

Tạo file sau khi ứng dụng chạy không tự làm bean xuất hiện. Xóa file sau startup cũng không tự xóa bean khỏi context.

Cách xử lý: nếu trạng thái file cần thay đổi động, dùng một service kiểm tra resource tại runtime hoặc thiết kế cơ chế refresh/reload phù hợp. Đừng mong `@ConditionalOnResource` hoạt động như file watcher.

### 13.6. Dùng nhiều resources nhưng chỉ tạo một file

Nếu khai báo:

~~~java
@ConditionalOnResource(resources = {
        "classpath:a.properties",
        "classpath:b.properties"
})
~~~

mà chỉ có `a.properties`, điều kiện không khớp vì `b.properties` còn thiếu.

Nếu logic cần một trong hai file, hãy tách condition hoặc viết custom condition thể hiện phép OR.

### 13.7. Dùng resource URL từ xa làm dependency khởi động

Một URL có thể không truy cập được khi khởi động vì mạng hoặc dịch vụ bên ngoài. Dùng nó làm điều kiện có thể khiến startup phụ thuộc vào availability bên ngoài.

Cách xử lý: đóng gói tài nguyên cần thiết hoặc dùng một cơ chế kiểm tra readiness/health phù hợp. `@ConditionalOnResource` không phải health check tổng quát.

## 14. Khi nào nên dùng @ConditionalOnResource?

Phù hợp khi việc **có hay không có một resource** quyết định một nhóm bean hoặc tính năng có nên được đăng ký hay không.

Ví dụ:

- Module render báo cáo chỉ bật khi có template được đóng gói.
- Một integration chỉ hoạt động khi schema hoặc mapping file đi kèm thư viện.
- Một starter cung cấp bean đọc tài nguyên mặc định nếu resource nằm trong classpath.
- Một cấu hình hỗ trợ định dạng dữ liệu chỉ nên đăng ký khi file metadata tương ứng có mặt.
- Một tính năng tùy chọn có resource được cài đặt cùng module.

Không phù hợp khi:

- Chỉ cần bật/tắt bằng property.
- Cần xác nhận class hoặc thư viện có trên classpath.
- Cần xác nhận bean khác đã được đăng ký.
- Cần kiểm tra nội dung file có hợp lệ hay không.
- Cần theo dõi file thay đổi liên tục sau startup.
- Cần kiểm tra một dịch vụ từ xa có khỏe mạnh hay không.

Chọn condition theo đúng câu hỏi cần trả lời sẽ giúp cấu hình dễ đọc và ít phụ thuộc vào hành vi ngầm.

## 15. Bài thực hành

### Bài A: Bật cấu hình khi template tồn tại

Tạo file:

~~~text
src/main/resources/templates/welcome.html
~~~

Đăng ký một bean `WelcomeTemplate` bằng `@Bean` và đánh dấu method bằng:

~~~java
@ConditionalOnResource(resources = "classpath:templates/welcome.html")
~~~

Chạy ứng dụng và xác nhận bean có trong context.

Sau đó đổi tên file hoặc di chuyển nó, khởi động lại và xác nhận bean không còn được đăng ký.

### Bài B: Condition trên class và trên method

Tạo một class cấu hình có hai bean method:

- Bean A chỉ cần resource `classpath:feature/a.txt`.
- Bean B chỉ cần resource `classpath:feature/b.txt`.

Đặt condition riêng trên từng method. Tạo hai file theo các tổ hợp khác nhau và quan sát bean definition nào xuất hiện.

Sau đó thử chuyển condition lên class và giải thích vì sao toàn bộ cấu hình bị bỏ qua nếu condition của class không khớp.

### Bài C: Kiểm tra nhiều resources

Khai báo:

~~~java
@ConditionalOnResource(resources = {
        "classpath:config/one.yml",
        "classpath:config/two.yml"
})
~~~

Thử bốn tổ hợp có/không của hai file. Ghi nhận trường hợp nào condition khớp.

### Bài D: Phân biệt tồn tại và nội dung hợp lệ

Tạo file JSON có mặt nhưng sai cú pháp. Xác nhận condition vẫn khớp. Sau đó thêm logic parse JSON trong bean initialization hoặc service và quan sát lỗi parse.

Giải thích vì sao hai phép kiểm này thuộc hai trách nhiệm khác nhau.

### Bài E: Tránh thiếu dependency

Tạo bean `TemplateService` chỉ được đăng ký khi template có mặt, sau đó tạo một component khác inject `TemplateService` bắt buộc.

Xóa template và quan sát lỗi startup. Sửa bằng cách đặt condition trên cả nhóm cấu hình hoặc dùng dependency tùy chọn với xử lý rõ ràng.

### Bài F: Kiểm tra classpath trong test và production

Đặt resource trong `src/test/resources` rồi xác nhận test thấy file. Sau đó kiểm tra rằng file không mặc nhiên được đưa vào executable JAR production. Chuyển file cần thiết sang `src/main/resources` và xác minh lại artifact.

## 16. Câu hỏi tự kiểm tra

**1. `@ConditionalOnResource` thuộc package nào?**

`org.springframework.boot.autoconfigure.condition`. Đây là annotation của Spring Boot Autoconfigure.

**2. Annotation kiểm tra điều gì?**

Nó kiểm tra sự tồn tại của các resource location được khai báo thông qua Spring ResourceLoader.

**3. Nếu liệt kê hai resource, chỉ cần một resource tồn tại có đủ không?**

Không. Các resource được liệt kê đều phải tồn tại để điều kiện khớp.

**4. Có thể đặt annotation ở đâu?**

Có thể đặt trên class cấu hình hoặc phương thức `@Bean` để điều khiển việc áp dụng cấu hình hay đăng ký bean tương ứng.

**5. Resource có mặt nhưng nội dung JSON sai, điều kiện có khớp không?**

Có thể khớp vì annotation kiểm tra sự tồn tại, không parse hay xác thực nội dung JSON.

**6. Tạo file sau khi ứng dụng đã khởi động có tự làm bean xuất hiện không?**

Không. Condition được đánh giá trong quá trình xử lý cấu hình; thay đổi resource sau đó không tự kích hoạt đăng ký bean.

**7. `classpath:` khác `file:` thế nào?**

`classpath:` tìm resource trên classpath của ứng dụng; `file:` trỏ đến tài nguyên trên filesystem.

**8. Khi bean có điều kiện không được đăng ký, consumer inject bắt buộc có thể gặp vấn đề gì?**

Nếu consumer vẫn được đăng ký và constructor yêu cầu bean đó, Spring không thể giải quyết dependency. Cần điều kiện hóa cả nhóm bean hoặc thiết kế dependency tùy chọn.

**9. `@ConditionalOnResource` có phải health check không?**

Không. Nó không xác nhận dịch vụ bên ngoài khỏe mạnh và không giám sát resource trong runtime.

## 17. Kết luận

`@ConditionalOnResource` cho phép Spring Boot **chỉ áp dụng một cấu hình hoặc đăng ký một bean khi các tài nguyên được chỉ định tồn tại**. Annotation có thể đặt trên class `@Configuration` để điều kiện hóa cả nhóm bean hoặc trên một method `@Bean` để điều kiện hóa riêng bean đó.

Hãy dùng resource location rõ ràng như `classpath:templates/report.html` hoặc `file:/opt/myapp/report.html`, hiểu rằng mọi resource liệt kê đều cần hiện diện, và nhớ condition được đánh giá trong quá trình khởi động context. Annotation chỉ kiểm tra sự tồn tại; việc đọc, parse, xác thực và xử lý lỗi nội dung vẫn thuộc trách nhiệm của ứng dụng.

Khi một bean có điều kiện được inject vào service khác, hãy bảo đảm consumer cũng có thể tồn tại khi bean ấy vắng mặt. Kết hợp đúng `@ConditionalOnResource` với `@ConditionalOnProperty`, `@ConditionalOnClass`, `@ConditionalOnBean` và các cơ chế dependency injection giúp cấu hình theo điều kiện rõ ràng, dễ kiểm thử và phù hợp với tài nguyên thực tế của ứng dụng.

