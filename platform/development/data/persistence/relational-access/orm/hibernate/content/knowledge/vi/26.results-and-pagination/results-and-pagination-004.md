# Đọc kết quả bằng Stream hoặc ScrollableResults và trách nhiệm đóng tài nguyên

Trong ứng dụng Hibernate, không phải truy vấn nào cũng chỉ trả vài chục bản ghi. Một báo cáo xuất CSV, tác vụ đồng bộ dữ liệu, công việc kiểm tra tính hợp lệ hoặc xử lý một tập dữ liệu lớn có thể phải đọc hàng chục nghìn, hàng triệu rows. Nếu gọi `getResultList()` rồi đưa toàn bộ kết quả vào một `List`, ứng dụng có thể tiêu tốn nhiều bộ nhớ và chịu áp lực garbage collection.

Hibernate cung cấp hai hướng đọc tuần tự đáng chú ý:

- **`Stream<T>`:** sử dụng Java Stream API qua `Query#getResultStream()` (JPA) hoặc `Query#stream()` (Hibernate). Thích hợp cho pipeline duyệt kết quả theo thứ tự, lọc/xử lý từng phần tử và đóng tài nguyên bằng `try-with-resources`.
- **`ScrollableResults<T>`:** API cursor của Hibernate, được lấy bằng `Query#scroll(...)`. Thích hợp khi muốn kiểm soát vòng lặp, vị trí cursor và thời điểm xử lý từng row. Đây là **API riêng của Hibernate**, không phải chuẩn JPQL portable.

Ví dụ dùng Java Stream:

~~~java
try (Stream<Book> stream = entityManager.createQuery(
        "select b from Book b order by b.id", Book.class
    ).getResultStream()) {

    stream.forEach(book -> exportBook(book));
}
~~~

Ví dụ dùng Hibernate ScrollableResults:

~~~java
Session session = entityManager.unwrap(Session.class);

Query<Book> query = session.createQuery(
    "select b from Book b order by b.id",
    Book.class
);

try (ScrollableResults<Book> cursor =
         query.scroll(ScrollMode.FORWARD_ONLY)) {

    while (cursor.next()) {
        Book book = cursor.get();
        exportBook(book);
    }
}
~~~

**Điểm trọng tâm:** Stream và ScrollableResults là **cơ chế tiêu thụ kết quả**, không phải lời bảo đảm rằng database chỉ đưa từng row qua mạng hoặc Hibernate chỉ giữ một object trong memory. Cách JDBC driver fetch dữ liệu, transaction, persistence context, cache và mã xử lý của ứng dụng quyết định hiệu quả thật. Đồng thời, cả stream và scroll có thể giữ `ResultSet`, `Statement`, JDBC connection hoặc cursor DB còn mở cho tới khi đóng.

> **Phạm vi:** Bài dùng Hibernate ORM 6.x, Jakarta Persistence (`jakarta.persistence`) và Java 17+ trong các ví dụ. Hibernate 5 thường dùng `javax.persistence` và một số API ScrollableResults có khác biệt, đặc biệt kiểu trả về của `get()`. Ví dụ Spring có chú thích riêng. Cơ chế cursor, fetch size và transaction thay đổi theo JDBC driver và DBMS; chỉ dựa vào tên API không đủ để kết luận có streaming thật ở database.

## 1. Tình huống dẫn nhập: xuất hàng trăm nghìn bản ghi

Giả sử ứng dụng quản lý đơn hàng và cần xuất danh sách đơn theo thời gian. Entity đơn giản:

~~~java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private OrderStatus status;

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public String getOrderNumber() { return orderNumber; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public OrderStatus getStatus() { return status; }
}
~~~

Dùng `getResultList()`:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery(
    """
    select o
    from PurchaseOrder o
    where o.createdAt >= :from
    order by o.id
    """,
    PurchaseOrder.class
)
.setParameter("from", from)
.getResultList();

for (PurchaseOrder order : orders) {
    writeCsvRow(order);
}
~~~

Vấn đề: `getResultList()` tạo kết quả dạng collection trong memory của ứng dụng. Với số row lớn, bộ nhớ có thể được dùng bởi:

1. Danh sách tham chiếu `List`.
2. Entity objects và các object thuộc tính.
3. Hibernate first-level cache/persistence context và metadata liên quan.
4. JDBC driver nếu nó đã buffer nhiều rows.
5. Các object tạm trong xử lý CSV, mapping hoặc collections liên quan.

Thay `List` bằng Stream hoặc ScrollableResults giúp **tiêu thụ từng phần tử** và có thể hỗ trợ JDBC fetching tăng dần khi driver được cấu hình phù hợp. Nhưng cần quản lý thêm **đời sống tài nguyên**.

## 2. Ba cách đọc kết quả và mục tiêu của từng cách

| Cách đọc | API chính | Hình thức sử dụng | Điểm cần chú ý |
|---|---|---|---|
| Danh sách | `getResultList()` | `List<T>` có toàn bộ kết quả của query. | Đơn giản nhưng có thể tốn RAM. |
| Java Stream | `getResultStream()` hoặc `stream()` | `Stream<T>` có thể tiêu thụ tuần tự. | Phải đóng, transaction/context còn sống; provider có thể materialize trước. |
| Hibernate scroll | `scroll(ScrollMode...)` | Cursor `ScrollableResults<T>`, `next()`, `get()`. | API Hibernate-specific, phải đóng; mode phụ thuộc driver. |

**Không có cách nào tốt nhất trong mọi tình huống.**

- Với danh sách vài chục rows, `getResultList()` thường đơn giản, đủ tốt và tài nguyên query ngắn hạn.
- Với báo cáo dài, stream/scroll có thể giúp giảm bộ nhớ khi xử lý từng row.
- Với hệ thống cần chia lô, retry, checkpoint và tránh giữ transaction lâu, **pagination/keyset pagination** thường phù hợp hơn một cursor mở quá lâu.
- Khi chỉ cần một vài fields, dùng DTO/scalar projection thay vì hydrate entity đầy đủ.

## 3. Stream trong Java không đồng nghĩa JDBC streaming

`java.util.stream.Stream` là giao diện mô tả các phép xử lý dữ liệu tuần tự hoặc song song theo pipeline. Nó **không tự biết** JDBC, ResultSet hay connection pool.

Có hai cách triển khai rất khác nhau:

~~~text
Cách A: materialize trước
DB -> JDBC -> List gồm toàn bộ rows -> list.stream() -> consumer

Cách B: đọc thông qua cursor
DB -> JDBC ResultSet / cursor -> Hibernate Stream -> consumer
~~~

Jakarta Persistence có `getResultStream()`. Ở cấp API, provider có thể triển khai dựa trên `getResultList().stream()` hoặc tối ưu để đọc thông qua JDBC cursor. Hibernate hỗ trợ streaming/cursor cho các truy vấn thích hợp, nhưng cách fetch tại JDBC/DB vẫn phụ thuộc driver, cấu hình và query.

**Vì vậy, chỉ đổi `getResultList().stream()` thành `getResultStream()` không bảo đảm đã giảm memory.** Cần kiểm tra provider thực tế và tài nguyên bên dưới.

## 4. getResultList().stream() khác getResultStream()

Đây là anti-pattern phổ biến khi muốn tối ưu bộ nhớ:

~~~java
List<PurchaseOrder> all = query.getResultList();

try (Stream<PurchaseOrder> stream = all.stream()) {
    stream.forEach(this::process);
}
~~~

Tại thời điểm `all.stream()`, `all` đã giữ toàn bộ kết quả; đóng stream không giải phóng danh sách đó.

Đúng hướng API hơn:

~~~java
try (Stream<PurchaseOrder> stream = query.getResultStream()) {
    stream.forEach(this::process);
}
~~~

Trong Hibernate ORM 6.x, một truy vấn Hibernate có thể sử dụng cơ chế cursor cho stream. Nhưng **fetch size, transaction và persistence context** vẫn phải được xem xét. Việc trả `Stream` từ API chỉ nói lên interface, không tự nói lên lượng dữ liệu đã nằm trong JDBC driver buffer.

## 5. API JPA: TypedQuery.getResultStream()

Từ JPA 2.2/Jakarta Persistence, `Query` và `TypedQuery` cung cấp `getResultStream()`.

~~~java
TypedQuery<PurchaseOrder> query =
    entityManager.createQuery(
        """
        select o
        from PurchaseOrder o
        where o.status = :status
        order by o.id
        """,
        PurchaseOrder.class
    );

query.setParameter("status", OrderStatus.SHIPPED);

try (Stream<PurchaseOrder> results = query.getResultStream()) {
    results.forEach(order -> {
        exportOrder(
            order.getId(),
            order.getOrderNumber(),
            order.getCreatedAt()
        );
    });
}
~~~

Điểm cần nhớ:

- `TypedQuery<PurchaseOrder>` giúp kiểu phần tử rõ ràng.
- Query parameter được bind như JPA thông thường.
- Đọc Stream diễn ra trong phạm vi còn hiệu lực của `EntityManager`, transaction khi cần và JDBC resources.
- `try-with-resources` gọi `close()` khi rời block, kể cả khi exception xuất hiện trong lúc tiêu thụ.
- Không giữ `PurchaseOrder` references trong một collection khác nếu mục tiêu là giảm memory.

### Vì sao không chỉ gọi forEach?

~~~java
query.getResultStream().forEach(this::process); // Không nên
~~~

Viết như trên **không đóng stream một cách tường minh**. Trong Hibernate, stream có thể giữ JDBC cursor/ResultSet mở. Hãy dùng:

~~~java
try (Stream<PurchaseOrder> stream = query.getResultStream()) {
    stream.forEach(this::process);
}
~~~

Ngay cả khi một provider hiện tại không giữ resources trong Stream, đóng tường minh là hợp đồng quản lý tài nguyên an toàn hơn khi ứng dụng đổi provider/phiên bản.

## 6. Hibernate Session: Query.stream()

Nếu làm việc trực tiếp với Hibernate:

~~~java
import org.hibernate.Session;
import org.hibernate.query.Query;
import java.util.stream.Stream;

Session session = entityManager.unwrap(Session.class);

Query<PurchaseOrder> query = session.createQuery(
    """
    select o
    from PurchaseOrder o
    where o.createdAt >= :from
    order by o.id
    """,
    PurchaseOrder.class
);

query.setParameter("from", from);

try (Stream<PurchaseOrder> stream = query.stream()) {
    stream.forEach(this::exportOrder);
}
~~~

`Session.createQuery()` là API Hibernate. `Query.stream()` thường sử dụng kết quả scroll phía dưới. Đừng coi phương thức này là `parallelStream()`; Hibernate Session và JDBC ResultSet không phù hợp cho tiêu thụ đồng thời từ nhiều threads.

### Khi đã có EntityManager

Không phải tạo Session mới; có thể `unwrap` Session đang dùng:

~~~java
Session session = entityManager.unwrap(Session.class);
~~~

Với EntityManager do Spring/JTA quản lý, **không tự đóng Session/EntityManager được framework quản lý** chỉ vì đã unwrap. Bạn **phải đóng stream/cursor**, còn lifecycle EntityManager/transaction thuộc chủ sở hữu của chúng.

## 7. ScrollableResults là gì?

`org.hibernate.ScrollableResults<T>` là giao diện duyệt kết quả truy vấn theo kiểu cursor. Nó cho phép di chuyển qua các rows và lấy phần tử hiện tại.

~~~java
import org.hibernate.ScrollMode;
import org.hibernate.ScrollableResults;
import org.hibernate.Session;
import org.hibernate.query.Query;

Session session = entityManager.unwrap(Session.class);

Query<PurchaseOrder> query = session.createQuery(
    "select o from PurchaseOrder o order by o.id",
    PurchaseOrder.class
);

try (ScrollableResults<PurchaseOrder> cursor =
         query.scroll(ScrollMode.FORWARD_ONLY)) {

    while (cursor.next()) {
        PurchaseOrder order = cursor.get();
        exportOrder(order);
    }
}
~~~

Hai thao tác quan trọng:

- `next()`: tiến tới row kế tiếp; trả `false` khi đã hết.
- `get()`: lấy kết quả ở vị trí hiện tại.

**Lưu ý phiên bản:** Với Hibernate 6, `ScrollableResults<R>#get()` thường trả `R` theo typed query. Tài liệu/ứng dụng Hibernate 5 có thể dùng `Object[]` hoặc cách đọc kết quả khác. Không copy code của phiên bản cũ sang 6 mà không đối chiếu API version.

## 8. ScrollMode.FORWARD_ONLY

Hibernate có `ScrollMode` để chỉ định kiểu di chuyển cursor. Với bài toán export tuần tự, `FORWARD_ONLY` thường là lựa chọn đầu tiên:

~~~java
try (ScrollableResults<PurchaseOrder> cursor =
         query.scroll(ScrollMode.FORWARD_ONLY)) {

    while (cursor.next()) {
        process(cursor.get());
    }
}
~~~

`FORWARD_ONLY` diễn đạt ý định chỉ đi từ đầu tới cuối, không cần di chuyển ngược.

Lợi ích tiềm năng:

- Phù hợp với cursor JDBC forward-only phổ biến.
- Driver/database có thể tối ưu hơn so với cursor phải hỗ trợ random access.
- Vòng lặp dễ đọc và dễ dừng khi đủ điều kiện.

Không bảo đảm mọi driver tạo server-side cursor hay mỗi `next()` sẽ đi một network round trip. Driver có thể buffer một phần hoặc toàn bộ result set.

## 9. SCROLL_INSENSITIVE và SCROLL_SENSITIVE

Các mode khác có thể gặp:

| Mode | Ý định khái niệm | Lưu ý |
|---|---|---|
| `FORWARD_ONLY` | Di chuyển tuần tự về phía trước. | Thường phù hợp nhất với xử lý nhiều rows. |
| `SCROLL_INSENSITIVE` | Cho phép điều hướng, không phản ánh thay đổi bên ngoài theo semantics cursor. | JDBC/DB có thể mô phỏng hoặc không hỗ trợ đầy đủ. |
| `SCROLL_SENSITIVE` | Cho phép điều hướng với ý định nhận biết một số thay đổi bên ngoài. | Khả năng và mức độ phản ánh thay đổi phụ thuộc JDBC driver/DB/isolation. |

Khi cần `previous()`, `first()`, `last()` hoặc di chuyển theo vị trí, hãy kiểm tra những khả năng được interface/provider version và JDBC ResultSet type thực sự hỗ trợ.

**Không dùng SCROLL_SENSITIVE làm cơ chế realtime đồng bộ dữ liệu.** Isolation level, transaction snapshot và hỗ trợ cursor có thể khiến kết quả không phản ánh mọi cập nhật mới.

## 10. Stream và ScrollableResults thường được thực thi khi nào?

Khi gọi:

~~~java
Query<PurchaseOrder> query =
    session.createQuery("from PurchaseOrder", PurchaseOrder.class);
~~~

Hibernate thường mới tạo đối tượng query. Khi lấy Stream hoặc ScrollableResults, provider có thể chuẩn bị/thực thi SQL và mở resources. Terminal operation trên Stream sẽ duyệt dữ liệu; cursor có thể đã tồn tại từ lúc tạo stream.

~~~text
createQuery()
   |
   v
setParameter(), setFetchSize(), setReadOnly()
   |
   v
getResultStream() / stream() / scroll()
   |
   v
JDBC Statement + ResultSet có thể được mở
   |
   v
duyệt từng phần tử
   |
   v
close() Stream/ScrollableResults
   |
   v
ResultSet/Statement/cursor được giải phóng theo provider
~~~

Không trì hoãn tiêu thụ sau khi đã đóng EntityManager hoặc rời transaction cần thiết. Cũng không dùng lazy Stream trong một request đã trả response xong rồi mới kỳ vọng có thể truy cập database.

## 11. Những tài nguyên nào có thể bị giữ?

Một stream/cursor dựa trên JDBC có thể giữ:

1. **JDBC ResultSet** — con trỏ đến các rows.
2. **JDBC Statement/PreparedStatement** — statement còn đang thực thi/được sử dụng.
3. **JDBC Connection** — connection mượn từ pool, có thể phải giữ đến khi đọc xong.
4. **Database cursor/server-side resources** — tùy driver/DBMS.
5. **Database transaction/snapshot** — nhất là khi cursor cần transaction còn mở.
6. **Hibernate Session/persistence context** — quản lý identity và entity state trong suốt vòng lặp.

Đóng stream/cursor giúp giải phóng tài nguyên thuộc query. Nó không tự động đồng nghĩa đóng EntityManager, commit/rollback transaction hoặc xóa mọi entity khỏi persistence context.

### Trách nhiệm đóng theo chủ sở hữu

| Resource | Ai thường chịu trách nhiệm? |
|---|---|
| `Stream<T>` do Hibernate/JPA query trả về | Code nhận stream: `try-with-resources`. |
| `ScrollableResults<T>` | Code nhận cursor: `try-with-resources`. |
| Application-managed EntityManager | Code tạo EM tự đóng sau khi xong. |
| Container/Spring-managed EntityManager | Container/framework đóng theo scope. |
| Hibernate Session tự mở | Code mở Session tự đóng. |
| JDBC connection tự mở trực tiếp | Code sở hữu connection phải đóng/trả pool. |
| Transaction `begin()` | Code quản lý phải commit/rollback phù hợp. |

Nguyên tắc: **Ai tạo/nhận quyền sở hữu một Closeable resource thì phải có điểm đóng rõ ràng**, trừ khi ownership được chuyển bằng API/documentation một cách có kiểm soát.

## 12. try-with-resources là mẫu ưu tiên

Java `try-with-resources` hoạt động với `AutoCloseable`:

~~~java
try (Stream<PurchaseOrder> stream = query.getResultStream()) {
    stream.forEach(this::process);
}
~~~

Khi block kết thúc bình thường hoặc ném exception, Java gọi `stream.close()`. Tương tự với `ScrollableResults`:

~~~java
try (ScrollableResults<PurchaseOrder> results =
         query.scroll(ScrollMode.FORWARD_ONLY)) {

    while (results.next()) {
        process(results.get());
    }
}
~~~

Ưu điểm so với đóng thủ công:

- Không quên đóng khi `return` sớm.
- Không quên đóng khi exception xuất hiện.
- Dễ nhìn ra phạm vi resource còn sống.
- Java quản lý suppressed exceptions khi cả xử lý lẫn close đều lỗi.

## 13. Đóng thủ công bằng finally khi bắt buộc

Nếu API hoặc flow không thể dùng try-with-resources, cần `finally`:

~~~java
ScrollableResults<PurchaseOrder> results =
    query.scroll(ScrollMode.FORWARD_ONLY);

try {
    while (results.next()) {
        process(results.get());
    }
} finally {
    results.close();
}
~~~

Nhưng `try-with-resources` ngắn và khó sai hơn. Tránh:

~~~java
ScrollableResults<PurchaseOrder> results =
    query.scroll(ScrollMode.FORWARD_ONLY);

while (results.next()) {
    process(results.get());
}

results.close(); // Nếu process ném exception, không chạy!
~~~

Mẫu sau có nguy cơ giữ ResultSet/connection lâu cho tới khi framework/connection pool dọn dẹp, gây cạn pool khi nhiều request tương tự chạy đồng thời.

## 14. Đọc một phần kết quả cũng phải close

Không phải lúc nào ứng dụng đọc đến cuối:

~~~java
try (Stream<PurchaseOrder> stream = query.getResultStream()) {
    Optional<PurchaseOrder> firstLargeOrder =
        stream.filter(order -> isLarge(order))
              .findFirst();
}
~~~

`findFirst()` có thể dừng sớm. JDBC ResultSet và những resources liên quan vẫn cần đóng. `try-with-resources` đảm bảo close dù đọc hết hay đọc một phần.

Tương tự, với cursor:

~~~java
try (ScrollableResults<PurchaseOrder> cursor =
         query.scroll(ScrollMode.FORWARD_ONLY)) {

    while (cursor.next()) {
        PurchaseOrder order = cursor.get();
        if (isTarget(order)) {
            break;
        }
    }
}
~~~

Vòng lặp kết thúc sớm không phải sự thay thế cho `close()`.

## 15. Không trả Stream ra khỏi transaction đã kết thúc

Ví dụ Spring dễ mắc lỗi:

~~~java
@Transactional(readOnly = true)
public Stream<PurchaseOrder> loadOrders() {
    return entityManager.createQuery(
        "from PurchaseOrder o order by o.id",
        PurchaseOrder.class
    ).getResultStream();
}
~~~

Nếu caller tiêu thụ stream **sau khi method đã trả về**, transaction của method có thể đã kết thúc, connection/cursor không còn hợp lệ hoặc lifecycle bị lệch. Caller cũng có thể quên đóng stream.

### Mẫu tốt hơn: tiêu thụ bên trong transaction

~~~java
@Transactional(readOnly = true)
public void exportOrders(CsvWriter writer) {
    TypedQuery<PurchaseOrder> query = entityManager.createQuery(
        "select o from PurchaseOrder o order by o.id",
        PurchaseOrder.class
    );

    try (Stream<PurchaseOrder> stream = query.getResultStream()) {
        stream.forEach(order -> writer.write(
            order.getId(),
            order.getOrderNumber()
        ));
    }
}
~~~

Stream được mở, tiêu thụ và đóng **trước khi transaction method kết thúc**. `CsvWriter` là component minh họa; nếu nó sở hữu OutputStream/Writer, tài nguyên của nó cũng cần được đóng bởi code sở hữu tương ứng.

### Chú ý self-invocation với Spring

Nếu một method cùng class gọi trực tiếp method `@Transactional` khác trong chế độ Spring proxy thông thường, transaction interceptor có thể không được kích hoạt. Đảm bảo transaction bao phủ vòng đời thực tế bằng kiến trúc service phù hợp.

## 16. Spring Data JPA trả Stream<T>

Spring Data JPA repository có thể khai báo method truy vấn trả `Stream<T>`:

~~~java
public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select o
        from PurchaseOrder o
        where o.status = :status
        order by o.id
        """)
    Stream<PurchaseOrder> streamByStatus(
        @Param("status") OrderStatus status
    );
}
~~~

Service tiêu thụ:

~~~java
@Service
public class OrderExportService {
    private final OrderRepository repository;

    public OrderExportService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public void exportShipped(CsvWriter writer) {
        try (Stream<PurchaseOrder> stream =
                 repository.streamByStatus(OrderStatus.SHIPPED)) {

            stream.forEach(order -> writer.write(order));
        }
    }
}
~~~

Theo Spring Data JPA, các query methods trả Stream cần được đóng và thường yêu cầu transaction bao quanh việc tiêu thụ, tùy provider. Không dùng Stream ở controller sau khi service đã kết thúc transaction.

**Đừng cho rằng `@Transactional(readOnly = true)` tự khiến bộ nhớ không tăng**; EntityManager vẫn có thể quản lý các entity đã đọc và JDBC driver vẫn có thể buffer rows.

## 17. @Transactional(readOnly = true) thực sự giúp gì?

Trong Spring, `@Transactional(readOnly = true)` là một **hint/định nghĩa ngữ cảnh transaction**. Khi phối hợp với Hibernate, cấu hình Spring/Hibernate có thể điều chỉnh flush mode hoặc default read-only behavior để giảm chi phí dirty checking trong các trường hợp thích hợp.

Tuy nhiên:

- Không thay `Stream.close()`.
- Không tự tạo server-side cursor.
- Không tự giới hạn JDBC fetch size.
- Không xóa entity objects khỏi first-level cache.
- Không luôn bảo đảm database từ chối mọi câu INSERT/UPDATE/DELETE.
- Không bảo đảm một long-running read transaction là rẻ.

Nếu đọc chỉ để export và không thay đổi entity, kết hợp transaction read-only, query read-only, fetch size và chiến lược quản lý Session hợp lý.

## 18. Fetch size là gì?

`fetchSize` là một **hint** cho JDBC driver về số rows nên fetch theo đợt. Đây không phải `limit` và **không thay đổi tổng số row query trả về**.

Trong Hibernate:

~~~java
Session session = entityManager.unwrap(Session.class);

Query<PurchaseOrder> query = session.createQuery(
    "select o from PurchaseOrder o order by o.id",
    PurchaseOrder.class
);

query.setFetchSize(200);

try (Stream<PurchaseOrder> stream = query.stream()) {
    stream.forEach(this::process);
}
~~~

Khái niệm:

~~~text
Tổng kết quả: 100.000 rows

fetchSize = 200 (gợi ý)
   |
   +--> driver có thể fetch ~200 rows/đợt
   +--> application xử lý tiếp
   +--> driver fetch đợt kế
   +--> ...
~~~

`fetchSize` không phải hợp đồng rằng Java heap chỉ giữ 200 entities, cũng không phải số rows cố định của từng network fetch. Driver có thể bỏ qua hint hoặc dùng cơ chế khác.

### Fetch size khác setMaxResults

| API | Mục đích |
|---|---|
| `setFetchSize(200)` | Gợi ý cách driver lấy các rows theo đợt. |
| `setMaxResults(200)` | Giới hạn tổng số kết quả query trả ra cho application. |
| `setFirstResult(200)` | Bỏ qua một số rows đầu để phân trang theo offset. |

Để đọc **toàn bộ** tập lớn, fetch size có thể hữu ích. Để chỉ lấy **200 rows**, dùng result limit.

## 19. Fetch size theo từng JDBC driver

Không có một cấu hình streaming đúng cho mọi DB.

### PostgreSQL JDBC

Với PostgreSQL JDBC, cursor-based fetching thường cần **autocommit bị tắt / transaction còn mở**, ResultSet forward-only và fetch size dương. Nếu autocommit bật, driver có thể lấy toàn bộ kết quả thay vì fetch từng phần theo cursor.

Vì vậy:

~~~java
@Transactional(readOnly = true)
public void exportOrders() {
    Query<PurchaseOrder> query = session.createQuery(
        "select o from PurchaseOrder o order by o.id",
        PurchaseOrder.class
    );
    query.setFetchSize(500);

    try (Stream<PurchaseOrder> stream = query.stream()) {
        stream.forEach(this::process);
    }
}
~~~

Ví dụ Spring transaction phải thực sự active trong khi stream được tiêu thụ. Đừng tự gọi `setAutoCommit(false)` lên một connection do Spring/JTA quản lý; để transaction manager chịu trách nhiệm.

### MySQL Connector/J

Một số chế độ streaming/result cursor của MySQL Connector/J cần **driver properties và fetch-size configuration đặc thù**. Tùy version, chế độ cursor-based fetching có thể yêu cầu `useCursorFetch` kết hợp fetch size dương và server-side prepared statements; có cả legacy streaming behavior khác.

Không copy một magic fetch-size value cho mọi driver. Đọc tài liệu đúng phiên bản Connector/J và kiểm chứng memory/round trips thực tế.

### Oracle, SQL Server và các DB khác

Driver có cơ chế prefetch/row buffering, cursor support và fetch-size semantics khác nhau. Một số mode không thực sự dùng server cursor; một số cursor giữ transaction/lock lâu.

**Nguyên tắc:** `setFetchSize` là gợi ý; hiệu quả thực tế phải đo trên tổ hợp **Hibernate version + JDBC driver + connection settings + database + transaction mode**.

## 20. Query.setReadOnly(true) trong Hibernate

Khi chỉ đọc để xuất dữ liệu:

~~~java
Query<PurchaseOrder> query = session.createQuery(
    "select o from PurchaseOrder o order by o.id",
    PurchaseOrder.class
);

query.setReadOnly(true);
query.setFetchSize(200);
~~~

Với Hibernate, `setReadOnly(true)` yêu cầu xử lý kết quả query theo read-only entity semantics khi thích hợp, có thể giảm chi phí snapshot/dirty checking.

Nhưng cần phân biệt:

- **Query read-only** không làm một entity object biến mất khỏi persistence context.
- Nó không tự tạo transaction read-only ở DB.
- Nó không đảm bảo mọi association đã load theo cách khác cũng read-only.
- Khi entity đã nằm trong Session từ trước, trạng thái read-only và dirty checking cần xét theo entity/context cụ thể.
- Nếu code cố sửa các entity chỉ định read-only, việc cập nhật qua dirty checking có thể không xảy ra như mong đợi.

Dùng khi domain thực sự **chỉ đọc**. Không đặt read-only lên một query mà consumer cần thay đổi managed entities rồi trông chờ Hibernate tự flush.

## 21. First-level cache vẫn có thể lớn dần

Đây là bẫy quan trọng: JDBC fetch tăng dần không đồng nghĩa Hibernate Session chỉ giữ một entity.

~~~text
JDBC ResultSet: lấy từng batch
        |
        v
Hibernate hydrate entity
        |
        v
Persistence Context giữ managed entities theo identity
        |
        v
Đọc càng nhiều rows, số managed entities có thể càng tăng
~~~

Nếu stream 500.000 entities trong cùng một Session mà không quản lý persistence context, memory vẫn có thể tăng đáng kể.

Các cách tiếp cận:

1. Dùng projection/scalar/DTO thay vì entity khi không cần entity lifecycle.
2. Với vòng lặp dài, `session.clear()` định kỳ nếu an toàn.
3. `session.detach(entity)` sau khi xử lý từng entity nếu chỉ muốn giải phóng state của entity đó.
4. Dùng StatelessSession khi phù hợp yêu cầu và semantics.
5. Chia thành các trang/transactions ngắn hơn.

Cần chọn cách theo ownership, lazy loading, cache và hành vi của pipeline; không gọi clear một cách máy móc.

## 22. Ví dụ scroll và clear định kỳ

Một pattern thường dùng trong batch read:

~~~java
Session session = entityManager.unwrap(Session.class);

Query<PurchaseOrder> query = session.createQuery(
    "select o from PurchaseOrder o order by o.id",
    PurchaseOrder.class
);

query.setReadOnly(true);
query.setFetchSize(250);

int processed = 0;

try (ScrollableResults<PurchaseOrder> cursor =
         query.scroll(ScrollMode.FORWARD_ONLY)) {

    while (cursor.next()) {
        PurchaseOrder order = cursor.get();

        exportOrder(
            order.getId(),
            order.getOrderNumber(),
            order.getCreatedAt()
        );

        processed++;

        if (processed % 250 == 0) {
            session.clear();
        }
    }
}
~~~

`session.clear()` detach **tất cả** managed entities của Session và bỏ pending changes chưa flush. Mẫu này phù hợp khi Session dành riêng cho tác vụ chỉ đọc, không có entity khác cần giữ managed, và code chỉ dùng dữ liệu đã đọc trước khi clear.

### Rủi ro khi clear

- Một lazy association chưa khởi tạo có thể bị `LazyInitializationException` nếu consumer truy cập sau khi entity bị detach.
- Những thay đổi managed entities khác chưa flush sẽ bị bỏ qua.
- Tham chiếu Java tới entity vẫn tồn tại, chỉ là đã detached; hãy tránh giữ chúng trong collections lâu dài.
- Một số kiểu fetch plan/result mapping phức tạp cần kiểm tra hành vi với cursor, nhất là khi join collection.
- Không gọi clear trong Session đang dùng chung bởi luồng nghiệp vụ khác.

Nếu cần phân lập, tạo transaction/Session riêng cho export hoặc chuyển sang DTO projection.

## 23. Detach từng entity thay cho clear toàn Session

Khi muốn chỉ loại bản ghi đã xử lý:

~~~java
try (ScrollableResults<PurchaseOrder> cursor =
         query.scroll(ScrollMode.FORWARD_ONLY)) {

    while (cursor.next()) {
        PurchaseOrder order = cursor.get();

        exportOrder(order);
        session.detach(order);
    }
}
~~~

Ưu điểm: không xóa toàn bộ persistence context. Tuy nhiên, các associations đã load và entities khác có thể vẫn được quản lý, nên `detach(order)` không đảm bảo giải phóng tất cả dữ liệu liên quan. Nếu code giữ tham chiếu `order` ở nơi khác, heap vẫn có thể tăng.

Đừng detach trước khi code truy cập lazy associations cần dùng. Một cách thiết kế tốt là chỉ select những scalar fields phục vụ export, giảm nhu cầu load entity đầy đủ.

## 24. Dùng projection để giảm quản lý entity

Nếu chỉ cần ID, số đơn và ngày tạo, thay vì lấy `PurchaseOrder`:

~~~java
record OrderExportRow(
    Long id,
    String orderNumber,
    LocalDateTime createdAt
) {}

Query<OrderExportRow> query = session.createQuery(
    """
    select new com.example.reporting.OrderExportRow(
        o.id, o.orderNumber, o.createdAt
    )
    from PurchaseOrder o
    order by o.id
    """,
    OrderExportRow.class
);
~~~

Trong HQL constructor expression, class DTO phải có constructor tương ứng, và tên đầy đủ phải trỏ đến class thực tế. Record Java có canonical constructor phù hợp.

~~~java
query.setFetchSize(200);

try (Stream<OrderExportRow> stream = query.stream()) {
    stream.forEach(row -> csvWriter.write(
        row.id(),
        row.orderNumber(),
        row.createdAt()
    ));
}
~~~

DTO result không tự được quản lý như entity, nên có thể giảm chi phí persistence context/dirty checking. Tuy nhiên, JDBC buffering, Stream resources và các object tạm do consumer tạo vẫn cần quản lý.

## 25. Native SQL cũng có thể đọc bằng stream/scroll

Native query có thể dùng khi cần SQL database-specific:

~~~java
Session session = entityManager.unwrap(Session.class);

NativeQuery<Object[]> query = session.createNativeQuery(
    """
    SELECT
        o.id AS order_id,
        o.order_number AS order_number
    FROM purchase_order o
    WHERE o.created_at >= :fromTime
    ORDER BY o.id
    """,
    Object[].class
);

query.setParameter("fromTime", fromTime);
query.setFetchSize(200);

try (Stream<Object[]> stream = query.stream()) {
    stream.forEach(columns -> {
        Number id = (Number) columns[0];
        String number = (String) columns[1];
        writeCsvRow(id.longValue(), number);
    });
}
~~~

Hỗ trợ typed native result/query overload, scalar conversion và `Object[]` shape khác nhau theo Hibernate version/dialect. Trong mã production, dùng scalar mapping/DTO mapping rõ ràng nếu cần tránh cast thủ công.

Nếu query native chỉ SELECT vài scalar columns, Hibernate không cần đưa mỗi row thành managed entity, có thể phù hợp hơn cho xuất dữ liệu dài.

## 26. Đừng dùng Java Stream operations làm materialize trở lại

Một số terminal/intermediate operations yêu cầu giữ nhiều phần tử trong memory:

~~~java
try (Stream<PurchaseOrder> stream = query.stream()) {
    List<PurchaseOrder> all = stream.toList();
    // Vẫn materialize toàn bộ kết quả vào một List.
}
~~~

Tương tự, các phép:

- `sorted()` trong Java sau khi fetch.
- `distinct()` khi cần theo dõi các giá trị đã thấy.
- `collect(groupingBy(...))`.
- `collect(toList())`.
- `toArray()`.

có thể làm tăng memory đáng kể tùy dataset.

**Ưu tiên đẩy filter, ORDER BY, DISTINCT và aggregate phù hợp xuống SQL/HQL** để DB xử lý. Với export, dùng từng row để ghi ra Writer/OutputStream theo kiểu streaming thay vì gom thành một collection lớn.

## 27. Query ORDER BY rất quan trọng khi stream

Nếu mục tiêu là export theo thời gian hoặc ID:

~~~sql
select o
from PurchaseOrder o
order by o.createdAt asc, o.id asc
~~~

Không có `order by`, database không bảo đảm thứ tự rows. Khi nhiều đơn có cùng `createdAt`, thêm unique tie-breaker `id` cho kết quả ổn định hơn.

Với các tác vụ có checkpoint/resume, thứ tự xác định là điều kiện quan trọng để biết đã xử lý tới đâu. Tuy nhiên, sort có thể buộc database thực hiện sort lớn hoặc giữ state bên DB. Index phù hợp với filter/sort giúp tránh chi phí không cần thiết, cần đo execution plan.

Đừng gọi `stream.sorted(...)` nếu có thể dùng `order by` trong HQL; điều đó thường làm tiêu tốn memory ở JVM.

## 28. Stream khác pagination

| Đặc điểm | Stream/scroll dài | Phân trang |
|---|---|---|
| Thời gian giữ query resources | Có thể suốt tác vụ. | Mỗi page có query riêng ngắn hơn. |
| Transaction | Thường phải tồn tại trong khi tiêu thụ cursor. | Có thể chia thành transactions nhỏ. |
| Retry từ giữa | Cần checkpoint riêng, cursor cũ có thể mất. | Dễ dùng keyset cursor hoặc page token. |
| Memory nếu xử lý tốt | Có thể thấp. | Bị giới hạn bởi page size. |
| Tính nhất quán snapshot | Phụ thuộc transaction isolation/cursor. | Có thể khác nhau giữa các pages nếu dữ liệu thay đổi. |
| Độ phức tạp | Resource closure, driver behavior, L1 cache. | Chọn pagination strategy, stable order. |

Streaming hợp với xử lý tuyến tính không quá dài và môi trường kiểm soát được connection/transaction. Pagination hợp với tác vụ dài, retryable, hoặc hệ thống có connection pool cần bảo đảm fairness cho nhiều requests.

## 29. Offset pagination và giới hạn của nó

Đọc từng trang:

~~~java
int pageSize = 500;
int offset = 0;

while (true) {
    List<OrderExportRow> page = session.createQuery(
        """
        select new com.example.reporting.OrderExportRow(
            o.id, o.orderNumber, o.createdAt
        )
        from PurchaseOrder o
        order by o.id
        """,
        OrderExportRow.class
    )
    .setFirstResult(offset)
    .setMaxResults(pageSize)
    .getResultList();

    if (page.isEmpty()) {
        break;
    }

    page.forEach(this::exportRow);
    offset += page.size();
}
~~~

Mỗi query trả tối đa `pageSize` DTO rows, nên memory dễ giới hạn hơn nếu không giữ references. Nhưng OFFSET sâu có thể tốn chi phí bỏ qua rows. Ngoài ra, khi rows được chèn/xóa giữa các page requests, có thể có duplicate/missing rows.

## 30. Keyset pagination cho tác vụ dài

Nếu ID tăng dần, một phương án dễ checkpoint:

~~~java
long lastId = 0L;
int pageSize = 500;

while (true) {
    List<OrderExportRow> page = session.createQuery(
        """
        select new com.example.reporting.OrderExportRow(
            o.id, o.orderNumber, o.createdAt
        )
        from PurchaseOrder o
        where o.id > :lastId
        order by o.id asc
        """,
        OrderExportRow.class
    )
    .setParameter("lastId", lastId)
    .setMaxResults(pageSize)
    .getResultList();

    if (page.isEmpty()) {
        break;
    }

    for (OrderExportRow row : page) {
        exportRow(row);
        lastId = row.id();
    }

    // Có thể persist checkpoint lastId khi batch được xác nhận.
}
~~~

Keyset pagination giảm chi phí OFFSET sâu và dễ resume sau khi ứng dụng crash. Nhưng nó **không tự tạo một snapshot bất biến**: rows được insert/update/delete trong khi chạy vẫn có thể ảnh hưởng kết quả. Nếu yêu cầu một snapshot nhất quán, cần thiết kế transaction isolation, cutoff timestamp/version hoặc snapshot/export strategy phù hợp.

Nếu ID có thể âm hoặc không tăng như mong muốn, không bắt đầu mặc định bằng 0; dùng cursor nullable hoặc mốc theo domain.

## 31. Transaction kéo dài khi stream

Cursor thường cần database connection và transaction còn mở trong suốt thời gian tiêu thụ. Với export kéo dài hàng chục phút, điều này có thể:

- Giữ connection pool slot lâu.
- Giữ transaction snapshot lâu.
- Tăng áp lực database (ví dụ MVCC cleanup/vacuum trên PostgreSQL tùy isolation và active snapshots).
- Tạo nguy cơ timeout, network disconnect hoặc cursor bị hủy.
- Tăng nguy cơ lock contention nếu query có lock clause.
- Làm các requests khác chờ connection khi pool nhỏ.

Không nên cố giải quyết mọi tác vụ lớn bằng một Stream chạy hàng giờ. Nếu công việc có thể chia, dùng keyset pagination với transaction ngắn, checkpoint và retry.

### Đọc từ một snapshot

Nếu nghiệp vụ cần “danh sách đơn tại thời điểm T”, phải nêu rõ tiêu chí snapshot. Một transaction REPEATABLE READ trên DB hỗ trợ có thể cung cấp snapshot nhất quán trong transaction, nhưng giữ transaction lâu có chi phí. Một giải pháp khác là tạo snapshot/export job với cutoff/revision/bảng staging. Cân nhắc consistency, resource usage và khả năng retry, không chỉ lượng RAM.

## 32. Không dùng parallel() trên query stream

Sai hướng:

~~~java
try (Stream<PurchaseOrder> stream = query.stream()) {
    stream.parallel().forEach(this::process);
}
~~~

Hibernate `Session`/JPA `EntityManager` không thread-safe; JDBC ResultSet/cursor thông thường cũng không phù hợp để nhiều threads truy cập cùng một query stream.

Ngay cả khi Java Stream cho phép chuyển pipeline thành parallel, việc xử lý entity cùng Session trên nhiều threads có thể gây race conditions, lazy loading lỗi hoặc truy cập JDBC sai.

Nếu muốn xử lý song song:

1. Đọc dữ liệu thành **DTO bất biến, độc lập Session** theo batch vừa phải.
2. Đóng cursor/transaction hoặc tách rõ ownership.
3. Giao các DTO batches cho worker threads.
4. Mỗi worker mở transaction/EntityManager riêng khi cần truy cập DB.
5. Điều tiết concurrency/backpressure để tránh ngập CPU, memory và connection pool.

Không chia sẻ Session giữa các threads.

## 33. Tránh lazy loading không kiểm soát trong vòng lặp

Ví dụ:

~~~java
try (Stream<PurchaseOrder> stream = query.stream()) {
    stream.forEach(order -> {
        String customerName = order.getCustomer().getName();
        writeCsvRow(order.getId(), customerName);
    });
}
~~~

Nếu `customer` là LAZY, mỗi row có thể kích hoạt thêm SELECT, dẫn đến N+1 queries. Với 100.000 rows, đây có thể trở thành 100.001 SQL statements hoặc nhiều hơn.

Các lựa chọn:

- Dùng projection join trực tiếp những columns cần export.
- Dùng entity graph/batch fetching nếu phù hợp và đã kiểm tra.
- Với to-one association, cân nhắc join fetch trong query khi không làm tăng cardinality.
- Đối với collection fetch joins, **tránh kết hợp bừa với stream/scroll** vì result rows nhân bản, hydration/collection assembly phức tạp và có thể có giới hạn theo Hibernate version.

Ví dụ DTO join:

~~~java
record OrderCustomerRow(Long id, String customerName) {}

Query<OrderCustomerRow> query = session.createQuery(
    """
    select new com.example.reporting.OrderCustomerRow(
        o.id, c.name
    )
    from PurchaseOrder o
    join o.customer c
    order by o.id
    """,
    OrderCustomerRow.class
);
~~~

Giữ projection tập trung vào dữ liệu cần xử lý, không kích hoạt lazy loading sau khi entity đã bị detach.

## 34. Vì sao collection fetch join không hợp với stream/scroll?

Giả sử đơn hàng có nhiều dòng chi tiết:

~~~sql
select distinct o
from PurchaseOrder o
join fetch o.lines
order by o.id
~~~

Ở mức SQL, mỗi `PurchaseOrder` có thể xuất hiện nhiều rows, tương ứng với từng `OrderLine`. Hibernate phải tổng hợp rows thành collections, xử lý identity/deduplication và đảm bảo một parent collection được hoàn chỉnh.

Một cursor forward-only theo từng row **không** tự tương đương một luồng entity parent đã được hydrate hoàn chỉnh với tất cả child rows. Hibernate có thể không hỗ trợ hoặc cảnh báo các tổ hợp stream/scroll với collection fetch join; các phiên bản mới hơn có thể hạn chế thêm.

Hướng an toàn hơn cho export:

- Query trực tiếp flat DTO rows (`orderId`, `lineId`, `sku`...) rồi nhóm theo thứ tự trong consumer với bộ nhớ giới hạn.
- Dùng keyset pagination trên IDs của parent rồi query children theo batch.
- Tránh giữ toàn bộ parent + collection graph cho hàng trăm nghìn parent.

## 35. Xử lý ngoại lệ khi đang đọc

Dòng thứ 10.000 có thể làm consumer ném exception:

~~~java
try (Stream<PurchaseOrder> stream = query.stream()) {
    stream.forEach(order -> {
        if (invalid(order)) {
            throw new IllegalStateException("Invalid order " + order.getId());
        }
        exportOrder(order);
    });
}
~~~

`try-with-resources` vẫn gọi `stream.close()` khi exception được ném. Nhưng các câu hỏi nghiệp vụ khác vẫn tồn tại:

- Transaction có bị rollback không? Tùy transaction manager, exception type và cấu hình rollback.
- CSV/file/output bên ngoài DB đã ghi một phần có cần xóa không?
- Có thể retry từ row nào để tránh duplicate không?
- Có cần đóng Writer/OutputStream không?
- Nếu JDBC driver bị ngắt kết nối, Session còn dùng tiếp được không?

Đừng tiếp tục dùng Session sau một exception JDBC/Hibernate nghiêm trọng mà chưa xử lý transaction/Session lifecycle theo hướng dẫn provider. Thường cần rollback rồi kết thúc unit of work.

## 36. Đóng stream không đồng nghĩa rollback/commit

Ví dụ application-managed transaction:

~~~java
EntityManager em = entityManagerFactory.createEntityManager();

try {
    em.getTransaction().begin();

    TypedQuery<PurchaseOrder> query = em.createQuery(
        "select o from PurchaseOrder o order by o.id",
        PurchaseOrder.class
    );

    try (Stream<PurchaseOrder> stream = query.getResultStream()) {
        stream.forEach(this::exportOrder);
    }

    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Ở ví dụ này:

- Inner try đóng Stream.
- `commit()/rollback()` giải quyết transaction.
- `em.close()` giải quyết application-managed EntityManager.

Nếu Stream close gây exception, catch/finally vẫn thực hiện cleanup. Code thực tế cần xử lý exception hơn nữa khi rollback/close thất bại, nhưng **ownership giữa ba tài nguyên là riêng biệt**.

Với container-managed/Spring-managed EntityManager, không tự gọi `em.close()`; để framework đóng đúng scope.

## 37. Đóng tài nguyên theo thứ tự ngược khi tự mở Session

Nếu tự tạo Hibernate Session và transaction:

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    try {
        Query<PurchaseOrder> query = session.createQuery(
            "select o from PurchaseOrder o order by o.id",
            PurchaseOrder.class
        );
        query.setFetchSize(200);
        query.setReadOnly(true);

        try (ScrollableResults<PurchaseOrder> cursor =
                 query.scroll(ScrollMode.FORWARD_ONLY)) {

            while (cursor.next()) {
                exportOrder(cursor.get());
            }
        }

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.getStatus().canRollback()) {
            tx.rollback();
        }
        throw ex;
    }
}
~~~

Mẫu minh họa transaction phải bao phủ thời gian cursor được đọc, cursor được đóng trước commit, Session được đóng sau cùng. API kiểm tra transaction status có thể khác theo Hibernate version; trong production cần dùng phương thức/status enum phù hợp với phiên bản đã chọn.

Không giữ Session mở ngoài try block nếu không có chủ sở hữu chịu trách nhiệm đóng.

## 38. Cách đóng Stream trong REST export

Giả sử Controller trả một streaming HTTP response. Với một số framework, callback ghi response có thể chạy **sau khi transaction của controller/service đã kết thúc**.

Dễ sai:

~~~java
@Transactional(readOnly = true)
public Stream<PurchaseOrder> getOrdersForResponse() {
    return repository.streamByStatus(OrderStatus.SHIPPED);
}
~~~

Nếu trả Stream trực tiếp, có nguy cơ cursor sống lâu hơn transaction.

Một thiết kế an toàn hơn:

- Tạo transaction trong **thời điểm callback thực sự chạy** nếu framework hỗ trợ và bạn kiểm soát được lifecycle.
- Hoặc dùng service export theo batches, mỗi batch có transaction ngắn, ghi ra response writer theo backpressure.
- Đảm bảo Stream/cursor đóng ở cùng callback với nơi mở.
- Dừng đọc và đóng resources khi client ngắt kết nối; không giữ connection chờ output chậm vô thời hạn.

Ví dụ pseudocode Spring:

~~~java
StreamingResponseBody body = outputStream -> {
    // Gọi service tự quản lý transaction và stream bên trong callback.
    exportService.writeCsvTo(outputStream);
};
~~~

Đảm bảo `exportService.writeCsvTo()` là method có transaction active trong lúc tiêu thụ query; các proxy/call paths của Spring phải được cấu hình đúng. Đừng viết JDBC stream trong controller method rồi trả về sau khi transaction đã đóng.

## 39. Backpressure: consumer chậm kéo dài connection

Dù Hibernate lấy rows hiệu quả, nếu consumer làm việc chậm:

~~~java
stream.forEach(order -> {
    remoteApi.send(order);  // Có thể mất vài trăm ms mỗi row.
});
~~~

thì connection/cursor DB có thể bị giữ trong lúc chờ network. Điều này dễ cạn pool khi nhiều tasks chạy đồng thời.

Các giải pháp:

1. Tách **đọc DB theo batch** khỏi việc gọi remote API.
2. Chuyển DTO batch vào queue có giới hạn kích thước (bounded queue).
3. Đóng DB cursor/transaction trước khi thực hiện công việc tốn thời gian nếu có thể.
4. Dùng outbox hoặc job queue khi cần bảo đảm delivery.
5. Tạo checkpoint để retry thay vì giữ transaction mở hàng giờ.

Không dùng unbounded queue để “cứu” việc giữ cursor: nó có thể chuyển vấn đề sang out-of-memory ở JVM.

## 40. JDBC timeouts và hủy giữa chừng

Dữ liệu lớn dễ bị ảnh hưởng bởi:

- Statement/query timeout.
- Network/socket timeout.
- Transaction timeout.
- Connection pool lifetime/idle timeout.
- DB server cursor timeout và session termination.
- Client cancellation.

Hibernate Query có API cấu hình query timeout trong những phiên bản phù hợp, hoặc có thể dùng JPA query hint tùy provider:

~~~java
query.setTimeout(60); // Hibernate Query API: đơn vị thường là giây.
~~~

Không được nhầm với `jakarta.persistence.query.timeout`, thường được định nghĩa theo **mili-giây** trong JPA hints; hiệu lực phụ thuộc provider/driver/database.

Khi timeout hoặc cancel, `try-with-resources` vẫn cần bảo đảm đóng cursor/Stream. Transaction có thể phải rollback. Không mặc định stream đang mở có thể tiếp tục sử dụng sau JDBC exception.

## 41. Stream và quản lý connection pool

Một application có pool 10 JDBC connections. Nếu 10 concurrent exports, mỗi export giữ connection 20 phút, các requests khác có thể phải chờ dù CPU còn rảnh.

Để tránh:

- Giới hạn số concurrent streaming jobs.
- Đặt giới hạn tổng thời gian job/connection và theo dõi.
- Dùng pagination nếu mỗi job lâu.
- Dùng dedicated worker pool/datasource hoặc scheduling phù hợp.
- Chuyển report lớn sang background job có quản lý queue khi sản phẩm yêu cầu.
- Quan sát connection acquisition time, active/idle pool metrics, DB active sessions và cursor count.

Streaming tiết kiệm heap có thể **đánh đổi bằng thời gian chiếm connection**. Phải tối ưu cả ứng dụng lẫn DB, không chỉ một tài nguyên.

## 42. Đếm số row và hiển thị tiến độ

Khi cần progress bar, không nên bắt Stream materialize chỉ để đếm:

~~~java
long count = query.getResultStream().count();
~~~

`count()` là terminal operation và sẽ tiêu thụ Stream; phải đóng Stream, đồng thời làm DB/JDBC/ORM phải đọc kết quả thay vì tận dụng `COUNT(*)`.

Nếu cần tổng số bản ghi, chạy aggregate query riêng:

~~~java
Long total = entityManager.createQuery(
    """
    select count(o)
    from PurchaseOrder o
    where o.status = :status
    """,
    Long.class
)
.setParameter("status", OrderStatus.SHIPPED)
.getSingleResult();
~~~

Sau đó Stream query dùng cùng predicate để xử lý rows. Lưu ý tổng COUNT và số rows export có thể khác nếu dữ liệu thay đổi giữa hai truy vấn; điều đó phụ thuộc isolation/snapshot.

Cập nhật tiến độ theo batch thay vì log từng row:

~~~java
long processed = 0;
try (ScrollableResults<PurchaseOrder> cursor =
         query.scroll(ScrollMode.FORWARD_ONLY)) {
    while (cursor.next()) {
        exportOrder(cursor.get());
        processed++;
        if (processed % 1000 == 0) {
            reportProgress(processed);
        }
    }
}
~~~

## 43. Đọc hết dữ liệu có nghĩa mọi row đều được xử lý đúng?

Không hẳn. Khi xuất dữ liệu hoặc đồng bộ:

- Một row có thể được đọc nhưng ghi file/remote API thất bại.
- Consumer có thể gặp exception sau khi đã tạo partial output.
- App crash sau row N nhưng trước khi ghi checkpoint.
- Retry có thể đọc lại rows đã gửi trước.
- Concurrent changes có thể làm snapshot khác giữa lần retry.

Do đó, Stream/ScrollableResults **chỉ giải quyết cơ chế đọc kết quả**, không tự cung cấp exactly-once processing, transactional outbox hay resumable export.

Với tác vụ cần retry, dùng idempotent writes, checkpoint theo unique key, batch boundaries rõ và kiểm tra transaction của từng bước.

## 44. Quy trình quyết định: stream, scroll hay pagination?

~~~mermaid
flowchart TD
    A["Cần đọc nhiều kết quả"] --> B{"Tập nhỏ, RAM đủ?"}
    B -- "Có" --> C["getResultList()"]
    B -- "Không" --> D{"Cần checkpoint/retry, job rất dài?"}
    D -- "Có" --> E["Keyset pagination + batches"]
    D -- "Không" --> F{"Cần điều khiển cursor rõ ràng?"}
    F -- "Có" --> G["ScrollableResults + FORWARD_ONLY"]
    F -- "Không" --> H["Query Stream"]
    G --> I["Transaction + fetchSize + readOnly"]
    H --> I
    I --> J["try-with-resources"]
    J --> K["Chọn DTO / clear / detach khi cần"]
    K --> L["Đo memory, connection, DB cursor"]
~~~

Chọn theo **độ dài tác vụ, khả năng retry, thời gian giữ transaction, bộ nhớ, tính nhất quán và nhu cầu điều khiển cursor**.

## 45. Ví dụ hoàn chỉnh: HQL Stream xuất CSV bằng DTO

Giả sử đã khai báo:

~~~java
package com.example.reporting;

public record OrderCsvRow(
    Long id,
    String orderNumber,
    LocalDateTime createdAt,
    OrderStatus status
) {}
~~~

Ví dụ service Spring:

~~~java
@Service
public class OrderCsvExportService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public void exportSince(LocalDateTime from, Writer target) {
        Session session = entityManager.unwrap(Session.class);

        Query<OrderCsvRow> query = session.createQuery(
            """
            select new com.example.reporting.OrderCsvRow(
                o.id, o.orderNumber, o.createdAt, o.status
            )
            from PurchaseOrder o
            where o.createdAt >= :from
            order by o.id asc
            """,
            OrderCsvRow.class
        );

        query.setParameter("from", from);
        query.setFetchSize(250);
        query.setReadOnly(true);

        try (Stream<OrderCsvRow> stream = query.stream()) {
            stream.forEach(row -> writeCsvRow(target, row));
        }

        // Writer do caller sở hữu nên không tự đóng ở đây.
    }

    private void writeCsvRow(Writer target, OrderCsvRow row) {
        try {
            target.write(row.id().toString());
            target.write(',');
            target.write(escapeCsv(row.orderNumber()));
            target.write(',');
            target.write(row.createdAt().toString());
            target.write(',');
            target.write(row.status().name());
            target.write('\n');
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }

    private String escapeCsv(String value) {
        String escaped = value.replace("\"", "\"\"");
        return "\"" + escaped + "\"";
    }
}
~~~

Mẫu minh họa:

- DTO projection tránh hydrate managed entity đầy đủ.
- `setFetchSize(250)` chỉ là hint cho JDBC driver.
- Stream được mở/đọc/đóng trong transaction.
- Writer là resource do caller sở hữu; service không đóng Writer.
- Escape dấu nháy trong CSV giúp giữ field chứa dấu phẩy, quote, xuống dòng đúng định dạng CSV theo quy ước phổ biến.

**Lưu ý CSV injection:** Nếu dữ liệu CSV lấy từ user input và được mở bằng spreadsheet software, các cell bắt đầu bằng công thức (`=`, `+`, `-`, `@`) có thể bị ứng dụng bảng tính diễn giải. CSV escaping không tự chống formula injection; cần chính sách encode/sanitize riêng nếu export cho Excel/Sheets và dữ liệu không đáng tin cậy.

## 46. Ví dụ hoàn chỉnh: scroll và quản lý entity context

~~~java
@Service
public class OrderAuditService {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public long auditAll(Long minId) {
        Session session = entityManager.unwrap(Session.class);

        Query<PurchaseOrder> query = session.createQuery(
            """
            select o
            from PurchaseOrder o
            where o.id >= :minId
            order by o.id asc
            """,
            PurchaseOrder.class
        );

        query.setParameter("minId", minId);
        query.setReadOnly(true);
        query.setFetchSize(200);

        long total = 0;

        try (ScrollableResults<PurchaseOrder> cursor =
                 query.scroll(ScrollMode.FORWARD_ONLY)) {

            while (cursor.next()) {
                PurchaseOrder order = cursor.get();

                checkInvariant(order);
                total++;

                if (total % 200 == 0) {
                    session.clear();
                }
            }
        }

        return total;
    }

    private void checkInvariant(PurchaseOrder order) {
        // Chỉ đọc các thuộc tính scalar đã hydrate.
    }
}
~~~

Mẫu này giả định transaction/Session dùng riêng cho audit và không có pending changes cần giữ. `session.clear()` trong một persistence context chung với thao tác khác có thể gây mất thay đổi chưa flush; khi đó cần tách Session, dùng projection hoặc detach phù hợp.

Nếu audit kéo dài quá lâu, chuyển sang keyset pagination và transaction theo batch thay vì giữ một cursor duy nhất.

## 47. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Connection pool cạn dần | Stream/ScrollableResults không đóng; export giữ connection quá lâu. | `try-with-resources`; giới hạn concurrency; pagination. |
| `LazyInitializationException` | Stream được tiêu thụ sau khi Session/transaction đã đóng, hoặc entity đã detach. | Tiêu thụ trong scope hợp lệ; dùng DTO cho dữ liệu cần. |
| RAM vẫn tăng dù dùng stream | Driver buffer rows hoặc Hibernate first-level cache giữ entities. | Fetch size/driver config; DTO; detach/clear; chia trang. |
| `OutOfMemoryError` khi `collect(toList())` | Materialize toàn bộ Stream. | Xử lý từng row, không gom tất cả. |
| Query chậm bất thường | N+1 lazy loading hoặc sort lớn/thiếu index. | Projection, query plan, index, tránh collection fetch join. |
| Kết quả khác giữa các lần đọc | Không có ORDER BY ổn định hoặc dữ liệu thay đổi. | Tie-breaker và snapshot/checkpoint phù hợp. |
| JDBC cursor đóng bất ngờ | Transaction kết thúc trước consumer. | Giữ transaction active trong khi đọc. |
| `setFetchSize()` không giảm memory | Driver bỏ qua hint, autocommit/config không phù hợp. | Xem tài liệu đúng JDBC driver và đo thực tế. |
| `clear()` làm mất thay đổi | Session có pending dirty entities chưa flush. | Không clear Session có writes cần giữ; tách read-only Session. |
| Process row thất bại làm connection giữ lâu | Close không nằm trong finally/try-with-resources. | Đóng resource trong mọi exit paths. |
| Stream `parallel()` lỗi ngẫu nhiên | Session/ResultSet không thread-safe. | Duyệt tuần tự; parallelize detached DTO batches. |
| Báo cáo chạy hàng giờ | Cursor/transaction sống quá lâu, consumer chậm. | Keyset pagination + checkpoint; không gọi remote API trong cursor. |

## 48. Debug và đo hiệu năng

Không chỉ nhìn vào việc dùng Stream hay ScrollableResults; hãy đo:

- Peak heap / retained memory và số managed entity entries.
- Tổng rows đã tiêu thụ.
- Thời gian mở transaction và thời gian giữ JDBC connection.
- Connection pool active/idle/wait metrics.
- Số round trips/fetch batches nếu driver/DB cung cấp.
- Query execution plan, index và sort cost.
- Số SQL statements phát sinh do lazy loading.
- Thời gian consumer xử lý từng batch.
- Số ResultSet/cursor còn mở trong DB (nếu DB có công cụ quan sát).
- Tỷ lệ timeout/cancellation và retry.

Hibernate có SQL logging và statistics; cấu hình tên logger tùy phiên bản. Với Hibernate 6/Spring Boot:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Bind logging có thể chứa dữ liệu nhạy cảm; chỉ bật có kiểm soát. SQL log không cho biết chắc toàn bộ JDBC driver đã buffer bao nhiêu rows; cần dùng profiler, JDBC metrics và database monitoring khi kiểm chứng streaming thực sự.

## 49. Kiểm thử trách nhiệm đóng tài nguyên

Một số kịch bản integration test quan trọng:

1. Đọc toàn bộ Stream trong try-with-resources và xác nhận kết quả.
2. Gọi `findFirst()` hoặc `break` sớm, đảm bảo scope close được thực thi.
3. Consumer ném exception giữa chừng và kiểm tra không leak connections.
4. Đọc khi transaction active và thử tình huống ngoài transaction theo cấu hình driver.
5. Thử `setFetchSize` với DB production-like.
6. Xác định memory khi đọc 10.000, 100.000, 1.000.000 rows (dùng dữ liệu giả lập phù hợp).
7. So sánh entity streaming, DTO streaming và pagination.
8. Kiểm tra `clear()/detach()` không làm mất pending writes.
9. Kiểm tra lazy association và collection fetch join.
10. Chạy concurrent exports với connection pool hạn chế để quan sát blocking.

**Dùng database giống production** khi kết quả phụ thuộc cursor behavior. H2 in-memory không nhất thiết phản ánh PostgreSQL/MySQL/Oracle JDBC fetching và transaction requirements.

## 50. Bài tập thực hành

### Bài 1 — So sánh getResultList và getResultStream

Viết hai phiên bản cùng một query lấy đơn theo ID. Một phiên bản dùng `getResultList()`, một phiên bản dùng `getResultStream()` với try-with-resources. Chạy trên dataset lớn và quan sát memory. Đừng chỉ suy luận từ API name.

### Bài 2 — ScrollableResults FORWARD_ONLY

Dùng `query.scroll(ScrollMode.FORWARD_ONLY)`. Đếm số rows đã đọc và đóng cursor bằng try-with-resources. Thử thoát sớm khi gặp một ID mục tiêu.

### Bài 3 — Transaction scope

Trong Spring, viết một service method `@Transactional(readOnly=true)` tiêu thụ Stream bên trong method. Sau đó thử cách trả Stream ra ngoài service và giải thích nguy cơ connection/transaction bị đóng sớm.

### Bài 4 — Fetch size trên driver thật

Dùng PostgreSQL JDBC hoặc driver mục tiêu. So sánh `fetchSize=0`, 100 và 1000 (trong transaction phù hợp), đo peak memory/network/resource usage. Ghi nhận rằng driver có thể không tuân fetch size như giới hạn cứng.

### Bài 5 — First-level cache

Query một tập entity lớn qua cursor, đo memory. Sau đó dùng `setReadOnly(true)` và `session.clear()` theo batch trong Session chỉ đọc; quan sát sự khác biệt. Giải thích rủi ro của clear khi Session có pending changes.

### Bài 6 — DTO projection

Thay entity result bằng record DTO chỉ chứa ID, order number và createdAt. Stream DTO ra CSV. Giải thích tại sao cách này có thể giảm chi phí persistence context.

### Bài 7 — Lazy association

Trong consumer, truy cập một lazy association. Bật SQL logging để phát hiện N+1. Thay bằng projection JOIN phù hợp và so sánh số SQL statements.

### Bài 8 — Stream vs keyset pagination

Thiết kế tác vụ export 3 triệu rows có thể retry và resume từ checkpoint. Giải thích vì sao pagination có thể tốt hơn giữ transaction/cursor mở hàng giờ.

### Bài 9 — Exception và cleanup

Cho consumer ném exception tại row thứ 25. Xác nhận try-with-resources đóng cursor/Stream; phân biệt cleanup JDBC, rollback transaction và cleanup output file.

### Bài 10 — Concurrency

Chạy nhiều exports đồng thời với pool nhỏ và quan sát connection acquisition wait. Đề xuất giới hạn concurrent jobs và chia batch.

## 51. Checklist trước khi dùng Stream hoặc ScrollableResults

**Về API**

- [ ] Dùng `getResultStream()/stream()` hoặc `scroll()` thật, không phải `getResultList().stream()` nếu mục tiêu là tránh materialize list.
- [ ] Đã xác định JPA portable API hay Hibernate-specific API.
- [ ] Stream/cursor có một scope `try-with-resources` rõ ràng.
- [ ] Không trả Stream cho caller ngoài transaction/lifecycle mà không quản lý ownership.

**Về JDBC/transaction**

- [ ] Transaction còn active trong quá trình đọc nếu driver/cursor yêu cầu.
- [ ] Biết driver có thực sự fetch tăng dần hay không.
- [ ] Fetch size được cấu hình và đo; không nhầm với `setMaxResults()`.
- [ ] Không giữ connection lâu vì consumer gọi network chậm.
- [ ] Có timeout/cancellation và cleanup path.

**Về memory/lifecycle**

- [ ] Chỉ select fields cần thiết; cân nhắc DTO projection.
- [ ] Entity read-only behavior được định nghĩa rõ.
- [ ] First-level cache không tăng vô hạn hoặc đã có chiến lược clear/detach an toàn.
- [ ] Không tích lũy kết quả bằng `toList()`, `groupingBy()` nếu muốn streaming.
- [ ] Không dùng `parallel()` với một Session/cursor.
- [ ] Không tạo N+1 qua lazy associations.
- [ ] Không kết hợp tùy tiện scroll/stream với collection fetch join.

**Về tính đúng đắn**

- [ ] Có ORDER BY ổn định khi thứ tự quan trọng.
- [ ] Có checkpoint/retry nếu tác vụ dài và có thể bị gián đoạn.
- [ ] Hiểu isolation/snapshot semantics nếu dữ liệu thay đổi trong lúc đọc.
- [ ] Resource owner rõ: Stream, cursor, EM/Session, transaction và output Writer.
- [ ] Integration test trên database + driver tương ứng production.

## 52. Câu hỏi thường gặp

**1. Stream có tự động đóng khi forEach() đọc hết không?**  
Không nên dựa vào điều đó. Java Stream terminal operation không cam kết gọi `close()`. Với Hibernate/JPA query stream có thể giữ JDBC resources, vì vậy dùng `try-with-resources` ngay cả khi đọc đến cuối.

**2. `stream.limit(100)` có giống SQL LIMIT 100 không?**  
Không. `limit(100)` là Java Stream operation; Hibernate/DB có thể đã thực thi query và mở cursor cho tập lớn. Nếu chỉ cần 100 rows, dùng `query.setMaxResults(100)` hoặc SQL LIMIT/OFFSET thích hợp.

**3. `fetchSize=500` nghĩa là Hibernate chỉ giữ 500 entities?**  
Không. Fetch size là JDBC hint; first-level cache vẫn có thể giữ các entity đã hydrate. Dùng DTO, read-only, detach/clear hoặc chia trang theo nhu cầu.

**4. Đã có `@Transactional(readOnly=true)` có cần đóng Stream không?**  
Có. Transaction boundary và Stream.close là hai trách nhiệm khác nhau. Chỉ vì transaction manager sẽ dọn tài nguyên cuối scope không có nghĩa nên giữ ResultSet mở đến lúc đó.

**5. Có thể trả Stream từ Spring Data Repository không?**  
Có, nếu repository/provider hỗ trợ, nhưng caller phải đóng Stream và tiêu thụ trong transaction/context còn hiệu lực. Đừng trả nó ra khỏi service transaction rồi tiêu thụ ở controller bất kỳ.

**6. Có thể song song hóa với `parallel()` không?**  
Không nên với stream gắn với Hibernate Session/JDBC ResultSet. Session không thread-safe. Hãy tách các DTO batches độc lập và mỗi worker dùng transaction/Session riêng.

**7. Có nên luôn dùng scroll thay stream?**  
Không. Stream thường dễ dùng khi chỉ duyệt tuần tự; ScrollableResults tiện cho vòng lặp/cursor control. Cả hai cần quản lý tài nguyên. Nếu tác vụ kéo dài và cần retry, pagination có thể phù hợp hơn.

**8. Vì sao vẫn OOM khi dùng ScrollableResults?**  
Có thể driver đã buffer kết quả, first-level cache giữ entity objects, consumer tích lũy references hoặc query fetch association quá lớn. Cần đo từng lớp thay vì mặc định lỗi do ScrollableResults.

**9. Đóng Stream có commit transaction không?**  
Không. Đóng query result resources và commit/rollback transaction là hai hành động riêng. Với application-managed transaction phải commit/rollback tường minh; với Spring/JTA framework quản lý transaction theo scope.

**10. Nếu client hủy tải CSV thì sao?**  
Code xuất dữ liệu phải dừng consumer, đóng Stream/cursor và xử lý transaction/output resources. Trong mô hình HTTP streaming, callback chạy khi nào và ai sở hữu transaction cần được thiết kế tường minh.

## 53. Tổng kết

~~~mermaid
flowchart TD
    A["Query nhiều rows"] --> B{"Có thể phân trang/retry?"}
    B -- "Job dài, cần checkpoint" --> C["Keyset pagination theo batch"]
    B -- "Cần duyệt cursor liên tục" --> D{"API nào?"}
    D -- "Java pipeline" --> E["Stream<T>"]
    D -- "Cursor control" --> F["ScrollableResults<T>"]
    E --> G["Transaction / EntityManager còn hiệu lực"]
    F --> G
    G --> H["Fetch size + driver configuration"]
    H --> I["DTO hoặc read-only + L1 cache strategy"]
    I --> J["Xử lý tuần tự, không parallel"]
    J --> K["try-with-resources: close"]
    K --> L["Commit/rollback + đóng Session nếu sở hữu"]
~~~

**Stream và ScrollableResults không chỉ là hai cú pháp duyệt dữ liệu**. Chúng là lựa chọn về **lifecycle của JDBC results, thời gian giữ transaction/connection và quản lý memory của persistence context**.

Mẫu an toàn nên nhớ:

~~~java
try (Stream<MyRow> stream = query.getResultStream()) {
    stream.forEach(this::processOneRow);
}
~~~

hoặc:

~~~java
try (ScrollableResults<MyRow> cursor =
         query.scroll(ScrollMode.FORWARD_ONLY)) {
    while (cursor.next()) {
        processOneRow(cursor.get());
    }
}
~~~

Đóng resource tường minh, tiêu thụ trong phạm vi transaction/session phù hợp, cấu hình fetch size theo driver thực tế và không tích lũy toàn bộ kết quả trong memory. Khi tác vụ quá dài hoặc cần retry, hãy cân nhắc keyset pagination để giảm thời gian giữ connection và xây dựng tiến trình có thể phục hồi.
