# Mối liên hệ giữa EntityManager và tập entity được quản lý trong JPA

Một câu lệnh `SELECT` từ cơ sở dữ liệu không tự động tạo ra một đối tượng Java được theo dõi suốt thời gian tồn tại của ứng dụng. Trong Java Persistence API (JPA), việc một entity có được quản lý hay không phụ thuộc vào **persistence context** (ngữ cảnh lưu trữ), còn **`EntityManager`** là giao diện chính để ứng dụng làm việc với ngữ cảnh đó.

Đây là điểm phân biệt cốt lõi khi học JPA:

> **`EntityManager` là API để thao tác với persistence context; persistence context là tập những entity instance đang được quản lý cùng trạng thái liên quan đến chúng.**

Nhờ persistence context, JPA có thể giữ **identity thống nhất** của entity, tự phát hiện thay đổi (*dirty checking*), điều phối các thao tác thêm/sửa/xóa và gửi lệnh SQL khi thích hợp. Nhưng điều đó cũng tạo ra các giới hạn: entity có thể trở thành *detached*, dữ liệu trong bộ nhớ có thể khác database, quá nhiều entity managed có thể tốn bộ nhớ, và `EntityManager` không phải đối tượng an toàn để chia sẻ tùy tiện giữa nhiều thread.

Bài này giải thích cách các thành phần liên hệ với nhau, vòng đời entity từ *new* tới *managed* rồi *detached/removed*, tác động của `persist`, `find`, `merge`, `remove`, `flush`, `clear` và transaction, cùng những tình huống thường gặp trong ứng dụng Java.

## 1. Bức tranh tổng thể: từ Java object đến database

Một luồng làm việc đơn giản:

```text
                Ứng dụng Java
                     |
                     | EntityManager API
                     v
              +--------------+
              | EntityManager|
              +--------------+
                     |
                     | Làm việc với
                     v
        +-----------------------------+
        |      Persistence Context    |
        |-----------------------------|
        | Customer#1  -> object A     |
        | Customer#2  -> object B     |
        | Order#10    -> object C     |
        |-----------------------------|
        | Trạng thái được quản lý     |
        | Snapshot / dirty tracking   |
        | Các thay đổi chờ đồng bộ    |
        +-----------------------------+
                     |
                     | flush / SQL thông qua provider + JDBC
                     v
              +---------------+
              |   Database    |
              |---------------|
              | customer      |
              | purchase_order|
              +---------------+
```

Trong hình:

- **`EntityManager`** cho phép tìm, tạo, merge, xóa, khóa, refresh và truy vấn entity.
- **Persistence context** nhận diện các entity đang *managed* và cung cấp nhất quán về Java instance cho từng persistent identity.
- **JPA provider** (ví dụ Hibernate, EclipseLink) thực thi mapping, dirty checking, SQL generation và cache cụ thể.
- **Database** lưu các hàng quan hệ dưới transaction. Nó không chứa trực tiếp Java object.
- **JDBC** là lớp giao tiếp với database; ngữ cảnh JPA không đồng nghĩa một JDBC connection cố định.

Một `EntityManager` hoạt động trong quan hệ với một persistence context, nhưng ở môi trường container-managed, **nhiều tham chiếu `EntityManager` được inject có thể cùng tham gia một persistence context gắn với transaction**. Do vậy không nên hình dung mọi biến Java kiểu `EntityManager` luôn tạo một persistence context hoàn toàn riêng.

## 2. EntityManager là gì?

`EntityManager` là một giao diện của Jakarta Persistence:

```java
import jakarta.persistence.EntityManager;
```

Các phương thức tiêu biểu:

| Phương thức | Ý nghĩa chính |
|---|---|
| `persist(entity)` | Đưa entity mới vào trạng thái managed và lên lịch lưu theo vòng đời persistence |
| `find(EntityClass.class, id)` | Tìm entity theo identity; trả về managed instance trong context |
| `getReference(EntityClass.class, id)` | Lấy reference tới identity, có thể trì hoãn truy vấn thực tế |
| `merge(entity)` | Sao chép trạng thái của entity vào một managed instance và trả instance đó |
| `remove(entity)` | Đánh dấu managed entity để xóa |
| `contains(entity)` | Hỏi một instance cụ thể có đang được context quản lý không |
| `detach(entity)` | Ngừng quản lý instance cụ thể |
| `clear()` | Gỡ toàn bộ entity khỏi persistence context |
| `flush()` | Đồng bộ các thay đổi chờ của context với database trong transaction |
| `refresh(entity)` | Đọc lại state của managed entity từ database theo điều kiện thích hợp |
| `createQuery(...)` | Tạo và chạy JPQL/Criteria query |
| `lock(entity, ...)` | Áp dụng cơ chế khóa được JPA hỗ trợ |

`EntityManager` không phải:

- Một Java `Map` công khai cho phép đọc trực tiếp tất cả managed objects.
- Một kết nối JDBC duy nhất được giữ mãi từ lúc tạo đến lúc đóng.
- Một thread-safe singleton dùng chung cho mọi request.
- Một transaction. Transaction và persistence context có **vòng đời liên quan nhưng không phải cùng một khái niệm**.
- Một cơ chế tự động quản lý mọi POJO trong heap. Chỉ các entity instance thực sự thuộc persistence context mới là managed.

### 2.1. EntityManagerFactory nằm ở đâu?

Trong ứng dụng JPA tự quản lý (resource-local), `EntityManagerFactory` được tạo từ persistence unit:

```java
EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("learningPU");

EntityManager em = emf.createEntityManager();

try {
    // Thao tác JPA với em.
} finally {
    em.close();
    emf.close(); // Chỉ đóng khi ứng dụng không còn dùng factory.
}
```

Ví dụ trên rút gọn để làm rõ API. Trong server thực tế, **`EntityManagerFactory` thường được tạo một lần cho ứng dụng** rồi đóng khi ứng dụng tắt, còn `EntityManager` được cấp cho mỗi đơn vị công việc/thời gian thích hợp.

Phân biệt:

| Thành phần | Quy mô trách nhiệm |
|---|---|
| `EntityManagerFactory` | Quản lý cấu hình persistence unit, tạo EntityManager; được thiết kế để sử dụng chung giữa các luồng |
| `EntityManager` | API thao tác persistence context cho một đơn vị công việc/ngữ cảnh; **không thread-safe** |
| Persistence context | Giữ tập managed entities và trạng thái phục vụ đồng bộ |
| Database transaction | Ranh giới commit/rollback các thay đổi dữ liệu ở database |

Trong môi trường Jakarta EE/Spring, lifecycle của `EntityManager` và transaction thường được container/framework quản lý. Không phải lúc nào code ứng dụng cũng tự gọi `createEntityManager()` hoặc `close()`.

## 3. Persistence context là gì?

Persistence context là tập những **entity instance** đang được provider quản lý theo một persistent identity. Ngoài các đối tượng, provider còn lưu thông tin cần thiết để theo dõi thay đổi và đồng bộ với database.

Có thể hình dung:

```text
Persistence context, ở thời điểm T:

    (Customer.class, 5)   -> Customer instance A
    (Customer.class, 9)   -> Customer instance B
    (PurchaseOrder.class, 27) -> PurchaseOrder instance C

    A.name đã thay đổi?  -> Có thể đánh dấu/suy ra dirty
    B.name đã thay đổi?  -> Không
    C đang chờ xóa?      -> Không
```

Hình trên là **mô hình tư duy**, không phải cấu trúc nội bộ bắt buộc của mọi provider. Hibernate có thể dùng snapshot, bytecode enhancement, identity map và nhiều cấu trúc khác; EclipseLink có chiến lược khác. Điều JPA bảo đảm ở mức khái niệm là tính quản lý và nhất quán entity identity trong persistence context.

### 3.1. Identity map: một identity, một managed instance

Giả sử `Customer` có `@Id Long id`.

```java
Customer first = em.find(Customer.class, 5L);
Customer second = em.find(Customer.class, 5L);

System.out.println(first == second); // true trong cùng persistence context.
```

Nếu cả hai lần tìm đều trả entity cùng persistent identity trong **cùng persistence context**, JPA quản lý **một Java instance** đại diện cho entity đó. Đó là ý tưởng của *identity map*.

Điểm cần hiểu:

- Database có thể có rất nhiều hàng.
- Trong một context, một identity cụ thể không được biểu diễn bởi hai managed instance độc lập.
- Nếu entity đã managed, JPA có thể dùng lại chính object đang có thay vì hydrate một object khác.
- Các query JPQL trả về entity cùng identity cũng phối hợp với identity map này.
- Khi đổi sang persistence context khác, cùng một database row có thể được biểu diễn bởi **instance Java khác**.

Ví dụ hai context độc lập:

```java
EntityManager em1 = emf.createEntityManager();
EntityManager em2 = emf.createEntityManager();

try {
    Customer c1 = em1.find(Customer.class, 5L);
    Customer c2 = em2.find(Customer.class, 5L);

    // Cùng persistent identity, nhưng không bắt buộc
    // là cùng Java object.
    System.out.println(c1 == c2); // Thường false.
} finally {
    em1.close();
    em2.close();
}
```

`em1` và `em2` trong ví dụ là application-managed EntityManager độc lập. Nếu cả hai đọc cùng row, đối tượng được quản lý trong mỗi context là riêng. Việc `c1.equals(c2)` trả `true` hay `false` lại phụ thuộc cách entity triển khai `equals`, không thay đổi hợp đồng identity map.

### 3.2. Persistence context không phải cache dữ liệu vô hạn

Persistence context thường được gọi là **first-level cache** vì nó có thể giữ managed entity đã đọc. Nhưng có ba điều cần tách biệt:

1. **Identity map**: nhất quán identity của entity trong context.
2. **Trạng thái managed**: provider theo dõi thay đổi và lifecycle entity.
3. **Chiến lược truy vấn**: mỗi lần `find`/JPQL có dùng SQL hay không còn phụ thuộc query, lock, cache và fetch plan.

Không được suy luận rằng:

> “Một entity đã nằm trong persistence context thì mọi truy vấn JPQL liên quan đến nó đều không chạm database.”

Provider vẫn có thể phải chạy SQL để xác định kết quả truy vấn, join, sort, count hoặc refresh, sau đó tái sử dụng managed instance khi hydrate entity tương ứng.

### 3.3. Persistence context khác second-level cache

| Đặc điểm | Persistence context / first-level cache | Second-level cache (nếu provider hỗ trợ và bật) |
|---|---|---|
| Phạm vi | Một persistence context | Có thể dùng giữa nhiều context |
| Đối tượng | Managed entity instances và state liên quan | Dữ liệu cache theo chiến lược provider |
| Dirty checking | Có, cho managed state | Không thay thế theo dõi sửa đổi entity |
| Identity trong Java | Một managed instance trên một identity trong context | Không bảo đảm hai context dùng cùng Java instance |
| Có theo JPA hoạt động bình thường? | Là phần lõi của persistence context | Tùy cấu hình/shared cache/provider |
| Thao tác quản lý | `detach`, `clear`, `refresh`, kết thúc context | Cơ chế cache API/provider và shared-cache config riêng |

Một cache hit cấp hai không làm hai `EntityManager` độc lập chia sẻ cùng managed Java object. Mỗi context vẫn quản lý instance của riêng nó.

## 4. Bốn trạng thái quan trọng của entity

Một entity instance thường được xét ở các trạng thái:

| Trạng thái | Có identity DB? | Có managed bởi context? | Ý nghĩa |
|---|---|---|---|
| **New / transient** | Có thể chưa có ID; chưa persistent theo JPA | Không | Object mới được tạo bằng `new`, chưa `persist` |
| **Managed / persistent** | Đã gắn với persistent identity hoặc đang trong quá trình tạo | Có | Provider theo dõi state và đồng bộ theo transaction |
| **Detached** | Thường đã tồn tại/persistent identity | Không | Object từng managed nhưng đã rời context |
| **Removed** | Đã có persistent identity | Được đánh dấu xóa theo lifecycle | JPA lên lịch xóa row tương ứng khi flush/commit |

Sơ đồ chuyển trạng thái:

```text
                new Student(...)
                       |
                       | em.persist(entity)
                       v
                   MANAGED
                    |  |  \
          em.detach |  |   \ em.remove
          em.clear  |  |    \
          em.close* |  |     v
                    |  |   REMOVED
                    v  |
                 DETACHED
                    |
                    | em.merge(detached)
                    | trả về managed instance
                    +--------------------> MANAGED (instance khác)

* Đóng application-managed EntityManager gắn context với nó.
```

Quan trọng:

- `merge` **không “biến” detached object gốc thành managed**; nó trả về một managed instance, có thể là một Java object khác.
- `remove` áp dụng cho managed entity và khiến entity đi vào lifecycle removed; không có nghĩa SQL `DELETE` phải chạy ngay tức thì.
- Một entity mới gọi `persist` trở thành managed theo lifecycle JPA, dù câu `INSERT` có thể chờ flush/commit hoặc chạy sớm khi provider cần ID.
- Đóng context hoặc gọi `clear` có thể làm các instance trước đó mất trạng thái managed, nhưng không xóa row database.

### 4.1. Entity có `id != null` chưa chắc managed

```java
Customer customer = new Customer();
customer.setId(5L);
```

Việc object có ID **không tự đưa nó vào context**. Một POJO có `id = 5` có thể là new/transient, detached hoặc managed tùy lịch sử và ngữ cảnh thực tế.

Cũng vậy:

```java
Customer detached = ...;

boolean managed = em.contains(detached);
```

`contains` hỏi **instance cụ thể có đang được context hiện tại quản lý hay không**. Nó không chỉ hỏi “ID này có tồn tại trong database không?”.

### 4.2. Object managed không nhất thiết đã được commit

```java
Customer c = new Customer("An");

em.persist(c);
System.out.println(em.contains(c)); // true khi persist hợp lệ.
```

Entity `c` đã managed, nhưng database có thể chưa nhận `INSERT` hoặc transaction chưa commit. Managed state là một khái niệm trong context, không đồng nghĩa dữ liệu đã bền vững sau commit.

## 5. Ví dụ xuyên suốt: Customer và PurchaseOrder

Để quan sát các thao tác, dùng hai entity.

### 5.1. Customer

```java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String name;

    @Column(nullable = false, unique = true, length = 254)
    private String email;

    @Version
    private long version;

    protected Customer() {
    }

    public Customer(String name, String email) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email không hợp lệ");
        }
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void rename(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public long getVersion() {
        return version;
    }
}
```

### 5.2. PurchaseOrder

```java
package com.example.persistence;

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
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal totalAmount;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Customer customer, BigDecimal totalAmount) {
        if (customer == null) {
            throw new IllegalArgumentException("Thiếu khách hàng");
        }
        if (totalAmount == null || totalAmount.signum() < 0) {
            throw new IllegalArgumentException("Tổng tiền không hợp lệ");
        }
        this.customer = customer;
        this.totalAmount = totalAmount;
    }

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }
}
```

Entity `Customer` có version để minh họa optimistic locking, còn `PurchaseOrder.customer` là association nhiều-một để thấy hai entity cùng được persistence context theo dõi.

Schema khái niệm:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(254) NOT NULL UNIQUE,
    version BIGINT NOT NULL
);

CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customer(id)
);
```

Đây chỉ là DDL mô tả các cột/quan hệ; cơ chế IDENTITY/sequence và kiểu dữ liệu chi tiết phụ thuộc database, dialect và migration.

## 6. `persist`: đưa object mới vào tập managed

### 6.1. Trước và sau persist

```java
Customer customer = new Customer("An", "an@example.com");

// Vừa gọi new: object chưa thuộc persistence context.
System.out.println(em.contains(customer)); // false.

em.persist(customer);

// Sau persist hợp lệ, object trở thành managed.
System.out.println(em.contains(customer)); // true.
```

Diễn biến:

```text
new Customer(...)                 em.persist(customer)
       |                                  |
       v                                  v
Transient Java object  ---------->  Managed entity
                                           |
                                           | flush/commit
                                           v
                                      INSERT customer
```

Khi entity managed, ứng dụng sửa thuộc tính persistent của nó trong transaction và provider có thể nhận ra thay đổi.

Không nên tự động đồng nhất `persist` với việc `INSERT` chạy ngay. Một số chiến lược sinh ID như IDENTITY có thể đòi hỏi INSERT sớm để lấy khóa; các chiến lược khác có thể trì hoãn tới flush. Thời điểm thực thi chi tiết phụ thuộc provider, database và transaction.

### 6.2. Không gọi `persist` một lần cho mỗi lần sửa

Sau khi đã managed:

```java
Customer customer =
    em.find(Customer.class, customerId);

customer.rename("An Nguyễn");

// Không cần gọi em.persist(customer) lần nữa
// chỉ để lưu thuộc tính name trong transaction.
```

Nếu code liên tục gọi `persist` trên entity managed, lời gọi thường không tạo ý nghĩa “update”; nó không phải phương thức `save()` tổng quát có thể thay cho mọi lifecycle. Với detached entity, `persist` cũng không phải cách portable để gắn lại; có thể phát sinh lỗi entity đã tồn tại/detached.

### 6.3. Cascade và tập managed

Nếu một entity chứa association có cascade persist:

```java
@OneToMany(
    mappedBy = "customer",
    cascade = CascadeType.PERSIST
)
private List<PurchaseOrder> orders;
```

thì persist Customer có thể cascade persist tới PurchaseOrder được liên kết theo cấu hình, khiến **nhiều instance** trở thành managed. Nhưng điều đó không biến mọi object trong Java graph thành managed tự động nếu không có mapping/cascade đúng.

Đặc biệt, cascade lifecycle khác với ownership của khóa ngoại: với `@ManyToOne` ở PurchaseOrder, phải gán đúng `order.customer` để FK được cập nhật.

## 7. `find`: tìm entity và dùng lại managed instance

### 7.1. Gọi nhiều lần trong cùng context

```java
Customer customer1 = em.find(Customer.class, 5L);
Customer customer2 = em.find(Customer.class, 5L);

boolean sameReference = (customer1 == customer2);
// true nếu cùng entity trong một persistence context.
```

Nếu database có row `customer.id = 5`, context ánh xạ row này thành một managed Java instance. Lần tìm sau nhận lại entity đang managed.

Đây là đảm bảo mạnh hơn việc hai object `equals` nhau: chúng là **cùng reference Java** trong context.

### 7.2. JPQL entity query cũng tham gia context

```java
Customer byId = em.find(Customer.class, 5L);

Customer byEmail = em.createQuery(
    "select c from Customer c where c.email = :email",
    Customer.class
)
.setParameter("email", "an@example.com")
.getSingleResult();

System.out.println(byId == byEmail); // true nếu cùng persistent identity.
```

JPQL có thể phát SQL để tìm row theo email, nhưng khi hydrate entity cùng ID, provider phải duy trì identity thống nhất trong context.

Nếu JPQL trả về **DTO** thay vì entity:

```java
public record CustomerSummary(Long id, String name) { }

List<CustomerSummary> summaries = em.createQuery(
    """
    select new com.example.persistence.CustomerSummary(c.id, c.name)
    from Customer c
    """,
    CustomerSummary.class
).getResultList();
```

`CustomerSummary` **không phải managed entity** và không được JPA dirty-check. Thay đổi `summary.name` hoặc tạo record mới không làm đổi row `customer`. Query projection có thể phù hợp khi chỉ cần đọc vài cột.

### 7.3. Không xem context như nguồn truth toàn cục

Giả sử Customer đã được load, trong lúc đó một transaction khác cập nhật database. Lần `find` tiếp theo trong cùng context có thể trả **managed state hiện tại trong bộ nhớ**, chưa chắc đã phản ánh cập nhật bên ngoài.

Persistence context duy trì nhất quán identity và state theo vòng đời của nó, **không cam kết luôn tự cập nhật khi database đổi**. Nếu cần lấy lại state, xem `refresh` và cơ chế concurrency ở phần sau.

## 8. Dirty checking: vì sao sửa field có thể sinh SQL UPDATE?

### 8.1. Một transaction cập nhật entity managed

Giả sử `Customer#5` đã có trong database. Ta thực hiện:

```java
Customer customer = em.find(Customer.class, 5L);

customer.rename("An Nguyễn");

// Không có em.update(customer) trong JPA chuẩn.
```

Nếu entity vẫn managed và transaction được flush/commit hợp lệ, provider theo dõi thay đổi và có thể sinh SQL tương tự:

```sql
UPDATE customer
SET name = ?, version = ?
WHERE id = ? AND version = ?;
```

Do `Customer` có `@Version`, provider có thể dùng version cũ để phát hiện xung đột cập nhật, và tăng version theo quy tắc optimistic locking. SQL chính xác khác theo provider và dialect; một số provider cập nhật nhiều cột hơn trường thay đổi.

Mấu chốt: **người viết Java sửa object managed**, provider **đồng bộ entity state** vào database.

### 8.2. Persistence context giữ thông tin gì để theo dõi?

Có thể hình dung:

```text
Sau find:
    snapshot.name = "An"
    entity.name   = "An"

Sau rename:
    snapshot.name = "An"
    entity.name   = "An Nguyễn"

Tới flush:
    so sánh hoặc cơ chế tracking phát hiện khác biệt
    -> chuẩn bị UPDATE
```

Một số provider dùng snapshot và so sánh, một số dùng bytecode enhancement/dirty tracking để tối ưu. JPA **không buộc mọi provider dùng cùng thuật toán**. Nhưng về mặt ứng dụng, entity managed có thể được đồng bộ khi sửa persistent state.

### 8.3. Đổi field của detached entity không được theo dõi

```java
Customer customer = em.find(Customer.class, 5L);
em.detach(customer);

customer.rename("Tên thay đổi bên ngoài context");
```

Lúc này `customer` không còn managed trong `em`. Sửa nó không tự sinh `UPDATE` từ context đó. Muốn lưu state detached, cần một thao tác phù hợp như `merge` trong transaction và kiểm soát phiên bản.

### 8.4. Sửa dữ liệu trong Java chưa chắc đã ghi ngay

Dirty checking không đồng nghĩa với:

- Có một SQL `UPDATE` chạy mỗi lần gọi setter.
- Thay đổi đã commit và được transaction khác nhìn thấy.
- Provider chắc chắn update nếu entity được detach/clear trước khi flush.
- Thay đổi transient/non-persistent field sẽ được ghi.

Ngữ cảnh và transaction phải còn phù hợp để thay đổi được đồng bộ.

## 9. `flush`, `commit` và transaction: ba khái niệm cần phân biệt

### 9.1. `flush` là đồng bộ, không phải xác nhận transaction

```java
Customer customer = em.find(Customer.class, 5L);
customer.rename("Tên mới");

em.flush(); // Đưa các thay đổi pending phù hợp tới database.
```

Sau `flush`, lệnh SQL có thể đã được database thực thi **trong transaction hiện tại**, nhưng transaction vẫn có thể rollback. Vì vậy `flush()` **không bằng `commit()`**.

Diễn biến:

```text
Java managed entity
       |
       | customer.rename(...)
       v
Persistence context có thay đổi chờ
       |
       | em.flush()
       v
SQL UPDATE gửi tới DB trong transaction
       |
       +------> rollback: DB không xác nhận thay đổi
       |
       +------> commit: thay đổi được xác nhận
```

Tùy môi trường, gọi `flush` khi không có transaction phù hợp có thể dẫn tới `TransactionRequiredException` hoặc hành vi không cho phép đồng bộ. Không nên gọi `flush` như một cách thay transaction.

### 9.2. Commit thường kéo theo flush

Trong một transaction JPA hợp lệ, khi commit, provider thường phải đồng bộ thay đổi pending để hoàn tất transaction. Vì vậy:

```java
customer.rename("Tên mới");
// Transaction commit khi kết thúc service.
```

thường đủ; không cần gọi `em.flush()` thủ công sau từng setter. `flush` thủ công hữu ích khi muốn:

- Phát hiện lỗi constraint sớm hơn trước commit.
- Bảo đảm SQL được gửi trước khi chạy một thao tác phụ thuộc vào dữ liệu đó trong cùng transaction.
- Kiểm soát điểm đồng bộ trong quy trình xử lý theo lô.
- Quan sát SQL trong ví dụ học tập.

Tuy nhiên, flush sớm cũng có chi phí và có thể thay đổi thời điểm phát sinh lỗi. Không lạm dụng `flush` trong mỗi vòng lặp nếu không cần.

### 9.3. Flush mode AUTO và COMMIT

JPA có:

```java
em.setFlushMode(FlushModeType.AUTO);
em.setFlushMode(FlushModeType.COMMIT);
```

Tổng quan:

| Flush mode | Ý nghĩa |
|---|---|
| `AUTO` | Provider phải bảo đảm các thay đổi cần thấy trong những query phù hợp được phản ánh theo hợp đồng của chế độ này; có thể flush trước query hoặc dùng cơ chế khác |
| `COMMIT` | Nhấn mạnh đồng bộ ở commit; tác động của các thay đổi chưa flush tới kết quả query trước commit không được quy định hoàn toàn portable |

Không nên xây logic nghiệp vụ với giả định “`COMMIT` chắc chắn sẽ bỏ qua mọi thay đổi cho tới cuối transaction” hoặc “`AUTO` luôn flush mọi lần gọi query”. Hành vi tối ưu và SQL cụ thể do provider quyết định trong phạm vi hợp đồng JPA.

### 9.4. Transaction không đồng nghĩa persistence context

Hai định nghĩa:

- **Transaction:** đơn vị atomic commit/rollback của các thay đổi dữ liệu.
- **Persistence context:** tập entity instances được quản lý và trạng thái cần đồng bộ.

Có thể có tình huống persistence context tồn tại lâu hơn một transaction, như **extended persistence context** hoặc application-managed EntityManager còn mở. Ngược lại, với transaction-scoped context, vòng đời context thông thường gắn với transaction.

Một transaction chỉ đang “mở” không tự động có nghĩa mọi POJO được tạo trong thread trở thành managed. Chúng vẫn cần đi qua persistence operations hoặc association cascade phù hợp.

## 10. Resource-local EntityManager: ví dụ đầy đủ

Đây là ví dụ JPA SE tự quản lý transaction:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

public final class CustomerService {

    private final EntityManagerFactory emf;

    public CustomerService(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public Long createCustomer(String name, String email) {
        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                Customer customer = new Customer(name, email);

                // New -> Managed.
                em.persist(customer);

                // Đồng bộ sớm để minh họa điểm flush
                // và việc có thể đọc identifier sau flush.
                em.flush();

                Long id = customer.getId();

                tx.commit();
                return id;
            } catch (RuntimeException ex) {
                if (tx.isActive()) {
                    tx.rollback();
                }
                throw ex;
            }
        } finally {
            em.close();
        }
    }

    public void renameCustomer(Long id, String newName) {
        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                Customer customer = em.find(Customer.class, id);
                if (customer == null) {
                    throw new IllegalArgumentException(
                        "Không tìm thấy khách hàng"
                    );
                }

                // Managed entity -> dirty checking.
                customer.rename(newName);

                tx.commit(); // Provider đồng bộ thay đổi.
            } catch (RuntimeException ex) {
                if (tx.isActive()) {
                    tx.rollback();
                }
                throw ex;
            }
        } finally {
            em.close();
        }
    }
}
```

Điểm cần ghi nhớ:

1. Factory được cung cấp từ bên ngoài, thường sống lâu trong ứng dụng.
2. Mỗi phương thức tạo một `EntityManager` phù hợp với đơn vị công việc.
3. `EntityTransaction` dùng cho **resource-local transaction**, không phải cách quản lý JTA container-managed.
4. Entity trong phương thức được managed bởi context của `em` đó.
5. Sau khi `em.close()`, không tiếp tục gọi API của `em`; entity trả ra ngoài (nếu có) không còn được quản lý bởi context đã đóng.
6. Nếu thao tác persistence gặp lỗi dẫn tới rollback, không nên giả định managed state còn phản ánh database một cách an toàn; kết thúc đơn vị công việc và dùng context mới khi cần.

Ví dụ nhằm giải thích vòng đời, không cố gắng bao quát toàn bộ exception hierarchy hoặc transaction retry trong hệ thống production.

## 11. Container-managed EntityManager: những khác biệt thực tế

Trong môi trường Jakarta EE, ứng dụng có thể inject:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.transaction.Transactional;

public class CustomerApplicationService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void renameCustomer(Long id, String newName) {
        Customer customer = em.find(Customer.class, id);
        customer.rename(newName);
    }
}
```

Với môi trường JTA/container phù hợp, transaction được quản lý bởi container. Khi phương thức thành công và transaction được commit, JPA đồng bộ state của managed entity.

Tại đây:

- Code ứng dụng không tạo `EntityManager` mới thủ công cho mỗi call.
- Không gọi `em.getTransaction().begin()` đối với container-managed JTA EntityManager.
- Không gọi `em.close()` trên container-managed EntityManager do container quản lý.
- `@PersistenceContext` cung cấp tham chiếu để tương tác với context được container liên kết theo scope và transaction.

Trong Spring, cơ chế thông dụng là inject `@PersistenceContext` hoặc repository và dùng `@Transactional` của Spring; lifecycle chi tiết do Spring transaction infrastructure điều phối. **Mô hình khái niệm giống nhau**, nhưng không nên trộn các API điều phối transaction của Jakarta EE, Spring và JPA resource-local theo cách tùy ý.

### 11.1. Nhiều service cùng transaction có thể cùng context

Giả sử Service A tải Customer#5 và Service B cũng tải Customer#5 trong **cùng transaction-scoped persistence context**:

```text
Transaction T
   |
   +--> Service A dùng EntityManager proxy
   |       -> find(Customer, 5)
   |       -> managed Customer instance A
   |
   +--> Service B dùng EntityManager proxy
           -> find(Customer, 5)
           -> cùng managed instance A
```

Trong JTA container-managed transaction-scoped context, persistence context có thể được lan truyền giữa các `EntityManager` tham gia cùng persistence unit/transaction theo quy tắc container. Nhờ vậy một transaction có cái nhìn identity thống nhất.

Đừng dựa chỉ vào **tên biến em** để kết luận có context khác nhau. Điều cần xét là scope và transaction mà provider/container đã gắn các thao tác vào.

### 11.2. Scope của context không đồng nhất scope HTTP request

Trong web application:

```text
HTTP request
  -> Controller
  -> Service @Transactional
       -> EntityManager / Persistence Context
       -> Database transaction
  -> DTO response
```

Một transaction thường bao quanh một service method, không nhất thiết toàn bộ request. Nếu response serializer truy cập association lazy sau khi transaction/context đóng, có thể gặp lỗi lazy initialization hoặc làm phát sinh truy vấn ngoài vị trí mong muốn nếu context còn mở.

Nên xác định nhu cầu dữ liệu trong service/query, dùng DTO và fetch plan phù hợp thay vì mặc định mọi entity trả ra API vẫn managed.

## 12. Transaction-scoped và extended persistence context

Một persistence context có thể được quản lý theo nhiều kiểu scope. Phân biệt này giúp giải thích vì sao một entity có thể còn managed hoặc trở thành detached sau transaction.

### 12.1. Transaction-scoped persistence context

Thường gặp trong ứng dụng JTA/container-managed:

```java
@PersistenceContext(
    type = PersistenceContextType.TRANSACTION
)
private EntityManager em;
```

Đây là kiểu mặc định cho nhiều trường hợp injection phù hợp.

Ý nghĩa tổng quan:

- Context được liên kết với transaction.
- Managed entities nằm trong context gắn transaction đó.
- Khi transaction kết thúc, entity không còn được quản lý bởi transaction-scoped context như trước.
- Trong một transaction khác, ứng dụng có thể phải tải lại hoặc merge entity.

Không phải mọi `EntityManager` trong cùng JVM chia sẻ context này; điều kiện là tham gia cùng persistence unit/transaction theo các quy tắc của môi trường.

### 12.2. Extended persistence context

Một **extended persistence context** có thể tồn tại qua **nhiều transaction**, thường được sử dụng trong mô hình hội thoại nghiệp vụ dài (*long-running conversation*) với những thành phần container phù hợp, như stateful session bean.

Một ví dụ khai báo trong môi trường Jakarta EE hỗ trợ:

```java
import jakarta.ejb.Stateful;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.PersistenceContextType;

@Stateful
public class CustomerEditConversation {

    @PersistenceContext(
        type = PersistenceContextType.EXTENDED
    )
    private EntityManager em;

    private Customer editing;

    public void beginEdit(Long customerId) {
        editing = em.find(Customer.class, customerId);
    }

    public void changeName(String name) {
        editing.rename(name);
    }

    // Một business method khác có transaction phù hợp
    // sẽ quyết định thời điểm lưu/commit thay đổi.
}
```

Đây là **mẫu minh họa scope**, không phải workflow production hoàn chỉnh. Không nên tự áp extended context vào một singleton/shared service rồi coi nó thread-safe; extended context có yêu cầu vòng đời, concurrency và transaction association riêng.

Ưu điểm có thể là giữ identity và state qua nhiều bước nhập liệu. Đổi lại:

- Giữ nhiều managed entity lâu hơn, tốn bộ nhớ.
- State có thể stale so với transaction của người dùng khác.
- Có thể làm xung đột optimistic locking xuất hiện khi commit.
- Cần quản lý rõ kết thúc conversation, hủy chỉnh sửa và rollback.
- Không được dùng cùng extended context đồng thời từ nhiều thread như một singleton toàn ứng dụng.

### 12.3. Application-managed context có thể sống qua transaction

Với `EntityManager em = emf.createEntityManager()`, context gắn với `em` tồn tại trong vòng đời `em`, có thể kéo dài qua một số transaction theo cấu hình application-managed. Điều này **không biến mọi thay đổi ngoài transaction thành thao tác ghi database đã được chấp nhận**; phải có transaction và synchronization phù hợp để flush/commit.

Do đó:

> **Thời gian sống của EntityManager, thời gian sống của persistence context và thời gian sống của transaction là ba đường thời gian có thể khác nhau.**

## 13. `merge`: khôi phục state detached mà không quản lý object gốc

Một tình huống phổ biến:

1. Request A tải Customer.
2. Transaction kết thúc; entity trở thành detached.
3. Code sửa Customer detached.
4. Request B muốn lưu trạng thái đó.

Cách sai lầm là nghĩ `merge` sẽ đưa chính object detached trở lại trạng thái managed.

### 13.1. Ví dụ minh họa

```java
Customer detached = ...; // Instance không còn managed.

detached.rename("Tên từ request mới");

Customer managed = em.merge(detached);

System.out.println(detached == managed);
// Không nên kỳ vọng true nếu detached trước đó không managed.

System.out.println(em.contains(detached)); // false.
System.out.println(em.contains(managed));  // true.
```

`merge` sao chép state sang một instance **được context hiện tại quản lý**, rồi trả về instance đó. Object `detached` vẫn detached.

Hình dung:

```text
Detached Customer (object D)
    id = 5
    name = "Tên mới"
          |
          | em.merge(detached)
          | copy state
          v
Managed Customer (object M) trong context
    id = 5
    name = "Tên mới"
          |
          | flush/commit
          v
    UPDATE customer ...
```

Trong một số tình huống entity truyền vào `merge` đã managed, provider có thể xử lý khác. Quy tắc sử dụng an toàn là **lấy giá trị trả về từ `merge` làm managed instance để tiếp tục thao tác**.

### 13.2. Một lỗi phổ biến sau merge

```java
Customer managed = em.merge(detached);

// SAI ý định:
detached.rename("Sửa tiếp sau merge");
// Sửa đối tượng detached gốc, không sửa managed instance.
```

Sửa đúng:

```java
Customer managed = em.merge(detached);
managed.rename("Sửa tiếp trên managed");
```

### 13.3. Merge không thay thế business validation

Từ request API, đừng nhận toàn bộ JSON entity rồi gọi `merge` mà không kiểm soát:

```java
// Rủi ro nếu request chứa field không được phép đổi:
em.merge(customerFromRequest);
```

Có thể vô tình ghi đè dữ liệu không thuộc quyền cập nhật hoặc thay collection/association ngoài ý định. Một kiểu cập nhật thường rõ hơn:

```java
Customer managed = em.find(Customer.class, customerId);
authorization.checkCanEdit(managed, currentUser);
managed.rename(request.newName());
```

Service chỉ sửa những thuộc tính được phép. Với detached graph thực sự cần merge, phải cân nhắc cascade merge, `@Version` và xử lý xung đột dữ liệu.

### 13.4. Entity mới truyền vào merge thì sao?

JPA có thể dùng `merge` với entity new, tạo managed copy mới để persist theo lifecycle. Nhưng khi **muốn tạo mới** một entity có identity được sinh tự động, `persist` thường rõ ý nghĩa hơn, tránh nhầm với cập nhật detached entity. Không nên gọi `merge` như một “upsert” tự động kiểm soát mọi trường hợp tồn tại/không tồn tại ở database.

## 14. `remove`: đánh dấu xóa entity managed

### 14.1. Xóa trong context

```java
Customer customer = em.find(Customer.class, 5L);

if (customer != null) {
    em.remove(customer);
}
```

Sau `remove`, entity bước vào lifecycle removed và provider chuẩn bị xóa row khi đồng bộ transaction.

```text
Managed Customer#5
       |
       | em.remove(customer)
       v
Removed entity trong lifecycle context
       |
       | flush / commit
       v
DELETE FROM customer WHERE id = ...
```

Không nên suy ra SQL chạy ngay ở lệnh `remove`. Thêm nữa, nếu row Customer còn được `PurchaseOrder` tham chiếu, FK/cascade/orphan rules có thể cản xóa hoặc yêu cầu thao tác dọn liên kết trước.

### 14.2. Không truyền detached object trực tiếp cho remove

```java
Customer detached = ...;

em.remove(detached); // Không phải cách xóa portable khi detached.
```

`remove` yêu cầu entity managed theo hợp đồng JPA. Thông thường:

```java
Customer managed =
    em.find(Customer.class, detached.getId());

if (managed != null) {
    em.remove(managed);
}
```

Đặc biệt khi xóa theo ID từ API, không cần merge cả detached graph rồi remove; tìm entity managed, kiểm tra quyền và xóa thường dễ kiểm soát hơn.

### 14.3. Removed state không giống detached state

- **Detached**: entity không còn bị context theo dõi; chỉnh sửa không tự ghi.
- **Removed**: entity đã được yêu cầu xóa theo lifecycle, có thể còn tham gia cơ chế xử lý của context tới thời điểm flush/transaction.

Không coi `em.contains(entity)` là đủ để phân biệt mọi trạng thái lifecycle. Nếu cần suy luận về thao tác đã xảy ra, hãy quản lý logic service rõ ràng thay vì dựa vào cờ trạng thái không được API công khai toàn diện.

## 15. `detach`, `clear` và `close`: ba cách kết thúc quản lý

### 15.1. `detach(entity)` chỉ tách một instance

```java
Customer c1 = em.find(Customer.class, 5L);
Customer c2 = em.find(Customer.class, 9L);

em.detach(c1);

System.out.println(em.contains(c1)); // false.
System.out.println(em.contains(c2)); // true.
```

Sau khi detach, `c1` không còn được theo dõi bởi context này. Nếu association có cascade type `DETACH`, việc detach có thể truyền sang entity liên kết theo mapping, nên không mặc định chỉ một object duy nhất bị ảnh hưởng trong mọi graph.

`detach` hữu ích khi:

- Muốn chủ động ngừng theo dõi một entity lớn.
- Muốn tránh thay đổi kế tiếp trên object đó bị flush.
- Cần xử lý theo lô với bộ nhớ được kiểm soát.
- Muốn minh họa lifecycle để hiểu `merge`.

Nhưng detach **không đồng nghĩa xóa khỏi DB**, và không tự làm mới dữ liệu bên ngoài.

### 15.2. `clear()` tách toàn bộ entity

```java
Customer customer = em.find(Customer.class, 5L);
customer.rename("Tên chưa flush");

em.clear();

System.out.println(em.contains(customer)); // false.
```

`clear()` làm các managed entity trong context bị detach. Những thay đổi pending **chưa được đồng bộ có thể bị mất**, vì context không còn quản lý instance để flush các thay đổi đó.

Vì thế, nếu muốn giữ thay đổi trước khi clear, thường cần:

```java
em.flush(); // Đồng bộ pending SQL trong transaction.
em.clear(); // Tách managed instances.
```

Tuy nhiên, `flush()` rồi `clear()` vẫn chưa phải `commit()`. Nếu transaction rollback sau đó, DB thay đổi vẫn có thể bị hủy.

### 15.3. `close()` đóng application-managed EntityManager

```java
EntityManager em = emf.createEntityManager();

try {
    Customer c = em.find(Customer.class, 5L);
} finally {
    em.close();
}
```

Khi `EntityManager` application-managed được đóng theo lifecycle hợp lệ:

- Không gọi tiếp các thao tác persistence thông thường trên `em` đã đóng.
- Persistence context liên quan không còn được sử dụng để quản lý entity như trước.
- Các instance đang giữ ngoài context sẽ không còn được tự dirty-check bởi context đã đóng.
- Lazy association chưa được khởi tạo có thể không thể tải khi không còn context thích hợp.

Lưu ý: container-managed `EntityManager` là tài nguyên do container quản lý; code ứng dụng không được tùy ý đóng nó như application-managed instance.

### 15.4. So sánh ba thao tác

| Lệnh | Phạm vi tách | EntityManager còn dùng được? | Thay đổi pending |
|---|---|---|---|
| `detach(entity)` | Một entity và phần cascade DETACH phù hợp | Có | Thay đổi chưa flush trên entity bị tách không còn được đồng bộ bởi context này |
| `clear()` | Toàn bộ persistence context | Có | Thay đổi chưa flush có thể mất |
| `close()` | Kết thúc lifecycle application-managed EM/context | Không | Không được dùng thay commit/flush; transaction phải được kết thúc đúng |

Cả ba đều khác `remove`. `remove` có mục tiêu **xóa row**, còn detach/clear/close chủ yếu thay đổi **mối quan hệ quản lý giữa Java object và context**.

## 16. `refresh`: khi state trong context khác database

Giả sử transaction A tải Customer#5. Sau đó transaction B cập nhật tên Customer#5 và commit. Context A vẫn giữ instance với tên cũ.

```java
Customer customer = em.find(Customer.class, 5L);

// Một transaction khác có thể đã cập nhật row tương ứng.

em.refresh(customer);
```

`refresh` yêu cầu nạp lại state entity managed từ database, theo ngữ cảnh/transaction và cơ chế lock/fetch phù hợp.

Cẩn trọng:

- `refresh` có thể **ghi đè những thay đổi cục bộ chưa flush** trên managed entity.
- Nếu row đã biến mất hoặc gặp xung đột/constraint, provider có thể ném exception thích hợp.
- Refresh không phải cơ chế giải quyết mọi concurrency problem.
- Nếu chỉ cần tránh stale data trong một workflow, cần xem transaction isolation, `@Version` và cách thiết kế đơn vị công việc.
- Với quan hệ có cascade `REFRESH`, việc nạp lại có thể lan sang entity liên kết theo mapping.

### 16.1. Ví dụ xung đột với dirty changes

```java
Customer customer = em.find(Customer.class, 5L);
customer.rename("Tên A");

// Việc refresh có thể làm mất sửa đổi "Tên A" chưa flush:
em.refresh(customer);
```

Nếu mục tiêu là lưu “Tên A”, không gọi refresh rồi mong provider tự hòa giải. Nếu mục tiêu là bỏ sửa đổi cục bộ, refresh có thể là một phương án có chủ đích.

### 16.2. Refresh khác clear rồi find

Hai cách:

```java
em.refresh(customer);
```

và:

```java
em.clear();
Customer reloaded = em.find(Customer.class, 5L);
```

khác nhau:

- `refresh` áp dụng cho **managed instance cụ thể**, giữ reference Java của nó ở context.
- `clear` detach **tất cả** managed entities, rồi `find` có thể trả **instance mới**.
- `clear` có thể làm mất các pending changes của nhiều entity khác.
- Cả hai vẫn phải xét transaction, cache/fetch plan và isolation.

Không gọi `clear` chỉ để “refresh một entity” nếu context đang giữ những thay đổi quan trọng ở nhiều entity khác.

## 17. getReference và lazy association vẫn gắn với context

`getReference` có thể trả một tham chiếu tới entity dựa trên ID mà chưa tải đầy đủ row:

```java
Customer customerRef =
    em.getReference(Customer.class, 5L);

PurchaseOrder order = new PurchaseOrder(
    customerRef,
    new BigDecimal("150000.00")
);

em.persist(order);
```

Trong một số provider, sử dụng reference giúp khai báo foreign key mà không cần `SELECT` lấy đầy đủ Customer trước đó. Nhưng:

- Provider có thể chọn truy vấn tại thời điểm lấy reference hoặc khi truy cập thuộc tính.
- Nếu ID không tồn tại, `EntityNotFoundException` hoặc lỗi FK có thể xuất hiện tại thời điểm thích hợp; đừng coi `getReference` là xác nhận entity tồn tại.
- Lazy proxy/reference phụ thuộc vào persistence context đang còn cho phép lấy dữ liệu.
- Kiểm tra quyền truy cập và tính tồn tại theo nghiệp vụ vẫn cần được service thực hiện.

### 17.1. Truy cập association sau khi context đóng

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
em.close();

// Nếu order.customer chưa được tải,
// truy cập customer.name ở đây có thể thất bại.
String name = order.getCustomer().getName();
```

Đây là nguyên nhân phổ biến của lỗi lazy initialization do provider: entity chính đã được đọc nhưng association còn đòi hỏi truy vấn mà context không còn phục vụ.

Giải pháp không phải gọi `persist`/`merge` một cách mù quáng. Nên tổ chức truy vấn với fetch plan thích hợp hoặc chuyển sang DTO trong ranh giới transaction/context còn hoạt động.

### 17.2. Loaded khác managed

Một entity có thể đã có đầy đủ field trong Java nhưng đã detached. Ngược lại, một proxy/entity reference có thể được context quản lý nhưng phần association hoặc một số state chưa tải đủ.

Vì thế cần phân biệt:

- **Managed?** Context có theo dõi instance không?
- **Loaded?** Thuộc tính dữ liệu cần dùng đã được nạp chưa?
- **Database up-to-date?** State có còn phản ánh row hiện tại không?
- **Committed?** Transaction đã xác nhận thay đổi chưa?

Đây là bốn câu hỏi khác nhau.

## 18. Query, projection và managed entity

### 18.1. Entity query trả managed instances

```java
List<Customer> customers = em.createQuery(
    "select c from Customer c where c.name like :prefix",
    Customer.class
)
.setParameter("prefix", "An%")
.getResultList();
```

Kết quả chứa entity instances do persistence context quản lý (khi chạy truy vấn trong điều kiện phù hợp).

```java
for (Customer customer : customers) {
    customer.rename(customer.getName().toUpperCase());
}
```

Nếu transaction cho phép ghi, các thay đổi này có thể được flush. Điều đó vừa là ưu điểm của JPA vừa là rủi ro nếu service chỉ định đọc nhưng vô tình sửa entity.

### 18.2. Scalar và DTO query không tạo managed result entities

```java
List<String> names = em.createQuery(
    "select c.name from Customer c",
    String.class
).getResultList();
```

`names` là các chuỗi, không phải entity managed.

Với DTO:

```java
List<CustomerSummary> summaries = em.createQuery(
    """
    select new com.example.persistence.CustomerSummary(c.id, c.name)
    from Customer c
    """,
    CustomerSummary.class
).getResultList();
```

`summaries` không được dirty-check. Dù query chạy trong cùng EntityManager, tạo một record/DTO không mặc nhiên đăng ký nó vào persistence context.

### 18.3. EntityManager không giữ mọi row query lại mãi theo một cấu trúc công khai

Persistence context thường giữ các entity đã load/managed, khiến bộ nhớ tăng theo số entity. Nhưng JPA không có API chuẩn kiểu:

```java
List<Object> allManagedEntities = em.getAllManagedEntities();
```

API đó **không tồn tại** trong JPA chuẩn. Nếu cần thống kê internals, provider có thể có API riêng, nhưng không nên phụ thuộc vào cấu trúc nội bộ để thực hiện nghiệp vụ.

### 18.4. Bulk update/delete bỏ qua state đang managed

Ví dụ:

```java
int changed = em.createQuery(
    """
    update Customer c
    set c.name = :name
    where c.email like :domain
    """
)
.setParameter("name", "Unknown")
.setParameter("domain", "%@example.com")
.executeUpdate();
```

Bulk JPQL update hoạt động trực tiếp trên database theo quy tắc query và **không tự đồng bộ state của các managed Customer đã load** như một vòng lặp gọi setter. Điều này có thể khiến persistence context còn dữ liệu cũ.

Với bulk operation, ứng dụng cần quản lý ranh giới context, refresh/clear hoặc quy trình đọc lại phù hợp. Nếu entity có `@Version`, bulk update cũng không tự áp dụng toàn bộ ý nghĩa optimistic locking giống entity-level update; cần xử lý version thủ công/khác theo nghiệp vụ nếu cần.

## 19. Quan hệ entity: context quản lý các instance chứ không chỉ một bảng

Một persistence context có thể chứa entity của nhiều loại:

```text
Persistence Context:
    Customer#5  ------------+
        |                   |
        +-- orders          v
                      PurchaseOrder#27
                              |
                              +-- customer -> Customer#5
```

Nếu association được tải và trỏ tới Customer#5, JPA dùng cùng managed identity của Customer trong context.

Ví dụ:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
Customer customer = em.find(Customer.class, customerId);

// Nếu order.customer tham chiếu cùng identity Customer,
// provider quản lý relationship với managed identity đó.
```

Có hai vấn đề riêng:

1. **Object identity/management:** context nhận diện Customer#5 thống nhất.
2. **Mapping ownership:** thuộc tính `PurchaseOrder.customer` giữ FK `customer_id` và quyết định liên kết khi ghi.

JPA không tự giữ mọi tham chiếu Java của hai chiều luôn đồng bộ nếu code chỉ sửa một phía. Với quan hệ hai chiều, ứng dụng nên tạo helper method để cập nhật owning và inverse side. Persistence context giải quyết quản lý entity identity và state, **không thay thế mọi business invariant của object graph**.

### 19.1. Cascade có thể mở rộng tập managed entity

Nếu `persist` một aggregate root có cascade `PERSIST` tới các entity liên quan, context có thể nhận quản lý nhiều instance. Với `merge`, cascade `MERGE` có thể sao chép state của một graph sâu.

Không nên bật `CascadeType.ALL` trên mọi association chỉ vì muốn “mọi thứ được quản lý”. Đặc biệt với `@ManyToMany` giữa các entity độc lập, cascade `REMOVE` có thể khiến xóa nhầm entity đích đang được tham chiếu nhiều nơi.

### 19.2. Provider giữ tham chiếu nên bộ nhớ có thể tăng

Một context tải 50.000 Customer và các PurchaseOrder liên kết có thể giữ rất nhiều instance, snapshot và collection wrapper. Garbage collector không thể giải phóng những object còn được context tham chiếu theo cách thông thường.

Vì thế, khi xử lý số lượng lớn, cần cân nhắc streaming/paging, flush/clear theo lô, projection hoặc cách xử lý chuyên dụng.

## 20. Xử lý theo lô và quản lý kích thước persistence context

### 20.1. Rủi ro khi persist hàng chục nghìn entity

Ví dụ đơn giản:

```java
for (int i = 0; i < 100_000; i++) {
    em.persist(new Customer(
        "Customer " + i,
        "customer" + i + "@example.com"
    ));
}
```

Ngay cả khi JDBC batching được cấu hình, persistence context có thể giữ lượng lớn managed instances. Ngoài entity, provider còn phải quản lý identity, snapshot và pending operations.

Bộ nhớ và thời gian flush có thể tăng dần, nhất là khi mỗi entity có nhiều association.

### 20.2. Flush và clear theo batch

Một hướng với application-managed EntityManager trong transaction:

```java
int batchSize = 100;

for (int i = 1; i <= 10_000; i++) {
    Customer customer = new Customer(
        "Customer " + i,
        "bulk" + i + "@example.com"
    );
    em.persist(customer);

    if (i % batchSize == 0) {
        em.flush();
        em.clear();
    }
}

em.flush();
em.clear();
```

Ý nghĩa:

- `flush` gửi thay đổi chờ tới database.
- `clear` giải phóng việc quản lý các instance, giúp hạn chế kích thước context.
- Cuối vòng lặp vẫn flush cho batch còn lại nếu tổng số không chia hết.
- Đoạn code giả định **transaction đang mở**; cần commit hoặc rollback bằng cơ chế transaction phù hợp bên ngoài.

Nhưng có các giới hạn:

- `clear` detach mọi entity, kể cả những entity khác đang được service cần tiếp tục sử dụng.
- Không nên giữ reference tới entity đã detach rồi sửa nó và kỳ vọng tự ghi.
- Nếu cascade/association giữa các batch phức tạp, cần quản lý identity và thứ tự ghi cẩn thận.
- IDENTITY generation có thể hạn chế khả năng batching INSERT trên một số provider/database.
- Một transaction quá lớn vẫn có thể gây áp lực transaction log/locking; flush/clear **không rút ngắn transaction**.
- Nếu dữ liệu cho phép, có thể chia thành nhiều transaction rõ ràng theo batch để giảm tải, nhưng phải chấp nhận semantics commit từng phần.

### 20.3. Paging và projection cho tác vụ đọc

Thay vì:

```java
List<Customer> all = em.createQuery(
    "select c from Customer c",
    Customer.class
).getResultList();
```

có thể phân trang và chỉ chọn các cột cần xử lý, hoặc dùng DTO projection nếu không cần dirty checking.

Ví dụ:

```java
List<CustomerSummary> page = em.createQuery(
    """
    select new com.example.persistence.CustomerSummary(c.id, c.name)
    from Customer c
    order by c.id
    """,
    CustomerSummary.class
)
.setFirstResult(0)
.setMaxResults(100)
.getResultList();
```

Query DTO không thêm mỗi record vào persistence context như entity managed. Nếu cần xử lý hàng triệu row, pagination chiến lược keyset/streaming có thể phù hợp hơn offset lớn, tùy database và provider.

## 21. EntityManager không thread-safe và không nên dùng như singleton

Một lỗi nghiêm trọng:

```java
public class UnsafeSharedService {
    private static EntityManager em; // Không nên chia sẻ như thế.
}
```

`EntityManager` và persistence context thường có mutable state. Chia sẻ một application-managed EntityManager giữa các request/thread có thể dẫn tới:

- Các thao tác `persist`, `remove`, `clear` đè lên state của nhau.
- Managed entities giữa request bị lẫn trạng thái.
- Lỗi do transaction association không đúng thread.
- Dữ liệu stale hoặc không nhất quán.
- Tranh chấp connection/resource và exception khó dự đoán.

**`EntityManagerFactory` mới là thành phần có thể chia sẻ** giữa các thread theo thiết kế. EntityManager/context nên được sử dụng trong đơn vị công việc và phạm vi concurrency được container/framework hỗ trợ.

### 21.1. Inject EntityManager vào singleton service có luôn sai?

Không nhất thiết. Trong Spring/Jakarta EE, thứ được inject có thể là **proxy/reference do framework quản lý**, định tuyến thao tác tới EntityManager/context phù hợp với transaction/thread. Điều này khác hoàn toàn việc tự tạo:

```java
private final EntityManager em = emf.createEntityManager();
```

rồi dùng instance đó cho mọi request trong singleton.

Vì vậy phải phân biệt **application-managed EntityManager instance** với **container/framework-managed injected proxy**, không kết luận chỉ từ kiểu field Java.

### 21.2. Tránh dùng entity managed như global cache

Một managed entity không nên được giữ làm singleton hoặc đưa vào global `Map<Long, Customer>` để nhiều request sửa trực tiếp. Khi context cũ đóng, nó thành detached; khi context vẫn mở lâu, lại gây leak và concurrency problem.

Nếu cần cache thông tin khách hàng, dùng DTO bất biến hoặc cache application có chính sách invalidation rõ ràng; không mặc định tận dụng JPA managed entity như global mutable cache.

## 22. Optimistic locking và sự khác biệt giữa context với database

### 22.1. Hai EntityManager độc lập cập nhật cùng row

Giả sử:

```text
Customer id = 5
name    = "An"
version = 3
```

Hai transaction:

```text
Transaction A / PC-A             Transaction B / PC-B
----------------------------     ----------------------------
Load Customer#5, version 3       Load Customer#5, version 3
Rename "An A"                    Rename "An B"
Flush/commit                     Flush/commit
DB version tăng lên 4            Version 3 không còn phù hợp
                                 -> optimistic conflict
```

Mỗi context quản lý **một Java instance riêng** cho Customer#5. Identity map chỉ bảo đảm nhất quán **trong từng context**, không khóa toàn bộ các transaction khác.

Với `@Version`:

```java
@Version
private long version;
```

JPA provider có thể phát hiện cập nhật stale và ném `OptimisticLockException` khi flush hoặc commit thích hợp. Ứng dụng cần xử lý xung đột bằng báo lỗi, tải lại, retry có kiểm soát hoặc quy tắc hòa giải dữ liệu.

### 22.2. Nếu không có `@Version`

Không có version, tùy transaction isolation và provider, hai cập nhật có thể gây **lost update** hoặc một transaction ghi đè kết quả của transaction khác. Persistence context không tự bảo đảm mọi cập nhật đồng thời an toàn.

Cần chọn cơ chế concurrency thích hợp:

- Optimistic locking (`@Version`).
- Pessimistic locking trong những use case cần thiết.
- Ràng buộc database/unique/FK.
- Transaction isolation phù hợp.
- API semantics và conflict resolution.

### 22.3. `refresh` không thay thế xử lý concurrency

Nếu một user đang chỉnh sửa một form dài, gọi `refresh` trước khi lưu có thể làm mất state đang sửa. Nếu muốn kiểm tra có dữ liệu mới, dùng version/ETag hoặc cơ chế phù hợp rồi cho user quyết định.

**Identity trong một context** và **đồng bộ giữa những người dùng** là hai vấn đề khác nhau.

## 23. Unsynchronized persistence context: kiến thức mở rộng

JPA có `SynchronizationType` cho việc quản lý sự đồng bộ giữa context và JTA transaction trong những trường hợp được hỗ trợ.

Ví dụ ở môi trường container:

```java
@PersistenceContext(
    synchronization = SynchronizationType.UNSYNCHRONIZED
)
private EntityManager em;
```

Một unsynchronized persistence context có thể giữ managed entities nhưng **chưa tự tham gia việc đồng bộ vào transaction** cho tới khi được yêu cầu join theo quy tắc JPA:

```java
em.joinTransaction();
```

Các điểm quan trọng:

- **Managed không đồng nghĩa được phép flush ngay** khi context chưa join transaction cần thiết.
- `joinTransaction()` là thao tác tham gia JTA transaction hiện tại; không thay thế việc mở/commit transaction.
- Ngữ nghĩa transaction scope và khả năng sử dụng unsynchronized context phụ thuộc môi trường JTA/container.
- Đây là tính năng nâng cao, không phải cách mặc định để tắt dirty checking hoặc tránh flush trong ứng dụng CRUD thông thường.

Từ đây có thêm một cấp phân biệt:

```text
Entity managed?          -> Persistence context quản lý instance?
Context synchronized?    -> Có tham gia JTA transaction để flush?
Transaction committed?   -> DB đã xác nhận thay đổi?
```

Ba câu trả lời có thể khác nhau. Điều đó cho thấy vì sao không thể đồng nhất EntityManager, context và transaction.

## 24. Những nhầm lẫn thường gặp

### 24.1. “EntityManager chính là database connection”

**Sai.** EntityManager là JPA API gắn với persistence context. Provider có thể mượn/giải phóng JDBC connection theo thời điểm transaction và connection management, không bắt buộc giữ đúng một connection xuyên suốt vòng đời của mọi EntityManager.

### 24.2. “Có ID là entity managed”

**Sai.** Managed state phụ thuộc persistence context. Một DTO, detached entity hoặc POJO có ID vẫn không tự được quản lý.

### 24.3. “Hai lần find trong hai EntityManager luôn trả cùng Java object”

**Sai.** Identity map chỉ có phạm vi persistence context. Hai context độc lập có thể trả hai Java instances cùng ID.

### 24.4. “`find` luôn query database”

**Sai.** Nếu entity đã managed trong context, `find` có thể dùng lại instance. Nhưng một query JPQL mới vẫn có thể cần SQL để xác định result set.

### 24.5. “`persist` chạy INSERT ngay”

**Không luôn đúng.** SQL có thể đợi flush/commit hoặc chạy sớm vì ID generation/constraint/provider. Đừng dựa vào một thời điểm SQL cố định.

### 24.6. “Sửa setter xong phải gọi `save/update`”

**Không đối với managed entity thông thường.** Dirty checking cho phép provider đồng bộ state trong transaction. Nếu object detached, câu chuyện khác.

### 24.7. “`merge` biến object truyền vào thành managed”

**Sai.** `merge` trả về managed instance. Object detached gốc vẫn detached.

### 24.8. “`remove` có thể nhận bất kỳ object có ID”

**Không portable.** Phải dùng managed entity hoặc thao tác chuyển/tìm instance managed phù hợp.

### 24.9. “`flush` tương đương `commit`”

**Sai.** Flush gửi thay đổi tới database trong transaction; commit xác nhận transaction. Flush xong vẫn có thể rollback.

### 24.10. “`clear` chỉ xóa cache, không ảnh hưởng cập nhật chờ”

**Sai.** Clear làm detach các entity, và thay đổi chưa flush có thể mất. Cần cân nhắc flush trước khi clear nếu phải lưu pending changes.

### 24.11. “`close` xóa các row tương ứng”

**Sai.** Close kết thúc lifecycle của EntityManager, không phải thao tác xóa entity. `remove` mới diễn đạt ý định delete.

### 24.12. “Entity managed luôn phản ánh dữ liệu mới nhất ở DB”

**Sai.** Có thể stale sau khi transaction khác cập nhật. Cần hiểu isolation, refresh và concurrency control.

### 24.13. “Mọi object liên kết đều tự thành managed”

**Sai.** Cascade và operation semantics quyết định entity nào được quản lý; object graph Java không tự biến mọi POJO thành persistent entity.

### 24.14. “DTO trả về từ JPQL cũng được dirty-check”

**Sai.** DTO/scalar result không phải entity managed. Chúng không tham gia persistence context theo nghĩa entity lifecycle.

### 24.15. “EntityManager thread-safe vì inject vào service singleton”

**Sai về cách suy luận.** Một application-managed EM không thread-safe. Inject proxy của framework có thể hoạt động an toàn nhờ điều phối context theo transaction/thread, không phải vì EM instance tự thread-safe.

### 24.16. “Lazy proxy có thể tải sau khi context đóng trong mọi trường hợp”

**Sai.** Truy cập dữ liệu chưa loaded có thể thất bại khi không còn context/session phù hợp.

### 24.17. “Bulk JPQL update sửa cả các managed object đang có”

**Sai.** Bulk DML không tự đồng bộ state đã managed như setter bình thường; cần refresh/clear hoặc phối hợp ranh giới context.

### 24.18. “Extended context là cách dùng EntityManager toàn cục không cần transaction”

**Sai.** Extended scope giữ context qua nhiều transaction nhưng vẫn phải tuân thủ JTA, concurrency, synchronization và lifecycle. Nó không phải global thread-safe session.

### 24.19. “Có persistence context thì không cần `@Version`”

**Sai.** Identity map giải quyết identity trong một context; version giúp phát hiện xung đột giữa các transaction/context độc lập.

## 25. Bảng quyết định theo thao tác

| Tình huống | Cách tiếp cận phù hợp | Lý do |
|---|---|---|
| Tạo Customer mới | `new` rồi `em.persist` trong transaction | Đưa instance mới vào managed lifecycle |
| Sửa Customer đã `find` trong transaction | Gọi phương thức nghiệp vụ trên managed instance | Dirty checking đồng bộ state |
| Có entity detached cần merge | `Customer managed = em.merge(detached)` | Nhận managed copy để tiếp tục thao tác |
| Xóa entity theo ID | `find` managed, kiểm tra quyền, `remove` | Xóa theo lifecycle đúng |
| Muốn dừng theo dõi một instance | `detach` | Không còn dirty-check instance đó |
| Muốn dừng theo dõi toàn bộ | `flush` khi cần, rồi `clear` | Tránh mất pending changes ngoài ý định |
| Kết thúc một application-managed EM | `close` sau xử lý transaction phù hợp | Giải phóng lifecycle resource |
| State đã cũ so với DB | `refresh` có chủ đích | Nạp lại managed state, có thể ghi đè local changes |
| Chỉ cần dữ liệu hiển thị | DTO/scalar projection | Không cần hydrate managed entities đầy đủ |
| Đọc nhiều entity số lượng lớn | Paging/projection hoặc flush-clear batch phù hợp | Kiểm soát memory và query |
| Đồng thời nhiều request | Mỗi unit of work/context phù hợp | Tránh chia sẻ EM mutable |
| Hai người sửa cùng row | `@Version`/locking phù hợp | Context riêng không tự ngăn lost update |
| Cần association lazy | Fetch plan hoặc DTO trong transaction | Tránh truy cập ngoài context |
| Có quan hệ hai chiều | Helper sửa owning + inverse side | Duy trì object graph và FK nhất quán |

## 26. Bài tập thực hành có lời giải gợi ý

### Bài 1: Hai biến và một identity

```java
Customer a = em.find(Customer.class, 8L);
Customer b = em.find(Customer.class, 8L);
```

**Câu hỏi:** Trong một persistence context, `a == b` có đúng không? Nếu gọi từ hai EntityManager độc lập thì sao?

**Gợi ý:** Trong cùng context, một persistent identity tương ứng một managed instance, nên `a == b` là true nếu entity tồn tại. Ở hai context độc lập, Java reference không bắt buộc giống nhau; thường là hai object khác nhau.

### Bài 2: Managed nhưng chưa commit

```java
Customer customer = new Customer("Bình", "binh@example.com");
em.persist(customer);
boolean managed = em.contains(customer);
```

**Câu hỏi:** Có thể kết luận row đã commit vào database chỉ từ `managed == true` không?

**Gợi ý:** Không. Entity managed là trạng thái context; SQL có thể chưa flush và transaction chưa commit.

### Bài 3: Sửa entity đã được find

```java
Customer c = em.find(Customer.class, 5L);
c.rename("Tên mới");
```

**Câu hỏi:** Vì sao không có `em.update(c)` nhưng tên có thể được lưu?

**Gợi ý:** JPA dirty checking đối với managed entity. Khi transaction được đồng bộ/commit, provider có thể phát `UPDATE`.

### Bài 4: Merge detached

```java
Customer d = detachedCustomer;
Customer m = em.merge(d);

d.rename("Tên cuối");
```

**Câu hỏi:** Câu rename cuối có chắc được lưu không?

**Gợi ý:** Không. `d` vẫn detached; nên tiếp tục sửa `m` là instance managed trả về từ `merge`.

### Bài 5: Clear trước flush

```java
Customer c = em.find(Customer.class, 5L);
c.rename("Cần lưu");
em.clear();
```

**Câu hỏi:** Điều gì có thể xảy ra?

**Gợi ý:** Nếu thay đổi chưa được flush, clear làm entity detach và thay đổi pending có thể mất. Nếu cần giữ, flush trong transaction phù hợp trước khi clear.

### Bài 6: Flush không phải commit

```java
c.rename("A");
em.flush();
tx.rollback();
```

**Câu hỏi:** Database có nhất thiết giữ tên “A” không?

**Gợi ý:** Không. Flush gửi SQL trong transaction; rollback hủy các thay đổi database trong transaction đó.

### Bài 7: Query entity so với projection

```java
List<Customer> entities = em.createQuery(
    "select c from Customer c", Customer.class
).getResultList();

List<String> names = em.createQuery(
    "select c.name from Customer c", String.class
).getResultList();
```

**Câu hỏi:** Kết quả nào chứa managed entity?

**Gợi ý:** `entities`. `names` chỉ là scalar strings, không được dirty-check.

### Bài 8: Tải entity sau khi context đóng

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 10L);
em.close();

String name = order.getCustomer().getName();
```

**Câu hỏi:** Vì sao có thể xảy ra lỗi?

**Gợi ý:** `order.customer` có thể là LAZY association chưa loaded. Không còn persistence context phù hợp để lấy dữ liệu. Dùng query/fetch plan/DTO khi còn context.

### Bài 9: Hai transaction cùng sửa

Transaction A và B cùng đọc Customer#5 version 1. A commit trước. B tiếp tục commit giá trị cũ.

**Câu hỏi:** Identity map có ngăn conflict này không?

**Gợi ý:** Không. Hai context có instance riêng. `@Version`/optimistic locking có thể phát hiện xung đột; cần xử lý retry/hòa giải.

### Bài 10: Batch 10.000 records

Một service tạo 10.000 Customer trong một transaction mà không clear context.

**Câu hỏi:** Nguy cơ về resource và một biện pháp phù hợp?

**Gợi ý:** Context có thể giữ nhiều managed instances/snapshot, tăng heap và chi phí flush. Có thể flush + clear theo batch hoặc dùng giải pháp bulk thích hợp, đồng thời cân nhắc chia transaction và IDENTITY generation.

### Bài 11: Persistence context và entity graph

Một Service A tải Customer#5. Service B trong cùng transaction-scoped context query Customer#5 và liên kết PurchaseOrder.

**Câu hỏi:** Có hai managed Customer objects cùng ID không?

**Gợi ý:** Trong cùng context, không. Query có thể chạy SQL mới nhưng entity cùng identity phải được thống nhất về managed Java instance.

### Bài 12: Bulk update làm stale context

```java
Customer c = em.find(Customer.class, 5L);

em.createQuery(
    "update Customer c set c.name = 'Unknown' where c.id = 5"
).executeUpdate();

String name = c.getName();
```

**Câu hỏi:** `name` chắc chắn là `Unknown` không?

**Gợi ý:** Không. Bulk JPQL không cập nhật managed instance đã có như setter bình thường. Có thể phải refresh/clear hoặc tổ chức transaction mới để nhìn state được đồng bộ.

### Bài 13: EntityManager có phải singleton không?

Một web service tự tạo `EntityManager em = emf.createEntityManager()` trong constructor singleton và tái sử dụng qua nhiều request.

**Câu hỏi:** Có an toàn không?

**Gợi ý:** Không. Application-managed EntityManager không thread-safe; cần quản lý scope per-unit-of-work hoặc dùng proxy/container-managed phù hợp.

### Bài 14: Detached có ID nhưng `contains` false

```java
Customer d = ...; // id = 5, detached.
boolean result = em.contains(d); // false.
Customer m = em.find(Customer.class, 5L);
```

**Câu hỏi:** Vì sao `d` và `m` có cùng ID mà `contains(d)` vẫn false?

**Gợi ý:** `contains` kiểm tra **Java instance d** thuộc current context hay không. `m` là managed instance của context; `d` vẫn detached.

### Bài 15: Refresh khi có thay đổi cục bộ

```java
Customer c = em.find(Customer.class, 5L);
c.rename("Đang nhập");
em.refresh(c);
```

**Câu hỏi:** Người dùng có thể mất thay đổi nào?

**Gợi ý:** `refresh` nạp lại DB state và có thể ghi đè “Đang nhập” chưa flush. Cần xử lý chủ đích thay vì refresh vô điều kiện.

## 27. Tổng kết: bốn câu hỏi trước mỗi thao tác JPA

Khi debug một entity, hãy tự hỏi:

1. **Instance này có managed trong persistence context hiện tại không?** Kiểm tra lifecycle, `em.contains` khi thích hợp, và xem nó đến từ `find`, `persist` hay `merge`.
2. **Persistence context còn hoạt động và được liên kết transaction phù hợp không?** Một reference đã detached hoặc context không joined transaction sẽ không hành xử như managed entity đang tham gia ghi dữ liệu bình thường.
3. **Thay đổi đã được flush và commit chưa?** Java state, SQL đã gửi và dữ liệu đã xác nhận là ba giai đoạn khác nhau.
4. **Có ai khác thay đổi cùng dữ liệu trong context/transaction khác không?** Identity map không đảm bảo cập nhật mới nhất trên mọi context; cần `@Version`, locking hoặc refresh theo yêu cầu.

Bảng ghi nhớ cuối:

| Khái niệm | Câu hỏi nó trả lời |
|---|---|
| `EntityManager` | Ứng dụng thao tác JPA bằng API nào? |
| Persistence context | Entity instance nào đang được quản lý, theo dõi và thống nhất identity? |
| Managed entity | Sửa object này có thể được dirty-check và flush không? |
| Detached entity | Object có còn được context hiện tại theo dõi không? |
| `persist` | Đưa object mới vào quản lý như thế nào? |
| `find` | Tìm entity và tái sử dụng managed identity ra sao? |
| `merge` | Sao chép state vào managed instance nào? |
| `remove` | Đánh dấu xóa managed entity nào? |
| `flush` | Khi nào đồng bộ state từ context sang SQL? |
| `commit` / `rollback` | Database xác nhận hay hủy transaction? |
| `detach` / `clear` / `close` | Khi nào entity rời phạm vi quản lý? |
| `refresh` | Làm thế nào nạp lại state từ database? |
| `@Version` | Phát hiện xung đột cập nhật giữa các context ra sao? |
| `EntityManagerFactory` | Thành phần nào tạo và cấu hình các EntityManager? |

**Kết luận:** Mối liên hệ giữa `EntityManager` và tập entity được quản lý là nền tảng của JPA. `EntityManager` mở ra các thao tác persistence, còn **persistence context duy trì identity và lifecycle của những entity managed**, theo dõi thay đổi và điều phối đồng bộ trong transaction. Khi phân biệt rõ *managed* với *detached*, *flush* với *commit* và *context* với *transaction*, ta có thể giải thích được vì sao có lúc đổi field là tự lưu, có lúc đổi lại không lưu; vì sao `merge` trả object khác; và vì sao một entity chỉ được bảo đảm cùng Java instance **trong phạm vi một persistence context**, chứ không phải trong toàn bộ ứng dụng.
