# Phân biệt tạo bean, liên kết thuộc tính và tiêm phụ thuộc với @ConfigurationProperties

## 1. Một yêu cầu tưởng đơn giản nhưng có ba việc khác nhau

Giả sử ứng dụng Spring Boot xử lý các lô công việc. Tệp `application.yaml` chứa:

~~~yaml
jobs:
  batch-size: 200
  timeout: 15s
  endpoint: https://jobs.example.test
~~~

Bạn muốn mã Java sử dụng các giá trị này một cách an toàn, có kiểu dữ liệu rõ ràng:

~~~java
public record JobProperties(
        int batchSize,
        Duration timeout,
        URI endpoint) {
}
~~~

Chỉ nhìn đoạn mã và tệp YAML, ta có thể nghĩ Spring Boot sẽ tự động tạo một `JobProperties`, đọc từng khóa và đưa đối tượng đó vào service. Trên thực tế có **ba trách nhiệm riêng**:

1. **Tạo và đăng ký bean**: làm thế nào `JobProperties` trở thành một đối tượng do Spring quản lý trong `ApplicationContext`?
2. **Liên kết thuộc tính (configuration binding)**: làm thế nào các giá trị `jobs.batch-size`, `jobs.timeout` và `jobs.endpoint` từ `Environment` được chuyển thành giá trị Java tương ứng?
3. **Tiêm phụ thuộc (dependency injection, DI)**: sau khi đối tượng cấu hình là bean, làm thế nào một `JobService` nhận được đối tượng đó qua constructor?

`@ConfigurationProperties` chủ yếu mô tả **nhóm thuộc tính cần liên kết**. Nó không đồng nghĩa với việc mọi class chỉ cần có annotation này là tự xuất hiện trong container theo mọi hoàn cảnh. Việc đăng ký có thể do quét cấu hình, đăng ký tường minh hoặc cơ chế tạo bean thông thường; cách liên kết lại phụ thuộc kiểu đối tượng và cơ chế đăng ký.

**Mục tiêu học tập:** sau bài này, bạn phân biệt được lỗi “thiếu bean”, “liên kết cấu hình thất bại” và “tiêm phụ thuộc thất bại”, đồng thời chọn được cách đăng ký và liên kết `@ConfigurationProperties` phù hợp trong Spring Boot.

## 2. Ba khái niệm dưới góc nhìn ApplicationContext và Environment

### 2.1. Bean creation và registration

**Bean** là đối tượng được Spring container quản lý. Spring có thể biết về một định nghĩa bean thông qua:

- `@Component` và component scanning.
- `@Bean` trên phương thức của một lớp cấu hình.
- `@Import`, `@EnableConfigurationProperties` hoặc các cơ chế đăng ký được framework cung cấp.
- Quét các lớp `@ConfigurationProperties` bằng `@ConfigurationPropertiesScan`.
- Auto-configuration hoặc một cơ chế đăng ký mở rộng phù hợp.

Nói “tạo bean” thường bao gồm việc Spring biết định nghĩa bean và sau đó khởi tạo đối tượng theo cơ chế thích hợp. Để tiêm phụ thuộc được, đối tượng phải **được quản lý trong container**; một đối tượng tự tạo bằng `new` bên ngoài Spring không tự trở thành bean.

### 2.2. Configuration binding

**Binding** là việc lấy thuộc tính từ `Environment`, chuyển kiểu và gắn vào một đối tượng Java theo cấu trúc đã khai báo.

Ví dụ:

~~~properties
jobs.batch-size=200
jobs.timeout=15s
~~~

được gắn vào:

~~~java
int batchSize = 200;
Duration timeout = Duration.ofSeconds(15);
~~~

Với `@ConfigurationProperties(prefix = "jobs")`, Spring Boot hiểu các thuộc tính bắt đầu từ `jobs` là dữ liệu dành cho đối tượng cấu hình.

Binding có thể thực hiện qua **setter/JavaBean binding** hoặc **constructor binding**, tùy lớp cấu hình và cách đăng ký. Nó không đồng nghĩa với việc một service đã nhận đối tượng đó.

### 2.3. Dependency injection

**Dependency injection** là cơ chế Spring cung cấp đối tượng cần thiết cho một bean khác.

~~~java
@Service
public class JobService {
    private final JobProperties properties;

    public JobService(JobProperties properties) {
        this.properties = properties;
    }
}
~~~

Trong ví dụ, `JobService` phụ thuộc vào `JobProperties`. Spring tìm bean phù hợp kiểu, rồi truyền bean đó vào constructor.

DI không tự quyết định `jobs.batch-size` bằng bao nhiêu. **Binding** mới chịu trách nhiệm đó. Và DI không nhất thiết tạo mới một `JobProperties` cho mỗi `JobService`; thông thường bean singleton được tái sử dụng theo phạm vi của bean.

### 2.4. Mô hình tổng thể

~~~text
application.yaml ──────┐
application-prod.yaml ─┤
OS environment ────────┤
JVM -Dproperties ──────┼─> Environment / PropertySources
CLI --key=value ───────┘                |
                                      lấy jobs.*
                                          |
                                          v
                                Configuration Binder
                                   |          |
                 constructor binding          JavaBean/setter binding
                                   |          |
                                   +-----+----+
                                         |
                                 JobProperties bean
                                         |
                                   Spring DI
                                         |
                                         v
                                      JobService
~~~

Sơ đồ chỉ thể hiện trách nhiệm, không phải một thứ tự cứng cho mọi kiểu bean. Với constructor binding, binder **dùng giá trị cấu hình ngay trong lúc tạo đối tượng**; với JavaBean binding, container có thể tạo đối tượng trước rồi binder điền thuộc tính. Cả hai cuối cùng có thể cung cấp một bean để Spring tiêm vào các thành phần khác.

## 3. Vì sao chỉ thêm @ConfigurationProperties chưa đủ?

Một class:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "jobs")
public class JobProperties {
    private int batchSize;
    private Duration timeout;

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Annotation `@ConfigurationProperties(prefix = "jobs")` nói rằng đối tượng này **có thể được gắn cấu hình từ nhóm `jobs`**.

Nếu ứng dụng chưa có cơ chế đăng ký class thành bean, đoạn:

~~~java
@Service
public class JobService {
    public JobService(JobProperties properties) {
    }
}
~~~

có thể khiến ứng dụng không khởi động được vì Spring **không tìm thấy bean `JobProperties`**.

Đây là lỗi ở tầng **đăng ký bean**, chưa phải bằng chứng rằng binder không hiểu `batch-size` hoặc `timeout`.

Hãy tách câu hỏi chẩn đoán:

- Có định nghĩa bean `JobProperties` trong context không?
- Nếu có, bean được tạo theo cách nào?
- Binder đã lấy đúng khóa và chuyển kiểu thành công không?
- `JobService` có tìm được đúng một bean phù hợp để inject không?

Một lỗi ở bước đầu có thể ngăn các bước sau diễn ra.

## 4. Cách đăng ký chuẩn: @ConfigurationPropertiesScan

Với các class cấu hình được thiết kế riêng cho Spring Boot, `@ConfigurationPropertiesScan` là lựa chọn quen thuộc.

### 4.1. Khai báo record bất biến

~~~java
package com.example.demo.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "jobs")
public record JobProperties(
        int batchSize,
        Duration timeout,
        URI endpoint) {
}
~~~

Record này:

- Có ba thành phần bất biến sau khi được tạo.
- Không cần setter.
- Dùng constructor chính để nhận các giá trị.
- Cho phép Spring Boot chuyển `200` thành `int`, `15s` thành `Duration` và URL hợp lệ thành `URI`.

### 4.2. Bật quét cấu hình

~~~java
package com.example.demo;

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

Với cấu trúc package:

~~~text
com.example.demo
├── DemoApplication.java
├── config
│   └── JobProperties.java
└── service
    └── JobService.java
~~~

`@ConfigurationPropertiesScan` sẽ tìm những lớp cấu hình phù hợp dưới package quét mặc định của lớp có annotation. Nó **đăng ký** `JobProperties` và cho phép Spring Boot tạo đối tượng bằng constructor binding.

Điều kiện tiên quyết là class được đặt trong phạm vi quét hoặc bạn khai báo phạm vi quét tường minh:

~~~java
@ConfigurationPropertiesScan("com.example.shared.config")
~~~

Nếu class ở ngoài phạm vi quét mà không có cách đăng ký khác, chỉ có annotation trên class chưa bảo đảm bean tồn tại.

### 4.3. Cách hiểu đúng

`@ConfigurationPropertiesScan` chịu trách nhiệm **phát hiện và đăng ký** các class `@ConfigurationProperties`. Khi định nghĩa được xử lý, hạ tầng của Spring Boot thực hiện **binding**. Service sử dụng bean về sau thông qua **DI**.

Đây là ba việc kết hợp để cho cảm giác “mọi thứ tự hoạt động”, nhưng chúng vẫn có vai trò độc lập.

## 5. Cách đăng ký tường minh: @EnableConfigurationProperties

Thay vì quét package, bạn có thể liệt kê class cấu hình cần đăng ký:

~~~java
package com.example.demo;

import com.example.demo.config.JobProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(JobProperties.class)
public class JobConfiguration {
}
~~~

Spring Boot đăng ký `JobProperties` theo cách tường minh, sau đó thực hiện liên kết những giá trị từ `Environment`.

Phù hợp khi:

- Chỉ cần một vài nhóm cấu hình cụ thể.
- Class nằm trong module/thư viện không thuộc package quét.
- Bạn muốn thể hiện rõ lớp cấu hình này phụ trách những nhóm thuộc tính nào.
- Auto-configuration hoặc cấu hình riêng của module cần bật một kiểu properties cụ thể.

Nếu bạn dùng `@EnableConfigurationProperties(JobProperties.class)` thì không bắt buộc phải đồng thời thêm `@ConfigurationPropertiesScan` chỉ để đăng ký **cùng một class**. Chọn một cơ chế rõ ràng, tránh cấu hình trùng lặp khó theo dõi.

### Tại sao cách này làm rõ ba tầng?

Trong ví dụ:

- `@EnableConfigurationProperties`: yêu cầu Spring Boot đăng ký loại bean cần thiết.
- `@ConfigurationProperties(prefix = "jobs")` trên `JobProperties`: mô tả dữ liệu đầu vào cho binder.
- `JobService(JobProperties properties)`: yêu cầu Spring tiêm bean đã được quản lý vào service.

Tất cả có thể làm việc cùng nhau, nhưng mỗi annotation/constructor diễn đạt một trách nhiệm.

## 6. Tạo bean kiểu thông thường: @Component kết hợp @ConfigurationProperties

Một class mutable cũng có thể được tạo bằng cơ chế component scanning:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "jobs")
public class MutableJobProperties {

    private int batchSize;
    private Duration timeout = Duration.ofSeconds(10);

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Ở đây:

1. `@Component` và component scan giúp Spring đăng ký/tạo bean theo cơ chế thông thường.
2. `@ConfigurationProperties` yêu cầu hạ tầng binding gắn những giá trị `jobs.*` lên instance đã tạo.
3. Một service có thể nhận `MutableJobProperties` qua constructor injection.

Đây là dạng **JavaBean binding** với setter, khác cách tạo record bất biến bằng constructor binding.

### Hạn chế cần hiểu

Không dùng `@Component` như cách mặc định để tạo các class chỉ có constructor nhận **giá trị cấu hình** và mong Spring Boot tự dùng constructor binding.

Ví dụ:

~~~java
@Component
@ConfigurationProperties(prefix = "jobs")
public record JobProperties(int batchSize, Duration timeout) {
}
~~~

Trong thiết kế này, Spring coi record là một component thông thường và có thể cố giải quyết các tham số constructor như **bean dependency**. Cơ chế constructor binding của `@ConfigurationProperties` không áp dụng theo cùng cách cho bean được tạo bởi những cơ chế thường xuyên như `@Component`.

Đối với record `@ConfigurationProperties`, hãy đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` để dùng constructor binding theo đúng mục đích.

**Ghi nhớ:** `@ConfigurationPropertiesScan` không quét các class đồng thời được đánh dấu `@Component` như một configuration-properties class riêng. Với `@Component`, trách nhiệm đăng ký thuộc component scan và việc liên kết dùng cơ chế phù hợp với bean hiện có.

## 7. Constructor binding và JavaBean binding khác nhau như thế nào?

| Tiêu chí | Constructor binding | JavaBean / setter binding |
| --- | --- | --- |
| Đối tượng thường gặp | Record, class bất biến có constructor nhận cấu hình | Class mutable có constructor phù hợp và setter |
| Đường tạo giá trị | Binder phân giải và chuyển giá trị trước khi gọi constructor | Spring tạo đối tượng rồi binder cập nhật thuộc tính có thể ghi |
| Cần setter? | Không | Thường có setter cho thuộc tính scalar cần gắn |
| Tích hợp với đăng ký | `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` | Hai cách trên hoặc bean do Spring tạo bằng `@Component`/`@Bean` |
| Ưu điểm | Dữ liệu sau tạo ổn định, thể hiện rõ thông số bắt buộc | Thuận tiện với lớp mutable và đối tượng thư viện đã có |
| Cần cân nhắc | Constructor phải nhận giá trị cấu hình; không trộn với DI bean tùy tiện | Object có thể tạm thời ở trạng thái chưa gắn đủ thuộc tính trong quá trình khởi tạo |

### 7.1. Record và constructor binding

~~~java
@ConfigurationProperties(prefix = "mail")
public record MailProperties(
        String from,
        int retryCount) {
}
~~~

Với Spring Boot 3.x, record có constructor chính phù hợp được hỗ trợ constructor binding khi đăng ký qua quét cấu hình hoặc `@EnableConfigurationProperties`. Bộ gắn kết đọc `mail.from`, `mail.retry-count` rồi tạo `MailProperties` từ hai giá trị này.

Không cần tự viết:

~~~java
new MailProperties(
    environment.getProperty("mail.from"),
    environment.getProperty("mail.retry-count", Integer.class));
~~~

Bộ gắn kết đã thực hiện phần đọc và chuyển kiểu theo cấu trúc mà bạn khai báo.

### 7.2. Class bất biến có nhiều constructor

Trong những trường hợp một class có nhiều constructor, có thể cần đánh dấu constructor dùng để binding:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "gateway")
public class GatewayProperties {

    private final String host;
    private final Duration timeout;

    @ConstructorBinding
    public GatewayProperties(String host, Duration timeout) {
        this.host = host;
        this.timeout = timeout;
    }

    public GatewayProperties(String host) {
        this(host, Duration.ofSeconds(5));
    }

    public String getHost() {
        return host;
    }

    public Duration getTimeout() {
        return timeout;
    }
}
~~~

Trong Spring Boot 3.x, `@ConstructorBinding` áp dụng trên **constructor**, được cung cấp ở package `org.springframework.boot.context.properties.bind`. Đừng dùng cú pháp/package của những phiên bản Spring Boot cũ nếu dự án đang dùng Boot 3.x.

Đây là ví dụ để hiểu việc chọn constructor. Với một record hoặc class chỉ có một constructor tham số hợp lệ, Spring Boot thường suy ra constructor cần dùng mà không yêu cầu annotation riêng.

### 7.3. JavaBean binding qua setter

~~~java
@ConfigurationProperties(prefix = "gateway")
public class MutableGatewayProperties {

    private String host = "localhost";
    private Duration timeout = Duration.ofSeconds(5);

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Với JavaBean binding, các giá trị ban đầu của field có thể đóng vai trò mặc định khi cấu hình không cung cấp khóa tương ứng; nếu cung cấp thì binder sẽ thay đổi giá trị qua setter.

Trong ví dụ trên, mặc định `timeout` là 5 giây. Nếu `gateway.timeout=30s` có hiệu lực, đối tượng nhận `Duration.ofSeconds(30)` sau binding.

**Không có yêu cầu mọi lớp `@ConfigurationProperties` phải immutable.** Quan trọng là cách đăng ký, mục đích của lớp và cơ chế liên kết phải tương thích.

## 8. Dependency injection: khi bean cấu hình đã sẵn sàng

Sau khi `JobProperties` được đăng ký và được tạo/bind thành công, một service khác có thể nhận bean này:

~~~java
package com.example.demo.service;

import com.example.demo.config.JobProperties;
import org.springframework.stereotype.Service;

@Service
public class JobService {

    private final JobProperties properties;

    public JobService(JobProperties properties) {
        this.properties = properties;
    }

    public int batchSize() {
        return properties.batchSize();
    }

    public String destination() {
        return properties.endpoint().toString();
    }
}
~~~

Spring nhìn vào constructor `JobService(JobProperties properties)` rồi tìm bean kiểu `JobProperties` trong context. Nếu tìm đúng một bean tương thích, Spring truyền bean đó vào.

**Điều DI giải quyết:** làm cho `JobService` có đối tượng cấu hình mà nó cần.

**Điều DI không giải quyết:** tự chuyển `15s` thành `Duration`, tự hiểu cấu trúc `jobs.batch-size` hoặc tự kiểm tra URI hợp lệ. Đó là việc của configuration binding và chuyển kiểu.

### Không cần @Autowired nếu chỉ có một constructor

Trong Spring Framework hiện đại, một bean có một constructor thì thông thường không cần viết thêm `@Autowired` trên constructor đó:

~~~java
@Service
public class JobService {
    private final JobProperties properties;

    public JobService(JobProperties properties) {
        this.properties = properties;
    }
}
~~~

Cách tiêm qua constructor làm phụ thuộc bắt buộc được thể hiện rõ, thuận tiện cho kiểm thử và giữ field ở trạng thái `final`.

Không nên nhầm constructor nhận một **bean `JobProperties`** với constructor của chính `JobProperties` nhận các **giá trị cấu hình**. Hai constructor nhìn giống nhau nhưng được hạ tầng khác nhau dùng theo cơ chế đăng ký:

~~~text
JobProperties(int batchSize, Duration timeout, URI endpoint)
               ^^^^^^^^^       ^^^^^^^^        ^^^
               dữ liệu cấu hình được Binder chuyển kiểu

JobService(JobProperties properties)
           ^^^^^^^^^^^^^^^^^^^^^^^^
           bean đã đăng ký được Spring DI cung cấp
~~~

Đây là điểm phân biệt quan trọng nhất của bài.

## 9. Ví dụ đầy đủ: từ application.yaml đến Service

### 9.1. Tổ chức dự án

~~~text
src/main/
├── java/com/example/reporting/
│   ├── ReportingApplication.java
│   ├── config/
│   │   └── ReportProperties.java
│   └── service/
│       ├── ReportService.java
│       └── ReportRunner.java
└── resources/
    └── application.yaml
~~~

### 9.2. Tệp cấu hình

~~~yaml
reports:
  batch-size: 120
  timeout: 8s
  endpoint: https://reporting.example.test
  enabled: true
~~~

### 9.3. ConfigurationProperties record

~~~java
package com.example.reporting.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "reports")
public record ReportProperties(
        int batchSize,
        Duration timeout,
        URI endpoint,
        boolean enabled) {
}
~~~

### 9.4. Ứng dụng kích hoạt scanning

~~~java
package com.example.reporting;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ReportingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReportingApplication.class, args);
    }
}
~~~

### 9.5. Service sử dụng bean qua DI

~~~java
package com.example.reporting.service;

import com.example.reporting.config.ReportProperties;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    private final ReportProperties properties;

    public ReportService(ReportProperties properties) {
        this.properties = properties;
    }

    public String summary() {
        return "enabled=" + properties.enabled()
                + ", batchSize=" + properties.batchSize()
                + ", timeout=" + properties.timeout()
                + ", endpoint=" + properties.endpoint();
    }
}
~~~

### 9.6. Runner minh họa kết quả

~~~java
package com.example.reporting.service;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ReportRunner implements ApplicationRunner {

    private final ReportService service;

    public ReportRunner(ReportService service) {
        this.service = service;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(service.summary());
    }
}
~~~

Với cấu hình mặc định, chuỗi minh họa:

~~~text
enabled=true, batchSize=120, timeout=PT8S, endpoint=https://reporting.example.test
~~~

Vì `Duration.toString()` hiển thị kiểu ISO-8601, `8s` có thể được biểu diễn thành `PT8S` trong Java.

Chạy với đối số ghi đè:

~~~bash
java -jar reporting.jar --reports.batch-size=250 --reports.timeout=30s
~~~

Service có thể nhận:

~~~text
enabled=true, batchSize=250, timeout=PT30S, endpoint=https://reporting.example.test
~~~

Quy trình thực tế:

1. Spring Boot nạp nguồn cấu hình và xác định giá trị hiệu lực cho `reports.*`.
2. `@ConfigurationPropertiesScan` phát hiện và đăng ký `ReportProperties`.
3. Binder tạo record với các giá trị đã chuyển kiểu.
4. Spring tạo `ReportService` và tiêm bean `ReportProperties`.
5. Spring tạo `ReportRunner`, tiêm `ReportService` rồi gọi runner sau khi khởi tạo context.

Đây là một cách nhìn xuyên suốt ba cơ chế: **đăng ký/tạo bean – binding – DI**.

## 10. @Bean và @ConfigurationProperties: cấu hình đối tượng của thư viện ngoài

Không phải class nào bạn muốn bind cũng có thể sửa mã nguồn để gắn `@ConfigurationProperties`. Với một class mutable có sẵn từ thư viện ngoài hoặc module dùng chung, bạn có thể dùng `@Bean` kết hợp `@ConfigurationProperties` trên **phương thức factory**.

Ví dụ ta có một class mutable `RemoteClientOptions`:

~~~java
package com.example.reporting.client;

import java.net.URI;
import java.time.Duration;

public class RemoteClientOptions {

    private URI endpoint;
    private Duration timeout = Duration.ofSeconds(5);

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Cấu hình tạo bean:

~~~java
package com.example.reporting.config;

import com.example.reporting.client.RemoteClientOptions;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RemoteClientConfig {

    @Bean
    @ConfigurationProperties(prefix = "remote.client")
    RemoteClientOptions remoteClientOptions() {
        return new RemoteClientOptions();
    }
}
~~~

Với:

~~~yaml
remote:
  client:
    endpoint: https://gateway.example.test
    timeout: 12s
~~~

cơ chế gồm:

- Phương thức `@Bean` **tạo và đăng ký** một đối tượng `RemoteClientOptions`.
- `@ConfigurationProperties(prefix = "remote.client")` yêu cầu binder **liên kết các thuộc tính** vào đối tượng đó, qua các phương thức setter.
- Bean khác có thể **inject** `RemoteClientOptions` bằng kiểu Java tương ứng.

~~~java
package com.example.reporting.client;

import org.springframework.stereotype.Service;

@Service
public class RemoteGateway {

    private final RemoteClientOptions options;

    public RemoteGateway(RemoteClientOptions options) {
        this.options = options;
    }

    public String targetDescription() {
        return options.getEndpoint() + " (" + options.getTimeout() + ")";
    }
}
~~~

Cách này đặc biệt hữu ích khi cấu hình đối tượng mutable của bên thứ ba có JavaBean properties tương ứng.

**Giới hạn quan trọng:** `@Bean @ConfigurationProperties` được dùng với instance mà factory đã tạo ra, thường theo hướng JavaBean binding. Đừng hiểu rằng gắn `@ConfigurationProperties` trên phương thức `@Bean` sẽ khiến Spring Boot tự dùng constructor binding của một record do factory đã trả về.

## 11. Binding không phải là tự động tiêm mọi bean vào Properties

Một hiểu lầm thường gặp là class `@ConfigurationProperties` có constructor nhận `DataSource`, `RestClient` hay một service khác thì binder sẽ tự tiêm bean tương ứng.

Ví dụ ý tưởng sai khi đăng ký qua configuration properties scanning:

~~~java
@ConfigurationProperties(prefix = "integration")
public class IntegrationProperties {

    private final AuditService auditService;

    public IntegrationProperties(AuditService auditService) {
        this.auditService = auditService;
    }
}
~~~

Nếu Spring Boot chọn constructor binding, nó cố gắn một **thuộc tính cấu hình** phù hợp với tham số `auditService`, không chủ động dùng DI như constructor của `@Service`. Class này còn không có field dữ liệu đơn giản cần lấy từ `integration.*`.

Hãy tách hai trách nhiệm:

~~~java
@ConfigurationProperties(prefix = "integration")
public record IntegrationProperties(
        String endpoint,
        int retries) {
}
~~~

~~~java
@Service
public class IntegrationService {

    private final IntegrationProperties properties;
    private final AuditService auditService;

    public IntegrationService(
            IntegrationProperties properties,
            AuditService auditService) {
        this.properties = properties;
        this.auditService = auditService;
    }
}
~~~

Giả sử `AuditService` đã là một bean hợp lệ. Cách viết thứ hai giúp:

- `IntegrationProperties` chỉ giữ dữ liệu cấu hình.
- `IntegrationService` được DI cả bean cấu hình và bean nghiệp vụ.
- Binder không phải xử lý một service như thuộc tính YAML.

Các tài liệu Spring Boot khuyến nghị đối tượng `@ConfigurationProperties` nên chủ yếu làm việc với **Environment** và không phụ thuộc trực tiếp vào các bean khác. Nếu bạn thật sự cần tích hợp một số logic phụ thuộc bean khi tạo object, hãy dùng một bean/service riêng hoặc cơ chế `@Bean` phù hợp.

## 12. @Value là đường tiêm giá trị, nhưng khác @ConfigurationProperties

Một service cũng có thể đọc từng giá trị qua `@Value`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class SimpleReportService {

    private final int batchSize;
    private final String endpoint;

    public SimpleReportService(
            @Value("${reports.batch-size:100}") int batchSize,
            @Value("${reports.endpoint}") String endpoint) {
        this.batchSize = batchSize;
        this.endpoint = endpoint;
    }
}
~~~

Ở đây:

- `SimpleReportService` được đăng ký do `@Service`.
- Giá trị trong `@Value("${...}")` được Spring phân giải từ `Environment`.
- Spring tiêm các giá trị vào constructor của service.

Không có đối tượng `ReportProperties` trung gian.

### So sánh

| Tiêu chí | `@Value` | `@ConfigurationProperties` |
| --- | --- | --- |
| Mục đích chính | Tiêm một hoặc vài giá trị tại điểm sử dụng | Liên kết nhóm giá trị vào class/record cấu hình |
| Đăng ký bean cấu hình riêng? | Không bắt buộc | Cần nếu muốn inject đối tượng properties |
| Cấu trúc nhóm khóa | Viết từng biểu thức `${key}` | Dùng `prefix` và field tương ứng |
| Chuyển kiểu | Có thể thông qua cơ chế chuyển đổi của Spring | Được Binder xử lý theo cấu trúc đối tượng |
| Relaxed binding | Không tương đương đầy đủ với Binder | Là một thế mạnh |
| Validation cấu hình theo nhóm | Cần tự tổ chức | Tích hợp tốt với Bean Validation |
| Nên dùng khi | Ít khóa, logic đơn giản | Cấu hình lớn, có kiểu và dùng lại nhiều nơi |

Khi class chỉ cần một tên hiển thị, `@Value` có thể đủ. Khi một module cần endpoint, timeout, batch size, các nhóm con và validation, `@ConfigurationProperties` thường dễ đọc, dễ kiểm thử và dễ mở rộng hơn.

## 13. Tạo bean xong nhưng bind thất bại: lỗi thuộc tầng nào?

Giả sử:

~~~yaml
reports:
  batch-size: abc
  timeout: 8s
  endpoint: https://reporting.example.test
~~~

Trong khi record khai báo:

~~~java
@ConfigurationProperties(prefix = "reports")
public record ReportProperties(
        int batchSize,
        Duration timeout,
        URI endpoint) {
}
~~~

Bean đã được **đăng ký** qua scanning hoặc `@EnableConfigurationProperties`, nhưng binder không chuyển `abc` thành số nguyên hợp lệ cho `int batchSize`. Quá trình tạo/bind bean có thể thất bại với lỗi liên quan đến `ConfigurationPropertiesBindException` hoặc thông tin nguyên nhân của `BindException`.

Đây không phải lỗi “Spring không biết `ReportProperties` là bean”. Nó là lỗi **liên kết hoặc chuyển kiểu**.

Ngược lại:

~~~text
No qualifying bean of type '...ReportProperties'
~~~

thường là dấu hiệu bạn cần điều tra **đăng ký bean**, package scan hoặc điều kiện context.

Và:

~~~text
expected single matching bean but found 2
~~~

thường là lỗi **DI có nhiều ứng viên**, chẳng hạn bạn vô tình đăng ký nhiều bean cùng kiểu.

Ba nhóm lỗi này gợi ý các hướng xử lý khác nhau.

## 14. Validation: kiểm tra giá trị có hợp lệ về nghiệp vụ

Chuyển kiểu thành công chưa bảo đảm dữ liệu hợp lệ. Ví dụ `batch-size=0` là số nguyên hợp lệ về cú pháp, nhưng không hợp lệ nếu hệ thống yêu cầu ít nhất 1 phần tử mỗi lô.

Có thể dùng Bean Validation:

~~~java
package com.example.reporting.config;

import java.net.URI;
import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "reports")
public record ReportProperties(
        @Min(1) int batchSize,
        @NotNull Duration timeout,
        @NotNull URI endpoint,
        boolean enabled) {
}
~~~

Nếu project có Bean Validation provider phù hợp (trong nhiều ứng dụng dùng `spring-boot-starter-validation`), Spring Boot có thể kiểm tra các constraint trong quá trình liên kết cấu hình.

Trong ví dụ:

- `reports.batch-size=0` vi phạm `@Min(1)`.
- Không có `reports.endpoint` có thể vi phạm `@NotNull`.
- `reports.timeout=invalid` có thể gây lỗi chuyển kiểu **trước** khi tới validation.

Nếu cần kiểm tra `timeout` phải dương, bạn có thể bổ sung constraint hoặc quy tắc validation riêng theo kiểu dữ liệu. Không nên cho rằng `@NotNull` tự đảm bảo một `Duration` là số dương.

### Binding và validation vẫn khác nhau

1. **Đăng ký bean** xác định đối tượng nào cần tạo.
2. **Binding** lấy và chuyển các thuộc tính.
3. **Validation** kiểm tra giá trị đối tượng theo quy tắc.
4. **DI** cung cấp bean hợp lệ cho đối tượng tiêu thụ.

Khi validation thất bại, ứng dụng thường không hoàn tất khởi động với bean cấu hình lỗi. Điều này có lợi: cấu hình sai được phát hiện sớm.

## 15. Thứ tự PropertySource ảnh hưởng binding, không thay đổi kiểu bean

Với tệp:

~~~yaml
reports:
  batch-size: 120
  timeout: 8s
~~~

và lệnh:

~~~bash
java -jar reporting.jar --reports.batch-size=250
~~~

theo cấu hình mặc định của Spring Boot, giá trị `reports.batch-size` từ dòng lệnh có ưu tiên hơn tệp. Binder dùng **giá trị hiệu lực** trong `Environment` nên record nhận `250`.

Không cần thay `@ConfigurationProperties(prefix="reports")` hay sửa code trong `ReportService`. Thứ tự nguồn quyết định giá trị mà binding sử dụng.

### Profile và tệp theo môi trường

~~~yaml
# application.yaml
reports:
  batch-size: 100
~~~

~~~yaml
# application-prod.yaml
reports:
  batch-size: 1000
~~~

Khi profile `prod` hoạt động và không có nguồn ưu tiên cao hơn ghi đè, `ReportProperties.batchSize()` sẽ có giá trị `1000`.

**Đây vẫn là cùng một bean kiểu `ReportProperties`**, không phải “bean dev” và “bean prod” do `@ConfigurationProperties` tự tạo. Profile làm thay đổi nguồn dữ liệu, còn việc tạo bean theo profile cần cơ chế điều kiện riêng, chẳng hạn `@Profile`.

## 16. @Profile có thể quyết định tạo bean, còn @ConfigurationProperties quyết định dữ liệu

Giả sử một hệ thống có hai triển khai `ReportPublisher`:

~~~java
public interface ReportPublisher {
    String destination();
}
~~~

Cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class PublisherConfiguration {

    @Bean
    @Profile("!prod")
    ReportPublisher localPublisher(ReportProperties properties) {
        return () -> "local: " + properties.endpoint();
    }

    @Bean
    @Profile("prod")
    ReportPublisher productionPublisher(ReportProperties properties) {
        return () -> "production: " + properties.endpoint();
    }
}
~~~

Trong ví dụ:

- `@Profile("prod")` và `@Profile("!prod")` chọn **bean `ReportPublisher`** nào được đăng ký.
- `@ConfigurationProperties` trên `ReportProperties` xác định **nhóm dữ liệu `reports.*`** dùng để tạo properties bean.
- Tham số `ReportProperties properties` của phương thức `@Bean` được **Spring DI** cung cấp.
- Tệp `application-prod.yaml` có thể cung cấp giá trị `reports.endpoint` khi profile `prod` hoạt động.

Như vậy, ba trách nhiệm khác nhau có thể phối hợp trong cùng một đoạn cấu hình.

Nếu cả `prod` và `cloud` hoạt động, điều kiện `@Profile("prod")` vẫn thỏa; điều kiện `!prod` không thỏa. Nhưng nếu bạn khai báo hai bean `@Profile("prod")` và `@Profile("cloud")` cùng kiểu, cả hai có thể được tạo, dẫn đến DI mơ hồ. Thứ tự file profile không tự chọn bean thắng.

## 17. Một bean cấu hình có thể được nhiều service sử dụng

Ví dụ:

~~~java
@Service
public class ReportService {

    private final ReportProperties properties;

    public ReportService(ReportProperties properties) {
        this.properties = properties;
    }
}
~~~

~~~java
@Service
public class AlertService {

    private final ReportProperties properties;

    public AlertService(ReportProperties properties) {
        this.properties = properties;
    }
}
~~~

Hai service nhận cùng một **bean `ReportProperties`** trong ngữ cảnh singleton thông thường.

Điều đó không có nghĩa Spring Boot phải bind lại cấu hình một lần cho mỗi service. Binder tạo/thiết lập properties bean trong vòng đời context, rồi cơ chế DI cung cấp bean đã được quản lý tới các thành phần tiêu thụ.

Một ưu điểm của cách làm này là nhiều service có thể dùng **cùng nguồn sự thật cho cấu hình** thay vì mỗi service tự đọc và chuyển kiểu các khóa giống nhau.

### Không nhầm với việc tự tạo object bằng new

~~~java
ReportProperties manual = new ReportProperties(
        10,
        Duration.ofSeconds(1),
        URI.create("https://manual.example.test"));
~~~

Đối tượng `manual` là Java object thông thường. Việc gọi constructor này **không tự đăng ký** nó vào `ApplicationContext` và cũng không buộc binder đọc `application.yaml`.

Tương tự, tự viết:

~~~java
JobService service = new JobService(manual);
~~~

là dependency injection theo nghĩa chung của lập trình hướng đối tượng, nhưng không phải một thao tác Spring container thực hiện từ bean definition. Khi thiết kế Spring Boot, cần biết phần nào do Spring quản lý và phần nào do code tự khởi tạo.

## 18. Không đăng ký trùng khi trộn @Component, @Bean và scanning

Một lỗi có thể xảy ra khi bạn đồng thời:

- Gắn `@Component` trên lớp `MutableJobProperties`.
- Tạo thêm một `@Bean MutableJobProperties` trong một `@Configuration`.
- Cùng inject theo kiểu `MutableJobProperties` mà không chỉ rõ bean cần dùng.

Khi đó context có thể có **hai bean cùng kiểu** và một constructor nhận duy nhất `MutableJobProperties` trở nên mơ hồ.

Ví dụ:

~~~java
@Component
@ConfigurationProperties(prefix = "jobs")
public class MutableJobProperties {
    // fields, getters, setters
}
~~~

~~~java
@Configuration
public class ExtraConfiguration {

    @Bean
    MutableJobProperties anotherProperties() {
        return new MutableJobProperties();
    }
}
~~~

Nếu service viết:

~~~java
public JobService(MutableJobProperties properties) {
}
~~~

thì Spring có thể báo có nhiều ứng viên cùng loại.

Để tránh lỗi:

- Chọn một cách đăng ký cho mỗi kiểu properties theo mục đích thực tế.
- Với record cấu hình được binder tạo, ưu tiên `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.
- Với đối tượng thư viện mutable, dùng `@Bean @ConfigurationProperties` khi phù hợp.
- Với bean Spring mutable được component scan, có thể dùng `@Component @ConfigurationProperties`.
- Nếu có nhiều bean cùng kiểu một cách chủ ý, thiết kế tên bean, qualifier hoặc cấu trúc kiểu riêng để giải quyết DI.

Không nên tự động sửa vấn đề bằng cách thêm `@Primary` cho một bean mà chưa biết vì sao có hai định nghĩa. `@Primary` có thể giúp chọn một ứng viên, nhưng không làm mất nguồn gốc trùng lặp.

## 19. Phạm vi quét package và tổ chức module

Giả sử:

~~~text
com.acme.application
└── DemoApplication.java

com.acme.shared
└── SharedProperties.java
~~~

Nếu `@ConfigurationPropertiesScan` nằm trên `DemoApplication` và không chỉ định package khác, class `SharedProperties` **có thể nằm ngoài phạm vi quét** vì không thuộc package `com.acme.application` hoặc package con.

Cách giải quyết trực tiếp:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan({
    "com.acme.application",
    "com.acme.shared"
})
public class DemoApplication {
}
~~~

Hoặc đăng ký rõ class:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(SharedProperties.class)
public class SharedConfig {
}
~~~

Cả hai cách có thể giúp hạ tầng Spring Boot biết bean cần tạo. Sau đó, binding vẫn sử dụng prefix được khai báo trong class `SharedProperties`.

### Annotation prefix không phải chỉ dẫn package scan

`@ConfigurationProperties(prefix = "shared")` có nghĩa **gắn các khóa `shared.*`**. Nó không có nghĩa “tìm class ở package `com.acme.shared`”. Đây là hai khái niệm hoàn toàn khác.

## 20. Những triệu chứng giúp xác định tầng bị lỗi

| Triệu chứng | Tầng cần xem trước | Gợi ý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` cho class properties | Đăng ký bean | Kiểm tra `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, package và component scan. |
| Không inject được vì có nhiều bean cùng kiểu | DI / đăng ký | Kiểm tra tạo trùng bằng `@Component`, `@Bean` hoặc nhiều cấu hình. |
| `ConfigurationPropertiesBindException` | Binding | Kiểm tra tên khóa, kiểu Java, cú pháp và giá trị từ `Environment`. |
| `batchSize=0` dù mong 200 | Binding / nguồn | Kiểm tra khóa `batch-size`, prefix, giá trị có hiệu lực và giá trị mặc định của kiểu primitive. |
| Bean tồn tại nhưng URI không hợp lệ | Chuyển kiểu / validation | Kiểm tra `URI`, cấu hình và quy tắc validation. |
| Giá trị từ CLI thắng YAML | PropertySource precedence | Đây là hành vi bình thường khi nguồn CLI có ưu tiên cao hơn. |
| Dùng record nhưng Spring hỏi bean `int` hoặc `Duration` trong constructor | Đăng ký sai kiểu cho constructor binding | Kiểm tra việc gắn `@Component` hoặc đăng ký như bean thường. |
| Service dùng cấu hình cũ sau khi sửa file | Vòng đời cấu hình | Việc sửa file không tự làm mới mọi properties bean. |

Trong nhật ký lỗi, cần xem **nguyên nhân đầu tiên có ý nghĩa**. `UnsatisfiedDependencyException` có thể xuất hiện như một lỗi bọc bên ngoài khi thiếu bean, nhưng cũng có thể bọc một lỗi tạo bean do binding thất bại. Vì vậy, đừng kết luận chỉ dựa trên tên exception ngoài cùng.

## 21. Thời điểm cấu hình được liên kết và vấn đề thay đổi khi chạy

Trong ứng dụng thông thường, Spring Boot chuẩn bị `Environment` và xử lý Config Data trong lúc khởi động. Các bean cấu hình được tạo/bind khi context xây dựng các thành phần cần thiết.

Nếu bạn sửa `application.yaml` trên đĩa sau khi ứng dụng đã chạy, điều đó **không bảo đảm** các bean `@ConfigurationProperties` được liên kết lại. Với một record bất biến, giá trị của nó tất nhiên không thể tự đổi sau khi object đã tạo.

Muốn có thay đổi cấu hình động, ứng dụng cần một cơ chế riêng để cập nhật nguồn cấu hình và các thành phần liên quan. Không nên kỳ vọng `@ConfigurationPropertiesScan`, setter binding hoặc constructor injection tự thực hiện việc refresh.

Phân biệt:

- **Environment có thể bị thay đổi trong runtime** nếu ứng dụng/chức năng khác chủ động thêm hoặc sửa một `PropertySource`.
- **Properties bean đã được liên kết** có thể tiếp tục giữ những giá trị được lấy ở thời điểm tạo/bind.
- **Service đã nhận properties bean qua constructor** vẫn giữ tham chiếu đến bean được tiêm, không tự thay bằng một object mới.

Vì vậy, khi chẩn đoán hành vi runtime, cần biết **thời điểm lấy giá trị** thay vì chỉ xem tệp cấu hình hiện trên ổ đĩa.

## 22. Kiểm thử riêng từng trách nhiệm

Bạn có thể viết kiểm thử Spring Boot để xác nhận toàn bộ đường đi từ nguồn cấu hình đến service.

Ví dụ:

~~~java
package com.example.reporting;

import com.example.reporting.config.ReportProperties;
import com.example.reporting.service.ReportService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
        "reports.batch-size=25",
        "reports.timeout=3s",
        "reports.endpoint=https://test.example.test",
        "reports.enabled=false"
})
class ReportPropertiesIntegrationTest {

    @Autowired
    ReportProperties properties;

    @Autowired
    ReportService service;

    @Test
    void bindsAndInjectsConfiguration() {
        assertEquals(25, properties.batchSize());
        assertEquals(Duration.ofSeconds(3), properties.timeout());
        assertEquals(25, service.batchSize());
    }
}
~~~

Nếu cấu hình ứng dụng có `@ConfigurationPropertiesScan` và service tương ứng, test này xác nhận cả ba việc:

1. `ReportProperties` **được đăng ký** đủ để Spring inject vào test.
2. Các giá trị từ nguồn kiểm thử **được binder liên kết** đúng kiểu.
3. `ReportService` **nhận được bean** với giá trị mong đợi.

### Tách kiểm thử lỗi binding

Có thể thử đưa `reports.batch-size=not-a-number`. Lần tạo context sẽ thất bại trước khi service được sử dụng, vì binder không chuyển giá trị sang kiểu `int`.

### Tách kiểm thử lỗi đăng ký

Nếu loại bỏ mọi cơ chế đăng ký `ReportProperties`, giữ nguyên service yêu cầu bean, context có thể báo thiếu bean. Đây là bài kiểm thử luồng đăng ký, không phải bài kiểm thử chuyển kiểu.

### Tách kiểm thử DI nhiều ứng viên

Nếu bạn chủ động đăng ký thêm một bean `ReportProperties` cùng kiểu, hãy quan sát lỗi inject mơ hồ rồi đưa ra cách phân biệt đúng chủ đích. Không nên giải quyết bằng một bean ẩn không rõ nguồn gốc.

## 23. Chẩn đoán bằng Environment và công cụ Spring Boot

Với dữ liệu không nhạy cảm, bạn có thể kiểm tra một thuộc tính có hiệu lực:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ReportConfigProbe {

    private final Environment environment;

    ReportConfigProbe(Environment environment) {
        this.environment = environment;
    }

    Integer effectiveBatchSize() {
        return environment.getProperty(
                "reports.batch-size", Integer.class);
    }
}
~~~

Nếu `effectiveBatchSize()` trả 250 nhưng properties bean có 0, hãy điều tra cơ chế đăng ký/binding và tên field. Nếu giá trị từ `Environment` đã khác kỳ vọng, hãy điều tra **nguồn cấu hình và độ ưu tiên** trước.

Spring Boot Actuator có thể cung cấp các endpoint như `/actuator/configprops` và `/actuator/env` khi bạn cài đặt, bật và cấp quyền phù hợp. Chúng hữu ích để quan sát các nhóm thuộc tính và nguồn, nhưng có thể lộ thông tin nhạy cảm. Chỉ dùng trong phạm vi bảo mật phù hợp và dựa vào cơ chế che giấu giá trị.

Không nên in toàn bộ object `@ConfigurationProperties` ra log khi nó có thể chứa mật khẩu, token hoặc thông tin kết nối.

## 24. Các câu hỏi dễ nhầm và lời giải

### Tình huống A — chỉ thêm annotation lên record

~~~java
@ConfigurationProperties(prefix = "payments")
public record PaymentProperties(String merchantId) {
}
~~~

Một service inject `PaymentProperties`, nhưng ứng dụng chưa bật `@ConfigurationPropertiesScan`, chưa dùng `@EnableConfigurationProperties` và không có cơ chế đăng ký nào khác.

**Kết quả mong đợi:** Spring không mặc nhiên có bean `PaymentProperties` chỉ vì class có `@ConfigurationProperties`. Cần đăng ký đúng cơ chế.

### Tình huống B — có bean nhưng không có cấu hình tương ứng

~~~java
@ConfigurationProperties(prefix = "payments")
public record PaymentProperties(String merchantId) {
}
~~~

Ứng dụng đã đăng ký bean đúng cách, nhưng không có `payments.merchant-id` trong bất kỳ nguồn cấu hình nào.

**Kết quả cần hiểu:** Việc đăng ký vẫn là một trách nhiệm riêng. Khi bind, giá trị có thể thiếu hoặc nhận mặc định theo cấu trúc/kiểu Java. Nếu dữ liệu bắt buộc, cần validation hoặc logic xác minh thay vì mặc nhiên cho rằng mọi khóa được yêu cầu đều tồn tại.

### Tình huống C — @Component trên record để có bean

~~~java
@Component
@ConfigurationProperties(prefix = "payments")
public record PaymentProperties(String merchantId) {
}
~~~

**Vấn đề:** Đây là kiểu đăng ký component thường, không phải cách chọn constructor binding chuẩn cho immutable configuration properties. Spring có thể cố dùng constructor như dependency injection, trong khi `merchantId` chỉ là giá trị cấu hình. Nên dùng scanning chuyên biệt hoặc `@EnableConfigurationProperties` cho record.

### Tình huống D — một service cần cả bean cấu hình và bean nghiệp vụ

~~~java
@Service
public class PaymentService {

    private final PaymentProperties properties;
    private final PaymentGateway gateway;

    public PaymentService(
            PaymentProperties properties,
            PaymentGateway gateway) {
        this.properties = properties;
        this.gateway = gateway;
    }
}
~~~

Giả sử cả hai phụ thuộc đã là bean hợp lệ. Đây là DI ở service; `PaymentProperties` chịu binding, còn `PaymentGateway` được đăng ký/tạo theo cơ chế của bean nghiệp vụ.

### Tình huống E — đối tượng bên thứ ba có setter

Bạn không thể sửa mã của lớp `ThirdPartyOptions` để thêm annotation. Tuy nhiên lớp có constructor mặc định và setter cho các thuộc tính.

**Lựa chọn phù hợp:** phương thức `@Bean` tạo `ThirdPartyOptions` và đặt `@ConfigurationProperties(prefix="third-party")` trên phương thức ấy, để binder cập nhật instance trước khi bean được sử dụng.

### Tình huống F — giá trị có trong YAML nhưng không vào service

Hãy lần lượt kiểm tra:

1. `JobProperties` có được đăng ký không?
2. Prefix `jobs` và tên field `batchSize` có ánh xạ đúng `jobs.batch-size` không?
3. Nguồn cấu hình khác có ghi đè giá trị không?
4. Binder có báo lỗi chuyển kiểu hay validation không?
5. Service có đang inject bean đúng kiểu hay có nhiều ứng viên?

Trình tự này phân biệt nguồn dữ liệu, đăng ký, binding và DI.

## 25. Bài thực hành

### Bài 1 — phân loại trách nhiệm

Cho đoạn mã:

~~~java
@ConfigurationProperties(prefix = "mail")
public record MailProperties(String from, int retryCount) {
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(MailProperties.class)
class MailConfig {
}
~~~

~~~java
@Service
class MailService {
    MailService(MailProperties properties) {
    }
}
~~~

Hãy xác định:

- Dòng nào mô tả nhóm khóa dùng để bind?
- Dòng nào yêu cầu đăng ký bean?
- Dòng nào yêu cầu tiêm phụ thuộc?

**Đáp án:** `@ConfigurationProperties` mô tả binding, `@EnableConfigurationProperties` đăng ký, constructor của `MailService` là điểm DI.

### Bài 2 — dùng record với Spring Boot 3.x

Định nghĩa:

~~~java
@ConfigurationProperties(prefix = "storage")
public record StorageProperties(
        String bucket,
        int maxSize) {
}
~~~

Hãy bật đăng ký record bằng `@ConfigurationPropertiesScan` rồi cung cấp:

~~~yaml
storage:
  bucket: files-demo
  max-size: 25
~~~

Tạo `StorageService(StorageProperties properties)`, kiểm tra `properties.bucket()` bằng `files-demo` và `maxSize()` bằng 25.

**Điểm cần nhận ra:** binder dựng record; Spring DI truyền **record đã tạo** vào service.

### Bài 3 — sửa cấu hình đăng ký chưa phù hợp

Đoạn mã:

~~~java
@Component
@ConfigurationProperties(prefix = "storage")
public record StorageProperties(String bucket) {
}
~~~

Mục tiêu là constructor binding cho record.

**Cách sửa:** bỏ `@Component` trên record và đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(StorageProperties.class)`.

### Bài 4 — cấu hình đối tượng mutable

Tạo class có:

~~~java
public class RetryOptions {
    private int maxAttempts = 3;

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }
}
~~~

Sau đó khai báo:

~~~java
@Bean
@ConfigurationProperties(prefix = "client.retry")
RetryOptions retryOptions() {
    return new RetryOptions();
}
~~~

Với:

~~~yaml
client:
  retry:
    max-attempts: 5
~~~

Hỏi ai tạo instance, ai ghi giá trị 5, và ai đưa `RetryOptions` vào service?

**Đáp án:** phương thức `@Bean` tạo instance; configuration binder gọi cơ chế ghi thuộc tính và đặt 5; Spring DI cung cấp bean cho service.

### Bài 5 — dự đoán lỗi

Bạn có:

~~~java
@ConfigurationProperties(prefix = "service")
public record ServiceProperties(int port) {
}
~~~

ứng dụng đã đăng ký đúng bằng `@ConfigurationPropertiesScan`, nhưng YAML ghi:

~~~yaml
service:
  port: abc
~~~

**Đáp án:** đây là lỗi binding/chuyển kiểu vì `abc` không thể chuyển thành `int`. Thêm `@Service` lên một service khác không giải quyết nguyên nhân.

### Bài 6 — ghi đè qua command line

Trong `application.yaml`:

~~~yaml
service:
  port: 8080
~~~

Chạy:

~~~bash
java -jar app.jar --service.port=9191
~~~

Với `@ConfigurationProperties(prefix="service")` và một bean đăng ký đúng, `port` thường nhận 9191 do nguồn CLI ghi đè tệp.

**Điểm cần nhận ra:** thay đổi nguồn giá trị không đồng nghĩa thay đổi cách đăng ký bean hay DI.

### Bài 7 — kiểm thử số lượng bean

Tạo một ứng dụng có một `StorageProperties` và một `StorageService`. Trong test dùng `ApplicationContext`:

~~~java
assertEquals(
        1,
        context.getBeansOfType(StorageProperties.class).size());
~~~

Nếu kết quả lớn hơn một, kiểm tra xem bạn đã đăng ký cùng một kiểu bằng những cơ chế khác nhau hoặc đã tạo thêm factory bean có cùng kiểu hay chưa.

### Bài 8 — yêu cầu validation

Giả sử `service.max-connections` phải lớn hơn hoặc bằng 1.

Hãy định nghĩa record `ServiceProperties` có `@Min(1)` trên tham số `maxConnections`, thêm `@Validated` lên class, đăng ký bean qua `@ConfigurationPropertiesScan` và bổ sung hạ tầng Bean Validation phù hợp.

**Kỳ vọng:** giá trị 0 bị phát hiện khi binding/validation diễn ra, trước khi service hoạt động với một thông số không hợp lệ.

## 26. Bảng ghi nhớ

| Công việc | Công cụ thường dùng | Đầu vào | Kết quả |
| --- | --- | --- | --- |
| Phát hiện/đăng ký properties class | `@ConfigurationPropertiesScan` | Package có lớp được annotate | Bean definition cho properties class. |
| Đăng ký một tập properties class cụ thể | `@EnableConfigurationProperties` | Các class được liệt kê | Bean definition cho các class đó. |
| Tạo bean mutable theo cơ chế Spring thông thường | `@Component` hoặc `@Bean` | Class/factory method | Bean được container quản lý. |
| Liên kết thuộc tính vào object | `@ConfigurationProperties(prefix="...")` + Binder | Giá trị hiệu lực trong `Environment` | Object/fields được điền dữ liệu và chuyển kiểu. |
| Tạo object cấu hình bất biến | Constructor binding | Giá trị cấu hình tương ứng tham số constructor | Record/class bất biến được binder tạo. |
| Liên kết vào object factory tạo ra | `@Bean @ConfigurationProperties` | Bean đã tạo, các setter/thuộc tính ghi được | Bean mutable được gắn cấu hình. |
| Cung cấp properties cho service | Constructor injection | Bean `ReportProperties` đã đăng ký | Service nhận phụ thuộc và sử dụng. |
| Kiểm tra giá trị hợp lệ | `@Validated`, Bean Validation | Object đã bind | Báo lỗi nếu vi phạm constraint. |
| Thay đổi giá trị theo môi trường | Config Data, biến môi trường, CLI | Nguồn cấu hình và thứ tự ưu tiên | Giá trị đầu vào mới cho Binder. |

## 27. Kết luận

Ba hành động **tạo bean**, **liên kết thuộc tính** và **tiêm phụ thuộc** là ba cơ chế liên quan nhưng có ranh giới rõ ràng.

- Bean registration/creation trả lời: *“Đối tượng cấu hình này có tồn tại trong `ApplicationContext` không, và ai tạo nó?”*
- Configuration binding trả lời: *“Những khóa trong `Environment` được chuyển thành các field hoặc tham số constructor như thế nào?”*
- Dependency injection trả lời: *“Bean/service nào nhận được đối tượng cấu hình đã được Spring quản lý?”*

Với một class cấu hình riêng của ứng dụng, cách phổ biến trong Spring Boot là khai báo `@ConfigurationProperties` trên record hoặc POJO, đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, rồi inject bean đó qua constructor của service.

Với đối tượng mutable được tạo qua factory hoặc component scanning, JavaBean binding và `@Bean @ConfigurationProperties` có thể phù hợp hơn. Chọn đúng cách đăng ký và binding sẽ giúp bạn phân biệt được lỗi thiếu bean, lỗi chuyển kiểu, lỗi validation và lỗi DI, thay vì sửa nhầm ở một tầng không liên quan.

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration, Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties).
- [Spring Boot — ConfigurationProperties API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html).
- [Spring Boot — ConfigurationPropertiesScan API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationPropertiesScan.html).
- [Spring Framework — The IoC Container](https://docs.spring.io/spring-framework/reference/core/beans.html).