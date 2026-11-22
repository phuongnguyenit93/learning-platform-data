# Ánh xạ đối tượng – quan hệ (ORM) là gì và giải quyết vấn đề nào?

Trong ứng dụng Java, lập trình viên thường làm việc với **đối tượng**: `Customer` có tên, `PurchaseOrder` có tổng tiền và tham chiếu đến khách hàng đã đặt hàng. Nhưng cơ sở dữ liệu quan hệ lại lưu dữ liệu dưới dạng **bảng, hàng, cột, khóa chính và khóa ngoại**. Hai cách biểu diễn này phục vụ những mục đích khác nhau, nên cần một cơ chế chuyển đổi giữa chúng.

**Object–Relational Mapping (ORM)**, hay **ánh xạ đối tượng – quan hệ**, là kỹ thuật gắn các lớp và đối tượng trong chương trình với cấu trúc dữ liệu quan hệ, từ đó hỗ trợ đọc, ghi, cập nhật và xóa dữ liệu thông qua các đối tượng. Trong hệ sinh thái Java, **JPA (Jakarta Persistence)** là một đặc tả phổ biến về cách quản lý thực thể và ánh xạ; **Hibernate ORM** là một trong những công cụ triển khai đặc tả đó.

Mục tiêu quan trọng nhất của ORM là giảm phần việc chuyển đổi lặp đi lặp lại giữa mô hình đối tượng và mô hình quan hệ, đồng thời cung cấp một cách nhất quán để quản lý dữ liệu có vòng đời dài hơn một lần chạy chương trình. ORM vẫn làm việc với cơ sở dữ liệu quan hệ và SQL; nó không khiến cấu trúc bảng, truy vấn hay giao dịch trở nên không cần thiết.

## 1. Vì sao đối tượng và bảng không khớp nhau hoàn toàn?

Giả sử một hệ thống bán hàng cần lưu khách hàng và đơn hàng. Trong mã Java, ta tự nhiên nghĩ đến hai đối tượng có quan hệ tham chiếu:

```text
Customer
  id = 10
  name = "Lan"

PurchaseOrder
  id = 105
  totalAmount = 199000.00
  customer ──────────────> Customer(id = 10, name = "Lan")
```

Trong cơ sở dữ liệu quan hệ, cùng thông tin đó có thể được lưu như sau:

**Bảng `customers`**

| id (PK) | name |
| --- | --- |
| 10 | Lan |

**Bảng `purchase_orders`**

| id (PK) | customer_id (FK) | total_amount |
| --- | --- | --- |
| 105 | 10 | 199000.00 |

Đối tượng `PurchaseOrder` giữ một **tham chiếu** đến `Customer`; hàng trong `purchase_orders` chỉ giữ giá trị **khóa ngoại** `customer_id = 10`. Khi đọc đơn hàng, chương trình phải quyết định có tải thêm khách hàng hay không, khi nào tải, và làm sao để hai đối tượng cùng tham chiếu đến một khách hàng nhất quán trong phạm vi làm việc hiện tại.

Đây là một ví dụ của **sự khác biệt giữa mô hình đối tượng và mô hình quan hệ** (*object–relational impedance mismatch*).

| Góc nhìn | Mô hình đối tượng Java | Mô hình quan hệ |
| --- | --- | --- |
| Đơn vị cấu trúc | Lớp, thuộc tính, đối tượng | Bảng, cột, hàng |
| Định danh | Tham chiếu đối tượng; có thể có trường `id` | Khóa chính (`PRIMARY KEY`) |
| Liên kết | Tham chiếu, tập hợp đối tượng | Khóa ngoại (`FOREIGN KEY`), bảng nối, `JOIN` |
| Kiểu dữ liệu | `String`, `BigDecimal`, `LocalDate`, enum... | `VARCHAR`, `NUMERIC`, `DATE`, các kiểu SQL... |
| Kế thừa | `extends`, interface, đa hình | Không có mô hình kế thừa tương ứng trực tiếp giữa các bảng |
| Truy cập dữ liệu | Đi qua trường và phương thức | Chọn hàng, lọc, nhóm, nối bảng bằng truy vấn |
| Vòng đời | Được tạo, thay đổi, giải phóng trong bộ nhớ | Được lưu bền vững qua các phiên chạy ứng dụng |

ORM cung cấp các quy tắc để thu hẹp khoảng cách này. Chẳng hạn, một đối tượng có thể được ánh xạ vào một hàng; thuộc tính `customer` được ánh xạ thành khóa ngoại `customer_id`; thuộc tính `totalAmount` được chuyển thành cột `total_amount` với kiểu số thích hợp.

## 2. ORM thực hiện công việc gì?

Một ORM điển hình sử dụng **metadata ánh xạ** (thường qua annotation hoặc cấu hình) để biết:

1. Lớp nào biểu diễn dữ liệu cần lưu trữ, và nó tương ứng với bảng nào.
2. Thuộc tính nào tương ứng với cột nào, kiểu dữ liệu và ràng buộc cần thiết là gì.
3. Thuộc tính nào là khóa chính, khóa chính được cấp phát ra sao.
4. Quan hệ giữa các đối tượng tương ứng với khóa ngoại hay bảng nối nào.
5. Những thay đổi nào cần được đồng bộ xuống cơ sở dữ liệu trong một giao dịch.

Luồng hoạt động khái quát:

```text
Mã Java làm việc với đối tượng
        |
        v
API ORM / JPA (EntityManager hoặc lớp truy cập dữ liệu)
        |
        v
ORM đọc metadata, quản lý thực thể, tạo / thực thi SQL
        |
        v
JDBC driver
        |
        v
Cơ sở dữ liệu quan hệ (bảng, khóa, chỉ mục, giao dịch)
```

Ví dụ, lời gọi `entityManager.find(Customer.class, 10L)` yêu cầu tìm một thực thể `Customer` theo khóa chính. ORM có thể sử dụng dữ liệu đã được quản lý trong *persistence context* hoặc thực hiện truy vấn SQL tương đương `SELECT ... FROM customers WHERE id = ?`, sau đó chuyển hàng kết quả thành một đối tượng Java. Việc truy vấn SQL thực sự xảy ra khi nào phụ thuộc vào trạng thái của thực thể, bộ nhớ đệm, cấu hình và nhà cung cấp ORM.

Khi ghi dữ liệu, ORM có thể tạo các câu lệnh `INSERT`, `UPDATE`, `DELETE` dựa trên trạng thái thực thể. Câu lệnh cụ thể và thời điểm thực thi có thể khác nhau giữa các công cụ hoặc chiến lược cấp phát khóa chính.

## 3. Những vấn đề ORM giúp giải quyết

### 3.1. Giảm mã chuyển đổi hàng dữ liệu thành đối tượng

Với JDBC thuần, ngay cả thao tác lấy một khách hàng cũng thường đòi hỏi mở câu lệnh, gán tham số, chạy truy vấn, đọc từng cột và tạo đối tượng:

```java
// connection là JDBC Connection đang được quản lý ở bên ngoài.
CustomerView customer = null;

try (PreparedStatement statement = connection.prepareStatement(
        "SELECT id, name FROM customers WHERE id = ?")) {
    statement.setLong(1, customerId);

    try (ResultSet result = statement.executeQuery()) {
        if (result.next()) {
            customer = new CustomerView(
                    result.getLong("id"),
                    result.getString("name")
            );
        }
    }
}

// Ví dụ kiểu nhận dữ liệu: record CustomerView(Long id, String name) {}
```

Khi bảng có nhiều cột hoặc truy vấn nối nhiều bảng, phần mã đọc `ResultSet`, chuyển kiểu, xây dựng đối tượng và xử lý quan hệ sẽ dài thêm. Với một lớp đã được ánh xạ bằng JPA, thao tác tương ứng có thể được diễn đạt ngắn gọn:

```java
Customer customer = entityManager.find(Customer.class, customerId);
```

ORM đảm nhận phần ánh xạ đã khai báo. Điều này đặc biệt hữu ích khi ứng dụng có nhiều thực thể và các thao tác CRUD thông thường. JDBC vẫn là lựa chọn hợp lý nếu cần kiểm soát trực tiếp từng câu SQL hoặc chỉ đọc dữ liệu đơn giản.

### 3.2. Biểu diễn và quản lý quan hệ giữa các thực thể

Trong Java, việc đi từ đơn hàng sang khách hàng thường là `order.getCustomer()`. Trong cơ sở dữ liệu, thao tác này phải dựa trên `customer_id` và có thể cần `JOIN` hoặc một truy vấn riêng.

ORM cho phép khai báo các kiểu quan hệ như `@ManyToOne`, `@OneToMany`, `@OneToOne` và `@ManyToMany`. Từ metadata đó, ORM biết cách liên kết khóa ngoại với tham chiếu hoặc tập hợp đối tượng. Nó cũng hỗ trợ cấu hình **tải ngay/tải trì hoãn** (*eager/lazy loading*) và quy tắc **lan truyền thao tác** (*cascade*) khi phù hợp.

Tuy vậy, quan hệ trong mã không đồng nghĩa ORM sẽ truy vấn hiệu quả trong mọi trường hợp. Truy cập một quan hệ tải trì hoãn có thể phát sinh thêm SQL; tải hàng loạt mà không cân nhắc có thể gây hiện tượng **N+1 query**.

### 3.3. Theo dõi thay đổi và đồng bộ dữ liệu

Một ORM như Hibernate thường quản lý các thực thể bên trong *persistence context* (ngữ cảnh lưu trữ). Trong phạm vi ngữ cảnh đó, thực thể được quản lý có **định danh nhất quán**: đối với cùng loại thực thể và cùng khóa chính, các lần tìm kiếm thường trả về cùng một phiên bản đối tượng được quản lý.

Khi thuộc tính của thực thể được quản lý thay đổi, ORM có thể nhận biết sự thay đổi (*dirty checking*) và đồng bộ xuống database trong quá trình *flush*. Ví dụ:

```java
EntityTransaction transaction = entityManager.getTransaction();
transaction.begin();

PurchaseOrder order = entityManager.find(PurchaseOrder.class, 105L);
if (order == null) {
    transaction.rollback();
    throw new IllegalArgumentException("Không tìm thấy đơn hàng");
}

order.changeTotalAmount(new BigDecimal("250000.00"));
transaction.commit(); // ORM đồng bộ thay đổi theo vòng đời giao dịch.
```

Đoạn này minh họa `EntityManager` quản lý giao dịch trực tiếp trong môi trường Java SE. Ở ứng dụng có giao dịch do framework hoặc container quản lý, cách bắt đầu/kết thúc giao dịch sẽ khác. Ví dụ cũng giả định không có lỗi trong khi thao tác; mã ứng dụng thực tế cần rollback và giải phóng tài nguyên theo môi trường chạy.

Tính năng theo dõi thay đổi giúp bớt các lệnh cập nhật thủ công. Nó chỉ áp dụng đúng theo trạng thái của thực thể và ngữ cảnh quản lý; sửa một đối tượng **detached** không tự động làm database thay đổi.

### 3.4. Nhất quán cách làm việc với truy vấn và giao dịch

ORM thường đi kèm một API nhất quán cho việc tìm, lưu, xóa và truy vấn dữ liệu. Trong JPA, ngoài truy vấn theo khóa chính, ta có thể dùng **JPQL** để viết truy vấn theo tên thực thể và thuộc tính Java:

```java
List<PurchaseOrder> orders = entityManager.createQuery(
        "SELECT o FROM PurchaseOrder o WHERE o.totalAmount >= :minimum",
        PurchaseOrder.class
    )
    .setParameter("minimum", new BigDecimal("100000.00"))
    .getResultList();
```

JPQL thao tác với `PurchaseOrder` và `totalAmount`, trong khi SQL làm việc với `purchase_orders` và `total_amount`. ORM chuyển truy vấn sang SQL theo hệ quản trị và cách ánh xạ tương ứng. Tham số `:minimum` được truyền theo cơ chế tham số hóa, thay vì nối trực tiếp chuỗi đầu vào thành câu truy vấn.

ORM cũng phối hợp với giao dịch để bảo đảm một nhóm thao tác thành công hoặc thất bại theo cam kết của database. **ACID, khóa, mức cô lập và ràng buộc toàn vẹn vẫn do hệ quản trị cơ sở dữ liệu thực thi**; ORM không tự thay thế chúng.

### 3.5. Hỗ trợ tính di động và bảo trì

Việc định nghĩa ánh xạ tập trung giúp đổi tên thuộc tính, chỉnh quan hệ hoặc thay cấu trúc mã dễ kiểm soát hơn so với đặt mã đọc cột thủ công ở nhiều nơi. JPA đưa ra API chung, còn nhà cung cấp ORM có thể xử lý khác biệt SQL giữa các hệ quản trị (*SQL dialect*).

**Tính di động chỉ mang tính tương đối**: kiểu dữ liệu đặc thù, câu SQL native, cú pháp phân trang, khóa, hàm database và hiệu năng truy vấn vẫn có thể phụ thuộc hệ quản trị. Tương tự, ORM không thay công cụ quản lý thay đổi schema như Flyway hoặc Liquibase.

## 4. Ví dụ ánh xạ bằng JPA: từ bảng sang thực thể Java

Tiếp tục ví dụ `Customer` và `PurchaseOrder`. Giả sử database PostgreSQL có schema tối giản sau:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    total_amount NUMERIC(12, 2) NOT NULL
);
```

Ta có thể ánh xạ bằng Jakarta Persistence như sau. Lớp thứ nhất biểu diễn bảng `customers`:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected Customer() {
        // Constructor không tham số để JPA khởi tạo thực thể.
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
}
```

Lớp thứ hai biểu diễn bảng `purchase_orders` và quan hệ nhiều đơn hàng thuộc về một khách hàng:

```java
import java.math.BigDecimal;
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
    private BigDecimal totalAmount;

    protected PurchaseOrder() {
        // Constructor không tham số cho JPA.
    }

    public PurchaseOrder(Customer customer, BigDecimal totalAmount) {
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

    public void changeTotalAmount(BigDecimal newAmount) {
        this.totalAmount = newAmount;
    }
}
```

Ý nghĩa những annotation quan trọng:

| Annotation | Vai trò |
| --- | --- |
| `@Entity` | Khai báo lớp là thực thể có thể được JPA quản lý. |
| `@Table(name = ...)` | Chỉ rõ bảng tương ứng. |
| `@Id` | Xác định thuộc tính định danh thực thể. |
| `@GeneratedValue` | Khai báo chiến lược tạo giá trị khóa chính. |
| `@Column` | Cấu hình cột, tên cột, khả năng `NULL`, độ dài hoặc độ chính xác. |
| `@ManyToOne` | Biểu diễn nhiều đơn hàng có thể tham chiếu cùng một khách hàng. |
| `@JoinColumn` | Xác định cột khóa ngoại `customer_id` dùng cho quan hệ. |

Khi đã có một khách hàng mang khóa chính `10`, việc tạo đơn hàng có thể viết ở mức đối tượng:

```java
EntityTransaction transaction = entityManager.getTransaction();
try {
    transaction.begin();

    Customer customer = entityManager.find(Customer.class, 10L);
    if (customer == null) {
        throw new IllegalArgumentException("Không tìm thấy khách hàng");
    }

    PurchaseOrder order = new PurchaseOrder(
            customer,
            new BigDecimal("199000.00")
    );
    entityManager.persist(order);

    transaction.commit();
} catch (RuntimeException exception) {
    if (transaction.isActive()) {
        transaction.rollback();
    }
    throw exception;
}
```

Đây là đoạn mã dùng trong môi trường **giao dịch do ứng dụng quản lý**, với `entityManager` đã được tạo trước đó và sẽ được đóng ở phạm vi thích hợp. Nó minh họa cách gọi API, không phải một chương trình hoàn chỉnh về cấu hình kết nối.

ORM sẽ biết rằng `order.customer` liên quan đến cột `purchase_orders.customer_id` và có thể tạo câu lệnh SQL có ý nghĩa tương tự:

```sql
INSERT INTO purchase_orders (customer_id, total_amount)
VALUES (10, 199000.00);
```

SQL trên chỉ mô tả **ý nghĩa thao tác**; SQL thực tế do provider sinh ra có thể dùng tham số `?`, câu lệnh nhận khóa tự sinh, hoặc thứ tự cột khác. Với chiến lược `IDENTITY`, việc chèn bản ghi có thể diễn ra sớm để lấy khóa chính, không nhất thiết đợi tới `commit`.

## 5. Phân biệt ORM, JPA, Hibernate, JDBC và Spring Data JPA

Các thuật ngữ này cùng xuất hiện trong ứng dụng Java nhưng nằm ở các tầng khác nhau:

| Thành phần | Bản chất | Ví dụ trách nhiệm |
| --- | --- | --- |
| **ORM** | Kỹ thuật/nhóm công cụ ánh xạ đối tượng với dữ liệu quan hệ | Ánh xạ lớp–bảng, thuộc tính–cột, quản lý vòng đời thực thể |
| **JPA / Jakarta Persistence** | Đặc tả và API chuẩn về persistence trong Java | `@Entity`, `EntityManager`, JPQL |
| **Hibernate ORM** | Công cụ ORM, đồng thời là một provider triển khai Jakarta Persistence | Thực thi ánh xạ, quản lý persistence context, sinh SQL |
| **JDBC** | API Java mức thấp để làm việc với database quan hệ | `Connection`, `PreparedStatement`, `ResultSet` |
| **Spring Data JPA** | Lớp trừu tượng repository xây dựng trên JPA | `JpaRepository`, suy diễn truy vấn từ tên phương thức |

Ví dụ, khi dùng `JpaRepository<Customer, Long>`, lập trình viên đang sử dụng Spring Data JPA; bên dưới có thể là API Jakarta Persistence, một provider như Hibernate, rồi JDBC driver để giao tiếp database. **Spring Data JPA không phải tên khác của Hibernate**, và **JPA không phải một database**.

## 6. ORM không giải quyết được điều gì?

ORM hữu ích nhưng việc che đi một phần SQL có thể khiến ta bỏ sót chi phí thực tế. Những giới hạn đáng lưu ý gồm:

- **Hiệu năng truy vấn vẫn cần thiết kế:** Lấy danh sách 100 đơn hàng rồi lần lượt truy cập `getCustomer()` có thể tạo một truy vấn lấy đơn hàng và nhiều truy vấn bổ sung. Tùy trường hợp cần `JOIN FETCH`, entity graph, truy vấn projection hoặc truy vấn riêng phù hợp.
- **Lazy loading phụ thuộc ngữ cảnh:** Truy cập một quan hệ chưa tải sau khi ngữ cảnh persistence đóng có thể không thực hiện được. Cần quyết định dữ liệu sẽ được tải ở ranh giới giao dịch nào.
- **Thiết kế bảng vẫn quan trọng:** Chỉ mục, khóa ngoại, `NOT NULL`, chuẩn hóa dữ liệu và chiến lược migration phải được thiết kế và quản lý. Annotation không bảo đảm schema tối ưu hay dữ liệu hợp lệ trong mọi tình huống.
- **Giao dịch và đồng thời không biến mất:** Phải hiểu commit, rollback, mức cô lập và khi cần khóa lạc quan/bi quan. Việc hai người cùng sửa một bản ghi có thể cần `@Version` hoặc cơ chế kiểm soát đồng thời thích hợp.
- **ORM không thay toàn bộ SQL:** Báo cáo tổng hợp, xử lý dữ liệu hàng loạt, câu truy vấn đặc thù database hoặc thao tác cần tối ưu sâu đôi khi phù hợp hơn với SQL trực tiếp, JDBC hoặc công cụ truy vấn chuyên dụng.
- **Không phải mọi đối tượng đều là entity:** DTO dùng cho API, dữ liệu hiển thị hoặc kết quả báo cáo thường không cần và không nên được quản lý như thực thể ORM.

Vì vậy, sử dụng ORM tốt đòi hỏi hiểu cả **mô hình Java** lẫn **mô hình quan hệ**. Nên kiểm tra SQL được sinh ra và kế hoạch thực thi khi xuất hiện vấn đề hiệu năng, thay vì suy luận chỉ từ số dòng mã Java.

## 7. Khi nào nên dùng ORM, khi nào nên cân nhắc cách khác?

| Nhu cầu | Hướng tiếp cận thường phù hợp | Lý do |
| --- | --- | --- |
| Ứng dụng nghiệp vụ nhiều thực thể, quan hệ và CRUD | ORM/JPA | Tận dụng ánh xạ và quản lý trạng thái thực thể; giảm mã lặp |
| Phát triển theo mô hình domain với quy tắc nghiệp vụ gắn với thực thể | ORM/JPA | Dễ biểu diễn và thao tác trên quan hệ đối tượng |
| Báo cáo đọc nhiều, chọn ít cột, phép tổng hợp phức tạp | SQL, projection hoặc công cụ truy vấn chuyên dụng | Kiểm soát dữ liệu truy xuất và kế hoạch thực thi rõ hơn |
| Import/export hoặc cập nhật hàng loạt dữ liệu rất lớn | JDBC batch, bulk SQL hay phương án chuyên biệt | Tránh tạo và theo dõi quá nhiều entity không cần thiết |
| Dịch vụ nhỏ chỉ có vài truy vấn cố định | JDBC hoặc ORM tùy bối cảnh | Cân nhắc độ phức tạp, nhu cầu ánh xạ và khả năng bảo trì |

Đây không phải lựa chọn loại trừ tuyệt đối. Một ứng dụng có thể dùng JPA cho nghiệp vụ thông thường và dùng native SQL hoặc JDBC cho các tác vụ được xác định rõ là cần tối ưu riêng.

## 8. Những hiểu lầm thường gặp

**“ORM giúp không cần học SQL?”** Không. ORM sinh và thực thi SQL; muốn thiết kế quan hệ, chẩn đoán lỗi khóa ngoại, tránh N+1 và tối ưu ứng dụng vẫn cần hiểu SQL cùng database.

**“Một đối tượng Java luôn tương ứng đúng một hàng trong một bảng?”** Đây là trường hợp phổ biến, nhưng ánh xạ thực tế còn có quan hệ nhiều bảng, kế thừa, kiểu nhúng (*embeddable*) và các cách ánh xạ khác. Không nên coi quy tắc một lớp–một bảng là định nghĩa đầy đủ của ORM.

**“Gọi `persist()` luôn phát ngay `INSERT`?”** Không nhất thiết. JPA có cơ chế *flush*, và thời điểm chạy SQL tùy provider, chiến lược định danh và bối cảnh giao dịch.

**“Có ORM là database sẽ tự bảo đảm mọi cập nhật đúng?”** Không. Ràng buộc dữ liệu, thiết kế giao dịch, xử lý xung đột cập nhật và kiểm soát quyền truy cập vẫn là trách nhiệm thiết kế của ứng dụng và database.

## 9. Ghi nhớ cốt lõi

ORM là **cầu nối giữa đối tượng trong chương trình và dữ liệu trong cơ sở dữ liệu quan hệ**. Nó giải quyết việc ánh xạ lớp–bảng, thuộc tính–cột, tham chiếu–khóa ngoại và giảm mã CRUD/chuyển đổi thủ công. Một ORM có khả năng quản lý thực thể như Hibernate còn giúp theo dõi thay đổi, quản lý quan hệ và phối hợp đồng bộ dữ liệu với giao dịch.

Đổi lại, lập trình viên phải nhận thức rõ SQL phía dưới, phạm vi quản lý thực thể, ranh giới giao dịch và chi phí tải dữ liệu. Nắm được điều này là nền tảng để học các khái niệm tiếp theo của JPA: `@Entity`, trạng thái thực thể, `EntityManager`, quan hệ, truy vấn JPQL và tối ưu hiệu năng.
