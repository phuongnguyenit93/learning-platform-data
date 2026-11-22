# Thời điểm có định danh và ảnh hưởng đến batching hoặc equals trong Hibernate ORM

Trong Hibernate ORM, định danh của entity thường được khai báo bằng `@Id` và có thể được gán thủ công hoặc sinh tự động qua `@GeneratedValue`. Tuy nhiên, **không phải chiến lược sinh ID nào cũng khiến entity nhận được ID ở cùng một thời điểm**. Sự khác nhau này ảnh hưởng đến thời điểm Hibernate phải chạy SQL, khả năng gom các lệnh `INSERT` thành JDBC batch và cách viết `equals()`/`hashCode()` cho entity.

Xét một tình huống:

```java
PurchaseOrder order = new PurchaseOrder("PO-2026-001");

System.out.println(order.getId()); // Có thể đang null.
entityManager.persist(order);
System.out.println(order.getId()); // Khi nào đã có ID?
```

Câu trả lời phụ thuộc vào **kiểu generator**, **cấu hình Hibernate**, **trạng thái transaction** và đôi khi cả **thời điểm flush**. Việc Hibernate đã điền `order.id` cũng không đồng nghĩa dữ liệu đã commit.

Bài học phân tích những khác biệt đó và đưa ra các mẫu thiết kế an toàn trong ứng dụng Java dùng Hibernate.

## 1. Ba mốc thời gian phải phân biệt

Khi tạo entity có ID sinh tự động, có ít nhất ba sự kiện khác nhau:

1. **Entity nhận giá trị ID trong bộ nhớ Java.**
2. **Câu lệnh `INSERT` được gửi tới cơ sở dữ liệu.**
3. **Transaction chứa câu lệnh `INSERT` được commit thành công.**

Ví dụ chu trình đơn giản:

```text
new Entity()
    |
    | id có thể là null
    v
persist(entity)
    |
    | Hibernate có thể cấp ID ở đây
    | (tùy chiến lược)
    v
flush()
    |
    | SQL INSERT được thực thi nếu chưa thực thi trước đó
    v
commit()
    |
    | Database xác nhận transaction thành công
    v
Hàng dữ liệu được commit
```

Sơ đồ trên là **luồng khái niệm**, không phải cam kết rằng mọi ID đều được gán tại `persist()` hoặc mọi `INSERT` đều chờ đến `flush()`. Với `IDENTITY`, Hibernate thường phải insert sớm để lấy ID. Với `SEQUENCE`, Hibernate thường có ID **trước khi** insert.

| Sự kiện | Có thể đã có ID? | Hàng đã được insert? | Đã commit? |
|---|---|---|---|
| Ngay sau `new` | ID được gán thủ công: có; ID sinh tự động: thường chưa | Chưa | Chưa |
| Sau `persist` | Tùy generator và thời điểm xử lý | Có thể chưa, hoặc đã insert sớm | Chưa nếu transaction còn mở |
| Sau `flush` thành công | Thông thường đã có | Các insert đang chờ đã được gửi xuống DB | Chưa, nếu transaction chưa commit |
| Sau `commit` thành công | Đã có nếu ghi thành công | Đã thực hiện | Có |

**Điểm cốt lõi:** `id != null` không chứng minh hàng đã tồn tại trong database dưới dạng dữ liệu đã commit. ID có thể được cấp trước khi `INSERT`, và transaction có thể rollback sau khi ID đã được gán.

## 2. Những chiến lược sinh định danh thường gặp

Jakarta Persistence có các giá trị `GenerationType` như `AUTO`, `IDENTITY`, `SEQUENCE`, `TABLE` và, ở các phiên bản hỗ trợ, `UUID`. Hibernate còn cung cấp những generator riêng và cơ chế tối ưu cấp phát.

| Chiến lược | Nguồn ID | Thời điểm biết ID thường gặp | Tác động nổi bật đến insert batching |
|---|---|---|---|
| **Gán thủ công** | Code ứng dụng gán trước `persist` | Trước `persist` | Hibernate biết ID trước insert; batching có thể thực hiện khi các điều kiện khác phù hợp |
| **`SEQUENCE`** | Database sequence, có thể kết hợp optimizer cấp dải | Thường lúc `persist`, trước khi insert | Thuận lợi cho JDBC insert batching |
| **`IDENTITY`** | Cột identity/auto-increment khi database insert hàng | Thường sau khi thực hiện insert để nhận generated key | Hibernate thường không gom insert của entity dùng `IDENTITY` vào JDBC batch |
| **`TABLE`** | Bảng lưu trạng thái cấp số của generator | Có thể lấy trước insert entity | Biết ID sớm nhưng generator table có thêm truy vấn và cạnh tranh khóa |
| **`UUID`** | Generator UUID do provider cung cấp | Thường được tạo ở phía ứng dụng trước insert | Biết ID sớm, có thể batching tùy cấu hình |
| **`AUTO`** | Hibernate/provider chọn theo kiểu ID và dialect | Phụ thuộc chiến lược thực tế | Không thể kết luận nếu chưa xác định generator được chọn |

Bảng diễn tả **hành vi thông dụng trong Hibernate**, không phải bảo đảm API rằng `persist()` luôn điền ID ngay lập tức trong mọi tình huống. Đặc biệt, `IDENTITY` có các tình huống deferred/delayed insert phụ thuộc môi trường transaction và phiên bản.

### 2.1. Gán ID thủ công

Entity có ID được ứng dụng đặt:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class ExternalDocument {
    @Id
    private String id;

    private String title;

    protected ExternalDocument() {
    }

    public ExternalDocument(String id, String title) {
        this.id = id;
        this.title = title;
    }

    public String getId() {
        return id;
    }
}
```

Sử dụng:

```java
ExternalDocument document =
    new ExternalDocument("DOC-01", "Hướng dẫn sử dụng");

entityManager.persist(document);
// document.getId() đã có giá trị từ trước persist.
```

Không có `@GeneratedValue`: **ứng dụng chịu trách nhiệm** tạo ID hợp lệ, duy nhất trong phạm vi ràng buộc của bảng. Hibernate không tự bảo đảm rằng hai tiến trình sẽ không sinh cùng một giá trị.

Nếu ID là một mã nghiệp vụ có thể thay đổi, dùng nó trực tiếp làm khóa chính và làm cơ sở `equals` có thể tạo vấn đề. Phải cân nhắc tính bất biến của mã và ràng buộc unique.

### 2.2. `SEQUENCE`: biết ID trước khi insert

Ví dụ entity:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchase_order_seq_generator"
    )
    @SequenceGenerator(
        name = "purchase_order_seq_generator",
        sequenceName = "purchase_order_id_seq",
        allocationSize = 50
    )
    private Long id;

    @Column(nullable = false, length = 80)
    private String referenceCode;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String referenceCode) {
        this.referenceCode = referenceCode;
    }

    public Long getId() {
        return id;
    }
}
```

Hibernate thường cần giá trị sequence, hoặc một ID chưa dùng từ dải đã cấp phát, để gán `id` khi entity được `persist`. Vì ID có thể biết trước câu lệnh `INSERT`, Hibernate có quyền **trì hoãn insert đến lúc flush**.

Luồng minh họa:

```text
Java                            Hibernate                  Database
 |                                  |                          |
 | persist(order)                   |                          |
 |--------------------------------->|                          |
 |                                  | nextval(sequence) [nếu cần]
 |                                  |------------------------->|
 |                                  |<-------------------------|
 |                                  | gán order.id             |
 |<---------------------------------|                          |
 |                                  |                          |
 | flush/commit                     |                          |
 |--------------------------------->| INSERT ... id=?          |
 |                                  |------------------------->|
 |                                  |                          |
```

Nếu Hibernate còn ID trong pool đã cấp, nó không nhất thiết phải gọi `nextval` cho mỗi entity.

Đây là lý do `SEQUENCE` thường phù hợp với insert hàng loạt khi database hỗ trợ sequence và Hibernate đã được cấu hình phù hợp.

### 2.3. `IDENTITY`: ID do insert sinh ra

Ví dụ:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Ở nhiều database, ID được tạo bởi cột identity hoặc auto-increment khi hàng được insert. Hibernate thường cần thực thi `INSERT` để nhận generated key:

```text
persist(order)
    |
    v
Hibernate cần ID
    |
    v
INSERT INTO purchase_orders (...) VALUES (...)
    |
    v
Database sinh id = 501
    |
    v
JDBC trả generated key
    |
    v
Hibernate gán order.id = 501
```

Trong transaction đang hoạt động, Hibernate thường thực hiện insert sớm với `IDENTITY` để biết khóa chính. Nhưng có những tình huống provider trì hoãn insert, ví dụ một số cách gọi khi không có transaction đang hoạt động hoặc tùy cách Hibernate xử lý delayed identity insertion.

Do đó, không xây dựng logic phụ thuộc tuyệt đối vào phát biểu “sau `persist()` thì `IDENTITY` luôn khác null”. Hãy dựa vào hợp đồng persistence và kiểm chứng hành vi của phiên bản dùng trong ứng dụng.

Một nhầm lẫn thường gặp là “insert sớm tức là commit sớm”. **Không đúng.** `INSERT` có thể được thực thi trong transaction chưa commit; transaction vẫn có thể rollback.

### 2.4. `TABLE`: cấp số từ bảng generator

`GenerationType.TABLE` dùng bảng để quản lý trạng thái cấp ID thay vì database sequence chuyên dụng. Hibernate cần truy cập bảng generator, thường thông qua các thao tác có phối hợp concurrency, rồi mới có giá trị để cấp cho entity.

Ưu điểm là có thể áp dụng ở môi trường không hỗ trợ sequence. Nhược điểm là thêm thao tác database và có thể tạo điểm tranh chấp khi nhiều luồng/instance cùng xin ID. Nếu database hỗ trợ sequence tốt, `SEQUENCE` thường là lựa chọn tự nhiên hơn cho ứng dụng cần throughput insert cao.

### 2.5. UUID: không cần đợi database sinh số

Các phiên bản Jakarta Persistence hỗ trợ `GenerationType.UUID` cho phép provider tạo ID UUID. Ví dụ:

```java
import java.util.UUID;
import jakarta.persistence.*;

@Entity
public class EventRecord {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false)
    private String eventType;

    protected EventRecord() {
    }
}
```

Khi Hibernate sinh UUID trong ứng dụng, ID thường được xác định trước `INSERT`. Vì vậy insert batching không bị ràng buộc bởi việc đợi database trả identity key như `IDENTITY`.

Tuy nhiên, cách lưu UUID vật lý (`UUID`, `BINARY`, `VARCHAR`...) phụ thuộc mapping và dialect. UUID không mặc nhiên tốt hơn sequence: cần xem kích thước index, sự phân bố khóa, khả năng tìm kiếm, tính bảo mật và yêu cầu hệ thống.

## 3. Khi nào `persist()`, `flush()` và `commit()` thực sự thực hiện SQL?

Giả sử code quản lý transaction bằng `EntityManager` trong môi trường resource-local:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    PurchaseOrder order = new PurchaseOrder("PO-100");
    System.out.println("Before persist: " + order.getId());

    em.persist(order);
    System.out.println("After persist: " + order.getId());

    em.flush();
    System.out.println("After flush: " + order.getId());

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Với `SEQUENCE` thông dụng, giá trị ID thường xuất hiện sau `persist`; Hibernate có thể chỉ chạy `INSERT` khi flush. Với `IDENTITY`, Hibernate thường phải `INSERT` sớm để lấy ID, khiến `After persist` thường có giá trị trong transaction đang hoạt động.

Trong Jakarta Persistence, `persist` làm một entity mới trở thành **managed**; không có nghĩa SQL nhất thiết đã được gửi ngay. `flush` đồng bộ các thay đổi cần thiết trong persistence context với database, nhưng vẫn **không commit** transaction.

### Rollback sau khi ID đã được gán

Ví dụ:

```java
tx.begin();

PurchaseOrder order = new PurchaseOrder("PO-ROLLBACK");
em.persist(order);

Long generatedId = order.getId(); // Có thể đã có giá trị.

tx.rollback();
```

Định danh `generatedId` có thể đã được lấy từ sequence hoặc generated key. Sau rollback, hàng dữ liệu **không được commit**, nhưng giá trị trong đối tượng Java không nhất thiết tự quay về `null`.

Vì vậy:

- Không dùng `id != null` để quyết định “đơn hàng đã được lưu thành công”.
- Không dùng `id == null` như kiểm tra duy nhất cho “đối tượng chưa từng tham gia persistence”.
- Sau rollback, phải xác định lại trạng thái của persistence context và đối tượng theo workflow phù hợp; thường nên kết thúc unit of work thất bại và mở một unit of work mới nếu cần thử lại.
- Nếu sequence đã phát giá trị, rollback thông thường không trả lại giá trị sequence; khoảng trống ID là bình thường.

## 4. Vì sao thời điểm có ID ảnh hưởng đến JDBC batching?

**JDBC batching** cho phép Hibernate gom nhiều lệnh SQL có dạng phù hợp để gửi qua JDBC theo một nhóm, giảm số lượt gọi tới database. Đây là tối ưu cách thực thi SQL, không thay đổi số hàng cần insert.

Giả sử cần lưu 1.000 entity mới.

### 4.1. Với `SEQUENCE`

Hibernate có thể thực hiện:

1. Lấy ID từ sequence hoặc từ dải ID đã được cấp sẵn.
2. Đưa các entity vào trạng thái managed và xếp hàng các thao tác insert.
3. Khi flush, gom những câu `INSERT` tương thích thành JDBC batch.

Ý tưởng:

```text
persist(A) -> ID 101, insert đang chờ
persist(B) -> ID 102, insert đang chờ
persist(C) -> ID 103, insert đang chờ
...
flush()
    -> batch INSERT A, B, C, ...
```

Một ví dụ cấu hình Hibernate:

```properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
```

- `hibernate.jdbc.batch_size` đặt số statement tối đa trong một JDBC batch theo cấu hình Hibernate.
- `hibernate.order_inserts` cho phép Hibernate sắp xếp các insert nhằm tăng cơ hội gom batch, nhưng việc sắp xếp có chi phí riêng và cần đánh giá thực tế.

Ví dụ `@SequenceGenerator(allocationSize = 50)` còn giảm số lần xin ID từ sequence, nhưng đây là **một tối ưu khác** với JDBC insert batching.

### 4.2. Với `IDENTITY`

Để biết ID của entity A, Hibernate thường phải insert A rồi nhận generated key. Với entity B, quá trình tương tự lặp lại.

```text
persist(A) -> INSERT A -> DB sinh ID 501 -> Hibernate nhận ID
persist(B) -> INSERT B -> DB sinh ID 502 -> Hibernate nhận ID
persist(C) -> INSERT C -> DB sinh ID 503 -> Hibernate nhận ID
```

Do ID cần được trả về sau từng insert, Hibernate ORM thông thường **không dùng JDBC insert batching cho các entity sử dụng identity identifier generation**. Những entity khác trong cùng transaction vẫn có thể được batch nếu mapping và thứ tự SQL cho phép.

Điều đó không có nghĩa database không thể hỗ trợ batch insert hoặc `INSERT ... RETURNING` theo cơ chế khác; đây là giới hạn/hành vi của **đường sinh IDENTITY thông thường trong Hibernate ORM**, không phải một định luật cho mọi thư viện truy cập dữ liệu hoặc mọi phiên bản database.

### 4.3. So sánh hai dòng thời gian

```text
SEQUENCE (biết ID trước INSERT)
    persist A -- ID A --+
    persist B -- ID B --+--> flush --> JDBC batch INSERT
    persist C -- ID C --+

IDENTITY (ID đến từ INSERT)
    persist A --> INSERT A --> ID A
    persist B --> INSERT B --> ID B
    persist C --> INSERT C --> ID C
```

Hệ quả thực tế: trong một nghiệp vụ insert rất nhiều entity, lựa chọn generator có thể ảnh hưởng đáng kể đến hiệu năng. Nhưng **không nên đổi chiến lược chỉ để tối ưu batching** mà bỏ qua khả năng hỗ trợ của DB, schema hiện hữu và ảnh hưởng đến triển khai.

## 5. `allocationSize` không phải `jdbc.batch_size`

Hai thông số thường cùng xuất hiện khi tối ưu insert nhưng giải quyết hai chi phí khác nhau.

```java
@SequenceGenerator(
    name = "order_seq_generator",
    sequenceName = "purchase_order_id_seq",
    allocationSize = 50
)
```

```properties
hibernate.jdbc.batch_size=50
```

| Thông số | Dùng cho | Tác dụng |
|---|---|---|
| `allocationSize = 50` | Identifier generator | Cấp nhiều ID từ một lần lấy giá trị nguồn theo optimizer |
| `hibernate.jdbc.batch_size=50` | JDBC SQL execution | Gom tối đa một số statement tương thích vào batch |
| `hibernate.order_inserts=true` | Action ordering | Tăng cơ hội nhóm các insert có SQL tương thích |

Ví dụ 1.000 entity:

- `allocationSize = 1` có thể cần lấy sequence gần 1.000 lần.
- `allocationSize = 50` với optimizer pooled có thể giảm đáng kể số lần lấy sequence.
- `jdbc.batch_size = 50` có thể giảm số lần gửi 1.000 insert tới database khi batching thực sự hoạt động.

Các con số trên là **minh họa quy mô**; việc thực thi chính xác còn phụ thuộc optimizer, trạng thái dải ID, số bảng, quan hệ, schema, driver, dialect, thứ tự insert và thời điểm flush.

Nếu dùng optimizer pooled/pooled-lo, bước tăng của database sequence phải **tương thích** với kích thước dải Hibernate kỳ vọng. Ví dụ ở những cấu hình pooled thông dụng, `allocationSize = 50` thường đi cùng sequence `INCREMENT BY 50`; không được nhầm với `CACHE 50` của database. Cấu hình lệch có thể bị validation từ chối hoặc dẫn tới cấp trùng dải ID.

## 6. Ví dụ insert hàng loạt với Session và Sequence

Giả sử bảng có khóa chính `BIGINT`, entity dùng `SEQUENCE` như trên và batch insert đã được cấu hình.

```java
import org.hibernate.Session;
import org.hibernate.SessionFactory;
import org.hibernate.Transaction;

public final class BulkOrderWriter {
    private final SessionFactory sessionFactory;

    public BulkOrderWriter(SessionFactory sessionFactory) {
        this.sessionFactory = sessionFactory;
    }

    public void insertOrders(int count) {
        try (Session session = sessionFactory.openSession()) {
            Transaction tx = session.beginTransaction();

            try {
                for (int i = 1; i <= count; i++) {
                    PurchaseOrder order =
                        new PurchaseOrder("PO-BATCH-" + i);

                    session.persist(order);

                    if (i % 50 == 0) {
                        session.flush();
                        session.clear();
                    }
                }

                tx.commit();
            } catch (RuntimeException ex) {
                if (tx.isActive()) {
                    tx.rollback();
                }
                throw ex;
            }
        }
    }
}
```

Trong ví dụ:

- Các ID có thể được sinh trước khi `INSERT` nhờ `SEQUENCE`.
- `flush()` gửi những thay đổi đang chờ; `clear()` tách các managed entity khỏi Session để giới hạn bộ nhớ khi xử lý nhiều entity.
- `commit()` hoàn tất transaction; `flush()` ở mỗi nhóm **không tạo commit riêng**.
- Nếu lỗi sau nhiều nhóm flush, rollback transaction có thể hoàn tác các row insert đã thực thi trong transaction theo semantics database.
- Vì `clear()` detach entity, code phía sau không được dựa vào dirty checking của các entity cũ trừ khi chúng được managed lại.

Ở hệ thống thực tế, cần bảo đảm `referenceCode` không trùng, transaction không quá dài và sequence/optimizer được cấu hình đúng. Batching không thay thế thiết kế và xử lý dữ liệu khối lượng lớn.

### Khi batching không hoạt động như kỳ vọng

Ngoài `IDENTITY`, các yếu tố có thể làm batch nhỏ hoặc khó gom:

- Dữ liệu thuộc nhiều bảng hoặc SQL insert có hình dạng khác nhau.
- Hibernate phải thực thi insert sớm do ràng buộc quan hệ hoặc sự kiện khác.
- Flush xảy ra với kích thước quá nhỏ.
- Mapping và driver/dialect không hỗ trợ hoặc hạn chế kiểu batching đang dùng.
- Transaction và Session được chia nhỏ khiến không có đủ statement trong cùng lượt flush.
- Một số kiểu ID, version hoặc chiến lược cập nhật có yêu cầu đặc biệt.

Vì vậy, chỉ nhìn cấu hình `hibernate.jdbc.batch_size=50` không chứng minh một batch 50 insert thực sự được gửi. Cần quan sát thống kê Hibernate, SQL/JDBC hoặc công cụ đo phù hợp.

## 7. Entity identity và Java object identity là hai khái niệm

Hibernate phải phân biệt ít nhất hai loại “giống nhau”:

- **Cùng object trong bộ nhớ:** `a == b`.
- **Cùng bản ghi nghiệp vụ/persistence:** hai entity biểu diễn cùng hàng dữ liệu, thường dựa vào khóa chính trong phạm vi database/tenant tương ứng.

Trong cùng một persistence context, Hibernate có **identity map**: cùng kiểu entity và cùng identifier thường tương ứng với cùng một managed instance.

```java
PurchaseOrder first = em.find(PurchaseOrder.class, 100L);
PurchaseOrder second = em.find(PurchaseOrder.class, 100L);

System.out.println(first == second); // Thông thường true trong cùng context.
```

Nhưng nếu tải từ hai `EntityManager` khác nhau:

```java
PurchaseOrder a = em1.find(PurchaseOrder.class, 100L);
PurchaseOrder b = em2.find(PurchaseOrder.class, 100L);

// a và b có thể là hai instance Java riêng biệt,
// dù biểu diễn cùng hàng dữ liệu.
```

Vì vậy, `Object.equals()` mặc định (so sánh theo reference) có thể đủ trong một số thiết kế chỉ xử lý managed entity trong một context, nhưng không nhất thiết phù hợp khi so sánh detached entity giữa request, Session hoặc khi dùng collection có ngữ nghĩa thực thể.

Mặt khác, **không phải mọi entity đều cần override `equals()`/`hashCode()`**. Cần chọn chính sách theo cách entity được sử dụng và yêu cầu domain.

## 8. Vấn đề lớn: ID được sinh sau khi object đã được tạo

Đối với entity dùng `@GeneratedValue`, ID thường bắt đầu là `null`:

```java
PurchaseOrder order = new PurchaseOrder("PO-100");

System.out.println(order.getId()); // null
em.persist(order);
System.out.println(order.getId()); // Có thể đã có ID, tùy generator.
```

Nếu định nghĩa `hashCode()` bằng ID:

```java
@Override
public int hashCode() {
    return java.util.Objects.hashCode(id);
}
```

thì hash code có thể đổi sau `persist()`. Điều này làm hỏng giả định quan trọng của `HashSet` và `HashMap`: khi một object đang nằm trong hash collection, hash code của nó phải ổn định trong suốt thời gian được sử dụng làm key/member.

### Ví dụ lỗi với `HashSet`

```java
PurchaseOrder order = new PurchaseOrder("PO-100");

Set<PurchaseOrder> orders = new HashSet<>();
orders.add(order);

boolean before = orders.contains(order); // true

em.persist(order); // ID từ null chuyển sang giá trị mới.

boolean after = orders.contains(order);
// Có thể false nếu hashCode phụ thuộc id đã thay đổi.
```

Bộ sưu tập đã đặt object vào bucket dựa trên hash cũ. Sau khi ID được gán, tìm kiếm theo hash mới có thể đi đến bucket khác.

Đáng chú ý: ngay cả khi cùng một instance `order`, `HashSet.contains(order)` vẫn có thể trả false vì cơ chế bucket, bất chấp `order.equals(order)` là true.

**Không nên lấy ID sinh tự động làm hash code biến đổi** nếu entity có thể được đưa vào hash collection trước khi nhận ID.

## 9. Vì sao `equals()` chỉ so sánh `id` có thể sai?

Một cách viết ngây thơ:

```java
@Override
public boolean equals(Object other) {
    if (!(other instanceof PurchaseOrder that)) {
        return false;
    }

    return java.util.Objects.equals(id, that.id);
}
```

Với hai entity mới chưa được persist:

```java
PurchaseOrder a = new PurchaseOrder("PO-A");
PurchaseOrder b = new PurchaseOrder("PO-B");

// a.id == null và b.id == null.
```

`Objects.equals(null, null)` trả true, vì vậy `a.equals(b)` có thể trả true dù chúng là **hai đơn hàng mới khác nhau**.

Điều đó có thể khiến:

```java
Set<PurchaseOrder> orders = new HashSet<>();
orders.add(a);
orders.add(b);

// Có thể chỉ giữ lại một phần tử nếu equals coi a và b bằng nhau.
```

Quy tắc cốt lõi khi dùng khóa sinh tự động để quyết định equality:

> Hai entity mới có ID `null` **không được coi bằng nhau chỉ vì cả hai chưa có ID**.

Trong ví dụ còn có vấn đề kiểu entity: so sánh duy nhất ID giữa các loại entity khác nhau cũng có thể sai nếu cùng một số khóa xuất hiện ở nhiều bảng.

## 10. Cách triển khai `equals()`/`hashCode()` dựa trên ID sinh tự động

Một phương án thường dùng cho **entity không có phân cấp kế thừa nghiệp vụ** là:

1. Nếu là cùng Java reference thì bằng nhau.
2. Nếu không cùng loại entity được chấp nhận, không bằng nhau.
3. Nếu ID chưa được sinh, hai instance khác nhau không bằng nhau.
4. Nếu cả hai đã có ID, so sánh ID.
5. Dùng **hash code không phụ thuộc ID** để hash không đổi khi ID từ `null` thành giá trị.

Ví dụ:

```java
import java.util.Objects;
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "order_generator"
    )
    @SequenceGenerator(
        name = "order_generator",
        sequenceName = "purchase_order_id_seq",
        allocationSize = 50
    )
    private Long id;

    @Column(nullable = false, length = 80)
    private String referenceCode;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String referenceCode) {
        this.referenceCode = referenceCode;
    }

    public Long getId() {
        return id;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof PurchaseOrder that)) {
            return false;
        }

        return getId() != null
            && Objects.equals(getId(), that.getId());
    }

    @Override
    public int hashCode() {
        return 31;
    }
}
```

Ở đây:

- Hai transient instance khác nhau với `id == null` không bị coi là bằng nhau.
- Khi entity đã có ID, hai instance thuộc kiểu tương ứng có cùng ID được xem là bằng nhau.
- `hashCode()` không đổi trước/sau `persist()`.
- Với Hibernate proxy thường là subtype của entity, `instanceof` và gọi `getId()` có thể hoạt động phù hợp mà không cần truy cập trực tiếp field ID của proxy.

**Phạm vi của mẫu:** ví dụ giả định `PurchaseOrder` không có hệ phân cấp entity mà việc dùng `instanceof PurchaseOrder` sẽ gộp nhầm hai lớp con khác nhau, và ID có cùng namespace. Nếu dùng inheritance, multitenancy hoặc entity cùng ID thuộc hai nguồn dữ liệu khác nhau, cần xác định equality theo đúng định danh nghiệp vụ/persistence đó.

Hash code hằng số hợp lệ theo contract Java (hai object bằng nhau có cùng hash), nhưng phân bố bucket kém hơn trong các hash collection chứa số lượng rất lớn entity. Nếu hiệu năng thao tác `HashSet` là trọng yếu, hãy đánh giá liệu một khóa nghiệp vụ bất biến có phù hợp hơn hoặc liệu cần lưu entity trực tiếp trong hash collection hay không.

### Getter trong `equals()` và Hibernate proxy

Hibernate có thể biểu diễn một entity lazy bằng proxy. Proxy thường giữ identifier mà không nhất thiết tải ngay toàn bộ trạng thái entity. Đọc trực tiếp field `that.id` trong `equals` có thể khác với dùng getter và có thể gặp behavior không mong muốn khi proxy chưa được khởi tạo.

Do đó, ví dụ sử dụng `getId()` thay vì truy cập trực tiếp `that.id`. Tuy nhiên, **việc proxy có khởi tạo hay không khi gọi `equals`/getter phụ thuộc cách Hibernate sinh proxy, khả năng bytecode enhancement và mapping**. Không nên coi `equals` luôn “miễn phí” về truy vấn.

Ngoài ra, so sánh bằng `getClass()` có thể thấy class proxy khác class entity gốc. Nếu thiết kế đòi hỏi chính xác cùng entity type, cần một chính sách so sánh kiểu thích hợp với chiến lược proxy/inheritance đang dùng, không máy móc thay `instanceof` bằng `getClass()` mà chưa đánh giá.

## 11. Có nên dùng business key trong `equals()`?

Một hướng khác là xác định equality bằng **business key ổn định**, ví dụ mã quốc gia ISO, ISBN sách hoặc một mã được cấp ngay khi tạo object.

Ví dụ:

```java
@Entity
@Table(
    name = "countries",
    uniqueConstraints = @UniqueConstraint(columnNames = "iso_code")
)
public class Country {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "iso_code", nullable = false, unique = true, updatable = false)
    private String isoCode;

    protected Country() {
    }

    public Country(String isoCode) {
        this.isoCode = isoCode;
    }

    public String getIsoCode() {
        return isoCode;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Country that)) {
            return false;
        }
        return java.util.Objects.equals(
            getIsoCode(), that.getIsoCode()
        );
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hashCode(getIsoCode());
    }
}
```

Mẫu này **chỉ phù hợp** khi:

- Business key được đặt trước khi entity tham gia hash collection.
- Business key thực sự là bất biến trong toàn bộ vòng đời entity, kể cả khi đã persist.
- Nó có ý nghĩa duy nhất theo phạm vi ứng dụng, được database bảo vệ bằng unique constraint thích hợp.
- Các giá trị `null` được xử lý theo chính sách rõ ràng; ở ví dụ, cần đảm bảo `isoCode` không null trong constructor và các đường khởi tạo nghiệp vụ.
- Phạm vi equality và proxy/inheritance được định nghĩa nhất quán.

Nếu mã nghiệp vụ có thể sửa, ví dụ `customer.email` hoặc `product.displayName`, đưa nó vào `hashCode` sẽ lặp lại vấn đề hash thay đổi. Một email có thể không còn là identifier đáng tin khi người dùng thay đổi email.

Trong Hibernate, `@NaturalId` mô tả natural identifier ở mức framework; nó có thể hữu ích khi business key phù hợp, nhưng **không tự sinh `equals()`/`hashCode()`** và không có nghĩa mọi thuộc tính đánh dấu natural ID đều luôn bất biến trong mọi cấu hình.

## 12. So sánh các chính sách `equals()`/`hashCode()`

| Chính sách | Khi nào hợp lý | Rủi ro chính |
|---|---|---|
| Giữ nguyên `Object.equals` | Entity chỉ được xử lý theo Java reference trong một persistence context hoặc không cần so sánh xuyên context | Hai detached instance cùng hàng không bằng nhau |
| So sánh generated ID khi khác `null`, hash hằng số | Cần so sánh cùng entity qua nhiều Session, ID sinh sau khi tạo | Hash collision trong collection rất lớn; phải xử lý proxy/inheritance/tenant |
| Dùng natural/business key bất biến | Có khóa nghiệp vụ duy nhất, ổn định từ lúc tạo entity | Nếu business key thay đổi hoặc chưa được gán thì hash/equality sai |
| So sánh tất cả thuộc tính | Thường phù hợp hơn với value object bất biến | Với entity, có thể kích hoạt lazy load, đệ quy, thay đổi equality khi update |
| So sánh `id` kể cả khi `null` | Không nên cho generated ID | Hai transient entity khác nhau có thể bằng nhau |
| `hashCode = id.hashCode()` | Chỉ khi ID bất biến đã tồn tại trước khi object vào hash collection | ID sinh sau `persist` làm hash thay đổi |

### Entity không phải value object

Một entity có **identity xuyên suốt thời gian**: đơn hàng vẫn là cùng đơn hàng dù trạng thái hoặc tổng tiền thay đổi. Trong khi đó, value object như `Money(amount, currency)` thường so sánh theo giá trị và nên bất biến.

Dùng Lombok `@Data` hoặc `@EqualsAndHashCode` mặc định trên entity có thể vô tình đưa các trường mutable và association lazy vào phép so sánh, gây truy vấn thừa, recursion hoặc thay đổi hash code. Nên viết chính sách có chủ đích hoặc cấu hình generator rõ ràng thay vì tự động so sánh toàn bộ fields của entity.

## 13. Ảnh hưởng đến `Set`, `Map` và association trong Hibernate

Trong domain Java, việc dùng `Set<Entity>` khá phổ biến:

```java
@OneToMany(mappedBy = "order")
private Set<OrderLine> lines = new HashSet<>();
```

Khi thêm một entity mới vào `HashSet`, `hashCode()` phải ổn định trong quá trình entity nằm trong collection.

Ví dụ:

```java
OrderLine line = new OrderLine("SKU-01", 2);
order.getLines().add(line);

// Nếu hashCode() dựa vào id đang null, rồi id được sinh sau persist,
// collection có thể không tìm hoặc remove đúng phần tử.
entityManager.persist(order);
```

Trong mapping trên, việc `persist(order)` có cascade tới `OrderLine` hay không phụ thuộc `cascade` đã cấu hình; ví dụ chỉ minh họa rủi ro hash thay đổi. Dùng `Set` còn làm contract của `equals` quan trọng vì `Set` dựa trên phép so sánh để quyết định phần tử trùng.

### Hệ quả với `HashMap`

Nếu dùng entity làm key:

```java
Map<PurchaseOrder, String> tags = new HashMap<>();

tags.put(order, "urgent");
em.persist(order);

String tag = tags.get(order);
```

Nếu hash của `order` đổi vì ID được sinh, `get(order)` có thể không tìm thấy key dù chính object đó vẫn còn trong map.

Một phương án khác thường rõ hơn khi đã có ID là dùng **ID làm key** thay vì entity:

```java
Map<Long, String> tagsByOrderId = new HashMap<>();
tagsByOrderId.put(order.getId(), "urgent");
```

Nhưng cách này chỉ thích hợp **sau khi ID thực sự có giá trị** và cần tính đến hệ thống nhiều tenant hoặc nguồn dữ liệu. Nó không giúp nếu code cần đưa entity mới chưa có ID vào map từ trước.

### Không dùng `hashCode` làm định danh DB

Hash code có thể va chạm; nó không phải primary key. Tương tự, một ID số duy nhất trong bảng không thể thay thế toàn bộ contract `equals` cho object ở Java nếu chưa xử lý null, kiểu entity và phạm vi ID.

## 14. Tác động của proxy, `getReference()` và detached entity

Hibernate hỗ trợ lazy reference:

```java
PurchaseOrder reference =
    entityManager.getReference(PurchaseOrder.class, orderId);
```

Provider có thể trả về proxy chưa tải dữ liệu đầy đủ. So sánh proxy với entity được tải trong một persistence context khác có thể đặt ra hai vấn đề:

1. **So sánh kiểu:** proxy class có thể khác entity class khi dùng `getClass()`.
2. **Truy cập thuộc tính:** `equals` gọi getter ngoài identifier có thể làm proxy initialize; nếu Session đã đóng có thể phát sinh `LazyInitializationException`.

Ví dụ chính sách dựa trên generated ID thường cố gắng chỉ so sánh identifier:

```java
return getId() != null
    && getId().equals(that.getId());
```

Dù vậy, đừng khẳng định mọi proxy luôn trả ID không truy vấn. Behavior phụ thuộc mapping và implementation cụ thể. Nếu cần contract chính xác cho hệ phân cấp entity phức tạp, nên thiết kế kiểm soát type và proxy một cách rõ ràng, có thể sử dụng API Hibernate đã được công bố theo phiên bản đang chạy.

### `merge()` và identity

Sau khi entity trở thành detached, `EntityManager.merge(detached)` trả về **managed instance** tương ứng:

```java
PurchaseOrder managed = entityManager.merge(detached);

System.out.println(managed == detached); // Có thể false.
```

`merge` không biến object truyền vào thành managed; object trả về mới là đối tượng thuộc persistence context hiện tại.

Nếu `equals` dựa trên identifier khác null và cùng entity type, hai object có thể được xem là bằng nhau mặc dù khác Java reference. Đây là một lý do các ứng dụng xử lý detached entity cần chính sách equality rõ ràng.

## 15. Khi nào ID được sinh không phụ thuộc vào `commit`?

Một hiểu lầm thường gặp: “Chỉ commit xong entity mới có ID.”

Thực tế:

- Với `SEQUENCE`, Hibernate thường lấy ID trước insert nên ID có thể có ngay sau `persist`.
- Với `UUID` được generator phía Java tạo, ID có thể có trước insert.
- Với `IDENTITY`, ID thường có sau khi database insert thành công trong transaction, trước khi commit.
- Với ID gán thủ công, ID tồn tại ngay khi constructor hoặc setter gán.

Vì vậy **commit không phải mốc duy nhất** để biết identifier. Nhưng commit là mốc quan trọng để xác định **transaction đã hoàn tất thành công**.

### Có nên gọi `flush()` chỉ để lấy ID?

Tùy generator. Với `SEQUENCE`, thường không cần flush chỉ để có ID. Với `IDENTITY`, nếu cần generated key mà insert còn trì hoãn, flush có thể buộc đồng bộ insert khi transaction hợp lệ. Tuy nhiên, không nên tự thêm flush ở mọi đoạn code chỉ vì muốn “an toàn”: flush có chi phí SQL và ảnh hưởng batching; nó có thể khiến các constraint được kiểm tra sớm và tác động thứ tự thực thi.

Hãy hỏi: *nghiệp vụ thực sự cần biết ID ngay lúc đó, hay chỉ cần một tham chiếu tới entity managed?* Với quan hệ entity, Hibernate thường có thể quản lý khóa ngoại thông qua tham chiếu object mà không cần code nghiệp vụ tự ép flush sau từng `persist`.

### Có nên dựa vào `id == null` để nhận biết entity mới?

Đây là một **heuristic** thường được sử dụng, đặc biệt cho entity có generated ID nullable. Tuy nhiên, nó không mô tả đầy đủ trạng thái persistence:

- Entity có ID nhưng transaction đã rollback.
- Detached entity có ID nhưng không được Session hiện tại quản lý.
- Entity dùng assigned ID có ID từ trước `persist`.
- Entity dùng IDENTITY có thể chưa nhận ID cho đến khi insert xảy ra ở một vài trường hợp.

Để biết object có đang được quản lý hay không trong context hiện tại, dùng `entityManager.contains(entity)` hoặc API phù hợp, thay vì suy luận từ ID:

```java
boolean managedHere = entityManager.contains(order);
```

Lệnh này kiểm tra **managed state trong đúng EntityManager hiện tại**. Nó không xác nhận row đã commit.

## 16. Chọn generator khi cần tạo nhiều entity

Lựa chọn ID là quyết định giữa semantics, hiệu năng và tính vận hành.

### Trường hợp A: ứng dụng nhập đơn hàng theo lô

Một batch job cần insert hàng chục nghìn đơn hàng vào một database hỗ trợ sequence. Chọn `SEQUENCE` với optimizer pooled tương thích, batching JDBC và flush/clear theo nhóm thường có lợi:

```text
SEQUENCE:
  giảm round-trip xin ID
  + biết ID trước INSERT
  + thuận lợi cho JDBC insert batching
```

Cần đồng bộ `allocationSize` với cấu hình sequence và mọi producer cùng dùng nó.

### Trường hợp B: bảng legacy dùng auto-increment

Schema đã có khóa `IDENTITY` và nhiều ứng dụng đang dựa vào cơ chế đó. Hibernate có thể sử dụng `GenerationType.IDENTITY` để phù hợp schema.

```text
IDENTITY:
  DB sinh ID khi INSERT
  + ít thay đổi schema legacy
  - hạn chế JDBC insert batching của entity dùng IDENTITY
```

Nếu throughput insert là nút thắt, cần đo đạc trước khi thiết kế migration sang sequence hoặc cơ chế khác; không nên đổi chỉ vì muốn một con số batch lớn hơn.

### Trường hợp C: nhiều service tạo object trước khi gửi database

UUID có thể giúp định danh đối tượng sớm mà không cần DB cấp số ngay lập tức. Nhưng cần xem phạm vi định danh, index, phân bố khóa và tính nhất quán giữa các service. Không vì ID biết trước mà suy ra dữ liệu đã được lưu hoặc đã đồng bộ giữa các hệ thống.

### Trường hợp D: entity tham gia nhiều `HashSet` trước khi persist

Dù chọn `SEQUENCE`, `IDENTITY` hay UUID generator, nếu ID **chỉ được sinh sau khi object được tạo**, chính sách `hashCode` dựa vào ID vẫn có thể thay đổi.

Giải pháp là tránh hash biến đổi hoặc dùng business key bất biến được cấp **trước khi** entity vào collection. Chuyển từ `IDENTITY` sang `SEQUENCE` có thể khiến ID xuất hiện sớm hơn lúc insert, nhưng **không tự sửa lỗi `hashCode`** nếu entity đã được thêm vào Set trước lúc `persist`.

## 17. Các lỗi thường gặp và cách nhận biết

| Triệu chứng | Điều cần kiểm tra | Cách xử lý theo nguyên nhân |
|---|---|---|
| ID vẫn null ngay sau `new` | Entity dùng generator tự động? | Đây là hành vi bình thường trước persistence |
| ID vẫn null ở thời điểm code kỳ vọng sau `persist` | `GenerationType`, transaction, Hibernate version, delayed insert | Không giả định mọi generator cùng thời điểm; xem hành vi thực tế |
| Nhiều `INSERT` riêng dù đã bật `batch_size` | Entity có `IDENTITY`? Flush quá thường xuyên? SQL có tương thích? | Chọn cách cấp khóa/cấu hình phù hợp và đo batch thực |
| `HashSet.contains(entity)` trả false sau persist | `hashCode` có đổi theo ID không? | Dùng hash ổn định hoặc business key bất biến |
| Hai entity mới bị coi là bằng nhau | `equals` có so sánh `null` ID không? | Chỉ so sánh generated ID khi khác null; giữ reference identity cho transient |
| `LazyInitializationException` trong `equals` | Có truy cập association hoặc trường lazy không? | Tránh đưa association/lazy state vào equality |
| Object detached và managed không cùng reference | Có dùng `merge` hoặc nhiều Session không? | Phân biệt `==` với domain/persistence identity |
| Dù ID đã có, truy vấn khác chưa thấy hàng | Insert/commit chưa xảy ra, isolation hoặc transaction khác | Phân biệt ID được cấp, flush và commit |
| Sau rollback entity vẫn có ID | Generator đã cấp giá trị trước rollback | Không coi ID là bằng chứng commit; quản lý lại unit of work |
| Sequence tạo dải trùng hoặc khởi động báo mismatch | `allocationSize`, optimizer và sequence increment | Đồng bộ mapping, DB metadata và producer sử dụng chung |

### Lỗi với Lombok

Ví dụ sau thường nguy hiểm trên entity có quan hệ:

```java
@Data
@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue
    private Long id;

    @OneToMany(mappedBy = "order")
    private Set<OrderLine> lines;
}
```

`@Data` của Lombok tạo `equals`/`hashCode` dựa trên fields theo quy tắc của annotation. Với entity, điều này có thể đưa ID đang thay đổi, mutable state hoặc lazy association vào equality, làm phát sinh recursion, truy vấn bất ngờ hoặc hash không ổn định.

Có thể sử dụng Lombok chọn lọc cho getter/setter/constructor, nhưng cần định nghĩa equality của entity có chủ đích và không mặc định rằng mọi field đều là thành phần định danh.

## 18. Cách quan sát thời điểm ID và batching trong ứng dụng thử nghiệm

Một bài thực hành có thể dùng **cùng một entity nhưng các bảng/test schema tách biệt** cho hai chiến lược khác nhau.

**Thử nghiệm 1 — SEQUENCE**

- Tạo sequence và entity dùng `@GeneratedValue(strategy = SEQUENCE)`.
- Bắt đầu transaction, tạo entity rồi in ID trước/sau `persist`, sau `flush`.
- Quan sát log truy vấn sequence, log `INSERT` và thống kê JDBC batch.
- Rollback và quan sát rằng ID trong object không chứng minh có dữ liệu được commit.

**Thử nghiệm 2 — IDENTITY**

- Tạo bảng test có cột identity và entity dùng `GenerationType.IDENTITY`.
- Bật cùng `hibernate.jdbc.batch_size`.
- Persist nhiều entity trong transaction.
- Quan sát việc Hibernate phải insert để biết ID và khả năng batching của entity này.

**Thử nghiệm 3 — Equality**

- Tạo hai transient entity khác nhau, đều có `id == null`.
- Thêm một entity vào `HashSet` trước khi persist.
- Đối chiếu cách viết `hashCode` dựa vào ID với cách viết hash ổn định.
- Kiểm tra trường hợp detached instance khác reference nhưng cùng identifier.

Các thử nghiệm nhằm hiểu đúng **thời điểm và cơ chế**, không nên dùng kết quả của một database hoặc Hibernate version để khẳng định mọi môi trường đều xử lý y hệt.

### Theo dõi SQL cần nhìn hai loại chi phí

Khi đo:

- **Lấy ID:** số lần gọi sequence hoặc generator table, hay số lần chờ identity key.
- **Ghi hàng:** số `INSERT`, số JDBC batch và thời gian thực thi.

Một chiến lược có thể giảm lượt lấy ID nhưng vẫn phải insert đủ N hàng. Ngược lại, `jdbc.batch_size` có thể được đặt cao nhưng không có tác dụng với entity dùng `IDENTITY` theo cơ chế thông thường.

## 19. Những nguyên tắc áp dụng khi thiết kế entity

1. **Biết ID, đã insert và đã commit là ba sự kiện khác nhau.** Đừng dùng `id != null` làm bằng chứng dữ liệu đã tồn tại bền vững.
2. `SEQUENCE` thường giúp Hibernate biết khóa **trước `INSERT`**, tạo điều kiện trì hoãn insert và JDBC batching.
3. `IDENTITY` thường yêu cầu insert để nhận generated key, khiến Hibernate ORM thông thường **không batch insert** cho loại entity này.
4. `TABLE` có thể sinh ID trước insert nhưng dễ tăng truy vấn và contention; UUID sinh phía ứng dụng cũng cho ID sớm nhưng có đánh đổi riêng.
5. `allocationSize` tối ưu việc **cấp ID**; `hibernate.jdbc.batch_size` tối ưu **thực thi JDBC**. Hai cơ chế độc lập và phải đánh giá riêng.
6. Entity có generated ID thường bắt đầu với `id == null`. Nếu dùng ID trong `equals`, **không coi hai ID null là hai entity bằng nhau**.
7. **Không dùng hash code thay đổi theo generated ID** khi entity có thể nằm trong `HashSet`/`HashMap` trước lúc ID được cấp.
8. Nếu có natural/business key bất biến và unique, có thể cân nhắc equality theo khóa ấy; không dùng thuộc tính mutable hoặc lazy association như thành phần equality.
9. Hibernate proxy, detached object, inheritance và multitenancy có thể ảnh hưởng so sánh thực thể. Chọn contract phù hợp với domain và mô hình persistence.
10. Đo lường SQL/batch thực tế và kiểm tra behavior của đúng phiên bản Hibernate/database trước khi đưa ra quyết định tối ưu.

**Ý chính:** thời điểm Hibernate biết khóa chính quyết định mức tự do sắp xếp và gom lệnh `INSERT`, đồng thời làm lộ ra sự khác biệt giữa **identity trong database** và **equality của đối tượng Java**. Thiết kế generator, transaction và `equals()`/`hashCode()` nhất quán sẽ giúp hệ thống vừa ghi dữ liệu hiệu quả vừa tránh lỗi khó phát hiện trong entity collection.
