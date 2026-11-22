# Quy ước ánh xạ tên lớp, thuộc tính, bảng và cột

Khi viết ứng dụng với **Spring Data Relational JDBC (Spring Data JDBC)**, lớp Java và bảng SQL thường dùng hai quy tắc đặt tên khác nhau. Java quen với `CustomerOrder`, `customerId`, `createdAt`, còn database hay dùng `customer_orders`, `customer_id`, `created_at`. Để hai thế giới này giao tiếp với nhau, Spring Data JDBC dùng **metadata ánh xạ** và **`NamingStrategy`** để xác định tên bảng, tên cột và tên cột liên kết.

Hiểu các quy ước giúp bạn trả lời những câu hỏi rất thực tế: Vì sao repository báo “relation does not exist” dù bảng đã tạo? Vì sao trường `firstName` được tìm trong cột `FIRST_NAME`? Tại sao một `List` cần thêm cột lưu vị trí? Khi nào phải dùng `@Table`, `@Column` hoặc `@MappedCollection`?

> **Nguyên tắc xuyên suốt:** Mô hình Java mô tả đối tượng và quan hệ trong aggregate; database có schema và tên định danh riêng. Spring Data JDBC ánh xạ giữa hai phía, nhưng **không tự đổi tên bảng/cột trong database** để khớp với Java. Mỗi đổi tên ở schema cần được quản lý bằng migration và ánh xạ tương ứng.

## 1. Bức tranh tổng thể của quá trình ánh xạ

Một repository làm việc với đối tượng Java nhưng cuối cùng vẫn cần phát sinh SQL phù hợp với database:

~~~mermaid
flowchart LR
    A["Lớp Java<br/>CustomerOrder"] --> B["Metadata ánh xạ<br/>@Table, @Column, @Id"]
    B --> C["NamingStrategy<br/>quy ước khi thiếu tên tường minh"]
    C --> D["Tên SQL<br/>CUSTOMER_ORDER, CREATED_AT"]
    D --> E[("Bảng/cột vật lý trong database")]
~~~

Có ba nguồn thông tin chủ yếu:

1. **Quy ước mặc định**: tên lớp và trường Java được chuyển sang dạng tên SQL theo `NamingStrategy`.
2. **Annotation tường minh**: `@Table`, `@Column`, `@MappedCollection`, `@Embedded`… chỉ ra tên hoặc cách ánh xạ cụ thể.
3. **Cấu hình ánh xạ chung**: một `NamingStrategy` tùy chỉnh hoặc thay đổi cách quote identifier có thể áp dụng cho nhiều entity trong ứng dụng.

Tên mà Spring Data JDBC *mong đợi* phải tương thích với tên thực tế trong schema. Annotation làm thay đổi cách framework tìm bảng/cột; nó không gửi `ALTER TABLE` để đổi tên thật.

### Phân biệt với Spring Data JPA

Spring Data JDBC không sử dụng cơ chế ánh xạ entity JPA/Hibernate. Các annotation phù hợp cho Spring Data JDBC nằm trong các package Spring Data, chẳng hạn:

| Mục đích | Annotation / API của Spring Data JDBC |
| --- | --- |
| Tên bảng, schema | `org.springframework.data.relational.core.mapping.Table` |
| Tên cột | `org.springframework.data.relational.core.mapping.Column` |
| Cột định danh | `org.springframework.data.annotation.Id` |
| Thuộc tính không được lưu | `org.springframework.data.annotation.Transient` |
| Thuộc tính con cùng bảng | `org.springframework.data.relational.core.mapping.Embedded` |
| Tên cột liên kết collection | `org.springframework.data.relational.core.mapping.MappedCollection` |
| Tùy chỉnh quy ước đặt tên | `org.springframework.data.relational.core.mapping.NamingStrategy` |

Vì vậy, `@Entity`, `@JoinColumn`, `@OneToMany` hoặc các thuộc tính `spring.jpa.hibernate.naming.*` không phải công cụ cấu hình tên cho Spring Data JDBC.

## 2. Quy ước mặc định: tên lớp Java → tên bảng

Khi không chỉ định tên bảng bằng `@Table`, Spring Data JDBC lấy **tên ngắn của lớp** (bỏ package) rồi chuyển các ranh giới camel/Pascal case thành dấu gạch dưới.

Theo quy ước được mô tả trong tài liệu Spring Data Relational, ví dụ:

| Tên lớp Java | Tên bảng được suy ra |
| --- | --- |
| `Customer` | `CUSTOMER` |
| `CustomerOrder` | `CUSTOMER_ORDER` |
| `SavingsAccount` | `SAVINGS_ACCOUNT` |
| `OrderLine` | `ORDER_LINE` |
| `InvoicePayment` | `INVOICE_PAYMENT` |

Dạng tên mặc định được diễn đạt là **`SNAKE_CASE`** (chữ hoa theo ví dụ mapping của framework). Điều quan trọng hơn hình thức in hoa là **tên định danh cuối cùng và cách database xử lý quoting**; phần 5 sẽ giải thích kỹ.

Hai hệ quả dễ bỏ sót:

- **Không tự chuyển sang số nhiều.** Lớp `CustomerOrder` không đương nhiên tìm bảng `customer_orders`. Nếu thiết kế dùng tên số nhiều, cần khai báo `@Table("customer_orders")` hoặc chiến lược đặt tên tương ứng.
- **Package không trở thành một phần của tên bảng.** `com.example.sales.Customer` và `com.example.crm.Customer` đều có thể dẫn tới tên bảng `CUSTOMER`. Nếu hai aggregate cùng dùng một database/schema nhưng cần bảng khác nhau, hãy cấu hình tường minh.

Không nên suy diễn quy tắc cho các chữ viết tắt phức tạp như `URLMapping`, `HTTPStatus` chỉ từ một vài ví dụ. Nếu tên vật lý là hợp đồng lâu dài, hãy ghi rõ `@Table` và `@Column` để tránh bất ngờ khi đổi phiên bản hoặc chiến lược.

## 3. Quy ước mặc định: tên thuộc tính → tên cột

Với thuộc tính được lưu trong cùng bảng, `NamingStrategy` cũng chuyển camelCase sang snake case. Chẳng hạn:

| Trường Java | Tên cột được suy ra |
| --- | --- |
| `id` | `ID` |
| `firstName` | `FIRST_NAME` |
| `customerId` | `CUSTOMER_ID` |
| `createdAt` | `CREATED_AT` |
| `unitPrice` | `UNIT_PRICE` |
| `isActive` | `IS_ACTIVE` |

Một ví dụ không dùng annotation đặt tên tường minh:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;

public class CustomerOrder {
    @Id
    private Long id;

    private Long customerId;
    private Instant createdAt;
    private String orderStatus;
}
~~~

Theo quy ước, Spring Data JDBC dự kiến các cột `ID`, `CUSTOMER_ID`, `CREATED_AT` và `ORDER_STATUS` trong bảng `CUSTOMER_ORDER`. `@Id` đánh dấu thuộc tính nhận diện hàng; nó không có nghĩa tên cột bắt buộc là `id` nếu trong Java tên thuộc tính khác.

Ví dụ, một trường có tên `orderId` và annotation `@Id` vẫn cần ánh xạ tới đúng cột `ORDER_ID`, hoặc được chỉ định bằng `@Column("id")` nếu khóa chính trong SQL thực sự mang tên `id`.

### Vì sao getter/setter không quyết định toàn bộ ánh xạ?

Spring Data JDBC dựa trên **thuộc tính/trường của đối tượng** để lập metadata. Theo quy ước converter, các trường được dùng để chuyển dữ liệu; không đơn giản lấy tên mọi JavaBean getter công khai rồi coi chúng là cột.

~~~java
public class Customer {
    private String fullName;

    public String getDisplayName() {
        return fullName == null ? "" : fullName.trim();
    }
}
~~~

`getDisplayName()` là một phương thức tính giá trị; nó không tự tạo cột `DISPLAY_NAME`. Ngược lại, nếu một trường thuộc mô hình được đánh dấu là persisted property, framework phải biết tên cột tương ứng ngay cả khi bạn không khai báo getter.

Những quy tắc về constructor, record, accessors và immutable object là phần khác của object mapping; **quy tắc đặt tên cột** vẫn dựa trên metadata của từng thuộc tính.

## 4. Ví dụ đầy đủ: dùng 100% tên mặc định

Giả sử định nghĩa aggregate:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;

public class CustomerProfile {
    @Id
    private Long id;
    private String fullName;
    private String emailAddress;
    private Instant registeredAt;
}
~~~

Nếu chọn giữ nguyên tên mặc định và quy tắc quote identifier của Spring Data JDBC, PostgreSQL có thể cần schema đặt tên khớp chính xác như sau:

~~~sql
CREATE TABLE "CUSTOMER_PROFILE" (
    "ID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "FULL_NAME" VARCHAR(150) NOT NULL,
    "EMAIL_ADDRESS" VARCHAR(320) NOT NULL UNIQUE,
    "REGISTERED_AT" TIMESTAMPTZ NOT NULL
);
~~~

Đây là ví dụ minh họa **định danh SQL có quote và chữ hoa**. Nó không có nghĩa phải dùng quy ước viết hoa trong mọi dự án. Nếu schema đang dùng `customer_profiles` và `email_address` ở PostgreSQL, cách ổn định hơn thường là annotation tường minh hoặc `NamingStrategy` thống nhất với schema hiện tại.

## 5. Dùng `@Table` và `@Column` để chỉ định tên rõ ràng

Đây là giải pháp thường gặp nhất khi bảng đã tồn tại, tên bảng ở dạng số nhiều, hoặc cột không trùng quy ước từ tên trường.

### 5.1. Ánh xạ vào bảng/cột hiện hữu

Database PostgreSQL được tạo bằng migration:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email_address VARCHAR(320) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL
);
~~~

Java model:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {
    @Id
    @Column("id")
    private Long id;

    @Column("full_name")
    private String fullName;

    @Column("email_address")
    private String email;

    @Column("created_at")
    private Instant registeredAt;

    // Constructor, getter và phương thức nghiệp vụ...
}
~~~

| Java | Annotation | Cột trong bảng `customers` |
| --- | --- | --- |
| `Customer` | `@Table("customers")` | Bảng `customers` |
| `id` | `@Id @Column("id")` | `id` |
| `fullName` | `@Column("full_name")` | `full_name` |
| `email` | `@Column("email_address")` | `email_address` |
| `registeredAt` | `@Column("created_at")` | `created_at` |

Chú ý hai trường hợp cố ý khác tên: `email` ↔ `email_address` và `registeredAt` ↔ `created_at`. Đây là lý do quan trọng để dùng `@Column` ngay cả khi đã có quy tắc chung.

Annotation `@Table("customers")` chỉ thay **tên bảng**, không tự đổi toàn bộ tên cột từ chữ hoa mặc định sang chữ thường. Trong ví dụ, các cột được ghi rõ để nhất quán với migration PostgreSQL tạo không quote.

### 5.2. `@Column` không làm thay đổi tên thuộc tính Java

Bạn vẫn viết:

~~~java
Customer customer = ...;
String email = customer.getEmail();
~~~

Trong khi câu SQL có thể là:

~~~sql
SELECT email_address
FROM customers
WHERE id = 10;
~~~

Spring Data JDBC nối hai tên bằng mapping metadata; chúng không cần giống nhau. Các phương thức repository và các class dịch vụ vẫn làm việc với tên thuộc tính của Java. Với SQL viết thủ công, người lập trình phải dùng tên cột vật lý trong database.

### 5.3. `@Id` không tạo khóa chính

~~~java
@Id
@Column("customer_key")
private Long id;
~~~

Đoạn này nói rằng trường Java `id` là định danh của aggregate và được lưu ở cột `customer_key`. Nó **không tự tạo** `PRIMARY KEY(customer_key)` trong database.

Constraint, index, kiểu dữ liệu, `NOT NULL` và cách sinh ID cần được tạo theo schema migration riêng. Cấu hình mapping trỏ sai cột khóa chính có thể gây lỗi insert/update hoặc đọc nhầm dữ liệu.

## 6. Tên schema: một phần riêng với tên bảng

Một database quan hệ có thể có nhiều schema. Ví dụ PostgreSQL:

~~~sql
CREATE SCHEMA sales;

CREATE TABLE sales.purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE
);
~~~

Spring Data JDBC hỗ trợ chỉ rõ schema trong `@Table`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table(name = "purchase_orders", schema = "sales")
public class PurchaseOrder {
    @Id
    @Column("id")
    private Long id;

    @Column("order_number")
    private String orderNumber;
}
~~~

Ở đây `sales` là schema, còn `purchase_orders` là tên bảng. Hai giá trị được framework ghép thành định danh đủ điều kiện theo SQL dialect tương ứng.

Nếu không đặt `schema`, framework sử dụng schema mặc định của kết nối hoặc schema do `NamingStrategy.getSchema()` cung cấp, tùy cấu hình. Điều đó có nghĩa cùng tên `purchase_orders` có thể chỉ những bảng khác nhau nếu ứng dụng kết nối với schema mặc định khác.

Không nên giả định chuỗi `@Table("sales.purchase_orders")` luôn tương đương với khai báo hai thuộc tính tách biệt: dấu chấm có thể được xử lý khác nhau tùy cách API diễn giải một identifier có quote. **Ưu tiên `@Table(schema = "sales", name = "purchase_orders")`** khi cần ánh xạ schema tường minh.

## 7. Phân biệt tên SQL, chữ hoa/chữ thường và dấu quote

Đây là nguồn lỗi phổ biến khi chuyển từ H2 sang PostgreSQL.

### 7.1. Database có quy tắc chuẩn hóa identifier riêng

Trong PostgreSQL:

~~~sql
CREATE TABLE customer_order (
    id BIGINT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL
);
~~~

Do identifier không được quote, PostgreSQL lưu tên dưới dạng chữ thường `customer_order`, `id`, `created_at`.

Nhưng:

~~~sql
CREATE TABLE "CUSTOMER_ORDER" (
    "ID" BIGINT PRIMARY KEY,
    "CREATED_AT" TIMESTAMP NOT NULL
);
~~~

lại tạo identifier **có phân biệt chữ hoa/chữ thường**: `"CUSTOMER_ORDER"` là tên khác với `customer_order`.

Các câu truy vấn này không đồng nghĩa trên PostgreSQL:

~~~sql
SELECT * FROM customer_order;
SELECT * FROM "CUSTOMER_ORDER";
~~~

Câu thứ nhất tìm bảng lowercase; câu thứ hai tìm bảng uppercase được quote. Một bảng có thể tồn tại mà Spring JDBC vẫn báo không tìm thấy nếu tên SQL cuối cùng không khớp.

### 7.2. Spring Data JDBC có thể quote identifier mặc định

Theo tài liệu mapping của Spring Data Relational, các tên bảng/cột được suy ra từ lớp và thuộc tính được dùng trong SQL **có quote theo mặc định**; tên do `@Column` chỉ định cũng được quote khi `forceQuote` bật. Framework cung cấp các cơ chế như `JdbcMappingContext.setForceQuote(false)` hoặc factory tạo context cho identifier không quote để thay đổi điều đó khi cấu hình hạ tầng.

Ví dụ minh họa ý tưởng:

| Định danh Spring Data JDBC hướng tới | Tên tạo trong PostgreSQL | Khớp? |
| --- | --- | --- |
| `"CUSTOMER_ORDER"` | `CREATE TABLE "CUSTOMER_ORDER" ...` | Có |
| `"CUSTOMER_ORDER"` | `CREATE TABLE customer_order ...` | Không |
| `"customer_order"` | `CREATE TABLE customer_order ...` | Có |
| `"created_at"` | Cột tạo không quote là `created_at` | Có |

**Quoting và case là hai vấn đề liên quan nhưng khác nhau.** Một `NamingStrategy` tùy chỉnh chọn chữ thường có thể khớp schema lowercase ngay cả khi framework vẫn quote identifier; tắt quote không tự sửa các khác biệt về số ít/số nhiều hoặc tên nghiệp vụ.

### 7.3. Tránh phụ thuộc vào hành vi khác nhau của các hệ CSDL

H2, PostgreSQL, MySQL, SQL Server và Oracle có các quy tắc và cấu hình case khác nhau. Một ví dụ chạy được trên H2 không phải bằng chứng tên SQL sẽ khớp PostgreSQL. Tên như `user`, `order` hoặc `group` còn dễ va chạm keyword SQL; tên dễ hiểu như `app_users` hay `purchase_orders` giảm nhu cầu quote đặc biệt.

Nên chọn một quy tắc thống nhất (ví dụ **lowercase snake_case trong database**) rồi bảo đảm annotation, naming strategy và migration dùng cùng quy tắc.

## 8. Những trường nào được ánh xạ thành cột?

Không phải mọi thành phần trong một class Java đều tương ứng một cột.

### 8.1. `@Transient`: loại thuộc tính khỏi persistence mapping

~~~java
import org.springframework.data.annotation.Transient;

@Table("customers")
class Customer {
    @Id
    @Column("id")
    Long id;

    @Column("full_name")
    String fullName;

    @Transient
    String displayLabel; // Chỉ dùng trong ứng dụng, không cần cột display_label.
}
~~~

`@Transient` của Spring Data báo rằng thuộc tính này không được lưu. Nó khác với việc đơn giản đặt tên cột tùy ý bằng `@Column`. Nếu một constructor persistence đòi giá trị của thuộc tính transient mà không có cách cung cấp, quá trình tạo object từ kết quả SQL cũng có thể gặp vấn đề.

### 8.2. `@ReadOnlyProperty` và cột do database sinh

Có trường hợp một cột được đọc từ database nhưng ứng dụng không nên ghi khi lưu:

~~~java
import org.springframework.data.annotation.ReadOnlyProperty;

@ReadOnlyProperty
@Column("generated_label")
private String generatedLabel;
~~~

Nội dung này mô tả cách ánh xạ một cột được đọc; không phải cơ chế đổi tên và không tự thiết lập công thức sinh giá trị trong SQL. Nếu database tự tính cột, schema phải cung cấp cơ chế đó.

### 8.3. `@Version` cũng có tên cột

Spring Data JDBC có cơ chế optimistic locking với `@Version`. Nếu trường Java là `versionNumber`, quy tắc tên mặc định sẽ áp dụng như thuộc tính khác; nếu schema dùng `row_version` thì cần `@Column("row_version")`:

~~~java
import org.springframework.data.annotation.Version;

@Version
@Column("row_version")
private Long versionNumber;
~~~

`@Version` quyết định ý nghĩa concurrency control của giá trị; `@Column` xác định cột SQL chứa nó.

### 8.4. Chuyển đổi kiểu dữ liệu không phải đổi tên

`MappingJdbcConverter` và `CustomConversions` có thể chuyển `Instant`, enum, value type… sang giá trị JDBC phù hợp. Việc chọn tên cột và việc chuyển kiểu dữ liệu là hai trách nhiệm riêng. Ví dụ `@Column("unit_price") BigDecimal price` chỉ rõ tên cột; kiểu SQL `NUMERIC(12,2)` vẫn do schema định nghĩa.

## 9. Tên cột liên kết khi một aggregate chứa entity con

Quy ước tên không dừng ở các cột đơn giản. Với Spring Data JDBC, một entity con trong aggregate thường nằm ở bảng khác và cần cột tham chiếu ngược về aggregate root (**back reference**).

Giả sử một đơn hàng chứa nhiều dòng:

~~~mermaid
erDiagram
    PURCHASE_ORDERS ||--o{ ORDER_LINES : contains
    PURCHASE_ORDERS {
        bigint id PK
        bigint customer_id
    }
    ORDER_LINES {
        bigint id PK
        bigint purchase_order_id FK
        integer line_position
        varchar sku
    }
~~~

### 9.1. Quy ước back-reference mặc định

Tài liệu Spring Data Relational mô tả rằng tên cột tham chiếu từ entity con về entity cha **mặc định dựa trên tên bảng của entity sở hữu quan hệ**, chứ không đơn thuần dựa trên tên thuộc tính collection.

Với `List` hoặc `Map`, entity con còn có một cột biểu diễn **chỉ số vị trí / khóa của map**. Tên mặc định của cột đó được suy từ tên cột back-reference với hậu tố kiểu `_KEY`.

Điều này dẫn đến một điểm dễ bất ngờ: nếu `PurchaseOrder` ánh xạ vào bảng `purchase_orders` và có `List<OrderLine>`, đừng tự kết luận framework sẽ tự tìm cột `order_id` và `line_no` chỉ vì đó là những tên hợp lý theo nghiệp vụ. **Tên mặc định có quy tắc riêng**, và có thể phụ thuộc `@Table` cùng chiến lược đặt tên đã cấu hình.

### 9.2. Dùng `@MappedCollection` để thống nhất tên rõ ràng

Model:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    @Column("id")
    private Long id;

    @Column("customer_id")
    private Long customerId;

    @MappedCollection(
        idColumn = "purchase_order_id",
        keyColumn = "line_position"
    )
    private List<OrderLine> lines = new ArrayList<>();
}

@Table("order_lines")
public class OrderLine {
    @Id
    @Column("id")
    private Long id;

    @Column("sku")
    private String sku;

    @Column("quantity")
    private int quantity;
}
~~~

Schema tương ứng:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL
        REFERENCES purchase_orders(id),
    line_position INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    CONSTRAINT uq_line_position
        UNIQUE (purchase_order_id, line_position)
);
~~~

Ở đây:

- `idColumn = "purchase_order_id"` xác định **cột trong bảng con** chứa ID của đơn hàng cha. Nó không đổi tên `id` là khóa chính riêng của `OrderLine`.
- `keyColumn = "line_position"` chỉ ra cột biểu diễn vị trí phần tử `List`. Với `List`, khóa về mặt mô hình là chỉ số số nguyên.
- `@Table("order_lines")` chọn bảng của entity con; `@Column("sku")`, `@Column("quantity")` xác định cột dữ liệu nghiệp vụ của con.
- Cột `purchase_order_id` và `line_position` được framework quản lý như metadata của collection. Không cần thêm chúng thành các trường persisted thông thường trong `OrderLine` chỉ để lặp lại tên FK và chỉ số.

Ví dụ trên chọn explicit mapping để database và mô hình Java nhất quán. Dù đã khai báo tên cột trong `@MappedCollection`, **khóa ngoại SQL** và **unique constraint** vẫn phải được tạo trong migration; annotation không tạo constraint.

### 9.3. Phân biệt `Set`, `List` và `Map`

| Kiểu thuộc tính của cha | Cột back reference | Cột key/index |
| --- | --- | --- |
| `Set<Child>` | Cần cột tham chiếu về cha | Không có ý nghĩa vị trí; `keyColumn` không áp dụng |
| `List<Child>` | Cần cột tham chiếu về cha | Cần thêm cột lưu chỉ số phần tử |
| `Map<K, Child>` | Cần cột tham chiếu về cha | Cần thêm cột chứa khóa `K` phù hợp khả năng ánh xạ |
| Một entity con đơn lẻ | Quan hệ cha–con cần cột tham chiếu | Không cần cột vị trí collection |

Tên cột back reference có thể điều chỉnh bằng `NamingStrategy.getReverseColumnName(...)`; tên cột khóa collection có thể điều chỉnh bằng `NamingStrategy.getKeyColumn(...)`. Khi đã có schema cụ thể, `@MappedCollection` thường dễ đọc và ít bất ngờ hơn.

### 9.4. Quan hệ tới aggregate độc lập

Khách hàng và đơn hàng có thể là **hai aggregate độc lập**. Trong trường hợp đó, khai báo:

~~~java
@Column("customer_id")
private Long customerId;
~~~

trên `PurchaseOrder` là một cách biểu diễn tham chiếu theo ID, không phải collection entity con. Nếu muốn biểu đạt rõ hơn về mặt kiểu Java, Spring Data JDBC cũng hỗ trợ `AggregateReference<Customer, Long>`.

Quan hệ giữa hai aggregate không có nghĩa Spring Data JDBC tự tạo join hoặc FK constraint. Bạn vẫn phải khai báo `customer_id` đúng tên và tạo `FOREIGN KEY` trong database nếu nghiệp vụ cần bảo vệ toàn vẹn tham chiếu.

## 10. `@Embedded` và quy tắc tiền tố tên cột

Một **value object** có thể được lưu trực tiếp vào bảng cha thay vì một bảng riêng. Annotation `@Embedded` hỗ trợ điều này.

Giả sử mỗi đơn hàng có thông tin địa chỉ giao hàng:

~~~java
import org.springframework.data.relational.core.mapping.Column;

public class Address {
    @Column("street_name")
    private String street;

    @Column("postal_code")
    private String postalCode;
}
~~~

Ở aggregate:

~~~java
import org.springframework.data.relational.core.mapping.Embedded;

@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    @Column("id")
    private Long id;

    @Embedded.Nullable(prefix = "shipping_")
    private Address shippingAddress;
}
~~~

Schema có các cột ngay trong `purchase_orders`:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    shipping_street_name VARCHAR(200),
    shipping_postal_code VARCHAR(20)
);
~~~

Do có prefix `shipping_` và cột bên trong khai báo `street_name`, `postal_code`, hai tên SQL cuối cùng là `shipping_street_name` và `shipping_postal_code`.

Nếu thêm địa chỉ thanh toán:

~~~java
@Embedded.Nullable(prefix = "billing_")
private Address billingAddress;
~~~

thì framework có thể ánh xạ cùng value object `Address` vào các cột `billing_street_name`, `billing_postal_code` mà không đụng cột shipping.

`@Embedded.Nullable` chỉ định cách xử lý khi mọi cột bên trong đều `NULL` (đối tượng embedded có thể là `null`). Annotation này không có nghĩa database tự cho phép mọi cột null; ràng buộc SQL vẫn là nguồn quyết định sau cùng.

**Khác biệt cốt lõi:** `@MappedCollection` biểu diễn entity con có thể nằm ở bảng riêng, cần cột back reference; `@Embedded` trải các thuộc tính của value object thành **cột trong bảng cha**, và prefix giúp tránh trùng tên.

## 11. Tùy chỉnh `NamingStrategy` cho toàn ứng dụng

Nếu nhiều entity đều theo cùng một quy ước vật lý (ví dụ PostgreSQL dùng lowercase snake_case), viết `@Column` cho mọi trường sẽ dài và dễ bị quên. Có thể khai báo `NamingStrategy` tùy chỉnh để thay đổi cách framework suy ra tên mặc định.

Ví dụ cấu hình Spring:

~~~java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.relational.core.mapping.NamingStrategy;
import org.springframework.data.relational.core.mapping.RelationalPersistentProperty;

@Configuration
public class JdbcNamingConfiguration {

    @Bean
    NamingStrategy lowerSnakeCaseNamingStrategy() {
        return new NamingStrategy() {
            @Override
            public String getTableName(Class<?> type) {
                return NamingStrategy.super.getTableName(type)
                    .toLowerCase(Locale.ROOT);
            }

            @Override
            public String getColumnName(RelationalPersistentProperty property) {
                return NamingStrategy.super.getColumnName(property)
                    .toLowerCase(Locale.ROOT);
            }
        };
    }
}
~~~

Chiến lược này giữ quy tắc phân tách camel case bằng dấu `_` nhưng áp dụng lowercase cho **tên bảng và tên cột cơ bản được suy ra**. Theo đó, một class `CustomerOrder` với trường `createdAt` hướng đến `customer_order` và `created_at`, nếu không có annotation tường minh nào ghi đè.

Đây là **ví dụ tùy chỉnh một phần**: tên back reference, key column, schema và các quy tắc khác của collection vẫn cần kiểm tra để chúng cùng tuân theo quy ước dự kiến. Muốn quy tắc đặt tên mới áp dụng nhất quán cho toàn hệ thống, nên xét thêm `getReverseColumnName(...)` và `getKeyColumn(...)` khi dùng entity con, `List` hoặc `Map`.

### 11.1. Độ ưu tiên giữa annotation và strategy

Thông thường:

1. Tên bảng đã chỉ định trong `@Table` được dùng thay cho tên bảng suy ra từ class.
2. Tên cột đã chỉ định trong `@Column` được dùng thay cho tên cột suy ra từ field.
3. Khi annotation không cung cấp tên, `NamingStrategy` giải quyết quy ước mặc định.
4. Với collection, `@MappedCollection(idColumn = ..., keyColumn = ...)` cho phép đặt tên tường minh thay cho tên back reference/key suy ra.

Vì vậy, sau khi thêm `NamingStrategy` mới, một entity đã khai báo `@Table("legacy_orders")` vẫn có thể tiếp tục ánh xạ vào bảng `legacy_orders`. Điều này hữu ích khi toàn ứng dụng dùng một quy ước chung nhưng một số bảng cũ cần ngoại lệ.

### 11.2. Spring Boot và cấu hình thủ công

Trong cấu hình Spring Data JDBC dựa trên Spring Boot, tài liệu hỗ trợ cung cấp `NamingStrategy` trong application context. Với cấu hình thủ công kế thừa `AbstractJdbcConfiguration`, cũng có thể điều chỉnh hook cấu hình naming strategy của hạ tầng JDBC. Cần chọn **một** cơ chế nhất quán với cách ứng dụng khởi tạo Spring Data JDBC, tránh tạo nhiều context mapping/strategy khiến repository và DAO không đồng nhất.

Đừng sao chép cấu hình của Hibernate sang JDBC. `spring.jpa.hibernate.naming.physical-strategy` dành cho Hibernate/JPA và không phải cách thiết lập `NamingStrategy` của Spring Data JDBC.

### 11.3. Có nên tắt quote identifier?

Có những API như `JdbcMappingContext.setForceQuote(false)` hoặc cơ chế tạo context dùng plain identifiers, tùy phiên bản Spring Data. Tuy nhiên, tắt quote có thể thay đổi cách database chuẩn hóa identifier, gây vấn đề với chữ hoa, tên trùng keyword và schema có sẵn. Hãy chọn theo convention đã thống nhất, không tắt quote chỉ để che lỗi tên bảng khác nhau.

Nếu dự án dùng lowercase snake_case trong PostgreSQL, sử dụng các tên **lowercase rõ ràng** hoặc naming strategy phù hợp thường dễ quản trị hơn là trộn identifier uppercase có quote với identifier lowercase không quote.

## 12. SQL viết thủ công và repository có tự đổi tên như nhau không?

Giả sử entity dùng:

~~~java
@Table("customers")
class Customer {
    @Id
    @Column("id")
    Long id;

    @Column("email_address")
    String email;
}
~~~

Repository CRUD được Spring Data JDBC tạo dựa trên metadata, vì thế framework biết tên bảng và cột đã chỉ định. Nhưng nếu bạn viết SQL trong DAO:

~~~java
import java.util.Map;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;

public class CustomerLookupDao {
    private final NamedParameterJdbcOperations jdbc;

    public CustomerLookupDao(NamedParameterJdbcOperations jdbc) {
        this.jdbc = jdbc;
    }

    public Long findIdByEmail(String email) {
        return jdbc.queryForObject(
            """
            SELECT id
            FROM customers
            WHERE email_address = :email
            """,
            Map.of("email", email),
            Long.class
        );
    }
}
~~~

thì chính bạn phải viết `customers` và `email_address` theo schema vật lý. `NamedParameterJdbcOperations` thay thế **giá trị tham số** như `:email`, chứ không tự đọc annotation `@Table`/`@Column` để viết lại tên cột trong chuỗi SQL.

Điều tương tự áp dụng với `@Query` của Spring Data JDBC: nội dung câu query do bạn khai báo là SQL bạn chịu trách nhiệm, còn kết quả ánh xạ thành đối tượng sử dụng metadata/converter tương ứng.

**Đổi tên cột Java không tự thay đổi câu SQL viết tay.** Khi refactor `emailAddress` thành `email`, cần rà soát những nơi truy vấn bằng tên thuộc tính Java và những nơi viết tên cột SQL trực tiếp.

## 13. Đổi tên lớp, thuộc tính và schema theo thời gian

Một thay đổi tưởng như chỉ là refactor Java có thể làm thay đổi tên SQL nếu đang phụ thuộc vào quy ước tự suy ra.

Ví dụ:

| Thay đổi trong Java | Nguy cơ khi không có tên tường minh |
| --- | --- |
| Đổi class `CustomerOrder` thành `PurchaseOrder` | Tên bảng suy ra đổi từ `CUSTOMER_ORDER` sang `PURCHASE_ORDER` |
| Đổi field `createdAt` thành `orderedAt` | Tên cột suy ra đổi từ `CREATED_AT` sang `ORDERED_AT` |
| Đổi `List<OrderLine>` sang `Set<OrderLine>` | Không còn cần key/index column theo semantics của `List` |
| Đổi `@Table("orders")` thành `@Table("purchase_orders")` | Repository chuyển sang tên bảng khác, dữ liệu cũ không tự được chuyển |
| Thay `NamingStrategy` toàn cục | Nhiều tên bảng, cột và liên kết có thể đổi cùng lúc |

Với ứng dụng đã chạy thực tế, **đổi tên SQL phải được coi là thay đổi schema**:

1. Xác định tên vật lý đang có và tên dự kiến.
2. Cập nhật migration Flyway/Liquibase hoặc cơ chế quản trị schema phù hợp.
3. Cập nhật annotation/strategy và các truy vấn SQL thủ công.
4. Xem xét khóa ngoại, chỉ mục, view, trigger, báo cáo và ứng dụng khác sử dụng bảng/cột.
5. Nếu triển khai rolling deployment, cân nhắc chiến lược tương thích nhiều phiên bản (ví dụ expand–migrate–contract) để không làm instance cũ hỏng giữa chừng.

Với bảng nghiệp vụ tồn tại lâu dài, khai báo tường minh những tên vật lý quan trọng làm cho Java refactor ít bị phụ thuộc vào sơ đồ SQL hơn.

## 14. Cách tìm nguyên nhân khi ánh xạ sai tên

Các triệu chứng điển hình:

| Triệu chứng | Khả năng nguyên nhân | Điểm kiểm tra |
| --- | --- | --- |
| PostgreSQL báo `relation does not exist` | Tên bảng/schéma hoặc quote/case không khớp | `@Table`, `NamingStrategy`, `search_path`, tên bảng thật |
| Báo `column ... does not exist` | Trường Java đổi tên, `@Column` thiếu/sai hoặc tên uppercase có quote | Mapping field, DDL, SQL được phát sinh |
| H2 chạy được nhưng PostgreSQL lỗi | Quy tắc chuẩn hóa identifier của hai DB khác nhau | Câu SQL thực tế và tên bảng/cột vật lý |
| Lưu collection báo thiếu cột trong bảng con | Cột back reference/index không đúng quy ước | `@MappedCollection(idColumn, keyColumn)` và migration |
| Hai value object nhúng ghi đè/trùng tên | Thiếu prefix hoặc prefix giống nhau | `@Embedded(prefix = ...)` |
| CRUD repository chạy nhưng `@Query` lỗi | SQL viết tay dùng tên Java thay vì tên vật lý | Chuỗi SQL trong `@Query`, DAO |
| Refactor tên class làm repository không tìm thấy bảng | Đang để tên bảng suy ra mặc định | Thêm `@Table` phù hợp hoặc migration |
| Tên entity khác tên bảng sau khi đổi strategy | Có annotation tường minh ghi đè hoặc mapping context khác | `@Table`, bean `NamingStrategy`, cấu hình repository |

### Kiểm tra schema thực tế

Với PostgreSQL, có thể xác định tên bảng từ catalog:

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
~~~

Và tên cột:

~~~sql
SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'customers'
ORDER BY ordinal_position;
~~~

Nếu bảng thật tên `"CUSTOMERS"` thì lọc `table_name = 'customers'` sẽ không trả về kết quả tương ứng. Đó là lý do việc nhìn **tên được lưu thực tế** trong catalog tốt hơn suy đoán từ file migration.

### Quan sát SQL trong môi trường phát triển

Khi dùng Spring Boot có thể bật logging cho Spring JDBC:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core: DEBUG
~~~

Hãy xem câu SQL được framework gửi ra (gồm tên bảng/cột và quote) để so với schema. Nếu cần logging sâu hơn, cân nhắc dữ liệu nhạy cảm trong tham số SQL; không bật log chi tiết quá mức trong production.

## 15. Quy ước đề xuất cho dự án Spring Data JDBC

Một bộ quy tắc dễ duy trì là:

- **Java:** lớp `PascalCase`; trường/method `camelCase`, tên diễn đạt ý nghĩa miền nghiệp vụ, ví dụ `PurchaseOrder`, `customerId`, `orderedAt`.
- **Database:** thống nhất một kiểu như `lowercase_snake_case` cho bảng, cột, foreign key, index; đặt tên cụ thể, tránh keyword SQL.
- **Mapping:** dùng `@Table` và `@Column` cho các tên vật lý khác quy ước, hoặc chọn `NamingStrategy` toàn cục khi schema thực sự nhất quán.
- **Aggregate con:** dùng `@MappedCollection` khi tên FK hoặc cột chỉ số của `List`/`Map` có yêu cầu cụ thể; dùng `@Embedded(prefix = ...)` khi value object lưu chung bảng và có nguy cơ trùng cột.
- **Migration:** coi tên vật lý là hợp đồng được version hóa; không dựa vào thay đổi tên Java để schema tự đổi theo.
- **SQL thủ công:** dùng tên bảng/cột vật lý và bind giá trị bằng tham số; không nối tùy tiện identifier do người dùng nhập vào SQL.

Bảng quyết định nhanh:

| Tình huống | Cách xử lý |
| --- | --- |
| Class/field và DDL đều tuân thủ cùng một quy ước | Có thể để `NamingStrategy` suy ra |
| Bảng dùng số nhiều hoặc tên legacy | `@Table("actual_table")` |
| Cột có tên khác field Java | `@Column("actual_column")` |
| Entity nằm trong schema không mặc định | `@Table(schema = "...", name = "...")` |
| Toàn ứng dụng dùng lowercase snake_case | Đăng ký `NamingStrategy` nhất quán |
| Collection con dùng tên FK/index riêng | `@MappedCollection(idColumn = "...", keyColumn = "...")` |
| Value object nhúng nhiều lần | `@Embedded(prefix = "...")` |
| Query SQL do lập trình viên viết | Dùng tên thật trong database; metadata không tự viết lại SQL |
| Thay đổi tên đã triển khai | Viết migration và cập nhật mapping/SQL liên quan |

## 16. Bài tập tự thực hành

### Bài 1 — Suy ra tên mặc định

Cho lớp:

~~~java
public class InventoryItem {
    @Id Long itemId;
    String displayName;
    Integer stockQuantity;
}
~~~

Hãy ghi các tên bảng/cột Spring Data JDBC sẽ suy ra khi không có annotation tên tường minh, và giải thích vì sao `itemId` không đương nhiên là cột `ID`.

### Bài 2 — Ánh xạ schema hiện hữu

Có bảng:

~~~sql
CREATE TABLE sales.order_headers (
    order_id BIGINT PRIMARY KEY,
    buyer_email VARCHAR(320),
    ordered_at TIMESTAMPTZ
);
~~~

Hãy viết class `OrderHeader` với `@Table`, `@Id`, `@Column` phù hợp để có các trường `id`, `email`, `createdAt`. Chú ý chỉ rõ `schema = "sales"` thay vì dựa vào schema mặc định.

### Bài 3 — Ánh xạ `List`

Một đơn hàng lưu danh sách dòng hàng, bảng con có `parent_order_id` và `sort_index`. Hãy sử dụng `@MappedCollection(idColumn = "parent_order_id", keyColumn = "sort_index")` để diễn đạt quan hệ này; xác định vì sao bảng con vẫn cần cột khóa chính riêng và constraint thích hợp.

### Bài 4 — Điều tra lỗi quote/case

Một migration PostgreSQL tạo `customer_order` không quote, trong khi log repository cho thấy truy vấn `"CUSTOMER_ORDER"`. Hãy đưa ra ít nhất hai cách xử lý hợp lý và nêu trường hợp cần migration.

### Bài 5 — Refactor an toàn

Bạn đổi tên trường `createdAt` thành `registeredAt` nhưng muốn giữ nguyên cột `created_at` để tương thích dữ liệu cũ. Hãy thêm annotation phù hợp và liệt kê những câu SQL viết tay có thể cần rà soát.

## 17. Tài liệu chính thức để đọc thêm

- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): quy ước ánh xạ, `@Table`, `@Column`, `@MappedCollection`, `@Embedded`, back references và quote identifier.
- [Spring Data Relational — `NamingStrategy` API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/relational/core/mapping/NamingStrategy.html): các hook tên bảng, cột, schema, cột back reference và key của collection.
- [Spring Data Relational — `@Table` API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/Table.html): `value`/`name` và `schema`.
- [Spring Data Relational — `@MappedCollection` API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/relational/core/mapping/MappedCollection.html): `idColumn` và `keyColumn`.
- [Spring Data Relational — JDBC Repositories](https://docs.spring.io/spring-data/relational/reference/jdbc/repositories.html): cách repository làm việc với mapping và aggregate.

**Điều cần ghi nhớ:** tên lớp và tên thuộc tính Java có thể được chuyển thành tên bảng/cột qua `NamingStrategy`, nhưng giá trị cuối cùng có thể được ghi đè bởi các annotation. Tên liên kết của collection và các trường embedded cũng có quy tắc riêng. Khi thiết kế Spring Data JDBC, hãy quyết định quy ước tên SQL, cấu hình mapping tương ứng và giữ schema migration nhất quán với những tên mà repository thực sự sử dụng.
