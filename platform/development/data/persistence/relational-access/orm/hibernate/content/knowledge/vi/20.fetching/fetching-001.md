# Thời điểm tải khác với cách Hibernate lấy dữ liệu

Khi Hibernate tải một entity có quan hệ tới entity hoặc collection khác, cần trả lời hai câu hỏi riêng:

1. **Khi nào dữ liệu liên quan được tải?** Ngay trong quá trình tải entity gốc hay chỉ khi ứng dụng truy cập quan hệ?
2. **Hibernate lấy dữ liệu bằng cách nào?** Dùng JOIN trong cùng câu SQL, phát SELECT riêng, gom nhiều lần tải thành một batch hay dùng subselect?

Hai câu hỏi này thường bị gộp khi cấu hình `FetchType.LAZY` hoặc `FetchType.EAGER`. Nhưng LAZY/EAGER chủ yếu mô tả **thời điểm dữ liệu cần sẵn sàng**; chúng không tự quyết định duy nhất SQL sẽ có JOIN hay SELECT. Hiểu hai chiều này giúp chọn fetch plan phù hợp, tránh N+1 query, tránh tải quá nhiều dữ liệu và không làm API phụ thuộc vào việc session còn mở.

Bài này dùng Jakarta Persistence và Hibernate ORM 6.x. Các annotation Hibernate-specific như `@Fetch` và `@BatchSize` được ghi rõ. SQL chỉ minh họa hình dạng truy vấn; Hibernate có thể thay đổi alias, thứ tự join và cách render theo mapping, query, phiên bản và `Dialect`.

## 1. Hai chiều của fetching: timing và style

**Fetch timing** mô tả dữ liệu cần được nạp sớm hay trì hoãn:

- **Immediate/eager:** dữ liệu phải sẵn sàng trong quá trình tải entity theo fetch plan đang áp dụng.
- **Delayed/lazy:** dữ liệu được trì hoãn cho tới khi ứng dụng truy cập hoặc một thao tác khác yêu cầu nó.

**Fetch style** mô tả cách lấy dữ liệu:

- **JOIN:** dùng join trong cùng câu SQL với entity gốc.
- **SELECT:** phát một câu SELECT riêng để tải association/collection.
- **BATCH:** một SELECT tải nhiều association/proxy cùng lúc theo nhóm ID.
- **SUBSELECT:** tải collection cho một nhóm owner bằng truy vấn dựa trên truy vấn đã tải các owner đó.

~~~mermaid
flowchart TD
    A["Fetch plan"] --> B["Thời điểm tải (when)"]
    A --> C["Cách lấy dữ liệu (how)"]
    B --> D["Immediate / Eager"]
    B --> E["Delayed / Lazy"]
    C --> F["JOIN"]
    C --> G["SELECT"]
    C --> H["BATCH"]
    C --> I["SUBSELECT"]
    D --> J["Dữ liệu sẵn sàng theo plan"]
    E --> K["Có thể tải khi truy cập"]
    F --> L["Một SQL có join"]
    G --> M["SQL riêng"]
    H --> N["Một SQL cho nhóm ID"]
    I --> O["Một SQL cho nhóm collection owner"]
~~~

Không phải mọi tổ hợp timing/style đều được dùng giống nhau trong mọi mapping. JOIN thường tải ngay vì dữ liệu đã nằm trong result set; association delayed có thể dùng proxy trước rồi tải bằng SELECT khi được truy cập. BATCH có thể trì hoãn tới lần truy cập đầu tiên nhưng sau đó tải nhiều proxy cùng lúc.

**Câu hỏi “LAZY hay EAGER?” không trả lời được “có bao nhiêu câu SQL?”** Muốn biết số query và hình dạng SQL, phải xem fetch style và fetch plan cụ thể.

## 2. Mô hình ví dụ

Giả sử một cửa hàng có khách hàng, đơn hàng và dòng hàng:

~~~java
import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {}

    public Long getId() { return id; }
    public String getName() { return name; }
    public List<PurchaseOrder> getOrders() { return orders; }
}

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderItem> items = new ArrayList<>();

    @Column(nullable = false, length = 24)
    private String status;

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public Customer getCustomer() { return customer; }
    public List<OrderItem> getItems() { return items; }
    public String getStatus() { return status; }
}

@Entity
@Table(name = "order_items")
public class OrderItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false)
    private String productName;

    protected OrderItem() {}

    public String getProductName() { return productName; }
}
~~~

Ví dụ khai báo association LAZY tường minh để caller chọn dữ liệu cần tải theo use case. Mặc định JPA: `@ManyToOne` và `@OneToOne` là EAGER; `@OneToMany` và `@ManyToMany` là LAZY. LAZY là hint theo JPA; provider có thể có giới hạn hỗ trợ, đặc biệt với basic attribute hoặc quan hệ một-một inverse.

## 3. Fetch timing: EAGER và LAZY

### 3.1. EAGER không có nghĩa là JOIN

~~~java
@ManyToOne(fetch = FetchType.EAGER)
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

EAGER yêu cầu association sẵn sàng theo fetch semantics khi entity được trả về. Nhưng Hibernate **không bắt buộc thực hiện bằng một JOIN duy nhất**. Với JPQL/HQL query không có fetch join, Hibernate có thể:

1. SELECT danh sách đơn hàng.
2. Đọc customer ID của mỗi hàng.
3. Phát thêm SELECT để nạp các customer EAGER.

Nếu có nhiều đơn hàng tham chiếu nhiều customer, cách này có thể tạo nhiều truy vấn phụ. EAGER có thể dẫn đến N+1; batch fetching/cache có thể giảm số query nhưng không nên mặc định rằng chúng luôn được bật.

~~~text
EAGER = yêu cầu về độ sẵn sàng của association.
JOIN = một cách thực thi fetch.
EAGER không đồng nghĩa JOIN.
~~~

Nếu một use case cần association trong cùng câu SQL, chỉ định fetch join hoặc fetch plan phù hợp thay vì dựa vào EAGER toàn cục.

### 3.2. LAZY không có nghĩa “không bao giờ tải”

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

Khi tải `PurchaseOrder`, Hibernate có thể chỉ tạo proxy/reference cho `Customer`. Khi code gọi:

~~~java
String customerName = order.getCustomer().getName();
~~~

Hibernate khởi tạo reference nếu dữ liệu chưa được tải, thường bằng SELECT. Nếu association đã có trong persistence context hoặc cache phù hợp, không nhất thiết phát thêm SQL.

LAZY chỉ trì hoãn tải tới lúc cần; **nó không loại bỏ nhu cầu dữ liệu**. Nếu caller cuối cùng duyệt mọi association, Hibernate vẫn phải tải chúng.

### 3.3. Basic attribute LAZY

Với field đơn giản như nội dung dài, JPA cho phép khai báo:

~~~java
@Basic(fetch = FetchType.LAZY)
@Lob
private String longDescription;
~~~

Để trì hoãn tải basic attribute, Hibernate thường cần bytecode enhancement hỗ trợ lazy attribute loading. Nếu entity chưa được enhancement hoặc môi trường không hỗ trợ, provider có thể tải field sớm. Hibernate còn có lazy groups: nhiều thuộc tính lazy có thể được tải theo nhóm tùy cấu hình. Không giả định mọi basic property trở thành lazy chỉ bằng annotation.

### 3.4. Proxy và thời điểm phát SQL

Proxy có thể cung cấp ID mà không tải toàn bộ target. Ví dụ `order.getCustomer().getId()` đôi khi không cần khởi tạo proxy vì ID đã có. Truy cập `getName()` thường cần tải target.

Đừng phụ thuộc quá mức vào hình thức runtime proxy: bytecode enhancement, inheritance và mapping có thể thay đổi nó. Dùng DTO/fetch plan để xác định dữ liệu caller cần thay vì để serializer tùy tiện truy cập proxy.

### 3.5. LazyInitializationException là lỗi vòng đời

~~~java
PurchaseOrder order;
try (EntityManager em = emf.createEntityManager()) {
    order = em.find(PurchaseOrder.class, 42L);
}

// Persistence context đã đóng.
String name = order.getCustomer().getName(); // Có thể lỗi.
~~~

Nếu `customer` chưa khởi tạo khi context đóng, Hibernate không còn Session để tải dữ liệu và có thể ném `LazyInitializationException`. Hãy tải dữ liệu cần thiết trong transaction rồi trả DTO; không mở Session vô hạn hoặc bật EAGER cho mọi quan hệ chỉ để né lỗi.

## 4. Fetch style JOIN: lấy association trong cùng câu SQL

### 4.1. Fetch join trong JPQL/HQL

~~~java
PurchaseOrder order = entityManager.createQuery(
        "select o from PurchaseOrder o " +
        "join fetch o.customer " +
        "where o.id = :id",
        PurchaseOrder.class
    )
    .setParameter("id", 42L)
    .getSingleResult();
~~~

SQL có thể có dạng:

~~~sql
select o.id, o.customer_id, o.status, c.id, c.name
from purchase_orders o
join customers c on c.id = o.customer_id
where o.id = ?;
~~~

Từ khóa `fetch` có ý nghĩa quan trọng: `join o.customer` dùng join để lọc/truy vấn theo quan hệ; `join fetch o.customer` yêu cầu nạp association vào entity graph kết quả.

Nếu quan hệ tùy chọn và cần giữ đơn hàng không có customer, dùng `left join fetch`:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery(
        "select o from PurchaseOrder o " +
        "left join fetch o.customer",
        PurchaseOrder.class
    )
    .getResultList();
~~~

### 4.2. Fetch join collection

~~~java
PurchaseOrder order = entityManager.createQuery(
        "select distinct o from PurchaseOrder o " +
        "left join fetch o.items " +
        "where o.id = :id",
        PurchaseOrder.class
    )
    .setParameter("id", 42L)
    .getSingleResult();
~~~

Một câu SQL join `purchase_orders` với `order_items`. Nếu đơn hàng có 5 item, result set có thể chứa 5 dòng cho cùng order ID. Hibernate dựng một root entity và collection từ các dòng đó. `distinct` thường diễn đạt ý định loại trùng root trong JPQL; Hibernate 6 cũng loại duplicate entity root trong các trường hợp fetch join theo semantics của nó. Tuy nhiên, **database vẫn phải xử lý các dòng join**.

### 4.3. Lợi ích và chi phí của JOIN

| Lợi ích | Chi phí/rủi ro |
| --- | --- |
| Ít round trip hơn cho association được fetch | Hàng SQL bị nhân lên khi join collection |
| Có thể tải graph cần thiết trong một query | Result set rộng, có thể lặp dữ liệu root |
| Fetch plan rõ tại query | Join nhiều collection có thể tạo Cartesian product |
| Phù hợp trang chi tiết với graph đã biết | Pagination trên collection fetch join phức tạp |
| Tránh SELECT phụ cho association đã join | Có thể gặp `MultipleBagFetchException` khi fetch nhiều bag |

### 4.4. Không fetch join nhiều collection lớn tùy tiện

Giả sử một order có 5 items và 4 notes. Fetch join cả hai collection trong cùng query có thể tạo khoảng 5 × 4 = 20 dòng cho một order, vì các tập con kết hợp thành tích Descartes. Khi số collection lớn, result set phình to nhanh.

Hibernate có thể từ chối fetch đồng thời nhiều bag-valued associations bằng `MultipleBagFetchException` vì không thể tái tạo chính xác bag semantics trong một số trường hợp. Chuyển List thành Set chỉ để né exception không phải lúc nào cũng đúng: nó thay đổi semantics và có thể che dữ liệu trùng hợp lệ.

Các lựa chọn thường tốt hơn:

- Fetch join một collection, batch fetch collection còn lại.
- Chia thành hai query trong cùng persistence context.
- Dùng DTO projection.
- Dùng collection type có semantics đúng domain, không đổi kiểu chỉ để né lỗi.

### 4.5. Pagination và collection fetch join

Không nên mặc định dùng `setFirstResult()`/`setMaxResults()` trên query fetch join collection. SQL pagination cắt **các dòng join**, không nhất thiết cắt đúng số root entity. Hibernate có thể phải áp pagination trong bộ nhớ hoặc cảnh báo/lỗi tùy cấu hình, gây tải quá nhiều dữ liệu.

Một pattern thường dùng:

1. Query trang ID của root entities với sort/filter ổn định.
2. Query thứ hai fetch association cần thiết cho tập ID đó.
3. Dựng kết quả theo thứ tự ID của trang đầu.

Hoặc dùng DTO projection/batch fetching nếu chỉ cần dữ liệu hiển thị. Kiểm tra SQL và execution plan với dữ liệu thật.

## 5. Fetch style SELECT: query riêng khi cần

SELECT fetching tải association bằng câu truy vấn khác với query lấy entity owner:

~~~text
Query 1: SELECT orders ...
Khi truy cập order.customer:
Query 2: SELECT customer WHERE id = ?
~~~

Với proxy LAZY, SELECT có thể chỉ phát khi caller truy cập. Với association EAGER không được join, SELECT phụ có thể phát ngay trong quá trình hoàn tất việc tải entity. Vì vậy **SELECT style không quyết định timing**: nó có thể dùng cùng LAZY hoặc EAGER tùy fetch plan.

### 5.1. N+1 query

~~~java
List<PurchaseOrder> orders = entityManager.createQuery(
        "select o from PurchaseOrder o",
        PurchaseOrder.class
    )
    .getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
~~~

Nếu có N đơn hàng và mỗi customer proxy cần khởi tạo riêng, có thể xảy ra:

~~~sql
select ... from purchase_orders;        -- 1 query
select ... from customers where id=?;   -- query phụ
select ... from customers where id=?;   -- query phụ
-- ...
~~~

Đây là N+1: một query lấy danh sách gốc và nhiều query phụ lấy association. Nếu nhiều order cùng tham chiếu customer đã có trong persistence context/cache, số query có thể ít hơn N; không nên dựa vào điều đó làm chiến lược.

### 5.2. SELECT có thể là lựa chọn tốt

SELECT không mặc định xấu. Nó phù hợp khi association không phải lúc nào cũng cần, dữ liệu liên quan lớn, chỉ một phần owner được truy cập, join sẽ nhân số dòng, hoặc batch fetching có thể gom nhiều lần tải. Chọn SELECT có chủ đích và đo round trip thay vì xem mọi SELECT phụ là lỗi.

## 6. Fetch style BATCH: gom nhiều proxy hoặc collection

Batch fetching giảm N+1 bằng cách gom ID của nhiều proxy/collection chưa khởi tạo vào một câu SELECT.

~~~java
import org.hibernate.annotations.BatchSize;

@Entity
@Table(name = "customers")
@BatchSize(size = 16)
public class Customer {
    @Id
    private Long id;
    private String name;
    protected Customer() {}
}
~~~

Khi ứng dụng tải 40 order rồi truy cập customer, Hibernate có thể tải các customer proxy đang chờ theo nhóm tối đa 16 ID, tùy batch queue, cache hit và giới hạn tham số DBMS.

SQL minh họa:

~~~sql
select c.id, c.name
from customers c
where c.id in (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
~~~

Nếu 40 customer khác nhau cần tải, có thể cần khoảng 3 batch query thay vì 40 SELECT riêng. Con số thực tế tùy association, proxy đang chờ, cache, parameter limit và cách truy cập.

### 6.1. Batch size ở entity và collection

`@BatchSize` có thể đặt trên entity để gom entity proxies hoặc trên collection mapping để gom collection owners:

~~~java
@OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
@BatchSize(size = 16)
private List<PurchaseOrder> orders = new ArrayList<>();
~~~

Cũng có thể đặt mặc định toàn cục:

~~~properties
hibernate.default_batch_fetch_size=16
~~~

Trong Spring Boot, property thường đặt dưới `spring.jpa.properties.hibernate.default_batch_fetch_size=16`. Chọn batch size theo workload, driver và DBMS parameter limit; batch quá lớn có thể tăng memory/result size.

### 6.2. Fetch batch khác JDBC DML batch

| Cơ chế | Mục đích | Ví dụ |
| --- | --- | --- |
| Fetch batch | Tải nhiều entity/collection trong một SELECT | `WHERE id IN (?, ?, ...)` |
| JDBC DML batch | Gom nhiều INSERT/UPDATE/DELETE | `hibernate.jdbc.batch_size` |
| Application batch | Xử lý nhiều phần tử theo chunk nghiệp vụ | Một transaction cho mỗi chunk |

`@BatchSize` là cơ chế đọc. Nó không tự bật JDBC insert batching.

### 6.3. BATCH vẫn có thể giữ timing LAZY

Association vẫn LAZY; khi lần đầu một proxy được khởi tạo, Hibernate có thể tải nhiều proxy đang chờ cùng lúc. Đây là ví dụ rõ: timing delayed, style BATCH.

## 7. Fetch style SUBSELECT: tải collection cho nhóm owner

SUBSELECT fetching chủ yếu áp dụng cho collection. Khi Hibernate tải một tập owner bằng query, rồi collection của một owner trong tập được khởi tạo, Hibernate có thể tải collection cho **toàn bộ nhóm owner** bằng một SELECT dựa trên truy vấn trước.

~~~java
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;

@OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<PurchaseOrder> orders = new ArrayList<>();
~~~

Ví dụ query 20 customer:

~~~java
List<Customer> customers = entityManager.createQuery(
        "select c from Customer c where c.name like :prefix",
        Customer.class
    )
    .setParameter("prefix", "A%")
    .getResultList();
~~~

Khi code truy cập `customers.get(0).getOrders()`, Hibernate có thể tải orders của nhóm customer đó bằng SQL dạng:

~~~sql
select o.*
from purchase_orders o
where o.customer_id in (
    select c.id
    from customers c
    where c.name like ?
);
~~~

Đây là SQL minh họa; Hibernate có thể render subselect khác theo query, filter và dialect. Ý nghĩa là một lần khởi tạo collection có thể tải collection cho cả nhóm owner, thay vì một SELECT cho từng customer.

### 7.1. Khi SUBSELECT hữu ích

- Ứng dụng tải một nhóm owner rồi duyệt collection của hầu hết owner.
- Collection có kích thước vừa phải.
- Muốn giảm N+1 mà không join collection làm nhân dòng root.
- Query ban đầu tạo tập owner có phạm vi rõ.

### 7.2. Khi cần thận trọng

- Nếu chỉ truy cập collection của một owner, subselect có thể tải thêm collection không cần.
- Nếu query owner trả tập rất lớn, kết quả collection có thể tốn memory và DB I/O.
- Filter, pagination, query shape và persistence context ảnh hưởng nhóm owner.
- Đây là Hibernate-specific fetch mode, không phải lựa chọn JPQL portable.

BATCH gom ID theo batch size; SUBSELECT dùng tập owner của query trước để tải collection liên quan.

## 8. Bảng tổng hợp fetch styles

| Fetch style | SQL thường gặp | Timing thường thấy | Điểm mạnh | Rủi ro |
| --- | --- | --- | --- | --- |
| JOIN | Một SELECT có JOIN | Immediate trong query | Ít round trip | Dòng trùng, Cartesian product, pagination |
| SELECT | SELECT riêng theo ID/owner | Immediate hoặc delayed | Chỉ tải khi cần nếu LAZY | N+1 |
| BATCH | SELECT với nhiều ID trong IN list | Thường delayed tới lần truy cập | Giảm N+1 mà tránh join lớn | Batch size và tải thừa |
| SUBSELECT | SELECT collection theo tập owner | Thường delayed | Một query cho nhóm collection | Có thể tải quá nhiều owner |

Không có fetch style tốt nhất cho mọi quan hệ. Trang chi tiết một order có thể hợp JOIN; danh sách order chỉ cần trạng thái có thể không cần customer; trang customer với nhiều collection có thể hợp BATCH/SUBSELECT.

## 9. JPA FetchType và Hibernate FetchMode

### 9.1. JPA `FetchType`

`jakarta.persistence.FetchType` gồm EAGER và LAZY. EAGER yêu cầu dữ liệu association sẵn sàng theo contract; LAZY cho phép provider trì hoãn. JPA không có annotation chuẩn để yêu cầu cụ thể SELECT, BATCH hoặc SUBSELECT.

### 9.2. Hibernate `@Fetch`

Hibernate cung cấp `org.hibernate.annotations.Fetch` và `FetchMode`:

~~~java
@Fetch(FetchMode.SELECT)
@OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
private List<PurchaseOrder> orders = new ArrayList<>();
~~~

Các mode thường dùng:

- `FetchMode.SELECT`: tải bằng SELECT riêng.
- `FetchMode.JOIN`: dùng JOIN; thường kéo theo immediate/eager fetch cho association.
- `FetchMode.SUBSELECT`: tải collection cho nhóm owner bằng subselect.

`@Fetch` là Hibernate-specific. Cấu hình mapping-level JOIN có thể làm association tải sớm dù field khai báo LAZY; hãy kiểm tra semantics của đúng phiên bản. Với nhu cầu riêng của một query, fetch join hoặc EntityGraph thường diễn đạt ý định rõ hơn việc đổi mapping mặc định.

### 9.3. `@BatchSize` không phải FetchType

`@BatchSize` điều chỉnh số entity/collection được gom khi Hibernate thực hiện batch fetch. Nó không tự chuyển association từ EAGER thành LAZY hay ngược lại.

## 10. Entity Graph: dữ liệu cần cho một use case

JPA Entity Graph cho phép chọn association cần fetch theo một lần query mà không phải thay fetch type mặc định của entity.

~~~java
@Entity
@NamedEntityGraph(
    name = "PurchaseOrder.withCustomer",
    attributeNodes = @NamedAttributeNode("customer")
)
public class PurchaseOrder {
    // Các thuộc tính khác.
}
~~~

Sử dụng:

~~~java
EntityGraph<?> graph = entityManager.getEntityGraph(
        "PurchaseOrder.withCustomer"
);

PurchaseOrder order = entityManager.find(
        PurchaseOrder.class,
        42L,
        Map.of("jakarta.persistence.fetchgraph", graph)
);
~~~

Các import còn thiếu trong snippet: `jakarta.persistence.EntityGraph`, `NamedEntityGraph`, `NamedAttributeNode` và `java.util.Map`.

Hai hint chính:

| Hint | Ngữ nghĩa khái quát |
| --- | --- |
| `jakarta.persistence.fetchgraph` | Thuộc tính trong graph được xem là eager cho lần fetch; thuộc tính ngoài graph được xem là lazy theo fetch graph semantics |
| `jakarta.persistence.loadgraph` | Thuộc tính trong graph được fetch eager; thuộc tính ngoài graph giữ fetch semantics mặc định |

EntityGraph xác định **dữ liệu cần fetch**, provider chọn JOIN/SELECT hoặc cách phù hợp; nó không bắt buộc một SQL JOIN duy nhất. Subgraph có thể mô tả đường association lồng nhau. Graph sâu vẫn có thể tạo join lớn, SELECT phụ hoặc Cartesian product.

## 11. Chọn công cụ theo truy vấn

| Công cụ | Phạm vi | Khi phù hợp |
| --- | --- | --- |
| JPQL/HQL `join fetch` | Một query cụ thể | Cần tải association cùng kết quả |
| JPA EntityGraph | Một lần find/query | Muốn tách fetch plan khỏi JPQL và mapping |
| `@BatchSize`/default batch size | Mapping/cấu hình Hibernate | Nhiều proxy hoặc collection lazy được truy cập theo nhóm |
| `@Fetch(SUBSELECT)` | Collection mapping | Tải collection cho tập owner vừa query |
| `@Fetch(FetchMode.JOIN)` | Mapping association | Quan hệ thường xuyên cần immediate join |
| DTO projection | Một query cụ thể | Chỉ cần field cho API/report, không cần managed graph |

Không cần chọn duy nhất một công cụ cho toàn hệ thống. Ví dụ: mapping mặc định LAZY, query fetch join customer, collection items batch fetch khi cần. Hãy tránh cấu hình chồng chéo khó dự đoán và giữ fetch plan dễ hiểu theo use case.

## 12. N+1 và các cách xử lý

Giả sử trang hiển thị 100 đơn hàng, customer name và item count:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery(
        "select o from PurchaseOrder o order by o.id",
        PurchaseOrder.class
    )
    .getResultList();

for (PurchaseOrder order : orders) {
    String customerName = order.getCustomer().getName();
    int itemCount = order.getItems().size();
}
~~~

Có thể phát sinh một query lấy orders, nhiều query lấy customers và nhiều query lấy items. Số thực tế tùy identity map, cache và batch settings.

### 12.1. Fetch join to-one

~~~java
List<PurchaseOrder> orders = entityManager.createQuery(
        "select o from PurchaseOrder o " +
        "join fetch o.customer order by o.id",
        PurchaseOrder.class
    )
    .getResultList();
~~~

Phù hợp nếu mọi order trên trang đều cần customer. To-one join thường ít làm nhân dòng hơn collection join.

### 12.2. Batch fetch collection

Giữ items LAZY và thêm `@BatchSize` trên collection hoặc cấu hình mặc định. Khi vòng lặp truy cập items, Hibernate gom owner IDs thành nhóm, tránh join collection làm nhân dòng root.

### 12.3. DTO projection

Nếu chỉ cần ID, customer name và số item, không cần hydrate entity graph:

~~~java
public record OrderRow(
        Long orderId,
        String customerName,
        Long itemCount
) {}
~~~

~~~java
List<OrderRow> rows = entityManager.createQuery(
        "select new com.example.api.OrderRow(" +
        "o.id, c.name, count(i)) " +
        "from PurchaseOrder o " +
        "join o.customer c " +
        "left join o.items i " +
        "group by o.id, c.name " +
        "order by o.id",
        OrderRow.class
    )
    .getResultList();
~~~

Tên package `com.example.api.OrderRow` là giả định, cần thay theo dự án. Projection trả đúng dữ liệu màn hình và tránh quản lý entity state không cần thiết.

### 12.4. Query collection riêng cho một trang ID

Với pagination, có thể lấy trang order IDs trước rồi query items cho các ID đó:

~~~java
List<Long> ids = entityManager.createQuery(
        "select o.id from PurchaseOrder o order by o.id",
        Long.class
    )
    .setFirstResult(offset)
    .setMaxResults(pageSize)
    .getResultList();

List<OrderItem> items = entityManager.createQuery(
        "select i from OrderItem i where i.order.id in :ids",
        OrderItem.class
    )
    .setParameter("ids", ids)
    .getResultList();
~~~

Sau đó group items theo order ID hoặc dùng batch fetching. Xử lý trang rỗng và giữ thứ tự root theo danh sách ID ban đầu nếu query thứ hai không có cùng ordering.

## 13. To-one và to-many có đặc điểm khác nhau

### 13.1. To-one

`@ManyToOne` và `@OneToOne` thường trả về một target. JOIN fetch thường hiệu quả nếu chỉ có một vài to-one cần thiết. Nhưng EAGER mặc định của to-one có thể tạo SELECT phụ khi query root không join, nên thường khai báo LAZY và fetch theo use case.

Một số one-to-one inverse khó lazy vì Hibernate cần xác định target có tồn tại khi chưa có FK trên phía owner. Bytecode enhancement, shared primary key và mapping cụ thể có thể ảnh hưởng; không giả định LAZY luôn là proxy đơn giản.

### 13.2. To-many

`@OneToMany`/`@ManyToMany` có thể trả về rất nhiều hàng. JOIN fetch có nguy cơ nhân số dòng, làm pagination khó và tải collection lớn ngoài ý muốn. BATCH/SUBSELECT thường đáng cân nhắc khi caller cần collection của nhiều owner.

Không đặt EAGER cho mọi collection để né LazyInitializationException: nó có thể tải toàn bộ graph trong mọi use case.

### 13.3. Multiple bag fetch

Hibernate có thể báo `MultipleBagFetchException` khi một query fetch đồng thời nhiều bag collections. Đây là giới hạn liên quan bag semantics và việc kết hợp nhiều collection result sets. Có thể fetch một collection, batch collection còn lại, chia query hoặc dùng projection. Không đổi List thành Set chỉ để né lỗi nếu semantics domain cho phép trùng phần tử.

## 14. Fetching và cache: dữ liệu được lấy từ đâu?

Fetch style nói về cách Hibernate tổ chức tải association; câu SQL có thực sự tới DB còn phụ thuộc cache:

- **First-level cache/persistence context:** entity identity đã managed thì Hibernate dùng instance hiện có.
- **Second-level cache:** nếu bật, entity/collection state có thể được lấy từ cache provider tùy mapping và cache mode.
- **Query cache:** cache thông tin kết quả query theo cấu hình; không đồng nghĩa cache một object graph dùng chung.
- **Database buffer/cache:** DBMS có thể phục vụ SQL từ bộ nhớ nội bộ, nhưng JDBC/network round trip vẫn tồn tại.

Cache hit có thể giảm SQL nhưng không làm fetch timing và fetch plan trở nên không quan trọng. Khi đo, dùng session mới và kiểm soát cache state; không để first-level cache làm sai số.

## 15. Chọn fetch plan theo use case

| Use case | Fetch plan thường phù hợp | Lý do |
| --- | --- | --- |
| Danh sách order chỉ hiển thị ID/trạng thái | DTO projection hoặc query root fields | Không cần customer/items |
| Trang order detail cần customer và vài item | Fetch join to-one + collection có giới hạn hoặc query riêng | Graph cụ thể, tránh tải mọi collection |
| Danh sách customer rồi duyệt orders của hầu hết customer | Batch hoặc subselect collection | Giảm N+1 mà không join toàn collection |
| Export dữ liệu lớn theo chunk | DTO/stream phù hợp, context scope có kiểm soát | Tránh giữ entity graph lớn |
| Cập nhật một order theo ID | Load entity cần thiết, quan hệ khác giữ lazy | Tránh tải dữ liệu không dùng |
| Báo cáo tổng hợp | Aggregate query/DTO projection | DB tính toán gần dữ liệu |
| Hiển thị customer name cho mọi order | Fetch join to-one hoặc projection | Tránh SELECT tuần tự |
| Nhiều collection lớn | Query tách biệt hoặc batch | Tránh Cartesian product/bag-fetch issue |

Một entity mapping có thể được dùng bởi nhiều use case. Đừng chọn EAGER/JOIN toàn cục chỉ vì một màn hình cần nhiều dữ liệu. Hãy để mapping mặc định tối giản và dùng query-specific fetch plan.

## 16. Quan sát SQL và đo hiệu năng

### 16.1. SQL logging

Trong Hibernate 6, logger `org.hibernate.SQL` ở mức DEBUG cho thấy SQL; `org.hibernate.orm.jdbc.bind` ở mức TRACE có thể cho thấy bind parameters nếu thật sự cần. Tên logger/cách cấu hình phụ thuộc logging framework. Không bật bind trace rộng rãi ở production nếu tham số có dữ liệu cá nhân hoặc bí mật.

~~~properties
# Ví dụ tên logger, cấu hình qua Logback/Log4j hoặc framework:
# org.hibernate.SQL = DEBUG
# org.hibernate.orm.jdbc.bind = TRACE
~~~

### 16.2. Đo nhiều hơn số query

Khi so sánh SELECT/JOIN/BATCH/SUBSELECT, ghi nhận:

- Số statement SQL trên một request/unit of work.
- Số dòng result set và số entity/collection thực sự cần.
- Thời gian DB, JDBC và tổng latency.
- Số cột, kích thước payload và lượng dữ liệu tải thừa.
- Query plan/index của DBMS.
- Cache hit/miss, session mới hay session đã dùng.
- Kích thước collection và phân bố association thực tế.

Một query duy nhất không luôn nhanh hơn năm query nhỏ. JOIN có thể tạo hàng triệu dòng lặp; nhiều SELECT được gom batch đôi khi tốt hơn. Ngược lại, một to-one join nhỏ thường rẻ hơn hàng chục SELECT tuần tự.

### 16.3. Hibernate statistics

Có thể bật statistics trong môi trường phù hợp:

~~~properties
hibernate.generate_statistics=true
~~~

Statistics hỗ trợ quan sát query/entity/collection fetch và cache metrics tùy phiên bản. Nó có overhead; không bật tùy tiện cho mọi production workload. Đối chiếu SQL logging với DB monitoring để có bức tranh đầy đủ.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| EAGER nhưng vẫn có nhiều SELECT | EAGER yêu cầu timing, không bắt buộc JOIN | Fetch join/entity graph hoặc batch |
| LAZY nhưng query đã tải quan hệ | Fetch join, entity graph hoặc mapping JOIN | Xem fetch plan lần tải cụ thể |
| LazyInitializationException | Truy cập association chưa tải sau khi context đóng | Tải trong transaction và trả DTO |
| N+1 query | Nhiều proxy/collection dùng SELECT riêng | Fetch join to-one, batch/subselect, projection |
| Nhiều dòng trùng root | Join collection | Giảm số collection join hoặc query riêng |
| Pagination tải quá nhiều dữ liệu | Pagination trên collection fetch join | Page IDs trước rồi fetch graph |
| MultipleBagFetchException | Fetch nhiều bag cùng query | Chia query, batch hoặc projection |
| Batch không giảm query | Không có proxy chờ, mapping/cache hoặc batch config không phù hợp | Xem SQL và batch settings |
| SUBSELECT tải quá nhiều collection | Tập owner query ban đầu quá rộng | Batch size hoặc query collection có giới hạn |
| Basic LAZY không hoạt động | Thiếu enhancement hoặc provider không hỗ trợ | Kiểm tra enhancer/version |
| EAGER toàn cục làm API nặng | Graph mặc định tải dữ liệu không cần | LAZY mapping và fetch plan theo use case |

## 18. Quy trình chọn fetching strategy

1. **Xác định dữ liệu caller cần.** Field nào, association nào, có cần toàn bộ collection không?
2. **Chọn timing mặc định.** Với association lớn/ít dùng, ưu tiên LAZY; dùng EAGER khi dữ liệu phải luôn sẵn sàng và đã đo hệ quả.
3. **Chọn style theo hình dạng dữ liệu.** To-one nhỏ thường hợp JOIN; collection lớn có thể hợp BATCH/SUBSELECT hoặc query riêng.
4. **Đặt fetch plan tại query/use case.** Dùng fetch join hoặc EntityGraph, tránh thay mapping toàn cục chỉ cho một màn hình.
5. **Kiểm tra N+1 và Cartesian product.** Đếm SQL, xem result rows và số association được tải.
6. **Xem pagination.** Không fetch join collection lớn rồi áp offset/limit mà chưa hiểu provider thực thi thế nào.
7. **Kiểm soát cache và persistence context.** Đo trong điều kiện cache phù hợp.
8. **Đo trên DBMS thật.** So sánh latency, I/O, row count và query plan.
9. **Giữ transaction boundary hợp lý.** Tải dữ liệu cần cho DTO trong transaction; không dựa vào lazy loading ngoài session.
10. **Theo dõi production.** Slow query, query count, batch size, memory và cache metrics thay đổi theo dữ liệu thật.

## 19. Bài tập tự kiểm tra

1. `FetchType.EAGER` có bắt buộc Hibernate dùng JOIN không? Nếu không, Hibernate có thể dùng cách nào?
2. Association LAZY được truy cập lần đầu. Vì sao timing là delayed nhưng style vẫn có thể là SELECT?
3. Tải 100 order rồi truy cập customer của từng order có thể tạo N+1 như thế nào? Cách nào giảm query mà vẫn giữ LAZY?
4. `@BatchSize(size = 16)` khác `hibernate.jdbc.batch_size=16` thế nào?
5. Fetch join hai collection lớn có thể tạo result set phình lên ra sao?
6. Vì sao pagination trên collection fetch join phức tạp hơn pagination trên root?
7. `FetchMode.SUBSELECT` gom collection theo phạm vi nào?
8. EntityGraph quyết định SQL JOIN cụ thể hay mô tả graph cần fetch?
9. Vì sao `@Basic(fetch = FetchType.LAZY)` có thể cần bytecode enhancement?
10. Khi API chỉ cần customer name và item count, vì sao DTO projection có thể tốt hơn hydrate toàn bộ graph?

**Gợi ý:** (1) không, có thể SELECT phụ; (2) truy cập kích hoạt SELECT; (3) một query gốc cộng query phụ, dùng fetch join to-one hoặc batch; (4) fetch batch là SELECT nhiều ID, JDBC batch là gom DML; (5) tích số phần tử của các collection; (6) limit cắt row join chứ không phải root; (7) tập owner của query trước; (8) graph mô tả dữ liệu, provider chọn cách; (9) cần intercept access basic field; (10) chỉ tải cột cần dùng.

## 20. Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide – Fetching](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#fetching): fetch timing, fetch styles, batch fetching, subselect và fetch profiles.
- [Hibernate ORM 6.6 HQL Guide](https://docs.hibernate.org/orm/6.6/querylanguage/html_single/Hibernate_Query_Language.html): join fetch và truy vấn association.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): FetchType, EntityGraph, fetch/load graph hints và query semantics.
- [Hibernate ORM Documentation](https://hibernate.org/orm/documentation/): chọn user guide và migration guide theo phiên bản runtime.

**Nguyên tắc cần nhớ:** *thời điểm tải* và *cách lấy dữ liệu* là hai chiều riêng. EAGER/LAZY trả lời dữ liệu cần sẵn sàng khi nào; JOIN/SELECT/BATCH/SUBSELECT mô tả cách Hibernate lấy dữ liệu. Chọn timing theo vòng đời và nhu cầu nghiệp vụ, chọn style theo hình dạng truy vấn và kích thước quan hệ, rồi xác nhận bằng SQL, số dòng và query plan.
