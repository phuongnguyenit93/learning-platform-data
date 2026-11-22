# Đăng ký cùng chức năng bằng component scan và Java configuration

Spring Boot có nhiều cách đưa một object vào Spring IoC container. Hai cách thường gặp nhất là:

- **Component scan:** đánh dấu class bằng stereotype như `@Component`, `@Service`, `@Repository` hoặc `@Controller`; Spring tìm class trong phạm vi scan và đăng ký bean.
- **Java configuration:** khai báo một method `@Bean` trong class `@Configuration`; Spring gọi factory method và đăng ký object mà method trả về.

Cả hai cách có thể đăng ký một chức năng giống nhau. Ví dụ, một ứng dụng cần `MessageFormatter` để định dạng lời chào. Ta có thể để Spring tìm `DefaultMessageFormatter` qua component scan, hoặc khai báo rõ object đó bằng `@Bean`.

Điểm quan trọng là **đăng ký bean và thực hiện chức năng là hai việc khác nhau**. Component scan và Java configuration là hai cách mô tả object nào thuộc container, dependency nào cần được cung cấp và lifecycle nào Spring quản lý. Chúng không làm thay đổi logic nghiệp vụ của object nếu cùng tạo ra một implementation với cùng dependency và cấu hình.

Bài học này thực hành hai cách đăng ký tương đương, phân tích điểm khác nhau, cách kết hợp chúng trong một ứng dụng, cách tránh tạo hai bean cùng chức năng ngoài ý muốn và cách kiểm tra kết quả bằng Spring Boot tests.

## 1. Mục tiêu và mô hình bài thực hành

Giả sử ứng dụng cần một chức năng định dạng thông điệp:

```text
WelcomeController
        |
        v
WelcomeService
        |
        v
MessageFormatter
        |
        v
DefaultMessageFormatter
```

`WelcomeService` chỉ cần contract `MessageFormatter`. Nó không cần biết object được đăng ký nhờ component scan hay `@Bean`.

Ta sẽ thực hiện hai phương án:

**Phương án A — Component scan**

```java
@Component
public class DefaultMessageFormatter implements MessageFormatter {
    // ...
}
```

Spring tìm class và tạo bean.

**Phương án B — Java configuration**

```java
@Configuration(proxyBeanMethods = false)
public class MessageConfiguration {

    @Bean
    MessageFormatter messageFormatter() {
        return new DefaultMessageFormatter();
    }
}
```

Spring gọi factory method và đăng ký object được trả về.

Hai phương án là **lựa chọn thay thế cho cùng một bean** trong ví dụ này. Nếu cùng bật cả hai mà không có chủ đích, ứng dụng có thể có hai bean cùng implement `MessageFormatter`, dẫn tới injection ambiguity hoặc bean name conflict.

## 2. Bean là gì trong Spring?

Bean là object được Spring IoC container khởi tạo, cấu hình và quản lý lifecycle theo metadata đã đăng ký.

Ví dụ:

```java
@Component
public class WelcomeService {
}
```

Class `WelcomeService` là một kiểu Java. Khi component scan tìm thấy class và Spring đăng ký bean definition, container có thể tạo instance và quản lý instance đó.

Một object được tạo bằng `new` trong bất kỳ method nào không tự động trở thành Spring bean:

```java
WelcomeService service = new WelcomeService();
```

Object này do đoạn code hiện tại tự tạo và sở hữu. Spring không tự động inject dependency, apply bean post-processors hoặc gọi destroy callback cho nó.

### 2.1. Bean definition và bean instance

Có thể phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Class | Kiểu Java, ví dụ `DefaultMessageFormatter` |
| Bean definition | Metadata mô tả bean cần tạo, scope, dependencies và các thuộc tính liên quan |
| Bean instance | Object thực tế được tạo trong container |
| Bean name | Tên dùng để tra cứu bean trong container |
| Dependency | Bean hoặc giá trị được cung cấp cho bean khác |

Component scan và `@Bean` đều có thể tạo bean definitions. Chúng khác nhau ở cách khai báo metadata và cách Spring xác định object cần tạo.

### 2.2. Vì sao có hai cách đăng ký?

Component scan thuận tiện khi class thuộc code của ứng dụng và có thể gắn stereotype.

Java configuration phù hợp khi:

- Class đến từ thư viện bên ngoài và không thể sửa source.
- Cần gọi constructor/factory method với đối số cụ thể.
- Muốn chọn implementation theo cấu hình.
- Cần tạo một bean từ nhiều dependency.
- Muốn kiểm soát rõ bean name, scope, init/destroy method.
- Muốn giữ class domain hoặc class thư viện không phụ thuộc Spring annotations.

Không có một cách duy nhất luôn tốt hơn. Hãy chọn cách diễn đạt ownership và composition rõ ràng nhất.

## 3. Chuẩn bị project Spring Boot

Ví dụ sử dụng Spring Boot project có dependency phù hợp, Java version tương thích và build tool đã được cấu hình.

Một cấu trúc package đơn giản:

```text
com.example.welcome
├── WelcomeApplication.java
├── api
│   └── WelcomeController.java
├── application
│   └── WelcomeService.java
└── formatting
    ├── MessageFormatter.java
    └── DefaultMessageFormatter.java
```

Application class:

```java
package com.example.welcome;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WelcomeApplication {

    public static void main(String[] args) {
        SpringApplication.run(WelcomeApplication.class, args);
    }
}
```

`@SpringBootApplication` kết hợp các chức năng cấu hình Spring Boot, auto-configuration và component scanning. Component scan mặc định bắt đầu từ package của application class và đi xuống các package con.

Vì `api`, `application` và `formatting` đều là package con của `com.example.welcome`, các stereotype trong những package này có thể được tìm thấy.

## 4. Tạo contract cho chức năng

Tạo interface:

```java
package com.example.welcome.formatting;

public interface MessageFormatter {

    String format(String name);
}
```

Interface mô tả hành vi mà client cần: nhận một tên và trả về thông điệp đã định dạng.

Implementation:

```java
package com.example.welcome.formatting;

public class DefaultMessageFormatter implements MessageFormatter {

    @Override
    public String format(String name) {
        String normalizedName =
                name == null || name.isBlank()
                        ? "Guest"
                        : name.trim();

        return "Hello, " + normalizedName + "!";
    }
}
```

Ở thời điểm này, class chưa có annotation Spring. Đây là class Java thông thường, có thể được tạo trực tiếp trong unit test hoặc được Spring đăng ký qua Java configuration.

### 4.1. Logic không phụ thuộc cách đăng ký

Method `format()` không biết:

- Có component scan hay không.
- Bean name là gì.
- Object được tạo bởi `@Component` hay `@Bean`.
- Application đang dùng profile nào.

Đây là một đặc điểm tốt: logic định dạng độc lập với cơ chế wiring.

## 5. Phương án A: đăng ký bằng component scan

Để Spring tìm implementation, thêm stereotype:

```java
package com.example.welcome.formatting;

import org.springframework.stereotype.Component;

@Component
public class DefaultMessageFormatter implements MessageFormatter {

    @Override
    public String format(String name) {
        String normalizedName =
                name == null || name.isBlank()
                        ? "Guest"
                        : name.trim();

        return "Hello, " + normalizedName + "!";
    }
}
```

Khi application context khởi động:

1. Spring thực hiện component scan trong phạm vi đã cấu hình.
2. Phát hiện `DefaultMessageFormatter` có `@Component`.
3. Đăng ký bean definition.
4. Tạo bean theo scope và lifecycle.
5. Bean có thể được inject vào các collaborator cần `MessageFormatter`.

### 5.1. Bean name mặc định

Với stereotype class:

```java
@Component
public class DefaultMessageFormatter {
}
```

Bean name mặc định thường là tên class viết thường chữ đầu:

```text
defaultMessageFormatter
```

Có thể đặt tên rõ ràng:

```java
@Component("welcomeMessageFormatter")
public class DefaultMessageFormatter {
}
```

Không nên đặt tên bean theo thói quen nếu không có nhu cầu tra cứu hoặc phân biệt cụ thể. Khi inject theo type với một ứng viên duy nhất, thường không cần biết bean name.

### 5.2. Các stereotype phổ biến

| Annotation | Vai trò thường dùng |
| --- | --- |
| `@Component` | Component tổng quát do Spring quản lý |
| `@Service` | Component ở tầng service/application |
| `@Repository` | Component ở tầng persistence; có thể tham gia exception translation |
| `@Controller` | Spring MVC controller trả view |
| `@RestController` | Controller có response body mặc định |
| `@Configuration` | Class khai báo cấu hình bean và các cấu hình Spring |

`@Service`, `@Repository`, `@Controller` là những stereotype chuyên biệt trong hệ sinh thái Spring. Chúng đều có thể được component scan phát hiện.

### 5.3. Component scan không quét toàn bộ máy tính

Spring không tự tìm mọi class trong mọi package của mọi dependency. Phạm vi scan được xác định bởi:

- Package chứa class cấu hình scan mặc định.
- `@ComponentScan` và các base packages được chỉ định.
- Include/exclude filters.
- Điều kiện và metadata của class.

Nếu implementation nằm ngoài package gốc, có thể cần cấu hình scan hoặc import rõ ràng.

## 6. Inject implementation qua interface

Tạo service:

```java
package com.example.welcome.application;

import com.example.welcome.formatting.MessageFormatter;
import org.springframework.stereotype.Service;

@Service
public class WelcomeService {

    private final MessageFormatter formatter;

    public WelcomeService(MessageFormatter formatter) {
        this.formatter = formatter;
    }

    public String welcome(String name) {
        return formatter.format(name);
    }
}
```

`WelcomeService` sử dụng constructor injection. Spring tìm một bean phù hợp với kiểu `MessageFormatter` rồi truyền vào constructor.

Với phương án A, bean được tìm thấy là `DefaultMessageFormatter`.

### 6.1. Không cần tự gọi constructor

Không làm:

```java
@Service
public class WelcomeService {

    private final MessageFormatter formatter =
            new DefaultMessageFormatter();
}
```

Đoạn code này tự tạo implementation, bỏ qua việc Spring quản lý dependency đó. Nếu formatter cần một bean khác, proxy, configuration hoặc lifecycle callback, object tự tạo sẽ không được wiring theo cách của container.

### 6.2. Constructor injection làm dependency rõ ràng

```java
public WelcomeService(MessageFormatter formatter) {
    this.formatter = formatter;
}
```

Constructor cho biết service không thể hoạt động nếu thiếu formatter. Với dependency bắt buộc, đây thường là lựa chọn rõ ràng hơn field injection.

## 7. Tạo REST endpoint để quan sát chức năng

```java
package com.example.welcome.api;

import com.example.welcome.application.WelcomeService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WelcomeController {

    private final WelcomeService welcomeService;

    public WelcomeController(WelcomeService welcomeService) {
        this.welcomeService = welcomeService;
    }

    @GetMapping("/welcome")
    public String welcome(
            @RequestParam(defaultValue = "Guest") String name) {
        return welcomeService.welcome(name);
    }
}
```

Chạy ứng dụng và gọi:

```http
GET /welcome?name=Lan
```

Response:

```text
Hello, Lan!
```

Gọi:

```http
GET /welcome
```

Response:

```text
Hello, Guest!
```

Luồng gọi:

```text
HTTP request
    |
    v
WelcomeController
    |
    v
WelcomeService
    |
    v
MessageFormatter bean
    |
    v
DefaultMessageFormatter.format(...)
```

Controller và service không cần biết formatter được đăng ký bằng cách nào.

## 8. Phương án B: đăng ký cùng chức năng bằng Java configuration

Bây giờ giả sử `DefaultMessageFormatter` là class thư viện hoặc class không muốn gắn annotation Spring. Ta bỏ `@Component` và đăng ký object qua `@Bean`.

Class implementation giữ nguyên:

```java
package com.example.welcome.formatting;

public class DefaultMessageFormatter implements MessageFormatter {

    @Override
    public String format(String name) {
        String normalizedName =
                name == null || name.isBlank()
                        ? "Guest"
                        : name.trim();

        return "Hello, " + normalizedName + "!";
    }
}
```

Tạo configuration:

```java
package com.example.welcome.config;

import com.example.welcome.formatting.DefaultMessageFormatter;
import com.example.welcome.formatting.MessageFormatter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MessageConfiguration {

    @Bean
    public MessageFormatter messageFormatter() {
        return new DefaultMessageFormatter();
    }
}
```

Spring phát hiện `MessageConfiguration` qua component scan vì class nằm trong package con của application class. Khi xử lý configuration, Spring đăng ký bean từ method `messageFormatter()`.

### 8.1. `@Configuration` và `@Bean`

- `@Configuration` đánh dấu class chứa các khai báo cấu hình.
- `@Bean` đánh dấu method cung cấp một object cho Spring container.
- Giá trị trả về của method trở thành bean do Spring quản lý.
- Bean name mặc định là tên method, trong ví dụ là `messageFormatter`.

Client vẫn inject:

```java
public WelcomeService(MessageFormatter formatter) {
    this.formatter = formatter;
}
```

Không cần thay đổi `WelcomeService`.

### 8.2. Vì sao `@Bean` trả về interface?

Method khai báo:

```java
@Bean
public MessageFormatter messageFormatter() {
    return new DefaultMessageFormatter();
}
```

Spring biết bean cung cấp contract `MessageFormatter`. Khi cần inject theo type, container dùng kiểu object thực tế và metadata của bean để resolve dependency.

Khai báo return type là interface thể hiện contract mà client cần. Nếu configuration hoặc framework cần truy cập một method đặc thù của implementation ở giai đoạn tạo bean, có thể cần khai báo kiểu cụ thể; hãy chọn kiểu trả về phù hợp với nhu cầu wiring và API.

### 8.3. Bean name từ method

Trong:

```java
@Bean
public MessageFormatter messageFormatter() {
    return new DefaultMessageFormatter();
}
```

Tên bean mặc định là:

```text
messageFormatter
```

Có thể chỉ định:

```java
@Bean("welcomeFormatter")
public MessageFormatter messageFormatter() {
    return new DefaultMessageFormatter();
}
```

Method name và bean name có thể khác nhau. Nếu có nhiều tên alias:

```java
@Bean({"welcomeFormatter", "defaultFormatter"})
public MessageFormatter messageFormatter() {
    return new DefaultMessageFormatter();
}
```

Hai tên trên cùng tham chiếu một bean definition, không tạo hai instance riêng chỉ vì có hai alias.

## 9. Hai phương án có cùng kết quả như thế nào?

Trong ví dụ này:

| Nội dung | Component scan | Java configuration |
| --- | --- | --- |
| Class implementation | `DefaultMessageFormatter` | `DefaultMessageFormatter` |
| Khai báo đăng ký | `@Component` | Method `@Bean` |
| Nơi Spring tìm thấy | Component scan | Configuration class được đăng ký |
| Bean type | `MessageFormatter` | `MessageFormatter` |
| Hành vi `format("Lan")` | `Hello, Lan!` | `Hello, Lan!` |
| Client inject | `WelcomeService` | `WelcomeService` |
| Bean lifecycle | Spring quản lý | Spring quản lý |
| Cách tạo object | Spring instantiate component | Factory method trả object |

Nếu object, dependency và cấu hình tương đương, chức năng mà client quan sát được có thể giống nhau.

Điều thay đổi chủ yếu là **nơi và cách khai báo object thuộc container**.

### 9.1. Component scan thiên về discovery

Class tự khai báo vai trò là Spring component:

```java
@Component
public class DefaultMessageFormatter {
}
```

Spring tìm và đăng ký class theo phạm vi scan.

### 9.2. Java configuration thiên về explicit assembly

Configuration class nói rõ:

```java
@Bean
MessageFormatter messageFormatter() {
    return new DefaultMessageFormatter();
}
```

Người đọc có thể thấy rõ object được tạo ra ở đâu và dependencies nào được truyền vào factory method.

### 9.3. Client không nên phụ thuộc vào cơ chế đăng ký

Nếu cần đổi từ component scan sang Java configuration, lý tưởng là không phải sửa service và controller. Chỉ thay nơi khai báo bean, giữ contract và behavior.

Đây là một cách kiểm tra xem application layer có đang phụ thuộc quá sâu vào cơ chế tạo object hay không.

## 10. Không đăng ký cùng một implementation bằng cả hai cách ngoài ý muốn

Một lỗi thường gặp là giữ `@Component` trên class, đồng thời khai báo thêm `@Bean` tạo một instance mới:

```java
@Component
public class DefaultMessageFormatter implements MessageFormatter {
}
```

```java
@Configuration(proxyBeanMethods = false)
public class MessageConfiguration {

    @Bean
    MessageFormatter anotherFormatter() {
        return new DefaultMessageFormatter();
    }
}
```

Khi cả hai cùng được nạp, container có thể có:

```text
defaultMessageFormatter
anotherFormatter
```

Cả hai đều implement `MessageFormatter`.

Constructor:

```java
public WelcomeService(MessageFormatter formatter) {
    this.formatter = formatter;
}
```

có thể gặp `NoUniqueBeanDefinitionException` vì có hai bean phù hợp.

### 10.1. Tên bean khác nhau không làm chúng trở thành một bean

```text
defaultMessageFormatter -> instance A
anotherFormatter        -> instance B
```

Hai bean name khác nhau thường có nghĩa hai bean definitions khác nhau. Đừng nghĩ Spring tự nhận ra chúng cùng class rồi gộp lại.

### 10.2. Cùng bean name có thể gây conflict

Nếu component có tên `messageFormatter` và `@Bean` method cũng tên `messageFormatter`, hai đăng ký có thể xung đột. Hành vi xử lý bean definition overriding phụ thuộc cấu hình và phiên bản; Spring Boot thường không bật bean definition overriding mặc định trong các cấu hình thông dụng.

Không dựa vào thứ tự scan hoặc cơ chế override để quyết định implementation. Hãy đăng ký một nguồn rõ ràng cho mỗi bean name và mỗi contract bắt buộc.

### 10.3. Cách chuyển từ component scan sang `@Bean`

Khi chuyển:

1. Bỏ stereotype annotation khỏi implementation nếu không muốn component scan tự đăng ký nó.
2. Thêm `@Bean` method trong configuration class.
3. Giữ nguyên contract và client injection.
4. Khởi động context để xác nhận chỉ có bean mong muốn.
5. Test behavior qua client.

Không cần sửa logic `format()` chỉ vì đổi cách đăng ký.

### 10.4. Khi nào cố ý cần hai implementation?

Nếu hai bean có vai trò khác nhau, ví dụ formatter tiếng Anh và tiếng Việt, việc có hai bean là hợp lệ. Khi đó client cần lựa chọn rõ ràng bằng qualifier, primary hoặc một strategy router.

Vấn đề không phải “nhiều bean luôn sai”, mà là **nhiều ứng viên nhưng client không có quy tắc chọn rõ ràng**.

## 11. Đăng ký class thư viện bên ngoài bằng `@Bean`

Một lý do quan trọng để dùng Java configuration là không thể thêm `@Component` vào class bên ngoài.

Giả sử dependency cung cấp:

```java
package com.vendor.mail;

public class VendorMailClient {

    public VendorMailClient(String endpoint, int timeoutMillis) {
        // ...
    }

    public void send(String recipient, String content) {
        // ...
    }

    public void close() {
        // Release resources
    }
}
```

Bạn không sở hữu source class này và không thể thêm `@Component`.

Tạo configuration:

```java
@Configuration(proxyBeanMethods = false)
public class MailClientConfiguration {

    @Bean(destroyMethod = "close")
    public VendorMailClient vendorMailClient(
            MailProperties properties) {

        return new VendorMailClient(
                properties.endpoint(),
                properties.timeoutMillis()
        );
    }
}
```

Spring gọi factory method, truyền `MailProperties` đã được bind, đăng ký client và gọi destroy method khi bean được đóng theo lifecycle.

### 11.1. Khi nào dùng component scan cho class bên ngoài?

Nếu thư viện đã cung cấp configuration class hoặc auto-configuration, có thể import hoặc bật theo tài liệu của thư viện.

Không phải class nào trong dependency cũng cần hoặc có thể được component scan đăng ký. Nhiều thư viện chỉ cung cấp POJO/client factory; Java configuration là cách lắp ghép phù hợp.

### 11.2. Giữ class thư viện độc lập Spring

Đăng ký bằng `@Bean` giúp class bên ngoài không cần phụ thuộc Spring annotations. Điều này hữu ích khi:

- Thư viện được dùng ở nhiều framework.
- Class là domain object hoặc client thuần Java.
- Không thể sửa source.
- Muốn giữ cấu hình tích hợp tại một package riêng.

## 12. Dependency injection bên trong `@Bean` method

Không cần tự lấy dependency từ `ApplicationContext`:

```java
@Bean
public WelcomeService welcomeService(ApplicationContext context) {
    MessageFormatter formatter =
            context.getBean(MessageFormatter.class);
    return new WelcomeService(formatter);
}
```

Cách này làm code phụ thuộc service locator và che giấu dependency thật.

Ưu tiên method parameter injection:

```java
@Bean
public WelcomeService welcomeService(MessageFormatter formatter) {
    return new WelcomeService(formatter);
}
```

Spring resolve `MessageFormatter` rồi truyền vào method.

### 12.1. Ví dụ cấu hình hoàn chỉnh

```java
@Configuration(proxyBeanMethods = false)
public class WelcomeConfiguration {

    @Bean
    public MessageFormatter messageFormatter() {
        return new DefaultMessageFormatter();
    }

    @Bean
    public WelcomeService welcomeService(
            MessageFormatter messageFormatter) {
        return new WelcomeService(messageFormatter);
    }
}
```

Trong ứng dụng thực tế, nếu `WelcomeService` đã được đăng ký bằng `@Service`, không cần khai báo lại `@Bean` cho service đó. Ví dụ trên chỉ minh họa việc Spring inject dependency vào factory method.

### 12.2. Tham số method thể hiện dependency graph

```java
@Bean
public OrderFacade orderFacade(
        OrderService orders,
        PaymentGateway payments,
        InventoryAvailability inventory) {

    return new OrderFacade(orders, payments, inventory);
}
```

Người đọc thấy ngay `OrderFacade` cần ba dependency nào. Spring cũng có đủ thông tin để sắp xếp việc tạo bean theo dependency graph.

## 13. `@Configuration(proxyBeanMethods = false)` và lời gọi trực tiếp giữa các method

Một class `@Configuration` có thể dùng:

```java
@Configuration(proxyBeanMethods = false)
```

Đây là chế độ lite configuration đối với việc xử lý method `@Bean`: Spring không cần tạo CGLIB subclass để intercept lời gọi trực tiếp giữa các method trong configuration class.

### 13.1. Không gọi trực tiếp `@Bean` method để lấy bean khác

Với `proxyBeanMethods = false`, code:

```java
@Configuration(proxyBeanMethods = false)
public class AppConfiguration {

    @Bean
    MessageFormatter formatter() {
        return new DefaultMessageFormatter();
    }

    @Bean
    WelcomeService welcomeService() {
        return new WelcomeService(formatter());
    }
}
```

Lời gọi `formatter()` trong Java là lời gọi method thông thường. Nó có thể tạo một object mới thay vì lấy bean `formatter` đã được container quản lý.

Kết quả là có nguy cơ tạo instance ngoài dự kiến.

### 13.2. Dùng method parameter injection

Viết:

```java
@Configuration(proxyBeanMethods = false)
public class AppConfiguration {

    @Bean
    MessageFormatter formatter() {
        return new DefaultMessageFormatter();
    }

    @Bean
    WelcomeService welcomeService(MessageFormatter formatter) {
        return new WelcomeService(formatter);
    }
}
```

Spring resolve bean theo dependency graph và truyền instance quản lý vào method.

### 13.3. Full configuration

Nếu dùng:

```java
@Configuration
public class AppConfiguration {
}
```

`proxyBeanMethods` mặc định là `true`. Spring có thể dùng proxy để intercept lời gọi giữa các `@Bean` methods trên configuration object nhằm bảo đảm tham chiếu tới bean theo semantics container.

Tuy nhiên, parameter injection vẫn thường rõ ràng hơn và giúp configuration ít phụ thuộc vào cơ chế proxy.

### 13.4. `@Component` có `@Bean` method

Một class không được đánh dấu `@Configuration` nhưng khai báo `@Bean` có thể được xử lý theo lite configuration semantics. Đừng giả định lời gọi trực tiếp giữa các method được intercept như full `@Configuration`.

Nếu class có trách nhiệm lắp ghép bean, dùng `@Configuration` và parameter injection rõ ràng.

## 14. Kết hợp component scan và Java configuration trong cùng ứng dụng

Một ứng dụng thường sử dụng cả hai:

```text
Spring Boot application
       |
       +--> Component scan
       |       |
       |       +--> @Service
       |       +--> @Repository
       |       +--> @RestController
       |
       +--> @Configuration
               |
               +--> @Bean: third-party client
               +--> @Bean: clock / mapper / adapter
               +--> @Bean: conditional strategy
```

Ví dụ:

```java
@Service
public class WelcomeService {

    private final MessageFormatter formatter;

    public WelcomeService(MessageFormatter formatter) {
        this.formatter = formatter;
    }
}
```

Formatter được đăng ký qua component scan:

```java
@Component
public class DefaultMessageFormatter implements MessageFormatter {
}
```

Một client bên ngoài được đăng ký qua Java configuration:

```java
@Configuration(proxyBeanMethods = false)
public class PartnerConfiguration {

    @Bean(destroyMethod = "close")
    public PartnerClient partnerClient(
            PartnerProperties properties) {
        return new PartnerClient(properties.endpoint());
    }
}
```

Không có lý do phải ép tất cả bean dùng cùng một cơ chế. Chọn theo nơi class được định nghĩa và mức kiểm soát cần thiết.

## 15. Đăng ký theo profile

Giả sử ứng dụng cần hai formatter:

- Một formatter đơn giản cho local.
- Một formatter dùng template engine trong production.

### 15.1. Component scan kết hợp `@Profile`

```java
@Component
@Profile("local")
public class SimpleMessageFormatter implements MessageFormatter {

    @Override
    public String format(String name) {
        return "Hello, " + name + "!";
    }
}
```

```java
@Component
@Profile("production")
public class TemplateMessageFormatter implements MessageFormatter {

    @Override
    public String format(String name) {
        return "Welcome, " + name + "!";
    }
}
```

### 15.2. Java configuration kết hợp `@Profile`

```java
@Configuration(proxyBeanMethods = false)
public class MessageConfiguration {

    @Bean
    @Profile("local")
    MessageFormatter localFormatter() {
        return new SimpleMessageFormatter();
    }

    @Bean
    @Profile("production")
    MessageFormatter productionFormatter(
            TemplateEngine templateEngine) {
        return new TemplateMessageFormatter(templateEngine);
    }
}
```

Trong ví dụ thứ hai, `TemplateEngine` là dependency giả định đã được đăng ký.

### 15.3. Chọn profile khi chạy

```bash
java -jar app.jar --spring.profiles.active=local
```

Hoặc:

```bash
java -jar app.jar --spring.profiles.active=production
```

Spring chỉ đăng ký những bean definitions phù hợp với profile active.

### 15.4. Tránh thiếu hoặc trùng implementation

Nếu không profile nào tạo `MessageFormatter`, service inject bắt buộc sẽ thất bại khi khởi động.

Nếu nhiều profile cùng active và hai implementation cùng được đăng ký, service có thể gặp ambiguity.

Hãy kiểm tra profile combination trong từng môi trường và xác định implementation được chọn.

## 16. Đăng ký theo property với `@ConditionalOnProperty`

Nếu muốn lựa chọn implementation theo property thay vì profile, có thể dùng conditional bean.

```java
@Configuration(proxyBeanMethods = false)
public class MessageConfiguration {

    @Bean
    @ConditionalOnProperty(
            name = "welcome.formatter",
            havingValue = "simple",
            matchIfMissing = true
    )
    MessageFormatter simpleFormatter() {
        return new DefaultMessageFormatter();
    }

    @Bean
    @ConditionalOnProperty(
            name = "welcome.formatter",
            havingValue = "template"
    )
    MessageFormatter templateFormatter(
            TemplateEngine templateEngine) {
        return new TemplateMessageFormatter(templateEngine);
    }
}
```

`application.properties`:

```properties
welcome.formatter=simple
```

Hoặc:

```bash
java -jar app.jar --welcome.formatter=template
```

### 16.1. Ý nghĩa `matchIfMissing`

```java
matchIfMissing = true
```

cho phép condition match khi property không được khai báo. Trong ví dụ, formatter simple trở thành lựa chọn mặc định.

Nếu cả hai condition không match, ứng dụng không có `MessageFormatter` và dependency bắt buộc có thể thất bại.

### 16.2. Không đăng ký hai implementation cùng lúc ngoài ý muốn

Điều kiện cần được thiết kế để chỉ một lựa chọn match cho một cấu hình hợp lệ. Nếu property có giá trị không mong muốn, nên fail rõ ràng thay vì âm thầm chọn sai bean.

### 16.3. `@ConditionalOnProperty` thuộc Spring Boot

Annotation này thường được import từ:

```java
org.springframework.boot.autoconfigure.condition.ConditionalOnProperty
```

Nó hữu ích trong application configuration và auto-configuration. Với một điều kiện đơn giản chỉ phụ thuộc profile, `@Profile` có thể rõ ràng hơn.

## 17. Nhiều bean cùng interface: `@Qualifier` và `@Primary`

Có nhiều implementation là một nhu cầu hợp lệ. Khi đó client phải xác định bean cần dùng.

### 17.1. Dùng `@Qualifier`

Component:

```java
@Component("plainFormatter")
public class PlainFormatter implements MessageFormatter {
}
```

Java configuration:

```java
@Configuration(proxyBeanMethods = false)
public class FormatterConfiguration {

    @Bean("formalFormatter")
    MessageFormatter formalFormatter() {
        return new FormalFormatter();
    }
}
```

Client:

```java
@Service
public class FormalWelcomeService {

    private final MessageFormatter formatter;

    public FormalWelcomeService(
            @Qualifier("formalFormatter")
            MessageFormatter formatter) {
        this.formatter = formatter;
    }
}
```

### 17.2. Dùng `@Primary`

```java
@Bean
@Primary
MessageFormatter defaultFormatter() {
    return new DefaultMessageFormatter();
}
```

Khi injection theo type có nhiều ứng viên, `@Primary` chỉ định bean ưu tiên mặc định trong các trường hợp phù hợp.

### 17.3. Khi cần chọn theo dữ liệu runtime

`@Qualifier` và `@Primary` giải quyết lựa chọn lúc wiring. Nếu provider được chọn theo request hoặc tenant, hãy inject một registry/map hoặc strategy router:

```java
@Service
public class FormatterRouter {

    private final Map<String, MessageFormatter> formatters;

    public FormatterRouter(
            Map<String, MessageFormatter> formatters) {
        this.formatters = formatters;
    }

    public MessageFormatter forLanguage(String language) {
        MessageFormatter formatter = formatters.get(language);
        if (formatter == null) {
            throw new IllegalArgumentException(
                    "Unsupported language"
            );
        }
        return formatter;
    }
}
```

Trong ứng dụng thật, cần chuẩn hóa key và quy định fallback. Không đưa giá trị đầu vào không kiểm soát vào việc tra cứu bean tùy tiện.

## 18. Lifecycle của bean đăng ký bằng hai cách

Một điểm quan trọng: component scan và `@Bean` đều đăng ký bean để Spring quản lý lifecycle.

Với component:

```java
@Component
public class FileIndex {

    @PostConstruct
    void initialize() {
        // ...
    }

    @PreDestroy
    void close() {
        // ...
    }
}
```

Với Java configuration:

```java
@Bean(initMethod = "initialize", destroyMethod = "close")
public FileIndex fileIndex() {
    return new FileIndex();
}
```

Trong cả hai trường hợp, Spring quản lý object nếu bean được tạo bởi container.

### 18.1. Khai báo destroy method cho third-party class

Một thư viện có method `close()` nhưng không có annotation Spring:

```java
@Bean(destroyMethod = "close")
VendorClient vendorClient() {
    return new VendorClient();
}
```

Đây là một lợi ích rõ ràng của Java configuration: có thể gắn lifecycle metadata cho class mà không sửa source.

### 18.2. Không nhầm bean với object tự tạo

Nếu trong một `@Bean` method bạn tạo:

```java
VendorClient client = new VendorClient();
return client;
```

object được trả về là bean và Spring quản lý theo cấu hình.

Nhưng nếu method tạo thêm object khác rồi giữ trong một static field hoặc trả nó ra ngoài mà không đăng ký bean, object đó không tự động có lifecycle riêng trong container.

## 19. Scope và proxy không phụ thuộc cách đăng ký

Có thể khai báo scope bằng stereotype:

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class RequestFormatter {
}
```

Hoặc bằng `@Bean`:

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
RequestFormatter requestFormatter() {
    return new RequestFormatter();
}
```

Tương tự, những metadata như `@Lazy`, `@Primary`, `@DependsOn`, qualifier và các điều kiện khác có thể được áp dụng theo cách phù hợp với từng bean definition.

### 19.1. Prototype không được destroy giống singleton

Spring tạo prototype bean khi được yêu cầu nhưng không quản lý đầy đủ destruction lifecycle của prototype instance sau khi giao cho client.

Nếu prototype sở hữu socket, thread hoặc resource cần đóng, caller/factory phải có trách nhiệm release rõ ràng.

### 19.2. Scope cần phản ánh lifecycle thật

Đừng chọn prototype chỉ để “mỗi lần inject có object mới” nếu bean chứa resource dùng chung hoặc dependency singleton. Hãy xem scope của bean và scope của dependencies tương thích như thế nào.

## 20. Component scan: kiểm soát phạm vi tìm kiếm

Mặc định, `@SpringBootApplication` scan package của application class và các package con.

Ví dụ:

```text
com.example
├── Application.java
├── orders
│   └── OrderService.java
└── payment
    └── PaymentGatewayImpl.java
```

Nếu `Application.java` nằm ở `com.example`, các package con có thể được scan.

Nếu application class nằm ở `com.example.orders`, package `com.example.payment` không nằm trong package con đó.

### 20.1. Dùng `scanBasePackages`

```java
@SpringBootApplication(
    scanBasePackages = {
        "com.example.orders",
        "com.example.payment"
    }
)
public class OrdersApplication {
}
```

### 20.2. Dùng `@ComponentScan`

```java
@Configuration
@ComponentScan(basePackages = {
        "com.example.orders",
        "com.example.payment"
})
public class ApplicationComponents {
}
```

Trong ứng dụng Spring Boot, cần tránh cấu hình scan trùng lặp không cần thiết. Chọn một nơi rõ ràng để xác định package roots.

### 20.3. Scan rộng quá mức

Không nên:

```java
@ComponentScan("com")
```

nếu phạm vi này có thể quét package của dependency hoặc module không thuộc ứng dụng. Nó có thể đăng ký bean ngoài dự kiến, tạo xung đột hoặc làm startup chậm.

Hãy tổ chức package gốc hợp lý và scan những module mà ứng dụng sở hữu.

## 21. Đăng ký Java configuration từ package khác

Configuration class cũng phải được đưa vào context.

Nếu nằm ngoài component scan, có thể import:

```java
@SpringBootApplication
@Import(PartnerClientConfiguration.class)
public class Application {
}
```

Hoặc điều chỉnh package scan theo kiến trúc.

### 21.1. `@Import` phù hợp khi muốn module wiring tường minh

Một module có thể cung cấp configuration class:

```java
@Configuration(proxyBeanMethods = false)
public class BillingModuleConfiguration {

    @Bean
    BillingService billingService(PaymentGateway gateway) {
        return new BillingService(gateway);
    }
}
```

Application composition root import module:

```java
@Import(BillingModuleConfiguration.class)
```

Đây là cách lắp ghép module mà không cần quét toàn bộ package.

### 21.2. Không import mọi configuration tùy tiện

Nếu hai configuration cùng tạo bean cùng tên hoặc cùng contract không có qualifier, application context có thể gặp conflict. Hãy kiểm tra composition root và các điều kiện bật/tắt module.

## 22. So sánh khi nào dùng component scan và khi nào dùng `@Bean`

| Tình huống | Cách thường phù hợp | Lý do |
| --- | --- | --- |
| Service do ứng dụng viết, vai trò rõ | `@Service` + component scan | Đơn giản, gần class |
| Repository implementation do ứng dụng viết | `@Repository` + component scan | Thể hiện persistence stereotype |
| Controller | `@Controller` / `@RestController` | Tích hợp Spring MVC |
| Class thư viện bên ngoài | `@Bean` | Không sửa được source |
| Client cần constructor arguments từ config | `@Bean` | Wiring tường minh |
| Chọn implementation theo property | `@Bean` + condition hoặc component + condition | Kiểm soát lựa chọn |
| Tạo object từ factory method | `@Bean` | Thể hiện quá trình tạo |
| Domain object thuần, không cần container | Không đăng ký bean | Có thể tạo trực tiếp |
| Nhiều object cùng contract theo profile | Một trong hai, kết hợp profile | Chọn implementation rõ ràng |
| Một dependency có lifecycle `close()` | `@Bean(destroyMethod=...)` hoặc bean lifecycle phù hợp | Quản lý cleanup |

Đây là hướng dẫn lựa chọn, không phải luật bắt buộc. Một class ứng dụng vẫn có thể được tạo bằng `@Bean` nếu cần assembly rõ ràng; một class thư viện cũng có thể được import qua auto-configuration có sẵn.

## 23. Java configuration không có nghĩa là tự quản lý object ngoài Spring

Một hiểu nhầm:

```java
@Configuration
public class AppConfiguration {

    @Bean
    MessageFormatter messageFormatter() {
        return new DefaultMessageFormatter();
    }
}
```

Vì method tự gọi `new`, có người cho rằng Spring không quản lý object. Điều đó không đúng.

Spring gọi factory method và đăng ký object trả về như bean. Container vẫn có thể:

- Inject object vào bean khác.
- Áp dụng bean post-processors.
- Quản lý scope.
- Áp dụng proxy khi phù hợp.
- Gọi initialization/destruction callbacks.

Object được tạo bằng `new` **bên trong factory method** vẫn trở thành bean khi được method `@Bean` trả về.

Điều khác biệt là ai gọi constructor và nơi cung cấp metadata: Spring xử lý bean definition thông qua configuration method.

## 24. Khi nào không nên đăng ký một class thành bean?

Không phải mọi class đều cần container.

Ví dụ value object:

```java
public record Money(
        BigDecimal amount,
        Currency currency) {
}
```

Một `Money` cụ thể thường là dữ liệu theo từng nghiệp vụ, không phải một singleton service dùng chung.

Có thể tạo trực tiếp:

```java
Money total = new Money(amount, currency);
```

Tương tự, DTO, request model, domain event hoặc calculator thuần không có dependency container có thể không cần bean registration.

### 24.1. Tiêu chí nhận diện

Một object thường phù hợp với Spring bean khi:

- Là collaborator dùng chung trong application context.
- Có dependencies cần container inject.
- Cần lifecycle do container quản lý.
- Cần proxy/transaction/security/async behavior do Spring cung cấp.
- Là controller, service, repository hoặc infrastructure component.

Một object thường không cần bean khi:

- Là dữ liệu ngắn hạn theo request/use case.
- Được tạo rẻ và có giá trị theo từng lần xử lý.
- Không có dependency hoặc lifecycle dùng chung.
- Việc tạo trực tiếp làm ownership rõ hơn.

Đừng đăng ký tất cả domain objects vào context chỉ để có thể autowire chúng.

## 25. Kiểm tra bean được đăng ký bằng component scan

Có thể dùng test với `ApplicationContextRunner` hoặc `@SpringBootTest`.

Ví dụ context test tối thiểu:

```java
class ComponentScanRegistrationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(ScanConfiguration.class);

    @Test
    void discoversFormatterComponent() {
        contextRunner.run(context -> {
            assertThat(context)
                    .hasSingleBean(MessageFormatter.class);
        });
    }

    @Configuration
    @ComponentScan(basePackageClasses = DefaultMessageFormatter.class)
    static class ScanConfiguration {
    }
}
```

Ví dụ cần imports phù hợp cho JUnit 5, AssertJ, Spring Boot test context runner và `@Configuration`.

`basePackageClasses` giúp chỉ định package theo class marker, tránh hard-code package string.

### 25.1. Kiểm tra bean name

```java
contextRunner.run(context -> {
    assertThat(context)
            .containsBean("defaultMessageFormatter");
});
```

Tên bean mặc định dựa trên class name; nếu đã chỉ định tên trong `@Component`, assertion cần dùng tên thực tế.

## 26. Kiểm tra bean được đăng ký bằng Java configuration

```java
class JavaConfigurationRegistrationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(MessageConfiguration.class);

    @Test
    void registersFormatterFromBeanMethod() {
        contextRunner.run(context -> {
            assertThat(context)
                    .hasSingleBean(MessageFormatter.class);

            MessageFormatter formatter =
                    context.getBean(MessageFormatter.class);

            assertThat(formatter.format("Lan"))
                    .isEqualTo("Hello, Lan!");
        });
    }
}
```

Test này kiểm tra hai điều:

1. Configuration đã đăng ký đúng một bean `MessageFormatter`.
2. Bean thực hiện chức năng mong đợi.

### 26.1. Kiểm tra bean name từ method

```java
contextRunner.run(context -> {
    assertThat(context).containsBean("messageFormatter");
});
```

Nếu method `@Bean` được đặt tên khác hoặc có explicit bean name, assertion phải phản ánh cấu hình thực tế.

## 27. So sánh hai cách đăng ký bằng cùng một contract test

Ta có thể viết test dùng chung cho service:

```java
class WelcomeServiceTest {

    @Test
    void returnsFormattedWelcomeMessage() {
        MessageFormatter formatter =
                new DefaultMessageFormatter();

        WelcomeService service =
                new WelcomeService(formatter);

        assertThat(service.welcome("Lan"))
                .isEqualTo("Hello, Lan!");
    }
}
```

Test này không cần Spring. Nó kiểm tra behavior của application service và implementation.

Sau đó, mỗi cách đăng ký có một context test riêng để xác nhận wiring.

### 27.1. Test component scan

Xác nhận context tìm thấy implementation nhờ stereotype.

### 27.2. Test Java configuration

Xác nhận factory method tạo bean đúng contract và dependency.

### 27.3. Tại sao tách hai loại test?

Nếu behavior test fail, có thể logic format sai.

Nếu wiring test fail, có thể component scan, package, profile hoặc bean definition sai.

Hai lỗi thuộc hai tầng khác nhau. Tách test giúp định vị nhanh hơn.

## 28. Kiểm tra toàn bộ ứng dụng bằng `@SpringBootTest`

Một integration test có thể khởi tạo context gần với application:

```java
@SpringBootTest
class WelcomeApplicationTest {

    @Autowired
    WelcomeService welcomeService;

    @Test
    void applicationProvidesWelcomeService() {
        assertThat(welcomeService.welcome("Lan"))
                .isEqualTo("Hello, Lan!");
    }
}
```

Test này kiểm tra application context thật của project và service được inject.

### 28.1. Dùng khi cần kiểm tra integration

`@SpringBootTest` hữu ích khi cần:

- Xác nhận application context có thể khởi động.
- Xác nhận component scan và Java configuration được kết hợp đúng.
- Kiểm tra bean wiring thực tế.
- Kiểm tra auto-configuration liên quan.

### 28.2. Không dùng cho mọi unit test

Khởi tạo toàn bộ context có chi phí cao hơn tạo class trực tiếp hoặc dùng context runner nhỏ. Dùng mức test tương xứng với điều cần xác nhận.

## 29. Chẩn đoán khi component scan không tìm thấy bean

Triệu chứng:

```text
No qualifying bean of type 'MessageFormatter' available
```

Kiểm tra:

1. Implementation có stereotype không?
2. Package có nằm trong phạm vi scan không?
3. Component scan có exclude filter không?
4. Bean có bị điều kiện profile/property loại bỏ không?
5. Class có phải là một class được Spring có thể instantiate không?
6. Có lỗi dependency của chính implementation khiến bean không tạo được không?
7. Có configuration class nào chưa được import không?

### 29.1. Sửa package scan

Nếu class nằm ngoài package gốc:

```java
@SpringBootApplication(scanBasePackages = {
        "com.example.welcome",
        "com.example.shared.formatting"
})
```

### 29.2. Dùng `@Import`

Nếu module cung cấp một configuration class:

```java
@Import(FormattingConfiguration.class)
```

### 29.3. Không tạo một `@Bean` khác để che scan sai

Nếu implementation đã được thiết kế là component, hãy sửa phạm vi scan. Đăng ký thêm cùng implementation bằng `@Bean` có thể tạo hai bean và che nguyên nhân ban đầu.

## 30. Chẩn đoán khi Java configuration không đăng ký bean

Triệu chứng:

```text
No qualifying bean of type 'MessageFormatter' available
```

Kiểm tra:

- Configuration class có được component scan hoặc import không?
- Method có `@Bean` không?
- Configuration có bị profile/condition loại bỏ không?
- Method factory có ném exception khi được gọi không?
- Return type/object có phù hợp contract không?
- Bean có bị đăng ký dưới tên/qualifier khác với điều client yêu cầu không?
- Có điều kiện property bị sai không?

### 30.1. `@Configuration` không tự được tìm thấy ở mọi package

Một configuration class cũng phải được đưa vào context qua scan hoặc import. Chỉ thêm `@Configuration` vào class nằm ngoài phạm vi scan không tự động làm Spring biết tới nó.

### 30.2. Factory method không được gọi

Nếu condition không match, Spring có thể không đăng ký bean definition từ method đó.

Kiểm tra active profiles, property sources và condition evaluation khi cần.

### 30.3. Factory method ném exception

Nếu method `@Bean` gọi constructor hoặc client factory bị lỗi, Spring có thể báo `BeanCreationException` hoặc exception liên quan. Đọc `Caused by` để xác định constructor/factory operation thất bại.

## 31. Chẩn đoán khi có hai bean cùng chức năng

Triệu chứng thường gặp:

```text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2
```

Kiểm tra bean names:

```java
String[] names =
        context.getBeanNamesForType(MessageFormatter.class);
```

Trong môi trường debug/test, có thể in những bean names không nhạy cảm:

```java
Arrays.stream(names).forEach(System.out::println);
```

Ví dụ kết quả:

```text
defaultMessageFormatter
messageFormatter
```

Điều này gợi ý implementation được đăng ký cả bằng component scan và Java configuration.

### 31.1. Chọn một registration path

Nếu hai bean thực ra cùng đại diện một chức năng và không cần đồng thời tồn tại, bỏ một đường đăng ký.

### 31.2. Đặt qualifier khi thật sự cần nhiều bean

Nếu hai formatter phục vụ hai mục đích khác nhau, đặt tên rõ và inject đúng bean.

### 31.3. Tránh bật bean overriding để che conflict

Cho phép bean definition override có thể khiến một đăng ký thay thế đăng ký khác tùy thứ tự và cấu hình. Điều này làm kết quả startup khó dự đoán.

Hãy làm rõ bean ownership và điều kiện đăng ký thay vì phụ thuộc vào override.

## 32. `@Bean` method có thể trả về implementation cụ thể hoặc interface

Hai ví dụ:

```java
@Bean
MessageFormatter messageFormatter() {
    return new DefaultMessageFormatter();
}
```

và:

```java
@Bean
DefaultMessageFormatter messageFormatter() {
    return new DefaultMessageFormatter();
}
```

Cả hai đều trả về object có thể được inject theo `MessageFormatter`.

### 32.1. Khi nào return type interface phù hợp?

Khi bean được dùng qua contract và không cần expose implementation-specific API trong quá trình wiring.

### 32.2. Khi nào return type cụ thể phù hợp?

Khi configuration hoặc các bean khác thực sự cần kiểu cụ thể, hoặc khi framework cần metadata/type prediction ở giai đoạn đăng ký. Hãy tránh làm client phụ thuộc concrete class chỉ vì method trả về concrete type.

### 32.3. Bean type prediction

Spring có thể cần dự đoán kiểu bean trước khi factory method được thực thi. Khai báo return type cụ thể có thể cung cấp metadata tốt hơn trong một số tình huống, nhất là khi cần tìm bean theo implementation type hoặc xử lý configuration phức tạp.

Đối với contract thông thường, khai báo return type interface giúp thể hiện rõ abstraction client cần.

## 33. Tên bean, alias và qualifier

Một bean có thể có:

- Bean name chính.
- Alias.
- Qualifier metadata.
- Primary status.

Ví dụ:

```java
@Bean(name = {"primaryFormatter", "welcomeFormatter"})
@Primary
MessageFormatter messageFormatter() {
    return new DefaultMessageFormatter();
}
```

Client:

```java
public WelcomeService(
        @Qualifier("primaryFormatter")
        MessageFormatter formatter) {
    this.formatter = formatter;
}
```

### 33.1. Bean name không phải lúc nào cũng là qualifier duy nhất

`@Qualifier` có thể dùng giá trị qualifier metadata, không chỉ bean name. Có thể tạo custom qualifier annotation khi cần thể hiện semantic role:

```java
@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.METHOD,
        ElementType.TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface Formal {
}
```

Đăng ký:

```java
@Bean
@Formal
MessageFormatter formalFormatter() {
    return new FormalFormatter();
}
```

Inject:

```java
public ReportService(@Formal MessageFormatter formatter) {
    this.formatter = formatter;
}
```

Custom qualifier hữu ích khi ý nghĩa lựa chọn quan trọng hơn một chuỗi tên bean.

## 34. Java configuration và auto-configuration

Spring Boot auto-configuration cũng dựa nhiều vào Java configuration và conditional bean definitions.

Ví dụ một auto-configuration có thể cung cấp bean khi:

- Một class có trên classpath.
- Một property có giá trị phù hợp.
- Người dùng chưa tự khai báo bean tương ứng.

Một pattern phổ biến:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(SomeClient.class)
public class SomeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    SomeClient someClient(SomeClientProperties properties) {
        return new SomeClient(properties.endpoint());
    }
}
```

Ví dụ chỉ minh họa cấu trúc auto-configuration; trong project thật cần đúng annotation/import và điều kiện theo framework version.

### 34.1. `@ConditionalOnMissingBean`

Condition này cho phép auto-configuration cung cấp default bean khi người dùng chưa định nghĩa bean phù hợp.

Đây là một cơ chế mở rộng có chủ đích: người dùng có thể thay implementation bằng một bean của họ.

### 34.2. Khác biệt với component scan

Component scan phát hiện các class có stereotype trong phạm vi scan.

Auto-configuration thường đăng ký bean dựa trên điều kiện classpath, property, bean hiện có và thứ tự cấu hình.

### 34.3. Không tạo auto-configuration cho mọi module nhỏ

Nếu ứng dụng chỉ có một service nội bộ, `@Service` hoặc một `@Bean` đơn giản thường đủ. Auto-configuration phù hợp hơn khi xây starter hoặc module tích hợp có API cấu hình cho nhiều ứng dụng.

## 35. Một bài thực hành thứ hai: cấu hình `Clock`

`Clock` là ví dụ tốt cho Java configuration vì đây là class Java chuẩn, thường cần chọn implementation phù hợp với môi trường và test.

### 35.1. Đăng ký bằng `@Bean`

```java
@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Service:

```java
@Service
public class ExpirationService {

    private final Clock clock;

    public ExpirationService(Clock clock) {
        this.clock = clock;
    }

    public Instant now() {
        return clock.instant();
    }
}
```

### 35.2. Thay bằng fixed clock trong test

```java
@TestConfiguration
public class FixedTimeTestConfiguration {

    @Bean
    @Primary
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
```

Test có thể import test configuration để kiểm soát thời gian.

### 35.3. Vì sao không cần `ClockImpl`?

Không cần tạo:

```java
interface ClockProvider { ... }
class ClockProviderImpl implements ClockProvider { ... }
```

nếu Java `Clock` đã là abstraction phù hợp. Có thể đăng ký một instance của class chuẩn bằng `@Bean`.

Đây là ví dụ cho thấy Java configuration có thể cung cấp dependency mà không cần tạo một interface/implementation pair riêng.

## 36. Một bài thực hành thứ ba: đăng ký mapper

Giả sử ứng dụng dùng mapper thuần Java:

```java
public class OrderMapper {

    public OrderResponse toResponse(Order order) {
        return new OrderResponse(
                order.id().value(),
                order.total().amount()
        );
    }
}
```

Nếu mapper không cần Spring annotation, có thể đăng ký:

```java
@Configuration(proxyBeanMethods = false)
public class MappingConfiguration {

    @Bean
    OrderMapper orderMapper() {
        return new OrderMapper();
    }
}
```

Hoặc nếu mapper được ứng dụng quản lý và có thể gắn stereotype:

```java
@Component
public class OrderMapper {
}
```

Hai cách đều có thể cung cấp `OrderMapper` cho service.

### 36.1. Chọn theo trách nhiệm

Nếu mapper được tạo bởi annotation processor hoặc thư viện có factory riêng, Java configuration có thể phù hợp.

Nếu mapper là component đơn giản do ứng dụng viết và cần inject dependency, component scan có thể gọn hơn.

Nếu mapper thuần, tạo rẻ và không có dependency, khởi tạo trực tiếp trong scope phù hợp cũng có thể đủ.

Không nên biến mọi class helper thành singleton bean chỉ vì Spring có thể quản lý chúng.

## 37. Tổ chức configuration theo module

Khi ứng dụng lớn lên, không nên gom mọi `@Bean` vào một file khổng lồ.

Có thể tổ chức:

```text
config/
├── WebConfiguration.java
├── PersistenceConfiguration.java
├── MessagingConfiguration.java
├── PaymentConfiguration.java
└── TimeConfiguration.java
```

Mỗi configuration nên tập trung vào một nhóm bean liên quan.

### 37.1. Không tạo configuration cho một bean không cần cấu hình

Nếu một service đơn giản:

```java
@Service
public class OrderService {
}
```

thì không cần thêm một `OrderServiceConfiguration` chỉ để trả về `new OrderService()`, trừ khi có lý do wiring đặc biệt.

### 37.2. Configuration class không phải nơi đặt business logic

Không nên:

```java
@Configuration
public class OrderConfiguration {

    @Bean
    OrderService orderService() {
        // Tính giá, ghi database, gửi email...
        return new OrderService();
    }
}
```

Configuration chịu trách nhiệm lắp ghép object. Business logic thuộc service/domain.

### 37.3. Tách property binding

Những cấu hình phức tạp có thể dùng `@ConfigurationProperties`:

```java
@ConfigurationProperties(prefix = "mail")
public record MailProperties(
        URI endpoint,
        Duration timeout
) {
}
```

Đăng ký properties bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` theo cấu trúc ứng dụng.

Sau đó `@Bean` method nhận properties qua parameter injection.

## 38. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | Component không được scan hoặc configuration chưa được import | Kiểm tra package, scan base, `@Import` |
| `No qualifying bean` | Không có implementation phù hợp | Kiểm tra stereotype, `@Bean`, profile và condition |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng type | Chọn một registration hoặc dùng qualifier/primary |
| Bean definition override conflict | Hai đường đăng ký dùng cùng bean name | Xác định owner và bỏ đăng ký trùng |
| `@Bean` method không chạy | Configuration không được nạp hoặc condition không match | Kiểm tra configuration registration |
| `NullPointerException` trong service | Tự tạo object bằng `new` và bỏ qua injection | Inject bean qua constructor |
| Tạo nhiều instance ngoài ý muốn | Gọi trực tiếp `@Bean` method trong lite configuration | Dùng method parameter injection |
| Không đóng client | Thiếu destroy method/lifecycle | Khai báo `destroyMethod` hoặc callback |
| Profile local thiếu formatter | Profile không active hoặc condition sai | Xác nhận cấu hình runtime |
| Component ngoài package không được tìm thấy | Phạm vi scan quá hẹp | Dùng base package hoặc import config |
| Bean đúng type nhưng sai implementation | Condition/qualifier/primary chưa rõ | Xác định quy tắc chọn implementation |
| Context khởi động chậm | Scan quá rộng hoặc factory method làm I/O dài | Thu hẹp scan, tách startup work |

## 39. Quy trình thực hành chuyển từ component scan sang Java configuration

Giả sử project hiện tại có:

```java
@Component
public class DefaultMessageFormatter implements MessageFormatter {
}
```

Bạn muốn bỏ annotation để class thuần Java và đăng ký từ configuration.

Thực hiện:

### Bước 1 — Xác định bean đang được sử dụng

Tìm các client inject `MessageFormatter` và xác định bean name/qualifier hiện tại.

### Bước 2 — Tạo configuration

```java
@Configuration(proxyBeanMethods = false)
public class MessageConfiguration {

    @Bean
    MessageFormatter messageFormatter() {
        return new DefaultMessageFormatter();
    }
}
```

### Bước 3 — Bỏ stereotype khỏi class

```java
public class DefaultMessageFormatter implements MessageFormatter {
}
```

### Bước 4 — Giữ nguyên client

```java
public WelcomeService(MessageFormatter formatter) {
    this.formatter = formatter;
}
```

### Bước 5 — Kiểm tra context

Xác nhận có đúng một bean `MessageFormatter` và bean có tên mong muốn.

### Bước 6 — Kiểm tra behavior

Gọi service và xác nhận output vẫn giống trước.

### Bước 7 — Kiểm tra lifecycle nếu có resource

Nếu implementation mở socket hoặc pool, xác nhận destroy callback được gọi khi context đóng.

### Bước 8 — Ghi nhận lý do chọn Java configuration

Ví dụ: implementation đến từ thư viện, cần constructor arguments hoặc muốn gom integration wiring vào module config.

Đừng thay đổi cách đăng ký chỉ để tạo thêm một lớp configuration nếu không có lợi ích cụ thể.

## 40. Bài tập tổng hợp

### Bài 1 — Đăng ký bằng component scan

Tạo `MessageFormatter`, `DefaultMessageFormatter` và `WelcomeService`.

Đánh dấu implementation bằng `@Component`, khởi động Spring Boot context và gọi service.

Xác nhận bean được tìm thấy trong phạm vi component scan.

### Bài 2 — Chuyển sang Java configuration

Bỏ `@Component` khỏi implementation, tạo `MessageConfiguration` với một `@Bean` method.

Giữ nguyên service và kiểm tra output không thay đổi.

### Bài 3 — So sánh bean name

Ghi nhận bean name khi đăng ký bằng component scan và khi đăng ký bằng `@Bean`.

Thay method name và explicit bean name, quan sát kết quả.

### Bài 4 — Đăng ký trùng

Giữ `@Component`, đồng thời thêm `@Bean` tạo một instance mới cùng interface.

Khởi động context và quan sát ambiguity hoặc bean name conflict. Sau đó loại bỏ một đường đăng ký.

### Bài 5 — Nhiều implementation

Tạo `PlainFormatter` và `FormalFormatter`.

Đăng ký một bằng component scan, một bằng Java configuration. Dùng `@Qualifier` để inject đúng bean.

### Bài 6 — Dùng `@Primary`

Đánh dấu một formatter là primary. Inject `MessageFormatter` mà không qualifier.

Quan sát implementation được chọn và giải thích khi nào primary phù hợp.

### Bài 7 — Chọn bằng profile

Tạo formatter local và production, đăng ký bằng `@Profile` theo cả hai phương án.

Chạy ứng dụng với các profile khác nhau và xác nhận bean nào tồn tại.

### Bài 8 — Chọn bằng property

Dùng `@ConditionalOnProperty` để chọn implementation.

Thử property không có, giá trị `simple`, `template` và một giá trị không hợp lệ.

Xác định khi nào ứng dụng thiếu bean hoặc có nhiều bean.

### Bài 9 — Đăng ký class thư viện

Tạo một class client không có annotation Spring, constructor cần endpoint và timeout.

Đăng ký bằng `@Bean` và inject vào một service.

### Bài 10 — Destroy method

Tạo fake client có `close()` và đăng ký bằng:

```java
@Bean(destroyMethod = "close")
```

Đóng context, xác nhận method được gọi.

### Bài 11 — `proxyBeanMethods = false`

Tạo hai `@Bean` methods. Thử gọi trực tiếp method này từ method kia, quan sát instance được tạo.

Sau đó đổi sang method parameter injection và xác nhận cùng bean instance được sử dụng.

### Bài 12 — Component scan package

Đặt implementation ở package sibling ngoài application root. Quan sát bean không được tìm thấy.

Sửa bằng `scanBasePackages` hoặc `@Import` configuration phù hợp.

### Bài 13 — Test bằng `ApplicationContextRunner`

Viết hai test:

- Một test đăng ký component qua scan.
- Một test đăng ký qua `@Bean`.

Assert có đúng một bean theo type và behavior đúng.

### Bài 14 — Test toàn ứng dụng

Dùng `@SpringBootTest` để xác nhận controller, service và formatter được wiring trong application context.

### Bài 15 — Đánh giá class có cần bean không

Với các class `Money`, `OrderMapper`, `PaymentGateway`, `OrderService` và `RequestDto`, quyết định class nào nên là bean, class nào nên được tạo trực tiếp.

Giải thích dựa trên dependency, lifecycle và phạm vi sử dụng.

### Bài 16 — Chọn registration strategy

Một ứng dụng có:

- Service do team viết.
- Repository JPA.
- SDK đối tác.
- Clock.
- Formatter theo profile.

Đề xuất registration strategy cho từng loại và giải thích lý do.

### Bài 17 — Điều tra startup failure

Tạo một `@Bean` method ném exception khi endpoint thiếu.

Đọc stack trace, tìm bean root và sửa property. Phân biệt lỗi factory method với lỗi component scan.

### Bài 18 — Refactor configuration

Tạo một configuration class có nhiều bean không liên quan. Chia thành các configuration theo module.

Xác nhận application context vẫn khởi động và không có bean duplicate.

## 41. Ghi nhớ

Component scan và Java configuration là hai cách đăng ký object vào Spring IoC container. Component scan phù hợp với class ứng dụng có stereotype và nằm trong phạm vi scan. Java configuration phù hợp khi cần tạo object từ factory method, cấu hình constructor arguments, tích hợp thư viện bên ngoài hoặc lựa chọn implementation theo điều kiện.

Khi cả hai cách cung cấp cùng một implementation và cùng dependency, client có thể sử dụng chúng mà không cần thay đổi. `WelcomeService` chỉ phụ thuộc `MessageFormatter`; nó không cần biết bean được tạo từ `@Component` hay `@Bean`.

Không đăng ký cùng một chức năng hai lần nếu không có nhu cầu nhiều implementation. Hai bean cùng type có thể gây ambiguity; cùng bean name có thể tạo conflict. Nếu thật sự cần nhiều bean, dùng `@Qualifier`, `@Primary`, profile hoặc điều kiện để lựa chọn rõ ràng.

**Hãy dùng component scan cho discovery tự nhiên của component ứng dụng, dùng Java configuration cho việc lắp ghép tường minh và tích hợp dependency.** Cả hai đều tạo bean do Spring quản lý; điều quan trọng là mỗi bean có một nguồn đăng ký rõ, dependency được thể hiện minh bạch và lifecycle được xử lý đúng.
