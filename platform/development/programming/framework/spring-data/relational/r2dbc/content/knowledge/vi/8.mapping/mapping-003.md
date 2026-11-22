# Ánh xạ thuộc tính sang cột bằng @Column

Trong Spring Data Relational R2DBC, một entity Java mô tả dữ liệu mà ứng dụng làm việc, còn bảng và cột trong database tuân theo cấu trúc quan hệ đã được thiết kế. Tên thuộc tính Java không phải lúc nào cũng giống tên cột vật lý. Ví dụ, ứng dụng có thuộc tính `firstName` nhưng bảng cũ đặt tên cột là `FIRST_NM` hoặc `customer_name`.

Annotation `@Column` cho phép khai báo rõ tên cột mà một thuộc tính entity ánh xạ tới. Nhờ mapping metadata, Spring Data R2DBC có thể tạo câu lệnh SQL phù hợp khi đọc, insert hoặc update entity. Annotation này đặc biệt hữu ích khi tích hợp với schema có sẵn, tuân theo quy ước đặt tên khác Java hoặc chứa tên cột không đều.

Bài học này trình bày vị trí và cách dùng `@Column`, mối quan hệ với naming strategy, cách annotation ảnh hưởng đến SQL được sinh, cách xử lý tên định danh đặc biệt và những trường hợp `@Column` không giải quyết thay cho schema hoặc custom conversion.

## 1. Vai trò của @Column

`@Column` là annotation của Spring Data Relational dùng để chỉ định tên cột tương ứng với một thuộc tính persistent trong entity. Với R2DBC, annotation nằm trong package:

~~~java
import org.springframework.data.relational.core.mapping.Column;
~~~

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("customer_name")
    private String name;

    @Column("email_address")
    private String email;

    // Constructor, getters và setters
}
~~~

Entity trên ánh xạ tới bảng `customer`. Thuộc tính Java `name` được lưu ở cột `customer_name`; thuộc tính `email` được lưu ở cột `email_address`.

Khi Spring Data tạo câu lệnh SQL cho entity, nó dùng mapping metadata để xác định tên bảng, tên cột, khóa chính và các thuộc tính cần ghi. Vì vậy, mã Java vẫn dùng tên dễ đọc như `name` hoặc `email` trong khi database có thể duy trì tên cột theo quy ước riêng.

`@Column` không đổi tên thuộc tính trong Java. Nó chỉ mô tả cách thuộc tính được ánh xạ vào cấu trúc quan hệ.

## 2. Phân biệt @Column với các annotation mapping khác

Các annotation mapping có trách nhiệm riêng:

| Annotation | Trách nhiệm |
|---|---|
| `@Table` | Xác định bảng quan hệ mà entity ánh xạ tới |
| `@Id` | Đánh dấu thuộc tính định danh/khóa chính |
| `@Column` | Xác định cột tương ứng với thuộc tính |
| `@Transient` | Đánh dấu thuộc tính không được lưu như dữ liệu persistent |
| `@Version` | Đánh dấu thuộc tính version phục vụ optimistic locking |

Ví dụ kết hợp:

~~~java
@Table("customer_account")
public class CustomerAccount {

    @Id
    private Long id;

    @Column("account_number")
    private String accountNumber;

    @Column("available_balance")
    private BigDecimal balance;

    @Version
    private Long version;

    @Transient
    private String displayLabel;
}
~~~

Trong ví dụ này, `id` là khóa chính, `accountNumber` và `balance` ánh xạ tới hai cột có tên cụ thể, `version` hỗ trợ phát hiện cập nhật cạnh tranh và `displayLabel` chỉ phục vụ ứng dụng.

Không dùng `@Column` để khai báo tên bảng hoặc khóa chính. Tên bảng thuộc `@Table`; định danh thuộc `@Id`.

## 3. Quy tắc đặt tên mặc định và naming strategy

Không phải entity nào cũng cần khai báo `@Column` cho mọi thuộc tính. Spring Data Relational sử dụng naming strategy để chuyển tên domain property thành tên cột nếu không có tên được chỉ định rõ.

Với naming strategy mặc định thường dùng trong Spring Data Relational, tên thuộc tính camelCase được chuyển thành snake_case:

| Thuộc tính Java | Tên cột theo quy tắc mặc định |
|---|---|
| `firstName` | `first_name` |
| `createdAt` | `created_at` |
| `phoneNumber` | `phone_number` |
| `orderStatus` | `order_status` |

Ví dụ:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String firstName;

    private LocalDateTime createdAt;
}
~~~

Nếu naming strategy chuyển đổi theo quy tắc trên, `firstName` được ánh xạ tới `first_name`, còn `createdAt` được ánh xạ tới `created_at`. Có thể không cần viết annotation cho những cột đã tuân thủ quy ước đó.

Tuy nhiên, schema thực tế có thể dùng tên khác:

| Thuộc tính Java | Tên cột trong schema cũ |
|---|---|
| `firstName` | `FIRST_NM` |
| `createdAt` | `created_timestamp` |
| `phoneNumber` | `tel_no` |

Khi đó, khai báo rõ ràng bằng `@Column` giúp mapping không phụ thuộc vào việc naming strategy có thể suy ra tên cột hay không:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("FIRST_NM")
    private String firstName;

    @Column("created_timestamp")
    private LocalDateTime createdAt;

    @Column("tel_no")
    private String phoneNumber;
}
~~~

Tên trong `@Column` là tên cột theo schema mà database sử dụng. Hãy kiểm tra tên thật trong database và quy tắc chữ hoa/chữ thường của hệ quản trị, đặc biệt khi schema có định danh được tạo bằng dấu nháy.

### 3.1. Khi nào nên khai báo tường minh?

Dùng `@Column` khi:

- Tên cột khác tên mà naming strategy mặc định tạo ra.
- Tích hợp với schema cũ hoặc schema do hệ thống khác quản lý.
- Tên cột là từ khóa SQL hoặc cần quy tắc quoting đặc biệt.
- Muốn thể hiện rõ mapping quan trọng ngay trong entity.
- Quy ước database yêu cầu viết tắt hoặc tiền tố riêng.

Nếu toàn bộ schema tuân theo naming strategy nhất quán, không cần thêm annotation một cách máy móc cho mọi thuộc tính. Giữ entity gọn và chỉ ghi đè ở những nơi có khác biệt thực sự.

### 3.2. Naming strategy và @Column

Naming strategy cung cấp quy tắc chung cho những thuộc tính không có tên cột tường minh. `@Column` cung cấp tên cụ thể cho một thuộc tính.

Có thể hình dung thứ tự quyết định như sau:

~~~text
Thuộc tính persistent trong entity
              |
              v
Có tên cột khai báo bằng @Column?
        /               \
      Có                 Không
      |                   |
      v                   v
Dùng tên cột        Áp dụng naming strategy
được chỉ định       của mapping context
      |                   |
      +---------+---------+
                |
                v
        Mapping metadata
                |
                v
       SQL và row mapping
~~~

Nếu thay đổi naming strategy của toàn ứng dụng, những thuộc tính không khai báo `@Column` có thể được ánh xạ sang tên khác. Các thuộc tính đã khai báo tên cột tường minh tiếp tục dùng tên được chỉ định theo metadata của annotation.

## 4. Cách sử dụng @Column

Cách dùng phổ biến nhất là truyền tên cột vào annotation:

~~~java
@Column("customer_name")
private String name;
~~~

Có thể đặt annotation trên các thuộc tính persistent của entity. Ví dụ đầy đủ:

~~~java
@Table("customer_profile")
public class CustomerProfile {

    @Id
    private Long id;

    @Column("given_name")
    private String firstName;

    @Column("family_name")
    private String lastName;

    @Column("email_addr")
    private String email;

    @Column("registered_on")
    private LocalDate registeredOn;

    // Constructor, getters và setters
}
~~~

Mapping tương ứng:

| Thuộc tính Java | Cột database |
|---|---|
| `id` | Cột khóa chính theo mapping của `@Id` và naming metadata |
| `firstName` | `given_name` |
| `lastName` | `family_name` |
| `email` | `email_addr` |
| `registeredOn` | `registered_on` |

Tên bảng vẫn được xác định bởi `@Table("customer_profile")`. Annotation `@Column` không thay đổi cấu trúc bảng hoặc tạo cột mới.

### 4.1. Đặt tên cột có dấu gạch dưới

Tên cột snake_case là trường hợp phổ biến khi thuộc tính Java dùng camelCase:

~~~java
@Column("shipping_address")
private String shippingAddress;

@Column("last_login_at")
private LocalDateTime lastLoginAt;
~~~

Nếu naming strategy mặc định đã chuyển `shippingAddress` thành `shipping_address`, annotation đầu tiên có thể không cần thiết. Annotation vẫn có thể được giữ để thể hiện một mapping quan trọng hoặc bảo đảm rõ ràng khi naming strategy thay đổi, nhưng nên duy trì một quy ước nhất quán trong dự án.

### 4.2. Tên cột viết hoa hoặc viết tắt

Schema cũ có thể chứa tên như `CUST_NO`, `ADDR_1` hoặc `UPD_TS`:

~~~java
@Column("CUST_NO")
private String customerNumber;

@Column("ADDR_1")
private String addressLine1;

@Column("UPD_TS")
private LocalDateTime updatedAt;
~~~

Không tự chuyển tên cột về chữ thường nếu schema thực tế dùng định danh có quy tắc chữ hoa/chữ thường đặc biệt. Cách database xử lý chữ hoa và chữ thường phụ thuộc việc định danh có được quote và phụ thuộc hệ quản trị.

## 5. Tên định danh đặc biệt và quoting

Tên cột có thể trùng từ khóa SQL, chứa khoảng trắng hoặc dùng chữ hoa/chữ thường cần giữ nguyên. Trong trường hợp đó, SQL có thể cần quote identifier.

Một số phiên bản Spring Data Relational hỗ trợ thuộc tính `forceQuote` trên `@Column`. Có thể khai báo:

~~~java
@Column(value = "order", forceQuote = true)
private String order;
~~~

Khi sinh SQL, Spring Data yêu cầu dialect quote tên cột theo quy tắc của database. PostgreSQL thường dùng dấu nháy kép cho identifier; một số hệ quản trị khác có quy tắc khác.

Không nên tự thêm ký tự quote vào tên annotation nếu không cần. Hãy dùng cơ chế quoting do mapping metadata và dialect hỗ trợ. Kiểm tra API của phiên bản Spring Data Relational mà dự án đang sử dụng nếu cần dùng thuộc tính `forceQuote`.

Quoting identifier khác với bind parameter cho giá trị. `@Column` mô tả tên cột trong SQL; giá trị dữ liệu vẫn được truyền qua parameter binding để tránh nối chuỗi SQL và giảm nguy cơ SQL injection.

## 6. @Column ảnh hưởng đến câu lệnh SQL được sinh như thế nào?

Khi repository hoặc `R2dbcEntityTemplate` thực hiện thao tác trên entity, Spring Data dùng mapping metadata để xây dựng câu lệnh. Tên cột đã khai báo bằng `@Column` được sử dụng cho mapping của thuộc tính.

Giả sử entity:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("display_name")
    private String name;

    @Column("email_addr")
    private String email;
}
~~~

Khi insert hoặc update, câu SQL được tạo sẽ sử dụng các tên cột vật lý tương ứng. Dạng minh họa:

~~~sql
INSERT INTO customer (display_name, email_addr)
VALUES (?, ?);
~~~

Khi đọc entity, mapping cũng dựa trên metadata để đưa giá trị từ các cột về đúng thuộc tính Java. Cú pháp placeholder và cách sinh alias có thể khác nhau theo dialect, driver và loại thao tác; ví dụ chỉ minh họa tên cột được sử dụng.

Vì thế, mã ứng dụng vẫn có thể làm việc với `customer.getName()` trong khi database lưu giá trị ở `display_name`.

### 6.1. Tên thuộc tính trong repository method vẫn là tên Java

`@Column` không đổi tên property trong mô hình domain. Các derived query method được đặt theo thuộc tính Java:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByName(String name);

    Mono<Customer> findByEmail(String email);
}
~~~

Ở đây dùng `findByName` và `findByEmail` vì entity có thuộc tính `name` và `email`. Spring Data dùng metadata để chuyển điều kiện property sang cột `display_name` và `email_addr`.

Không viết `findByDisplayName` chỉ vì cột vật lý có tên `display_name`, trừ khi entity thực sự có property Java tên `displayName`.

### 6.2. SQL viết tay phải dùng tên cột vật lý

Khi dùng `@Query` với SQL tự viết, chuỗi SQL là câu lệnh do người phát triển cung cấp. `@Column` không tự sửa nội dung SQL literal.

Ví dụ:

~~~java
@Query("""
    SELECT id, display_name, email_addr
    FROM customer
    WHERE display_name = :name
    """)
Flux<Customer> findCustomersByName(@Param("name") String name);
~~~

Trong SQL trên, phải viết đúng tên bảng và cột trong database: `customer`, `display_name`, `email_addr`. Không dùng tên property Java thay cho tên cột vật lý nếu hai tên khác nhau.

Với projection hoặc câu truy vấn có biểu thức, hãy đặt alias phù hợp với mapping/projection mà ứng dụng mong đợi. Ví dụ, nếu truy vấn trả về giá trị tính toán, alias rõ ràng giúp Spring Data ánh xạ kết quả dễ dự đoán hơn.

## 7. @Column không thay thế schema hoặc migration

Annotation mô tả mapping ở tầng ứng dụng. Nó không tự tạo, đổi tên hoặc di chuyển cột trong database.

Giả sử entity khai báo:

~~~java
@Column("display_name")
private String name;
~~~

Nếu bảng `customer` chưa có cột `display_name`, thao tác SQL có thể thất bại với lỗi không tìm thấy cột. Việc thêm annotation không làm database tự thêm cột đó.

Khi đổi mapping từ `name` sang `display_name`, schema phải được cập nhật bằng công cụ migration hoặc quy trình quản lý schema của dự án, chẳng hạn Flyway hoặc Liquibase. Một thay đổi thường cần:

1. Kiểm tra schema hiện tại và dữ liệu đang có.
2. Viết migration đổi tên hoặc tạo cột theo kế hoạch.
3. Xử lý dữ liệu cũ nếu cần chuyển đổi.
4. Cập nhật entity với `@Column`.
5. Chạy integration test trên database đã áp dụng migration.
6. Triển khai ứng dụng và schema theo thứ tự tương thích với chiến lược rollout.

Trong hệ thống đang chạy, thay đổi tên cột có thể ảnh hưởng nhiều ứng dụng cùng sử dụng schema. Hãy phối hợp migration và phiên bản ứng dụng để tránh một phiên bản code đọc tên cột mà database chưa có.

## 8. @Column không quyết định kiểu dữ liệu hoặc chuyển đổi giá trị

`@Column` xác định tên cột. Nó không phải nơi khai báo kiểu SQL, độ dài chuỗi, precision của số hoặc quy tắc chuyển đổi giá trị.

Ví dụ:

~~~java
@Column("total_amount")
private BigDecimal totalAmount;
~~~

Annotation nói rằng `totalAmount` ánh xạ tới cột `total_amount`. Kiểu SQL thực tế và độ chính xác phải được định nghĩa trong schema database. Việc chuyển đổi giữa kiểu Java và kiểu R2DBC/database do Spring Data conversion và driver đảm nhiệm.

Nếu một kiểu Java cần quy tắc chuyển đổi đặc biệt, hãy dùng Spring Data custom conversions với reading converter và writing converter phù hợp, thay vì cố dùng `@Column` để thay đổi kiểu dữ liệu.

Ví dụ, nếu database lưu trạng thái đơn hàng dưới dạng chuỗi nhưng ứng dụng dùng enum, cần kiểm tra converter mặc định có đáp ứng định dạng lưu trữ hay không. Nếu không, khai báo converter phù hợp trong cấu hình custom conversions.

Tương tự, các ràng buộc `NOT NULL`, `UNIQUE`, `CHECK`, default value và độ dài cột phải được định nghĩa trong schema hoặc migration. `@Column` không tự tạo các constraint này.

## 9. Kết hợp @Column với entity bất biến

Spring Data Relational có thể ánh xạ entity qua constructor. Với entity bất biến, thuộc tính được khởi tạo thông qua constructor thay vì setter.

Ví dụ:

~~~java
@Table("customer")
public class Customer {

    @Id
    private final Long id;

    @Column("display_name")
    private final String name;

    @Column("email_addr")
    private final String email;

    public Customer(Long id, String name, String email) {
        this.id = id;
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Mapping vẫn dựa trên metadata của entity. Tên cột vật lý có thể khác tên tham số hoặc property Java; `@Column` xác định cột cho thuộc tính persistent.

Khi dùng constructor mapping, hãy bảo đảm constructor có thể được Spring Data chọn và các tham số tương ứng với property của entity. Không đổi tên tham số Java theo tên cột vật lý chỉ để khớp schema.

## 10. Chọn đúng annotation package

Một lỗi dễ gặp trong dự án dùng nhiều công nghệ persistence là import nhầm `@Column` của JPA.

Spring Data Relational dùng:

~~~java
import org.springframework.data.relational.core.mapping.Column;
~~~

JPA dùng:

~~~java
import jakarta.persistence.Column;
~~~

Hai annotation thuộc hai cơ chế mapping khác nhau. Nếu entity được Spring Data R2DBC quản lý, hãy dùng annotation của Spring Data Relational. Annotation JPA không thay thế mapping metadata của Spring Data Relational.

Điều này đặc biệt quan trọng khi một dự án có cả module JPA/JDBC và R2DBC. Mỗi entity nên được thiết kế theo persistence technology quản lý nó; không giả định annotation của một framework tự động có ý nghĩa trong framework còn lại.

## 11. Những trường hợp không nên dùng @Column

Không cần dùng `@Column` trong các tình huống sau:

- Tên cột đã khớp naming strategy và không có yêu cầu thể hiện mapping tường minh.
- Thuộc tính được đánh dấu `@Transient` và không được lưu trong database.
- Thuộc tính là dữ liệu tính toán chỉ tồn tại trong ứng dụng.
- Bạn muốn đổi tên bảng; hãy dùng `@Table`.
- Bạn muốn thay đổi kiểu SQL hoặc format giá trị; hãy xem schema và custom conversions.
- Bạn muốn viết SQL tùy chỉnh; hãy dùng đúng identifier vật lý trong câu SQL.
- Bạn muốn tạo hoặc đổi tên cột; hãy thực hiện migration schema.

Annotation nên mô tả mapping thực sự cần thiết, không thay thế trách nhiệm của các lớp persistence khác.

## 12. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng `jakarta.persistence.Column` cho entity R2DBC | Annotation thuộc JPA mapping | Import `org.springframework.data.relational.core.mapping.Column` |
| Ghi tên property Java vào `@Column` dù schema có tên khác | Mapping trỏ tới cột không tồn tại | Dùng đúng tên cột vật lý |
| Đổi `@Column` nhưng không chạy migration | Code và schema không đồng bộ | Cập nhật schema bằng migration |
| Đặt tên cột vật lý trong derived query method | Nhầm property name với column name | Dùng tên thuộc tính Java trong `findBy...` |
| Nghĩ `@Column` tự đổi SQL trong `@Query` | SQL viết tay không được annotation sửa lại | Dùng tên bảng/cột thật trong SQL |
| Dùng `@Column` để khai báo kiểu dữ liệu hoặc `NOT NULL` | Annotation chỉ mô tả mapping tên cột | Quản lý kiểu và constraint ở schema, converter |
| Bỏ qua chữ hoa/chữ thường và identifier quoting | Database xử lý identifier theo dialect | Kiểm tra schema và dùng quoting khi cần |
| Thêm annotation cho mọi property không theo quy ước | Mapping dư thừa, khó bảo trì | Dựa vào naming strategy; chỉ ghi đè khi cần |
| Dùng `@Column` trên dữ liệu không persistent | Nhầm thuộc tính ứng dụng với cột database | Dùng `@Transient` hoặc mô hình hóa property phù hợp |

## 13. Quy trình ánh xạ thuộc tính sang cột

Khi tạo hoặc cập nhật entity, hãy thực hiện theo trình tự:

1. Xác định bảng và schema thực tế mà entity sẽ truy cập.
2. Liệt kê property persistent của entity và tên cột tương ứng trong database.
3. Kiểm tra naming strategy mặc định để biết tên cột nào đã được suy ra đúng.
4. Dùng `@Column` cho property có tên cột khác quy tắc mặc định hoặc cần quoting.
5. Dùng đúng package annotation của Spring Data Relational.
6. Kiểm tra SQL viết tay và projection để bảo đảm dùng identifier phù hợp.
7. Cập nhật schema bằng migration nếu tên hoặc cấu trúc cột thay đổi.
8. Chạy integration test trên database tương thích để xác nhận insert, select và update.

Một bảng mapping đơn giản trong giai đoạn thiết kế giúp tránh nhầm lẫn:

| Property Java | Column database | Cách khai báo |
|---|---|---|
| `firstName` | `first_name` | Theo naming strategy mặc định hoặc `@Column` |
| `customerNumber` | `CUST_NO` | `@Column("CUST_NO")` |
| `registeredAt` | `registered_timestamp` | `@Column("registered_timestamp")` |
| `order` | `order` là từ khóa cần quote theo dialect | `@Column(value = "order", forceQuote = true)` nếu phiên bản hỗ trợ |

## 14. Ghi nhớ

- `@Column` của Spring Data Relational ánh xạ một property Java tới tên cột database.
- Annotation cần import từ `org.springframework.data.relational.core.mapping.Column`.
- Naming strategy mặc định thường chuyển camelCase thành snake_case; `@Column` ghi đè tên cột cho property cụ thể.
- `@Column` không đổi tên property Java, không đổi tên bảng và không tự sửa SQL viết tay.
- Derived query method dùng tên property Java; SQL trong `@Query` phải dùng identifier vật lý phù hợp với database.
- Dùng `forceQuote` khi cần quote identifier và phiên bản Spring Data Relational hỗ trợ thuộc tính này.
- Annotation không tạo cột, không khai báo constraint và không thay thế migration schema.
- Kiểu SQL và chuyển đổi giá trị thuộc schema, driver và custom conversions.
- Dùng đúng annotation package để tránh nhầm mapping của JPA với Spring Data R2DBC.

