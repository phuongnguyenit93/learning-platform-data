# Đánh đổi giữa Criteria, HQL và SQL theo độ phức tạp thực tế

Trong ứng dụng Java sử dụng Hibernate, một yêu cầu truy vấn thường có nhiều cách triển khai: **Criteria API**, **HQL/JPQL** hoặc **SQL native**. Cả ba có thể lấy được cùng một tập dữ liệu, nhưng chi phí phát triển, khả năng thay đổi, độ rõ ràng, tính di động giữa database, kiểm soát hiệu năng và rủi ro bảo trì rất khác nhau.

Không có công cụ nào thắng trong mọi tình huống:

- **HQL/JPQL** thường dễ đọc nhất cho truy vấn tương đối ổn định, diễn đạt tự nhiên theo entity và association.
- **Criteria API** đặc biệt hữu ích khi cấu trúc truy vấn phải được xây dựng động từ nhiều điều kiện, phép kết hợp hoặc reusable query specifications.
- **SQL native** thường đáng cân nhắc khi truy vấn là một bài toán quan hệ phức tạp, cần tính năng riêng của database hoặc cần kiểm soát trực tiếp SQL và kế hoạch thực thi.

Quy tắc quan trọng: **Chọn mức trừu tượng đơn giản nhất vẫn diễn đạt đúng nghiệp vụ, đủ an toàn và có hiệu năng kiểm chứng được.** Đừng chọn Criteria chỉ vì nghe “type-safe”, cũng đừng chọn SQL native cho mọi thứ vì cho rằng “ORM luôn chậm”.

Bài học nằm trong chương **Criteria và truy vấn động**, nhưng phân tích toàn bộ ba lựa chọn trong ngữ cảnh Data Persistence, Relational Access, ORM và Hibernate. Ta sẽ dùng cùng một chức năng tìm kiếm đơn hàng, triển khai bằng nhiều cách, rồi mở rộng đến báo cáo tổng hợp, pagination, bảo mật, testing và quyết định kiến trúc.

## 1. Ba tầng truy vấn và những câu hỏi khác nhau

~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ"] --> B{"Độ động và độ phức tạp?"}
    B -->|"Cố định / ít nhánh"| C["HQL / JPQL"]
    B -->|"Nhiều điều kiện cấu thành"| D["Criteria API"]
    B -->|"Báo cáo SQL đặc thù / tối ưu riêng"| E["Native SQL"]
    C --> F["Hibernate ORM + Dialect"]
    D --> F
    E --> G["JDBC / Database SQL"]
    F --> G
    G --> H["Database optimizer"]
    H --> I["Rows hoặc update counts"]
~~~

HQL và Criteria thường được Hibernate biên dịch thành **SQL** thông qua mapping và dialect. Native SQL gần database hơn, nhưng nếu chạy qua `EntityManager.createNativeQuery()`, nó vẫn được Hibernate/JDBC quản lý kết nối và parameters.

Điều đó dẫn tới hai điểm thường bị hiểu nhầm:

1. **Criteria không tự nhanh hơn HQL.** Nếu cả hai tạo SQL có cùng cấu trúc, khác biệt hiệu năng thường phụ thuộc SQL, parameters, indexes, kết quả và database plan nhiều hơn hình thức Java code.
2. **Native SQL không tự nhanh hơn ORM.** Một câu SQL viết tay vẫn có thể full table scan, thiếu index, phân trang sai hoặc nhân hàng do JOIN.

### 1.1. So sánh nhanh

| Tiêu chí | HQL/JPQL | Criteria API | Native SQL |
| --- | --- | --- | --- |
| Cách biểu đạt | Chuỗi ngôn ngữ truy vấn | Cây biểu thức Java | SQL của database |
| Truy vấn tĩnh, dễ đọc | Thường rất tốt | Có thể dài dòng | Tốt nếu SQL quen thuộc |
| Điều kiện động nhiều nhánh | Phải lắp chuỗi/query fragments cẩn thận | Thường thuận tiện | Phải lắp SQL fragments cẩn thận |
| Type safety | Có typed result, nhưng property path trong chuỗi | Mạnh hơn khi dùng static metamodel; string paths vẫn có rủi ro | Thường kiểm tra tên cột/type ở runtime |
| Liên hệ entity/association | Trực tiếp | Trực tiếp | Bằng bảng/khóa ngoại thật |
| Khả năng di động | JPQL chuẩn tương đối tốt; HQL extension phụ thuộc Hibernate | JPA Criteria chuẩn tương đối tốt | Phụ thuộc SQL dialect |
| Tính năng DB chuyên sâu | Một số được HQL hỗ trợ | JPA Criteria có giới hạn biểu đạt; vendor API có thể mở rộng | Trực tiếp nhất |
| Kết quả entity managed | Tự nhiên | Tự nhiên | Có thể mapping entity, nhưng phải cẩn thận |
| DTO projection | Constructor expression | `CriteriaBuilder.construct()` | Mapping thủ công, mapping cấu hình hoặc công cụ khác |
| Dễ quan sát SQL cuối | Cần log SQL | Cần log SQL | Câu SQL gần với code hơn, vẫn phải xem plan |
| Độ dài code | Thường ngắn | Có thể nhiều boilerplate | Tùy query và mapping |
| Tối ưu riêng từng DB | Qua HQL/dialect hoặc native | Qua provider extensions; giới hạn hơn | Linh hoạt nhất |
| Rủi ro injection | Khi nối dữ liệu vào chuỗi sai cách | Thấp hơn nếu dùng parameter APIs; dynamic identifiers vẫn phải kiểm soát | Cao nếu nối dữ liệu/identifier không tin cậy |
| Thích hợp nhất | Query ổn định, logic theo entity | Search/filter builder, query composition | Analytics nặng, recursive/DB features, specialized report |

**Từ khóa “tốt nhất” luôn đi kèm yêu cầu cụ thể**: số bộ lọc, số cách sắp xếp, kích thước dữ liệu, khả năng thay DB, số query cần bảo trì và đội ngũ vận hành.

## 2. Nguyên tắc chọn lựa trước khi viết code

Trước khi chọn API, trả lời sáu câu hỏi:

1. **Cấu trúc query có ổn định không?** Chỉ vài tham số thay đổi hay cả WHERE/JOIN/GROUP BY/ORDER BY đều thay đổi theo input?
2. **Kết quả cần là entity hay read model?** Có cần dirty checking, cascade và managed state, hay chỉ cần vài cột để trả API?
3. **Truy vấn là CRUD/domain query hay phân tích quan hệ phức tạp?** Tìm Order theo status khác với xếp hạng doanh số và tính cohort.
4. **Ứng dụng cần portable tới mức nào?** Một database duy nhất hay nhiều RDBMS/JPA providers?
5. **Tải và hiệu năng được đo ra sao?** Bao nhiêu rows, JOIN, SQL round-trips, bytes, latency, lock?
6. **Ai sẽ đọc và sửa query trong tương lai?** Cách viết nào rõ nhất với nhóm phát triển?

Nếu yêu cầu chỉ là:

> Lấy các đơn hàng đã hoàn tất trong khoảng ngày, sắp mới nhất trước.

HQL thường là lựa chọn đơn giản nhất. Nếu yêu cầu là:

> Có 12 filter tùy chọn, 4 nhóm điều kiện AND/OR, kết hợp quyền truy cập, 5 sort modes và các join chỉ xuất hiện khi cần.

Criteria hoặc một abstraction xây trên Criteria thường dễ mở rộng hơn. Nếu yêu cầu là:

> Xếp hạng top 3 sản phẩm mỗi khu vực theo rolling 30-day revenue, dùng window functions và bảng tổng hợp lớn.

Native SQL có thể diễn đạt rõ ràng và dễ tối ưu hơn, nhưng Hibernate HQL hiện đại cũng hỗ trợ một số window/CTE features; cần so sánh thực tế thay vì giả định bắt buộc phải native.

## 3. Mô hình ví dụ: tìm kiếm đơn hàng

Ta sử dụng các entity:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(nullable = false)
    private Instant createdAt;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal totalAmount;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    @Version
    private long version;

    protected PurchaseOrder() {}
}
~~~

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {}
}
~~~

~~~java
public enum OrderStatus {
    DRAFT, PAID, COMPLETED, CANCELLED
}

public enum OrderSort {
    NEWEST, OLDEST, HIGHEST_TOTAL
}
~~~

Bộ lọc của một màn hình quản trị:

~~~java
public record OrderSearchFilter(
    OrderStatus status,
    Long customerId,
    BigDecimal minimumTotal,
    Instant fromInclusive,
    Instant toExclusive,
    OrderSort sort,
    int page,
    int size
) {}
~~~

DTO kết quả:

~~~java
public record OrderSummaryView(
    Long id,
    String customerName,
    OrderStatus status,
    Instant createdAt,
    BigDecimal totalAmount
) {}
~~~

Yêu cầu:

- Những filter có giá trị `null` sẽ không tham gia WHERE.
- Nếu có `status`, lọc trạng thái.
- Nếu có `customerId`, lọc khách hàng.
- Nếu có `minimumTotal`, lọc tổng đơn lớn hơn hoặc bằng ngưỡng.
- Khoảng thời gian là **[fromInclusive, toExclusive)** để tránh lỗi cắt cuối ngày.
- Cho phép một trong ba kiểu sort đã định nghĩa.
- Trả theo trang, có secondary order theo ID để ổn định.

Đây là một tình huống rất thực tế: truy vấn cơ bản không phức tạp về quan hệ, nhưng **tổ hợp điều kiện là động**.

### 3.1. Vì sao khoảng thời gian dùng cận trên exclusive?

Nếu dùng:

~~~hql
where o.createdAt between :start and :end
~~~

cả hai cận đều inclusive. Khi lọc ngày 01/01, tự chọn 23:59:59.999 có thể bỏ sót dữ liệu với độ chính xác microseconds/nanoseconds.

Một lựa chọn rõ ràng hơn:

~~~hql
where o.createdAt >= :fromInclusive
  and o.createdAt < :toExclusive
~~~

`toExclusive` là đầu ngày kế tiếp theo timezone nghiệp vụ đã được chuyển đúng sang `Instant`. Điều này giảm lỗi ranh giới và dễ ghép các khoảng liên tiếp.

## 4. Cách 1: HQL tĩnh cho yêu cầu đơn giản

Nếu chỉ cần trạng thái và một khoảng thời gian cố định:

~~~java
List<PurchaseOrder> orders = em.createQuery("""
    select o
    from PurchaseOrder o
    where o.status = :status
      and o.createdAt >= :from
      and o.createdAt < :to
    order by o.createdAt desc, o.id desc
    """, PurchaseOrder.class)
    .setParameter("status", OrderStatus.COMPLETED)
    .setParameter("from", fromInstant)
    .setParameter("to", toInstant)
    .setMaxResults(50)
    .getResultList();
~~~

Đây là trường hợp HQL thể hiện ưu điểm:

- Ngắn, gần với cách viết SQL.
- Entity/property names rõ ràng.
- Named parameters giảm sai sót positional binding.
- ORM tạo entity managed từ kết quả.
- Hibernate dialect sinh SQL phù hợp với database.

Không cần Criteria chỉ vì muốn tạo query bằng Java API.

### 4.1. DTO projection với HQL

Nếu màn hình chỉ cần 5 trường, không nhất thiết tải toàn entity:

~~~java
List<OrderSummaryView> rows = em.createQuery("""
    select new com.example.orders.OrderSummaryView(
        o.id,
        c.name,
        o.status,
        o.createdAt,
        o.totalAmount
    )
    from PurchaseOrder o
    join o.customer c
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """, OrderSummaryView.class)
    .setParameter("status", OrderStatus.COMPLETED)
    .setMaxResults(50)
    .getResultList();
~~~

`com.example.orders.OrderSummaryView` là **tên class DTO đầy đủ giả định**; trong dự án thật thay bằng package đúng.

Projection phù hợp cho read-only API hoặc report. Nó không biến DTO thành managed entity và không cung cấp dirty checking trên chính DTO.

### 4.2. Khi query bắt đầu có nhiều filter tùy chọn

Một cách viết nhanh có thể là:

~~~hql
where (:status is null or o.status = :status)
  and (:customerId is null or o.customer.id = :customerId)
  and (:minimumTotal is null or o.totalAmount >= :minimumTotal)
~~~

Mẫu này có vẻ tiện vì một HQL dùng được cho mọi trường hợp. Nhưng có các đánh đổi:

- Hibernate/JDBC phải xử lý các tham số `null` trong biểu thức `:p is null`, có thể gặp vấn đề suy luận type ở một số dialect/driver.
- Cấu trúc `OR` có thể ảnh hưởng optimizer hoặc khả năng tận dụng index tùy DB và execution plan.
- Query quá dài nếu có hàng chục filter.
- Các JOIN/filter có thể tồn tại ngay cả khi một nhánh không cần.
- Logic AND/OR phức tạp dễ khó đọc.

Không phải mọi query có `OR :param IS NULL` đều chậm, nhưng **không nên xem đây là giải pháp miễn phí cho tìm kiếm động**. Có thể tạo WHERE chỉ chứa filter được cung cấp.

## 5. Cách 2: HQL động bằng các đoạn được kiểm soát

Với số filter vừa phải, có thể lắp HQL từ **các fragment do server định nghĩa sẵn**:

~~~java
public List<OrderSummaryView> searchWithHql(
        EntityManager em,
        OrderSearchFilter filter) {

    StringBuilder hql = new StringBuilder("""
        select new com.example.orders.OrderSummaryView(
            o.id, c.name, o.status, o.createdAt, o.totalAmount
        )
        from PurchaseOrder o
        join o.customer c
        where 1 = 1
        """);

    if (filter.status() != null) {
        hql.append(" and o.status = :status");
    }
    if (filter.customerId() != null) {
        hql.append(" and c.id = :customerId");
    }
    if (filter.minimumTotal() != null) {
        hql.append(" and o.totalAmount >= :minimumTotal");
    }
    if (filter.fromInclusive() != null) {
        hql.append(" and o.createdAt >= :from");
    }
    if (filter.toExclusive() != null) {
        hql.append(" and o.createdAt < :to");
    }

    OrderSort sort = filter.sort() == null
        ? OrderSort.NEWEST
        : filter.sort();

    hql.append(switch (sort) {
        case NEWEST -> " order by o.createdAt desc, o.id desc";
        case OLDEST -> " order by o.createdAt asc, o.id asc";
        case HIGHEST_TOTAL ->
            " order by o.totalAmount desc, o.id desc";
    });

    TypedQuery<OrderSummaryView> query =
        em.createQuery(hql.toString(), OrderSummaryView.class);

    if (filter.status() != null) {
        query.setParameter("status", filter.status());
    }
    if (filter.customerId() != null) {
        query.setParameter("customerId", filter.customerId());
    }
    if (filter.minimumTotal() != null) {
        query.setParameter("minimumTotal", filter.minimumTotal());
    }
    if (filter.fromInclusive() != null) {
        query.setParameter("from", filter.fromInclusive());
    }
    if (filter.toExclusive() != null) {
        query.setParameter("to", filter.toExclusive());
    }

    return query
        .setFirstResult(Math.multiplyExact(filter.page(), filter.size()))
        .setMaxResults(filter.size())
        .getResultList();
}
~~~

Ví dụ giả định đầu vào đã được validate: `page >= 0`, `1 <= size <= giới hạn ứng dụng`, `fromInclusive < toExclusive` nếu cả hai tồn tại. `Math.multiplyExact()` giúp phát hiện overflow phép nhân int, nhưng không thay việc validate input.

### 5.1. Tại sao lắp chuỗi kiểu này có thể an toàn?

Vì **chỉ nối những fragment cố định, do code ứng dụng kiểm soát**, còn giá trị người dùng đi qua `setParameter()`.

**Không viết:**

~~~java
hql.append(" and c.name = '" + userInput + "'");
~~~

Đây là một lỗi injection và escaping. Thay bằng:

~~~java
hql.append(" and c.name = :name");
query.setParameter("name", userInput);
~~~

### 5.2. Dynamic ORDER BY phải có whitelist

Không được nối trực tiếp:

~~~java
hql.append(" order by " + request.getParameter("sort"));
~~~

Tên field, tên bảng hoặc keyword trong ORDER BY không thể được bind như giá trị JDBC thông thường. Hãy map input thành enum hoặc whitelist:

~~~java
String orderExpression = switch (sort) {
    case NEWEST -> "o.createdAt desc, o.id desc";
    case OLDEST -> "o.createdAt asc, o.id asc";
    case HIGHEST_TOTAL -> "o.totalAmount desc, o.id desc";
};
~~~

Điều này vừa ngăn injection, vừa giới hạn những field mà API được phép dùng để sắp xếp.

### 5.3. Khi nào HQL string builder trở nên khó bảo trì?

Khi query có:

- Nhiều group AND/OR lồng nhau.
- Join tùy chọn tới 5–10 association.
- Subquery được thêm/bỏ tùy filter.
- Những predicate tái sử dụng giữa các màn hình.
- Nhiều kiểu projection và thống kê.

Khi đó, việc nối chuỗi và giữ danh sách parameter tương ứng dễ mất đồng bộ. Criteria API có thể phù hợp hơn.

## 6. Cách 3: Criteria API cho nhiều filter động

Jakarta Persistence Criteria API tạo cây biểu thức truy vấn bằng các object Java thay vì HQL string.

Các thành phần chính:

| API | Vai trò |
| --- | --- |
| `CriteriaBuilder` | Tạo predicate, expression, aggregate, order và query |
| `CriteriaQuery<T>` | Khai báo kiểu kết quả và cấu trúc SELECT |
| `Root<T>` | Root entity trong FROM |
| `Join<X,Y>` | Liên kết association trong FROM |
| `Predicate` | Biểu thức điều kiện WHERE/HAVING |
| `Path<T>` | Đường dẫn thuộc tính |
| `Order` | Biểu thức ORDER BY |
| `TypedQuery<T>` | Bind parameters, pagination, execute |

Một ví dụ tương đương với HQL động:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import jakarta.persistence.criteria.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

public List<OrderSummaryView> searchWithCriteria(
        EntityManager em,
        OrderSearchFilter filter) {

    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<OrderSummaryView> cq =
        cb.createQuery(OrderSummaryView.class);

    Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);
    Join<PurchaseOrder, Customer> customer =
        order.join("customer", JoinType.INNER);

    List<Predicate> predicates = new ArrayList<>();

    if (filter.status() != null) {
        predicates.add(
            cb.equal(order.get("status"), filter.status()));
    }

    if (filter.customerId() != null) {
        predicates.add(
            cb.equal(customer.get("id"), filter.customerId()));
    }

    if (filter.minimumTotal() != null) {
        Path<BigDecimal> amount = order.get("totalAmount");
        predicates.add(
            cb.greaterThanOrEqualTo(amount, filter.minimumTotal()));
    }

    if (filter.fromInclusive() != null) {
        Path<Instant> createdAt = order.get("createdAt");
        predicates.add(
            cb.greaterThanOrEqualTo(createdAt, filter.fromInclusive()));
    }

    if (filter.toExclusive() != null) {
        Path<Instant> createdAt = order.get("createdAt");
        predicates.add(
            cb.lessThan(createdAt, filter.toExclusive()));
    }

    cq.select(cb.construct(
        OrderSummaryView.class,
        order.get("id"),
        customer.get("name"),
        order.get("status"),
        order.get("createdAt"),
        order.get("totalAmount")
    ));

    cq.where(cb.and(predicates.toArray(new Predicate[0])));

    OrderSort sort = filter.sort() == null
        ? OrderSort.NEWEST
        : filter.sort();

    cq.orderBy(switch (sort) {
        case NEWEST -> List.of(
            cb.desc(order.get("createdAt")),
            cb.desc(order.get("id")));
        case OLDEST -> List.of(
            cb.asc(order.get("createdAt")),
            cb.asc(order.get("id")));
        case HIGHEST_TOTAL -> List.of(
            cb.desc(order.get("totalAmount")),
            cb.desc(order.get("id")));
    });

    TypedQuery<OrderSummaryView> query = em.createQuery(cq);

    return query
        .setFirstResult(Math.multiplyExact(filter.page(), filter.size()))
        .setMaxResults(filter.size())
        .getResultList();
}
~~~

**Đặc điểm đáng chú ý:**

- Mỗi filter chỉ được thêm khi có dữ liệu.
- `List<Predicate>` cho phép dựng WHERE từng bước.
- `cb.and(...)` kết hợp các predicate một cách tường minh.
- Sort được chọn bằng enum; không phải nối chuỗi do client gửi.
- `cb.construct()` tạo DTO projection.
- Tên bảng/cột SQL do Hibernate mapping quyết định.

Một số code Criteria dài hơn HQL dù logic SQL tương đương. **Đây là chi phí đổi lấy khả năng cấu thành truy vấn có cấu trúc.**

### 6.1. Criteria vẫn có thể dùng string property names

Trong ví dụ có:

~~~java
order.get("totalAmount")
~~~

Nếu đổi field Java từ `totalAmount` sang `amount` mà quên sửa string, compiler có thể không phát hiện; lỗi xuất hiện khi xây/execute query.

Vì thế “Criteria luôn type-safe ở compile time” là khẳng định quá rộng. Để hưởng lợi nhiều hơn từ type safety, hãy dùng **JPA static metamodel**.

### 6.2. Static metamodel

Annotation processor có thể tạo class dạng:

~~~java
@StaticMetamodel(PurchaseOrder.class)
public abstract class PurchaseOrder_ {
    public static volatile SingularAttribute<PurchaseOrder, Long> id;
    public static volatile SingularAttribute<PurchaseOrder, BigDecimal>
        totalAmount;
    // Các attribute khác do processor tạo.
}
~~~

Đây là **dạng mô tả** của generated metamodel; không nên tự viết tay class `PurchaseOrder_` cho ứng dụng thông thường.

Khi processor tạo metamodel, Criteria có thể dùng:

~~~java
Path<BigDecimal> amount = order.get(PurchaseOrder_.totalAmount);

predicates.add(
    cb.greaterThanOrEqualTo(amount, filter.minimumTotal()));
~~~

Nếu tên property đổi và metamodel được sinh lại đúng cách, code tham chiếu constant cũ có thể không compile. Điều này giúp refactor an toàn hơn so với string-based paths.

### 6.3. Type safety không thay kiểm thử logic

Static metamodel giúp bắt lỗi thuộc tính/kiểu ở compile time trong nhiều trường hợp. Nó không tự chứng minh:

- Predicate dùng `AND` đúng thay vì `OR`.
- Join type có giữ lại row optional hay không.
- Query có nhân rows từ association to-many.
- Filter tenant/authorization đã được thêm chưa.
- Pagination/count query có đúng không.

Criteria type-safe về **một phần cấu trúc truy vấn**, không đảm bảo business correctness.

## 7. Tiêu chí thật sự khiến Criteria đáng giá: khả năng tổ hợp

Giá trị lớn của Criteria không phải chỉ để đổi:

~~~hql
where o.status = :status
~~~

thành:

~~~java
cb.equal(root.get("status"), status)
~~~

mà là **tái sử dụng logic predicate** trong nhiều truy vấn động.

Ví dụ helper:

~~~java
private static List<Predicate> buildOrderPredicates(
        CriteriaBuilder cb,
        Root<PurchaseOrder> order,
        OrderSearchFilter filter) {

    List<Predicate> predicates = new ArrayList<>();

    if (filter.status() != null) {
        predicates.add(
            cb.equal(order.get("status"), filter.status()));
    }

    if (filter.minimumTotal() != null) {
        Path<BigDecimal> amount = order.get("totalAmount");
        predicates.add(
            cb.greaterThanOrEqualTo(amount, filter.minimumTotal()));
    }

    if (filter.fromInclusive() != null) {
        Path<Instant> createdAt = order.get("createdAt");
        predicates.add(
            cb.greaterThanOrEqualTo(createdAt, filter.fromInclusive()));
    }

    if (filter.toExclusive() != null) {
        Path<Instant> createdAt = order.get("createdAt");
        predicates.add(
            cb.lessThan(createdAt, filter.toExclusive()));
    }

    if (filter.customerId() != null) {
        predicates.add(cb.equal(
            order.get("customer").get("id"), filter.customerId()));
    }

    return predicates;
}
~~~

Sau đó list query và count query có thể gọi cùng **hàm dựng predicate**, nhưng phải dựng lại predicate trên **Root tương ứng của từng CriteriaQuery**.

### 7.1. Vì sao không dùng lại object Predicate giữa hai CriteriaQuery?

`Predicate` thường tham chiếu `Path` và `Root` thuộc một query tree nhất định. Nếu cố copy cùng object predicate từ list query sang count query với root khác, có thể tạo path không thuộc đúng query hoặc dẫn đến SQL/exception không mong muốn.

**Tái sử dụng công thức xây predicate, không tái sử dụng object Predicate đã gắn với một Root khác.**

Đây là một quy tắc quan trọng khi viết generic Criteria builders.

### 7.2. Nhóm AND/OR phức tạp

Ví dụ yêu cầu:

> Order thuộc status COMPLETED, đồng thời (tổng >= 1 triệu **hoặc** customer có ID trong nhóm VIP).

Criteria biểu diễn rõ cấu trúc:

~~~java
Predicate isCompleted =
    cb.equal(order.get("status"), OrderStatus.COMPLETED);

Predicate isHighValue =
    cb.ge(order.<BigDecimal>get("totalAmount"),
          new BigDecimal("1000000"));

Predicate isVip =
    order.get("customer").get("id").in(vipCustomerIds);

Predicate combined = cb.and(
    isCompleted,
    cb.or(isHighValue, isVip)
);
~~~

`cb.ge(...)` cho numeric expressions; cũng có thể dùng `cb.greaterThanOrEqualTo(...)` cho comparable types. Đối với danh sách VIP rỗng, cần xác định semantics và xử lý riêng để tránh SQL `IN ()` không portable.

Đọc cấu trúc Java này có thể rõ hơn so với nối nhiều nhánh HQL string, đặc biệt khi nhóm predicate được tạo từ các component độc lập.

### 7.3. Reusable query fragments phải mang ngữ nghĩa domain

Không chỉ tạo helper chung kiểu `addStringFilter(...)` rồi ghép mọi thứ vô tội vạ. Các predicate thực sự hữu ích thường có tên theo domain:

- `visibleToTenant(tenantId)`
- `hasStatus(status)`
- `createdWithin(from, to)`
- `hasPaidInvoice()`
- `matchesAllowedCustomerIds(ids)`

Tên này giúp review bảo mật và nghiệp vụ, đồng thời giảm khả năng vô tình bỏ sót filter.

## 8. Count query cho phân trang: chỗ Criteria dễ bị sai

Khi UI cần `Page<OrderSummaryView>`, thường phải có:

1. Query lấy các rows của trang.
2. Query `COUNT` số root entities phù hợp điều kiện.

Với Criteria, cần tạo count query riêng:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Long> countQuery =
    cb.createQuery(Long.class);

Root<PurchaseOrder> root =
    countQuery.from(PurchaseOrder.class);

List<Predicate> predicates =
    buildOrderPredicates(cb, root, filter);

countQuery.select(cb.count(root));
countQuery.where(cb.and(
    predicates.toArray(new Predicate[0])
));

Long total = em.createQuery(countQuery)
    .getSingleResult();
~~~

**Điểm then chốt:** không bê nguyên fetch joins, projection hoặc ORDER BY từ content query sang count query.

### 8.1. Count query không cần fetch collection

Không nên dùng:

~~~java
root.fetch("lines", JoinType.LEFT);
countQuery.select(cb.count(root));
~~~

Fetch join dùng để khởi tạo association cho entity được trả về. Count query không trả entity root để tiêu thụ fetch, nên fetch join trong count thường không hợp lệ hoặc tạo SQL phình to.

### 8.2. Join to-many có thể đếm trùng

Giả sử Order có 4 dòng hàng. Khi count query JOIN `o.lines`, một Order có thể tạo 4 rows. Nếu mục tiêu đếm **số Order**, không phải số dòng hàng, có thể cần:

~~~java
countQuery.select(cb.countDistinct(root));
~~~

Hoặc thiết kế lại filter theo `EXISTS` để tránh nhân root rows.

### 8.3. Count query có thể không cần join nào

Nếu filter chỉ theo status, customerId, amount và date, ORM có thể biểu diễn điều kiện trực tiếp trên bảng orders hoặc JOIN cần thiết. Đừng thêm `lines` join chỉ vì page DTO có số dòng hàng hoặc màn hình sẽ hiển thị collection sau này.

### 8.4. Page và Slice

Nếu UI chỉ cần biết còn trang tiếp theo, một query tải `pageSize + 1` hàng rồi trả `Slice` có thể tránh một COUNT đắt. Nhưng nếu cần tổng số trang, tổng bản ghi hoặc điều hướng chính xác, COUNT vẫn cần thiết.

Đây là quyết định **API/product**, không chỉ quyết định HQL/Criteria.

## 9. EXISTS thay JOIN trong nhiều filter to-many

Yêu cầu: tìm các Order có ít nhất một dòng hàng với số lượng >= 10.

HQL dùng EXISTS:

~~~hql
select o
from PurchaseOrder o
where exists (
    select 1
    from OrderLine l
    where l.order = o
      and l.quantity >= :minimumQuantity
)
~~~

`EXISTS` biểu diễn rõ “có ít nhất một dòng”. Nó không cần nhân root Order theo số matching OrderLine.

Criteria tương đương:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Subquery<Integer> sq = cq.subquery(Integer.class);
Root<OrderLine> line = sq.from(OrderLine.class);

sq.select(cb.literal(1));
sq.where(
    cb.equal(line.get("order"), order),
    cb.ge(line.get("quantity"), minimumQuantity)
);

cq.select(order).where(cb.exists(sq));

List<PurchaseOrder> result =
    em.createQuery(cq).getResultList();
~~~

Về mặt ý nghĩa, cả hai là semijoin-style filter. Nhưng SQL optimizer có thể chọn chiến lược khác nhau. Cần kiểm tra SQL và execution plan thay vì kết luận EXISTS luôn nhanh hơn JOIN + DISTINCT.

### 9.1. Khi query có nhiều EXISTS

Nếu form có nhiều filter “có ít nhất một X”, “không có Y”, “có event Z sau ngày D”, Criteria builders giúp cấu thành các subquery tùy chọn. Nhưng code sẽ phức tạp hơn đáng kể; nên chia thành helper theo domain và test từng predicate.

### 9.2. NOT EXISTS khi cần absence

HQL:

~~~hql
select o
from PurchaseOrder o
where not exists (
    select 1
    from OrderLine l
    where l.order = o
)
~~~

thường biểu đạt “Order không có dòng hàng” rõ ràng hơn các thủ thuật LEFT JOIN + IS NULL trong một số truy vấn phức tạp. Cả hai có thể đúng tùy mapping và điều kiện; chọn cách dễ chứng minh semantics.

## 10. Spring Data JPA Specification: Criteria có thể tái sử dụng tốt hơn

Nếu ứng dụng dùng Spring Data JPA, `Specification<T>` là một abstraction dựa trên Criteria.

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long>,
                JpaSpecificationExecutor<PurchaseOrder> {
}
~~~

Specification:

~~~java
import org.springframework.data.jpa.domain.Specification;

public final class OrderSpecs {

    private OrderSpecs() {}

    public static Specification<PurchaseOrder> statusIs(
            OrderStatus status) {

        return (root, query, cb) ->
            status == null
                ? cb.conjunction()
                : cb.equal(root.get("status"), status);
    }

    public static Specification<PurchaseOrder> totalAtLeast(
            BigDecimal minimum) {

        return (root, query, cb) ->
            minimum == null
                ? cb.conjunction()
                : cb.greaterThanOrEqualTo(
                    root.<BigDecimal>get("totalAmount"), minimum);
    }
}
~~~

Cách dùng:

~~~java
Specification<PurchaseOrder> spec =
    OrderSpecs.statusIs(filter.status())
        .and(OrderSpecs.totalAtLeast(filter.minimumTotal()));

Pageable pageable = PageRequest.of(
    filter.page(),
    filter.size(),
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Page<PurchaseOrder> page =
    orderRepository.findAll(spec, pageable);
~~~

`Pageable` và `PageRequest` thuộc Spring Data, không phải JPA chuẩn. Ví dụ này chỉ chứa hai filter để minh họa composition; các filter khác được thêm bằng `Specification` tương tự.

### 10.1. Vì sao Specification hữu ích?

Nó giúp tái sử dụng domain predicates qua nhiều repository queries và giảm nhu cầu ghép HQL string. Đội ngũ có thể xây một thư viện filter nhỏ, composable và test độc lập.

### 10.2. Đừng đặt fetch join vô điều kiện trong mọi Specification

Một anti-pattern thường thấy:

~~~java
return (root, query, cb) -> {
    root.fetch("lines", JoinType.LEFT);
    return cb.equal(root.get("status"), status);
};
~~~

Vì Spring Data có thể dùng specification trong count query và content query, fetch join như trên có thể khiến count query lỗi hoặc tính sai. Hơn nữa, collection fetch join với pagination có thể dẫn tới in-memory pagination.

Hãy tách **predicate specification** khỏi **fetch plan**. Dùng entity graph hoặc custom repository query phù hợp khi cần fetch, và xác định cách pagination hoạt động.

### 10.3. Specification không giải quyết mọi projection

`JpaSpecificationExecutor` giúp truy vấn entity và một số fluent query/projection tùy phiên bản Spring Data, nhưng yêu cầu DTO phức tạp, grouping, nhiều select expressions hoặc DB-specific SQL có thể khiến custom repository dùng Criteria/HQL/native rõ ràng hơn.

Đừng ép mọi báo cáo thành một `Specification<PurchaseOrder>` khổng lồ chỉ để giữ cùng một abstraction.

## 11. Cách 4: Native SQL cho cùng bộ lọc

Native SQL sử dụng **table names và column names**. Với schema minh họa:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP,
    total_amount DECIMAL(19,2),
    version BIGINT
);

CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);
~~~

SQL tìm kiếm có thể là:

~~~sql
SELECT
    o.id,
    c.name AS customer_name,
    o.status,
    o.created_at,
    o.total_amount
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = :status
  AND o.total_amount >= :minimumTotal
ORDER BY o.created_at DESC, o.id DESC
~~~

Câu SQL này không cần ORM để biểu đạt JOIN. Nó cũng khiến developer nhìn thấy cột/index và cấu trúc thực tế.

### 11.1. Native SQL động an toàn

Một ví dụ tìm các ID phù hợp qua JPA native query:

~~~java
public List<Long> findOrderIdsNative(
        EntityManager em,
        OrderSearchFilter filter) {

    StringBuilder sql = new StringBuilder("""
        select o.id
        from purchase_orders o
        where 1 = 1
        """);

    if (filter.status() != null) {
        sql.append(" and o.status = :status");
    }
    if (filter.minimumTotal() != null) {
        sql.append(" and o.total_amount >= :minimumTotal");
    }
    if (filter.customerId() != null) {
        sql.append(" and o.customer_id = :customerId");
    }
    if (filter.fromInclusive() != null) {
        sql.append(" and o.created_at >= :from");
    }
    if (filter.toExclusive() != null) {
        sql.append(" and o.created_at < :to");
    }

    OrderSort sort = filter.sort() == null
        ? OrderSort.NEWEST : filter.sort();

    sql.append(switch (sort) {
        case NEWEST -> " order by o.created_at desc, o.id desc";
        case OLDEST -> " order by o.created_at asc, o.id asc";
        case HIGHEST_TOTAL ->
            " order by o.total_amount desc, o.id desc";
    });

    Query q = em.createNativeQuery(sql.toString());

    if (filter.status() != null) {
        q.setParameter("status", filter.status().name());
    }
    if (filter.minimumTotal() != null) {
        q.setParameter("minimumTotal", filter.minimumTotal());
    }
    if (filter.customerId() != null) {
        q.setParameter("customerId", filter.customerId());
    }
    if (filter.fromInclusive() != null) {
        q.setParameter("from", filter.fromInclusive());
    }
    if (filter.toExclusive() != null) {
        q.setParameter("to", filter.toExclusive());
    }

    q.setFirstResult(Math.multiplyExact(filter.page(), filter.size()));
    q.setMaxResults(filter.size());

    return q.getResultStream()
        .map(value -> ((Number) value).longValue())
        .toList();
}
~~~

Ví dụ **chỉ trả IDs** để tránh trình bày rườm rà việc ánh xạ năm cột qua JDBC types. Với dữ liệu thực tế, query native có thể trả `Object[]`, DTO mapping/`@SqlResultSetMapping` hoặc kết quả mapped entity theo API tương ứng.

Những điểm cần kiểm tra:

- `OrderStatus` được lưu bằng `EnumType.STRING`, nên ví dụ native bind `name()`. Nếu schema dùng ordinal hoặc custom converter, phải điều chỉnh.
- Kiểu SQL/JDBC của `Instant` phụ thuộc mapping và database; cần test query trên DB thực.
- Tính di động của native parameters và pagination tùy provider/dialect.
- Mọi fragment SQL nối vào đều do server định nghĩa, còn giá trị đi qua bind parameters.
- Không ghép raw ORDER BY từ client.

### 11.2. Chọn native SQL có thật sự đáng không?

Với bộ lọc đơn giản này, HQL/Criteria thường tiết kiệm công hơn vì không phải lặp table/column names và conversion. Native SQL trở nên hấp dẫn hơn nếu:

- Query phải tận dụng function/index hints riêng của DB.
- Kết quả là báo cáo aggregate hoặc projection không cần entity.
- DBA và team tối ưu trực tiếp trên SQL.
- ORM-generated SQL có hạn chế đã được xác minh.
- Cần sử dụng feature SQL được HQL/Criteria không biểu đạt rõ hoặc không hỗ trợ trong stack hiện tại.

**Sự tồn tại của SQL native là một lựa chọn kỹ thuật, không phải bằng chứng ORM không phù hợp.**

## 12. Bài toán phức tạp hơn: top-N mỗi nhóm

Yêu cầu:

> Với mỗi khách hàng, lấy tối đa ba đơn hàng mới nhất đã hoàn tất trong 30 ngày.

Đây là bài toán **top-N per group**. Một SQL sử dụng window function có thể rõ ràng:

~~~sql
WITH ranked AS (
    SELECT
        o.id,
        o.customer_id,
        o.created_at,
        o.total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.created_at DESC, o.id DESC
        ) AS rn
    FROM purchase_orders o
    WHERE o.status = :status
      AND o.created_at >= :from
)
SELECT r.id, r.customer_id, r.created_at, r.total_amount
FROM ranked r
WHERE r.rn <= :perCustomer
ORDER BY r.customer_id, r.rn;
~~~

Ưu điểm:

- Rõ logic xếp hạng theo từng customer.
- Sử dụng feature SQL chuyên cho bài toán.
- Dễ đưa vào database EXPLAIN.
- Không cần dựng graph entity rồi lọc bằng Java.

Hibernate HQL 6.x có hỗ trợ một số CTE/window functions khi phù hợp dialect, nên **không được kết luận native SQL là cách duy nhất**. Nhưng nếu team đã chuẩn hóa một database và SQL là cách ngắn, dễ tối ưu nhất, native query có thể hợp lý.

### 12.1. Vì sao Criteria chuẩn có thể không phải lựa chọn tốt nhất?

Criteria API tiêu chuẩn JPA có những giới hạn biểu đạt với window/CTE tùy phiên bản Jakarta Persistence. Có thể dùng Hibernate-specific Criteria extensions hoặc các library khác, nhưng khi đó code có thể phức tạp hơn SQL ban đầu.

Nếu đang cố tạo một cây Criteria dài hàng trăm dòng chỉ để biểu diễn một CTE 20 dòng dễ đọc, hãy đánh giá lại mức trừu tượng.

### 12.2. Khi nào HQL nâng cao là điểm cân bằng?

Nếu cùng một window query được HQL phiên bản đang dùng hỗ trợ tốt, có thể viết bằng entity/property names và để dialect chuyển SQL. Điều đó thuận lợi cho schema refactoring và result mapping, nhưng vẫn phụ thuộc Hibernate HQL extension và database capabilities.

Cần so sánh ba thứ:

1. Query có rõ ràng không?
2. SQL Hibernate sinh có đúng, hiệu quả và dễ giải thích không?
3. Dự án có chấp nhận phụ thuộc Hibernate/dialect không?

### 12.3. SQL native và tính năng riêng DB là quyết định có chủ đích

Nếu dùng `DATE_TRUNC`, JSONB operators, `DISTINCT ON` hay DB-specific index hints, hãy ghi rõ database product/version và có integration tests trên DB đó. Đừng mô tả truy vấn đó là portable SQL cho mọi RDBMS.

## 13. Chi phí phát triển so với chi phí thực thi

Một công cụ query có ít code hơn chưa chắc có runtime tốt hơn. Ngược lại, một query cực kỳ tối ưu nhưng khó hiểu có thể tốn nhiều chi phí bảo trì.

Có thể nhìn trade-off qua bốn trục:

| Trục | Điều cần đánh giá |
| --- | --- |
| Độ rõ ràng | Người đọc có hiểu phép lọc, join, grouping và sort không? |
| Độ linh hoạt | Thêm filter mới có sửa nhiều chỗ và tăng rủi ro không? |
| Chi phí runtime | SQL statements, round-trips, rows, bytes, CPU, IO, locks |
| Khả năng bảo trì | Refactor mapping/schema, upgrade Hibernate/DB, testing |

Ví dụ:

- HQL 12 dòng, SQL ra 2 SELECT: có thể tốt hơn Criteria 80 dòng nếu filter tĩnh.
- Criteria 150 dòng nhưng lắp được 20 filter kiểm thử độc lập: có thể tốt hơn 40 biến thể HQL string.
- SQL 30 dòng dùng window functions: có thể tốt hơn 300 dòng Java gom và xếp hạng entity trong memory.

Không đánh giá query chỉ bằng **số dòng Java** hoặc **số round-trip SQL**.

## 14. Hiệu năng: SQL sinh ra mới là thứ cần đo

HQL và Criteria đều được Hibernate chuyển thành SQL; native SQL cũng phải được database tối ưu và thực thi. Quy trình đo cần dựa trên SQL cuối, không chỉ code.

Bật log phát triển trong Hibernate 6:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE

spring:
  jpa:
    properties:
      hibernate:
        format_sql: true
        generate_statistics: true
~~~

`org.hibernate.orm.jdbc.bind` có thể log giá trị tham số nhạy cảm; **không bật TRACE tràn lan trên production**.

### 14.1. Nên kiểm tra gì?

- SQL có JOIN nào ngoài dự kiến?
- Predicate có dùng đúng index/column?
- Query có phân trang ở SQL hay trong memory?
- Có N+1 do lazy loading sau query?
- Có Cartesian product khi fetch nhiều to-many?
- Có ORDER BY ổn định?
- Aggregate có đếm trùng vì JOIN?
- Count query có tốn hơn content query?
- SQL có fetch mọi cột/LOB không cần thiết?
- Database có áp dụng execution plan hợp lý không?

### 14.2. Một Criteria và một HQL cùng SQL: không có phép màu

Ví dụ Criteria:

~~~java
cb.equal(root.get("status"), OrderStatus.COMPLETED)
~~~

và HQL:

~~~hql
where o.status = :status
~~~

có thể sinh cùng một SQL predicate. Nếu mapping, fetch plan, bind values và SQL cuối giống nhau, tốc độ truy vấn DB thường cùng một bậc. Chọn dựa trên maintainability và cấu trúc query thay vì kỳ vọng Criteria tự cải thiện index use.

### 14.3. EXPLAIN trên database thật

Với PostgreSQL, có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.id, o.created_at
FROM purchase_orders o
WHERE o.status = 'COMPLETED'
ORDER BY o.created_at DESC, o.id DESC
LIMIT 20;
~~~

`EXPLAIN ANALYZE` trên PostgreSQL thực thi truy vấn để lấy số liệu thực. Đối với DML, điều này có thể gây thay đổi dữ liệu; đừng dùng trên production một cách tùy tiện.

Đánh giá actual rows, index scan, sort, join strategy, buffer reads và execution time trên dữ liệu gần production. SQL đẹp mắt vẫn có thể chậm nếu thiếu index.

### 14.4. Hibernate Statistics hỗ trợ đếm statements

Hibernate `SessionFactory.getStatistics()` có thể cho biết prepared statement count, entity load, collection fetch và cache behavior. Nhưng statistics thường có scope toàn SessionFactory, không tự cô lập một request; khi test song song phải kiểm soát nhiễu.

StatementInspector có thể capture SQL template. Khi cần biết thời gian thực thi DB, dùng thêm metrics/tracing và DB profiler.

## 15. N+1, fetch join và DTO không phụ thuộc lựa chọn API

Một query HQL, Criteria hoặc native chỉ là điểm khởi đầu. Sau khi Hibernate trả entity managed, code có thể truy cập lazy associations và phát SQL phụ.

Ví dụ:

~~~java
List<PurchaseOrder> orders = em.createQuery("""
    select o from PurchaseOrder o
    where o.status = :status
    """, PurchaseOrder.class)
    .setParameter("status", OrderStatus.COMPLETED)
    .getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
~~~

Nếu Customer được lazy load mà không có cache/batch phù hợp, có thể phát thêm nhiều SELECT. Thay HQL bằng Criteria mà vẫn trả cùng root entities sẽ **không tự xử lý N+1**.

Các cách:

- `join fetch` cho một to-one association thực sự cần.
- DTO projection chỉ lấy field yêu cầu.
- EntityGraph phù hợp với màn hình.
- Batch fetching hoặc subselect cho collection.
- Split queries để tránh nhiều collection join chéo.

### 15.1. Join không đồng nghĩa fetch

Trong HQL:

~~~hql
join o.customer c
~~~

là join dùng cho điều kiện/projection; không nhất thiết khởi tạo association `o.customer` trên entity result. Trong Criteria, `root.join()` khác `root.fetch()` về ý định fetch.

Cần phân biệt query join với fetch plan, nhất là khi kết quả trả entity managed.

### 15.2. Nhiều collection fetch join

Một Order có 10 lines và 8 tags, fetch join đồng thời có thể tạo khoảng 80 tổ hợp SQL rows. Với hai bag, Hibernate có thể báo `MultipleBagFetchException` trong những mapping nhất định.

Criteria không tránh được hiện tượng này nếu sinh cùng join plan. SQL native tự JOIN cũng không tránh được tích Cartesian. Cần thay cách lấy dữ liệu, không chỉ thay ngôn ngữ query.

## 16. Sorting động: bảo mật và tính nhất quán

Sorting động là điểm dễ bị injection trong HQL/SQL string builders, và là nơi Criteria có lợi thế về API cấu trúc.

### 16.1. Không bind column name như value

Sai về semantics:

~~~sql
ORDER BY :columnName
~~~

Parameter bind thường biểu diễn một giá trị literal, **không phải identifier** của cột để database thay đổi cấu trúc query.

### 16.2. Whitelist bắt buộc với SQL và HQL

~~~java
String sortSql = switch (filter.sort()) {
    case NEWEST -> "o.created_at desc, o.id desc";
    case OLDEST -> "o.created_at asc, o.id asc";
    case HIGHEST_TOTAL -> "o.total_amount desc, o.id desc";
};
~~~

Có thể truyền `sortSql` vào câu SQL vì nó đến từ nhánh cố định của server, không phải raw user input.

### 16.3. Criteria không miễn trừ authorization

Ngay cả khi dùng:

~~~java
cb.desc(root.get(sortField))
~~~

nếu `sortField` lấy từ client, có thể cho phép truy cập thuộc tính không được phép hoặc dẫn đến lỗi. Vẫn cần whitelist các trường được phép sắp xếp, đặc biệt khi API có dữ liệu nhạy cảm.

### 16.4. Tie-breaker theo ID

Nếu nhiều Order có cùng `createdAt` hoặc `totalAmount`, thêm `id` vào ORDER BY giúp pagination ổn định hơn. Nếu dữ liệu thay đổi liên tục giữa các page requests, offset pagination vẫn có thể nhảy/mất hàng; có thể cần keyset pagination theo use case.

## 17. Tìm kiếm văn bản và escaping LIKE

Một filter tìm tên khách hàng chứa chuỗi nhập từ người dùng có thể dùng:

~~~hql
where lower(c.name) like :namePattern
~~~

Parameter bind giúp chống injection, nhưng **%** và **_** trong SQL LIKE vẫn là wildcard, không phải ký tự literal.

Nếu yêu cầu là tìm chính xác chuỗi có ký tự `%` hoặc `_`, cần escape wildcard theo database/dialect.

Ví dụ helper trong Java:

~~~java
static String escapeLike(String input) {
    return input
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_");
}
~~~

Criteria có overload `like(..., char escapeChar)`:

~~~java
String normalized = userInput.toLowerCase(Locale.ROOT);
String pattern = "%" + escapeLike(normalized) + "%";

Predicate nameMatch = cb.like(
    cb.lower(customer.get("name")),
    pattern,
    '\\'
);
~~~

Cách escape này dựa vào ký tự `\` làm escape character; SQL Hibernate sinh và khả năng tương thích cần được kiểm thử trên database mục tiêu.

Ngoài ra, gọi `lower(column)` có thể làm thay đổi khả năng dùng index thông thường. Tùy DB, cân nhắc functional index, collation/case-insensitive type hoặc full-text search.

### 17.1. Tìm kiếm text phức tạp không nhất thiết thuộc Criteria

Nếu cần ranking theo độ liên quan, stemming, language tokenization hoặc full-text index, tính năng database-specific hay search engine có thể phù hợp hơn `LIKE '%...%'` qua Criteria.

**Đừng ép chức năng tìm kiếm toàn văn vào Criteria chỉ vì đó là “truy vấn động”.** Bản chất dữ liệu và công cụ index mới quyết định.

## 18. Null semantics: lỗi logic chung của cả ba cách

SQL dùng three-valued logic với TRUE, FALSE và UNKNOWN. So sánh:

~~~sql
column = NULL
~~~

không tương đương:

~~~sql
column IS NULL
~~~

Trong HQL:

~~~hql
where o.customer is null
~~~

Trong Criteria:

~~~java
cb.isNull(root.get("customer"))
~~~

Trong native SQL:

~~~sql
where o.customer_id is null
~~~

Ví dụ entity `PurchaseOrder.customer` đã khai báo optional=false, nên trường hợp null về mặt mapping không hợp lệ; đây là minh họa chung cho một association tùy chọn.

### 18.1. Filter null có thể mang hai ý nghĩa

Một request filter có trường `status = null` có thể nghĩa:

1. **Không lọc theo status**, hoặc
2. **Tìm row có status NULL**.

Hai ý nghĩa khác nhau. Trong example filter, ta chọn ý nghĩa 1. Nếu API cần ý nghĩa 2, phải có trạng thái rõ ràng, ví dụ filter type `UNSPECIFIED / IS_NULL / EQUAL(value)` thay vì nhét tất cả vào `null`.

### 18.2. IN với collection rỗng

Nếu filter có danh sách allowed customer IDs rỗng:

~~~hql
where o.customer.id in :ids
~~~

thì ý nghĩa nghiệp vụ thường là trả **0 hàng**, không phải bỏ filter và hiển thị tất cả đơn hàng. Đừng để case rỗng vô tình bỏ qua authorization constraint.

Có thể xử lý `ids.isEmpty()` trước khi execute hoặc dùng predicate luôn false như `cb.disjunction()` trong Criteria, tùy API.

### 18.3. Giá trị optional và joins

Một LEFT JOIN cộng điều kiện trên bảng bên phải trong WHERE có thể loại các hàng không có association, khiến kết quả gần với inner join.

Ví dụ:

~~~hql
select o
from PurchaseOrder o
left join o.lines l
where l.quantity >= :minimum
~~~

Điều kiện WHERE loại những Order không có line. Nếu cần giữ cả Order không có line, cần định nghĩa logic JOIN/filter khác. Không có ngôn ngữ query nào tự sửa được lỗi semantics này.

## 19. Tenant/authorization filter: không được coi là “optional”

Một search filter do user gửi có thể có status, amount và date tùy chọn. Nhưng tenantId/authorization constraint phải được áp dụng **bắt buộc** theo quyền truy cập, không do client quyết định.

Ví dụ HQL:

~~~hql
select o
from PurchaseOrder o
where o.tenantId = :tenantId
  and o.status = :status
~~~

Với Criteria:

~~~java
predicates.add(
    cb.equal(root.get("tenantId"), authenticatedTenantId));
~~~

Với native SQL:

~~~sql
where o.tenant_id = :tenantId
~~~

Không cung cấp một nhánh `if (tenantId != null)` khiến bộ lọc tenant có thể biến mất khi caller quên truyền hoặc client thao túng request.

### 19.1. Bảo mật không chỉ là SQL injection

Ngay cả parameterized queries vẫn có thể lộ dữ liệu nếu:

- Thiếu predicate tenant.
- Truy vấn JOIN qua association ngoài tenant.
- Count query bỏ lọc quyền.
- Subquery/CTE không áp dụng phạm vi đúng.
- API cho phép sort/filter trên field nhạy cảm.
- Native SQL bỏ qua soft-delete hoặc row-level security policy.

Các ràng buộc an ninh phải được kiểm tra trong **mọi nhánh query**, kể cả content/count, reporting và bulk DML.

### 19.2. Dùng ORM filters hay RLS?

Hibernate filters hoặc database row-level security (RLS) có thể hỗ trợ, nhưng mỗi cơ chế có phạm vi, lifecycle và đường SQL cần kiểm soát. Đừng mặc định một custom native query luôn kế thừa đúng mọi filter ORM, hoặc RLS tự được bật ở mọi connection.

Chính sách an ninh cần có integration tests trên DB thật.

## 20. Portability: JPQL, HQL extension và SQL dialect

“Chạy được với Hibernate” không tự đồng nghĩa “JPA portable”.

### 20.1. JPQL tiêu chuẩn

Ví dụ truy vấn đơn giản:

~~~hql
select o
from PurchaseOrder o
where o.status = :status
~~~

là một cấu trúc JPQL quen thuộc và có tính di động tương đối tốt giữa các JPA providers. Nhưng mapping, column types, collation và generated SQL vẫn có thể khác theo database.

### 20.2. Hibernate HQL extension

Các phiên bản Hibernate 6.x hỗ trợ một số cú pháp nâng cao ngoài JPQL truyền thống, chẳng hạn CTE/recursive CTE, window functions, set operations hoặc các biểu thức khác tùy version.

Dùng extension có thể rất hợp lý nhưng tạo phụ thuộc vào:

- Hibernate ORM version.
- HQL parser/semantics.
- Dialect translation.
- Database capability.

Ví dụ một recursive CTE không chạy được nếu database không hỗ trợ recursion, dù HQL parser hiểu cú pháp.

### 20.3. Native SQL và vendor features

SQL native có thể tận dụng PostgreSQL `DISTINCT ON`, JSONB, partial index, hoặc cách viết locking riêng. Đó là quyết định phụ thuộc database thực sự.

Nếu sản phẩm chỉ chạy PostgreSQL và team chấp nhận điều đó, sử dụng tính năng riêng không sai. Nhưng nên lưu lại yêu cầu phiên bản DB, test integration và giải pháp nâng cấp.

### 20.4. Criteria có đảm bảo portable tuyệt đối không?

Không. JPA Criteria API chuẩn giúp diễn đạt cấu trúc query có tính portable hơn so với các extension riêng, nhưng:

- Một số function trong `cb.function(...)` có thể riêng DB.
- Mapping Hibernate-specific vẫn có thể tác động SQL.
- SQL semantics NULL/timezone/collation khác nhau.
- Native entity types/custom JDBC types có thể phụ thuộc dialect.
- Hibernate Criteria extensions không phải API Jakarta Persistence portable.

**API type-safe không đồng nghĩa SQL behavior portable.**

## 21. Bulk UPDATE/DELETE: một đánh đổi riêng

Đôi khi yêu cầu không phải tìm kiếm, mà là đổi trạng thái hàng loạt:

> Hủy tất cả đơn DRAFT quá 90 ngày.

HQL bulk DML:

~~~java
int updated = em.createQuery("""
    update PurchaseOrder o
    set o.status = :cancelled
    where o.status = :draft
      and o.createdAt < :cutoff
    """)
    .setParameter("cancelled", OrderStatus.CANCELLED)
    .setParameter("draft", OrderStatus.DRAFT)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
~~~

Criteria Update:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaUpdate<PurchaseOrder> update =
    cb.createCriteriaUpdate(PurchaseOrder.class);

Root<PurchaseOrder> root = update.from(PurchaseOrder.class);

update.set("status", OrderStatus.CANCELLED);
update.where(
    cb.equal(root.get("status"), OrderStatus.DRAFT),
    cb.lessThan(root.<Instant>get("createdAt"), cutoff)
);

int affected = em.createQuery(update).executeUpdate();
~~~

Native SQL:

~~~sql
UPDATE purchase_orders
SET status = 'CANCELLED'
WHERE status = 'DRAFT'
  AND created_at < :cutoff;
~~~

Ba cách đều có thể dùng cho bulk operation. Nhưng **không cách nào tự chuyển bulk DML thành lifecycle update từng managed entity**.

### 21.1. Bulk DML bỏ qua một số ORM lifecycle semantics

Với bulk HQL/Criteria/native DML:

- Không tự chạy dirty checking trên từng entity như setter + flush.
- Không mặc định trigger các lifecycle callbacks trên từng entity.
- Có thể không tự tăng/kiểm tra `@Version` như Hibernate-managed entity updates.
- Managed instances đang có trong persistence context có thể stale.
- Có thể bỏ qua cascade operations của object graph.
- Cần xử lý quyền và ràng buộc tenant rõ ràng.

Nếu business rule nằm trong entity methods/callback, bulk DML có thể bỏ qua rule đó. Dùng bulk cho nghiệp vụ phù hợp và có transaction/row-count checks.

### 21.2. Cần kiểm soát persistence context

Sau bulk update, có thể cần `em.clear()` hoặc refresh entity liên quan, tùy phạm vi. Trước bulk DML, có thể cần `em.flush()` để đồng bộ pending changes. Nhưng `clear()` detach **toàn bộ managed entities** của context, có thể làm mất các sửa đổi chưa flush nếu dùng sai thời điểm.

### 21.3. Native SQL đáng dùng khi set-based logic phức tạp

Nếu bulk operation cần nhiều bảng, CTE, output returning hoặc locking behavior riêng DB, native SQL có thể rõ ràng hơn. Tuy nhiên, semantic correctness và transaction isolation mới là trọng tâm, không phải chỉ giảm code Java.

## 22. Chọn DTO hay entity trước khi chọn ngôn ngữ query

Một sai lầm phổ biến là bắt đầu bằng:

> Dùng Criteria hay HQL?

trong khi câu hỏi đầu tiên nên là:

> Màn hình cần **entity managed** hay chỉ cần dữ liệu để đọc?

### 22.1. Khi cần entity managed

Chọn query trả `PurchaseOrder` nếu cần:

- Thực thi domain methods rồi flush.
- Dirty checking.
- Phối hợp aggregate lifecycle.
- Locking trên entity.
- Sử dụng relationship theo transaction.

HQL/Criteria dễ trả entity managed. Native SQL cũng có thể map entity, nhưng phải xử lý schema/result mapping cẩn thận.

### 22.2. Khi cần read-only projection

Nếu trang list chỉ có ID, customer name, status, createdAt và amount, nên cân nhắc DTO projection. Dù dùng HQL/Criteria/native, việc chỉ lấy cột cần thiết có thể giảm:

- JDBC bytes.
- Object allocation.
- Association hydration.
- Lazy loading ngoài ý muốn.
- Serialization object graph.

### 22.3. Trả Entity ra JSON trực tiếp là một quyết định riêng

Nếu controller serialize entity graph, một số lazy getters có thể bị truy cập sau transaction, gây `LazyInitializationException` hoặc N+1 nếu Open Session in View bật. DTO hóa trong transaction giúp kiểm soát dữ liệu API rõ hơn.

## 23. Độ phức tạp query và ngưỡng chuyển cách tiếp cận

Có thể dùng một thang định tính:

<escape>**Mức 1 — Query đơn giản, ổn định**</escape>

~~~hql
select o from PurchaseOrder o
where o.status = :status
~~~

**Ưu tiên:** HQL/JPQL hoặc repository-derived query. Criteria thường dư boilerplate.

<escape>**Mức 2 — Vài filter tùy chọn**</escape>

Status, date range, customer ID, minimum amount. **Ưu tiên:** HQL dynamic fragments có kiểm soát hoặc Criteria. Chọn cách team đọc và test dễ nhất.

<escape>**Mức 3 — Rất nhiều predicate tái sử dụng**</escape>

Tìm kiếm nâng cao, multi-tenant visibility, nhiều nhóm AND/OR, subquery EXISTS. **Ưu tiên:** Criteria/Specifications hoặc query builder tương đương, chia nhỏ theo domain.

<escape>**Mức 4 — Báo cáo tổng hợp phức tạp**</escape>

Grouped aggregates, ranking, top-N, windows, CTE. **Ưu tiên:** so sánh HQL advanced và native SQL; Criteria chuẩn có thể trở nên dài và khó đọc.

<escape>**Mức 5 — Tính năng riêng DB hoặc performance-critical SQL**</escape>

JSONB, full-text, native CTE strategy, specialized indexing/locking hints. **Ưu tiên:** native SQL hoặc Hibernate extension có chủ đích, được kiểm thử trên DB mục tiêu.

Thang này không phải quy tắc tuyệt đối. Một team có reusable Criteria DSL tốt có thể xử lý Mức 4 dễ dàng; một team chuyên SQL có thể viết reporting native ngay từ Mức 2 nếu hệ thống đã theo kiến trúc read model. Cần đánh giá theo công cụ và năng lực vận hành thật.

## 24. Khi nào Criteria trở thành gánh nặng?

Criteria có thể gây khó đọc nếu:

- Một query đơn giản bị trải thành hàng chục dòng Java.
- Helper nhận quá nhiều `Root<?>`, `Join<?,?>` và generic types.
- Kết quả DTO phải dựng thủ công bằng nhiều `cb.construct()` lồng nhau.
- Người viết sử dụng raw types hoặc unchecked casts để “đánh bại” compiler.
- Query động được cấu thành bởi abstraction quá tổng quát, khó tìm SQL semantics.
- Mọi field name vẫn là string nên không có lợi thế static metamodel rõ rệt.
- Debugging chỉ nhìn Java object tree mà không xem SQL cuối.

Dấu hiệu cần thay đổi là **query khó chứng minh đúng** hơn khi viết bằng HQL hoặc SQL.

### 24.1. Đừng xây một “framework truy vấn vạn năng” quá sớm

Một filter builder tổng quát nhận JSON AST tự do từ client có thể cho phép lắp gần như mọi JOIN, function và ORDER BY. Điều đó kéo theo rủi ro bảo mật, query cost không kiểm soát và khả năng lộ dữ liệu.

Chỉ expose những field, operator và join paths có mục đích nghiệp vụ. Dùng whitelist và limits rõ ràng.

### 24.2. Complexity không chỉ là số filter

Có thể có 15 filter nhưng tất cả đều là `AND equals` trên một bảng — Criteria xử lý dễ. Ngược lại, chỉ một yêu cầu “top 1 event per account, including ties” có thể đòi window/rank logic phức tạp.

Hãy phân biệt **số nhánh cấu thành** với **độ phức tạp quan hệ/toán học của query**.

## 25. Khi nào HQL trở thành gánh nặng?

HQL có thể khó bảo trì nếu:

- Cùng một query được copy-paste thành hàng chục biến thể.
- String builder chứa rất nhiều `if/else` nối WHERE/JOIN/ORDER BY.
- Tên parameter được duy trì ở hai nơi và dễ không khớp.
- Các nhóm AND/OR không được đặt ngoặc nhất quán.
- Dynamic join aliases phụ thuộc thứ tự thêm fragment.
- Logic quyền truy cập bị lặp ở nhiều query và dễ bỏ sót.
- Dùng positional parameters khi query thay đổi liên tục.
- Một string HQL dài hàng nghìn ký tự với nhiều vendor extensions trở nên khó đọc hơn SQL.

Khi đó có thể chuyển sang Criteria để composition hoặc tách thành nhiều repository methods/use cases.

### 25.1. Không gắn chặt business logic vào HQL string

Nếu một điều kiện như `mayViewOrder` chứa chính sách quyền phức tạp, nên có helper hoặc service cung cấp predicate/parameter set rõ ràng. Không để các chuỗi SQL/HQL rải khắp controller.

### 25.2. Query ổn định đôi khi tốt hơn query “siêu động”

Nếu chỉ có ba loại tìm kiếm rõ ràng, viết ba query HQL riêng có thể dễ đọc/test hơn một query builder tổng quát chứa hàng chục optional branches.

## 26. Khi nào native SQL trở thành gánh nặng?

Native SQL có thể tốn công khi:

- Schema liên tục đổi tên table/column.
- Ứng dụng cần hỗ trợ nhiều RDBMS.
- Result mapping phức tạp hoặc driver trả type khác kỳ vọng.
- Filter/tenant/soft-delete policies nằm ở ORM layer và phải áp dụng thủ công.
- Entity lifecycle/versioning/cascade cần bảo toàn.
- Query dùng cú pháp vendor-specific nhưng không có integration tests.
- Phải viết SQL cho nhiều dialect và giữ chúng đồng bộ.

Do đó native SQL nên được **cô lập sau một interface/repository adapter** nếu nó là thành phần quan trọng.

Ví dụ:

~~~java
public interface OrderReportPort {
    List<CustomerRevenueRow> topCustomers(
        Instant fromInclusive,
        Instant toExclusive,
        int limit
    );
}
~~~

Một implementation PostgreSQL có thể chứa SQL chuyên biệt, trong khi service chỉ biết contract dữ liệu. Khi đổi database, phạm vi cần chỉnh sửa rõ hơn.

## 27. Test truy vấn động theo tổ hợp, không thử một ví dụ duy nhất

Một Criteria builder với nhiều filter có thể thất bại ở những tổ hợp hiếm. Test nên bao gồm:

| Tình huống | Kết quả cần kiểm tra |
| --- | --- |
| Không có filter optional | Trả các bản ghi được phép xem, không lộ tenant khác |
| Chỉ status | Đúng trạng thái |
| Chỉ minimumTotal | Không có đơn dưới ngưỡng |
| From và to | Khoảng [from, to) đúng, không trùng biên |
| Kết hợp status + amount + date | Tất cả predicate được áp dụng theo AND |
| Một danh sách IDs rỗng | Không vô tình bỏ lọc quyền |
| Customer không tồn tại | Kết quả rỗng, không exception ngoài dự kiến |
| Sort từng mode | Đúng field, hướng, tie-breaker |
| Page 0/page 1 | Không mất/trùng row khi dữ liệu đứng yên |
| Count query | Tổng số **root** đúng, không bị JOIN nhân |
| To-many filter | EXISTS/JOIN không tạo duplicate không mong muốn |
| Input chứa %, _, quote | Đúng semantics LIKE và không injection |
| Null field | WHERE/IS NULL đúng nghiệp vụ |
| Dữ liệu khác tenant | Không xuất hiện trong content **và count** |
| Result mapping native | Kiểu số, enum, timestamp đúng |

### 27.1. Không chỉ assert số hàng

Một test “query trả 5 rows” vẫn có thể cho kết quả sai 5 rows. Kiểm tra IDs, thứ tự, field values, aggregate và quyền truy cập.

### 27.2. Test cả SQL shape khi performance quan trọng

Dùng Hibernate SQL logging/`StatementInspector` hoặc Statistics trong test được cô lập để kiểm tra:

- Không có N+1.
- Không fetch join nhiều to-many ngoài ý muốn.
- Pagination được đẩy xuống SQL khi cần.
- Không có JOIN bất ngờ.
- Số statement trong một use case nằm trong giới hạn hợp lý.

Không snapshot exact SQL alias/whitespace như một contract vĩnh viễn, vì Hibernate version/dialect có thể thay đổi những chi tiết implementation mà semantics vẫn đúng.

### 27.3. Test trên database thật

H2 hoặc database in-memory có thể giúp test nhanh nhưng không bảo đảm cùng query plan, collation, timezone, index, SQL syntax và lock semantics với production.

Nếu native query hoặc HQL extension phụ thuộc PostgreSQL/SQL Server/Oracle, nên chạy integration tests bằng database product/version tương ứng, ví dụ Testcontainers khi phù hợp.

## 28. Refactoring và static metamodel

Một lý do đội ngũ chọn Criteria là muốn IDE/compiler hỗ trợ refactor.

### 28.1. HQL dùng string property path

~~~hql
select o from PurchaseOrder o
where o.totalAmount >= :minimum
~~~

Nếu rename `totalAmount` trong Java, compiler có thể vẫn compile query string, rồi lỗi mới xuất hiện khi parse query trong runtime/integration test.

### 28.2. Criteria với metamodel

~~~java
Path<BigDecimal> total =
    root.get(PurchaseOrder_.totalAmount);
~~~

Khi metamodel được generate lại đúng, rename Java property thường được biểu hiện qua thay đổi generated symbol và lỗi compile tại nơi sử dụng symbol cũ.

### 28.3. Criteria với string path vẫn có điểm yếu tương tự HQL

~~~java
root.get("totalAmount")
~~~

Nên không thể nói Criteria mặc định luôn được compiler phát hiện mọi lỗi property name. Muốn hưởng lợi type safety, cần cấu hình annotation processor và sử dụng metamodel một cách nhất quán.

### 28.4. HQL không nhất thiết khó refactor hơn nếu query ít

Một repository có năm câu HQL ngắn, integration tests đầy đủ và code review rõ ràng có thể ít tốn bảo trì hơn một lớp Criteria abstraction phức tạp. Compile-time validation quan trọng nhưng không phải tiêu chí duy nhất.

## 29. Query plan, caching và số shape động

Query động bằng HQL string hoặc Criteria có thể tạo nhiều **query shapes** — tổ hợp WHERE/JOIN/ORDER BY khác nhau.

Nếu có 12 filter độc lập, về lý thuyết có tới:

\[
2^{12} = 4096
\]

tổ hợp có/không của filter. Không phải tất cả tổ hợp đều được dùng, và database/ORM không nhất thiết tạo đúng một plan cho mỗi tổ hợp. Nhưng điều này cho thấy dynamic query builder có thể tạo nhiều SQL shapes.

### 29.1. Query shape khác với bind values

Cùng một query:

~~~hql
where o.status = :status
~~~

với `PAID` hay `COMPLETED` thường có cùng cấu trúc SQL khác bind value, có thể hưởng lợi từ prepared statement/query plan caching tùy database.

Nếu thay đổi cả JOIN/WHERE/order cho từng tổ hợp, SQL shape có thể khác và làm tăng công parse/plan. Cũng có lợi khi mỗi shape chỉ chứa predicate thực sự cần, giúp optimizer chọn plan phù hợp.

Không kết luận “một SQL shape cho mọi filter luôn nhanh nhất” hoặc “dynamic shape luôn tốt hơn”. Phải đo workload.

### 29.2. Cân bằng độ linh hoạt và số trường hợp hỗ trợ

Một UI có thể chỉ cần 4 mode tìm kiếm được sản phẩm xác định rõ. Thay vì cho client tùy chọn 30 operators, xây một DSL vô hạn, có thể giới hạn các use cases để giảm query shape, complexity và rủi ro.

### 29.3. Batch/filter theo IN

Nếu filter nhận hàng nghìn IDs, câu `IN (:ids)` có thể dẫn đến nhiều bind parameters và giới hạn dialect. Cần chia batch hoặc dùng giải pháp khác khi danh sách lớn; cả Criteria, HQL và native đều phải đối mặt với vấn đề này.

## 30. Các tình huống quyết định thực tế

### Tình huống A — CRUD service lọc theo ID và status

**Ưu tiên:** HQL/JPQL hoặc Spring Data repository query. Criteria có thể quá dài so với yêu cầu.

~~~hql
select o from PurchaseOrder o
where o.id = :id and o.status = :status
~~~

### Tình huống B — Admin search có 10 filter optional

**Ưu tiên:** Criteria/Specifications, nhất là khi filters được tổ hợp và tái sử dụng. HQL string builder vẫn phù hợp nếu số nhánh dễ kiểm soát.

### Tình huống C — Báo cáo revenue theo tháng

**Ưu tiên:** HQL projection nếu group/aggregate đơn giản, hoặc native SQL nếu cần date bucketing/window functions riêng DB. Đừng tải hàng triệu entity rồi group trong Java nếu DB có thể tổng hợp đúng.

### Tình huống D — Lấy chi tiết Order cùng Customer

**Ưu tiên:** HQL `join fetch` to-one hoặc Criteria fetch/EntityGraph thích hợp. Chọn fetch plan dựa trên dữ liệu cần, không dựa vào sở thích API.

### Tình huống E — Tìm Order có ít nhất một line khớp điều kiện động

**Ưu tiên:** HQL EXISTS nếu query ổn định; Criteria Subquery khi cần thêm/bỏ nhiều EXISTS theo filter.

### Tình huống F — JSONB containment trên PostgreSQL

**Ưu tiên:** native SQL hoặc Hibernate function/custom mapping có chủ đích. Cần test index, SQL semantics và khả năng tương thích DB.

### Tình huống G — Chuyển nhiều hàng từ DRAFT sang CANCELLED

**Ưu tiên:** HQL/Criteria bulk DML nếu đơn giản, native SQL khi logic DB-specific. Cần chú ý version, callbacks, tenant và persistence context.

### Tình huống H — Một sản phẩm có thể chạy trên PostgreSQL và Oracle

**Ưu tiên:** JPQL/Criteria chuẩn cho nghiệp vụ thông thường; cô lập các native/vendor-specific reports sau adapter với test trên từng DB. HQL extensions cần được đánh dấu và kiểm thử compatibility.

## 31. Bảng ra quyết định cuối cùng

| Yêu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Query cố định, ngắn, gần entity | HQL/JPQL | Dễ đọc và bảo trì |
| Một vài điều kiện tùy chọn | HQL fragments hoặc Criteria | Cả hai đều được; chọn theo team |
| Nhiều điều kiện tổ hợp và tái dùng | Criteria/Specification | Predicate composition và type-aware API |
| Nhiều phép OR/EXISTS động | Criteria hoặc query builder phù hợp | Cây điều kiện rõ |
| Aggregate đơn giản | HQL projection | Gọn, diễn đạt ở entity level |
| Report có window/CTE phức tạp | HQL advanced hoặc native SQL | So sánh sự rõ ràng và SQL thực tế |
| Tối ưu đặc thù database | Native SQL | Kiểm soát cú pháp/feature DB |
| Cần entity managed để cập nhật | HQL/Criteria entity query | ORM lifecycle tự nhiên |
| Read-only DTO API | Cả ba | Ưu tiên lấy ít cột và mapping rõ |
| Thay đổi sort động | Criteria hoặc whitelist HQL/SQL | Không nối raw client strings |
| Đòi portability giữa JPA providers | JPQL hoặc JPA Criteria chuẩn | Hạn chế vendor extensions |
| Chỉ hỗ trợ một DB cụ thể | Có thể dùng native SQL | Nếu giúp query rõ/nhanh và được test |
| Pagination to-many | Hai bước, batch/projection | Ngôn ngữ query không tự giải quyết |
| Vấn đề N+1 | Đổi fetch plan | Không phải chỉ đổi HQL sang Criteria |
| Bulk cập nhật lớn | Bulk HQL/Criteria/native | Quyết định theo logic và transaction semantics |

**Khuyến nghị thực hành:** chọn HQL làm mặc định cho query ổn định; chọn Criteria khi **độ động tạo lợi ích thực sự về composition**; chọn native SQL khi **cần diễn đạt/kiểm soát SQL trực tiếp** và chấp nhận nghĩa vụ kiểm thử theo dialect. Mọi lựa chọn đều cần quan sát SQL và bảo vệ business invariants.

## 32. Checklist trước khi merge một truy vấn mới

- [ ] Yêu cầu nghiệp vụ và kết quả mong muốn được mô tả rõ.
- [ ] Chọn entity result hay DTO projection có chủ đích.
- [ ] Chọn HQL/Criteria/native dựa trên mức động và độ phức tạp.
- [ ] Không nối trực tiếp dữ liệu người dùng vào HQL/SQL.
- [ ] ORDER BY chỉ dùng những identifier/field trong whitelist.
- [ ] Các filter tenant/authorization không bị bỏ qua.
- [ ] Rõ semantics của null, list rỗng, LIKE và timezone.
- [ ] Các filter AND/OR và EXISTS được kiểm thử.
- [ ] Pagination có sort ổn định và count đúng.
- [ ] Tránh fetch join collection khi phân trang trực tiếp.
- [ ] Không tạo N+1 hoặc Cartesian product ngoài ý muốn.
- [ ] Query bulk không vô tình bỏ qua version/lifecycle rules.
- [ ] SQL sinh ra và execution plan đã được xem trên DB mục tiêu.
- [ ] Native/HQL extensions được ghi nhận là dependency có chủ đích.
- [ ] Có integration tests cho filter combinations và edge cases.
- [ ] Có metrics hoặc giới hạn query phù hợp với tải production.

## 33. Bài tập thực hành

### Bài 1 — Chọn công cụ

Một service chỉ cần tìm Order theo ID và status. Nên dùng HQL hay Criteria? Hãy giải thích chi phí boilerplate và khả năng bảo trì.

### Bài 2 — Filter động

Màn hình cho phép lọc status, customerId, minimumTotal và khoảng thời gian. Hãy viết Criteria query chỉ thêm predicate khi người dùng cung cấp filter tương ứng.

### Bài 3 — HQL string builder an toàn

Một developer viết:

~~~java
hql.append(" and c.name = '" + input + "'");
~~~

Hãy chỉ ra rủi ro và sửa thành named parameter. Dynamic ORDER BY cần xử lý thế nào?

### Bài 4 — Static metamodel

So sánh:

~~~java
root.get("totalAmount")
~~~

với:

~~~java
root.get(PurchaseOrder_.totalAmount)
~~~

Cách nào có khả năng giúp compiler phát hiện lỗi refactor field khi annotation processor hoạt động đúng?

### Bài 5 — Count và to-many JOIN

Một Order có 5 OrderLine. Count query JOIN lines rồi dùng `count(order)`. Vì sao tổng số Order có thể sai? Hãy đề xuất `countDistinct` hoặc `EXISTS`.

### Bài 6 — Criteria reusable predicates

Vì sao không nên lấy một Predicate tạo với Root của query list rồi gắn thẳng sang count query? Nên tái sử dụng điều gì?

### Bài 7 — Window function

Một báo cáo cần top 3 Order theo doanh số cho mỗi Customer. So sánh native SQL với `ROW_NUMBER() OVER(PARTITION BY ...)` và HQL nâng cao. Khi nào Criteria chuẩn có thể gây khó đọc?

### Bài 8 — SQL performance

Hai implementation HQL và Criteria sinh cùng SQL, nhưng một reviewer khẳng định Criteria nhanh hơn. Bạn sẽ kiểm tra gì để xác minh? Vì sao chỉ đổi API Java không đủ?

### Bài 9 — LIKE và wildcard

Một người dùng tìm tên có ký tự `100%`. Vì sao parameter binding chưa đủ để coi dấu `%` là literal? Hãy đề xuất escape strategy và test trên DB thật.

### Bài 10 — IN rỗng

Một API nhận danh sách customer IDs mà user được xem. Nếu danh sách rỗng, điều gì sai nếu query builder bỏ qua filter `IN :ids`? Cách xử lý an toàn?

### Bài 11 — Pagination

Một Criteria query fetch join `Order.lines` rồi áp dụng `setMaxResults(20)`. Vì sao có thể xảy ra in-memory pagination? Hãy mô tả two-step pagination.

### Bài 12 — Multi-DB portability

Một ứng dụng tuyên bố hỗ trợ PostgreSQL và SQL Server nhưng query dùng function riêng của PostgreSQL. Bạn sẽ thay đổi code/test hoặc định nghĩa phạm vi hỗ trợ như thế nào?

### Bài 13 — Bulk DML

Một bulk HQL UPDATE sửa status của nhiều Order có `@Version`. Có thể xảy ra điều gì nếu không thiết kế version update và refresh persistence context?

### Bài 14 — Quyết định kiến trúc

Một nhóm đã có 40 HQL query ngắn nhưng muốn chuyển toàn bộ sang Criteria “vì type-safe”. Hãy lập bảng đánh giá lợi ích, chi phí và điều kiện cần trước khi quyết định migration.

### Bài 15 — Thiết kế một query contract

Với chức năng tìm Order nhiều filter, hãy viết test matrix bao gồm không filter, từng filter riêng, phối hợp AND/OR, time boundaries, null, tenant isolation, pagination, sort và số statement.

### Gợi ý trả lời

- **Bài 1:** HQL/JPQL thường ngắn và rõ nhất khi query ổn định.
- **Bài 2:** Dựng `List<Predicate>`, thêm khi filter != null, dùng `cb.and(...)`.
- **Bài 3:** Không nối raw input; bind `:name`. Sort dùng enum/whitelist.
- **Bài 4:** Static metamodel mang property types vào Java compile time khi được generate.
- **Bài 5:** JOIN nhân rows theo số lines; countDistinct hoặc EXISTS bảo vệ root cardinality.
- **Bài 6:** Predicate gắn với Root/query tree cũ; tái sử dụng hàm builder để tạo Predicate mới cho count root.
- **Bài 7:** SQL window ngắn và rõ khi DB hỗ trợ; HQL advanced có thể thích hợp nếu dialect chuyển tốt.
- **Bài 8:** So sánh SQL, binds, indexes, execution plans, row counts, caching và workload.
- **Bài 9:** `%` vẫn là wildcard của LIKE; escape đặc biệt và dùng escape character phù hợp.
- **Bài 10:** Bỏ filter có thể lộ tất cả Orders; cần trả empty result hoặc predicate false.
- **Bài 11:** JOIN rows có thể cắt collection, Hibernate phải paginate memory; page IDs trước.
- **Bài 12:** Cô lập function theo dialect hoặc viết lại portable query, test cả hai DB.
- **Bài 13:** Bulk DML có thể bỏ qua ORM version/callback và làm managed entities stale.
- **Bài 14:** Migration chỉ đáng làm khi lợi ích composition/metamodel/refactor vượt chi phí và rủi ro.
- **Bài 15:** Test đúng tập IDs/thứ tự và authorization, không chỉ test số hàng.

---

## Kết luận

**HQL, Criteria và SQL là ba cách diễn đạt yêu cầu truy vấn với những đánh đổi khác nhau, không phải ba cấp độ chất lượng từ thấp đến cao.** HQL có ưu thế về tính trực quan với truy vấn ổn định; Criteria mạnh ở điều kiện động và composition; native SQL mạnh khi cần kiểm soát tính năng và kế hoạch SQL chuyên biệt.

Ở cả ba cách, điều quan trọng nhất vẫn là **ngữ nghĩa nghiệp vụ đúng, parameters được bind an toàn, phân trang và quan hệ được xử lý chính xác, quyền truy cập không bị bỏ lọc, và SQL thực sự chạy trên database được đo/kiểm thử**. Chọn công cụ nào giúp nhóm phát triển đạt các yêu cầu đó với độ phức tạp tổng thể thấp nhất, thay vì chọn theo khẩu hiệu “Criteria luôn tốt hơn HQL” hay “SQL native luôn nhanh hơn Hibernate”.
