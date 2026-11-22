# Truyền mã định danh hoặc dữ liệu bất biến thay cho thực thể đang gắn phiên

## 1. Bài toán: một entity JPA không phải thông điệp an toàn giữa các thread

Trong một ứng dụng Spring, transaction thường mở một persistence context để truy xuất entity JPA qua `EntityManager`/Hibernate `Session`. Ở thread xử lý request, code lấy `OrderEntity` từ repository, sửa trạng thái, rồi muốn phát sự kiện hoặc gửi entity đó cho method `@Async`. Cách làm tưởng tiện:

```java
// Phản ví dụ, không phải một chương trình Java độc lập.
@Transactional
public void approve(long orderId) {
    OrderEntity order = repository.findById(orderId).orElseThrow();
    order.approve();
    backgroundWorker.notifyCustomer(order); // Truyền entity đang managed.
}
```

Nhưng `backgroundWorker` có thể chạy trên thread khác khi transaction của caller chưa commit, đã rollback hoặc persistence context đã đóng. Entity có thể chứa lazy proxy, collection chưa khởi tạo, trạng thái mutable và tham chiếu đến đồ thị đối tượng lớn. **Một entity đang managed không phải hợp đồng dữ liệu được thiết kế để chuyển giữa transaction, thread, process hay message broker.**

Mục tiêu bài học thuộc nhóm **Giao dịch và sự kiện** của chủ đề **Spring Framework - concurrency**: **truyền mã định danh (ID) hoặc dữ liệu bất biến (immutable snapshot/DTO) thay cho entity đang gắn persistence context** ở những ranh giới bất đồng bộ.

Sau khi học xong, bạn cần:

1. Giải thích managed, detached, lazy association, dirty checking và lý do `Session`/persistence context không thread-safe.
2. Hiểu vì sao `@Async` không tự chuyển transaction, `EntityManager` hay Hibernate session của caller sang worker.
3. Chọn giữa **truyền ID rồi load lại**, **truyền immutable snapshot**, và **truyền ID kèm version** theo yêu cầu nhất quán.
4. Biết tạo snapshot **khi context còn hợp lệ**, không vô tình đụng lazy association trong worker.
5. Áp dụng Spring `@TransactionalEventListener(phase = AFTER_COMMIT)` đúng phạm vi; phân biệt sự kiện sau commit với hàng đợi bền vững.
6. Dùng `@Version`/optimistic locking hoặc conditional update khi công việc cũ không được ghi đè trạng thái mới.
7. Nhận diện giới hạn của `List.copyOf` và `record`: immutable reference không tự làm cho cả object graph sâu bên trong bất biến.
8. Có ví dụ Java 17+ chạy được, cấu trúc Spring/JPA minh họa và kế hoạch test lỗi concurrency.

**Thông điệp chính:** truyền một entity reference sang thread khác chỉ truyền **tham chiếu**, không truyền một transaction còn sống, không clone trạng thái và không trao quyền sử dụng persistence context từ thread khác.

## 2. Persistence context thực sự quản lý điều gì?

Một JPA persistence context theo dõi các entity và quan hệ của chúng trong một đơn vị công việc. Hibernate `Session` cung cấp persistence context, thường đóng vai trò:

- **Identity map / first-level cache:** trong một context, một hàng entity theo định danh có một managed representation tương ứng.
- **Dirty checking:** Hibernate có thể nhận diện thay đổi trên managed entity và đồng bộ xuống database khi flush/commit thích hợp.
- **Lazy loading:** một association có thể được đại diện bằng proxy/collection chưa được nạp; việc truy cập có thể cần một context/session còn hiệu lực.
- **Unit of work:** các thao tác được phối hợp trong phạm vi transaction/flush theo cấu hình.
- **Lifecycle:** context có thể là transaction-scoped, extended hoặc application-managed; không phải mặc định tồn tại suốt vòng đời JVM.

Trong cấu hình Spring Data JPA thông thường, transaction-bound `EntityManager` được quản lý theo phạm vi transaction và thread context phù hợp. Entity lấy ra bên trong transaction có thể là **managed** ở thời điểm đó. Sau khi context đóng, entity có thể trở thành **detached**; việc truy cập trường đã nạp có thể vẫn hoạt động, còn lazy association chưa nạp có thể gây `LazyInitializationException` khi dùng Hibernate.

### 2.1. Bốn trạng thái entity JPA cơ bản

| Trạng thái | Diễn giải | Rủi ro khi chuyển sang background worker |
| --- | --- | --- |
| `new/transient` | Object mới, chưa gắn persistence context | Không có dirty checking; ID có thể chưa được cấp |
| `managed` | Object gắn với persistence context | Chia sẻ graph/session không thread-safe, dữ liệu có thể chưa commit |
| `detached` | Entity từng được quản lý nhưng không còn gắn context đó | Lazy chưa load có thể lỗi, dữ liệu cũ, thay đổi không tự flush |
| `removed` | Entity đã được đánh dấu xóa trong context | Worker có thể quan sát trạng thái không còn phù hợp sau commit/rollback |

**Cần phân biệt:** một reference entity được **truyền** sang worker không tự động thành detached ngay lập tức chỉ vì đổi thread. Entity vẫn có thể đang managed trong **context của caller**. Vấn đề là context/Session không được thiết kế để sử dụng đồng thời từ nhiều thread; khi context kết thúc, reference có thể detached.

### 2.2. Session không thread-safe

Hibernate User Guide ghi rõ `Session`/`EntityManager` và persistence context **không thread-safe**. Không đưa cùng một `EntityManager`/`Session` thật sang nhiều worker, và không cho các worker đồng thời thao tác cùng một managed entity graph trong một context.

Một nuance quan trọng: bean `EntityManager` được Spring inject qua `@PersistenceContext` trong nhiều cấu hình thực tế có thể là **shared transactional proxy** an toàn để *inject* vào nhiều Spring services, vì proxy định tuyến tới target `EntityManager` phù hợp với thread/transaction. Điều đó **không** làm cho **target EntityManager**, persistence context, hoặc entity lấy từ context trở thành đối tượng dùng chung an toàn giữa thread.

### 2.3. OSIV có thể che lấp lỗi thiết kế

Open Session in View (OSIV) có thể giữ persistence context trong suốt vòng đời HTTP request ở một số cấu hình Spring web, khiến lazy properties vô tình được nạp khi serialize response. Nó không bảo đảm session còn sống trong mọi `@Async` worker, không biến JPA entity thành thread-safe và dễ dẫn đến truy vấn N+1/khó quan sát số query.

Không bật OSIV hoặc giữ transaction mở dài chỉ để “chữa” việc chuyển entity sang worker. Hãy **xác định dữ liệu cần dùng** và xây boundary rõ ràng.

## 3. Vì sao truyền trực tiếp entity sang @Async dễ sai?

```text
Request thread                          Worker thread
-------------------------               ------------------------
@Transactional
   |
   | findById(42)
   v
managed OrderEntity ----- reference ---> @Async process(OrderEntity)
   |                                        |
   | mutate/flush/commit                    | getCustomer().getEmail()
   |                                        | getLines().size()
   | close persistence context              | mutate order.setStatus(...)
   v                                        v
transaction ended                    lazy failure / stale data /
                                     concurrent modification /
                                     no predictable flush
```

Một số tình huống thực tế:

- **Lazy association:** `order.getLines()` chưa khởi tạo. Worker đụng vào sau khi context đóng có thể gặp `LazyInitializationException`.
- **Race khi caller còn chạy:** worker đọc `order.status` đúng lúc caller đang sửa; không có snapshot độc lập.
- **Dirty checking sai kỳ vọng:** worker thay đổi entity detached không tự làm database được update; worker thay đổi managed entity từ thread khác lại là sử dụng context không an toàn.
- **Đọc trước commit:** worker có thể chạy trước transaction tạo/sửa order commit. Một query trong transaction mới thậm chí chưa thấy hàng mới, hoặc đọc phiên bản cũ.
- **Rollback:** caller phát event/submit task trước commit rồi transaction rollback; worker vẫn có thể gửi email về một order chưa từng được commit.
- **Serialize message:** JPA proxy/bi-directional relations gây payload rất lớn, recursion, dữ liệu không chủ đích hoặc lỗi serializer.
- **Gắn transaction lâu:** giữ entity manager/connection mở trong suốt tác vụ chậm gây tăng contention và giữ first-level cache lớn.

Không phải lần nào truyền entity cũng lập tức ném lỗi. Một entity đã nạp toàn bộ trường và chỉ đọc có thể trông như chạy “ổn” trong test. Điều đó **không phải bảo đảm** về tính nhất quán, thread-safety hay vòng đời.

## 4. Nguyên tắc: chuyển quyền truy cập dữ liệu thành một hợp đồng rõ ràng

Thay vì mang theo **managed entity reference**, hãy mang theo một **message/command** gồm dữ liệu tối thiểu, ổn định và có ý nghĩa nghiệp vụ:

1. **ID:** worker nhận định danh rồi tự mở transaction/persistence context phù hợp để load dữ liệu.
2. **Immutable snapshot:** caller tạo DTO bất biến từ những trường cần thiết khi context hợp lệ, rồi chuyển qua worker.
3. **ID + version/revision:** worker dùng ID để tải lại hoặc kiểm tra version nhằm phát hiện job đã lỗi thời.
4. **Hybrid:** ID + version + vài trường snapshot để tối ưu, nhưng vẫn định nghĩa dữ liệu nào là authoritative.

| Tiêu chí | ID rồi re-fetch | Immutable snapshot | ID + expected version |
| --- | --- | --- | --- |
| Payload | Nhỏ | Theo số trường đã chọn | Nhỏ |
| Thời điểm dữ liệu được đọc | Lúc worker load | Lúc caller tạo snapshot | Lúc worker load/so version |
| Thấy dữ liệu cập nhật sau event? | Có thể, tùy transaction/isolation | Không, snapshot giữ giá trị cũ | Có thể phát hiện thay đổi |
| Lazy loading | Worker load trong context mới | Caller phải materialize trường cần thiết trước khi gửi | Worker load trong context mới |
| Dễ dùng qua queue/broker | Có | Có nếu DTO serializable theo protocol | Có |
| Chi phí query ở worker | Có | Có thể không | Thường có |
| Rủi ro stale | Đọc state mới nhưng có thể lệch event | Snapshot cũ theo chủ đích | Có luật từ chối stale |
| Sử dụng phổ biến | “Xử lý trạng thái hiện tại của order X” | “Gửi thông điệp phản ánh event tại thời điểm T” | “Chỉ xử lý nếu revision X còn hợp lệ” |

Không có lựa chọn “luôn tốt nhất”. Phải hỏi **ngữ nghĩa thời điểm**: worker nên xử lý **trạng thái mới nhất hiện tại** hay **sự kiện đã xảy ra tại một thời điểm cụ thể**?

## 5. Mẫu 1 — Chỉ truyền ID, worker load lại trong transaction của nó

Đây thường là điểm khởi đầu đơn giản nhất:

```java
// Phản mẫu: OrderEntity đang managed được đưa qua async boundary.
@Async("orderExecutor")
public CompletableFuture<Void> sendNotice(OrderEntity order) {
    String email = order.getCustomer().getEmail();
    gateway.send(email, order.getId());
    return CompletableFuture.completedFuture(null);
}
```

Đổi sang:

```java
// Fragment Spring: chỉ truyền giá trị định danh.
@Async("orderExecutor")
public CompletableFuture<Void> sendNotice(long orderId) {
    NoticeSnapshot notice = snapshotLoader.loadById(orderId);
    gateway.send(notice);
    return CompletableFuture.completedFuture(null);
}
```

`snapshotLoader` là một **Spring bean khác** có method `@Transactional(readOnly = true)`. Nó load entity trong transaction mới của worker, lấy đúng dữ liệu và trả snapshot. Worker gửi email **sau khi** transaction đọc đã đóng, không giữ transaction qua network I/O kéo dài.

Lợi ích:

- Không chia sẻ entity/Session giữa caller và worker.
- Mỗi transaction có persistence context độc lập.
- Payload có thể truyền qua message broker: chỉ ID, version, tenant ID nếu cần.
- Dễ thay implementation lưu trữ và tối ưu query mà không thay event schema phức tạp.
- Có thể kiểm soát trường hợp record đã bị xóa hoặc không nhìn thấy do commit chưa xảy ra.

### 5.1. Re-fetch có nghĩa đọc state vào thời điểm worker chạy

Giả sử tại thời điểm event, order có status `CREATED`, nhưng trước khi worker chạy, người khác cập nhật thành `CANCELLED`. Worker load bằng ID có thể thấy `CANCELLED`. Đó là hành vi **đúng** nếu mục tiêu là “chỉ gửi nếu order hiện còn được phép gửi”; nhưng có thể **sai** nếu người nhận cần một bản ghi audit chính xác về sự kiện `CREATED` đã xảy ra.

Để tránh nhầm lẫn, ghi rõ:

- **Fresh-state command:** “Đọc trạng thái hiện tại của order X và quyết định có gửi không”.
- **Historical event:** “Order X đã được xác nhận lúc T với dữ liệu Y”. Event cần snapshot hoặc version/historical storage để diễn tả sự kiện.
- **Guarded command:** “Chỉ áp dụng lệnh nếu order X vẫn ở version V”.

### 5.2. Đợi commit trước khi worker tìm record mới tạo

Nếu caller tạo order và submit worker **trước commit**, worker có thể chạy trước khi row được commit, rồi `findById` trả empty hoặc thấy trạng thái cũ theo isolation. Không giải quyết bằng `Thread.sleep(500)` vì thứ tự scheduling không được bảo đảm.

Giải pháp đúng tùy yêu cầu:

- Gắn listener với `AFTER_COMMIT` qua `@TransactionalEventListener` khi có transaction thật.
- Lưu durable outbox/job record **cùng transaction** nếu sự kiện bắt buộc không được mất.
- Nếu workflow phụ thuộc vào transaction thành công, đừng trực tiếp gọi `@Async` để phát side effect **trước commit**.

## 6. Mẫu 2 — Snapshot bất biến giữ dữ liệu tại thời điểm phát sự kiện

Khi worker cần **giá trị tại thời điểm caller quyết định**, một immutable DTO giúp mô tả contract chính xác.

Ví dụ dùng Java 17 `record`:

```java
public record OrderNoticeSnapshot(
        long orderId,
        String customerEmail,
        String status,
        java.util.List<String> productCodes) {

    public OrderNoticeSnapshot {
        java.util.Objects.requireNonNull(customerEmail);
        java.util.Objects.requireNonNull(status);
        productCodes = java.util.List.copyOf(productCodes);
    }
}
```

Đây là **fragment định nghĩa DTO**. `record` cung cấp các final components; `String` bất biến; `List.copyOf` chụp cấu trúc list và trả unmodifiable list, từ chối null. Vì mỗi element là `String` bất biến nên đồ thị trong ví dụ có tính chất snapshot tốt.

**Cảnh báo sâu:** `List.copyOf` chỉ **shallow copy** cấu trúc list, không copy sâu từng phần tử. Nếu `productCodes` là `List<MutableLine>`, mỗi `MutableLine` vẫn có thể bị sửa sau khi gửi. Tương tự, một record chứa `Date`, mảng, entity, `List<MutableEntity>` hoặc object có setter **không tự thành deep immutable** chỉ vì outer type là record.

### 6.1. Chọn đúng dữ liệu

Snapshot tốt:

- Chỉ có trường worker thực sự cần.
- Có ý nghĩa rõ: ID, operation ID, timestamp, status tại thời điểm phát event, version nếu cần.
- Không chứa `EntityManager`, `Session`, `PersistenceContext`, lazy proxy hoặc live `PersistentCollection`.
- Không chứa object có lifecycle request hay thông tin nhạy cảm không cần thiết.
- Có schema ổn định nếu được serialize qua message broker.
- Dùng immutable scalars, nested records/DTOs cũng bất biến, và immutable collections.

Nếu một quan hệ được lazy load, hãy chủ động fetch/khởi tạo **trong transaction đang mở** và chuyển từng trường thành DTO; không truyền lazy collection để worker “tự đọc sau”.

### 6.2. Transaction boundary của snapshot

Khi tạo snapshot trong method `@Transactional`, bạn đang chụp **trạng thái code nhìn thấy** trong transaction đó. Nếu sau đó transaction rollback, một snapshot được phát đi ngay từ method có thể mô tả thay đổi chưa bao giờ commit.

Vì vậy:

- Nếu event chỉ hợp lệ khi commit thành công, publish event theo contract phù hợp và xử lý bằng `@TransactionalEventListener(AFTER_COMMIT)`, hoặc ghi outbox trong cùng transaction.
- Có thể **tạo snapshot trước commit** khi entity còn được truy cập hợp lệ, rồi listener chỉ xử lý nó **sau commit**.
- Snapshot không bảo đảm dữ liệu không đổi trong DB sau thời điểm chụp; nó bảo đảm **payload đã chụp không thay đổi** nếu thiết kế thật sự bất biến.

## 7. Ví dụ Java 17+ — reference mutable và snapshot bất biến

Ví dụ Java thuần sau mô phỏng việc một thread giữ reference mutable, trong khi một object `record` chứa giá trị đã chụp. Không cần JPA để thấy rằng **truyền reference không copy giá trị**. Dùng latch để tạo thứ tự xác định, không dựa vào `Thread.sleep`.

Tệp `MutableVsSnapshotDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class MutableVsSnapshotDemo {
    static final class MutableOrder {
        private volatile String status;

        MutableOrder(String status) {
            this.status = status;
        }

        String status() {
            return status;
        }

        void changeStatus(String newStatus) {
            status = newStatus;
        }
    }

    record OrderSnapshot(String status) {}

    public static void main(String[] args) throws Exception {
        MutableOrder entity = new MutableOrder("CREATED");
        OrderSnapshot snapshot = new OrderSnapshot(entity.status());
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<String> byReference = executor.submit(() -> {
                release.await();
                return entity.status();
            });

            Future<String> bySnapshot = executor.submit(() -> {
                release.await();
                return snapshot.status();
            });

            entity.changeStatus("CANCELLED");
            release.countDown();

            System.out.println("reference=" +
                    byReference.get(5, TimeUnit.SECONDS));
            System.out.println("snapshot=" +
                    bySnapshot.get(5, TimeUnit.SECONDS));
        } finally {
            release.countDown();
            executor.shutdownNow();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac MutableVsSnapshotDemo.java
java MutableVsSnapshotDemo
```

Kết quả:

```text
reference=CANCELLED
snapshot=CREATED
```

**Giải thích:**

- `byReference` giữ cùng reference `entity`, nên sau khi main đổi status, worker thấy giá trị mới.
- `bySnapshot` giữ record chứa String đã được chụp lúc `CREATED`.
- `volatile` trong mẫu chỉ làm việc đọc/ghi status rõ ràng về visibility; nó không biến một JPA entity và Hibernate Session thành thread-safe.
- Latch đặt quan hệ *happens-before* cần thiết cho thứ tự quan sát. Đây là mô phỏng **tính mutable của Java reference**, không phải khẳng định về nội bộ JPA.
- Nếu nghiệp vụ muốn worker xử lý **trạng thái mới nhất**, việc re-fetch ID là một chiến lược; nếu muốn xử lý đúng event `CREATED`, snapshot là một chiến lược khác.

## 8. Ví dụ Java 17+ — đóng băng nested data bằng copy phù hợp

Một snapshot có `List` cần tránh “bất biến ở vỏ, mutable ở ruột”.

Tệp `DeepEnoughSnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class DeepEnoughSnapshotDemo {
    record Line(String productCode, int quantity) {}

    record OrderSnapshot(long id, List<Line> lines) {
        OrderSnapshot {
            lines = List.copyOf(lines);
        }
    }

    public static void main(String[] args) {
        List<Line> liveLines = new ArrayList<>();
        liveLines.add(new Line("SKU-A", 2));

        OrderSnapshot snapshot =
                new OrderSnapshot(101L, liveLines);

        liveLines.add(new Line("SKU-B", 1));

        System.out.println("live-size=" + liveLines.size());
        System.out.println("snapshot-size=" + snapshot.lines().size());
        System.out.println("first=" +
                snapshot.lines().get(0).productCode());

        try {
            snapshot.lines().add(new Line("SKU-C", 3));
        } catch (UnsupportedOperationException ex) {
            System.out.println("list-is-unmodifiable=true");
        }
    }
}
```

```bash
javac DeepEnoughSnapshotDemo.java
java DeepEnoughSnapshotDemo
```

Output:

```text
live-size=2
snapshot-size=1
first=SKU-A
list-is-unmodifiable=true
```

Ở đây `Line` là record chứa `String` và `int`; list được copy thành unmodifiable list nên snapshot đủ bất biến theo contract đơn giản này.

**Không tổng quát hóa sai:** nếu phần tử list là `MutableLine` với setter, `List.copyOf` vẫn giữ reference tới phần tử đó. Lúc ấy hãy map thành `Line` bất biến **từng phần tử** trước khi tạo list snapshot.

Một ví dụ map trong transaction JPA:

```java
List<OrderLineSnapshot> lines =
        order.getLines().stream()
                .map(line -> new OrderLineSnapshot(
                        line.getSku(),
                        line.getQuantity()))
                .toList();
```

Đây là fragment Spring/JPA, giả định `getLines()` được fetch/đọc khi persistence context hợp lệ và `OrderLineSnapshot` là immutable DTO. `Stream.toList()` trả unmodifiable list, nhưng tính bất biến sâu vẫn phụ thuộc phần tử.

## 9. Ví dụ Java 17+ — chọn fresh state hoặc snapshot theo hợp đồng

Tệp `IdVsSnapshotDemo.java`:

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class IdVsSnapshotDemo {
    record Order(long id, String status) {}
    record OrderEvent(long id, String statusAtEvent) {}

    public static void main(String[] args) {
        Map<Long, Order> store = new ConcurrentHashMap<>();
        store.put(7L, new Order(7L, "CREATED"));

        Order atEvent = store.get(7L);
        long idOnly = atEvent.id();
        OrderEvent snapshot =
                new OrderEvent(atEvent.id(), atEvent.status());

        store.put(7L, new Order(7L, "CANCELLED"));

        Order current = store.get(idOnly);

        System.out.println("loaded-now=" + current.status());
        System.out.println("event-snapshot="
                + snapshot.statusAtEvent());
    }
}
```

```bash
javac IdVsSnapshotDemo.java
java IdVsSnapshotDemo
```

Output:

```text
loaded-now=CANCELLED
event-snapshot=CREATED
```

Đây là mô phỏng bằng `ConcurrentHashMap`, không phải database/JPA. Nó cố ý cho thấy hai câu hỏi khác nhau:

- **“Trạng thái của order 7 là gì ở thời điểm xử lý?”** → re-fetch theo ID.
- **“Trạng thái của order 7 khi event được tạo là gì?”** → dùng snapshot.

Trong database thật, isolation level, replication lag và transaction timing còn ảnh hưởng tới dữ liệu mà worker nhìn thấy. Vì vậy “re-fetch” không đồng nghĩa với “luôn nhìn thấy trạng thái mới nhất theo thời gian thực trên mọi replica”.

## 10. Cấu trúc Spring/JPA nên dùng: event chỉ mang ID, worker load snapshot trong transaction riêng

Các đoạn sau là **mẫu kiến trúc trong project Spring Boot + Spring Data JPA**, không phải từng file chạy chỉ với `javac`. Chúng cần imports đúng của Spring/JPA, bean database, entity/repository/service/notification gateway thực tế.

### 10.1. Entity và repository

Ví dụ domain có `OrderEntity` và `OrderLineEntity`. Trong snippet này, entity có ID và các fields; collection `lines` có thể được lazy-load.

```java
// File: OrderEntity.java (fragment)
@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private Long id;

    @Version
    private long version;

    private String status;
    private String customerEmail;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLineEntity> lines = new ArrayList<>();

    public Long getId() { return id; }
    public long getVersion() { return version; }
    public String getStatus() { return status; }
    public String getCustomerEmail() { return customerEmail; }
    public List<OrderLineEntity> getLines() { return lines; }

    public void markApproved() {
        status = "APPROVED";
    }
}
```

`OrderLineEntity` là một entity riêng có quan hệ `order` và field `sku`/`quantity`; cần khai báo nó trong dự án. `@Version` giúp optimistic locking phát hiện các ghi cạnh tranh theo semantics provider, nhưng không tự biến entity thành object có thể chia sẻ giữa thread.

Repository đọc order cùng lines bằng query có chủ đích:

```java
// File: OrderRepository.java (fragment)
public interface OrderRepository
        extends JpaRepository<OrderEntity, Long> {

    @Query("""
           select distinct o from OrderEntity o
           left join fetch o.lines
           where o.id = :id
           """)
    Optional<OrderEntity> findWithLines(@Param("id") Long id);
}
```

Query này yêu cầu quan hệ/mapping hợp lệ trong project. Có thể thay bằng `@EntityGraph`, DTO projection hoặc query chuyên biệt. **Không** trả về entity này cho worker khác sau khi repository gọi xong chỉ vì query đã fetch eager; làm vậy vẫn ràng buộc code vào managed entity/mutable graph.

### 10.2. Command và snapshot tách khỏi JPA

```java
// File: OrderCommitted.java
public record OrderCommitted(long orderId) {}

// File: OrderNoticeSnapshot.java
public record OrderNoticeSnapshot(
        long orderId,
        long version,
        String customerEmail,
        java.util.List<String> productCodes) {

    public OrderNoticeSnapshot {
        productCodes = java.util.List.copyOf(productCodes);
    }
}
```

Hai record đều là **value carriers**; không chứa entity, Hibernate proxy hay `EntityManager`. Nếu `customerEmail` có dữ liệu cá nhân, hãy áp dụng tối thiểu hóa payload và chính sách xử lý dữ liệu của hệ thống, nhất là khi gửi qua broker/log.

### 10.3. Loader sở hữu transaction đọc trong worker thread

```java
// File: OrderSnapshotLoader.java (fragment)
@Service
public class OrderSnapshotLoader {
    private final OrderRepository repository;

    public OrderSnapshotLoader(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderNoticeSnapshot load(long id) {
        OrderEntity order =
                repository.findWithLines(id).orElseThrow();

        List<String> codes =
                order.getLines().stream()
                        .map(OrderLineEntity::getSku)
                        .toList();

        return new OrderNoticeSnapshot(
                order.getId(),
                order.getVersion(),
                order.getCustomerEmail(),
                codes);
    }
}
```

Đây là một **Spring bean riêng**. Worker gọi `loader.load(id)` qua Spring-managed reference nên `@Transactional(readOnly = true)` được intercept khi cấu hình transaction hoạt động. Loader tạo snapshot **bên trong context**, rồi trả ra DTO. Sau khi method kết thúc, worker không cần truy cập lazy fields của entity.

**Đừng coi `readOnly = true` là cơ chế cấm ghi tuyệt đối ở mọi database:** đó là chỉ dẫn transaction/provider để tối ưu hoặc hạn chế flush theo cấu hình; correctness nghiệp vụ vẫn cần thiết kế riêng.

### 10.4. Worker @Async nhận ID, không nhận entity

```java
// File: OrderNotificationWorker.java (fragment)
@Service
public class OrderNotificationWorker {
    private final OrderSnapshotLoader loader;
    private final NotificationGateway gateway;

    public OrderNotificationWorker(
            OrderSnapshotLoader loader,
            NotificationGateway gateway) {
        this.loader = loader;
        this.gateway = gateway;
    }

    @Async("notificationExecutor")
    public CompletableFuture<Void> deliver(long orderId) {
        OrderNoticeSnapshot payload = loader.load(orderId);
        gateway.send(payload);
        return CompletableFuture.completedFuture(null);
    }
}
```

Worker mở transaction đọc **qua loader khác bean**, sau đó gọi gateway bằng DTO. Cách tách giúp tránh giữ một transaction DB mở trong lúc chờ HTTP/email I/O. Lỗi gateway làm future của lời gọi `@Async` thất bại theo cơ chế của Spring; caller/event listener cần quan sát và xử lý thất bại.

Nếu thông báo bắt buộc phải được gửi dù JVM restart, worker chỉ chạy trong RAM không đủ; xem phần **outbox** dưới đây.

### 10.5. Cấu hình executor có giới hạn

```java
@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfig {
    @Bean("notificationExecutor")
    public ThreadPoolTaskExecutor notificationExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("notice-");
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(40);
        return executor;
    }
}
```

Fragment cần imports tương ứng. Số thread/queue chỉ là ví dụ. `@EnableAsync` kích hoạt async annotation processing; bean executor quyết định tài nguyên. Nếu `notificationExecutor` bị reject khi quá tải, application phải có chính sách xử lý, không bỏ lặng exception hoặc chỉ tin rằng “đã publish event là xong”.

## 11. Sự kiện gắn transaction: chỉ xử lý sau commit

Một luồng tiêu biểu là service transactional cập nhật order và phát **event nhẹ**:

```java
// File: OrderApplicationService.java (fragment)
@Service
public class OrderApplicationService {
    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;

    public OrderApplicationService(
            OrderRepository repository,
            ApplicationEventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional
    public void approve(long orderId) {
        OrderEntity order =
                repository.findById(orderId).orElseThrow();
        order.markApproved();

        // Event mang ID, không mang OrderEntity.
        publisher.publishEvent(new OrderCommitted(orderId));
    }
}
```

Nếu listener thông thường được gọi ngay trong transaction, việc gọi worker trực tiếp có thể chạy **trước khi commit**. Ta cần listener theo pha transaction:

```java
// File: OrderCommittedListener.java (fragment)
@Component
public class OrderCommittedListener {
    private final OrderNotificationWorker worker;

    public OrderCommittedListener(
            OrderNotificationWorker worker) {
        this.worker = worker;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderCommitted event) {
        worker.deliver(event.orderId())
              .whenComplete((ignored, error) -> {
                  if (error != null) {
                      // Ghi nhận lỗi theo logging/monitoring thực tế.
                  }
              });
    }
}
```

Các snippet này cần imports, transaction manager thực sự và event được publish **trong transaction**. `@TransactionalEventListener` mặc định gắn với pha `AFTER_COMMIT`. Khi transaction không tồn tại, listener mặc định **không được gọi**, trừ khi bật `fallbackExecution=true` theo yêu cầu rõ ràng.

**Quan hệ thời gian dự kiến:**

```text
Request thread:
  @Transactional approve()
     -> find managed OrderEntity
     -> mutate entity
     -> publish OrderCommitted(orderId)
     -> commit transaction
     -> listener AFTER_COMMIT gọi worker.deliver(orderId)

Worker executor thread:
  @Async deliver(orderId)
     -> @Transactional(readOnly=true) loader.load(orderId)
     -> mở context mới trong worker
     -> map entity sang immutable snapshot
     -> đóng transaction đọc
     -> gateway.send(snapshot)
```

Listener sau commit **không tự động bất đồng bộ**. `@TransactionalEventListener` gắn với lifecycle của transaction; bước gọi `worker.deliver(...)` mới đi qua `@Async` proxy để submit task cho executor.

### 11.1. Hai cảnh báo quan trọng về AFTER_COMMIT

**Cảnh báo 1 — Sự kiện in-memory không bền vững.** Transaction DB có thể commit thành công rồi JVM chết **trước khi** listener kịp submit task, hoặc task đã nằm trong queue RAM nhưng process bị kill. `AFTER_COMMIT` ngăn chạy trước commit theo cấu hình, **không** cam kết at-least-once delivery qua restart. Nếu không được mất tác vụ, dùng transactional outbox/durable job queue.

**Cảnh báo 2 — Resources sau commit có thể vẫn còn bound.** Theo Javadoc Spring, trong callback `AFTER_COMMIT`/`AFTER_COMPLETION`, transactional resources đôi khi vẫn accessible mặc dù transaction đã commit; một thao tác DB ghi trong cùng transaction resource có thể **không được commit tiếp**. Nếu listener phải thực hiện ghi transactional đồng bộ, dùng transaction mới phù hợp (ví dụ `REQUIRES_NEW` qua Spring proxy); trong mẫu trên, ta chỉ submit sang worker, còn loader mở transaction ở thread worker.

Đừng coi “đã sau commit” là đồng nghĩa mọi resource đã bị remove ngay tại thời điểm callback bắt đầu.

### 11.2. Nếu cần snapshot của trạng thái trước/sau cụ thể

Listener chỉ nhận ID sẽ load **trạng thái hiện tại khi worker chạy**, có thể là bản được cập nhật *sau* event. Nếu email phải phản ánh chính xác “đã duyệt lúc T, tổng tiền Y” thì event nên chứa immutable snapshot của những trường đó, được xây **trong transaction** khi trạng thái đã chuẩn bị đúng và chỉ được xử lý sau commit, hoặc lưu dữ liệu trong outbox theo transaction.

Không lấy entity `OrderEntity` rồi trì hoãn việc map DTO đến listener sau commit; điều đó đưa rủi ro lazy/context trở lại. **Materialize snapshot khi context còn hợp lệ.**

## 12. Khi cần tránh dữ liệu cũ: ID kèm version và optimistic locking

Truyền ID bảo đảm có thể re-fetch trong context riêng, nhưng không tự chống xử lý thông tin cũ. Dùng `@Version` hoặc revision/generation nếu cần xác nhận công việc tương ứng trạng thái nào.

Ví dụ event:

```java
public record OrderNotificationRequested(
        long orderId,
        long expectedVersion) {}
```

Worker đọc version hiện tại rồi quyết định:

```java
OrderNoticeSnapshot current = loader.load(event.orderId());

if (current.version() != event.expectedVersion()) {
    // Event đã cũ; skip, reconcile hoặc theo policy.
}
```

Đây chỉ là **fragment kiểm tra trước xử lý**. Nếu dữ liệu có thể đổi **giữa lúc kiểm tra và lúc commit side effect**, phép so sánh trong Java có race kiểu check-then-act. Cần thực thi điều kiện **nguyên tử tại ranh giới cập nhật**: JPA optimistic lock khi flush/commit, conditional SQL UPDATE theo version, hoặc fencing ở downstream.

Cũng cần lưu ý `@Version` thường được cập nhật khi flush. Nếu publish event trong method transactional mà đọc `getVersion()` **trước flush**, giá trị có thể vẫn là version cũ. Nếu cần **committed version** trong event, thiết kế cách lấy version sau khi flush và chỉ xử lý event sau commit; kiểm tra behavior của JPA provider và transaction thực tế.

### 12.1. Conditional update ở database

Ví dụ SQL minh họa:

```sql
UPDATE orders
SET notification_state = 'SENT'
WHERE id = :order_id
  AND version = :expected_version
  AND notification_state = 'PENDING';
```

Số hàng update là tín hiệu quan trọng: 1 nghĩa là điều kiện phù hợp tại thời điểm database áp dụng câu lệnh; 0 nghĩa là record/version/state đã khác hoặc không tồn tại. Cần xử lý transaction, isolation và version increments đúng schema. **Đây chưa phải một fencing guarantee cho lệnh gửi email bên ngoài**, vì gửi email xảy ra ở hệ thống khác.

Đối với giao dịch cập nhật nhiều bảng, thiết kế transaction để check + thay đổi **cùng phạm vi nguyên tử**, không làm một `findById` rồi ghi tự do sau thời gian dài.

### 12.2. Ví dụ Java 17+: bảo vệ cập nhật bằng version

Tệp `VersionedUpdateDemo.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public class VersionedUpdateDemo {
    record State(long version, String status) {}

    static boolean updateIfVersion(
            AtomicReference<State> store,
            long expectedVersion,
            String newStatus) {

        while (true) {
            State current = store.get();

            if (current.version() != expectedVersion) {
                return false;
            }

            State next = new State(
                    current.version() + 1,
                    newStatus);

            if (store.compareAndSet(current, next)) {
                return true;
            }
        }
    }

    public static void main(String[] args) {
        AtomicReference<State> state =
                new AtomicReference<>(new State(1, "CREATED"));

        long oldVersion = state.get().version();

        state.set(new State(2, "APPROVED"));

        System.out.println("stale-applied=" +
                updateIfVersion(state, oldVersion, "SENT"));
        System.out.println("current-applied=" +
                updateIfVersion(state, 2, "SENT"));
        System.out.println("final=" +
                state.get().version() + ":" +
                state.get().status());
    }
}
```

```bash
javac VersionedUpdateDemo.java
java VersionedUpdateDemo
```

Stdout:

```text
stale-applied=false
current-applied=true
final=3:SENT
```

Đây là mô hình một JVM dùng `AtomicReference.compareAndSet`. So sánh version + cập nhật state được thực hiện nguyên tử bằng CAS trên **reference hiện tại**. Trong production có nhiều replica, dùng **database conditional update/optimistic locking**, không dựa vào một `AtomicReference` cục bộ.

Nếu tác dụng phụ là email/HTTP call, không thể đặt network I/O vào CAS để tạo transaction phân tán. Sử dụng outbox/idempotency/reconciliation theo hợp đồng hệ nhận.

## 13. Immutable snapshot còn phải an toàn về ownership và serialization

Một DTO tốt không nên dùng lại **JPA entity** bên trong:

**Không an toàn:**

```java
record OrderEvent(long id, OrderEntity entity) {}
record CustomerEvent(long id, List<CustomerEntity> customers) {}
```

Outer record bất biến về reference, nhưng `entity` và phần tử list vẫn mutable và có thể giữ lazy proxies.

**Tốt hơn:**

```java
record CustomerSnapshot(long id, String email) {}

record OrderEvent(
        long id,
        long revision,
        List<CustomerSnapshot> customers) {

    OrderEvent {
        customers = List.copyOf(customers);
    }
}
```

Ví dụ này có thể cần import `List`; là fragment định nghĩa DTO. Phải tạo `CustomerSnapshot` từ các scalar fields đã load trong transaction, không tạo một record chỉ để tiếp tục giữ entity reference.

### 13.1. Đừng lạm dụng serialize entity

Tránh phát entity toàn bộ qua JSON/Kafka/RabbitMQ vì:

- Trường lazy có thể bị truy cập ngoài session.
- Mối quan hệ hai chiều dẫn tới recursion hoặc payload lớn.
- Schema persistence khác schema event; đổi JPA mapping có thể phá consumer.
- Có thể vô tình rò dữ liệu cá nhân hoặc thông tin nội bộ.
- Entity có thể gắn behavior và invariant không phù hợp serialized contract.
- “Deserialized entity” không vì vậy tự là một **managed entity** trong transaction mới.

Message nên dùng event DTO có schema riêng, version khi cần, trường tối thiểu và ID hợp lệ. Các consumer phải có cách xử lý message cũ trong quá trình schema evolution.

### 13.2. ID không phải đủ nếu có nhiều tenant

Trong ứng dụng multi-tenant, chỉ truyền `orderId` có thể không đủ để xác định đúng phạm vi truy cập. Event nên có `tenantId`/scope cần thiết (không phải toàn bộ `SecurityContext` mutable), và worker phải kiểm tra quyền truy cập/tenant isolation tại nguồn dữ liệu authoritative. Đừng tin rằng vì controller đã được authenticate nên worker bất đồng bộ tự mang đầy đủ security context.

### 13.3. Version và event time không giống nhau

- `id` xác định tài nguyên.
- `version` xác định revision và hỗ trợ phát hiện stale update.
- `eventId` định danh một lần phát event/operation để deduplicate.
- `occurredAt` mô tả thời điểm sự kiện; không phải khóa concurrency đủ mạnh.
- `tenantId` xác định scope.
- `correlationId` hỗ trợ tracing và audit.

Chọn metadata có mục đích, tránh nhồi mọi trường vào một record.

## 14. @Async và transaction context là hai ranh giới khác nhau

Khi một method được gọi qua Spring `@Async` proxy, logic thường được submit lên executor và chạy trên thread khác. Spring transaction được quản lý dựa trên thread-bound context trong mô hình imperative phổ biến; transaction ở caller **không tự di chuyển sang worker**.

Các điều này cần phân biệt:

1. `@Async` bật chuyển cách thực thi qua proxy khi có `@EnableAsync`; không tự mở transaction.
2. `@Transactional` bật transaction advice khi method được intercept đúng; không tự tạo executor.
3. Một method có cả hai annotation có thể hoạt động theo thứ tự advice/config cụ thể; cách dễ kiểm soát hơn là **tách bean async worker và bean transactional loader** để boundary rõ ràng.
4. `@Transactional(readOnly = true)` trên loader mở context phù hợp với thread worker khi method được gọi qua proxy.
5. `this.loadById(id)` trong cùng bean có thể bypass transaction advice ở proxy mode; tách loader sang bean riêng hoặc dùng transaction mechanism phù hợp.
6. Context của caller có thể chứa object chưa flush/commit, nên ID re-fetch trong worker **trước commit** có thể không thấy thay đổi.

### 14.1. OpenEntityManagerInView không phải công cụ truyền context

OSIV có thể mở context trong thread request, nhưng **không** đưa cái context đó vào mọi `@Async`/`CompletableFuture` callback. Tránh dùng OSIV như giải pháp chính cho việc giữ graph sống. Kỹ thuật thiết kế đúng là query/projection/DTO và transaction scope ngắn rõ ràng.

### 14.2. Reactive context là mô hình khác

Với Spring WebFlux/R2DBC, transaction context có thể được truyền qua Reactor context thay vì `ThreadLocal`. Dù vậy, nguyên tắc message boundary vẫn hữu ích: không kéo tài nguyên/session gắn execution context qua thread hoặc callback không phù hợp. `@TransactionalEventListener` trong Spring 6.1+ cũng có hỗ trợ reactive transaction theo quy tắc riêng; cần dùng đúng event source/context. Không suy từ ví dụ JPA imperative ra cách xử lý reactive.

## 15. Khi nào truyền ID tốt hơn snapshot?

**Truyền ID** thường phù hợp khi:

- Worker phải đánh giá **trạng thái hiện tại** của entity.
- Quyền gửi/ghi phụ thuộc vào status, consent, subscription hoặc thông tin mới nhất.
- Object graph lớn, chỉ vài trường cần thiết và có repository query tối ưu.
- Job tồn tại lâu, qua nhiều retry/replica/restart.
- Event schema cần đơn giản, còn logic worker tự quyết định bằng domain state mới.

Ví dụ: “sau khi order được xác nhận, nếu hiện chưa gửi thông báo và chưa bị hủy, hãy gửi đúng một lần” → ID + kiểm tra state/version/idempotency trong worker.

**Bất lợi:** worker có thêm DB query, có thể thấy record đã thay đổi hoặc bị xóa; cần xử lý `not found` và consistency lag.

## 16. Khi nào snapshot bất biến tốt hơn ID?

**Immutable snapshot** thường phù hợp khi:

- Nội dung phải phản ánh **giá trị tại thời điểm event**.
- Consumer ở hệ khác không có quyền truy cập database nguồn.
- Không muốn một worker chậm đọc state mới và làm sai ngữ nghĩa lịch sử.
- Event là fact nghiệp vụ (“đơn đã được xác nhận với tổng tiền X”), không phải command “hãy đọc state mới nhất”.
- Muốn giảm coupling tới JPA mapping và database schema.

Ví dụ: audit/billing event cần amount, currency, approvedAt và revision **đúng lúc commit**. Snapshot phải được tạo từ dữ liệu hợp lệ và chỉ công bố sau commit; nếu cần độ bền qua crash, lưu outbox record cùng transaction.

**Bất lợi:** payload lớn hơn, cần version schema, bất biến sâu và chính sách xử lý thông tin nhạy cảm. Snapshot có thể **cố ý cũ** so với trạng thái hiện tại; consumer không nên dùng nó để ghi đè một aggregate mới hơn khi chưa có version/fencing.

## 17. Mẫu hybrid: ID + version + snapshot tối thiểu

Một event domain có thể dùng:

```java
public record OrderApprovedEvent(
        long orderId,
        long aggregateVersion,
        String approvedCurrency,
        long approvedAmountMinor,
        String eventId) {}
```

Đây là fragment value type Java 17. Consumer có thể:

- Dùng amount/currency snapshot để ghi audit sự kiện.
- Dùng `orderId` truy vấn thêm dữ liệu mới khi cần.
- Dùng `aggregateVersion` để phát hiện event cũ nếu làm state projection latest-wins.
- Dùng `eventId` để deduplicate retry/event redelivery.

Không có một field nào tự bảo đảm exactly-once qua mọi dịch vụ. Phải có unique constraint, conditional update hoặc downstream idempotency mechanism phù hợp.

### 17.1. Ví dụ SQL kiểm tra version khi áp dụng projection

```sql
UPDATE order_views
SET status = :status,
    source_version = :incoming_version
WHERE order_id = :order_id
  AND source_version < :incoming_version;
```

Đây là **SQL mẫu**, yêu cầu schema/transaction thích hợp và cơ chế xử lý hàng chưa tồn tại (UPSERT hợp lệ). Nó cho phép tránh một event version nhỏ hơn ghi đè projection mới hơn, nhưng chưa tự giải quyết insert race, duplicate event hay atomicity giữa nhiều bảng.

## 18. Transactional outbox cho event không được mất

`@TransactionalEventListener(AFTER_COMMIT)` tốt để nối logic với commit **trong một process đang sống**, nhưng **không** bảo đảm job tồn tại khi process chết ở khoảng giữa DB commit và listener/async queue.

Với yêu cầu at-least-once delivery:

```text
Trong transaction tạo/sửa order:
    UPDATE/INSERT order...
    INSERT outbox(event_id, order_id, version, immutable_payload)
COMMIT

Worker outbox:
    đọc event chưa giao
    publish/dispatch bằng retry có giới hạn
    consumer deduplicate theo event_id
    ghi trạng thái giao nhận
```

Đây là pseudocode kiến trúc, không phải SQL chạy độc lập. Khi ghi **order + outbox cùng DB transaction**, hoặc cả hai commit hoặc cả hai rollback. Consumer có thể nhận lại message, nên phải thiết kế **idempotency**. Event chứa ID hoặc immutable DTO/projection, **không chứa managed JPA entity**.

Nếu cần chống lệnh cũ đến sau lệnh mới, thêm `version`/fencing tại consumer; outbox không tự làm dữ liệu của event luôn là bản mới nhất.

### 18.1. Sau commit vẫn có thể có cạnh tranh sự kiện

Hai order events có thể được publish cùng lúc và worker xử lý không đúng thứ tự publish. Một event ID chỉ giúp dedup, không giúp sắp thứ tự. Với projection latest-wins, dùng aggregate version và conditional update. Với quy trình cần đúng một thứ tự toàn cục, phải thiết kế partitioning/order guarantee riêng.

## 19. Kiểm thử: chứng minh không chuyển managed entity qua boundary

Một test tốt phải nắm được transaction, thread, entity state và dữ liệu thực tế — không chỉ kiểm tra future đã complete.

### 19.1. Unit tests cho DTO

- Khởi tạo `OrderNoticeSnapshot` với `List` mutable, sửa list gốc sau đó và xác nhận snapshot không đổi.
- Thử sửa `snapshot.productCodes()` và xác nhận list không hỗ trợ `add`.
- Kiểm tra nested elements là immutable, không chỉ outer record.
- Kiểm tra null, missing fields, schema version và dữ liệu nhạy cảm bị loại bỏ.

Các ví dụ Java 17+ trong bài cung cấp dữ liệu mẫu để test deterministic.

### 19.2. Integration tests với JPA/Hibernate

1. Tạo order và lazy association trong transaction.
2. Load entity, tạo DTO **trong transaction**, đóng transaction.
3. Truy cập DTO trong worker thread và xác nhận không còn phụ thuộc vào Hibernate session.
4. Kiểm tra trường hợp cố tình mang một lazy proxy chưa nạp ra ngoài context và xác nhận hành vi provider tương ứng — thường là `LazyInitializationException` với Hibernate khi truy cập cần session. Không giả định tất cả entity reference luôn ném lỗi.
5. Đo query count để phát hiện N+1 từ projection; dùng fetch join/entity graph/DTO projection thích hợp.
6. Cho transaction rollback sau khi publish event, xác nhận `AFTER_COMMIT` listener không thực hiện side effect.
7. Publish event trong transaction thành công và xác nhận worker đọc dữ liệu **đã commit**.
8. Thay đổi entity trước khi worker load, kiểm tra ID path thấy state theo isolation, trong khi snapshot giữ state đã chụp.
9. Gây optimistic locking conflict và kiểm tra stale version bị từ chối.
10. Dừng ứng dụng sau DB commit nhưng trước khi dispatch, so sánh hành vi `@TransactionalEventListener` với outbox bền vững.

### 19.3. Không dùng sleep để dự đoán thứ tự

Dùng `CountDownLatch`/`CyclicBarrier`/`CompletableFuture` có timeout để điều phối *event published*, *transaction committed*, *worker started*, *worker allowed to query*. `Thread.sleep(100)` không bảo đảm transaction sẽ kịp commit hoặc worker sẽ chạy lúc mong muốn.

Ví dụ với integration test có thể giữ worker tại barrier, cho caller commit và thay đổi state, sau đó release. Kiểm tra ID path và snapshot path khác nhau. Với nhiều replica, cần kiểm tra isolation/concurrency trên DB thật thay vì chỉ in-memory map.

### 19.4. Proxy và transaction đúng thread

- `@EnableAsync` thực sự được nạp vào context?
- Method `@Async` có được gọi qua Spring-managed bean, không phải `this.method()`?
- `@Transactional` loader có được intercept qua bean khác?
- Thread executor được chọn có tên/bounds đúng?
- Method listener `AFTER_COMMIT` có được gọi khi transaction commit, bỏ qua khi rollback?
- Lỗi từ `CompletableFuture<Void>` được quan sát, không bị bỏ qua?
- Loader đóng transaction trước khi gửi external I/O kéo dài?

## 20. Sai lầm thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Truyền entity đang managed trực tiếp vào `@Async` | Dùng object graph/session qua thread; race/lazy failure | Truyền ID hoặc immutable DTO |
| Nghĩ chuyển thread sẽ tự detach entity | Entity vẫn có thể thuộc context của caller | Không chia sẻ context/entity giữa thread |
| Đọc lazy association ở worker sau khi transaction caller đóng | `LazyInitializationException` khi chưa load | Fetch/materialize DTO trong transaction hợp lệ |
| Bật OSIV để “chữa” async lazy loading | Che boundary, không đảm bảo thread-safe | Transaction riêng của worker + DTO |
| Truyền `List.copyOf(entities)` | Copy list nhưng phần tử vẫn là entity mutable | Map từng phần tử thành immutable snapshot |
| Đọc entity vào event trước commit rồi xử lý ngay | Worker thấy dữ liệu chưa commit/rollback | AFTER_COMMIT hoặc outbox |
| Nghĩ `@TransactionalEventListener` luôn chạy async | Mặc định listener theo pha, không phải executor riêng | Gọi `@Async` worker qua proxy hoặc cấu hình rõ |
| Nghĩ AFTER_COMMIT bảo đảm durable delivery | JVM chết có thể mất event in-memory | Transactional outbox/queue |
| Truyền ID rồi tin worker sẽ thấy snapshot tại event | Re-fetch có thể thấy state mới | Truyền snapshot nếu cần historical fact |
| Truyền snapshot rồi dùng để cập nhật state mới nhất | Snapshot có thể cũ | Version/conditional update, domain invariant |
| Đọc `@Version` trước flush rồi tưởng committed revision | Version có thể chưa được tăng | Kiểm chứng flush/commit và payload version |
| Dùng `@Transactional` trên self-invoked helper | Advice có thể bị bypass | Tách transactional loader sang bean khác |
| Giữ transaction DB trong lúc gọi email/HTTP lâu | Giữ tài nguyên và tăng contention | Copy DTO, đóng transaction rồi gọi gateway |
| Mang `SecurityContext`/`HttpServletRequest` sang worker | Context request/thread không còn hợp lệ | Truyền ID/scope an toàn, xác thực lại ở boundary |
| Serialize whole JPA entity ra broker | Lazy recursion, schema coupling, rò dữ liệu | Message schema riêng |
| Dùng ID không kèm tenant scope | Truy cập sai dữ liệu trong multi-tenant | Tenant isolation và authorization authoritative |
| Bỏ lỗi future của worker | Job thất bại âm thầm | Theo dõi completion, metrics, retry/durable job |

## 21. Bài tập thực hành

### Bài 1 — Refactor async service

Cho code:

```java
@Transactional
public void createOrder(OrderEntity entity) {
    repository.save(entity);
    worker.sendEmail(entity);
}
```

Thiết kế lại thành: transactional service persist order và publish `OrderCommitted(orderId)`; listener `AFTER_COMMIT` dispatch `worker.sendEmail(orderId)`; worker gọi một `@Transactional(readOnly=true)` loader riêng để lấy immutable payload. Giải thích vì sao không dùng `entity` làm tham số async.

### Bài 2 — Snapshot các lazy associations

Cho `OrderEntity` có `List<OrderLineEntity> lines` lazy. Viết query fetch phù hợp, tạo `OrderNoticeSnapshot` với `List<LineSnapshot>` mà mọi element đều immutable, thử đóng persistence context và dùng snapshot ở worker thread.

### Bài 3 — Trạng thái mới nhất hay lịch sử?

Order ở phiên bản 8 khi phát event nhưng chuyển sang phiên bản 9 trước khi worker chạy. Hãy xác định behavior mong muốn cho (a) email hóa đơn lịch sử, (b) gửi thông báo nếu order chưa hủy, (c) cập nhật search projection. Chọn ID, snapshot hoặc ID+version và giải thích.

### Bài 4 — Optimistic locking

Viết test có hai worker dùng cùng `expectedVersion`. Worker đầu update thành công; worker sau phải nhận `OptimisticLockException`/số hàng conditional UPDATE bằng 0 theo implementation. Không cho một dữ liệu cũ ghi đè dữ liệu mới.

### Bài 5 — Ranh giới event và retry

Thử rollback transaction sau khi publish event; kiểm tra listener `AFTER_COMMIT` không chạy. Sau đó giả lập process chết sau commit trước listener; giải thích vì sao outbox mới có thể khôi phục công việc. Thêm `eventId` để consumer deduplicate retry.

### Bài 6 — Multi-tenant và bảo vệ dữ liệu

Thiết kế event chỉ có `tenantId`, `orderId`, `eventId` và các trường snapshot thật cần thiết. Worker query theo cả tenant và ID, không dựa vào SecurityContext request, tránh log email/full payload. Test một event tenant A không thể đọc order tenant B.

### Bài 7 — Deep immutability

Thay `List<String>` bằng `List<MutableLine>` trong record và thấy `List.copyOf` không chặn thay đổi field phần tử. Sửa bằng mapping từng line thành `record LineSnapshot` bất biến. Viết assertion sau khi mutate source.

## 22. Checklist trước khi đưa vào production

- [ ] Tôi biết entity managed và persistence context là hai khái niệm gắn với một unit of work, không phải message payload.
- [ ] Tôi không chia sẻ target `EntityManager`/Hibernate Session hoặc managed entity graph đồng thời giữa thread.
- [ ] Tôi chọn ID khi worker cần fresh state; snapshot khi worker cần state tại event; ID+version khi cần stale guard.
- [ ] Tôi không truy cập lazy association của entity trong background thread ngoài context phù hợp.
- [ ] Snapshot được tạo trong transaction hợp lệ và immutable **cả nested elements cần thiết**.
- [ ] Tôi không nghĩ `@Async` chuyển transaction hoặc request context sang worker.
- [ ] Tôi dùng bean transactional loader riêng và gọi nó qua Spring proxy.
- [ ] Tôi hiểu `@TransactionalEventListener(AFTER_COMMIT)` không đồng nghĩa với async/durability.
- [ ] Tôi không giữ transaction DB lâu khi gọi network/email bên ngoài.
- [ ] Tôi có optimistic locking/fencing nếu bản cập nhật cũ không được ghi đè bản mới.
- [ ] Tôi có outbox/idempotency khi event bắt buộc được giao và có thể retry.
- [ ] Tôi kiểm soát tenant scope, quyền truy cập và nội dung nhạy cảm trong payload.
- [ ] Tôi có test lazy loading, rollback, commit, re-fetch, snapshot, stale version và restart.

**Kết luận:** trong Spring concurrency, cách an toàn là **đi qua async/event boundary bằng những giá trị có hợp đồng rõ ràng** — ID, immutable snapshot hoặc ID+version — thay vì chuyển entity còn gắn persistence context. Worker tự mở transaction cần thiết, materialize DTO bên trong boundary đó và kiểm soát side effect sau commit. Kết quả là code có vòng đời minh bạch, ít phụ thuộc Hibernate session, dễ test cạnh tranh và dễ mở rộng qua queue/replica.

## 23. Tài liệu tham khảo chính thức

- Hibernate ORM — [User Guide, Persistence Context](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): managed/detached, session lifecycle, dirty checking, lazy loading và thread-safety.
- Hibernate ORM — [An Introduction to Hibernate 6](https://docs.hibernate.org/orm/6.6/introduction/html_single/): vì sao Session/EntityManager không được chia sẻ giữa thread.
- Spring Framework — [Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): các pha `@TransactionalEventListener` và `fallbackExecution`.
- Spring Framework Javadoc — [TransactionalEventListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): lưu ý nguồn lực sau `AFTER_COMMIT`.
- Spring Framework — [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, executor và lifecycle.
- Spring Framework — [Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): Spring transaction proxy và ranh giới `@Transactional`.
- Jakarta Persistence — [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): entity lifecycle, persistence context và `@Version`.

Hãy đối chiếu phiên bản Spring/JPA/Hibernate trong project. Các snippet Spring/JPA và SQL ở trên là **mẫu tích hợp cần có domain, imports và dependencies thực tế**; các ví dụ ghi rõ `javac`/`java` là chương trình Java 17+ độc lập.
