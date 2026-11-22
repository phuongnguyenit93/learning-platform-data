# Giới hạn với final, private và phương thức không thể can thiệp

Spring AOP thường được dùng để triển khai những hành vi cắt ngang (cross-cutting concerns) như transaction, logging, metrics, caching, security hoặc xử lý bất đồng bộ. Với các annotation như `@Transactional`, `@Cacheable` và `@Async`, nhiều lập trình viên mong rằng chỉ cần đánh dấu một phương thức là Spring sẽ tự động áp dụng hành vi tương ứng mỗi khi phương thức chạy.

Nhưng Spring AOP ở chế độ thông thường dựa trên **proxy**. Proxy chỉ có thể can thiệp các lời gọi **đi qua đối tượng proxy** và các phương thức mà cơ chế proxy thực sự có khả năng chặn. Vì vậy, một phương thức `private`, một phương thức `final` khi dùng class-based proxy, một lời gọi nội bộ bằng `this` hoặc một constructor không được xử lý theo cách một phương thức public được gọi qua proxy.

Bài học này tập trung vào những ranh giới đó và cách thiết kế code phù hợp, tránh trường hợp annotation có mặt nhưng không có tác dụng.

## 1. Trước hết: Spring AOP proxy hoạt động thế nào?

Một Spring bean bình thường là một Java object:

~~~java
@Service
public class PaymentService {

    public void pay() {
        // Logic thanh toán.
    }
}
~~~

Khi bean được áp dụng AOP, Spring có thể cung cấp một **proxy object** cho các thành phần bên ngoài sử dụng. Proxy này nhận lời gọi phương thức, chạy chuỗi interceptor/advice, rồi chuyển tiếp đến logic của target object theo cơ chế phù hợp.

~~~text
           OtherService
                |
                | gọi paymentService.pay()
                v
        +------------------+
        |  Spring AOP      |
        |  proxy           |
        |------------------|
        | Before advice    |
        | Around advice    |
        | Transaction ...  |
        +------------------+
                |
                v
           Target method
           PaymentService.pay()
                |
                v
        Return / exception
                |
                v
      Proxy hoàn thành advice
~~~

Ví dụ một advice:

~~~java
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TimingAspect {

    @Around("execution(* com.example.payment.PaymentService.pay(..))")
    public Object measure(ProceedingJoinPoint joinPoint)
            throws Throwable {

        long start = System.nanoTime();
        try {
            return joinPoint.proceed();
        } finally {
            long elapsed = System.nanoTime() - start;
            System.out.println("Elapsed nanos: " + elapsed);
        }
    }
}
~~~

Khi `PaymentService.pay()` được gọi **qua proxy** và pointcut khớp, advice có thể thực thi. Để sử dụng các `@Aspect` dạng này trong ứng dụng Boot, cần có AOP infrastructure tương ứng trên classpath và được kích hoạt theo cấu hình ứng dụng.

**Bản chất:** Proxy chặn lời gọi tại ranh giới giữa đối tượng gọi và bean. Proxy không tự sửa bytecode của mọi phương thức Java và cũng không trở thành một trình quan sát mọi lời gọi bên trong target.

## 2. Hai chiến lược proxy quan trọng

Spring AOP có hai chiến lược proxy phổ biến:

1. **JDK dynamic proxy:** tạo proxy triển khai các interface của target.
2. **Class-based proxy (CGLIB):** tạo một subclass của target class rồi override các phương thức có thể can thiệp.

### 2.1. JDK dynamic proxy

Ví dụ:

~~~java
public interface PaymentOperations {
    void pay();
}

@Service
public class PaymentService implements PaymentOperations {

    @Override
    public void pay() {
        // Xử lý thanh toán.
    }
}
~~~

JDK proxy triển khai `PaymentOperations`:

~~~text
PaymentOperations
      ^
      |
JDK Proxy implements PaymentOperations
      |
      | dispatch / interceptor
      v
PaymentService target
~~~

Điều quan trọng là caller sử dụng kiểu interface:

~~~java
@Service
public class CheckoutService {

    private final PaymentOperations payments;

    public CheckoutService(PaymentOperations payments) {
        this.payments = payments;
    }

    public void checkout() {
        payments.pay();
    }
}
~~~

Với JDK dynamic proxy, chỉ các phương thức được phơi bày qua những interface mà proxy triển khai mới là điểm gọi có thể can thiệp theo kiểu proxy này. Những phương thức chỉ tồn tại trên concrete class và không thuộc interface sẽ không thể được gọi trực tiếp qua một reference chỉ có kiểu interface proxy.

### 2.2. Class-based proxy (CGLIB)

Nếu Spring dùng class-based proxy:

~~~text
PaymentService
      ^
      | extends
      |
PaymentService$$SpringCGLIB proxy
      |
      | override pay() và áp dụng advice
      v
PaymentService logic
~~~

Proxy là một subclass của target class. Cơ chế subclassing cần Java cho phép **kế thừa class** và **override method**. Đây là nguồn gốc của giới hạn với `final` và `private`.

### 2.3. Spring Boot thường chọn loại nào?

Trong các ứng dụng Spring Boot có AOP được auto-configure, class-based proxy thường là lựa chọn mặc định. Với cấu hình hỗ trợ tương ứng, có thể điều chỉnh bằng:

~~~properties
spring.aop.proxy-target-class=false
~~~

Giá trị `false` yêu cầu ưu tiên JDK interface-based proxy nếu target có interface phù hợp. Nếu class không có interface thích hợp, không thể mong JDK proxy cung cấp các phương thức riêng của class.

Một số cơ chế như transaction, async và AOP infrastructure có thể có cấu hình proxy riêng hoặc chịu tác động của các thiết lập `@Enable...`. Vì vậy, **hãy kiểm tra kiểu proxy thực tế**, đừng dựa duy nhất vào việc dự án dùng Spring Boot.

## 3. Bảng giới hạn tổng quan

| Trường hợp | JDK dynamic proxy | Class-based proxy | Ghi chú |
|---|---|---|---|
| Public method được khai báo trong interface | Có thể can thiệp | Có thể can thiệp nếu override được | Lời gọi phải qua proxy |
| Public method chỉ có trên concrete class | Không truy cập được qua interface proxy thông thường | Có thể can thiệp nếu không final | Phụ thuộc kiểu proxy |
| `final` class | Có thể proxy qua interface phù hợp | **Không thể subclass** | JDK proxy không cần kế thừa target class |
| `final` instance method | Có thể can thiệp lời gọi qua interface proxy | **Không override được** | Phân biệt final class với final method |
| `private` method | Không phơi bày qua interface | **Không override được** | Annotation trên private method không được áp dụng bởi proxy thông thường |
| `static` method | Không là instance-dispatch của JDK proxy | Không override được | Static dispatch không đi qua proxy instance |
| Constructor | Không phải interface method | Không phải method override | Spring AOP không advise constructor execution |
| `protected`/package-private method | Không phơi bày như public interface method | Có thể được hỗ trợ tùy visibility và framework semantics | Không mặc định mọi loại annotation hỗ trợ như nhau |
| Self-invocation, ví dụ `this.runTask()` | Không qua proxy | Không qua proxy | Cùng object gọi nội bộ |
| Object tạo bằng `new` ngoài Spring | Không được Spring proxy tự động | Không được Spring proxy tự động | Không phải Spring-managed bean |

Bảng nói về **Spring AOP dựa trên proxy**. AspectJ weaving là cơ chế khác và có khả năng can thiệp nhiều loại join point hơn.

## 4. Vì sao final class không thể dùng class-based proxy?

Trong Java, `final` trên class cấm class khác kế thừa nó:

~~~java
public final class ReportService {

    public void generate() {
        // ...
    }
}
~~~

CGLIB cần tạo subclass tương tự:

~~~java
class ReportServiceProxy extends ReportService {
    // Không thể: ReportService là final.
}
~~~

Vì thế, một AOP configuration yêu cầu class-based proxy cho `ReportService` không thể tạo subclass proxy bình thường. Tùy trường hợp và cơ chế AOP, startup có thể thất bại khi Spring cố tạo proxy cho target final.

### 4.1. final class có interface thì sao?

Điểm tinh tế: **final class không đồng nghĩa không thể sử dụng AOP với mọi chiến lược proxy**.

~~~java
public interface ReportOperations {
    void generate();
}

public final class ReportService implements ReportOperations {

    @Override
    public void generate() {
        // ...
    }
}
~~~

Một **JDK dynamic proxy** có thể triển khai `ReportOperations` và chuyển lời gọi đến `ReportService`, dù target class là final. JDK proxy không kế thừa `ReportService`.

~~~text
             ReportOperations
                    ^
                    |
             JDK interface proxy
                    |
                    v
           final ReportService target
~~~

Điều kiện là bean cần được cấu hình để thực sự dùng JDK proxy, và caller nên inject `ReportOperations` thay vì kiểu concrete `ReportService`.

~~~java
@Service
public class ExportControllerService {
    private final ReportOperations reports;

    public ExportControllerService(ReportOperations reports) {
        this.reports = reports;
    }
}
~~~

Nếu code inject concrete type trong khi Spring trả về JDK proxy, có thể gặp lỗi không khớp kiểu vì proxy đó **không phải một instance của concrete target class**.

### 4.2. Kết luận với final class

- Dùng class-based proxy: target class cần có thể kế thừa.
- Dùng JDK proxy: target có thể final, miễn là proxy hóa được interface phù hợp.
- Không nên thay đổi cấu hình proxy của toàn ứng dụng chỉ để xử lý một class nếu việc đó làm những bean khác bị ảnh hưởng.
- Nếu cần AOP trên nhiều method không thuộc interface, cân nhắc thiết kế target class có thể proxy hoặc tách logic qua một service phù hợp.

## 5. Vì sao final method không được CGLIB can thiệp?

`final` trên method cấm subclass override method đó:

~~~java
@Service
public class InvoiceService {

    public final void issueInvoice() {
        System.out.println("Issuing invoice");
    }
}
~~~

Với class-based proxy, Java không cho phép subclass viết:

~~~java
@Override
public void issueInvoice() {
    // Không thể override final method.
}
~~~

Vì không override được method, CGLIB không thể đặt logic interceptor vào đường gọi method đó theo cách thông thường.

Ví dụ có annotation:

~~~java
@Service
public class InvoiceService {

    @Transactional
    public final void issueInvoice() {
        // Code xử lý hóa đơn.
    }
}
~~~

Nếu ứng dụng dùng class-based proxy, **đừng kỳ vọng `@Transactional` có tác dụng trên final method**. Annotation vẫn nằm trong source/bytecode, nhưng proxy không thể chặn lời gọi để mở transaction cho method đó.

### 5.1. final method qua JDK proxy

Nếu method là triển khai của một interface:

~~~java
public interface InvoiceOperations {
    void issueInvoice();
}

@Service
public class InvoiceService implements InvoiceOperations {

    @Override
    @Transactional
    public final void issueInvoice() {
        // ...
    }
}
~~~

Với **JDK interface proxy**, lời gọi `InvoiceOperations.issueInvoice()` đi qua invocation handler trước khi đến target. Do đó, `final` của method triển khai trên target class không ngăn JDK proxy chặn interface call.

Kết quả phụ thuộc cấu hình proxy, annotation discovery và advisor đang dùng, nhưng ràng buộc kỹ thuật “không thể override final method” **không áp dụng cho JDK proxy**.

### 5.2. final do công cụ sinh code

Không phải chỉ những class có chữ `final` viết trực tiếp mới gặp giới hạn:

- Java `record` là final class.
- Một số class generated bởi code generator có thể là final.
- Kotlin class và method mặc định là final nếu không được mở.
- Sealed class có thể giới hạn những subclass nào được phép kế thừa.

Nếu một bean sẽ được áp dụng class-based AOP, hãy kiểm tra cả các ràng buộc kế thừa này.

## 6. Vì sao private method không thể được proxy can thiệp?

Một phương thức `private` chỉ được truy cập bên trong phạm vi class theo quy tắc Java. Nó không được subclass override như một public/protected method.

~~~java
@Service
public class BillingService {

    public void bill() {
        validateInvoice();
    }

    @Transactional
    private void validateInvoice() {
        // ...
    }
}
~~~

Ở đây có hai vấn đề:

1. `validateInvoice()` là private, nên class-based proxy không thể override để can thiệp.
2. `bill()` gọi `validateInvoice()` trực tiếp bên trong target, không phải lời gọi đi qua proxy.

Vì vậy, `@Transactional` trên private method không tạo một transaction mới khi private method đó chạy qua proxy-based AOP.

### 6.1. Đổi private thành public đã đủ chưa?

Chưa chắc. Nếu code chỉ đổi:

~~~java
@Transactional
public void validateInvoice() {
    // ...
}
~~~

nhưng `bill()` vẫn gọi:

~~~java
public void bill() {
    validateInvoice(); // self-invocation
}
~~~

thì lời gọi nội bộ vẫn có thể **bỏ qua proxy**, dù method là public và không final. Cần xét cả **khả năng intercept** lẫn **đường đi của lời gọi**.

## 7. Self-invocation: lời gọi nội bộ không đi qua proxy

Đây là lỗi phổ biến nhất khi dùng proxy-based AOP.

~~~java
@Service
public class OrderService {

    public void placeOrder() {
        saveAuditLog();
    }

    @Transactional
    public void saveAuditLog() {
        // Ghi dữ liệu xuống DB.
    }
}
~~~

Caller bên ngoài gọi:

~~~java
orderService.placeOrder();
~~~

Dòng thực thi khái quát:

~~~text
Controller
    |
    v
OrderService proxy
    |
    v
Target OrderService.placeOrder()
    |
    | this.saveAuditLog()
    v
Target OrderService.saveAuditLog()
    |
    v
Không đi qua proxy cho lời gọi bên trong
~~~

Nếu `placeOrder()` không được advice giao dịch bao phủ, `@Transactional` đặt riêng trên `saveAuditLog()` không tự tạo transaction cho lời gọi nội bộ đó.

### 7.1. Nếu method ngoài đã có transaction?

~~~java
@Transactional
public void placeOrder() {
    saveAuditLog();
}
~~~

Nếu `placeOrder()` được gọi từ bên ngoài qua proxy, transaction mở ở method ngoài có thể bao phủ cả logic bên trong. Nhưng annotation transaction trên `saveAuditLog()` **không được đánh giá lại cho self-invocation**.

Điều này đặc biệt quan trọng nếu method trong khai báo:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void saveAuditLog() {
    // ...
}
~~~

Khi chỉ được gọi nội bộ, `REQUIRES_NEW` không tự kích hoạt qua proxy. Code chạy trong transaction của method ngoài (nếu có) hoặc không có transaction do method trong tạo ra.

### 7.2. Các annotation khác cũng gặp hiện tượng này

Không chỉ `@Transactional`:

| Annotation/cơ chế | Nếu method được gọi nội bộ mà không qua proxy |
|---|---|
| `@Transactional` | Transaction advice của method được gọi nội bộ không kích hoạt riêng |
| `@Async` (proxy mode) | Không tự chuyển lời gọi nội bộ sang executor |
| `@Cacheable` | Không tự kiểm tra/cache kết quả cho lời gọi nội bộ |
| `@CacheEvict` | Không tự kích hoạt cache eviction ở lời gọi nội bộ |
| `@PreAuthorize` qua method-security proxy | Không tự chạy check bảo mật cho self-invocation |
| Custom `@Aspect` advice | Không áp dụng nếu không có lời gọi qua proxy |

Hành vi cụ thể còn tùy cơ chế và cấu hình riêng, nhưng đối với **proxy mode**, nguyên tắc chung là không có intercept nếu call không đi qua proxy.

## 8. Giải pháp ưu tiên: tách method cần advice sang bean khác

Thay vì buộc một object gọi qua proxy của chính nó, ta có thể đặt logic cần transaction trong một service riêng.

~~~java
@Service
public class AuditLogService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAuditLog(Order order) {
        // Ghi log audit trong transaction độc lập.
    }
}
~~~

~~~java
@Service
public class OrderService {

    private final AuditLogService auditLogService;

    public OrderService(AuditLogService auditLogService) {
        this.auditLogService = auditLogService;
    }

    public void placeOrder(Order order) {
        // Các bước xử lý nghiệp vụ chính.
        auditLogService.writeAuditLog(order);
    }
}
~~~

Dòng thực thi:

~~~text
OrderService.placeOrder()
          |
          | gọi bean được inject
          v
AuditLogService proxy
          |
          | TransactionInterceptor
          v
AuditLogService.writeAuditLog()
~~~

Với cấu hình transaction infrastructure phù hợp, lời gọi vào `AuditLogService` đi qua proxy và có thể áp dụng `REQUIRES_NEW`.

Ưu điểm:

- Dependency được thể hiện qua constructor injection.
- Method cần advice có ranh giới trách nhiệm rõ.
- Không cần thao tác trực tiếp với `AopContext`.
- Dễ kiểm thử transaction behavior bằng integration test.
- Giảm việc một service tự gọi vào chính proxy của nó.

**Lưu ý:** `REQUIRES_NEW` cần transaction manager và tài nguyên phù hợp; có thể cần connection riêng. Không chọn propagation này chỉ để “thấy một transaction mới” mà không xét semantics nghiệp vụ.

## 9. Giải pháp khác: TransactionTemplate cho transaction cần điều khiển tường minh

Nếu một đoạn logic nằm trong private method và chỉ muốn một transaction quanh chính đoạn đó, có thể dùng `TransactionTemplate` thay cho việc kỳ vọng annotation trên private method hoạt động.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class BillingService {

    private final TransactionTemplate transactionTemplate;

    public BillingService(TransactionTemplate transactionTemplate) {
        this.transactionTemplate = transactionTemplate;
    }

    public void bill(Bill bill) {
        transactionTemplate.executeWithoutResult(status -> {
            performDatabaseChanges(bill);
        });
    }

    private void performDatabaseChanges(Bill bill) {
        // Các thay đổi DB nằm trong transaction được template mở.
    }
}
~~~

Ở đây transaction được điều khiển bằng một API tường minh, không cần proxy chặn lời gọi private method. Ứng dụng phải có `TransactionTemplate` bean được cấu hình với transaction manager thích hợp.

Có thể cấu hình propagation bằng API của template khi cần:

~~~java
TransactionTemplate template =
        new TransactionTemplate(transactionManager);
template.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
~~~

Đây là một giải pháp khi dùng transaction programmatic rõ ràng hơn. Nó không thay thế cho mọi AOP aspect như caching hoặc security. Với nghiệp vụ phức tạp, tách bean có thể vẫn là thiết kế dễ bảo trì hơn.

## 10. AopContext.currentProxy() và self-injection: vì sao không nên dùng tùy tiện?

Spring có cơ chế truy cập proxy hiện tại trong một số cấu hình:

~~~java
AopContext.currentProxy()
~~~

Nếu bật expose proxy tương ứng, code trong target có thể lấy proxy hiện tại rồi gọi method qua proxy. Nhưng cách này gắn business code trực tiếp với Spring AOP và đòi hỏi một lời gọi proxy context hợp lệ.

Ví dụ minh họa ý tưởng:

~~~java
((OrderService) AopContext.currentProxy()).saveAuditLog();
~~~

Cách này có nhiều điều kiện:

- Proxy phải được cấu hình để expose qua `AopContext`.
- Lời gọi phải diễn ra bên trong một invocation được AOP quản lý.
- Nếu là JDK proxy, proxy không nhất thiết cast được sang concrete class `OrderService`.
- Cấu hình proxy và call stack trở thành phụ thuộc ẩn trong business code.
- Dùng nó không giải quyết được giới hạn CGLIB với final/private method.

Một kỹ thuật khác là inject proxy của chính service vào service. Tuy nhiên, self-injection dễ tạo vòng dependency và khiến thiết kế khó hiểu. Spring Boot hiện đại thường không khuyến khích dựa vào circular references như một kiến trúc mặc định.

**Khuyến nghị:** ưu tiên tách logic cần advice sang một bean khác hoặc dùng API programmatic phù hợp, thay vì lạm dụng self-proxy.

## 11. static method không phải điểm can thiệp của proxy instance

Static method thuộc class, không gắn với dispatch trên instance theo cách một phương thức ảo được override.

~~~java
public class TokenUtil {

    @Transactional
    public static void resetTokens() {
        // ...
    }
}
~~~

Lời gọi:

~~~java
TokenUtil.resetTokens();
~~~

không đi qua Spring bean proxy thông thường. Không nên kỳ vọng annotation AOP trên static method được áp dụng.

Nếu xử lý cần transaction/cache/async, hãy chuyển nó sang một instance method trên Spring bean với phạm vi phù hợp:

~~~java
@Service
public class TokenMaintenanceService {

    @Transactional
    public void resetTokens() {
        // ...
    }
}
~~~

Sau đó gọi thông qua bean được Spring quản lý.

Static helper thuần, ví dụ parse string hoặc tính toán không có side effect, vẫn có thể là static; vấn đề chỉ xuất hiện khi cố sử dụng proxy advice trên nó.

## 12. Constructor và field access nằm ngoài Spring AOP proxy thông thường

Spring AOP proxy chủ yếu hỗ trợ **method execution join points** trên Spring-managed beans. Nó không phải cơ chế toàn diện để can thiệp:

- Constructor call hoặc constructor execution.
- Đọc/ghi field trực tiếp.
- Khởi tạo object bằng `new` ngoài container.
- Static initialization.
- Những thao tác khác không phải method call đi qua proxy.

Ví dụ:

~~~java
@Service
public class InventoryService {

    public InventoryService() {
        initializeState();
    }

    private void initializeState() {
        // Không đi qua AOP proxy khi constructor chạy.
    }
}
~~~

Ngay cả khi `initializeState()` đổi thành public và gắn `@Transactional`, lời gọi từ constructor vẫn xảy ra khi object đang được tạo, trước khi proxy hoàn chỉnh được dùng bởi caller.

Nếu việc khởi tạo cần transaction hoặc phụ thuộc vào những bean khác, nên xem xét lifecycle phù hợp hoặc chuyển thao tác đến service khác, chạy ở thời điểm ứng dụng sẵn sàng.

### 12.1. @PostConstruct cũng có giới hạn

~~~java
@Service
public class ReportService {

    @PostConstruct
    void initialize() {
        generateReport();
    }

    @Transactional
    public void generateReport() {
        // ...
    }
}
~~~

`@PostConstruct` thường chạy trong quá trình bean initialization **trước khi BeanPostProcessor tạo AOP proxy hoàn chỉnh và đưa proxy đến caller**. Lời gọi trực tiếp `generateReport()` từ callback này không đi qua proxy.

Nếu cần chạy logic giao dịch sau khi context sẵn sàng, có thể gọi một bean transaction khác từ `ApplicationRunner` hoặc một lifecycle event phù hợp. Tránh đặt logic nghiệp vụ phức tạp trong `@PostConstruct` chỉ vì muốn nó chạy sớm.

## 13. Protected và package-private method: cần phân biệt theo phiên bản

Không nên giản lược tất cả non-public method thành một nhóm “chắc chắn không thể AOP”. Có sự khác biệt quan trọng giữa `private` và `protected` hoặc package-private.

### 13.1. Private luôn có rào cản override

Private method không được subclass override, nên class-based proxy không thể intercept bằng cách override. JDK proxy cũng không phơi bày private method qua interface.

### 13.2. Protected và package-private có thể được class-based proxy hỗ trợ

Class-based proxy có thể override protected method hoặc package-private method khi các quy tắc truy cập Java và package của generated subclass cho phép. Trong Spring Framework 6, proxy-based `@Transactional` hỗ trợ mặc định cả protected và package-private methods trên class-based proxies trong những trường hợp phù hợp.

Ví dụ Spring Framework 6:

~~~java
@Service
public class BillingService {

    @Transactional
    protected void settleInvoice() {
        // ...
    }
}
~~~

Nhưng chỉ vì method có thể được proxy override không có nghĩa mọi lời gọi đến nó sẽ đi qua proxy. Nếu một method public trong cùng target gọi `settleInvoice()` bằng self-invocation, transaction advice của protected method vẫn không được kích hoạt riêng.

Ngoài ra:

- JDK interface proxy chỉ expose những interface method phù hợp, thông thường là public.
- Một package-private method không thể được override bởi subclass ngoài package theo quy tắc Java.
- Các annotation/hạ tầng khác có thể đặt yêu cầu visibility riêng.
- Trong các phiên bản Spring cũ, mặc định transaction proxy có những quy tắc visibility hạn chế hơn.

### 13.3. Cách viết an toàn khi cần tương thích rộng

Với một API nghiệp vụ có cross-cutting behavior, dùng **public non-final method** được gọi từ bean khác qua proxy thường là phương án dễ dự đoán nhất.

Nếu dự án cần proxy protected/package-private method, kiểm tra cụ thể Spring Framework version, proxy strategy và integration test. Không lấy một trường hợp hoạt động trên CGLIB rồi mặc định nó cũng hoạt động với JDK proxy hoặc mọi annotation khác.

## 14. Spring Boot và Kotlin: class final theo mặc định

Trong Kotlin, class và member function mặc định là final trừ khi được khai báo `open` hoặc được compiler plugin phù hợp mở tự động.

Ví dụ:

~~~kotlin
@Service
class EmailService {

    @Transactional
    fun sendEmail() {
        // ...
    }
}
~~~

Nếu class và method giữ final ở bytecode, class-based proxy có thể không subclass/override được. Với dự án Spring Boot + Kotlin, nhiều ứng dụng dùng plugin `kotlin-spring` (dựa trên all-open compiler plugin) để tự động mở các class/member có những annotation Spring phù hợp.

Ví dụ cấu hình Gradle Kotlin DSL (phiên bản plugin theo build của dự án):

~~~kotlin
plugins {
    kotlin("jvm")
    kotlin("plugin.spring")
    id("org.springframework.boot")
}
~~~

Không nên đưa version placeholder vào code production mà không đồng bộ với version Kotlin/Boot của dự án. Mục tiêu của ví dụ là nhận biết **plugin cần được kích hoạt**, không phải ấn định một tổ hợp version.

### 14.1. Khi nào vẫn gặp lỗi với Kotlin?

- Class không có annotation được all-open plugin nhận diện.
- Method bị khai báo final theo cấu hình/bytecode thực tế.
- Một class không được Spring quản lý mà được tạo bằng constructor thông thường.
- Self-invocation bỏ qua proxy dù class đã open.
- Proxy là JDK proxy nhưng caller inject bằng concrete type.

Do đó, bật `kotlin-spring` có thể giải quyết vấn đề proxy subclass final, nhưng **không giải quyết toàn bộ giới hạn của Spring AOP**.

## 15. Java record, final class và sealed class

Java record là final class nên không thể làm superclass cho class-based proxy:

~~~java
public record ExchangeRate(String currency, double value) {
}
~~~

Record thường thích hợp làm DTO hoặc value object bất biến, **không phải service bean chứa method cần transaction/AOP**. Nếu đặt một record làm Spring bean rồi yêu cầu CGLIB proxy, cần xem xét ngay ràng buộc final.

Sealed class cũng giới hạn những class có thể extends/implements nó; dynamic proxy và subclass generation có thể gặp các ràng buộc về permitted subclasses/interfaces. Khi thiết kế service dùng AOP, tránh để inheritance constraints của domain model vô tình biến thành rào cản proxy.

Một mô hình tốt là giữ DTO/value object bất biến, còn hành vi cần transaction/cache/async nằm trong một Spring service phù hợp.

## 16. Các module JPMS và class visibility

Ngay cả khi class không `final`, class-based proxy vẫn có thể gặp giới hạn từ Java module system và access rules.

Ví dụ:

- Class hoặc method không đủ visibility cho subclass/generated proxy.
- Package chưa được mở trong named module khi framework cần quyền phản chiếu hoặc định nghĩa proxy.
- Class thuộc một module/package hệ thống có ràng buộc truy cập.
- Class loader hoặc môi trường runtime hạn chế bytecode generation.

Trong môi trường có `module-info.java`, cần thiết kế module exports/opens thích hợp cho Spring framework và các thư viện proxy nếu thật sự cần. Đừng phản ứng với lỗi proxy bằng cách mở toàn bộ module hoặc thêm JVM flags rất rộng mà chưa xác định nguyên nhân.

Spring Boot ứng dụng trên classpath thông thường ít phải xử lý JPMS trực tiếp hơn, nhưng giới hạn visibility vẫn quan trọng với package-private method và target classes.

## 17. @Transactional: những tình huống dễ nhầm

Xét class:

~~~java
@Service
public class AccountService {

    @Transactional
    public void transfer() {
        debit();
        credit();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    private void debit() {
        // ...
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    private void credit() {
        // ...
    }
}
~~~

Đối với proxy-based transaction management:

- `transfer()` được gọi qua proxy có thể được bao trong **một** transaction.
- `debit()` và `credit()` là private nên không được proxy intercept.
- Hai annotation `REQUIRES_NEW` không tạo hai transaction độc lập khi private methods được gọi như vậy.

Nếu yêu cầu nghiệp vụ thực sự cần mỗi bước có transaction độc lập, có thể tách thành service riêng với public method được gọi qua proxy hoặc dùng `TransactionTemplate` với propagation rõ ràng.

### 17.1. Transaction không chỉ phụ thuộc annotation

Ngay cả với public method được proxy intercept, transaction có hoạt động như mong đợi còn phụ thuộc:

- Transaction infrastructure có được kích hoạt và transaction manager có phù hợp không.
- Call có đi qua đúng proxy không.
- Exception và rollback rules có được cấu hình đúng không.
- Nơi chạy method (thread khác, async boundary, v.v.) có giữ transaction context theo semantics hay không.
- Method có phải điểm khởi đầu transaction phù hợp với mô hình dữ liệu/DB không.

Không nên quy mọi lỗi transaction cho `final` hoặc `private` mà bỏ qua những yếu tố này.

## 18. @Async: không phải cứ annotation là chạy trên thread khác

Ví dụ:

~~~java
@Service
public class EmailService {

    public void notifyCustomer() {
        sendEmail();
    }

    @Async
    public void sendEmail() {
        // ...
    }
}
~~~

Nếu `notifyCustomer()` gọi `sendEmail()` nội bộ, lời gọi đó thường chạy như Java method call bình thường; proxy async interceptor không được áp dụng. Khi đó không nên kỳ vọng method tự chuyển sang executor.

Một thiết kế rõ hơn:

~~~java
@Service
public class AsyncEmailSender {

    @Async
    public void sendEmail() {
        // ...
    }
}
~~~

~~~java
@Service
public class NotificationService {

    private final AsyncEmailSender sender;

    public NotificationService(AsyncEmailSender sender) {
        this.sender = sender;
    }

    public void notifyCustomer() {
        sender.sendEmail();
    }
}
~~~

Cần cấu hình bật async support và executor phù hợp. Ngoài ra, `@Async` với proxy mode không giúp một private/static/final method của class-based proxy được intercept.

## 19. @Cacheable: self-invocation làm cache không được dùng

Ví dụ:

~~~java
@Service
public class ProductService {

    public Product getProduct(String sku) {
        return loadFromDatabase(sku);
    }

    @Cacheable("products")
    public Product loadFromDatabase(String sku) {
        // ...
    }
}
~~~

Lời gọi từ `getProduct()` đến `loadFromDatabase()` trong cùng target không đi qua proxy cache. Kết quả có thể là database bị truy vấn lặp lại dù annotation `@Cacheable` có mặt.

Để cache hoạt động theo proxy mode:

~~~java
@Service
public class CachedProductLookup {

    @Cacheable("products")
    public Product loadFromDatabase(String sku) {
        // ...
    }
}
~~~

~~~java
@Service
public class ProductService {
    private final CachedProductLookup lookup;

    public ProductService(CachedProductLookup lookup) {
        this.lookup = lookup;
    }

    public Product getProduct(String sku) {
        return lookup.loadFromDatabase(sku);
    }
}
~~~

Lời gọi được chuyển qua bean proxy khác, nơi caching interceptor có thể thực hiện lookup/cache result.

## 20. Khi Spring bean không được proxy vì tạo bằng new

Một class có `@Service` chỉ là metadata. Nếu code chủ động dùng `new`:

~~~java
PaymentService service = new PaymentService();
service.pay();
~~~

thì object này không được tạo hoặc thay thế bởi Spring container. Nó không tự có proxy của Spring AOP.

Để hưởng proxy advice, lấy bean từ Spring container thông qua dependency injection:

~~~java
@Service
public class CheckoutService {

    private final PaymentService payments;

    public CheckoutService(PaymentService payments) {
        this.payments = payments;
    }

    public void checkout() {
        payments.pay();
    }
}
~~~

Ví dụ giả định target có thể proxy theo chiến lược đang dùng. Với JDK proxy, nên inject interface tương ứng.

Tương tự, nếu một framework khác tự tạo instance mà không qua Spring integration thích hợp, annotation AOP trên class không tự bảo đảm interceptor sẽ chạy.

## 21. Proxy có được tạo quá muộn không?

Spring thường áp dụng proxy thông qua `BeanPostProcessor`. Vì vậy, những thời điểm sớm như constructor và `@PostConstruct` khác với những lời gọi đến bean sau khi context đã hoàn tất khởi tạo.

~~~text
Instantiate target
      |
      v
Dependency injection
      |
      v
@PostConstruct / initialization callbacks
      |
      v
BeanPostProcessor after initialization
      |
      v
Proxy hoàn chỉnh được đưa cho caller
      |
      v
External calls qua proxy -> có thể bị advice intercept
~~~

Đây là luồng khái quát thông thường; một số tình huống như circular dependencies hoặc các framework extension đặc biệt có thể phức tạp hơn. Không nên dùng callback khởi tạo để “thử” một method `@Transactional` của chính bean rồi kết luận AOP đã hoạt động.

Một bean được khởi tạo quá sớm trước khi tất cả `BeanPostProcessor` được đăng ký cũng có thể không được xử lý đầy đủ bởi infrastructure cần thiết. Đó là vấn đề lifecycle khác với giới hạn final/private, nhưng có cùng biểu hiện: annotation không tạo ra hiệu ứng mong muốn.

## 22. Cách xác định bean đang dùng proxy nào

Spring cung cấp `AopUtils` để kiểm tra một bean sau khi context đã tạo:

~~~java
import org.springframework.aop.support.AopUtils;
import org.springframework.context.ApplicationContext;

public class ProxyDiagnostics {

    public static void print(ApplicationContext context) {
        Object bean = context.getBean("paymentService");

        System.out.println(AopUtils.isAopProxy(bean));
        System.out.println(AopUtils.isJdkDynamicProxy(bean));
        System.out.println(AopUtils.isCglibProxy(bean));
        System.out.println(bean.getClass().getName());
    }
}
~~~

Ý nghĩa:

| API | Cho biết |
|---|---|
| `AopUtils.isAopProxy(bean)` | Đối tượng có phải Spring AOP proxy không |
| `AopUtils.isJdkDynamicProxy(bean)` | Có phải JDK dynamic proxy do Spring AOP dùng không |
| `AopUtils.isCglibProxy(bean)` | Có phải CGLIB class-based proxy do Spring AOP dùng không |
| `bean.getClass()` | Runtime type thực tế của object đang được inject |

Không phải mọi Spring bean đều có proxy. Không thấy proxy không nhất thiết là lỗi nếu bean không có advisor/annotation nào áp dụng.

### 22.1. Đừng chỉ nhìn tên class

Tên class có hậu tố như `$$SpringCGLIB$$` có thể là dấu hiệu nhưng không nên là điều kiện kiểm thử cứng. Dùng `AopUtils` và quan sát hành vi thực tế sẽ rõ ràng hơn.

### 22.2. Proxy kiểu interface và việc cast

Một JDK proxy có thể được inject bằng kiểu interface:

~~~java
PaymentOperations operations =
        context.getBean(PaymentOperations.class);
~~~

Nhưng việc cast nó sang concrete class:

~~~java
PaymentService implementation = (PaymentService) operations;
~~~

có thể thất bại vì JDK proxy không extends `PaymentService`. Thiết kế dependency bằng interface giúp tránh phụ thuộc loại proxy.

## 23. AspectJ weaving khác proxy-based Spring AOP thế nào?

Spring AOP proxy chỉ chặn những method execution đi qua proxy. **AspectJ weaving** là cơ chế có thể tác động đến bytecode tại compile time hoặc load time, nên hỗ trợ nhiều join points hơn.

| Đặc điểm | Spring AOP proxy | AspectJ weaving |
|---|---|---|
| Cơ chế | JDK/CGLIB proxy tại runtime | Weave bytecode |
| Lời gọi self-invocation | Thường không intercept | Có thể advice nếu pointcut/weaving phù hợp |
| Constructor join points | Không | Có thể hỗ trợ |
| Field get/set join points | Không | Có thể hỗ trợ |
| Private method execution | Không theo proxy-based method interception | Có thể advise với AspectJ phù hợp |
| Final method execution | Không với class-based proxy | Có thể advise bằng weaving phù hợp |
| Độ phức tạp triển khai | Thường đơn giản hơn | Cần cấu hình compiler/weaver, class loading và test kỹ |

Cần phân biệt **AspectJ annotation syntax** với **AspectJ weaving**. Dùng `@Aspect` trong một dự án Spring Boot thông thường **không có nghĩa** ứng dụng đã bật bytecode weaving. Một `@Aspect` được Spring AOP phát hiện vẫn chạy theo proxy model và chịu giới hạn proxy.

Với `@Transactional`, có thể tồn tại transaction AspectJ mode khi cấu hình hỗ trợ, nhưng đó là lựa chọn kiến trúc riêng, cần dependency/weaving setup tương ứng. Không thể khắc phục private/final method bằng cách chỉ thêm một dependency AspectJ rồi giữ nguyên mọi thiết lập.

## 24. Nên chọn refactor hay AspectJ?

Đối với phần lớn ứng dụng nghiệp vụ Spring Boot:

- Nếu method cần transaction/cache/async, **tách sang bean riêng** hoặc bảo đảm caller đi qua proxy.
- Nếu method đang `private`, cân nhắc ranh giới public ở service phù hợp, không cần làm public mọi helper chỉ để “có annotation”.
- Nếu class/method `final` không có lý do bắt buộc, có thể điều chỉnh thiết kế để class-based proxy hoạt động.
- Nếu class bắt buộc final nhưng có interface phù hợp, JDK proxy có thể là lựa chọn.
- Nếu cần transaction chủ động bên trong method, `TransactionTemplate` có thể phù hợp.
- Chỉ xem xét AspectJ weaving khi yêu cầu join point thực sự vượt giới hạn proxy và team có khả năng vận hành hệ thống weaving.

Lợi ích của việc tách bean không chỉ là “qua được proxy”: nó làm dependency, transaction boundary và trách nhiệm nghiệp vụ rõ ràng hơn.

## 25. Kiểm thử ranh giới can thiệp

Với hành vi AOP, **unit test gọi thẳng target method** không đủ để xác nhận advice hoạt động. Cần một Spring context chứa proxy, advisor và dependency thật hoặc test double phù hợp.

### 25.1. Kiểm tra proxy strategy

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ProxyTypeTest {

    @Autowired
    PaymentOperations payments;

    @Test
    void paymentServiceIsProxied() {
        assertThat(AopUtils.isAopProxy(payments)).isTrue();
    }
}
~~~

Ví dụ giả định `PaymentService` có advisor thực sự áp dụng và ứng dụng đã bật infrastructure AOP. Nếu không có advisor phù hợp, không có lý do buộc Spring phải tạo proxy.

### 25.2. Kiểm thử @Transactional qua behavior thực tế

Một cách quan sát là kiểm tra trạng thái transaction trong method được gọi qua proxy:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class TransactionProbe {

    @Transactional
    public boolean isTransactionActive() {
        return TransactionSynchronizationManager
                .isActualTransactionActive();
    }
}
~~~

Test:

~~~java
@SpringBootTest
class TransactionProbeTest {

    @Autowired
    TransactionProbe probe;

    @Test
    void externalCallRunsInsideTransaction() {
        assertThat(probe.isTransactionActive()).isTrue();
    }
}
~~~

Test yêu cầu một transaction manager được cấu hình đúng. Nó kiểm tra behavior khi gọi public method qua bean Spring, không chỉ sự tồn tại của annotation. Nếu test class tự có `@Transactional`, một transaction bao ngoài có thể khiến assertion không chứng minh được advice của probe; hãy tránh điều đó khi thiết kế test này.

### 25.3. Kiểm tra self-invocation

Có thể bổ sung method:

~~~java
@Service
public class TransactionProbe {

    @Transactional
    public boolean isTransactionActive() {
        return TransactionSynchronizationManager
                .isActualTransactionActive();
    }

    public boolean internalCall() {
        return isTransactionActive();
    }
}
~~~

Với `internalCall()` được gọi từ bên ngoài mà method đó không có transaction advice và không có transaction nào khác đang hoạt động, `isTransactionActive()` bên trong thường trả về `false`: self-invocation không kích hoạt transaction advice của method bên trong.

Test tình huống này cần kiểm soát môi trường giao dịch, không chạy trong một transaction được test runner mở sẵn.

### 25.4. Kiểm thử final/private behavior

Với class-based proxy, viết test thể hiện:

- Một public, non-final method được gọi qua proxy nhận advice như mong đợi.
- Final method không được class-based proxy intercept.
- Private method không phải điểm chặn proxy.
- JDK proxy có thể chặn interface call dù target implementation method final.
- Self-invocation không chạy advice độc lập.

Không nên chỉ assert tên annotation; nên quan sát counter của aspect, transaction activity, số lần cache lookup hoặc thread thực thi tùy mục tiêu kiểm thử.

## 26. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `@Transactional` đặt trên private method nhưng không hoạt động | Proxy không can thiệp private method | Đặt transaction boundary trên method có thể proxy và gọi qua bean khác, hoặc dùng TransactionTemplate |
| `@Async` method chạy trên caller thread | Self-invocation, method không intercept được, async chưa bật hoặc executor configuration | Đưa method vào bean khác, xác nhận proxy/async setup |
| `@Cacheable` không giảm số lần gọi DB | Method được gọi nội bộ, không qua cache proxy | Tách cached lookup bean và gọi qua proxy |
| Bean final class không tạo được CGLIB proxy | Class không thể subclass | Dùng interface JDK proxy nếu phù hợp hoặc refactor class |
| Final method không nhận advice khi dùng CGLIB | Không thể override method | Bỏ final khi thiết kế cho phép, tách bean, hoặc chọn mô hình khác |
| Inject concrete type thất bại khi bật JDK proxy | Proxy chỉ implement interface | Inject interface hoặc xem lại proxy strategy |
| Public method có annotation nhưng vẫn không có advice | Bean không do Spring quản lý, advisor không match hoặc call không qua proxy | Kiểm tra bean wiring, pointcut, AopUtils và call path |
| `@PostConstruct` gọi method transaction không có effect | Proxy chưa sẵn sàng; self-invocation | Dùng lifecycle muộn và gọi bean transaction khác |
| Kotlin service final gây lỗi proxy | Kotlin mặc định final, thiếu all-open plugin | Dùng kotlin-spring plugin hoặc thiết kế proxy phù hợp |
| Method protected hoạt động ở dự án này nhưng không ở dự án khác | Khác Spring version/proxy strategy/annotation support | Kiểm tra semantics cụ thể, ưu tiên public non-final cho API cần AOP |
| Muốn advice constructor hoặc field | Spring AOP proxy không hỗ trợ join point đó | Refactor hoặc cân nhắc AspectJ weaving khi thật sự cần |
| Aspect dùng `@Aspect` nhưng self-call vẫn bỏ qua advice | Vẫn dùng Spring proxy-based AOP, không phải weaving | Hiểu sự khác biệt giữa @Aspect syntax và weaving |

## 27. Hướng dẫn chọn giải pháp

| Yêu cầu thực tế | Cách nên cân nhắc |
|---|---|
| Transaction cho method nghiệp vụ | Public non-final method trên Spring bean, gọi qua proxy |
| Method nội bộ cần transaction độc lập | Tách sang service khác hoặc TransactionTemplate |
| Async task được gọi nội bộ | Tách worker bean có `@Async` và gọi qua proxy |
| Cache kết quả một method | Dùng bean chuyên trách có `@Cacheable`, được caller gọi qua proxy |
| Target class bắt buộc final | Dùng JDK interface proxy nếu có interface phù hợp |
| Target method final nhưng cần advice theo interface | Xác nhận JDK proxy và annotation/advisor thực sự hoạt động |
| Kotlin bean dùng class-based AOP | Bật và cấu hình kotlin-spring/all-open phù hợp |
| Cần chặn constructor hoặc field access | Cân nhắc AspectJ weaving hoặc thiết kế lại |
| Chỉ muốn helper dùng chung | Giữ private/static thuần khi không cần AOP |
| Cần biết proxy loại nào | `AopUtils.isAopProxy/isJdkDynamicProxy/isCglibProxy` và integration test |

## 28. Nguyên tắc thiết kế cần nhớ

1. **Spring AOP proxy cần một lời gọi đi qua proxy.** Annotation một mình không thay đổi mọi method call trong JVM.
2. **JDK dynamic proxy dựa trên interface; CGLIB class proxy dựa trên subclass và override.**
3. **Final class** không thể làm target của class-based proxy thông thường; nếu có interface thích hợp vẫn có thể dùng JDK proxy.
4. **Final instance method** không thể được CGLIB override, nhưng có thể được intercept qua interface proxy nếu lời gọi đi qua JDK proxy phù hợp.
5. **Private/static method và constructor** không phải các điểm can thiệp của Spring AOP proxy thông thường.
6. **Self-invocation** bỏ qua proxy kể cả khi method public, non-final và có annotation.
7. Các annotation `@Transactional`, `@Async`, `@Cacheable`, `@PreAuthorize` đều cần xét đường gọi và mô hình proxy tương ứng.
8. Với Spring Framework 6 và class-based proxy, một số protected/package-private methods có thể được hỗ trợ; đừng đánh đồng với private.
9. Đừng dùng `@PostConstruct` hoặc constructor để gọi method AOP của chính bean rồi mong advice chạy.
10. Ưu tiên **tách bean theo trách nhiệm**, interface injection và transaction boundary rõ ràng. Chỉ sử dụng self-proxy hoặc bytecode weaving khi có lý do kỹ thuật xác đáng.
11. Kiểm thử hành vi advice trong context thật; kiểm tra proxy bằng `AopUtils` khi cần.
12. Khi gặp lỗi, xác định **proxy type → method visibility/finality → Spring bean ownership → đường gọi → advisor/pointcut → lifecycle** trước khi sửa annotation.

**Kết luận:** Giới hạn với `final`, `private` và những phương thức không thể can thiệp xuất phát từ cơ chế proxy của Spring AOP, không phải do Spring “bỏ qua annotation một cách ngẫu nhiên”. Một class-based proxy không thể kế thừa final class hoặc override final/private method; JDK proxy chỉ chặn lời gọi qua interface; self-invocation và constructor/static call không đi qua proxy. Thiết kế đúng điểm giao tiếp giữa các bean và chọn cơ chế transaction/AOP phù hợp sẽ giúp hành vi cắt ngang rõ ràng, kiểm thử được và nhất quán khi ứng dụng phát triển.
