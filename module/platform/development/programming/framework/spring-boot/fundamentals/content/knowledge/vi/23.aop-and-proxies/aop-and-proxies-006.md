# Self-invocation và trường hợp gọi nội bộ không qua proxy

Trong Spring Boot, nhiều chức năng như `@Transactional`, `@Async`, `@Cacheable` và các advice AOP được triển khai bằng **proxy**. Vì vậy, annotation có xuất hiện trên phương thức chưa đủ để đảm bảo advice luôn chạy: lời gọi phải đi qua đúng đối tượng proxy được Spring quản lý.

Một lỗi rất dễ gặp là **self-invocation**: một phương thức của bean gọi một phương thức khác trên chính đối tượng đó bằng `this.method()` hoặc một lời gọi tương đương không ghi `this`. Lời gọi nội bộ này thường **không đi qua proxy**, nên advice dành riêng cho phương thức được gọi không được kích hoạt.

Bài học này giải thích cơ chế, dấu hiệu nhận biết, hậu quả và những cách tổ chức lại code để AOP hoạt động theo mong đợi.

## 1. AOP proxy can thiệp vào lời gọi như thế nào?

Aspect-Oriented Programming (AOP) cho phép tách các mối quan tâm cắt ngang (*cross-cutting concerns*) khỏi code nghiệp vụ, chẳng hạn:

- Bắt đầu, commit hoặc rollback transaction.
- Chạy tác vụ qua một executor thay vì trên luồng gọi.
- Tra cứu và cập nhật cache.
- Ghi log, đo thời gian thực thi, kiểm tra quyền truy cập.
- Áp dụng các advice do ứng dụng tự khai báo.

Trong **proxy-based Spring AOP**, Spring tạo một đối tượng trung gian (proxy) để đứng trước đối tượng thực thi nghiệp vụ (target). Các thành phần khác lấy bean từ ApplicationContext thường nhận tham chiếu đến proxy. Khi một phương thức phù hợp được gọi qua proxy, proxy có cơ hội thực thi advice trước, sau hoặc xung quanh phương thức của target.

~~~text
Controller / bean khác
         |
         v
  Spring AOP proxy
         |
         +--> Advice: mở transaction / cache / log ...
         |
         v
    Target object
         |
         v
  Phương thức nghiệp vụ
         |
         v
  Advice hoàn tất / commit / xử lý lỗi
~~~

Nếu phương thức không khớp pointcut hoặc điều kiện của advice, proxy có thể chuyển tiếp lời gọi mà không áp dụng advice đó. Nếu lời gọi không đi qua proxy ngay từ đầu, advice trên phương thức đích không có cơ hội xử lý.

## 2. Self-invocation là gì?

Giả sử một Spring bean có hai phương thức:

~~~java
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {

    public void processInvoice() {
        validateInvoice();

        // Logic xử lý hóa đơn ...
    }

    public void validateInvoice() {
        // Kiểm tra dữ liệu hóa đơn ...
    }
}
~~~

Trong `processInvoice()`, lời gọi `validateInvoice()` tương đương với `this.validateInvoice()`. `this` lúc này trỏ tới **target object** đang thực thi phương thức, không phải một lần truy cập lại bean qua container.

Nếu `validateInvoice()` có advice AOP, lời gọi nội bộ không đi qua điểm chặn của proxy theo cơ chế proxy-based AOP thông thường.

So sánh hai đường gọi:

~~~text
(1) Gọi từ một bean khác

OrderController
      |
      v
InvoiceService proxy
      |
      v
Advice cho validateInvoice()
      |
      v
InvoiceService target.validateInvoice()


(2) Gọi nội bộ trong cùng bean

OrderController
      |
      v
InvoiceService proxy.processInvoice()
      |
      v
InvoiceService target.processInvoice()
      |
      +--> this.validateInvoice()
                  |
                  v
        Target.validateInvoice()
        KHÔNG đi qua proxy lần nữa
~~~

Đường (2) có thể được áp dụng advice của `processInvoice()` nếu phương thức đó khớp pointcut. Nhưng **advice riêng của `validateInvoice()` không được chạy chỉ vì target tự gọi phương thức này**.

Đây là khác biệt giữa *lời gọi trên bean proxy* và *lời gọi trên chính đối tượng đã được proxy ủy quyền thực thi*.

## 3. Ví dụ điển hình với @Transactional

`@Transactional` là ví dụ phổ biến nhất của vấn đề self-invocation.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    public void placeOrder() {
        // Một số kiểm tra và tính toán...
        saveOrder();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveOrder() {
        // Ghi đơn hàng vào database...
    }
}
~~~

Một bean khác gọi:

~~~java
orderService.placeOrder();
~~~

Lời gọi có đi qua proxy của `OrderService` nếu Spring quản lý bean. Tuy nhiên `placeOrder()` không được đánh dấu transaction, rồi target gọi trực tiếp `saveOrder()`. Do đó, interceptor giao dịch của `saveOrder()` không được chạy trong lời gọi nội bộ này.

Kết quả là annotation `@Transactional(propagation = REQUIRES_NEW)` **không tự tạo transaction mới** ở lần gọi trên. Nếu thao tác ghi có transaction, nó có thể đến từ tầng khác hoặc từ hành vi riêng của thư viện truy cập dữ liệu, không phải từ advice của `saveOrder()`.

Trái lại, nếu một bean khác nhận `OrderService` từ Spring rồi gọi trực tiếp:

~~~java
orderService.saveOrder();
~~~

thì lời gọi có thể đi qua transactional proxy, và advice của `saveOrder()` được thực thi, với điều kiện transaction management đã được cấu hình phù hợp.

### Nếu phương thức ngoài cũng có @Transactional thì sao?

Xét phiên bản khác:

~~~java
@Service
public class OrderService {

    @Transactional
    public void placeOrder() {
        saveOrder();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveOrder() {
        // Ghi dữ liệu...
    }
}
~~~

Khi một bean khác gọi `placeOrder()` qua proxy, **transaction của `placeOrder()` được áp dụng**. Lời gọi nội bộ tới `saveOrder()` vẫn bỏ qua advice của phương thức trong.

Điều này có nghĩa `saveOrder()` có thể chạy trong transaction đang có từ `placeOrder()`, nhưng thuộc tính riêng `REQUIRES_NEW` của `saveOrder()` **không có hiệu lực tại ranh giới lời gọi nội bộ**. Nó không tự tạm ngưng transaction ngoài để tạo transaction mới.

Tương tự, những thuộc tính như `readOnly`, `timeout`, `isolation` hoặc quy tắc rollback trên phương thức trong không được áp dụng như một giao dịch độc lập nếu không đi qua interceptor tương ứng.

Đây là lý do không thể kiểm tra chỉ bằng câu hỏi “hiện tại có transaction hay không?”. Cần phân biệt **transaction đã tồn tại từ lời gọi ngoài** với **advice giao dịch của phương thức trong có thực sự được gọi hay không**.

## 4. Ảnh hưởng tới @Async và @Cacheable

Self-invocation không chỉ liên quan transaction. Các cơ chế proxy-based khác cũng chịu cùng nguyên tắc.

### @Async: lời gọi nội bộ vẫn chạy đồng bộ

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    public void requestReport() {
        generateReport();
    }

    @Async
    public void generateReport() {
        // Xử lý report mất nhiều thời gian...
    }
}
~~~

Giả sử ứng dụng đã bật async execution, ví dụ bằng `@EnableAsync`, và một bean khác gọi `reportService.requestReport()`.

Lời gọi nội bộ `generateReport()` bỏ qua async proxy, nên phần xử lý được thực thi trên luồng hiện tại thay vì được chuyển tới executor qua advice `@Async`. Phương thức `requestReport()` vì vậy có thể bị chặn cho tới khi `generateReport()` hoàn tất.

Nếu một bean khác gọi `reportService.generateReport()` qua proxy, advice `@Async` có cơ hội gửi tác vụ tới executor đã cấu hình.

### @Cacheable: bỏ qua tra cứu và cập nhật cache

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    public Product loadForCheckout(String id) {
        return findProduct(id);
    }

    @Cacheable(cacheNames = "products", key = "#id")
    public Product findProduct(String id) {
        // Truy vấn dữ liệu...
        return loadProductFromDatabase(id);
    }

    private Product loadProductFromDatabase(String id) {
        // Ví dụ minh họa.
        return new Product(id);
    }
}
~~~

Giả sử caching đã được bật, ví dụ bằng `@EnableCaching`, và cache manager phù hợp đã có mặt.

Khi `loadForCheckout()` gọi nội bộ `findProduct()`, lời gọi không đi qua caching advice. Điều đó có nghĩa:

- Không thực hiện bước tra cứu cache tại interceptor của `findProduct()`.
- Không sử dụng kết quả cache để bỏ qua truy vấn.
- Không ghi kết quả vào cache qua interceptor của lời gọi này.

Nếu một bean khác gọi `productService.findProduct(id)` qua proxy, cơ chế `@Cacheable` có thể hoạt động theo cấu hình cache hiện tại.

Các annotation như `@CachePut`, `@CacheEvict` hay advice do `@Aspect` tự viết cũng cần được xét tương tự khi chúng chạy theo cơ chế proxy.

## 5. JDK dynamic proxy và CGLIB có làm self-invocation khác đi không?

Spring AOP thường sử dụng hai cách tạo proxy:

| Loại | Đặc điểm | Phạm vi lưu ý |
|---|---|---|
| JDK dynamic proxy | Proxy triển khai các interface được target cung cấp | Lời gọi thường đi qua các phương thức được khai báo trên interface |
| Class-based proxy (CGLIB) | Proxy dựa trên subclass của lớp target | Có thể proxy các phương thức phù hợp trên lớp, nhưng có giới hạn với `final`, `private` và khả năng override |

Dù dùng JDK dynamic proxy hay CGLIB, **self-invocation trong target vẫn bỏ qua advice của lời gọi tới chính nó** theo mô hình Spring AOP proxy.

Chuyển từ JDK proxy sang CGLIB không phải giải pháp chữa self-invocation. Lựa chọn proxy type chủ yếu ảnh hưởng tới kiểu proxy, khả năng truy cập bean qua interface hoặc class và những phương thức có thể được advised.

Ví dụ, cấu hình:

~~~yaml
spring:
  aop:
    proxy-target-class: true
~~~

có thể yêu cầu class-based proxy trong môi trường Spring Boot phù hợp. Tuy nhiên, cấu hình này **không biến `this.method()` thành lời gọi qua proxy**.

### Hạn chế của phương thức final, private và non-public

Ngoài self-invocation, Spring AOP còn có giới hạn về khả năng intercept:

- Method `private` không thể bị override bởi class-based proxy, nên không thể được advised theo cách này.
- Method `final` không thể bị override; class-based proxy không thể áp dụng advice lên method đó.
- Với interface-based JDK proxy, lời gọi được intercept qua các method do proxy interface công bố.
- Chính sách của từng annotation có thể đặt thêm yêu cầu về visibility, ví dụ phạm vi method mà transaction advice hỗ trợ.

Do đó, khi debug một annotation không hoạt động, cần kiểm tra **cả ranh giới proxy lẫn tính chất method**. Nhưng kể cả một method `public`, không `final` và có annotation hợp lệ vẫn có thể bỏ qua advice nếu được gọi nội bộ.

## 6. Dấu hiệu nhận biết lỗi self-invocation

Một số dấu hiệu thường gặp:

1. Gọi trực tiếp phương thức annotated từ controller thì tính năng hoạt động, nhưng gọi qua một phương thức khác trong cùng service thì không.
2. `@Transactional(propagation = REQUIRES_NEW)` không tạo transaction độc lập như dự kiến.
3. `@Async` chạy trên luồng request thay vì executor khi được gọi từ một phương thức cùng lớp.
4. `@Cacheable` không giảm số lần truy vấn khi gọi qua một helper method trong cùng bean.
5. Logging aspect hoặc metrics advice không ghi nhận lần gọi vào phương thức trong.
6. Đổi sang CGLIB mà hành vi vẫn không khác.

Có thể mô phỏng lời gọi nội bộ và bên ngoài bằng sơ đồ:

~~~text
service.outer() -> this.inner()      : bỏ qua advice cho inner()
caller         -> service.inner()   : đi qua proxy, advice có cơ hội chạy
~~~

Điều quyết định không phải phương thức có tên giống nhau, mà là **đối tượng nhận lời gọi tại thời điểm gọi**.

## 7. Giải pháp ưu tiên: tách chức năng được advised sang bean khác

Cách rõ ràng và thường dễ bảo trì nhất là tách phương thức cần advice sang một Spring bean riêng. Bean phía ngoài inject bean phía trong; lời gọi qua dependency này đi qua proxy của bean được inject.

Ví dụ với transaction:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final OrderWriter orderWriter;

    public CheckoutService(OrderWriter orderWriter) {
        this.orderWriter = orderWriter;
    }

    public void checkout() {
        // Kiểm tra đơn hàng...
        orderWriter.saveOrder();
    }
}
~~~

Bean phụ trách ghi dữ liệu:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveOrder() {
        // Thao tác ghi dữ liệu...
    }
}
~~~

Luồng thực thi:

~~~text
Controller
   |
   v
CheckoutService proxy / target
   |
   v
orderWriter.saveOrder()
   |
   v
OrderWriter proxy
   |
   v
Transaction advice (REQUIRES_NEW)
   |
   v
OrderWriter target.saveOrder()
~~~

Cách này có nhiều lợi ích:

- Ranh giới transaction rõ ràng qua một dependency giữa các service.
- Không phụ thuộc vào việc bean tự tìm lại proxy của chính mình.
- Có thể kiểm thử nghiệp vụ của `CheckoutService` độc lập với `OrderWriter`.
- Dễ phân định trách nhiệm giữa orchestration và thao tác ghi dữ liệu.

Tương tự, với `@Async` có thể tách `ReportGenerator` thành bean riêng; với `@Cacheable` có thể tạo một `ProductLookup` bean được các service khác sử dụng.

### Chú ý ranh giới nghiệp vụ

Không nhất thiết tách mọi phương thức nhỏ thành một bean. Chỉ nên tách khi phương thức đó cần một **ranh giới advice riêng** hoặc có trách nhiệm độc lập. Nếu hai phương thức thực sự cần cùng transaction, có thể đặt annotation ở phương thức ngoài và giữ lời gọi nội bộ bình thường.

Ví dụ:

~~~java
@Transactional
public void checkout() {
    validate();
    reserveStock();
    saveOrder();
}
~~~

Nếu cả ba bước đều nên chạy trong cùng transaction, việc đặt `@Transactional` ở điểm vào `checkout()` có thể phù hợp hơn việc annotation từng helper method.

## 8. Giải pháp: dùng TransactionTemplate khi cần ranh giới transaction tường minh

Nếu không muốn tách thêm một bean nhưng cần kiểm soát transaction của một đoạn code, có thể sử dụng programmatic transaction management với `TransactionTemplate`.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class OrderService {

    private final TransactionTemplate requiresNewTransaction;

    public OrderService(PlatformTransactionManager transactionManager) {
        this.requiresNewTransaction =
                new TransactionTemplate(transactionManager);

        this.requiresNewTransaction.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );
    }

    public void placeOrder() {
        // Logic trước giao dịch...

        requiresNewTransaction.executeWithoutResult(status -> {
            // Ghi dữ liệu cần chạy trong transaction mới...
        });
    }
}
~~~

Trong cách này, code gọi trực tiếp `TransactionTemplate`; việc mở transaction không phụ thuộc phương thức được gọi qua proxy hay không.

Ưu điểm là ranh giới giao dịch nhìn thấy rõ ngay tại nơi sử dụng. Đổi lại, code nghiệp vụ gắn với API quản lý transaction của Spring nhiều hơn. Đây là lựa chọn phù hợp khi transaction đặc biệt cần thiết trong một phạm vi nhỏ và không muốn tạo thêm service.

Giải pháp này chỉ xử lý nhu cầu về transaction. Nó không tự thay thế cơ chế `@Async` hoặc `@Cacheable`.

## 9. Tự gọi qua proxy của chính bean: có thể làm nhưng cần cân nhắc

Về kỹ thuật, ứng dụng có thể tổ chức để lời gọi đi qua proxy của chính bean thay vì gọi `this`. Ví dụ, một biến thể sử dụng Spring AOP `AopContext`:

~~~java
import org.springframework.aop.framework.AopContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {

    public void updateAccount() {
        AccountService proxy =
                (AccountService) AopContext.currentProxy();

        proxy.saveAuditRecord();
    }

    @Transactional
    public void saveAuditRecord() {
        // Ghi audit...
    }
}
~~~

Để `AopContext.currentProxy()` hoạt động, proxy phải được cấu hình `exposeProxy = true` và lời gọi hiện tại phải đang đi qua một AOP proxy trong cùng luồng thực thi. Ví dụ, trong cấu hình AspectJ auto-proxy của Spring:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(exposeProxy = true)
public class AopConfiguration {
}
~~~

Cách này có những bất lợi:

- Business code phụ thuộc trực tiếp vào Spring AOP.
- Yêu cầu cấu hình proxy được expose.
- `AopContext.currentProxy()` có thể thất bại nếu không có proxy hiện hành trong cùng thread.
- Khi kiểu proxy là JDK interface proxy, cast sang concrete class có thể không hợp lệ.
- Logic khó đọc và kiểm thử hơn so với ranh giới giữa hai bean.

Vì vậy, đây thường là lựa chọn cuối khi việc tái cấu trúc bean không phù hợp. Đừng dùng nó như cách mặc định để làm `@Transactional` hoạt động.

Một số giải pháp tự inject bean thông qua `ObjectProvider` hoặc lazy proxy cũng có thể tạo lời gọi qua proxy, nhưng làm xuất hiện quan hệ tự phụ thuộc và đòi hỏi hiểu rõ vòng đời bean. Tách trách nhiệm sang bean khác thường minh bạch hơn.

## 10. AspectJ weaving khác proxy-based AOP

Spring hỗ trợ cơ chế AOP dựa trên proxy, trong khi AspectJ có khả năng **weaving** advice vào bytecode bằng cách compile-time weaving hoặc load-time weaving khi được cấu hình đầy đủ.

Với weaving, advice không chỉ dựa vào việc lời gọi phải đi qua một proxy bên ngoài. Vì vậy, AspectJ có thể xử lý một số trường hợp self-invocation mà proxy-based Spring AOP không xử lý được.

Ví dụ, Spring transaction management có thể được cấu hình dùng AspectJ mode khi ứng dụng có các dependency và weaving infrastructure cần thiết:

~~~java
import org.springframework.context.annotation.AdviceMode;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration(proxyBeanMethods = false)
@EnableTransactionManagement(mode = AdviceMode.ASPECTJ)
public class TransactionConfiguration {
}
~~~

**Chỉ khai báo mode AspectJ chưa đủ.** Ứng dụng cần thư viện hỗ trợ và cơ chế weaving tương ứng, chẳng hạn cấu hình AspectJ load-time weaving theo môi trường chạy. Nếu thiếu các thành phần đó, không nên kỳ vọng self-invocation được intercept.

Đối với đa số ứng dụng Spring Boot thông thường, việc sắp xếp lại ranh giới bean đơn giản và ít rủi ro vận hành hơn việc chuyển toàn bộ cơ chế interception sang AspectJ weaving.

| Cơ chế | Cách advice được áp dụng | Self-invocation |
|---|---|---|
| Spring AOP proxy | Lời gọi vào bean đi qua proxy | Bỏ qua advice của phương thức được gọi nội bộ |
| AspectJ weaving | Advice được dệt vào các join point phù hợp trong bytecode | Có thể xử lý lời gọi nội bộ tùy pointcut và weaving configuration |

Hai cơ chế không thể hoán đổi chỉ bằng việc bật CGLIB. CGLIB vẫn là một dạng **proxy**, không phải AspectJ weaving.

## 11. Kiểm chứng bằng transaction state

Một cách minh họa là sử dụng `TransactionSynchronizationManager` để kiểm tra có transaction thực tế trong luồng đang chạy hay không.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class DiagnosticService {

    public void outer() {
        System.out.println("outer before: " + active());
        inner();
        System.out.println("outer after: " + active());
    }

    @Transactional
    public void inner() {
        System.out.println("inner: " + active());
    }

    private boolean active() {
        return TransactionSynchronizationManager
                .isActualTransactionActive();
    }
}
~~~

Giả sử có `PlatformTransactionManager` phù hợp, đã bật transaction management và code gọi bean từ context trong một luồng không có transaction sẵn:

~~~java
diagnosticService.outer();
diagnosticService.inner();
~~~

Với proxy-based transaction management, kết quả dự kiến về mặt ý nghĩa là:

~~~text
outer before: false
inner: false
outer after: false
inner: true
~~~

Lời gọi `inner()` trong `outer()` không qua proxy nên không tạo transaction mới. Lời gọi trực tiếp `diagnosticService.inner()` ở ngoài đi qua proxy và được interceptor giao dịch xử lý.

Đây là ví dụ chẩn đoán. Trong ứng dụng thực tế, một transaction có thể đã tồn tại từ caller khác, hoặc một thành phần truy cập dữ liệu có thể quản lý transaction của nó. Vì vậy, khi kiểm thử `REQUIRES_NEW`, hãy xác minh đúng ranh giới transaction và hành vi commit/rollback thay vì chỉ xem một giá trị boolean.

### Kiểm tra @Async bằng tên luồng

Với `@Async`, có thể ghi tên thread:

~~~java
@Async
public void generateReport() {
    System.out.println(Thread.currentThread().getName());
}
~~~

So sánh hai đường gọi:

~~~java
reportService.requestReport(); // Nội bộ gọi generateReport()
reportService.generateReport(); // Gọi từ bên ngoài qua proxy
~~~

Nếu async execution được bật và cấu hình đúng, lời gọi nội bộ có thể chạy ngay trên luồng của caller, còn lời gọi qua proxy được thực thi bởi executor. Kết quả phụ thuộc executor thực tế; mục đích là quan sát ranh giới gọi, không khẳng định mọi ứng dụng đều có tên thread giống nhau.

## 12. Những lỗi tư duy thường gặp

### Có annotation nghĩa là advice chắc chắn chạy

Không đúng trong proxy-based AOP. Advice phụ thuộc pointcut, phương thức phù hợp và lời gọi đi qua proxy. Annotation chỉ mô tả điều kiện và cấu hình cho một cơ chế xử lý.

### Gọi method public trong cùng lớp sẽ đi qua proxy

Không đúng. Khả năng truy cập `public` không thay đổi đối tượng nhận lời gọi. `this.publicMethod()` vẫn là lời gọi nội bộ trên target.

### Chuyển sang CGLIB sẽ sửa self-invocation

Không đúng. CGLIB là class-based proxy, vẫn có ranh giới interception tương tự. Vấn đề không nằm ở việc proxy dùng interface hay subclass mà nằm ở đường gọi đi qua proxy hay không.

### @Transactional trong phương thức nội bộ luôn không có transaction

Cách nói này thiếu chính xác. Nếu phương thức ngoài đã tham gia transaction, phương thức trong có thể chạy **bên trong transaction đang tồn tại**. Điều bị bỏ qua là advice riêng tại phương thức trong, ví dụ `REQUIRES_NEW`, một timeout hay quy tắc rollback khác.

### Private method có @Transactional sẽ được advice khi gọi qua this

Không đúng. Trong cơ chế proxy, private method không phải một điểm chặn phù hợp cho class-based proxy. Việc lời gọi nằm cùng bean càng khiến nó không đi qua proxy.

### Gọi phương thức khi đang khởi tạo bean sẽ nhận đầy đủ advice

Trong constructor hoặc một số callback sớm của vòng đời bean, AOP proxy có thể chưa ở trạng thái sẵn sàng cho kiểu lời gọi mong muốn. Không nên coi lời gọi nội bộ trong quá trình construction/init là điểm vào qua proxy.

### Đặt @Async trên method nội bộ để tự động chạy nền

Nếu caller gọi method qua `this`, async interceptor không được kích hoạt. Nếu muốn tác vụ nền, nên đặt phương thức trong bean riêng hoặc dùng executor tường minh.

## 13. Hướng thiết kế và lựa chọn giải pháp

Khi phát hiện advice không chạy, có thể quyết định theo thứ tự:

1. **Xác định điểm vào:** bean khác gọi phương thức qua bean Spring hay target tự gọi `this.method()`?
2. **Xác định advice cần áp dụng:** transaction, async, cache, security hay custom aspect?
3. **Nếu toàn bộ workflow dùng chung một advice:** cân nhắc đặt annotation ở phương thức entry point được gọi qua proxy.
4. **Nếu phương thức trong cần ranh giới riêng:** tách nó sang một bean khác và inject bean đó vào caller.
5. **Nếu cần transaction với phạm vi cực cụ thể:** cân nhắc `TransactionTemplate` để điều khiển tường minh.
6. **Nếu không thể tái cấu trúc:** đánh giá kỹ việc truy cập self proxy, hiểu rõ điều kiện exposeProxy và kiểu proxy.
7. **Nếu thực sự cần weave advice vào self-invocation:** nghiên cứu AspectJ mode và chi phí cấu hình weaving.
8. **Kiểm thử ở mức phù hợp:** xác nhận side effect, luồng thực thi, số lần dùng cache hoặc ranh giới transaction; không chỉ xem sự tồn tại của annotation.

### Ví dụ chọn giải pháp

| Tình huống | Lựa chọn thường phù hợp |
|---|---|
| Một workflow gồm nhiều helper phải dùng chung transaction | Đặt `@Transactional` trên entry point được gọi qua proxy |
| Một bước phải dùng `REQUIRES_NEW` độc lập với workflow | Tách sang bean khác và gọi qua dependency |
| Một tác vụ phải chạy async | Tách bean có method `@Async` hoặc dùng executor tường minh |
| Một truy vấn phải tận dụng `@Cacheable` | Đưa truy vấn vào bean lookup riêng và gọi qua proxy |
| Chỉ cần transaction cho một block nhỏ | Sử dụng `TransactionTemplate` |
| Không thể thay kiến trúc và cần advice cho lời gọi nội bộ | Đánh giá AspectJ weaving sau khi cân nhắc yêu cầu triển khai |

## 14. Tóm lại: ranh giới quan trọng là proxy

Với Spring Boot, dấu hiệu cốt lõi của lỗi self-invocation là phương thức được gắn annotation AOP nhưng lại được gọi bằng `this.method()` hoặc một lời gọi nội bộ tương đương. Khi đó:

- Lời gọi **không quay lại Spring AOP proxy**.
- Advice dành riêng cho phương thức trong **không được kích hoạt**.
- Transaction đang có từ phương thức ngoài có thể vẫn tồn tại, nhưng propagation hoặc các quy tắc riêng trên phương thức trong không được áp dụng như một lần intercept riêng.
- CGLIB không tự giải quyết vấn đề.
- Tách phương thức cần advice sang một Spring bean riêng thường là giải pháp rõ ràng nhất.

Hiểu chính xác đường đi của lời gọi giúp tránh những lỗi khó nhận biết như `@Transactional` không mở giao dịch mới, `@Async` chạy đồng bộ hoặc `@Cacheable` không dùng cache. Hãy thiết kế các ranh giới advice tại những điểm vào thật sự đi qua bean proxy, đồng thời giữ logic nghiệp vụ dễ đọc và dễ kiểm thử.

