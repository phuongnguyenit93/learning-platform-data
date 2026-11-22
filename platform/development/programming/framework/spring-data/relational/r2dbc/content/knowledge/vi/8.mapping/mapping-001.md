# Quy ước mặc định khi ánh xạ lớp Java sang bảng

## 1. Ánh xạ đối tượng trong Spring Data Relational R2DBC là gì?

Spring Data Relational R2DBC cho phép ứng dụng làm việc với dữ liệu quan hệ thông qua các lớp Java. Thay vì phải tự viết SQL cho mọi thao tác CRUD, bạn có thể khai báo một lớp biểu diễn dữ liệu rồi dùng repository hoặc R2dbcEntityTemplate để đọc và ghi các đối tượng đó.

Để thực hiện việc này, Spring Data cần biết cách liên hệ giữa:

- Lớp Java với bảng trong database.
- Thuộc tính Java với cột trong bảng.
- Thuộc tính định danh với khóa của bản ghi.
- Kiểu Java với kiểu dữ liệu mà R2DBC driver và database hỗ trợ.

Quá trình liên hệ đó được gọi là ánh xạ đối tượng sang dữ liệu quan hệ (object-relational mapping). Spring Data Relational có cơ chế mapping riêng, được dùng trong Spring Data JDBC và Spring Data R2DBC. Bài này tập trung vào R2DBC.

Spring Data Relational có các quy ước mặc định để bạn không phải khai báo tên bảng và tên cột cho mọi thuộc tính. Khi tên trong Java và tên trong database không theo cùng quy ước, bạn có thể ghi đè bằng các annotation như @Table và @Column.

## 2. Quy ước đặt tên mặc định

Theo naming strategy mặc định của Spring Data Relational, tên lớp và tên thuộc tính Java được chuyển từ dạng PascalCase/camelCase sang dạng snake_case, thường dùng chữ thường.

### 2.1. Tên lớp Java trở thành tên bảng

Nếu lớp không chỉ định tên bảng bằng @Table, Spring Data suy ra tên bảng từ tên lớp.

| Tên lớp Java | Tên bảng theo quy ước mặc định |
|---|---|
| Customer | customer |
| Product | product |
| PurchaseOrder | purchase_order |
| OrderItem | order_item |
| ShippingAddress | shipping_address |

Ví dụ:

~~~java
public class Customer {
    private Long id;
    private String fullName;
}
~~~

Lớp Customer được ánh xạ tới bảng customer. Spring Data không tự động đổi tên số ít thành số nhiều. Vì vậy, Customer mặc định là customer, không phải customers.

Tương tự, PurchaseOrder trở thành purchase_order; Spring Data tách các từ trong tên lớp và nối bằng dấu gạch dưới.

Tên package không được ghép vào tên bảng. Lớp com.example.domain.Customer vẫn suy ra tên bảng từ tên lớp Customer, trừ khi bạn chỉ định tên khác hoặc thay đổi naming strategy.

### 2.2. Tên thuộc tính Java trở thành tên cột

Nếu thuộc tính không có tên cột được chỉ định tường minh, Spring Data suy ra tên cột từ tên thuộc tính theo cùng quy ước snake_case.

| Thuộc tính Java | Tên cột mặc định |
|---|---|
| id | id |
| firstName | first_name |
| createdAt | created_at |
| customerId | customer_id |
| unitPrice | unit_price |
| isActive | is_active |

Ví dụ:

~~~java
public class PurchaseOrder {
    private Long id;
    private String orderNumber;
    private Long customerId;
    private Instant createdAt;
}
~~~

Theo quy ước mặc định, lớp này ánh xạ tới bảng purchase_order với các cột id, order_number, customer_id và created_at.

Bạn nên phân biệt tên thuộc tính Java với tên cột SQL. Trong Java, camelCase thường dễ đọc và phù hợp với quy ước ngôn ngữ. Trong database, snake_case thường được dùng để đặt tên bảng và cột. Spring Data kết nối hai cách đặt tên này thông qua naming strategy.

### 2.3. Quy ước không tự động tạo bảng

Naming strategy chỉ xác định tên mà mapping metadata sử dụng khi tạo SQL hoặc đọc dữ liệu. Nó không có nghĩa Spring Data R2DBC sẽ tự tạo bảng, cột, primary key hay constraint trong database.

Ví dụ, nếu entity có:

~~~java
public class Customer {
    @Id
    private Long id;

    private String fullName;
}
~~~

thì quy ước tên gợi ra bảng customer và các cột id, full_name. Nhưng schema thật vẫn phải có các cấu trúc tương ứng. Nếu bảng thực tế tên là customers, còn code đang mặc định tìm bảng customer, câu SQL được sinh có thể không chạy như mong đợi.

Hãy quản lý schema bằng migration hoặc công cụ DDL phù hợp với dự án. Mapping và schema cần thống nhất với nhau.

## 3. Dùng @Table để chỉ định tên bảng

Annotation @Table cho phép khai báo tên bảng tường minh. Khi có annotation này, tên được khai báo sẽ được dùng thay cho tên suy ra từ lớp.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {
    @Id
    private Long id;

    private String fullName;
}
~~~

Trong ví dụ này:

- Tên lớp là Customer.
- Nếu dùng mặc định, tên bảng sẽ là customer.
- Vì đã khai báo @Table("customers"), lớp được ánh xạ tới bảng customers.
- Tên cột fullName vẫn theo naming strategy mặc định và trở thành full_name.

@Table chỉ thay đổi tên bảng. Nó không tự thay đổi tên tất cả thuộc tính, kiểu dữ liệu, primary key hoặc các constraint.

### 3.1. Khi nào nên dùng @Table?

Dùng @Table khi:

- Database hiện tại sử dụng tên bảng khác với tên suy ra từ lớp Java.
- Dự án thống nhất dùng tên bảng số nhiều như customers, orders, products.
- Tên bảng là tên nghiệp vụ đã được quy định hoặc được chia sẻ với ứng dụng khác.
- Muốn khai báo rõ ràng hợp đồng giữa entity và schema để người đọc code dễ nhận ra.

Ví dụ:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    private String orderNumber;
}
~~~

Entity PurchaseOrder sẽ làm việc với bảng purchase_orders, thay vì bảng mặc định purchase_order.

### 3.2. Tên bảng trong @Table phải khớp schema thật

Giả sử migration tạo bảng:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL
);
~~~

Entity tương ứng:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    private String orderNumber;
}
~~~

Hai phía thống nhất tên bảng và cột. Nếu annotation chỉ định @Table("purchase_order") trong khi database chỉ có purchase_orders, truy vấn được sinh sẽ nhắm tới một bảng khác và database có thể báo không tìm thấy table/relation.

Tên bảng phải phù hợp với quy tắc định danh của hệ quản trị đang dùng. Cách database xử lý chữ hoa, chữ thường, dấu nháy kép và tên dành riêng có thể khác nhau. Hãy ưu tiên tên đơn giản, nhất quán, tránh từ khóa SQL và kiểm tra DDL thực tế.

## 4. Dùng @Column để chỉ định tên cột

Annotation @Column cho phép ánh xạ một thuộc tính Java tới tên cột cụ thể. Khi có @Column, tên được khai báo sẽ thay cho tên được suy ra từ thuộc tính.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {
    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    @Column("email_address")
    private String email;
}
~~~

Trong ví dụ:

| Thuộc tính Java | Nếu dùng mặc định | Tên cột được khai báo |
|---|---|---|
| id | id | id |
| fullName | full_name | full_name |
| email | email | email_address |

fullName vốn đã được ánh xạ thành full_name, nhưng annotation vẫn có thể được dùng để thể hiện rõ tên cột trong schema. email sẽ được ánh xạ tới email_address thay vì email.

### 4.1. Khi nào nên dùng @Column?

Dùng @Column khi:

- Tên cột trong database không theo quy ước snake_case được suy ra từ Java.
- Database có schema cũ với tên cột đã được cố định.
- Tên thuộc tính Java được đặt theo ngôn ngữ hoặc quy ước khác với tên cột.
- Cần làm rõ tên cột mà entity phụ thuộc vào.

Ví dụ, database cũ có cột cust_nm:

~~~java
@Table("customer_master")
public class Customer {
    @Id
    private Long id;

    @Column("cust_nm")
    private String fullName;
}
~~~

Thuộc tính fullName sẽ được đọc/ghi qua cột cust_nm.

### 4.2. @Column không thay đổi kiểu dữ liệu SQL

@Column("email_address") chỉ định tên cột. Nó không tự biến kiểu Java String thành một cột VARCHAR(255), cũng không tạo NOT NULL, UNIQUE hoặc CHECK.

Ví dụ entity:

~~~java
@Column("email_address")
private String email;
~~~

Schema tương ứng có thể được quản lý bằng DDL:

~~~sql
email_address VARCHAR(255) NOT NULL
~~~

Độ dài, nullability, tính duy nhất và các quy tắc dữ liệu được quyết định bởi schema và constraint. Việc ánh xạ kiểu Java sang kiểu SQL còn phụ thuộc Spring Data conversion, R2DBC driver và dialect của database.

### 4.3. @Column trên thuộc tính định danh

Thuộc tính có @Id vẫn tuân theo quy tắc tên cột. Nếu tên ID trong database khác với tên thuộc tính Java, có thể chỉ định @Column cho thuộc tính đó:

~~~java
@Table("customers")
public class Customer {
    @Id
    @Column("customer_id")
    private Long id;

    @Column("full_name")
    private String fullName;
}
~~~

Trong ví dụ, id được ánh xạ tới customer_id. Annotation @Id đánh dấu thuộc tính định danh cho Spring Data; @Column chỉ định tên cột tương ứng. Primary key trong database vẫn cần được tạo trong schema.

## 5. Vai trò của @Id trong ánh xạ

Spring Data cần biết thuộc tính nào định danh một entity. Annotation @Id đánh dấu thuộc tính đó.

~~~java
@Table("products")
public class Product {
    @Id
    private Long id;

    private String name;
    private BigDecimal price;
}
~~~

Trong ví dụ:

- Product được ánh xạ tới bảng products.
- id là thuộc tính định danh.
- name được ánh xạ tới cột name.
- price được ánh xạ tới cột price.

@Id là metadata cho Spring Data biết thuộc tính nào đại diện cho ID của entity. Nó không phải lệnh DDL và không tự tạo primary key trong database.

Schema có thể được tạo như sau:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL
);
~~~

Cách sinh ID cụ thể phụ thuộc hệ quản trị và cấu hình ứng dụng. Với ID do database sinh, kiểu Java, kiểu cột và cơ chế identity/sequence phải tương thích. Với ID do ứng dụng cấp, code cần gán giá trị theo thiết kế trước khi lưu.

Không nên chỉ nhìn vào tên thuộc tính id rồi giả định database đã có primary key. Hãy kiểm tra cả annotation và DDL.

## 6. Thuộc tính không được lưu bằng @Transient

Không phải mọi thuộc tính trong lớp Java đều là cột của bảng. Một số thuộc tính chỉ phục vụ hiển thị hoặc tính toán trong ứng dụng.

Dùng @Transient để đánh dấu thuộc tính không thuộc persistent mapping:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {
    @Id
    private Long id;

    private String firstName;
    private String lastName;

    @Transient
    private String displayName;
}
~~~

displayName có thể được tính từ firstName và lastName:

~~~java
public String getDisplayName() {
    return firstName + " " + lastName;
}
~~~

Thuộc tính này không được xem là cột cần đọc/ghi trong bảng customers. Vì vậy, schema không cần cột display_name chỉ vì lớp Java có thuộc tính displayName.

Hãy dùng @Transient cho dữ liệu dẫn xuất hoặc dữ liệu chỉ tồn tại trong bộ nhớ. Nếu muốn lưu giá trị đó xuống database, hãy bỏ annotation và tạo cột tương ứng trong schema.

Cần phân biệt @Transient của Spring Data với annotation hoặc modifier cùng tên ở những thư viện khác. Khi làm việc với mapping của Spring Data Relational, dùng org.springframework.data.annotation.Transient.

## 7. Ví dụ hoàn chỉnh: từ lớp Java đến bảng SQL

Giả sử ứng dụng quản lý khách hàng và database dùng quy ước tên bảng số nhiều, tên cột snake_case.

Entity:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    @Column("email_address")
    private String email;

    private Instant createdAt;

    @Transient
    private String displayLabel;

    public Customer() {
    }

    public Customer(Long id, String fullName, String email, Instant createdAt) {
        this.id = id;
        this.fullName = fullName;
        this.email = email;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getDisplayLabel() {
        return displayLabel;
    }
}
~~~

Schema SQL tương ứng:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email_address VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Bảng ánh xạ:

| Java | Database | Nguồn quy ước |
|---|---|---|
| Lớp Customer | Bảng customers | @Table("customers") |
| Thuộc tính id | Cột id | @Id và tên mặc định |
| Thuộc tính fullName | Cột full_name | @Column("full_name") |
| Thuộc tính email | Cột email_address | @Column("email_address") |
| Thuộc tính createdAt | Cột created_at | Naming strategy mặc định |
| Thuộc tính displayLabel | Không có cột | @Transient |

Có thể dùng repository để thao tác với entity:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

Spring Data dùng mapping metadata của Customer để xây dựng các thao tác repository. Khi gọi save, findById hoặc các phương thức CRUD khác, tên bảng và cột được lấy từ metadata ánh xạ.

Ví dụ trên giả định schema đã được tạo trước và kiểu cột tương thích với kiểu Java. Chỉ thêm entity và repository không đủ để tạo bảng customers.

## 8. Quy ước mặc định và SQL viết thủ công

Cần phân biệt SQL được Spring Data sinh từ mapping metadata với SQL mà lập trình viên viết trực tiếp.

Với repository hoặc các API mapping entity, Spring Data có thể dùng metadata để xác định tên bảng và cột. Ví dụ entity PurchaseOrder mặc định ánh xạ tới purchase_order, thuộc tính createdAt ánh xạ tới created_at.

Nhưng nếu tự viết SQL bằng DatabaseClient, tên bảng và cột trong chuỗi SQL là tên do bạn chỉ định:

~~~java
databaseClient.sql("""
    SELECT id, created_at
    FROM purchase_order
    WHERE customer_id = :customerId
    """)
    .bind("customerId", customerId);
~~~

DatabaseClient không tự phân tích mọi chuỗi SQL để đổi PurchaseOrder thành purchase_order hoặc createdAt thành created_at. Hãy viết tên SQL khớp với schema thật.

Nếu muốn ánh xạ kết quả truy vấn sang một kiểu Java, có thể dùng cơ chế mapping của DatabaseClient hoặc chuyển đổi phù hợp. Việc ánh xạ kết quả không đồng nghĩa với việc chuỗi SQL đầu vào được đổi tên tự động.

Điều này đặc biệt quan trọng khi dự án dùng @Table và @Column để làm việc với một schema có tên khác quy ước. Các câu SQL thủ công vẫn phải dùng đúng tên bảng và cột thực tế.

## 9. Kiểu Java và kiểu SQL là một phần khác của mapping tên

Tên lớp và tên thuộc tính chỉ giải quyết câu hỏi "đọc/ghi vào bảng và cột nào". Còn câu hỏi "giá trị Java được lưu dưới kiểu SQL nào" liên quan đến hệ thống chuyển đổi kiểu và R2DBC driver.

Một số ví dụ thường gặp:

| Kiểu Java | Kiểu SQL thường tương ứng | Lưu ý |
|---|---|---|
| Long | BIGINT | Kiểm tra phạm vi và cách sinh ID |
| Integer | INTEGER | Dùng cho số nguyên trong phạm vi phù hợp |
| String | VARCHAR hoặc TEXT | Độ dài và kiểu cột do schema quy định |
| BigDecimal | DECIMAL / NUMERIC | Phù hợp với số thập phân cần độ chính xác |
| Boolean | BOOLEAN hoặc kiểu tương đương | Phụ thuộc hệ quản trị |
| LocalDate | DATE | Biểu diễn ngày |
| LocalDateTime | TIMESTAMP | Không mang thông tin múi giờ |
| Instant | Kiểu timestamp phù hợp với driver/database | Cần thống nhất quy ước UTC và múi giờ |

Bảng này là định hướng phổ biến, không phải cam kết rằng mọi driver và database đều hỗ trợ cùng một cách chuyển đổi. Hãy kiểm tra dialect, driver và schema đang dùng. Với kiểu tùy chỉnh, có thể cần converter đọc/ghi do ứng dụng cấu hình.

Ví dụ, thuộc tính:

~~~java
private BigDecimal unitPrice;
~~~

có thể được ánh xạ tới cột unit_price, nhưng kiểu và độ chính xác của cột phải được định nghĩa trong schema:

~~~sql
unit_price DECIMAL(12, 2) NOT NULL
~~~

Naming strategy không quyết định DECIMAL(12, 2). Tên cột và kiểu cột là hai phần riêng biệt.

## 10. Tên bảng, cột và quy tắc của hệ quản trị

Mặc dù Spring Data có naming strategy, database vẫn áp dụng quy tắc định danh riêng.

Một số hệ quản trị tự chuyển identifier không đặt trong dấu nháy về chữ thường hoặc chữ hoa. Identifier được đặt trong dấu nháy có thể phân biệt chữ hoa và chữ thường theo cách riêng của hệ quản trị. Vì vậy, tên bảng Customer, customer và "Customer" không nhất thiết tương đương.

Các lưu ý khi thiết kế tên:

- Dùng chữ thường và snake_case nhất quán cho bảng/cột nếu đó là quy ước của dự án.
- Tránh tên trùng với từ khóa SQL như order, user, group nếu có thể chọn tên rõ ràng khác.
- Không tự ý thay đổi chữ hoa/chữ thường giữa annotation và DDL.
- Nếu phải làm việc với schema cũ có identifier đặc biệt, hãy kiểm tra quy tắc quoting của database và cách Spring Data Relational cấu hình tên.
- Đặt tên cột rõ ý nghĩa, tránh những tên quá ngắn hoặc phụ thuộc vào một ngữ cảnh không được thể hiện trong tên.

Ví dụ, orders hoặc purchase_orders thường dễ đọc hơn một tên chung như order, vốn có thể gây vướng từ khóa hoặc quy tắc quoting tùy hệ quản trị.

## 11. NamingStrategy có thể được tùy chỉnh

Quy ước snake_case là mặc định, không phải quy tắc bắt buộc cho mọi dự án. Spring Data Relational cho phép tùy chỉnh cách suy ra tên bảng và tên cột thông qua NamingStrategy.

Một dự án có thể cần naming strategy khác khi:

- Database hiện hữu dùng chữ hoa hoặc một quy tắc tên riêng.
- Các bảng được đặt theo tiền tố của module.
- Một tổ chức có chuẩn đặt tên chung cho nhiều ứng dụng.
- Muốn dùng quy ước tên khác với mặc định nhưng vẫn giữ mapping nhất quán.

Khi tùy chỉnh, cần bảo đảm strategy được sử dụng nhất quán trong mapping context của ứng dụng. Cách đăng ký strategy phụ thuộc kiểu cấu hình Spring Data Relational/R2DBC mà dự án đang dùng. Hãy cấu hình theo phiên bản Spring Data hiện tại và kiểm tra SQL thực tế được sinh ra.

Không nên thay đổi naming strategy chỉ để sửa một hoặc hai tên bảng đặc biệt. Với các ngoại lệ riêng lẻ, @Table và @Column thường dễ hiểu hơn. Naming strategy phù hợp khi cần thay đổi quy ước trên diện rộng.

## 12. Một số trường hợp cần chú ý khi ánh xạ

### 12.1. Tên bảng số ít hay số nhiều

Spring Data không tự động suy luận ngữ nghĩa số ít/số nhiều để đổi tên bảng. Customer theo mặc định là customer, OrderItem là order_item.

Nếu dự án dùng customers, orders, order_items, hãy dùng @Table cho các tên khác với mặc định hoặc cấu hình naming strategy phù hợp. Đừng tự giả định rằng Spring Data luôn thêm chữ s.

### 12.2. Thuộc tính có tên giống từ khóa hoặc tên không rõ nghĩa

Tên Java có thể hợp lệ nhưng tên cột suy ra có thể không phù hợp với schema hoặc quy tắc database. Hãy dùng @Column để ánh xạ tới tên cột rõ ràng, tránh từ khóa và kiểm tra identifier thực tế.

Ví dụ:

~~~java
@Table("app_users")
public class AppUser {
    @Id
    private Long id;

    @Column("user_status")
    private String status;
}
~~~

### 12.3. Thuộc tính dẫn xuất

Nếu một thuộc tính chỉ là kết quả tính toán, không lưu xuống database, đánh dấu @Transient. Nếu không, Spring Data có thể coi đó là một persistent property và tìm cột tương ứng trong các thao tác mapping.

### 12.4. Lớp con và thuộc tính phức hợp

Không phải mọi thuộc tính Java đều là một cột đơn giản. Spring Data Relational còn có quy tắc cho embedded objects, aggregate và collection được ánh xạ. Các trường hợp đó cần được mô hình hóa theo annotation tương ứng, ví dụ @Embedded hoặc @MappedCollection, thay vì suy luận rằng mọi object lồng nhau sẽ tự động trở thành một cột hoặc một bảng theo ý muốn.

Đặc biệt, Spring Data Relational tổ chức dữ liệu theo aggregate. Một foreign key trong database không tự động tạo ra quan hệ object hai chiều hoặc lazy-loading như JPA. Hãy xác định rõ aggregate root, cấu trúc bảng con và cách truy vấn dữ liệu liên quan.

### 12.5. Trường hợp database có sẵn

Khi ứng dụng kết nối tới database hiện hữu, hãy đọc DDL hoặc metadata của schema trước khi viết entity. Không nên đổi tên bảng/cột trong database chỉ để khớp naming strategy nếu có ứng dụng khác đang phụ thuộc vào schema đó.

Thay vào đó, dùng @Table và @Column để ánh xạ entity tới tên thực tế. Cách này giữ được tên Java rõ ràng mà vẫn tương thích với schema đang tồn tại.

## 13. Quy trình ánh xạ một lớp Java mới

Khi tạo entity mới trong Spring Data Relational R2DBC, có thể thực hiện theo thứ tự:

1. Xác định tên bảng thực tế trong database.
2. Đặt tên lớp Java theo PascalCase và xác định tên bảng mặc định mà naming strategy sẽ suy ra.
3. Nếu tên bảng thực tế khác tên mặc định, khai báo @Table.
4. Xác định thuộc tính định danh và đánh dấu @Id.
5. Đối chiếu từng thuộc tính với tên cột được suy ra theo snake_case.
6. Nếu cột thực tế khác tên mặc định, khai báo @Column.
7. Đánh dấu các thuộc tính không lưu bằng @Transient.
8. Chọn kiểu Java phù hợp với kiểu SQL, driver và converter.
9. Kiểm tra các quan hệ/collection theo mô hình aggregate và annotation tương ứng.
10. Tạo hoặc cập nhật schema bằng migration, bao gồm primary key, foreign key, nullability, unique và các constraint nghiệp vụ.
11. Dùng repository hoặc R2dbcEntityTemplate để kiểm tra thao tác mapping; với SQL thủ công, ghi rõ tên bảng và cột theo schema.
12. Xác nhận mapping hoạt động với database và driver thực tế của dự án.

## 14. Ví dụ tổng hợp với hai entity

Giả sử database có hai bảng customers và purchase_orders. Mỗi đơn hàng lưu customer_id để tham chiếu khách hàng.

Entity khách hàng:

~~~java
@Table("customers")
public class Customer {
    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    @Column("email_address")
    private String email;
}
~~~

Entity đơn hàng:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    @Column("order_number")
    private String orderNumber;

    private Instant createdAt;
}
~~~

DDL minh họa:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email_address VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_purchase_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
);
~~~

Ở đây, customerId được ánh xạ tới cột customer_id, nhưng bản thân thuộc tính Java kiểu Long không tự bảo đảm khách hàng tồn tại. Foreign key trong DDL mới bảo vệ toàn vẹn tham chiếu.

Tương tự, @Table("purchase_orders") giúp Spring Data dùng đúng bảng số nhiều, còn UNIQUE(order_number) và foreign key là quy tắc của database. Mapping metadata và constraint SQL có nhiệm vụ riêng nhưng phải khớp nhau.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Lớp Customer tự động ánh xạ tới bảng customers | Mặc định là customer; dùng @Table hoặc naming strategy nếu muốn tên khác |
| Thuộc tính createdAt ánh xạ tới createdAt trong SQL | Mặc định được chuyển thành created_at |
| @Table thay đổi tên mọi cột | @Table chỉ chỉ định tên bảng |
| @Column tạo cột trong database | @Column chỉ cung cấp metadata ánh xạ; DDL/migration tạo cột |
| @Id tự tạo primary key | @Id đánh dấu thuộc tính định danh cho Spring Data; schema vẫn cần primary key |
| Mọi thuộc tính Java đều được lưu | Thuộc tính @Transient không tham gia persistent mapping |
| Naming strategy tạo schema | Naming strategy chỉ quyết định tên trong mapping metadata |
| SQL viết trong DatabaseClient tự đổi camelCase sang snake_case | SQL viết thủ công phải dùng tên bảng/cột đúng theo schema |
| Tên cột quyết định kiểu SQL | Kiểu cột được xác định bởi schema và cơ chế chuyển đổi của driver/framework |

## 16. Bài tập tự kiểm tra

### Bài 1: Suy ra tên mặc định

Cho lớp:

~~~java
public class ShippingAddress {
    private Long id;
    private String recipientName;
    private String postalCode;
    private Instant updatedAt;
}
~~~

Hãy xác định tên bảng và tên cột mặc định.

Gợi ý: Bảng là shipping_address; các cột lần lượt là id, recipient_name, postal_code và updated_at.

### Bài 2: Ánh xạ tới bảng có sẵn

Database có bảng app_users, cột user_name và email_address. Hãy viết entity AppUser với thuộc tính userName và email.

Gợi ý:

~~~java
@Table("app_users")
public class AppUser {
    @Id
    private Long id;

    @Column("user_name")
    private String userName;

    @Column("email_address")
    private String email;
}
~~~

### Bài 3: Thuộc tính chỉ dùng trong ứng dụng

Một entity Product có price, quantity và totalValue. totalValue được tính từ hai thuộc tính đầu và không cần lưu xuống database. Cần làm gì?

Gợi ý: Đánh dấu totalValue bằng @Transient và tính giá trị trong Java. Nếu muốn lưu giá trị này, hãy bỏ @Transient và tạo cột tương ứng.

### Bài 4: Phân biệt mapping và schema

Entity có @Id private Long id; nhưng bảng trong database không có primary key. @Id có tự sửa vấn đề này không?

Gợi ý: Không. @Id là metadata mapping. Hãy bổ sung primary key bằng migration/DDL và bảo đảm dữ liệu hiện có thỏa mãn constraint trước khi áp dụng.

### Bài 5: SQL thủ công

Entity PurchaseOrder có @Table("purchase_orders") và thuộc tính createdAt. Nếu viết SQL thủ công để lọc theo thời gian tạo, nên dùng tên cột nào?

Gợi ý: Dùng created_at theo schema. SQL thủ công không tự đổi tên thuộc tính Java.

## 17. Ghi nhớ

- Spring Data Relational có naming strategy mặc định để suy ra tên bảng từ lớp và tên cột từ thuộc tính.
- Tên lớp như PurchaseOrder thường được chuyển thành purchase_order; thuộc tính createdAt thành created_at.
- Mặc định không tự chuyển tên bảng sang số nhiều.
- @Table ghi đè tên bảng; @Column ghi đè tên cột.
- @Id đánh dấu thuộc tính định danh; @Transient loại thuộc tính khỏi persistent mapping.
- Annotation ánh xạ không tự tạo bảng, cột, primary key hoặc các constraint.
- Kiểu SQL phụ thuộc schema, Spring Data conversion, R2DBC driver và hệ quản trị.
- SQL viết thủ công phải dùng tên bảng/cột thực tế; không dựa vào naming strategy để tự sửa chuỗi SQL.
- Với database có sẵn, hãy ánh xạ entity theo schema thực tế và quản lý thay đổi bằng migration.

Khi tạo entity trong Spring Data Relational R2DBC, hãy bắt đầu từ tên bảng và cột thực tế, đối chiếu với naming strategy mặc định, rồi dùng annotation cho những tên cần ghi đè. Cách làm này giúp mapping dễ đọc, nhất quán và phù hợp với schema mà ứng dụng đang sử dụng.

