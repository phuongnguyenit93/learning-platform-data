# Flush rồi clear theo từng lô để giới hạn Persistence Context

Khi dùng Hibernate/JPA để `persist()` hoặc cập nhật hàng chục nghìn, hàng trăm nghìn entity trong một transaction, đoạn code có thể chạy đúng ở quy mô nhỏ nhưng tiêu thụ ngày càng nhiều bộ nhớ, chậm dần và cuối cùng gặp áp lực GC hoặc `OutOfMemoryError`.

Một nguyên nhân lớn là **Persistence Context** (*first-level cache*). Mỗi entity đang được quản lý có thể cần identity entry, trạng thái theo dõi thay đổi (*dirty checking*), các collection/proxy liên quan và những cấu trúc nội bộ của Hibernate. Nếu cứ tiếp tục đưa entity mới vào cùng một context mà không giải phóng những entity đã hoàn tất, chi phí quản lý sẽ tăng theo tổng số object tích lũy, ngay cả khi database xử lý INSERT khá nhanh.

Kỹ thuật cơ bản để ghi theo lô là:

```java
entityManager.persist(entity);

if (processed % chunkSize == 0) {
    entityManager.flush();
    entityManager.clear();
}
```

Trong đó:

- `flush()` yêu cầu Hibernate **đồng bộ các thay đổi đang chờ** từ Persistence Context sang database bằng các thao tác SQL phù hợp.
- `clear()` **detach toàn bộ entity** khỏi Persistence Context để Hibernate không tiếp tục giữ và dirty-check chúng.
- `chunkSize` giới hạn số lượng object/aggregate được xử lý trước mỗi lần flush/clear.
- **Không có `commit()` ở hai lệnh trên**: việc commit hoặc rollback vẫn do transaction quản lý.

`flush()` và `clear()` không thay thế **JDBC batching** (`hibernate.jdbc.batch_size`), cũng không bảo đảm một transaction khổng lồ sẽ trở nên phù hợp cho production. Chúng giải quyết những lớp vấn đề khác nhau. Bài học phân tích từng lớp, cách triển khai an toàn, các lỗi với entity detached/cascade, chiến lược transaction theo chunk và cách đo lường hiệu quả.

## 1. Vì sao ghi nhiều entity làm Persistence Context phình to?

Xét đoạn code:

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

for (int i = 0; i < 100_000; i++) {
    OrderEvent event = new OrderEvent(...);
    em.persist(event);
}

tx.commit();
```

Nếu không có thao tác giải phóng context, sau hàng chục nghìn lần `persist()` Hibernate có thể còn quản lý một lượng rất lớn `OrderEvent`.

Hình dung:

```text
EntityManager / Hibernate Session
  |
  └─ Persistence Context (L1 cache)
       ├─ OrderEvent#1    [managed]
       ├─ OrderEvent#2    [managed]
       ├─ OrderEvent#3    [managed]
       ├─ ...
       ├─ OrderEvent#50_000 [managed]
       └─ OrderEvent#100_000 [managed]
               |
               v
         Tăng heap + GC + chi phí quản lý
```

Persistence Context làm những việc hữu ích:

1. Đảm bảo một persistent identity có một managed representation trong context.
2. Giữ thông tin quản lý lifecycle và trạng thái.
3. Theo dõi thay đổi của entity đã được load hoặc persist.
4. Giữ các proxy/collection wrappers liên quan.
5. Hỗ trợ flush thay đổi theo một đơn vị công việc.

Nhưng lợi ích này không miễn phí. Trong import lớn, ta thường **không cần giữ 100.000 entity managed cùng lúc** sau khi đã gửi các thay đổi của chúng xuống database.

### 1.1. Không phải toàn bộ heap đều do Hibernate giữ

Ngay cả khi gọi `clear()`, nếu application vẫn giữ:

```java
List<OrderEvent> all = new ArrayList<>();

for (...) {
    OrderEvent event = new OrderEvent(...);
    all.add(event);
    em.persist(event);
}
```

thì `all` vẫn tham chiếu tới mọi object; GC không thể thu hồi chúng. `clear()` chỉ giải phóng các tham chiếu quản lý trong Persistence Context, **không xóa các Java references ở nơi khác**.

Để thực sự giới hạn memory, input và output cũng cần được đọc/xử lý theo luồng hoặc từng phần có giới hạn.

## 2. `persist()`, `flush()`, `clear()` và `commit()` khác nhau thế nào?

| Thao tác | Ý nghĩa chính | Entity còn managed? | SQL có thể được gửi? | Transaction đã commit? |
| --- | --- | --- | --- | --- |
| `persist(x)` | Chuyển entity mới thành managed, lên kế hoạch INSERT | Có | Có thể, tùy ID strategy/cascade | Chưa |
| `flush()` | Đồng bộ pending changes vào DB | Có | Có; thực thi INSERT/UPDATE/DELETE cần thiết | Chưa |
| `clear()` | Detach tất cả managed entities khỏi context | Không | Không phải thao tác flush | Chưa |
| `detach(x)` | Detach một entity cụ thể | Với `x`: không | Không tự flush | Chưa |
| `commit()` | Kết thúc transaction thành công | Tùy lifecycle của context | Có thể auto-flush trước commit | Có |
| `rollback()` | Hủy các thay đổi trong transaction DB | Không tự phục hồi object graph Java | DB rollback các SQL trong tx | Không |

**Flush là đồng bộ SQL trong transaction, không phải commit.** Sau `flush()`, một lần `rollback()` vẫn có thể hoàn tác các INSERT/UPDATE/DELETE của cùng transaction.

**Clear là detach, không phải xóa database.** Sau `clear()`, dữ liệu đã flush vẫn đang ở trong transaction; nếu transaction rollback, dữ liệu đó không được commit.

### 2.1. Dòng thời gian của một lô

```text
BEGIN TRANSACTION
  persist #1
  persist #2
  ...
  persist #50
      |
      v
  FLUSH
      └─ SQL gửi tới database trong transaction
      |
      v
  CLEAR
      └─ Các entity trong lô không còn managed
  persist #51
  ...
  FLUSH
  CLEAR
  COMMIT
      └─ Database commit tất cả các lô trong transaction
```

Nếu lỗi trước `COMMIT`, transaction có thể rollback **tất cả lô đã flush**. Điều đó rất khác chiến lược commit sau mỗi chunk.

## 3. Mô hình ví dụ: nhập nhiều `OrderEvent`

Để tập trung vào batch insert, dùng một entity đơn giản:

```java
import jakarta.persistence.*;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(
    name = "order_events",
    indexes = {
        @Index(
            name = "idx_order_events_order_id",
            columnList = "order_id"
        )
    }
)
public class OrderEvent {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "order_event_seq"
    )
    @SequenceGenerator(
        name = "order_event_seq",
        sequenceName = "order_event_seq",
        allocationSize = 50
    )
    private Long id;

    @Column(name = "order_id", nullable = false)
    private Long orderId;

    @Column(name = "event_type", nullable = false, length = 40)
    private String eventType;

    @Column(name = "occurred_at", nullable = false)
    private Instant occurredAt;

    @Column(name = "payload", nullable = false, length = 1000)
    private String payload;

    protected OrderEvent() {}

    public OrderEvent(
        Long orderId,
        String eventType,
        Instant occurredAt,
        String payload
    ) {
        this.orderId = Objects.requireNonNull(orderId);
        this.eventType = Objects.requireNonNull(eventType);
        this.occurredAt = Objects.requireNonNull(occurredAt);
        this.payload = Objects.requireNonNull(payload);
    }

    public Long getId() { return id; }
}
```

Ví dụ dùng `SEQUENCE` với `allocationSize = 50` vì chiến lược này có thể hỗ trợ cấp phát ID theo nhóm và JDBC insert batching tốt hơn `IDENTITY` trong nhiều cấu hình Hibernate.

**Lưu ý DBMS:** `GenerationType.SEQUENCE` cần database/dialect hỗ trợ sequence và cấu hình sequence phù hợp. Với H2/PostgreSQL, có thể cần migration tạo sequence. Nếu database sequence đã có, increment/allocation phải tương thích với mapping và cách Hibernate kiểm tra schema.

Input DTO:

```java
import java.time.Instant;

public record EventInput(
    Long orderId,
    String eventType,
    Instant occurredAt,
    String payload
) {}
```

`EventInput` là dữ liệu đầu vào, không phải entity managed.

## 4. Code mẫu một transaction và flush/clear định kỳ

Giả định caller cung cấp `Iterator<EventInput>` không giữ toàn bộ dữ liệu trong heap.

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import java.util.Iterator;

public final class EventImporter {

    private final EntityManagerFactory emf;

    public EventImporter(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public long importEvents(
            Iterator<EventInput> input,
            int chunkSize
    ) {
        if (chunkSize <= 0) {
            throw new IllegalArgumentException(
                "chunkSize must be positive"
            );
        }

        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        long processed = 0;

        try {
            tx.begin();

            while (input.hasNext()) {
                EventInput item = input.next();

                OrderEvent event = new OrderEvent(
                    item.orderId(),
                    item.eventType(),
                    item.occurredAt(),
                    item.payload()
                );

                em.persist(event);
                processed++;

                if (processed % chunkSize == 0) {
                    em.flush();
                    em.clear();
                }
            }

            if (processed % chunkSize != 0) {
                em.flush();
                em.clear();
            }

            tx.commit();
            return processed;
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        } finally {
            em.close();
        }
    }
}
```

Đây là chiến lược **một transaction duy nhất**, nhưng Hibernate chỉ tích lũy tối đa khoảng một chunk các entity `OrderEvent` đơn giản đang chờ trong Persistence Context giữa các lần `clear()`.

Nếu có 10.023 events và `chunkSize = 100`:

```text
100 events -> flush -> clear
100 events -> flush -> clear
...
100 events -> flush -> clear
23 events  -> flush -> clear
commit
```

Tổng là 101 lượt xử lý flush/clear: 100 lô đầy đủ và một lô cuối 23 events.

### 4.1. Vì sao cuối vòng lặp phải xử lý phần dư?

Nếu chỉ flush khi:

```java
processed % chunkSize == 0
```

thì lô cuối chưa đủ `chunkSize` vẫn còn pending. Khi commit với flush mode bình thường, Hibernate thường tự flush, nhưng **không nên dựa hoàn toàn vào commit khi muốn có một thuật toán chunk rõ ràng**.

Đoạn:

```java
if (processed % chunkSize != 0) {
    em.flush();
    em.clear();
}
```

làm ranh giới lô cuối tường minh. Nếu `processed == 0` hoặc số lượng chia hết cho batch size, nhánh này không chạy.

### 4.2. Có bắt buộc clear sau lượt flush cuối không?

Không. Nếu chỉ còn commit rồi đóng EntityManager, clear cuối có thể không cần thiết cho memory vì context sẽ được đóng ngay. Nhưng dùng cặp `flush(); clear();` nhất quán giúp mô tả rõ vòng đời từng chunk.

Nếu sau import còn cần dùng entity managed trong cùng transaction, việc clear toàn bộ context có thể không phù hợp; cần thiết kế ranh giới quản lý state thay vì áp dụng máy móc.

### 4.3. Đừng giả định Context size luôn đúng bằng chunkSize

Một `persist(parent)` có thể cascade tạo hàng trăm child entities. Một query trong vòng lặp có thể load thêm nhiều entity. Vì vậy số managed instances có thể lớn hơn số lần lặp `processed`.

`chunkSize` ở ví dụ này là **số input records**, không phải một lời hứa Hibernate chỉ giữ chính xác từng ấy object.

## 5. Vì sao thứ tự phải là `flush()` rồi `clear()`?

Thứ tự đúng:

```java
em.flush();
em.clear();
```

Thứ tự nguy hiểm:

```java
em.clear();
em.flush();
```

`clear()` detach mọi entity. Những thay đổi chưa flush có thể không được database đồng bộ vì Hibernate không còn theo dõi các object đó.

Ví dụ:

```java
OrderEvent event = new OrderEvent(...);
em.persist(event);

em.clear(); // Không nên detach trước khi đảm bảo pending work đã flush.
em.flush();
```

Đừng nghĩ lệnh `flush()` phía sau sẽ “tìm lại” những entity đã bị detach rồi tự viết SQL theo toàn bộ state Java. Nó chỉ xử lý những thay đổi còn nằm trong Persistence Context theo semantics provider.

**Quy tắc:** nếu muốn giải phóng context mà vẫn lưu tất cả công việc của chunk, phải flush thành công **trước** khi clear.

## 6. `clear()` thay đổi trạng thái entity như thế nào?

Trước clear:

```java
em.persist(event);

System.out.println(em.contains(event)); // true
```

Sau flush/clear:

```java
em.flush();
em.clear();

System.out.println(em.contains(event)); // false
```

Entity `event` đã trở thành **detached**.

Hệ quả:

- Sửa field trên `event` sau clear **không tự động được dirty-check**.
- Lazy association chưa khởi tạo có thể không tải được nếu context gốc không còn liên kết phù hợp.
- Muốn tiếp tục thao tác managed, có thể tải lại bằng `find()` hoặc dùng `merge()` theo lifecycle phù hợp.
- `event.getId()` có thể vẫn trả ID đã cấp phát; detach không xóa field ID.
- `clear()` không đặt ID về `null`, không xóa row trong database và không commit.

### 6.1. Không sửa detached entity rồi mong tự lưu

```java
em.persist(event);
em.flush();
em.clear();

event.setPayload("changed"); // Giả sử có setter.
// Không có managed dirty checking cho sự thay đổi này.
```

Nếu muốn sửa sau clear, phải chủ động làm việc với managed instance trong transaction:

```java
OrderEvent managed = em.find(OrderEvent.class, event.getId());
managed.updatePayload("changed");
```

Hoặc, nếu thực sự cần merge detached object:

```java
OrderEvent managedCopy = em.merge(event);
```

`merge()` trả **managed copy**, còn `event` ban đầu vẫn detached. Không nên merge hàng chục nghìn graph phức tạp chỉ để “undo” một `clear()` không cần thiết.

## 7. `flush()` có thể phát SQL sớm hơn dự kiến

Trong ví dụ, ta đặt flush sau mỗi chunk. Nhưng Hibernate có thể phải thực hiện SQL **trước thời điểm đó**:

- ID generator `IDENTITY` có thể cần INSERT sớm để lấy ID.
- Một query trong vòng lặp có thể kích hoạt auto-flush ở flush mode `AUTO`.
- Cascade/constraint hoặc các thao tác khác có thể cần đồng bộ theo cơ chế provider.
- Code có thể gọi `flush()` tường minh ở helper/repository khác.

Vì vậy, khi đo số lần thực thi SQL, đừng suy luận chỉ từ số lần bạn gọi `flush()`.

### 7.1. `persist()` không phải luôn chỉ lưu trong RAM

Với `SEQUENCE`, Hibernate có thể lấy/gán identifier trước rồi hoãn INSERT tới flush. Với `IDENTITY`, INSERT có thể cần xảy ra ngay để lấy generated key, tùy provider/configuration.

Điểm quan trọng là **lịch INSERT và cơ hội JDBC batching phụ thuộc ID strategy**.

## 8. `hibernate.jdbc.batch_size` khác `chunkSize`

Hai khái niệm thường bị gọi chung là “batch”, nhưng chức năng khác nhau:

- `hibernate.jdbc.batch_size`: số statement DML tương thích Hibernate/JDBC cố gắng gom trong một JDBC batch.
- `chunkSize` trong code: số entity/input xử lý trước khi `flush()` và `clear()` để quản lý kích thước Persistence Context.

Ví dụ:

```properties
hibernate.jdbc.batch_size=25
```

và:

```java
int chunkSize = 100;
```

Có thể hiểu khái niệm:

```text
100 entity managed trong một chunk
        |
        | flush
        v
JDBC layer có thể gom các INSERT tương thích
        |
        ├─ batch khoảng 25 statements
        ├─ batch khoảng 25 statements
        ├─ batch khoảng 25 statements
        └─ batch khoảng 25 statements
        |
        v
clear -> detach entity khỏi Persistence Context
```

Đây là hình minh họa. Nếu INSERT thuộc nhiều bảng/SQL shapes khác nhau, hoặc driver/ID strategy không hỗ trợ, số JDBC batches có thể khác nhiều.

### 8.1. Bảng so sánh

| Tiêu chí | JDBC batching | Flush/clear theo chunk |
| --- | --- | --- |
| Mục tiêu | Giảm chi phí round trip khi gửi DML | Giới hạn managed state/dirty-checking |
| Điều khiển chính | `hibernate.jdbc.batch_size` | Biến `chunkSize` và `em.flush()/clear()` |
| Đơn vị | JDBC statement batch | Entity/input units trong context |
| Tác động đến memory L1 | Không tự giải phóng managed entities | Có, sau `clear()` |
| Tác động transaction | Không tự commit | Không tự commit |
| Có thể dùng riêng | Có | Có |
| Nên phối hợp khi insert/update lớn | Thường có | Thường có |

### 8.2. Đừng nhầm với `@BatchSize`

```java
@org.hibernate.annotations.BatchSize(size = 16)
```

và:

```properties
hibernate.default_batch_fetch_size=16
```

là các cơ chế **batch fetching khi đọc lazy entities/collections**, không phải JDBC insert/update batching.

## 9. Cấu hình Hibernate JDBC batching

Với Hibernate ORM:

```properties
hibernate.jdbc.batch_size=25
hibernate.order_inserts=true
hibernate.order_updates=true
```

Với Spring Boot:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=25
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

Giải thích:

- `hibernate.jdbc.batch_size`: kích thước JDBC batch mặc định.
- `hibernate.order_inserts`: cho Hibernate cơ hội sắp xếp nhóm INSERT theo entity type/SQL shape, có thể tăng batching.
- `hibernate.order_updates`: sắp xếp UPDATE theo entity type/PK, có thể tăng batching hoặc giảm deadlock trong một số workload.

**Không phải cứ bật ba setting thì mọi DML chắc chắn được batch.** ID generator, SQL shape, driver, cascade, version handling và statement ordering đều ảnh hưởng.

### 9.1. Batch size hợp lý là bao nhiêu?

Giá trị 20–50 thường là điểm khởi đầu thử nghiệm trong nhiều hướng dẫn Hibernate, nhưng không phải quy tắc cố định. Với workload thực tế, hãy benchmark 10, 25, 50 hoặc giá trị khác.

Một batch rất lớn có thể:

- Tăng số parameter/statement giữ ở driver.
- Tăng memory buffers.
- Làm quá trình báo lỗi/diagnostic khó hơn.
- Gặp giới hạn driver hoặc database.
- Không cải thiện nếu bottleneck là disk index/constraint thay vì network round trip.

### 9.2. Cấu hình riêng từng Session

Hibernate version hiện đại có API có thể đặt JDBC batch size ở scope Session:

```java
import org.hibernate.Session;

Session session = em.unwrap(Session.class);
session.setJdbcBatchSize(25);
```

Cần kiểm tra API của version đang sử dụng và nhớ rằng đây là Hibernate-specific. `chunkSize` trong vòng lặp vẫn do code ứng dụng quản lý.

## 10. `GenerationType.IDENTITY` có thể cản trở JDBC INSERT batching

Ví dụ:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Khi dùng identity column, Hibernate thường phải thực hiện INSERT để lấy generated identifier cho entity. Hibernate User Guide ghi nhận identity-based ID generation làm Hibernate không sử dụng JDBC batching cho INSERT trong trường hợp thông thường.

Điều này có nghĩa:

```properties
hibernate.jdbc.batch_size=50
```

**không đủ** để bảo đảm 50 INSERT entity dùng `IDENTITY` được gửi thành JDBC batch.

So sánh khái quát:

| ID strategy | Đặc điểm | Ảnh hưởng đến insert batching |
| --- | --- | --- |
| `IDENTITY` | DB sinh ID tại INSERT | Thường cản trở Hibernate JDBC INSERT batching |
| `SEQUENCE` | ORM có thể lấy ID trước INSERT | Có thể batch INSERT tốt hơn |
| Sequence với allocation/pooling | Hibernate lấy trước nhiều ID từ sequence | Giảm round trip cấp ID, thuận lợi batching |
| Assigned UUID/ID | ID có trước INSERT | Có thể batch, nhưng cần xét mapping và index |
| `TABLE` generator | Dùng bảng cấp ID | Có overhead/lock, thường không phải lựa chọn ưu tiên nếu DB có sequence |

Không thay đổi ID strategy trên hệ thống production chỉ để “bật batch”: migration, uniqueness, sequence allocation, foreign keys và dữ liệu cũ cần được kiểm tra.

### 10.1. `allocationSize` của sequence

```java
@SequenceGenerator(
    name = "order_event_seq",
    sequenceName = "order_event_seq",
    allocationSize = 50
)
```

giúp Hibernate có thể cấp phát một nhóm ID mà không cần hỏi database cho từng entity.

Nhưng DB sequence và mapping allocation cần tương thích với optimizer/DDL thực tế. Trong dự án dùng schema validation, mismatch có thể dẫn đến lỗi bootstrap. Một migration phải được lập kế hoạch nếu thay đổi allocation trên schema đã vận hành.

## 11. Batch INSERT với quan hệ và cascade

Không phải mọi vòng lặp chỉ persist một entity độc lập.

Giả sử:

```text
Order
  ├─ OrderLine
  ├─ OrderLine
  └─ OrderLine
```

Một lần:

```java
em.persist(order);
```

có thể cascade persist tới các `OrderLine` nhờ:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines;
```

Nếu một order có 500 lines, `chunkSize = 50 orders` có thể tạo **hơn 25.000 managed entities** trong một chunk.

### 11.1. Chọn đơn vị chunk theo aggregate graph

Đơn vị chunk có thể là:

- Số entity đơn giản.
- Số aggregate roots.
- Ước lượng tổng entity con.
- Dung lượng payload đã đọc.
- Số lượng DML dự kiến.
- Memory/latency giới hạn theo benchmark.

Không khẳng định `chunkSize=100` tương đương “chỉ 100 entities trong L1”.

### 11.2. Giữ thứ tự quan hệ hợp lệ

Nếu child có FK `NOT NULL` tới parent, SQL phải thỏa dependency. Hibernate thường lập kế hoạch action ordering theo mapping/cascade nhưng không nên dùng thứ tự list Java để cam kết thứ tự SQL duy nhất.

Cần:

- Thiết lập owning side của relationship.
- Cascade persist đúng phạm vi aggregate.
- Kiểm tra FK constraints trên database.
- Không clear khi child vẫn chưa được persist/flush đúng.
- Không dùng CascadeType.ALL lên association tới entity dùng chung chỉ để tiết kiệm lệnh persist.

## 12. Không giữ parent managed xuyên nhiều chunk một cách vô ý

Giả sử cùng một `Customer` được dùng cho 10.000 `OrderEvent`.

```java
Customer customer = em.find(Customer.class, customerId);

for (...) {
    // persist các child có association tới customer
    ...
    em.flush();
    em.clear();
}
```

Sau `em.clear()`, biến `customer` vẫn tồn tại trong Java nhưng là **detached**.

Nếu tiếp tục dùng nó như một managed object và cascade PERSIST không phù hợp, Hibernate có thể báo lỗi liên quan detached entity hoặc không theo dõi thay đổi như mong muốn.

Các hướng:

1. Đừng cache một managed parent instance xuyên các chunk sau clear.
2. Lưu **ID**, rồi lấy `em.getReference(Customer.class, customerId)` trong context hiện tại khi cần gán FK.
3. Hoặc `em.find()` lại nếu cần state/thẩm định.
4. Không cascade persist tới một parent đã tồn tại và được chia sẻ chỉ vì child mới cần tham chiếu nó.

Ví dụ:

```java
Long customerId = ...;

for (...) {
    Customer customerRef =
        em.getReference(Customer.class, customerId);

    OrderEvent event = ...; // Nếu event có association tới Customer.
    event.setCustomer(customerRef);

    em.persist(event);

    if (++count % chunkSize == 0) {
        em.flush();
        em.clear();
    }
}
```

Đây là phác thảo cho một entity có `Customer` association, **khác entity `OrderEvent` chỉ chứa `Long orderId` ở phần đầu bài**. `getReference()` có thể tạo proxy mà chưa kiểm tra row tồn tại; FK/constraint hoặc một access sau đó mới phát hiện ID không hợp lệ.

## 13. Batch UPDATE và dirty checking theo lô

Import không phải use case duy nhất. Có thể cần cập nhật hàng trăm nghìn order.

Mẫu xử lý:

```java
long updated = 0L;

tx.begin();

for (Long id : orderIds) {
    PurchaseOrder order =
        em.find(PurchaseOrder.class, id);

    if (order == null) {
        continue;
    }

    order.setStatus(OrderStatus.ARCHIVED);
    updated++;

    if (updated % chunkSize == 0) {
        em.flush();
        em.clear();
    }
}

if (updated % chunkSize != 0) {
    em.flush();
    em.clear();
}

tx.commit();
```

Ở đây `setStatus()` là method nghiệp vụ minh họa, `PurchaseOrder`/`OrderStatus` phải được định nghĩa trong ứng dụng.

Hibernate dirty-check các managed entities và tạo `UPDATE` khi flush nếu state thay đổi phù hợp.

### 13.1. Batch UPDATE khác `update query`

Hai cách:

**Entity-by-entity:**

```java
Order order = em.find(Order.class, id);
order.archive();
```

- Sử dụng lifecycle và dirty checking.
- Có thể kích hoạt callbacks.
- Có thể áp dụng optimistic version check.
- Cần quản lý L1 context và số SELECT.

**Bulk HQL/SQL:**

```java
int affected = em.createQuery("""
    update Order o
    set o.status = :status
    where o.status = :oldStatus
    """)
    .setParameter("status", OrderStatus.ARCHIVED)
    .setParameter("oldStatus", OrderStatus.COMPLETED)
    .executeUpdate();
```

- Một bulk statement có thể xử lý nhiều rows.
- Không qua dirty checking từng entity như khi thay đổi managed object.
- Có thể bỏ qua entity callbacks/version semantics mặc định; cần thiết kế rõ.
- Persistence Context đã load entities có thể giữ state cũ.

Nếu chỉ thay một cột trên rất nhiều hàng và không cần entity lifecycle, bulk UPDATE có thể phù hợp hơn loop `find` + flush/clear. Nhưng không coi hai cách là tương đương về behavior.

## 14. Tránh `merge()` hàng loạt nếu không cần

Một cách dễ mắc lỗi:

```java
for (DetachedOrder order : input) {
    em.merge(order);
}
```

Vấn đề không chỉ là memory:

- `merge()` có thể cần SELECT để lấy managed state.
- Cascade MERGE có thể đi qua object graph lớn.
- `merge()` trả **managed copy**, không làm object được truyền trở thành managed.
- Detached graph stale có thể ghi đè field hoặc association mới hơn.
- `@Version`/optimistic locking có thể báo conflict tại merge/flush.
- Sau `clear()`, mọi managed copy cũng bị detach.

Nếu input chỉ chứa ID và vài trường cần sửa, thường rõ hơn:

```java
Order managed = em.find(Order.class, input.id());
managed.changeStatus(input.newStatus());
```

và flush/clear theo chunk. Hoặc dùng update query có version/constraint phù hợp khi không cần lifecycle.

Không lấy `merge()` làm giải pháp tự động để né mọi lỗi detached sau clear.

## 15. Nhiều transaction theo chunk: khác một transaction lớn

Một transaction lớn với nhiều lần flush/clear vẫn giữ:

- Transaction DB mở tới cuối toàn bộ import.
- Các row locks/transaction resources tùy loại DML/isolation.
- Undo/WAL/redo logs và MVCC snapshots cho transaction dài.
- Rủi ro rollback toàn bộ nếu có một lỗi ở cuối.

Với import hàng triệu rows, dù L1 memory đã được giới hạn, **database transaction vẫn có thể quá lớn**.

Một chiến lược khác là **mỗi chunk là một transaction riêng**:

```text
Chunk 1: BEGIN -> persist -> flush -> COMMIT
Chunk 2: BEGIN -> persist -> flush -> COMMIT
Chunk 3: BEGIN -> persist -> flush -> COMMIT
...
```

Điều này giảm thời gian giữ một transaction, nhưng đánh đổi:

- Chunk đã commit không bị rollback nếu chunk sau lỗi.
- Import không còn atomic ở mức toàn bộ file.
- Cần thiết kế retry, idempotency, checkpoint và trạng thái job.
- Người đọc có thể thấy dữ liệu mới được nạp một phần.

### 15.1. Bảng quyết định

| Tiêu chí | Một transaction, flush/clear nhiều lần | Mỗi chunk một transaction |
| --- | --- | --- |
| Atomicity toàn bộ import | Có, nếu một DB transaction duy nhất | Không |
| Persistence Context bounded | Có, nếu clear đúng | Có, nếu context/transaction được quản lý đúng |
| DB locks/undo/WAL duration | Có thể rất dài | Thường ngắn hơn mỗi chunk |
| Rollback khi lỗi ở chunk cuối | Hoàn tác toàn bộ | Chỉ chunk lỗi/chưa commit |
| Resume/checkpoint | Đơn giản hơn về atomicity nhưng rollback tốn kém | Bắt buộc thiết kế khi cần |
| Phù hợp | Đợt vừa phải, yêu cầu all-or-nothing | Dữ liệu lớn, chấp nhận partial progress |

Không thể vừa “commit từng chunk để giảm transaction dài” vừa “một rollback sẽ hoàn tác mọi chunk đã commit” nếu không có cơ chế bù trừ hoặc điều phối transaction ngoài phạm vi cơ bản.

## 16. Ví dụ commit từng chunk bằng Jakarta Persistence

Một hướng đơn giản là mở EntityManager/transaction mới cho mỗi nhóm input:

```java
public long importInCommittedChunks(
        Iterator<EventInput> source,
        int chunkSize
) {
    if (chunkSize <= 0) {
        throw new IllegalArgumentException("chunkSize");
    }

    long total = 0;

    while (source.hasNext()) {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        int inChunk = 0;

        try {
            tx.begin();

            while (inChunk < chunkSize && source.hasNext()) {
                EventInput item = source.next();
                em.persist(new OrderEvent(
                    item.orderId(),
                    item.eventType(),
                    item.occurredAt(),
                    item.payload()
                ));
                inChunk++;
            }

            em.flush();
            tx.commit();

            total += inChunk;
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        } finally {
            em.close();
        }
    }

    return total;
}
```

Mỗi chunk dùng một `EntityManager` mới và đóng nó sau transaction, nên không cần gọi `clear()` để giải phóng context sau khi đóng. Nếu một transaction quản lý nhiều chunks trong cùng EntityManager, lúc đó flush/clear vẫn cần.

### 16.1. Thứ tự đọc input và retry

Ví dụ trên lấy từng item khỏi `Iterator` trước commit. Nếu chunk thất bại, source đã tiến lên; **không thể tự retry cùng chunk** trừ khi dữ liệu được lưu lại hoặc source có checkpoint/replay.

Trong production, hãy cân nhắc:

- Đọc và giữ chunk input bounded đến khi commit.
- Chỉ đánh dấu checkpoint sau commit thành công.
- Ghi log job ID/chunk offset.
- Sử dụng idempotency key và unique constraint cho dữ liệu nhập.
- Thiết kế retry transaction mới và không làm lặp rows.

## 17. Spring `@Transactional`: một transaction lớn hay nhiều chunk?

Một service:

```java
@Service
public class ImportService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void importAll(List<EventInput> input) {
        int i = 0;

        for (EventInput item : input) {
            em.persist(toEntity(item));

            if (++i % 100 == 0) {
                em.flush();
                em.clear();
            }
        }
    }
}
```

vẫn là **một transaction** quanh toàn bộ method, không phải 100 transactions chỉ vì gọi flush/clear mỗi 100 item.

Spring sẽ commit khi method kết thúc thành công theo transaction manager phù hợp. Trong example, `toEntity()` là helper ứng dụng.

### 17.1. `@Transactional(readOnly = true)` không dành cho batch ghi

Một số cấu hình Hibernate/Spring có thể tối ưu flush/dirty checking khi transaction read-only. Không đánh dấu job import là `readOnly = true`; muốn ghi cần transaction write phù hợp.

### 17.2. Per-chunk transactions trong một bean khác

Một thiết kế:

```java
@Service
public class ChunkWriter {

    @PersistenceContext
    private EntityManager em;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(List<EventInput> chunk) {
        for (EventInput item : chunk) {
            em.persist(toEntity(item));
        }

        em.flush();
    }
}
```

Một coordinator khác gọi:

```java
@Service
public class ImportCoordinator {

    private final ChunkWriter writer;

    public ImportCoordinator(ChunkWriter writer) {
        this.writer = writer;
    }

    public void importAll(Iterator<EventInput> source) {
        while (source.hasNext()) {
            List<EventInput> chunk = nextChunk(source, 100);
            writer.write(chunk);
            checkpointAfterSuccessfulCommit(chunk);
        }
    }
}
```

Các helper `toEntity`, `nextChunk`, `checkpointAfterSuccessfulCommit` là thành phần ứng dụng cần triển khai. Với Spring proxy-based transactions, `ChunkWriter.write()` phải được gọi **qua proxy Spring** từ bean khác; self-invocation trong cùng class có thể không tạo transaction mới như mong muốn.

### 17.3. Chú ý thời điểm checkpoint

`writer.write(chunk)` trở về sau khi transaction interceptor đã hoàn tất commit nếu gọi qua proxy đúng cấu hình. Nhưng checkpoint ghi ở nơi khác vẫn cần quyết định transaction/độ tin cậy. Một crash giữa commit và checkpoint có thể khiến chunk bị xử lý lại. Vì vậy nên dùng unique business keys, `INSERT ... ON CONFLICT` thích hợp hoặc idempotent upsert logic tùy domain.

## 18. Spring `saveAll()` có tự giải quyết tất cả không?

Với Spring Data JPA:

```java
repository.saveAll(entities);
```

không bảo đảm ứng dụng đã có toàn bộ chiến lược batch tối ưu.

Tùy entity state, repository có thể gọi `persist` hoặc `merge` từng entity. Việc saveAll một danh sách lớn trong một transaction vẫn có thể làm Persistence Context giữ nhiều objects.

```java
repository.saveAllAndFlush(entities);
```

có thể gọi flush, nhưng **flush không phải clear**. Nếu entity vẫn managed, L1 cache vẫn có thể lớn.

Với import quy mô lớn:

- Xem transaction boundary.
- Xem Hibernate JDBC batch settings.
- Xem ID strategy.
- Chọn chunk input bounded.
- Sử dụng EntityManager flush/clear hoặc mở context/transaction theo chunk.
- Đo SQL/JDBC batches thật.

Không đánh giá “đã batch” chỉ vì tên method có `All`.

## 19. Đọc input lớn mà không nạp tất cả vào heap

Nếu source là một file CSV có hàng triệu dòng, đoạn:

```java
List<EventInput> all = Files.lines(path)
    .map(this::parse)
    .toList();
```

có thể giữ toàn bộ input ở heap. Dù có `em.clear()` trong vòng lặp xử lý, danh sách `all` vẫn tồn tại.

Một hướng streaming:

```java
try (Stream<String> lines = Files.lines(path)) {
    Iterator<EventInput> iterator = lines
        .skip(1)
        .map(this::parse)
        .iterator();

    importer.importEvents(iterator, 100);
}
```

Ở đây:

- Stream file được đóng khi rời `try`.
- Mỗi dòng được parse khi iterator tiến tới.
- Persistence Context được flush/clear theo chunk.
- Không giữ toàn bộ file trong List.

Cần thêm validation, encoding UTF-8, CSV quoting/escaping, lỗi dòng và kiểm soát kích thước payload. `String.split(",")` không đủ cho CSV chuẩn có dấu phẩy trong dấu ngoặc kép.

### 19.1. Input nguồn là database khác

Nếu copy dữ liệu từ database source sang target, việc đọc hàng triệu source entities trong cùng Persistence Context có thể phình heap. Ưu tiên projection ID/DTO, pagination hoặc cursor có lifecycle rõ.

Đừng nghĩ chỉ clear target EntityManager là source Session cũng được giải phóng; chúng có thể là hai persistence contexts riêng.

## 20. Đọc entity để UPDATE: keyset pagination

Giả sử cần cập nhật một bảng lớn. Không nên:

```java
List<Order> all = em.createQuery(
    "from Order",
    Order.class
).getResultList();

for (Order order : all) { ... }
```

vì `all` giữ toàn bộ Java references và Hibernate quản lý nhiều entities.

Một hướng đọc IDs theo keyset:

```java
long lastSeenId = 0L;
int pageSize = 100;

while (true) {
    List<Long> ids = em.createQuery("""
        select o.id
        from Order o
        where o.id > :lastId
        order by o.id
        """, Long.class)
        .setParameter("lastId", lastSeenId)
        .setMaxResults(pageSize)
        .getResultList();

    if (ids.isEmpty()) {
        break;
    }

    for (Long id : ids) {
        Order order = em.find(Order.class, id);
        if (order != null) {
            order.archive();
        }
    }

    em.flush();
    em.clear();

    lastSeenId = ids.get(ids.size() - 1);
}
```

Đây là mẫu khái niệm, giả định IDs là số dương tăng dần, có index PK và mọi thao tác nằm trong transaction boundary được thiết kế rõ.

### 20.1. Vì sao không dùng OFFSET tăng dần khi thay đổi tập dữ liệu?

Nếu một query paging lọc `status = 'ACTIVE'` nhưng bạn đang đổi trạng thái từng row từ ACTIVE sang ARCHIVED, tập kết quả shrink sau mỗi chunk. `OFFSET 100`, `OFFSET 200` có thể **bỏ qua rows** vì những rows đầu đã không còn match filter.

Keyset pagination theo ID ổn định:

```sql
WHERE id > :lastSeenId
ORDER BY id
LIMIT :pageSize
```

thường tránh lỗi offset-shift đó. Tuy nhiên:

- Concurrent inserts/deletes vẫn ảnh hưởng tập dữ liệu nhìn thấy.
- ID không monotonic theo ý nghĩa nghiệp vụ ở mọi schema.
- Nếu sort theo nhiều cột, cần keyset tuple/tie-breaker phù hợp.
- Nếu cần snapshot chính xác, xác định transaction isolation/snapshot policy.

### 20.2. Có nên stream JPA entities rồi clear trong vòng lặp?

Hibernate hỗ trợ cursor/scroll/stream APIs, nhưng đọc entities từ một cursor và đồng thời `clear()` trên cùng Session có các ràng buộc về cursor lifecycle, connection, lazy loading và provider behavior.

Với import/update quan trọng, **phân trang IDs/DTO rồi load từng chunk** thường dễ kiểm soát hơn. Nếu sử dụng `scroll()`/`Stream` cho khối lượng lớn, cần test provider/dialect, đóng cursor, giới hạn memory và tránh làm transaction kéo dài vô hạn.

## 21. Xử lý lỗi phát sinh tại flush

Một lời gọi `persist()` chưa phát INSERT ngay. Vì vậy exception có thể chỉ xuất hiện ở:

```java
em.flush();
```

Ví dụ:

- Vi phạm UNIQUE constraint.
- Foreign key trỏ tới hàng không tồn tại.
- NOT NULL/CHECK violation.
- JDBC batch lỗi ở một statement.
- Deadlock/lock timeout.
- Optimistic lock failure khi UPDATE/DELETE.
- Database connection lỗi.

Trong JDBC batch, lỗi có thể được bọc trong `BatchUpdateException`, `PersistenceException` hoặc exception Hibernate/Spring phù hợp.

### 21.1. Sau lỗi flush, không tiếp tục dùng context như chưa có gì xảy ra

Ví dụ không an toàn:

```java
try {
    em.flush();
} catch (Exception ex) {
    // Log rồi tiếp tục em.persist(...) trong cùng transaction.
}
```

Nếu flush thất bại, transaction/session có thể đang ở trạng thái không còn sử dụng an toàn. Hướng xử lý thường là:

1. Ghi nhận lỗi.
2. Rollback transaction.
3. Đóng/discard EntityManager/Session bị lỗi.
4. Bắt đầu transaction mới nếu retry hợp lệ.
5. Đọc lại dữ liệu cần và xác định idempotency/concurrency policy.

Không chỉ `em.clear()` rồi tiếp tục để “sửa” một JDBC batch đã lỗi. Clear không làm database transaction trở lại trạng thái sạch.

### 21.2. Không khẳng định biết chính xác record nào lỗi từ thứ tự SQL

Hibernate có thể reorder INSERT/UPDATE và JDBC driver có thể báo affected counts không đầy đủ. Nếu cần xác định record lỗi, hãy bổ sung input ID/business key, audit logging và chiến lược cô lập/thu nhỏ chunk khi retry, thay vì dựa vào vị trí statement trong batch.

## 22. Rollback toàn bộ hay xử lý partial success?

Với một transaction lớn:

```text
BEGIN
  flush chunk 1
  flush chunk 2
  flush chunk 3 -> constraint error
ROLLBACK
```

Các SQL đã flush ở chunk 1 và 2 vẫn nằm trong transaction và sẽ được rollback cùng chunk 3.

Với per-chunk commit:

```text
chunk 1 -> COMMIT ✓
chunk 2 -> COMMIT ✓
chunk 3 -> ROLLBACK ✗
```

Chunks 1 và 2 vẫn tồn tại trong DB. Job cần biết bắt đầu lại từ đâu.

### 22.1. Idempotency quan trọng hơn retry vô điều kiện

Ví dụ mỗi input event có `externalEventId` duy nhất. Có thể thêm unique constraint:

```sql
ALTER TABLE order_events
ADD CONSTRAINT uk_order_events_external_event
UNIQUE (external_event_id);
```

DDL này giả định schema có cột `external_event_id`; phải bổ sung migration/field trước nếu áp dụng.

Khi retry chunk đã commit nhưng checkpoint chưa lưu, unique key hoặc upsert idempotent giúp tránh tạo event trùng. Tùy domain, duplicate có thể:

- Được bỏ qua như retry an toàn.
- Báo conflict.
- Được update có kiểm soát.
- Được chuyển vào dead-letter queue.

Không nên tự động bỏ qua mọi constraint exception: một vi phạm UNIQUE có thể đại diện dữ liệu sai, không chỉ retry trùng.

## 23. Batch update và optimistic locking

Entity có:

```java
@Version
private long version;
```

Khi cập nhật managed entity, Hibernate thường dùng version trong `WHERE` để phát hiện stale writes.

Ví dụ khái niệm:

```sql
UPDATE purchase_orders
SET status = ?, version = ?
WHERE id = ? AND version = ?;
```

Nếu một transaction khác đã thay đổi version, số row update có thể không như dự kiến, dẫn tới optimistic locking exception.

Với JDBC batching, driver phải hỗ trợ cơ chế affected row counts phù hợp để Hibernate xử lý optimistic locking. Các chi tiết và configuration phụ thuộc Hibernate/driver version.

**Flush/clear không tắt optimistic locking.** Một conflict có thể chỉ xuất hiện ở flush sau 100 entity. Lúc đó hãy rollback và xử lý lại theo nghiệp vụ trong transaction mới.

### 23.1. Native/bulk DML không tự có cùng version semantics

Nếu thay entity loop bằng native SQL:

```sql
UPDATE purchase_orders
SET status = 'ARCHIVED'
WHERE status = 'COMPLETED';
```

DB thực thi trực tiếp; SQL này không tự tăng version/check version như Hibernate managed updates. Muốn bảo vệ concurrency phải thiết kế version predicate/increment phù hợp.

Không coi bulk update là tương đương hoàn toàn về lifecycle, callbacks và version.

## 24. Dirty checking và số entity đang managed

Hibernate dirty-check managed entities khi flush để xác định cần UPDATE hay không. Với nhiều managed instances, công việc kiểm tra state có thể tăng.

Ví dụ:

```java
List<Order> orders = em.createQuery(
    "from Order",
    Order.class
).getResultList();

for (Order order : orders) {
    order.recalculate();
}
em.flush();
```

Nếu orders chứa 100.000 entities, ORM phải quản lý state trên một tập lớn. Việc tách thành chunks giúp:

- Tạm thời giới hạn số entity loaded trong một đợt.
- Giảm snapshots/collections giữ trong context.
- Giảm số đối tượng cần cân nhắc ở các lần flush sau.
- Hạ áp lực heap/GC.

Bytecode enhancement có thể tối ưu một phần cơ chế dirty tracking, nhưng **không tự giải quyết** việc ứng dụng giữ quá nhiều managed entities/collection graph.

## 25. `clear()` không giải phóng mọi loại cache

Có nhiều lớp cache:

| Lớp | Phạm vi | `em.clear()` làm gì? |
| --- | --- | --- |
| Java List/Map do ứng dụng giữ | Application code | Không xóa references |
| L1 Persistence Context | EntityManager/Session | Detach tất cả managed entities |
| Hibernate action/dirty tracking state | Theo Session | Flush rồi clear giúp bỏ state đã hoàn tất |
| L2 cache | SessionFactory/shared cache | Không tự xóa L2 cache |
| Query cache | Theo cấu hình provider | Không tự xóa tất cả entries |
| Database buffer pool | DB server | Không liên quan |
| JDBC driver statement buffers | Driver/connection | Không trực tiếp giải phóng mọi tài nguyên driver |

Đừng gọi `em.clear()` với kỳ vọng nó reset toàn bộ heap hoặc tất cả caches của hệ thống.

### 25.1. Dùng `detach(entity)` thay clear khi nào?

Nếu chỉ muốn detach một entity:

```java
em.detach(entity);
```

có thể phù hợp hơn `clear()` trong một unit of work vẫn cần quản lý các entities khác. Nhưng để import một chuỗi independent aggregates theo chunks, `clear()` thường đơn giản hơn.

Không detach từng entity trước khi flush nếu còn pending changes.

## 26. Flush mode ảnh hưởng tới thời điểm đồng bộ

JPA có:

```java
em.setFlushMode(FlushModeType.AUTO);
em.setFlushMode(FlushModeType.COMMIT);
```

- `AUTO`: provider có thể flush trước query nếu cần bảo đảm semantics query.
- `COMMIT`: đẩy flush gần commit hơn trong những trường hợp tương thích; ảnh hưởng kết quả các query trong transaction có thể theo quy định/provider.
- Hibernate còn có các flush modes riêng tùy API/version.

Với batch import, không nên tùy tiện đặt `MANUAL` hoặc vô hiệu auto-flush khi không hiểu semantics. Thuật toán đã chủ động gọi `em.flush()` theo chunk; hãy giữ configuration nhất quán và test khi có query xen vào vòng lặp.

### 26.1. Query giữa lô có thể làm phát SQL sớm

```java
em.persist(event1);
em.persist(event2);

Long count = em.createQuery(
    "select count(e) from OrderEvent e",
    Long.class
).getSingleResult();
```

Ở `AUTO` mode, Hibernate có thể flush pending INSERT trước count query. Nếu job cần throughput cao, tránh truy vấn không cần thiết bên trong hot loop.

## 27. Ordering SQL và constraints

`hibernate.order_inserts=true`/`order_updates=true` có thể reorder DML để tăng khả năng batching. Điều này **không phải cam kết giữ thứ tự insert theo vòng lặp**.

Ví dụ:

```java
em.persist(eventA);
em.persist(eventB);
```

không có nghĩa SQL statement/order trong DB luôn có A trước B khi có nhiều entity types/relationships.

Nếu nghiệp vụ cần thứ tự sự kiện, lưu một trường sequence/timestamp được xác định rõ và dùng `ORDER BY` khi đọc. Không dùng thứ tự vật lý của INSERT để biểu diễn event ordering.

### 27.1. Unique constraint và “đổi chỗ” dữ liệu

Khi hai entities trao đổi giá trị UNIQUE trong cùng transaction, việc UPDATE theo một thứ tự cụ thể có thể vi phạm constraint trung gian, dù final state hợp lệ trên giấy. `flush()` không tự làm database constraints defer.

Cần thiết kế schema/transaction/SQL rõ (ví dụ constraint deferrable nếu DBMS hỗ trợ, hoặc update thông qua giá trị tạm hợp lệ) thay vì hy vọng Hibernate action ordering luôn giải quyết.

## 28. Benchmark batch size và chunk size độc lập

Giả sử:
- `hibernate.jdbc.batch_size = 25`.
- `chunkSize = 100`.

Thử các cặp:

| JDBC batch size | Chunk size | Ý tưởng thử nghiệm |
| ---: | ---: | --- |
| 0 | 100 | Baseline không JDBC batching nhưng bounded context |
| 10 | 100 | DML batching nhỏ |
| 25 | 100 | Điểm bắt đầu |
| 50 | 100 | JDBC batch lớn hơn |
| 25 | 50 | Flush/clear thường xuyên hơn |
| 25 | 500 | Ít flush hơn nhưng context lớn hơn |
| 50 | 500 | Cân bằng theo throughput/heap thực tế |

Đừng thay cả hai tham số cùng lúc rồi không biết cái nào giúp cải thiện.

### 28.1. Những chỉ số nên đo

- Số records thành công/giây.
- Thời gian tổng import và p95/p99 chunk latency.
- Heap used/peak, GC pauses, CPU.
- Số JDBC batch executions/round trips thực tế.
- Số prepared statements, SQL INSERT/UPDATE.
- Database CPU, WAL/redo/undo, lock waits, transaction duration.
- Query/cache behavior nếu có SELECT xen kẽ.
- Thời gian rollback khi lỗi giữa hoặc cuối job.

### 28.2. JDBC batch có thực sự được kích hoạt?

Cần xem:
- ID strategy có cho phép batch INSERT không.
- SQL insert statements có cùng shape/table không.
- Hibernate/JDBC batch size có được set vào đúng Session không.
- Driver có hỗ trợ batch execution không.
- `order_inserts` có giúp nhóm statements cùng kiểu không.
- Có SQL phát sớm do `IDENTITY`/query auto-flush không.

Một log hiển thị 100 câu INSERT **không tự chứng minh** driver đã gửi 100 network round trips; tương tự, ít log lines không chứng minh SQL được batch. Có thể dùng datasource proxy, JDBC driver metrics, database logs hoặc tracing phù hợp.

## 29. Hibernate Statistics và SQL logging

Có thể bật:

```properties
hibernate.generate_statistics=true
```

Trong Spring Boot:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
logging.level.org.hibernate.SQL=DEBUG
```

Đọc thống kê:

```java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sf =
    emf.unwrap(SessionFactory.class);

Statistics stats = sf.getStatistics();
stats.clear();

long before = stats.getEntityInsertCount();

// Thực thi một import/test riêng.

long inserted =
    stats.getEntityInsertCount() - before;

System.out.println("Entity inserts: " + inserted);
System.out.println(
    "Flush count: " + stats.getFlushCount()
);
System.out.println(
    "Prepared statement count: " +
        stats.getPrepareStatementCount()
);
```

**Statistics là ở phạm vi SessionFactory**; test chạy song song có thể làm số liệu nhiễu. `getPrepareStatementCount()` không bằng số network round trips hoặc số JDBC batches. Dùng metrics driver/datasource nếu muốn xác nhận batching thật.

Không bật bind-parameter logging cho dữ liệu nhạy cảm ở production.

## 30. Integration test: flush/clear làm detach entity

Một test cần một `EntityManagerFactory` thực với schema phù hợp. Ví dụ:

```java
@Test
void clearDetachesEntitiesAfterFlush() {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    Long id;

    try {
        tx.begin();

        OrderEvent event = new OrderEvent(
            101L,
            "ORDER_CREATED",
            Instant.parse("2026-01-01T00:00:00Z"),
            "{}"
        );

        em.persist(event);
        assertTrue(em.contains(event));

        em.flush();
        id = event.getId();

        em.clear();
        assertFalse(em.contains(event));

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) tx.rollback();
        throw ex;
    } finally {
        em.close();
    }

    try (EntityManager verify = emf.createEntityManager()) {
        assertNotNull(verify.find(OrderEvent.class, id));
    }
}
```

Đây là **test body minh họa**, cần JUnit imports, fixture `emf`, schema/sequence và teardown phù hợp. `EntityManager` hỗ trợ `close()`; cú pháp `try-with-resources` phụ thuộc Jakarta Persistence version áp dụng và API trong dự án — nếu version không implement `AutoCloseable`, dùng `try/finally` để đóng.

### 30.1. Test rollback dù đã flush

```java
tx.begin();

em.persist(new OrderEvent(...));
em.flush();
em.clear();

tx.rollback();
```

Sau rollback, EntityManager mới query theo business key/ID và xác nhận row chưa được commit. Bài học: **flush không phải commit**.

### 30.2. Test cuối chunk chưa đủ batch size

Nhập 23 input với chunk size 10. Kiểm tra sau commit đủ 23 rows, không phải 20. Test này bắt lỗi quên final remainder flush logic.

### 30.3. Test memory behavior đúng trọng tâm

Một test nhỏ 20 records không chứng minh heap bounded ở 2 triệu records. Dùng benchmark/profile riêng với input streaming, đo heap/GC và số managed instances; không dùng một threshold heap cứng dễ nhiễu trong unit tests.

## 31. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Import rất chậm/heap tăng đều | L1 giữ tất cả managed entities | Flush rồi clear theo chunk, stream input |
| Gọi flush nhưng heap vẫn cao | Chưa clear; List ứng dụng vẫn giữ objects | Clear context và giải phóng references ngoài ORM |
| Mất thay đổi cuối lô | Clear trước flush hoặc quên phần dư | Flush trước clear, xử lý remainder |
| Gọi flush rồi tưởng đã commit | Nhầm transaction semantics | Commit/rollback tường minh |
| JDBC batch không hoạt động | `IDENTITY`, batch size 0, SQL shape khác | Kiểm tra ID strategy/driver/settings |
| `saveAllAndFlush` vẫn ngốn memory | Flush không giải phóng managed instances | Cân nhắc clear/chunk context |
| Entity sau clear không được update | Đã detached | Find/merge managed copy có kiểm soát |
| Cascade báo detached entity | Reuse parent detached hoặc cascade sai | Dùng ID/getReference trong context hiện tại |
| Flush lỗi UNIQUE sau 100 records | Constraint được kiểm tra ở flush | Rollback và xử lý chunk lỗi trong transaction mới |
| Lỗi flush rồi tiếp tục gây lỗi khác | Persistence Context/transaction không còn an toàn | Rollback và discard context |
| Commit-per-chunk làm import dở dang | Atomicity toàn job không còn | Checkpoint, idempotency, retry policy |
| `@Transactional` inner method không tạo tx mới | Self-invocation bypass proxy | Bean khác/proxy hoặc TransactionTemplate |
| Batch update bỏ qua bản ghi | OFFSET trên tập dữ liệu đang shrink | Keyset pagination theo stable key |
| Stats cho thấy nhiều prepared statements | Stats không trực tiếp đếm JDBC batch trips | Dùng datasource/driver metrics |
| Chạy với H2 nhanh nhưng PostgreSQL chậm | Driver/DB plan/constraints khác | Benchmark trên DB production-like |
| Clear làm lazy collection lỗi | Entity/proxy đã detached | Load dữ liệu cần trước clear hoặc DTO |
| Batch lớn làm lock/undo kéo dài | Một DB transaction quá lớn | Xem xét commit từng chunk với đánh đổi atomicity |

## 32. Quy trình lựa chọn chiến lược

**Bước 1 — Xác định yêu cầu atomicity.** Toàn bộ import phải all-or-nothing hay chấp nhận commit từng chunk?

**Bước 2 — Đo baseline.** Heap, GC, throughput, số SQL/JDBC batches, transaction duration.

**Bước 3 — Kiểm tra ID strategy.** Nếu INSERT dùng `IDENTITY`, đừng kỳ vọng JDBC insert batching giống SEQUENCE.

**Bước 4 — Cấu hình JDBC batching.** Chọn `hibernate.jdbc.batch_size` vừa phải, kiểm tra driver và `order_inserts`/`order_updates`.

**Bước 5 — Chọn đơn vị chunk.** Theo số entity/aggregate và kích thước object graph; không chỉ theo số root.

**Bước 6 — Sắp xếp vòng lặp.** `persist`/mutate → `flush` → `clear`, cuối cùng xử lý remainder.

**Bước 7 — Đảm bảo input bounded.** Streaming/paginated IDs/DTO, tránh List hàng triệu objects.

**Bước 8 — Xử lý detached references.** Sau clear, đừng dùng một managed parent cũ; load/reference lại khi cần.

**Bước 9 — Chọn transaction boundaries.** Một transaction lớn nếu cần atomicity và khả năng DB chịu được; per-chunk transactions nếu dữ liệu lớn và partial progress được quản lý.

**Bước 10 — Xử lý lỗi và idempotency.** Rollback/discard context sau flush failure, retry từ chunk checkpoint, unique business keys.

**Bước 11 — Kiểm tra SQL và constraints.** FK, UNIQUE, version, callbacks, reordering, JDBC batch execution.

**Bước 12 — Benchmark production-like.** Không chọn batch/chunk size chỉ từ một test in-memory nhỏ.

## 33. Bài tập tình huống

### Bài 1 — Flush và commit

Sau `em.flush()` cho 100 events, transaction rollback. Events có còn trong DB không?

**Đáp án:** Không, nếu database transaction rollback thành công. Flush không commit.

### Bài 2 — Clear trước flush

```java
em.persist(event);
em.clear();
em.flush();
```

Có an toàn không?

**Đáp án:** Không. Clear detach trước khi đồng bộ pending changes; cần flush trước clear.

### Bài 3 — Giới hạn Persistence Context

Nhập 100.000 entities với `chunkSize=100`; mỗi 100 gọi flush/clear. L1 có còn tích lũy tất cả 100.000 managed instances không?

**Đáp án:** Trong mô hình đơn giản, không: các instances đã xử lý được detach định kỳ. Tuy nhiên memory khác có thể còn do List/cascade/query và object graph.

### Bài 4 — Hibernate batch 25

Cấu hình `hibernate.jdbc.batch_size=25`, nhưng không gọi clear. Memory có được giải quyết tự động không?

**Đáp án:** Không. JDBC batching giảm chi phí DML round trip; L1 vẫn giữ managed entities nếu không clear/đóng context.

### Bài 5 — `@BatchSize`

Có dùng `@BatchSize(size=25)` để batch 25 INSERT được không?

**Đáp án:** Không. Annotation phục vụ lazy fetch khi đọc, không phải JDBC DML batching.

### Bài 6 — IDENTITY

Entity dùng `GenerationType.IDENTITY`, `hibernate.jdbc.batch_size=50` nhưng Hibernate vẫn INSERT riêng. Vì sao?

**Đáp án:** Identity ID thường phải được lấy ngay sau INSERT; Hibernate không dùng JDBC insert batching theo cách thông thường cho identity-generated IDs.

### Bài 7 — Chọn sequence

Đổi `IDENTITY` sang `SEQUENCE` là chỉ thêm annotation?

**Đáp án:** Không. Phải kiểm tra schema, migration, allocationSize/DB sequence increment, ID ranges, FK và production rollout.

### Bài 8 — Detached entity

Sau `flush(); clear();`, sửa `event` rồi commit. Có chắc UPDATE không?

**Đáp án:** Không. Event detached, không còn dirty checking; cần managed instance mới/merge thích hợp.

### Bài 9 — Per-chunk commit

Chunk 1 và 2 đã commit, chunk 3 lỗi. Rollback chunk 3 có xóa dữ liệu chunk 1 và 2 không?

**Đáp án:** Không. Các chunk trước đã commit. Cần checkpoint/idempotency hoặc compensation nếu nghiệp vụ yêu cầu.

### Bài 10 — Spring transaction

Một method `@Transactional` gọi `flush(); clear();` 50 lần. Có tạo 50 transactions không?

**Đáp án:** Không. Vẫn một transaction quanh method, trừ khi được tách transaction boundaries thực sự.

### Bài 11 — `saveAllAndFlush()`

Tại sao `saveAllAndFlush()` không đủ để giới hạn L1?

**Đáp án:** Flush không detach managed instances. Cần clear, context đóng hoặc transaction chunks.

### Bài 12 — CSV streaming

Code dùng `List<Input> all = ...toList()` rồi flush/clear. Heap vẫn cao, vì sao?

**Đáp án:** `all` vẫn giữ toàn bộ input records; clear chỉ giải phóng Hibernate L1 references.

### Bài 13 — Update bằng OFFSET

Trang đầu `status=ACTIVE` được đổi thành ARCHIVED; trang sau dùng OFFSET 100. Có thể bỏ sót gì?

**Đáp án:** Tập ACTIVE co lại khiến OFFSET skip records chưa xử lý. Dùng keyset pagination theo stable key và transaction policy phù hợp.

### Bài 14 — Flush thất bại

`em.flush()` báo foreign-key violation. Có nên `clear()` rồi tiếp tục cùng transaction không?

**Đáp án:** Không. Rollback và bỏ context/transaction bị lỗi; sửa input và bắt đầu transaction mới.

### Bài 15 — Cascade graph

`chunkSize=50` aggregate roots, mỗi root có 100 children. Hibernate có chỉ giữ tối đa 50 entities không?

**Đáp án:** Không. Có thể giữ hơn 5.000 entities; chunk phải tính cả graph size.

### Bài 16 — JDBC metrics

Hibernate log cho thấy 100 dòng INSERT. Kết luận được JDBC driver gửi 100 round trips không?

**Đáp án:** Không. SQL logging và JDBC batch execution/network metrics là hai lớp khác nhau; cần driver/datasource tracing.

### Bài 17 — Optimistic locking

Batch UPDATE 100 entities có @Version; conflict xuất hiện ở `flush()`. Cần làm gì?

**Đáp án:** Rollback, bỏ context bị lỗi, đọc lại state và quyết định retry/conflict trong transaction mới, không cố tiếp tục batch cũ.

### Bài 18 — Chọn transaction strategy

Một job nhập 5 triệu events có thể restart và chấp nhận dữ liệu xuất hiện từng phần. Có cần một transaction 5 triệu rows không?

**Đáp án:** Thường nên đánh giá commit-per-chunk với idempotency/checkpoint và test consistency, vì một transaction quá dài có chi phí DB lớn. Quyết định phụ thuộc yêu cầu atomicity và operational constraints.

## 34. Tài liệu tham khảo chính thức

- [Hibernate ORM User Guide — Batch processing](https://docs.hibernate.org/stable/orm/userguide/html_single/#batch): JDBC batching, flush/clear khi insert/update lớn, IDENTITY strategy và stateless session.
- [Hibernate ORM User Guide — Persistence Context](https://docs.hibernate.org/stable/orm/userguide/html_single/#pc): managed/detached states, first-level cache, dirty checking.
- [Hibernate ORM User Guide — Flushing](https://docs.hibernate.org/stable/orm/userguide/html_single/#flushing): flush modes, thời điểm đồng bộ SQL và commit.
- [Hibernate ORM User Guide — Identifiers](https://docs.hibernate.org/stable/orm/userguide/html_single/#identifiers): sequence/identity generation và allocation strategies.
- [Hibernate ORM Javadoc — `Session`](https://docs.hibernate.org/stable/orm/javadocs/org/hibernate/Session.html): `flush`, `clear`, `setJdbcBatchSize` và session lifecycle.
- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): lifecycle entity, flush, persistence context, transaction và detach.
- [Jakarta Persistence 3.2 — `EntityManager`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/EntityManager.html): `persist`, `flush`, `clear`, `detach`, `merge`.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, propagation, proxy semantics và rollback.
- [Spring Data JPA — Persisting Entities](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html): repository save, persist/merge semantics.
- [PostgreSQL Documentation — Transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html): transaction boundaries, commit và rollback.

`hibernate.jdbc.batch_size`, `hibernate.order_inserts`, `hibernate.order_updates`, Hibernate `Session` và `StatelessSession` là Hibernate-specific. SQL batching behavior và generated ID details phụ thuộc version/dialect/driver. Hãy kiểm tra trên đúng stack đang triển khai, không mặc định H2/test driver phản ánh production.

## Kết luận

**Flush rồi clear theo từng lô** là kỹ thuật nền tảng để giới hạn Persistence Context khi Hibernate xử lý khối lượng ghi lớn. `flush()` gửi các thay đổi pending xuống database **trong transaction hiện tại**; `clear()` detach các entity đã xử lý để L1 không tăng mãi. Thứ tự đúng là `flush()` **trước** `clear()`, và phần lô cuối chưa đủ kích thước vẫn cần được đồng bộ.

Để tối ưu thực tế, phải phân biệt `chunkSize` giới hạn managed state với `hibernate.jdbc.batch_size` gom DML ở JDBC. Xem xét ID generator (`IDENTITY` thường cản trở INSERT batching), cascade graph size, detached references, dirty checking, SQL ordering, constraints và optimistic locking. Đồng thời tránh giữ toàn bộ input trong List, lựa chọn transaction boundaries phù hợp và có rollback/retry/idempotency khi commit từng chunk.

Cuối cùng, **một transaction có nhiều flush không phải nhiều commit**. Flush/clear giúp Hibernate quản lý heap, nhưng không xóa bỏ chi phí transaction dài ở database. Chọn cấu hình qua benchmark và kiểm thử trên dữ liệu/driver/DBMS giống production, dựa vào heap, số JDBC batches, throughput, locking và transaction duration thay vì chỉ nhìn số dòng `persist()` trong vòng lặp.
