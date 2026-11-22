# JOIN FETCH theo từng tình huống sử dụng

Khi một entity có quan hệ tới entity khác, Hibernate có thể tải quan hệ đó theo nhiều cách. Nếu tải danh sách đơn hàng rồi lần lượt đọc khách hàng của từng đơn, ứng dụng có thể phát sinh nhiều câu SQL. Nếu đặt mọi association thành EAGER, một truy vấn tưởng đơn giản có thể kéo theo cả một object graph lớn. **JOIN FETCH** là một công cụ JPQL/HQL để yêu cầu tải association ngay trong truy vấn đang lấy entity gốc.

Ví dụ:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "select o from PurchaseOrder o " +
    "join fetch o.customer",
    PurchaseOrder.class
).getResultList();
~~~

Truy vấn lấy đơn hàng và yêu cầu tải luôn `customer` của từng đơn. Hibernate thường thực hiện bằng SQL JOIN, nhờ đó code có thể dùng tên khách hàng trong cùng persistence context mà không cần một truy vấn lazy riêng cho mỗi đơn.

Tuy nhiên, JOIN FETCH không phải lựa chọn mặc định cho mọi quan hệ. Nó có thể làm nhân số hàng kết quả khi join collection, gây vấn đề với pagination, kết hợp nhiều collection hoặc làm truy vấn tải nhiều dữ liệu hơn use case cần. Bài học này trình bày **JOIN FETCH theo từng tình huống sử dụng** trong chương **Tải dữ liệu** của module *Data Persistence Relational Access ORM Hibernate*.

Các ví dụ dùng Jakarta Persistence (`jakarta.persistence.*`), Hibernate ORM và JPQL. Một số lưu ý về HQL, batch fetching và cấu hình Hibernate được đánh dấu rõ là tính năng riêng của Hibernate. SQL minh họa có thể khác theo dialect, mapping và phiên bản.

## 1. JOIN thường và JOIN FETCH khác nhau ở đâu?

Một JOIN thông thường phục vụ điều kiện truy vấn hoặc lấy dữ liệu trong projection. Nó không tự yêu cầu association được khởi tạo trong entity result.

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "select o from PurchaseOrder o " +
    "join o.customer c " +
    "where c.active = true",
    PurchaseOrder.class
).getResultList();
~~~

Ở đây alias `c` được dùng để lọc đơn hàng theo trạng thái khách hàng. Kết quả chính vẫn là `PurchaseOrder`. Association `o.customer` không nhất thiết được fetch chỉ vì truy vấn có JOIN; nó vẫn tuân theo fetch plan của mapping và provider.

JOIN FETCH nói rõ rằng association phải được lấy cùng entity gốc:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "select o from PurchaseOrder o " +
    "join fetch o.customer " +
    "where o.customer.active = true",
    PurchaseOrder.class
).getResultList();
~~~

Ý nghĩa:

- `select o`: kết quả truy vấn là entity `PurchaseOrder`.
- `join fetch o.customer`: yêu cầu nạp association `customer` cho các đơn được trả về.
- `where ...`: điều kiện lọc tập entity gốc.

**JOIN FETCH không phải một cascade operation.** Nó không truyền persist/remove sang entity liên quan. Nó cũng không thay đổi vòng đời của entity, không lưu dữ liệu và không tạo quan hệ mới.

| Cú pháp | Mục đích chính | Association được yêu cầu tải? |
| --- | --- | --- |
| `join o.customer c` | Join để lọc, sắp xếp hoặc chiếu dữ liệu | Không tự yêu cầu |
| `join fetch o.customer` | Join và fetch association | Có |
| `left join o.customer c` | Giữ entity gốc dù association không có | Không tự yêu cầu |
| `left join fetch o.customer` | Giữ entity gốc và fetch association nếu có | Có |
| `select new ...` | Trả DTO/projection | Lấy các cột được chọn, không cần entity graph |

## 2. Mô hình dữ liệu xuyên suốt

Giả sử một cửa hàng có khách hàng, đơn hàng, dòng hàng và sản phẩm:

~~~text
Customer 1 ───── N PurchaseOrder
PurchaseOrder 1 ───── N OrderLine
OrderLine N ───── 1 Product
~~~

SQL giản lược:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(160) NOT NULL,
    active BOOLEAN NOT NULL
);

CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT,
    order_code VARCHAR(40) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(15, 2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);
~~~

Mapping minh họa:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    // Các thuộc tính và phương thức khác.
}
~~~

~~~java
@Entity
@Table(name = "order_lines")
public class OrderLine {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "product_id")
    private Product product;

    private int quantity;
    private BigDecimal unitPrice;
}
~~~

Các entity ở đây dùng LAZY để minh họa việc fetch plan có thể thay đổi theo use case. Với JPA, default fetch của `@ManyToOne` và `@OneToOne` là EAGER, còn `@OneToMany` và `@ManyToMany` là LAZY. Trong ứng dụng thực, khai báo LAZY tường minh cho to-one thường giúp tránh việc tải association ngoài ý muốn, nhưng hiệu quả còn phụ thuộc provider và cấu hình proxy/enhancement.

## 3. Tình huống 1 — Danh sách đơn hàng cần tên khách hàng

Đây là use case điển hình cho fetch join to-one. Trang danh sách hiển thị mã đơn và tên khách hàng, nhưng không cần các dòng hàng.

Nếu chỉ truy vấn entity:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "select o from PurchaseOrder o order by o.createdAt desc",
    PurchaseOrder.class
).getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(
        order.getOrderCode() + " - " +
        order.getCustomer().getDisplayName()
    );
}
~~~

Nếu `customer` lazy và chưa có trong persistence context/cache, mỗi lần gọi `getDisplayName()` có thể khởi tạo một reference riêng. Với N đơn và nhiều khách hàng khác nhau, đây là nguy cơ N+1.

Dùng JOIN FETCH:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "select o from PurchaseOrder o " +
    "left join fetch o.customer " +
    "order by o.createdAt desc",
    PurchaseOrder.class
).getResultList();
~~~

SQL có thể có dạng:

~~~sql
SELECT o.*, c.*
FROM purchase_orders o
LEFT JOIN customers c ON c.id = o.customer_id
ORDER BY o.created_at DESC;
~~~

Khi kết quả trả về, association customer của từng đơn đã được fetch theo truy vấn. Truy cập tên khách hàng không cần một lazy SELECT riêng nếu trạng thái đã được lấy đầy đủ.

### Nên dùng INNER hay LEFT JOIN FETCH?

- `join fetch` tương đương inner join: chỉ giữ đơn có customer phù hợp.
- `left join fetch` giữ cả đơn không có customer, nếu mapping/schema cho phép null association.

Nếu `customer_id` nullable hoặc nghiệp vụ muốn giữ tất cả đơn, LEFT JOIN FETCH thường phù hợp hơn. Nếu association bắt buộc và dữ liệu bảo đảm có customer, INNER JOIN FETCH có thể diễn đạt rõ điều kiện cần liên kết.

Đừng chọn INNER chỉ vì nghĩ nó nhanh hơn. Nó thay đổi **tập entity gốc được trả về**.

## 4. Tình huống 2 — Chi tiết đơn hàng cần sản phẩm

Khi hiển thị một đơn, có thể cần các dòng hàng và tên sản phẩm:

~~~java
PurchaseOrder order = em.createQuery(
    "select o from PurchaseOrder o " +
    "left join fetch o.lines " +
    "where o.id = :id",
    PurchaseOrder.class
)
.setParameter("id", orderId)
.getSingleResult();
~~~

Collection `lines` được fetch cùng đơn hàng. Nhưng mỗi `OrderLine.product` vẫn có thể lazy. Nếu sau đó lặp qua dòng và đọc tên sản phẩm:

~~~java
for (OrderLine line : order.getLines()) {
    System.out.println(line.getProduct().getName());
}
~~~

thì có thể lại xuất hiện N+1 cho sản phẩm.

### Fetch lồng nhau

Với Hibernate HQL, có thể dùng alias trên fetch join để fetch association ở cấp tiếp theo:

~~~java
PurchaseOrder order = em.createQuery(
    "select o from PurchaseOrder o " +
    "left join fetch o.lines line " +
    "left join fetch line.product " +
    "where o.id = :id",
    PurchaseOrder.class
)
.setParameter("id", orderId)
.getSingleResult();
~~~

Đây là cú pháp HQL mà Hibernate hỗ trợ; alias trên fetch join **không portable theo JPQL chuẩn**. Nếu cần mã JPQL portable hoặc muốn biểu diễn graph rõ ràng, cân nhắc Entity Graph ở phần sau.

SQL minh họa:

~~~sql
SELECT o.*, l.*, p.*
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
LEFT JOIN products p ON p.id = l.product_id
WHERE o.id = ?;
~~~

Đối với một đơn cụ thể có số dòng vừa phải, fetch join nested có thể là lựa chọn dễ hiểu. Với hàng nghìn dòng hoặc nhiều collection sâu, cần cân nhắc kích thước result set và dữ liệu thật sự cần hiển thị.

## 5. Tình huống 3 — Chi tiết một entity, chỉ cần một association

Nếu use case lấy một đơn theo ID và cần customer, một fetch join đơn giản thường đủ:

~~~java
PurchaseOrder order = em.createQuery(
    "select o from PurchaseOrder o " +
    "join fetch o.customer " +
    "where o.id = :id",
    PurchaseOrder.class
)
.setParameter("id", orderId)
.getSingleResult();
~~~

Có thể dùng `em.find` với Entity Graph nếu muốn dùng API tìm theo ID:

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    Map.of("jakarta.persistence.fetchgraph", graph)
);
~~~

Hai cách đều biểu đạt fetch plan, nhưng khác về hình thức truy vấn:

- JPQL JOIN FETCH phù hợp khi truy vấn cần thêm điều kiện, sort hoặc join cụ thể.
- Entity Graph hữu ích khi muốn tách fetch plan khỏi JPQL và tái sử dụng trên các truy vấn/entity load khác nhau.
- Entity Graph không bảo đảm provider phải sinh đúng một SQL JOIN; provider được quyền chọn chiến lược tải miễn đáp ứng fetch requirement.

Nếu chỉ cần vài trường để hiển thị, DTO projection có thể nhẹ hơn việc nạp cả entity.

## 6. Tình huống 4 — Danh sách đơn hàng có thể không có khách hàng

Nếu association tùy chọn:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = true)
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

dùng:

~~~java
select o
from PurchaseOrder o
left join fetch o.customer
~~~

LEFT JOIN FETCH giữ đơn ngay cả khi `customer_id` là NULL hoặc không có hàng customer khớp (trong trường hợp dữ liệu không có FK constraint). Field association tương ứng sẽ là null theo mapping.

Nếu dùng:

~~~java
select o
from PurchaseOrder o
join fetch o.customer
~~~

đơn không có customer sẽ bị loại khỏi kết quả. Điều này đôi khi đúng với báo cáo “chỉ đơn có khách hàng”, nhưng sai nếu use case muốn hiển thị mọi đơn.

**INNER/LEFT là quyết định về kết quả nghiệp vụ, không chỉ là cách viết SQL.**

## 7. Tình huống 5 — Chỉ muốn lọc theo association, nhưng vẫn tải đầy đủ collection

Giả sử cần tìm những đơn có ít nhất một dòng thuộc sản phẩm ID 7, nhưng khi trả mỗi đơn ta muốn có **tất cả các dòng hàng** của nó.

Một cách rõ ràng là dùng EXISTS để lọc root và fetch join collection:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "select distinct o from PurchaseOrder o " +
    "left join fetch o.lines " +
    "where exists (" +
    "  select 1 from OrderLine candidate " +
    "  where candidate.order = o " +
    "    and candidate.product.id = :productId" +
    ")",
    PurchaseOrder.class
)
.setParameter("productId", 7L)
.getResultList();
~~~

Điều kiện EXISTS chọn những đơn có dòng phù hợp; fetch join lấy collection `lines` cho các đơn được chọn. Cách này giúp tránh một lỗi thiết kế: lọc trực tiếp collection fetch join rồi vô tình coi collection đã khởi tạo là **toàn bộ collection**, trong khi thực tế chỉ có các phần tử thỏa điều kiện.

### Vì sao không nên lọc trực tiếp association đang fetch?

Ví dụ HQL sau có thể trông hấp dẫn:

~~~hql
select o
from PurchaseOrder o
join fetch o.lines line
where line.product.id = :productId
~~~

Nó có thể tạo kết quả root đúng theo điều kiện, nhưng collection được nạp từ các hàng join phù hợp với WHERE có thể chỉ chứa những dòng đã lọc. Một association collection đã initialized với dữ liệu không đầy đủ dễ làm code phía sau hiểu sai trạng thái domain.

Quy tắc thực hành: **dùng JOIN/EXISTS riêng để lọc root; fetch join association đầy đủ theo nhu cầu**. Nếu use case thật sự muốn một tập con các dòng hàng, trả DTO/projection hoặc truy vấn OrderLine riêng, không giả vờ đó là collection đầy đủ của entity.

## 8. Tình huống 6 — Cần lọc theo thuộc tính to-one và vẫn fetch to-one

Với quan hệ to-one, việc lọc theo thuộc tính của association và fetch association thường ít rủi ro về cardinality hơn collection:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "select o from PurchaseOrder o " +
    "join fetch o.customer " +
    "where o.customer.active = true " +
    "order by o.createdAt desc",
    PurchaseOrder.class
).getResultList();
~~~

Truy vấn trả đơn có khách hàng active và nạp customer cùng lúc.

Nếu customer là optional và muốn giữ cả đơn chưa có customer, cần điều kiện phù hợp với LEFT JOIN. Điều kiện đặt trong WHERE có thể loại các hàng có customer NULL:

~~~sql
LEFT JOIN customers c ON ...
WHERE c.active = true
~~~

Điều kiện WHERE trên c khiến LEFT JOIN có hiệu ứng gần như INNER đối với những hàng NULL. Nếu muốn giữ đơn không có customer và chỉ lấy customer khi active, phải cân nhắc điều kiện ON/provider syntax hoặc query/DTO riêng; JPQL fetch join portable có giới hạn biểu đạt điều kiện ON cho fetch association. Không sửa ngữ nghĩa chỉ bằng cách đổi chữ join mà không xem logic null.

## 9. Tình huống 7 — Fetch một collection trong danh sách root

JOIN FETCH collection làm số hàng SQL tăng theo số phần tử collection.

Giả sử có 3 đơn:

| Đơn hàng | Số dòng |
| --- | ---: |
| 101 | 2 |
| 102 | 3 |
| 103 | 0 |

Truy vấn:

~~~jpql
select o
from PurchaseOrder o
left join fetch o.lines
~~~

SQL result set có thể có:

| order_id | line_id |
| ---: | ---: |
| 101 | 1 |
| 101 | 2 |
| 102 | 3 |
| 102 | 4 |
| 102 | 5 |
| 103 | NULL |

Hàng đơn 101 xuất hiện hai lần ở mức SQL vì có hai dòng. Hibernate ghép các hàng vào cùng một entity root và collection tương ứng.

### Có cần `DISTINCT` không?

JPQL có thể viết:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "select distinct o from PurchaseOrder o " +
    "left join fetch o.lines",
    PurchaseOrder.class
).getResultList();
~~~

`DISTINCT` biểu đạt rằng kết quả entity root không nên chứa bản sao trùng theo semantics của truy vấn. Với Hibernate 6, các entity root trùng lặp do collection fetch join được tự động loại khỏi kết quả entity ở bộ nhớ trong nhiều trường hợp; không nhất thiết phải thêm DISTINCT chỉ để loại bản sao root. Các phiên bản Hibernate cũ và provider khác có thể có hành vi khác.

Nếu thêm DISTINCT, provider có thể truyền nó xuống SQL. Vì các cột child khác nhau, SQL DISTINCT không nhất thiết giảm số hàng join; nó có thể thêm chi phí sort/hash. Cần kiểm tra SQL thực tế và phiên bản provider.

**Đừng nhầm số hàng SQL với số entity root trong List.** Một root có thể được lặp ở result set SQL để biểu diễn collection.

## 10. Tình huống 8 — Pagination với JOIN FETCH to-one

Phân trang với association to-one thường an toàn hơn collection vì mỗi root chỉ có tối đa một hàng liên quan cho một association to-one hợp lệ.

Ví dụ:

~~~java
List<PurchaseOrder> page = em.createQuery(
    "select o from PurchaseOrder o " +
    "left join fetch o.customer " +
    "order by o.createdAt desc, o.id desc",
    PurchaseOrder.class
)
.setFirstResult(offset)
.setMaxResults(pageSize)
.getResultList();
~~~

Vì customer là ManyToOne/OneToOne, join thường không nhân mỗi order thành nhiều hàng. Do đó giới hạn kết quả SQL có thể tương ứng với giới hạn root entity, miễn mapping thực sự bảo đảm to-one không tạo nhiều hàng cho mỗi root.

Dùng thêm khóa sắp xếp ổn định (`o.id`) để tránh thứ tự không xác định giữa các đơn có cùng `createdAt`. Đây là nguyên tắc pagination nói chung, không riêng JOIN FETCH.

## 11. Tình huống 9 — Pagination với JOIN FETCH collection

Đây là trường hợp cần tránh:

~~~java
List<PurchaseOrder> page = em.createQuery(
    "select distinct o from PurchaseOrder o " +
    "left join fetch o.lines " +
    "order by o.createdAt desc",
    PurchaseOrder.class
)
.setFirstResult(0)
.setMaxResults(20)
.getResultList();
~~~

Vấn đề: một đơn có thể tạo nhiều hàng SQL. Nếu database áp dụng LIMIT/OFFSET trên result set đã join, nó có thể cắt giữa các dòng của cùng một đơn hoặc trả ít root hơn dự kiến. Provider cần bảo đảm collection được nạp đúng nên Hibernate có thể phải **phân trang trong bộ nhớ** sau khi lấy nhiều hàng, gây tải lớn và khó dự đoán hiệu năng.

Hibernate có cảnh báo khi pagination kết hợp collection fetch. Có thể cấu hình để biến cảnh báo thành lỗi trong môi trường phát triển/test:

~~~properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

Tên setting và khả năng áp dụng cần đối chiếu phiên bản Hibernate. Mục đích là tránh âm thầm chạy một truy vấn tải quá nhiều hàng rồi phân trang trong memory.

### Cách an toàn hơn: hai truy vấn

**Bước 1 — Lấy trang ID root:**

~~~java
List<Long> ids = em.createQuery(
    "select o.id from PurchaseOrder o " +
    "where o.status = :status " +
    "order by o.createdAt desc, o.id desc",
    Long.class
)
.setParameter("status", OrderStatus.PAID)
.setFirstResult(offset)
.setMaxResults(pageSize)
.getResultList();
~~~

**Bước 2 — Fetch collection cho đúng tập ID:**

~~~java
if (ids.isEmpty()) {
    return List.of();
}

List<PurchaseOrder> fetched = em.createQuery(
    "select distinct o from PurchaseOrder o " +
    "left join fetch o.lines " +
    "where o.id in :ids",
    PurchaseOrder.class
)
.setParameter("ids", ids)
.getResultList();
~~~

Truy vấn thứ hai có thể trả kết quả theo thứ tự khác với danh sách ID, vì SQL `IN` không bảo đảm thứ tự. Nếu thứ tự trang quan trọng, hãy sắp xếp lại theo thứ tự ID ban đầu:

~~~java
Map<Long, PurchaseOrder> byId = fetched.stream()
    .collect(Collectors.toMap(PurchaseOrder::getId, Function.identity()));

List<PurchaseOrder> ordered = ids.stream()
    .map(byId::get)
    .filter(Objects::nonNull)
    .toList();
~~~

Đây là ví dụ Java hiện đại; cần import `Map`, `Collectors`, `Function` và `Objects`. Với JDK cũ chưa có `Stream.toList()`, có thể dùng `collect(Collectors.toList())`.

Hai truy vấn nên chạy trong một transaction/read consistency phù hợp nếu cần kết quả ổn định khi dữ liệu thay đổi đồng thời giữa bước lấy ID và bước fetch. Cũng cần xem giới hạn số bind parameters của database khi page size rất lớn.

### Khi nào hai bước là lựa chọn tốt?

- Trang có collection to-many cần hiển thị.
- Muốn phân trang theo root entity một cách rõ ràng.
- Cần tránh Hibernate phân trang collection fetch trong memory.
- Có thể giữ hai query trong cùng transaction và persistence context.

## 12. Tình huống 10 — Nhiều collection trên cùng một root

Giả sử `PurchaseOrder` có hai collection:

- `lines`: các dòng hàng.
- `notes`: ghi chú của đơn.

Một truy vấn cố fetch cả hai:

~~~hql
select distinct o
from PurchaseOrder o
left join fetch o.lines
left join fetch o.notes
where o.id = :id
~~~

Nếu một đơn có 5 dòng và 4 ghi chú, SQL join có thể tạo **5 × 4 = 20 hàng** cho cùng root. Đây là Cartesian multiplication giữa hai collection.

Hệ quả:

- Nhiều dữ liệu lặp lại trên wire.
- Tốn CPU và bộ nhớ để hydrate entity/collection.
- Kích thước result set tăng theo tích số phần tử.
- Hibernate có thể ném `MultipleBagFetchException` nếu đồng thời fetch nhiều bag collection trong mapping phù hợp.

Đổi một collection từ List sang Set có thể ảnh hưởng lỗi MultipleBagFetchException trong một số mapping, nhưng **không loại bỏ Cartesian explosion**. Không dùng Set chỉ để né exception nếu semantics collection là danh sách có thứ tự hoặc cho phép phần tử trùng.

### Cách xử lý: fetch collection theo các truy vấn riêng

Trong cùng persistence context:

~~~java
PurchaseOrder order = em.createQuery(
    "select distinct o from PurchaseOrder o " +
    "left join fetch o.lines " +
    "where o.id = :id",
    PurchaseOrder.class
)
.setParameter("id", orderId)
.getSingleResult();

em.createQuery(
    "select distinct o from PurchaseOrder o " +
    "left join fetch o.notes " +
    "where o.id = :id",
    PurchaseOrder.class
)
.setParameter("id", orderId)
.getSingleResult();
~~~

Cùng một persistence context bảo đảm entity root có identity thống nhất; query thứ hai có thể khởi tạo collection notes trên instance managed đã có. Kết quả là hai query với cardinality dễ kiểm soát hơn thay vì một tích số lớn.

Một lựa chọn khác là Entity Graph hoặc batch fetching/subselect fetch tùy use case và provider. **Không có quy tắc phải gộp tất cả association vào một JOIN FETCH.**

## 13. Tình huống 11 — Collection lớn: có nên fetch join không?

Nếu một đơn có hàng chục nghìn dòng lịch sử, việc fetch toàn bộ collection chỉ để hiển thị tổng tiền là lãng phí.

Thay vì:

~~~java
PurchaseOrder order = em.createQuery(
    "select o from PurchaseOrder o " +
    "left join fetch o.lines where o.id = :id",
    PurchaseOrder.class
)
.setParameter("id", id)
.getSingleResult();

BigDecimal total = order.getLines().stream()
    .map(line -> line.getUnitPrice()
        .multiply(BigDecimal.valueOf(line.getQuantity())))
    .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

có thể để database tính tổng:

~~~java
BigDecimal total = em.createQuery(
    "select sum(l.unitPrice * l.quantity) " +
    "from OrderLine l where l.order.id = :id",
    BigDecimal.class
)
.setParameter("id", id)
.getSingleResult();
~~~

Hoặc lấy projection theo từng phần tử nếu UI chỉ hiển thị một trang dòng hàng. JOIN FETCH hữu ích khi cần object graph, nhưng không nên tải collection khổng lồ chỉ để tính toán tổng hợp hoặc hiển thị vài cột.

**Fetch entity khi cần entity behavior/state; dùng projection khi cần dữ liệu trình bày hoặc phép tổng hợp.**

## 14. Tình huống 12 — Fetch join và DTO projection

Nếu màn hình chỉ cần mã đơn, ngày tạo và tên khách hàng, không cần managed entity:

~~~java
public record OrderListItem(
    Long id,
    String orderCode,
    LocalDateTime createdAt,
    String customerName
) {
}
~~~

JPQL constructor projection:

~~~java
List<OrderListItem> rows = em.createQuery(
    "select new com.example.shop.api.OrderListItem(" +
    "o.id, o.orderCode, o.createdAt, c.displayName) " +
    "from PurchaseOrder o " +
    "left join o.customer c " +
    "order by o.createdAt desc, o.id desc",
    OrderListItem.class
).getResultList();
~~~

Đây là JOIN thông thường trong projection, không cần JOIN FETCH vì kết quả không phải entity graph `PurchaseOrder`. Các cột được chọn trực tiếp thành DTO.

So sánh:

| Nhu cầu | JOIN FETCH entity | DTO projection |
| --- | --- | --- |
| Cần entity managed để sửa | Phù hợp | Không |
| Cần đầy đủ association object | Phù hợp | Chỉ nếu thiết kế DTO lồng |
| Chỉ hiển thị một số cột | Có thể tải thừa | Thường phù hợp hơn |
| Cần dirty checking/cascade về sau | Có | Không áp dụng trực tiếp |
| Giảm dữ liệu hydrate | Không nhất thiết | Thường tốt hơn |
| Serialize qua API | Cần chuyển DTO/fetch plan cẩn thận | Phù hợp trực tiếp |

Không phải cứ dùng JOIN FETCH là hiệu năng tốt hơn JOIN projection. Chọn theo mục tiêu use case.

## 15. Tình huống 13 — Count query và phân trang Spring Data

Khi repository trả `Page<PurchaseOrder>`, framework thường cần một query lấy dữ liệu và một count query. Không nên copy nguyên JOIN FETCH collection vào count query.

Ví dụ:

~~~java
@Query(
    value = "select o from PurchaseOrder o " +
            "left join fetch o.customer " +
            "where o.status = :status " +
            "order by o.createdAt desc",
    countQuery = "select count(o) from PurchaseOrder o " +
                 "where o.status = :status"
)
Page<PurchaseOrder> findPageWithCustomer(
    OrderStatus status,
    Pageable pageable
);
~~~

Đây là ví dụ Spring Data JPA; cú pháp annotation/import cần khớp phiên bản. Count query đếm root entity, không cần fetch association để đếm.

Nếu fetch join collection trong query phân trang, vấn đề pagination collection fetch vẫn tồn tại. Tách count query **không tự sửa** vấn đề result query. Cần dùng hai-step pagination hoặc projection/fetch plan khác.

Với to-one fetch join, pagination thường an toàn hơn như đã trình bày, nhưng vẫn cần kiểm tra query thực tế và sort ổn định.

## 16. Tình huống 14 — Fetch join trong query có GROUP BY hoặc aggregate

JOIN FETCH dành cho truy vấn trả về entity và association cần được khởi tạo. Nó thường không phù hợp với query chỉ trả kết quả tổng hợp:

~~~jpql
select c, count(o)
from Customer c
left join c.orders o
group by c
~~~

Nếu mục tiêu là đếm số đơn theo khách hàng, không cần fetch toàn bộ collection orders. Dùng DTO:

~~~java
public record CustomerOrderCount(
    Long customerId,
    String customerName,
    Long orderCount
) {
}
~~~

~~~java
List<CustomerOrderCount> counts = em.createQuery(
    "select new com.example.shop.api.CustomerOrderCount(" +
    "c.id, c.displayName, count(o)) " +
    "from Customer c left join c.orders o " +
    "group by c.id, c.displayName",
    CustomerOrderCount.class
).getResultList();
~~~

Đưa collection fetch vào aggregate query có thể làm dữ liệu phình to hoặc vi phạm ngữ nghĩa truy vấn. **Khi kết quả là con số/summary, hãy trả summary**, không hydrate cả entity graph.

## 17. Tình huống 15 — Fetch association qua nhiều cấp

Use case hiển thị đơn, dòng hàng và sản phẩm có thể dùng nested fetch. Với Hibernate HQL:

~~~hql
select distinct o
from PurchaseOrder o
left join fetch o.lines line
left join fetch line.product
where o.id = :id
~~~

Cú pháp alias trên fetch join là extension HQL của Hibernate; đừng giả định portable với mọi JPA provider.

Một lựa chọn dùng Entity Graph:

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

Subgraph<OrderLine> lineGraph =
    graph.addSubgraph("lines");

lineGraph.addAttributeNodes("product");

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    Map.of("jakarta.persistence.fetchgraph", graph)
);
~~~

Entity Graph cho phép diễn đạt nested path mà không cần alias HQL. Provider có thể thực hiện bằng join hoặc secondary select; hãy xem SQL nếu cần tối ưu.

### Không fetch cả graph theo thói quen

Nếu trang chỉ cần tên khách hàng, fetch lines và products là tải thừa. Fetch depth lớn có thể tạo:

- Result set rộng và nhiều hàng lặp.
- Nhiều object managed trong persistence context.
- Thời gian hydrate cao.
- Nguy cơ Cartesian product nếu nhiều collection.
- Khó phân trang và kiểm soát bộ nhớ.

Fetch plan nên gắn với use case cụ thể, không phải một cấu hình “load everything” dùng chung.

## 18. Tình huống 16 — Lọc collection nhưng cần kết quả con riêng

Nếu use case muốn “các dòng hàng có sản phẩm đang bán”, có thể truy vấn OrderLine trực tiếp:

~~~java
List<OrderLine> lines = em.createQuery(
    "select l from OrderLine l " +
    "join fetch l.product " +
    "where l.order.id = :orderId " +
    "and l.product.active = true",
    OrderLine.class
)
.setParameter("orderId", orderId)
.getResultList();
~~~

Kết quả là các dòng hàng phù hợp, và product được fetch. Không cần nạp toàn bộ `PurchaseOrder.lines` rồi loại phần tử trong Java.

Nếu muốn root PurchaseOrder nhưng chỉ hiển thị các dòng được lọc, hãy tạo DTO chứa order info và danh sách dòng phù hợp hoặc truy vấn riêng cho các dòng. Không gắn một collection con bị lọc vào entity như thể nó là collection hoàn chỉnh nếu domain logic có thể dùng nó cho tính toán/xóa/cập nhật.

## 19. Tình huống 17 — Nhiều association to-one cùng lúc

Fetch nhiều association to-one thường ít gây nhân số hàng hơn fetch nhiều collection:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "select o from PurchaseOrder o " +
    "left join fetch o.customer " +
    "left join fetch o.createdBy " +
    "left join fetch o.billingAddress " +
    "where o.status = :status",
    PurchaseOrder.class
)
.setParameter("status", OrderStatus.CONFIRMED)
.getResultList();
~~~

Mỗi association to-one hợp lệ chỉ đóng góp tối đa một hàng cho mỗi root. Do đó nhiều to-one fetch join thường có thể phù hợp khi màn hình cần những thông tin này.

Tuy vậy, vẫn phải cân nhắc:

- Association có thật sự là to-one trong dữ liệu và constraint không?
- Có mapping sai cardinality khiến JOIN nhân hàng không?
- Những cột có cần thiết cho use case không?
- Có nullable association khiến INNER JOIN loại root ngoài ý muốn không?
- Có thể dùng DTO projection để chỉ lấy vài field không?

Nếu dữ liệu thực tế có nhiều hàng khớp với một quan hệ được khai báo to-one do thiếu unique constraint, JOIN có thể nhân hàng và ORM có thể gặp lỗi non-unique result hoặc dữ liệu mapping bất thường. Mapping to-one cần được hỗ trợ bởi uniqueness đúng ở database.

## 20. Tình huống 18 — Fetch join với điều kiện ON

JPQL hỗ trợ điều kiện join trong các trường hợp phù hợp; tuy nhiên **fetch join không phải nơi tốt để tạo association chỉ chứa một phần dữ liệu**.

Ví dụ muốn lấy đơn và chỉ những dòng hàng có quantity lớn hơn 1, mục tiêu có thể là một báo cáo:

~~~java
List<OrderLineSummary> summaries = em.createQuery(
    "select new com.example.shop.api.OrderLineSummary(" +
    "o.id, o.orderCode, l.id, l.quantity) " +
    "from PurchaseOrder o " +
    "join o.lines l " +
    "where l.quantity > 1",
    OrderLineSummary.class
).getResultList();
~~~

Projection này thể hiện rõ mỗi kết quả là một dòng phù hợp. Nếu fetch join collection rồi thêm điều kiện ON/WHERE theo child, có nguy cơ association initialized không đầy đủ và gây nhầm lẫn về domain state.

Trong JPQL portable, fetch join có giới hạn cú pháp; một số alias/ON condition trên fetch join chỉ được hỗ trợ như extension HQL. Khi query cần điều kiện phức tạp trên association, hãy cân nhắc join thường, EXISTS hoặc DTO.

## 21. Tình huống 19 — JOIN FETCH với DISTINCT và thứ tự

Khi fetch collection, root có thể lặp ở SQL. Ví dụ:

~~~jpql
select distinct o
from PurchaseOrder o
left join fetch o.lines
order by o.createdAt desc
~~~

Cần nhớ:

- `DISTINCT` là semantics ở cấp kết quả JPQL.
- Hibernate 6 tự loại duplicate entity root phát sinh từ fetch join trong nhiều tình huống.
- SQL DISTINCT có thể không giảm hàng nếu child columns khác nhau.
- `ORDER BY o.createdAt` sắp xếp hàng SQL, nhưng khi một root có nhiều child, các hàng root lặp có cùng createdAt.
- Nếu cần thứ tự collection bên trong root, mapping `@OrderBy` hoặc `@OrderColumn` giải quyết một vấn đề khác với thứ tự danh sách root.

Đối với pagination, thêm một tie-breaker duy nhất như `o.id` để thứ tự ổn định. Với collection fetch, ưu tiên hai-phase pagination thay vì dựa vào DISTINCT.

## 22. Tình huống 20 — Batch fetching khi không muốn JOIN

JOIN FETCH không phải cách duy nhất giảm N+1. Hibernate hỗ trợ **batch fetching** để gom nhiều lazy reference/collection vào một số query theo lô.

Ví dụ Hibernate-specific:

~~~java
import org.hibernate.annotations.BatchSize;

@Entity
public class PurchaseOrder {
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    @BatchSize(size = 32)
    private Customer customer;
}
~~~

Hoặc cấu hình mặc định phù hợp phiên bản:

~~~properties
hibernate.default_batch_fetch_size=32
~~~

Khi truy cập một số proxy/collection, Hibernate có thể tải nhiều ID trong một query dùng IN thay vì một query cho từng association. Batch fetching hữu ích khi:

- Danh sách root lớn và association được truy cập một phần.
- Muốn giữ query gốc đơn giản, tránh result set join quá rộng.
- Có nhiều collection/association không phù hợp fetch đồng thời.
- Không cần tất cả association ngay từ đầu.

`@BatchSize` và `hibernate.default_batch_fetch_size` là tính năng Hibernate-specific, không thuộc JPA chuẩn. Batch size cần được đo theo kích thước dữ liệu, giới hạn bind parameter và database.

## 23. Tình huống 21 — Hibernate SUBSELECT fetching

Hibernate có chiến lược `FetchMode.SUBSELECT` cho một số collection:

~~~java
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<OrderLine> lines;
~~~

Sau khi tải một nhóm PurchaseOrder và truy cập một collection, Hibernate có thể dùng subselect dựa trên query root ban đầu để tải collection cho nhóm entity liên quan, thay vì một query cho mỗi root.

Đây là extension Hibernate. Nó không phải JOIN FETCH và cũng không bảo đảm một SQL cho toàn bộ graph. Cần cân nhắc truy vấn root ban đầu, số entity trong persistence context và khả năng subselect tải nhiều child hơn use case cần.

## 24. Tình huống 22 — Entity Graph hay JOIN FETCH?

Hai cơ chế thường phục vụ mục tiêu tương tự nhưng cách diễn đạt khác nhau.

**JOIN FETCH trong JPQL:**

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "select o from PurchaseOrder o " +
    "left join fetch o.customer",
    PurchaseOrder.class
).getResultList();
~~~

**Entity Graph:**

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

List<PurchaseOrder> orders = em.createQuery(
    "select o from PurchaseOrder o",
    PurchaseOrder.class
)
.setHint("jakarta.persistence.fetchgraph", graph)
.getResultList();
~~~

| Tiêu chí | JOIN FETCH | Entity Graph |
| --- | --- | --- |
| Khai báo fetch plan | Ngay trong JPQL/HQL | Tách riêng qua graph metadata |
| Điều kiện lọc/sort | Cùng query, linh hoạt | Query vẫn khai báo riêng |
| Tái sử dụng | Có thể phải lặp fetch path | Có thể đặt tên/tái sử dụng graph |
| SQL cụ thể | Thường biểu đạt join rõ | Provider chọn chiến lược đáp ứng graph |
| Portable | JPQL fetch join chuẩn; HQL có extension | API chuẩn JPA |
| Collection pagination | Có vấn đề tương tự | Không tự giải quyết nếu provider fetch collection join |
| DTO projection | Không cần fetch join | Entity graph áp dụng entity load, không thay DTO query |

Không có lựa chọn nào luôn nhanh hơn. Nếu cần kiểm soát query cụ thể, JOIN FETCH rõ ràng. Nếu muốn tách fetch plan khỏi query hoặc dùng cùng graph ở nhiều nơi, Entity Graph hữu ích.

## 25. Tình huống 23 — Không cần entity graph: dùng projection

Ví dụ trang thống kê chỉ cần:

- Mã đơn.
- Tên khách hàng.
- Tổng số dòng hàng.
- Tổng tiền.

Không nên fetch toàn bộ order, lines và products nếu chỉ cần summary. Có thể dùng aggregate projection:

~~~java
public record OrderSummary(
    Long orderId,
    String orderCode,
    String customerName,
    Long lineCount,
    BigDecimal total
) {
}
~~~

~~~java
List<OrderSummary> result = em.createQuery(
    "select new com.example.shop.api.OrderSummary(" +
    "o.id, o.orderCode, c.displayName, " +
    "count(l), sum(l.quantity * l.unitPrice)) " +
    "from PurchaseOrder o " +
    "left join o.customer c " +
    "left join o.lines l " +
    "group by o.id, o.orderCode, c.displayName",
    OrderSummary.class
).getResultList();
~~~

Đây là ví dụ cần điều chỉnh kiểu trả về của `count` theo provider/constructor (JPQL count thường là Long) và kiểu kết quả của phép sum. Với collection nhiều cấp, aggregate có thể nhân hàng nếu join thêm collection khác; tách subquery hoặc query riêng khi cần.

Projection tránh hydrate entity graph và trả đúng shape dữ liệu UI cần. Nó không tham gia dirty checking như managed entity.

## 26. Tình huống 24 — JOIN FETCH trong truy vấn phân trang bằng Spring Data

Với Spring Data JPA, ví dụ fetch to-one:

~~~java
@Query(
    value = "select o from PurchaseOrder o " +
            "left join fetch o.customer " +
            "where o.status = :status",
    countQuery = "select count(o) from PurchaseOrder o " +
                 "where o.status = :status"
)
Page<PurchaseOrder> findPageWithCustomer(
    OrderStatus status,
    Pageable pageable
);
~~~

Count query không cần fetch customer vì mục tiêu chỉ đếm số root phù hợp. Fetch to-one thường tương thích pagination hơn collection.

Với collection fetch, tránh dùng cùng mẫu Page query một cách máy móc. Hãy phân trang ID root trước rồi fetch collection theo ID như phần 11, hoặc trả DTO/projection phân trang trực tiếp.

Một repository method có thể trả `Slice` nếu không cần total count; nhưng Slice không tự giải quyết vấn đề pagination trên collection fetch. Vẫn phải bảo đảm giới hạn được áp dụng trên root chứ không phải hàng join đã nhân.

## 27. Tình huống 25 — Tải một association nhiều cấp mà không cần nạp collection

Giả sử trang chi tiết đơn chỉ cần:

- Đơn hàng.
- Khách hàng.
- Tổng tiền.
- Không cần danh sách dòng hàng.

Không nên dùng:

~~~hql
select distinct o
from PurchaseOrder o
left join fetch o.customer
left join fetch o.lines
left join fetch o.lines.product
where o.id = :id
~~~

Chỉ để lấy customer. Fetch thừa lines và product sẽ tăng SQL result set và số entity managed.

Dùng fetch to-one:

~~~jpql
select o
from PurchaseOrder o
left join fetch o.customer
where o.id = :id
~~~

Hoặc projection nếu chỉ cần một số scalar. **Fetch plan càng sát use case, dữ liệu phải truyền và hydrate càng ít.**

## 28. Tình huống 26 — LazyInitializationException và ranh giới service

Một controller nhận entity từ service, rồi truy cập association sau khi transaction đóng:

~~~java
PurchaseOrder order = orderService.findOrder(orderId);
return order.getLines().stream()
    .map(line -> line.getProduct().getName())
    .toList();
~~~

Nếu service trả entity detached với collection/proxy chưa initialized, controller có thể gặp `LazyInitializationException`.

Một cách giải quyết là fetch đúng graph trong service transaction rồi chuyển DTO:

~~~java
@Transactional(readOnly = true)
public OrderDetailDto getDetail(Long id) {
    PurchaseOrder order = em.createQuery(
        "select distinct o from PurchaseOrder o " +
        "left join fetch o.customer " +
        "left join fetch o.lines line " +
        "left join fetch line.product " +
        "where o.id = :id",
        PurchaseOrder.class
    )
    .setParameter("id", id)
    .getSingleResult();

    return OrderDetailDto.from(order);
}
~~~

Ví dụ dùng alias fetch join của Hibernate HQL cho nested association. `OrderDetailDto.from` là mapper giả định. Trong thực tế, nếu cần portable JPQL, có thể dùng Entity Graph hoặc truy vấn projection. Nếu có nhiều collection, không nên gộp tất cả vào một fetch join.

Không dùng Open Session in View để che giấu mọi fetch plan thiếu rõ ràng; điều đó có thể làm SQL phát sinh ở tầng serialize và khó dự đoán N+1.

## 29. Tình huống 27 — Fetch join có tương tác với lock

JPA cho phép query với lock mode:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "select o from PurchaseOrder o " +
    "left join fetch o.customer " +
    "where o.status = :status",
    PurchaseOrder.class
)
.setParameter("status", OrderStatus.OPEN)
.setLockMode(LockModeType.PESSIMISTIC_WRITE)
.getResultList();
~~~

Lock mode được áp dụng theo ngữ nghĩa JPA/provider; việc lock các hàng được join và hỗ trợ SQL phụ thuộc dialect/database. Không mặc định fetch join đồng nghĩa tất cả association được khóa theo cách giống root.

Nếu cần khóa cụ thể customer hoặc order lines, xác định entity/row nào phải được khóa và dùng lock query phù hợp. Transaction phải còn hoạt động trong suốt thời gian cần giữ lock.

## 30. Tình huống 28 — Fetch join và dữ liệu trùng do mapping

Một quan hệ được khai báo `@OneToOne` hoặc `@ManyToOne` nhưng cột FK trong database không unique/không đảm bảo đúng cardinality. Khi JOIN, một root có thể khớp nhiều hàng child, làm kết quả nhân bất ngờ.

Mapping to-one nên có ràng buộc phù hợp:

~~~sql
ALTER TABLE customer_profiles
ADD CONSTRAINT uq_customer_profile_customer
UNIQUE (customer_id);
~~~

Nếu dữ liệu thực tế là một-nhiều, hãy map `@OneToMany` thay vì khai báo to-one để che cấu trúc. JOIN FETCH chỉ làm lộ rõ vấn đề cardinality; nó không sửa dữ liệu hoặc constraint.

## 31. Quy tắc về alias trong JPQL fetch join

Trong JPQL chuẩn, cú pháp fetch join có giới hạn và **không cho phép identification variable trên fetch association theo cách HQL mở rộng**. Ví dụ portable:

~~~jpql
select o
from PurchaseOrder o
left join fetch o.customer
~~~

Với nested fetch, nhiều dự án Hibernate dùng HQL alias:

~~~hql
select o
from PurchaseOrder o
left join fetch o.lines line
left join fetch line.product
~~~

Đoạn thứ hai là Hibernate HQL extension; khi cần chạy với provider khác, kiểm tra JPQL grammar/khả năng provider và cân nhắc Entity Graph. Không sao chép HQL alias vào dự án portable mà không xác nhận.

## 32. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Vẫn có N+1 sau JOIN thường | JOIN không phải JOIN FETCH | Dùng fetch join hoặc Entity Graph |
| Đơn không có customer biến mất | Dùng INNER JOIN FETCH | Dùng LEFT JOIN FETCH nếu cần giữ root |
| Collection có dữ liệu thiếu sau lọc | Lọc trực tiếp association fetch | Dùng EXISTS để lọc root hoặc DTO cho subset |
| Root entity lặp trong kết quả | Join collection tạo nhiều SQL rows | Hiểu provider/version, dùng DISTINCT khi cần semantics |
| Pagination trả ít root hoặc tải rất nhiều hàng | Collection fetch join với LIMIT/OFFSET | Hai-phase pagination hoặc projection |
| Hibernate cảnh báo pagination in memory | Fetch collection khi phân trang | Cấu hình fail-on-pagination và sửa query |
| `MultipleBagFetchException` | Fetch đồng thời nhiều bag | Tách query, batch/subselect; xem mapping collection |
| Result set khổng lồ | Cartesian product giữa nhiều collection | Không join fetch tất cả collection cùng lúc |
| LazyInitializationException ở controller | Association chưa tải khi context đóng | Fetch trong service và trả DTO |
| EAGER vẫn phát nhiều SELECT | EAGER không bảo đảm một JOIN | Thiết kế query/fetch plan cụ thể |
| HQL chạy nhưng provider khác lỗi | Dùng alias/extension không portable | JPQL chuẩn hoặc Entity Graph |
| Count query lỗi/đếm sai | Copy fetch join collection vào count | Count root riêng, không fetch |
| Tổng hợp bị nhân số tiền | Join nhiều collection gây duplicate aggregate | Query aggregate riêng/subquery/projection |
| Entity to-one trả nhiều kết quả | DB không bảo đảm unique cardinality | Sửa mapping và constraint |
| SQL quá rộng dù UI chỉ cần vài field | Fetch entity graph thừa | DTO projection |
| Fetch join lock không khóa đúng row mong muốn | Nhầm join fetch với lock propagation | Xác định row/entity cần lock và kiểm tra dialect |

## 33. Quy trình chọn JOIN FETCH

~~~mermaid
flowchart TD
    A["Use case cần dữ liệu liên quan nào?"] --> B{"Chỉ cần vài cột để hiển thị/tổng hợp?"}
    B -- "Có" --> C["DTO/projection và JOIN thường"]
    B -- "Không" --> D{"Cần association to-one?"}
    D -- "Có" --> E["JOIN FETCH to-one; chọn INNER/LEFT theo null semantics"]
    D -- "Không" --> F{"Cần một collection to-many?"}
    F -- "Có" --> G{"Có phân trang root?"}
    G -- "Không" --> H["JOIN FETCH collection nếu cardinality hợp lý"]
    G -- "Có" --> I["Phân trang ID trước, fetch collection sau"]
    F -- "Không / nhiều collection" --> J["Entity Graph, batch/subselect hoặc tách query"]
    E --> K["Kiểm tra SQL, cardinality, transaction"]
    H --> K
    I --> K
    J --> K
    C --> K
~~~

Sơ đồ là hướng ra quyết định, không phải quy tắc cứng cho mọi query. Hãy xem số lượng hàng, kích thước collection, nhu cầu dữ liệu và khả năng phân trang của use case thực.

## 34. Bài tập tình huống

**Bài 1 — Danh sách đơn cần tên khách hàng.** Truy vấn `PurchaseOrder` rồi gọi `getCustomer().getDisplayName()` gây N+1. Cách sửa phù hợp?

**Đáp án:** Dùng `join fetch o.customer` hoặc Entity Graph chứa `customer`. Nếu chỉ cần mã đơn và tên khách, cân nhắc DTO projection.

**Bài 2 — Đơn có thể chưa có khách hàng.** Dùng `join fetch o.customer` làm đơn không có customer biến mất. Vì sao?

**Đáp án:** INNER JOIN loại root không có association phù hợp. Dùng `left join fetch` nếu cần giữ mọi đơn.

**Bài 3 — Một đơn có nhiều dòng hàng.** JOIN FETCH collection làm SQL có nhiều hàng cho cùng đơn. Có phải Hibernate tạo nhiều entity PurchaseOrder khác nhau?

**Đáp án:** Không. Một entity root được hydrate từ các hàng join và collection được lắp ghép. Duplicate result semantics tùy provider/version; Hibernate 6 tự loại nhiều duplicate root do fetch join.

**Bài 4 — Phân trang 20 đơn kèm dòng hàng.** Có nên dùng `setMaxResults(20)` trực tiếp trên collection fetch join?

**Đáp án:** Không nên. Kết quả SQL đã nhân theo số dòng hàng. Lấy page ID root trước, sau đó fetch collection theo ID trong truy vấn thứ hai.

**Bài 5 — Fetch hai collection cùng lúc.** Một đơn có 8 dòng và 6 ghi chú. Result set có thể có bao nhiêu tổ hợp?

**Đáp án:** Có thể tới 8 × 6 = 48 hàng cho root đó. Tách query hoặc dùng batch/subselect/graph phù hợp.

**Bài 6 — Lọc đơn có một sản phẩm nhưng cần tất cả dòng hàng.** Có nên filter trực tiếp alias collection fetch?

**Đáp án:** Dùng EXISTS/regular join để lọc root và fetch join collection đầy đủ. Nếu chỉ muốn các dòng phù hợp, truy vấn OrderLine hoặc DTO riêng.

**Bài 7 — Trang báo cáo chỉ cần tổng tiền.** Có nên fetch toàn bộ collection lines?

**Đáp án:** Không cần thiết. Dùng SUM/aggregate projection ở database.

**Bài 8 — Nested fetch chạy với Hibernate nhưng lỗi provider khác.** Nguyên nhân có thể?

**Đáp án:** HQL alias trên fetch join có thể là extension Hibernate, không portable JPQL. Dùng Entity Graph hoặc cú pháp chuẩn phù hợp.

**Bài 9 — INNER và LEFT JOIN FETCH.** Chọn theo tiêu chí nào?

**Đáp án:** Theo việc có muốn giữ root entity khi association null/không tồn tại hay không, không chỉ theo hiệu năng.

**Bài 10 — EAGER và Cascade ALL.** Hai thứ có liên hệ gì?

**Đáp án:** EAGER là fetch requirement; Cascade ALL truyền PERSIST, MERGE, REMOVE, REFRESH và DETACH. Chúng giải quyết hai vấn đề khác nhau.

**Bài 11 — Count query trong Page.** Có nên fetch join collection trong `select count(o)`?

**Đáp án:** Không. Count query đếm root và không cần fetch association; dùng count query riêng.

**Bài 12 — Controller truy cập collection sau khi transaction đóng.** Cách xử lý?

**Đáp án:** Fetch đúng association trong transaction service rồi chuyển DTO; không phụ thuộc proxy lazy ngoài persistence context.

## 35. Bảng chọn chiến lược theo use case

| Use case | Chiến lược nên cân nhắc | Lý do |
| --- | --- | --- |
| Danh sách đơn cần tên khách hàng | JOIN FETCH to-one | Giảm lazy query từng đơn |
| Chi tiết đơn cần customer | JOIN FETCH hoặc Entity Graph | Fetch association ngay |
| Chi tiết đơn cần lines và product | Nested fetch join HQL hoặc Entity Graph | Nạp graph cần dùng |
| Đơn có thể không có customer | LEFT JOIN FETCH | Giữ root khi association null |
| Chỉ muốn đơn có customer | INNER JOIN FETCH | Lọc root theo association bắt buộc |
| Lọc root theo child nhưng lấy toàn bộ collection | EXISTS + collection fetch | Không nạp collection bị lọc một phần |
| Trang root có to-one | Fetch join to-one + pagination | Cardinality thường không nhân root |
| Trang root có collection | Hai-phase pagination | Giới hạn root trước |
| Nhiều collection to-many | Tách query, batch/subselect | Tránh Cartesian product/MultipleBag |
| Collection rất lớn | Projection, query child riêng, aggregate | Không hydrate toàn bộ graph |
| Báo cáo summary | DTO projection + aggregate | Chỉ lấy dữ liệu cần |
| Nhiều lazy association được truy cập rải rác | Batch fetching | Gom tải theo lô |
| API cần object graph sau transaction | Fetch trong service + DTO | Tránh lazy initialization lỗi |
| Cần fetch plan tái sử dụng | Entity Graph | Tách query khỏi graph |
| Cần kiểm soát SQL cụ thể | JOIN FETCH trong JPQL/HQL | Fetch path rõ ràng |

## 36. Nguyên tắc cần nhớ

1. **JOIN thường không đồng nghĩa JOIN FETCH.** JOIN có thể chỉ phục vụ điều kiện; JOIN FETCH yêu cầu tải association cùng entity gốc.
2. **Chọn INNER hay LEFT theo ngữ nghĩa dữ liệu.** INNER loại root không có association; LEFT giữ lại root đó.
3. **Fetch to-one thường là tình huống thuận lợi.** Nó thường không nhân số root như collection to-many, nên phù hợp cho danh sách cần một vài association bắt buộc.
4. **Fetch collection làm tăng số hàng SQL.** Root có thể lặp ở result set dù persistence context vẫn quản lý một entity identity.
5. **Không phân trang collection fetch join trực tiếp.** Phân trang root ID trước rồi fetch collection theo ID là cách rõ ràng hơn.
6. **Tránh fetch nhiều collection trong một query.** Cartesian product và MultipleBagFetchException có thể làm truy vấn rất tốn kém.
7. **Không lọc collection fetch nếu cần collection đầy đủ.** Lọc root bằng EXISTS/regular join; dùng DTO hoặc query child riêng cho tập con.
8. **EAGER không bảo đảm một SQL.** Fetch plan cụ thể mới quyết định dữ liệu cần lấy cho use case.
9. **Entity Graph, batch fetching và subselect là lựa chọn bổ sung.** Không phải mọi association đều nên JOIN FETCH.
10. **DTO projection tốt cho màn hình/report chỉ cần vài cột.** Không cần hydrate entity graph nếu không dùng entity behavior.
11. **Fetch trong transaction phù hợp và trả DTO qua ranh giới service/API.** Tránh để serializer tự kích hoạt lazy query.
12. **Đọc SQL và đo trên dữ liệu thật.** Kích thước collection, index, cache, dialect và phiên bản Hibernate ảnh hưởng kết quả.

Hãy bắt đầu từ câu hỏi **use case thật sự cần dữ liệu liên quan nào**, sau đó mới chọn JOIN FETCH, Entity Graph, batch fetching hay projection. Fetch đúng association có thể loại bỏ N+1 và giữ object graph sẵn sàng trong persistence context; fetch quá nhiều lại tạo result set lớn, phá pagination hoặc làm tăng chi phí hydrate.
