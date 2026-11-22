# Định nghĩa SQL bằng @NamedNativeQuery

`@NamedNativeQuery` cho phép khai báo một câu SQL native có tên trong metadata JPA để tái sử dụng ở nhiều nơi trong ứng dụng. Khác với JPQL, native SQL làm việc trực tiếp với tên bảng, tên cột, hàm và cú pháp của hệ quản trị cơ sở dữ liệu. JPA có thể ánh xạ kết quả native query thành entity hoặc dùng `@SqlResultSetMapping` để tạo DTO và các dạng kết quả phức tạp.

Cách này phù hợp khi câu SQL cần dùng tính năng riêng của database, truy vấn nhiều bảng theo cách khó diễn đạt bằng JPQL, hoặc cần tập trung định nghĩa một câu SQL dùng lại. Đổi lại, query gắn chặt hơn với schema và dialect, nên phải kiểm thử trên database thực tế của ứng dụng.

## 1. Named native query là gì?

Named native query là một câu SQL được đăng ký trước với một tên duy nhất trong persistence unit. Sau khi đăng ký, ứng dụng gọi query bằng tên thay vì viết lại chuỗi SQL ở từng service.

Ví dụ:

```java
@Entity
@Table(name = "purchase_orders")
@NamedNativeQuery(
    name = "PurchaseOrder.findRecent",
    query = """
        SELECT id, order_number, customer_id, status,
               created_at, total_amount
        FROM purchase_orders
        ORDER BY created_at DESC
        """,
    resultClass = PurchaseOrder.class
)
public class PurchaseOrder {
    // Entity mapping
}
```

Có hai phần cần phân biệt:

- `name` là tên logic của named query trong JPA. Tên này được dùng khi gọi `EntityManager.createNamedQuery(...)`.
- `query` là câu SQL thực tế mà database thực thi. Nó dùng tên bảng và cột vật lý.

`@NamedNativeQuery` thuộc Jakarta Persistence, thường nằm trong package `jakarta.persistence` ở Spring Boot 3.x. Có thể khai báo một query trên entity bằng `@NamedNativeQuery`, hoặc nhiều query bằng container `@NamedNativeQueries`.

Tên named query phải duy nhất trong persistence unit. Một quy ước dễ quản lý là dùng `TênEntity.tênMụcĐích`, ví dụ `PurchaseOrder.findRecent` hoặc `PurchaseOrder.findByStatus`. Đây là quy ước đặt tên của ứng dụng, không phải tên bảng hay tên Spring bean.

## 2. @NamedNativeQuery khác @NamedQuery thế nào?

Hai annotation đều khai báo query có tên, nhưng ngôn ngữ truy vấn khác nhau:

| Tiêu chí | @NamedQuery | @NamedNativeQuery |
|---|---|---|
| Ngôn ngữ | JPQL | SQL native |
| Định danh trong câu query | Entity name và property Java | Table name và column name |
| Phụ thuộc database | Ít hơn, theo JPA/provider | Nhiều hơn, theo dialect và schema |
| Truy cập tính năng riêng của DB | Hạn chế theo JPQL | Có thể dùng function, CTE, window function, cú pháp riêng |
| Mapping kết quả | Entity hoặc kết quả JPQL | Entity, scalar hoặc mapping kết quả native |
| Khả năng chuyển database | Thường dễ hơn | Có thể cần viết lại SQL |

Ví dụ JPQL:

```java
@NamedQuery(
    name = "PurchaseOrder.findByStatus",
    query = """
        SELECT p
        FROM PurchaseOrder p
        WHERE p.status = :status
        ORDER BY p.createdAt DESC
        """
)
```

JPQL tham chiếu entity `PurchaseOrder` và thuộc tính `status`, `createdAt`.

Cùng ý tưởng bằng native SQL:

```java
@NamedNativeQuery(
    name = "PurchaseOrder.findByStatusNative",
    query = """
        SELECT id, order_number, customer_id, status,
               created_at, total_amount
        FROM purchase_orders
        WHERE status = ?
        ORDER BY created_at DESC
        """,
    resultClass = PurchaseOrder.class
)
```

Native SQL tham chiếu `purchase_orders`, `order_number`, `customer_id` và `created_at`. Nếu schema đổi tên bảng hoặc cột, native query cần được cập nhật tương ứng.

## 3. Khai báo @NamedNativeQuery trả về entity

Khi muốn kết quả là entity, dùng thuộc tính `resultClass`:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_orders")
@NamedNativeQuery(
    name = "PurchaseOrder.findByStatusNative",
    query = """
        SELECT id, order_number, customer_id, status,
               created_at, total_amount
        FROM purchase_orders
        WHERE status = ?
        ORDER BY created_at DESC, id DESC
        """,
    resultClass = PurchaseOrder.class
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Column(nullable = false)
    private String status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "total_amount", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal totalAmount;

    protected PurchaseOrder() {
    }
}
```

Ví dụ là mapping rút gọn để tập trung vào named native query. Trong ứng dụng thật, nếu `customer_id` được ánh xạ thành association `@ManyToOne`, hãy dùng `@JoinColumn(name = "customer_id")` và chọn cột phù hợp trong SQL.

Khi dùng `resultClass = PurchaseOrder.class`, provider ánh xạ mỗi hàng kết quả thành entity theo mapping của PurchaseOrder. Câu SQL phải trả về các cột cần thiết cho entity, với tên cột/alias phù hợp với mapping. Với entity có nhiều thuộc tính, embedded value, quan hệ hoặc inheritance, phải bảo đảm kết quả chứa đủ dữ liệu mà mapping yêu cầu. Trả về một vài cột rồi yêu cầu provider tạo entity hoàn chỉnh có thể dẫn đến kết quả không xác định hoặc lỗi mapping.

Không dùng entity làm DTO chỉ để tránh khai báo result mapping. Entity được quản lý theo identity và persistence context; nếu chỉ cần vài cột để hiển thị báo cáo, hãy dùng scalar/DTO mapping.

## 4. Gọi named native query bằng EntityManager

JPA cung cấp `createNamedQuery` để gọi query đã đăng ký:

```java
@Repository
public class PurchaseOrderLookup {

    @PersistenceContext
    private EntityManager entityManager;

    public List<PurchaseOrder> findByStatus(String status) {
        return entityManager
            .createNamedQuery(
                "PurchaseOrder.findByStatusNative",
                PurchaseOrder.class
            )
            .setParameter(1, status)
            .getResultList();
    }
}
```

Với native SQL, cách bind positional parameter là lựa chọn portable theo JPA. Trong chuỗi SQL khai báo bằng `@NamedNativeQuery`, dùng dấu hỏi `?`; khi gọi `setParameter`, vị trí bắt đầu từ 1. Ví dụ `WHERE status = ?` tương ứng với `.setParameter(1, status)`.

Một số provider như Hibernate hỗ trợ thêm cách bind named parameter cho native SQL, nhưng đó có thể là mở rộng riêng của provider. Nếu cần khả năng tương thích JPA, dùng positional parameter cho native query.

Không nối giá trị đầu vào trực tiếp vào SQL:

```java
// Không an toàn: dữ liệu đầu vào bị ghép vào câu SQL.
String sql = "SELECT * FROM purchase_orders WHERE status = '"
        + status + "'";
```

Hãy bind parameter:

```java
query.setParameter(1, status);
```

Bind parameter bảo vệ giá trị khỏi bị diễn giải thành cú pháp SQL và giúp database/provider quản lý kiểu dữ liệu. Parameter không thể thay thế tên bảng, tên cột hoặc từ khóa SQL. Nếu cần chọn cột sort động, hãy dùng danh sách identifier cho phép đã kiểm soát ở code; không lấy tên cột tùy ý từ request rồi nối vào query.

## 5. Ánh xạ kết quả sang DTO bằng @SqlResultSetMapping

Không phải query nào cũng nên trả về entity. Ví dụ màn hình báo cáo chỉ cần mã đơn và tổng tiền. Có thể dùng `@SqlResultSetMapping` kết hợp `@ConstructorResult` để ánh xạ từng hàng SQL vào constructor DTO.

DTO:

```java
public class OrderSummary {

    private final String orderNumber;
    private final BigDecimal totalAmount;

    public OrderSummary(
            String orderNumber,
            BigDecimal totalAmount
    ) {
        this.orderNumber = orderNumber;
        this.totalAmount = totalAmount;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }
}
```

Khai báo mapping trên entity:

```java
@Entity
@Table(name = "purchase_orders")
@SqlResultSetMapping(
    name = "OrderSummaryMapping",
    classes = @ConstructorResult(
        targetClass = OrderSummary.class,
        columns = {
            @ColumnResult(name = "order_number", type = String.class),
            @ColumnResult(name = "total_amount", type = BigDecimal.class)
        }
    )
)
@NamedNativeQuery(
    name = "PurchaseOrder.findSummariesByStatus",
    query = """
        SELECT order_number, total_amount
        FROM purchase_orders
        WHERE status = ?
        ORDER BY created_at DESC, id DESC
        """,
    resultSetMapping = "OrderSummaryMapping"
)
public class PurchaseOrder {
    // Entity mapping
}
```

Gọi query:

```java
@SuppressWarnings("unchecked")
public List<OrderSummary> findSummariesByStatus(String status) {
    return entityManager
        .createNamedQuery("PurchaseOrder.findSummariesByStatus")
        .setParameter(1, status)
        .getResultList();
}
```

Các quy tắc cần giữ:

- `resultSetMapping` phải khớp chính xác tên `@SqlResultSetMapping`.
- `@ConstructorResult.targetClass` là DTO cần khởi tạo.
- Các `@ColumnResult` được truyền vào constructor theo đúng thứ tự khai báo.
- Tên trong `@ColumnResult(name = ...)` phải khớp tên cột hoặc alias mà SQL trả về.
- Kiểu dữ liệu phải tương thích với constructor DTO và kiểu JDBC thực tế.

Nên đặt alias tường minh cho các biểu thức hoặc cột trùng tên:

```sql
SELECT
    p.order_number AS order_number,
    SUM(i.quantity * i.unit_price) AS total_amount
FROM purchase_orders p
JOIN order_items i ON i.order_id = p.id
GROUP BY p.order_number
```

Khi dùng aggregate hoặc expression, alias ổn định giúp `@ColumnResult` nhận diện cột rõ ràng. Tên alias và quy tắc chữ hoa/chữ thường có thể chịu ảnh hưởng của database; kiểm thử trên hệ quản trị thực tế.

## 6. Các dạng result mapping khác

JPA cung cấp một số cách ánh xạ kết quả native:

| Mapping | Mục đích |
|---|---|
| `resultClass` | Ánh xạ kết quả vào một entity hoặc kiểu kết quả phù hợp |
| `resultSetMapping` | Tham chiếu mapping khai báo bằng @SqlResultSetMapping |
| `@EntityResult` | Ánh xạ một entity từ các cột kết quả |
| `@FieldResult` | Chỉ rõ cột SQL tương ứng với field/property của entity |
| `@ColumnResult` | Lấy một cột scalar từ result set |
| `@ConstructorResult` | Tạo DTO qua constructor từ các cột đã ánh xạ |

Ví dụ một result set có thể trả về nhiều loại thông tin:

```java
@SqlResultSetMapping(
    name = "OrderAndCustomerMapping",
    entities = {
        @EntityResult(entityClass = PurchaseOrder.class),
        @EntityResult(entityClass = Customer.class)
    }
)
```

Khi dùng `@EntityResult` cho nhiều entity trong cùng result set, cần bảo đảm SQL trả về các cột cần thiết cho từng entity và tên cột không mơ hồ. Nếu hai entity có cột `id`, hãy alias riêng và khai báo `@FieldResult` tương ứng để tránh provider không phân biệt được cột.

Nếu kết quả chỉ là các scalar đơn giản, có thể dùng `@ColumnResult`. Nếu kết quả là DTO, `@ConstructorResult` thường rõ ràng hơn việc trả về `Object[]` rồi tự ép kiểu ở service.

## 7. Named native query cho UPDATE và DELETE

`@NamedNativeQuery` cũng có thể định nghĩa câu SQL thay đổi dữ liệu. Khi gọi, dùng `executeUpdate()`:

```java
@NamedNativeQuery(
    name = "PurchaseOrder.expireOldDrafts",
    query = """
        UPDATE purchase_orders
        SET status = 'EXPIRED'
        WHERE status = 'DRAFT'
          AND created_at < ?
        """
)
```

Thực thi:

```java
@Transactional
public int expireOldDrafts(Instant cutoff) {
    return entityManager
        .createNamedQuery("PurchaseOrder.expireOldDrafts")
        .setParameter(1, Timestamp.from(cutoff))
        .executeUpdate();
}
```

Ví dụ giả định cột `created_at` được lưu dưới dạng timestamp tương thích với JDBC `Timestamp`; cách bind thời gian nên được xác nhận theo database, JDBC driver và kiểu cột thực tế. Với native SQL, không mặc định mọi kiểu Java được chuyển đổi giống JPQL.

Native UPDATE/DELETE tác động trực tiếp lên database, không gọi setter trên từng entity và không chạy lifecycle callback như thao tác sửa/xóa từng entity qua EntityManager. Persistence context có thể vẫn chứa entity cũ. Nếu cần tiếp tục dùng các entity liên quan, hãy flush trước query khi cần đồng bộ thay đổi pending, sau đó clear hoặc refresh theo phạm vi thích hợp.

Đây cũng là lý do phải cẩn thận khi dùng bulk SQL trong một transaction đang giữ nhiều entity managed. Một entity trong bộ nhớ có thể không còn phản ánh dữ liệu trong database sau câu UPDATE native.

## 8. Pagination và sorting với native query

Named native query thường có thứ tự cố định trong SQL. Có thể giới hạn kết quả trực tiếp bằng Query API:

```java
List<PurchaseOrder> page = entityManager
    .createNamedQuery(
        "PurchaseOrder.findByStatusNative",
        PurchaseOrder.class
    )
    .setParameter(1, "PAID")
    .setFirstResult(0)
    .setMaxResults(50)
    .getResultList();
```

`setFirstResult` dùng offset bắt đầu từ 0; `setMaxResults` đặt số hàng tối đa. Cách provider dịch giới hạn này sang SQL phụ thuộc dialect.

Nếu cần Page có tổng số bản ghi, phải có count query riêng hoặc cách tính tổng phù hợp. `@NamedNativeQuery` không tự suy ra count query từ SQL gốc. Với Spring Data repository, khi khai báo native query trả Page, cần cung cấp `countQuery` rõ ràng nếu query phức tạp hoặc Spring Data không thể suy luận chính xác.

Sort động cũng cần thận trọng. Giá trị sort là identifier SQL, không phải bind parameter thông thường. Hãy giới hạn lựa chọn sort bằng whitelist và xây dựng câu SQL đã kiểm soát, hoặc khai báo các named query riêng cho những thứ tự quan trọng. Không nối trực tiếp chuỗi sort từ request vào SQL.

## 9. Gọi named query qua Spring Data repository

Spring Data JPA có thể tìm named query theo quy ước tên:

```text
TênEntity.tênMethodRepository
```

Ví dụ khai báo query:

```java
@NamedNativeQuery(
    name = "PurchaseOrder.findByStatusNative",
    query = """
        SELECT id, order_number, customer_id, status,
               created_at, total_amount
        FROM purchase_orders
        WHERE status = ?
        ORDER BY created_at DESC, id DESC
        """,
    resultClass = PurchaseOrder.class
)
```

Repository có method tương ứng:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatusNative(String status);
}
```

Spring Data có thể tra cứu named query theo tên entity và tên method. Cần bảo đảm tên query khớp chính xác quy ước và kiểm thử trên phiên bản Spring Data JPA đang dùng. Nếu method có `@Query` tường minh, khai báo đó thường được ưu tiên thay cho việc tra cứu named query theo convention.

Với DTO mapping qua `@SqlResultSetMapping`, gọi trực tiếp qua EntityManager là cách thể hiện rõ mapping JPA và dễ kiểm soát kiểu kết quả. Nếu muốn Spring Data repository trả DTO từ named native query, hãy xác minh cách Spring Data phiên bản dự án xử lý result mapping và kiểu trả về; không giả định mọi mapping phức tạp tự suy ra được từ chữ ký method.

## 10. Đặt named query trong annotation hay orm.xml?

Có hai cách phổ biến:

- Khai báo trực tiếp bằng `@NamedNativeQuery` trên entity class.
- Khai báo metadata trong `orm.xml`.

Dùng annotation khi query gắn chặt với entity và muốn giữ mapping/query gần nhau. Dùng orm.xml khi muốn tách metadata khỏi source Java, quản lý mapping tập trung hoặc không muốn sửa entity class.

Nếu khai báo nhiều named native query bằng annotation, dùng container:

```java
@NamedNativeQueries({
    @NamedNativeQuery(
        name = "PurchaseOrder.findRecent",
        query = "SELECT id, order_number FROM purchase_orders",
        resultSetMapping = "OrderSummaryMapping"
    ),
    @NamedNativeQuery(
        name = "PurchaseOrder.findPaid",
        query = """
            SELECT id, order_number, customer_id, status,
                   created_at, total_amount
            FROM purchase_orders
            WHERE status = 'PAID'
            """,
        resultClass = PurchaseOrder.class
    )
})
```

Trong ví dụ thực tế, query đầu tiên phải tham chiếu result mapping có sẵn và SQL phải trả về đủ các cột mà mapping đó yêu cầu. Không để hai named query trùng tên trong cùng persistence unit; lỗi tên trùng có thể làm ứng dụng không khởi tạo được hoặc provider báo lỗi mapping.

## 11. Query hints và timeout

`@NamedNativeQuery` hỗ trợ khai báo query hints qua thuộc tính `hints`. Ví dụ có thể đặt timeout chuẩn JPA:

```java
@NamedNativeQuery(
    name = "PurchaseOrder.findRecent",
    query = """
        SELECT id, order_number, customer_id, status,
               created_at, total_amount
        FROM purchase_orders
        ORDER BY created_at DESC
        """,
    resultClass = PurchaseOrder.class,
    hints = {
        @QueryHint(
            name = "jakarta.persistence.query.timeout",
            value = "5000"
        )
    }
)
```

Hint timeout chuẩn được tính bằng mili giây. Provider/database có thể không hỗ trợ mọi hint hoặc có thể diễn giải một số hint theo cách riêng. Timeout query không thay thế timeout transaction, connection timeout hoặc giới hạn thời gian của request. Hãy xác minh hành vi trên provider và driver đang triển khai.

Không thêm hint tối ưu hóa tùy tiện chỉ vì query chạy chậm. Trước hết hãy xem execution plan, index, số hàng trả về và lượng dữ liệu cần ánh xạ.

## 12. Native query và tính portable

Native SQL phụ thuộc schema và database:

- Hàm ngày giờ, JSON, array, toán tử và cú pháp phân trang khác nhau giữa các hệ quản trị.
- Tên identifier và cách quote có thể khác nhau.
- Kiểu dữ liệu như UUID, JSONB, timestamp with time zone hoặc boolean có thể có cách bind riêng.
- CTE, window function, lateral join và các tính năng đặc thù không được mọi database hỗ trợ giống nhau.
- JDBC driver có thể ảnh hưởng cách bind kiểu dữ liệu và cách đọc kết quả.

Dùng native query khi lợi ích rõ ràng, chẳng hạn cần window function hoặc tối ưu truy vấn báo cáo đã đo đạc. Nếu JPQL diễn đạt được yêu cầu và có hiệu năng phù hợp, JPQL thường dễ bảo trì và chuyển database hơn.

Native query không làm truy vấn tự động nhanh hơn. Database vẫn phải thực hiện join, filter, sort, aggregate và đọc dữ liệu. Câu SQL viết tay có thể còn chậm hơn query do provider sinh ra nếu thiếu index hoặc kế hoạch truy vấn không tốt.

## 13. Bảo mật và kiểm soát đầu vào

Luôn bind giá trị thay vì nối chuỗi:

```java
Query query = entityManager.createNamedQuery(
    "PurchaseOrder.findByStatusNative"
);
query.setParameter(1, status);
```

Không làm như sau:

```java
String sql = "SELECT * FROM purchase_orders WHERE status = '"
        + userInput + "'";
```

Ngoài SQL injection, cần kiểm soát quyền truy cập ở tầng nghiệp vụ. Một native query đọc được bảng không có nghĩa mọi người dùng đều được phép đọc mọi bản ghi. Thêm điều kiện tenant/customer/owner nếu mô hình bảo mật yêu cầu và bảo đảm điều kiện đó không thể bị người gọi tùy ý bỏ qua.

Tên bảng, cột, schema và chiều sort không thể bind như giá trị thông thường. Nếu cần lựa chọn động, hãy ánh xạ input qua whitelist cố định và chỉ tạo query từ những identifier đã được kiểm soát.

## 14. Kiểm thử named native query

Native SQL nên được kiểm thử trên cùng loại database với môi trường chạy thật. H2 có thể hữu ích cho test nhanh, nhưng không bảo đảm tương thích với PostgreSQL, MySQL, Oracle hoặc SQL Server về dialect, kiểu dữ liệu, identifier, function và pagination.

Checklist kiểm thử:

1. Application context phát hiện named query và khởi tạo mapping thành công.
2. Tên query được gọi đúng và không trùng trong persistence unit.
3. SQL dùng đúng table/column/schema của migration.
4. Parameter được bind đúng vị trí và kiểu JDBC.
5. Entity result chứa đủ các cột được mapping.
6. DTO constructor nhận đúng thứ tự, tên alias và kiểu dữ liệu.
7. Null, aggregate, duplicate column name và dữ liệu rỗng được xử lý đúng.
8. Pagination, sort và count query trả kết quả đúng.
9. UPDATE/DELETE trả số hàng phù hợp và persistence context được đồng bộ.
10. Query có điều kiện phân quyền/tenant không thể bị bỏ qua.

Ví dụ test tích hợp:

```java
@DataJpaTest
class PurchaseOrderNativeQueryTest {

    @Autowired
    EntityManager entityManager;

    @Test
    void findsPaidOrdersUsingNamedNativeQuery() {
        List<PurchaseOrder> orders = entityManager
            .createNamedQuery(
                "PurchaseOrder.findByStatusNative",
                PurchaseOrder.class
            )
            .setParameter(1, "PAID")
            .getResultList();

        assertThat(orders)
            .allMatch(order -> "PAID".equals(order.getStatus()));
    }
}
```

Đây là khung minh họa; dữ liệu test cần được seed theo constraint và mapping thực tế. Nếu test slice không tự nhận entity hoặc mapping chứa trong cấu hình khác, hãy import đúng cấu hình persistence. Với native SQL phụ thuộc database, ưu tiên Testcontainers hoặc môi trường integration dùng cùng hệ quản trị.

## 15. Lỗi thường gặp

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Named query không tìm thấy | Gọi sai tên hoặc query chưa được đăng ký trong persistence unit | Đối chiếu name và entity scan/orm.xml |
| SQL báo không tồn tại table/column | Dùng tên property/entity thay tên vật lý hoặc schema sai | Kiểm tra migration và mapping table/column |
| Entity result thiếu field hoặc lỗi mapping | SELECT không trả đủ cột cần cho entity | Chọn đủ cột hoặc dùng DTO result mapping |
| DTO nhận sai dữ liệu | Alias, thứ tự constructor hoặc kiểu ColumnResult không khớp | Đối chiếu SQL alias và constructor |
| Parameter không bind được | Sai vị trí hoặc dùng named parameter không portable | Dùng dấu ? và setParameter theo vị trí |
| Native query chạy trên DB này nhưng lỗi DB khác | SQL dùng function/dialect riêng | Viết query theo dialect hoặc tách implementation |
| Query trả entity cũ sau native UPDATE | Persistence context vẫn giữ trạng thái cũ | Flush trước và clear/refresh sau khi cần |
| Page thiếu total | Không có count query tương ứng | Khai báo count query riêng |
| Sort gây SQL lỗi hoặc rủi ro injection | Ghép identifier từ request | Dùng whitelist hoặc query cố định |
| Ứng dụng lỗi khi khởi động | Tên query trùng hoặc metadata mapping sai | Kiểm tra toàn bộ named query và result mapping |

## 16. Bài tập thực hành

1. Khai báo `PurchaseOrder.findByStatusNative` bằng @NamedNativeQuery và trả về PurchaseOrder.
2. Gọi named query bằng EntityManager.createNamedQuery và bind status bằng positional parameter.
3. Đổi tên một column trong migration test để quan sát lỗi mapping/native SQL.
4. Viết DTO OrderSummary và ánh xạ bằng @SqlResultSetMapping + @ConstructorResult.
5. Dùng alias rõ ràng cho aggregate và xác nhận ColumnResult nhận đúng kiểu.
6. Viết native UPDATE có tên, gọi executeUpdate trong transaction và kiểm tra số hàng bị tác động.
7. Quan sát persistence context sau native UPDATE; thử flush/clear/refresh theo đúng trường hợp.
8. Thêm pagination bằng setFirstResult/setMaxResults và count query riêng.
9. Thử query trên database cùng loại production qua Testcontainers.
10. So sánh cùng một use case bằng JPQL và native SQL; đo execution plan và giải thích lý do chọn một cách.

**Nguyên tắc xuyên suốt:** @NamedNativeQuery đặt tên cho SQL native để tái sử dụng trong persistence unit. Dùng resultClass khi ánh xạ đầy đủ entity; dùng @SqlResultSetMapping khi cần DTO, scalar hoặc nhiều entity. Bind parameter theo cách portable, dùng đúng tên bảng/cột vật lý, kiểm soát identifier động và kiểm thử trên database đích. Native SQL cho quyền kiểm soát cao hơn, đồng thời yêu cầu quản lý schema, dialect và result mapping chặt chẽ hơn.
