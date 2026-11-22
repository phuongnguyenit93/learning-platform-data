# Phân biệt fetch graph và load graph

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Nhóm kiến thức:** Kế hoạch tải

Một trong những câu hỏi khó nhất khi tối ưu truy vấn JPA là: **Khi tải một entity, những quan hệ nào nên được nạp ngay, những quan hệ nào chỉ nạp khi thực sự cần?** Chọn không đúng có thể làm phát sinh hàng trăm câu SELECT (N+1), tạo dữ liệu dư thừa qua JOIN, tiêu tốn bộ nhớ hoặc gây lỗi truy cập lazy association ngoài persistence context.

**Entity graph** cho phép mô tả một **kế hoạch tải dữ liệu (fetch plan)** theo từng use case. Trong JPA, cùng một entity graph có thể được sử dụng với hai ngữ nghĩa khác nhau:

- **Fetch graph** — dùng hint **jakarta.persistence.fetchgraph**: những thuộc tính có trong graph được xem như yêu cầu tải sớm; những thuộc tính không có trong graph được **xem như LAZY** theo ngữ nghĩa graph.
- **Load graph** — dùng hint **jakarta.persistence.loadgraph**: những thuộc tính có trong graph được xem như yêu cầu tải sớm; những thuộc tính không có trong graph vẫn theo **fetch type được khai báo trong mapping**, chẳng hạn EAGER hay LAZY.

Điểm phân biệt không nằm ở hình dạng Java object của graph mà ở **quy tắc áp dụng cho thuộc tính không được liệt kê**. Cũng cần nhớ: JPA cho phép provider tải **nhiều trạng thái hơn** graph yêu cầu. Vì vậy fetch graph **không bảo đảm** mọi thuộc tính không khai báo sẽ chắc chắn chưa được tải, và entity graph **không bắt buộc** provider phải sử dụng một câu SQL JOIN duy nhất.

Ví dụ:

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);
graph.addAttributeNodes("lines");

// Cùng graph, nhưng cách hiểu thuộc tính không liệt kê khác nhau.
TypedQuery<PurchaseOrder> query = em.createQuery(
    "select o from PurchaseOrder o where o.id = :id",
    PurchaseOrder.class
);

query.setParameter("id", orderId);
query.setHint("jakarta.persistence.fetchgraph", graph);
PurchaseOrder order = query.getSingleResult();
~~~

Nếu thay hint bằng **jakarta.persistence.loadgraph**, các association EAGER có sẵn trong mapping tiếp tục được yêu cầu tải sớm, ngay cả khi chúng không nằm trong graph.

Bài học giải thích định nghĩa chính xác, cách khai báo và áp dụng graph bằng annotation hoặc Java API, những khác biệt với JPQL JOIN FETCH, các trường hợp Spring Data JPA, kiểm thử và thực hành tối ưu truy vấn.

## 1. Vì sao cần kế hoạch tải?

Một entity thường liên kết nhiều đối tượng:

~~~text
PurchaseOrder
    |
    +-- customer (ManyToOne)
    |       |
    |       +-- preferredAddress (ManyToOne)
    |
    +-- invoice (OneToOne)
    |
    +-- lines (OneToMany)
    |       |
    |       +-- product (ManyToOne)
    |
    +-- attachments (OneToMany)
~~~

Màn hình quản lý đơn hàng có thể cần:
- **Danh sách**: mã đơn, trạng thái, tên khách hàng;
- **Chi tiết**: thông tin khách hàng, dòng hàng, tên sản phẩm, hóa đơn;
- **Xuất file**: các dòng hàng và một số thông tin thống kê;
- **Cập nhật trạng thái**: chỉ cần đơn hàng, không cần tất cả quan hệ.

Nếu mọi quan hệ đều khai báo EAGER, chỉ mở danh sách 100 đơn có thể kéo theo lượng dữ liệu rất lớn. Nếu mọi quan hệ LAZY nhưng service lặp qua từng đơn để đọc customer/lines, có thể phát sinh N+1 SELECT.

### 1.1. N+1 là gì?

Giả sử câu đầu tải 50 PurchaseOrder:

~~~sql
SELECT ...
FROM purchase_orders
WHERE status = 'CREATED';
~~~

Rồi Java:

~~~java
for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
~~~

Nếu customer chưa được tải và provider phải truy vấn riêng cho mỗi order, ứng dụng có thể thực hiện một SELECT tìm orders cộng thêm nhiều SELECT tìm customers. **N+1** là tên của dạng phát sinh query theo số phần tử như vậy, không nhất thiết chính xác 51 lần trong mọi môi trường (vì first-level cache, second-level cache, batch fetching hoặc nhiều orders cùng customer có thể giảm số câu).

### 1.2. EAGER không đồng nghĩa JOIN FETCH

Mapping:

~~~java
@ManyToOne(fetch = FetchType.EAGER)
private Customer customer;
~~~

nói rằng association phải sẵn sàng theo eager fetching requirement. Nó **không cam kết** mọi truy vấn PurchaseOrder sẽ được biến thành một SQL SELECT với LEFT JOIN customer. Provider có thể thực hiện truy vấn phụ để bảo đảm eager state, tùy loại query, cache, mapping và cấu hình.

Do đó:
- Có thể vẫn gặp nhiều câu SELECT với EAGER association;
- Chuyển bừa mọi association sang EAGER không phải giải pháp tối ưu;
- Fetch plan cần được quyết định theo trường hợp sử dụng.

### 1.3. Entity graph cung cấp điều gì?

Entity graph mô tả các **attribute nodes** cần tải, có thể thêm **subgraph** cho thuộc tính của entity liên kết.

Ví dụ kế hoạch cho màn hình chi tiết:

~~~text
PurchaseOrder graph
    +-- customer
    +-- invoice
    +-- lines
           +-- product
~~~

Graph này trả lời câu hỏi: *Những thành phần nào của entity graph cần được yêu cầu tải sớm?*

Nó **không** tự trả lời:
- Cần bao nhiêu rows ở kết quả?
- WHERE lọc những đơn nào?
- Có bao nhiêu SQL statements?
- Quan hệ được JOIN hay tải bằng SELECT phụ?
- API cần trả DTO nào?
- Người dùng có quyền xem đơn không?

Những câu hỏi đó do query, transaction, provider và thiết kế ứng dụng quyết định.

## 2. Mô hình ví dụ nhất quán

Các đoạn code sử dụng Jakarta Persistence (namespace **jakarta.persistence**) với một hệ thống đơn hàng. Những ví dụ cần chạy trong dự án đã cấu hình JPA provider (ví dụ Hibernate) và một cơ sở dữ liệu phù hợp.

### 2.1. Customer

~~~java
package com.example.orders;

import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, unique = true)
    private String email;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "preferred_address_id")
    private Address preferredAddress;

    protected Customer() {}

    public Long getId() { return id; }
    public String getName() { return name; }
    public String getEmail() { return email; }
    public Address getPreferredAddress() {
        return preferredAddress;
    }
}
~~~

### 2.2. Address và Product

~~~java
@Entity
@Table(name = "addresses")
public class Address {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String city;
    private String street;

    protected Address() {}

    public Long getId() { return id; }
    public String getCity() { return city; }
    public String getStreet() { return street; }
}
~~~

~~~java
@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    protected Product() {}

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
}
~~~

Các entity được trình bày thành các code block độc lập; khi triển khai Java, mỗi public class cần đặt trong file riêng theo quy tắc ngôn ngữ.

### 2.3. Invoice

~~~java
@Entity
@Table(name = "invoices")
public class Invoice {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String invoiceNumber;

    protected Invoice() {}

    public Long getId() { return id; }
    public String getInvoiceNumber() {
        return invoiceNumber;
    }
}
~~~

### 2.4. PurchaseOrder và OrderLine

~~~java
package com.example.orders;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String orderNumber;

    @Column(nullable = false)
    private String status;

    @Column(nullable = false)
    private Instant createdAt;

    // ManyToOne có default EAGER; khai báo để nhấn mạnh.
    @ManyToOne(fetch = FetchType.EAGER, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    // OneToOne có default EAGER; association có thể nullable.
    @OneToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "invoice_id")
    private Invoice invoice;

    // OneToMany mặc định LAZY; khai báo để đọc rõ ý định.
    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderAttachment> attachments = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public String getOrderNumber() { return orderNumber; }
    public String getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
    public Customer getCustomer() { return customer; }
    public Invoice getInvoice() { return invoice; }
    public List<OrderLine> getLines() { return lines; }
    public List<OrderAttachment> getAttachments() {
        return attachments;
    }
}
~~~

~~~java
@Entity
@Table(name = "order_lines")
public class OrderLine {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {}

    public Long getId() { return id; }
    public Product getProduct() { return product; }
    public int getQuantity() { return quantity; }
}
~~~

~~~java
@Entity
@Table(name = "order_attachments")
public class OrderAttachment {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    private String filename;

    protected OrderAttachment() {}

    public Long getId() { return id; }
    public String getFilename() { return filename; }
}
~~~

Các khai báo thể hiện ví dụ tối thiểu. Trong ứng dụng thực tế cần thêm constructors/domain methods, các ràng buộc dữ liệu và quản lý cả hai phía của quan hệ hai chiều. Đối với bài học về fetch plan, điểm chính là **customer/invoice EAGER**, còn **lines/attachments LAZY**.

### 2.5. Dữ liệu mẫu

Giả sử có 3 đơn hàng:

| Đơn | Khách hàng | Invoice | Số dòng hàng | Số attachment |
|---|---|---|---:|---:|
| PO-001 | An | INV-001 | 2 | 1 |
| PO-002 | Bình | Chưa có | 3 | 0 |
| PO-003 | An | INV-003 | 1 | 2 |

Câu truy vấn:

~~~java
select o from PurchaseOrder o
~~~

trả **3 PurchaseOrder**, còn các quan hệ liên quan được tải thế nào phụ thuộc mapping, fetch plan, provider, persistence context/cache và đường thực thi.

## 3. Mặc định JPA: FetchType.EAGER và FetchType.LAZY

Trước khi phân biệt hai loại graph cần nắm **static fetch plan** được định nghĩa tại mapping.

| Mapping | Mặc định theo JPA | Ý nghĩa |
|---|---|---|
| @Basic | EAGER | Thuộc tính cơ bản được yêu cầu eager |
| @ManyToOne | EAGER | Quan hệ nhiều-một được yêu cầu eager |
| @OneToOne | EAGER | Quan hệ một-một được yêu cầu eager |
| @OneToMany | LAZY | Collection được yêu cầu lazy |
| @ManyToMany | LAZY | Collection được yêu cầu lazy |
| @ElementCollection | LAZY | Collection giá trị được yêu cầu lazy |

**EAGER** được coi là yêu cầu provider phải có trạng thái được tải theo semantics; **LAZY** là gợi ý/hint cho provider rằng có thể hoãn việc tải đến lúc truy cập. Provider được phép tải sớm hơn để đáp ứng những hạn chế mapping hoặc tối ưu.

### 3.1. Ví dụ trạng thái theo mapping

Trong PurchaseOrder:

~~~java
@ManyToOne(fetch = FetchType.EAGER)
private Customer customer;

@OneToOne(fetch = FetchType.EAGER)
private Invoice invoice;

@OneToMany(fetch = FetchType.LAZY, mappedBy = "order")
private List<OrderLine> lines;
~~~

Theo static plan:
- Customer EAGER;
- Invoice EAGER;
- Lines LAZY.

Nếu không có entity graph nào, provider phải thực hiện fetch strategy theo yêu cầu mapping và các cơ chế áp dụng khác.

### 3.2. EAGER không có nghĩa tất cả liên kết sâu đều được tải

Ngay cả khi PurchaseOrder.customer EAGER, Customer.preferredAddress được mapping LAZY. Không thể suy ra rằng địa chỉ ưu tiên đã được tải chỉ vì customer đã được tải.

~~~text
PurchaseOrder.customer             EAGER
Customer.preferredAddress          LAZY
PurchaseOrder.lines                LAZY
OrderLine.product                  LAZY
~~~

Fetch plan nên được mô tả theo **từng cấp quan hệ** thay vì nói “Order đã EAGER nên toàn bộ graph đã có”.

### 3.3. Hạn chế thực thi của LAZY

Trong một số provider/configurations:
- Quan hệ to-one LAZY có thể dùng proxy hoặc bytecode enhancement;
- Quan hệ inverse @OneToOne có thể khó trì hoãn hơn;
- @Basic(fetch=LAZY) có thể cần bytecode enhancement;
- Provider có quyền tải thêm state.

Vì thế **FetchType.LAZY là dự kiến fetch behavior**, không phải cam kết SQL chắc chắn sẽ không tải. Một ứng dụng không nên dựa vào thuộc tính chưa tải để bảo mật; mọi bí mật phải được bảo vệ qua authorization/DTO/API contract.

## 4. Entity graph là gì?

**EntityGraph<T>** biểu diễn một tập những attribute nodes của entity type T mà ứng dụng muốn tải theo một kế hoạch.

~~~text
EntityGraph<PurchaseOrder>
    |
    +-- attributeNode("customer")
    +-- attributeNode("lines")
             |
             +-- subgraph("product")
~~~

Entity graph có hai nguồn chính:

1. **Named entity graph**: khai báo bằng annotation, truy xuất bằng logical name.
2. **Dynamic entity graph**: xây ở runtime bằng EntityManager.createEntityGraph và thêm attribute nodes/subgraphs.

Entity graph còn có thể có **subgraph** cho liên kết lồng nhau, không giới hạn ở một tầng quan hệ.

### 4.1. Graph chỉ liệt kê fetch requirements

Graph không chứa WHERE. Ví dụ:

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("lines");
~~~

định nghĩa điều cần tải đối với PurchaseOrder được chọn, nhưng **không có nghĩa chỉ chọn Orders có Lines**. Muốn lọc orders theo status, phải dùng JPQL/Criteria predicates:

~~~java
select o
from PurchaseOrder o
where o.status = :status
~~~

Graph và WHERE giải quyết hai bài toán khác nhau.

### 4.2. Graph không đổi mapping entity

Lời gọi:

~~~java
graph.addAttributeNodes("lines");
~~~

không sửa annotation @OneToMany(fetch=LAZY) thành EAGER vĩnh viễn. Nó chỉ mô tả fetch plan cho thao tác đọc sử dụng graph.

Nhờ vậy cùng một PurchaseOrder có thể có:
- Graph cho list page;
- Graph cho detail page;
- Graph cho export;
- Graph cho job kiểm toán.

Không phải chỉnh toàn bộ mapping cho một endpoint đặc biệt.

### 4.3. Graph không phải một DTO projection

Graph trả entity và những relationships được tải theo graph semantics. Nếu một endpoint chỉ cần orderNumber và customerName, dùng DTO projection đôi khi phù hợp hơn vì graph vẫn là entity-oriented fetching.

Ví dụ:

~~~java
select new com.example.orders.dto.OrderSummary(
    o.id, o.orderNumber, c.name
)
from PurchaseOrder o
join o.customer c
where o.status = :status
~~~

DTO projection giải quyết **hình dạng dữ liệu đầu ra**; EntityGraph giải quyết **kế hoạch tải entity**. Hai cơ chế có thể cùng tồn tại trong một hệ thống, nhưng không nên coi chúng tương đương.

## 5. Fetch graph: thuộc tính không khai báo được xem như LAZY

Một **fetch graph** được áp dụng bằng hint:

~~~java
"jakarta.persistence.fetchgraph"
~~~

Quy tắc theo JPA: những thuộc tính được graph xác định là cần fetch sẽ được yêu cầu **EAGER**; các thuộc tính không nằm trong graph được **xem như LAZY** theo fetch graph semantics.

### 5.1. Ví dụ fetch graph chỉ có lines

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("lines");

TypedQuery<PurchaseOrder> query = em.createQuery(
    """
    select o
    from PurchaseOrder o
    where o.id = :id
    """,
    PurchaseOrder.class
);

query.setParameter("id", orderId);
query.setHint("jakarta.persistence.fetchgraph", graph);

PurchaseOrder order = query.getSingleResult();
~~~

Theo mapping ở phần 2:

| Thuộc tính | Static fetch type | Có trong fetch graph? | Ngữ nghĩa fetch graph |
|---|---|---|---|
| PurchaseOrder.lines | LAZY | Có | Yêu cầu tải sớm |
| PurchaseOrder.customer | EAGER | Không | Xem như LAZY |
| PurchaseOrder.invoice | EAGER | Không | Xem như LAZY |
| PurchaseOrder.attachments | LAZY | Không | Xem như LAZY |

Điểm đáng nhớ: **customer/invoice vốn EAGER trong mapping nhưng không có trong fetch graph**, nên đối với request này chúng được **xem như LAZY** theo fetch graph semantics.

Tuy nhiên, từ quy tắc trên **không được kết luận** provider bắt buộc giữ customer/invoice ở trạng thái uninitialized. Đặc tả cho phép provider tải thêm state không được graph yêu cầu. Một số provider cũng có giới hạn trong việc trì hoãn các EAGER associations nhất định.

### 5.2. Vì sao fetch graph hữu ích?

Fetch graph cho phép màn hình xử lý **một bộ quan hệ được liệt kê rõ** mà không cần thừa hưởng tất cả EAGER associations đã khai báo trong model.

Ví dụ:
- Trang export dòng hàng chỉ cần Order cùng Lines;
- Trang kiểm tra dữ liệu muốn nạp customer nhưng không cần invoice;
- Một endpoint nội bộ đã có EAGER mặc định quá rộng, muốn thử thu hẹp fetch plan.

Đó là lợi ích về **ý định tải dữ liệu**, nhưng kết quả thực tế phải được xác minh trên provider và mapping cụ thể.

### 5.3. Fetch graph không xóa hay làm NULL association

Nếu customer không có trong graph:

~~~java
PurchaseOrder order = ...;
Customer customer = order.getCustomer();
~~~

association **vẫn tồn tại theo dữ liệu database**. Nó không bị set null và không bị xóa liên kết. Nếu chưa tải, việc truy cập có thể kích hoạt lazy loading khi persistence context còn hoạt động.

Nếu session/context đã đóng, hành vi truy cập quan hệ chưa tải phụ thuộc provider và có thể gây lỗi lazy initialization. Không sử dụng fetch graph như cách cố tình bỏ dữ liệu nhạy cảm khỏi entity object khi người dùng vẫn có thể đi qua association.

### 5.4. Các thuộc tính cơ bản không nhất thiết là các SQL cột bị loại

Fetch graph điều khiển fetch semantics; nó **không phải SELECT-list projection**. Dù chỉ liệt kê lines, provider vẫn có thể select các basic columns của PurchaseOrder để tạo entity hợp lệ.

Đừng đọc tên hint “fetchgraph” rồi tin rằng SQL chỉ chứa columns liệt kê trong graph. Nếu cần chọn chính xác 3 fields trả về API, dùng DTO/scalar projection.

### 5.5. Khóa chính và nhận diện entity

Một entity được JPA quản lý vẫn cần có identity phù hợp. Graph không phải phương tiện làm entity “không có ID”. Dù graph chỉ chỉ định một quan hệ, provider phải có đủ thông tin để nhận diện/ánh xạ entity theo contract.

Việc ứng dụng không liệt kê id trong graph **không đồng nghĩa ID không thể đọc được** hoặc bị xóa khỏi managed entity.

### 5.6. Fetch graph không phải luôn “override EAGER tuyệt đối”

Một cách mô tả sai là:

> Dùng fetchgraph sẽ bảo đảm bỏ tải tất cả EAGER associations không ghi trong graph.

Cách hiểu chính xác hơn:

> Các thuộc tính không liệt kê được **xem như LAZY theo graph semantics**, nhưng provider **được phép** tải thêm state, và các mapping cụ thể có thể hạn chế khả năng trì hoãn.

Vì vậy, fetch graph là công cụ **nêu kế hoạch tải tối thiểu**, không phải cam kết “chỉ tải đúng các field này”.

## 6. Load graph: thuộc tính không khai báo theo static mapping

Một **load graph** được áp dụng bằng hint:

~~~java
"jakarta.persistence.loadgraph"
~~~

Quy tắc:
- Thuộc tính **có trong graph** được yêu cầu tải sớm.
- Thuộc tính **không có trong graph** vẫn dùng fetch type đã cấu hình trong mapping.

### 6.1. Cùng graph chỉ có lines, đổi sang loadgraph

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("lines");

TypedQuery<PurchaseOrder> query = em.createQuery(
    "select o from PurchaseOrder o where o.id = :id",
    PurchaseOrder.class
);

query.setParameter("id", orderId);
query.setHint("jakarta.persistence.loadgraph", graph);

PurchaseOrder order = query.getSingleResult();
~~~

Theo mapping:

| Thuộc tính | Static fetch type | Có trong load graph? | Ngữ nghĩa load graph |
|---|---|---|---|
| PurchaseOrder.lines | LAZY | Có | Yêu cầu tải sớm |
| PurchaseOrder.customer | EAGER | Không | Vẫn EAGER |
| PurchaseOrder.invoice | EAGER | Không | Vẫn EAGER |
| PurchaseOrder.attachments | LAZY | Không | Vẫn LAZY |

**Khác biệt quan trọng với phần 5:** customer và invoice không nằm trong graph nhưng vẫn được yêu cầu eager do mapping ban đầu.

### 6.2. Load graph là phép mở rộng kế hoạch tải mặc định

Nếu entity hiện có:
- customer EAGER;
- invoice EAGER;
- lines LAZY;
- attachments LAZY;

và màn hình detail muốn thêm lines, **load graph** là lựa chọn phù hợp khi vẫn muốn giữ những requirements EAGER mặc định.

~~~text
Static plan:
    customer EAGER
    invoice  EAGER
    lines    LAZY
    attachments LAZY

Load graph { lines }:
    customer EAGER (giữ mapping)
    invoice  EAGER (giữ mapping)
    lines    EAGER (do graph)
    attachments LAZY
~~~

### 6.3. Không coi loadgraph luôn tải toàn bộ graph

Một load graph có thể chỉ thêm một association mới. Các quan hệ LAZY không được chỉ định vẫn theo mapping LAZY.

Ví dụ **attachments** không nằm trong graph và vốn LAZY, nên không có yêu cầu eager mới cho attachments. Provider vẫn có thể tải thêm state nếu cho là cần, nhưng ứng dụng không nên dựa vào điều đó.

### 6.4. Sự khác biệt về bảo trì model

Giả sử sau này developer đổi:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

Với graph chỉ chứa lines:
- **Fetch graph**: customer vốn được xem LAZY do không nằm trong graph — ý định graph không đổi.
- **Load graph**: customer từ EAGER thành LAZY theo mapping mới — kết quả fetch requirements của graph cũng thay đổi.

Điều này hữu ích để cân nhắc:
- Fetch graph có thể mô tả ranh giới fetch rõ hơn cho use case;
- Load graph thuận tiện khi muốn **bổ sung** vào static plan và chấp nhận thay đổi theo mapping.

Cả hai vẫn chịu các điều kiện và quyền tối ưu hóa của JPA provider.

### 6.5. Load graph không tự sửa các vấn đề EAGER sẵn có

Nếu nhiều to-one associations được mapping EAGER và một màn hình chỉ cần lines, dùng **loadgraph {lines}** vẫn giữ những yêu cầu eager đó. Nó không phải công cụ thu hẹp quá nhiều EAGER mappings.

Với mô hình mới, nên xem lại việc đặt EAGER ở static mapping nếu thiếu linh hoạt; nhiều dự án chọn to-one LAZY có chủ đích rồi dùng graph theo use case. Nhưng phải xét khả năng hỗ trợ lazy to-one của provider và đánh đổi khi chuyển mapping.

## 7. So sánh trực diện: fetch graph và load graph

Hai hint dùng **cùng một đối tượng EntityGraph**, nhưng không có cùng hiệu lực với những thuộc tính ngoài graph.

### 7.1. Bảng quy tắc cốt lõi

| Static mapping | Có trong graph? | Fetch graph | Load graph |
|---|---|---|---|
| EAGER | Có | EAGER | EAGER |
| LAZY | Có | EAGER | EAGER |
| EAGER | Không | Xem như LAZY | EAGER |
| LAZY | Không | Xem như LAZY | LAZY |

Từ bảng này suy ra:

- Hai loại graph **giống nhau đối với thuộc tính được liệt kê**: đều yêu cầu eager.
- Hai loại graph **khác nhau đối với thuộc tính EAGER không được liệt kê**.
- Với thuộc tính LAZY không liệt kê, cả hai đều không đặt yêu cầu eager mới.
- Không có trạng thái graph nào được bảo đảm “không bao giờ tải”, vì provider có thể fetch thêm.

### 7.2. Ví dụ minh họa với cùng graph

~~~java
EntityGraph<PurchaseOrder> linesOnly =
    em.createEntityGraph(PurchaseOrder.class);
linesOnly.addAttributeNodes("lines");
~~~

Chạy hai query riêng:

~~~java
TypedQuery<PurchaseOrder> fetchQuery = em.createQuery(
    "select o from PurchaseOrder o where o.id = :id",
    PurchaseOrder.class
);
fetchQuery.setParameter("id", orderId);
fetchQuery.setHint(
    "jakarta.persistence.fetchgraph", linesOnly);
PurchaseOrder byFetchGraph = fetchQuery.getSingleResult();
~~~

~~~java
TypedQuery<PurchaseOrder> loadQuery = em.createQuery(
    "select o from PurchaseOrder o where o.id = :id",
    PurchaseOrder.class
);
loadQuery.setParameter("id", orderId);
loadQuery.setHint(
    "jakarta.persistence.loadgraph", linesOnly);
PurchaseOrder byLoadGraph = loadQuery.getSingleResult();
~~~

**Kết quả Java đều là PurchaseOrder**. Khác biệt nằm ở fetch requirements, không phải class kết quả.

Quan trọng: nếu chạy hai query trong **cùng EntityManager** và row đầu đã được load, identity map có thể khiến query sau tái sử dụng cùng managed instance. Vì vậy **không nên dùng đoạn trên nguyên trạng làm phép đo công bằng** giữa hai graph. Khi kiểm thử performance, nên làm sạch persistence context hoặc dùng EntityManager riêng, và kiểm soát caches.

### 7.3. Bảng tình huống

| Mục tiêu | Graph thường nên cân nhắc | Lý do |
|---|---|---|
| Chỉ yêu cầu thêm lines nhưng giữ EAGER mặc định | Load graph | Không thay đổi yêu cầu static EAGER ngoài graph |
| Muốn yêu cầu rõ những association thiết yếu cho endpoint | Fetch graph | Unspecified attributes được xem LAZY |
| Muốn những EAGER association không khai báo được xem LAZY | Fetch graph | Đây là khác biệt cốt lõi |
| Muốn tránh N+1 khi đọc lines | Cả hai | Đều yêu cầu lines được fetch |
| Chỉ cần vài scalars, không cần entity | DTO projection | Graph không thay thế SELECT projection |
| Muốn chính xác một SQL JOIN | Không graph nào bảo đảm | Provider quyết định SQL shape |
| Cần phân trang list to-many | Thường chọn query hai bước/DTO | Graph trên collection có thể nhân rows |
| Không muốn thay đổi static entity annotations | Cả hai | Fetch hints theo từng query |

### 7.4. Không gọi loadgraph “eager mọi thứ”

Cụm “load graph giữ mapping” **không** nghĩa tải mọi association trong toàn bộ graph. Nó chỉ giữ **fetch type vốn có** của từng thuộc tính không liệt kê.

### 7.5. Không gọi fetchgraph “lazy mọi thứ khác” theo nghĩa tuyệt đối

Ở mức semantics fetch graph, nói “ngoài graph được xem LAZY” là đúng. Nhưng khi nói về **SQL execution thực tế**, phải thêm điều kiện: provider có thể eager-fetch những trạng thái không được liệt kê.

### 7.6. Cả hai không ghi đè dữ liệu trong database

Chọn loadgraph hay fetchgraph không làm UPDATE/DELETE/INSERT gì vào các bảng. Mục đích của chúng là xác định fetch plan cho thao tác đọc; chúng không đổi quan hệ hoặc fetch annotations của entity.

## 8. Khai báo named entity graph bằng annotation

Khi fetch plan được nhiều repository/service sử dụng, khai báo **@NamedEntityGraph** trên entity giúp có một tên logic ổn định.

### 8.1. Graph chỉ lấy customer

Trong khai báo PurchaseOrder, có thể thêm:

~~~java
@NamedEntityGraph(
    name = "PurchaseOrder.withCustomer",
    attributeNodes = @NamedAttributeNode("customer")
)
~~~

Dấu **@NamedAttributeNode("customer")** chỉ định một association cần fetch. Annotation được đặt trên entity class, không đặt trên repository method như một thao tác runtime.

### 8.2. Nhiều named graphs trên cùng entity

~~~java
@NamedEntityGraphs({
    @NamedEntityGraph(
        name = "PurchaseOrder.withCustomer",
        attributeNodes = {
            @NamedAttributeNode("customer")
        }
    ),
    @NamedEntityGraph(
        name = "PurchaseOrder.withLines",
        attributeNodes = {
            @NamedAttributeNode("lines")
        }
    )
})
@Entity
public class PurchaseOrder {
    // Mapping các thuộc tính đã mô tả ở phần 2.
}
~~~

Đây là minh họa phần annotations; khi đưa vào dự án, tích hợp với class PurchaseOrder đang có, không tạo thêm một entity class trùng tên.

### 8.3. Graph chi tiết có nested subgraphs

Một màn hình detail cần:
- Customer và preferredAddress;
- Invoice;
- Lines và Product của từng line.

~~~java
@NamedEntityGraph(
    name = "PurchaseOrder.detail",
    attributeNodes = {
        @NamedAttributeNode(
            value = "customer",
            subgraph = "customerWithAddress"
        ),
        @NamedAttributeNode("invoice"),
        @NamedAttributeNode(
            value = "lines",
            subgraph = "lineWithProduct"
        )
    },
    subgraphs = {
        @NamedSubgraph(
            name = "customerWithAddress",
            attributeNodes = {
                @NamedAttributeNode("preferredAddress")
            }
        ),
        @NamedSubgraph(
            name = "lineWithProduct",
            attributeNodes = {
                @NamedAttributeNode("product")
            }
        )
    }
)
~~~

Dạng cây:

~~~text
PurchaseOrder.detail
    |
    +-- customer
    |       +-- preferredAddress
    |
    +-- invoice
    |
    +-- lines
            +-- product
~~~

Graph detail không có attachments. Với **fetchgraph**, attachments được xem LAZY; với **loadgraph**, attachments vẫn theo mapping LAZY. Với Customer.preferredAddress vốn LAZY, subgraph khiến nó được yêu cầu tải sớm.

### 8.4. Tên subgraph là tên tham chiếu trong annotation

Ở:

~~~java
@NamedAttributeNode(
    value = "lines",
    subgraph = "lineWithProduct"
)
~~~

**lineWithProduct** là tên của @NamedSubgraph khai báo trong graph, không phải tên table hay JPQL alias. Attribute node **lines** phải thực sự là persistent attribute trên PurchaseOrder.

### 8.5. Lấy graph bằng tên

~~~java
EntityGraph<?> graph =
    em.getEntityGraph("PurchaseOrder.detail");
~~~

Nếu tên không tồn tại trong persistence unit, provider có thể ném exception. Tên graph có scope trong persistence unit; nên đặt tên có prefix entity/use case để tránh nhầm.

### 8.6. includeAllAttributes

@NamedEntityGraph có thuộc tính **includeAllAttributes**:

~~~java
@NamedEntityGraph(
    name = "PurchaseOrder.allDirectAttributes",
    includeAllAttributes = true
)
~~~

Ý nghĩa là bao gồm các persistent attributes trực tiếp phù hợp trong graph. Với entity có nhiều LAZY collections, điều này có thể tạo fetch requirements rất rộng.

**includeAllAttributes=true không tự có nghĩa nạp vô hạn mọi association lồng sâu.** Với các nested relationships, graph/subgraph và default fetch graph của target vẫn cần được hiểu. Thường nên liệt kê attribute nodes có chủ đích hơn là dùng includeAllAttributes bừa bãi.

## 9. Tạo entity graph động bằng Java API

Không phải mọi fetch plan đều cần annotation. EntityManager có thể tạo **dynamic EntityGraph** phù hợp với từng màn hình.

### 9.1. Thêm attribute nodes

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes(
    "customer",
    "invoice",
    "lines"
);
~~~

Các chuỗi phải là **persistent attribute names** của entity, không phải cột SQL. Graph không có WHERE và không đổi mapping vĩnh viễn.

### 9.2. Subgraph cho lines.product

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

Subgraph<OrderLine> lineGraph =
    graph.addSubgraph("lines");

lineGraph.addAttributeNodes("product");
~~~

Graph này yêu cầu tải cả OrderLine.product:

~~~text
PurchaseOrder
   +-- lines
         +-- product
~~~

**addSubgraph("lines")** xác định node lines đồng thời cho phép khai báo nhánh sâu; không cần thêm một attribute node "lines" lặp lại.

### 9.3. Subgraph cho customer.preferredAddress

~~~java
Subgraph<Customer> customerGraph =
    graph.addSubgraph("customer");

customerGraph.addAttributeNodes("preferredAddress");
~~~

Trong model, preferredAddress LAZY; subgraph yêu cầu fetch thuộc tính này theo graph.

### 9.4. Graph động cho màn hình chi tiết

~~~java
EntityGraph<PurchaseOrder> detail =
    em.createEntityGraph(PurchaseOrder.class);

detail.addAttributeNodes("invoice");

Subgraph<Customer> c =
    detail.addSubgraph("customer");
c.addAttributeNodes("preferredAddress");

Subgraph<OrderLine> lines =
    detail.addSubgraph("lines");
lines.addAttributeNodes("product");
~~~

Cây tương đương:

~~~text
PurchaseOrder.detail
   +-- customer
   |      +-- preferredAddress
   +-- invoice
   +-- lines
          +-- product
~~~

### 9.5. Tạo graph theo lựa chọn có kiểm soát

~~~java
public EntityGraph<PurchaseOrder> buildGraph(
        boolean includeLines,
        boolean includeInvoice) {

    EntityGraph<PurchaseOrder> graph =
        em.createEntityGraph(PurchaseOrder.class);

    graph.addAttributeNodes("customer");

    if (includeLines) {
        Subgraph<OrderLine> lines =
            graph.addSubgraph("lines");
        lines.addAttributeNodes("product");
    }

    if (includeInvoice) {
        graph.addAttributeNodes("invoice");
    }

    return graph;
}
~~~

Không nhận tên attribute tùy ý từ request để gọi addAttributeNodes: ứng dụng cần **whitelist** quan hệ được phép fetch và expose. Đừng dùng một dynamic graph mutable chung cho nhiều requests rồi sửa đồng thời; nên build cục bộ hoặc dùng named graph có ý nghĩa cố định.

## 10. Áp dụng graph khi find và truy vấn JPQL

### 10.1. Fetch graph với EntityManager.find

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("lines");

Map<String, Object> properties = Map.of(
    "jakarta.persistence.fetchgraph",
    graph
);

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    properties
);
~~~

Map.of yêu cầu Java 9+; Java cũ có thể dùng HashMap. **EntityManager.find(Class<T>, Object, Map<String,Object>)** áp các properties/hints cho thao tác tìm entity.

### 10.2. Load graph với EntityManager.find

~~~java
Map<String, Object> properties = Map.of(
    "jakarta.persistence.loadgraph",
    graph
);

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    properties
);
~~~

Với graph chỉ có lines:
- FETCH: customer/invoice ngoài graph được **xem như LAZY**.
- LOAD: customer/invoice ngoài graph vẫn theo mapping **EAGER**.

### 10.3. Fetch graph với JPQL TypedQuery

~~~java
EntityGraph<?> graph =
    em.getEntityGraph("PurchaseOrder.detail");

TypedQuery<PurchaseOrder> query =
    em.createQuery(
        """
        select o from PurchaseOrder o
        where o.status = :status
        order by o.createdAt desc, o.id desc
        """,
        PurchaseOrder.class
    );

query.setParameter("status", "CREATED");
query.setHint(
    "jakarta.persistence.fetchgraph",
    graph
);

List<PurchaseOrder> orders =
    query.setMaxResults(20).getResultList();
~~~

Graph không thay thế WHERE, ORDER BY hay giới hạn số hàng. Vì graph detail có to-many **lines**, nên phân trang trực tiếp kiểu này có thể không hiệu quả; sẽ phân tích ở phần tối ưu.

### 10.4. Đổi sang loadgraph

~~~java
query.setHint("jakarta.persistence.loadgraph", graph);
~~~

Cùng một graph Java; **chế độ áp dụng** mới là điểm khác biệt.

### 10.5. Namespace Jakarta và Java EE cũ

Các hint hiện đại:

~~~java
"jakarta.persistence.fetchgraph"
"jakarta.persistence.loadgraph"
~~~

Các ứng dụng JPA cũ dùng namespace **javax.persistence** có hints:

~~~java
"javax.persistence.fetchgraph"
"javax.persistence.loadgraph"
~~~

Không trộn imports và hint namespaces thiếu kiểm soát; kiểm tra phiên bản JPA/Hibernate/Spring Boot của dự án.

### 10.6. Không áp cả hai hints cùng một query

Không nên đặt đồng thời fetchgraph và loadgraph rồi kỳ vọng provider tự hợp nhất. Hai hint biểu thị hai semantics khác nhau; chọn một mode cho một thao tác fetch, trừ trường hợp provider mô tả rõ precedence mở rộng.

### 10.7. Cẩn thận khi entity đã managed sẵn

~~~java
PurchaseOrder first =
    em.find(PurchaseOrder.class, orderId);

PurchaseOrder second = em.find(
    PurchaseOrder.class,
    orderId,
    Map.of("jakarta.persistence.fetchgraph", graph)
);
~~~

Vì identity map, **second có thể chính là first**. Lần find thứ hai không bảo đảm một lần tải hoàn toàn mới để so sánh graph.

Để thí nghiệm:
- Dùng EntityManager riêng cho từng trường hợp;
- Hoặc clear với lưu ý detach **mọi** managed entity;
- Kiểm soát second-level cache và query cache;
- Dùng statistics và SQL logs, không đo hai query liên tiếp trong context đã warm-up.

### 10.8. Find với graph không phải refresh

Graph mô tả fetch plan. Nếu một managed instance đã chứa state cũ từ database, **find thêm graph không tự bảo đảm refresh state**. Khi cần đồng bộ state từ DB, dùng refresh trên managed entity theo transaction/lifecycle phù hợp.

### 10.9. Graph không phải lớp bảo mật

Fetch graph có thể tải Customer và Invoice, nhưng **không xác định user được phép xem order nào**. Query vẫn cần authorization, tenant isolation, soft-delete predicates và output DTO phù hợp.

Một truy vấn scalar:

~~~java
select o.orderNumber
from PurchaseOrder o
~~~

trả String, không phải PurchaseOrder; graph không biến scalar projection thành entity selection. Khi chỉ cần vài columns, dùng DTO/scalar projection thay vì entity graph là lựa chọn đáng cân nhắc.

## 11. Subgraph và default fetch graph ở cấp liên kết

Khi EntityGraph có node là association, không được suy ra rằng **mọi thuộc tính sâu hơn của target entity** đều được fetch.

### 11.1. Chỉ customer

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);
graph.addAttributeNodes("customer");
~~~

Node customer yêu cầu tải Customer. Khi không khai báo subgraph cho relationship này, **default fetch graph** của Customer được sử dụng theo quy tắc entity graph: bao gồm những attributes có EAGER semantics theo mapping và thông tin identity cần thiết, không tự mở rộng vô hạn qua LAZY associations.

Theo model:
- Customer.name và email là basic attributes EAGER mặc định.
- Customer.preferredAddress là LAZY.

Graph chỉ có customer **không tự yêu cầu** Customer.preferredAddress.

### 11.2. Customer và preferredAddress

~~~java
Subgraph<Customer> customer =
    graph.addSubgraph("customer");
customer.addAttributeNodes("preferredAddress");
~~~

PreferredAddress bây giờ được liệt kê rõ trong subgraph, nên được yêu cầu eager.

### 11.3. Lines và Product

~~~java
graph.addAttributeNodes("lines");
~~~

yêu cầu OrderLines nhưng không tự yêu cầu OrderLine.product vốn LAZY. Nếu code duyệt:

~~~java
for (OrderLine line : order.getLines()) {
    System.out.println(line.getProduct().getName());
}
~~~

vẫn có thể gây thêm queries. Để thể hiện nhu cầu:

~~~java
Subgraph<OrderLine> lines =
    graph.addSubgraph("lines");
lines.addAttributeNodes("product");
~~~

### 11.4. Graph nhiều cấp không bắt buộc một JOIN duy nhất

~~~text
PurchaseOrder
   +-- customer
   |      +-- preferredAddress
   +-- lines
          +-- product
~~~

có thể được provider thực thi bằng JOIN, secondary SELECTs, batch fetching hoặc cache. Graph quy định **fetch requirements**, không phải chính xác số SQL statements. Hãy đo SQL thực tế nếu đang xử lý N+1.

### 11.5. Map key subgraph

JPA còn có API key subgraph cho một số Map-valued associations có entity key, khác với subgraph thông thường cho target/value. Không dùng key subgraph khi Map key chỉ là String/enum basic và không có entity mapping.

## 12. Spring Data JPA @EntityGraph

Spring Data JPA cung cấp annotation **org.springframework.data.jpa.repository.EntityGraph** trên repository method. Đừng nhầm với interface runtime **jakarta.persistence.EntityGraph**.

### 12.1. Dùng named graph với FETCH

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(
        value = "PurchaseOrder.detail",
        type = EntityGraph.EntityGraphType.FETCH
    )
    @Query("""
        select o from PurchaseOrder o
        where o.id = :id
        """)
    Optional<PurchaseOrder> findDetailed(
        @Param("id") Long id
    );
}
~~~

**value** là tên graph đã đăng ký ở entity; FETCH tương đương fetchgraph semantics.

### 12.2. Dùng LOAD

~~~java
@EntityGraph(
    value = "PurchaseOrder.detail",
    type = EntityGraph.EntityGraphType.LOAD
)
@Query("""
    select o from PurchaseOrder o
    where o.id = :id
    """)
Optional<PurchaseOrder> findWithLoadGraph(
    @Param("id") Long id
);
~~~

Các EAGER relationships không nằm trong graph tiếp tục theo mapping. Trong nhiều phiên bản Spring Data JPA, **FETCH** là type mặc định; viết tường minh dễ bảo trì hơn.

### 12.3. attributePaths ad hoc

~~~java
@EntityGraph(
    attributePaths = {
        "customer",
        "lines.product"
    },
    type = EntityGraph.EntityGraphType.FETCH
)
@Query("""
    select o from PurchaseOrder o
    where o.id = :id
    """)
Optional<PurchaseOrder> findWithProductLines(
    @Param("id") Long id
);
~~~

**attributePaths** là tiện ích của Spring Data JPA, có thể diễn đạt nested path tùy version. Nó không phải cú pháp chuẩn của @NamedAttributeNode.

### 12.4. Chọn value hoặc attributePaths

- **value**: trỏ named graph.
- **attributePaths**: framework tạo dynamic graph từ paths.

Khi attributePaths không rỗng, Spring Data có thể ưu tiên dynamic graph và không dùng value như tên named graph; tránh khai báo cả hai mà không xác nhận precedence/version.

### 12.5. Pagination với collection graph

~~~java
@EntityGraph(attributePaths = "lines")
Page<PurchaseOrder> findByStatus(
    String status, Pageable pageable
);
~~~

Nếu fetch to-many collection cùng Pageable, SQL JOIN có thể nhân rows, provider có thể xử lý pagination trong bộ nhớ hoặc cảnh báo. **Page không bảo đảm collection fetch được phân trang hiệu quả tại database**. Với số lượng lớn, nên page IDs trước, sau đó fetch graph cho trang IDs.

### 12.6. @Transactional vẫn quan trọng

Repository trả entity có graph không có nghĩa mọi LAZY relationship ngoài graph vẫn dùng được sau khi session đóng. Map entity sang DTO/response trong một transaction thích hợp; tránh để JSON serializer truy cập quan hệ chưa được tải một cách vô tình.

## 13. EntityGraph và JPQL JOIN FETCH khác nhau thế nào?

### 13.1. JOIN FETCH nằm ngay trong JPQL

~~~java
List<PurchaseOrder> result = em.createQuery(
    """
    select o
    from PurchaseOrder o
    left join fetch o.customer
    where o.status = :status
    """,
    PurchaseOrder.class
)
.setParameter("status", "CREATED")
.getResultList();
~~~

Query xác định customer được fetch bằng một JOIN FETCH path.

### 13.2. Graph tách fetch plan khỏi query

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

List<PurchaseOrder> result = em.createQuery(
    """
    select o from PurchaseOrder o
    where o.status = :status
    """,
    PurchaseOrder.class
)
.setParameter("status", "CREATED")
.setHint("jakarta.persistence.fetchgraph", graph)
.getResultList();
~~~

Graph có thể tái dùng cho các queries khác, còn JPQL vẫn chủ yếu mô tả WHERE/ORDER BY.

### 13.3. Bảng so sánh

| Yếu tố | JOIN FETCH | EntityGraph |
|---|---|---|
| Nơi khai báo | JPQL statement | Named/dynamic graph và hint |
| Điều khiển to-one/to-many | JOIN FETCH path | Attribute nodes/subgraphs |
| Chế độ fetchgraph vs loadgraph | Không | Có |
| INNER/LEFT join semantics | Chọn tường minh JOIN/LEFT JOIN FETCH | Không ép SQL JOIN shape |
| Tái dùng cho nhiều queries | Thường cần lặp query fragment | Named graph có thể tái dùng |
| SQL số câu bắt buộc | Không nên suy tuyệt đối | Không bảo đảm 1 câu |
| Fetch collection pagination | Có rủi ro | Có rủi ro tương tự |
| Chỉ select DTO fields | Không phải mục đích chính | Không phải mục đích chính |

### 13.4. JOIN FETCH có thể thay đổi tập root rows

~~~java
select o
from PurchaseOrder o
join fetch o.invoice
~~~

là INNER JOIN FETCH; nếu invoice optional và chưa có, order ấy có thể không được chọn. Dùng **left join fetch o.invoice** để giữ order thiếu invoice.

Entity graph yêu cầu invoice được fetch, không tự có nghĩa lọc bỏ order chưa có invoice.

### 13.5. To-many collection và duplicate SQL rows

Một PurchaseOrder có 10 lines, JOIN FETCH lines có thể phát 10 SQL rows cho cùng root. Provider sẽ xử lý entity identity/de-dup theo semantics và version, nhưng vẫn phải truyền và xử lý nhiều rows.

EntityGraph trên lines cũng có thể dẫn đến JOIN và tác động tương tự. Với collection fetch, phải cân nhắc pagination và cardinality; không cho rằng graph tránh được Cartesian product.

### 13.6. Kết hợp nhiều cơ chế cần chủ đích

Một query có JOIN FETCH và graph trùng/khác associations có thể sinh fetch plan khó dự đoán. Không thêm cả hai đơn thuần để “tăng tốc”. Chọn một chiến lược chính, rồi đo SQL và kiểm thử trên provider mục tiêu.

### 13.7. Quy tắc chọn

**JOIN FETCH** hợp khi query chuyên biệt cần một vài associations và muốn kiểm soát JOIN/LEFT JOIN. **EntityGraph** hợp khi cần fetch plan tái sử dụng, dynamic requirements hoặc phân biệt FETCH/LOAD so với static mapping. **DTO projection** hợp khi chỉ cần scalar fields/read-only API response, không cần managed entity graph.

## 14. Entity graph không giải quyết mọi vấn đề N+1

Entity graph là công cụ quan trọng để làm rõ nhu cầu tải associations, nhưng **không thay thế việc kiểm tra SQL thực tế**.

### 14.1. N+1 ở Customer

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "select o from PurchaseOrder o",
    PurchaseOrder.class
).getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
~~~

Vì customer trong model có EAGER, provider phải đáp ứng eager requirement; nhưng có thể dùng secondary SELECTs thay vì JOIN. Một ứng dụng vẫn có thể gặp nhiều queries.

Graph:

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);
graph.addAttributeNodes("customer");
~~~

nêu rõ cần customer, nhưng provider vẫn quyết định kỹ thuật fetch. Kết quả có thể được cải thiện; cần đo để biết.

### 14.2. N+1 ở Lines/Product

~~~java
for (PurchaseOrder order : orders) {
    for (OrderLine line : order.getLines()) {
        System.out.println(
            line.getProduct().getName()
        );
    }
}
~~~

Đây có thể là:
- N SELECTs tải Lines;
- Nhiều SELECTs tải Products;
- Ngoài câu SELECT đầu lấy orders.

Graph phù hợp hơn:

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

Subgraph<OrderLine> lines =
    graph.addSubgraph("lines");
lines.addAttributeNodes("product");
~~~

Không chỉ thêm **lines** nếu UI thực sự còn đọc **product.name**.

### 14.3. Khi graph còn gây thêm dữ liệu thừa

Nếu UI chỉ hiển thị **orderNumber, status và customerName**, graph bao gồm:
- Lines;
- Product;
- Invoice;
- Attachments;

sẽ có nguy cơ tải rất nhiều dữ liệu không cần thiết. Kế hoạch tải tối ưu không phải kế hoạch “càng nhiều nodes càng tốt”.

### 14.4. Không khẳng định một graph luôn tạo đúng một query

Graph là mô tả trạng thái phải sẵn sàng khi fetch theo semantics; provider có thể sử dụng nhiều SQL statements để đáp ứng. Hiệu quả cần được đánh giá qua:
- Số round trips;
- SQL row count;
- Tổng bytes truyền về;
- Time to first row;
- Heap/GC;
- Các statements phụ do lazy associations;
- Database execution plan và indexes.

### 14.5. Entity graph và batch fetching có thể bổ sung nhau

Một số provider, chẳng hạn Hibernate, hỗ trợ **@BatchSize** hoặc **hibernate.default_batch_fetch_size** để gom việc tải lazy associations. Đây là cơ chế provider-specific, khác với graph.

Không phải luôn cần đưa một collection khổng lồ vào graph để tránh N+1. Có khi giữ nó LAZY và dùng batch fetching đúng kích thước sẽ ít SQL rows nhân bản hơn.

### 14.6. EAGER mapping quá rộng vẫn có chi phí

Nếu PurchaseOrder.customer và invoice mặc định EAGER, mọi use case có thể chịu nhu cầu eager không cần thiết. Với loadgraph, những yêu cầu EAGER ngoài graph vẫn được giữ.

Fetchgraph có thể thử thu hẹp fetch requirements cho use case, nhưng provider vẫn được phép fetch thêm; về lâu dài, nếu kiểm soát model, cân nhắc mapping LAZY có chủ đích ở các to-one associations và chọn graph theo màn hình. Thay đổi static mapping phải được kiểm thử vì các tính năng như inverse one-to-one LAZY có thể cần bytecode enhancement tùy provider.

## 15. Pagination và collection fetch: tránh mất kiểm soát cardinality

Một danh sách đơn hàng có 1.000 orders, mỗi order có trung bình 20 lines. Nếu query fetch lines qua JOIN, SQL có thể cần trả khoảng **20.000 rows** để biểu diễn 1.000 orders, chưa tính các joins khác.

### 15.1. Vì sao LIMIT/OFFSET khó với collection?

Giả sử SQL JOIN tạo:

~~~text
Order#1 Line#1
Order#1 Line#2
Order#1 Line#3
Order#2 Line#4
Order#2 Line#5
Order#3 Line#6
...
~~~

Nếu DB LIMIT 3 **rows**, kết quả chỉ chứa một Order#1 với ba lines. Nhưng API cần LIMIT 3 **orders**, mỗi order đủ collection. Provider phải lựa chọn chiến lược để tránh thiếu dữ liệu, có thể xử lý pagination trong bộ nhớ, dùng nhiều queries hoặc báo lỗi/cảnh báo.

**Số SQL rows không phải số entity roots.** Đây là lý do fetch collection to-many với pagination cần thiết kế riêng.

### 15.2. Quy trình hai bước

**Bước 1:** lấy trang IDs của root entity:

~~~java
List<Long> pageIds = em.createQuery(
    """
    select o.id
    from PurchaseOrder o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """,
    Long.class
)
.setParameter("status", "CREATED")
.setFirstResult(offset)
.setMaxResults(pageSize)
.getResultList();
~~~

**Bước 2:** fetch graph cho các IDs vừa có:

~~~java
if (pageIds.isEmpty()) {
    return List.of();
}

EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

Subgraph<OrderLine> lines =
    graph.addSubgraph("lines");
lines.addAttributeNodes("product");

List<PurchaseOrder> loaded = em.createQuery(
    """
    select distinct o
    from PurchaseOrder o
    where o.id in :ids
    """,
    PurchaseOrder.class
)
.setParameter("ids", pageIds)
.setHint("jakarta.persistence.fetchgraph", graph)
.getResultList();
~~~

Query thứ hai không áp LIMIT/OFFSET cho tập JOIN collection; nó chỉ lấy những order IDs thuộc trang nhỏ.

### 15.3. Khôi phục thứ tự trang

Điều kiện **IN :ids** không đảm bảo thứ tự theo List<Long> pageIds. Có thể dựng Map rồi sắp theo trang gốc:

~~~java
Map<Long, PurchaseOrder> byId = loaded.stream()
    .collect(Collectors.toMap(
        PurchaseOrder::getId,
        Function.identity()
    ));

List<PurchaseOrder> ordered = pageIds.stream()
    .map(byId::get)
    .filter(Objects::nonNull)
    .toList();
~~~

Imports tương ứng: **java.util.Map**, **java.util.stream.Collectors**, **java.util.function.Function**, **java.util.Objects**. Trong Java cũ không hỗ trợ toList(), dùng collect(Collectors.toList()).

Nếu dữ liệu thay đổi đồng thời giữa hai bước, một Order có thể bị xóa/đổi; ứng dụng phải xác định consistency policy. Không coi hai queries độc lập là snapshot transaction tự động.

### 15.4. COUNT query riêng

Để hiển thị tổng trang:

~~~java
Long total = em.createQuery(
    """
    select count(o)
    from PurchaseOrder o
    where o.status = :status
    """,
    Long.class
)
.setParameter("status", "CREATED")
.getSingleResult();
~~~

Không để count query fetch Lines: đếm roots theo filter, không đếm số SQL rows sau JOIN to-many.

### 15.5. Có nên fetch hai collections cùng lúc?

Nếu graph bao gồm **lines** và **attachments** (cùng là List), JOIN đồng thời có thể tạo Cartesian multiplication:

~~~text
1 order × 20 lines × 5 attachments = 100 rows
~~~

Một số cấu hình Hibernate còn có thể báo **MultipleBagFetchException** khi đồng thời fetch nhiều bag-valued collections.

Đây là **hành vi Hibernate-specific**, không phải tên exception chuẩn JPA. Trong trường hợp này, cân nhắc:
- Tách query fetch từng collection;
- Batch fetching;
- Query root + projection;
- Hạn chế số relationships trong graph;
- Read model riêng cho màn hình.

### 15.6. DISTINCT không xóa chi phí truyền dữ liệu

~~~java
select distinct o
from PurchaseOrder o
where o.id in :ids
~~~

có thể yêu cầu distinct root results, nhưng không bảo đảm DB sẽ chỉ truyền một row vật lý cho mỗi order khi fetch collection. Root de-dup không xóa bỏ số rows trung gian, memory và join cost.

### 15.7. Keyset pagination khi dữ liệu biến động

Khi bảng có nhiều rows, OFFSET lớn có thể gây chi phí scan và kết quả bị dịch khi insert/delete đồng thời. Một hướng khác là keyset pagination theo **(createdAt, id)** có điều kiện cursor rõ ràng.

Graph chỉ xử lý fetch shape, không thay thế chiến lược pagination. Để có thứ tự ổn định, cần ORDER BY đầy đủ và logic cursor tương ứng.

## 16. Persistence context, lazy loading và vòng đời giao dịch

### 16.1. Graph không giữ EntityManager luôn mở

Một entity có attributes chưa được tải sau khi EntityManager đóng hoặc persistence context kết thúc có thể không truy cập được lazy relations. Với Hibernate, thường gặp **LazyInitializationException**; đây là exception của provider, không phải một loại exception chuẩn buộc mọi provider phải giống nhau.

Giả sử:

~~~java
PurchaseOrder order = service.findOrder(orderId);

// Nếu lines chưa được load và session đã đóng:
order.getLines().size(); // Có thể lỗi lazy initialization.
~~~

### 16.2. Map DTO trong transaction

~~~java
@Transactional(readOnly = true)
public OrderDetailDto getDetail(long id) {
    EntityGraph<PurchaseOrder> graph =
        em.createEntityGraph(PurchaseOrder.class);

    Subgraph<OrderLine> lines =
        graph.addSubgraph("lines");
    lines.addAttributeNodes("product");

    PurchaseOrder order = em.find(
        PurchaseOrder.class,
        id,
        Map.of("jakarta.persistence.fetchgraph", graph)
    );

    if (order == null) {
        throw new IllegalArgumentException(
            "Không tìm thấy đơn hàng");
    }

    return OrderDetailDto.from(order);
}
~~~

Ví dụ giả định có OrderDetailDto cùng factory method from. Khi mapping, chỉ đọc những relationships mà DTO thực sự yêu cầu. **Graph không tự sinh DTO**.

### 16.3. Không trả entity trực tiếp rồi phụ thuộc JSON serializer

Entity associations có thể hai chiều, ví dụ Order → Lines → Order. Nếu serializer duyệt mọi getter:
- Có thể kích hoạt lazy queries bất ngờ;
- Có thể gặp vòng tham chiếu;
- Có thể expose dữ liệu không nên trả;
- Có thể lỗi sau khi persistence context đóng.

EntityGraph không định nghĩa JSON serialization boundaries. Dùng response DTO, Jackson annotations hoặc serializers có kiểm soát tùy kiến trúc; đừng lấy graph làm cơ chế phân quyền.

### 16.4. Open Session In View không phải giải pháp mặc định

Một số ứng dụng Spring dùng Open Session/EntityManager In View để giữ persistence context tới lúc render response. Nó có thể giảm lỗi lazy initialization trong controller, nhưng cũng dễ làm query được phát **ngoài business service boundary**, khó kiểm soát SQL và hiệu năng.

Một thiết kế rõ ràng thường xác định fetch plan và map DTO bên trong service transaction. Cần quyết định OSIV theo kiến trúc, không xem nó thay EntityGraph.

### 16.5. Graph không đổi trạng thái managed/detached

Entity được chọn bởi query có graph vẫn có thể là managed trong persistence context. Sau **em.clear()**, các instances ấy detached; graph không ngăn detach.

~~~java
PurchaseOrder order = em.find(
    PurchaseOrder.class, id, properties
);

em.clear();

// order là detached reference.
~~~

Các associations đã được tải có thể còn đọc được như Java objects tùy trạng thái; các associations chưa tải có thể không được khởi tạo nữa. Không gọi em.clear rồi mong graph giữ entity managed.

### 16.6. Có thể dùng refresh với properties nhưng cần cân nhắc

JPA có overload refresh nhận properties. Tuy nhiên refresh có thể ghi đè pending changes trên managed entity. Nếu mục tiêu chỉ fetch một LAZY association cụ thể, việc áp graph lúc query đầu hoặc tách read model rõ thường dễ hiểu hơn.

Không dùng refresh như cách tự động giải quyết mọi sai lệch fetch plan: nó mang semantics đồng bộ entity state với database, khác với việc chọn projection.

## 17. Những sai lầm phổ biến về FETCH và LOAD

### 17.1. “Fetch graph chỉ tải đúng các node đã liệt kê”

Sai nếu hiểu tuyệt đối. Quy tắc đúng: **những node không liệt kê được xem như LAZY**, nhưng provider vẫn được phép tải thêm state. SQL có thể chứa các basic columns hoặc eager associations ngoài graph.

### 17.2. “Load graph bỏ qua mọi EAGER annotation”

Sai. **Load graph giữ mapping fetch type đối với attributes không liệt kê**. Đó chính là khác biệt nổi bật với fetch graph.

### 17.3. “Fetch graph biến mọi nested relationship thành EAGER”

Sai. Relationship node không có subgraph chỉ áp dụng default fetch graph của target theo ngữ nghĩa JPA. Muốn OrderLine.product thì khai báo **lines → product**.

### 17.4. “Graph luôn là một câu JOIN”

Sai. Provider có thể thực hiện multiple SELECTs, batch fetching hoặc join tùy mapping/dialect. Đo SQL thực tế.

### 17.5. “Graph chính là DTO”

Sai. Graph là kế hoạch tải **entity attributes/associations**; DTO là hình dạng dữ liệu trả về. Graph không giới hạn SQL columns cứng như constructor projection.

### 17.6. “Dùng @EntityGraph thì không bao giờ có N+1”

Sai. Có thể thiếu subgraph sâu hơn hoặc provider dùng secondary SELECTs. Graph không bảo đảm số query cố định.

### 17.7. “Fetch collection luôn tốt cho pagination”

Sai. JOIN to-many có thể nhân rows, gây in-memory pagination hoặc vấn đề MultipleBagFetchException ở Hibernate. Dùng query IDs trước hoặc read-model riêng.

### 17.8. “Nếu lần find thứ hai dùng graph khác, tôi đã benchmark công bằng”

Sai nếu cùng persistence context hoặc caches đã warm. Identity map và cached attributes có thể khiến lần fetch sau không tương đương lần đầu.

### 17.9. “Graph thay đổi association trong database”

Sai. Graph chỉ tác động fetch plan tại thao tác đọc. Nó không UPDATE relationships hoặc thay annotations.

### 17.10. “Graph đủ để bảo vệ dữ liệu nhạy cảm”

Sai. Graph không áp authorization/tenant filtering hay public API field selection. Không dựa vào lazy state như một hàng rào bảo mật.

## 18. Kiểm thử fetch graph và load graph

Entity graph là tính năng của persistence provider; nên kiểm thử bằng **integration test** thay vì chỉ mock EntityManager.

### 18.1. Kiểm tra trạng thái loaded

JPA cung cấp **PersistenceUnitUtil**:

~~~java
boolean loaded = em.getEntityManagerFactory()
    .getPersistenceUnitUtil()
    .isLoaded(order, "lines");
~~~

Hoặc:

~~~java
PersistenceUtil util = Persistence.getPersistenceUtil();
boolean loaded = util.isLoaded(order, "lines");
~~~

Các API này hỗ trợ kiểm tra thuộc tính đã được load hay chưa, không cho biết chính xác provider dùng một hay nhiều SQL statements.

### 18.2. Test một thuộc tính có trong fetch graph

~~~java
@Test
void fetchGraphLoadsOrderLines() {
    em.clear();

    EntityGraph<PurchaseOrder> graph =
        em.createEntityGraph(PurchaseOrder.class);
    graph.addAttributeNodes("lines");

    PurchaseOrder order = em.find(
        PurchaseOrder.class,
        testOrderId,
        Map.of("jakarta.persistence.fetchgraph", graph)
    );

    assertNotNull(order);
    assertTrue(em.getEntityManagerFactory()
                 .getPersistenceUnitUtil()
                 .isLoaded(order, "lines"));
}
~~~

Ví dụ giả định JUnit 5, EntityManager hợp lệ và có testOrderId. Fixture phải được persist bằng transaction phù hợp.

### 18.3. Không assert thuộc tính ngoài graph luôn unloaded

Một assertion như:

~~~java
assertFalse(
    util.isLoaded(order, "customer")
);
~~~

không portable nếu customer ngoài fetch graph. Provider **được phép tải thêm** state, đặc biệt EAGER associations. Kiểm thử những attributes graph yêu cầu và đo SQL thực tế riêng; đừng biến mục tiêu tối ưu thành điều kiện JPA spec không bảo đảm.

### 18.4. Test nested subgraph

~~~java
@Test
void graphLoadsProductsOfOrderLines() {
    em.clear();

    EntityGraph<PurchaseOrder> graph =
        em.createEntityGraph(PurchaseOrder.class);

    Subgraph<OrderLine> lines =
        graph.addSubgraph("lines");
    lines.addAttributeNodes("product");

    PurchaseOrder order = em.find(
        PurchaseOrder.class,
        testOrderId,
        Map.of("jakarta.persistence.fetchgraph", graph)
    );

    for (OrderLine line : order.getLines()) {
        assertTrue(
            em.getEntityManagerFactory()
              .getPersistenceUnitUtil()
              .isLoaded(line, "product")
        );
    }
}
~~~

Fixture phải có ít nhất một OrderLine, nếu không vòng lặp rỗng sẽ không kiểm tra được subgraph.

### 18.5. Benchmark hai graph với context riêng

Không chạy fetchgraph rồi loadgraph cho cùng ID trong một EntityManager và coi số SQL của lần hai là tương đương lần đầu. Identity map, đã khởi tạo associations và L2 cache làm kết quả sai lệch.

Quy trình:
1. Ghi fixtures, commit setup transaction.
2. Mở EntityManager riêng cho fetchgraph.
3. Xóa/reset statistics trong phạm vi đo; thực thi và truy cập dữ liệu theo cùng mục tiêu.
4. Đóng context, kiểm soát L2/query cache nếu cần cold runs.
5. Mở context mới cho loadgraph và lặp quy trình.
6. So sánh statements, rows, thời gian và heap.

### 18.6. Test không đòi một SQL duy nhất

Graph có thể được đáp ứng bằng JOIN hoặc secondary SELECTs. Assertion số SQL bằng 1 chỉ là **kỳ vọng performance của provider/cấu hình cụ thể**, không phải điều kiện portable của entity graph.

Quan trọng hơn là test **những fields cần dùng đã được tải đúng**, query trả đúng entities và N+1 được kiểm soát.

### 18.7. Test pagination với collection

Tạo 30 orders, mỗi order có nhiều lines:
- Page 10 IDs theo (createdAt, id);
- Fetch graph lines.product cho 10 IDs;
- Assert đúng tập root IDs;
- Khôi phục thứ tự theo page IDs;
- Assert collections đủ phần tử;
- Theo dõi SQL để không tải cả 30 orders rồi cắt trong RAM.

### 18.8. Flush/clear để tránh fixture che kết quả

Sau khi setup:

~~~java
em.flush();
em.clear();
~~~

giúp các instances cũ không còn managed. Nhưng flush **không phải commit**; nếu test chuyển sang EntityManager khác, phải bảo đảm transaction setup đã commit để dữ liệu hiển thị theo isolation.

## 19. Thiết kế graph theo từng use case

### 19.1. List page chỉ cần ba fields

UI: orderNumber, status, customerName.

Chọn:
- DTO projection nếu chỉ đọc;
- EntityGraph chỉ có customer nếu cần entity result.

Không tải lines/invoice/attachments nếu UI không dùng. Nếu muốn ngoài graph được xem LAZY, chọn FETCH; nếu muốn giữ static EAGER, chọn LOAD.

### 19.2. Detail của một order

UI cần:
- Customer và preferredAddress;
- Invoice;
- Lines với Product names.

Graph:

~~~text
PurchaseOrder
    +-- customer
    |     +-- preferredAddress
    +-- invoice
    +-- lines
          +-- product
~~~

Cả fetchgraph/loadgraph đều yêu cầu những nodes có trong graph được fetch. Khác nhau ở các EAGER attributes khác chưa được liệt kê.

### 19.3. Export một triệu đơn

Nếu chỉ xuất scalar fields, dùng DTO/tuple projection, page/stream theo thiết kế. Không tạo một triệu managed PurchaseOrder với graph chứa mọi relationship.

### 19.4. Job xử lý lines

Nếu nghiệp vụ phải duyệt từng OrderLine và Product, graph lines.product có thể hữu ích cho từng chunk. Nhưng đừng giữ nhiều collections lớn trong persistence context; cần pagination, flush/clear phù hợp và theo dõi memory.

### 19.5. Chọn giữa FETCH, LOAD và DTO

| Use case | Lựa chọn cân nhắc | Lý do |
|---|---|---|
| Cần customer, không muốn thêm EAGER ngoài graph theo semantics | Fetch graph | Unspecified attributes xem LAZY |
| Muốn thêm lines nhưng giữ EAGER mapping | Load graph | Bổ sung vào static plan |
| Cần detail gồm lines/product | Graph có subgraph | Yêu cầu fetch đúng cấp |
| Chỉ 3 scalar fields | DTO projection | Không dựng graph entity dư |
| Query chuyên biệt cần LEFT JOIN | LEFT JOIN FETCH | Nêu join semantics trực tiếp |
| Pageable list và to-many collection | Hai bước: page IDs, fetch graph | Giảm rủi ro pagination |
| Màn hình dùng nhiều collections | Tách graph/batch/DTO | Tránh cartesian multiplication |

## 20. Bảng xử lý lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
|---|---|---|
| Loadgraph vẫn tải Invoice | Invoice vốn EAGER | Đây là semantics load graph |
| Fetchgraph vẫn thấy Invoice loaded | Provider fetch thêm | Không assert unspecified bắt buộc unloaded |
| Lines loaded nhưng Products N+1 | Thiếu lines.product | Thêm subgraph |
| Customer loaded nhưng Address lazy | Thiếu customer.preferredAddress | Thêm subgraph |
| Số SQL không giảm | Provider dùng secondary SELECT/cache | Đo SQL, cân nhắc batch fetching |
| Graph sinh nhiều SQL rows | To-many JOIN | Thu hẹp graph, chia queries |
| Page bị chậm/in-memory | Fetch collection trong Pageable | Page IDs trước |
| MultipleBagFetchException | Hibernate fetch nhiều bags | Tách fetch, giảm collections |
| find lần hai không đổi gì | Entity đã managed sẵn | Đo với context mới |
| Không tìm thấy named graph | Sai tên hoặc entity metadata chưa quét | Kiểm tra graph name/scanning |
| Wrong attribute name | Dùng tên cột thay Java property | Dùng persistent attribute name |
| @EntityGraph import lỗi | Nhầm Spring annotation/Jakarta interface | Sửa import |
| Không áp được nested path | Dùng API/version không hỗ trợ | Dùng JPA subgraph hoặc update framework |
| Graph sau transaction vẫn lazy error | Thiếu nhánh cần fetch/context đóng | Map DTO trong transaction |
| JSON trả quá nhiều dữ liệu | Serialize entity graph trực tiếp | Dùng DTO |
| Graph không chặn cross-tenant | Fetch plan không phải authorization | Áp WHERE/security policy |
| includeAllAttributes làm query nặng | Fetch quá nhiều nodes | Liệt kê nodes cần thiết |
| Test dựa trên SQL count=1 thất bại | Graph không ép SQL shape | Kiểm đúng semantics + provider-specific metrics |
| Benchmark khác nhau khó giải thích | Context/cache/fixture warm | Kiểm soát môi trường đo |

## 21. Bài tập thực hành

Các bài tập dùng entity PurchaseOrder, Customer, OrderLine, Product, Invoice, Address và OrderAttachment đã mô tả ở phần 2. Nếu muốn chạy code, tạo fixture thật trong database và kiểm thử bằng Jakarta Persistence provider tương thích.

### Bài 1. Dự đoán fetch plan mặc định

PurchaseOrder mapping:
- customer: EAGER;
- invoice: EAGER;
- lines: LAZY;
- attachments: LAZY.

Không có EntityGraph. Hãy ghi các yêu cầu fetch do static mapping tạo ra và giải thích vì sao **không thể từ đó suy ra chính xác số SQL SELECT statements**.

### Bài 2. Fetch graph chỉ có lines

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);
graph.addAttributeNodes("lines");
~~~

Áp hint **jakarta.persistence.fetchgraph**. Hãy nêu semantics của customer, invoice, lines, attachments.

**Định hướng:** lines được yêu cầu EAGER; những thuộc tính ngoài graph được xem LAZY theo fetch graph semantics. Provider vẫn được phép fetch thêm.

### Bài 3. Load graph chỉ có lines

Dùng chính graph ở bài 2 nhưng áp **jakarta.persistence.loadgraph**. Hãy điền bảng trạng thái fetch requirements.

**Định hướng:** customer/invoice vẫn EAGER vì static mapping; lines EAGER vì graph; attachments LAZY.

### Bài 4. So sánh hai loại graph bằng bảng

Hoàn thành bảng:

| Mapping | Có trong graph? | Fetch graph | Load graph |
|---|---|---|---|
| EAGER | Có | ? | ? |
| EAGER | Không | ? | ? |
| LAZY | Có | ? | ? |
| LAZY | Không | ? | ? |

Thêm một câu giải thích vì sao **xem như LAZY** không đồng nghĩa **bắt buộc chưa tải**.

### Bài 5. Graph chỉ chứa customer

Tạo fetch graph có customer nhưng không có subgraph. Customer.preferredAddress LAZY. Có chắc preferredAddress được fetch không? Hãy giải thích default fetch graph của target Customer.

### Bài 6. Nested subgraph

Viết graph:

~~~text
PurchaseOrder
  +-- customer
        +-- preferredAddress
~~~

bằng EntityManager.createEntityGraph và Subgraph<Customer>. Gọi EntityManager.find với fetchgraph.

### Bài 7. Lines và Product

Một service duyệt orders rồi với mỗi OrderLine in Product.name. Graph chỉ có lines vẫn phát nhiều SELECT đến Product. Hãy sửa graph thêm lines.product và giải thích vì sao node lines không tự kéo toàn bộ associations của OrderLine.

### Bài 8. Named entity graph

Khai báo:

~~~text
PurchaseOrder.detail
  customer
  invoice
  lines -> product
~~~

bằng **@NamedEntityGraph**, **@NamedAttributeNode**, **@NamedSubgraph**. Sau đó dùng getEntityGraph(name) rồi setHint fetchgraph.

### Bài 9. Phân biệt logical graph name với entity name

Tên entity là PurchaseOrder; named graph có name="PurchaseOrder.detail". Tại sao:

~~~java
em.getEntityGraph("PurchaseOrder");
~~~

có thể không tìm thấy graph mong muốn? Phải dùng tên nào?

### Bài 10. Graph ad hoc

Viết một method nhận boolean includeLines/includeInvoice rồi tạo dynamic EntityGraph tương ứng. Không cho client truyền tên field tùy ý. Nếu includeLines=true, phải thêm lines.product.

### Bài 11. Named graph hay dynamic graph?

Một hệ thống có ba màn hình cố định: list/detail/export. Một công cụ báo cáo khác cho người dùng chọn các cột tùy ý. Hãy quyết định dùng named graph, dynamic graph hay DTO projection cho từng trường hợp, và giải thích.

### Bài 12. Áp graph cho EntityManager.find

Viết:

~~~java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.loadgraph", graph
);
~~~

và gọi em.find(PurchaseOrder.class, id, hints). Đổi sang fetchgraph. Phân tích những thuộc tính EAGER ngoài graph.

### Bài 13. Hint namespace

Một dự án dùng Jakarta Persistence nhưng code setHint với **javax.persistence.fetchgraph**. Hãy nêu cách kiểm tra namespace tương ứng với JPA/provider version và vì sao không nên trộn hai hệ API.

### Bài 14. Query đã có entity managed

Service gọi find(PurchaseOrder.class, id) rồi gọi lần nữa với fetchgraph trong cùng EntityManager. Vì sao không nên dùng lần gọi thứ hai để benchmark hiệu quả graph? Hãy đề xuất setup test công bằng.

### Bài 15. Spring Data EntityGraphType

Viết hai repository methods dùng named graph PurchaseOrder.detail:
- type=FETCH;
- type=LOAD.

Giải thích với một EAGER association không liệt kê trong graph, hai method khác nhau về fetch requirements như thế nào.

### Bài 16. Nested attributePaths

Viết Spring Data JPA repository method:

~~~java
@EntityGraph(
    attributePaths = {"customer", "lines.product"}
)
~~~

Giải thích dấu chấm trong path và khác biệt giữa attributePaths của Spring Data và @NamedAttributeNode/@NamedSubgraph chuẩn JPA.

### Bài 17. @EntityGraph import

Trong cùng Java file, developer import **jakarta.persistence.EntityGraph** nhưng dùng:

~~~java
@EntityGraph(attributePaths = "customer")
~~~

tại repository method. Vì sao code không compile? Hãy sửa import sang annotation của Spring Data.

### Bài 18. JOIN FETCH với invoice optional

So sánh:

~~~java
select o from PurchaseOrder o
join fetch o.invoice
~~~

và:

~~~java
select o from PurchaseOrder o
left join fetch o.invoice
~~~

Giả sử PO-002 chưa có Invoice. Query nào có thể loại PO-002 khỏi root results? EntityGraph có tự áp một INNER JOIN semantics như vậy không?

### Bài 19. N+1 và query count

Tạo 50 PurchaseOrders, mỗi Order có Customer và Lines. Đo:
1. Truy vấn không graph rồi duyệt lines;
2. Truy vấn với graph lines;
3. Truy vấn với subgraph lines.product rồi đọc product names.

Đếm SQL statements trên provider cụ thể. Vì sao không nên assert **mọi graph phải luôn chỉ dùng một SELECT**?

### Bài 20. Page Orders có Lines

Có 100 Orders và 1.000 Lines. API yêu cầu pageSize=10 Orders, mỗi Order kèm Lines. Hãy thiết kế:
1. Query IDs có orderBy ổn định;
2. Query fetch graph cho page IDs;
3. Khôi phục thứ tự trang;
4. Count query riêng.

Giải thích vì sao LIMIT 10 SQL rows khi JOIN Lines không phải luôn là 10 Orders đầy đủ.

### Bài 21. Hai collection bags

PurchaseOrder có List<OrderLine> lines và List<OrderAttachment> attachments. Graph tải cả hai. Với Hibernate, lỗi nào có thể phát sinh? Ngoài exception, còn vấn đề cardinality nào nếu JOIN tạo 10 × 5 rows một Order? Đề xuất hai cách thay thế.

### Bài 22. Entity graph không phải DTO

Một endpoint chỉ trả orderNumber, status, customerName. So sánh:
- EntityGraph(customer);
- JPQL constructor DTO projection;
- JOIN FETCH customer rồi map entity.

Khi nào DTO có thể tiết kiệm chi phí và cho API contract rõ ràng hơn?

### Bài 23. Lazy ngoài transaction

Một service trả PurchaseOrder sau khi đóng persistence context. Controller gọi getLines().size(). Có thể phát lỗi gì khi lines chưa load? Hãy đề xuất fetch plan và mapping DTO trong @Transactional service.

### Bài 24. Trạng thái loaded theo JPA

Viết integration test dùng:

~~~java
emf.getPersistenceUnitUtil().isLoaded(
    order, "lines"
);
~~~

để xác nhận node lines được graph yêu cầu. Tại sao không nên assert customer ngoài fetchgraph bắt buộc là unloaded trên mọi provider?

### Bài 25. Static mapping thay đổi

Ban đầu customer EAGER, sau một lần refactor đổi thành LAZY. Graph chỉ có lines không thay đổi:
- Fetch graph sẽ thay đổi ý nghĩa gì?
- Load graph sẽ thay đổi ý nghĩa gì?
- Tại sao load graph phụ thuộc static mapping ngoài graph nhiều hơn?

### Bài 26. Kiểm thử tính đúng và hiệu năng

Thiết kế test matrix cho ba phương án:
- Static mapping;
- Fetch graph;
- Load graph.

Fixture có Orders với Invoice có/không, Lines rỗng/nhiều, Products chia sẻ giữa các Lines. Kiểm tra:
- Tập roots trả về;
- Những nodes yêu cầu đã loaded;
- Khả năng đọc data trong transaction;
- SQL count/row count;
- Pagination;
- Ảnh hưởng của warm first-level/L2 caches.

### Bài 27. Bảo mật dữ liệu

Một API chỉ cho phép role VIEWER đọc orderNumber và customerName. Một developer dùng fetchgraph {customer} rồi trả thẳng PurchaseOrder entity qua JSON.

Hãy giải thích vì sao graph không chặn các fields/associations khác bị serialize hoặc load khi truy cập. Đề xuất row-level authorization và response DTO.

### Bài 28. Chọn giải pháp theo mục tiêu

Hãy chọn một trong **FETCH graph / LOAD graph / JOIN FETCH / DTO projection / batch fetching** cho từng trường hợp:
1. Chỉ hiển thị ba scalar fields;
2. Chi tiết một Order cần Lines và Products;
3. Giữ customer/invoice EAGER đồng thời tải Lines;
4. Muốn EAGER ngoài graph được xem LAZY;
5. Page lớn có Lines;
6. Một query đơn giản cần LEFT JOIN một to-one;
7. Một danh sách dài có LAZY relation thường xuyên truy cập nhưng JOIN khiến rows phình lớn.

Giải thích trade-offs về fetch semantics và SQL performance.

## 22. Bảng tra cứu nhanh

| Nhu cầu | Cơ chế |
|---|---|
| Fetch những nodes liệt kê, unspecified xem LAZY | jakarta.persistence.fetchgraph |
| Fetch nodes liệt kê, unspecified theo static mapping | jakarta.persistence.loadgraph |
| Tạo graph động | em.createEntityGraph(EntityClass.class) |
| Thêm một/nhiều nodes | graph.addAttributeNodes(...) |
| Thêm nested relationship | graph.addSubgraph("relationship") |
| Thêm attribute sâu | subgraph.addAttributeNodes("targetAttribute") |
| Đặt tên graph tại entity | @NamedEntityGraph |
| Attribute trong named graph | @NamedAttributeNode |
| Nested named graph | @NamedSubgraph |
| Lấy named graph | em.getEntityGraph("LogicalName") |
| Áp graph cho query | query.setHint("jakarta.persistence.fetchgraph", graph) |
| Áp graph cho find | em.find(Entity.class, id, Map.of(hint, graph)) |
| Spring Data graph named | @EntityGraph(value="Name", type=FETCH/LOAD) |
| Spring Data graph ad hoc | @EntityGraph(attributePaths={"a", "a.b"}) |
| Kiểm tra loaded state | emf.getPersistenceUnitUtil().isLoaded(entity, attributeName) |
| Fetch relation bằng JPQL | JOIN FETCH / LEFT JOIN FETCH |
| Chỉ chọn vài fields | Constructor DTO/scalar projection |
| Tránh page to-many fetch | Page IDs rồi fetch graph cho IDs |
| Giảm nhiều lazy SELECTs | Graph subgraphs hoặc provider batch fetching |
| Không muốn nhiều bags cùng JOIN | Tách fetch queries/collections |
| So sánh SQL hiệu quả | Context riêng + statistics + query plan |

### 22.1. Nhớ nhanh bảng cốt lõi

| Unspecified attribute | Fetch graph | Load graph |
|---|---|---|
| Mapping EAGER | **Xem như LAZY** | **EAGER** |
| Mapping LAZY | **Xem như LAZY** | **LAZY** |

Đối với **specified attribute**, cả hai đều yêu cầu **EAGER**. Đây là cách nhanh nhất để nhớ khác biệt.

## 23. Checklist áp dụng trong dự án

Trước khi thêm EntityGraph hoặc đổi giữa FETCH và LOAD, xác định:

1. **Root entity là gì?** PurchaseOrder hay entity khác?
2. **Endpoint thực sự dùng attributes nào?** Không fetch theo mọi field có thể có.
3. **Mapping mặc định đã rõ chưa?** Đặc biệt ManyToOne/OneToOne EAGER.
4. **Muốn giữ EAGER ngoài graph hay xem chúng như LAZY?** Đây là điểm phân biệt LOAD/FETCH.
5. **Có hiểu rằng fetchgraph không cấm provider tải thêm?** Đừng assert unsupported guarantees.
6. **Có những relationship lồng sâu nào được truy cập?** Cần subgraph thích hợp.
7. **Có relationship node không có subgraph?** Xem default fetch graph của target.
8. **Graph name và attribute names có đúng không?** Dùng property Java, không tên cột DB.
9. **Đã chọn Jakarta hay javax hint namespace đúng version?**
10. **Spring @EntityGraph import có đúng annotation repository không?**
11. **Khi dùng named graph, có vô tình thêm attributePaths không?** Xem precedence.
12. **Có to-many collections trong graph không?** Đánh giá join cardinality.
13. **Có fetch nhiều List bags không?** Cẩn thận MultipleBagFetchException của Hibernate.
14. **Có Pageable/OFFSET với collection fetch không?** Xem query hai bước.
15. **Có orderBy ổn định cho paging không?** Dùng ID tie-breaker nếu cần.
16. **Có cần DTO projection thay entity graph không?** Đặc biệt read-only API.
17. **Có N+1 ở nhánh sâu hơn không?** lines được tải chưa chắc product đã tải.
18. **Có đo SQL statements và rows thực tế chưa?** Graph không cam kết JOIN duy nhất.
19. **Có provider-specific batch fetching phù hợp hơn không?** Không phải mọi collection đều nên eager.
20. **Đã test với persistence context sạch chưa?** Identity map có thể che khác biệt.
21. **L2 cache có làm benchmark sai lệch không?** Kiểm soát cache warm-up.
22. **Các nodes được graph yêu cầu có loaded đúng không?** Dùng PersistenceUnitUtil.
23. **Test có giả định unspecified luôn unloaded không?** Bỏ assertion không portable.
24. **Transaction boundary có rõ không?** Map DTO trước khi context đóng.
25. **Graph có đang bị dùng như một rào bảo mật không?** Đó là sai mục đích.
26. **Các điều kiện tenant/owner/soft-delete được áp ở WHERE chưa?**
27. **Graph động có được build độc lập theo request không?** Tránh shared mutable state.
28. **Các performance metrics có phản ánh cùng công việc không?** So sánh đồng mức dữ liệu được sử dụng.

### 23.1. Sơ đồ quyết định

~~~text
Cần tải dữ liệu với JPA
       |
       +-- Chỉ cần một số scalar fields?
       |       |
       |       +-- Có → DTO / scalar projection
       |
       +-- Cần entity và associations?
               |
               +-- Fetch plan có trong query cụ thể?
               |       |
               |       +-- Cần LEFT/INNER semantics tường minh?
               |               → JOIN FETCH (chú ý pagination)
               |
               +-- Muốn dùng EntityGraph?
                       |
                       +-- Unspecified EAGER vẫn phải theo mapping?
                       |       |
                       |       +-- Có → LOAD graph
                       |       |
                       |       +-- Không, muốn xem như LAZY → FETCH graph
                       |
                       +-- Có nested associations?
                       |       → Thêm subgraph
                       |
                       +-- Có to-many với phân trang?
                               → Page root IDs trước
                                 rồi fetch graph cho trang
~~~

## 24. Tổng kết

**Fetch graph** và **load graph** là hai cách áp dụng một EntityGraph trong Jakarta Persistence. Chúng đều yêu cầu tải sớm các attribute nodes được chỉ định, nhưng có sự khác biệt quyết định:

- **Fetch graph:** thuộc tính ngoài graph được **xem như LAZY** theo graph semantics, bất kể static mapping trước đó là EAGER hay LAZY.
- **Load graph:** thuộc tính ngoài graph **giữ fetch type trong mapping**; EAGER vẫn EAGER và LAZY vẫn LAZY.
- **Cả hai:** provider có thể fetch thêm state và được quyền chọn SQL strategy phù hợp; graph **không bảo đảm chỉ tải đúng nodes liệt kê hoặc dùng một SQL JOIN duy nhất**.

Để dùng đúng trong dự án, cần xem fetch plan theo **từng use case**, thêm **subgraph** cho những quan hệ lồng nhau, cân nhắc **JOIN FETCH so với DTO projection**, và đặc biệt tránh fetch collection to-many quá rộng khi phân trang. Kiểm thử bằng **PersistenceUnitUtil**, SQL statistics và integration tests trên provider mục tiêu giúp xác nhận both semantics và hiệu năng.

Ghi nhớ ngắn:

~~~text
Specified attributes:
    FETCH graph → EAGER
    LOAD graph  → EAGER

Unspecified EAGER mapping:
    FETCH graph → treated as LAZY
    LOAD graph  → EAGER

Unspecified LAZY mapping:
    FETCH graph → treated as LAZY
    LOAD graph  → LAZY

Provider may fetch more state than the graph requests.
Entity graph specifies WHAT is needed, not EXACT SQL HOW.
~~~

**Nguyên tắc thực hành:** chọn **load graph** khi muốn *bổ sung* những association cần thiết trên nền static mapping; chọn **fetch graph** khi muốn *diễn đạt rõ phạm vi yêu cầu fetch của use case*, đặc biệt đối với những EAGER associations không thuộc graph. Không dùng một trong hai như cơ chế bảo mật, DTO projection hoặc lời hứa mọi lazy field đều không được nạp.











