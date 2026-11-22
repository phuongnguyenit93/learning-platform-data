# Nhận biết tên phương thức quá dài và thời điểm chuyển cách truy vấn

## 1. Query derivation phù hợp đến đâu?

Spring Data JPA có thể suy ra truy vấn từ tên repository method. Với điều kiện đơn giản và ổn định, đây là cách viết ngắn, dễ hiểu và ít mã phụ trợ. Ví dụ `findByEmail`, `existsByStatus` hoặc `findTop10ByStatusOrderByCreatedAtDesc` diễn đạt rõ ý định mà không cần viết JPQL.

Khi điều kiện tăng lên, tên method phải chứa nhiều property path, toán tử, nhóm `And`/`Or`, sắp xếp và giới hạn kết quả. Method vẫn có thể hợp lệ, nhưng chi phí đọc và thay đổi tăng dần. Không có ngưỡng ký tự chính thức để kết luận tên đã quá dài; cần đánh giá xem người đọc có hiểu đúng logic ngay lần đầu hay không.

Điểm cần phân biệt: method name dài là vấn đề bảo trì và khả năng diễn đạt. Bản thân độ dài tên method không làm SQL chạy chậm. Hiệu năng phụ thuộc SQL được tạo, index, dữ liệu, execution plan, fetch strategy và database.

## 2. Khi nào tiếp tục dùng derived query?

Derived query phù hợp khi mỗi method thể hiện một điều kiện nghiệp vụ rõ ràng, số predicate ít, property path dễ nhận ra và query không cần cấu trúc đặc biệt.

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Optional<Customer> findByEmail(String email);

    List<Customer> findByStatusAndCreatedAtAfter(
        CustomerStatus status, Instant createdAt
    );

    boolean existsByEmailIgnoreCase(String email);

    long countByStatus(CustomerStatus status);

    List<Customer> findTop20ByStatusOrderByCreatedAtDesc(
        CustomerStatus status
    );
}
```

Các từ khóa thường gặp gồm `And`, `Or`, `Between`, `After`, `Before`, `GreaterThan`, `LessThan`, `Like`, `Containing`, `StartingWith`, `EndingWith`, `In`, `NotIn`, `IsNull`, `IsNotNull`, `True`, `False`, `IgnoreCase`, `Distinct`, `Top`, `First` và `OrderBy`.

Spring Data phân tích tên thuộc tính Java, không phải tên cột vật lý. Nếu `createdAt` được ánh xạ xuống cột `created_at`, method vẫn phải dùng `CreatedAt`. Với property path lồng nhau, dấu gạch dưới có thể làm ranh giới rõ hơn, ví dụ `findByCustomer_Address_City(...)` để chỉ `customer.address.city`.

## 3. Dấu hiệu method name đang trở thành gánh nặng

Cân nhắc refactor khi:

- Tên có nhiều nhóm `And`/`Or`, khó kiểm tra các điều kiện thuộc cùng một nhánh logic nào.
- Có nhiều property path lồng nhau hoặc tên thuộc tính khiến parser dễ hiểu nhầm.
- Một method kết hợp nhiều bộ lọc, trạng thái, khoảng ngày, quyền truy cập, sort và pagination.
- Điều kiện có thể bật/tắt theo tham số request, khiến method phải xử lý nhiều trường hợp tùy chọn.
- Cần `JOIN`, `GROUP BY`, `HAVING`, aggregate, subquery, function hoặc projection đặc biệt.
- Cần kiểm soát `fetch join`, `distinct`, count query hoặc SQL riêng theo database.
- Method name mô tả quá nhiều chi tiết kỹ thuật và che mất mục đích nghiệp vụ.

Ví dụ một method đã khó quét mắt:

```java
Page<PurchaseOrder>
findDistinctByCustomer_IdAndStatusInAndCreatedAtBetweenAndTotalAmountGreaterThanOrderByCreatedAtDesc(
    Long customerId,
    Collection<OrderStatus> statuses,
    Instant from,
    Instant to,
    BigDecimal minimum,
    Pageable pageable
);
```

Method trên có thể hợp lệ nếu mọi property và kiểu tham số đúng, nhưng tên phải chứa nhiều chi tiết. Nếu query còn thêm quyền xem, loại thanh toán và điều kiện địa chỉ, nên chuyển sang cách biểu đạt rõ hơn.

Không refactor chỉ vì tên dài nếu nó vẫn rõ ràng, ổn định và dễ kiểm thử. Cũng không nên tách một truy vấn đơn giản thành nhiều tầng abstraction khiến việc đọc khó hơn.

## 4. Kiểm tra logic And và Or trước khi refactor

Query derivation chia điều kiện theo các nhóm `OrParts`; trong mỗi nhóm, các phần nối bằng `And` được kết hợp với nhau. Vì thế method:

```java
findByStatusAndPriorityOrAssignedTo(
    OrderStatus status, Priority priority, Long userId
);
```

có logic tương đương:

```text
(status = ? AND priority = ?) OR assignedTo = ?
```

Nếu nghiệp vụ yêu cầu:

```text
status = ? AND (priority = ? OR assignedTo = ?)
```

thì không nên cố mã hóa ngoặc logic vào một method name. Dùng JPQL hoặc predicate builder để thể hiện nhóm điều kiện tường minh.

Khi refactor, đừng suy luận logic chỉ từ cách đọc tự nhiên của tên method. Hãy xác định biểu thức hiện tại, viết test cho từng nhánh và so sánh kết quả trước/sau.

## 5. Chuyển sang @Query cho điều kiện tĩnh

`@Query` phù hợp khi điều kiện tương đối cố định nhưng tên derived query khó đọc, hoặc khi cần thể hiện join, projection, distinct và nhóm logic rõ ràng.

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query(
        value = """
            select distinct p
            from PurchaseOrder p
            where p.customer.id = :customerId
              and p.status in :statuses
              and p.createdAt >= :from
              and p.createdAt < :to
              and p.totalAmount > :minimum
            order by p.createdAt desc
            """,
        countQuery = """
            select count(distinct p.id)
            from PurchaseOrder p
            where p.customer.id = :customerId
              and p.status in :statuses
              and p.createdAt >= :from
              and p.createdAt < :to
              and p.totalAmount > :minimum
            """
    )
    Page<PurchaseOrder> searchOrders(
        @Param("customerId") Long customerId,
        @Param("statuses") Collection<OrderStatus> statuses,
        @Param("from") Instant from,
        @Param("to") Instant to,
        @Param("minimum") BigDecimal minimum,
        Pageable pageable
    );
}
```

JPQL dùng entity name và thuộc tính Java, ví dụ `PurchaseOrder`, `customer.id`, `createdAt`; không dùng tên bảng/cột vật lý. `@Param` liên kết named parameter với tham số method. `Page` cần tổng số kết quả nên khai báo `countQuery` tường minh giúp kiểm soát trường hợp có join hoặc distinct.

Ví dụ dùng khoảng thời gian nửa mở `[from, to)` để tránh chồng lấn giữa hai khoảng liên tiếp. Quy tắc này cần thống nhất với nghiệp vụ và cách lưu timezone của ứng dụng.

Với điều kiện `IN`, định nghĩa rõ hành vi khi collection rỗng: trả rỗng, bỏ bộ lọc hay báo lỗi. Đừng phụ thuộc vào cách từng provider/database xử lý `IN ()`.

## 6. Khi nào dùng native SQL?

Dùng native SQL khi truy vấn cần tính năng riêng của database, CTE, window function, hint, cú pháp đặc thù hoặc một kế hoạch đã đo đạc mà JPQL không thể diễn đạt phù hợp.

```java
@Query(
    value = """
        select *
        from purchase_order
        where customer_id = :customerId
          and order_status = :status
        """,
    nativeQuery = true
)
List<PurchaseOrder> findOrdersNative(
    @Param("customerId") Long customerId,
    @Param("status") String status
);
```

Native SQL tham chiếu tên bảng và cột vật lý. Nó gắn với dialect, kiểu dữ liệu, cách quote identifier và cấu trúc schema. Với native `Page`, thường cần `countQuery` rõ ràng; khả năng tự thêm sort/pagination phụ thuộc phiên bản Spring Data và độ phức tạp câu SQL.

Không chuyển sang native SQL chỉ để rút ngắn method name. Cần cân nhắc chi phí bảo trì, kiểm thử và tính di động khi schema hoặc database thay đổi.

## 7. Dùng Specification cho bộ lọc tùy chọn

Khi request có nhiều filter có thể xuất hiện hoặc vắng mặt, `Specification` cho phép ghép predicate theo từng điều kiện. Repository cần mở rộng `JpaSpecificationExecutor`:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long>,
                JpaSpecificationExecutor<PurchaseOrder> {
}
```

Ví dụ xây predicate theo tham số:

```java
public static Specification<PurchaseOrder> matches(
        Long customerId, OrderStatus status, Instant from, Instant to) {
    return (root, query, cb) -> {
        List<Predicate> predicates = new ArrayList<>();

        if (customerId != null) {
            predicates.add(cb.equal(root.get("customer").get("id"), customerId));
        }
        if (status != null) {
            predicates.add(cb.equal(root.get("status"), status));
        }
        if (from != null) {
            predicates.add(cb.greaterThanOrEqualTo(root.<Instant>get("createdAt"), from));
        }
        if (to != null) {
            predicates.add(cb.lessThan(root.<Instant>get("createdAt"), to));
        }

        return cb.and(predicates.toArray(Predicate[]::new));
    };
}
```

Đây là đoạn minh họa; cần import `Specification`, `Predicate`, `List`, `ArrayList` và các kiểu domain. Có thể gọi `repository.findAll(specification, pageable)` để lấy trang.

Specification thích hợp cho filter tùy chọn, nhưng Criteria API dạng string như `root.get("createdAt")` không hoàn toàn type-safe. Tách từng predicate thành method nhỏ để dễ đọc và kiểm thử. Với join phức tạp hoặc logic động nhiều nhánh, Querydsl có thể rõ hơn.

## 8. Querydsl và custom repository

**Querydsl** cung cấp predicate type-safe thông qua các lớp Q được sinh từ Entity. Nó phù hợp khi có nhiều điều kiện động, join và nhánh logic, đồng thời muốn compiler hỗ trợ kiểm tra thuộc tính. Dự án cần cấu hình dependency và annotation processing phù hợp.

**Custom repository** phù hợp khi query cần nhiều bước xây dựng, projection đặc biệt, CTE/native SQL, điều khiển `EntityManager` hoặc mapping kết quả tùy chỉnh. Dùng repository fragment để tách phần truy vấn chuyên biệt khỏi interface CRUD.

| Đặc điểm truy vấn | Lựa chọn nên cân nhắc |
| --- | --- |
| Ít điều kiện, cố định, tên rõ | Derived query |
| Nhiều điều kiện tĩnh, cần nhóm logic rõ | `@Query` |
| Filter tùy chọn, ghép predicate | `Specification` |
| Query động phức tạp và muốn type-safe | Querydsl |
| SQL đặc thù database | Native SQL |
| Nhiều bước xử lý hoặc custom result mapping | Custom repository |

Không có một công cụ tối ưu cho mọi trường hợp. Chọn cách diễn đạt giúp người bảo trì kiểm tra được điều kiện, tham số và hành vi kết quả.

## 9. Tránh lạm dụng tham số null trong @Query

Một cách thường thấy để xử lý filter tùy chọn là viết:

```java
@Query("""
    select p from PurchaseOrder p
    where (:status is null or p.status = :status)
      and (:customerId is null or p.customer.id = :customerId)
    """)
List<PurchaseOrder> search(
    @Param("status") OrderStatus status,
    @Param("customerId") Long customerId
);
```

Cách này dễ viết cho một vài filter, nhưng nhiều điều kiện `:param is null or ...` có thể làm query khó tối ưu, gây vấn đề suy luận kiểu cho một số database/provider hoặc làm câu query phình to. Nếu số filter tăng và tùy chọn nhiều, Specification/Querydsl thường biểu đạt tốt hơn vì chỉ thêm predicate cần thiết.

Định nghĩa rõ semantics của null: null có nghĩa bỏ điều kiện, tìm bản ghi có giá trị null, hay dữ liệu đầu vào không hợp lệ? Ba trường hợp này khác nhau và không nên dùng chung một cách ngầm định.

## 10. Pagination, sorting và count query

Method derived và `@Query` đều có thể nhận `Pageable`, nhưng khi query có join collection, `distinct`, group hoặc projection, cần kiểm tra count query và số hàng thực tế.

- `Page<T>` cần tổng số phần tử và có thể phát sinh thêm count query.
- `Slice<T>` chỉ cần biết còn trang tiếp theo hay không, thường tránh count tổng.
- `List<T>` với `Pageable` lấy một phần dữ liệu nhưng không cung cấp tổng số trang.
- `Sort` động chỉ nên cho phép các thuộc tính đã được kiểm soát; không ghép trực tiếp chuỗi sort từ input người dùng vào native SQL.

Với `@Query`, khai báo `countQuery` khi Spring Data không thể suy luận chính xác hoặc query có cấu trúc phức tạp. Với fetch join collection và phân trang, cân nhắc truy vấn trang ID trước rồi lấy dữ liệu chi tiết cho nhóm ID đó.

## 11. Refactor method dài mà không đổi hành vi

Trước khi thay một derived query, ghi lại hợp đồng hiện tại:

1. Property path và các toán tử được dùng.
2. Nhóm `And`/`Or` và logic ngoặc thực tế.
3. Cách xử lý null, collection rỗng, case sensitivity và giá trị biên.
4. Sort mặc định, `Pageable`, `Distinct`, kiểu trả về và count semantics.
5. Quan hệ được join và cách tải dữ liệu.

Sau đó viết integration test cho các trường hợp khớp và không khớp, chuyển query sang cách phù hợp, rồi so sánh kết quả và SQL. Đừng giả định `@Query` nhanh hơn derived query: cả hai có thể sinh SQL tương đương. Tối ưu hiệu năng cần xem execution plan, index và số round-trip.

## 12. Những lỗi thường gặp

**Method name đọc tự nhiên nhưng nhóm OR sai.** Kiểm tra biểu thức logic do parser tạo ra; dùng JPQL/predicate builder nếu cần ngoặc rõ.

**Dùng tên cột thay cho property trong derived query hoặc JPQL.** Derived query và JPQL dùng thuộc tính Java; native SQL dùng tên vật lý.

**Collection filter rỗng làm truy vấn lỗi hoặc trả kết quả bất ngờ.** Xử lý rỗng ở service/query builder theo quy tắc nghiệp vụ.

**Page có tổng số không đúng.** Kiểm tra count query, distinct, join và group.

**Native query lỗi khi đổi database.** Kiểm tra dialect, identifier, kiểu dữ liệu, pagination và migration.

**Specification tạo join trùng hoặc kết quả trùng.** Kiểm tra cardinality của join, dùng distinct khi phù hợp và đảm bảo count query tương ứng.

**Query refactor nhưng kết quả thay đổi.** So sánh logic And/Or, null, timezone, sort, pagination và test trên database tương thích.

## 13. Checklist chọn cách truy vấn

- Dùng derived query nếu method ngắn, điều kiện rõ và ít thay đổi.
- Dùng `@Query` nếu điều kiện tĩnh nhưng tên method đã che khuất logic.
- Dùng Specification hoặc Querydsl khi filter tùy chọn và cần ghép điều kiện động.
- Dùng native SQL khi thật sự cần tính năng database cụ thể.
- Dùng custom repository khi query cần nhiều bước hoặc mapping đặc biệt.
- Giữ nguyên semantics, kiểu trả về, sort và pagination khi refactor.
- Kiểm thử bằng integration test và đo SQL thực tế trước khi kết luận về hiệu năng.

Khi tên method không còn giúp người đọc hiểu truy vấn nhanh chóng, đó là thời điểm xem xét một cách khai báo rõ ràng hơn. Lựa chọn đúng giúp repository thể hiện ý định nghiệp vụ, giữ hành vi ổn định và dễ mở rộng khi yêu cầu lọc phát triển.