# Các thuật ngữ cốt lõi và trình tự học JPA

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Nền tảng ORM

Khi mới học JPA, khó khăn thường không nằm ở cú pháp `@Entity` hay `@Id` mà ở việc phân biệt **đối tượng Java**, **bản ghi trong cơ sở dữ liệu**, **trạng thái được quản lý** và **thời điểm SQL thực sự chạy**. Bài này xây dựng hệ thuật ngữ chung, giải thích cách chúng kết nối với nhau, rồi đề xuất trình tự thực hành từ SQL/JDBC đến JPA thuần và Spring Data JPA.

## 1. Sau bài học, bạn cần hiểu gì?

Bạn nên có thể:

- Phân biệt ORM, JPA/Jakarta Persistence, Hibernate, JDBC và Spring Data JPA; xác định vai trò của từng lớp.
- Giải thích `Entity`, `EntityManager`, `persistence context`, `transaction`, `flush` và `dirty checking` trong một thao tác ghi dữ liệu.
- Nhận diện bốn trạng thái chính của entity: transient/new, managed, detached và removed.
- Đọc được mapping đơn giản giữa class–table, field–column và quan hệ đối tượng–khóa ngoại.
- Giải thích JPQL truy vấn đối tượng ra sao, vì sao xuất hiện lazy loading và vấn đề N+1.
- Biết nên học và thực hành khái niệm nào trước khi chuyển sang repository của Spring Data JPA.

**Điểm xuất phát:** cần biết Java cơ bản (class, constructor, object, collection, exception), SQL cơ bản (`SELECT`, `INSERT`, `UPDATE`, `DELETE`, `JOIN`) và khái niệm khóa chính/khóa ngoại. Nếu thiếu phần này, nên bổ sung trước vì JPA vẫn vận hành trên một cơ sở dữ liệu quan hệ.

## 2. Bức tranh tổng thể: từ Java object đến hàng dữ liệu

Một ứng dụng Java cần lưu đối tượng `Customer` vào bảng `customers`. Nếu dùng JDBC trực tiếp, lập trình viên thường phải tự mở kết nối, viết SQL, gán tham số và chuyển `ResultSet` thành object. ORM (Object–Relational Mapping) cung cấp cơ chế mô tả cách đối tượng ánh xạ sang dữ liệu quan hệ và hỗ trợ thực hiện phần công việc lặp lại ấy.

```text
Ứng dụng Java (business logic)
             |
             v
JPA API: EntityManager, annotation, JPQL...
             |
             v
JPA provider: Hibernate / EclipseLink / ...
             |  ánh xạ object <-> table,
             |  theo dõi thay đổi, xây SQL
             v
JDBC driver và kết nối cơ sở dữ liệu
             |
             v
RDBMS: PostgreSQL / MySQL / Oracle / ...
     bảng, cột, khóa, index, transaction
```

Đường đi trên mang tính khái niệm: nhà cung cấp JPA có thể tích hợp thêm cache, connection pool hoặc công cụ khác, nhưng **cơ sở dữ liệu quan hệ vẫn chịu trách nhiệm lưu trữ và thực thi SQL**. ORM không thay thế kiến thức về SQL, transaction, index hay thiết kế bảng.

### 2.1. Phân biệt những tên gọi dễ nhầm

| Thuật ngữ | Bản chất | Khi nào cần quan tâm? |
|---|---|---|
| **JDBC** (Java Database Connectivity) | API Java cấp thấp để gửi SQL và xử lý kết quả qua driver | Khi cần hiểu SQL, connection, transaction và chi phí truy vấn |
| **ORM** | Kỹ thuật ánh xạ đối tượng và dữ liệu quan hệ | Khi mô hình Java không trùng một-một với bảng |
| **JPA** (Java Persistence API) | Tên quen thuộc của chuẩn/API persistence trong hệ Java | Khi học annotation, EntityManager, JPQL và vòng đời entity |
| **Jakarta Persistence** | Tên hiện hành của đặc tả tiếp nối JPA; namespace hiện đại là `jakarta.persistence` | Khi sử dụng Jakarta EE và Spring Boot 3+ |
| **Hibernate ORM** | Một implementation/provider phổ biến của Jakarta Persistence, đồng thời có API riêng | Khi xem SQL thực tế, cấu hình provider hoặc khả năng mở rộng Hibernate |
| **EclipseLink** | Một provider khác của đặc tả Persistence | Khi cần hiểu ứng dụng theo chuẩn không phụ thuộc một provider |
| **Spring Data JPA** | Lớp hỗ trợ repository, truy vấn, phân trang dựa trên JPA | Sau khi đã hiểu persistence context và transaction |
| **Flyway/Liquibase** | Công cụ quản lý phiên bản thay đổi schema (migration) | Khi schema phải phát triển ổn định qua nhiều môi trường |

Về phiên bản, tài liệu cũ thường dùng `javax.persistence.*`, còn hệ Jakarta hiện đại dùng `jakarta.persistence.*`. Đừng trộn hai namespace trong cùng một cấu hình nếu các dependency không tương thích. Trong bài này, mã minh họa dùng `jakarta.persistence`.

**Mô hình dễ nhớ:** *JPA là hợp đồng; Hibernate là một bên thực hiện hợp đồng; Spring Data JPA là lớp giúp gọi hợp đồng thuận tiện hơn*. Viết method trong `JpaRepository` không có nghĩa repository tự loại bỏ quy tắc lifecycle, lazy loading hay transaction của JPA.

## 3. Bảng thuật ngữ cốt lõi

### 3.1. Mô hình và ánh xạ dữ liệu

| Thuật ngữ | Ý nghĩa thực hành |
|---|---|
| **Entity** | Đối tượng Java thuộc kiểu được đánh dấu `@Entity`, có định danh và được JPA quản lý vòng đời |
| **Entity class** | Lớp mô tả kiểu entity; không phải mọi instance của lớp đều đang được quản lý |
| **Table / Row / Column** | Bảng / bản ghi / cột trong cơ sở dữ liệu, nơi dữ liệu được lưu |
| **Mapping** | Quy tắc nối class với table, thuộc tính với column, quan hệ với khóa ngoại hoặc bảng liên kết |
| **Primary key (PK)** | Giá trị định danh duy nhất của một hàng trong bảng |
| **Foreign key (FK)** | Cột/ràng buộc trỏ đến khóa của bảng khác, duy trì toàn vẹn tham chiếu |
| **Identifier** | Giá trị định danh entity (`@Id`), dùng để tìm một entity trong persistence context và database |
| **Basic attribute** | Thuộc tính có thể lưu bằng kiểu cột cơ bản như chuỗi, số, ngày/giờ |
| **Embeddable / Value object** | Kiểu giá trị được nhúng vào entity qua `@Embeddable` và `@Embedded`, thường không có định danh riêng |
| **Association** | Quan hệ giữa các entity, như many-to-one hoặc one-to-many |
| **Owning side** | Phía mapping kiểm soát cách ghi liên kết xuống database, thường là phía giữ khóa ngoại |
| **Schema** | Cấu trúc bảng, cột, kiểu dữ liệu, constraint và index của cơ sở dữ liệu |

### 3.2. Quản lý đối tượng và giao dịch

| Thuật ngữ | Ý nghĩa thực hành |
|---|---|
| **Persistence unit** | Tập hợp cấu hình và entity class thuộc một đơn vị làm việc JPA |
| **EntityManagerFactory** | Đối tượng tạo `EntityManager`; thường tạo dùng chung vì chi phí khởi tạo lớn và được thiết kế để dùng đồng thời |
| **EntityManager** | API thao tác với entity và persistence context; không dùng chung một instance tùy tiện giữa các thread |
| **Persistence context** | Vùng quản lý entity, giữ identity map và theo dõi thay đổi của các entity managed |
| **First-level cache** | Bộ nhớ theo persistence context, giúp cùng một định danh trong cùng context ánh xạ đến cùng managed instance |
| **Transaction** | Ranh giới commit/rollback bảo đảm một nhóm thao tác nhất quán theo khả năng database |
| **Dirty checking** | Provider phát hiện thuộc tính của managed entity đã đổi để sinh SQL cập nhật khi đồng bộ |
| **Flush** | Đồng bộ các thay đổi đang chờ từ persistence context sang database qua SQL; chưa đồng nghĩa commit |
| **Commit / Rollback** | Xác nhận / hủy các thay đổi của một transaction |
| **Cascade** | Truyền một số thao tác persistence từ entity nguồn sang entity liên quan |
| **Orphan removal** | Xóa entity con khi nó bị tách khỏi quan hệ cha–con được cấu hình `orphanRemoval=true` |
| **Optimistic locking** | Kiểm soát xung đột cập nhật bằng phiên bản, thường dùng `@Version` |

### 3.3. Truy vấn và tối ưu

| Thuật ngữ | Ý nghĩa thực hành |
|---|---|
| **JPQL** | Ngôn ngữ truy vấn theo entity và tên thuộc tính Java, được provider chuyển thành SQL |
| **Criteria API** | API Java xây truy vấn theo cấu trúc biểu thức; hữu ích khi điều kiện ghép động |
| **Native SQL** | SQL viết trực tiếp theo bảng, cột và cú pháp database |
| **Fetch strategy** | Cách dữ liệu liên quan được tải: eager hay lazy |
| **Lazy loading** | Trì hoãn tải dữ liệu liên quan đến khi cần truy cập, tùy khả năng provider và context |
| **Fetch join** | Cách khai báo tải association trong cùng truy vấn JPQL để chủ động lấy dữ liệu |
| **N+1 query** | Một truy vấn lấy N entity rồi phát sinh thêm nhiều truy vấn lấy dữ liệu liên quan |
| **DTO projection** | Truy vấn ra đối tượng mang đúng trường cần trả về, tránh phải tải cả entity graph |

Không cần học thuộc bảng một lượt. Nên quay lại những định nghĩa này khi gặp mã chạy thực tế.

## 4. Ví dụ mapping nhỏ để đặt thuật ngữ vào ngữ cảnh

Giả sử hệ thống quản lý khách hàng và đơn hàng có hai bảng:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
```

*Cú pháp tạo identity ở trên chỉ để minh họa; DDL cụ thể tùy hệ quản trị cơ sở dữ liệu.*

Class entity tương ứng:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "name", nullable = false, length = 150)
    private String name;

    protected Customer() {
        // JPA cần constructor không tham số.
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void rename(String newName) {
        this.name = newName;
    }
}
```

Ở đây:

1. `@Entity` cho biết lớp tham gia ánh xạ JPA; `@Table` chọn bảng cụ thể.
2. `@Id` khai báo định danh; `@GeneratedValue` yêu cầu cơ chế sinh giá trị theo chiến lược đã chọn. `IDENTITY` thường dựa trên cột sinh giá trị của database.
3. `@Column` mô tả cột và một số ràng buộc mapping; constraint thực tế vẫn cần được kiểm tra/quản lý ở database.
4. `protected Customer()` cho provider khả năng tạo instance; constructor nghiệp vụ nhận `name` giúp tạo một khách hàng hợp lệ.
5. Vì annotation định danh đặt trên **field**, JPA dùng *field access* cho các thuộc tính persistent trong lớp này.

Lưu ý: một object `new Customer("An")` **chưa tự động có hàng dữ liệu trong database**. Object đó chỉ mới là instance Java. Cần một persistence context và thao tác persistence trong transaction phù hợp mới có thể ghi dữ liệu.

### 4.1. Tạo và cập nhật entity bằng EntityManager

Đoạn mã dưới đây minh họa **JPA với resource-local transaction** (không phải mẫu gọi `getTransaction()` trong container JTA hay phương thức Spring được quản lý bởi `@Transactional`):

```java
EntityManager em = entityManagerFactory.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Customer customer = new Customer("An");
    em.persist(customer);           // customer trở thành managed

    customer.rename("An Nguyen");  // JPA theo dõi thay đổi trên managed entity

    tx.commit();                    // flush và commit theo transaction
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Bạn không cần gọi `em.update(customer)`. JPA không có một thao tác "update managed entity" bắt buộc theo cách đó: khi entity đang managed, *dirty checking* giúp provider xác định thay đổi. SQL cụ thể và lúc phát ra SQL phụ thuộc provider, chiến lược sinh ID, flush và transaction; ví dụ trên không bảo đảm chỉ có một câu SQL hay đúng một thứ tự phát SQL ở mọi database.

Trong ứng dụng Spring thông thường, transaction do Spring quản lý bằng `@Transactional`; không nên vừa tự gọi `em.getTransaction()` vừa dựa vào cùng transaction do Spring quản lý.

## 5. Entity lifecycle: thuật ngữ quyết định cách JPA hoạt động

Một entity có thể thay đổi trạng thái khi ứng dụng gọi JPA API hoặc khi persistence context kết thúc.

```text
new Customer(...)                  (transient / new)
       |
       | persist(entity)
       v
managed  <--------------------- merge(detached) trả về object managed
   |                                      ^
   | remove(entity)                       |
   v                                      |
removed                                detached
   ^                                      ^
   |                                      |
   +-- managed -- detach / clear / close -+
```

Sơ đồ thể hiện các chuyển đổi thường gặp; `merge` trả về **managed instance**, không biến chính object detached ban đầu thành managed.

| Trạng thái | Đang nằm trong persistence context? | Có ý nghĩa gì khi sửa field? |
|---|---|---|
| **New / transient** | Chưa | Chỉ thay đổi object Java; `persist` mới đăng ký lưu |
| **Managed** | Có | Có thể được phát hiện bởi dirty checking và đồng bộ khi flush |
| **Detached** | Không | Sửa field không được context cũ tự động theo dõi; `merge` có thể sao chép trạng thái vào managed instance |
| **Removed** | Đã đánh dấu xóa trong context | Xóa được lên lịch; SQL có thể được thực thi khi flush |

Ví dụ quan sát identity map:

```java
Customer first = em.find(Customer.class, 7L);
Customer again = em.find(Customer.class, 7L);

boolean sameInstance = (first == again); // true nếu cùng managed entity/context
```

Trong cùng persistence context, cùng một loại entity và cùng định danh sẽ được biểu diễn bởi một managed instance. Tuy nhiên, **first-level cache không có nghĩa mọi query đều tránh chạm database**; riêng việc tạo JPQL query có thể vẫn khiến database thực thi SQL.

### 5.1. Các thao tác dễ nhầm

- `persist(entity)`: đăng ký một entity mới để lưu. Provider có thể thực hiện SQL sớm nếu cần lấy ID, nên không giả định mọi `INSERT` đều chờ đến commit.
- `find(Entity.class, id)`: tìm entity theo khóa chính; kết quả thông thường là managed trong context đang mở.
- `remove(entity)`: đánh dấu entity managed cần xóa. Với object detached, cần xử lý đưa về managed đúng cách trước khi xóa.
- `detach(entity)` và `clear()`: ngừng quản lý một entity hoặc toàn bộ entity trong context.
- `merge(detached)`: hợp nhất trạng thái object detached vào managed instance và **trả về instance đó**; tránh tiếp tục giả định tham chiếu cũ đã managed.
- `flush()`: gửi các thay đổi đang chờ xuống database, nhưng **chưa xác nhận transaction**.
- `refresh(entity)`: đọc lại trạng thái từ database, có thể ghi đè thay đổi chưa flush trên entity.

Ví dụ cho điểm khác nhau giữa flush và commit:

```java
tx.begin();

Customer c = new Customer("Binh");
em.persist(c);
em.flush();       // SQL có thể đã thực thi trong transaction hiện tại

tx.rollback();    // các thay đổi của transaction bị hủy
```

Nếu database và transaction hỗ trợ rollback bình thường, hàng vừa chèn sẽ không trở thành dữ liệu đã commit. Không nên dùng `flush()` như cách "lưu chắc chắn". Cũng cần phân biệt entity đã có ID với bản ghi đã commit: hai mốc này không đồng nghĩa.

## 6. Association: ánh xạ quan hệ và hiểu khóa ngoại

Trong quan hệ nhiều đơn hàng thuộc một khách hàng, mỗi hàng `purchase_orders` giữ khóa ngoại `customer_id` trỏ tới `customers.id`:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(name = "total_amount", nullable = false,
            precision = 12, scale = 2)
    private java.math.BigDecimal totalAmount;

    protected PurchaseOrder() {}

    public PurchaseOrder(Customer customer,
                         java.math.BigDecimal totalAmount) {
        this.customer = customer;
        this.totalAmount = totalAmount;
    }

    public Customer getCustomer() {
        return customer;
    }
}
```

`@ManyToOne` nói về **bội số của quan hệ đối tượng**; `@JoinColumn` chỉ rõ cột khóa ngoại. Phía `PurchaseOrder.customer` là *owning side* của quan hệ này vì nó ghi nhận khóa ngoại.

Nếu muốn điều hướng ngược từ `Customer` đến các đơn hàng, có thể thêm:

```java
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders = new ArrayList<>();
```

Trong mapping hai chiều này, `mappedBy = "customer"` chỉ đúng **tên field Java** của phía owning side. Tự thêm một đơn hàng vào `customer.getOrders()` mà không gán `order.customer` sẽ không thiết lập khóa ngoại theo ý định; cần giữ hai phía nhất quán bằng phương thức nghiệp vụ thích hợp. Để ví dụ chạy, nhớ import `java.util.List` và `java.util.ArrayList`, đồng thời bổ sung field vào class `Customer` ở trên.

### 6.1. Bốn loại quan hệ thường gặp

| Annotation | Ví dụ | Ý nghĩa và điểm cần nhớ |
|---|---|---|
| `@ManyToOne` | Nhiều Order thuộc một Customer | Thường ánh xạ bằng FK trên bảng phía "many" |
| `@OneToMany` | Customer có nhiều Order | Khi hai chiều, `mappedBy` chỉ phía inverse; collection mặc định lazy |
| `@OneToOne` | User có một Profile | Cần quyết định phía giữ FK, tính unique và tùy chọn |
| `@ManyToMany` | Student học nhiều Course và ngược lại | Thường dùng bảng nối; nếu bảng nối có thuộc tính riêng, nên mô hình thành entity trung gian |

Hai khái niệm dễ nhầm:

- **Cascade** điều khiển thao tác JPA lan sang entity liên quan, chẳng hạn `PERSIST`, `MERGE` hoặc `REMOVE`. Chỉ cascade khi thực sự có quan hệ vòng đời phù hợp; cascade xóa bừa bãi qua many-to-many có thể xóa dữ liệu dùng chung.
- **Orphan removal** dành cho mô hình cha–con có sở hữu vòng đời: khi con bị gỡ khỏi association được quản lý, provider có thể xóa bản ghi con. Nó không đồng nghĩa với xóa mọi đối tượng được một entity tham chiếu.

## 7. JPQL, truy vấn dữ liệu và vấn đề tải quan hệ

SQL thao tác trên bảng/cột. JPQL thao tác trên **tên entity, field/property và association**.

```java
List<Customer> customers = em.createQuery(
        "select c from Customer c " +
        "where c.name like :prefix order by c.id",
        Customer.class)
    .setParameter("prefix", "An%")
    .setMaxResults(20)
    .getResultList();
```

Truy vấn trên dùng `Customer` và `name` thay vì `customers` và tên cột vật lý. Provider chuyển JPQL thành SQL phù hợp với mapping và dialect database. Một số hướng truy vấn quan trọng:

- **JPQL:** phù hợp truy vấn có cấu trúc tương đối ổn định theo mô hình entity.
- **Criteria API:** hỗ trợ ghép điều kiện động bằng API Java; cú pháp dài hơn nhưng có thể xây dựng có kiểm soát.
- **Native SQL:** hữu ích khi cần tính năng đặc thù database, query phức tạp hoặc tối ưu cụ thể; phải tự quan tâm bảng/cột và tính tương thích.
- **DTO projection:** chọn đúng dữ liệu cần hiển thị, ví dụ tên khách hàng và tổng đơn, thay vì tự động kéo toàn bộ object graph.

### 7.1. Eager, lazy và N+1

`FetchType.EAGER` thể hiện yêu cầu tải association cùng quá trình tải entity; **không có nghĩa provider luôn dùng một SQL JOIN**. `FetchType.LAZY` hướng tới trì hoãn tải association cho đến khi cần. Theo mặc định của JPA, `@ManyToOne` và `@OneToOne` là eager; `@OneToMany` và `@ManyToMany` là lazy. Khi thiết kế ứng dụng, cần chủ động đặt fetch strategy theo từng use case thay vì tin rằng mặc định luôn tối ưu.

Giả sử truy vấn lấy 100 `PurchaseOrder`. Khi lặp qua từng `order.getCustomer().getName()`, provider có thể phải tải thêm từng customer chưa có trong context. Một truy vấn lấy danh sách cộng nhiều truy vấn riêng để lấy quan hệ là mô hình **N+1** (số SQL cụ thể phụ thuộc cache, quan hệ trùng lặp và provider).

Một cách chủ động là **fetch join** khi màn hình cần customer của từng order:

```java
List<PurchaseOrder> orders = em.createQuery(
        "select o from PurchaseOrder o " +
        "join fetch o.customer " +
        "where o.totalAmount >= :min",
        PurchaseOrder.class)
    .setParameter("min", new java.math.BigDecimal("100.00"))
    .getResultList();
```

`JOIN FETCH` minh họa một phương án, không phải giải pháp mặc định cho mọi màn hình. Với collection lớn, nhiều collection hoặc phân trang, fetch join có thể gây nhân bản hàng và giới hạn khả năng phân trang hiệu quả. Lúc đó cân nhắc projection, entity graph, batch fetching hoặc tách truy vấn theo nhu cầu.

Truy cập association lazy sau khi `EntityManager`/persistence context cần thiết đã đóng có thể thất bại do dữ liệu chưa được tải. Cách xử lý tốt là xác định trước dữ liệu cần cho use case và tải dữ liệu trong transaction hợp lý, thay vì giữ context mở vô thời hạn.

## 8. Transaction, đồng thời và nhất quán

Persistence context quản lý object; **transaction quyết định phạm vi thao tác được commit/rollback**. Hai khái niệm có liên hệ nhưng không đồng nhất. Một transaction thường gắn với một persistence context trong cách tổ chức thông dụng, nhưng đặc tả còn có các chế độ quản lý context khác.

Khi hai người cùng cập nhật một hàng, ghi đè ngoài ý muốn có thể xảy ra. JPA hỗ trợ **optimistic locking** qua một trường version:

```java
@Version
private Long version;
```

Provider dùng version để nhận biết dữ liệu đã bị người khác cập nhật trong lúc thao tác; khi có xung đột, có thể phát sinh ngoại lệ optimistic locking và transaction cần được xử lý phù hợp. Với quy trình kinh doanh, ứng dụng phải quyết định cách thông báo, thử lại hoặc yêu cầu người dùng đối chiếu thay đổi; JPA không tự chọn cách giải quyết xung đột nghiệp vụ.

Cần giữ ranh giới rõ ràng:

- Database quản lý isolation, khóa, constraint và durability của transaction.
- JPA quản lý identity, trạng thái entity, mapping và việc đồng bộ SQL.
- Service layer quyết định một đơn vị nghiệp vụ gồm những thao tác nào cần thành công hoặc thất bại cùng nhau.
- Spring `@Transactional` (nếu sử dụng) quản lý phạm vi transaction; repository chỉ là một cách truy cập persistence.

## 9. Trình tự học JPA đề xuất

Hãy học theo thứ tự **mỗi bước giải quyết một câu hỏi của bước trước**. Dùng cùng một mini project khách hàng–đơn hàng để dễ quan sát thay vì liên tục đổi bài toán.

| Giai đoạn | Trọng tâm | Bài thực hành | Dấu hiệu đã hiểu |
|---|---|---|---|
| **0. Củng cố SQL/JDBC** | PK, FK, JOIN, transaction, parameterized SQL | Tạo hai bảng, thêm/xóa/sửa bằng SQL rồi đọc qua JDBC | Giải thích được SQL nào thay đổi hàng nào và vì sao phải dùng transaction |
| **1. Hiểu lớp công nghệ** | ORM, JPA spec, provider, Spring Data JPA | Vẽ đường đi từ method Java tới SQL | Nói được thành phần nào định nghĩa API và thành phần nào thực thi |
| **2. Entity và mapping cơ bản** | `@Entity`, `@Table`, `@Id`, `@Column`, sinh ID | Mapping `Customer` và đọc/ghi một hàng | Phân biệt object, entity instance, định danh và row |
| **3. EntityManager và lifecycle** | `persist`, `find`, `remove`, managed/detached, dirty checking | Đọc cùng ID hai lần, đổi field, `flush` rồi rollback | Giải thích được SQL có thể xuất hiện ở thời điểm nào |
| **4. JPQL và đọc dữ liệu** | Truy vấn tham số, sắp xếp, giới hạn kết quả, projection | Tìm khách hàng theo tiền tố tên, lọc order theo tiền | Không nhầm tên entity/field với tên table/column |
| **5. Ánh xạ quan hệ** | Many-to-one, one-to-many, owning side, FK, cascade | Tạo `PurchaseOrder` và nối đúng `Customer` | Biết thay đổi phía nào quyết định FK; biết khi nào không dùng cascade |
| **6. Transaction và lỗi** | Commit/rollback, constraint, optimistic locking | Cố ý vi phạm FK/unique; thử hai cập nhật cạnh tranh | Phân biệt flush với commit và xử lý được rollback |
| **7. Fetching và hiệu năng** | Lazy/eager, N+1, fetch join, pagination | Bật SQL log, tải danh sách đơn và tên khách | Nhìn số SQL để phát hiện tải dữ liệu ngoài ý muốn |
| **8. Tích hợp Spring Data JPA** | Repository, derived query, `@Query`, `@Transactional` | Chuyển use case từ EntityManager sang repository/service | Thấy được lớp thuận tiện mới vẫn dùng các quy tắc JPA |
| **9. Vận hành thực tế** | Migration, index, batch, integration test, lỗi concurrency | Dùng schema migration và DB kiểm thử phù hợp | Có thể giải thích hành vi dữ liệu qua SQL, log và transaction |

### Giai đoạn 0–2: Dựng nền trước khi dùng tiện ích

Bắt đầu bằng SQL và JDBC tối thiểu để hiểu một thao tác như `INSERT INTO customers ...` làm gì. Sau đó thử JPA thuần: cấu hình một provider, tạo `EntityManagerFactory`/`EntityManager`, mapping một entity và thực hiện `persist` rồi `find`. Khi đọc mã, luôn có khả năng chỉ ra bảng, cột, khóa và thao tác SQL tương ứng.

Nếu bắt đầu ngay bằng `repository.save(entity)`, bạn có thể tạo CRUD nhanh nhưng sẽ khó giải thích tại sao một object chưa được cập nhật hoặc một truy vấn tự phát sinh SQL phụ.

### Giai đoạn 3–4: Học trạng thái trước khi học truy vấn phức tạp

Thử cùng một entity trong ba tình huống:

1. Khởi tạo bằng `new` rồi chưa gọi `persist`.
2. Lấy bằng `find` và đổi tên trong transaction.
3. Gọi `detach` rồi đổi tên tiếp.

Dự đoán trạng thái nào được JPA theo dõi. Kế tiếp, dùng JPQL với tham số bind thay vì ghép chuỗi người dùng vào câu truy vấn. Thử cả truy vấn trả entity và projection chỉ gồm trường cần thiết.

### Giai đoạn 5–6: Đi từ database relationship đến object association

Vẽ FK trên giấy rồi mới thêm `@ManyToOne`. Khi dùng mapping hai chiều, xác định owning side trước khi chỉnh collection. Thử thao tác sai FK, gọi `flush` và xem lỗi xảy ra vào lúc nào. Cuối cùng, đặt `@Version` cho entity có thể cập nhật cạnh tranh để hiểu vì sao "đọc rồi ghi" chưa đủ trong môi trường nhiều request.

### Giai đoạn 7–8: Quan sát SQL, rồi mới đưa Spring Data JPA vào

Bật log câu SQL và, nếu có, công cụ đo số truy vấn. Viết một endpoint/list view trả về danh sách order kèm customer. So sánh cách truy cập association bình thường với fetch join hoặc DTO projection. Sau khi đã hiểu đường đi đó, chuyển phần CRUD/truy vấn sang `JpaRepository` và `@Query`, giữ transaction tại service phù hợp.

Khi một repository method trả về dữ liệu sai hoặc chậm, hãy đặt câu hỏi theo thứ tự: **mapping đúng không → transaction đang ở đâu → entity đang managed không → SQL được phát ra là gì → số hàng/số truy vấn bao nhiêu?**

### Giai đoạn 9: Đặt JPA trong hệ thống có dữ liệu thật

Thực hành migration cho schema, thêm index cho FK và cột lọc phù hợp, thử transaction với database cùng loại môi trường triển khai nếu có thể. Viết integration test cho truy vấn/constraint quan trọng. Chọn kích thước transaction và cách phân trang theo khối lượng dữ liệu thật; không xem annotation như thay thế cho quan sát SQL execution plan.

## 10. Mini project xuyên suốt bài học

Xây một ứng dụng quản lý **khách hàng và đơn hàng** có các chức năng:

1. Tạo customer (tên bắt buộc).
2. Tạo purchase order gắn với một customer đang tồn tại; tổng tiền không âm.
3. Liệt kê đơn hàng theo khoảng tiền, trả thêm tên khách hàng.
4. Đổi tên customer trong transaction; kiểm tra dữ liệu sau commit.
5. Tìm danh sách đơn hàng phân trang, quan sát SQL.
6. Thử hai thao tác cập nhật cùng một customer có version; mô tả kết quả xung đột.

Đề xuất cấu trúc mã theo trách nhiệm:

```text
domain/
    Customer.java
    PurchaseOrder.java
persistence/
    CustomerRepository (hoặc DAO JPA thuần)
    PurchaseOrderRepository
service/
    CustomerService
    OrderService
api/
    CustomerController
    OrderController
db/migration/
    V1__create_customer_and_order_tables.sql
```

**Câu hỏi tự giải thích sau mỗi chức năng:** Dữ liệu nằm ở bảng nào? Entity nào đang managed? Transaction bắt đầu/kết thúc ở đâu? Lệnh SQL nào phải chạy? Association nào cần được tải? Ràng buộc nào do database kiểm tra?

Nếu trả lời được các câu hỏi này mà không phụ thuộc việc dùng JPA thuần hay Spring Data JPA, bạn đã nắm được nền tảng cho phần học nâng cao.

## 11. Những hiểu lầm thường gây lỗi

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “Thêm `@Entity` là dữ liệu tự được lưu.” | Annotation chỉ cấu hình mapping; vẫn cần thao tác persistence và transaction thích hợp. |
| “Có `id` tức là bản ghi đã commit.” | ID có thể được cấp trước commit; transaction vẫn có thể rollback. |
| “`flush()` giống `commit()`.” | Flush đồng bộ SQL trong transaction; commit mới xác nhận transaction. |
| “Sửa bất kỳ object entity nào JPA cũng lưu.” | Dirty checking hoạt động trên entity **managed** trong context thích hợp. |
| “`merge` gắn lại chính object detached cũ.” | `merge` trả về managed instance; tham chiếu detached ban đầu vẫn cần được xử lý cẩn thận. |
| “`FetchType.EAGER` luôn chạy đúng một query.” | Eager nói về yêu cầu tải, không cam kết số câu SQL. |
| “Lazy luôn nhanh hơn.” | Lazy không phù hợp cách dùng có thể tạo N+1 hoặc truy cập ngoài context. |
| “Cứ đặt `CascadeType.ALL` cho mọi quan hệ.” | Cascade phải theo quyền sở hữu vòng đời; xóa dây chuyền sai có thể làm mất dữ liệu. |
| “Quan hệ hai chiều tự đồng bộ hai object trong bộ nhớ.” | Mã ứng dụng thường phải giữ cả hai phía nhất quán; owning side quyết định thay đổi FK. |
| “`@Column(nullable=false)` đủ thay constraint/migration.” | Database constraint và quản lý schema vẫn là tuyến bảo vệ và triển khai quan trọng. |
| “EntityManager dùng chung nhiều thread cho tiết kiệm.” | EntityManager không được thiết kế dùng chung đồng thời giữa các thread; dùng scope phù hợp. |
| “Spring Data JPA loại bỏ nhu cầu hiểu JPA.” | Repository là lớp abstraction; lifecycle, transaction, fetching và SQL vẫn còn nguyên. |

Cẩn thận khi tạo `equals()`, `hashCode()` và `toString()` cho entity, đặc biệt với ID sinh sau khi persist hoặc quan hệ hai chiều. Tạo chúng tự động cho toàn bộ field (ví dụ qua `@Data` của Lombok) dễ dẫn đến tải lazy ngoài ý muốn, đệ quy vô hạn hoặc thay đổi hash trong collection. Với API, cân nhắc trả DTO thay vì đưa toàn bộ entity graph trực tiếp ra JSON.

## 12. Bảng kiểm năng lực trước khi học JPA nâng cao

Hãy tự trả lời, không cần học thuộc định nghĩa:

- Tại sao `new Customer("An")` và `em.find(Customer.class, id)` có thể khác nhau về cách JPA theo dõi thay đổi?
- Vì sao `em.flush()` có thể phát SQL nhưng `rollback()` vẫn hủy thay đổi?
- Khi `PurchaseOrder.customer` giữ khóa ngoại, phía nào là owning side và `mappedBy` dùng tên nào?
- Một query lấy 100 orders có thể tạo nhiều câu SQL bổ sung trong trường hợp nào?
- Tại sao `merge(detached)` phải được dùng với giá trị trả về?
- Khi hai request cùng sửa một customer, `@Version` giúp phát hiện điều gì?
- Nếu dùng Spring Data JPA, transaction nên được xác định quanh đơn vị nghiệp vụ nào?
- Khi danh sách trả về chậm, làm sao nhìn SQL, mapping, index, số query và số hàng để tìm nguyên nhân?

Nếu còn phân vân, quay về đúng giai đoạn tương ứng trong phần 9 và chạy lại một ví dụ nhỏ. Năng lực quan trọng nhất ở mức nền tảng là **dự đoán được trạng thái entity và hành vi SQL/transaction từ đoạn mã Java**, rồi kiểm chứng bằng database và log.

## 13. Từ điển rút gọn để ghi nhớ

```text
ORM               = Object-Relational Mapping
JPA               = Java Persistence API (tên gọi lịch sử, quen dùng)
Jakarta Persistence = đặc tả persistence Jakarta hiện đại
JDBC              = Java Database Connectivity
Entity            = đối tượng có định danh được JPA ánh xạ
EM                = EntityManager
EMF               = EntityManagerFactory
PC                = Persistence Context
PK / FK           = Primary Key / Foreign Key
JPQL              = Jakarta Persistence Query Language
DTO               = Data Transfer Object
DDL / DML         = Data Definition / Data Manipulation Language
N+1               = một lần tải danh sách + nhiều lần tải liên quan
```

**Hướng học tiếp:** sau khi làm được mini project và giải thích được bảng thuật ngữ trên, hãy đi sâu từng nhánh: entity lifecycle/dirty checking, khóa và concurrency, mapping quan hệ, thiết kế truy vấn hiệu năng, rồi đến Spring Data JPA và vận hành với database thực tế.
