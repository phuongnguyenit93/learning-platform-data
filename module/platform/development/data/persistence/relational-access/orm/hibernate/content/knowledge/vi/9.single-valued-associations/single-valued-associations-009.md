# Phân biệt phía quản lý liên kết với chủ sở hữu vòng đời nghiệp vụ

Trong Hibernate/JPA, một quan hệ giữa hai entity thường được mô tả bằng `@ManyToOne`, `@OneToOne` và đôi khi là phía đối ứng `@OneToMany` hoặc `@OneToOne(mappedBy = "...")`. Khi đọc tài liệu, bạn sẽ gặp cụm từ **owning side** (phía sở hữu/quản lý liên kết). Trong thiết kế domain, bạn cũng gặp cụm từ **aggregate root** hoặc **đối tượng chịu trách nhiệm vòng đời**. Hai khái niệm này đều nói về “sở hữu”, nhưng chúng giải quyết **hai câu hỏi hoàn toàn khác nhau**:

- **Phía quản lý liên kết trong JPA**: Khi quan hệ thay đổi, Hibernate dựa vào phía nào để cập nhật khóa ngoại hoặc bản ghi liên kết trong database?
- **Chủ sở hữu vòng đời nghiệp vụ**: Đối tượng hoặc aggregate nào quyết định khi nào một đối tượng được tạo, thay đổi, chuyển giao hoặc xóa theo các quy tắc của hệ thống?

Một entity có thể là **phía quản lý khóa ngoại** mà **không có quyền quyết định vòng đời** của entity nó tham chiếu. Ngược lại, một aggregate root có thể quản lý toàn bộ vòng đời của các entity con dù bản thân nó là **phía đối ứng** (`mappedBy`) trong quan hệ JPA.

Bài học tập trung vào các quan hệ đơn trị như `@ManyToOne` và `@OneToOne`, đồng thời sử dụng ví dụ hai chiều để làm rõ việc hai khái niệm trên tách biệt ra sao.

## 1. Ba loại “sở hữu” dễ bị trộn lẫn

| Khái niệm | Câu hỏi cần trả lời | Quyết định bằng | Ví dụ |
| --- | --- | --- | --- |
| **Owning side của JPA** | Ai định nghĩa phần ánh xạ quan hệ để Hibernate ghi thay đổi liên kết? | `@JoinColumn`, `mappedBy`, `@JoinTable` và loại quan hệ | `OrderLine.order` giữ ánh xạ cột `order_id` |
| **Chủ sở hữu vòng đời nghiệp vụ** | Ai được phép tạo, sửa, hủy đối tượng và bảo vệ bất biến nghiệp vụ? | Quy tắc domain, aggregate boundary, application service | `Order` quyết định thêm/xóa `OrderLine` |
| **Chủ sở hữu khóa ngoại ở database** | Bảng nào thực sự chứa FK, unique constraint hoặc join table? | Thiết kế SQL schema | Bảng `order_lines` chứa `order_id` tham chiếu `orders.id` |

Trong một quan hệ `@ManyToOne` hai chiều thông thường, owning side JPA nằm ở entity có thuộc tính `@ManyToOne`. Nhưng aggregate root lại có thể nằm ở phía `@OneToMany(mappedBy = ...)`. Sự lệch nhau này **không phải lỗi thiết kế**.

Cũng cần phân biệt “chủ sở hữu vòng đời” với “người dùng có quyền truy cập” hoặc “service nào gọi repository”. Một nghiệp vụ có thể kiểm tra quyền của người dùng và điều phối nhiều aggregate, nhưng quy tắc **entity con chỉ được tạo/xóa thông qua aggregate root** vẫn là một quyết định domain độc lập với các API của Hibernate.

## 2. Owning side của quan hệ JPA là gì?

Với một quan hệ **hai chiều**, hai entity có thể giữ tham chiếu Java đến nhau. JPA cần một phía làm cơ sở ánh xạ để tránh hiểu hai thuộc tính là hai liên kết độc lập.

Ví dụ một đơn hàng có nhiều dòng hàng:

~~~java
@Entity
public class Order {

    @Id
    private Long id;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

~~~java
@Entity
public class OrderLine {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private Order order;
}
~~~

Trong mapping này:

- `OrderLine.order` là **owning side** của quan hệ: ở đó Hibernate biết FK `order_id` được ánh xạ.
- `Order.lines` là **inverse side** hay phía đối ứng: `mappedBy = "order"` nghĩa là tham chiếu tới **tên thuộc tính Java** `order` trong `OrderLine`, không phải tên cột `order_id`.
- Hai field mô tả **cùng một liên kết**, nhìn từ hai hướng Java khác nhau.

~~~mermaid
flowchart LR
    O["Order<br/>lines @OneToMany(mappedBy='order')<br/>phía đối ứng JPA"] <-->|"tham chiếu Java hai chiều"| L["OrderLine<br/>order @ManyToOne<br/>phía quản lý liên kết JPA"]
    L -->|"FK order_id"| D[("order_lines.order_id<br/>→ orders.id")]
~~~

SQL schema có thể là:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY
);

CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES orders(id)
);
~~~

Không có cột tên `lines` trong bảng `orders` chỉ vì entity `Order` có collection `lines`. Với mapping này, liên kết được thể hiện bằng FK trong bảng `order_lines`.

### 2.1. Thay đổi phía đối ứng một mình chưa đủ

Giả sử:

~~~java
Order order = em.find(Order.class, orderId);
OrderLine line = em.find(OrderLine.class, lineId);

// Chỉ sửa collection inverse.
order.getLines().add(line);
~~~

Thao tác này thay đổi một collection trong bộ nhớ, nhưng **chưa chỉ định thay đổi FK thông qua owning side** là `line.order`. Không nên dựa vào đoạn code trên để khiến `order_lines.order_id` được cập nhật như mong muốn.

Ngược lại:

~~~java
line.setOrder(order);
~~~

là thao tác lên phía owning side. Nếu `line` đang managed và thay đổi hợp lệ, Hibernate có cơ sở để cập nhật liên kết khi flush. Tuy nhiên, collection `order.lines` trong cùng object graph vẫn có thể **không phản ánh ngay** liên kết mới nếu bạn không tự đồng bộ nó.

Do vậy, khi quan hệ hai chiều, quy tắc thực dụng là **đồng bộ cả hai phía trong bộ nhớ**, còn Hibernate dùng owning side làm căn cứ ghi liên kết.

### 2.2. Owning side không nói ai “làm chủ” đối tượng được tham chiếu

`OrderLine.order` sở hữu FK; điều đó không có nghĩa một `OrderLine` được quyền xóa `Order` hoặc quyết định trạng thái thanh toán của đơn hàng.

Tương tự, nếu `Invoice.customer` là `@ManyToOne`, `Invoice` giữ FK `customer_id`; điều này hoàn toàn không có nghĩa một hóa đơn được quyền xóa khách hàng khi hóa đơn bị xóa.

Owning side là thuật ngữ về **persistence mapping**, không phải bằng chứng về **quyền sở hữu nghiệp vụ**.

## 3. Chủ sở hữu vòng đời trong domain là gì?

Trong thiết kế domain, một đối tượng có thể chịu trách nhiệm bảo vệ những quy tắc như:

- Đơn hàng không được thêm dòng hàng sau khi đã thanh toán.
- Số lượng của mỗi dòng hàng phải lớn hơn 0.
- Dòng hàng thuộc về đúng một đơn; không được tự ý chuyển sang đơn khác.
- Xóa đơn hàng đồng nghĩa với xóa các dòng hàng cấu thành đơn.
- Khách hàng vẫn tồn tại dù một hóa đơn tham chiếu đến họ bị xóa.

Nếu chọn `Order` làm **aggregate root**, ứng dụng thường thao tác theo hướng:

~~~java
order.addLine(productId, quantity, unitPrice);
order.removeLine(lineId);
order.confirm();
~~~

Các phương thức này kiểm tra trạng thái và bất biến nghiệp vụ. Code bên ngoài hạn chế tự ý tạo `OrderLine` với FK khác hoặc xóa `OrderLine` không qua `Order`.

Điều đó vẫn đúng dù `Order` có annotation `mappedBy`, còn `OrderLine` chứa FK.

### 3.1. Aggregate root quyết định hành vi, không phải tên annotation

Không có annotation chuẩn JPA nào tuyên bố “đây là aggregate root” và tự động thực thi toàn bộ bất biến domain. Việc đặt aggregate boundary là quyết định thiết kế dựa trên nghiệp vụ và transaction consistency.

JPA `@Entity` chỉ nói một class có identity và trạng thái persistent. `@ManyToOne`, `@OneToOne`, `@OneToMany` nói về quan hệ ánh xạ. Chúng không áp đặt rằng entity nào là root nghiệp vụ.

### 3.2. Phân biệt “chứa” và “tham chiếu”

Quan hệ một chiều hoặc nhiều chiều trong Java không nhất thiết biểu thị sự phụ thuộc vòng đời:

- `Order` **chứa** `OrderLine` như một phần của đơn hàng: thường là lifecycle dependency.
- `Invoice` **tham chiếu** `Customer`: cả hai có thể là aggregate root độc lập.
- `Employee` tham chiếu `Department`: xóa một nhân viên không xóa phòng ban.
- `Account` có một `AccountSettings` phụ thuộc: settings có thể được tạo/hủy theo account, tùy quy tắc.

Để quyết định chủ sở hữu vòng đời, hãy hỏi: “Nếu thực thể A biến mất, thực thể B có còn ý nghĩa và identity độc lập không?” Câu trả lời phụ thuộc domain, không phụ thuộc vị trí cột FK.

## 4. Ví dụ đầy đủ: Order sở hữu vòng đời, OrderLine sở hữu FK

Đây là tình huống điển hình nhất cho việc hai khái niệm “owner” **nằm ở hai phía khác nhau**.

### 4.1. Entity Order: aggregate root, phía đối ứng JPA

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Entity
@Table(name = "orders")
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status = OrderStatus.DRAFT;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected Order() {}

    public Long getId() {
        return id;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(Long productId, int quantity,
                        BigDecimal unitPrice) {
        requireDraft();

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Số lượng phải lớn hơn 0");
        }
        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Đơn giá không hợp lệ");
        }

        OrderLine line = new OrderLine(productId, quantity, unitPrice);
        lines.add(line);
        line.attachTo(this); // Cập nhật phía owning side JPA.
    }

    public void removeLine(Long lineId) {
        requireDraft();

        OrderLine target = lines.stream()
            .filter(item -> item.getId() != null
                && item.getId().equals(lineId))
            .findFirst()
            .orElseThrow(() ->
                new IllegalArgumentException("Không tìm thấy dòng hàng"));

        lines.remove(target); // orphanRemoval xử lý xóa entity con.
        target.attachTo(null); // Giữ hai phía nhất quán trong RAM.
    }

    public void confirm() {
        requireDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException("Đơn hàng rỗng");
        }
        status = OrderStatus.CONFIRMED;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Chỉ sửa dòng hàng khi đơn ở trạng thái DRAFT");
        }
    }
}
~~~

`OrderStatus` là enum nghiệp vụ với các giá trị `DRAFT` và `CONFIRMED`. Đoạn mã chủ đích đặt các phương thức sửa dòng hàng trên `Order` để root kiểm soát quy tắc; đây là ví dụ thiết kế, chưa bao gồm toàn bộ ràng buộc giá, thuế và kiểm kê của một hệ thống thương mại.

### 4.2. Entity OrderLine: owning side JPA nhưng không tự quyết định vòng đời

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private Order order;

    @Column(name = "product_id", nullable = false)
    private Long productId;

    @Column(nullable = false)
    private int quantity;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal unitPrice;

    protected OrderLine() {}

    OrderLine(Long productId, int quantity, BigDecimal unitPrice) {
        this.productId = productId;
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public Long getId() {
        return id;
    }

    public Long getProductId() {
        return productId;
    }

    public int getQuantity() {
        return quantity;
    }

    void attachTo(Order owner) {
        this.order = owner;
    }
}
~~~

Ở đây:

- `@ManyToOne` và `@JoinColumn(name = "order_id")` xác định **owning side JPA**.
- `Order.addLine()`, `Order.removeLine()` và `Order.confirm()` quyết định **vòng đời/hành vi nghiệp vụ**.
- `attachTo()` chỉ có mức truy cập package-private, giúp giảm việc code ngoài aggregate tự sửa FK qua setter công khai.
- `cascade = CascadeType.ALL` và `orphanRemoval = true` trên collection giúp phản ánh vòng đời phụ thuộc của dòng hàng, **không biến collection `Order.lines` thành owning side của FK**.
- `optional = false` và `nullable = false` diễn đạt mong muốn mỗi dòng hàng phải có đơn, nhưng vẫn cần migration/constraint thật trong database để bảo vệ dữ liệu ngoài ORM.

### 4.3. Luồng tạo đơn và dòng hàng

Ví dụ khi transaction do service quản lý:

~~~java
@Transactional
public Long createDraftOrder() {
    Order order = new Order();
    order.addLine(10L, 2, new BigDecimal("120000.00"));
    order.addLine(20L, 1, new BigDecimal("90000.00"));

    entityManager.persist(order);
    return order.getId();
}
~~~

Nhờ `cascade = ALL` từ `Order.lines`, Hibernate có thể persist các dòng hàng mới khi persist root. Tại thời điểm ghi, `OrderLine.order` đã trỏ tới `Order`, nên Hibernate có thông tin để thiết lập `order_id`.

Việc khai báo cascade ở phía `mappedBy` là **hợp lệ**: cascade điều khiển lan truyền thao tác quản lý entity, còn owning side điều khiển giá trị liên kết cần ghi. Chúng là hai cơ chế khác nhau.

### 4.4. Luồng xóa một dòng hàng

Khi `Order` đã được load trong một transaction:

~~~java
Order order = entityManager.find(Order.class, orderId);
order.removeLine(lineId);
~~~

Với `orphanRemoval = true`, dòng hàng đã tồn tại và bị bỏ khỏi collection phụ thuộc sẽ được Hibernate xóa theo semantics orphan removal khi đồng bộ trạng thái. Không cần gọi `entityManager.remove(line)` bằng tay cho use case này.

Một số điểm cần nhớ:

- Khi đã quyết định dòng hàng phụ thuộc vòng đời vào đơn, **không tùy tiện chuyển cùng `OrderLine` sang `Order` khác**. Orphan removal phù hợp với ngữ nghĩa hủy con khi bị bỏ khỏi cha; nếu nghiệp vụ cho phép chuyển con giữa cha thì nên xem lại lựa chọn này.
- `attachTo(null)` đồng bộ object graph trong bộ nhớ; thao tác xóa nhờ orphan removal, không phải một ý định giữ dòng hàng tồn tại với FK null.
- Hibernate có thể lên lịch SQL DELETE vào lúc flush. Thứ tự SQL thực tế phụ thuộc engine và trạng thái entity.
- Nếu dòng hàng được tham chiếu bởi bảng khác, FK và quy tắc vòng đời cần được thiết kế phù hợp; orphan removal không giải quyết thay cho domain.

## 5. Vì sao cascade không quyết định owning side?

`CascadeType` quy định thao tác lifecycle JPA nào được lan truyền qua một association. Ví dụ:

| Cascade | Ý nghĩa cơ bản |
| --- | --- |
| `PERSIST` | Khi persist entity nguồn, có thể persist entity đích theo liên kết |
| `MERGE` | Lan truyền thao tác merge sang entity đích |
| `REMOVE` | Lan truyền thao tác remove sang entity đích |
| `REFRESH` | Lan truyền refresh |
| `DETACH` | Lan truyền detach |
| `ALL` | Gồm các kiểu cascade trên |

Một collection phía đối ứng có thể khai báo:

~~~java
@OneToMany(mappedBy = "order", cascade = CascadeType.ALL)
private List<OrderLine> lines;
~~~

Hibernate vẫn xem `OrderLine.order` là owning side của FK. Cascade không đổi vai trò đó.

### 5.1. Không cascade REMOVE từ con tới root độc lập

Cấu hình sau thường rất nguy hiểm:

~~~java
@ManyToOne(cascade = CascadeType.REMOVE)
private Customer customer;
~~~

Nếu xóa một hóa đơn hoặc đơn hàng đang tham chiếu `Customer`, cascade remove có thể lan sang khách hàng, trong khi khách hàng còn được nhiều giao dịch khác sử dụng. Đây gần như không bao giờ là vòng đời mong muốn của quan hệ “tham chiếu tới aggregate khác”.

Tương tự, `CascadeType.ALL` trên `@ManyToOne` có thể vô tình lan truyền những thao tác không phù hợp. Chỉ khai báo cascade theo ngữ nghĩa lifecycle thật sự, không vì muốn tiết kiệm vài lệnh repository.

### 5.2. Cascade và orphanRemoval khác nhau

Hai annotation dễ bị đồng nhất:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
~~~

- `CascadeType.REMOVE`: khi **xóa parent**, thao tác remove có thể lan xuống các child liên quan.
- `orphanRemoval = true`: khi **child bị tách khỏi quan hệ sở hữu** trong tập con hoặc quan hệ một-một phù hợp, child có thể bị xóa ngay cả khi parent vẫn tồn tại.

Không phải mọi collection đều nên dùng orphan removal. Nếu entity con có identity, vòng đời độc lập hoặc được chia sẻ, việc rút nó ra khỏi collection không nên mặc định đồng nghĩa xóa khỏi database.

## 6. @ManyToOne: chủ FK thường là entity tham chiếu, chủ nghiệp vụ có thể khác

Trong JPA, `@ManyToOne` là quan hệ đơn trị từ entity hiện tại đến một entity đích. Thuộc tính `@ManyToOne` thường giữ ánh xạ FK; nó là owning side của liên kết này.

Nhưng quan hệ ManyToOne có ít nhất hai nhóm nghiệp vụ:

| Quan hệ | Owning side JPA | Ai quyết định vòng đời của entity đích? |
| --- | --- | --- |
| `OrderLine.order` | `OrderLine` | `Order` là root quản lý dòng hàng, nhưng dòng hàng không quản lý vòng đời đơn |
| `Invoice.customer` | `Invoice` | `Customer` thường độc lập, không bị hóa đơn tạo/xóa |
| `Employee.department` | `Employee` | `Department` thường độc lập |
| `Ticket.assignee` | `Ticket` | `User` được quản lý bởi hệ thống người dùng, không phụ thuộc ticket |
| `Address.country` | `Address` | `Country`/danh mục quốc gia là dữ liệu được tham chiếu độc lập |

Khi nhìn vào `@ManyToOne`, chỉ có thể kết luận về **hướng tham chiếu và mapping**; chưa đủ để kết luận nên cascade remove, ai được cập nhật hay thực thể nào là aggregate root.

### 6.1. Trường hợp tham chiếu một aggregate độc lập

Giả sử:

~~~java
@Entity
public class Invoice {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;
}
~~~

Trong mô hình này, `Invoice` giữ FK `customer_id`. Nhưng `Customer` vẫn tồn tại khi một hóa đơn bị xóa. Thông thường **không khai báo `CascadeType.REMOVE` từ Invoice sang Customer**; service chỉ lấy tham chiếu khách hàng đã tồn tại, đồng thời kiểm tra quy tắc nghiệp vụ.

Nếu hai aggregate phải đồng bộ theo một quy trình, application service có thể điều phối; việc điều phối không biến khóa ngoại của Invoice thành quyền kiểm soát vòng đời Customer.

## 7. @OneToOne: phía giữ FK chưa chắc là chủ vòng đời

Với quan hệ một-một, một phía thường chứa FK có ràng buộc UNIQUE, trong khi phía còn lại có thể khai báo `mappedBy`.

Ví dụ một tài khoản có đúng một bộ cài đặt phụ thuộc vào tài khoản.

### 7.1. Account là root nghiệp vụ; AccountSettings giữ FK

~~~java
@Entity
@Table(name = "accounts")
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(
        mappedBy = "account",
        cascade = CascadeType.ALL,
        orphanRemoval = true,
        fetch = FetchType.LAZY
    )
    private AccountSettings settings;

    protected Account() {}

    public void initializeSettings(String locale) {
        if (settings != null) {
            throw new IllegalStateException("Cài đặt đã tồn tại");
        }

        AccountSettings next = new AccountSettings(locale);
        next.attachTo(this);
        this.settings = next;
    }

    public void changeLocale(String locale) {
        if (settings == null) {
            throw new IllegalStateException("Chưa khởi tạo cài đặt");
        }
        settings.changeLocale(locale);
    }

    public void removeSettings() {
        AccountSettings old = this.settings;
        this.settings = null;
        if (old != null) {
            old.attachTo(null);
        }
    }
}
~~~

~~~java
@Entity
@Table(
    name = "account_settings",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_settings_account",
        columnNames = "account_id"
    )
)
public class AccountSettings {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "account_id",
        nullable = false,
        unique = true
    )
    private Account account;

    @Column(nullable = false, length = 15)
    private String locale;

    protected AccountSettings() {}

    AccountSettings(String locale) {
        changeLocale(locale);
    }

    void attachTo(Account owner) {
        this.account = owner;
    }

    void changeLocale(String locale) {
        if (locale == null || locale.isBlank()) {
            throw new IllegalArgumentException("Locale không hợp lệ");
        }
        this.locale = locale;
    }
}
~~~

Ở đây:

- `AccountSettings.account` là owning side JPA, vì nó gắn với cột `account_id`.
- `Account.settings` là inverse side JPA với `mappedBy = "account"`.
- `Account` là chủ nghiệp vụ quyết định tạo, sửa và hủy `AccountSettings`.
- `cascade` và `orphanRemoval` phản ánh lifecycle dependency từ tài khoản xuống settings.
- Cột `account_id` cần UNIQUE để không có hai hàng settings cùng trỏ tới một account. JPA annotation nên được phản ánh bằng migration/constraint thực tế.

Sơ đồ database:

~~~text
accounts
  id PK
     ^
     | account_settings.account_id (FK, UNIQUE, NOT NULL)
     |
account_settings
  id PK
  account_id
  locale
~~~

`UNIQUE` ngăn *một account có nhiều settings*, còn `NOT NULL` ngăn settings tồn tại mà không trỏ tới account. Hai constraint đó **không tự buộc mỗi account phải có đúng một settings**; nếu nghiệp vụ yêu cầu luôn có settings, phải áp dụng quy tắc tạo/check ở domain và cân nhắc ràng buộc thêm khi cần.

### 7.2. FK đặt ở phía root cũng hợp lệ nếu schema phù hợp

Một thiết kế khác có thể đặt cột `settings_id` trong bảng `accounts`:

~~~java
@Entity
class Account {

    @Id
    Long id;

    @OneToOne(fetch = FetchType.LAZY, cascade = CascadeType.ALL)
    @JoinColumn(name = "settings_id", unique = true)
    AccountSettings settings;
}
~~~

Khi đó `Account` vừa là **owning side JPA** vừa là **root quản lý vòng đời nghiệp vụ** nếu domain được thiết kế như vậy.

Do đó, mối quan hệ giữa hai loại “owner” là **độc lập**, không có quy tắc bắt buộc chúng phải nằm cùng phía hoặc khác phía.

### 7.3. @MapsId: vòng đời phụ thuộc và primary key dùng chung

Khi settings không cần identity độc lập, có thể cân nhắc kiểu một-một có **shared primary key**:

~~~java
@Entity
class AccountSettings {

    @Id
    private Long id;

    @MapsId
    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "id")
    private Account account;
}
~~~

Ở đây `account_settings.id` vừa là PK vừa tham chiếu `accounts.id`. Mapping `@MapsId` liên kết identity của entity con với entity cha. Phía có `@JoinColumn` và `@MapsId` vẫn là phía ánh xạ FK; nghiệp vụ vẫn có thể yêu cầu mọi thay đổi settings đi qua `Account`.

Việc chọn shared primary key là một quyết định về schema/identity, không phải điều kiện bắt buộc để xác định aggregate root.

## 8. Đồng bộ hai phía Java và điều gì xảy ra khi flush?

Với mapping hai chiều, một association chỉ có **một liên kết logic** nhưng có thể có hai tham chiếu Java:

~~~text
order.lines.contains(line) == true
line.order == order
~~~

Nếu hai biểu thức bất đồng, object graph không nhất quán. Điều này có thể gây:

- Code nghiệp vụ đọc từ collection thấy thiếu hoặc thừa entity.
- Logic validation nhận định sai số dòng hàng.
- Hibernate cập nhật FK theo owning side khác với mong đợi từ collection inverse.
- Những thao tác tiếp theo trong cùng persistence context hoạt động khó dự đoán.

Vì vậy nên có **helper method tập trung** quản lý hai chiều, thường nằm trên aggregate root nếu root chịu trách nhiệm hành vi.

~~~java
public void addLine(OrderLine line) {
    requireDraft();

    if (line == null) {
        throw new IllegalArgumentException("Dòng hàng trống");
    }

    if (!lines.contains(line)) {
        lines.add(line);
    }

    line.attachTo(this);
}
~~~

Đây là một biến thể đơn giản; trong hệ thống thật còn phải kiểm tra dòng hàng đang thuộc một đơn khác hay không và xử lý identity của entity mới/đã lưu. Không dùng helper để cho phép chuyển aggregate con một cách vô điều kiện.

**Không trông chờ `flush()` hoặc `refresh()` để tự sửa một object graph Java vốn đã sai ý nghĩa nghiệp vụ.** Hibernate đồng bộ persistent state dựa trên mapping, nhưng domain nên bảo đảm hai tham chiếu nhất quán trước đó.

## 9. Cơ chế xóa: ORM cascade, orphan removal và FK ON DELETE CASCADE

Ba cơ chế sau có tác dụng khác nhau:

| Cơ chế | Được thực thi ở đâu? | Tình huống tiêu biểu |
| --- | --- | --- |
| JPA `CascadeType.REMOVE` | Hibernate/JPA khi gọi remove và xử lý entity liên quan | Xóa root và lan xuống child theo mapping |
| JPA `orphanRemoval = true` | Hibernate/JPA khi entity phụ thuộc bị loại khỏi association | Xóa một child khỏi collection root |
| SQL `ON DELETE CASCADE` | Database khi hàng cha bị xóa | DB tự xóa những hàng chứa FK tham chiếu |

Ví dụ SQL:

~~~sql
ALTER TABLE order_lines
ADD CONSTRAINT fk_order_line_order
FOREIGN KEY (order_id)
REFERENCES orders(id)
ON DELETE CASCADE;
~~~

Với database có `ON DELETE CASCADE`, khi database thực thi lệnh xóa hàng `orders`, nó có thể tự xóa `order_lines` liên quan. **Đây là ràng buộc DB**, không đồng nghĩa Hibernate đã gọi `remove()` cho từng entity con hoặc chạy đầy đủ callback/cascade Java.

Cần chú ý:

- Dùng native SQL hoặc bulk JPQL để xóa hàng có thể **bỏ qua vòng đời entity** và nhiều callback/cascade ORM.
- Nếu dựa vào database cascade, persistence context đã nạp sẵn entity có thể cần đồng bộ lại.
- ORM cascade và DB cascade có thể cùng xuất hiện nhưng phải hiểu cách Hibernate xử lý và bảo đảm không tạo kỳ vọng sai về callback hoặc event nghiệp vụ.
- Không nên dùng `ON DELETE CASCADE` trên FK trỏ tới aggregate độc lập nếu việc xóa aggregate gốc không được phép xóa các đối tượng tham chiếu trong domain.

Thiết kế xóa phải xuất phát từ **quy tắc vòng đời**, sau đó mới chọn cơ chế Hibernate/SQL để thực hiện an toàn và hiệu quả.

## 10. Vòng đời nghiệp vụ và ranh giới transaction

Một aggregate root thường là **ranh giới nhất quán của một transaction** trong thiết kế domain. Ví dụ một thao tác xác nhận đơn cần bảo vệ đồng thời các điều kiện:

1. Đơn đang ở trạng thái DRAFT.
2. Đơn có ít nhất một dòng hàng hợp lệ.
3. Tổng số lượng và giá trị đơn thỏa quy tắc.
4. Trạng thái mới là CONFIRMED và không còn được sửa dòng hàng.

Application service có thể mở transaction và gọi một phương thức domain:

~~~java
@Transactional
public void confirmOrder(Long orderId) {
    Order order = entityManager.find(Order.class, orderId);

    if (order == null) {
        throw new IllegalArgumentException("Không tìm thấy đơn");
    }

    order.confirm();
}
~~~

Transaction và dirty checking ghi thay đổi `status`. Quan hệ `OrderLine.order` vẫn là owning side FK; nó **không quyết định** quyền xác nhận đơn.

Nếu có nhiều request cập nhật cùng một aggregate, có thể dùng optimistic locking:

~~~java
@Version
private long version;
~~~

Đặt version trên root phù hợp khi cần phát hiện cập nhật cạnh tranh của chính root. Tuy nhiên, không nên mặc định mọi sửa đổi child đều làm tăng version của root trong mọi mapping/provider. Nếu bất biến phụ thuộc cả child và các transaction đồng thời, cần thiết kế cơ chế khóa/version hoặc truy vấn nhất quán phù hợp thực tế.

### 10.1. Không nhầm service điều phối với entity owning side

Service có thể gọi repository cho nhiều entity, transaction manager có thể điều phối connection và Hibernate có thể phát ra nhiều SQL. Những cơ chế đó thuộc tầng ứng dụng/persistence.

Aggregate root là nơi diễn đạt và bảo vệ quy tắc nghiệp vụ. Owning side JPA chỉ nói “Hibernate dựa trên thuộc tính nào để biểu diễn liên kết trong database”. Đây là hai quyết định khác mức trừu tượng.

## 11. Một số trường hợp làm rõ ranh giới

### 11.1. Một con có thể chuyển sang cha khác?

Ví dụ nhân viên chuyển từ phòng ban A sang phòng ban B:

~~~java
employee.changeDepartment(newDepartment);
~~~

`Employee.department` là owning side JPA, nhưng `Department` thường là entity độc lập. Việc chuyển phòng ban không nên xóa nhân viên hoặc phòng ban. `orphanRemoval` trên tập nhân viên của phòng ban không phù hợp với ý nghĩa đó.

Ngược lại, một `OrderLine` đã thuộc đơn A có thể không được phép chuyển sang đơn B: chuyển tương đương hủy dòng ở A và tạo dòng mới ở B theo các quy tắc mới. Khi đó orphan removal có thể phù hợp.

### 11.2. Một con có identity độc lập?

Nếu `Address` là một địa chỉ giao hàng bất biến thuộc Order tại thời điểm đặt hàng, nó có thể phù hợp với `@Embeddable` hoặc value object. Nếu `Address` là địa chỉ trong sổ địa chỉ người dùng có thể dùng lại, nó có thể là entity độc lập.

Quyết định entity/value object và aggregate boundary nên được đưa ra trước, sau đó mới chọn `@OneToOne`, `@ManyToOne` hoặc `@Embedded`.

### 11.3. Một quan hệ đơn trị không nhất thiết là sở hữu vòng đời

`Ticket.assignee` là một tham chiếu `@ManyToOne` từ ticket tới user. Ticket giữ FK, nhưng người dùng vẫn tồn tại độc lập. Không nên cascade remove từ ticket sang user.

### 11.4. Hai aggregate có thể tham chiếu nhau?

Có thể, nhưng nên cân nhắc giảm coupling và ranh giới transaction. Nhiều thiết kế DDD chỉ giữ ID của aggregate bên ngoài thay vì object reference trực tiếp. JPA có thể ánh xạ entity reference, nhưng lựa chọn đó không có nghĩa hai aggregate đương nhiên chung vòng đời hoặc phải cascade tất cả.

## 12. Tương tác với truy vấn và tải dữ liệu

Owning side **không tự quyết định fetch strategy**. Với quan hệ đơn trị:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

`FetchType.LAZY` là gợi ý tải trễ, hữu ích khi không cần đọc `Customer` cho mọi hóa đơn. Cần kiểm tra SQL phát sinh, vấn đề N+1 và phạm vi persistence context.

Với quan hệ một-một hai chiều, đặc biệt phía `mappedBy`, provider có thể cần truy vấn phụ để biết entity liên quan có tồn tại hay không; khả năng lazy của `@OneToOne` còn phụ thuộc phiên bản Hibernate, kiểu mapping và bytecode enhancement. Không nên khẳng định “phía owning luôn LAZY còn inverse luôn EAGER”.

Tối ưu truy vấn bằng DTO projection, fetch join hoặc entity graph là quyết định **truy cập dữ liệu**; nó không làm thay đổi vị trí FK owner hoặc aggregate root.

### 12.1. Query trực tiếp child có phá aggregate boundary không?

Một repository có thể cần đọc `OrderLine` để làm báo cáo. Việc **đọc** các dòng hàng bằng query độc lập không bắt buộc phải cho phép code nghiệp vụ **sửa** chúng ngoài root.

Trong thiết kế domain, có thể tách rõ read model/DTO dùng cho báo cáo khỏi các command thay đổi trạng thái. Đây là một cách bảo vệ invariant mà không ép mọi use case đọc toàn bộ aggregate.

## 13. Những sai lầm phổ biến

| Nhận định | Vì sao chưa đúng? | Cách sửa |
| --- | --- | --- |
| “`mappedBy` nghĩa là entity này không được quản lý bởi Hibernate.” | `mappedBy` chỉ nói phía đối ứng của **quan hệ**; entity vẫn được persist/dirty-check các field của nó | Phân biệt entity lifecycle và ownership của association |
| “Phía nào có `@JoinColumn` là cha nghiệp vụ.” | FK nằm ở đâu không quyết định aggregate root | Dựa vào invariant và lifecycle dependency |
| “Root phải là owning side JPA.” | Trong Order–OrderLine, root có thể là phía `mappedBy` | Thiết kế quan hệ theo schema và domain riêng |
| “`cascade = ALL` làm entity thành owning side.” | Cascade chỉ lan truyền thao tác entity | Owning side vẫn do `mappedBy`/join mapping xác định |
| “Chỉ add vào collection inverse là đủ đổi FK.” | FK được quản lý qua owning side | Helper method cập nhật cả hai phía |
| “Xóa child thì cần xóa luôn parent.” | Child có FK không có nghĩa nó sở hữu parent | Không cascade REMOVE từ `@ManyToOne` đến root độc lập |
| “`orphanRemoval` giống `CascadeType.REMOVE`.” | Orphan removal xử lý child bị tách khỏi association; REMOVE lan khi parent bị xóa | Chọn theo hành vi nghiệp vụ |
| “FK `ON DELETE CASCADE` chạy callback Hibernate.” | Database xóa hàng, không thực thi đầy đủ vòng đời entity Java | Thiết kế DB cascade và sự kiện nghiệp vụ riêng |
| “Nếu `@OneToOne` thì hai entity luôn cùng vòng đời.” | Cardinality một-một không nói gì về identity hoặc quyền xóa | Kiểm tra lifecycle thật |
| “Cùng transaction nghĩa là một aggregate.” | Một transaction có thể tác động nhiều aggregate khi cần | Aggregate là ranh giới nghiệp vụ, transaction là cơ chế nhất quán |

## 14. Quy trình thiết kế một quan hệ mới

Khi mô hình hai entity A và B, nên quyết định theo hai lượt:

**Lượt 1 — Thiết kế nghiệp vụ**

1. A và B có identity riêng không?
2. B có tồn tại hợp lệ nếu A bị xóa không?
3. B có được tham chiếu bởi nhiều A khác nhau không?
4. Ai được phép tạo, sửa, chuyển hoặc xóa B?
5. Những invariant nào phải được bảo vệ đồng thời?
6. Nên dùng entity con, value object hay một aggregate độc lập?

**Lượt 2 — Thiết kế persistence**

1. Cardinality: một-một hay nhiều-một?
2. FK được đặt ở bảng nào? Có cần UNIQUE, NOT NULL hoặc join table không?
3. Attribute nào là owning side (`@JoinColumn`); nếu hai chiều, attribute nào dùng `mappedBy`?
4. Có cần cascade PERSIST/MERGE/REMOVE theo vòng đời không?
5. Có đúng nghĩa orphan removal không?
6. Làm sao đồng bộ cả hai phía Java qua helper method?
7. Ràng buộc database, transaction, version/locking và migration sẽ bảo vệ dữ liệu ra sao?
8. Fetch strategy và các truy vấn đọc phù hợp use case nào?

Không cần ép các câu trả lời của lượt 1 và lượt 2 phải dẫn đến cùng một entity “owner”.

## 15. Bài tập vận dụng

### Bài 1 — Đơn hàng và dòng hàng

Cho mapping:

~~~java
class Order {
    @OneToMany(mappedBy = "order",
               cascade = CascadeType.ALL,
               orphanRemoval = true)
    List<OrderLine> lines;
}

class OrderLine {
    @ManyToOne
    @JoinColumn(name = "order_id")
    Order order;
}
~~~

Hãy xác định: (a) owning side JPA; (b) phía quản lý vòng đời nếu dòng hàng chỉ tồn tại cùng đơn; (c) vì sao thêm line vào collection chưa đủ; (d) ý nghĩa của orphan removal.

### Bài 2 — Invoice và Customer

Một Invoice tham chiếu Customer bằng `@ManyToOne` và `@JoinColumn(name = "customer_id")`. Khi xóa Invoice, có được cascade REMOVE sang Customer không? Vì sao owning side JPA không trả lời câu hỏi này?

### Bài 3 — Account và Settings

Một `Account` có một `AccountSettings` phụ thuộc; FK `account_id UNIQUE` nằm trong bảng `account_settings`. Hãy đề xuất vị trí `@OneToOne`, `@JoinColumn`, `mappedBy` và chỗ đặt `cascade`/`orphanRemoval` để root Account kiểm soát vòng đời settings.

### Bài 4 — Chuyển nhân viên giữa phòng ban

Entity `Employee` có `@ManyToOne Department department`; `Department` có `@OneToMany(mappedBy = "department") List<Employee> employees`. Một nhân viên có thể chuyển phòng ban. Bạn có nên đặt `orphanRemoval = true` trên collection nhân viên của phòng ban không? Cần cập nhật những tham chiếu Java nào?

### Bài 5 — Kiểm tra phát biểu

Đánh giá các phát biểu sau và giải thích:

1. “Một entity là phía `mappedBy` thì không thể có `cascade = ALL`.”
2. “Nếu hai entity liên kết `@OneToOne`, bên giữ FK chắc chắn phải xóa bên còn lại khi bị xóa.”
3. “Nếu xóa root qua bulk JPQL, các lifecycle callback và cascade entity luôn chạy như khi `entityManager.remove(root)`.”
4. “Root quyết định quy tắc thêm child, nhưng child có thể giữ FK và là owning side JPA.”

### Định hướng trả lời

- **Bài 1:** Owning side JPA là `OrderLine.order`; chủ vòng đời là `Order`; helper method cần đồng bộ cả collection và reference; orphan removal hỗ trợ xóa child khi bị bỏ khỏi quan hệ phụ thuộc.
- **Bài 2:** Không cascade REMOVE sang Customer nếu Customer độc lập; FK owner chỉ quyết định ánh xạ.
- **Bài 3:** `AccountSettings.account` có `@JoinColumn` và sở hữu FK; `Account.settings` dùng `mappedBy = "account"`, cascade/orphan removal phù hợp đặt từ root tới dependent.
- **Bài 4:** Không nên dùng orphan removal nếu mục tiêu là chuyển nhân viên giữa phòng ban mà không xóa nhân viên; cập nhật `employee.department` và collection của cả phòng ban cũ/mới trong bộ nhớ.
- **Bài 5:** (1) Sai, cascade độc lập owning side; (2) Sai, phụ thuộc quy tắc domain; (3) Sai, bulk operation không áp dụng vòng đời entity như remove từng object; (4) Đúng.

---

**Nguyên tắc ghi nhớ:** **Owning side của JPA quản lý việc ghi liên kết**, còn **aggregate root/chủ sở hữu vòng đời quản lý quy tắc tạo, thay đổi và hủy đối tượng trong nghiệp vụ**. Khi thiết kế `@ManyToOne` hoặc `@OneToOne`, hãy quyết định vòng đời theo domain, đặt FK theo schema phù hợp, đồng bộ hai phía của quan hệ hai chiều và chỉ dùng cascade/orphan removal khi chúng phản ánh đúng những quy tắc đó.
