# Những kiến thức Java, SQL và giao dịch cần có

> **Chủ đề:** Data Persistence – Relational Access, ORM, JPA  
> **Nhóm kiến thức:** Nền tảng ORM

ORM (Object–Relational Mapping) nối thế giới đối tượng Java với dữ liệu quan hệ. Để dùng JPA/Hibernate đúng, cần hiểu cả ba phía: **đối tượng và vòng đời của chúng trong Java**, **bảng và truy vấn trong SQL**, **ranh giới giao dịch khi nhiều thao tác được thực hiện cùng nhau**. Nếu thiếu một phía, ứng dụng vẫn có thể chạy nhưng dễ gặp lỗi dữ liệu, truy vấn chậm hoặc hành vi khó giải thích.

Sau bài này, người học có thể đọc một mô hình dữ liệu và xác định khóa chính/khóa ngoại; hiểu vì sao Java entity có yêu cầu riêng; viết và đọc những truy vấn SQL thiết yếu; phân biệt flush với commit, managed với detached; giải thích ACID, các lỗi cạnh tranh và lựa chọn cơ chế khóa phù hợp. Đây là kiến thức nền để học sâu về mapping, persistence context, JPQL, transaction management và hiệu năng JPA.

## 1. Nhìn toàn cảnh: đối tượng Java không phải là hàng SQL

Giả sử hệ thống bán hàng có khách hàng và đơn hàng:

~~~java
Customer customer = customerRepository.findById(10L);
List<PurchaseOrder> orders = customer.getOrders();
~~~

Trong Java, **Customer** là đối tượng có trạng thái, hành vi và tham chiếu tới các đối tượng khác. Trong cơ sở dữ liệu quan hệ, thông tin được lưu thành các hàng, chẳng hạn **customers(id, name, email)** và **purchase_orders(id, customer_id, placed_at)**. Một tham chiếu đối tượng có thể được biểu diễn bằng **khóa ngoại**; một collection có thể tương ứng nhiều hàng ở bảng khác.

~~~text
Java                                      Cơ sở dữ liệu quan hệ
Customer(id=10)                           customers
  └── orders: List<PurchaseOrder>             id | name
        ├── Order(id=101)                     10 | An
        └── Order(id=102)
                                          purchase_orders
                                              id  | customer_id
                                              101 | 10
                                              102 | 10
~~~

**JPA** là đặc tả API và quy tắc ánh xạ của Jakarta Persistence; **Hibernate** là một trong các nhà cung cấp triển khai JPA. JPA không loại bỏ SQL hay giao dịch: ORM dựa vào chúng để đọc và ghi dữ liệu, đồng thời quản lý trạng thái entity và thời điểm đồng bộ với database.

Một chuỗi công việc điển hình là:

~~~mermaid
flowchart LR
    A["Service / nghiệp vụ Java"] --> B["Entity và persistence context"]
    B --> C["JPA provider / ORM"]
    C --> D["JDBC và connection"]
    D --> E[("Cơ sở dữ liệu SQL")]
~~~

Ứng dụng không nên xem entity như một bản sao tự động luôn đồng bộ với bảng. Có thời điểm đối tượng được quản lý trong bộ nhớ, có thời điểm ORM gửi SQL, và có thời điểm transaction mới commit. Hiểu ba mốc này giúp tránh nhiều lỗi thường gặp.

## 2. Những kiến thức Java cần vững

### 2.1. Class, object, reference và object identity

Java phân biệt **đối tượng** và **tham chiếu tới đối tượng**. Hai biến cùng trỏ tới một instance thì thay đổi từ một biến sẽ hiện ra qua biến còn lại:

~~~java
Customer a = new Customer("An");
Customer b = a;
b.setName("Bình");
System.out.println(a.getName()); // Bình: a và b cùng tham chiếu
~~~

Ngược lại, hai instance riêng có thể đại diện cùng một hàng trong database:

~~~java
Customer first = loadCustomer(10L);
Customer second = loadCustomerInAnotherContext(10L);
// first == second có thể false dù cả hai ứng với customers.id = 10.
~~~

Phân biệt ba khái niệm:

| Khái niệm | Ví dụ | Ý nghĩa khi dùng ORM |
|---|---|---|
| Reference identity | **a == b** | Cùng một instance Java |
| Logical equality | **a.equals(b)** | Bằng nhau theo quy tắc do class định nghĩa |
| Database identity | **customers.id = 10** | Cùng một hàng theo khóa chính |

Trong **một persistence context**, JPA duy trì identity map: với cùng loại entity và cùng định danh database, thao tác tìm kiếm thường trả về cùng managed instance. Qua hai persistence context khác nhau, không được dựa vào toán tử **==**.

### 2.2. Đóng gói, constructor và khả năng thay đổi trạng thái

Entity thường là class có trạng thái; JPA cần cách tạo instance, đọc và ghi các thuộc tính đã mapping. Một dạng cơ bản:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected Customer() { } // Constructor không tham số cho JPA

    public Customer(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không được trống");
        }
        this.name = name;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên không được trống");
        }
        this.name = newName;
    }
}
~~~

Lưu ý:

- JPA entity cần **constructor không tham số public hoặc protected**; không nhất thiết phải có setter public cho mọi field.
- Nếu annotation mapping đặt trên field như ví dụ, JPA dùng **field access**; đặt trên getter thì dùng **property access**. Nên nhất quán theo từng entity.
- Getter, setter và phương thức nghiệp vụ quyết định tính hợp lệ của trạng thái phía Java. Ràng buộc **NOT NULL**, **UNIQUE**, **CHECK**, **FOREIGN KEY** ở database vẫn cần thiết để bảo vệ dữ liệu bất kể nguồn ghi nào.
- Entity không nên mặc định được xem là immutable record. Các loại immutable như Java **record** thường thích hợp hơn cho DTO hoặc projection, không phải lựa chọn mặc định cho JPA entity.

### 2.3. equals(), hashCode() và collection

Java dùng **equals/hashCode** cho tìm kiếm trong **HashSet**, **HashMap** và kiểm tra phần tử. Với entity có khóa chính được database sinh sau khi **persist**, định danh có thể thay đổi từ **null** sang một giá trị; nếu hashCode đổi sau khi đối tượng vào HashSet, collection có thể hoạt động sai.

Không có một công thức equals/hashCode phù hợp mọi mô hình entity. Cần xét vòng đời transient/managed/detached, khóa nghiệp vụ có ổn định và duy nhất không, và proxy do ORM tạo. Những nguyên tắc an toàn:

- Không tự động đưa toàn bộ field và quan hệ vào equals/hashCode: có thể gây tải lazy, đệ quy vòng và thay đổi hash code khi cập nhật field.
- Khóa nghiệp vụ chỉ phù hợp nếu thực sự **bất biến và duy nhất** trong miền dữ liệu.
- Nếu so sánh theo ID sinh tự động, cần xử lý **ID null**, class/proxy và giữ hashCode ổn định trong vòng đời dùng với hash-based collection.
- Khi chưa rõ quy tắc equality, đừng dùng Set hoặc Map với key là entity chỉ để thay thế một danh sách.

**List** duy trì thứ tự phần tử trong Java, nhưng thứ tự hàng lấy từ SQL chỉ được đảm bảo khi có **ORDER BY**. Mapping collection JPA cũng cần cấu hình phù hợp (**@OrderBy**, **@OrderColumn**) nếu nghiệp vụ phụ thuộc thứ tự.

### 2.4. Kiểu dữ liệu: null, số tiền và thời gian

Java và SQL có hệ kiểu khác nhau. Lựa chọn kiểu ảnh hưởng trực tiếp tới tính đúng đắn của dữ liệu:

| Nhu cầu | Kiểu Java thường dùng | Kiểu SQL thường gặp | Ghi chú |
|---|---|---|---|
| ID dạng số | **Long** | **BIGINT** | Wrapper cho phép null trước khi được cấp ID |
| Số lượng | **Integer/int** | **INTEGER** | Xét ý nghĩa của null; kiểm tra miền giá trị |
| Giá tiền | **BigDecimal** | **DECIMAL/NUMERIC(p,s)** | Tránh double/float cho tiền |
| Ngày (không giờ) | **LocalDate** | **DATE** | Không mang múi giờ |
| Giờ địa phương | **LocalDateTime** | **TIMESTAMP** | Không mang offset/múi giờ |
| Thời điểm tuyệt đối | **Instant** | Tùy DB, thường kiểu hỗ trợ timezone | Quy ước lưu/đọc UTC nhất quán |
| Trạng thái | **enum** | **VARCHAR** hoặc loại enum DB | Ưu tiên mapping chuỗi hơn ordinal |
| Có/không | **Boolean/boolean** | **BOOLEAN** | Boolean wrapper có thể biểu diễn null |

Ví dụ số tiền:

~~~java
BigDecimal price = new BigDecimal("19.90");
BigDecimal quantity = BigDecimal.valueOf(3);
BigDecimal total = price.multiply(quantity); // 59.70

// BigDecimal.equals xét cả scale; compareTo so sánh giá trị số.
boolean sameAmount = new BigDecimal("1.0")
        .compareTo(new BigDecimal("1.00")) == 0;
~~~

Không viết **new BigDecimal(0.1)** nếu muốn đúng chính xác giá trị thập phân 0,1. Với giờ, cần thống nhất ý nghĩa giữa thời gian nghiệp vụ, timezone của JDBC, driver và kiểu cột database. Với enum, **@Enumerated(EnumType.STRING)** dễ đọc và ít rủi ro hơn lưu ordinal: thêm hoặc đổi thứ tự enum sẽ không làm các giá trị cũ bị hiểu thành trạng thái khác.

### 2.5. Annotation, reflection và proxy

Các annotation như **@Entity**, **@Id**, **@Column**, **@OneToMany**, **@ManyToOne** cung cấp metadata để ORM mapping class với bảng. ORM có thể dùng reflection, bytecode enhancement và proxy cho quản lý entity/lazy loading. Vì thế:

- Đừng mặc định mọi object lấy ra là instance “thuần” không có proxy.
- Truy cập quan hệ lazy có thể dẫn đến SQL mới; ngoài phạm vi persistence context phù hợp, việc tải dữ liệu có thể thất bại.
- Không nên gọi getter quan hệ sâu trong **toString()**, logger, JSON serializer hoặc equals/hashCode mà không kiểm soát việc tải dữ liệu.
- **EntityManager** và persistence context không được chia sẻ tùy ý giữa các thread; một HTTP request/task cần ranh giới làm việc rõ ràng.

### 2.6. Exception và quản lý tài nguyên

Khi làm việc trực tiếp qua JDBC, cần nắm **try-with-resources** để đóng **Connection**, **PreparedStatement**, **ResultSet** đúng cách, kể cả khi có lỗi. Với JPA, entity operations có thể ném runtime exception; lỗi SQL ở thời điểm flush/commit cũng có thể khiến transaction phải rollback. Không nên bắt exception rồi coi giao dịch vẫn sử dụng bình thường.

## 3. Những kiến thức cơ sở dữ liệu và SQL cần có

### 3.1. Bảng, hàng, cột và lược đồ

Một **table** có các cột được định kiểu và các hàng dữ liệu. **DDL** định nghĩa cấu trúc (CREATE, ALTER, DROP); **DML** thay đổi dữ liệu (INSERT, UPDATE, DELETE); **SELECT** truy vấn dữ liệu. Ví dụ sau dùng cú pháp gần với **PostgreSQL**; chi tiết tạo ID, date/time và kiểu dữ liệu thay đổi theo hệ quản trị.

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    placed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE order_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    sku VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19, 2) NOT NULL CHECK (unit_price >= 0),
    UNIQUE (order_id, sku)
);

CREATE INDEX idx_orders_customer_time
    ON purchase_orders (customer_id, placed_at);
~~~

Ý nghĩa những ràng buộc quan trọng:

- **PRIMARY KEY:** định danh duy nhất từng hàng; một bảng có thể có khóa chính gồm nhiều cột.
- **FOREIGN KEY:** giá trị phải tham chiếu khóa hợp lệ ở bảng khác (hoặc null nếu cột cho phép); bảo vệ tính toàn vẹn tham chiếu.
- **NOT NULL:** không chấp nhận null. Chuỗi rỗng vẫn khác null và cần kiểm tra riêng.
- **UNIQUE:** ngăn các giá trị trùng theo quy tắc database; cách xử lý nhiều null phụ thuộc hệ quản trị.
- **CHECK:** biểu đạt một điều kiện hợp lệ ngay tại database.
- **INDEX:** cấu trúc hỗ trợ một số kiểu tra cứu, lọc, join, sort; không thay thế khóa hay đảm bảo một truy vấn luôn nhanh.

**Khóa chính** thường có ID kỹ thuật; **khóa nghiệp vụ** là thông tin duy nhất mang ý nghĩa miền dữ liệu, như email hoặc mã đơn. Chúng có thể độc lập: đổi email không cần làm đổi ID khách hàng.

### 3.2. Quan hệ 1–1, 1–N, N–N

Trong mô hình trên, **một khách hàng có nhiều đơn hàng**. Khóa ngoại **purchase_orders.customer_id** nằm ở phía N:

~~~text
customers          purchase_orders           order_items
---------          ---------------           -----------
id (PK) <--------- customer_id (FK)
                    id (PK) <---------------- order_id (FK)
                                               id (PK)
~~~

| Quan hệ | Cách lưu thường gặp | Ví dụ |
|---|---|---|
| Một – một (1–1) | FK có UNIQUE hoặc dùng chung PK | User – UserProfile |
| Một – nhiều (1–N) | FK ở bảng phía nhiều | Customer – PurchaseOrder |
| Nhiều – nhiều (N–N) | Bảng nối chứa hai FK | Student – Course |

Nếu quan hệ N–N có thuộc tính riêng như **quantity**, **unit_price**, **created_at**, nên xem bảng nối như một thực thể nghiệp vụ riêng. **OrderItem** không chỉ là “mối nối” giữa order và product: nó mang số lượng và đơn giá tại thời điểm mua.

**Chuẩn hóa dữ liệu** giúp giảm lặp và tránh bất nhất khi cập nhật: tên khách hàng nên thuộc bảng customers, không cần chép vào mọi đơn nếu không có lý do nghiệp vụ. Tuy vậy, giữ **unit_price** trên từng order item là hợp lý vì cần lưu “giá đã chốt”, không phải giá hiện tại của sản phẩm. Chuẩn hóa và lưu snapshot đều phải dựa trên ý nghĩa dữ liệu.

### 3.3. SELECT, WHERE, JOIN và ORDER BY

SQL diễn đạt điều cần lấy dựa trên tập dữ liệu. Ví dụ:

~~~sql
-- Đơn hàng của khách 10, gần nhất trước.
SELECT o.id, o.status, o.placed_at
FROM purchase_orders AS o
WHERE o.customer_id = 10
ORDER BY o.placed_at DESC, o.id DESC
LIMIT 20;

-- Lấy thông tin đơn cùng tên khách hàng.
SELECT o.id, c.name, o.status
FROM purchase_orders AS o
JOIN customers AS c ON c.id = o.customer_id;

-- Giữ cả khách hàng chưa có đơn.
SELECT c.id, c.name, o.id AS order_id
FROM customers AS c
LEFT JOIN purchase_orders AS o ON o.customer_id = c.id;
~~~

**INNER JOIN** chỉ giữ các cặp khớp điều kiện; **LEFT JOIN** giữ toàn bộ hàng bên trái và dùng null cho cột phía phải khi không có hàng khớp. Điều kiện đặt ở **ON** và **WHERE** có thể tạo kết quả khác nhau khi dùng outer join.

Một lưu ý quan trọng: một phép JOIN từ customer sang nhiều order tạo **nhiều dòng cho một customer**. ORM có thể hợp nhất object ở bộ nhớ nhưng SQL vẫn phải đọc nhiều dòng; join nhiều collection cùng lúc dễ làm bùng số dòng trung gian.

### 3.4. GROUP BY, aggregate và phân trang

~~~sql
SELECT o.customer_id, COUNT(*) AS order_count
FROM purchase_orders AS o
WHERE o.status = 'PAID'
GROUP BY o.customer_id
HAVING COUNT(*) >= 2
ORDER BY order_count DESC;
~~~

**WHERE** lọc hàng trước khi nhóm; **HAVING** lọc nhóm sau aggregate. Các hàm phổ biến gồm **COUNT**, **SUM**, **AVG**, **MIN**, **MAX**. Cần nhớ COUNT(*) đếm hàng, còn COUNT(column) bỏ qua null.

**LIMIT/OFFSET** thường thuận tiện cho trang nhỏ nhưng OFFSET lớn có thể tốn tài nguyên và kết quả dễ thay đổi khi dữ liệu được thêm/xóa. Với danh sách lớn cần cuộn liên tục, cân nhắc **keyset pagination** dựa trên thứ tự ổn định, ví dụ **(placed_at, id)**; luôn có ORDER BY đủ xác định khi phân trang.

### 3.5. NULL và logic ba giá trị

SQL có **TRUE**, **FALSE** và **UNKNOWN** trong điều kiện so sánh liên quan null:

~~~sql
-- Đúng
SELECT * FROM customers WHERE email IS NULL;

-- Không đúng: so sánh với NULL bằng dấu = không trả TRUE.
SELECT * FROM customers WHERE email = NULL;
~~~

Ví dụ **NOT IN** có thể cho kết quả bất ngờ nếu tập con chứa null; **NOT EXISTS** thường rõ nghĩa hơn khi diễn đạt “không tồn tại hàng liên quan”. JPA/JPQL không loại bỏ logic null của SQL; các điều kiện sinh ra vẫn phải được hiểu theo database.

### 3.6. UPDATE, DELETE, số hàng bị tác động và tính toàn vẹn

~~~sql
UPDATE purchase_orders
SET status = 'PAID'
WHERE id = 101 AND status = 'NEW';

DELETE FROM order_items
WHERE order_id = 101;
~~~

Điều kiện WHERE quyết định hàng nào bị thay đổi; số hàng được cập nhật có ý nghĩa nghiệp vụ. Với **UPDATE ... WHERE id=? AND status='NEW'**, kết quả **0 hàng** có thể nghĩa là đơn không tồn tại hoặc đã đổi trạng thái. Nhiều transaction logic an toàn dựa vào kiểm tra row count thay vì chỉ “chạy SQL không lỗi”.

Xóa một hàng được tham chiếu bởi FK có thể bị database từ chối. **ON DELETE CASCADE** thuộc database, còn **CascadeType.REMOVE** thuộc JPA; hai cơ chế khác lớp và không được coi là tương đương. Cần quyết định vòng đời dữ liệu trước khi cấu hình xóa dây chuyền.

### 3.7. Chỉ mục và kế hoạch thực thi

Một index hỗ trợ tra cứu theo cột (hoặc tiền tố cột) phù hợp, nhưng cũng có chi phí ghi và lưu trữ. Với **INDEX(customer_id, placed_at)**, truy vấn lọc **customer_id** rồi sắp xếp thời gian thường có lợi; truy vấn chỉ lọc **placed_at** có thể không hưởng lợi tương tự. Trình tối ưu có thể chọn quét bảng nếu dữ liệu nhỏ hoặc điều kiện ít chọn lọc.

Khi truy vấn chậm, xem **EXPLAIN** hoặc **EXPLAIN ANALYZE** (nếu phù hợp môi trường) để đọc kế hoạch, số hàng và cost thực tế. Không thêm index theo cảm tính; xem điều kiện lọc, join, thứ tự sắp xếp, tính chọn lọc và tần suất cập nhật.

### 3.8. Query có tham số và nguy cơ SQL injection

Giá trị bên ngoài phải được truyền bằng **parameter binding**:

~~~java
String sql = "SELECT id, name FROM customers WHERE email = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, requestedEmail);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id") + ": " + rs.getString("name"));
        }
    }
}
~~~

Không nối input người dùng trực tiếp thành SQL. Với JPQL cũng cần bind tham số bằng **setParameter**. Tham số thường dùng cho **giá trị**, không thay trực tiếp tên bảng/cột hay từ khóa ORDER BY; trường hợp sort động nên chọn từ danh sách trường hợp lệ định trước.

## 4. Nền tảng JDBC để hiểu JPA hoạt động trên gì

JDBC là API thấp hơn ORM. Quy trình đơn giản là lấy connection từ **DataSource**, chuẩn bị statement, gán tham số, chạy câu SQL và đọc **ResultSet**. ORM thường sử dụng JDBC phía dưới để thực hiện SQL mà nó sinh ra.

Những khái niệm phải phân biệt:

| JDBC | Vai trò | Liên hệ với JPA |
|---|---|---|
| **DataSource** | Cấp Connection; thường tích hợp connection pool | JPA provider lấy connection qua cấu hình |
| **Connection** | Phiên kết nối làm việc với DB | Được ORM mượn/trả theo lifecycle |
| **PreparedStatement** | SQL có tham số | ORM bind giá trị trước khi chạy |
| **ResultSet** | Dữ liệu trả về theo hàng/cột | ORM chuyển kết quả thành entity/DTO |
| **autoCommit** | Quyết định mỗi statement có tự commit | Transaction manager điều phối phạm vi commit |

Không nên giữ connection mở suốt vòng đời ứng dụng hoặc giữ entity manager dùng chung mọi request. Connection pool quản lý tài nguyên kết nối; **persistence context** quản lý identity/trạng thái entity. Chúng là hai khái niệm độc lập.

## 5. Giao dịch (transaction): đơn vị nhất quán của nghiệp vụ

### 5.1. Vì sao nhiều lệnh SQL phải thuộc cùng giao dịch?

Chuyển 100.000 đồng từ tài khoản A sang B thường gồm **trừ A** và **cộng B**. Nếu trừ thành công nhưng cộng thất bại, tổng tiền sai. Giao dịch gộp cả hai thành một đơn vị: **hoặc hoàn tất cả hai, hoặc rollback cả hai**.

~~~mermaid
flowchart TD
    A["BEGIN"] --> B["Trừ tiền A"]
    B --> C["Cộng tiền B"]
    C --> D{"Tất cả hợp lệ?"}
    D -->|Có| E["COMMIT"]
    D -->|Không / lỗi| F["ROLLBACK"]
~~~

Đây là lý do transaction nên bám theo **một hành động nghiệp vụ cần nhất quán**, chứ không nhất thiết theo từng lời gọi repository.

### 5.2. ACID: bốn tính chất cần hiểu đúng

| Tính chất | Ý nghĩa | Ví dụ |
|---|---|---|
| **Atomicity** (nguyên tử) | Cả transaction thành công hoặc rollback như một đơn vị | Trừ và cộng tiền cùng thành công |
| **Consistency** (nhất quán) | Transaction hợp lệ đưa dữ liệu từ trạng thái thỏa quy tắc sang trạng thái thỏa quy tắc | Không vi phạm FK/CHECK; nghiệp vụ giữ tổng tiền đúng |
| **Isolation** (cô lập) | Quy định mức độ ảnh hưởng/quan sát giữa các giao dịch đồng thời | Hai người cùng cập nhật tồn kho |
| **Durability** (bền vững) | Sau khi commit thành công, thay đổi được DB đảm bảo bền vững theo cơ chế của nó | Số dư sau commit không mất vì ứng dụng restart |

**Consistency** không có nghĩa database tự biết mọi quy tắc nghiệp vụ. Database thực thi các constraint được khai báo; ứng dụng phải bảo vệ những bất biến khác (chẳng hạn logic chuyển tiền) bằng logic giao dịch đúng.

### 5.3. BEGIN, COMMIT, ROLLBACK và auto-commit

Trong JDBC, nhiều driver chạy ở chế độ **auto-commit=true** mặc định: mỗi statement độc lập có thể được commit ngay. Để gom nhiều lệnh:

~~~java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public void transfer(
        DataSource dataSource, long fromId, long toId, BigDecimal amount
) throws SQLException {
    if (amount == null || amount.signum() <= 0 || fromId == toId) {
        throw new IllegalArgumentException("Giao dịch chuyển tiền không hợp lệ");
    }

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            String debitSql = """
                    UPDATE accounts SET balance = balance - ?
                    WHERE id = ? AND balance >= ?
                    """;
            try (PreparedStatement debit = connection.prepareStatement(debitSql)) {
                debit.setBigDecimal(1, amount);
                debit.setLong(2, fromId);
                debit.setBigDecimal(3, amount);
                if (debit.executeUpdate() != 1) {
                    throw new IllegalStateException("Tài khoản nguồn không đủ tiền hoặc không tồn tại");
                }
            }

            String creditSql = "UPDATE accounts SET balance = balance + ? WHERE id = ?";
            try (PreparedStatement credit = connection.prepareStatement(creditSql)) {
                credit.setBigDecimal(1, amount);
                credit.setLong(2, toId);
                if (credit.executeUpdate() != 1) {
                    throw new IllegalStateException("Tài khoản đích không tồn tại");
                }
            }

            connection.commit();
        } catch (SQLException | RuntimeException ex) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                ex.addSuppressed(rollbackError);
            }
            throw ex;
        }
    }
}
~~~

Ví dụ minh họa tính nguyên tử với bảng **accounts(id, balance)** và cột balance kiểu DECIMAL/NUMERIC. Điều kiện **balance >= amount** trong UPDATE giúp tránh kiểu kiểm tra số dư rồi cập nhật riêng rẽ dễ bị race condition. Trong sản phẩm thực tế còn cần xử lý thứ tự khóa, deadlock/retry, idempotency và yêu cầu nghiệp vụ; cách quản lý connection phụ thuộc transaction manager. Đoạn này cố ý dùng JDBC trực tiếp để thấy rõ transaction.

### 5.4. Các hiện tượng cạnh tranh dữ liệu

Giả sử hai transaction A và B chạy đồng thời:

- **Dirty read:** A thấy dữ liệu B đã sửa dù B chưa commit; B rollback làm giá trị A đã thấy chưa từng được xác nhận.
- **Non-repeatable read:** A đọc cùng một hàng hai lần nhưng giá trị khác vì B commit cập nhật ở giữa.
- **Phantom read:** A chạy lại truy vấn theo điều kiện và thấy thêm/bớt hàng do B commit.
- **Lost update:** A và B cùng đọc một giá trị cũ rồi ghi đè thay đổi của nhau nếu không có bảo vệ phù hợp.
- **Write skew:** Hai transaction cùng đọc một tập điều kiện, cập nhật các hàng khác nhau và kết hợp lại làm vi phạm bất biến nghiệp vụ.

Ví dụ lost update khi tồn kho đang là 10:

~~~text
T1: đọc stock = 10
T2: đọc stock = 10
T1: tính 10 - 1, ghi stock = 9, commit
T2: tính 10 - 1, ghi stock = 9, commit
Kết quả: stock = 9 dù hai đơn đã bán (mong muốn là 8).
~~~

Thay đổi dữ liệu có điều kiện ngay trên DB có thể tránh ví dụ này:

~~~sql
UPDATE products
SET stock = stock - 1
WHERE id = :product_id AND stock >= 1;
-- Chấp nhận bán 1 sản phẩm khi số hàng được cập nhật = 1.
~~~

Với entity được đọc, sửa trong Java rồi ghi lại, có thể dùng **optimistic locking** với cột version; nếu dữ liệu đã đổi, transaction sau cần xử lý xung đột thay vì âm thầm ghi đè.

### 5.5. Mức cô lập giao dịch

SQL định nghĩa các mức **READ UNCOMMITTED**, **READ COMMITTED**, **REPEATABLE READ** và **SERIALIZABLE**. Mức cô lập cao hơn thường hạn chế thêm các bất thường, nhưng có thể làm tăng chờ đợi, xung đột hoặc chi phí vận hành. Triển khai thực tế phụ thuộc database, MVCC, loại câu lệnh và chính sách khóa.

| Isolation level | Hiểu ở mức khái niệm |
|---|---|
| **READ UNCOMMITTED** | Mức tối thiểu; chuẩn cho phép quan sát dữ liệu chưa commit |
| **READ COMMITTED** | Mỗi statement thường chỉ thấy dữ liệu đã commit, nhưng hai lần đọc có thể khác |
| **REPEATABLE READ** | Bảo vệ mạnh hơn cho các lần đọc lặp; phantom/write skew phải xem triển khai DB |
| **SERIALIZABLE** | Kết quả các transaction đồng thời phải tương đương một thứ tự thực thi tuần tự; có thể cần retry khi DB phát hiện xung đột |

Đừng thuộc một bảng “mức X luôn tránh lỗi Y” rồi áp dụng cho mọi hệ quản trị. Ví dụ, PostgreSQL dùng MVCC và snapshot isolation cho REPEATABLE READ; các database khác có thể dùng khóa với ngữ nghĩa khác. Kiểm tra **isolation mặc định**, tài liệu của DB và thực nghiệm phù hợp.

**MVCC (Multi-Version Concurrency Control)** lưu/duy trì các phiên bản dữ liệu để nhiều lượt đọc/ghi có thể diễn ra đồng thời theo quy tắc nhìn thấy dữ liệu. MVCC không đồng nghĩa mọi race condition đã được giải quyết; mất cập nhật và bất biến liên hàng vẫn cần được thiết kế.

### 5.6. Optimistic locking và pessimistic locking

**Optimistic locking** phù hợp khi xung đột tương đối hiếm: đọc entity với version, cập nhật chỉ khi version chưa đổi.

~~~sql
UPDATE purchase_orders
SET status = 'PAID', version = version + 1
WHERE id = 101 AND version = 3;
-- 0 hàng: có thể đã bị cập nhật bởi transaction khác.
~~~

Trong JPA, đánh dấu trường version:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Version
    private Long version;

    // Các trường nghiệp vụ và mapping còn lại...
}
~~~

JPA provider sẽ dùng version để phát hiện cập nhật xung đột; thường báo **OptimisticLockException** hoặc exception tương ứng ở tầng framework, có thể lộ ra khi flush/commit. Khi retry phải chạy lại **toàn bộ đơn vị công việc** trong transaction mới, lấy dữ liệu mới và kiểm tra lại nghiệp vụ; không đơn giản gửi lại cùng đối tượng cũ.

**Pessimistic locking** yêu cầu khóa sớm hơn (ví dụ SQL **SELECT ... FOR UPDATE** hoặc JPA **LockModeType.PESSIMISTIC_WRITE**). Nó hữu ích khi cần ngăn transaction khác sửa hàng trong thời gian xử lý nhưng có thể gây chờ, deadlock và giảm throughput. Khóa hàng cũng không mặc định bảo vệ mọi bất biến liên quan nhiều hàng hoặc “hàng chưa tồn tại”.

### 5.7. Deadlock, timeout và retry

Nếu A giữ khóa hàng 1 chờ hàng 2, còn B giữ hàng 2 chờ hàng 1, database có thể phát hiện **deadlock** và buộc một transaction rollback. Ứng dụng cần cho phép giao dịch thất bại, xử lý lỗi phù hợp và retry an toàn khi có lý do.

Các cách giảm rủi ro gồm cập nhật tài nguyên theo một thứ tự nhất quán, giữ transaction ngắn, tạo index hỗ trợ câu lệnh, tránh gọi network lâu trong transaction và thiết kế thao tác có **idempotency key** khi client có thể gửi lại yêu cầu.

## 6. Nối ba nền tảng với JPA

### 6.1. Ánh xạ một quan hệ nhiều–một

Trong SQL, mỗi đơn có **customer_id**. Trong Java/JPA, đây có thể là một tham chiếu **Customer**:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(name = "placed_at", nullable = false)
    private java.time.Instant placedAt;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Version
    private Long version;

    protected PurchaseOrder() { }

    public PurchaseOrder(Customer customer, java.time.Instant placedAt) {
        this.customer = java.util.Objects.requireNonNull(customer);
        this.placedAt = java.util.Objects.requireNonNull(placedAt);
        this.status = OrderStatus.NEW;
    }

    public Customer getCustomer() { return customer; }
}

enum OrderStatus { NEW, PAID, CANCELLED }
~~~

**@ManyToOne** là quan hệ hướng đối tượng, **@JoinColumn** chỉ cột FK, **@Version** hỗ trợ optimistic locking. SQL vẫn quyết định ràng buộc FK và uniqueness thực tế. Annotation **@Column(nullable=false)** không thay thế migration thêm **NOT NULL** vào schema hiện có.

Nếu bổ sung chiều ngược **Customer.orders**:

~~~java
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders = new ArrayList<>();
~~~

**mappedBy = "customer"** chỉ ra phía kia sở hữu mapping FK. Trong quan hệ hai chiều, code miền dữ liệu nên giữ hai phía tham chiếu nhất quán; chỉ thêm một phần tử vào list phía inverse có thể không cập nhật FK như mong đợi nếu phía owning vẫn chưa được gán.

### 6.2. Các trạng thái của entity và persistence context

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| **New / transient** | Instance mới, chưa được quản lý | **new Customer("An")** |
| **Managed / persistent** | Được quản lý trong persistence context; thay đổi có thể được dirty checking nhận biết | **em.find(Customer.class, 10L)** |
| **Detached** | Đã từng được quản lý nhưng hiện nằm ngoài context đó | Entity sau **em.detach**, **em.clear**, đóng context |
| **Removed** | Đang được đánh dấu xóa trong context | **em.remove(entity)** |

Ví dụ với transaction kiểu **resource-local JPA**:

~~~java
EntityManager em = entityManagerFactory.createEntityManager();
EntityTransaction tx = em.getTransaction();
try {
    tx.begin();
    Customer customer = em.find(Customer.class, 10L); // managed
    customer.rename("Tên mới");                       // dirty checking
    tx.commit(); // provider flush khi cần và commit transaction
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Ví dụ chỉ áp dụng khi ứng dụng tự quản lý **resource-local transaction**. Với **JTA** hoặc framework như Spring, transaction thường do container/transaction manager quản lý; không tự gọi **getTransaction()** trên container-managed EntityManager.

**Dirty checking** nghĩa là ORM phát hiện thay đổi của managed entity và có thể sinh UPDATE khi đồng bộ. Đây không phải cơ chế tự lưu mọi POJO tùy ý: entity detached đổi trạng thái không tự sinh UPDATE trong context đã đóng.

### 6.3. persist(), merge(), remove(), flush() và commit()

- **persist(entity):** đưa entity mới vào quản lý, lên lịch INSERT; không mặc định có INSERT ngay lúc gọi.
- **merge(entity):** sao chép trạng thái một entity detached/new sang **managed instance được trả về**; đối số đầu vào không tự trở thành managed. Khi cần cập nhật, phải hiểu merge thay đổi field nào và các ràng buộc nghiệp vụ.
- **remove(managedEntity):** đánh dấu xóa; SQL DELETE có thể đến ở flush.
- **flush():** đồng bộ các thay đổi đang chờ từ persistence context xuống DB bằng SQL **trong transaction hiện tại**; không có nghĩa dữ liệu đã commit.
- **commit():** hoàn tất transaction (thường yêu cầu flush trước khi commit); sau commit, thay đổi mới có hiệu lực bền vững theo đảm bảo của DB.

~~~text
new Entity ──persist──> managed ──flush──> INSERT/UPDATE gửi vào DB
                           │
                           └──commit──> transaction hoàn tất

                 rollback: các thay đổi DB của transaction bị hủy;
                 trạng thái object trong bộ nhớ không tự “quay về” như cũ.
~~~

Một câu query có thể kích hoạt flush trước khi chạy, tùy **FlushMode**, provider và ngữ cảnh. Khóa chính dùng IDENTITY cũng có thể khiến INSERT xảy ra sớm để lấy ID. Do đó không nên lập luận rằng “chỉ commit mới gửi SQL”; điều cần phân biệt là **thời điểm phát SQL** và **thời điểm commit**.

Khi rollback, không nên tiếp tục tái sử dụng entity/context đang mang trạng thái thay đổi mà coi như hoàn toàn sạch. Tạo transaction mới và nạp lại dữ liệu khi cần.

### 6.4. Fetch, N+1 và số câu SQL thực sự

Giả sử lấy 100 đơn hàng rồi trong vòng lặp truy cập **order.getCustomer().getName()**:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "select o from PurchaseOrder o", PurchaseOrder.class
).getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
~~~

Nếu quan hệ lazy và mỗi order trỏ tới customer khác nhau, ORM có thể phát **1 truy vấn đơn hàng + nhiều truy vấn customer**: một dạng **N+1 query**. Số truy vấn thực tế phụ thuộc dữ liệu, cache, batch fetching và provider.

Đối với màn hình cần cả tên khách, có thể chọn projection hoặc **JOIN FETCH** có chủ đích:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "select o from PurchaseOrder o join fetch o.customer",
    PurchaseOrder.class
).getResultList();
~~~

Không biến mọi mapping thành EAGER để “chữa” N+1. Cần chọn dữ liệu cho **từng use case**, xem SQL/log/profiler và chú ý join fetch nhiều collection có thể nhân số dòng, làm sai/khó phân trang.

### 6.5. Ranh giới transaction trong service

Đặt transaction quanh nghiệp vụ cần nhất quán, ví dụ “tạo đơn + tạo các dòng hàng + trừ tồn kho”. Trong ứng dụng Spring, có thể dùng **@Transactional** ở service:

~~~java
@Service
public class CheckoutService {
    private final OrderRepository orders;
    private final StockRepository stock;

    public CheckoutService(OrderRepository orders, StockRepository stock) {
        this.orders = orders;
        this.stock = stock;
    }

    @Transactional
    public void checkout(CreateOrderCommand command) {
        stock.reserveFor(command.items()); // phải kiểm tra xung đột/tồn kho
        orders.save(PurchaseOrder.from(command));
    }
}
~~~

Đây là **mã minh họa cấu trúc**, không phải implementation hoàn chỉnh: **CreateOrderCommand**, **OrderRepository**, **StockRepository** và factory **from** do ứng dụng tự định nghĩa. Spring **@Transactional** là cơ chế framework bên ngoài đặc tả JPA. Rollback mặc định của Spring cho exception nào, propagation, self-invocation và việc gọi qua proxy cần được hiểu khi triển khai.

Khi transaction liên quan gửi email, HTTP hoặc thanh toán qua dịch vụ ngoài, một DB transaction đơn lẻ không thể rollback tác động ở hệ thống khác. Có thể cần **outbox pattern**, **idempotency** hoặc quy trình bù trừ, thay vì giữ transaction mở trong thời gian gọi mạng.

## 7. Những nhầm lẫn cần gỡ trước khi học ORM nâng cao

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Gọi save là đã commit.” | Save/persist có thể chỉ đổi trạng thái quản lý; SQL, flush và commit có mốc khác nhau. |
| “Đã có @Column(nullable=false) là DB chắc chắn có NOT NULL.” | Cần migration/schema thật sự tạo constraint. |
| “Quan hệ Java là một cột lưu nguyên object.” | Thường là FK hoặc bảng nối trong mô hình quan hệ. |
| “Mọi collection đều giữ thứ tự như khi SELECT.” | Không có ORDER BY/mapping thứ tự thì thứ tự không được đảm bảo. |
| “LAZY luôn chỉ tốn một SQL.” | Truy cập lazy có thể tạo SQL bổ sung và N+1. |
| “Transaction xong là mọi object tự cập nhật theo DB.” | Persistence context có quy tắc quản lý trạng thái riêng; rollback không tự phục hồi field Java. |
| “REPEATABLE READ luôn xử lý mọi race condition.” | Cần xem database, cơ chế khóa, snapshot và bất biến nghiệp vụ. |
| “@Version ngăn mọi người sửa cùng lúc.” | Nó phát hiện xung đột ghi theo version; ứng dụng vẫn phải xử lý retry hoặc báo lỗi. |
| “Cascade là cách chữa lỗi FK khi xóa.” | Cascade liên quan vòng đời entity; quyết định xóa phải dựa trên ownership và quy tắc dữ liệu. |
| “ORM giúp không cần biết SQL.” | Muốn đúng và nhanh vẫn phải hiểu JOIN, index, constraint, transaction và truy vấn được sinh ra. |

## 8. Bài thực hành kết nối Java – SQL – transaction

### Bài 1: Đọc mô hình và phát hiện ràng buộc

Với ba bảng **customers**, **purchase_orders**, **order_items** ở trên, hãy xác định:

1. Bảng nào nằm ở phía “nhiều” của quan hệ Customer–Order và Order–Item?
2. Vì sao **order_items.unit_price** cần lưu riêng, dù hệ thống còn bảng product có giá hiện tại?
3. Constraint nào bảo đảm **quantity > 0**? Constraint nào bảo đảm một item không trỏ tới order không tồn tại?
4. Khi xóa customer còn order, database phản ứng thế nào nếu không cấu hình cascade?

Gợi ý: FK nằm ở **purchase_orders** và **order_items**; đơn giá là snapshot lịch sử; CHECK và FOREIGN KEY đảm bảo hai điều kiện; database thường từ chối xóa hàng cha còn bị FK tham chiếu.

### Bài 2: Viết SQL cho một màn hình

Yêu cầu: trả về 20 đơn mới nhất của khách hàng 10, gồm ID đơn, thời điểm đặt, số dòng hàng và tổng số tiền tính từ **quantity × unit_price**. Hãy suy nghĩ vì sao LEFT JOIN cần thiết để đơn chưa có dòng vẫn xuất hiện.

~~~sql
SELECT
    o.id,
    o.placed_at,
    COUNT(i.id) AS item_count,
    COALESCE(SUM(i.quantity * i.unit_price), 0) AS total_amount
FROM purchase_orders AS o
LEFT JOIN order_items AS i ON i.order_id = o.id
WHERE o.customer_id = 10
GROUP BY o.id, o.placed_at
ORDER BY o.placed_at DESC, o.id DESC
LIMIT 20;
~~~

Trong PostgreSQL, **COALESCE** thay null của SUM khi không có item bằng 0; **COUNT(i.id)** bằng 0 cho đơn không có item. Nếu số order rất lớn, cân nhắc chọn trước 20 order rồi mới aggregate để tránh tính toán trên quá nhiều order; cần đánh giá bằng kế hoạch thực thi.

### Bài 3: Phân tích lịch sử hai giao dịch

Tồn kho ban đầu là 1. T1 và T2 cùng đọc stock = 1, rồi cả hai thử đặt hàng. Hãy so sánh:

**Cách A:** đọc stock, kiểm tra trong Java, cuối cùng ghi stock = 0.  
**Cách B:** thực thi **UPDATE products SET stock=stock-1 WHERE id=? AND stock>=1** và chỉ tạo đơn nếu row count bằng 1.

Cách A có nguy cơ cả hai chấp nhận đơn nếu không có khóa/version. Cách B cho phép database quyết định cập nhật có điều kiện một cách nguyên tử trên hàng đó; chỉ một transaction có thể trừ từ 1 xuống 0. Vẫn cần gộp UPDATE với việc tạo đơn vào cùng transaction và xử lý kết quả thất bại rõ ràng.

### Bài 4: Dự đoán thời điểm ghi SQL

Trong một resource-local JPA transaction:

~~~java
tx.begin();
Customer customer = new Customer("Lan");
em.persist(customer);
customer.rename("Lan Anh");
em.flush();
tx.rollback();
~~~

Hãy trả lời: entity có thể đã được INSERT trước khi gọi flush không? flush có đồng nghĩa commit không? Sau rollback, giá trị tên trong object Java có tự quay lại “Lan” không?

Đáp án: INSERT **có thể** được gửi sớm tùy chiến lược ID/provider; flush không phải commit; rollback hủy thay đổi DB của transaction nhưng không tự biến đổi ngược trạng thái field trong object Java.

## 9. Lộ trình dùng kiến thức này khi học JPA

Khi bắt đầu một tính năng có lưu dữ liệu, nên đi theo trình tự tư duy:

1. **Mô tả invariant nghiệp vụ:** điều gì luôn phải đúng, kể cả khi có hai request đồng thời?
2. **Thiết kế schema:** bảng, PK, FK, UNIQUE, NOT NULL, CHECK, và index theo truy vấn thực tế.
3. **Thiết kế object model:** entity nào có identity và vòng đời riêng; quan hệ nào cần hai chiều; kiểu dữ liệu Java nào thể hiện đúng ngữ nghĩa.
4. **Đặt transaction boundary:** các thay đổi nào phải commit hoặc rollback cùng nhau; khi nào cần optimistic/pessimistic locking.
5. **Viết mapping và query:** chọn persist/merge khi phù hợp, kiểm soát fetch, dùng tham số, tránh N+1.
6. **Quan sát hệ thống:** xem SQL phát sinh, số statement, row count, kế hoạch truy vấn, rollback, deadlock và hành vi khi có xung đột.

Nắm được nền tảng này sẽ giúp các khái niệm tiếp theo như **owning side**, **cascade**, **dirty checking**, **JPQL**, **flush mode**, **entity graph**, **optimistic locking** và **transaction propagation** trở thành những quyết định có cơ sở, thay vì những annotation cần thử ngẫu nhiên.
