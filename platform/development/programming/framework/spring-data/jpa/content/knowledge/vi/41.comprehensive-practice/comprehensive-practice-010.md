# Đánh giá giải pháp bằng tính đúng đắn, SQL, hiệu năng và khả năng bảo trì

Một giải pháp Spring Data JPA không thể được đánh giá chỉ bằng việc endpoint trả về đúng dữ liệu trong một test đơn giản hoặc repository method có ít dòng code. Cần xem xét đồng thời bốn khía cạnh: **tính đúng đắn của nghiệp vụ**, **SQL thực tế được sinh ra**, **hiệu năng trong điều kiện tải gần production** và **khả năng bảo trì của thiết kế**.

Một giải pháp tốt phải giữ đúng invariant và transaction boundary, truy vấn đúng dữ liệu với số câu SQL và lượng dữ liệu hợp lý, có hiệu năng đo được, đồng thời dễ đọc, kiểm thử và thay đổi khi nghiệp vụ phát triển. Tối ưu một khía cạnh nhưng làm sai các khía cạnh còn lại không phải là cải tiến.

## 1. Khung đánh giá bốn chiều

| Khía cạnh | Câu hỏi trọng tâm | Bằng chứng cần có |
|---|---|---|
| Tính đúng đắn | Kết quả và side effect có đúng với quy tắc nghiệp vụ trong mọi trường hợp quan trọng không? | Unit test, integration test, transaction/concurrency test, assertion trạng thái database |
| SQL | ORM thực sự phát ra câu SQL nào, điều kiện lọc và join có đúng không? | SQL log, bind parameter, query plan, số câu SQL, dữ liệu trả về |
| Hiệu năng | Thời gian, CPU, bộ nhớ, connection và database load có đáp ứng yêu cầu không? | Benchmark có dữ liệu đại diện, p95/p99 latency, throughput, query count, execution plan |
| Khả năng bảo trì | Code có thể hiểu, kiểm thử, mở rộng và sửa an toàn không? | Ranh giới trách nhiệm, độ rõ ràng của query, test dễ đọc, mức độ coupling và tài liệu quyết định |

Nên đánh giá theo thứ tự:

1. Xác định hành vi nghiệp vụ và invariant cần bảo vệ.
2. Xác nhận kết quả và trạng thái database là đúng.
3. Quan sát SQL để hiểu ORM đang thực hiện điều gì.
4. Đo hiệu năng trên dữ liệu và tải đại diện.
5. So sánh độ phức tạp, rủi ro và chi phí bảo trì của các phương án.

Không nên bắt đầu bằng việc đếm số annotation hoặc so sánh số dòng code. Một phương án ít code hơn có thể tạo SQL đắt hơn hoặc che giấu hành vi khó kiểm soát.

## 2. Đánh giá tính đúng đắn trước khi tối ưu

### Chuyển yêu cầu nghiệp vụ thành điều kiện kiểm chứng

Trước khi viết repository query, hãy ghi rõ:

- Input hợp lệ và không hợp lệ.
- Điều kiện lọc và phân quyền.
- Quan hệ dữ liệu cần tải.
- Trạng thái được phép chuyển đổi.
- Kết quả trả về, thứ tự và quy tắc phân trang.
- Transaction boundary và hành vi khi lỗi.
- Hành vi khi nhiều request thao tác cùng dữ liệu.

Ví dụ, yêu cầu "xác nhận đơn hàng" có thể bao gồm:

- Chỉ đơn hàng ở trạng thái `DRAFT` mới được xác nhận.
- Các dòng hàng phải có số lượng hợp lệ.
- Trạng thái đơn và thao tác trừ tồn kho phải nhất quán theo thiết kế giao dịch.
- Hai request xác nhận đồng thời không được tạo hai lần side effect.
- Nếu một bước bắt buộc thất bại, dữ liệu phải rollback đúng phạm vi.

Nếu không có các điều kiện này, một query chạy nhanh vẫn có thể tạo ra dữ liệu sai.

### Entity lifecycle và dirty checking

Với entity managed, thay đổi field được JPA phát hiện bằng dirty checking khi flush. Không phải mọi thay đổi đều cần gọi `save()` lần nữa:

```java
@Transactional
public void renameUser(Long id, String newName) {
    User user = userRepository.findById(id)
        .orElseThrow(() -> new UserNotFoundException(id));

    user.changeDisplayName(newName);
    // Entity đang managed; dirty checking ghi nhận thay đổi.
}
```

Đánh giá tính đúng đắn cần xem:

- Entity có thực sự managed trong transaction không?
- Có vô tình thao tác trên entity detached không?
- Có dùng đúng instance trả về từ `merge()`/repository `save()` không?
- Có flush/clear làm thay đổi trạng thái quản lý không?
- Cascade và `orphanRemoval` có đúng với vòng đời quan hệ không?

Không nên thêm `save()` vào mọi setter như một quy tắc máy móc. Nhưng với entity mới hoặc detached, cần hiểu rõ repository `save()` chọn `persist()` hay `merge()` theo cơ chế xác định entity mới.

### Transaction boundary và rollback

Đánh giá giải pháp phải xác định rõ transaction bắt đầu ở đâu, kết thúc ở đâu và thao tác nào cần nguyên tử.

```java
@Service
public class OrderService {

    private final OrderRepository orders;
    private final InventoryService inventory;

    public OrderService(
            OrderRepository orders,
            InventoryService inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void confirm(Long orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.confirm();
        inventory.reserve(order.getLines());
    }
}
```

Đây chỉ là cấu trúc minh họa. Nếu `InventoryService.reserve()` tham gia transaction bằng propagation mặc định `REQUIRED`, các thay đổi có thể thuộc cùng transaction vật lý. Nếu thao tác tồn kho thất bại và transaction rollback-only, việc bắt exception rồi tiếp tục không làm transaction có thể commit trở lại.

Cần kiểm thử:

- Rollback khi một bước bắt buộc thất bại.
- Checked exception và rollback rule (`rollbackFor`, `noRollbackFor`).
- Propagation `REQUIRED`, `REQUIRES_NEW` khi cần.
- Lỗi xuất hiện ở flush hoặc commit.
- Side effect chỉ chạy sau commit khi nghiệp vụ yêu cầu.

### Concurrency và invariant

Nếu nhiều request cùng cập nhật một entity hoặc tập dữ liệu, giải pháp phải bảo vệ invariant:

- `@Version` và optimistic locking khi chấp nhận phát hiện xung đột lúc ghi.
- `@Lock(PESSIMISTIC_WRITE)` khi cần khóa database và tuần tự hóa thao tác.
- Unique constraint/check constraint ở database cho các quy tắc có thể biểu diễn bằng constraint.
- Transaction isolation phù hợp với hiện tượng cạnh tranh cần ngăn.

Không đánh giá tính đúng đắn chỉ bằng test tuần tự. Các tình huống cạnh tranh cần integration test với nhiều transaction/connection độc lập.

## 3. Đọc SQL thực tế thay vì suy đoán từ repository method

Spring Data JPA tạo SQL thông qua JPA provider, mapping metadata, fetch strategy và dialect database. Cùng một repository method có thể tạo SQL khác nhau khi mapping hoặc provider thay đổi.

### Bật SQL log khi điều tra

Với Hibernate, có thể bật log trong môi trường phát triển hoặc test:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
    org.springframework.transaction: TRACE
```

Logger bind parameter phụ thuộc phiên bản Hibernate. Chỉ bật chi tiết bind parameter ở môi trường được kiểm soát vì giá trị có thể chứa thông tin cá nhân, token hoặc dữ liệu nhạy cảm.

Khi đọc SQL, kiểm tra:

- Số câu SELECT/INSERT/UPDATE/DELETE.
- Cột được lấy có cần thiết không.
- Điều kiện WHERE có đúng và có tận dụng index không.
- JOIN có tạo nhiều hàng trùng do quan hệ collection không.
- Có query lặp cho từng entity hay không.
- Có câu UPDATE/DELETE hàng loạt không mong muốn không.
- Có truy vấn count riêng khi phân trang không.
- Bind parameter và kiểu dữ liệu có đúng không.

### N+1 query

Ví dụ lấy danh sách đơn hàng rồi truy cập customer cho từng đơn:

```java
List<Order> orders = orderRepository.findAll();

for (Order order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

Nếu customer chưa được tải và quan hệ là lazy, provider có thể phát một query lấy danh sách order rồi thêm một query cho mỗi customer. Với N đơn hàng, tổng số query có thể tăng theo N.

Không thể kết luận N+1 chỉ từ annotation `FetchType.LAZY`; phải quan sát SQL thực tế và cách code truy cập quan hệ.

Các phương án xử lý có thể gồm:

- DTO projection khi chỉ cần một số cột.
- `JOIN FETCH` khi cần tải quan hệ trong cùng query và cardinality phù hợp.
- `@EntityGraph` để khai báo fetch plan theo use case.
- Batch fetching của provider khi phù hợp.
- Tách truy vấn theo hai bước để tránh join làm nhân bản hàng.

Chọn phương án dựa trên dữ liệu thực tế và hình dạng kết quả, không chỉ dựa trên số lượng query.

## 4. So sánh fetch join, EntityGraph và DTO projection

### Fetch join

```java
@Query("""
    select o
      from Order o
      join fetch o.customer
     where o.status = :status
    """)
List<Order> findWithCustomerByStatus(
    @Param("status") OrderStatus status
);
```

Ưu điểm:

- Truy vấn và tải quan hệ cần thiết trong một SQL.
- Hạn chế N+1 cho quan hệ được fetch.
- Query thể hiện rõ quan hệ cần tải trong use case.

Rủi ro:

- Join collection có thể nhân số hàng trả về.
- Kết hợp pagination với collection fetch join có thể khiến provider phải phân trang trong bộ nhớ hoặc phát cảnh báo/lỗi tùy cấu hình.
- Tải quá nhiều quan hệ làm tăng dữ liệu truyền qua mạng và bộ nhớ.

### @EntityGraph

```java
@EntityGraph(attributePaths = {"customer"})
List<Order> findByStatus(OrderStatus status);
```

EntityGraph tách fetch plan khỏi JPQL query, phù hợp khi muốn tái sử dụng query method nhưng cần tải một tập quan hệ cụ thể cho use case. SQL cuối cùng vẫn do provider quyết định; cần kiểm tra SQL để biết graph được triển khai bằng join hay chiến lược khác.

### DTO projection

```java
public record OrderSummary(
    Long id,
    String orderNumber,
    String customerName,
    BigDecimal total
) {}
```

```java
@Query("""
    select new com.example.api.OrderSummary(
        o.id, o.number, c.name, o.total
    )
      from Order o
      join o.customer c
     where o.status = :status
    """)
List<OrderSummary> findSummariesByStatus(
    @Param("status") OrderStatus status
);
```

DTO projection phù hợp khi endpoint chỉ cần dữ liệu đọc, không cần chỉnh sửa entity hoặc thao tác lifecycle. Nó giảm số cột và tránh đưa entity graph vào tầng API.

| Tiêu chí | Fetch join | EntityGraph | DTO projection |
|---|---|---|---|
| Mục tiêu | Tải entity và quan hệ | Khai báo fetch plan | Chỉ lấy dữ liệu cần hiển thị |
| Entity managed | Có | Có | Không cần entity managed |
| Tính linh hoạt query | JPQL rõ ràng | Có thể dùng query method hiện có | Query/projection cụ thể |
| Rủi ro | Nhân hàng, pagination collection | SQL tùy provider | Projection dễ phải sửa khi cấu trúc output đổi |
| Dùng tốt khi | Cần entity và quan hệ xác định | Cần thay đổi fetch plan theo use case | Read model/API chỉ cần một số trường |

## 5. Phân trang đúng và hiệu quả

Một giải pháp phân trang phải bảo đảm cả nội dung trang và tổng số bản ghi đúng. Spring Data thường dùng `Page<T>` khi cần total count; điều này có thể phát sinh thêm count query. Nếu không cần tổng số trang, `Slice<T>` có thể giảm chi phí count.

```java
PageRequest pageRequest = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.DESC, "createdAt")
);

Page<Order> page = orderRepository.findByStatus(
    OrderStatus.PAID,
    pageRequest
);
```

Đánh giá:

- Sort phải ổn định; nên thêm cột tie-breaker duy nhất nếu nhiều hàng có cùng giá trị sort.
- Index nên phù hợp với điều kiện lọc và thứ tự sắp xếp.
- Count query có thể đắt với join phức tạp.
- Không fetch join collection trực tiếp với phân trang lớn nếu chưa hiểu cách provider xử lý.
- Với dữ liệu lớn và duyệt tuần tự, cân nhắc keyset/scrolling thay cho offset sâu.
- Phải kiểm thử page đầu, page cuối, trang ngoài phạm vi, dữ liệu rỗng và thay đổi dữ liệu đồng thời.

Ví dụ thêm tie-breaker:

```java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
```

Sort ổn định giúp hạn chế bản ghi nhảy trang khi nhiều hàng có cùng timestamp. Nó không thay thế snapshot/isolation nếu dữ liệu thay đổi giữa các lần gọi page.

## 6. Kiểm tra query plan và index

SQL ngắn không có nghĩa là SQL nhanh. Database có thể phải quét bảng lớn, sort trên bộ nhớ hoặc thực hiện join tốn kém.

Quy trình:

1. Lấy SQL và bind parameter từ log.
2. Chạy `EXPLAIN` hoặc công cụ query plan phù hợp database.
3. Xem access path: sequential/table scan, index scan, join strategy, sort và estimated rows.
4. So sánh estimated rows với actual rows nếu database hỗ trợ.
5. Kiểm tra index có phù hợp với predicate, join key và sort order không.
6. Đo lại sau khi thay query hoặc index bằng dữ liệu đại diện.

Ví dụ trên PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_number, created_at
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

`EXPLAIN ANALYZE` thực thi query thật. Cẩn thận khi dùng với câu lệnh ghi hoặc query nặng trong production. Với câu SELECT, nó vẫn tiêu tốn tài nguyên và có thể tạo tải. Kiểm tra quyền và chính sách môi trường trước khi chạy.

Không thêm index chỉ vì thấy một cột trong WHERE. Index làm tăng chi phí ghi, dung lượng và bảo trì. Chọn index dựa trên workload đọc/ghi và query plan thực tế.

## 7. Đo hiệu năng bằng dữ liệu đại diện

Một benchmark có ý nghĩa cần phản ánh:

- Số lượng entity và phân bố dữ liệu.
- Tỷ lệ dữ liệu có quan hệ và cardinality của collection.
- Tỷ lệ cache warm/cold.
- Kích thước page và mức độ sâu của offset.
- Mức độ đồng thời của request.
- Tỷ lệ đọc/ghi.
- Database engine, index và connection pool gần production.

### Chỉ số nên theo dõi

| Chỉ số | Ý nghĩa |
|---|---|
| p50/p95/p99 latency | Độ trễ điển hình và tail latency |
| Throughput | Số request hoặc transaction hoàn tất mỗi giây |
| SQL query count | Số câu SQL cho một use case |
| Rows examined/returned | Mức độ dữ liệu database phải xử lý |
| DB CPU và I/O | Tài nguyên database tiêu thụ |
| Connection pool active/wait | Áp lực lên connection pool |
| Heap/GC | Chi phí object và entity graph trong JVM |
| Lock wait/deadlock | Mức độ cạnh tranh dữ liệu |

Không dùng thời gian một lần chạy làm kết luận. Thực hiện warm-up, nhiều lần đo, tải đồng thời phù hợp và so sánh cùng điều kiện. Báo cáo p95/p99 thay vì chỉ trung bình vì tail latency thường ảnh hưởng trải nghiệm người dùng.

### Hibernate statistics

Trong môi trường test/benchmark, có thể bật Hibernate statistics để quan sát số entity load, query execution và cache hit:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Có thể truy cập `SessionFactory.getStatistics()` trong test hoặc công cụ đo. Statistics có overhead và phạm vi đếm tùy cách cấu hình; chỉ bật trong môi trường cần đo, không mặc định để luôn bật production nếu chưa đánh giá tác động.

SQL logging cũng có overhead và tạo lượng log lớn. Với benchmark chính thức, dùng metrics hoặc datasource instrumentation phù hợp để đếm query mà không làm sai kết quả đo quá nhiều.

## 8. Đánh giá batch insert/update

Với dữ liệu lớn, gọi `save()` từng entity có thể tạo nhiều round trip hoặc giữ persistence context quá lớn. Có thể dùng JDBC batching của Hibernate và chia công việc thành lô.

Ví dụ cấu hình Hibernate (cần kiểm tra phiên bản và loại ID generator):

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

Các điểm phải kiểm tra:

- Provider có thực sự gom câu lệnh thành batch không.
- ID generation strategy có cho phép batching trong cấu hình đang dùng không.
- Persistence context có cần `flush()` và `clear()` theo lô để giới hạn bộ nhớ không.
- Transaction có quá lớn, giữ lock quá lâu hoặc khó rollback không.
- Batch size có phù hợp driver/database không.
- Thứ tự cập nhật có làm tăng nguy cơ deadlock không.

Bulk JPQL update/delete khác JDBC batching: bulk query tác động trực tiếp database và bỏ qua dirty checking/lifecycle entity thông thường. Cần clear/refresh persistence context nếu entity managed có thể stale.

## 9. Tính đúng đắn của mapping và truy vấn

Một giải pháp phải được kiểm tra cả mapping và semantics:

- `@ManyToOne`, `@OneToMany`, `@OneToOne`, `@ManyToMany` có đúng cardinality không?
- Owning side và `mappedBy` có đúng không?
- Cascade và `orphanRemoval` có phản ánh vòng đời nghiệp vụ không?
- Fetch type có tạo tải dữ liệu ngoài dự kiến không?
- `equals()`/`hashCode()` có an toàn với entity và generated ID không?
- Enum mapping có ổn định khi lưu database không?
- Nullability, unique constraint và foreign key có được bảo vệ ở database không?
- Query có trả duplicate hoặc bỏ sót dữ liệu do join không?
- Sort, page và count có cùng semantics không?

Đặc biệt, không dùng `CascadeType.ALL` hoặc `FetchType.EAGER` như giải pháp mặc định cho mọi quan hệ. Chúng có thể tạo side effect và tải dữ liệu rộng ngoài use case cần thiết.

## 10. Kiểm thử để chứng minh giải pháp đúng

### Unit test cho domain logic

Dùng unit test cho các quy tắc thuần Java: chuyển trạng thái, tính tổng, kiểm tra điều kiện và invariant. Không cần khởi tạo Spring context nếu logic không phụ thuộc Spring/JPA.

### Repository integration test

Dùng `@DataJpaTest` với database phù hợp để xác minh:

- JPQL/native query thực thi đúng.
- Mapping và cascade hoạt động như mong muốn.
- Projection và pagination trả dữ liệu chính xác.
- Unique/foreign key constraint được áp dụng.
- Flush/clear và dirty checking cho kết quả đúng.

Nếu cần kiểm tra lỗi tại commit, nhớ test transaction mặc định có thể rollback thay vì commit. Dùng flush để phát hiện lỗi SQL tại thời điểm thực thi; dùng test không transactional hoặc `TestTransaction` để kiểm tra commit thật.

### Service integration test

Dùng Spring context để xác minh:

- Transaction boundary và rollback.
- Nhiều repository cùng tham gia transaction.
- Exception translation.
- Event listener theo transaction phase.
- Retry và idempotency ở ranh giới phù hợp.

### Concurrency test

Dùng nhiều transaction và connection độc lập để kiểm tra:

- Optimistic locking.
- Pessimistic lock và timeout.
- Deadlock hoặc thứ tự khóa.
- Lost update.
- Invariant khi hai request đồng thời.

Test concurrency cần barrier/latch để tạo thứ tự có kiểm soát, tránh chỉ dựa vào `Thread.sleep()` và hy vọng race condition xuất hiện.

## 11. Đánh giá khả năng bảo trì

Một giải pháp có thể nhanh nhưng rất khó sửa. Các dấu hiệu cần xem:

### Ranh giới trách nhiệm rõ ràng

- Repository chịu trách nhiệm truy cập dữ liệu.
- Service điều phối use case và transaction.
- Aggregate/entity bảo vệ invariant miền nghiệp vụ.
- DTO/projection phục vụ read model hoặc API.
- Mapper chuyển đổi dữ liệu ở ranh giới phù hợp.

Không đưa logic nghiệp vụ phức tạp vào query string hoặc controller. Đồng thời, tránh tạo quá nhiều lớp chỉ chuyển tiếp lời gọi mà không tạo giá trị.

### Query có thể đọc và kiểm thử

Chọn derived query khi tên method vẫn dễ hiểu. Chọn JPQL hoặc native SQL khi query phức tạp, cần kiểm soát join/aggregation hoặc tận dụng tính năng database. Đặt tên repository method theo ý nghĩa nghiệp vụ và viết test cho semantics.

Một native query nhanh nhưng gắn chặt vào dialect có thể tăng chi phí chuyển database. Đổi lại, native SQL có thể hợp lý khi query plan và tính năng database là yêu cầu quan trọng. Hãy ghi rõ lý do lựa chọn và kiểm thử trên database production-like.

### Fetch plan rõ ràng theo use case

Không đặt mọi quan hệ thành EAGER để tránh lazy loading exception. Xác định dữ liệu cần tải cho từng use case bằng EntityGraph, fetch join hoặc projection. Fetch plan tường minh giúp người bảo trì biết query cần dữ liệu nào và giảm nguy cơ N+1 bất ngờ.

### Không che giấu chi phí bằng abstraction

Generic repository hoặc base service có thể giảm lặp, nhưng nếu khiến query, transaction và lifecycle khó hiểu hơn thì abstraction đang gây hại. Ưu tiên code đơn giản, có tên rõ và có test chứng minh.

### Ghi lại trade-off quan trọng

Với quyết định đáng kể như native query, pessimistic lock, batch size hoặc outbox, ghi ngắn gọn:

- Vấn đề thực tế.
- Phương án đã chọn.
- Phương án khác đã cân nhắc.
- Số đo hoặc bằng chứng.
- Giới hạn và điều kiện cần xem lại.

## 12. Ví dụ đánh giá hai phương án cho màn hình danh sách đơn hàng

Yêu cầu: trả về 20 đơn hàng đã thanh toán, sắp xếp mới nhất, gồm mã đơn, thời gian tạo, tên khách hàng và tổng tiền.

### Phương án A: tải entity rồi truy cập quan hệ

```java
List<Order> orders = orderRepository.findByStatus(
    OrderStatus.PAID
);

List<OrderSummary> result = orders.stream()
    .map(order -> new OrderSummary(
        order.getId(),
        order.getNumber(),
        order.getCustomer().getName(),
        order.getTotal()
    ))
    .toList();
```

Rủi ro:

- Nếu tải tất cả đơn hàng, bộ nhớ và số hàng xử lý tăng theo dữ liệu.
- Truy cập customer có thể tạo N+1.
- Entity graph có thể tải nhiều field/quan hệ không cần cho màn hình.
- Không có pagination nếu không bổ sung.

### Phương án B: projection có phân trang

```java
public record OrderSummary(
    Long id,
    String number,
    String customerName,
    BigDecimal total
) {}
```

```java
@Query("""
    select new com.example.api.OrderSummary(
        o.id, o.number, c.name, o.total
    )
      from Order o
      join o.customer c
     where o.status = :status
    """)
Page<OrderSummary> findOrderSummaries(
    @Param("status") OrderStatus status,
    Pageable pageable
);
```

Phương án B thường phù hợp hơn với read-only list vì lấy đúng cột cần thiết và có phân trang. Tuy nhiên, vẫn phải kiểm tra:

- SQL có join đúng và count query có chi phí hợp lý không.
- Index có hỗ trợ filter/sort không.
- Sort có ổn định không.
- Kích thước page có phù hợp không.
- p95 latency và DB load có thực sự tốt hơn không.

Nếu tổng số bản ghi không cần thiết, có thể dùng `Slice<OrderSummary>` hoặc keyset pagination theo yêu cầu. Không kết luận B tốt hơn chỉ vì dùng projection; cần đo trên dữ liệu đại diện và xác nhận semantics.

## 13. Bảng chấm điểm giải pháp

Có thể dùng bảng dưới đây trong review để bảo đảm các khía cạnh đều được xem xét. Điểm là công cụ thảo luận nội bộ, không thay thế bằng chứng kỹ thuật.

| Tiêu chí | Trọng số gợi ý | Điểm 1 | Điểm 3 | Điểm 5 |
|---|---:|---|---|---|
| Tính đúng đắn | 35% | Sai invariant hoặc thiếu rollback/concurrency | Đúng luồng chính, còn thiếu edge case | Có test cho lỗi, biên, transaction và concurrency cần thiết |
| SQL | 25% | SQL sai hoặc có N+1/scan nghiêm trọng | SQL đúng nhưng còn query/column thừa | SQL được quan sát, query plan hợp lý và dữ liệu trả về chính xác |
| Hiệu năng | 25% | Không đo hoặc không đáp ứng yêu cầu | Đạt tải cơ bản, tail latency chưa rõ | Có benchmark đại diện và đạt mục tiêu latency/throughput/tài nguyên |
| Bảo trì | 15% | Coupling cao, khó hiểu và khó test | Cấu trúc chấp nhận được | Trách nhiệm rõ, query/fetch plan dễ hiểu, trade-off được ghi nhận |

Cách tính điểm quy đổi:

`Tổng điểm = Σ (điểm tiêu chí / 5 × trọng số)`

Với trọng số ví dụ trên, tổng trọng số bằng 100%. Một lỗi nghiêm trọng về tính đúng đắn hoặc bảo mật phải là điều kiện chặn độc lập; không để điểm hiệu năng cao bù cho dữ liệu sai.

## 14. Checklist review trước khi chấp nhận giải pháp

**Tính đúng đắn**

- [ ] Kết quả khớp yêu cầu và invariant.
- [ ] Transaction boundary và rollback được xác minh.
- [ ] Quan hệ, cascade, orphan removal và lifecycle đúng.
- [ ] Phân trang, sort, null và dữ liệu biên đúng.
- [ ] Concurrency/locking được kiểm thử khi cần.

**SQL**

- [ ] Đã xem SQL thực tế và bind parameter phù hợp.
- [ ] Không có N+1 không chủ đích.
- [ ] WHERE/JOIN/ORDER BY đúng.
- [ ] Projection/fetch plan chỉ lấy dữ liệu cần.
- [ ] Query plan và index được đánh giá.

**Hiệu năng**

- [ ] Dữ liệu benchmark đại diện.
- [ ] Có p95/p99, throughput và query count.
- [ ] Đã xem DB CPU/I/O, connection pool và heap.
- [ ] Batch/page size được đo thay vì đoán.
- [ ] Không có lock wait/deadlock bất thường.

**Bảo trì**

- [ ] Repository, service, domain và API có trách nhiệm rõ.
- [ ] Query dễ hiểu và có test.
- [ ] Native SQL/lock/batch có lý do rõ ràng.
- [ ] Trade-off và giới hạn được ghi nhận.
- [ ] Không thêm abstraction hoặc annotation không cần thiết.

## Kết luận

Đánh giá giải pháp Spring Data JPA cần bắt đầu từ tính đúng đắn, sau đó xác minh SQL, đo hiệu năng và xem xét chi phí bảo trì. SQL do ORM sinh ra mới là hành vi thực tế; annotation hoặc tên repository method không đủ để chứng minh giải pháp hiệu quả.

Một giải pháp chỉ nên được chấp nhận khi kết quả và transaction đúng, query plan phù hợp, hiệu năng đạt mục tiêu trên dữ liệu đại diện và code vẫn đủ rõ để đội ngũ tiếp tục thay đổi. Khi có trade-off, hãy ghi rõ bằng chứng và giới hạn thay vì tối ưu theo cảm tính.
