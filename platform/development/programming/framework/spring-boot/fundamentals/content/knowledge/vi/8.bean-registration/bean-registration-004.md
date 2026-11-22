# Quy tắc đặt tên bean mặc định và đặt tên chủ động

Trong Spring Boot, một đối tượng được Spring quản lý được gọi là **bean**. Mỗi bean được đăng ký trong một `ApplicationContext` với một **tên bean** (bean name) dùng để nhận diện bean trong registry. Tên này xuất hiện trong thông báo lỗi, công cụ chẩn đoán và một số cách tiêm phụ thuộc. Hiểu quy tắc đặt tên giúp dự đoán bean nào được tạo, tránh xung đột tên và chọn đúng implementation khi có nhiều bean cùng kiểu.

Spring Boot sử dụng cơ chế bean của **Spring Framework**. Bản thân Boot thường tạo và cấu hình nhiều bean tự động, nhưng các quy tắc cơ bản khi đặt tên cho component hoặc cho phương thức `@Bean` vẫn là quy tắc của Spring.

## 1. Tên bean là gì, và khác gì với tên lớp?

Xét một class:

~~~java
package com.example.store.service;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public String status() {
        return "READY";
    }
}
~~~

Nếu class nằm trong phạm vi component scan, Spring thường đăng ký một bean với:

| Thuộc tính | Giá trị trong ví dụ |
|---|---|
| Tên class Java | `OrderService` |
| Tên đầy đủ của class | `com.example.store.service.OrderService` |
| Tên bean Spring mặc định | `orderService` |
| Kiểu của bean | `OrderService` |

**Tên bean** là định danh trong container; **kiểu bean** là thông tin dùng để chọn một bean đáp ứng dependency. Tên bean không bắt buộc trùng tên class, cũng không nhất thiết là tên biến Java dùng để tham chiếu đến bean.

Ví dụ:

~~~java
private final OrderService service;
~~~

Tên trường `service` không làm đổi tên bean `orderService` đã đăng ký.

Để Spring quản lý được class, nó phải được đăng ký qua một cơ chế phù hợp như component scanning, `@Bean`, `@Import` hoặc auto-configuration. **Chỉ khai báo class trong một package không tự tạo bean.**

## 2. Quy tắc mặc định với `@Component`, `@Service` và các stereotype

Khi component scan gặp một class được đánh dấu bằng `@Component` hoặc annotation chuyên biệt như `@Service`, `@Repository`, `@Controller`, `@RestController`, Spring thường sử dụng `AnnotationBeanNameGenerator` để sinh tên nếu không có tên tường minh.

Quy tắc cơ bản: lấy **tên class ngắn** (không có phần package) và áp dụng phép chuyển thành tên thuộc tính theo quy tắc JavaBeans, tương tự `Introspector.decapitalize(...)`.

~~~java
package com.example.store;

import org.springframework.stereotype.Component;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.RestController;

@Component
class TaxCalculator {
}

@Service
class CustomerService {
}

@Repository
class CustomerRepositoryAdapter {
}

@RestController
class CustomerController {
}
~~~

Các tên bean mặc định tương ứng:

| Class | Tên bean mặc định |
|---|---|
| `TaxCalculator` | `taxCalculator` |
| `CustomerService` | `customerService` |
| `CustomerRepositoryAdapter` | `customerRepositoryAdapter` |
| `CustomerController` | `customerController` |
| `PaymentAPIClient` | `paymentAPIClient` |
| `URLParser` | `URLParser` |

Hai hàng cuối cho thấy một chi tiết dễ bỏ sót: quy tắc JavaBeans **không phải lúc nào cũng chỉ viết thường ký tự đầu tiên**. Khi **hai ký tự đầu của tên class đều viết hoa**, ví dụ `URLParser`, tên được giữ nguyên `URLParser` thay vì thành `uRLParser`. Vì vậy, đừng suy luận tên bean bằng phép `lowercase(firstCharacter)` cho mọi class.

> Các ví dụ ở bảng giả định class được component scan phát hiện, không bị điều kiện/profile loại trừ và không có cấu hình tên bean khác.

### 2.1. Annotation chuyên biệt vẫn thuộc họ component

`@Service`, `@Repository` và `@Controller` là các stereotype dựa trên `@Component`. Chúng giúp thể hiện vai trò kiến trúc và có thể tham gia các cơ chế xử lý đặc thù. Nhưng xét riêng việc sinh tên mặc định từ class được quét, chúng tuân theo cùng cơ chế cơ bản.

Không nên nhầm interface Spring Data repository với class gắn `@Repository`. Một interface kế thừa `JpaRepository` có thể được đăng ký qua cơ chế Spring Data repository riêng, với quy tắc/cấu hình đặt tên tương ứng. Bài học này tập trung vào **bean component thông thường** và bean từ `@Bean`.

### 2.2. Không lấy đường dẫn file làm tên bean

Nếu đổi nơi lưu file Java trong IDE mà không thay `package` và tên class, quy tắc sinh tên bean vẫn dựa trên định danh class được Spring phát hiện. Package ảnh hưởng chủ yếu đến **phạm vi quét** và khả năng phân biệt class, còn tên bean mặc định thông dụng thường dựa vào **tên class ngắn**.

## 3. Đặt tên chủ động ngay tại component

Khi muốn một tên ổn định, dễ hiểu hoặc cần phân biệt hai implementation, truyền tên vào annotation:

~~~java
package com.example.store.payment;

import org.springframework.stereotype.Service;

@Service("cardPaymentService")
public class CardPaymentService {
    public void pay(long amount) {
        // Xử lý thanh toán bằng thẻ.
    }
}
~~~

Khi đó bean có tên **`cardPaymentService`** do lập trình viên quyết định, thay vì tên suy ra mặc định `cardPaymentService`. Trong ví dụ này hai tên tình cờ giống nhau; giá trị của khai báo tường minh nằm ở chỗ tên bean không tự đổi nếu class được đổi tên:

~~~java
@Service("cardPaymentService")
public class CreditCardPaymentHandler {
    // Tên bean vẫn là "cardPaymentService".
}
~~~

Các stereotype khác cũng hỗ trợ chỉ định tên, chẳng hạn:

~~~java
@Component("exchangeRateCache")
class ExchangeRateCache {
}

@Repository("inventoryGateway")
class JdbcInventoryGateway {
}

@RestController("catalogHttpController")
class CatalogController {
}
~~~

Tên được khai báo trong annotation là tên bean chính của component. Việc đặt tên tường minh **không đổi loại bean**, không tự thiết lập route HTTP và cũng không tạo thêm bản sao bean.

### Khi nào nên chỉ định tên tường minh?

- Khi cần phân biệt **hai component có cùng tên class ngắn** ở hai package khác nhau.
- Khi tên bean là một phần của hợp đồng tích hợp, ví dụ được dùng trong `@Qualifier`, `@Resource` hoặc tra cứu theo tên.
- Khi dự kiến đổi tên class nhưng muốn giữ ổn định định danh bean đã được các thành phần khác sử dụng.
- Khi thư viện hoặc framework tích hợp yêu cầu một bean có tên cụ thể.

Không cần đặt tên thủ công cho **mọi** service. Nếu mỗi kiểu chỉ có một bean, cơ chế tiêm theo kiểu thường rõ ràng hơn và ít phụ thuộc chuỗi tên.

## 4. Quy tắc mặc định với phương thức `@Bean`

Một cách đăng ký khác là đặt `@Bean` lên phương thức factory trong lớp cấu hình Spring:

~~~java
package com.example.store.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PricingConfiguration {

    @Bean
    public PriceCalculator priceCalculator() {
        return new PriceCalculator();
    }
}

class PriceCalculator {
    long total(long price, long shipping) {
        return price + shipping;
    }
}
~~~

Spring tạo bean kiểu `PriceCalculator` từ phương thức factory, và **tên bean mặc định là tên phương thức**: `priceCalculator`.

Điểm này khác quy tắc của `@Component`:

| Cách đăng ký | Nguồn sinh tên mặc định |
|---|---|
| `@Component` trên `PriceCalculator` | Tên class ngắn theo JavaBeans → `priceCalculator` |
| `@Bean` trên phương thức `buildCalculator()` trả `PriceCalculator` | Tên phương thức → `buildCalculator` |

Do đó, cùng một kiểu `PriceCalculator` có thể mang tên bean `priceCalculator`, `buildCalculator` hoặc tên khác tùy cách đăng ký. **Không suy ra tên bean của `@Bean` từ class được return.**

### 4.1. Đặt tên tường minh bằng `@Bean(name = ...)`

~~~java
@Configuration
class ShippingConfiguration {

    @Bean(name = "shippingRateCalculator")
    ShippingCalculator createShippingCalculator() {
        return new ShippingCalculator();
    }
}

class ShippingCalculator {
}
~~~

Mặc dù tên phương thức là `createShippingCalculator`, tên bean do Spring đăng ký là `shippingRateCalculator`.

Cú pháp rút gọn cũng có thể dùng:

~~~java
@Bean("shippingRateCalculator")
ShippingCalculator createShippingCalculator() {
    return new ShippingCalculator();
}
~~~

Hai đoạn trên minh họa **hai lựa chọn cú pháp cho cùng một cách đăng ký**, không đặt đồng thời hai phương thức như vậy trong cùng cấu hình.

### 4.2. Một bean có thể có nhiều alias

Thuộc tính `name` của `@Bean` nhận một mảng tên; tên đầu tiên được sử dụng làm **tên chính**, các tên còn lại là **alias**:

~~~java
@Bean(name = {"primaryRateCalculator", "legacyRateCalculator"})
ShippingCalculator shippingCalculator() {
    return new ShippingCalculator();
}
~~~

Ở đây:

- `primaryRateCalculator` là tên chính.
- `legacyRateCalculator` là alias.
- Cả hai tên tham chiếu **cùng một bean**, không phải hai object độc lập.

Alias hữu ích khi đổi tên bean theo từng bước nhưng còn nơi sử dụng tên cũ. Tuy nhiên, alias cũng là một định danh được container quản lý: đặt tên alias không rõ ràng hoặc trùng tên khác có thể gây xung đột.

## 5. Xem quy trình từ code đến tên bean

~~~text
                       KHAI BÁO BEAN
                             |
                +------------+------------+
                |                         |
          Component scan             Phương thức @Bean
                |                         |
         Có tên tường minh?         Có name/value?
           /          \               /         \
         Có          Không           Có         Không
          |              |            |             |
  Dùng tên chỉ định  Sinh từ tên   Dùng tên được   Dùng tên
                    class ngắn     chỉ định       phương thức
                    kiểu JavaBeans  (+ alias)
                |                         |
                +------------+------------+
                             |
                   Đăng ký vào bean registry
                             |
               Kiểm tra trùng tên và các điều kiện
                             |
                    Bean có tên để truy xuất
~~~

Sơ đồ trên mô tả hai đường tạo bean phổ biến. Ngoài ra, auto-configuration, programmatic registration, `@Import`, factory bean và các cơ chế chuyên biệt khác có thể áp dụng quy tắc đặt tên riêng. **Đừng giả định toàn bộ bean trong context đều có tên bắt đầu bằng chữ thường.**

## 6. Tên bean có phân biệt chữ hoa, chữ thường không?

Trong cách tra cứu bằng tên thông thường, tên bean là chuỗi định danh và **có phân biệt chữ hoa/chữ thường**:

~~~java
@Component("emailSender")
class EmailSender {
}
~~~

`emailSender` và `EmailSender` là hai chuỗi khác nhau. Vì vậy:

~~~java
context.getBean("emailSender"); // Tên đã khai báo.
context.getBean("EmailSender"); // Không phải cùng tên; có thể không tìm thấy.
~~~

Không nên tự viết hoa hoặc viết thường chuỗi bean name khi dùng `@Qualifier`, `@Resource`, expression hoặc API tra cứu theo tên. Việc Spring có thể dùng alias, pattern matching hay fallback trong một số cơ chế resolution không thay đổi nguyên tắc: **hãy dùng chính xác định danh đã đăng ký**.

Tên bean có thể chứa dấu chấm hoặc các ký tự hợp lệ khác, nhưng nên chọn quy ước dễ hiểu, nhất quán trong dự án. Với bean ứng dụng thông thường, `lowerCamelCase` như `emailSender` hoặc `orderRepository` là lựa chọn quen thuộc.

## 7. Hai class cùng tên ngắn có thể làm component scan xung đột

Xét dự án:

~~~text
com.example.shop
├── ShopApplication
├── sales
│   └── ReportService.java
└── support
    └── ReportService.java
~~~

Cả hai class đều có:

~~~java
@Service
public class ReportService {
}
~~~

Hai file là **hai class khác nhau** vì package khác nhau:

~~~text
com.example.shop.sales.ReportService
com.example.shop.support.ReportService
~~~

Nhưng tên bean mặc định của cả hai đều là `reportService`. Nếu cả hai nằm trong cùng phạm vi scan và cùng được đăng ký vào một bean registry, Spring có thể báo lỗi **xung đột bean definition** khi quét, chẳng hạn một `ConflictingBeanDefinitionException`.

Đây là **trùng tên bean khi đăng ký**, không chỉ là vấn đề tiêm phụ thuộc có nhiều ứng viên.

### Cách 1: Đặt tên rõ vai trò

~~~java
// com.example.shop.sales.ReportService
@Service("salesReportService")
public class ReportService {
}
~~~

~~~java
// com.example.shop.support.ReportService
@Service("supportReportService")
public class ReportService {
}
~~~

Lúc này registry có hai tên khác nhau, `salesReportService` và `supportReportService`.

### Cách 2: Đổi tên class theo ngữ cảnh

Ví dụ `SalesReportService` và `SupportReportService`. Khi dùng quy tắc mặc định, Spring sẽ sinh `salesReportService` và `supportReportService`. Cách này thường giúp code dễ đọc hơn nếu hai class thực sự có trách nhiệm khác nhau.

### Cách 3: Dùng chiến lược sinh tên khác cho component scan

Spring cung cấp `FullyQualifiedAnnotationBeanNameGenerator`, có thể dùng tên class đầy đủ làm tên mặc định khi không chỉ định tên:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.FullyQualifiedAnnotationBeanNameGenerator;

@SpringBootApplication(
        nameGenerator = FullyQualifiedAnnotationBeanNameGenerator.class
)
public class ShopApplication {
    public static void main(String[] args) {
        org.springframework.boot.SpringApplication.run(
                ShopApplication.class, args);
    }
}
~~~

Với chiến lược này, các component không có tên tường minh có thể nhận tên như:

~~~text
com.example.shop.sales.ReportService
com.example.shop.support.ReportService
~~~

Đây là lựa chọn có tác động rộng tới tên bean của những component được scan. Chỉ áp dụng khi có chủ đích; nếu code hiện hữu đang dùng chuỗi tên mặc định trong `@Qualifier`, `@Resource`, `getBean(...)` hoặc cấu hình tích hợp thì phải điều chỉnh tương ứng.

## 8. Trùng tên bean khác với nhiều bean cùng kiểu

Hai tình huống thường bị đánh đồng:

**Tình huống A — Trùng tên:** hai bean definition tranh cùng tên `notificationSender`. Đây là xung đột khi đăng ký tên.

**Tình huống B — Trùng kiểu:** hai bean có tên khác nhau, nhưng cùng triển khai interface `NotificationSender`. Đăng ký có thể thành công; lỗi chỉ xuất hiện khi Spring cần chọn **một** bean theo kiểu mà không đủ thông tin phân biệt.

Ví dụ hai implementation:

~~~java
package com.example.shop.notification;

public interface NotificationSender {
    void send(String message);
}
~~~

~~~java
package com.example.shop.notification;

import org.springframework.stereotype.Component;

@Component("emailSender")
public class EmailSender implements NotificationSender {
    @Override
    public void send(String message) {
        // Gửi email.
    }
}
~~~

~~~java
package com.example.shop.notification;

import org.springframework.stereotype.Component;

@Component("smsSender")
public class SmsSender implements NotificationSender {
    @Override
    public void send(String message) {
        // Gửi SMS.
    }
}
~~~

Đã có hai bean, tên khác nhau:

| Bean name | Kiểu cụ thể | Kiểu interface |
|---|---|---|
| `emailSender` | `EmailSender` | `NotificationSender` |
| `smsSender` | `SmsSender` | `NotificationSender` |

Nếu cần tiêm một `NotificationSender` mà không có thông tin chọn lựa, Spring có thể ném `NoUniqueBeanDefinitionException`. Đổi một tên bean sẽ **không tự giải quyết** tính mơ hồ theo kiểu nếu vẫn có hai ứng viên hợp lệ.

## 9. Chọn đúng bean bằng `@Qualifier`

Khi biết rõ implementation nào được sử dụng, có thể chỉ định:

~~~java
package com.example.shop.notification;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class MessageService {
    private final NotificationSender sender;

    public MessageService(
            @Qualifier("emailSender") NotificationSender sender) {
        this.sender = sender;
    }

    public void notifyCustomer(String message) {
        sender.send(message);
    }
}
~~~

`@Qualifier("emailSender")` yêu cầu Spring lọc ứng viên theo qualifier phù hợp. Trong tình huống trên, tên bean `emailSender` là một ứng viên phù hợp với giá trị qualifier. Tuy nhiên, **qualifier không phải lúc nào cũng chỉ là tên bean**: Spring cho phép khai báo metadata qualifier độc lập để phân nhóm/chọn bean. Khi đọc code, cần phân biệt “giá trị qualifier” với “tên bean đã đăng ký”.

Một phương án khác, khi một implementation là lựa chọn mặc định, là `@Primary`:

~~~java
@Primary
@Component("emailSender")
class EmailSender implements NotificationSender {
    @Override
    public void send(String message) {
        // Gửi email.
    }
}
~~~

`@Primary` ưu tiên bean này trong nhiều trường hợp tiêm một đối tượng theo kiểu; tên bean vẫn là `emailSender`. Khi đã khai báo `@Qualifier` cụ thể, lựa chọn theo qualifier có thể thu hẹp tập ứng viên trước khi xét `@Primary`.

Các lựa chọn được dùng theo mục đích:

| Cơ chế | Giải quyết vấn đề gì? | Có đổi tên bean không? |
|---|---|---|
| `@Component("emailSender")` | Chỉ định định danh cho component | Có |
| `@Bean("emailSender")` | Chỉ định định danh cho bean từ phương thức factory | Có |
| `@Qualifier("emailSender")` | Giới hạn bean được chọn khi inject | Không |
| `@Primary` | Đặt ứng viên ưu tiên khi có nhiều bean cùng kiểu | Không |
| `@Resource(name = "emailSender")` | Yêu cầu tiêm tài nguyên theo tên | Không |

`@Resource` thuộc Jakarta Annotations trong các ứng dụng Spring hiện đại có dependency phù hợp; có thể hữu ích khi ý định là liên kết theo tên cụ thể.

### Có thể Spring dùng tên parameter khi tiêm?

Với constructor injection hoặc `@Autowired`, Spring chủ yếu giải quyết dependency **theo kiểu**. Khi có nhiều ứng viên, Spring có thể dùng thêm qualifier, primary và **tên parameter/field** theo các quy tắc resolution nếu metadata cần thiết tồn tại.

~~~java
public MessageService(NotificationSender emailSender) {
    this.sender = emailSender;
}
~~~

Trong một cấu hình phù hợp, tên tham số `emailSender` có thể giúp chọn bean cùng tên. Tuy nhiên, cơ chế này phụ thuộc metadata tên tham số và các điều kiện resolution, chẳng hạn Java compilation cần xuất tên tham số (thường qua `-parameters` đối với Spring Framework hiện đại). **Đừng coi tên biến là hợp đồng chọn bean ổn định** trong tình huống nhiều implementation quan trọng; `@Qualifier` nói rõ ý định và dễ kiểm soát hơn.

## 10. Tên bean trong application context và cơ chế override

Thông thường, tên bean phải **duy nhất trong cùng một bean registry**. Nếu hai nguồn cấu hình cùng khai báo bean name giống nhau, điều gì xảy ra phụ thuộc loại đăng ký và chính sách cho phép ghi đè.

Ví dụ:

~~~java
@Configuration
class FirstConfiguration {
    @Bean("paymentGateway")
    PaymentGateway firstGateway() {
        return new PaymentGateway("first");
    }
}

@Configuration
class SecondConfiguration {
    @Bean("paymentGateway")
    PaymentGateway secondGateway() {
        return new PaymentGateway("second");
    }
}
~~~

Giả sử `PaymentGateway` có constructor nhận `String`. Nếu cả hai cấu hình được nạp vào cùng registry, chúng cạnh tranh tên `paymentGateway`.

Với Spring Boot hiện đại, việc ghi đè bean definition **được tắt theo mặc định**, nên một số xung đột kiểu này có thể dẫn tới lỗi `BeanDefinitionOverrideException`. Có thể điều chỉnh chính sách:

~~~properties
spring.main.allow-bean-definition-overriding=true
~~~

Nhưng bật override đại trà thường che giấu sự cố và làm khó dự đoán bean cuối cùng được chọn. Một số xung đột trong component scanning còn có thể thất bại theo cơ chế kiểm tra riêng, vì vậy **bật override không phải cách sửa chung cho mọi lỗi trùng tên**.

Giải pháp phù hợp thường là sửa lại tên và phạm vi đăng ký bean, dùng `@ConditionalOnMissingBean` trong thư viện auto-configuration khi muốn cung cấp mặc định, hoặc loại bỏ cấu hình trùng lặp.

Lưu ý: một ứng dụng có nhiều application context theo quan hệ cha–con có thể có bean cùng tên ở các context khác nhau, với khả năng che khuất khi tra cứu theo ngữ cảnh. Quy tắc “duy nhất” ở đây xét **mỗi registry/context**, không nhất thiết toàn bộ JVM.

## 11. Khi đổi tên bean, những điểm nào chịu ảnh hưởng?

Giả sử ban đầu:

~~~java
@Service("invoiceService")
class InvoiceService {
}
~~~

Sau khi đổi thành:

~~~java
@Service("billingService")
class InvoiceService {
}
~~~

Code tiêm theo **kiểu duy nhất** `InvoiceService` thường vẫn có thể hoạt động. Nhưng nơi tham chiếu trực tiếp tên `invoiceService` có thể cần sửa, ví dụ:

- `@Qualifier("invoiceService")` hoặc `@Resource(name = "invoiceService")`.
- `applicationContext.getBean("invoiceService")`.
- Các biểu thức SpEL tham chiếu bean bằng tên, ví dụ `@invoiceService`.
- Cấu hình/framework tích hợp chọn bean theo tên, hoặc điều kiện có yêu cầu bean name cụ thể.

Nếu cần chuyển đổi có kiểm soát, cân nhắc alias (đặc biệt với `@Bean(name = {...})`) hoặc một cơ chế đăng ký alias phù hợp. Đổi tên class mà giữ tên bean tường minh thường an toàn hơn cho các thành phần phụ thuộc vào tên.

Tên bean cũng **khác** với:

| Tên | Ý nghĩa |
|---|---|
| `spring.application.name` | Định danh ứng dụng phục vụ cấu hình/quan sát/tích hợp |
| Tên bảng JPA (`@Table`) | Định danh bảng dữ liệu |
| Tên mapping HTTP (`@RequestMapping`, `@GetMapping`) | Đường dẫn hoặc thuộc tính định tuyến request |
| Tên class Java | Định danh class trong code |
| Bean name | Định danh bean trong Spring container |

Đổi `spring.application.name` không tự đổi tên tất cả bean; đặt tên controller bean không tự đổi URL API.

## 12. Cách quan sát tên bean đang được đăng ký

Nếu không chắc Spring đã tạo bean với tên gì, có thể truy vấn `ApplicationContext`. Ví dụ dưới đây là đoạn minh họa để chạy trong ứng dụng thử nghiệm:

~~~java
package com.example.store;

import java.util.Arrays;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class BeanInspectionConfiguration {

    @Bean
    CommandLineRunner printBeanNames(ApplicationContext context) {
        return args -> {
            String[] names = context.getBeanNamesForType(
                    com.example.store.service.OrderService.class);
            Arrays.stream(names).forEach(System.out::println);
        };
    }
}
~~~

Khi class `OrderService` được đăng ký bằng `@Service` như ví dụ đầu và không có bean khác cùng kiểu, kết quả thường là:

~~~text
orderService
~~~

Lệnh trên liệt kê **tên bean theo kiểu**, giúp phân biệt tên bean thực tế với suy đoán từ tên class. Một số lựa chọn quan sát khác:

~~~java
context.containsBean("orderService");
context.getAliases("orderService");
context.getBean("orderService");
~~~

`containsBean(...)` kiểm tra tên/alias có được nhận diện hay không; `getAliases(...)` cho biết alias mà context công khai cho tên đó; `getBean(...)` lấy instance và có thể kích hoạt tạo bean lazy tùy tình huống. Khi chỉ muốn **kiểm tra danh sách tên**, ưu tiên các phương thức tra cứu metadata và tránh gọi khởi tạo bean không cần thiết.

Spring Boot Actuator cung cấp endpoint `beans` để quan sát các bean theo context khi có starter Actuator và endpoint được bật/expose phù hợp. Không nên công khai endpoint chẩn đoán này trên Internet nếu chưa kiểm soát truy cập, vì nó có thể tiết lộ thông tin cấu trúc nội bộ.

### Các thông báo lỗi thường gặp

| Dạng lỗi | Ý nghĩa cần kiểm tra |
|---|---|
| `NoSuchBeanDefinitionException` khi tra cứu theo tên | Tên bean có đúng chữ hoa/thường không? Có alias không? Bean đã được đăng ký trong context đang dùng chưa? |
| `NoUniqueBeanDefinitionException` khi tiêm theo interface | Có nhiều bean hợp lệ cùng kiểu; cần `@Qualifier`/`@Primary` hoặc điều chỉnh thiết kế |
| `ConflictingBeanDefinitionException` khi scan | Nhiều component cùng sinh một tên bean nhưng là các định nghĩa không tương thích |
| `BeanDefinitionOverrideException` | Có attempt đăng ký lại tên bean trong context không cho phép override |

Không phải tất cả các lỗi trên đều do quy tắc đặt tên: bean còn có thể không tồn tại vì package scan, profile, điều kiện auto-configuration, thiếu dependency hoặc cấu hình riêng.

## 13. Quy tắc đặt tên chủ động trong dự án thực tế

Một chiến lược đơn giản, dễ duy trì:

1. **Mặc định dùng tên sinh tự động** cho component khi chỉ có một bean đúng kiểu và không có hợp đồng dùng tên cụ thể.
2. **Đặt tên rõ ngữ nghĩa** khi có nhiều implementation hoặc một tích hợp cần chọn bean theo tên. Ví dụ `primaryPaymentGateway` và `backupPaymentGateway` diễn đạt vai trò rõ hơn `gateway1` và `gateway2`.
3. **Nhớ rằng `@Bean` mặc định lấy tên phương thức.** Nếu đổi tên phương thức factory, hãy xem nơi nào đang dựa vào tên bean.
4. **Đừng dựa vào override để giải quyết tên trùng.** Đặt lại tên hoặc thu hẹp phạm vi scan/cấu hình để tránh định nghĩa xung đột.
5. **Dùng `@Qualifier` khi việc chọn implementation phải rõ ràng.** Không phụ thuộc vào việc tên biến Java tình cờ trùng tên bean.
6. **Kiểm tra bean name thực tế** qua `ApplicationContext`, log lỗi hoặc Actuator trong môi trường phù hợp trước khi suy đoán.

Ví dụ kiến trúc ứng dụng:

~~~text
com.example.store
├── StoreApplication.java
├── payment
│   ├── PaymentGateway.java          (interface)
│   ├── StripeGateway.java           (@Component("stripeGateway"))
│   ├── BankTransferGateway.java     (@Component("bankTransferGateway"))
│   └── CheckoutService.java         (@Service; dùng @Qualifier)
└── config
    └── CheckoutConfiguration.java   (@Bean("checkoutPolicy"))
~~~

Nếu `StoreApplication` ở package gốc và các class này được scan/import đúng cách, ứng dụng có thể có những tên như:

~~~text
storeApplication
stripeGateway
bankTransferGateway
checkoutService
checkoutConfiguration
checkoutPolicy
~~~

Hai bean `storeApplication` và `checkoutConfiguration` phản ánh việc lớp cấu hình cũng có thể được đăng ký làm bean; các tên chính xác phụ thuộc cách phát hiện và cấu hình. `PaymentGateway` chỉ là interface nên không tự sinh bean từ interface đó. `checkoutPolicy` đến từ tên chỉ định trên phương thức `@Bean`, không suy ra từ kiểu trả về.

**Điểm cần ghi nhớ:** Với component được scan, Spring thường sinh tên bằng quy tắc JavaBeans từ **tên class ngắn**; với phương thức `@Bean`, mặc định là **tên phương thức**. Ta có thể đặt tên tường minh cho cả hai, và có thể khai báo alias khi thích hợp. Tên bean dùng để **định danh trong container**, còn việc chọn bean để tiêm phụ thuộc vào **kiểu, qualifier, primary và các quy tắc resolution**. Phân biệt rõ hai vai trò này giúp xử lý chính xác cả lỗi trùng tên lẫn lỗi nhiều bean cùng kiểu.
