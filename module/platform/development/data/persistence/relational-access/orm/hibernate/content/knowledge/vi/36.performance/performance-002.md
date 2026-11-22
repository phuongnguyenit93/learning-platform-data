# Chọn hình dạng kết quả theo nhu cầu thay vì luôn tải thực thể đầy đủ

Một màn hình chỉ cần mã đơn hàng, trạng thái và tổng tiền nhưng repository lại tải toàn bộ `Order`, `Customer`, `OrderLine`, địa chỉ giao hàng và các collection liên quan. Sau đó service chỉ đọc ba thuộc tính rồi trả JSON. Cách làm này vẫn có thể đúng về chức năng, nhưng nó khiến Hibernate phải xử lý nhiều dữ liệu và trạng thái ORM hơn nhu cầu thực tế.

Khi một entity được load, Hibernate thường tạo hoặc quản lý một object trong Persistence Context, theo dõi identity, trạng thái và các thay đổi có thể cần dirty checking. Nếu query trả hàng nghìn entities, ứng dụng phải trả chi phí cho quá trình hydrate, quản lý object graph, giữ references và có thể kích hoạt thêm các lazy loads. Trong khi đó, nếu use case chỉ cần vài cột hoặc một phép tổng hợp, **scalar projection hoặc DTO projection** thường biểu đạt đúng nhu cầu hơn.

Bài này giúp chọn hình dạng kết quả dựa trên mục đích sử dụng: **managed entity khi cần làm việc với domain state; DTO/projection khi cần đọc dữ liệu cụ thể; scalar/aggregate khi chỉ cần giá trị; entity graph/fetch join khi cần một object graph có kiểm soát**.

~~~text
Use case
   |
   +-- Cần thay đổi domain entity?
   |       |
   |       +-- Có -> Managed entity / aggregate
   |       |           +-- Fetch đúng associations cần dùng
   |       |
   |       +-- Không
   |            |
   |            +-- Cần vài fields -> DTO / projection
   |            |
   |            +-- Cần một giá trị -> Scalar
   |            |
   |            +-- Cần thống kê -> Aggregate / GROUP BY
   |
   +-- Dữ liệu rất lớn -> Pagination / keyset / streaming
~~~

**Nguyên tắc cốt lõi:** Hãy chọn kết quả nhỏ nhất vẫn đáp ứng đúng hợp đồng của use case. Không phải mọi query đều cần entity; cũng không phải mọi entity query đều cần chuyển thành DTO. Lựa chọn đúng phụ thuộc vào việc code cần đọc, cập nhật, serialize, thống kê hay duyệt một tập dữ liệu lớn.

> **Phạm vi:** Java 17+, Jakarta Persistence, Hibernate ORM 6.x, Spring Data JPA và SQL quan hệ là bối cảnh minh họa. Constructor projections, record DTOs, interface projections, fetch plans và query APIs có khác biệt nhỏ theo phiên bản. Ví dụ JPQL/JPA được phân biệt với API riêng của Hibernate khi cần.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt entity result, scalar result, DTO projection, interface projection và aggregate result.
2. Giải thích vì sao entity query có thể tiêu tốn bộ nhớ và CPU nhiều hơn một projection.
3. Chọn query result shape theo nhu cầu đọc hay cập nhật dữ liệu.
4. Viết JPQL constructor projection và projection dùng Java record.
5. Dùng Spring Data JPA interface/class projections đúng mục đích.
6. Biết khi nào nên dùng `Tuple`, `Object[]`, native SQL hoặc `@SqlResultSetMapping`.
7. Thiết kế fetch plan để tránh N+1 và over-fetching.
8. Hiểu ảnh hưởng của to-many joins, duplicate rows và pagination.
9. Dùng scalar/aggregate queries cho count, sum, min, max và reporting.
10. Chọn offset/keyset pagination hoặc streaming cho tập dữ liệu lớn.
11. Kiểm tra managed state, dirty checking, L1/L2 cache và read-only behavior.
12. Đo SQL, số statements, số rows, heap và latency để xác nhận lựa chọn.

## 2. Entity query làm những việc gì?

Ví dụ:

~~~java
List<Order> orders = entityManager.createQuery(
    "select o from Order o where o.status = :status",
    Order.class
)
.setParameter("status", OrderStatus.PENDING)
.getResultList();
~~~

Hibernate không chỉ lấy vài cột để tạo một object đơn giản. Nó phải thực hiện các công việc phù hợp với entity mapping:

- Đọc các cột cần để hydrate entity.
- Xác định entity identity.
- Kiểm tra Persistence Context đã có instance tương ứng chưa.
- Tạo hoặc tái sử dụng managed instance.
- Thiết lập loaded state/snapshot theo cơ chế dirty checking.
- Resolve associations/proxies theo mapping.
- Quản lý collection state nếu query fetch các quan hệ.
- Áp dụng cache/provider behavior liên quan.

Entity result rất hữu ích khi use case cần domain behavior hoặc thay đổi state. Nhưng nếu chỉ hiển thị 3 cột, nhiều công việc trong số đó không đem lại giá trị.

## 3. Managed entity có giá trị khi nào?

Dùng entity khi use case thực sự cần:

- Gọi domain methods để thay đổi trạng thái.
- Duy trì invariants trong aggregate.
- Thay đổi nhiều thuộc tính và để dirty checking phát hiện.
- Dùng cascade/orphan removal theo mapping.
- Làm việc với associations trong cùng unit of work.
- Thực hiện lifecycle callbacks/auditing theo semantics ORM.
- Dùng optimistic locking qua `@Version`.

Ví dụ:

~~~java
@Transactional
public void confirmOrder(Long orderId) {
    Order order = entityManager.find(Order.class, orderId);

    if (order == null) {
        throw new OrderNotFoundException(orderId);
    }

    order.confirm();
    // Dirty checking sẽ ghi thay đổi khi flush/commit.
}
~~~

Ở đây `Order` là domain object cần được quản lý. DTO chỉ chứa trạng thái không thể thay thế tự nhiên mọi hành vi của aggregate.

## 4. Entity không phải định dạng trả API mặc định

Một controller trả entity trực tiếp:

~~~java
@GetMapping("/{id}")
public Order get(@PathVariable Long id) {
    return orderRepository.findById(id).orElseThrow();
}
~~~

có thể gặp:

- Serializer truy cập lazy associations.
- N+1 queries trong quá trình serialize.
- Infinite recursion giữa quan hệ hai chiều.
- Lộ các fields nội bộ.
- JSON shape thay đổi khi mapping thay đổi.
- Session đóng trước khi lazy association được truy cập.
- API contract phụ thuộc entity graph và Hibernate proxies.

DTO response tạo ranh giới rõ:

~~~java
public record OrderResponse(
    Long id,
    String orderNumber,
    String status,
    BigDecimal total
) {}
~~~

Controller trả DTO thay vì managed entity. DTO chỉ chứa dữ liệu API được phép công bố; fetch query được thiết kế để lấy đúng fields cần thiết.

## 5. Projection là gì?

Projection là cách yêu cầu database trả về **một tập thuộc tính hoặc giá trị cụ thể** thay vì hydrate toàn bộ entity graph.

Ví dụ:

~~~java
select o.id, o.orderNumber, o.status
from Order o
where o.status = :status
~~~

Projection có thể là:

- Scalar: một giá trị như `Long`, `BigDecimal`, `String`.
- Multi-select: nhiều giá trị như `Object[]` hoặc `Tuple`.
- DTO constructor projection: tạo class/record kết quả.
- Spring Data interface projection: tạo projection view từ selected properties.
- Aggregate projection: `COUNT`, `SUM`, `AVG`, `GROUP BY`.
- Native result mapping: mapping SQL custom vào DTO/entity/scalar.

Projection giúp giảm columns, object hydration và managed state khi phù hợp. Nó không tự đảm bảo query nhanh nếu WHERE/JOIN/index vẫn kém; SQL và query plan vẫn cần được đo.

## 6. Scalar projection cho một giá trị

Nếu chỉ cần tổng số đơn pending:

~~~java
Long count = entityManager.createQuery(
    """
    select count(o)
    from Order o
    where o.status = :status
    """,
    Long.class
)
.setParameter("status", OrderStatus.PENDING)
.getSingleResult();
~~~

Không cần load `List<Order>` rồi gọi `.size()`.

Ví dụ khác:

~~~java
BigDecimal total = entityManager.createQuery(
    """
    select sum(o.total)
    from Order o
    where o.customer.id = :customerId
    """,
    BigDecimal.class
)
.setParameter("customerId", customerId)
.getSingleResult();
~~~

Lưu ý: `SUM` có thể trả `null` nếu không có giá trị đầu vào (tùy aggregate/query semantics); quyết định service contract có chuyển null thành zero hay không. `COUNT` trả một giá trị số và thường trả 0 khi không có rows.

## 7. COUNT khác với tải entities

Không nên:

~~~java
List<Order> orders = repository.findByStatus(PENDING);
long count = orders.size();
~~~

nếu chỉ cần count.

Nên:

~~~java
long count = repository.countByStatus(PENDING);
~~~

hoặc JPQL `select count(o)`.

Database có thể thực hiện count mà không chuyển từng row thành Java entity. Execution plan cụ thể phụ thuộc index, predicate, MVCC và DBMS; không giả định `COUNT(*)` luôn constant-time.

## 8. DTO projection bằng JPQL constructor expression

Định nghĩa DTO:

~~~java
public record OrderSummary(
    Long id,
    String orderNumber,
    OrderStatus status,
    BigDecimal total
) {}
~~~

JPQL:

~~~java
List<OrderSummary> summaries = entityManager.createQuery(
    """
    select new com.example.orders.OrderSummary(
        o.id,
        o.orderNumber,
        o.status,
        o.total
    )
    from Order o
    where o.customer.id = :customerId
    order by o.createdAt desc
    """,
    OrderSummary.class
)
.setParameter("customerId", customerId)
.getResultList();
~~~

`select new fully.qualified.ClassName(...)` là constructor expression của JPQL. Hibernate gọi constructor tương ứng để tạo result object.

Ưu điểm:

- Chọn rõ các cột cần thiết.
- Result không phải managed entity.
- API/query contract dễ đọc.
- Dễ serialize.
- Không giữ entity graph chỉ để hiển thị.

Constructor và argument types/order phải khớp select list. Record canonical constructor có thể dùng được với các Hibernate/JPA versions phù hợp; xác nhận trên version dự án.

## 9. DTO class truyền thống

Nếu không dùng record:

~~~java
public class OrderSummaryDto {

    private final Long id;
    private final String orderNumber;
    private final OrderStatus status;
    private final BigDecimal total;

    public OrderSummaryDto(
            Long id,
            String orderNumber,
            OrderStatus status,
            BigDecimal total) {
        this.id = id;
        this.orderNumber = orderNumber;
        this.status = status;
        this.total = total;
    }

    public Long getId() { return id; }
    public String getOrderNumber() { return orderNumber; }
    public OrderStatus getStatus() { return status; }
    public BigDecimal getTotal() { return total; }
}
~~~

JPQL constructor expression vẫn dùng fully qualified class name:

~~~java
select new com.example.orders.OrderSummaryDto(
    o.id, o.orderNumber, o.status, o.total
)
from Order o
~~~

DTO bất biến giúp tránh vô tình sửa dữ liệu hiển thị và thể hiện rõ query output. Với class có nhiều constructors, đảm bảo Hibernate chọn được constructor phù hợp; có thể cần mapping rõ hơn.

## 10. DTO projection không nằm trong Persistence Context như entity

Khi query trả `OrderSummary`, object này không phải entity `Order` được quản lý. Vì vậy:

- Thay `summary.status` không tự tạo UPDATE cho bảng orders.
- Không có dirty checking entity cho DTO.
- DTO không có lazy associations của Hibernate entity.
- Không dùng `entityManager.remove(summary)`.
- Không thể merge DTO như một entity thông thường.
- Query chỉ hydrate các values đã select.

Đây thường là điều mong muốn cho read model. Nếu cần cập nhật order, load entity trong command/use case hoặc dùng explicit update query có semantics phù hợp.

## 11. Constructor projection với phép tính

DTO có thể chứa biểu thức:

~~~java
public record CustomerSpend(
    Long customerId,
    String customerName,
    Long orderCount,
    BigDecimal totalSpend
) {}
~~~

~~~java
List<CustomerSpend> result = entityManager.createQuery(
    """
    select new com.example.CustomerSpend(
        c.id,
        c.name,
        count(o),
        sum(o.total)
    )
    from Customer c
    left join c.orders o
    group by c.id, c.name
    order by sum(o.total) desc
    """,
    CustomerSpend.class
).getResultList();
~~~

Query trả một dòng summary cho mỗi customer. Không cần load toàn bộ orders vào Java chỉ để cộng tổng.

Cần xử lý `sum(o.total)` có thể null khi customer chưa có orders. DTO field phải chấp nhận null hoặc query dùng `coalesce(sum(o.total), 0)` với kiểu literal phù hợp dialect/JPA.

## 12. Interface projection trong Spring Data JPA

Spring Data có thể tạo projection dựa trên interface:

~~~java
public interface OrderListView {
    Long getId();
    String getOrderNumber();
    OrderStatus getStatus();
    BigDecimal getTotal();
}
~~~

Repository:

~~~java
List<OrderListView> findByCustomerId(Long customerId);
~~~

Spring Data có thể tạo proxy projection và chọn các properties tương ứng khi có thể xác định projection là closed. Đây là cách ngắn gọn cho read views đơn giản.

Tuy nhiên, cần inspect SQL generated để xác nhận provider chỉ lấy columns cần thiết; nested projections, open projections hoặc computed expressions có thể làm query rộng hơn dự kiến.

## 13. Closed và open projections

**Closed projection** khai báo getters tương ứng properties của entity:

~~~java
public interface CustomerNameView {
    String getName();
    String getEmail();
}
~~~

Spring Data biết các properties cần thiết và có thể tối ưu selection.

**Open projection** có thể dùng SpEL:

~~~java
public interface CustomerLabel {
    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
~~~

Với open projection, framework có thể phải lấy entity/target state rộng hơn vì expression có thể truy cập bất kỳ thuộc tính nào. Không giả định open projection luôn giảm SQL columns.

Nếu chỉ cần ghép firstName/lastName, cân nhắc JPQL constructor projection hoặc database expression có select list rõ.

## 14. Nested interface projections và associations

Ví dụ:

~~~java
public interface OrderView {
    Long getId();
    String getOrderNumber();
    CustomerView getCustomer();

    interface CustomerView {
        String getName();
    }
}
~~~

Nested projection tiện cho API/read model, nhưng việc traverse association có thể khiến Spring Data/Hibernate tạo joins hoặc lấy nhiều dữ liệu hơn mong muốn. Cấu trúc proxy và nested property resolution phụ thuộc query/mapping.

Đừng chỉ nhìn interface rồi kết luận một SQL join tối ưu được sinh ra. Bật SQL logging, đếm statements và kiểm tra số rows/cột thực tế.

Nếu query cần một shape phức tạp có nhiều aggregate/joins, constructor DTO thường cho bạn quyền kiểm soát rõ hơn.

## 15. Spring Data class-based projection

Có thể dùng record:

~~~java
public record OrderListItem(
    Long id,
    String orderNumber,
    BigDecimal total
) {}
~~~

~~~java
List<OrderListItem> findByCustomerId(Long customerId);
~~~

Spring Data có thể dùng constructor parameter names để xác định properties cho class-based projection. Với class có nhiều constructors, cần constructor được đánh dấu/được framework nhận diện theo contract phiên bản Spring Data.

Khi cần query cụ thể, dùng `@Query` với JPQL constructor expression:

~~~java
@Query("""
    select new com.example.OrderListItem(
        o.id, o.orderNumber, o.total
    )
    from Order o
    where o.customer.id = :customerId
    """)
List<OrderListItem> findItems(Long customerId);
~~~

Đây là cách tường minh và dễ review SQL intent.

## 16. Dynamic projections

Spring Data có thể nhận projection type làm tham số:

~~~java
<T> Collection<T> findByCustomerId(
    Long customerId,
    Class<T> type
);
~~~

Caller chọn projection type:

~~~java
Collection<OrderListView> views =
    repository.findByCustomerId(customerId, OrderListView.class);

Collection<Order> entities =
    repository.findByCustomerId(customerId, Order.class);
~~~

Dynamic projections hữu ích khi nhiều use cases cần các read shapes khác nhau. Nhưng không nên biến repository thành API mơ hồ, để caller tùy ý chọn entity graph không giới hạn. Giữ các projection types có mục đích và kiểm tra SQL từng trường hợp.

## 17. Tuple projection

JPA `Tuple` cho phép truy cập kết quả theo alias:

~~~java
List<Tuple> rows = entityManager.createQuery(
    """
    select
        o.id as id,
        o.orderNumber as number,
        o.total as total
    from Order o
    where o.status = :status
    """,
    Tuple.class
)
.setParameter("status", OrderStatus.PAID)
.getResultList();
~~~

Đọc:

~~~java
for (Tuple row : rows) {
    Long id = row.get("id", Long.class);
    String number = row.get("number", String.class);
    BigDecimal total = row.get("total", BigDecimal.class);
}
~~~

Tuple tiện cho query động hoặc kết quả có cấu trúc thay đổi. Nhược điểm là lỗi alias/type thường chỉ phát hiện runtime; DTO constructor/record thường có contract compile-time dễ hiểu hơn.

## 18. Object[] projection và vì sao nên hạn chế

~~~java
List<Object[]> rows = entityManager.createQuery(
    "select o.id, o.orderNumber, o.total from Order o"
).getResultList();
~~~

Truy cập:

~~~java
Long id = (Long) rows.get(0)[0];
String number = (String) rows.get(0)[1];
BigDecimal total = (BigDecimal) rows.get(0)[2];
~~~

Vấn đề:

- Index phụ thuộc thứ tự select.
- Cast dễ sai.
- Code không tự mô tả field names.
- Refactor query có thể làm lỗi runtime.
- Khó chia sẻ contract với API/service.

`Object[]` vẫn có thể hữu ích cho script nhỏ hoặc query tạm, nhưng với production code dài hạn, ưu tiên DTO, record hoặc Tuple có aliases.

## 19. Native SQL projection

Khi cần SQL-specific features, window functions, CTE, vendor functions hoặc query plan tối ưu đặc biệt, native SQL có thể phù hợp.

Ví dụ Spring Data:

~~~java
@Query(
    value = """
        select
            o.id as id,
            o.order_number as orderNumber,
            o.total as total
        from orders o
        where o.customer_id = :customerId
        order by o.created_at desc
        """,
    nativeQuery = true
)
List<Map<String, Object>> findNativeSummary(Long customerId);
~~~

Map result types và alias handling phụ thuộc Spring Data/provider/driver. Với DTO native result phức tạp, cân nhắc `@SqlResultSetMapping`, `ConstructorResult`, `ColumnResult` hoặc custom repository JDBC mapping.

Native SQL có trách nhiệm rõ hơn với tên bảng/cột, dialect và tenant/security predicates; đừng cho rằng mọi ORM filters/soft-delete restrictions tự động được thêm vào raw SQL.

## 20. @SqlResultSetMapping cho native DTO

JPA có thể khai báo:

~~~java
@SqlResultSetMapping(
    name = "OrderSummaryMapping",
    classes = @ConstructorResult(
        targetClass = OrderSummaryDto.class,
        columns = {
            @ColumnResult(name = "id", type = Long.class),
            @ColumnResult(name = "order_number", type = String.class),
            @ColumnResult(name = "total", type = BigDecimal.class)
        }
    )
)
~~~

Sau đó native query có thể dùng mapping name qua API phù hợp.

Lợi ích là định nghĩa conversion vào constructor DTO rõ ràng. Nhưng phải test alias, numeric types và driver output trên DB thực tế; một số database trả kiểu số khác với kỳ vọng Java nếu không cast rõ.

Với query đơn giản, JPQL DTO projection thường portable hơn và ít mapping metadata hơn.

## 21. Chọn fields thay vì SELECT *

Projection query:

~~~java
select new com.example.OrderListItem(
    o.id, o.orderNumber, o.total
)
from Order o
~~~

có thể chọn ba columns. Entity query có thể cần nhiều mapped columns để hydrate đầy đủ entity state, tùy mapping và bytecode enhancement/provider optimization.

Giảm columns giúp:

- Ít bytes truyền từ DB.
- Ít conversion/hydration.
- Ít Java allocations.
- Ít nguy cơ vô tình load sensitive columns.
- Read model/API contract rõ hơn.

Tuy nhiên, nếu query filter/order/join trên index khác, DB vẫn có thể đọc nhiều pages. Projection không thay index/query plan design.

## 22. Fetch plan: projection hay entity graph?

Có hai nhu cầu khác nhau:

**A. Cần một read shape cố định:** dùng DTO/projection.

~~~java
select new com.example.OrderDetail(
    o.id, o.orderNumber, c.name, o.total
)
from Order o
join o.customer c
where o.id = :id
~~~

**B. Cần domain entity và một phần associations để tiếp tục xử lý:** dùng entity query với fetch plan.

~~~java
@EntityGraph(attributePaths = {"customer", "lines"})
Optional<Order> findWithCustomerAndLinesById(Long id);
~~~

EntityGraph điều khiển fetch plan; nó không biến entity result thành DTO. Associations được fetch vẫn là managed objects trong Persistence Context.

Không dùng EntityGraph chỉ để trả JSON khi DTO là contract phù hợp hơn.

## 23. N+1 queries do lazy associations

Ví dụ:

~~~java
List<Order> orders = repository.findAll();

for (Order order : orders) {
    String customerName = order.getCustomer().getName();
}
~~~

Nếu customer là LAZY, có thể phát:

~~~text
SELECT orders ...                     1 query
SELECT customer WHERE id = ?         N queries
~~~

Mỗi query riêng có thể nhanh nhưng tổng latency và connection usage tăng.

Các lựa chọn:

- DTO projection join customer name.
- Fetch join cho entity graph cần dùng.
- EntityGraph theo repository use case.
- Batch fetching cho nhiều proxies/collections.
- Thay đổi use case để chỉ lấy dữ liệu cần.

Chọn giải pháp theo expected cardinality và SQL shape; không chuyển mọi association thành EAGER để che N+1.

## 24. DTO join tránh hydrate association entity

Nếu list view chỉ cần tên khách hàng:

~~~java
public record OrderRow(
    Long id,
    String number,
    String customerName,
    BigDecimal total
) {}
~~~

~~~java
select new com.example.OrderRow(
    o.id,
    o.orderNumber,
    c.name,
    o.total
)
from Order o
join o.customer c
where o.status = :status
~~~

Hibernate join customer table để lấy `c.name`, nhưng không nhất thiết hydrate một managed Customer entity cho mỗi row.

Đây là read model phù hợp cho bảng danh sách. Nếu customer optional, dùng `left join` và DTO field nullable để giữ orders không có customer.

## 25. To-many joins tạo duplicate parent rows

Query:

~~~java
select o
from Order o
join o.lines l
where l.sku = :sku
~~~

Một Order có nhiều matching lines có thể xuất hiện nhiều lần trong SQL result. `select distinct o` có thể giúp loại duplicate entity results theo query semantics/provider.

Nhưng `DISTINCT` trên SQL rows với nhiều selected columns không phải lúc nào cũng giảm database work; Hibernate có thể xử lý entity identity/deduplication theo query type.

Nếu chỉ muốn kiểm tra order có line matching, `exists` có thể phù hợp:

~~~java
select o
from Order o
where exists (
    select 1
    from OrderLine l
    where l.order = o
      and l.sku = :sku
)
~~~

Chọn shape phản ánh điều kiện thay vì join to-many không cần thiết.

## 26. Fetch join một collection

~~~java
select distinct o
from Order o
left join fetch o.lines
where o.id = :id
~~~

Hữu ích khi cần Order và lines trong cùng unit of work. Tuy nhiên SQL rows được nhân lên theo số lines. Nếu fetch nhiều to-many collections cùng lúc, row multiplication có thể rất lớn.

Ví dụ 100 Orders × 10 Lines × 5 Discounts có thể tạo khoảng 5.000 joined rows, dù số root entities chỉ 100.

Không fetch mọi collection chỉ vì “muốn tránh N+1”. Cần đo cardinality, bytes và hydration cost.

## 27. Multiple bag fetch và collection explosion

Một số mapping nhiều `List` collections (bag semantics) khi fetch join đồng thời có thể gây `MultipleBagFetchException` trong Hibernate, hoặc tạo Cartesian multiplication nếu mapping/collection types cho phép.

Thay vì fetch đồng thời mọi collection:

- Fetch một collection rồi batch fetch collection khác.
- Dùng nhiều query có kiểm soát trong cùng persistence context.
- Dùng DTO projections với aggregation/subqueries.
- Chia read model thành các endpoints/queries.
- Xem xét Set/list semantics chỉ khi domain ordering/duplicates cho phép.

Đổi `List` thành `Set` chỉ để né exception có thể thay đổi semantics của domain và equality requirements; không làm vậy một cách máy móc.

## 28. EntityGraph không phải đảm bảo một SQL duy nhất

~~~java
@EntityGraph(attributePaths = {"customer", "lines"})
Optional<Order> findById(Long id);
~~~

EntityGraph mô tả associations cần fetch. Provider có thể thực hiện joins hoặc secondary selects tùy mapping, query và version.

Do đó:

- Kiểm tra SQL statements.
- Kiểm tra collection cardinality.
- Xác nhận không có lazy SQL sau khi service return.
- Kiểm tra pagination nếu graph có to-many.
- Kiểm tra cache interaction.

EntityGraph là công cụ kiểm soát fetch requirements, không phải contract “luôn đúng một SELECT”.

## 29. Aggregate query cho dashboard

Không load toàn bộ payments để tính doanh thu:

~~~java
List<Payment> payments = paymentRepository.findByDateBetween(from, to);
BigDecimal total = payments.stream()
    .map(Payment::getAmount)
    .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

Nên cân nhắc aggregate trong DB:

~~~java
BigDecimal total = entityManager.createQuery(
    """
    select sum(p.amount)
    from Payment p
    where p.paidAt >= :from
      and p.paidAt < :to
      and p.status = :status
    """,
    BigDecimal.class
)
.setParameter("from", from)
.setParameter("to", to)
.setParameter("status", PaymentStatus.PAID)
.getSingleResult();
~~~

Database có thể dùng indexes và aggregate execution mà không chuyển mọi Payment thành Java objects. Kết quả null khi không có rows cần được xử lý rõ.

## 30. GROUP BY trả summary rows

~~~java
public record DailySales(
    LocalDate date,
    Long orderCount,
    BigDecimal total
) {}
~~~

~~~java
List<DailySales> daily = entityManager.createQuery(
    """
    select new com.example.DailySales(
        o.businessDate,
        count(o),
        sum(o.total)
    )
    from Order o
    where o.businessDate >= :from
      and o.businessDate < :to
    group by o.businessDate
    order by o.businessDate
    """,
    DailySales.class
)
.setParameter("from", from)
.setParameter("to", to)
.getResultList();
~~~

Một row mỗi ngày thay vì một entity mỗi order. Đây là lựa chọn phù hợp cho dashboard/reporting.

Cần cân nhắc DB grouping semantics, timezone/business date definition, null amounts và index trên filter/group columns.

## 31. EXISTS và scalar subquery

Nếu chỉ cần biết customer có order overdue:

~~~java
select c.id
from Customer c
where exists (
    select 1
    from Order o
    where o.customer = c
      and o.dueDate < :today
      and o.status <> :paid
)
~~~

Không cần load Customer và collection Orders. `EXISTS` biểu đạt điều kiện tồn tại; optimizer có thể dùng semi-join/index strategies.

Nếu cần số lượng orders, dùng `count` subquery/aggregate thay vì load collection rồi `.size()`. Với lazy collection, `.size()` có thể phát SQL count hoặc load collection tùy mapping/provider; không nên dựa vào một behavior không được đo.

## 32. Pagination với DTO projection

Ví dụ Spring Data:

~~~java
@Query("""
    select new com.example.OrderListItem(
        o.id, o.orderNumber, o.total
    )
    from Order o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
Page<OrderListItem> findItems(
    OrderStatus status,
    Pageable pageable
);
~~~

Projection giảm dữ liệu hydrate cho từng row. `Page` thường cần thêm count query để tính tổng số trang; với query phức tạp, count query có thể tốn kém.

Nếu UI chỉ cần “có trang tiếp theo không”, `Slice` hoặc `Window` (tùy Spring Data version) có thể tránh count toàn bộ. Kiểm tra generated count query và SQL thật.

## 33. Offset pagination và chi phí offset lớn

~~~java
query.setFirstResult(100000);
query.setMaxResults(50);
~~~

Offset lớn có thể yêu cầu database scan/skip nhiều rows trước khi trả 50 rows. Khi bảng thay đổi trong lúc người dùng duyệt, rows có thể lặp hoặc bị bỏ qua tùy sort order.

Dùng offset pagination khi:

- Tập dữ liệu vừa phải.
- User cần nhảy tới trang số N.
- Sort ổn định.
- Query plan đủ tốt.

Với batch processing hoặc infinite scrolling lớn, cân nhắc keyset pagination.

## 34. Keyset pagination cho list lớn

~~~java
List<OrderListItem> page = entityManager.createQuery(
    """
    select new com.example.OrderListItem(
        o.id, o.orderNumber, o.total
    )
    from Order o
    where o.status = :status
      and (
          o.createdAt < :lastCreatedAt
          or (
              o.createdAt = :lastCreatedAt
              and o.id < :lastId
          )
      )
    order by o.createdAt desc, o.id desc
    """,
    OrderListItem.class
)
.setParameter("status", status)
.setParameter("lastCreatedAt", cursor.createdAt())
.setParameter("lastId", cursor.id())
.setMaxResults(pageSize)
.getResultList();
~~~

Cursor gồm tất cả sort keys cần để thứ tự là deterministic. Thêm unique tie-breaker như ID để không bỏ/nhân rows có cùng timestamp.

Keyset pagination phù hợp next/previous scrolling; không tự hỗ trợ nhảy tới trang 500 nếu không lưu cursor history.

## 35. Projection không tự giải quyết pagination trên to-many fetch joins

Một query entity:

~~~java
select distinct o
from Order o
left join fetch o.lines
order by o.createdAt desc
~~~

kết hợp pagination có thể gặp giới hạn do database pagination trên joined rows khác với pagination trên root entities. Hibernate có thể cảnh báo, thực hiện pagination trong memory hoặc behavior khác tùy config/version.

Giải pháp thường dùng:

1. Query page root IDs/DTOs trước.
2. Query entity graph/children cho page IDs nếu thực sự cần.
3. Giữ thứ tự page rõ ràng khi ghép kết quả.
4. Hoặc dùng DTO projection/grouping trực tiếp.

Không tắt cảnh báo pagination collection fetch mà không hiểu memory impact; có thể biến query 50 rows thành load toàn bộ result rồi cắt trong JVM.

## 36. Two-step loading: page IDs rồi load graph

Bước 1:

~~~java
List<Long> ids = entityManager.createQuery(
    """
    select o.id
    from Order o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """,
    Long.class
)
.setParameter("status", status)
.setMaxResults(50)
.getResultList();
~~~

Bước 2:

~~~java
List<Order> orders = entityManager.createQuery(
    """
    select distinct o
    from Order o
    left join fetch o.customer
    left join fetch o.lines
    where o.id in :ids
    """,
    Order.class
)
.setParameter("ids", ids)
.getResultList();
~~~

`IN` query không đảm bảo trả kết quả theo thứ tự IDs đầu vào. Nếu thứ tự quan trọng, sắp xếp lại theo ID list hoặc dùng order expression thích hợp.

Với hai queries trong cùng transaction, dữ liệu có thể thay đổi giữa bước 1 và bước 2 tùy isolation. Xác định semantics snapshot/consistency cần thiết.

## 37. Streaming và cursor khi đọc nhiều rows

Không nên:

~~~java
List<Order> all = repository.findAll();
~~~

nếu có hàng triệu rows.

Các lựa chọn:

- Page/chunk.
- Keyset pagination.
- Hibernate scroll/cursor.
- Spring Data `Stream<T>` khi query/driver/transaction hỗ trợ.
- DTO/scalar projection.
- Database export/bulk tools.

Stream không có nghĩa dữ liệu tự động không chiếm bộ nhớ. Driver fetch size, persistence context, transaction và code consumer đều ảnh hưởng buffering.

## 38. Spring Data Stream<T> cần đóng resource

Ví dụ:

~~~java
@Query("select o from Order o where o.status = :status")
Stream<Order> streamByStatus(OrderStatus status);
~~~

Sử dụng:

~~~java
@Transactional(readOnly = true)
public void processPending() {
    try (Stream<Order> stream =
             repository.streamByStatus(OrderStatus.PENDING)) {
        stream.forEach(this::process);
    }
}
~~~

Stream phải được đóng để giải phóng JDBC ResultSet/statement/connection. Transaction phải còn hiệu lực trong lúc tiêu thụ nếu provider yêu cầu.

Nếu stream trả entities, Persistence Context vẫn có thể tích lũy managed entities. Kết hợp clear/detach theo cách tương thích cursor, hoặc dùng DTO/scalar stream. Không clear giữa cursor rows mà chưa test driver/provider behavior và entity references.

## 39. Read-only query và projection là hai lựa chọn khác nhau

Hibernate/Spring có thể tối ưu read-only behavior:

~~~java
@Transactional(readOnly = true)
public List<Order> listOrders() {
    return repository.findAll();
}
~~~

Read-only transaction/hints có thể giảm một số dirty-checking work tùy integration, nhưng kết quả vẫn là entity objects và có thể vẫn chiếm Persistence Context.

DTO projection thay đổi **result shape** và không hydrate entity graph. Hai kỹ thuật có thể kết hợp khi phù hợp, nhưng không thay thế nhau.

Nếu chỉ cần dữ liệu để hiển thị, projection thường biểu đạt nhu cầu rõ hơn là load entities rồi đánh dấu read-only.

## 40. Entity query có thể tận dụng L1/L2 cache

Entity load có thể hưởng lợi từ first-level identity map và L2 entity cache. Nếu use case cần entity đã được cache, load entity có thể nhanh và tiết kiệm hơn DTO query phải truy vấn lại columns.

Vì vậy không phải projection luôn nhanh hơn:

- L2 hit có thể tránh DB round trip cho entity.
- Projection thường cần SQL để lấy selected fields.
- DTO query có thể không dùng entity cache theo cách entity load dùng.
- Query cache là cơ chế riêng.
- Cache invalidation/consistency cũng có cost.

Đo workload thực tế; chọn projection để giảm data/managed state, không phải theo khẩu hiệu “DTO luôn nhanh”.

## 41. Entity projection và update semantics

Một query trả entity:

~~~java
Order order = entityManager.createQuery(
    "select o from Order o where o.id = :id",
    Order.class
)
.setParameter("id", id)
.getSingleResult();

order.changeShippingAddress(address);
~~~

Entity managed; thay đổi có thể được dirty checking ghi khi flush.

DTO projection:

~~~java
OrderEditView view = ...;
~~~

Thay đổi DTO không cập nhật entity. Nếu cần ghi, service phải:

- Load entity và áp dụng command/domain method; hoặc
- Thực hiện explicit update query với optimistic locking/audit semantics thích hợp.

Đừng dùng DTO read model làm entity giả rồi `merge()` toàn bộ dữ liệu từ client; điều đó dễ ghi đè fields không được tải hoặc không được phép sửa.

## 42. Partial entity selection không phải DTO

Một query chỉ select vài properties nhưng khai báo result type là entity:

~~~java
select new Order(o.id, o.orderNumber)
from Order o
~~~

không phải cách portable để tạo một managed partial entity. JPA entities có identity/state contract đầy đủ; partial constructor object có thể không phải managed entity theo semantics bạn mong muốn.

Tránh tạo entity object không đầy đủ để dùng như read DTO. Dùng DTO class/record riêng để tránh nhầm lẫn và dirty checking không mong muốn.

## 43. Entity field lazy basic attributes

Hibernate có thể hỗ trợ lazy basic attributes với bytecode enhancement trong một số cấu hình. Điều này không biến entity query thành projection query tự động:

- Entity vẫn là managed object.
- Lazy basic field có thể được load khi truy cập.
- Enhancement/build configuration cần đúng.
- Serialization có thể kích hoạt field load.
- SQL count/columns phụ thuộc mapping/provider.

Nếu use case chỉ cần vài cột ổn định, DTO projection thường đơn giản và dễ kiểm soát hơn việc dựa vào lazy basic field enhancement.

## 44. Một query, nhiều use cases hay nhiều projection?

Repository có thể cung cấp:

~~~java
Optional<Order> findById(Long id);

Optional<OrderDetailView> findDetailViewById(Long id);

Page<OrderListItem> findListItems(
    OrderStatus status,
    Pageable pageable
);

Long countByStatus(OrderStatus status);
~~~

Mỗi method có contract rõ:

- Command/update path lấy entity.
- Detail API lấy DTO có đúng fields.
- List page lấy projection nhẹ.
- Dashboard lấy aggregate.

Tránh một repository method “load everything” rồi mọi caller tự chọn vài properties. Cũng tránh tạo hàng trăm projection types trùng lặp; nhóm theo API/use-case boundary và reuse khi contract thực sự giống nhau.

## 45. Query projection và authorization

Projection chỉ chọn fields, không tự bảo đảm caller được phép xem row.

~~~java
select new com.example.CustomerSummary(c.id, c.name)
from Customer c
where c.tenantId = :tenantId
  and c.id = :id
~~~

Tenant/ownership/ACL predicates vẫn phải được áp dụng theo security model. Native SQL và bulk queries cần cùng policy.

Không loại bỏ security predicate chỉ vì DTO chứa ít fields. Một `CustomerSummary` nhỏ trả nhầm tenant vẫn là data leak.

## 46. Projection và soft delete/filter

Entity-level filters hoặc SQL restrictions có thể áp dụng cho ORM query paths theo mapping/version, nhưng native SQL projection không tự nhận mọi ORM restriction.

Với DTO JPQL, xác nhận Hibernate sinh predicate phù hợp. Với native DTO query, viết tenant/soft-delete/visibility predicates tường minh hoặc dựa vào DB RLS/view có contract rõ.

Đừng cho rằng “không hydrate entity” nghĩa là query không cần security/visibility rules.

## 47. Grouping và SQL aggregate types

Aggregate queries có kiểu trả về phụ thuộc JPQL/database semantics:

- `COUNT` thường trả `Long`.
- `SUM` trả kiểu số tương ứng với expression theo JPA rules.
- `AVG` có kiểu trả về theo expression/JPA.
- `MIN`/`MAX` trả kiểu của expression.
- Empty input có thể tạo null cho nhiều aggregates ngoại trừ count.

DTO constructor parameter types phải khớp kết quả query. Với `SUM(BigDecimal)`, dùng BigDecimal; không ép sang Double cho tiền.

Nếu DB trả numeric precision khác mong đợi, test integration trên DB thật.

## 48. DISTINCT và duplicate elimination

Projection query:

~~~java
select distinct o.customer.id
from Order o
~~~

có thể trả distinct customer IDs ở DB.

Entity query với join fetch:

~~~java
select distinct o
from Order o
left join fetch o.lines
~~~

có thể cần deduplicate root entity results. Cách Hibernate xử lý SQL DISTINCT và entity identity có thể khác theo query shape/version.

Nếu chỉ cần unique scalar values, hãy để DB `DISTINCT` trên scalar projection thay vì load entities rồi tạo `Set` trong Java.

## 49. Sorting và computed columns

Nếu sort DTO theo expression:

~~~java
select new com.example.OrderListItem(
    o.id, o.orderNumber, o.total
)
from Order o
order by o.createdAt desc, o.id desc
~~~

`createdAt` không nhất thiết phải nằm trong DTO để dùng ORDER BY, tùy JPQL/provider semantics. Tuy nhiên khi dùng Spring Data pageable/sort dynamic, property phải tương thích query/projection mapping.

Nếu sort theo computed aggregate, kiểm tra database execution plan và stable ordering. Luôn thêm unique tie-breaker khi pagination cần deterministic order.

## 50. DTO projection cho command validation có thể stale

Một DTO summary được load ở thời điểm T1 không đảm bảo dữ liệu còn đúng lúc update T2.

Ví dụ client nhận `OrderEditView(status=PENDING)`, nhưng một process khác đã confirm order. Khi client gửi command, service nên load current managed entity và kiểm tra state/version, hoặc update có optimistic version predicate.

Không dùng projection cũ làm nguồn sự thật để quyết định transition nếu concurrency có thể thay đổi row.

## 51. Optimistic locking với projection

Nếu API cần gửi version về client:

~~~java
public record OrderEditView(
    Long id,
    String status,
    long version
) {}
~~~

Query:

~~~java
select new com.example.OrderEditView(
    o.id, o.status, o.version
)
from Order o
where o.id = :id
~~~

Command có thể gửi version kỳ vọng. Khi update, load entity và so sánh version hoặc dùng update query:

~~~sql
UPDATE orders
SET status = ?, version = version + 1
WHERE id = ? AND version = ?;
~~~

Kiểm tra affected row count. Dùng `@Version` trên entity thường thuận tiện hơn khi dùng managed entity path. Projection chỉ cung cấp version value; nó không tự bật optimistic locking.

## 52. Native SQL projection và type conversion

Native query có thể trả JDBC types như:

- `BigInteger` hoặc `BigDecimal` cho numeric expressions tùy driver.
- `Timestamp` cho temporal columns.
- `String` cho enum codes.
- `Object[]`/Tuple-like rows tùy API.

Nếu cast trực tiếp:

~~~java
Long count = (Long) query.getSingleResult();
~~~

có thể lỗi trên driver trả `BigInteger`. Dùng mapping/explicit SQL cast phù hợp và integration tests theo DB driver.

Với native DTO, `@SqlResultSetMapping` hoặc custom row mapper cho phép conversion có kiểm soát hơn.

## 53. Query count và test performance

Một query projection vẫn có thể phát N+1 nếu code truy cập association sau đó qua proxy. Vì DTO thường không có proxy associations, điều này dễ kiểm soát hơn, nhưng query chính vẫn có thể có nhiều joins/rows.

Test:

- SQL statement count.
- Number of rows returned.
- Columns selected (SQL log/DB driver instrumentation).
- Query duration.
- Heap allocation/GC.
- Connection pool usage.
- DB execution plan.

Không chỉ assert “query chạy một lần”; một câu SQL join có thể trả hàng triệu rows do Cartesian multiplication.

## 54. Integration test so sánh entity và DTO

Test có thể thực hiện cùng một use case hai cách:

~~~java
@Test
void listProjectionReturnsRequiredData() {
    List<OrderListItem> items = repository.findListItems(
        OrderStatus.PENDING
    );

    assertThat(items)
        .extracting(OrderListItem::orderNumber)
        .contains("ORD-100");
}
~~~

Đối với entity query:

~~~java
@Test
void entityQueryReturnsManagedInstances() {
    Order order = entityManager.find(Order.class, orderId);

    assertTrue(entityManager.contains(order));
}
~~~

Đối với DTO:

~~~java
OrderListItem item = repository.findListItem(orderId);
assertFalse(entityManager.contains(item)); // DTO không phải entity.
~~~

Assertions cần phù hợp method thực tế; `EntityManager.contains()` nhận entity object, nên test DTO có thể kiểm tra class/managed status theo cách API cho phép. Mục tiêu là chứng minh result shape và state semantics khác nhau.

## 55. Test tránh lazy SQL sau service boundary

Một regression test có thể:

1. Gọi service trả DTO.
2. Đóng transaction/EntityManager.
3. Serialize DTO thành JSON.
4. Xác nhận không có SQL phát sinh thêm.
5. Kiểm tra response chỉ chứa fields được phép.

Đối chứng với entity trả trực tiếp có thể serialize và phát lazy queries nếu OSIV bật. Đừng để test dựa vào OSIV configuration vô tình che lazy-loading bug.

## 56. Test N+1 bằng query counter

Dùng datasource proxy, Hibernate statistics hoặc test instrumentation để đếm SQL statements.

Kịch bản:

- Tạo N orders và N customers.
- Load list.
- Truy cập customer name.
- Đo số statements.
- Thay bằng DTO projection join.
- Đo lại.

Nếu N tăng từ 10 lên 100 mà statement count cũng tăng tuyến tính, có thể có N+1. Tuy nhiên một số batch-fetch strategies tạo số queries theo batches; kiểm tra SQL shape và correctness, không chỉ một con số.

Hibernate Statistics là SessionFactory-wide; test chạy song song có thể làm nhiễu. Cô lập test workload.

## 57. Test pagination không bị collection fetch in-memory

Cấu hình test dữ liệu có nhiều child rows và page size nhỏ. Quan sát:

- Hibernate warnings/logs về pagination collection fetch.
- SQL có LIMIT/OFFSET hay không.
- Số root entities và joined rows.
- Heap peak.
- Query count.
- Kết quả page boundaries không duplicate/missing.

Nếu Hibernate xử lý pagination trong memory, test có thể pass nhưng production dataset lớn sẽ tốn bộ nhớ. Ưu tiên page IDs/DTOs rồi fetch associations có giới hạn.

## 58. Test projection types và null values

DTO constructor phải chấp nhận null khi LEFT JOIN:

~~~java
public record OrderCustomerView(
    Long orderId,
    String customerName
) {}
~~~

~~~java
select new com.example.OrderCustomerView(
    o.id,
    c.name
)
from Order o
left join o.customer c
~~~

Nếu customer null, `customerName` null. Constructor primitive `long`/`int` không biểu diễn null; dùng wrapper `Long`/`Integer` hoặc xử lý bằng `coalesce` có chủ đích.

Test empty aggregates, nullable fields và numeric conversions trên database thật.

## 59. Read model và write model

Một ứng dụng có thể dùng:

- **Write model:** Domain entities/aggregates được load và thay đổi trong transaction.
- **Read model:** DTO/projections tối ưu theo màn hình/report/API.
- **Reporting model:** Aggregate/materialized view hoặc query native.
- **Export model:** Streaming DTO/scalar rows theo keyset.

Đây là cách phân chia theo nhu cầu, không bắt buộc triển khai CQRS framework. Cùng một database vẫn có thể có nhiều query shapes.

Không nhân bản business rules tùy tiện giữa read/write models; read projection là cách trình bày dữ liệu, còn command path vẫn enforce domain invariants.

## 60. Quy trình chọn hình dạng kết quả

~~~mermaid
flowchart TD
    A["Use case cần dữ liệu"] --> B{"Có thay đổi domain state?"}
    B -- "Có" --> C["Load managed entity/aggregate"]
    C --> D["Fetch đúng associations"]
    B -- "Không" --> E{"Cần toàn entity behavior?"}
    E -- "Có" --> C
    E -- "Không" --> F{"Một giá trị hay phép tính?"}
    F -- "Một giá trị / aggregate" --> G["Scalar / COUNT / SUM / GROUP BY"]
    F -- "Nhiều fields" --> H["DTO / record / interface projection"]
    G --> I{"Dataset lớn?"}
    H --> I
    I -- "Có" --> J["Keyset / page / stream / cursor"]
    I -- "Không" --> K["Giới hạn rows và kiểm tra SQL"]
    D --> K
    J --> L["Đo query, rows, heap, latency"]
    K --> L
~~~

## 61. Checklist trước khi viết repository query

**Nhu cầu use case**

- [ ] Có cần gọi domain methods hoặc cập nhật entity không?
- [ ] Cần tất cả mapped fields hay chỉ vài properties?
- [ ] Cần associations nào thật sự?
- [ ] Có thể dùng scalar/aggregate thay vì load collection?
- [ ] DTO có phải API/read contract rõ ràng hơn entity?

**SQL và fetch plan**

- [ ] Select list chỉ gồm fields cần?
- [ ] Có N+1 hoặc to-many Cartesian multiplication?
- [ ] LEFT JOIN hay INNER JOIN đúng semantics?
- [ ] Pagination có tương thích fetch plan?
- [ ] Sort có stable tie-breaker?
- [ ] Count query có thực sự cần thiết?
- [ ] Native query có tenant/soft-delete/security predicates?

**Lifecycle**

- [ ] Entity result có cần managed state không?
- [ ] DTO có bị nhầm là entity không?
- [ ] Lazy loads có thể xảy ra sau transaction?
- [ ] Read-only hints có bị nhầm với projection?
- [ ] Cache behavior đã được tính đến?
- [ ] Projection cũ có thể stale trước command update?

**Kiểm thử và đo lường**

- [ ] SQL generated đã được kiểm tra?
- [ ] Statement count và row count có hợp lý?
- [ ] Heap/allocation được đo với dataset lớn?
- [ ] Null/type conversions được test?
- [ ] Pagination boundaries không duplicate/miss?
- [ ] DB query plan có index phù hợp?

## 62. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Luôn trả entity cho list API | Hydrate fields/state không cần | DTO/interface projection |
| Load list rồi `.size()` | Tải toàn bộ rows để đếm | `COUNT` |
| Load collection để tính tổng | Nhiều entities/heap | `SUM`/aggregate |
| DTO projection nhưng vẫn truy cập entity proxy khác | N+1 vẫn xảy ra ở nơi khác | Select join fields cần thiết |
| Open projection dùng SpEL tùy tiện | Framework có thể phải load rộng | Closed projection/DTO query |
| Dùng Object[] lâu dài | Cast/index lỗi runtime | Record/DTO/Tuple |
| Fetch join nhiều collections | Row multiplication/MultipleBagFetch | Nhiều query hoặc projection |
| Page với collection fetch join | In-memory pagination/heap lớn | Page IDs rồi load graph |
| Serialize entity trực tiếp | Lazy SQL/N+1/API coupling | DTO response |
| Cho DTO merge như entity | Update state không an toàn | Load entity + command |
| Nghĩ projection luôn nhanh hơn cache | Bỏ qua L2 hit và workload | Benchmark thực tế |
| Native query quên tenant predicate | Data leak | Explicit policy/DB RLS |
| Stream không đóng | Giữ connection/resultset | try-with-resources + transaction |
| Keyset thiếu tie-breaker | Duplicate/missing page rows | Composite stable cursor |
| Projection nullable vào primitive | Null conversion failure | Wrapper/coalesce |

## 63. Bài tập thực hành

1. Viết list endpoint trả entity đầy đủ; đo SQL columns, statement count và heap.
2. Chuyển sang Java record DTO với 4 fields; so sánh SQL và allocations.
3. Viết interface closed projection và open projection; quan sát select list.
4. Tạo query `COUNT` thay cho `findAll().size()`.
5. Tạo dashboard `SUM`/`GROUP BY` thay cho aggregate trong Java.
6. So sánh Tuple, Object[] và DTO constructor projection về readability/type safety.
7. Tạo N+1 khi truy cập `Order.customer`; sửa bằng DTO join và EntityGraph, đo lại.
8. Fetch hai to-many collections và quan sát row multiplication/MultipleBagFetch.
9. Thử pagination với collection fetch join; kiểm tra warning và SQL limit.
10. Viết two-step loading: page IDs rồi fetch graph, bảo toàn thứ tự.
11. Dùng keyset pagination với `(createdAt, id)` và test timestamps trùng nhau.
12. Stream DTO rows, đóng Stream và kiểm tra connection release.
13. Trả DTO qua controller sau khi transaction đóng; serialize không phát SQL.
14. Test DTO null values từ LEFT JOIN và aggregate empty result.
15. So sánh entity L2 cache hit với DTO query trên cùng workload.
16. Thêm `@Version` vào DTO read model, gửi command update với expected version và test conflict.
17. Viết native DTO mapping và test numeric/temporal types trên PostgreSQL Testcontainers.
18. Dùng query counter để đặt regression limit cho số SQL statements trong một use case.

## 64. Tài liệu tham khảo

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — JPQL, constructor expressions, Tuple, EntityManager, entity lifecycle và query semantics.
- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/current/userguide/html_single/Hibernate_User_Guide.html) — fetching, projections, HQL, pagination, batching và Session behavior.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/) — interface/class projections, repository query methods, pagination và streaming.
- [Spring Data Commons Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html) — closed/open/nested/dynamic projections.
- [Hibernate ORM Query Language](https://docs.hibernate.org/orm/current/querylanguage/html_single/Hibernate_Query_Language.html) — select lists, constructor expressions, aggregates, joins và subqueries.

Các trang `current` có thể mô tả phiên bản mới hơn project. Hãy đối chiếu API record projections, `Window`/keyset pagination, native result mapping và Hibernate query behavior với đúng Spring Data/Hibernate minor version đang chạy.

## 65. Tổng kết

**Hình dạng kết quả là một quyết định thiết kế query và lifecycle, không chỉ là kiểu Java trả về.**

- Dùng **managed entity** khi cần domain behavior, thay đổi state, cascade, dirty checking hoặc optimistic locking.
- Dùng **DTO/record/interface projection** khi cần một read shape cụ thể cho list/detail/API.
- Dùng **scalar và aggregate** khi chỉ cần một giá trị, count hoặc summary; đừng tải hàng nghìn entities để tính trong Java.
- Dùng **EntityGraph/fetch join** khi cần entity graph có kiểm soát; theo dõi N+1, to-many cardinality và pagination.
- Dùng **keyset/page/streaming** để giới hạn rows và resource lifetime cho tập dữ liệu lớn.
- Dùng **native SQL/result mapping** khi query cần khả năng riêng của DB, đồng thời chịu trách nhiệm rõ với types, tenant/security predicates và dialect.
- Kiểm tra **SQL, row count, statement count, heap, cache và transaction lifecycle**; không kết luận hiệu năng chỉ từ số columns hoặc tên annotation.

Trước mỗi repository method, hãy hỏi: **use case cần đọc fields nào, có thay đổi domain state không, cần bao nhiêu rows và associations nào?** Chọn entity, DTO, scalar hoặc aggregate theo câu trả lời đó. Khi result shape phản ánh đúng nhu cầu, Hibernate có ít công việc không cần thiết hơn và code cũng thể hiện rõ hơn hợp đồng dữ liệu của use case.
