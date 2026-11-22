# Tối ưu join, DISTINCT, truy vấn con và bộ lọc lớn

Hiệu năng truy vấn Spring Data JPA không chỉ phụ thuộc vào số dòng trong bảng. Một truy vấn có thể chậm vì JOIN làm nhân số dòng, DISTINCT phải loại trùng trên tập dữ liệu lớn, subquery được thực thi với kế hoạch không phù hợp, hoặc danh sách tham số IN quá dài.

Muốn tối ưu đúng, cần hiểu **cardinality** của quan hệ, số dòng thực sự được database xử lý, dữ liệu cần trả về và execution plan. Không nên thêm DISTINCT hoặc đổi JOIN thành subquery theo cảm tính. Hãy xác định kết quả mong muốn trước, viết truy vấn đúng ngữ nghĩa, sau đó đo SQL và kế hoạch thực thi trên database gần với production.

Bài này tập trung vào bốn nhóm kỹ thuật: JOIN, DISTINCT, subquery và bộ lọc lớn. Các ví dụ dùng JPQL và Spring Data JPA; phần nào phụ thuộc database sẽ được ghi rõ.

**Điều kiện của ví dụ:** Java 17+, Spring Boot 3.x, Spring Data JPA, Jakarta Persistence và Hibernate. Ứng dụng cần **spring-boot-starter-data-jpa**, JDBC driver, DataSource và schema phù hợp. Các class bên dưới là những phần của ứng dụng Spring Boot, không phải chương trình độc lập chạy chỉ bằng javac.

## 1. Bắt đầu từ cardinality của quan hệ

JOIN kết hợp dữ liệu từ nhiều bảng. Điều cần hiểu trước tiên là quan hệ giữa hai phía có thể là one-to-one, many-to-one, one-to-many hoặc many-to-many.

Ví dụ một đơn hàng có nhiều dòng hàng:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderItem> items = new ArrayList<>();

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public List<OrderItem> getItems() {
        return items;
    }
}
~~~

~~~java
@Entity
@Table(name = "order_items")
public class OrderItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;

    private String sku;

    private Integer quantity;

    @Enumerated(EnumType.STRING)
    private ItemStatus status;
}
~~~

Nếu một đơn hàng có ba dòng hàng, câu query join từ PurchaseOrder sang items có thể tạo ba dòng SQL cho cùng một đơn hàng:

~~~sql
SELECT o.id, i.id, i.sku
FROM purchase_orders o
JOIN order_items i ON i.order_id = o.id;
~~~

| order_id | item_id | sku |
|---:|---:|---|
| 10 | 101 | KB-01 |
| 10 | 102 | MS-02 |
| 10 | 103 | USB-03 |
| 11 | 104 | HD-04 |

Entity cha có thể bị lặp trong tập kết quả SQL vì mỗi dòng con tạo một tổ hợp riêng. Đây là nguồn gốc của nhiều lỗi đếm sai, phân trang sai và việc thêm DISTINCT không đúng chỗ.

Trước khi viết JOIN, hãy trả lời:

- Kết quả cần một dòng cho mỗi entity cha hay một dòng cho mỗi cặp cha-con?
- Có cần dữ liệu của entity con trong response không, hay chỉ cần biết có ít nhất một con phù hợp?
- Một entity cha có thể có bao nhiêu entity con?
- Điều kiện lọc nằm ở bảng cha, bảng con hay cả hai?

## 2. INNER JOIN và LEFT JOIN có ngữ nghĩa khác nhau

**INNER JOIN** chỉ trả về các hàng có quan hệ khớp ở cả hai phía. **LEFT JOIN** giữ lại mọi hàng phía trái, kể cả khi không có hàng phía phải phù hợp; các cột phía phải khi đó là NULL.

JPQL ví dụ:

~~~java
@Query("""
    select p
    from PurchaseOrder p
    join p.items i
    where i.status = :status
    """)
List<PurchaseOrder> findOrdersWithItemStatus(
    @Param("status") ItemStatus status
);
~~~

Đơn hàng không có item phù hợp sẽ bị loại. Nếu mục tiêu là tìm đơn hàng có ít nhất một item đạt trạng thái, truy vấn này có thể diễn đạt đúng ý, nhưng JOIN có thể tạo nhiều dòng cho một đơn hàng.

LEFT JOIN:

~~~java
@Query("""
    select p
    from PurchaseOrder p
    left join p.items i
    """)
List<PurchaseOrder> findOrdersIncludingWithoutItems();
~~~

Truy vấn này giữ cả đơn hàng không có item. Tuy nhiên, nếu đặt điều kiện phía phải trong WHERE:

~~~java
select p
from PurchaseOrder p
left join p.items i
where i.status = :status
~~~

các hàng không có item có i.status = NULL và bị WHERE loại. Kết quả lúc này có hiệu quả tương tự INNER JOIN đối với điều kiện đó.

Nếu muốn giữ tất cả đơn hàng và chỉ ghép các item có status cụ thể, đặt điều kiện vào ON:

~~~java
@Query("""
    select p
    from PurchaseOrder p
    left join p.items i on i.status = :status
    """)
List<PurchaseOrder> findOrdersAndMatchingItems(
    @Param("status") ItemStatus status
);
~~~

Điều kiện ON giữ ngữ nghĩa LEFT JOIN. Lưu ý query vẫn có thể trả một đơn hàng nhiều lần nếu nhiều item khớp.

## 3. JOIN làm nhân dòng và tác động tới kết quả

Khi join collection, một entity cha có thể xuất hiện nhiều lần ở mức SQL. Điều này ảnh hưởng tới:

- Số phần tử trả về và việc loại trùng.
- COUNT và tổng hợp.
- LIMIT/OFFSET và phân trang.
- Dung lượng dữ liệu truyền từ database.
- Chi phí sort, hash và duplicate elimination.

Ví dụ:

~~~java
@Query("""
    select p
    from PurchaseOrder p
    join p.items i
    where i.sku like :prefix
    """)
List<PurchaseOrder> findOrdersByItemSkuPrefix(
    @Param("prefix") String prefix
);
~~~

Một đơn hàng có hai item cùng khớp prefix có thể xuất hiện hai lần trong kết quả logic của truy vấn. Nếu mục tiêu là danh sách đơn hàng duy nhất, hãy cân nhắc **select distinct p** hoặc đổi truy vấn thành EXISTS nếu không cần dữ liệu item.

Không nên mặc định mọi JOIN đều gây nhân dòng. JOIN từ many-to-one hoặc one-to-one thường không nhân một hàng cha thành nhiều hàng con nếu ràng buộc dữ liệu đúng. JOIN từ one-to-many và many-to-many có khả năng nhân dòng theo số phần tử liên quan.

## 4. DISTINCT trong JPQL và SQL

**DISTINCT** yêu cầu kết quả loại bỏ các giá trị trùng theo tập biểu thức được SELECT. Trong JPQL, nó có thể dùng với entity hoặc projection:

~~~java
@Query("""
    select distinct p
    from PurchaseOrder p
    join p.items i
    where i.status = :status
    """)
List<PurchaseOrder> findDistinctOrdersByItemStatus(
    @Param("status") ItemStatus status
);
~~~

Mục tiêu ở đây là danh sách entity PurchaseOrder duy nhất, dù nhiều item của cùng đơn hàng cùng khớp điều kiện.

DISTINCT không có nghĩa “loại trùng theo bất kỳ field nào bạn muốn”. Nếu SELECT nhiều biểu thức scalar, tính duy nhất áp dụng cho tổ hợp giá trị được chọn:

~~~java
select distinct p.status, i.sku
from PurchaseOrder p
join p.items i
~~~

Hai dòng chỉ bị xem là trùng nếu cả status và sku đều trùng.

### DISTINCT có chi phí

Database có thể phải dùng sort hoặc hash để loại trùng. Chi phí tăng theo số dòng đầu vào và kích thước các cột cần so sánh. Vì vậy:

- Đừng thêm DISTINCT chỉ để che một JOIN không cần thiết.
- Chỉ SELECT các cột thực sự cần.
- Kiểm tra execution plan để biết database dùng bước sort/hash nào.
- Nếu chỉ cần kiểm tra tồn tại, cân nhắc EXISTS thay vì JOIN rồi DISTINCT.

Với Hibernate 6, các entity root trùng lặp do collection fetch join được loại khỏi kết quả entity ở một số trường hợp theo hành vi của provider. Tuy vậy, **select distinct** vẫn có ý nghĩa JPQL rõ ràng và có thể ảnh hưởng SQL được sinh. Không dựa vào một hành vi provider/version cụ thể thay cho việc hiểu ngữ nghĩa query; hãy kiểm tra SQL thực tế.

## 5. COUNT(DISTINCT ...) để đếm entity duy nhất

Nếu JOIN collection rồi đếm entity cha, **count(p)** có thể đếm số dòng join thay vì số đơn hàng duy nhất, tùy cấu trúc truy vấn và cách provider dịch.

Ví dụ cần đếm số đơn hàng có item đang ACTIVE:

~~~java
@Query("""
    select count(distinct p.id)
    from PurchaseOrder p
    join p.items i
    where i.status = :status
    """)
long countDistinctOrdersByItemStatus(
    @Param("status") ItemStatus status
);
~~~

**count(distinct p.id)** đếm ID đơn hàng duy nhất. Nếu mục tiêu thực sự là đếm item thì dùng count(i.id), còn đếm cặp đơn hàng-item thì cần xác định khóa/cấu trúc phù hợp.

Không thay mọi COUNT bằng COUNT DISTINCT một cách máy móc. DISTINCT có thể làm query đắt hơn; chỉ dùng khi cardinality cho thấy một entity có thể xuất hiện nhiều lần và yêu cầu nghiệp vụ là đếm entity duy nhất.

Với truy vấn Page, count query phải phản ánh cùng điều kiện logic với content query:

~~~java
@Query(
    value = """
        select distinct p
        from PurchaseOrder p
        join p.items i
        where i.status = :status
        """,
    countQuery = """
        select count(distinct p.id)
        from PurchaseOrder p
        join p.items i
        where i.status = :status
        """
)
Page<PurchaseOrder> pageOrdersByItemStatus(
    @Param("status") ItemStatus status,
    Pageable pageable
);
~~~

Nếu query có GROUP BY, count query phải đếm số nhóm được trả về, không phải tổng số hàng nguồn. Với query native hoặc cấu trúc phức tạp, khai báo countQuery riêng và kiểm thử trên database đích.

## 6. EXISTS: chỉ cần biết có bản ghi liên quan

Nếu use case chỉ cần lấy đơn hàng có ít nhất một item phù hợp, không cần dữ liệu item trong kết quả, **EXISTS** thường diễn đạt đúng ý hơn JOIN + DISTINCT.

~~~java
@Query("""
    select p
    from PurchaseOrder p
    where exists (
        select i.id
        from OrderItem i
        where i.order = p
          and i.status = :status
    )
    """)
List<PurchaseOrder> findOrdersHavingItemStatus(
    @Param("status") ItemStatus status
);
~~~

Subquery liên kết với truy vấn ngoài qua **i.order = p**. Đây là correlated subquery: điều kiện bên trong tham chiếu entity p của truy vấn ngoài.

Database có thể tối ưu EXISTS như semi-join và dừng tìm kiếm khi đã tìm thấy một hàng phù hợp, tùy optimizer và index. Không có bảo đảm EXISTS luôn nhanh hơn JOIN trên mọi database; lợi ích quan trọng là ngữ nghĩa “có ít nhất một” được thể hiện rõ và tránh tạo các bản sao entity cha ở kết quả.

Một index trên khóa ngoại và cột lọc, ví dụ **order_items(order_id, status)**, có thể hỗ trợ tìm item phù hợp. Thứ tự cột index cần dựa trên các query thực tế, selectivity và execution plan.

## 7. NOT EXISTS để tìm entity không có bản ghi liên quan

Để tìm đơn hàng không có item ở trạng thái CANCELLED:

~~~java
@Query("""
    select p
    from PurchaseOrder p
    where not exists (
        select i.id
        from OrderItem i
        where i.order = p
          and i.status = :status
    )
    """)
List<PurchaseOrder> findOrdersWithoutItemStatus(
    @Param("status") ItemStatus status
);
~~~

NOT EXISTS thường rõ ràng hơn LEFT JOIN ... IS NULL khi cần diễn đạt điều kiện không tồn tại bản ghi liên quan. Nó cũng tránh một số lỗi do đặt nhầm điều kiện ở ON hoặc WHERE.

Cần phân biệt:

- Không có item nào.
- Có item nhưng không có item thuộc trạng thái cụ thể.
- Có item có status NULL.

Đây là các điều kiện nghiệp vụ khác nhau. Hãy viết predicate đúng với yêu cầu và kiểm thử cả trường hợp collection rỗng.

## 8. Subquery với IN và giá trị tổng hợp

JPQL hỗ trợ subquery trong WHERE và HAVING. Ví dụ tìm đơn hàng có tổng tiền lớn hơn trung bình:

~~~java
@Query("""
    select p
    from PurchaseOrder p
    where p.totalAmount > (
        select avg(p2.totalAmount)
        from PurchaseOrder p2
    )
    """)
List<PurchaseOrder> findOrdersAboveAverageAmount();
~~~

Subquery không tương quan ở ví dụ này: nó tính giá trị trung bình trên tập đơn hàng, rồi query ngoài so sánh từng đơn với giá trị đó.

Ví dụ dùng IN với subquery:

~~~java
@Query("""
    select p
    from PurchaseOrder p
    where p.customer.id in (
        select c.id
        from Customer c
        where c.active = true
    )
    """)
List<PurchaseOrder> findOrdersOfActiveCustomers();
~~~

Trong trường hợp này, có thể viết bằng JOIN tới customer. Lựa chọn phụ thuộc việc cần dữ liệu Customer trong kết quả hay chỉ cần lọc theo điều kiện tồn tại.

JPQL chuẩn cho phép subquery trong WHERE và HAVING; không hỗ trợ subquery tùy ý trong FROM như một derived table theo SQL. Nếu cần CTE, window function hoặc derived table phức tạp, cân nhắc native query hoặc tính năng riêng của provider và ghi nhận mức phụ thuộc database.

## 9. Chọn JOIN, EXISTS hay IN như thế nào?

| Nhu cầu | Cách thường dễ diễn đạt |
|---|---|
| Cần lấy field của cả hai entity | JOIN |
| Cần entity cha và dữ liệu con để đọc | JOIN/FETCH JOIN hoặc DTO join tùy use case |
| Chỉ cần biết có ít nhất một entity con | EXISTS |
| Cần biết không có entity con phù hợp | NOT EXISTS |
| So sánh với một tập giá trị từ subquery | IN (subquery) |
| Cần đếm entity cha duy nhất sau join collection | COUNT(DISTINCT parent.id) |
| Cần kết quả tổng hợp theo tổ hợp field | GROUP BY, aggregate và HAVING |

Không có quy tắc “EXISTS luôn nhanh hơn JOIN” hoặc “IN luôn chậm hơn EXISTS”. Optimizer có thể biến đổi các dạng truy vấn tương đương thành cùng một kế hoạch. Hãy ưu tiên ngữ nghĩa rõ ràng, sau đó đo trên dữ liệu thật.

## 10. Bộ lọc IN với danh sách ID nhỏ và vừa

Spring Data JPA hỗ trợ collection parameter:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    List<Product> findByIdIn(Collection<Long> ids);
}
~~~

Hoặc JPQL:

~~~java
@Query("""
    select p
    from Product p
    where p.id in :ids
    """)
List<Product> findAllByIds(
    @Param("ids") Collection<Long> ids
);
~~~

Đây là cách thuận tiện khi danh sách có kích thước vừa phải. Framework/provider bind các giá trị dưới dạng parameter thay vì ghép chuỗi SQL.

Không làm:

~~~java
String sql = "select * from products where id in (" +
    ids.stream().map(String::valueOf).collect(Collectors.joining(",")) +
    ")";
~~~

Ghép input vào SQL có nguy cơ injection, lỗi escaping và làm câu query khó quản lý. Dùng parameter binding cho giá trị.

### Xử lý danh sách rỗng

Không dựa vào việc mọi provider/database đều xử lý IN với danh sách rỗng giống nhau. Hãy quyết định semantics ở service:

- Nếu danh sách rỗng nghĩa là “không có ID nào được chọn”, trả danh sách rỗng ngay.
- Nếu danh sách rỗng nghĩa là “không áp dụng bộ lọc ID”, bỏ predicate IN khỏi query.
- Nếu API không cho phép danh sách rỗng, trả validation error phù hợp.

Ví dụ:

~~~java
public List<Product> findSelected(Collection<Long> ids) {
    if (ids == null || ids.isEmpty()) {
        return List.of();
    }

    return productRepository.findByIdIn(ids);
}
~~~

Nếu ids có thể chứa null, hãy loại bỏ null hoặc xử lý trường hợp NULL thành predicate riêng. SQL IN với NULL tuân theo three-valued logic; nó không tương đương với việc so sánh bằng một giá trị thông thường.

## 11. Danh sách IN rất lớn gây ra vấn đề gì?

Một danh sách có vài chục ID thường đơn giản. Nhưng danh sách có hàng nghìn hoặc hàng chục nghìn ID có thể tạo ra các vấn đề:

- Nhiều bind parameter, có thể chạm giới hạn của database hoặc driver.
- SQL dài, tốn chi phí parse và chuẩn bị statement.
- Optimizer khó ước lượng cardinality của danh sách.
- Plan cache có thể kém hiệu quả nếu số lượng placeholder thay đổi liên tục.
- Dữ liệu lớn phải truyền từ ứng dụng sang database.
- Kết quả lớn tiếp tục tiêu tốn nhiều bộ nhớ và thời gian mapping entity.

Giới hạn bind parameter khác nhau theo database, phiên bản, driver và cách Hibernate tạo SQL. Không có một con số an toàn chung cho mọi môi trường. Hãy kiểm tra tài liệu engine/driver đang dùng và đo với kích thước dữ liệu thực tế.

Trước khi tối ưu, hỏi xem có thể thay danh sách ID bằng điều kiện nghiệp vụ đơn giản hơn không, chẳng hạn khoảng ngày, trạng thái, tenant hoặc một quan hệ đã tồn tại trong database.

## 12. Chia danh sách lớn thành các batch

Nếu danh sách ID lớn nhưng vẫn cần truyền từ ứng dụng, có thể chia thành nhiều nhóm nhỏ:

~~~java
public List<Product> findInBatches(
        Collection<Long> ids,
        int batchSize) {

    if (ids == null || ids.isEmpty()) {
        return List.of();
    }

    List<Long> values = ids.stream()
        .filter(Objects::nonNull)
        .distinct()
        .toList();

    List<Product> result = new ArrayList<>();

    for (int start = 0; start < values.size(); start += batchSize) {
        int end = Math.min(start + batchSize, values.size());
        List<Long> batch = values.subList(start, end);

        result.addAll(productRepository.findByIdIn(batch));
    }

    return result;
}
~~~

batchSize phải được chọn theo giới hạn parameter, kích thước query, latency và khả năng database. Không mặc định 500 hay 1000 luôn là tối ưu.

Batching có các đánh đổi:

- Tạo nhiều round-trip thay vì một query.
- Có thể giảm kích thước mỗi câu SQL và số parameter.
- Thứ tự tổng thể có thể khác thứ tự danh sách ID đầu vào.
- Cần loại trùng nếu một ID xuất hiện ở nhiều batch.
- Kết quả kết hợp có thể chiếm nhiều bộ nhớ.

Nếu cần giữ thứ tự đầu vào, hãy xây dựng map theo ID rồi sắp xếp lại theo danh sách ban đầu. Nếu cần phân trang toàn cục, không thể đơn giản phân trang từng batch rồi ghép lại mà vẫn bảo đảm thứ tự và tổng số đúng; cần thiết kế lại truy vấn hoặc dùng staging table.

## 13. Dùng bảng tạm hoặc staging table cho bộ lọc rất lớn

Khi danh sách đầu vào có hàng chục nghìn hoặc nhiều hơn, truyền tất cả ID dưới dạng bind parameter có thể không còn phù hợp.

Một chiến lược là đưa ID vào bảng tạm hoặc staging table, sau đó JOIN:

~~~sql
SELECT p.id, p.name, p.price
FROM products p
JOIN request_product_ids r
  ON r.product_id = p.id
WHERE r.request_token = ?;
~~~

Quy trình tổng quát:

1. Tạo hoặc dùng một staging table có cột request_token và product_id.
2. Batch insert các ID cùng một request token.
3. Chạy query JOIN staging table với products.
4. Xóa dữ liệu staging sau khi hoàn tất hoặc để job cleanup theo chính sách.
5. Bảo đảm dữ liệu của các request không trộn lẫn.

Bảng tạm theo session/connection cần được tạo, nạp và truy vấn trên cùng connection phù hợp. Connection pool có thể trả connection về pool sau transaction; không giả định bảng tạm còn tồn tại hoặc được nhìn thấy từ connection khác.

Staging table lâu dài với request token dễ quản lý hơn cho tác vụ lớn hoặc bất đồng bộ, nhưng cần index, cleanup, giới hạn thời gian lưu và cách xử lý request lỗi.

## 14. Cơ chế danh sách lớn đặc thù theo database

Một số database có cách truyền tập giá trị hiệu quả hơn nhiều placeholder:

- **PostgreSQL**: có thể dùng array parameter và toán tử phù hợp, ví dụ **= ANY(...)**, hoặc **unnest()** để biến array thành tập dòng. Cách bind array phụ thuộc JDBC driver và native query.
- **SQL Server**: table-valued parameter cho phép truyền một tập hàng theo kiểu bảng đã định nghĩa.
- **Oracle**: có thể dùng SQL collection type, global temporary table hoặc staging table; cách bind collection phụ thuộc JDBC API và cấu hình.
- **MySQL**: có thể dùng temporary table hoặc staging table rồi JOIN; không có cùng cơ chế table-valued parameter như SQL Server.

Đây là các kỹ thuật database-specific, không phải JPQL portable. Đặt chúng sau một repository/service abstraction để phần còn lại của ứng dụng không phụ thuộc trực tiếp vào cú pháp riêng.

Nếu ứng dụng hỗ trợ nhiều database, cung cấp implementation theo từng engine hoặc giữ một phương án portable với batching cho tập vừa phải.

## 15. Bộ lọc lớn với nhiều điều kiện động

Một màn hình tìm kiếm có thể nhận nhiều filter: trạng thái, danh sách customer ID, khoảng ngày và từ khóa. Tránh nối chuỗi SQL thủ công. Có thể dùng Specification để thêm predicate theo điều kiện thực sự được cung cấp.

Ví dụ:

~~~java
public static Specification<PurchaseOrder> hasStatus(
        OrderStatus status) {
    return (root, query, cb) ->
        status == null ? null : cb.equal(root.get("status"), status);
}

public static Specification<PurchaseOrder> createdFrom(
        Instant from) {
    return (root, query, cb) ->
        from == null ? null : cb.greaterThanOrEqualTo(
            root.get("createdAt"), from);
}
~~~

Kết hợp:

~~~java
Specification<PurchaseOrder> spec =
    Specification.where(hasStatus(status))
        .and(createdFrom(from));

Page<PurchaseOrder> page =
    repository.findAll(spec, pageable);
~~~

Với filter danh sách ID, chỉ thêm predicate IN khi danh sách có nội dung và đã được xác thực. Nếu danh sách quá lớn, chuyển sang batching hoặc staging strategy đã chọn thay vì tạo một predicate khổng lồ.

Specification giúp xây dựng WHERE động, nhưng không tự giải quyết mọi vấn đề hiệu năng. JOIN collection trong Specification vẫn có thể nhân dòng, ảnh hưởng DISTINCT, count query và pagination.

## 16. Index cho JOIN, EXISTS và bộ lọc lớn

Index cần dựa trên điều kiện lọc, cột join, thứ tự sắp xếp và selectivity. Ví dụ truy vấn tìm item theo order_id và status:

~~~sql
SELECT i.id
FROM order_items i
WHERE i.order_id = ?
  AND i.status = ?;
~~~

Một composite index như:

~~~sql
CREATE INDEX idx_order_items_order_status
ON order_items(order_id, status);
~~~

có thể hỗ trợ truy vấn trên. Nhưng thứ tự cột tốt nhất phụ thuộc các query khác, phân bố dữ liệu, selectivity và khả năng index của database.

Các hướng suy nghĩ:

- Index khóa ngoại thường hữu ích cho JOIN và EXISTS.
- Composite index có thể hỗ trợ nhiều điều kiện equality kết hợp.
- Cột sort có thể được đưa vào index nếu query thường xuyên lọc và sắp xếp theo cùng một pattern.
- Index quá nhiều làm tăng chi phí INSERT/UPDATE/DELETE và dung lượng.
- Bọc cột bằng hàm như LOWER(column) có thể làm index thông thường khó được dùng, trừ khi database có functional index hoặc collation phù hợp.
- Không tạo index chỉ vì một cột xuất hiện trong WHERE; kiểm tra workload và execution plan.

Với bộ lọc IN lớn, index trên khóa chính thường hỗ trợ lookup từng ID, nhưng chi phí truyền danh sách và cardinality estimation vẫn có thể chi phối thời gian tổng thể.

## 17. Đọc execution plan thay vì đoán

Dùng công cụ của database để xem optimizer dự định thực hiện query như thế nào:

- PostgreSQL: **EXPLAIN** và **EXPLAIN (ANALYZE, BUFFERS)**.
- MySQL: **EXPLAIN** hoặc **EXPLAIN ANALYZE** tùy phiên bản.
- SQL Server: actual execution plan và thống kê IO/time.
- Oracle: execution plan và runtime statistics theo công cụ phù hợp.

**EXPLAIN ANALYZE** có thể thực thi query thật, nên chỉ chạy trên môi trường và dữ liệu phù hợp. Với query ghi, phải đặc biệt cẩn thận về tác động.

Các dấu hiệu cần quan sát:

- Full table scan trên bảng lớn khi kỳ vọng index lookup.
- Nested loop lặp quá nhiều lần vì cardinality lớn.
- Hash join hoặc sort tiêu tốn bộ nhớ.
- DISTINCT tạo bước sort/hash lớn.
- Estimate rows khác xa actual rows.
- Count query chậm hơn content query.
- Số dòng trung gian sau JOIN lớn hơn nhiều so với số entity cuối cùng.

Đo cả thời gian, số dòng đọc, số dòng trả về và số round-trip. Một query trả 20 entity vẫn có thể xử lý hàng triệu dòng trung gian.

## 18. JOIN FETCH, DTO và phân trang

JOIN FETCH giúp tải association cùng query, nhưng fetch collection làm nhân dòng SQL. Kết hợp collection fetch join với Pageable có thể khiến limit/offset áp dụng trên các dòng join thay vì số entity cha như mong đợi. Hibernate có thể phải xử lý phân trang trong bộ nhớ hoặc phát cảnh báo tùy cấu hình.

Với trang entity cha và collection con, một chiến lược an toàn hơn:

1. Phân trang ID của entity cha.
2. Tải entity/DTO chi tiết cho danh sách ID của trang.
3. Giữ thứ tự ID nếu response yêu cầu.
4. Chạy count query riêng nếu cần Page metadata.

Nếu endpoint chỉ cần một số field từ cha và con, DTO projection thường tiết kiệm dữ liệu hơn việc tải cả entity graph.

Không fetch nhiều collection lớn chỉ để tránh LazyInitializationException. Chọn fetch plan theo use case và kiểm tra cardinality thực tế.

## 19. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Entity cha xuất hiện lặp | JOIN collection tạo nhiều dòng | DISTINCT hoặc EXISTS tùy mục tiêu |
| COUNT lớn hơn số entity | Đếm dòng join thay vì ID duy nhất | COUNT(DISTINCT parent.id) |
| LEFT JOIN vẫn loại cha không có con | Đặt điều kiện phía phải trong WHERE | Đặt điều kiện phù hợp trong ON hoặc đổi ngữ nghĩa có chủ đích |
| DISTINCT làm query chậm | Loại trùng trên tập kết quả lớn | Tránh join không cần thiết, dùng EXISTS nếu chỉ kiểm tra tồn tại |
| Page có totalElements sai | Count query không phản ánh cardinality | Khai báo countQuery đúng |
| IN list thất bại khi tăng dữ liệu | Chạm giới hạn parameter hoặc SQL quá lớn | Batching, array/table parameter hoặc staging table |
| IN list rỗng sinh SQL lỗi | Không xử lý semantics danh sách rỗng | Trả empty hoặc bỏ filter theo nghiệp vụ |
| NOT IN trả kết quả bất ngờ | Danh sách có NULL | Loại NULL hoặc dùng NOT EXISTS |
| JOIN FETCH pagination chậm | Collection join nhân dòng | Phân trang ID trước, tải chi tiết sau |
| Query có index nhưng vẫn chậm | Index không phù hợp selectivity/order hoặc plan không dùng | Đọc execution plan và đo dữ liệu thật |
| Dùng native SQL làm giảm portability | Cú pháp phụ thuộc database | Cô lập theo repository adapter và test từng engine |

## 20. Checklist tối ưu truy vấn

- [ ] Xác định một dòng kết quả đại diện cho entity cha, entity con hay một tổ hợp.
- [ ] Kiểm tra cardinality của mọi JOIN, nhất là one-to-many và many-to-many.
- [ ] Đặt điều kiện LEFT JOIN vào ON khi cần giữ entity cha không có bản ghi con phù hợp.
- [ ] Dùng DISTINCT chỉ khi cần loại trùng theo đúng tập biểu thức SELECT.
- [ ] Dùng COUNT(DISTINCT id) khi mục tiêu là đếm entity duy nhất sau join.
- [ ] Dùng EXISTS/NOT EXISTS khi chỉ cần kiểm tra có hoặc không có bản ghi liên quan.
- [ ] Chọn JOIN khi thực sự cần dữ liệu từ cả hai phía.
- [ ] Xử lý danh sách IN rỗng và NULL một cách tường minh.
- [ ] Dùng parameter binding, không ghép giá trị vào SQL.
- [ ] Chia batch hoặc dùng staging/array/table-valued parameter cho danh sách rất lớn.
- [ ] Kiểm tra ảnh hưởng batching tới thứ tự, trùng lặp và phân trang toàn cục.
- [ ] Tạo index theo query workload, khóa ngoại, filter và sort thực tế.
- [ ] Đọc execution plan và đo trên dữ liệu gần production.
- [ ] Kiểm tra count query và collection fetch join khi phân trang.
- [ ] Dùng DTO khi chỉ cần một phần dữ liệu.
- [ ] Viết integration test trên đúng database/driver triển khai.

## 21. Kết luận

Tối ưu JOIN bắt đầu từ cardinality: JOIN collection có thể nhân dòng, làm trùng entity và khiến COUNT hoặc pagination sai. **DISTINCT** hữu ích khi cần loại trùng theo kết quả SELECT, nhưng có chi phí; **COUNT(DISTINCT id)** dùng khi cần đếm entity duy nhất. Nếu chỉ cần biết entity cha có bản ghi con phù hợp, **EXISTS** hoặc **NOT EXISTS** thường diễn đạt mục tiêu rõ hơn.

Với bộ lọc IN lớn, hãy xử lý danh sách rỗng/NULL, bind parameter, chia batch khi phù hợp hoặc dùng staging table và cơ chế đặc thù của database. Cuối cùng, kiểm tra index và execution plan trên dữ liệu thực tế. Tối ưu tốt là giảm công việc database phải làm mà vẫn giữ nguyên ngữ nghĩa nghiệp vụ của kết quả.