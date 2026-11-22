# Tham chiếu trì hoãn và điều kiện để tránh tải thực thể ngay trong Hibernate ORM

Trong ứng dụng Java, một entity thường giữ tham chiếu đến entity khác, chẳng hạn `Order.customer`, `Invoice.account` hoặc `User.profile`. Đó là **quan hệ đơn trị** (*to-one association*): thuộc tính tham chiếu tối đa một đối tượng, thường được ánh xạ bằng `@ManyToOne` hoặc `@OneToOne`.

Điểm dễ nhầm là: **tải một entity không nhất thiết phải tải toàn bộ entity mà nó tham chiếu đến**, nhưng việc khai báo `fetch = FetchType.LAZY` cũng **không tự bảo đảm** Hibernate sẽ tránh mọi truy vấn hay tránh tải đối tượng đích trong tất cả tình huống.

Hibernate có thể trì hoãn việc tải entity liên quan bằng **proxy**, bằng **bytecode enhancement**, hoặc bằng một chiến lược fetching thích hợp với ánh xạ và phiên bản framework. Quyết định đó phụ thuộc vào việc Hibernate có biết định danh của entity đích hay không, có phải kiểm tra sự tồn tại của quan hệ không, lớp entity có đáp ứng điều kiện tạo proxy không và mã ứng dụng truy cập thuộc tính như thế nào.

Bài học giải thích cơ chế này, các ngoại lệ quan trọng và cách thiết kế truy vấn để đạt hành vi dự đoán được.

## 1. Quan hệ đơn trị là gì?

Hibernate ORM có hai ánh xạ quan hệ đơn trị phổ biến:

- **`@ManyToOne`**: nhiều entity cùng tham chiếu đến một entity. Ví dụ mỗi đơn hàng thuộc một khách hàng.
- **`@OneToOne`**: một entity có tối đa một entity liên quan, được thể hiện bằng khóa ngoại có ràng buộc unique, khóa chính dùng chung hoặc chiến lược ánh xạ tương đương.

Ví dụ hai entity:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;

    @Column(nullable = false, length = 100)
    private String name;

    protected Customer() {}

    public Long getId() { return id; }
    public String getName() { return name; }
}
```

```java
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public Customer getCustomer() { return customer; }
}
```

Trong database, một cách lưu thông thường:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id)
);
```

Trong Java, `order.getCustomer()` là một tham chiếu đối tượng. Trong bảng `purchase_orders`, Hibernate chỉ cần giá trị khóa ngoại `customer_id` để biết đơn hàng liên quan đến khách hàng nào.

**Câu hỏi của lazy loading:** khi truy vấn đơn hàng, Hibernate có phải thực hiện thêm `SELECT` để tải `Customer` ngay lập tức không?

## 2. EAGER và LAZY khác nhau ở đâu?

Jakarta Persistence có hai giá trị của `FetchType`:

- **`EAGER`**: yêu cầu provider lấy sẵn trạng thái của association theo hợp đồng fetch eager.
- **`LAZY`**: cho phép provider trì hoãn fetch; theo đặc tả, đây là **gợi ý** cho provider nên nạp khi cần.

Với `@ManyToOne` và `@OneToOne`, **mặc định của Jakarta Persistence là EAGER** nếu không khai báo `fetch`.

Ví dụ:

```java
@ManyToOne
private Customer customer; // Mặc định EAGER.

@ManyToOne(fetch = FetchType.LAZY)
private Customer lazyCustomer;
```

Để chủ động tránh nạp đối tượng liên quan khi không cần, cần khai báo `LAZY` rõ ràng ở những quan hệ phù hợp. Nhưng cần hiểu giới hạn:

> `FetchType.LAZY` thể hiện ý định trì hoãn; Hibernate vẫn có thể cần tải entity liên quan hoặc chạy SQL bổ sung vì cấu trúc mapping, kế hoạch truy vấn, yêu cầu xác định `null` hoặc hành vi cụ thể của provider.

Không nên đồng nhất `LAZY` với “không bao giờ truy vấn đối tượng đích” hoặc “getter chắc chắn không bao giờ tạo SQL”.

### Phân biệt ba tình huống dễ bị gộp thành một

| Hành vi | Điều gì xảy ra? | Ý nghĩa |
|---|---|---|
| **Eager fetch** | Đối tượng liên quan được nạp cùng quá trình lấy entity chính | Có thể dùng join hoặc truy vấn thứ cấp; không phải lúc nào cũng là một câu SQL |
| **Lazy proxy** | Hibernate đặt một đối tượng đại diện ở thuộc tính quan hệ; dữ liệu thật được tải khi cần | Có thể đọc tham chiếu mà chưa tải mọi cột của entity đích |
| **Lazy attribute bằng enhancement** | Hibernate trì hoãn truy cập thuộc tính/association thông qua bytecode được tăng cường | Không nhất thiết phải dùng proxy kiểu subclass; phụ thuộc cấu hình và mapping |

Vì vậy, cần hỏi **Hibernate đã tải dữ liệu entity đích chưa?** chứ không chỉ hỏi **Java field có khác `null` chưa?**

## 3. Cách Hibernate dùng proxy cho `@ManyToOne`

Với `@ManyToOne` ở phía có khóa ngoại, Hibernate thường đã đọc được `customer_id` khi nạp hàng đơn hàng. Nếu `customer_id = 15`, framework đã biết **identifier của Customer đích** mà chưa cần biết tên, địa chỉ hay các thuộc tính khác của khách hàng.

Giả sử:

```text
purchase_orders
+-----+-------------+
| id  | customer_id |
+-----+-------------+
| 101 | 15          |
+-----+-------------+

customers
+----+----------+
| id | name     |
+----+----------+
| 15 | Ngọc An  |
+----+----------+
```

Nếu mapping cho phép lazy proxy:

```text
SELECT id, customer_id
FROM purchase_orders
WHERE id = 101
               |
               v
PurchaseOrder { id=101 }
        |
        +--> customer: Hibernate proxy
                      { identifier=15 }
                      [name chưa được tải]
               |
               | order.getCustomer().getName()
               v
SELECT id, name
FROM customers
WHERE id = 15
               |
               v
Customer được khởi tạo dữ liệu
```

Nội dung quan trọng: Hibernate **không cần đọc toàn bộ Customer chỉ để dựng tham chiếu theo khóa ngoại đã biết**. Proxy chứa đủ thông tin nhận dạng để trì hoãn truy vấn dữ liệu đích.

### Ví dụ theo dõi thực thi

```java
EntityManager em = entityManagerFactory.createEntityManager();
try {
    PurchaseOrder order = em.find(PurchaseOrder.class, 101L);

    Customer customer = order.getCustomer();
    // Nếu proxy lazy hoạt động, chưa nhất thiết cần SELECT customers.

    String name = customer.getName();
    // Khi dữ liệu name chưa có, Hibernate có thể SELECT customers ở đây.
} finally {
    em.close();
}
```

Ví dụ giả định entity `PurchaseOrder` có ánh xạ ở phần trước và môi trường không có fetch plan buộc eager load. Với code thực tế, thao tác đọc nên đặt trong transaction phù hợp để đảm bảo phạm vi nhất quán cần thiết. Một số đường load và cache có thể khiến không có SQL thứ cấp dù association vẫn được cấu hình lazy.

### Gọi getter của association không nhất thiết là tải entity đích

```java
Customer customer = order.getCustomer();
```

Trong proxy-based lazy loading, câu lệnh trên thường chỉ trả về proxy. Đến khi truy cập dữ liệu thật của `Customer`, proxy mới phải khởi tạo.

Tuy nhiên:

- Chỉ có thể đưa ra kết luận này khi mapping và bytecode/proxy thực tế hỗ trợ.
- Phương thức gọi trên proxy có thể kích hoạt initialization tùy nội dung phương thức.
- Một số kiểu truy cập identifier được Hibernate xử lý mà không cần khởi tạo proxy; cách hành xử chính xác phụ thuộc mapping và phiên bản.

Không nên dùng hành vi của một getter đơn lẻ làm giả định chung cho mọi cấu hình Hibernate.

## 4. Điều kiện để quan hệ đơn trị thật sự được trì hoãn

Việc `@ManyToOne(fetch = LAZY)` có tác dụng như kỳ vọng thường dựa vào các điều kiện sau.

### 4.1. Hibernate biết identifier của đích

Ở phía sở hữu `@ManyToOne`, khóa ngoại trong hàng nguồn thường cho Hibernate biết ID của entity đích. Nếu cột `customer_id` khác null, Hibernate có thể dựng proxy của `Customer(id=15)` mà chưa cần truy vấn `customers`.

Nếu khóa ngoại là null và association cho phép null, Hibernate có thể trả về `null` ngay:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = true)
@JoinColumn(name = "reviewer_id")
private User reviewer;
```

Với hàng có `reviewer_id IS NULL`, không cần tạo proxy để biểu diễn một reviewer không tồn tại.

### 4.2. Mapping không buộc fetch trước

Nếu annotation mặc định `EAGER`, một entity graph yêu cầu tải association hoặc truy vấn có `JOIN FETCH`, Hibernate có thể lấy entity đích ngay trong quá trình tải nguồn.

Ví dụ chủ động fetch:

```java
List<PurchaseOrder> orders = em.createQuery("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    where o.id = :id
    """, PurchaseOrder.class)
    .setParameter("id", 101L)
    .getResultList();
```

Khi query yêu cầu `JOIN FETCH`, mặc dù mapping là `LAZY`, kết quả truy vấn vẫn được nạp association theo fetch plan.

### 4.3. Entity đích có thể được đại diện bằng proxy, hoặc Hibernate dùng enhancement phù hợp

Với cơ chế proxy truyền thống, Hibernate cần khả năng tạo lớp proxy đại diện entity. Những thiết kế có thể gây trở ngại:

- Lớp entity `final` hoặc cấu trúc không cho phép sinh subclass proxy thích hợp.
- Constructor không tham số không thể được provider/proxy tiếp cận theo cách cần thiết.
- Các phương thức cần được proxy intercept bị khai báo `final` hoặc giới hạn phù hợp khác.
- Entity và bytecode được đóng gói theo cách khiến cơ chế proxy/enhancement không tương thích.

Ví dụ đơn giản nên dùng một entity Java bình thường:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String name;

    protected Customer() {}
}
```

Jakarta Persistence yêu cầu constructor không tham số phù hợp cho entity, thường là `public` hoặc `protected`. Đồng thời, việc tạo proxy còn tùy cơ chế kỹ thuật của Hibernate. **Không phải mọi entity không proxy được đều khiến toàn bộ ORM thất bại**, nhưng ý định lazy có thể cần một cơ chế thay thế hoặc không đạt như mong đợi.

**Bytecode enhancement** cho phép Hibernate can thiệp ở mức truy cập thuộc tính và có thể hỗ trợ những dạng lazy loading không dựa hoàn toàn vào proxy subclass. Khả năng áp dụng cụ thể phụ thuộc phiên bản Hibernate và cấu hình build/runtime; không nên giả định chỉ khai báo `LAZY` là đã bật enhancement.

### 4.4. Trạng thái Session và persistence context cho phép tải về sau

Hibernate cần một Session/persistence context hợp lệ để tải dữ liệu khi lazy association bị truy cập.

Ví dụ:

```java
PurchaseOrder order;
try (Session session = sessionFactory.openSession()) {
    order = session.find(PurchaseOrder.class, 101L);
}
// session đã đóng.

String name = order.getCustomer().getName();
// Nếu Customer chưa initialized, có thể ném LazyInitializationException.
```

`LAZY` không kéo dài vòng đời Session. Khi mã ứng dụng muốn sử dụng thông tin của entity đích, cần truy cập trong phạm vi quản lý thích hợp hoặc truy vấn trước dữ liệu cần trả về.

### 4.5. Mã ứng dụng chưa vô tình khởi tạo association

Ngay cả khi Hibernate dựng proxy thành công, mã gọi sau đây có thể kích hoạt tải:

- Gọi getter của dữ liệu đích, ví dụ `order.getCustomer().getName()`.
- Ghi log toàn bộ entity nếu `toString()` đi sâu qua association.
- Serialize entity trực tiếp thành JSON và serializer đi vào nested object.
- So sánh `equals()`/`hashCode()` khi implementation truy cập thuộc tính lazy.
- Dùng debugger hiển thị tất cả properties hoặc gọi `toString()` tự động.
- Dùng mapper chuyển toàn bộ object graph sang DTO dù màn hình chỉ cần vài trường.

Vì vậy, **khả năng trì hoãn của Hibernate** và **việc ứng dụng có thực sự để dữ liệu ở trạng thái chưa tải** là hai vấn đề riêng.

## 5. `@OneToOne`: quan hệ đơn trị khó lazy hơn ở phía ngược

`@OneToOne` có trường hợp rất khác với `@ManyToOne`, nhất là khi quan hệ **hai chiều** và khóa ngoại nằm ở bảng entity kia.

Giả sử một tài khoản có thể có một hồ sơ chi tiết.

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    username VARCHAR(100) NOT NULL
);

CREATE TABLE account_profiles (
    id BIGINT PRIMARY KEY,
    account_id BIGINT NOT NULL UNIQUE REFERENCES accounts(id),
    bio VARCHAR(1000)
);
```

Entity phía sở hữu khóa ngoại:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "account_profiles")
public class AccountProfile {
    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "account_id", nullable = false, unique = true)
    private Account account;

    protected AccountProfile() {}

    public Long getId() { return id; }
    public Account getAccount() { return account; }
}
```

Entity phía ngược:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "accounts")
public class Account {
    @Id
    private Long id;

    private String username;

    @OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
    private AccountProfile profile;

    protected Account() {}

    public Long getId() { return id; }
    public AccountProfile getProfile() { return profile; }
}
```

Quan sát khác biệt:

- Khi tải `AccountProfile`, cột `account_id` nằm ngay trong hàng nguồn. Hibernate biết ID của `Account` đích và có thể dùng proxy.
- Khi tải `Account`, hàng `accounts` **không chứa `account_profile.id` hay một cột cho biết profile có tồn tại**. Để trả về `null` khi không có profile hoặc một reference hợp lệ khi có profile, Hibernate có thể phải truy vấn bảng `account_profiles`.

Với phía ngược của `@OneToOne` kiểu khóa ngoại riêng và **nullable/optional**, chỉ nhìn hàng `accounts` thường không biết có profile hay không:

```text
accounts:
  id = 10
  [không có cột profile_id]

account_profiles:
  id = 90, account_id = 10
  hoặc không có row nào cho account 10

Khi tải Account(10), Hibernate cần phân biệt:
  profile == null
  hay
  profile -> AccountProfile(...)
```

Đây là một trong những lý do thực tế khiến khai báo `fetch = LAZY` ở phía ngược của `@OneToOne` có thể **không tránh được truy vấn bổ sung**.

### `optional = false` có tự giải quyết được không?

`optional = false` thông báo quan hệ bắt buộc theo metadata mapping, giúp Hibernate suy luận trong một số trường hợp. Tuy vậy:

- Nó chỉ hợp lý nếu database và quy tắc nghiệp vụ thật sự bảo đảm đối tượng đích tồn tại.
- Ở phía ngược, nếu ID của entity đích không thể suy ra từ ID của entity nguồn, việc biết quan hệ là bắt buộc chưa chắc đã đủ để dựng reference đúng mà không truy vấn.
- Behavior lazy của inverse one-to-one khác nhau theo phiên bản Hibernate, proxy/enhancement và cấu trúc khóa.

Vì thế **không nên coi `optional = false` là một “công tắc” chắc chắn bỏ mọi SQL phụ**. Nó là một điều kiện semantics của mapping, không thay thế thiết kế khóa và khả năng tham chiếu.

## 6. Shared primary key và `@MapsId` giúp ích thế nào?

Một biến thể thường gặp của `@OneToOne` là **dùng chung khóa chính** (*shared primary key*): khóa chính của profile đồng thời là khóa ngoại tới account.

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    username VARCHAR(100) NOT NULL
);

CREATE TABLE account_profiles (
    id BIGINT PRIMARY KEY REFERENCES accounts(id),
    bio VARCHAR(1000)
);
```

Mapping phía profile:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "account_profiles")
public class AccountProfile {
    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @MapsId
    @JoinColumn(name = "id")
    private Account account;

    private String bio;

    protected AccountProfile() {}
}
```

Mapping phía account:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "accounts")
public class Account {
    @Id
    private Long id;

    private String username;

    @OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
    private AccountProfile profile;

    protected Account() {}
}
```

Với shared primary key, nếu `Account.id = 10` thì `AccountProfile`, **nếu tồn tại**, cũng có ID 10. Hibernate có thể biết ID của profile mà không cần đọc một khóa ngoại riêng từ bảng đích.

Tuy nhiên, vẫn phải phân biệt:

1. **Biết ID có thể có của profile.**
2. **Biết profile có tồn tại hay không.**

Nếu profile là tùy chọn và có thể chưa được tạo, chỉ biết ID tiềm năng **không chứng minh row tồn tại**. Hibernate có thể cần kiểm tra tồn tại, hoặc dùng enhancement/chiến lược khác để hoãn kiểm tra đến khi thuộc tính được truy cập.

Nếu quan hệ được bảo đảm bắt buộc bằng thiết kế và các invariant thực tế, Hibernate có thêm cơ sở để tránh truy vấn sớm. Nhưng cơ chế cụ thể vẫn phụ thuộc mapping/version và tình trạng dữ liệu; dùng `optional = false` cho quan hệ thực sự tùy chọn chỉ để giảm SQL là không đúng semantics.

### Một chiều thường đơn giản hơn khi không cần đi ngược

Nếu use case chỉ cần đi từ `AccountProfile` đến `Account`, không bắt buộc khai báo thêm `Account.profile`. Quan hệ một chiều chỉ ở phía giữ khóa ngoại thường đơn giản và ít phát sinh yêu cầu kiểm tra sự tồn tại ngược.

Chỉ thêm navigation ngược khi có nhu cầu nghiệp vụ; mapping hai chiều không phải mặc định “tốt hơn” một chiều.

## 7. Proxy là gì và đọc gì mà chưa tải đích?

**Hibernate proxy** là đối tượng thay mặt entity đích. Nó thường giữ định danh và có thể được khởi tạo sau, khi mã cần trạng thái thật.

Giả sử:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 101L);

Customer customer = order.getCustomer();
```

Tại thời điểm này, nếu proxy lazy được tạo thành công, biến `customer` **không phải null** nhưng vẫn có thể chứa dữ liệu chưa được tải.

### Truy cập identifier có luôn không truy vấn?

Trong nhiều trường hợp Hibernate proxy có thể cung cấp ID mà không cần initialize toàn bộ entity:

```java
Long id = order.getCustomer().getId();
```

Nhưng không nên nâng đó thành lời hứa tổng quát rằng “mọi getter tên `getId()` đều miễn phí”. Hành vi phụ thuộc cách Hibernate nhận diện identifier getter, chế độ truy cập property/field, bytecode enhancement, kiểu proxy và một số cấu hình compliance.

Nếu chỉ cần ID quan hệ, cách **rõ ràng về chi phí** là lập kế hoạch truy vấn DTO hoặc ánh xạ giá trị khóa ngoại riêng theo thiết kế có kiểm soát. Tránh suy đoán hành vi proxy trong một endpoint tải hàng chục nghìn bản ghi.

### Kiểm tra proxy đã khởi tạo chưa

Hibernate cung cấp API kiểm tra trạng thái initialized:

```java
import org.hibernate.Hibernate;

Customer customer = order.getCustomer();

boolean initialized = Hibernate.isInitialized(customer);
```

`Hibernate.isInitialized(...)` giúp quan sát trạng thái liên quan đến lazy loading trong ứng dụng Hibernate. Với entity đã được tải từ persistence context/cache, kết quả có thể đã là initialized trước khi getter được gọi; việc đó không trái với khai báo `LAZY`.

Để yêu cầu tải dữ liệu trong Session hợp lệ:

```java
Hibernate.initialize(customer);
```

Lệnh này nhằm initialize giá trị đang lazy; nó **không sửa vòng đời tài nguyên**. Nếu Session cần thiết đã đóng và dữ liệu chưa nạp, việc initialize có thể thất bại.

### `getReference()` khác `find()`

`EntityManager.find(...)` thông thường nhằm tìm và nạp entity:

```java
Customer customer = em.find(Customer.class, 15L);
```

`EntityManager.getReference(...)` yêu cầu một tham chiếu có thể trì hoãn truy cập dữ liệu:

```java
Customer customerReference =
    em.getReference(Customer.class, 15L);
```

Trong Hibernate, lời gọi `getReference` thường có thể trả proxy mà không thực hiện `SELECT` ngay. Nó hữu ích khi cần **gán quan hệ qua ID đã biết**:

```java
PurchaseOrder order = new PurchaseOrder();
order.setCustomer(em.getReference(Customer.class, customerId));
em.persist(order);
```

Ví dụ giả định entity có constructor và setter thích hợp, đang ở transaction hợp lệ. Không cần fetch toàn bộ Customer chỉ để đặt khóa ngoại của order.

**Lưu ý:** `getReference` không có nghĩa kiểm chứng ngay rằng hàng khách hàng thực sự tồn tại. Nếu ID không tồn tại, lỗi có thể chỉ xuất hiện khi proxy được sử dụng hoặc khi ràng buộc khóa ngoại bị kiểm tra; behavior tùy provider và database. Khi nghiệp vụ đòi hỏi xác nhận Customer tồn tại và người dùng có quyền tham chiếu, cần kiểm tra thích hợp.

## 8. Bytecode enhancement và lazy loading không cần proxy truyền thống

Proxy subclass là một cơ chế trì hoãn phổ biến, nhưng không phải cơ chế duy nhất. **Hibernate bytecode enhancement** thay đổi bytecode của entity để hỗ trợ những khả năng như:

- Intercept truy cập thuộc tính để trì hoãn tải dữ liệu.
- Theo dõi thay đổi thuộc tính trong một số cấu hình.
- Cung cấp một số chiến lược lazy initialization cho to-one association mà cơ chế proxy thông thường khó thực hiện.

Với enhanced entity, Hibernate có thể trì hoãn việc truy cập một association theo cách khác, thay vì buộc field phải chứa một proxy subclass ngay từ đầu.

### Bật enhancement thế nào?

Cơ chế thực tế tùy Hibernate version và công cụ build. Một số dự án dùng Hibernate Gradle/Maven plugin để enhance entity khi build; một số môi trường dùng runtime enhancement nếu được hỗ trợ.

Ví dụ cấu hình khái niệm:

```text
Java entity source
        |
        v
Build / runtime enhancement (khi được cấu hình)
        |
        v
Enhanced entity bytecode
        |
        v
Hibernate intercept attribute access
        |
        v
Fetch dữ liệu khi cần theo mapping
```

Không nên sao chép nguyên một cấu hình plugin từ tài liệu Hibernate đời khác mà không đối chiếu version đang dùng. Các annotation riêng từng có vai trò điều khiển lazy to-one, chẳng hạn những dạng cấu hình `@LazyToOne` trong phiên bản cũ, có thể được thay đổi hoặc không còn cần thiết trong phiên bản mới.

**Điểm phải hiểu:** enhancement mở rộng khả năng trì hoãn, nhất là đối với inverse `@OneToOne` hoặc các mô hình khó proxy, nhưng **không biến mọi association thành lazy tuyệt đối** và không loại bỏ yêu cầu transaction/Session khi truy cập dữ liệu chưa tải.

### Khi nào enhancement không phải câu trả lời duy nhất?

Nếu một màn hình chắc chắn cần tên khách hàng của mọi đơn hàng, trì hoãn từng customer rồi truy cập tuần tự có thể dẫn đến N+1. Trong trường hợp ấy, truy vấn fetch join/projection được thiết kế theo use case thường hiệu quả hơn việc cố tối đa hóa laziness.

Enhancement là **cơ chế thực hiện fetch plan**, còn lựa chọn dữ liệu cần tải là **quyết định truy vấn** của ứng dụng.

## 9. Lazy to-one và N+1 query

Lazy loading giúp bỏ qua dữ liệu không cần thiết, nhưng khi truy cập cùng association cho nhiều entity, có thể phát sinh **N+1 queries**.

Ví dụ:

```java
List<PurchaseOrder> orders = em.createQuery("""
    select o
    from PurchaseOrder o
    order by o.id
    """, PurchaseOrder.class).getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

Giả sử có 100 đơn hàng thuộc nhiều khách hàng riêng biệt và các customer chưa tồn tại trong persistence context/cache:

```text
1 truy vấn lấy 100 purchase_orders
+
tới 100 truy vấn bổ sung lấy từng customers
=
có thể gần 101 truy vấn
```

Nếu nhiều đơn hàng cùng trỏ tới một customer, identity map cấp Session hoặc cache có thể làm giảm số truy vấn. Vì vậy “N+1” là mô hình rủi ro, không nhất thiết đúng chính xác mọi lần.

### Giải pháp khi use case cần dữ liệu liên quan

Dùng fetch join trên JPQL:

```java
List<PurchaseOrder> orders = em.createQuery("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    order by o.id
    """, PurchaseOrder.class).getResultList();
```

Khi cần cả order và customer, `join fetch` yêu cầu Hibernate lấy luôn Customer theo truy vấn, tránh kiểu nạp một customer mỗi lần truy cập về sau.

Nếu association có thể null và vẫn muốn giữ các order không có customer, cân nhắc `left join fetch`:

```java
select o
from PurchaseOrder o
left join fetch o.customer
```

Chọn inner hay left join theo semantics nullability. `join fetch` không nên được thêm cho mọi association: fetch thừa có thể tăng dữ liệu truyền, độ phức tạp SQL và bộ nhớ.

### Entity graph cũng là lựa chọn

Khi cần tùy biến fetch plan nhưng không muốn nhúng nhiều join vào JPQL:

```java
import jakarta.persistence.EntityGraph;

EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

List<PurchaseOrder> orders = em.createQuery("""
    select o from PurchaseOrder o
    order by o.id
    """, PurchaseOrder.class)
    .setHint("jakarta.persistence.fetchgraph", graph)
    .getResultList();
```

Entity graph cho phép chỉ định association cần eager-load cho một truy vấn. Cách Hibernate thực thi có thể là join hoặc truy vấn bổ sung thích hợp; **entity graph quyết định dữ liệu cần tải**, không phải cam kết hình dạng SQL duy nhất.

### DTO projection: chỉ đọc giá trị cần hiển thị

Nếu màn hình chỉ cần mã đơn hàng và tên khách hàng, DTO projection có thể hiệu quả và rõ nghĩa hơn tải entity:

```java
List<OrderRow> rows = em.createQuery("""
    select new com.example.orders.OrderRow(
        o.id, o.referenceCode, c.name
    )
    from PurchaseOrder o
    join o.customer c
    """, OrderRow.class)
    .getResultList();
```

Ví dụ giả định `PurchaseOrder` có thuộc tính `referenceCode` và `OrderRow` là DTO có constructor tương ứng. Truy vấn đọc dữ liệu cần thiết mà không buộc code đi qua proxy để lấy từng tên khách hàng.

## 10. EAGER không đồng nghĩa một JOIN duy nhất

Một hiểu lầm thường gặp là `EAGER` chắc chắn lấy mọi association bằng join trong cùng một SQL. Trên thực tế, Hibernate có thể thực hiện **secondary select** để thỏa yêu cầu eager fetch khi truy vấn chính không fetch join.

Ví dụ:

```java
@ManyToOne // EAGER mặc định
private Customer customer;
```

Truy vấn:

```java
List<PurchaseOrder> orders = em.createQuery(
    "select o from PurchaseOrder o",
    PurchaseOrder.class
).getResultList();
```

Có thể phát sinh SQL lấy orders, sau đó các SQL lấy Customer để bảo đảm eager association được khởi tạo trước khi trả kết quả. Điều này cũng có thể tạo N+1.

Khi cần kiểm soát hiệu năng, đừng dựa vào một annotation eager/lazy đơn lẻ. Hãy xác định dữ liệu thực sự cần cho **mỗi truy vấn** rồi chọn join fetch, entity graph, projection hoặc batch fetching phù hợp.

## 11. Bytecode, proxy và việc truy cập thực thể trong debugger/log

Một entity có thể được tải lười thành công nhưng SQL phát sinh ngay sau đó vì những hành vi vô tình.

### 11.1. `toString()` truy cập association

Ví dụ nguy hiểm:

```java
@Override
public String toString() {
    return "Order: " + id
        + ", customer=" + customer.getName();
}
```

Mỗi lần log `order` có thể truy cập name và khiến proxy initialize. Nếu toString hai entity gọi qua lại, còn có thể gây recursion.

Đối với entity, nên viết `toString()` tập trung vào các trường đơn giản thật sự cần thiết; tránh duyệt toàn bộ object graph.

### 11.2. Lombok trên entity

Ví dụ:

```java
@Data
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;
}
```

Lombok `@Data` có thể sinh `toString()`, `equals()` và `hashCode()` dựa trên field, dẫn tới việc truy cập association lazy, vòng tham chiếu hoặc thay đổi equality theo trạng thái. Không nên tự động đưa quan hệ lazy vào các phương thức này.

Có thể dùng những annotation Lombok chuyên biệt và loại trừ association khi cần, hoặc tự viết các phương thức phù hợp với domain.

### 11.3. JSON serialization

Nếu controller trả trực tiếp entity:

```java
@GetMapping("/orders/{id}")
public PurchaseOrder get(@PathVariable Long id) {
    return repository.findById(id);
}
```

Serializer có thể gọi `getCustomer()` rồi đi vào các getter của Customer. Điều này có thể:

- Phát sinh truy vấn ngoài ý muốn.
- Gặp `LazyInitializationException` sau khi Session đã đóng.
- Xuất dữ liệu nhạy cảm hoặc tạo vòng object graph khi association hai chiều.

Đối với REST API, thường nên trả DTO được tạo trong service/transaction với dữ liệu xác định rõ. Không nên chỉ bật eager toàn bộ quan hệ để “sửa” lỗi serializer.

### 11.4. Debugger và logging

Một số IDE có chế độ tự đánh giá property, `toString()` hoặc biểu thức trong cửa sổ debugger. Khi xem entity lazy, thao tác quan sát đó có thể thực sự gọi Java method và kích hoạt SQL.

Nếu đo số truy vấn, cần kiểm soát các thao tác debug/log. “Chỉ xem biến” không phải lúc nào cũng là hoạt động không có tác dụng phụ.

## 12. Session, transaction và `LazyInitializationException`

Một association lazy thường được tải khi có yêu cầu truy cập trạng thái thật. Để Hibernate thực hiện việc đó, dữ liệu phải được lấy trong ngữ cảnh persistence thích hợp.

Ví dụ phương thức đóng Session quá sớm:

```java
public PurchaseOrder findOrder(Long id) {
    try (Session session = sessionFactory.openSession()) {
        return session.find(PurchaseOrder.class, id);
    }
}

public String customerName(Long id) {
    PurchaseOrder order = findOrder(id);
    return order.getCustomer().getName();
    // Nếu association còn lazy, có thể gặp LazyInitializationException.
}
```

Vấn đề nằm ở ranh giới tài nguyên: `findOrder` trả entity đã tách khỏi Session, nhưng caller vẫn kỳ vọng ORM đi truy vấn khi truy cập customer.

Một cách rõ ràng hơn là lấy đúng dữ liệu trong transaction:

```java
@Transactional(readOnly = true)
public OrderView findOrderView(Long id) {
    PurchaseOrder order = em.createQuery("""
        select o from PurchaseOrder o
        join fetch o.customer
        where o.id = :id
        """, PurchaseOrder.class)
        .setParameter("id", id)
        .getSingleResult();

    return new OrderView(
        order.getId(),
        order.getCustomer().getName()
    );
}
```

Ví dụ trên giả định một framework như Spring thực sự xử lý `@Transactional`, entity `PurchaseOrder`/`Customer` có getters tương ứng và `OrderView` là DTO. Với API trả về một bản ghi có thể không tồn tại, cần thêm cách xử lý `NoResultException` hoặc API tương ứng.

**Không nên kéo dài vòng đời Session chỉ vì muốn serializer tự truy vấn tùy ý**. Thiết kế fetch theo response rõ ràng thường dễ kiểm soát hiệu năng và dữ liệu.

### Open Session in View (OSIV)

OSIV cho phép Session/persistence context còn hoạt động trong giai đoạn xử lý view hoặc serialization, giúp một số lazy access không lập tức lỗi. Tuy nhiên, đó là lựa chọn kiến trúc có đánh đổi:

- Truy vấn có thể phát sinh ở tầng controller/view, ngoài nơi được thiết kế transaction nghiệp vụ.
- Khó kiểm soát tổng số SQL và N+1.
- Ranh giới consistency giữa các lần truy vấn có thể không đúng kỳ vọng.

OSIV không phải điều kiện bắt buộc cho Hibernate lazy loading. Một ứng dụng có thể tắt OSIV và dùng projection/fetch plan trong transaction để trả dữ liệu đầy đủ.

## 13. Các yếu tố khiến LAZY không đạt kết quả như dự kiến

| Tình huống | Vì sao có thể tải hoặc truy vấn sớm? | Hướng xử lý |
|---|---|---|
| Quên `fetch = LAZY` trên to-one | Mặc định JPA của `@ManyToOne`/`@OneToOne` là EAGER | Khai báo LAZY khi phù hợp và kiểm chứng SQL |
| `@OneToOne(mappedBy=...)` tùy chọn | Hàng nguồn không có FK, cần xác định entity đích có tồn tại | Cân nhắc shared PK, cấu trúc ownership, enhancement hoặc bỏ navigation ngược |
| Target entity khó proxy | `final`/constructor/method có thể hạn chế subclass proxy | Dùng entity phù hợp, enhancement khi được hỗ trợ |
| Truy vấn dùng `JOIN FETCH`/entity graph | Fetch plan ghi đè mong muốn trì hoãn của mapping | Chỉ fetch các quan hệ use case thực sự cần |
| `toString`/serializer/mapper đi sâu vào quan hệ | Getter trên proxy bị gọi | Dùng DTO, hạn chế đọc association trong utility methods |
| Lấy nhiều source rồi đọc từng association | N+1 | Fetch join, projection, graph hoặc batch fetching |
| Session đóng trước khi truy cập | Hibernate không còn ngữ cảnh để initialize | Đọc dữ liệu cần thiết trong transaction và trả DTO |
| Mapping sử dụng chiến lược bỏ qua FK bị hỏng như `@NotFound` | Hibernate có thể phải kiểm tra tồn tại đích, khiến association được fetch eager | Giữ toàn vẹn FK và xem hệ quả fetch của annotation riêng |
| Chính sách eager trong mapping liên quan | Nạp target kéo theo những quan hệ eager khác | Kiểm soát fetch graph và giảm eager chain |
| Cache đã có entity đích | Không thấy SQL dù thuộc tính chưa truy cập | Đừng kết luận LAZY/EAGER chỉ qua một lần chạy nóng cache |

Với Hibernate-specific `@NotFound`, cơ chế xử lý tham chiếu đến hàng không tồn tại thường có hệ quả **fetch eager** đối với association liên quan. Đây là lý do tốt để ưu tiên khóa ngoại thật và tính toàn vẹn dữ liệu thay vì cố “chấp nhận” mọi tham chiếu bị hỏng trong mapping.

## 14. Trì hoãn tham chiếu khác với trì hoãn trường dữ liệu cơ bản

`@ManyToOne(fetch = LAZY)` và `@OneToOne(fetch = LAZY)` điều khiển **association**. Một cột cơ bản như `String description` hoặc `byte[] attachment` lại thuộc nhóm lazy basic attribute:

```java
@Basic(fetch = FetchType.LAZY)
@Lob
private byte[] attachment;
```

Việc nạp lazy trường basic có thể yêu cầu bytecode enhancement và có semantics riêng. Điều kiện để trì hoãn một quan hệ to-one qua proxy **không áp dụng nguyên vẹn** cho một trường `byte[]`. Bởi vậy cần phân biệt:

- Lazy association: trì hoãn tải **entity liên quan**.
- Lazy basic attribute: trì hoãn tải **một số thuộc tính thuộc chính entity**.
- Lazy collection: trì hoãn tải một **tập hợp** liên quan, có cách quản lý khác to-one.

Trong bài này, trọng tâm là khả năng dựng tham chiếu tới **một entity khác** mà chưa phải nạp đầy đủ trạng thái entity ấy.

## 15. Có nên để mọi `@ManyToOne` là LAZY?

Khai báo `LAZY` là lựa chọn phổ biến để tránh tải thừa dữ liệu theo mặc định. Nhưng chiến lược thực tế phụ thuộc cách sử dụng:

- Khi chỉ hiển thị thông tin đơn hàng, thường không cần lấy toàn bộ khách hàng.
- Khi hiển thị đơn hàng **kèm tên khách hàng**, nên fetch đúng dữ liệu trong truy vấn.
- Khi màn hình danh sách chỉ cần ID của customer, có thể chọn projection chỉ lấy cột khóa ngoại hoặc ánh xạ thích hợp.
- Khi một object graph phục vụ nghiệp vụ luôn cần association cụ thể, có thể thiết kế fetch plan tương ứng ở repository.

Tối ưu không phải là “không bao giờ fetch customer”; tối ưu là **chỉ fetch đúng dữ liệu cần ở đúng thời điểm, với số truy vấn chấp nhận được**.

### Batch fetching khi cần nhiều to-one lazy

Hibernate có cơ chế batch fetching cho proxy/entity chưa initialized. Khi truy cập một proxy, Hibernate có thể tải nhiều proxy cùng loại trong một truy vấn theo batch-size được cấu hình, giảm số query so với N+1 thuần túy.

Ví dụ annotation riêng Hibernate:

```java
import org.hibernate.annotations.BatchSize;

@Entity
@BatchSize(size = 20)
public class Customer {
    @Id
    private Long id;

    private String name;

    protected Customer() {}
}
```

Batch fetching **không đồng nghĩa** tải toàn bộ graph luôn trong một query và không thay thế fetch join/projection ở mọi trường hợp. Hiệu quả còn phụ thuộc số proxy chưa initialized, cấu hình và query thực tế.

### Fetch join và phân trang

Fetch join một to-one association thường ít gây nhân bản hàng kết quả hơn fetch join collection, nên có thể phù hợp khi phân trang danh sách order kèm customer. Tuy nhiên, nếu fetch nhiều quan hệ, ghép query phức tạp hoặc thay đổi cardinality, vẫn cần kiểm tra SQL và pagination trên DB thật.

Nếu fetch join collection đồng thời với pagination, rủi ro phình dữ liệu và xử lý phân trang trong bộ nhớ lớn hơn nhiều. Không nên khái quát lời khuyên từ to-one sang mọi association.

## 16. Thiết kế ánh xạ `@OneToOne` có chủ đích

Khi mô hình domain chứa một cặp thực thể 1–1, trước khi quyết định để association lazy hãy trả lời:

1. **Bảng nào giữ khóa ngoại?** Phía sở hữu có thể đọc ID đích từ hàng nguồn dễ hơn.
2. **Quan hệ có tùy chọn không?** Nếu có thể không tồn tại, phía ngược có thể cần kiểm tra `null`.
3. **Có thể dùng shared primary key không?** Shared PK giúp biết ID liên quan, nhưng vẫn phải giải quyết bài toán tồn tại.
4. **Có thật sự cần điều hướng hai chiều không?** Nếu không, giảm một mapping có thể làm mô hình đơn giản hơn.
5. **Hibernate version và enhancement được cấu hình thế nào?** Lazy inverse one-to-one không nên dự đoán chỉ qua annotation.
6. **Use case sẽ truy cập entity đích khi nào?** Nếu luôn truy cập, fetch sớm có thể phù hợp hơn trì hoãn rồi tạo secondary select.

Ví dụ một hệ thống có entity `User` và `UserSettings`. Nếu phần lớn thao tác chỉ cần user, có thể tách cài đặt thành entity riêng và **không đặt `User.settings`**. Truy vấn lấy settings khi cần:

```java
UserSettings settings = em.createQuery("""
    select s
    from UserSettings s
    where s.user.id = :userId
    """, UserSettings.class)
    .setParameter("userId", userId)
    .getSingleResult();
```

Thiết kế này làm việc truy cập settings trở thành một **hành động truy vấn rõ ràng**, tránh phụ thuộc vào khả năng Hibernate suy ra trạng thái của inverse one-to-one.

Nếu settings bắt buộc được tạo cùng user và dùng shared primary key, navigation hai chiều có thể phù hợp; khi ấy nên chọn mapping và fetch strategy dựa trên invariants thực tế.

## 17. Cascade và orphan removal không quyết định lazy loading

Một hiểu nhầm khác là `cascade = CascadeType.ALL` sẽ khiến association eager hoặc bảo đảm Hibernate tự fetch nó. **Cascade** và **fetch** giải quyết hai vấn đề khác nhau:

- **Cascade**: một số thao tác persistence như `PERSIST`, `MERGE`, `REMOVE` có lan sang entity liên quan không.
- **Fetch**: khi truy xuất entity nguồn, dữ liệu liên quan được tải khi nào.

Ví dụ:

```java
@OneToOne(
    mappedBy = "account",
    fetch = FetchType.LAZY,
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private AccountProfile profile;
```

Ở đây:

- `fetch = LAZY` yêu cầu trì hoãn việc tải profile khi có thể.
- `cascade = ALL` quyết định lan các thao tác lifecycle tương ứng.
- `orphanRemoval = true` quy định hành vi xóa child khi quan hệ bị ngắt theo semantics mapping.

Không suy luận rằng do có cascade nên Hibernate bắt buộc luôn load profile vào lúc đọc Account. Ngược lại, khi thực hiện thao tác lifecycle cụ thể, Hibernate có thể cần xử lý hoặc truy vấn liên quan đến child để bảo đảm semantics; đó là hành vi của thao tác được yêu cầu, không phải định nghĩa của fetch mode.

## 18. Cách quan sát hành vi lazy to-one một cách có ý nghĩa

Để hiểu mapping trong ứng dụng, có thể quan sát ở một transaction với cache đã được kiểm soát.

### Trường hợp 1: chỉ cần order

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 101L);
Long id = order.getId();
```

Kỳ vọng đối với mapping `@ManyToOne(fetch = LAZY)` thông thường: không cần nạp Customer chỉ để đọc ID của Order.

### Trường hợp 2: lấy tham chiếu customer

```java
Customer customer = order.getCustomer();
boolean initialized = Hibernate.isInitialized(customer);
```

Nếu proxy lazy được dùng và Customer chưa có trong persistence context/cache, `initialized` có thể là `false`. Nhưng không phải mọi mapping hoặc fetch plan đều làm như vậy.

### Trường hợp 3: truy cập dữ liệu thật

```java
String customerName = customer.getName();
```

Nếu Customer chưa nạp, Hibernate có thể thực hiện SQL bổ sung. Cần phân biệt truy vấn do truy cập association với truy vấn thứ cấp do eager fetch hoặc do inverse one-to-one phải kiểm tra tồn tại.

### Trường hợp 4: lấy danh sách

```java
List<PurchaseOrder> orders = em.createQuery(
    "select o from PurchaseOrder o",
    PurchaseOrder.class
).getResultList();
```

Nếu tiếp tục lặp qua `order.getCustomer().getName()`, quan sát tổng số SQL và cân nhắc fetch join/projection để tránh N+1.

**Lưu ý:** SQL log không nhất thiết hiển thị rõ việc query có đến từ cache hoặc prepared statement reuse; quan sát thực tế nên tính đến cơ chế cache của Hibernate và database. Một lần không thấy SQL không đủ chứng minh association luôn lazy; một lần có SQL cũng chưa nói rõ SQL đó đến từ bước nào nếu không xem call path.

## 19. Những hiểu lầm thường gặp

**“`@ManyToOne` mặc định lazy giống `@OneToMany`.”**  
Không đúng theo Jakarta Persistence: to-one mặc định `EAGER`. Muốn trì hoãn, khai báo `fetch = LAZY` có chủ đích.

**“`fetch = LAZY` bảo đảm không có `SELECT` thứ cấp.”**  
Không đúng. Có thể cần SQL do inverse one-to-one, thiếu proxy/enhancement, truy cập association hoặc fetch plan khác.

**“Một proxy khác null nghĩa là entity đã được tải hết.”**  
Không đúng. Proxy có thể chỉ biết ID, còn thuộc tính thật chưa loaded.

**“Gọi `getCustomer()` luôn truy vấn database.”**  
Không đúng với proxy-based lazy loading thông dụng: có thể chỉ trả proxy. Nhưng getter tiếp theo hoặc logic tùy biến có thể initialize proxy.

**“`optional = false` khiến inverse `@OneToOne` chắc chắn lazy.”**  
Không có bảo đảm như vậy. Nó cung cấp thông tin về tính bắt buộc; Hibernate vẫn cần đủ thông tin để xác định đích và có thể phụ thuộc enhancement/kiểu khóa.

**“`@MapsId` tự bảo đảm đối tượng đích tồn tại.”**  
Không đúng. Shared ID giúp suy ra identifier nhưng không tự chứng minh row liên quan tồn tại khi quan hệ là tùy chọn.

**“Nếu tránh `LazyInitializationException` bằng OSIV thì hiệu năng đã ổn.”**  
Không. OSIV có thể khiến lazy SQL chạy ở tầng view và che N+1. Cần chọn fetch plan theo nhu cầu thực tế.

**“Đặt `@NotFound` cho khóa ngoại hỏng sẽ giữ được lazy.”**  
Hibernate thường cần kiểm tra tham chiếu và có thể ép eager fetch. Điều này cũng không thay thế ràng buộc toàn vẹn trong database.

**“Mọi entity quan hệ đơn trị nên được eager để giảm truy vấn.”**  
Không đúng. Eager có thể tải dư dữ liệu hoặc sinh secondary select. Lazy cùng truy vấn được thiết kế cho từng use case thường kiểm soát chi phí tốt hơn.

## 20. Quy trình lựa chọn cho từng quan hệ đơn trị

Khi thêm một association mới, có thể tiến hành theo trình tự:

1. **Xác định cardinality và ownership.** Đây là `@ManyToOne` hay `@OneToOne`? Bảng nào chứa FK?
2. **Xác định nullability thực tế.** Cột có thể null không? Quan hệ 1–1 phía ngược có thật sự luôn tồn tại?
3. **Khai báo fetch phù hợp.** Với association không luôn cần, bắt đầu bằng `LAZY` và đánh giá khả năng provider thực hiện.
4. **Xem entity có proxy/enhancement phù hợp không.** Tránh cấu trúc class cản trở lazy mechanism; xác nhận version nếu cần enhancement.
5. **Xác định dữ liệu từng use case thực sự dùng.** Viết fetch join/entity graph hoặc DTO projection khi chắc chắn cần target.
6. **Giữ ranh giới transaction/Session rõ ràng.** Không trả entity chưa chuẩn bị dữ liệu cần thiết cho serializer truy cập ngoài context.
7. **Quan sát SQL và số lượt truy vấn.** Chú ý N+1, secondary select, inverse one-to-one và ảnh hưởng cache.
8. **Tách navigation không cần thiết.** Đôi khi query trực tiếp entity liên quan đơn giản hơn cố ép inverse one-to-one lazy.

### Bảng ghi nhớ

| Mapping/tình huống | Có sẵn ID của target từ hàng nguồn? | Khả năng trì hoãn thường gặp |
|---|---|---|
| `@ManyToOne` ở phía giữ FK khác null | Có | Có thể tạo proxy/đại diện lazy khi cấu hình hỗ trợ |
| `@ManyToOne` với FK null | Không có target | Trả `null`, không cần tải entity đích |
| `@OneToOne` phía sở hữu FK | Thường có khi FK khác null | Tương tự to-one owning side; phụ thuộc proxy/enhancement |
| `@OneToOne` phía ngược, optional, FK ở bảng đích | Thường không | Có thể cần SELECT xác định tồn tại/ID; khó lazy hơn |
| `@OneToOne` shared primary key | Có thể suy ra ID từ PK nguồn | Giúp trì hoãn, nhưng vẫn phải xử lý trường hợp target không tồn tại |
| `JOIN FETCH`/fetch graph yêu cầu tải | Không phụ thuộc proxy | Association được fetch theo query |
| Lazy association sau khi Session đóng | Proxy có thể còn nhưng thiếu khả năng nạp | Truy cập dữ liệu chưa loaded có thể lỗi |

**Kết luận:** tham chiếu trì hoãn trong Hibernate là sự phối hợp giữa **metadata quan hệ, định danh biết trước, cơ chế proxy/bytecode enhancement, fetch plan và vòng đời Session**. Với `@ManyToOne` hoặc phía sở hữu `@OneToOne`, khóa ngoại có sẵn thường tạo điều kiện để giữ một tham chiếu nhẹ mà chưa tải entity đích. Với phía ngược của `@OneToOne`, đặc biệt khi quan hệ tùy chọn, Hibernate có thể phải kiểm tra liệu target có tồn tại hay không. Muốn tránh tải thừa và tránh N+1, cần kết hợp ánh xạ `LAZY` với truy vấn đúng nhu cầu, thay vì chỉ dựa vào một annotation.
