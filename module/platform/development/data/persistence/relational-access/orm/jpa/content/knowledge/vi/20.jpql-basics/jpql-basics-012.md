# Áp dụng query hint và kiểm tra khả năng hỗ trợ trong JPQL

Khi viết truy vấn bằng Java Persistence API (JPA), phần lớn ứng dụng bắt đầu với JPQL và các tham số:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery(
        "SELECT o FROM PurchaseOrder o " +
        "WHERE o.status = :status ORDER BY o.createdAt DESC",
        PurchaseOrder.class
    )
    .setParameter("status", OrderStatus.PAID)
    .getResultList();
~~~

Truy vấn trên mô tả **dữ liệu muốn lấy**, nhưng chưa nêu rõ một số yêu cầu vận hành: truy vấn nên giới hạn thời gian bao lâu, có cần khóa bản ghi không, có muốn tác động đến cache hay không, hoặc cần tải trước association nào để tránh những truy vấn phụ. JPA cho phép truyền các **query hint** để hướng dẫn provider trong những vấn đề như vậy.

Ví dụ, muốn yêu cầu thời gian truy vấn tối đa khoảng ba giây:

~~~java
TypedQuery<PurchaseOrder> query = entityManager.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.status = :status",
    PurchaseOrder.class
);

query.setParameter("status", OrderStatus.PAID);
query.setHint("jakarta.persistence.query.timeout", 3000);

List<PurchaseOrder> orders = query.getResultList();
~~~

Điểm khó nằm ở cụm từ **“yêu cầu”**: hint không phải một mệnh lệnh SQL bảo đảm mọi provider và database đều xử lý giống hệt nhau. Một số hint thuộc chuẩn Jakarta Persistence; một số chỉ có trong Hibernate, EclipseLink hoặc provider khác. Những hint không được nhận diện thường có thể bị bỏ qua, và kể cả hint chuẩn cũng có thể bị giới hạn bởi khả năng của driver và database.

Bài học này giải thích cách áp dụng hint trong JPQL, lựa chọn đúng hint, phân biệt hint chuẩn và hint riêng provider, đồng thời **kiểm tra khả năng hỗ trợ bằng tài liệu, API và quan sát thực tế** thay vì chỉ dựa vào việc `setHint()` không ném exception.

## 1. Query hint nằm ở đâu trong vòng đời truy vấn JPA?

Một truy vấn JPA có thể được mô tả qua ba tầng:

~~~text
          ỨNG DỤNG
              |
              | JPQL:
              | SELECT o FROM PurchaseOrder o
              | WHERE o.status = :status
              |
              | Parameters:
              | status = PAID
              |
              | Hints:
              | query.timeout = 3000
              | fetchgraph = ...
              v
       JPA PROVIDER
       (Hibernate, EclipseLink, ...)
              |
              | Dịch JPQL thành SQL
              | Tạo kế hoạch nạp entity
              | Cấu hình JDBC statement/cache/locking
              v
       JDBC + DATABASE
              |
              | SQL, index, lock, timeout
              v
          KẾT QUẢ
~~~

**JPQL** mô tả đối tượng và điều kiện dữ liệu muốn truy vấn. **Query hint** cung cấp thông tin phụ để provider quyết định cách thực hiện truy vấn, trong giới hạn được hỗ trợ.

Ví dụ:

~~~java
TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.customer.id = :customerId",
    PurchaseOrder.class
);

query.setParameter("customerId", customerId);
query.setMaxResults(50);
query.setHint("jakarta.persistence.query.timeout", 3000);
~~~

Trong đó:

- `setParameter(...)` cung cấp giá trị điều kiện JPQL.
- `setMaxResults(50)` là **API phân trang/giới hạn kết quả chuẩn**, không phải query hint.
- `setHint(...)` truyền một hint kèm giá trị cho provider.
- `getResultList()` mới là một trong những thao tác thực thi truy vấn.
- EntityManager/persistence context quản lý các entity trả về theo quy tắc JPA.
- Giao dịch, isolation, flush mode và locking có ảnh hưởng riêng, không được thay thế hoàn toàn bằng hint.

### 1.1. Hint khác điều kiện WHERE

Một lỗi tư duy:

> “Tôi đặt hint timeout nên truy vấn sẽ không phải tối ưu SQL.”

Sai. Hint timeout không thay thế việc thiết kế `WHERE`, chỉ mục, giới hạn kết quả hoặc quan hệ. Nếu truy vấn đọc hàng triệu hàng vì thiếu điều kiện, timeout chỉ có thể khiến ứng dụng phát hiện vấn đề sớm hơn trong một số môi trường; nó không làm truy vấn hiệu quả.

### 1.2. Hint khác query parameter

Tham số JPQL:

~~~java
query.setParameter("status", OrderStatus.PAID);
~~~

được dùng để bind dữ liệu vào biểu thức `:status`. Hint:

~~~java
query.setHint("jakarta.persistence.query.timeout", 3000);
~~~

không phải tham số trong `WHERE`; nó hướng dẫn provider thực thi. Đặt tên hint giống tên parameter cũng không khiến JPA bind tham số.

### 1.3. Hint khác các option chuẩn chuyên dụng

Không phải mọi lựa chọn cấu hình truy vấn đều nên đưa vào `setHint`.

| Nhu cầu | API JPA nên xem trước |
|---|---|
| Đặt tham số | `setParameter(...)` |
| Giới hạn số bản ghi | `setMaxResults(...)` |
| Bỏ qua các bản ghi đầu | `setFirstResult(...)` |
| Yêu cầu lock mode | `setLockMode(...)` |
| Đặt flush mode riêng cho query | `setFlushMode(...)` |
| Yêu cầu provider timeout | `setHint("jakarta.persistence.query.timeout", ...)` |
| Hướng dẫn cache | Các hint `jakarta.persistence.cache.*` phù hợp |
| Hướng dẫn fetch graph | `jakarta.persistence.fetchgraph` / `loadgraph` |
| Hướng dẫn fetch size hoặc query-result cache riêng Hibernate | Hint/option do Hibernate cung cấp |

Hãy ưu tiên API chuẩn chuyên dụng khi nó đã tồn tại. Query hint là cơ chế mở rộng, không phải cách thay mọi option của Query.

## 2. Cơ chế `Query.setHint(...)` và `TypedQuery.setHint(...)`

JPA có các giao diện:

~~~java
jakarta.persistence.Query
jakarta.persistence.TypedQuery<T>
~~~

Cả hai hỗ trợ việc đặt hint. Ví dụ:

~~~java
Query query = em.createQuery(
    "SELECT o.id FROM PurchaseOrder o"
);

query.setHint("jakarta.persistence.query.timeout", 2500);
~~~

Hoặc truy vấn có kiểu kết quả:

~~~java
TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
);

query.setHint("jakarta.persistence.query.timeout", 2500);
~~~

Phương thức `setHint` nhận:

~~~java
query.setHint(String hintName, Object value);
~~~

**Tên hint** thường là chuỗi namespace có dấu chấm; **giá trị** có thể là Integer, enum, EntityGraph hoặc kiểu do provider quy định.

Cần phân biệt:

~~~java
// Giá trị number (Integer), dạng API runtime:
query.setHint("jakarta.persistence.query.timeout", 2500);
~~~

với annotation `@QueryHint`, nơi `value` là **String**:

~~~java
@QueryHint(
    name = "jakarta.persistence.query.timeout",
    value = "2500"
)
~~~

Không được giả định mọi hint đều nhận một chuỗi bất kỳ hay mọi provider tự convert mọi kiểu giống nhau.

### 2.1. `setHint` trả về chính Query để chain

~~~java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o " +
        "WHERE o.status = :status",
        PurchaseOrder.class
    )
    .setParameter("status", OrderStatus.PAID)
    .setHint("jakarta.persistence.query.timeout", 3000)
    .setMaxResults(100)
    .getResultList();
~~~

Cách viết chain tiện cho ví dụ ngắn. Với truy vấn có nhiều tùy chọn, nên tách biến `TypedQuery` và giải thích tên hằng để dễ quan sát và gỡ lỗi.

### 2.2. Hint chỉ có hiệu lực trên truy vấn được cấu hình

~~~java
TypedQuery<PurchaseOrder> first = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
);
first.setHint("jakarta.persistence.query.timeout", 1000);

TypedQuery<PurchaseOrder> second = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
);
~~~

Không mặc định rằng `second` cũng có timeout 1000 ms chỉ vì `first` đã đặt hint. Hai đối tượng Query riêng có cấu hình riêng, trừ khi provider hoặc môi trường cấu hình mặc định tương ứng.

### 2.3. Thời điểm cấu hình

Nên đặt tất cả tham số, giới hạn và hint **trước** lời gọi thực thi như:

~~~java
getResultList()
getSingleResult()
getResultStream()
executeUpdate()
~~~

Đừng trông đợi thay hint sau khi đã lấy kết quả sẽ hồi tố thay đổi SQL vừa chạy. Nếu muốn thực thi lại query với cấu hình khác, dùng Query thích hợp và cân nhắc tác động tới persistence context.

## 3. Phân biệt hint chuẩn với hint riêng provider

### 3.1. Nhóm hint chuẩn Jakarta Persistence

Tùy phiên bản Jakarta Persistence, các hint chuẩn thường gặp gồm:

| Hint | Mục đích | Giá trị điển hình |
|---|---|---|
| `jakarta.persistence.query.timeout` | Yêu cầu giới hạn thời gian chạy truy vấn | Integer, đơn vị mili-giây |
| `jakarta.persistence.lock.timeout` | Yêu cầu timeout khi chờ pessimistic lock | Integer, đơn vị mili-giây |
| `jakarta.persistence.cache.retrieveMode` | Điều chỉnh việc đọc entity từ second-level cache | `CacheRetrieveMode` |
| `jakarta.persistence.cache.storeMode` | Điều chỉnh việc lưu/refresh cache | `CacheStoreMode` |
| `jakarta.persistence.fetchgraph` | Áp dụng entity graph theo ngữ nghĩa fetch graph | `EntityGraph<?>` |
| `jakarta.persistence.loadgraph` | Áp dụng entity graph theo ngữ nghĩa load graph | `EntityGraph<?>` |
| `jakarta.persistence.lock.scope` | Yêu cầu phạm vi pessimistic lock | `PessimisticLockScope` |

Các hint này thuộc namespace `jakarta.persistence`. Dự án dùng JPA cũ có thể gặp namespace `javax.persistence`; **không tự trộn hai namespace** khi ứng dụng đã chuyển sang Jakarta Persistence.

### 3.2. Nhóm hint chỉ có ở provider

Ví dụ các nhu cầu như:

- Đặt fetch size cụ thể ở JDBC.
- Cấu hình truy vấn có được cache kết quả hay không.
- Đánh dấu entity của query là read-only theo cơ chế riêng.
- Gắn comment vào SQL để phục vụ tracing.
- Chọn một số cơ chế batch fetching riêng provider.
- Truyền SQL optimizer hint đặc thù database.

Những khả năng này không nhất thiết thuộc API JPA portable. Nếu đang dùng Hibernate, nên ưu tiên constants mà Hibernate cung cấp, thay vì ghi nhớ những chuỗi có thể thay đổi qua phiên bản.

Ví dụ với một phiên bản Hibernate hỗ trợ các constants tương ứng:

~~~java
import org.hibernate.jpa.HibernateHints;

TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
);

query.setHint(HibernateHints.HINT_READ_ONLY, true);
query.setHint(HibernateHints.HINT_FETCH_SIZE, 200);
~~~

Đây là **code phụ thuộc Hibernate**, không phải JPA portable. Nếu đổi provider, constants trên không còn dùng được và hành vi có thể khác.

### 3.3. Không đoán hint từ tên

Một chuỗi trông hợp lý:

~~~java
query.setHint("myapp.database.fastQuery", true);
~~~

không làm database chạy nhanh hơn nếu không có thành phần nào hiểu nó. Một provider có thể bỏ qua hint không được nhận diện mà không báo lỗi.

Tương tự, cùng một ý tưởng như “cache kết quả truy vấn” có thể cần cơ chế riêng của Hibernate hoặc EclipseLink; không tự tạo tên `jakarta.persistence.query.cacheable` rồi coi là chuẩn.

## 4. Ví dụ entity để áp dụng các hint

Giả sử ứng dụng quản lý đơn hàng, khách hàng và dòng hàng. Các entity được rút gọn chỉ để tập trung vào JPQL/hint.

### 4.1. Customer

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

    @Column(nullable = false, length = 150)
    private String name;

    protected Customer() {}

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

### 4.2. OrderStatus

~~~java
package com.example.shop.domain;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

### 4.3. PurchaseOrder

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
import jakarta.persistence.OneToMany;
import jakarta.persistence.OrderBy;
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

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status = OrderStatus.NEW;

    @Column(name = "total_amount", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    @OrderBy("id ASC")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
~~~

### 4.4. OrderLine

~~~java
package com.example.shop.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    private int quantity;

    protected OrderLine() {}
}
~~~

Trong bài:

- `PurchaseOrder.customer` là to-one LAZY.
- `PurchaseOrder.lines` là one-to-many LAZY.
- `@Version` giúp optimistic locking khi cập nhật entity.
- Các ví dụ query đọc danh sách Order có thể không cần nạp Customer/Line.
- Khi cần thông tin liên quan, entity graph hoặc JPQL fetch join là những lựa chọn cần so sánh.

Các ví dụ này minh họa mapping; ứng dụng thực tế cần constructor, invariant và schema/migration phù hợp.

## 5. Hint chuẩn `jakarta.persistence.query.timeout`

Timeout là một trong những hint dễ hiểu nhất nhưng cũng dễ bị diễn giải quá mức.

### 5.1. Đặt timeout khi chạy JPQL

~~~java
TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.status = :status " +
    "ORDER BY o.createdAt DESC",
    PurchaseOrder.class
);

query.setParameter("status", OrderStatus.PAID);
query.setHint("jakarta.persistence.query.timeout", 3000);

List<PurchaseOrder> orders = query.getResultList();
~~~

Giá trị `3000` có nghĩa **ba nghìn mili-giây** theo ngữ nghĩa của hint. Nhưng không có bảo đảm tuyệt đối rằng query sẽ dừng chính xác tại giây thứ ba.

### 5.2. Vì sao timeout là “yêu cầu” chứ không phải timer chính xác?

Việc thực thi phụ thuộc:

- JPA provider có nhận diện và áp dụng hint không?
- Provider có truyền timeout vào JDBC `Statement` không?
- JDBC driver và database có hỗ trợ hủy query đang chạy không?
- Driver có làm tròn timeout sang đơn vị giây không?
- Query đang chờ khóa, chạy SQL, chuyển dữ liệu mạng hay materialize object?
- Timeout bị kiểm tra tại database, driver hay framework ở tầng khác?

Ví dụ một provider có thể chuyển 3000 ms thành `Statement.setQueryTimeout(3)`, trong khi JDBC query timeout thường biểu diễn bằng giây. Đó là một khả năng triển khai; **không phải mọi provider đều dùng đúng phương thức hay quy tắc làm tròn này**.

### 5.3. Exception nào có thể xuất hiện?

Nếu query timeout được thực thi và vi phạm:

- `QueryTimeoutException` có thể biểu thị tình huống statement bị timeout nhưng transaction không bị đánh dấu rollback toàn bộ theo phân loại JPA.
- Một `PersistenceException` khác có thể được ném nếu thất bại ảnh hưởng tới transaction hoặc provider/driver bọc lỗi theo cách khác.
- Một số môi trường có thể ném exception vendor-specific được framework dịch sang loại khác.

Không viết logic chỉ bắt đúng một exception rồi kết luận mọi timeout đều như vậy. Sau lỗi, cần xác định transaction còn dùng được hay đã rollback-only trước khi tiếp tục.

### 5.4. Không dùng timeout để sửa SQL kém

Một query đọc hàng triệu entity không có điều kiện:

~~~java
SELECT o FROM PurchaseOrder o
~~~

có thể chậm do thiếu index, join lớn, offset sâu hoặc tải association. `query.timeout` có thể là hàng rào vận hành, nhưng cách sửa gốc là thiết kế truy vấn, phân trang, projection và index phù hợp.

### 5.5. Timeout khác thời gian toàn bộ HTTP request

Nếu request còn thực hiện:

1. Xác thực và xử lý input.
2. Chờ lấy connection từ pool.
3. Thực thi query.
4. Chuyển đổi entity thành DTO.
5. Gọi API bên ngoài.
6. Serialize JSON.

thì `jakarta.persistence.query.timeout` **không tự bảo đảm toàn bộ request kết thúc trong ba giây**. Để quản lý SLA cho API cần kết hợp timeout ở transaction, pool, HTTP và các dependency, không chỉ hint JPA.

## 6. Hint chuẩn `jakarta.persistence.lock.timeout`

Query timeout giới hạn thời gian thực thi truy vấn theo khả năng provider/driver. **Lock timeout** điều chỉnh thời gian chờ khóa trong các tình huống pessimistic locking.

### 6.1. Dùng với `setLockMode(...)`

~~~java
import jakarta.persistence.LockModeType;

TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o WHERE o.id = :id",
    PurchaseOrder.class
);

query.setParameter("id", orderId);
query.setLockMode(LockModeType.PESSIMISTIC_WRITE);
query.setHint("jakarta.persistence.lock.timeout", 500);

PurchaseOrder order = query.getSingleResult();
~~~

Ý nghĩa mong muốn:

- JPA yêu cầu lock pessimistic trên entity được chọn.
- Hint `lock.timeout` cung cấp khoảng chờ lock mong muốn 500 ms.
- Database/provider phải hỗ trợ cơ chế chờ/không chờ phù hợp thì mới có thể áp dụng chính xác.
- Lời gọi cần một transaction phù hợp cho pessimistic locking.

### 6.2. Lock timeout không biến query thường thành query khóa

Đây là cấu hình thiếu ý nghĩa nếu kỳ vọng nó tự khóa row:

~~~java
TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
);

query.setHint("jakarta.persistence.lock.timeout", 500);
// Không gọi setLockMode(...).
~~~

Chỉ riêng hint lock timeout **không phải lệnh yêu cầu pessimistic lock**. Cần đặt `LockModeType` phù hợp cho operation thực sự có khóa.

### 6.3. Lock timeout có thể không được thực thi ở từng mức millisecond

Một số database chỉ hỗ trợ NOWAIT, WAIT với đơn vị hạn chế hoặc cơ chế session/statement khác. Có provider không hỗ trợ một giá trị timeout cụ thể. Vì vậy:

- `500` không được diễn giải là “chắc chắn thất bại sau đúng 0,5 giây”.
- `0` thường được dùng như yêu cầu không chờ khi cơ chế được hỗ trợ, nhưng không bảo đảm portable trên mọi DB/provider.
- Không dùng hint lock timeout làm phương tiện duy nhất để bảo đảm deadline toàn transaction.
- Kiểm chứng bằng test có hai transaction thực sự tranh chấp cùng một row.

### 6.4. Phân biệt hai exception về lock

JPA có những exception liên quan pessimistic locking:

- `LockTimeoutException`: trong tình huống lock timeout theo phân loại của JPA mà chỉ statement bị rollback, không toàn bộ transaction.
- `PessimisticLockException`: khi lỗi pessimistic locking khiến transaction bị đánh dấu rollback theo phân loại JPA.

Provider và DB có thể trả về lỗi với mức ảnh hưởng khác nhau. Khi bắt lỗi, phải xem transaction status, cách framework dịch exception và quy định retry; không tiếp tục dùng transaction đã hỏng như thể chưa có gì xảy ra.

### 6.5. Lock timeout khác optimistic locking

`@Version`/`LockModeType.OPTIMISTIC` dùng optimistic locking, phát hiện xung đột khi cập nhật/kiểm tra phiên bản. Lock timeout đặc biệt liên quan tới thời gian chờ **pessimistic lock**, không làm optimistic locking nhanh hay chậm theo cùng cách.

Nếu nghiệp vụ có tranh chấp cao, cần chọn chiến lược concurrency dựa trên workload: optimistic locking, pessimistic locking, update có điều kiện hoặc isolation phù hợp.

## 7. Cache hints: `cache.retrieveMode` và `cache.storeMode`

JPA có cơ chế second-level cache tùy cấu hình provider và entity. Hai hint chuẩn giúp điều chỉnh cách provider tương tác với cache.

### 7.1. CacheRetrieveMode

~~~java
import jakarta.persistence.CacheRetrieveMode;

query.setHint(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);
~~~

Ý nghĩa theo ngữ nghĩa cache retrieve mode: yêu cầu **bỏ qua việc lấy trạng thái entity từ second-level cache** trong những operation có áp dụng hint này, thay vì đọc từ cache như bình thường.

Các giá trị:

- `CacheRetrieveMode.USE`: có thể sử dụng cache.
- `CacheRetrieveMode.BYPASS`: bỏ qua việc truy xuất dữ liệu từ cache.

Không hiểu `BYPASS` là “bỏ qua mọi cache của máy chủ”, vì **first-level cache/persistence context vẫn có quy tắc identity và managed state riêng**.

### 7.2. CacheStoreMode

~~~java
import jakarta.persistence.CacheStoreMode;

query.setHint(
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.REFRESH
);
~~~

Các giá trị chuẩn:

| CacheStoreMode | Ý nghĩa chung |
|---|---|
| `USE` | Cho phép sử dụng hành vi lưu cache bình thường |
| `BYPASS` | Bỏ qua việc lưu cache theo ngữ nghĩa store mode |
| `REFRESH` | Yêu cầu refresh trạng thái cache từ nguồn dữ liệu theo cơ chế được hỗ trợ |

Hành vi cụ thể còn phụ thuộc entity có được cache, cách provider quản lý second-level cache và các quy tắc của JPA.

### 7.3. Ví dụ query không muốn dùng second-level cache

~~~java
TypedQuery<Customer> query = em.createQuery(
    "SELECT c FROM Customer c WHERE c.id = :id",
    Customer.class
);

query.setParameter("id", customerId);

query.setHint(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);

List<Customer> customers = query.getResultList();
~~~

Không suy ra rằng query này chắc chắn tạo một `SELECT` mới cho mọi lần gọi: first-level cache có thể đã chứa Customer và các quy tắc trả managed entity vẫn có hiệu lực. Ngoài ra, chính JPQL query thường chạy SQL để xác định tập kết quả, trong khi **second-level entity cache** ảnh hưởng tới việc tải trạng thái entity; hai phần này không giống nhau.

### 7.4. Second-level cache khác query-result cache

Đây là nhầm lẫn quan trọng.

**Second-level entity cache** lưu trạng thái entity theo identity theo cấu hình. **Query-result cache** có thể lưu danh sách ID/kết quả của một câu truy vấn, nhưng cơ chế query-result cache thường là tính năng riêng provider.

Ví dụ Hibernate:

~~~java
import org.hibernate.jpa.HibernateHints;

TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.status = :status",
    PurchaseOrder.class
);

query.setParameter("status", OrderStatus.PAID);
query.setHint(HibernateHints.HINT_CACHEABLE, true);
~~~

Đây là **Hibernate-specific hint**. Nó không trở thành chuẩn JPA chỉ vì gọi qua `TypedQuery.setHint()`.

Muốn query-result cache thực sự có tác dụng, còn cần cấu hình query cache, cache region, invalidation và khả năng hỗ trợ tương ứng của Hibernate. Đặt `HINT_CACHEABLE = true` mà không bật hệ thống cache cần thiết không bảo đảm query sẽ hit cache.

### 7.5. Cache không phải giải pháp trực tiếp cho stale entity trong context

Nếu `Customer` đã managed và code dùng JDBC/native SQL sửa row tương ứng ngoài JPA, đặt cache.retrieveMode BYPASS lên một query không tự cập nhật mọi field đã nằm trong managed entity.

Có thể cần:

~~~java
em.refresh(customer);
~~~

hoặc quy trình `clear()/reload` phù hợp sau khi đồng bộ pending changes. `clear()` có thể làm mất những thay đổi chưa flush; phải dùng có chủ đích.

## 8. Entity graph hints: `fetchgraph` và `loadgraph`

Một vấn đề JPQL phổ biến là N+1 queries.

Ví dụ application tải 100 PurchaseOrder, rồi trong vòng lặp truy cập Customer và Lines:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();

for (PurchaseOrder order : orders) {
    // Những association LAZY có thể kích hoạt SQL bổ sung.
    System.out.println(order.getStatus());
}
~~~

Khi màn hình cần thêm Customer, ta có thể dùng **entity graph** để hướng dẫn kế hoạch tải dữ liệu mà không nhất thiết viết một câu JPQL fetch join cho mọi trường hợp.

### 8.1. Tạo graph động

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");
~~~

Sử dụng trong query:

~~~java
TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.status = :status",
    PurchaseOrder.class
);

query.setParameter("status", OrderStatus.PAID);
query.setHint("jakarta.persistence.fetchgraph", graph);

List<PurchaseOrder> orders = query.getResultList();
~~~

Hint `fetchgraph` nhận một `EntityGraph` object; không phải tên chuỗi bất kỳ trừ những overload/API khác được thiết kế cho named entity graph.

### 8.2. Semantics của fetch graph

Với `fetchgraph`, những thuộc tính được chỉ định trong graph được xem là cần fetch; các thuộc tính **không được liệt kê** được xử lý theo ngữ nghĩa LAZY của fetch graph, trong giới hạn provider và quy tắc đặc tả. Provider có thể tải nhiều trạng thái hơn mức tối thiểu.

Không nên khẳng định:

> “fetchgraph sẽ luôn chỉ chạy một câu SQL JOIN.”

Sai. Entity graph nói về **fetch plan**, không cam kết một hình dạng SQL duy nhất. Provider có thể dùng join, query bổ sung, batch fetching hoặc kỹ thuật khác.

### 8.3. Semantics của load graph

~~~java
query.setHint("jakarta.persistence.loadgraph", graph);
~~~

Với `loadgraph`:

- Những thuộc tính trong graph được yêu cầu tải.
- Những thuộc tính không có trong graph giữ ngữ nghĩa fetch mặc định từ mapping.
- Nếu entity có to-one được mapping EAGER mà không được đưa vào graph, load graph vẫn giữ mặc định của mapping cho thuộc tính đó.

Bảng so sánh khái niệm:

| Khía cạnh | `fetchgraph` | `loadgraph` |
|---|---|---|
| Thuộc tính có trong graph | Được yêu cầu fetch | Được yêu cầu fetch |
| Thuộc tính không có trong graph | Theo ngữ nghĩa LAZY của fetch graph | Theo mapping fetch mặc định |
| Bảo đảm chỉ một SQL? | Không | Không |
| Bảo đảm không có N+1 trong mọi use case? | Không | Không |
| Có thể dùng qua `Query.setHint(...)`? | Có | Có |

Provider được phép tải thêm dữ liệu ngoài yêu cầu tối thiểu nên không dùng entity graph như một cơ chế bảo mật để che field nhạy cảm. Để giới hạn dữ liệu trả API, dùng DTO/projection và kiểm soát serialization rõ ràng.

### 8.4. Graph có subgraph

Nếu `PurchaseOrder.customer` có association `address` và màn hình cần cả hai:

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

Subgraph<Customer> customerGraph =
    graph.addSubgraph("customer");

customerGraph.addAttributeNodes("address");
~~~

Ví dụ giả định entity Customer có thuộc tính mapped tên `address`. Subgraph cho phép mô tả nhu cầu nạp sâu hơn mà không cần đưa toàn bộ object graph vào mọi query.

### 8.5. NamedEntityGraph

Có thể khai báo graph tại entity:

~~~java
@NamedEntityGraph(
    name = "PurchaseOrder.withCustomer",
    attributeNodes = @NamedAttributeNode("customer")
)
@Entity
public class PurchaseOrder {
    // ...
}
~~~

Rồi lấy trong runtime:

~~~java
EntityGraph<?> graph =
    em.getEntityGraph("PurchaseOrder.withCustomer");

TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
);

query.setHint("jakarta.persistence.loadgraph", graph);
~~~

Đây là phương án khi cùng một fetch plan được tái sử dụng ở nhiều query.

### 8.6. Khi nào ưu tiên JPQL fetch join thay cho graph?

Ví dụ:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "JOIN FETCH o.customer " +
    "WHERE o.status = :status",
    PurchaseOrder.class
)
.setParameter("status", OrderStatus.PAID)
.getResultList();
~~~

`JOIN FETCH` mô tả fetch trực tiếp trong JPQL; entity graph mô tả fetch plan riêng bên ngoài query.

Cân nhắc:

- Nếu query luôn cần một quan hệ cụ thể, JPQL fetch join có thể rõ ràng.
- Nếu muốn tái sử dụng cùng query với nhiều fetch plan, entity graph tiện hơn.
- Với collection to-many lớn, cả fetch join và entity graph đều có thể dẫn đến nhiều hàng SQL, dữ liệu trùng và khó phân trang.
- Nếu màn hình chỉ cần vài field, DTO projection thường tiết kiệm dữ liệu hơn nạp toàn bộ entity + graph.

## 9. `@NamedQuery` kết hợp `@QueryHint`

Ngoài `setHint` ở runtime, JPA cho phép cấu hình hint trong named query.

### 9.1. Khai báo named JPQL query

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.NamedQuery;
import jakarta.persistence.QueryHint;

@Entity
@NamedQuery(
    name = "PurchaseOrder.findPaid",
    query = "SELECT o FROM PurchaseOrder o " +
            "WHERE o.status = :status " +
            "ORDER BY o.createdAt DESC",
    hints = {
        @QueryHint(
            name = "jakarta.persistence.query.timeout",
            value = "3000"
        )
    }
)
public class PurchaseOrder {
    // ...
}
~~~

**Lưu ý:** ví dụ trên chỉ thể hiện những annotation liên quan; trong code dự án, class vẫn cần `@Id` và các field như ví dụ entity đầy đủ ở phần trước.

### 9.2. Thực thi named query

~~~java
TypedQuery<PurchaseOrder> query =
    em.createNamedQuery(
        "PurchaseOrder.findPaid",
        PurchaseOrder.class
    );

query.setParameter("status", OrderStatus.PAID);
List<PurchaseOrder> orders = query.getResultList();
~~~

Tên `PurchaseOrder.findPaid` là tên query JPA đã đăng ký, không phải SQL function và không phải tên bảng.

### 9.3. Tại sao value trong annotation là String?

`@QueryHint` là annotation, và thuộc tính `value` được khai báo là `String`. Vì vậy:

~~~java
@QueryHint(
    name = "jakarta.persistence.query.timeout",
    value = "3000"
)
~~~

là cú pháp đúng ở metadata. Ở runtime API, giá trị tương ứng thường dùng Integer:

~~~java
query.setHint("jakarta.persistence.query.timeout", 3000);
~~~

Provider chịu trách nhiệm đọc annotation và chuyển đổi giá trị phù hợp với hint mà nó hiểu. Nếu giá trị không hợp lệ hoặc provider không hỗ trợ, behavior phụ thuộc contract/implementation; phải kiểm tra thay vì giả định mọi chuỗi đều được chấp nhận.

### 9.4. NamedQuery với hint riêng provider

Có thể khai báo:

~~~java
@NamedQuery(
    name = "PurchaseOrder.activeWithReadHint",
    query = "SELECT o FROM PurchaseOrder o " +
            "WHERE o.status <> :cancelled",
    hints = {
        @QueryHint(
            name = "org.hibernate.readOnly",
            value = "true"
        )
    }
)
~~~

Đây là minh họa **hint riêng Hibernate**; tên hint chính xác phải được đối chiếu với constants và tài liệu Hibernate của phiên bản dự án. Không được dùng một chuỗi riêng provider rồi coi đó là cấu hình chuẩn mọi JPA implementation.

Khi có khả năng dùng code runtime, dùng constant do provider cung cấp thường giúp tránh sai tên hơn. Trong annotation Java, `@QueryHint.name` là String constant expression nên có thể dùng constant phù hợp nếu được khai báo là compile-time constant.

## 10. Query hint trong Spring Data JPA repository

Spring Data JPA có annotation `@QueryHints` để truyền JPA `@QueryHint` vào query do repository quản lý.

Ví dụ:

~~~java
import jakarta.persistence.QueryHint;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query(
        "SELECT o FROM PurchaseOrder o " +
        "WHERE o.status = :status"
    )
    @QueryHints({
        @QueryHint(
            name = "jakarta.persistence.query.timeout",
            value = "3000"
        )
    })
    List<PurchaseOrder> findByStatusWithTimeout(
        @Param("status") OrderStatus status
    );
}
~~~

Khi áp dụng vào dự án thật, nhớ import:

~~~java
import org.springframework.data.repository.query.Param;
~~~

Ở đây có **hai tầng annotation**:

- `@QueryHints` của Spring Data JPA để khai báo hint cho repository method.
- `@QueryHint` của Jakarta Persistence để mô tả từng name/value cụ thể.

Spring Data là framework bổ sung; code này không còn portable trên một ứng dụng JPA thuần không sử dụng Spring Data.

### 10.1. Query đếm và pagination

Khi repository trả `Page<T>`, Spring Data có thể tạo thêm count query. Một số thuộc tính cấu hình `@QueryHints` của Spring Data cho phép quyết định có áp dụng hints cho count query hay không, ví dụ:

~~~java
@QueryHints(
    value = {
        @QueryHint(
            name = "jakarta.persistence.query.timeout",
            value = "3000"
        )
    },
    forCounting = false
)
~~~

Nếu hint fetch graph hoặc fetch size chỉ phù hợp query chính, việc dùng nó trên count query có thể không có ý nghĩa hoặc làm phát sinh hành vi không mong muốn. Nên kiểm tra query thực tế do Spring Data sinh ra thay vì chỉ nhìn method repository.

### 10.2. `@Transactional(readOnly=true)` không tương đương query hint

Một repository method:

~~~java
@Transactional(readOnly = true)
List<PurchaseOrder> findAllByStatus(OrderStatus status);
~~~

khai báo transaction hint/chính sách của Spring, không phải yêu cầu JPA query timeout hoặc entity graph cụ thể.

Trong tích hợp Spring/Hibernate, readOnly có thể ảnh hưởng flush behavior theo cấu hình, nhưng không đồng nghĩa với một query-level `HINT_READ_ONLY` của Hibernate trong mọi phiên bản và tình huống.

## 11. `Query.getHints()` có thể giúp kiểm tra gì?

JPA cung cấp:

~~~java
Map<String, Object> hints = query.getHints();
~~~

Ví dụ:

~~~java
TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
);

query.setHint("jakarta.persistence.query.timeout", 3000);

Map<String, Object> hints = query.getHints();

hints.forEach((name, value) -> {
    System.out.println(name + " = " + value);
});
~~~

Đây là bước **quan sát cấu hình của Query** theo provider. Nó hữu ích khi:

- Muốn biết Query đang ghi nhận những giá trị hint nào.
- Debug named query có metadata hint từ annotation.
- Kiểm tra query do framework tạo có cấu hình dự kiến hay không.
- So sánh cấu hình trước và sau `setHint()`.

Nhưng có một giới hạn quan trọng.

### 11.1. `getHints()` không phải bằng chứng tuyệt đối SQL đã áp dụng hint

Có sự khác biệt giữa:

1. Ứng dụng gọi `setHint()` thành công.
2. Provider nhận diện tên hint.
3. Provider ghi nhận hint vào Query metadata.
4. Provider chuyển hint thành JDBC/SQL behavior phù hợp.
5. Database/driver thực sự thực thi hành vi dự kiến.

`getHints()` chủ yếu giúp quan sát tầng cấu hình trong JPA; nó **không thay thế việc kiểm tra SQL, log, driver hoặc test hành vi** ở các tầng dưới.

Với hint không hỗ trợ, theo ngữ nghĩa JPA, provider có thể âm thầm bỏ qua. Việc một hint xuất hiện hoặc không xuất hiện trong Map cần được hiểu theo hợp đồng của provider; không viết kiểm tra “nếu map có key thì DB chắc chắn hỗ trợ”.

### 11.2. Cách kiểm tra kỹ thuật có thể tổ chức

~~~java
TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
);

query.setHint("jakarta.persistence.query.timeout", 3000);

Object actual = query.getHints().get(
    "jakarta.persistence.query.timeout"
);

System.out.println("Configured timeout hint: " + actual);
~~~

Thông tin đó mới là **bước đầu**. Bước sau là thực thi một truy vấn phù hợp, quan sát timeout thật với provider/database đang chạy.

## 12. Không nhận diện hint: Vì sao ứng dụng có thể không báo lỗi?

JPA được thiết kế cho tính mở rộng: các provider có thể có nhiều hint riêng. Vì thế khi gọi:

~~~java
query.setHint("vendor.feature.not.available", true);
~~~

provider có thể bỏ qua một hint không được nhận diện. Điều này tránh việc một tên hint riêng provider làm hỏng hoàn toàn ứng dụng trên provider khác, nhưng cũng làm tăng rủi ro:

> Một dòng `setHint(...)` chạy qua mà không lỗi **không chứng minh** tính năng đã hoạt động.

### 12.1. Không nên coi “không exception” là bài test hỗ trợ

Ví dụ:

~~~java
query.setHint("jakarta.persistence.query.timeout", 250);
query.getResultList();
~~~

Nếu query chạy dưới 250 ms, kết quả bình thường không chứng minh timeout được provider thực thi: ngay cả khi hint bị bỏ qua, query nhanh vẫn thành công.

Muốn kiểm tra tính năng, cần một test tạo ra **điều kiện mà hành vi của hint có thể quan sát**, rồi đối chiếu log/exception/SQL. Và vẫn phải tránh thiết kế test phụ thuộc exact millisecond gây flaky.

### 12.2. Giá trị hint sai kiểu khác hint không được nhận diện

Ví dụ:

~~~java
query.setHint("jakarta.persistence.query.timeout", "very-fast");
~~~

Tên hint có thể hợp lệ nhưng giá trị không phù hợp. Provider có thể ném exception hoặc không chấp nhận giá trị theo cách riêng; không nên coi “đã set được” là giá trị đã hợp lệ.

Ở runtime, dùng kiểu do API/hint quy định; ví dụ timeout thường dùng Integer mili-giây, cache modes dùng enum, entity graph dùng `EntityGraph<?>`.

### 12.3. Hint chuẩn cũng có thể bị giới hạn tính khả thi

Một số chuẩn hint có ngữ nghĩa khuyến nghị và được JPA đặc tả với điều kiện *nếu hỗ trợ được*. Ví dụ lock timeout có thể bị hạn chế do DB không hỗ trợ chờ lock theo timeout mong muốn.

Do đó, phân loại hỗ trợ nên có nhiều mức:

- **Provider nhận diện hint.**
- **Provider có thể ánh xạ hint vào database/driver hiện tại.**
- **Hành vi được quan sát đúng dưới một tình huống kiểm thử.**
- **Hành vi có thể dựa vào cho nghiệp vụ theo hợp đồng portable hay chỉ phụ thuộc stack cụ thể.**

## 13. Hướng dẫn kiểm tra khả năng hỗ trợ theo từng lớp

Đây là phần quan trọng nhất khi dùng query hint trong hệ thống production.

### Lớp 1: Xác định JPA API và namespace

Dự án đang dùng:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.Query;
~~~

hay API legacy:

~~~java
import javax.persistence.EntityManager;
~~~

Namespace hint phải nhất quán với thế hệ API/provider. Không copy tùy tiện những chuỗi `javax.persistence.*` từ bài viết cũ vào ứng dụng Jakarta hiện đại, rồi kỳ vọng provider luôn tương thích.

### Lớp 2: Xác định provider và phiên bản

Có thể xem cấu hình persistence unit, dependency hoặc startup log. Với Hibernate, tên constant và bộ hint được hỗ trợ có thể thay đổi giữa các thế hệ. EclipseLink có danh mục hint riêng.

JPA specification chỉ đảm bảo hợp đồng **portable** của những tính năng chuẩn; mở rộng của vendor cần kiểm tra theo phiên bản thực tế.

### Lớp 3: Xác định cơ sở dữ liệu và JDBC driver

Một hint lock timeout có thể hoạt động trên PostgreSQL nhưng khác trên một DB khác. Hint fetch size có thể bị driver diễn giải tùy chế độ kết nối. Query timeout có thể được làm tròn hoặc bỏ qua.

Không kết luận tính hỗ trợ chỉ từ lớp Java nếu khả năng cần có ở DB.

### Lớp 4: Kiểm tra query metadata

Dùng `getHints()` hoặc cơ chế inspection của provider để xem giá trị cấu hình có được ghi nhận không.

Đây là bằng chứng về **tầng JPA**, không phải tầng thực thi.

### Lớp 5: Quan sát SQL và JDBC

Có thể bật SQL logging, parameter logging ở mức phù hợp, log JDBC/driver hoặc tích hợp metrics. Với hint ảnh hưởng execution plan, xem SQL thật và công cụ `EXPLAIN` của database.

Nếu hint là timeout, SQL có thể không thay đổi dù JDBC statement đã được cấu hình; lúc này SQL log đơn thuần chưa đủ, có thể cần proxy/trace JDBC hoặc test hành vi.

### Lớp 6: Chạy thử trường hợp tạo sự khác biệt

- Timeout: một query thực sự chậm nhưng được kiểm soát.
- Lock timeout: hai transaction tranh chấp cùng row.
- Fetch graph: nạp tập entity rồi kiểm số SQL và tình trạng association.
- Cache: kiểm tra hit/miss và số SQL qua nhiều persistence context.
- Query cache provider-specific: kiểm tra cache region và invalidation.

### Lớp 7: Ghi lại giới hạn và chính sách fallback

Một feature support matrix nên nêu:

- Tên hint và giá trị.
- Provider/phiên bản đã kiểm tra.
- Database và JDBC driver.
- Mức độ hỗ trợ thực tế.
- Điều kiện áp dụng.
- Nếu hint không có tác dụng, hệ thống vẫn đúng nghiệp vụ hay cần cách khác?

Không biến test “lần này chạy tốt” thành bảo đảm vô điều kiện trên mọi môi trường.

## 14. Ma trận minh họa kiểm tra hỗ trợ

Bảng dưới là **mẫu tài liệu kiểm thử**, không phải danh sách kết quả đã được xác minh cho một stack cụ thể.

| Hint hoặc tính năng | Hành vi muốn quan sát | Cách kiểm chứng | Rủi ro/giới hạn |
|---|---|---|---|
| `query.timeout` | Query đủ chậm bị hủy/timeout | Integration test + JDBC trace/exception | Giới hạn driver/DB; không chính xác từng ms |
| `lock.timeout` | Chờ pessimistic lock có giới hạn | Hai transaction tranh chấp row | Chỉ một số chế độ WAIT/NOWAIT có thể khả thi |
| `fetchgraph` | Association trong graph được tải theo fetch plan | Đếm SQL, kiểm tra trạng thái tải | Không cam kết đúng một SQL |
| `loadgraph` | Attribute không liệt kê giữ fetch default | So sánh SQL và mapping | Provider có thể fetch thêm |
| `cache.retrieveMode` | Bỏ qua/cho phép second-level entity cache | Cache stats qua context khác nhau | First-level cache vẫn tác động |
| `cache.storeMode` | Cache được ghi/refresh theo cấu hình | Cache stats và reload | Cần bật cache ở entity/provider |
| Hibernate read-only | Query entity hạn chế dirty checking theo contract Hibernate | Thay managed object rồi flush trong test | Không tương đương transaction readOnly chung |
| Hibernate fetch size | JDBC fetch size được đặt | JDBC trace/driver metrics | Chỉ là gợi ý; streaming tùy driver |
| Hibernate query cache | Query repeated có cache hit | Cache stats và SQL | Cần bật query cache và invalidation |
| SQL optimizer hint | SQL/plan chịu hint | SQL log + DB EXPLAIN | Tên và cú pháp DB-specific |

Những giá trị “Supported/Unsupported/Partial” chỉ nên được điền **sau khi kiểm tra** với provider/database cụ thể.

## 15. Kiểm thử query timeout đúng cách

Một integration test có thể đặt timeout và chạy truy vấn mất thời gian đủ dài để quan sát việc hủy.

### 15.1. Không kiểm tra timeout bằng truy vấn quá nhanh

Test yếu:

~~~java
@Test
void timeoutIsSet() {
    TypedQuery<Long> query = em.createQuery(
        "SELECT COUNT(o) FROM PurchaseOrder o",
        Long.class
    );

    query.setHint("jakarta.persistence.query.timeout", 1);
    query.getSingleResult(); // Chạy nhanh vẫn có thể thành công.
}
~~~

Test này không chứng minh provider áp dụng timeout. Nếu query hoàn thành trong vài mili-giây, có hay không có hint đều cho cùng kết quả.

### 15.2. Tạo truy vấn chậm có kiểm soát

Có thể dùng một truy vấn phức tạp trên fixture đủ lớn hoặc một hàm sleep **riêng của database** trong môi trường test biệt lập, ví dụ PostgreSQL có `pg_sleep`. Những kỹ thuật này thường phải chạy dưới native SQL và không phải JPQL portable.

Một skeleton:

~~~java
@Test
void timeoutMayInterruptSlowQuery() {
    Query query = em.createNativeQuery(
        // SQL thử nghiệm có khả năng chạy chậm,
        // được viết riêng cho database kiểm thử.
        slowDatabaseSpecificSql
    );

    query.setHint(
        "jakarta.persistence.query.timeout",
        1000
    );

    assertThrows(
        PersistenceException.class,
        () -> query.getResultList()
    );
}
~~~

Đây là **khung kiểm thử mang tính định hướng**, không phải assertion có thể copy chạy ngay trên mọi provider. Vì timeout có thể không được hỗ trợ, test phải ghi nhận tình trạng hỗ trợ và loại exception thực tế; không bắt buộc mọi provider ném `PersistenceException` đúng sau một giây.

### 15.3. Tránh benchmark giây tuyệt đối

Một test kiểu:

~~~java
assertTrue(elapsedMillis < 1050);
~~~

rất dễ flaky do scheduler, network, load máy, warm-up và cách làm tròn timeout. Tốt hơn là:

- Có đối chứng query chậm khi không đặt timeout.
- Dùng khoảng thời gian chấp nhận đủ rộng để phân biệt.
- Kiểm tra loại lỗi, DB query state và transaction status.
- Chạy nhiều lần có kiểm soát và ghi nhận sai khác.
- Không chạy test gây lock/sleep nặng trên production database.

### 15.4. Timeout ở JPQL và native query có thể khác

Một provider có thể xử lý timeout khác nhau giữa JPQL, Criteria và native SQL, nhất là khi dùng API riêng của provider. Do đó, test phải dùng đúng **kiểu query dự án thực sự chạy** nếu muốn suy luận về production behavior.

## 16. Kiểm thử lock timeout với hai transaction

Để quan sát `lock.timeout`, cần **tranh chấp lock thực sự**, không chỉ gọi một SELECT nhanh trong một transaction.

### 16.1. Kịch bản

~~~text
Transaction A                         Transaction B
-----------------------------------   ----------------------------------
BEGIN                                 BEGIN
Lock Order #100 bằng PESSIMISTIC_WRITE
                                      Muốn lock Order #100
                                      với lock.timeout = 500 ms
Giữ lock để B phải chờ
                                      -> Có thể timeout nếu hỗ trợ
COMMIT hoặc ROLLBACK
                                      Rollback/đóng transaction
~~~

### 16.2. Pseudocode phối hợp

~~~java
// Transaction A, EntityManager A:
emA.getTransaction().begin();

PurchaseOrder locked = emA.find(
    PurchaseOrder.class,
    orderId,
    LockModeType.PESSIMISTIC_WRITE
);

// Giữ transaction A mở trong phạm vi test có kiểm soát.

// Transaction B, EntityManager B:
emB.getTransaction().begin();

TypedQuery<PurchaseOrder> query = emB.createQuery(
    "SELECT o FROM PurchaseOrder o WHERE o.id = :id",
    PurchaseOrder.class
);

query.setParameter("id", orderId);
query.setLockMode(LockModeType.PESSIMISTIC_WRITE);
query.setHint("jakarta.persistence.lock.timeout", 500);

// Thực thi khi A vẫn giữ lock.
// Quan sát exception, thời gian chờ và trạng thái transaction.
query.getSingleResult();
~~~

Đây là pseudocode: cần cơ chế đồng bộ giữa hai thread/transaction, fixture Order tồn tại, timeout test ở cấp framework và cleanup cả A/B trong `finally`. Không chạy kiểu sleep tùy tiện rồi mong hai transaction chắc chắn đúng thứ tự.

### 16.3. Cần xem transaction bị rollback ở cấp nào

Sau timeout, provider có thể báo `LockTimeoutException` hoặc `PessimisticLockException`, với quy tắc rollback khác nhau. Test không nên mặc định transaction B còn dùng được. Đọc trạng thái transaction hoặc rollback/đóng context theo chính sách an toàn.

### 16.4. Không dùng cùng EntityManager cho hai transaction song song

`EntityManager` không thread-safe. Khi mô phỏng tranh chấp, dùng hai EntityManager riêng, hai transaction thực và connection tương ứng. Nếu dùng Spring `@Transactional` trong hai thread, phải chắc rằng cả hai boundary được tạo đúng qua transaction manager/proxy.

## 17. Kiểm chứng entity graph và N+1

Nếu đặt:

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
);

query.setHint("jakarta.persistence.loadgraph", graph);
List<PurchaseOrder> orders = query.getResultList();
~~~

Một phương án kiểm chứng:

1. Tạo fixture nhiều Order thuộc nhiều Customer.
2. Dọn persistence context/cache giữa các kịch bản để tránh kết quả bị ảnh hưởng bởi entity đã load.
3. Chạy query không có graph; theo dõi số SQL khi truy cập `order.getCustomer().getName()`.
4. Chạy query có graph; theo dõi SQL tương tự.
5. So sánh số round trip và dữ liệu được nạp trên DB/provider thật.
6. Kiểm tra payload/DTO không vô tình truy cập các association khác gây N+1.

### 17.1. Không dùng `getHints()` để thay đếm SQL

Nếu `getHints()` hiển thị graph, điều đó chưa chứng minh query đã giải quyết N+1. Chỉ truy vết SQL và hành vi truy cập object mới trả lời được.

### 17.2. Không giả định graph buộc JOIN

Provider có thể dùng:

~~~sql
SELECT ... FROM purchase_order ...
SELECT ... FROM customer WHERE id IN (...)
~~~

thay vì:

~~~sql
SELECT ... FROM purchase_order
JOIN customer ON ...
~~~

Cả hai đều có thể phù hợp với kế hoạch tải của provider. Nhu cầu nghiệp vụ là giảm SQL không cần thiết và bảo đảm dữ liệu có sẵn đúng use case, không phải luôn ép đúng một dạng JOIN.

### 17.3. Collection fetch và pagination

Nếu graph bao gồm `lines` (to-many) và query phân trang:

~~~java
query.setFirstResult(0);
query.setMaxResults(20);
~~~

phải kiểm tra kỹ SQL và kết quả. Fetch collection có thể nhân số row và khiến provider áp dụng pagination trong bộ nhớ hoặc cảnh báo. Khi phân trang danh sách Order lớn, thường nên dùng query hai bước hoặc projection:

1. Chọn page ID của Order.
2. Tải dữ liệu cần thiết cho page ấy bằng query riêng hoặc fetch plan phù hợp.

Một hint entity graph không thay thế thiết kế phân trang chính xác.

## 18. Kiểm chứng cache bằng nhiều persistence context

Một lỗi test phổ biến là:

~~~java
Customer customer = em.find(Customer.class, id);
Customer again = em.find(Customer.class, id);
~~~

Nếu không có SQL ở lần thứ hai, không thể khẳng định second-level cache hoạt động. Lý do có thể chỉ là **first-level cache** của chính EntityManager.

### 18.1. Thiết kế test cache tốt hơn

~~~text
Transaction / EntityManager A:
    Load Customer #10
    Commit/close

Transaction / EntityManager B:
    Load Customer #10
    Quan sát SQL/cache hit

Transaction / EntityManager C:
    Thử với CacheRetrieveMode.BYPASS
    Quan sát SQL/cache access
~~~

Cần đảm bảo cache của provider thực sự được bật và Customer có cache policy thích hợp.

### 18.2. Dùng thống kê provider nếu có

Hibernate có thống kê cache/query bằng API riêng, nếu được bật. Có thể xem:

- Second-level cache hit/miss/put.
- Query cache hit/miss.
- Prepared statement/query execution counts.

Những số này có thể chịu ảnh hưởng bởi concurrent tests; nên cô lập fixture, cache region và số request.

### 18.3. Không dùng query cache để né tính nhất quán

Dữ liệu đơn hàng cập nhật liên tục có thể không thích hợp với query-result cache nếu cache invalidation phức tạp hoặc yêu cầu đọc mới rất nghiêm ngặt. Trước khi bật query cache, xác định:

- Dữ liệu thay đổi thường xuyên hay ít?
- Query lặp lại đủ nhiều để có lợi không?
- Khi update entity, cache được invalidated thế nào?
- Các đường ghi ngoài JPA có thể làm cache stale không?
- Có cơ chế TTL/eviction và giám sát cache không?

## 19. Hibernate-specific: Read-only query hint

Một số use case chỉ đọc nhiều entity để tính báo cáo, không cần sửa chúng trong persistence context. Hibernate có hint chỉ đọc theo cơ chế riêng:

~~~java
import org.hibernate.jpa.HibernateHints;

TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
);

query.setHint(HibernateHints.HINT_READ_ONLY, true);

List<PurchaseOrder> orders = query.getResultList();
~~~

Tùy phiên bản/cấu hình, Hibernate có thể tối ưu dirty checking/snapshot cho những entity được tải dưới chế độ read-only.

Nhưng cần phân biệt:

- **Read-only entity/query của Hibernate** không phải một ràng buộc DB ngăn mọi UPDATE.
- Nó không thay thế authorization của application.
- Nó không biến toàn bộ transaction thành read-only.
- Nó không nhất thiết thay đổi trạng thái những entity đã managed trước khi query theo cách người viết mong muốn.
- Việc gọi setter trên một entity read-only không làm dữ liệu được commit theo cách thông thường; muốn sửa entity cần hiểu và điều chỉnh read-only status theo contract của Hibernate.

Nếu ứng dụng chỉ cần báo cáo vài cột, projection DTO:

~~~java
List<Object[]> rows = em.createQuery(
    "SELECT o.id, o.totalAmount FROM PurchaseOrder o",
    Object[].class
).getResultList();
~~~

có thể còn hợp lý hơn tải hàng nghìn managed entities chỉ để đọc. Hint read-only là tối ưu có điều kiện, không phải giải pháp chung cho mọi query.

### 19.1. Đừng nhầm với `@Transactional(readOnly=true)`

Spring transaction-level `readOnly` có thể được truyền thành hint hoặc cấu hình session/connection tùy transaction manager, nhưng nó **không đồng nghĩa** việc từng Query luôn mang `HINT_READ_ONLY`. Hãy kiểm tra provider integration và runtime.

### 19.2. Không dùng read-only để bảo vệ dữ liệu nhạy cảm

Một object được tải theo chế độ read-only vẫn có thể chứa các field mà caller không được phép xem. Để bảo vệ thông tin, áp dụng authorization và DTO/projection ở tầng truy vấn/API, không chỉ đặt hint.

## 20. Hibernate-specific: Fetch size

Với kết quả lớn, một số provider cho phép truyền gợi ý fetch size tới JDBC driver.

~~~java
import org.hibernate.jpa.HibernateHints;

TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "ORDER BY o.id",
    PurchaseOrder.class
);

query.setHint(HibernateHints.HINT_FETCH_SIZE, 200);
~~~

`HINT_FETCH_SIZE` là hint riêng Hibernate. Giá trị 200 thường nhằm gợi ý driver lấy dữ liệu theo nhóm, nhưng **không đồng nghĩa chỉ có 200 entity được trả**.

Phân biệt:

| API | Mục tiêu |
|---|---|
| `setMaxResults(200)` | Giới hạn số kết quả logic của query |
| `HINT_FETCH_SIZE = 200` | Gợi ý kích thước fetch cho JDBC/driver, không phải giới hạn kết quả |
| `setFirstResult(200)` | Bỏ qua một số kết quả đầu để phân trang |
| Streaming/scrolling API | Cách tiêu thụ dữ liệu, tùy JPA/provider/driver |

### 20.1. Fetch size không tự tạo streaming

Một số driver yêu cầu transaction/connection settings cụ thể để stream nhiều hàng. Nếu ứng dụng vẫn gọi `getResultList()` và giữ toàn bộ kết quả trong bộ nhớ, fetch size không bảo đảm mức dùng RAM thấp.

Với tác vụ export lớn, phải xem thêm:

- Projection thay vì full entity.
- Pagination hoặc keyset pagination.
- Streaming API và cách đóng stream.
- Kích thước persistence context.
- JDBC driver settings.
- Transaction duration và connection occupancy.

Đừng đặt fetch size rồi kết luận vấn đề memory đã được giải quyết.

## 21. SQL optimizer hint không phải JPA portable hint

DB có thể hỗ trợ SQL optimizer hints riêng, ví dụ cú pháp comment của một số hệ quản trị cơ sở dữ liệu để ưu tiên index hoặc join strategy.

JPQL:

~~~java
SELECT o FROM PurchaseOrder o WHERE o.status = :status
~~~

không có một cú pháp SQL optimizer hint **portable chung cho mọi provider/database** mà ứng dụng có thể đưa vào JPQL tùy ý rồi chắc chắn được truyền sang SQL.

Một số provider cho phép:

- Chèn comment/hint vào SQL sinh ra.
- Tùy chỉnh SQL thông qua extension.
- Chỉ định index/plan bằng API riêng.
- Dùng native SQL khi thật sự cần truy cập tính năng DB-specific.

Tất cả phải được kiểm tra theo provider và DB thật.

### 21.1. Hint optimizer không thay thế index

Nếu query thường lọc:

~~~sql
WHERE status = ?
ORDER BY created_at DESC
~~~

hãy đánh giá index phù hợp theo selectivity, khối lượng dữ liệu và workload. Có thể index `(status, created_at)` hữu ích trong một hệ thống, nhưng phải dùng `EXPLAIN` và số liệu thực tế để quyết định.

Không ép DB dùng một index chỉ vì kết quả một lần benchmark đơn lẻ; optimizer có thể có lý do chọn kế hoạch khác.

### 21.2. Đừng biến tối ưu provider-specific thành quy tắc nghiệp vụ

Nếu một hint chỉ hoạt động trên Oracle hoặc Hibernate, code ứng dụng vẫn phải đúng về **kết quả dữ liệu** khi hint bị bỏ qua, trừ khi đã xác định ràng buộc triển khai rằng provider/database cụ thể là một dependency bắt buộc.

Các tối ưu hiệu năng không nên âm thầm quyết định xem một order có được đặt hay không; việc đó phải dựa trên điều kiện nghiệp vụ được bảo vệ bằng transaction/constraint.

## 22. Query hint và transaction boundary

Một số hint chỉ có ý nghĩa trong transaction phù hợp.

### 22.1. Pessimistic lock cần transaction

~~~java
@Transactional
public PurchaseOrder lockOrder(Long id) {
    return em.createQuery(
            "SELECT o FROM PurchaseOrder o WHERE o.id = :id",
            PurchaseOrder.class
        )
        .setParameter("id", id)
        .setLockMode(LockModeType.PESSIMISTIC_WRITE)
        .setHint("jakarta.persistence.lock.timeout", 500)
        .getSingleResult();
}
~~~

`@Transactional` trong ví dụ này giả định Spring hoặc môi trường phù hợp có transaction interceptor thật sự; phải kiểm tra đúng import/cấu hình. Nếu không có transaction hợp lệ, pessimistic locking có thể gây `TransactionRequiredException`.

### 22.2. Hint không commit giao dịch

Ngay cả khi query timeout hoặc cache hint được áp dụng, giao dịch vẫn do transaction owner quyết định.

~~~text
begin transaction
   |
   +-- persist(order)
   +-- query.setHint(...)
   +-- query.getResultList()
   +-- flush (có thể xảy ra)
   |
   +-- commit hoặc rollback
~~~

Hint không thay thế `flush()`, `commit()` hoặc `rollback()`.

### 22.3. Query hint khác FlushModeType

~~~java
query.setFlushMode(FlushModeType.AUTO);
~~~

và:

~~~java
query.setHint("jakarta.persistence.query.timeout", 3000);
~~~

là hai điều khiển độc lập. Flush mode quyết định ngữ nghĩa đồng bộ pending changes trước khi query; timeout tác động tới thời gian thực thi trong giới hạn hỗ trợ.

Không dùng timeout để kiểm soát khi nào pending inserts/updates được flush; không dùng COMMIT flush mode để đặt query timeout.

### 22.4. Timeout có thể ảnh hưởng trạng thái transaction

Nếu query bị timeout, một số database sẽ đánh dấu transaction lỗi hoặc cần rollback trước khi thực hiện SQL tiếp. Bản thân JPA phân biệt exception loại statement-only timeout và transaction-level failure, nhưng ứng dụng phải xem trạng thái transaction thực tế.

Không nên catch mọi timeout rồi tiếp tục commit những thay đổi trước đó mà không hiểu transaction còn hợp lệ.

## 23. Tránh đặt hint ở phạm vi quá rộng

Một ví dụ dễ gây vấn đề:

~~~java
// Pseudocode: cấu hình timeout cực thấp cho toàn bộ truy vấn
// trong ứng dụng mà không phân loại use case.
globalDefaultQueryTimeout = 100;
~~~

Một timeout 100 ms có thể phù hợp với lookup nhanh, nhưng không hợp lý cho báo cáo tổng hợp lớn đã được phê duyệt. Ngược lại, timeout 60 giây trên mọi truy vấn đơn giản có thể khiến request treo quá lâu khi DB bị lock.

Nên phân loại:

- **Lookup nhanh:** timeout ngắn, projection nhỏ.
- **Danh sách phân trang:** timeout vừa phải, có index và giới hạn kết quả.
- **Báo cáo batch:** timeout khác, chạy nền phù hợp, không chiếm transaction của HTTP request quá lâu.
- **Pessimistic lock:** thời gian chờ ngắn có kiểm soát, xử lý retry/concurrency.
- **Dữ liệu tra cứu ít thay đổi:** cân nhắc cache nếu hợp lý.
- **Quan hệ cần cho một màn hình:** entity graph hoặc projection đúng use case.

Một hint đúng ở một truy vấn không mặc định đúng cho tất cả truy vấn.

## 24. Query hint trong kiến trúc repository/service

Một cách tổ chức rõ ràng:

~~~text
REST Controller
       |
       v
Application Service / Use Case
       |
       +-- Quyết định SLA và transaction
       |
       v
Repository
       |
       +-- JPQL/Criteria
       +-- Parameters
       +-- Query hints cho use case cụ thể
       |
       v
JPA Provider + Database
~~~

Repository có thể đóng gói những hint mang tính kỹ thuật như timeout hoặc fetch graph, nhưng service/use case nên xác định yêu cầu nghiệp vụ: màn hình cần dữ liệu nào, có cần khóa không, deadline nào hợp lý.

### 24.1. Đừng để controller gửi tên hint tự do xuống provider

API kiểu:

~~~json
{
  "filter": "PAID",
  "hintName": "org.hibernate.someOption",
  "hintValue": "anything"
}
~~~

không nên được chuyển trực tiếp thành `query.setHint(...)` từ input người dùng. Điều đó có thể khiến client can thiệp tính năng provider, gây tải nặng hoặc tạo behavior không kiểm soát.

Thay vào đó, controller nhận tham số nghiệp vụ hợp lệ; repository chọn một tập hint **được định nghĩa và kiểm thử** ở phía server.

### 24.2. Định nghĩa helper khi hint lặp lại

~~~java
public final class QueryOptions {

    private QueryOptions() {}

    public static <T> TypedQuery<T> withTimeout(
            TypedQuery<T> query,
            int timeoutMillis) {

        if (timeoutMillis <= 0) {
            throw new IllegalArgumentException(
                "Timeout must be positive"
            );
        }

        query.setHint(
            "jakarta.persistence.query.timeout",
            timeoutMillis
        );
        return query;
    }
}
~~~

Usage:

~~~java
TypedQuery<PurchaseOrder> query =
    em.createQuery(
        "SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class
    );

QueryOptions.withTimeout(query, 3000);
List<PurchaseOrder> orders = query.getResultList();
~~~

Helper giúp nhất quán và giảm lỗi đơn vị thời gian. Nhưng nó **không làm timeout trở thành chắc chắn được hỗ trợ**. Cần có integration test và tài liệu support cho provider.

### 24.3. Ưu tiên độ đúng, sau đó tối ưu

Nếu một query buộc phải thấy dữ liệu đã sửa trong cùng transaction, đừng cố dùng cache/query hint để né quy tắc flush. Nếu ứng dụng cần khóa một row, đừng chỉ đặt `lock.timeout` mà bỏ `setLockMode`. Nếu cần 20 record, dùng `setMaxResults(20)` hoặc pagination, không nhầm với fetch size.

## 25. Khi hint không được hỗ trợ: Chiến lược fallback

Không phải mọi hint bị bỏ qua đều là lỗi nghiêm trọng. Cần phân biệt **hint tối ưu** và **điều kiện bắt buộc cho tính đúng nghiệp vụ**.

### 25.1. Hint chỉ tối ưu

Ví dụ `HINT_FETCH_SIZE` nhằm giảm round trip nhưng nếu provider/driver bỏ qua, query vẫn trả kết quả đúng.

Fallback:

- Tiếp tục sử dụng query.
- Ghi nhận metric/performance.
- Tối ưu bằng pagination/projection hoặc driver settings khi cần.
- Không throw lỗi ứng dụng chỉ vì không đạt đúng fetch size.

### 25.2. Hint liên quan deadline vận hành

Nếu query timeout không hỗ trợ, query vẫn có thể trả kết quả đúng nhưng vượt SLA. Fallback nên xem:

- Timeout ở JDBC/connection/database nếu có và được xác minh.
- Deadline ở service hoặc API gateway.
- Cải thiện query plan/index.
- Giới hạn lượng dữ liệu và phân trang.
- Circuit breaker/cancellation trong phạm vi hỗ trợ.

Không coi việc gọi `setHint("jakarta.persistence.query.timeout", ...)` là bảo đảm duy nhất chống quá tải.

### 25.3. Hint liên quan locking

Nếu lock timeout không hỗ trợ nhưng nghiệp vụ cần “không chờ lâu khi tranh chấp”, có thể phải dùng cơ chế DB-specific đã kiểm thử hoặc thay chiến lược concurrency.

Nếu yêu cầu locking là **điều kiện bắt buộc cho tính đúng**, ứng dụng phải đảm bảo transaction/locking thật sự hoạt động, không chấp nhận âm thầm bỏ qua rồi tiếp tục ghi dữ liệu như thể đã có khóa.

### 25.4. Fallback cho entity graph

Nếu graph tạo query quá nặng hoặc không đem lại hiệu năng như mong muốn:

- Dùng JPQL fetch join có chủ đích.
- Dùng DTO projection.
- Tách query lấy ID và query lấy association.
- Batch fetching theo provider khi được hỗ trợ.
- Đo lại số SQL và kích thước kết quả.

Không ép mọi association EAGER toàn cục chỉ vì một màn hình cần nhiều dữ liệu.

## 26. Những sai lầm phổ biến

### 26.1. Tin rằng `setHint()` không lỗi nghĩa là được hỗ trợ

~~~java
query.setHint("my.unknown.hint", true);
~~~

Một provider có thể bỏ qua hint không nhận diện mà không ném exception. **Cần kiểm chứng hành vi**, không chỉ kiểm tra cú pháp.

### 26.2. Dùng namespace cũ cho ứng dụng Jakarta

~~~java
query.setHint("javax.persistence.query.timeout", 3000);
~~~

Trong dự án mới dùng `jakarta.persistence`, nên dùng tên tương ứng:

~~~java
query.setHint("jakarta.persistence.query.timeout", 3000);
~~~

Các provider có thể duy trì alias tương thích, nhưng không nên dựa vào alias mà không kiểm chứng.

### 26.3. Nhầm đơn vị timeout

~~~java
query.setHint("jakarta.persistence.query.timeout", 3);
~~~

Theo ngữ nghĩa chuẩn, số 3 là **mili-giây**, không phải ba giây. Muốn khoảng ba giây thường dùng `3000`.

### 26.4. Truyền sai kiểu giá trị

~~~java
query.setHint(
    "jakarta.persistence.cache.retrieveMode",
    "BYPASS"
);
~~~

Với API runtime chuẩn, dùng enum:

~~~java
query.setHint(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);
~~~

Không giả định provider tự parse mọi chuỗi giống nhau.

### 26.5. Nhầm QueryHint annotation với Spring QueryHints

~~~java
@QueryHints(...)
~~~

là annotation Spring Data JPA; từng mục `@QueryHint` là annotation JPA. Named JPQL query chuẩn có thể dùng `@NamedQuery(hints = @QueryHint(...))` mà không cần Spring.

### 26.6. Nhầm fetch size với số row trả về

`HINT_FETCH_SIZE = 200` không tương đương `setMaxResults(200)`. Query vẫn có thể trả hàng trăm nghìn entity.

### 26.7. Nhầm read-only query với read-only transaction

Hibernate read-only hint có ngữ nghĩa provider-specific với entity dirty checking, không phải cơ chế bất biến dữ liệu hay quyền truy cập DB.

### 26.8. Dùng lock timeout nhưng không lock

`jakarta.persistence.lock.timeout` có ý nghĩa khi operation yêu cầu pessimistic lock. Đặt riêng hint không có `setLockMode(PESSIMISTIC_*)` không tự tạo row lock.

### 26.9. Dùng getHints làm test hiệu quả

`query.getHints()` là thông tin cấu hình; muốn xác nhận optimization phải quan sát SQL, metrics/cache stats hoặc behavior.

### 26.10. Dùng entity graph làm công cụ bảo mật

Entity graph chọn fetch plan, không chắc provider chỉ load các field khai báo. Không dùng nó thay authorization hoặc DTO projection.

### 26.11. Bật query cache khi dữ liệu thay đổi liên tục

Nếu invalidation thường xuyên, cache có thể tốn công duy trì và dễ hiểu sai tính nhất quán. Cần đánh giá update frequency và cache region.

### 26.12. Chỉ test trên H2 rồi suy ra production

Lock timeout, query timeout, optimizer hint, batch fetching và cache behavior có thể khác đáng kể giữa H2, PostgreSQL, MySQL, Oracle hay SQL Server. Các tình huống phụ thuộc DB phải được kiểm tra trên stack mục tiêu.

## 27. Checklist khi thêm một query hint mới

Trước khi merge code có hint, nên trả lời rõ:

1. **Mục tiêu của hint là gì?** Timeout, cache, fetch plan, lock, fetch size hay tracing?
2. **Có API JPA chuẩn chuyên dụng thay thế không?** Ví dụ `setMaxResults`, `setLockMode`, `setFlushMode`.
3. **Tên hint có thuộc Jakarta Persistence hay là extension?**
4. **Nếu là extension, provider và phiên bản nào hỗ trợ?**
5. **Giá trị cần kiểu gì?** Integer ms, enum, EntityGraph, Boolean hay string trong annotation?
6. **Hint được đặt ở cấp Query hay named query/repository method?**
7. **Nó ảnh hưởng các query khác hoặc count query không?**
8. **Transaction cần active hay lock mode nào phải được đặt không?**
9. **Có thể quan sát tác dụng bằng log, JDBC trace, cache stats hoặc test behavior không?**
10. **Nếu hint bị bỏ qua, ứng dụng có còn đúng nghiệp vụ không?**
11. **Đã thử trên DB/JDBC driver/provider giống production chưa?**
12. **Đã ghi lại fallback và những giới hạn hỗ trợ chưa?**

Đối với hint chỉ mang tính tối ưu, có thể chấp nhận fallback hiệu năng. Đối với hint có liên quan tính đúng nghiệp vụ hoặc an toàn concurrency, không được dựa vào hành vi chưa được xác minh.

## 28. Bài tập thực hành

### Bài 1. Nhận diện query hint

Cho đoạn code:

~~~java
TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o WHERE o.status = :status",
    PurchaseOrder.class
);

query.setParameter("status", OrderStatus.PAID);
query.setMaxResults(50);
query.setHint("jakarta.persistence.query.timeout", 3000);
~~~

**Câu hỏi:** Lệnh nào đặt JPQL parameter, lệnh nào giới hạn số bản ghi, lệnh nào là query hint?

**Đáp án:** `setParameter` bind `:status`; `setMaxResults(50)` giới hạn kết quả; `setHint(...,3000)` yêu cầu query timeout. Chúng phục vụ ba mục đích khác nhau.

### Bài 2. Giá trị timeout

Một developer viết:

~~~java
query.setHint("jakarta.persistence.query.timeout", 5);
~~~

và nói đã đặt timeout năm giây.

**Đáp án:** Không đúng theo đơn vị chuẩn của hint. `5` là năm mili-giây; muốn năm giây, truyền `5000`. Còn việc timeout được thực thi chính xác đến đâu tùy provider/driver/database.

### Bài 3. NamedQuery

~~~java
@NamedQuery(
    name = "Order.findNew",
    query = "SELECT o FROM PurchaseOrder o " +
            "WHERE o.status = :status",
    hints = @QueryHint(
        name = "jakarta.persistence.query.timeout",
        value = "2000"
    )
)
~~~

**Câu hỏi:** Vì sao `value = "2000"` là String, trong khi `setHint` thường dùng số 2000?

**Đáp án:** Annotation `@QueryHint.value` có kiểu String. API runtime `Query.setHint` nhận Object và timeout thường dùng Integer mili-giây.

### Bài 4. Query hint riêng Hibernate

~~~java
query.setHint(HibernateHints.HINT_CACHEABLE, true);
~~~

**Câu hỏi:** Có thể dùng y nguyên khi đổi sang EclipseLink không?

**Đáp án:** Không portable. Đây là constant/provider extension của Hibernate, có thể không tồn tại hoặc không được EclipseLink hiểu. Cần kiểm tra tính năng tương đương và cấu hình riêng, hoặc bỏ tối ưu nếu không cần.

### Bài 5. Kiểm tra nhận diện hint

Code chạy không lỗi:

~~~java
query.setHint("not.a.real.hint", true);
query.getResultList();
~~~

**Câu hỏi:** Có chứng minh hint được áp dụng không?

**Đáp án:** Không. Provider có thể âm thầm bỏ qua tên không nhận diện. Cần tài liệu hỗ trợ, inspection và test hành vi.

### Bài 6. Entity graph

Một màn hình danh sách Order cần Customer.name nhưng không cần Order.lines.

**Câu hỏi:** Nên làm gì để giảm N+1?

**Đáp án gợi ý:** Có thể dùng `EntityGraph<PurchaseOrder>` với attribute `customer` và áp dụng `jakarta.persistence.loadgraph` hoặc `fetchgraph`, hoặc JPQL fetch join/projection. Chọn dựa trên SQL thực tế, không mặc định graph luôn tạo một JOIN hoặc bảo đảm không có query phụ.

### Bài 7. Cache hint

~~~java
query.setHint(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);
~~~

**Câu hỏi:** Tác dụng có nghĩa bỏ qua mọi object đã managed trong EntityManager không?

**Đáp án:** Không. Đây là hint về second-level cache retrieval; first-level persistence context vẫn có identity map và các quy tắc riêng.

### Bài 8. Lock timeout

Một query đặt:

~~~java
query.setHint("jakarta.persistence.lock.timeout", 500);
~~~

nhưng không gọi `setLockMode`.

**Câu hỏi:** Có đảm bảo database sẽ khóa các row được chọn không?

**Đáp án:** Không. Lock timeout không tự yêu cầu lock. Cần `setLockMode(PESSIMISTIC_*)` trong transaction phù hợp và kiểm tra hỗ trợ của DB/provider.

### Bài 9. Fetch size

~~~java
query.setHint(HibernateHints.HINT_FETCH_SIZE, 100);
~~~

**Câu hỏi:** Query có chỉ trả tối đa 100 entity không?

**Đáp án:** Không. Fetch size là gợi ý JDBC/driver về cách lấy dữ liệu, không phải giới hạn số row. Dùng `setMaxResults(100)` nếu cần tối đa 100 kết quả.

### Bài 10. Timeout test

Một query hoàn thành trong 10 ms sau khi đặt timeout 1000 ms.

**Câu hỏi:** Có thể kết luận provider hỗ trợ query timeout không?

**Đáp án:** Không. Query nhanh sẽ thành công kể cả khi timeout bị bỏ qua. Cần test query chậm có kiểm soát và quan sát hủy query/exception trên stack thực.

### Bài 11. Spring Data count query

Một repository `Page<PurchaseOrder>` áp dụng fetch-related hints cho query chính, nhưng count query cũng bị ảnh hưởng.

**Câu hỏi:** Cần kiểm tra gì?

**Đáp án:** Xem cách Spring Data tạo count query và cấu hình `@QueryHints` như `forCounting=false` nếu phù hợp. Tách nhu cầu load entity của query chính khỏi nhu cầu đếm record.

### Bài 12. Hint bắt buộc cho nghiệp vụ

Nghiệp vụ yêu cầu không chờ khóa quá lâu, nhưng database production không hỗ trợ lock timeout theo mong muốn.

**Câu hỏi:** Có được tiếp tục dựa trên `setHint("jakarta.persistence.lock.timeout", 500)` không?

**Đáp án:** Không nên. Cần thiết kế cơ chế concurrency/deadline khác được DB/provider hỗ trợ và kiểm thử, hoặc thay đổi contract nghiệp vụ. Hint bị bỏ qua có thể khiến request chờ lâu ngoài dự kiến.

### Bài 13. Provider khác nhau

Hai môi trường cùng chạy JPQL và `jakarta.persistence.query.timeout`, nhưng môi trường A hủy query khi chậm còn môi trường B không hủy.

**Câu hỏi:** Có nhất thiết do JPA query viết sai không?

**Đáp án:** Không. Cần kiểm tra provider, version, driver, DB, cách chuyển timeout và kiểu query. Hint chuẩn vẫn có giới hạn về khả năng thực thi cụ thể.

### Bài 14. Query-level optimization và transaction

Một repository gọi `setHint(HibernateHints.HINT_READ_ONLY, true)` trên query, sau đó service sửa một entity managed khác trong cùng transaction.

**Câu hỏi:** Có chắc toàn transaction không ghi thay đổi nào không?

**Đáp án:** Không. Read-only query hint áp dụng theo ngữ nghĩa Hibernate cho query/các entity liên quan, không mặc định cấm mọi thao tác ghi của transaction.

## 29. Quy trình áp dụng query hint trong dự án thực tế

~~~text
Nhu cầu vận hành của một JPQL query
                 |
                 v
     Có API JPA chuẩn chuyên dụng?
                 |
          +------+------+
          |             |
         Có            Không
          |             |
       Dùng API         Xem query hint
          |             |
          +------+------+
                 |
                 v
      Hint chuẩn Jakarta hay vendor?
                 |
          +------+------+
          |             |
        Chuẩn       Provider-specific
          |             |
       Đúng kiểu       Đúng constant,
       giá trị và      phiên bản và DB
       ngữ nghĩa
          |             |
          +------+------+
                 |
                 v
        Cấu hình Query / NamedQuery
                 |
                 v
        Kiểm tra getHints() (cấu hình)
                 |
                 v
        Kiểm tra SQL/JDBC/metrics
                 |
                 v
        Integration test hành vi
                 |
                 v
        Ghi nhận hỗ trợ và fallback
                 |
                 v
        Theo dõi production
~~~

Trong bước kiểm tra, điều quan trọng là **chọn bằng chứng phù hợp với loại hint**. Timeout cần test thời gian/lỗi; cache cần thống kê hit/miss và số SQL; graph cần quan sát fetch behavior; lock timeout cần hai transaction tranh chấp; optimizer hint cần SQL plan; fetch size cần trace driver.

Không có một phương pháp `getHints().containsKey(...)` đủ chứng minh mọi loại hint.

## 30. Tổng kết các nguyên tắc

~~~text
JPQL mô tả "LẤY DỮ LIỆU GÌ"
      |
      +-- WHERE, JOIN, ORDER BY, parameters
      |
      v
Query hint mô tả "GỢI Ý THỰC THI NHƯ THẾ NÀO"
      |
      +-- query.timeout
      +-- lock.timeout
      +-- cache.retrieveMode / cache.storeMode
      +-- fetchgraph / loadgraph
      +-- provider-specific options
      |
      v
JPA provider quyết định áp dụng trong giới hạn hỗ trợ
      |
      v
JDBC / Database thực thi
      |
      v
Đo lường và kiểm tra: hint CÓ THẬT SỰ TẠO TÁC DỤNG KHÔNG?
~~~

Các điểm cần ghi nhớ:

1. **`setHint(name, value)` truyền gợi ý tới JPA provider**, không phải mệnh lệnh portable bảo đảm mọi database làm y hệt.
2. **Dùng `TypedQuery` khi có thể** để làm rõ kiểu kết quả; có thể cấu hình hint bằng `Query.setHint` hoặc `TypedQuery.setHint`.
3. **Hint chuẩn Jakarta Persistence khác hint riêng provider.** Những extension như Hibernate fetch size/read-only/query cache phải được kiểm tra theo phiên bản.
4. **`@NamedQuery(hints = @QueryHint(...))` cấu hình hint ở metadata**, trong khi `setHint(...)` cấu hình tại runtime. Giá trị `@QueryHint.value` là String.
5. **`query.timeout` và `lock.timeout` là hai vấn đề khác nhau.** Timeout có thể bị giới hạn bởi provider/driver/DB và không phải deadline tuyệt đối của toàn request.
6. **Cache retrieve/store modes liên quan tới second-level entity cache**, không đồng nghĩa query-result cache và không bỏ qua mọi managed entity ở first-level context.
7. **`fetchgraph` và `loadgraph` điều chỉnh fetch plan**, không cam kết SQL đúng một JOIN, không phải công cụ bảo mật và không thay projection.
8. **`getHints()` giúp xem cấu hình Query nhưng không đủ chứng minh tác dụng runtime.** Hint không được nhận diện có thể bị bỏ qua.
9. **Không nhầm `setMaxResults` với fetch size, `setLockMode` với lock timeout, `setFlushMode` với query timeout.** Mỗi API điều khiển một khía cạnh riêng.
10. **Kiểm chứng bằng integration test trên provider, JDBC driver và database mục tiêu**, với tình huống thực sự khiến hiệu ứng hint có thể quan sát.
11. **Thiết kế fallback cho hint không được hỗ trợ.** Với hint tối ưu có thể chấp nhận hiệu năng thấp hơn; với yêu cầu concurrency/deadline quan trọng phải có phương án được bảo đảm.
12. **Độ đúng của JPQL và giao dịch quan trọng hơn tối ưu hint.** Hãy thiết kế query, index, transaction và entity loading đúng trước khi tinh chỉnh provider-specific.

Áp dụng query hint hiệu quả không nằm ở việc thêm nhiều dòng `setHint(...)`, mà ở khả năng **xác định mục tiêu cụ thể, dùng đúng contract, hiểu giới hạn hỗ trợ và đo được hành vi thực tế**. Khi có quy trình kiểm chứng rõ ràng, query hint trở thành công cụ tối ưu hữu ích mà không làm ứng dụng phụ thuộc mù quáng vào một provider hoặc database.
