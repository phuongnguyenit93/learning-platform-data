# Khai báo truy vấn có tên để quản lý và tái sử dụng trong JPA

Trong ứng dụng sử dụng **Jakarta Persistence (JPA)**, nhiều chức năng cần lặp lại cùng một câu truy vấn: lấy đơn hàng theo khách hàng, đếm đơn ở một trạng thái, hoặc trả dữ liệu phục vụ màn hình danh sách. Nếu mỗi service tự viết lại một chuỗi JPQL, các câu truy vấn dễ khác nhau về điều kiện lọc, thứ tự sắp xếp và tên tham số.

**Named query (truy vấn có tên)** là cơ chế của JPA cho phép **khai báo một câu truy vấn JPQL tĩnh với một tên định danh**, rồi gọi lại bằng tên đó ở những nơi cần sử dụng.

Ví dụ:

~~~java
@NamedQuery(
    name = "PurchaseOrder.findByStatus",
    query = "SELECT o FROM PurchaseOrder o " +
            "WHERE o.status = :status ORDER BY o.id DESC"
)
~~~

Ở tầng truy cập dữ liệu:

~~~java
List<PurchaseOrder> orders = em.createNamedQuery(
        "PurchaseOrder.findByStatus",
        PurchaseOrder.class
    )
    .setParameter("status", OrderStatus.CONFIRMED)
    .getResultList();
~~~

Hai phần này có trách nhiệm khác nhau:

- **Khai báo:** đặt tên, xác định cấu trúc JPQL và các tham số cần thiết.
- **Sử dụng:** tra cứu tên, truyền giá trị tham số, tùy chỉnh phân trang/hint khi phù hợp, rồi thực thi.

Named query giúp **tái sử dụng và quản lý câu truy vấn tập trung**, nhưng không phải là một stored procedure, không phải bảng dữ liệu lưu sẵn và cũng không tự động khiến mọi câu SQL nhanh hơn.

Bài học nằm trong chương **JPQL cơ bản**, tập trung vào `@NamedQuery`, `@NamedQueries`, `EntityManager.createNamedQuery`, tham số, kiểu kết quả, tính đóng gói, lỗi cấu hình và cách lựa chọn giữa named query với truy vấn động.

## 1. Vì sao cần truy vấn có tên?

Giả sử ứng dụng bán hàng có nhiều vị trí lấy đơn hàng đã xác nhận:

~~~java
// OrderReportService
em.createQuery(
    "SELECT o FROM PurchaseOrder o WHERE o.status = :status",
    PurchaseOrder.class
);

// CustomerDashboardService
em.createQuery(
    "SELECT o FROM PurchaseOrder o WHERE o.status = :status",
    PurchaseOrder.class
);

// OrderExportService
em.createQuery(
    "SELECT o FROM PurchaseOrder o WHERE o.status = :status",
    PurchaseOrder.class
);
~~~

Khi nghiệp vụ bổ sung thứ tự `createdAt DESC`, người sửa có thể quên cập nhật một trong ba vị trí. Kết quả giữa các màn hình trở nên không nhất quán.

Với named query:

~~~text
            Định nghĩa JPQL một nơi
                      |
             @NamedQuery("PurchaseOrder.findByStatus")
                      |
         +------------+------------+
         |            |            |
         v            v            v
     Dashboard      Report       Export
         |            |            |
         +------------+------------+
                      |
            createNamedQuery(...)
                      |
                      v
                JPA provider
                      |
                      v
                   Database
~~~

Những lợi ích thường gặp:

1. **Giảm lặp chuỗi JPQL:** không phải copy toàn bộ truy vấn vào nhiều service.
2. **Tạo tên có ý nghĩa:** code gọi `PurchaseOrder.findByStatus` thay cho chuỗi JPQL dài.
3. **Giữ truy vấn tĩnh tập trung:** dễ tìm nơi khai báo để thay đổi điều kiện chung.
4. **Tách cấu trúc truy vấn khỏi tham số:** cùng truy vấn dùng nhiều giá trị `status` khác nhau.
5. **Có khả năng được provider phân tích/kiểm tra metadata sớm:** một số lỗi JPQL được phát hiện khi khởi động persistence unit, tùy provider.
6. **Hỗ trợ nhiều kiểu kết quả:** entity, scalar, aggregate hoặc DTO constructor expression.

Tuy nhiên, **tên truy vấn không thay thế việc thiết kế repository/service và transaction**. Nó chỉ là một thành phần metadata truy vấn được provider quản lý.

## 2. @NamedQuery: định nghĩa một câu JPQL có tên

Annotation `jakarta.persistence.NamedQuery` có hai thành phần quan trọng nhất:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `name` | Tên dùng để truy xuất truy vấn trong persistence unit |
| `query` | Nội dung câu JPQL tĩnh |
| `hints` | Tùy chọn cung cấp query hints cho provider |
| `lockMode` | Có thể chỉ định lock mode phù hợp với truy vấn và đặc tả |

Ví dụ:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.NamedQuery;

@Entity
@NamedQuery(
    name = "PurchaseOrder.findByStatus",
    query = "SELECT o FROM PurchaseOrder o " +
            "WHERE o.status = :status ORDER BY o.id DESC"
)
public class PurchaseOrder {
    // @Id, thuộc tính, constructor...
}
~~~

Chú ý các thành phần:

- `PurchaseOrder.findByStatus` là **tên định danh do ứng dụng lựa chọn**.
- `SELECT o FROM PurchaseOrder o` là **JPQL**, trong đó `PurchaseOrder` là **tên entity JPA**.
- `o.status` là **thuộc tính Java được ánh xạ**.
- `:status` là **named parameter**, sẽ được gán giá trị lúc thực thi.
- `ORDER BY o.id DESC` xác định thứ tự trả kết quả.

Đây **không phải** SQL dùng tên bảng `purchase_orders` và cột `order_status`. Nếu tên bảng/cột vật lý khác tên Java, câu JPQL vẫn dùng mô hình entity/attribute.

### 2.1. Named query là metadata của persistence unit

Một named query có thể được khai báo cạnh một entity, nhưng khi được đăng ký, tên truy vấn nằm trong **phạm vi của persistence unit**, không phải một phương thức chỉ có thể gọi từ object instance của class đó.

Ví dụ:

~~~java
em.createNamedQuery(
    "PurchaseOrder.findByStatus",
    PurchaseOrder.class
);
~~~

không cần phải có instance `PurchaseOrder` trước khi gọi. `EntityManager` lấy định nghĩa truy vấn theo tên từ metadata của persistence unit.

Điều này cũng có nghĩa **tên named query phải duy nhất trong phạm vi persistence unit** theo quy tắc metadata. Không nên khai báo hai truy vấn khác nhau có cùng tên `PurchaseOrder.findByStatus` trong những entity khác nhau thuộc cùng persistence unit.

### 2.2. Quy ước đặt tên

JPA không bắt buộc tên phải có dạng `EntityName.methodName`, nhưng quy ước này có ích:

~~~text
PurchaseOrder.findByStatus
PurchaseOrder.findByCustomerAndStatus
PurchaseOrder.countByStatus
PurchaseOrder.summaryByStatus
Customer.findByEmail
Product.searchByName
~~~

Nên:

- Chọn một prefix thể hiện entity hoặc nhóm nghiệp vụ.
- Dùng tên tác vụ rõ: `find`, `count`, `search`, `summary`.
- Nhất quán về chữ hoa/chữ thường; tên truy vấn là định danh phân biệt chính xác.
- Không lấy tên query làm nơi nhét input của người dùng.
- Tránh tên mơ hồ như `query1`, `q2` hoặc `listAllData`.

Tên không phải đường dẫn Java hay SQL. Nó là **khóa để tra cứu metadata**.

## 3. Mô hình hoàn chỉnh để minh họa

Bài học dùng Java 17+, Jakarta Persistence 3.x và các entity đơn hàng/khách hàng. Các ví dụ phần tiếp theo giả định hai entity này được JPA quản lý trong cùng persistence unit.

### 3.1. Enum OrderStatus

~~~java
package com.example.shop.domain;

public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
~~~

### 3.2. Entity Customer

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 180)
    private String email;

    protected Customer() {
    }

    public Customer(String email) {
        this.email = Objects.requireNonNull(email);
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

### 3.3. Entity PurchaseOrder khai báo nhiều named queries

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.NamedQueries;
import jakarta.persistence.NamedQuery;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
@NamedQueries({
    @NamedQuery(
        name = "PurchaseOrder.findByCustomerAndStatus",
        query =
            "SELECT o FROM PurchaseOrder o " +
            "WHERE o.customer.id = :customerId " +
            "AND o.status = :status " +
            "ORDER BY o.createdAt DESC, o.id DESC"
    ),
    @NamedQuery(
        name = "PurchaseOrder.countByStatus",
        query =
            "SELECT COUNT(o) FROM PurchaseOrder o " +
            "WHERE o.status = :status"
    ),
    @NamedQuery(
        name = "PurchaseOrder.summaryByStatus",
        query =
            "SELECT new com.example.shop.dto.OrderSummary(" +
            "o.id, o.orderCode, c.email, o.totalAmount) " +
            "FROM PurchaseOrder o JOIN o.customer c " +
            "WHERE o.status = :status " +
            "ORDER BY o.id DESC"
    ),
    @NamedQuery(
        name = "PurchaseOrder.findWithCustomer",
        query =
            "SELECT o FROM PurchaseOrder o " +
            "JOIN FETCH o.customer " +
            "WHERE o.id = :orderId"
    )
})
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
        name = "order_code",
        nullable = false,
        unique = true,
        length = 60
    )
    private String orderCode;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status = OrderStatus.DRAFT;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(
        name = "total_amount",
        nullable = false,
        precision = 15,
        scale = 2
    )
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            String orderCode,
            Customer customer,
            BigDecimal totalAmount) {
        this.orderCode = Objects.requireNonNull(orderCode);
        this.customer = Objects.requireNonNull(customer);
        this.totalAmount = Objects.requireNonNull(totalAmount);
    }

    @PrePersist
    void initializeCreatedAt() {
        if (createdAt == null) {
            createdAt = LocalDateTime.now();
        }
    }

    public Long getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Customer getCustomer() {
        return customer;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void confirm() {
        status = OrderStatus.CONFIRMED;
    }
}
~~~

Những điểm quan trọng:

- `@NamedQueries` gom **nhiều `@NamedQuery`** trên một entity.
- `name` của mỗi truy vấn khác nhau và được tra cứu theo chuỗi chính xác.
- `query` là JPQL; `o.customer.id` là đường dẫn qua association `customer`.
- `OrderStatus` được ánh xạ bằng `@Enumerated(EnumType.STRING)`, nên tham số Java có kiểu enum.
- `summaryByStatus` dùng JPQL **constructor expression** để tạo DTO.
- `findWithCustomer` dùng `JOIN FETCH` để chủ động tải association `customer` cho một đơn hàng.

`@PrePersist` chỉ minh họa cách tạo thời điểm khi persist. Ứng dụng production có thể dùng thời gian từ tầng nghiệp vụ hoặc cơ chế audit phù hợp; điều đó không thay đổi cách hoạt động của named query.

### 3.4. DTO cho named query projection

JPQL constructor expression cần một class có constructor tương thích. Java record có constructor theo đúng thứ tự các component:

~~~java
package com.example.shop.dto;

import java.math.BigDecimal;

public record OrderSummary(
    Long id,
    String orderCode,
    String customerEmail,
    BigDecimal totalAmount
) {
}
~~~

Câu JPQL:

~~~jpql
SELECT new com.example.shop.dto.OrderSummary(
    o.id,
    o.orderCode,
    c.email,
    o.totalAmount
)
FROM PurchaseOrder o
JOIN o.customer c
WHERE o.status = :status
ORDER BY o.id DESC
~~~

trả về `OrderSummary`, **không phải `PurchaseOrder` managed**. Các record được tạo từ constructor projection là giá trị kết quả; không dùng `EntityManager.persist(summary)` hay dirty checking của entity để cập nhật chúng.

### 3.5. Schema quan hệ minh họa

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(180) NOT NULL UNIQUE
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(60) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE INDEX idx_orders_customer_status_created
    ON purchase_orders (
        customer_id,
        status,
        created_at,
        id
    );
~~~

Câu SQL và index chỉ là minh họa thiết kế database, không phải code sinh tự động từ annotation. Khi dùng Flyway/Liquibase, cần migration tương ứng.

## 4. Gọi named query bằng EntityManager.createNamedQuery

JPA cung cấp overload nhận tên và result class:

~~~java
TypedQuery<PurchaseOrder> query =
    em.createNamedQuery(
        "PurchaseOrder.findByCustomerAndStatus",
        PurchaseOrder.class
    );
~~~

Đối tượng `TypedQuery<PurchaseOrder>` cho biết kết quả mong muốn là entity `PurchaseOrder`.

### 4.1. Truyền tham số rồi lấy danh sách

~~~java
List<PurchaseOrder> orders = em.createNamedQuery(
        "PurchaseOrder.findByCustomerAndStatus",
        PurchaseOrder.class
    )
    .setParameter("customerId", 42L)
    .setParameter("status", OrderStatus.CONFIRMED)
    .getResultList();
~~~

Điều đang xảy ra:

1. Tên `PurchaseOrder.findByCustomerAndStatus` được tra cứu từ metadata.
2. Provider tạo query object cho lần gọi này.
3. `customerId` và `status` được binding bằng giá trị hiện tại.
4. `getResultList()` thực thi và trả về danh sách kết quả.
5. Kết quả là `List<PurchaseOrder>` có thể rỗng nếu không có bản ghi khớp.

**Không ghép giá trị trực tiếp vào chuỗi JPQL.** Named query đã chứa các placeholder tham số; khi thực thi, `setParameter` truyền giá trị một cách an toàn và tách cấu trúc truy vấn khỏi dữ liệu.

### 4.2. Query object không phải bản ghi kết quả được cache sẵn

Mỗi lần:

~~~java
em.createNamedQuery("PurchaseOrder.findByCustomerAndStatus",
                    PurchaseOrder.class);
~~~

bạn đang tạo/truy xuất một **đối tượng truy vấn có thể thiết lập tham số và thực thi** theo metadata đã đăng ký. Named query **không có nghĩa** JPA trả lại dữ liệu đã tính từ lần gọi trước.

Provider có thể tối ưu việc parse/compile JPQL hoặc cache query plan, nhưng mức tối ưu phụ thuộc implementation. Query result cache, nếu có, là một cơ chế riêng và không tự bật chỉ vì dùng named query.

### 4.3. Cùng named query, nhiều bộ tham số

~~~java
List<PurchaseOrder> draftOrders = em.createNamedQuery(
        "PurchaseOrder.findByCustomerAndStatus",
        PurchaseOrder.class
    )
    .setParameter("customerId", 42L)
    .setParameter("status", OrderStatus.DRAFT)
    .getResultList();

List<PurchaseOrder> confirmedOrders = em.createNamedQuery(
        "PurchaseOrder.findByCustomerAndStatus",
        PurchaseOrder.class
    )
    .setParameter("customerId", 42L)
    .setParameter("status", OrderStatus.CONFIRMED)
    .getResultList();
~~~

Chỉ có **một định nghĩa truy vấn**, nhưng nó được thực thi với **hai giá trị tham số** khác nhau.

Không dùng một instance `Query` làm đối tượng chia sẻ toàn cục giữa nhiều request/thread. `Query`/`EntityManager` nên được dùng theo phạm vi thích hợp, với tham số và transaction của từng lần gọi.

## 5. Dùng @NamedQueries để quản lý nhiều truy vấn

Khi một entity có nhiều nhu cầu truy cập, `@NamedQueries` có thể gom các định nghĩa:

~~~java
@NamedQueries({
    @NamedQuery(
        name = "Customer.findByEmail",
        query = "SELECT c FROM Customer c WHERE c.email = :email"
    ),
    @NamedQuery(
        name = "Customer.countAll",
        query = "SELECT COUNT(c) FROM Customer c"
    )
})
@Entity
public class Customer {
    // ...
}
~~~

Đây là **ví dụ bổ sung độc lập** về cách khai báo ở entity Customer. Nếu áp dụng vào một project, hãy đặt annotation vào class tương ứng và tránh khai báo hai lần cùng tên trong persistence unit.

### 5.1. Khi nào dùng một @NamedQuery, khi nào dùng @NamedQueries?

- Có một truy vấn: dùng `@NamedQuery`.
- Có nhiều truy vấn cùng khai báo tại một class: dùng `@NamedQueries` hoặc khai báo nhiều annotation lặp ở phiên bản Jakarta Persistence/Java được hỗ trợ.
- Các truy vấn không liên quan tới nhau về nghiệp vụ: có thể khai báo cạnh các entity thích hợp thay vì dồn tất cả vào một class.

**Nơi đặt annotation không giới hạn nơi được phép gọi query**. Khi query đã đăng ký trong persistence unit, bất kỳ `EntityManager` thuộc persistence unit tương ứng cũng có thể gọi theo tên.

### 5.2. Phạm vi đặt tên: tránh collision

Trường hợp xấu:

~~~java
// Trên Customer:
@NamedQuery(name = "findAll", query = "SELECT c FROM Customer c")

// Trên PurchaseOrder:
@NamedQuery(name = "findAll", query = "SELECT o FROM PurchaseOrder o")
~~~

Cả hai tên đều là `findAll`, gây trùng trong cùng persistence unit. Thay bằng:

~~~text
Customer.findAll
PurchaseOrder.findAll
~~~

**Đừng xem tên query tự động được namespace theo class chứa annotation.** Chỉ có tên mà bạn khai báo là khóa tra cứu.

## 6. Tham số named parameter và positional parameter

JPQL hỗ trợ tham số theo tên:

~~~jpql
SELECT o
FROM PurchaseOrder o
WHERE o.customer.id = :customerId
  AND o.status = :status
~~~

Binding:

~~~java
query.setParameter("customerId", customerId);
query.setParameter("status", status);
~~~

Đây là cách thường rõ ràng nhất với truy vấn phức tạp vì tên thể hiện ý nghĩa.

JPQL cũng có tham số vị trí:

~~~jpql
SELECT o
FROM PurchaseOrder o
WHERE o.customer.id = ?1
  AND o.status = ?2
~~~

Binding:

~~~java
query.setParameter(1, customerId);
query.setParameter(2, status);
~~~

### 6.1. Nên chọn loại nào?

| Tiêu chí | Tham số theo tên | Tham số vị trí |
| --- | --- | --- |
| Ví dụ JPQL | `:customerId` | `?1` |
| Binding | `setParameter("customerId", value)` | `setParameter(1, value)` |
| Khả năng đọc | Rõ nghĩa khi có nhiều điều kiện | Gọn khi rất ít tham số |
| Rủi ro | Sai tên, thiếu binding | Nhầm thứ tự/vị trí |
| Khuyến nghị cho named query dài | Thường dễ bảo trì hơn | Vẫn hợp lệ nếu nhất quán |

Không nên trộn cả hai kiểu trong cùng một câu JPQL khi không có lý do; dùng một quy ước rõ ràng cho từng query.

### 6.2. Binding enum và kiểu Java

Với trường:

~~~java
@Enumerated(EnumType.STRING)
private OrderStatus status;
~~~

tham số trong JPQL:

~~~jpql
WHERE o.status = :status
~~~

nên nhận **giá trị enum Java**:

~~~java
query.setParameter("status", OrderStatus.CONFIRMED);
~~~

Không suy luận rằng vì cột SQL lưu chuỗi `"CONFIRMED"` nên phải binding bằng `String` trong mọi câu JPQL. JPQL so sánh thuộc tính được ánh xạ theo **kiểu Java của entity**.

### 6.3. Không truyền input vào phần cấu trúc truy vấn

Đây là anti-pattern:

~~~java
String queryText =
    "SELECT o FROM PurchaseOrder o WHERE o.orderCode = '" +
    userInput + "'";
~~~

Việc ghép dữ liệu trực tiếp vào query dễ gây lỗi escaping, logic và injection.

Với named query:

~~~java
@NamedQuery(
    name = "PurchaseOrder.findByCode",
    query = "SELECT o FROM PurchaseOrder o " +
            "WHERE o.orderCode = :orderCode"
)
~~~

và:

~~~java
query.setParameter("orderCode", userInput);
~~~

Cấu trúc JPQL không thay đổi theo input.

Nếu muốn người dùng chọn cột `ORDER BY` hoặc hướng `ASC/DESC`, **không được binding tên field như một giá trị tham số thông thường**. Tên field là **cấu trúc truy vấn**, cần lựa chọn từ danh sách cho phép hoặc dùng Criteria API/truy vấn động an toàn.

## 7. getResultList và getSingleResult

Hai API đều thực thi truy vấn đọc nhưng khác hợp đồng kết quả.

### 7.1. getResultList()

~~~java
List<PurchaseOrder> orders = em.createNamedQuery(
        "PurchaseOrder.findByCustomerAndStatus",
        PurchaseOrder.class
    )
    .setParameter("customerId", customerId)
    .setParameter("status", OrderStatus.DRAFT)
    .getResultList();
~~~

Nếu không có kết quả, trả danh sách rỗng. Trường hợp **0..N kết quả**, đây là lựa chọn thường phù hợp.

### 7.2. getSingleResult()

Với named query chọn theo ID:

~~~java
PurchaseOrder order = em.createNamedQuery(
        "PurchaseOrder.findWithCustomer",
        PurchaseOrder.class
    )
    .setParameter("orderId", orderId)
    .getSingleResult();
~~~

API này đòi hỏi kết quả duy nhất theo hợp đồng:

- `NoResultException` nếu không có kết quả.
- `NonUniqueResultException` nếu kết quả không duy nhất.
- Các ngoại lệ persistence hoặc giao dịch khác có thể xuất hiện nếu query/DB gặp lỗi.

Ví dụ xử lý khi không tìm thấy:

~~~java
import jakarta.persistence.NoResultException;

public PurchaseOrder findWithCustomer(
        EntityManager em,
        Long orderId) {
    try {
        return em.createNamedQuery(
                "PurchaseOrder.findWithCustomer",
                PurchaseOrder.class
            )
            .setParameter("orderId", orderId)
            .getSingleResult();
    } catch (NoResultException ex) {
        return null;
    }
}
~~~

**Chỉ catch ngoại lệ phù hợp.** Không nên bắt `RuntimeException` rồi coi mọi lỗi SQL, sai JPQL hoặc lỗi quyền truy cập là “không có dữ liệu”.

Có thể dùng `getResultList()` với điều kiện trả một dòng khi muốn tránh exception cho trường hợp không tìm thấy:

~~~java
List<PurchaseOrder> rows = em.createNamedQuery(
        "PurchaseOrder.findWithCustomer",
        PurchaseOrder.class
    )
    .setParameter("orderId", orderId)
    .getResultList();

PurchaseOrder order =
    rows.isEmpty() ? null : rows.get(0);
~~~

Nếu truy vấn theo khóa chính đã biết và **không cần fetch plan đặc biệt**, `em.find(PurchaseOrder.class, id)` thường gọn hơn named query. Nhưng named query với `JOIN FETCH` có thể hữu ích khi cần tải một association xác định.

## 8. Named query trả kết quả tổng hợp

Một truy vấn không bắt buộc phải trả entity. Ví dụ đếm đơn hàng theo trạng thái:

~~~java
@NamedQuery(
    name = "PurchaseOrder.countByStatus",
    query = "SELECT COUNT(o) FROM PurchaseOrder o " +
            "WHERE o.status = :status"
)
~~~

Cách gọi:

~~~java
Long count = em.createNamedQuery(
        "PurchaseOrder.countByStatus",
        Long.class
    )
    .setParameter("status", OrderStatus.CONFIRMED)
    .getSingleResult();
~~~

Với JPQL `COUNT`, kiểu kết quả là `Long`. Nó trả về một giá trị đếm, kể cả khi số bản ghi phù hợp bằng 0.

Một số phép tổng hợp khác:

~~~jpql
SELECT SUM(o.totalAmount)
FROM PurchaseOrder o
WHERE o.status = :status
~~~

~~~jpql
SELECT AVG(o.totalAmount)
FROM PurchaseOrder o
WHERE o.status = :status
~~~

Khi dùng chúng trong named query, phải xem kiểu kết quả theo JPQL và xử lý `NULL` với những phép tổng hợp có thể không có bản ghi để tính. Không ép mọi kết quả về `PurchaseOrder.class` chỉ vì named query được khai báo trên class `PurchaseOrder`.

## 9. Named query với DTO constructor expression

Dùng định nghĩa:

~~~java
@NamedQuery(
    name = "PurchaseOrder.summaryByStatus",
    query =
        "SELECT new com.example.shop.dto.OrderSummary(" +
        "o.id, o.orderCode, c.email, o.totalAmount) " +
        "FROM PurchaseOrder o JOIN o.customer c " +
        "WHERE o.status = :status " +
        "ORDER BY o.id DESC"
)
~~~

Gọi:

~~~java
List<OrderSummary> summaries = em.createNamedQuery(
        "PurchaseOrder.summaryByStatus",
        OrderSummary.class
    )
    .setParameter("status", OrderStatus.CONFIRMED)
    .getResultList();
~~~

Các lưu ý:

1. JPQL `new` dùng **tên class đầy đủ** trong constructor expression.
2. Kiểu và thứ tự arguments phải khớp với constructor có thể truy cập.
3. `OrderSummary` là DTO/record, không phải entity managed.
4. Câu query có thể chỉ lấy những cột cần thiết cho màn hình.
5. DTO projection giúp tránh việc serializer vô tình duyệt toàn bộ graph của entity.

Nếu DTO đổi package hoặc đổi constructor, chuỗi JPQL trong named query cần được cập nhật. Với provider có validation tại startup, lỗi constructor có thể được phát hiện sớm; không nên giả định mọi provider đều kiểm tra hết tại đúng cùng một thời điểm.

### 9.1. Vì sao DTO projection không cần flush để tạo DTO?

`SELECT new ...` chỉ mô tả cách chuyển mỗi hàng kết quả thành object Java khi truy vấn thực thi. Nó không phải `INSERT`/`UPDATE` vào database.

Nếu đang có managed entity thay đổi trong cùng transaction, flush mode có thể ảnh hưởng dữ liệu truy vấn nhìn thấy; nhưng bản thân việc tạo DTO không làm DTO trở thành managed hoặc persistable.

## 10. Phân trang một named query

Một named query tĩnh vẫn có thể phân trang khi thực thi:

~~~java
int page = 2;
int size = 20;

List<PurchaseOrder> orders = em.createNamedQuery(
        "PurchaseOrder.findByCustomerAndStatus",
        PurchaseOrder.class
    )
    .setParameter("customerId", customerId)
    .setParameter("status", OrderStatus.CONFIRMED)
    .setFirstResult(page * size)
    .setMaxResults(size)
    .getResultList();
~~~

`setFirstResult` và `setMaxResults` được thiết lập trên **query object của lần gọi**, không sửa metadata `@NamedQuery`.

Đánh giá kết quả:

- `setFirstResult(40)` bỏ qua 40 kết quả đầu theo thứ tự truy vấn.
- `setMaxResults(20)` giới hạn tối đa 20 kết quả trả về.
- Thứ tự `ORDER BY o.createdAt DESC, o.id DESC` giúp phân trang xác định hơn khi nhiều đơn cùng thời gian tạo.
- `page` ở ví dụ đánh số từ 0; cần kiểm tra không âm và tránh tràn số khi nhân với `size` trong code production.

**Phân trang cần thứ tự ổn định.** Nếu query không có `ORDER BY`, database không bảo đảm thứ tự trang. Nếu chỉ sort theo `createdAt` và có nhiều bản ghi trùng thời gian, thêm `id` làm tiêu chí phân biệt thường có ích.

### 10.1. Tổng số bản ghi dùng count query riêng

Khi API trả một trang kèm tổng số kết quả, nên có một query đếm phù hợp điều kiện lọc.

Ví dụ muốn tổng số đơn theo cả customer và status, khai báo thêm:

~~~java
@NamedQuery(
    name = "PurchaseOrder.countByCustomerAndStatus",
    query =
        "SELECT COUNT(o) FROM PurchaseOrder o " +
        "WHERE o.customer.id = :customerId " +
        "AND o.status = :status"
)
~~~

Cách gọi:

~~~java
Long total = em.createNamedQuery(
        "PurchaseOrder.countByCustomerAndStatus",
        Long.class
    )
    .setParameter("customerId", customerId)
    .setParameter("status", OrderStatus.CONFIRMED)
    .getSingleResult();
~~~

Không dùng `countByStatus` ban đầu cho tổng số trang lọc theo khách hàng vì điều kiện đếm không tương ứng với điều kiện truy vấn danh sách.

### 10.2. Tránh collection fetch join khi phân trang

Một named query có `JOIN FETCH` trên quan hệ **to-many** có thể nhân số dòng SQL, khiến offset/limit trên parent không hoạt động như kỳ vọng và provider có thể xử lý phân trang trong bộ nhớ hoặc báo lỗi tùy cấu hình.

Với `PurchaseOrder.findWithCustomer` ở ví dụ, fetch join là **to-one** nên không gây nhân hàng theo số child theo cách của collection fetch join. Dù vậy, khi danh sách lớn nên kiểm tra query plan và fetch strategy.

Khi cần phân trang root entity và lấy collection con, thường cân nhắc truy vấn hai bước, batch fetching hoặc DTO projection thay vì áp dụng `setMaxResults` tùy tiện trên một collection fetch join.

## 11. Named query và thời điểm thực thi

Annotation:

~~~java
@NamedQuery(
    name = "PurchaseOrder.findByStatus",
    query = "SELECT o FROM PurchaseOrder o WHERE o.status = :status"
)
~~~

chỉ khai báo metadata. Nó **không tự chạy** khi application khởi động.

Ở thời điểm:

~~~java
TypedQuery<PurchaseOrder> query =
    em.createNamedQuery(
        "PurchaseOrder.findByStatus",
        PurchaseOrder.class
    );
~~~

JPA tạo query object dựa trên metadata. SQL đọc dữ liệu thường được thực hiện khi gọi:

~~~java
query.setParameter("status", OrderStatus.DRAFT);
List<PurchaseOrder> rows = query.getResultList();
~~~

Provider có thể kiểm tra/biên dịch JPQL ở giai đoạn khởi động hoặc khi query được tạo/được thực thi. **Không có nghĩa named query là một SQL prepared statement được kết nối và giữ mãi từ lúc boot**.

### 11.1. Flush mode khi thực thi named query

Nếu đang trong transaction có managed entity chưa flush:

~~~java
em.persist(newOrder);

List<PurchaseOrder> rows = em.createNamedQuery(
        "PurchaseOrder.findByStatus",
        PurchaseOrder.class
    )
    .setParameter("status", OrderStatus.DRAFT)
    .getResultList();
~~~

Với `FlushModeType.AUTO` theo hợp đồng JPA, provider phải bảo đảm kết quả truy vấn phản ánh các thay đổi pending khi cần; nó có thể flush trước query. Tuy nhiên không phải mọi SELECT đều phát flush mới.

Query object có thể đặt flush mode khi cần:

~~~java
query.setFlushMode(
    jakarta.persistence.FlushModeType.COMMIT
);
~~~

Khi dùng `COMMIT`, ảnh hưởng của pending changes lên kết quả query trước commit có thể không được xác định theo một cách đồng nhất. **Named query không tạo một transaction mới và không commit giao dịch**; nó vẫn hoạt động trong transaction/persistence context của lần thực thi.

### 11.2. Có thể dùng named query ngoài transaction không?

Truy vấn SELECT thông thường có thể được thực hiện trong ngữ cảnh phù hợp mà không cần ứng dụng gọi `begin` thủ công, tùy mô hình EntityManager và container. Nhưng nếu cần dữ liệu nhất quán trong một luồng nghiệp vụ, lazy loading, locking hoặc cập nhật entity, cần ranh giới transaction rõ ràng.

Đặc biệt, named query kiểu `UPDATE` hoặc `DELETE` là bulk DML; việc thực thi cập nhật database đòi hỏi transaction phù hợp.

## 12. @NamedQuery có thể khai báo UPDATE và DELETE không?

Named query chứa **JPQL**, mà JPQL có những câu bulk UPDATE/DELETE.

Ví dụ:

~~~java
@NamedQuery(
    name = "PurchaseOrder.cancelDrafts",
    query =
        "UPDATE PurchaseOrder o " +
        "SET o.status = :cancelled " +
        "WHERE o.status = :draft"
)
~~~

Thực thi bằng:

~~~java
int affected = em.createNamedQuery(
        "PurchaseOrder.cancelDrafts"
    )
    .setParameter("draft", OrderStatus.DRAFT)
    .setParameter("cancelled", OrderStatus.CANCELLED)
    .executeUpdate();
~~~

**Không gọi `getResultList()` cho bulk UPDATE/DELETE.** `executeUpdate()` trả số entity/row bị ảnh hưởng theo ngữ nghĩa JPA.

Cảnh báo quan trọng:

- Bulk JPQL UPDATE/DELETE tác động trực tiếp đến dữ liệu và **không đồng bộ tự động tất cả managed instance** trong persistence context như việc sửa từng entity.
- Không kích hoạt entity lifecycle, cascade và optimistic version checking theo đúng cách cập nhật entity managed thông thường.
- Persistence context đã tải những entity liên quan có thể trở nên **stale**.
- Cần chú ý `flush` trước bulk operation và `clear`/refresh sau đó khi cần, không xóa context bừa vì có thể mất thay đổi chưa flush.
- Cần transaction hoạt động và xử lý rollback khi lỗi.

Vì vậy một named query bulk DML không phải “phiên bản nhanh hơn hoàn toàn tương đương” với việc gọi method nghiệp vụ trên từng entity. Chỉ dùng khi hiểu rõ tác động tới lifecycle và persistence context.

## 13. Named query khác dynamic JPQL như thế nào?

### 13.1. Named query: cấu trúc tĩnh

~~~java
@NamedQuery(
    name = "PurchaseOrder.findByCustomerAndStatus",
    query =
        "SELECT o FROM PurchaseOrder o " +
        "WHERE o.customer.id = :customerId " +
        "AND o.status = :status"
)
~~~

Các điều kiện `customerId` và `status` luôn thuộc cấu trúc query. Có thể đổi **giá trị** của tham số, nhưng không thể thêm/bớt phần `WHERE` chỉ bằng `setParameter`.

### 13.2. Dynamic JPQL: cấu trúc phụ thuộc điều kiện

Ví dụ một màn hình có bộ lọc tùy chọn:

~~~text
customerId: có thể nhập hoặc bỏ trống
status:     có thể nhập hoặc bỏ trống
fromDate:   có thể nhập hoặc bỏ trống
search:     có thể nhập hoặc bỏ trống
~~~

Nếu tổ hợp điều kiện thay đổi nhiều, các lựa chọn là:

- Tạo nhiều named query cho những tổ hợp phổ biến, có ý nghĩa rõ.
- Dùng JPQL động có kiểm soát, chỉ ghép cấu trúc do ứng dụng xây dựng, luôn bind dữ liệu bằng parameter.
- Dùng **Criteria API** hoặc abstraction tương đương để xây điều kiện động.
- Đặt logic truy vấn trong repository chuyên trách.

Không nên cố khai báo hàng trăm named query cho mọi tổ hợp lọc chỉ để tránh viết Criteria API. Named query thích hợp nhất với **truy vấn thường dùng, ổn định về cấu trúc**.

### 13.3. Mẫu điều kiện optional trong một truy vấn

Đôi khi có thể viết:

~~~java
@NamedQuery(
    name = "PurchaseOrder.filter",
    query =
        "SELECT o FROM PurchaseOrder o " +
        "WHERE (:status IS NULL OR o.status = :status) " +
        "ORDER BY o.id DESC"
)
~~~

Cách này tiện khi số filter ít, nhưng có những hệ quả:

- Cần binding đủ tham số, kể cả giá trị null phù hợp với kiểu.
- Query optimizer có thể khó tối ưu điều kiện `OR` hơn điều kiện tương đương không có `OR`.
- Không mở rộng tốt với nhiều nhánh lọc và join tùy chọn.
- Null parameter đôi khi cần thông tin kiểu rõ hơn tùy provider/dialect.

**Named query không phải yêu cầu phải biến mọi filter động thành biểu thức `:param IS NULL OR ...`.** Hãy lựa chọn dựa trên độ rõ ràng và hiệu năng thực tế.

## 14. Phân biệt @NamedQuery và @NamedNativeQuery

Hai annotation gần tên nhưng ngôn ngữ khác nhau:

| Tiêu chí | `@NamedQuery` | `@NamedNativeQuery` |
| --- | --- | --- |
| Ngôn ngữ | **JPQL** | **SQL native** |
| Dùng tên entity Java | Có | Không, dùng bảng SQL |
| Dùng tên attribute Java | Có | Không, dùng cột SQL |
| Tính portable | Cao hơn khi viết theo JPQL chuẩn | Phụ thuộc database/dialect |
| Kiểu kết quả | Entity/scalar/DTO constructor JPQL | Có thể dùng entity resultClass hoặc result set mapping |
| Khi phù hợp | CRUD/query nghiệp vụ theo entity model | Truy vấn cần tính năng SQL đặc thù, CTE/hàm dialect... |

Named JPQL:

~~~java
@NamedQuery(
    name = "PurchaseOrder.findByCode",
    query = "SELECT o FROM PurchaseOrder o " +
            "WHERE o.orderCode = :code"
)
~~~

Named native SQL:

~~~java
@NamedNativeQuery(
    name = "PurchaseOrder.nativeFindByCode",
    query =
        "SELECT o.* FROM purchase_orders o " +
        "WHERE o.order_code = ?",
    resultClass = PurchaseOrder.class
)
~~~

Truy xuất named native query:

~~~java
List<PurchaseOrder> rows = em.createNamedQuery(
        "PurchaseOrder.nativeFindByCode",
        PurchaseOrder.class
    )
    .setParameter(1, code)
    .getResultList();
~~~

Với native SQL, dùng positional parameters theo cách portable thường an toàn hơn; **named parameters trong native SQL không được hỗ trợ thống nhất theo mọi JPA provider**. Cần dựa vào provider đang dùng nếu muốn cú pháp native đặc biệt.

`resultClass = PurchaseOrder.class` đòi hỏi SELECT đủ các cột cần để materialize entity theo mapping; không thể mặc định một câu native SELECT chỉ lấy hai cột vẫn tạo được mọi entity mapping hợp lệ.

**Đừng khai báo SQL có tên bảng/cột vật lý vào `@NamedQuery`.** Nếu cần native SQL, dùng `@NamedNativeQuery` hoặc `createNativeQuery`.

## 15. Khai báo named queries trong XML thay vì annotation

Ngoài annotation, JPA có hỗ trợ **metadata XML mapping**, thường dùng file `META-INF/orm.xml`. Đây là lựa chọn khi muốn tập trung cấu hình JPQL ngoài Java source hoặc giữ mapping metadata tách khỏi entity class.

Ví dụ minh họa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    version="3.1">

    <named-query name="PurchaseOrder.findAll">
        <query>
            <![CDATA[
                SELECT o FROM PurchaseOrder o
                ORDER BY o.id DESC
            ]]>
        </query>
    </named-query>

</entity-mappings>
~~~

Đây là ví dụ metadata cho Jakarta Persistence 3.1; phiên bản và namespace của XML phải tương thích với runtime/persistence unit đang sử dụng.

Một số lưu ý:

1. Cần bảo đảm file mapping được provider phát hiện hoặc đăng ký trong persistence unit theo cấu hình.
2. Không khai báo trùng tên một named query ở annotation và XML mà không hiểu quy tắc override/metadata của provider và đặc tả.
3. Tên dùng lúc gọi vẫn là `PurchaseOrder.findAll`.
4. JPQL trong XML vẫn dùng tên entity/attribute Java, không phải SQL native.
5. Chọn annotation hay XML theo convention của dự án; không có yêu cầu phải trộn cả hai.

Khi ứng dụng nhỏ hoặc query gắn chặt entity, annotation thường thuận tiện. Với hệ thống muốn quản lý metadata riêng, XML có thể phù hợp.

## 16. Có nên đặt mọi truy vấn trên entity?

Không nhất thiết. Named query là metadata, còn logic sử dụng query thuộc tầng truy cập dữ liệu.

Một cấu trúc code có thể là:

~~~text
src/main/java/com/example/shop/
    domain/
        Customer.java
        PurchaseOrder.java
        OrderStatus.java
    dto/
        OrderSummary.java
    repository/
        PurchaseOrderReader.java
    service/
        OrderSearchService.java
~~~

Trên `PurchaseOrder`: khai báo metadata.

Trên `PurchaseOrderReader`: dùng named query và đóng gói việc binding tham số:

~~~java
package com.example.shop.repository;

import com.example.shop.domain.OrderStatus;
import com.example.shop.domain.PurchaseOrder;
import com.example.shop.dto.OrderSummary;
import jakarta.persistence.EntityManager;
import java.util.List;

public final class PurchaseOrderReader {

    private final EntityManager em;

    public PurchaseOrderReader(EntityManager em) {
        this.em = em;
    }

    public List<PurchaseOrder> findByCustomerAndStatus(
            Long customerId,
            OrderStatus status,
            int offset,
            int limit) {

        if (customerId == null || status == null) {
            throw new IllegalArgumentException(
                "customerId and status are required");
        }
        if (offset < 0 || limit <= 0) {
            throw new IllegalArgumentException(
                "Invalid pagination arguments");
        }

        return em.createNamedQuery(
                "PurchaseOrder.findByCustomerAndStatus",
                PurchaseOrder.class
            )
            .setParameter("customerId", customerId)
            .setParameter("status", status)
            .setFirstResult(offset)
            .setMaxResults(limit)
            .getResultList();
    }

    public List<OrderSummary> summariesByStatus(
            OrderStatus status) {

        return em.createNamedQuery(
                "PurchaseOrder.summaryByStatus",
                OrderSummary.class
            )
            .setParameter("status", status)
            .getResultList();
    }

    public long countByStatus(OrderStatus status) {
        return em.createNamedQuery(
                "PurchaseOrder.countByStatus",
                Long.class
            )
            .setParameter("status", status)
            .getSingleResult();
    }
}
~~~

`PurchaseOrderReader` ở đây là class thường được caller cung cấp `EntityManager` đúng phạm vi. Trong một ứng dụng thực tế có thể chuyển thành repository do CDI/Spring quản lý.

Lợi ích của tầng repository:

- Caller không cần nhớ tên query hoặc tham số chính xác.
- Có chỗ tập trung validation, phân trang và chuyển đổi kết quả.
- Tên query không bị rải khắp service/controller.
- Thay đổi cấu trúc query không bắt buộc ảnh hưởng API service.

**Đừng giữ một `EntityManager` dùng chung giữa nhiều thread**. Khi dùng container-managed EM hoặc dependency injection, làm theo vòng đời được framework hỗ trợ.

### 16.1. Hằng số tên truy vấn

Để tránh lỗi gõ chuỗi nhiều nơi, có thể khai báo hằng số:

~~~java
public final class OrderQueryNames {

    private OrderQueryNames() {
    }

    public static final String FIND_BY_CUSTOMER_AND_STATUS =
        "PurchaseOrder.findByCustomerAndStatus";

    public static final String COUNT_BY_STATUS =
        "PurchaseOrder.countByStatus";

    public static final String SUMMARY_BY_STATUS =
        "PurchaseOrder.summaryByStatus";
}
~~~

Khi dùng:

~~~java
em.createNamedQuery(
    OrderQueryNames.FIND_BY_CUSTOMER_AND_STATUS,
    PurchaseOrder.class
);
~~~

Điểm cần lưu ý: nếu dự án vừa dùng hằng số vừa hardcode tên trong annotation thì vẫn có thể lệch khi rename. Có thể dùng **compile-time constants** trực tiếp ở annotation nếu convention cho phép:

~~~java
@NamedQuery(
    name = OrderQueryNames.COUNT_BY_STATUS,
    query =
        "SELECT COUNT(o) FROM PurchaseOrder o " +
        "WHERE o.status = :status"
)
~~~

Java annotation yêu cầu giá trị là hằng biểu thức phù hợp. `public static final String` được gán literal như trên là một compile-time constant.

## 17. Named query trong Spring Data JPA

Spring Data JPA có thể hỗ trợ truy vấn có tên do JPA định nghĩa, bên cạnh cơ chế suy diễn truy vấn từ tên method và annotation `@Query` của Spring Data.

Ví dụ repository (giả sử cấu hình Spring Data JPA phù hợp):

~~~java
import com.example.shop.domain.OrderStatus;
import com.example.shop.domain.PurchaseOrder;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query(name = "PurchaseOrder.findByCustomerAndStatus")
    List<PurchaseOrder> findOrders(
        @Param("customerId") Long customerId,
        @Param("status") OrderStatus status
    );
}
~~~

`@Query` trong ví dụ là annotation **của Spring Data JPA**. `name` tham chiếu named query đã được JPA đăng ký, trong khi `@NamedQuery` ở entity là annotation thuộc **Jakarta Persistence**.

Ngoài cách chỉ định rõ, Spring Data còn có quy ước tìm named query theo tên entity/method trong cấu hình hỗ trợ. Nhưng để tránh phụ thuộc vào quy ước ngầm khi refactor, có thể chọn `@Query(name = "...")` theo thiết kế dự án.

Không nhầm:

~~~java
@Query("SELECT o FROM PurchaseOrder o WHERE ...")
~~~

với:

~~~java
@Query(name = "PurchaseOrder.findByCustomerAndStatus")
~~~

Dạng đầu khai báo nội dung JPQL ngay tại repository method; dạng sau tham chiếu một **named query đã đăng ký**.

### 17.1. Khi nào không cần named query trong Spring Data?

Nếu phương thức chỉ là:

~~~java
List<PurchaseOrder> findByStatus(OrderStatus status);
~~~

Spring Data có thể tự tạo truy vấn dựa trên method name. Với điều kiện ngắn và không cần query được dùng ngoài Spring Data, named query có thể là sự phức tạp không cần thiết.

Nên cân nhắc named query khi:

- Câu JPQL phức tạp nhưng cấu trúc ổn định.
- Nhiều consumer dùng cùng truy vấn.
- Dự án muốn tập trung query metadata ở entity/XML.
- Có JPQL projection hoặc join/fetch plan cần đặt tên rõ.

Không chọn named query chỉ vì “truy vấn nào cũng cần một @NamedQuery” — bản thân cơ chế này là tùy chọn kiến trúc.

## 18. Xử lý lỗi khi khai báo và gọi named query

### 18.1. Sai tên query

~~~java
em.createNamedQuery("PurchaseOrders.findByStatus");
~~~

Nếu tên thật là `PurchaseOrder.findByStatus`, việc tra cứu có thể ném `IllegalArgumentException` vì không tồn tại named query tương ứng.

Đối chiếu:

- Tên trên `@NamedQuery(name = "...")`.
- Tên truyền vào `createNamedQuery(...)`.
- Persistence unit có đăng ký entity chứa annotation không.
- Đã cấu hình đúng `orm.xml`/metadata chưa.

### 18.2. Sai tên entity hoặc attribute trong JPQL

Sai:

~~~java
@NamedQuery(
    name = "PurchaseOrder.badQuery",
    query =
        "SELECT o FROM purchase_orders o " +
        "WHERE o.order_code = :code"
)
~~~

Trong JPQL, nếu entity là `PurchaseOrder` và field là `orderCode`, dùng:

~~~java
@NamedQuery(
    name = "PurchaseOrder.findByCode",
    query =
        "SELECT o FROM PurchaseOrder o " +
        "WHERE o.orderCode = :code"
)
~~~

Provider có thể báo lỗi khi xử lý metadata lúc startup hoặc muộn hơn khi query được tạo/thực thi. **Không giả định mọi provider đều xác minh mọi named query từ startup theo một cách giống nhau**.

### 18.3. Quên binding parameter

~~~java
em.createNamedQuery(
        "PurchaseOrder.findByCustomerAndStatus",
        PurchaseOrder.class
    )
    .setParameter("customerId", 42L)
    // Quên :status.
    .getResultList();
~~~

Query có hai tham số yêu cầu nên cần binding đúng cả hai. Nếu thiếu, có thể xảy ra exception khi thực thi.

### 18.4. Binding sai tên hoặc sai kiểu

~~~java
// Tên không tồn tại trong JPQL:
query.setParameter("state", OrderStatus.DRAFT);

// Kiểu không tương thích với entity enum:
query.setParameter("status", 123);
~~~

Phải dùng đúng tên tham số đã khai báo và kiểu phù hợp với expression JPQL. Khi query chứa `o.status = :status` và `status` là enum, hãy binding `OrderStatus`.

### 18.5. Dùng resultClass không tương thích

~~~java
em.createNamedQuery(
    "PurchaseOrder.countByStatus",
    PurchaseOrder.class
);
~~~

`COUNT` cho ra `Long`, không phải entity `PurchaseOrder`. Dùng `Long.class`.

Tương tự, constructor expression `new OrderSummary(...)` phải dùng `OrderSummary.class` nếu cần typed query, không mặc định là class entity chứa annotation.

### 18.6. Duplicate query name

Hai định nghĩa `@NamedQuery` có cùng tên trong một persistence unit là xung đột metadata. Đặt convention tên và tránh khai báo nhiều bản sao ở những class/XML khác nhau.

### 18.7. NoResultException không phải lỗi cú pháp

Với `getSingleResult()`, không có bản ghi gây `NoResultException` là tình huống nghiệp vụ có thể dự kiến. Nó khác với lỗi cú pháp JPQL, thiếu tham số hoặc kết nối database. Phân biệt các nhóm lỗi để không ẩn bug cấu hình.

## 19. Quản lý thay đổi và refactor named queries

Named query tạo một hợp đồng giữa **tên**, **JPQL**, **tham số** và **kiểu kết quả**.

Ví dụ hợp đồng:

~~~text
Tên:       PurchaseOrder.findByCustomerAndStatus
Kết quả:   List<PurchaseOrder>
Tham số:   customerId: Long
           status: OrderStatus
Thứ tự:    createdAt DESC, id DESC
Điều kiện: customer.id = :customerId AND status = :status
~~~

Khi thay đổi từ `status` sang bộ trạng thái, cần cập nhật:

1. JPQL trong named query.
2. Tên và kiểu tham số.
3. Các chỗ gọi `setParameter`.
4. Repository/service method tương ứng.
5. Quy tắc xử lý kết quả và phân trang.

Nếu giữ tên cũ nhưng thay ngữ nghĩa theo cách không tương thích, các consumer có thể vô tình nhận kết quả khác kỳ vọng. Khi thay đổi mang tính breaking, có thể cân nhắc tạo named query mới với tên mới, sau đó chuyển caller có kiểm soát.

### 19.1. Named query không thay thế kiểm soát quyền

Ví dụ:

~~~jpql
SELECT o FROM PurchaseOrder o
WHERE o.customer.id = :customerId
~~~

Nếu `customerId` đến từ input client, kẻ gọi API có thể thử ID của người khác. Binding parameter **bảo vệ cấu trúc truy vấn khỏi input**, nhưng không tự kiểm tra **quyền truy cập dữ liệu**.

Service phải xác thực user hiện tại có quyền đọc `customerId`, hoặc bảo đảm query luôn lọc theo identity/tenant phù hợp từ security context.

Trong hệ thống đa tenant, có thể cần điều kiện:

~~~jpql
WHERE o.tenant.id = :tenantId
  AND o.customer.id = :customerId
~~~

`tenantId` phải được lấy từ context tin cậy; không coi input do client cung cấp là bằng chứng được phép đọc tenant đó.

### 19.2. Query name không phải hằng số SQL được database hiểu

Đổi tên `PurchaseOrder.findByStatus` không tác động trực tiếp tới schema. Database không biết tên named query; nó chỉ nhận SQL do provider tạo khi thực thi.

Named query cũng không tự đảm bảo:

- Có index cho mọi điều kiện lọc.
- Không xảy ra N+1.
- Query chỉ đọc dữ liệu được phép.
- Cache kết quả luôn chính xác.
- Truy vấn không làm tăng khóa hoặc contention.

Cần đánh giá những vấn đề này ở mapping, database, transaction và security.

## 20. Hiệu năng, query plan và caching

Một số người chọn named query vì nghĩ nó luôn nhanh hơn `createQuery(...)`. Cần hiểu rõ:

- Provider **có thể** phân tích/compile named JPQL và tái sử dụng metadata hoặc query plan.
- Dynamic JPQL cũng **có thể** được provider cache query plan theo cấu hình.
- Câu SQL cuối cùng vẫn cần database thực thi.
- Độ chọn lọc điều kiện, index, join, phân trang và cardinality thường ảnh hưởng nhiều tới hiệu năng.
- Result caching (nếu có) là cơ chế khác và phải được cấu hình/đánh giá riêng.

Ví dụ query:

~~~jpql
SELECT o FROM PurchaseOrder o
WHERE o.customer.id = :customerId
  AND o.status = :status
ORDER BY o.createdAt DESC, o.id DESC
~~~

Một index có thể cần cân nhắc:

~~~sql
CREATE INDEX idx_orders_customer_status_created
ON purchase_orders (
    customer_id,
    status,
    created_at,
    id
);
~~~

Đây là thiết kế minh họa, không phải khuyến nghị áp dụng nguyên xi cho mọi database. Cần xem SQL thực tế, query plan, kích thước bảng, thứ tự sort, phân phối dữ liệu và workload.

### 20.1. Hints trong named query

JPA có `@QueryHint` để khai báo các hint:

~~~java
@NamedQuery(
    name = "PurchaseOrder.findByStatusHinted",
    query =
        "SELECT o FROM PurchaseOrder o " +
        "WHERE o.status = :status",
    hints = {
        @QueryHint(
            name = "jakarta.persistence.query.timeout",
            value = "3000"
        )
    }
)
~~~

Ví dụ sử dụng tên hint theo Jakarta Persistence cho timeout (giá trị đơn vị mili giây theo quy ước của hint). **Support của từng hint có thể khác nhau giữa provider và database**, và một hint không được hỗ trợ có thể bị bỏ qua.

Không nên chỉ vì query được đặt tên mà thêm hàng loạt provider-specific hints khi chưa có phép đo hoặc yêu cầu vận hành cụ thể. Nếu runtime dùng JPA `javax.persistence` cũ, tên hint cũng cần đúng namespace tương ứng.

### 20.2. Truy vấn có tên không phải native prepared statement bất biến

Không giả định câu named JPQL được gửi nguyên xi tới database hay database giữ một prepared statement mãi cho mọi lần gọi. Provider còn phải biến JPQL thành SQL theo dialect, bind parameters, xử lý flush mode, lock mode và fetch plan.

Nếu cần xác minh hiệu năng, quan sát SQL/log/metrics thực tế thay vì suy luận từ việc sử dụng annotation.

## 21. Named query và vòng đời EntityManager

Ví dụ application-managed EntityManager với resource-local transaction:

~~~java
import com.example.shop.domain.OrderStatus;
import com.example.shop.domain.PurchaseOrder;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import java.util.List;

public class OrderLookup {

    private final EntityManagerFactory emf;

    public OrderLookup(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public List<PurchaseOrder> findConfirmed(Long customerId) {
        EntityManager em = emf.createEntityManager();

        try {
            return em.createNamedQuery(
                    "PurchaseOrder.findByCustomerAndStatus",
                    PurchaseOrder.class
                )
                .setParameter("customerId", customerId)
                .setParameter("status", OrderStatus.CONFIRMED)
                .getResultList();
        } finally {
            em.close();
        }
    }
}
~~~

Ví dụ có mục tiêu minh họa cách tạo query. Sau khi `em.close()`, các entity trả về trở thành **detached** nếu không còn context quản lý; các quan hệ LAZY chưa tải có thể không truy cập được trong cách sử dụng thông thường.

Nếu API cần trả dữ liệu qua HTTP, nên:

- Lấy DTO projection cần thiết trong transaction thích hợp, hoặc
- Tải fetch plan đúng yêu cầu rồi map sang DTO, hoặc
- Xây dựng tầng service với transaction boundary phù hợp.

Không dùng việc truy vấn có tên như một cách “giữ sống” persistence context. Named query không thay đổi quy tắc managed/detached/lazy loading.

### 21.1. Một EntityManager, nhiều lần gọi named query

~~~java
List<PurchaseOrder> drafts =
    em.createNamedQuery(
        "PurchaseOrder.findByCustomerAndStatus",
        PurchaseOrder.class
    )
    .setParameter("customerId", customerId)
    .setParameter("status", OrderStatus.DRAFT)
    .getResultList();

List<PurchaseOrder> confirmed =
    em.createNamedQuery(
        "PurchaseOrder.findByCustomerAndStatus",
        PurchaseOrder.class
    )
    .setParameter("customerId", customerId)
    .setParameter("status", OrderStatus.CONFIRMED)
    .getResultList();
~~~

Hai lần thực thi có thể nhận các managed entities từ **cùng persistence context**. JPA vẫn quản lý entity identity và có thể trả cùng managed instance nếu các kết quả trỏ đến cùng entity.

Điều này không có nghĩa danh sách kết quả query là cache bất biến hay `createNamedQuery` luôn bỏ qua database. Persistence context cache và query execution là các khái niệm khác nhau.

## 22. Named query với fetch join và N+1

Nếu query chỉ lấy đơn hàng:

~~~jpql
SELECT o FROM PurchaseOrder o
WHERE o.status = :status
~~~

rồi code lặp:

~~~java
for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getEmail());
}
~~~

khi `customer` là LAZY, provider có thể phát thêm SELECT cho những customer chưa có trong context, dẫn tới nhiều truy vấn.

Một named query dành cho màn hình cần customer:

~~~java
@NamedQuery(
    name = "PurchaseOrder.findByStatusWithCustomer",
    query =
        "SELECT o FROM PurchaseOrder o " +
        "JOIN FETCH o.customer " +
        "WHERE o.status = :status " +
        "ORDER BY o.id DESC"
)
~~~

Chọn query này khi chức năng thực sự cần quan hệ `customer`. Nó có thể giảm các truy vấn bổ sung, nhưng cũng làm query chính có join và lấy thêm dữ liệu.

**Không thêm `JOIN FETCH` vào mọi named query chỉ vì muốn “chống N+1”.** Fetch plan phải dựa trên data access thực tế. Với collection to-many và phân trang, vấn đề nhân dòng càng cần chú ý.

DTO projection có thể là lựa chọn khác khi chỉ cần vài trường từ customer.

## 23. Bài tập tình huống

### Bài 1. Tại sao tên phải duy nhất?

Hai entity cùng khai báo:

~~~java
@NamedQuery(name = "findAll", query = "SELECT c FROM Customer c")
~~~

và:

~~~java
@NamedQuery(name = "findAll", query = "SELECT o FROM PurchaseOrder o")
~~~

**Đáp án:** Named query có phạm vi persistence unit, không tự namespace theo class. Đặt tên `Customer.findAll` và `PurchaseOrder.findAll` để tránh collision.

### Bài 2. Chọn tên attribute trong JPQL

Entity:

~~~java
@Column(name = "order_code")
private String orderCode;
~~~

Có nên viết `WHERE o.order_code = :code` trong `@NamedQuery`?

**Đáp án:** Không nếu attribute Java là `orderCode`. JPQL dùng `o.orderCode`, còn `order_code` là cột SQL.

### Bài 3. Truy vấn hai trạng thái bằng một named query

~~~jpql
SELECT o FROM PurchaseOrder o
WHERE o.status = :status
~~~

**Câu hỏi:** Muốn lấy đơn DRAFT rồi CONFIRMED có cần hai khai báo không?

**Đáp án:** Không. Tạo hai query object hoặc thực thi cùng định nghĩa ở các lần gọi khác nhau, binding `OrderStatus.DRAFT` và `OrderStatus.CONFIRMED`.

### Bài 4. Tìm theo email không có kết quả

Named query:

~~~jpql
SELECT c FROM Customer c WHERE c.email = :email
~~~

Code gọi `getSingleResult()` nhưng không có customer.

**Đáp án:** Có thể xuất hiện `NoResultException`. Nếu nghiệp vụ cho phép không có customer, xử lý riêng trường hợp đó hoặc dùng `getResultList()`; đừng catch tất cả runtime exceptions rồi trả null.

### Bài 5. Đếm đơn nhưng dùng sai resultClass

~~~java
em.createNamedQuery(
    "PurchaseOrder.countByStatus",
    PurchaseOrder.class
);
~~~

**Đáp án:** Sai kiểu kết quả. Query `COUNT` trả `Long`, nên dùng `Long.class`.

### Bài 6. Đổi sort bằng parameter

Developer muốn:

~~~jpql
SELECT o FROM PurchaseOrder o ORDER BY :sortField
~~~

rồi binding `sortField = "createdAt"`.

**Đáp án:** Parameter biểu diễn **giá trị**, không thay thế tên thuộc tính JPQL. Dùng named query riêng cho các thứ tự được phép hoặc Criteria/dynamic query có whitelist.

### Bài 7. Phân trang khi nhiều đơn cùng createdAt

Named query chỉ dùng:

~~~jpql
ORDER BY o.createdAt DESC
~~~

**Đáp án:** Nhiều đơn có thể cùng timestamp nên thứ tự tie không xác định. Bổ sung `o.id DESC` giúp phân trang ổn định hơn. Với dữ liệu thay đổi đồng thời, offset pagination vẫn có thể chịu ảnh hưởng insert/delete giữa các request.

### Bài 8. Cần một DTO thay vì entity

Màn hình chỉ cần order code, customer email và total amount.

**Đáp án:** Khai báo named JPQL với `SELECT new ...OrderSummary(...)`, dùng `createNamedQuery(name, OrderSummary.class)`. Không cần tải đầy đủ entity graph nếu DTO đáp ứng yêu cầu.

### Bài 9. Query name giống nhau nhưng annotation ở hai file

Một truy vấn được khai báo trong Java annotation, truy vấn khác cùng tên ở `orm.xml`.

**Đáp án:** Phải kiểm tra quy tắc metadata override/collision của cấu hình JPA, không mặc định cả hai cùng tồn tại độc lập. Tránh trùng tên và xác định một nguồn khai báo có chủ đích.

### Bài 10. Bulk update dưới dạng named query

Named query chứa `UPDATE PurchaseOrder o SET o.status = :status ...`.

**Đáp án:** Thực thi bằng `executeUpdate()` trong transaction. Nó là bulk DML, không đồng bộ managed instances/callback như cập nhật từng entity thông thường; cần xem xét persistence context.

### Bài 11. Spring Data @Query khác JPA @NamedQuery

~~~java
@Query(name = "PurchaseOrder.findByCustomerAndStatus")
~~~

**Đáp án:** Đây là Spring Data annotation tham chiếu named query đã đăng ký. Còn `@NamedQuery` trên entity khai báo chính nội dung JPQL với tên đó.

### Bài 12. Named query có tự nhanh hơn không?

**Đáp án:** Không bảo đảm. Provider có thể cache query plan, nhưng hiệu năng chủ yếu phụ thuộc SQL được sinh, index, join, số dòng và workload. Cần quan sát SQL thực tế, không xem named query là kết quả cache sẵn.

### Bài 13. Binding enum

Một field `status` dùng `@Enumerated(EnumType.STRING)`. Truy vấn có `WHERE o.status = :status`.

**Đáp án:** Binding một giá trị `OrderStatus` trong JPQL là phù hợp. Không cần tự ghép chuỗi SQL `'CONFIRMED'` vào query.

### Bài 14. Query dùng để kiểm tra quyền theo customerId

Một API nhận `customerId` từ URL rồi thực thi named query tìm đơn hàng.

**Đáp án:** Binding tham số tránh ghép input vào câu JPQL nhưng **không tự kiểm tra quyền truy cập**. Service phải đối chiếu customerId với tài khoản được xác thực hoặc policy được tin cậy.

## 24. Khi nào nên chọn named query?

Một cách quyết định:

~~~text
         Có một truy vấn được dùng nhiều lần?
                       |
              +--------+--------+
              |                 |
             Có                Không
              |                 |
              v                 v
       Cấu trúc JPQL       Truy vấn đơn giản chỉ
         ổn định?          dùng một lần?
          /     \                 |
        Có      Không             v
         |         |         createQuery hoặc
         v         v         repository method
     @NamedQuery   Criteria /
     / XML         dynamic JPQL
         |
         v
    Đặt tên rõ, unique
    trong persistence unit
         |
         v
    Bind parameter + chọn
    TypedQuery đúng kết quả
         |
         v
    Phân trang / fetch plan /
    transaction phù hợp
~~~

Nên dùng named query khi:

- Câu truy vấn **ổn định về cấu trúc** và lặp lại ở nhiều nơi.
- Muốn quản lý JPQL tập trung, tránh sai khác điều kiện.
- Có nhiều tham số và một tên nghiệp vụ dễ hiểu.
- Cần khai báo projection hoặc fetch plan theo một use case cụ thể.
- Dự án đã có convention quản lý named queries bằng annotation/XML.

Cân nhắc giải pháp khác khi:

- Query chỉ là tìm theo ID: `EntityManager.find` hoặc repository `findById` thường đủ.
- Điều kiện lọc thay đổi linh hoạt: Criteria API hoặc query builder có thể rõ hơn.
- Phương thức Spring Data rất đơn giản và có thể suy diễn từ tên.
- Cần native SQL: `@NamedNativeQuery` phù hợp hơn.
- Cần nhiều thứ tự động không cố định: không thể thay cấu trúc `ORDER BY` bằng binding một parameter string.

## 25. Ghi nhớ

- **`@NamedQuery` khai báo một câu JPQL tĩnh với tên riêng**; `@NamedQueries` dùng khi khai báo nhiều câu trên cùng class.
- **Tên query là định danh trong phạm vi persistence unit**, không tự động được namespace theo entity chứa annotation. Dùng quy ước `EntityName.action` để tránh xung đột.
- **`EntityManager.createNamedQuery(name, ResultClass.class)`** tạo typed query; `setParameter` truyền dữ liệu ở từng lần gọi.
- **JPQL dùng tên entity và thuộc tính Java**, không dùng trực tiếp tên bảng/cột SQL.
- **Named query không chạy khi chỉ được khai báo**; thực thi xảy ra khi gọi `getResultList`, `getSingleResult` hoặc `executeUpdate` theo loại query.
- **Kiểu kết quả phải khớp**: entity, `Long` cho COUNT, hoặc DTO class cho `SELECT new ...`.
- **Phân trang và hint** có thể đặt trên query object khi thực thi; chú ý ORDER BY ổn định và fetch join to-many.
- **@NamedQuery khác @NamedNativeQuery**: một bên JPQL, một bên SQL native.
- **Named query không tự giải quyết N+1, caching, security hay transaction**. Những yêu cầu đó cần fetch plan, chỉ mục, policy và transaction boundary phù hợp.
- **Bulk UPDATE/DELETE named queries** vẫn có các giới hạn của JPQL bulk DML đối với managed entities, callbacks và cascade.

Cốt lõi: **đặt tên cho một cấu trúc JPQL ổn định để các nơi trong ứng dụng dùng chung đúng một định nghĩa, còn giá trị tham số, phân trang và thời điểm thực thi được quyết định ở mỗi lần gọi**. Thiết kế tốt không chỉ là có `@NamedQuery`, mà còn là chọn tên rõ nghĩa, giữ metadata nhất quán, và dùng typed query trong một tầng truy cập dữ liệu có trách nhiệm.
