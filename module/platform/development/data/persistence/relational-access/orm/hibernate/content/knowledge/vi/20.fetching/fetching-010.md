# Phân trang cùng collection fetch join và nguy cơ xử lý trong bộ nhớ

## 1. Vì sao một trang 20 đơn hàng có thể tải hàng trăm nghìn dòng?

Một màn hình quản trị thường cần hiển thị danh sách đơn hàng mới nhất, mỗi đơn kèm vài dòng hàng. Trong Hibernate ORM, lập trình viên có thể viết một truy vấn tự nhiên:

~~~java
select distinct o
from PurchaseOrder o
left join fetch o.items
order by o.createdAt desc
~~~

Sau đó thêm phân trang bằng **setFirstResult()**, **setMaxResults()** hoặc **Pageable**. Ý định là lấy 20 đơn hàng và các dòng hàng của chúng trong một lần truy vấn.

Vấn đề nằm ở chỗ **collection fetch join làm một đơn hàng xuất hiện trên nhiều hàng SQL**. Nếu đơn hàng có 5 dòng hàng, kết quả join có thể chứa 5 hàng cho cùng một đơn. **LIMIT 20** ở SQL khi đó giới hạn 20 hàng join, không phải 20 đơn hàng đầy đủ.

Nếu Hibernate áp dụng giới hạn trực tiếp tại database, một trang có thể chứa ít hơn 20 đơn và collection của đơn cuối bị cắt cụt. Để tránh trả về collection không đầy đủ, Hibernate có thể **lấy toàn bộ các hàng join phù hợp rồi áp dụng phân trang trong bộ nhớ**. Kết quả Java vẫn có 20 đơn, nhưng database có thể đã gửi hàng trăm nghìn hàng cho ứng dụng.

Đây là một lỗi hiệu năng khó nhận ra khi dùng ORM: code trông như chỉ lấy một trang nhỏ, nhưng công việc thực tế không bị giới hạn theo page size.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa phân trang **entity gốc** và phân trang **hàng SQL sau join**.
2. Nhận biết collection fetch join làm nhân số hàng như thế nào.
3. Hiểu cảnh báo Hibernate về pagination over collection fetch và cấu hình để biến cảnh báo thành lỗi sớm.
4. Dùng chiến lược hai bước: phân trang ID trước, rồi fetch dữ liệu của đúng tập ID đó.
5. Chọn DTO projection, batch fetching hoặc subselect fetching khi phù hợp.
6. Xử lý count query, thứ tự kết quả, collection lớn và nhiều collection.
7. Tránh các lỗi do DISTINCT, Pageable, EntityGraph, JOIN FETCH và điều kiện lọc collection.
8. Đo số hàng SQL, bộ nhớ, thời gian và execution plan để xác nhận phân trang thật sự hiệu quả.

Ví dụ dùng Java 17+, Jakarta Persistence, Hibernate ORM 6.x, Spring Data JPA và PostgreSQL. Cảnh báo, tên logger và hành vi chi tiết có thể khác theo phiên bản Hibernate; hãy xác nhận trên phiên bản của ứng dụng.

## 2. Phân trang database có nghĩa là gì?

Phân trang thông thường giới hạn số hàng database trả về:

~~~sql
SELECT id, created_at, status
FROM purchase_orders
WHERE status = 'CONFIRMED'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;
~~~

Với chỉ mục phù hợp, database có thể đọc các hàng theo thứ tự cần thiết rồi dừng khi đã tìm đủ 20 hàng. Ở trang tiếp theo, OFFSET 20 bỏ qua 20 hàng đầu rồi lấy 20 hàng sau.

Trong JPA:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery("""
    select o
    from PurchaseOrder o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """, PurchaseOrder.class)
    .setParameter("status", OrderStatus.CONFIRMED)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
~~~

Với truy vấn không làm nhân bản hàng gốc, Hibernate có thể chuyển giới hạn thành cú pháp pagination của dialect, chẳng hạn LIMIT/OFFSET trong PostgreSQL.

**Điểm cốt yếu:** số hàng mà database giới hạn phải tương ứng với đơn vị mà ứng dụng muốn phân trang. Khi query chỉ lấy PurchaseOrder, một hàng SQL thường tương ứng một đơn hàng. Khi query join collection, một đơn hàng có thể xuất hiện nhiều hàng SQL.

### 2.1. Thứ tự phải ổn định

Không nên phân trang chỉ với:

~~~sql
ORDER BY created_at DESC
~~~

nếu nhiều đơn có cùng timestamp. Hãy thêm một khóa duy nhất làm tie-breaker:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Thứ tự ổn định giúp giảm hiện tượng bản ghi lặp hoặc bị bỏ sót giữa các trang khi các giá trị sort trùng nhau. Nó không tự giải quyết mọi thay đổi đồng thời giữa các request; nếu tập dữ liệu thay đổi trong khi người dùng lật trang, cần chọn semantics nhất quán phù hợp.

## 3. Collection fetch join làm nhân bản hàng SQL

Giả sử có ba đơn:

| Order ID | Số OrderItem |
|---:|---:|
| 101 | 3 |
| 102 | 1 |
| 103 | 4 |

Truy vấn:

~~~sql
SELECT o.id, o.status, i.id, i.product_id, i.quantity
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
ORDER BY o.id;
~~~

có thể trả:

| order_id | item_id | quantity |
|---:|---:|---:|
| 101 | 1 | 2 |
| 101 | 2 | 1 |
| 101 | 3 | 4 |
| 102 | 4 | 1 |
| 103 | 5 | 1 |
| 103 | 6 | 2 |
| 103 | 7 | 1 |
| 103 | 8 | 3 |

Tám hàng SQL tương ứng ba entity PurchaseOrder và tám entity OrderItem.

Hibernate đọc các hàng này và dựng object graph:

~~~text
PurchaseOrder 101
  items: [1, 2, 3]

PurchaseOrder 102
  items: [4]

PurchaseOrder 103
  items: [5, 6, 7, 8]
~~~

Một collection fetch join là cách lấy parent và collection trong cùng query. Nhưng **một entity gốc có thể lặp trên nhiều hàng kết quả SQL**.

### 3.1. LIMIT 5 giới hạn hàng join, không giới hạn parent

Nếu database thực thi:

~~~sql
SELECT ...
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
ORDER BY o.id
LIMIT 5;
~~~

kết quả có thể là:

| order_id | item_id |
|---:|---:|
| 101 | 1 |
| 101 | 2 |
| 101 | 3 |
| 102 | 4 |
| 103 | 5 |

Ứng dụng nhận được ba đơn, nhưng Order 103 chỉ có một trong bốn dòng hàng. Nếu Hibernate đánh dấu collection items là đã được khởi tạo, code có thể hiểu nhầm đây là toàn bộ collection.

Đây là lý do ORM không thể đơn giản áp dụng LIMIT vào mọi collection fetch join rồi coi kết quả là một trang entity hợp lệ.

### 3.2. Số hàng SQL có thể lớn hơn nhiều page size

Với một collection items, số hàng join xấp xỉ:

~~~text
R = tổng trên mỗi order của max(1, số item của order)
~~~

max(1, ...) phản ánh LEFT JOIN: đơn không có item vẫn có một hàng với cột item NULL.

Nếu một trang logic có 20 đơn, mỗi đơn trung bình 30 item, query có thể trả khoảng 600 hàng SQL. Nếu có đơn chứa 5.000 item, một trang nhỏ vẫn có thể kéo về hàng nghìn hàng.

Page size giới hạn số parent; nó **không giới hạn số child của mỗi parent**. Đây là một lý do khác để không fetch một collection không có giới hạn kích thước trong màn hình danh sách.

## 4. Điều Hibernate làm khi gặp pagination trên collection fetch join

Hãy xét:

~~~java
List<PurchaseOrder> page = entityManager.createQuery("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.items
    order by o.createdAt desc, o.id desc
    """, PurchaseOrder.class)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
~~~

Trong Hibernate ORM, collection fetch join kết hợp setFirstResult/setMaxResults là tình huống đặc biệt. Để tránh cắt cụt collection, Hibernate có thể:

1. Gửi query join **không giới hạn page ở database**.
2. Đọc và hydrate các hàng phù hợp, dựng entity/collection trong persistence context.
3. Khử các root entity trùng lặp theo cơ chế của Hibernate.
4. Áp dụng offset/limit trong bộ nhớ trên danh sách root entity.

Kết quả có thể đúng về số lượng parent và collection đầy đủ, nhưng chi phí truy vấn không còn được giới hạn bởi page size.

### 4.1. Cảnh báo thường gặp

Hibernate có thể phát cảnh báo dạng:

~~~text
HHH90003004: firstResult/maxResults specified with collection fetch;
applying in memory
~~~

Đây là tín hiệu cần xem xét ngay. Nếu log này xuất hiện trên một endpoint production có nhiều dữ liệu, database có thể đang trả về một tập join rất lớn để ứng dụng tự cắt trang.

### 4.2. Vì sao Hibernate không luôn áp dụng LIMIT tại DB?

Nếu Hibernate áp dụng LIMIT trực tiếp vào hàng join, collection của một parent có thể không đầy đủ. ORM phải bảo vệ ngữ nghĩa của entity graph mà query yêu cầu.

Có thể hình dung:

- **Phân trang hàng SQL:** dễ cho database, nhưng có nguy cơ lấy thiếu child của parent.
- **Phân trang root entity sau khi hydrate:** bảo đảm collection được nạp đầy đủ, nhưng có thể đọc quá nhiều dữ liệu.

Hibernate chọn bảo vệ tính đầy đủ của collection bằng cách xử lý pagination trong memory trong trường hợp này. Đây là hành vi cần được phát hiện và tránh trong query lớn.

### 4.3. Cấu hình fail fast

Trong Spring Boot:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        query:
          fail_on_pagination_over_collection_fetch: true
~~~

Hoặc cấu hình property tương đương:

~~~properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

Khi bật, Hibernate sẽ ném exception thay vì âm thầm xử lý pagination trên collection fetch join trong bộ nhớ (với trường hợp được cấu hình phát hiện). Điều này hữu ích trong môi trường development/test và thường nên cân nhắc bật ở production để lỗi query được phát hiện sớm thay vì âm thầm tạo tải lớn.

Tên setting thuộc Hibernate, không phải thuộc tính JPA portable. Hãy kiểm tra version Hibernate mà ứng dụng đang chạy.

**Cấu hình fail fast không sửa query.** Nó biến một vấn đề hiệu năng tiềm ẩn thành lỗi rõ ràng để đội phát triển thay bằng chiến lược fetch/pagination phù hợp.

## 5. Ví dụ Spring Data JPA thường gặp

Một repository:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select distinct o
        from PurchaseOrder o
        left join fetch o.items
        where o.status = :status
        order by o.createdAt desc, o.id desc
        """)
    Page<PurchaseOrder> findPageWithItems(
        @Param("status") OrderStatus status,
        Pageable pageable
    );
}
~~~

Phương thức trên trông hợp lý nhưng có vấn đề: Pageable yêu cầu phân trang root, trong khi collection fetch join làm nhân hàng SQL. Hibernate có thể phải phân trang trong memory.

Thêm distinct không giải quyết vấn đề này. DISTINCT có thể giúp ngữ nghĩa kết quả JPQL và loại các root entity trùng trong một số đường thực thi, nhưng các hàng có item_id khác nhau vẫn khác nhau ở cấp SQL. Database không thể gộp chúng thành một hàng parent duy nhất mà vẫn trả đủ cột của từng item.

### 5.1. Page còn có count query

Spring Data Page thường cần:

1. Query lấy nội dung trang.
2. Query đếm tổng số phần tử phù hợp để tạo totalElements và totalPages, nếu framework không suy ra được từ nội dung.

Không nên đưa collection fetch join vào count query. Count cần đếm parent, không phải số hàng join:

~~~java
@Query(
    value = """
        select o from PurchaseOrder o
        where o.status = :status
        order by o.createdAt desc, o.id desc
        """,
    countQuery = """
        select count(o) from PurchaseOrder o
        where o.status = :status
        """
)
Page<PurchaseOrder> findPage(
    @Param("status") OrderStatus status,
    Pageable pageable
);
~~~

Query này phân trang an toàn ở root vì chưa fetch collection. Có thể load items sau bằng batch fetch hoặc query chi tiết theo danh sách ID.

### 5.2. Slice khi không cần tổng số trang

Nếu UI chỉ cần nút “Trang tiếp theo” hoặc “Tải thêm”, Slice có thể tránh count query tổng. Nhưng Slice **không làm collection fetch join trở nên an toàn**: vấn đề row multiplication vẫn còn. Hãy kết hợp Slice với query root hoặc DTO projection, không dùng nó để che warning.

## 6. Chiến lược khuyến nghị: phân trang ID trước, fetch collection sau

Một cách phổ biến để lấy một trang parent cùng collection là thực hiện **hai truy vấn**:

1. Query đầu tiên chỉ lấy ID của đúng trang PurchaseOrder, áp dụng LIMIT/OFFSET tại database.
2. Query thứ hai lấy các PurchaseOrder có ID thuộc trang đó và fetch collection items, **không áp dụng pagination ở query thứ hai**.

Vì query thứ hai chỉ giới hạn trong tập ID của trang, Hibernate có thể nạp đầy đủ collection mà không phải quét toàn bộ đơn phù hợp.

~~~mermaid
flowchart TD
    A[Nhận Pageable] --> B[Query 1: chọn 20 Order ID + thứ tự]
    B --> C[Database áp dụng LIMIT/OFFSET]
    C --> D{Có ID?}
    D -->|Không| E[Trả trang rỗng]
    D -->|Có| F[Query 2: fetch Order + Items theo ID]
    F --> G[Map kết quả theo ID]
    G --> H[Khôi phục thứ tự của Query 1]
    H --> I[Trả Page/DTO]
~~~

### 6.1. Repository với query lấy ID

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select o.id
        from PurchaseOrder o
        where o.status = :status
        order by o.createdAt desc, o.id desc
        """)
    List<Long> findPageIds(
        @Param("status") OrderStatus status,
        Pageable pageable
    );

    @Query("""
        select distinct o
        from PurchaseOrder o
        left join fetch o.items
        where o.id in :ids
        """)
    List<PurchaseOrder> findWithItemsByIdIn(
        @Param("ids") Collection<Long> ids
    );

    @Query("""
        select count(o)
        from PurchaseOrder o
        where o.status = :status
        """)
    long countByStatus(@Param("status") OrderStatus status);
}
~~~

Đây là các method trong cùng repository; cần import Collection, List, Long, Pageable, Query và Param. Query thứ hai không có Pageable. Vì danh sách ID đã được giới hạn, số parent được fetch cũng bị giới hạn theo trang.

### 6.2. Service thực hiện hai bước

~~~java
@Service
public class PurchaseOrderQueryService {
    private final PurchaseOrderRepository orders;

    public PurchaseOrderQueryService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public Page<PurchaseOrder> findPageWithItems(
            OrderStatus status, Pageable pageable) {

        List<Long> ids = orders.findPageIds(status, pageable);
        if (ids.isEmpty()) {
            return new PageImpl<>(
                List.of(), pageable, orders.countByStatus(status));
        }

        List<PurchaseOrder> fetched = orders.findWithItemsByIdIn(ids);
        Map<Long, PurchaseOrder> byId = fetched.stream()
            .collect(Collectors.toMap(
                PurchaseOrder::getId,
                Function.identity()
            ));

        List<PurchaseOrder> ordered = ids.stream()
            .map(byId::get)
            .filter(Objects::nonNull)
            .toList();

        long total = orders.countByStatus(status);
        return new PageImpl<>(ordered, pageable, total);
    }
}
~~~

Ví dụ cần import Page, PageImpl, Pageable, Map, Collectors, Function, Objects và List. Nó thể hiện ba điểm:

- ID query có pagination ở database.
- Query fetch không phân trang và chỉ lấy các parent đã chọn.
- Kết quả query IN không bảo đảm thứ tự theo danh sách ID đầu vào, nên service khôi phục thứ tự bằng map.

**Trong ứng dụng thực tế**, cần quyết định có cần count query riêng hay không; có thể dùng PageableExecutionUtils hoặc Slice để tránh count khi không cần. Ngoài ra, nếu parent bị xóa giữa hai query, kết quả query fetch có thể ít ID hơn. Transaction isolation READ COMMITTED cho phép dữ liệu thay đổi giữa hai statement; hãy chọn semantics phù hợp và xử lý missing ID theo nghiệp vụ.

### 6.3. Vì sao cần cùng transaction?

Hai query thường nên chạy trong cùng service transaction để có một persistence context nhất quán và tránh để entity graph tách rời giữa các lần đọc. Nhưng **cùng transaction không mặc nhiên có snapshot giống nhau ở mọi isolation level**:

- PostgreSQL READ COMMITTED tạo snapshot cho từng statement; dữ liệu có thể đổi giữa query ID và query fetch.
- REPEATABLE READ giữ snapshot nhất quán hơn cho transaction nhưng có trade-off về concurrency/MVCC.
- Khóa pessimistic có thể cần nếu nghiệp vụ yêu cầu các parent không bị thay đổi/xóa trong lúc đọc.

Đối với màn hình danh sách thông thường, chấp nhận dữ liệu thay đổi nhẹ giữa hai query thường là hợp lý. Với báo cáo cần snapshot nhất quán, hãy định nghĩa yêu cầu rõ và chọn isolation/chiến lược đọc phù hợp.

### 6.4. Đừng fetch collection không cần thiết

Nếu danh sách chỉ cần số lượng item và tổng tiền, có thể dùng projection/aggregate thay vì fetch toàn bộ OrderItem:

~~~java
public record OrderListRow(
    Long id,
    Instant createdAt,
    OrderStatus status,
    Long itemCount,
    BigDecimal totalAmount
) {}
~~~

Query aggregate có thể dùng GROUP BY hoặc correlated subquery tùy schema. Ví dụ:

~~~java
@Query("""
    select new com.example.shop.dto.OrderListRow(
        o.id,
        o.createdAt,
        o.status,
        count(i.id),
        coalesce(sum(i.quantity * i.unitPrice), 0)
    )
    from PurchaseOrder o
    left join o.items i
    where o.status = :status
    group by o.id, o.createdAt, o.status
    order by o.createdAt desc, o.id desc
    """)
Page<OrderListRow> findOrderRows(
    @Param("status") OrderStatus status,
    Pageable pageable
);
~~~

Đây là ví dụ DTO JPQL; tùy database/provider, biểu thức coalesce/kiểu trả về của sum có thể cần điều chỉnh cho constructor record. Vì query có GROUP BY parent, phải kiểm tra SQL pagination và count query do Spring Data tạo; cung cấp countQuery tường minh nếu cần. Nếu chỉ cần danh sách, không cần dựng toàn bộ entity graph.

## 7. Giải pháp khác: batch fetching cho collection LAZY

Không phải lúc nào cũng cần fetch join. Một lựa chọn là lấy trang PurchaseOrder trước, rồi để Hibernate tải các collection theo từng nhóm khi ứng dụng truy cập.

### 7.1. @BatchSize trên collection

~~~java
import org.hibernate.annotations.BatchSize;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 25)
private List<OrderItem> items = new ArrayList<>();
~~~

Khi code truy cập getItems() trên một số parent đang managed, Hibernate có thể gom các owner chưa khởi tạo collection vào một hoặc nhiều câu SELECT theo batch, thay vì một SELECT riêng cho mỗi parent.

### 7.2. Cấu hình mặc định toàn ứng dụng

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 25
~~~

Hoặc:

~~~properties
hibernate.default_batch_fetch_size=25
~~~

Batch fetching giảm N+1 trong nhiều trường hợp, nhưng không đảm bảo chỉ có đúng một query. Hibernate có thể phát nhiều batch tùy số parent, số ID còn chờ và giới hạn bind parameter của database/driver.

### 7.3. Batch fetching không nhân bản hàng parent như fetch join

Truy vấn trang:

~~~sql
SELECT id, created_at, status
FROM purchase_orders
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Sau đó Hibernate có thể tải items:

~~~sql
SELECT *
FROM order_items
WHERE order_id IN (?, ?, ..., ?);
~~~

Parent page vẫn được giới hạn tại database; child rows được lấy trong một query hoặc vài query theo batch. Không có phép nhân parent × child trong cùng result set của root query.

### 7.4. Batch size không giới hạn số child của mỗi parent

Nếu một trong 20 đơn có 50.000 item, batch fetching vẫn có thể tải 50.000 item cho parent đó khi collection được truy cập. Batch size giới hạn **số owner được nhóm trong một lần lấy collection**, không phải số phần tử bên trong từng collection.

Với collection cực lớn, hãy query OrderItem theo trang riêng:

~~~java
Page<OrderItem> findByOrderIdOrderById(
    Long orderId, Pageable pageable);
~~~

Không nên buộc màn hình danh sách đơn hàng phải tải toàn bộ dòng hàng của một đơn có hàng chục nghìn chi tiết.

## 8. SUBSELECT fetching: lấy collection cho nhóm parent đã nạp

Hibernate hỗ trợ FetchMode.SUBSELECT cho một số quan hệ collection:

~~~java
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<OrderItem> items = new ArrayList<>();
~~~

Khi một collection trong nhóm parent được khởi tạo, Hibernate có thể sử dụng một subselect dựa trên truy vấn đã tải các owner trong persistence context để lấy collection cho nhóm đó. Hình dạng SQL cụ thể tùy query và Hibernate version.

**Lợi ích:** giảm số SELECT riêng lẻ cho từng collection owner.

**Giới hạn:**

- Không thay thế phân trang parent ở database.
- Có thể tải collection của toàn bộ nhóm parent đã được query, tùy phạm vi subselect.
- Không phù hợp nếu các collection rất lớn hoặc parent set không được giới hạn.
- Cần đo SQL thực tế, đặc biệt khi persistence context đã chứa nhiều parent từ những truy vấn trước.

Batch fetching và subselect fetching là hai chiến lược khác nhau. Chọn dựa trên pattern truy cập, kích thước nhóm và số phần tử collection.

## 9. EntityGraph không làm mất vấn đề pagination

Spring Data JPA cho phép:

~~~java
@EntityGraph(attributePaths = "items")
Page<PurchaseOrder> findByStatus(
    OrderStatus status, Pageable pageable);
~~~

EntityGraph là cách mô tả fetch plan. Nếu attribute path là một collection, provider có thể triển khai bằng join fetch hoặc chiến lược tải tương ứng. Khi query cần phân trang root nhưng fetch collection qua join, nguy cơ row multiplication và xử lý pagination trong memory vẫn có thể xuất hiện.

Vì vậy:

- EntityGraph chỉ có to-one associations thường ít gặp vấn đề row multiplication hơn.
- EntityGraph có collection cần kiểm tra SQL và cảnh báo pagination.
- Không coi EntityGraph là cách né quy tắc của collection fetch join.
- Bật fail-on-pagination-over-collection-fetch để phát hiện trường hợp Hibernate nhận ra tình huống này.

## 10. To-one fetch join thường an toàn hơn collection fetch join

Quan hệ:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

về mặt cardinality, mỗi PurchaseOrder tham chiếu tối đa một Customer. Fetch join:

~~~java
select o
from PurchaseOrder o
join fetch o.customer
order by o.createdAt desc, o.id desc
~~~

không nhân số hàng parent như một collection join, miễn là mapping/constraint bảo đảm quan hệ to-one thực sự là nhiều-một hoặc một-một theo đúng schema. Vì vậy phân trang root cùng to-one fetch join thường có thể được thực hiện ở database.

Nhưng hãy cẩn thận nếu mapping OneToOne không có uniqueness/FK như kỳ vọng hoặc query kết hợp thêm collection fetch join. Chỉ cần một collection fetch join trong query cũng có thể đưa query vào tình huống pagination over collection fetch.

### 10.1. Kết hợp to-one và collection

~~~java
select distinct o
from PurchaseOrder o
join fetch o.customer
left join fetch o.items
~~~

Việc fetch customer không gây nhân bản thêm vì đó là to-one, nhưng items vẫn làm một order có nhiều hàng SQL. To-one fetch join không “cứu” được collection pagination.

## 11. Fetch nhiều collection cùng lúc: Cartesian multiplication

Giả sử PurchaseOrder có:

- items: trung bình 5 phần tử.
- payments: trung bình 2 phần tử.
- shipments: trung bình 1 phần tử.

Query:

~~~java
select distinct o
from PurchaseOrder o
left join fetch o.items
left join fetch o.payments
left join fetch o.shipments
~~~

Với mỗi parent, số hàng SQL có thể xấp xỉ:

~~~text
max(1, itemCount)
× max(1, paymentCount)
× max(1, shipmentCount)
~~~

Ví dụ một đơn có 5 items, 2 payments và 1 shipment có thể tạo **10 hàng SQL** cho cùng một đơn. Nếu có 20 đơn tương tự, query trả khoảng 200 hàng join; nếu các collection lớn, số hàng tăng theo tích, không phải tổng.

### 11.1. MultipleBagFetchException

Hibernate có thể ném **MultipleBagFetchException** khi cùng fetch nhiều bag collection trong một query. Bag thường là collection kiểu List không có order column và có semantics cho phép phần tử lặp. Đây là dấu hiệu mapping/query đang yêu cầu một phép join rất dễ nhân bản dữ liệu.

Đổi List thành Set chỉ để né exception **không phải giải pháp tổng quát**:

- Cartesian multiplication vẫn tồn tại trong SQL.
- Set có semantics khác List/bag.
- equals()/hashCode() của entity có thể gây lỗi nếu thiết kế không ổn định.
- Dữ liệu trùng hoặc thứ tự có ý nghĩa có thể bị xử lý sai.

### 11.2. Chia fetch thành nhiều query

Một chiến lược thường dễ kiểm soát:

1. Lấy trang PurchaseOrder ID.
2. Fetch items cho các ID đó.
3. Fetch payments cho các ID đó trong một query khác hoặc batch.
4. Fetch shipments khi use case cần.
5. Map DTO trong transaction.

Nhiều query có thể tốt hơn một query join khổng lồ vì tránh tích số hàng và giảm dữ liệu lặp của parent. Hãy đo tổng round-trip và bytes truyền; không tối ưu theo số câu SQL đơn thuần.

## 12. Lọc collection khi fetch join có thể tạo collection không đầy đủ

Một query dễ gây nhầm:

~~~java
select distinct o
from PurchaseOrder o
join fetch o.items i
where i.status = :itemStatus
~~~

Ý định có thể là “lấy đơn có ít nhất một item ở trạng thái X”. Nhưng join fetch cũng đang dùng điều kiện trên item. Collection o.items có thể được khởi tạo chỉ với các item thỏa điều kiện, dù ứng dụng hiểu collection là toàn bộ items.

Nếu cần lọc parent theo điều kiện child nhưng vẫn muốn fetch **toàn bộ collection**, dùng EXISTS để lọc parent và fetch collection riêng:

~~~java
select distinct o
from PurchaseOrder o
left join fetch o.items
where exists (
    select 1
    from OrderItem i
    where i.order = o
      and i.status = :itemStatus
)
~~~

Query này vẫn có collection fetch join và vì thế vẫn không phù hợp để kết hợp trực tiếp với pagination lớn. Nó chỉ minh họa sự khác nhau giữa điều kiện chọn parent và collection được tải. Với danh sách phân trang, hãy đưa EXISTS vào query lấy ID, rồi fetch collection trong bước thứ hai.

## 13. Hai pha chi tiết hơn: Page ID và fetch graph

Đối với màn hình quản trị, ta có thể định nghĩa DTO:

~~~java
public record OrderListItem(
    Long id,
    Instant createdAt,
    OrderStatus status,
    String customerName,
    long itemCount
) {}
~~~

### 13.1. Pha 1: lấy ID và count

~~~java
@Query("""
    select o.id
    from PurchaseOrder o
    where o.status = :status
      and exists (
          select 1
          from OrderItem i
          where i.order = o
            and i.quantity >= :minimumQuantity
      )
    order by o.createdAt desc, o.id desc
    """)
List<Long> findMatchingIds(
    @Param("status") OrderStatus status,
    @Param("minimumQuantity") int minimumQuantity,
    Pageable pageable
);

@Query("""
    select count(o)
    from PurchaseOrder o
    where o.status = :status
      and exists (
          select 1
          from OrderItem i
          where i.order = o
            and i.quantity >= :minimumQuantity
      )
    """)
long countMatching(
    @Param("status") OrderStatus status,
    @Param("minimumQuantity") int minimumQuantity
);
~~~

Pha này phân trang parent ID, không join child thành nhiều hàng kết quả. EXISTS chỉ kiểm tra có child phù hợp, nên không làm nhân bản parent row trong result set.

### 13.2. Pha 2: fetch phần dữ liệu cần

~~~java
@Query("""
    select distinct o
    from PurchaseOrder o
    join fetch o.customer
    left join fetch o.items
    where o.id in :ids
    """)
List<PurchaseOrder> fetchPageGraph(
    @Param("ids") Collection<Long> ids
);
~~~

Không thêm Pageable vào query này. Nó chỉ nhận ID của trang hiện tại. Nếu một order có quá nhiều items, cân nhắc không fetch items ở đây mà query aggregate/child page riêng.

### 13.3. Map về DTO thay vì trả entity

~~~java
@Transactional(readOnly = true)
public Page<OrderListItem> search(
        OrderStatus status, int minimumQuantity, Pageable pageable) {

    List<Long> ids = repository.findMatchingIds(
        status, minimumQuantity, pageable);
    long total = repository.countMatching(status, minimumQuantity);

    if (ids.isEmpty()) {
        return new PageImpl<>(List.of(), pageable, total);
    }

    List<PurchaseOrder> graph = repository.fetchPageGraph(ids);
    Map<Long, PurchaseOrder> byId = graph.stream()
        .collect(Collectors.toMap(
            PurchaseOrder::getId, Function.identity()));

    List<OrderListItem> content = ids.stream()
        .map(byId::get)
        .filter(Objects::nonNull)
        .map(order -> new OrderListItem(
            order.getId(),
            order.getCreatedAt(),
            order.getStatus(),
            order.getCustomer().getName(),
            order.getItems().size()
        ))
        .toList();

    return new PageImpl<>(content, pageable, total);
}
~~~

Code cần import các kiểu DTO, Page/PageImpl/Pageable, Map, Collectors, Function, Objects. Đây là minh họa cho một transaction read-only; cần xử lý trường hợp parent biến mất giữa hai query theo semantics đã chọn.

Nếu chỉ cần itemCount, **fetch tất cả items là thừa**. Thay query thứ hai bằng projection/aggregate lấy số lượng, hoặc lưu một giá trị tổng hợp được cập nhật nhất quán nếu workload yêu cầu. DTO giúp tránh đưa entity graph ra ngoài service và tránh lazy SQL phát sinh lúc JSON serialization.

## 14. Khi collection rất lớn: phân trang child độc lập

Một đơn có thể có hàng chục nghìn dòng do import hoặc lịch sử chi tiết. Trong trường hợp đó, không nên tải toàn bộ items chỉ vì đang hiển thị parent.

API có thể chia:

~~~text
GET /orders?page=0&size=20
GET /orders/9001/items?page=0&size=50
~~~

Repository:

~~~java
public interface OrderItemRepository
        extends JpaRepository<OrderItem, Long> {

    Page<OrderItem> findByOrderIdOrderById(
        Long orderId, Pageable pageable);
}
~~~

Service chỉ xác nhận order tồn tại/quyền truy cập rồi trả trang item. Cách này đặt giới hạn độc lập lên cả parent lẫn child.

Nếu UI cần hiển thị số lượng/tổng tiền, dùng aggregate query thay vì load toàn bộ collection:

~~~java
@Query("""
    select count(i)
    from OrderItem i
    where i.order.id = :orderId
    """)
long countItems(@Param("orderId") Long orderId);
~~~

Một collection là quan hệ trong domain; điều đó không có nghĩa mọi use case phải nạp tất cả phần tử của nó vào bộ nhớ.

## 15. Offset pagination và keyset pagination

Ngay cả khi bỏ collection fetch join, OFFSET lớn có thể tốn kém:

~~~sql
SELECT id, created_at, status
FROM purchase_orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 200000;
~~~

Database có thể phải đi qua/bỏ qua nhiều hàng trước khi trả trang sâu, tùy index và execution plan.

### 15.1. Keyset theo ID

Nếu thứ tự chỉ theo ID:

~~~sql
SELECT id, created_at, status
FROM purchase_orders
WHERE id < :lastSeenId
ORDER BY id DESC
LIMIT 20;
~~~

Đây là keyset/cursor pagination. Mỗi request gửi khóa cuối của trang trước. Query không cần bỏ qua tất cả hàng ở các trang trước.

### 15.2. Keyset theo timestamp và ID

Với thứ tự created_at DESC, id DESC, điều kiện trang tiếp theo:

~~~sql
SELECT id, created_at, status
FROM purchase_orders
WHERE (created_at, id) < (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

PostgreSQL hỗ trợ row-value comparison cho kiểu dữ liệu phù hợp. JPQL có thể biểu diễn tương đương bằng điều kiện:

~~~java
where o.createdAt < :lastCreatedAt
   or (o.createdAt = :lastCreatedAt and o.id < :lastId)
~~~

### 15.3. Kết hợp keyset với collection fetch

Keyset giải quyết chi phí OFFSET trong query chọn parent; nó **không làm collection fetch join trở nên an toàn nếu query cuối vẫn dùng pagination trên join**.

Kết hợp đúng:

1. Keyset query lấy ID của 20 parent tiếp theo.
2. Query thứ hai fetch graph theo ID, không pagination.
3. Khôi phục thứ tự theo ID query.
4. Tạo cursor cho trang tiếp theo từ phần tử cuối.

Với dữ liệu liên tục thay đổi, keyset thường ổn định hơn OFFSET, nhưng cần định nghĩa cách xử lý bản ghi được insert/update có sort key nằm trước hoặc sau cursor.

## 16. Count query không được đếm hàng join thay cho parent

Giả sử có:

| Order | Số items |
|---|---:|
| A | 3 |
| B | 2 |
| C | 1 |

COUNT(*) trên join order_items có thể trả 6, trong khi số đơn là 3.

Nếu query lọc bằng join:

~~~sql
SELECT COUNT(*)
FROM purchase_orders o
JOIN order_items i ON i.order_id = o.id
WHERE i.quantity > 0;
~~~

đây là số hàng join, không phải số đơn duy nhất. Để đếm parent:

~~~sql
SELECT COUNT(DISTINCT o.id)
FROM purchase_orders o
JOIN order_items i ON i.order_id = o.id
WHERE i.quantity > 0;
~~~

Hoặc dùng EXISTS:

~~~sql
SELECT COUNT(*)
FROM purchase_orders o
WHERE EXISTS (
    SELECT 1
    FROM order_items i
    WHERE i.order_id = o.id
      AND i.quantity > 0
);
~~~

Với Spring Data Page, count query nên được định nghĩa rõ khi query phức tạp. Không copy collection fetch join sang count query. Count distinct có thể đúng nhưng vẫn có chi phí sort/hash lớn; EXISTS thường diễn đạt rõ hơn khi chỉ cần kiểm tra sự tồn tại.

## 17. DISTINCT trong JPQL không phải phép giảm dữ liệu miễn phí

Trong query:

~~~java
select distinct o
from PurchaseOrder o
left join fetch o.items
~~~

DISTINCT diễn đạt rằng kết quả JPQL không nên chứa lặp root entity. Tuy nhiên:

- Các hàng SQL chứa cột OrderItem khác nhau vẫn khác nhau.
- Database có thể cần DISTINCT/unique processing trên toàn bộ hàng nếu SQL DISTINCT được render.
- Hibernate ORM 6 tự loại các duplicate root entity trong kết quả của collection fetch join theo cơ chế của Hibernate; trong nhiều trường hợp không cần thêm distinct chỉ để khử root object trùng.
- Tính portable của JPQL và hành vi provider cần được cân nhắc nếu code phải chạy trên nhiều JPA provider/version.

DISTINCT **không biến một collection join thành một hàng trên mỗi parent**, không giảm số child cần hydrate và không sửa vấn đề pagination trong memory. Dùng nó vì ngữ nghĩa kết quả cần, không dùng như một cách chữa hiệu năng.

## 18. EntityGraph, fetch profile và query method cần được kiểm tra bằng SQL

Có nhiều cách yêu cầu Hibernate tải association:

- JPQL/HQL JOIN FETCH.
- JPA EntityGraph.
- Hibernate fetch profile.
- @BatchSize/default batch fetch size.
- FetchMode.SUBSELECT.
- EAGER mapping (không nên bật tràn lan).

Chúng mô tả hoặc ảnh hưởng fetch plan, nhưng kết quả SQL phụ thuộc provider, dialect, association và query. Với một collection, nếu fetch plan cuối cùng tạo join làm nhân bản parent, pagination vẫn có thể phát sinh vấn đề.

### 18.1. To-one và to-many khác nhau

| Association | Cardinality | Tác động thường gặp khi join fetch |
|---|---|---|
| ManyToOne | Mỗi parent tối đa một target | Không nhân bản parent nếu FK/mapping đúng |
| OneToOne | Mỗi parent tối đa một target | Thường không nhân bản parent nếu uniqueness đúng |
| OneToMany | Một parent có nhiều child | Nhân bản parent theo số child |
| ManyToMany | Một parent có nhiều target | Nhân bản parent theo số liên kết |

### 18.2. Không đặt EAGER để né LazyInitializationException

Nếu collection bị truy cập sau khi EntityManager đóng, lỗi LazyInitializationException có thể xuất hiện. Chuyển toàn bộ collection sang EAGER chỉ để tránh lỗi này có thể khiến mọi query đều tải collection không cần thiết và tạo thêm N+1/Cartesian multiplication.

Hãy chọn fetch plan ở use case:

- Danh sách: DTO/projection và aggregate.
- Chi tiết một đơn: fetch graph phù hợp.
- Trang parent nhiều đơn: query ID rồi fetch bounded graph hoặc batch fetching.
- Collection cực lớn: trang child riêng.

## 19. Index hỗ trợ query phân trang parent

Ví dụ query:

~~~sql
SELECT id
FROM purchase_orders
WHERE status = 'CONFIRMED'
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Một index có thể phù hợp:

~~~sql
CREATE INDEX idx_orders_status_created_id
ON purchase_orders(status, created_at DESC, id DESC);
~~~

Query fetch collection thứ hai:

~~~sql
SELECT *
FROM order_items
WHERE order_id IN (...);
~~~

có thể hưởng lợi từ:

~~~sql
CREATE INDEX idx_order_items_order_id
ON order_items(order_id);
~~~

Index cần được chọn dựa trên cardinality, tần suất query, tỷ lệ ghi và execution plan. Index không làm giảm số lượng item cần trả về; nếu một trang chứa một order có 50.000 item thì query child vẫn phải đọc 50.000 hàng khi yêu cầu lấy tất cả.

## 20. Đo xem pagination có thật sự ở database không

### 20.1. Bật log SQL Hibernate

Trong môi trường development/test:

~~~yaml
spring:
  jpa:
    show-sql: false
    properties:
      hibernate:
        format_sql: true
        generate_statistics: true

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

Logger bind parameter có thể chứa dữ liệu nhạy cảm; chỉ bật ở môi trường phù hợp và trong thời gian ngắn.

Khi kiểm tra query phân trang, hãy tìm:

- SQL query đầu tiên có LIMIT/OFFSET hoặc cú pháp tương ứng của dialect không?
- Nếu có collection fetch join, Hibernate có phát cảnh báo HHH90003004 không?
- Query có lấy tất cả các hàng join mà không có giới hạn database không?
- Có thêm một count query không?
- Có nhiều query lazy N+1 sau khi trả danh sách không?

### 20.2. Hibernate Statistics

~~~java
SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);
Statistics statistics = sessionFactory.getStatistics();

long statementsBefore = statistics.getPrepareStatementCount();
long loadsBefore = statistics.getEntityLoadCount();

// Chạy đúng một use case phân trang.

long statementDelta =
    statistics.getPrepareStatementCount() - statementsBefore;
long entityLoadDelta =
    statistics.getEntityLoadCount() - loadsBefore;
~~~

Statistics là bộ đếm tích lũy ở SessionFactory. Phép trừ trước/sau chỉ có ý nghĩa rõ khi test cô lập, không có request khác cùng tăng counter. entityLoadCount và statement count không thay thế việc đo số hàng SQL thực tế.

### 20.3. PostgreSQL EXPLAIN ANALYZE

Lấy SQL Hibernate sinh ra và tham số tương ứng, rồi kiểm tra plan:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.id, o.created_at, o.status
FROM purchase_orders o
WHERE o.status = 'CONFIRMED'
ORDER BY o.created_at DESC, o.id DESC
LIMIT 20;
~~~

Xem:

- Index Scan hay Seq Scan.
- Actual rows và loops.
- Sort có xảy ra không, có spill ra disk không.
- Shared hit/read buffers.
- Thời gian thực thi.

EXPLAIN ANALYZE thực sự chạy câu SELECT; chỉ chạy trên môi trường và dữ liệu phù hợp. Với query collection join, so sánh actual rows của join với số parent cuối cùng. Nếu page 20 parent nhưng DB trả 40.000 joined rows, đó là tín hiệu phải xem lại fetch plan.

### 20.4. Đo heap và số entity được hydrate

Một query có thể chỉ là một prepared statement nhưng hydrate hàng chục nghìn entity. Theo dõi:

- Heap trước/sau query và sau GC.
- Entity load count.
- Số OrderItem được khởi tạo.
- Thời gian query và thời gian map/serialize.
- Bytes trả từ database/driver nếu công cụ quan sát hỗ trợ.

Không suy luận “một SQL là nhanh” hoặc “20 entity gốc nghĩa là chỉ 20 object”. Collection fetch có thể tạo rất nhiều child object và metadata trong persistence context.

## 21. Kiểm thử regression cho collection pagination

Một integration test hữu ích nên tạo dữ liệu có độ phân bố child không đồng đều:

| Order | Số items |
|---|---:|
| A | 1 |
| B | 2 |
| C | 30 |
| D | 0 |
| E | 100 |

Sau đó:

1. Query trang 2 parent có fetch join collection.
2. Kiểm tra log cảnh báo hoặc fail-fast exception khi bật setting.
3. Chạy chiến lược ID-first rồi fetch-by-IDs.
4. Assert số parent đúng page size (nếu đủ dữ liệu).
5. Assert mỗi collection có đúng số child trong DB.
6. Assert thứ tự parent giống query ID đầu tiên.
7. Đếm số hàng/entity được hydrate để thấy chi phí khác nhau.

### 21.1. Skeleton test

~~~java
@SpringBootTest
class PurchaseOrderPaginationTest {
    @Autowired PurchaseOrderQueryService queryService;
    @Autowired TestEntityManager testEntityManager;

    @Test
    void idFirstPaginationReturnsCompleteCollections() {
        // Arrange:
        // - Tạo nhiều Order có số items khác nhau, gồm một Order có collection lớn.
        // - Flush dữ liệu fixture.
        // Act:
        // - Lấy page ID rồi fetch graph theo IDs.
        // Assert:
        // - Số parent đúng page size.
        // - Số items của từng parent khớp DB.
        // - Thứ tự parent đúng theo createdAt DESC, id DESC.
    }
}
~~~

Đây là skeleton hướng dẫn, cần bổ sung fixture, import và dữ liệu thực tế. Với Hibernate fail-fast, nên có một test riêng mong đợi exception cho query collection fetch có pagination. Tùy cách Spring Data thực thi, exception có thể được wrap trong data access exception.

### 21.2. Test phải quan sát database/context mới

Sau khi setup fixture hoặc chạy query, hãy flush() và clear() khi cần, hoặc mở transaction mới để kiểm tra dữ liệu. Nếu test chỉ đọc collection đang nằm trong first-level cache, nó có thể kiểm tra object đã có trong memory thay vì chứng minh query nạp đầy đủ dữ liệu từ database.

## 22. Các lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Hướng giải quyết |
|---|---|---|
| Page 20 nhưng SQL trả hàng chục nghìn hàng | Collection fetch join khiến pagination trong memory | Page ID trước, fetch collection theo ID |
| Hibernate cảnh báo HHH90003004 | Pagination kết hợp collection fetch | Bật fail-on-pagination-over-collection-fetch và sửa query |
| distinct vẫn không giảm dữ liệu đáng kể | Các hàng child có giá trị khác nhau nên SQL row vẫn khác | Đổi fetch strategy, không dựa vào DISTINCT |
| Trang có ít parent hơn mong đợi khi LIMIT áp dụng trên join | LIMIT cắt hàng child trước khi đủ parent | Không paginate trực tiếp trên collection join |
| Collection của parent cuối bị thiếu | Pagination ở SQL row level | Fetch collection đầy đủ bằng query thứ hai |
| Page chạy hai query, query count sai | Count join đếm child row hoặc count query phức tạp | Viết countQuery theo parent, dùng EXISTS/count distinct |
| MultipleBagFetchException | Fetch nhiều bag collection cùng lúc | Chia fetch thành nhiều query hoặc dùng batch fetching |
| Đổi List thành Set nhưng query vẫn chậm | Cartesian multiplication vẫn còn | Giảm số collection join, chia query |
| EntityGraph vẫn phát cảnh báo | EntityGraph yêu cầu collection fetch | Kiểm tra SQL, dùng ID-first/DTO/batch |
| N+1 sau khi lấy trang root | Truy cập LAZY collection từng parent | @BatchSize/default batch hoặc SUBSELECT |
| Một parent có collection quá lớn gây OOM | Batch fetch vẫn tải mọi child của parent | Phân trang child riêng hoặc aggregate |
| Query ID và fetch graph cho thứ tự khác nhau | IN không giữ thứ tự input | Khôi phục thứ tự bằng map theo ID |
| Hai query trong ID-first thấy dữ liệu khác nhau | Dữ liệu thay đổi giữa statement/isolation | Chọn semantics, snapshot/lock phù hợp |
| OFFSET trang sâu chậm | Database phải bỏ qua nhiều hàng | Keyset pagination |
| SQL một câu nhưng heap tăng mạnh | Nhiều entity/collection được hydrate | DTO/projection, đo entity load và số hàng |

## 23. Hướng dẫn chọn chiến lược theo màn hình

| Use case | Chiến lược thường phù hợp |
|---|---|
| Danh sách đơn hàng chỉ hiện ID, ngày, trạng thái, tổng tiền | DTO projection trên root, aggregate nếu cần |
| Danh sách đơn hàng cần tên khách (to-one) | Fetch join Customer hoặc DTO projection |
| Trang đơn hàng cần tất cả items, collection có kích thước vừa | Hai pha: page ID rồi fetch items theo ID |
| Trang đơn hàng cần vài thuộc tính tổng hợp của items | DTO aggregate, không tải toàn bộ collection |
| Chi tiết một đơn với số items vừa phải | Fetch join collection trong query không phân trang |
| Chi tiết một đơn có hàng chục nghìn items | Trang child riêng, không fetch toàn bộ |
| Trang parent rồi code truy cập collection trên nhiều parent | Batch fetching hoặc SUBSELECT, đo query |
| Danh sách có nhiều collection độc lập | Tách query theo collection hoặc DTO riêng |
| Lịch sử hàng triệu bản ghi với trang rất sâu | Keyset/cursor pagination |
| Báo cáo cần snapshot nhất quán | Xác định isolation/read model và query projection |

## 24. Quy trình thiết kế một query phân trang có collection

Khi viết repository method, thực hiện theo trình tự:

1. **Xác định đơn vị phân trang:** parent hay child? Page 20 PurchaseOrder khác Page 20 OrderItem.
2. **Liệt kê dữ liệu thực sự cần hiển thị:** field root, to-one, số lượng child hay toàn bộ collection?
3. **Ước lượng cardinality:** mỗi parent có bao nhiêu child, có parent ngoại lệ với collection rất lớn không?
4. **Chọn query đầu tiên:** page root ID hoặc DTO, có order ổn định và count đúng.
5. **Chọn fetch cho dữ liệu liên quan:** to-one join, ID-first collection fetch, batch/subselect hoặc query child riêng.
6. **Giữ thứ tự trang:** query IN không đảm bảo thứ tự, cần map theo ID.
7. **Đặt ranh giới transaction:** xác định có chấp nhận dữ liệu đổi giữa các query hay cần snapshot/lock.
8. **Bật fail-fast:** không để pagination over collection fetch âm thầm đi vào production.
9. **Đo SQL và heap:** xác nhận database thực hiện LIMIT ở query parent và số joined rows được kiểm soát.
10. **Kiểm thử collection đầy đủ:** dùng dữ liệu có cardinality lệch, không chỉ test mọi parent có một child.

## 25. Bài thực hành tổng hợp

Xây dựng ứng dụng Spring Boot + Hibernate + PostgreSQL với các entity:

- PurchaseOrder có createdAt, status, customer.
- OrderItem có order, product, quantity, unitPrice.
- Payment và Shipment là hai collection khác của PurchaseOrder.

### Bài A — Quan sát pagination trong memory

1. Tạo 100 đơn hàng với số OrderItem khác nhau: có đơn 0, 1, 5, 30 và 1.000 item.
2. Viết query Page<PurchaseOrder> kết hợp left join fetch o.items.
3. Quan sát warning HHH90003004, SQL và số hàng trả về.
4. Bật hibernate.query.fail_on_pagination_over_collection_fetch=true và xác nhận query bị từ chối.
5. Ghi nhận heap/entity load count khi page size là 10 và 20.

### Bài B — Sửa bằng hai pha

1. Viết query lấy ID theo status và thứ tự createdAt DESC, id DESC.
2. Viết query fetch items theo ID, không pagination.
3. Khôi phục thứ tự ID từ query đầu.
4. Viết count query đếm parent, không đếm item.
5. Kiểm tra tất cả collection của parent trong trang đầy đủ.

### Bài C — So sánh các fetch strategy

Chạy cùng một trang với:

- ID-first + collection fetch.
- Root page + @BatchSize.
- Root page + FetchMode.SUBSELECT.
- DTO projection chỉ lấy số item và tổng tiền.

Ghi số statement, SQL rows, entity loads, heap và p95 query time. Không kết luận chỉ từ số statement; một câu join khổng lồ có thể đắt hơn ba câu nhỏ.

### Bài D — Nhiều collection

1. Thử fetch items và payments cùng lúc.
2. Quan sát Cartesian multiplication hoặc MultipleBagFetchException.
3. Tách thành hai query theo ID.
4. So sánh tổng rows và dữ liệu truyền.
5. Không đổi collection List thành Set nếu chưa xác định rõ semantics và equality.

### Bài E — Keyset và dữ liệu thay đổi

1. Tạo hàng nghìn đơn với timestamp trùng nhau.
2. Phân trang bằng OFFSET và bằng keyset (createdAt, id).
3. Trong lúc lật trang, insert một đơn mới và cập nhật một đơn cũ.
4. Quan sát bản ghi lặp/bị bỏ qua theo từng semantics.
5. Chọn cursor contract phù hợp cho màn hình.

## 26. Nguyên tắc ghi nhớ

Collection fetch join là công cụ hữu ích để tải parent và child trong một query, đặc biệt ở trang chi tiết một entity. Nhưng khi kết hợp với pagination, cần nhớ:

1. **Một parent có nhiều hàng SQL** sau collection join.
2. LIMIT/OFFSET trên hàng join không tương đương giới hạn số parent đầy đủ.
3. Hibernate có thể phân trang trong bộ nhớ để tránh collection bị cắt, dẫn tới tải quá nhiều hàng và entity.
4. DISTINCT không loại bỏ row multiplication khi các cột child khác nhau.
5. Pageable, Slice hay EntityGraph không tự làm collection fetch join an toàn.
6. **Page ID trước, fetch graph theo ID sau** là một chiến lược dễ kiểm soát; query thứ hai không áp dụng pagination.
7. Batch fetching, SUBSELECT và DTO projection có thể phù hợp hơn tùy dữ liệu cần tải.
8. Nhiều collection join có thể tạo Cartesian multiplication hoặc MultipleBagFetchException.
9. Collection cực lớn cần được phân trang riêng hoặc truy vấn aggregate.
10. Xác nhận bằng SQL log, actual rows, execution plan, heap và integration test có cardinality thực tế.

Một trang nhỏ chỉ thật sự nhỏ khi **database giới hạn đúng tập parent trước khi tải các collection**. Hãy để page query quyết định những entity gốc cần hiển thị, rồi tải đúng phần dữ liệu liên quan cho tập entity ấy. Cách này giữ collection đầy đủ, tránh xử lý toàn bộ kết quả trong bộ nhớ và giúp chi phí truy vấn dự đoán được khi dữ liệu tăng trưởng.
