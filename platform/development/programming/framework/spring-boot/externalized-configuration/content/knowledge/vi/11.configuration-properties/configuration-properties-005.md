# Đăng ký kiểu JavaBean bằng `@Component` và phạm vi áp dụng của `@ConfigurationProperties`

## 1. Mục tiêu và bối cảnh

Spring Boot hỗ trợ **externalized configuration**: các giá trị thay đổi theo môi trường được cung cấp từ `application.properties`, `application.yml`, biến môi trường, system properties, command-line arguments và các nguồn Config Data khác. Khi ứng dụng có nhiều giá trị liên quan, việc đặt hàng loạt `@Value` trên từng trường khiến cấu hình phân tán và khó kiểm tra.

`@ConfigurationProperties` cho phép **liên kết một nhóm property** có chung tiền tố (`prefix`) thành một object Java có kiểu. Một cách đăng ký object này là đặt đồng thời hai annotation trên một lớp JavaBean:

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
    // Các field, getter và setter để Spring Boot binding.
}
~~~

- **`@Component`** làm cho lớp trở thành ứng viên bean của Spring Framework khi phạm vi component scan chứa lớp đó.
- **`@ConfigurationProperties(prefix = "app.mail")`** nói với cơ chế binding của Spring Boot rằng các khóa `app.mail.*` phải được ánh xạ vào các property JavaBean của bean này.
- **JavaBean binding** sử dụng cấu trúc bean và các accessor phù hợp, thường là một constructor không tham số cùng getter/setter.
- Sau khi Spring tạo và bind object, các service khác có thể nhận `MailProperties` qua dependency injection.

Đây là mô hình rất phổ biến đối với ứng dụng Spring Boot sử dụng Java class có trạng thái cấu hình được khai báo bằng field và setter. Nó khác với **constructor binding** cho record hoặc lớp bất biến được đăng ký bằng `@ConfigurationPropertiesScan` hay `@EnableConfigurationProperties`.

## 2. Vai trò của từng annotation

### 2.1. `@Component`: đăng ký bean thông qua component scanning

`@Component` là stereotype của Spring Framework. Khi application context thực hiện component scan, lớp có annotation này được tìm thấy và đăng ký thành một bean definition.

Ví dụ:

~~~java
package com.example.orders.config;

import org.springframework.stereotype.Component;

@Component
public class MailProperties {
}
~~~

Nếu `com.example.orders.config` nằm trong phạm vi component scan, Spring tạo bean `MailProperties`. Theo quy tắc đặt tên mặc định thông dụng, bean có thể mang tên `mailProperties`; ứng dụng nên inject theo kiểu thay vì phụ thuộc vào tên mặc định đó.

Chỉ có `@Component` thì **chưa xác định nhóm property nào sẽ được liên kết**. Cần thêm `@ConfigurationProperties` và các member có thể bind.

### 2.2. `@ConfigurationProperties`: mô tả prefix và binding

~~~java
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
    private String host;
    private int port;

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }

    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }
}
~~~

Annotation này không tự làm bean xuất hiện trong application context chỉ vì class nằm trên classpath. Bean phải được **đăng ký qua một cơ chế thích hợp**. Một trong các cơ chế đó là `@Component` kết hợp component scanning.

Khi Boot nhận được bean như ví dụ trên, Binder sử dụng prefix `app.mail` để tìm các khóa:

~~~properties
app.mail.host=mail.example.test
app.mail.port=2525
~~~

Sau binding, `getHost()` có thể trả `mail.example.test`, `getPort()` trả `2525`.

### 2.3. Hai annotation giải quyết hai trách nhiệm khác nhau

| Thành phần | Trách nhiệm | Không tự bảo đảm |
| --- | --- | --- |
| `@Component` | Cho phép component scan đăng ký bean | Không khai báo prefix hoặc cách bind property |
| `@ConfigurationProperties` | Khai báo prefix và metadata binding | Không tự đăng ký mọi class thành bean |
| Getter/setter JavaBean | Cho phép truy cập và cập nhật property | Không tự nạp dữ liệu từ `Environment` |
| Spring Boot Binder | Chuyển đổi giá trị ngoài ứng dụng vào object | Không tự tạo class ngoài cơ chế đăng ký bean |
| `Environment` | Cung cấp các property sources hiệu lực | Không tự tạo bean hoặc quyết định validation |

Trong ứng dụng Spring Boot được cấu hình thông thường, những cơ chế này phối hợp để tạo bean đã có giá trị cấu hình.

## 3. Ví dụ hoàn chỉnh: JavaBean được đăng ký bằng `@Component`

Giả sử package chính là `com.example.orders`. Cấu trúc dự án:

~~~text
src/main/java/com/example/orders/
├── OrdersApplication.java
├── config/
│   └── MailProperties.java
└── service/
    └── MailSender.java
src/main/resources/
└── application.yml
~~~

### 3.1. Tạo lớp cấu hình có getter/setter

~~~java
package com.example.orders.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private String host = "localhost";
    private int port = 2525;
    private Duration connectTimeout = Duration.ofSeconds(3);
    private boolean enabled = true;

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

Lớp này có constructor không tham số ngầm định vì không tự khai báo constructor khác. Các trường có giá trị mặc định để trường hợp file cấu hình không chỉ định toàn bộ giá trị vẫn có thể tạo object với các default phù hợp.

### 3.2. Định nghĩa cấu hình YAML

~~~yaml
# application.yml
app:
  mail:
    host: smtp.example.test
    port: 587
    connect-timeout: 5s
    enabled: true
~~~

Spring Boot có thể liên kết các giá trị:

| Property nguồn | JavaBean member | Giá trị |
| --- | --- | --- |
| `app.mail.host` | `host` | `smtp.example.test` |
| `app.mail.port` | `port` | `587` |
| `app.mail.connect-timeout` | `connectTimeout` | `Duration.ofSeconds(5)` |
| `app.mail.enabled` | `enabled` | `true` |

Đây là **relaxed binding**: tên `connect-timeout` theo kebab-case trong file cấu hình được liên kết với `connectTimeout` theo camelCase trong Java.

### 3.3. Lớp main nằm ở package cha

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

`@SpringBootApplication` bao gồm `@ComponentScan` theo cấu hình mặc định. Vì `OrdersApplication` nằm trong `com.example.orders`, quá trình quét component sẽ bao gồm package con `com.example.orders.config` và phát hiện `MailProperties`.

Trong cấu trúc này, không cần thêm `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(MailProperties.class)` để đăng ký chính class đã có `@Component`.

### 3.4. Inject cấu hình vào service

~~~java
package com.example.orders.service;

import com.example.orders.config.MailProperties;
import org.springframework.stereotype.Service;

@Service
public class MailSender {

    private final MailProperties mailProperties;

    public MailSender(MailProperties mailProperties) {
        this.mailProperties = mailProperties;
    }

    public String endpoint() {
        return mailProperties.getHost() + ":" + mailProperties.getPort();
    }
}
~~~

Spring inject bean `MailProperties` theo kiểu vào `MailSender`. Lúc sử dụng, các property thông thường đã được bind trong quá trình khởi tạo bean. `MailSender` không phải tự đọc file YAML hay chuyển chuỗi `5s` thành `Duration`.

**Giới hạn ví dụ:** `MailSender` trên chỉ minh họa việc đọc cấu hình; nó không tự tạo kết nối SMTP hoặc gửi email.

## 4. JavaBean binding: tại sao cần getter/setter?

Khi một bean được tạo bởi cơ chế thông thường của Spring, chẳng hạn component scanning qua `@Component`, `@ConfigurationProperties` dùng **JavaBean binding** để thiết lập các trường phù hợp.

Mẫu điển hình:

~~~java
@Component
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private String baseUrl;
    private int retries;

    public String getBaseUrl() { return baseUrl; }
    public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }

    public int getRetries() { return retries; }
    public void setRetries(int retries) { this.retries = retries; }
}
~~~

Cấu hình:

~~~properties
app.client.base-url=https://api.example.test
app.client.retries=3
~~~

Binder liên kết tên khóa với JavaBean property rồi gọi các phương thức setter cần thiết. Getter giúp mã khác đọc giá trị và hỗ trợ các tình huống binding phức tạp.

### 4.1. Constructor không tham số

Nếu không tự khai báo constructor, Java sẽ sinh constructor không tham số cho class thông thường. Spring có thể dùng constructor đó để khởi tạo bean rồi Binder đặt các giá trị thông qua setters.

Có thể khai báo tường minh:

~~~java
public ClientProperties() {
}
~~~

Nếu class chỉ có constructor với các tham số được kỳ vọng lấy từ property, `@Component` **không tự biến constructor đó thành constructor binding**. Spring có thể cố resolve các tham số như dependency injection của bean thông thường. Khi cần constructor binding bất biến, hãy chọn cách đăng ký phù hợp ở phần sau.

### 4.2. Trường không có setter

Với một scalar đơn giản như `String host` hay `int port`, một setter truy cập được là phương án rõ ràng nhất cho JavaBean binding.

Tuy nhiên, đối với một nested object đã được tạo sẵn và có thể cập nhật, Binder có thể sử dụng getter để truy cập object đó mà không cần setter của object cha. Ví dụ:

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private final Security security = new Security();

    public Security getSecurity() {
        return security;
    }

    public static class Security {
        private boolean tlsEnabled;

        public boolean isTlsEnabled() {
            return tlsEnabled;
        }

        public void setTlsEnabled(boolean tlsEnabled) {
            this.tlsEnabled = tlsEnabled;
        }
    }
}
~~~

Cấu hình:

~~~yaml
app:
  mail:
    security:
      tls-enabled: true
~~~

Binder có thể cập nhật `security.tlsEnabled` trên object `Security` đã khởi tạo. Dù field `security` là `final`, các trường bên trong nested object vẫn có thể thay đổi qua setter của chúng.

Đừng suy rộng rằng mọi field `final` đều được bind theo cách setter binding; một scalar bất biến không có setter cần cơ chế khởi tạo khác.

### 4.3. Danh sách và bản đồ

Ví dụ JavaBean:

~~~java
@Component
@ConfigurationProperties(prefix = "app.gateway")
public class GatewayProperties {

    private java.util.List<String> upstreams =
            new java.util.ArrayList<>();

    public java.util.List<String> getUpstreams() {
        return upstreams;
    }

    public void setUpstreams(java.util.List<String> upstreams) {
        this.upstreams = upstreams;
    }
}
~~~

Cấu hình YAML:

~~~yaml
app:
  gateway:
    upstreams:
      - https://api-a.example.test
      - https://api-b.example.test
~~~

Kết quả là một danh sách có hai endpoint. Khi một list được khai báo ở nhiều property sources, hành vi override/binding của danh sách cần xem theo quy tắc Config Data và Binder; không mặc định các phần tử từ tất cả nguồn đều được cộng dồn.

## 5. Phạm vi component scan quyết định `@Component` có được đăng ký không

Một lỗi thường gặp là đặt `@Component` và `@ConfigurationProperties` đúng cú pháp nhưng khởi động bị lỗi:

~~~text
No qualifying bean of type 'com.example.shared.MailProperties'
~~~

Lý do có thể là package chứa class không nằm trong phạm vi component scanning.

### 5.1. Phạm vi mặc định của `@SpringBootApplication`

Ví dụ:

~~~text
com.example.orders
├── OrdersApplication
├── config
│   └── MailProperties
└── service
    └── MailSender
~~~

Nếu `OrdersApplication` nằm trong `com.example.orders`, các class trong package đó và package con thường được component scan tìm thấy.

Nhưng với:

~~~text
com.example.orders
└── OrdersApplication

com.example.shared.config
└── MailProperties
~~~

`MailProperties` có thể nằm ngoài phạm vi quét mặc định. Lúc này, chỉ thêm `@Component` là chưa đủ để Spring đăng ký bean.

### 5.2. Điều chỉnh phạm vi quét khi cần

Có thể cấu hình rõ:

~~~java
@SpringBootApplication(scanBasePackages = {
        "com.example.orders",
        "com.example.shared"
})
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Lúc này component scan có thể phát hiện `MailProperties` trong `com.example.shared.config`.

Tuy nhiên, mở rộng component scan cũng có thể kéo thêm service, controller, configuration hoặc bean khác từ package đó. Nếu chỉ muốn đăng ký **một lớp cấu hình**, có thể cân nhắc đăng ký riêng bằng `@EnableConfigurationProperties` và bỏ `@Component` khỏi lớp properties, thay vì mở rộng phạm vi quét quá rộng.

### 5.3. `@ConfigurationPropertiesScan` là cơ chế quét khác

`@ConfigurationPropertiesScan` tìm và đăng ký các class có `@ConfigurationProperties` chưa được quản lý bởi cơ chế component thông thường. Nó có cách chọn package riêng, ví dụ `@ConfigurationPropertiesScan(basePackages = "com.example.shared.config")`.

**Điểm đặc biệt:** các class được đánh dấu hoặc meta-annotated bằng `@Component` **không phải là đối tượng mà `@ConfigurationPropertiesScan` sẽ đăng ký theo cơ chế scanning riêng của nó**. Nếu đã chọn mô hình `@Component`, cần bảo đảm **component scan** phát hiện class.

Không nên cố chữa một bean `@Component` bị nằm ngoài component scan bằng cách thêm `@ConfigurationPropertiesScan` mà không hiểu hai cơ chế quét. Hai annotation được thiết kế cho các cách đăng ký khác nhau.

## 6. Phạm vi prefix: bind những khóa nào?

Một class được khai báo:

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
    private String host;
    // Getter và setter...
}
~~~

sẽ tìm nhóm khóa có prefix `app.mail`. Ví dụ:

~~~properties
app.mail.host=smtp.example.test
app.mail.port=587
app.payment.host=payment.example.test
~~~

`app.payment.host` thuộc nhóm khác và không tự liên kết với field `host` của `MailProperties`.

Prefix nên dùng dạng **canonical kebab-case**, ví dụ `app.mail` hoặc `app.outbound-mail`. Cấu trúc JavaBean bên trong có thể dùng camelCase và được relaxed binding ánh xạ từ tên property tương ứng.

Một class JavaBean không đại diện cho “toàn bộ file cấu hình”. Nó chỉ nhận nhóm property khớp prefix và tên các thành phần có thể bind. Những property thuộc nhóm không phù hợp hoặc không có member tương ứng thường bị bỏ qua theo các thiết lập binding mặc định, trừ khi có chính sách kiểm tra chặt hơn.

### 6.1. Phạm vi theo application context

Bean `MailProperties` được đăng ký trong **application context** của Spring, không có nghĩa mọi chương trình Java đang chạy trên máy đều chia sẻ cùng một instance. Nếu có nhiều application context độc lập, mỗi context có thể có tập bean và `Environment` riêng.

Trong tình huống thường gặp, `@Component` tạo bean với scope mặc định `singleton`: một instance cho mỗi bean definition trong mỗi Spring container. Các service inject cùng bean sẽ nhìn thấy cùng object cấu hình, trừ khi phạm vi scope hoặc cấu trúc context được thay đổi có chủ đích.

Không hiểu “singleton” thành một instance duy nhất trên toàn bộ JVM hoặc giữa nhiều tiến trình/máy chủ.

### 6.2. `@Profile` và điều kiện đăng ký bean

`@Component` có thể kết hợp với `@Profile` nếu class chỉ được dùng trong một số môi trường:

~~~java
@Component
@Profile("dev")
@ConfigurationProperties(prefix = "app.mock-client")
public class MockClientProperties {
    private String endpoint;
    public String getEndpoint() { return endpoint; }
    public void setEndpoint(String endpoint) { this.endpoint = endpoint; }
}
~~~

Nếu profile `dev` không hoạt động, bean này có thể không được đăng ký. Khi đó, service yêu cầu inject nó mà không có điều kiện tương ứng có thể lỗi vì thiếu bean.

**Khác biệt quan trọng:** `@Profile` quyết định **bean có được tạo hay không**; `@ConfigurationProperties` quyết định **nếu bean được tạo thì các giá trị nào được bind**. Các file `application-dev.yml` và cấu hình có điều kiện là phần xử lý Config Data, không thay thế điều kiện bean.

## 7. JavaBean binding khác constructor binding như thế nào?

Đây là ranh giới quan trọng khi sử dụng `@Component`.

### 7.1. Mô hình mutable JavaBean với `@Component`

~~~java
@Component
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {

    private String host;
    private int port;

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }

    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }
}
~~~

Spring tạo bean theo cơ chế component thông thường rồi Binder gán property thông qua JavaBean setters. Mô hình này đơn giản khi cần dùng bean cùng các thành phần Spring khác, hoặc cần tương thích với một số thư viện dựa trên JavaBean.

### 7.2. Mô hình immutable với constructor binding

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String host, int port) {
}
~~~

Record này có thể được đăng ký bằng:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
}
~~~

Hoặc:

~~~java
@Configuration
@EnableConfigurationProperties(ClientProperties.class)
public class ClientConfiguration {
}
~~~

Trong Spring Boot 3.x, record có một constructor phù hợp thường có thể được constructor-bound mà không cần chú thích `@ConstructorBinding` trên record đó. Đối với nhiều constructor hoặc phiên bản Boot khác, quy tắc và cú pháp có thể khác.

**Không đặt `@Component` lên record để kỳ vọng constructor binding hoạt động như cách đăng ký bằng `@ConfigurationPropertiesScan`.** Constructor của một bean được tạo qua component scanning thông thường thuộc cơ chế dependency injection của Spring. Constructor binding của configuration properties yêu cầu cách đăng ký được Boot hỗ trợ cho mô hình đó.

### 7.3. Bảng so sánh

| Tiêu chí | `@Component` + JavaBean | `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` + constructor binding |
| --- | --- | --- |
| Cách đăng ký | Component scan của Spring | Cơ chế đăng ký configuration properties của Boot |
| Tạo object | Container Spring tạo bean | Binder/Boot tạo object theo constructor phù hợp |
| Thay đổi field | Thường qua setter | Thường qua tham số constructor |
| Mutable/immutable | Dễ dùng mutable bean | Phù hợp record hoặc class bất biến |
| Phạm vi quét | Theo `@ComponentScan` | Theo configuration properties scan hoặc danh sách class |
| Thích hợp khi | JavaBean có getter/setter, cấu hình ứng dụng đơn giản | Muốn immutable config, field bắt buộc qua constructor |
| Nguy cơ | Setter công khai có thể bị gọi ngoài ý muốn | Cần đăng ký đúng và thiết kế constructor rõ ràng |

Chọn một cơ chế nhất quán cho mỗi class; tránh cố sử dụng cả hai mô hình để đăng ký cùng một nhóm cấu hình.

## 8. Khi nào dùng `@EnableConfigurationProperties`?

Có thể bỏ `@Component` và đăng ký lớp JavaBean một cách tường minh:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private String host;
    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }
}
~~~

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(MailProperties.class)
public class MailConfiguration {
}
~~~

`@EnableConfigurationProperties(MailProperties.class)` yêu cầu Boot đăng ký bean configuration properties. Cách này hữu ích khi:

- class nằm ngoài phạm vi component scan của ứng dụng;
- muốn danh sách các class cấu hình được đăng ký rõ ràng tại một configuration class;
- làm starter/autoconfiguration hoặc module cần bật một nhóm cấu hình có chủ đích;
- muốn sử dụng cơ chế constructor binding với class phù hợp.

**Không nhất thiết dùng cả `@Component` và `@EnableConfigurationProperties` cho cùng một class.** Nếu dùng đồng thời các cơ chế đăng ký, có thể tạo ra hai bean cấu hình cùng kiểu nhưng tên khác nhau, dẫn đến inject theo kiểu bị mơ hồ hoặc bean được bind nhiều lần. Khi gặp vấn đề, cần kiểm tra bean definitions và loại bỏ đăng ký trùng.

## 9. Khi nào dùng `@ConfigurationPropertiesScan`?

Nếu dự án có nhiều class cấu hình và muốn tự động đăng ký theo annotation:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
}
~~~

Với các class:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
    // JavaBean hoặc record tùy mô hình binding.
}
~~~

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(String endpoint, int retries) {
}
~~~

Cách này giúp không cần thêm `@Component` trên từng configuration properties class.

Nếu đặt `@ConfigurationPropertiesScan` không có tham số, phạm vi tìm kiếm của nó thường bắt đầu từ package chứa class khai báo annotation và các package con. Có thể cung cấp `basePackages` hoặc `basePackageClasses` khi cần mở rộng phạm vi.

**Không nhầm hai loại scan:**

- `@ComponentScan` tìm các component của Spring như `@Component`, `@Service`, `@Repository`, `@Controller`.
- `@ConfigurationPropertiesScan` tìm các class `@ConfigurationProperties` phù hợp với quy tắc scanning riêng của Boot, không thay thế component scan cho các class có stereotype component.

Vì vậy, nếu chọn mô hình `@Component` + JavaBean, cách ngắn gọn nhất thường là đặt class dưới package gốc của `@SpringBootApplication`.

## 10. `@Bean` + `@ConfigurationProperties`: một lựa chọn khác

Khi cần bind vào một object của thư viện bên thứ ba mà không thể sửa class để thêm annotation, có thể đặt `@ConfigurationProperties` trên method `@Bean`:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClientOptionsConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "app.third-party")
    public ThirdPartyClientOptions thirdPartyOptions() {
        return new ThirdPartyClientOptions();
    }
}
~~~

Ví dụ giả định thư viện cung cấp class `ThirdPartyClientOptions` có JavaBean setters thích hợp. Boot sẽ liên kết các thuộc tính `app.third-party.*` vào object trả về từ `@Bean`.

Đây là cơ chế bind kiểu JavaBean cho một bean do Spring tạo; nó **không biến object đó thành constructor-bound configuration properties**. Mô hình phù hợp khi không sở hữu mã nguồn class hoặc khi phải khởi tạo object bằng một factory method.

So với `@Component`, cách `@Bean` mang lại quyền kiểm soát tường minh về cách tạo object, nhưng dài hơn khi chỉ có một JavaBean cấu hình đơn giản do ứng dụng sở hữu.

## 11. Relaxed binding trong JavaBean

Spring Boot Binder hỗ trợ nhiều biến thể tên property, giúp cấu hình từ các nguồn khác nhau đều ánh xạ về tên trường Java.

Giả sử lớp có:

~~~java
private Duration connectTimeout;

public Duration getConnectTimeout() {
    return connectTimeout;
}

public void setConnectTimeout(Duration connectTimeout) {
    this.connectTimeout = connectTimeout;
}
~~~

Một khóa chuẩn trong file là:

~~~properties
app.mail.connect-timeout=3s
~~~

Trong YAML:

~~~yaml
app:
  mail:
    connect-timeout: 3s
~~~

Khi đặt biến môi trường, tên theo quy tắc canonical của Boot có thể là:

~~~text
APP_MAIL_CONNECTTIMEOUT=5s
~~~

Đối với tên canonical `app.mail.connect-timeout`, quy tắc chuyển sang biến môi trường thường là thay dấu chấm bằng underscore, loại dấu gạch nối, rồi viết hoa. Tránh suy đoán rằng mọi cách chèn thêm underscore giữa các từ đều được đối xử giống nhau trong tất cả tình huống.

Binder có thể chuyển đổi một số kiểu thông dụng, ví dụ:

- `String` từ chuỗi.
- `int`, `long` hoặc các wrapper số từ giá trị hợp lệ.
- `boolean` từ biểu diễn boolean hỗ trợ.
- `Duration` từ `3s`, `500ms`, `2m`.
- `DataSize` từ những đơn vị dữ liệu được hỗ trợ.
- `URI`, `URL` và một số kiểu khác thông qua conversion service.
- `List`, `Map` và nested JavaBean khi cấu trúc nguồn phù hợp.

Không phải mọi chuỗi đều chuyển thành công. Nếu giá trị `app.mail.port=not-a-number` được bind vào `int`, startup có thể thất bại do lỗi binding.

## 12. Giá trị mặc định trong JavaBean

Một JavaBean có thể khai báo default ngay trên field:

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private String host = "localhost";
    private int port = 2525;

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }

    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }
}
~~~

Nếu không có `app.mail.host` hoặc `app.mail.port` trong nguồn cấu hình, bean có thể giữ giá trị khởi tạo. Nếu các khóa xuất hiện, Binder thiết lập giá trị được cung cấp.

Cách này khác với default trong placeholder:

~~~properties
app.mail.host=${MAIL_HOST:localhost}
~~~

Ở đây, giá trị `localhost` thuộc biểu thức tham chiếu của file. Còn giá trị mặc định trên field Java chỉ tồn tại trong object được tạo.

Khi default có ý nghĩa vận hành, nên quyết định đặt ở đâu cho dễ quan sát và bảo trì. Với giá trị thật sự bắt buộc, tránh default làm che thiếu cấu hình. Có thể kết hợp validation để ứng dụng từ chối startup khi thiếu hoặc sai giá trị.

### 12.1. Null và primitive

Trường `int port` có mặc định Java là `0` nếu không được khởi tạo. Nếu `port=0` không hợp lệ với nghiệp vụ, chỉ dựa vào primitive có thể khiến lỗi cấu hình không được phát hiện.

Có thể dùng `Integer port` cùng validation `@NotNull` và `@Min(1)`, hoặc thiết lập default hợp lý rồi kiểm tra miền giá trị. Binder không biết port nào hợp lệ với nghiệp vụ nếu ứng dụng không biểu diễn yêu cầu đó.

## 13. Validation cho JavaBean cấu hình

Một trong những lợi ích của `@ConfigurationProperties` là có thể kiểm tra cấu hình sớm, trước khi ứng dụng bắt đầu xử lý công việc thực tế.

Ví dụ với Spring Boot 3.x và Jakarta Bean Validation:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;
import org.springframework.validation.annotation.Validated;

@Component
@Validated
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    @NotBlank
    private String host;

    @Min(1)
    @Max(65535)
    private int port = 2525;

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }

    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }
}
~~~

Với:

~~~properties
app.mail.host=
app.mail.port=70000
~~~

Validation có thể khiến startup thất bại với thông báo liên quan các trường không hợp lệ. Để tích hợp Bean Validation, ứng dụng cần provider và dependency phù hợp, thường là `spring-boot-starter-validation`.

Lợi ích:

1. Phát hiện cấu hình sai trong giai đoạn khởi động.
2. Giữ quy tắc hợp lệ gần class khai báo cấu hình.
3. Hạn chế việc từng service tự kiểm tra những giá trị giống nhau.
4. Làm rõ trường bắt buộc và giới hạn.

### 13.1. Validation object lồng nhau

Nếu có object con:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

@Component
@Validated
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    @Valid
    private final Authentication authentication = new Authentication();

    public Authentication getAuthentication() {
        return authentication;
    }

    public static class Authentication {
        @NotBlank
        private String username;

        public String getUsername() { return username; }
        public void setUsername(String username) {
            this.username = username;
        }
    }
}
~~~

`@Valid` cho phép validation đi sâu vào nested object theo quy tắc Bean Validation. Khi thiết kế cấu hình nhạy cảm như credential, không đưa giá trị thật vào source code hoặc log. Annotation validation kiểm tra dữ liệu, không làm mật khẩu được mã hóa.

### 13.2. Không dùng validation như cơ chế chọn bean

Validation của `@ConfigurationProperties` kiểm tra bean sau khi được tạo và bind. Nó không quyết định một `@Component` có được quét hay không. Muốn bean chỉ tồn tại theo profile, dùng `@Profile` hoặc condition tạo bean; muốn bean luôn tồn tại nhưng buộc giá trị hợp lệ, dùng validation.

## 14. Thứ tự khởi tạo và thời điểm binding

Trong một ứng dụng Spring Boot thông thường, trình tự khái quát:

1. Boot chuẩn bị `Environment` và những Config Data sources phù hợp.
2. Spring container xác định bean definitions từ component scanning và configuration classes.
3. Container khởi tạo bean `MailProperties`.
4. Cơ chế configuration properties binding gán các giá trị thuộc prefix `app.mail` lên object.
5. Validation được thực hiện nếu thiết lập phù hợp.
6. Bean có thể được inject vào những component khác để sử dụng các giá trị đã bind.

Đây là mô hình khái quát; chi tiết lifecycle và các BeanPostProcessor có thể khác theo cấu hình ứng dụng. Người viết code không nên phụ thuộc vào việc các setter được gọi theo một thứ tự cố định giữa các property.

### 14.1. Không ghi logic nghiệp vụ vào setter

Không nên làm những việc như mở kết nối mạng, gửi thông báo hoặc cập nhật database mỗi lần setter của configuration properties được gọi:

~~~java
public void setHost(String host) {
    this.host = host;
    // Không mở kết nối hay thực hiện tác vụ có side effect tại đây.
}
~~~

Setter nên giữ nhiệm vụ cập nhật dữ liệu. Logic sử dụng cấu hình nên nằm trong service hoặc factory bean được khởi tạo sau khi cấu hình đã hợp lệ. Điều này giúp tách giai đoạn binding khỏi side effects.

### 14.2. Không coi JavaBean mutable là cấu hình cập nhật tự động

Sau startup, bean JavaBean vẫn là object Java thông thường. Có setter không có nghĩa Spring Boot tự gọi setter mỗi khi file hoặc biến môi trường thay đổi.

Ví dụ sửa `app.mail.host` trong file ngoài JAR khi tiến trình đang chạy **không tự động** làm `MailProperties.host` đổi. Thông thường cần restart hoặc một cơ chế refresh được thiết kế thêm.

Nếu ứng dụng chủ động gọi setter tại runtime, đó là thay đổi trạng thái bean; các component khác có thể nhìn thấy giá trị mới, nhưng tính nhất quán và concurrency cần được quản lý. Đối với cấu hình ổn định, tránh để các service tùy ý chỉnh sửa cấu hình đang dùng.

## 15. Phạm vi áp dụng trong ứng dụng nhiều module

Ví dụ một dự án có các module:

~~~text
orders-app/
  com.example.orders.OrdersApplication

orders-core/
  com.example.orders.core.OrderService

shared-config/
  com.example.shared.config.MailProperties
~~~

Việc thêm dependency `shared-config` vào classpath **không đảm bảo** `MailProperties` được component scan nếu package nằm ngoài phạm vi của `OrdersApplication`.

Các phương án:

- Đặt application class tại package cha bao trùm các package liên quan khi cấu trúc cho phép.
- Chỉ định `scanBasePackageClasses` / `scanBasePackages` của `@SpringBootApplication` nếu thật sự muốn mở rộng component scan.
- Bỏ `@Component` và đăng ký `MailProperties` tường minh bằng `@EnableConfigurationProperties`.
- Dùng `@ConfigurationPropertiesScan` trên package chứa class không có `@Component`.

Nếu đang phát triển Spring Boot starter dùng lại ở nhiều ứng dụng, đăng ký configuration properties qua auto-configuration và `@EnableConfigurationProperties` thường rõ ràng hơn việc kỳ vọng ứng dụng nhận diện package của starter bằng component scanning mặc định.

### 15.1. Phạm vi của `@SpringBootApplication(scanBasePackages=...)`

Thiết lập `scanBasePackages` chủ yếu điều khiển **component scanning**. Nó không mặc định mở rộng mọi cơ chế khác như entity scanning của JPA hoặc repository scanning. Vì vậy, khi thay đổi package layout, không nên cho rằng mọi subsystem sẽ thay đổi phạm vi quét theo cùng một annotation.

### 15.2. Tránh mở rộng scan quá rộng chỉ để thấy một class

Nếu cấu hình:

~~~java
@SpringBootApplication(scanBasePackages = "com")
~~~

thì ứng dụng có thể phát hiện nhiều component ngoài ý định trong các thư viện hoặc module cùng namespace. Điều này gây lỗi bean trùng, phụ thuộc vòng hoặc khởi tạo thành phần không phù hợp.

Hãy chọn ranh giới package nhỏ, có chủ đích, hoặc dùng đăng ký tường minh cho class cấu hình.

## 16. Những trường hợp không nên dùng `@Component`

### 16.1. Muốn configuration properties immutable

Nếu yêu cầu dữ liệu bất biến sau khi khởi tạo, record hoặc class constructor-bound được đăng ký bằng `@ConfigurationPropertiesScan` / `@EnableConfigurationProperties` thường hợp lý hơn.

~~~java
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(String host, int port) {
}
~~~

Sử dụng constructor binding đúng cách giảm bề mặt thay đổi object sau khởi tạo. Không trộn nó với `@Component` chỉ vì muốn bean được phát hiện tự động.

### 16.2. Class cấu hình đến từ thư viện không thể chỉnh sửa

Nếu không sở hữu class, không thể tùy ý gắn `@Component` và `@ConfigurationProperties`. Dùng `@Bean` với `@ConfigurationProperties` có thể bind một JavaBean của thư viện.

### 16.3. Cần đăng ký có điều kiện trong auto-configuration

Trong starter hoặc auto-configuration, nên cân nhắc `@EnableConfigurationProperties` đi cùng các condition có chủ đích. `@Component` được quét không kiểm soát có thể tạo bean ở những ứng dụng chưa muốn bật tính năng đó.

### 16.4. Chỉ cần một property đơn giản

Khi một bean chỉ cần một giá trị nhỏ và không tạo thành nhóm cấu hình, `@Value("${app.feature.enabled:false}")` có thể đủ. Tuy nhiên, nếu nhóm property ngày càng lớn, chuyển sang `@ConfigurationProperties` giúp cấu trúc rõ hơn.

## 17. Những lỗi thường gặp và cách sửa

### Lỗi 1: Có `@ConfigurationProperties` nhưng không có bean

~~~java
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
    // Không có @Component, không được scan, không được enable.
}
~~~

**Triệu chứng:** inject `MailProperties` bị báo không có bean.

**Sửa:** chọn một cơ chế đăng ký: thêm `@Component` trong package được component scan, hoặc đăng ký bằng `@EnableConfigurationProperties`, hoặc dùng `@ConfigurationPropertiesScan`.

### Lỗi 2: `@Component` nằm ngoài package được quét

~~~text
com.example.orders.OrdersApplication
com.example.external.config.MailProperties
~~~

**Triệu chứng:** annotation đúng nhưng không thấy bean.

**Sửa:** kiểm tra package gốc, component scan và các filter; nếu chỉ cần một configuration properties bean, cân nhắc đăng ký tường minh.

### Lỗi 3: Dùng record với `@Component` rồi mong Boot bind constructor

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(String host, int port) {
}
~~~

**Triệu chứng:** Spring cố resolve các tham số constructor như dependency thông thường, hoặc quá trình tạo bean không đúng kỳ vọng.

**Sửa:** bỏ `@Component`, đăng ký record bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` trong Spring Boot version hỗ trợ.

### Lỗi 4: Thiếu setter cho scalar

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
    private String host;
    public String getHost() { return host; }
}
~~~

**Triệu chứng:** `host` không được bind bằng JavaBean setter như mong đợi.

**Sửa:** thêm setter phù hợp hoặc thay mô hình binding nếu muốn immutable config.

### Lỗi 5: Đăng ký cùng class bằng nhiều cơ chế

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
}
~~~

và đồng thời:

~~~java
@EnableConfigurationProperties(MailProperties.class)
~~~

**Triệu chứng:** có thể xuất hiện nhiều bean cùng kiểu hoặc injection bị mơ hồ.

**Sửa:** chọn một cơ chế đăng ký; nếu dùng component scan, thường không cần enable lại class đó.

### Lỗi 6: Dùng `@ConfigurationPropertiesScan` nhưng class vẫn có `@Component`

**Triệu chứng:** class không được phát hiện theo cách configuration-properties scanning như kỳ vọng.

**Sửa:** hiểu rằng `@ConfigurationPropertiesScan` không đăng ký class `@Component`; bỏ `@Component` để dùng cơ chế đó, hoặc bảo đảm component scanning thường tìm được class.

### Lỗi 7: Prefix hoặc tên property không khớp

~~~java
@ConfigurationProperties(prefix = "app.mail")
~~~

nhưng file có:

~~~properties
app.email.host=smtp.example.test
~~~

**Triệu chứng:** bean được tạo nhưng field giữ default hoặc null.

**Sửa:** dùng đúng `app.mail.host`, kiểm tra relaxed binding và nguồn property thực sự được Boot nạp.

### Lỗi 8: Đọc bean quá sớm hoặc tự `new` object

~~~java
MailProperties properties = new MailProperties();
~~~

Object trên không do Spring container quản lý nên không tự được Boot bind chỉ vì class có annotation. Sử dụng constructor injection của bean đã đăng ký hoặc dùng Binder API tường minh nếu xây object ngoài context.

### Lỗi 9: Thêm `@Scope("prototype")` rồi mong giống singleton

`@Component` mặc định là singleton, nhưng Spring cho phép scope khác. Nếu đặt scope không mặc định, thời điểm tạo bean và số instance có thể thay đổi, khiến việc chia sẻ cấu hình giữa service không còn như ví dụ singleton.

Chỉ thay scope khi có yêu cầu thực tế; configuration properties thường được dùng như bean cấu hình ổn định của context.

### Lỗi 10: Thiếu Bean Validation provider

Khi dùng `@Validated` và Jakarta constraints mà môi trường không có Bean Validation provider tương ứng, cấu hình validation có thể không hoạt động như mong đợi hoặc gặp lỗi. Cần đưa dependency phù hợp với Boot version, thường là `spring-boot-starter-validation`.

## 18. Kiểm thử việc component scan và binding

Một bài kiểm thử tích hợp Spring Boot có thể chứng minh bean được đăng ký và nhận đúng giá trị.

Giả sử `MailProperties` trong ví dụ `app.mail` đã có `@Component`, getter/setter và nằm trong phạm vi quét của application class:

~~~java
import com.example.orders.config.MailProperties;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(properties = {
    "app.mail.host=mail.test.example",
    "app.mail.port=2526",
    "app.mail.connect-timeout=750ms"
})
class MailPropertiesTest {

    @Autowired
    MailProperties properties;

    @Test
    void bindsProperties() {
        assertNotNull(properties);
        assertEquals("mail.test.example", properties.getHost());
        assertEquals(2526, properties.getPort());
        assertEquals(java.time.Duration.ofMillis(750),
                     properties.getConnectTimeout());
    }
}
~~~

Cần dependency Spring Boot Test và JUnit phù hợp. Vì test dùng Spring application context, ví dụ cũng phụ thuộc vào việc package của `MailProperties` có được scan hay không.

### 18.1. Test khi bean không được quét

Nếu đưa `MailProperties` ra ngoài phạm vi component scan, context có thể không inject được bean. Đây là dấu hiệu cần kiểm tra phạm vi quét và cách đăng ký bean, không phải lỗi vì Binder không hiểu tên `app.mail.host`.

### 18.2. Test validation

Khi `@Validated` và constraints được bật, có thể đưa vào giá trị thiếu hoặc sai để xác minh ứng dụng thất bại ngay ở startup. Loại ngoại lệ có thể được Spring Boot bọc qua nhiều lớp; trong test nên kiểm tra thông điệp và nguyên nhân tương ứng với field cấu hình hơn là phụ thuộc một chuỗi thông báo duy nhất ở mọi phiên bản.

### 18.3. Test binding và test nghiệp vụ là hai việc khác nhau

Kiểm thử `MailProperties` chứng minh cơ chế binding và registration. Việc kết nối SMTP hoặc gửi email thực tế cần test khác, vì một URL hoặc port được bind hợp lệ chưa bảo đảm có thể kết nối tới hệ thống ngoài.

## 19. Quy trình chẩn đoán khi bean không nhận giá trị

Khi thấy một `@Component` + `@ConfigurationProperties` bean nhận null hoặc default khác mong đợi, đi theo trình tự:

1. **Kiểm tra bean có tồn tại không.** Nếu inject báo không có bean, xem component scanning trước; đừng vội chỉnh YAML.
2. **Kiểm tra package.** Application class nằm ở đâu? Class properties có thuộc package được scan không? Có filter hoặc điều kiện `@Profile` không?
3. **Kiểm tra annotation.** Có đủ `@Component` và `@ConfigurationProperties(prefix = "...")` trong mô hình JavaBean không?
4. **Kiểm tra class JavaBean.** Có constructor phù hợp, getter/setter cho scalar và cấu trúc nested object phù hợp không?
5. **Kiểm tra prefix.** `app.mail` có trùng với prefix trong file và biến môi trường không?
6. **Kiểm tra dữ liệu nguồn.** File `application.properties`/YAML có thực sự được nạp? Có profile hoặc location override làm đổi nguồn không?
7. **Kiểm tra mức ưu tiên.** Biến môi trường, JVM system property hoặc command-line argument có ghi đè file không?
8. **Kiểm tra tên relaxed binding.** Với `connectTimeout`, sử dụng `connect-timeout` trong file và dạng biến môi trường đúng quy ước.
9. **Kiểm tra lỗi chuyển kiểu.** `Duration` cần giá trị hợp lệ như `750ms`, `5s`; port phải chuyển được thành số.
10. **Kiểm tra validation.** Nếu có `@NotBlank`/`@Min`, lỗi binding/validation có thể xuất hiện sớm khi tạo context.
11. **Kiểm tra đăng ký trùng.** Có đồng thời `@Component`, `@EnableConfigurationProperties` và các `@Bean` cùng loại không?
12. **Kiểm tra thời điểm.** Một instance tạo bằng `new` hoặc sử dụng ngoài Spring context sẽ không được binder tự động xử lý.
13. **Kiểm tra thay đổi lúc runtime.** Sửa file khi ứng dụng đang chạy không tự cập nhật bean.
14. **Quan sát an toàn.** Nếu dùng Actuator `/actuator/configprops` hoặc `/actuator/env`, bảo vệ endpoint và che giá trị nhạy cảm.

Với dự án có nhiều cấu hình, annotation processor `spring-boot-configuration-processor` có thể cung cấp metadata cho IDE và hỗ trợ autocomplete các property. Processor này **không thay thế** `@Component`, `@EnableConfigurationProperties` hoặc binder lúc runtime.

## 20. Phân biệt các phạm vi “áp dụng”

Khi nói “`@Component` đăng ký JavaBean trong phạm vi nào?”, có ít nhất bốn phạm vi cần phân biệt:

| Phạm vi | Điều gì quyết định? | Ý nghĩa |
| --- | --- | --- |
| Phạm vi **component scan** | Vị trí `@SpringBootApplication`, `@ComponentScan`, package và filter | Class có được Spring phát hiện để tạo bean không |
| Phạm vi **prefix binding** | `@ConfigurationProperties(prefix="app.mail")` | Nhóm khóa cấu hình nào được đưa vào object |
| Phạm vi **bean scope** | Mặc định singleton; `@Scope` nếu thay đổi | Có bao nhiêu instance và vòng đời trong một context |
| Phạm vi **Config Data** | File location, profile, import, property-source precedence | Giá trị cuối cùng đến từ đâu và có được nạp không |

Một lỗi ở bất kỳ phạm vi nào cũng có thể làm cấu hình không hoạt động như mong đợi. Chẳng hạn:

- Không được scan: **không có bean**.
- Có bean nhưng prefix sai: **bean tồn tại nhưng không được bind giá trị đúng**.
- Prefix đúng nhưng giá trị bị source khác ghi đè: **bean có giá trị khác file đang nhìn**.
- Scope thay đổi: **các service có thể nhận các instance khác nhau**.
- Thay Config Data sau startup: **bean hiện tại không tự đổi**.

Tách bốn câu hỏi này giúp debug có trình tự thay vì thêm annotation tùy ý.

## 21. Hướng dẫn lựa chọn cơ chế đăng ký

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Ứng dụng nhỏ, JavaBean có setter, class nằm trong component scan | `@Component` + `@ConfigurationProperties` |
| Muốn JavaBean vẫn được đăng ký dù ở ngoài component scan | `@EnableConfigurationProperties` |
| Có nhiều properties class không phải Spring component | `@ConfigurationPropertiesScan` |
| Muốn immutable record hoặc constructor binding | `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, không thêm `@Component` |
| Muốn bind class của thư viện bên thứ ba | `@Bean` + `@ConfigurationProperties` |
| Cần bean chỉ ở profile cụ thể | Kết hợp điều kiện đăng ký bean, ví dụ `@Profile` |
| Muốn kiểm tra dữ liệu lúc startup | `@Validated` và Bean Validation phù hợp |
| Chỉ cần một khóa đơn giản | Có thể dùng `@Value`; xem lại khi nhóm cấu hình mở rộng |

Không có cơ chế duy nhất tốt cho mọi tình huống. Với đề bài này, lựa chọn cốt lõi là **JavaBean mutable có `@Component`, được component scan phát hiện, rồi Binder liên kết thuộc tính theo prefix**.

## 22. Ghi nhớ

1. `@Component` đăng ký một Spring bean khi class nằm trong **phạm vi component scan**.
2. `@ConfigurationProperties(prefix = "...")` khai báo **nhóm property** được Binder ánh xạ vào bean.
3. Với bean tạo theo cơ chế `@Component`, **JavaBean binding** là mô hình phù hợp: constructor không tham số và getter/setter rõ ràng cho các trường scalar.
4. Nested mutable object đã khởi tạo sẵn có thể được bind thông qua getter; không suy rằng mọi trường `final` đều bind được theo setter.
5. Component scan và configuration-properties scan là **hai cơ chế khác nhau**; `@ConfigurationPropertiesScan` không tự đăng ký class có `@Component` qua cơ chế scan riêng của nó.
6. Không dùng `@Component` để kỳ vọng constructor binding vào record hoặc class bất biến.
7. Không cần kết hợp `@Component` với `@EnableConfigurationProperties` chỉ để đăng ký lại cùng class.
8. Prefix binding, component scan, bean scope và property-source precedence là bốn phạm vi ảnh hưởng khác nhau.
9. `@Validated` giúp phát hiện cấu hình sai nhưng cần Bean Validation provider; `@ConfigurationProperties` không tự làm mọi chuỗi hợp lệ.
10. Bean cấu hình mặc định là singleton trong application context và thông thường không tự refresh khi file thay đổi.

### Tài liệu tham khảo

- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot Reference — Enabling Configuration-annotated Types](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Framework Reference — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)
- [Spring Boot API — ConfigurationProperties](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
