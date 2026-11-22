# Đụng tên bean, nhiều bean cùng type và hai loại xung đột cần phân biệt

Trong ứng dụng Spring Boot, bạn có thể đăng ký nhiều bean bằng `@Component`, `@Service`, `@Repository`, `@Controller` hoặc `@Bean`. Khi số lượng bean tăng lên, hai lỗi dễ bị gọi chung là “trùng bean” thường xuất hiện:

1. **Đụng tên bean**: hai định nghĩa cố đăng ký vào cùng một **bean name** trong một container, dẫn đến xung đột ở giai đoạn đăng ký định nghĩa bean.
2. **Nhiều bean cùng type**: container có nhiều bean khác nhau cùng phù hợp với một kiểu cần inject; nếu không có quy tắc chọn rõ ràng, Spring không biết phải cung cấp bean nào.

Đây là **hai loại xung đột khác nhau**, xảy ra ở những bước khác nhau và cần giải pháp khác nhau. Đổi tên bean có thể xử lý xung đột tên, nhưng chưa chắc giải quyết được sự nhập nhằng theo type. Ngược lại, thêm `@Primary` hoặc `@Qualifier` có thể giúp Spring chọn bean khi inject, nhưng không làm hai bean definition trùng tên cùng tồn tại.

Bài học thuộc chương **Đăng ký bean** của **Spring Boot Fundamentals**. Chúng ta sẽ đi từ nguyên lý đăng ký bean, xây dựng ví dụ gây lỗi có chủ đích, đọc log Spring Boot và lựa chọn cách sửa phù hợp.

## 1. Spring quản lý bean bằng tên và kiểu như thế nào?

Một *Spring bean* là một đối tượng được IoC container quản lý. Container lưu các **bean definition**, từ đó có thể tạo instance, xử lý dependency và quản lý vòng đời.

Mỗi bean definition có một **tên chính** (*bean name*); bean có thể có thêm alias. Container cũng biết hoặc suy ra những kiểu Java mà instance của bean có thể đáp ứng.

Ví dụ:

```java
package com.example.shop.payment;

public interface PaymentGateway {
    String charge(long amount);
}
```

```java
package com.example.shop.payment;

import org.springframework.stereotype.Service;

@Service("cardGateway")
public class CardPaymentGateway implements PaymentGateway {

    @Override
    public String charge(long amount) {
        return "Đã thanh toán " + amount + " qua thẻ";
    }
}
```

Ở đây:

- **Tên bean:** `cardGateway` do khai báo rõ trong `@Service("cardGateway")`.
- **Kiểu triển khai:** `CardPaymentGateway`.
- **Một kiểu mà bean đáp ứng:** `PaymentGateway` vì class implements interface này.
- **Instance:** đối tượng được Spring tạo và quản lý khi bean được khởi tạo.

Một bean có thể đáp ứng nhiều kiểu (class, interface, superclass), nhưng không vì vậy mà biến thành nhiều bean khác nhau.

### 1.1. Hai câu hỏi độc lập

Khi đăng ký và sử dụng bean, Spring lần lượt cần trả lời các câu hỏi tương ứng:

```text
ĐĂNG KÝ
  "Tên này đã được dùng cho một định nghĩa bean khác chưa?"
                     │
                     ▼
        Bean definitions trong container
                     │
                     ▼
SỬ DỤNG / INJECTION
  "Trong các bean phù hợp type được yêu cầu,
   bean nào cần được đưa vào đây?"
```

Một dự án có thể vượt qua giai đoạn đăng ký bean mà vẫn thất bại khi inject dependency. Điều đó xảy ra khi **tên không trùng**, nhưng **có nhiều bean cùng phù hợp type**.

### 1.2. Một sơ đồ giúp phân biệt

```text
TÌNH HUỐNG A — ĐỤNG TÊN
    bean name: "paymentGateway"  ← định nghĩa từ ConfigA
    bean name: "paymentGateway"  ← định nghĩa từ ConfigB
                    │
                    ▼
       Đụng cùng khóa đăng ký bean
       (thường thất bại trước khi inject)

TÌNH HUỐNG B — NHIỀU BEAN CÙNG TYPE
    bean name: "cardGateway"      ─┐
                                   ├── đều là PaymentGateway
    bean name: "bankGateway"      ─┘
                    │
                    ▼
    OrderService(PaymentGateway gateway)
                    │
                    ▼
      Không biết chọn bean nào
      nếu không có chỉ dẫn phù hợp
```

Đây là điểm phân biệt cốt lõi của bài học: **name collision** và **type ambiguity**.

## 2. Bean name được tạo từ đâu?

Khi đọc lỗi đụng tên, cần biết Spring đã gán tên bean từ nguồn nào. Tên có thể được chỉ định rõ hoặc được sinh theo quy ước.

| Cách đăng ký | Ví dụ | Tên bean thường dùng |
|---|---|---|
| `@Component` mặc định | `@Component class FileParser` | `fileParser` |
| `@Service` mặc định | `@Service class EmailSender` | `emailSender` |
| `@Repository` mặc định | `@Repository class OrderRepository` | `orderRepository` |
| `@RestController` mặc định | `@RestController class OrderController` | `orderController` |
| `@Component` đặt tên rõ | `@Component("csvParser")` | `csvParser` |
| `@Service` đặt tên rõ | `@Service("fastSender")` | `fastSender` |
| `@Bean` không chỉ định tên | `@Bean PaymentGateway gateway()` | `gateway` |
| `@Bean` đặt tên rõ | `@Bean("cardGateway")` | `cardGateway` |

Các annotation như `@Service` và `@RestController` là stereotype dựa trên `@Component`; Spring có thể phát hiện chúng qua component scanning.

Với tên mặc định của component, Spring thường lấy tên class ngắn và xử lý quy tắc viết thường chữ đầu. Có những trường hợp chữ viết hoa liên tiếp được giữ theo quy tắc JavaBeans, vì vậy đừng suy luận máy móc rằng mọi acronym luôn được chuyển hết sang chữ thường.

### 2.1. Tên bean không phải tên đầy đủ của class

Hai class:

```text
com.example.shop.mail.EmailSender
com.example.shop.audit.EmailSender
```

có **tên đầy đủ của class khác nhau** nhưng tên bean mặc định khi scan có thể đều là:

```text
emailSender
```

Package Java giúp JVM phân biệt hai class, **không bảo đảm bean name mặc định phân biệt được chúng**.

Đây là một nguồn đụng tên phổ biến trong dự án được tổ chức theo nhiều package.

### 2.2. `@Bean` có thể khai báo alias

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class GatewayConfiguration {

    @Bean(name = {"primaryCardGateway", "cardGatewayAlias"})
    public PaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }
}
```

Trong cấu hình này, `primaryCardGateway` là tên chính và `cardGatewayAlias` là một alias của cùng bean definition. Hai tên đó **không có nghĩa Spring tạo hai đối tượng độc lập**. Việc đăng ký alias vẫn phải phù hợp với các quy tắc tên của container.

Trong các ví dụ tiếp theo, để tránh phức tạp, mỗi bean chỉ sử dụng một tên chính.

## 3. Xung đột loại 1: hai bean definition đụng cùng tên

Giả sử ứng dụng có hai lớp cấu hình đều nằm trong package được quét:

```text
com.example.shop
├── ShopApplication.java
└── config/
    ├── DefaultGatewayConfiguration.java
    └── ExperimentalGatewayConfiguration.java
```

Lớp cấu hình thứ nhất:

```java
package com.example.shop.config;

import com.example.shop.payment.PaymentGateway;
import com.example.shop.payment.CardPaymentGateway;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DefaultGatewayConfiguration {

    @Bean("paymentGateway")
    public PaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }
}
```

Lớp thứ hai:

```java
package com.example.shop.config;

import com.example.shop.payment.PaymentGateway;
import com.example.shop.payment.BankPaymentGateway;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ExperimentalGatewayConfiguration {

    @Bean("paymentGateway")
    public PaymentGateway bankGateway() {
        return new BankPaymentGateway();
    }
}
```

Ở ví dụ này giả định `CardPaymentGateway` và `BankPaymentGateway` là các class có constructor không tham số hợp lệ, cùng implements `PaymentGateway`.

Mỗi configuration khai báo một phương thức `@Bean` khác tên Java (`cardGateway()` và `bankGateway()`), nhưng cả hai **đăng ký cùng tên bean `paymentGateway`**.

Đối với một registry bean definition, điều này tương tự cố gắng gán hai định nghĩa khác nhau cho một khóa:

```text
"paymentGateway" -> định nghĩa từ DefaultGatewayConfiguration

"paymentGateway" -> định nghĩa từ ExperimentalGatewayConfiguration
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                     đụng khóa đã được đăng ký
```

### 3.1. Spring Boot thường báo lỗi gì?

Trong Spring Boot hiện đại, tính năng ghi đè bean definition thường **bị tắt theo mặc định**. Với ví dụ hai định nghĩa cùng tên, log có thể chứa thông báo theo ý nghĩa:

```text
The bean 'paymentGateway', defined in class path resource
[.../ExperimentalGatewayConfiguration.class], could not be registered.

A bean with that name has already been defined in
[.../DefaultGatewayConfiguration.class] and overriding is disabled.
```

Một exception thường liên quan là:

```text
org.springframework.beans.factory.support.BeanDefinitionOverrideException
```

Tùy nguồn đăng ký và pha xử lý, lỗi đụng tên có thể có exception cụ thể khác; ví dụ xung đột khi component scanner quét hai class có cùng tên bean có thể liên quan đến `ConflictingBeanDefinitionException`. Đừng chỉ dựa vào một tên exception cố định; hãy nhìn kỹ **bean name** và **hai nguồn bean definition**.

Điều quan trọng: đây là **xung đột khi đăng ký tên**. Spring chưa cần thử inject `PaymentGateway` vào service nào để nhận ra vấn đề.

### 3.2. Cách sửa đúng: thiết kế lại tên hoặc điều kiện đăng ký

Nếu hai bean thực sự phải cùng tồn tại, hãy đặt **hai tên khác nhau**:

```java
@Bean("cardGateway")
public PaymentGateway cardGateway() {
    return new CardPaymentGateway();
}
```

```java
@Bean("bankGateway")
public PaymentGateway bankGateway() {
    return new BankPaymentGateway();
}
```

Khi ấy không còn đụng name, nhưng vì cả hai đều mang type `PaymentGateway`, application **có thể chuyển sang gặp xung đột loại 2** khi một thành phần inject `PaymentGateway` đơn lẻ mà chưa có lựa chọn rõ ràng.

Nếu chỉ một bean được phép tồn tại ở một môi trường, có thể dùng `@Profile` hoặc `@Conditional` để các cấu hình **loại trừ nhau theo điều kiện**. Nếu một bean chỉ là cấu hình thử nghiệm đã không còn được dùng, loại bỏ định nghĩa thừa cũng là một cách giải quyết đúng.

Việc sửa cần dựa vào ý nghĩa nghiệp vụ: **muốn có hai gateway đồng thời**, hay **chỉ muốn một gateway ở mỗi môi trường**?

## 4. Đụng tên khi component scan: hai class khác package cùng tên ngắn

Một tình huống khác không cần `@Bean`:

```java
// com.example.shop.notifications.EmailSender
package com.example.shop.notifications;

import org.springframework.stereotype.Component;

@Component
public class EmailSender {
}
```

```java
// com.example.shop.audit.EmailSender
package com.example.shop.audit;

import org.springframework.stereotype.Component;

@Component
public class EmailSender {
}
```

Nếu cả hai package nằm trong vùng component scanning, bean name mặc định cho từng class có thể đều là `emailSender`.

Khi Spring tìm được hai candidate không tương thích cùng tên, có thể xuất hiện lỗi kiểu:

```text
ConflictingBeanDefinitionException:
Annotation-specified bean name 'emailSender'
for bean class [...] conflicts with existing,
non-compatible bean definition of same name [...]
```

Tùy hoàn cảnh, cơ chế scanner và định nghĩa bean đang tồn tại có thể dẫn đến hành vi hoặc thông báo khác. Nhưng nguyên nhân chung là **hai nguồn đăng ký cùng muốn chiếm tên `emailSender`**.

### 4.1. Đặt tên có chủ đích cho component

Nếu cả hai đều cần dùng:

```java
@Component("notificationEmailSender")
public class EmailSender {
}
```

và:

```java
@Component("auditEmailSender")
public class EmailSender {
}
```

Mỗi class phải nằm trong package riêng đã khai báo đúng. Trong ví dụ, hai class Java cùng tên ngắn vẫn tồn tại bình thường vì package khác nhau; còn bean names được phân biệt rõ để registry không đụng khóa.

Đặt tên dựa trên **trách nhiệm của bean** thường dễ đọc hơn việc thêm số thứ tự tùy ý.

### 4.2. Đổi Java class name khác gì đổi bean name?

- **Đổi class name** có thể làm thay đổi tên bean mặc định, nhưng cũng ảnh hưởng cách code Java tham chiếu class.
- **Đặt bean name trực tiếp** bằng `@Component("...")` hoặc `@Bean("...")` giúp chỉ rõ danh tính container mà không nhất thiết đổi class.
- **Đổi package** của class không đảm bảo đổi tên bean mặc định nếu bean name vẫn lấy từ tên class ngắn.

Khi hệ thống có nhiều module, nên tạo quy ước bean name hoặc thiết kế stereotype sao cho dễ phân biệt các trách nhiệm.

## 5. Có nên bật bean definition overriding không?

Spring Boot hỗ trợ thuộc tính cấu hình:

```yaml
spring:
  main:
    allow-bean-definition-overriding: true
```

Khi bật, container có thể cho phép một bean definition đăng ký sau **thay thế** định nghĩa trước có cùng tên, trong những trường hợp cơ chế đăng ký cho phép. Việc này không có nghĩa có hai bean cùng tên cùng tồn tại trong một registry.

Nhưng với xung đột tình cờ, đây **không phải cách sửa nên dùng đầu tiên**:

- Một định nghĩa có thể âm thầm thay thế định nghĩa khác.
- Hành vi có thể phụ thuộc quá trình đăng ký bean definitions.
- Đọc log và xác định vì sao một bean “biến mất” trở nên khó hơn.
- Việc có hai bean cùng type cho nhu cầu khác nhau vẫn không được giải quyết rõ ràng.

Cũng không nên nghĩ rằng bật thuộc tính trên sẽ xử lý **mọi dạng lỗi component scan**; không phải mọi xung đột khi phát hiện metadata đều là tình huống registry cho phép ghi đè.

**Nếu mục đích là hai bean khác nhau cùng hoạt động, hãy cho chúng hai tên khác nhau.** Nếu mục đích là một bean thay thế bean mặc định của thư viện, cần hiểu cơ chế mở rộng của thư viện, điều kiện cấu hình và quy ước override trước khi lựa chọn.

### 5.1. Spring Boot auto-configuration thường cố tránh va chạm ra sao?

Nhiều auto-configuration của Spring Boot có điều kiện theo kiểu:

```java
@ConditionalOnMissingBean
```

Điều đó giúp cấu hình tự động **không tạo một bean mặc định** trong những trường hợp điều kiện xác định rằng ứng dụng đã cung cấp bean phù hợp.

Ví dụ khái niệm:

```text
Ứng dụng cung cấp CustomClock
               │
               ▼
Điều kiện kiểm tra bean hiện có
               │
        ┌──────┴──────┐
        ▼             ▼
   Đã có bean      Chưa có bean
        │             │
        ▼             ▼
  Bỏ qua default   Tạo default
```

Tuy nhiên, `@ConditionalOnMissingBean` có thể kiểm tra theo type, name hoặc annotation tùy cấu hình; kết quả còn phụ thuộc **thời điểm đăng ký định nghĩa bean**. Nó không phải cơ chế chung bảo đảm mọi bean trong mọi project không bao giờ đụng tên. Trong ứng dụng bình thường, hãy để các auto-configuration của Boot quản lý mặc định của chúng và chỉ thay thế khi có mục đích rõ ràng.

## 6. Xung đột loại 2: nhiều bean khác tên cùng phù hợp một type

Bây giờ xét tình huống hai bean đã đăng ký thành công:

```java
package com.example.shop.payment;

public interface PaymentGateway {
    String charge(long amount);
}
```

Implementation thứ nhất:

```java
package com.example.shop.payment;

import org.springframework.stereotype.Service;

@Service("cardGateway")
public class CardPaymentGateway implements PaymentGateway {

    @Override
    public String charge(long amount) {
        return "Card: " + amount;
    }
}
```

Implementation thứ hai:

```java
package com.example.shop.payment;

import org.springframework.stereotype.Service;

@Service("bankGateway")
public class BankPaymentGateway implements PaymentGateway {

    @Override
    public String charge(long amount) {
        return "Bank: " + amount;
    }
}
```

Trong container lúc này:

| Bean name | Bean type cụ thể | Có đáp ứng `PaymentGateway`? |
|---|---|---|
| `cardGateway` | `CardPaymentGateway` | Có |
| `bankGateway` | `BankPaymentGateway` | Có |

Hai bean **không trùng tên**, vì vậy bước đăng ký có thể hoàn toàn hợp lệ.

Nhưng service sau yêu cầu **một** dependency duy nhất:

```java
package com.example.shop.checkout;

import com.example.shop.payment.PaymentGateway;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public String checkout(long amount) {
        return gateway.charge(amount);
    }
}
```

Spring phải tìm một bean phù hợp `PaymentGateway` cho tham số constructor `gateway`. Kết quả tìm kiếm có hai ứng viên và không có dấu hiệu đủ để xác định một ứng viên.

Thông báo có thể có dạng:

```text
Parameter 0 of constructor in com.example.shop.checkout.CheckoutService
required a single bean, but 2 were found:
    - cardGateway
    - bankGateway
```

Exception liên quan thường là `NoUniqueBeanDefinitionException`; trong quá trình khởi tạo bean, nó cũng có thể được bọc trong `UnsatisfiedDependencyException`.

Đây là **nhập nhằng khi resolve dependency theo type**, không phải xung đột bean name. Hai bean đều có thể tồn tại trong container; vấn đề chỉ xuất hiện tại điểm Spring cần chọn **một bean**.

### 6.1. Vì sao `PaymentGateway` là kiểu bị nhập nhằng?

Lệnh inject yêu cầu interface:

```java
public CheckoutService(PaymentGateway gateway)
```

Cả `CardPaymentGateway` và `BankPaymentGateway` đều implements `PaymentGateway`. Không có quy tắc nào trong đoạn code trên nói “hãy dùng thẻ” hoặc “hãy dùng ngân hàng”.

Nếu code yêu cầu kiểu cụ thể:

```java
public CheckoutService(CardPaymentGateway gateway)
```

thì có thể chỉ còn một bean phù hợp, nhưng service sẽ phụ thuộc trực tiếp implementation, làm giảm khả năng thay đổi chiến lược và kiểm thử. Việc dùng một interface cộng với lựa chọn bean rõ ràng thường hợp lý hơn nếu nghiệp vụ cần trừu tượng hóa payment gateway.

### 6.2. Spring có thể dùng tên tham số không?

Trong một số tình huống, khi có nhiều ứng viên cùng type và tên điểm inject khớp với bean name, Spring có thể sử dụng thông tin tên tham số hoặc field name làm một trong các quy tắc lựa chọn. Khả năng này phụ thuộc metadata được giữ lại lúc biên dịch và quy tắc resolution của phiên bản Spring.

Ví dụ:

```java
public CheckoutService(PaymentGateway cardGateway)
```

có thể được resolve theo tên trong điều kiện phù hợp, nhưng **không nên biến việc tình cờ trùng tên biến thành hợp đồng cấu hình quan trọng**. Khi yêu cầu lựa chọn có ý nghĩa nghiệp vụ, `@Qualifier` biểu đạt ý định rõ hơn.

Tương tự, sự tồn tại của `@Primary` hoặc một số quy tắc ưu tiên khác có thể ảnh hưởng kết quả trước hoặc cùng quá trình lựa chọn theo tên. Vì thế không nên suy luận rằng Spring luôn lấy bean có tên trùng tên tham số bất kể hoàn cảnh.

## 7. Cách xử lý nhiều bean cùng type bằng `@Primary`

Nếu ứng dụng có một implementation là lựa chọn mặc định, có thể đánh dấu nó bằng `@Primary`:

```java
package com.example.shop.payment;

import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Service;

@Primary
@Service("cardGateway")
public class CardPaymentGateway implements PaymentGateway {

    @Override
    public String charge(long amount) {
        return "Card: " + amount;
    }
}
```

Khi inject một `PaymentGateway` đơn lẻ, Spring ưu tiên bean được đánh dấu `@Primary` trong số các ứng viên phù hợp:

```text
PaymentGateway (một dependency)
           │
           ▼
  Các ứng viên phù hợp
   ├── cardGateway  (@Primary)
   └── bankGateway
           │
           ▼
      cardGateway
```

Điểm quan trọng:

- `@Primary` **không đổi tên bean**.
- `@Primary` **không xóa các bean khác khỏi container**.
- `@Primary` chủ yếu hỗ trợ lựa chọn một bean khi autowire dependency đơn lẻ.
- Nếu có nhiều ứng viên cùng mức primary và không có quy tắc phân giải phù hợp, vẫn có thể xảy ra nhập nhằng.
- Với injection vào collection/map, Spring có thể cung cấp nhiều ứng viên thay vì chỉ bean primary.

Có thể đặt `@Primary` trên phương thức `@Bean`:

```java
@Bean("cardGateway")
@Primary
public PaymentGateway cardGateway() {
    return new CardPaymentGateway();
}
```

Dùng `@Primary` khi thật sự có một **giá trị mặc định hợp lý trên toàn ứng dụng**. Nếu mỗi nghiệp vụ cần một gateway khác nhau, `@Qualifier` thường thể hiện đúng ý hơn.

## 8. Cách xử lý nhiều bean cùng type bằng `@Qualifier`

`@Qualifier` giúp chỉ rõ bean hay nhóm ứng viên phù hợp mà một điểm injection muốn sử dụng.

Ví dụ:

```java
package com.example.shop.checkout;

import com.example.shop.payment.PaymentGateway;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("bankGateway") PaymentGateway gateway
    ) {
        this.gateway = gateway;
    }

    public String checkout(long amount) {
        return gateway.charge(amount);
    }
}
```

Ở đây, Spring tìm `PaymentGateway` nhưng có thêm qualifier `bankGateway` để thu hẹp lựa chọn. Do bean đã được đặt tên `bankGateway`, code thể hiện rõ rằng checkout dùng implementation dành cho ngân hàng.

`@Qualifier` **không tự đăng ký bean mới**. Nó chỉ đưa metadata lựa chọn tại injection point và/hoặc phía định nghĩa bean.

### 8.1. Dùng `@Qualifier` trên phương thức `@Bean`

Nếu bean được tạo bằng configuration:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean("cardGateway")
    public PaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }

    @Bean("bankGateway")
    public PaymentGateway bankGateway() {
        return new BankPaymentGateway();
    }
}
```

Có thể inject:

```java
public CheckoutService(
        @Qualifier("cardGateway") PaymentGateway gateway
) {
    this.gateway = gateway;
}
```

`@Qualifier("cardGateway")` là cách mô tả điểm injection. Tên bean có thể được Spring xem là giá trị qualifier phù hợp; Spring cũng hỗ trợ metadata qualifier rõ ràng và qualifier annotation tùy biến. Không nên hiểu `@Qualifier` đơn giản là một API thay thế `getBean(String)` trong mọi trường hợp.

### 8.2. `@Primary` và `@Qualifier` khi cùng xuất hiện

Giả sử `cardGateway` được đánh dấu `@Primary`, nhưng một service cần `bankGateway`:

```java
public RefundService(
        @Qualifier("bankGateway") PaymentGateway gateway
) {
    this.gateway = gateway;
}
```

Qualifier làm rõ ứng viên phù hợp cho điểm inject này; `@Primary` không có nghĩa mọi service đều bắt buộc nhận `cardGateway`. Vì vậy cách dùng kết hợp thường hợp lý:

- `@Primary` cho lựa chọn mặc định của hệ thống.
- `@Qualifier` cho những nơi chủ động chọn một phương án khác.

Cả hai đều xử lý **lựa chọn khi injection**, không giải quyết việc hai bean definition đã đụng cùng tên ở giai đoạn đăng ký.

### 8.3. Qualifier tùy biến theo ngữ nghĩa nghiệp vụ

Khi số lượng bean lớn, lặp lại tên chuỗi có thể khó bảo trì. Spring cho phép tạo qualifier annotation riêng, ví dụ:

```java
package com.example.shop.payment;

import java.lang.annotation.Retention;
import java.lang.annotation.Target;
import org.springframework.beans.factory.annotation.Qualifier;

import static java.lang.annotation.ElementType.FIELD;
import static java.lang.annotation.ElementType.METHOD;
import static java.lang.annotation.ElementType.PARAMETER;
import static java.lang.annotation.ElementType.TYPE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

@Target({FIELD, METHOD, PARAMETER, TYPE})
@Retention(RUNTIME)
@Qualifier
public @interface OnlinePayment {
}
```

Khi đánh dấu bean và injection point bằng `@OnlinePayment`, ta thể hiện lựa chọn theo vai trò **thanh toán online**, thay vì phụ thuộc vào bean name. Đây là kỹ thuật hữu ích khi ứng dụng có nhiều chiến lược và cần một ngôn ngữ cấu hình rõ ràng.

Cần bảo đảm các qualifier được đặt nhất quán; nếu nhiều bean cùng mang qualifier mà điểm inject yêu cầu một bean, vẫn có thể gặp nhập nhằng.

## 9. Nếu thật sự muốn dùng tất cả bean cùng type

Không phải lúc nào nhiều bean cùng type cũng là lỗi. Có những thiết kế cố ý đăng ký nhiều implementation của một interface, ví dụ nhiều bộ kiểm tra hoặc nhiều bước xử lý.

### 9.1. Inject danh sách

Ví dụ interface:

```java
public interface OrderValidator {
    void validate(Order order);
}
```

Các implementation:

```java
@Component
public class StockValidator implements OrderValidator {
    @Override
    public void validate(Order order) {
        // Kiểm tra tồn kho
    }
}
```

```java
@Component
public class AmountValidator implements OrderValidator {
    @Override
    public void validate(Order order) {
        // Kiểm tra giá trị đơn hàng
    }
}
```

Một service có thể nhận `List<OrderValidator>`:

```java
@Service
public class OrderValidationService {

    private final List<OrderValidator> validators;

    public OrderValidationService(List<OrderValidator> validators) {
        this.validators = validators;
    }

    public void validate(Order order) {
        for (OrderValidator validator : validators) {
            validator.validate(order);
        }
    }
}
```

Spring inject các bean phù hợp vào collection. Ở đây số lượng implementation là một phần của thiết kế, không phải vấn đề cần khử bằng `@Primary`.

Nếu thứ tự validator quan trọng, có thể dùng `@Order` hoặc `Ordered` theo semantics của Spring, thay vì dựa vào thứ tự quét class hoặc đăng ký bean.

### 9.2. Inject `Map<String, T>` để chọn theo bean name

Ví dụ:

```java
@Service
public class PaymentRouter {

    private final Map<String, PaymentGateway> gateways;

    public PaymentRouter(Map<String, PaymentGateway> gateways) {
        this.gateways = gateways;
    }

    public PaymentGateway getGateway(String name) {
        PaymentGateway gateway = gateways.get(name);
        if (gateway == null) {
            throw new IllegalArgumentException(
                    "Không tồn tại gateway: " + name
            );
        }
        return gateway;
    }
}
```

Khi inject `Map<String, PaymentGateway>` theo cơ chế thông thường, keys thường là **bean names**, values là các bean phù hợp type. Bạn có thể lựa chọn một strategy theo key ở runtime.

Trong ứng dụng thật, key đến từ request cần được kiểm tra/whitelist theo nghiệp vụ, không nên cho một input bất kỳ từ người dùng truy cập tùy tiện mọi bean nội bộ.

### 9.3. Inject `ObjectProvider<T>` khi cần truy cập linh hoạt

`ObjectProvider<PaymentGateway>` cho phép làm việc với khả năng lấy bean theo nhu cầu, hoặc duyệt các bean phù hợp khi cần:

```java
@Service
public class GatewayInspector {

    private final ObjectProvider<PaymentGateway> gateways;

    public GatewayInspector(
            ObjectProvider<PaymentGateway> gateways
    ) {
        this.gateways = gateways;
    }

    public List<PaymentGateway> findAll() {
        return gateways.stream().toList();
    }
}
```

`ObjectProvider` là công cụ hữu ích, nhưng nó không biến yêu cầu **một bean duy nhất** thành một lựa chọn không nhập nhằng. Các phương thức lấy đơn lẻ vẫn có semantics riêng; khi cần tất cả, nên dùng `stream()` hoặc API tương ứng.

### 9.4. Khi nào dùng collection, khi nào dùng qualifier?

| Mục tiêu | Cách thể hiện |
|---|---|
| Một gateway mặc định dùng rộng rãi | `@Primary` |
| Một gateway cụ thể tại một service | `@Qualifier` |
| Chạy tất cả validators | `List<OrderValidator>` |
| Chọn strategy theo tên ở runtime | `Map<String, Strategy>` |
| Truy xuất linh hoạt và trì hoãn | `ObjectProvider<T>` |
| Tách implementation theo môi trường | `@Profile`/`@Conditional` khi thích hợp |

Các lựa chọn trên không đồng nhất về ngữ nghĩa. Chúng nên phản ánh cách nghiệp vụ cần sử dụng bean, thay vì chỉ được thêm vào để làm mất lỗi log.

## 10. Một ví dụ Spring Boot đầy đủ không bị nhập nhằng

Ta xây dựng một ứng dụng web nhỏ có **hai bean cùng type**, nhưng injection được chọn rõ ràng.

### 10.1. Cấu trúc mã nguồn

```text
src/main/java/com/example/paymentdemo/
├── PaymentDemoApplication.java
├── payment/
│   ├── PaymentGateway.java
│   ├── CardPaymentGateway.java
│   └── BankPaymentGateway.java
├── service/
│   └── CheckoutService.java
└── web/
    └── CheckoutController.java
```

### 10.2. Lớp main

`PaymentDemoApplication.java`:

```java
package com.example.paymentdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PaymentDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PaymentDemoApplication.class, args);
    }
}
```

### 10.3. Hai implementation có tên riêng

`payment/PaymentGateway.java`:

```java
package com.example.paymentdemo.payment;

public interface PaymentGateway {
    String charge(long amount);
}
```

`payment/CardPaymentGateway.java`:

```java
package com.example.paymentdemo.payment;

import org.springframework.stereotype.Service;

@Service("cardGateway")
public class CardPaymentGateway implements PaymentGateway {

    @Override
    public String charge(long amount) {
        return "Thanh toán " + amount + " bằng thẻ";
    }
}
```

`payment/BankPaymentGateway.java`:

```java
package com.example.paymentdemo.payment;

import org.springframework.stereotype.Service;

@Service("bankGateway")
public class BankPaymentGateway implements PaymentGateway {

    @Override
    public String charge(long amount) {
        return "Thanh toán " + amount + " qua ngân hàng";
    }
}
```

### 10.4. Service chọn một bean cụ thể

`service/CheckoutService.java`:

```java
package com.example.paymentdemo.service;

import com.example.paymentdemo.payment.PaymentGateway;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("cardGateway") PaymentGateway gateway
    ) {
        this.gateway = gateway;
    }

    public String pay(long amount) {
        return gateway.charge(amount);
    }
}
```

### 10.5. Endpoint

`web/CheckoutController.java`:

```java
package com.example.paymentdemo.web;

import com.example.paymentdemo.service.CheckoutService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CheckoutController {

    private final CheckoutService checkoutService;

    public CheckoutController(CheckoutService checkoutService) {
        this.checkoutService = checkoutService;
    }

    @GetMapping("/pay")
    public String pay(@RequestParam(defaultValue = "100") long amount) {
        return checkoutService.pay(amount);
    }
}
```

Với project đã khai báo `spring-boot-starter-web`, ứng dụng chạy tại cổng mặc định và không có cấu hình khác ghi đè, request minh họa:

```text
GET http://localhost:8080/pay?amount=500
```

trả nội dung:

```text
Thanh toán 500 bằng thẻ
```

Cả `cardGateway` và `bankGateway` đều đăng ký thành công. `CheckoutService` sử dụng bean `cardGateway` vì constructor đặt `@Qualifier("cardGateway")`. Đây là ví dụ rõ ràng của việc **nhiều bean cùng type nhưng không có xung đột vì injection point chỉ rõ lựa chọn**.

### 10.6. Thử gây lỗi type ambiguity

Trong `CheckoutService`, bỏ qualifier:

```java
public CheckoutService(PaymentGateway gateway) {
    this.gateway = gateway;
}
```

Giữ hai bean cùng type và cùng tên khác nhau. Với điểm injection không có chỉ dẫn chọn đủ rõ, startup có thể thất bại vì `PaymentGateway` có hai ứng viên.

Sau đó thêm lại `@Qualifier`. Hãy lưu ý **không cần xóa một trong hai bean**: chúng đều hợp lệ, chỉ dependency đơn lẻ chưa chỉ rõ lựa chọn.

### 10.7. Thử gây lỗi name collision

Trên hai implementation, cố tình đặt cùng tên:

```java
@Service("paymentGateway")
public class CardPaymentGateway implements PaymentGateway {
    // ...
}
```

```java
@Service("paymentGateway")
public class BankPaymentGateway implements PaymentGateway {
    // ...
}
```

Lúc này vấn đề không còn là cách chọn bean khi inject. Cả hai component đều cố đăng ký tên `paymentGateway`. Khi scanner coi chúng là hai định nghĩa không tương thích, việc đăng ký có thể thất bại trước khi Spring giải quyết constructor của `CheckoutService`.

Hãy **khôi phục hai bean name khác nhau** sau khi quan sát. Thêm `@Primary` vào một class sẽ không làm hai định nghĩa cùng tên tự trở thành hai bean hợp lệ.

## 11. Phân biệt qua log: đọc đúng triệu chứng

### 11.1. Log xung đột tên

Một đoạn thông báo minh họa:

```text
The bean 'paymentGateway' could not be registered.
A bean with that name has already been defined
and overriding is disabled.
```

Các từ khóa đáng chú ý:

- `bean 'paymentGateway'`: chỉ ra **tên bean bị đụng**.
- `already been defined`: tên đã được đăng ký.
- `overriding is disabled`: việc thay thế định nghĩa trước không được cho phép.

Câu hỏi cần trả lời: **Hai định nghĩa nào sử dụng tên `paymentGateway`?**

Bạn nên xác định tên bean, nguồn class/method tạo bean, và tại sao hai nguồn cùng được đưa vào context. Hành động có thể là đổi tên, loại bỏ định nghĩa thừa hoặc điều chỉnh điều kiện đăng ký.

### 11.2. Log nhiều bean cùng type

Một log minh họa khác:

```text
Parameter 0 of constructor in CheckoutService
required a single bean, but 2 were found:
    - cardGateway: defined in class path resource [...]
    - bankGateway: defined in class path resource [...]
```

Các từ khóa đáng chú ý:

- `required a single bean`: một injection point cần đúng một bean.
- `2 were found`: container đã tìm thấy nhiều bean phù hợp.
- Hai tên liệt kê **khác nhau**: đây không phải va chạm tên.

Câu hỏi cần trả lời: **CheckoutService phải sử dụng gateway nào, hay thực sự cần cả hai?**

Hành động có thể là `@Primary`, `@Qualifier`, thay dependency bằng collection/map hoặc thay đổi thiết kế để mỗi môi trường chỉ có một implementation.

### 11.3. Bảng đối chiếu hai loại lỗi

| Đặc điểm | Đụng tên bean | Nhiều bean cùng type |
|---|---|---|
| Thứ bị trùng | Bean name | Kiểu phù hợp cho một dependency |
| Tên bean của các ứng viên | Thường giống nhau | Thường khác nhau |
| Giai đoạn phát hiện | Đăng ký/scan bean definitions | Resolve dependency khi tạo hoặc lấy bean |
| Lỗi thường thấy | `BeanDefinitionOverrideException` hoặc lỗi xung đột scanner | `NoUniqueBeanDefinitionException`, có thể nằm trong `UnsatisfiedDependencyException` |
| `@Primary` có giải quyết được không? | Không | Có thể, nếu tạo lựa chọn duy nhất phù hợp |
| `@Qualifier` có giải quyết được không? | Không | Có thể, nếu chọn được ứng viên phù hợp |
| Đổi một bean name có giải quyết được không? | Có thể | Không đủ nếu vẫn có nhiều bean cùng type tại injection point |
| Bật overriding có đúng mục tiêu không? | Chỉ khi thật sự muốn một định nghĩa thay thế định nghĩa khác | Không giải quyết nhu cầu chọn giữa hai bean khác tên |
| Giải pháp thiết kế | Tên riêng, điều kiện riêng, bỏ định nghĩa thừa | Chọn mặc định, qualifier, collection, hoặc điều kiện đăng ký |

### 11.4. `NoSuchBeanDefinitionException` là nhóm thứ ba

Nếu Spring báo:

```text
No qualifying bean of type 'com.example.PaymentGateway' available
```

và **không có** ứng viên phù hợp, đó là **thiếu bean**, khác cả hai loại xung đột trong bài:

- Đụng tên: có hai nguồn cùng muốn đăng ký một tên.
- Nhiều cùng type: có từ hai ứng viên phù hợp trở lên nhưng chưa xác định được một.
- Thiếu bean: không tìm được ứng viên phù hợp.

Cách xử lý thiếu bean là kiểm tra component scan, `@Bean`, `@Import`, profile, conditional configuration và classpath. Không thêm `@Primary` vào một bean không tồn tại.

## 12. Profiles và conditions có thể tạo hoặc loại bỏ xung đột

Đôi khi ứng dụng cố ý có nhiều implementation nhưng mỗi môi trường chỉ nên dùng một.

Ví dụ dùng profile:

```java
@Service("paymentGateway")
@Profile("dev")
public class SandboxPaymentGateway implements PaymentGateway {
    // ...
}
```

```java
@Service("paymentGateway")
@Profile("prod")
public class ProductionPaymentGateway implements PaymentGateway {
    // ...
}
```

Nếu chỉ profile `dev` được kích hoạt thì bean sandbox được đăng ký, còn production bean không hoạt động. Nếu chỉ profile `prod` được kích hoạt thì ngược lại.

Tuy nhiên, hãy chú ý:

- Spring cho phép **nhiều profile cùng active**. Nếu `dev` và `prod` cùng active, cả hai định nghĩa có thể cùng muốn tên `paymentGateway` và đụng tên.
- Nếu không có profile phù hợp, có thể **không có bean `PaymentGateway` nào**.
- Khi các bean có tên khác nhau nhưng đồng thời active, vấn đề nhập nhằng theo type vẫn có thể xảy ra tại injection point đơn lẻ.

Vì vậy, profile là một công cụ **điều khiển điều kiện đăng ký bean**, không phải cơ chế chọn bean theo type trong mọi trường hợp.

### 12.1. Hai cách thiết kế hợp lệ theo mục tiêu

**Thiết kế A: chỉ một gateway cho mỗi môi trường.**

```text
Active profile = dev
    -> SandboxPaymentGateway

Active profile = prod
    -> ProductionPaymentGateway
```

Dùng `@Profile` hoặc configuration conditions sao cho mỗi môi trường có đúng định nghĩa cần thiết.

**Thiết kế B: nhiều gateway hoạt động đồng thời.**

```text
cardGateway
bankGateway
walletGateway
     │
     ▼
PaymentRouter hoặc injection có qualifier
```

Dùng tên riêng cho từng bean và một chiến lược chọn được thể hiện trong code nghiệp vụ.

Nếu hệ thống hỗ trợ nhiều cổng thanh toán cùng lúc, không nên cố loại bỏ các bean chỉ để tránh nhập nhằng khi inject một interface.

## 13. Một số tình huống nâng cao cần nhận biết

### 13.1. Một bean có thể có nhiều interface

```java
public class CardGateway implements PaymentGateway, HealthCheck {
}
```

Một bean `cardGateway` có thể xuất hiện trong tập ứng viên khi inject `PaymentGateway` hoặc `HealthCheck`. Điều này không phải bean name collision; nó là bản chất của type assignability.

Nếu một interface có nhiều implementation và bạn yêu cầu một bean duy nhất, có thể cần qualifier hoặc quy tắc lựa chọn khác.

### 13.2. Generic type có thể giúp phân biệt ứng viên

Ví dụ:

```java
public interface Handler<T> {
    void handle(T value);
}
```

```java
@Component
public class StringHandler implements Handler<String> {
    @Override
    public void handle(String value) {
        // ...
    }
}
```

```java
@Component
public class IntegerHandler implements Handler<Integer> {
    @Override
    public void handle(Integer value) {
        // ...
    }
}
```

Spring có thể sử dụng thông tin generic như một phần của quá trình lọc ứng viên. Điểm inject `Handler<String>` có thể được phân biệt với `Handler<Integer>` mà không cần một bean name riêng tại injection point.

Không suy diễn rằng raw type `Handler` cũng luôn phân biệt được hai bean: raw type làm mất thông tin generic dùng cho lựa chọn.

### 13.3. `@Primary` không áp dụng “độc quyền” với collection

Nếu inject:

```java
public GatewayRegistry(List<PaymentGateway> gateways) {
    this.gateways = gateways;
}
```

thì danh sách vẫn có thể bao gồm cả `@Primary` bean và những bean khác phù hợp. `@Primary` chủ yếu giải quyết lựa chọn khi dependency cần **một** đối tượng.

Nếu chỉ một bean nên được đưa vào collection, hãy cân nhắc qualifier hoặc một cấu hình lọc ứng viên phù hợp với mục tiêu thực tế.

### 13.4. Tên bean và tên của biến Java không phải một

```java
PaymentGateway selectedGateway =
        context.getBean("cardGateway", PaymentGateway.class);
```

Tên biến Java là `selectedGateway`, còn bean name là `cardGateway`. Đổi tên biến không làm đổi bean definition.

Với constructor injection, đôi khi tên tham số được dùng như một dữ kiện khi resolve dependency; nhưng tên bean vẫn được khai báo hoặc sinh từ cơ chế đăng ký bean.

### 13.5. Nhiều `ApplicationContext` có thể có bean cùng tên

Các bean names được quản lý trong phạm vi registry/context. Hai context độc lập có thể có bean cùng tên mà không đụng nhau vì chúng không đăng ký vào cùng một registry.

Với context hierarchy, việc truy cập bean của parent/child có quy tắc visibility và shadowing riêng. Khi chẩn đoán, cần xác định **bean thuộc context nào**, đặc biệt trong integration test hoặc ứng dụng có context phân tầng.

Với Spring Boot Fundamentals, bạn thường bắt đầu từ một ApplicationContext chính; hiểu phạm vi tên giúp tránh ngộ nhận “mỗi bean name phải duy nhất trên toàn JVM”.

## 14. Cách kiểm tra những bean thực sự được đăng ký

Khi ứng dụng khởi động được nhưng kết quả inject không như dự kiến, bạn có thể xem các bean phù hợp một type từ `ApplicationContext`.

Ví dụ một `CommandLineRunner` trong Spring Boot:

```java
package com.example.shop;

import java.util.Arrays;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;
import com.example.shop.payment.PaymentGateway;

@Component
public class GatewayInspector implements CommandLineRunner {

    private final ApplicationContext context;

    public GatewayInspector(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(String... args) {
        String[] names = context.getBeanNamesForType(PaymentGateway.class);
        System.out.println("PaymentGateway beans: " + Arrays.toString(names));
    }
}
```

Nếu hai bean `cardGateway` và `bankGateway` được đăng ký, output minh họa có thể là:

```text
PaymentGateway beans: [cardGateway, bankGateway]
```

Thứ tự hiển thị không nên dùng như quy tắc chọn implementation. Code này là công cụ quan sát trong bài học; ứng dụng production nên dùng logging và cơ chế chẩn đoán phù hợp thay vì in tùy tiện tất cả bean names.

### 14.1. Khi ứng dụng không khởi động được thì sao?

Nếu lỗi xảy ra sớm khi đăng ký bean definitions, `CommandLineRunner` sẽ chưa được chạy. Khi đó cần đọc startup log và xác định cấu hình đã đăng ký bean trùng tên.

Nếu lỗi xảy ra trong lúc dựng một bean bắt buộc, context cũng có thể không hoàn thành startup, nên `CommandLineRunner` không phải cách chẩn đoán duy nhất.

### 14.2. Xem nguyên nhân gốc trong log

Hãy tìm:

- **Tên bean:** ví dụ `paymentGateway`.
- **Type cần inject:** ví dụ `com.example.shop.payment.PaymentGateway`.
- **Hai nguồn bean definitions:** class, `@Bean` method hoặc auto-configuration nào?
- **Injection point:** constructor hoặc field nào yêu cầu dependency?
- **Profiles/conditions:** những cấu hình nào đang active?
- **Chuỗi `Caused by`:** exception nào thực sự giải thích thất bại?

Spring Boot có thể cung cấp báo cáo auto-configuration khi chạy với `--debug` trong tình huống cần hiểu conditions. Báo cáo đó giúp xác định điều kiện nào đã match hoặc không match, nhưng không thay cho việc đọc trực tiếp thông báo đụng tên hoặc nhập nhằng.

## 15. Quy trình xử lý lỗi trong dự án đầu tiên

Khi Spring Boot báo không tạo được bean hoặc không khởi động được, có thể áp dụng quy trình sau:

### Bước 1 — Xác định lỗi ở đăng ký hay injection

Log có nói:

```text
A bean with that name has already been defined
```

hay:

```text
required a single bean, but 2 were found
```

Nếu là thông báo thứ nhất, tìm **xung đột tên**. Nếu là thông báo thứ hai, tìm **lựa chọn theo type**.

### Bước 2 — Liệt kê ứng viên và nguồn định nghĩa

Với bean name collision, ghi lại:

```text
bean name: paymentGateway
definition A: DefaultGatewayConfiguration#cardGateway()
definition B: ExperimentalGatewayConfiguration#bankGateway()
```

Với type ambiguity, ghi:

```text
required type: PaymentGateway
injection point: CheckoutService(PaymentGateway gateway)
candidate A: cardGateway
candidate B: bankGateway
```

Cách ghi này giúp nhìn thấy chính xác thứ đang trùng: **name** hay **type**.

### Bước 3 — Quyết định nghiệp vụ cần bao nhiêu bean

Hỏi xem ứng dụng cần:

- Một implementation duy nhất trong mọi môi trường?
- Một implementation mặc định và những implementation tùy chọn?
- Nhiều implementation chạy đồng thời?
- Một implementation chỉ ở profile nhất định?
- Một bean tùy chỉnh thay thế bean mặc định của auto-configuration?

Chỉ sau khi hiểu yêu cầu này mới chọn giải pháp kỹ thuật.

### Bước 4 — Sửa theo loại xung đột

Nếu **đụng tên**, xử lý tại chỗ đăng ký:

- Dùng bean names khác nhau khi muốn hai bean cùng tồn tại.
- Bỏ đăng ký thừa nếu chỉ cần một bean.
- Đặt `@Profile`/`@Conditional` nếu cần một bean theo môi trường.
- Chỉ cân nhắc overriding khi việc thay thế definition là chủ ý và đã kiểm soát.

Nếu **nhiều bean cùng type**, xử lý tại chỗ lựa chọn:

- `@Qualifier` nếu service cần một bean cụ thể.
- `@Primary` nếu có lựa chọn mặc định.
- `List<T>` hoặc `Map<String, T>` nếu service cần nhiều bean.
- Thiết kế lại conditions nếu thực tế chỉ nên có một bean.

### Bước 5 — Đọc log sau sửa đúng mục tiêu

Khi đổi tên hai bean từ `paymentGateway` thành `cardGateway` và `bankGateway`, bước đăng ký có thể thành công nhưng startup tiếp tục báo `required a single bean, but 2 were found`. Đây không phải quay lại lỗi cũ: bạn đã đi qua **giai đoạn đăng ký** và phát hiện một yêu cầu inject cần được chỉ rõ.

Ngược lại, nếu bạn thêm `@Qualifier("cardGateway")` nhưng cả hai bean definition vẫn cùng tên `paymentGateway`, lỗi đụng tên sẽ xảy ra trước khi qualifier có cơ hội được dùng.

## 16. Bài luyện tập nhận diện hai loại xung đột

### Bài 1 — Hai `@Bean` trùng tên

Tạo hai lớp `@Configuration` cùng nằm trong vùng component scan, mỗi lớp có một phương thức trả `Clock` nhưng cả hai đều đặt:

```java
@Bean("applicationClock")
```

Quan sát log khi khởi động. Ghi ra bean name bị đụng và hai nguồn định nghĩa. Sau đó đổi thành `utcClock` và `systemClock`.

Bài này minh họa **đụng tên**. Sau khi đổi tên, nếu một service inject `Clock` đơn lẻ mà không có lựa chọn, bạn có thể gặp **nhập nhằng theo type**.

### Bài 2 — Hai bean `Clock` có tên khác nhau

Cấu hình:

```java
@Configuration(proxyBeanMethods = false)
public class ClockConfiguration {

    @Bean("utcClock")
    public Clock utcClock() {
        return Clock.systemUTC();
    }

    @Bean("systemClock")
    public Clock systemClock() {
        return Clock.systemDefaultZone();
    }
}
```

Tạo một service nhận `Clock` qua constructor:

```java
public TimeService(Clock clock) {
    this.clock = clock;
}
```

Với hai ứng viên cùng type, injection có thể nhập nhằng. Hãy thử lần lượt `@Qualifier("utcClock")` và `@Primary` (trên một `@Bean`) để quan sát hai cách lựa chọn.

### Bài 3 — Cùng lúc dùng hai implementation

Tạo interface `NotificationSender` và hai bean `emailSender`, `smsSender`. Cho một service nhận:

```java
public NotificationService(List<NotificationSender> senders) {
    this.senders = senders;
}
```

Giải thích vì sao đây là một thiết kế hợp lệ với nhiều bean cùng type, và tại sao không cần `@Primary` nếu service muốn sử dụng tất cả các sender.

### Bài 4 — Profile có thể bật nhiều bean

Tạo hai bean cùng tên, một đánh dấu `@Profile("dev")`, một đánh dấu `@Profile("prod")`. Quan sát khi chỉ bật `dev` hoặc chỉ bật `prod`. Sau đó xem điều gì có thể xảy ra nếu cả hai profile cùng active.

Mục đích là hiểu `@Profile` điều khiển **đăng ký bean theo điều kiện**, chứ không bảo đảm trên toàn bộ hệ thống chỉ có một profile hoạt động.

### Bài 5 — Phân loại log

Xác định nhóm lỗi và bước kiểm tra đầu tiên:

| Log | Loại vấn đề | Bước đầu tiên |
|---|---|---|
| `bean 'mailSender' already defined and overriding is disabled` | Đụng tên | Tìm hai bean definitions cùng tên |
| `required a single bean, but 3 were found` | Nhiều bean cùng type | Xác định injection point và ba ứng viên |
| `No qualifying bean of type 'PaymentGateway' available` | Thiếu bean phù hợp | Kiểm tra scan, `@Bean`, profile, conditions |
| `NoUniqueBeanDefinitionException: expected single matching bean but found 2` | Nhiều bean cùng type | Quyết định `@Qualifier`, `@Primary` hoặc collection |
| `ConflictingBeanDefinitionException ... bean name 'emailSender'` | Đụng tên do scan | Xem class/packages và tên mặc định |
| `NoSuchBeanDefinitionException` khi `getBean("cardGateway")` | Không có bean theo tên yêu cầu | Xem bean name thật, alias và điều kiện đăng ký |

## 17. Nguyên tắc áp dụng lâu dài

Khi tổ chức mã nguồn và đăng ký bean trong Spring Boot, hãy luôn giữ ba lớp thông tin rõ ràng:

```text
Bean definition
    ├── Name: cardGateway
    ├── Type: CardPaymentGateway implements PaymentGateway
    └── Conditions: profile, configuration, v.v.
                    │
                    ▼
Dependency injection
    ├── Required type: PaymentGateway
    ├── Qualifier/Primary: lựa chọn phù hợp
    └── Shape: một bean, List, Map, Provider...
                    │
                    ▼
Bean instance được đưa vào nơi sử dụng
```

**Đụng tên bean** là vấn đề nhiều định nghĩa cùng muốn một tên trong container. **Nhiều bean cùng type** là vấn đề các bean đã đăng ký nhưng một điểm injection chưa xác định được ứng viên cần dùng. Bean names là cách định danh trong registry; bean types là cách Spring xác định đối tượng nào đáp ứng một dependency. Hiểu hai chiều này giúp bạn sửa đúng nguyên nhân và thiết kế ứng dụng có nhiều implementation mà vẫn rõ ràng, ổn định.
