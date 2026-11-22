# Đánh giá kích thước persistence context và chi phí theo dõi thay đổi trong JPA

Trong **Jakarta Persistence (JPA)**, khi một entity được truy xuất thông qua `EntityManager`, nó thường trở thành một đối tượng **managed** thuộc **persistence context**. Provider giữ entity identity, quản lý trạng thái đã tải, theo dõi những thay đổi đối với persistent attributes, phối hợp relationships/cascades và đồng bộ dữ liệu khi `flush()` hoặc commit. Nhờ đó, một ứng dụng chỉ cần viết:

~~~java
Product product = em.find(Product.class, productId);
product.changePrice(new BigDecimal("125000.00"));

// Provider có thể tự phát UPDATE khi flush/commit.
~~~

Cơ chế rất tiện lợi này có chi phí. Nếu truy vấn trả 100.000 entity chỉ để hiển thị ba cột, persistence context có thể giữ hàng trăm nghìn objects, identity/entry metadata, loaded-state snapshots hoặc dirty flags, collection wrappers và pending actions. Ngay cả khi không entity nào thực sự thay đổi, CPU/heap vẫn có thể bị tiêu thụ bởi object management. Đối với batch updates, một flush quá lớn hoặc một transaction sống quá lâu còn có thể gây GC pauses, slow commits, lock contention và connection pool pressure.

**Điểm cần phân biệt:** số SQL rows, số root entities trong query result, số unique managed instances, số entities dirty, số UPDATE statements và số JDBC batches **không đồng nhất**. Một context lớn có thể không sinh UPDATE, còn một query N+1 có thể phát rất nhiều SQL với context không quá lớn.

Bài học hướng dẫn đánh giá **kích thước persistence context** và **chi phí dirty checking** qua memory, allocation rate, garbage collection, flush time, SQL/JDBC và transaction metrics; đồng thời chọn DTO projection, pagination, `flush()/clear()` theo chunk, read-only optimizations hoặc bulk operations có bảo vệ tính đúng đắn.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể giải thích identity map và first-level cache; mô tả chi phí giữ managed state, dirty checking và collection tracking; phân biệt flush với commit; đo heap/GC/SQL/CPU; thiết kế batch bounded-memory; sử dụng `clear()` và `detach()` không làm mất dữ liệu; so sánh entity query với DTO projection, fetch graph, read-only queries, JDBC batching và bulk DML; cuối cùng đánh giá trade-off transaction/optimistic locking.

## 2. Persistence context và identity map

Một persistence context quản lý những entity instances theo identity. Trong cùng context:

~~~java
Product a = em.find(Product.class, 10L);
Product b = em.find(Product.class, 10L);

System.out.println(a == b); // true
~~~

Lần thứ hai thường trả chính managed instance đã được giữ trong **first-level cache (L1)**.

~~~text
EntityManager
    |
    v
Persistence context / L1
 +----------------------------------------+
 | (Product, id=10) -> Product instance A |
 | (Product, id=11) -> Product instance B |
 | (Order, id=80)   -> Order instance C   |
 | state / snapshots / changes / actions  |
 +----------------------------------------+
                   |
                   v
              flush -> SQL
                   |
                   v
                Database
~~~

**L1 không phải L2 cache.** Shared second-level cache (L2), nếu provider bật, có thể chia sẻ cached entity data giữa các contexts, nhưng mỗi entity được load vẫn có thể trở thành managed instance trong L1 của context hiện tại.

## 3. Managed khác detached như thế nào?

| Entity state | Có thuộc persistence context hiện tại? | Sửa field có thể được flush tự động? |
| --- | --- | --- |
| New/transient | Chưa | Không; cần persist phù hợp |
| Managed | Có | Có thể, qua dirty checking |
| Detached | Không | Không |
| Removed | Thuộc lifecycle remove | Provider xử lý DELETE theo transaction |

Ví dụ:

~~~java
Product p = em.find(Product.class, id);
System.out.println(em.contains(p)); // true

em.detach(p);
System.out.println(em.contains(p)); // false

p.changePrice(new BigDecimal("99.00"));
// Không tự UPDATE nếu vẫn detached.
~~~

`detach()` **không hủy Java object**. Nếu application list/cache vẫn giữ reference tới `p`, JVM vẫn thấy nó reachable và chưa thể garbage collect.

## 4. Những thành phần thường làm context tốn bộ nhớ

Provider có thể giữ:

1. Managed entity objects.
2. Entity keys/identity-map entries.
3. Loaded-state snapshots hoặc equivalent tracking structures.
4. Collection wrappers và collection snapshots.
5. Association/proxy metadata.
6. Pending insert/update/delete actions.
7. Cascade/lifecycle-related state.

~~~text
Managed Product
  +-- Fields (sku, name, price...)
  +-- Identity key and entry
  +-- Loaded-state snapshot / dirty flags
  +-- Related entity references
  +-- Collection state if loaded
~~~

**JPA không quy định một layout heap duy nhất.** Hibernate, EclipseLink và các phiên bản/enhancement settings có implementation khác nhau. Đừng coi bất kỳ con số byte/entity của một ví dụ nào là kích thước chuẩn cho mọi ứng dụng.

## 5. Dirty checking qua loaded-state snapshot

Một provider có thể lưu state khi entity được load để so sánh về sau:

~~~text
Load Product:
  Current price  = 100
  Snapshot price = 100

Application:
  product.changePrice(120)

Flush:
  Current price  = 120
  Snapshot price = 100
  -> phát hiện dirty
  -> UPDATE nếu phù hợp mapping/lifecycle
~~~

**Gọi setter không đồng nghĩa phát SQL UPDATE.** Gán một giá trị bằng giá trị cũ có thể không làm state thực sự dirty; ngược lại, sửa collection có thể gây SQL mà không đụng một scalar setter nào.

## 6. Có phải flush luôn so sánh mọi field của mọi entity?

Không có thuật toán/độ phức tạp cố định được JPA đặc tả cho mọi provider. Trong chiến lược snapshot comparison, ta có thể hình dung chi phí tăng với:

\[
N_{\text{managed}} \times A_{\text{attributes inspected}}
\]

Nhưng đây chỉ là **mô hình tư duy**. Bytecode enhancement, dirty flags, read-only entities, collection tracking, pending actions, flush mode và provider internals có thể thay đổi hành vi.

Một application có 50.000 entities managed nhưng chỉ sửa một entity có thể cần ít UPDATE, song vẫn chịu chi phí management/flush bookkeeping. Cần đo thực tế thay vì khẳng định flush luôn O(N) hoặc O(1).

## 7. Không có UPDATE vẫn có thể có chi phí tracking

~~~java
List<Product> products = em.createQuery(
        "SELECT p FROM Product p", Product.class)
    .getResultList();

// Không sửa Product.
em.flush();
~~~

SQL UPDATE count có thể bằng 0 nhưng context vẫn giữ entity objects và provider có thể thực hiện dirty checking/bookkeeping.

Vì vậy:

> SQL log không có UPDATE **không chứng minh** chi phí dirty checking hoặc memory bằng 0.

Để đánh giá, đo CPU profile, flush latency, retained heap và provider statistics cùng với SQL count.

## 8. Object graph quan trọng hơn số root results

Ví dụ:

~~~java
@Entity
class PurchaseOrder {
    @Id Long id;

    @OneToMany(mappedBy = "order")
    List<OrderLine> lines;

    @ManyToOne(fetch = FetchType.LAZY)
    Customer customer;
}
~~~

Một Order có 1.000 Lines có thể gắn với hơn 1.000 entity instances, collection wrappers và metadata. Query chỉ trả 100 Orders vẫn có thể tạo hàng nghìn managed objects nếu fetch graph bao gồm lines/customer/product.

**Không dùng `resultList.size()` làm số đo toàn bộ managed entities.** SQL JOIN có thể lặp root row, còn một managed graph có thể chứa nhiều entity types hơn root results.

## 9. JOIN FETCH giải quyết N+1 nhưng có thể tăng memory

~~~java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT DISTINCT o FROM PurchaseOrder o " +
        "JOIN FETCH o.lines",
        PurchaseOrder.class)
    .getResultList();
~~~

JOIN FETCH có thể giảm số SELECT khi duyệt OrderLines, nhưng:

- SQL trả nhiều physical rows.
- Provider materialize nhiều OrderLine entities.
- Collections được initialized.
- Context giữ graph lớn hơn.

**N+1 và context growth là hai vấn đề có liên quan nhưng khác nhau.** Fetch quá nhiều quan hệ để giảm SELECT count có thể khiến heap tăng mạnh.

## 10. Collection dirty checking

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true)
private List<OrderLine> lines = new ArrayList<>();
~~~

Khi:

~~~java
order.getLines().removeIf(OrderLine::isExpired);
~~~

provider có thể cần khởi tạo lazy collection, theo dõi membership, xác định children bị xóa và lên lịch SQL. Một collection lớn có thể đắt hơn nhiều scalar attributes.

Chi phí không chỉ đến từ `Order.price` hay `Order.status` mà còn từ **cấu trúc relationships và cascade semantics**.

## 11. Bytecode enhancement

Một số providers, ví dụ Hibernate, hỗ trợ bytecode enhancement để ghi nhận dirty fields:

~~~text
Snapshot-based:
  load -> snapshot -> flush -> compare

Enhanced dirty tracking:
  instrument field writes -> record changes
  flush -> use tracking when supported
~~~

Enhancement có thể giảm CPU ở một số workloads nhưng **không loại bỏ L1 identity map, relationship tracking hoặc tất cả pending actions**.

Mutable values được thay đổi in-place có thể có semantics khác nhau; cần kiểm thử theo provider/version. Không mặc định enhanced tracking nhận diện mọi mutation mà không cần snapshot.

## 12. @Version không thay dirty checking

~~~java
@Entity
public class Product {
    @Id Long id;
    @Version Long version;
    BigDecimal price;
}
~~~

Khi update một managed Product, SQL có thể gồm:

~~~sql
UPDATE product
SET price = ?, version = ?
WHERE id = ? AND version = ?;
~~~

`@Version` bảo vệ optimistic concurrency, còn dirty checking giúp xác định state cần cập nhật. Bỏ version để giảm một điều kiện SQL có thể làm xuất hiện lost updates.

## 13. Flush khác JDBC batching và commit

~~~text
Managed state changes
       |
       v
Dirty checking / SQL actions
       |
       v
flush() -> JDBC INSERT/UPDATE/DELETE
       |
       v
commit() hoặc rollback()
~~~

**Flush** đồng bộ pending operations xuống database nhưng chưa commit.

**JDBC batching** nhóm một số DML operations tương thích để giảm round trips.

**Commit** xác nhận transaction.

Một flush có thể phát nhiều SQL statements; một JDBC batch không tự giải phóng L1 entries; flush thành công không đồng nghĩa commit.

## 14. FlushModeType.AUTO và COMMIT

~~~java
em.setFlushMode(FlushModeType.COMMIT);
~~~

`AUTO` cho phép/đòi provider đồng bộ changes khi cần để query thấy state phù hợp theo JPA semantics, có thể gây auto-flush trước một SELECT.

`COMMIT` thay đổi thời điểm flush; nó không phải cơ chế tự động tắt dirty checking hay chuyển managed entities thành read-only DTOs.

Ví dụ:

~~~java
Product p = em.find(Product.class, id);
p.changePrice(new BigDecimal("500.00"));

List<Product> results = em.createQuery(
        "SELECT p FROM Product p WHERE p.price > :min",
        Product.class)
    .setParameter("min", new BigDecimal("400.00"))
    .getResultList();
~~~

Trong AUTO mode, một query có thể kéo theo auto-flush, khiến latency bao gồm cả UPDATE + SELECT. Khi đo query time, phải xét flush trước query.

## 15. Một transaction dài có thể tích lũy nhiều entity types

~~~java
List<Customer> customers = loadCustomers(em);
List<Product> products = loadProducts(em);
List<PurchaseOrder> orders = loadOrders(em);
~~~

Trong cùng EntityManager, các objects đã managed thường không bị tự động đẩy khỏi context chỉ vì query kế tiếp chạy:

~~~text
3.000 Customers
+ 5.000 Products
+ 8.000 Orders
+ related entities đã được load
-------------------------------
Context lớn dần
~~~

Long-lived EntityManager, transaction quá dài hoặc OSIV có thể làm lifecycle khó kiểm soát. Giữ một EntityManager trong singleton dùng giữa threads còn có nguy cơ thread safety.

## 16. Ước lượng memory và những giới hạn

Một mô hình khái niệm:

\[
M_{\text{context}} \approx M_{\text{entities}}+M_{\text{tracking}}+M_{\text{collections}}+M_{\text{actions}}+M_{\text{overhead}}
\]

Nếu một benchmark giả định đo được trung bình 1 KiB retained heap cho một Product managed và phần overhead liên quan, 100.000 Products sẽ tương ứng khoảng 97,7 MiB. **1 KiB chỉ là giả định minh họa**, không phải hằng số JPA.

Object graph, số fields, Strings, immutable references, collection snapshots, compressed object pointers, provider version và JDK làm footprint khác nhau đáng kể. Muốn capacity planning phải đo mapping/workload thật.

## 17. Metrics quan trọng

| Metric | Đo điều gì? |
| --- | --- |
| Unique entities loaded | Quy mô state đang quản lý |
| Query root/result row count | SQL/data shape, không là live context size |
| Retained heap / peak heap | Memory pressure |
| Allocation rate | Tốc độ tạo objects |
| GC frequency và pause | Độ trễ JVM |
| Flush duration | Dirty tracking + JDBC + DB waits |
| SQL SELECT/UPDATE count | N+1, DML volume |
| JDBC batch count | SQL batching efficiency |
| Transaction duration | Lock/connection lifetime |
| Throughput rows/s | Kết quả nghiệp vụ |
| p95/p99 latency | Trải nghiệm API/job |
| DB lock waits | Concurrency pressure |

**Không có một metric duy nhất đủ để kết luận bottleneck.**

## 18. API JPA có đếm live managed entities không?

JPA có:

~~~java
boolean managed = em.contains(product);
~~~

Nhưng API này chỉ kiểm tra **một object instance**. JPA chuẩn không có method portable đơn giản như `em.getManagedEntityCount()`.

Đếm `em.contains()` trên một List chỉ cho biết những objects trong List ấy, không bao trùm entities được fetch qua associations.

Provider-specific persistence-context statistics có thể được dùng ở test/diagnostics, nhưng tránh business logic phụ thuộc vào internal APIs có thể thay đổi theo provider version.

## 19. Hibernate Statistics

Với Hibernate:

~~~java
SessionFactory sf =
    emf.unwrap(SessionFactory.class);

Statistics stats = sf.getStatistics();

long loads = stats.getEntityLoadCount();
long updates = stats.getEntityUpdateCount();
long flushes = stats.getFlushCount();
long queries = stats.getQueryExecutionCount();
~~~

Một cấu hình ví dụ:

~~~properties
hibernate.generate_statistics=true
~~~

Các counters có thể thuộc phạm vi **toàn SessionFactory**, không riêng một EntityManager/request. Entity load count cũng **không bằng live managed entity count**, còn query execution count không nhất thiết bằng mọi JDBC statement. Nên đo trên benchmark cô lập hoặc tracing có scope rõ.

## 20. Đo flush wall time

~~~java
long start = System.nanoTime();
em.flush();
long elapsedNanos = System.nanoTime() - start;

log.debug(
    "flush_ms={}",
    elapsedNanos / 1_000_000.0
);
~~~

Thời gian này có thể gồm provider dirty checking, SQL action scheduling, JDBC network, database execution và lock waits.

Muốn tách CPU tracking khỏi SQL time, kết hợp **JFR/CPU profiler, JDBC metrics, database slow-query/lock logs, heap/GC và provider statistics**. Không kết luận từ flush wall time một mình.

## 21. Heap dump và Java Flight Recorder

Khi nghi ngờ memory pressure, cần xem **ai đang giữ reference**, không chỉ used heap tại một thời điểm.

Heap dump có thể cho thấy:

~~~text
EntityManager
  -> PersistenceContext
    -> IdentityMap
      -> Managed Product

Application cache
  -> HashMap
    -> Product instances

Job coordinator
  -> ArrayList
    -> Product instances của các pages cũ
~~~

Nếu `em.clear()` đã bỏ references từ persistence context nhưng job vẫn giữ một ArrayList lớn, GC không thể thu hồi Product objects.

**Java Flight Recorder (JFR)** có thể giúp quan sát allocations, CPU samples, GC pauses và thread activity. Dùng cùng spans đánh dấu query/flush/commit để xem chi phí thực nằm ở Java tracking, DB IO hay garbage collection.

## 22. GC không tự xử lý persistence context

Hai cơ chế khác nhau:

~~~text
em.clear()/detach()/close()
  -> Bỏ quản lý hoặc kết thúc context.

Garbage Collector
  -> Thu hồi objects không còn reachable.
~~~

`System.gc()` không thay `em.clear()`, và `em.clear()` cũng không bảo đảm used heap giảm ngay lập tức. JVM có thể chưa thu gom hoặc vẫn giữ heap committed.

### Tại sao memory sau clear chưa giảm?

- Application List vẫn giữ entities.
- Static cache giữ reference.
- Thread-local hoặc queue giữ graph.
- JIT/GC chưa thu gom unreachable objects.
- L2 cache vẫn giữ cached data riêng.
- Other allocations che hiệu quả vừa giải phóng.

Hãy dùng retained heap/dominator tree thay vì một phép so used heap duy nhất.

## 23. Batch insert ngây thơ

Ví dụ:

~~~java
tx.begin();

for (int i = 0; i < 100_000; i++) {
    em.persist(createProduct(i));
}

tx.commit();
~~~

Một context có thể phải giữ nhiều managed Products, pending insert actions và cascading state cho đến flush/commit. Tùy provider/ID strategy, SQL INSERT có thể xảy ra ở những thời điểm khác nhau.

Với 100 rows nhỏ, code trên có thể hoàn toàn ổn. Với 100.000 entities hoặc graph phức tạp, đây là một ứng viên cần **memory và flush profiling**, không nên chỉ nhìn tốc độ vòng for.

## 24. Batch insert: flush và clear theo chunk

Mẫu resource-local:

~~~java
public void importProducts(
        EntityManagerFactory emf,
        List<NewProductData> inputs) {

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();
    int chunkSize = 100;

    try {
        tx.begin();

        for (int i = 0; i < inputs.size(); i++) {
            NewProductData data = inputs.get(i);

            em.persist(new Product(
                data.sku(), data.price()
            ));

            if ((i + 1) % chunkSize == 0) {
                em.flush();
                em.clear();
            }
        }

        em.flush();
        em.clear();
        tx.commit();

    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            try {
                tx.rollback();
            } catch (RuntimeException rollbackError) {
                ex.addSuppressed(rollbackError);
            }
        }
        throw ex;
    } finally {
        em.close();
    }
}
~~~

Giả định `NewProductData` là DTO/record đầu vào; `Product` có constructor và ID mapping hợp lệ.

### Ý nghĩa

- `persist()` đưa từng Product vào managed state.
- `flush()` đồng bộ pending actions trong transaction.
- `clear()` detach mọi managed instances, giới hạn context accumulation.
- `commit()` xác nhận transaction.

### Flush/clear có tạo nhiều commits không?

Không. Đoạn code trên chỉ có **một commit cuối cùng**. Flush giúp bounded context, nhưng transaction vẫn có thể giữ locks/resources lâu nếu job lớn.

## 25. Clear trước flush có thể làm mất thay đổi

Ví dụ sai:

~~~java
tx.begin();

Product p = em.find(Product.class, id);
p.changePrice(new BigDecimal("199.00"));

em.clear();
tx.commit();
~~~

`clear()` detach Product đang managed và thay đổi chưa flush có thể không được đồng bộ.

### Thứ tự đúng với chunk ghi

~~~java
p.changePrice(new BigDecimal("199.00"));

em.flush();
em.clear();

tx.commit();
~~~

**Flush không có nghĩa commit**. Nếu transaction rollback sau nhiều chunks đã flush+clear, database vẫn rollback các operations thuộc transaction ấy.

## 26. Clear() detach toàn context, không chỉ page hiện tại

Giả sử:

~~~text
Service load Order managed
  -> sửa shippingAddress
  -> Query 10.000 Product entities
  -> Repository gọi em.clear()
  -> Service tiếp tục sửa Order
  -> commit
~~~

`clear()` detach **cả Order** và các Product trong context. Thay đổi Order sau clear có thể không được dirty tracked.

**Không đặt `em.clear()` bí mật trong một generic repository**. Đó là lifecycle decision của transaction owner/job coordinator.

Nếu chỉ cần Product để đọc, DTO projection có thể tránh việc nạp chúng thành managed entities ngay từ đầu.

## 27. Detach() có chọn lọc

~~~java
Product p = em.find(Product.class, id);
em.detach(p);
~~~

`detach(p)` loại p khỏi context; `clear()` detach tất cả.

Nếu `CascadeType.DETACH` được cấu hình trên association, detach có thể cascade theo mapping.

### Khi nào hữu ích?

Một job đọc từng entity nhưng không cần sửa có thể detach sau khi xử lý để không tích lũy managed state, miễn là application không tiếp tục truy cập lazy relationships cần context.

### Khi nào không nên?

Nếu caller còn định sửa p rồi trông chờ flush, detach làm biến mất điều đó. Khi cần update, hãy giữ p managed trong chunk hoặc áp thay đổi vào managed instance mới một cách rõ ràng.

## 28. Close EntityManager và object lifetime

Với application-managed EntityManager:

~~~java
EntityManager em = emf.createEntityManager();
try {
    // Work
} finally {
    em.close();
}
~~~

EntityManager closure kết thúc scope quản lý theo JPA rules, nhưng entity objects mà Java code đang giữ có thể tiếp tục sống dưới dạng detached.

Với Spring/JTA, EntityManager thường do framework/container sở hữu; không gọi `close()` trên injected container-managed EntityManager chỉ để “giảm heap nhanh”.

### Đừng giữ EM như singleton

EntityManager không được thiết kế để chia sẻ tùy tiện giữa threads. Giữ một EM dài hạn vừa có memory/stale state hazards vừa khó quản lý transaction boundaries.

## 29. Pagination không tự clear L1

~~~java
for (int pageIndex = 0;
        pageIndex < 100;
        pageIndex++) {

    List<Product> page = em.createQuery(
            "SELECT p FROM Product p ORDER BY p.id",
            Product.class)
        .setFirstResult(pageIndex * 1000)
        .setMaxResults(1000)
        .getResultList();

    process(page);
}
~~~

Mỗi query chỉ trả tối đa 1.000 Products, nhưng nếu cùng một EntityManager tiếp tục quản lý tất cả pages cũ, L1 vẫn có thể tăng gần 100.000 managed instances.

### Các lựa chọn

- Dùng DTO projection khi chỉ đọc.
- Flush/clear sau mỗi chunk khi cập nhật.
- Detach các objects không còn cần quản lý.
- Dùng transaction/context theo chunk nếu atomicity cho phép.

**Page size của result query khác managed context size.**

## 30. Không gom mọi page vào một List lớn

Ví dụ:

~~~java
List<Product> all = new ArrayList<>();

while (hasMorePages()) {
    List<Product> page = loadNextPage();
    all.addAll(page);
    em.clear();
}
~~~

`em.clear()` không giải phóng objects nếu `all` vẫn giữ references.

Hướng phù hợp:

~~~java
while (hasMorePages()) {
    List<Product> page = loadNextPage();
    process(page);
    em.flush();
    em.clear();

    // Không lưu page vào collection dài hạn.
}
~~~

Đối với đọc thuần, có thể không cần `flush()`; không gọi flush nếu không có transaction hoặc không có pending changes. Ví dụ trên giả định có transaction ghi và process có thể thay đổi entities.

## 31. Keyset pagination cho batch update

Nếu ID là Long và có stable order:

~~~java
public int updatePages(
        EntityManager em,
        BigDecimal factor,
        int size) {

    long lastId = 0L;
    int count = 0;

    while (true) {
        List<Product> page = em.createQuery(
                "SELECT p FROM Product p " +
                "WHERE p.id > :lastId " +
                "ORDER BY p.id",
                Product.class)
            .setParameter("lastId", lastId)
            .setMaxResults(size)
            .getResultList();

        if (page.isEmpty()) {
            break;
        }

        for (Product p : page) {
            p.changePrice(
                p.getPrice().multiply(factor)
            );
        }

        lastId =
            page.get(page.size() - 1).getId();
        count += page.size();

        em.flush();
        em.clear();
    }

    return count;
}
~~~

**Điều kiện:** Method được gọi trong transaction active; Product có getters/domain methods và ID Long; input factor, monetary rounding và nghiệp vụ được validate riêng. Trong multi-tenant application phải thêm predicates tenant/authorization.

### Vì sao keyset thường tốt hơn OFFSET lớn?

Với index phù hợp, `WHERE id > :lastId ORDER BY id` có thể tránh việc database phải bỏ qua quá nhiều rows như OFFSET lớn.

### Nhưng keyset không tự đảm bảo snapshot

Nếu rows được thêm/sửa trong lúc job chạy, tập phù hợp có thể thay đổi. Dùng max ID/cut-off, transaction isolation, checkpoint hoặc job marker khi cần một tập cố định.

## 32. Entity query so với DTO projection

Entity:

~~~java
List<Product> products = em.createQuery(
        "SELECT p FROM Product p", Product.class)
    .getResultList();
~~~

DTO constructor projection:

~~~java
List<ProductRow> rows = em.createQuery(
        "SELECT NEW com.example.report.ProductRow(" +
        "p.id, p.sku, p.price) " +
        "FROM Product p",
        ProductRow.class)
    .getResultList();
~~~

DTO có thể chỉ chứa những fields ứng dụng cần; provider không phải tạo managed Product instance/dirty tracking cho từng row chỉ để tính báo cáo.

| Khía cạnh | Entity result | DTO result |
| --- | --- | --- |
| Managed identity | Có | Không cho Product |
| Dirty checking | Có thể | Không cho DTO |
| Lazy associations | Có thể load | Chỉ dữ liệu query yêu cầu |
| L1 tracking overhead | Có | Tránh được phần Product-managed tracking |
| Có thể sửa qua domain method/flush | Có | Không trực tiếp |
| Read-only report lớn | Cần paging/clear | Thường phù hợp hơn |

**DTO cũng là Java object và tốn memory.** Nếu ứng dụng giữ một triệu DTO trong list, vẫn có thể OOM; cần paging hoặc output streaming có kiểm soát.

## 33. Spring @Transactional(readOnly=true)

~~~java
@Transactional(readOnly = true)
public List<Product> listProducts() {
    return em.createQuery(
        "SELECT p FROM Product p", Product.class)
      .getResultList();
}
~~~

`readOnly=true` có thể làm Spring/provider điều chỉnh flush mode hoặc dirty tracking behavior theo tích hợp/version; nhưng nó **không tự biến entity query thành DTO projection**.

Một read-only transaction vẫn có thể tạo nhiều managed entity objects. Mức snapshot optimization phải xác minh bằng profiling và provider documentation.

### Không dùng readOnly như bảo mật writes

Read-only transaction hint không thay authorization/domain constraints. Có provider/database có thể từ chối writes, có nơi behavior khác; đừng coi nó là cơ chế bảo vệ dữ liệu duy nhất.

## 34. Hibernate-specific read-only entity loading

Ví dụ với Hibernate:

~~~java
Session session = em.unwrap(Session.class);
session.setDefaultReadOnly(true);
~~~

Khi phù hợp, Hibernate có thể không giữ một số loaded-state snapshots/dirty checking cho newly loaded read-only entities, giúp giảm overhead.

### Giới hạn

- `Session` không phải API JPA portable.
- Không tự xóa identity map.
- Không bảo đảm mọi collection/cascade side effects biến mất.
- Nếu sau đó sửa read-only entity, changes có thể không được đồng bộ như managed writable entity.
- Behavior với entity đã managed trước đó có thể khác entity mới được load.

Provider-specific query read-only hints cũng cần kiểm chứng theo phiên bản Hibernate.

## 35. FlushModeType.COMMIT khác read-only

~~~java
em.setFlushMode(FlushModeType.COMMIT);
~~~

JPA COMMIT mode chủ yếu điều chỉnh **flush timing**, không tự biến loaded entities thành readonly state hoặc loại bỏ mọi snapshots.

| Cơ chế | Mục tiêu chính |
| --- | --- |
| FlushModeType.COMMIT | Thời điểm flush/query visibility |
| Spring readOnly=true | Transaction/provider hints |
| Hibernate Session read-only | Provider-specific tracking behavior |
| DTO projection | Không tạo managed entity khi chỉ cần fields |
| detach/clear | Bỏ context management |

Không thay các cơ chế này cho nhau khi chưa hiểu use case.

## 36. Stream<Entity> không phải zero-memory

~~~java
try (Stream<Product> stream = em.createQuery(
        "SELECT p FROM Product p",
        Product.class).getResultStream()) {

    stream.forEach(this::processProduct);
}
~~~

Tùy provider/driver:

- ResultSet có thể được buffer.
- JDBC cursor/connection có thể được giữ.
- Materialized Product entities vẫn được managed.
- L1 vẫn có thể tăng.
- Lazy relationship access có thể làm graph lớn.

Streaming giúp một số dạng result buffering nhưng **không tự tắt dirty tracking**. Để đọc rất lớn, cân nhắc DTO streaming/chunked query và kiểm soát resources/transactions.

## 37. Hibernate StatelessSession

Hibernate có `StatelessSession` cho những workloads cần thao tác dữ liệu mà không dùng first-level stateful persistence context/automatic dirty checking như Session thông thường.

Lợi ích tiềm năng: tránh identity-map/tracking overhead khi batch/ETL thích hợp.

Nhưng đây là **provider-specific API**, không phải một EntityManager nhanh hơn với toàn bộ semantics y hệt:

- Cascades có thể khác.
- Lifecycle callbacks không tương đương.
- Dirty checking không tự diễn ra.
- Cache và explicit operations có semantics riêng.

Nếu business dựa vào orphan removal, callbacks, version checks hoặc entity graph lifecycle, phải thiết kế lại đường xử lý và kiểm thử kỹ.

## 38. JDBC batching và Hibernate configuration

Ví dụ:

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
~~~

JDBC batching giúp gom compatible DML statements, giảm round trips, nhưng **không tự clear persistence context**.

### IDENTITY ảnh hưởng batching

Với một số Hibernate versions/configurations, `GenerationType.IDENTITY` làm insert batching kém hiệu quả vì generated ID cần nhận về tại INSERT.

### Các kích thước độc lập

| Kích thước | Vai trò |
| --- | --- |
| JDBC fetch size | Buffering của SELECT |
| Query page size | Số rows/results một lần |
| JDBC batch size | Grouping DML |
| Flush/clear chunk size | Bounded L1 state |
| Transaction chunk size | Atomicity/lock lifetime |

Đừng chỉ dùng một giá trị `batchSize` cho tất cả rồi nghĩ chúng có cùng ý nghĩa.

## 39. Chọn chunk size như thế nào?

Những giá trị thử nghiệm:

~~~text
25, 50, 100, 250, 500, 1000
~~~

Chunk quá nhỏ: nhiều flush calls, overhead tăng.

Chunk quá lớn: memory spikes, flush latency/GC cao.

Đánh giá bằng:

- Heap peak và allocation rate.
- Flush p95.
- JDBC round trips/batches.
- End-to-end throughput.
- Transaction duration/DB locks.

Không có chunk size tốt nhất độc lập với entity graph, driver, ID generation và database workload.

## 40. Flush chunk và transaction chunk

**Một transaction cho toàn job:**

~~~text
BEGIN
  Process 100 entities -> flush/clear
  Process 100 entities -> flush/clear
  ...
COMMIT
~~~

Giảm context memory nhưng transaction vẫn dài.

**Một transaction mỗi chunk:**

~~~text
BEGIN -> Process 1000 -> COMMIT
BEGIN -> Process 1000 -> COMMIT
...
~~~

Giảm transaction lifetime nhưng có **partial commits**. Cần checkpoint, restart và idempotency.

Không chia một nghiệp vụ phải atomic thành nhiều commits chỉ vì muốn giảm heap.

## 41. Checkpoint và restart

Một batch job:

~~~text
Read checkpoint
    |
    v
Fetch page by stable id
    |
    v
Process/validate
    |
    v
Flush + commit
    |
    v
Save checkpoint
    |
    v
Next page
~~~

### Race khi checkpoint

Nếu lưu checkpoint trước commit và transaction rollback, job có thể **bỏ qua rows chưa xử lý**.

Nếu commit thành công rồi crash trước khi lưu checkpoint, job có thể xử lý lại cùng rows.

Cần dùng idempotency marker, unique constraints, checkpoint transactional cùng resource khi phù hợp, hoặc outbox/job state machine.

## 42. Bulk JPQL UPDATE có thể tránh entity materialization

~~~java
int changed = em.createQuery(
        "UPDATE Product p " +
        "SET p.active = false " +
        "WHERE p.lastSeenAt < :cutoff")
    .setParameter("cutoff", cutoff)
    .executeUpdate();
~~~

Nếu chỉ cần đổi một scalar field cho nhiều rows, bulk DML có thể tránh load từng Product và dirty tracking chúng.

### Nhưng bulk DML có trade-off

- Bypass per-entity callbacks/validation tương ứng.
- Không tự có cùng @Version handling như managed update.
- Có thể làm L1/L2 cached state stale.
- Cần active transaction.
- Cần tenant/authorization predicates.

Không dùng bulk DML nếu nghiệp vụ yêu cầu gọi domain method/check trên từng entity mà query không thay thế được.

## 43. Native SQL/ETL cho dữ liệu rất lớn

Một migration hàng triệu rows có thể phù hợp native SQL, stored procedure hoặc ETL thay vì materialize entity graph.

Tuy nhiên:

- DML vẫn cần transaction đúng.
- Database constraints/locks cần được bảo vệ.
- Native SQL bypass JPA lifecycle.
- Version/caches có thể cần xử lý riêng.
- Partial success/restart cần thiết kế rõ.

**Nhanh hơn nhưng làm sai business invariant không phải tối ưu hợp lệ.**

## 44. Merge một detached graph lớn

~~~java
Order managed = em.merge(detachedOrder);
~~~

`merge()` copy state vào managed instance và có thể traverse graph/cascade MERGE, load counterparts, tạo tracked state và xử lý collections.

Nếu API chỉ muốn sửa địa chỉ:

~~~java
Order order = em.find(Order.class, id);
order.changeShippingAddress(nextAddress);
~~~

có thể rõ hơn, giới hạn graph và bảo vệ domain invariants. Không merge nguyên entity do client gửi với mong đợi provider tự giải quyết tenant/authorization/version.

## 45. Tối ưu theo một số đo duy nhất rất nguy hiểm

| Chỉ số được tối ưu | Rủi ro bị bỏ sót |
| --- | --- |
| Ít SQL statements | JOIN FETCH tạo graph cực lớn |
| Ít managed entities | Native/bulk bỏ lifecycle rules |
| Flush nhanh | Database lock waits/commit chậm |
| Heap thấp | Quá nhiều nhỏ transactions/round trips |
| Throughput cao | Partial commits, mất @Version/validation |
| Query latency thấp | Connection pool/GC ảnh hưởng request khác |

Một giải pháp tốt phải đồng thời thỏa **business correctness, bounded memory, throughput và operational stability**.

## 46. Quy trình benchmark có kiểm soát

Một thí nghiệm đánh giá persistence context nên ghi rõ:

~~~text
Database: cùng engine/version
JDBC driver: cùng version
JPA provider: cùng version
JDK: cùng phiên bản
Heap/GC: cùng cấu hình
Dataset: cùng số rows và distribution
Indexes: giống nhau
Transaction isolation: giống nhau
Warm-up: đủ để ổn định phần JIT/cache
Runs: nhiều lần, lấy median/p95
~~~

So sánh:

**Case A:** load toàn bộ managed entities, mutate, commit một lần.

**Case B:** query từng page rồi mutate + flush/clear mỗi 100.

**Case C:** chỉ đọc qua DTO projection, có paging.

**Case D:** bulk DML khi business cho phép.

Không coi C là phương án “nhanh hơn” A cho cùng nhiệm vụ **ghi**, vì C không cập nhật dữ liệu. Với D, phải nêu rõ các callbacks, version và validation bị bypass nếu có.

### Các kết quả cần công bố

Throughput, peak memory, allocations, GC pauses, SQL count/timing, flush p50/p95, commit latency, transaction duration và **database state correctness**. Mỗi số phải gắn với môi trường/test configuration.

## 47. Tách CPU dirty checking khỏi JDBC latency

Một phép thử:

1. Tạo fixture Product đã commit.
2. Mở EntityManager mới và transaction phù hợp.
3. Load N managed Products.
4. Không thay đổi gì.
5. Đo `em.flush()` và quan sát SQL UPDATE count.
6. Lặp lại với những giá trị N khác nhau.
7. Thu CPU profiling và GC metrics.

Nếu SQL UPDATE count = 0 nhưng flush CPU tăng rõ theo số entities, đây có thể là bằng chứng tracking/bookkeeping overhead của provider đang dùng.

### Không khẳng định một định luật O(N)

Số đo có thể bị ảnh hưởng bởi collection initialization, enhancement, JIT, heap pressure và provider flush optimizations. Diễn giải kết quả như một **đặc tính workload**, không phải quy tắc chung của JPA.

## 48. Integration test: clear làm entity detached

Ví dụ JUnit với EntityManagerFactory thật:

~~~java
@Test
void clearDetachesManagedProduct() {
    EntityManager em = emf.createEntityManager();
    try {
        Product product =
            em.find(Product.class, productId);

        assertTrue(em.contains(product));

        em.clear();

        assertFalse(em.contains(product));
    } finally {
        em.close();
    }
}
~~~

Test trên xác nhận lifecycle semantics, **không phải test heap**. Object Product vẫn được local variable `product` giữ reference, nên không thể yêu cầu JVM ngay lập tức thu hồi nó.

## 49. Integration test: flush trước clear

Một fixture đã commit, rồi:

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product product =
        em.find(Product.class, productId);

    product.changePrice(
        new BigDecimal("199.00")
    );

    em.flush();
    em.clear();

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Mở **EntityManager mới** để đọc lại row và xác nhận price đã commit.

### Test trường hợp clear trước flush

Tạo transaction/fixture độc lập, sửa managed entity rồi clear không flush, commit và đọc lại DB. Điều này giúp hiểu nguy cơ mất pending changes nếu detach trước synchronization.

Không dùng production data để cố ý tạo tình huống bỏ thay đổi.

## 50. Integration test: pagination không tự detach page trước

~~~java
List<Product> first = em.createQuery(
        "SELECT p FROM Product p ORDER BY p.id",
        Product.class)
    .setMaxResults(1000)
    .getResultList();

List<Product> second = em.createQuery(
        "SELECT p FROM Product p ORDER BY p.id",
        Product.class)
    .setFirstResult(1000)
    .setMaxResults(1000)
    .getResultList();

assertTrue(em.contains(first.get(0)));
assertTrue(em.contains(second.get(0)));
~~~

Đây là phép kiểm tra hai entity instances, không phải phép đo portable tổng số managed entities trong context.

Sau `em.clear()`, cả hai không còn managed, nhưng Java lists vẫn giữ references tới chúng.

## 51. Integration test: JDBC batching có thật không?

Chỉ bật:

~~~properties
hibernate.jdbc.batch_size=50
~~~

không đủ chứng minh driver đang batch hiệu quả.

Hãy đo:

- JDBC batch execution counters/timing.
- SQL statements thực tế.
- INSERT/UPDATE ordering.
- ID generation strategy.
- Provider logs/driver behavior.

Với `IDENTITY`, batching có thể bị hạn chế trong một số Hibernate configurations. Nếu đổi ID strategy, cần đánh giá cả correctness và database schema, không chỉ benchmark.

## 52. Integration test: read-only optimization

Hai workloads:

1. Normal entity query trong transaction.
2. Provider-specific read-only entity query hoặc transaction hint.

Giữ cùng dataset, SQL shape, query result count, JDK/GC/driver.

Đo:

- Loaded/managed objects.
- Retained heap/allocations.
- Flush CPU.
- Query duration.
- GC pauses.

### Vì sao cần kiểm tra tính đúng?

Với Hibernate read-only entity semantics, application không nên mutate entity rồi mặc định flush sẽ ghi. Phải phân tách read use case và write use case rõ.

## 53. Integration test: DTO projection

Entity query:

~~~java
List<Product> entities = em.createQuery(
        "SELECT p FROM Product p",
        Product.class)
    .setMaxResults(5000)
    .getResultList();
~~~

DTO query:

~~~java
List<ProductRow> rows = em.createQuery(
        "SELECT NEW com.example.report.ProductRow(" +
        "p.id, p.sku, p.price) FROM Product p",
        ProductRow.class)
    .setMaxResults(5000)
    .getResultList();
~~~

Đo query duration, allocations, memory retained, selected columns và provider tracking behavior.

**Không đánh đồng DTO tối ưu hơn chỉ vì result object nhỏ hơn**: phần dữ liệu được SELECT từ DB cũng có thể ít hơn. Đây là lợi ích hợp lệ nhưng phải mô tả đúng nguồn khác biệt.

## 54. Integration test: transaction chunk và checkpoint

Kịch bản job 10.000 Products:

~~~text
Chunk 1: 1..1000, COMMIT
Chunk 2: 1001..2000, COMMIT
Chunk 3: giả lập lỗi giữa chừng, ROLLBACK
Restart:
  đọc checkpoint cuối đã commit
  xử lý lại an toàn
~~~

Test:

- Row state của các chunk đã commit.
- Chunks rollback không có partially committed state ngoài protocol.
- Checkpoint không vượt quá trạng thái đã commit.
- Retry không tạo duplicate effects.
- Tenant scope không bị bỏ sót.

Đây là phép kiểm thử correctness, song song với benchmark throughput/memory.

## 55. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Khả năng | Cách xác nhận |
| --- | --- | --- |
| Heap tăng qua pages | L1 giữ entities cũ | contains sample, provider diagnostics, heap dump |
| Heap tăng cả sau clear | List/cache giữ references | Dominator/retaining paths |
| Flush tăng thời gian dù không UPDATE | Tracking/flush bookkeeping | CPU profiler + SQL count |
| SQL SELECT tăng khi duyệt relation | N+1 | SQL trace/query count |
| Một SELECT trả ít roots nhưng memory cao | JOIN FETCH graph lớn | Actual SQL rows và loaded entities |
| Rất nhiều INSERT round trips | Batching/IDENTITY limitations | JDBC metrics, ID strategy |
| Clear rồi update mất tác dụng | Entity đã detached | em.contains, DB reread |
| Batch xử lý nhanh nhưng DB lock lâu | Transaction quá dài | Transaction duration/DB lock waits |
| Dùng readOnly mà DB không cập nhật | Provider read-only tracking | Read-only semantics |
| DTO result vẫn OOM | Giữ toàn bộ DTO trong List | Heap retaining paths |
| Stream lớn vẫn tăng L1 | Entities vẫn managed | Context diagnostics |
| Bulk UPDATE nhanh nhưng cache stale | Bypass managed state synchronization | New EM/refresh/cache metrics |
| Commit theo chunk bỏ rows | Checkpoint/ordering lỗi | Restart integration test |
| Mất optimistic checks | Bulk SQL bypass @Version | Concurrent update tests |
| GC pauses lớn | Object graph/allocations cao | JFR/GC logs |

## 56. Cách tối ưu không gây mất consistency

Quy trình:

1. Xác định workload **đọc hay ghi**.
2. Nếu chỉ đọc scalar fields, cân nhắc DTO projection.
3. Nếu cần per-entity domain logic, giữ managed processing theo chunk.
4. Chọn flush+clear boundary rõ.
5. Quyết định transaction chunk theo atomicity, không theo RAM đơn thuần.
6. Giữ optimistic locking/tenant authorization và database constraints.
7. Tính toán tác động L1/L2 caches khi bulk/native operations.
8. Có checkpoint/idempotency khi commit từng chunk.
9. Đo memory, CPU, SQL và transaction metrics.
10. So sánh database committed state từ một context độc lập.

## 57. Sơ đồ chọn kỹ thuật

~~~text
                   Workload
                      |
              +-------+-------+
              |               |
             Read            Write
              |               |
       Chỉ cần vài fields?    Cần entity lifecycle?
            /    \                /      \
           Có    Không           Có      Không
            |      |              |        |
            v      v              v        v
        DTO/paging Entity     Managed    Bulk DML
                   fetch       chunk      / ETL
                              flush/clear
                                  |
                                  v
                        Chọn transaction scope
                           /          \
                        Atomic       Partial commits
                         all            |
                          |             v
                          v         Checkpoint /
                       Một TX       idempotency
~~~

Điều kiện của nhánh bulk là **business rules thực sự cho phép bỏ per-entity lifecycle** hoặc đã có cơ chế tương đương rõ ràng.

## 58. Bài tập thực hành

### Bài 1 — Identity map

Vì sao hai lần `em.find(Product.class, 10L)` trong cùng context thường trả cùng instance?

**Gợi ý:** L1 identity map.

### Bài 2 — Context size

Một query trả 1.000 Orders, mỗi Order có 10 Lines fetch eager. Có chắc chỉ 1.000 managed entities không?

**Gợi ý:** không; OrderLines cũng có thể managed.

### Bài 3 — Snapshot

Loaded-state snapshot được dùng để làm gì?

**Gợi ý:** đối chiếu với current state để nhận diện dirty changes.

### Bài 4 — UPDATE count

Không có SQL UPDATE có nghĩa flush CPU bằng 0 không?

**Gợi ý:** không.

### Bài 5 — Enhancement

Bytecode enhancement có tự bỏ identity map không?

**Gợi ý:** không.

### Bài 6 — Collections

Vì sao remove phần tử trong `@OneToMany(orphanRemoval=true)` tốn hơn một scalar assignment?

**Gợi ý:** collection tracking, cascade/orphan operations.

### Bài 7 — Flush/commit

`em.flush()` thành công nghĩa transaction đã commit chưa?

**Gợi ý:** chưa.

### Bài 8 — AUTO

Vì sao một SELECT trong AUTO flush mode có thể thực hiện thêm SQL UPDATE?

**Gợi ý:** auto-flush nhằm bảo đảm query semantics.

### Bài 9 — Clear

Sau `em.clear()`, managed entities có trạng thái gì?

**Gợi ý:** detached.

### Bài 10 — Pending changes

Tại sao phải flush trước clear trong batch ghi?

**Gợi ý:** tránh bỏ unflushed changes.

### Bài 11 — Java references

Vì sao clear xong mà một global List vẫn khiến Product objects chiếm heap?

**Gợi ý:** List giữ references.

### Bài 12 — Detach

Sửa một detached entity có tự được cập nhật tại commit không?

**Gợi ý:** không.

### Bài 13 — L2 cache

`em.clear()` có tự evict mọi entry của L2 cache không?

**Gợi ý:** không.

### Bài 14 — DTO

Vì sao DTO constructor projection thường giảm L1 tracking?

**Gợi ý:** không cần materialize managed Product.

### Bài 15 — Read-only

Spring `@Transactional(readOnly=true)` có tự chuyển entity result thành DTO không?

**Gợi ý:** không.

### Bài 16 — Hibernate

`Session.setDefaultReadOnly(true)` có phải Jakarta Persistence API portable không?

**Gợi ý:** không.

### Bài 17 — Streaming

`getResultStream()` có tự detach entity sau khi phần tử được xử lý không?

**Gợi ý:** không mặc định.

### Bài 18 — Pagination

`setMaxResults(100)` có tự giới hạn L1 còn 100 entities không?

**Gợi ý:** không.

### Bài 19 — Keyset

Keyset theo id có tự tạo snapshot xuyên nhiều transactions không?

**Gợi ý:** không.

### Bài 20 — JDBC batching

`hibernate.jdbc.batch_size=50` có tự gọi `em.clear()` sau mỗi 50 entities không?

**Gợi ý:** không.

### Bài 21 — Chunk commits

Flush+clear 20 lần trong một transaction có tạo 20 commits không?

**Gợi ý:** không.

### Bài 22 — Checkpoint

Commit chunk 3 thành công rồi crash trước lưu checkpoint cần xử lý thế nào?

**Gợi ý:** idempotent retry hoặc checkpoint atomic.

### Bài 23 — Bulk update

Vì sao bulk JPQL UPDATE có thể giảm tracking overhead nhưng bỏ qua @PreUpdate?

**Gợi ý:** không xử lý từng managed entity theo lifecycle.

### Bài 24 — Concurrency

Có nên bỏ `@Version` chỉ để một SQL UPDATE ngắn hơn không?

**Gợi ý:** không nếu cần optimistic concurrency.

### Bài 25 — SQL count

N+1 và dirty checking có phải cùng loại bottleneck không?

**Gợi ý:** không; một bên SQL round trips, một bên managed state/tracking.

### Bài 26 — Memory metrics

Kể bốn metrics hữu ích khi đánh giá context growth.

**Gợi ý:** retained heap, allocation rate, GC pauses, live managed count estimate, flush duration.

### Bài 27 — Provider statistics

`Statistics.getEntityLoadCount()` có bằng số live entities của một EntityManager không?

**Gợi ý:** không.

### Bài 28 — StatelessSession

Có thể dùng Hibernate StatelessSession thay EntityManager mà giữ nguyên mọi callback/cascade behavior không?

**Gợi ý:** không.

### Bài 29 — Benchmark

Một bulk SQL test nhanh hơn per-entity test nhưng bỏ domain validations. Kết luận “tối ưu cùng nghiệp vụ” có hợp lệ không?

**Gợi ý:** không; workloads không tương đương.

### Bài 30 — Thiết kế hoàn chỉnh

Thiết kế job cập nhật 2 triệu Products theo tenant, gồm query/page strategy, transaction chunk, flush/clear, checkpoint, error handling và metrics.

**Gợi ý:** stable keyset, tenant scoping, bounded managed graph, version policy, idempotent checkpoints và profiling đầy đủ.

## 59. Bảng ghi nhớ nhanh

| Khái niệm | Ghi nhớ |
| --- | --- |
| Persistence context | Quản lý identity, lifecycle và state |
| L1 cache | Gắn với context |
| L2 cache | Shared cache riêng, nếu bật |
| Managed entity | Có dirty tracking theo provider |
| Detached entity | Không tự flush |
| Loaded-state snapshot | Một cách so sánh dirty state |
| Bytecode enhancement | Có thể tối ưu field tracking |
| Collection snapshot | Có thể tốn nhiều RAM/CPU |
| Flush | Đồng bộ SQL trong transaction, chưa commit |
| FlushModeType.AUTO | Có thể auto-flush trước query |
| FlushModeType.COMMIT | Chỉnh timing, không tự vô hiệu tracking |
| SQL UPDATE count = 0 | Không chứng minh tracking cost bằng 0 |
| Entity result count | Không đồng nghĩa managed count |
| `em.clear()` | Detach toàn bộ managed entities |
| `em.detach(entity)` | Detach entity theo cascade rules |
| `em.contains(entity)` | Kiểm tra một entity có managed không |
| Application List | Có thể giữ entities dù đã clear |
| DTO projection | Tránh Product managed tracking cho selected fields |
| readOnly hints | Phụ thuộc framework/provider semantics |
| JDBC fetch size | Read-side buffering |
| JDBC batch size | DML grouping |
| Flush/clear chunk | Giới hạn context size |
| Transaction chunk | Atomicity và lock lifetime |
| Pagination | Không tự clear L1 |
| Streaming entities | Không tự tránh L1 growth |
| Hibernate Statistics | Counters, không live managed count |
| JFR/heap dump | CPU, GC, retained references |
| @Version | Optimistic concurrency |
| Bulk SQL | Tránh managed per-row tracking nhưng có trade-off |
| Kết quả tối ưu tốt | Correctness + memory + throughput + stability |

## Kết luận

**Persistence context là nền tảng của khả năng theo dõi và đồng bộ thay đổi trong JPA, nhưng không miễn phí về bộ nhớ và CPU.** Khi context chứa nhiều entities và collections, provider có thể giữ identity entries, loaded-state snapshots hoặc dirty flags, relationship state và pending actions. Chi phí đó có thể tồn tại ngay cả khi hầu như không có SQL UPDATE. Tuy nhiên, provider/version/enhancement khác nhau nên không thể áp một hằng số bytes/entity hoặc quy tắc O(N) tuyệt đối cho mọi trường hợp.

Muốn đánh giá chính xác, cần đo đồng thời **retained heap, allocations, GC, flush time, SQL/JDBC, query fetch shape, transaction duration và business throughput**. Một câu SQL ít hơn không có nghĩa graph nhỏ hơn; một heap thấp hơn không tự bảo đảm atomicity hay latency tốt hơn.

Với workload chỉ đọc, **DTO/scalar projections cùng paging hợp lý** thường tránh được managed-state overhead không cần thiết. Với workload phải xử lý entities theo domain lifecycle, **flush rồi clear theo chunk** giúp kiểm soát context growth, nhưng clear có thể detach cả entities caller vẫn đang sử dụng và flush không phải commit. JDBC batching, read-only provider hints và StatelessSession có thể hữu ích khi được dùng đúng semantics.

Hãy giữ **transaction boundaries, tenant authorization, @Version, database constraints, callbacks và restart/idempotency requirements** trong mọi quyết định tối ưu. Bulk SQL hoặc chia transaction theo chunk có thể tăng tốc nhưng cũng thay đổi business guarantees. Chỉ sau khi kiểm chứng dữ liệu committed và đo trên workload đại diện mới nên kết luận phương án nào thực sự hiệu quả.

Nguyên tắc thực hành cuối cùng: **giữ persistence context vừa đủ cho từng đơn vị công việc, tránh tải managed entities khi chỉ cần dữ liệu đọc, và xem memory–dirty checking–SQL–transaction như những chi phí liên quan nhưng cần đo riêng**.
