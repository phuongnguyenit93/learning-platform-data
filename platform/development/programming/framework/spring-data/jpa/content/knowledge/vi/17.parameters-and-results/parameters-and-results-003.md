# Truyền tập hợp, enum, thời gian và tham số có thể null

## 1. Mục tiêu

Spring Data JPA cho phép truyền nhiều kiểu giá trị vào derived query và JPQL: danh sách ID, tập hợp enum, mốc thời gian và tham số có thể không có giá trị. Cách khai báo kiểu tham số ảnh hưởng tới SQL được tạo, cách database xử lý NULL và tính đúng đắn của điều kiện lọc.

Sau bài học, bạn có thể:
- Truyền `Collection`, `List`, mảng hoặc varargs cho điều kiện `IN` và `NOT IN`.
- Xử lý tập hợp rỗng, phần tử null và danh sách lớn một cách chủ động.
- Ánh xạ enum bằng `EnumType.STRING` hoặc `EnumType.ORDINAL` và bind tham số đúng kiểu.
- Truy vấn theo `LocalDate`, `LocalDateTime` và `OffsetDateTime` với khoảng thời gian rõ ràng.
- Phân biệt tham số null mang nghĩa bỏ qua bộ lọc, tìm bản ghi có cột null hoặc so sánh null an toàn.
- Kiểm thử các trường hợp biên bằng Spring Data JPA.

## 2. Ví dụ mô hình dữ liệu

Ví dụ dùng Java 17+, Maven, Spring Boot 3.5.0, Spring Data JPA và H2. Entity `PurchaseOrder` lưu khách hàng, trạng thái đơn, thời điểm tạo, ngày giao dự kiến và mã tham chiếu tùy chọn.

### Enum OrderStatus

`src/main/java/com/example/orders/OrderStatus.java`:

```java
package com.example.orders;

public enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}
```

### Entity PurchaseOrder

`src/main/java/com/example/orders/PurchaseOrder.java`:

```java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "delivery_date")
    private LocalDate deliveryDate;

    @Column(name = "reference_code", length = 40)
    private String referenceCode;

    @Column(name = "total_amount", nullable = false, precision = 14, scale = 2)
    private BigDecimal totalAmount;

    protected PurchaseOrder() {
        // JPA cần constructor không tham số.
    }

    public PurchaseOrder(
            Long customerId, OrderStatus status, OffsetDateTime createdAt,
            LocalDate deliveryDate, String referenceCode, BigDecimal totalAmount) {
        if (customerId == null || customerId <= 0) {
            throw new IllegalArgumentException("Customer ID must be positive");
        }
        if (status == null) {
            throw new IllegalArgumentException("Status is required");
        }
        if (createdAt == null) {
            throw new IllegalArgumentException("Created time is required");
        }
        if (totalAmount == null || totalAmount.signum() < 0) {
            throw new IllegalArgumentException("Total amount cannot be negative");
        }
        if (referenceCode != null && referenceCode.length() > 40) {
            throw new IllegalArgumentException("Reference code is too long");
        }
        this.customerId = customerId;
        this.status = status;
        this.createdAt = createdAt;
        this.deliveryDate = deliveryDate;
        this.referenceCode = referenceCode;
        this.totalAmount = totalAmount;
    }

    public Long getId() { return id; }
    public Long getCustomerId() { return customerId; }
    public OrderStatus getStatus() { return status; }
    public OffsetDateTime getCreatedAt() { return createdAt; }
    public LocalDate getDeliveryDate() { return deliveryDate; }
    public String getReferenceCode() { return referenceCode; }
    public BigDecimal getTotalAmount() { return totalAmount; }
}
```

`@Enumerated(EnumType.STRING)` lưu tên enum như `PAID` hoặc `SHIPPED`. `createdAt` là một thời điểm có offset; `deliveryDate` là ngày lịch không kèm giờ hoặc múi giờ. `referenceCode` được phép null để minh họa bộ lọc với dữ liệu tùy chọn.

## 3. Truyền tập hợp cho IN và NOT IN

Spring Data hỗ trợ derived query với `In` và `NotIn`. Tham số có thể là `Collection`, `List`, mảng hoặc varargs phù hợp với kiểu thuộc tính.

```java
List<PurchaseOrder> findByIdIn(Collection<Long> ids);

List<PurchaseOrder> findByStatusIn(Collection<OrderStatus> statuses);

List<PurchaseOrder> findByStatusNotIn(Collection<OrderStatus> statuses);
```

Ví dụ:

```java
List<PurchaseOrder> paidOrShipped = repository.findByStatusIn(
        List.of(OrderStatus.PAID, OrderStatus.SHIPPED));
```

Derived query trên tương đương điều kiện JPQL `o.status in :statuses`. Có thể khai báo truy vấn rõ ràng như sau:

```java
@Query("select o from PurchaseOrder o where o.status in :statuses")
List<PurchaseOrder> findByStatuses(@Param("statuses") Collection<OrderStatus> statuses);
```

Provider JPA mở rộng collection parameter thành các bind parameter SQL phù hợp. Không tự nối chuỗi `IN (...)` và không ghép giá trị đầu vào vào câu SQL.

### 3.1. Xử lý collection null hoặc rỗng

Không dựa vào database để xử lý `IN ()`. Cách provider chuyển danh sách rỗng thành SQL có thể khác nhau; một số database không chấp nhận danh sách rỗng. Hãy quyết định ý nghĩa ở tầng Service trước khi gọi Repository.

Ví dụ, với chức năng tìm theo danh sách ID, hợp đồng được chọn là: danh sách null hoặc rỗng trả về danh sách rỗng, không có nghĩa là bỏ điều kiện và lấy toàn bộ đơn hàng.

```java
package com.example.orders;

import java.util.Collection;
import java.util.List;
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class PurchaseOrderQueryService {
    private final PurchaseOrderRepository repository;

    public PurchaseOrderQueryService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    public List<PurchaseOrder> findByIds(Collection<Long> ids) {
        if (ids == null || ids.isEmpty()) {
            return List.of();
        }
        if (ids.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException("ID collection must not contain null");
        }
        return repository.findByIdIn(ids);
    }

    public List<PurchaseOrder> findByStatuses(Collection<OrderStatus> statuses) {
        if (statuses == null || statuses.isEmpty()) {
            return List.of();
        }
        if (statuses.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException("Status collection must not contain null");
        }
        return repository.findByStatusInOrderByIdAsc(statuses);
    }
}
```

Đây là một chính sách nghiệp vụ mẫu. Một màn hình tìm kiếm khác có thể định nghĩa collection null là không áp dụng bộ lọc; khi đó hãy dùng một phương thức tìm kiếm tùy chọn riêng và thể hiện rõ ý nghĩa này.

### 3.2. Phần tử null trong IN và NOT IN

Không đưa phần tử null vào collection dùng với `IN` hoặc `NOT IN` trừ khi đã xác định rõ semantics. SQL sử dụng logic ba giá trị: TRUE, FALSE và UNKNOWN. Với `NOT IN`, chỉ một phần tử null trong danh sách cũng có thể khiến kết quả so sánh trở thành UNKNOWN và loại bỏ các dòng mà bạn tưởng sẽ được giữ lại.

Hãy lọc hoặc từ chối null trước khi gọi Repository. Nếu cần tìm bản ghi có cột null, dùng điều kiện `IS NULL` riêng thay vì nhét null vào danh sách `IN`.

### 3.3. Danh sách lớn

Truyền hàng chục hoặc hàng trăm giá trị thường phù hợp với `IN`. Danh sách rất lớn có thể vượt giới hạn số bind parameter của database hoặc tạo SQL lớn và chậm.

Với danh sách lớn, cân nhắc chia thành batch có kích thước giới hạn, đưa ID vào bảng staging/temporary table rồi join, hoặc dùng array/table-valued parameter qua custom repository/JDBC. Không giả định mọi database có cùng giới hạn số parameter; hãy đo và kiểm thử trên engine thật.

## 4. Truyền enum làm tham số

Enum là một kiểu Java có tập giá trị hữu hạn. JPA có thể lưu enum bằng ordinal hoặc tên.

| Mapping | Giá trị lưu | Rủi ro |
| --- | --- | --- |
| `EnumType.STRING` | Tên enum, ví dụ `PAID`. | Đổi tên hằng enum cần migration dữ liệu. |
| `EnumType.ORDINAL` | Vị trí số, ví dụ `0`, `1`, `2`. | Thêm hoặc sắp xếp lại hằng enum có thể làm dữ liệu cũ mang ý nghĩa khác. |

Nếu không khai báo `@Enumerated`, mặc định JPA là ordinal. Với dữ liệu nghiệp vụ lâu dài, `EnumType.STRING` thường dễ đọc và an toàn hơn khi thêm hằng mới.

```java
@Enumerated(EnumType.STRING)
@Column(nullable = false, length = 20)
private OrderStatus status;
```

Repository nên nhận `OrderStatus`, không cần chuyển enum thành chuỗi trước khi gọi query:

```java
List<PurchaseOrder> findByStatus(OrderStatus status);
List<PurchaseOrder> findByStatusIn(Collection<OrderStatus> statuses);
```

JPQL:

```java
@Query("select o from PurchaseOrder o where o.status = :status")
List<PurchaseOrder> findAllWithStatus(@Param("status") OrderStatus status);
```

JPA provider biết kiểu của thuộc tính `status` và ánh xạ tham số enum theo mapping của Entity. Với `EnumType.STRING`, database lưu tên enum. Với native SQL, kiểu bind enum có thể phụ thuộc provider và schema; nếu buộc phải viết native query, hãy xác định representation được lưu và kiểm thử trên database mục tiêu.

Giả sử đã lưu `PAID` trong database và sau này đổi tên hằng thành `SETTLED`. Các dòng cũ vẫn chứa `PAID`; khi đọc, provider không thể tự đoán tên mới. Cần migration dữ liệu đồng bộ với thay đổi mã nguồn. Không đổi từ ORDINAL sang STRING chỉ bằng cách sửa annotation; cần chuyển dữ liệu số sang tên enum tương ứng.

## 5. Truyền tham số thời gian

JPA hỗ trợ các kiểu `java.time` phổ biến. Chọn kiểu theo ý nghĩa của dữ liệu:

| Java type | Ý nghĩa |
| --- | --- |
| `LocalDate` | Ngày lịch, không có giờ và múi giờ. |
| `LocalTime` | Giờ trong ngày, không có ngày hoặc múi giờ. |
| `LocalDateTime` | Ngày giờ địa phương, không chứa offset/múi giờ. |
| `OffsetDateTime` | Ngày giờ có UTC offset. |
| `Instant` | Một thời điểm trên timeline; được Hibernate hỗ trợ, nhưng nếu cần portability JPA nghiêm ngặt hãy xác nhận mapping với provider/version đang dùng. |

Không dùng `@Temporal` cho `java.time`. `@Temporal` dành cho `java.util.Date` và `Calendar` trong các mapping legacy.

### 5.1. Truy vấn theo ngày

Với thuộc tính `LocalDate`, có thể dùng `Between`. Trong derived query, `Between` bao gồm cả hai đầu mút.

```java
List<PurchaseOrder> findByDeliveryDateBetweenOrderByDeliveryDateAsc(
        LocalDate fromInclusive, LocalDate toInclusive);
```

Ví dụ tìm các đơn giao từ ngày 1 tới ngày 31 tháng 3:

```java
List<PurchaseOrder> marchOrders = repository.findByDeliveryDateBetweenOrderByDeliveryDateAsc(
        LocalDate.of(2026, 3, 1),
        LocalDate.of(2026, 3, 31));
```

### 5.2. Truy vấn theo khoảng timestamp

Với thời điểm có giờ, nên ưu tiên khoảng nửa mở: bao gồm thời điểm bắt đầu và loại trừ thời điểm kết thúc.

```java
List<PurchaseOrder> findByCreatedAtGreaterThanEqualAndCreatedAtLessThanOrderByCreatedAtAscIdAsc(
        OffsetDateTime fromInclusive,
        OffsetDateTime toExclusive);
```

Ví dụ lấy đơn trong tháng 3 năm 2026 theo UTC:

```java
OffsetDateTime from = OffsetDateTime.parse("2026-03-01T00:00:00Z");
OffsetDateTime to = OffsetDateTime.parse("2026-04-01T00:00:00Z");

List<PurchaseOrder> marchOrders = repository
        .findByCreatedAtGreaterThanEqualAndCreatedAtLessThanOrderByCreatedAtAscIdAsc(from, to);
```

Khoảng `[from, to)` tránh phải tạo mốc cuối ngày như `23:59:59.999999`, vốn phụ thuộc độ chính xác timestamp của database. Hai khoảng liên tiếp cũng không bị trùng hoặc bỏ sót tại ranh giới.

### 5.3. Offset và múi giờ

`OffsetDateTime` mang ngày giờ cùng offset. Tuy nhiên, nhiều database, trong đó có PostgreSQL `TIMESTAMP WITH TIME ZONE`, lưu một instant đã chuẩn hóa chứ không giữ nguyên offset ban đầu mà người dùng nhập. Nếu nghiệp vụ cần nhớ múi giờ gốc như `Asia/Ho_Chi_Minh`, hãy lưu thêm `ZoneId` dưới dạng chuỗi riêng.

`LocalDateTime` không có thông tin múi giờ. Không dùng nó để biểu diễn một thời điểm toàn cầu nếu các máy hoặc người dùng ở nhiều múi giờ; cùng một giá trị local có thể chỉ nhiều thời điểm khác nhau.

Quy ước tốt là tạo boundary theo một timezone đã thống nhất (thường UTC cho thời điểm toàn cầu), dùng cùng quy ước khi ghi và truy vấn, và kiểm thử precision của cột timestamp trên database mục tiêu.

## 6. Tham số có thể null: ba ý nghĩa khác nhau

NULL thường bị hiểu nhầm là một giá trị có thể so sánh bằng `=`. Trong SQL/JPQL, phép so sánh `column = NULL` không trả TRUE; nó trả UNKNOWN. Vì vậy, cần xác định rõ null mang ý nghĩa gì trong use case.

### 6.1. Null có nghĩa là bỏ qua bộ lọc

Ví dụ màn hình tìm kiếm cho phép lọc theo khách hàng và trạng thái. Nếu `customerId` null thì không lọc theo khách hàng; nếu `status` null thì không lọc theo trạng thái.

```java
@Query("""
       select o
       from PurchaseOrder o
       where (:customerId is null or o.customerId = :customerId)
         and (:status is null or o.status = :status)
       order by o.createdAt desc, o.id desc
       """)
List<PurchaseOrder> searchOptionalFilters(
        @Param("customerId") Long customerId,
        @Param("status") OrderStatus status);
```

Ở đây `searchOptionalFilters(10L, PAID)` lọc theo cả khách hàng 10 và trạng thái PAID; `searchOptionalFilters(null, PAID)` chỉ lọc theo trạng thái; `searchOptionalFilters(10L, null)` chỉ lọc theo khách hàng; `searchOptionalFilters(null, null)` không áp dụng hai bộ lọc này và có thể trả về tất cả đơn hàng.

Đây là semantics của bộ lọc tùy chọn. Cần bảo vệ endpoint có khả năng trả về toàn bộ dữ liệu bằng giới hạn phân trang, quyền truy cập và giới hạn phạm vi phù hợp.

### 6.2. Null có nghĩa là tìm cột đang null

Nếu cần tìm đơn hàng chưa có mã tham chiếu, viết điều kiện rõ ràng:

```java
List<PurchaseOrder> findByReferenceCodeIsNull();
```

Hoặc JPQL:

```java
@Query("select o from PurchaseOrder o where o.referenceCode is null")
List<PurchaseOrder> findWithoutReferenceCode();
```

Không viết `o.referenceCode = null`; cú pháp đúng là `IS NULL`.

Với derived query dạng equality, Spring Data có thể chuyển tham số null thành điều kiện IS NULL. Tuy nhiên, nếu nghiệp vụ yêu cầu tìm null, tên method `IsNull` tường minh giúp người đọc hiểu ý định và tránh nhầm với bộ lọc tùy chọn.

### 6.3. Null có nghĩa là so sánh null-safe

Đôi khi muốn tìm các bản ghi có giá trị bằng tham số, trong đó null chỉ khớp với cột null. Có thể biểu đạt rõ:

```java
@Query("""
       select o
       from PurchaseOrder o
       where (:referenceCode is null and o.referenceCode is null)
          or o.referenceCode = :referenceCode
       """)
List<PurchaseOrder> findByReferenceCodeNullSafe(
        @Param("referenceCode") String referenceCode);
```

Khi tham số null, query lấy các đơn có `referenceCode IS NULL`. Khi tham số không null, query lấy các đơn có mã tham chiếu bằng giá trị đó.

Điều này khác với bộ lọc tùy chọn: ở bộ lọc tùy chọn, null có nghĩa là không giới hạn theo cột; ở null-safe equality, null có nghĩa là chỉ lấy những dòng có cột null.

## 7. Derived query và JPQL: chọn đúng cách

| Nhu cầu | Derived query | JPQL |
| --- | --- | --- |
| ID nằm trong tập hợp | `findByIdIn(ids)` | `where o.id in :ids` |
| Trạng thái thuộc một tập hợp enum | `findByStatusIn(statuses)` | `where o.status in :statuses` |
| Ngày nằm trong khoảng đóng | `findByDeliveryDateBetween(from, to)` | `where o.deliveryDate between :from and :to` |
| Timestamp từ đầu mút, không gồm cuối mút | `findByCreatedAtGreaterThanEqualAndCreatedAtLessThan(from, to)` | `where o.createdAt >= :from and o.createdAt < :to` |
| Cột đang null | `findByReferenceCodeIsNull()` | `where o.referenceCode is null` |
| Bỏ qua filter khi tham số null | Không nên giả định method equality tự bỏ filter. | `(:param is null or field = :param)` |

Derived query phù hợp với điều kiện đơn giản. JPQL phù hợp khi cần kết hợp nhiều bộ lọc tùy chọn, biểu thức null hoặc join phức tạp.

## 8. Repository hoàn chỉnh

`src/main/java/com/example/orders/PurchaseOrderRepository.java`:

```java
package com.example.orders;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository extends JpaRepository<PurchaseOrder, Long> {
    List<PurchaseOrder> findByIdIn(Collection<Long> ids);

    List<PurchaseOrder> findByStatusInOrderByIdAsc(Collection<OrderStatus> statuses);

    List<PurchaseOrder> findByStatusNotIn(Collection<OrderStatus> statuses);

    List<PurchaseOrder> findByCreatedAtGreaterThanEqualAndCreatedAtLessThanOrderByCreatedAtAscIdAsc(
            OffsetDateTime fromInclusive, OffsetDateTime toExclusive);

    List<PurchaseOrder> findByDeliveryDateBetweenOrderByDeliveryDateAsc(
            LocalDate fromInclusive, LocalDate toInclusive);

    List<PurchaseOrder> findByReferenceCodeIsNull();

    @Query("""
           select o from PurchaseOrder o
           where (:customerId is null or o.customerId = :customerId)
             and (:status is null or o.status = :status)
           order by o.createdAt desc, o.id desc
           """)
    List<PurchaseOrder> searchOptionalFilters(
            @Param("customerId") Long customerId,
            @Param("status") OrderStatus status);
}
```

Repository dùng generic ID là `Long`, vì khóa chính của `PurchaseOrder` là `Long`. Kiểu của tham số filter độc lập với kiểu ID: `Collection<OrderStatus>`, `OffsetDateTime`, `LocalDate` hoặc các giá trị nullable.

## 9. Kiểm thử tích hợp với H2

Ví dụ kiểm thử dùng `@DataJpaTest` để xác nhận collection parameter, enum, khoảng thời gian và null semantics. H2 phù hợp để kiểm tra hành vi JPA cơ bản; nếu production dùng database có quy tắc timezone hoặc kiểu dữ liệu riêng, hãy bổ sung integration test trên đúng engine đó.

`pom.xml` cần có các dependency:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:ordersdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

`src/test/java/com/example/orders/PurchaseOrderRepositoryTest.java`:

```java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class PurchaseOrderRepositoryTest {
    @Autowired
    private PurchaseOrderRepository repository;

    private PurchaseOrder order(
            long customerId, OrderStatus status, String createdAt,
            LocalDate deliveryDate, String referenceCode) {
        return new PurchaseOrder(
                customerId, status, OffsetDateTime.parse(createdAt), deliveryDate,
                referenceCode, new BigDecimal("100.00"));
    }

    @Test
    void filtersByCollectionOfEnumValues() {
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-10T10:00:00Z", LocalDate.of(2026, 3, 12), "R-1"));
        repository.save(order(10L, OrderStatus.SHIPPED,
                "2026-03-11T10:00:00Z", LocalDate.of(2026, 3, 13), "R-2"));
        repository.save(order(20L, OrderStatus.CANCELLED,
                "2026-03-12T10:00:00Z", LocalDate.of(2026, 3, 14), null));
        repository.flush();

        List<PurchaseOrder> result = repository.findByStatusInOrderByIdAsc(
                List.of(OrderStatus.PAID, OrderStatus.SHIPPED));

        assertThat(result).hasSize(2);
        assertThat(result).extracting(PurchaseOrder::getStatus)
                .containsExactly(OrderStatus.PAID, OrderStatus.SHIPPED);
    }

    @Test
    void usesHalfOpenTimeRange() {
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-01T00:00:00Z", LocalDate.of(2026, 3, 1), "START"));
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-31T23:59:59Z", LocalDate.of(2026, 3, 31), "INSIDE"));
        repository.save(order(10L, OrderStatus.PAID,
                "2026-04-01T00:00:00Z", LocalDate.of(2026, 4, 1), "END"));
        repository.flush();

        List<PurchaseOrder> result = repository
                .findByCreatedAtGreaterThanEqualAndCreatedAtLessThanOrderByCreatedAtAscIdAsc(
                        OffsetDateTime.parse("2026-03-01T00:00:00Z"),
                        OffsetDateTime.parse("2026-04-01T00:00:00Z"));

        assertThat(result).extracting(PurchaseOrder::getReferenceCode)
                .containsExactly("START", "INSIDE");
    }

    @Test
    void findsRowsWithNullReferenceCode() {
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-01T00:00:00Z", LocalDate.of(2026, 3, 2), null));
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-02T00:00:00Z", LocalDate.of(2026, 3, 3), "R-2"));
        repository.flush();

        List<PurchaseOrder> result = repository.findByReferenceCodeIsNull();

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getReferenceCode()).isNull();
    }

    @Test
    void nullOptionalFiltersAreIgnored() {
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-01T00:00:00Z", LocalDate.of(2026, 3, 2), "R-1"));
        repository.save(order(20L, OrderStatus.PAID,
                "2026-03-02T00:00:00Z", LocalDate.of(2026, 3, 3), "R-2"));
        repository.save(order(10L, OrderStatus.CANCELLED,
                "2026-03-03T00:00:00Z", LocalDate.of(2026, 3, 4), "R-3"));
        repository.flush();

        List<PurchaseOrder> byStatus = repository.searchOptionalFilters(null, OrderStatus.PAID);
        List<PurchaseOrder> byCustomer = repository.searchOptionalFilters(10L, null);
        List<PurchaseOrder> withoutFilters = repository.searchOptionalFilters(null, null);

        assertThat(byStatus).hasSize(2);
        assertThat(byCustomer).hasSize(2);
        assertThat(withoutFilters).hasSize(3);
    }

    @Test
    void dateBetweenIncludesBothEndpoints() {
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-01T10:00:00Z", LocalDate.of(2026, 3, 1), "FIRST"));
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-02T10:00:00Z", LocalDate.of(2026, 3, 15), "MIDDLE"));
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-03T10:00:00Z", LocalDate.of(2026, 4, 1), "LAST"));
        repository.flush();

        List<PurchaseOrder> result = repository.findByDeliveryDateBetweenOrderByDeliveryDateAsc(
                LocalDate.of(2026, 3, 1), LocalDate.of(2026, 4, 1));

        assertThat(result).extracting(PurchaseOrder::getReferenceCode)
                .containsExactly("FIRST", "MIDDLE", "LAST");
    }
}
```

Chạy kiểm thử từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả mong đợi là Maven kết thúc với `BUILD SUCCESS` và cả năm test đều thành công. Các test kiểm tra collection enum, khoảng thời gian nửa mở, ngày với `Between` bao gồm hai đầu mút, cột null và semantics bỏ qua filter khi tham số null. Đây là kết quả kỳ vọng của ví dụ; chưa có log build thực tế.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query `IN` lỗi với danh sách rỗng | SQL sinh ra có thể chứa `IN ()` hoặc provider/database xử lý khác nhau. | Xử lý null/rỗng ở Service trước khi gọi Repository. |
| `NOT IN` không trả kết quả như dự kiến | Collection có phần tử null làm biểu thức trở thành UNKNOWN. | Loại hoặc từ chối null trong collection; xử lý cột null riêng. |
| Truy vấn enum không khớp dữ liệu | Mapping ordinal/string không giống representation trong database. | Đồng bộ `@Enumerated` với schema và dữ liệu; bind enum Java đúng kiểu trong JPQL. |
| Đổi tên enum khiến đọc dữ liệu lỗi | Database vẫn lưu tên enum cũ. | Migration dữ liệu cùng thời điểm đổi tên hằng. |
| Truy vấn thời gian bỏ sót cuối ngày | Dùng `Between` với timestamp và tự tạo mốc cuối ngày thiếu precision. | Dùng khoảng `[start, nextStart)` với `>=` và `<`. |
| Kết quả timestamp lệch giờ | Dùng LocalDateTime cho thời điểm toàn cầu hoặc ghi/truy vấn với timezone không thống nhất. | Chọn `OffsetDateTime`/Instant phù hợp, chuẩn hóa boundary và kiểm thử trên DB thật. |
| Tham số null không bỏ qua filter | Điều kiện `field = :value` không mang nghĩa optional filter khi value null. | Dùng `(:value is null or field = :value)` hoặc xây dựng query động. |
| Muốn tìm cột null nhưng query không khớp | Viết `field = null`. | Dùng `field is null` hoặc derived method `findByFieldIsNull()`. |
| Query tùy chọn chậm khi nhiều điều kiện OR | Biểu thức `(:param is null or field = :param)` có thể làm planner khó dùng index hiệu quả. | Dùng Specification/Criteria/custom repository để chỉ thêm predicate cần thiết. |
| Quá nhiều bind parameters | Danh sách IN rất lớn. | Batch, staging table hoặc tính năng array/table parameter của database. |

## 11. Nguyên tắc thiết kế

1. Khai báo generic Java đúng với kiểu cột: `Collection<Long>`, `Collection<OrderStatus>`, `LocalDate` hoặc `OffsetDateTime`.
2. Xác định rõ collection null/rỗng có nghĩa là không có kết quả hay bỏ qua filter; xử lý ở Service trước khi gọi query.
3. Không đưa phần tử null vào `IN`/`NOT IN` nếu chưa định nghĩa semantics.
4. Dùng `EnumType.STRING` cho enum nghiệp vụ khi phù hợp, đồng thời quản lý việc đổi tên hằng bằng migration.
5. Dùng `LocalDate` cho ngày lịch và kiểu có offset/instant cho thời điểm toàn cầu; không gắn `@Temporal` lên `java.time`.
6. Dùng khoảng thời gian nửa mở cho timestamp và dùng UTC hoặc một timezone đã thống nhất để tạo boundary.
7. Tách rõ ba ý nghĩa của null: bỏ qua filter, tìm cột null, và null-safe equality.
8. Với nhiều filter tùy chọn hoặc query cần tối ưu index, cân nhắc Specification/Criteria để chỉ sinh predicate thực sự được chọn.
9. Kiểm thử dữ liệu biên: collection rỗng, collection chứa null, enum mới, timestamp đúng ranh giới và tham số null.
10. Kiểm thử timezone và precision trên database thật khi chúng ảnh hưởng đến nghiệp vụ.

## 12. Checklist hoàn thành

- [ ] Truyền được `Collection` vào derived query `In` và `NotIn`.
- [ ] Xử lý collection null/rỗng và phần tử null có chủ đích.
- [ ] Hiểu vì sao `NOT IN` có phần tử null có thể cho kết quả bất ngờ.
- [ ] Ánh xạ enum bằng `EnumType.STRING` và bind tham số enum Java.
- [ ] Phân biệt `LocalDate`, `LocalDateTime` và `OffsetDateTime`.
- [ ] Dùng `Between` đúng với khoảng ngày và dùng `[start, end)` cho timestamp.
- [ ] Phân biệt tham số null bỏ qua filter với điều kiện `IS NULL`.
- [ ] Viết được JPQL với bộ lọc tùy chọn và hiểu tác động hiệu năng.
- [ ] Chạy được integration test cho collection, enum, thời gian và null.

Khi hoàn thành, bạn có thể truyền tham số có kiểu dữ liệu rõ ràng vào Spring Data JPA, xử lý đúng các trường hợp null/rỗng và xây dựng bộ lọc ngày giờ nhất quán.