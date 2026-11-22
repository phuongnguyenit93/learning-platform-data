# Quản lý đồng thời và tính an toàn của trạng thái dùng chung

Một ứng dụng Java serverless có thể tạo nhiều execution environment để xử lý tải tăng lên. Mỗi environment có JVM, bộ nhớ và vòng đời riêng; một số nền tảng còn cho phép nhiều request hoặc invocation chạy đồng thời trong cùng instance. Bên trong một invocation, code cũng có thể tạo thread hoặc xử lý song song nhiều tác vụ. Vì vậy, trạng thái dùng chung có thể bị truy cập đồng thời ở nhiều phạm vi khác nhau.

Một biến `static` trong Java có thể tồn tại qua nhiều lần gọi trên cùng JVM, nhưng không được chia sẻ giữa mọi function instance và cũng không được bảo đảm tồn tại lâu dài. Một khóa `synchronized` có thể bảo vệ dữ liệu giữa các thread trong cùng JVM, nhưng không khóa được một instance khác. Nếu nhầm các phạm vi này, hệ thống có thể ghi đè dữ liệu, trừ tồn kho hai lần, xử lý một event đồng thời hoặc để thông tin của request trước rò sang request sau.

Bài học này giúp phân biệt đồng thời trong một JVM với đồng thời giữa nhiều function instance, chọn cách quản lý trạng thái phù hợp và thiết kế Java handler an toàn khi được mở rộng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vòng đời execution environment và tác động của warm reuse đến biến static.
- Phân biệt trạng thái cục bộ trong JVM với trạng thái dùng chung giữa các instance.
- Nhận diện race condition, vấn đề visibility và cập nhật không nguyên tử trong Java.
- Chọn giữa immutable state, atomic operation, optimistic locking, pessimistic locking và distributed coordination.
- Thiết kế idempotency để bảo vệ side effect khi event hoặc request được xử lý lặp.
- Tái sử dụng client an toàn, giới hạn thread và connection trong function.
- Kiểm thử race condition và quan sát tranh chấp tài nguyên trong môi trường serverless.

## 1. Đồng thời tồn tại ở nhiều phạm vi

Trong FaaS, một function logic có thể được thực thi trên nhiều môi trường độc lập. Khi tải tăng, nền tảng thường tăng số execution environment hoặc instance theo cơ chế scaling của dịch vụ.

~~~mermaid
flowchart TD
    A["HTTP / Queue / Event"] --> B["FaaS platform"]
    B --> C["JVM instance A"]
    B --> D["JVM instance B"]
    B --> E["JVM instance C"]
    C --> F["Database / Shared service"]
    D --> F
    E --> F
~~~

Mỗi JVM có heap, class static, thread và các object riêng. Việc nhiều instance cùng truy cập database hoặc Redis tạo ra đồng thời ở cấp hệ thống, ngay cả khi mỗi JVM chỉ xử lý một invocation tại một thời điểm.

Có thể chia phạm vi đồng thời thành ba lớp:

| Phạm vi | Ví dụ | Cơ chế bảo vệ phù hợp |
|---|---|---|
| Nhiều thread trong một JVM | Hai thread cùng sửa một HashMap | `synchronized`, lock, concurrent collection, atomic class |
| Nhiều invocation trong cùng instance | Runtime cho phép nhiều request đồng thời hoặc handler tự chạy tác vụ song song | Thread-safe object, giới hạn concurrency nội bộ, không dùng request state toàn cục |
| Nhiều function instance hoặc service | Hai JVM cùng cập nhật một sản phẩm hoặc xử lý một event | Database transaction, unique constraint, atomic operation ở dịch vụ dùng chung, distributed coordination |

Không được giả định mọi nền tảng FaaS có cùng mô hình concurrency. Với execution environment tiêu chuẩn của AWS Lambda, mỗi environment xử lý một invocation tại một thời điểm; các lựa chọn compute hoặc runtime khác có thể có mô hình concurrency khác. Một số nền tảng container/function cũng cho phép nhiều request đồng thời trên một instance. Dù runtime tuần tự hóa invocation, code Java vẫn có thể tạo nhiều thread, và nhiều environment vẫn có thể cập nhật cùng một dữ liệu. Hãy kiểm tra concurrency model của đúng loại compute và cấu hình đang dùng.

## 2. Warm reuse và biến static trong Java

Nền tảng có thể tái sử dụng execution environment sau khi một invocation hoàn tất. JVM và các object đã khởi tạo có thể vẫn còn trong bộ nhớ, giúp giảm chi phí khởi tạo ở lần gọi sau. Đây thường được gọi là **warm reuse**.

Ví dụ:

~~~java
public final class RequestCounter {
    private static long count = 0;

    public long handle() {
        count++;
        return count;
    }
}
~~~

Nếu cùng một JVM được tái sử dụng, giá trị count có thể tiếp tục tăng qua các invocation. Nhưng giá trị này:

- Không được chia sẻ với JVM khác.
- Có thể mất khi nền tảng thu hồi environment.
- Có thể bắt đầu lại khi instance mới được tạo.
- Không thể dùng làm số đếm nghiệp vụ hoặc nguồn dữ liệu chuẩn.
- Có thể gặp race condition nếu nhiều thread cùng truy cập.

Vì vậy, static field phù hợp hơn cho cấu hình bất biến hoặc client dùng chung đã được khởi tạo đúng cách. Trạng thái nghiệp vụ như số dư, tồn kho, trạng thái đơn hàng, số lần xử lý event và tiến độ workflow cần được lưu ở dịch vụ bền vững.

### Những gì có thể và không nên giữ trong static field

| Loại dữ liệu | Có thể giữ trong static field? | Lưu ý |
|---|---|---|
| Cấu hình đã parse và bất biến | Có | Không sửa sau khi khởi tạo; không chứa thông tin riêng của request |
| Client SDK thread-safe | Có thể | Xác minh tài liệu client; quản lý timeout và kết nối |
| ObjectMapper đã cấu hình xong | Có thể | Không thay đổi cấu hình trong lúc đang dùng |
| Cache cục bộ có thể tái tạo | Có điều kiện | Chỉ là tối ưu theo từng instance; cần TTL và giới hạn bộ nhớ |
| User ID, tenant ID của request hiện tại | Không | Có thể rò dữ liệu giữa các request |
| Trạng thái đơn hàng hoặc số dư | Không | Cần lưu ở database hoặc dịch vụ trạng thái |
| Bộ đếm cần chính xác toàn hệ thống | Không | Dùng atomic operation hoặc kho dữ liệu dùng chung |

Một cache cục bộ trong JVM có thể hữu ích để giữ metadata ít thay đổi, nhưng không được xem là cache chia sẻ. Nếu cần cache chung giữa nhiều instance, hãy dùng external cache và thiết kế TTL/invalidation như một phần riêng của kiến trúc.

## 3. Race condition và Java Memory Model

**Race condition** xảy ra khi kết quả phụ thuộc vào thứ tự thực thi không được kiểm soát giữa các thread hoặc tiến trình. Một ví dụ quen thuộc là phép tăng biến:

~~~java
count++;
~~~

Phép tăng không phải một thao tác nguyên tử duy nhất. Về khái niệm, nó gồm đọc giá trị, cộng một rồi ghi lại. Nếu hai thread cùng đọc 10 trước khi ghi, cả hai có thể cùng ghi 11; một lần tăng bị mất.

### Visibility và atomicity

Java Memory Model quy định khi nào thay đổi do một thread thực hiện được thread khác nhìn thấy. Hai vấn đề cần phân biệt:

- **Atomicity:** một thao tác có được thực hiện như một đơn vị không thể bị xen giữa hay không.
- **Visibility:** thay đổi do một thread ghi có được thread khác nhìn thấy đúng lúc hay không.

`volatile` giúp bảo đảm visibility và một số quy tắc ordering cho biến, nhưng không biến phép đọc-sửa-ghi như `count++` thành atomic. `synchronized` hoặc lock tạo vùng loại trừ tương hỗ giữa các thread dùng cùng lock trong một JVM. Chúng không phối hợp giữa nhiều JVM.

Ví dụ bộ đếm an toàn giữa các thread trong cùng JVM:

~~~java
import java.util.concurrent.atomic.AtomicLong;

public final class LocalInvocationMetrics {
    private final AtomicLong completed = new AtomicLong();

    public long markCompleted() {
        return completed.incrementAndGet();
    }

    public long currentValue() {
        return completed.get();
    }
}
~~~

AtomicLong bảo vệ thao tác tăng trong một JVM. Nếu có 10 function instance, mỗi instance có một LocalInvocationMetrics riêng; tổng của chúng không phải bộ đếm toàn hệ thống. Để đếm event nghiệp vụ chính xác, hãy dùng atomic counter ở database, Redis hoặc dịch vụ chuyên dụng có semantics phù hợp.

### HashMap không an toàn khi sửa đồng thời

Nếu nhiều thread cùng ghi vào một HashMap, dữ liệu có thể bị mất hoặc cấu trúc map có thể gặp hành vi không được bảo đảm. Có thể dùng ConcurrentHashMap khi cần map chia sẻ giữa thread trong một JVM:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public final class LocalLookup {
    private final ConcurrentMap<String, String> values =
            new ConcurrentHashMap<>();

    public String getOrLoad(String key) {
        return values.computeIfAbsent(key, this::load);
    }

    private String load(String key) {
        return "value-for-" + key;
    }
}
~~~

ConcurrentHashMap chỉ giải quyết truy cập đồng thời trong process. Nó không chia sẻ map giữa các execution environment, không tự cung cấp TTL, eviction theo chính sách nghiệp vụ hay invalidation giữa các instance. Với cache cục bộ thực tế, cần giới hạn kích thước và tuổi dữ liệu.

## 4. Trạng thái request phải có phạm vi rõ ràng

Một lỗi khó phát hiện là lưu thông tin request trong field của singleton hoặc biến static:

~~~java
public final class UnsafeHandler {
    private String currentTenant;

    public String handle(String tenantId) {
        currentTenant = tenantId;
        // Xử lý nghiệp vụ có thể gọi sang nhiều service.
        return currentTenant;
    }
}
~~~

Nếu runtime cho phép hai request chạy đồng thời trên cùng object, request thứ hai có thể ghi đè currentTenant trong lúc request thứ nhất đang xử lý. Request thứ nhất có thể truy cập dữ liệu tenant sai.

Hãy truyền dữ liệu request qua tham số hoặc một object context riêng cho invocation:

~~~java
public record RequestContext(
        String requestId,
        String tenantId,
        String actorId) {
}

public final class SafeOrderService {
    public OrderResult handle(
            RequestContext context,
            CreateOrderCommand command) {
        // Dùng context của lần gọi này; không lưu vào field dùng chung.
        return createForTenant(context.tenantId(), command);
    }

    private OrderResult createForTenant(
            String tenantId,
            CreateOrderCommand command) {
        // Gọi repository với tenant đã xác định.
        return new OrderResult(command.orderId(), "ACCEPTED");
    }
}

public record CreateOrderCommand(String orderId) {
}

public record OrderResult(String orderId, String status) {
}
~~~

Nếu dùng ThreadLocal để gắn context với thread, phải nhớ rằng thread có thể được tái sử dụng. Hãy xóa giá trị trong finally sau khi xử lý. Với async code, ThreadLocal cũng không tự truyền context sang thread khác; dùng cơ chế context propagation phù hợp thay vì giả định request context luôn đi cùng thread.

## 5. Chọn cơ chế đồng bộ hóa theo nơi lưu trạng thái

Không có một lock duy nhất giải quyết mọi phạm vi. Chọn cơ chế dựa trên nơi dữ liệu được lưu và yêu cầu nghiệp vụ.

| Cơ chế | Phạm vi | Phù hợp khi | Giới hạn |
|---|---|---|---|
| `synchronized` / ReentrantLock | Một JVM | Bảo vệ object hoặc cấu trúc dữ liệu trong process | Không khóa instance khác; lock mất khi process kết thúc |
| Atomic class | Một JVM | Bộ đếm hoặc cập nhật biến đơn giản | Không phải transaction cho nhiều field hoặc nhiều instance |
| Database optimistic locking | Nhiều process cùng cập nhật bản ghi | Xung đột không quá thường xuyên; có thể retry | Cần xử lý conflict và retry có giới hạn |
| Database pessimistic locking | Nhiều transaction | Cần khóa bản ghi trong thời gian transaction ngắn | Có thể gây wait, deadlock và giảm throughput |
| Atomic operation ở Redis hoặc database | Nhiều instance | Counter, set-if-absent, conditional update | Phải hiểu durability, expiry và semantics của lệnh |
| Distributed lock | Nhiều instance | Điều phối một công việc độc quyền khi không có cách đơn giản hơn | Cần lease, fencing, xử lý client chết và network partition |

### Optimistic locking

Optimistic locking giả định xung đột ít xảy ra. Bản ghi có một version; khi cập nhật, transaction chỉ thành công nếu version vẫn bằng giá trị đã đọc. Nếu một invocation khác đã cập nhật trước, thao tác hiện tại không cập nhật được và phải đọc lại hoặc retry.

Ví dụ với JPA:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class InventoryItem {
    @Id
    private String productId;

    private int available;

    @Version
    private long version;

    protected InventoryItem() {
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (available < quantity) {
            throw new InsufficientInventoryException();
        }
        available -= quantity;
    }

    public int getAvailable() {
        return available;
    }
}

class InsufficientInventoryException extends RuntimeException {
}
~~~

Khi transaction commit, JPA provider kiểm tra version. Nếu bản ghi đã thay đổi, provider có thể ném OptimisticLockException. Ứng dụng cần xử lý conflict ở ranh giới transaction: đọc lại trạng thái mới, xác định còn đủ hàng không và thử lại một số lần có giới hạn. Không retry vô hạn vì điều đó có thể làm tăng tải khi xung đột đang cao.

### Pessimistic locking

Pessimistic locking khóa bản ghi trong transaction, ví dụ dùng `SELECT ... FOR UPDATE`. Invocation khác cần khóa cùng bản ghi sẽ phải chờ hoặc nhận lỗi timeout.

Cách này phù hợp khi xung đột cao và thao tác cần đọc-sửa-ghi nhất quán. Giữ transaction càng ngắn càng tốt; không gọi API thanh toán hoặc chờ mạng bên ngoài trong lúc giữ database lock. Nếu transaction kéo dài, lock contention và deadlock có thể làm giảm throughput toàn hệ thống.

### Atomic update ở nguồn dữ liệu

Với một thao tác đơn giản, conditional update có thể an toàn và hiệu quả hơn việc đọc rồi ghi tách rời:

~~~sql
UPDATE inventory
SET available = available - :quantity,
    version = version + 1
WHERE product_id = :product_id
  AND available >= :quantity;
~~~

Nếu số dòng cập nhật là 1, lượng hàng đã được giữ thành công. Nếu là 0, sản phẩm không tồn tại hoặc lượng hàng không đủ tại thời điểm cập nhật. Có thể đọc lại để phân biệt hai trường hợp. Vì điều kiện và cập nhật nằm trong một câu lệnh, hai invocation không thể cùng tiêu thụ một lượng tồn kho đã không còn.

## 6. Đồng thời giữa nhiều function instance

Giả sử hai invocation cùng xử lý đơn hàng cuối cùng của một sản phẩm:

1. Instance A đọc available = 1.
2. Instance B đọc available = 1.
3. A kiểm tra đủ hàng.
4. B cũng kiểm tra đủ hàng.
5. A ghi available = 0.
6. B ghi available = 0.

Cả hai đơn có thể được xác nhận dù chỉ còn một sản phẩm. Đây là lost update. Một lock Java trong A không thể ngăn B vì hai instance có hai JVM khác nhau.

Cách giải quyết nên đặt gần dữ liệu chuẩn:

- Dùng conditional update hoặc optimistic/pessimistic locking trong database.
- Dùng atomic decrement hoặc script trong Redis nếu cache/store đó thực sự là nơi quản lý quota/tồn kho và có yêu cầu durability phù hợp.
- Dùng transaction để cập nhật nhiều bản ghi liên quan khi cần tính nguyên tử.
- Dùng queue hoặc partition key để tuần tự hóa các công việc cùng một khóa nghiệp vụ nếu mô hình tải phù hợp.
- Dùng idempotency key để ngăn cùng một yêu cầu nghiệp vụ tạo side effect nhiều lần.

Không dùng static lock hoặc synchronized để bảo vệ tài nguyên dùng chung giữa các instance. Chúng chỉ khóa trong một JVM.

### Distributed lock cần fencing và lease

Distributed lock có thể hữu ích khi một công việc cần được một instance thực hiện tại một thời điểm. Nhưng lock có thể hết hạn trong khi client cũ vẫn đang chạy, ví dụ do pause dài hoặc mất kết nối. Một client mới lấy lock rồi bắt đầu công việc; client cũ hồi phục và tiếp tục ghi dữ liệu. Lúc này hai client có thể cùng hoạt động dù lock service chỉ cấp một lease hiện hành.

Với tài nguyên quan trọng, cần **fencing token** hoặc version tăng đơn điệu. Mỗi lần lấy lock nhận một token mới; nguồn dữ liệu chỉ chấp nhận thao tác có token mới hơn token đã ghi nhận. Như vậy, client cũ với token thấp không thể ghi đè kết quả của client mới.

Nếu có thể dùng conditional write hoặc transaction ở chính nguồn dữ liệu, cách đó thường đơn giản hơn việc tự xây distributed lock. Lock chỉ nên được thêm khi đã xác định rõ race condition cần giải quyết.

## 7. Idempotency bảo vệ thao tác khi có retry và xử lý đồng thời

Serverless thường giao nhận message theo semantics ít nhất một lần ở nhiều cấu hình. Một request có thể timeout ở phía client dù function đã hoàn thành; một message có thể được giao lại; hai producer cũng có thể gửi cùng một yêu cầu nghiệp vụ gần như đồng thời.

**Idempotency** giúp nhiều lần nhận cùng một yêu cầu tạo ra kết quả nghiệp vụ tương đương một lần xử lý.

Một mẫu phổ biến là dùng idempotency key ổn định và unique constraint trong database:

~~~sql
CREATE TABLE processed_request (
    idempotency_key VARCHAR(120) PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    result_json TEXT,
    created_at TIMESTAMP NOT NULL,
    lease_until TIMESTAMP,
    owner_token VARCHAR(120)
);
~~~

Luồng xử lý:

1. Nhận request và xác thực idempotency key.
2. Thử tạo bản ghi với key đó.
3. Nếu key đã tồn tại và trạng thái SUCCEEDED, trả lại kết quả đã lưu.
4. Nếu key đang PROCESSING, áp dụng chính sách chờ, trả trạng thái đang xử lý hoặc điều phối lại.
5. Nếu tạo key thành công, thực hiện nghiệp vụ trong transaction phù hợp.
6. Lưu kết quả và đánh dấu SUCCEEDED trước khi trả thành công.

Việc claim key và cập nhật dữ liệu nghiệp vụ nên được phối hợp trong transaction nếu cùng database. Với trạng thái PROCESSING, có thể lưu lease_until và owner_token để một worker khác tiếp quản khi lease hết hạn; việc tiếp quản phải là conditional update để hai worker không cùng nhận quyền. Nếu nghiệp vụ gọi dịch vụ ngoài database, dùng idempotency key của dịch vụ đó và mô hình outbox/saga khi cần. Không đánh dấu SUCCEEDED trước khi side effect hoàn tất.

Idempotency và concurrency control giải quyết hai câu hỏi khác nhau: idempotency ngăn lặp cùng một yêu cầu; optimistic locking hoặc atomic update bảo vệ khi nhiều yêu cầu khác nhau cùng cạnh tranh một tài nguyên.

## 8. Tái sử dụng client và giới hạn concurrency trong Java function

Tạo client SDK, connection pool hoặc ObjectMapper ở mỗi lần gọi có thể làm tăng cold-start work và số kết nối. Có thể tái sử dụng object ở cấp class nếu:

- Object đã cấu hình xong trước khi được chia sẻ.
- Tài liệu xác nhận object/client thread-safe.
- Không lưu dữ liệu riêng của request trong object.
- Connection pool và timeout được giới hạn theo năng lực của dịch vụ đích.

Ví dụ:

~~~java
public final class CatalogHandler {
    private static final CatalogClient CLIENT =
            CatalogClient.createFromEnvironment();

    public CatalogResult handle(CatalogRequest request) {
        return CLIENT.lookup(request.productId());
    }
}
~~~

CatalogClient trong ví dụ là client minh họa; chỉ tái sử dụng theo cách này khi thư viện thực tế hỗ trợ dùng chung giữa thread. Không phải mọi SDK client hoặc custom client đều thread-safe.

### Không tạo thread không giới hạn

Nếu một invocation nhận batch gồm 500 item rồi tạo 500 thread, function có thể vượt giới hạn bộ nhớ, file descriptor, connection pool hoặc quota dịch vụ phụ thuộc. Nên dùng executor có giới hạn và chờ công việc hoàn tất trước khi handler trả response.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;

public final class BoundedBatchProcessor {
    private final ExecutorService executor;

    public BoundedBatchProcessor(ExecutorService executor) {
        this.executor = executor;
    }

    public List<String> process(List<String> items) {

        List<Future<String>> futures = new ArrayList<>();
        for (String item : items) {
            futures.add(executor.submit(() -> processOne(item)));
        }

        // Chỉ trả kết quả sau khi các tác vụ đã hoàn tất.
        List<String> results = new ArrayList<>(futures.size());
        try {
            for (Future<String> future : futures) {
                results.add(getResult(future));
            }
            return results;
        } catch (RuntimeException failure) {
            // Yêu cầu hủy các tác vụ còn lại nếu batch không thể hoàn tất.
            futures.forEach(future -> future.cancel(true));
            throw failure;
        }
    }

    private String getResult(Future<String> future) {
        try {
            return future.get();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Processing interrupted", ex);
        } catch (ExecutionException ex) {
            throw new IllegalStateException("Item processing failed", ex.getCause());
        }
    }

    private String processOne(String item) {
        return "processed:" + item;
    }
}
~~~

Executor được inject để composition root có thể cấu hình thread count và task queue có giới hạn, ví dụ:

~~~java
ExecutorService executor = new ThreadPoolExecutor(
        8, 8, 0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(64),
        new ThreadPoolExecutor.CallerRunsPolicy());
~~~

Các import tương ứng là ArrayBlockingQueue, TimeUnit, ThreadPoolExecutor và ExecutorService. Owner của executor chịu trách nhiệm đóng nó theo vòng đời runtime; nếu nền tảng không có lifecycle hook phù hợp, có thể tạo executor theo invocation rồi shutdown và chờ các tác vụ hoàn tất trước khi trả response, đồng thời tính đến chi phí khởi tạo. Phải áp dụng timeout cho tác vụ, giới hạn số request tới database/API và xác định cách báo lỗi từng item. Không để thread nền tiếp tục ghi dữ liệu sau khi handler đã trả kết quả hoặc sau khi invocation hết thời gian.

Nếu xử lý song song một batch, thứ tự hoàn thành có thể khác thứ tự đầu vào. Với FIFO hoặc nghiệp vụ phụ thuộc thứ tự, chỉ song song hóa các item độc lập hoặc theo từng message group. Khi một item lỗi, cần thu thập lỗi và trả partial batch response đúng hợp đồng trigger.

## 9. Giới hạn tài nguyên và backpressure

Scaling function nhanh hơn khả năng phục vụ của database hoặc API phụ thuộc có thể khiến hệ thống quá tải. Mỗi instance có thể tạo connection pool riêng; nếu 100 instance cùng mở pool tối đa 20 connection, backend có thể phải chịu tới 2.000 connection.

Hãy phối hợp các giới hạn:

- **Function concurrency:** giới hạn số invocation đồng thời.
- **Executor size:** giới hạn số thread nội bộ của mỗi invocation.
- **Connection pool:** giới hạn connection mỗi instance và tổng connection dự kiến.
- **Rate limit:** giới hạn tốc độ gọi API bên ngoài.
- **Queue buffering:** dùng queue để hấp thụ tải và xử lý theo tốc độ backend chịu được.
- **Timeout và backpressure:** ngừng nhận thêm việc khi không còn năng lực xử lý an toàn.

Khi dùng queue, độ dài queue và tuổi message lâu nhất là tín hiệu để điều chỉnh concurrency. Khi dùng HTTP trigger, cần trả lỗi có thể retry hoặc phản hồi quá tải theo hợp đồng API, thay vì giữ request vô thời hạn.

## 10. Kiểm thử đồng thời và quan sát production

Unit test tuần tự không phát hiện được mọi race condition. Hãy kiểm thử cùng một key hoặc bản ghi với nhiều thread, nhiều invocation và nhiều function instance.

| Tình huống | Cách kiểm thử | Kết quả cần xác minh |
|---|---|---|
| Hai thread tăng cùng counter | Dùng CountDownLatch cho nhiều thread bắt đầu cùng lúc | Atomic counter cho đúng tổng |
| Hai invocation giữ sản phẩm cuối | Gửi hai request khác nhau đồng thời | Chỉ một request giữ thành công |
| Duplicate event | Gửi cùng eventId song song | Chỉ một side effect nghiệp vụ |
| Hai tenant dùng chung handler | Gửi request xen kẽ và song song | Không rò tenant/request context |
| Cache local giữa instance | Gọi nhiều instance khác nhau | Không dựa vào static field để đồng bộ |
| Cache/database outage | Giả lập timeout và lỗi kết nối | Fallback có giới hạn, không tạo retry storm |
| Function timeout khi task còn chạy | Giả lập task chậm và invocation hết hạn | Không có background write không được kiểm soát |

Trong Java, có thể dùng CountDownLatch, CyclicBarrier hoặc công cụ stress test để làm nhiều thread tranh chấp cùng một điểm. Integration test nên chạy nhiều invocation đồng thời trên môi trường gần production và xác minh dữ liệu cuối trong database, không chỉ kiểm tra HTTP response.

Các metric nên theo dõi:

- Số invocation đồng thời và số execution environment.
- Thời gian xử lý, timeout, throttling và cold start.
- Thread count, task queue depth và executor rejection.
- Connection pool active/idle, timeout và lỗi kết nối.
- Optimistic lock conflict, deadlock và transaction retry.
- Duplicate event, idempotency hit và số side effect bị chặn.
- Queue depth, message age và số lần redelivery.

Log cần có request ID, correlation ID, business key và function version để truy vết. Không ghi token, secret hoặc dữ liệu cá nhân không cần thiết.

## 11. Checklist quản lý trạng thái dùng chung

- [ ] Đã xác định concurrency model của FaaS provider và khả năng nhiều request trên một instance.
- [ ] Static field chỉ chứa cấu hình bất biến hoặc client dùng chung đã xác minh thread-safe.
- [ ] Không lưu tenant, user, request hoặc trạng thái nghiệp vụ trong field dùng chung.
- [ ] Local cache có giới hạn kích thước, TTL và không được coi là nguồn chuẩn.
- [ ] Không dùng synchronized, volatile hoặc AtomicLong để khóa/cập nhật dữ liệu giữa nhiều instance.
- [ ] Dữ liệu dùng chung được bảo vệ ở database hoặc dịch vụ có atomic operation phù hợp.
- [ ] Có optimistic/pessimistic locking hoặc conditional update cho tài nguyên tranh chấp.
- [ ] Có idempotency key ổn định và unique constraint cho yêu cầu có thể bị gửi lại.
- [ ] Thread pool, connection pool, timeout và concurrency có giới hạn.
- [ ] Tác vụ async hoàn tất hoặc được quản lý rõ trước khi invocation kết thúc.
- [ ] Có backpressure và giới hạn tải lên dịch vụ phụ thuộc.
- [ ] Đã kiểm thử race condition, duplicate, timeout, outage và request xen kẽ giữa tenant.
- [ ] Có metric cho lock conflict, connection, retry, concurrency và queue age.

## Tự kiểm tra

1. Vì sao biến static có thể còn giá trị sau một invocation nhưng không phải trạng thái bền vững của serverless function?
2. `volatile` giải quyết vấn đề gì và vì sao không làm phép `count++` trở thành atomic?
3. Vì sao `synchronized` không bảo vệ được tồn kho khi hai function instance khác nhau cùng cập nhật database?
4. Khi nào nên dùng optimistic locking và khi nào pessimistic locking?
5. Idempotency khác gì với concurrency control?
6. Vì sao không nên tạo một thread cho mỗi message trong batch lớn?
7. Nếu 100 function instance cùng fallback về database khi Redis lỗi, hệ thống có thể gặp vấn đề gì?
8. Cần giữ những dữ liệu nào ngoài state hiện tại để điều tra một race condition trong production?

Java serverless cần được thiết kế như một hệ thống phân tán: mỗi execution environment có bộ nhớ riêng, vòng đời không cố định và có thể chạy đồng thời với nhiều instance khác. Hãy giữ request state trong phạm vi invocation, dùng object bất biến hoặc thread-safe cho chia sẻ trong JVM, và đặt bảo đảm nghiệp vụ ở database hoặc dịch vụ dùng chung có atomic semantics. Khi kết hợp idempotency, giới hạn concurrency, backpressure và kiểm thử song song, function có thể mở rộng mà vẫn bảo toàn dữ liệu.

