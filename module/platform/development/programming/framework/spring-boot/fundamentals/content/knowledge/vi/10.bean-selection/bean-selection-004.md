# @Resource, tên bean và khác biệt với lựa chọn theo type

Trong một ứng dụng Spring Boot, nhiều bean có thể cùng triển khai một interface. Ví dụ, ứng dụng thanh toán có thể có `StripePaymentGateway`, `BankPaymentGateway` và `FakePaymentGateway`, tất cả đều triển khai `PaymentGateway`. Khi một service yêu cầu `PaymentGateway`, Spring cần biết **chính xác bean nào sẽ được truyền vào**.

Hai cách inject thường được so sánh là:

- **`@Resource`**: ưu tiên tìm bean theo **tên** (name-based resolution), với quy tắc mặc định dựa trên tên field hoặc property.
- **`@Autowired`**: chủ yếu tìm bean theo **kiểu Java** (type-based resolution); khi có nhiều ứng viên, có thể dùng `@Qualifier`, `@Primary` và các quy tắc phân giải ứng viên.

Sự khác nhau này ảnh hưởng trực tiếp đến việc đặt tên bean, thay đổi field/property, thêm implementation mới và thiết kế constructor của service. Hiểu đúng giúp tránh lỗi inject nhầm implementation hoặc lỗi không tìm được bean khi ứng dụng khởi động.

## 1. Bean có hai đặc điểm cần phân biệt: tên và kiểu

Một bean trong Spring có **bean name** và **bean type**. Chúng trả lời hai câu hỏi khác nhau:

- **Tên bean**: container định danh bean bằng tên nào?
- **Kiểu bean**: bean có thể được inject hoặc truy vấn bằng class/interface nào?

Ví dụ:

```java
public interface PaymentGateway {
    String charge(long amount);
}
```

Hai implementation:

```java
import org.springframework.stereotype.Component;

@Component("stripeGateway")
public class StripePaymentGateway implements PaymentGateway {
    @Override
    public String charge(long amount) {
        return "Charged by Stripe: " + amount;
    }
}
```

```java
import org.springframework.stereotype.Component;

@Component("bankGateway")
public class BankPaymentGateway implements PaymentGateway {
    @Override
    public String charge(long amount) {
        return "Charged by bank: " + amount;
    }
}
```

Container có thể quản lý hai bean:

| Bean name | Concrete type | Interface có thể dùng để tìm |
|---|---|---|
| `stripeGateway` | `StripePaymentGateway` | `PaymentGateway` |
| `bankGateway` | `BankPaymentGateway` | `PaymentGateway` |

Cả hai bean đều có thể đáp ứng một dependency kiểu `PaymentGateway`. Nhưng nếu cần gọi theo tên `stripeGateway`, container chỉ chọn bean có tên đó (hoặc alias tương ứng).

Một cách kiểm tra khi đang debug:

```java
PaymentGateway stripe =
        applicationContext.getBean("stripeGateway", PaymentGateway.class);

PaymentGateway bank =
        applicationContext.getBean("bankGateway", PaymentGateway.class);
```

Đoạn code trên giả định context có hai bean với đúng tên đó. Nếu không có tên bean phù hợp, Spring ném lỗi lookup; nếu bean tồn tại nhưng không tương thích kiểu yêu cầu, việc lấy theo kiểu cũng thất bại.

**Tên và kiểu không thay thế cho nhau.** Một bean có thể được tìm theo type mà không cần caller biết tên; ngược lại, một bean có tên cụ thể vẫn có thể không phải implementation mà caller mong muốn nếu kiểu yêu cầu quá rộng hoặc cấu hình sai.

## 2. Spring tạo tên bean mặc định như thế nào?

Tên bean có thể được đặt tường minh hoặc được suy ra từ nơi khai báo.

### 2.1. Với stereotype annotation

Nếu bạn viết:

```java
@Service
public class OrderService {
}
```

Spring thường tạo tên bean mặc định từ tên lớp theo quy tắc decapitalize: `OrderService` thành `orderService`.

Bạn có thể chỉ định tên riêng:

```java
@Service("checkoutService")
public class OrderService {
}
```

Trong ví dụ này, tên bean là `checkoutService`; tên class vẫn là `OrderService`.

Quy tắc tương tự áp dụng với `@Component`, `@Repository`, `@Controller` và các stereotype tương ứng.

### 2.2. Với phương thức `@Bean`

Tên bean mặc định thường là tên phương thức khai báo:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    public PaymentGateway stripeGateway() {
        return new StripePaymentGateway();
    }
}
```

Bean được đăng ký với tên `stripeGateway`. Có thể đặt tên hoặc alias rõ ràng:

```java
@Bean(name = {"stripeGateway", "primaryPaymentGateway"})
public PaymentGateway paymentGateway() {
    return new StripePaymentGateway();
}
```

Trong ví dụ này, `stripeGateway` là tên bean và `primaryPaymentGateway` là một alias. Cả hai tên có thể dùng để tra cứu cùng một bean. Tên và alias nên được quản lý nhất quán để tránh nhầm lẫn.

### 2.3. Tên bean phân biệt chữ hoa/chữ thường

Tên bean thường được so khớp theo chuỗi chính xác và phân biệt chữ hoa/chữ thường. `stripeGateway` và `StripeGateway` không nên được xem là cùng một tên. Hãy dùng một convention nhất quán, thông thường là lower camel case.

Tên bean mặc định cũng không phải lúc nào đơn giản là viết thường ký tự đầu tiên. Quy tắc JavaBeans decapitalize giữ nguyên một số tên bắt đầu bằng hai chữ hoa liên tiếp; ví dụ tên class dạng `URLClient` có thể giữ nguyên `URLClient`. Khi tên là một phần của contract tích hợp, hãy đặt tường minh thay vì dựa vào quy tắc suy ra.

## 3. `@Resource` là injection theo tên

`@Resource` là annotation thuộc nhóm Jakarta Common Annotations (trước đây là JSR-250), không phải annotation riêng do Spring định nghĩa. Spring hỗ trợ nó trong quá trình dependency injection thông qua hạ tầng xử lý common annotations.

Ví dụ:

```java
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    @Resource(name = "stripeGateway")
    private PaymentGateway paymentGateway;

    public String checkout(long amount) {
        return paymentGateway.charge(amount);
    }
}
```

Ý nghĩa:

1. Container xử lý annotation `@Resource` trên field.
2. Giá trị `name = "stripeGateway"` yêu cầu bean có tên `stripeGateway`.
3. Bean đó phải tương thích với kiểu field `PaymentGateway`.
4. Spring inject tham chiếu đến bean vào field trước khi bean được đưa vào sử dụng theo lifecycle tương ứng.

Trong ví dụ này, dù có nhiều bean cùng implement `PaymentGateway`, tên `stripeGateway` chỉ rõ bean mong muốn.

### 3.1. Không chỉ định `name`: tên mặc định lấy từ field/property

Bạn có thể viết:

```java
@Resource
private PaymentGateway stripeGateway;
```

Khi `name` không được khai báo, Spring suy ra tên mặc định từ field: `stripeGateway`. Tương tự, nếu dùng setter `setStripeGateway(...)`, tên property mặc định là `stripeGateway`.

Vì vậy, đổi tên field có thể làm thay đổi cách `@Resource` tìm bean:

```java
@Resource
private PaymentGateway paymentGateway;
```

Trong trường hợp này, tên mặc định được suy ra là `paymentGateway`, không còn là `stripeGateway`.

Đây là một khác biệt quan trọng với `@Autowired`: **tên field là một phần của quy tắc chọn bean mặc định của `@Resource`**, nên refactor tên field có thể ảnh hưởng đến dependency resolution.

### 3.2. Spring xử lý default name và type fallback

Trong annotation-driven injection của Spring, khi `@Resource` **không ghi rõ `name`**, Spring trước tiên dùng tên mặc định suy ra từ field/property. Nếu không có bean mang tên mặc định đó, Spring có thể fallback sang phân giải theo type.

Ví dụ, nếu field tên `paymentGateway` nhưng không có bean tên `paymentGateway`, trong khi context chỉ có duy nhất một bean phù hợp kiểu `PaymentGateway`, Spring có thể inject ứng viên theo type.

Nếu có nhiều bean cùng kiểu mà không thể chọn duy nhất, việc fallback sẽ vẫn gặp ambiguity.

**Khi `name` được chỉ định tường minh**, ý định là lookup theo tên đó. Nếu bean tên này không tồn tại hoặc không tương thích kiểu, việc inject thất bại; Spring không nên tự chọn một bean cùng type mang tên khác để che giấu lỗi chính tả hoặc lỗi cấu hình.

Đây là hành vi hỗ trợ của Spring trong cơ chế xử lý `@Resource`; nếu bạn cần tính portable giữa nhiều container Jakarta khác nhau, hãy kiểm tra quy tắc của môi trường đích thay vì dựa vào fallback riêng của Spring.

### 3.3. Dùng `@Resource` trên setter

`@Resource` được Spring hỗ trợ cho field và bean property setter method:

```java
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private PaymentGateway gateway;

    @Resource(name = "stripeGateway")
    public void setGateway(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public String checkout(long amount) {
        return gateway.charge(amount);
    }
}
```

Với setter, `name` tường minh sẽ được dùng để lookup. Nếu bỏ `name`, tên property suy ra từ method setter là `gateway` trong ví dụ `setGateway`.

### 3.4. `@Resource` không phải lựa chọn constructor injection

Spring hỗ trợ `@Resource` trên field và setter property, **không dùng nó như annotation constructor injection** theo cách `@Autowired` hỗ trợ.

Nếu dependency bắt buộc nên được cung cấp qua constructor, dùng `@Autowired` kết hợp `@Qualifier` hoặc một cơ chế constructor injection phù hợp:

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("stripeGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Constructor injection thường là lựa chọn tốt cho dependency bắt buộc vì field có thể để `final`, dependency hiện rõ và unit test dễ tạo đối tượng. Vì vậy, dù `@Resource` hữu ích khi cần name-based injection trên field/setter, không nên chọn nó chỉ vì muốn thay thế mọi chỗ dùng `@Autowired`.

## 4. `@Autowired` chủ yếu chọn theo type

`@Autowired` thuộc Spring Framework. Cơ chế mặc định là tìm bean phù hợp với **kiểu dependency**.

Ví dụ chỉ có một bean implement `PaymentGateway`:

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Spring tìm ứng viên có thể gán cho `PaymentGateway`. Nếu chỉ có một ứng viên phù hợp, container inject nó. Đây là cách phổ biến khi dependency được xác định tự nhiên bằng interface/type.

Nếu có hai bean cùng implement `PaymentGateway` như `stripeGateway` và `bankGateway`, chỉ dựa vào type sẽ không đủ để chọn một ứng viên duy nhất. Bạn cần cung cấp thêm metadata hoặc quy tắc lựa chọn.

### 4.1. `@Qualifier` thu hẹp tập ứng viên theo type

`@Qualifier` thường được dùng cùng `@Autowired` để chọn một bean trong các ứng viên cùng type:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("stripeGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Có thể hiểu quá trình theo hai bước:

1. Tìm bean phù hợp với kiểu `PaymentGateway`.
2. Dùng qualifier `stripeGateway` để lọc/chọn ứng viên phù hợp.

Giá trị qualifier thường trùng bean name trong ví dụ đơn giản. Tuy nhiên, `@Qualifier` là metadata lựa chọn ứng viên, không chỉ là một API lookup theo tên. Bạn có thể khai báo qualifier riêng trên bean và injection point để mô tả vai trò/ngữ nghĩa, chẳng hạn `@Qualifier("primary")`, `@Qualifier("external")` hoặc custom qualifier annotation.

Ví dụ:

```java
@Component
@Qualifier("external")
public class RemotePaymentGateway implements PaymentGateway {
    @Override
    public String charge(long amount) {
        return "Remote charge: " + amount;
    }
}
```

Injection point:

```java
public CheckoutService(
        @Qualifier("external") PaymentGateway gateway) {
    this.gateway = gateway;
}
```

Ở đây `external` mô tả nhóm/ý nghĩa của ứng viên. Cách dùng qualifier này hữu ích khi tên bean triển khai có thể thay đổi nhưng vai trò mà code cần vẫn giữ nguyên.

### 4.2. `@Primary` chọn ứng viên mặc định

Nếu có nhiều bean cùng type và một bean nên được ưu tiên trong hầu hết injection point, có thể đánh dấu nó là `@Primary`:

```java
@Component
@Primary
public class StripePaymentGateway implements PaymentGateway {
    @Override
    public String charge(long amount) {
        return "Stripe charge: " + amount;
    }
}
```

Khi một dependency kiểu `PaymentGateway` không có qualifier cụ thể, bean primary có thể được chọn làm ứng viên ưu tiên.

`@Primary` **không loại bỏ** các bean khác khỏi container. Bạn vẫn có thể yêu cầu bean khác bằng `@Qualifier` hoặc truy cập theo tên. Nếu có nhiều bean được đánh dấu primary trong cùng phạm vi lựa chọn, Spring vẫn có thể không phân giải được duy nhất.

### 4.3. Tên injection point có thể là fallback trong phân giải `@Autowired`

`@Autowired` chủ yếu theo type, nhưng Spring còn có thể dùng tên field/parameter làm gợi ý khi nhiều ứng viên cùng type và các quy tắc ưu tiên khác chưa chọn được. Ví dụ field tên `stripeGateway` có thể giúp Spring chọn bean cùng tên trong một số tình huống.

Tuy nhiên, không nên coi đây là hợp đồng name-first giống `@Resource(name = "...")`. Cách rõ ràng hơn là khai báo `@Qualifier` tường minh khi bạn cần một implementation cụ thể.

Với constructor/method parameter, việc sử dụng tên tham số làm fallback phụ thuộc thông tin tên parameter có sẵn lúc biên dịch và phiên bản/cấu hình Spring. Nếu dùng quy tắc này, hãy đảm bảo build giữ parameter names; đừng để lựa chọn bean quan trọng phụ thuộc vào tên tham số vô tình bị mất sau compile.

## 5. So sánh trực tiếp `@Resource` và `@Autowired`

| Tiêu chí | `@Resource` | `@Autowired` |
|---|---|---|
| Nguồn annotation | Jakarta Common Annotations (trước đây `javax.annotation`) | Spring Framework |
| Quy tắc chủ đạo | Theo **bean name** | Theo **bean type** |
| Khi không ghi tên/qualifier | Tên mặc định từ field/property; trong Spring có thể fallback theo type khi tên mặc định không tồn tại | Tìm ứng viên theo type; áp dụng qualifier/primary và quy tắc phân giải khác |
| Chỉ định tên cụ thể | `@Resource(name = "stripeGateway")` | Thường dùng `@Qualifier("stripeGateway")` cùng type |
| Constructor injection | Không được Spring hỗ trợ như cách dùng field/setter | Được hỗ trợ |
| Field injection | Có | Có |
| Setter injection | Có | Có |
| Chọn theo qualifier ngữ nghĩa | Không phải mục đích chính của `@Resource` | Có, qua `@Qualifier` và custom qualifier |
| Chọn ứng viên mặc định | Theo tên yêu cầu; fallback theo type trong trường hợp mặc định của Spring | `@Primary` và các quy tắc candidate resolution |
| Phù hợp với | Dependency cần định danh bằng tên, đặc biệt khi tên là một phần của contract | Dependency theo abstraction/type, constructor injection, qualifier và primary |

Cách nhớ:

- `@Resource`: “Hãy tìm bean tên này; nếu tôi không ghi tên, dùng tên field/property làm mặc định.”
- `@Autowired`: “Hãy tìm bean có kiểu phù hợp; nếu có nhiều, dùng qualifier/primary hoặc quy tắc chọn ứng viên.”

Đây là cách diễn đạt rút gọn. Khi debug, hãy xét cả type, name, alias, qualifier, primary, scope và điều kiện đăng ký bean.

## 6. Ví dụ hoàn chỉnh: hai implementation, hai cách lựa chọn

Giả sử cấu hình hai bean:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean("stripeGateway")
    PaymentGateway stripeGateway() {
        return new StripePaymentGateway();
    }

    @Bean("bankGateway")
    PaymentGateway bankGateway() {
        return new BankPaymentGateway();
    }
}
```

### 6.1. Chọn theo tên bằng `@Resource`

```java
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

@Service
public class StripeCheckoutService {

    @Resource(name = "stripeGateway")
    private PaymentGateway gateway;

    public String checkout(long amount) {
        return gateway.charge(amount);
    }
}
```

Bean name tường minh là `stripeGateway`, nên `bankGateway` không được chọn chỉ vì nó cùng implement `PaymentGateway`.

### 6.2. Chọn theo type + qualifier bằng constructor

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class BankCheckoutService {

    private final PaymentGateway gateway;

    public BankCheckoutService(
            @Qualifier("bankGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public String checkout(long amount) {
        return gateway.charge(amount);
    }
}
```

Ở đây constructor thể hiện rõ dependency bắt buộc và qualifier xác định implementation. Nếu đổi tên bean, bạn cần cập nhật qualifier tương ứng hoặc thay bằng qualifier annotation ngữ nghĩa ổn định hơn.

### 6.3. Chọn mặc định bằng `@Primary`

Nếu `StripePaymentGateway` được cấu hình `@Primary`, service sau không cần qualifier khi chỉ muốn default:

```java
@Service
public class DefaultCheckoutService {

    private final PaymentGateway gateway;

    public DefaultCheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Dù vậy, code có thể trở nên khó đọc nếu behavior nghiệp vụ phụ thuộc mạnh vào implementation mặc định toàn ứng dụng. Với các luồng thanh toán khác nhau, nên chỉ rõ qualifier/role ngay tại injection point.

## 7. Khi nào nên dùng `@Resource`?

`@Resource` có ích khi **tên bean là yếu tố định danh có chủ ý**:

- Ứng dụng có nhiều bean cùng interface và quy ước bean name đã được công bố.
- Bạn tích hợp thành phần theo một tên bean cố định từ module khác.
- Bạn đang duy trì codebase sử dụng Jakarta Common Annotations và cần giữ contract injection theo tên.
- Bạn muốn inject trên field hoặc setter bằng một tên cụ thể.

Ví dụ tên bean được xem như cấu hình:

```java
@Resource(name = "primaryPaymentGateway")
private PaymentGateway gateway;
```

Người đọc thấy ngay bean name mà component cần. Nhưng đổi tên bean trong configuration sẽ yêu cầu cập nhật mọi nơi tham chiếu tên đó.

Không nên dùng `@Resource` một cách máy móc chỉ để “Spring tìm đúng class”. Nếu chỉ có một implementation phù hợp và dependency là bắt buộc, constructor injection theo type thường đơn giản hơn.

## 8. Khi nào nên dùng `@Autowired` cùng `@Qualifier`?

`@Autowired` phù hợp khi dependency được mô tả bằng **abstraction/type** và bạn muốn giữ constructor injection:

```java
@Service
public class InvoiceService {

    private final PaymentGateway gateway;

    public InvoiceService(
            @Qualifier("stripeGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Đặc biệt nên dùng khi:

- Dependency là bắt buộc để đối tượng hoạt động.
- Bạn muốn field là `final` và tạo unit test dễ dàng.
- Cần chọn một bean trong nhiều implementation cùng type.
- Qualifier thể hiện vai trò như `@Qualifier("external")` thay vì khóa code vào tên class.
- Bạn muốn tận dụng `@Primary` cho default và qualifier cho các ngoại lệ cụ thể.

Một nguyên tắc thiết kế hữu ích: **chọn theo type trước, thêm qualifier khi cần phân biệt vai trò**. Dùng tên bean khi tên thực sự là contract mà component cần.

## 9. `@Resource` và tên setter/property

Khi đặt `@Resource` trên setter, tên mặc định là tên property theo JavaBeans convention.

```java
@Resource
public void setPaymentGateway(PaymentGateway gateway) {
    this.paymentGateway = gateway;
}
```

Tên property được suy ra là `paymentGateway`. Nếu container có bean mang tên đó, Spring sẽ ưu tiên lookup theo tên mặc định.

Nếu setter là:

```java
@Resource
public void setGateway(PaymentGateway gateway) {
    this.gateway = gateway;
}
```

Tên mặc định đổi thành `gateway`. Điều này có thể gây bất ngờ nếu bean vẫn mang tên `stripeGateway`. Bạn có thể ghi rõ:

```java
@Resource(name = "stripeGateway")
public void setGateway(PaymentGateway gateway) {
    this.gateway = gateway;
}
```

**Tên method setter không phải bean name.** Nó chỉ góp phần suy ra tên property khi `@Resource` không có `name` tường minh.

## 10. Tên bean, alias và qualifier: ba khái niệm không nên nhập làm một

Các giá trị này thường giống nhau trong ứng dụng nhỏ, nhưng có ý nghĩa riêng:

- **Bean name**: tên chính dùng để định danh một bean trong container.
- **Alias**: tên khác trỏ tới cùng bean.
- **Qualifier**: metadata giúp chọn bean phù hợp với injection point.

Ví dụ bean có tên chính và alias:

```java
@Bean(name = {"stripeGateway", "cardGateway"})
PaymentGateway paymentGateway() {
    return new StripePaymentGateway();
}
```

Hai tên có thể lookup cùng bean. Nhưng qualifier có thể mô tả vai trò độc lập với alias:

```java
@Component
@Qualifier("external")
public class RemotePaymentGateway implements PaymentGateway {
    // ...
}
```

`@Qualifier("external")` tại injection point diễn đạt yêu cầu một implementation mang qualifier `external`. Bean name vẫn có thể tham gia làm giá trị qualifier fallback theo quy tắc Spring, nhưng đừng thiết kế hệ thống dựa trên giả định rằng mọi qualifier string luôn là alias của bean.

Nếu nhiều implementation cùng có qualifier hoặc có metadata tùy biến, phải hiểu cách Spring lọc ứng viên và đảm bảo kết quả duy nhất.

## 11. Phiên bản annotation: `jakarta.annotation.Resource` và `javax.annotation.Resource`

Tên package của `@Resource` phụ thuộc thế hệ Java/Spring:

| Nền tảng phổ biến | Import thường gặp |
|---|---|
| Spring Boot 2.x / Spring Framework 5.x | `javax.annotation.Resource` |
| Spring Boot 3.x / Spring Framework 6.x trở lên | `jakarta.annotation.Resource` |

Spring Boot 3 chuyển sang hệ Jakarta EE; các annotation Common Annotations chuyển từ namespace `javax.annotation` sang `jakarta.annotation`. Vì vậy, code cũ có:

```java
import javax.annotation.Resource;
```

cần được cập nhật tương ứng khi chuyển sang Boot 3+:

```java
import jakarta.annotation.Resource;
```

Đây không phải hai class có thể thay thế lẫn nhau bằng cách đổi dependency tùy ý. Hãy dùng đúng API theo phiên bản Spring/Jakarta mà project đang dùng.

Nếu compiler báo không tìm thấy `Resource`, kiểm tra import và dependency API tương ứng trong build. Đừng tự thêm một phiên bản annotation API không tương thích với nền tảng Spring hiện tại. Các starter/BOM của Spring Boot có thể đã quản lý dependency cần thiết; kiểm tra dependency tree trước khi thêm thủ công.

## 12. `@Resource` có inject được vào constructor không?

Một constructor là nơi rất phù hợp để thể hiện dependency bắt buộc, nhưng `@Resource` theo hỗ trợ annotation-driven injection của Spring không dùng trên constructor như `@Autowired`.

Ví dụ không nên viết:

```java
// Không dùng @Resource theo cách này trong Spring
public CheckoutService(@Resource PaymentGateway gateway) {
    this.gateway = gateway;
}
```

Thay vào đó:

```java
public CheckoutService(
        @Qualifier("stripeGateway") PaymentGateway gateway) {
    this.gateway = gateway;
}
```

Nếu class chỉ có một constructor, Spring tự sử dụng constructor đó cho injection mà không cần ghi `@Autowired`. Nếu có nhiều constructor, cần khai báo rõ constructor được chọn theo quy tắc injection.

Đây là một lý do thực tế khiến `@Autowired` + `@Qualifier` thường phù hợp hơn cho code Spring mới: nó vừa hỗ trợ lựa chọn implementation vừa giữ constructor injection.

## 13. Kết hợp `@Resource` với `@Autowired` có cần thiết không?

Thông thường, không nên đặt cả hai annotation lên cùng một injection point để hy vọng chúng “bổ sung” nhau. Chúng là hai cơ chế xử lý injection riêng và có thể gây khó hiểu về thứ tự xử lý, đặc biệt khi cả hai đều cố gắng ghi giá trị cho cùng field/property.

Hãy chọn một cách diễn đạt ý định:

- Cần bean có tên cụ thể trên field/setter: `@Resource(name = "...")`.
- Cần dependency theo type và lựa chọn ứng viên: `@Autowired` với `@Qualifier` hoặc `@Primary`.
- Cần dependency bắt buộc: ưu tiên constructor injection; nếu có nhiều implementation, đặt qualifier trên parameter.

Tách bạch giúp code không phụ thuộc vào hành vi xử lý annotation mà người đọc khó dự đoán.

## 14. Lỗi thường gặp khi chọn bean theo tên

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `NoSuchBeanDefinitionException` khi dùng `@Resource` | Bean name tường minh không tồn tại hoặc không có bean phù hợp; cấu hình chưa được nạp. | Kiểm tra tên, alias, component scan, `@Bean` và điều kiện auto-configuration. |
| `NoUniqueBeanDefinitionException` | `@Resource` dùng tên mặc định nhưng không có bean tên đó, fallback theo type gặp nhiều ứng viên; hoặc injection theo type không có qualifier/primary. | Dùng tên tường minh hoặc `@Qualifier`; kiểm tra `@Primary`. |
| `BeanNotOfRequiredTypeException` | Bean có đúng tên nhưng kiểu không tương thích với field/parameter. | Sửa bean name, kiểu khai báo hoặc implementation. |
| Đổi tên field làm startup lỗi | `@Resource` không ghi tên nên default name thay đổi theo field/property. | Đặt `name` tường minh hoặc điều chỉnh bean name. |
| `@Autowired` inject nhầm implementation sau khi thêm bean mới | Trước đó chỉ có một ứng viên; giờ có nhiều ứng viên và quy tắc chọn mặc định thay đổi. | Dùng qualifier/primary và kiểm tra dependency graph. |
| `@Resource` không biên dịch được | Import `javax.annotation`/`jakarta.annotation` sai phiên bản hoặc API chưa có trên classpath. | Dùng namespace tương ứng Spring Framework và kiểm tra dependency. |
| `@Resource` trên constructor không hoạt động | Cách đặt annotation không thuộc injection point được Spring hỗ trợ. | Dùng constructor injection với `@Qualifier`. |
| Qualifier không chọn được bean | Qualifier value không khớp metadata/ứng viên; hoặc bean không thuộc type cần inject. | Kiểm tra type trước, qualifier sau và bean definition. |

### Đọc lỗi theo thứ tự

Khi startup thất bại, đừng chỉ sửa tên bean theo phỏng đoán. Hãy kiểm tra:

1. Kiểu dependency tại injection point là gì?
2. Có bao nhiêu bean có thể gán cho kiểu đó?
3. Bean name chính xác là gì, có alias không?
4. `@Resource` có ghi `name` hay đang dùng tên mặc định từ field/property?
5. Nếu dùng `@Autowired`, qualifier/primary nào đang có?
6. Bean có thực sự được đăng ký không, hay bị component scan/condition/profile loại bỏ?
7. Bean có tạo thành công không, hay constructor/factory method ném exception?

Tên đúng mà bean chưa được đăng ký vẫn không inject được. Tương tự, bean đã đăng ký mà kiểu không tương thích vẫn không thể được gán cho field/parameter.

## 15. Kiểm tra bean name và type trong container

Trong code debug hoặc test, có thể truy vấn theo tên và theo type:

```java
PaymentGateway byName =
        context.getBean("stripeGateway", PaymentGateway.class);

Map<String, PaymentGateway> allGateways =
        context.getBeansOfType(PaymentGateway.class);

allGateways.forEach((name, gateway) ->
        System.out.println(name + " -> " + gateway.getClass().getName()));
```

- `getBean(name, type)` giúp xác nhận một bean name cụ thể tồn tại và tương thích kiểu.
- `getBeansOfType(type)` cho biết các bean có thể đáp ứng type; hữu ích khi điều tra nhiều implementation.
- `getBean(type)` yêu cầu Spring phân giải một bean duy nhất theo type; nếu có nhiều ứng viên không phân giải được, có thể ném lỗi.

Khi có proxy, `getClass()` trên object trả về có thể hiển thị class proxy thay vì concrete target class. Vì vậy, không nên dựa duy nhất vào tên class runtime để kết luận bean definition ban đầu là gì.

### Một test đơn giản kiểm tra lựa chọn theo qualifier

```java
@SpringBootTest
class CheckoutServiceTest {

    @Autowired
    ApplicationContext context;

    @Test
    void stripeGatewayHasExpectedBeanName() {
        PaymentGateway gateway =
                context.getBean("stripeGateway", PaymentGateway.class);

        assertNotNull(gateway);
    }
}
```

Đoạn test minh họa việc tra cứu theo tên trong context. Để kiểm tra chính xác behavior của service, nên gọi method nghiệp vụ và assert kết quả hoặc dùng test configuration có implementation dễ quan sát. Cần có import JUnit/Spring Boot Test tương ứng với dòng Boot của dự án.

## 16. Chọn theo tên hay theo type trong thiết kế ứng dụng?

Không có một cách duy nhất đúng cho mọi trường hợp. Hãy chọn cơ chế diễn đạt đúng mối quan hệ mà code cần.

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Chỉ có một implementation cho abstraction | Constructor injection theo type; Spring tự phân giải. |
| Có nhiều implementation và một cái là default | `@Primary` trên ứng viên mặc định, nếu quy tắc toàn ứng dụng rõ ràng. |
| Có nhiều implementation và mỗi use case cần một cái cụ thể | `@Qualifier` trên constructor parameter. |
| Bean name là contract đã thống nhất với module khác | `@Resource(name = "...")` trên field/setter, hoặc lookup theo tên khi cần. |
| Cần inject dependency bắt buộc và test dễ | Constructor injection với type/qualifier. |
| Đang duy trì code dùng Jakarta Common Annotations | Có thể giữ `@Resource` nếu name-based semantics phù hợp. |
| Cần chọn theo vai trò nghiệp vụ ổn định qua nhiều lần đổi tên class | Custom qualifier annotation hoặc qualifier metadata có ngữ nghĩa. |

Một ví dụ qualifier tùy biến:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.beans.factory.annotation.Qualifier;

import static java.lang.annotation.ElementType.FIELD;
import static java.lang.annotation.ElementType.PARAMETER;
import static java.lang.annotation.ElementType.TYPE;

@Target({FIELD, PARAMETER, TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Qualifier
public @interface ExternalGateway {
}
```

Đánh dấu implementation:

```java
@Component
@ExternalGateway
public class RemotePaymentGateway implements PaymentGateway {
    // implementation...
}
```

Inject theo vai trò:

```java
@Service
public class InternationalCheckoutService {

    private final PaymentGateway gateway;

    public InternationalCheckoutService(
            @ExternalGateway PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Cách này diễn đạt **vì sao** dependency được chọn, không chỉ bean tên gì. Nó đặc biệt hữu ích khi một module có nhiều implementation thay đổi theo môi trường hoặc nhà cung cấp.

## 17. Bài tập thực hành

### Bài tập A — Quan sát tên bean mặc định

1. Tạo class `EmailNotifier` có `@Component` và không ghi tên.
2. Khởi chạy ứng dụng, truy vấn bean theo tên `emailNotifier`.
3. Đổi thành `@Component("mailSender")`.
4. Thử tra cứu theo tên cũ và tên mới; giải thích khác biệt.

### Bài tập B — Hai bean cùng type

1. Tạo hai implementation `StripePaymentGateway` và `BankPaymentGateway`.
2. Khai báo cả hai bean với tên riêng.
3. Inject một `PaymentGateway` bằng `@Autowired` mà không qualifier.
4. Quan sát lỗi ambiguity.
5. Thêm `@Primary` cho một bean, sau đó dùng `@Qualifier` để chọn bean còn lại ở một service khác.

### Bài tập C — Thay đổi tên field với `@Resource`

1. Khai báo bean tên `stripeGateway`.
2. Inject bằng `@Resource` không ghi `name` vào field `stripeGateway`.
3. Đổi tên field thành `paymentGateway` nhưng giữ nguyên bean name.
4. Quan sát quy tắc default name và thử thêm bean có tên `paymentGateway`.
5. Đổi sang `@Resource(name = "stripeGateway")` để cố định tên được yêu cầu.

### Bài tập D — So sánh với constructor injection

Viết một service dùng `@Autowired` + `@Qualifier` trên constructor parameter. Sau đó viết phiên bản dùng `@Resource(name = "...")` trên field hoặc setter. So sánh:

- Dependency có hiển thị rõ qua constructor không?
- Đổi tên field/property có làm đổi default bean name không?
- Có thể dùng `final` cho dependency không?
- Unit test thuần Java tạo service cần những tham số nào?

### Bài tập E — Chuyển namespace Jakarta

Nếu đang có code cũ dùng `javax.annotation.Resource`, xác định phiên bản Spring Boot/Spring Framework của project. Thử đối chiếu với project Boot 3+ dùng `jakarta.annotation.Resource`. Ghi lại import và dependency API tương ứng; không trộn hai namespace trong cùng một injection point.

## 18. Những nguyên tắc cần nhớ

1. **Bean name và bean type là hai khái niệm khác nhau.** Nhiều bean có thể cùng type nhưng có tên riêng.
2. **`@Resource` chủ yếu chọn theo tên.** Nếu không ghi `name`, Spring suy ra tên từ field/property; trong Spring, trường hợp default name không tồn tại có thể fallback theo type.
3. **Tên `@Resource(name = "...")` là yêu cầu rõ ràng.** Tên sai hoặc kiểu không tương thích sẽ làm injection thất bại thay vì tự chọn một implementation khác.
4. **`@Autowired` chủ yếu chọn theo type.** Khi nhiều ứng viên, dùng `@Qualifier` hoặc `@Primary` để biểu đạt lựa chọn.
5. **Tên field/parameter có thể là fallback trong một số quy tắc `@Autowired`**, nhưng không nên thay cho qualifier tường minh khi lựa chọn quan trọng.
6. **`@Resource` của Boot 3+/Spring 6 dùng `jakarta.annotation.Resource`**; code Boot 2/Spring 5 thường dùng `javax.annotation.Resource`.
7. **Constructor injection thường phù hợp cho dependency bắt buộc.** Kết hợp type và qualifier để có dependency rõ, dễ test và ít phụ thuộc vào tên field.

Khi gặp nhiều bean cùng implement một interface, hãy hỏi: **component cần một vai trò/type nào, hay cần bean có tên cụ thể nào?** Nếu câu trả lời là vai trò/type, dùng constructor injection cùng qualifier/primary khi cần. Nếu tên bean là contract cần tuân thủ, `@Resource(name = "...")` thể hiện trực tiếp ý định đó.
