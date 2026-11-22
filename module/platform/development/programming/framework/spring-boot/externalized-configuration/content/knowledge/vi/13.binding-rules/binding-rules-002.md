# Đối chiếu kebab-case, camelCase và underscore theo từng nguồn cấu hình Spring Boot

## Mục tiêu

Một ứng dụng Spring Boot có thể khai báo cùng một thuộc tính cấu hình dưới nhiều hình thức:

~~~properties
# application.properties
app.http.read-timeout=5s
~~~

~~~yaml
# application.yml
app:
  http:
    readTimeout: 5s
~~~

~~~bash
# Biến môi trường
APP_HTTP_READTIMEOUT=5s
~~~

~~~bash
# Tham số dòng lệnh
java -jar demo.jar --app.http.read-timeout=5s
~~~

Các tên trông khác nhau nhưng có thể được **Spring Boot relaxed binding** liên kết đến cùng một trường **readTimeout** trong bean **@ConfigurationProperties**. Tuy nhiên, **không phải mọi dấu gạch dưới đều tương đương với dấu gạch ngang**, và không phải mọi API đọc thuộc tính đều áp dụng đúng cùng một cơ chế.

Chủ đề này giải thích cách đối chiếu **kebab-case**, **camelCase**, **underscore** và **UPPER_UNDERSCORE** theo từng nguồn: **.properties**, **YAML**, **environment variables**, **JVM system properties** và **command-line arguments**. Bài học cũng làm rõ các ranh giới giữa nhận diện tên, chọn nguồn ưu tiên, bind vào object, xử lý danh sách và map, cũng như các lỗi triển khai thường gặp.

Sau khi học, người đọc có thể:

- Chọn một **tên thuộc tính canonical** làm hợp đồng cấu hình.
- Viết đúng biến môi trường tương ứng mà không suy đoán từ camelCase.
- Phân biệt ba dạng tên trong file cấu hình với dạng chữ hoa của hệ điều hành.
- Hiểu vì sao **app.http.read-timeout** và **app.http.read.timeout** không nên được đánh đồng.
- Biết khi nào dùng **@ConfigurationProperties**, **@Value** và **Environment**.
- Chẩn đoán việc biến môi trường tồn tại nhưng bean không nhận giá trị.
- Kiểm soát va chạm tên và sự ghi đè khi cùng một thuộc tính có nhiều cách biểu diễn.

## 1. Từ vựng: bốn cách viết dễ nhầm

Trước hết cần phân biệt **tên property logic**, **cách trình bày tên**, và **nguồn cung cấp giá trị**.

| Kiểu tên | Ví dụ | Đặc điểm |
| --- | --- | --- |
| **kebab-case** | read-timeout | Chữ thường, các từ phân cách bằng dấu gạch ngang |
| **camelCase** | readTimeout | Từ đầu chữ thường, từ sau viết hoa chữ cái đầu |
| **underscore / snake_case** | read_timeout | Chữ thường, các từ phân cách bằng dấu gạch dưới |
| **UPPER_UNDERSCORE** | READ_TIMEOUT | Chữ hoa, các phần phân cách bằng dấu gạch dưới |

Trong cấu hình Spring Boot, một property thường có thêm **dấu chấm** để biểu diễn đường dẫn nhiều cấp:

~~~text
app.http.read-timeout
|   |    |
|   |    +-- tên property của cấp http
|   +------- cấp cấu hình http
+----------- prefix app
~~~

**read-timeout** là một tên ghép trong cùng cấp. **app.http** là hai cấp khác nhau.

Dấu chấm **.** và dấu gạch ngang **-** không có cùng ý nghĩa. Dấu gạch dưới **_** lại có vai trò phụ thuộc vào **nguồn cấu hình**. Đặc biệt ở environment variables, dấu gạch dưới chủ yếu được dùng để biểu diễn **ranh giới cấp** sau khi chuyển đổi từ tên property canonical.

### 1.1. Canonical property name

Trong tài liệu và cấu hình Spring Boot, nên dùng tên dạng **canonical kebab-case**:

~~~text
app.http.read-timeout
app.mail.retry-count
spring.main.log-startup-info
integration.catalog.base-url
~~~

Quy ước này thường là:

- Chữ thường.
- Dấu chấm phân cách từng cấp.
- Dấu gạch ngang phân cách những từ trong một tên property.
- Prefix diễn đạt phạm vi chức năng, ví dụ **app.http** hoặc **integration.catalog**.

Canonical name là **điểm tham chiếu ổn định** để từ đó viết tên tương ứng ở YAML, .properties, biến môi trường, JVM và CLI.

### 1.2. Tên Java field không phải tên env var

Java thường dùng camelCase:

~~~java
public record HttpProperties(
        java.time.Duration readTimeout,
        int maxConnections
) {}
~~~

Nếu prefix là **app.http**, hai property canonical tương ứng:

~~~text
app.http.read-timeout
app.http.max-connections
~~~

Tên biến môi trường chuẩn không đơn giản là chèn dấu gạch dưới vào mọi chữ hoa của Java field. Thay vào đó, chuyển **tên canonical đầy đủ** theo quy tắc riêng dành cho environment variables.

## 2. Một mô hình Java dùng xuyên suốt các ví dụ

Giả sử ứng dụng khai báo:

~~~java
package example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        Http http,
        Mail mail
) {
    public record Http(
            Duration readTimeout,
            Duration connectTimeout,
            int maxConnections
    ) {}

    public record Mail(
            String senderName,
            int retryCount,
            boolean enabled
    ) {}
}
~~~

Đăng ký bean cấu hình bằng cách scan:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**@ConfigurationPropertiesScan** cần bao phủ package có record AppProperties. Có thể dùng **@EnableConfigurationProperties(AppProperties.class)** nếu muốn đăng ký tường minh.

Các tên đầy đủ cần được bind:

| Java record path | Canonical property path |
| --- | --- |
| http().readTimeout() | app.http.read-timeout |
| http().connectTimeout() | app.http.connect-timeout |
| http().maxConnections() | app.http.max-connections |
| mail().senderName() | app.mail.sender-name |
| mail().retryCount() | app.mail.retry-count |
| mail().enabled() | app.mail.enabled |

Ví dụ này sẽ dùng để so sánh các nguồn. Quan trọng: **kết quả bind phụ thuộc cả tên lẫn kiểu**, nên giá trị **5s** được chuyển sang **Duration**, còn **12** được chuyển sang **int**.

## 3. Bảng đối chiếu nhanh theo từng nguồn

Lấy key canonical **app.http.read-timeout**:

| Nguồn | Cách viết nên dùng | Cách viết khác có thể được relaxed binder chấp nhận |
| --- | --- | --- |
| application.properties | app.http.read-timeout=5s | app.http.readTimeout=5s, app.http.read_timeout=5s |
| application.yml | app → http → read-timeout: 5s | app → http → readTimeout: 5s, app → http → read_timeout: 5s |
| JVM system property | -Dapp.http.read-timeout=5s | -Dapp.http.readTimeout=5s, -Dapp.http.read_timeout=5s |
| Command-line argument | --app.http.read-timeout=5s | Có thể xuất hiện biến thể tên trong nguồn, nhưng nên dùng canonical |
| Environment variable | **APP_HTTP_READTIMEOUT=5s** | Không lấy APP_HTTP_READ_TIMEOUT làm công thức chuyển chuẩn |
| Java field/record component | **readTimeout** | Đây là tên Java, không phải cú pháp tên property trong file |

Đối với file .properties, YAML và Java system properties, Spring Boot hỗ trợ các dạng **camelCase**, **kebab-case** và **underscore notation** trong bối cảnh relaxed binding.

Đối với **environment variables**, Spring Boot đưa ra quy tắc riêng vì tên biến do hệ điều hành và nền tảng triển khai quản lý. Không nên suy diễn trực tiếp từ các dạng file sang env.

Cần lưu ý hai mức độ khác nhau:

1. **Tên chuẩn để viết và tài liệu hóa:** nên dùng kebab-case trong property keys.
2. **Các dạng được relaxed binder nhận diện:** có thể linh hoạt hơn, tùy nguồn và API đang đọc.

Sự linh hoạt khi bind không phải lời khuyên tạo nhiều tên cho cùng một khóa trong một file.

## 4. application.properties: kebab-case, camelCase, underscore

Ví dụ cấu hình chuẩn:

~~~properties
app.http.read-timeout=5s
app.http.connect-timeout=2s
app.http.max-connections=25
app.mail.sender-name=Operations
app.mail.retry-count=3
app.mail.enabled=true
~~~

Khi bind với AppProperties, Spring Boot tìm các component Java tương ứng. Với kiểu đọc này, các biến thể như sau có thể được nhận diện:

~~~properties
app.http.readTimeout=5s
app.http.connectTimeout=2s
app.http.maxConnections=25
app.mail.senderName=Operations
app.mail.retryCount=3
app.mail.enabled=true
~~~

Hoặc:

~~~properties
app.http.read_timeout=5s
app.http.connect_timeout=2s
app.http.max_connections=25
app.mail.sender_name=Operations
app.mail.retry_count=3
app.mail.enabled=true
~~~

Đây là các ví dụ về **relaxed binding ở lớp @ConfigurationProperties**, không có nghĩa ta nên viết xen kẽ cả ba dạng trong cùng file thực tế.

### 4.1. Vì sao nên chọn kebab-case trong file?

Một file thống nhất dễ đọc hơn:

~~~properties
app.http.read-timeout=5s
app.http.connect-timeout=2s
app.http.max-connections=25
~~~

so với một file pha trộn:

~~~properties
app.http.readTimeout=5s
app.http.connect_timeout=2s
app.http.max-connections=25
~~~

Cả hai có thể biểu diễn những thuộc tính mong muốn, nhưng file thứ hai làm người đọc khó biết quy ước chính thức. Khi refactor class Java hoặc viết tài liệu vận hành, tên canonical đóng vai trò hợp đồng ổn định.

### 4.2. Đừng khai báo các dạng tên tương đương cùng lúc

Ví dụ cần tránh:

~~~properties
app.http.read-timeout=5s
app.http.readTimeout=8s
app.http.read_timeout=10s
~~~

Đây không phải ba thông số kinh doanh riêng biệt. Chúng là ba cách viết có khả năng được binder liên kết đến cùng trường **readTimeout**. Một file như vậy tạo sự nhập nhằng, khiến kết quả phụ thuộc cách các nguồn và binder xử lý key trùng logic.

Quy tắc vận hành nên là **một thuộc tính logic, một tên canonical** trong mỗi nguồn. Nếu thật sự có ba giá trị khác nhau, hãy đặt ba đường dẫn thể hiện ba ý nghĩa khác nhau.

### 4.3. Phân biệt dấu gạch dưới trong file với dấu gạch dưới ở env

Ở file properties, **read_timeout** là biến thể tên ghép mà binder có thể hiểu như **readTimeout**.

Ở environment variables, quy tắc chuẩn cho cùng khóa **app.http.read-timeout** là **APP_HTTP_READTIMEOUT**, không phải phép đổi toàn bộ dấu nối từ thành dấu gạch dưới.

Không dùng quy ước của file .properties để đoán tên environment variable.

## 5. YAML: cách viết key và cấu trúc thụt lề

Cùng giá trị có thể được khai báo bằng YAML ở dạng canonical:

~~~yaml
app:
  http:
    read-timeout: 5s
    connect-timeout: 2s
    max-connections: 25
  mail:
    sender-name: "Operations"
    retry-count: 3
    enabled: true
~~~

Hoặc dạng camelCase:

~~~yaml
app:
  http:
    readTimeout: 5s
    connectTimeout: 2s
    maxConnections: 25
  mail:
    senderName: "Operations"
    retryCount: 3
    enabled: true
~~~

Hoặc dạng underscore:

~~~yaml
app:
  http:
    read_timeout: 5s
    connect_timeout: 2s
    max_connections: 25
  mail:
    sender_name: "Operations"
    retry_count: 3
    enabled: true
~~~

Với **@ConfigurationProperties**, các dạng này được thiết kế để bind linh hoạt vào mô hình Java phù hợp. Dù vậy, dùng **kebab-case** trong tài liệu YAML dài hạn thường dễ đọc và khớp tên canonical.

### 5.1. Thụt lề không phải một kiểu đặt tên

Xét:

~~~yaml
app:
  http:
    read-timeout: 5s
~~~

Đường dẫn là **app.http.read-timeout**.

Nhưng nếu viết:

~~~yaml
app:
  http:
    read:
      timeout: 5s
~~~

đường dẫn trở thành **app.http.read.timeout**. Dù có thể nghe tương tự, đây là hai cấu trúc khác nhau: một là tên field ghép **readTimeout**, một là một object con **read** chứa field **timeout**.

Một sai lầm khác:

~~~yaml
app:
  http:
    read-timeout: 5s
  connect-timeout: 2s
~~~

Trường **connect-timeout** đã nằm dưới **app**, không còn nằm dưới **app.http**. Binder không tự chuyển nó sang **http.connectTimeout**.

**Tách biệt hai loại kiểm tra:** relaxed binding giải quyết **biến thể tên của cùng một property**; nó không sửa lỗi cấu trúc đường dẫn do YAML thụt lề sai.

### 5.2. Key YAML không phải Java field

Cú pháp:

~~~yaml
app:
  http:
    max-connections: 25
~~~

không đòi hỏi Java có field đặt tên với dấu gạch ngang. Java field vẫn là **maxConnections**. Khi Spring Boot bind, tên cấu hình được đối chiếu với mô hình Java theo cơ chế binder.

Dấu gạch ngang trong YAML không được mang nguyên thành tên biến trong Java source code.

### 5.3. Dùng YAML quote đúng chỗ

Nếu key hay giá trị có ký tự đặc biệt, YAML có các quy tắc parser riêng. Ví dụ Map key có bracket notation cần được quote:

~~~yaml
app:
  tenants:
    "[tenant.eu]":
      endpoint: "https://eu.example.test"
~~~

Dấu nháy của YAML không ảnh hưởng đến thuật toán relaxed binding của các key thông thường, nhưng quyết định YAML parser đọc đúng key và value hay không.

## 6. Environment variables: ba bước chuyển đổi chuẩn

Đây là phần dễ mắc lỗi nhất khi deploy qua shell, Docker hoặc Kubernetes.

Để chuyển từ một tên property canonical sang tên biến môi trường theo quy tắc Spring Boot:

1. **Thay dấu chấm (.) bằng dấu gạch dưới (_).**
2. **Bỏ dấu gạch ngang (-).**
3. **Chuyển tên còn lại thành chữ hoa.**

Ví dụ từng bước:

~~~text
app.http.read-timeout
  |
  | "." thành "_"
  v
app_http_read-timeout
  |
  | bỏ "-"
  v
app_http_readtimeout
  |
  | viết hoa
  v
APP_HTTP_READTIMEOUT
~~~

Kết quả chuẩn:

~~~bash
APP_HTTP_READTIMEOUT=5s java -jar demo.jar
~~~

### 6.1. Bảng đối chiếu hay dùng

| Canonical property | Environment variable |
| --- | --- |
| server.port | SERVER_PORT |
| spring.profiles.active | SPRING_PROFILES_ACTIVE |
| spring.datasource.url | SPRING_DATASOURCE_URL |
| spring.main.log-startup-info | SPRING_MAIN_LOGSTARTUPINFO |
| management.endpoints.web.exposure.include | MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE |
| app.http.read-timeout | APP_HTTP_READTIMEOUT |
| app.http.connect-timeout | APP_HTTP_CONNECTTIMEOUT |
| app.http.max-connections | APP_HTTP_MAXCONNECTIONS |
| app.mail.sender-name | APP_MAIL_SENDERNAME |
| app.mail.retry-count | APP_MAIL_RETRYCOUNT |
| app.mail.enabled | APP_MAIL_ENABLED |
| integration.catalog.base-url | INTEGRATION_CATALOG_BASEURL |
| integration.catalog.retry.max-attempts | INTEGRATION_CATALOG_RETRY_MAXATTEMPTS |

Đặc biệt, **spring.main.log-startup-info** được chuyển thành **SPRING_MAIN_LOGSTARTUPINFO**, không phải **SPRING_MAIN_LOG_STARTUP_INFO** nếu ta bám theo phép chuyển canonical.

### 6.2. Dấu gạch dưới trong biến môi trường thường biểu diễn cấp

So sánh:

~~~text
app.http.read-timeout
     --> APP_HTTP_READTIMEOUT

app.http.read.timeout
     --> APP_HTTP_READ_TIMEOUT
~~~

Ở ví dụ thứ hai, dấu chấm giữa **read** và **timeout** tạo một cấp riêng, nên tên env chứa thêm dấu gạch dưới.

Đây là lý do không thể “đổi cả camelCase thành UPPER_SNAKE_CASE” mà không đọc cấu trúc property. Java field **readTimeout** thường đi với **read-timeout**; hai đoạn **read** và **timeout** không tự là hai cấp trong Spring Environment.

### 6.3. Một tên env có thể tương ứng nhiều cách viết canonical

Vì dấu gạch ngang bị bỏ, các tên sau cho ra cùng một tên env:

~~~text
app.service.max-retries
    -> APP_SERVICE_MAXRETRIES

app.service.maxretries
    -> APP_SERVICE_MAXRETRIES
~~~

Điều này tạo **nguy cơ va chạm tên**. Nếu mô hình cấu hình cố tình khai báo hai property chỉ khác vị trí dấu gạch ngang, việc cung cấp chúng bằng environment variables có thể không phân biệt được.

Nên tránh thiết kế các key như vậy. Thay vào đó, dùng các tên có ý nghĩa khác nhau và cấu trúc cấp rõ ràng.

### 6.4. Biến đặt đúng nhưng ứng dụng vẫn không nhận?

Một biến được khai báo trên máy không có nghĩa nó được cấp cho tiến trình Java đang chạy. Các nguyên nhân gồm:

- Đặt biến trong terminal khác với terminal chạy ứng dụng.
- IDE hoặc service manager dùng cấu hình environment riêng.
- Docker entrypoint script không chuyển tiếp môi trường đúng cách.
- Kubernetes ConfigMap tồn tại nhưng chưa được tham chiếu trong Pod.
- Tên biến không đúng chuẩn chuyển đổi, hoặc đặt sai prefix.
- Một nguồn ưu tiên cao hơn như JVM system property/CLI đang ghi đè giá trị.
- Giá trị có mặt nhưng không chuyển được thành kiểu Java.

Để kiểm tra chính xác, cần xem cả môi trường tiến trình, Spring Environment và bean được bind, không chỉ xem một dòng YAML deployment.

## 7. JVM system properties: giữ tên property thông thường

JVM system property được cấp bằng **-D**, đặt trước **-jar**:

~~~bash
java -Dapp.http.read-timeout=7s -jar demo.jar
~~~

Với cấu hình ở ví dụ, Spring Boot có thể bind giá trị này vào **readTimeout**.

Cơ chế relaxed binding đối với **system properties** hỗ trợ các dạng tên như:

~~~text
app.http.read-timeout
app.http.readTimeout
app.http.read_timeout
~~~

Tuy nhiên, khi viết lệnh chạy, nên dùng tên canonical:

~~~bash
java -Dapp.http.read-timeout=7s -jar demo.jar
~~~

**Chú ý:** JVM system property và OS environment variable là hai nguồn khác nhau:

~~~bash
APP_HTTP_READTIMEOUT=5s java -Dapp.http.read-timeout=7s -jar demo.jar
~~~

Ở lệnh trên:

- **APP_HTTP_READTIMEOUT** là biến môi trường của tiến trình.
- **app.http.read-timeout** là JVM system property.
- Trong thứ tự nguồn Spring Boot thông thường, system property **7s** có độ ưu tiên cao hơn biến môi trường **5s**.

Việc hai nguồn có thể liên kết đến cùng một Java field không khiến chúng trở thành một nguồn duy nhất.

### 7.1. Không nhầm -DUPPER_UNDERSCORE với môi trường

Lệnh:

~~~bash
java -DAPP_HTTP_READTIMEOUT=5s -jar demo.jar
~~~

đưa tên **APP_HTTP_READTIMEOUT** vào danh sách JVM system properties, **không** tạo biến môi trường hệ điều hành có tên đó. Java có thể đọc tên nguyên văn bằng **System.getProperty("APP_HTTP_READTIMEOUT")**, nhưng không nên thiết kế hợp đồng cấu hình dựa trên việc dùng kiểu env var như JVM property.

Hãy chọn đúng cơ chế từ nguồn triển khai: **-Dapp.http.read-timeout** hoặc **APP_HTTP_READTIMEOUT**.

## 8. Command-line arguments: ưu tiên canonical kebab-case

Spring Boot thường đọc các tham số ứng dụng theo dạng:

~~~bash
java -jar demo.jar --app.http.read-timeout=9s
~~~

Giá trị được đưa vào nguồn thuộc tính command-line của Spring. Binder có thể liên kết key đó với field **readTimeout**.

Mặc dù một số biến thể tên vẫn có thể được nhận diện khi binding, cách viết CLI được khuyến nghị là:

~~~text
--app.http.read-timeout=9s
--app.http.max-connections=30
--app.mail.retry-count=4
~~~

Điều này nhất quán với application.yml/properties và tài liệu triển khai.

### 8.1. CLI argument không giống option của JVM

Đúng cách truyền JVM property:

~~~bash
java -Dapp.http.read-timeout=7s -jar demo.jar
~~~

Đúng cách truyền Spring Boot application argument:

~~~bash
java -jar demo.jar --app.http.read-timeout=9s
~~~

Đặt **-D** sau tên JAR có thể khiến nó được xử lý như một application argument thông thường thay vì JVM option. Đừng dựa vào một giá trị vô tình được ứng dụng riêng diễn giải để kết luận các nguồn là tương đương.

### 8.2. Không áp dụng quy tắc env var lên tên CLI

Ví dụ:

~~~text
--APP_HTTP_READTIMEOUT=9s
~~~

đây không phải cách viết canonical của một option Spring Boot. Khi chạy lệnh, dùng **--app.http.read-timeout=9s**. Tiền tố **--** không làm Spring tự biến mọi tên chữ hoa có gạch dưới thành cùng cách tra cứu như OS environment variable.

## 9. So sánh theo cùng một thuộc tính qua các nguồn

Giả sử file đóng gói:

~~~yaml
app:
  http:
    read-timeout: 5s
~~~

Đồng thời người vận hành cấp:

~~~bash
APP_HTTP_READTIMEOUT=8s java -Dapp.http.readTimeout=10s -jar demo.jar   --app.http.read-timeout=12s
~~~

Theo cơ chế nguồn chuẩn:

| Nguồn | Tên được dùng | Giá trị |
| --- | --- | --- |
| YAML | app.http.read-timeout | 5s |
| Environment variable | APP_HTTP_READTIMEOUT | 8s |
| JVM system property | app.http.readTimeout | 10s |
| CLI argument | app.http.read-timeout | **12s** |

Với **@ConfigurationProperties**, những key tương ứng được binder hiểu là cùng một thuộc tính logic. Giá trị cuối của field **readTimeout** là **12 giây** nếu không có PropertySource ưu tiên cao hơn ngoài các nguồn đã xét.

Đây là sự kết hợp của **hai cơ chế độc lập**:

1. **Relaxed binding:** nhận diện tên tương ứng với field Java.
2. **PropertySource precedence:** chọn giá trị có hiệu lực giữa các nguồn.

Nếu muốn kiểm tra riêng relaxed binding, chỉ nên đặt một nguồn giá trị tại một thời điểm. Nếu cùng lúc cung cấp bốn nguồn như trên, giá trị cuối còn phản ánh precedence.

## 10. Không nhầm một cấp property với một từ ghép

Đây là điểm cần hiểu trước khi chuyển giữa kebab-case, camelCase và underscore.

Ba biểu diễn dưới đây có thể hướng đến cùng Java field **readTimeout** trong một nested Http:

~~~text
app.http.read-timeout
app.http.readTimeout
app.http.read_timeout
~~~

Nhưng đường dẫn:

~~~text
app.http.read.timeout
~~~

thể hiện một nhánh cấu hình khác. Nó gần với mô hình:

~~~java
public record Http(Read read) {
    public record Read(java.time.Duration timeout) {}
}
~~~

hơn là mô hình:

~~~java
public record Http(java.time.Duration readTimeout) {}
~~~

### 10.1. Sai lầm từ việc tự tách camelCase

Nếu thấy Java field **maxConnections**, người viết có thể tự động tạo:

~~~text
APP_HTTP_MAX_CONNECTIONS
~~~

Tên này lại gần với đường dẫn **app.http.max.connections** hơn.

Với một field duy nhất **maxConnections**, tên canonical thường là **app.http.max-connections**, và biến môi trường chuẩn là:

~~~text
APP_HTTP_MAXCONNECTIONS
~~~

**Quy trình đúng:** xác định cây property → ghi tên canonical → chuyển sang env. Không bắt đầu từ chữ hoa trong tên Java rồi suy đoán cấu trúc.

### 10.2. Java nested class và YAML nested mapping

Java:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(Http http) {
    public record Http(java.time.Duration readTimeout) {}
}
~~~

YAML đúng:

~~~yaml
app:
  http:
    read-timeout: 5s
~~~

Nếu YAML viết:

~~~yaml
app:
  http:
    read:
      timeout: 5s
~~~

thì đã tạo thêm một cấp **read**. Relaxed binding không tự gộp hai cấp đó để lấp field readTimeout. Khi sửa lỗi, phải xem prefix và cây object, không chỉ tên key cuối.

## 11. @ConfigurationProperties là ngữ cảnh relaxed binding điển hình

Một bean cấu hình:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(
        Duration readTimeout,
        Duration connectTimeout,
        int maxConnections
) {}
~~~

Các file có thể dùng kebab-case, camelCase hoặc underscore theo quy tắc của nguồn, còn Java vẫn giữ camelCase.

Ví dụ YAML:

~~~yaml
app:
  http:
    read-timeout: 5s
    connect-timeout: 2s
    max-connections: 25
~~~

Và env:

~~~bash
APP_HTTP_READTIMEOUT=8s APP_HTTP_MAXCONNECTIONS=40 java -jar demo.jar
~~~

Kết quả bind trong tình huống thông thường:

~~~text
readTimeout    = Duration 8 giây
connectTimeout = Duration 2 giây
maxConnections = 40
~~~

Bản thân record không cần định nghĩa field **READTIMEOUT**, **read_timeout** hoặc **read-timeout**. Cơ chế binder chuyển tên thuộc tính về cấu trúc Java.

### 11.1. Prefix nên canonical

Khi dùng **@ConfigurationProperties(prefix = "app.http")**, nên viết prefix rõ ràng theo canonical kebab-case và dấu chấm. Prefix không phải nơi thay đổi linh hoạt thành tên biến môi trường hoặc viết hoa tùy ý.

Ví dụ một prefix có tên ghép:

~~~java
@ConfigurationProperties(prefix = "integration.catalog-client")
public record CatalogClientProperties(String baseUrl) {}
~~~

Canonical property là:

~~~text
integration.catalog-client.base-url
~~~

Tên biến môi trường là:

~~~text
INTEGRATION_CATALOGCLIENT_BASEURL
~~~

Hai dấu gạch ngang của canonical bị bỏ khi chuyển env, dấu chấm mới tạo dấu gạch dưới.

### 11.2. Relaxed binding không đảm bảo giá trị hợp lệ

Ví dụ:

~~~bash
APP_HTTP_MAXCONNECTIONS=not-a-number java -jar demo.jar
~~~

Tên đúng nhưng field Java là int. Binder không chuyển được chuỗi **not-a-number** thành số nguyên. Lỗi này thuộc **type conversion/binding**, không phải lỗi quy tắc đặt tên.

Với Duration, nên dùng giá trị như **250ms**, **5s**; với boolean dùng các dạng được converter hỗ trợ. Cấu hình đúng tên chỉ là một bước.

## 12. @Value và placeholder có sự khác biệt

Khi cần lấy một property riêng lẻ, ứng dụng thường dùng:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
class HttpSettings {

    @Value("${app.http.read-timeout:5s}")
    private String readTimeout;
}
~~~

Spring Boot khuyến nghị dùng **tên placeholder canonical kebab-case** trong @Value. Khi tên được viết theo canonical, cơ chế tra cứu của Boot có thể áp dụng những quy tắc tìm biến thể tên tương tự như binding cấu hình.

Không nên viết:

~~~java
@Value("${app.http.readTimeout:5s}")
private String readTimeout;
~~~

rồi mặc định rằng mọi nguồn sẽ được tìm giống hệt cách binder của @ConfigurationProperties xử lý tên canonical. Placeholder không phải một alias tùy ý cho mọi dạng tên có thể xuất hiện trong tất cả PropertySource.

### 12.1. @Value không thay thế @ConfigurationProperties

@Value phù hợp khi chỉ cần vài giá trị. Nếu có hàng chục trường nested hoặc List/Map, nhiều annotation @Value sẽ lặp lại tên prefix, khó kiểm tra và giảm khả năng mô hình hóa.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(
        java.time.Duration readTimeout,
        int maxConnections
) {}
~~~

thường dễ duy trì hơn hai giá trị @Value rải ở nhiều service. Có thể thêm validation và test trên record.

### 12.2. Placeholder có mặc định nhưng không chữa tên sai

~~~java
@Value("${app.http.read-timeout:5s}")
private String timeout;
~~~

Nếu biến môi trường được đặt theo một tên không khớp, placeholder có thể chọn **5s**. Việc ứng dụng chạy thành công không chứng minh biến override đã được nhận.

Để chẩn đoán, thử một giá trị khác mặc định dễ quan sát, đọc Environment và so sánh bean. Không nên dựa vào việc “không báo lỗi” làm tiêu chí binding đúng.

## 13. Environment.getProperty và các API đọc trực tiếp

Có ba đường đọc cần phân biệt:

~~~java
String directEnv = System.getenv("APP_HTTP_READTIMEOUT");
String systemProperty = System.getProperty("app.http.read-timeout");
String springProperty = environment.getProperty("app.http.read-timeout");
~~~

- **System.getenv** chỉ đọc biến môi trường của tiến trình với tên được truyền.
- **System.getProperty** đọc JVM system properties.
- **Environment.getProperty** tra cứu qua Spring Environment và các PropertySource của ứng dụng.

Bên cạnh đó, **@ConfigurationProperties** sử dụng binder chuyên dụng để liên kết cấu trúc và chuyển đổi kiểu.

Không thể khẳng định rằng một tên camelCase, underscore hay UPPER_UNDERSCORE sẽ được tất cả API trên giải quyết tương tự nhau. Chúng có cách tra cứu và xử lý tên khác nhau.

### 13.1. Environment không đồng nghĩa gọi binder

Ví dụ:

~~~java
String a = environment.getProperty("app.http.read-timeout");
String b = environment.getProperty("app.http.readTimeout");
~~~

Trong một số hoàn cảnh và nguồn, hai truy vấn có thể cho kết quả khác. Với cấu hình Spring Boot, nên dùng **tên canonical** trong code tra cứu thuộc tính và kiểm tra thêm nguồn thực tế.

Nếu đang cần bind cả nhóm field, **@ConfigurationProperties** mới là API được thiết kế cho relaxed binding và nested object.

### 13.2. In giá trị cấu hình an toàn

Một bean kiểm tra giá trị không nhạy cảm:

~~~java
import java.time.Duration;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ConfigProbe implements ApplicationRunner {

    private final Environment environment;
    private final HttpProperties http;

    ConfigProbe(Environment environment, HttpProperties http) {
        this.environment = environment;
        this.http = http;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("env raw = "
                + System.getenv("APP_HTTP_READTIMEOUT"));
        System.out.println("spring property = "
                + environment.getProperty("app.http.read-timeout"));
        Duration timeout = http.readTimeout();
        System.out.println("bound Duration = " + timeout);
    }
}
~~~

Tùy nguồn đang cấp giá trị, ba dòng có thể khác nhau. Một Duration **8s** khi in từ Java có thể được hiển thị là **PT8S**, khác chuỗi gốc nhưng vẫn biểu diễn cùng khoảng thời gian.

Không in password, API token hoặc nội dung toàn bộ PropertySource để debug. Với bí mật, nên kiểm tra cấu hình theo các metadata không nhạy cảm.

## 14. Biến môi trường theo hệ điều hành và nền tảng triển khai

### 14.1. Linux / macOS shell

~~~bash
export APP_HTTP_READTIMEOUT=8s
export APP_HTTP_MAXCONNECTIONS=40
java -jar demo.jar
~~~

Hoặc cấp riêng cho lệnh:

~~~bash
APP_HTTP_READTIMEOUT=8s APP_HTTP_MAXCONNECTIONS=40 java -jar demo.jar
~~~

Trong shell Unix, tên biến có thể phân biệt hoa/thường. Nên thống nhất chữ hoa để tránh môi trường có đồng thời **APP_HTTP_READTIMEOUT** và **app_http_readtimeout** với ý nghĩa không rõ ràng.

### 14.2. Windows PowerShell

~~~powershell
$env:APP_HTTP_READTIMEOUT = "8s"
$env:APP_HTTP_MAXCONNECTIONS = "40"
java -jar demo.jar
~~~

Biến phải tồn tại trong môi trường của đúng tiến trình JVM. Một thay đổi biến ở terminal khác sau khi JVM đã chạy thường không cập nhật bean đã được bind.

### 14.3. Docker

~~~bash
docker run --rm   -e APP_HTTP_READTIMEOUT=8s   -e APP_HTTP_MAXCONNECTIONS=40   example/demo:latest
~~~

Docker cấp biến môi trường vào container theo cơ chế runtime. Spring Boot dùng tên env để giải quyết property. Chọn tên đúng canonical giúp image dùng được ở nhiều môi trường mà không phải sửa YAML trong JAR.

### 14.4. Kubernetes

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: demo
  template:
    metadata:
      labels:
        app: demo
    spec:
      containers:
        - name: demo
          image: example/demo:latest
          env:
            - name: APP_HTTP_READTIMEOUT
              value: "8s"
            - name: APP_HTTP_MAXCONNECTIONS
              value: "40"
~~~

Kubernetes không biết record Java có field **readTimeout**. Nó chỉ đưa tên và giá trị env vào tiến trình. Spring Boot chịu trách nhiệm binder, conversion và thứ tự nguồn.

Một ConfigMap hoặc Secret phải được tham chiếu qua **env**, **envFrom** hoặc cơ chế mount phù hợp thì dữ liệu mới đến được ứng dụng. Không coi việc resource tồn tại trong cluster là bằng chứng tiến trình Java nhận đúng biến.

### 14.5. Vì sao không nên thử nhiều biến thể env cùng lúc?

Một cách debug kém hiệu quả là đặt đồng thời:

~~~text
APP_HTTP_READTIMEOUT
APP_HTTP_READ_TIMEOUT
app_http_readTimeout
~~~

với các giá trị khác nhau để “thử xem Spring nhận cái nào”. Cách này làm cấu hình khó dự đoán, có thể phụ thuộc OS hoặc cách binder chọn các khóa gần giống nhau.

Thay vào đó, xác định **app.http.read-timeout** là canonical, đặt **duy nhất APP_HTTP_READTIMEOUT**, khởi động lại và đọc kết quả.

## 15. List: chỉ số và underscore có quy tắc bổ sung

Đối với danh sách, property có dạng:

~~~text
app.clients[0].base-url
app.clients[1].base-url
~~~

Vì List chứa các phần tử có index, cách chuyển tên biến môi trường sử dụng chỉ số được bao quanh bởi dấu gạch dưới:

~~~text
APP_CLIENTS_0_BASEURL
APP_CLIENTS_1_BASEURL
~~~

Ví dụ YAML:

~~~yaml
app:
  clients:
    - name: catalog
      base-url: "https://catalog.example.test"
      retry-count: 2
    - name: billing
      base-url: "https://billing.example.test"
      retry-count: 4
~~~

Java:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record ClientCollection(List<Client> clients) {
    public record Client(
            String name,
            String baseUrl,
            int retryCount
    ) {}
}
~~~

Tên env chuẩn của các field:

~~~text
APP_CLIENTS_0_NAME
APP_CLIENTS_0_BASEURL
APP_CLIENTS_0_RETRYCOUNT
APP_CLIENTS_1_NAME
APP_CLIENTS_1_BASEURL
APP_CLIENTS_1_RETRYCOUNT
~~~

### 15.1. Dấu gạch dưới có hai vai trò trong tên env List

Ở **APP_CLIENTS_0_BASEURL**:

- Dấu gạch dưới giữa APP và CLIENTS biểu diễn dấu chấm trong đường dẫn.
- Phần **_0_** biểu diễn chỉ số **[0]** của List.
- **BASEURL** xuất phát từ tên ghép **base-url**, với dấu gạch ngang bị bỏ.

Không tự viết **APP_CLIENTS_0_BASE_URL** rồi coi đó là chuyển đổi chuẩn của **app.clients[0].base-url**. Nó có thêm dấu gạch dưới không đến từ dấu chấm hay chỉ số trong property canonical.

### 15.2. List ở nhiều nguồn có thể bị thay thế

Một lưu ý độc lập với cách đặt tên: khi nhiều PropertySource cùng cấu hình một List, Spring Boot thường dùng danh sách từ nguồn ưu tiên cao thay vì tự nối tất cả phần tử.

Đặt **APP_CLIENTS_0_NAME** có thể làm thay đổi cách binder hình thành List chứ không nhất thiết chỉ cập nhật một field của phần tử 0 rồi giữ nguyên mọi phần tử khác từ YAML. Khi cần override List phức tạp qua env, phải xác minh toàn bộ kết quả bind và cung cấp cấu hình đủ các phần tử mong muốn.

## 16. Map và key động: relaxed binding không phải phép biến đổi vô điều kiện

Giả sử ứng dụng có Map:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record RegionProperties(Map<String, Region> regions) {
    public record Region(String endpoint, int weight) {}
}
~~~

YAML:

~~~yaml
app:
  regions:
    asia:
      endpoint: "https://asia.example.test"
      weight: 50
    europe:
      endpoint: "https://europe.example.test"
      weight: 25
~~~

Đường dẫn:

~~~text
app.regions.asia.endpoint
app.regions.asia.weight
app.regions.europe.endpoint
app.regions.europe.weight
~~~

Ở đây **asia** và **europe** là **key động của Map**, không phải field cố định của record RegionProperties.

### 16.1. Khi Map key chứa dấu chấm

Nếu key thật sự là **tenant.eu**, có thể cần bracket notation:

~~~yaml
app:
  tenants:
    "[tenant.eu]":
      endpoint: "https://eu.example.test"
~~~

Trong .properties:

~~~properties
app.tenants.[tenant.eu].endpoint=https://eu.example.test
~~~

Dấu ngoặc vuông cho biết **tenant.eu** cần được giữ làm key Map. Nếu thiếu, dấu chấm có thể trở thành ranh giới nested path, tùy kiểu Map được bind.

### 16.2. Khi Map key chứa ký tự đặc biệt

Một key có dấu gạch chéo như **/internal/path** có thể được biểu diễn:

~~~yaml
app:
  headers:
    "[/internal/path]": "enabled"
~~~

Không có quy tắc đơn giản nào từ **key tùy ý có dấu chấm, chữ hoa, dấu gạch chéo** sang env var bảo đảm giữ nguyên mọi ký tự. Với Map có key động không chuẩn, nên dùng cấu hình YAML/properties có bracket notation hoặc nguồn hỗ trợ biểu diễn key đúng hợp đồng.

### 16.3. Tách canonical key và dữ liệu Map

Một tên như **app.regions.asia.endpoint** chứa:

- **app.regions**: đường dẫn cố định.
- **asia**: key dữ liệu trong Map.
- **endpoint**: field của value object.

Không suy luận rằng binder sẽ chuẩn hóa giá trị của Map key giống hệt field camelCase. Việc giữ key trong Map là một vấn đề riêng, nhất là với Map<String, Object> và Map<String, String>.

## 17. Các nguồn khác cũng có thể chứa property

Ngoài các nguồn cơ bản, Spring Boot có thể đọc **Config Data imports**, file theo profile, configtree, Java system properties, command-line arguments và các PropertySource do ứng dụng/thư viện bổ sung.

Ví dụ import:

~~~yaml
spring:
  config:
    import: "optional:file:./config/override.yml"
~~~

Nếu override.yml chứa:

~~~yaml
app:
  http:
    read-timeout: 15s
~~~

thì nó đưa thêm một tài liệu Config Data với tên canonical **app.http.read-timeout**. Một file import không yêu cầu tên key mới; relaxed binding vẫn áp dụng khi các thuộc tính từ nó được bind vào Java.

Tương tự, một configtree mount secret thành các file có tên tương ứng với property không tự làm thay đổi prefix của @ConfigurationProperties. Cần phân biệt cách nguồn biểu diễn key với quy tắc binder giải quyết tên.

Các resolver hoặc loader của thư viện ngoài có thể đưa vào Spring Environment những key với quy ước riêng. Đừng đoán rằng một key từ nguồn tùy chỉnh nhất thiết đi theo toàn bộ cách biến đổi của OS env var; nên xác nhận tên thực được đưa vào PropertySource.

## 18. Thứ tự ưu tiên nguồn không thay đổi quy tắc đặt tên

Giả sử cùng một thuộc tính có mặt ở file và môi trường:

~~~yaml
# application.yml
app:
  http:
    read-timeout: 5s
~~~

~~~bash
APP_HTTP_READTIMEOUT=8s java -jar demo.jar
~~~

Trong cấu hình Spring Boot thông thường, env có thể ghi đè Config Data, nên readTimeout = 8 giây.

Nếu thêm:

~~~bash
APP_HTTP_READTIMEOUT=8s java -Dapp.http.read-timeout=10s -jar demo.jar
~~~

thì JVM system property 10s có thể thắng env 8s.

Nếu thêm:

~~~bash
APP_HTTP_READTIMEOUT=8s java -Dapp.http.read-timeout=10s -jar demo.jar   --app.http.read-timeout=12s
~~~

thì CLI 12s có thể thắng cả hai.

| Thao tác | Câu hỏi mà nó trả lời |
| --- | --- |
| Chuyển kebab-case ↔ camelCase ↔ underscore | Tên nào có thể bind vào field? |
| Chuyển canonical sang UPPER_UNDERSCORE | Biến môi trường nên tên gì? |
| PropertySource precedence | Trong nhiều nguồn, giá trị nào thắng? |
| Type conversion | Giá trị String sẽ thành Java type nào? |
| Validation | Giá trị sau bind có hợp lệ không? |

Không được nhầm lỗi **tên biến sai** với lỗi **một nguồn khác thắng**. Cả hai có thể làm ứng dụng nhận giá trị không như mong đợi, nhưng phương pháp xử lý khác nhau.

## 19. Chữ hoa, chữ thường và tính di động giữa môi trường

Trong các file cấu hình, canonical name dùng chữ thường. Trong Java, field dùng camelCase. Trong OS env, quy tắc chuẩn chuyển sang chữ hoa.

~~~text
app.worker.max-retries  // canonical
maxRetries             // Java component
APP_WORKER_MAXRETRIES  // OS environment variable
~~~

Trên nhiều hệ Unix, tên env var phân biệt hoa/thường; trên Windows có quy tắc khác. Đừng thiết kế cấu hình phụ thuộc vào việc đồng thời tồn tại hai biến chỉ khác chữ hoa/thường.

Ngoài ra, một số công cụ triển khai có ràng buộc riêng đối với tên biến môi trường, đặc biệt các ký tự được cho phép. Dạng **UPPER_UNDERSCORE** của Spring Boot phù hợp rộng rãi với shell và hệ thống orchestration.

Với tên key chứa ký tự đặc biệt, đừng cố tạo biến môi trường tùy ý vượt quy tắc nền tảng. Có thể chuyển sang một file config hoặc một nguồn dữ liệu có cấu trúc khác.

## 20. Bảng chuyển đổi thực hành cho nhiều thuộc tính

Một bộ quy chiếu dùng khi viết tài liệu vận hành:

| Java path | Canonical | app.properties/YAML nên dùng | Env var |
| --- | --- | --- | --- |
| http.readTimeout | app.http.read-timeout | app.http.read-timeout | APP_HTTP_READTIMEOUT |
| http.connectTimeout | app.http.connect-timeout | app.http.connect-timeout | APP_HTTP_CONNECTTIMEOUT |
| http.maxConnections | app.http.max-connections | app.http.max-connections | APP_HTTP_MAXCONNECTIONS |
| mail.senderName | app.mail.sender-name | app.mail.sender-name | APP_MAIL_SENDERNAME |
| mail.retryCount | app.mail.retry-count | app.mail.retry-count | APP_MAIL_RETRYCOUNT |
| mail.enabled | app.mail.enabled | app.mail.enabled | APP_MAIL_ENABLED |
| security.tokenTtl | app.security.token-ttl | app.security.token-ttl | APP_SECURITY_TOKENTTL |
| cache.timeToLive | app.cache.time-to-live | app.cache.time-to-live | APP_CACHE_TIMETOLIVE |
| client.pool.maxSize | app.client.pool.max-size | app.client.pool.max-size | APP_CLIENT_POOL_MAXSIZE |
| batch.jobs[0].maxItems | app.batch.jobs[0].max-items | app.batch.jobs[0].max-items | APP_BATCH_JOBS_0_MAXITEMS |

Trong cột file, YAML có thể dùng cây nested thay vì viết toàn bộ key trên một dòng, nhưng đường dẫn logic không thay đổi.

Có thể diễn đạt bảng này thành hướng dẫn triển khai: **đội phát triển công bố canonical property; đội vận hành lấy từ cột env var; không tự biến đổi theo thói quen của ngôn ngữ lập trình**.

## 21. Bốn lỗi tên biến điển hình

### 21.1. Nhầm READ_TIMEOUT với READTIMEOUT

Java có readTimeout. Canonical:

~~~text
app.http.read-timeout
~~~

Tên chuẩn:

~~~text
APP_HTTP_READTIMEOUT
~~~

Tên dự đoán sai theo việc tách camelCase:

~~~text
APP_HTTP_READ_TIMEOUT
~~~

Cách sửa: bắt đầu từ canonical, không phải từ Java field rồi chèn dấu gạch dưới theo từ.

### 21.2. Quên cấp của prefix

Java:

~~~java
@ConfigurationProperties(prefix = "integration.catalog")
public record CatalogProperties(String baseUrl) {}
~~~

Canonical là **integration.catalog.base-url**, không phải **catalog.base-url**.

Env chuẩn:

~~~text
INTEGRATION_CATALOG_BASEURL
~~~

Nếu dùng **CATALOG_BASEURL**, binder không tự suy ra phần prefix còn thiếu.

### 21.3. Tự thêm dấu chấm vào tên ghép

Cần:

~~~text
app.mail.retry-count
~~~

Nhưng file lại ghi:

~~~properties
app.mail.retry.count=3
~~~

Đây là đường dẫn khác. Nếu Java có field retryCount trực tiếp trong Mail, hãy sửa tên property đúng cấu trúc thay vì chỉ đổi camelCase sang underscore.

### 21.4. Tưởng default che được mọi lỗi

Bean dùng:

~~~java
@Value("${app.mail.retry-count:3}")
private int retryCount;
~~~

Một env var bị đặt sai tên có thể khiến default 3 được sử dụng. Điều đó không chứng minh override đúng. Thử đọc **Environment.getProperty("app.mail.retry-count")** và kiểm tra dữ liệu nguồn.

Nếu property đã tìm thấy nhưng giá trị là **abc**, default cũng không tự chữa lỗi chuyển kiểu int.

## 22. Các lỗi về dữ liệu không phải lỗi naming

### 22.1. Kiểu giá trị không tương thích

~~~bash
APP_HTTP_MAXCONNECTIONS=many java -jar demo.jar
~~~

Tên đúng, nhưng không thể chuyển **many** sang int. Cần sửa giá trị hoặc xác định kiểu Java thích hợp.

### 22.2. Nhầm chuỗi rỗng với không khai báo

~~~bash
APP_MAIL_SENDERNAME='' java -jar demo.jar
~~~

Chuỗi rỗng là một giá trị có thể tồn tại trong environment. Nó không mặc nhiên giống với biến không tồn tại. Nếu giá trị bắt buộc không được blank, dùng validation.

### 22.3. Null trong YAML không luôn xóa nguồn khác

~~~yaml
app:
  mail:
    sender-name: null
~~~

Một null scalar có hành vi phụ thuộc cơ chế nạp Config Data và cách PropertySource cung cấp dữ liệu. Không nên giả định rằng null chắc chắn xóa một giá trị đến từ nguồn thấp hơn.

Khi muốn tắt một chức năng, dùng một cờ rõ nghĩa như **enabled: false**. Khi một trường bắt buộc, dùng validation để phát hiện thiếu dữ liệu.

### 22.4. Chỉ một môi trường bị lỗi

Nếu dev chạy đúng nhưng prod sai, đừng tự kết luận prod có parser YAML khác. Hãy kiểm tra:

- Profile đang hoạt động.
- File theo profile, location và import.
- Biến môi trường trong tiến trình production.
- JVM options và command-line args.
- Kết quả Spring Environment và @ConfigurationProperties.
- Các tài liệu cấu hình có cùng tên logic nhưng khác cách viết.

Đặc biệt, biến môi trường thường xuất hiện trong production thông qua Docker/Kubernetes nên một lỗi chuyển tên dễ chỉ bộc lộ khi deploy.

## 23. Diagnostic: lần theo source → canonical key → Java field

Khi có một trường Java nhận sai giá trị, nên truy nguyên theo thứ tự:

1. **Xác định field Java và prefix.** Ví dụ record HttpProperties có prefix app.http và field readTimeout.
2. **Viết tên canonical.** app.http.read-timeout.
3. **Xác định các nguồn có thể chứa key.** .properties, YAML, env, JVM, CLI, import và profile.
4. **Đối chiếu cách viết theo từng nguồn.** Env phải là APP_HTTP_READTIMEOUT.
5. **Kiểm tra môi trường của tiến trình.** Biến có thực sự đến được JVM không?
6. **Đọc giá trị Environment.** Dùng canonical key để quan sát giá trị được tra cứu.
7. **Đọc bean @ConfigurationProperties.** Binder có chuyển đúng kiểu và gán đúng field không?
8. **Xem validation/conversion nếu có lỗi.** Một giá trị đúng tên nhưng sai kiểu phải được xử lý ở tầng dữ liệu.
9. **Xem thứ tự PropertySource.** Nguồn có độ ưu tiên cao hơn có thể quyết định kết quả.

Một đoạn mã để quan sát nguồn không nhạy cảm:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@Component
class PropertySourceNames implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    PropertySourceNames(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(org.springframework.boot.ApplicationArguments args) {
        System.out.println("app.http.read-timeout = "
                + environment.getProperty("app.http.read-timeout"));

        for (PropertySource<?> source : environment.getPropertySources()) {
            System.out.println(source.getName());
        }
    }
}
~~~

Chỉ in tên PropertySource và những key giả lập không nhạy cảm. Không log mọi giá trị vì nguồn cấu hình có thể chứa password, token hoặc dữ liệu riêng tư.

### 23.1. Khi nào cần nhìn bên trong Binder?

Nếu Environment đã có property đúng mà @ConfigurationProperties không nhận, có thể nguyên nhân nằm ở:

- Prefix sai.
- Cấu trúc nested không đúng cấp.
- Thiếu đăng ký bean cấu hình.
- Conversion không thành công.
- Constructor binding hoặc setter binding không tương thích với class.
- Validation từ chối giá trị.
- List/Map có cấu trúc khác mong đợi.

Không cố “sửa” naming ở env khi root cause nằm ở cấu trúc Java hoặc kiểu dữ liệu.

## 24. Ví dụ lớp cấu hình có validation

Một cách kết hợp naming với validation:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(
        @NotNull Duration readTimeout,
        @NotNull Duration connectTimeout,
        @Min(1) int maxConnections
) {}
~~~

Cấu hình:

~~~yaml
app:
  http:
    read-timeout: 5s
    connect-timeout: 2s
    max-connections: 25
~~~

Biến môi trường:

~~~bash
APP_HTTP_READTIMEOUT=10s APP_HTTP_MAXCONNECTIONS=40 java -jar demo.jar
~~~

Nếu validation provider tương thích đã được cấu hình, các ràng buộc giúp phát hiện thiếu timeout hoặc maxConnections không hợp lệ khi khởi động.

Annotation validation không thay đổi quy tắc naming; nó chỉ kiểm tra **giá trị sau khi binder xử lý**. Với một dự án Spring Boot dùng Jakarta Validation, cần dependency phù hợp để ràng buộc có hiệu lực.

## 25. Bài thực hành 1: đổi tên canonical sang env var

Cho danh sách:

~~~text
1. server.port
2. spring.main.log-startup-info
3. app.mail.retry-count
4. app.http.read-timeout
5. app.cache.time-to-live
6. integration.billing.connect-timeout
7. app.servers[0].base-url
~~~

Đáp án theo quy tắc chuyển đổi của Spring Boot:

~~~text
1. SERVER_PORT
2. SPRING_MAIN_LOGSTARTUPINFO
3. APP_MAIL_RETRYCOUNT
4. APP_HTTP_READTIMEOUT
5. APP_CACHE_TIMETOLIVE
6. INTEGRATION_BILLING_CONNECTTIMEOUT
7. APP_SERVERS_0_BASEURL
~~~

Bài tập này buộc phân biệt dấu chấm, dấu gạch ngang và phần index của List. Nếu tên kết quả có thêm **_RETRY_COUNT**, **_READ_TIMEOUT** hoặc **_BASE_URL**, hãy quay về ba bước canonical thay vì chèn gạch dưới theo từ tiếng Anh.

## 26. Bài thực hành 2: ba dạng trong file, một field Java

Java:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(String senderName, int retryCount) {}
~~~

Ba phiên bản application.properties, mỗi phiên bản dùng độc lập:

~~~properties
# A - kebab-case
app.mail.sender-name=Team A
app.mail.retry-count=2
~~~

~~~properties
# B - camelCase
app.mail.senderName=Team B
app.mail.retryCount=3
~~~

~~~properties
# C - underscore
app.mail.sender_name=Team C
app.mail.retry_count=4
~~~

Trong bối cảnh relaxed binding của @ConfigurationProperties, các phiên bản hướng đến cùng hai field **senderName** và **retryCount**, với những giá trị khác nhau của từng file.

Câu hỏi: khi phải chọn một phiên bản làm chuẩn repository, nên chọn gì? **A**, vì canonical kebab-case dễ tài liệu hóa và chuyển sang những nguồn khác.

Không đặt cả A, B, C vào cùng một file rồi dùng kết quả để đánh giá một thứ tự “ưu tiên theo kiểu tên”. Đó không phải mục đích của relaxed binding.

## 27. Bài thực hành 3: phân biệt một cấp hay hai cấp

Hai đường dẫn:

~~~text
app.task.max-retries
app.task.max.retries
~~~

Chuyển env:

~~~text
APP_TASK_MAXRETRIES
APP_TASK_MAX_RETRIES
~~~

Viết mô hình Java phù hợp cho từng trường hợp.

Trường hợp một field ghép:

~~~java
@ConfigurationProperties(prefix = "app.task")
public record TaskProperties(int maxRetries) {}
~~~

Trường hợp một cấp nested:

~~~java
@ConfigurationProperties(prefix = "app.task")
public record TaskProperties(Max max) {
    public record Max(int retries) {}
}
~~~

Mục đích: hiểu rằng **underscore giữa MAX và RETRIES** trong tên env xuất hiện khi canonical chứa **dấu chấm**, chứ không phải khi nó chỉ chứa dấu gạch ngang.

## 28. Bài thực hành 4: đọc giá trị qua nhiều nguồn

application.yml:

~~~yaml
app:
  mail:
    retry-count: 2
~~~

Biến môi trường và tham số:

~~~bash
APP_MAIL_RETRYCOUNT=4 java -Dapp.mail.retryCount=6 -jar demo.jar   --app.mail.retry-count=8
~~~

Câu hỏi:

- System.getenv("APP_MAIL_RETRYCOUNT") nhận gì?
- System.getProperty("app.mail.retryCount") nhận gì?
- Bean MailProperties.retryCount() nhận gì, giả sử thứ tự nguồn thông thường?

Đáp án:

~~~text
System.getenv(...)       -> "4"
System.getProperty(...)  -> "6"
MailProperties.retryCount() -> 8
~~~

Hai API đầu đọc trực tiếp nguồn tương ứng; binder nhận giá trị thắng từ các PropertySource, trong tình huống này là CLI 8.

## 29. Bài thực hành 5: từ YAML nested đến biến môi trường

Cho cấu hình:

~~~yaml
integration:
  catalog-client:
    http:
      connect-timeout: 3s
      read-timeout: 7s
    retry:
      max-attempts: 5
~~~

Tên canonical:

~~~text
integration.catalog-client.http.connect-timeout
integration.catalog-client.http.read-timeout
integration.catalog-client.retry.max-attempts
~~~

Tên env:

~~~text
INTEGRATION_CATALOGCLIENT_HTTP_CONNECTTIMEOUT
INTEGRATION_CATALOGCLIENT_HTTP_READTIMEOUT
INTEGRATION_CATALOGCLIENT_RETRY_MAXATTEMPTS
~~~

Hãy giải thích vì sao **CATALOGCLIENT** và **CONNECTTIMEOUT** không chứa gạch dưới: vì tên canonical tương ứng dùng dấu gạch ngang, mà quy tắc chuyển sang environment variable yêu cầu **bỏ** dấu ấy.

## 30. Bài thực hành 6: tìm lỗi khi triển khai Kubernetes

Một ứng dụng có:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(int maxTasks) {}
~~~

YAML nền:

~~~yaml
app:
  worker:
    max-tasks: 5
~~~

Pod khai báo:

~~~yaml
env:
  - name: APP_WORKER_MAX_TASKS
    value: "20"
~~~

Người vận hành muốn maxTasks thành 20 nhưng ứng dụng vẫn nhận 5. Hướng xử lý:

1. Xác định canonical property là **app.worker.max-tasks**.
2. Áp dụng phép chuyển canonical sang env → **APP_WORKER_MAXTASKS**.
3. Sửa trường name của env trong Pod.
4. Triển khai lại để tiến trình Java nhận biến mới.
5. Đọc Environment và WorkerProperties để xác nhận giá trị 20 khi không có nguồn ưu tiên hơn.

Ví dụ sửa:

~~~yaml
env:
  - name: APP_WORKER_MAXTASKS
    value: "20"
~~~

Không nên tạo thêm một biến thứ hai chỉ để thử, khiến cả hai cùng tồn tại ở runtime.

## 31. Bài thực hành 7: xác định naming hay precedence

Có hai tình huống:

**Tình huống A:**

~~~text
File: app.http.read-timeout=5s
Env:  APP_HTTP_READ_TIMEOUT=8s
Kết quả: 5s
~~~

Trước tiên kiểm tra **naming**, vì env không phải cách chuyển canonical được khuyến nghị.

**Tình huống B:**

~~~text
File: app.http.read-timeout=5s
Env:  APP_HTTP_READTIMEOUT=8s
CLI:  --app.http.read-timeout=12s
Kết quả: 12s
~~~

Ở đây env đã dùng tên đúng. Kết quả 12s đến từ **precedence**, vì CLI thắng Config Data và env trong tình huống tiêu chuẩn.

Bài tập cho thấy hai lỗi có vẻ ngoài giống nhau — giá trị từ env không xuất hiện — nhưng cách xử lý hoàn toàn khác.

## 32. Quy ước cấu hình cho một dự án Spring Boot

Khi một dự án có cả developer, DevOps và nhiều môi trường triển khai, nên thống nhất hợp đồng:

| Thành phần | Quy ước | Ví dụ |
| --- | --- | --- |
| Java field | camelCase | maxConnections |
| Java ConfigurationProperties prefix | canonical kebab-case | app.http |
| Property trong .properties | canonical kebab-case | app.http.max-connections |
| YAML mapping key | kebab-case, nested theo cấp | http → max-connections |
| JVM -D | canonical kebab-case | -Dapp.http.max-connections=25 |
| Spring Boot CLI | canonical kebab-case | --app.http.max-connections=25 |
| Environment variable | uppercase, underscore cho cấp, bỏ hyphen | APP_HTTP_MAXCONNECTIONS |
| List index trong env | _0_, _1_... | APP_SERVERS_0_HOST |
| Map key đặc biệt | bracket notation ở nguồn phù hợp | app.tenants.[tenant.eu] |

Việc công bố canonical property cùng tên env trong README giúp tránh chuyện hai nhóm tự định nghĩa hai convention khác nhau.

### 32.1. Một bảng hợp đồng cấu hình mẫu

| Canonical key | Loại | Giá trị mẫu | Env var | Ý nghĩa |
| --- | --- | --- | --- | --- |
| app.http.read-timeout | Duration | 5s | APP_HTTP_READTIMEOUT | Giới hạn thời gian đọc |
| app.http.connect-timeout | Duration | 2s | APP_HTTP_CONNECTTIMEOUT | Giới hạn thời gian kết nối |
| app.http.max-connections | int | 25 | APP_HTTP_MAXCONNECTIONS | Số kết nối tối đa |
| app.mail.retry-count | int | 3 | APP_MAIL_RETRYCOUNT | Số lần thử gửi lại |
| app.mail.enabled | boolean | true | APP_MAIL_ENABLED | Cho phép gửi mail |
| app.cache.time-to-live | Duration | 10m | APP_CACHE_TIMETOLIVE | Thời gian sống cache |

Khi thêm một field mới, nên cập nhật bảng trên và mẫu config ở cùng thay đổi mã nguồn. Không cần chờ đến khi deploy production mới phát hiện tên env khác tên property.

### 32.2. Đừng để công cụ tự sinh tên tùy ý

Một script có thể tự chuyển camelCase thành SNAKE_CASE, trong khi Spring Boot đưa ra phép chuyển từ **canonical key** có dấu chấm/dấu gạch ngang. Nếu sinh tên env tự động, script phải nhận **canonical property path** làm đầu vào và thực hiện quy tắc chuyển tương ứng.

Nếu tên field trong Java đổi nhưng canonical key cố ý giữ ổn định nhờ cách mô hình hóa/binding, script phụ thuộc Java field có thể làm đứt hợp đồng với người vận hành.

## 33. Checklist trước khi kết luận cấu hình đã đúng

Khi chuyển giữa kebab-case, camelCase và underscore, hãy lần lượt tự kiểm tra:

1. Tên canonical đã xác định chưa?
2. Prefix có nằm đúng cấp không?
3. Dấu gạch ngang chỉ là một phần tên ghép hay thực sự cần một cấp nested?
4. Trong file .properties hoặc YAML, có đang dùng một quy ước nhất quán không?
5. Với env var, đã thay dấu chấm thành gạch dưới, bỏ dấu gạch ngang và viết hoa chưa?
6. Với List, có biểu diễn index dạng **_0_**, **_1_** không?
7. Với Map, có key động chứa ký tự đặc biệt cần bracket notation không?
8. Biến env có thực sự được truyền tới JVM đang chạy không?
9. Có nguồn khác ưu tiên cao hơn đang khai báo cùng logical property không?
10. Giá trị có chuyển đổi được thành kiểu Java và vượt validation không?
11. @ConfigurationProperties có được scan/enable đúng không?
12. Đã xác nhận giá trị thực trong bean thay vì chỉ thấy ứng dụng khởi động thành công chưa?

Mỗi câu hỏi kiểm tra một nguyên nhân độc lập. Quy trình giúp tránh sửa sai tên property khi lỗi thực tế nằm ở file profile, thứ tự nguồn hoặc type conversion.

## 34. Những điểm cần ghi nhớ

**Trong .properties và YAML**, Spring Boot relaxed binding hỗ trợ những biến thể như **read-timeout**, **readTimeout** và **read_timeout** khi bind vào cùng field Java phù hợp. Dù có thể linh hoạt, **kebab-case** là cách viết nên chuẩn hóa.

**Trong JVM system properties**, các biến thể tên tương tự có thể được binder liên kết; khi triển khai nên dùng canonical kebab-case với **-Dapp.http.read-timeout=...**.

**Trong command-line arguments**, nên dùng **--app.http.read-timeout=...** để nhất quán và giảm nhập nhằng.

**Trong environment variables**, tên chuẩn được tạo từ canonical path bằng ba bước: **dấu chấm → gạch dưới; bỏ dấu gạch ngang; viết hoa**. Vì vậy **app.http.read-timeout → APP_HTTP_READTIMEOUT**.

**Dấu chấm tạo cấp; dấu gạch ngang nằm trong tên ghép**. Hai đường dẫn **app.http.read-timeout** và **app.http.read.timeout** không nên được coi là cùng mô hình. Biến môi trường tương ứng cũng khác: **APP_HTTP_READTIMEOUT** và **APP_HTTP_READ_TIMEOUT**.

**Relaxed binding, precedence, conversion và validation là những bước khác nhau.** Tên đúng không đảm bảo giá trị thắng; giá trị thắng không đảm bảo kiểu hợp lệ. Khi gặp sự cố, lần theo **nguồn → tên canonical → PropertySource → binder → Java field** thay vì tự đổi qua lại giữa các cách viết một cách ngẫu nhiên.
