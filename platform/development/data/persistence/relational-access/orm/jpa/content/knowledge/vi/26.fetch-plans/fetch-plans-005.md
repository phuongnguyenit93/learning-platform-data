# Vấn đề truy cập dữ liệu chưa tải sau khi ngữ cảnh kết thúc trong JPA

Trong Java Persistence API (JPA), một entity có thể chứa những quan hệ chưa được tải ngay từ database. Khi ứng dụng đọc `PurchaseOrder`, JPA có thể chỉ lấy các cột của bảng đơn hàng, còn `OrderLine`, `Customer` hoặc những liên kết khác sẽ được tải khi code thực sự truy cập. Cơ chế này thường được gọi là **lazy loading**.

Lazy loading hữu ích vì tránh tải một đồ thị đối tượng rất lớn cho mọi truy vấn. Nhưng nó kéo theo một điều kiện: **những dữ liệu chưa được tải thường cần một persistence context/session còn hoạt động để truy xuất tiếp từ database**.

Một lỗi điển hình:

~~~java
PurchaseOrder order = orderService.findOrder(orderId);

// Khi controller/serializer đã ở ngoài persistence context:
int count = order.getLines().size();
~~~

Nếu `lines` chưa được khởi tạo và entity đã detached, Hibernate thường ném:

~~~text
org.hibernate.LazyInitializationException:
failed to lazily initialize a collection of role ...
could not initialize proxy - no Session
~~~

Đây không phải lỗi của `size()` hay của `List` nói chung. Code đang yêu cầu ORM tải thêm dữ liệu **sau khi cơ chế quản lý entity đã kết thúc hoặc không còn cho phép tải tiếp**.

Bài học này tập trung vào cách nhận diện nguyên nhân, phân biệt transaction và persistence context, xác định phần dữ liệu nào đã được tải, rồi thiết kế fetch plan phù hợp qua `JOIN FETCH`, entity graph, DTO projection, transaction boundary và các chiến lược truy vấn khác. Mục tiêu là sửa **nguyên nhân của truy cập dữ liệu chưa tải**, không chỉ che exception.

## 1. Bài toán thực tế: API trả chi tiết đơn hàng

Giả sử hệ thống bán hàng có quan hệ:

~~~text
Customer 1 -------- N PurchaseOrder
                           |
                           | 1
                           |
                           N OrderLine
                           |
                           | N
                           |
                           1 Product
~~~

Màn hình **danh sách đơn hàng** chỉ cần mã đơn, trạng thái, thời gian tạo và tổng tiền. Màn hình **chi tiết đơn hàng** còn cần tên khách hàng và các dòng hàng.

Hai màn hình có nhu cầu dữ liệu khác nhau:

| Use case | Cần đọc | Không nhất thiết cần |
|---|---|---|
| Danh sách đơn | ID, mã đơn, trạng thái, tổng tiền | Toàn bộ `lines` và chi tiết `product` |
| Chi tiết đơn | Thông tin đơn, tên khách, các dòng hàng | Những association không hiển thị |
| Báo cáo tổng doanh thu | Tổng tiền, nhóm theo ngày | Object graph các entity |
| Tác vụ cập nhật trạng thái | ID, version, trạng thái và dữ liệu nghiệp vụ liên quan | Mọi collection nếu không dùng |

Nếu luôn tải toàn bộ đồ thị đơn hàng, ứng dụng dễ chậm, dùng nhiều RAM và phát sinh JOIN lớn. Nếu để mọi quan hệ lazy rồi trả entity trực tiếp ra bên ngoài, dữ liệu có thể chưa được tải khi controller/serializer truy cập.

**Bài toán cần giải là xác định đúng tập dữ liệu cho mỗi use case và tải nó trước khi kết thúc phạm vi quản lý truy vấn.**

## 2. Persistence context là gì?

Persistence context là tập các entity instance mà `EntityManager` hiện quản lý cùng trạng thái đồng bộ liên quan. Khi một entity còn **managed**:

- JPA có thể theo dõi các thay đổi của nó để flush.
- Identity map giúp cùng một identity có thể tương ứng cùng managed instance trong context.
- Provider có thể thực hiện một số thao tác lazy loading khi association chưa tải và điều kiện runtime cho phép.
- Các query khác có thể tương tác với những object đã managed.

Có thể hình dung:

~~~text
             EntityManager
                   |
                   v
           Persistence Context
                   |
           +-------+-------+
           |               |
           v               v
     Order #101        Customer #8
     (managed)         (managed/proxy)
           |
           v
       lines: LAZY
       (chưa tải)
           |
           | Khi truy cập trong bối cảnh phù hợp
           v
       SELECT order_line ...
~~~

Khi context đóng, bị clear hoặc entity bị detach, entity trở thành **detached**. Các giá trị đã nạp có thể vẫn đọc được từ Java object, nhưng association chưa tải thường không còn cơ chế hợp lệ để tự truy vấn tiếp.

### 2.1. Persistence context khác database connection

Persistence context không đơn thuần là JDBC connection. Nó có identity map, snapshots, managed entities và các quy tắc vòng đời. Một connection có thể được lấy/trả về pool ở các thời điểm khác nhau tùy provider và transaction manager.

Vì vậy câu “còn connection là lazy loading sẽ chạy” không diễn đạt đúng nguyên tắc. Vấn đề trọng tâm là **entity còn gắn với persistence context/session có khả năng thực hiện việc tải chưa?**

### 2.2. Persistence context khác transaction

Hai khái niệm liên quan nhưng không đồng nhất:

- **Transaction** xác định phạm vi nguyên tử, commit/rollback và các quy tắc isolation/locking của những thao tác DB.
- **Persistence context** xác định phạm vi entity managed, identity map và trạng thái đã/chưa tải.
- Trong mô hình transaction-scoped thông thường, context kết thúc khi transaction kết thúc theo cách container/framework quản lý.
- Một application-managed `EntityManager` có thể còn mở qua nhiều transaction; extended persistence context cũng có vòng đời dài hơn một transaction.
- Spring Open EntityManager in View có thể giữ EntityManager mở qua giai đoạn render response, mặc dù service transaction đã hoàn tất.

Do đó không được khẳng định **“vừa commit là mọi lazy access chắc chắn thất bại”** hay **“còn transaction thì mọi lazy access luôn thành công”**. Cần xem phạm vi EntityManager/session và cấu hình thực tế.

## 3. Managed, detached và dữ liệu đã tải

Một entity JPA thường trải qua những trạng thái:

~~~text
new/transient
       |
       | persist()
       v
    managed
       |
       +-- flush / query / lazy loading
       |
       +-- detach(entity), clear(), close()
       |                         |
       v                         v
    detached  <-------------  context kết thúc
       |
       | merge()
       v
managed copy (instance do merge trả về)
~~~

Trong phần lớn trường hợp:

- Object managed có thể truy cập association lazy khi provider/session phù hợp.
- Object detached **vẫn là một Java object**; các field basic đã tải vẫn đọc được.
- Collection đã được khởi tạo đầy đủ trước khi detach thường tiếp tục sử dụng được về mặt dữ liệu đang có.
- Collection hoặc proxy **chưa được khởi tạo** có thể thất bại khi code đòi đọc nội dung sau detach.
- Một association đã load không đồng nghĩa **mọi association lồng sâu bên trong** đều đã load.

Ví dụ:

~~~text
PurchaseOrder #101        đã tải
  ├─ id                    đã tải
  ├─ orderNumber           đã tải
  ├─ status                đã tải
  ├─ customer              chưa tải
  └─ lines                 đã tải
       ├─ Line #1          đã tải
       │    └─ product     chưa tải
       └─ Line #2          đã tải
            └─ product     chưa tải
~~~

Sau khi context kết thúc, code có thể duyệt hai Line đã tải nhưng vẫn gặp lỗi khi truy cập `line.getProduct().getName()`. Điều cần kiểm tra là **toàn bộ những thuộc tính mà use case sẽ đọc**, không chỉ collection đầu tiên.

## 4. LAZY và EAGER theo chuẩn JPA

JPA có `FetchType.LAZY` và `FetchType.EAGER`:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
~~~

Ý nghĩa khái quát:

- **LAZY**: yêu cầu provider trì hoãn tải thuộc tính khi chưa cần; đối với một số loại mapping, LAZY là hint và khả năng thực thi phụ thuộc provider.
- **EAGER**: yêu cầu thuộc tính được tải theo ngữ nghĩa fetch strategy; provider có quyền chọn JOIN, secondary SELECT hoặc cách thực thi phù hợp.
- EAGER không đồng nghĩa luôn một SQL duy nhất.
- LAZY không đảm bảo mọi truy vấn sẽ không tải thuộc tính đó: fetch join, entity graph hoặc provider có thể fetch thêm.

### 4.1. Default fetch types dễ bị quên

| Mapping | Fetch mặc định theo JPA |
|---|---|
| `@OneToMany` | LAZY |
| `@ManyToMany` | LAZY |
| `@ElementCollection` | LAZY |
| `@ManyToOne` | EAGER |
| `@OneToOne` | EAGER |
| `@Basic` | EAGER |

Nếu code không đặt `fetch = FetchType.LAZY` cho một `@ManyToOne`, mặc định JPA là EAGER. Trong dự án có nhiều quan hệ to-one, default EAGER có thể làm query tải nhiều dữ liệu hơn dự kiến.

### 4.2. To-one LAZY có giới hạn triển khai

Một số provider có thể dùng proxy, bytecode enhancement hoặc cơ chế khác để hỗ trợ lazy loading to-one/basic attributes. Với certain one-to-one mappings hoặc field access patterns, khả năng tải trì hoãn có thể cần cấu hình đặc thù.

Không lấy một quan hệ `@OneToOne(fetch = LAZY)` để kết luận nó **chắc chắn chưa tải** trên mọi provider. Hãy quan sát SQL và trạng thái loaded trên stack thực tế.

### 4.3. Fetch strategy không phải quyền truy cập

EAGER/LAZY ảnh hưởng kế hoạch tải dữ liệu, không thay thế authorization. Một thuộc tính nhạy cảm đã được load vào entity vẫn cần được bảo vệ khi chuyển sang response DTO/JSON.

## 5. Entity minh họa

Để hiểu vấn đề một cách cụ thể, giả sử ứng dụng dùng ba entity: `Customer`, `PurchaseOrder` và `OrderLine`.

### 5.1. Customer

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected Customer() {}

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

### 5.2. PurchaseOrder

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "total_amount", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal totalAmount;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderLine> getLines() {
        return lines;
    }
}
~~~

### 5.3. OrderLine

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

import java.math.BigDecimal;

@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_sku", nullable = false)
    private String productSku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal unitPrice;

    protected OrderLine() {}

    public Long getId() {
        return id;
    }

    public String getProductSku() {
        return productSku;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }
}
~~~

Schema ý tưởng:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    version BIGINT NOT NULL,
    customer_id BIGINT NOT NULL REFERENCES customer(id)
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id),
    product_sku VARCHAR(60) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(14, 2) NOT NULL
);
~~~

Đây là mô hình minh họa, không phải migration đầy đủ có cấu hình sinh ID và tất cả constraint.

## 6. Tái hiện lỗi: EntityManager đã đóng

Một ví dụ JPA resource-local:

~~~java
EntityManager em = emf.createEntityManager();

PurchaseOrder order;

try {
    order = em.find(PurchaseOrder.class, orderId);
} finally {
    em.close();
}

// Entity đã không còn được quản lý bởi EntityManager cũ.
System.out.println(order.getOrderNumber());

// Có thể phát sinh lỗi với provider dùng lazy collections:
System.out.println(order.getLines().size());
~~~

Hai lời gọi có điểm khác biệt:

- `getOrderNumber()` thường chỉ đọc một basic field đã được nạp.
- `getLines().size()` có thể khiến ORM cần truy vấn bảng `order_line` nếu collection chưa được tải.

Không có session/persistence context có khả năng truy vấn ở thời điểm thứ hai; Hibernate thường ném `LazyInitializationException`.

### 6.1. Lỗi chỉ xảy ra khi thuộc tính chưa được tải?

Đúng về nguyên nhân cơ bản: nếu collection đã được khởi tạo hoàn toàn trước khi đóng context, dữ liệu đó có thể vẫn đọc được sau detach.

~~~java
EntityManager em = emf.createEntityManager();
PurchaseOrder order;

try {
    order = em.find(PurchaseOrder.class, orderId);

    // Khi context còn hoạt động, buộc duyệt collection.
    order.getLines().size();
} finally {
    em.close();
}

// Duyệt collection đã khởi tạo có thể hoạt động.
for (OrderLine line : order.getLines()) {
    System.out.println(line.getProductSku());
}
~~~

Nhưng đây chỉ là **minh họa cơ chế**, không phải khuyến nghị mặc định gọi `size()` để ép load trong mọi service. `size()` có thể có tối ưu riêng tùy provider/collection; muốn bảo đảm một fetch plan rõ ràng, ưu tiên query/graph/DTO được thiết kế cho use case.

### 6.2. Các field lồng sâu vẫn có thể chưa tải

Nếu mỗi OrderLine có quan hệ LAZY `product`, tải `lines` không nhất thiết làm `product` được tải. Điều kiện để an toàn sau detach là **những dữ liệu thực sự sẽ được dùng đều đã có sẵn**, không chỉ parent collection.

## 7. Hibernate LazyInitializationException và JPA standard

`org.hibernate.LazyInitializationException` là exception **riêng Hibernate**. JPA quy định persistence context và fetch semantics nhưng không yêu cầu mọi provider ném chính xác cùng class exception trong mọi tình huống unloaded detached access.

Ví dụ một log Hibernate:

~~~text
org.hibernate.LazyInitializationException:
could not initialize proxy [Customer#42] - no Session
~~~

hoặc:

~~~text
failed to lazily initialize a collection of role:
com.example.shop.domain.PurchaseOrder.lines
could not initialize proxy - no Session
~~~

Diễn giải:

- Có một proxy hoặc collection wrapper chưa được khởi tạo.
- Code đang cố lấy dữ liệu bên trong nó.
- Hibernate Session cần thiết không còn gắn với object hoặc đã đóng.

### 7.1. Đừng nhầm với `EntityNotFoundException`

`EntityNotFoundException` có thể xuất hiện khi proxy trỏ tới entity không tồn tại trong DB khi cần tải. Đây là vấn đề **identity tham chiếu không tìm thấy** hoặc dữ liệu nhất quán, khác với việc context/session đã đóng.

### 7.2. Đừng nhầm với `NullPointerException`

Nếu `order.getCustomer() == null` vì một association optional không có giá trị, truy cập `getDisplayName()` sẽ gây NullPointerException. Nếu customer là proxy nhưng không có session để initialize, Hibernate có thể ném LazyInitializationException. Hai lỗi khác nhau về dữ liệu và cơ chế.

### 7.3. Đừng nhầm với `LazyInitializationException` trong ứng dụng không dùng Hibernate

Dự án EclipseLink hoặc provider khác có thể dùng exception/behavior riêng. Chẩn đoán nên dựa trên **thuộc tính chưa tải, trạng thái entity và vòng đời context**, không chỉ tìm một tên exception cụ thể.

## 8. Dòng thời gian của lỗi trong kiến trúc nhiều lớp

Mẫu code dễ gặp:

~~~text
HTTP Request
    |
    v
Controller
    |
    v
Service @Transactional
    |
    +-- repository.findById(id)
    |      |
    |      +-- SELECT purchase_order ...
    |      +-- lines còn LAZY
    |
    +-- return PurchaseOrder
    |
    v
Service transaction kết thúc
    |
    +-- Transaction-scoped context có thể đóng
    |
    v
Controller trả entity
    |
    v
JSON Serializer
    |
    +-- gọi getOrderNumber()    -> đã tải
    +-- gọi getLines()          -> cần lazy load
    |
    v
LazyInitializationException
~~~

Điểm gây lỗi thường **không nằm trong repository query**. Lỗi nổ ra muộn hơn tại controller, mapper hoặc serializer khi code chạm thuộc tính chưa tải.

### 8.1. Ví dụ service trả entity trực tiếp

~~~java
@Service
public class OrderService {

    private final PurchaseOrderRepository repository;

    public OrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public PurchaseOrder findOrder(Long id) {
        return repository.findById(id)
            .orElseThrow();
    }
}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public PurchaseOrder details(@PathVariable Long id) {
        return service.findOrder(id);
    }
}
~~~

Framework JSON serialization có thể truy cập `getLines()` **sau khi service transaction đã hoàn tất**. Nếu persistence context không được giữ mở bởi cơ chế khác, đây là điều kiện dẫn đến lazy initialization failure.

### 8.2. Vì sao API có lúc lỗi, có lúc không?

Một số khả năng:

- Quan hệ đã được khởi tạo bởi query trước đó trong cùng context.
- HTTP request khác có fetch plan khác.
- Open EntityManager in View đang bật ở một môi trường nhưng tắt ở môi trường khác.
- Test dùng transaction bao phủ cả bước serialize nhưng production thì không.
- Provider có caching/enhancement khác nhau.
- Serializer đọc một nhánh association khác tùy JSON view.

Sự không nhất quán trong biểu hiện **không làm vấn đề biến mất**. Cần thiết kế data boundary rõ cho từng use case.

## 9. Transaction kết thúc có đồng nghĩa context kết thúc?

Không hoàn toàn.

### 9.1. Transaction-scoped context

Ở nhiều ứng dụng Spring/Jakarta EE, persistence context gắn với transaction hoặc operation scope. Khi transaction kết thúc, entity thường không còn được quản lý ở một EntityManager có thể phục vụ lazy loading ngoài tầng dữ liệu.

Đây là tình huống phổ biến khiến DTO mapper chạy sau service transaction bị lỗi.

### 9.2. Application-managed EntityManager

Một `EntityManager` do application tự tạo:

~~~java
EntityManager em = emf.createEntityManager();
~~~

có thể còn mở sau một transaction đã commit. Trong một số cấu hình, thao tác đọc/lazy loading có thể tiếp tục khi EM mở, theo quy tắc provider và yêu cầu transaction. Vì vậy không thể chỉ dựa vào `commit()` để suy ra tất cả LAZY đều hỏng.

Tuy nhiên, giữ EM mở tùy tiện để các phần code khác tự truy cập DB thường làm vòng đời dữ liệu khó kiểm soát.

### 9.3. Extended persistence context

Trong một số mô hình Jakarta EE, extended persistence context có thể tồn tại qua nhiều giao dịch. Nó là lựa chọn kiến trúc đặc thù, không phải mẹo mặc định cho REST API để tránh LazyInitializationException.

### 9.4. Open EntityManager in View

Spring có cơ chế giữ EntityManager mở qua giai đoạn xử lý view/response. Khi bật, JSON serializer đôi khi có thể truy cập LAZY dù service transaction đã xong.

Nhưng việc “không còn exception” **không chứng minh fetch plan đã đúng**: serializer có thể phát sinh những SELECT mới ở ngoài service transaction, tạo N+1 hoặc làm tăng thời gian giữ tài nguyên.

## 10. Cách sửa ưu tiên: Trả DTO đã hoàn thiện bên trong service

Với REST API, một giải pháp rõ ràng là **không để tầng web tự duyệt entity graph**. Service/query layer trả một DTO mô tả đúng dữ liệu API cần.

DTO:

~~~java
package com.example.shop.api;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record OrderLineView(
    Long id,
    String productSku,
    int quantity,
    BigDecimal unitPrice
) {}

public record OrderDetailsView(
    Long id,
    String orderNumber,
    Instant createdAt,
    BigDecimal totalAmount,
    String customerName,
    List<OrderLineView> lines
) {}
~~~

### 10.1. Chuyển thành DTO trong transaction

~~~java
@Service
public class OrderQueryService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public OrderDetailsView getDetails(Long orderId) {

        PurchaseOrder order =
            em.find(PurchaseOrder.class, orderId);

        if (order == null) {
            throw new NoSuchElementException(
                "Order not found: " + orderId
            );
        }

        String customerName =
            order.getCustomer().getDisplayName();

        List<OrderLineView> lineViews =
            order.getLines().stream()
                .map(line -> new OrderLineView(
                    line.getId(),
                    line.getProductSku(),
                    line.getQuantity(),
                    line.getUnitPrice()
                ))
                .toList();

        return new OrderDetailsView(
            order.getId(),
            order.getOrderNumber(),
            order.getCreatedAt(),
            order.getTotalAmount(),
            customerName,
            lineViews
        );
    }
}
~~~

Trong ví dụ này, việc truy cập `customer` và `lines` được thực hiện **bên trong phạm vi service transactional**, trước khi trả DTO. DTO chứa dữ liệu Java thông thường, không có Hibernate proxy hoặc lazy collection cần database để serialize.

### 10.2. Controller chỉ nhận DTO

~~~java
@GetMapping("/{id}")
public OrderDetailsView details(@PathVariable Long id) {
    return orderQueryService.getDetails(id);
}
~~~

Serializer không cần gọi `getLines()` trên entity detached. Cấu trúc response cũng không vô tình mở rộng khi developer thêm một association mới vào entity.

### 10.3. DTO không tự bảo đảm query hiệu quả

Code mapper trên có thể thực hiện:

- Một SELECT Order.
- Một SELECT Customer khi truy cập `getCustomer()`.
- Một SELECT Lines khi truy cập `getLines()`.

Với **một order**, chi phí có thể chấp nhận được. Với danh sách hàng trăm order, cách map tương tự có thể gây N+1. Vì vậy cần phối hợp **DTO boundary** với **fetch plan/truy vấn phù hợp**.

### 10.4. DTO bảo vệ hợp đồng API

Không trả trực tiếp entity giúp:

- Không vô tình serialize field nhạy cảm.
- Không phát sinh vòng tham chiếu `Order -> Lines -> Order`.
- Không làm cấu trúc JSON phụ thuộc annotation lazy/eager.
- Có thể version API mà không đổi mapping entity.
- Không đưa đối tượng managed/detached sang một tầng chỉ nên xử lý dữ liệu trình bày.

**Đây thường là lựa chọn ưu tiên cho API**, nhưng không có nghĩa mọi ứng dụng đều phải dùng cùng dạng DTO cho mọi use case.

## 11. Chọn fetch plan bằng JPQL JOIN FETCH

Nếu use case biết trước sẽ cần `customer` và `lines` của một Order, có thể khai báo điều đó ngay trong JPQL.

~~~java
TypedQuery<PurchaseOrder> query = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    JOIN FETCH o.customer
    LEFT JOIN FETCH o.lines
    WHERE o.id = :id
    """,
    PurchaseOrder.class
);

PurchaseOrder order = query
    .setParameter("id", orderId)
    .getSingleResult();
~~~

Ý nghĩa:

- `JOIN FETCH o.customer` yêu cầu tải Customer cùng truy vấn entity.
- `LEFT JOIN FETCH o.lines` yêu cầu tải collection Lines, kể cả Order chưa có dòng.
- `DISTINCT` diễn đạt kết quả root Order duy nhất theo ngữ nghĩa JPQL, tránh kết quả parent bị nhân bản ở tầng entity khi join to-many. SQL và cơ chế khử trùng cụ thể do provider xử lý.
- Query có filter theo **một Order ID**, nên không vướng bài toán phân trang một tập lớn root.

Sau khi query hoàn tất, nếu các association được fetch theo yêu cầu đã khởi tạo, DTO mapper có thể truy cập chúng mà không kích hoạt truy vấn lazy bổ sung cho hai association đó.

### 11.1. JOIN FETCH không phải SELECT JOIN thông thường

~~~jpql
SELECT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.quantity > 0
~~~

JOIN trên đây dùng để lọc dữ liệu; nó **không đồng nghĩa collection `o.lines` được đánh dấu đã fetch**.

Trong khi:

~~~jpql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.lines
~~~

là yêu cầu tải association.

### 11.2. FETCH JOIN không nhất thiết tối ưu cho mọi màn hình

Khi một Order có 500 Lines, SQL join có thể trả 500 hàng để materialize một parent. Nếu fetch nhiều collection cùng lúc, số hàng có thể tăng rất mạnh.

Không có quy tắc “cứ LazyInitializationException thì thêm JOIN FETCH tất cả associations”.

### 11.3. Nested associations vẫn cần xem riêng

Nếu `OrderLine` có quan hệ LAZY `product`, câu:

~~~jpql
JOIN FETCH o.customer
LEFT JOIN FETCH o.lines
~~~

không nhất thiết tải từng `line.product`. Chỉ yêu cầu fetch các association thực sự cần, có thể qua thêm query riêng hoặc graph/subgraph phù hợp.

## 12. Entity graph: Kế hoạch tải độc lập với cấu trúc JPQL

JPA hỗ trợ `EntityGraph` để yêu cầu những association cụ thể được fetch, mà không nhất thiết viết `JOIN FETCH` vào mọi câu JPQL.

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");
graph.addAttributeNodes("lines");

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    Map.of("jakarta.persistence.fetchgraph", graph)
);
~~~

Hoặc dùng trên query:

~~~java
TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o WHERE o.id = :id",
    PurchaseOrder.class
);

query.setParameter("id", orderId);
query.setHint("jakarta.persistence.loadgraph", graph);

PurchaseOrder order = query.getSingleResult();
~~~

### 12.1. Phân biệt fetchgraph và loadgraph

| Hint | Ý nghĩa chính |
|---|---|
| `jakarta.persistence.fetchgraph` | Yêu cầu fetch các thuộc tính trong graph; thuộc tính không liệt kê tuân theo ngữ nghĩa fetch graph với giới hạn provider |
| `jakarta.persistence.loadgraph` | Yêu cầu fetch các thuộc tính trong graph; thuộc tính không liệt kê theo fetch strategy mặc định của mapping |

Provider có thể fetch nhiều hơn mức tối thiểu và không cam kết mọi graph sẽ thành **một SQL JOIN duy nhất**.

### 12.2. Named entity graph

Nếu cùng một fetch plan được tái sử dụng:

~~~java
@NamedEntityGraph(
    name = "PurchaseOrder.details",
    attributeNodes = {
        @NamedAttributeNode("customer"),
        @NamedAttributeNode("lines")
    }
)
@Entity
public class PurchaseOrder {
    // ...
}
~~~

Sau đó:

~~~java
EntityGraph<?> graph =
    em.getEntityGraph("PurchaseOrder.details");

TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o WHERE o.id = :id",
    PurchaseOrder.class
);

query.setParameter("id", orderId);
query.setHint("jakarta.persistence.fetchgraph", graph);
~~~

Khai báo annotation ở ví dụ chỉ thể hiện phần liên quan; class vẫn cần `@Id` và mapping đầy đủ.

### 12.3. Khi nào entity graph phù hợp?

- Cùng câu JPQL nhưng nhiều màn hình cần fetch plan khác nhau.
- Có association cần cho DTO mà muốn khai báo ngoài query string.
- Cần một tên fetch plan có thể tái sử dụng.
- Dự án dùng Spring Data và `@EntityGraph` trên repository method.

Entity graph không giải quyết tự động projection, phân trang to-many và authorization. Chọn các association có chủ đích.

## 13. Spring Data JPA: @EntityGraph cho một method

Nếu dùng Spring Data:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(
        attributePaths = {"customer", "lines"}
    )
    @Query("""
        SELECT o
        FROM PurchaseOrder o
        WHERE o.id = :id
        """)
    Optional<PurchaseOrder> findDetailsById(
        @Param("id") Long id
    );
}
~~~

Các import tương ứng:

~~~java
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
~~~

Khi service gọi method này trong transaction phù hợp, những association được yêu cầu sẽ được tải theo kế hoạch provider.

### 13.1. Repository entity graph không làm controller transaction-safe

Nếu repository fetch `customer` và `lines` nhưng controller lại truy cập association khác chưa tải, lỗi vẫn có thể xảy ra sau khi context kết thúc.

**Fetch plan phải bám use case**, không chỉ thêm graph để làm một lỗi cụ thể biến mất rồi bỏ qua phần còn lại của object graph.

### 13.2. Không giả định graph luôn giải quyết N+1

Entity graph có thể thay đổi số SQL, nhưng cách provider thực thi tùy mapping/dialect/cache. Bắt buộc kiểm tra SQL log hoặc statistics với dữ liệu thực.

## 14. DTO projection ngay trong JPQL

Nếu màn hình danh sách chỉ cần một số scalar fields, có thể không cần nạp entity rồi chuyển đổi.

DTO:

~~~java
package com.example.shop.api;

import java.math.BigDecimal;

public record OrderListItem(
    Long id,
    String orderNumber,
    BigDecimal totalAmount,
    String customerName
) {}
~~~

JPQL constructor expression:

~~~java
List<OrderListItem> items = em.createQuery(
    """
    SELECT new com.example.shop.api.OrderListItem(
        o.id,
        o.orderNumber,
        o.totalAmount,
        c.displayName
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    WHERE o.totalAmount >= :minTotal
    ORDER BY o.id DESC
    """,
    OrderListItem.class
)
.setParameter("minTotal", new BigDecimal("100000.00"))
.setMaxResults(50)
.getResultList();
~~~

Kết quả là các `OrderListItem` thuần Java. Không có `PurchaseOrder.lines` chưa tải mà serializer vô tình truy cập.

### 14.1. Projection có ưu điểm gì?

- Chỉ chọn trường cần cho màn hình.
- Không cần tạo managed entity cho mỗi dòng khi chỉ đọc báo cáo.
- Dữ liệu trả ra không có lazy association.
- Có thể kiểm soát rõ authorization và response fields.
- Giảm nguy cơ N+1 khi đọc một số association to-one trong câu SELECT.

### 14.2. Projection không hoàn toàn thay thế entity graph

Nếu use case cần **một object graph phức tạp** để thực hiện nghiệp vụ, managed entity và fetch plan có thể phù hợp hơn. Nếu chỉ xây JSON/list/report, projection thường đơn giản hơn.

### 14.3. Danh sách collection không tự động nằm trong một DTO constructor

Một JPQL constructor expression không mặc định gộp nhiều OrderLine thành `List<OrderLineView>` bên trong một OrderDetailsView. Với màn hình có parent và nhiều children, có thể:

1. Query parent summary.
2. Query tất cả line summaries theo parent ID.
3. Group các lines theo orderId ở Java.
4. Tạo DTO đã hoàn thiện trước khi trả về.

Cách này thường dễ kiểm soát pagination và không cần collection lazy bên ngoài transaction.

## 15. Dùng hai truy vấn để dựng DTO chi tiết

Không nhất thiết ép mọi thông tin vào một query có fetch join collection.

Ví dụ query header:

~~~java
OrderListItem header = em.createQuery(
    """
    SELECT new com.example.shop.api.OrderListItem(
        o.id, o.orderNumber, o.totalAmount, c.displayName
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    WHERE o.id = :id
    """,
    OrderListItem.class
)
.setParameter("id", orderId)
.getSingleResult();
~~~

Query lines:

~~~java
List<OrderLineView> lines = em.createQuery(
    """
    SELECT new com.example.shop.api.OrderLineView(
        l.id, l.productSku, l.quantity, l.unitPrice
    )
    FROM OrderLine l
    WHERE l.order.id = :orderId
    ORDER BY l.id
    """,
    OrderLineView.class
)
.setParameter("orderId", orderId)
.getResultList();
~~~

Sau đó service tạo một response DTO hoàn chỉnh từ `header` và `lines`.

### 15.1. Hai query không nhất thiết kém hơn một query

Một JOIN vào collection lớn có thể lặp lại nhiều cột của Order trên mỗi hàng. Hai query có thể truyền ít dữ liệu hơn và dễ phân trang. Tuy nhiên, đổi lại có thêm round trip; cần đo theo workload.

### 15.2. Tính nhất quán giữa hai SELECT

Nếu transaction khác thay đổi dữ liệu giữa query header và lines, kết quả có thể thuộc các thời điểm khác nhau tùy isolation và transaction strategy.

Đối với màn hình đọc thông thường, mức nhất quán này có thể chấp nhận. Đối với báo cáo tài chính hoặc quyết định nghiệp vụ bắt buộc nhất quán, cần transaction isolation/snapshot hoặc truy vấn thích hợp.

### 15.3. Không trả DTO dở dang

Nếu service trả một DTO chứa `Supplier<List<OrderLineView>>` để controller gọi sau, bạn chỉ chuyển vấn đề lazy loading từ entity sang abstraction khác. Với response đồng bộ, nên hoàn thành truy vấn và materialize dữ liệu cần thiết trong query layer.

## 16. N+1: Một lỗi khác có cùng gốc fetch plan

Giả sử:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(
        order.getCustomer().getDisplayName()
    );
}
~~~

Nếu `customer` là LAZY và mỗi Order có Customer chưa tải, provider có thể tạo:

~~~text
1 SELECT để tải danh sách Orders
N SELECT để tải Customer cho từng Order/Customer chưa có
--------------------------------------------------------
1 + N SQL queries (kịch bản xấu)
~~~

Đây là **N+1 query problem**. Khác biệt:

- **LazyInitializationException**: truy cập dữ liệu chưa tải khi context/session không còn khả năng tải.
- **N+1**: context còn mở nên lazy loading chạy được, nhưng sinh quá nhiều query.

Một “cách sửa” làm context mở lâu hơn có thể khiến LazyInitializationException biến mất nhưng **N+1 trở nên khó phát hiện hơn**.

### 16.1. Khi nào N+1 xảy ra ít hơn?

Nếu nhiều Order cùng Customer hoặc second-level cache có dữ liệu, số SQL bổ sung có thể nhỏ hơn N. Không vì thế mà thiết kế mặc định truy cập lazy association trong vòng lặp không cần đo lường.

### 16.2. Cách xử lý

- JPQL projection trên các field cần dùng.
- JOIN FETCH to-one association phù hợp.
- EntityGraph cho use case.
- Batch fetching hoặc subselect fetching nếu provider hỗ trợ và đã kiểm tra.
- Truy vấn theo tập ID, sau đó group data trong Java.
- Không thực hiện DTO mapping kiểu “mỗi row gọi repository một lần”.

## 17. Phân trang và fetch collection: Cạm bẫy đặc biệt

Một màn hình danh sách đơn cần 20 Order mỗi trang; mỗi Order có các Lines.

Đoạn code nguy hiểm về mặt hiệu năng:

~~~java
TypedQuery<PurchaseOrder> query = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.lines
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    PurchaseOrder.class
);

query.setFirstResult(0);
query.setMaxResults(20);
~~~

Với quan hệ 1:N, SQL join có thể trả nhiều row cho mỗi Order. Nếu phân trang ở cấp SQL rows, khó bảo đảm đúng 20 Order roots. Một số provider cảnh báo hoặc phân trang trong memory khi fetch collection.

**Không kết luận rằng JOIN FETCH collection + pagination luôn đúng và hiệu quả** chỉ vì method trả List có 20 phần tử trên dữ liệu nhỏ.

### 17.1. Chiến lược hai bước: Page IDs trước, fetch sau

Bước 1 — lấy ID theo sort ổn định:

~~~java
List<Long> ids = em.createQuery(
    """
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.totalAmount >= :minimum
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    Long.class
)
.setParameter("minimum", minTotal)
.setFirstResult(page * size)
.setMaxResults(size)
.getResultList();
~~~

Bước 2 — fetch dữ liệu cần thiết đúng các ID:

~~~java
if (ids.isEmpty()) {
    return List.of();
}

List<PurchaseOrder> rows = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    JOIN FETCH o.customer
    LEFT JOIN FETCH o.lines
    WHERE o.id IN :ids
    """,
    PurchaseOrder.class
)
.setParameter("ids", ids)
.getResultList();
~~~

Bước 3 — khôi phục thứ tự theo `ids` từ page query. Câu `WHERE id IN :ids` **không bảo đảm giữ thứ tự của list đầu vào**.

~~~java
Map<Long, PurchaseOrder> byId = rows.stream()
    .collect(Collectors.toMap(
        PurchaseOrder::getId,
        Function.identity()
    ));

List<PurchaseOrder> ordered = ids.stream()
    .map(byId::get)
    .filter(Objects::nonNull)
    .toList();
~~~

Cuối cùng, chuyển `ordered` thành DTO **khi cần đọc association đã tải**, trước khi rời khỏi transaction/context thích hợp.

### 17.2. Bước COUNT tách riêng

Nếu UI cần tổng số:

~~~java
long total = em.createQuery(
    """
    SELECT COUNT(o)
    FROM PurchaseOrder o
    WHERE o.totalAmount >= :minimum
    """,
    Long.class
)
.setParameter("minimum", minTotal)
.getSingleResult();
~~~

Count query không nên mang fetch join collection của data query.

### 17.3. Giới hạn của hai bước

Nếu dữ liệu thay đổi giữa bước chọn IDs và bước fetch chi tiết, kết quả có thể có khác biệt theo transaction isolation. Nếu trang cần snapshot nhất quán tuyệt đối, cần một chính sách transaction/isolation phù hợp.

Với tập dữ liệu rất lớn hoặc feed thường xuyên thay đổi, keyset pagination có thể tốt hơn offset; nhưng nó vẫn cần fetch plan hợp lý.

## 18. Chủ động khởi tạo LAZY trong context: Khi nào nên làm?

Trong một số trường hợp, service biết chính xác cần thêm một association và có thể chủ động truy cập nó khi context còn hoạt động.

~~~java
@Transactional(readOnly = true)
public PurchaseOrder findWithLines(Long id) {
    PurchaseOrder order = repository.findById(id)
        .orElseThrow();

    // Yêu cầu đọc collection trong phạm vi transaction.
    order.getLines().forEach(
        line -> line.getProductSku()
    );

    return order;
}
~~~

Với một collection nhỏ, điều này có thể đáp ứng nhu cầu. Tuy nhiên, trả entity trực tiếp vẫn có các hạn chế API/serialization và không bảo đảm association khác đã tải. Đây không phải phương án ưu tiên cho một REST contract phức tạp.

### 18.1. `Hibernate.initialize(...)`

Hibernate có API riêng:

~~~java
import org.hibernate.Hibernate;

Hibernate.initialize(order.getLines());
~~~

Hành vi: yêu cầu khởi tạo một proxy/collection theo cơ chế Hibernate.

Nhưng:

- Đây là **Hibernate-specific**, không phải API JPA portable.
- Cần Session/persistence context thích hợp còn khả năng tải dữ liệu.
- Gọi **sau** khi session đã đóng không “hồi sinh” context cũ.
- Khi dùng trong vòng lặp nhiều entity, vẫn có nguy cơ N+1.
- Khởi tạo `lines` không mặc định khởi tạo mọi nested association.

### 18.2. Vì sao không khuyến nghị gọi `size()` ở mọi nơi?

Một số provider/collection có chế độ extra-lazy tối ưu phép `size()` bằng COUNT riêng mà không materialize toàn collection. Vì vậy, dùng `size()` làm một API “bảo đảm đã tải toàn bộ” là không chắc chắn trên mọi stack.

Fetch plan hoặc mapping DTO rõ ràng dễ kiểm soát hơn.

## 19. Kiểm tra thuộc tính đã được tải hay chưa

JPA cung cấp `PersistenceUnitUtil`:

~~~java
PersistenceUnitUtil util =
    em.getEntityManagerFactory()
      .getPersistenceUnitUtil();

boolean linesLoaded =
    util.isLoaded(order, "lines");

boolean customerLoaded =
    util.isLoaded(order, "customer");
~~~

API này giúp quan sát trạng thái loaded theo ngữ nghĩa JPA/provider.

### 19.1. Dùng loaded check để chẩn đoán

Ví dụ:

~~~java
System.out.println(
    "lines loaded: " + util.isLoaded(order, "lines")
);
~~~

Có thể in kết quả trước khi context kết thúc. Nếu `false` và downstream sẽ cần `lines`, use case cần fetch/DTO plan phù hợp.

### 19.2. Loaded check không phải lệnh tải dữ liệu

~~~java
util.isLoaded(order, "lines");
~~~

không có nghĩa collection sẽ được nạp từ DB. Nó kiểm tra state; muốn fetch phải sử dụng operation thích hợp khi context còn hoạt động.

### 19.3. Hibernate `isInitialized`

Nếu dùng Hibernate:

~~~java
boolean initialized =
    org.hibernate.Hibernate.isInitialized(
        order.getLines()
    );
~~~

API này cũng chủ yếu để kiểm tra proxy/collection wrapper, không thay thế fetch plan.

### 19.4. Test không nên phụ thuộc tên class proxy

Những tên kiểu `HibernateProxy` hoặc class sinh động có thể thay đổi theo provider/version. Khi cần kiểm thử khả năng tải, ưu tiên `PersistenceUnitUtil` cho phần JPA portable và chỉ dùng Hibernate APIs khi test chủ đích Hibernate-specific.

## 20. Tại sao `@Transactional` không luôn giải quyết vấn đề?

Một phản ứng quen thuộc là thêm annotation:

~~~java
@Transactional
public PurchaseOrder findOrder(...) {
    return repository.findById(...).orElseThrow();
}
~~~

Nhưng nếu caller truy cập association **sau khi method trả về và transaction kết thúc**, annotation không kéo dài transaction đến lúc caller/serializer đọc lazy field.

### 20.1. Đặt mapping ở trong transaction

Sai về boundary:

~~~java
PurchaseOrder order = service.findOrder(id);
return mapper.toDetailsView(order); // Đọc lazy ngoài service.
~~~

Tốt hơn:

~~~java
@Transactional(readOnly = true)
public OrderDetailsView getDetails(Long id) {
    PurchaseOrder order =
        repository.findById(id).orElseThrow();

    return mapper.toDetailsView(order);
}
~~~

Tại đây mapper chạy trước khi transaction service kết thúc.

### 20.2. Self-invocation của Spring

Trong cách dùng Spring proxy-based transaction thông thường:

~~~java
@Service
public class OrderService {

    public OrderDetailsView getDetails(Long id) {
        // Gọi từ cùng instance, có thể không đi qua proxy.
        return loadDetailsTransactional(id);
    }

    @Transactional(readOnly = true)
    public OrderDetailsView loadDetailsTransactional(Long id) {
        // ...
    }
}
~~~

Lời gọi nội bộ `this.loadDetailsTransactional(...)` có thể **không kích hoạt transaction interceptor**, nên annotation có vẻ tồn tại nhưng transaction thực tế không được mở như kỳ vọng.

Giải pháp: đặt transaction boundary tại public service method được gọi qua proxy, tách collaborator bean hoặc dùng cơ chế transaction programmatic/AspectJ phù hợp.

### 20.3. Không mở transaction rộng hơn chỉ để serialize JSON

Đặt `@Transactional` lên controller hoặc kéo dài transaction qua tất cả bước HTTP rendering có thể che lỗi fetch plan nhưng làm giảm tính rõ ràng của transaction và tăng thời gian giữ tài nguyên.

Thường tốt hơn là chuyển sang DTO trong service/query layer rồi trả dữ liệu độc lập khỏi persistence context.

## 21. Open EntityManager in View (OSIV): Giải pháp hay bẫy?

Spring có cơ chế **Open EntityManager in View** giữ EntityManager qua phạm vi request/rendering. Có thể cấu hình:

~~~properties
spring.jpa.open-in-view=false
~~~

Cấu hình này thường được dùng để **tắt OSIV** trong Spring Boot, nếu dự án lựa chọn transaction/fetch plan rõ ràng ở service.

### 21.1. Khi OSIV bật

~~~text
Request bắt đầu
    |
    v
Mở/bind EntityManager
    |
    v
Service @Transactional
    |
    +-- SELECT Order
    |
    v
Service transaction kết thúc
    |
    v
Serializer gọi getLines()
    |
    +-- Có thể thực hiện lazy SELECT qua EM còn mở
    |
    v
Response hoàn tất -> đóng EntityManager
~~~

Điều này có thể giúp tránh exception trong một số tình huống. Nhưng các SELECT bổ sung ở tầng view/serialization có thể không nằm trong business transaction của service, phụ thuộc connection/DB behavior.

### 21.2. Những chi phí có thể phát sinh

- Lazy SQL xảy ra ở tầng presentation, khó quan sát ở service.
- N+1 theo số entity/association được serialize.
- Thời gian response tăng ngoài dự kiến.
- Có thể kéo dài vòng đời EntityManager và sử dụng connection/tài nguyên theo cấu hình.
- Dữ liệu ở các thời điểm khác nhau có thể không cùng snapshot.
- Tầng web phụ thuộc mapping JPA thay vì DTO contract.

### 21.3. Có nên luôn tắt OSIV?

Không có một lựa chọn áp dụng y hệt cho mọi ứng dụng. Một số ứng dụng server-rendered view có thể chủ đích dùng OSIV, nhưng cần hiểu chi phí và giám sát SQL.

Đối với API có contract DTO và service layer rõ ràng, **tắt OSIV thường là một lựa chọn đáng cân nhắc** để phát hiện việc tải dữ liệu sai tầng. Khi tắt, phải bảo đảm tất cả dữ liệu cần trả đã được fetch/map trước khi transaction/context kết thúc.

### 21.4. Tắt OSIV không tự sửa query

Nếu chỉ đổi:

~~~properties
spring.jpa.open-in-view=false
~~~

mà controller vẫn trả entity với lazy fields, exception có thể xuất hiện rõ hơn. Phải phối hợp sửa response layer sang DTO/projection/fetch plan.

## 22. Anti-pattern: Bật lazy loading ngoài transaction tự động

Hibernate có một số cấu hình riêng, ví dụ:

~~~properties
hibernate.enable_lazy_load_no_trans=true
~~~

Một số môi trường có thể bật tính năng để Hibernate tải association ngoài transaction ban đầu bằng session tạm hoặc cơ chế tương tự.

**Không nên coi đây là cách sửa mặc định.** Những rủi ro:

- SQL phát sinh ở những nơi không dự kiến.
- N+1 và round trip tăng cao.
- Dữ liệu được đọc ngoài snapshot/transaction nghiệp vụ ban đầu.
- Việc phát hiện boundary sai trở nên khó hơn.
- Ứng dụng phụ thuộc hành vi riêng Hibernate/provider/version.

Nếu không có lý do kiến trúc và kiểm thử hiệu năng/tính nhất quán rõ, ưu tiên fetch plan và DTO trong phạm vi service phù hợp.

## 23. Anti-pattern: Chuyển toàn bộ association thành EAGER

Ví dụ:

~~~java
@OneToMany(
    mappedBy = "order",
    fetch = FetchType.EAGER
)
private List<OrderLine> lines;
~~~

Điều này có thể khiến collection được tải sớm hơn trong nhiều truy vấn, nhưng đổi lại:

- Query danh sách Order cũng có thể kéo theo Lines dù không cần.
- Provider có thể thực hiện nhiều SELECT phụ.
- Payload lớn và memory tăng.
- N+1 vẫn có thể xảy ra với EAGER association khi provider tải bằng secondary selects.
- Các nested associations có thể tiếp tục chưa tải.
- Phân trang và fetch nhiều collections trở nên khó tối ưu.

**EAGER không phải nút “sửa mọi LazyInitializationException”**. Fetch strategy ở mapping nên thể hiện default hợp lý; fetch plan cụ thể cho từng use case vẫn rất quan trọng.

## 24. Anti-pattern: `@JsonIgnore` như một giải pháp duy nhất

Một số team giải quyết lỗi serialize bằng:

~~~java
@JsonIgnore
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
~~~

Điều này có thể ngăn JSON serializer chạm vào collection, nên không xảy ra lỗi ở đường serialize đó. Nhưng nếu API thực sự cần trả Lines thì dữ liệu lại bị ẩn.

Ngoài ra:

- Entity có thể có quan hệ khác vẫn lazy.
- Vấn đề N+1 ở service vẫn còn.
- Annotations JSON trên entity làm persistence model phụ thuộc presentation.
- Không thay thế quyền truy cập/authorization.
- Các vòng quan hệ khác có thể tiếp tục gây recursion.

Dùng DTO là cách tách ranh giới API rõ ràng hơn. `@JsonIgnore` có thể hữu ích cho một số trường hợp có chủ đích, nhưng không phải giải pháp tổng quát cho kế hoạch tải dữ liệu.

## 25. Anti-pattern: Trả entity JPA trực tiếp qua REST

Một entity là mô hình lưu trữ và vòng đời JPA. Một REST response là **hợp đồng dữ liệu** với client. Khi dùng cùng một object cho cả hai:

~~~text
Entity mapping thay đổi
         |
         v
JSON response có thể thay đổi ngoài ý muốn
         |
         +-- Lộ field mới
         +-- Lazy loading khi serializer truy cập
         +-- Vòng tham chiếu bidirectional
         +-- Payload tăng
         +-- N+1 phát sinh
~~~

DTO/projection giảm sự phụ thuộc giữa hai tầng, kể cả khi một vài entity hiện tại serialize được.

### 25.1. Đừng dùng DTO như một nhãn rỗng

Nếu DTO vẫn chứa:

~~~java
public record OrderView(
    PurchaseOrder order
) {}
~~~

thì serializer vẫn có thể duyệt entity graph lười tải. DTO nên chứa **giá trị/structure được thiết kế cho response**, không chỉ bọc entity để đổi tên.

### 25.2. Cân nhắc DTO có nested list

Một `OrderDetailsView` với `List<OrderLineView>` là phù hợp khi list đã được materialize thành Java DTO thuần. Đừng đưa Hibernate persistent collection hoặc proxy vào field DTO rồi xem là đã tách tầng.

## 26. Detached entity, merge và getReference

### 26.1. `EntityManager.detach(entity)`

~~~java
em.detach(order);
~~~

Entity không còn managed trong context đó. Nếu có unloaded lazy associations, việc truy cập sau detach có thể thất bại.

### 26.2. `EntityManager.clear()`

~~~java
em.clear();
~~~

Detach **toàn bộ** managed entities khỏi context, không chỉ Order.

### 26.3. `EntityManager.close()`

~~~java
em.close();
~~~

Đóng EntityManager, chấm dứt khả năng quản lý và tải tiếp qua EM đó.

### 26.4. `merge(detached)` có sửa lazy problem không?

~~~java
PurchaseOrder managedCopy = em.merge(detachedOrder);
~~~

`merge` dùng để sao chép state từ detached entity vào một managed instance theo contract JPA. Nó **không phải API chỉ để bật lazy loading lại cho detached object**.

Đặc biệt:

- Object `detachedOrder` ban đầu vẫn detached.
- `merge` trả về một managed instance khác hoặc tương ứng trong context.
- Merge có thể tạo truy vấn/ghi dữ liệu và liên quan cascade.
- Những field chưa tải, stale state và concurrency cần được xem xét.
- Không merge một entity chỉ để JSON serializer lấy thêm collection.

Nếu mục tiêu là đọc dữ liệu, **query mới/fetch plan mới trong service** thường rõ và an toàn hơn.

### 26.5. `getReference(...)` không giải quyết unloaded access

~~~java
PurchaseOrder ref =
    em.getReference(PurchaseOrder.class, id);
~~~

`getReference` có thể trả proxy/reference mà chưa tải entity ngay. Nó hữu ích cho một số thao tác quan hệ, nhưng **không phải cách bảo đảm mọi field đã tải**. Trả reference ra ngoài context có thể khiến vấn đề lazy loading xuất hiện ở cấp chính entity.

## 27. Async, background job và thread boundary

Một tình huống khác:

~~~java
@Transactional(readOnly = true)
public void scheduleReport(Long orderId) {
    PurchaseOrder order =
        em.find(PurchaseOrder.class, orderId);

    executor.submit(() -> {
        // Thread khác, chạy sau:
        process(order.getLines());
    });
}
~~~

Đây là thiết kế rủi ro:

- EntityManager không thread-safe.
- Thread khác không tự kế thừa persistence context/transaction ban đầu.
- Công việc async có thể chạy sau khi context service đã kết thúc.
- Entity/lazy proxy đưa qua thread có thể detached hoặc truy cập dữ liệu không nhất quán.

### 27.1. Truyền ID thay vì entity

Tốt hơn:

~~~java
@Transactional(readOnly = true)
public void scheduleReport(Long orderId) {
    reportQueue.enqueue(orderId);
}
~~~

Worker xử lý:

~~~java
@Transactional(readOnly = true)
public void processReport(Long orderId) {
    OrderDetailsView details =
        orderQueryService.getDetails(orderId);

    reportGenerator.generate(details);
}
~~~

Đoạn code chỉ minh họa luồng. Với Spring, cần đảm bảo transaction thực sự mở qua proxy và boundary ở worker hợp lệ; không mặc định annotation trên lời gọi nội bộ cùng bean có hiệu lực.

### 27.2. Truyền DTO snapshot khi phù hợp

Nếu nhiệm vụ async cần chính xác dữ liệu đã xác định tại thời điểm tạo job, có thể tạo DTO snapshot hoặc lưu snapshot/event trong outbox. Khi dùng ID để query lại ở worker, dữ liệu có thể đã thay đổi; cần chọn semantics phù hợp nghiệp vụ.

## 28. Streaming result và vòng đời EntityManager

JPA có `getResultStream()`:

~~~java
Stream<PurchaseOrder> stream =
    em.createQuery(
        "SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class
    ).getResultStream();
~~~

Không nên tạo stream trong service, đóng context rồi trả stream để caller mới duyệt:

~~~java
@Transactional(readOnly = true)
public Stream<PurchaseOrder> streamOrders() {
    return em.createQuery(
        "SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class
    ).getResultStream();
}
~~~

Caller có thể tiêu thụ stream sau transaction, trong khi provider cần ResultSet/session/connection còn hoạt động.

### 28.1. Tiêu thụ stream bên trong boundary

~~~java
@Transactional(readOnly = true)
public List<OrderListItem> listSummaries() {
    try (Stream<OrderListItem> stream =
            em.createQuery(
                """
                SELECT new com.example.shop.api.OrderListItem(
                    o.id, o.orderNumber, o.totalAmount,
                    c.displayName
                )
                FROM PurchaseOrder o
                JOIN o.customer c
                ORDER BY o.id
                """,
                OrderListItem.class
            ).getResultStream()) {

        return stream.toList();
    }
}
~~~

Use case lớn có thể cần streaming incremental thực sự thay vì materialize thành list; lúc đó phải quản lý lifetime/connection và commit semantics cẩn thận. Điểm chính là **không đưa stream phụ thuộc DB ra ngoài scope có thể phục vụ nó**.

## 29. Lazy loading và second-level cache

Một số người nhận thấy association lazy hoạt động ở môi trường dev nhờ cache và kết luận không còn cần persistence context.

Không nên dựa vào điều này:

- **First-level cache** nằm trong persistence context; khi context đóng, entity detached không tự có quyền query thêm.
- **Second-level cache** có thể chứa dữ liệu entity theo cấu hình provider, nhưng không bảo đảm mọi lazy association có sẵn hoặc được initialize cho detached object.
- Query-result cache và entity cache là hai cơ chế khác nhau.
- Cache hit làm giảm SQL, không thay contract về lifecycle/loaded state.

Một thiết kế tốt phải đúng dù cache cold, warm hoặc bị eviction, và không lệ thuộc vào may mắn thứ tự tải object.

## 30. Khi entity đã tải dữ liệu, có cần giữ context mở để đọc không?

Không phải lúc nào. Ví dụ:

~~~java
String number = order.getOrderNumber();
~~~

với basic field đã load có thể được gọi trên detached entity. Một collection đã fully initialized thường có thể duyệt sau close.

Nhưng cần phân biệt:

1. **Đọc dữ liệu sẵn có** trong Java memory.
2. **Yêu cầu provider đi database lấy phần chưa load**.
3. **Sửa detached entity** rồi mong dirty checking tự flush.

Chỉ trường hợp 1 thường không cần EntityManager còn hoạt động. Trường hợp 2 cần fetch context thích hợp. Trường hợp 3 phải dùng quy trình update/merge và concurrency phù hợp, không liên quan trực tiếp tới việc hết LazyInitializationException.

## 31. Chẩn đoán qua log và SQL

Khi gặp lỗi, nên ghi lại flow của request:

~~~text
[service] begin transaction
[sql] SELECT ... FROM purchase_order WHERE id = ?
[service] return entity
[service] commit / close transaction-scoped context
[controller] build response
[serializer] access PurchaseOrder.lines
[error] LazyInitializationException
~~~

Cần xác định:

- Lỗi xảy ra khi truy cập field nào?
- Field mapped LAZY hay EAGER?
- Nó đã loaded trước khi kết thúc context chưa?
- Object ở trạng thái managed hay detached?
- Query service có fetch plan nào?
- Mapper/serializer chạy trước hay sau transaction?
- OSIV có bật không?
- Có async/thread boundary không?
- Nếu cố sửa bằng EAGER/OSIV, số SQL có tăng mạnh không?

### 31.1. Xem stack trace đúng tầng

Một stack trace thường có các lớp:

~~~text
Controller
  -> Jackson serializer / DTO mapper
     -> PurchaseOrder.getLines()
        -> Hibernate PersistentCollection
           -> LazyInitializationException
~~~

Exception có thể bị bọc thành lỗi HTTP 500 hoặc JSON mapping exception. Hãy tìm **root cause** để không nhầm với lỗi cấu hình serializer đơn thuần.

### 31.2. Log SQL có trách nhiệm

Bật SQL logging ở môi trường dev/test có thể giúp thấy query ban đầu chỉ tải Order, không tải Lines. Nhưng không bật bind parameter logging chứa email, token, dữ liệu thanh toán hoặc thông tin nhạy cảm trên production mà không có chính sách bảo vệ.

### 31.3. Dùng metrics/statistics

Với Hibernate, thống kê số query, entity load, collection fetch và second-level cache hit/miss có thể giúp nhận diện N+1 sau khi sửa lazy loading. APIs thống kê là provider-specific; không coi chúng là JPA standard.

## 32. Lựa chọn chiến lược theo use case

| Tình huống | Hướng giải quyết thường phù hợp | Điều cần tránh |
|---|---|---|
| API chi tiết một Order có Lines | DTO trong service + JOIN FETCH hoặc EntityGraph | Trả entity detached |
| API danh sách 20 Order chỉ cần summary | JPQL constructor projection | Fetch collection Lines không dùng |
| API danh sách cần Lines của mỗi Order | Page IDs rồi fetch/group lines | Collection FETCH JOIN + OFFSET trực tiếp |
| Service chỉ cần Customer.name | Join/projection hoặc fetch to-one | Mỗi Order lazy SELECT riêng nếu N+1 |
| Business operation sửa entity | Managed entity trong transaction | Bulk workarounds chỉ để đọc lazy |
| Báo cáo thống kê | Scalar/DTO aggregation query | Tải toàn bộ graph |
| Async job | Gửi ID, worker query trong context riêng | Gửi entity/proxy qua thread |
| JSON serializer gây lỗi | Thiết kế DTO response | Bật OSIV hoặc EAGER toàn hệ thống vô điều kiện |
| Cần kiểm tra loaded status | `PersistenceUnitUtil.isLoaded` | Coi kiểm tra là hành động fetch |
| Data đã detach, cần đọc thêm | Query lại trong transaction mới | `merge` chỉ để serializer truy cập |
| Một transaction cần ít association | Fetch graph theo use case | Fetch “toàn bộ” cho mọi query |

Không có một annotation nào là giải pháp chung. Kế hoạch tải là quyết định **tại ranh giới use case**, dựa trên dữ liệu thực sự cần và chi phí truy vấn có thể đo.

## 33. Kiểm thử lỗi trong JPA resource-local

Một test cô lập có thể xác minh lazy boundary. Với Hibernate và collection thực sự chưa initialized:

~~~java
@Test
void cannotInitializeUnloadedLinesAfterClose() {

    EntityManager em = emf.createEntityManager();
    PurchaseOrder order;

    try {
        order = em.find(
            PurchaseOrder.class,
            orderIdWithLines
        );

        PersistenceUnitUtil util =
            emf.getPersistenceUnitUtil();

        assertFalse(
            util.isLoaded(order, "lines")
        );
    } finally {
        em.close();
    }

    assertThrows(
        org.hibernate.LazyInitializationException.class,
        () -> order.getLines().iterator().hasNext()
    );
}
~~~

**Đây là test phụ thuộc Hibernate**, vì nó assert class exception riêng provider. Cần fixture Order tồn tại và mapping LAZY thực sự chưa tải. Nếu provider fetch association sớm hơn hoặc cache/test setup khiến nó đã initialized, giả định `assertFalse` không còn đúng; khi đó test không thể dùng để kết luận mọi provider sẽ hành xử như Hibernate.

### 33.1. Kiểm thử giải pháp DTO

~~~java
@Test
void detailsDtoIsUsableOutsideTransaction() {

    OrderDetailsView result =
        orderQueryService.getDetails(orderIdWithLines);

    // Service đã trả DTO hoàn chỉnh.
    assertNotNull(result.customerName());
    assertFalse(result.lines().isEmpty());

    // Truy cập DTO không cần EntityManager.
    int itemCount = result.lines().size();

    assertTrue(itemCount > 0);
}
~~~

Test tốt phải kiểm tra **đúng dữ liệu** (mã, tổng tiền, số dòng, quyền truy cập), không chỉ đảm bảo không ném exception.

### 33.2. Bài test độc lập transaction context

Với Spring, `@DataJpaTest` hoặc test method có `@Transactional` có thể giữ transaction/context mở bao phủ cả phần assert. Điều này khiến bug ở production bị che.

Muốn kiểm tra dữ liệu sau ranh giới service, có thể:

- Dùng integration test không bao phủ toàn method bằng một transaction.
- Gọi service qua Spring proxy.
- Đảm bảo transaction service đã kết thúc khi truy cập DTO.
- Dùng controller/MVC test với OSIV off khi thích hợp.
- Xác minh behavior dưới cấu hình tương ứng production.

### 33.3. Đừng chỉ gọi repository rồi assert trong transaction test

Nếu test viết:

~~~java
@Transactional
@Test
void testOrder() {
    PurchaseOrder order =
        repository.findById(orderId).orElseThrow();

    assertFalse(order.getLines().isEmpty());
}
~~~

nó có thể thành công vì context vẫn mở trong test. Điều đó không chứng minh controller có thể serialize entity sau service transaction.

### 33.4. Test N+1 ngoài kiểm thử exception

Nếu đã sửa bằng cách giữ context mở hoặc map DTO trong vòng lặp, cần kiểm tra SQL count trên tập dữ liệu đủ lớn:

~~~text
Load 1 Order         : ~1 query + fetch phù hợp
Load 50 Orders       : không nên tự tăng thêm 50 SQL
Load 200 Orders      : theo dõi round trips/payload
~~~

Không bắt buộc có “đúng 1 SELECT” cho mọi use case; một số thiết kế 2–3 query theo batch có thể hiệu quả hơn một JOIN rất rộng.

## 34. Kiểm tra tính đầy đủ của fetch plan trong use case

Một quy trình làm việc thực tế:

### Bước 1: Xác định output contract

Ví dụ màn hình chi tiết cần:

~~~text
OrderDetailsView
  id
  orderNumber
  createdAt
  totalAmount
  customerName
  lines:
    id
    productSku
    quantity
    unitPrice
~~~

### Bước 2: Ghi rõ dữ liệu lấy từ đâu

| Field DTO | Nguồn |
|---|---|
| orderNumber | `PurchaseOrder.orderNumber` |
| customerName | `PurchaseOrder.customer.displayName` |
| lines | `PurchaseOrder.lines` |
| productSku | `OrderLine.productSku` |

### Bước 3: Chọn cách truy vấn

- Một Order: JOIN FETCH customer + lines hoặc EntityGraph.
- List summary: projection.
- List phân trang kèm lines: page IDs rồi fetch/group.
- Báo cáo: aggregate DTO.

### Bước 4: Chạy mapper bên trong boundary

Không trả entity ra controller rồi mới gọi các getter chưa tải.

### Bước 5: Kiểm tra truy vấn và tính đúng

- Query có nạp đúng fields?
- Có N+1 không?
- Có nhân row root không?
- Có trả đúng page size/order không?
- Có rò dữ liệu tenant không?
- Caching có che test hay không?
- Những nested associations có cần fetch tiếp không?

### Bước 6: Kiểm thử khi context đã đóng

Đảm bảo DTO/result cuối cùng độc lập khỏi persistence context và có đủ giá trị cần dùng.

## 35. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân phổ biến | Hướng xử lý |
|---|---|---|
| `LazyInitializationException` khi serialize JSON | Controller trả entity có lazy field | DTO trong service; fetch plan rõ |
| Lỗi ở `order.getLines().size()` sau close | Collection chưa load | Fetch trong context trước close |
| `getCustomer().getName()` lỗi trên detached | To-one proxy chưa initialized | Fetch/projection to-one |
| Service `@Transactional` vẫn lỗi | Mapper chạy sau khi method trả về | Đưa mapping vào service |
| Annotation `@Transactional` không có tác dụng | Self-invocation, proxy/manager config | Kiểm tra transaction boundary thật |
| Unit test pass, production fail | Test giữ context mở, prod đóng | Test ngoài transaction/OSIV off |
| Bật OSIV thì hết lỗi nhưng chậm | SQL phát sinh ở serializer | Tối ưu fetch/DTO và tắt dependency vào view |
| Đổi EAGER thì SQL tăng mạnh | Mọi query tải dữ liệu không cần | Quay lại fetch theo use case |
| JOIN FETCH to-many làm page sai/chậm | SQL rows bị nhân theo collection | Page IDs rồi fetch sau |
| Duyệt list Order gây nhiều SELECT | N+1 | Projection/EntityGraph/batch fetch |
| `@JsonIgnore` hết lỗi nhưng thiếu JSON | Field bị ẩn thay vì load | Thiết kế DTO đúng contract |
| Hibernate.initialize vẫn lỗi | Session đã đóng | Khởi tạo trong context, không sau close |
| `merge` tạo hành vi khó hiểu | Dùng merge để cố đọc detached | Query lại theo ID |
| Async worker truy cập proxy lỗi | Entity đi qua thread/context khác | Truyền ID hoặc DTO snapshot |
| Truy cập Product sau khi đã load Lines vẫn lỗi | Nested association chưa tải | Fetch những paths thật sự cần |
| DTO chứa PersistentCollection vẫn lỗi | Bọc entity collection trong DTO | Materialize List DTO thuần |
| SQL log không có query Lines trước khi close | Association còn lazy | Fetch plan chưa đầy đủ |
| L2 cache “lúc được lúc không” | Loaded/cache state phụ thuộc môi trường | Kiểm thử cache cold và boundary |
| EntityNotFoundException khi initialize proxy | Row tham chiếu không tồn tại | Kiểm tra dữ liệu/FK |
| `NullPointerException` trên optional relation | Association thực sự null | Xử lý null, không đổ cho LAZY |

### 35.1. Không chữa bằng catch LazyInitializationException rồi trả list rỗng

Ví dụ:

~~~java
try {
    return order.getLines();
} catch (LazyInitializationException ex) {
    return List.of();
}
~~~

Đây là lỗi nghiêm trọng về ngữ nghĩa: **chưa tải dữ liệu khác với không có dữ liệu**. Trả list rỗng có thể làm API nói dối về số dòng của Order.

### 35.2. Không chữa bằng mở một EntityManager tạm trong getter

Đưa DB access vào entity getter hoặc serializer khiến domain object phụ thuộc infrastructure, rất khó test, có thể tạo transaction mới không nhất quán và N+1.

### 35.3. Không chữa bằng cách “không bao giờ đóng EntityManager”

EntityManager cần vòng đời rõ và được đóng/giải phóng đúng cách. Giữ mở vô hạn dẫn tới quản lý tài nguyên kém, memory growth và state stale.

## 36. Câu hỏi và bài tập thực hành

### Bài 1: Nhận diện nguyên nhân

Code:

~~~java
PurchaseOrder order = repository.findById(id).orElseThrow();
// Transaction service đã kết thúc.
return order.getLines().size();
~~~

**Câu hỏi:** Vì sao có thể ném LazyInitializationException?

**Đáp án:** `lines` chưa được tải và entity không còn gắn với session/context có thể tải thêm. Đọc collection ở ngoài boundary làm phát sinh lỗi.

### Bài 2: Entity đã detach có đọc field scalar không?

**Câu hỏi:** Một `PurchaseOrder` detached có chắc không đọc được `getOrderNumber()`?

**Đáp án:** Không. Nếu basic field đã được tải, dữ liệu đó vẫn nằm trong Java object. Vấn đề chủ yếu là truy cập những thuộc tính cần tải thêm.

### Bài 3: Đã tải Lines nhưng Product vẫn lỗi

**Câu hỏi:** Vì sao `order.getLines()` duyệt được sau close nhưng `line.getProduct().getName()` lỗi?

**Đáp án:** Collection Lines đã initialized, nhưng association Product trên mỗi Line có thể còn LAZY và chưa được fetch.

### Bài 4: Transaction và context có phải một?

**Đáp án:** Không. Transaction quản lý commit/rollback/isolation; persistence context quản lý entity state/identity/lazy loading. Vòng đời có thể khác nhau tùy transaction-scoped, extended, application-managed EM hoặc OSIV.

### Bài 5: Spring @Transactional

Một service có `@Transactional` nhưng trả entity cho controller; controller mới map sang DTO.

**Câu hỏi:** Thêm annotation ở service đã đủ chưa?

**Đáp án:** Chưa. Mapper có thể chạy sau khi transaction đã kết thúc. Nên map sang DTO trong service hoặc đảm bảo fetch plan trước khi trả.

### Bài 6: JOIN và JOIN FETCH

**Câu hỏi:** `JOIN o.lines l` có tự khởi tạo collection `o.lines` không?

**Đáp án:** Không có bảo đảm như fetch join. `JOIN` phục vụ điều kiện/truy vấn; `JOIN FETCH` mới yêu cầu nạp association theo ngữ nghĩa JPQL.

### Bài 7: EntityGraph

**Câu hỏi:** Có thể khai báo fetch plan không sửa query JPQL không?

**Đáp án:** Có. Sử dụng `EntityGraph` và các hint `jakarta.persistence.fetchgraph`/`loadgraph`, hoặc Spring Data `@EntityGraph` nếu dùng framework đó.

### Bài 8: DTO projection

Danh sách Order chỉ cần ID, số đơn, tổng tiền và tên khách.

**Câu hỏi:** Có cần tải `List<OrderLine>` không?

**Đáp án:** Không. JPQL constructor projection chọn đúng trường cần dùng, tránh association lazy không liên quan.

### Bài 9: Fetch join và pagination

**Câu hỏi:** Vì sao `LEFT JOIN FETCH o.lines` với `setMaxResults(20)` có rủi ro?

**Đáp án:** Collection to-many có thể nhân SQL rows; pagination trên roots trở nên khó. Có thể page IDs trước rồi fetch Lines theo tập ID.

### Bài 10: PersistenceUnitUtil

~~~java
util.isLoaded(order, "lines");
~~~

**Câu hỏi:** Lệnh này có tải Lines không?

**Đáp án:** Không. Nó kiểm tra trạng thái loaded; không phải lệnh fetch collection.

### Bài 11: Hibernate.initialize

**Câu hỏi:** `Hibernate.initialize(order.getLines())` có giải quyết được khi session đã đóng không?

**Đáp án:** Thông thường không. Đây là API Hibernate-specific và cần context/session phù hợp còn khả năng tải dữ liệu.

### Bài 12: OSIV

**Câu hỏi:** Vì sao bật OSIV có thể hết lỗi mà hiệu năng vẫn kém?

**Đáp án:** EntityManager còn mở trong quá trình render, serializer có thể phát sinh nhiều lazy SELECT gây N+1, làm tăng latency và coupling tầng web với DB.

### Bài 13: Đổi toàn bộ EAGER

**Câu hỏi:** Có nên sửa mọi quan hệ thành EAGER?

**Đáp án:** Không. EAGER có thể tải nhiều dữ liệu không dùng, tăng secondary SELECT, payload và phức tạp pagination. Nên dùng fetch plan theo use case.

### Bài 14: Async

Một service đưa entity vào executor task sau khi transaction kết thúc.

**Câu hỏi:** Thiết kế tốt hơn là gì?

**Đáp án:** Gửi ID hoặc DTO snapshot; worker mở transaction/context riêng để đọc dữ liệu, không chuyển Hibernate proxy qua thread.

### Bài 15: Merge

**Câu hỏi:** Có nên gọi `em.merge(detachedOrder)` chỉ để serializer đọc Lazy collection không?

**Đáp án:** Không. Merge là thao tác vòng đời đồng bộ state có thể phát sinh ghi; detached original vẫn detached. Để đọc, query lại với fetch plan phù hợp trong service.

### Bài 16: JPA vs Hibernate exception

**Câu hỏi:** `LazyInitializationException` có phải exception chuẩn JPA mọi provider đều ném không?

**Đáp án:** Không. Đây là exception riêng Hibernate; provider khác có thể biểu hiện khác. Nguyên nhân cần hiểu là unloaded data sau khi context/session không còn khả năng tải.

### Bài 17: Test sai boundary

Một test được đánh dấu `@Transactional` đọc `order.getLines()` thành công.

**Câu hỏi:** Có chứng minh production controller serialize được không?

**Đáp án:** Không. Test đang giữ transaction/context mở. Cần test sau service boundary hoặc kiểm thử HTTP response với cấu hình context giống production.

### Bài 18: Không được trả list rỗng khi lazy fail

**Câu hỏi:** Vì sao catch LazyInitializationException rồi trả `List.of()` không đúng?

**Đáp án:** Chưa tải dữ liệu không đồng nghĩa database không có dòng nào; cách này có thể làm sai dữ liệu nghiệp vụ.

### Bài 19: Parent đã initialized có đủ chưa?

**Câu hỏi:** Nếu `util.isLoaded(order, "lines")` là true thì mọi field trên từng Line đã tải chưa?

**Đáp án:** Không. Những association trên từng Line có thể chưa được tải; cần xem toàn bộ paths mà DTO/use case truy cập.

### Bài 20: N+1 khác lazy failure

**Câu hỏi:** Vì sao N+1 có thể xuất hiện sau khi “sửa” LazyInitializationException bằng OSIV?

**Đáp án:** Trước đó query bổ sung bị chặn vì context đóng; khi mở lâu hơn, hàng loạt lazy query có thể chạy ở controller/serializer. Cần tối ưu fetch/projection, không chỉ làm exception biến mất.

## 37. Checklist thiết kế kế hoạch tải

Trước khi merge một API/service sử dụng JPA, hãy xác nhận:

1. **Use case cần những field nào?** Có thật sự cần entity graph hay chỉ DTO?
2. **Những association nào có thể LAZY?** Có nested LAZY không?
3. **Mapper có chạy trong service transaction/context phù hợp không?**
4. **Controller có trả entity trực tiếp cho serializer không?**
5. **Có path nào mà serializer có thể tự gọi getter gây SQL không?**
6. **Có dùng `JOIN FETCH`/EntityGraph đúng association cần đọc không?**
7. **Query SELECT có fetch quá nhiều fields hoặc collections không?**
8. **Có N+1 trong vòng lặp map danh sách entities không?**
9. **Có phân trang cùng fetch join collection to-many không?**
10. **COUNT query có được tách khỏi fetch join không?**
11. **Có cần projection để chỉ đọc vài scalar fields không?**
12. **Có dùng OSIV không? Nếu có, đã kiểm tra SQL ngoài service transaction chưa?**
13. **Có cấu hình lazy-load-no-trans riêng provider không? Vì sao cần?**
14. **Có đưa entity/proxy qua async/thread boundary không?**
15. **Có test DTO sau khi transaction service kết thúc không?**
16. **Test có vô tình giữ EntityManager mở, che bug production không?**
17. **Có quan sát SQL count khi dữ liệu tăng từ 1 lên 50/200 rows không?**
18. **Có phân biệt detached, unloaded và null association không?**
19. **Có xử lý cache mà không dùng cache làm giả định correctness không?**
20. **Có bảo vệ authorization/tenant khi projection/fetch dữ liệu không?**

## 38. Tổng kết

~~~text
                   ĐỌC ENTITY TỪ DATABASE
                             |
                             v
                   Thuộc tính đã tải hết?
                       /           \
                      Có           Chưa
                      |             |
                      v             v
              Đọc được giá trị    Cần lazy loading
              ngay trong memory        |
                                 +-----+------+
                                 |            |
                              Context       Context
                              còn hoạt      không còn
                              động          tải được
                                 |            |
                                 v            v
                           Query bổ sung   Lazy initialization
                           (có thể N+1)    failure
                                 |            |
                                 +-----+------+
                                       |
                                       v
                              Thiết kế lại fetch plan
                                       |
                       +---------------+----------------+
                       |               |                |
                       v               v                v
                  JOIN FETCH      EntityGraph      DTO projection
                       |               |                |
                       +---------------+----------------+
                                       |
                                       v
                           Materialize dữ liệu đúng
                           trong query/service boundary
                                       |
                                       v
                          Trả DTO độc lập với JPA context
~~~

Những nguyên tắc cần ghi nhớ:

1. **Lazy loading trì hoãn truy cập database cho đến khi cần dữ liệu**, giúp tránh tải graph không dùng nhưng đòi hỏi phạm vi context/session thích hợp.
2. **Entity detached vẫn chứa những giá trị đã tải**, nhưng association chưa initialized có thể không còn khả năng fetch khi truy cập.
3. **Hibernate `LazyInitializationException` không phải exception chuẩn chung của JPA**; cần chẩn đoán theo lifecycle và loaded state.
4. **Transaction và persistence context không phải một khái niệm**, dù chúng thường gắn chặt trong transaction-scoped ứng dụng.
5. **Service `@Transactional` chỉ giúp khi dữ liệu được đọc/mapped trong phạm vi hiệu lực**, không sửa được mapper chạy sau khi method trả về.
6. **DTO trong service là ranh giới rõ cho REST API**, tách response khỏi Hibernate proxies và vòng đời EntityManager.
7. **`JOIN FETCH` và `EntityGraph` tải association theo use case**, nhưng phải đo SQL, tránh lạm dụng collection fetch và chú ý nested associations.
8. **Projection là lựa chọn tốt cho danh sách/report chỉ cần vài field**, không nhất thiết materialize entity.
9. **N+1 và LazyInitializationException khác nhau**: một bên query quá nhiều khi context còn mở, một bên cần query nhưng context không còn khả năng phục vụ.
10. **OSIV hoặc lazy-load-no-trans có thể che exception nhưng không giải quyết fetch plan**, đồng thời có thể làm tăng SQL ngoài business transaction.
11. **Không chuyển tất cả mappings thành EAGER**, không dùng `@JsonIgnore` để che dữ liệu cần trả và không dùng `merge` chỉ để tải lazy.
12. **Không truyền entity/proxy qua async boundary**, thay bằng ID hoặc DTO snapshot cùng transaction riêng của worker.
13. **Kiểm thử khi context thực sự đã đóng**, tránh để transaction test che lỗi xuất hiện tại REST serialization.
14. **Đo hiệu năng cùng với kiểm tra độ đúng**, đặc biệt khi chuyển sang fetch join, entity graph hoặc mapper duyệt collection.

Vấn đề truy cập dữ liệu chưa tải sau khi ngữ cảnh kết thúc phản ánh một ranh giới kiến trúc chưa rõ ràng giữa **truy xuất dữ liệu** và **sử dụng dữ liệu**. Cách xử lý bền vững là xác định chính xác use case cần gì, chọn fetch plan tương ứng và hoàn thiện DTO hoặc kết quả đọc **trước khi rời khỏi phạm vi JPA có thể tải dữ liệu**, thay vì kéo dài session vô điều kiện chỉ để một getter không báo lỗi.
