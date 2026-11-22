# An toàn luồng khi Controller xử lý nhiều yêu cầu đồng thời

Trong ứng dụng web MVC, nhiều người dùng có thể gửi request cùng lúc. Một người xem danh sách sản phẩm, người khác cập nhật giỏ hàng, trong khi một người khác đang thanh toán. Máy chủ có thể xử lý các request này trên nhiều luồng thực thi chồng lấp về thời gian. Vì vậy, Controller, service và các đối tượng dùng chung phải được thiết kế để không làm lẫn dữ liệu giữa request, không ghi đè thay đổi của nhau và không phá vỡ quy tắc nghiệp vụ.

Spring MVC thường quản lý Controller dưới dạng singleton bean: một instance được nhiều request sử dụng. Điều đó không có nghĩa là Spring tự tuần tự hóa mọi lời gọi đến Controller. Một handler có thể được nhiều luồng gọi đồng thời. Thiết kế an toàn thường giữ Controller và service không lưu trạng thái request trong field, dùng dữ liệu cục bộ hoặc đối tượng bất biến, và bảo vệ những trạng thái có thể thay đổi bằng cơ chế đồng bộ phù hợp.

## 1. Đồng thời trong ứng dụng web MVC

**Concurrency (đồng thời)** là tình huống nhiều tác vụ có tiến trình thực thi chồng lấp hoặc cùng cần truy cập tài nguyên. **Parallelism (song song)** là khi nhiều tác vụ thực sự chạy cùng thời điểm trên nhiều lõi hoặc bộ xử lý. Một máy chủ web có thể xử lý request đồng thời ngay cả khi một số tác vụ luân phiên trên cùng một lõi.

Trong môi trường Servlet, container thường dùng một nhóm luồng để xử lý request. Khi một request được chuyển đến Spring MVC, DispatcherServlet tìm handler và gọi phương thức Controller trên luồng xử lý tương ứng. Một request khác có thể đồng thời gọi cùng phương thức trên cùng instance Controller.

~~~mermaid
flowchart TD
    R1[Request người dùng A] --> T1[Luồng xử lý 1]
    R2[Request người dùng B] --> T2[Luồng xử lý 2]
    R3[Request người dùng C] --> T3[Luồng xử lý 3]
    T1 --> D[DispatcherServlet]
    T2 --> D
    T3 --> D
    D --> C[Controller singleton]
    C --> S[Service]
    S --> DB[(Cơ sở dữ liệu)]
~~~

Sơ đồ cho thấy nhiều luồng có thể gọi cùng Controller và service. Container quản lý vòng đời request và luồng xử lý, nhưng ứng dụng chịu trách nhiệm bảo vệ trạng thái dùng chung của chính mình.

Một request thông thường có đối tượng request và response riêng. Dữ liệu gắn vào request attribute thường thuộc về request đó. Tuy nhiên, các bean singleton, cache dùng chung, biến static, tài nguyên bên ngoài và HTTP session có thể được nhiều request truy cập đồng thời.

## 2. Vì sao Controller thường là singleton?

Trong Spring, bean mặc định có scope singleton trong ApplicationContext. Spring tạo một instance Controller rồi tái sử dụng instance đó để xử lý nhiều request. Điều này tiết kiệm chi phí khởi tạo và phù hợp với Controller không trạng thái.

Ví dụ Controller an toàn về cấu trúc:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {
    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/products/{id}")
    public ProductResponse detail(@PathVariable long id) {
        Product product = productService.findById(id);
        return ProductResponse.from(product);
    }
}
~~~

Controller chỉ giữ dependency bất biến trong field. ID, product và response là dữ liệu của lần gọi hiện tại, được lưu trong tham số hoặc biến cục bộ. Request A và request B không ghi đè ID của nhau.

Một Controller singleton không có vấn đề chỉ vì nhiều luồng cùng gọi nó. Vấn đề xuất hiện khi các luồng cùng đọc/ghi trạng thái mutable mà không có cơ chế bảo vệ phù hợp.

## 3. Không lưu dữ liệu của request trong field của Controller

Đây là một lỗi phổ biến:

~~~java
@RestController
public class UnsafeReportController {
    private long currentUserId;

    @GetMapping("/reports/{id}")
    public ReportResponse report(
            @PathVariable long id,
            @AuthenticationPrincipal CurrentUser user
    ) {
        currentUserId = user.id();
        Report report = reportService.findForUser(id, currentUserId);
        return ReportResponse.from(report);
    }
}
~~~

Giả sử request A của người dùng 10 gán currentUserId = 10. Trước khi A dùng giá trị đó, request B của người dùng 20 có thể gán currentUserId = 20. Request A khi tiếp tục có thể truy vấn bằng ID của B. Kết quả là dữ liệu sai hoặc nghiêm trọng hơn là rò rỉ dữ liệu giữa người dùng.

Hãy giữ dữ liệu request trong tham số và biến cục bộ:

~~~java
@RestController
public class ReportController {
    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/reports/{id}")
    public ReportResponse report(
            @PathVariable long id,
            @AuthenticationPrincipal CurrentUser user
    ) {
        Report report = reportService.findForUser(id, user.id());
        return ReportResponse.from(report);
    }
}
~~~

Biến cục bộ thuộc lần gọi phương thức. Mỗi lần gọi handler có một khung ngăn xếp riêng, nên request khác không thể ghi trực tiếp vào biến cục bộ của lần gọi đó. Đối tượng mà biến cục bộ tham chiếu đến vẫn có thể là đối tượng dùng chung; vì vậy cần xem xét cả vòng đời và khả năng mutable của đối tượng được tham chiếu.

## 4. Nhận diện trạng thái dùng chung có nguy cơ

Khi xem xét một Controller hoặc service, hãy phân loại dữ liệu:

| Loại dữ liệu | Ví dụ | Cách xử lý |
|---|---|---|
| Tham số request | ID, query, DTO form | Nhận qua tham số handler hoặc đối tượng request |
| Biến cục bộ | Kết quả truy vấn trong một lần gọi | Giữ trong phạm vi phương thức |
| Dependency bất biến | Repository, service, mapper | Tiêm qua constructor, không thay tham chiếu |
| Đối tượng mutable dùng chung | Cache, danh sách, bộ đếm, cấu hình runtime | Dùng cấu trúc đồng thời hoặc cơ chế đồng bộ phù hợp |
| Trạng thái người dùng | Giỏ hàng, lựa chọn, wizard | Phân vùng theo user/session và kiểm soát truy cập |
| Trạng thái bền vững | Đơn hàng, tồn kho, số dư | Bảo vệ bằng transaction và cơ chế đồng thời ở tầng lưu trữ |

Không phải field nào cũng nguy hiểm. Một field final tham chiếu đến service không trạng thái thường phù hợp. Nhưng final chỉ ngăn thay đổi tham chiếu; nó không làm đối tượng được tham chiếu trở thành bất biến hoặc thread-safe.

Ví dụ, một field final chứa ArrayList vẫn có thể bị nhiều luồng thêm hoặc xóa đồng thời. Cần đánh giá hành vi của đối tượng bên trong, không chỉ nhìn từ khóa final.

## 5. Race condition và lost update

Race condition xảy ra khi kết quả phụ thuộc vào thứ tự hoặc thời điểm các luồng truy cập trạng thái dùng chung. Một trường hợp điển hình là lost update: hai request cùng đọc một giá trị cũ, mỗi request tính giá trị mới rồi ghi lại; một thay đổi bị ghi đè.

Giả sử tồn kho hiện tại là 5:

1. Request A đọc tồn kho 5.
2. Request B cũng đọc tồn kho 5.
3. A đặt mua 4 và ghi tồn kho còn 1.
4. B đặt mua 3 dựa trên giá trị cũ 5 và ghi tồn kho còn 2.

Kết quả cuối cùng là 2, dù tổng số lượng đã bán là 7. Hệ thống đã bán nhiều hơn tồn kho ban đầu.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as Inventory
    A->>DB: Đọc available = 5
    B->>DB: Đọc available = 5
    A->>A: Tính 5 - 4 = 1
    B->>B: Tính 5 - 3 = 2
    A->>DB: Ghi available = 1
    B->>DB: Ghi available = 2
    Note over DB: Một lần cập nhật bị ghi đè
~~~

Việc mỗi request có một Controller invocation riêng không ngăn được race condition ở dữ liệu dùng chung. Nếu trạng thái nằm trong cơ sở dữ liệu, cần dùng cơ chế giao dịch và đồng thời phù hợp với yêu cầu nghiệp vụ.

## 6. Thread safety của các cấu trúc dữ liệu trong Java

Các collection thông thường như ArrayList, HashMap và HashSet không được thiết kế để nhiều luồng đọc/ghi tùy ý mà không đồng bộ. Nếu nhiều request cùng thay đổi một collection dùng chung, có thể xảy ra mất cập nhật, dữ liệu không nhất quán hoặc lỗi khi duyệt.

Java có các lựa chọn:

- ConcurrentHashMap cho map dùng chung với thao tác riêng lẻ an toàn đồng thời.
- CopyOnWriteArrayList khi đọc rất nhiều và cập nhật rất ít.
- BlockingQueue cho trao đổi công việc giữa producer và consumer.
- AtomicInteger, AtomicLong cho các phép cập nhật nguyên tử trên một biến đơn.
- synchronized, Lock hoặc cơ chế đồng bộ khác khi một nhóm thao tác phải được thực hiện như một đơn vị.

Từ khóa volatile có thể bảo đảm các luồng nhìn thấy giá trị mới nhất của một biến và tạo quan hệ thứ tự bộ nhớ cần thiết cho những trường hợp phù hợp, chẳng hạn một cờ dừng. Tuy nhiên, volatile không biến thao tác đọc–sửa–ghi như count++ thành nguyên tử và không bảo vệ một bất biến gồm nhiều field. Nếu cần tăng bộ đếm, dùng AtomicLong; nếu cần bảo vệ nhiều bước, dùng khóa hoặc một cơ chế giao dịch phù hợp.

Ví dụ bộ đếm dùng chung:

~~~java
import java.util.concurrent.atomic.AtomicLong;

public final class RequestCounter {
    private final AtomicLong count = new AtomicLong();

    public long increment() {
        return count.incrementAndGet();
    }

    public long current() {
        return count.get();
    }
}
~~~

Nếu dùng long count rồi viết count++, thao tác thực tế gồm đọc, cộng và ghi. Hai luồng có thể cùng đọc một giá trị rồi cùng ghi một kết quả, làm mất một lần tăng. AtomicLong cung cấp thao tác tăng nguyên tử.

Tuy nhiên, cấu trúc đồng thời chỉ bảo đảm các thao tác theo hợp đồng của nó. Ví dụ, if (!map.containsKey(key)) map.put(key, value) vẫn là chuỗi hai thao tác riêng; hai luồng có thể cùng thấy key chưa tồn tại. Dùng putIfAbsent, computeIfAbsent hoặc một vùng đồng bộ phù hợp khi cần hành vi kết hợp.

## 7. Bảo vệ một nhóm thao tác trong bộ nhớ

Khi một bất biến liên quan nhiều field, chỉ dùng atomic cho từng field là chưa đủ. Cần bảo vệ toàn bộ thao tác đọc–kiểm tra–ghi.

Ví dụ bộ giữ chỗ trong bộ nhớ:

~~~java
public final class InMemoryInventory {
    private int available;

    public InMemoryInventory(int initialAvailable) {
        if (initialAvailable < 0) {
            throw new IllegalArgumentException("Tồn kho không hợp lệ");
        }
        this.available = initialAvailable;
    }

    public synchronized boolean reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
        }

        if (available < quantity) {
            return false;
        }

        available -= quantity;
        return true;
    }

    public synchronized int available() {
        return available;
    }
}
~~~

Từ khóa synchronized bảo đảm chỉ một luồng tại một thời điểm thực hiện phần thân các phương thức đồng bộ trên cùng instance. Việc kiểm tra tồn kho và giảm số lượng nằm trong cùng vùng bảo vệ, nên hai request không thể đồng thời vượt qua kiểm tra dựa trên cùng một giá trị cũ.

Ví dụ này chỉ bảo vệ một instance trong một tiến trình JVM. Nếu ứng dụng chạy nhiều instance hoặc dữ liệu nằm trong cơ sở dữ liệu, synchronized không bảo vệ được các tiến trình khác. Khi đó, cần cơ chế đồng thời tại tầng lưu trữ hoặc một dịch vụ điều phối dùng chung.

Không nên khóa quá rộng. Nếu giữ khóa trong khi gọi API bên ngoài hoặc thực hiện truy vấn mạng chậm, các request khác phải chờ lâu và thông lượng giảm. Hãy giữ vùng khóa ngắn, chỉ bao quanh thao tác cần bảo vệ.

## 8. Service singleton cũng phải được thiết kế an toàn

Controller thường gọi application service hoặc domain service. Nếu service là singleton và giữ trạng thái mutable theo request, lỗi tương tự vẫn xảy ra dù Controller không có field trạng thái.

Ví dụ service không an toàn:

~~~java
@Service
public class UnsafeCheckoutService {
    private CheckoutCommand currentCommand;

    public Order checkout(CheckoutCommand command) {
        currentCommand = command;
        validate(currentCommand);
        return createOrder(currentCommand);
    }
}
~~~

Hai request có thể ghi đè currentCommand. Hãy truyền dữ liệu qua tham số và giữ service không trạng thái:

~~~java
@Service
public class CheckoutService {
    private final OrderRepository orders;
    private final InventoryService inventory;

    public CheckoutService(
            OrderRepository orders,
            InventoryService inventory
    ) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public Order checkout(CheckoutCommand command) {
        inventory.reserve(command.productId(), command.quantity());
        Order order = Order.create(command);
        return orders.save(order);
    }
}
~~~

Service dùng dependency được tiêm qua constructor và biến cục bộ cho dữ liệu của lần gọi. Đây là cấu trúc dễ kiểm thử và ít có trạng thái chia sẻ cần đồng bộ. Ví dụ vẫn cần bảo đảm InventoryService dùng cơ chế cập nhật tồn kho an toàn ở nơi lưu trữ.

## 9. Transaction không tự động giải quyết mọi race condition

Transaction giúp nhóm các thao tác lưu trữ thành một đơn vị commit hoặc rollback. Nhưng chỉ thêm @Transactional không có nghĩa là hai transaction đồng thời không thể ghi đè nhau. Kết quả còn phụ thuộc isolation level, loại truy vấn, khóa và cách ứng dụng cập nhật dữ liệu.

Ví dụ, hai transaction có thể cùng đọc tồn kho 5 rồi cùng ghi giá trị mới nếu câu lệnh cập nhật không có khóa hoặc điều kiện phiên bản. Transaction có thể bảo đảm mỗi lần ghi là nguyên tử nhưng không tự đảm bảo quy tắc “không bán vượt tồn kho” nếu logic đọc–sửa–ghi vẫn có race.

Các mức isolation thường gặp:

| Isolation | Đặc điểm khái quát | Điều cần cân nhắc |
|---|---|---|
| READ UNCOMMITTED | Có thể đọc dữ liệu chưa commit | Ít dùng cho nghiệp vụ cần độ tin cậy |
| READ COMMITTED | Chỉ đọc dữ liệu đã commit | Một transaction có thể đọc giá trị khác ở lần đọc sau |
| REPEATABLE READ | Các hàng đã đọc có tính ổn định hơn trong transaction | Hành vi cụ thể và phantom phụ thuộc hệ quản trị CSDL |
| SERIALIZABLE | Mục tiêu tương đương thực thi tuần tự | Có thể giảm thông lượng và phát sinh retry khi xung đột |

Tên isolation level có ý nghĩa chuẩn, nhưng hành vi chi tiết và cơ chế triển khai khác nhau giữa các hệ quản trị cơ sở dữ liệu. Hãy dựa vào tài liệu của hệ quản trị đang dùng và kiểm thử bằng tình huống cạnh tranh thực tế.

## 10. Optimistic locking với JPA

Optimistic locking phù hợp khi xung đột không thường xuyên. Entity có trường version; khi cập nhật, JPA kiểm tra phiên bản trong cơ sở dữ liệu có còn khớp phiên bản đã đọc hay không.

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class InventoryItem {
    @Id
    private Long productId;

    private int available;

    @Version
    private long version;

    protected InventoryItem() {
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
        }
        if (available < quantity) {
            throw new InsufficientStockException();
        }
        available -= quantity;
    }
}
~~~

Nếu hai transaction cùng đọc version 7, transaction đầu tiên commit và nâng version lên 8. Transaction còn lại cập nhật với điều kiện version vẫn là 7 sẽ không cập nhật được và nhận lỗi optimistic locking. Ứng dụng có thể yêu cầu client tải lại dữ liệu hoặc thử lại theo chính sách phù hợp.

Không nên tự động retry vô hạn. Nếu nghiệp vụ yêu cầu người dùng xác nhận lại số lượng hoặc giá sau xung đột, hãy trả lỗi xung đột rõ ràng, thường là HTTP 409. Retry tự động chỉ phù hợp khi thao tác có thể thực hiện lại an toàn và giới hạn số lần thử.

## 11. Pessimistic locking và cập nhật có điều kiện

Pessimistic locking khóa dữ liệu trong cơ sở dữ liệu để transaction khác phải chờ hoặc thất bại khi truy cập theo chế độ xung đột. Với JPA, repository có thể khai báo khóa ghi:

~~~java
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select i from InventoryItem i where i.productId = :id")
    Optional<InventoryItem> findForUpdate(@Param("id") long productId);
}
~~~

Service gọi phương thức này bên trong transaction rồi kiểm tra và cập nhật tồn kho. Khóa cần được giữ trong transaction và giải phóng khi transaction kết thúc. Cần chú ý timeout, deadlock và thứ tự lấy nhiều khóa.

Với một phép cập nhật đơn giản, câu SQL có điều kiện có thể hiệu quả hơn đọc rồi ghi:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE product_id = :productId
  AND available >= :quantity;
~~~

Ứng dụng kiểm tra số hàng bị ảnh hưởng. Nếu cập nhật một hàng, việc giữ chỗ thành công; nếu không có hàng nào được cập nhật, sản phẩm không tồn tại hoặc tồn kho không đủ theo điều kiện. Trước khi chạy câu lệnh, vẫn phải xác thực quantity lớn hơn 0 và xử lý phân biệt tài nguyên không tồn tại với hết hàng nếu hợp đồng yêu cầu.

## 12. Scope của Spring và trạng thái theo request/session

Spring hỗ trợ nhiều bean scope. Chọn scope theo vòng đời dữ liệu, nhưng scope không thay thế thiết kế đồng thời.

| Scope | Vòng đời | Lưu ý đồng thời |
|---|---|---|
| singleton | Một instance trong ApplicationContext | Có thể được nhiều request truy cập cùng lúc; tránh trạng thái request mutable |
| prototype | Tạo instance mới mỗi lần container được yêu cầu | Nếu được inject trực tiếp vào singleton, instance được inject thường vẫn là một instance đã tạo lúc singleton khởi tạo |
| request | Một instance cho mỗi HTTP request | Phù hợp dữ liệu gắn với request; không chia sẻ sang request khác |
| session | Một instance cho mỗi HTTP session | Nhiều request/tab cùng session vẫn có thể truy cập đồng thời |
| application | Một instance gắn với ServletContext | Trạng thái dùng chung toàn ứng dụng, cần bảo vệ như singleton |

Có thể dùng @RequestScope cho đối tượng chỉ sống trong một request hoặc @SessionScope cho dữ liệu theo phiên. Khi inject bean scope hẹp hơn vào singleton, Spring thường cần scoped proxy hoặc ObjectProvider để phân giải instance đúng vòng đời.

Đặc biệt, session scope không có nghĩa là chỉ có một request chạy tại một thời điểm. Người dùng có thể mở hai tab và gửi hai request cùng lúc với cùng session. Nếu hai request cập nhật một object mutable trong session, vẫn có thể xảy ra race condition. Hãy dùng cấu trúc bất biến, đồng bộ hóa hoặc cơ chế cập nhật phiên bản phù hợp.

## 13. ThreadLocal không phải giải pháp mặc định cho trạng thái request

ThreadLocal lưu giá trị riêng theo từng luồng, có thể hữu ích cho ngữ cảnh kỹ thuật như một số cơ chế logging. Tuy nhiên, thread pool tái sử dụng luồng cho nhiều request. Nếu không xóa giá trị đúng lúc, dữ liệu của request trước có thể rò sang request sau chạy trên cùng luồng.

Ngoài ra, request có thể chuyển sang luồng khác khi dùng async processing. ThreadLocal không tự truyền dữ liệu sang luồng mới. Vì vậy:

- Ưu tiên truyền dữ liệu cần thiết qua tham số.
- Dùng cơ chế context propagation do framework quản lý khi thực sự cần.
- Nếu tự dùng ThreadLocal, luôn xóa trong finally và kiểm tra hành vi khi request async hoặc dispatch nhiều lần.
- Không dùng ThreadLocal để thay thế authentication/session hoặc để giữ dữ liệu nghiệp vụ.

Spring Security có cơ chế quản lý SecurityContext theo luồng và tích hợp với vòng đời request. Khi dùng async, cần cấu hình cơ chế truyền context phù hợp thay vì giả định ThreadLocal tự đi theo tác vụ.

## 14. Async processing và transaction

Spring MVC có thể xử lý request bất đồng bộ qua Callable, DeferredResult hoặc các cơ chế async khác. Khi công việc chuyển sang luồng khác, cần xem xét:

- Controller/service không được giả định cùng một thread từ đầu đến cuối.
- Biến cục bộ của lần gọi vẫn thuộc invocation, nhưng đối tượng dùng chung vẫn cần thread-safe.
- ThreadLocal và SecurityContext có thể không được truyền tự động nếu không có tích hợp phù hợp.
- Transaction gắn với thread trong các cấu hình Spring thông thường không tự chuyển sang thread khác.
- Tác vụ nền cần mở transaction riêng khi cần truy cập dữ liệu trong transaction.

Ví dụ, một method @Async được gọi sau khi request bắt đầu sẽ chạy trên executor thread. Nếu method đó cần transaction, hãy khai báo ranh giới transaction phù hợp trên method async hoặc service được gọi từ đó. Không dựa vào transaction của thread request ban đầu.

Không giữ transaction hoặc khóa cơ sở dữ liệu trong khi chờ một tác vụ mạng dài nếu không cần thiết. Transaction dài làm tăng thời gian giữ khóa và nguy cơ nghẽn hệ thống.

## 15. Tác dụng phụ bên ngoài và tính idempotent

Request đồng thời không chỉ cạnh tranh dữ liệu trong bộ nhớ hoặc cơ sở dữ liệu. Chúng còn có thể cùng gửi email, gọi cổng thanh toán, tạo hóa đơn hoặc phát sự kiện.

Các biện pháp cần cân nhắc:

- Dùng idempotency key cho thao tác mà client có thể gửi lặp, chẳng hạn tạo thanh toán.
- Lưu kết quả xử lý gắn với key để request lặp nhận lại kết quả đã có thay vì thực hiện tác dụng phụ lần nữa.
- Dùng unique constraint hoặc khóa nghiệp vụ để ngăn tạo bản ghi trùng.
- Chỉ thực hiện tác dụng phụ sau khi dữ liệu chính đã commit khi đó là yêu cầu.
- Dùng Transactional Outbox khi cần ghi sự kiện bền vững cùng transaction nghiệp vụ.
- Thiết kế consumer idempotent vì message broker có thể giao sự kiện nhiều lần.

Redirect sau POST giúp giảm việc trình duyệt gửi lại form khi refresh, nhưng không thay thế idempotency. Hai request POST có thể đến đồng thời trước khi trình duyệt nhận redirect.

## 16. Kiểm thử an toàn luồng

Kiểm thử concurrency cần tạo được tình huống nhiều luồng cùng truy cập trạng thái. Tránh chỉ dùng Thread.sleep để hy vọng race condition xuất hiện; hãy dùng CountDownLatch, CyclicBarrier hoặc executor để điều phối thời điểm bắt đầu.

Ví dụ kiểm thử một bộ giữ chỗ trong bộ nhớ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

class InMemoryInventoryTest {
    @Test
    void concurrentReservationsNeverMakeStockNegative() throws Exception {
        InMemoryInventory inventory = new InMemoryInventory(10);
        int workers = 20;
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(workers);

        try {
            List<Future<Boolean>> results = new ArrayList<>();
            for (int i = 0; i < workers; i++) {
                results.add(pool.submit(() -> {
                    ready.countDown();
                    start.await();
                    return inventory.reserve(1);
                }));
            }

            ready.await();
            start.countDown();

            int successful = 0;
            for (Future<Boolean> result : results) {
                if (result.get()) {
                    successful++;
                }
            }

            assertEquals(10, successful);
            assertEquals(0, inventory.available());
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Ví dụ trên minh họa kiểm thử đồng thời cho một instance trong bộ nhớ. Với cơ sở dữ liệu, cần kiểm thử tích hợp bằng nhiều transaction độc lập cùng cập nhật một bản ghi hoặc cùng đặt hàng. Chạy test trong một transaction duy nhất của test framework có thể không tái hiện đúng cạnh tranh giữa các transaction.

Các tình huống cần kiểm tra:

1. Nhiều request cùng cập nhật một tài nguyên không làm mất thay đổi.
2. Hai request giữ chỗ cùng một lượng tồn kho không thể làm số lượng âm.
3. Cùng một idempotency key không tạo hai giao dịch.
4. Hai session khác nhau không nhìn thấy trạng thái riêng của nhau.
5. Nhiều tab cùng session không ghi đè trạng thái session một cách ngoài ý muốn.
6. Optimistic lock conflict được xử lý và trả kết quả phù hợp.
7. Tác vụ async không phụ thuộc vào transaction hoặc ThreadLocal của request thread.
8. Lỗi giữa các bước không để lại trạng thái dở dang.

## 17. Quan sát lỗi đồng thời trong môi trường chạy

Race condition có thể khó tái hiện. Hãy bổ sung khả năng quan sát phù hợp:

- Log correlation ID hoặc request ID để ghép các dòng log thuộc cùng request.
- Ghi nhận thời gian chờ connection pool, lock timeout và transaction duration.
- Theo dõi lỗi optimistic locking, deadlock, retry và conflict.
- Dùng thread dump khi ứng dụng có nhiều luồng chờ khóa hoặc executor bị nghẽn.
- Theo dõi số lượng tác vụ đang chạy và hàng đợi của executor.
- Không log token, mật khẩu hoặc dữ liệu nhạy cảm chỉ để gỡ lỗi concurrency.

Log cần giúp phân biệt hai request và thứ tự sự kiện mà không làm lộ danh tính hoặc dữ liệu ngoài phạm vi được phép. Với dữ liệu quan trọng, audit event nên có định danh nghiệp vụ và thời điểm commit.

## 18. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Lưu user ID hoặc DTO hiện tại trong field Controller | Request khác ghi đè dữ liệu | Dùng tham số và biến cục bộ |
| Service singleton giữ command mutable | Dữ liệu các lần gọi bị trộn | Thiết kế service không trạng thái |
| Dùng ArrayList/HashMap chung mà không bảo vệ | Race condition và dữ liệu không nhất quán | Dùng collection đồng thời hoặc đồng bộ hóa |
| Nghĩ final đồng nghĩa thread-safe | Đối tượng mutable bên trong vẫn bị thay đổi | Dùng đối tượng bất biến hoặc bảo vệ nội bộ |
| Chỉ thêm @Transactional để giải quyết lost update | Hai transaction vẫn có thể ghi đè nhau | Dùng locking, isolation hoặc cập nhật có điều kiện |
| Dùng synchronized trong một instance để bảo vệ nhiều server | Instance khác không chịu cùng khóa | Bảo vệ tại DB hoặc dịch vụ điều phối chung |
| Nghĩ session scope chỉ có một request | Nhiều tab cùng session vẫn có thể chạy đồng thời | Bảo vệ trạng thái session mutable |
| Dùng ThreadLocal mà không cleanup | Rò dữ liệu sang request khác trên thread pool | Cleanup trong finally hoặc dùng context framework |
| Chuyển sang @Async nhưng trông chờ transaction cũ | Tác vụ chạy ngoài transaction dự kiến | Mở transaction riêng ở ranh giới async |
| Dựa vào PRG để chống request lặp | Hai POST vẫn có thể đến đồng thời | Dùng idempotency key và ràng buộc nghiệp vụ |

## 19. Checklist thiết kế Controller an toàn luồng

Trước khi đưa Controller và service vào môi trường có nhiều request, hãy kiểm tra:

- Controller có đang giữ dữ liệu riêng của request trong field không?
- Field của singleton có tham chiếu đến đối tượng mutable dùng chung không?
- Service có giữ command, user, entity hoặc kết quả của lần gọi trước trong field không?
- Dữ liệu người dùng và request có được truyền qua tham số hoặc context có vòng đời rõ không?
- Collection và cache dùng chung có cơ chế đồng thời phù hợp không?
- Bất biến nhiều field có được bảo vệ như một thao tác nguyên tử không?
- Cập nhật cơ sở dữ liệu có chống lost update và overselling không?
- Transaction và isolation có phù hợp với hệ quản trị CSDL đang dùng không?
- Có cần optimistic lock, pessimistic lock, unique constraint hoặc idempotency key không?
- Session và async processing có được xem xét về nhiều request và nhiều luồng không?
- Kiểm thử có tạo nhiều transaction hoặc luồng cạnh tranh thực sự không?
- Log và metric có đủ để chẩn đoán xung đột mà không làm lộ dữ liệu nhạy cảm không?

Controller an toàn luồng thường là Controller không lưu trạng thái request trong instance dùng chung. Nhưng chỉ làm Controller không trạng thái vẫn chưa đủ: service, cache, session và cơ sở dữ liệu cũng phải có chính sách đồng thời rõ ràng. Hãy bảo vệ dữ liệu tại nơi nó được chia sẻ và đặt cơ chế khóa hoặc transaction sát với bất biến cần duy trì. Điều đó giúp nhiều request được xử lý đồng thời mà không trộn dữ liệu người dùng, mất cập nhật hoặc vi phạm quy tắc nghiệp vụ.
