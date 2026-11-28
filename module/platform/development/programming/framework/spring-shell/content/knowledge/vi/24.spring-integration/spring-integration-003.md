# Gọi bean có proxy để giữ các cơ chế như transaction hoạt động

Một command Spring Shell có thể gọi repository, service và các thành phần nghiệp vụ giống như những phần còn lại của ứng dụng Spring. Điểm quan trọng là các đối tượng này phải được Spring quản lý và lời gọi phải đi qua bean reference mà container cung cấp. Khi một bean có `@Transactional`, `@Async`, `@Cacheable` hoặc một cơ chế AOP khác, Spring có thể bọc bean đích bằng proxy để thực hiện hành vi bổ sung trước hoặc sau lời gọi phương thức.

Nếu command tự tạo service bằng `new`, nó nhận một đối tượng Java thông thường, không phải proxy do Spring quản lý. Nếu một phương thức trong cùng bean gọi phương thức khác bằng `this`, lời gọi nội bộ cũng bỏ qua proxy trong chế độ proxy mặc định. Vì vậy, annotation có thể vẫn xuất hiện trong mã nguồn nhưng advice tương ứng không chạy ở lần gọi đó.

Với Spring Shell 3.x, lớp `@ShellComponent` là một Spring component và có thể dùng constructor injection. Một command nên nhận service qua constructor, sau đó gọi phương thức nghiệp vụ trên bean được inject. Khi service được cấu hình transaction đúng cách, lời gọi từ command đi qua proxy và transaction interceptor có thể mở, commit hoặc rollback transaction.

Bài này giúp bạn:

- Hiểu vì sao Spring AOP cần proxy và interceptor để áp dụng transaction.
- Gọi service từ command bằng constructor injection.
- Phân biệt Spring-managed bean, target object và proxy reference.
- Nhận biết các trường hợp `new`, `this` và self-invocation làm bỏ qua proxy.
- Đặt ranh giới transaction ở service nghiệp vụ.
- Hiểu khác biệt cơ bản giữa JDK dynamic proxy và CGLIB proxy.
- Kiểm tra transaction và proxy trong runtime.
- Xử lý rollback, checked exception và lời gọi chạy trên thread khác.

> Ví dụ tập trung vào Spring Shell 3.3.x, Spring Boot 3.3.x và Spring Framework 6.1.x. Spring Shell 3.3 dùng mô hình legacy `@ShellComponent`, `@ShellMethod` và `@ShellOption`.

## 1. Vì sao command cần gọi bean qua Spring?

Spring Shell đăng ký command từ các bean được Spring quản lý. Với mô hình annotation legacy, `@ShellComponent` là stereotype annotation được meta-annotate bằng `@Component`; phương thức có `@ShellMethod` được Spring Shell nhận diện làm command.

Do đó, command có thể nhận các dependency bằng constructor injection như một Spring component thông thường:

~~~java
@ShellComponent
public class OrderCommands {

    private final OrderService orderService;

    public OrderCommands(OrderService orderService) {
        this.orderService = orderService;
    }

    @ShellMethod(key = "orders create", value = "Tạo một đơn hàng.")
    public String create(
            @ShellOption("--customer-id") long customerId) {
        OrderReceipt receipt = orderService.create(customerId);
        return "Đã tạo đơn hàng " + receipt.orderNumber();
    }
}
~~~

`OrderCommands` không cần biết transaction được mở bằng cách nào. Nó chỉ gọi `OrderService`. Container cung cấp implementation phù hợp cho dependency đó; nếu service được áp dụng transaction advice, reference được inject có thể là proxy.

Luồng lời gọi:

~~~mermaid
flowchart TD
    A[Người dùng gọi orders create] --> B[Spring Shell tìm command bean]
    B --> C[OrderCommands.create]
    C --> D[OrderService reference được inject]
    D --> E[Transaction proxy]
    E --> F[TransactionInterceptor]
    F --> G[PlatformTransactionManager bắt đầu transaction]
    G --> H[OrderService target method]
    H --> I[Repository và các service nghiệp vụ]
    I --> J[Commit hoặc rollback]
    J --> K[Kết quả quay về command]
    K --> L[Spring Shell hiển thị kết quả]
~~~

Proxy nằm giữa caller và target object. Nó nhận lời gọi trước, chạy interceptor phù hợp rồi mới chuyển tiếp tới phương thức thật. Khi phương thức kết thúc, interceptor có thể commit transaction; khi có exception thỏa điều kiện rollback, interceptor yêu cầu transaction manager rollback trước khi exception quay lại caller.

## 2. Phân biệt bean, target object và proxy

Ba khái niệm thường bị gọi chung là “service”, nhưng chúng có vai trò khác nhau:

| Khái niệm | Ý nghĩa |
|---|---|
| Bean | Đối tượng do Spring container tạo hoặc đăng ký và quản lý vòng đời |
| Target object | Đối tượng thực thi logic nghiệp vụ |
| Proxy | Đối tượng trung gian nhận lời gọi và áp dụng các interceptor/advice trước khi chuyển tiếp tới target |

Ví dụ, `DefaultOrderService` là target class. Khi transaction management được bật và bean có phương thức transactional phù hợp, Spring có thể tạo proxy bao quanh target. Command được inject reference mà container công bố, nên lời gọi đi qua proxy.

`@Transactional` chỉ là metadata mô tả chính sách transaction. Chỉ thêm annotation vào một class Java được tạo bằng `new` không làm cho đối tượng đó tự có transaction. Cần có transaction infrastructure và bean phải được quản lý trong application context.

### Tự tạo đối tượng bằng new sẽ bỏ qua container

Ví dụ sai:

~~~java
@ShellComponent
public class OrderCommands {

    @ShellMethod(key = "orders create")
    public String create(long customerId) {
        OrderService service = new DefaultOrderService();
        OrderReceipt receipt = service.create(customerId);
        return receipt.orderNumber();
    }
}
~~~

`new DefaultOrderService()` tạo một target object trực tiếp. Spring không có cơ hội áp dụng dependency injection, transaction interceptor, cache advice hoặc các proxy khác cho instance này. Những dependency của service cũng không được tự động inject.

Dùng constructor injection:

~~~java
@ShellComponent
public class OrderCommands {

    private final OrderService orderService;

    public OrderCommands(OrderService orderService) {
        this.orderService = orderService;
    }

    @ShellMethod(key = "orders create")
    public String create(long customerId) {
        OrderReceipt receipt = orderService.create(customerId);
        return receipt.orderNumber();
    }
}
~~~

Trong ví dụ này, Spring giải quyết `OrderService` từ application context. Nếu bean được proxy, `orderService` là reference cần dùng để đi qua các advice đã cấu hình.

## 3. Đặt transaction ở service nghiệp vụ

Command nên tập trung vào việc nhận option, gọi nghiệp vụ và chuyển kết quả thành nội dung hiển thị. Ranh giới transaction thường phù hợp hơn ở service vì một nghiệp vụ có thể được gọi từ nhiều command hoặc từ các kênh khác như REST API, scheduler hay message listener.

Ví dụ service:

~~~java
public interface OrderService {
    OrderReceipt create(long customerId);
}
~~~

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DefaultOrderService implements OrderService {

    private final OrderRepository orderRepository;
    private final InventoryService inventoryService;

    public DefaultOrderService(
            OrderRepository orderRepository,
            InventoryService inventoryService) {
        this.orderRepository = orderRepository;
        this.inventoryService = inventoryService;
    }

    @Override
    @Transactional
    public OrderReceipt create(long customerId) {
        Order order = Order.newOrder(customerId);
        orderRepository.save(order);
        inventoryService.reserveFor(order);
        return new OrderReceipt(order.getOrderNumber());
    }
}
~~~

Khi `OrderCommands` gọi `orderService.create(customerId)`, lời gọi đi qua proxy của `DefaultOrderService`. Transaction interceptor bắt đầu transaction trước khi gọi target method. Các thao tác repository thực hiện trong cùng transaction nếu chúng tham gia cùng transaction manager và cùng execution context.

Khi phương thức trả kết quả bình thường, interceptor commit transaction trước khi lời gọi trả về command. Nếu phương thức ném runtime exception hoặc error, mặc định Spring rollback transaction rồi truyền exception ra ngoài.

### Transaction manager phải được cấu hình

Để `@Transactional` hoạt động, ứng dụng cần transaction management và một transaction manager phù hợp với công nghệ truy cập dữ liệu.

Với ứng dụng Spring Framework cấu hình thủ công, có thể bật annotation-driven transaction management:

~~~java
@Configuration
@EnableTransactionManagement
public class TransactionConfiguration {
}
~~~

Đồng thời phải có một `PlatformTransactionManager` phù hợp, chẳng hạn `DataSourceTransactionManager` cho JDBC hoặc transaction manager do JPA cung cấp.

Trong Spring Boot, các starter truy cập dữ liệu như `spring-boot-starter-jdbc` hoặc `spring-boot-starter-data-jpa` thường cung cấp auto-configuration cho `DataSource`, repository và transaction manager khi điều kiện cấu hình được đáp ứng. `spring-shell-starter` tự nó không tạo database hoặc transaction manager. Hãy kiểm tra dependency và auto-configuration của ứng dụng trước khi kết luận transaction đã sẵn sàng.

Ví dụ dependency cho ứng dụng dùng JPA:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.shell</groupId>
        <artifactId>spring-shell-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
</dependencies>
~~~

Ví dụ này chỉ minh họa hai nhóm dependency chính. Ứng dụng vẫn cần cấu hình datasource, entity, repository và phiên bản Spring Shell tương thích với Spring Boot đang dùng.

## 4. Điều gì xảy ra khi gọi qua proxy?

Giả sử command gọi:

~~~java
orderService.create(customerId);
~~~

Với transaction proxy, trình tự thường là:

1. Command gọi phương thức trên proxy reference.
2. Proxy tìm các interceptor áp dụng cho phương thức.
3. `TransactionInterceptor` đọc metadata `@Transactional`.
4. Transaction manager bắt đầu hoặc tham gia transaction theo propagation.
5. Proxy gọi phương thức trên target object.
6. Target thực hiện nghiệp vụ và gọi repository.
7. Khi target trả về, interceptor commit transaction.
8. Kết quả trả về command để Spring Shell hiển thị.

Nếu target ném exception, interceptor đánh giá rollback rules. Với mặc định, `RuntimeException` và `Error` làm rollback; checked exception không tự động rollback nếu không cấu hình `rollbackFor`.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant S as Spring Shell
    participant C as OrderCommands
    participant P as OrderService proxy
    participant T as TransactionManager
    participant O as OrderService target
    participant R as Repository
    U->>S: orders create --customer-id 42
    S->>C: create(42)
    C->>P: create(42)
    P->>T: begin/join transaction
    P->>O: create(42)
    O->>R: save(order)
    R-->>O: saved
    O-->>P: OrderReceipt
    P->>T: commit
    P-->>C: OrderReceipt
    C-->>S: message
    S-->>U: Hiển thị kết quả
~~~

Đường đi qua proxy là điều kiện để interceptor được thực thi. Chỉ nhìn thấy annotation trên source code chưa đủ để khẳng định transaction đã bắt đầu.

## 5. Self-invocation: gọi phương thức bằng this

Trong chế độ proxy mặc định, Spring chỉ intercept lời gọi từ bên ngoài đi qua proxy. Khi một phương thức của target gọi một phương thức khác trên chính target bằng `this`, lời gọi không quay lại proxy.

Ví dụ:

~~~java
@Service
public class ImportService {

    public void importAll() {
        // Lời gọi trực tiếp trên target object.
        this.importOne();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void importOne() {
        // Lưu một nhóm dữ liệu.
    }
}
~~~

Nếu caller gọi `importAll()` qua proxy, lời gọi bên ngoài tới `importAll()` có thể được intercept. Nhưng khi `importAll()` gọi `this.importOne()`, proxy không nhận được lời gọi thứ hai. Vì thế `REQUIRES_NEW` trên `importOne()` không được áp dụng cho lần gọi nội bộ này.

Đây là nguyên nhân phổ biến khiến propagation, isolation hoặc rollback rule trên một phương thức không có tác dụng như mong đợi.

### Tách phương thức thành một bean khác

Một cách thiết kế dễ hiểu là đưa đơn vị công việc cần transaction riêng sang service khác:

~~~java
@Service
public class ImportCoordinator {

    private final ImportUnitService importUnitService;

    public ImportCoordinator(ImportUnitService importUnitService) {
        this.importUnitService = importUnitService;
    }

    public void importAll(List<ImportRow> rows) {
        for (ImportRow row : rows) {
            importUnitService.importOne(row);
        }
    }
}
~~~

~~~java
@Service
public class ImportUnitService {

    private final ImportRepository repository;

    public ImportUnitService(ImportRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void importOne(ImportRow row) {
        repository.save(row);
    }
}
~~~

`ImportCoordinator` gọi `ImportUnitService` thông qua dependency được inject. Đây là lời gọi giữa hai bean, nên có thể đi qua proxy của `ImportUnitService`. Mỗi lần gọi có thể mở transaction mới theo `REQUIRES_NEW`.

Spring cũng hỗ trợ self-injection hoặc `AopContext.currentProxy()` trong một số trường hợp, nhưng các cách đó khiến class phụ thuộc chặt vào cơ chế AOP. Tách trách nhiệm thành bean phù hợp thường dễ đọc và kiểm thử hơn.

## 6. JDK dynamic proxy và CGLIB proxy

Spring AOP có hai cách phổ biến để tạo proxy:

| Loại proxy | Cách hoạt động | Điều cần chú ý |
|---|---|---|
| JDK dynamic proxy | Tạo đối tượng proxy thực thi các interface của target | Caller thường nên inject qua interface; chỉ lời gọi qua interface được proxy hỗ trợ |
| CGLIB proxy | Tạo subclass của class đích tại runtime | Không thể override class hoặc method `final`; method `private` không thể được intercept |

Nếu service triển khai interface, Spring có thể sử dụng JDK proxy tùy cấu hình. Nếu dùng class-based proxy, Spring tạo subclass bằng CGLIB. Spring Boot có thể đặt mặc định proxy class-based tùy cấu hình AOP của ứng dụng; không nên dựa vào một kiểu proxy cụ thể nếu thiết kế có thể inject qua interface.

Ví dụ:

~~~java
public interface CustomerService {
    Customer findById(long id);
}

@Service
public class DefaultCustomerService implements CustomerService {

    @Override
    @Transactional(readOnly = true)
    public Customer findById(long id) {
        // Truy vấn dữ liệu.
    }
}
~~~

Command nên phụ thuộc vào `CustomerService`:

~~~java
@ShellComponent
public class CustomerCommands {

    private final CustomerService customerService;

    public CustomerCommands(CustomerService customerService) {
        this.customerService = customerService;
    }
}
~~~

Khi sử dụng JDK proxy, reference được inject có thể không phải là instance của `DefaultCustomerService`. Vì vậy, inject qua interface giúp command không phụ thuộc vào lớp triển khai cụ thể.

### Những method không phù hợp để proxy

- Method `private` không thể được override để CGLIB intercept.
- Method `final` không thể bị override trong class-based proxy.
- Class `final` không thể được CGLIB subclass.
- Với JDK proxy, method cần được gọi qua interface được proxy.
- Nên đặt method transaction ở mức `public` và gọi qua bean reference.

Spring Framework 6 hỗ trợ thêm method `protected` hoặc package-visible cho class-based proxy trong một số cấu hình; tuy nhiên, dùng method `public` giúp hành vi rõ ràng và nhất quán hơn giữa các loại proxy.

## 7. Các cơ chế AOP khác cũng cần lời gọi qua proxy

Transaction là ví dụ dễ thấy, nhưng nguyên tắc gọi bean qua proxy áp dụng cho nhiều cơ chế dựa trên Spring AOP:

| Cơ chế | Tác dụng khi lời gọi được intercept |
|---|---|
| `@Transactional` | Mở, tham gia, commit hoặc rollback transaction |
| `@Cacheable` | Tra cache trước khi chạy method và lưu kết quả theo cấu hình |
| `@CacheEvict` | Xóa cache theo điều kiện |
| `@Async` | Chuyển việc thực thi sang executor được cấu hình |
| `@Retryable` | Thử lại lời gọi khi gặp lỗi thuộc chính sách retry |
| `@PreAuthorize` | Kiểm tra quyền truy cập trước khi chạy method khi method security đã bật |

Các annotation này không tự hoạt động chỉ vì được viết trên method. Bean phải được quản lý, infrastructure tương ứng phải được bật và lời gọi phải đi qua proxy trong chế độ proxy.

### Không giả định transaction tự truyền sang thread khác

Với transaction imperative dùng `PlatformTransactionManager`, trạng thái transaction thường gắn với thread thực thi. Nếu một method transactional khởi chạy công việc trên thread mới, thread mới không tự động tham gia transaction của thread ban đầu.

Ví dụ, `@Async` có thể chuyển method sang executor khác. Không nên giả định một transaction đang mở trong command tự bao phủ toàn bộ công việc bất đồng bộ. Hãy thiết kế transaction riêng cho tác vụ chạy nền hoặc dùng cơ chế điều phối phù hợp với mô hình dữ liệu.

## 8. Rollback và exception khi command gọi service

Mặc định của Spring transaction:

| Loại kết quả từ service method | Hành vi mặc định |
|---|---|
| Trả về bình thường | Commit nếu transaction không bị đánh dấu rollback-only |
| Ném `RuntimeException` | Rollback |
| Ném `Error` | Rollback |
| Ném checked exception | Không tự động rollback |

Nếu checked exception phải làm rollback, khai báo rõ:

~~~java
@Transactional(rollbackFor = ImportFormatException.class)
public void importFile(Path file) throws ImportFormatException {
    // Đọc và lưu dữ liệu.
}
~~~

Command có thể bắt exception sau khi lời gọi service đi qua proxy:

~~~java
@ShellMethod(key = "orders create")
public String create(long customerId) {
    try {
        OrderReceipt receipt = orderService.create(customerId);
        return "Đã tạo đơn hàng " + receipt.orderNumber();
    }
    catch (OrderRejectedException ex) {
        return "Không thể tạo đơn hàng: " + ex.getMessage();
    }
}
~~~

Exception đã đi ra khỏi phương thức transactional và được transaction interceptor xử lý trước khi trở lại command. Vì vậy, command có thể chuyển lỗi thành thông báo thân thiện sau khi rollback đã diễn ra. Nếu service tự bắt exception bên trong transaction rồi trả về bình thường, transaction có thể commit trừ khi code đánh dấu rollback-only hoặc ném exception phù hợp.

## 9. Kiểm tra bean có proxy và transaction có hoạt động

Có thể kiểm tra proxy ở runtime bằng `AopUtils.isAopProxy(...)`:

~~~java
import org.springframework.aop.support.AopUtils;

boolean proxied = AopUtils.isAopProxy(orderService);
~~~

Kết quả `true` cho biết reference là một Spring AOP proxy. Nó chưa chứng minh transaction cụ thể đang hoạt động, vì proxy có thể được tạo cho một advice khác hoặc method được gọi không khớp transaction metadata.

Để kiểm tra transaction bên trong service:

~~~java
import org.springframework.transaction.support.TransactionSynchronizationManager;

public OrderReceipt create(long customerId) {
    boolean active =
            TransactionSynchronizationManager.isActualTransactionActive();

    if (!active) {
        throw new IllegalStateException("Không có transaction đang hoạt động.");
    }

    // Thực hiện nghiệp vụ.
}
~~~

Đoạn kiểm tra này phù hợp cho chẩn đoán hoặc kiểm thử. Trong code nghiệp vụ thông thường, không nên dùng nó thay thế cho thiết kế transaction rõ ràng.

### Kiểm thử rollback qua bean được inject

Một kiểm thử Spring context có thể gọi service bean và xác nhận dữ liệu không được lưu sau runtime exception:

~~~java
@SpringBootTest
class OrderServiceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void rollsBackWhenReservationFails() {
        long before = orderRepository.count();

        assertThatThrownBy(() -> orderService.createWithFailure(42L))
                .isInstanceOf(InventoryUnavailableException.class);

        assertThat(orderRepository.count()).isEqualTo(before);
    }
}
~~~

Trong ví dụ, test gọi reference do Spring inject. Phương thức `createWithFailure` cần lưu một bản ghi rồi ném `InventoryUnavailableException`, một runtime exception. Kiểm tra trạng thái database sau khi exception thoát khỏi service giúp xác nhận transaction proxy đã rollback. Không đánh dấu test method bằng `@Transactional` trong ví dụ này để transaction của test không che khuất ranh giới commit/rollback mà service đang kiểm tra.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `@Transactional` không có tác dụng | Service được tạo bằng `new` hoặc không phải bean Spring | Đăng ký service thành bean và inject từ container |
| Command gọi service nhưng dữ liệu không rollback | Method không được gọi qua proxy, hoặc exception không thỏa rollback rule | Kiểm tra proxy, call path và loại exception |
| Method có `@Transactional` nhưng không mở transaction | Transaction management hoặc transaction manager chưa được cấu hình | Kiểm tra dependency dữ liệu, `PlatformTransactionManager` và transaction infrastructure |
| Method nội bộ không có `REQUIRES_NEW` | Self-invocation bằng `this` bỏ qua proxy | Tách method sang bean khác hoặc gọi qua proxy reference |
| Inject implementation bị lỗi kiểu | Bean được bọc bằng JDK proxy chỉ cung cấp interface | Inject qua interface hoặc cấu hình class-based proxy có chủ đích |
| Method `final` không được intercept | CGLIB không thể override method `final` | Bỏ `final` khỏi method/class cần proxy hoặc chọn thiết kế khác |
| `private` method không chạy advice | Private method không thể được proxy override | Đặt ranh giới advice ở method public được gọi từ bên ngoài |
| Checked exception không rollback | Quy tắc mặc định chỉ rollback `RuntimeException` và `Error` | Khai báo `rollbackFor` nếu nghiệp vụ yêu cầu |
| Command bắt exception nhưng transaction vẫn commit | Exception bị bắt bên trong service trước khi đi qua transaction interceptor | Ném exception ra ngoài hoặc đánh dấu rollback-only |
| Tác vụ `@Async` không nằm trong transaction của command | Công việc chạy trên thread khác | Tạo transaction riêng cho tác vụ bất đồng bộ |
| `AopUtils.isAopProxy` trả `false` | Bean không có advice phù hợp hoặc không được proxy | Kiểm tra bean type, annotation, infrastructure và context scan |

## 11. Checklist tích hợp command với bean có proxy

- Đăng ký command bằng `@ShellComponent` và service bằng `@Service` hoặc `@Bean`.
- Dùng constructor injection cho repository và service.
- Không tự tạo service bằng `new` trong command.
- Đặt transaction boundary tại service nghiệp vụ.
- Bảo đảm transaction manager và annotation-driven transaction management đã được cấu hình.
- Gọi phương thức transactional qua bean reference do Spring inject.
- Tránh self-invocation cho method cần propagation hoặc advice riêng.
- Dùng interface khi muốn command không phụ thuộc loại proxy cụ thể.
- Kiểm tra method visibility và tránh `final`/`private` ở điểm cần proxy.
- Xác định rollback rule cho checked exception.
- Không giả định transaction imperative truyền sang thread mới.
- Kiểm thử bằng Spring context và xác nhận dữ liệu rollback thực tế.

## 12. Bài tập thực hành

Tạo command `orders create --customer-id <id>` với một nghiệp vụ cần ghi dữ liệu:

1. Tạo `OrderCommands` bằng `@ShellComponent`, nhận `OrderService` qua constructor.
2. Tạo `DefaultOrderService` thành bean Spring bằng `@Service`.
3. Khai báo `@Transactional` trên method `create(...)` của service.
4. Gọi repository để lưu đơn hàng và gọi `InventoryService` để giữ tồn kho.
5. Cấu hình transaction manager phù hợp với JDBC hoặc JPA đang sử dụng.
6. Chạy command thành công và xác nhận đơn hàng được lưu.
7. Tạo tình huống `InventoryUnavailableException` sau khi lưu đơn hàng; xác nhận dữ liệu đơn hàng được rollback.
8. Thử thay constructor injection bằng `new DefaultOrderService(...)` và quan sát việc transaction proxy không còn được áp dụng.
9. Tạo một method `@Transactional(propagation = REQUIRES_NEW)` được gọi bằng `this`, sau đó tách method đó sang bean riêng và so sánh hành vi.
10. Dùng `AopUtils.isAopProxy(...)` để kiểm tra reference service được inject.
11. Dùng `TransactionSynchronizationManager.isActualTransactionActive()` trong service để kiểm tra transaction đang hoạt động.
12. Thử một checked exception và cấu hình `rollbackFor` khi nghiệp vụ yêu cầu rollback.

Khi hoàn thành, hãy giải thích đường đi từ command method qua service proxy tới transaction manager và vì sao lời gọi nội bộ trong cùng bean không kích hoạt advice lần thứ hai.

## Tài liệu tham khảo

- [Spring Shell 3.3 – Getting Started](https://docs.spring.io/spring-shell/reference/3.3/getting-started.html): tạo command và sử dụng `@ShellComponent`.
- [Spring Shell 3.3 – Legacy Annotation](https://docs.spring.io/spring-shell/reference/3.3/commands/registration/legacyannotation.html): cách `@ShellComponent` và `@ShellMethod` đăng ký command từ Spring bean.
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): bật transaction management, rollback rule, method visibility và giới hạn self-invocation.
- [Spring Framework – Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK dynamic proxy, CGLIB và cách lời gọi đi qua hoặc bỏ qua proxy.
- [Spring Framework – Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): vai trò của `TransactionInterceptor`, AOP proxy và transaction manager.
- [Spring Framework – EnableTransactionManagement API](https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html): bật annotation-driven transaction management.
- [Spring Framework – Transactional API](https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/transaction/annotation/Transactional.html): thuộc tính transaction, propagation và rollback rules.
