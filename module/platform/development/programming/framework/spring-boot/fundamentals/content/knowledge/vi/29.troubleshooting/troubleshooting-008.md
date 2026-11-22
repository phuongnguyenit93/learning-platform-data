# BeanNotOfRequiredTypeException và kiểu thực tế của proxy

Một bean Spring có thể được khai báo bằng một class Java, nhưng object mà container trả về khi ứng dụng chạy **không nhất thiết có đúng class đó**. Spring có thể bọc bean bằng proxy để áp dụng transaction, security, caching, async execution, aspect hoặc scope. Vì vậy, khi code yêu cầu một implementation cụ thể nhưng Spring trả về proxy chỉ tương thích với interface, ứng dụng có thể gặp lỗi:

~~~text
org.springframework.beans.factory.BeanNotOfRequiredTypeException:
Bean named 'paymentService' is expected to be of type
'com.example.payment.PaymentServiceImpl' but was actually of type
'jdk.proxy2.$Proxy...'
~~~

Thông báo cho thấy bean có tên được yêu cầu, nhưng **kiểu runtime của object không gán được cho kiểu mà caller yêu cầu**.

Bài học **Spring Boot Fundamentals → Chẩn đoán lỗi → BeanNotOfRequiredTypeException và kiểu thực tế của proxy** giải thích exception này biểu thị điều gì, vì sao JDK dynamic proxy và CGLIB proxy có kiểu runtime khác nhau, tác động của các tính năng AOP, cách chẩn đoán target class và proxy class, cũng như cách chọn contract injection và proxy strategy phù hợp.

## 1. Hiểu đúng thông báo BeanNotOfRequiredTypeException

Giả sử ứng dụng có service:

~~~java
package com.example.payment;

public class PaymentServiceImpl {
    public void pay() {
        // Xử lý thanh toán.
    }
}
~~~

Code lấy bean bằng tên cùng kiểu bắt buộc:

~~~java
PaymentServiceImpl service =
        applicationContext.getBean(
                "paymentService",
                PaymentServiceImpl.class
        );
~~~

Lời gọi này yêu cầu Spring trả về bean tên `paymentService` và bảo đảm object trả về có thể gán cho `PaymentServiceImpl`.

Về mặt Java, điều kiện tương đương là:

~~~java
PaymentServiceImpl.class.isInstance(bean)
~~~

Nếu bean thực tế là một object proxy chỉ implement interface `PaymentService`, điều kiện trên là false. Spring không thể ép object proxy đó thành `PaymentServiceImpl`, nên ném `BeanNotOfRequiredTypeException`.

| Thành phần | Ý nghĩa |
|---|---|
| Bean name | Tên bean được yêu cầu, ví dụ `paymentService` |
| Required type | Kiểu mà caller muốn nhận, ví dụ `PaymentServiceImpl` |
| Actual type | Class runtime của object Spring thực sự trả về, ví dụ `jdk.proxy2.$Proxy...` |

**Exception không nhất thiết có nghĩa bean không tồn tại.** Nó thường cho biết Spring đã tìm thấy object dưới tên đó, nhưng object không đáp ứng kiểu được yêu cầu.

### 1.1. Ví dụ lỗi với JDK proxy

Ta định nghĩa interface và implementation:

~~~java
package com.example.payment;

public interface PaymentService {
    void pay();
}
~~~

~~~java
package com.example.payment;

public class PaymentServiceImpl implements PaymentService {
    @Override
    public void pay() {
        // Xử lý thanh toán.
    }
}
~~~

Khi Spring tạo JDK dynamic proxy, object được trả về có thể có kiểu runtime dạng `jdk.proxy2.$Proxy42`.

Object proxy implement `PaymentService`, nhưng không phải là subclass của `PaymentServiceImpl`.

Vì vậy:

~~~java
PaymentService service =
        applicationContext.getBean(
                "paymentService",
                PaymentService.class
        );
~~~

có thể hoạt động, còn:

~~~java
PaymentServiceImpl service =
        applicationContext.getBean(
                "paymentService",
                PaymentServiceImpl.class
        );
~~~

có thể ném `BeanNotOfRequiredTypeException`.

Đây là ví dụ điển hình về **kiểu khai báo của target khác với kiểu runtime của proxy**.

## 2. Proxy là gì và tại sao Spring tạo proxy?

Proxy là một object đứng trước object khác để kiểm soát hoặc bổ sung hành vi khi method được gọi.

Trong Spring, proxy thường được dùng để thực hiện những chức năng nằm ngoài logic nghiệp vụ chính:

- Mở và commit/rollback transaction.
- Kiểm tra quyền truy cập.
- Ghi và đọc cache.
- Chạy method bất đồng bộ.
- Áp dụng logging, tracing hoặc profiling bằng aspect.
- Áp dụng phạm vi bean như request/session scope trong một số mô hình.

Luồng gọi có thể như sau:

~~~text
Caller
  |
  v
Spring proxy
  |
  +-- Kiểm tra quyền
  +-- Bắt đầu transaction
  +-- Chạy interceptor/aspect
  |
  v
Target object
  |
  v
Kết quả hoặc exception
  |
  v
Proxy hoàn tất interceptor
  |
  v
Caller nhận kết quả
~~~

Caller thường chỉ cần biết contract mà bean cung cấp. Proxy đảm nhiệm phần điều phối trước và sau lời gọi target.

**Proxy không phải bản sao của target object.** Nó là một object riêng có thể có class runtime khác, và việc có thể cast sang target implementation hay không phụ thuộc loại proxy.

### 2.1. Ví dụ với @Transactional

~~~java
@Service
public class PaymentServiceImpl implements PaymentService {

    @Override
    @Transactional
    public void pay() {
        // Các thao tác database trong transaction.
    }
}
~~~

Khi transaction management được bật, Spring có thể tạo proxy để bắt lời gọi `pay()`, bắt đầu transaction trước khi gọi target và commit hoặc rollback sau đó.

Caller inject bean từ container sẽ nhận **proxy được quản lý**, không nhất thiết nhận object `new PaymentServiceImpl()` nguyên bản.

### 2.2. Không phải mọi bean đều được proxy

Một bean chỉ bị proxy khi có cơ chế cần áp dụng, ví dụ:

- Có advisor/aspect phù hợp.
- Có annotation được xử lý bằng proxy-based infrastructure.
- Bean nằm trong scope cần scoped proxy.
- Có post-processor hoặc framework feature tạo proxy.

Nếu bean không có cơ chế nào cần proxy, object trả về có thể chính là instance của class implementation.

Không nên nhìn một class có `@Service` rồi kết luận nó chắc chắn là JDK proxy hoặc CGLIB proxy. Cần kiểm tra runtime object.

## 3. Hai kiểu proxy phổ biến: JDK dynamic proxy và CGLIB

Spring AOP thường sử dụng một trong hai cách:

1. **JDK dynamic proxy:** tạo object proxy implement các interface.
2. **CGLIB class-based proxy:** tạo class proxy kế thừa target class và override những method có thể intercept.

| Đặc điểm | JDK dynamic proxy | CGLIB proxy |
|---|---|---|
| Cơ chế | Implement interface | Subclass target class |
| Kiểu runtime | Class dạng `$Proxy...` | Class dạng `TargetClass$$SpringCGLIB$$...` |
| Gán cho interface target implement | Có | Có, kế thừa interface |
| Gán cho concrete target class | Không | Thường có, vì proxy là subclass |
| Target class final | Có thể proxy interface dù implementation final | Không thể subclass final class |
| Final method | Interface invocation có thể được intercept qua proxy | Final method không thể override để intercept |
| Không có interface | Không phù hợp | Có thể dùng nếu class có thể subclass |
| Ràng buộc chính | Phải có interface cần expose | Cần class/method có thể override |

### 3.1. JDK dynamic proxy

~~~java
public interface ReportService {
    void generate();
}

public class ReportServiceImpl implements ReportService {
    @Override
    public void generate() {
        // Tạo báo cáo.
    }
}
~~~

JDK proxy có thể implement `ReportService`:

~~~text
ReportService
      ^
      |
jdk.proxy2.$Proxy42
      |
      +-- invocation handler
                |
                v
          ReportServiceImpl
~~~

Nhưng proxy không kế thừa `ReportServiceImpl`:

~~~java
Object proxy = /* JDK proxy */;

System.out.println(proxy instanceof ReportService);
// true

System.out.println(proxy instanceof ReportServiceImpl);
// false
~~~

Đây là nguyên nhân trực tiếp khiến lookup theo concrete implementation có thể thất bại.

### 3.2. CGLIB class-based proxy

Với CGLIB, Spring tạo một class con của implementation:

~~~text
ReportServiceImpl
       ^
       |
ReportServiceImpl$$SpringCGLIB$$0
       |
       +-- method interception
                |
                v
          target object
~~~

Vì proxy là subclass nên:

~~~java
Object proxy = /* CGLIB proxy */;

System.out.println(proxy instanceof ReportServiceImpl);
// true
~~~

Điều này có thể làm cho lookup hoặc injection theo concrete class hoạt động trong trường hợp JDK proxy không tương thích.

Tuy nhiên, CGLIB không loại bỏ mọi vấn đề về kiểu. Nó không thể kế thừa class `final`, và không thể override method `final` để áp dụng interception. Private method cũng không được override theo cơ chế proxy subclass.

## 4. Target class, proxy class và required type

Giả sử code khai báo:

~~~java
@Service
public class InvoiceService implements InvoiceOperations {

    @Override
    public void issueInvoice() {
        // Logic nghiệp vụ.
    }
}
~~~

Target object có class `com.example.invoice.InvoiceService`. Nhưng khi Spring áp dụng AOP, object trả về có thể là:

~~~text
jdk.proxy2.$Proxy57
~~~

hoặc:

~~~text
com.example.invoice.InvoiceService$$SpringCGLIB$$0
~~~

Cần phân biệt:

- **Declared type:** kiểu được khai báo ở field, parameter hoặc return type của method.
- **Target class:** class của object chứa logic nghiệp vụ phía sau proxy.
- **Proxy class:** class runtime của object caller nhận từ Spring.
- **Exposed interfaces:** các interface mà proxy công bố cho caller.
- **Required type:** kiểu caller yêu cầu khi lookup hoặc inject.

Một proxy có thể đại diện cho target class nhưng không phải là target class. Không nên dùng `bean.getClass()` để suy ra trực tiếp class nghiệp vụ khi biết bean có thể bị proxy.

## 5. Inject implementation thay vì interface

Thiết kế:

~~~java
public interface OrderOperations {
    void createOrder();
}
~~~

~~~java
@Service
public class OrderService implements OrderOperations {

    @Override
    @Transactional
    public void createOrder() {
        // Lưu đơn hàng.
    }
}
~~~

Consumer inject interface:

~~~java
@Service
public class CheckoutFacade {

    private final OrderOperations orderOperations;

    public CheckoutFacade(OrderOperations orderOperations) {
        this.orderOperations = orderOperations;
    }
}
~~~

Đây là cách thiết kế phù hợp với JDK proxy vì proxy expose interface `OrderOperations`.

Ngược lại:

~~~java
@Service
public class CheckoutFacade {

    private final OrderService orderService;

    public CheckoutFacade(OrderService orderService) {
        this.orderService = orderService;
    }
}
~~~

Nếu bean được tạo thành JDK proxy chỉ expose `OrderOperations`, consumer yêu cầu `OrderService` sẽ không tương thích.

Tùy đường resolve dependency và metadata của bean, lỗi khởi động có thể được trình bày dưới dạng lỗi không tìm thấy candidate phù hợp hoặc lỗi kiểu thực tế không tương thích. Điểm cốt lõi vẫn là: **caller yêu cầu concrete class trong khi object được expose không phải instance của class đó**.

### 5.1. Vì sao inject interface thường tốt hơn?

Inject interface giúp:

- Caller phụ thuộc vào contract, không phụ thuộc implementation.
- Có thể thay implementation mà không đổi consumer.
- Tương thích với JDK dynamic proxy.
- Test dễ thay bằng fake hoặc mock.
- Hạn chế caller truy cập chi tiết nội bộ của target.
- Giảm coupling giữa các module.

~~~java
public interface PaymentOperations {
    PaymentResult pay(PaymentCommand command);
}
~~~

~~~java
@Service
public class PaymentService implements PaymentOperations {
    @Override
    public PaymentResult pay(PaymentCommand command) {
        // ...
    }
}
~~~

~~~java
@Service
public class CheckoutService {

    private final PaymentOperations payments;

    public CheckoutService(PaymentOperations payments) {
        this.payments = payments;
    }
}
~~~

Consumer chỉ biết `PaymentOperations`. Spring có thể cung cấp target hoặc proxy miễn object đó đáp ứng interface.

Không cần tạo interface cho mọi class chỉ để tránh exception. Interface hữu ích khi nó biểu đạt contract, boundary hoặc khả năng thay thế. Với class nội bộ không có nhu cầu abstraction, class-based proxy cũng có thể phù hợp nếu thỏa giới hạn.

## 6. Lookup theo bean name và required type

Một API dễ làm xuất hiện exception là:

~~~java
<T> T getBean(String name, Class<T> requiredType)
~~~

Ví dụ:

~~~java
PaymentService service =
        context.getBean("paymentService", PaymentService.class);
~~~

Spring tìm bean theo tên rồi kiểm tra object trả về có gán được cho `requiredType` hay không.

| Cách gọi | Ý nghĩa |
|---|---|
| `getBean("paymentService")` | Lấy object theo tên, kiểu trả về là `Object` |
| `getBean("paymentService", PaymentService.class)` | Lấy theo tên và yêu cầu object tương thích với interface |
| `getBean("paymentService", PaymentServiceImpl.class)` | Lấy theo tên và yêu cầu object tương thích với implementation |

Với JDK proxy expose `PaymentService`, lookup theo interface phù hợp; lookup theo concrete implementation có thể thất bại.

Một cách chẩn đoán:

~~~java
Object bean = context.getBean("paymentService");

System.out.println(bean.getClass().getName());

PaymentService contract =
        context.getBean("paymentService", PaymentService.class);
~~~

Nếu output cho thấy `jdk.proxy2.$Proxy...`, điều đó gợi ý object là JDK dynamic proxy. Sau đó cần kiểm tra interface mà proxy expose và class target phía sau.

Không nên sửa bằng cách ép kiểu:

~~~java
PaymentServiceImpl implementation =
        (PaymentServiceImpl) context.getBean("paymentService");
~~~

Nếu object là JDK proxy, cast sẽ ném `ClassCastException`. Cast không thể biến một object proxy thành subclass của target.

## 7. @Qualifier và @Primary không sửa được lỗi kiểu runtime

`@Qualifier` chọn bean phù hợp trong số nhiều candidate. `@Primary` ưu tiên một candidate khi có nhiều bean cùng phù hợp.

Ví dụ:

~~~java
@Autowired
@Qualifier("paymentService")
private PaymentOperations payments;
~~~

Cấu hình này chọn bean tên `paymentService` theo contract `PaymentOperations`.

Nhưng nếu viết:

~~~java
@Autowired
@Qualifier("paymentService")
private PaymentServiceImpl payments;
~~~

`@Qualifier` chỉ giúp chọn candidate theo định danh. Nó **không biến JDK proxy thành `PaymentServiceImpl`**.

Tương tự, `@Primary` không thay đổi class runtime của proxy. Nếu bean được chọn vẫn là JDK proxy không tương thích với concrete type, lỗi kiểu vẫn tồn tại.

Hãy giải quyết đúng hai câu hỏi: có chọn đúng bean không, và object được expose có thực sự assignable với required type không?

## 8. @Bean factory method và kiểu khai báo trả về

Một nguồn nhầm lẫn khác là kiểu khai báo của method `@Bean`.

~~~java
@Bean
PaymentOperations paymentService() {
    return new PaymentService();
}
~~~

Spring nhìn thấy return type được khai báo là `PaymentOperations`. Kiểu này đủ để tìm bean theo interface, nhưng không nhất thiết đủ thông tin để dự đoán concrete implementation trước khi bean được tạo.

Nếu code ở nơi khác yêu cầu `PaymentService`, quá trình tìm candidate có thể gặp vấn đề ngay cả trước khi xét đến AOP proxy.

Khai báo concrete return type có thể cung cấp metadata cụ thể hơn:

~~~java
@Bean
PaymentService paymentService() {
    return new PaymentService();
}
~~~

Nhưng nếu Spring sau đó bọc bean bằng JDK proxy, object runtime vẫn có thể chỉ expose interface.

Vì vậy:

- Return type của `@Bean` ảnh hưởng khả năng dự đoán kiểu bean trước khi khởi tạo.
- Proxy strategy ảnh hưởng kiểu runtime object được expose.
- Hai vấn đề liên quan nhưng không giống nhau.

Thiết kế ổn định thường để consumer phụ thuộc interface và khai báo factory method đủ thông tin cho nhu cầu thực tế.
## 21. @Async và proxy: kiểu runtime không phải điều duy nhất cần chú ý

§@Async§ thường sử dụng proxy để chuyển lời gọi method sang executor.

~~~java
public interface ReportOperations {
    CompletableFuture<String> generate();
}
~~~

~~~java
@Service
public class ReportService implements ReportOperations {

    @Override
    @Async
    public CompletableFuture<String> generate() {
        return CompletableFuture.completedFuture("done");
    }
}
~~~

Consumer nên inject interface:

~~~java
@Service
public class ReportControllerFacade {

    private final ReportOperations reports;

    public ReportControllerFacade(ReportOperations reports) {
        this.reports = reports;
    }
}
~~~

Nếu proxy là JDK dynamic proxy, injection theo §ReportService§ có thể không tương thích.

Ngoài ra, §@Async§ có giới hạn proxy mode:

- Lời gọi từ bean khác qua proxy mới được intercept theo cách thông thường.
- Self-invocation trong cùng instance có thể không chạy async.
- Method được gọi cần phù hợp với quy tắc của proxy và executor.
- Exception trong async method được truyền qua future hoặc cơ chế xử lý async, không nhất thiết quay lại caller theo cách đồng bộ.

Khi chẩn đoán, hãy tách hai vấn đề: **caller có đang nhận đúng kiểu proxy không** và **lời gọi có thực sự đi qua proxy hay không**.

## 22. @Transactional: đừng ép target để tự gọi method

Một cách sửa sai thường gặp là lấy target object ra khỏi proxy để gọi trực tiếp:

~~~java
PaymentServiceImpl target =
        (PaymentServiceImpl) AopProxyUtils.getSingletonTarget(bean);
~~~

hoặc dùng tiện ích test để unwrap target.

Cách này có thể bỏ qua interceptor chain:

- Transaction không được mở như dự kiến.
- Security advice không được áp dụng.
- Cache không hoạt động.
- Metrics/tracing advice bị bỏ qua.
- Caller phụ thuộc vào implementation nội bộ.

Trong code production, nên gọi qua proxy contract mà container cung cấp:

~~~java
PaymentOperations payments =
        context.getBean(PaymentOperations.class);

payments.pay();
~~~

Nếu cần test logic thuần của target, unit test trực tiếp implementation hoặc test với dependency fake. Không biến thao tác unwrap proxy thành cách truy cập service thông thường.

## 23. Chẩn đoán theo stack trace và required/actual type

Khi gặp exception, đọc ba giá trị đầu tiên:

1. **Bean name:** tên bean nào đang được resolve?
2. **Required type:** caller yêu cầu kiểu gì?
3. **Actual type:** object được trả về có class runtime nào?

Ví dụ:

~~~text
Bean named 'orderService'
is expected to be of type
'com.example.orders.OrderService'
but was actually of type
'jdk.proxy2.$Proxy81'
~~~

Có thể lập luận:

- Bean §orderService§ có tồn tại.
- Caller yêu cầu §OrderService§.
- Actual object là JDK proxy.
- Cần xác định interface mà proxy implement.
- Nếu §OrderService§ là implementation class và proxy chỉ expose interface, yêu cầu concrete type không phù hợp.

Sau đó tìm vị trí phát sinh lookup:

~~~java
context.getBean("orderService", OrderService.class);
~~~

hoặc injection:

~~~java
@Autowired
private OrderService orderService;
~~~

hoặc một API gián tiếp gọi bean theo name/type.

Tìm **nơi yêu cầu type**, không chỉ nơi định nghĩa class. Exception thường phát sinh tại ranh giới lấy bean, còn nguyên nhân thiết kế có thể nằm ở proxy configuration hoặc contract injection.

## 24. Quy trình chẩn đoán từng bước

### Bước 1 — Đọc actual type trong exception

Nếu là §jdk.proxy...§, xem các interface mà proxy expose. Nếu là §$$SpringCGLIB$$§, xác định target class và giới hạn subclass. Nếu là class không liên quan, kiểm tra bean registration.

### Bước 2 — Tìm required type

Xác định code đang yêu cầu implementation class, interface hay một kiểu cha khác.

### Bước 3 — Xác định đường lấy bean

Tìm:

- §getBean(name, requiredType)§.
- §@Autowired§ hoặc constructor injection.
- §@Resource(name)§.
- §ObjectProvider<T>§ hoặc §Provider<T>§.
- Factory method, scoped proxy hoặc FactoryBean.
- Cấu hình test override.

### Bước 4 — Kiểm tra proxy có được tạo hay không

Dùng §AopUtils.isAopProxy§, §isJdkDynamicProxy§, §isCglibProxy§ và §getTargetClass§.

### Bước 5 — Xác định advisor nào làm bean được proxy

Tìm §@Transactional§, §@Async§, §@Cacheable§, §@PreAuthorize§, custom aspects và post-processors.

### Bước 6 — So sánh các môi trường

Nếu chỉ lỗi ở production hoặc một profile, so sánh:

- §spring.aop.proxy-target-class§.
- Transaction/async/security configuration.
- Dependency và version.
- Profile-specific bean definitions.
- Custom BeanPostProcessor.
- Test override hoặc mock configuration.

### Bước 7 — Sửa ở contract hoặc proxy strategy

Ưu tiên interface phù hợp. Nếu thật sự cần concrete type, cân nhắc class-based proxy và kiểm tra target class có thể subclass hay không.

### Bước 8 — Thêm test regression

Tạo context test với advisor/proxy tương ứng và assert consumer có thể inject/gọi contract mong muốn.

Không chỉ sửa property rồi kết luận xong; test phải chứng minh **đường truy cập thực tế của ứng dụng** đã hoạt động.

## 25. Ví dụ: sửa một consumer inject implementation

### Code gây vấn đề

~~~java
public interface CustomerService {
    Customer findById(long id);
}
~~~

~~~java
@Service
public class CustomerServiceImpl implements CustomerService {

    @Override
    @Transactional(readOnly = true)
    public Customer findById(long id) {
        // Truy vấn customer.
        return null;
    }
}
~~~

~~~java
@Service
public class CustomerControllerFacade {

    private final CustomerServiceImpl service;

    public CustomerControllerFacade(CustomerServiceImpl service) {
        this.service = service;
    }
}
~~~

Nếu Spring expose bean qua JDK proxy chỉ implement §CustomerService§, consumer yêu cầu §CustomerServiceImpl§ sẽ không tương thích.

### Sửa theo interface

~~~java
@Service
public class CustomerControllerFacade {

    private final CustomerService service;

    public CustomerControllerFacade(CustomerService service) {
        this.service = service;
    }
}
~~~

Không cần thay đổi logic trong §CustomerServiceImpl§. Caller sử dụng contract và Spring có thể cung cấp target hoặc proxy tương thích.

### Vì sao đây thường là lựa chọn tốt?

Consumer không cần biết transaction được thực hiện bằng proxy, aspect hay một implementation khác. Nó chỉ cần một object đáp ứng §CustomerService§.

Đây là lợi ích thiết kế, không chỉ là workaround cho exception.

## 26. Khi nào class-based proxy là lựa chọn hợp lý?

Có những trường hợp dự án không có interface riêng cho bean hoặc cần expose concrete class do một ràng buộc thiết kế.

Khi đó có thể cân nhắc:

~~~properties
spring.aop.proxy-target-class=true
~~~

Hoặc cấu hình cụ thể theo cơ chế AOP/transaction đang dùng.

Trước khi chọn, xác nhận:

- Target class không final.
- Method cần intercept không final/private/static.
- Không dựa vào self-invocation để kích hoạt advice.
- Proxy class có thể được tạo trong runtime/module environment.
- Việc thay đổi strategy không ảnh hưởng những bean khác.
- Consumer thật sự cần concrete type hay chỉ đang phụ thuộc implementation không cần thiết.

Class-based proxy không có nghĩa target object được expose nguyên vẹn; caller vẫn đang tương tác với proxy subclass. Chỉ là proxy subclass có thể gán được cho target class.

## 27. Không nhầm proxy AOP với proxy của @Configuration

Spring có thể dùng CGLIB để tạo subclass của class §@Configuration§ nhằm hỗ trợ method interception giữa các §@Bean§ method khi §proxyBeanMethods=true§.

Ví dụ:

~~~java
@Configuration
public class AppConfiguration {

    @Bean
    FirstService firstService() {
        return new FirstService();
    }

    @Bean
    SecondService secondService() {
        return new SecondService(firstService());
    }
}
~~~

Trong full configuration mode, Spring có thể intercept lời gọi §firstService()§ để trả về singleton bean thay vì tạo instance mới.

Đây là **configuration class proxy**, khác với AOP proxy bọc service để áp dụng transaction/security.

Khi cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
~~~

cơ chế intercept lời gọi giữa các §@Bean§ method bị tắt; lúc đó không nên gọi trực tiếp một §@Bean§ method khác như thể nó luôn trả về singleton được container quản lý. Thay vào đó, inject dependency vào method factory:

~~~java
@Bean
SecondService secondService(FirstService firstService) {
    return new SecondService(firstService);
}
~~~

Đừng nhìn thấy class name có §$$SpringCGLIB$$§ rồi kết luận mọi CGLIB proxy đều do §@Transactional§ tạo. Hãy xác định loại bean và mục đích proxy.

## 28. Một số lỗi sửa sai thường gặp

| Cách sửa | Vì sao chưa chắc đúng |
|---|---|
| Cast JDK proxy sang implementation | Object không phải instance của implementation |
| Bật CGLIB cho toàn ứng dụng ngay lập tức | Có thể gặp final class/method và ảnh hưởng nhiều bean |
| Thêm §@Primary§ | Chỉ ưu tiên candidate, không đổi kiểu proxy |
| Thêm §@Qualifier§ | Chỉ chọn bean, không biến proxy thành target class |
| Xóa §@Transactional§ | Có thể làm mất transaction behavior cần thiết |
| Unwrap target trong production | Có thể bỏ qua interceptor và phá contract container |
| So sánh §bean.getClass()§ với class implementation | Proxy class có thể khác dù bean hoạt động đúng |
| Dùng reflection để truy cập target field | Phụ thuộc implementation nội bộ và dễ vỡ |
| Tạo §new PaymentServiceImpl()§ trong consumer | Bỏ qua DI, proxy, transaction và lifecycle của Spring |
| Đổi tên bean ngẫu nhiên | Không giải quyết mismatch giữa required type và actual type |
| Tắt AOP toàn cục | Có thể vô hiệu hóa transaction, security, cache hoặc async |

Hãy xác định lỗi thực tế trước khi thay đổi cấu hình.

## 29. Kiểm thử regression cho contract proxy

Một test regression tốt nên mô phỏng đúng cơ chế gây lỗi.

Ví dụ dùng §ProxyFactory§ để tạo JDK proxy và xác nhận:

~~~java
@Test
void jdkProxyExposesInterfaceButNotImplementation() {
    GreetingService target = new GreetingService();

    ProxyFactory factory = new ProxyFactory();
    factory.setTarget(target);
    factory.setInterfaces(GreetingOperations.class);
    factory.setProxyTargetClass(false);

    Object proxy = factory.getProxy();

    assertTrue(proxy instanceof GreetingOperations);
    assertFalse(proxy instanceof GreetingService);
}
~~~

Sau đó có thể xác nhận lookup theo interface thành công và lookup theo implementation thất bại bằng §DefaultListableBeanFactory§:

~~~java
@Test
void typedLookupRejectsIncompatibleProxy() {
    GreetingService target = new GreetingService();

    ProxyFactory factory = new ProxyFactory();
    factory.setTarget(target);
    factory.setInterfaces(GreetingOperations.class);
    factory.setProxyTargetClass(false);

    Object proxy = factory.getProxy();

    DefaultListableBeanFactory beanFactory =
            new DefaultListableBeanFactory();

    beanFactory.registerSingleton("greeting", proxy);

    assertNotNull(
            beanFactory.getBean(
                    "greeting",
                    GreetingOperations.class)
    );

    assertThrows(
            BeanNotOfRequiredTypeException.class,
            () -> beanFactory.getBean(
                    "greeting",
                    GreetingService.class)
    );
}
~~~

Test này cô lập contract của bean factory và proxy. Trong một ứng dụng thật, nên có thêm context-level test cho cấu hình AOP thực tế để xác nhận đúng advisor và proxy strategy được áp dụng.

### Test consumer nên inject contract

~~~java
@SpringBootTest
class CheckoutFacadeTest {

    @Autowired
    CheckoutFacade checkoutFacade;

    @Autowired
    PaymentOperations paymentOperations;

    @Test
    void injectsProxyThroughInterface() {
        assertNotNull(checkoutFacade);
        assertNotNull(paymentOperations);
    }
}
~~~

Nếu mục tiêu là chứng minh transaction advice chạy, cần test hành vi transaction phù hợp, không chỉ assert bean được inject.

## 30. Chẩn đoán trong debugger và log

Khi dừng tại điểm có bean object, xem:

~~~java
bean.getClass().getName()
~~~

Sau đó:

~~~java
AopUtils.isAopProxy(bean)
AopUtils.isJdkDynamicProxy(bean)
AopUtils.isCglibProxy(bean)
AopUtils.getTargetClass(bean)
~~~

Có thể log chẩn đoán có kiểm soát:

~~~java
log.debug(
        "Resolved bean name={} runtimeType={} targetType={} jdkProxy={} cglibProxy={}",
        beanName,
        bean.getClass().getName(),
        AopUtils.getTargetClass(bean).getName(),
        AopUtils.isJdkDynamicProxy(bean),
        AopUtils.isCglibProxy(bean)
);
~~~

Không nên ghi toàn bộ object hoặc state nội bộ của target. Tên class thường đủ để điều tra proxy strategy.

Nếu cần kiểm tra các interface:

~~~java
Class<?>[] interfaces = bean.getClass().getInterfaces();

for (Class<?> contract : interfaces) {
    log.debug("Exposed interface={}", contract.getName());
}
~~~

Lưu ý class-based proxy có thể kế thừa interface từ target; nếu cần danh sách contract đầy đủ, nên xem cả superclass hierarchy.

## 31. BeanNotOfRequiredTypeException khác các exception gần giống

| Exception | Ý nghĩa chính |
|---|---|
| §BeanNotOfRequiredTypeException§ | Bean theo tên đã có object nhưng object không tương thích required type |
| §NoSuchBeanDefinitionException§ | Không tìm được bean definition/candidate phù hợp |
| §NoUniqueBeanDefinitionException§ | Có nhiều candidate nhưng không xác định được một bean duy nhất |
| §BeanCreationException§ | Lỗi trong quá trình tạo bean |
| §UnsatisfiedDependencyException§ | Dependency không được resolve hoặc không thể inject |
| §ClassCastException§ | Code Java tự cast object sang kiểu không tương thích |
| §NoSuchMethodException§ | Reflection không tìm được method theo yêu cầu |

Trong startup, một exception có thể được bọc trong exception khác. Ví dụ §UnsatisfiedDependencyException§ có thể chứa nguyên nhân sâu hơn là §BeanNotOfRequiredTypeException§.

Khi đọc stack trace, hãy tìm **root cause** và dòng đầu tiên của code ứng dụng nơi bean được yêu cầu.

Không nên chỉ nhìn exception ngoài cùng rồi đổi cấu hình ngẫu nhiên.

## 32. Trường hợp bean có nhiều interface

Một implementation có thể implement nhiều interface:

~~~java
public class AccountService
        implements AccountOperations, AuditOperations {
    // ...
}
~~~

JDK proxy có thể expose cả hai interface nếu chúng được đưa vào proxy configuration.

Khi đó caller có thể inject:

~~~java
AccountOperations accounts;
~~~

hoặc:

~~~java
AuditOperations audit;
~~~

Nhưng nếu proxy chỉ được tạo với §AccountOperations§, caller yêu cầu §AuditOperations§ vẫn không tương thích dù target class có implement interface đó.

Vì vậy, khi dùng JDK proxy, **đừng chỉ kiểm tra target class implement interface nào; cần kiểm tra proxy thực sự expose interface nào**.

Nếu một advisor hoặc proxy factory được cấu hình với tập interface giới hạn, tập interface đó quyết định contract caller có thể sử dụng.

## 33. Proxy lồng nhau và target class

Trong một ứng dụng có nhiều infrastructure, bean có thể trải qua nhiều lớp proxy hoặc wrapper. Ví dụ một proxy security, transaction hoặc custom instrumentation có thể được phối hợp hoặc bọc qua nhiều tầng tùy cấu hình.

Khi đó:

- §bean.getClass()§ chỉ cho biết lớp ngoài cùng.
- §AopUtils.getTargetClass(bean)§ có thể giúp xác định target class mà Spring nhận diện.
- §AopProxyUtils.ultimateTargetClass(bean)§ có thể hữu ích khi cần xác định ultimate target class trong các trường hợp hỗ trợ.
- Việc lấy target object thật có thể bị giới hạn bởi proxy, scope hoặc target source.

Không nên viết logic production phụ thuộc vào việc unwrap thành công mọi lớp proxy. Proxy là chi tiết triển khai của container; contract ổn định nên là interface hoặc class mà bean đã cam kết expose.

## 34. Nguyên tắc thiết kế để tránh lỗi về sau

1. **Inject theo contract:** ưu tiên interface khi bean được expose qua interface.
2. **Không ép kiểu target:** tránh cast proxy sang implementation.
3. **Tạo bean qua container:** không tự §new§ service trong consumer.
4. **Giữ factory method rõ kiểu:** khai báo return type phản ánh contract và metadata cần thiết.
5. **Hiểu proxy strategy:** biết project đang dùng JDK hay class-based proxy.
6. **Kiểm tra giới hạn CGLIB:** final class/method và self-invocation.
7. **Không dùng qualifier để sửa mismatch:** qualifier chỉ chọn candidate.
8. **Test đúng wiring:** kiểm tra context và proxy thật khi chức năng phụ thuộc AOP.
9. **Không khóa test vào tên proxy runtime:** dùng §AopUtils§.
10. **Giữ AOP behavior:** không xóa transaction/security/cache chỉ để tránh exception.
11. **Xác định advisor:** biết annotation hoặc post-processor nào tạo proxy.
12. **Phân biệt proxy AOP và scoped/configuration proxy:** chúng có mục đích khác nhau.

## 35. Bài tập thực hành

### Bài tập 1: Tái hiện JDK proxy

Tạo interface §GreetingOperations§ và class §GreetingService§ implement interface đó.

Dùng §ProxyFactory§:

~~~java
factory.setTarget(new GreetingService());
factory.setInterfaces(GreetingOperations.class);
factory.setProxyTargetClass(false);
~~~

Kiểm tra:

- Proxy có phải §GreetingOperations§ không?
- Proxy có phải §GreetingService§ không?
- §bean.getClass()§ trả về class nào?

**Mục tiêu:** quan sát trực tiếp vì sao target class và proxy class khác nhau.

### Bài tập 2: Tái hiện BeanNotOfRequiredTypeException

Đăng ký JDK proxy vào §DefaultListableBeanFactory§ dưới tên §greeting§.

Thử:

~~~java
beanFactory.getBean("greeting", GreetingOperations.class);
~~~

Sau đó:

~~~java
beanFactory.getBean("greeting", GreetingService.class);
~~~

Giải thích sự khác biệt dựa trên phép kiểm tra assignability.

### Bài tập 3: Sửa injection

Một consumer inject:

~~~java
private final PaymentServiceImpl paymentService;
~~~

Trong khi bean được expose bằng JDK proxy implement §PaymentOperations§.

Hãy sửa consumer để inject §PaymentOperations§ và giải thích vì sao cách sửa không cần thay đổi target implementation.

### Bài tập 4: So sánh CGLIB

Tạo lại proxy với:

~~~java
factory.setProxyTargetClass(true);
~~~

Kiểm tra §instanceof GreetingService§. Sau đó khai báo target class là §final§ và quan sát việc tạo class-based proxy thất bại.

### Bài tập 5: Phân biệt lỗi proxy và lỗi bean name

Tạo một bean có tên §paymentService§ nhưng factory method trả về object §String§. Gọi §getBean("paymentService", PaymentOperations.class)§.

Giải thích vì sao actual type là §String§ cho thấy lỗi đăng ký bean, không phải lỗi JDK proxy.

### Bài tập 6: Quan sát bean runtime trong Spring Boot

Tạo một service có interface và bật một advisor như transaction hoặc aspect. Inject bean theo interface, rồi in:

~~~java
AopUtils.isAopProxy(bean)
AopUtils.isJdkDynamicProxy(bean)
AopUtils.isCglibProxy(bean)
AopUtils.getTargetClass(bean)
~~~

Thay đổi proxy configuration trong môi trường test và quan sát kiểu runtime. Không dựa vào tên §$Proxy42§ cố định vì tên này không ổn định.

## 36. Checklist điều tra một lỗi thực tế

Khi gặp §BeanNotOfRequiredTypeException§, hãy trả lời theo thứ tự:

- Bean name nào xuất hiện trong exception?
- Required type là interface hay concrete class?
- Actual runtime type là JDK proxy, CGLIB proxy hay một class khác?
- Target class thực tế là gì?
- Proxy expose những interface nào?
- Bean có §@Transactional§, §@Async§, §@Cacheable§, security annotation hoặc custom aspect không?
- Consumer đang inject theo interface hay implementation?
- Bean được tạo từ §@Component§, §@Bean§ hay §FactoryBean§?
- Profile nào đang active?
- Có bean override, alias hoặc test mock nào không?
- §spring.aop.proxy-target-class§ có bị override không?
- Class target có final hoặc method cần intercept có final/private không?
- Có self-invocation khiến advice không được áp dụng không?
- Có thể sửa consumer để phụ thuộc contract không?
- Test regression đã mô phỏng đúng proxy strategy chưa?

Không cần thay đổi tất cả cấu hình. Một câu trả lời chính xác cho required type, actual type và bean registration thường đủ thu hẹp nguyên nhân.

## Kết luận

§BeanNotOfRequiredTypeException§ xuất hiện khi bean được yêu cầu theo tên nhưng object Spring trả về **không tương thích với kiểu mà caller yêu cầu**. Một nguyên nhân phổ biến là Spring AOP bọc implementation bằng **JDK dynamic proxy**, vốn expose interface nhưng không kế thừa concrete target class.

Cần phân biệt:

- **Target class:** class chứa logic nghiệp vụ.
- **Proxy class:** class runtime caller nhận được.
- **Required type:** kiểu mà caller muốn inject hoặc lookup.
- **Exposed interface:** contract proxy thực sự hỗ trợ.

JDK proxy phù hợp với thiết kế hướng interface; CGLIB tạo subclass và có thể tương thích với concrete class nhưng bị giới hạn bởi final class/method và cơ chế self-invocation. Các tính năng như transaction, async, cache, security và scoped proxy đều có thể ảnh hưởng kiểu object được expose.

Khi chẩn đoán, đọc bean name, required type và actual type trong exception; dùng §AopUtils§ để xác định proxy; kiểm tra bean registration và đường injection. **Ưu tiên để consumer phụ thuộc interface mà proxy cung cấp**, chỉ chuyển sang class-based proxy khi có lý do rõ ràng và target class đáp ứng các giới hạn. Không cast proxy, unwrap target trong code nghiệp vụ hoặc tắt AOP chỉ để làm exception biến mất.

Hiểu đúng kiểu runtime của proxy giúp giải quyết lỗi tại nguyên nhân, đồng thời giữ được các hành vi quan trọng mà Spring bổ sung quanh bean như transaction, security và caching.
+## 9. Các tính năng Spring có thể tạo proxy

§BeanNotOfRequiredTypeException§ không chỉ liên quan §@Transactional§. Những tính năng sau cũng có thể sử dụng proxy:

| Tính năng | Mục đích proxy | Điều cần lưu ý |
|---|---|---|
| §@Transactional§ | Transaction boundary | Inject theo interface nếu dùng JDK proxy |
| §@Async§ | Chuyển lời gọi sang executor | Self-invocation có thể không đi qua proxy |
| §@Cacheable§ | Đọc/ghi cache quanh method | Không nên ép bean thành target class |
| §@PreAuthorize§ | Kiểm tra quyền method | Proxy phải expose đúng contract |
| Custom §@Aspect§ | Logging, metrics, audit | Advisor có thể làm bean được bọc |
| Scoped proxy | Đại diện cho bean scope ngắn hơn | Proxy có kiểu riêng, target được lấy theo scope |
| Method validation | Áp dụng validation qua interceptor | Kiểu object có thể là proxy |

Nếu một bean đồng thời chịu nhiều advisor, Spring thường phối hợp chúng trong cùng proxy chain. Caller vẫn làm việc với object proxy đã được expose.

## 10. JDK proxy có thể hoạt động với target class final

Một điểm quan trọng: JDK proxy không cần kế thừa target class. Nó chỉ cần implement interface.

~~~java
public interface PaymentOperations {
    void pay();
}
~~~

~~~java
public final class PaymentService implements PaymentOperations {
    @Override
    public void pay() {
        // ...
    }
}
~~~

Một JDK proxy vẫn có thể implement §PaymentOperations§ và delegate tới instance §PaymentService§ final.

Nhưng CGLIB cần tạo subclass:

~~~text
PaymentService$$SpringCGLIB$$0 extends PaymentService
~~~

Nếu §PaymentService§ là final, điều đó không thể thực hiện. CGLIB không thể subclass một class final.

Do đó, nếu project bật class-based proxy và gặp lỗi liên quan final class, giải pháp có thể là:

- Dùng JDK proxy qua interface.
- Bỏ §final§ nếu thiết kế cho phép và proxy subclass là chủ đích.
- Chuyển chức năng cần intercept sang một bean khác có thể proxy.
- Chọn một cơ chế interception khác phù hợp.

Không nên xóa §final§ hàng loạt mà không hiểu vì sao class được thiết kế immutable hoặc final.

## 11. Giới hạn của CGLIB: final, private và self-invocation

CGLIB proxy dựa trên subclass và method overriding. Vì vậy:

- Final class không thể được subclass.
- Final method không thể override để interception.
- Private method không thể override theo cơ chế này.
- Static method không phải instance method được proxy override.
- Self-invocation thường bypass proxy.

Ví dụ:

~~~java
@Service
public class BillingService {

    public void createInvoice() {
        calculateTax();
    }

    @Transactional
    public void calculateTax() {
        // ...
    }
}
~~~

Khi §createInvoice()§ gọi §calculateTax()§ bằng §this.calculateTax()§, lời gọi nội bộ không đi qua proxy bên ngoài. Vì vậy transaction advice đặt trên method nội bộ có thể không được áp dụng như mong đợi trong proxy mode.

Một cách thiết kế thường tốt hơn là tách phần cần interception sang bean khác:

~~~java
@Service
public class TaxService {

    @Transactional
    public void calculateTax() {
        // ...
    }
}
~~~

~~~java
@Service
public class BillingService {

    private final TaxService taxService;

    public BillingService(TaxService taxService) {
        this.taxService = taxService;
    }

    public void createInvoice() {
        taxService.calculateTax();
    }
}
~~~

Giờ lời gọi đi qua bean proxy §TaxService§ được inject từ container.

Đây không phải lỗi §BeanNotOfRequiredTypeException§ trực tiếp, nhưng thường xuất hiện cùng lúc khi người phát triển thay proxy strategy mà chưa hiểu giới hạn của proxy.

## 12. Cấu hình proxy-target-class trong Spring Boot

Có thể điều chỉnh proxy strategy bằng property:

~~~properties
spring.aop.proxy-target-class=true
~~~

Giá trị §true§ yêu cầu class-based proxy trong phạm vi auto-configuration AOP của Spring Boot khi cơ chế đó áp dụng.

Giá trị §false§ cho phép sử dụng JDK dynamic proxy khi bean có interface phù hợp:

~~~properties
spring.aop.proxy-target-class=false
~~~

Spring Framework cũng có cấu hình annotation:

~~~java
@EnableAspectJAutoProxy(proxyTargetClass = true)
~~~

Với transaction management có cấu hình riêng:

~~~java
@EnableTransactionManagement(proxyTargetClass = true)
~~~

Cần xem xét cấu hình thực tế vì nhiều cơ chế AOP auto-proxy trong Spring có thể được hợp nhất vào một auto-proxy creator chung. Một cấu hình class-based proxy ở nơi khác có thể ảnh hưởng cách proxy được tạo cho nhiều advisor.

### 12.1. Spring Boot default có thể là class-based proxy

Trong nhiều cấu hình Spring Boot dùng AOP auto-configuration thông thường, §spring.aop.proxy-target-class§ mặc định là §true§. Nhưng không nên suy luận từ default đó rằng **mọi bean của ứng dụng chắc chắn là CGLIB proxy**:

- Bean có thể không cần proxy.
- Có thể có cấu hình AOP/transaction riêng.
- Có thể dùng framework hoặc post-processor khác.
- Một số bean dùng proxy strategy riêng.
- Cấu hình có thể bị override qua profile, environment hoặc command line.

Hãy kiểm tra effective configuration và runtime class thực tế.

### 12.2. Bật CGLIB có phải cách sửa tốt nhất?

Nếu lỗi chỉ xảy ra vì consumer inject implementation trong khi bean là JDK proxy, bật class-based proxy có thể khiến concrete injection hoạt động trong trường hợp class có thể subclass.

Nhưng đây không phải giải pháp phổ quát:

- Target class final sẽ không thể proxy theo cách đó.
- Final method không được intercept.
- Có thể làm thay đổi kiểu proxy của các bean khác.
- Có thể tạo thêm ràng buộc vào implementation class.
- Không sửa lỗi khi bean name trỏ nhầm bean.
- Không sửa sai return type hoặc một dependency không liên quan.
- Không sửa logic gọi self-invocation.

**Ưu tiên sửa contract injection cho phù hợp với interface mà proxy expose.** Chỉ chọn CGLIB khi có lý do thiết kế rõ ràng để expose concrete class.

## 13. Cách xác định proxy runtime trong code

Spring AOP cung cấp utility để nhận biết proxy.

~~~java
import org.springframework.aop.support.AopUtils;

Object bean = applicationContext.getBean("paymentService");

Class<?> runtimeType = bean.getClass();

System.out.println("Runtime type: " + runtimeType.getName());
System.out.println("Is AOP proxy: " + AopUtils.isAopProxy(bean));
System.out.println("Is JDK proxy: " + AopUtils.isJdkDynamicProxy(bean));
System.out.println("Is CGLIB proxy: " + AopUtils.isCglibProxy(bean));
System.out.println("Target class: " +
        AopUtils.getTargetClass(bean).getName());
~~~

Các phương thức có ý nghĩa:

| API | Trả lời câu hỏi |
|---|---|
| §bean.getClass()§ | Class runtime của object caller đang giữ là gì? |
| §AopUtils.isAopProxy(bean)§ | Object có phải Spring AOP proxy không? |
| §AopUtils.isJdkDynamicProxy(bean)§ | Có phải JDK dynamic proxy không? |
| §AopUtils.isCglibProxy(bean)§ | Có phải CGLIB proxy không? |
| §AopUtils.getTargetClass(bean)§ | Target class mà Spring có thể xác định là gì? |

§getTargetClass()§ giúp chẩn đoán class phía sau proxy, nhưng **không có nghĩa object trả về đã trở thành instance của target class**.

Ví dụ:

~~~java
Object bean = context.getBean("paymentService");

System.out.println(bean instanceof PaymentService);
// true nếu proxy expose interface

System.out.println(bean instanceof PaymentServiceImpl);
// false nếu đây là JDK proxy chỉ expose interface
~~~

Có thể §AopUtils.getTargetClass(bean)§ trả về §PaymentServiceImpl.class§ trong khi §bean.getClass()§ vẫn là §jdk.proxy2.$Proxy...§.

Đó là hai câu trả lời cho hai câu hỏi khác nhau: target class là gì và proxy object có kiểu runtime nào.

## 14. Kiểm tra interface mà proxy expose

Nếu cần chẩn đoán JDK proxy, có thể xem các interface của runtime class:

~~~java
Object bean = context.getBean("paymentService");

for (Class<?> type : bean.getClass().getInterfaces()) {
    System.out.println(type.getName());
}
~~~

Với JDK dynamic proxy, danh sách interface thường là contract mà proxy expose.

Có thể kiểm tra trực tiếp:

~~~java
boolean supportsContract =
        PaymentOperations.class.isInstance(bean);
~~~

Đây là phép kiểm tra assignability phù hợp hơn việc so sánh tên class runtime với tên implementation.

Không nên coi danh sách interface runtime của CGLIB proxy là toàn bộ contract; proxy subclass có thể kế thừa interface từ target class và các interface khác.

## 15. Kiểm tra bean type trước khi khởi tạo và sau khi khởi tạo

Spring BeanFactory có một số API hữu ích:

~~~java
boolean matches =
        beanFactory.isTypeMatch(
                "paymentService",
                PaymentOperations.class
        );
~~~

~~~java
Class<?> predictedType =
        beanFactory.getType("paymentService");
~~~

~~~java
String[] names =
        beanFactory.getBeanNamesForType(
                PaymentOperations.class
        );
~~~

Những API này giúp xem Spring có dự đoán hoặc nhận diện bean theo type nào.

Cần lưu ý:

- §getType()§ có thể trả về kiểu dự đoán từ bean definition/factory method.
- Kiểu dự đoán trước khi tạo bean có thể khác class runtime sau khi post-processor bọc proxy.
- §isTypeMatch()§ phụ thuộc metadata và khả năng xác định kiểu của factory/proxy.
- Không phải mọi FactoryBean hoặc bean lazy đều có thể cung cấp đầy đủ kiểu runtime trước khi tạo.

Vì vậy, khi điều tra exception, hãy so sánh **metadata bean** và **object thực tế sau khi lấy được**. Đừng chỉ dựa vào một API type prediction.

## 16. Một cách tái hiện exception bằng ProxyFactory

Có thể tái hiện sự khác nhau giữa JDK proxy và target implementation bằng Spring AOP §ProxyFactory§.

Interface:

~~~java
public interface GreetingOperations {
    String greet();
}
~~~

Implementation:

~~~java
public class GreetingService implements GreetingOperations {

    @Override
    public String greet() {
        return "Hello";
    }
}
~~~

Tạo JDK proxy:

~~~java
ProxyFactory factory = new ProxyFactory();
factory.setTarget(new GreetingService());
factory.setInterfaces(GreetingOperations.class);
factory.setProxyTargetClass(false);

Object proxy = factory.getProxy();
~~~

Kiểm tra:

~~~java
assertTrue(proxy instanceof GreetingOperations);
assertFalse(proxy instanceof GreetingService);
~~~

Sau đó đăng ký proxy vào bean factory:

~~~java
DefaultListableBeanFactory beanFactory =
        new DefaultListableBeanFactory();

beanFactory.registerSingleton("greetingService", proxy);

GreetingOperations operations =
        beanFactory.getBean(
                "greetingService",
                GreetingOperations.class
        );
~~~

Lookup theo interface phù hợp với kiểu proxy. Lookup theo concrete class:

~~~java
GreetingService implementation =
        beanFactory.getBean(
                "greetingService",
                GreetingService.class
        );
~~~

có thể ném §BeanNotOfRequiredTypeException§.

Đây là cách minh họa trực tiếp contract của §getBean(name, requiredType)§. Khi chuyển thành test thực tế, cần thêm import cho §ProxyFactory§, §DefaultListableBeanFactory§ và các assertion của JUnit.

### 16.1. Tái hiện CGLIB proxy

Đổi:

~~~java
factory.setProxyTargetClass(true);
~~~

Nếu target class không final và có thể proxy theo cơ chế subclass, object tạo ra có thể gán được cho §GreetingService§:

~~~java
assertTrue(proxy instanceof GreetingService);
assertTrue(proxy instanceof GreetingOperations);
~~~

Đây là khác biệt quan trọng nhất cần quan sát khi điều tra lỗi kiểu.

## 17. Kiểm thử proxy trong Spring context

Một test context-level có thể xác nhận bean được bọc và contract interface vẫn sử dụng được.

~~~java
@SpringBootTest
class PaymentProxyTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    PaymentOperations paymentOperations;

    @Test
    void beanExposesPaymentContract() {
        Object bean = context.getBean("paymentService");

        assertTrue(AopUtils.isAopProxy(bean));
        assertTrue(bean instanceof PaymentOperations);
    }
}
~~~

Ví dụ giả định:

- Có bean tên §paymentService§.
- Bean có interface §PaymentOperations§.
- Có một aspect hoặc transaction advisor thực sự khiến bean được proxy.
- Test application context được cấu hình phù hợp.

Không nên assert §isAopProxy()§ nếu test không tạo bất kỳ advisor nào; khi đó bean có thể không bị proxy và test sẽ thất bại đúng như cấu hình.

### Test không nên khóa cứng tên class proxy

Không nên viết:

~~~java
assertEquals(
        "jdk.proxy2.$Proxy42",
        bean.getClass().getName()
);
~~~

Tên proxy phụ thuộc JVM, thứ tự tạo proxy, runtime và framework. Thay vào đó dùng:

~~~java
assertTrue(AopUtils.isJdkDynamicProxy(bean));
~~~

hoặc:

~~~java
assertTrue(AopUtils.isCglibProxy(bean));
~~~

Nếu mục tiêu test là contract của consumer, chỉ cần inject và gọi interface.

## 18. Phân biệt lỗi proxy và lỗi chọn nhầm bean

Không phải mọi §BeanNotOfRequiredTypeException§ đều do JDK proxy.

Ví dụ có hai bean:

~~~java
@Bean
Object paymentService() {
    return new String("not a payment service");
}
~~~

Nếu bean name §paymentService§ được dùng để lấy §PaymentOperations§, object thực tế là §String§. Đây là sai kiểu do cấu hình bean, không phải proxy.

Những nguyên nhân khác:

- Bean name trùng hoặc alias trỏ tới bean không như mong muốn.
- Một §@Bean§ factory method trả về implementation khác.
- Cấu hình profile tạo bean khác nhau giữa local và production.
- Một §FactoryBean§ cung cấp product có kiểu khác dự kiến.
- Một bean test thay thế bean production bằng mock/fake sai contract.
- Bean definition bị override bởi cấu hình khác.
- Caller yêu cầu concrete class nhưng bean được expose qua proxy.

| Dấu hiệu | Hướng điều tra |
|---|---|
| Actual type là §jdk.proxy...§ | Kiểm tra JDK proxy và interface expose |
| Actual type có §$$SpringCGLIB$$§ | Kiểm tra class-based proxy và target class |
| Actual type là class không liên quan | Kiểm tra bean name, alias, factory method và profile |
| §getType()§ trả interface nhưng caller yêu cầu implementation | Kiểm tra kiểu khai báo bean và proxy strategy |
| Chỉ lỗi ở một profile | So sánh bean definitions và configuration source theo profile |
| Chỉ lỗi trong test | Kiểm tra mock bean, §@TestConfiguration§, context cache |

**Không đổi proxy strategy trước khi xác nhận actual type.** Nếu bean thực tế là object hoàn toàn sai, bật CGLIB sẽ không giải quyết nguyên nhân.

## 19. FactoryBean và object được expose

Spring có interface §FactoryBean<T>§ cho phép một factory tạo ra object được container expose như bean product.

Ví dụ khái quát:

~~~java
public class PaymentClientFactory
        implements FactoryBean<PaymentOperations> {

    @Override
    public PaymentOperations getObject() {
        return createClient();
    }

    @Override
    public Class<?> getObjectType() {
        return PaymentOperations.class;
    }
}
~~~

Khi lấy bean bằng tên thông thường, caller thường nhận **product** của FactoryBean. Muốn lấy chính factory, có quy ước prefix §&§:

~~~java
Object product = context.getBean("paymentClient");
Object factory = context.getBean("&paymentClient");
~~~

Nếu caller nhầm product với factory hoặc ngược lại, kiểu yêu cầu có thể không tương thích.

Trong chẩn đoán, hãy xác định tên bean có phải FactoryBean không và caller đang yêu cầu object nào. Không nên kết luận mọi actual type khác target class đều là AOP proxy.

## 20. Scoped proxy cũng có kiểu runtime riêng

Một số bean có scope ngắn hơn singleton, chẳng hạn request scope trong ứng dụng web. Nếu singleton cần tham chiếu đến bean request-scoped, Spring có thể dùng scoped proxy.

Ví dụ:

~~~java
@Component
@RequestScope
public class RequestContextData {

    public String requestId() {
        return "current-request";
    }
}
~~~

Một singleton có thể inject §RequestContextData§ thông qua scoped proxy. Proxy tồn tại lâu hơn object target theo request; mỗi request có thể resolve target tương ứng.

Cách proxy được tạo có thể là interface-based hoặc class-based tùy cấu hình và kiểu bean.

Điểm cần nhớ:

- Proxy không phải object target của một request cụ thể.
- Không nên lưu target request-scoped ra ngoài vòng đời request.
- Không cast proxy thành một class nội bộ mà proxy không expose.
- Khi test, cần có web request scope đang hoạt động nếu muốn gọi method truy cập target.

Scoped proxy là một lý do khác khiến §getClass()§ khác với class mà người viết bean mong đợi.
