# Sử dụng `@MapsId` cho khóa chia sẻ hoặc khóa có thành phần liên kết

Trong JPA, một entity được nhận diện bởi khóa chính (`@Id` hoặc `@EmbeddedId`). Thông thường khóa chính của mỗi entity được cấp độc lập, ví dụ bằng `@GeneratedValue`. Nhưng có những mô hình dữ liệu mà **định danh của entity phụ thuộc vào định danh của entity khác**:

- Hồ sơ `AccountProfile` có khóa chính **chính là** khóa của `Account` tương ứng: quan hệ một-một với **shared primary key**.
- Dòng đơn hàng `OrderLine` có khóa ghép **(order_id, line_no)**. Phần `order_id` đồng thời là khóa ngoại trỏ đến `PurchaseOrder`: đây là **khóa ghép có thành phần liên kết**.
- Bản ghi đăng ký `Enrollment` có khóa ghép **(student_id, course_id)**; mỗi thành phần lấy từ một association `@ManyToOne`.

Nếu chỉ khai báo các cột khóa và association một cách độc lập, lập trình viên dễ phải **tự đồng bộ hai biểu diễn của cùng một giá trị**: `orderLine.id.orderId` và `orderLine.order.id`, hoặc `profile.id` và `profile.account.id`. Annotation **`@MapsId`** được JPA cung cấp để diễn đạt trực tiếp quan hệ đó.

**`@MapsId` cho provider biết rằng một association `@ManyToOne` hoặc `@OneToOne` cung cấp giá trị định danh cho toàn bộ khóa chính hoặc một thuộc tính thuộc khóa chính của entity phụ thuộc.** Khi cấu hình đúng, quan hệ thực thể và định danh của entity phụ thuộc được ánh xạ nhất quán trên cùng cột khóa ngoại/khóa chính.

Bài học nằm trong chủ đề **khóa ghép**, nhưng trước tiên cần hiểu mô hình khóa chia sẻ đơn giản, vì đó là trường hợp `@MapsId` không có tham số `value`. Sau đó ta mở rộng sang `@EmbeddedId` với một hoặc nhiều thành phần liên kết.

## 1. Khái niệm derived identity (định danh dẫn xuất)

Một entity được gọi là có **derived identity** khi định danh của nó phụ thuộc vào một quan hệ với entity khác (entity cha, principal hoặc owner về mặt định danh).

Hai dạng thường gặp:

| Dạng định danh | Entity phụ thuộc | Nguồn giá trị định danh | `@MapsId` |
|---|---|---|---|
| **Khóa chính chia sẻ** | `AccountProfile` | Toàn bộ ID lấy từ `Account.id` | `@MapsId`, không có tên thuộc tính |
| **Một thành phần của khóa ghép** | `OrderLine` | `OrderLineId.orderId` lấy từ `PurchaseOrder.id` | `@MapsId("orderId")` |
| **Nhiều thành phần liên kết** | `Enrollment` | `studentId` từ `Student.id`, `courseId` từ `Course.id` | Hai `@MapsId("...")` trên hai association |

Hãy phân biệt ba khái niệm:

1. **Primary key:** cột hoặc tập cột xác định duy nhất một hàng trong bảng.
2. **Foreign key:** cột hoặc tập cột tham chiếu khóa của bảng khác, được database kiểm tra nếu có constraint.
3. **Derived identity:** ở phía entity phụ thuộc, một phần hoặc toàn bộ primary key đồng thời được lấy từ association; các cột tương ứng thường **vừa là PK vừa là FK**.

Ví dụ:

```text
accounts                         account_profiles
+----------+                     +----------+-------------+
| id (PK)  |                     | id (PK)  | language    |
+----------+                     +----------+-------------+
| 21       | <--- PK/FK --------- | 21       | vi          |
+----------+                     +----------+-------------+

account_profiles.id đồng thời là:
  - Primary key của account_profiles
  - Foreign key đến accounts.id
```

Ở ví dụ này, `AccountProfile` **không cần một sequence/identity generator riêng**. Giá trị khóa chính của profile được dẫn xuất từ account liên kết.

## 2. `@MapsId` có ý nghĩa gì trong JPA?

Annotation nằm trong gói `jakarta.persistence`:

```java
import jakarta.persistence.MapsId;
```

Nó dùng trên **field hoặc getter biểu diễn relationship** thuộc entity phụ thuộc, thông thường đi kèm `@OneToOne` hoặc `@ManyToOne`.

Có hai cú pháp cơ bản:

```java
// Association cung cấp toàn bộ khóa đơn/khóa được dùng cho entity phụ thuộc.
@OneToOne
@MapsId
private Account account;
```

```java
// Association cung cấp một thành phần trong @EmbeddedId.
@ManyToOne
@MapsId("orderId")
private PurchaseOrder order;
```

**`value` trong `@MapsId("orderId")` là tên thuộc tính Java trong lớp khóa ghép**, không phải tên cột SQL và cũng không phải tên bảng.

Khi association gắn với trường khóa đơn có cùng kiểu ID, có thể bỏ `value`. Khi khóa ghép có một thành phần tương ứng với entity cha, khai báo rõ tên thành phần đó để provider biết lấy ID của quan hệ đặt vào đâu.

### `@MapsId` làm gì và không làm gì?

| Việc cần làm | `@MapsId` có đảm nhiệm không? |
|---|---|
| Diễn đạt rằng association tạo nên toàn bộ/một phần identity | **Có** |
| Phối hợp metadata giữa `@Id`/`@EmbeddedId` và foreign-key association | **Có** |
| Cho phép provider lấy giá trị ID từ entity liên kết | **Có**, theo quy tắc derived identity |
| Tự tạo entity cha khi chưa được `persist` | **Không** |
| Tự bật `CascadeType.PERSIST` hoặc `REMOVE` | **Không** |
| Tạo sẵn foreign-key constraint trên database đã có | **Không đảm bảo**; phụ thuộc DDL/migration |
| Tự cho phép thay đổi khóa chính của entity sau khi lưu | **Không** |
| Bảo đảm lazy loading ở mọi provider/cấu hình | **Không** |

`@MapsId` là **metadata ORM về định danh**, không phải một lệnh SQL hay một cơ chế cascade.

## 3. Trường hợp 1: khóa chính chia sẻ với `@OneToOne`

Giả sử ứng dụng có bảng `accounts` và bảng `account_profiles`. Một tài khoản có tối đa một hồ sơ mở rộng; hồ sơ chỉ tồn tại để bổ sung thông tin cho tài khoản đó.

Yêu cầu:

- `Account` có ID số do database cấp.
- `AccountProfile` không có ID độc lập.
- `AccountProfile.id == Account.id` của tài khoản tương ứng.
- Bảng `account_profiles` dùng cột `id` đồng thời làm khóa chính và khóa ngoại.

### 3.1. Entity cha `Account`

```java
package example.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "accounts")
public class Account {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 100)
    private String username;

    protected Account() {
    }

    public Account(String username) {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("username is required");
        }
        this.username = username;
    }

    public Long getId() {
        return id;
    }

    public String getUsername() {
        return username;
    }
}
```

Đây là entity cha thông thường: `Account.id` sinh bằng `GenerationType.IDENTITY` và được lưu ở bảng `accounts`.

### 3.2. Entity phụ thuộc `AccountProfile`

```java
package example.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.MapsId;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "account_profiles")
public class AccountProfile {
    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @MapsId
    @JoinColumn(name = "id", nullable = false)
    private Account account;

    @Column(name = "language_code", nullable = false, length = 10)
    private String languageCode;

    protected AccountProfile() {
    }

    public AccountProfile(Account account, String languageCode) {
        if (account == null || languageCode == null || languageCode.isBlank()) {
            throw new IllegalArgumentException("account and language are required");
        }
        this.account = account;
        this.languageCode = languageCode;
    }

    public Long getId() {
        return id;
    }

    public Account getAccount() {
        return account;
    }

    public String getLanguageCode() {
        return languageCode;
    }

    public void changeLanguage(String languageCode) {
        if (languageCode == null || languageCode.isBlank()) {
            throw new IllegalArgumentException("language is required");
        }
        this.languageCode = languageCode;
    }
}
```

Đọc từng annotation quan trọng:

| Khai báo | Vai trò |
|---|---|
| `@Id private Long id` | Khóa chính của `AccountProfile` |
| `@OneToOne(optional = false)` | Mỗi profile phụ thuộc vào một account |
| `@MapsId` | Toàn bộ `AccountProfile.id` được dẫn xuất từ `Account.id` |
| `@JoinColumn(name = "id")` | Cột `id` của profile đồng thời là cột join/FK tới `accounts.id` |
| Không có `@GeneratedValue` ở profile | Profile dùng ID của account, không tự sinh ID riêng |

Điểm đặc biệt là **không cần gọi `profile.setId(account.getId())`**. Association `profile.account` biểu diễn nguồn của identity; provider sẽ đồng bộ giá trị theo cơ chế `@MapsId`.

`@OneToOne(fetch = FetchType.LAZY)` là yêu cầu tải chậm. Với association một-một, hành vi thực tế còn phụ thuộc provider, bytecode enhancement, proxy và chiều quan hệ. `@MapsId` không bảo đảm tuyệt đối rằng mọi truy cập đều lazy.

### 3.3. Lược đồ quan hệ tương ứng

```sql
CREATE TABLE accounts (
    id       BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE account_profiles (
    id            BIGINT PRIMARY KEY,
    language_code VARCHAR(10) NOT NULL,
    CONSTRAINT fk_profile_account
        FOREIGN KEY (id) REFERENCES accounts(id)
);
```

DDL dùng cú pháp identity mang tính minh họa; cần điều chỉnh theo hệ quản trị CSDL mục tiêu.

Ở đây:

1. `accounts.id` do database/provider cấp theo `IDENTITY`.
2. `account_profiles.id` là cột `BIGINT` thông thường, **không có cơ chế auto-increment riêng**.
3. Khóa chính `account_profiles.id` ngăn hai profile cùng dùng một account ID.
4. Foreign key `fk_profile_account` ngăn profile trỏ tới account không tồn tại.

Cặp ràng buộc **PK + FK** thể hiện quan hệ một-một ở cấp cơ sở dữ liệu. `@MapsId` thể hiện cùng ý nghĩa ở cấp mô hình JPA.

### 3.4. Tạo dữ liệu trong một transaction

Ví dụ Java SE dùng `EntityManager` resource-local:

```java
EntityManager em = emf.createEntityManager();
try {
    em.getTransaction().begin();

    Account account = new Account("minh");
    em.persist(account);

    AccountProfile profile = new AccountProfile(account, "vi");
    em.persist(profile);

    em.getTransaction().commit();

    System.out.println("Account id: " + account.getId());
    System.out.println("Profile id: " + profile.getId());
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Trong luồng này, `account` được đưa vào persistence context trước `profile`. Provider có thể phải thực hiện `INSERT` sớm đối với `IDENTITY` để lấy ID của account; sau đó sử dụng ID này khi chèn profile. Với các chiến lược sinh khóa khác, thời điểm lấy số và chèn hàng có thể thay đổi.

**Một kết quả minh họa**:

```text
accounts
id   username
31   minh

account_profiles
id   language_code
31   vi
```

Điều được bảo đảm về mô hình là khóa của profile liên hệ với khóa của account. Không cần dựa vào thời điểm `profile.id` trở nên khác `null` trước `flush`; nếu ứng dụng cần một giá trị đã được đồng bộ để dùng ở bước tiếp theo, hãy làm việc trong transaction thích hợp và cân nhắc `flush()`.

### 3.5. Có thể ánh xạ quan hệ hai chiều không?

Có. Nếu muốn đi từ `Account` sang `AccountProfile`, thêm phía nghịch trên `Account`:

```java
@OneToOne(
    mappedBy = "account",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private AccountProfile profile;

public void attachProfile(AccountProfile profile) {
    if (profile == null) {
        throw new IllegalArgumentException("profile is required");
    }
    this.profile = profile;
    // Đồng bộ profile.account bằng constructor/helper thích hợp.
}
```

Ví dụ này minh họa metadata quan hệ ngược; muốn sử dụng thực tế cần bổ sung import và helper duy trì **hai phía association** nhất quán. `mappedBy = "account"` cho biết phía `AccountProfile.account` là phía sở hữu quan hệ. Không thêm `@JoinColumn` ở cả hai phía rồi mong hai cột được đồng bộ tự động.

`cascade = CascadeType.ALL` là lựa chọn riêng của vòng đời quan hệ. Trong một quan hệ phụ thuộc hoàn toàn, `PERSIST` và `REMOVE` có thể phù hợp, nhưng phải cân nhắc chính sách xóa. **`@MapsId` không tự kéo theo cascade**; nếu không khai báo cascade, ứng dụng vẫn phải lưu entity liên quan theo thứ tự/phạm vi transaction phù hợp.

## 4. Trường hợp 2: khóa ghép có một thành phần lấy từ association

Đây là tình huống trung tâm của `@MapsId` trong một bài về **khóa ghép**.

Một đơn hàng có nhiều dòng. Mỗi dòng được phân biệt bởi:

- `order_id`: ID của đơn hàng chứa dòng.
- `line_no`: số thứ tự dòng **trong phạm vi đơn hàng**.

Khóa chính của `OrderLine` là cặp **`(order_id, line_no)`**. Một dòng có thể có `line_no = 1` trong nhiều đơn hàng; nhưng không được có hai dòng `(order_id = 42, line_no = 1)`.

```text
purchase_orders                   order_lines
+----------+                     +----------+---------+-------+
| id (PK)  |                     | order_id | line_no | sku   |
+----------+                     +----------+---------+-------+
| 42       | <--- FK ------------ | 42       | 1       | A100  |
| 43       |                     | 42       | 2       | B200  |
+----------+                     | 43       | 1       | C300  |
                                 +----------+---------+-------+
                                 PRIMARY KEY(order_id, line_no)
```

### 4.1. Entity cha `PurchaseOrder`

```java
package example.domain;

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

    @Column(name = "order_code", nullable = false, unique = true)
    private String orderCode;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderCode) {
        if (orderCode == null || orderCode.isBlank()) {
            throw new IllegalArgumentException("orderCode is required");
        }
        this.orderCode = orderCode;
    }

    public Long getId() {
        return id;
    }
}
```

### 4.2. Lớp khóa ghép `OrderLineId`

`@Embeddable` chứa các **giá trị định danh**, chưa chứa association:

```java
package example.domain;

import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class OrderLineId implements Serializable {
    private Long orderId;
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

Những điểm cần lưu ý:

- `OrderLineId` **không phải entity**, nên không có `@Entity` hay `@Id` riêng.
- Nó có constructor không tham số phù hợp, dùng `Serializable` để tương thích tốt với các thế hệ JPA và định nghĩa key truyền thống.
- `equals`/`hashCode` được viết theo tất cả thuộc tính khóa; không dựa trên object identity.
- `orderId` sẽ lấy từ `PurchaseOrder.id`, còn `lineNo` do logic nghiệp vụ cung cấp.
- Sau khi entity đã persistent, các thành phần khóa phải được xem là ổn định; không viết API cho phép sửa `orderId` hoặc `lineNo` tùy ý.

### 4.3. Entity con với `@EmbeddedId` và `@MapsId("orderId")`

```java
package example.domain;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.MapsId;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
public class OrderLine {
    @EmbeddedId
    private OrderLineId id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @MapsId("orderId")
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "sku", nullable = false, length = 50)
    private String sku;

    protected OrderLine() {
    }

    public OrderLine(PurchaseOrder order, int lineNo, String sku) {
        if (order == null || lineNo <= 0 || sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("Invalid order line");
        }
        this.order = order;
        this.id = new OrderLineId(null, lineNo);
        this.sku = sku;
    }

    public OrderLineId getId() {
        return id;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    public String getSku() {
        return sku;
    }
}
```

Ở đây:

- `@EmbeddedId` khai báo `OrderLineId` là khóa chính ghép.
- `@ManyToOne` khai báo association từ dòng hàng đến đơn hàng.
- **`@MapsId("orderId")`** khẳng định thành phần `OrderLineId.orderId` được dẫn xuất từ `OrderLine.order.id`.
- `@JoinColumn(name = "order_id")` chỉ định **cột database** cùng tham gia khóa ghép và foreign key.
- `lineNo` còn lại là phần khóa do nghiệp vụ xác định; nó không phải ID của entity cha.

Việc dùng `new OrderLineId(null, lineNo)` có chủ ý: trước khi `PurchaseOrder` được persist, ID sinh tự động của nó có thể chưa tồn tại. Provider có trách nhiệm đồng bộ phần khóa tương ứng với `@MapsId` trong tiến trình persistence.

**Tên trong `@MapsId("orderId")` phải khớp `orderId` của lớp `OrderLineId`.** Nếu viết `@MapsId("order_id")`, đó là nhầm tên cột SQL với tên property Java.

### 4.4. Mapping các cột khóa ghép

Ta muốn schema:

```sql
CREATE TABLE purchase_orders (
    id         BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_no  INTEGER NOT NULL,
    sku      VARCHAR(50) NOT NULL,
    CONSTRAINT pk_order_lines
        PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
```

Với một số naming strategy, nếu không chỉ rõ tên các cột của `@EmbeddedId`, tên cột suy ra từ `orderId` và `lineNo` có thể khác `order_id`/`line_no`. Để ánh xạ chắc chắn theo schema ở trên, có thể khai báo tại lớp khóa:

```java
@Embeddable
public class OrderLineId implements Serializable {
    @Column(name = "order_id")
    private Long orderId;

    @Column(name = "line_no")
    private Integer lineNo;

    // Constructors, getters, equals và hashCode như ví dụ trước.
}
```

Cột `order_id` giờ vừa nằm trong `@EmbeddedId`, vừa là cột join của `@ManyToOne`. `@MapsId("orderId")` nói rõ **đó là một cột dùng cho hai mục đích ánh xạ thống nhất**, giúp tránh việc khai báo hai nguồn ghi khóa độc lập.

Không tùy tiện thêm `insertable = false, updatable = false` vào `@JoinColumn` chỉ vì nhận thấy hai đường ánh xạ cùng cột. Các thiết lập read-only có ý nghĩa riêng và có thể làm sai mô hình derived identity nếu ứng dụng cố gắng dùng chúng để né cấu hình `@MapsId`. Hãy để provider điều phối khóa theo annotation chuẩn.

### 4.5. Lưu entity cha và các dòng hàng

```java
EntityManager em = emf.createEntityManager();
try {
    em.getTransaction().begin();

    PurchaseOrder order = new PurchaseOrder("PO-2026-0042");
    em.persist(order);

    OrderLine line1 = new OrderLine(order, 1, "SKU-A");
    OrderLine line2 = new OrderLine(order, 2, "SKU-B");

    em.persist(line1);
    em.persist(line2);

    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Về mặt logic, hai dòng được lưu với cặp khóa:

```text
OrderLine 1: (order_id = ID của order vừa tạo, line_no = 1)
OrderLine 2: (order_id = ID của order vừa tạo, line_no = 2)
```

`em.persist(order)` được gọi trước để provider có thể xử lý ID của entity cha. Nếu tạo `OrderLine` trỏ tới `PurchaseOrder` transient mà không persist cha và không có cascade phù hợp, việc flush có thể thất bại vì association tham chiếu entity chưa persistent.

### 4.6. Khi nào dùng `@MapsId("orderId")` thay vì gán cả khóa thủ công?

Không nên tạo hai giá trị có thể mâu thuẫn:

```java
line.id.orderId = 42L; // Giả sử code có setter.
line.order = orderWithId99; // ID từ association khác ID trong khóa.
```

Trong mô hình `@MapsId`, association là nguồn dữ liệu của thành phần identity liên quan. Business code nên thiết lập `order` đúng và để provider đồng bộ phần `orderId`. Khi đã persistent, không chuyển dòng sang một đơn hàng khác bằng cách thay `order`: đó là thay đổi **một phần khóa chính**. Phương án an toàn thường là tạo một dòng mới với identity phù hợp và xử lý dòng cũ theo yêu cầu nghiệp vụ.

## 5. Trường hợp 3: hai association tạo thành toàn bộ khóa ghép

Một bảng liên kết nhiều-nhiều đôi khi không nên được ánh xạ chỉ bằng `@ManyToMany`. Nếu bản ghi liên kết có thuộc tính nghiệp vụ như ngày đăng ký, trạng thái hoặc điểm số, ta có thể tạo **entity liên kết**.

Ví dụ:

```text
students              enrollments                    courses
+---------+          +----------------------------+  +---------+
| id (PK) | <------  | student_id (PK, FK)        |  | id (PK) |
+---------+          | course_id  (PK, FK)        | ----> 
                     | enrolled_at                |
                     +----------------------------+

PRIMARY KEY(student_id, course_id)
```

`Enrollment` có khóa ghép `(studentId, courseId)`. Hai thành phần được dẫn xuất từ hai association `student` và `course`.

### 5.1. Lớp khóa

```java
package example.domain;

import java.io.Serializable;
import java.util.Objects;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class EnrollmentId implements Serializable {
    @Column(name = "student_id")
    private Long studentId;

    @Column(name = "course_id")
    private Long courseId;

    protected EnrollmentId() {}

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

### 5.2. Entity liên kết

Giả định `Student` và `Course` đều có `@Id Long id`:

```java
package example.domain;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.MapsId;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "enrollments")
public class Enrollment {
    @EmbeddedId
    private EnrollmentId id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @MapsId("studentId")
    @JoinColumn(name = "student_id", nullable = false)
    private Student student;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @MapsId("courseId")
    @JoinColumn(name = "course_id", nullable = false)
    private Course course;

    @Column(name = "enrolled_at", nullable = false)
    private Instant enrolledAt;

    protected Enrollment() {}

    public Enrollment(Student student, Course course, Instant enrolledAt) {
        if (student == null || course == null || enrolledAt == null) {
            throw new IllegalArgumentException("Enrollment data required");
        }
        this.student = student;
        this.course = course;
        this.enrolledAt = enrolledAt;
        this.id = new EnrollmentId(null, null);
    }

    public EnrollmentId getId() {
        return id;
    }
}
```

**Điểm đáng chú ý:** hai association cùng tham gia xác lập một `@EmbeddedId`. `@MapsId("studentId")` và `@MapsId("courseId")` chỉ tới **hai thuộc tính khác nhau**, giúp provider lấy khóa của từng entity liên kết và điền vào đúng thành phần.

Một schema tương ứng:

```sql
CREATE TABLE enrollments (
    student_id  BIGINT NOT NULL,
    course_id   BIGINT NOT NULL,
    enrolled_at TIMESTAMP NOT NULL,
    PRIMARY KEY (student_id, course_id),
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (course_id)  REFERENCES courses(id)
);
```

Vì cặp `(student_id, course_id)` là khóa chính, một sinh viên không thể có hai bản ghi `Enrollment` có cùng khóa đối với một khóa học. Nếu nghiệp vụ cho phép đăng ký lại cùng một khóa nhiều lần, cần bổ sung một thành phần định danh khác (ví dụ `attemptNo`) hoặc chọn surrogate key và unique constraint theo quy tắc mới.

### 5.3. Lưu đăng ký

```java
Student student = em.find(Student.class, studentId);
Course course = em.find(Course.class, courseId);

if (student == null || course == null) {
    throw new IllegalArgumentException("Student or course does not exist");
}

Enrollment enrollment = new Enrollment(student, course, Instant.now());
em.persist(enrollment);
```

Ví dụ giả định đoạn mã chạy **trong transaction phù hợp**. `student` và `course` là các entity đã tồn tại, được tìm qua `find`. Provider dùng định danh của chúng để xác định khóa ghép của `Enrollment`.

Không cần `@GeneratedValue` cho `EnrollmentId.studentId` hay `courseId` vì các giá trị ấy được lấy từ association. Các ID của `Student` và `Course` có thể tự được sinh theo chiến lược riêng của từng entity cha.

## 6. `@MapsId` với khóa đơn và khóa ghép: so sánh cơ chế

| Điểm so sánh | Shared PK một-một | Thành phần khóa ghép | Hai khóa ngoại trong khóa ghép |
|---|---|---|---|
| Entity phụ thuộc | `AccountProfile` | `OrderLine` | `Enrollment` |
| Annotation khóa | `@Id Long id` | `@EmbeddedId OrderLineId id` | `@EmbeddedId EnrollmentId id` |
| Association cung cấp ID | `@OneToOne Account` | `@ManyToOne PurchaseOrder` | Hai `@ManyToOne` |
| `@MapsId` | Không tham số | `@MapsId("orderId")` | `@MapsId("studentId")`, `@MapsId("courseId")` |
| Cột vừa PK vừa FK | `id` | `order_id` | `student_id`, `course_id` |
| Thành phần khóa còn lại | Không có | `line_no` | Không có |
| Tự sinh ID phía phụ thuộc | Không | Không cho phần FK; `lineNo` do ứng dụng định nghĩa | Không |

Cùng một cơ chế derived identity giải quyết cả ba mô hình. Điều thay đổi là **bao nhiêu phần của ID đến từ association**, và kiểu khóa được biểu diễn trong Java như thế nào.

## 7. Phân biệt `@MapsId` với `@JoinColumn` và `@PrimaryKeyJoinColumn`

Các annotation này thường xuất hiện cùng một bài toán, nhưng không thay thế hoàn toàn cho nhau.

### `@JoinColumn`

`@JoinColumn(name = "order_id")` quy định **cột dùng để join/foreign key** cho association. Một association thông thường có `@JoinColumn` chưa có nghĩa cột này tham gia khóa chính.

Ví dụ:

```java
@ManyToOne
@JoinColumn(name = "customer_id")
private Customer customer;
```

Đây chỉ là quan hệ nhiều-một bình thường nếu `customer_id` không được định nghĩa trong entity ID.

### `@MapsId`

`@MapsId("orderId")` xác định **sự gắn kết giữa relationship và thành phần ID**. Khi kết hợp với `@JoinColumn(name = "order_id")`, provider biết `order_id` vừa là cột join vừa thuộc khóa ghép.

### `@PrimaryKeyJoinColumn`

`@PrimaryKeyJoinColumn` có thể gặp ở một số trường hợp shared primary key hoặc inheritance mapping. Trong mô hình shared PK một-một, việc chỉ định primary-key join không nhất thiết diễn đạt rõ **cách ID của dependent được dẫn xuất và đồng bộ** như `@MapsId`.

Nếu mục tiêu là dùng khóa của entity cha cho entity phụ thuộc và làm việc theo API JPA, `@MapsId` thường là cách diễn đạt trực tiếp, rõ ràng hơn cho derived identity. `@PrimaryKeyJoinColumn` vẫn có những ngữ cảnh và semantics riêng; không nên thay đổi annotation tùy ý mà không xem lại mapping.

### `@IdClass` có liên quan không?

JPA cũng hỗ trợ `@IdClass` cho khóa ghép. Với `@IdClass`, các trường `@Id` thường được khai báo trực tiếp trên entity và có lớp ID tương ứng. Khi identity phụ thuộc association, mô hình derived identity còn có quy tắc ánh xạ tên và kiểu giữa khóa của entity liên kết và lớp ID.

`@MapsId` xuất hiện rất rõ ràng khi dùng `@EmbeddedId`; đây là trọng tâm của ví dụ trong bài. Không nên suy luận rằng mọi dạng khóa ghép buộc phải dùng `@EmbeddedId`; lựa chọn `@IdClass` hay `@EmbeddedId` cần xét mục tiêu thiết kế và quy tắc đặc tả.

## 8. Quy trình lưu dữ liệu, cascade và thứ tự persist

Một trong những lỗi thường gặp là cho rằng `@MapsId` tự đưa entity cha vào persistence context.

Giả sử:

```java
PurchaseOrder order = new PurchaseOrder("PO-2026-0090");
OrderLine line = new OrderLine(order, 1, "SKU-A");

em.persist(line);
```

Nếu `order` vẫn là **transient** và association không có cascade phù hợp, provider có thể không có khóa chính hợp lệ để đưa vào `order_id`; thao tác flush có thể phát sinh lỗi liên quan entity chưa được lưu.

### Cách 1: persist cha trước

```java
em.persist(order);
em.persist(line);
```

Cách này thể hiện rõ vòng đời: trước tiên yêu cầu lưu đơn hàng, rồi yêu cầu lưu dòng phụ thuộc.

### Cách 2: cấu hình cascade có chủ đích

Ví dụ phía con:

```java
@ManyToOne(
    fetch = FetchType.LAZY,
    optional = false,
    cascade = CascadeType.PERSIST
)
@MapsId("orderId")
@JoinColumn(name = "order_id")
private PurchaseOrder order;
```

Nếu có cascade `PERSIST`, lệnh `em.persist(line)` có thể được lan truyền sang `order`. Tuy nhiên, cascade từ **nhiều dòng về cùng một đơn hàng** không phải lúc nào cũng phản ánh đúng quyền sở hữu vòng đời nghiệp vụ. Thông thường, người ta kiểm soát cascade từ aggregate root (đơn hàng) xuống các dòng thay vì từ mỗi dòng lên đơn hàng.

Một thiết kế hai chiều thường gặp:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

Khi đó, `PurchaseOrder` là aggregate root và có thể quản lý việc tạo, thêm/xóa dòng. Để dùng được, class `PurchaseOrder` cần một helper thiết lập `line.order = this` cùng `line.id.lineNo` nhất quán; ví dụ ở đây minh họa mapping, không phải implementation hoàn chỉnh của aggregate.

**`CascadeType.REMOVE` không tự động có vì `@MapsId`.** Việc xóa parent khi child còn tồn tại phụ thuộc mapping cascade, `orphanRemoval`, quy tắc foreign key và thiết kế nghiệp vụ. Database `ON DELETE CASCADE` là một cơ chế khác với cascade của JPA và phải được cấu hình riêng trong schema nếu sử dụng.

### Transaction và thời điểm khóa xuất hiện

Khi parent ID sử dụng `GenerationType.IDENTITY`, database có thể phải chạy `INSERT` parent trước để trả về ID. Nếu parent ID dùng `SEQUENCE` hoặc `TABLE`, provider có thể lấy số trước rồi chèn parent ở thời điểm flush thích hợp. Vì vậy:

- Đừng xây dựng nghiệp vụ dựa trên việc ID chắc chắn đã khác `null` ngay sau lệnh tạo đối tượng bằng `new`.
- Đừng giả định mọi SQL được thực thi đúng thứ tự dòng Java trong một transaction.
- Nếu cần kiểm chứng constraint hoặc có ID đã được đồng bộ trước bước xử lý tiếp theo, dùng transaction và `flush()` có chủ đích.
- `flush()` đồng bộ SQL trong transaction, **không phải commit**. Transaction vẫn có thể rollback.

## 9. Tính nhất quán giữa association và khóa ghép

Với `@MapsId`, một thành phần khóa chính chính là định danh của association. Đó vừa là lợi ích vừa là ràng buộc nghiệp vụ.

### 9.1. Không cập nhật khóa chính sau khi entity đã persistent

Ví dụ, một `OrderLine` đã lưu với khóa `(order_id = 42, line_no = 2)`. Nếu đổi `order` sang một `PurchaseOrder` khác, thành phần `orderId` của khóa sẽ phải đổi theo. JPA không bảo đảm hành vi portable khi thay identifier của entity đã persistent.

Thay vì:

```java
orderLine.changeOrder(otherOrder); // Thay một phần identity.
```

Nên mô hình hóa nghiệp vụ chuyển dòng sang đơn khác theo cách rõ ràng:

1. Tải/kiểm tra dòng hiện tại và đơn đích.
2. Tạo dòng mới với `OrderLineId` phù hợp (hoặc dùng identifier model khác nếu nghiệp vụ cần chuyển linh hoạt).
3. Xóa hoặc đánh dấu thay thế dòng cũ theo quy tắc nghiệp vụ.
4. Thực hiện trong transaction có kiểm soát.

### 9.2. Không tùy ý đưa hai nguồn giá trị trái ngược nhau

Không nên truyền cả `orderId` và `PurchaseOrder` rồi tự gán chúng mà không kiểm tra:

```java
public OrderLine(Long orderId, PurchaseOrder order, int lineNo) {
    this.id = new OrderLineId(orderId, lineNo);
    this.order = order; // Có thể chứa order.id khác orderId.
}
```

Thiết kế constructor đơn giản hơn là nhận `PurchaseOrder` và `lineNo`, rồi để `@MapsId` đồng bộ `orderId`. Đừng xem `id.orderId` và `order.id` là hai thuộc tính nghiệp vụ độc lập.

### 9.3. `equals()` và `hashCode()` cho lớp khóa

Lớp `@Embeddable` làm composite ID cần so sánh bằng giá trị và có semantics phù hợp với khóa database. Tránh:

```java
@Override
public boolean equals(Object other) {
    return this == other; // Sai mục đích của composite-key value type.
}
```

Hãy dùng tất cả thành phần khóa đúng type và logic so sánh phù hợp. Đồng thời tránh sửa những field tham gia `hashCode()` khi object đang nằm trong `HashSet` hoặc làm key trong `HashMap`: việc thay hash sau khi thêm vào collection có thể làm mất khả năng tra cứu.

Với entity có generated ID, trước khi persist khóa ghép có thể chứa phần ID `null`. Do đó, khi thiết kế `equals`/`hashCode` trên **entity**, phải cân nhắc vòng đời `transient → managed` để tránh các lỗi do ID thay đổi. Có thể tách rõ equality của **ID class** với equality của **entity**.

## 10. Truy vấn entity có khóa dẫn xuất

Sau khi mapping đúng, JPA vẫn truy vấn entity theo JPQL/Criteria như bình thường.

### 10.1. Tìm bằng `@EmbeddedId`

```java
OrderLineId id = new OrderLineId(orderId, 2);
OrderLine line = em.find(OrderLine.class, id);
```

Điều kiện là cả hai thành phần khóa đã biết. `EntityManager.find` nhận **đối tượng khóa ghép**, không nhận chỉ một `Long orderId` nếu entity định nghĩa `@EmbeddedId`.

### 10.2. Truy vấn theo đường dẫn khóa

```java
List<OrderLine> lines = em.createQuery(
        "select l from OrderLine l " +
        "where l.id.orderId = :orderId " +
        "order by l.id.lineNo",
        OrderLine.class)
    .setParameter("orderId", orderId)
    .getResultList();
```

`l.id.orderId` là đường dẫn **thuộc tính Java** của `OrderLineId`, không phải tên cột `order_id`. Provider dùng metadata ánh xạ để sinh SQL tương ứng.

### 10.3. Truy vấn qua association

```java
List<OrderLine> lines = em.createQuery(
        "select l from OrderLine l " +
        "where l.order.id = :orderId " +
        "order by l.id.lineNo",
        OrderLine.class)
    .setParameter("orderId", orderId)
    .getResultList();
```

Vì `l.order` ánh xạ tới quan hệ xác định `orderId`, provider có thể tối ưu truy vấn dựa trên cột foreign key. Không nên tự cam kết JPQL sẽ phát ra đúng một dạng SQL hoặc số JOIN cố định trên mọi provider.

### 10.4. Truy vấn enrollment theo hai thành phần

```java
EnrollmentId id = new EnrollmentId(studentId, courseId);
Enrollment enrollment = em.find(Enrollment.class, id);
```

Hoặc:

```java
List<Enrollment> enrollments = em.createQuery(
        "select e from Enrollment e " +
        "where e.student.id = :studentId " +
        "order by e.enrolledAt desc",
        Enrollment.class)
    .setParameter("studentId", studentId)
    .getResultList();
```

Các truy vấn này làm việc với entity `Enrollment`, còn `EnrollmentId` là object mang định danh, không phải entity truy vấn độc lập.

## 11. Mapping dữ liệu và ràng buộc ở database

Mặc dù `@MapsId` giúp provider hiểu derived identity, **database constraint vẫn rất quan trọng**.

| Bất biến cần bảo đảm | Nên thể hiện ở đâu? |
|---|---|
| Mỗi profile chỉ có một account ID | `account_profiles.id` là PK |
| Profile không tồn tại nếu không có account | FK `account_profiles.id → accounts.id` |
| Một đơn hàng không có hai dòng cùng `line_no` | Composite PK `(order_id, line_no)` |
| Dòng đơn phải trỏ đến order hợp lệ | FK `order_lines.order_id → purchase_orders.id` |
| Một sinh viên đăng ký mỗi khóa học tối đa một lần | Composite PK `(student_id, course_id)` |
| Trạng thái nghiệp vụ hợp lệ | Business method, validation và constraint phù hợp |

Đừng chỉ dựa vào annotation để bảo đảm ràng buộc đã được áp dụng ở database có schema từ trước. Nếu dùng migration, cần tạo đúng primary key, foreign key, nullability và index. Nếu để provider sinh schema, cần kiểm tra DDL và quy trình triển khai theo phiên bản provider.

### Khóa ngoại vừa nằm trong khóa chính có thể `NULL` không?

Theo mô hình quan hệ, cột thuộc primary key không được null. Vì vậy `order_id` của `order_lines` và `student_id`/`course_id` của `enrollments` không thể thiếu khi bản ghi được lưu hợp lệ. Mapping `optional = false` trên association thể hiện ý nghĩa tương ứng ở tầng ORM, nhưng database vẫn nên có primary key/foreign key constraint.

### Chỉ số và hiệu năng

Với `PRIMARY KEY(order_id, line_no)`, nhiều database tạo index phục vụ truy vấn theo `order_id` và theo cặp khóa. Tuy nhiên, truy vấn theo riêng `line_no` hoặc association thứ hai có thể cần index bổ sung.

Ví dụ, với bảng `enrollments`:

```sql
CREATE INDEX idx_enrollments_course_id
    ON enrollments(course_id);
```

Nếu primary key là `(student_id, course_id)`, một index riêng trên `course_id` có thể giúp truy vấn danh sách sinh viên của một khóa học. Hiệu quả phụ thuộc hệ quản trị và kế hoạch thực thi thực tế.

## 12. Lazy loading, batch fetching và các vấn đề về hiệu năng

`@MapsId` không tự giải quyết bài toán tải liên kết.

Ví dụ `Enrollment` có:

```java
@ManyToOne(fetch = FetchType.LAZY)
@MapsId("studentId")
private Student student;

@ManyToOne(fetch = FetchType.LAZY)
@MapsId("courseId")
private Course course;
```

Khi truy vấn nhiều enrollment rồi lần lượt truy cập `getStudent().getName()` hoặc `getCourse().getTitle()`, provider có thể phát sinh thêm nhiều truy vấn (hiện tượng **N+1**). Nếu dữ liệu cần hiển thị gồm tên sinh viên và tên khóa học, có thể dùng:

```java
List<Enrollment> items = em.createQuery(
        "select e from Enrollment e " +
        "join fetch e.student " +
        "join fetch e.course " +
        "where e.id.studentId = :studentId",
        Enrollment.class)
    .setParameter("studentId", studentId)
    .getResultList();
```

Hoặc dùng entity graph, projection/DTO và phân trang phù hợp.

Đặc biệt, với `@OneToOne` shared primary key, nhiều provider cần thêm thông tin để quyết định có thực sự tồn tại entity liên kết khi truy cập phía nghịch; một số cấu hình có thể phát sinh truy vấn ngay cả khi khai báo `LAZY`. Hành vi này phụ thuộc provider và khả năng enhancement; hãy xem SQL thực tế khi tối ưu.

**Không nhầm tối ưu truy vấn với mô hình khóa:** `@MapsId` diễn đạt identity; `JOIN FETCH`, entity graph, batch size và transaction scope giải quyết cách dữ liệu liên quan được tải.

## 13. Tương thích phiên bản và namespace

`@MapsId` đã là một phần của JPA từ các thế hệ trước Jakarta Persistence hiện đại. Cú pháp nhập package tùy thế hệ:

```java
// Ứng dụng JPA 2.x cũ:
import javax.persistence.MapsId;

// Ứng dụng Jakarta Persistence 3.x:
import jakarta.persistence.MapsId;
```

Các ví dụ trong bài sử dụng `jakarta.persistence`. Để chạy được, phải chọn Jakarta Persistence API, JPA provider và framework/container cùng thế hệ tương thích. Không trộn `javax.persistence` và `jakarta.persistence` tùy tiện trong cùng mapping.

### Lớp khóa composite và `record`

Các ví dụ `@EmbeddedId` dùng `@Embeddable class` thông thường có constructor không tham số và `Serializable`, phù hợp với kiểu viết code JPA truyền thống.

Jakarta Persistence 3.2 mở rộng khả năng dùng **Java record** làm embeddable và primary key class, nên có thể gặp:

```java
@Embeddable
public record OrderLineId(Long orderId, Integer lineNo) {}
```

Tuy nhiên, chỉ xem record là lựa chọn portable khi **phiên bản đặc tả và provider** đều hỗ trợ. Record vẫn không phải `@Entity`. Với derived identity và `@MapsId`, cần để provider đồng bộ giá trị ID; những trường hợp record immutable có thể có chi tiết khởi tạo khác class key mutable. Nếu dự án cần chạy trên JPA cũ hoặc nhiều provider, lớp `@Embeddable` thông thường là lựa chọn dễ bảo đảm tương thích hơn.

### Không dùng provider-specific annotation nếu không cần thiết

Hibernate có những cách ánh xạ derived identity và composite key riêng. Chúng có thể hữu ích trong một dự án chỉ dùng Hibernate, nhưng nếu mục tiêu là kiến trúc JPA portable, nên bắt đầu bằng `@MapsId` cùng `@EmbeddedId`/`@Id`, `@ManyToOne`/`@OneToOne` và `@JoinColumn`.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Provider báo không tìm được attribute trong `@MapsId("...")` | Dùng tên cột SQL thay vì tên property của lớp ID | Đổi thành đúng tên property Java trong `@EmbeddedId` |
| Lỗi duplicate column mapping | Khai báo cả ID field và join column độc lập nhưng thiếu `@MapsId` hoặc mapping không khớp | Dùng `@MapsId` để liên kết các mapping cùng cột |
| Trùng primary key ở bảng con | Tạo hai dòng cùng cặp khóa hoặc cùng shared ID | Kiểm tra identity model và constraint |
| Foreign-key violation | Entity cha chưa tồn tại/không được persist phù hợp | Persist cha trước hoặc cấu hình cascade có chủ đích |
| `TransientPropertyValueException` hoặc lỗi tương tự của provider | Quan hệ trỏ tới entity transient chưa được lưu | Kiểm tra trạng thái association và cascade |
| `NullPointerException` khi tạo `OrderLineId` | Khởi tạo/đọc khóa trước khi provider có đủ ID | Tạo object khóa hợp lệ phần tự cấp, gắn association, xác định thời điểm dùng ID |
| Lỗi khi đổi `order` của dòng đã lưu | Đổi relationship đồng thời đổi primary key | Thiết kế xóa/tạo dòng mới hoặc đổi mô hình ID |
| Chèn thành công nhưng quan hệ hai chiều đọc sai trong RAM | Không đồng bộ cả hai phía của association trong helper | Duy trì `parent.children` và `child.parent` nhất quán |
| N+1 query khi đọc liên kết | Fetch strategy không phù hợp | Dùng JPQL fetch join, entity graph hoặc DTO |
| Entity detached không tự cập nhật | Ngoài persistence context hoặc transaction | Tải lại/merge có chủ đích trong transaction |
| Không tìm được entity bằng `em.find(OrderLine.class, orderId)` | Khóa là composite ID chứ không phải `Long` | Tạo `new OrderLineId(orderId, lineNo)` |

### 14.1. Sai: chỉ ánh xạ khóa ghép, không liên kết `@MapsId`

```java
@EmbeddedId
private OrderLineId id;

@ManyToOne
@JoinColumn(name = "order_id")
private PurchaseOrder order;
```

Nếu `OrderLineId.orderId` cũng ánh xạ cột `order_id`, đoạn này có thể tạo hai mapping ghi cùng cột mà provider không biết một bên là nguồn identity của bên kia. Khai báo:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@MapsId("orderId")
@JoinColumn(name = "order_id")
private PurchaseOrder order;
```

### 14.2. Sai: áp dụng `@GeneratedValue` vào khóa phụ thuộc

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;

@OneToOne
@MapsId
private Account account;
```

Trong mô hình shared ID, profile phải sử dụng `Account.id` làm ID. Tạo thêm một generator độc lập cho cùng field `id` đi ngược ý nghĩa derived identity. Bỏ `@GeneratedValue` ở phía dependent.

### 14.3. Sai: hiểu `@MapsId` là khai báo cascade

```java
Account account = new Account("thao");
AccountProfile profile = new AccountProfile(account, "en");
em.persist(profile); // Không tự có cascade nếu relationship không cấu hình.
```

Để rõ ràng, có thể `em.persist(account)` trước khi persist profile. Nếu muốn persist profile kéo theo account, cần khai báo `cascade = CascadeType.PERSIST` và xem liệu hướng cascade đó có phù hợp mô hình nghiệp vụ không.

### 14.4. Sai: cho phép sửa thành phần khóa ghép như thuộc tính thường

```java
public void changeLineNo(int newLineNo) {
    this.id = new OrderLineId(id.getOrderId(), newLineNo);
}
```

Sau khi dòng hàng đã persistent, việc thay `lineNo` làm thay identity. Nếu cần reorder hiển thị, tách `displayOrder` là một thuộc tính thường khỏi khóa, hoặc thiết kế lại ID theo surrogate key. Không dùng sự thay đổi primary key để biểu diễn mọi thay đổi nghiệp vụ.

## 15. Một số quyết định thiết kế quan trọng

### Khi nào shared primary key thật sự phù hợp?

Phù hợp nếu đối tượng phụ thuộc:

- Có vòng đời gắn chặt với một entity chủ.
- Không cần định danh riêng có ý nghĩa khi tách khỏi chủ.
- Chỉ có tối đa một instance phụ thuộc trên mỗi principal.
- Được định vị tự nhiên bằng khóa của principal.

Ví dụ: profile mở rộng tài khoản, thiết lập đặc thù của một resource, metadata duy nhất cho một bản ghi gốc.

Nếu phía con có thể được chuyển sang chủ khác, sống độc lập, hoặc có nhiều bản ghi trên mỗi chủ, shared primary key có thể là ràng buộc quá chặt.

### Khi nào khóa ghép chứa association phù hợp?

Phù hợp nếu một entity có identity mang ý nghĩa **trong phạm vi một cha** hoặc **từ tổ hợp những thực thể liên kết**:

- `OrderLine(orderId, lineNo)`: số dòng duy nhất trong từng đơn.
- `Enrollment(studentId, courseId)`: một sinh viên với một khóa học.
- `InventoryBalance(warehouseId, productId)`: một dòng tồn kho cho mỗi cặp kho/sản phẩm.

Nếu thành phần khóa hay thay đổi, bị tham chiếu bởi quá nhiều bảng khác hoặc dài/cồng kềnh, có thể cân nhắc **surrogate key** (`Long id`/UUID) và thêm `UNIQUE` constraint cho cặp khóa nghiệp vụ. Khi đó association là foreign key thông thường, không nhất thiết dùng `@MapsId`.

### Đừng đồng nhất khóa ghép với quy tắc nghiệp vụ bất biến mãi mãi

Hôm nay một sinh viên chỉ được đăng ký một lần cho mỗi khóa học, nhưng ngày mai có thể có học kỳ, lần học lại hoặc lớp học phần khác nhau. Nếu ID chỉ gồm `studentId` và `courseId`, schema sẽ không biểu diễn được yêu cầu mới mà không thay đổi identity. Hãy kiểm tra quy tắc cardinality và vòng đời thật sự trước khi chốt composite PK.

## 16. Bài tập thực hành

### Bài tập A: hồ sơ tài khoản dùng cùng ID

Thiết kế hai bảng:

```text
users(id PK, email)
user_settings(user_id PK/FK -> users.id, theme)
```

Yêu cầu:

1. Tạo entity `User` có `@Id` do database cấp.
2. Tạo `UserSettings` với `@Id Long userId` và `@OneToOne @MapsId @JoinColumn(name="user_id")`.
3. Viết một transaction lưu user và settings.
4. Tải settings bằng `em.find(UserSettings.class, user.getId())`.
5. Quan sát rằng một user không thể có hai rows settings nhờ khóa chính chia sẻ.

### Bài tập B: dòng phiếu nhập kho

Schema:

```text
goods_receipts(id PK)
receipt_lines(receipt_id PK/FK, line_no PK, quantity)
```

Yêu cầu:

1. Tạo `ReceiptLineId(receiptId, lineNo)` với `@Embeddable`, `Serializable` và `equals/hashCode`.
2. Tạo `ReceiptLine` dùng `@EmbeddedId`.
3. Dùng `@ManyToOne @MapsId("receiptId")` để trỏ `GoodsReceipt`.
4. Viết transaction tạo một phiếu có ba dòng, kiểm tra các cặp khóa không trùng.
5. Thử tạo hai dòng cùng `(receiptId, lineNo)` và quan sát việc DB bảo vệ uniqueness.

### Bài tập C: bản ghi phân quyền

Schema:

```text
users(id PK)
roles(id PK)
user_roles(user_id PK/FK, role_id PK/FK, granted_at)
```

Yêu cầu:

1. Tạo `UserRoleId(userId, roleId)`.
2. Tạo entity `UserRole` với hai `@ManyToOne`, mỗi association có một `@MapsId` trỏ đúng thuộc tính ID.
3. Truy vấn các vai trò theo `user.id` bằng JPQL.
4. Cân nhắc có cần thời điểm hết hạn hoặc nhiều lần cấp lại vai trò hay không, rồi quyết định khóa ghép hiện tại đã đủ cho nghiệp vụ chưa.

## 17. Câu hỏi tự kiểm tra

**1. `@MapsId` được đặt trên `@EmbeddedId` hay trên association?**

Nó được đặt trên **field/getter của association** (`@ManyToOne` hoặc `@OneToOne`) để nói rằng quan hệ ấy cung cấp toàn bộ/một phần identity của entity phụ thuộc.

**2. `@MapsId("orderId")` có trỏ tới cột `order_id` không?**

Không trực tiếp. `"orderId"` là tên thuộc tính Java thuộc lớp `OrderLineId`. `@JoinColumn(name = "order_id")` mới chỉ rõ tên cột SQL của association.

**3. Vì sao `AccountProfile` không cần `@GeneratedValue`?**

Vì `AccountProfile.id` được lấy từ `Account.id` qua `@MapsId`. Nếu cấp thêm một dãy ID riêng, hai khóa có thể không trùng nhau, phá vỡ mô hình shared primary key.

**4. `@MapsId` có tự lưu account transient không?**

Không. Muốn lưu entity cha phải gọi `persist` phù hợp hoặc cấu hình cascade. `@MapsId` chỉ mô tả mối quan hệ về identity.

**5. Vì sao `OrderLine` dùng `@EmbeddedId` nhưng `PurchaseOrder` chỉ có `@Id`?**

Vì identity của dòng đơn là cặp `(orderId, lineNo)`, còn đơn hàng có một khóa `id` đơn. Hai entity không nhất thiết dùng cùng kiểu biểu diễn khóa.

**6. Có thể dùng hai `@MapsId` trong một entity không?**

Có, ví dụ `Enrollment` dùng `studentId` và `courseId`, mỗi thành phần lấy từ một association khác nhau.

**7. Khóa ghép có association có cần foreign key constraint ở database?**

Nên có. `@MapsId` mô tả ORM mapping, còn FK ở database bảo vệ dữ liệu khỏi tham chiếu không tồn tại, kể cả khi có truy cập bên ngoài JPA.

**8. Có nên thay `OrderLine.order` sau khi đã persist để chuyển dòng sang đơn khác?**

Không nên vì như vậy thay thành phần khóa chính. Mô hình nghiệp vụ thường cần tạo/xóa dòng hoặc chuyển sang thiết kế khóa khác.

**9. Nếu dùng `@EmbeddedId`, gọi `em.find(OrderLine.class, 42L)` có đúng không?**

Không. Phải truyền một `OrderLineId` gồm các thành phần khóa tương ứng.

**10. `@MapsId` có giúp tránh N+1 query tự động không?**

Không. Nó mô tả nguồn định danh; lazy/eager fetching, JPQL, entity graph và cách provider tạo SQL quyết định truy vấn phát sinh.

## 18. Tổng kết

`@MapsId` giải quyết bài toán **định danh dẫn xuất** trong JPA: khóa chính của entity phụ thuộc được lấy từ association với entity khác, toàn phần hoặc từng thành phần. Với **shared primary key**, `@Id` kết hợp `@OneToOne @MapsId` để hai entity dùng cùng một giá trị khóa. Với **khóa ghép có thành phần liên kết**, `@EmbeddedId` kết hợp `@ManyToOne @MapsId("tênThuộcTínhKhóa")` để liên kết thành phần của khóa ghép với khóa của entity cha; một entity có thể có nhiều association cùng tham gia tạo composite ID.

Thiết kế đúng cần bảo đảm cả hai tầng: ở **Java/JPA**, mapping khóa, tên thuộc tính và association nhất quán; ở **database**, composite primary key và foreign key ràng buộc dữ liệu đúng. `@MapsId` không tự bật cascade, không cho phép thay đổi identity sau khi lưu, và không thay thế quyết định về transaction hay fetch strategy.

Khi khóa của một entity thực sự phụ thuộc vào entity khác, `@MapsId` giúp mã nguồn diễn đạt chính xác quy tắc miền, giảm thao tác sao chép ID thủ công và tạo một mô hình ORM rõ ràng hơn cho các cấu trúc khóa chia sẻ và khóa ghép.
