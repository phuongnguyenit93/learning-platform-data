# Kiểm soát kích thước Persistence Context trong tác vụ dài

Một tác vụ import một triệu sản phẩm có thể chỉ cần vài trăm MB nếu xử lý từng lô nhỏ. Nhưng nếu dùng một Hibernate `Session` để `persist()` tất cả entity rồi mới commit, bộ nhớ có thể tăng liên tục dù mỗi câu SQL đều chạy nhanh. Nguyên nhân thường không chỉ là danh sách đầu vào: **Persistence Context giữ các entity đang managed, thông tin phục vụ dirty checking, collection state và những tham chiếu liên quan trong suốt vòng đời Session**.

Cách xử lý phổ biến với Stateful Session là **flush theo lô rồi clear Persistence Context**, đồng thời kiểm soát nguồn dữ liệu và transaction boundaries. Tuy nhiên, `flush()` và `clear()` giải quyết hai việc khác nhau; chia batch JDBC cũng không tự giới hạn số entity managed; và commit theo lô là một quyết định về atomicity chứ không chỉ về hiệu năng.

Ví dụ nền tảng:

~~~java
int batchSize = 50;
int processed = 0;

try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        for (Product product : readProductsLazily()) {
            session.persist(product);
            processed++;

            if (processed % batchSize == 0) {
                session.flush();
                session.clear();
            }
        }

        session.flush();
        session.clear();
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
~~~

Ví dụ này minh họa một transaction cho toàn bộ công việc, nhưng Persistence Context được giải phóng theo từng lô. Nếu dữ liệu rất lớn, thời gian transaction và lock lifetime vẫn có thể dài; phần sau sẽ phân biệt cách chia **flush/clear batches** với **transaction chunks**.

> **Phạm vi:** Java 17+, Hibernate ORM 6.x, Jakarta Persistence, JDBC và Spring/Spring Batch là bối cảnh minh họa. Một số API và hành vi phụ thuộc Hibernate/Spring Batch version, ID generator, JDBC driver và DBMS. `Session` là API Hibernate stateful; `EntityManager` có các thao tác tương đương như `flush()` và `clear()`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao Persistence Context tăng bộ nhớ trong batch jobs.
2. Phân biệt managed entities, first-level cache, snapshots, collection state và JDBC statement batching.
3. Sử dụng `flush()` và `clear()` theo đúng thứ tự để giới hạn số entity được theo dõi.
4. Chọn batch size và đo ảnh hưởng đến heap, GC, SQL throughput và database.
5. Phân biệt batch size của ORM, JDBC batch size và transaction chunk size.
6. Thiết kế transaction boundaries ngắn, có retry/checkpoint phù hợp.
7. Chọn streaming, keyset pagination, scroll/cursor hoặc Spring Batch cho nguồn dữ liệu lớn.
8. Nhận diện các vấn đề do cascade, associations, detached entities, optimistic locking và generated IDs.
9. Biết khi nào cân nhắc `StatelessSession`, bulk DML hoặc JDBC trực tiếp.
10. Kiểm thử và vận hành tác vụ dài mà không giữ một Persistence Context phình to.

## 2. Persistence Context là gì?

Trong Hibernate, Persistence Context là vùng quản lý các entity instances đang được gắn với một `Session`. Trong JPA, nó là môi trường quản lý entity của `EntityManager`.

Nó đảm nhiệm nhiều chức năng:

- **Identity map:** Một entity key trong cùng context thường có một managed instance đại diện.
- **First-level cache:** Các lần load cùng identity có thể trả object đã quản lý mà không cần SELECT lại.
- **Dirty checking:** Theo dõi state để nhận ra thuộc tính nào thay đổi.
- **Loaded-state snapshots:** Lưu state tham chiếu để so sánh khi flush, tùy entity/mapping/provider.
- **Collection tracking:** Theo dõi các collection được quản lý và thay đổi của chúng.
- **Action queue:** Tập hợp các thao tác INSERT/UPDATE/DELETE/collection actions chờ thực thi khi flush.
- **Association management:** Theo dõi entity relationships, proxies và trạng thái managed/detached.

Đây là nền tảng giúp Hibernate cung cấp unit-of-work semantics. Nhưng một Persistence Context có hàng trăm nghìn entities sẽ có chi phí đáng kể.

## 3. Vì sao bộ nhớ tăng?

Giả sử một job đọc CSV một triệu dòng rồi gọi `persist()`:

~~~java
@Transactional
public void importAll(List<Product> products) {
    for (Product product : products) {
        entityManager.persist(product);
    }
}
~~~

Bộ nhớ có thể chứa đồng thời:

1. `List<Product>` đầu vào và toàn bộ strings/objects của parser.
2. Một triệu managed entities trong Persistence Context.
3. Loaded-state/snapshot data cho dirty checking khi áp dụng.
4. Entity entries, keys và association references.
5. Collection wrappers/snapshots nếu entity có collections.
6. Pending actions và metadata phục vụ flush.
7. JDBC statements/buffers và kết quả truy vấn.
8. Các object ứng dụng khác vẫn giữ references đến entities.

Ngay cả khi Hibernate đã gửi một phần SQL trong quá trình flush, **managed entities vẫn có thể nằm trong Persistence Context**. Flush không đồng nghĩa xóa chúng khỏi bộ nhớ.

## 4. Persistence Context tăng theo số managed entities

Mô hình khái niệm:

~~~text
Session / EntityManager
    |
    +-- Entity key A -> Product A + tracking state
    +-- Entity key B -> Product B + tracking state
    +-- Entity key C -> Product C + tracking state
    +-- ...
    +-- Entity key N -> Product N + tracking state
    |
    +-- Collection entries / snapshots
    +-- Pending actions / metadata
~~~

Nếu job chỉ gọi `persist()` liên tục mà không detach/clear, số managed entities thường tăng theo tổng số records đã xử lý.

Một triệu entities không chỉ là một triệu object Java đơn giản. Entity mapping, strings, BigDecimal, relationships, snapshots và collection state có thể làm footprint lớn hơn đáng kể.

Không thể đưa ra một hệ số RAM chung: nó phụ thuộc kích thước entity, số fields, collections, JVM, Hibernate version và graph được load.

## 5. First-level cache khác second-level cache

| Thành phần | Phạm vi | Vai trò |
|---|---|---|
| Persistence Context / L1 | Một Session/EntityManager | Managed state, identity map, dirty checking |
| Second-level cache / L2 | Chia sẻ giữa Sessions theo cấu hình | Cache entity/collection data |
| Query cache | Theo cấu hình SessionFactory/provider | Cache query result/identifiers |
| JDBC driver buffers | Statement/ResultSet/connection | Truyền và nhận dữ liệu SQL |
| Application heap | Toàn process | Lists, DTOs, queues, references |

`clear()` xóa trạng thái managed khỏi **Persistence Context hiện tại**. Nó không có nghĩa xóa L2 cache, giải phóng mọi object mà application còn giữ hoặc thu hồi ngay toàn bộ heap.

Tương tự, tắt L2 cache không giải quyết việc một Session giữ một triệu managed entities.

## 6. `flush()` làm gì?

`flush()` yêu cầu Hibernate đồng bộ những thay đổi đang pending trong Persistence Context với database:

~~~java
entityManager.persist(product);
entityManager.flush();
~~~

Hibernate có thể:

- Phát INSERT cho entity mới.
- Phát UPDATE cho managed entities dirty.
- Phát DELETE cho entity bị remove.
- Phát collection table/association SQL.
- Kiểm tra các ràng buộc mà DB đánh giá lúc thực thi.
- Sắp xếp/thực hiện actions theo mapping và action queue.

Sau khi flush thành công, SQL đã được thực hiện trong **transaction hiện tại**. Nhưng transaction vẫn có thể rollback.

~~~text
persist / change entity
        |
        v
pending ORM actions
        |
      flush()
        |
        v
SQL executed inside current transaction
        |
        +---- commit -> changes durable
        |
        +---- rollback -> changes undone
~~~

**Flush không phải commit và không phải clear.**

## 7. `clear()` làm gì?

~~~java
entityManager.clear();
~~~

`clear()` detach tất cả entity đang được quản lý trong Persistence Context hiện tại. Sau đó:

- Các entity references mà code giữ vẫn là Java objects.
- Chúng không còn được dirty checking tự động.
- Thay đổi field trên detached objects không tự được flush.
- Lần load tiếp theo có thể tạo instance managed mới.
- Những association references cũ không tự trở thành managed trở lại.

Trong Hibernate `Session`, `session.clear()` có ý nghĩa tương tự.

**Clear không xóa dữ liệu trong database.** Nó chỉ xóa state managed của context hiện tại.

## 8. Vì sao phải flush trước clear?

Đây là quy tắc quan trọng:

~~~java
session.persist(product);

// Sai nếu muốn bảo đảm pending insert được gửi trước khi detach:
session.clear();
~~~

Khi clear, pending state trong Persistence Context bị detach/discard; những thay đổi chưa flush có thể không được đồng bộ như bạn mong đợi.

Pattern an toàn thường là:

~~~java
session.flush();
session.clear();
~~~

Thứ tự:

1. Hoàn thành các thay đổi trong batch.
2. `flush()` để Hibernate gửi SQL.
3. Nếu flush thành công, `clear()` để detach managed entities.
4. Tiếp tục batch tiếp theo.

Nếu `flush()` ném exception, không tiếp tục clear rồi dùng cùng Session như thể batch đã thành công. Transaction cần rollback theo policy; sau Hibernate/JDBC exception nghiêm trọng, thường nên đóng/discard Session và bắt đầu unit of work mới.

## 9. Ví dụ đầy đủ với batch flush/clear

~~~java
int batchSize = 50;
int count = 0;

try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    try {
        for (Product product : productSource()) {
            session.persist(product);
            count++;

            if (count % batchSize == 0) {
                session.flush();
                session.clear();
            }
        }

        session.flush();
        session.clear();

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
~~~

Với batch size 50, số managed entities tại thời điểm trước mỗi clear thường được giới hạn gần một batch, nếu mỗi iteration tạo một entity mới và không giữ thêm entity graph.

Điều đó **không giới hạn** RAM của `productSource()` nếu nguồn này trả một List chứa toàn bộ dữ liệu. Cần streaming hoặc pagination ở đầu vào nữa.

## 10. Flush/Clear theo số records, không theo thời gian

Một pattern dễ dự đoán:

~~~java
int batchSize = 100;
int processed = 0;

for (Product product : source) {
    session.persist(product);

    if (++processed % batchSize == 0) {
        session.flush();
        session.clear();
    }
}
~~~

Batch boundary theo số records giúp:

- Giới hạn số managed entities.
- Giảm dao động memory theo thời gian xử lý.
- Dễ log progress/checkpoint.
- Dễ benchmark các batch sizes.

Nếu mỗi record tạo một graph gồm parent và nhiều children, số entities thực tế có thể lớn hơn `batchSize`. Hãy đo theo **entity count/graph size**, không chỉ số dòng input.

## 11. Flush cuối cùng là cần thiết

Nếu tổng records không chia hết cho batch size, còn một lô nhỏ ở cuối:

~~~java
for (Product product : source) {
    session.persist(product);

    if (++count % batchSize == 0) {
        session.flush();
        session.clear();
    }
}

// Flush phần dư.
session.flush();
session.clear();
tx.commit();
~~~

Nếu không flush phần dư, commit của transaction thông thường vẫn có thể kích hoạt flush theo cấu hình/provider, nhưng viết rõ final flush giúp kiểm soát và quan sát điểm đồng bộ cuối cùng. Không gọi clear trước khi pending changes cuối đã được flush.

## 12. Batch flush/clear không tự chia transaction

Ví dụ:

~~~java
Transaction tx = session.beginTransaction();

for (...) {
    // persist
    session.flush();
    session.clear();
}

tx.commit();
~~~

Đây vẫn là **một transaction**. Flush/clear nhiều lần không commit từng batch.

Ưu điểm:

- All-or-nothing cho toàn bộ job trong một transaction, nếu DB/transaction support.
- Persistence Context nhỏ hơn.

Nhược điểm:

- Transaction có thể kéo dài.
- Locks/undo/WAL/MVCC resources có thể tồn tại lâu.
- Connection có thể bị giữ lâu.
- Rollback một triệu records có thể rất tốn kém.
- Timeout/deadlock risk tăng theo workload.
- Restart từ giữa job khó hơn.

Vì vậy cần quyết định riêng: **chỉ giới hạn Persistence Context** hay **chia cả transaction thành các chunks**.

## 13. Phân biệt ba loại batch size

| Loại | Điều khiển điều gì? | Ví dụ |
|---|---|---|
| ORM flush/clear batch | Số entities managed giữa các lần clear | Mỗi 50 entities flush + clear |
| JDBC statement batch | Số statements gom trong JDBC batch | `hibernate.jdbc.batch_size=50` |
| Transaction chunk | Số records commit trong một transaction | Commit mỗi 1.000 records |

Chúng có thể cùng dùng một giá trị nhưng không có nghĩa giống nhau.

Ví dụ:

~~~text
Transaction chunk: 1,000 records
    |
    +-- Persistence Context batch: 100
    |      flush + clear
    |      flush + clear
    |      ...
    |
    +-- JDBC batch: 50 statements (nếu mapping/driver hỗ trợ)
           executeBatch nhiều lần
    |
    +-- COMMIT chunk
~~~

Một transaction chunk có thể chứa nhiều flush/clear batches; mỗi flush có thể tạo một hoặc nhiều JDBC batches.

## 14. Cấu hình JDBC batching

Hibernate có các settings thường dùng:

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
~~~

Ý nghĩa:

- `hibernate.jdbc.batch_size`: giới hạn số prepared-statement executions được nhóm theo batch trong các điều kiện phù hợp.
- `hibernate.order_inserts`: sắp xếp insert actions để tăng khả năng gom statements tương thích.
- `hibernate.order_updates`: sắp xếp update actions, có thể giúp batching và giảm một số deadlocks trong workload phù hợp.

Cấu hình này **không gọi `clear()` thay bạn** và không giới hạn số managed entities trong Persistence Context.

Batching thực tế phụ thuộc:

- Entity ID generator.
- SQL statement shape.
- Mapping/table grouping.
- Dialect.
- JDBC driver/database support.
- Hibernate version.
- Các thao tác có generated keys hoặc statement đặc biệt.

Không kết luận JDBC batching hoạt động chỉ vì property đã được đặt; hãy đo số batch executions và SQL thật.

## 15. IDENTITY có thể hạn chế insert batching

Với:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Hibernate thường cần thực thi INSERT để lấy generated identity value. Điều này có thể ngăn hoặc hạn chế JDBC insert batching đối với entity dùng IDENTITY trong nhiều cấu hình.

Với sequence:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE)
private Long id;
~~~

ID có thể được lấy trước khi INSERT, tạo điều kiện thuận lợi hơn cho batching. Tuy nhiên sequence allocation và batching behavior còn phụ thuộc database/provider/version.

Không đổi ID strategy chỉ để bật batching nếu việc đó phá schema/semantics. Benchmark với generator phù hợp và kiểm tra generated SQL.

## 16. Batch size bao nhiêu là hợp lý?

Không có một giá trị đúng cho mọi hệ thống.

Một điểm khởi đầu có thể thử:

| Workload | Batch thử nghiệm ban đầu |
|---|---:|
| Entity nhỏ, ít associations | 25–100 |
| Entity lớn, nhiều fields | 10–50 |
| Graph parent-child phức tạp | 10–50 aggregate roots, đo tổng entities |
| JDBC batch size | 25–50 statements |
| Transaction chunk | 500–2.000 records, tùy DB/job |

Đây là **khoảng thử nghiệm**, không phải recommendation cố định.

Batch quá nhỏ:

- Flush overhead nhiều.
- Ít tận dụng JDBC batching.
- Nhiều lần clear/flush.

Batch quá lớn:

- Persistence Context lớn.
- Flush/dirty checking lâu.
- Heap/GC tăng.
- JDBC batch hoặc DB transaction quá tải.

Đo throughput, heap, GC, DB locks, transaction duration và error/retry rates để chọn.

## 17. Persistence Context size khác heap size

Sau `clear()`, entity không còn managed, nhưng object có thể vẫn được giữ bởi:

~~~java
List<Product> processed = new ArrayList<>();

for (Product p : source) {
    session.persist(p);
    processed.add(p); // Giữ reference trong application.
}
~~~

Lúc này Persistence Context nhỏ nhưng `processed` vẫn giữ tất cả Product objects.

Cần kiểm soát **cả hai**:

- ORM-managed state.
- Application-owned references.
- Input parser buffers.
- Output/error collections.
- Queue backlog.
- JDBC ResultSet/driver buffers.

Không kết luận memory leak đã được sửa chỉ từ việc gọi clear.

## 18. Dùng streaming input thay List khổng lồ

Không tốt cho dữ liệu lớn:

~~~java
List<Product> products = parseEntireFile(csvFile);

for (Product p : products) {
    session.persist(p);
}
~~~

Tốt hơn là đọc tuần tự:

~~~java
try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

    String line;
    int count = 0;

    while ((line = reader.readLine()) != null) {
        Product product = parseProduct(line);
        session.persist(product);

        if (++count % batchSize == 0) {
            session.flush();
            session.clear();
        }
    }

    session.flush();
    session.clear();
}
~~~

Ví dụ lược bỏ header, CSV quoting và error handling để tập trung vào memory. Trong production, dùng CSV parser đúng chuẩn; không tự `split(",")` nếu field có dấu phẩy/quotes/newlines.

## 19. Đọc từ database bằng pagination

Nếu nguồn là một bảng lớn, pagination giúp giới hạn dữ liệu mỗi lần đọc.

Offset pagination:

~~~java
List<Product> page = entityManager.createQuery(
    "select p from Product p order by p.id",
    Product.class
)
.setFirstResult(offset)
.setMaxResults(pageSize)
.getResultList();
~~~

Offset lớn có thể tốn chi phí DB vì database phải bỏ qua nhiều rows. Concurrent inserts/deletes cũng có thể làm page boundaries thay đổi và gây duplicate/missing rows tùy sort/order.

Với job dài, keyset pagination thường đáng cân nhắc hơn.

## 20. Keyset pagination

Nếu có ID tăng và ổn định:

~~~java
List<Product> page = entityManager.createQuery(
    """
    select p from Product p
    where p.id > :lastId
    order by p.id
    """,
    Product.class
)
.setParameter("lastId", lastSeenId)
.setMaxResults(pageSize)
.getResultList();
~~~

Sau khi xử lý page, cập nhật `lastSeenId` bằng ID cuối đã xử lý. Mỗi page là một tập dữ liệu giới hạn.

Ưu điểm:

- Không phải scan/bỏ qua offset lớn.
- Dễ resume theo checkpoint.
- Giảm nguy cơ dịch chuyển vị trí do insert trước offset.
- Có thể kết hợp transaction theo page/chunk.

Điều kiện:

- Sort key phải ổn định, có thứ tự xác định.
- Nếu key không unique, dùng tie-breaker (ví dụ `(created_at, id)`).
- Cần định nghĩa snapshot/cutoff khi rows mới được thêm trong lúc job chạy.
- Không dùng một cursor key có thể thay đổi trong quá trình xử lý.

## 21. Keyset pagination theo hai cột

Khi thứ tự là `created_at, id`:

~~~java
List<Product> page = entityManager.createQuery(
    """
    select p from Product p
    where p.createdAt > :lastCreatedAt
       or (p.createdAt = :lastCreatedAt and p.id > :lastId)
    order by p.createdAt, p.id
    """,
    Product.class
)
.setParameter("lastCreatedAt", lastCreatedAt)
.setParameter("lastId", lastId)
.setMaxResults(pageSize)
.getResultList();
~~~

Composite cursor cần index phù hợp:

~~~sql
CREATE INDEX ix_product_created_id
ON product(created_at, id);
~~~

Nếu có `NULL`, timezone precision hoặc timestamp rounding, cursor comparison phải được thiết kế rõ. ID duy nhất thường dễ vận hành hơn khi business ordering không bắt buộc.

## 22. Mỗi page cần một Persistence Context ngắn

Một pattern:

~~~java
Long lastId = 0L;

while (true) {
    List<Long> ids = readNextIds(lastId, 500);

    if (ids.isEmpty()) {
        break;
    }

    processChunk(ids);

    lastId = ids.get(ids.size() - 1);
}
~~~

`readNextIds()` và `processChunk()` nên có transaction boundaries phù hợp, ví dụ transaction đọc page và transaction ghi chunk. Nếu cả hai cùng tham gia một transaction outer kéo dài, lợi ích về transaction lifetime sẽ mất.

Khi chỉ cần IDs để xử lý, query scalar ID projection giúp tránh hydrate full entities trong bước discovery.

## 23. Dùng scalar/DTO projection nếu không cần managed entity

Không cần load toàn entity chỉ để xuất ba cột:

~~~java
public record ProductRow(
    Long id,
    String sku,
    String name
) {}
~~~

~~~java
List<ProductRow> rows = entityManager.createQuery(
    """
    select new com.example.ProductRow(
        p.id, p.sku, p.name
    )
    from Product p
    where p.id > :lastId
    order by p.id
    """,
    ProductRow.class
)
.setParameter("lastId", lastId)
.setMaxResults(500)
.getResultList();
~~~

DTO projection:

- Không tạo full managed entity cho từng row theo cách entity query.
- Không cần dirty checking cho dữ liệu đọc-only.
- Chỉ chọn các cột cần thiết.
- Vẫn có thể materialize List lớn nếu không giới hạn page.
- Không thay thế validation/domain methods nếu cần business mutation.

Đây thường là tối ưu hiệu quả hơn việc load entity graph rồi chỉ đọc vài properties.

## 24. Scroll/stream query và resource lifetime

Hibernate có thể cung cấp scrollable results để duyệt lượng rows lớn mà không materialize toàn bộ List.

Ví dụ Hibernate-specific minh họa:

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    try (ScrollableResults<Product> results =
             session.createSelectionQuery(
                 "from Product p order by p.id",
                 Product.class
             )
             .setFetchSize(200)
             .scroll(ScrollMode.FORWARD_ONLY)) {

        int count = 0;

        while (results.next()) {
            Product p = results.get();

            // Xử lý p.

            if (++count % 100 == 0) {
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
~~~

API generic/try-with-resources và kiểu kết quả có thể khác minor versions; kiểm tra Hibernate 6.x Javadocs của dự án. Việc `clear()` trong khi cursor còn mở cũng cần test với driver, fetch strategy và associations; keyset pagination theo chunk thường dễ quản lý lifecycle hơn.

**Fetch size là JDBC driver hint**, không phải bảo đảm chỉ có đúng N rows trong heap. Cursor thường giữ connection và transaction trong thời gian đọc; không giữ nó hàng giờ nếu có lựa chọn page/chunk ngắn hơn.

## 25. Không dùng getResultList() cho toàn bộ bảng

~~~java
List<Product> all =
    entityManager.createQuery(
        "from Product",
        Product.class
    ).getResultList();
~~~

Dù Persistence Context được clear sau mỗi 100 records trong vòng lặp, tất cả Product đã nằm trong `all` ngay từ đầu. Bạn đã materialize toàn bộ dữ liệu.

Giải pháp:

- `setMaxResults()` theo page.
- Keyset pagination.
- Scroll/stream với driver phù hợp.
- DTO/scalar projection.
- Spring Batch ItemReader.
- DB export/bulk tooling khi workload phù hợp.

Giới hạn ORM context và giới hạn input result memory là hai mục tiêu riêng.

## 26. `@Transactional(readOnly=true)` không thay `clear()`

Read-only transaction có thể giảm dirty-checking overhead tùy Hibernate/Spring integration, nhưng:

- Session vẫn có Persistence Context.
- Entities vẫn có thể được giữ managed.
- Collections/proxies vẫn chiếm bộ nhớ.
- Application List vẫn giữ references.
- Read-only không detach entities.
- Không giới hạn số rows trả về.

Nếu cần đọc hàng triệu rows, kết hợp projection, pagination/streaming và context lifecycle rõ ràng.

## 27. Hibernate StatelessSession là lựa chọn khác

`StatelessSession` không có Persistence Context/first-level managed identity map như `Session` stateful.

~~~java
try (StatelessSession session =
         sessionFactory.openStatelessSession()) {

    Transaction tx = session.beginTransaction();

    try {
        for (Product product : productSource()) {
            session.insert(product);
        }
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) tx.rollback();
        throw ex;
    }
}
~~~

Ưu điểm:

- Không tích lũy managed entities trong L1 context.
- Không dirty checking tự động.
- CRUD tường minh.
- Hữu ích cho thao tác hàng loạt trên rows độc lập.

Trade-offs:

- Không có cascade lifecycle thông thường.
- Không có orphan removal tracking như Session.
- Không có managed identity map.
- Không có dirty checking; sửa object phải gọi `update()` rõ.
- Entity callbacks/events thông thường có thể bị bỏ qua theo StatelessSession semantics.
- Associations và lazy loading không hoạt động như stateful Session.
- Version, batching và API behavior cần xác minh đúng Hibernate release.

StatelessSession giảm ORM context overhead nhưng **không tự giải quyết** input List lớn, JDBC buffering, transaction quá dài hay idempotency.

## 28. Bulk HQL/JPQL DML khi nhiều rows có cùng quy tắc

Nếu muốn đánh dấu tất cả sản phẩm hết hạn:

~~~java
int updated = entityManager.createQuery(
    """
    update Product p
    set p.active = false
    where p.expiryDate < :cutoff
    """
)
.setParameter("cutoff", cutoff)
.executeUpdate();
~~~

Bulk update có thể thay thế hàng nghìn entity loads/updates bằng một SQL statement.

Nhưng bulk DML:

- Bypass per-entity dirty checking/callback lifecycle.
- Persistence Context đang mở có thể stale.
- Cascade/orphan removal không diễn ra như từng entity.
- `@Version` không tự được xử lý giống entity-by-entity update nếu query không viết logic version thích hợp.
- L2/query cache cần được xem xét theo provider.
- DB-specific SQL có thể có behavior khác HQL.

Sau bulk DML, cân nhắc `flush()` trước và `clear()` sau để đồng bộ context, nhưng chỉ khi bạn hiểu pending changes và managed entities sẽ bị detach.

## 29. JDBC trực tiếp cho ingestion cực lớn

Với import đơn giản, throughput quan trọng và không cần ORM entity lifecycle, JDBC batching có thể phù hợp:

~~~java
String sql = """
    INSERT INTO product(sku, name, price)
    VALUES (?, ?, ?)
    """;

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        int count = 0;

        for (ProductRow row : source) {
            ps.setString(1, row.sku());
            ps.setString(2, row.name());
            ps.setBigDecimal(3, row.price());
            ps.addBatch();

            if (++count % 500 == 0) {
                ps.executeBatch();
            }
        }

        ps.executeBatch();
        connection.commit();
    } catch (SQLException ex) {
        connection.rollback();
        throw ex;
    }
}
~~~

Ví dụ lược bỏ connection pooling/exception translation và batch leftovers policy. JDBC trực tiếp cho phép kiểm soát SQL và batch, nhưng application tự chịu trách nhiệm:

- Mapping values.
- FK ordering.
- Defaults/validation.
- Versioning/concurrency.
- Auditing/domain events.
- Transaction management.
- Cache invalidation nếu cùng database được đọc bởi ORM.

Không chuyển sang JDBC chỉ vì một benchmark nhỏ nếu business semantics phụ thuộc ORM lifecycle.

## 30. Cascade và entity graph làm batch size phình ra

Giả sử mỗi Order có 20 OrderLines:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines;
~~~

Persist 100 Orders có thể quản lý thêm 2.000 OrderLines. Batch size 100 **aggregate roots** không đồng nghĩa chỉ có 100 managed entities.

Khi tính memory, hãy ước lượng:

- Root entities.
- Cascaded child entities.
- Collection wrappers/snapshots.
- Associated reference entities.
- Embeddables/element collections.
- Application DTOs/commands.

Nếu mỗi aggregate rất lớn, batch theo tổng entities hoặc theo số aggregate có giới hạn graph phù hợp; đo peak heap thực tế.

## 31. Thứ tự insert và foreign keys

Ví dụ:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES purchase_order(id)
);
~~~

Khi insert graph, parent thường phải có ID trước khi child row tham chiếu FK. Hibernate action queue và cascade có thể điều phối stateful inserts; StatelessSession/JDBC yêu cầu code rõ thứ tự hơn.

~~~text
INSERT purchase_order
    |
    v
parent ID available
    |
    v
INSERT order_line rows
~~~

Không chia batch boundary giữa parent và child nếu child chưa thể insert hợp lệ. Khi chunking, đảm bảo mọi references ngoài chunk có cách resolve rõ và không phụ thuộc một managed object đã bị clear.

## 32. Clear làm detached references; đừng dùng object cũ như managed

~~~java
Product p = session.get(Product.class, id);

session.flush();
session.clear();

p.rename("Tên mới");

// p hiện detached; đổi field không tự UPDATE.
~~~

Nếu cần tiếp tục sửa:

~~~java
Product managed = session.merge(p);
managed.rename("Tên mới");
~~~

`merge()` trả **một managed instance khác hoặc instance managed tương ứng**; object truyền vào không nhất thiết trở thành managed. Hãy tiếp tục thao tác trên object được trả về.

Trong batch processing, tốt hơn thường là load lại entity cần thiết theo ID trong chunk mới thay vì giữ toàn bộ detached graphs qua nhiều vòng.

## 33. Clear detach cả những reference entities dùng chung

Ví dụ một `Category` được dùng bởi nhiều Products:

~~~java
Product p = new Product(...);
p.setCategory(category);
session.persist(p);

session.flush();
session.clear();
~~~

Sau clear, `category` reference mà application đang giữ cũng detached nếu nó được quản lý bởi Session đó. Khi tạo Product ở chunk tiếp theo, không nên giả định Hibernate vẫn theo dõi Category cũ.

Các lựa chọn:

- Lưu `categoryId` và load reference trong chunk mới.
- Dùng `session.getReference(Category.class, id)` sau clear.
- Đảm bảo entity/reference có lifecycle rõ.
- Dùng DTO/command data thay cho giữ managed graph.
- Không merge cả graph lớn nếu chỉ cần liên kết một FK.

Cẩn trọng cascade `MERGE`/`PERSIST`: merge một graph cũ có thể copy state không mong muốn.

## 34. Cascade và orphan removal qua chunk boundaries

Nếu Order và OrderLines được xử lý trong cùng một aggregate:

- Đừng clear giữa lúc graph vẫn còn pending operations.
- Flush toàn bộ graph ở boundary thích hợp.
- Chỉ clear sau khi SQL thành công.
- Khi chunk tiếp theo cần sửa aggregate đó, reload aggregate/children.
- Không kỳ vọng orphan removal được phát hiện sau khi collection đã detached.
- Không truyền lazy proxies qua thread hoặc ra ngoài Session.

Một aggregate có nhiều rows phụ thuộc nhau nên thường được xử lý trong cùng unit of work/transaction, trừ khi domain cho phép trạng thái trung gian.

## 35. Optimistic locking khi chia chunk

Entity:

~~~java
@Version
private long version;
~~~

Khi transaction chunk A load row version 5 và cập nhật, transaction chunk B có thể cũng load version 5. Nếu A commit trước, B có thể gặp optimistic lock conflict.

Trong job dài:

- Không giữ stale entities qua nhiều chunks.
- Reload state trong transaction mới.
- Chọn retry policy cho `OptimisticLockException`.
- Phân vùng dữ liệu để giảm concurrent writes cùng aggregate.
- Không retry mù một command không idempotent.
- Kiểm tra row counts/version trong bulk SQL nếu tự xử lý.

Persistence Context nhỏ không tự giải quyết concurrency conflicts.

## 36. Transaction chunking: commit từng phần

Một transaction cho cả triệu rows có thể quá dài. Có thể commit mỗi 1.000 records:

~~~text
Chunk 1: BEGIN -> process 1,000 -> COMMIT
Chunk 2: BEGIN -> process 1,000 -> COMMIT
Chunk 3: BEGIN -> process 1,000 -> COMMIT
...
~~~

Lợi ích:

- Giảm transaction lifetime.
- Giải phóng locks/resources sau mỗi commit.
- Retry phạm vi nhỏ hơn.
- Checkpoint tiến độ sau commit.
- Giới hạn lượng công việc rollback.

Đánh đổi:

- Toàn job không còn all-or-nothing.
- Dữ liệu có thể ở trạng thái partial completion.
- Cần idempotency/checkpoint/restart.
- Consumer khác có thể nhìn thấy từng chunk commit.

Chỉ chọn khi domain chấp nhận partial progress hoặc có staging/publish strategy.

## 37. Spring TransactionTemplate cho từng chunk

Ví dụ imperative Spring:

~~~java
@Service
public class ProductImportJob {

    private final TransactionTemplate transactionTemplate;
    private final SessionFactory sessionFactory;

    public ProductImportJob(
            PlatformTransactionManager transactionManager,
            SessionFactory sessionFactory) {
        this.transactionTemplate =
            new TransactionTemplate(transactionManager);
        this.sessionFactory = sessionFactory;
    }

    public void importChunks(Iterator<ProductRow> input) {
        while (input.hasNext()) {
            List<ProductRow> chunk = nextChunk(input, 1000);

            transactionTemplate.executeWithoutResult(status -> {
                try (Session session =
                         sessionFactory.getCurrentSession()) {
                    // Với Spring-managed current Session, ownership/
                    // closing phụ thuộc cấu hình; ví dụ này chỉ mô tả
                    // transaction callback, xem ghi chú bên dưới.
                    for (ProductRow row : chunk) {
                        session.persist(toEntity(row));
                    }

                    session.flush();
                    session.clear();
                }
            });
        }
    }
}
~~~

**Ghi chú quan trọng:** Khi dùng Spring `HibernateTransactionManager` hoặc `JpaTransactionManager` với current-session/EntityManager integration, Spring quản lý lifecycle Session/EntityManager gắn transaction. Không tự close một current Session do transaction manager sở hữu. Đoạn trên minh họa transaction callback; cách lấy Session thực tế phải theo integration của dự án. Nếu tự `openSession()`, bạn phải quản lý connection/transaction/session ownership rõ và đảm bảo nó tham gia đúng transaction.

Một lựa chọn dễ hiểu là dùng `EntityManager` được inject và `TransactionTemplate` với persistence context transaction-scoped; mỗi callback mở transaction mới và kết thúc scope sau mỗi chunk.

## 38. Không gọi inner @Transactional bằng self-invocation để tạo chunk

Anti-pattern:

~~~java
public void importAll() {
    while (...) {
        this.importChunk(); // Proxy không intercept lời gọi nội bộ.
    }
}

@Transactional
public void importChunk() {
    // ...
}
~~~

Trong proxy-based Spring AOP, `this.importChunk()` không đi qua transaction proxy, nên không tạo transaction mới như mong đợi.

Các lựa chọn:

- `TransactionTemplate` trong loop.
- Tách `ChunkWriter` thành Spring bean khác và gọi qua proxy.
- Dùng Spring Batch chunk-oriented processing.
- Thiết kế transaction boundary ở method được gọi từ bên ngoài.

Kiểm tra transaction thực tế bằng integration tests/logs; không chỉ nhìn annotation.

## 39. Spring Batch chunk-oriented processing

Spring Batch có mô hình:

~~~text
ItemReader
    |
    v
ItemProcessor
    |
    v
ItemWriter
    |
    v
Commit interval
    |
    v
Transaction commit
~~~

Ví dụ cấu hình khái niệm:

~~~java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<ProductRow> reader,
        ItemProcessor<ProductRow, Product> processor,
        ItemWriter<Product> writer) {

    return new StepBuilder("importProducts", jobRepository)
        .<ProductRow, Product>chunk(1000, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
~~~

Mỗi chunk có transaction theo cấu hình Step. Tuy nhiên **commit interval không tự bảo đảm mọi Persistence Context do writer/reader sử dụng đều bị clear đúng cách**. Phải hiểu transaction-scoped EntityManager, implementation của ItemWriter, flush/clear behavior và version Spring Batch đang dùng.

Spring Batch còn hỗ trợ restartability, checkpoint và skip/retry policies; đây là lợi ích lớn cho jobs dài.

## 40. ItemWriter dùng JPA phải có lifecycle rõ

Nếu writer gọi `EntityManager.persist()` cho cả chunk:

~~~java
public void write(Chunk<? extends Product> chunk) {
    for (Product p : chunk) {
        entityManager.persist(p);
    }
    entityManager.flush();
    entityManager.clear();
}
~~~

Đây là ví dụ minh họa. Spring Batch/JPA writer implementations có thể đã thực hiện flush/clear theo contract/version cụ thể; không lặp clear/flush vô thức mà chưa xem behavior của writer đang dùng.

Cần đảm bảo:

- EntityManager tham gia transaction của chunk.
- Clear chỉ xảy ra sau flush thành công.
- Không còn pending changes bị detach.
- Không cần managed entity references sau writer.
- Error/rollback được xử lý bởi Step transaction.

## 41. Checkpoint và idempotency khi restart

Nếu mỗi chunk commit độc lập, process có thể crash:

~~~text
Chunk 1 committed
Chunk 2 committed
Chunk 3 partially processed, rollback
Process crash
Restart job
~~~

Một checkpoint đáng tin nên được lưu **sau khi chunk commit** hoặc trong cùng transaction nếu repository/job metadata hỗ trợ.

Các cách chống duplicate:

- Unique natural key/import key.
- Upsert theo business key.
- Bảng `processed_import_row`.
- Job ID + source record ID.
- Deterministic transformation.
- Checkpoint theo keyset cursor.

Không lưu checkpoint trước khi dữ liệu chunk commit; nếu checkpoint đi trước DB data, restart có thể bỏ qua rows chưa được ghi.

## 42. Skip/retry và lỗi giữa batch

Nếu flush batch thất bại do unique/FK constraint:

- Transaction có thể bị đánh dấu rollback-only hoặc DB transaction aborted.
- Hibernate Session có thể không còn an toàn để tiếp tục.
- Không nuốt exception rồi tiếp tục insert rows vào cùng Session.
- Rollback chunk và tạo unit of work mới.
- Phân loại lỗi data-invalid vs transient DB errors.
- Ghi reject record/checkpoint theo policy đã thiết kế.

Nếu muốn skip một row lỗi mà vẫn commit rows còn lại, phải thiết kế savepoint/transaction strategy hoặc validate trước; không tự catch exception ở vòng lặp rồi cho rằng database có thể tiếp tục transaction bình thường.

## 43. Transaction per row thường quá nhỏ

Mở một transaction cho từng record:

~~~text
BEGIN -> INSERT -> COMMIT
BEGIN -> INSERT -> COMMIT
...
~~~

có thể tăng round trips, commit overhead và giảm throughput đáng kể.

Nhưng transaction quá lớn cũng có hại. Chọn chunk size cân bằng:

- DB commit cost.
- Lock lifetime.
- Rollback scope.
- Connection pool.
- Memory/PC size.
- Retry cost.
- Business atomicity.

Batch 500–2.000 có thể là điểm thử nghiệm, không phải luật. Một số DB/workloads cần nhỏ hơn hoặc lớn hơn.

## 44. Transaction chunk và Persistence Context chunk nên phối hợp

Một thiết kế:

~~~text
Transaction chunk: 1,000 rows
    |
    +-- 10 ORM batches × 100 entities
           |
           +-- persist 100
           +-- flush + clear
           +-- persist 100
           +-- flush + clear
           ...
    |
    +-- final flush
    |
    +-- COMMIT
    |
    +-- checkpoint
~~~

Tuy nhiên nếu Persistence Context bị clear sau mỗi 100 rows, transaction vẫn mở cho 1.000 rows. Khi commit, các entity đã flush/clear vẫn nằm trong DB transaction và sẽ rollback cùng chunk nếu chunk thất bại.

Điều này thường là sự cân bằng hữu ích: PC nhỏ nhưng transaction không quá lớn. Cần nhớ external side effects không rollback cùng DB transaction.

## 45. Clear toàn bộ hay detach từng entity?

`clear()` detach toàn bộ context. Nếu chỉ muốn giải phóng một entity cụ thể, Hibernate `Session` có API:

~~~java
session.detach(entity);
~~~

JPA `EntityManager.detach(entity)` cũng có semantics tương ứng.

Tuy nhiên:

- Detach parent không tự giải phóng mọi children mà application đang giữ.
- Associated entities có thể vẫn managed.
- Pending changes của entity detach có thể không được flush nếu chưa flush trước.
- Collection snapshots/other managed entities vẫn còn.
- Quản lý graph phức tạp hơn clear.

Trong batch insert độc lập, `flush()+clear()` thường đơn giản hơn. Khi cần giữ một phần managed context (ví dụ reference entity), hãy thiết kế và đo cẩn thận.

## 46. `clear()` không phải System.gc()

~~~java
session.flush();
session.clear();
~~~

sẽ loại managed references khỏi Persistence Context, nhưng JVM chỉ thu hồi object khi **không còn strong references** và GC quyết định thực hiện.

Không gọi `System.gc()` sau mỗi batch để “sửa” memory. Điều đó có thể gây full GC pauses và không giải quyết application giữ references.

Nếu heap không giảm sau clear, kiểm tra:

- Input collection/List.
- Static caches.
- Queues/metrics labels.
- Logging buffers.
- Batch result lists.
- Entity graph references.
- ThreadLocal/MDC/custom contexts.
- JDBC ResultSet/streams chưa đóng.

Dùng heap dump/profiler để xác định retaining paths.

## 47. Query read-only và read-only entity không thay context size

Một query có thể được đánh dấu read-only:

~~~java
query.setReadOnly(true);
~~~

hoặc Session default:

~~~java
session.setDefaultReadOnly(true);
~~~

Điều này có thể giảm dirty-checking/snapshot overhead tùy mapping/version, nhưng **entity vẫn có thể được giữ trong Persistence Context**.

Nếu query load 500.000 entities và application giữ một Session dài, read-only flag không thay thế pagination/clear/streaming. Cũng đừng nhầm `@Transactional(readOnly=true)` với StatelessSession.

## 48. Lazy collections có thể làm footprint tăng ngoài dự kiến

Một entity root nhỏ có thể giữ collection wrapper; khi code gọi:

~~~java
order.getLines().size();
~~~

Hibernate có thể load hàng nghìn children vào Persistence Context. Một batch gồm 100 Orders có thể kéo theo hàng chục nghìn child entities.

Để kiểm soát:

- Chỉ fetch associations cần thiết.
- Dùng DTO projection cho reports.
- Batch fetch lazy associations khi phù hợp.
- Tránh load nhiều to-many collections cùng lúc.
- Không gọi `size()`/iterate một collection khổng lồ mà không hiểu SQL.
- Xử lý graph và clear ở boundaries an toàn.

`@BatchSize` hoặc `hibernate.default_batch_fetch_size` giúp gom **association SELECT fetching**, không phải JDBC DML batch và không tự giới hạn Persistence Context.

## 49. Phân biệt batch fetching và JDBC batching

| Cơ chế | Hướng dữ liệu | Mục tiêu |
|---|---|---|
| JDBC statement batching | Writes | Gom INSERT/UPDATE/DELETE executions |
| Hibernate batch fetching | Reads | Gom loads của proxies/collections |
| Flush/clear batching | ORM memory | Giới hạn managed entities |
| Pagination/chunking | Input/output | Giới hạn records mỗi lần xử lý |
| Transaction chunking | Database transaction | Giới hạn commit/rollback scope |

Ví dụ cấu hình batch fetching:

~~~properties
hibernate.default_batch_fetch_size=32
~~~

Nó có thể giúp tránh N+1 trong một số association loads, nhưng không có nghĩa chỉ 32 entities được giữ trong Persistence Context.

## 50. Một Session dài còn có nguy cơ stale state

Persistence Context không chỉ tốn memory. Nó còn có thể giữ state cũ:

- Một transaction khác cập nhật row.
- Job giữ entity cũ trong nhiều phút.
- Flush update có thể ghi state dựa trên dữ liệu stale.
- Optimistic locking có thể phát hiện conflict nếu mapping/version được dùng.
- Không có version/lock phù hợp có thể gây lost updates.

Clear/reload giữa chunks làm unit of work nhỏ hơn và giúp đọc state mới theo transaction/isolation mới. Nhưng nó không thay thế concurrency control.

## 51. Long transaction gây áp lực lên database

Một transaction mở quá lâu có thể:

- Giữ row/table locks.
- Giữ MVCC snapshot lâu, cản trở cleanup/vacuum ở một số DB.
- Tích lũy undo/WAL/transaction log.
- Chiếm connection pool slot.
- Tăng timeout/deadlock risk.
- Làm rollback lâu khi lỗi.
- Làm dữ liệu chưa commit không visible cho transaction khác.

Do đó, flush/clear theo batch là giải pháp cho **Persistence Context memory**, không đủ nếu transaction lifetime vẫn quá dài. Khi workload cho phép partial commits, chia transaction chunks.

## 52. Một pipeline import có kiểm soát

~~~mermaid
flowchart TD
    A["Đọc input tuần tự"] --> B["Parse + validate"]
    B --> C["Tạo chunk giới hạn"]
    C --> D["Mở transaction chunk"]
    D --> E["Persist/update theo ORM batch"]
    E --> F["Flush"]
    F --> G["Clear Persistence Context"]
    G --> H{"Còn records trong chunk?"}
    H -- "Có" --> E
    H -- "Không" --> I["Commit chunk"]
    I --> J["Checkpoint sau commit"]
    J --> K{"Còn input?"}
    K -- "Có" --> C
    K -- "Không" --> L["Hoàn tất"]
~~~

Sơ đồ tách:

- Input chunk.
- ORM flush/clear boundaries.
- Transaction commit.
- Checkpoint.

Các boundary có thể trùng hoặc lồng nhau tùy memory/atomicity requirements.

## 53. Chọn giữa Stateful Session, StatelessSession và bulk SQL

| Yêu cầu | Lựa chọn cân nhắc |
|---|---|
| Domain logic và cascade phức tạp | Stateful Session + flush/clear |
| Import entity graph vừa phải | Stateful Session + batch boundaries |
| Rows độc lập, không cần lifecycle ORM | StatelessSession |
| Cùng một rule update nhiều rows | Bulk HQL/SQL |
| Ingestion rất lớn, schema đơn giản | JDBC batch/DB bulk loader |
| Đọc report vài columns | DTO/scalar projection |
| Job cần restart/skip/retry/checkpoint | Spring Batch |
| Đọc dataset lớn theo thứ tự | Keyset pagination hoặc cursor |

Không có một lựa chọn tối ưu cho mọi job. Ưu tiên semantics domain trước, rồi benchmark throughput và resource usage.

## 54. Batch update managed entities

Ví dụ cập nhật nhiều Products:

~~~java
int batchSize = 100;
int count = 0;

for (Long id : productIds) {
    Product p = session.find(Product.class, id);

    if (p != null) {
        p.recalculatePrice();
    }

    if (++count % batchSize == 0) {
        session.flush();
        session.clear();
    }
}

session.flush();
session.clear();
~~~

`find()` từng ID có thể tạo N SELECTs nếu không dùng phù hợp batching/queries. Tối ưu nguồn IDs và loading strategy riêng.

Sau `clear()`, entity `p` đã detach. Không giữ list `p` rồi tiếp tục mutate sau đó. Nếu một entity được cập nhật ở nhiều chunks, reload nó trong chunk cần xử lý.

## 55. Batch delete

Nếu phải xóa từng entity để giữ cascade/callbacks:

~~~java
int count = 0;

for (Long id : ids) {
    Product p = session.find(Product.class, id);

    if (p != null) {
        session.remove(p);
    }

    if (++count % batchSize == 0) {
        session.flush();
        session.clear();
    }
}

session.flush();
session.clear();
~~~

Nếu dùng bulk HQL DELETE, số statements giảm mạnh nhưng per-entity lifecycle/cascade semantics khác. Chọn theo yêu cầu audit, cascade, soft delete và cache consistency.

Không dùng `deleteAllInBatch()` với giả định nó tương đương gọi `remove()` cho từng entity.

## 56. Xử lý nhiều parent-child aggregates

Một aggregate graph cần được ghi trong cùng transaction chunk khi các FK/invariants phụ thuộc nhau.

~~~java
for (OrderInput input : chunk) {
    Order order = mapOrder(input);

    for (OrderLine line : order.getLines()) {
        line.setOrder(order);
    }

    session.persist(order);
}
session.flush();
session.clear();
~~~

Với cascade PERSIST, persist root có thể cascade children theo mapping. Nếu không có cascade, persist children rõ ràng.

Không clear giữa lúc root đã persist nhưng children còn pending nếu thứ tự/ownership chưa được giải quyết. Sau flush, clear detach cả root và children.

## 57. Generated identifiers và checkpoint

Nếu ID được database sinh khi INSERT, ứng dụng có thể chỉ nhận generated ID sau operation/flush phù hợp.

Nếu checkpoint cần ID DB:

~~~java
session.persist(entity);
session.flush();

Long generatedId = entity.getId();
~~~

Tuy nhiên ID generation timing phụ thuộc strategy. Không dùng generated ID như checkpoint duy nhất nếu job restart có thể tạo duplicates; dùng stable source key/import ID và unique constraint.

Sequence gaps sau rollback là bình thường; không giả định IDs phải liên tiếp.

## 58. Validation trước flush giúp batch lỗi ít tốn kém

Một lỗi constraint ở record cuối của chunk có thể khiến cả chunk rollback. Có thể giảm một số lỗi bằng:

- Validate required fields trước persist.
- Normalize natural keys.
- Check format/length.
- Resolve referenced IDs.
- Kiểm tra business invariants có thể xác minh an toàn.
- Dùng DB constraints làm lớp cuối cùng cho concurrency/integrity.

Không thay database constraints bằng “SELECT trước để xem có duplicate không”: hai transactions có thể race. Unique/FK/NOT NULL constraints vẫn cần thiết.

## 59. Tách rejected records khỏi committed records

Một import job có thể cần skip dữ liệu không hợp lệ thay vì rollback toàn job. Thiết kế:

~~~text
Input row
   |
Parse / validate
   |
   +-- Invalid -> rejected_rows / error report
   |
   +-- Valid -> transaction chunk
                    |
                    +-- DB success -> commit/checkpoint
                    |
                    +-- DB transient error -> rollback/retry
                    |
                    +-- DB permanent error -> policy xử lý
~~~

Không ghi rejected record vào cùng một transaction đã bị aborted rồi kỳ vọng tiếp tục. Có thể ghi rejection report sau rollback bằng transaction mới hoặc lưu ở file/object storage, tùy yêu cầu.

## 60. Cách đo Persistence Context và heap

Để đánh giá batch size, theo dõi:

- Heap used/committed/max.
- Allocation rate.
- GC frequency/pause time.
- Số entity loads/inserts/updates.
- Flush count và flush duration.
- JDBC prepared statements/batch executions.
- Transaction duration.
- Connection pool active/pending.
- DB CPU/IO/lock waits.
- Rows per second và error/retry rate.

Hibernate Statistics có thể cung cấp số liệu tổng hợp:

~~~java
SessionFactory sf =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics stats = sf.getStatistics();

long loadsBefore = stats.getEntityLoadCount();
long insertsBefore = stats.getEntityInsertCount();
long flushesBefore = stats.getFlushCount();

// Chạy workload cô lập.

long loads = stats.getEntityLoadCount() - loadsBefore;
long inserts = stats.getEntityInsertCount() - insertsBefore;
long flushes = stats.getFlushCount() - flushesBefore;
~~~

Statistics là số liệu ở SessionFactory scope và có thể bị các threads khác làm nhiễu. Chỉ bật/capture trong test hoặc benchmark có kiểm soát; không clear global stats giữa production requests.

## 61. Profiling khi heap không giảm

Nếu heap tăng dù đã clear:

1. Lấy heap histogram hoặc heap dump ở test/staging.
2. Xem loại object chiếm nhiều nhất.
3. Xem retaining paths tới GC roots.
4. Kiểm tra List/Map/queue và static caches.
5. Kiểm tra entity graphs còn được application giữ.
6. Kiểm tra stream/ResultSet/JDBC resources chưa đóng.
7. Kiểm tra ThreadLocal, callbacks, listeners và logging buffers.
8. So sánh sau mỗi chunk và sau khi input source kết thúc.

Không suy đoán memory leak chỉ từ `Runtime.freeMemory()`: JVM có thể giữ committed heap để tái sử dụng dù objects đã eligible for GC.

## 62. SQL và flush timing trong logs

Một job có thể log:

~~~text
chunk=12 started rows=1000
flush batch=1 elapsed=45ms
clear batch=1
flush batch=2 elapsed=52ms
clear batch=2
chunk=12 committed elapsed=410ms
checkpoint=12000
~~~

Các logs nên dùng:

- Job ID.
- Chunk sequence.
- Row count.
- Duration.
- Transaction outcome.
- Last committed source key.
- Retry count.
- Error classification.

Không log toàn bộ entity payload, PII hoặc SQL bind values thiếu kiểm soát. Chunk ID là metadata vận hành; không dùng nó làm metric label nếu cardinality quá cao.

## 63. Test đảm bảo flush/clear không làm mất dữ liệu

Một integration test cơ bản:

~~~java
@Test
void persistsRowsAcrossFlushAndClearBoundaries() {
    try (Session session = sessionFactory.openSession()) {
        Transaction tx = session.beginTransaction();

        try {
            for (int i = 0; i < 250; i++) {
                session.persist(new Product("SKU-" + i));

                if ((i + 1) % 50 == 0) {
                    session.flush();
                    session.clear();
                }
            }

            session.flush();
            session.clear();
            tx.commit();
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        }
    }

    try (Session verify = sessionFactory.openSession()) {
        Long count = verify.createSelectionQuery(
            "select count(p) from Product p",
            Long.class
        ).getSingleResult();

        assertEquals(250L, count);
    }
}
~~~

Constructor `Product(String sku)` và test schema là fixture minh họa. Test nên chạy trên DB phù hợp với dialect/ID strategy thực tế.

## 64. Test clear khiến entity detached

~~~java
@Test
void clearDetachesManagedEntities() {
    try (Session session = sessionFactory.openSession()) {
        Transaction tx = session.beginTransaction();

        Product product = new Product("SKU-DETACH");
        session.persist(product);
        session.flush();

        assertTrue(session.contains(product));

        session.clear();

        assertFalse(session.contains(product));

        product.rename("Changed in memory");
        tx.commit();
    }

    // Đọc bằng Session mới để xác nhận field sau clear
    // không được dirty-check tự động.
}
~~~

Test minh họa `Session.contains()` để xác nhận managed status. Khi kiểm tra database state, mở Session mới và query theo ID/SKU, không assert vào Java object cũ.

## 65. Test transaction chunks và partial progress

Một test có thể:

1. Commit chunk 1.
2. Làm chunk 2 vi phạm unique constraint.
3. Rollback chunk 2.
4. Xác nhận chunk 1 vẫn tồn tại.
5. Xác nhận checkpoint chỉ đến hết chunk 1.
6. Restart job và xử lý lại chunk 2.
7. Xác nhận idempotency không tạo duplicate chunk 1.

Đây là test khác với flush/clear trong một transaction lớn: **chunk commit là boundary atomicity**.

## 66. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Heap tăng theo records | Không clear Persistence Context | Flush + clear theo batch |
| Clear rồi mất pending writes | Clear trước flush | Flush thành công rồi clear |
| RAM vẫn tăng sau clear | Application giữ references/List | Streaming input, bounded queues |
| Batch JDBC bật nhưng PC vẫn lớn | Nhầm batching với clear | Quản lý ORM context riêng |
| Job giữ DB connection lâu | Một transaction toàn job | Transaction chunks nếu domain cho phép |
| Flush cuối thất bại | Constraint/DB error | Rollback chunk, không dùng Session lỗi |
| Entity cũ không tự update | Clear đã detach entity | Reload hoặc merge và dùng object trả về |
| Merge nhưng sửa object cũ | Merge copy state vào managed instance | Dùng return value của merge |
| Child thiếu khi clear | Clear giữa aggregate graph | Flush graph đầy đủ tại boundary |
| Duplicate khi restart | Checkpoint/idempotency thiếu | Stable key, commit-aware checkpoint |
| Query đầu vào dùng List khổng lồ | getResultList toàn bảng | Keyset/stream/DTO |
| N+1 trong batch | Lazy access từng entity | Fetch plan/batch fetching/DTO |
| Identity generator không batch insert | Generated key cần insert sớm | Đánh giá sequence hoặc strategy phù hợp |
| Hết connection pool | Transaction/stream giữ connection | Rút ngắn scope, đóng resources |
| Rollback toàn job quá lâu | Transaction quá lớn | Chunk transactions hoặc staging |
| Bulk DML làm cache stale | Bypass managed lifecycle | Flush/clear/cache invalidation |

## 67. Quy trình chọn chiến lược

~~~mermaid
flowchart TD
    A["Tác vụ dài xử lý nhiều records"] --> B{"Có cần entity lifecycle/cascade?"}
    B -- "Có" --> C["Stateful Session"]
    C --> D["Streaming/chunked input"]
    D --> E["Persist/update theo batch"]
    E --> F["flush + clear"]
    F --> G{"Transaction quá dài?"}
    G -- "Có" --> H["Commit chunks + checkpoint"]
    G -- "Không" --> I["Một transaction nếu atomicity yêu cầu"]
    B -- "Không" --> J{"Rows độc lập hay cùng một SQL rule?"}
    J -- "Rows độc lập" --> K["StatelessSession / JDBC batch"]
    J -- "Cùng một rule" --> L["Bulk HQL/SQL"]
    H --> M["Đo heap, JDBC, DB và retry"]
    I --> M
    K --> M
    L --> M
~~~

## 68. Checklist trước khi chạy production job

**Nguồn dữ liệu và memory**

- [ ] Input được đọc tuần tự/paged, không materialize toàn bộ?
- [ ] Persistence Context có flush/clear boundaries?
- [ ] Batch size tính theo tổng entity graph, không chỉ root count?
- [ ] Application không giữ references của mọi entity đã xử lý?
- [ ] Collections/lazy associations được giới hạn?
- [ ] JDBC streams/resultsets được đóng đúng scope?

**ORM và JDBC**

- [ ] Flush trước clear?
- [ ] Không còn managed references cần dùng sau clear?
- [ ] JDBC batch behavior đã xác minh?
- [ ] ID generator có ảnh hưởng batching?
- [ ] Cascade/FK ordering đúng?
- [ ] Optimistic locking/version conflicts có policy?
- [ ] Bulk DML/cache effects được kiểm tra?

**Transaction và restart**

- [ ] Transaction chunk size phù hợp?
- [ ] Partial commit có được domain chấp nhận?
- [ ] Checkpoint chỉ tiến sau commit?
- [ ] Retry/idempotency có stable keys?
- [ ] Lỗi flush dẫn đến rollback/discard Session?
- [ ] Job có thể resume sau crash?
- [ ] Connection lifetime/timeout/lock policy rõ?

**Quan sát và vận hành**

- [ ] Đo heap, allocation, GC, flush duration?
- [ ] Đo SQL/batch execution count và rows/sec?
- [ ] Đo Hikari active/pending/acquire?
- [ ] Theo dõi DB locks/IO/transaction duration?
- [ ] Logs có job/chunk/last-key/commit outcome?
- [ ] Có runbook cho failed chunk và replay?

## 69. Bài tập thực hành

1. Import 100.000 Products trong một Session không clear; đo heap và GC.
2. Thêm `flush()+clear()` mỗi 100 records; so sánh managed context và heap.
3. Giữ toàn bộ input trong List rồi đổi sang streaming reader; đo riêng hai thay đổi.
4. So sánh `hibernate.jdbc.batch_size=50` có/không, giữ flush/clear cố định.
5. Thử IDENTITY và SEQUENCE với database hỗ trợ; đo JDBC insert batches.
6. Chia transaction mỗi 1.000 records; làm chunk thứ ba fail và kiểm tra partial progress.
7. Thêm checkpoint theo ID; kill job giữa chừng và restart.
8. Tạo Order với 20 OrderLines; tính tổng entities managed mỗi chunk.
9. Clear giữa parent/child operations rồi tìm lỗi detached/transient reference.
10. Sửa entity sau clear, chứng minh không có dirty checking; thử merge và dùng object trả về.
11. So sánh keyset pagination với offset pagination ở ID lớn.
12. Dùng DTO projection để export chỉ ba cột; đo allocations.
13. Dùng StatelessSession cho rows độc lập; kiểm tra cascade/callback differences.
14. Dùng bulk HQL update và kiểm tra first-level cache stale state.
15. Dùng Spring Batch chunk step; quan sát transaction/EntityManager lifecycle và restart metadata.
16. Tạo constraint violation ở cuối chunk; xác nhận rollback và Session disposal.
17. Dùng heap dump tìm retaining path nếu heap không giảm sau clear.
18. Tạo concurrent updater để kiểm tra `@Version` conflicts giữa chunks.

## 70. Tổng kết

**Kiểm soát Persistence Context là quản lý vòng đời các entity được Hibernate theo dõi, không chỉ là bật JDBC batching.**

- `flush()` gửi pending ORM changes xuống DB **trong transaction hiện tại**.
- `clear()` detach toàn bộ managed entities khỏi context hiện tại.
- Pattern thông dụng là **flush thành công rồi clear** theo số records/entity graph có giới hạn.
- `hibernate.jdbc.batch_size` gom JDBC statements; nó **không** tự giảm số managed entities.
- Transaction chunking giới hạn commit/rollback scope; nó là quyết định atomicity khác với flush/clear.
- Streaming, keyset pagination và DTO projections giúp giới hạn dữ liệu đầu vào/đầu ra.
- `StatelessSession`, bulk HQL/SQL và JDBC batch có thể giảm ORM overhead nhưng thay đổi lifecycle/cascade/dirty-check semantics.
- Clear không giải phóng object mà application vẫn giữ; heap cần được phân tích qua retaining paths.
- Long transaction vẫn có thể giữ locks, MVCC snapshots và connection dù Persistence Context đã clear.

**Quy tắc thực hành:** Đầu tiên giới hạn input; tiếp theo giới hạn số entities managed bằng `flush()+clear()`; sau đó chọn transaction chunks theo yêu cầu atomicity/restart; cuối cùng đo heap, GC, JDBC batching, connection pool và database trên workload đại diện. Làm rõ từng boundary giúp tác vụ dài ổn định về memory mà vẫn giữ đúng semantics nghiệp vụ.
