# Phân biệt `insertable`, `updatable` và ràng buộc dữ liệu thực tế

> **Chủ đề:** Data Persistence – Relational Access, ORM, JPA  
> **Nhóm kiến thức:** Ánh xạ thuộc tính

Khi ánh xạ thuộc tính Java vào cột của cơ sở dữ liệu quan hệ bằng JPA, ba khái niệm rất dễ bị đánh đồng:

1. **ORM có đưa cột vào câu lệnh SQL INSERT hay UPDATE không?**
2. **Một đối tượng Java có được phép thay đổi giá trị của thuộc tính không?**
3. **Cơ sở dữ liệu có chấp nhận hoặc bảo vệ một giá trị theo quy tắc nghiệp vụ không?**

Hai thuộc tính **`insertable`** và **`updatable`** chỉ trực tiếp trả lời câu hỏi thứ nhất. Chúng là lựa chọn **ánh xạ cột trong những câu SQL do JPA provider sinh ra**, không phải cơ chế phân quyền sửa dữ liệu và cũng không tự động tạo ràng buộc toàn vẹn ở database.

Ví dụ:

~~~java
@Column(name = "created_at", insertable = false, updatable = false)
private Instant createdAt;
~~~

Khai báo trên yêu cầu JPA không dùng ánh xạ **`createdAt`** để ghi cột **`created_at`** khi sinh INSERT hoặc UPDATE thông thường. Nó **không** bảo đảm cột đó được database tự cấp giá trị, **không** cấm code gọi setter, và **không** cấm người có quyền thực thi SQL cập nhật cột.

Bài học này phân tích chính xác chức năng của các cờ mapping, liên hệ với cơ chế dirty checking, giá trị mặc định và cột sinh bởi database, cách tránh hai thuộc tính cùng ghi một cột, cùng những ràng buộc thật sự như **NOT NULL**, **UNIQUE**, **CHECK** và **FOREIGN KEY**. Mục tiêu là đọc mapping JPA và dự đoán được **SQL sẽ ghi cột nào**, **database sẽ làm gì**, cũng như **dữ liệu có thể bị sai ở đâu**.

## 1. Ba lớp quy tắc khác nhau

Xét một entity:

~~~java
@Entity
@Table(name = "accounts")
public class Account {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "account_number", nullable = false, unique = true,
            updatable = false)
    private String accountNumber;

    // Constructor/getter/method nghiệp vụ...
}
~~~

Cùng cột **`account_number`**, có thể tồn tại ba nhóm quy tắc:

| Lớp | Biện pháp | Bảo vệ điều gì? |
|---|---|---|
| **Mapping của ORM** | **`insertable=false`**, **`updatable=false`** | Cột có tham gia SQL INSERT/UPDATE phát sinh từ ánh xạ đó hay không |
| **Logic và validation Java** | Constructor, method nghiệp vụ, Bean Validation như **`@NotBlank`** | Trạng thái entity/input có hợp lệ theo logic ứng dụng hay không |
| **Database schema và quyền** | **NOT NULL**, **UNIQUE**, **CHECK**, **FOREIGN KEY**, trigger, GRANT | Database có chấp nhận thao tác ghi từ bất kỳ client nào hay không |

**`@Column(nullable = false)`** là metadata của mapping, có thể được provider dùng khi sinh DDL. Nếu bảng đang tồn tại và ứng dụng không chạy schema generation/migration, annotation ấy **không tự sửa schema**. Tương tự, **`@Column(unique = true)`** không thay thế việc xác nhận trong database rằng một unique constraint hoặc unique index phù hợp đã được tạo.

Sơ đồ luồng:

~~~mermaid
flowchart LR
    A["Đối tượng Java"] --> B["JPA mapping / dirty checking"]
    B --> C["SQL INSERT / UPDATE"]
    C --> D["Database: default, constraint, trigger, quyền"]
    D --> E[("Dữ liệu được commit hoặc giao dịch thất bại")]
~~~

Mỗi lớp có phạm vi riêng. Khi một giá trị không hợp lệ bị chặn ở Java, trải nghiệm lỗi có thể dễ hiểu hơn. Khi constraint tồn tại ở database, dữ liệu còn được bảo vệ nếu ghi qua batch, native SQL, script migration, công cụ quản trị hoặc ứng dụng khác.

## 2. `insertable` và `updatable` định nghĩa điều gì?

Hai thuộc tính được khai báo phổ biến trên **`@Column`** và **`@JoinColumn`** (cùng những mapping cột tương ứng).

- **`insertable`**: cột có được đưa vào câu lệnh **SQL INSERT** do persistence provider sinh ra từ mapping này hay không. Giá trị mặc định là **`true`**.
- **`updatable`**: cột có được đưa vào câu lệnh **SQL UPDATE** do persistence provider sinh ra từ mapping này hay không. Giá trị mặc định là **`true`**.

Hai cờ áp dụng cho **khả năng ghi thông qua mapping**. Chúng không làm một thuộc tính biến mất khỏi phép SELECT; không đồng nghĩa với **`@Transient`**; và không thể dùng để kiểm soát mọi SQL tự viết.

### 2.1. Bốn tổ hợp thường gặp

| `insertable` | `updatable` | Hành vi đối với SQL do mapping sinh ra | Ứng dụng điển hình |
|---|---|---|---|
| **true** | **true** | Có thể ghi trong cả INSERT và UPDATE | Thuộc tính thông thường: tên, số lượng, trạng thái |
| **true** | **false** | Cho phép ghi ban đầu; không cập nhật sau đó bằng mapping này | Mã tham chiếu cố định, giá trị chỉ chốt khi tạo |
| **false** | **true** | Bỏ cột khi INSERT; có thể cập nhật về sau | Giá trị khởi tạo bằng database default nhưng có thể sửa sau |
| **false** | **false** | Bỏ cột trong INSERT và UPDATE của mapping này | Cột tính bởi database, thời gian do DB cấp, scalar phụ để đọc FK |

**“Có thể ghi” không có nghĩa ORM chắc chắn gửi cột trong mọi statement.** Với UPDATE, provider có thể chỉ cập nhật những thuộc tính thay đổi hoặc tạo câu SQL có tập cột cố định, tùy provider và cấu hình. Với INSERT, chiến lược ID, dynamic insert, giá trị mặc định và các tối ưu hóa cũng ảnh hưởng câu SQL. Ý nghĩa chính của hai cờ là **cột đủ điều kiện được ghi bằng mapping ấy**, không phải lời hứa về chính xác số lệnh hay thời điểm phát SQL.

### 2.2. Ví dụ đơn giản: ghi lần đầu, khóa cập nhật qua mapping

~~~java
@Entity
@Table(name = "invoices")
public class Invoice {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "invoice_number", nullable = false, unique = true,
            insertable = true, updatable = false)
    private String invoiceNumber;

    @Column(name = "description", nullable = false)
    private String description;

    protected Invoice() {}

    public Invoice(String invoiceNumber, String description) {
        this.invoiceNumber = invoiceNumber;
        this.description = description;
    }

    public void changeDescription(String description) {
        this.description = description;
    }
}
~~~

Giả sử đối tượng mới được persist:

~~~java
Invoice invoice = new Invoice("INV-2026-001", "Gói phần mềm");
em.persist(invoice);
~~~

SQL minh họa:

~~~sql
INSERT INTO invoices (invoice_number, description)
VALUES ('INV-2026-001', 'Gói phần mềm');
~~~

Khi sửa **`description`**, provider có thể phát UPDATE:

~~~sql
UPDATE invoices
SET description = 'Gia hạn gói phần mềm'
WHERE id = 1;
~~~

Cột **`invoice_number`** không được cập nhật qua mapping này vì **`updatable=false`**. Nếu code Java vẫn đổi giá trị của field bằng reflection, setter, mapping DTO hoặc logic nội bộ, object có thể chứa một giá trị **khác với dữ liệu database**. Không nên xem cờ này là phương thức thiết lập bất biến nghiệp vụ hoàn chỉnh.

### 2.3. `insertable=false` không có nghĩa “không có giá trị”

~~~java
@Column(name = "created_at", insertable = false, updatable = false)
private Instant createdAt;
~~~

Nếu database định nghĩa:

~~~sql
created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
~~~

thì khi ORM bỏ cột **`created_at`** khỏi INSERT, database có thể áp dụng default để tạo timestamp. Nhưng nếu cột trong bảng thật là **`created_at TIMESTAMP ... NOT NULL`** và không có default/trigger/giá trị nguồn khác, INSERT có thể thất bại vì vi phạm **NOT NULL**.

Một cờ mapping không tự sinh ra một giá trị hợp lệ. Cần xác định **ai là người cấp giá trị**: ứng dụng, database default, trigger hay tính toán ở database.

## 3. Phân biệt “không gửi cột” với “gửi giá trị NULL”

Đây là điểm then chốt khi dùng database default.

~~~sql
CREATE TABLE jobs (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    state VARCHAR(20) NOT NULL DEFAULT 'PENDING'
);
~~~

Hai câu lệnh không tương đương:

~~~sql
-- Bỏ cột state: database được phép áp dụng DEFAULT 'PENDING'.
INSERT INTO jobs DEFAULT VALUES;

-- Ghi NULL tường minh: vi phạm NOT NULL, không dùng DEFAULT.
INSERT INTO jobs (state) VALUES (NULL);
~~~

Tương tự, khi column không có **NOT NULL**, cách thứ hai có thể lưu thật giá trị **NULL** thay vì **PENDING**. Nếu mục tiêu là để database cấp default, phải bảo đảm ORM **không gửi cột** (ví dụ bằng **`insertable=false`** đối với mapping đó hoặc cơ chế dynamic insert được cấu hình đúng).

Ví dụ entity:

~~~java
@Entity
@Table(name = "jobs")
public class Job {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "state", insertable = false)
    private String state;

    protected Job() {}

    public String getState() { return state; }
    public void changeState(String newState) { this.state = newState; }
}
~~~

Với mapping này:

- INSERT do JPA sinh ra không ghi **`state`** từ field đó, cho phép DB default hoạt động.
- UPDATE sau này **có thể ghi** **`state`** vì **`updatable`** mặc định là true.
- Ngay sau **`persist()`**, field Java **không nhất thiết được tự điền `"PENDING"`**. Database đã có giá trị nhưng object trong persistence context có thể còn null cho đến khi được đọc lại/refresh hoặc được provider đồng bộ cột generated phù hợp.
- Gọi **`changeState("RUNNING")`** trước khi object nhận lại default có thể vẫn dẫn tới UPDATE theo quy tắc provider. Cần thiết kế lifecycle rõ ràng nếu sau INSERT sẽ tiếp tục xử lý.

**`@ColumnDefault`** của Hibernate là một cơ chế vendor-specific giúp diễn đạt default trong DDL do Hibernate sinh; chỉ dùng **`@ColumnDefault`** không nhất thiết khiến provider bỏ cột khỏi INSERT. Còn **`@DynamicInsert`** của Hibernate là một tối ưu/chiến lược khác, ảnh hưởng cách sinh INSERT dựa trên giá trị thuộc tính. Không coi các annotation Hibernate này là các thuộc tính chuẩn của JPA.

## 4. Cơ sở dữ liệu cấp giá trị: default, trigger và generated column

Có nhiều nguồn sinh dữ liệu, và mỗi nguồn nên được mapping có chủ đích.

### 4.1. Giá trị mặc định tại thời điểm INSERT

~~~sql
CREATE TABLE documents (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lifecycle_state VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
);
~~~

Một mapping phù hợp khi database sở hữu thời gian tạo:

~~~java
@Column(name = "created_at", insertable = false, updatable = false)
private Instant createdAt;
~~~

Nếu ứng dụng muốn đổi **`lifecycle_state`** sau đó nhưng để database tạo giá trị ban đầu:

~~~java
@Column(name = "lifecycle_state", insertable = false, updatable = true)
private String lifecycleState;
~~~

Đừng giả định trường đã chứa giá trị DB default ngay sau khi gọi **`em.persist()`**. Một cách đọc lại sau khi INSERT đã được phát:

~~~java
em.persist(document);
em.flush();    // INSERT đã được gửi; không đồng nghĩa COMMIT.
em.refresh(document); // Nạp lại trạng thái từ DB trong transaction.
~~~

**`refresh()`** đòi hỏi entity được quản lý và context/transaction phù hợp. Nó làm thay đổi trạng thái object để khớp database và có thể ghi đè các thay đổi chưa được flush; không nên lạm dụng cho mọi lần persist. Một số provider hỗ trợ đọc giá trị sinh ra ngay lúc INSERT/UPDATE bằng cơ chế chuyên biệt, giúp tránh một câu SELECT riêng.

### 4.2. Cột do database tính toán

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19, 2) NOT NULL CHECK (unit_price >= 0),
    line_total NUMERIC(19, 2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED
);
~~~

Entity:

~~~java
@Entity
@Table(name = "order_lines")
public class OrderLine {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private Integer quantity;

    @Column(name = "unit_price", nullable = false, precision = 19, scale = 2)
    private BigDecimal unitPrice;

    @Column(name = "line_total", insertable = false, updatable = false,
            precision = 19, scale = 2)
    private BigDecimal lineTotal;

    protected OrderLine() {}
    // Constructor, getter và method cập nhật quantity/unitPrice...
}
~~~

**`line_total`** là cột DB tính từ hai cột khác. Không nên đưa nó vào INSERT/UPDATE do ORM sinh ra vì PostgreSQL không cho ghi tùy ý vào generated column. Khi **quantity** hoặc **unit_price** thay đổi, database cập nhật **line_total** theo định nghĩa của cột, còn **`lineTotal`** trong object Java có thể đang là giá trị cũ cho tới khi refresh hoặc đọc trong persistence context mới.

Nếu cần dùng **lineTotal** ngay trong quá trình nghiệp vụ trước khi flush, có thể tính giá trị trên Java theo cùng quy tắc hoặc dùng query/projection đọc từ DB. Việc “đọc sau khi database cập nhật” và “tính trong bộ nhớ trước commit” là hai yêu cầu khác nhau.

### 4.3. Trigger cập nhật thời điểm sửa

Một số hệ thống để database tự đặt **`updated_at`** qua trigger mỗi khi UPDATE. Khi ấy có thể dùng:

~~~java
@Column(name = "updated_at", insertable = false, updatable = false)
private Instant updatedAt;
~~~

Ví dụ giả lập hành vi:

~~~text
Java đổi description
    ↓
JPA gửi UPDATE description = ...
    ↓
DB trigger tự ghi updated_at = thời điểm hiện tại
    ↓
DB có updated_at mới; object Java có thể còn giá trị cũ
~~~

Không phải hệ quản trị database nào cũng có cú pháp trigger giống nhau; trigger phải được tạo bằng migration/DDL thật. Nếu JPA cũng tự ghi **`updated_at`** qua một annotation hoặc callback mà DB trigger lại chỉnh tiếp, cần quyết định rõ **một nguồn sở hữu chính** và hiểu thứ tự thực thi.

### 4.4. Giá trị sinh ở Java khác giá trị sinh ở DB

Một lựa chọn khác là ứng dụng tự gán:

~~~java
@PrePersist
void onCreate() {
    createdAt = Instant.now();
}

@PreUpdate
void onUpdate() {
    updatedAt = Instant.now();
}
~~~

Khi dùng callback kiểu này, các cột cần được mapping cho phép ghi nếu muốn callback tác động vào SQL. **`@PrePersist`** và **`@PreUpdate`** chạy trong vòng đời JPA phù hợp; chúng không tự đảm bảo các thao tác SQL từ bên ngoài ứng dụng sẽ đặt timestamp, và không thay thế trigger ở database.

Chọn một chiến lược có chủ đích:

| Người sở hữu giá trị | Mapping thường gặp | Nguồn sinh | Điều cần chú ý |
|---|---|---|---|
| Java/application | `insertable=true, updatable=true` khi có thể đổi | Constructor, service, callback | Đồng bộ đồng hồ, đường ghi ngoài JPA |
| Database default khi tạo | `insertable=false` | DEFAULT trong schema | Object chưa chắc biết giá trị ngay sau INSERT |
| Database trigger | Thường `insertable=false, updatable=false` | Trigger DB | Phải nạp lại giá trị khi cần |
| Database generated column | `insertable=false, updatable=false` | Biểu thức generated column | Không cập nhật trực tiếp, có nguy cơ state Java cũ |
| Provider tự quản lý | Tùy loại mapping (ví dụ `@Version`) | JPA provider | Tuân thủ API/đặc tả riêng, không tự khóa việc ghi cột bằng cờ sai mục đích |

## 5. `insertable` và `updatable` liên quan dirty checking ra sao?

JPA quản lý entity trong một **persistence context**. Khi một entity đang **managed**, provider theo dõi trạng thái và có thể phát SQL UPDATE ở lần **flush**. Nhưng **thay đổi field** và **việc đưa field vào UPDATE** là hai chuyện khác nhau.

Ví dụ:

~~~java
@Column(name = "external_ref", updatable = false)
private String externalRef;

@Column(name = "display_name")
private String displayName;
~~~

Trong một transaction:

~~~java
Customer customer = em.find(Customer.class, 42L);
customer.setExternalRef("NEW-REF");
customer.setDisplayName("Tên hiển thị mới");
em.flush();
~~~

Nếu không có mapping nào khác ghi **`external_ref`**, SQL UPDATE cho entity có thể chứa **`display_name`** nhưng không chứa **`external_ref`**. Field **`externalRef`** ở Java vẫn có thể hiển thị **`NEW-REF`** trong cùng persistence context, dù database giữ giá trị cũ.

Điều này dẫn đến các hệ quả:

1. **Không dùng `updatable=false` để thay thế thiết kế API bất biến.** Không expose setter công khai nếu không muốn code đổi field; cân nhắc class/aggregate method chỉ cho phép thay đổi hợp lệ.
2. **Không dùng field read-only để ra quyết định dựa trên việc cập nhật mà ORM không ghi.** Trong context hiện tại, giá trị object và DB có thể lệch nhau.
3. **`flush()` không đồng nghĩa `commit()`.** SQL có thể đã chạy nhưng transaction còn có thể rollback.
4. **Provider có thể dùng cache và identity map.** Gọi **`find()`** lần nữa trong cùng context có thể trả về đúng object đang managed, không truy vấn lại DB.
5. **`refresh()`** hoặc đọc lại trong context mới giúp quan sát giá trị đã ghi vào database, khi đã thỏa những điều kiện transaction và visibility tương ứng.

### 5.1. Mốc thời gian quan trọng

~~~text
new Entity
   │
   ├─ persist(entity) ──> entity được quản lý
   │
   ├─ INSERT có thể xảy ra lúc persist, flush hoặc thời điểm provider cần
   │                        └─ insertable=false => bỏ cột khỏi INSERT tương ứng
   │
managed Entity
   │
   ├─ thay đổi field Java
   │
   ├─ flush / phát UPDATE ──> updatable=false => bỏ cột khỏi UPDATE tương ứng
   │
   └─ commit / rollback ──> quyết định kết quả transaction
~~~

Với **`GenerationType.IDENTITY`**, provider thường phải INSERT sớm để lấy khóa chính. Với các chiến lược khác, thời điểm phát SQL có thể khác. Không viết logic dựa trên giả định mọi INSERT chờ tới commit hoặc cứ gọi save là SQL đã hoàn tất.

### 5.2. Detached entity và `merge()`

**`em.merge(detached)`** sao chép trạng thái của đối tượng vào một managed instance và trả về instance đó. Cờ **`updatable=false`** tiếp tục điều chỉnh việc ghi cột trong SQL UPDATE từ mapping, chứ không phải quy tắc “field này không bao giờ được sao chép vào object”.

~~~java
Customer managed = em.merge(detachedCustomer);
// Không giả định managed.externalRef khớp DB nếu field updatable=false
// nhưng detachedCustomer đã thay đổi giá trị đó.
~~~

Điều này đặc biệt quan trọng khi nhận request JSON rồi map trực tiếp toàn bộ field vào entity: dùng DTO chứa danh sách field được phép sửa và service method rõ ràng sẽ giảm nguy cơ một thuộc tính “không cập nhật bằng JPA” nhưng lại bị thay đổi trong state Java rồi xuất hiện trong response.

### 5.3. JPQL bulk update và native SQL đi theo đường khác

~~~java
em.createQuery(
    "update Customer c set c.externalRef = :ref where c.id = :id")
    .setParameter("ref", "OVERRIDE")
    .setParameter("id", 42L)
    .executeUpdate();
~~~

**JPQL bulk UPDATE**, **CriteriaUpdate** và native SQL là những thao tác khác với dirty checking thông thường từng entity. Cờ **`updatable=false`** không nên được xem như cơ chế phân quyền chặn mọi DML; hành vi SQL hợp lệ và cách provider xử lý các đường ghi chuyên biệt phải được xác minh. Bulk DML cũng thường **không đồng bộ ngay các managed entity đang nằm trong persistence context**.

~~~sql
UPDATE customers SET external_ref = 'OVERRIDE' WHERE id = 42;
~~~

Database vẫn có thể cho câu SQL này chạy nếu người gọi có quyền, không vướng constraint/trigger. Muốn ngăn thay đổi thật sự, cần quy định nghiệp vụ, quyền truy cập và ràng buộc/trigger tại DB; cờ mapping của JPA không làm việc thay những cơ chế đó.

## 6. `@JoinColumn`: các cờ tương tự áp dụng cho khóa ngoại

Khi một entity tham chiếu entity khác qua FK, JPA dùng **`@JoinColumn`** để định nghĩa cột liên kết. Trên **`@ManyToOne`** hoặc phía sở hữu **`@OneToOne`**, hai cờ có ý nghĩa gần tương tự:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false,
            insertable = true, updatable = true)
private Customer customer;
~~~

Mapping này có quyền sử dụng **`customer_id`** làm cột FK trong SQL INSERT/UPDATE của entity chứa quan hệ. **`optional=false`** thể hiện tính bắt buộc trong mô hình quan hệ JPA, còn **`nullable=false`** là metadata của join column; để DB thật sự chặn null/các ID không tồn tại, schema cần **NOT NULL** và **FOREIGN KEY**.

### 6.1. Hai thuộc tính cùng ánh xạ một cột: tránh ghi trùng

Đôi khi service cần vừa có đối tượng **Customer**, vừa truy cập trực tiếp **customerId** mà không buộc phải dereference một quan hệ lazy.

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer; // Mapping ghi FK

    @Column(name = "customer_id", insertable = false, updatable = false)
    private Long customerId;  // Mapping chỉ đọc FK

    protected PurchaseOrder() {}

    public PurchaseOrder(Customer customer) {
        this.customer = Objects.requireNonNull(customer);
    }

    public Long getCustomerId() { return customerId; }
    public Customer getCustomer() { return customer; }
}
~~~

Với mapping trên, **`customer`** là phía ghi cột **`customer_id`**, còn **`customerId`** chỉ đọc cùng cột qua một ánh xạ scalar. Khi INSERT, provider dùng ID của **`customer`** để điền FK. Việc đánh dấu cặp **`insertable=false, updatable=false`** cho mapping scalar tránh trường hợp provider thấy hai mapping cùng cố ghi một physical column.

Nếu cả hai mapping đều ghi cột **`customer_id`**, nhiều provider như Hibernate thường báo lỗi cấu hình **repeated column mapping**. Đánh dấu một mapping chỉ đọc là giải pháp phổ biến.

**Chú ý trạng thái trong bộ nhớ:** sau khi gán **`customer`**, field **`customerId`** không nhất thiết cập nhật ngay. Đổi tham chiếu **`customer`** trong transaction cũng không tự đồng bộ scalar field; refresh hoặc reload có thể cần thiết nếu UI cần giá trị mới ngay. Nếu chỉ cần ID của quan hệ, một phương án khác là lấy **`customer.getId()`** khi có thể thực hiện mà không kích hoạt hành vi lazy không mong muốn, tùy provider và trạng thái entity.

### 6.2. Đổi vai trò ghi: scalar quản lý FK, quan hệ chỉ đọc

Cũng có thể chọn:

~~~java
@Column(name = "customer_id", nullable = false)
private Long customerId; // Mapping ghi FK

@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id", insertable = false, updatable = false)
private Customer customer; // Tham chiếu chỉ đọc
~~~

Khi ấy muốn đổi FK, code phải đổi **`customerId`**, không chỉ gán object **`customer`**. Sau khi sửa scalar ID, object **`customer`** đang được cache/loaded trong persistence context có thể vẫn trỏ tới khách hàng cũ. Đừng dùng cả hai cách viết trong cùng entity mà không có một quy tắc ownership rõ ràng.

Thông thường nên **chọn association là mapping chính** và chỉ thêm ID scalar read-only khi có nhu cầu thực sự. Nếu ứng dụng chủ yếu thao tác bằng ID không cần graph quan hệ, mapping scalar đơn thuần cũng có thể là một lựa chọn; lúc đó không nhất thiết phải khai báo association.

### 6.3. `mappedBy` không phải là `updatable=false`

Trong quan hệ hai chiều:

~~~java
@Entity
public class Customer {
    @Id
    private Long id;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();
}
~~~

**`mappedBy`** cho biết **phía inverse** của relationship. Phía **`PurchaseOrder.customer`** quản lý FK **`customer_id`**; chỉ thêm một order vào collection **`Customer.orders`** mà không đặt **`order.customer`** đúng sẽ không bảo đảm FK được cập nhật.

**`insertable=false, updatable=false`** lại điều khiển khả năng ghi của **một mapping cột/join column**, kể cả khi không tồn tại quan hệ hai chiều. Hai cơ chế khác nhau về ý nghĩa và phạm vi.

### 6.4. Khóa ngoại tổng hợp và shared primary key

Với FK gồm nhiều cột, JPA có thể dùng **`@JoinColumns`**. Các thuộc tính insertable/updatable phải được xem xét nhất quán cho từng cột; nếu một trong các cột cũng nằm trong **`@EmbeddedId`**, khả năng ghi trùng phải được xử lý ở thiết kế key.

Với quan hệ dùng chung khóa chính, **`@MapsId`** thường diễn đạt đúng hơn việc đặt nhiều **`insertable=false, updatable=false`** tùy tiện. **`@MapsId`** cho phép association cung cấp một phần hoặc toàn bộ khóa định danh của entity. Khi khóa là ID được quản lý bởi provider hoặc lấy từ association, không nên sửa cờ insert/update của **`@Id`** chỉ để “chữa lỗi duplicate column” mà chưa hiểu ownership và quá trình tạo khóa.

## 7. Ràng buộc dữ liệu thực tế phải tồn tại ở schema

Một mapping trông có vẻ chặt chẽ trên Java không đồng nghĩa bảng đã có các constraint.

Giả sử entity:

~~~java
@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 64,
            updatable = false)
    private String sku;

    @Column(name = "price", nullable = false, precision = 19, scale = 2)
    private BigDecimal price;

    @Column(name = "stock", nullable = false)
    private Integer stock;
}
~~~

Để database bảo vệ dữ liệu khi có nhiều tiến trình cùng ghi, schema nên được định nghĩa có chủ đích, ví dụ PostgreSQL:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(64) NOT NULL UNIQUE,
    price NUMERIC(19, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0)
);
~~~

### 7.1. `nullable=false` và `NOT NULL`

- **`@Column(nullable=false)`** diễn tả metadata cho cột; provider có thể dùng để sinh DDL hoặc thực hiện một số kiểm tra tùy cấu hình.
- **`NOT NULL`** thật sự ở database chặn các thao tác ghi null bất kể người ghi là JPA, JDBC, ETL hay công cụ quản trị.
- **`@Basic(optional=false)`** thể hiện tính bắt buộc ở mức mapping của basic attribute và có thể ảnh hưởng schema generation, nhưng không thay thế NOT NULL đã được áp dụng trong DB.
- **`@NotNull`** của Bean Validation là một quy tắc validation ở ứng dụng nếu validation được kích hoạt; nó không đương nhiên trở thành constraint vật lý trong mọi hệ thống.

Một cột có NOT NULL vẫn có thể nhận chuỗi rỗng **`''`**. Nếu nghiệp vụ không cho phép SKU chỉ có dấu cách, cần validation như **`@NotBlank`**, đồng thời cân nhắc CHECK/normalization ở DB nếu cần chống mọi nguồn ghi.

### 7.2. `unique=true` và `UNIQUE`

~~~java
@Column(name = "email", nullable = false, unique = true)
private String email;
~~~

Annotation là metadata tiện dụng cho một ràng buộc duy nhất trên một cột, nhưng **unique constraint/index được tạo thật tại DB** mới chống được hai transaction đồng thời cùng ghi email trùng.

Kiểm tra trước trong Java:

~~~java
if (!repository.existsByEmail(email)) {
    repository.save(new Customer(email));
}
~~~

không thể bảo đảm duy nhất khi hai request chạy đồng thời:

~~~text
T1: existsByEmail("a@example.com") -> false
T2: existsByEmail("a@example.com") -> false
T1: INSERT thành công
T2: INSERT -> phải bị DB UNIQUE từ chối
~~~

Ứng dụng nên bắt và xử lý lỗi unique constraint ở lớp phù hợp để trả thông báo nghiệp vụ chính xác. Chi tiết mã lỗi và tên exception phụ thuộc JDBC provider/JPA provider/framework.

Với unique gồm nhiều cột, định nghĩa constraint ở cấp bảng:

~~~java
@Table(
    name = "order_items",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_order_item_order_sku",
        columnNames = {"order_id", "sku"}
    )
)
~~~

Và bảo đảm database có constraint tương ứng thông qua migration. Đừng tưởng **`unique=true`** trên mỗi cột riêng biệt biểu diễn uniqueness của **cặp giá trị**: cách đó sẽ làm mỗi cột phải duy nhất riêng.

### 7.3. `length`, `precision`, `scale` và giới hạn dữ liệu

~~~java
@Column(length = 64)
private String sku;

@Column(precision = 19, scale = 2)
private BigDecimal amount;
~~~

- **`length`** là metadata độ dài cột chuỗi khi sinh DDL; không đảm bảo mọi DB sẽ chặn vượt độ dài giống nhau, và không thay thế validation input.
- **`precision`** là tổng số chữ số thập phân của kiểu numeric; **`scale`** là số chữ số sau dấu thập phân.
- Với tiền, dùng **`BigDecimal`** để tránh sai số nhị phân của **`double`**. Quy tắc làm tròn cần được quyết định rõ ở nghiệp vụ.
- **`@Size(max=64)`** và **`@Digits(integer=..., fraction=...)`** của Bean Validation có thể hỗ trợ thông báo lỗi sớm nhưng vẫn cần thiết kế cột thật chính xác.

Không có **`@Column(precision=19, scale=2)`** nào thay thế được **CHECK(amount >= 0)**. Precision/scale và giá trị không âm là hai nhóm ràng buộc khác nhau.

### 7.4. `CHECK`, `FOREIGN KEY` và các bất biến liên quan

Với dữ liệu đơn hàng:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    total_amount NUMERIC(19, 2) NOT NULL CHECK (total_amount >= 0)
);
~~~

- **FOREIGN KEY** ngăn gán một **customer_id** không tồn tại trong bảng tham chiếu (theo quy tắc constraint).
- **CHECK** giữ tập trạng thái hợp lệ và giá trị tiền không âm.
- **NOT NULL** ngăn tình huống không gán khách hàng/trạng thái.
- **`@JoinColumn(nullable=false)`** giúp mô tả FK trong JPA, nhưng chỉ có một database FK được tạo thật mới bảo vệ được nguồn ghi ngoài ORM.

Không phải mọi bất biến nghiệp vụ đều diễn đạt được bằng một CHECK trên một hàng. Ví dụ “tổng số tiền của các item phải bằng số tiền đơn hàng” hoặc “không được bán quá tồn kho” có thể cần transaction, truy vấn khóa, trigger, thiết kế aggregate và các kiểm tra theo isolation của DB.

## 8. `updatable=false` không làm cột bất biến ở database

Một lỗi thiết kế phổ biến là:

~~~java
@Column(updatable = false)
private String immutableCode;
~~~

rồi kết luận **immutableCode không bao giờ thay đổi**. Kết luận đó không đúng nếu có đường ghi khác:

~~~sql
UPDATE accounts
SET immutable_code = 'OTHER'
WHERE id = 10;
~~~

Câu SQL vẫn có thể thành công nếu người gọi có quyền và không có constraint/trigger nào ngăn sửa. Tương tự, một ứng dụng thứ hai có mapping cho phép UPDATE vẫn có thể sửa giá trị.

Để bảo vệ thực sự một mã không đổi sau khi tạo, nên kết hợp:

1. **Thiết kế domain:** không cung cấp public setter nếu không có nghiệp vụ thay đổi; constructor/factory kiểm tra giá trị đầu vào.
2. **Mapping:** dùng **`updatable=false`** khi muốn JPA không ghi lại mã sau INSERT.
3. **Database:** unique/not-null và, nếu yêu cầu “không đổi” áp dụng cho mọi nguồn ghi, một trigger/policy/quyền thích hợp để chặn UPDATE cột.
4. **Vận hành:** migration và script có quyền cao vẫn có thể thay dữ liệu; cần kiểm soát và audit những thay đổi đặc biệt.

**UNIQUE không có nghĩa immutable.** Unique chỉ ngăn trùng giữa các hàng theo quy tắc DB; cập nhật từ một mã sang mã khác vẫn có thể được phép. **NOT NULL không có nghĩa immutable**; nó chỉ chặn null.

### 8.1. Ví dụ PostgreSQL: trigger ngăn đổi mã sau khi tạo

~~~sql
CREATE OR REPLACE FUNCTION prevent_account_number_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.account_number IS DISTINCT FROM OLD.account_number THEN
        RAISE EXCEPTION 'account_number cannot be changed';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER accounts_account_number_immutable
BEFORE UPDATE ON accounts
FOR EACH ROW
EXECUTE FUNCTION prevent_account_number_change();
~~~

Đây là cú pháp PostgreSQL minh họa cho yêu cầu bất biến trên database. Với RDBMS khác, cú pháp trigger khác. Người có quyền cao có thể thay đổi/tắt trigger theo quyền DB; đó là vấn đề quản trị, không phải chức năng của JPA.

### 8.2. Cột read-only không đồng nghĩa toàn entity read-only

Entity có một field **`updatable=false`** vẫn có thể sửa các field còn lại. Nếu muốn một entity không bao giờ được thay đổi bởi tầng ứng dụng, cần thiết kế immutable aggregate hoặc cơ chế read-only thích hợp của provider/DB, tùy yêu cầu. **`@Immutable`** là annotation đặc thù Hibernate; nó không phải cú pháp JPA chuẩn và cũng không tự thiết lập quyền DB.

## 9. Ràng buộc Java và Bean Validation: vai trò bổ sung

Ví dụ:

~~~java
@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    @Size(max = 120)
    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    @NotBlank
    @Email
    @Column(name = "email", nullable = false, unique = true)
    private String email;
}
~~~

**`@NotBlank`**, **`@Size`**, **`@Email`** thuộc **Jakarta Bean Validation**, ví dụ package **`jakarta.validation.constraints`**, không phải thuộc tính của JPA. Khi validation provider được tích hợp và kích hoạt, validation có thể chạy trước các lifecycle persistence phù hợp để chặn dữ liệu không hợp lệ, thường ném **ConstraintViolationException**. Nhưng không thể chỉ dựa vào validation Java trong hệ thống nhiều đường ghi.

So sánh:

| Quy tắc | Ví dụ | Giới hạn |
|---|---|---|
| Java constructor/method | Không cho tạo Customer với tên rỗng | Không kiểm soát các đường ghi ngoài Java và việc ORM/reflection gán trực tiếp theo mapping |
| Bean Validation | `@NotBlank`, `@Size`, `@Email` | Chỉ áp dụng khi gọi validation/tích hợp được cấu hình; không thay thế database constraints |
| JPA mapping metadata | `nullable=false`, `unique=true`, `updatable=false` | Có thể hỗ trợ DDL/SQL sinh ra, không tự sửa mọi schema hiện hữu |
| Database constraint | `NOT NULL`, `UNIQUE`, `CHECK`, `FOREIGN KEY` | Bảo vệ trên database, nhưng không diễn đạt mọi nghiệp vụ liên bảng |
| Transaction/locking | UNIQUE + transaction, `@Version`, row locking | Bảo vệ hành vi đồng thời tùy thiết kế và isolation |

**`@Email`** kiểm tra hình thức theo validator, không chứng minh email tồn tại hoặc thuộc về người dùng. **`@NotBlank`** chặn các chuỗi chỉ chứa khoảng trắng nhưng cần cân nhắc normalize/collation/case sensitivity ở DB nếu email hay mã SKU phải duy nhất theo cách không phân biệt chữ hoa/thường.

## 10. Tình huống thực tế: đơn hàng có cột do DB sở hữu

Giả sử có yêu cầu:

- **orderCode** do ứng dụng tạo, phải duy nhất và không thay đổi sau khi lưu.
- **customerId** là khóa ngoại trỏ tới khách hàng; quan hệ **Customer** là mapping chính.
- **createdAt** do database cấp bằng CURRENT_TIMESTAMP.
- **status** ban đầu **NEW** do ứng dụng quyết định và có thể thay đổi sau.
- **totalAmount** phải không âm; dùng BigDecimal.

### 10.1. Database schema (ví dụ PostgreSQL)

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(64) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    total_amount NUMERIC(19, 2) NOT NULL CHECK (total_amount >= 0)
);

CREATE INDEX idx_purchase_orders_customer
    ON purchase_orders(customer_id);
~~~

Cần migration tương ứng để đảm bảo các constraint/index thật sự hiện diện. Trên schema cũ có dữ liệu, thêm NOT NULL/CHECK/UNIQUE đôi khi yêu cầu dọn dữ liệu và kế hoạch rollout trước khi chạy migration.

### 10.2. Entity mapping

~~~java
package com.example.orders;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_code", nullable = false, unique = true,
            length = 64, updatable = false)
    private String orderCode;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(name = "customer_id", insertable = false, updatable = false)
    private Long customerId;

    @Column(name = "created_at", nullable = false,
            insertable = false, updatable = false)
    private Instant createdAt;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false, precision = 19, scale = 2)
    private BigDecimal totalAmount;

    protected PurchaseOrder() {}

    public PurchaseOrder(String orderCode, Customer customer, BigDecimal amount) {
        if (orderCode == null || orderCode.isBlank()) {
            throw new IllegalArgumentException("Mã đơn không được trống");
        }
        this.orderCode = orderCode;
        this.customer = Objects.requireNonNull(customer);
        this.totalAmount = Objects.requireNonNull(amount);
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Tổng tiền không được âm");
        }
        this.status = OrderStatus.NEW;
    }

    public Long getId() { return id; }
    public String getOrderCode() { return orderCode; }
    public Long getCustomerId() { return customerId; }
    public Instant getCreatedAt() { return createdAt; }
    public OrderStatus getStatus() { return status; }

    public void markPaid() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException("Chỉ đơn NEW mới chuyển sang PAID");
        }
        status = OrderStatus.PAID;
    }
}

enum OrderStatus { NEW, PAID, CANCELLED }
~~~

Class **Customer** là entity riêng được mapping tới bảng **customers** trong cùng persistence unit; ví dụ giả định nó đã được định nghĩa với **`@Id Long id`**. Các import dùng wildcard chỉ để rút gọn ví dụ. Cách mapping **`Customer`** và quyền tham chiếu phải đúng theo vòng đời dữ liệu thật.

### 10.3. SQL kỳ vọng về mặt ý nghĩa

Sau:

~~~java
PurchaseOrder order = new PurchaseOrder("ORD-1001", customer,
                                       new BigDecimal("250000.00"));
em.persist(order);
em.flush();
~~~

Một dạng INSERT minh họa có thể là:

~~~sql
INSERT INTO purchase_orders
    (order_code, customer_id, status, total_amount)
VALUES
    ('ORD-1001', 42, 'NEW', 250000.00);
~~~

Lưu ý:

- **`created_at`** được bỏ khỏi INSERT để database cấp DEFAULT.
- **`customer_id`** được ghi thông qua association **`customer`**; scalar **`customerId`** không tạo thêm cột ghi.
- **`status`** và **`total_amount`** được ứng dụng cấp giá trị.
- **`order_code`** được INSERT; cờ **`updatable=false`** sẽ ảnh hưởng các UPDATE về sau, không ngăn INSERT.

Sau **`order.markPaid()`** và flush, provider có thể phát UPDATE thay đổi status:

~~~sql
UPDATE purchase_orders
SET status = 'PAID'
WHERE id = ?;
~~~

Đây là **SQL minh họa**, không phải cam kết về thứ tự cột, số statement, việc provider có cập nhật thêm các cột khác hay cú pháp lấy generated key. Tập cột ghi và thời điểm INSERT/UPDATE vẫn phụ thuộc provider và cấu hình cụ thể.

Nếu cần **createdAt** ngay sau INSERT, có thể **`em.refresh(order)`** sau khi flush trong transaction phù hợp. Nếu dữ liệu được trả về API trong lúc entity còn managed nhưng chưa refresh, **createdAt có thể vẫn null**, dù cột DB đã chứa timestamp.

## 11. Những điểm đặc biệt: ID, version, embeddable, bulk DML

### 11.1. `@Id` và `@GeneratedValue` không nên xử lý như field thường

JPA có cơ chế quản lý khóa chính và các chiến lược sinh ID như **IDENTITY**, **SEQUENCE**. Không tùy tiện đặt **`insertable=false`** trên ID để database sinh khóa thay cho **`@GeneratedValue`**. Hành vi định danh của một entity còn phụ thuộc quy tắc của JPA provider và loại khóa.

Ví dụ đúng với kiểu khóa tăng tự động thông dụng:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Với khóa tự nhiên do ứng dụng tạo, có thể không dùng **`@GeneratedValue`**; khi ấy phải bảo đảm entity có ID hợp lệ và không thay đổi identity khi đã persistent.

### 11.2. `@Version` dành cho optimistic locking

~~~java
@Version
private Long version;
~~~

JPA provider quản lý version để phát hiện xung đột cập nhật đồng thời. Đừng coi version như một cột thông thường cần “read-only” bằng **`updatable=false`**, vì provider cần kiểm soát việc ghi/tăng phiên bản. Với optimistic locking, provider có thể phát SQL mang điều kiện:

~~~sql
UPDATE products
SET price = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Nếu số hàng cập nhật bằng 0 vì version đã thay đổi, provider có thể báo optimistic locking failure và yêu cầu transaction xử lý xung đột. **`updatable=false`** trên một field nghiệp vụ không phát hiện lost update; đó là trách nhiệm của cơ chế concurrency phù hợp.

### 11.3. `@Embedded` và `@AttributeOverride`

Một embeddable có thể được tái sử dụng với tên cột khác nhau:

~~~java
@Embeddable
public class Money {
    @Column(name = "amount")
    private BigDecimal amount;
}

@Embedded
@AttributeOverride(
    name = "amount",
    column = @Column(name = "shipping_fee",
                     precision = 19, scale = 2, updatable = false)
)
private Money shippingFee;
~~~

Ví dụ ánh xạ **`Money.amount`** sang cột **`shipping_fee`** với chính sách không cập nhật qua mapping ấy. Khi override, cần hiểu field nào đang được ánh xạ tới cột nào để tránh trùng cột; một embeddable dùng lại ở nhiều vị trí phải có tên cột phân biệt phù hợp. **`@Column`** trong override là metadata mapping; constraint thực tế vẫn phải có ở database nếu cần.

### 11.4. `@Transient` khác hoàn toàn cột read-only

~~~java
@Transient
private BigDecimal temporaryTotal;
~~~

**`@Transient`** của JPA nghĩa là thuộc tính không được ánh xạ persistence; ORM không đọc nó từ database và không sinh INSERT/UPDATE cho nó. Ngược lại, **`@Column(insertable=false, updatable=false)`** vẫn là thuộc tính được mapping: có thể được load qua SELECT nhưng không ghi bởi mapping đó.

Không nhầm **`jakarta.persistence.Transient`** với từ khóa **`transient`** của Java: cả hai có thể ảnh hưởng đến persistence theo từng kiểu access, nhưng không có cùng ý nghĩa trong mọi framework/serialization.

### 11.5. Bulk DML làm stale persistence context

Ví dụ đang có managed product với **stock = 10**:

~~~java
Product product = em.find(Product.class, 5L);

em.createQuery(
        "update Product p set p.stock = p.stock - 1 where p.id = :id")
  .setParameter("id", 5L)
  .executeUpdate();

// Không giả định product.getStock() tự chuyển từ 10 thành 9.
~~~

JPQL bulk update thực thi trực tiếp trên dữ liệu và không đồng bộ state của các managed entity theo cách dirty checking thông thường. Sau bulk update, cần cân nhắc **`clear()`**, **`refresh()`**, nạp lại hoặc thiết kế transaction boundary thích hợp. Điều này quan trọng hơn cờ updatable nếu nhiều code path cùng tác động cột.

## 12. Kiểm tra mapping bằng SQL, schema và tình huống ghi dữ liệu

Đừng chỉ đọc annotation rồi suy luận rằng ràng buộc tồn tại. Khi làm việc với ứng dụng thật, cần phân biệt ba loại bằng chứng:

| Nguồn bằng chứng | Cho thấy điều gì? | Không tự chứng minh điều gì? |
|---|---|---|
| Mapping entity | ORM định nghĩa cột, quan hệ và cờ ghi ra sao | Schema đang triển khai chắc chắn giống annotation |
| Log SQL / SQL trace | Statement nào được provider phát sinh trong ca chạy cụ thể | DB sẽ bảo vệ dữ liệu khỏi mọi client khác |
| Metadata DB / migration | Constraint, default, trigger, index thật đang tồn tại | Logic Java, dữ liệu trong persistence context luôn đồng bộ |

Ví dụ khi muốn biết **created_at** do DB tự cấp có hoạt động không:

1. Xem bảng thực tế có **DEFAULT CURRENT_TIMESTAMP** và NOT NULL không.
2. Tạo entity mới và persist/flush qua EntityManager.
3. Quan sát INSERT xem **created_at** có thật sự bị bỏ khỏi danh sách cột không.
4. Truy vấn giá trị được DB lưu và xem thời điểm giá trị xuất hiện trong entity (sau refresh/load).
5. Nếu nghiệp vụ cần immutable timestamp, xác định cơ chế bảo vệ UPDATE bên ngoài ORM.

### 12.1. Kiểm tra metadata PostgreSQL

Với PostgreSQL, có thể xem constraint và default thông qua thông tin schema, ví dụ:

~~~sql
SELECT column_name, is_nullable, column_default,
       data_type, numeric_precision, numeric_scale
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'purchase_orders'
ORDER BY ordinal_position;
~~~

Và kiểm tra constraint:

~~~sql
SELECT conname AS constraint_name,
       contype AS constraint_type,
       pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.purchase_orders'::regclass;
~~~

Trong **pg_constraint**, **contype** là mã loại constraint (ví dụ primary key, unique, foreign key, check). SQL này mang tính đặc thù PostgreSQL; MySQL, SQL Server, Oracle và H2 có cơ chế metadata tương ứng nhưng cú pháp khác.

### 12.2. Cùng một entity, nhiều đường ghi

Giả sử ứng dụng có một trường **legacyCode** mà JPA mapping **`updatable=false`**. Hãy liệt kê các đường ghi có thể tồn tại:

~~~text
HTTP request -> Service -> managed entity -> JPA flush
Scheduled job -> native SQL
ETL/import -> JDBC
Database migration -> DML
Another application -> DB driver
Admin/DBA -> SQL console
Database trigger -> cập nhật cột
~~~

Cờ JPA chỉ kiểm soát **đường đi qua mapping tương ứng**. Nếu mọi đường ghi đều phải giữ giá trị bất biến, không thể chỉ dựa vào một annotation trong một ứng dụng.

## 13. Lỗi phổ biến và cách sửa

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| INSERT lỗi NOT NULL cho cột `created_at` | Mapping `insertable=false` nhưng DB không có DEFAULT/trigger | Thêm default bằng migration hoặc để ứng dụng cấp giá trị và cho phép INSERT |
| INSERT chứa NULL nên default không chạy | ORM vẫn gửi cột với null | Xem SQL, xét mapping insertable/dynamic insert hoặc tự đặt giá trị |
| Đổi field Java rồi DB không cập nhật | Cờ `updatable=false`, hoặc entity detached/không flush | Kiểm tra mapping và lifecycle, đừng dựa vào setter như bằng chứng SQL đã chạy |
| Đọc generated value sau persist vẫn null | Database đã cấp nhưng persistence context chưa reload | Flush + refresh hoặc cơ chế generated-value của provider |
| Hibernate báo repeated column mapping | Hai thuộc tính/association cùng cố ghi một cột | Chọn một mapping ghi, mapping phụ đặt insertable/updatable=false |
| Sửa `customerId` nhưng quan hệ vẫn trỏ customer cũ | Hai mapping độc lập trong bộ nhớ, không tự đồng bộ tham chiếu | Định nghĩa một nguồn sở hữu, đồng bộ state hoặc refresh |
| Email trùng vẫn chui qua kiểm tra exists | Race condition giữa kiểm tra Java và INSERT | Unique constraint thật ở DB và xử lý lỗi ở transaction |
| `@Column(unique=true)` mà DB vẫn có hàng trùng | Schema hiện tại không chứa unique constraint, hoặc semantics unique/collation khác mong đợi | Kiểm tra DB và migration; thiết kế normalization |
| Field được đánh dấu `updatable=false` vẫn đổi bởi batch script | Native SQL/JDBC/ETL không bị cờ JPA chặn | Dùng DB privilege, trigger/constraint và quy trình dữ liệu |
| Trigger đổi timestamp nhưng JSON trả timestamp cũ | Entity managed giữ stale value | Refresh hoặc đọc lại khi cần |
| Bulk update xong `find` trả dữ liệu cũ | Persistence context chưa được đồng bộ | Clear/refresh, xác định lại transaction boundary |
| UPDATE bị từ chối vì constraint | Dữ liệu vi phạm CHECK/FK/UNIQUE/NOT NULL thật | Bổ sung validate đầu vào và xử lý lỗi DB, không vô hiệu constraint |

### 13.1. Nơi xử lý exception

Database có thể báo vi phạm constraint ngay khi statement chạy, lúc flush, hoặc tại commit nếu constraint được defer. JPA provider và framework có thể bọc lỗi SQL thành **PersistenceException**, **ConstraintViolationException** của persistence provider, **DataIntegrityViolationException** của Spring hoặc exception tương ứng. Đừng phụ thuộc một tên exception duy nhất cho tất cả DB/provider.

Hãy xử lý lỗi ở ranh giới transaction/service, không bắt lỗi rồi tiếp tục dùng transaction đã không còn hợp lệ. Khi phản hồi người dùng, có thể ánh xạ mã lỗi constraint đã biết thành thông báo nghiệp vụ như “Mã đơn đã tồn tại”.

## 14. Bài tập thực hành

### Bài 1: Dự đoán SQL từ bốn tổ hợp

Cho entity:

~~~java
@Column(name = "a", insertable = true,  updatable = true)
private String a;

@Column(name = "b", insertable = true,  updatable = false)
private String b;

@Column(name = "c", insertable = false, updatable = true)
private String c;

@Column(name = "d", insertable = false, updatable = false)
private String d;
~~~

Giả sử bốn field đều được gán giá trị lúc tạo, và tất cả đều bị đổi khi entity đang managed. Khi INSERT và UPDATE do JPA sinh ra, các cột nào đủ điều kiện được ghi?

**Gợi ý:** INSERT có thể dùng **a, b**; UPDATE có thể dùng **a, c**. **d** không được ghi qua mapping này. Điều kiện “có thể dùng” còn phụ thuộc trạng thái entity và SQL generation của provider, nhưng những cột bị cờ tắt không được ghi qua mapping ấy.

### Bài 2: Tìm lỗi trong mapping timestamp

Schema:

~~~sql
CREATE TABLE audit_messages (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    text VARCHAR(500) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

Entity:

~~~java
@Column(name = "created_at", insertable = false, updatable = false)
private Instant createdAt;
~~~

**Câu hỏi:** Tại sao INSERT có thể lỗi? Có hai phương án sửa hợp lệ nào?

**Đáp án gợi ý:** database không có default/trigger và ORM bỏ cột khỏi INSERT, nên NOT NULL bị vi phạm. (1) Thêm **DEFAULT CURRENT_TIMESTAMP** ở DB; giữ mapping chỉ đọc nếu DB sở hữu timestamp. (2) Cho ứng dụng gán timestamp và mapping **`insertable=true`** để SQL chèn giá trị, đồng thời đảm bảo các đường ghi khác.

### Bài 3: Ràng buộc `UNIQUE` có đủ giữ field bất biến?

Một cột **sku VARCHAR(64) NOT NULL UNIQUE** được mapping **`updatable=false`**. DBA chạy:

~~~sql
UPDATE products SET sku = 'SKU-NEW' WHERE id = 10;
~~~

Giả sử SKU-NEW chưa được dùng và DBA có quyền UPDATE. Database có từ chối chỉ vì UNIQUE không?

**Đáp án:** không. UNIQUE chỉ ngăn trùng với giá trị khác theo quy tắc constraint; nó không ngăn thay đổi giá trị duy nhất hiện có. Cờ JPA không kiểm soát SQL của DBA. Muốn bất biến ở DB cần policy/trigger/quyền thích hợp.

### Bài 4: Hai mapping của cùng một FK

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;

@Column(name = "customer_id")
private Long customerId;
~~~

**Câu hỏi:** Mô hình này có thể khiến Hibernate báo lỗi gì? Hãy sửa thành “association ghi, scalar đọc”.

**Đáp án:** hai mapping cùng cố ghi cột **customer_id**, dẫn tới lỗi repeated column mapping. Sửa:

~~~java
@Column(name = "customer_id", insertable = false, updatable = false)
private Long customerId;
~~~

Giữ **`@JoinColumn`** mặc định cho association. Sau khi đổi **customer** trong Java, không được giả định **customerId** tự cập nhật trước khi reload.

### Bài 5: Phân tích dữ liệu default và trạng thái entity

Bảng có cột **state VARCHAR(20) NOT NULL DEFAULT 'NEW'**. Entity mapping:

~~~java
@Column(name = "state", insertable = false, updatable = true)
private String state;
~~~

Thao tác:

~~~java
OrderEntity order = new OrderEntity();
em.persist(order);
em.flush();
String current = order.getState();
~~~

**Câu hỏi:** Có thể khẳng định **current** luôn bằng **"NEW"** không? Vì sao? Nếu cần dùng state ngay sau INSERT thì làm thế nào?

**Đáp án:** không thể khẳng định. Database default đã được áp dụng khi cột bị bỏ khỏi INSERT, nhưng provider không nhất thiết tự nạp default vào field. Có thể refresh entity sau flush hoặc cấu hình cơ chế đọc generated value phù hợp với provider. Nếu muốn trạng thái logic NEW có ngay trong Java và không cần DB cấp default, cân nhắc cho ứng dụng gán NEW từ constructor/factory và cho phép INSERT.

### Bài 6: Phân loại lớp bảo vệ

Với một hệ thống thương mại, hãy phân loại nơi thực thi những yêu cầu sau:

| Yêu cầu | Biện pháp nên xem xét |
|---|---|
| Không cho người dùng đặt số lượng âm | Validation Java cộng CHECK(quantity > 0) ở DB |
| Mỗi SKU là duy nhất | UNIQUE constraint/index ở DB, cùng xử lý lỗi tranh chấp |
| Timestamp tạo do DB cấp | DEFAULT/trigger và mapping bỏ cột khi INSERT |
| Không cho SQL bên ngoài sửa mã đơn | DB permission hoặc trigger/policy, không chỉ `updatable=false` |
| Không được bán quá tồn kho khi nhiều request đồng thời | Atomic UPDATE có điều kiện, khóa hoặc version trong transaction thích hợp |
| Quan hệ order/customer phải trỏ tới hàng có thật | FOREIGN KEY ở DB và mapping association đúng |

Hãy giải thích tại sao một **`@Column`** duy nhất không thể thay thế các cơ chế tương ứng.

## 15. Tư duy khi thiết kế mapping thuộc tính

Khi nhìn một field JPA, nên lần lượt đặt những câu hỏi:

1. **Nguồn giá trị ban đầu là ai?** Java, database default, trigger, generated expression hay provider?
2. **Giá trị có được thay đổi trong vòng đời entity không?** Nếu có, phương thức nghiệp vụ nào được phép sửa? Nếu không, cần bất biến ở Java, ORM, DB hay cả ba?
3. **ORM có nên ghi cột trong INSERT/UPDATE không?** Chọn `insertable` và `updatable` theo trách nhiệm ghi của mapping.
4. **Cột có được ánh xạ nhiều lần không?** Nếu có, mapping nào là nguồn ghi chính? Mapping còn lại chỉ đọc hay cần dùng `@MapsId`?
5. **Constraint nào phải nằm ở database?** NOT NULL, UNIQUE, CHECK, FOREIGN KEY, type/precision/scale, trigger hoặc quyền cập nhật.
6. **Ứng dụng lấy lại giá trị DB-generated khi nào?** Trước khi trả API, sau flush/refresh, qua query mới hay qua cơ chế provider?
7. **Có đường ghi ngoài ORM không?** Batch SQL, ETL, bulk query, ứng dụng khác và tác vụ quản trị phải tuân thủ cùng bất biến.
8. **Nếu hai transaction cùng ghi, kết quả thế nào?** Unique constraint, optimistic locking, conditional update và isolation xử lý những vấn đề khác nhau.

Ví dụ ghi nhớ ngắn:

~~~text
insertable=false → Bỏ cột khỏi INSERT của mapping này.
updatable=false  → Bỏ cột khỏi UPDATE của mapping này.
nullable=false   → Metadata mapping; NOT NULL thật phải có ở DB.
unique=true      → Metadata uniqueness; UNIQUE thật phải có ở DB.
@NotBlank        → Validation Java khi được kích hoạt.
DB constraint    → Bảo vệ dữ liệu tại nơi dữ liệu được lưu.
~~~

**Kết luận:** `insertable` và `updatable` là công cụ xác định **trách nhiệm ghi cột của ORM**. Chúng giúp xử lý field do DB sở hữu, tách mapping đọc/ghi khi một cột được ánh xạ nhiều lần, và giữ SQL sinh ra phù hợp với vòng đời thuộc tính. Tính hợp lệ và bất biến thực tế vẫn phải được bảo vệ bằng **thiết kế nghiệp vụ, validation, transaction và schema database**. Hiểu đúng ranh giới này là nền tảng để mapping JPA an toàn, nhất quán và dễ vận hành.
