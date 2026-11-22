# Ánh xạ khóa chính đơn bằng `@Id`

## 1. Khóa chính đơn trong JPA là gì?

Trong cơ sở dữ liệu quan hệ, **khóa chính (primary key)** định danh duy nhất một hàng trong bảng. Khóa chính đơn là khóa chỉ gồm **một cột**, chẳng hạn `products.id`. Trong Jakarta Persistence (JPA), thuộc tính ánh xạ tới khóa chính của một entity được đánh dấu bằng annotation **`@Id`**.

Ví dụ, mỗi bản ghi sản phẩm có một mã số nội bộ:

```text
products
+----+-------------------+----------+
| id | name              | price    |
+----+-------------------+----------+
|  1 | Java Fundamentals | 150000   |
|  2 | Spring Cookbook   | 190000   |
+----+-------------------+----------+
  ^
  |
PRIMARY KEY: id
```

Entity Java tương ứng:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    private Long id;

    private String name;

    protected Product() {
    }

    public Product(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public Long getId() {
        return id;
    }
}
```

Ở ví dụ này, `@Id` tuyên bố `id` là thuộc tính định danh của `Product`. JPA có thể dùng giá trị đó để tìm entity bằng `EntityManager.find(Product.class, 1L)`, quản lý các bản thể hiện trong persistence context và sinh câu SQL đọc/ghi tương ứng.

**`@Id` chỉ xác định thuộc tính định danh; bản thân nó không quy định giá trị ID được sinh như thế nào.** Nếu muốn ORM tạo ID, thông thường cần kết hợp `@GeneratedValue` hoặc một cơ chế tạo ID được cấu hình phù hợp. Nếu ứng dụng tự cấp ID, có thể chỉ dùng `@Id`.

### Khóa chính ở database khác gì định danh ở Java?

| Khía cạnh | Database | JPA |
|---|---|---|
| Đơn vị định danh | Một hàng trong bảng | Một entity trong phạm vi persistence unit |
| Khai báo | `PRIMARY KEY (id)` | `@Id` trên field hoặc getter |
| Bảo đảm duy nhất | Constraint/unique index do database thực thi | Mapping xác định định danh để ORM quản lý object |
| Kiểu giá trị | `BIGINT`, `UUID`, `VARCHAR`... tùy hệ CSDL | `Long`, `UUID`, `String`... theo hỗ trợ JPA/provider |
| Tạo giá trị | Identity, sequence, trigger, ứng dụng... | Assigned ID hoặc `@GeneratedValue` với chiến lược phù hợp |
| Khi cập nhật | Cột khóa chính thường không nên đổi | Identity của managed entity được kỳ vọng ổn định |

Annotation giúp JPA hiểu cách làm việc với bảng, nhưng **không thay thế constraint `PRIMARY KEY` ở database**. Một cơ sở dữ liệu đã có schema cần được kiểm tra để bảo đảm cột thật sự duy nhất, không null và khớp loại dữ liệu JPA ánh xạ.

## 2. Ánh xạ khóa đơn cơ bản bằng `@Id`

### 2.1. Đặt `@Id` lên field

Một entity quản lý khóa số nguyên kiểu `Long`:

```java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @Column(name = "customer_id", nullable = false, updatable = false)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 150)
    private String fullName;

    protected Customer() {
        // JPA cần constructor không tham số.
    }

    public Customer(Long id, String fullName) {
        this.id = id;
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public void rename(String newName) {
        this.fullName = newName;
    }
}
```

Tương ứng với schema có sẵn:

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
);
```

Ý nghĩa từng annotation:

- **`@Entity`**: lớp được JPA quản lý như một entity.
- **`@Table(name = "customers")`**: chỉ định bảng chứa entity.
- **`@Id`**: đánh dấu duy nhất thuộc tính ID của entity sử dụng khóa chính đơn.
- **`@Column(name = "customer_id")`**: ánh xạ field `id` tới cột `customer_id`. Nếu tên cột trùng quy ước mặc định và không cần tùy chỉnh, có thể bỏ `@Column`.
- **`nullable = false`**: metadata cột không cho phép null khi DDL được provider sinh; ràng buộc PRIMARY KEY của database mới là nơi bảo vệ dữ liệu cuối cùng.
- **`updatable = false`**: đề nghị ORM không đưa cột ID vào SQL UPDATE do ORM sinh. Đây không phải cơ chế bảo vệ duy nhất trước việc đổi khóa.
- **Constructor `protected` không tham số**: cho phép JPA khởi tạo entity trong quá trình đọc dữ liệu.
  
Ví dụ trên dùng **ID do ứng dụng cấp**: constructor nhận `Long id`, không có `@GeneratedValue`. Ứng dụng phải bảo đảm ID đã có giá trị và duy nhất **trước khi gọi `persist`**.

### 2.2. Đặt `@Id` lên getter: property access

JPA có thể truy cập trạng thái entity qua field hoặc JavaBean property. Vị trí đặt `@Id` là yếu tố quan trọng khi xác định **access type mặc định** của entity.

Một entity sử dụng property access:

```java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "departments")
public class Department {

    private Long id;
    private String name;

    protected Department() {
    }

    public Department(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    @Id
    @Column(name = "department_id")
    public Long getId() {
        return id;
    }

    protected void setId(Long id) {
        this.id = id;
    }

    @Column(name = "name", nullable = false)
    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Ở đây `@Id` gắn với **getter** và JPA truy cập thuộc tính qua accessor tương ứng theo quy tắc property access. Một số provider cần setter có khả năng truy cập phù hợp để hydrate dữ liệu. Không nên tự ý xóa setter chỉ vì mã nghiệp vụ không gọi nó.

**Không đặt `@Id` ở field nhưng đặt phần lớn annotation ánh xạ còn lại trên getter một cách lẫn lộn** nếu chưa cấu hình rõ `@Access`: JPA có thể bỏ qua metadata hoặc đưa ra kết quả không mong muốn. Nếu bắt buộc trộn cách truy cập, chỉ định `@Access(AccessType.FIELD)` hoặc `@Access(AccessType.PROPERTY)` ở phạm vi phù hợp và hiểu cách override theo đặc tả.

### 2.3. Những kiểu khóa phù hợp

JPA hỗ trợ một nhóm kiểu khóa đơn thường gặp, ví dụ:

| Kiểu Java | Cột SQL thường gặp | Ghi chú |
|---|---|---|
| `Long` / `long` | `BIGINT` | Phổ biến cho ID số nguyên, dễ index/JOIN |
| `Integer` / `int` | `INTEGER` | Phù hợp phạm vi nhỏ, cần tính nguy cơ tràn |
| `String` | `VARCHAR` / `CHAR` | Hữu ích cho mã đã ổn định và duy nhất; cần chuẩn hóa |
| `UUID` | `UUID`, binary hoặc char | Tùy database, JDBC driver và JPA/provider/version |
| Các kiểu số nguyên phù hợp khác | Kiểu số tương ứng | Cần đối chiếu đặc tả/provider và schema |
| `BigInteger` / `BigDecimal` | Kiểu số lớn/phù hợp | Chỉ dùng khi có lý do rõ và provider hỗ trợ đúng kiểu khóa |

Những lựa chọn thực tế phổ biến là `Long`, `UUID` hoặc `String` bất biến. **Đừng coi mọi class Java đều là kiểu khóa đơn di động**: custom object, JSON, mutable collection, quan hệ entity khác hoặc các kiểu database đặc thù có thể cần thiết kế khác và không thích hợp làm `@Id` đơn giản.

Nếu sinh ID tại database, **wrapper type `Long` hoặc `Integer` thường dễ hiểu hơn primitive**: trước khi có ID, giá trị `null` thể hiện “chưa được gán”; `long` có giá trị mặc định `0`, dễ gây nhầm lẫn giữa chưa có ID và một ID hợp lệ.

## 3. `@Id` không đồng nghĩa với `@GeneratedValue`

Hai kiểu thiết kế khóa cơ bản:

1. **Assigned identifier:** ứng dụng hoặc hệ thống bên ngoài tự cung cấp khóa. Field được gắn `@Id` nhưng không cần `@GeneratedValue`.
2. **Generated identifier:** ORM/database cấp khóa theo một chiến lược đã chọn. Thường dùng `@Id` kết hợp `@GeneratedValue`.

So sánh:

```java
// Ứng dụng tự cấp ID.
@Id
@Column(name = "sku", nullable = false, updatable = false)
private String sku;
```

```java
// JPA và database phối hợp cấp khóa số.
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Trong trường hợp tự cấp ID, nếu quên gán ID trước khi persist, provider có thể báo lỗi định danh chưa được cung cấp. Trong trường hợp ID sinh tự động, **không nên tự điền ID tùy ý** vào entity mới: hành vi phát hiện entity mới/cũ, sinh ID và SQL có thể phụ thuộc provider và ngữ cảnh sử dụng.

### 3.1. Ví dụ assigned ID: mã kho hàng

```java
@Entity
@Table(name = "warehouses")
public class Warehouse {

    @Id
    @Column(name = "warehouse_code", length = 16, updatable = false)
    private String code;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected Warehouse() {
    }

    public Warehouse(String code, String displayName) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("Mã kho không được trống");
        }
        this.code = code;
        this.displayName = displayName;
    }

    public String getCode() {
        return code;
    }
}
```

Schema:

```sql
CREATE TABLE warehouses (
    warehouse_code VARCHAR(16) PRIMARY KEY,
    display_name VARCHAR(255) NOT NULL
);
```

Ứng dụng cấp `"HCM01"` trước khi gọi `persist`. Điều này phù hợp nếu mã kho là **khóa nghiệp vụ duy nhất, ổn định**, không bị tái sử dụng hay đổi tên. Nếu mã kho có thể thay đổi, nên tách một surrogate key (ví dụ `Long id`) khỏi `warehouse_code` có unique constraint.

**Một khóa chính phải ổn định.** Dùng một trường nghiệp vụ dễ thay đổi như tên hiển thị, email, địa chỉ hay trạng thái làm `@Id` thường gây khó khăn cho quan hệ khóa ngoại, cache và đồng bộ object.

## 4. Sinh khóa chính đơn với `@GeneratedValue`

JPA cho phép chọn chiến lược tạo ID qua `@GeneratedValue(strategy = ...)`. Tên enum là `GenerationType`; cách thực thi phụ thuộc provider, database dialect và phiên bản.

| Chiến lược | Ý tưởng | Phù hợp khi | Điểm cần chú ý |
|---|---|---|---|
| `AUTO` | Provider tự chọn cơ chế sinh khóa | Ứng dụng muốn để provider quyết định mặc định | SQL/sequence/hiệu năng có thể thay đổi theo database và phiên bản |
| `IDENTITY` | Database cấp giá trị khi INSERT vào cột identity | Database hỗ trợ identity/auto increment | ORM thường cần INSERT để lấy ID; một số tối ưu batch INSERT có thể bị hạn chế |
| `SEQUENCE` | Lấy ID từ sequence của database | PostgreSQL, Oracle, H2 hoặc database hỗ trợ sequence | Cần sequence tồn tại, tên/`allocationSize` tương thích với cấu hình |
| `TABLE` | Dùng bảng riêng giữ giá trị cấp phát ID | Khi không có native sequence/identity phù hợp | Có thêm thao tác và cạnh tranh cập nhật bảng cấp ID |
| `UUID` | Sinh định danh dạng UUID | Jakarta Persistence 3.1+ với provider hỗ trợ | Dùng kiểu `UUID` phù hợp, xem cách lưu cột và ảnh hưởng index |

Không phải mọi chiến lược đều được hỗ trợ như nhau trên mọi kiểu ID và hệ CSDL. Ví dụ `UUID` là một giá trị định danh khác với sequence số; không nên chọn `SEQUENCE` cho `UUID` chỉ vì JPA cho phép viết annotation về mặt cú pháp.

### 4.1. `GenerationType.IDENTITY`

Ví dụ với bảng `products` có cột ID tự tăng do database cấp:

```java
package com.example.shop.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }
}
```

Ví dụ lược đồ PostgreSQL:

```sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(255) NOT NULL
);
```

Thao tác lưu:

```java
EntityTransaction transaction = em.getTransaction();
transaction.begin();

Product product = new Product("JPA Handbook");
em.persist(product);

transaction.commit();

Long generatedId = product.getId();
System.out.println(generatedId);
```

Mã trên giả định `em` là một `EntityManager` đang mở và cấu hình với giao dịch `RESOURCE_LOCAL`. Sau commit thành công, ID phải có để nhận diện bản ghi vừa lưu. Nhưng **thời điểm chính xác ID xuất hiện và câu INSERT được gửi đi** phụ thuộc chiến lược sinh ID và provider. Với `IDENTITY`, ORM thường phải thực hiện INSERT để nhận khóa do database tạo; không nên kỳ vọng mọi trường hợp ID được cấp ngay ở lệnh `new` hay ngay trước commit theo một quy tắc cố định.

Một chi tiết vận hành: khi phải INSERT sớm để lấy khóa, provider có thể gặp hạn chế tối ưu batch INSERT so với chiến lược cấp ID trước bằng sequence. Cần quan sát SQL và throughput thật nếu ứng dụng ghi nhiều hàng.

### 4.2. `GenerationType.SEQUENCE`

Với database hỗ trợ sequence, ta có thể khai báo sequence tường minh:

```java
@Entity
@Table(name = "invoices")
public class Invoice {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "invoice_id_generator"
    )
    @SequenceGenerator(
        name = "invoice_id_generator",
        sequenceName = "invoice_id_seq",
        allocationSize = 1
    )
    private Long id;

    @Column(name = "invoice_number", nullable = false, unique = true)
    private String invoiceNumber;

    protected Invoice() {
    }

    public Invoice(String invoiceNumber) {
        this.invoiceNumber = invoiceNumber;
    }

    public Long getId() {
        return id;
    }
}
```

Ví dụ SQL PostgreSQL:

```sql
CREATE SEQUENCE invoice_id_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE invoices (
    id BIGINT PRIMARY KEY,
    invoice_number VARCHAR(80) NOT NULL UNIQUE
);
```

Ý nghĩa:

- `@SequenceGenerator(name = "invoice_id_generator")` đặt tên generator phía JPA.
- `sequenceName = "invoice_id_seq"` là tên sequence thật trong database.
- `@GeneratedValue(generator = "invoice_id_generator")` tham chiếu đúng generator phía JPA.
- `allocationSize = 1` minh họa cấu hình dễ đối chiếu với sequence increment bằng 1.

Trong ứng dụng ghi nhiều dữ liệu, `allocationSize` lớn hơn có thể giảm số lần hỏi database để lấy giá trị sequence. Tuy nhiên, cơ chế tối ưu/hi-lo và yêu cầu đồng bộ tăng giá trị sequence **phụ thuộc provider và cấu hình**; không tự ý đổi `allocationSize` mà bỏ qua migration/cơ chế cấp phát hiện tại.

Sequence cấp ID thường **trước câu INSERT**, cho phép ORM biết khóa sớm hơn trong luồng persist và có thể thuận lợi cho batch insert. Sequence cũng có thể tạo “lỗ hổng” số thứ tự sau rollback, cache hoặc phân bổ trước. **Khóa chính chỉ cần duy nhất, không phải dãy số liên tục không thiếu số.**

### 4.3. `GenerationType.AUTO`

Ví dụ ngắn:

```java
@Id
@GeneratedValue(strategy = GenerationType.AUTO)
private Long id;
```

`AUTO` để provider quyết định cách sinh ID dựa trên kiểu thuộc tính, dialect, cấu hình và hỗ trợ của database. Điều này tiện cho ví dụ hoặc ứng dụng không muốn kiểm soát cụ thể cách sinh khóa.

Nhưng khi di chuyển môi trường hoặc nâng cấp Hibernate, provider có thể chọn sequence, bảng cấp ID hay cơ chế khác. Nếu việc truy cập DB, cấu hình DDL, throughput hoặc thứ tự cấp ID là yếu tố quan trọng, nên **chỉ định chiến lược có chủ đích và quản lý schema tương ứng**.

`@GeneratedValue` không có `strategy` thường tương đương chọn giá trị mặc định `AUTO` theo annotation JPA.

### 4.4. `GenerationType.TABLE`

Khi cần bảng lưu trạng thái cấp ID, JPA có `@TableGenerator`. Ý tưởng là lưu cặp tên generator và giá trị hiện hành:

```text
id_generator
+-------------+-----------+
| generator   | next_id   |
+-------------+-----------+
| ticket      | 500       |
+-------------+-----------+
```

Ví dụ cấu hình:

```java
@Id
@GeneratedValue(
    strategy = GenerationType.TABLE,
    generator = "ticket_id_generator"
)
@TableGenerator(
    name = "ticket_id_generator",
    table = "id_generator",
    pkColumnName = "generator",
    valueColumnName = "next_id",
    pkColumnValue = "ticket",
    allocationSize = 10
)
private Long id;
```

Lúc tạo khóa, provider thao tác với bảng cấp số theo giao dịch/locking phù hợp. Phương án này có thể kém hiệu quả hơn native sequence và tạo điểm tranh chấp nếu nhiều luồng cấp ID đồng thời. Cấu trúc bảng, giá trị ban đầu và cách cấp phát phải tương thích provider/dialect.

`TABLE` vẫn có giá trị khi hệ quản trị không hỗ trợ các chiến lược native mong muốn, nhưng không nên dùng như lựa chọn mặc định chỉ vì không phải tự viết SQL sinh ID.

### 4.5. `GenerationType.UUID`

Jakarta Persistence 3.1 chuẩn hóa `GenerationType.UUID`:

```java
import java.util.UUID;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class UploadJob {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    protected UploadJob() {
    }

    public UUID getId() {
        return id;
    }
}
```

UUID hữu ích khi ID được tạo mà không cần một bộ đếm số tăng tập trung, ví dụ các ứng dụng đa node hoặc hệ thống import dữ liệu. Nhưng cần xác định loại UUID/provider sử dụng và cách lưu ở database: `uuid` native (PostgreSQL), `BINARY` hay `CHAR` tùy khả năng. UUID có thể chiếm nhiều byte hơn khóa số và ảnh hưởng kích thước index cũng như tính cục bộ của insert.

**Đừng đồng nhất `UUID` với bí mật bảo mật**: ID khó đoán không thay thế kiểm tra quyền. Ngoài ra, `GenerationType.UUID` được provider thực hiện trong vòng đời persistence, không bảo đảm ID đã tồn tại ngay khi constructor ứng dụng hoàn thành.

## 5. Tự cấp UUID: phân biệt với generated UUID

Nếu ứng dụng muốn ID có giá trị **trước khi gọi `persist`**, có thể dùng assigned UUID:

```java
@Entity
@Table(name = "export_tasks")
public class ExportTask {

    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "file_name", nullable = false)
    private String fileName;

    protected ExportTask() {
    }

    public ExportTask(String fileName) {
        this.id = UUID.randomUUID();
        this.fileName = fileName;
    }

    public UUID getId() {
        return id;
    }
}
```

Ở đây **không dùng `@GeneratedValue`**; constructor nghiệp vụ tự cấp giá trị. Khi entity mới đi vào collection hoặc được gửi qua API trước khi lưu, ID đã sẵn có.

Khác biệt cần nhớ:

| Tình huống | ID xuất hiện khi nào? | Ai chịu trách nhiệm? |
|---|---|---|
| `@Id`, assigned `Long` | Khi ứng dụng tự gán | Mã nghiệp vụ/hệ cấp khóa |
| `@Id`, UUID tạo trong constructor | Khi tạo object bằng constructor nghiệp vụ | Ứng dụng |
| `@Id` + `GenerationType.UUID` | Trong cơ chế sinh ID của JPA/provider | Provider |
| `@Id` + `IDENTITY` | Khi database xử lý INSERT/ORM nhận khóa | Database và provider |
| `@Id` + `SEQUENCE` | Khi ORM lấy giá trị sequence | Database và provider |

Assigned UUID cần ràng buộc PRIMARY KEY trong database và xử lý xung đột nếu có. Nếu một hệ thống có cách import tạo ID riêng, cần tránh vô tình tạo trùng hoặc tự đổi ID của một đối tượng đã tồn tại.

## 6. `@Id` và vòng đời entity

### 6.1. New, managed, detached và removed

Entity trong JPA có trạng thái liên quan persistence context:

```text
    new Product(...)                      em.persist(...)
        |                                      |
        v                                      v
    TRANSIENT ----------------------------> MANAGED
                                               |
                                               | em.detach()/em.close()
                                               v
                                           DETACHED
                                               |
                                               | em.merge(detached)
                                               v
                                      MANAGED instance mới/đã có

    MANAGED -- em.remove() --> REMOVED -- flush/commit --> xóa bản ghi
```

Khóa chính đơn có vai trò xuyên suốt:

- **Transient:** entity mới có thể chưa có ID nếu ORM/database sinh khóa.
- **Managed:** persistence context theo dõi entity dựa trên loại entity và định danh. Khi ID đã được cấp, mọi thao tác cập nhật dùng cùng identity đó.
- **Detached:** object không còn được quản lý nhưng ID thường vẫn giữ nguyên.
- **Merged:** `merge` trả về managed instance tương ứng. Object truyền vào không tự biến thành managed.
- **Removed:** ID trên Java object không bắt buộc tự bị xóa; entity đã bị đánh dấu xóa khỏi database theo vòng đời transaction.

Không nên thay đổi `id` của một managed entity. Việc đổi ID có thể gây ngoại lệ khi flush, nhầm lẫn trong persistence context hoặc làm hỏng tham chiếu khóa ngoại. Muốn đổi một mã nghiệp vụ, **tách mã đó khỏi khóa chính** nếu có khả năng đổi.

### 6.2. Tìm entity theo khóa

Sử dụng `find` với một ID cùng kiểu:

```java
Product product = entityManager.find(Product.class, 42L);

if (product == null) {
    System.out.println("Không tìm thấy sản phẩm");
} else {
    System.out.println(product.getName());
}
```

`find` trả về entity hoặc `null` nếu không tìm thấy (nếu không có lỗi khác). Việc truy vấn database có thể được tối ưu qua persistence context và cache; không nên giả định lần gọi nào cũng phát ra SQL.

Với entity dùng `@Id private String sku`, tham số `find` phải là giá trị `String` tương ứng:

```java
Warehouse warehouse =
    entityManager.find(Warehouse.class, "HCM01");
```

Sai kiểu khóa hoặc metadata không phù hợp có thể dẫn đến lỗi trước hoặc trong truy vấn.

### 6.3. Hai object Java có thể cùng một khóa

```java
Product first = em1.find(Product.class, 42L);
Product second = em2.find(Product.class, 42L);

System.out.println(first == second); // Thường false nếu 2 context riêng
```

Cả hai có thể đại diện cùng hàng trong database dù là hai Java object khác nhau. `@Id` cung cấp **persistence identity** để ORM hiểu, nhưng không tự override `equals` và `hashCode` của Java.

Nếu entity có thể xuất hiện trong `HashSet` trước khi có ID, viết `hashCode()` trực tiếp theo generated ID dễ gây lỗi khi ID thay đổi từ `null` sang giá trị. Một chính sách bình thường là chỉ xem hai entity khác tham chiếu là bằng nhau khi cùng loại và ID **khác null**, với hash ổn định trong vòng đời; tuy nhiên proxy, entity inheritance và multi-tenancy làm thiết kế này phức tạp hơn.

**`@Id` không sinh tự động `equals`/`hashCode`**. Hãy quyết định độc lập hai vấn đề: cách ánh xạ identity cho persistence và quy tắc so sánh object khi nghiệp vụ thực sự cần.

## 7. Khóa chính đơn và quan hệ với các bảng khác

Khóa chính đơn thường được bảng khác tham chiếu qua **foreign key**:

```text
customers
+-------------+-------------+
| customer_id | full_name   |
+-------------+-------------+
| 10          | An          |
+-------------+-------------+
      ^
      | orders.customer_id (FK)
      |
orders
+----+-------------+---------+
| id | customer_id | total   |
+----+-------------+---------+
| 50 | 10          | 300000  |
+----+-------------+---------+
```

Mapping quan hệ từ `Order` sang `Customer`:

```java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "customer_id",
        referencedColumnName = "customer_id",
        nullable = false
    )
    private Customer customer;

    protected Order() {
    }
}
```

Ở đây:

- `orders.id` là **khóa chính đơn** của `Order`.
- `orders.customer_id` là **khóa ngoại** tham chiếu `Customer`; nó **không phải `@Id` của Order** trong mapping này.
- `@JoinColumn` ánh xạ cột quan hệ; giá trị khóa ngoại thông thường được ORM lấy từ ID của `Customer`.
- Database phải có ràng buộc foreign key nếu muốn bảo đảm tính toàn vẹn khi dữ liệu bị thao tác từ mọi nguồn.

Nếu `Order` phải dùng một khóa có nhiều cột, sẽ chuyển sang thiết kế `@EmbeddedId`, `@IdClass` hoặc cấu trúc liên quan. Bài này tập trung vào **khóa chính đơn**, nên không thay thế một mô hình khóa ghép bằng cách ngẫu nhiên chọn một thành phần làm `@Id`.

## 8. Tổ chức mã JPA với một khóa chính đơn

Một mẫu đầy đủ cho ứng dụng Java dùng sequence:

```java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

import java.math.BigDecimal;

@Entity
@Table(name = "catalog_items")
public class CatalogItem {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "catalog_item_id_gen"
    )
    @SequenceGenerator(
        name = "catalog_item_id_gen",
        sequenceName = "catalog_item_id_seq",
        allocationSize = 1
    )
    @Column(name = "id", nullable = false, updatable = false)
    private Long id;

    @Column(name = "name", nullable = false, length = 160)
    private String name;

    @Column(name = "price", nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    protected CatalogItem() {
    }

    public CatalogItem(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("Giá phải không âm");
        }
        this.price = newPrice;
    }
}
```

Tạo schema bằng migration được kiểm soát (ví dụ PostgreSQL):

```sql
CREATE SEQUENCE catalog_item_id_seq
    START WITH 1 INCREMENT BY 1;

CREATE TABLE catalog_items (
    id BIGINT PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    price NUMERIC(14, 2) NOT NULL
);
```

Tầng service truy cập qua `EntityManager` với một transaction phù hợp:

```java
public Long createItem(
        EntityManager em,
        String name,
        BigDecimal price) {

    EntityTransaction tx = em.getTransaction();
    tx.begin();
    try {
        CatalogItem item = new CatalogItem(name, price);
        em.persist(item);
        em.flush(); // Bảo đảm các thay đổi dự kiến được đồng bộ trước khi đọc ID.

        Long id = item.getId();
        tx.commit();
        return id;
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
```

Đây là mẫu minh họa cho **`RESOURCE_LOCAL`**. Với Jakarta EE/JTA hoặc Spring quản lý transaction, ranh giới giao dịch thường được điều khiển bởi container/framework, không gọi `getTransaction()` theo cách trên. Với `SEQUENCE`, ID có thể đã được cấp trước `flush()`; dòng `em.flush()` giúp quan sát hành vi đồng bộ trong ví dụ, không phải yêu cầu bắt buộc để gọi `getId()` ở mọi nhà cung cấp.

Đối tượng tạo mới không cần setter cho ID: ứng dụng không có trách nhiệm đổi ID sau khi lưu. Các thuộc tính nghiệp vụ có thể có method thay đổi với validation, còn khóa chính nên được đối xử như thông tin định danh bất biến.

## 9. Thiết kế khóa chính đơn: lựa chọn natural hay surrogate key?

**Natural key** có ý nghĩa nghiệp vụ, ví dụ mã quốc gia `"VN"`. **Surrogate key** là ID kỹ thuật, ví dụ `Long id` hoặc `UUID id`, được dùng để định danh bản ghi độc lập với thuộc tính nghiệp vụ.

| Tiêu chí | Natural key làm `@Id` | Surrogate key làm `@Id` |
|---|---|---|
| Dễ giải thích với nghiệp vụ | Có, nếu mã có ý nghĩa thực | Không trực tiếp; cần field nghiệp vụ riêng |
| Khả năng thay đổi | Rủi ro cao nếu nghiệp vụ cho phép sửa mã | Thường rất ổn định |
| Kích thước khóa ngoại | Có thể lớn nếu dùng chuỗi dài | `BIGINT`/UUID tương đối ổn định |
| Mức ràng buộc | Cần UNIQUE/PRIMARY KEY trên mã | Cần UNIQUE riêng nếu mã nghiệp vụ vẫn phải duy nhất |
| Tích hợp với hệ bên ngoài | Thuận tiện nếu mã thống nhất toàn hệ thống | Có thể cần mapping sang external ID |
| Di chuyển dữ liệu | Cần xác định va chạm/thay mã nghiệp vụ | Cần chiến lược tránh trùng ID khi hợp nhất nguồn |

Ví dụ sản phẩm có mã SKU có thể thay đổi do chuẩn mới. Thay vì:

```java
@Id
private String sku;
```

thường nên cân nhắc:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;

@Column(name = "sku", nullable = false, unique = true)
private String sku;
```

Khi SKU đổi, khóa ngoại của đơn hàng vẫn tham chiếu ID ổn định. `unique = true` là metadata ánh xạ; trong production cần có **unique constraint** ở database để thực sự chặn trùng mã.

Tuy nhiên, nếu hệ thống có khóa tự nhiên ngắn, bất biến và đã được chuẩn hóa toàn cầu, dùng natural key làm `@Id` vẫn có thể hợp lý. Mấu chốt là **bảo đảm không đổi theo vòng đời thực thể**.

## 10. Những quyết định cần đưa ra khi dùng khóa số

### 10.1. `Long` hay `Integer`?

`Long` cung cấp không gian giá trị lớn hơn `Integer` và thường là lựa chọn an toàn cho bảng có thể tăng quy mô. Nhưng độ rộng cột và index khác nhau ảnh hưởng lưu trữ. Chọn `Long` còn cần kết hợp cột `BIGINT` thực trong database, không chỉ đổi kiểu Java mà quên migrate schema.

Dùng `Integer` cho tập dữ liệu rất nhỏ có thể đủ, nhưng cần nghĩ tới khả năng số bản ghi tăng về lâu dài và các ID có thể bị tiêu hao bởi rollback hay cấp phát trước.

### 10.2. ID có phải thứ tự nghiệp vụ không?

**Không.** Một ID tăng dần không bảo đảm thứ tự tạo đơn hàng tuyệt đối, thứ tự commit hay thời gian xảy ra sự kiện. Sequence và identity có thể sinh khoảng trống hoặc cấp trước trong transaction chưa commit.

Nếu cần số hóa đơn liên tục theo năm, ngày hay đơn vị pháp lý, phải thiết kế một cơ chế **business numbering** riêng với ràng buộc và quy tắc cạnh tranh phù hợp; không nên coi `@Id` tự sinh là số thứ tự nghiệp vụ.

### 10.3. ID có được lộ ra API không?

Có thể gửi ID qua URL hoặc response nếu phù hợp kiến trúc, nhưng việc biết ID **không phải bằng chứng được phép truy cập bản ghi**. Ví dụ API `GET /orders/42` vẫn cần kiểm tra quyền theo người dùng/tenant. Nếu không muốn lộ ID nội bộ, có thể dùng external reference hoặc public identifier riêng, nhưng không thay thế kiểm tra phân quyền.

### 10.4. ID trong môi trường đa tenant

Nếu mỗi tenant có database hoặc schema riêng đều chứa `Product(id=1)`, cùng một giá trị ID **không phân biệt hai bản ghi ở hai tenant**. Cần xem phạm vi định danh của entity, cách định tuyến kết nối và khóa ứng dụng. Trong một schema chia sẻ dữ liệu, có thể cần kết hợp `tenant_id` trong unique key hoặc thiết kế ID toàn cục phù hợp. Không tự giả định `@Id Long id` duy nhất trên mọi database được kết nối bởi hệ thống phân tán.

## 11. Những lỗi thường gặp với `@Id`

### 11.1. Quên khai báo ID

```java
@Entity
class Product {
    private Long id;
    private String name;
}
```

Một JPA entity hợp lệ cần có định danh được ánh xạ. Thiếu `@Id` hoặc metadata XML tương ứng thường gây lỗi khi provider khởi tạo persistence unit, chẳng hạn thông báo entity không có identifier.

Cách khắc phục: xác định thuộc tính khóa đúng và đánh dấu `@Id` tại vị trí access type phù hợp.

### 11.2. Nhầm khóa chính đơn với khóa chính ghép

```java
@Id
private Long orderId;

@Id
private Integer lineNumber;
```

Đây không còn là **khóa đơn**; hai trường định danh đòi hỏi cấu hình khóa ghép phù hợp như `@IdClass` hoặc `@EmbeddedId`. Không nên rải nhiều `@Id` rồi nghĩ provider tự hiểu đầy đủ cấu trúc mà không định nghĩa lớp khóa cần thiết.

### 11.3. Khai báo generated ID nhưng schema không hỗ trợ

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Nếu cột `id` ở database chỉ là `BIGINT NOT NULL PRIMARY KEY` mà **không có cơ chế identity/auto increment**, INSERT không cung cấp ID có thể thất bại. Điều chỉnh migration và mapping phải đồng bộ.

Tương tự, `SEQUENCE` sẽ thất bại nếu provider truy cập sequence sai tên, thiếu quyền, thiếu sequence, hoặc cấu hình cấp phát không tương thích cơ chế database đang dùng.

### 11.4. Gán lại ID đã tồn tại

```java
Product product = em.find(Product.class, 42L);
// Ví dụ không nên làm:
product.setId(99L);
```

Thay ID của managed entity có thể bị JPA phát hiện như thay identity và sinh lỗi, hoặc làm ngữ nghĩa object và các quan hệ không còn nhất quán. Không nên công khai setter ID cho luồng nghiệp vụ sửa dữ liệu.

### 11.5. Dùng primitive ID và suy đoán sai trạng thái

```java
@Id
@GeneratedValue
private long id;
```

Giá trị `0` có thể biểu thị trạng thái chưa được cấp ID nhưng không phải `null`. Trong mã ứng dụng, `Long` giúp phân biệt rõ hơn entity chưa được nhận ID. Tuy nhiên, phát hiện object mới/cũ của provider không chỉ dựa vào phép so sánh này; còn phụ thuộc chiến lược, trạng thái entity, provider và framework phía trên.

### 11.6. Bỏ qua ràng buộc khóa chính ở database

`@Id` chỉ có ý nghĩa trong ORM metadata. Nếu database bị ghi từ SQL khác hoặc một dịch vụ khác, **PRIMARY KEY ở database** mới bảo đảm dữ liệu không có hai hàng trùng ID. Đừng để chỉ có chú thích Java mà schema thực lại không khóa duy nhất.

### 11.7. Giả định ID được tạo ngay tại mọi bước

```java
Product p = new Product("New");
System.out.println(p.getId()); // null nếu generated Long ID

em.persist(p);
// Tại đây ID có thể đã có hoặc chưa, tùy generator/provider.
```

Với một số chiến lược, thời điểm INSERT/flush quyết định khi nhận được khóa; với sequence, khóa thường được cấp trước INSERT. Không nên viết logic phụ thuộc vào đúng thời điểm nếu chưa xác định chiến lược sinh và môi trường.

### 11.8. Dùng generated ID làm hash thay đổi

Một entity có `hashCode() = Objects.hashCode(id)` nếu được thêm vào `HashSet` trước `persist` có thể không được `contains` tìm thấy sau khi ID được sinh. Đây là vấn đề hợp đồng Java và vòng đời định danh, **không phải lỗi của annotation `@Id`**. Lựa chọn quy tắc equality/hash ổn định khi entity cần dùng trong collection băm.

## 12. Cách kiểm tra một ánh xạ khóa đơn có đúng ý nghĩa

Khi đọc một entity JPA, lần lượt đặt các câu hỏi:

1. **Thuộc tính nào là ID?** Chỉ có một field/getter `@Id`, hay entity cần khóa ghép?
2. **Tên cột là gì?** Quy ước mặc định hay `@Column(name = ...)`? Có đúng với schema hiện hữu không?
3. **ID thuộc kiểu nào?** Java type, JDBC binding và SQL type có tương thích không?
4. **Ai tạo ID?** Ứng dụng, sequence, identity, table generator hay UUID do provider sinh?
5. **Khi nào ID có giá trị?** Trước persist, tại persist, lúc flush/INSERT hay khi commit?
6. **ID có được giữ ổn định không?** Có trường hợp nghiệp vụ sửa ID, đổi mã hoặc di chuyển tenant?
7. **Database ràng buộc gì?** Có PRIMARY KEY thực, các khóa ngoại tham chiếu và quyền trên generator?
8. **Có dùng ID để làm business number không?** Nếu có, quy tắc yêu cầu liên tục/thứ tự có nên tách riêng?
9. **Entity có đi qua nhiều persistence context không?** Nếu có, đã hiểu `merge` và quy tắc Java `equals`/`hashCode` chưa?
10. **Có yêu cầu tải lớn hoặc ghi theo lô?** Chiến lược `IDENTITY`/`SEQUENCE` có ảnh hưởng đến batching hay không?

Một bảng đối chiếu giúp hình dung các giải pháp:

| Trường hợp | Khai báo khóa khởi đầu | Rủi ro nên xem xét |
|---|---|---|
| Bảng CRUD cần khóa số tự tăng, PostgreSQL/MySQL | `@Id` + `@GeneratedValue(IDENTITY)` | Cột identity thật, batch INSERT |
| Dịch vụ ghi số lượng lớn trên DB có sequence | `@Id` + `@SequenceGenerator` + `SEQUENCE` | Sequence, allocation, batch |
| Entity có mã ngoài bất biến | `@Id` trên `String` và ứng dụng cấp | Chuẩn hóa, duplicate, khả năng đổi mã |
| ID toàn cục tạo tại ứng dụng trước lưu | `@Id UUID`, tự cấp UUID | Phạm vi unique, kích thước index, UUID type |
| UUID để JPA cấp khi persist | `@Id` + `@GeneratedValue(UUID)` (JPA 3.1+) | Phiên bản, SQL representation |
| Dữ liệu chỉ vài ngàn hàng nhưng cần ít phụ thuộc | Khóa `Long` hoặc `String` phù hợp | Không chọn generator phức tạp thiếu lý do |

## 13. Thực hành: ánh xạ một khóa đơn và quan sát ID

**Bài 1 — Assigned ID**

Tạo bảng:

```sql
CREATE TABLE departments (
    department_id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);
```

Viết entity `Department` dùng `@Id` và `@Column(name = "department_id")`, không dùng `@GeneratedValue`. Tạo một `Department(10L, "Engineering")`, gọi `persist` trong transaction và tải lại bằng `find(Department.class, 10L)`.

Tự trả lời: Nếu tạo thêm `Department(10L, "Finance")` và INSERT, thành phần nào bảo vệ dữ liệu cuối cùng trước ID trùng? Tại sao khóa của entity lại không nên là tên phòng ban?

**Bài 2 — IDENTITY**

Tạo `Product` có `@GeneratedValue(IDENTITY)` và schema tương ứng. In `getId()` ở ba thời điểm: sau constructor, sau `persist` và sau `flush`/commit. Quan sát log SQL để hiểu thực tế provider và database đang dùng.

Tự trả lời: IDENTITY cần database hỗ trợ điều gì? Thao tác nào khiến ORM biết giá trị ID thực?

**Bài 3 — SEQUENCE**

Tạo `Invoice` dùng `@SequenceGenerator` và sequence trong database. So sánh thời điểm ID xuất hiện với IDENTITY, theo dõi lượt lấy sequence và INSERT. Đổi `allocationSize` trong một môi trường thử nghiệm độc lập, tìm hiểu sự khác biệt của cơ chế cấp phát và yêu cầu tương thích với migration.

Tự trả lời: Vì sao số ID có thể thiếu sau rollback mà vẫn không làm sai ràng buộc PRIMARY KEY?

**Bài 4 — UUID**

Tạo hai entity: một entity cấp `UUID.randomUUID()` trong constructor, một entity để provider tạo bằng `GenerationType.UUID`. So sánh ID trước và sau `persist`. Kiểm tra kiểu cột thật do migration hoặc DDL tạo ra.

Tự trả lời: Hai cách này khác nhau ở **thời điểm và người chịu trách nhiệm tạo ID** ra sao?

**Bài 5 — Tách business key và primary key**

Một sản phẩm có SKU nhưng bộ phận kinh doanh đôi khi thay SKU. Thiết kế entity với `Long id` làm `@Id` và `String sku` có unique constraint. Mô tả ảnh hưởng đến các bảng tham chiếu khi SKU đổi, so với việc đặt thẳng SKU làm primary key.

## 14. Ghi nhớ

Một entity có **khóa chính đơn** cần một thuộc tính định danh được ánh xạ bằng **`@Id`**. Annotation này đánh dấu identity cho JPA; cách cấp giá trị là một quyết định riêng: ứng dụng tự cấp hoặc sử dụng `@GeneratedValue` với chiến lược tương thích database và provider.

Khi thiết kế, ưu tiên **ID ổn định, kiểu Java–SQL khớp nhau, ràng buộc PRIMARY KEY tại database và vòng đời ID rõ ràng**. `@Column` làm rõ tên cột, `@GeneratedValue` điều phối sinh khóa, còn `EntityManager` dùng ID để quản lý và truy xuất entity. Chọn `IDENTITY`, `SEQUENCE`, `TABLE`, `AUTO` hay `UUID` phải dựa trên cách database cấp khóa và nhu cầu của ứng dụng, không chỉ để giảm vài dòng code.

Hiểu đúng `@Id` là nền tảng để bước tiếp theo về sinh khóa, quan hệ khóa ngoại, khóa ghép và quản lý vòng đời entity hoạt động nhất quán.
