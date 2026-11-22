# Proxy Spring, lời gọi nội bộ và trường hợp giao dịch không được kích hoạt

Trong ứng dụng Spring sử dụng Hibernate/JPA, nhiều lập trình viên chỉ cần thêm `@Transactional` là có thể quản lý commit, rollback và persistence context mà không viết mã `beginTransaction()` hay `commit()` thủ công. Cách làm này rất tiện, nhưng có một điều kiện kiến trúc quan trọng: **khi dùng Spring transaction management ở chế độ proxy mặc định, lời gọi phương thức phải đi qua Spring AOP proxy thì interceptor giao dịch mới có cơ hội hoạt động.**

Một lỗi điển hình:

~~~java
@Service
public class OrderService {

    public void placeOrder(OrderRequest request) {
        saveOrder(request);
    }

    @Transactional
    public void saveOrder(OrderRequest request) {
        // JPA persist, update hoặc query.
    }
}
~~~

Tưởng rằng `saveOrder()` luôn có transaction vì đã đánh dấu `@Transactional`. Nhưng `placeOrder()` gọi nội bộ `this.saveOrder()` trên cùng đối tượng, có thể **đi thẳng vào method của target mà không qua proxy**. Nếu `placeOrder()` không được gọi dưới một transaction có sẵn, phần logic kỳ vọng transaction trong `saveOrder()` có thể không nhận transaction boundary như mong muốn.

Lỗi còn tinh vi hơn khi inner method dùng:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAudit() { ... }
~~~

Nếu gọi nội bộ, Spring không có cơ hội xử lý `REQUIRES_NEW`. Nếu đã có transaction bên ngoài, `writeAudit()` có thể vẫn chạy trong **transaction cũ**, thay vì transaction riêng, và mọi người tưởng đã tách giao dịch thành công.

Bài học này giải thích Spring transaction proxy, lời gọi nội bộ (*self-invocation*), trường hợp `@Transactional` không được kích hoạt, khác biệt proxy JDK/CGLIB, method visibility, propagation, Spring Data JPA/Hibernate, dấu hiệu chẩn đoán, giải pháp thiết kế và cách viết integration test xác nhận transaction behavior.

---

## 1. Cần hiểu @Transactional làm gì

`@Transactional` là metadata mô tả **ý định giao dịch** trên class hoặc method. Trong Spring transaction management với proxy AOP, một transaction interceptor đọc metadata này khi method được gọi qua proxy, rồi phối hợp với một `PlatformTransactionManager` phù hợp để:

1. Quyết định tạo transaction mới, tham gia transaction hiện có, hoặc thay đổi phạm vi theo `Propagation`.
2. Áp dụng những thuộc tính được hỗ trợ như isolation, timeout và read-only.
3. Gọi business method.
4. Khi method hoàn thành, yêu cầu commit hoặc rollback theo outcome và rollback rules.
5. Dọn resources/thread-bound transaction context theo contract của transaction manager.

Ví dụ:

~~~java
@Service
public class PaymentService {

    private final PaymentRepository repository;

    public PaymentService(PaymentRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void capture(Long paymentId) {
        Payment payment = repository.findById(paymentId)
            .orElseThrow();
        payment.capture();
    }
}
~~~

Nếu `capture()` được gọi qua Spring proxy và transaction manager được cấu hình đúng, Hibernate có thể quản lý entity trong persistence context và flush thay đổi khi transaction hoàn thành. Không cần gọi `repository.save(payment)` chỉ để yêu cầu dirty checking trên một managed entity, miễn là mapping và transaction boundaries phù hợp.

### 1.1. @Transactional không phải một keyword Java đặc biệt

Java compiler không tự thêm lệnh begin/commit chỉ vì thấy annotation. Nếu tạo một instance mới bằng `new` hoặc gọi một method không qua interception, annotation có thể không có tác dụng gì.

### 1.2. Một annotation không đồng nghĩa có transaction mới

Ngay cả khi interceptor chạy, kết quả còn phụ thuộc `propagation`:

- `REQUIRED` (mặc định): tham gia transaction hiện có hoặc tạo mới.
- `REQUIRES_NEW`: tạm treo transaction ngoài (nếu có) và mở transaction độc lập.
- `SUPPORTS`: tham gia nếu có, có thể chạy không transaction nếu không có.
- `MANDATORY`: yêu cầu transaction có sẵn, nếu không thì báo lỗi.
- `NOT_SUPPORTED`: chạy không transaction, tạm treo transaction ngoài nếu có.
- `NEVER`: yêu cầu không có transaction.
- `NESTED`: cơ chế savepoint/nested transaction khi manager/resource hỗ trợ.

Vì vậy câu hỏi đúng không chỉ là “annotation có được kích hoạt không?” mà là **interceptor đã xử lý method chưa, transaction có active không, và method đang tham gia transaction nào?**

## 2. Spring AOP proxy là gì?

Khi cấu hình transaction management, Spring có thể tạo một **proxy object** bao quanh bean cần được intercept.

~~~mermaid
sequenceDiagram
    participant C as Controller / Bean khác
    participant P as Spring AOP Proxy
    participant T as OrderService target
    participant TM as TransactionManager
    participant DB as Hibernate / Database

    C->>P: placeOrder(...)
    P->>TM: begin/join theo @Transactional
    P->>T: gọi business method
    T->>DB: entity operations / SQL
    DB-->>T: result
    T-->>P: return
    P->>TM: commit hoặc rollback
    P-->>C: return / exception
~~~

Proxy là đối tượng mà Spring đưa cho các bean khác khi dependency injection, trong mô hình áp dụng AOP tương ứng. Interceptor transaction nằm **trên đường đi qua proxy**.

### 2.1. Đối tượng proxy và target không phải một khái niệm

Thông thường:

- **Proxy:** điểm vào chịu trách nhiệm áp dụng transaction advice, security advice và các interceptor khác.
- **Target:** instance chứa business methods thực sự.

Trong nhiều trường hợp, gọi method qua proxy sẽ đến target. Tuy nhiên, từ bên trong target, từ khóa `this` trỏ về chính target hiện đang chạy, không tự “quay lại” proxy.

### 2.2. Proxy-based AOP chỉ intercept lời gọi phù hợp đi qua proxy

Hai đường gọi:

~~~text
Bean A  --->  proxy(OrderService) ---> TransactionInterceptor ---> target.method()
                                  [@Transactional được xử lý]

target.placeOrder()
   |
   +---- this.saveOrder() ------------------------> target.saveOrder()
                                  [bypass proxy]
~~~

Đó là lý do self-invocation nổi tiếng trong Spring. Cần hiểu **đường đi thực tế của lời gọi**, không chỉ đọc annotations.

### 2.3. Cấu hình @EnableTransactionManagement

Trong ứng dụng Java thuần Spring:

~~~java
@Configuration
@EnableTransactionManagement
public class PersistenceConfig {
    // DataSource, EntityManagerFactory và transaction manager
    // phải được cấu hình phù hợp.
}
~~~

Trong Spring Boot với Spring Data JPA hoặc starter phù hợp, transaction infrastructure thường được auto-configure; không nhất thiết thêm `@EnableTransactionManagement` thủ công.

Nếu transaction management chưa được bật hoặc không có transaction manager thích hợp, có thể thấy annotation không được xử lý hoặc có lỗi cấu hình. Đừng đoán nguyên nhân là self-invocation trước khi xác minh hạ tầng transaction đã hoạt động.

## 3. Lời gọi nội bộ (self-invocation) là gì?

Xét service:

~~~java
@Service
public class InventoryService {

    public void reserveMany(List<ReservationRequest> requests) {
        for (ReservationRequest request : requests) {
            reserveOne(request); // tương đương this.reserveOne(...)
        }
    }

    @Transactional
    public void reserveOne(ReservationRequest request) {
        // Tải Stock, kiểm tra quantity, giảm tồn kho.
    }
}
~~~

Nếu controller gọi `reserveMany()` (không có transaction), method này chạy trên target qua proxy nhưng không có advice transaction cần áp dụng cho `reserveMany()`. Bên trong, `reserveOne()` được gọi qua `this` nên annotation trên `reserveOne()` **không có cơ hội kích hoạt interceptor**.

### 3.1. Vì sao this không tạo lời gọi qua proxy?

Bên trong target, Java method invocation trên `this` gọi trực tiếp method của đối tượng hiện tại. Spring AOP ở proxy không chen vào điểm gọi đó.

Đây không phải lỗi của Hibernate hay JPA. Hibernate chỉ thấy có hoặc không có transaction/persistence context phù hợp được Spring thiết lập.

### 3.2. Cùng class, khác method vẫn là self-invocation

Những kiểu gọi dưới đây có cùng bản chất:

~~~java
public void a() {
    b();
}

public void a() {
    this.b();
}

public void a() {
    helper();
}

private void helper() {
    b();
}
~~~

Chỉ đổi `b()` thành `this.b()` không khắc phục được. Tách một helper private rồi gọi transactional method từ helper private cũng không làm cuộc gọi đi qua proxy.

### 3.3. Self-invocation có thể qua nhiều tầng

Ví dụ:

~~~java
@Service
public class BillingService {

    public void charge() {
        validate();
    }

    private void validate() {
        persistCharge();
    }

    @Transactional
    public void persistCharge() {
        // ...
    }
}
~~~

Dù chain gồm nhiều method, tất cả lời gọi bên trong cùng target vẫn không quay lại proxy.

## 4. Ba tình huống cần phân biệt: không có, có sẵn và giao dịch mới

Chỉ nói “self-invocation khiến transaction không chạy” có thể dẫn tới hiểu nhầm. Hãy phân biệt:

### 4.1. Trường hợp A — Không có transaction bên ngoài

~~~java
@Service
public class OrderService {

    public void checkout(OrderRequest request) {
        save(request); // gọi nội bộ
    }

    @Transactional
    public void save(OrderRequest request) {
        // Thao tác DB.
    }
}
~~~

Nếu `checkout()` được gọi từ controller không có active transaction, `save()` không tự mở transaction vì proxy bị bypass.

Hệ quả có thể bao gồm:

- JPA `flush()`/DML cần transaction báo `TransactionRequiredException`.
- Hibernate entity changes không được commit theo kỳ vọng.
- Một repository method tự mở transaction khác, che giấu lỗi boundary của service.
- Các thao tác được thực hiện qua các transaction riêng rẽ thay vì một transaction nghiệp vụ thống nhất.

### 4.2. Trường hợp B — Transaction đã có ở method ngoài

~~~java
@Service
public class OrderService {

    @Transactional
    public void checkout(OrderRequest request) {
        save(request);
    }

    @Transactional
    public void save(OrderRequest request) {
        // ...
    }
}
~~~

Khi bên ngoài gọi `checkout()` qua proxy, transaction được mở. Lời gọi nội bộ `save()` vẫn bypass interceptor riêng của `save()`, **nhưng body của save vẫn chạy trong transaction đang active do checkout tạo**.

Vì vậy câu “save không có transaction” lúc này **sai**. Chính xác hơn: **annotation trên save không được áp dụng riêng**. Nếu save có cấu hình khác, những cấu hình đó có thể bị bỏ qua.

### 4.3. Trường hợp C — Inner method yêu cầu REQUIRES_NEW

~~~java
@Service
public class OrderService {

    @Transactional
    public void checkout(OrderRequest request) {
        saveOrder(request);
        writeAudit(request); // self-invocation
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(OrderRequest request) {
        // Insert audit row.
    }
}
~~~

Nếu `writeAudit()` được gọi nội bộ, `REQUIRES_NEW` **không được kích hoạt**. Body của `writeAudit()` có thể vẫn sử dụng transaction của `checkout()`.

Nếu `checkout()` rollback, audit row cũng có thể rollback, trái kỳ vọng “audit là transaction riêng”.

### 4.4. Bảng tình huống

| Caller đi qua proxy? | Method ngoài có transaction? | Method trong gọi bằng this? | Kết quả |
| --- | --- | --- | --- |
| Có | Không | Có, inner `@Transactional(REQUIRED)` | Inner annotation bị bypass; có thể không có transaction |
| Có | Có | Có, inner `@Transactional(REQUIRED)` | Chạy trong transaction ngoài; inner advice không chạy |
| Có | Có | Có, inner `@Transactional(REQUIRES_NEW)` | **Không mở transaction mới** |
| Có | Có | Có, inner `@Transactional(NOT_SUPPORTED)` | **Không tạm treo transaction ngoài** |
| Có | Có | Có, inner `@Transactional(MANDATORY)` | Không kiểm tra riêng MANDATORY; body vẫn có thể có transaction ngoài |
| Có | Không | Có, inner `@Transactional(MANDATORY)` | Không báo exception do interceptor của inner; body có thể chạy thiếu transaction |
| Có | Bất kỳ | Không, gọi bean khác qua proxy | Interceptor của target method có thể áp dụng propagation đúng |
| Không | Không | Gọi method annotated trực tiếp trên object mới | Annotation không được proxy xử lý |

Quy tắc ngắn gọn: **Lời gọi nội bộ bypass advice, không nhất thiết bypass một transaction đã active từ trước.**

## 5. Ví dụ nghiệp vụ: đơn hàng và audit phải tách transaction

Giả sử yêu cầu:

- Đặt hàng được thực hiện trong transaction chính.
- Ghi một audit event về nỗ lực đặt hàng phải được lưu độc lập, kể cả khi transaction đặt hàng bị rollback.
- Audit không được làm suy yếu ranh giới transaction của Order.

Một thiết kế **sai kỳ vọng**:

~~~java
@Service
public class CheckoutService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void placeOrder(OrderRequest request) {
        em.persist(Order.create(request));

        writeAudit(request); // self-invocation: REQUIRES_NEW bị bỏ qua.

        verifyBusinessConstraints(request);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(OrderRequest request) {
        em.persist(AuditRecord.forAttempt(request));
    }
}
~~~

Nếu `verifyBusinessConstraints()` ném runtime exception, toàn bộ transaction chính rollback. Vì `writeAudit()` không mở giao dịch riêng, audit cũng có thể bị rollback.

### 5.1. Thiết kế đúng hơn: tách bean

~~~java
@Service
public class AuditWriter {

    private final AuditRepository auditRepository;

    public AuditWriter(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(OrderAttempt attempt) {
        auditRepository.save(AuditRecord.from(attempt));
    }
}
~~~

~~~java
@Service
public class CheckoutService {

    private final OrderRepository orderRepository;
    private final AuditWriter auditWriter;

    public CheckoutService(
            OrderRepository orderRepository,
            AuditWriter auditWriter) {
        this.orderRepository = orderRepository;
        this.auditWriter = auditWriter;
    }

    @Transactional
    public void placeOrder(OrderRequest request) {
        Order order = Order.create(request);
        orderRepository.save(order);

        auditWriter.recordAttempt(
            OrderAttempt.from(order, request)
        );

        verifyBusinessConstraints(order);
    }
}
~~~

Luồng:

~~~mermaid
sequenceDiagram
    participant C as Controller
    participant P as CheckoutService proxy
    participant S as CheckoutService target
    participant A as AuditWriter proxy
    participant DB as Database

    C->>P: placeOrder()
    P->>DB: BEGIN T1
    P->>S: business method
    S->>A: recordAttempt()
    A->>DB: suspend T1; BEGIN T2
    A->>DB: INSERT audit; COMMIT T2
    A-->>S: return
    S->>S: business validation throws
    S-->>P: exception
    P->>DB: ROLLBACK T1
~~~

### 5.2. Lưu ý về audit độc lập

`REQUIRES_NEW` thường cần transaction/connection riêng; transaction ngoài có thể giữ một connection trong lúc transaction trong cần thêm connection. Cần sizing pool phù hợp, nhất là với concurrent requests.

Ngoài ra, một audit “order failed” được ghi **trước khi biết toàn bộ outcome của T1** có thể mang ngữ nghĩa sai. Nếu yêu cầu chỉ phát event **khi order commit**, transactional outbox trong T1 thường phù hợp hơn ghi event bằng REQUIRES_NEW.

Không chọn propagation trước khi xác định chính xác audit/event semantics.

### 5.3. Lỗi trong AuditWriter có thể ảnh hưởng transaction ngoài

Nếu `AuditWriter.recordAttempt()` ném exception và `CheckoutService` không xử lý, exception đi qua proxy của method ngoài, khiến T1 có thể rollback theo rollback rules.

T2 rollback không tự bắt buộc T1 rollback nếu lỗi được bắt và xử lý theo chính sách phù hợp, nhưng business code cần nêu rõ lựa chọn đó. Không dựa vào REQUIRES_NEW như một cơ chế “không thể ảnh hưởng transaction khác”.

## 6. Spring AOP chọn JDK dynamic proxy hoặc class-based proxy

Spring thường dùng một trong hai kiểu proxy:

1. **JDK dynamic proxy:** implement một hoặc nhiều interface.
2. **Class-based proxy (thường dựa trên CGLIB):** tạo subclass của class target để intercept các method phù hợp.

Cả hai đều dựa trên đường gọi qua proxy, nên **cả hai đều có giới hạn self-invocation** trong proxy-based mode.

### 6.1. JDK dynamic proxy

Ví dụ interface:

~~~java
public interface OrderOperations {
    void submit(OrderRequest request);
}
~~~

Implementation:

~~~java
@Service
public class OrderService implements OrderOperations {

    @Override
    @Transactional
    public void submit(OrderRequest request) {
        // ...
    }
}
~~~

Proxy JDK implement `OrderOperations`; một bean khác tiêm `OrderOperations` và gọi `submit()` có thể được intercept.

Cần lưu ý:

- Những method **không được expose qua interface proxy** thường không thể gọi qua JDK proxy theo kiểu cast sang implementation.
- JDK proxy không phải subclass của implementation.
- Từ bên trong target, `this.otherMethod()` vẫn bypass proxy.

### 6.2. Class-based/CGLIB proxy

Spring có thể dùng class-based proxy khi phù hợp, đặc biệt trong nhiều cấu hình Boot mặc định.

~~~java
@Service
public class OrderService {

    @Transactional
    public void submit(OrderRequest request) {
        // ...
    }
}
~~~

Proxy là subclass của `OrderService`, có thể intercept những method có thể override và được Spring AOP hỗ trợ.

Giới hạn quan trọng:

- `final class` không thể được subclass theo cách CGLIB thông thường.
- `final method` không thể được override để intercept.
- `private method` không thể được override và không được proxy advice.
- Method không visible với generated subclass theo quy tắc JVM cũng không intercept được.
- Self-invocation trên target vẫn không được giải quyết chỉ bằng cách đổi JDK proxy sang CGLIB.

### 6.3. Chọn class-based proxy có giải quyết self-invocation không?

**Không.** Cấu hình `proxyTargetClass = true` thay kiểu proxy, không biến `this.method()` trong target thành một lời gọi vào proxy.

Ví dụ:

~~~java
@EnableTransactionManagement(proxyTargetClass = true)
@Configuration
public class Config {
}
~~~

có thể buộc class-based proxy trong cấu hình tương ứng, nhưng method gọi nội bộ vẫn cần giải pháp khác.

### 6.4. Proxy type ảnh hưởng DI và cast

Nếu Spring tạo JDK proxy cho interface, code sau có thể không phù hợp:

~~~java
@Autowired
private OrderService concreteType;
~~~

khi bean thực tế là proxy chỉ implement `OrderOperations`. Tiêm interface thường an toàn hơn:

~~~java
@Autowired
private OrderOperations orderOperations;
~~~

Trong class-based proxy, concrete type thường có thể được inject như subclass, nhưng không dùng chi tiết này làm hợp đồng mặc định nếu ứng dụng có thể đổi proxy strategy.

## 7. Method visibility: public, protected, package-private, private

Một hiểu lầm thường gặp là “mọi `@Transactional` trên bất kỳ method nào cũng hoạt động”.

Trong proxy-based Spring, điều đó không đúng.

### 7.1. Public method là lựa chọn an toàn và rõ ràng nhất

~~~java
@Service
public class TransferService {

    @Transactional
    public void transfer(TransferCommand command) {
        // ...
    }
}
~~~

Nếu method được gọi qua Spring proxy và hạ tầng transaction đúng, đây là case dễ hiểu nhất và thường portable qua các proxy strategies.

### 7.2. Private method

~~~java
@Service
public class TransferService {

    public void transfer() {
        debitAndCredit();
    }

    @Transactional
    private void debitAndCredit() {
        // ...
    }
}
~~~

Annotation trên private method **không thể được Spring proxy advice áp dụng** trong cấu hình proxy thông thường. Private method không được override để CGLIB intercept, và không thuộc interface-based proxy entry points.

Nếu transaction boundary ở private helper, chuyển nó lên một public method được gọi qua proxy hoặc tách bean.

### 7.3. Protected và package-private: phụ thuộc phiên bản/proxy

Từ Spring Framework 6, proxy-based transactional support với class-based proxies có thể hỗ trợ `protected` và package-private methods theo default transaction attribute handling trong các trường hợp phù hợp.

Với JDK interface proxies, các phương thức được expose qua interface thường là public. Nếu muốn một thiết kế dễ hiểu xuyên suốt phiên bản/proxy, **dùng public transactional service methods**.

Không phát biểu tuyệt đối rằng “mọi non-public @Transactional đều bị bỏ qua” trong tất cả Spring versions; method visibility rules đã thay đổi ở những phiên bản mới.

### 7.4. Final method/class

~~~java
@Service
public final class FinalService {

    @Transactional
    public void execute() {
        // ...
    }
}
~~~

Class-based proxy không thể subclass final class. Một method `final` cũng không override được. Với JDK dynamic proxies dựa vào interface, cơ chế intercept ở interface entry point khác, nên behavior không nên được suy luận trực tiếp chỉ từ class final.

Vì sự khác biệt đó, tránh áp dụng final vào Spring service classes/methods cần class-based advice, trừ khi đã kiểm chứng rõ proxy strategy.

### 7.5. Kotlin là trường hợp đặc biệt

Trong Kotlin, class và methods **final theo mặc định**. Dự án Spring Kotlin thường dùng plugin `kotlin-spring` / all-open để mở những class mang Spring stereotypes khi cần proxy subclass.

Nếu quên cấu hình, một class Kotlin annotated `@Service` có thể không proxy được theo kỳ vọng, đặc biệt khi không dùng JDK interface proxy. Cần kiểm tra cấu hình build, proxy type và integration tests. Không giả định annotation trên Kotlin method tự vượt giới hạn final.

## 8. Annotation đặt trên interface hay implementation?

Spring có thể phát hiện transaction metadata trên class/method trong nhiều tình huống, nhưng **đặt `@Transactional` trên concrete implementation class/method thường rõ ràng hơn** với proxy modes và tooling.

Ví dụ nên ưu tiên:

~~~java
public interface AccountOperations {
    void transfer(Long from, Long to, BigDecimal amount);
}
~~~

~~~java
@Service
public class AccountService implements AccountOperations {

    @Override
    @Transactional
    public void transfer(
            Long from, Long to, BigDecimal amount) {
        // ...
    }
}
~~~

Không phụ thuộc vào việc mọi Spring AOP/AspectJ configuration đều xử lý annotation chỉ đặt trên interface theo cách giống nhau.

### 8.1. Class-level @Transactional

~~~java
@Service
@Transactional(readOnly = true)
public class CatalogService {

    public ProductView getProduct(Long id) {
        // Read-only transaction expectation.
    }

    @Transactional
    public void changePrice(Long id, BigDecimal price) {
        // Override class-level readOnly rule.
    }
}
~~~

Class-level annotation cho default transaction attributes, method-level annotation có thể override trên method tương ứng khi advice được áp dụng.

Nếu `getProduct()` tự gọi nội bộ `changePrice()`, override tại `changePrice()` **không được áp dụng riêng** qua proxy. Body có thể vẫn chạy trong read-only transaction của `getProduct()`.

### 8.2. Đừng dùng inheritance/overrides mà không kiểm chứng

Transaction attribute resolution có quy tắc ưu tiên class/method/interfaces và ảnh hưởng của proxy strategy. Trong hierarchy phức tạp, luôn kiểm thử method thật sự được intercept và transaction attributes nào có hiệu lực. Tránh thiết kế transaction contract trải đều ở nhiều tầng inheritance khó đọc.

## 9. Object không do Spring quản lý

`@Transactional` chỉ là annotation trên class. Nếu tự tạo:

~~~java
OrderService service = new OrderService(repository);
service.submit(request);
~~~

thì object này không tự có Spring AOP proxy. Không có lý do để transaction interceptor chạy chỉ vì method có annotation.

Tương tự:

- Object được tạo trong static factory ngoài container.
- Helper được khởi tạo bằng `new` trong service.
- Class nhận dependency thủ công nhưng không là bean Spring.
- JPA entity hoặc DTO có method `@Transactional` mà không được proxy quản lý.
- Một instance lấy từ cơ chế không đi qua Spring proxy.

### 9.1. Quy tắc thiết kế

Đặt transaction boundary ở **application/service layer Spring-managed**, rồi đưa domain entities qua transaction đó. Entity không nên tự quyết định mở transaction của mình.

### 9.2. Không nên tạo proxy thủ công để né kiến trúc

Spring có `ProxyFactory` và nhiều extension AOP, nhưng chỉ nên dùng khi thực sự xây hạ tầng. Đối với code ứng dụng, tách service beans hoặc dùng `TransactionTemplate` thường rõ ràng hơn.

## 10. @PostConstruct và lifecycle initialization

Ví dụ dễ mắc:

~~~java
@Service
public class SeedService {

    @PostConstruct
    public void initialize() {
        seedData(); // self-invocation và lifecycle timing.
    }

    @Transactional
    public void seedData() {
        // Persist seed records.
    }
}
~~~

Vấn đề gồm hai yếu tố:

1. `initialize()` gọi nội bộ `seedData()`, bypass proxy.
2. `@PostConstruct` chạy trong giai đoạn bean initialization; proxy transaction có thể chưa sẵn sàng cho lời gọi qua chính bean theo cách thông thường.

### 10.1. Khắc phục: ApplicationRunner gọi service bean khác

~~~java
@Component
public class SeedRunner implements ApplicationRunner {

    private final SeedWriter writer;

    public SeedRunner(SeedWriter writer) {
        this.writer = writer;
    }

    @Override
    public void run(ApplicationArguments args) {
        writer.seedData();
    }
}
~~~

~~~java
@Service
public class SeedWriter {

    private final ProductRepository repository;

    public SeedWriter(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void seedData() {
        // Write seed data.
    }
}
~~~

Lời gọi `writer.seedData()` qua bean injected có thể đi qua proxy sau khi context được khởi tạo.

### 10.2. Chú ý startup migrations

Dữ liệu seed/migration cần idempotency và không nên tùy tiện chạy mỗi khi app restart. Với schema migration, dùng công cụ như Flyway/Liquibase phù hợp; với business seed, có unique keys và trạng thái version/migration. Transactional proxy chỉ giải quyết boundary, không giải quyết tính lặp an toàn của startup jobs.

## 11. @Async, CompletableFuture và thread boundaries

Spring transaction context thông thường được gắn với thread thực thi. Nếu một method mở transaction rồi khởi tạo task trên thread khác:

~~~java
@Transactional
public void createOrder(OrderRequest request) {
    orderRepository.save(Order.create(request));

    CompletableFuture.runAsync(() -> {
        sendConfirmation(request);
    });
}
~~~

Không được giả định task async tự **kế thừa transaction** của thread gọi. Nó có thể chạy trước khi transaction ngoài commit, hoặc trong một thread không có EntityManager/transaction context cần thiết.

### 11.1. Không chuyển managed entity tùy tiện qua thread

Hibernate `Session`/JPA `EntityManager` không nên được chia sẻ cho nhiều threads song song như một context chung. Nếu task async cần đọc entity, truyền ID hoặc immutable DTO, rồi mở transaction/persistence context riêng trong worker.

### 11.2. @Async cũng là AOP proxy-based trong cấu hình thông dụng

~~~java
@Service
public class NotificationService {

    @Async
    public void sendAsync(Long orderId) {
        // ...
    }
}
~~~

Nếu một method trong cùng bean gọi `this.sendAsync()`, async advice cũng có thể bị bypass và method chạy đồng bộ. Đây là cùng họ vấn đề Spring AOP proxy.

### 11.3. Transaction riêng cho worker async

Một phương án:

~~~java
@Service
public class NotificationWorker {

    @Transactional(readOnly = true)
    public NotificationData loadData(Long orderId) {
        // Return immutable DTO.
        return ...;
    }
}
~~~

Một component async gọi `NotificationWorker` qua Spring-managed bean, mở transaction của thread xử lý. Nếu phải phát thông báo **chỉ sau khi commit order**, cân nhắc `@TransactionalEventListener(phase = AFTER_COMMIT)` hoặc transactional outbox, tùy yêu cầu reliability.

### 11.4. TransactionalEventListener và self-invocation khác vấn đề

`@TransactionalEventListener` có lifecycle gắn với transaction event, không phải giải pháp tự động để bắt mọi lời gọi nội bộ có `@Transactional`. Cần hiểu điều kiện event publish trong transaction và semantics nếu event phát ở ngoài transaction; thêm outbox khi cần bảo đảm delivery/retry bền vững.

## 12. Spring Data JPA có thể che giấu lỗi boundary

Một trường hợp đặc biệt nguy hiểm là service method `@Transactional` bị bypass nhưng repository method vẫn tự mở transaction.

Ví dụ:

~~~java
@Service
public class CheckoutService {

    private final OrderRepository repository;

    public CheckoutService(OrderRepository repository) {
        this.repository = repository;
    }

    public void checkout(OrderRequest request) {
        saveInternal(request); // self-invocation.
    }

    @Transactional
    public void saveInternal(OrderRequest request) {
        repository.save(Order.create(request));
        repository.save(OrderLog.create(request));
    }
}
~~~

Nhiều Spring Data JPA repository methods có transaction metadata mặc định, thường trên implementation `SimpleJpaRepository`. Nếu service transaction không được kích hoạt, từng `save()` có thể tạo hoặc tham gia **transaction riêng**, khiến một lệnh thành công rồi lệnh sau lỗi và rollback — nhưng lệnh trước đã commit.

### 12.1. Vì sao test có thể vẫn thấy dữ liệu được lưu?

Vì repository `save()` tự có transaction nên thao tác vẫn được ghi. Điều đó không chứng minh **hai save cùng atomic transaction**.

### 12.2. Kiểm thử atomicity, không chỉ số lượng rows

Một test tốt:

1. Gọi public service API theo đường thực tế từ controller hoặc bean khác.
2. Để operation thứ nhất ghi thành công.
3. Cố tình tạo exception ở operation thứ hai.
4. Kiểm tra cả hai thay đổi có rollback theo yêu cầu hay không.
5. Xác nhận transaction boundary bằng diagnostics nếu cần.

Nếu chỉ test “save một Order thành công”, self-invocation có thể bị bỏ qua mà test vẫn xanh.

### 12.3. Repository method là proxy riêng

Một service method bypass transaction advice **không đồng nghĩa mọi lời gọi repository sau đó đều không có advice**. Repository là bean Spring proxy khác; các method của repository có thể áp transaction của chính chúng.

Đây là lý do cần mô tả **transaction của toàn use case**, không đoán chỉ từ một annotation.

## 13. Cấu hình propagation khi self-invocation

Mỗi propagation có rủi ro khác khi không được advice:

| Propagation trên inner method | Ý định khi gọi qua proxy | Khi gọi qua this |
| --- | --- | --- |
| `REQUIRED` | Join/create transaction | Không tự tạo transaction; chỉ dùng transaction đã tồn tại |
| `REQUIRES_NEW` | Suspend outer, mở transaction mới | Không suspend; body có thể chạy trong outer |
| `MANDATORY` | Lỗi nếu không có transaction | Check không chạy; có thể thiếu transaction mà không báo đúng lúc |
| `SUPPORTS` | Join nếu có, không có thì chạy non-transactional | Không áp metadata riêng; dùng context hiện tại |
| `NOT_SUPPORTED` | Suspend transaction ngoài, chạy không transaction | Không suspend; body có thể chạy trong outer |
| `NEVER` | Báo lỗi khi có transaction | Check không chạy; body có thể chạy trong transaction ngoài |
| `NESTED` | Tạo savepoint nếu supported | Không tạo nested/savepoint mới |
| `REQUIRED(readOnly=true)` | Tham gia/tạo transaction với hint phù hợp | Hint inner không được áp riêng |
| `REQUIRED(timeout=...)` | Áp timeout khi tạo transaction phù hợp | Timeout inner không được thiết lập riêng |

**Lưu ý:** Khi một method `REQUIRED` tham gia transaction đang có, một số attributes của inner method không nhất thiết thay đổi transaction vật lý đã tạo (ví dụ isolation/read-only của transaction ngoài). Nhưng với self-invocation, interceptor inner còn không chạy, nên các propagation checks/validation cũng bị bypass. Cần phân biệt hai hiện tượng.

## 14. @Transactional(readOnly = true) không phải database write protection tuyệt đối

Một code path:

~~~java
@Service
@Transactional(readOnly = true)
public class CatalogService {

    public ProductView show(Long id) {
        adjustCounter(id); // self-invocation.
        return loadView(id);
    }

    @Transactional
    public void adjustCounter(Long id) {
        // Update statistics.
    }
}
~~~

Nếu `show()` được gọi qua proxy, read-only transaction của method ngoài có thể được tạo. `adjustCounter()` gọi nội bộ không được áp override `@Transactional`.

Trong Spring + Hibernate, `readOnly=true` thường là hint được transaction manager/ORM sử dụng để tối ưu flush/dirty checking trong những điều kiện phù hợp. Nó **không bảo đảm** mọi database sẽ từ chối SQL UPDATE, cũng không bảo đảm mỗi loại query có cùng behavior.

Vì vậy:

- Không dùng readOnly làm cơ chế phân quyền ghi dữ liệu.
- Không kỳ vọng annotation inner “tắt readOnly” nếu bị self-invocation.
- Nếu cần write transaction, thiết kế public write boundary riêng được gọi qua proxy.

## 15. Rollback rules và checked exceptions

Mặc định trong Spring proxy-based transaction management truyền thống, `@Transactional` rollback khi method ném:

- `RuntimeException`.
- `Error`.

**Checked exception** thường không kích hoạt rollback mặc định nếu không cấu hình thêm.

~~~java
@Transactional(rollbackFor = IOException.class)
public void importFile(InputStream input) throws IOException {
    // ...
}
~~~

### 15.1. Khi self-invocation, rollbackFor inner bị bỏ qua

~~~java
@Transactional
public void run() throws IOException {
    parseAndWrite();
}

@Transactional(rollbackFor = IOException.class)
public void parseAndWrite() throws IOException {
    // ...
}
~~~

Nếu `parseAndWrite()` gọi nội bộ từ `run()`, rule `rollbackFor = IOException.class` trên inner không được áp dụng. Nếu checked `IOException` thoát ra khỏi `run()` và outer transaction chỉ có rollback rule mặc định, outer transaction có thể **commit** (hoặc vẫn rollback vì lý do khác), trái kỳ vọng.

Cách sửa là đặt rollback rule đúng tại **public boundary thực sự được intercept**, hoặc tách method sang bean riêng.

### 15.2. Bắt exception rồi không throw làm thay đổi outcome

~~~java
@Transactional
public void process() {
    try {
        repository.save(entity);
        externalOperation();
    } catch (RuntimeException ex) {
        log.warn("Ignored", ex);
    }
}
~~~

Nếu exception bị nuốt, interceptor của outer method thấy return bình thường và có thể cố commit. Tuy nhiên, nếu một resource/inner transactional method đã đánh dấu transaction rollback-only, commit có thể ném `UnexpectedRollbackException`.

Đừng cố điều khiển rollback chỉ bằng cách bắt hoặc nuốt exception. Phải có transaction policy rõ ràng, xử lý lỗi ở đúng tầng và rollback rule phù hợp.

### 15.3. Không chỉ là self-invocation

Ngay cả lời gọi qua proxy cũng có thể commit khi checked exception thoát ra nếu không có `rollbackFor` hoặc cấu hình rollback khác phù hợp. Khi debug, phân biệt “interceptor không chạy” với “interceptor chạy nhưng rollback policy không như mong đợi”.

## 16. Multiple transaction managers và manager sai

Một ứng dụng có thể có nhiều transaction managers:

- JPA transaction manager cho một EntityManagerFactory.
- JDBC transaction manager cho DataSource khác.
- Transaction manager cho message broker hoặc hệ thống phụ.

Ví dụ:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public void writeOrder() {
    // ...
}
~~~

Nếu bean được gọi qua proxy nhưng manager được chọn không quản lý resource mà code dùng, ta có thể nhìn thấy transaction active nhưng dữ liệu không tham gia cùng boundary mong đợi.

### 16.1. Transaction active không đồng nghĩa đúng database

`TransactionSynchronizationManager.isActualTransactionActive()` cho biết có transaction synchronization/actual transaction theo thông tin thread-bound của Spring. Nó không tự chứng minh đó là **transaction manager đúng cho EntityManagerFactory đang sử dụng**.

Trong hệ thống nhiều datasources, cần xác nhận:

- Qualifier/bean name của transaction manager.
- EntityManagerFactory/DataSource tương ứng.
- Routing datasource và connection binding.
- Đường thực thi thực sự.

### 16.2. Một transaction manager không làm nhiều database atomic mặc định

Một `JpaTransactionManager` quản lý một database không tự tạo distributed ACID transaction trên hai database khác nhau. Nếu use case cần ghi nhiều DB/broker, cần thiết kế outbox/saga hoặc transaction coordination thích hợp.

## 17. Cách sửa 1 — Tách transactional method sang bean riêng

Đây là cách thường được khuyến nghị vì **làm transaction boundary rõ trong kiến trúc**.

Sai:

~~~java
@Service
public class ReportService {

    public void generate() {
        saveBatch();
    }

    @Transactional
    public void saveBatch() {
        // ...
    }
}
~~~

Đúng hơn:

~~~java
@Service
public class ReportBatchWriter {

    @Transactional
    public void saveBatch() {
        // ...
    }
}
~~~

~~~java
@Service
public class ReportService {

    private final ReportBatchWriter writer;

    public ReportService(ReportBatchWriter writer) {
        this.writer = writer;
    }

    public void generate() {
        writer.saveBatch();
    }
}
~~~

Lợi ích:

- `writer.saveBatch()` đi qua injected proxy.
- Transaction scope được đặt tại một service boundary rõ ràng.
- Unit/integration tests có thể trực tiếp gọi bean proxy.
- Giảm coupling vào Spring AOP internals.
- Dễ thay propagation và kiểm tra transaction manager.

### 17.1. Không tách chỉ để “né this” mà làm hỏng domain design

Một bean mới nên có responsibility hợp lý, ví dụ `ImportChunkWriter`, `AuditWriter`, `BillingTransactionService`. Không cần tạo hàng chục bean cực nhỏ không có semantic boundary chỉ vì mỗi method đều gắn annotation. Cân nhắc đặt transaction ở public orchestration method nếu business operation vốn là một transaction thống nhất.

## 18. Cách sửa 2 — Đặt @Transactional ở method ngoài

Nếu mục tiêu thật sự là một transaction cho toàn use case, chuyển annotation lên entry point:

~~~java
@Service
public class RegistrationService {

    @Transactional
    public void register(RegisterCommand command) {
        validate(command);
        createUser(command);
        createProfile(command);
    }

    private void validate(RegisterCommand command) {
        // ...
    }

    private void createUser(RegisterCommand command) {
        // Ghi entity.
    }

    private void createProfile(RegisterCommand command) {
        // Ghi entity.
    }
}
~~~

Các helper private cùng nằm trong transaction của `register()`. Không cần gắn `@Transactional` lên helper, vì transaction boundary là **register operation**.

Ưu điểm:

- Gọn và rõ.
- Bảo đảm atomicity cho toàn use case.
- Không tốn REQUIRES_NEW connections.
- Dễ xác định rollback rules.

Không áp dụng khi một helper thực sự cần transaction độc lập hoặc propagation khác với outer.

### 18.1. Transaction dài có thể phản tác dụng

Không đặt transaction bao quanh toàn bộ HTTP call, xử lý file 30 phút hoặc một chuỗi external API chậm chỉ vì muốn “an toàn”. Transaction dài giữ resources và locks, tăng contention. Hãy tách các bước ngoài DB và transaction boundary đủ ngắn cho nghiệp vụ.

## 19. Cách sửa 3 — TransactionTemplate

Nếu cần điều khiển transaction **bên trong cùng class** mà không dựa vào proxy self-call, dùng programmatic transaction boundary:

~~~java
@Service
public class InventoryImportService {

    private final TransactionTemplate template;
    private final InventoryRepository repository;

    public InventoryImportService(
            PlatformTransactionManager txManager,
            InventoryRepository repository) {
        this.template = new TransactionTemplate(txManager);
        this.repository = repository;

        this.template.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );
    }

    public void importOne(ImportRecord record) {
        template.executeWithoutResult(status -> {
            InventoryItem item = toEntity(record);
            repository.save(item);
        });
    }

    private InventoryItem toEntity(ImportRecord record) {
        // Validate và map input.
        return ...;
    }
}
~~~

Các imports cần thiết gồm:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;
~~~

Ở đây transaction được khởi tạo khi code gọi `template.executeWithoutResult()`, không phụ thuộc method có đi qua Spring proxy hay không.

### 19.1. TransactionTemplate không phải giải pháp cho mọi use case

Nó làm transaction API lộ rõ trong service code, tăng coupling với Spring, nhưng hữu ích khi:

- Cần ranh giới transaction điều kiện.
- Cần tạo transaction per chunk trong vòng lặp.
- Cần phân biệt orchestration và persistence.
- Khó hoặc không hợp lý để tách bean.

Vẫn phải xử lý transaction manager đúng resource, exceptions, rollback, idempotency và các giới hạn của `REQUIRES_NEW`.

### 19.2. TransactionTemplate với per-chunk processing

~~~java
for (List<ImportRecord> chunk : chunks) {
    transactionTemplate.executeWithoutResult(status -> {
        for (ImportRecord record : chunk) {
            entityManager.persist(toEntity(record));
        }
        entityManager.flush();
        entityManager.clear();
    });
}
~~~

Để mỗi `executeWithoutResult` có transaction riêng, kiểm tra propagation của template và không bao toàn bộ loop trong transaction ngoài không mong muốn. Nếu dùng `PROPAGATION_REQUIRED` trong một outer transaction, các calls có thể tham gia cùng outer transaction.

### 19.3. TransactionTemplate callback return không phải “commit đã xong”

Trong `TransactionTemplate.execute(...)`, callback chạy **bên trong transaction**; commit diễn ra sau khi callback trả về và trước khi `execute(...)` trả thành công trong local transaction thông thường. Đừng ghi nhận một trạng thái COMMITTED trong callback dựa chỉ vào flush; nếu cần ledger đồng bộ, ghi cùng transaction hoặc ghi nhận sau khi `execute(...)` return.

## 20. Cách sửa 4 — Gọi qua chính proxy (dùng thận trọng)

Có những kỹ thuật như inject một proxy của chính bean hoặc sử dụng `AopContext.currentProxy()`.

Ví dụ minh họa self-injection:

~~~java
@Service
public class FileService {

    private final FileService selfProxy;

    public FileService(@Lazy FileService selfProxy) {
        this.selfProxy = selfProxy;
    }

    public void importFiles(List<FileInput> files) {
        for (FileInput file : files) {
            selfProxy.importOne(file);
        }
    }

    @Transactional
    public void importOne(FileInput file) {
        // ...
    }
}
~~~

Kỹ thuật này chỉ hoạt động khi bean injection thực sự nhận **Spring proxy phù hợp**; có thể tạo circular dependency/lifecycle complexity và chịu ảnh hưởng proxy type. Một số Spring Boot versions mặc định hạn chế circular references.

**Không coi self-injection là lựa chọn đầu tiên.** Tách bean hoặc `TransactionTemplate` thường rõ ràng và ít bất ngờ hơn.

### 20.1. AopContext.currentProxy()

Ví dụ thường thấy:

~~~java
((FileService) AopContext.currentProxy()).importOne(file);
~~~

Để hoạt động cần expose proxy và có lời gọi hiện tại trong AOP invocation context thích hợp; nó phụ thuộc vào Spring AOP internals, casting/proxy type và cấu hình. Dùng rộng rãi làm business code khó test và coupling mạnh với framework.

Ưu tiên refactor cấu trúc service thay vì dựa vào `AopContext` cho transaction bình thường.

### 20.2. Lời gọi qua applicationContext.getBean()

Lấy chính bean từ `ApplicationContext` rồi gọi method cũng có thể đi qua proxy, nhưng biến business class thành service locator và làm dependency ẩn. Tránh dùng làm cách chữa self-invocation mặc định.

## 21. Cách sửa 5 — AspectJ weaving mode (trường hợp đặc biệt)

Spring transaction management có thể dùng AspectJ-based weaving thay vì proxy interception khi được cấu hình phù hợp.

Trong AspectJ mode, advice có thể được weave vào bytecode, nên **self-invocation có thể được intercept** khi weaving thực sự được áp dụng. Đây là khác biệt quan trọng so với proxy mode.

Ví dụ cấu hình định hướng:

~~~java
@Configuration
@EnableTransactionManagement(
    mode = AdviceMode.ASPECTJ
)
public class TransactionConfig {
}
~~~

Cần các dependency hỗ trợ như `spring-aspects` và cấu hình compile-time hoặc load-time weaving tương ứng. Việc chỉ đổi enum sang `ASPECTJ` **không tự bảo đảm** class đã được weave.

### 21.1. Trade-off của AspectJ

Ưu điểm:

- Có thể xử lý self-invocation theo cơ chế weaving.
- Một số join points không phải public proxy entry points có thể được advice theo cấu hình/khả năng weaving.

Nhược điểm:

- Cấu hình build/runtime phức tạp hơn.
- Cần kiểm chứng class loading/weaving thực sự.
- Tooling và debugging khó hơn.
- Có thể tác động rộng nếu pointcuts được định nghĩa thiếu kiểm soát.
- Team phải hiểu AspectJ lifecycle và môi trường triển khai.

Không chọn AspectJ chỉ để sửa một lời gọi `this.method()` nếu tách bean đơn giản hơn.

### 21.2. Không nhầm AspectJ với CGLIB

- **CGLIB/class-based Spring AOP proxy:** vẫn là proxy; self-invocation thông thường vẫn bypass.
- **AspectJ weaving:** sửa/instrument bytecode theo aspect, có thể bắt được self calls khi thiết lập đúng.

## 22. Gỡ lỗi: kiểm tra bean có phải proxy không

Spring cung cấp tiện ích:

~~~java
import org.springframework.aop.support.AopUtils;

Object bean = applicationContext.getBean(OrderService.class);

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
~~~

**Lưu ý:** Với JDK dynamic proxy, lấy bean bằng concrete implementation type có thể không hợp lệ; có thể lấy bean theo interface type:

~~~java
OrderOperations bean =
    applicationContext.getBean(OrderOperations.class);

System.out.println(AopUtils.isAopProxy(bean));
~~~

### 22.1. isAopProxy(true) chưa chứng minh method được transactional advice

Bean là proxy không có nghĩa **mọi method** đều được advice transaction. Cần xác định:

- Method thực tế có transaction metadata hợp lệ không.
- Method được gọi qua proxy hay self-invocation.
- Proxy type có expose/override method đó không.
- Transaction interceptor đã chạy chưa.
- Transaction manager nào được chọn.
- Cấu hình propagation có tạo transaction mới hay join không.

### 22.2. Dùng AopUtils để chẩn đoán, không phụ thuộc trong nghiệp vụ

Không viết business rule kiểu “nếu bean là CGLIB thì bắt đầu transaction, nếu JDK thì khác”. Proxy type là chi tiết hạ tầng; service contract nên nhất quán và được test.

## 23. Kiểm tra transaction active ngay trong method

Có thể dùng:

~~~java
import org.springframework.transaction.support.TransactionSynchronizationManager;

boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();

boolean synchronizationActive =
    TransactionSynchronizationManager.isSynchronizationActive();

boolean readOnly =
    TransactionSynchronizationManager.isCurrentTransactionReadOnly();
~~~

Đặt log phát triển:

~~~java
public void printTransactionState(String marker) {
    log.info(
        "{}: active={}, readOnly={}, name={}",
        marker,
        TransactionSynchronizationManager.isActualTransactionActive(),
        TransactionSynchronizationManager.isCurrentTransactionReadOnly(),
        TransactionSynchronizationManager.getCurrentTransactionName()
    );
}
~~~

### 23.1. Một ví dụ tự chứng minh self-invocation

~~~java
@Service
public class TransactionProbe {

    public void outer() {
        inner();
    }

    @Transactional
    public void inner() {
        boolean active =
            TransactionSynchronizationManager
                .isActualTransactionActive();

        System.out.println("Transaction active = " + active);
    }
}
~~~

Nếu gọi `outer()` từ bean khác, không có transaction bên ngoài và Spring dùng proxy mode, lời gọi nội bộ `inner()` thường in `false`.

Nếu gọi `inner()` **qua proxy trực tiếp**, method thường chạy trong transaction được tạo bởi interceptor và in `true`.

Nếu gọi `outer()` khi một transaction khác đang active, `inner()` có thể in `true` **dù inner annotation bị bypass**. Vì thế test phải cô lập phạm vi và kiểm tra đúng điều kiện.

### 23.2. TransactionSynchronizationManager không chứng minh transaction mới

`isActualTransactionActive() == true` chỉ xác nhận có transaction active theo Spring context; nó không chứng minh `REQUIRES_NEW` đã tạo transaction độc lập hoặc rằng transaction dùng đúng resource.

Để kiểm tra REQUIRES_NEW, cần một test theo **outcome/commit separation**, hoặc diagnostic có ý thức về transaction manager và transaction identity/connection theo hạ tầng cụ thể.

### 23.3. TransactionName không phải ID độc nhất

`getCurrentTransactionName()` hữu ích cho log, nhưng tên thường dựa trên method và không phải ID giao dịch duy nhất. Không dùng tên để chứng minh hai transactions khác nhau đã được tạo.

## 24. Logging transaction interceptor của Spring

Trong môi trường local/test, có thể tăng log:

~~~yaml
logging:
  level:
    org.springframework.transaction.interceptor: TRACE
    org.springframework.orm.jpa: DEBUG
    org.springframework.jdbc.datasource: DEBUG
    org.hibernate.SQL: DEBUG
~~~

Tùy Spring/Hibernate version và transaction manager, log có thể có thông tin về tạo transaction, join, commit, rollback, SQL hoặc resource handling.

Không phải mọi logger đều in cùng chi tiết ở mọi version. Dùng log cùng test để xác định:

1. Method nào được intercept.
2. Transaction bắt đầu ở đâu.
3. Method nào tham gia transaction hiện có.
4. Rollback/commit được yêu cầu lúc nào.
5. SQL xuất hiện ở thời điểm nào so với flush/commit.

### 24.1. Không bật bind TRACE vô kiểm soát

Hibernate 6 hỗ trợ:

~~~properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Bind log có thể lộ email, số thẻ, token hoặc dữ liệu người dùng. Chỉ bật trong môi trường an toàn hoặc dùng masking/sampling phù hợp.

### 24.2. SQL có UPDATE không chứng minh commit

Hibernate có thể gửi UPDATE ở flush; transaction sau đó vẫn rollback. Nếu test chỉ tìm chuỗi UPDATE trong log rồi báo “giao dịch chạy đúng”, đó là kết luận thiếu bằng chứng.

### 24.3. Query SELECT chạy được không chứng minh write transaction active

Một truy vấn SELECT có thể chạy ngoài transaction theo khả năng ORM/JDBC/driver. Vì vậy test “repository.findById không exception” không đủ chứng minh `@Transactional` đã được áp dụng.

## 25. Integration test phát hiện self-invocation

Ví dụ dùng Spring Boot:

~~~java
@SpringBootTest
class TransactionProbeIT {

    @Autowired
    private TransactionProbe probe;

    @Test
    void externalCallShouldStartTransaction() {
        // Gọi qua injected bean, không new().
        probe.inner();
    }
}
~~~

Đoạn trên chỉ minh họa entry point. Để khẳng định behavior, cần assertion trong method hoặc một test service nhận kết quả transaction state.

Có thể thiết kế probe trả boolean:

~~~java
@Service
public class TransactionProbe {

    public boolean direct() {
        return transactionalMethod();
    }

    @Transactional
    public boolean transactionalMethod() {
        return TransactionSynchronizationManager
            .isActualTransactionActive();
    }
}
~~~

Test:

~~~java
@SpringBootTest
class TransactionProbeIT {

    @Autowired
    TransactionProbe probe;

    @Test
    void directExternalCallIsTransactional() {
        assertThat(probe.transactionalMethod()).isTrue();
    }

    @Test
    void selfInvocationBypassesTransactionalProxy() {
        assertThat(probe.direct()).isFalse();
    }
}
~~~

**Điều kiện test:** Không gắn `@Transactional` trên test class/method, không chạy sẵn trong outer transaction, `TransactionProbe` là Spring-managed proxy, cấu hình transaction manager phù hợp, proxy mode thông thường.

### 25.1. @Transactional trên test có thể che giấu vấn đề

Spring Test có thể tạo transaction cho chính test method:

~~~java
@SpringBootTest
@Transactional
class TransactionProbeIT {
    // ...
}
~~~

Khi đó `probe.direct()` có thể thấy active transaction dù inner annotation bị bypass, vì **test đã mở transaction từ trước**.

Đây là một nguyên nhân phổ biến khiến test “xác nhận transaction active” nhưng production vẫn lỗi.

### 25.2. Spring Data repository có thể che giấu lỗi

Nếu test chỉ kiểm tra `repository.save()` ghi thành công, các method repository có thể tự mở transaction. Cần test **atomicity của toàn service use case**, không chỉ hiệu quả của một repository call.

### 25.3. Test REQUIRES_NEW theo outcome

Một test nghiệp vụ mạnh hơn:

1. Outer service bắt đầu transaction và gọi inner writer.
2. Inner writer lưu một audit row trong `REQUIRES_NEW`.
3. Outer service ném runtime exception để rollback.
4. Đọc DB bằng transaction/EntityManager mới.
5. Audit row phải tồn tại nếu thật sự commit độc lập; order row phải rollback.

Nếu inner writer là self-call, audit thường rollback cùng outer và test sẽ phát hiện sai transaction boundary.

### 25.4. Kiểm tra exceptions tại commit, không chỉ trong body

Khi dùng `@Transactional`, commit thường được thực hiện bởi interceptor sau khi business method trả về. Nếu method body tự catch ngoại lệ để chuyển status, nó có thể không bắt được exception xảy ra ở commit boundary. Test cần gọi **qua proxy** và assert kết quả/exception từ lời gọi ngoài, rồi xác minh trạng thái DB.

## 26. Phân biệt ba loại lỗi thường nhầm nhau

### 26.1. Transaction advice không được kích hoạt

Dấu hiệu:

- `TransactionSynchronizationManager.isActualTransactionActive()` là false ở method kỳ vọng REQUIRED (khi không có outer transaction).
- Transaction interceptor log không hiển thị method đó.
- Method được gọi bằng `this.method()`, object `new` hoặc private method.
- `REQUIRES_NEW` không tạo transaction riêng khi self-invocation.

Giải pháp: sửa đường gọi/proxy/lifecycle hoặc chuyển boundary.

### 26.2. Interceptor có chạy nhưng không tạo transaction mới

Ví dụ:

~~~java
@Transactional(propagation = Propagation.SUPPORTS)
public void readOptional() {
    // ...
}
~~~

Nếu không có transaction hiện có, interceptor có thể xử lý method nhưng chạy không có actual transaction theo semantics SUPPORTS. `isActualTransactionActive() == false` lúc này **không phải bằng chứng proxy bị bypass**.

Tương tự, method `NOT_SUPPORTED` được proxy xử lý đúng có thể cố ý chạy không transaction.

### 26.3. Transaction có chạy nhưng rollback/commit khác kỳ vọng

Nguyên nhân có thể:

- Checked exception mặc định không rollback.
- Exception bị catch/suppressed.
- Inner transaction đánh dấu rollback-only → outer commit gặp `UnexpectedRollbackException`.
- Bulk DML không theo entity lifecycle.
- Sai transaction manager.
- Timeout/isolation/readOnly không đúng contract.
- Lỗi ở flush/commit sau method body.

Cần debug từng tầng, không sửa tất cả bằng `@Transactional` thêm vào nhiều method.

## 27. Hibernate/JPA: persistence context không đồng nghĩa transaction

Trong Spring + JPA, EntityManager/persistence context quản lý entity lifecycle (managed, detached, removed). Transaction xác định commit/rollback và synchronization với database.

Một entity có thể được nạp trong một persistence context, nhưng không phải mọi thao tác đều đảm bảo nằm trong một active transaction theo mong đợi.

### 27.1. Lazy loading không phải bằng chứng transaction

Một ứng dụng bật Open Session in View (OSIV) có thể giữ EntityManager mở xuyên suốt HTTP request để hỗ trợ lazy access tại view layer. Khi đó một lazy getter có thể thực hiện SQL sau service transaction.

Điều này **không chứng minh** service method có active transaction tại thời điểm nghiệp vụ diễn ra. OSIV còn dễ che giấu N+1 ở serialization và boundary lỏng lẻo.

### 27.2. Ghi entity cần transaction rõ

Đối với write use cases, đặt `@Transactional` trên public Spring-managed service boundary hoặc dùng `TransactionTemplate`; kiểm thử rollback/atomicity theo outcome.

### 27.3. Flush timing làm lỗi xuất hiện muộn

~~~java
@Transactional
public void updateOrder(Long id) {
    Order order = repository.findById(id).orElseThrow();
    order.changeStatus(OrderStatus.COMPLETED);
    // Không nhất thiết có SQL ngay tại setter.
}
~~~

Hibernate có thể flush khi commit. Nếu optimistic conflict/constraint lỗi, exception xuất hiện sau phần method body, khi interceptor thực hiện completion.

Không suy luận rằng không có exception tại setter là commit sẽ thành công.

## 28. Propagation.REQUIRES_NEW và resource exhaustion

Một lý do không tùy tiện dùng `REQUIRES_NEW` cho mọi inner method: outer transaction giữ resource của nó khi inner transaction cần resource riêng.

~~~text
Thread 1: T1 giữ connection A → cần T2 connection mới
Thread 2: T1 giữ connection B → cần T2 connection mới
Pool size = 2 → không còn connection cho T2
~~~

Tùy transaction manager/connection pool, điều này có thể dẫn đến starvation hoặc deadlock-like wait.

Với nhiều requests đồng thời, pool cần đủ headroom cho transactions lồng nhau hoặc thiết kế phải tránh mở nested independent transactions không cần thiết.

### 28.1. REQUIRES_NEW không phải savepoint

`REQUIRES_NEW` có transaction vật lý độc lập. `NESTED` thường dùng savepoint trong cùng transaction/resource khi manager hỗ trợ, không phải hai commits độc lập.

`JpaTransactionManager` và JPA semantics không bảo đảm mọi `NESTED` use case hoạt động như JDBC savepoint; cần kiểm tra support và transaction manager cụ thể. Không thay REQUIRES_NEW bằng NESTED mà kỳ vọng cùng commit independence.

## 29. @Transactional và transaction-bound resource trong multi-thread jobs

Với import 100.000 records, một coordinator thường chia chunk:

~~~java
for (List<ImportRecord> chunk : chunks) {
    writeChunk(chunk); // nếu cùng class: có thể bypass REQUIRES_NEW!
}
~~~

Nếu `writeChunk` gắn `@Transactional(REQUIRES_NEW)` nhưng gọi nội bộ, có thể:

- Không tạo transaction nào nếu coordinator không transactional.
- Chạy trong một outer transaction dài nếu coordinator đã transactional.
- Không có checkpoint per-chunk.
- Khi chunk cuối lỗi, rollback cả job thay vì một chunk.
- Khi method repository tự tạo transaction, mỗi save tự commit riêng làm mất atomicity chunk.

Giải pháp thường là một bean `ImportChunkWriter` với public `writeChunk` transactional, hoặc `TransactionTemplate` per chunk. Worker threads không dùng chung EntityManager và nên có connection/transaction riêng.

### 29.1. Batch size không quyết định transaction

`hibernate.jdbc.batch_size = 50` chỉ là grouping JDBC statements, không tự tạo transaction mới mỗi 50 records. Muốn transaction mỗi 500 records phải thiết kế boundary thật; annotation bị self-invocation có thể khiến cả mô hình job sai.

### 29.2. Commit unknown và idempotency

Ngay cả khi `REQUIRES_NEW` áp dụng đúng, một commit có thể thành công nhưng caller bị timeout. Chunk retry phải có business key/idempotency/ledger để tránh duplicate. Proxy transaction không bảo đảm exactly-once processing.

## 30. Một mẫu kiến trúc cho Spring + Hibernate

Đối với hệ thống đặt hàng, một cách tổ chức dễ bảo trì:

~~~text
REST Controller
    |
    v
CheckoutApplicationService (@Transactional)
    |-- OrderRepository
    |-- InventoryRepository
    |-- PaymentPolicy (domain logic)
    |-- OutboxRepository (cùng transaction)
    |
    +-- AuditAttemptWriter (@Transactional(REQUIRES_NEW), bean riêng)
~~~

Phân công trách nhiệm:

- **Controller:** parse request, authentication, response mapping; không gánh transaction boundary phức tạp.
- **Application service:** transaction nghiệp vụ chính, phối hợp repositories và domain model.
- **Domain service/entity:** thực thi business rules, không tùy tiện tự mở transaction.
- **Repository:** persistence operations; không thay thế atomic service boundary.
- **Outbox:** event bền vững cùng transaction với dữ liệu chính khi cần after-commit messaging.
- **Independent writer:** chỉ dùng REQUIRES_NEW khi semantics thật sự đòi transaction độc lập.
- **Async worker:** dùng transaction riêng trên thread riêng và idempotent processing.

Đây là cấu trúc tham khảo, không bắt buộc mọi dự án phải có từng class riêng. Điểm quan trọng là **đường gọi qua proxy và transaction ownership phải rõ**.

## 31. Những anti-pattern cần tránh

| Anti-pattern | Vì sao nguy hiểm | Thay thế |
| --- | --- | --- |
| `this.transactionalMethod()` | Bypass proxy advice | Public outer boundary, tách bean hoặc TransactionTemplate |
| `@Transactional` trên private method | Proxy thông thường không intercept | Đặt trên public service method |
| `@Transactional` trên object tự `new` | Không có Spring proxy | Sử dụng Spring-managed bean |
| Chuyển sang CGLIB để sửa self-call | CGLIB vẫn là proxy | Sửa đường gọi |
| `@Transactional` trong `@PostConstruct` | Lifecycle/proxy chưa phù hợp, thường là self-call | ApplicationRunner + bean khác |
| `REQUIRES_NEW` inner gọi bằng `this` | Không có independent transaction | Call qua proxy bean khác |
| Nuốt exception trong transactional method | Có thể commit sai hoặc rollback-only | Rollback/error policy rõ |
| Chỉ test `isActualTransactionActive()` trong test có `@Transactional` | Test transaction che lỗi | Test không outer transaction |
| Chỉ kiểm tra `repository.save()` thành công | Repository tự mở transaction | Test atomicity nhiều writes |
| Inject concrete type khi proxy là JDK interface | Type không phù hợp | Inject interface |
| Đặt transaction trên Kotlin final class với class proxy không cấu hình | Không subclass/intercept được | kotlin-spring/all-open hoặc interface strategy |
| Xem readOnly là write protection | Hint không phải authorization | Enforce permissions và DB constraints |
| Dùng `AopContext.currentProxy()` khắp domain code | Coupling AOP internals, khó test | Tách bean/TransactionTemplate |
| Gắn @Transactional cho mọi helper | Boundary mơ hồ và dễ self-call | Một public orchestration boundary rõ |
| Transaction bao gồm long-running external calls | Giữ locks/resources quá lâu | Tách steps, outbox/saga |
| `@Async` gọi nội bộ và nghĩ chạy thread khác | Async proxy có thể bị bypass | Gọi async bean qua proxy |

## 32. Quy trình chẩn đoán từng bước

Khi thấy `@Transactional` “không hoạt động”, đi theo thứ tự:

1. **Bean có được Spring quản lý không?** Có `@Service`/`@Component` và được inject hay tạo bằng `new`?
2. **Transaction infrastructure đã bật chưa?** Có transaction manager phù hợp với JPA/DataSource không?
3. **Method được gọi qua proxy không?** Hay `this.method()`, private helper, constructor, `@PostConstruct`?
4. **Proxy type là gì?** JDK interface hay class-based? Method có visible/final không?
5. **Method có @Transactional thực sự được nhận diện không?** Annotation ở class/interface/method nào?
6. **Propagation là gì?** REQUIRED, REQUIRES_NEW, SUPPORTS, NOT_SUPPORTED ...?
7. **Có outer transaction không?** Đặc biệt trong test hoặc caller upstream.
8. **Transaction active của đúng resource không?** Hệ thống có nhiều managers không?
9. **Rollback rule là gì?** Checked exception, catch/swallow, rollback-only?
10. **Flush/commit xảy ra lúc nào?** SQL được gửi không phải bằng chứng commit.
11. **Repository có transaction riêng không?** Có thể che mất boundary service.
12. **Test thực hiện đúng caller path chưa?** Gọi bean qua proxy và assert DB outcome.
13. **Có async/thread hop không?** Transaction thread-bound không tự truyền.
14. **Có dùng OSIV không?** EntityManager mở không chứng minh active transaction.
15. **Nếu REQUIRES_NEW:** audit/inner change có thực sự commit độc lập khi outer rollback không?

Chẩn đoán xong mới chọn refactor: public outer transaction, tách bean, TransactionTemplate hoặc AspectJ weaving phù hợp.

## 33. Bài tập thực hành

### Bài 1 — Self-invocation cơ bản

Một service có `outer()` không annotation gọi `this.inner()` gắn `@Transactional(REQUIRED)`. Không có outer transaction. Khi gọi `outer()` qua proxy, inner có tự mở transaction không? Giải thích.

### Bài 2 — Outer transaction che lỗi

Một service có `outer()` gắn `@Transactional` và gọi `inner()` gắn `@Transactional(REQUIRED)` bằng `this`. Khi inner gọi `isActualTransactionActive()` nhận true. Điều đó chứng minh inner annotation đã chạy chưa?

### Bài 3 — REQUIRES_NEW không hoạt động

`checkout()` transactional gọi `this.writeAudit()` với `REQUIRES_NEW`, sau đó ném exception. Audit row cũng rollback. Viết lại bằng hai beans và giải thích.

### Bài 4 — NOT_SUPPORTED

Outer transaction gọi inner gắn `NOT_SUPPORTED` bằng `this`. Inner có chạy ngoài transaction không? Nếu không, cách sửa?

### Bài 5 — JDK vs CGLIB

Một bean implement interface `PaymentOperations` và Spring dùng JDK dynamic proxy. Tại sao inject concrete class có thể lỗi? Chuyển sang class-based proxy có sửa self-invocation không?

### Bài 6 — Private method

Một private method gắn `@Transactional` được public method gọi. Vì sao proxy mode không intercept private method? Nêu hai giải pháp.

### Bài 7 — Kotlin final

Vì sao Kotlin Spring services có thể gặp lỗi proxy do final class/method? Plugin nào thường được dùng? Khi nào JDK interface proxies làm thay đổi phân tích?

### Bài 8 — @PostConstruct

Một bean gọi transactional method từ `@PostConstruct`. Vì sao không nên dựa vào lời gọi đó để mở transaction? Thiết kế bằng `ApplicationRunner` và bean riêng.

### Bài 9 — Checked exceptions

Outer method `@Transactional` gọi inner method `@Transactional(rollbackFor = IOException.class)` bằng `this`. Inner ném `IOException`. Vì sao outer có thể commit? Cách thay đổi rollback rule?

### Bài 10 — Catch exception

Một transactional service catch RuntimeException rồi return bình thường. Transaction manager có thể làm gì? Khi nào xuất hiện `UnexpectedRollbackException`?

### Bài 11 — Repository che lỗi

Service self-invocation khiến không có transaction bao toàn use case, nhưng hai lần `repository.save()` vẫn ghi được. Vì sao? Viết integration test rollback cả hai thao tác để phát hiện.

### Bài 12 — TransactionTemplate

Viết `TransactionTemplate.executeWithoutResult()` với propagation REQUIRES_NEW để xử lý mỗi chunk; vì sao điều này không phụ thuộc self-invocation?

### Bài 13 — isActualTransactionActive()

Một test class gắn `@Transactional` kiểm tra inner method tự gọi và thấy true. Vì sao test này có thể false positive? Sửa test.

### Bài 14 — Multiple managers

Một service dùng JPA transaction manager A nhưng repository ghi sang DataSource B. Vì sao `isActualTransactionActive() == true` chưa đủ để khẳng định thao tác B thuộc transaction A?

### Bài 15 — OSIV

Lazy getter chạy được trong controller sau service method. Có chứng minh service @Transactional đã được kích hoạt không? Giải thích.

### Bài 16 — Thread hop

Một transactional method gọi `CompletableFuture.runAsync()`, task truy cập managed entity. Những rủi ro nào liên quan EntityManager và transaction context? Đề xuất truyền ID/DTO và mở transaction riêng.

### Bài 17 — AspectJ

AspectJ weaving khác proxy-based Spring AOP thế nào đối với self-invocation? Vì sao chỉ đổi `mode=ASPECTJ` chưa bảo đảm hoạt động?

### Bài 18 — Chuỗi rollback nghiệp vụ

Order transaction T1 gọi AuditWriter T2 (REQUIRES_NEW), T2 commit, T1 rollback. Những row nào còn sau đó? Nếu AuditWriter ném exception chưa được bắt thì kết quả có thể thay đổi thế nào?

### Bài 19 — Debug logs

Bật transaction interceptor TRACE, Hibernate SQL DEBUG; câu UPDATE xuất hiện ở log nhưng transaction rollback. Vì sao log SQL không chứng minh dữ liệu đã commit?

### Bài 20 — Chọn đúng thiết kế

Một batch job cần transaction cho mỗi 500 items. Lập luận nên dùng `@Transactional(REQUIRES_NEW)` trên writer bean hay `TransactionTemplate`, và giải thích vì sao đặt annotation trên method cùng class được gọi bằng `this` là không đủ.

### Gợi ý đáp án

- **Bài 1:** Không; self-invocation bỏ qua proxy transaction advice.
- **Bài 2:** Không; có thể do transaction ngoài đã mở.
- **Bài 3:** Tách AuditWriter thành bean, gọi qua proxy; T2 có thể commit độc lập.
- **Bài 4:** Không; NOT_SUPPORTED không suspend nếu bị self-call; gọi qua proxy/TransactionTemplate.
- **Bài 5:** JDK proxy implement interface không nhất thiết là subclass concrete; CGLIB không sửa self-call.
- **Bài 6:** Private không override/intercept qua proxy; đặt boundary ở public method hoặc tách bean.
- **Bài 7:** Kotlin classes final mặc định; kotlin-spring/all-open hỗ trợ class-based proxy; JDK proxy qua interface có cơ chế khác.
- **Bài 8:** Lifecycle/initialization và self-call làm advice không đáng tin; dùng runner gọi writer proxy.
- **Bài 9:** Rollback rule inner bị bỏ qua; outer cần rollbackFor hoặc thiết kế method boundary lại.
- **Bài 10:** Nếu exception bị nuốt, interceptor có thể cố commit; rollback-only có thể dẫn UnexpectedRollbackException.
- **Bài 11:** Repository có transactional metadata riêng; cần test atomicity của service operation.
- **Bài 12:** TransactionTemplate mở boundary programmatically trong callback.
- **Bài 13:** Test transaction có sẵn che lỗi; test không @Transactional outer và gọi bean qua proxy.
- **Bài 14:** Active transaction không chứng minh đúng resource/manager.
- **Bài 15:** Không; OSIV/persistence context mở khác active transaction.
- **Bài 16:** Transaction thường thread-bound; EntityManager không chia sẻ giữa threads; worker cần context riêng.
- **Bài 17:** Weaving có thể intercept self-call khi thực sự weave; cần dependencies/configuration đúng.
- **Bài 18:** T2 committed có thể còn, T1 rollback; exception chưa bắt có thể kích hoạt rollback T1.
- **Bài 19:** Flush gửi SQL nhưng commit có thể rollback.
- **Bài 20:** Cả writer bean và TransactionTemplate đều có thể đúng; cân nhắc cấu trúc, resource pool và idempotency.

---

## Tóm tắt

**Spring `@Transactional` trong proxy mode chỉ được áp dụng khi method invocation phù hợp đi qua Spring AOP proxy.** Lời gọi nội bộ qua `this.method()` thường bypass advice của method được gọi. Nhưng phải phân biệt:

- **Không có outer transaction:** inner REQUIRED có thể chạy không có transaction.
- **Có outer transaction:** inner chạy trong transaction ngoài, nhưng attributes như REQUIRES_NEW, NOT_SUPPORTED, rollbackFor, timeout hoặc readOnly riêng **không được áp dụng** nếu bypass proxy.
- **Method không proxy được hoặc object không managed:** private/final class-based limitations, `new`, initialization lifecycle và proxy strategy cũng có thể khiến advice không hoạt động.

Giải pháp thường tốt nhất là **đặt transaction trên public entry point thực sự được gọi qua proxy**, hoặc **tách transactional operation sang Spring bean khác**. `TransactionTemplate` phù hợp khi muốn quản lý boundary theo code; AspectJ weaving là lựa chọn đặc biệt cần cấu hình đúng. Không dựa vào việc SQL xuất hiện, repository save thành công hoặc transaction active trong một test có outer transaction để kết luận giao dịch đã hoạt động đúng. Hãy kiểm tra **atomicity, rollback, propagation và database outcome** bằng integration test trên đường gọi thực tế.
