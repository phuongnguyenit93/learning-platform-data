# Phân trang, batch insert/update và kiểm soát N+1

Trong ứng dụng Spring Boot dùng Spring Data JPA và Hibernate, ba vấn đề thường ảnh hưởng trực tiếp đến hiệu năng truy cập dữ liệu là phân trang, ghi dữ liệu theo batch và truy vấn N+1.

- **Phân trang (pagination)** giới hạn số dòng trả về trong một lần đọc, giúp API kiểm soát payload, bộ nhớ và thời gian phản hồi.
- **Batch insert/update** gom nhiều thao tác ghi để giảm số lần trao đổi giữa ứng dụng và database, đồng thời kiểm soát lượng dữ liệu được giữ trong persistence context.
- **N+1** xảy ra khi ứng dụng tải một tập entity rồi phát sinh thêm một truy vấn cho từng entity hoặc từng quan hệ, làm số lượng SQL tăng theo số bản ghi.

Ba vấn đề liên quan với nhau. Một API phân trang đơn hàng nhưng truy cập LAZY đến danh sách mặt hàng có thể tạo N+1. Một job import gọi save cho hàng chục nghìn entity trong một transaction có thể tiêu tốn nhiều bộ nhớ dù đã dùng saveAll. Một truy vấn fetch join collection có thể giải quyết N+1 nhưng lại làm phân trang sai hoặc buộc Hibernate phân trang trong bộ nhớ.

Muốn tối ưu đúng, cần xem SQL thực tế, execution plan, số lần round trip, kích thước dữ liệu, persistence context và ranh giới transaction. Chỉ thêm annotation hoặc bật một thuộc tính cấu hình không bảo đảm vấn đề đã được giải quyết.

## 1. Phân trang với Spring Data JPA

Spring Data JPA hỗ trợ phân trang qua interface Pageable và các kiểu kết quả như Page, Slice hoặc List. Repository nhận Pageable sẽ chuyển thông tin trang, kích thước trang và sort xuống JPA provider để tạo câu SQL phù hợp với dialect của database.

Ví dụ entity đơn hàng:

~~~java
@Entity
@Table(name = "ORDERS")
public class Order {
    @Id
    private Long id;

    @Column(name = "ORDER_DATE")
    private LocalDateTime orderDate;

    @Column(name = "STATUS")
    private String status;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "CUSTOMER_ID")
    private Customer customer;
}
~~~

Repository:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {
    Page<Order> findByStatus(String status, Pageable pageable);
}
~~~

Service:

~~~java
@Service
@RequiredArgsConstructor
public class OrderService {
    private final OrderRepository orderRepository;

    @Transactional(readOnly = true)
    public Page<OrderResponse> findOpenOrders(int page, int size) {
        Pageable pageable = PageRequest.of(
            page,
            size,
            Sort.by(
                Sort.Order.desc("orderDate"),
                Sort.Order.desc("id")
            )
        );

        return orderRepository.findByStatus("OPEN", pageable)
            .map(OrderResponse::from);
    }
}
~~~

Controller có thể nhận page và size từ query parameter:

~~~java
@GetMapping("/orders")
public Page<OrderResponse> findOrders(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {

    return orderService.findOpenOrders(page, size);
}
~~~

PageRequest đánh số trang từ 0. Trang đầu tiên là page 0, trang tiếp theo là page 1. Cần kiểm tra và giới hạn size từ request để client không yêu cầu hàng trăm nghìn dòng trong một lần gọi.

### Page, Slice và List khác nhau thế nào?

| Kiểu kết quả | Nội dung | Chi phí thường gặp | Khi nên dùng |
|---|---|---|---|
| Page<T> | Nội dung trang, số trang, tổng số phần tử và thông tin điều hướng | Thường cần thêm count query để tính tổng | UI cần tổng số dòng hoặc số trang |
| Slice<T> | Nội dung và thông tin còn trang tiếp theo hay không | Thường lấy thêm một dòng để xác định hasNext | Cuộn hoặc tải thêm, không cần tổng số dòng |
| List<T> với Pageable | Danh sách của phạm vi trang | Không cung cấp tổng số phần tử | Chỉ cần một trang dữ liệu, không cần metadata Page/Slice |

Page hữu ích cho màn hình cần hiển thị “1–20 trên tổng 3.450 bản ghi”. Đổi lại, Spring Data thường thực hiện truy vấn lấy dữ liệu và một count query. Count có thể đắt với truy vấn join, distinct hoặc điều kiện phức tạp.

Slice phù hợp khi giao diện chỉ cần nút “Tải thêm” hoặc biết còn dữ liệu hay không. Framework thường yêu cầu nhiều hơn page size một dòng; nếu có dòng dư, Slice.hasNext() là true. Không cần đếm toàn bộ kết quả.

Ví dụ repository trả Slice:

~~~java
Slice<OrderSummary> findByStatus(String status, Pageable pageable);
~~~

Nếu API không cần tổng số dòng, chọn Slice có thể giảm đáng kể chi phí trên bảng lớn.

### Count query và truy vấn join

Khi dùng Page với @Query có join, count query tự sinh có thể phức tạp hoặc đếm sai do một entity xuất hiện nhiều lần trong join. Nên khai báo countQuery rõ ràng khi cần:

~~~java
@Query(
    value = """
        select o
        from Order o
        join o.customer c
        where o.status = :status
          and c.region = :region
        """,
    countQuery = """
        select count(o)
        from Order o
        join o.customer c
        where o.status = :status
          and c.region = :region
        """
)
Page<Order> findOrders(
    @Param("status") String status,
    @Param("region") String region,
    Pageable pageable
);
~~~

Nếu join collection làm nhân bản dòng gốc, có thể cần count distinct hoặc thiết kế lại query. Ví dụ:

~~~sql
SELECT COUNT(DISTINCT o.id)
FROM orders o
JOIN order_items i ON i.order_id = o.id
WHERE i.product_id = :productId;
~~~

Count query phải đếm đúng đơn vị mà API phân trang, thường là số entity gốc chứ không phải số dòng sau join.

### Sắp xếp phải ổn định

Khi phân trang, luôn nên có thứ tự xác định. Nếu chỉ sort theo một cột có thể trùng, các dòng cùng giá trị có thể đổi vị trí giữa các lần gọi. Thêm một khóa duy nhất làm tie-breaker, thường là primary key.

~~~java
Pageable pageable = PageRequest.of(
    page,
    size,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
~~~

Không ghép trực tiếp tên cột sort từ chuỗi người dùng vào native SQL. Với Spring Data Sort, chỉ cho phép các thuộc tính nằm trong allowlist của API. Sort theo field không tồn tại hoặc expression tùy ý có thể gây lỗi và tạo rủi ro khi dựng query động.

### Phân trang offset và giới hạn của trang sâu

Phân trang truyền thống dùng offset và limit/fetch first. Về khái niệm, trang thứ 1000 với page size 20 cần bỏ qua 19.980 dòng trước khi lấy 20 dòng tiếp theo.

Ví dụ SQL minh họa:

~~~sql
SELECT order_id, order_date, status
FROM orders
WHERE status = 'OPEN'
ORDER BY order_date DESC, order_id DESC
OFFSET 19980 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

Oracle hỗ trợ cú pháp OFFSET/FETCH từ 12c. Hibernate/Spring Data sẽ sinh cú pháp theo dialect và phiên bản database; không nên tự viết tay một cú pháp pagination chung cho mọi phiên bản.

Với offset lớn, database có thể phải đọc, sắp xếp hoặc bỏ qua nhiều dòng trước khi trả trang. Hiệu năng giảm theo độ sâu trang, đặc biệt khi cột lọc/sort thiếu index phù hợp.

Offset pagination cũng có thể gây hiện tượng lặp hoặc bỏ sót dòng khi dữ liệu thay đổi giữa hai request. Ví dụ client đọc trang 1, sau đó có một dòng mới được thêm vào đầu danh sách trước khi client đọc trang 2; offset trang 2 có thể dịch chuyển và trả lại một dòng đã thấy.

### Keyset/seek pagination

Keyset pagination dùng giá trị cuối cùng của trang trước làm mốc để lấy trang tiếp theo. Nó phù hợp với danh sách lớn, thường chỉ đọc tiến về phía trước và có khóa sort ổn định.

Giả sử sắp xếp theo createdAt giảm dần rồi id giảm dần. Sau trang đầu, client giữ lastCreatedAt và lastId của dòng cuối. Truy vấn trang tiếp theo:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE status = :status
  AND (
       created_at < :lastCreatedAt
       OR (created_at = :lastCreatedAt AND order_id < :lastId)
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :pageSize ROWS ONLY;
~~~

Có thể triển khai bằng repository query tùy database và JPA provider:

~~~java
@Query("""
    select o
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
    """)
List<Order> findNextOrders(
    @Param("status") String status,
    @Param("lastCreatedAt") LocalDateTime lastCreatedAt,
    @Param("lastId") Long lastId,
    Pageable limit
);
~~~

Keyset pagination cần xử lý rõ trang đầu (chưa có cursor), NULL trong cột sort, chiều sort và các cột tạo thành khóa thứ tự. Nên chọn cột sort không NULL hoặc định nghĩa thứ tự NULL nhất quán. Cursor trả cho client có thể chứa lastCreatedAt và lastId, được serialize an toàn và không cho client sửa tùy ý.

Keyset thường hiệu quả hơn offset trên dữ liệu lớn khi có index phù hợp, nhưng không hỗ trợ nhảy trực tiếp đến một số trang bất kỳ một cách tự nhiên. Đây là lựa chọn dựa trên UX, không phải thay thế bắt buộc cho mọi API.

## 2. Phân trang với quan hệ JPA

Một vấn đề quan trọng là phân trang entity có quan hệ. Nếu query lấy Order và fetch join collection orderItems, số dòng SQL có thể là số tổ hợp Order × OrderItem, không còn tương ứng một dòng cho một Order.

Ví dụ:

~~~java
@Query("""
    select distinct o
    from Order o
    left join fetch o.items
    where o.status = :status
    """)
Page<Order> findOrdersWithItems(
    @Param("status") String status,
    Pageable pageable
);
~~~

Query trên có vẻ giải quyết N+1 vì lấy items cùng lúc, nhưng phân trang trên collection fetch join có thể không thực hiện được đúng ở database. Hibernate có thể phải lấy toàn bộ kết quả join rồi phân trang trong bộ nhớ, dẫn đến tiêu thụ nhiều bộ nhớ và thời gian. Một số phiên bản/cấu hình có thể cảnh báo khi tình huống này xảy ra.

Không nên fetch join một collection lớn trong query phân trang chính. Có thể bật chế độ fail fast để phát hiện sớm:

~~~properties
spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

### Chiến lược hai truy vấn

Một cách phổ biến là:

1. Phân trang ID của entity gốc.
2. Dùng danh sách ID đó fetch các quan hệ cần thiết trong một query thứ hai.
3. Khôi phục thứ tự ban đầu theo danh sách ID nếu query thứ hai không giữ thứ tự.

Repository:

~~~java
@Query("""
    select o.id
    from Order o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
Page<Long> findOrderIds(
    @Param("status") String status,
    Pageable pageable
);

@Query("""
    select distinct o
    from Order o
    left join fetch o.customer
    left join fetch o.items
    where o.id in :ids
    """)
List<Order> findWithDetailsByIdIn(
    @Param("ids") Collection<Long> ids
);
~~~

Service:

~~~java
@Transactional(readOnly = true)
public Page<OrderResponse> findOrderPage(
        String status, Pageable pageable) {

    Page<Long> idPage = repository.findOrderIds(status, pageable);

    if (idPage.isEmpty()) {
        return new PageImpl<>(
            List.of(),
            pageable,
            idPage.getTotalElements()
        );
    }

    List<Long> ids = idPage.getContent();
    List<Order> loaded = repository.findWithDetailsByIdIn(ids);

    Map<Long, Order> byId = loaded.stream()
        .collect(Collectors.toMap(Order::getId, Function.identity()));

    List<OrderResponse> content = ids.stream()
        .map(byId::get)
        .filter(Objects::nonNull)
        .map(OrderResponse::from)
        .toList();

    return new PageImpl<>(
        content,
        pageable,
        idPage.getTotalElements()
    );
}
~~~

Hai truy vấn này giới hạn số entity gốc trước khi fetch collection. Nếu trang có 20 order, query thứ hai chỉ tải quan hệ của 20 order đó. Cần chú ý giới hạn số bind parameter của database khi page size lớn, và không truyền collection ID quá lớn.

Trong ví dụ, Page<Long> thực hiện count query để tính total. Nếu không cần total, có thể dùng Slice<Long> hoặc một query lấy page size + 1 ID.

### EntityGraph cho quan hệ cần tải

Nếu chỉ cần tải quan hệ to-one như customer, dùng EntityGraph có thể rõ ràng hơn:

~~~java
@EntityGraph(attributePaths = {"customer"})
Page<Order> findByStatus(String status, Pageable pageable);
~~~

EntityGraph chỉ định quan hệ cần fetch cho query. Nó không bảo đảm mọi provider sẽ tạo đúng một SQL đơn giản trong mọi trường hợp; hãy xem SQL được sinh ra. Với collection lớn, cần kiểm tra kỹ việc kết hợp EntityGraph và pagination.

## 3. Batch insert với Hibernate và Spring Data JPA

Batch insert là gom nhiều lệnh INSERT thành JDBC batch để giảm số lần round trip giữa ứng dụng và database. Nếu ứng dụng insert 1.000 dòng, việc gửi từng câu INSERT riêng có thể tạo nhiều lần giao tiếp. JDBC batch cho phép driver gửi một nhóm lệnh theo batch.

Tuy nhiên, cần phân biệt:

- saveAll() của Spring Data JPA là API lưu một iterable entity. Nó không tự bảo đảm Hibernate gửi JDBC batch.
- Hibernate JDBC batching cần được cấu hình và loại identifier generator phải hỗ trợ batching.
- Persistence context vẫn giữ entity được quản lý cho đến khi flush/clear hoặc transaction kết thúc.
- Database vẫn phải thực hiện từng row insert/update; batch chủ yếu giảm chi phí round trip và có thể cải thiện throughput.

### Cấu hình Hibernate batch

Với Spring Boot, có thể cấu hình trong application.properties:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
spring.jpa.properties.hibernate.jdbc.batch_versioned_data=true
~~~

Ý nghĩa:

| Thuộc tính | Tác dụng |
|---|---|
| hibernate.jdbc.batch_size | Số statement tối đa gom vào một JDBC batch |
| hibernate.order_inserts | Sắp xếp insert theo entity type và khóa để tăng cơ hội gom batch |
| hibernate.order_updates | Sắp xếp update để gom batch và giảm một số tình huống deadlock |
| hibernate.jdbc.batch_versioned_data | Cho phép batch thao tác với entity có version khi driver trả update count phù hợp |

Giá trị 50 chỉ là điểm bắt đầu để đo thử. Batch size phù hợp phụ thuộc kích thước row, số cột, driver, network, database, memory và concurrency. Batch quá lớn có thể tăng bộ nhớ, thời gian giữ transaction và áp lực redo/undo ở Oracle.

Có thể cấu hình fetch size riêng cho đọc dữ liệu lớn, nhưng fetch size không phải batch size ghi. Hai thuộc tính giải quyết hai vấn đề khác nhau.

### Identifier generation ảnh hưởng batching

Một hạn chế quan trọng của Hibernate là chiến lược IDENTITY thường ngăn JDBC insert batching cho entity dùng generator đó, vì Hibernate cần thực thi INSERT để lấy generated key của từng dòng. Với Oracle, dùng sequence generator thường phù hợp hơn khi muốn tận dụng batching.

Ví dụ:

~~~java
@Entity
@Table(name = "ORDERS")
public class Order {
    @Id
    @SequenceGenerator(
        name = "order_seq_gen",
        sequenceName = "ORDER_SEQ",
        allocationSize = 50
    )
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "order_seq_gen"
    )
    private Long id;

    // Các thuộc tính khác.
}
~~~

allocationSize cho phép Hibernate cấp phát ID theo nhóm bằng sequence optimizer phù hợp, giảm số lần gọi sequence. Cần bảo đảm cấu hình sequence/schema migration tương thích với optimizer và phiên bản Hibernate. Không đổi IDENTITY sang SEQUENCE trong hệ thống đang chạy mà chưa đánh giá dữ liệu, DDL và khả năng tương thích.

### Insert nhiều entity bằng EntityManager

Đối với job import lớn, dùng persist() theo từng entity và flush/clear theo batch:

~~~java
@Service
@RequiredArgsConstructor
public class OrderImportService {
    private static final int BATCH_SIZE = 50;

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void importOrders(List<Order> orders) {
        for (int i = 0; i < orders.size(); i++) {
            entityManager.persist(orders.get(i));

            if ((i + 1) % BATCH_SIZE == 0) {
                entityManager.flush();
                entityManager.clear();
            }
        }

        entityManager.flush();
        entityManager.clear();
    }
}
~~~

flush() đồng bộ các thay đổi đang chờ trong persistence context xuống database. Nếu Hibernate batching được bật, các INSERT đủ điều kiện sẽ được gom theo JDBC batch.

clear() xóa toàn bộ entity đang được quản lý khỏi persistence context. Điều này giúp tránh giữ hàng chục nghìn object trong bộ nhớ, nhưng các entity đã persist trở thành detached. Sau clear, không nên tiếp tục sửa một entity cũ và kỳ vọng Hibernate tự theo dõi thay đổi.

Cần kiểm tra quan hệ cascade, entity graph và callback trước khi flush/clear theo batch. Nếu entity cần tham chiếu đến entity cha đã detach, có thể phải giữ khóa hoặc thiết kế lại bước insert.

### saveAll không đồng nghĩa với JDBC batch

Ví dụ:

~~~java
orderRepository.saveAll(orders);
~~~

Đây là cách viết ngắn gọn để lưu danh sách, nhưng implementation của repository có thể lặp qua từng entity và gọi save. Hibernate chỉ gửi JDBC batch khi batching được cấu hình và các điều kiện thực thi phù hợp.

Với danh sách rất lớn, saveAll() trong một transaction có thể làm persistence context giữ toàn bộ entity đến cuối transaction. Có thể chia thành các chunk, mỗi chunk chạy trong transaction riêng, hoặc dùng EntityManager với flush/clear định kỳ.

Nếu chia transaction theo chunk, cần xác định rõ semantics khi một chunk lỗi: các chunk trước có thể đã commit, trong khi chunk hiện tại rollback. Với import phải nguyên tử toàn bộ, cần chiến lược staging và kiểm tra trước khi publish dữ liệu.

## 4. Batch update

Có hai hướng cập nhật batch thường gặp:

1. Tải entity, thay đổi thuộc tính rồi flush để Hibernate tạo UPDATE batch.
2. Dùng bulk JPQL UPDATE để cập nhật trực tiếp nhiều dòng trong một câu SQL.

Hai cách có semantics khác nhau.

### Batch update qua entity state

~~~java
@Transactional
public void markOrdersAsArchived(List<Long> orderIds) {
    List<Order> orders = entityManager.createQuery(
        "select o from Order o where o.id in :ids",
        Order.class
    )
    .setParameter("ids", orderIds)
    .getResultList();

    for (Order order : orders) {
        order.setStatus("ARCHIVED");
    }

    entityManager.flush();
}
~~~

Hibernate dirty checking phát hiện entity thay đổi và sinh UPDATE. Với hibernate.jdbc.batch_size và hibernate.order_updates=true, các update có thể được gom batch.

Cách này phù hợp khi cần domain logic, validation, callback hoặc optimistic locking của entity. Tuy nhiên, nó tải entity vào persistence context và tiêu thụ bộ nhớ. Với số lượng lớn, xử lý theo chunk và flush/clear.

### Bulk JPQL UPDATE

Nếu chỉ cần đổi một cột theo điều kiện, bulk update có thể hiệu quả hơn:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query("""
        update Order o
        set o.status = :newStatus
        where o.status = :oldStatus
        """)
    int updateStatus(
        @Param("oldStatus") String oldStatus,
        @Param("newStatus") String newStatus
    );
}
~~~

Service:

~~~java
@Transactional
public int archiveClosedOrders() {
    return orderRepository.updateStatus("CLOSED", "ARCHIVED");
}
~~~

Bulk JPQL được chuyển thành một câu UPDATE tác động trực tiếp đến các dòng phù hợp. Nó không cần load từng entity vào persistence context, do đó có thể giảm memory và round trip.

Tuy nhiên, bulk update có những hệ quả quan trọng:

- Nó bỏ qua dirty checking của các entity đang được quản lý.
- Không chạy đầy đủ entity lifecycle callback như khi cập nhật từng entity.
- Không áp dụng cascade theo cách cập nhật entity thông thường.
- Persistence context có thể đang chứa bản entity cũ, vì vậy cần flush trước và clear/refresh sau.
- Optimistic locking với @Version không tự động được áp dụng như update từng entity; cần thiết kế điều kiện version và cập nhật version rõ ràng nếu nghiệp vụ yêu cầu.

Không dùng bulk update nếu logic nghiệp vụ phụ thuộc callback, cascade hoặc kiểm tra trên từng entity mà chưa chuyển logic đó sang một cơ chế phù hợp.

### Cập nhật version khi bulk update

Nếu entity có trường @Version, bulk JPQL update thường không tự tăng version theo cơ chế dirty checking. Có thể cập nhật version rõ ràng:

~~~java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
    update Order o
    set o.status = :status,
        o.version = o.version + 1
    where o.id = :id
      and o.version = :expectedVersion
    """)
int updateStatusWithVersion(
    @Param("id") Long id,
    @Param("status") String status,
    @Param("expectedVersion") long expectedVersion
);
~~~

Nếu kết quả update count bằng 0, có thể entity không tồn tại hoặc version đã thay đổi. Ứng dụng cần quyết định cách phân biệt hai trường hợp nếu nghiệp vụ cần thông báo cụ thể.

### JPQL bulk update và native SQL

Native SQL có thể tận dụng cú pháp database riêng, nhưng gắn chặt với schema và dialect. Dùng JPQL bulk update khi biểu thức có thể diễn đạt bằng entity model; dùng native SQL khi thật sự cần tính năng đặc thù hoặc query tối ưu đã được đo kiểm.

Với Oracle, kiểm tra execution plan, index, redo/undo và số dòng bị tác động. Một UPDATE một câu có thể nhanh hơn hàng nghìn UPDATE riêng lẻ, nhưng vẫn có thể tạo lượng redo/undo lớn và khóa nhiều dòng trong một transaction.

## 5. Chia batch và quản lý transaction

Batch size của Hibernate, kích thước chunk nghiệp vụ và số dòng trong một transaction là ba khái niệm khác nhau.

- **JDBC batch size**: số statement Hibernate gom vào một lần executeBatch.
- **Chunk size**: số entity ứng dụng xử lý trước khi flush/clear hoặc chuyển sang chunk tiếp theo.
- **Transaction size**: số thao tác được commit/rollback cùng nhau.

Ví dụ batch size 50 và chunk size 500 có thể tạo khoảng 10 JDBC batch trong một chunk. Nếu mỗi chunk commit riêng, transaction size cũng là 500 entity. Nhưng nếu flush/clear mỗi 500 entity trong một transaction lớn, transaction size vẫn có thể là toàn bộ file import.

### Chunk transaction qua Spring

Một pattern thường dùng là service điều phối chunk và một bean khác thực thi mỗi chunk trong transaction riêng:

~~~java
@Service
@RequiredArgsConstructor
public class ImportCoordinator {
    private final ImportChunkWriter chunkWriter;

    public void importAll(List<OrderInput> inputs) {
        int chunkSize = 500;

        for (int start = 0; start < inputs.size(); start += chunkSize) {
            int end = Math.min(start + chunkSize, inputs.size());
            chunkWriter.writeChunk(inputs.subList(start, end));
        }
    }
}

@Service
@RequiredArgsConstructor
public class ImportChunkWriter {
    private final OrderRepository orderRepository;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeChunk(List<OrderInput> chunk) {
        List<Order> entities = chunk.stream()
            .map(Order::from)
            .toList();

        orderRepository.saveAll(entities);
        orderRepository.flush();
    }
}
~~~

Đặt writer ở bean riêng để lời gọi đi qua Spring proxy. Gọi một method @Transactional khác trong cùng object bằng self-invocation thường không kích hoạt transaction interceptor theo cách mong muốn.

REQUIRES_NEW tạo transaction độc lập cho mỗi chunk. Nếu chunk sau thất bại, các chunk trước đã commit vẫn còn. Chỉ chọn cách này khi nghiệp vụ chấp nhận import từng phần hoặc có cơ chế resume/đối soát. Nếu cần tất cả hoặc không có gì, dùng transaction lớn hoặc staging workflow phù hợp, nhưng phải đánh giá undo, redo, lock duration và thời gian rollback.

### Oracle và transaction lớn

Với Oracle, batch ghi lớn có thể tạo nhiều redo/undo, giữ row lock lâu, tăng áp lực buffer cache và ảnh hưởng workload khác. Transaction quá lớn còn làm rollback kéo dài và khó phục hồi khi job bị gián đoạn.

Cần đo:

- Thời gian mỗi chunk.
- Số dòng ghi và update count.
- CPU, logical reads, physical I/O.
- Redo/undo và thời gian commit.
- Lock contention và deadlock.
- Kích thước persistence context và heap JVM.

Không có một chunk size tối ưu cho mọi bảng. Bắt đầu với giá trị vừa phải, đo trên dữ liệu gần production và điều chỉnh theo giới hạn hệ thống.

## 6. N+1 là gì?

N+1 là mẫu truy vấn trong đó ứng dụng chạy một query lấy N entity gốc, rồi phát sinh thêm N query để lấy dữ liệu liên quan cho từng entity.

Ví dụ lấy 50 đơn hàng:

~~~java
List<Order> orders = orderRepository.findTop50ByStatus("OPEN");

for (Order order : orders) {
    String customerName = order.getCustomer().getName();
    // Dùng customerName.
}
~~~

Nếu quan hệ Order.customer là LAZY và chưa được fetch, Hibernate có thể chạy:

1. Một SELECT lấy 50 Order.
2. Một SELECT Customer cho từng Order nếu mỗi order tham chiếu customer khác nhau.

Tổng số query có thể là 1 + N. Nếu mỗi order có collection items và code truy cập collection, có thể phát sinh thêm truy vấn cho từng order.

Ví dụ log SQL minh họa:

~~~sql
SELECT ... FROM orders WHERE status = 'OPEN';

SELECT ... FROM customers WHERE customer_id = 101;
SELECT ... FROM customers WHERE customer_id = 102;
SELECT ... FROM customers WHERE customer_id = 103;
-- Lặp lại theo từng customer được truy cập.
~~~

N+1 không nhất thiết là đúng N query bổ sung: Hibernate có thể dùng persistence context cache để không truy vấn lại cùng một entity đã được load, nhưng số query vẫn có thể tăng theo số quan hệ khác nhau.

### Vì sao N+1 nguy hiểm?

- Mỗi query có round trip qua JDBC và network.
- Database phải parse/execute nhiều statement hoặc quản lý nhiều cursor.
- Connection bị sử dụng lâu hơn.
- Latency cộng dồn ngay cả khi mỗi query riêng lẻ rất nhanh.
- Tải tăng theo số dòng trên trang hoặc số entity được duyệt.
- Vấn đề có thể không xuất hiện trên dữ liệu test nhỏ nhưng bộc lộ khi production có hàng trăm hoặc hàng nghìn dòng.

Một query join có thể trả nhiều dữ liệu hơn một chút nhưng thường tiết kiệm round trip. Tuy nhiên, fetch quá nhiều collection cùng lúc cũng gây Cartesian multiplication và duplicate row, nên cần chọn chiến lược theo quan hệ thực tế.

## 7. Cách nhận diện N+1

### Bật SQL log khi phát triển

Trong Spring Boot có thể cấu hình:

~~~properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Tên logger bind parameter có thể khác giữa các phiên bản Hibernate. Log bind có thể chứa dữ liệu nhạy cảm, vì vậy không nên bật ở production nếu chưa có chính sách bảo vệ log.

Hãy xem một request cụ thể và đếm số SQL. Nếu thấy một SELECT lấy danh sách, sau đó nhiều SELECT có cùng mẫu WHERE id = ?, rất có thể đang có N+1.

### Hibernate statistics

Có thể bật thống kê Hibernate trong môi trường phát triển hoặc kiểm thử:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Hibernate Statistics cung cấp số lượng query, entity load, collection fetch, flush và các thông tin liên quan. Có thể truy cập qua SessionFactory:

~~~java
SessionFactory sessionFactory = entityManagerFactory
    .unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();
statistics.clear();

// Gọi service cần đo.

long queryCount = statistics.getPrepareStatementCount();
long entityFetchCount = statistics.getEntityFetchCount();
long collectionFetchCount = statistics.getCollectionFetchCount();
~~~

Statistics là số liệu tích lũy theo SessionFactory, không phải mặc định riêng cho một request. Khi test song song, cần cô lập hoặc reset có kiểm soát; không nên dùng phép đo global này để kết luận cho từng request production.

### Kiểm thử số query

Có thể viết integration test để xác nhận số query không tăng tuyến tính theo số entity. Ví dụ tạo sẵn dữ liệu, clear persistence context, reset statistics, gọi service rồi kiểm tra query count.

~~~java
@Test
@Transactional
void loadsOrdersWithoutNPlusOne() {
    entityManager.flush();
    entityManager.clear();

    Statistics statistics = sessionFactory.getStatistics();
    statistics.clear();

    orderService.findOrderSummaries();

    long statements = statistics.getPrepareStatementCount();

    assertThat(statements).isLessThanOrEqualTo(3);
}
~~~

Con số 3 chỉ là ngưỡng minh họa cho một query chính và một vài query phụ đã biết. Test cần phản ánh thiết kế repository thực tế và không nên đặt ngưỡng cứng tùy tiện nếu schema/test data thay đổi.

## 8. Xử lý N+1 bằng JOIN FETCH

Với quan hệ to-one hoặc collection nhỏ cần dùng ngay, JPQL JOIN FETCH có thể lấy dữ liệu liên quan trong cùng query:

~~~java
@Query("""
    select o
    from Order o
    join fetch o.customer
    where o.status = :status
    """)
List<Order> findOrdersWithCustomer(
    @Param("status") String status
);
~~~

Khi chạy query, Hibernate fetch customer cùng với order. Truy cập order.getCustomer().getName() không cần phát sinh query riêng nếu customer đã được fetch.

Với collection:

~~~java
@Query("""
    select distinct o
    from Order o
    left join fetch o.items
    where o.id = :id
    """)
Optional<Order> findOrderWithItems(@Param("id") Long id);
~~~

distinct giúp loại entity gốc trùng trong kết quả JPQL khi join collection. Nó không nhất thiết làm SQL result set chỉ còn một dòng cho mỗi order vì database vẫn trả một dòng cho mỗi tổ hợp order-item.

### Hạn chế của JOIN FETCH

- Join nhiều collection cùng lúc có thể tạo tích Descartes, làm số dòng SQL tăng mạnh.
- Fetch join collection không phù hợp trực tiếp với pagination entity gốc.
- Một số quan hệ to-many có thể tạo duplicate row và tăng lượng dữ liệu truyền.
- Fetch join quá rộng làm tải nhiều cột và object không cần thiết.
- Không nên thêm fetch join chỉ để hết log N+1 nếu nó khiến query trở nên nặng hơn.

Với quan hệ to-one, join fetch thường ít rủi ro hơn collection. Với collection lớn hoặc phân trang, cân nhắc query hai bước, batch fetching hoặc DTO projection.

## 9. Xử lý N+1 bằng EntityGraph

EntityGraph mô tả những association cần fetch cho một query mà không phải viết JPQL fetch join trực tiếp.

~~~java
@EntityGraph(attributePaths = {"customer"})
Optional<Order> findWithCustomerById(Long id);
~~~

Hoặc trên query:

~~~java
@EntityGraph(attributePaths = {"customer", "shippingAddress"})
Page<Order> findByStatus(String status, Pageable pageable);
~~~

EntityGraph chỉ định fetch plan cho query. Nó không bảo đảm mọi provider sẽ tạo đúng một SQL đơn giản trong mọi trường hợp; hãy xem SQL được sinh ra. Với collection lớn, cần kiểm tra kỹ việc kết hợp EntityGraph và pagination.

EntityGraph hữu ích khi một repository method cần fetch plan riêng mà không muốn thay đổi mapping toàn cục của entity.

## 10. Xử lý N+1 bằng batch fetching

Batch fetching không gộp tất cả quan hệ vào một JOIN. Thay vào đó, Hibernate gom nhiều entity hoặc collection chưa được load vào một câu SELECT với điều kiện IN.

Có thể cấu hình mặc định:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

Hoặc đặt trên entity/collection:

~~~java
@Entity
@BatchSize(size = 32)
public class Customer {
    // ...
}
~~~

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<OrderItem> items = new ArrayList<>();
~~~

Khi ứng dụng truy cập nhiều collection hoặc proxy trong cùng persistence context, Hibernate có thể tải theo nhóm, ví dụ:

~~~sql
SELECT ...
FROM customers
WHERE customer_id IN (?, ?, ..., ?);
~~~

Nếu có 100 customer và batch size 32, số query có thể giảm từ gần 100 xuống khoảng 4 nhóm, tùy cache, thứ tự truy cập và dữ liệu thực tế.

Batch fetching hữu ích khi:
- Không muốn join collection vào query gốc.
- Có nhiều entity cùng tham chiếu đến quan hệ LAZY.
- Cần giữ pagination query đơn giản.
- Muốn giảm N+1 nhưng vẫn tải dữ liệu theo nhu cầu.

Nó không bảo đảm chỉ còn một query và không thay thế việc chọn fetch plan hợp lý. Batch size cần được đo theo số lượng association, kích thước row và giới hạn bind parameter.

## 11. Xử lý N+1 bằng DTO projection

Nếu API chỉ cần một số trường, không nhất thiết phải load toàn bộ entity và quan hệ. DTO projection cho phép query chỉ chọn các cột cần thiết:

~~~java
public record OrderSummary(
    Long id,
    LocalDateTime orderDate,
    String status,
    String customerName,
    BigDecimal totalAmount
) {}
~~~

Repository:

~~~java
@Query("""
    select new com.example.orders.OrderSummary(
        o.id,
        o.orderDate,
        o.status,
        c.name,
        o.totalAmount
    )
    from Order o
    join o.customer c
    where o.status = :status
    """)
Page<OrderSummary> findSummaries(
    @Param("status") String status,
    Pageable pageable
);
~~~

Query chỉ lấy các cột cần dùng. DTO không có lazy association nên code serialize response không phát sinh thêm truy vấn.

Projection phù hợp cho API list và search, màn hình báo cáo, trang kết quả cần nhiều trường từ các bảng liên quan và trường hợp chỉ đọc không cần thay đổi entity.

DTO projection thường là lựa chọn tốt cho endpoint chỉ đọc có pagination. Nếu cần cập nhật entity, load entity theo use case ghi riêng.

## 12. FetchType LAZY/EAGER và Open Session in View

JPA có hai chế độ fetch phổ biến:

- LAZY: association được tải khi ứng dụng truy cập, nếu persistence context còn mở.
- EAGER: association phải được tải theo yêu cầu mapping, nhưng provider có thể dùng join hoặc secondary select.

Đặt EAGER toàn cục không phải cách chữa N+1. Một entity có nhiều quan hệ EAGER có thể khiến truy vấn không cần thiết, dữ liệu dư thừa hoặc nhiều secondary select. Nên giữ mapping mặc định hợp lý, thường ưu tiên LAZY cho quan hệ to-one và to-many rồi chọn fetch plan theo từng query.

Với quan hệ to-one, JPA mặc định EAGER cho nhiều mapping như @ManyToOne và @OneToOne nếu không chỉ định LAZY. Hãy cân nhắc khai báo rõ:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "CUSTOMER_ID")
private Customer customer;
~~~

Open Session in View (OSIV) có thể giữ persistence context mở trong suốt vòng đời HTTP request, khiến lazy loading xảy ra trong tầng serialize response. Điều này làm N+1 khó phát hiện vì truy vấn phát sinh ngoài service/repository.

Có thể tắt OSIV để buộc ứng dụng load dữ liệu trong transaction/service boundary:

~~~properties
spring.jpa.open-in-view=false
~~~

Khi tắt OSIV, cần trả DTO hoặc fetch đầy đủ association cần dùng trước khi transaction kết thúc. Không nên dựa vào serializer để tự tải quan hệ từ database.

## 13. Kết hợp pagination và kiểm soát N+1

Một API danh sách đơn hàng có customer và tổng số item có thể được thiết kế bằng DTO projection:

~~~java
public record OrderListRow(
    Long id,
    LocalDateTime createdAt,
    String status,
    String customerName,
    Long itemCount
) {}
~~~

~~~java
@Query(
    value = """
        select new com.example.orders.OrderListRow(
            o.id,
            o.createdAt,
            o.status,
            c.name,
            count(i.id)
        )
        from Order o
        join o.customer c
        left join o.items i
        where o.status = :status
        group by o.id, o.createdAt, o.status, c.name
        """,
    countQuery = """
        select count(o)
        from Order o
        where o.status = :status
        """
)
Page<OrderListRow> findOrderRows(
    @Param("status") String status,
    Pageable pageable
);
~~~

Projection trả trực tiếp dữ liệu cần cho API, không cần gọi getter LAZY sau khi nhận page. Count query cần tương ứng với đơn vị phân trang. Nếu điều kiện lọc phụ thuộc collection, count query phải tính đúng distinct entity gốc và có thể cần join/exists tương ứng.

Nếu cần hiển thị toàn bộ items của từng order, hãy đánh giá kích thước collection. Có thể dùng hai bước: page ID, sau đó fetch items cho các ID trong trang. Không nên fetch join nhiều collection trong query Page chính.

## 14. Index và execution plan cho pagination

Pagination chỉ hiệu quả khi điều kiện lọc và thứ tự sort có index phù hợp. Ví dụ query:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE status = :status
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :pageSize ROWS ONLY;
~~~

Có thể cân nhắc index kết hợp theo filter và sort:

~~~sql
CREATE INDEX ix_orders_status_created_id
ON orders(status, created_at DESC, order_id DESC);
~~~

Đây chỉ là ví dụ. Cần xem độ chọn lọc status, phân bố dữ liệu, số lượng giá trị distinct, clustering và workload ghi. Index có thể tăng tốc đọc nhưng làm insert/update/delete đắt hơn và tiêu tốn storage.

Với Oracle, xem execution plan của SQL thực tế, kiểm tra predicate, sort, access path và số dòng ước lượng/thực tế. Nếu dùng bind variable, kiểm tra nhiều giá trị bind đại diện. Không kết luận index cần tạo chỉ từ hình dạng JPQL.

Count query có thể cần index khác hoặc vẫn tốn kém do phải đếm số lượng lớn. Nếu UX không yêu cầu tổng số trang, dùng Slice hoặc keyset pagination để tránh count toàn bộ.

## 15. Cấu hình Spring Boot mẫu

Một cấu hình phát triển có thể bật SQL và statistics để quan sát:

~~~properties
spring.jpa.open-in-view=false

spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
spring.jpa.properties.hibernate.default_batch_fetch_size=32

spring.jpa.properties.hibernate.generate_statistics=true
spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true

logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Không nên bật tất cả log chi tiết ở production theo mặc định. Bind logging có thể làm lộ thông tin cá nhân, token hoặc dữ liệu nghiệp vụ. Hibernate statistics có overhead và là số liệu tích lũy; dùng trong môi trường phù hợp.

Tên property và hành vi chi tiết có thể khác giữa các thế hệ Hibernate đi kèm Spring Boot. Hãy kiểm tra dependency thực tế của dự án trước khi dùng property hoặc API chỉ có ở phiên bản mới.

## 16. Quy trình điều tra và tối ưu

Khi một endpoint chậm hoặc job import kéo dài, nên đo trước khi thay đổi.

1. **Tái hiện với dữ liệu đủ lớn.** Test với số lượng và phân bố gần production; dữ liệu vài dòng thường không bộc lộ N+1 hoặc offset sâu.
2. **Ghi nhận số SQL.** Bật SQL log hoặc statistics trong môi trường test, xác định query count và query lặp.
3. **Phân loại bottleneck.** Xác định thời gian nằm ở count query, page query, lazy loading, insert/update, flush hay commit.
4. **Chọn chiến lược phù hợp.** Page/Slice/keyset cho đọc; JDBC batching và chunking cho ghi; fetch join, EntityGraph, batch fetching hoặc projection cho quan hệ.
5. **Kiểm tra persistence context.** Xem entity có bị giữ quá lâu, có clear đúng lúc và bulk update có làm stale entity không.
6. **Kiểm tra SQL và index.** Đối chiếu execution plan, số dòng, sort, join, index và bind values.
7. **Đo lại cùng điều kiện.** So sánh query count, elapsed time, CPU, memory, I/O và kết quả nghiệp vụ.
8. **Kiểm thử concurrency và lỗi.** Kiểm tra optimistic locking, transaction rollback, retry, duplicate request và dữ liệu thay đổi khi pagination.

Một thay đổi chỉ có ý nghĩa khi cải thiện được chỉ số cần thiết mà vẫn giữ đúng kết quả và transaction semantics.

## 17. Các sai lầm thường gặp

- **Dùng Page cho mọi API.** Page có thể cần count query đắt; nếu không cần tổng số dòng, dùng Slice hoặc keyset.
- **Không có sort ổn định.** Các dòng trùng giá trị sort có thể đổi vị trí giữa các trang; thêm khóa duy nhất làm tie-breaker.
- **Dùng fetch join collection cùng pagination.** Có thể gây nhân bản dòng hoặc in-memory pagination; dùng query hai bước hoặc projection.
- **Nghĩ saveAll tự động batch.** Phải bật Hibernate batching và kiểm tra ID strategy, flush behavior, SQL thực tế.
- **Dùng IDENTITY nhưng kỳ vọng insert batching.** Hibernate thường phải insert từng entity để lấy generated key; cân nhắc sequence trên Oracle nếu phù hợp.
- **Chỉ bật batch_size mà không flush/clear.** Persistence context vẫn có thể giữ toàn bộ entity và làm tăng heap.
- **Gọi clear quá sớm.** Entity bị detach; thay đổi sau đó không còn được dirty checking.
- **Dùng bulk JPQL mà quên persistence context.** Entity đang quản lý có thể chứa giá trị cũ; flush/clear/refresh phù hợp.
- **Tưởng bulk update tự xử lý @Version và callback.** Bulk DML bỏ qua nhiều cơ chế entity lifecycle; cần xử lý version và side effect rõ ràng.
- **Đặt EAGER để tránh lazy exception.** EAGER có thể tải quá nhiều dữ liệu và vẫn tạo nhiều query.
- **Chỉ kiểm tra query count trên test data nhỏ.** N+1 chỉ lộ rõ khi số entity đủ lớn.
- **Tăng batch size vô hạn.** Batch quá lớn có thể làm tăng memory, lock duration, redo/undo và thời gian rollback.

## 18. Checklist lựa chọn kỹ thuật

| Tình huống | Hướng xử lý nên xem xét |
|---|---|
| Trang list cần tổng số dòng | Page với countQuery phù hợp |
| Cuộn danh sách, không cần tổng | Slice |
| Dữ liệu rất lớn, chỉ đi tiếp | Keyset/seek pagination |
| API list chỉ cần một số cột | DTO projection |
| Cần load quan hệ to-one | JOIN FETCH hoặc EntityGraph |
| Cần load collection cho một entity | JOIN FETCH có giới hạn |
| Cần load collection cho trang entity | Hai query: page ID rồi fetch chi tiết |
| Nhiều proxy/collection LAZY được truy cập | Hibernate batch fetching |
| Insert hàng nghìn entity | JDBC batching, sequence phù hợp, flush/clear theo chunk |
| Update theo một điều kiện chung | Bulk JPQL/native UPDATE |
| Update cần callback/domain logic/version | Load entity và dirty checking theo batch |
| Import cần commit từng phần | Chunk transaction và cơ chế resume |
| Import cần atomic toàn bộ | Staging hoặc transaction có kiểm soát theo yêu cầu nghiệp vụ |

## 19. Nguyên tắc vận hành

- Giới hạn page size ở API và dùng thứ tự sort ổn định.
- Chọn Page khi cần tổng số dòng; dùng Slice hoặc keyset nếu không cần count.
- Kiểm tra count query riêng, đặc biệt với join và distinct.
- Không phân trang trực tiếp trên collection fetch join; dùng projection hoặc hai bước.
- Bật Hibernate JDBC batching và đo batch size; saveAll không tự bảo đảm batch.
- Với Oracle, cân nhắc sequence generation nếu cần JDBC insert batching.
- Flush/clear theo chunk để giới hạn persistence context; hiểu rằng clear detach toàn bộ entity.
- Dùng bulk JPQL khi thao tác hàng loạt đơn giản, nhưng xử lý stale persistence context và @Version rõ ràng.
- Phát hiện N+1 bằng SQL log, Hibernate statistics và integration test với dữ liệu đủ lớn.
- Chọn fetch join, EntityGraph, batch fetching hoặc DTO projection theo kích thước quan hệ và mục đích endpoint.
- Tắt OSIV nếu muốn quản lý fetch plan trong service transaction; trả DTO đã được chuẩn bị đầy đủ.
- Đo query count, elapsed time, memory, CPU, I/O và transaction duration trước/sau tối ưu.

Phân trang, batch ghi và kiểm soát N+1 là ba phần của cùng một bài toán thiết kế truy cập dữ liệu. Chọn đúng kiểu phân trang, gom ghi theo batch có kiểm soát và xác định fetch plan cho từng use case sẽ giúp ứng dụng Spring Boot/JPA giảm round trip, giữ bộ nhớ ổn định và duy trì hiệu năng khi dữ liệu tăng trưởng.
