# Phía sở hữu quan hệ và vai trò của `mappedBy` trong JPA

Trong Java Persistence API (JPA), hai entity có thể liên kết với nhau qua `@ManyToOne`, `@OneToMany`, `@OneToOne` hoặc `@ManyToMany`. Một câu hỏi quan trọng khi ánh xạ **quan hệ hai chiều** (*bidirectional relationship*) là: **Phía nào chịu trách nhiệm duy trì liên kết trong cơ sở dữ liệu?**

JPA gọi phía đó là **phía sở hữu quan hệ** (*owning side*). Phía còn lại là **phía nghịch đảo** (*inverse/non-owning side*); phía nghịch đảo thường khai báo thuộc tính `mappedBy` để nói với JPA rằng liên kết thực sự được quản lý bởi một thuộc tính ở entity đối diện.

Hiểu đúng phía sở hữu và `mappedBy` giúp tránh các lỗi: sinh thêm bảng/cột không mong muốn, khóa ngoại không được cập nhật, quan hệ chỉ đúng trong bộ nhớ nhưng sai trong database, hoặc lưu một entity mà JPA không biết liên kết nó với entity còn lại.

Bài học thuộc chủ đề **Quan hệ thực thể**, tập trung vào nguyên lý sở hữu liên kết, ba loại quan hệ hai chiều thường gặp, cách đồng bộ hai phía, và các trường hợp cần phân biệt với cascade, orphan removal, fetch và transaction.

## 1. Cùng một quan hệ, hai hướng nhìn

Giả sử hệ thống bán hàng có đơn hàng và các dòng hàng:

- Một đơn hàng `PurchaseOrder` có nhiều `OrderLine`.
- Mỗi dòng hàng thuộc về đúng một đơn hàng.
- Cơ sở dữ liệu lưu bảng `purchase_order` và `order_line`.
- Bảng `order_line` có khóa ngoại `order_id` trỏ tới `purchase_order.id`.

Sơ đồ quan hệ:

```text
                purchase_order
             +------------------+
             | id (PK)          |
             | order_code       |
             +------------------+
                    ^
                    |
                    | order_line.order_id
                    | (FK -> purchase_order.id)
                    |
             +------------------+
             | order_line       |
             +------------------+
             | id (PK)          |
             | order_id (FK)    |
             | sku              |
             | quantity         |
             +------------------+

  Java:
  PurchaseOrder -----------------> List<OrderLine>
       <-------------------------- OrderLine.order
               hai hướng đi
```

Ở Java, một đối tượng `PurchaseOrder` có thể đi tới danh sách `OrderLine`; đồng thời mỗi `OrderLine` có thể đi ngược về `PurchaseOrder`. Đó là **quan hệ hai chiều**.

Tuy nhiên, dưới tầng SQL chỉ cần **một quan hệ khóa ngoại**: `order_line.order_id`. Nếu JPA hiểu hai hướng Java là hai quan hệ độc lập, mapping có thể sinh thêm join table hoặc không cập nhật đúng FK. `mappedBy` cho JPA biết rằng **hai tham chiếu Java là hai mặt của cùng một liên kết**.

## 2. Hai khái niệm nền tảng: owning side và inverse side

### 2.1. Phía sở hữu quan hệ là gì?

**Owning side** là phía được JPA dùng làm nguồn ánh xạ chính để **ghi thay đổi của liên kết** xuống database.

Trong quan hệ hai chiều `PurchaseOrder`–`OrderLine`:

```java
// Ở OrderLine: owning side.
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "order_id")
private PurchaseOrder order;
```

`OrderLine.order` là phía sở hữu vì thuộc tính này ánh xạ trực tiếp khóa ngoại `order_id`.

Nếu một `OrderLine` đang managed chuyển từ đơn hàng A sang đơn hàng B bằng cách cập nhật thuộc tính `order`, JPA có cơ sở để cập nhật cột `order_id` khi đồng bộ transaction.

**Phía sở hữu không nhất thiết là entity “cha” trong nghiệp vụ.** Một đơn hàng có thể sở hữu các dòng hàng theo nghĩa domain hoặc aggregate, nhưng với mapping quan hệ `@OneToMany`/`@ManyToOne` hai chiều, phía JPA sở hữu liên kết lại là `OrderLine.order` ở phía many.

Cần phân biệt:

| “Sở hữu” theo ngữ cảnh | Ý nghĩa |
|---|---|
| **Sở hữu quan hệ của JPA** | Phía nào định nghĩa liên kết để ghi FK/join table |
| **Sở hữu nghiệp vụ/aggregate** | Đối tượng nào chịu trách nhiệm giữ invariant nghiệp vụ |
| **Sở hữu vòng đời con** | Có cascade, orphan removal hay quy tắc xóa phụ thuộc hay không |
| **Chủ dữ liệu/bảo mật** | Ai có quyền đọc, cập nhật dữ liệu trong hệ thống |

Một entity có thể là chủ thể nghiệp vụ nhưng vẫn nằm ở phía nghịch đảo của mapping JPA.

### 2.2. Phía nghịch đảo là gì?

**Inverse side** thể hiện khả năng đi theo hướng ngược lại của một quan hệ hai chiều. Nó **không định nghĩa một liên kết SQL thứ hai**.

Ví dụ:

```java
// Ở PurchaseOrder: inverse side.
@OneToMany(mappedBy = "order")
private List<OrderLine> lines = new ArrayList<>();
```

Cụm `mappedBy = "order"` có nghĩa: “Danh sách `PurchaseOrder.lines` phản ánh cùng quan hệ mà thuộc tính **`OrderLine.order`** đang sở hữu”.

Nhờ vậy JPA biết:

- Cột khóa ngoại nằm ở mapping `OrderLine.order`.
- Không cần một quan hệ độc lập chỉ vì `PurchaseOrder` có collection `lines`.
- `PurchaseOrder.lines` là phía nghịch đảo của liên kết.
- Khi ghi FK, phía sở hữu quyết định quan hệ được lưu.

**Inverse không có nghĩa chỉ đọc (read-only).** Bạn vẫn có thể thay đổi collection trong Java, duyệt collection, dùng cascade trên inverse side và query qua liên kết. Điểm mấu chốt là **thay đổi phía inverse một mình không phải cách đủ để chỉ định thay đổi khóa ngoại**.

### 2.3. `mappedBy` là tên Java, không phải tên SQL

Đây là nguyên tắc phải nhớ:

```java
@Entity
public class OrderLine {
    @ManyToOne
    @JoinColumn(name = "order_id") // Tên CỘT SQL.
    private PurchaseOrder order;  // Tên THUỘC TÍNH Java.
}
```

Khi khai báo phía đối diện:

```java
@OneToMany(mappedBy = "order") // ĐÚNG: tên thuộc tính Java.
private List<OrderLine> lines;
```

Các dạng sau sai ý nghĩa:

```java
@OneToMany(mappedBy = "order_id")       // SAI: tên cột SQL.
private List<OrderLine> lines;

@OneToMany(mappedBy = "purchase_order") // SAI: tên bảng SQL.
private List<OrderLine> lines;

@OneToMany(mappedBy = "OrderLine")      // SAI: tên lớp.
private List<OrderLine> lines;
```

`mappedBy` tham chiếu tới **thuộc tính quan hệ ở phía đối diện**, chứ không phải bảng, tên cột, tên khóa chính hay tên lớp. Tên đó phải đúng chính tả và chữ hoa/chữ thường. Nếu phía owner đổi tên field `order` thành `purchaseOrder`, khai báo `mappedBy` tương ứng phải đổi thành `"purchaseOrder"`.

## 3. Ví dụ đầy đủ: `@OneToMany` và `@ManyToOne` hai chiều

Đây là loại quan hệ phù hợp nhất để làm rõ sở hữu.

### 3.1. Entity cha: `PurchaseOrder`

```java
package com.example.persistence;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_code", nullable = false, unique = true)
    private String orderCode;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
        // Constructor cho JPA.
    }

    public PurchaseOrder(String orderCode) {
        if (orderCode == null || orderCode.isBlank()) {
            throw new IllegalArgumentException("Mã đơn hàng không hợp lệ");
        }
        this.orderCode = orderCode;
    }

    public Long getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(OrderLine line) {
        Objects.requireNonNull(line, "line");

        if (line.getOrder() != null && line.getOrder() != this) {
            throw new IllegalStateException(
                "Dòng hàng đã thuộc đơn khác"
            );
        }

        if (!lines.contains(line)) {
            lines.add(line);
        }
        line.attachTo(this); // Cập nhật phía sở hữu.
    }

    public void removeLine(OrderLine line) {
        if (lines.remove(line)) {
            line.attachTo(null); // Dọn tham chiếu phía sở hữu.
        }
    }
}
```

Phân tích:

- `@OneToMany` mô tả từ **một** đơn hàng tới **nhiều** dòng hàng.
- `mappedBy = "order"` khiến collection `lines` là phía **inverse**.
- `CascadeType.ALL` cho phép nhiều thao tác lifecycle được truyền từ `PurchaseOrder` tới các dòng hàng; không làm `PurchaseOrder` trở thành owning side của FK.
- `orphanRemoval = true` cho biết khi dòng hàng bị loại khỏi quan hệ sở hữu vòng đời, JPA có thể xóa entity con khỏi database theo quy tắc orphan removal; cũng không làm thay đổi sở hữu FK.
- `addLine` và `removeLine` cập nhật **cả collection và trường `order`** để giữ object graph nhất quán.

`Collections.unmodifiableList` giúp code gọi bên ngoài không tự thêm/xóa phần tử mà bỏ qua phương thức đồng bộ quan hệ. Đó là một cách giữ bất biến trong mô hình này; JPA vẫn có thể thao tác với field persistent bằng field access.

### 3.2. Entity con: `OrderLine`

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

@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false, length = 64)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {
    }

    public OrderLine(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        this.sku = sku;
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    void attachTo(PurchaseOrder order) {
        this.order = order; // Phương thức hỗ trợ package-local.
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }
}
```

**Phía sở hữu là `OrderLine.order`**, vì:

1. `@ManyToOne` gắn với `@JoinColumn(name = "order_id")`.
2. Cột `order_id` nằm trong bảng `order_line` và trỏ đến `purchase_order.id`.
3. Khi quan hệ đổi, JPA nhìn vào trạng thái của thuộc tính `order` trên entity con.

Trong ví dụ này, `optional = false` và `nullable = false` diễn đạt rằng dòng hàng phải có đơn hàng. Khi tạo dòng hàng mới, phải gọi `order.addLine(line)` trước khi persist. Khi loại dòng hàng khỏi đơn, `orphanRemoval = true` phù hợp với quy tắc “dòng hàng không thể sống độc lập”; nếu không muốn xóa mà muốn chuyển dòng hàng sang một đơn khác, cần thiết kế phương thức riêng và xem xét hành vi orphan removal trước khi sửa.

### 3.3. Tạo và lưu một đơn hàng

```java
PurchaseOrder order = new PurchaseOrder("PO-2026-001");

OrderLine first = new OrderLine("BOOK-01", 2);
OrderLine second = new OrderLine("PEN-02", 5);

order.addLine(first);
order.addLine(second);

// Giả sử đang ở trong transaction và em là EntityManager hợp lệ.
entityManager.persist(order);

// CascadeType.ALL có PERSIST, nên các OrderLine mới
// cũng được persist; thuộc tính order ở phía owning side
// đã trỏ tới PurchaseOrder tương ứng.
```

Với lược đồ khái niệm:

```sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    order_code VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_order(id)
);
```

DDL trên bỏ qua cú pháp sinh ID tự động vì mỗi DB hỗ trợ `IDENTITY` theo cách khác nhau.

Sau commit, dữ liệu có thể như sau:

**Bảng `purchase_order`**

| id | order_code |
|---:|---|
| 10 | PO-2026-001 |

**Bảng `order_line`**

| id | order_id | sku | quantity |
|---:|---:|---|---:|
| 101 | 10 | BOOK-01 | 2 |
| 102 | 10 | PEN-02 | 5 |

Dù Java có cả `order.lines` và `line.order`, database chỉ cần khóa ngoại `order_line.order_id`. `mappedBy` cho JPA biết đây là **một quan hệ được biểu diễn theo hai chiều trong Java**.

### 3.4. Điều gì xảy ra nếu chỉ sửa phía nghịch đảo?

Ví dụ thiếu đồng bộ:

```java
PurchaseOrder order =
    entityManager.find(PurchaseOrder.class, 10L);

OrderLine line = new OrderLine("NOTE-03", 1);

// Giả sử entity có phương thức cho phép sửa list trực tiếp:
order.getInternalLines().add(line);

// Chưa gán line.order = order!
```

Ở mức Java, collection của `order` có thể chứa `line`. Nhưng **phía owning `line.order` vẫn là `null`**. JPA không có thông tin đúng từ owning side để ghi `order_id`.

Tùy các cascade, nullable constraint và trạng thái entity, kết quả có thể là:

- Dòng hàng được persist nhưng thiếu liên kết, dẫn tới lỗi ràng buộc `NOT NULL`/FK.
- Liên kết không được cập nhật như người viết code mong muốn.
- Object graph đang chạy thiếu nhất quán với dữ liệu database.

Không nên dựa vào những tác động phụ tùy provider để tự “hàn gắn” hai phía. Phương pháp rõ ràng là gọi **`order.addLine(line)`**, nơi code chủ động cập nhật cả `order.lines` và `line.order`.

### 3.5. Chỉ sửa phía sở hữu có đủ để ghi database không?

Giả sử có hai entity managed:

```java
OrderLine line = entityManager.find(OrderLine.class, 101L);
PurchaseOrder newOrder =
    entityManager.find(PurchaseOrder.class, 11L);

line.attachTo(newOrder); // Sửa owning side.
```

Phía owner đã đổi nên JPA có căn cứ cập nhật `order_id` thành 11 ở thời điểm flush/commit thích hợp. **Nhưng hai collection trong bộ nhớ** có thể vẫn không phản ánh sự thay đổi:

- `oldOrder.lines` có thể còn `line`.
- `newOrder.lines` có thể chưa chứa `line`.

Đó là lỗi **tính nhất quán của object graph**. Vì vậy luôn đồng bộ cả hai phía khi ứng dụng cần sử dụng quan hệ hai chiều. Ví dụ này còn dùng orphan removal trong mô hình đã giới thiệu; việc “chuyển” con giữa hai aggregate có orphan removal cần một quy tắc riêng, không chỉ gán lại field.

## 4. Tại sao `@ManyToOne` thường là owning side?

Trong mô hình quan hệ một-nhiều:

```text
parent (1) ----------------------------- child (N)
   id                                      parent_id (FK)
```

Khóa ngoại nằm trên bảng **many**. Do đó với mapping **hai chiều** `@OneToMany`/`@ManyToOne`:

- `@ManyToOne` luôn là phía sở hữu quan hệ theo quy tắc JPA.
- `@OneToMany(mappedBy = "...")` là phía nghịch đảo tương ứng.
- `mappedBy` phải chỉ đến thuộc tính `@ManyToOne` của entity con.
- `@JoinColumn` để chỉ định cột FK thường nằm bên `@ManyToOne`.

Ví dụ đúng:

```java
// Child.java
@ManyToOne
@JoinColumn(name = "parent_id")
private Parent parent;

// Parent.java
@OneToMany(mappedBy = "parent")
private List<Child> children;
```

Ví dụ sai về mặt ý định:

```java
// Parent.java
@OneToMany(mappedBy = "parent_id")
private List<Child> children;
```

`parent_id` là tên SQL column, trong khi `mappedBy` cần tên Java association `parent`.

**Không đặt `mappedBy` trên `@ManyToOne`**. Trong JPA, annotation `@ManyToOne` không có phần tử `mappedBy`. Đây là điểm khác với `@OneToMany`, `@OneToOne` và `@ManyToMany`.

## 5. Quy tắc sở hữu theo từng loại quan hệ

| Quan hệ | Phía owning side trong mapping hai chiều | Phía inverse dùng `mappedBy` | Cấu trúc DB phổ biến |
|---|---|---|---|
| **`@ManyToOne` ↔ `@OneToMany`** | `@ManyToOne` | `@OneToMany(mappedBy = "...")` | FK trên bảng phía many |
| **`@OneToOne` ↔ `@OneToOne`** | Phía khai báo mapping FK/join tương ứng | `@OneToOne(mappedBy = "...")` ở phía còn lại | FK có unique constraint hoặc shared PK |
| **`@ManyToMany` ↔ `@ManyToMany`** | Phía quản lý bảng nối, thường khai báo `@JoinTable` | `@ManyToMany(mappedBy = "...")` | Bảng nối có hai FK |
| **Quan hệ một chiều** | Phía duy nhất có thuộc tính quan hệ | Không có inverse side; không dùng `mappedBy` | FK hoặc join table tùy loại mapping |

Không có quy tắc “đối tượng nào được khai báo trước thì sở hữu” hay “entity cha luôn sở hữu”. Phía sở hữu được quyết định bởi loại và cấu hình **association mapping**.

## 6. `@OneToOne`: một bên quản lý khóa ngoại

### 6.1. Ví dụ tài khoản và cấu hình tài khoản

Giả sử mỗi tài khoản có tối đa một bản cấu hình. Bảng `account_settings` chứa khóa ngoại `account_id` tham chiếu `account.id`.

```text
account                         account_settings
+-----------------+             +--------------------------+
| id (PK)         |<------------| account_id (FK, UNIQUE)  |
| username        |             | id (PK)                  |
+-----------------+             | theme                    |
                                +--------------------------+
```

Entity `Account` ở phía inverse:

```java
@Entity
@Table(name = "account")
public class Account {

    @Id
    @GeneratedValue
    private Long id;

    private String username;

    @OneToOne(mappedBy = "account", cascade = CascadeType.ALL)
    private AccountSettings settings;

    protected Account() {
    }

    public void setSettings(AccountSettings settings) {
        if (this.settings == settings) {
            return;
        }

        AccountSettings old = this.settings;
        this.settings = settings;

        if (old != null) {
            old.attachTo(null);
        }
        if (settings != null) {
            settings.attachTo(this);
        }
    }
}
```

Entity `AccountSettings` ở phía owning:

```java
@Entity
@Table(name = "account_settings")
public class AccountSettings {

    @Id
    @GeneratedValue
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "account_id", unique = true)
    private Account account;

    @Column(nullable = false)
    private String theme;

    protected AccountSettings() {
    }

    public Account getAccount() {
        return account;
    }

    void attachTo(Account account) {
        this.account = account;
    }
}
```

Ý nghĩa:

- `AccountSettings.account` giữ FK `account_id`, nên là **owning side**.
- `Account.settings` có `mappedBy = "account"`, nên là **inverse side**.
- `unique = true` diễn đạt một tài khoản không được gắn vào nhiều dòng settings, phù hợp ý định một-một; cần bảo đảm schema DB có ràng buộc thực tế.
- `cascade = ALL` ở inverse side vẫn có thể cascade persist/merge/remove theo cấu hình. Nó **không đổi ownership của `account_id`**.

Phương thức `setSettings` chỉ để minh họa đồng bộ liên kết. Trong hệ thống có orphan removal hoặc yêu cầu thay thế settings phức tạp, cần thiết kế cả việc xử lý settings cũ (xóa, tách, chuyển giao) để phù hợp ràng buộc FK và vòng đời.

### 6.2. Đổi chiều owner ở `@OneToOne` có được không?

Có thể lựa chọn phía sở hữu trong mô hình một-một khi schema và ràng buộc cho phép. Nếu muốn bảng `account` chứa FK `settings_id`, phía `Account` có thể là owning side bằng `@JoinColumn(name = "settings_id")`, còn `AccountSettings` dùng `mappedBy` trỏ về thuộc tính trong `Account`.

**Thay ownership trong code không tự di chuyển cột FK đang tồn tại**. Nếu ứng dụng đã có dữ liệu, cần schema migration phù hợp.

### 6.3. Shared primary key và `@MapsId`

Một dạng một-một dùng cùng ID cho hai bảng, ví dụ `AccountSettings.id` cũng là FK tới `Account.id`:

```java
@Entity
public class AccountSettings {

    @Id
    private Long id;

    @OneToOne(optional = false)
    @MapsId
    @JoinColumn(name = "id")
    private Account account;

    protected AccountSettings() {
    }
}
```

`@MapsId` cho biết identifier của settings được dẫn xuất từ association với account. Đây là cách ánh xạ **derived identity**, không phải một ý nghĩa mới của `mappedBy`. Ở phía `Account` vẫn có thể khai báo `@OneToOne(mappedBy = "account")` nếu muốn điều hướng hai chiều.

## 7. `@ManyToMany`: phía sở hữu quản lý bảng nối

### 7.1. Cấu trúc quan hệ nhiều-nhiều

Giả sử một sinh viên đăng ký nhiều khóa học và một khóa học có nhiều sinh viên:

```text
student                 student_course                 course
+----------+       +----------------------+       +----------+
| id (PK)  |<------| student_id (FK)      |       | id (PK)  |
| name     |       | course_id (FK)       |------>| title    |
+----------+       +----------------------+       +----------+
```

Ở đây không có FK trực tiếp trong `student` hay `course`; liên kết nằm trong **bảng nối** (*join table*) `student_course`.

### 7.2. Chọn phía sở hữu

Entity `Student` làm owner:

```java
@Entity
public class Student {

    @Id
    private Long id;

    private String name;

    @ManyToMany
    @JoinTable(
        name = "student_course",
        joinColumns = @JoinColumn(name = "student_id"),
        inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();

    protected Student() {
    }

    public void enroll(Course course) {
        if (courses.add(course)) {
            course.registerStudent(this);
        }
    }

    public void withdraw(Course course) {
        if (courses.remove(course)) {
            course.unregisterStudent(this);
        }
    }
}
```

Entity `Course` làm inverse side:

```java
@Entity
public class Course {

    @Id
    private Long id;

    private String title;

    @ManyToMany(mappedBy = "courses")
    private Set<Student> students = new HashSet<>();

    protected Course() {
    }

    void registerStudent(Student student) {
        students.add(student);
    }

    void unregisterStudent(Student student) {
        students.remove(student);
    }
}
```

Trong ví dụ này:

- `Student.courses` là **owning side**, định nghĩa `@JoinTable` và các cột FK.
- `Course.students` là **inverse side**, với `mappedBy = "courses"` trỏ tới tên Java property của `Student`.
- Khi `student.enroll(course)` thêm phần tử vào phía owner, JPA có thể ghi một dòng vào `student_course` ở thời điểm đồng bộ.
- Khi `student.withdraw(course)` xóa phần tử khỏi phía owner, JPA có thể xóa liên kết tương ứng trong bảng nối.
- Thay đổi chỉ ở `course.students` không phải cách chuẩn để cập nhật join table.

**Lưu ý về `Set` và equality:** Khi dùng entity trong `HashSet`, cần có chính sách `equals`/`hashCode` phù hợp với vòng đời ID, proxy và trạng thái mutable. Ví dụ trên tập trung vào ownership, còn thiết kế equality của `Student`/`Course` cần được hoàn thiện khi đưa vào ứng dụng. Không tùy tiện xây `hashCode` từ collection hai chiều vì có thể gây vòng lặp và thay đổi hash khi liên kết đổi.

### 7.3. Có thể chọn `Course` làm owning side không?

Có. Khi thiết kế từ đầu, có thể đặt `@JoinTable` ở `Course.students` và `mappedBy = "students"` ở `Student.courses`, miễn toàn bộ mapping nhất quán với một owner.

Nên chọn phía owner theo cách ứng dụng thường tạo/xóa liên kết và nơi đặt helper method rõ ràng. Tuy nhiên, nếu đã có schema/migration thì phải bảo đảm tên bảng nối, hai FK và các ràng buộc hiện có không bị đổi ngoài ý muốn.

### 7.4. Quan hệ nhiều-nhiều có dữ liệu bổ sung

Nếu bảng đăng ký học còn có `enrolled_at`, `grade` hoặc `status`:

```text
enrollment
+-------------+-------------+-------------+--------+
| student_id  | course_id   | enrolled_at | grade  |
+-------------+-------------+-------------+--------+
```

Lúc này thường nên mô hình hóa `Enrollment` như một **entity trung gian** với hai `@ManyToOne`:

```java
@Entity
public class Enrollment {

    @EmbeddedId
    private EnrollmentId id;

    @ManyToOne(fetch = FetchType.LAZY)
    @MapsId("studentId")
    @JoinColumn(name = "student_id")
    private Student student;

    @ManyToOne(fetch = FetchType.LAZY)
    @MapsId("courseId")
    @JoinColumn(name = "course_id")
    private Course course;

    private java.time.Instant enrolledAt;

    private String grade;

    protected Enrollment() {
    }
}
```

Giả sử `EnrollmentId` là `@Embeddable` với hai thuộc tính `studentId`, `courseId` và có `equals/hashCode` thích hợp. Đây là mẫu rút gọn; cần bổ sung constructor và quy tắc nghiệp vụ.

`Enrollment` làm rõ rằng bản ghi đăng ký học có thuộc tính và vòng đời riêng, thay vì chỉ là một cạnh nối hai entity. Lúc đó quan hệ từ `Student` hoặc `Course` tới `Enrollment` có thể là `@OneToMany(mappedBy = "student")` / `@OneToMany(mappedBy = "course")`. Phía sở hữu của từng liên kết là các `@ManyToOne` trong `Enrollment`.

## 8. Quan hệ một chiều: không có `mappedBy`

`mappedBy` chỉ có ý nghĩa khi có **hai hướng Java cùng biểu diễn một liên kết**. Nếu entity chỉ giữ một tham chiếu đơn phương, thường không khai báo `mappedBy`.

### 8.1. `@ManyToOne` một chiều

```java
@Entity
public class SupportTicket {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "assignee_id")
    private Employee assignee;

    protected SupportTicket() {
    }
}
```

Nếu `Employee` không có collection `tickets`, đây vẫn là quan hệ một-nhiều về mặt dữ liệu: nhiều ticket có thể cùng một assignee. Mapping chỉ cho phép đi từ ticket sang employee. Không có inverse property nên **không cần `mappedBy`**.

### 8.2. `@OneToOne` một chiều

```java
@Entity
public class UserAccount {

    @Id
    private Long id;

    @OneToOne
    @JoinColumn(name = "avatar_id", unique = true)
    private Avatar avatar;

    protected UserAccount() {
    }
}
```

`UserAccount.avatar` là phía ánh xạ duy nhất; `Avatar` không cần property trỏ ngược về `UserAccount`.

### 8.3. `@OneToMany` một chiều có thể dùng join table

```java
@Entity
public class Playlist {

    @Id
    private Long id;

    @OneToMany
    private List<PlaylistEntry> entries = new ArrayList<>();

    protected Playlist() {
    }
}
```

Với một `@OneToMany` **một chiều** không cấu hình thêm, JPA thường ánh xạ bằng **join table** mặc định. Điều này có thể khác mong đợi nếu người viết code nghĩ luôn có FK `playlist_id` trong bảng `playlist_entry`.

Có thể cấu hình `@JoinColumn` cho một số mapping một chiều phù hợp:

```java
@OneToMany
@JoinColumn(name = "playlist_id")
private List<PlaylistEntry> entries;
```

Ở cách một chiều này, phía collection là nơi định nghĩa liên kết; không có `mappedBy`. Khả năng phát sinh câu SQL, thời điểm cập nhật FK và cách provider đồng bộ collection có thể khác với mô hình hai chiều `@ManyToOne` owner. Nếu entity con có khái niệm cha rõ ràng, mapping hai chiều với `@ManyToOne` owner thường dễ diễn đạt quan hệ khóa ngoại hơn.

### 8.4. Một chiều không có nghĩa chỉ truy vấn được một chiều trong SQL

Dù Java không có `employee.getTickets()`, ứng dụng vẫn có thể truy vấn ticket theo assignee thông qua JPQL/Criteria hoặc SQL. Điều hướng object và khả năng join SQL là hai khái niệm khác nhau.

## 9. `mappedBy` và `@JoinColumn` khác nhau

| Annotation/thuộc tính | Viết ở đâu | Ý nghĩa |
|---|---|---|
| `@JoinColumn(name = "order_id")` | Phía owner của quan hệ có FK | Chỉ định cột FK, ràng buộc liên quan |
| `@JoinTable(...)` | Phía owner của quan hệ dùng bảng nối | Chỉ định bảng nối và các cột FK |
| `mappedBy = "order"` | Phía inverse của quan hệ hai chiều | Trỏ tới **tên thuộc tính Java** ở owning side |
| `@Column(name = "sku")` | Basic attribute | Ánh xạ cột dữ liệu thường, không định nghĩa association |
| `@ForeignKey` | Cấu hình trong join annotation phù hợp | Định hướng sinh ràng buộc FK khi schema generation |
| `@MapsId` | Association tham gia derived identity | Liên kết khóa chính với định danh entity khác |

Trong một quan hệ hai chiều đơn giản, không nên khai báo cùng liên kết theo kiểu:

```java
// Không phải cấu hình một quan hệ hai chiều chuẩn:
@OneToMany(mappedBy = "order")
@JoinColumn(name = "order_id")
private List<OrderLine> lines;
```

Ở phía inverse, `mappedBy` đã chỉ ra phía nào định nghĩa FK. Đồng thời chỉ định `@JoinColumn` như thể phía inverse cũng sở hữu FK làm ý nghĩa cấu hình mâu thuẫn. Hãy đặt `@JoinColumn(name = "order_id")` trên `OrderLine.order`.

Tương tự, phía nghịch đảo `@ManyToMany(mappedBy = "courses")` không nên định nghĩa thêm bảng nối độc lập với `@JoinTable` cho cùng một quan hệ.

## 10. Cách đồng bộ hai phía trong code nghiệp vụ

### 10.1. Một liên kết SQL, hai tham chiếu Java

Trong cơ sở dữ liệu:

```text
order_line.order_id = 10
```

Trong object graph hai chiều:

```java
line.getOrder() == order
order.getLines().contains(line)
```

Hai biểu thức cần thống nhất nếu ứng dụng muốn thao tác trên một object graph nhất quán. JPA không cam kết tự sửa mọi collection và reference trong bộ nhớ ngay khi bạn chỉ đổi một phía.

Đối với các quan hệ có ràng buộc nghiệp vụ, nên tổ chức phương thức thay đổi liên kết tại **một nơi có trách nhiệm rõ ràng**, ví dụ `order.addLine(line)`.

### 10.2. Helper method nên làm gì?

Một helper tốt thường:

1. Kiểm tra dữ liệu và invariant.
2. Tránh thêm trùng hoặc rơi vào vòng lặp gọi setter qua lại.
3. Cập nhật reference ở **owning side**.
4. Cập nhật collection/reference ở **inverse side**.
5. Xử lý quan hệ cũ nếu có chuyển chủ sở hữu.
6. Tôn trọng quy tắc xóa con, không tùy ý null hóa FK bắt buộc.

Ví dụ đơn giản cho quan hệ không có orphan removal:

```java
public class Team {

    @OneToMany(mappedBy = "team")
    private Set<Member> members = new HashSet<>();

    public void addMember(Member member) {
        if (member.getTeam() == this) {
            members.add(member);
            return;
        }

        Team oldTeam = member.getTeam();
        if (oldTeam != null) {
            oldTeam.members.remove(member);
        }

        member.setTeamInternal(this); // Owning side: Member.team.
        members.add(member);
    }

    public void removeMember(Member member) {
        if (members.remove(member) && member.getTeam() == this) {
            member.setTeamInternal(null);
        }
    }
}
```

`Member` giả định có `@ManyToOne Team team`, getter `getTeam()` và method nội bộ `setTeamInternal(Team)`. Đây là đoạn logic minh họa, chưa phải lớp entity đầy đủ.

Nếu `Member.team` có `optional = false`/FK NOT NULL, không thể giữ member ở trạng thái không có team sau commit. Khi đó thao tác “remove” phải gắn với **xóa member, chuyển team mới hoặc một quy tắc khác phù hợp**.

### 10.3. Tránh gọi hai setter lẫn nhau vô hạn

Cấu trúc nguy hiểm:

```java
// Parent
public void addChild(Child child) {
    children.add(child);
    child.setParent(this);
}

// Child
public void setParent(Parent parent) {
    this.parent = parent;
    parent.addChild(this); // Gọi lại vô hạn nếu không có điều kiện.
}
```

Có thể gây đệ quy không dừng. Hãy chọn một phương thức công khai làm điểm điều phối và một setter nội bộ chỉ gán field, hoặc dùng điều kiện dừng và kiểm tra liên kết cũ một cách rõ ràng.

### 10.4. Không suy ra quan hệ từ `equals/hashCode`

Collection `Set` hoặc các hàm `contains/remove` có thể phụ thuộc vào `equals/hashCode`. Với entity có ID do DB sinh, identity có thể là `null` trước persist. Nếu `hashCode` thay đổi sau khi ID được cấp, `HashSet` có thể không tìm được phần tử đã thêm.

Ngoài ra, đưa liên kết hai chiều vào `toString`/`equals`/`hashCode` dễ gây vòng lặp:

```text
Order.toString()
  -> Order.lines
      -> OrderLine.order
          -> Order.lines
              -> ...
```

Nên chọn chiến lược equality cho entity phù hợp với identity và trạng thái quản lý, và tránh tính toàn bộ graph trong các phương thức này.

## 11. Ownership không đồng nghĩa cascade và orphan removal

### 11.1. Cascade là truyền thao tác lifecycle

Ví dụ:

```java
@OneToMany(mappedBy = "order", cascade = CascadeType.PERSIST)
private List<OrderLine> lines;
```

Dù đây là **inverse side**, cấu hình cascade vẫn có hiệu lực theo ý nghĩa của nó: persist `PurchaseOrder` có thể cascade persist đến các `OrderLine` trong collection.

Nhưng JPA vẫn lấy `OrderLine.order` ở **owning side** để biết FK nên trỏ tới đơn hàng nào.

Tách bạch:

- **Owner** trả lời “Thành viên nào quản lý liên kết?”
- **Cascade** trả lời “Thao tác persistence nào được truyền sang entity liên quan?”
- **Orphan removal** trả lời “Entity con có bị xóa khi bị loại khỏi quan hệ sở hữu vòng đời không?”

Một thuộc tính inverse có thể khai báo cascade, và một thuộc tính owner có thể không khai báo cascade. Không nên dựa vào cascade để suy ra ownership.

### 11.2. Orphan removal không tự xuất hiện vì có `mappedBy`

```java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
```

Ở đây **không** có orphan removal mặc định. Xóa một dòng hàng khỏi list phía inverse một mình không đồng nghĩa JPA sẽ xóa row con.

Nếu cấu hình:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
```

Khi một dòng hàng được loại khỏi quan hệ theo đúng quy tắc entity và persistence context, orphan removal có thể xóa dòng hàng khỏi database. Chức năng này thích hợp khi con thuộc vòng đời của cha và không được tái sử dụng độc lập. Nó không phải lựa chọn mặc định cho mọi quan hệ.

**Không chuyển con vốn được xem là orphan sang một cha khác rồi mặc định orphan removal sẽ tự giải quyết đúng.** Đặc tả có những giới hạn và thời điểm xử lý orphan; với nghiệp vụ chuyển chủ sở hữu, cần lựa chọn mapping/vòng đời phù hợp.

### 11.3. `CascadeType.REMOVE` với `@ManyToMany`

Hai sinh viên có thể cùng tham gia một khóa học. Xóa sinh viên khỏi khóa học **không nên xóa entity `Course`** vì các sinh viên khác có thể còn học.

Vì vậy, không nên tùy ý đặt `CascadeType.REMOVE` hoặc `CascadeType.ALL` lên `@ManyToMany` giữa các entity độc lập. Thường chỉ cần xóa dòng ở join table khi hủy liên kết.

`orphanRemoval` thuộc các kiểu quan hệ được JPA hỗ trợ như `@OneToOne` và `@OneToMany`, **không phải thuộc tính của `@ManyToMany`**.

## 12. Ownership không quyết định fetch và transaction

### 12.1. Fetch là chuyện khác

```java
@ManyToOne(fetch = FetchType.LAZY)
private PurchaseOrder order;
```

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
```

Hai annotation đang cấu hình chiến lược lấy dữ liệu, **không** thay đổi phía owner/inverse.

Trong JPA, fetch mặc định của `@ManyToOne` và `@OneToOne` là `EAGER`, còn `@OneToMany` và `@ManyToMany` mặc định `LAZY`. Tuy nhiên cách lazy thực tế, nhất là một-một phía inverse, có thể phụ thuộc provider, proxy và bytecode enhancement.

Lỗi lazy initialization khi truy cập collection ngoài persistence context không có nghĩa `mappedBy` sai. Đó là vấn đề lifecycle/fetch. Ngược lại, một collection đã được tải đầy đủ vẫn có thể bị sai trong bộ nhớ nếu ứng dụng không đồng bộ hai phía.

### 12.2. Dirty checking và thời điểm SQL

Giả sử `OrderLine` đang managed:

```java
OrderLine line = entityManager.find(OrderLine.class, 101L);
PurchaseOrder other =
    entityManager.find(PurchaseOrder.class, 11L);

// Việc chuyển đơn đòi hỏi helper phù hợp với invariant:
line.attachTo(other);
```

Nếu association `order` được ánh xạ là owner và dữ liệu hợp lệ, JPA có thể phát hiện thay đổi và đồng bộ câu SQL tương tự:

```sql
UPDATE order_line
SET order_id = 11
WHERE id = 101;
```

SQL chính xác có thể khác do provider, optimistic locking, batching, cascade hoặc schema. Khi entity managed bị thay đổi, `flush` có thể gửi SQL trong transaction; **commit** mới xác nhận transaction. Rollback có thể hủy thay đổi của cơ sở dữ liệu.

Chỉ nhìn thấy list đã đổi trong Java không chứng minh SQL đã được phát hay đã commit.

### 12.3. Detached entity và `merge`

Nếu entity đã detached, thay đổi quan hệ bên trong đối tượng detached không được tự động đồng bộ. `merge` có thể sao chép trạng thái sang một managed instance, với hành vi phụ thuộc mapping, cascade và trạng thái graph.

Không nên gọi `merge` rồi bỏ qua giá trị trả về, bởi instance trả về mới là managed instance. Việc đồng bộ hai chiều ở graph detached vẫn quan trọng, nhưng chưa đủ nếu code đang sửa một đối tượng không tham gia persistence context.

### 12.4. Bulk JPQL/SQL có thể làm graph cũ

Nếu có lệnh bulk update:

```java
entityManager.createQuery(
    "update OrderLine l set l.order = :order where l.id = :id"
)
.setParameter("order", other)
.setParameter("id", 101L)
.executeUpdate();
```

Bulk update theo JPQL không đồng bộ tự động toàn bộ state đã nạp trong persistence context như việc sửa managed instance. Những `OrderLine`/collection cũ có thể stale. Cần xác định chiến lược `refresh`, `clear` hoặc tạo persistence context mới phù hợp; không nhầm đây là lỗi của `mappedBy`.

## 13. Mapping với access qua field hay property

`mappedBy` trỏ tới **tên thuộc tính persistent được JPA ánh xạ** ở phía sở hữu.

Với field access:

```java
@Entity
public class Comment {
    @Id
    private Long id;

    @ManyToOne
    @JoinColumn(name = "post_id")
    private BlogPost blogPost; // Tên attribute = "blogPost".
}
```

```java
@OneToMany(mappedBy = "blogPost")
private List<Comment> comments;
```

Với property access, mapping đặt trên getter:

```java
@Entity
@Access(AccessType.PROPERTY)
public class Comment {
    private Long id;
    private BlogPost blogPost;

    @Id
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    @ManyToOne
    @JoinColumn(name = "post_id")
    public BlogPost getBlogPost() {
        return blogPost;
    }

    public void setBlogPost(BlogPost blogPost) {
        this.blogPost = blogPost;
    }
}
```

Phía inverse vẫn dùng `mappedBy = "blogPost"`. Tên JavaBeans property xuất phát từ `getBlogPost()`, không phải tên cột `post_id`.

**Tránh trộn annotation** giữa field và getter khi không khai báo `@Access` đúng cách. Nếu JPA không nhận ra owning attribute, thông báo kiểu “mappedBy references an unknown target entity property” hoặc lỗi mapping tương tự có thể xuất hiện khi khởi tạo persistence unit.

## 14. Các lỗi mapping điển hình

### 14.1. Dùng tên cột SQL trong `mappedBy`

```java
@OneToMany(mappedBy = "customer_id")
private List<Invoice> invoices;
```

Nếu entity `Invoice` có field `customer` và `@JoinColumn(name = "customer_id")`, phải sửa thành:

```java
@OneToMany(mappedBy = "customer")
private List<Invoice> invoices;
```

### 14.2. Hai phía cùng tưởng mình là owner

Ví dụ:

```java
// Department
@OneToMany
@JoinColumn(name = "department_id")
private List<Employee> employees;

// Employee
@ManyToOne
@JoinColumn(name = "department_id")
private Department department;
```

Nếu cả hai phía được khai báo như những mapping sở hữu độc lập cùng cột `department_id`, provider có thể tạo SQL không mong muốn, đụng cấu hình cột hoặc coi hai quan hệ không đồng bộ với nhau.

Trong mô hình hai chiều truyền thống:

```java
// Department: inverse
@OneToMany(mappedBy = "department")
private List<Employee> employees;

// Employee: owner
@ManyToOne
@JoinColumn(name = "department_id")
private Department department;
```

### 14.3. Tưởng `mappedBy` tên entity cha

```java
@OneToMany(mappedBy = "Department")
private List<Employee> employees;
```

`Department` là class/entity type, không phải tên field `department` của `Employee`. Phải dùng tên attribute chính xác.

### 14.4. Chỉ thêm vào inverse collection

```java
department.getEmployees().add(employee);
```

Nếu `employee.department` chưa được gán, relationship owner vẫn không phản ánh thay đổi. Gọi helper đồng bộ cả hai phía, chẳng hạn `department.addEmployee(employee)`.

### 14.5. Chỉ gọi `setDepartment` trên con

```java
employee.setDepartment(department);
```

Nếu collection đã được tải, `department.getEmployees()` có thể chưa xuất hiện employee cho đến khi graph được đồng bộ/tải lại. DB có thể đúng theo owning side, nhưng bộ nhớ tạm thời sai. Cần helper cập nhật hai phía.

### 14.6. Đặt `mappedBy` lên `@ManyToOne`

`@ManyToOne` không có thuộc tính `mappedBy`; code sẽ không compile nếu cố truyền tham số không tồn tại. Phải dùng `@JoinColumn` hoặc cấu hình association hợp lệ trên `@ManyToOne`; `mappedBy` thuộc bên `@OneToMany`.

### 14.7. Nhầm cascade với ownership

```java
@OneToMany(mappedBy = "order", cascade = CascadeType.ALL)
private List<OrderLine> lines;
```

Cascade không biến `PurchaseOrder.lines` thành owning side. `OrderLine.order` vẫn quản lý FK.

### 14.8. Nhầm inverse với thuộc tính không thể query

`mappedBy` không cản JPQL join từ bên inverse:

```java
select o
from PurchaseOrder o
join o.lines line
where line.sku = :sku
```

Đây là một path hợp lệ trên object model nếu mapping đúng. Vai trò “inverse” chỉ liên quan tới sở hữu **liên kết khi ghi**, không hạn chế đường truy vấn.

### 14.9. Sửa tên field owner nhưng không cập nhật `mappedBy`

Khi refactor `OrderLine.order` thành `OrderLine.purchaseOrder`, chuỗi `mappedBy = "order"` không được Java compiler tự sửa trong mọi công cụ. Cần cập nhật sang `mappedBy = "purchaseOrder"`.

### 14.10. Chỉ dựa vào default join table rồi kết luận sai FK

Một `@OneToMany` một chiều không có `mappedBy` có thể dùng join table mặc định. Nếu muốn quan hệ hai chiều trên FK `order_line.order_id`, phải khai báo cặp `@OneToMany(mappedBy = "order")` và `@ManyToOne @JoinColumn(...)` nhất quán.

### 14.11. Xóa quan hệ rồi quên ràng buộc NOT NULL

Nếu `@JoinColumn(nullable = false)` và cột FK `NOT NULL`, gán `child.parent = null` không tạo ra trạng thái có thể commit, trừ khi xử lý orphan removal/xóa entity hoặc chuyển parent phù hợp. Quy tắc nullability là vấn đề riêng với `mappedBy`.

### 14.12. Dùng `@ManyToMany(cascade = ALL)` cho hai entity độc lập

Xóa một `Student` không nên cascade xóa `Course` đang được các sinh viên khác tham chiếu. Hãy quản lý **dòng join table** và lifecycle của hai entity theo nghiệp vụ; tránh cascade remove không phù hợp.

### 14.13. Dùng quan hệ hai chiều chỉ để phục vụ JSON

Thêm một `@OneToMany` inverse chỉ để serializer có thể đi từ parent tới children có thể tạo vòng tham chiếu, tải nhiều dữ liệu và lỗi lazy loading. Thiết kế DTO/API có chủ đích; không dùng mapping ownership để giải quyết vấn đề presentation.

## 15. Cách phân tích một quan hệ trong dự án thực tế

Khi đọc một cặp entity lạ, hãy lần lượt kiểm tra:

1. **Số hướng Java:** chỉ một entity giữ reference/collection hay cả hai entity giữ?
2. **Loại mapping:** `@ManyToOne`, `@OneToMany`, `@OneToOne` hay `@ManyToMany`?
3. **Vị trí FK/join table:** cột FK nằm bảng nào, có bảng nối không, có unique constraint không?
4. **Owning attribute:** field/getter nào khai báo `@JoinColumn`/`@JoinTable` hoặc nắm association theo quy tắc loại quan hệ?
5. **Inverse attribute:** `mappedBy` có trỏ đúng **tên Java** của owning attribute không?
6. **Hành vi cập nhật:** helper method có đồng bộ cả hai phía khi thêm, xóa và thay đổi liên kết không?
7. **Vòng đời con:** cascade, orphan removal và ràng buộc `NOT NULL` có đúng với nghiệp vụ không?
8. **Đọc dữ liệu:** fetch mode, truy vấn, transaction và serialization có phù hợp không?
9. **Schema migration:** tên FK/unique/join table thực tế có khớp với mapping không?

Đặc biệt, hãy xem **`@JoinColumn` nằm ở đâu** khi có `@ManyToOne` hoặc `@OneToOne`, và xem **`@JoinTable` nằm ở đâu** khi có `@ManyToMany`. Sau đó tìm `mappedBy` tại phía đối diện. Đây là cách đọc mapping dễ hiểu hơn so với việc đoán từ tên lớp “cha” hay “con”.

## 16. Tình huống và bài tập

### Bài tập 1: Tìm owning side

```java
class Author {
    @OneToMany(mappedBy = "author")
    List<Book> books;
}

class Book {
    @ManyToOne
    @JoinColumn(name = "author_id")
    Author author;
}
```

**Câu hỏi:** Phía nào ghi khóa ngoại `author_id`? `mappedBy` tham chiếu tới gì?

**Trả lời:** `Book.author` là owning side và ánh xạ FK `author_id`. `Author.books` là inverse side; `mappedBy = "author"` tham chiếu tới tên thuộc tính `author` trên entity `Book`.

### Bài tập 2: Chỉ sửa phía inverse

```java
Author author = entityManager.find(Author.class, 5L);
Book book = new Book();

author.getBooks().add(book);
// Chưa gán book.author.
```

**Câu hỏi:** Đây có phải cách đầy đủ để lưu quan hệ không?

**Trả lời:** Chưa. Phía owning `book.author` chưa được cập nhật. Cần helper gán `book.author = author`, đồng thời thêm book vào `author.books`. Nếu dùng cascade persist, nó vẫn không thay thế việc chỉ định owner.

### Bài tập 3: Dùng đúng `mappedBy` với tên cột khác

```java
// Employee
@ManyToOne
@JoinColumn(name = "manager_id")
private Manager directManager;
```

**Câu hỏi:** Bên `Manager` nên đặt `mappedBy` bằng chuỗi nào?

**Trả lời:** `"directManager"`, vì đó là tên Java attribute ở owner. Không dùng `"manager_id"`.

### Bài tập 4: Một-một có FK trong bảng nào?

Một hệ thống lưu `user_profile.user_id` là FK trỏ tới `app_user.id`.

**Câu hỏi:** Nếu mô hình hai chiều theo FK này, nơi nào đặt `@JoinColumn` và nơi nào đặt `mappedBy`?

**Trả lời:** `UserProfile.user` đặt `@OneToOne @JoinColumn(name = "user_id")` để sở hữu FK. `AppUser.profile` đặt `@OneToOne(mappedBy = "user")` để khai báo inverse. Cần ràng buộc unique cho `user_id` nếu muốn quan hệ đúng nghĩa một-một.

### Bài tập 5: Nhiều-nhiều

```java
class Reader {
    @ManyToMany
    @JoinTable(name = "reader_book")
    Set<Book> books;
}

class Book {
    @ManyToMany(mappedBy = "books")
    Set<Reader> readers;
}
```

**Câu hỏi:** Thêm reader vào `book.readers` có chắc tạo dòng `reader_book` không?

**Trả lời:** Không nên dựa vào điều đó. Phía owner là `Reader.books`; cần thêm book vào collection đó, đồng thời đồng bộ `Book.readers` trong bộ nhớ.

### Bài tập 6: Xác định sai lầm về cascade

Một developer nói: “`Order` có `cascade = ALL` trên `@OneToMany(mappedBy = "order")`, vậy `Order` là owner của relationship.”

**Trả lời:** Không. Cascade và ownership là hai cơ chế độc lập. `OrderLine.order` là owner của FK; `Order.lines` vẫn là inverse dù có cascade.

### Bài tập 7: Bảng nối có metadata riêng

Bảng `student_course` thêm hai cột `enrolled_at` và `grade`.

**Câu hỏi:** Nên giữ `@ManyToMany` hay tạo entity `Enrollment`?

**Trả lời:** Có thể tạo `Enrollment` khi bản ghi liên kết có thuộc tính và lifecycle riêng. `Enrollment.student` và `Enrollment.course` là các `@ManyToOne` owner; các collection phía `Student`/`Course`, nếu có, dùng `mappedBy` tương ứng.

### Bài tập 8: Đọc SQL và suy ra object mapping

```sql
CREATE TABLE department (
    id BIGINT PRIMARY KEY
);

CREATE TABLE employee (
    id BIGINT PRIMARY KEY,
    department_id BIGINT NOT NULL,
    FOREIGN KEY (department_id) REFERENCES department(id)
);
```

**Yêu cầu:** Đề xuất mapping hai chiều phù hợp.

**Trả lời mẫu:**

```java
// Employee
@ManyToOne(optional = false)
@JoinColumn(name = "department_id", nullable = false)
private Department department;

// Department
@OneToMany(mappedBy = "department")
private List<Employee> employees = new ArrayList<>();
```

`Employee.department` sở hữu quan hệ; `Department.employees` là inverse. Helper method cần đồng bộ hai phía, và việc remove employee phải tôn trọng FK NOT NULL.

## 17. Ghi nhớ trọng tâm

- **Owning side** là phía JPA dùng để quản lý việc ghi liên kết vào FK hoặc join table; nó không nhất thiết là “cha” nghiệp vụ.
- **`mappedBy` chỉ tên thuộc tính Java ở phía owner**, không chỉ cột SQL, tên bảng hoặc tên entity.
- Với **`@OneToMany`/`@ManyToOne` hai chiều**, `@ManyToOne` là owning side; `@OneToMany(mappedBy = "...")` là inverse.
- Với **`@OneToOne`**, phía ánh xạ FK là owner; phía đối diện dùng `mappedBy` nếu có điều hướng hai chiều.
- Với **`@ManyToMany`**, một phía quản lý join table; phía còn lại dùng `mappedBy` trỏ tới owning collection.
- **Một chiều không cần `mappedBy`** vì không có thuộc tính inverse; đặc biệt `@OneToMany` một chiều có thể dùng join table theo mặc định.
- Khi cập nhật quan hệ **hai chiều**, hãy sửa **cả owning side lẫn inverse side** bằng helper method để FK đúng và object graph nhất quán.
- **Cascade, orphan removal, fetch và transaction là những cơ chế khác ownership.** Chúng vẫn phải được thiết kế phù hợp với vòng đời và invariant của từng entity.

Khi thấy một mapping JPA như `@OneToMany(mappedBy = "order")`, hãy tìm tới entity phần tử và xem **`order` được khai báo như thế nào**. Việc lần theo đường này từ thuộc tính Java tới `@JoinColumn` hoặc `@JoinTable` giúp xác định chính xác phía sở hữu và dự đoán JPA sẽ cập nhật liên kết nào trong cơ sở dữ liệu.
