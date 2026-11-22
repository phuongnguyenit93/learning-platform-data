# Lỗi chuyển đổi kiểu, constructor và thuộc tính không được ánh xạ

Spring Data Relational R2DBC chuyển dữ liệu giữa hàng trong database và object Java/Kotlin. Khi một truy vấn chạy được nhưng việc đọc hoặc ghi entity thất bại, nguyên nhân thường nằm ở ba phần: kiểu dữ liệu database không chuyển được sang kiểu thuộc tính, Spring Data không tạo được entity bằng constructor phù hợp, hoặc tên/cấu trúc thuộc tính không khớp với cột thực tế.

Những lỗi này có thể xuất hiện khi đọc một hàng, insert entity, cập nhật entity bất biến, ánh xạ projection hoặc thêm thuộc tính mới vào class mà chưa thay đổi schema. Chúng thường bị nhầm với lỗi SQL, nhưng nhiều trường hợp SQL đã chạy thành công và lỗi chỉ xảy ra ở bước convert result thành object.

Bài học này giải thích cách Spring Data R2DBC ánh xạ entity, cách chẩn đoán lỗi conversion và constructor, cách ánh xạ tên cột, xử lý thuộc tính không lưu, đăng ký custom converter, kiểm soát null và generated ID, cùng một quy trình tái hiện và sửa lỗi trên database thật.

## 1. Luồng ánh xạ dữ liệu trong Spring Data R2DBC

Khi repository đọc dữ liệu, kết quả đi qua nhiều lớp trước khi trở thành entity:

~~~text
SQL query
   |
   v
R2DBC driver
   |
   v
Row / RowMetadata
   |
   v
Spring Data MappingR2dbcConverter
   |
   +--> đọc metadata của entity
   +--> tìm constructor tạo object
   +--> chuyển từng giá trị sang kiểu Java
   +--> gán các thuộc tính còn lại
   |
   v
Entity Java/Kotlin
~~~

Khi ghi dữ liệu, chiều chuyển đổi ngược lại:

~~~text
Entity
   |
   v
Spring Data mapping metadata
   |
   +--> xác định table/column
   +--> bỏ qua thuộc tính không được ghi
   +--> chuyển Java value sang database value
   |
   v
OutboundRow / bind values
   |
   v
R2DBC driver
   |
   v
Database
~~~

Một lỗi trong hai luồng này có thể có cùng thông báo chung như conversion failed, cannot read property, no suitable constructor hoặc column not found. Cần xác định lỗi xảy ra ở bước nào trước khi thay đổi entity.

### 1.1. Phân biệt ba nhóm lỗi

| Nhóm | Dấu hiệu | Nơi cần kiểm tra |
|---|---|---|
| Type conversion | Không thể chuyển giá trị SQL sang kiểu thuộc tính hoặc ngược lại | SQL type, Java type, converter, driver |
| Constructor/object creation | Không tìm thấy constructor phù hợp hoặc thiếu tham số | Constructor, tên tham số, immutable property, Kotlin metadata |
| Property/column mapping | Không tìm thấy cột, sai tên cột hoặc thuộc tính không được xử lý như mong đợi | @Table, @Column, NamingStrategy, @Transient, schema |

Không nên sửa cả ba nhóm cùng lúc. Hãy dùng stack trace để xác định thao tác đọc hay ghi, sau đó kiểm tra mapping metadata và dữ liệu cụ thể.

## 2. Cách Spring Data xác định table và column

Spring Data Relational sử dụng metadata từ entity để xác định tên bảng, tên cột và cách ánh xạ thuộc tính. Các annotation thường gặp:

- `@Table`: chỉ định table.
- `@Column`: chỉ định column của property.
- `@Id`: đánh dấu khóa chính.
- `@Transient`: loại property khỏi persistent mapping.
- `@ReadOnlyProperty`: property được đọc nhưng không ghi.
- `@Version`: optimistic locking version.
- `@PersistenceCreator`: chọn constructor/factory method dùng để tạo entity.
- `@Embedded`: ánh xạ thuộc tính của object nhúng vào cùng hàng nếu mô hình và phiên bản hỗ trợ.

Ví dụ:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("email_address")
    private String email;

    @Column("full_name")
    private String fullName;
}
~~~

Tên table là customer; hai property được ánh xạ tường minh tới email_address và full_name.

Nếu không khai báo annotation, Spring Data áp dụng NamingStrategy của mapping context. Quy tắc mặc định thường chuyển tên Java theo quy ước relational, nhưng không nên giả định mọi project hoặc custom configuration đều giống nhau. Khi schema có tên cột đặc biệt, viết tường minh bằng @Column để giảm phụ thuộc vào naming convention.

### 2.1. Tên property không nhất thiết bằng tên cột

Ví dụ entity có property createdAt nhưng schema dùng created_on. Hãy chỉ rõ:

~~~java
@Column("created_on")
private LocalDateTime createdAt;
~~~

Nếu không chỉ rõ, query có thể tìm cột created_at và database báo lỗi column không tồn tại.

### 2.2. Tên table, schema và identifier

Khi table có tên khác tên class:

~~~java
@Table("sales_customer")
public class Customer {
    // ...
}
~~~

Nếu table nằm trong schema riêng, kiểm tra thuộc tính annotation và current schema của connection theo phiên bản Spring Data đang dùng. Đừng giải quyết lỗi bằng cách đổi tên table trong entity nếu migration thực tế đang tạo table ở schema khác.

Database có quy tắc khác nhau về identifier không quote và identifier được quote. Oracle thường chuẩn hóa identifier không quote thành uppercase; PostgreSQL thường chuẩn hóa thành lowercase. Identifier được quote có thể phân biệt hoa/thường. Nếu migration tạo tên cột có quote và chữ thường, tên đó có thể phải được tham chiếu chính xác.

## 3. Đọc stack trace để xác định lỗi xảy ra ở đâu

Không chỉ nhìn dòng đầu tiên của exception. Hãy tìm:

1. Exception gốc và cause sâu nhất.
2. Method repository đang chạy.
3. SQL statement hoặc operation được thực thi.
4. Property đang được convert nếu thông báo có nêu.
5. Kiểu Java đích và kiểu giá trị database.
6. Lỗi xảy ra khi bind outbound hay khi đọc inbound.

| Dấu hiệu | Hướng điều tra |
|---|---|
| No converter found capable of converting from/to | Thiếu custom converter hoặc source/target type không được hỗ trợ |
| Cannot decode value / unsupported type | Driver không hỗ trợ kiểu SQL hoặc kiểu Java đó |
| No suitable constructor / parameter mismatch | Constructor không khớp persistent properties |
| Column not found / invalid identifier | Sai tên column, schema hoặc quoting |
| Cannot set property / immutable property | Property không có setter/wither/constructor parameter phù hợp |
| Null value for primitive / conversion failure | Database trả NULL cho primitive hoặc constructor parameter không nullable |
| Duplicate/ambiguous mapping | Nhiều property trỏ cùng column hoặc mapping metadata xung đột |

Thông báo cụ thể khác nhau giữa driver và Spring Data release. Dùng exception class, cause và SQL thực tế thay vì dựa vào một chuỗi thông báo cố định.

### 3.1. Bật log có chọn lọc

Có thể tăng log cho phần Spring Data R2DBC trong môi trường phát triển:

~~~yaml
logging:
  level:
    org.springframework.data.r2dbc: DEBUG
    org.springframework.r2dbc.core: DEBUG
~~~

Tên logger và mức chi tiết tùy phiên bản. Log SQL giúp xác nhận statement và tên cột. Không bật logging nhạy cảm trong production hoặc ghi bind values chứa email, token, password và dữ liệu cá nhân.

Nếu query chạy thành công nhưng convert thất bại, cần xem tiếp type của từng cột và constructor được chọn.

## 4. Constructor được dùng để tạo entity

Spring Data không nhất thiết gọi constructor rỗng rồi setter từng field. Với entity có constructor phù hợp, framework có thể dùng constructor đó để tạo object trực tiếp từ persistent properties.

Các quy tắc lựa chọn constructor phụ thuộc kiểu class và phiên bản Spring Data, nhưng những trường hợp phổ biến gồm:

- Class có một constructor phù hợp: constructor đó thường được chọn.
- Có nhiều constructor: có thể đánh dấu constructor persistence bằng @PersistenceCreator.
- Có constructor không tham số: có thể được dùng khi không có constructor persistence được chỉ định theo quy tắc của framework.
- Java record: canonical constructor là lựa chọn tự nhiên.
- Kotlin: primary constructor thường được ưu tiên khi metadata Kotlin có sẵn.

Khi constructor được chọn, tên và kiểu tham số phải khớp với persistent properties. Một constructor không khớp có thể khiến framework không biết lấy cột nào cho tham số, hoặc chuyển đổi một giá trị sang sai kiểu.

### 4.1. Constructor nhiều tham số

~~~java
@Table("customer")
public class Customer {

    private final Long id;
    private final String email;
    private final String fullName;

    public Customer(Long id, String email, String fullName) {
        this.id = id;
        this.email = email;
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getFullName() {
        return fullName;
    }
}
~~~

Spring Data cần biết các tham số tương ứng với property nào. Tên tham số được giữ trong bytecode hoặc được cung cấp qua metadata phù hợp sẽ giúp framework thực hiện mapping.

Với Java, bật compiler option -parameters trong build để giữ tên tham số.

Gradle:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Maven compiler plugin có tùy chọn tương ứng:

~~~xml
<configuration>
    <parameters>true</parameters>
</configuration>
~~~

Tên tham số chỉ là một phần của mapping. Kiểu tham số cũng phải tương thích với giá trị được đọc từ database.

### 4.2. Chọn constructor tường minh bằng @PersistenceCreator

Khi class có nhiều constructor:

~~~java
@Table("customer")
public class Customer {

    private final Long id;
    private final String email;
    private final String fullName;

    public Customer(String email) {
        this(null, email, "Unknown");
    }

    @PersistenceCreator
    public Customer(Long id, String email, String fullName) {
        this.id = id;
        this.email = email;
        this.fullName = fullName;
    }

    // getters
}
~~~

Constructor được đánh dấu cho persistence mapping. Điều này giúp tránh việc framework chọn nhầm constructor tiện ích chỉ nhận một phần dữ liệu.

Không đánh dấu constructor chỉ để làm hết lỗi. Kiểm tra constructor đó có thể nhận đủ mọi property cần khôi phục từ database hay không.

### 4.3. Constructor parameter không khớp property

Ví dụ class có property fullName nhưng constructor đặt tham số name:

~~~java
public Customer(Long id, String email, String name) {
    this.id = id;
    this.email = email;
    this.fullName = name;
}
~~~

Spring Data cần mapping metadata xác định tham số name tương ứng với property nào. Không dựa vào ý nghĩa tự nhiên của tên. Hãy đổi tên tham số cho trùng persistent property hoặc cung cấp mapping metadata mà framework hỗ trợ.

## 5. Immutable entity, setter và wither

Entity bất biến có các field final và không có setter. Đây là cách thiết kế hợp lệ, nhưng constructor phải đủ để tạo entity và các thay đổi do persistence cần được biểu diễn qua cơ chế mà Spring Data hỗ trợ.

~~~java
@Table("customer")
public class Customer {

    @Id
    private final Long id;

    private final String email;

    @PersistenceCreator
    public Customer(Long id, String email) {
        this.id = id;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Khi framework cần cập nhật một property sau khi tạo object, chẳng hạn ID được database sinh, immutable entity cần có constructor hoặc wither phù hợp để tạo instance mới. Nếu property không thể được gán và không nằm trong persistence constructor, giá trị có thể không được cập nhật như mong đợi.

### 5.1. Dùng wither cho property bất biến

~~~java
public Customer withId(Long newId) {
    return new Customer(newId, email);
}
~~~

Một wither thường trả về instance mới với một property thay đổi. Spring Data có thể sử dụng cơ chế property accessor/wither theo mapping metadata và version.

Không nhầm wither với setter: setter sửa object hiện tại; wither tạo object khác. Nếu framework trả về instance mới, code ứng dụng phải sử dụng entity đã được lưu trả về thay vì tiếp tục giữ object cũ.

### 5.2. Lombok có thể làm constructor selection khó hiểu

Các annotation Lombok như @NoArgsConstructor, @AllArgsConstructor, @RequiredArgsConstructor và @Builder có thể tạo nhiều constructor hoặc factory method mà không hiện rõ trong source code.

Khi gặp lỗi constructor:

- Xem bytecode/decompiled class hoặc cấu hình Lombok delombok.
- Xác định constructor thực tế được sinh ra.
- Kiểm tra tên tham số có được giữ hay không.
- Chỉ định persistence constructor rõ ràng nếu cần.
- Không thêm @NoArgsConstructor chỉ để làm lỗi biến mất nếu entity bất biến cần constructor khác.

## 6. Java record và Kotlin data class

### 6.1. Java record

~~~java
@Table("customer")
public record Customer(
        @Id Long id,
        String email,
        @Column("full_name") String fullName) {
}
~~~

Record phù hợp với entity bất biến vì các component và canonical constructor được xác định rõ. Tên component là tên property, do đó cần khớp với mapping.

Nếu database sinh ID, kiểm tra Spring Data version và generated-value handling có tạo được record mới với ID được trả về hay không. Test insert rồi xác nhận object trả về có ID.

### 6.2. Kotlin data class

~~~kotlin
@Table("customer")
data class Customer(
    @Id val id: Long? = null,
    val email: String,
    @Column("full_name") val fullName: String
)
~~~

Spring Data có hỗ trợ Kotlin constructor mapping khi Kotlin reflection/metadata và dependency phù hợp được đưa vào classpath. Primary constructor thường là nguồn mapping chính.

Các điểm cần kiểm tra:

- Kotlin plugin và Spring plugin tương thích.
- Kotlin reflection có được khai báo nếu cần.
- Property nullable có khớp nullability của cột không.
- Default parameter có được sử dụng theo semantics mong muốn không.
- Constructor parameter có tên trùng property và column mapping không.
- Generated ID có được phản ánh trong instance trả về không.

Không giả định default value trong Kotlin sẽ tự động thay thế mọi SQL NULL. Giá trị mặc định và giá trị null là hai tình huống khác nhau.

## 7. Column mapping bằng @Column

Dùng @Column khi tên cột không theo naming convention, là từ khóa dành riêng hoặc cần giữ mapping ổn định giữa các môi trường.

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    @Column("created_on")
    private LocalDateTime createdAt;
}
~~~

Tên trong annotation phải khớp schema sau khi database áp dụng quy tắc identifier. Nếu database phân biệt quoted identifier, kiểm tra cách dialect quote tên.

### 7.1. Alias trong query tùy chỉnh

Với native query hoặc projection, alias phải tương thích với property mapping mong muốn.

~~~sql
SELECT
    o.id AS id,
    o.order_number AS order_number,
    o.created_on AS created_on
FROM purchase_order o
WHERE o.id = :id
~~~

Cách bind placeholder tùy dialect/DatabaseClient. Ví dụ minh họa phần alias. Không giả định alias được tự động đổi từ snake_case sang camelCase trong mọi custom mapping path; kiểm tra metadata và converter đang sử dụng.

### 7.2. Một cột không nên ánh xạ tùy tiện vào nhiều property

Nếu hai property cùng trỏ tới một column, việc ghi có thể mơ hồ hoặc một property không được xử lý như mong đợi. Nếu cần một biểu diễn khác của cùng dữ liệu, dùng property computed/transient hoặc converter có chủ đích.

## 8. Thuộc tính không được ánh xạ

Không phải mọi field trong entity đều là cột database. Một số field được tính từ dữ liệu khác, giữ trạng thái tạm thời hoặc chỉ phục vụ ứng dụng.

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String firstName;
    private String lastName;

    @Transient
    private String displayName;

    public String getDisplayName() {
        return firstName + " " + lastName;
    }
}
~~~

@Transient báo cho Spring Data không coi property đó là persistent column. Nếu không đánh dấu, mapping context có thể cố tìm column cùng tên và truy vấn/đọc dữ liệu thất bại.

### 8.1. Phân biệt @Transient với Java transient

Java keyword transient chủ yếu ảnh hưởng Java serialization. Annotation org.springframework.data.annotation.Transient dành cho persistent mapping của Spring Data.

Không dùng hai khái niệm thay thế cho nhau. Khi cần loại property khỏi mapping R2DBC, dùng annotation Spring Data phù hợp.

### 8.2. Property tính toán từ nhiều cột

Nếu display name được tính từ first name và last name, có thể:

- Dùng getter tính toán và đánh dấu property không persistent nếu mapping phát hiện property đó.
- Dùng DTO/projection cho truy vấn có alias computed.
- Tính ở service sau khi entity được đọc.

Đừng tạo cột database chỉ để giải quyết một property computed nếu nghiệp vụ không yêu cầu lưu giá trị đó.

### 8.3. Thuộc tính chỉ đọc

@ReadOnlyProperty dùng cho property có thể được đọc từ database nhưng không được ghi bởi Spring Data. Ví dụ property do database view hoặc generated expression cung cấp.

~~~java
@ReadOnlyProperty
@Column("display_label")
private String displayLabel;
~~~

Đảm bảo query đọc thực sự trả column đó. Nếu column không tồn tại trong bảng hoặc projection, annotation read-only không tự tạo ra giá trị.

### 8.4. Thuộc tính chỉ insert

Một số phiên bản Spring Data Relational cung cấp @InsertOnlyProperty để chỉ ghi property khi insert và không cập nhật trong update. Chỉ sử dụng nếu phiên bản dự án có annotation này và semantics phù hợp.

Ví dụ trường hợp created-by hoặc giá trị ban đầu không nên thay đổi sau insert. Không dùng annotation này để thay thế auditing nếu cần quản lý created/modified timestamps theo chuẩn.

## 9. Property không được đọc vì không có trong SELECT

Khi dùng custom query, entity mapping chỉ có thể lấy những cột mà result set cung cấp.

Ví dụ entity yêu cầu id, email, full_name và status, nhưng query chỉ select:

~~~sql
SELECT id, email
FROM customer
WHERE id = :id
~~~

Nếu ánh xạ kết quả thành full entity, các property còn thiếu có thể nhận null/default hoặc gây lỗi tùy constructor và mapping path. Một constructor yêu cầu đầy đủ tham số có thể không được tạo đúng.

Có ba cách xử lý:

1. Select đầy đủ các cột cần cho entity.
2. Dùng projection/DTO riêng chỉ chứa các cột được select.
3. Dùng custom row mapping có chủ đích.

Không dùng entity đầy đủ cho mọi query projection nếu query chỉ trả một phần dữ liệu.

### 9.1. Projection interface và DTO

~~~java
public interface CustomerNameView {
    Long getId();
    String getFullName();
}
~~~

Một DTO/record có thể phù hợp hơn khi query cần định nghĩa rõ kiểu trả về. Cú pháp và hỗ trợ projection phụ thuộc cách query và phiên bản Spring Data R2DBC; kiểm tra repository query mapping thực tế.

Không giả định projection tự động chuyển mọi alias hoặc nested property giống JPA.

## 10. Các kiểu dữ liệu đơn giản và custom value object

Spring Data R2DBC hỗ trợ nhiều kiểu đơn giản thông qua dialect, driver và conversion service. Tuy nhiên, một kiểu Java hợp lệ không đồng nghĩa mọi driver đều có thể bind/đọc nó.

| Nhóm dữ liệu | Ví dụ Java | Điểm cần kiểm tra |
|---|---|---|
| Số nguyên | Integer, Long, BigInteger | Precision, signed range, overflow |
| Số thập phân | BigDecimal | Precision và scale |
| Chuỗi | String, Character | Length, encoding, fixed-char padding |
| Boolean | Boolean | SQL type và driver representation |
| Ngày giờ | LocalDate, LocalDateTime, OffsetDateTime, Instant | Timezone, precision, semantics của database |
| Binary | byte[] | Độ dài, BLOB/RAW và memory |
| UUID | UUID | Native UUID hay textual/binary representation |
| Enum | Enum | String name hay mã nghiệp vụ |
| JSON/domain object | Json, String, custom class | Driver-specific type và custom converter |
| Value object | Money, EmailAddress, CustomerCode | Cần converter nếu không phải simple type |

Nếu lỗi conversion xuất hiện ở một property mới, hãy kiểm tra SQL type của column và Java type của property trước. Không đổi kiểu Java một cách thử-sai mà chưa xác định giá trị database thực tế.

## 11. Nullability và primitive type

Database column có thể chứa SQL NULL. Java primitive như long, int và boolean không biểu diễn null.

Ví dụ không an toàn nếu column nullable:

~~~java
private long loyaltyPoints;
~~~

Nếu database trả NULL, Spring Data không thể biểu diễn đúng giá trị đó bằng primitive. Tùy đường mapping, lỗi có thể xuất hiện trong conversion/constructor hoặc giá trị không thể được gán.

Dùng wrapper khi cột nullable:

~~~java
private Long loyaltyPoints;
private Boolean verified;
~~~

Nếu nghiệp vụ yêu cầu column không null:

- Khai báo NOT NULL trong schema.
- Đặt default nếu phù hợp.
- Validate trước khi ghi.
- Giữ Java property ở kiểu phù hợp với invariant.

### 11.1. Constructor parameter nullable

Một constructor nhận primitive cũng không thể nhận SQL NULL:

~~~java
public Customer(Long id, String email, long loyaltyPoints) {
    // ...
}
~~~

Nếu column nullable, dùng Long hoặc thay đổi schema/invariant. Với Kotlin, khai báo Long? khi column có thể null; khai báo Long khi schema và nghiệp vụ bảo đảm có giá trị.

### 11.2. Phân biệt NULL, thiếu column và default value

Ba trường hợp này không giống nhau:

- SQL NULL: column có mặt trong result nhưng giá trị là null.
- Thiếu column: query không select column.
- Default value: database hoặc constructor cung cấp một giá trị mặc định.

Khi chẩn đoán, chạy query trực tiếp để xác nhận column có tồn tại trong result và giá trị có null không.

## 12. Enum mapping

Spring Data thường có conversion cho enum, nhưng cách lưu mặc định và khả năng của driver cần được xác nhận trong phiên bản cụ thể. Nhiều mô hình lưu enum bằng tên constant dạng chuỗi.

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

Column:

~~~sql
status VARCHAR(20) NOT NULL
~~~

Entity:

~~~java
@Column("status")
private OrderStatus status;
~~~

Nếu database lưu mã riêng như N, P, C thay vì tên enum, cần custom converter. Không dùng ordinal vị trí enum làm hợp đồng lưu trữ bền vững: thêm hoặc đổi thứ tự constant có thể làm dữ liệu cũ mang nghĩa khác.

Khi đổi tên enum constant, kiểm tra dữ liệu hiện có và migration. Converter có thể hỗ trợ backward compatibility cho các mã cũ.

## 13. Custom converter khi Java type và SQL type không khớp

Khi domain dùng value object như Money, EmailAddress hoặc OrderCode, Spring Data có thể không biết cách chuyển đổi trực tiếp sang SQL value. Hãy tạo converter tường minh.

Ví dụ value object:

~~~java
public record EmailAddress(String value) {
    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("email is required");
        }
    }
}
~~~

Converter ghi:

~~~java
@WritingConverter
public class EmailAddressWritingConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

Converter đọc:

~~~java
@ReadingConverter
public class EmailAddressReadingConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

Annotation direction giúp Spring Data phân biệt conversion đi vào database và conversion đi ra từ database. Với source/target type mơ hồ, khai báo hướng rõ ràng.

### 13.1. Đăng ký converter

Trong cấu hình Spring Data R2DBC, custom converters phải được đưa vào R2dbcCustomConversions tương ứng với dialect của database.

Một dạng cấu hình thường gặp:

~~~java
@Bean
R2dbcCustomConversions r2dbcCustomConversions() {
    return R2dbcCustomConversions.of(
            PostgresDialect.INSTANCE,
            List.of(
                    new EmailAddressWritingConverter(),
                    new EmailAddressReadingConverter()));
}
~~~

Ví dụ dùng PostgreSQL dialect. Khi dùng Oracle hoặc database khác, phải dùng dialect tương ứng và API phù hợp với Spring Data release đang dùng. Spring Boot có thể tự cấu hình bean này; kiểm tra auto-configuration trước khi khai báo bean mới để tránh tạo cấu hình xung đột.

Nếu dùng extension point của AbstractR2dbcConfiguration, có thể đăng ký custom converters qua hook tương ứng. Không cấu hình thêm một connection factory ngoài ý muốn chỉ để lấy converter hook khi ứng dụng đã dùng Spring Boot auto-configuration.

### 13.2. Converter phải round-trip được

~~~java
@Test
void convertsEmailAddressToAndFromDatabaseValue() {
    EmailAddress value = new EmailAddress("dev@example.test");

    String stored = writingConverter.convert(value);
    EmailAddress restored = readingConverter.convert(stored);

    assertThat(stored).isEqualTo("dev@example.test");
    assertThat(restored).isEqualTo(value);
}
~~~

Sau unit test converter, thêm integration test với database thật để xác nhận driver bind và đọc kiểu SQL đó đúng.

### 13.3. Converter cho enum mã hóa

~~~java
public enum OrderStatus {
    NEW("N"),
    PAID("P"),
    CANCELLED("C");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        return Arrays.stream(values())
                .filter(status -> status.code.equals(code))
                .findFirst()
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Unknown order status code"));
    }
}
~~~

Writing converter:

~~~java
@WritingConverter
public class OrderStatusWritingConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return source.code();
    }
}
~~~

Reading converter:

~~~java
@ReadingConverter
public class OrderStatusReadingConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromCode(source);
    }
}
~~~

Xác định cách xử lý mã không biết. Nếu dữ liệu cũ có thể chứa code mới hơn ứng dụng, có thể cần enum UNKNOWN hoặc một lỗi domain rõ ràng. Không âm thầm đổi mọi mã lạ thành NEW.

## 14. JSON, ARRAY và kiểu database-specific

Một số database có kiểu đặc thù như JSON/JSONB, ARRAY, XML, enum native, spatial hoặc object type. Driver có thể trả về wrapper riêng thay vì String/byte[] thông thường.

Cách xử lý:

1. Xác nhận SQL type thật của column.
2. Đọc tài liệu mapping của R2DBC driver đang dùng.
3. Kiểm tra kiểu object mà driver trả về trong Row.
4. Chọn domain representation.
5. Viết reading/writing converter nếu cần.
6. Test null, empty, dữ liệu lớn và round-trip.
7. Kiểm tra query operator/index riêng của database.

Không giả định JSON trong PostgreSQL và JSON trong Oracle có cùng Java mapping. Không giả định ARRAY có thể map thẳng thành List<T> ở mọi driver.

Nếu dùng kiểu driver-specific trong converter, đặt dependency đó trong adapter persistence để domain model không phụ thuộc toàn bộ driver API.

## 15. Ngày giờ, timezone và precision

Lỗi mapping thời gian thường không chỉ là lỗi convert mà còn là mất semantics.

- LocalDate: ngày lịch, không có giờ.
- LocalTime: giờ trong ngày, không có ngày.
- LocalDateTime: ngày giờ không kèm offset/zone.
- OffsetDateTime: ngày giờ kèm offset.
- Instant: một thời điểm trên timeline UTC.

Database có thể phân biệt DATE, TIME, TIMESTAMP, TIMESTAMP WITH TIME ZONE hoặc kiểu riêng. Ý nghĩa của DATE khác giữa các hệ quản trị. Ví dụ Oracle DATE có cả phần thời gian tới giây, trong khi DATE ở nhiều database khác chỉ biểu diễn ngày.

Kiểm tra:

- SQL type và precision.
- Có timezone hay không.
- Session timezone.
- Driver conversion có hỗ trợ kiểu Java đó không.
- Giá trị được làm tròn/cắt phần nano/microseconds ra sao.
- Có cần converter riêng để giữ Instant/OffsetDateTime không.

Đừng chuyển LocalDateTime thành UTC một cách ngầm định nếu schema không chứa timezone và ứng dụng chưa định nghĩa quy ước.

## 16. BigDecimal, precision và scale

Một cột DECIMAL/NUMERIC/NUMBER có precision và scale. Java BigDecimal có thể giữ precision nhưng mapping cần tương thích với schema và driver.

~~~sql
amount DECIMAL(19, 4) NOT NULL
~~~

Java:

~~~java
private BigDecimal amount;
~~~

Kiểm tra:

- Giá trị có nhiều chữ số hơn precision không?
- Có nhiều chữ số thập phân hơn scale không?
- Database làm tròn hay từ chối?
- Converter có vô tình gọi doubleValue() không?
- JSON serializer có giữ số thập phân chính xác không?

Không map tiền sang double/float. Nếu cần quy tắc làm tròn nghiệp vụ, thực hiện rõ bằng BigDecimal và RoundingMode trước khi ghi.

## 17. Generated ID và entity constructor

Khi database sinh khóa chính, entity thường có property được đánh dấu @Id. Với ID chưa được gán, kiểu wrapper như Long thường phù hợp hơn primitive long vì có thể biểu diễn null trước insert.

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String email;

    // constructor, getters
}
~~~

Khi insert, Spring Data/driver/dialect phối hợp để xử lý generated value theo khả năng database. Không giả định mọi driver hỗ trợ cùng một chiến lược hoặc cùng API trả generated keys.

Sau save, dùng entity được publisher phát ra:

~~~java
return customerRepository.save(customer)
        .doOnNext(saved ->
                log.debug("Generated customer id: {}", saved.getId()));
~~~

Không tiếp tục dùng object đầu vào rồi giả định nó đã được mutate. Với entity immutable, framework có thể tạo instance mới chứa ID được sinh.

### 17.1. ID primitive có thể gây nhầm lẫn

Primitive long mặc định là 0, không phải null. Một số chiến lược persistence dùng trạng thái ID để phân biệt entity mới/cũ. ID bằng 0 có thể không mang ý nghĩa “chưa có ID” như code đang giả định.

Dùng wrapper hoặc chiến lược nhận diện entity mới phù hợp, và test insert/update trên database thật.

### 17.2. Generated property phải có thể được cập nhật

Nếu entity immutable, kiểm tra ID nằm trong persistence constructor hoặc có wither/property accessor phù hợp. Nếu không, insert có thể thành công nhưng object trả về không có ID mong muốn.

Không sửa bằng cách tự query SELECT MAX(id), vì request đồng thời có thể đọc ID của transaction khác.

## 18. Version property và auditing

Các property đặc biệt như @Version, @CreatedDate, @LastModifiedDate, @CreatedBy và @LastModifiedBy có quy tắc riêng.

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version;

    @CreatedDate
    private LocalDateTime createdAt;

    @LastModifiedDate
    private LocalDateTime updatedAt;
}
~~~

Nếu các field này không được populate như mong đợi, kiểm tra:

- Auditing đã được enable chưa.
- Reactive auditor provider có đúng kiểu không.
- Callback được đăng ký trong application context chưa.
- Property có tên/cột phù hợp không.
- Database column có kiểu và nullability đúng không.
- Có custom insert/update query bỏ qua callback hoặc field không.

@Version cần kiểu và column tương thích với optimistic locking strategy. Không tự sửa version trong service nếu Spring Data đang quản lý nó.

## 19. @Transient, @ReadOnlyProperty và @InsertOnlyProperty khác nhau

| Annotation | Đọc từ database | Ghi khi insert | Ghi khi update |
|---|---:|---:|---:|
| Không annotation | Có, nếu là persistent property | Có theo mapping | Có theo mapping |
| @Transient | Không | Không | Không |
| @ReadOnlyProperty | Có | Không | Không |
| @InsertOnlyProperty | Có | Có | Không |

Bảng mô tả mục đích chung; xác nhận annotation có trong phiên bản Spring Data Relational của dự án và xem semantics chính xác trong release đó.

Không dùng @Transient nếu bạn muốn đọc giá trị do database tạo. Dùng read-only mapping khi column phải được đọc nhưng không ghi. Không dùng read-only cho property mà ứng dụng cần insert.

## 20. Nested object và quan hệ entity

Spring Data Relational không hoạt động giống JPA với lazy proxy và object graph tự động. Một property kiểu object khác không tự động có nghĩa framework sẽ join và nạp entity liên quan.

~~~java
public class Customer {
    private Long id;
    private Address address;
}
~~~

Nếu Address là value object được nhúng, cần mapping embedded phù hợp và schema chứa các cột tương ứng. Nếu Address là entity riêng, thường lưu foreign key/customer ID và truy vấn riêng qua repository/service.

Các cách xử lý:

- Embedded value object với annotation/configuration được Spring Data Relational hỗ trợ.
- Custom converter nếu toàn bộ object được lưu trong một column dạng JSON/text.
- DTO/projection cho query join.
- Query riêng để nạp aggregate/related data.
- Service composition bằng Mono/Flux.

Không thêm property entity quan hệ rồi mong Spring Data R2DBC tự tạo join hoặc lazy loading như Hibernate.

### 20.1. Embedded property

Nếu dùng @Embedded, kiểm tra prefix, null handling và cách column name được tạo. Một embedded object có thể gồm nhiều column; constructor của object nhúng và constructor của root entity đều cần mapping phù hợp.

Nếu object nhúng toàn null, xác định chính sách khi tạo instance: null hay object rỗng. Cấu hình embedded on-empty/nullable tùy API version và test cả hàng có dữ liệu lẫn hàng không có dữ liệu.

## 21. Sai khác giữa schema và entity

Một nguyên nhân phổ biến là entity đã thay đổi nhưng migration chưa được cập nhật, hoặc database test đang chạy schema cũ.

~~~java
@Column("preferred_language")
private String preferredLanguage;
~~~

Nhưng database chưa có column preferred_language. Query đọc hoặc insert có thể thất bại.

Quy trình kiểm tra:

1. Xem migration mới nhất đã chạy chưa.
2. Kiểm tra schema/database mà ứng dụng thực sự kết nối.
3. Đọc metadata cột từ database.
4. So sánh tên, type, precision, scale và nullability.
5. Kiểm tra profile test/dev và URL.
6. Xác nhận migration được chạy theo đúng thứ tự.

Không chỉ thêm cột trực tiếp bằng tay vào database developer nếu migration của repository chưa được cập nhật. Làm vậy khiến môi trường khác tiếp tục lỗi.

## 22. Kiểm tra row metadata và kiểu driver trả về

Khi chưa rõ driver trả kiểu gì, tạo một test nhỏ dùng DatabaseClient hoặc R2DBC SPI để đọc giá trị và xem metadata.

~~~java
databaseClient.sql("""
        SELECT amount, status, created_at
        FROM purchase_order
        WHERE id = :id
        """)
        .bind("id", orderId)
        .map((row, metadata) -> {
            Object amount = row.get("amount");
            Object status = row.get("status");
            Object createdAt = row.get("created_at");

            return new RawValues(
                    amount == null ? null : amount.getClass().getName(),
                    status == null ? null : status.getClass().getName(),
                    createdAt == null ? null : createdAt.getClass().getName());
        })
        .one();
~~~

API Row.get overload và việc lấy metadata cần điều chỉnh theo driver/R2DBC SPI version. Đoạn này chỉ nhằm xác định runtime type, không nên giữ debug raw-value logging trong production.

Có thể dùng RowMetadata để xem tên cột và type metadata mà driver công bố. Tên label/casing có thể khác theo database và alias.

## 23. Mapping custom query khác mapping repository CRUD

Repository CRUD thường dùng mapping metadata của aggregate/entity. Custom query có thể:

- Trả toàn bộ entity.
- Trả projection.
- Trả scalar.
- Trả alias tùy chỉnh.
- Trả một phần cột.

Không mặc định các đường này có cùng semantics. Nếu custom query trả projection, tạo kiểu projection phù hợp thay vì ép thành entity đầy đủ.

Ví dụ scalar:

~~~java
@Query("SELECT COUNT(*) FROM customer")
Mono<Long> countCustomers();
~~~

Kiểu kết quả thực tế phải tương thích với dialect/driver. Nếu database trả numeric wrapper khác, có thể cần conversion hoặc chọn kiểu tổng quát rồi chuyển đổi có kiểm soát.

Khi query trả column alias, kiểm tra tên alias và cách Spring Data map sang constructor/property.

## 24. Tái hiện lỗi conversion bằng test nhỏ

Đừng bắt đầu bằng việc chạy toàn bộ application. Tạo một test tập trung vào một row và một property.

~~~java
@Test
void readsCustomerEmail() {
    StepVerifier.create(customerRepository.findById(42L))
            .assertNext(customer ->
                    assertThat(customer.getEmail())
                            .isEqualTo("dev@example.test"))
            .verifyComplete();
}
~~~

Nếu lỗi, tạo query nhỏ:

~~~java
StepVerifier.create(
        databaseClient.sql("""
                SELECT email_address
                FROM customer
                WHERE id = :id
                """)
                .bind("id", 42L)
                .map((row, metadata) ->
                        row.get("email_address"))
                .one())
        .expectNextCount(1)
        .verifyComplete();
~~~

Sau đó kiểm tra type thực tế. Nếu query đọc được raw value nhưng repository entity mapping lỗi, vấn đề nhiều khả năng nằm ở converter, property metadata hoặc constructor.

### 24.1. Test writing converter riêng

Trước khi test insert toàn entity, test converter source-to-target bằng unit test. Sau đó test binding bằng DatabaseClient và cuối cùng test repository save.

Đi theo từng bước giúp xác định lỗi ở conversion service, driver bind hay entity metadata.

### 24.2. Test constructor mapping riêng

Tạo một row fixture đầy đủ và đọc entity qua repository. Thử các tình huống:

- Constructor duy nhất.
- Nhiều constructor và @PersistenceCreator.
- Parameter name bị thiếu.
- Property nullable.
- Immutable property có/không có wither.
- Record hoặc Kotlin data class nếu dự án sử dụng.

Không viết test giả lập nội bộ framework quá sâu. Hãy ưu tiên kiểm tra hành vi mapping qua API public của repository/DatabaseClient.

## 25. Quy trình chẩn đoán theo từng bước

Khi gặp lỗi chuyển đổi kiểu, constructor hoặc property mapping:

1. **Xác định thao tác:** lỗi xảy ra khi đọc, insert, update hay delete?
2. **Tìm exception gốc:** đọc cause chain và xác định property/type được nhắc đến.
3. **Xem SQL:** query có chọn đúng column và alias không?
4. **Kiểm tra schema:** tên, SQL type, precision, scale, nullability và schema owner.
5. **Kiểm tra entity metadata:** @Table, @Column, @Id, NamingStrategy và annotation loại trừ.
6. **Kiểm tra constructor:** constructor nào được chọn, tên/thứ tự/kiểu tham số có phù hợp không?
7. **Kiểm tra nullability:** database có thể trả NULL cho primitive hoặc non-null parameter không?
8. **Kiểm tra driver:** runtime type của Row có đúng như dự kiến không?
9. **Kiểm tra converter:** built-in conversion có hỗ trợ không; custom converter có đúng chiều không?
10. **Tạo test tối thiểu:** đọc raw column, test converter và test entity mapping riêng.
11. **Sửa nguồn sự thật:** cập nhật entity, converter hoặc migration tương ứng.
12. **Chạy lại integration test:** dùng đúng database và R2DBC driver mục tiêu.

Không sửa lỗi bằng cách đổi hàng loạt field thành String. Cách đó có thể che mapping mismatch và đẩy lỗi sang business logic.

## 26. Bảng lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| No converter found | Domain type chưa có converter | Viết reading/writing converter và đăng ký |
| Unsupported SQL type | Driver không hỗ trợ type hoặc trả wrapper riêng | Kiểm tra driver mapping, dùng adapter/converter |
| Constructor không được tìm thấy | Nhiều constructor hoặc không có constructor phù hợp | Đánh dấu @PersistenceCreator, đơn giản hóa constructor |
| Tham số constructor nhận sai giá trị | Tên parameter không khớp property hoặc metadata bị mất | Bật -parameters, sửa tên, dùng persistence constructor |
| Record insert xong nhưng ID không có | Generated value/dialect hoặc immutable mapping | Kiểm tra generated key support và instance trả về |
| Cột không tồn tại | @Column/NamingStrategy/schema lệch | So sánh SQL thực tế với migration |
| Property computed bị tìm như column | Thiếu @Transient hoặc mapping phù hợp | Đánh dấu transient hoặc dùng DTO/projection |
| Property chỉ đọc bị ghi | Thiếu read-only mapping | Dùng @ReadOnlyProperty nếu đúng semantics |
| Column nullable gây lỗi | Java primitive hoặc constructor parameter không nhận null | Dùng wrapper/nullable type hoặc NOT NULL constraint |
| Enum conversion thất bại | Database lưu code khác enum name | Viết converter hai chiều |
| Timestamp lệch giờ | Sai kiểu timezone hoặc session setting | Chọn Java type/schema phù hợp, test round-trip |
| BigDecimal bị làm tròn | Precision/scale không khớp | Sửa schema hoặc quy tắc rounding |
| Query custom trả thiếu field | Map partial row vào full entity | Dùng projection hoặc select đủ cột |
| Nested object không được nạp | Mong đợi quan hệ tự động như ORM | Dùng embedded, converter, join projection hoặc query riêng |
| Chỉ lỗi ở một môi trường | Schema, driver hoặc naming khác | So sánh database/version/profile/metadata |
| Converter ghi đúng nhưng đọc sai | Chỉ đăng ký một chiều hoặc sai source type | Đăng ký reading và writing converter |
| Cấu hình converter không có tác dụng | Bean không được Spring Data sử dụng | Kiểm tra R2dbcCustomConversions và auto-configuration |

## 27. Ví dụ tổng hợp: ánh xạ entity có value object

Giả sử bảng:

~~~sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email_address VARCHAR(200) NOT NULL UNIQUE,
    status_code VARCHAR(10) NOT NULL,
    display_name VARCHAR(150),
    created_at TIMESTAMP NOT NULL
);
~~~

Domain model:

~~~java
public record EmailAddress(String value) {
    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("email is required");
        }
    }
}
~~~

~~~java
public enum CustomerStatus {
    ACTIVE("A"),
    SUSPENDED("S");

    private final String code;

    CustomerStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static CustomerStatus fromCode(String code) {
        return switch (code) {
            case "A" -> ACTIVE;
            case "S" -> SUSPENDED;
            default -> throw new IllegalArgumentException(
                    "Unknown customer status code");
        };
    }
}
~~~

Entity:

~~~java
@Table("customer")
public class Customer {

    @Id
    private final Long id;

    @Column("email_address")
    private final EmailAddress email;

    @Column("status_code")
    private final CustomerStatus status;

    @ReadOnlyProperty
    @Column("display_name")
    private final String displayName;

    @Column("created_at")
    private final LocalDateTime createdAt;

    @PersistenceCreator
    public Customer(
            Long id,
            EmailAddress email,
            CustomerStatus status,
            String displayName,
            LocalDateTime createdAt) {
        this.id = id;
        this.email = email;
        this.status = status;
        this.displayName = displayName;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public EmailAddress getEmail() {
        return email;
    }

    public CustomerStatus getStatus() {
        return status;
    }

    public String getDisplayName() {
        return displayName;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public Customer withId(Long newId) {
        return new Customer(
                newId, email, status, displayName, createdAt);
    }
}
~~~

Cấu hình cần đảm bảo:

- Database column names khớp @Column.
- ID được database sinh và driver/dialect trả generated value phù hợp.
- EmailAddress có converter hai chiều String.
- CustomerStatus có converter hai chiều code.
- display_name được đọc nhưng không ghi.
- Constructor parameter names giữ nguyên hoặc có metadata phù hợp.
- created_at có SQL type và Java time type tương thích.

Test mapping nên insert customer, nhận entity đã lưu, xác nhận ID, đọc lại từ database và so sánh value objects. Nếu database sinh display_name, kiểm tra query/read path thực sự trả column đó; @ReadOnlyProperty không tự tạo giá trị.

## 28. Những nguyên tắc để tránh lỗi mapping tái diễn

- Dùng migration làm nguồn sự thật cho schema.
- Khai báo @Column cho tên cột không theo convention.
- Dùng @PersistenceCreator khi class có nhiều constructor.
- Bật Java compiler parameter metadata khi cần constructor parameter name.
- Dùng wrapper/nullable type cho column có thể NULL.
- Dùng immutable entity có constructor/wither rõ ràng.
- Đánh dấu property computed bằng @Transient.
- Phân biệt property chỉ đọc và property không persistent.
- Viết converter hai chiều cho domain value object.
- Không lưu enum ordinal; dùng tên hoặc mã ổn định.
- Kiểm tra SQL type, precision, scale và timezone.
- Dùng DTO/projection cho custom query trả một phần cột.
- Không mong đợi tự động lazy-load quan hệ như JPA.
- Kiểm tra generated ID qua entity được save trả về.
- Test trên đúng R2DBC driver/database production.
- Không log dữ liệu nhạy cảm trong quá trình chẩn đoán.

## 29. Ghi nhớ

- Spring Data R2DBC chuyển đổi dữ liệu qua driver, mapping metadata, constructor và conversion service.
- Lỗi mapping thường thuộc một trong ba nhóm: type conversion, constructor/object creation hoặc column/property mapping.
- @Table và @Column xác định table/column; NamingStrategy quyết định quy ước tên mặc định.
- @PersistenceCreator giúp chọn constructor persistence khi có nhiều constructor.
- Java constructor parameter names cần metadata phù hợp; compiler option -parameters giúp giữ tên.
- Record canonical constructor và Kotlin primary constructor có thể hỗ trợ mapping bất biến khi dependency/metadata phù hợp.
- Entity immutable cần constructor/property accessor/wither phù hợp, đặc biệt với generated ID.
- @Transient loại property khỏi persistence mapping; Java transient không thay thế annotation này.
- @ReadOnlyProperty dùng cho property được đọc nhưng không ghi; @InsertOnlyProperty chỉ có trên các phiên bản hỗ trợ và có semantics riêng.
- Custom query trả thiếu column nên dùng projection/DTO thay vì ép vào full entity.
- SQL NULL không thể ánh xạ an toàn vào primitive; dùng wrapper hoặc ràng buộc NOT NULL.
- Custom domain type cần reading/writing converter và đăng ký trong R2dbcCustomConversions phù hợp dialect.
- Enum code, JSON, ARRAY, UUID và thời gian cần xác nhận theo driver/database thực tế.
- BigDecimal cần precision/scale đúng; thời gian cần quy ước timezone rõ ràng.
- Dùng RowMetadata/raw value test để xác định kiểu driver trả về.
- Chẩn đoán theo thứ tự SQL, schema, entity metadata, constructor, nullability, driver và converter.
- Chỉ đánh dấu lỗi đã sửa khi integration test xác nhận đọc/ghi trên database mục tiêu.

