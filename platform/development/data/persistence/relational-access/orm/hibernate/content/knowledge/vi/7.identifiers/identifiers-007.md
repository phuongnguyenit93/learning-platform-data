# Định danh phụ thuộc và `@MapsId`

Trong Hibernate/Jakarta Persistence, mỗi entity cần một **định danh** (*identifier*, thường là khóa chính `PRIMARY KEY`) để phân biệt các bản ghi. Thông thường entity tự có một `id` riêng. Tuy nhiên, một số thực thể **không thể xác định danh tính nếu thiếu thực thể khác**: thông tin cấu hình tài khoản mang cùng ID với tài khoản; một dòng đơn hàng được xác định bằng `(order_id, line_no)`; một lượt đăng ký học được xác định bằng `(student_id, course_id)`.

Đây là những trường hợp của **định danh phụ thuộc** (*derived identity*): toàn bộ hoặc một phần khóa chính của entity phụ thuộc được lấy từ khóa chính của entity cha. Jakarta Persistence cung cấp annotation **`@MapsId`** để liên kết quan hệ `@OneToOne` hoặc `@ManyToOne` với thuộc tính định danh đó.

Nắm chắc `@MapsId` giúp ánh xạ đúng **PK đồng thời là FK**, tránh khai báo cùng một cột hai lần, quản lý thứ tự lưu entity có phụ thuộc, và giữ mô hình Java nhất quán với ràng buộc quan hệ trong database.

## 1. Mô hình tư duy: khóa chính độc lập và khóa chính phụ thuộc

Giả sử có hai bảng:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE account_settings (
    account_id BIGINT PRIMARY KEY,
    theme VARCHAR(20) NOT NULL,
    CONSTRAINT fk_settings_account
        FOREIGN KEY (account_id) REFERENCES accounts(id)
);
```

`account_settings.account_id` vừa là:

- **Primary key (PK)** của hàng `account_settings`: tối đa một bộ settings cho mỗi tài khoản.
- **Foreign key (FK)** tham chiếu `accounts.id`: mỗi bộ settings thuộc về một tài khoản có thật.

Quan hệ dữ liệu:

```text
accounts                                   account_settings
+--------+------------+                   +------------+--------+
| id PK  | username   |                   | account_id | theme  |
+--------+------------+                   +------------+--------+
| 101    | "anna"     |------------------>| 101        | "dark" |
| 102    | "binh"     |                   +------------+--------+
+--------+------------+                          PK + FK
                   1 -------- 0..1
```

Ở đây, ID của `AccountSettings` **không được sinh độc lập**. Nó được suy ra từ `Account.id`. Tập giá trị có thể có của `account_settings.account_id` phụ thuộc vào tập khóa của `accounts`, và việc đổi chủ sở hữu sẽ đồng thời đổi danh tính của settings.

So với mô hình một-một có khóa riêng:

```sql
CREATE TABLE account_settings_independent (
    id BIGINT PRIMARY KEY,               -- PK riêng
    account_id BIGINT NOT NULL UNIQUE,   -- FK duy nhất
    theme VARCHAR(20) NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
```

Cả hai có thể biểu diễn một quan hệ một-một ở mức dữ liệu, nhưng **chỉ mô hình đầu có PK phụ thuộc**. Trong mô hình thứ hai, `id` và `account_id` là hai thuộc tính riêng; không nên dùng `@MapsId` nếu muốn giữ khóa chính độc lập.

### 1.1. Các dạng định danh phụ thuộc

| Dạng | Khóa chính của entity phụ thuộc | Quan hệ thường gặp | Mapping điển hình |
| --- | --- | --- | --- |
| **PK dùng chung** | Bằng toàn bộ PK của entity cha | `@OneToOne` | `@Id` + `@OneToOne` + `@MapsId` |
| **PK ghép chứa một FK** | `(parent_id, local_key)` | `@ManyToOne` | `@EmbeddedId` + `@MapsId("parentId")` |
| **PK ghép chứa nhiều FK** | `(first_parent_id, second_parent_id)` | Hai quan hệ `@ManyToOne` | `@EmbeddedId` + nhiều `@MapsId("...")` |
| **PK ghép với PK cha cũng là khóa ghép** | Chứa các thành phần PK của cha | `@ManyToOne` hoặc `@OneToOne` | `@EmbeddedId` có thuộc tính đúng kiểu khóa cha + `@MapsId` |

Điểm chung là **FK tạo nên một phần hoặc toàn bộ PK**, chứ không đơn thuần có một foreign key thông thường.

## 2. `@MapsId` định nghĩa chính xác điều gì?

Annotation chuẩn được import từ:

```java
import jakarta.persistence.MapsId;
```

Đặt trên một quan hệ `@OneToOne` hoặc `@ManyToOne`, nó thông báo rằng **quan hệ này cung cấp giá trị khóa chính** cho thuộc tính được đánh dấu `@Id`, `@EmbeddedId`, hoặc một thành phần trong `@EmbeddedId`.

Ví dụ:

```java
@Id
private Long id;

@OneToOne(fetch = FetchType.LAZY, optional = false)
@MapsId
@JoinColumn(name = "account_id")
private Account account;
```

Khi `account.id = 101`, định danh của entity có quan hệ `@MapsId` cũng là `101`. Hibernate sử dụng quan hệ `account` để gắn giá trị đó vào ID của entity phụ thuộc.

Với khóa ghép:

```java
@EmbeddedId
private OrderLineId id;

@ManyToOne(fetch = FetchType.LAZY, optional = false)
@MapsId("orderId")
@JoinColumn(name = "order_id")
private PurchaseOrder order;
```

Chuỗi `"orderId"` là **tên thuộc tính Java của lớp `OrderLineId`**, không phải tên cột SQL. Phần `orderId` trong `OrderLineId` lấy giá trị từ khóa chính của `PurchaseOrder`.

### 2.1. Có hoặc không có tham số `value`

| Cú pháp | Ý nghĩa |
| --- | --- |
| `@MapsId` hoặc `@MapsId("")` | Quan hệ cung cấp toàn bộ định danh của entity phụ thuộc; thường dùng với shared PK |
| `@MapsId("orderId")` | Quan hệ cung cấp một thành phần mang tên `orderId` trong composite ID |
| `@MapsId("studentId")`, `@MapsId("courseId")` | Hai quan hệ cung cấp hai thành phần khác nhau trong composite ID |

Với entity chỉ có khóa chính đơn giản giống kiểu ID của cha, có thể bỏ tên thuộc tính. Với `@EmbeddedId` chứa **nhiều thành phần**, cần chỉ rõ tên thành phần được ánh xạ bằng `@MapsId("...")`.

`@MapsId` **không phải** công cụ sinh số ID như `@GeneratedValue`. Nó lấy định danh từ **quan hệ cha**; việc khóa cha được sinh bằng sequence, identity, UUID hay được ứng dụng gán thủ công là một cơ chế khác.

## 3. Ví dụ 1 — `@OneToOne` dùng chung primary key

Xây dựng hai entity:

- `Account`: tài khoản, có ID sinh bởi database.
- `AccountSettings`: cấu hình đi kèm tài khoản, lấy chính ID của tài khoản làm PK.

### 3.1. Bảng SQL

```sql
CREATE TABLE accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE account_settings (
    account_id BIGINT PRIMARY KEY,
    theme VARCHAR(20) NOT NULL,
    CONSTRAINT fk_account_settings_account
        FOREIGN KEY (account_id) REFERENCES accounts(id)
);
```

Cú pháp `GENERATED BY DEFAULT AS IDENTITY` tương ứng một số DBMS như PostgreSQL hiện đại; hệ quản trị khác có thể dùng cú pháp sinh khóa khác. Các ràng buộc PK và FK mới là phần quan trọng của bài.

### 3.2. Entity cha `Account`

```java
import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "accounts")
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "username", nullable = false, unique = true)
    private String username;

    @OneToOne(
        mappedBy = "account",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private AccountSettings settings;

    protected Account() {
    }

    public Account(String username) {
        this.username = Objects.requireNonNull(username);
    }

    public Long getId() {
        return id;
    }

    public AccountSettings getSettings() {
        return settings;
    }

    public void attachSettings(AccountSettings settings) {
        this.settings = Objects.requireNonNull(settings);
        settings.assignAccount(this);
    }
}
```

`mappedBy = "account"` chỉ ra **phía sở hữu quan hệ là thuộc tính `AccountSettings.account`**. Khai báo `cascade` giúp việc persist/remove từ cha lan sang entity con trong ví dụ. **Không có luật nào nói `@MapsId` tự bật cascade**; đây là lựa chọn lifecycle rõ ràng ở entity cha.

`orphanRemoval = true` chỉ phù hợp nếu `AccountSettings` thật sự phụ thuộc vòng đời vào `Account` trong domain. Nếu hệ thống có chính sách giữ lại dữ liệu hoặc xóa mềm, phải xem lại lựa chọn này.

### 3.3. Entity phụ thuộc `AccountSettings`

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.MapsId;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "account_settings")
public class AccountSettings {

    @Id
    @Column(name = "account_id")
    private Long id;

    @MapsId
    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "account_id", nullable = false)
    private Account account;

    @Column(name = "theme", nullable = false, length = 20)
    private String theme;

    protected AccountSettings() {
    }

    public AccountSettings(String theme) {
        this.theme = Objects.requireNonNull(theme);
    }

    void assignAccount(Account account) {
        this.account = Objects.requireNonNull(account);
    }

    public Long getId() {
        return id;
    }

    public Account getAccount() {
        return account;
    }

    public String getTheme() {
        return theme;
    }
}
```

Cần quan sát bốn điểm:

1. `id` **không có** `@GeneratedValue`; ID của settings đến từ `account.id`.
2. `@MapsId` đặt trên **quan hệ sở hữu** `AccountSettings.account`, không phải trên `Account.settings`.
3. `@JoinColumn(name = "account_id")` dùng **cùng cột** vừa là FK tới `accounts`, vừa là PK của `account_settings`.
4. `fetch = FetchType.LAZY` là yêu cầu lấy dữ liệu lười; với `@OneToOne`, khả năng tránh SQL phụ thuộc phía quan hệ, enhancement và provider. Không nên hứa rằng mọi truy cập đến settings đều hoàn toàn không phát sinh SQL.

Mô hình này không có hai cột ID riêng biệt và không đòi hỏi khai báo cặp `insertable = false, updatable = false` chỉ để tránh lặp mapping. `@MapsId` diễn đạt sự dùng chung cột theo chuẩn JPA.

### 3.4. Persist cha và con trong một transaction

Trong một ứng dụng Java SE dùng transaction resource-local:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityTransaction;

EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Account account = new Account("anna");
    AccountSettings settings = new AccountSettings("dark");
    account.attachSettings(settings);

    em.persist(account); // CascadeType.ALL đưa settings vào persistence context.

    tx.commit(); // Hibernate đồng bộ và commit trong transaction.
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Có thể hình dung kết quả SQL:

```sql
INSERT INTO accounts(username) VALUES ('anna');
-- database cấp ID, ví dụ 101

INSERT INTO account_settings(account_id, theme)
VALUES (101, 'dark');
```

Đây là **SQL minh họa**, không phải cam kết về chuỗi SQL chính xác mà Hibernate sẽ phát ra: cách sinh ID, thứ tự flush và statement batching phụ thuộc mapping, dialect và phiên bản. Ràng buộc bất biến sau commit là:

```text
Account.id              = 101
AccountSettings.id      = 101
AccountSettings.account = Account có id 101
```

**Không giả định `settings.getId()` đã có giá trị ngay tại thời điểm constructor chạy hoặc ngay sau `persist()` trước `flush()`.** Với `@MapsId`, việc đồng bộ giá trị ID Java có thể hoàn tất trong pha flush, tùy provider và cách tạo ID cha.

### 3.5. Tìm entity phụ thuộc bằng khóa của cha

```java
AccountSettings settings = em.find(AccountSettings.class, 101L);

if (settings != null) {
    System.out.println(settings.getTheme());
}
```

Không cần truy vấn theo `account.id` bằng `JOIN` chỉ để tìm khóa con: `101` chính là primary key của `AccountSettings`. Khi dùng quan hệ cha trong truy vấn JPQL:

```java
AccountSettings settings = em.createQuery(
        "select s from AccountSettings s where s.account.id = :accountId",
        AccountSettings.class
    )
    .setParameter("accountId", 101L)
    .getSingleResult();
```

`getSingleResult()` sẽ ném exception nếu không tìm thấy kết quả (và hành vi khác nếu có nhiều kết quả). Với tình huống cần tìm tùy chọn, có thể dùng `find()` theo ID hoặc API query thích hợp.

## 4. Vì sao shared PK thực sự tạo quan hệ một-một?

Trong bảng `account_settings`, `account_id` là **PRIMARY KEY** nên không thể có hai hàng:

```text
(account_id=101, theme='dark')
(account_id=101, theme='light')  ← vi phạm PK
```

FK yêu cầu `101` tồn tại trong `accounts`. Kết hợp:

- Mỗi hàng settings tham chiếu **đúng một** account.
- Mỗi account có **tối đa một** settings.
- Một account có thể **chưa có** settings nếu không có ràng buộc khác buộc nó tồn tại.

Chính xác hơn, mô hình bảng thường diễn đạt **Account 1 → 0..1 AccountSettings**, dù `AccountSettings.account` là bắt buộc. Để yêu cầu mỗi tài khoản phải có settings ngay khi tạo, cần đảm bảo ở nghiệp vụ, transaction hoặc kiến trúc lưu trữ; FK của bảng con không tự ép bảng cha phải có con.

Đây là khác biệt giữa:

- **Bội số quan hệ (*cardinality*)** được bảo vệ bằng PK/UNIQUE và FK.
- **Sự tồn tại bắt buộc của con theo cha** thường là một quy tắc nghiệp vụ.

## 5. Ví dụ 2 — `@ManyToOne` tạo một phần của khóa ghép

Dòng đơn hàng (*order line*) có thể được xác định bằng:

```text
(order_id, line_no)
```

Trong đó:

- `order_id` đến từ thực thể `PurchaseOrder`.
- `line_no` là số dòng chỉ có ý nghĩa **trong phạm vi một đơn hàng**.

Đơn hàng `200` và đơn hàng `201` đều có thể có dòng `1`; nhưng **không được có hai dòng `(200, 1)`**.

### 5.1. Schema

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (order_id, line_no),
    FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    CONSTRAINT ck_order_lines_quantity CHECK (quantity > 0)
);
```

Mô hình khóa:

```text
purchase_orders                      order_lines
+---------+--------------+           +----------+---------+--------------+
| id PK   | order_number |           | order_id | line_no | product_name |
+---------+--------------+           +----------+---------+--------------+
| 200     | "PO-200"     |-----------| 200      | 1       | "Keyboard"   |
|         |              |-----------| 200      | 2       | "Mouse"      |
+---------+--------------+           +----------+---------+--------------+
                                    PRIMARY KEY(order_id, line_no)
                                       ^ FK tới purchase_orders.id
```

### 5.2. Khóa ghép `OrderLineId`

```java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class OrderLineId implements Serializable {

    @Column(name = "order_id", nullable = false)
    private Long orderId;

    @Column(name = "line_no", nullable = false)
    private Integer lineNo;

    protected OrderLineId() {
    }

    public OrderLineId(Long orderId, Integer lineNo) {
        this.orderId = orderId;
        this.lineNo = lineNo;
    }

    public Long getOrderId() {
        return orderId;
    }

    public Integer getLineNo() {
        return lineNo;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderLineId that)) return false;
        return Objects.equals(orderId, that.orderId)
            && Objects.equals(lineNo, that.lineNo);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNo);
    }
}
```

`OrderLineId` là một **value object đại diện khóa**, được đánh dấu `@Embeddable`. Nó có constructor không tham số, các trường của khóa và cách so sánh bằng giá trị (`equals()`/`hashCode()`); thiết kế này phù hợp với nguyên tắc định danh ghép trong Jakarta Persistence.

Để tránh thay đổi identity sau khi persist, **không cung cấp setter tự do cho khóa**. `orderId` có thể bắt đầu `null` khi đối tượng Java mới được tạo vì ID của đơn cha chưa được cấp; Hibernate sẽ ánh xạ phần này từ quan hệ `order` theo `@MapsId`.

### 5.3. Entity cha `PurchaseOrder`

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public Long getId() {
        return id;
    }
}
```

Ở ví dụ này, `PurchaseOrder` chưa có danh sách `lines`. Không cần quan hệ hai chiều nếu nghiệp vụ chưa cần từ order đi tới các line; **quan hệ một chiều** ở `OrderLine.order` đã đủ để ánh xạ derived identity.

### 5.4. Entity phụ thuộc `OrderLine`

```java
import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.MapsId;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @EmbeddedId
    private OrderLineId id;

    @MapsId("orderId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_name", nullable = false, length = 150)
    private String productName;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected OrderLine() {
    }

    public OrderLine(
        PurchaseOrder order,
        int lineNo,
        String productName,
        int quantity
    ) {
        this.order = Objects.requireNonNull(order);
        this.id = new OrderLineId(null, lineNo);
        this.productName = Objects.requireNonNull(productName);

        if (lineNo <= 0 || quantity <= 0) {
            throw new IllegalArgumentException(
                "lineNo and quantity must be positive"
            );
        }
        this.quantity = quantity;
    }

    public OrderLineId getId() {
        return id;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    public Integer getLineNo() {
        return id.getLineNo();
    }
}
```

Cơ chế then chốt:

```text
order.id = 200
line.id = (orderId = null, lineNo = 1)
line.order = order

@MapsId("orderId")
             ↓
Giá trị khóa chính tương ứng trong line.id được suy ra từ order.id

Sau đồng bộ:
line.id = (orderId = 200, lineNo = 1)
```

`@MapsId("orderId")` **không** có nghĩa Hibernate lấy `lineNo` từ order. Nó chỉ ánh xạ đúng một thành phần khóa ghép mang tên `orderId`.

### 5.5. Persist theo thứ tự phụ thuộc

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    PurchaseOrder order = new PurchaseOrder("PO-200");
    em.persist(order);

    OrderLine first = new OrderLine(order, 1, "Keyboard", 2);
    OrderLine second = new OrderLine(order, 2, "Mouse", 1);

    em.persist(first);
    em.persist(second);

    // Có thể flush nếu cần đọc ID đã được đồng bộ ngay trong transaction.
    em.flush();

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Sau khi đồng bộ thành công:

```text
purchase_orders.id = 200

order_lines:
(order_id = 200, line_no = 1, product_name = "Keyboard", quantity = 2)
(order_id = 200, line_no = 2, product_name = "Mouse", quantity = 1)
```

Trong ví dụ này, không bật cascade từ `OrderLine` lên `PurchaseOrder`. Ứng dụng **persist parent trước**, rồi persist dependent trong cùng transaction. Nếu parent đã tồn tại và đang managed, chỉ cần gắn đúng reference rồi persist line. Nếu dùng cascade từ aggregate root, khai báo cascade rõ ràng ở phía phù hợp; `@MapsId` tự nó không persist parent.

Đừng lấy thứ tự lệnh SQL thực tế hoặc thời điểm ID xuất hiện trước `flush()` làm hợp đồng bất biến: các chiến lược `IDENTITY`, `SEQUENCE`, flush mode và provider có thể làm thay đổi các thời điểm đó.

### 5.6. Tìm và xóa bằng khóa ghép

```java
OrderLineId key = new OrderLineId(200L, 1);

OrderLine line = em.find(OrderLine.class, key);
if (line != null) {
    em.remove(line); // Trong transaction đang hoạt động.
}
```

`em.find(OrderLine.class, 200L)` **không hợp lệ** cho entity dùng `@EmbeddedId` này; khóa cần là một `OrderLineId` có đầy đủ hai thành phần.

Với Spring Data JPA, repository tương ứng thường khai báo:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderLineRepository
        extends JpaRepository<OrderLine, OrderLineId> {
}
```

Dạng repository này chỉ có ý nghĩa khi dự án đã thêm và cấu hình Spring Data JPA. Hibernate ORM thuần không tự cung cấp `JpaRepository`.

## 6. Ví dụ 3 — Khóa chính được ghép từ **hai khóa ngoại**

Bảng đăng ký học:

```sql
CREATE TABLE students (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL
);

CREATE TABLE courses (
    id BIGINT PRIMARY KEY,
    title VARCHAR(120) NOT NULL
);

CREATE TABLE enrollments (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    enrolled_at TIMESTAMP NOT NULL,
    PRIMARY KEY (student_id, course_id),
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);
```

Ở đây không có `enrollment_id` riêng; định danh của một enrollment là cặp `(student_id, course_id)`.

### 6.1. Id class cho khóa ghép

```java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class EnrollmentId implements Serializable {

    @Column(name = "student_id", nullable = false)
    private Long studentId;

    @Column(name = "course_id", nullable = false)
    private Long courseId;

    protected EnrollmentId() {
    }

    public EnrollmentId(Long studentId, Long courseId) {
        this.studentId = studentId;
        this.courseId = courseId;
    }

    public Long getStudentId() {
        return studentId;
    }

    public Long getCourseId() {
        return courseId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof EnrollmentId that)) return false;
        return Objects.equals(studentId, that.studentId)
            && Objects.equals(courseId, that.courseId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(studentId, courseId);
    }
}
```

Tên `EnrollmentId` là lớp `@Embeddable` dùng với `@EmbeddedId`. Nó **không phải** dạng `@IdClass` dù tên lớp có hậu tố `Id`.

### 6.2. Entity với hai `@MapsId`

Giả sử `Student` và `Course` đã được ánh xạ làm entity có `@Id Long id` và các hàng tương ứng đang tồn tại:

```java
import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.MapsId;
import jakarta.persistence.Table;
import java.time.LocalDateTime;

@Entity
@Table(name = "enrollments")
public class Enrollment {

    @EmbeddedId
    private EnrollmentId id = new EnrollmentId();

    @MapsId("studentId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "student_id", nullable = false)
    private Student student;

    @MapsId("courseId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "course_id", nullable = false)
    private Course course;

    @Column(name = "enrolled_at", nullable = false)
    private LocalDateTime enrolledAt;

    protected Enrollment() {
    }

    public Enrollment(Student student, Course course, LocalDateTime at) {
        this.student = java.util.Objects.requireNonNull(student);
        this.course = java.util.Objects.requireNonNull(course);
        this.enrolledAt = java.util.Objects.requireNonNull(at);
    }

    public EnrollmentId getId() {
        return id;
    }
}
```

`Enrollment` có hai mối quan hệ `@ManyToOne`. Mỗi quan hệ cung cấp **một phần** của khóa ghép. Ví dụ:

```text
student.id = 13
course.id = 8
          ↓
enrollment.id = (studentId = 13, courseId = 8)
```

Bảng `enrollments` vừa biểu diễn quan hệ nhiều-nhiều ở mức dữ liệu, vừa có thể mang các thuộc tính nghiệp vụ như `enrolled_at`, trạng thái, điểm số. Khi cần entity trung gian có dữ liệu riêng, mapping này thường diễn đạt domain tốt hơn một `@ManyToMany` đơn giản.

> Các đoạn về `Enrollment` giả định đã có hai entity `Student` và `Course`. Trong ứng dụng đầy đủ, chúng cần mapping `@Entity` và `@Id` của riêng mình, còn `Enrollment` chỉ được persist sau khi gắn hai reference hợp lệ.

## 7. Trường hợp cha cũng có khóa ghép

Một phụ thuộc có thể chứa **toàn bộ khóa ghép của cha** như một thành phần của khóa con.

Ví dụ cha `Shipment` có khóa `(warehouseCode, shipmentNo)`, con `ShipmentItem` có khóa `(shipmentKey, itemNo)`:

```text
Shipment PK:     ShipmentId(warehouseCode, shipmentNo)
ShipmentItem PK: ShipmentItemId(shipmentId: ShipmentId, itemNo)
```

Cấu trúc minh họa:

```java
@Embeddable
public class ShipmentId implements java.io.Serializable {
    // warehouseCode, shipmentNo, equals(), hashCode(), ...
}

@Embeddable
public class ShipmentItemId implements java.io.Serializable {
    private ShipmentId shipmentId;
    private Integer itemNo;
    // constructor không tham số, equals(), hashCode(), ...
}

@Entity
public class ShipmentItem {

    @EmbeddedId
    private ShipmentItemId id;

    @MapsId("shipmentId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumns({
        @JoinColumn(
            name = "warehouse_code",
            referencedColumnName = "warehouse_code"
        ),
        @JoinColumn(
            name = "shipment_no",
            referencedColumnName = "shipment_no"
        )
    })
    private Shipment shipment;
}
```

Đoạn này là **sơ đồ mapping rút gọn**; để biên dịch/chạy cần khai báo đầy đủ `Shipment`, các lớp ID, import và column mapping thống nhất. Điểm cốt lõi là `@MapsId("shipmentId")` trỏ tới thuộc tính `shipmentId` có **cùng kiểu khóa của cha** (`ShipmentId`), còn `@JoinColumns` ánh xạ đủ các cột FK.

Khi dùng `@EmbeddedId`, **không đặt quan hệ entity bên trong lớp khóa chỉ để thuận tiện** nếu muốn bảo đảm portable theo Jakarta Persistence. Hibernate có hỗ trợ mở rộng cho quan hệ trong composite ID, nhưng cách chuẩn và dễ hiểu hơn là giữ ID dưới dạng **các giá trị khóa**, đặt quan hệ trên entity và dùng `@MapsId`.

## 8. Tại sao không chỉ khai báo cả `@Id` và `@JoinColumn` độc lập?

Một cách mapping không diễn đạt derived identity:

```java
@Id
@Column(name = "account_id")
private Long id;

@OneToOne
@JoinColumn(name = "account_id")
private Account account;
```

Hai thuộc tính có thể cùng cố gắng quản lý **một cột insert/update**, làm Hibernate báo lỗi dạng:

```text
Repeated column in mapping ... column: account_id
(should be mapped with insert="false" update="false")
```

Hoặc người lập trình tạm thêm:

```java
@JoinColumn(
    name = "account_id",
    insertable = false,
    updatable = false
)
```

Cách sau có thể giải quyết xung đột ghi cột trong một số mapping, nhưng **vẫn phải tự bảo đảm giá trị `id` và `account.id` nhất quán**. Nó không nói rằng khóa con được suy ra từ khóa cha.

Với trường hợp derived identity đúng nghĩa, dùng:

```java
@Id
private Long id;

@OneToOne(optional = false)
@MapsId
@JoinColumn(name = "account_id")
private Account account;
```

`@MapsId` vừa thể hiện ý nghĩa domain, vừa hướng provider thống nhất cột PK/FK thay vì duy trì hai thuộc tính ghi độc lập.

**Lưu ý:** Có những mô hình cần FK để tham chiếu cha nhưng PK của con vẫn độc lập. Khi đó **không dùng** `@MapsId`; hãy map `@ManyToOne`/`@OneToOne` thông thường, kết hợp `UNIQUE` nếu muốn quan hệ một-một.

## 9. Vòng đời entity và quy tắc bắt buộc của derived identity

Jakarta Persistence quy định: nếu định danh của dependent được suy ra qua `@MapsId` hoặc một quan hệ `@Id`, **không thể làm cho dependent trở thành persistent trước khi đã gán tham chiếu tới entity cha**.

Hãy phân biệt:

- **Gán tham chiếu cha:** `line.order = order` hoặc `settings.account = account`.
- **Làm cha persistent:** `em.persist(order)` hoặc lấy một parent đang managed.
- **Làm con persistent:** `em.persist(line)`; phụ thuộc có thể cascade từ aggregate root nếu được cấu hình.

Một quy trình thông thường:

```text
1. Tạo hoặc load cha
2. Gán cha vào con
3. Persist cha nếu cha mới (hoặc cấu hình cascade hợp lệ)
4. Persist con / cascade persist
5. Flush / commit: provider đồng bộ FK + PK phụ thuộc
```

### 9.1. Con không có parent

```java
AccountSettings settings = new AccountSettings("dark");
em.persist(settings); // Chưa gán settings.account!
```

Đây là trạng thái không hợp lệ cho shared-PK derived identity. Lỗi có thể bộc lộ khi persist, flush hoặc commit, tùy provider và chiến lược flush; thường liên quan thiếu parent reference, identifier hoặc foreign key.

**Không khắc phục bằng cách gán thủ công `settings.id = 101` trong khi `settings.account` để `null`.** Với `@MapsId`, quan hệ là nguồn định danh; nó cần tham chiếu phù hợp.

### 9.2. Cha mới nhưng chưa được persist

```java
Account account = new Account("anna");
AccountSettings settings = new AccountSettings("dark");
account.attachSettings(settings);

em.persist(settings); // Nếu không có cascade/parent managed: không bảo đảm.
```

Một số trường hợp sẽ dẫn tới lỗi tham chiếu transient parent khi flush. Đừng dựa vào việc Hibernate có thể tự sắp xếp hoặc phát hiện đối tượng cha chưa managed. Hãy:

```java
em.persist(account);  // Cascade từ Account.settings trong ví dụ mục 3.
```

hoặc persist cha trước, rồi persist con nếu không sử dụng cascade.

### 9.3. `@MapsId` không có nghĩa cascade delete

`@MapsId` diễn đạt **định danh**, không mặc định quản lý **vòng đời**:

```java
@MapsId
@OneToOne(optional = false)
private Account account;
```

Không có câu lệnh nào ở đây tự tương đương với:

```java
cascade = CascadeType.REMOVE
orphanRemoval = true
ON DELETE CASCADE
```

Đó là các quyết định độc lập:

| Cơ chế | Tác dụng |
| --- | --- |
| `@MapsId` | Khóa của con dùng giá trị khóa từ quan hệ cha |
| `CascadeType.PERSIST` | Lan truyền thao tác persist qua quan hệ được khai báo cascade |
| `CascadeType.REMOVE` | Lan truyền thao tác remove ở chiều được khai báo |
| `orphanRemoval = true` | Xóa entity con khi nó trở thành orphan từ quan hệ sở hữu theo quy tắc JPA |
| SQL `ON DELETE CASCADE` | Database tự xóa hàng con khi hàng cha bị xóa ở mức FK |

Nếu cần xóa mềm, audit hoặc lưu lại lịch sử, cascade remove/orphan removal có thể không phù hợp. **Không bật cascade bừa bãi từ con lên cha**, vì xóa một dòng đơn hàng tuyệt đối không nên mặc nhiên xóa cả đơn hàng.

## 10. Có thể thay đổi parent của entity đang managed không?

Xét `OrderLine` có ID `(200, 1)` thuộc `PurchaseOrder(200)`. Nếu đổi:

```java
line.setOrder(otherOrder); // Giả sử otherOrder.id = 201
```

thì về mặt domain, khóa cần trở thành `(201, 1)`. **Đổi khóa chính của entity đã persistent là hành động không được hỗ trợ như một update thông thường** trong mô hình Jakarta Persistence/Hibernate.

Quy tắc thiết kế:

- Khóa chính xác lập **identity ổn định** của entity.
- Đổi parent khi parent ID nằm trong PK đồng nghĩa **đổi danh tính**.
- Nếu nghiệp vụ thật sự cần chuyển dòng từ đơn này sang đơn khác, cân nhắc **xóa entity cũ và tạo entity mới**, với giao dịch, kiểm tra ràng buộc, audit phù hợp.
- Nếu thường xuyên cần chuyển parent, hãy đặt câu hỏi liệu **FK có nên nằm trong PK** hay không. Có thể phù hợp hơn với một PK độc lập và FK thay đổi được.

Tương tự, `lineNo` trong `(order_id, line_no)` không nên tùy ý sửa sau khi entity đã persistent. Muốn đổi thứ tự hiển thị, có thể giữ `line_no` làm định danh ổn định và thêm `display_order` riêng.

## 11. Khóa ghép phải có `equals()` và `hashCode()` chính xác

JPA yêu cầu lớp composite primary key có quy tắc bằng nhau nhất quán với primary key của database. Ví dụ:

```java
OrderLineId a = new OrderLineId(200L, 1);
OrderLineId b = new OrderLineId(200L, 1);
OrderLineId c = new OrderLineId(200L, 2);

System.out.println(a.equals(b)); // true
System.out.println(a.equals(c)); // false
```

Nếu không override `equals()`/`hashCode()`, hai object khóa đại diện cùng `(200, 1)` có thể bị xem như khác nhau trong các collection Java, gây khó hiểu khi tra cứu, cache, so sánh hoặc quản lý identity.

Hãy dùng các thành phần ID có `equals/hashCode` ổn định và tương thích với equality của kiểu dữ liệu database. Tránh giá trị có tính xấp xỉ hoặc thay đổi thường xuyên như `double`, `float`, timestamp bị cắt precision, hay chuỗi có chuẩn hóa khác nhau giữa Java và database.

### 11.1. Đừng đưa các tham chiếu entity vào ID để viết equals

Không nên làm:

```java
@Embeddable
public class OrderLineId {
    private PurchaseOrder order;
    private Integer lineNo;
}
```

Mục tiêu portable của `@EmbeddedId` là chứa **giá trị định danh**, còn quan hệ được đặt ở entity với `@MapsId`. Đưa quan hệ vào lớp ID có thể phụ thuộc hành vi mở rộng của Hibernate, dính proxy/lazy loading và làm equality phức tạp.

### 11.2. Entity equals/hashCode có thể khác khóa ID

Một entity có khóa sinh bởi database thường có ID `null` trước persist. Nếu `equals/hashCode` của entity trực tiếp dựa vào ID có thể đổi từ null sang giá trị sau persist; đưa entity vào `HashSet` trước lúc ID được cấp dễ gây sai lệch.

Với bài này, điều bắt buộc trước hết là **lớp ID ghép** có equality đúng. Còn equality cho entity cần được thiết kế nhất quán với strategy sinh khóa và vòng đời; không tự động sao chép một implementation từ ID class sang entity.

## 12. Đọc dữ liệu với JPQL và repository

Giả sử entity `OrderLine` từ mục 5. Một truy vấn JPQL theo thành phần của ID:

```java
List<OrderLine> lines = em.createQuery(
        "select l from OrderLine l " +
        "where l.id.orderId = :orderId " +
        "order by l.id.lineNo",
        OrderLine.class
    )
    .setParameter("orderId", 200L)
    .getResultList();
```

Một truy vấn tương đương theo quan hệ:

```java
List<OrderLine> lines = em.createQuery(
        "select l from OrderLine l " +
        "where l.order.id = :orderId " +
        "order by l.id.lineNo",
        OrderLine.class
    )
    .setParameter("orderId", 200L)
    .getResultList();
```

Cả hai đều diễn đạt ý định, còn SQL thực tế do Hibernate/dialect tạo ra. Truy cập `l.order.id` trong JPQL không nhất thiết khiến toàn bộ parent object được tải; cần kiểm tra SQL thật khi tối ưu.

Với Spring Data JPA, có thể có:

```java
public interface OrderLineRepository
        extends JpaRepository<OrderLine, OrderLineId> {

    List<OrderLine> findByIdOrderIdOrderByIdLineNo(Long orderId);
}
```

Derived query này đi theo đường thuộc tính `id.orderId`. Đối với ID ghép, repository ID type phải là **`OrderLineId`**, không phải `Long`.

Một lưu ý chuyên sâu: các phương thức `save()` của Spring Data JPA phải xác định entity là mới hay đã tồn tại. Với **ID do ứng dụng gán sẵn** hoặc composite ID không null, cơ chế xác định `isNew` có thể chọn đường `merge()` thay cho `persist()` nếu không có version hay tùy chỉnh cách nhận diện. `@MapsId` **không thay thế** quy tắc này. Khi thao tác insert và thứ tự cascade có ý nghĩa, hãy hiểu cách repository xác định trạng thái new/managed hoặc dùng `EntityManager.persist()` tại ranh giới phù hợp.

## 13. `@MapsId` và các annotation liên quan: chọn cái nào?

| Công cụ | Dùng khi nào | Quan hệ với định danh phụ thuộc |
| --- | --- | --- |
| `@Id` | Entity có một thuộc tính ID đơn giản | Có thể kết hợp `@MapsId` để dùng chung PK với cha |
| `@GeneratedValue` | Entity tự sinh ID theo strategy phù hợp | **Thường thuộc cha**, không thuộc khóa con do `@MapsId` lấy từ cha |
| `@EmbeddedId` | Entity dùng một object biểu diễn khóa ghép | Kết hợp `@MapsId("field")` để một phần khóa lấy từ FK |
| `@IdClass` | Entity biểu diễn khóa ghép qua nhiều thuộc tính `@Id` | Một lựa chọn khác trong JPA cho composite identity; mapping khác ví dụ `@EmbeddedId` |
| `@MapsId` | Quan hệ `@OneToOne`/`@ManyToOne` đóng góp toàn bộ hoặc một phần PK | Trọng tâm của derived identity |
| `@JoinColumn` / `@JoinColumns` | Chỉ rõ tên cột FK và cột được tham chiếu | Cần nhất quán với cột PK phụ thuộc |
| `@PrimaryKeyJoinColumn` | Cấu hình join qua primary key trong một số mô hình | Có thể cần tự đồng bộ giá trị ID thay vì tận dụng hành vi derived identity của `@MapsId` |
| `@UniqueConstraint` / SQL `UNIQUE` | Đảm bảo FK không bị lặp để tạo quan hệ một-một | Không đồng nghĩa FK trở thành PK |
| `cascade`, `orphanRemoval` | Quy định lan truyền hành động và vòng đời | Độc lập với cách tạo/ánh xạ ID |
| `@NaturalId` (Hibernate-specific) | Định danh nghiệp vụ duy nhất, ví dụ mã khách hàng | Không thay thế JPA primary key và không phải `@MapsId` |

### 13.1. Khi nào cân nhắc `@IdClass`?

Nếu muốn biểu diễn composite ID bằng các thuộc tính `@Id` trực tiếp trên entity, có thể dùng `@IdClass`. Nhưng không nên nghĩ `@IdClass` và `@EmbeddedId` chỉ khác cú pháp: đường dẫn JPQL, cấu trúc mã và quy tắc equality khác nhau.

Ví dụ bài học sử dụng `@EmbeddedId` vì nó nhóm thành phần khóa vào một **value object** dễ đọc và minh họa `@MapsId("orderId")` rõ ràng. Với hệ thống đang dùng `@IdClass`, hãy tuân theo mapping của đúng phiên bản Jakarta Persistence và quyết định có chuyển hay không dựa trên kiến trúc hiện tại.

### 13.2. `@PrimaryKeyJoinColumn` khác `@MapsId`

Một mapping shared primary key kiểu cũ có thể dùng `@PrimaryKeyJoinColumn`:

```java
@Id
private Long id;

@OneToOne
@PrimaryKeyJoinColumn(name = "account_id")
private Account account;
```

Với cách này, trong những mô hình cụ thể người lập trình phải bảo đảm **gán đồng bộ ID con từ ID cha**. `@MapsId` diễn đạt trực tiếp quy tắc lấy ID qua quan hệ và thường là phương án phù hợp hơn khi muốn derived identity theo chuẩn JPA.

## 14. Đọc hiểu lỗi khi sử dụng `@MapsId`

### 14.1. Thiếu parent reference

Dấu hiệu: persist child không có parent dẫn đến lỗi identifier/constraint hoặc transaction rollback.

Nguyên nhân: entity phụ thuộc chưa biết danh tính phải lấy từ đâu.

Hướng xử lý: **gán quan hệ cha trước khi persist**, dùng một đối tượng cha hợp lệ và quản lý cascade/thứ tự lưu đúng.

### 14.2. `TransientPropertyValueException` hoặc lỗi transient reference

Dấu hiệu: Hibernate cho biết một object tham chiếu một entity chưa được lưu.

Nguyên nhân thường gặp: con được persist nhưng parent mới vẫn transient và không có cascade cần thiết.

Hướng xử lý: persist parent trước hoặc khai báo cascade từ aggregate root đúng hướng, sau đó persist dependent trong transaction.

### 14.3. `Repeated column in mapping`

Dấu hiệu: cùng một cột như `account_id`, `order_id` bị map nhiều lần để ghi.

Nguyên nhân: khai báo ID scalar và association độc lập cùng muốn quản lý một cột, nhưng không dùng mô hình `@MapsId` phù hợp.

Hướng xử lý: xác định cột đó có thật sự là một phần PK/FK hay không; nếu có, dùng `@MapsId`. Nếu chỉ là một thuộc tính đọc riêng, phải xác định ownership và khả năng ghi phù hợp.

### 14.4. SQL báo vi phạm foreign key

Dấu hiệu: insert vào `order_lines` với `order_id` không tồn tại trong `purchase_orders`.

Nguyên nhân: parent không tồn tại, transaction sai, thứ tự/chính sách cascade sai hoặc đang dùng ID/reference không hợp lệ.

Hướng xử lý: đảm bảo parent đã persistent và được đồng bộ phù hợp, dùng đúng khóa, kiểm tra SQL và ranh giới transaction.

### 14.5. Vi phạm `PRIMARY KEY` hoặc `UNIQUE`

Dấu hiệu: tạo hai `Enrollment` có cùng `(student_id, course_id)`, hoặc tạo hai bộ settings cho cùng account.

Nguyên nhân: domain cố gắng tạo hai entity có cùng danh tính.

Hướng xử lý: chọn đúng hành vi nghiệp vụ **tạo mới, cập nhật entity hiện có hoặc từ chối yêu cầu**. Không giải quyết bằng cách bỏ PK/UNIQUE nếu ràng buộc đó phản ánh chính xác domain.

### 14.6. `@MapsId("...")` không khớp tên field

Dấu hiệu: Hibernate không tìm thấy attribute được chỉ định hoặc mapping không hợp lệ.

Nguyên nhân: `@MapsId("order_id")` dùng **tên cột SQL**, trong khi embeddable khai báo **tên field Java** là `orderId`.

Sai:

```java
@MapsId("order_id")
@ManyToOne
private PurchaseOrder order;
```

Đúng khi id class có field `orderId`:

```java
@MapsId("orderId")
@ManyToOne
private PurchaseOrder order;
```

### 14.7. Thay đổi parent hoặc thành phần PK sau khi persist

Dấu hiệu: lỗi identifier altered, cập nhật không nhất quán hoặc dữ liệu khó theo dõi.

Nguyên nhân: khóa chính phụ thuộc là danh tính entity, không phải field nghiệp vụ có thể sửa tùy ý.

Hướng xử lý: tạo identity mới nếu cần đổi parent, hoặc thiết kế PK độc lập nếu nghiệp vụ chuyển parent là thao tác bình thường.

## 15. Thiết kế database, migration và hiệu năng

### 15.1. Tạo khóa tại database để giữ invariant

`@MapsId` xử lý mapping Java; database cần ràng buộc tương ứng:

```sql
PRIMARY KEY (order_id, line_no)
FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
```

Không chỉ trông chờ vào annotation. Tác vụ ETL, script quản trị hay hệ thống ngoài Hibernate vẫn có thể ghi dữ liệu, nên **PK/FK database** là lớp bảo vệ quan trọng.

### 15.2. Index của khóa ghép

Với PK `(order_id, line_no)`, nhiều DBMS tạo index trên tổ hợp cột này. Các truy vấn như:

```sql
SELECT *
FROM order_lines
WHERE order_id = ?
ORDER BY line_no;
```

thường có khả năng tận dụng index này tốt. Nhưng truy vấn chỉ theo `line_no` chưa chắc sử dụng được index hiệu quả tương đương, tùy engine và statistics. Thứ tự cột trong composite PK có ảnh hưởng tới thiết kế truy vấn/index; đừng chỉ dựa vào việc nó là FK.

### 15.3. Không phải quan hệ phụ thuộc nào cũng nên dùng composite PK

Ưu điểm của `(order_id, line_no)`:

- Ràng buộc tự nhiên một dòng có số thứ tự duy nhất trong mỗi order.
- Khóa thể hiện rõ định danh theo phạm vi cha.
- Không cần thêm cột `id` nếu không có yêu cầu khác.

Hạn chế:

- Những bảng khác muốn tham chiếu chính dòng đơn hàng phải giữ **cả hai cột**.
- Domain có thể cần chuyển line sang order khác hoặc đổi `lineNo`, làm thay đổi identity.
- API/URL/DTO với khóa ghép có thể cần thêm logic serialize, validate.
- Với PK rộng hơn (nhiều khóa ngoại hoặc mã dài), index và khóa ngoại lan truyền có thể tốn thêm chi phí lưu trữ và join.

Nếu nhiều hệ thống ngoài liên kết tới `OrderLine`, một PK độc lập có thể dễ vận hành hơn, đồng thời vẫn giữ unique constraint:

```sql
CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    UNIQUE (order_id, line_no),
    FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
```

Trong thiết kế này, **không dùng `@MapsId`** vì `order_id` không nằm trong primary key.

### 15.4. Chuyển từ FK thường sang shared PK cần migration có kế hoạch

Giả sử bảng settings đang có `(id PK, account_id UNIQUE FK)`, muốn chuyển sang `(account_id PK/FK)`. Không chỉ sửa annotation:

1. Kiểm tra `account_id` có null/trùng hoặc dữ liệu mồ côi không.
2. Kiểm tra có bảng nào tham chiếu `settings.id` cũ không; cập nhật các FK và consumer.
3. Thiết kế migration tạo/sửa PK, FK, index và rollback plan phù hợp DBMS.
4. Cập nhật mapping entity, DTO, endpoint và truy vấn sử dụng ID.
5. Xác nhận các thao tác insert, update, remove và loading hoạt động trên schema mới.

Mức độ phức tạp phụ thuộc dữ liệu thật và khả năng đổi khóa trên database. Hibernate schema generation không thay thế quy trình migration có kiểm soát trong production.

## 16. Các thực hành tốt khi xây dựng aggregate

Một derived ID thường cho thấy entity con nằm trong **ngữ cảnh cha**, nhưng không tự chứng minh aggregate boundary theo Domain-Driven Design.

Nếu `AccountSettings` chỉ tồn tại cùng `Account`:

```text
Account aggregate
 ├── Account (aggregate root, ID được sinh độc lập)
 └── AccountSettings (shared PK qua @MapsId)
```

Có thể để `Account` là nơi tạo và liên kết settings, bật cascade persist và orphanRemoval theo yêu cầu. Nhưng nếu con có vòng đời/transaction khác, hãy phân tích lại việc dùng cascade và vòng đời.

Với `OrderLine`:

```text
PurchaseOrder aggregate
 ├── PurchaseOrder(id)
 └── OrderLine(orderId, lineNo)
```

Một số nguyên tắc hữu ích:

- Tạo con qua method của aggregate root để gán đúng cha.
- Sinh `lineNo` theo chính sách duy nhất trong order, chú ý concurrent requests.
- Không cho phép `setOrder()` hoặc `setLineNo()` tự do sau persist.
- Quy định rõ thao tác xóa line, xóa order và audit.
- Giữ transaction ngắn, đo các query khi duyệt collection.
- Không giả định `@MapsId` sẽ tự nạp relationship khi chỉ cần ID; chiến lược fetch cần quyết định riêng.

Ví dụ nếu hai request cùng xác định “số dòng tiếp theo = MAX(line_no) + 1” trong cùng order, cả hai có thể chọn cùng số và một request gặp xung đột PK. Cần chính sách khóa, phân phối số hoặc kiểm soát đồng thời; `@MapsId` **không tự xử lý race condition**.

## 17. Kiểm tra một mapping bằng câu hỏi cụ thể

Trước khi chọn `@MapsId`, hãy tự trả lời:

| Câu hỏi | Nếu câu trả lời là “có” |
| --- | --- |
| PK của con có bằng toàn bộ PK của cha không? | Cân nhắc shared PK với `@OneToOne @MapsId` |
| PK của con có chứa FK tới cha không? | Cân nhắc `@EmbeddedId` + `@MapsId("...")` |
| Một con có thể tồn tại nếu chưa biết cha không? | Nếu không, derived identity phản ánh được ràng buộc đó |
| Parent có cần đổi trong đời sống của con không? | Nếu có thường xuyên, xem lại việc dùng parent FK làm PK |
| Con có cần ID ổn định để các hệ thống khác tham chiếu không? | Xem xét PK độc lập + unique constraint thay cho composite PK |
| Đã có PK/FK hoặc UNIQUE tương ứng trong database chưa? | Mapping Java phải đồng bộ với schema đã quản lý |
| Ai persist/remove entity con? | Cấu hình cascade và orphan removal riêng, không phụ thuộc vào `@MapsId` |
| Có yêu cầu portable theo Jakarta Persistence không? | Dùng các ID value type và `@MapsId`, tránh phụ thuộc extension quan hệ nằm trong embedded ID |

Có thể kết hợp cả `@MapsId` và các quy tắc business khác, nhưng `@MapsId` chỉ diễn đạt **cách xác định identity**.

## 18. Bài tập vận dụng

### Tình huống 1: Hồ sơ nhân viên

Bảng `employees(id PK)` và `employee_profiles(employee_id PK/FK, address, avatar_url)`. Một nhân viên có tối đa một hồ sơ. Entity `EmployeeProfile` nên dùng dạng nào?

**Gợi ý:** `@Id Long id` và `@OneToOne @MapsId @JoinColumn(name = "employee_id") Employee employee`; không có `@GeneratedValue` trên `EmployeeProfile.id`.

### Tình huống 2: Dòng hóa đơn

Bảng `invoice_lines(invoice_id, line_no, item_code, quantity)` có PK `(invoice_id, line_no)`. ID của line phụ thuộc ID của invoice ra sao?

**Gợi ý:** `@EmbeddedId InvoiceLineId(invoiceId, lineNo)`, kết hợp `@ManyToOne @MapsId("invoiceId")` tham chiếu `Invoice`; `lineNo` được cấp theo phạm vi hóa đơn.

### Tình huống 3: Bảng quan hệ người dùng và vai trò

Bảng `user_roles(user_id, role_id, assigned_at)` có PK `(user_id, role_id)`. Một bản gán vai trò được nhận diện bằng hai quan hệ. Dùng gì?

**Gợi ý:** Một `@EmbeddedId` có `userId` và `roleId`, hai `@ManyToOne` lần lượt kèm `@MapsId("userId")`, `@MapsId("roleId")`. Nếu bảng không có thuộc tính nghiệp vụ và không cần entity riêng, `@ManyToMany` cũng có thể là lựa chọn khác; cân nhắc yêu cầu truy cập/thay đổi.

### Tình huống 4: Chuyển một dòng từ đơn hàng 10 sang 11

Định danh line đang là `(10, 3)`. Có nên chỉ sửa `line.order` sang `Order(11)` trong khi line vẫn managed?

**Gợi ý:** Không. Nó làm thay đổi primary key thành `(11, 3)`. Tùy nghiệp vụ, xóa/tạo line mới trong transaction hoặc thiết kế lại khóa nếu chuyển order thường xuyên.

### Tình huống 5: Mất dữ liệu sau khi xóa parent

Một hệ thống dùng `orphanRemoval=true` và `CascadeType.ALL` trên `Account.settings`; khi xóa `Account`, settings biến mất. Có phải do `@MapsId` không?

**Gợi ý:** Không. `@MapsId` liên quan identity. Việc xóa phụ thuộc `CascadeType.REMOVE` (nằm trong `ALL`), orphan removal và/hoặc FK cascade ở database. Phải phân biệt chúng trước khi sửa.

### Tình huống 6: Tên field sai

ID class có field `invoiceId`, nhưng entity dùng `@MapsId("invoice_id")`. Hệ quả?

**Gợi ý:** Tên trong `@MapsId` phải trỏ đến **tên thuộc tính Java** `invoiceId`, không phải tên cột `invoice_id`.

### Tình huống 7: Query theo ID

`OrderLine` dùng `@EmbeddedId OrderLineId`. `EntityManager.find(OrderLine.class, 1L)` có đúng không?

**Gợi ý:** Không. Phải truyền object `new OrderLineId(orderId, lineNo)` làm primary key; ID type là `OrderLineId`.

## 19. Tài liệu chính thức

- [Jakarta Persistence 3.2 — Specification: derived identities](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): định nghĩa PK phụ thuộc, quy tắc `@MapsId`, khóa đơn/khóa ghép và mối liên hệ parent–dependent.
- [Jakarta Persistence 3.2 — `@MapsId` API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/mapsid): quan hệ `ManyToOne`/`OneToOne`, ý nghĩa thuộc tính `value` và điều kiện gắn parent trước khi persist.
- [Jakarta Persistence 3.2 — `@EmbeddedId` API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/embeddedid): yêu cầu đối với composite ID và cách kết hợp `@MapsId`.
- [Hibernate ORM User Guide — Identifiers / Derived Identifiers](https://docs.hibernate.org/stable/orm/userguide/html_single/): các kiểu khóa trong Hibernate và những lưu ý về composite identifier.
- [Jakarta Persistence 3.2 — `@OneToOne`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/onetoone) và [Jakarta Persistence 3.2 — `@ManyToOne`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/manytoone): mapping quan hệ được dùng cùng `@MapsId`.

Các ví dụ dùng namespace `jakarta.persistence.*` thuộc Jakarta Persistence hiện đại. Ứng dụng JPA cũ có thể còn dùng `javax.persistence.*`; khi nâng cấp cần đồng bộ API, Hibernate và framework, thay vì chỉ đổi import ở một entity.

## Kết luận

**Định danh phụ thuộc** có nghĩa identity của entity con được tạo từ identity của một hay nhiều entity cha. Annotation **`@MapsId`** gắn một quan hệ `@OneToOne` hoặc `@ManyToOne` với phần khóa đó:

- **`@Id` + `@OneToOne @MapsId`** khi con và cha dùng chung khóa chính.
- **`@EmbeddedId` + `@ManyToOne @MapsId("parentId")`** khi khóa ghép của con chứa FK tới cha.
- Có thể có **nhiều `@MapsId("...")`** khi khóa ghép gồm các thành phần từ nhiều cha.

Để mapping đúng, luôn gắn parent reference trước khi persist dependent, lưu parent theo lifecycle phù hợp, triển khai equality cho composite ID, giữ PK ổn định sau khi entity persistent và bảo vệ ràng buộc tại database bằng PK/FK thực. `@MapsId` giải quyết **identity mapping**; còn cascade, xóa, fetching, transaction và concurrency cần được thiết kế riêng theo nhu cầu nghiệp vụ.
